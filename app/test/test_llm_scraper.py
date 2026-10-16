import json
import logging
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests

from jobrec.job_listing import JobListing
from jobrec.job_sources import SCRAPER_TYPES, JobSource, build_scraper
from jobrec.job_store import count_listings, list_listings
from jobrec.llm_scraper import (
    ExtractedListing,
    LlmPageScraper,
    PageCache,
    PostingLinks,
    page_text_and_links,
    structured_source_for,
)
from jobrec.scrape_pipeline import run_scrape_pipeline
from jobrec.scraper_base import ScraperRequestError

FIXTURES = Path(__file__).parent / "fixtures"
CAREERS = "https://acme-robotics.example/careers"
POSTING_A = "https://acme-robotics.example/careers/backend-engineer"
POSTING_B = "https://acme-robotics.example/careers/product-designer"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


# --- fakes: no network and no OpenAI key are needed ---


class FakeResponse:
    def __init__(self, text, status=200):
        self.text = text
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}", response=self)


class FakeSession:
    """Maps each URL to a page body (or an exception the request raises)."""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append(url)
        outcome = self.routes[url]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome if isinstance(outcome, FakeResponse) else FakeResponse(outcome)


class FakeClient:
    """Stands in for the OpenAI client: answers the link question with ``links`` and each extraction by page text."""

    def __init__(self, links, extractions):
        self.links = links
        # (needle found in the page text, ExtractedListing to answer with)
        self.extractions = extractions
        self.calls = []
        self.responses = SimpleNamespace(parse=self._parse)

    def _parse(self, **kwargs):
        self.calls.append(kwargs)
        text = kwargs["input"][0]["content"][0]["text"]
        if kwargs["text_format"] is PostingLinks:
            return SimpleNamespace(output_parsed=PostingLinks(urls=list(self.links)))
        for needle, extracted in self.extractions:
            if needle in text:
                return SimpleNamespace(output_parsed=extracted)
        return SimpleNamespace(output_parsed=ExtractedListing())

    def extraction_calls(self):
        return [c for c in self.calls if c["text_format"] is ExtractedListing]


def routes(**overrides):
    base = {CAREERS: fixture("llm_careers.html"), POSTING_A: fixture("llm_posting_a.html"), POSTING_B: fixture("llm_posting_b.html")}
    base.update(overrides)
    return base


EXTRACT_A = ExtractedListing(
    title="Backend Engineer",
    location="Remote, US",
    description="You will own the fleet coordination service that routes thousands of robots through our customers’ warehouses.",
    pay="$150,000 - $180,000 per year plus equity",
    status="open",
)
EXTRACT_B = ExtractedListing(title="Product Designer", location="Chicago, IL", description="You will design the operator console", pay=None, status="closed")


def make_scraper(session=None, client=None, cache=None, links=(POSTING_A, POSTING_B), extractions=None):
    client = client or FakeClient(links, extractions or [("Backend Engineer", EXTRACT_A), ("Product Designer", EXTRACT_B)])
    return LlmPageScraper(CAREERS, company_name="Acme Robotics", session=session or FakeSession(routes()), client=client, cache=cache), client


# --- parsing the page ---


# Visible text comes back without scripts and styles, and every link is absolute
def test_page_text_and_links_strip_noise_and_resolve_links():
    text, links = page_text_and_links(fixture("llm_careers.html"), CAREERS)

    assert "Open positions" in text and "Backend Engineer" in text
    assert "dataLayer" not in text and "display: flex" not in text
    assert (POSTING_A, "Backend Engineer") in links
    assert ("https://acme-robotics.example/about", "About us") in links
    assert not any(href.startswith("mailto:") for href, _ in links)


# --- fetching postings ---


# The model picks the posting links; each posting page is fetched and becomes a listing
def test_posting_links_are_identified_and_each_posting_fetched():
    session = FakeSession(routes())
    scraper, client = make_scraper(session=session)

    listings = scraper.fetch_jobs()

    assert [listing.application_url for listing in listings] == [POSTING_A, POSTING_B]
    assert session.calls == [CAREERS, POSTING_A, POSTING_B]
    assert all(listing.source == "llm" and listing.company_name == "Acme Robotics" for listing in listings)
    assert all(listing.source_job_id is None for listing in listings)
    # One model call to pick the links, one per posting to extract it
    assert len(client.calls) == 3


# Every field the model reads off the page is mapped onto the listing
def test_extracted_fields_are_mapped():
    scraper, _ = make_scraper()

    listing = scraper.fetch_jobs()[0]

    assert listing.title == "Backend Engineer"
    assert listing.location == "Remote, US"
    assert listing.pay == "$150,000 - $180,000 per year plus equity"
    assert "fleet coordination service" in listing.description
    assert listing.status == "open"


# A page that says the job is filled gives a closed listing, which the open-only view drops
def test_closed_notice_on_the_page_gives_a_closed_listing():
    scraper, _ = make_scraper()

    listings = scraper.fetch_jobs()

    assert listings[1].status == "closed"
    assert [listing.title for listing in scraper.fetch_open_jobs()] == ["Backend Engineer"]


# --- FR-004: only values that appear on the page are kept ---


# A value the model made up, which is not on the page, is dropped rather than stored
def test_values_not_on_the_page_are_dropped():
    invented = ExtractedListing(title="Backend Engineer", location="Mars", pay="$999,999", description="Invented summary of the job.", status="open")
    scraper, _ = make_scraper(extractions=[("Backend Engineer", invented), ("Product Designer", EXTRACT_B)])

    listing = scraper.fetch_jobs()[0]

    assert listing.location is None
    assert listing.pay is None
    # The description falls back to the page's own text rather than the invented summary
    assert "Invented summary" not in listing.description
    assert "fleet coordination service" in listing.description


# A value that matches the page except for case and spacing still counts as on the page
def test_whitespace_and_case_differences_still_count_as_verbatim():
    loose = ExtractedListing(title="backend engineer", location="Remote,   US", pay="$150,000 - $180,000  per year plus equity", description="", status="open")
    scraper, _ = make_scraper(extractions=[("Backend Engineer", loose), ("Product Designer", EXTRACT_B)])

    listing = scraper.fetch_jobs()[0]

    assert listing.title == "backend engineer"
    assert listing.location == "Remote,   US"
    assert listing.pay is not None


# A field the page does not have stays empty
def test_fields_absent_from_the_page_stay_empty():
    scraper, _ = make_scraper()

    designer = scraper.fetch_jobs()[1]

    assert designer.pay is None


# A posting whose title the model could not find on the page is skipped, not stored with a guessed title
def test_posting_without_a_verbatim_title_is_skipped(caplog):
    caplog.set_level(logging.WARNING)
    untitled = ExtractedListing(title="Senior Backend Wizard", location="Remote, US", description="", pay=None, status="open")
    scraper, _ = make_scraper(extractions=[("Backend Engineer", untitled), ("Product Designer", EXTRACT_B)])

    listings = scraper.fetch_jobs()

    assert [listing.title for listing in listings] == ["Product Designer"]
    assert POSTING_A in caplog.text


# A "closed" answer is only believed when the page itself says so
def test_closed_status_needs_a_closed_notice_on_the_page():
    closed_guess = ExtractedListing(title="Backend Engineer", location=None, description="", pay=None, status="closed")
    scraper, _ = make_scraper(extractions=[("Backend Engineer", closed_guess), ("Product Designer", EXTRACT_B)])

    assert scraper.fetch_jobs()[0].status == "open"


# A posting link the model returns that is not on the careers page is ignored
def test_posting_links_not_on_the_page_are_ignored():
    session = FakeSession(routes())
    scraper, _ = make_scraper(session=session, links=[POSTING_A, "https://acme-robotics.example/careers/made-up"])

    listings = scraper.fetch_jobs()

    assert [listing.application_url for listing in listings] == [POSTING_A]
    assert "https://acme-robotics.example/careers/made-up" not in session.calls


# --- caching: a posting costs one model call only when its page changed ---


# A second run over unchanged pages makes no model calls at all and returns the same listings
def test_unchanged_pages_are_served_from_the_cache():
    cache = PageCache()
    scraper, client = make_scraper(cache=cache)
    first = scraper.fetch_jobs()
    calls_before = len(client.calls)

    second = scraper.fetch_jobs()

    assert len(client.calls) == calls_before
    assert [listing.title for listing in second] == [listing.title for listing in first]
    assert second[0].pay == first[0].pay


# When one posting page changes, only that posting is extracted again
def test_changed_page_is_extracted_again():
    cache = PageCache()
    scraper, client = make_scraper(cache=cache)
    scraper.fetch_jobs()
    calls_before = len(client.calls)
    changed = fixture("llm_posting_a.html").replace("$150,000 - $180,000", "$160,000 - $190,000")
    scraper.session = FakeSession(routes(**{POSTING_A: changed}))
    client.extractions = [("Backend Engineer", EXTRACT_A.model_copy(update={"pay": "$160,000 - $190,000 per year plus equity"})), ("Product Designer", EXTRACT_B)]

    listings = scraper.fetch_jobs()

    assert len(client.extraction_calls()) == len([c for c in client.calls[:calls_before] if c["text_format"] is ExtractedListing]) + 1
    assert listings[0].pay == "$160,000 - $190,000 per year plus equity"


# The cache can be written to a file and read back, so a scheduled run does not start cold
def test_cache_round_trips_through_a_json_file(tmp_path):
    path = tmp_path / "llm_cache.json"
    cache = PageCache(path)
    scraper, client = make_scraper(cache=cache)
    scraper.fetch_jobs()
    cache.save()
    assert json.loads(path.read_text(encoding="utf-8"))

    reloaded = PageCache(path)
    scraper2, client2 = make_scraper(cache=reloaded)
    listings = scraper2.fetch_jobs()

    assert client2.calls == []
    assert [listing.title for listing in listings] == ["Backend Engineer", "Product Designer"]


# --- failures ---


# A careers page rendered only by JavaScript has no links to follow: nothing is returned and it is logged as unsupported
def test_js_only_page_is_unsupported(caplog):
    caplog.set_level(logging.WARNING)
    scraper, client = make_scraper(session=FakeSession({CAREERS: fixture("llm_careers_js_only.html")}))

    assert scraper.fetch_jobs() == []
    assert client.calls == []
    assert "unsupported" in caplog.text.lower() and CAREERS in caplog.text


# A posting page that cannot be fetched is skipped; the others are still returned
def test_posting_fetch_failure_skips_only_that_posting(caplog):
    caplog.set_level(logging.WARNING)
    scraper, _ = make_scraper(session=FakeSession(routes(**{POSTING_B: requests.ConnectionError("refused")})))

    listings = scraper.fetch_jobs()

    assert [listing.application_url for listing in listings] == [POSTING_A]
    assert POSTING_B in caplog.text


# A careers page that cannot be fetched raises the same error every scraper raises, so scrape_all moves on
def test_careers_page_failure_raises_scraper_request_error():
    scraper, _ = make_scraper(session=FakeSession({CAREERS: requests.Timeout("timed out")}))

    with pytest.raises(ScraperRequestError) as excinfo:
        scraper.fetch_jobs()
    assert excinfo.value.url == CAREERS


# A model that returns nothing usable (no postings) gives an empty result, not an error
def test_model_identifying_no_postings_gives_no_listings():
    scraper, _ = make_scraper(links=[])

    assert scraper.fetch_jobs() == []


# --- registry ---


# "llm" is a registry scraper type whose id is the careers page URL
def test_registry_builds_the_llm_scraper_from_a_careers_url():
    assert SCRAPER_TYPES["llm"] is LlmPageScraper

    scraper = build_scraper(JobSource(scraper="llm", id=CAREERS, company_name="Acme Robotics"))

    assert isinstance(scraper, LlmPageScraper)
    assert scraper.careers_url == CAREERS
    assert scraper.company_name == "Acme Robotics"


# Sources hosted on a supported job board must use that board's scraper, never the LLM
@pytest.mark.parametrize("url, expected", [
    ("https://boards.greenhouse.io/roblox", "greenhouse"),
    ("https://job-boards.greenhouse.io/figma/jobs/1", "greenhouse"),
    ("https://jobs.lever.co/palantir", "lever"),
    ("https://jobs.ashbyhq.com/ramp", "ashby"),
    ("https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite", "workday"),
])
def test_ats_hosted_sources_are_refused(url, expected):
    assert structured_source_for(url) == expected
    with pytest.raises(ValueError) as excinfo:
        build_scraper(JobSource(scraper="llm", id=url))
    assert expected in str(excinfo.value)


def test_ordinary_careers_sites_are_not_structured_sources():
    assert structured_source_for(CAREERS) is None


# --- the normal pipeline stores LLM listings like any other source ---


def test_llm_listings_go_through_the_normal_pipeline(engine):
    scraper, _ = make_scraper()

    result = run_scrape_pipeline(engine, [scraper])

    assert result.inserted == 1  # the closed designer posting is filtered out, as for every source
    stored = list_listings(engine)
    assert count_listings(engine) == 1
    assert stored[0].application_url == POSTING_A
    assert stored[0].source == "llm"
    assert isinstance(stored[0], JobListing)

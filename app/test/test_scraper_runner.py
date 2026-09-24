import logging
import os
import sys

# Lets this test import app/src/scraper_runner.py
SRC_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "src")
)
sys.path.insert(0, SRC_DIR)

from job_listing import JobListing  # noqa: E402
from scraper_base import BaseScraper, ScraperRequestError  # noqa: E402
from scraper_runner import fetch_all  # noqa: E402


def make_listing(source: str, title: str) -> JobListing:
    return JobListing(title=title, company_name="Acme", source=source, application_url="https://example.com/job")


class WorkingScraper(BaseScraper):
    """Returns a fixed set of listings without touching the network."""

    def __init__(self, source: str, titles: list[str]):
        self.source_name = source
        self._titles = titles

    def fetch_jobs(self) -> list[JobListing]:
        return [make_listing(self.source_name, title) for title in self._titles]


class UnreachableScraper(BaseScraper):
    source_name = "unreachable"

    def __init__(self):
        pass

    def fetch_jobs(self) -> list[JobListing]:
        raise ScraperRequestError(self.source_name, "https://down.example.com/jobs", "connection refused")


class BrokenScraper(BaseScraper):
    source_name = "broken"

    def __init__(self):
        pass

    def fetch_jobs(self) -> list[JobListing]:
        raise AttributeError("unexpected payload shape")


# Listings from every scraper are combined in the order the scrapers were given
def test_fetch_all_combines_listings_in_scraper_order():
    jobs = fetch_all([WorkingScraper("a", ["A1", "A2"]), WorkingScraper("b", ["B1"])])

    assert [job.title for job in jobs] == ["A1", "A2", "B1"]


# A source that cannot be reached does not stop the remaining sources
def test_fetch_all_continues_after_scraper_request_error():
    jobs = fetch_all([WorkingScraper("a", ["A1"]), UnreachableScraper(), WorkingScraper("b", ["B1"])])

    assert [job.title for job in jobs] == ["A1", "B1"]


# Even an unexpected bug in one scraper is logged and the run carries on
def test_fetch_all_continues_after_unexpected_exception_and_logs_it(caplog):
    caplog.set_level(logging.ERROR, logger="scraper_runner")

    jobs = fetch_all([BrokenScraper(), WorkingScraper("b", ["B1"])])

    assert [job.title for job in jobs] == ["B1"]
    errors = [r.getMessage() for r in caplog.records if r.levelno == logging.ERROR]
    assert len(errors) == 1
    assert "broken" in errors[0]


# When every source fails the result is simply empty
def test_fetch_all_returns_empty_when_every_scraper_fails():
    assert fetch_all([UnreachableScraper(), BrokenScraper()]) == []


# No scrapers means no listings
def test_fetch_all_with_no_scrapers_returns_empty_list():
    assert fetch_all([]) == []

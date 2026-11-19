import os
import sys

# Lets this test import app/src/scrape_all.py
SRC_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "src")
)
sys.path.insert(0, SRC_DIR)

import jobrec.job_sources as job_sources  # noqa: E402
from jobrec.job_listing import JobListing  # noqa: E402
from jobrec.job_sources import JobSource  # noqa: E402
from jobrec.job_store import count_listings  # noqa: E402
from jobrec.scrape_all import exit_code, scrape_sources  # noqa: E402
from jobrec.scraper_base import BaseScraper  # noqa: E402


class FakeScraper(BaseScraper):
    """Returns one listing per board; the board named "broken" cannot even be constructed."""

    source_name = "fake"

    def __init__(self, board, company_name=None, session=None):
        if board == "broken":
            raise ValueError("this source is misconfigured")
        self.board = board

    def fetch_jobs(self) -> list[JobListing]:
        return [
            JobListing(title=f"{self.board} job", company_name="Acme", source=self.source_name,
                       application_url=f"https://fake.example.com/{self.board}/1", source_job_id=f"{self.board}-1"),
        ]


# One source that blows up does not stop the sources around it from being stored
def test_failing_source_is_reported_and_the_rest_still_run(engine, monkeypatch):
    monkeypatch.setitem(job_sources.SCRAPER_TYPES, "fake", FakeScraper)
    sources = [JobSource(scraper="fake", id="one"), JobSource(scraper="fake", id="broken"), JobSource(scraper="fake", id="two")]

    results, failures = scrape_sources(engine, sources)

    assert [name for name, _ in results] == ["fake:one", "fake:two"]
    assert failures == ["fake:broken"]
    assert count_listings(engine) == 2


# Disabled sources are neither run nor counted as failures
def test_disabled_sources_are_skipped(engine, monkeypatch):
    monkeypatch.setitem(job_sources.SCRAPER_TYPES, "fake", FakeScraper)
    sources = [JobSource(scraper="fake", id="one"), JobSource(scraper="fake", id="broken", enabled=False)]

    results, failures = scrape_sources(engine, sources)

    assert [name for name, _ in results] == ["fake:one"]
    assert failures == []


# The demo registry the scheduled scrape uses loads, and every entry names a scraper that can be built
def test_demo_registry_loads_and_every_entry_builds_a_scraper():
    demo_path = os.path.join(os.path.dirname(job_sources.__file__), "job_sources_demo.json")

    sources = job_sources.load_sources(demo_path)

    assert len(sources) >= 10
    assert len({source.name for source in sources}) == len(sources)
    for source in sources:
        assert isinstance(job_sources.build_scraper(source), BaseScraper)


# The run succeeds only when nothing failed and the database holds listings
def test_exit_code_reflects_failures_and_empty_results():
    assert exit_code(failures=[], total_stored=10) == 0
    assert exit_code(failures=["fake:broken"], total_stored=10) == 1
    assert exit_code(failures=[], total_stored=0) == 1


class BigBoardScraper(BaseScraper):
    """Returns ten listings per board, so a cap has something to cut."""

    source_name = "big"

    def __init__(self, board, company_name=None, session=None):
        self.board = board

    def fetch_jobs(self) -> list[JobListing]:
        return [
            JobListing(title=f"{self.board} job {n}", company_name="Acme", source=self.source_name,
                       application_url=f"https://big.example.com/{self.board}/{n}", source_job_id=f"{self.board}-{n}")
            for n in range(10)
        ]


def big_sources(*boards):
    return [JobSource(scraper="big", id=board) for board in boards]


# Without a cap every listing of every source is stored, as the scheduled scrape needs
def test_no_cap_stores_every_listing(engine, monkeypatch):
    monkeypatch.setitem(job_sources.SCRAPER_TYPES, "big", BigBoardScraper)

    results, failures = scrape_sources(engine, big_sources("one", "two"))

    assert [result.inserted for _, result in results] == [10, 10]
    assert count_listings(engine) == 20


# --max-per-source N: each source stores at most N listings
def test_per_source_cap_limits_each_source(engine, monkeypatch):
    monkeypatch.setitem(job_sources.SCRAPER_TYPES, "big", BigBoardScraper)

    results, failures = scrape_sources(engine, big_sources("one", "two", "three"), max_per_source=3)

    assert [result.inserted for _, result in results] == [3, 3, 3]
    assert count_listings(engine) == 9


# --max-listings N: the whole run stores at most N, and sources after the budget is spent are not scraped
def test_total_cap_spreads_over_sources_and_stops_when_spent(engine, monkeypatch):
    monkeypatch.setitem(job_sources.SCRAPER_TYPES, "big", BigBoardScraper)

    results, failures = scrape_sources(engine, big_sources("one", "two", "three"), max_listings=15)

    assert [(name, result.inserted) for name, result in results] == [("big:one", 10), ("big:two", 5)]
    assert failures == []
    assert count_listings(engine) == 15


# Both caps together: each source takes the smaller of its own cap and what is left of the run's
def test_both_caps_take_the_smaller_limit(engine, monkeypatch):
    monkeypatch.setitem(job_sources.SCRAPER_TYPES, "big", BigBoardScraper)

    results, _ = scrape_sources(engine, big_sources("one", "two", "three"), max_per_source=4, max_listings=10)

    assert [result.inserted for _, result in results] == [4, 4, 2]
    assert count_listings(engine) == 10


# Listings already stored count toward the cap, so a repeated capped run does not grow the database
def test_repeated_capped_run_counts_listings_already_stored(engine, monkeypatch):
    monkeypatch.setitem(job_sources.SCRAPER_TYPES, "big", BigBoardScraper)
    scrape_sources(engine, big_sources("one", "two"), max_listings=12)

    results, _ = scrape_sources(engine, big_sources("one", "two"), max_listings=12)

    assert [(result.inserted, result.unchanged) for _, result in results] == [(0, 10), (0, 2)]
    assert count_listings(engine) == 12

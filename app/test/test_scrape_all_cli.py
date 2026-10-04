import os
import sys

# Lets this test import app/src/scrape_all.py
SRC_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "src")
)
sys.path.insert(0, SRC_DIR)

import job_sources  # noqa: E402
from job_listing import JobListing  # noqa: E402
from job_sources import JobSource  # noqa: E402
from job_store import count_listings  # noqa: E402
from scrape_all import exit_code, scrape_sources  # noqa: E402
from scraper_base import BaseScraper  # noqa: E402


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
    demo_path = os.path.join(SRC_DIR, "job_sources_demo.json")

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

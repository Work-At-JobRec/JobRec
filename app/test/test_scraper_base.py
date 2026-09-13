import os
import sys

import pytest

# Lets this test import app/src/scraper_base.py
SRC_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "src")
)
sys.path.insert(0, SRC_DIR)

from job_listing import JobListing  # noqa: E402
from scraper_base import BaseScraper  # noqa: E402


def make_listing(source: str) -> JobListing:
    return JobListing(
        title="Software Engineer",
        company_name="Acme",
        source=source,
        application_url="https://example.com/jobs/1",
    )


# The base interface itself cannot be instantiated
def test_base_scraper_cannot_be_instantiated():
    with pytest.raises(TypeError):
        BaseScraper()


# A subclass that forgets to implement fetch_jobs cannot be instantiated
def test_subclass_missing_fetch_jobs_cannot_be_instantiated():
    class Incomplete(BaseScraper):
        source_name = "incomplete"

    with pytest.raises(TypeError):
        Incomplete()


# A concrete scraper exposes its source name and returns JobListing objects
def test_concrete_scraper_returns_job_listings():
    class DummyScraper(BaseScraper):
        source_name = "dummy"

        def fetch_jobs(self) -> list[JobListing]:
            return [make_listing(self.source_name)]

    jobs = DummyScraper().fetch_jobs()

    assert DummyScraper.source_name == "dummy"
    assert len(jobs) == 1
    assert all(isinstance(job, JobListing) for job in jobs)
    assert jobs[0].source == "dummy"


# Consumers can treat any scraper the same way without knowing its concrete type
def test_consumer_can_iterate_multiple_scrapers_uniformly():
    class ScraperA(BaseScraper):
        source_name = "a"

        def fetch_jobs(self) -> list[JobListing]:
            return [make_listing("a")]

    class ScraperB(BaseScraper):
        source_name = "b"

        def fetch_jobs(self) -> list[JobListing]:
            return [make_listing("b"), make_listing("b")]

    scrapers: list[BaseScraper] = [ScraperA(), ScraperB()]

    collected = [job for scraper in scrapers for job in scraper.fetch_jobs()]

    assert [job.source for job in collected] == ["a", "b", "b"]

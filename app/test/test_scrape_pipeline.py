import os
import sys

import pytest
from sqlalchemy import create_engine

# Lets this test import app/src/scrape_pipeline.py
SRC_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "src")
)
sys.path.insert(0, SRC_DIR)

from db import Base  # noqa: E402
from job_listing import JobListing  # noqa: E402
from job_store import UpsertResult, count_listings, list_listings  # noqa: E402
from scrape_pipeline import run_scrape_pipeline  # noqa: E402
from scraper_base import BaseScraper, ScraperRequestError  # noqa: E402


@pytest.fixture
def engine(tmp_path):
    test_engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'jobs.db'}")
    Base.metadata.create_all(test_engine)
    return test_engine


class FixedScraper(BaseScraper):
    """Returns a fixed set of listings without touching the network."""

    source_name = "fixed"

    def __init__(self, listings: list[JobListing]):
        self._listings = listings

    def fetch_jobs(self) -> list[JobListing]:
        return list(self._listings)


class UnreachableScraper(BaseScraper):
    source_name = "unreachable"

    def __init__(self):
        pass

    def fetch_jobs(self) -> list[JobListing]:
        raise ScraperRequestError(self.source_name, "https://down.example.com/jobs", "connection refused")


def raw_listing(**overrides) -> JobListing:
    """A listing the way a scraper produces it: HTML description, tracking parameters, untidy whitespace."""
    fields = {
        "title": "  Software   Engineer ",
        "company_name": "Acme",
        "source": "fixed",
        "application_url": "https://acme.com/jobs/1?utm_source=newsletter",
        "description": "<p>Build <strong>things</strong>.</p>",
        "source_job_id": "1",
    }
    fields.update(overrides)
    return JobListing(**fields)


# Scraped listings are cleaned, checked, and stored in one step
def test_pipeline_normalizes_validates_and_stores(engine):
    scraper = FixedScraper([raw_listing(), raw_listing(title="", source_job_id="2")])

    result = run_scrape_pipeline(engine, [scraper])

    assert result == UpsertResult(inserted=1, updated=0, unchanged=0)
    assert count_listings(engine) == 1
    stored = list_listings(engine)[0]
    assert stored.title == "Software Engineer"
    assert stored.description == "Build things."
    assert stored.application_url == "https://acme.com/jobs/1"


# Running the pipeline again over the same source adds nothing new
def test_pipeline_second_run_reports_existing_not_new(engine):
    scraper = FixedScraper([raw_listing()])
    run_scrape_pipeline(engine, [scraper])

    result = run_scrape_pipeline(engine, [scraper])

    assert result == UpsertResult(inserted=0, updated=0, unchanged=1)
    assert count_listings(engine) == 1


# A source that cannot be reached does not stop the others from being stored
def test_pipeline_continues_past_unreachable_scraper(engine):
    result = run_scrape_pipeline(engine, [UnreachableScraper(), FixedScraper([raw_listing()])])

    assert result.inserted == 1
    assert count_listings(engine) == 1

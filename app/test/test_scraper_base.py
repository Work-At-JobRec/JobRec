import logging
import os
import sys
from unittest.mock import Mock

import pytest
import requests

# Lets this test import app/src/scraper_base.py
SRC_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "src")
)
sys.path.insert(0, SRC_DIR)

from job_listing import JobListing  # noqa: E402
from scraper_base import BaseScraper, ScraperRequestError  # noqa: E402


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


# --- request error handling (#27) ---

URL = "https://example.com/api/jobs"


class DummyScraper(BaseScraper):
    source_name = "dummy"

    def fetch_jobs(self) -> list[JobListing]:
        return []


def make_session(payload=None, get_error=None, status_error=None, json_error=None) -> Mock:
    """A stand-in for requests.Session that succeeds or fails in a chosen way."""
    response = Mock()
    response.json.return_value = payload
    response.json.side_effect = json_error
    response.raise_for_status.side_effect = status_error
    session = Mock()
    session.get.return_value = response
    session.get.side_effect = get_error
    return session


# A successful request returns the decoded JSON body
def test_get_json_returns_decoded_body():
    scraper = DummyScraper(session=make_session(payload={"jobs": []}))

    assert scraper._get_json(URL) == {"jobs": []}


# Query parameters and a timeout are always passed to the HTTP call
def test_get_json_passes_params_and_timeout():
    session = make_session(payload={})

    DummyScraper(session=session)._get_json(URL, params={"content": "true"}, timeout=3)

    session.get.assert_called_once_with(URL, params={"content": "true"}, timeout=3)


# A dropped connection becomes a ScraperRequestError that remembers the URL and the cause
def test_get_json_connection_error_raises_scraper_request_error():
    cause = requests.ConnectionError("connection refused")
    scraper = DummyScraper(session=make_session(get_error=cause))

    with pytest.raises(ScraperRequestError) as excinfo:
        scraper._get_json(URL)

    assert excinfo.value.url == URL
    assert excinfo.value.source == "dummy"
    assert excinfo.value.__cause__ is cause


# A request that takes too long becomes a ScraperRequestError
def test_get_json_timeout_raises_scraper_request_error():
    scraper = DummyScraper(session=make_session(get_error=requests.Timeout("timed out")))

    with pytest.raises(ScraperRequestError):
        scraper._get_json(URL)


# A non-2xx response becomes a ScraperRequestError that reports the status code
def test_get_json_http_error_raises_scraper_request_error():
    error = requests.HTTPError("Server Error", response=Mock(status_code=503))
    scraper = DummyScraper(session=make_session(status_error=error))

    with pytest.raises(ScraperRequestError) as excinfo:
        scraper._get_json(URL)

    assert "503" in str(excinfo.value)


# A body that is not JSON becomes a ScraperRequestError
def test_get_json_invalid_json_raises_scraper_request_error():
    scraper = DummyScraper(session=make_session(json_error=ValueError("Expecting value")))

    with pytest.raises(ScraperRequestError):
        scraper._get_json(URL)


# A failed request is logged once with the source, the URL, and the error
def test_get_json_failure_logs_source_url_and_error(caplog):
    caplog.set_level(logging.ERROR, logger="scraper_base")
    scraper = DummyScraper(session=make_session(get_error=requests.ConnectionError("connection refused")))

    with pytest.raises(ScraperRequestError):
        scraper._get_json(URL)

    errors = [r.getMessage() for r in caplog.records if r.levelno == logging.ERROR]
    assert len(errors) == 1
    assert "dummy" in errors[0] and URL in errors[0] and "connection refused" in errors[0]


def to_listing(raw: dict) -> JobListing:
    return JobListing(title=raw["title"], company_name="Acme", source="dummy", application_url=raw["url"])


# One item that cannot be converted is skipped; the rest are still returned
def test_build_listings_skips_item_that_fails_conversion_and_keeps_rest():
    raw_items = [
        {"id": 1, "title": "Engineer", "url": "https://example.com/1"},
        {"id": 2, "title": 123, "url": "https://example.com/2"},
        {"id": 3, "url": "https://example.com/3"},
        None,
        {"id": 5, "title": "Designer", "url": "https://example.com/5"},
    ]

    listings = DummyScraper(session=Mock())._build_listings(raw_items, to_listing)

    assert [listing.title for listing in listings] == ["Engineer", "Designer"]


# Each skipped item is logged with the source and the raw job id
def test_build_listings_logs_warning_with_source_and_raw_id(caplog):
    caplog.set_level(logging.WARNING, logger="scraper_base")
    raw_items = [{"id": 42, "title": 123, "url": "https://example.com/42"}]

    DummyScraper(session=Mock())._build_listings(raw_items, to_listing)

    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "dummy" in warnings[0] and "42" in warnings[0]

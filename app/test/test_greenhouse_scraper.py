import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import ANY, Mock

# Lets this test import app/src/greenhouse_scraper.py
SRC_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "src")
)
sys.path.insert(0, SRC_DIR)

from job_listing import JobListing  # noqa: E402
from greenhouse_scraper import GreenhouseScraper, GREENHOUSE_JOBS_URL, parse_iso8601  # noqa: E402

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "greenhouse_jobs.json"


def load_fixture() -> dict:
    """Saved Greenhouse Job Board API response so tests never hit the network."""
    with open(FIXTURE_PATH, encoding="utf-8") as f:
        return json.load(f)


def make_session(payload: dict) -> Mock:
    """A stand-in for requests.Session whose GET always returns the given JSON payload."""
    response = Mock()
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    session = Mock()
    session.get.return_value = response
    return session


def make_scraper(payload=None, **kwargs) -> GreenhouseScraper:
    payload = load_fixture() if payload is None else payload
    return GreenhouseScraper("acme", session=make_session(payload), **kwargs)


# Every job in the API response becomes one JobListing
def test_fetch_jobs_returns_one_listing_per_job():
    jobs = make_scraper().fetch_jobs()

    assert len(jobs) == 3
    assert all(isinstance(job, JobListing) for job in jobs)


# The scraper calls the board's jobs endpoint and asks for full job content
def test_fetch_jobs_requests_board_url_with_content_param():
    session = make_session(load_fixture())

    GreenhouseScraper("acme", session=session).fetch_jobs()

    session.get.assert_called_once_with(
        GREENHOUSE_JOBS_URL.format(board_token="acme"),
        params={"content": "true"},
        timeout=ANY,
    )


# A fully populated Greenhouse job maps onto every JobListing field
def test_complete_job_maps_every_field():
    job = make_scraper().fetch_jobs()[0]

    assert job.title == "Software Engineer, Payments"
    assert job.company_name == "Acme Corp"
    assert job.location == "Dublin"
    assert job.application_url == "https://acme.com/jobs?gh_jid=4012345"
    assert job.source == "greenhouse"
    assert job.source_job_id == "4012345"
    assert job.posted_at == datetime(2026, 9, 3, 13, 30, 34, tzinfo=timezone(timedelta(hours=-4)))


# Greenhouse returns the description HTML-escaped; the scraper decodes it to real HTML
def test_description_is_html_unescaped():
    job = make_scraper().fetch_jobs()[0]

    assert "<h2>" in job.description
    assert "&lt;" not in job.description
    assert "&amp;" not in job.description
    assert "payment infrastructure & tooling" in job.description


# Jobs missing optional fields are still returned, with sensible fallbacks
def test_missing_optional_fields_tolerated():
    job = make_scraper().fetch_jobs()[1]

    assert job.title == "Data Analyst"
    assert job.location is None
    assert job.description == ""
    assert job.posted_at == datetime(2026, 9, 10, 8, 0, 0, tzinfo=timezone.utc)


# A location object whose name is null maps to no location
def test_null_location_name_maps_to_none():
    job = make_scraper().fetch_jobs()[2]

    assert job.location is None
    assert job.posted_at is None


# A company name given to the constructor wins over whatever the API reports
def test_constructor_company_name_overrides_payload():
    job = make_scraper(company_name="Acme Inc.").fetch_jobs()[0]

    assert job.company_name == "Acme Inc."


# When neither the constructor nor the API give a company name, the board token is used
def test_company_name_falls_back_to_board_token():
    job = make_scraper().fetch_jobs()[1]

    assert job.company_name == "acme"


# An empty board yields no listings rather than an error
def test_empty_jobs_payload_returns_empty_list():
    assert make_scraper(payload={"jobs": [], "meta": {"total": 0}}).fetch_jobs() == []


# A response without a jobs key yields no listings rather than an error
def test_missing_jobs_key_returns_empty_list():
    assert make_scraper(payload={}).fetch_jobs() == []


# Timestamp parsing accepts the "Z" UTC suffix that Python 3.10 cannot parse natively
def test_parse_iso8601_accepts_z_suffix():
    assert parse_iso8601("2026-09-10T08:00:00Z") == datetime(2026, 9, 10, 8, 0, 0, tzinfo=timezone.utc)


# Timestamp parsing keeps explicit UTC offsets
def test_parse_iso8601_accepts_offset():
    assert parse_iso8601("2026-09-03T13:30:34-04:00") == datetime(
        2026, 9, 3, 13, 30, 34, tzinfo=timezone(timedelta(hours=-4))
    )


# Unparseable or absent timestamps become None instead of raising
def test_parse_iso8601_invalid_or_missing_returns_none():
    assert parse_iso8601("not a date") is None
    assert parse_iso8601("") is None
    assert parse_iso8601(None) is None


# One job that cannot be mapped is skipped instead of losing the whole board
def test_fetch_jobs_skips_job_that_cannot_be_mapped():
    payload = load_fixture()
    payload["jobs"].insert(1, {"id": 999, "title": 123, "absolute_url": "https://acme.com/jobs?gh_jid=999"})
    payload["jobs"].insert(2, {"id": 998, "title": "Bad location", "location": "Dublin"})

    jobs = make_scraper(payload=payload).fetch_jobs()

    assert [job.source_job_id for job in jobs] == ["4012345", "4012346", "4012347"]

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import ANY, Mock

import pytest
import requests

# Lets this test import app/src/lever_scraper.py
SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, SRC_DIR)

from app.jobrec.job_listing import JobListing  # noqa: E402
from app.jobrec.lever_scraper import (
    LEVER_POSTINGS_URL,
    LeverScraper,
    format_salary_range,
    parse_epoch_millis,
)  # noqa: E402
from app.jobrec.scraper_base import ScraperRequestError  # noqa: E402

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "lever_postings.json"
BOARD_URL = LEVER_POSTINGS_URL.format(company="acme")


def load_fixture() -> list:
    """Saved Lever postings API response so tests never hit the network."""
    with open(FIXTURE_PATH, encoding="utf-8") as f:
        return json.load(f)


def make_session(payload) -> Mock:
    response = Mock()
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    session = Mock()
    session.get.return_value = response
    return session


def make_scraper(payload=None, **kwargs) -> LeverScraper:
    payload = load_fixture() if payload is None else payload
    return LeverScraper("acme", session=make_session(payload), **kwargs)


# Every posting in the API response becomes one JobListing
def test_fetch_jobs_returns_one_listing_per_posting():
    jobs = make_scraper().fetch_jobs()

    assert len(jobs) == 3
    assert all(isinstance(job, JobListing) for job in jobs)


# The scraper calls the company's postings endpoint in JSON mode
def test_fetch_jobs_requests_postings_url_in_json_mode():
    session = make_session(load_fixture())

    LeverScraper("acme", session=session).fetch_jobs()

    session.get.assert_called_once_with(BOARD_URL, params={"mode": "json"}, timeout=ANY)


# A fully populated posting maps onto every JobListing field
def test_complete_posting_maps_every_field():
    job = make_scraper().fetch_jobs()[0]

    assert job.title == "Administrative Business Partner"
    assert job.company_name == "acme"
    assert job.location == "Singapore, Singapore"
    assert (
        job.application_url
        == "https://jobs.lever.co/acme/6ed76ce8-4156-4b60-b120-403538bd66cd"
    )
    assert job.source == "lever"
    assert job.source_job_id == "6ed76ce8-4156-4b60-b120-403538bd66cd"
    assert job.posted_at == datetime.fromtimestamp(
        1786469891368 / 1000, tz=timezone.utc
    )
    assert job.pay == "USD 90,000-120,000 (per year)"
    assert job.status == "open"


# The description keeps the opening text, every list section with its heading, and the closing text
def test_description_combines_opening_lists_and_additional():
    description = make_scraper().fetch_jobs()[0].description

    assert "A World-Changing Company" in description
    assert "What you'll do" in description
    assert "<li>Provide administrative support.</li>" in description
    assert "equal opportunity employer" in description
    assert (
        description.index("A World-Changing Company")
        < description.index("What you'll do")
        < description.index("equal opportunity")
    )


# A company name given to the constructor is used instead of the slug
def test_constructor_company_name_overrides_slug():
    assert (
        make_scraper(company_name="Acme Inc.").fetch_jobs()[0].company_name
        == "Acme Inc."
    )


# Postings missing optional fields are still returned with sensible fallbacks
def test_missing_optional_fields_tolerated():
    jobs = make_scraper().fetch_jobs()

    assert jobs[1].location is None
    assert jobs[1].description == ""
    assert jobs[1].pay is None
    assert jobs[2].posted_at is None
    assert jobs[2].pay is None


# An empty board yields no listings rather than an error
def test_empty_board_returns_empty_list():
    assert make_scraper(payload=[]).fetch_jobs() == []


# A response that is not a list yields no listings rather than an error
def test_non_list_payload_returns_empty_list():
    assert make_scraper(payload={"error": "not found"}).fetch_jobs() == []


# One posting that cannot be mapped is skipped instead of losing the whole board
def test_posting_that_cannot_be_mapped_is_skipped(caplog):
    caplog.set_level(logging.WARNING, logger="scraper_base")
    payload = load_fixture()
    payload.insert(
        1, {"id": "bad", "text": 123, "hostedUrl": "https://jobs.lever.co/acme/bad"}
    )

    jobs = make_scraper(payload=payload).fetch_jobs()

    assert [job.title for job in jobs] == [
        "Administrative Business Partner",
        "Data Analyst",
        "Product Designer",
    ]
    assert any("bad" in r.getMessage() for r in caplog.records)


# A failed request is reported with the board URL
def test_failed_request_raises_scraper_request_error_with_board_url():
    session = Mock()
    session.get.side_effect = requests.ConnectionError("refused")

    with pytest.raises(ScraperRequestError) as excinfo:
        LeverScraper("acme", session=session).fetch_jobs()

    assert excinfo.value.url == BOARD_URL
    assert excinfo.value.source == "lever"


# --- helpers ---


# Lever timestamps are epoch milliseconds and become timezone-aware UTC datetimes
def test_parse_epoch_millis():
    assert parse_epoch_millis(1786469891368) == datetime(
        2026, 8, 11, 17, 38, 11, 368000, tzinfo=timezone.utc
    )
    assert parse_epoch_millis(None) is None
    assert parse_epoch_millis("soon") is None


# A published salary range becomes one readable line
def test_format_salary_range():
    assert (
        format_salary_range(
            {
                "min": 90000,
                "max": 120000,
                "currency": "USD",
                "interval": "per-year-salary",
            }
        )
        == "USD 90,000-120,000 (per year)"
    )
    assert (
        format_salary_range(
            {"min": 40, "max": 60, "currency": "USD", "interval": "per-hour-wage"}
        )
        == "USD 40-60 (per hour)"
    )
    assert (
        format_salary_range({"min": 1000, "max": 2000, "currency": "EUR"})
        == "EUR 1,000-2,000"
    )
    assert format_salary_range(None) is None
    assert format_salary_range({"min": "lots"}) is None

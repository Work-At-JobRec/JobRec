import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import ANY, Mock

import pytest
import requests

# Lets this test import app/src/ashby_scraper.py
SRC_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "src")
)
sys.path.insert(0, SRC_DIR)

from jobrec.ashby_scraper import ASHBY_JOB_BOARD_URL, AshbyScraper, format_compensation  # noqa: E402
from jobrec.job_listing import JobListing  # noqa: E402
from jobrec.job_sources import DEFAULT_SOURCES_PATH, JobSource, build_scraper, load_sources  # noqa: E402
from jobrec.scraper_base import ScraperRequestError  # noqa: E402

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "ashby_jobs.json"
BOARD_URL = ASHBY_JOB_BOARD_URL.format(organization="acme")


def load_fixture() -> dict:
    """Saved Ashby job board API response so tests never hit the network."""
    with open(FIXTURE_PATH, encoding="utf-8") as f:
        return json.load(f)


def make_session(payload) -> Mock:
    response = Mock()
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    session = Mock()
    session.get.return_value = response
    return session


def make_scraper(payload=None, **kwargs) -> AshbyScraper:
    payload = load_fixture() if payload is None else payload
    return AshbyScraper("acme", session=make_session(payload), **kwargs)


# Every job in the API response becomes one JobListing
def test_fetch_jobs_returns_one_listing_per_job():
    jobs = make_scraper().fetch_jobs()

    assert len(jobs) == 3
    assert all(isinstance(job, JobListing) for job in jobs)


# The scraper calls the organization's job board endpoint and asks for compensation
def test_fetch_jobs_requests_board_url_with_compensation():
    session = make_session(load_fixture())

    AshbyScraper("acme", session=session).fetch_jobs()

    session.get.assert_called_once_with(BOARD_URL, params={"includeCompensation": "true"}, timeout=ANY)


# A fully populated job maps onto every JobListing field
def test_complete_job_maps_every_field():
    job = make_scraper().fetch_jobs()[0]

    assert job.title == " Security Engineer, Cloud"
    assert job.company_name == "acme"
    assert job.location == "New York, NY (HQ)"
    assert job.application_url == "https://jobs.ashbyhq.com/acme/34413f8d-26bf-4bbc-8ade-eb309a0e2245"
    assert job.source == "ashby"
    assert job.source_job_id == "34413f8d-26bf-4bbc-8ade-eb309a0e2245"
    assert job.posted_at == datetime(2026, 4, 7, 17, 12, 35, 753000, tzinfo=timezone.utc)
    assert job.pay == "USD 211,400-290,600 (per year)"
    assert job.status == "open"
    assert "<li>Secure our cloud.</li>" in job.description


# A company name given to the constructor is used instead of the slug
def test_constructor_company_name_overrides_slug():
    assert make_scraper(company_name="Acme Inc.").fetch_jobs()[0].company_name == "Acme Inc."


# Jobs missing optional fields are still returned with sensible fallbacks
def test_missing_optional_fields_tolerated():
    job = make_scraper().fetch_jobs()[1]

    assert job.title == "Software Engineering Intern"
    assert job.location is None
    assert job.description == ""
    assert job.posted_at is None
    assert job.pay is None
    assert job.status == "open"


# A job the board no longer lists is reported as closed, and the open-only view leaves it out
def test_unlisted_job_is_closed_and_excluded_from_open_jobs():
    scraper = make_scraper()

    assert scraper.fetch_jobs()[2].status == "closed"
    assert [job.title for job in scraper.fetch_open_jobs()] == [" Security Engineer, Cloud", "Software Engineering Intern"]


# When there is no structured salary, Ashby's own summary text is used
def test_pay_falls_back_to_summary_text():
    assert make_scraper().fetch_jobs()[2].pay == "$60 - $75 per hour"


# An empty or unexpected response yields no listings rather than an error
def test_empty_or_unexpected_payload_returns_empty_list():
    assert make_scraper(payload={"jobs": []}).fetch_jobs() == []
    assert make_scraper(payload={}).fetch_jobs() == []
    assert make_scraper(payload=[]).fetch_jobs() == []


# One job that cannot be mapped is skipped instead of losing the whole board
def test_job_that_cannot_be_mapped_is_skipped(caplog):
    caplog.set_level(logging.WARNING, logger="jobrec.scraper_base")
    payload = load_fixture()
    payload["jobs"].insert(1, {"id": "bad", "title": 123, "jobUrl": "https://jobs.ashbyhq.com/acme/bad"})

    jobs = make_scraper(payload=payload).fetch_jobs()

    assert len(jobs) == 3
    assert any("bad" in r.getMessage() for r in caplog.records)


# A failed request is reported with the board URL
def test_failed_request_raises_scraper_request_error_with_board_url():
    session = Mock()
    session.get.side_effect = requests.ConnectionError("refused")

    with pytest.raises(ScraperRequestError) as excinfo:
        AshbyScraper("acme", session=session).fetch_jobs()

    assert excinfo.value.url == BOARD_URL
    assert excinfo.value.source == "ashby"


# --- compensation helper ---

# The structured salary component becomes the same readable line the other scrapers produce
def test_format_compensation_prefers_the_salary_component():
    compensation = {
        "scrapeableCompensationSalarySummary": "$211.4K - $290.6K",
        "summaryComponents": [
            {"compensationType": "EquityPercentage", "interval": "NONE", "currencyCode": None, "minValue": None, "maxValue": None},
            {"compensationType": "Salary", "interval": "1 YEAR", "currencyCode": "USD", "minValue": 211400, "maxValue": 290600},
        ],
    }

    assert format_compensation(compensation) == "USD 211,400-290,600 (per year)"


# Hourly pay keeps its interval
def test_format_compensation_hourly_interval():
    compensation = {"summaryComponents": [
        {"compensationType": "Salary", "interval": "1 HOUR", "currencyCode": "USD", "minValue": 40, "maxValue": 55},
    ]}

    assert format_compensation(compensation) == "USD 40-55 (per hour)"


# Missing or malformed compensation gives no pay rather than an error
def test_format_compensation_missing_or_malformed():
    assert format_compensation(None) is None
    assert format_compensation({}) is None
    assert format_compensation({"summaryComponents": [{"compensationType": "Salary", "minValue": "lots"}]}) is None
    assert format_compensation("free text") is None


# --- registry ---

# The registry builds an Ashby scraper from an "ashby" entry
def test_registry_builds_an_ashby_scraper():
    scraper = build_scraper(JobSource(scraper="ashby", id="acme", company_name="Acme"))

    assert isinstance(scraper, AshbyScraper)
    assert scraper.organization == "acme" and scraper.company_name == "Acme"


# The demo registry includes Ashby companies and still loads
def test_demo_registry_includes_ashby_sources():
    sources = load_sources(DEFAULT_SOURCES_PATH.parent / "job_sources_demo.json")

    assert any(source.scraper == "ashby" for source in sources)

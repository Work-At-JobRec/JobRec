import copy
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import ANY, Mock

import pytest
import requests

# Lets this test import app/src/workday_scraper.py
SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, SRC_DIR)

from jobrec.job_listing import JobListing  # noqa: E402
from jobrec.scraper_base import ScraperRequestError  # noqa: E402
from jobrec.workday_scraper import WorkdayScraper, parse_workday_date  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"
BOARD = "acme.wd5.myworkdayjobs.com/AcmeExternalCareerSite"
BASE_URL = "https://acme.wd5.myworkdayjobs.com/wday/cxs/acme/AcmeExternalCareerSite"


def load_page() -> dict:
    with open(FIXTURES / "workday_jobs_page.json", encoding="utf-8") as f:
        return json.load(f)


def load_detail() -> dict:
    with open(FIXTURES / "workday_job_detail.json", encoding="utf-8") as f:
        return json.load(f)


def make_postings(count: int) -> list[dict]:
    """count postings in the style of the saved page, numbered so each has its own path and requisition id."""
    template = load_page()["jobPostings"][0]
    postings = []
    for i in range(count):
        posting = copy.deepcopy(template)
        posting["title"] = f"Job {i}"
        posting["externalPath"] = f"/job/Remote/Job-{i}_JR{i:07d}"
        posting["bulletFields"] = [f"JR{i:07d}"]
        postings.append(posting)
    return postings


def make_session(
    postings: list[dict],
    page_size: int,
    failing_paths: set = (),
    detail_overrides: dict = None,
) -> Mock:
    """A stand-in session: POST returns the page of postings at the requested offset, GET returns a detail per path."""
    detail_overrides = detail_overrides or {}

    def post(url, json=None, timeout=None):
        offset = json["offset"]
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "total": len(postings),
            "jobPostings": postings[offset : offset + page_size],
        }
        return response

    def get(url, params=None, timeout=None):
        path = url[len(BASE_URL) :]
        if path in failing_paths:
            raise requests.ConnectionError(f"refused for {path}")
        posting = next(p for p in postings if p["externalPath"] == path)
        detail = load_detail()
        detail["jobPostingInfo"]["title"] = posting["title"]
        detail["jobPostingInfo"]["jobReqId"] = posting["bulletFields"][0]
        detail["jobPostingInfo"].update(detail_overrides.get(path, {}))
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = detail
        return response

    session = Mock()
    session.post.side_effect = post
    session.get.side_effect = get
    return session


def make_scraper(postings=None, page_size=3, **kwargs) -> WorkdayScraper:
    postings = make_postings(7) if postings is None else postings
    session = make_session(
        postings,
        page_size,
        kwargs.pop("failing_paths", ()),
        kwargs.pop("detail_overrides", None),
    )
    return WorkdayScraper(BOARD, session=session, page_size=page_size, **kwargs)


# --- board identifier ---


# The board string "host/site" is split into the host, tenant, and site the endpoints need
def test_board_string_is_parsed_into_host_tenant_and_site():
    scraper = WorkdayScraper(BOARD, session=Mock())

    assert scraper.host == "acme.wd5.myworkdayjobs.com"
    assert scraper.tenant == "acme"
    assert scraper.site == "AcmeExternalCareerSite"


# A board string without a site is rejected up front
def test_board_string_without_site_is_rejected():
    with pytest.raises(ValueError):
        WorkdayScraper("acme.wd5.myworkdayjobs.com", session=Mock())


# --- pagination ---


# Every page is requested until the postings run out
def test_fetch_jobs_pages_through_listing_until_exhausted():
    scraper = make_scraper(page_size=3)

    jobs = scraper.fetch_jobs()

    assert len(jobs) == 7
    offsets = [
        call.kwargs["json"]["offset"] for call in scraper.session.post.call_args_list
    ]
    assert offsets == [0, 3, 6]


# Paging stops after the configured number of pages
def test_fetch_jobs_stops_at_max_pages():
    scraper = make_scraper(page_size=3, max_pages=2)

    jobs = scraper.fetch_jobs()

    assert len(jobs) == 6
    assert scraper.session.post.call_count == 2


# Each page is requested from the listing endpoint with Workday's expected body
def test_listing_request_shape():
    scraper = make_scraper(page_size=3)

    scraper.fetch_jobs()

    first = scraper.session.post.call_args_list[0]
    assert first.args[0] == BASE_URL + "/jobs"
    assert first.kwargs["json"] == {
        "appliedFacets": {},
        "limit": 3,
        "offset": 0,
        "searchText": "",
    }
    assert first.kwargs["timeout"] is not None


# An empty board yields no listings and stops after the first page
def test_empty_board_returns_empty_list():
    scraper = make_scraper(postings=[], page_size=3)

    assert scraper.fetch_jobs() == []
    assert scraper.session.post.call_count == 1


# --- field mapping ---


# A posting's detail response maps onto every JobListing field
def test_detail_maps_every_field():
    postings = load_page()["jobPostings"][:1]
    scraper = make_scraper(postings=postings, company_name="Acme Corp")

    job = scraper.fetch_jobs()[0]

    assert isinstance(job, JobListing)
    assert job.title == "Senior Solutions Architect, Agentic AI"
    assert job.company_name == "Acme Corp"
    assert job.location == "India, Gurugram"
    assert "Generative AI Solution Architect" in job.description
    assert "<li>Design agentic systems.</li>" in job.description
    assert job.application_url == (
        "https://acme.wd5.myworkdayjobs.com/AcmeExternalCareerSite"
        "/job/India-Gurugram/Senior-Solutions-Architect--Agentic-AI_JR2026267"
    )
    assert job.source == "workday"
    assert job.source_job_id == "JR2026267"
    assert job.posted_at == datetime(2026, 9, 28, tzinfo=timezone.utc)
    assert job.pay is None
    assert job.status == "open"


# Without a company name the tenant is used
def test_company_name_falls_back_to_tenant():
    assert (
        make_scraper(postings=make_postings(1)).fetch_jobs()[0].company_name == "acme"
    )


# A posting that Workday says can no longer be applied to is closed
def test_can_apply_false_is_closed():
    postings = make_postings(2)
    scraper = make_scraper(
        postings=postings,
        detail_overrides={postings[1]["externalPath"]: {"canApply": False}},
    )

    jobs = scraper.fetch_jobs()

    assert [job.status for job in jobs] == ["open", "closed"]


# A detail response missing optional fields still yields a listing
def test_detail_missing_optional_fields_tolerated():
    postings = make_postings(1)
    postings[0][
        "locationsText"
    ] = None  # neither the listing page nor the detail names a location
    overrides = {
        postings[0]["externalPath"]: {
            "startDate": None,
            "location": None,
            "jobDescription": None,
        }
    }
    scraper = make_scraper(postings=postings, detail_overrides=overrides)

    job = scraper.fetch_jobs()[0]

    assert job.posted_at is None
    assert job.location is None
    assert job.description == ""


# --- failures ---


# A posting whose detail cannot be fetched is skipped and logged; the rest are kept
def test_detail_failure_skips_posting_and_keeps_rest(caplog):
    caplog.set_level(logging.WARNING, logger="workday_scraper")
    postings = make_postings(3)
    scraper = make_scraper(
        postings=postings, failing_paths={postings[1]["externalPath"]}
    )

    jobs = scraper.fetch_jobs()

    assert [job.title for job in jobs] == ["Job 0", "Job 2"]
    assert any(postings[1]["externalPath"] in r.getMessage() for r in caplog.records)


# A failed listing request is reported with the listing URL
def test_listing_failure_raises_scraper_request_error():
    session = Mock()
    session.post.side_effect = requests.ConnectionError("refused")

    with pytest.raises(ScraperRequestError) as excinfo:
        WorkdayScraper(BOARD, session=session).fetch_jobs()

    assert excinfo.value.url == BASE_URL + "/jobs"
    assert excinfo.value.source == "workday"


# --- helpers ---


# Workday start dates are plain dates and become UTC midnight datetimes
def test_parse_workday_date():
    assert parse_workday_date("2026-09-28") == datetime(
        2026, 9, 28, tzinfo=timezone.utc
    )
    assert parse_workday_date(None) is None
    assert parse_workday_date("Posted Today") is None

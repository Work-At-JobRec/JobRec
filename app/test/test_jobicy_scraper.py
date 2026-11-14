from datetime import datetime, timezone
from unittest.mock import Mock

import pytest
import requests

from jobrec.jobicy_scraper import (
    JOBICY_JOBS_URL,
    JobicyScraper,
    format_salary,
    parse_pub_date,
)
from jobrec.scraper_base import ScraperRequestError

NOW = datetime(2026, 11, 14, 18, 0, tzinfo=timezone.utc)


def job(job_id, pub_date="2026-11-14T16:07:57+00:00", **fields):
    """One job as the Jobicy API returns it."""
    data = {
        "id": job_id,
        "url": f"https://jobicy.com/jobs/{job_id}-role",
        "jobTitle": f"Role {job_id}",
        "companyName": "Acme Health",
        "jobIndustry": ["Healthcare & Medical"],
        "jobType": ["Full-Time"],
        "jobGeo": "USA",
        "jobLevel": "Any",
        "jobDescription": "<p>Care coordination.</p>",
        "pubDate": pub_date,
        "salaryMin": 60000,
        "salaryMax": 75000,
        "salaryCurrency": "USD",
        "salaryPeriod": "yearly",
    }
    data.update(fields)
    return data


def page(jobs, cursor=None, has_more=None):
    return {
        "jobs": jobs,
        "nextCursor": cursor,
        "hasMore": bool(cursor) if has_more is None else has_more,
    }


def make_session(*payloads) -> Mock:
    responses = []
    for payload in payloads:
        response = Mock()
        response.json.return_value = payload
        response.raise_for_status.return_value = None
        responses.append(response)
    session = Mock()
    session.get.side_effect = responses
    return session


def make_scraper(*payloads, **kwargs):
    session = make_session(*payloads)
    kwargs.setdefault("now", NOW)
    return JobicyScraper(session=session, **kwargs), session


# Each Jobicy job becomes a JobListing with its own company, remote location, link and pay
def test_fetch_jobs_maps_each_field():
    scraper, _ = make_scraper(page([job(162244)]))

    [listing] = scraper.fetch_jobs()

    assert listing.title == "Role 162244"
    assert listing.company_name == "Acme Health"
    assert listing.location == "Remote (USA)"
    assert listing.description == "<p>Care coordination.</p>"
    assert listing.source == "jobicy"
    assert listing.application_url == "https://jobicy.com/jobs/162244-role"
    assert listing.posted_at == datetime(2026, 11, 14, 16, 7, 57, tzinfo=timezone.utc)
    assert listing.source_job_id == "162244"
    assert listing.pay == "USD 60,000-75,000 (per year)"
    assert listing.status == "open"


# "all" asks for every industry; any other id is sent as the industry filter
@pytest.mark.parametrize("industry, expected", [("all", None), ("healthcare", "healthcare")])
def test_industry_filter(industry, expected):
    scraper, session = make_scraper(page([job(1)]), industry=industry)

    scraper.fetch_jobs()

    url = session.get.call_args.args[0]
    params = session.get.call_args.kwargs["params"]
    assert url == JOBICY_JOBS_URL
    assert params["count"] == 100
    assert params.get("industry") == expected


# The next page is requested with the cursor from the previous one
def test_fetch_jobs_follows_the_cursor():
    scraper, session = make_scraper(page([job(1)], cursor="abc"), page([job(2)]))

    listings = scraper.fetch_jobs()

    assert [listing.source_job_id for listing in listings] == ["1", "2"]
    assert "cursor" not in session.get.call_args_list[0].kwargs["params"]
    assert session.get.call_args_list[1].kwargs["params"]["cursor"] == "abc"


# No more pages than max_pages are fetched, even if the board has more
def test_fetch_jobs_stops_at_the_page_cap():
    scraper, session = make_scraper(
        page([job(1)], cursor="a"), page([job(2)], cursor="b"), page([job(3)], cursor="c"), max_pages=2
    )

    listings = scraper.fetch_jobs()

    assert len(listings) == 2
    assert session.get.call_count == 2


# The feed is newest first, so the first job older than max_age_days ends the run
def test_fetch_jobs_stops_at_jobs_older_than_the_cutoff():
    scraper, session = make_scraper(
        page(
            [
                job(1, pub_date="2026-11-13T09:00:00+00:00"),
                job(2, pub_date="2026-11-01T09:00:00+00:00"),
                job(3, pub_date="2026-11-12T09:00:00+00:00"),
            ],
            cursor="more",
        ),
        max_age_days=7,
    )

    listings = scraper.fetch_jobs()

    assert [listing.source_job_id for listing in listings] == ["1"]
    assert session.get.call_count == 1


# hasMore false ends paging even when a cursor is present
def test_fetch_jobs_stops_when_has_more_is_false():
    scraper, session = make_scraper(page([job(1)], cursor="x", has_more=False))

    scraper.fetch_jobs()

    assert session.get.call_count == 1


# One malformed job is skipped without losing the rest
def test_malformed_job_is_skipped():
    scraper, _ = make_scraper(page([job(1, jobTitle=None, companyName=12), job(2)]))

    listings = scraper.fetch_jobs()

    assert [listing.source_job_id for listing in listings] == ["2"]


# A failed request is raised as ScraperRequestError so scrape_all can move on
def test_request_error_is_raised_as_scraper_request_error():
    session = Mock()
    session.get.side_effect = requests.ConnectionError("down")
    scraper = JobicyScraper(session=session, now=NOW)

    with pytest.raises(ScraperRequestError):
        scraper.fetch_jobs()


def test_format_salary():
    assert format_salary({"salaryMin": 20, "salaryMax": 25, "salaryCurrency": "USD", "salaryPeriod": "hourly"}) == (
        "USD 20-25 (per hour)"
    )
    assert format_salary({"salaryMin": 4000, "salaryMax": 5000, "salaryPeriod": "monthly"}) == "4,000-5,000 (per month)"
    assert format_salary({"salaryMin": None, "salaryMax": None}) is None


def test_parse_pub_date():
    assert parse_pub_date("2026-11-14T16:07:57+00:00") == datetime(2026, 11, 14, 16, 7, 57, tzinfo=timezone.utc)
    assert parse_pub_date("not a date") is None
    assert parse_pub_date(None) is None

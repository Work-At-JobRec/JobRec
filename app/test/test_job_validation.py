import logging
import os
import sys

# Lets this test import app/src/job_validation.py
SRC_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "src")
)
sys.path.insert(0, SRC_DIR)

from job_listing import JobListing  # noqa: E402
from job_validation import filter_valid_listings, validate_listing  # noqa: E402


def make_listing(**overrides) -> JobListing:
    """A fully valid listing; overrides replace individual fields."""
    fields = {
        "title": "Software Engineer",
        "company_name": "Acme",
        "source": "greenhouse",
        "application_url": "https://acme.com/jobs?gh_jid=123",
        "source_job_id": "123",
    }
    fields.update(overrides)
    return JobListing(**fields)


# A complete listing produces no problems
def test_valid_listing_has_no_problems():
    assert validate_listing(make_listing()) == []


# A listing with an empty title is reported
def test_blank_title_is_reported():
    problems = validate_listing(make_listing(title=""))

    assert len(problems) == 1
    assert "title" in problems[0]


# A title made only of whitespace counts as missing
def test_whitespace_only_title_is_reported():
    problems = validate_listing(make_listing(title="  \t\n"))

    assert len(problems) == 1
    assert "title" in problems[0]


# A listing with no company name is reported
def test_blank_company_name_is_reported():
    problems = validate_listing(make_listing(company_name=" "))

    assert len(problems) == 1
    assert "company_name" in problems[0]


# A listing with no application URL is reported
def test_blank_application_url_is_reported():
    problems = validate_listing(make_listing(application_url=""))

    assert len(problems) == 1
    assert "application_url" in problems[0]


# A listing that does not say which scraper produced it is reported
def test_blank_source_is_reported():
    problems = validate_listing(make_listing(source=""))

    assert len(problems) == 1
    assert "source" in problems[0]


# Only http and https links are usable application URLs
def test_non_http_url_is_reported():
    for url in ["ftp://acme.com/jobs", "mailto:jobs@acme.com", "acme.com/jobs"]:
        problems = validate_listing(make_listing(application_url=url))

        assert len(problems) == 1, url
        assert "application_url" in problems[0]


# A URL must name a host
def test_url_without_host_is_reported():
    for url in ["https:///jobs", "http://:80"]:
        problems = validate_listing(make_listing(application_url=url))

        assert len(problems) == 1, url
        assert "application_url" in problems[0]


# A URL containing whitespace is not usable
def test_url_with_internal_whitespace_is_reported():
    problems = validate_listing(make_listing(application_url="https://acme.com/jobs 123"))

    assert len(problems) == 1
    assert "application_url" in problems[0]


# A URL that cannot even be parsed is reported as a problem, never raised
def test_unparseable_url_is_reported_not_raised():
    problems = validate_listing(make_listing(application_url="http://[::1"))

    assert len(problems) == 1
    assert "application_url" in problems[0]


# Optional fields may all be missing
def test_missing_optional_fields_are_allowed():
    listing = make_listing(location=None, posted_at=None, source_job_id=None, description="")

    assert validate_listing(listing) == []


# Every problem is reported, not just the first one found
def test_multiple_problems_are_all_reported():
    problems = validate_listing(make_listing(title="", application_url=""))

    assert len(problems) == 2


# Filtering keeps the valid listings in their original order
def test_filter_keeps_valid_listings_in_order():
    first = make_listing(title="First")
    bad = make_listing(title="")
    second = make_listing(title="Second")

    assert filter_valid_listings([first, bad, second]) == [first, second]


# Each rejected listing is logged with enough detail to find it
def test_filter_logs_warning_for_each_rejected_listing(caplog):
    caplog.set_level(logging.WARNING, logger="job_validation")
    bad_one = make_listing(title="", source_job_id="111")
    bad_two = make_listing(company_name="", source_job_id="222")

    filter_valid_listings([bad_one, make_listing(), bad_two])

    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 2
    assert "greenhouse" in warnings[0] and "111" in warnings[0] and "title" in warnings[0]
    assert "222" in warnings[1] and "company_name" in warnings[1]


# Nothing is logged as a warning when every listing is valid
def test_filter_logs_no_warning_when_all_valid(caplog):
    caplog.set_level(logging.WARNING, logger="job_validation")

    filter_valid_listings([make_listing(), make_listing()])

    assert [r for r in caplog.records if r.levelno >= logging.WARNING] == []


# Any iterable is accepted, including generators and an empty list
def test_filter_accepts_generator_and_empty_input():
    generated = (listing for listing in [make_listing(), make_listing(title="")])

    assert len(filter_valid_listings(generated)) == 1
    assert filter_valid_listings([]) == []

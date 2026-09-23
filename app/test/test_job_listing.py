import os
import sys
from datetime import datetime, timezone, timedelta

import pytest
from pydantic import ValidationError

# Lets this test import app/src/job_listing.py
SRC_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "src")
)
sys.path.insert(0, SRC_DIR)

from job_listing import JobListing  # noqa: E402


def make_listing(**overrides):
    """Build a JobListing with every required field set; overrides replace fields."""
    fields = {
        "title": "Software Engineer",
        "company_name": "Acme",
        "source": "greenhouse",
        "application_url": "https://boards.greenhouse.io/acme/jobs/123",
    }
    fields.update(overrides)
    return JobListing(**fields)


# A listing built from only the required fields keeps those values as given
def test_required_fields_construct_listing():
    listing = make_listing()

    assert listing.title == "Software Engineer"
    assert listing.company_name == "Acme"
    assert listing.source == "greenhouse"
    assert listing.application_url == "https://boards.greenhouse.io/acme/jobs/123"


# Optional fields default to None (or empty string for the description)
def test_optional_fields_default_to_none_or_empty():
    listing = make_listing()

    assert listing.location is None
    assert listing.posted_at is None
    assert listing.source_job_id is None
    assert listing.description == ""


# The scrape timestamp is filled in automatically as a timezone-aware UTC "now"
def test_scraped_at_defaults_to_aware_utc_now():
    before = datetime.now(timezone.utc)
    listing = make_listing()
    after = datetime.now(timezone.utc)

    assert listing.scraped_at.tzinfo is not None
    assert before <= listing.scraped_at <= after


# A listing without a job title is rejected
def test_missing_title_raises_validation_error():
    with pytest.raises(ValidationError):
        JobListing(
            company_name="Acme",
            source="greenhouse",
            application_url="https://example.com/job",
        )


# A listing without an application URL is rejected
def test_missing_application_url_raises_validation_error():
    with pytest.raises(ValidationError):
        JobListing(
            title="Software Engineer",
            company_name="Acme",
            source="greenhouse",
        )


# Serialising to JSON and back yields an equal listing, including timezone-aware dates
def test_json_round_trip_preserves_values():
    listing = make_listing(
        location="Dublin",
        description="<p>Build things</p>",
        posted_at=datetime(2026, 9, 3, 13, 30, tzinfo=timezone(timedelta(hours=-4))),
        source_job_id="8172487",
    )

    restored = JobListing.model_validate_json(listing.model_dump_json())

    assert restored == listing

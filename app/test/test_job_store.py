import os
import sys
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

# Lets this test import app/src/job_store.py
SRC_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "src")
)
sys.path.insert(0, SRC_DIR)

from db import Base  # noqa: E402
from job_listing import JobListing  # noqa: E402
from job_store import (  # noqa: E402
    JobListingTable,
    UpsertResult,
    count_listings,
    list_listings,
    listing_key,
    upsert_listings,
)

T1 = datetime(2026, 9, 27, 10, 0, tzinfo=timezone.utc)
T2 = datetime(2026, 9, 28, 10, 0, tzinfo=timezone.utc)
T3 = datetime(2026, 9, 29, 10, 0, tzinfo=timezone.utc)


@pytest.fixture
def engine(tmp_path):
    """A fresh SQLite database with every table created, matching how the app creates its schema."""
    test_engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'jobs.db'}")
    Base.metadata.create_all(test_engine)
    return test_engine


def make_listing(**overrides) -> JobListing:
    fields = {
        "title": "Software Engineer",
        "company_name": "Acme",
        "location": "Dublin",
        "description": "Build things.",
        "source": "greenhouse",
        "application_url": "https://acme.com/jobs?gh_jid=123",
        "posted_at": datetime(2026, 9, 3, 13, 30, 34, tzinfo=timezone(timedelta(hours=-4))),
        "source_job_id": "123",
        "pay": "USD 100,000-120,000 (Base)",
        "status": "open",
    }
    fields.update(overrides)
    return JobListing(**fields)


def rows(engine) -> list[JobListingTable]:
    with Session(engine) as session:
        return list(session.scalars(select(JobListingTable).order_by(JobListingTable.id)))


# --- listing_key ---

# The source's own job id identifies a listing whenever it is present
def test_listing_key_uses_source_job_id_when_present():
    a = make_listing(source_job_id="123", application_url="https://acme.com/a")
    b = make_listing(source_job_id="123", application_url="https://acme.com/b")

    assert listing_key(a) == "greenhouse:id:123"
    assert listing_key(a) == listing_key(b)


# Without a job id the application URL identifies the listing, ignoring tracking noise
def test_listing_key_falls_back_to_url_when_no_source_id():
    a = make_listing(source_job_id=None, application_url="https://acme.com/jobs?gh_jid=5")
    b = make_listing(source_job_id=None, application_url="https://acme.com/jobs?gh_jid=5&utm_source=x#top")

    assert listing_key(a) == "greenhouse:url:https://acme.com/jobs?gh_jid=5"
    assert listing_key(a) == listing_key(b)


# With neither id nor URL the company, title, and location identify the listing, ignoring case and spacing
def test_listing_key_falls_back_to_fields_when_no_id_or_url():
    a = make_listing(source_job_id=None, application_url="", company_name="  Acme ", title="Engineer", location="NYC")
    b = make_listing(source_job_id=None, application_url="", company_name="acme", title="engineer", location="nyc")
    c = make_listing(source_job_id=None, application_url="", location=None)

    assert listing_key(a) == "greenhouse:fields:acme|engineer|nyc"
    assert listing_key(a) == listing_key(b)
    assert listing_key(c) == "greenhouse:fields:acme|software engineer|"


# The same job id on different sources is two different listings
def test_listing_key_includes_source():
    assert listing_key(make_listing(source="greenhouse")) != listing_key(make_listing(source="lever"))


# --- storing listings (TC-027) ---

# Every field of a listing is stored and reads back equal
def test_insert_stores_every_field_and_reads_back_equal(engine):
    listing = make_listing(description="Line one\n\n- bullet")

    result = upsert_listings(engine, [listing])

    assert result == UpsertResult(inserted=1, updated=0, unchanged=0)
    assert list_listings(engine) == [listing]


# Missing optional fields stay missing after a round trip
def test_none_location_pay_and_posted_at_round_trip(engine):
    upsert_listings(engine, [make_listing(location=None, posted_at=None, pay=None, description="")])

    stored = list_listings(engine)[0]

    assert stored.location is None
    assert stored.posted_at is None
    assert stored.pay is None
    assert stored.description == ""


# Timestamps come back timezone-aware in UTC, whatever offset they were stored with
def test_read_back_datetimes_are_utc_aware(engine):
    upsert_listings(engine, [make_listing()])

    stored = list_listings(engine)[0]

    assert stored.posted_at.utcoffset() == timedelta(0)
    assert stored.posted_at == datetime(2026, 9, 3, 17, 30, 34, tzinfo=timezone.utc)
    assert stored.scraped_at.tzinfo is not None


# Status is stored as given
def test_status_is_stored(engine):
    upsert_listings(engine, [make_listing(status="closed")])

    assert list_listings(engine)[0].status == "closed"


# --- duplicate handling (TC-028) ---

# Storing the same listing twice keeps one row and reports it as already known
def test_same_listing_twice_creates_one_row_and_is_reported_existing(engine):
    listing = make_listing()
    upsert_listings(engine, [listing])

    result = upsert_listings(engine, [listing])

    assert result == UpsertResult(inserted=0, updated=0, unchanged=1)
    assert result.existing == 1
    assert count_listings(engine) == 1


# A listing seen again with a changed field updates the existing row instead of adding one
def test_changed_title_updates_existing_row_instead_of_inserting(engine):
    upsert_listings(engine, [make_listing(title="Engineer")])
    original_id = rows(engine)[0].id

    result = upsert_listings(engine, [make_listing(title="Senior Engineer")])

    assert result == UpsertResult(inserted=0, updated=1, unchanged=0)
    assert count_listings(engine) == 1
    assert rows(engine)[0].id == original_id
    assert rows(engine)[0].title == "Senior Engineer"


# Listings without a job id are matched on their application URL
def test_same_url_without_source_id_is_deduplicated(engine):
    first = make_listing(source_job_id=None, title="First", application_url="https://acme.com/jobs/9")
    second = make_listing(source_job_id=None, title="Second", application_url="https://acme.com/jobs/9?utm_source=x")

    upsert_listings(engine, [first])
    result = upsert_listings(engine, [second])

    assert result.updated == 1
    assert count_listings(engine) == 1
    assert list_listings(engine)[0].title == "Second"


# The same job id from two different sources gives two rows
def test_same_source_job_id_from_different_sources_are_distinct(engine):
    upsert_listings(engine, [make_listing(source="greenhouse", source_job_id="1"), make_listing(source="lever", source_job_id="1")])

    assert count_listings(engine) == 2


# When both listings have job ids, the ids decide even if the URLs match
def test_different_source_job_ids_same_url_are_distinct(engine):
    url = "https://acme.com/jobs"
    upsert_listings(engine, [make_listing(source_job_id="1", application_url=url), make_listing(source_job_id="2", application_url=url)])

    assert count_listings(engine) == 2


# Two copies of one listing in the same batch are stored once, keeping the later copy
def test_intra_batch_duplicate_last_wins_and_counts_once(engine):
    result = upsert_listings(engine, [make_listing(title="Old"), make_listing(title="New")])

    assert result == UpsertResult(inserted=1, updated=0, unchanged=0)
    assert list_listings(engine)[0].title == "New"


# An empty batch stores nothing and reports nothing
def test_empty_batch_inserts_nothing(engine):
    assert upsert_listings(engine, []) == UpsertResult(inserted=0, updated=0, unchanged=0)
    assert count_listings(engine) == 0


# --- sighting timestamps ---

# The first time a listing was seen is kept; the last time is refreshed on every sighting
def test_first_seen_preserved_and_last_seen_refreshed_on_resight(engine):
    upsert_listings(engine, [make_listing()], now=T1)
    upsert_listings(engine, [make_listing()], now=T2)

    row = rows(engine)[0]

    assert row.first_seen_at.replace(tzinfo=timezone.utc) == T1
    assert row.last_seen_at.replace(tzinfo=timezone.utc) == T2


# The updated time only moves when a field actually changes
def test_updated_at_changes_only_when_a_field_changes(engine):
    upsert_listings(engine, [make_listing()], now=T1)
    upsert_listings(engine, [make_listing()], now=T2)
    assert rows(engine)[0].updated_at.replace(tzinfo=timezone.utc) == T1

    upsert_listings(engine, [make_listing(description="Changed")], now=T3)

    assert rows(engine)[0].updated_at.replace(tzinfo=timezone.utc) == T3


# --- read helpers ---

# Listings come back in the order they were first stored, and a limit is honoured
def test_list_listings_preserves_insert_order_and_honours_limit(engine):
    upsert_listings(engine, [make_listing(source_job_id=str(i), title=f"Job {i}") for i in (1, 2, 3)])

    assert [job.title for job in list_listings(engine)] == ["Job 1", "Job 2", "Job 3"]
    assert [job.title for job in list_listings(engine, limit=2)] == ["Job 1", "Job 2"]


# Counting reflects the rows stored
def test_count_listings_counts_rows(engine):
    assert count_listings(engine) == 0

    upsert_listings(engine, [make_listing(source_job_id=str(i)) for i in range(3)])

    assert count_listings(engine) == 3

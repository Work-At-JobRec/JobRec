import os
import sys
from datetime import datetime, timezone

import pytest

# Lets this test import files from app/src. It deliberately does not import app.py,
# so it runs without the auth and OpenAI settings the web app needs.
SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, SRC_DIR)

from jobrec.job_listing import JobListing  # noqa: E402
from jobrec.job_store import get_listing, list_recent_listings, upsert_listings  # noqa: E402
from jobrec.jobs import LIST_DESCRIPTION_CHARS, get_job, get_jobs, infer_job_type, to_api_job  # noqa: E402

API_FIELDS = {
    "id", "title", "company", "location", "description", "applicationUrl",
    "postedAgo", "jobType", "salary", "compatibility", "requirements",
}
SEEN = datetime(2026, 9, 10, tzinfo=timezone.utc)


def make_listing(**overrides) -> JobListing:
    fields = {
        "title": "Software Engineer",
        "company_name": "Acme",
        "location": "Dublin",
        "description": "Build things.",
        "source": "greenhouse",
        "application_url": "https://acme.com/jobs?gh_jid=123",
        "posted_at": datetime(2026, 9, 3, tzinfo=timezone.utc),
        "source_job_id": "123",
    }
    fields.update(overrides)
    return JobListing(**fields)


# --- which listings are served ---

# With nothing stored, the placeholder listings are served so a fresh checkout still shows something
def test_empty_store_serves_the_sample_listings(engine):
    jobs = get_jobs(engine)

    assert len(jobs) > 0
    assert all(job["id"].startswith("sample-") for job in jobs)


# Without a database at all, the placeholders are served
def test_no_engine_serves_the_sample_listings():
    assert all(job["id"].startswith("sample-") for job in get_jobs())


# Once the scraper has stored listings, those are served and the placeholders are gone
def test_stored_listings_replace_the_samples(engine):
    upsert_listings(engine, [make_listing(source_job_id="1", title="Engineer"), make_listing(source_job_id="2", title="Designer")])

    jobs = get_jobs(engine)

    assert sorted(job["title"] for job in jobs) == ["Designer", "Engineer"]
    assert not any(job["id"].startswith("sample-") for job in jobs)


# Each job has exactly the fields the frontend renders
def test_stored_jobs_have_exactly_the_frontend_fields(engine):
    upsert_listings(engine, [make_listing()])

    assert set(get_jobs(engine)[0]) == API_FIELDS


# The most recently posted jobs come first; a job with no posting date is placed by when it was first seen
def test_newest_postings_come_first(engine):
    upsert_listings(engine, [
        make_listing(source_job_id="old", title="Old", posted_at=datetime(2026, 9, 1, tzinfo=timezone.utc)),
        make_listing(source_job_id="undated", title="Undated", posted_at=None),
        make_listing(source_job_id="new", title="New", posted_at=datetime(2026, 9, 20, tzinfo=timezone.utc)),
    ], now=SEEN)

    assert [job["title"] for job in get_jobs(engine)] == ["New", "Undated", "Old"]


# The list is limited, and a nonsensical limit is clamped instead of failing
def test_limit_is_respected_and_clamped(engine):
    upsert_listings(engine, [make_listing(source_job_id=str(i)) for i in range(5)])

    assert len(get_jobs(engine, limit=2)) == 2
    assert len(get_jobs(engine, limit=0)) == 1
    assert len(get_jobs(engine, limit=10 ** 9)) == 5


# A listing with no source job id has no stable id for a detail page, so it is not listed
def test_listings_without_a_source_job_id_are_not_listed(engine):
    upsert_listings(engine, [make_listing(source_job_id=None), make_listing(source_job_id="7", title="Listed")])

    assert [job["title"] for job in get_jobs(engine)] == ["Listed"]


# An id containing characters that would break the /jobs/<id> page route is skipped
def test_ids_unsafe_for_routing_are_skipped(engine):
    upsert_listings(engine, [make_listing(source_job_id="a/b"), make_listing(source_job_id="c?d"),
                             make_listing(source_job_id="ok", title="Safe")])

    assert [job["title"] for job in get_jobs(engine)] == ["Safe"]


# --- description size ---

# The list carries a short description; the detail page gets the full text
def test_list_description_is_a_snippet_and_detail_is_full(engine):
    full = "Paragraph one.\n\n" + ("word " * 800)
    upsert_listings(engine, [make_listing(description=full)])

    listed = get_jobs(engine)[0]
    detail = get_job(listed["id"], engine)

    assert len(listed["description"]) <= LIST_DESCRIPTION_CHARS + 1
    assert listed["description"].startswith("Paragraph one.")
    assert listed["description"].endswith("…")
    assert detail["description"] == full.strip() or detail["description"] == full


# A description that already fits is not marked as cut off
def test_short_description_is_not_marked_as_truncated(engine):
    upsert_listings(engine, [make_listing(description="Build things.")])

    assert get_jobs(engine)[0]["description"] == "Build things."


# --- field mapping ---

# The scraped pay is shown as the salary; only the first range, so the card stays readable
def test_first_pay_range_is_the_salary(engine):
    upsert_listings(engine, [make_listing(pay="USD 100,000-120,000 (Base); USD 10,000-20,000 (Bonus)")])

    assert get_jobs(engine)[0]["salary"] == "USD 100,000-120,000 (Base)"


# A listing without pay has no salary
def test_missing_pay_means_no_salary(engine):
    upsert_listings(engine, [make_listing(pay=None)])

    assert get_jobs(engine)[0]["salary"] is None


# Compatibility and requirement matches stay empty until the matching algorithm supplies them
def test_real_listings_have_no_placeholder_matches(engine):
    upsert_listings(engine, [make_listing()])
    job = get_jobs(engine)[0]

    assert job["compatibility"] is None
    assert job["requirements"] == []


# The job type shown on the card is inferred from the title, matching the frontend's filter values
@pytest.mark.parametrize("title, expected", [
    ("Software Engineering Intern", "Internship"),
    ("Summer Internship, Data Science", "Internship"),
    ("Co-op, Hardware Design", "Internship"),
    ("Internal Tools Engineer", "Full Time"),
    ("International Sales Lead", "Full Time"),
    ("Part-Time Support Specialist", "Part Time"),
    ("Recruiter (Part Time)", "Part Time"),
    ("Contract Recruiter", "Contract"),
    ("Independent Contractor, Design", "Contract"),
    ("Software Engineer", "Full Time"),
])
def test_job_type_is_inferred_from_the_title(title, expected):
    assert infer_job_type(title) == expected


# to_api_job works on a listing directly, as the existing callers use it
def test_to_api_job_includes_inferred_type_and_pay():
    job = to_api_job(make_listing(title="Data Science Intern", pay="USD 40-50 (per hour)"))

    assert job["id"] == "greenhouse-123"
    assert job["jobType"] == "Internship"
    assert job["salary"] == "USD 40-50 (per hour)"


# --- detail lookup ---

# The detail lookup works for the id shapes each source produces
@pytest.mark.parametrize("source, source_job_id", [
    ("greenhouse", "4012345"),
    ("lever", "6ed76ce8-4156-4b60-b120-403538bd66cd"),
    ("workday", "JR2026267"),
])
def test_detail_lookup_works_for_each_source_id_shape(engine, source, source_job_id):
    upsert_listings(engine, [
        make_listing(source=source, source_job_id=source_job_id, title=f"{source} job"),
        make_listing(source=source, source_job_id="other", title="Another job"),
    ])

    job = get_job(f"{source}-{source_job_id}", engine)

    assert job["title"] == f"{source} job"
    assert job["id"] == f"{source}-{source_job_id}"


# An id that matches nothing gives None, which the route turns into a 404
def test_unknown_or_malformed_id_returns_none(engine):
    upsert_listings(engine, [make_listing()])

    assert get_job("greenhouse-999", engine) is None
    assert get_job("nodash", engine) is None
    assert get_job("", engine) is None


# The sample listings are still reachable by id while the store is empty
def test_sample_detail_is_served_when_the_store_is_empty(engine):
    assert get_job("sample-1", engine)["title"] == "Software Engineer"


# --- store helpers ---

# A stored listing is fetched by its source and source job id
def test_get_listing_by_source_and_id(engine):
    upsert_listings(engine, [make_listing(source_job_id="1", title="One"), make_listing(source_job_id="2", title="Two")])

    assert get_listing(engine, "greenhouse", "2").title == "Two"
    assert get_listing(engine, "greenhouse", "missing") is None
    assert get_listing(engine, "lever", "2") is None


# A source job id too long for the key column is shortened the same way when stored and when looked up
def test_get_listing_with_very_long_source_job_id(engine):
    long_id = "x" * 2000
    upsert_listings(engine, [make_listing(source_job_id=long_id, title="Long")])

    assert get_listing(engine, "greenhouse", long_id).title == "Long"
    assert get_listing(engine, "greenhouse", long_id[:-1] + "y") is None


# The recent-listings query cuts the description in the database, not after loading it
def test_list_recent_listings_can_cut_the_description(engine):
    upsert_listings(engine, [make_listing(description="x" * 1000)])

    assert len(list_recent_listings(engine, limit=10, description_chars=50)[0].description) == 50
    assert len(list_recent_listings(engine, limit=10)[0].description) == 1000

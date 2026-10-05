import os
import sys
from datetime import datetime, timedelta, timezone

# Lets this test import files from app/src
SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, SRC_DIR)

# These MUST come after sys.path.insert(...)
from jobrec.app import app  # noqa: E402
from jobrec.job_listing import JobListing  # noqa: E402
from jobrec.jobs import posted_ago, to_api_job  # noqa: E402

API_FIELDS = {
    "id",
    "title",
    "company",
    "location",
    "description",
    "applicationUrl",
    "postedAgo",
    "jobType",
    "salary",
    "compatibility",
    "requirements",
}


def test_jobs_api_lists_jobs_with_frontend_fields():
    response = app.test_client().get("/api/jobs")

    assert response.status_code == 200
    jobs = response.get_json()
    assert len(jobs) > 0
    for job in jobs:
        assert set(job) == API_FIELDS


def test_job_detail_api_returns_matching_job():
    client = app.test_client()
    first_id = client.get("/api/jobs").get_json()[0]["id"]

    response = client.get(f"/api/jobs/{first_id}")

    assert response.status_code == 200
    assert response.get_json()["id"] == first_id


def test_job_detail_api_unknown_id_is_404():
    response = app.test_client().get("/api/jobs/does-not-exist")

    assert response.status_code == 404
    assert response.get_json() == {"error": "Job not found"}


def test_to_api_job_maps_listing_fields_and_defaults_missing_matches():
    listing = JobListing(
        title="Backend Engineer",
        company_name="Globex",
        source="greenhouse",
        application_url="https://example.com/apply",
        source_job_id="42",
    )

    job = to_api_job(listing)

    assert job["id"] == "greenhouse-42"
    assert job["title"] == "Backend Engineer"
    assert job["company"] == "Globex"
    assert job["applicationUrl"] == "https://example.com/apply"
    assert job["location"] is None
    assert job["postedAgo"] is None
    # No placeholder match data exists for this job yet
    assert job["compatibility"] is None
    assert job["requirements"] == []


def test_posted_ago():
    now = datetime.now(timezone.utc)
    assert posted_ago(None) is None
    assert posted_ago(now) == "Today"
    assert posted_ago(now - timedelta(days=1, hours=1)) == "1 Day Ago"
    assert posted_ago(now - timedelta(days=4, hours=1)) == "4 Days Ago"

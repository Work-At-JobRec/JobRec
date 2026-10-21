import os
import sys
from datetime import datetime, timedelta, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
import pytest

# Lets this test import files from app/src
SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, SRC_DIR)

# These MUST come after sys.path.insert(...)
import jobrec.app as app_module  # noqa: E402
from jobrec.app import app  # noqa: E402
from jobrec.db import Base  # noqa: E402
from jobrec.job_listing import JobListing  # noqa: E402
from jobrec.job_store import listing_key, upsert_listings  # noqa: E402
from jobrec.jobs import posted_ago, to_api_job  # noqa: E402
from jobrec.openaiapi import SkillRanking, UserInfoTable  # noqa: E402
from jobrec.skill_detection import (
    DiscoveredSkill,
    persist_discovered_skills,
    store_listing_skills,
)  # noqa: E402

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


@pytest.fixture
def jobs_client(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'matching.db'}")
    Base.metadata.create_all(engine)
    fixtures = [
        JobListing(
            title=f"Role {index}",
            company_name="Acme",
            location="West Lafayette, IN" if index < 6 else "Chicago, IL",
            description="Build software",
            source="test",
            application_url=f"https://example.com/{index}",
            source_job_id=str(index),
            pay=pay,
            status=status,
        )
        for index, pay, status in [
            (1, "USD 100,000-120,000 (Annual Base Salary Range)", "open"),
            (2, "USD 200,000 per year", "open"),
            (3, None, "open"),
            (4, "USD 100,000 per year", "open"),
            (5, "USD 50,000 per year", "open"),
            (6, "USD 100,000 per year", "open"),
            (7, "USD 250,000 per year", "closed"),
        ]
    ]
    upsert_listings(engine, fixtures)
    persist_discovered_skills(
        engine,
        [
            DiscoveredSkill(skill_name="Python", proficiency_level=4),
            DiscoveredSkill(skill_name="SQL", proficiency_level=4),
        ],
    )
    store_listing_skills(
        engine,
        {
            listing_key(fixtures[0]): [
                SkillRanking(skill_name="Python", proficiency_level=4)
            ],
            listing_key(fixtures[1]): [
                SkillRanking(skill_name="Python", proficiency_level=4)
            ],
            listing_key(fixtures[2]): [
                SkillRanking(skill_name="Python", proficiency_level=4)
            ],
            listing_key(fixtures[3]): [
                SkillRanking(skill_name="SQL", proficiency_level=4)
            ],
            listing_key(fixtures[4]): [
                SkillRanking(skill_name="Python", proficiency_level=4)
            ],
            listing_key(fixtures[5]): [],
            listing_key(fixtures[6]): [
                SkillRanking(skill_name="Python", proficiency_level=4)
            ],
        },
    )
    with Session(engine) as session:
        session.add(
            UserInfoTable(
                user_id="test|matching-user",
                info={"skills": [{"skill_name": "python", "proficiency_level": 4}]},
                done_processing=True,
            )
        )
        session.commit()

    async def verify_token(token):
        return {"sub": "test|matching-user"}

    monkeypatch.setattr(app_module, "engine", engine)
    monkeypatch.setattr("jobrec.auth.api_client.verify_access_token", verify_token)
    return app.test_client(), {"Authorization": "Bearer test-token"}


def test_jobs_api_returns_top_five_ranked_jobs_with_frontend_fields(jobs_client):
    client, headers = jobs_client
    response = client.get("/api/jobs?desired_salary=100000", headers=headers)

    assert response.status_code == 200
    jobs = response.get_json()
    assert len(jobs) == 5
    assert [job["id"] for job in jobs] == [
        "test-2",
        "test-1",
        "test-5",
        "test-3",
        "test-4",
    ]
    assert jobs[0]["compatibility"] == 100
    assert jobs[3]["salary"] is None
    assert jobs[4]["compatibility"] == 0
    for job in jobs:
        assert set(job) == API_FIELDS


def test_jobs_api_filters_location_without_changing_score(jobs_client):
    client, headers = jobs_client
    response = client.get("/api/jobs?location=Chicago", headers=headers)

    assert response.status_code == 200
    assert [job["id"] for job in response.get_json()] == ["test-6"]


def test_job_detail_api_returns_matching_job(jobs_client):
    client, headers = jobs_client
    first_id = client.get("/api/jobs", headers=headers).get_json()[0]["id"]

    response = client.get(f"/api/jobs/{first_id}", headers=headers)

    assert response.status_code == 200
    assert response.get_json()["id"] == first_id


def test_job_detail_api_unknown_id_is_404(jobs_client):
    client, headers = jobs_client
    response = client.get("/api/jobs/does-not-exist", headers=headers)

    assert response.status_code == 404
    assert response.get_json() == {"error": "Job not found"}


def test_jobs_api_requires_authentication():
    response = app.test_client().get("/api/jobs")

    assert response.status_code == 401


def test_jobs_api_rejects_invalid_desired_salary(jobs_client):
    client, headers = jobs_client
    response = client.get("/api/jobs?desired_salary=0", headers=headers)

    assert response.status_code == 400


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

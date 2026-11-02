"""Integration test: removing a skill updates the profile and job compatibility.

Exercises DELETE /api/profile/skills together with GET /api/profile and
GET /api/jobs against one shared database, so it verifies that a removed
skill is persisted and that the job matching code sees the change.
"""

import os
import sys

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

# Lets this test import files from app/src
SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, SRC_DIR)

# These MUST come after sys.path.insert(...)
import jobrec.app as app_module  # noqa: E402
from jobrec.app import app  # noqa: E402
from jobrec.db import Base  # noqa: E402
from jobrec.job_listing import JobListing  # noqa: E402
from jobrec.job_store import listing_key, upsert_listings  # noqa: E402
from jobrec.openaiapi import SkillRanking, UserInfoTable  # noqa: E402
from jobrec.skill_detection import (  # noqa: E402
    DiscoveredSkill,
    persist_discovered_skills,
    store_listing_skills,
)

TEST_USER = "test|integration-user"
HEADERS = {"Authorization": "Bearer test-token"}


def test_removed_skill_disappears_from_profile_and_lowers_job_match(
    tmp_path, monkeypatch
):
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'integration.db'}")
    Base.metadata.create_all(engine)

    listing = JobListing(
        title="Python Developer",
        company_name="Acme",
        location="West Lafayette, IN",
        description="Build backend services in Python",
        source="test",
        application_url="https://example.com/python-dev",
        source_job_id="python-dev",
        pay="USD 100,000 per year",
        status="open",
    )
    upsert_listings(engine, [listing])
    persist_discovered_skills(
        engine, [DiscoveredSkill(skill_name="Python", proficiency_level=4)]
    )
    store_listing_skills(
        engine,
        {listing_key(listing): [SkillRanking(skill_name="Python", proficiency_level=4)]},
    )
    with Session(engine) as session:
        session.add(
            UserInfoTable(
                user_id=TEST_USER,
                info={
                    "name": "Test User",
                    "email": None,
                    "phone": None,
                    "location": None,
                    "skills": [{"skill_name": "Python", "proficiency_level": 4}],
                    "education": [],
                    "projects": [],
                    "socials": [],
                    "employment_history": [],
                },
                done_processing=True,
            )
        )
        session.commit()

    async def verify_token(token):
        return {"sub": TEST_USER}

    monkeypatch.setattr(app_module, "engine", engine)
    monkeypatch.setattr("jobrec.auth.api_client.verify_access_token", verify_token)
    client = app.test_client()

    # Before: the user has Python, so the Python job is a full match.
    before = client.get("/api/jobs", headers=HEADERS).get_json()
    assert before[0]["compatibility"] == 100

    # Remove the skill through the profile endpoint.
    delete_response = client.delete(
        "/api/profile/skills", json={"skill_name": "python"}, headers=HEADERS
    )
    assert delete_response.status_code == 200

    # After: the profile no longer lists it...
    profile = client.get("/api/profile", headers=HEADERS).get_json()
    assert profile["status"] == "done"
    assert profile["user_info"]["skills"] == []

    # ...and job matching no longer counts it.
    after = client.get("/api/jobs", headers=HEADERS).get_json()
    assert after[0]["compatibility"] == 0


def test_removing_one_of_two_skills_gives_partial_match_and_spares_other_jobs(
    tmp_path, monkeypatch
):
    """A user with Python and SQL removes Python.

    The job needing both skills drops from 100% to 50% and marks Python as unmet,
    while the job needing only SQL stays at 100%.
    """
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'integration.db'}")
    Base.metadata.create_all(engine)

    backend_job = JobListing(
        title="Backend Developer",
        company_name="Acme",
        location="West Lafayette, IN",
        description="Python services backed by SQL",
        source="test",
        application_url="https://example.com/backend-dev",
        source_job_id="backend-dev",
        pay="USD 100,000 per year",
        status="open",
    )
    database_job = JobListing(
        title="Database Analyst",
        company_name="Acme",
        location="West Lafayette, IN",
        description="Write SQL reports",
        source="test",
        application_url="https://example.com/db-analyst",
        source_job_id="db-analyst",
        pay="USD 100,000 per year",
        status="open",
    )
    upsert_listings(engine, [backend_job, database_job])
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
            listing_key(backend_job): [
                SkillRanking(skill_name="Python", proficiency_level=4),
                SkillRanking(skill_name="SQL", proficiency_level=4),
            ],
            listing_key(database_job): [
                SkillRanking(skill_name="SQL", proficiency_level=4),
            ],
        },
    )
    with Session(engine) as session:
        session.add(
            UserInfoTable(
                user_id=TEST_USER,
                info={
                    "name": "Test User",
                    "email": None,
                    "phone": None,
                    "location": None,
                    "skills": [
                        {"skill_name": "Python", "proficiency_level": 4},
                        {"skill_name": "SQL", "proficiency_level": 4},
                    ],
                    "education": [],
                    "projects": [],
                    "socials": [],
                    "employment_history": [],
                },
                done_processing=True,
            )
        )
        session.commit()

    async def verify_token(token):
        return {"sub": TEST_USER}

    monkeypatch.setattr(app_module, "engine", engine)
    monkeypatch.setattr("jobrec.auth.api_client.verify_access_token", verify_token)
    client = app.test_client()

    def jobs_by_title():
        jobs = client.get("/api/jobs", headers=HEADERS).get_json()
        return {job["title"]: job for job in jobs}

    # Before: the user has both skills, so both jobs are full matches.
    before = jobs_by_title()
    assert before["Backend Developer"]["compatibility"] == 100
    assert before["Database Analyst"]["compatibility"] == 100

    delete_response = client.delete(
        "/api/profile/skills", json={"skill_name": "Python"}, headers=HEADERS
    )
    assert delete_response.status_code == 200

    # The profile keeps SQL and drops Python.
    profile = client.get("/api/profile", headers=HEADERS).get_json()
    assert [s["skill_name"] for s in profile["user_info"]["skills"]] == ["SQL"]

    # After: the two-skill job is a half match with Python marked as unmet...
    after = jobs_by_title()
    backend = after["Backend Developer"]
    assert backend["compatibility"] == 50
    met = {req["skill"]: req["met"] for req in backend["requirements"]}
    assert met == {"Python": False, "SQL": True}

    # ...and the SQL-only job is unaffected.
    assert after["Database Analyst"]["compatibility"] == 100

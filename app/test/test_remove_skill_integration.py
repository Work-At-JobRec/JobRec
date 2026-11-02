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

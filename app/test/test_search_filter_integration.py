"""Integration test: the Search tab's filters work on real /api/jobs output.

The backend serves GET /api/jobs (Python) and the Search tab filters that list in
the browser with filterJobs() (frontend/src/utils/filterJobs.js). This test fetches
jobs from the real Flask endpoint, passes the JSON to filterJobs() in Node, and
checks the results. It fails if the backend renames a field the frontend filters on
(title, company, location, salary, jobType, requirements[].skill).
"""

import json
import os
import shutil
import subprocess
import sys

import pytest
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

FILTER_JOBS_JS = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "src", "utils", "filterJobs.js")
)
TEST_USER = "test|search-user"
HEADERS = {"Authorization": "Bearer test-token"}

# Reads {"jobs": [...], "filters": {...}} on stdin and prints the matching titles.
NODE_SCRIPT = """
const { EMPTY_FILTERS, filterJobs } = await import(process.argv[1]);
let input = "";
for await (const chunk of process.stdin) input += chunk;
const { jobs, filters } = JSON.parse(input);
const result = filterJobs(jobs, { ...EMPTY_FILTERS, ...filters });
console.log(JSON.stringify(result.map((job) => job.title)));
"""


def run_filter(jobs, filters):
    completed = subprocess.run(
        ["node", "--input-type=module", "-e", NODE_SCRIPT, "file://" + FILTER_JOBS_JS],
        input=json.dumps({"jobs": jobs, "filters": filters}),
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(completed.stdout)


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is needed to run filterJobs.js")
def test_search_filters_work_on_jobs_from_the_api(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'search.db'}")
    Base.metadata.create_all(engine)

    backend = JobListing(
        title="Backend Engineer",
        company_name="Acme",
        location="West Lafayette, IN",
        description="Build APIs in Python",
        source="test",
        application_url="https://example.com/backend",
        source_job_id="backend",
        pay="USD 120,000 per year",
        status="open",
    )
    intern = JobListing(
        title="Software Engineering Intern",
        company_name="Globex",
        location="Chicago, IL",
        description="Build React components",
        source="test",
        application_url="https://example.com/intern",
        source_job_id="intern",
        pay="USD 30 per hour",
        status="open",
    )
    upsert_listings(engine, [backend, intern])
    persist_discovered_skills(
        engine,
        [
            DiscoveredSkill(skill_name="Python", proficiency_level=3),
            DiscoveredSkill(skill_name="React", proficiency_level=3),
        ],
    )
    store_listing_skills(
        engine,
        {
            listing_key(backend): [SkillRanking(skill_name="Python", proficiency_level=3)],
            listing_key(intern): [SkillRanking(skill_name="React", proficiency_level=3)],
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
                    "skills": [],
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

    response = client.get("/api/jobs", headers=HEADERS)
    assert response.status_code == 200
    jobs = response.get_json()
    assert sorted(job["title"] for job in jobs) == ["Backend Engineer", "Software Engineering Intern"]

    # No filters: the Search tab shows every job.
    assert sorted(run_filter(jobs, {})) == ["Backend Engineer", "Software Engineering Intern"]
    # Keyword search reaches the skills the backend attached to each job.
    assert run_filter(jobs, {"keywords": "react"}) == ["Software Engineering Intern"]
    # Location matches the backend's "City, ST" format on the city.
    assert run_filter(jobs, {"location": "West Lafayette, IN"}) == ["Backend Engineer"]
    # Salary reads the backend's pay text: $30/hr is $62,400/yr, under the $100,000 minimum.
    assert run_filter(jobs, {"salaryMin": "100000"}) == ["Backend Engineer"]
    # Position type uses the jobType the backend infers from the title.
    assert run_filter(jobs, {"positionTypes": ["Internship"]}) == ["Software Engineering Intern"]
    # Company filter, and the "no jobs found" case.
    assert run_filter(jobs, {"companyName": "acme"}) == ["Backend Engineer"]
    assert run_filter(jobs, {"companyName": "Nonexistent Co"}) == []

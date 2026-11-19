"""Bookmarking jobs through /api/bookmarks."""

import os
import sys

import pytest

# Lets this test import files from app/src
SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, SRC_DIR)

# These MUST come after sys.path.insert(...)
import jobrec.app as app_module  # noqa: E402
import jobrec.bookmarks  # noqa: E402,F401  (registers the bookmarks table with Base)
import jobrec.openaiapi  # noqa: E402,F401  (registers the user_info table with Base)
from jobrec.app import app  # noqa: E402
from jobrec.db import Base  # noqa: E402
from jobrec.job_listing import JobListing  # noqa: E402
from jobrec.job_store import upsert_listings  # noqa: E402

HEADERS = {"Authorization": "Bearer test-token"}


def listing(source_job_id, title, status="open"):
    return JobListing(
        title=title,
        company_name="Acme",
        location="West Lafayette, IN",
        description=f"{title} at Acme",
        source="test",
        application_url=f"https://example.com/{source_job_id}",
        source_job_id=source_job_id,
        status=status,
    )


@pytest.fixture
def client(engine, monkeypatch):
    Base.metadata.create_all(engine)
    upsert_listings(engine, [listing("swe", "Software Engineer"), listing("ds", "Data Scientist")])

    # The token names the user, so tests can act as more than one.
    async def verify_token(token):
        return {"sub": f"test|{token}"}

    monkeypatch.setattr(app_module, "engine", engine)
    monkeypatch.setattr("jobrec.auth.api_client.verify_access_token", verify_token)
    return app.test_client()


def titles(response):
    assert response.status_code == 200
    return [job["title"] for job in response.get_json()]


def test_no_bookmarks_to_start(client):
    assert titles(client.get("/api/bookmarks", headers=HEADERS)) == []
    assert client.get("/api/bookmarks/test-swe", headers=HEADERS).get_json() == {"bookmarked": False}


def test_bookmarking_a_job_lists_it(client):
    response = client.put("/api/bookmarks/test-swe", headers=HEADERS)

    assert response.status_code == 200
    assert response.get_json() == {"bookmarked": True}
    assert client.get("/api/bookmarks/test-swe", headers=HEADERS).get_json() == {"bookmarked": True}
    assert titles(client.get("/api/bookmarks", headers=HEADERS)) == ["Software Engineer"]


def test_bookmarked_jobs_have_the_same_shape_as_the_job_list(client):
    client.put("/api/bookmarks/test-swe", headers=HEADERS)

    bookmarked = client.get("/api/bookmarks", headers=HEADERS).get_json()[0]
    listed = next(job for job in client.get("/api/jobs", headers=HEADERS).get_json() if job["id"] == "test-swe")
    assert bookmarked == listed


def test_most_recent_bookmark_comes_first(client):
    client.put("/api/bookmarks/test-swe", headers=HEADERS)
    client.put("/api/bookmarks/test-ds", headers=HEADERS)

    assert titles(client.get("/api/bookmarks", headers=HEADERS)) == ["Data Scientist", "Software Engineer"]


def test_bookmarking_twice_keeps_one_bookmark(client):
    client.put("/api/bookmarks/test-swe", headers=HEADERS)
    client.put("/api/bookmarks/test-swe", headers=HEADERS)

    assert titles(client.get("/api/bookmarks", headers=HEADERS)) == ["Software Engineer"]


def test_removing_a_bookmark(client):
    client.put("/api/bookmarks/test-swe", headers=HEADERS)

    response = client.delete("/api/bookmarks/test-swe", headers=HEADERS)

    assert response.get_json() == {"bookmarked": False}
    assert titles(client.get("/api/bookmarks", headers=HEADERS)) == []
    # Removing one that isn't there is not an error.
    assert client.delete("/api/bookmarks/test-swe", headers=HEADERS).status_code == 200


def test_unknown_job_cannot_be_bookmarked(client):
    response = client.put("/api/bookmarks/test-nope", headers=HEADERS)

    assert response.status_code == 404
    assert titles(client.get("/api/bookmarks", headers=HEADERS)) == []


def test_bookmarks_belong_to_one_user(client):
    client.put("/api/bookmarks/test-swe", headers={"Authorization": "Bearer alice"})

    assert titles(client.get("/api/bookmarks", headers={"Authorization": "Bearer alice"})) == ["Software Engineer"]
    assert titles(client.get("/api/bookmarks", headers={"Authorization": "Bearer bob"})) == []


def test_closed_jobs_drop_out_of_bookmarks(client, engine):
    client.put("/api/bookmarks/test-swe", headers=HEADERS)

    upsert_listings(engine, [listing("swe", "Software Engineer", status="closed")])

    assert titles(client.get("/api/bookmarks", headers=HEADERS)) == []


def test_bookmarks_require_sign_in(client):
    assert client.get("/api/bookmarks").status_code == 401
    assert client.put("/api/bookmarks/test-swe").status_code == 401

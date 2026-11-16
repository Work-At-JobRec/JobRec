"""Saving jobs to the user's lists through /api/bookmarks and /api/applied."""

import os
import sys

import pytest

# Lets this test import files from app/src
SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, SRC_DIR)

# These MUST come after sys.path.insert(...)
import jobrec.app as app_module  # noqa: E402
import jobrec.openaiapi  # noqa: E402,F401  (registers the user_info table with Base)
import jobrec.saved_jobs  # noqa: E402,F401  (registers the saved_jobs table with Base)
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


# Every behaviour below holds for each list.
@pytest.fixture(params=["bookmarks", "applied"])
def url(request):
    return f"/api/{request.param}"


def titles(response):
    assert response.status_code == 200
    return [job["title"] for job in response.get_json()]


def test_list_is_empty_to_start(client, url):
    assert titles(client.get(url, headers=HEADERS)) == []
    assert client.get(f"{url}/test-swe", headers=HEADERS).get_json() == {"saved": False}


def test_saving_a_job_lists_it(client, url):
    response = client.put(f"{url}/test-swe", headers=HEADERS)

    assert response.status_code == 200
    assert response.get_json() == {"saved": True}
    assert client.get(f"{url}/test-swe", headers=HEADERS).get_json() == {"saved": True}
    assert titles(client.get(url, headers=HEADERS)) == ["Software Engineer"]


def test_saved_jobs_have_the_same_shape_as_the_job_list(client, url):
    client.put(f"{url}/test-swe", headers=HEADERS)

    saved = client.get(url, headers=HEADERS).get_json()[0]
    listed = next(job for job in client.get("/api/jobs", headers=HEADERS).get_json() if job["id"] == "test-swe")
    assert saved == listed


def test_most_recently_saved_comes_first(client, url):
    client.put(f"{url}/test-swe", headers=HEADERS)
    client.put(f"{url}/test-ds", headers=HEADERS)

    assert titles(client.get(url, headers=HEADERS)) == ["Data Scientist", "Software Engineer"]


def test_saving_twice_keeps_one_entry(client, url):
    client.put(f"{url}/test-swe", headers=HEADERS)
    client.put(f"{url}/test-swe", headers=HEADERS)

    assert titles(client.get(url, headers=HEADERS)) == ["Software Engineer"]


def test_removing_a_saved_job(client, url):
    client.put(f"{url}/test-swe", headers=HEADERS)

    response = client.delete(f"{url}/test-swe", headers=HEADERS)

    assert response.get_json() == {"saved": False}
    assert titles(client.get(url, headers=HEADERS)) == []
    # Removing one that isn't there is not an error.
    assert client.delete(f"{url}/test-swe", headers=HEADERS).status_code == 200


def test_unknown_job_cannot_be_saved(client, url):
    response = client.put(f"{url}/test-nope", headers=HEADERS)

    assert response.status_code == 404
    assert titles(client.get(url, headers=HEADERS)) == []


def test_lists_belong_to_one_user(client, url):
    client.put(f"{url}/test-swe", headers={"Authorization": "Bearer alice"})

    assert titles(client.get(url, headers={"Authorization": "Bearer alice"})) == ["Software Engineer"]
    assert titles(client.get(url, headers={"Authorization": "Bearer bob"})) == []


def test_closed_jobs_drop_out_of_the_list(client, engine, url):
    client.put(f"{url}/test-swe", headers=HEADERS)

    upsert_listings(engine, [listing("swe", "Software Engineer", status="closed")])

    assert titles(client.get(url, headers=HEADERS)) == []


def test_lists_require_sign_in(client, url):
    assert client.get(url).status_code == 401
    assert client.put(f"{url}/test-swe").status_code == 401


def test_bookmarks_and_applied_jobs_are_separate(client):
    client.put("/api/bookmarks/test-swe", headers=HEADERS)
    client.put("/api/applied/test-ds", headers=HEADERS)

    assert titles(client.get("/api/bookmarks", headers=HEADERS)) == ["Software Engineer"]
    assert titles(client.get("/api/applied", headers=HEADERS)) == ["Data Scientist"]


def test_other_list_names_are_not_found(client):
    assert client.get("/api/favorites", headers=HEADERS).status_code == 404

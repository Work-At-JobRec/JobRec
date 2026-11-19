"""Unit tests for DELETE /api/profile/skills (remove_skill in jobrec/app.py).

Each test runs against a fresh SQLite database and a mocked Auth0 token,
so no real user data or network access is needed.
"""

import os
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
from jobrec.openaiapi import Base, UserInfoTable  # noqa: E402

TEST_USER = "test|remove-skill-user"
HEADERS = {"Authorization": "Bearer test-token"}


def profile_info():
    """A complete profile, matching the fields the UserInfo model requires."""
    return {
        "name": "Test User",
        "email": "test@example.com",
        "phone": None,
        "location": "West Lafayette, IN",
        "skills": [
            {"skill_name": "Python", "proficiency_level": 4},
            {"skill_name": "SQL", "proficiency_level": 3},
            {"skill_name": "React", "proficiency_level": 2},
        ],
        "education": [],
        "projects": [],
        "socials": [],
        "employment_history": [],
    }


def make_client(tmp_path, monkeypatch, user_row=None):
    """Return a test client backed by a fresh database holding `user_row` (if any)."""
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'profile.db'}")
    Base.metadata.create_all(engine)
    if user_row is not None:
        with Session(engine) as session:
            session.add(user_row)
            session.commit()

    async def verify_token(token):
        return {"sub": TEST_USER}

    monkeypatch.setattr(app_module, "engine", engine)
    monkeypatch.setattr("jobrec.auth.api_client.verify_access_token", verify_token)
    return app.test_client(), engine


def stored_skill_names(engine):
    with Session(engine) as session:
        row = session.get(UserInfoTable, TEST_USER)
        return [skill["skill_name"] for skill in row.info["skills"]]


@pytest.fixture
def client_with_profile(tmp_path, monkeypatch):
    row = UserInfoTable(user_id=TEST_USER, info=profile_info(), done_processing=True)
    return make_client(tmp_path, monkeypatch, row)


def test_removes_only_the_named_skill(client_with_profile):
    client, engine = client_with_profile

    response = client.delete(
        "/api/profile/skills", json={"skill_name": "SQL"}, headers=HEADERS
    )

    assert response.status_code == 200
    returned = [s["skill_name"] for s in response.get_json()["user_info"]["skills"]]
    assert returned == ["Python", "React"]
    assert stored_skill_names(engine) == ["Python", "React"]


def test_match_ignores_case_and_surrounding_spaces(client_with_profile):
    client, engine = client_with_profile

    response = client.delete(
        "/api/profile/skills", json={"skill_name": "  pYtHoN "}, headers=HEADERS
    )

    assert response.status_code == 200
    assert stored_skill_names(engine) == ["SQL", "React"]


def test_unknown_skill_leaves_profile_unchanged(client_with_profile):
    client, engine = client_with_profile

    response = client.delete(
        "/api/profile/skills", json={"skill_name": "Rust"}, headers=HEADERS
    )

    assert response.status_code == 200
    assert stored_skill_names(engine) == ["Python", "SQL", "React"]


@pytest.mark.parametrize("body", [{}, {"skill_name": ""}, None])
def test_missing_skill_name_returns_400(client_with_profile, body):
    client, engine = client_with_profile

    if body is None:
        response = client.delete("/api/profile/skills", headers=HEADERS)
    else:
        response = client.delete("/api/profile/skills", json=body, headers=HEADERS)

    assert response.status_code == 400
    assert stored_skill_names(engine) == ["Python", "SQL", "React"]


def test_user_without_profile_returns_404(tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch, user_row=None)

    response = client.delete(
        "/api/profile/skills", json={"skill_name": "Python"}, headers=HEADERS
    )

    assert response.status_code == 404


def test_profile_still_processing_returns_404(tmp_path, monkeypatch):
    row = UserInfoTable(user_id=TEST_USER, info=profile_info(), done_processing=False)
    client, engine = make_client(tmp_path, monkeypatch, row)

    response = client.delete(
        "/api/profile/skills", json={"skill_name": "Python"}, headers=HEADERS
    )

    assert response.status_code == 404
    assert stored_skill_names(engine) == ["Python", "SQL", "React"]


def test_request_without_token_is_rejected(client_with_profile):
    client, engine = client_with_profile

    response = client.delete("/api/profile/skills", json={"skill_name": "Python"})

    assert response.status_code == 401
    assert stored_skill_names(engine) == ["Python", "SQL", "React"]

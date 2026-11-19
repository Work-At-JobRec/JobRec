"""Unit tests for PUT /api/update_profile (manual profile editing in jobrec/app.py).

Each test runs against a fresh SQLite database and a mocked Auth0 token,
so no real user data or network access is needed.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import jobrec.app as app_module
from jobrec.app import app
from jobrec.openaiapi import Base, UserInfoTable

TEST_USER = "test|update-profile-user"
HEADERS = {"Authorization": "Bearer test-token"}


def profile_info(**overrides):
    info = {
        "name": "Jane Smith",
        "email": "jane@example.com",
        "phone": "(+1) 650-890-0093",
        "location": "West Lafayette, IN",
        "skills": [{"skill_name": "Python", "proficiency_level": 4}],
        "education": [{"school": "Purdue University", "degree": "BS Computer Engineering"}],
        "projects": ["RAG Email Generator"],
        "socials": [{"platform": "LinkedIn", "url": "https://linkedin.com/in/jane"}],
        "employment_history": [{"company_name": "Apple", "role": "Software Engineer"}],
    }
    info.update(overrides)
    return info


def make_client(tmp_path, monkeypatch, user_row=None):
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


def stored_info(engine):
    with Session(engine) as session:
        return session.get(UserInfoTable, TEST_USER).info


@pytest.fixture
def client_with_profile(tmp_path, monkeypatch):
    row = UserInfoTable(user_id=TEST_USER, info=profile_info(), done_processing=True)
    return make_client(tmp_path, monkeypatch, row)


def test_replaces_the_whole_profile(client_with_profile):
    client, engine = client_with_profile
    edited = profile_info(
        name="Jane A. Smith",
        location="Palo Alto, CA",
        skills=[
            {"skill_name": "Python", "proficiency_level": 4},
            {"skill_name": "Docker", "proficiency_level": 2},
        ],
        education=[],
        projects=["RAG Email Generator", "Campus Parking Tracker"],
        employment_history=[
            {"company_name": "Apple", "role": "Software Engineer"},
            {"company_name": "Microsoft", "role": "Intern"},
        ],
    )

    response = client.put("/api/update_profile", json=edited, headers=HEADERS)

    assert response.status_code == 200
    assert response.get_json() == {"status": "done", "user_info": edited}
    assert stored_info(engine) == edited


def test_new_profile_is_visible_through_get_profile(client_with_profile):
    client, _ = client_with_profile
    edited = profile_info(name="Jane A. Smith")

    client.put("/api/update_profile", json=edited, headers=HEADERS)
    response = client.get("/api/profile", headers=HEADERS)

    assert response.get_json() == {"status": "done", "user_info": edited}


def test_tidies_the_submitted_profile(client_with_profile):
    client, engine = client_with_profile
    messy = profile_info(
        name="  Jane Smith  ",
        phone="   ",
        skills=[
            {"skill_name": " Python ", "proficiency_level": 4},
            {"skill_name": "python", "proficiency_level": 1},
            {"skill_name": "  ", "proficiency_level": 2},
        ],
        education=[{"school": " ", "degree": ""}],
        projects=["  RAG Email Generator ", ""],
        socials=[
            {"platform": "GitHub", "url": "github.com/jane"},
            {"platform": "Empty", "url": " "},
        ],
        employment_history=[{"company_name": "", "role": "  "}],
    )

    response = client.put("/api/update_profile", json=messy, headers=HEADERS)

    assert response.status_code == 200
    info = stored_info(engine)
    assert info["name"] == "Jane Smith"
    assert info["phone"] is None
    assert info["skills"] == [{"skill_name": "Python", "proficiency_level": 4}]
    assert info["education"] == []
    assert info["projects"] == ["RAG Email Generator"]
    assert info["socials"] == [{"platform": "GitHub", "url": "https://github.com/jane"}]
    assert info["employment_history"] == []


@pytest.mark.parametrize("level", [0, 5, 2.5, "expert"])
def test_rejects_proficiency_outside_1_to_4(client_with_profile, level):
    client, engine = client_with_profile
    bad = profile_info(skills=[{"skill_name": "Go", "proficiency_level": level}])

    response = client.put("/api/update_profile", json=bad, headers=HEADERS)

    assert response.status_code == 400
    assert stored_info(engine) == profile_info()


def test_rejects_incomplete_body(client_with_profile):
    client, engine = client_with_profile

    response = client.put("/api/update_profile", json={"name": "Jane"}, headers=HEADERS)

    assert response.status_code == 400
    assert stored_info(engine) == profile_info()


def test_creates_profile_when_none_exists(tmp_path, monkeypatch):
    client, engine = make_client(tmp_path, monkeypatch)

    response = client.put("/api/update_profile", json=profile_info(), headers=HEADERS)

    assert response.status_code == 200
    assert stored_info(engine) == profile_info()


def test_refuses_while_resume_is_parsing(tmp_path, monkeypatch):
    row = UserInfoTable(user_id=TEST_USER, info={}, done_processing=False)
    client, engine = make_client(tmp_path, monkeypatch, row)

    response = client.put("/api/update_profile", json=profile_info(), headers=HEADERS)

    assert response.status_code == 409
    assert stored_info(engine) == {}


def test_requires_auth(client_with_profile):
    client, _ = client_with_profile

    response = client.put("/api/update_profile", json=profile_info())

    assert response.status_code == 401

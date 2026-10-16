import io
import os
import sys
from unittest.mock import patch
from functools import wraps
from jobrec.app import app
from sqlalchemy import delete

# Lets this test import files from app/src
SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, SRC_DIR)

mock_user = "test|mockuser"
fake_headers = {"Authorization": "Bearer 39"}


async def mock_verify_access_token(token):
    return {"sub": mock_user}


def ignore_auth(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        with patch("jobrec.app.get_user_id") as mock_auth0:
            mock_auth0.return_value = mock_user
            with patch(
                "jobrec.auth.api_client.verify_access_token",
                new=mock_verify_access_token,
            ):
                return f(*args, **kwargs)

    return wrapper


# These MUST come after sys.path.insert(...)

from jobrec.openaiapi import (
    Base,
    UserInfoTable,
    UserInfo,
    SkillRanking,
    update_skill_db,
)

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session


# Tests if PDF is allowed to be uploaded
def test_pdf_is_allowed():
    from jobrec.app import allowed_file

    assert allowed_file("resume.pdf")


# Tests if DOCX is allowed to be uploaded
def test_docx_is_allowed():
    from jobrec.app import allowed_file

    assert allowed_file("resume.docx")


# Tests if TXT is not allowed to be uploaded
def test_txt_is_not_allowed():
    from jobrec.app import allowed_file

    assert not allowed_file("resume.txt")


# Tests if PNG is not allowed to be uploaded
def test_jpg_is_not_allowed():
    from jobrec.app import allowed_file

    assert not allowed_file("resume.jpg")


# Tests if a corrupted/dummy PDF resume is rejected and not saved
@ignore_auth
def test_corrupted_pdf_upload_is_not_saved(tmp_path):

    app.config["TESTING"] = True
    app.config["UPLOAD_FOLDER"] = str(tmp_path)

    client = app.test_client()

    fake_pdf = io.BytesIO(b"fake pdf contents")
    with patch("jobrec.app.Thread"):
        response = client.post(
            "/upload",
            data={"resume": (fake_pdf, "test_resume.pdf")},
            content_type="multipart/form-data",
            headers=fake_headers,
        )

        uploaded_file = tmp_path / "test_resume.pdf"

        assert not uploaded_file.exists()
        assert not (response.status_code in [200, 302])


# Tests if a corrupted/dummy DOCX resume is rejected and not saved
@ignore_auth
def test_corrupted_docx_upload_is_not_saved(tmp_path):
    from jobrec.app import app

    app.config["TESTING"] = True
    app.config["UPLOAD_FOLDER"] = str(tmp_path)

    client = app.test_client()

    fake_docx = io.BytesIO(b"fake docx contents")

    with patch("jobrec.app.Thread"):
        response = client.post(
            "/upload",
            data={"resume": (fake_docx, "test_resume.docx")},
            content_type="multipart/form-data",
            headers=fake_headers,
        )

    uploaded_file = tmp_path / "test_resume.docx"

    assert not uploaded_file.exists()
    assert not (response.status_code in [200, 302])


# Tests if a real PDF resume is accepted and saved
@ignore_auth
def test_valid_pdf_upload_is_saved(tmp_path):
    from jobrec.app import app

    app.config["TESTING"] = True
    app.config["UPLOAD_FOLDER"] = str(tmp_path)

    client = app.test_client()

    resume_path = os.path.join(
        os.path.dirname(__file__),
        "test_resumes",
        "Jane_Smith_-_Public_Resume_Spring_2026-1.pdf",
    )

    with open(resume_path, "rb") as resume_file:
        with patch("jobrec.app.Thread"):
            response = client.post(
                "/upload",
                data={
                    "resume": (
                        resume_file,
                        "Jane_Smith_-_Public_Resume_Spring_2026-1.pdf",
                    )
                },
                content_type="multipart/form-data",
                headers=fake_headers,
            )

    saved = list(tmp_path.iterdir())

    assert len(saved) == 1 and saved[0].suffix == ".pdf"
    assert response.status_code == 200


# Tests if a real DOCX resume is accepted and saved
@ignore_auth
def test_valid_docx_upload_is_saved(tmp_path):
    from jobrec.app import app

    app.config["TESTING"] = True
    app.config["UPLOAD_FOLDER"] = str(tmp_path)

    client = app.test_client()

    resume_path = os.path.join(
        os.path.dirname(__file__),
        "test_resumes",
        "Jane_Smith_-_Public_Resume_Spring_2026-1.docx",
    )

    with open(resume_path, "rb") as resume_file:
        with patch("jobrec.app.Thread"):
            response = client.post(
                "/upload",
                data={
                    "resume": (
                        resume_file,
                        "Jane_Smith_-_Public_Resume_Spring_2026-1.docx",
                    )
                },
                content_type="multipart/form-data",
                headers=fake_headers,
            )

    saved = list(tmp_path.iterdir())

    assert len(saved) == 1 and saved[0].suffix == ".docx"
    assert response.status_code == 200


# Tests if a dummy txt resume is rejected
@ignore_auth
def test_txt_upload_is_rejected(tmp_path):
    from jobrec.app import app

    app.config["TESTING"] = True
    app.config["UPLOAD_FOLDER"] = str(tmp_path)

    client = app.test_client()

    fake_txt = io.BytesIO(b"hello world")
    response = client.post(
        "/upload",
        data={"resume": (fake_txt, "resume.txt")},
        content_type="multipart/form-data",
        headers=fake_headers,
    )

    assert not (tmp_path / "resume.txt").exists()


# Tests if a dummy png resume is rejected
@ignore_auth
def test_png_upload_is_rejected(tmp_path):
    from jobrec.app import app

    app.config["TESTING"] = True
    app.config["UPLOAD_FOLDER"] = str(tmp_path)

    client = app.test_client()

    fake_png = io.BytesIO(b"hello world")
    response = client.post(
        "/upload",
        data={"resume": (fake_png, "resume.png")},
        content_type="multipart/form-data",
        headers=fake_headers,
    )

    assert not (tmp_path / "resume.png").exists()


# Tests if extracted skills are displayed on the user profile
@ignore_auth
def test_profile_displays_skills(tmp_path):
    from jobrec.app import app

    # Create temporary database
    test_db = tmp_path / "test_user_skills.db"
    test_engine = create_engine(f"sqlite+pysqlite:///{test_db}")
    Base.metadata.create_all(test_engine)

    dummy_user_info = UserInfo(
        skills=[
            SkillRanking(skill_name="Python", proficiency_level=4),
            SkillRanking(skill_name="C", proficiency_level=3),
        ],
        education=[],
        projects=[],
        socials=[],
        employment_history=[],
    )

    with Session(test_engine) as session:
        user = UserInfoTable(
            user_id=mock_user, info=dummy_user_info.model_dump(), done_processing=True
        )

        session.add(user)
        session.commit()

    app.config["TESTING"] = True
    client = app.test_client()

    with patch("jobrec.app.engine", test_engine):
        response = client.get("/api/profile", headers=fake_headers)

    assert response.status_code == 200

    data = response.get_json()

    assert data["user_info"]["skills"][0]["skill_name"] == "Python"
    assert data["user_info"]["skills"][0]["proficiency_level"] == 4
    assert data["user_info"]["skills"][1]["skill_name"] == "C"
    assert data["user_info"]["skills"][1]["proficiency_level"] == 3


@ignore_auth
def test_persistence(tmp_path):
    # disable automatic database clearing
    if not (os.environ.get("DEV") is None):
        os.environ.pop("DEV")

    test_db = tmp_path / "test_user_info.db"
    test_engine = create_engine(f"sqlite+pysqlite:///{test_db}")
    Base.metadata.create_all(test_engine)

    with Session(test_engine) as session:
        session.execute(delete(UserInfoTable))

    app.config["TESTING"] = True
    client = app.test_client()
    personal_data = {
        "name": "Kanade Yoisaki",
        "email": "k@gmail.com",
        "address": "here",
        "phone": "(555) 393-9393",
    }
    with patch("jobrec.app.engine", test_engine):
        response = client.post(
            "/api/onboarding", data=personal_data, headers=fake_headers
        )

    assert response.status_code == 200
    # restart client
    del client
    app.config["TESTING"] = True
    client = app.test_client()
    with patch("jobrec.app.engine", test_engine):
        response = client.get("/api/profile", headers=fake_headers)

    assert response.status_code == 200
    data = UserInfo.model_validate(response.get_json().get("user_info"))
    assert not (data is None)
    assert data.location == personal_data.get("address")
    assert data.email == personal_data.get("email")
    assert data.name == personal_data.get("name")
    assert data.phone == personal_data.get("phone")


@ignore_auth
def test_api_returns_correct_personals(tmp_path):
    test_db = tmp_path / "test_user_info.db"
    test_engine = create_engine(f"sqlite+pysqlite:///{test_db}")
    Base.metadata.create_all(test_engine)

    with Session(test_engine) as session:
        dummy_user_personal = UserInfo(
            name="Kanade Yoisaki",
            email="k@gmail.com",
            location="N/A",
            phone="(555) 393-9393",
            skills=[],
            education=[],
            projects=[],
            socials=[],
            employment_history=[],
        )

        session.add(
            UserInfoTable(
                user_id=mock_user,
                info=dummy_user_personal.model_dump(),
                done_processing=True,
            )
        )
        session.commit()

        app.config["TESTING"] = True
        client = app.test_client()

        with patch("jobrec.app.engine", test_engine):
            response = client.get("/api/profile", headers=fake_headers)

        assert response.status_code == 200

        data = UserInfo.model_validate(response.get_json().get("user_info"))
        assert not (data is None)
        assert data.location == dummy_user_personal.location
        assert data.email == dummy_user_personal.email
        assert data.name == dummy_user_personal.name
        assert data.phone == dummy_user_personal.phone


# --- #116: uploads are stored under a per-user random name, never the name the browser sent ---

RESUME_PDF = os.path.join(
    os.path.dirname(__file__), "test_resumes", "Jane_Smith_-_Public_Resume_Spring_2026-1.pdf"
)


def post_resume(client, browser_name="resume.pdf"):
    with open(RESUME_PDF, "rb") as resume_file, patch("jobrec.app.Thread") as thread:
        response = client.post(
            "/upload",
            data={"resume": (resume_file, browser_name)},
            content_type="multipart/form-data",
            headers=fake_headers,
        )
    return response, thread


# The stored name is derived from the user and a random token, with the extension the browser sent
def test_upload_filename_is_per_user_random_and_keeps_the_extension():
    from jobrec.app import upload_filename

    first = upload_filename("auth0|alice", "My Resume (final).PDF")
    second = upload_filename("auth0|alice", "My Resume (final).PDF")
    other = upload_filename("auth0|bob", "My Resume (final).PDF")

    assert first.endswith(".pdf") and second.endswith(".pdf")
    assert first != second
    assert first.split("-")[0] == second.split("-")[0]
    assert first.split("-")[0] != other.split("-")[0]
    assert "My" not in first and "(" not in first and "/" not in first and "\\" not in first


# The file on disk does not carry the browser's filename, and the parse thread gets the stored path
@ignore_auth
def test_upload_is_stored_under_a_random_name_not_the_browsers(tmp_path):
    app.config["TESTING"] = True
    app.config["UPLOAD_FOLDER"] = str(tmp_path)
    client = app.test_client()

    response, thread = post_resume(client, "Jane_Smith_Resume.pdf")

    assert response.status_code == 200
    saved = list(tmp_path.iterdir())
    assert len(saved) == 1
    assert saved[0].name != "Jane_Smith_Resume.pdf"
    assert saved[0].suffix == ".pdf"
    assert thread.call_args.kwargs["args"][2] == str(saved[0])


# Two users who both upload "resume.pdf" get two files; neither overwrites the other
def test_two_users_uploading_the_same_filename_get_separate_files(tmp_path):
    app.config["TESTING"] = True
    app.config["UPLOAD_FOLDER"] = str(tmp_path)
    client = app.test_client()

    with patch("jobrec.auth.api_client.verify_access_token", new=mock_verify_access_token):
        with patch("jobrec.app.get_user_id", return_value="auth0|alice"):
            first, _ = post_resume(client, "resume.pdf")
        with patch("jobrec.app.get_user_id", return_value="auth0|bob"):
            second, _ = post_resume(client, "resume.pdf")

    assert first.status_code == 200 and second.status_code == 200
    saved = sorted(p.name for p in tmp_path.iterdir())
    assert len(saved) == 2
    assert "resume.pdf" not in saved
    assert saved[0].split("-")[0] != saved[1].split("-")[0]


# --- #117: the upload route does not print the request to the function log ---

@ignore_auth
def test_upload_does_not_print_the_request(tmp_path, capsys):
    app.config["TESTING"] = True
    app.config["UPLOAD_FOLDER"] = str(tmp_path)
    client = app.test_client()

    post_resume(client, "Jane_Smith_Resume.pdf")

    captured = capsys.readouterr()
    assert "Jane_Smith_Resume.pdf" not in captured.out
    assert "ImmutableMultiDict" not in captured.out

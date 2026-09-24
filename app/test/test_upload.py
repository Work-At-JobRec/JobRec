import io
import os
import sys
from unittest.mock import patch
from functools import wraps


# Lets this test import files from app/src
SRC_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "src")
)
sys.path.insert(0, SRC_DIR)

mock_user = "test|mockuser"
fake_headers = {"Authorization" : "Bearer 39"}

patch()

async def mock_verify_access_token(token):
    return {"sub": mock_user}



def ignore_auth(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        with patch("app.get_user_id") as mock_auth0:
            mock_auth0.return_value = mock_user
            with patch("auth.api_client.verify_access_token", new=mock_verify_access_token):
                return f(*args, **kwargs)
    return wrapper

# These MUST come after sys.path.insert(...)

from openaiapi import (
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
    from app import allowed_file
    assert allowed_file("resume.pdf")
    
# Tests if DOCX is allowed to be uploaded
def test_docx_is_allowed():
    from app import allowed_file
    assert allowed_file("resume.docx")

# Tests if TXT is not allowed to be uploaded
def test_txt_is_not_allowed():
    from app import allowed_file
    assert not allowed_file("resume.txt")

# Tests if PNG is not allowed to be uploaded
def test_jpg_is_not_allowed():
    from app import allowed_file
    assert not allowed_file("resume.jpg")

# Tests if a corrupted/dummy PDF resume is rejected and not saved
@ignore_auth
def test_corrupted_pdf_upload_is_not_saved(tmp_path):
    from app import app
    app.config["TESTING"] = True
    app.config["UPLOAD_FOLDER"] = str(tmp_path)

    client = app.test_client()

    fake_pdf = io.BytesIO(b"fake pdf contents")
    with patch("app.Thread"):
        response = client.post(
            "/upload",
            data={
                "resume": (fake_pdf, "test_resume.pdf")
            },
            content_type="multipart/form-data",
            headers = fake_headers
        )

        uploaded_file = tmp_path / "test_resume.pdf"

        assert not uploaded_file.exists()
        assert not (response.status_code in [200, 302])


# Tests if a corrupted/dummy DOCX resume is rejected and not saved
@ignore_auth
def test_corrupted_docx_upload_is_not_saved(tmp_path):
    from app import app
    app.config["TESTING"] = True
    app.config["UPLOAD_FOLDER"] = str(tmp_path)

    client = app.test_client()

    fake_docx = io.BytesIO(b"fake docx contents")


    with patch("app.Thread"):
        response = client.post(
            "/upload",
            data={
                "resume": (fake_docx, "test_resume.docx")
            },
            content_type="multipart/form-data",
            headers=fake_headers
        )

    uploaded_file = tmp_path / "test_resume.docx"

    assert not uploaded_file.exists()
    assert not (response.status_code in [200, 302])


# Tests if a real PDF resume is accepted and saved
@ignore_auth
def test_valid_pdf_upload_is_saved(tmp_path):
    from app import app
    app.config["TESTING"] = True
    app.config["UPLOAD_FOLDER"] = str(tmp_path)

    client = app.test_client()

    resume_path = os.path.join(
        os.path.dirname(__file__),
        "test_resumes",
        "Jane_Smith_-_Public_Resume_Spring_2026-1.pdf"
    )

    with open(resume_path, "rb") as resume_file:
        with patch("app.Thread"):
            response = client.post(
                "/upload",
                data={
                    "resume": (
                        resume_file,
                        "Jane_Smith_-_Public_Resume_Spring_2026-1.pdf"
                    )
                },
                content_type="multipart/form-data",
                headers=fake_headers
            )

    uploaded_file = (
        tmp_path / "Jane_Smith_-_Public_Resume_Spring_2026-1.pdf"
    )

    assert uploaded_file.exists()
    assert response.status_code == 200


# Tests if a real DOCX resume is accepted and saved
@ignore_auth
def test_valid_docx_upload_is_saved(tmp_path):
    from app import app
    app.config["TESTING"] = True
    app.config["UPLOAD_FOLDER"] = str(tmp_path)

    client = app.test_client()

    resume_path = os.path.join(
        os.path.dirname(__file__),
        "test_resumes",
        "Jane_Smith_-_Public_Resume_Spring_2026-1.docx"
    )

    with open(resume_path, "rb") as resume_file:
        with patch("app.Thread"):
            response = client.post(
                "/upload",
                data={
                    "resume": (
                        resume_file,
                        "Jane_Smith_-_Public_Resume_Spring_2026-1.docx"
                    )
                },
                content_type="multipart/form-data",
                headers=fake_headers
            )

    uploaded_file = (
        tmp_path / "Jane_Smith_-_Public_Resume_Spring_2026-1.docx"
    )

    assert uploaded_file.exists()
    assert response.status_code == 200  

# Tests if a dummy txt resume is rejected
@ignore_auth
def test_txt_upload_is_rejected(tmp_path):
    from app import app
    app.config["TESTING"] = True
    app.config["UPLOAD_FOLDER"] = str(tmp_path)

    client = app.test_client()

    fake_txt = io.BytesIO(b"hello world")
    response = client.post(
        "/upload",
        data={
            "resume": (fake_txt, "resume.txt")
        },
        content_type="multipart/form-data",
        headers=fake_headers
    )

    assert not (tmp_path / "resume.txt").exists()
    
# Tests if a dummy png resume is rejected
@ignore_auth
def test_png_upload_is_rejected(tmp_path):
    from app import app
    app.config["TESTING"] = True
    app.config["UPLOAD_FOLDER"] = str(tmp_path)

    client = app.test_client()

    fake_png = io.BytesIO(b"hello world")
    response = client.post(
        "/upload",
        data={
            "resume": (fake_png, "resume.png")
        },
        content_type="multipart/form-data",
        headers=fake_headers
    )

    assert not (tmp_path / "resume.png").exists()    
    
# Tests if extracted skills are displayed on the user profile
@ignore_auth
def test_profile_displays_skills(tmp_path):
    from app import app
   # Create temporary database
    test_db = tmp_path / "test_user_skills.db"
    test_engine = create_engine(f"sqlite+pysqlite:///{test_db}")
    Base.metadata.create_all(test_engine)

    dummy_user_info = UserInfo(
        skills=[
            SkillRanking(
                skill_name="Python",
                proficiency_level=4
            ),
            SkillRanking(
                skill_name="C",
                proficiency_level=3
            ),
        ],
        education=[],
        projects=[],
        socials=[],
        employment_history=[]
    )

    with Session(test_engine) as session:
        user = UserInfoTable(
            user_id=mock_user,
            info=dummy_user_info.model_dump(),
            done_processing=True
        )

        session.add(user)
        session.commit()

    app.config["TESTING"] = True
    client = app.test_client()

    with patch("app.engine", test_engine):
        response = client.get("/api/profile", headers=fake_headers)  

    assert response.status_code == 200

    data = response.get_json()

    assert data["user_info"]["skills"][0]["skill_name"] == "Python"
    assert data["user_info"]["skills"][0]["proficiency_level"] == 4
    assert data["user_info"]["skills"][1]["skill_name"] == "C"
    assert data["user_info"]["skills"][1]["proficiency_level"] == 3

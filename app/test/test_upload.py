import io
import os
import sys
from unittest.mock import patch


# Lets this test import files from app/src
SRC_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "src")
)
sys.path.insert(0, SRC_DIR)

# These MUST come after sys.path.insert(...)
from app import app, allowed_file

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
    assert allowed_file("resume.pdf")
    
# Tests if DOCX is allowed to be uploaded
def test_docx_is_allowed():
    assert allowed_file("resume.docx")

# Tests if TXT is not allowed to be uploaded
def test_txt_is_not_allowed():
    assert not allowed_file("resume.txt")

# Tests if PNG is not allowed to be uploaded
def test_jpg_is_not_allowed():
    assert not allowed_file("resume.jpg")

# Tests if a corrupted/dummy PDF resume is rejected and not saved
def test_corrupted_pdf_upload_is_not_saved(tmp_path):
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
        )

    uploaded_file = tmp_path / "test_resume.pdf"

    assert not uploaded_file.exists()
    assert response.status_code == 302


# Tests if a corrupted/dummy DOCX resume is rejected and not saved
def test_corrupted_docx_upload_is_not_saved(tmp_path):
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
        )

    uploaded_file = tmp_path / "test_resume.docx"

    assert not uploaded_file.exists()
    assert response.status_code == 302


# Tests if a real PDF resume is accepted and saved
def test_valid_pdf_upload_is_saved(tmp_path):
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
            )

    uploaded_file = (
        tmp_path / "Jane_Smith_-_Public_Resume_Spring_2026-1.pdf"
    )

    assert uploaded_file.exists()
    assert response.status_code == 302


# Tests if a real DOCX resume is accepted and saved
def test_valid_docx_upload_is_saved(tmp_path):
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
            )

    uploaded_file = (
        tmp_path / "Jane_Smith_-_Public_Resume_Spring_2026-1.docx"
    )

    assert uploaded_file.exists()
    assert response.status_code == 302    

# Tests if a dummy txt resume is rejected
def test_txt_upload_is_rejected(tmp_path):
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
    )

    assert not (tmp_path / "resume.txt").exists()
    
# Tests if a dummy png resume is rejected    
def test_png_upload_is_rejected(tmp_path):
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
    )

    assert not (tmp_path / "resume.png").exists()    
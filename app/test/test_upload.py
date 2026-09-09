import io
import os
import sys
from unittest.mock import patch

# Lets this test import app/src/app.py
SRC_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "src")
)
sys.path.insert(0, SRC_DIR)

from app import app, allowed_file

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

# Tests if a dummy pdf resume is saved    
def test_pdf_upload_is_saved(tmp_path):
    app.config["TESTING"] = True
    app.config["UPLOAD_FOLDER"] = str(tmp_path)

    client = app.test_client()

    fake_pdf = io.BytesIO(b"fake pdf contents")

    with patch("app.Thread") as mock_thread:
        response = client.post(
            "/upload",
            data={
                "resume": (fake_pdf, "test_resume.pdf")
            },
            content_type="multipart/form-data",
        )

    uploaded_file = tmp_path / "test_resume.pdf"

    assert uploaded_file.exists()
    assert response.status_code == 302
    
# Tests if a dummy docx resume is saved    
def test_docx_upload_is_saved(tmp_path):
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
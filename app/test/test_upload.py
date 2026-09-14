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

# Tests if duplicate skills are removed before user info is stored
def test_update_skill_db_removes_duplicate_skills(tmp_path):
    # Create a temporary database just for this test
    test_db = tmp_path / "test_user_skills.db"
    test_engine = create_engine(f"sqlite+pysqlite:///{test_db}")
    Base.metadata.create_all(test_engine)

    test_user_id = b"test user"

    # update_skill_db expects the user to already exist in the database
    with Session(test_engine) as session:
        user = UserInfoTable(
            user_id=test_user_id,
            info={},
            done_processing=False
        )

        session.add(user)
        session.commit()

    # Dummy LLM output containing duplicate skills
    dummy_user_info = UserInfo(
        skills=[
            SkillRanking(
                skill_name="Python",
                proficiency_level=2
            ),
            SkillRanking(
                skill_name="python",
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

    # Make parse_resume return our dummy data instead of calling OpenAI
    with patch("openaiapi.parse_resume", return_value=dummy_user_info):
        update_skill_db(
            test_user_id,
            test_engine,
            "fake_resume.pdf"
        )

    # Read the stored information back from the database
    with Session(test_engine) as session:
        stmt = select(UserInfoTable).where(
            UserInfoTable.user_id == test_user_id
        )

        stored_user = session.scalars(stmt).one()

        stored_info = UserInfo.model_validate(stored_user.info)

        assert stored_user.done_processing is True

    # Verify the actual stored list has been deduplicated
    stored_skills = stored_info.skills

    normalized_names = [
        skill.skill_name.strip().lower()
        for skill in stored_skills
    ]

    # There should actually only be two objects in the list
    assert len(stored_skills) == 2

    # Python should occur exactly once
    assert normalized_names.count("python") == 1

    # C should occur exactly once
    assert normalized_names.count("c") == 1

    # The higher Python proficiency should have been retained
    python_skill = next(
        skill
        for skill in stored_skills
        if skill.skill_name.strip().lower() == "python"
    )

    assert python_skill.proficiency_level == 4
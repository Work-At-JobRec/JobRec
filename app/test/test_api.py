import io
import os
import sys
import pytest
from unittest.mock import patch
from time import time_ns

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
    client,
    parse_resume
)

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

@pytest.mark.openai
def test_openai_api_connection(request):
    # Do not run unless --run-openai was explicitly provided
    if not request.config.getoption("--run-openai"):
        pytest.skip("OpenAI API test only runs with --run-openai")
        
    # Skip if no API key can be found
    if not os.getenv("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY is not available")

    response = client.models.list()

    # If authentication/networking failed, the call above should raise an error.
    # A successful response should contain model data.
    assert response.data is not None
    assert len(response.data) > 0

@pytest.mark.openai
def test_extraction_time_within_bounds(request):
    TIME_LIMIT_NS = 20 * 10 ** 9
    ITERATIONS = 30
    CONFIDENCE_PERCENT = 0.9

    if not request.config.getoption("--run-openai"):
            pytest.skip("OpenAI API test only runs with --run-openai")
    # Skip if no API key can be found
    if not os.getenv("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY is not available")
    resume_path = os.path.join(
            os.path.dirname(__file__),
            "test_resumes",
            "Simple Resume.pdf"
        )

    # Perform 30 tests and ensure time limits are not exceeded
    
    average_time_ns = 0
    correct_count = 0
    for _ in range(ITERATIONS):
        start = time_ns()
        _ = parse_resume(resume_path)
        elapsed = (time_ns() - start)
        average_time_ns += elapsed / ITERATIONS
        if elapsed <= TIME_LIMIT_NS:
            correct_count += 1

    assert average_time_ns <= TIME_LIMIT_NS
    assert correct_count >= ITERATIONS * CONFIDENCE_PERCENT
    
@pytest.mark.openai
def test_resume_skill_extraction(request):
    # Do not run unless --run-openai was explicitly provided
    if not request.config.getoption("--run-openai"):
        pytest.skip("OpenAI API test only runs with --run-openai")
        
    # Skip if no API key can be found
    if not os.getenv("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY is not available")

    # Path to test/test_resumes/Simple Resume.pdf
    resume_path = os.path.join(
        os.path.dirname(__file__),
        "test_resumes",
        "Simple Resume.pdf"
    )

    # Send the resume through the actual OpenAI resume parser
    user_info = parse_resume(resume_path)

    # Verify that the model returned structured user information
    assert user_info is not None
    assert isinstance(user_info, UserInfo)

    # Verify that skills were extracted
    assert len(user_info.skills) > 0

    # Normalize skill names for comparison
    extracted_skills = {
        skill.skill_name.strip().lower()
        for skill in user_info.skills
    }

    # These skills are explicitly listed in Simple Resume.pdf
    assert "python" in extracted_skills
    assert "sql" in extracted_skills
    assert "flask" in extracted_skills

    # Verify every returned skill has valid data
    for skill in user_info.skills:
        assert skill.skill_name.strip() != ""
        assert 1 <= skill.proficiency_level <= 4


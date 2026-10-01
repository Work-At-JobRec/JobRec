import os
import sys
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, SRC_DIR)

import jobrec.skill_detection  # noqa: E402
import jobrec.openaiapi  # noqa: E402
from jobrec.skill_detection import (  # noqa: E402
    DiscoveredSkill,
    SkillRanking,
    UnconstrainedSkillResult,
    _constrained_result_model,
    detect_document_skills,
)


def test_detectors_use_distinct_validated_output_models(monkeypatch):
    requested_formats = []

    class FakeResponses:
        def parse(self, **kwargs):
            requested_formats.append(kwargs["text_format"])
            if kwargs["text_format"].__name__ == "ConstrainedSkillResult":
                result = kwargs["text_format"].model_validate(
                    {"skills": [{"skill_name": "Python", "proficiency_level": 4}]}
                )
            else:
                result = UnconstrainedSkillResult(
                    skills=[
                        DiscoveredSkill(
                            skill_name="Go",
                            category="Programming Languages",
                            proficiency_level=3,
                        ),
                        DiscoveredSkill(
                            skill_name="Python",
                            category="Programming Languages",
                            proficiency_level=2,
                        ),
                    ]
                )
            return SimpleNamespace(output_parsed=result)

    monkeypatch.setattr(
        jobrec.skill_detection, "_client", SimpleNamespace(responses=FakeResponses())
    )

    matched, discovered = detect_document_skills(
        "Built production services with Python and Go.",
        ["Python"],
        document_type="resume",
    )

    assert requested_formats[0].__name__ == "ConstrainedSkillResult"
    assert requested_formats[1] is UnconstrainedSkillResult
    schema = requested_formats[0].model_json_schema()
    assert schema["$defs"]["CatalogSkillName"]["enum"] == ["Python"]
    assert matched == [SkillRanking(skill_name="Python", proficiency_level=4)]
    assert discovered == [
        DiscoveredSkill(
            skill_name="Go",
            category="Programming Languages",
            proficiency_level=3,
        )
    ]
    with pytest.raises(ValidationError):
        SkillRanking(skill_name="Python", proficiency_level=5)
    with pytest.raises(ValidationError):
        requested_formats[0].model_validate(
            {"skills": [{"skill_name": "Unlisted", "proficiency_level": 2}]}
        )


def test_empty_catalog_skips_constrained_model():
    assert _constrained_result_model([]) is None


def test_resume_parser_uses_dynamic_skill_detection(tmp_path, monkeypatch):
    resume = tmp_path / "resume.pdf"
    resume.write_bytes(b"resume placeholder")
    discovered = [
        DiscoveredSkill(
            skill_name="Go",
            category="Programming Languages",
            proficiency_level=3,
        )
    ]
    parsed_resume = jobrec.openaiapi.UserInfo(
        skills=[SkillRanking(skill_name="Legacy", proficiency_level=1)],
        education=[],
        projects=[],
        socials=[],
        employment_history=[],
    )

    class FakeFiles:
        def create(self, **kwargs):
            return SimpleNamespace(id="uploaded-resume")

    class FakeResponses:
        def parse(self, **kwargs):
            return SimpleNamespace(output_parsed=parsed_resume)

    engine = object()
    monkeypatch.setattr(
        jobrec.openaiapi,
        "client",
        SimpleNamespace(files=FakeFiles(), responses=FakeResponses()),
    )
    monkeypatch.setattr(
        jobrec.openaiapi, "extract_resume_text", lambda filename: "Python and Go"
    )
    monkeypatch.setattr(
        jobrec.openaiapi,
        "get_skill_catalog",
        lambda supplied_engine: ["Python"],
    )
    monkeypatch.setattr(
        jobrec.openaiapi,
        "detect_document_skills",
        lambda text, catalog, *, document_type: (
            [SkillRanking(skill_name="Python", proficiency_level=4)],
            discovered,
        ),
    )
    persisted = []
    monkeypatch.setattr(
        jobrec.openaiapi,
        "persist_discovered_skills",
        lambda supplied_engine, skills: persisted.extend(skills),
    )

    result = jobrec.openaiapi.parse_resume(str(resume), engine)

    assert result.skills == [
        SkillRanking(skill_name="Python", proficiency_level=4),
        SkillRanking(skill_name="Go", proficiency_level=3),
    ]
    assert persisted == discovered

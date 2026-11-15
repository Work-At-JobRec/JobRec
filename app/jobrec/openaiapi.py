import logging
import os
import traceback
from openai import OpenAI
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
import sqlalchemy
from jobrec.db import (
    Base,
)  # noqa: F401  (re-exported: app.py and tests import Base from here)
from jobrec.skill_detection import (
    SkillRanking,
    detect_document_skills,
    extract_resume_text,
    get_skill_catalog,
    persist_discovered_skills,
)

_ = load_dotenv()

logger = logging.getLogger(__name__)

client = OpenAI()


class UserInfoTable(Base):
    __tablename__ = "user_info"

    user_id = sqlalchemy.Column("user_id", sqlalchemy.String, primary_key=True)
    info = sqlalchemy.Column("skills", sqlalchemy.JSON)
    done_processing = sqlalchemy.Column("done_processing", sqlalchemy.Boolean)


class Education(BaseModel):
    school: str = Field(..., description="School that the degree was earned from")
    degree: str = Field(
        ...,
        description="Degree level and field of study achieved from this university (e.g. bachelor's in art history). Do not include GPA.",
    )


class Social(BaseModel):
    platform: str = Field(
        ..., description="Name of platform where this account is hosted"
    )
    url: str = Field(
        ...,
        description="Full URL of the user's account on this platform, including hostname",
    )


class Employment(BaseModel):
    company_name: str = Field(
        ..., description="Name of the company where the user worked"
    )
    role: str = Field(..., description="User's role at the company")


class UserInfo(BaseModel):
    name: str | None = Field(
        None, description="Applicant's full name, as it appears on the resume"
    )
    email: str | None = Field(
        None, description="Applicant's contact email address, if listed on the resume"
    )
    phone: str | None = Field(
        None, description="Applicant's phone number, if listed on the resume"
    )
    location: str | None = Field(
        None,
        description="Applicant's city and state (or region/country), if listed on the resume",
    )
    skills: list[SkillRanking] = Field(
        ..., description="All skills that the applicant has any experience with."
    )
    education: list[Education] = Field(
        ..., description="All education experience the applicant has"
    )
    projects: list[str] = Field(
        ...,
        description="Names of all projects the user has experience with (do not include other information)",
    )
    socials: list[Social] = Field(
        ...,
        description="All personal (not organizational) social media included in the user's resume",
    )
    employment_history: list[Employment] = Field(
        ..., description="All previous work experience of the user"
    )


def _remove_uploaded_resume(filename: str) -> None:
    """Delete the stored upload; the resume is not needed once parsing has finished (#115)."""
    try:
        os.remove(filename)
    except FileNotFoundError:
        pass
    except OSError:
        logger.exception("Could not delete the uploaded resume %s", filename)


def _delete_openai_file(file_id: str) -> None:
    """Remove the copy of the resume that was uploaded to OpenAI for parsing (#115)."""
    try:
        client.files.delete(file_id)
    except Exception:
        logger.exception("Could not delete OpenAI file %s", file_id)


def update_skill_db(user_id: bytes, engine: sqlalchemy.Engine, filename: str):
    """Parse the uploaded resume into the user's profile, then delete the upload.

    The file is removed whether or not parsing succeeded, so a resume never
    outlives the request that needed it (threat model TB1, NFR-003).
    """
    try:
        try:
            user_info = parse_resume(filename, engine)
        except Exception:
            traceback.print_exc()
            user_info = None
        _store_parsed_profile(user_id, engine, user_info)
    finally:
        _remove_uploaded_resume(filename)


def _store_parsed_profile(user_id, engine: sqlalchemy.Engine, user_info) -> None:
    with Session(engine) as session:

        stmt = select(UserInfoTable).where(UserInfoTable.user_id == user_id)
        try:
            skill_ranking = session.scalars(stmt).one()
        except:
            return None

        if user_info is None:
            skill_ranking.done_processing = True
        else:
            # Deduplicate skills
            unique_skills = {}

            for skill in user_info.skills:
                normalized_name = skill.skill_name.strip().lower()

                if normalized_name not in unique_skills:
                    unique_skills[normalized_name] = skill
                else:
                    # Keep whichever duplicate has the higher proficiency
                    if (
                        skill.proficiency_level
                        > unique_skills[normalized_name].proficiency_level
                    ):
                        unique_skills[normalized_name] = skill

            user_info.skills = list(unique_skills.values())

            unique_socials = {}
            for s in user_info.socials:
                unique_socials[s.platform.lower()] = s

            user_info.socials = list(unique_socials.values())

            for s in user_info.socials:
                if s.url and not s.url.startswith("http"):
                    s.url = "https://" + s.url

            skill_ranking.info = user_info.model_dump()
            skill_ranking.done_processing = True

        session.commit()


def parse_resume(
    filename: str, engine: sqlalchemy.engine.Engine | None = None
) -> UserInfo | None:

    # The handle is closed before the file is deleted later; Windows refuses to delete an open file.
    with open(filename, "rb") as resume_file:
        uploaded = client.files.create(file=resume_file, purpose="assistants")
    try:
        response = _parse_uploaded_resume(uploaded.id)
    finally:
        _delete_openai_file(uploaded.id)

    user_info = response.output_parsed
    if user_info is None:
        return None
    resume_text = extract_resume_text(filename)
    if resume_text.strip():
        catalog = get_skill_catalog(engine) if engine is not None else []
        skills, discovered = detect_document_skills(
            resume_text, catalog, document_type="resume"
        )
        if engine is not None:
            persist_discovered_skills(engine, discovered)
        user_info.skills = skills + [
            SkillRanking(
                skill_name=skill.skill_name,
                proficiency_level=skill.proficiency_level,
            )
            for skill in discovered
        ]
    return user_info


def _parse_uploaded_resume(file_id: str):
    return client.responses.parse(
        model="gpt-5.2",
        instructions="""You are an HR manager who is an expert in reading and parsing resumes.
        First, extract the applicant's contact information: their full name, email address, phone number, and location (city/state or region), as listed on the resume.
        Then, determine the user's employment history, project experience, education, and any linked social media presences.
        Extract and rank skills as before; when searchable document text is available, a separate skill detector will replace these results with catalog-constrained and newly discovered skills.
        If any piece of contact information is not present on the resume, leave it null rather than guessing.""",
        input=[
            {
                "role": "user",
                "content": [
                    {"type": "input_file", "file_id": file_id},
                ],
            }
        ],
        text_format=UserInfo,
    )


def clean_user_info(info: UserInfo) -> UserInfo:
    """Tidy a profile the user edited by hand before it is stored.

    Surrounding whitespace is trimmed, blank contact fields become null, entries
    left completely blank are dropped, skills are de-duplicated by name (the first
    one wins), and social links without a scheme get ``https://``.
    """

    def text(value: str | None) -> str | None:
        value = (value or "").strip()
        return value or None

    skills: dict[str, SkillRanking] = {}
    for skill in info.skills:
        name = skill.skill_name.strip()
        if name and name.lower() not in skills:
            skills[name.lower()] = SkillRanking(
                skill_name=name, proficiency_level=skill.proficiency_level
            )

    socials = []
    for social in info.socials:
        platform, url = social.platform.strip(), social.url.strip()
        if not url:
            continue
        if not url.lower().startswith(("http://", "https://")):
            url = "https://" + url
        socials.append(Social(platform=platform or url, url=url))

    return UserInfo(
        name=text(info.name),
        email=text(info.email),
        phone=text(info.phone),
        location=text(info.location),
        skills=list(skills.values()),
        education=[
            Education(school=e.school.strip(), degree=e.degree.strip())
            for e in info.education
            if e.school.strip() or e.degree.strip()
        ],
        projects=[p.strip() for p in info.projects if p.strip()],
        socials=socials,
        employment_history=[
            Employment(company_name=e.company_name.strip(), role=e.role.strip())
            for e in info.employment_history
            if e.company_name.strip() or e.role.strip()
        ],
    )

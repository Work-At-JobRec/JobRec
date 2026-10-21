"""Dynamic skill catalog and structured skill detection for resumes and listings."""

import logging
from enum import Enum
from pathlib import Path
from typing import cast

from openai import OpenAI
from pydantic import BaseModel, Field, create_model
from sqlalchemy import ForeignKey, Integer, String, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Mapped, Session, mapped_column

from jobrec.db import Base
from jobrec.job_store import JobListingTable

logger = logging.getLogger(__name__)


class SkillRanking(BaseModel):
    skill_name: str = Field(..., description="Canonical name of a skill")
    proficiency_level: int = Field(
        ...,
        ge=1,
        le=4,
        description="Proficiency or requirement level from 1 (basic) to 4 (expert)",
    )


class _CatalogSkillRanking(BaseModel):
    skill_name: str
    proficiency_level: int = Field(..., ge=1, le=4)


class _ConstrainedSkillResult(BaseModel):
    skills: list[_CatalogSkillRanking]


class DiscoveredSkill(BaseModel):
    skill_name: str = Field(..., description="Name of a genuinely new skill")
    proficiency_level: int = Field(
        ...,
        ge=1,
        le=4,
        description="Proficiency or requirement level from 1 (basic) to 4 (expert)",
    )


class UnconstrainedSkillResult(BaseModel):
    skills: list[DiscoveredSkill]


class CanonicalSkillTable(Base):
    __tablename__ = "canonical_skills"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    normalized_name: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False
    )
    skill_name: Mapped[str] = mapped_column(String(255), nullable=False)


class ListingSkillTable(Base):
    __tablename__ = "job_listing_skills"

    listing_id: Mapped[int] = mapped_column(
        ForeignKey("job_listings.id", ondelete="CASCADE"), primary_key=True
    )
    skill_id: Mapped[int] = mapped_column(
        ForeignKey("canonical_skills.id", ondelete="CASCADE"), primary_key=True
    )
    proficiency_level: Mapped[int] = mapped_column(Integer, nullable=False)


_client: OpenAI | None = None


def _openai_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI()
    return _client


def _normalized_name(name: str) -> str:
    return " ".join(name.strip().casefold().split())


def _constrained_result_model(
    catalog: list[str],
) -> type[_ConstrainedSkillResult] | None:
    """Build a response schema whose skill names are exactly the catalog entries."""
    names = tuple(dict.fromkeys(name for name in catalog if name.strip()))
    if not names:
        return None

    skill_name_type = Enum(
        "CatalogSkillName",
        {f"skill_{index}": name for index, name in enumerate(names)},
        type=str,
    )
    catalog_skill = create_model(
        "CatalogSkillRanking",
        skill_name=(
            skill_name_type,
            Field(..., description="A skill name selected from the current catalog"),
        ),
        proficiency_level=(
            int,
            Field(
                ...,
                ge=1,
                le=4,
                description="Proficiency or requirement level from 1 to 4",
            ),
        ),
    )
    result_model = create_model(
        "ConstrainedSkillResult",
        __base__=_ConstrainedSkillResult,
        skills=(list[catalog_skill], Field(...)),
    )
    return result_model


def initialize_skill_schema(engine: Engine) -> None:
    Base.metadata.create_all(engine)


def get_skill_catalog(engine: Engine) -> list[str]:
    initialize_skill_schema(engine)
    with Session(engine) as session:
        rows = session.scalars(
            select(CanonicalSkillTable).order_by(CanonicalSkillTable.skill_name)
        )
        return [row.skill_name for row in rows]


def persist_discovered_skills(engine: Engine, skills: list[DiscoveredSkill]) -> None:
    if not skills:
        return
    initialize_skill_schema(engine)
    with Session(engine) as session:
        existing = set(session.scalars(select(CanonicalSkillTable.normalized_name)))
        for skill in skills:
            normalized = _normalized_name(skill.skill_name)
            if normalized and normalized not in existing:
                session.add(
                    CanonicalSkillTable(
                        normalized_name=normalized, skill_name=skill.skill_name.strip()
                    )
                )
                existing.add(normalized)
        session.commit()


def detect_document_skills(
    document_text: str,
    catalog: list[str],
    *,
    document_type: str,
) -> tuple[list[SkillRanking], list[DiscoveredSkill]]:
    """Run catalog-constrained detection followed by discovery of missing skills."""
    if not document_text.strip():
        return [], []

    catalog_by_name = {_normalized_name(item): item for item in catalog}
    client = _openai_client()
    matched: dict[str, SkillRanking] = {}
    constrained_model = _constrained_result_model(catalog)
    if constrained_model is not None:
        constrained_response = client.responses.parse(
            model="gpt-5.2",
            instructions=(
                f"Identify skills explicitly evidenced or required by this {document_type}. "
                "Select only skills from the supplied canonical catalog. Do not infer a skill "
                "from a job title alone. For resumes, rate demonstrated proficiency: 1 is "
                "basic familiarity, 2 is extensive amateur experience, 3 is professional or "
                "academic experience, and 4 is proven long-term mastery. For listings, rate "
                "the required proficiency using the same scale. Return an empty list when none match."
            ),
            input=[
                {
                    "role": "user",
                    "content": (
                        f"Canonical skill catalog: {catalog!r}\n\n"
                        f"Document:\n{document_text}"
                    ),
                }
            ],
            text_format=constrained_model,
        )
        constrained = constrained_response.output_parsed
    else:
        constrained = None
    if constrained is not None:
        for skill in constrained.skills:
            skill_name = cast(str, getattr(skill.skill_name, "value", skill.skill_name))
            canonical = catalog_by_name.get(_normalized_name(skill_name))
            if canonical is None:
                continue
            normalized = _normalized_name(canonical)
            ranking = SkillRanking(
                skill_name=canonical,
                proficiency_level=skill.proficiency_level,
            )
            if (
                normalized not in matched
                or ranking.proficiency_level > matched[normalized].proficiency_level
            ):
                matched[normalized] = ranking

    unconstrained = client.responses.parse(
        model="gpt-5.2",
        instructions=(
            f"Find skills genuinely evidenced or required by this {document_type} that are "
            "missing from the already matched skill list. Do not return any catalog skill, "
            "synonym, alternate spelling, or a narrower/broader version of an existing skill. "
            "Do not infer skills from a title alone. Include a concise broad category and rate "
            "proficiency/requirement from 1 (basic) to 4 (expert). Return an empty list if none."
        ),
        input=[
            {
                "role": "user",
                "content": (
                    f"Already matched canonical skills: {list(matched.values())!r}\n\n"
                    f"Original document:\n{document_text}"
                ),
            }
        ],
        text_format=UnconstrainedSkillResult,
    ).output_parsed

    discovered: dict[str, DiscoveredSkill] = {}
    if unconstrained is not None:
        for skill in unconstrained.skills:
            normalized = _normalized_name(skill.skill_name)
            if not normalized or normalized in catalog_by_name or normalized in matched:
                continue
            ranking = discovered.get(normalized)
            if ranking is None or skill.proficiency_level > ranking.proficiency_level:
                discovered[normalized] = skill.model_copy(
                    update={"skill_name": " ".join(skill.skill_name.strip().split())}
                )

    return list(matched.values()), list(discovered.values())


def extract_resume_text(filename: str) -> str:
    """Extract searchable text locally so resume skills use the same detector as listings."""
    extension = Path(filename).suffix.lower()
    if extension == ".pdf":
        from pypdf import PdfReader

        return "\n".join(
            page.extract_text() or "" for page in PdfReader(filename).pages
        )
    if extension == ".docx":
        from docx import Document

        document = Document(filename)
        return "\n".join(paragraph.text for paragraph in document.paragraphs)
    return ""


def store_listing_skills(
    engine: Engine,
    skills_by_key: dict[str, list[SkillRanking]],
) -> None:
    if not skills_by_key:
        return
    initialize_skill_schema(engine)
    with Session(engine) as session:
        listings = {
            row.dedupe_key: row
            for row in session.scalars(
                select(JobListingTable).where(
                    JobListingTable.dedupe_key.in_(skills_by_key)
                )
            )
        }
        catalog = {
            row.normalized_name: row
            for row in session.scalars(select(CanonicalSkillTable))
        }
        for key, rankings in skills_by_key.items():
            listing = listings.get(key)
            if listing is None:
                continue
            session.query(ListingSkillTable).filter_by(listing_id=listing.id).delete()
            for ranking in rankings:
                skill = catalog.get(_normalized_name(ranking.skill_name))
                if skill is not None:
                    session.add(
                        ListingSkillTable(
                            listing_id=listing.id,
                            skill_id=skill.id,
                            proficiency_level=ranking.proficiency_level,
                        )
                    )
        session.commit()

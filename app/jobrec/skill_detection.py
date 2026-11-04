"""Dynamic skill catalog and structured skill detection for resumes and listings."""

import logging
import math
import re
from collections import Counter
from enum import Enum
from pathlib import Path
from typing import cast

from openai import OpenAI
from pydantic import BaseModel, Field, create_model
from sqlalchemy import ForeignKey, Integer, String, select, update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Mapped, Session, mapped_column

from jobrec.db import Base
from jobrec.job_store import JobListingTable, ensure_job_listing_schema

logger = logging.getLogger(__name__)

DEFAULT_SKILL_CANDIDATE_CAP = 100
_TOKEN_PATTERN = re.compile(r"\.net|c\+\+|c#|[a-z0-9]+", re.IGNORECASE)


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


def _search_tokens(text: str) -> list[str]:
    return [token.casefold() for token in _TOKEN_PATTERN.findall(text)]


def retrieve_skill_candidates(
    document_text: str, catalog: list[str], *, limit: int = DEFAULT_SKILL_CANDIDATE_CAP
) -> list[str]:
    """Rank catalog names against a document with BM25 and return the top matches."""
    if limit < 1:
        raise ValueError("limit must be at least 1")

    query_terms = set(_search_tokens(document_text))
    if not query_terms or not catalog:
        return []

    unique_names = list(dict.fromkeys(name for name in catalog if name.strip()))
    tokenized = [(name, _search_tokens(name)) for name in unique_names]
    document_frequency = Counter(
        token for _, tokens in tokenized for token in set(tokens)
    )
    average_length = (
        sum(len(tokens) for _, tokens in tokenized) / len(tokenized)
        if tokenized
        else 0.0
    )
    if not average_length:
        return []

    document_count = len(tokenized)
    k1 = 1.5
    b = 0.75
    scored: list[tuple[float, int, str]] = []
    for index, (name, tokens) in enumerate(tokenized):
        term_frequency = Counter(tokens)
        length_normalizer = k1 * (1 - b + b * len(tokens) / average_length)
        score = 0.0
        for term in query_terms.intersection(term_frequency):
            frequency = term_frequency[term]
            inverse_frequency = math.log(
                1
                + (document_count - document_frequency[term] + 0.5)
                / (document_frequency[term] + 0.5)
            )
            score += (
                inverse_frequency
                * frequency
                * (k1 + 1)
                / (frequency + length_normalizer)
            )
        if score:
            scored.append((score, index, name))

    scored.sort(key=lambda item: (-item[0], item[1]))
    return [name for _, _, name in scored[:limit]]


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
    ensure_job_listing_schema(engine)


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
        _persist_discovered_skills(session, skills)
        session.commit()


def _persist_discovered_skills(session: Session, skills: list[DiscoveredSkill]) -> None:
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


def detect_document_skills(
    document_text: str,
    catalog: list[str],
    *,
    document_type: str,
    candidate_cap: int = DEFAULT_SKILL_CANDIDATE_CAP,
) -> tuple[list[SkillRanking], list[DiscoveredSkill]]:
    """Detect catalog matches, then discover novel skills.

    A non-empty catalog requires two Responses API requests per document; an
    empty catalog skips the constrained request and requires one.
    """
    if not document_text.strip():
        return [], []
    if candidate_cap < 1:
        raise ValueError("candidate_cap must be at least 1")

    catalog_by_name = {_normalized_name(item): item for item in catalog}
    candidates = retrieve_skill_candidates(document_text, catalog, limit=candidate_cap)
    logger.info(
        "Skill candidate retrieval: %d of %d catalog entries (cap=%d)",
        len(candidates),
        len(catalog_by_name),
        candidate_cap,
    )
    client = _openai_client()
    matched: dict[str, SkillRanking] = {}
    constrained_model = _constrained_result_model(candidates)
    if constrained_model is not None:
        constrained_response = client.responses.parse(
            model="gpt-5.2",
            instructions=(
                f"Identify skills explicitly evidenced or required by this {document_type}. "
                "Select only skills from the supplied canonical catalog."
                "For resumes, rate demonstrated proficiency: 1 is "
                "basic familiarity, 2 is extensive amateur experience, 3 is professional or "
                "academic experience, and 4 is proven long-term mastery. For listings, rate "
                "the required proficiency using the same scale. Return an empty list when none match."
            ),
            input=[
                {
                    "role": "user",
                    "content": (f"Document:\n{document_text}"),
                }
            ],
            text_format=constrained_model,
        )
        if constrained_response.usage is not None:
            logger.info(
                f"constrained response used {constrained_response.usage.total_tokens} tokens"
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

    unconstrained_response = client.responses.parse(
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
    )

    unconstrained = unconstrained_response.output_parsed
    if unconstrained_response.usage is not None:
        logger.info(
            f"unconstrained response used {unconstrained_response.usage.total_tokens} tokens"
        )

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
        _store_listing_skills(session, skills_by_key)
        session.commit()


def _store_listing_skills(
    session: Session,
    skills_by_key: dict[str, list[SkillRanking]],
) -> None:
    listings = {
        row.dedupe_key: row
        for row in session.scalars(
            select(JobListingTable).where(JobListingTable.dedupe_key.in_(skills_by_key))
        )
    }
    catalog = {
        row.normalized_name: row for row in session.scalars(select(CanonicalSkillTable))
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


def save_listing_skill_analysis(
    engine: Engine,
    dedupe_key: str,
    description: str,
    matched: list[SkillRanking],
    discovered: list[DiscoveredSkill],
) -> bool:
    """Persist a result only if it still matches the listing's current description."""
    initialize_skill_schema(engine)
    with Session(engine) as session:
        listing = session.scalar(
            select(JobListingTable).where(
                JobListingTable.dedupe_key == dedupe_key,
                JobListingTable.skills_pending.is_(True),
            )
        )
        if listing is None or listing.description != description:
            return False

        _persist_discovered_skills(session, discovered)
        session.flush()
        updated = session.execute(
            update(JobListingTable)
            .where(
                JobListingTable.id == listing.id,
                JobListingTable.description == description,
                JobListingTable.skills_pending.is_(True),
            )
            .values(skills_pending=False)
        )
        if updated.rowcount != 1:
            session.rollback()
            return False

        rankings = matched + [
            SkillRanking(
                skill_name=skill.skill_name,
                proficiency_level=skill.proficiency_level,
            )
            for skill in discovered
        ]
        _store_listing_skills(session, {dedupe_key: rankings})
        session.commit()
        return True

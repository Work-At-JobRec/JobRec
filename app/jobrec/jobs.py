"""Job listings served to the frontend via /api/jobs.

Jobs are JobListing objects (see job_listing.py), the same model every scraper
produces. to_api_job() turns one into the JSON the Jobs pages render.

When the scraper has stored listings (see job_store.py), those are served: the
list returns the most recently posted ones with a short description, and the
detail returns one listing with its full description. The SAMPLE_LISTINGS below
are served only when no database is given or nothing is stored yet, so a fresh
checkout still shows something.

Salary comes from the listing's scraped pay, and job type is inferred from the
title. Compatibility combines exact skill matches with distance-weighted skill
graph matches.
"""

import heapq
import logging
import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from jobrec.job_listing import JobListing
from jobrec.job_store import (
    count_listings,
    list_listings_by_ids,
    list_recent_listings,
)

logger = logging.getLogger(__name__)

# Bounds for results and descriptions in the listings API.
DEFAULT_JOB_LIMIT = 500
MAX_JOB_LIMIT = 1000
# Length of the description sent with each job in the list; the detail route sends it in full.
LIST_DESCRIPTION_CHARS = 300
# Characters that would break the frontend's /jobs/<id> route if they appeared in an id.
_UNSAFE_ID_CHARS = ("/", "?", "#")

# Job type as the frontend's filters name it, inferred from words in the title.
_JOB_TYPE_PATTERNS = (
    (
        "Internship",
        re.compile(
            r"\b(intern|interns|internship|internships|co-?op)\b", re.IGNORECASE
        ),
    ),
    ("Part Time", re.compile(r"\bpart[- ]time\b", re.IGNORECASE)),
    ("Contract", re.compile(r"\b(contract|contractor)\b", re.IGNORECASE)),
)
from jobrec.job_store import JobListingTable, to_job_listing
from jobrec.openaiapi import UserInfoTable
from jobrec.skill_detection import (
    CanonicalSkillTable,
    ListingSkillTable,
    SkillConnectionTable,
)

MAX_JOB_RESULTS = 5
MAX_PAGE_SIZE = 50
_ANNUAL_MULTIPLIERS = {
    "year": 1,
    "annual": 1,
    "month": 12,
    "week": 52,
    "hour": 2080,
}
_SALARY_AMOUNT = re.compile(r"(?<![\w.])(\d[\d,]*(?:\.\d+)?)\s*(k)?", re.IGNORECASE)

_now = datetime.now(timezone.utc)

SAMPLE_LISTINGS = [
    JobListing(
        title="Software Engineer",
        company_name="ACME Corporation",
        location="West Lafayette, IN",
        description="Design and implement software for our internal use",
        source="sample",
        application_url="https://example.com/jobs/1",
        posted_at=_now - timedelta(days=1),
        source_job_id="1",
    ),
    JobListing(
        title="Data Scientist",
        company_name="ACME Corporation",
        location="West Lafayette, IN",
        description="Build models and dashboards that turn our data into decisions",
        source="sample",
        application_url="https://example.com/jobs/2",
        posted_at=_now - timedelta(days=4),
        source_job_id="2",
    ),
    JobListing(
        title="Designer",
        company_name="ACME Corporation",
        location="West Lafayette, IN",
        description="Design clear, friendly interfaces for our customer-facing apps",
        source="sample",
        application_url="https://example.com/jobs/3",
        source_job_id="3",
    ),
]

# Placeholder values for fields JobListing doesn't have, keyed by job id.
# Each requirement renders as "<text> <skill> ✓/✗"; `met` says whether the
# user's profile has the skill.
SAMPLE_MATCHES = {
    "sample-1": {
        "jobType": "Full Time",
        "salary": "100k/yr",
        "compatibility": 99,
        "requirements": [
            {"text": "Bachelors degree in", "skill": "computer science", "met": True},
            {"text": "Ability to work with", "skill": "Python", "met": True},
            {
                "text": "Experience with the",
                "skill": "Microsoft Office Suite",
                "met": False,
            },
        ],
    },
    "sample-2": {
        "jobType": "Part Time",
        "salary": "60k/yr",
        "compatibility": 70,
        "requirements": [
            {"text": "Bachelors degree in", "skill": "statistics", "met": False},
            {"text": "Ability to work with", "skill": "Python", "met": True},
            {"text": "Experience with", "skill": "SQL", "met": True},
        ],
    },
    "sample-3": {
        "jobType": "Full Time",
        "salary": "60k/yr",
        "compatibility": 20,
        "requirements": [
            {"text": "Portfolio of work in", "skill": "UI/UX design", "met": False},
            {"text": "Experience with", "skill": "Figma", "met": False},
            {"text": "Ability to work with", "skill": "HTML/CSS", "met": True},
        ],
    },
}


def _store_has_listings(engine):
    return engine is not None and count_listings(engine) > 0


def get_job_listings(engine=None, limit=None, summary=True, offset=0):
    """Return the listings to show: stored ones (newest first, short descriptions), else the samples."""
    limit = max(1, min(DEFAULT_JOB_LIMIT if limit is None else limit, MAX_JOB_LIMIT))
    offset = max(0, offset)
    if not _store_has_listings(engine):
        if engine is not None:
            logger.warning(
                "No stored job listings found; serving the sample listings instead"
            )
        return SAMPLE_LISTINGS[offset : offset + limit]
    listings = list_recent_listings(
        engine,
        limit,
        description_chars=LIST_DESCRIPTION_CHARS if summary else None,
        offset=offset,
    )
    return [
        listing
        for listing in listings
        if not any(ch in listing.source_job_id for ch in _UNSAFE_ID_CHARS)
    ]


def infer_job_type(title):
    """Job type for the frontend's filters ("Internship", "Part Time", "Contract", "Full Time"), from the title.

    Whole words only, so "Internal Tools Engineer" is not mistaken for an internship.
    """
    for job_type, pattern in _JOB_TYPE_PATTERNS:
        if pattern.search(title or ""):
            return job_type
    return "Full Time"


def first_pay_range(pay):
    """The first range of a scraped pay line (ranges are joined with ";"), or None when there is no pay."""
    if not pay:
        return None
    return pay.split(";")[0].strip() or None


def job_id(listing):
    """Id used in /jobs/<id>; includes the source so ids from different scrapers can't collide."""
    return f"{listing.source}-{listing.source_job_id}"


def posted_ago(posted_at):
    """Human-readable age of a posting, e.g. "Today", "1 Day Ago", "4 Days Ago"."""
    if posted_at is None:
        return None
    days = (datetime.now(timezone.utc) - posted_at).days
    if days <= 0:
        return "Today"
    return f"{days} Day{'' if days == 1 else 's'} Ago"


def to_api_job(listing: JobListing, summary=False) -> dict[str, object]:
    """Convert a JobListing into the dict the frontend renders.

    With ``summary`` set (the list), a description that was cut short ends in an ellipsis.
    """
    id_ = job_id(listing)
    match = SAMPLE_MATCHES.get(id_, {})
    description = listing.description
    if summary and len(description) >= LIST_DESCRIPTION_CHARS:
        description = description[:LIST_DESCRIPTION_CHARS].rstrip() + "…"
    return {
        "id": id_,
        "title": listing.title,
        "company": listing.company_name,
        "location": listing.location,
        "description": description,
        "applicationUrl": listing.application_url,
        "postedAgo": posted_ago(listing.posted_at),
        "jobType": match.get("jobType") or infer_job_type(listing.title),
        "salary": match.get("salary") or first_pay_range(listing.pay),
        "compatibility": match.get("compatibility"),
        "requirements": match.get("requirements", []),
    }


def _normalized_skill_name(name: str) -> str:
    return " ".join(name.casefold().split())


def _annual_salary(salary: str | None) -> float | None:
    if not salary:
        return None
    amounts = [
        float(value.replace(",", "")) * (1000 if thousands else 1)
        for value, thousands in _SALARY_AMOUNT.findall(salary)
    ]
    if not amounts:
        return None
    text = salary.casefold()
    period = next(
        (name for name in ("hour", "week", "month", "annual", "year") if name in text),
        "year",
    )
    return (sum(amounts) / len(amounts)) * _ANNUAL_MULTIPLIERS[period]


def _salary_score(salary: str | None, desired_salary: float | None) -> float:
    offered = _annual_salary(salary)
    if offered is None:
        return 0.25
    if desired_salary is None:
        return 1.0
    return min(offered / desired_salary, 2.0)


def _profile_skills(session: Session, user_id: str) -> dict[str, int]:
    user = session.get(UserInfoTable, user_id)
    info = user.info if user is not None and isinstance(user.info, dict) else {}
    skills: dict[str, int] = {}
    for skill in info.get("skills", []):
        if not isinstance(skill, dict) or not isinstance(skill.get("skill_name"), str):
            continue
        try:
            proficiency = int(skill.get("proficiency_level"))
        except (TypeError, ValueError):
            continue
        if 1 <= proficiency <= 4:
            name = _normalized_skill_name(skill["skill_name"])
            skills[name] = max(skills.get(name, 0), proficiency)
    return skills


def _skill_credits(
    session: Session, applicant_skills: dict[str, int]
) -> dict[int, float]:
    """Return proficiency-adjusted credit from each skill's nearest applicant skill."""
    if not applicant_skills:
        return {}
    root_rows = list(
        session.execute(
            select(CanonicalSkillTable.id, CanonicalSkillTable.normalized_name)
            .where(CanonicalSkillTable.normalized_name.in_(applicant_skills))
        )
    )
    if not root_rows:
        return {}

    adjacency: dict[int, list[tuple[int, float]]] = {}
    for skill_a_id, skill_b_id, distance in session.execute(
        select(
            SkillConnectionTable.skill_a_id,
            SkillConnectionTable.skill_b_id,
            SkillConnectionTable.distance,
        )
    ):
        adjacency.setdefault(skill_a_id, []).append((skill_b_id, distance))
        adjacency.setdefault(skill_b_id, []).append((skill_a_id, distance))

    root_proficiency: dict[int, int] = {}
    for skill_id, normalized_name in root_rows:
        root_proficiency[skill_id] = max(
            root_proficiency.get(skill_id, 0), applicant_skills[normalized_name]
        )

    closest: dict[int, tuple[float, int]] = {
        skill_id: (0.0, proficiency)
        for skill_id, proficiency in root_proficiency.items()
    }
    pending = [
        (0.0, -proficiency, skill_id)
        for skill_id, proficiency in root_proficiency.items()
    ]
    heapq.heapify(pending)
    while pending:
        distance, negative_proficiency, skill_id = heapq.heappop(pending)
        proficiency = -negative_proficiency
        if closest.get(skill_id) != (distance, proficiency):
            continue
        for neighbor_id, edge_distance in adjacency.get(skill_id, ()):
            next_distance = distance + edge_distance
            previous = closest.get(neighbor_id)
            if previous is None or next_distance < previous[0] or (
                next_distance == previous[0] and proficiency > previous[1]
            ):
                closest[neighbor_id] = (next_distance, proficiency)
                heapq.heappush(
                    pending, (next_distance, -proficiency, neighbor_id)
                )

    credits = {
        skill_id: proficiency / 4 / (1 + distance)
        for skill_id, (distance, proficiency) in closest.items()
    }
    return credits


def _listing_requirements(
    session: Session, listing_id: int
) -> list[tuple[int, str, int]]:
    return list(
        session.execute(
            select(
                ListingSkillTable.skill_id,
                CanonicalSkillTable.skill_name,
                ListingSkillTable.proficiency_level,
            )
            .join(
                CanonicalSkillTable,
                CanonicalSkillTable.id == ListingSkillTable.skill_id,
            )
            .where(ListingSkillTable.listing_id == listing_id)
        )
    )


def _compatibility(
    requirements: list[tuple[int, str, int]],
    applicant_skills: dict[str, int],
    graph_credits: dict[int, float],
) -> tuple[float, list[dict[str, object]]]:
    denominator = sum(required / 4 for _, _, required in requirements)
    numerator = 0.0
    displayed_requirements: list[dict[str, object]] = []
    for skill_id, name, required in requirements:
        exact_credit = (
            applicant_skills.get(_normalized_skill_name(name), 0) / 4
        )
        credit = max(exact_credit, graph_credits.get(skill_id, 0.0))
        numerator += (required / 4) * credit
        displayed_requirements.append(
            {
                "text": f"Requires proficiency level {required}/4",
                "skill": name,
                "met": credit >= required / 4,
            }
        )
    return (numerator / denominator if denominator else 0.0), displayed_requirements


def _ranked_jobs(
    engine: Engine,
    user_id: str,
    desired_salary: float | None,
    location: str | None,
    page: int = 1,
    page_size: int = MAX_JOB_RESULTS,
) -> list[dict[str, object]]:
    _validate_pagination(page, page_size)
    location_query = (location or "").split(",", 1)[0].strip().casefold()
    listing_filter = [JobListingTable.status == "open"]
    if location_query:
        listing_filter.append(
            func.lower(func.coalesce(JobListingTable.location, "")).contains(
                location_query, autoescape=True
            )
        )

    with Session(engine) as session:
        applicant_skills = _profile_skills(session, user_id)
        graph_credits = _skill_credits(session, applicant_skills)
        listing_rows = list(
            session.execute(
                select(
                    JobListingTable.id,
                    JobListingTable.source,
                    JobListingTable.source_job_id,
                    JobListingTable.title,
                    JobListingTable.company_name,
                    JobListingTable.location,
                    JobListingTable.application_url,
                    JobListingTable.posted_at,
                    JobListingTable.pay,
                )
                .where(*listing_filter)
                .order_by(JobListingTable.id)
            )
        )
        if not listing_rows:
            return []

        skill_rows = session.execute(
            select(
                ListingSkillTable.listing_id,
                ListingSkillTable.skill_id,
                CanonicalSkillTable.skill_name,
                ListingSkillTable.proficiency_level,
            )
            .join(
                JobListingTable,
                JobListingTable.id == ListingSkillTable.listing_id,
            )
            .join(
                CanonicalSkillTable,
                CanonicalSkillTable.id == ListingSkillTable.skill_id,
            )
            .where(*listing_filter)
        )
        requirements_by_listing: dict[int, list[tuple[int, str, int]]] = {}
        for listing_id, skill_id, skill_name, proficiency in skill_rows:
            requirements_by_listing.setdefault(listing_id, []).append(
                (skill_id, skill_name, proficiency)
            )

        ranked: list[tuple[float, int, float, list[tuple[int, str, int]]]] = []
        for row in listing_rows:
            if row.source_job_id and any(
                character in row.source_job_id for character in _UNSAFE_ID_CHARS
            ):
                continue
            requirements = requirements_by_listing.get(row.id, [])
            compatibility, _ = _compatibility(
                requirements, applicant_skills, graph_credits
            )
            if desired_salary is None:
                search_index = compatibility
            else:
                salary_score = _salary_score(row.pay, desired_salary)
                search_index = 0.7 * compatibility + 0.3 * salary_score
            ranked.append((search_index, row.id, compatibility, requirements))

        page_end = page * page_size
        page_start = page_end - page_size
        selected = heapq.nsmallest(
            page_end, ranked, key=lambda item: (-item[0], item[1])
        )[page_start:page_end]
        if not selected:
            return []

        listings = list_listings_by_ids(
            engine,
            [listing_id for _, listing_id, _, _ in selected],
            description_chars=LIST_DESCRIPTION_CHARS,
        )
        listing_by_id = {
            listing_id: listing
            for (_, listing_id, _, _), listing in zip(selected, listings)
        }
        jobs: list[dict[str, object]] = []
        for _, listing_id, compatibility, requirements in selected:
            listing = listing_by_id.get(listing_id)
            if listing is None:
                continue
            job = to_api_job(listing, summary=True)
            job["id"] = f"{listing.source}-{listing.source_job_id or listing_id}"
            job["salary"] = listing.pay
            job["compatibility"] = round(compatibility * 100)
            job["requirements"] = _compatibility(
                requirements, applicant_skills, graph_credits
            )[1]
            jobs.append(job)
        return jobs


def _validate_pagination(page: int, page_size: int) -> None:
    if page < 1:
        raise ValueError("page must be at least 1")
    if page_size < 1 or page_size > MAX_PAGE_SIZE:
        raise ValueError(f"page_size must be between 1 and {MAX_PAGE_SIZE}")


def get_jobs(
    engine: Engine | None = None,
    user_id: str | None = None,
    desired_salary: float | None = None,
    location: str | None = None,
    limit: int | None = None,
    page: int = 1,
    page_size: int = MAX_JOB_RESULTS,
) -> list[dict[str, object]]:
    _validate_pagination(page, page_size)
    offset = (page - 1) * page_size
    if engine is None:
        return [
            to_api_job(listing, summary=True)
            for listing in get_job_listings(summary=True)[offset : offset + page_size]
        ]
    if user_id is None:
        listing_limit = (
            page_size if limit is None else min(limit, page_size, MAX_PAGE_SIZE)
        )
        listing_limit = max(1, listing_limit)
        return [
            to_api_job(listing, summary=True)
            for listing in get_job_listings(
                engine, listing_limit, summary=True, offset=offset
            )
        ]
    return _ranked_jobs(
        engine, user_id, desired_salary, location, page=page, page_size=page_size
    )


def get_job(
    id_: str,
    engine: Engine | None = None,
    user_id: str | None = None,
    desired_salary: float | None = None,
) -> dict[str, object] | None:
    """Return a single job by id without loading other listing descriptions."""
    if engine is None or not _store_has_listings(engine):
        return next(
            (
                to_api_job(listing)
                for listing in SAMPLE_LISTINGS
                if to_api_job(listing)["id"] == id_
            ),
            None,
        )

    source, separator, source_job_id = id_.partition("-")
    if not separator or not source or not source_job_id:
        return None
    if any(character in source_job_id for character in _UNSAFE_ID_CHARS):
        return None

    with Session(engine) as session:
        row = session.scalar(
            select(JobListingTable).where(
                JobListingTable.source == source,
                JobListingTable.source_job_id == source_job_id,
            )
        )
        if row is None and user_id is not None and source_job_id.isdecimal():
            row = session.get(JobListingTable, int(source_job_id))
            if row is not None and row.source != source:
                row = None
        if row is None or (user_id is not None and row.status != "open"):
            return None

        listing = to_job_listing(row)
        job = to_api_job(listing)
        if user_id is None:
            return job

        applicant_skills = _profile_skills(session, user_id)
        graph_credits = _skill_credits(session, applicant_skills)
        requirements = _listing_requirements(session, row.id)
        compatibility, displayed_requirements = _compatibility(
            requirements, applicant_skills, graph_credits
        )
        job["id"] = f"{listing.source}-{listing.source_job_id or row.id}"
        job["salary"] = listing.pay
        job["compatibility"] = round(compatibility * 100)
        job["requirements"] = displayed_requirements
        return job

"""Job listings served to the frontend via /api/jobs.

Jobs are JobListing objects (see job_listing.py), the same model every scraper
produces. to_api_job() turns one into the JSON the Jobs pages render.

When the scraper has stored listings (see job_store.py), those are served: the
list returns the most recently posted ones with a short description, and the
detail returns one listing with its full description. The SAMPLE_LISTINGS below
are served only when no database is given or nothing is stored yet, so a fresh
checkout still shows something.

Salary comes from the listing's scraped pay, and job type is inferred from the
title. Compatibility and requirement matches will come from the matching
algorithm; until then they are empty for real listings (the samples keep their
placeholders in SAMPLE_MATCHES).
"""

import logging
import re
from datetime import datetime, timedelta, timezone
import re

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from jobrec.job_listing import JobListing
from jobrec.job_store import count_listings, get_listing, list_recent_listings

logger = logging.getLogger(__name__)

# How many listings /api/jobs returns unless asked otherwise, and the most it will return.
# The frontend loads the whole list at once, so this bounds the response size.
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
from jobrec.skill_detection import CanonicalSkillTable, ListingSkillTable

MAX_JOB_RESULTS = 5
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


def get_job_listings(engine=None, limit=None, summary=True):
    """Return the listings to show: stored ones (newest first, short descriptions), else the samples."""
    if not _store_has_listings(engine):
        if engine is not None:
            logger.warning(
                "No stored job listings found; serving the sample listings instead"
            )
        return SAMPLE_LISTINGS
    limit = max(1, min(DEFAULT_JOB_LIMIT if limit is None else limit, MAX_JOB_LIMIT))
    listings = list_recent_listings(
        engine, limit, description_chars=LIST_DESCRIPTION_CHARS if summary else None
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


def _ranked_jobs(
    engine: Engine,
    user_id: str,
    desired_salary: float | None,
    location: str | None,
) -> list[dict[str, object]]:
    with Session(engine) as session:
        applicant_skills = _profile_skills(session, user_id)
        listing_rows = list(
            session.scalars(
                select(JobListingTable)
                .where(JobListingTable.status == "open")
                .order_by(JobListingTable.id)
            )
        )
        if not listing_rows:
            return []

        listing_ids = [row.id for row in listing_rows]
        skill_rows = session.execute(
            select(
                ListingSkillTable.listing_id,
                CanonicalSkillTable.skill_name,
                ListingSkillTable.proficiency_level,
            )
            .join(
                CanonicalSkillTable,
                CanonicalSkillTable.id == ListingSkillTable.skill_id,
            )
            .where(ListingSkillTable.listing_id.in_(listing_ids))
        )
        requirements_by_listing: dict[int, list[tuple[str, int]]] = {}
        for listing_id, skill_name, proficiency in skill_rows:
            requirements_by_listing.setdefault(listing_id, []).append(
                (skill_name, proficiency)
            )

        location_query = (location or "").split(",", 1)[0].strip().casefold()
        ranked: list[tuple[float, int, dict[str, object]]] = []
        for row in listing_rows:
            listing = to_job_listing(row)
            if (
                location_query
                and location_query not in (listing.location or "").casefold()
            ):
                continue

            requirements = requirements_by_listing.get(row.id, [])
            denominator = sum(required / 4 for _, required in requirements)
            numerator = sum(
                (required / 4)
                * (applicant_skills.get(_normalized_skill_name(name), 0) / 4)
                for name, required in requirements
            )
            compatibility = numerator / denominator if denominator else 0.0
            salary_score = _salary_score(listing.pay, desired_salary)
            search_index = 0.7 * compatibility + 0.3 * salary_score
            displayed_requirements = [
                {
                    "text": f"Requires proficiency level {required}/4",
                    "skill": name,
                    "met": applicant_skills.get(_normalized_skill_name(name), 0)
                    >= required,
                }
                for name, required in requirements
            ]
            job = to_api_job(listing)
            job["id"] = f"{listing.source}-{listing.source_job_id or row.id}"
            job["salary"] = listing.pay
            job["compatibility"] = round(compatibility * 100)
            job["requirements"] = displayed_requirements
            ranked.append((search_index, row.id, job))

        ranked.sort(key=lambda item: (-item[0], item[1]))
        return [job for _, _, job in ranked]


def get_jobs(
    engine: Engine | None = None,
    user_id: str | None = None,
    desired_salary: float | None = None,
    location: str | None = None,
    limit: int | None = None,
) -> list[dict[str, object]]:
    if engine is None:
        return [to_api_job(listing, summary=True) for listing in get_job_listings()][
            :MAX_JOB_RESULTS
        ]
    if user_id is None:
        return [
            to_api_job(listing, summary=True)
            for listing in get_job_listings(engine, limit)[:MAX_JOB_RESULTS]
        ]
    return _ranked_jobs(engine, user_id, desired_salary, location)[:MAX_JOB_RESULTS]


def get_job(
    id_: str,
    engine: Engine | None = None,
    user_id: str | None = None,
    desired_salary: float | None = None,
) -> dict[str, object] | None:
    """Return the job with the given id, or None if it doesn't exist."""
    if engine is None:
        jobs = [to_api_job(listing) for listing in get_job_listings(summary=False)]
    elif user_id is None:
        jobs = [
            to_api_job(listing) for listing in get_job_listings(engine, summary=False)
        ]
    else:
        jobs = _ranked_jobs(engine, user_id, desired_salary, None)
    return next((job for job in jobs if job["id"] == id_), None)

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
    ("Internship", re.compile(r"\b(intern|interns|internship|internships|co-?op)\b", re.IGNORECASE)),
    ("Part Time", re.compile(r"\bpart[- ]time\b", re.IGNORECASE)),
    ("Contract", re.compile(r"\b(contract|contractor)\b", re.IGNORECASE)),
)

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


def get_job_listings(engine=None, limit=None):
    """Return the listings to show: stored ones (newest first, short descriptions), else the samples."""
    if not _store_has_listings(engine):
        if engine is not None:
            logger.warning("No stored job listings found; serving the sample listings instead")
        return SAMPLE_LISTINGS
    limit = max(1, min(DEFAULT_JOB_LIMIT if limit is None else limit, MAX_JOB_LIMIT))
    listings = list_recent_listings(engine, limit, description_chars=LIST_DESCRIPTION_CHARS)
    return [listing for listing in listings if not any(ch in listing.source_job_id for ch in _UNSAFE_ID_CHARS)]


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


def to_api_job(listing, summary=False):
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


def get_jobs(engine=None, limit=None):
    """Return the jobs for the list pages."""
    return [to_api_job(listing, summary=True) for listing in get_job_listings(engine, limit)]


def get_job(id_, engine=None):
    """Return the job with the given id and its full description, or None if it doesn't exist."""
    if _store_has_listings(engine):
        # Ids are "<source>-<source job id>"; source names contain no hyphen, the job id may.
        source, _, source_job_id = (id_ or "").partition("-")
        if not source or not source_job_id:
            return None
        listing = get_listing(engine, source, source_job_id)
        return to_api_job(listing) if listing is not None else None
    return next((to_api_job(listing) for listing in SAMPLE_LISTINGS if job_id(listing) == id_), None)

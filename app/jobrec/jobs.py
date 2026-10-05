"""Job listings served to the frontend via /api/jobs.

Jobs are JobListing objects (see job_listing.py), the same model every scraper
produces. to_api_job() turns one into the JSON the Jobs pages render, so to show
real jobs, replace get_job_listings() with a read from the scraper's storage;
the frontend needs no changes.

Salary, job type, compatibility and requirement matches aren't part of
JobListing yet (compatibility and matches will come from the matching
algorithm), so they're placeholders in SAMPLE_MATCHES until then.
"""

from datetime import datetime, timedelta, timezone

from jobrec.job_listing import JobListing

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


def get_job_listings():
    """Return all job listings. Swap this out for the scraper's data source."""
    return SAMPLE_LISTINGS


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


def to_api_job(listing):
    """Convert a JobListing into the dict the frontend renders."""
    id_ = job_id(listing)
    match = SAMPLE_MATCHES.get(id_, {})
    return {
        "id": id_,
        "title": listing.title,
        "company": listing.company_name,
        "location": listing.location,
        "description": listing.description,
        "applicationUrl": listing.application_url,
        "postedAgo": posted_ago(listing.posted_at),
        "jobType": match.get("jobType"),
        "salary": match.get("salary"),
        "compatibility": match.get("compatibility"),
        "requirements": match.get("requirements", []),
    }


def get_jobs():
    return [to_api_job(listing) for listing in get_job_listings()]


def get_job(id_):
    """Return the job with the given id, or None if it doesn't exist."""
    return next((job for job in get_jobs() if job["id"] == id_), None)

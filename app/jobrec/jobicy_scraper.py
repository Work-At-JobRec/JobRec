"""Scraper for the Jobicy remote job board, which lists jobs from every company and industry.

The company scrapers (Greenhouse, Lever, Ashby, Workday) can only read one named
company's board, so they skew toward whichever companies are in the registry.
Jobicy's public API needs no key and returns jobs from all employers, newest first:
https://jobicy.com/api/v2/remote-jobs?count=100
It pages with a cursor (``nextCursor`` / ``hasMore``) and can be narrowed with an
``industry`` filter. The registry id is that industry, or ``all`` for no filter.

Two limits keep a run small: only jobs posted in the last ``max_age_days`` days are
read, and at most ``max_pages`` pages of ``page_size`` jobs are fetched. Jobicy asks
that it be credited and that applications go to the job URL it provides, which is
what ``application_url`` stores.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import requests

from jobrec.job_listing import JobListing
from jobrec.scraper_base import BaseScraper

JOBICY_JOBS_URL = "https://jobicy.com/api/v2/remote-jobs"

# Registry id meaning "every industry".
ALL_INDUSTRIES = "all"

DEFAULT_PAGE_SIZE = 100  # the most Jobicy returns per request
DEFAULT_MAX_PAGES = 2
DEFAULT_MAX_AGE_DAYS = 7

_PERIODS = {
    "yearly": "per year",
    "monthly": "per month",
    "weekly": "per week",
    "daily": "per day",
    "hourly": "per hour",
}


def parse_pub_date(value: Any) -> Optional[datetime]:
    """Convert Jobicy's ISO 8601 pubDate to an aware UTC datetime, or None."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def format_salary(job: dict) -> Optional[str]:
    """Turn Jobicy's salary fields into one line such as "USD 90,000-120,000 (per year)", or None."""
    try:
        low = int(job["salaryMin"])
        high = int(job["salaryMax"])
    except (KeyError, TypeError, ValueError):
        return None
    currency = str(job.get("salaryCurrency") or "").strip()
    amount = f"{currency} {low:,}-{high:,}".strip()
    period = _PERIODS.get(str(job.get("salaryPeriod") or "").lower(), "")
    return f"{amount} ({period})" if period else amount


class JobicyScraper(BaseScraper):
    source_name = "jobicy"

    def __init__(
        self,
        industry: str = ALL_INDUSTRIES,
        company_name: Optional[str] = None,
        session: Optional[requests.Session] = None,
        page_size: int = DEFAULT_PAGE_SIZE,
        max_pages: int = DEFAULT_MAX_PAGES,
        max_age_days: int = DEFAULT_MAX_AGE_DAYS,
        now: Optional[datetime] = None,
    ):
        super().__init__(session=session)
        self.industry = industry
        # Accepted so every registry entry builds the same way; each job names its own company.
        self.company_name = company_name
        self.page_size = page_size
        self.max_pages = max_pages
        self.max_age_days = max_age_days
        self.now = now

    def fetch_jobs(self) -> list[JobListing]:
        cutoff = (self.now or datetime.now(timezone.utc)) - timedelta(days=self.max_age_days)
        params: dict[str, Any] = {"count": self.page_size}
        if self.industry and self.industry != ALL_INDUSTRIES:
            params["industry"] = self.industry

        recent: list[dict] = []
        for _ in range(self.max_pages):
            data = self._get_json(JOBICY_JOBS_URL, params=dict(params))
            jobs = data.get("jobs") if isinstance(data, dict) else None
            jobs = [job for job in jobs or [] if isinstance(job, dict)]
            reached_cutoff = False
            for job in jobs:
                posted = parse_pub_date(job.get("pubDate"))
                # The feed is newest first, so the first old job ends the run.
                if posted is not None and posted < cutoff:
                    reached_cutoff = True
                    break
                recent.append(job)
            cursor = data.get("nextCursor") if isinstance(data, dict) else None
            if reached_cutoff or not jobs or not data.get("hasMore") or not cursor:
                break
            params["cursor"] = cursor
        return self._build_listings(recent, self._to_listing)

    def _to_listing(self, job: dict) -> JobListing:
        """Map one Jobicy job onto the standardized JobListing model."""
        geo = str(job.get("jobGeo") or "").strip()
        job_id = job.get("id")
        return JobListing(
            title=job.get("jobTitle") or "",
            company_name=job.get("companyName") or "",
            location=f"Remote ({geo})" if geo else "Remote",
            description=job.get("jobDescription") or "",
            source=self.source_name,
            application_url=job.get("url") or "",
            posted_at=parse_pub_date(job.get("pubDate")),
            source_job_id=str(job_id) if job_id is not None else None,
            pay=format_salary(job),
            status="open",
        )

"""Scraper for company job boards hosted on Ashby.

Ashby exposes a public, unauthenticated job board API for every organization:
https://api.ashbyhq.com/posting-api/job-board/{organization}?includeCompensation=true
The response is JSON, so no HTML parsing is needed. Each job is converted into
a standardized JobListing; optional fields that Ashby omits are left empty. A
job the board no longer lists is reported as closed.
"""

from typing import Any, Optional

import requests

from jobrec.greenhouse_scraper import parse_iso8601
from jobrec.job_listing import JobListing
from jobrec.scraper_base import BaseScraper

ASHBY_JOB_BOARD_URL = "https://api.ashbyhq.com/posting-api/job-board/{organization}"

# Ashby's pay intervals, in the words the other scrapers use.
_INTERVALS = {
    "1 YEAR": "per year",
    "1 MONTH": "per month",
    "1 WEEK": "per week",
    "1 DAY": "per day",
    "1 HOUR": "per hour",
}


def format_compensation(compensation: Any) -> Optional[str]:
    """Turn Ashby's compensation object into one readable line, or None when no pay is published.

    The structured salary component is preferred, giving the same form the other scrapers
    produce ("USD 211,400-290,600 (per year)"). When there is none, Ashby's own summary
    text ("$60 - $75 per hour") is used as it is.
    """
    if not isinstance(compensation, dict):
        return None
    for component in compensation.get("summaryComponents") or []:
        if not isinstance(component, dict) or component.get("compensationType") != "Salary":
            continue
        try:
            low = int(component["minValue"])
            high = int(component["maxValue"])
        except (KeyError, TypeError, ValueError):
            continue
        currency = str(component.get("currencyCode") or "").strip()
        amount = f"{currency} {low:,}-{high:,}".strip()
        interval = _INTERVALS.get(str(component.get("interval") or ""), "")
        return f"{amount} ({interval})" if interval else amount
    summary = compensation.get("scrapeableCompensationSalarySummary")
    return summary.strip() if isinstance(summary, str) and summary.strip() else None


class AshbyScraper(BaseScraper):
    source_name = "ashby"

    def __init__(
        self,
        organization: str,
        company_name: Optional[str] = None,
        session: Optional[requests.Session] = None,
    ):
        super().__init__(session=session)
        # The organization slug from its Ashby URL (e.g. "ramp" in jobs.ashbyhq.com/ramp).
        self.organization = organization
        # Ashby's API does not include a company name, so use the one given or fall back to the slug.
        self.company_name = company_name

    def fetch_jobs(self) -> list[JobListing]:
        url = ASHBY_JOB_BOARD_URL.format(organization=self.organization)
        data = self._get_json(url, params={"includeCompensation": "true"})
        jobs = (data.get("jobs") or []) if isinstance(data, dict) else []
        return self._build_listings(jobs, self._to_listing)

    def _to_listing(self, job: dict) -> JobListing:
        """Map one Ashby job onto the standardized JobListing model."""
        job_id = job.get("id")
        return JobListing(
            title=job.get("title") or "",
            company_name=self.company_name or self.organization,
            location=job.get("location") or None,
            description=job.get("descriptionHtml") or job.get("descriptionPlain") or "",
            source=self.source_name,
            application_url=job.get("jobUrl") or job.get("applyUrl") or "",
            posted_at=parse_iso8601(job.get("publishedAt")),
            source_job_id=str(job_id) if job_id is not None else None,
            pay=format_compensation(job.get("compensation")),
            status="closed" if job.get("isListed") is False else "open",
        )

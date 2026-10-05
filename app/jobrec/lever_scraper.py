"""Scraper for company job boards hosted on Lever.

Lever exposes a public, unauthenticated postings API for every company:
https://api.lever.co/v0/postings/{company}?mode=json
The response is a JSON list of postings, so no HTML parsing is needed. Each
posting is converted into a standardized JobListing; optional fields that
Lever omits are left empty. Lever only serves open postings, so every listing
is reported as open.
"""

from datetime import datetime, timezone
from typing import Any, Optional

import requests

from app.jobrec.job_listing import JobListing
from app.jobrec.scraper_base import BaseScraper

LEVER_POSTINGS_URL = "https://api.lever.co/v0/postings/{company}"

# Lever's salary interval codes, in the words a reader expects.
_INTERVALS = {
    "per-year-salary": "per year",
    "per-month-salary": "per month",
    "per-week-salary": "per week",
    "per-day-wage": "per day",
    "per-hour-wage": "per hour",
}


def parse_epoch_millis(value: Any) -> Optional[datetime]:
    """Convert a Lever timestamp (milliseconds since the epoch) to an aware UTC datetime, or None."""
    try:
        return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc)
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def format_salary_range(salary: Any) -> Optional[str]:
    """Turn a Lever salaryRange into one readable line such as "USD 90,000-120,000 (per year)", or None."""
    if not isinstance(salary, dict):
        return None
    try:
        low = int(salary["min"])
        high = int(salary["max"])
    except (KeyError, TypeError, ValueError):
        return None
    currency = str(salary.get("currency") or "").strip()
    amount = f"{currency} {low:,}-{high:,}".strip()
    interval = _INTERVALS.get(str(salary.get("interval") or ""), "")
    return f"{amount} ({interval})" if interval else amount


class LeverScraper(BaseScraper):
    source_name = "lever"

    def __init__(
        self,
        company: str,
        company_name: Optional[str] = None,
        session: Optional[requests.Session] = None,
    ):
        super().__init__(session=session)
        # The company slug from its Lever URL (e.g. "palantir" in jobs.lever.co/palantir).
        self.company = company
        # Lever's API does not include a company name, so use the one given or fall back to the slug.
        self.company_name = company_name

    def fetch_jobs(self) -> list[JobListing]:
        url = LEVER_POSTINGS_URL.format(company=self.company)
        data = self._get_json(url, params={"mode": "json"})
        postings = data if isinstance(data, list) else []
        return self._build_listings(postings, self._to_listing)

    @staticmethod
    def _description(posting: dict) -> str:
        """Join the opening text, each titled list section, and the closing text into one HTML document."""
        parts = [posting.get("description") or ""]
        for section in posting.get("lists") or []:
            if isinstance(section, dict):
                heading = section.get("text") or ""
                parts.append(
                    f"<h3>{heading}</h3><ul>{section.get('content') or ''}</ul>"
                )
        parts.append(posting.get("additional") or "")
        return "\n".join(part for part in parts if part)

    def _to_listing(self, posting: dict) -> JobListing:
        """Map one Lever posting onto the standardized JobListing model."""
        categories = posting.get("categories") or {}
        job_id = posting.get("id")
        return JobListing(
            title=posting.get("text") or "",
            company_name=self.company_name or self.company,
            location=categories.get("location") or None,
            description=self._description(posting),
            source=self.source_name,
            application_url=posting.get("hostedUrl") or posting.get("applyUrl") or "",
            posted_at=parse_epoch_millis(posting.get("createdAt")),
            source_job_id=str(job_id) if job_id is not None else None,
            pay=format_salary_range(posting.get("salaryRange")),
            status="open",
        )

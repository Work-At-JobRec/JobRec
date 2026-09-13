"""Scraper for company job boards hosted on Greenhouse.

Greenhouse exposes a public, unauthenticated Job Board API for every board:
https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true
The response is JSON, so no HTML parsing is needed. Each job is converted into
a standardized JobListing; optional fields that Greenhouse omits are left empty.
"""

import html
from datetime import datetime
from typing import Optional

import requests

from job_listing import JobListing
from scraper_base import BaseScraper

GREENHOUSE_JOBS_URL = "https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs"


def parse_iso8601(value: Optional[str]) -> Optional[datetime]:
    """Parse a Greenhouse timestamp, returning None if it is missing or malformed.

    Greenhouse uses either an explicit offset ("2026-09-03T13:30:34-04:00") or a
    trailing "Z". Python 3.10's fromisoformat does not accept "Z", so it is
    rewritten as "+00:00" first.
    """
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


class GreenhouseScraper(BaseScraper):
    source_name = "greenhouse"

    def __init__(
        self,
        board_token: str,
        company_name: Optional[str] = None,
        session: Optional[requests.Session] = None,
    ):
        super().__init__(session=session)
        # The board token is the company's slug in its Greenhouse URL (e.g. "stripe").
        self.board_token = board_token
        # Optional human-readable company name; falls back to the API's value or the token.
        self.company_name = company_name

    def fetch_jobs(self) -> list[JobListing]:
        url = GREENHOUSE_JOBS_URL.format(board_token=self.board_token)
        data = self._get_json(url, params={"content": "true"})
        return [self._to_listing(job) for job in data.get("jobs", [])]

    def _to_listing(self, job: dict) -> JobListing:
        """Map one Greenhouse job object onto the standardized JobListing model."""
        location = job.get("location") or {}
        job_id = job.get("id")
        return JobListing(
            title=job.get("title") or "",
            company_name=self.company_name or job.get("company_name") or self.board_token,
            location=location.get("name"),
            # Greenhouse returns the description HTML-escaped (&lt;p&gt;); decode it to real HTML.
            description=html.unescape(job.get("content") or ""),
            source=self.source_name,
            application_url=job.get("absolute_url") or "",
            posted_at=parse_iso8601(job.get("first_published") or job.get("updated_at")),
            source_job_id=str(job_id) if job_id is not None else None,
        )

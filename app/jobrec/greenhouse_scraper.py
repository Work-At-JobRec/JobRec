"""Scraper for company job boards hosted on Greenhouse.

Greenhouse exposes a public, unauthenticated Job Board API for every board:
https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true
The response is JSON, so no HTML parsing is needed. Each job is converted into
a standardized JobListing; optional fields that Greenhouse omits are left empty.
"""

import html
from datetime import datetime, timezone
from typing import Any, Optional

import requests

from app.jobrec.job_listing import JobListing
from app.jobrec.scraper_base import BaseScraper

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


def format_pay_ranges(ranges: Any) -> Optional[str]:
    """Turn Greenhouse pay_input_ranges into one readable line, or None when nothing is published.

    Each range looks like {"min_cents": 16500000, "max_cents": 19000000, "currency_type": "USD",
    "title": "Annual Base Salary Range:"} and becomes "USD 165,000-190,000 (Annual Base Salary Range)".
    Entries that are not well-formed are skipped.
    """
    if not isinstance(ranges, list):
        return None
    parts = []
    for entry in ranges:
        if not isinstance(entry, dict):
            continue
        try:
            low = int(entry["min_cents"]) // 100
            high = int(entry["max_cents"]) // 100
        except (KeyError, TypeError, ValueError):
            continue
        currency = str(entry.get("currency_type") or "").strip()
        title = str(entry.get("title") or "").strip().rstrip(":").strip()
        amount = f"{currency} {low:,}-{high:,}".strip()
        parts.append(f"{amount} ({title})" if title else amount)
    return "; ".join(parts) or None


class GreenhouseScraper(BaseScraper):
    source_name = "greenhouse"

    def __init__(
        self,
        board_token: str,
        company_name: Optional[str] = None,
        session: Optional[requests.Session] = None,
        now: Optional[datetime] = None,
    ):
        super().__init__(session=session)
        # The board token is the company's slug in its Greenhouse URL (e.g. "stripe").
        self.board_token = board_token
        # Optional human-readable company name; falls back to the API's value or the token.
        self.company_name = company_name
        # The moment used to decide whether an application deadline has passed (injectable for tests).
        self.now = now

    def fetch_jobs(self) -> list[JobListing]:
        url = GREENHOUSE_JOBS_URL.format(board_token=self.board_token)
        # pay_transparency adds the pay_input_ranges field to each job.
        data = self._get_json(
            url, params={"content": "true", "pay_transparency": "true"}
        )
        return self._build_listings(data.get("jobs") or [], self._to_listing)

    def _status(self, job: dict) -> str:
        """Greenhouse has no status field, but a listing past its application deadline no longer accepts applicants."""
        deadline = parse_iso8601(job.get("application_deadline"))
        if deadline is None:
            return "open"
        now = self.now or datetime.now(timezone.utc)
        return "closed" if deadline < now else "open"

    def _to_listing(self, job: dict) -> JobListing:
        """Map one Greenhouse job object onto the standardized JobListing model."""
        location = job.get("location") or {}
        job_id = job.get("id")
        return JobListing(
            title=job.get("title") or "",
            company_name=self.company_name
            or job.get("company_name")
            or self.board_token,
            location=location.get("name"),
            # Greenhouse returns the description HTML-escaped (&lt;p&gt;); decode it to real HTML.
            description=html.unescape(job.get("content") or ""),
            source=self.source_name,
            application_url=job.get("absolute_url") or "",
            posted_at=parse_iso8601(
                job.get("first_published") or job.get("updated_at")
            ),
            source_job_id=str(job_id) if job_id is not None else None,
            pay=format_pay_ranges(job.get("pay_input_ranges")),
            status=self._status(job),
        )

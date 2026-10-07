"""Scraper for company careers sites hosted on Workday.

Workday careers pages load their listings from a JSON endpoint on the same host:
  POST https://{host}/wday/cxs/{tenant}/{site}/jobs  {"limit": 20, "offset": N, ...}
which returns a page of postings and the total count, and
  GET  https://{host}/wday/cxs/{tenant}/{site}{externalPath}
which returns one posting's details, including the HTML description. The
endpoint is undocumented but is what every Workday careers page itself uses.

A board is identified as "host/site", e.g.
"nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite"; the tenant is the
first label of the host. Because every posting costs one detail request, the
number of pages fetched is capped (5 pages of 20 by default).
"""

import logging
from datetime import datetime, timezone
from typing import Any, Optional

import requests

from jobrec.job_listing import JobListing
from jobrec.scraper_base import BaseScraper, ScraperRequestError

logger = logging.getLogger(__name__)

DEFAULT_PAGE_SIZE = 5
DEFAULT_MAX_PAGES = 1


def parse_workday_date(value: Any) -> Optional[datetime]:
    """Workday reports dates as plain "YYYY-MM-DD" strings; return midnight UTC on that day, or None."""
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


class WorkdayScraper(BaseScraper):
    source_name = "workday"

    def __init__(
        self,
        board: str,
        company_name: Optional[str] = None,
        session: Optional[requests.Session] = None,
        page_size: int = DEFAULT_PAGE_SIZE,
        max_pages: int = DEFAULT_MAX_PAGES,
    ):
        super().__init__(session=session)
        host, _, site = board.strip().strip("/").partition("/")
        if not host or not site or "/" in site:
            raise ValueError(
                f'Workday board must look like "host/site", e.g. "acme.wd5.myworkdayjobs.com/AcmeCareers"; got {board!r}'
            )
        self.host = host
        self.tenant = host.split(".")[0]
        self.site = site
        # Workday's API carries no company name, so use the one given or fall back to the tenant.
        self.company_name = company_name
        self.page_size = page_size
        self.max_pages = max_pages

    @property
    def api_base(self) -> str:
        return f"https://{self.host}/wday/cxs/{self.tenant}/{self.site}"

    def fetch_jobs(self) -> list[JobListing]:
        postings = []
        for page in range(self.max_pages):
            payload = {
                "appliedFacets": {},
                "limit": self.page_size,
                "offset": page * self.page_size,
                "searchText": "",
            }
            data = self._post_json(f"{self.api_base}/jobs", payload)
            page_postings = (
                data.get("jobPostings") or [] if isinstance(data, dict) else []
            )
            postings.extend(page_postings)
            if len(page_postings) < self.page_size:
                break
        return self._build_listings(postings, self._to_listing)

    def _to_listing(self, posting: dict) -> Optional[JobListing]:
        """Fetch one posting's details and map them onto the standardized JobListing model."""
        path = posting.get("externalPath") or ""
        try:
            detail = self._get_json(self.api_base + path)
        except ScraperRequestError:
            # Already logged with its URL by _get_json; the rest of the board is still returned.
            logger.warning(
                "Skipping %s posting whose details could not be fetched: %s",
                self.source_name,
                path,
            )
            raise ValueError(f"details unavailable for {path}")
        info = (
            detail.get("jobPostingInfo") if isinstance(detail, dict) else None
        ) or {}
        bullet_fields = posting.get("bulletFields") or []
        job_id = (
            info.get("jobReqId")
            or (bullet_fields[0] if bullet_fields else None)
            or info.get("id")
        )
        return JobListing(
            title=info.get("title") or posting.get("title") or "",
            company_name=self.company_name or self.tenant,
            location=info.get("location") or posting.get("locationsText") or None,
            description=info.get("jobDescription") or "",
            source=self.source_name,
            application_url=f"https://{self.host}/{self.site}{path}" if path else "",
            posted_at=parse_workday_date(info.get("startDate")),
            source_job_id=str(job_id) if job_id is not None else None,
            status="open" if info.get("canApply", True) else "closed",
        )

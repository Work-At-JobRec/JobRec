"""Standardized representation of a scraped job listing.

Every scraper converts its source-specific data into a JobListing before the
listing is passed to other parts of the application (validation, storage,
recommendation). Downstream code should only ever depend on this model.
"""

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field


def _utc_now() -> datetime:
    """Timezone-aware current time in UTC, used as the default scrape timestamp."""
    return datetime.now(timezone.utc)


class JobListing(BaseModel):
    title: str = Field(..., description="Job title exactly as posted by the source")
    company_name: str = Field(..., description="Name of the hiring company")
    location: Optional[str] = Field(
        None, description="Free-text location of the role; None when the source does not provide one"
    )
    description: str = Field(
        "", description="Full job description text. May contain HTML until normalization cleans it."
    )
    source: str = Field(..., description='Identifier of the scraper that produced this listing, e.g. "greenhouse"')
    application_url: str = Field(..., description="URL where a candidate can view or apply for the job")
    posted_at: Optional[datetime] = Field(
        None, description="When the job was originally posted, if the source reports it (timezone-aware)"
    )
    scraped_at: datetime = Field(
        default_factory=_utc_now, description="When this listing was retrieved by the scraper (UTC)"
    )
    source_job_id: Optional[str] = Field(
        None, description="Source-specific job identifier, stored as a string so it is comparable across sources"
    )

"""Validation for scraped job listings.

Scrapers are lenient on purpose: a job with a missing title still becomes a
JobListing so that it can be inspected and logged. This module is the gate that
decides which listings the rest of the application accepts. Invalid listings
are skipped and logged so malformed scraper results can be traced.
"""

import logging
from typing import Iterable
from urllib.parse import urlsplit

from job_listing import JobListing

logger = logging.getLogger(__name__)

# Text fields that must contain something other than whitespace.
REQUIRED_TEXT_FIELDS = ("title", "company_name", "source")


def _url_problem(url: str) -> str:
    """Return a description of what is wrong with an application URL, or "" if it is usable."""
    if not url.strip():
        return "application_url is missing"
    if any(ch.isspace() for ch in url.strip()):
        return "application_url contains whitespace"
    try:
        parts = urlsplit(url.strip())
        hostname = parts.hostname
    except ValueError:
        return "application_url could not be parsed"
    if parts.scheme.lower() not in ("http", "https"):
        return "application_url must start with http:// or https://"
    if not hostname:
        return "application_url has no host"
    return ""


def validate_listing(listing: JobListing) -> list[str]:
    """Return every problem found with a listing. An empty list means the listing is valid.

    Optional fields (location, description, posted_at, source_job_id) may be missing.
    """
    problems = [
        f"{field} is missing"
        for field in REQUIRED_TEXT_FIELDS
        if not getattr(listing, field).strip()
    ]
    url_problem = _url_problem(listing.application_url)
    if url_problem:
        problems.append(url_problem)
    return problems


def filter_valid_listings(listings: Iterable[JobListing]) -> list[JobListing]:
    """Keep only valid listings, in order. Each rejected listing is logged as a warning."""
    valid = []
    total = 0
    for listing in listings:
        total += 1
        problems = validate_listing(listing)
        if problems:
            logger.warning(
                "Skipping invalid job listing (source=%s, source_job_id=%s, url=%r): %s",
                listing.source or "?", listing.source_job_id, listing.application_url, "; ".join(problems),
            )
        else:
            valid.append(listing)
    if len(valid) != total:
        logger.info("Rejected %d of %d scraped job listings", total - len(valid), total)
    return valid

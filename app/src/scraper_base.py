"""Common interface that every job scraper implements.

Code that consumes scraped jobs only depends on this class: it calls
``fetch_jobs()`` and receives standardized ``JobListing`` objects. Adding a
new job source means adding a new subclass, not changing the consumers.
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, Callable, Iterable, Optional

import requests

from job_listing import JobListing

logger = logging.getLogger(__name__)

# Seconds to wait for a job source before giving up on a single request.
DEFAULT_TIMEOUT = 10


class ScraperRequestError(Exception):
    """A job source could not be retrieved (connection failure, timeout, bad status, or bad body)."""

    def __init__(self, source: str, url: str, message: str):
        super().__init__(f"{source}: request to {url} failed: {message}")
        self.source = source
        self.url = url


class BaseScraper(ABC):
    # Short identifier for the job source (e.g. "greenhouse"). Subclasses must set
    # this; it is copied into JobListing.source for every listing they produce.
    source_name: str = ""

    def __init__(self, session: Optional[requests.Session] = None):
        # A session can be injected so tests can control HTTP behaviour without touching the network.
        self.session = session or requests.Session()

    @abstractmethod
    def fetch_jobs(self) -> list[JobListing]:
        """Retrieve every currently available job from the source as JobListing objects."""

    def _get_json(self, url: str, params: Optional[dict] = None, timeout: float = DEFAULT_TIMEOUT) -> Any:
        """GET a URL and return its decoded JSON body.

        Connection failures, timeouts, non-2xx responses, and bodies that are not JSON
        are logged once with the source and URL, then raised as ScraperRequestError so
        the caller can move on to the next source instead of crashing.
        """
        try:
            response = self.session.get(url, params=params, timeout=timeout)
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as exc:
            # requests raises ValueError subclasses when the body is not valid JSON.
            failed_response = getattr(exc, "response", None)
            status = getattr(failed_response, "status_code", None)
            detail = f"HTTP {status}: {exc}" if status is not None else str(exc)
            logger.error("Request failed (source=%s, url=%s): %s", self.source_name, url, detail)
            raise ScraperRequestError(self.source_name, url, detail) from exc

    def _build_listings(self, raw_items: Iterable[Any], convert: Callable[[Any], JobListing]) -> list[JobListing]:
        """Convert raw source items into JobListings, skipping any single item that cannot be converted.

        Without this, one malformed job (for example a numeric title) would raise and
        lose every other job from the same source.
        """
        listings = []
        for raw in raw_items:
            try:
                listings.append(convert(raw))
            except (ValueError, TypeError, AttributeError, KeyError) as exc:
                # pydantic.ValidationError is a ValueError.
                raw_id = raw.get("id") if isinstance(raw, dict) else None
                logger.warning("Skipping malformed %s job (id=%r): %s", self.source_name, raw_id, exc)
        return listings

"""Common interface that every job scraper implements.

Code that consumes scraped jobs only depends on this class: it calls
``fetch_jobs()`` and receives standardized ``JobListing`` objects. Adding a
new job source means adding a new subclass, not changing the consumers.
"""

from abc import ABC, abstractmethod
from typing import Optional

import requests

from job_listing import JobListing

# Seconds to wait for a job source before giving up on a single request.
DEFAULT_TIMEOUT = 10


class BaseScraper(ABC):
    # Short identifier for the job source (e.g. "greenhouse"). Subclasses must set
    # this; it is copied into JobListing.source for every listing they produce.
    source_name: str = ""

    def __init__(self, session: Optional[requests.Session] = None):
        # A session can be injected so tests (and future retry/error handling)
        # can control HTTP behaviour without touching the network.
        self.session = session or requests.Session()

    @abstractmethod
    def fetch_jobs(self) -> list[JobListing]:
        """Retrieve every currently available job from the source as JobListing objects."""

    def _get_json(self, url: str, params: Optional[dict] = None, timeout: float = DEFAULT_TIMEOUT) -> dict:
        """GET a URL and return its decoded JSON body, raising on non-2xx responses."""
        response = self.session.get(url, params=params, timeout=timeout)
        response.raise_for_status()
        return response.json()

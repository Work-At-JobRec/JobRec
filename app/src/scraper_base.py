"""Common interface that every job scraper implements.

Code that consumes scraped jobs only depends on this class: it calls
``fetch_jobs()`` and receives standardized ``JobListing`` objects. Adding a
new job source means adding a new subclass, not changing the consumers.
"""

from abc import ABC, abstractmethod

from job_listing import JobListing


class BaseScraper(ABC):
    # Short identifier for the job source (e.g. "greenhouse"). Subclasses must set
    # this; it is copied into JobListing.source for every listing they produce.
    source_name: str = ""

    @abstractmethod
    def fetch_jobs(self) -> list[JobListing]:
        """Retrieve every currently available job from the source as JobListing objects."""

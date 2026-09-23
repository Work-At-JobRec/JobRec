"""Runs a set of job scrapers without letting one failing source stop the rest."""

import logging
from typing import Iterable

from job_listing import JobListing
from scraper_base import BaseScraper, ScraperRequestError

logger = logging.getLogger(__name__)


def fetch_all(scrapers: Iterable[BaseScraper]) -> list[JobListing]:
    """Fetch jobs from every scraper and return the combined listings in scraper order.

    A source that cannot be reached is skipped (the failed request has already been
    logged with its URL). Any other unexpected error from a scraper is logged with
    its traceback and skipped as well, so a single bad source never ends the run.
    """
    listings: list[JobListing] = []
    for scraper in scrapers:
        try:
            listings.extend(scraper.fetch_jobs())
        except ScraperRequestError:
            continue
        except Exception:
            logger.exception("Unexpected error while scraping source=%s; continuing", scraper.source_name)
    return listings

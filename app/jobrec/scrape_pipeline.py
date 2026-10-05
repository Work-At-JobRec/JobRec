"""End-to-end scraping run: fetch from every source, clean, validate, and store."""

import logging
from typing import Iterable

from sqlalchemy import Engine

from app.jobrec.job_normalization import normalize_listings
from app.jobrec.job_store import UpsertResult, upsert_listings
from app.jobrec.job_validation import filter_valid_listings
from app.jobrec.scraper_base import BaseScraper
from app.jobrec.scraper_runner import fetch_all

logger = logging.getLogger(__name__)


def run_scrape_pipeline(
    engine: Engine, scrapers: Iterable[BaseScraper]
) -> UpsertResult:
    """Fetch jobs from every scraper, normalize and validate them, and store the result.

    Sources that fail are skipped (already logged by the scrapers), invalid listings
    are skipped (logged by validation), and listings already stored are updated
    rather than duplicated.
    """
    fetched = fetch_all(scrapers)
    valid = filter_valid_listings(normalize_listings(fetched))
    result = upsert_listings(engine, valid)
    logger.info(
        "Scrape pipeline: %d fetched, %d valid, %d new, %d already stored",
        len(fetched),
        len(valid),
        result.inserted,
        result.existing,
    )
    return result

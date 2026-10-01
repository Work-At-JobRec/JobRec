"""End-to-end scraping run: fetch from every source, clean, validate, and store."""

import logging
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Iterable

from sqlalchemy import Engine

from jobrec.job_normalization import normalize_listings
from jobrec.job_store import UpsertResult, listing_key, upsert_listings
from jobrec.job_validation import filter_valid_listings
from jobrec.scraper_base import BaseScraper
from jobrec.scraper_runner import fetch_all

logger = logging.getLogger(__name__)


def run_scrape_pipeline(
    engine: Engine, scrapers: Iterable[BaseScraper]
) -> UpsertResult:
    """Fetch jobs from every scraper, normalize and validate them, and store the result.

    Sources that fail are skipped (already logged by the scrapers), invalid listings
    are skipped (logged by validation), and listings already stored are updated
    rather than duplicated.
    """
    from jobrec.skill_detection import (
        detect_document_skills,
        get_skill_catalog,
        initialize_skill_schema,
        persist_discovered_skills,
        SkillRanking,
        store_listing_skills,
    )

    initialize_skill_schema(engine)
    catalog = get_skill_catalog(engine)
    detection_tasks: list[
        tuple[JobListing, Future[tuple[list[SkillRanking], list]]]
    ] = []

    def submit_skill_detection(batch):
        normalized_batch = filter_valid_listings(normalize_listings(batch))
        for listing in normalized_batch:
            future = executor.submit(
                detect_document_skills,
                listing.description,
                catalog,
                document_type="job listing",
            )
            detection_tasks.append((listing, future))

    with ThreadPoolExecutor(max_workers=4) as executor:
        fetched = fetch_all(scrapers, on_listings=submit_skill_detection)
        detected_by_key = {}
        discovered = []
        for listing, future in detection_tasks:
            try:
                matched, new_skills = future.result()
            except Exception:
                logger.exception(
                    "Skill detection failed for listing %s", listing_key(listing)
                )
                continue
            detected_by_key[listing_key(listing)] = matched + [
                SkillRanking(
                    skill_name=skill.skill_name,
                    proficiency_level=skill.proficiency_level,
                )
                for skill in new_skills
            ]
            discovered.extend(new_skills)

    valid = filter_valid_listings(normalize_listings(fetched))
    result = upsert_listings(engine, valid)
    persist_discovered_skills(engine, discovered)
    store_listing_skills(engine, detected_by_key)
    logger.info(
        "Scrape pipeline: %d fetched, %d valid, %d new, %d already stored",
        len(fetched),
        len(valid),
        result.inserted,
        result.existing,
    )
    return result

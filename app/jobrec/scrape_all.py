"""Scrape every source in the registry into the application database.

Run from app/:  python -m jobrec.scrape_all [--sources path/to/job_sources.json]
                                             [--max-per-source N] [--max-listings N]

The two caps are for small test databases, such as one for a user acceptance
test: ``--max-per-source 20`` stores up to 20 listings from each source, and
``--max-listings 200`` stops the run once 200 are stored. Without them every
listing is stored, which is what the scheduled scrape does.

Uses the same DATABASE_URL setting as the web app (local SQLite by default), so
listings scraped here are what the application serves. Each source runs on its
own: one that fails is reported and the rest still run. The exit status is
non-zero when any source failed or when the database ends up with no listings,
so a scheduled run that silently stored nothing shows up as a failure.

New listings and listings with changed descriptions are marked for deferred
skill analysis. Run ``python -m jobrec.listing_skill_extractor`` separately to
process that queue; scraping itself does not call the OpenAI skill detector.
"""

import argparse
import logging
import sys
from os import environ as env
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from sqlalchemy import Engine

from jobrec.db import make_engine
from jobrec.job_sources import DEFAULT_SOURCES_PATH, JobSource, load_sources
from jobrec.job_sources import scrape_all as scrape_registry
from jobrec.job_store import (
    JobListingTable,
    UpsertResult,
    count_listings,
    ensure_job_listing_schema,
)  # noqa: F401

logger = logging.getLogger(__name__)


def scrape_sources(
    engine: Engine,
    sources: list[JobSource],
    max_per_source: Optional[int] = None,
    max_listings: Optional[int] = None,
) -> tuple[list[tuple[str, UpsertResult]], list[str]]:
    """Scrape each enabled source separately. Returns (per-source results, names of sources that failed).

    ``max_per_source`` caps what each source stores and ``max_listings`` caps the whole run;
    once the run's cap is used up the remaining sources are not scraped. Listings that were
    already stored count toward the caps, so repeating a capped run does not grow the database.
    """
    results: list[tuple[str, UpsertResult]] = []
    failures: list[str] = []
    remaining = max_listings
    for source in sources:
        if not source.enabled:
            continue
        if remaining is not None and remaining <= 0:
            logger.info("Listing cap of %d reached; not scraping %s", max_listings, source.name)
            continue
        caps = [cap for cap in (max_per_source, remaining) if cap is not None]
        try:
            source_results = scrape_registry(engine, [source], max_listings=min(caps) if caps else None)
        except Exception:
            logger.exception("Source %s failed; continuing with the remaining sources", source.name)
            failures.append(source.name)
            continue
        results.extend(source_results)
        if remaining is not None:
            remaining -= sum(result.inserted + result.existing for _, result in source_results)
    return results, failures


def positive_int(value: str) -> int:
    """argparse type for the caps: a whole number of at least 1."""
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError(f"must be at least 1, got {value}")
    return number


def exit_code(failures: list[str], total_stored: int) -> int:
    """0 when every source ran and the database holds listings, otherwise 1."""
    return 1 if failures or total_stored == 0 else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Scrape every registered job source into the database.")
    parser.add_argument("--sources", type=Path, default=DEFAULT_SOURCES_PATH, help="registry file to read")
    parser.add_argument("--max-per-source", type=positive_int, help="store at most N listings from each source")
    parser.add_argument("--max-listings", type=positive_int, help="store at most N listings in the whole run")
    args = parser.parse_args()

    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    engine = make_engine(env.get("DATABASE_URL", "sqlite+pysqlite:///user_skills.db"))
    ensure_job_listing_schema(engine)

    results, failures = scrape_sources(
        engine, load_sources(args.sources), max_per_source=args.max_per_source, max_listings=args.max_listings,
    )
    for name, result in results:
        print(f"{name:<40} new={result.inserted:<5} updated={result.updated:<5} unchanged={result.unchanged}")
    for name in failures:
        print(f"{name:<40} FAILED (see log above)")
    total = count_listings(engine)
    print(f"{len(results)} source(s) scraped, {len(failures)} failed; {total} listings stored in total")
    return exit_code(failures, total)


if __name__ == "__main__":
    sys.exit(main())

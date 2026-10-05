"""Scrape every source in the registry into the application database.

Run from app/:  python -m jobrec.scrape_all [--sources path/to/job_sources.json]

Uses the same DATABASE_URL setting as the web app (local SQLite by default), so
listings scraped here are what the application serves. Each source runs on its
own: one that fails is reported and the rest still run. The exit status is
non-zero when any source failed or when the database ends up with no listings,
so a scheduled run that silently stored nothing shows up as a failure.
"""

import argparse
import logging
import sys
from os import environ as env
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import Engine

from jobrec.db import Base, make_engine
from jobrec.job_sources import DEFAULT_SOURCES_PATH, JobSource, load_sources
from jobrec.job_sources import scrape_all as scrape_registry
from jobrec.job_store import JobListingTable, UpsertResult, count_listings  # noqa: F401  (registers the table before create_all)

logger = logging.getLogger(__name__)


def scrape_sources(engine: Engine, sources: list[JobSource]) -> tuple[list[tuple[str, UpsertResult]], list[str]]:
    """Scrape each enabled source separately. Returns (per-source results, names of sources that failed)."""
    results: list[tuple[str, UpsertResult]] = []
    failures: list[str] = []
    for source in sources:
        if not source.enabled:
            continue
        try:
            results.extend(scrape_registry(engine, [source]))
        except Exception:
            logger.exception("Source %s failed; continuing with the remaining sources", source.name)
            failures.append(source.name)
    return results, failures


def exit_code(failures: list[str], total_stored: int) -> int:
    """0 when every source ran and the database holds listings, otherwise 1."""
    return 1 if failures or total_stored == 0 else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Scrape every registered job source into the database.")
    parser.add_argument("--sources", type=Path, default=DEFAULT_SOURCES_PATH, help="registry file to read")
    args = parser.parse_args()

    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    engine = make_engine(env.get("DATABASE_URL", "sqlite+pysqlite:///user_skills.db"))
    Base.metadata.create_all(engine)

    results, failures = scrape_sources(engine, load_sources(args.sources))
    for name, result in results:
        print(f"{name:<40} new={result.inserted:<5} updated={result.updated:<5} unchanged={result.unchanged}")
    for name in failures:
        print(f"{name:<40} FAILED (see log above)")
    total = count_listings(engine)
    print(f"{len(results)} source(s) scraped, {len(failures)} failed; {total} listings stored in total")
    return exit_code(failures, total)


if __name__ == "__main__":
    sys.exit(main())

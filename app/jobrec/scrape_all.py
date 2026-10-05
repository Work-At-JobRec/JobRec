"""Scrape every source in the registry into the application database.

Run from app/src:  python scrape_all.py [--sources path/to/job_sources.json]

Uses the same DATABASE_URL setting as the web app (local SQLite by default), so
listings scraped here are what the application serves.
"""

import argparse
import logging
from os import environ as env
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine

from jobrec.db import Base
from jobrec.job_sources import DEFAULT_SOURCES_PATH, load_sources, scrape_all
from jobrec.job_store import (
    JobListingTable,
    count_listings,
)  # noqa: F401  (registers the table before create_all)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scrape every registered job source into the database."
    )
    parser.add_argument(
        "--sources",
        type=Path,
        default=DEFAULT_SOURCES_PATH,
        help="registry file to read",
    )
    args = parser.parse_args()

    load_dotenv()
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )
    engine = create_engine(env.get("DATABASE_URL", "sqlite+pysqlite:///user_skills.db"))
    Base.metadata.create_all(engine)

    results = scrape_all(engine, load_sources(args.sources))
    for name, result in results:
        print(
            f"{name:<24} new={result.inserted:<5} updated={result.updated:<5} unchanged={result.unchanged}"
        )
    print(
        f"{len(results)} source(s) scraped; {count_listings(engine)} listings stored in total"
    )


if __name__ == "__main__":
    main()

"""Deferred skill analysis for stored job listings."""

import argparse
import logging
import sys
from dataclasses import dataclass
from os import environ as env

from dotenv import load_dotenv
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from jobrec.db import make_engine
from jobrec.job_store import JobListingTable
from jobrec.skill_detection import (
    detect_document_skills,
    get_skill_catalog,
    save_listing_skill_analysis,
)

logger = logging.getLogger(__name__)

DEFAULT_LIMIT = 50


@dataclass
class ExtractionResult:
    processed: int = 0
    failed: int = 0
    stale: int = 0
    pending: int = 0


def extract_pending_listing_skills(
    engine: Engine, *, limit: int = DEFAULT_LIMIT
) -> ExtractionResult:
    """Analyze up to ``limit`` pending listings, leaving failures queued for retry."""
    if limit < 1:
        raise ValueError("limit must be at least 1")

    catalog = get_skill_catalog(engine)
    with Session(engine) as session:
        pending = list(
            session.execute(
                select(
                    JobListingTable.dedupe_key,
                    JobListingTable.description,
                )
                .where(JobListingTable.skills_pending.is_(True))
                .order_by(JobListingTable.id)
                .limit(limit)
            )
        )

    result = ExtractionResult()
    for dedupe_key, description in pending:
        try:
            matched, discovered = detect_document_skills(
                description,
                catalog,
                document_type="job listing",
            )
            saved = save_listing_skill_analysis(
                engine, dedupe_key, description, matched, discovered
            )
        except Exception:
            logger.exception("Skill extraction failed for listing %s", dedupe_key)
            result.failed += 1
            continue
        if saved:
            result.processed += 1
        else:
            result.stale += 1

    with Session(engine) as session:
        result.pending = session.scalar(
            select(func.count())
            .select_from(JobListingTable)
            .where(JobListingTable.skills_pending.is_(True))
        ) or 0
    return result


def exit_code(result: ExtractionResult) -> int:
    return 1 if result.failed else 0


def main(argv: list[str] | None = None, *, engine: Engine | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Extract skills from stored listings marked for analysis."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        help=f"maximum pending listings to analyze per run (default: {DEFAULT_LIMIT})",
    )
    args = parser.parse_args(argv)
    if args.limit < 1:
        parser.error("--limit must be at least 1")

    if engine is None:
        load_dotenv()
        logging.basicConfig(
            level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
        )
        engine = make_engine(
            env.get("DATABASE_URL", "sqlite+pysqlite:///user_skills.db")
        )

    result = extract_pending_listing_skills(engine, limit=args.limit)
    print(
        f"Skill extraction: {result.processed} processed, {result.failed} failed, "
        f"{result.stale} changed during analysis, {result.pending} still pending"
    )
    return exit_code(result)


if __name__ == "__main__":
    sys.exit(main())

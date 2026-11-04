"""Narrated scrape run for live demos.

Runs the same pipeline as ``scrape_all`` (fetch, keep open listings, normalize, validate,
store), one source at a time, printing every stage with timings and the growing database
count so an audience can follow a listing from a job board into the database.

Run from app/::

    poetry run python -m jobrec.scrape_demo --fresh

``--fresh`` starts from an empty database so the count visibly grows from zero; it only
ever deletes a file named ``demo_scrape.db``. By default the run writes to that file next
to the app's own database and never touches it; pass ``--database user_skills.db`` (or
``--database "$DATABASE_URL"``) to scrape into the real one, where rows are added or
updated in place and then show up on the Jobs page.
"""

import argparse
import logging
import sys
import time
from pathlib import Path
from typing import Callable, Optional

from dotenv import load_dotenv
from sqlalchemy import Engine, create_engine

from jobrec.db import Base
from jobrec.job_listing import JobListing
from jobrec.job_normalization import normalize_listings
from jobrec.job_sources import DEFAULT_SOURCES_PATH, JobSource, build_scraper, load_sources
from jobrec.job_store import UpsertResult, count_listings, upsert_listings
from jobrec.job_validation import filter_valid_listings, only_open_listings
from jobrec.scraper_base import BaseScraper, ScraperRequestError

DEFAULT_DATABASE = "demo_scrape.db"


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def _sample_line(listing: JobListing) -> str:
    url = listing.application_url
    if len(url) > 60:
        url = url[:57] + "..."
    return (
        f"      + {listing.title} | {listing.company_name} | {listing.location or 'location n/a'}"
        f" | {listing.pay or 'pay n/a'} | {url}"
    )


def run_demo(
    engine: Engine,
    sources: list[JobSource],
    *,
    build: Optional[Callable[[JobSource], BaseScraper]] = None,
    pause: float = 0.0,
    sample: int = 2,
    limit: Optional[int] = None,
    out: Callable[[str], None] = print,
) -> list[tuple[str, UpsertResult]]:
    """Scrape each enabled source in turn, narrating every stage through ``out``.

    ``pause`` seconds are waited between stages so the output is readable as it scrolls.
    ``sample`` stored listings per source are printed as example rows. ``limit`` caps how
    many valid listings per source are stored, to keep a demo short. ``build`` turns a
    registry entry into a scraper and defaults to the registry's own ``build_scraper``.
    """
    if build is None:
        build = build_scraper
    enabled = [source for source in sources if source.enabled]
    results: list[tuple[str, UpsertResult]] = []

    def wait() -> None:
        if pause > 0:
            time.sleep(pause)

    out(f"Scraping {_plural(len(enabled), 'source')}; database starts with {_plural(count_listings(engine), 'listing')}")
    for index, source in enumerate(enabled, start=1):
        scraper = build(source)
        out("")
        out(f"[{index}/{len(enabled)}] {source.name}  ({source.company_name or scraper.source_name})")
        out(f"    fetching with {type(scraper).__name__} ...")
        started = time.perf_counter()
        try:
            fetched = scraper.fetch_jobs()
        except ScraperRequestError as exc:
            out(f"    FAILED after {time.perf_counter() - started:.1f}s: {exc}; moving on to the next source")
            continue
        elapsed = time.perf_counter() - started
        opened = only_open_listings(fetched)
        out(
            f"    fetched {_plural(len(fetched), 'listing')} in {elapsed:.1f}s"
            f" ({len(opened)} open, {len(fetched) - len(opened)} closed)"
        )
        wait()

        normalized = normalize_listings(opened)
        out("    normalized: trimmed whitespace, stripped HTML from descriptions, removed tracking parameters from URLs")
        valid = filter_valid_listings(normalized)
        out(f"    validated: {len(valid)} valid, {len(normalized) - len(valid)} rejected (missing required fields or bad URL)")
        if limit is not None:
            valid = valid[:limit]
        wait()

        result = upsert_listings(engine, valid)
        out(
            f"    stored: {result.inserted} new, {result.updated} updated, {result.unchanged} unchanged"
            f" -> database now holds {_plural(count_listings(engine), 'listing')}"
        )
        for listing in valid[:sample]:
            out(_sample_line(listing))
        results.append((source.name, result))
        wait()

    out("")
    width = max([len(name) for name, _ in results] + [len("source")]) + 2
    out(f"{'source':<{width}}{'new':>6}{'updated':>9}{'unchanged':>11}")
    for name, result in results:
        out(f"{name:<{width}}{result.inserted:>6}{result.updated:>9}{result.unchanged:>11}")
    out(f"{_plural(len(results), 'source')} scraped; {_plural(count_listings(engine), 'listing')} stored in total")
    return results


def _engine_for(database: str) -> Engine:
    if "://" in database:
        return create_engine(database)
    return create_engine(f"sqlite+pysqlite:///{database}")


def main(argv: Optional[list[str]] = None, out: Optional[Callable[[str], None]] = None) -> int:
    parser = argparse.ArgumentParser(description="Scrape every registered source, narrating each stage for a demo.")
    parser.add_argument("--sources", type=Path, default=DEFAULT_SOURCES_PATH, help="registry file to read")
    parser.add_argument(
        "--database",
        default=DEFAULT_DATABASE,
        help=f"SQLite file or SQLAlchemy URL to write to (default: {DEFAULT_DATABASE})",
    )
    parser.add_argument("--fresh", action="store_true", help="delete the SQLite file first so the count grows from zero")
    parser.add_argument("--pause", type=float, default=0.8, help="seconds to wait between stages (default: 0.8)")
    parser.add_argument("--sample", type=int, default=2, help="example rows to print per source (default: 2)")
    parser.add_argument("--limit", type=int, default=None, help="store at most this many listings per source")
    parser.add_argument(
        "--only",
        default=None,
        help="comma-separated source names (or prefixes) to scrape, e.g. greenhouse:figma,lever",
    )
    args = parser.parse_args(argv)

    load_dotenv()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    # Only warnings and errors from the scrapers (bad listings, failed requests) are shown;
    # the narration below already reports the normal flow.
    logging.basicConfig(
        level=logging.WARNING, format="%(asctime)s  %(levelname)-7s %(message)s", datefmt="%H:%M:%S", stream=sys.stdout
    )
    if out is None:

        def out(line: str) -> None:
            stamp = time.strftime("%H:%M:%S") if line else ""
            print(f"{stamp}  {line}" if line else "", flush=True)

    if args.fresh:
        if "://" in args.database or Path(args.database).name != DEFAULT_DATABASE:
            # Never wipe the application's own database (it also holds user profiles).
            parser.error(f"--fresh only resets a file named {DEFAULT_DATABASE}; got {args.database!r}")
        Path(args.database).unlink(missing_ok=True)
    engine = _engine_for(args.database)
    Base.metadata.create_all(engine)

    sources = load_sources(args.sources)
    if args.only:
        wanted = [part.strip() for part in args.only.split(",") if part.strip()]
        sources = [source for source in sources if any(source.name.startswith(prefix) for prefix in wanted)]
        if not sources:
            parser.error(f"--only {args.only!r} matches none of the registered sources")

    run_demo(engine, sources, pause=args.pause, sample=args.sample, limit=args.limit, out=out)
    return 0


if __name__ == "__main__":
    sys.exit(main())

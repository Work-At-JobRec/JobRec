"""TC-017 seed: 4 open listings (live Lever scrape) + 4 closed ones, all a month stale.

Usage: DATABASE_URL=postgresql+psycopg://... python tc017_seed.py [seed|verify]
"""
import os
import sys
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, func, select, text, update

from jobrec.db import Base
from jobrec.job_listing import JobListing
from jobrec.job_normalization import normalize_listings
from jobrec.job_sources import JobSource, build_scraper
from jobrec.job_store import JobListingTable, upsert_listings
from jobrec.job_validation import filter_valid_listings

engine = create_engine(os.environ["DATABASE_URL"])
now = datetime.now(timezone.utc)

CLOSED = [
    # Lever answers an unknown posting id with 404 -> link_check reports CLOSED
    ("lever", "Palantir", "00000000-0000-0000-0000-000000000001",
     "https://jobs.lever.co/palantir/00000000-0000-0000-0000-000000000001", "Retired Lever posting A"),
    ("lever", "Palantir", "00000000-0000-0000-0000-000000000002",
     "https://jobs.lever.co/palantir/00000000-0000-0000-0000-000000000002", "Retired Lever posting B"),
    # Greenhouse board API answers an unknown job id with 404 -> CLOSED (checked before the careers page, #137)
    ("greenhouse", "Figma", "1", "https://job-boards.greenhouse.io/figma/jobs/1", "Retired Greenhouse posting A"),
    ("greenhouse", "Figma", "2", "https://job-boards.greenhouse.io/figma/jobs/2", "Retired Greenhouse posting B"),
]


def seed():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    scraper = build_scraper(JobSource(scraper="lever", id="palantir", company_name="Palantir"))
    live = filter_valid_listings(normalize_listings(scraper.fetch_open_jobs()))
    open_four = live[:4]
    closed_four = [
        JobListing(
            title=title, company_name=company, location="Remote",
            description="Listing kept only to verify pruning; the source no longer serves it.",
            source=source, application_url=url, scraped_at=now, source_job_id=job_id, status="open",
        )
        for source, company, job_id, url, title in CLOSED
    ]
    result = upsert_listings(engine, open_four + closed_four)
    print(f"seeded: {result.inserted} inserted ({len(open_four)} open from the live Palantir board, {len(closed_four)} closed)")
    # "Move the clock forward a month": every row was last seen 31 days ago
    with engine.begin() as conn:
        conn.execute(update(JobListingTable).values(
            last_seen_at=now - timedelta(days=31), first_seen_at=now - timedelta(days=40)))
    report("after seeding")


def report(label):
    with engine.connect() as conn:
        total = conn.execute(select(func.count()).select_from(JobListingTable)).scalar_one()
        rows = conn.execute(select(JobListingTable.source, JobListingTable.title, JobListingTable.application_url)
                            .order_by(JobListingTable.id)).all()
    print(f"{label}: {total} listings")
    for source, title, url in rows:
        print(f"  {source:11} {title[:45]:45} {url}")
    return rows


def verify():
    rows = report("after pruning")
    closed_urls = {url for *_, url, _ in CLOSED}
    remaining_closed = [r for r in rows if r.application_url in closed_urls]
    ok = len(rows) == 4 and not remaining_closed
    print("TC-017 RESULT:", "PASS" if ok else "FAIL",
          f"({len(rows)} remain, {len(remaining_closed)} closed listings still present)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(seed() if sys.argv[1] == "seed" else verify())

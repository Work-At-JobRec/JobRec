import logging
import os
import random
import sys
from datetime import datetime, timedelta, timezone

import requests
from sqlalchemy import ForeignKey, Integer, insert, select
from sqlalchemy.orm import Mapped, Session, mapped_column

# Lets this test import app/src/job_pruning.py
SRC_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "src")
)
sys.path.insert(0, SRC_DIR)

from jobrec.db import Base  # noqa: E402
from jobrec.job_listing import JobListing  # noqa: E402
from job_pruning import PruneResult, find_prune_candidates, prune_closed_listings  # noqa: E402
from jobrec.job_store import JobListingTable, count_listings, list_listings, upsert_listings  # noqa: E402
from link_fakes import FakeSession, page  # noqa: E402
import prune_jobs  # noqa: E402

T1 = datetime(2026, 10, 1, 10, 0, tzinfo=timezone.utc)
T2 = datetime(2026, 10, 2, 10, 0, tzinfo=timezone.utc)
OPEN = ["o1", "o2", "o3", "o4"]
CLOSED = ["c1", "c2", "c3", "c4"]


class ListingNote(Base):
    """Stands in for another table that refers to job listings (the matching branch adds one for skills)."""

    __tablename__ = "prune_test_listing_notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("job_listings.id"), nullable=False)


def url(job_id: str, host: str = "acme.com") -> str:
    return f"https://{host}/jobs/{job_id}"


def make_listing(job_id: str, host: str = "acme.com", company: str = "Acme", **overrides) -> JobListing:
    # Page-check fixtures are not greenhouse. An unresolved greenhouse source
    # is unknown and is not fetched, so these controls would stop reaching the page.
    fields = {
        "title": "Software Engineer",
        "company_name": company,
        "source": "lever",
        "application_url": url(job_id, host),
        "source_job_id": job_id,
    }
    fields.update(overrides)
    return JobListing(**fields)


def no_sleep(seconds):
    return None


def seed_open_and_closed(engine):
    """Four open and four closed listings last reported at T1, then one the next scrape still reported at T2."""
    upsert_listings(engine, [make_listing(job_id) for job_id in OPEN + CLOSED], now=T1)
    upsert_listings(engine, [make_listing("fresh")], now=T2)


def routes_for_open_and_closed():
    routes = {url(job_id): page(200, "<h1>Software Engineer</h1><p>Apply now</p>") for job_id in OPEN}
    routes[url("c1")] = page(404, "Not found")
    routes[url("c2")] = page(410, "Gone")
    routes[url("c3")] = page(200, "<h1>Openings</h1>", url="https://job-boards.greenhouse.io/acme?error=true", redirected=True)
    routes[url("c4")] = page(200, "<h1>Acme</h1><p>This job is no longer available.</p>")
    return routes


def stored_ids(engine):
    return sorted(listing.source_job_id for listing in list_listings(engine))


# --- TC-016 ---

# With four open and four closed listings stored, pruning follows each link and removes exactly the closed four
def test_tc016_prune_removes_exactly_the_closed_listings(engine):
    seed_open_and_closed(engine)
    session = FakeSession(routes_for_open_and_closed())

    result = prune_closed_listings(engine, session, dry_run=False, now=T2, sleep=no_sleep)

    assert result == PruneResult(checked=8, closed=4, removed=4, kept=4, unknown=0)
    assert stored_ids(engine) == sorted(OPEN + ["fresh"])
    # The listing the latest scrape reported is known to be open, so its link is not even requested.
    assert url("fresh") not in session.calls


# By default nothing is deleted; the result reports what would be removed
def test_dry_run_reports_closed_listings_without_deleting(engine):
    seed_open_and_closed(engine)

    result = prune_closed_listings(engine, FakeSession(routes_for_open_and_closed()), now=T2, sleep=no_sleep)

    assert result == PruneResult(checked=8, closed=4, removed=0, kept=4, unknown=0)
    assert count_listings(engine) == 9


# --- which listings are checked ---

# Listings missing from their company's latest scrape are candidates; the ones it reported are not
def test_candidates_are_listings_absent_from_their_companys_latest_scrape(engine):
    seed_open_and_closed(engine)

    candidates = find_prune_candidates(engine, now=T2)

    assert sorted(c.source_job_id for c in candidates) == sorted(OPEN + CLOSED)


# A company whose scrape did not run this time has nothing newer to compare against, so nothing is nominated
def test_company_with_no_newer_scrape_has_no_candidates(engine):
    upsert_listings(engine, [make_listing("a"), make_listing("b")], now=T1)
    upsert_listings(engine, [make_listing("z", company="Other Co", host="other.com")], now=T2)

    assert find_prune_candidates(engine, now=T2) == []


# Listings nobody has reported for a long time are checked even without a newer scrape
def test_listings_unseen_for_a_week_are_candidates(engine):
    upsert_listings(engine, [make_listing("old")], now=T1)

    candidates = find_prune_candidates(engine, now=T1 + timedelta(days=8))

    assert [c.source_job_id for c in candidates] == ["old"]


# With a fresh database, where everything was just seen, nothing is checked at all
def test_freshly_scraped_database_checks_nothing(engine):
    upsert_listings(engine, [make_listing(job_id) for job_id in OPEN], now=T2)
    session = FakeSession({})

    result = prune_closed_listings(engine, session, dry_run=False, now=T2, sleep=no_sleep)

    assert result == PruneResult()
    assert session.calls == []


# A limit caps how many links are followed in one run
def test_limit_caps_the_number_of_links_checked(engine):
    seed_open_and_closed(engine)
    session = FakeSession(routes_for_open_and_closed())

    result = prune_closed_listings(engine, session, dry_run=False, limit=3, now=T2, sleep=no_sleep, rng=random.Random(0))

    assert result.checked == 3
    assert len(session.calls) == 3


# --- a failed request must never delete a listing ---

# Network failures and blocked responses keep the listing and are logged with its address
def test_failed_or_blocked_requests_keep_the_listing_and_are_logged(engine, caplog):
    caplog.set_level(logging.WARNING, logger="job_pruning")
    upsert_listings(engine, [make_listing(job_id, host=f"{job_id}.example.com") for job_id in ["e1", "e2", "e3", "e4", "e5"]], now=T1)
    upsert_listings(engine, [make_listing("fresh")], now=T2)
    routes = {
        url("e1", "e1.example.com"): requests.ConnectionError("refused"),
        url("e2", "e2.example.com"): requests.Timeout("timed out"),
        url("e3", "e3.example.com"): page(500, "error"),
        url("e4", "e4.example.com"): page(403, "forbidden"),
        url("e5", "e5.example.com"): page(429, "slow down"),
    }

    result = prune_closed_listings(engine, FakeSession(routes), dry_run=False, now=T1 + timedelta(days=8), sleep=no_sleep)

    assert result.removed == 0
    assert result.unknown == 5
    assert count_listings(engine) == 6
    messages = " ".join(r.getMessage() for r in caplog.records)
    assert url("e1", "e1.example.com") in messages


# A redirect to a general careers page is not proof the job closed
def test_redirect_to_careers_page_keeps_the_listing(engine):
    upsert_listings(engine, [make_listing("r1")], now=T1)
    routes = {url("r1"): page(200, "<h1>Careers</h1>", url="https://acme.com/careers", redirected=True)}

    result = prune_closed_listings(engine, FakeSession(routes), dry_run=False, now=T1 + timedelta(days=8), sleep=no_sleep)

    assert result.removed == 0 and result.unknown == 1
    assert stored_ids(engine) == ["r1"]


# After three failures in a row a host is left alone for the rest of the run
def test_host_is_skipped_after_three_consecutive_failures(engine):
    job_ids = ["f1", "f2", "f3", "f4", "f5"]
    upsert_listings(engine, [make_listing(job_id, host="down.example.com") for job_id in job_ids], now=T1)
    session = FakeSession({url(job_id, "down.example.com"): requests.ConnectionError("refused") for job_id in job_ids})

    result = prune_closed_listings(engine, session, dry_run=False, now=T1 + timedelta(days=8), sleep=no_sleep)

    assert len(session.calls) == 3
    assert result.checked == 3
    assert result.unknown == 5
    assert count_listings(engine) == 5


# If most of a host's listings suddenly look closed, that is more likely a broken site than real closures: delete none
def test_mass_closure_on_one_host_deletes_nothing(engine, caplog):
    caplog.set_level(logging.ERROR, logger="job_pruning")
    job_ids = [f"m{i}" for i in range(24)]
    upsert_listings(engine, [make_listing(job_id, host="broken.example.com") for job_id in job_ids], now=T1)
    session = FakeSession({url(job_id, "broken.example.com"): page(404, "Not found") for job_id in job_ids})

    result = prune_closed_listings(engine, session, dry_run=False, now=T1 + timedelta(days=8), sleep=no_sleep)

    assert result.removed == 0
    assert result.closed == 24
    assert count_listings(engine) == 24
    assert any("broken.example.com" in r.getMessage() for r in caplog.records)


# --- deleting ---

# Rows in other tables that refer to a removed listing are removed with it
def test_rows_referring_to_a_removed_listing_are_removed_too(engine):
    upsert_listings(engine, [make_listing("c1"), make_listing("o1")], now=T1)
    with Session(engine) as session:
        ids = {row.source_job_id: row.id for row in session.scalars(select(JobListingTable))}
        session.execute(insert(ListingNote), [{"listing_id": ids["c1"]}, {"listing_id": ids["o1"]}])
        session.commit()
    routes = {url("c1"): page(404), url("o1"): page(200)}

    result = prune_closed_listings(engine, FakeSession(routes), dry_run=False, now=T1 + timedelta(days=8), sleep=no_sleep)

    assert result.removed == 1
    with Session(engine) as session:
        assert list(session.scalars(select(ListingNote.listing_id))) == [ids["o1"]]


# Requests to the same host are spaced out
def test_requests_to_one_host_are_paused(engine):
    seed_open_and_closed(engine)
    pauses = []

    prune_closed_listings(engine, FakeSession(routes_for_open_and_closed()), now=T2, sleep=pauses.append, pause=0.5)

    assert pauses and all(pause == 0.5 for pause in pauses)
    assert len(pauses) == 7


# --- command line ---

# The command line reports without deleting unless --delete is given
def test_cli_defaults_to_dry_run(engine, capsys):
    seed_open_and_closed(engine)

    code = prune_jobs.main([], engine=engine, session=FakeSession(routes_for_open_and_closed()), now=T2, sleep=no_sleep)

    assert code == 0
    assert count_listings(engine) == 9
    assert "dry run" in capsys.readouterr().out.lower()


# With --delete the closed listings are removed
def test_cli_delete_flag_removes_closed_listings(engine, capsys):
    seed_open_and_closed(engine)

    code = prune_jobs.main(["--delete"], engine=engine, session=FakeSession(routes_for_open_and_closed()), now=T2, sleep=no_sleep)

    assert code == 0
    assert count_listings(engine) == 5
    assert "removed 4" in capsys.readouterr().out.lower()

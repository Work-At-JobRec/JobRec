"""Persistent storage for scraped job listings, with duplicate detection.

Repeated scraper runs see the same jobs again and again. Each listing gets a
``dedupe_key`` (see ``listing_key``) and ``upsert_listings`` uses it to tell a
job that is already stored from a genuinely new one: known jobs have their
details refreshed instead of being inserted a second time.
"""

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Optional

from sqlalchemy import DateTime, Engine, Integer, String, Text, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, Session, mapped_column

from jobrec.db import Base
from jobrec.job_listing import JobListing
from jobrec.job_normalization import normalize_url

logger = logging.getLogger(__name__)

# Number of dedupe keys looked up per query; keeps SQLite's bound-parameter limit far away.
_CHUNK_SIZE = 500

# Fields refreshed from the newest sighting of a known listing.
_MUTABLE_FIELDS = (
    "title",
    "company_name",
    "location",
    "description",
    "application_url",
    "posted_at",
    "source_job_id",
    "pay",
    "status",
)


class JobListingTable(Base):
    __tablename__ = "job_listings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Identity of the job across scraper runs; see listing_key().
    dedupe_key: Mapped[str] = mapped_column(String(1024), unique=True, nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_job_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    location: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    application_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    pay: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="open")
    posted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    scraped_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    # When this job was first stored, and when a scraper last reported it.
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    # When any of the job's details last changed.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


@dataclass
class UpsertResult:
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0

    @property
    def existing(self) -> int:
        """Listings that were recognised as already stored, whether or not their details changed."""
        return self.updated + self.unchanged


def _squash(value: Optional[str]) -> str:
    return " ".join((value or "").split()).lower()


def _column_length(field: str) -> Optional[int]:
    """Maximum length of a text column, or None when it is unbounded (Text)."""
    return getattr(JobListingTable.__table__.c[field].type, "length", None)


def _fit_key(key: str) -> str:
    """Shorten a key that is too long for the dedupe_key column, keeping it unique with a hash of the full key."""
    max_length = _column_length("dedupe_key")
    if max_length is None or len(key) <= max_length:
        return key
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return key[:max_length - len(digest) - 1] + "#" + digest


def listing_key(listing: JobListing) -> str:
    """Return the string that identifies a listing across scraper runs.

    The source's own job id is used when there is one. Otherwise the (normalized)
    application URL identifies the job, and failing that the company, title, and
    location do. Known limit: if a source later starts reporting ids for a job that
    was stored under its URL, the job gets a second row.
    """
    source = listing.source.strip().lower()
    job_id = (listing.source_job_id or "").strip()
    if job_id:
        return _fit_key(f"{source}:id:{job_id}")
    url = normalize_url(listing.application_url)
    if url:
        return _fit_key(f"{source}:url:{url}")
    fields = "|".join(_squash(v) for v in (listing.company_name, listing.title, listing.location))
    return _fit_key(f"{source}:fields:{fields}")


def _to_db(value: Optional[datetime]) -> Optional[datetime]:
    """Timezone-aware UTC on the way in. SQLite ignores tzinfo, so converting first keeps the instant right."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _from_db(value: Optional[datetime]) -> Optional[datetime]:
    """Timezone-aware UTC on the way out. SQLite returns naive values (already UTC); Postgres returns aware ones."""
    return _to_db(value)


def to_job_listing(row: JobListingTable) -> JobListing:
    """Convert a stored row back into the standardized JobListing model."""
    return JobListing(
        title=row.title,
        company_name=row.company_name,
        location=row.location,
        description=row.description,
        source=row.source,
        application_url=row.application_url,
        posted_at=_from_db(row.posted_at),
        scraped_at=_from_db(row.scraped_at),
        source_job_id=row.source_job_id,
        pay=row.pay,
        status=row.status,
    )


def _text_for_db(value: str, field: str) -> str:
    """Text as the column can hold it: no NUL bytes (Postgres rejects them) and no longer than the column.

    SQLite ignores column lengths but Postgres raises on an over-long value, which would
    fail the commit and lose the whole batch.
    """
    value = value.replace("\x00", "")
    max_length = _column_length(field)
    return value[:max_length] if max_length is not None else value


def _value_for_db(listing: JobListing, field: str):
    value = getattr(listing, field)
    if isinstance(value, datetime):
        return _to_db(value)
    if isinstance(value, str):
        return _text_for_db(value, field)
    return value


def _apply_changes(row: JobListingTable, listing: JobListing) -> bool:
    """Copy any changed details from the listing onto the row. Returns True if something changed."""
    changed = False
    for field in _MUTABLE_FIELDS:
        new_value = _value_for_db(listing, field)
        old_value = getattr(row, field)
        if isinstance(old_value, datetime):
            old_value = _from_db(old_value)
        if old_value != new_value:
            setattr(row, field, new_value)
            changed = True
    return changed


def upsert_listings(
    engine: Engine, listings: Iterable[JobListing], *, now: Optional[datetime] = None
) -> UpsertResult:
    """Store listings, updating the ones already known instead of duplicating them.

    Duplicates inside the batch collapse to the last occurrence. ``now`` is the
    sighting time used for the first/last-seen columns (defaults to the current UTC time).
    """
    now = _to_db(now or datetime.now(timezone.utc))
    by_key: dict[str, JobListing] = {}
    for listing in listings:
        by_key[listing_key(listing)] = listing
    if not by_key:
        return UpsertResult()

    try:
        result = _upsert_once(engine, by_key, now)
    except IntegrityError:
        # Another run stored one of these new listings between our lookup and our insert.
        # Looking again finds it as existing, so a single retry settles it.
        logger.warning("Concurrent insert detected while storing job listings; retrying once")
        result = _upsert_once(engine, by_key, now)

    logger.info(
        "Stored job listings: %d inserted, %d updated, %d unchanged", result.inserted, result.updated, result.unchanged,
    )
    return result


def _upsert_once(engine: Engine, by_key: dict[str, JobListing], now: datetime) -> UpsertResult:
    """Insert or update every listing in one transaction."""
    result = UpsertResult()
    keys = list(by_key)
    with Session(engine) as session:
        existing: dict[str, JobListingTable] = {}
        for start in range(0, len(keys), _CHUNK_SIZE):
            chunk = keys[start : start + _CHUNK_SIZE]
            for row in session.scalars(
                select(JobListingTable).where(JobListingTable.dedupe_key.in_(chunk))
            ):
                existing[row.dedupe_key] = row

        for key, listing in by_key.items():
            row = existing.get(key)
            if row is None:
                row = JobListingTable(
                    dedupe_key=key, source=_text_for_db(listing.source, "source"), first_seen_at=now, updated_at=now,
                )
                _apply_changes(row, listing)
                session.add(row)
                result.inserted += 1
            elif _apply_changes(row, listing):
                row.updated_at = now
                result.updated += 1
            else:
                result.unchanged += 1
            row.scraped_at = _to_db(listing.scraped_at)
            row.last_seen_at = now
        session.commit()
    return result


def list_listings(engine: Engine, limit: Optional[int] = None) -> list[JobListing]:
    """Return stored listings in the order they were first stored."""
    query = select(JobListingTable).order_by(JobListingTable.id)
    if limit is not None:
        query = query.limit(limit)
    with Session(engine) as session:
        return [to_job_listing(row) for row in session.scalars(query)]


def count_listings(engine: Engine) -> int:
    with Session(engine) as session:
        return session.scalar(select(func.count()).select_from(JobListingTable)) or 0


def list_recent_listings(engine: Engine, limit: int, description_chars: Optional[int] = None) -> list[JobListing]:
    """Return up to ``limit`` stored listings, most recently posted first.

    A listing with no posting date is placed by when it was first seen. Listings without a
    source job id are left out, since they have no stable id to link to. When
    ``description_chars`` is given, the description is cut to that length in the database,
    so a page of listings does not pull every full description over the wire.
    """
    table = JobListingTable.__table__
    description = table.c.description
    if description_chars is not None:
        description = func.substr(table.c.description, 1, description_chars).label("description")
    columns = [column for column in table.c if column.name != "description"] + [description]
    query = (
        select(*columns)
        .where(table.c.source_job_id.is_not(None))
        # coalesce keeps the order the same on SQLite and Postgres, which sort NULLs differently.
        .order_by(func.coalesce(table.c.posted_at, table.c.first_seen_at).desc(), table.c.id.desc())
        .limit(limit)
    )
    with Session(engine) as session:
        return [to_job_listing(row) for row in session.execute(query)]


def get_listing(engine: Engine, source: str, source_job_id: str) -> Optional[JobListing]:
    """Return the stored listing with this source and source job id, or None."""
    key = _fit_key(f"{source.strip().lower()}:id:{source_job_id.strip()}")
    with Session(engine) as session:
        row = session.scalar(select(JobListingTable).where(JobListingTable.dedupe_key == key))
        return to_job_listing(row) if row is not None else None

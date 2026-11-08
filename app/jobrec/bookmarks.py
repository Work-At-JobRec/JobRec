"""Jobs a user has bookmarked, served to the frontend via /api/bookmarks.

A bookmark stores the job's API id (the same id used in /jobs/<id>), not a row id
in job_listings, so it survives the scraper refreshing a listing.
"""

from datetime import datetime, timezone

from sqlalchemy import DateTime, Engine, String, delete, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from jobrec.db import Base
from jobrec.jobs import get_jobs_by_id


class BookmarkTable(Base):
    __tablename__ = "bookmarks"

    user_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    job_id: Mapped[str] = mapped_column(String(512), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


def is_bookmarked(engine: Engine, user_id: str, job_id: str) -> bool:
    with Session(engine) as session:
        return session.get(BookmarkTable, (user_id, job_id)) is not None


def add_bookmark(engine: Engine, user_id: str, job_id: str) -> None:
    """Bookmark a job; bookmarking it again keeps the original time."""
    with Session(engine) as session:
        if session.get(BookmarkTable, (user_id, job_id)) is None:
            session.add(
                BookmarkTable(user_id=user_id, job_id=job_id, created_at=datetime.now(timezone.utc))
            )
            session.commit()


def remove_bookmark(engine: Engine, user_id: str, job_id: str) -> None:
    with Session(engine) as session:
        session.execute(
            delete(BookmarkTable).where(BookmarkTable.user_id == user_id, BookmarkTable.job_id == job_id)
        )
        session.commit()


def get_bookmarked_jobs(engine: Engine, user_id: str) -> list[dict[str, object]]:
    """The user's bookmarked jobs, most recently bookmarked first.

    Bookmarks whose job is no longer listed (closed or removed) are left out.
    """
    with Session(engine) as session:
        job_ids = list(
            session.scalars(
                select(BookmarkTable.job_id)
                .where(BookmarkTable.user_id == user_id)
                .order_by(BookmarkTable.created_at.desc())
            )
        )
    if not job_ids:
        return []
    jobs = get_jobs_by_id(engine, user_id)
    return [jobs[job_id] for job_id in job_ids if job_id in jobs]

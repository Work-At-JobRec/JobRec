"""Jobs a user has saved to one of their lists, served via /api/bookmarks and /api/applied.

LISTS names the lists: "bookmarks" (jobs the user bookmarked) and "applied" (jobs
the user pressed Apply Now on). A saved job stores the job's API id (the same id
used in /jobs/<id>), not a row id in job_listings, so it survives the scraper
refreshing a listing.
"""

from datetime import datetime, timezone

from sqlalchemy import DateTime, Engine, String, delete, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from jobrec.db import Base
from jobrec.jobs import get_jobs_by_id

LISTS = ("bookmarks", "applied")


class SavedJobTable(Base):
    __tablename__ = "saved_jobs"

    user_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    list_name: Mapped[str] = mapped_column(String(32), primary_key=True)
    job_id: Mapped[str] = mapped_column(String(512), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


def is_saved(engine: Engine, user_id: str, list_name: str, job_id: str) -> bool:
    with Session(engine) as session:
        return session.get(SavedJobTable, (user_id, list_name, job_id)) is not None


def save_job(engine: Engine, user_id: str, list_name: str, job_id: str) -> None:
    """Add a job to the list; adding it again keeps the original time."""
    with Session(engine) as session:
        if session.get(SavedJobTable, (user_id, list_name, job_id)) is None:
            session.add(
                SavedJobTable(
                    user_id=user_id,
                    list_name=list_name,
                    job_id=job_id,
                    created_at=datetime.now(timezone.utc),
                )
            )
            session.commit()


def unsave_job(engine: Engine, user_id: str, list_name: str, job_id: str) -> None:
    with Session(engine) as session:
        session.execute(
            delete(SavedJobTable).where(
                SavedJobTable.user_id == user_id,
                SavedJobTable.list_name == list_name,
                SavedJobTable.job_id == job_id,
            )
        )
        session.commit()


def get_saved_jobs(engine: Engine, user_id: str, list_name: str) -> list[dict[str, object]]:
    """The jobs on the user's list, most recently added first.

    Jobs that are no longer listed (closed or removed) are left out.
    """
    with Session(engine) as session:
        job_ids = list(
            session.scalars(
                select(SavedJobTable.job_id)
                .where(SavedJobTable.user_id == user_id, SavedJobTable.list_name == list_name)
                .order_by(SavedJobTable.created_at.desc())
            )
        )
    if not job_ids:
        return []
    jobs = get_jobs_by_id(engine, user_id)
    return [jobs[job_id] for job_id in job_ids if job_id in jobs]

import os
import sys

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

# Lets this test import app/src/scrape_pipeline.py
SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, SRC_DIR)

from jobrec.db import Base  # noqa: E402
from jobrec.job_listing import JobListing  # noqa: E402
from jobrec.job_store import (
    JobListingTable,
    UpsertResult,
    count_listings,
    list_listings,
)  # noqa: E402
from jobrec.listing_skill_extractor import extract_pending_listing_skills  # noqa: E402
from jobrec.scrape_pipeline import run_scrape_pipeline  # noqa: E402
from jobrec.scraper_base import BaseScraper, ScraperRequestError  # noqa: E402
from jobrec.skill_detection import (  # noqa: E402
    CanonicalSkillTable,
    DiscoveredSkill,
    ListingSkillTable,
    SkillRanking,
    save_listing_skill_analysis,
)


@pytest.fixture
def engine(tmp_path):
    test_engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'jobs.db'}")
    Base.metadata.create_all(test_engine)
    return test_engine


class FixedScraper(BaseScraper):
    """Returns a fixed set of listings without touching the network."""

    source_name = "fixed"

    def __init__(self, listings: list[JobListing]):
        self._listings = listings

    def fetch_jobs(self) -> list[JobListing]:
        return list(self._listings)


class UnreachableScraper(BaseScraper):
    source_name = "unreachable"

    def __init__(self):
        pass

    def fetch_jobs(self) -> list[JobListing]:
        raise ScraperRequestError(
            self.source_name, "https://down.example.com/jobs", "connection refused"
        )


def raw_listing(**overrides) -> JobListing:
    """A listing the way a scraper produces it: HTML description, tracking parameters, untidy whitespace."""
    fields = {
        "title": "  Software   Engineer ",
        "company_name": "Acme",
        "source": "fixed",
        "application_url": "https://acme.com/jobs/1?utm_source=newsletter",
        "description": "<p>Build <strong>things</strong>.</p>",
        "source_job_id": "1",
    }
    fields.update(overrides)
    return JobListing(**fields)


# Scraped listings are cleaned, checked, stored, and marked for deferred extraction
def test_pipeline_normalizes_validates_and_stores(engine):
    scraper = FixedScraper([raw_listing(), raw_listing(title="", source_job_id="2")])

    result = run_scrape_pipeline(engine, [scraper])

    assert result == UpsertResult(inserted=1, updated=0, unchanged=0)
    assert count_listings(engine) == 1
    stored = list_listings(engine)[0]
    assert stored.title == "Software Engineer"
    assert stored.description == "Build things."
    assert stored.application_url == "https://acme.com/jobs/1"
    with Session(engine) as session:
        assert session.scalar(select(JobListingTable.skills_pending)) is True


# Running the pipeline again over the same source adds nothing new
def test_pipeline_second_run_reports_existing_not_new(engine):
    scraper = FixedScraper([raw_listing()])
    run_scrape_pipeline(engine, [scraper])

    result = run_scrape_pipeline(engine, [scraper])

    assert result == UpsertResult(inserted=0, updated=0, unchanged=1)
    assert count_listings(engine) == 1


# A source that cannot be reached does not stop the others from being stored
def test_pipeline_continues_past_unreachable_scraper(engine):
    result = run_scrape_pipeline(
        engine, [UnreachableScraper(), FixedScraper([raw_listing()])]
    )

    assert result.inserted == 1
    assert count_listings(engine) == 1


# A listing that no longer accepts applicants is never stored
def test_pipeline_does_not_store_closed_listings(engine):
    scraper = FixedScraper(
        [raw_listing(), raw_listing(source_job_id="2", status="closed")]
    )

    result = run_scrape_pipeline(engine, [scraper])

    assert result.inserted == 1
    assert [job.source_job_id for job in list_listings(engine)] == ["1"]


def test_scrape_pipeline_does_not_call_skill_detector(engine, monkeypatch):
    def unexpected_detection(*args, **kwargs):
        pytest.fail("scraping must not call the OpenAI skill detector")

    monkeypatch.setattr(
        "jobrec.skill_detection.detect_document_skills", unexpected_detection
    )

    result = run_scrape_pipeline(engine, [FixedScraper([raw_listing()])])

    assert result.inserted == 1
    with Session(engine) as session:
        assert session.scalar(select(JobListingTable.skills_pending)) is True


def test_description_updates_requeue_skill_extraction(engine):
    original = raw_listing()
    run_scrape_pipeline(engine, [FixedScraper([original])])
    key = "fixed:id:1"
    assert save_listing_skill_analysis(
        engine,
        key,
        "Build things.",
        [SkillRanking(skill_name="Python", proficiency_level=3)],
        [],
    )

    run_scrape_pipeline(
        engine,
        [FixedScraper([raw_listing(title="Senior Engineer")])],
    )
    with Session(engine) as session:
        assert session.scalar(select(JobListingTable.skills_pending)) is False

    run_scrape_pipeline(
        engine,
        [FixedScraper([raw_listing(description="<p>Build different things.</p>")])],
    )
    with Session(engine) as session:
        assert session.scalar(select(JobListingTable.skills_pending)) is True


def test_pending_skill_extractor_saves_results_and_skips_completed_listings(
    engine, monkeypatch
):
    run_scrape_pipeline(engine, [FixedScraper([raw_listing()])])
    calls = []

    def detect_skills(
        document_text, catalog, *, document_type, candidate_cap
    ):
        calls.append((document_text, document_type))
        return [], [
            DiscoveredSkill(
                skill_name="Novel Framework",
                proficiency_level=3,
            )
        ]

    monkeypatch.setattr(
        "jobrec.listing_skill_extractor.detect_document_skills", detect_skills
    )
    result = extract_pending_listing_skills(engine, limit=10)

    assert result.processed == 1
    assert result.failed == result.stale == result.pending == 0
    assert calls == [("Build things.", "job listing")]
    with Session(engine) as session:
        skill = session.scalars(
            select(CanonicalSkillTable).where(
                CanonicalSkillTable.normalized_name == "novel framework"
            )
        ).one()
        associations = list(session.scalars(select(ListingSkillTable)))
    assert len(associations) == 1
    assert associations[0].skill_id == skill.id
    assert associations[0].proficiency_level == 3

    result = extract_pending_listing_skills(engine, limit=10)

    assert result.processed == result.failed == result.stale == result.pending == 0
    assert len(calls) == 1


def test_pending_skill_extractor_respects_limit(engine, monkeypatch):
    run_scrape_pipeline(
        engine,
        [
            FixedScraper(
                [
                    raw_listing(source_job_id="1"),
                    raw_listing(source_job_id="2"),
                ]
            )
        ],
    )
    monkeypatch.setattr(
        "jobrec.listing_skill_extractor.detect_document_skills",
        lambda *args, **kwargs: ([], []),
    )

    result = extract_pending_listing_skills(engine, limit=1)

    assert result.processed == 1
    assert result.pending == 1


def test_pending_skill_extractor_passes_candidate_cap(engine, monkeypatch):
    run_scrape_pipeline(engine, [FixedScraper([raw_listing()])])
    received = []

    def detect_skills(document_text, catalog, *, document_type, candidate_cap):
        received.append(candidate_cap)
        return [], []

    monkeypatch.setattr(
        "jobrec.listing_skill_extractor.detect_document_skills", detect_skills
    )

    extract_pending_listing_skills(engine, limit=1, candidate_cap=25)

    assert received == [25]


def test_failed_skill_extraction_remains_pending(engine, monkeypatch):
    run_scrape_pipeline(engine, [FixedScraper([raw_listing()])])

    def fail_detection(*args, **kwargs):
        raise RuntimeError("API unavailable")

    monkeypatch.setattr(
        "jobrec.listing_skill_extractor.detect_document_skills", fail_detection
    )

    result = extract_pending_listing_skills(engine, limit=1)

    assert result.failed == 1
    assert result.pending == 1

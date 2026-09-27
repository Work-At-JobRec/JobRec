import json
import logging
import os
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine

# Lets this test import app/src/job_sources.py
SRC_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "src")
)
sys.path.insert(0, SRC_DIR)

from db import Base  # noqa: E402
from greenhouse_scraper import GreenhouseScraper  # noqa: E402
from job_listing import JobListing  # noqa: E402
from job_sources import DEFAULT_SOURCES_PATH, JobSource, build_scraper, load_sources, scrape_all  # noqa: E402
from job_store import count_listings, list_listings  # noqa: E402
from lever_scraper import LeverScraper  # noqa: E402
from scraper_base import BaseScraper, ScraperRequestError  # noqa: E402
from workday_scraper import WorkdayScraper  # noqa: E402


@pytest.fixture
def engine(tmp_path):
    test_engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'jobs.db'}")
    Base.metadata.create_all(test_engine)
    return test_engine


def write_sources(path: Path, sources: list) -> Path:
    path.write_text(json.dumps({"sources": sources}), encoding="utf-8")
    return path


class FakeScraper(BaseScraper):
    """Stands in for a real scraper: returns one listing per title it was built with."""

    source_name = "fake"

    def __init__(self, board, company_name=None, session=None):
        self.board = board
        self.company_name = company_name or board

    def fetch_jobs(self) -> list[JobListing]:
        if self.board == "down":
            raise ScraperRequestError(self.source_name, "https://fake.example.com/down", "refused")
        return [
            JobListing(title=f"{self.board} job", company_name=self.company_name, source=self.source_name,
                       application_url=f"https://fake.example.com/{self.board}/1", source_job_id=f"{self.board}-1"),
        ]


# --- loading ---

# The checked-in registry loads and every entry names a supported scraper
def test_default_registry_loads_and_names_supported_scrapers():
    sources = load_sources(DEFAULT_SOURCES_PATH)

    assert len(sources) >= 1
    for source in sources:
        assert isinstance(build_scraper(source), BaseScraper)


# Each entry becomes a JobSource with its fields, and enabled defaults to true
def test_load_sources_reads_entries(tmp_path):
    path = write_sources(tmp_path / "sources.json", [
        {"scraper": "greenhouse", "id": "acme", "company_name": "Acme Corp"},
        {"scraper": "lever", "id": "beta", "enabled": False},
    ])

    sources = load_sources(path)

    assert sources == [
        JobSource(scraper="greenhouse", id="acme", company_name="Acme Corp", enabled=True),
        JobSource(scraper="lever", id="beta", company_name=None, enabled=False),
    ]


# An entry naming a scraper that does not exist is rejected when the registry is loaded
def test_load_sources_rejects_unknown_scraper(tmp_path):
    path = write_sources(tmp_path / "sources.json", [{"scraper": "monster", "id": "acme"}])

    with pytest.raises(ValueError, match="monster"):
        load_sources(path)


# An entry without an id is rejected
def test_load_sources_rejects_missing_id(tmp_path):
    path = write_sources(tmp_path / "sources.json", [{"scraper": "greenhouse"}])

    with pytest.raises(ValueError):
        load_sources(path)


# --- building scrapers ---

# Each scraper type is built with the entry's id and company name
def test_build_scraper_constructs_the_right_type():
    greenhouse = build_scraper(JobSource(scraper="greenhouse", id="acme", company_name="Acme"))
    lever = build_scraper(JobSource(scraper="lever", id="beta"))
    workday = build_scraper(JobSource(scraper="workday", id="acme.wd5.myworkdayjobs.com/AcmeCareers", company_name="Acme"))

    assert isinstance(greenhouse, GreenhouseScraper)
    assert greenhouse.board_token == "acme" and greenhouse.company_name == "Acme"
    assert isinstance(lever, LeverScraper)
    assert lever.company == "beta" and lever.company_name is None
    assert isinstance(workday, WorkdayScraper)
    assert workday.site == "AcmeCareers" and workday.company_name == "Acme"


# --- scraping every source ---

# Every enabled source is scraped and stored, with a result reported per source
def test_scrape_all_runs_every_enabled_source(engine, monkeypatch):
    monkeypatch.setitem(__import__("job_sources").SCRAPER_TYPES, "fake", FakeScraper)
    sources = [JobSource(scraper="fake", id="one"), JobSource(scraper="fake", id="two")]

    results = scrape_all(engine, sources)

    assert [name for name, _ in results] == ["fake:one", "fake:two"]
    assert all(result.inserted == 1 for _, result in results)
    assert count_listings(engine) == 2
    assert sorted(job.title for job in list_listings(engine)) == ["one job", "two job"]


# Disabled sources are skipped and do not appear in the results
def test_scrape_all_skips_disabled_sources(engine, monkeypatch):
    monkeypatch.setitem(__import__("job_sources").SCRAPER_TYPES, "fake", FakeScraper)
    sources = [JobSource(scraper="fake", id="one"), JobSource(scraper="fake", id="two", enabled=False)]

    results = scrape_all(engine, sources)

    assert [name for name, _ in results] == ["fake:one"]
    assert count_listings(engine) == 1


# A source that fails is logged and the rest are still scraped
def test_scrape_all_continues_past_failing_source(engine, monkeypatch, caplog):
    monkeypatch.setitem(__import__("job_sources").SCRAPER_TYPES, "fake", FakeScraper)
    caplog.set_level(logging.INFO, logger="job_sources")
    sources = [JobSource(scraper="fake", id="down"), JobSource(scraper="fake", id="two")]

    results = scrape_all(engine, sources)

    assert [(name, result.inserted) for name, result in results] == [("fake:down", 0), ("fake:two", 1)]
    assert count_listings(engine) == 1
    assert any("fake:down" in r.getMessage() for r in caplog.records)


# Running again over the same sources adds nothing new
def test_scrape_all_second_run_adds_nothing(engine, monkeypatch):
    monkeypatch.setitem(__import__("job_sources").SCRAPER_TYPES, "fake", FakeScraper)
    sources = [JobSource(scraper="fake", id="one")]
    scrape_all(engine, sources)

    results = scrape_all(engine, sources)

    assert results[0][1].inserted == 0 and results[0][1].existing == 1
    assert count_listings(engine) == 1


# No sources means no work and an empty result
def test_scrape_all_with_no_sources(engine):
    assert scrape_all(engine, []) == []
    assert count_listings(engine) == 0

"""Tests for the narrated scrape run used in demos (jobrec.scrape_demo)."""

import pytest

from jobrec.job_listing import JobListing
from jobrec.job_sources import JobSource
from jobrec.job_store import count_listings, list_listings
from jobrec.scrape_demo import main, run_demo
from jobrec.scraper_base import BaseScraper, ScraperRequestError


class FixedScraper(BaseScraper):
    source_name = "fixed"

    def __init__(self, listings):
        self._listings = listings

    def fetch_jobs(self):
        return list(self._listings)


class UnreachableScraper(BaseScraper):
    source_name = "unreachable"

    def __init__(self):
        pass

    def fetch_jobs(self):
        raise ScraperRequestError(self.source_name, "https://down.example.com/jobs", "connection refused")


def listing(job_id: str, **overrides) -> JobListing:
    fields = {
        "title": f"  Engineer {job_id} ",
        "company_name": "Acme",
        "source": "fixed",
        "application_url": f"https://acme.com/jobs/{job_id}?utm_source=x",
        "description": "<p>Build things.</p>",
        "source_job_id": job_id,
        "location": "Remote",
        "pay": "$100k",
    }
    fields.update(overrides)
    return JobListing(**fields)


def source(name: str) -> JobSource:
    return JobSource(scraper="greenhouse", id=name, company_name=name.title())


# Each source is narrated stage by stage and the database count grows as listings are stored
def test_demo_narrates_each_stage_and_stores_listings(engine):
    lines = []
    scrapers = {
        "greenhouse:acme": FixedScraper([listing("1"), listing("2"), listing("3", status="closed")]),
        "greenhouse:beta": FixedScraper([listing("4", title=""), listing("5")]),
    }

    results = run_demo(
        engine, [source("acme"), source("beta")], build=lambda s: scrapers[s.name], out=lines.append
    )

    text = "\n".join(lines)
    assert count_listings(engine) == 3
    assert [r.inserted for _, r in results] == [2, 1]
    assert "[1/2] greenhouse:acme" in text and "[2/2] greenhouse:beta" in text
    assert "fetched 3 listings" in text and "2 open, 1 closed" in text
    assert "1 rejected" in text  # beta's listing with an empty title
    assert "database now holds 2 listings" in text
    assert "database now holds 3 listings" in text
    assert "Engineer 1" in text  # a stored listing is shown as a sample row
    assert "3 listings stored in total" in text


# Stored listings are the cleaned versions, not the raw scraped ones
def test_demo_stores_normalized_listings(engine):
    run_demo(engine, [source("acme")], build=lambda s: FixedScraper([listing("1")]), out=lambda _: None)

    stored = list_listings(engine)[0]
    assert stored.title == "Engineer 1"
    assert stored.application_url == "https://acme.com/jobs/1"
    assert stored.description == "Build things."


# A second run over the same source stores nothing new and creates no duplicates
def test_demo_second_run_reports_unchanged(engine):
    build = lambda s: FixedScraper([listing("1"), listing("2")])  # noqa: E731
    run_demo(engine, [source("acme")], build=build, out=lambda _: None)
    lines = []

    results = run_demo(engine, [source("acme")], build=build, out=lines.append)

    assert count_listings(engine) == 2
    assert results[0][1].inserted == 0 and results[0][1].unchanged == 2
    assert "0 new, 0 updated, 2 unchanged" in "\n".join(lines)


# A source that cannot be reached is reported and the run carries on
def test_demo_continues_past_unreachable_source(engine):
    lines = []
    scrapers = {"greenhouse:down": UnreachableScraper(), "greenhouse:acme": FixedScraper([listing("1")])}

    results = run_demo(
        engine, [source("down"), source("acme")], build=lambda s: scrapers[s.name], out=lines.append
    )

    text = "\n".join(lines)
    assert count_listings(engine) == 1
    assert len(results) == 1 and results[0][0] == "greenhouse:acme"
    assert "greenhouse:down" in text and "connection refused" in text


# The command line creates the database file it is pointed at and starts it empty with --fresh
def test_main_fresh_creates_empty_database_then_fills_it(tmp_path, monkeypatch):
    db = tmp_path / "demo_scrape.db"
    registry = tmp_path / "sources.json"
    registry.write_text('{"sources": [{"scraper": "greenhouse", "id": "acme", "company_name": "Acme"}]}')
    monkeypatch.setattr("jobrec.scrape_demo.build_scraper", lambda s: FixedScraper([listing("1")]))
    lines = []

    code = main(["--sources", str(registry), "--database", str(db), "--fresh", "--pause", "0"], out=lines.append)

    assert code == 0
    assert db.exists()
    assert "database now holds 1 listing" in "\n".join(lines)


# --only restricts the run to the named sources, matching whole names or prefixes
def test_main_only_selects_matching_sources(tmp_path, monkeypatch):
    registry = tmp_path / "sources.json"
    registry.write_text(
        '{"sources": [{"scraper": "greenhouse", "id": "acme"}, {"scraper": "greenhouse", "id": "beta"},'
        ' {"scraper": "lever", "id": "gamma"}]}'
    )
    monkeypatch.setattr("jobrec.scrape_demo.build_scraper", lambda s: FixedScraper([listing(s.id)]))
    lines = []

    main(["--sources", str(registry), "--database", str(tmp_path / "d.db"), "--pause", "0",
          "--only", "greenhouse:beta,lever"], out=lines.append)

    text = "\n".join(lines)
    assert "greenhouse:acme" not in text
    assert "[1/2] greenhouse:beta" in text and "[2/2] lever:gamma" in text


# --fresh refuses to delete anything but the demo database file
def test_main_fresh_refuses_to_delete_other_databases(tmp_path):
    other = tmp_path / "user_skills.db"
    other.write_bytes(b"keep me")

    with pytest.raises(SystemExit):
        main(["--database", str(other), "--fresh", "--pause", "0"], out=lambda _: None)

    assert other.read_bytes() == b"keep me"

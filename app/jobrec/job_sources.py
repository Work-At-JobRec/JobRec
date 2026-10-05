"""Registry of job sources to scrape, and the entry point that scrapes all of them.

The registry is the checked-in ``job_sources.json`` next to this module: a list
of entries naming which scraper handles a source and the source's identifier
(a Greenhouse board token, a Lever company slug, ...). Adding a company means
adding a line to that file, not changing code. ``scrape_all`` runs the full
pipeline (fetch, normalize, validate, store) once per enabled source, so one
failing source never affects the others.
"""

import json
import logging
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import Engine

from app.jobrec.greenhouse_scraper import GreenhouseScraper
from app.jobrec.job_store import UpsertResult
from app.jobrec.lever_scraper import LeverScraper
from app.jobrec.scrape_pipeline import run_scrape_pipeline
from app.jobrec.scraper_base import BaseScraper
from app.jobrec.workday_scraper import WorkdayScraper

logger = logging.getLogger(__name__)

DEFAULT_SOURCES_PATH = Path(__file__).with_name("job_sources.json")

# Scraper name as written in the registry -> class. Every class takes (id, company_name=...).
SCRAPER_TYPES: dict[str, type] = {
    "greenhouse": GreenhouseScraper,
    "lever": LeverScraper,
    "workday": WorkdayScraper,
}


class JobSource(BaseModel):
    scraper: str = Field(
        ...,
        description='Which scraper handles this source, e.g. "greenhouse" or "lever"',
    )
    id: str = Field(
        ...,
        min_length=1,
        description="The source's identifier for that scraper, such as a board token",
    )
    company_name: Optional[str] = Field(
        None,
        description="Display name of the company; the scraper's own value is used if empty",
    )
    enabled: bool = Field(
        True, description="Disabled sources stay in the registry but are not scraped"
    )

    @field_validator("scraper")
    @classmethod
    def _known_scraper(cls, value: str) -> str:
        if value not in SCRAPER_TYPES:
            raise ValueError(
                f"unknown scraper {value!r}; expected one of {sorted(SCRAPER_TYPES)}"
            )
        return value

    @property
    def name(self) -> str:
        """Short label used in logs and results, e.g. "greenhouse:stripe"."""
        return f"{self.scraper}:{self.id}"


def load_sources(path: Path = DEFAULT_SOURCES_PATH) -> list[JobSource]:
    """Read the registry file. Raises ValueError if an entry is malformed or names an unknown scraper."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return [JobSource.model_validate(entry) for entry in data.get("sources", [])]


def build_scraper(source: JobSource) -> BaseScraper:
    """Construct the scraper that handles a registry entry."""
    scraper_class = SCRAPER_TYPES[source.scraper]
    return scraper_class(source.id, company_name=source.company_name)


def scrape_all(
    engine: Engine, sources: list[JobSource]
) -> list[tuple[str, UpsertResult]]:
    """Scrape every enabled source into the database, returning (source name, result) per source in order."""
    results: list[tuple[str, UpsertResult]] = []
    for source in sources:
        if not source.enabled:
            logger.info("Skipping disabled source %s", source.name)
            continue
        result = run_scrape_pipeline(engine, [build_scraper(source)])
        logger.info(
            "Source %s: %d new, %d updated, %d unchanged",
            source.name,
            result.inserted,
            result.updated,
            result.unchanged,
        )
        results.append((source.name, result))
    total_new = sum(result.inserted for _, result in results)
    logger.info(
        "Scraped %d source(s): %d new listing(s) stored", len(results), total_new
    )
    return results

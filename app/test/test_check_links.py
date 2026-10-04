import os
import random
import sys

import requests

# Lets this test import app/src/check_links.py
SRC_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "src")
)
sys.path.insert(0, SRC_DIR)

from check_links import check_stored_links  # noqa: E402
from job_listing import JobListing  # noqa: E402
from job_store import upsert_listings  # noqa: E402
from link_fakes import FakeSession, page  # noqa: E402


def make_listing(job_id: str, title: str = "Software Engineer", company: str = "Acme") -> JobListing:
    return JobListing(title=title, company_name=company, source="greenhouse",
                      application_url=f"https://acme.com/jobs/{job_id}", source_job_id=job_id)


def no_sleep(seconds):
    return None


# Each sampled link is classed by whether it resolves and whether the page is about the stored job
def test_report_counts_resolved_and_matching_links(engine):
    upsert_listings(engine, [
        make_listing("title", title="Data Scientist"),
        make_listing("company", title="Unusual Title", company="Globex"),
        make_listing("generic"),
        make_listing("gone"),
        make_listing("down"),
    ])
    session = FakeSession({
        "https://acme.com/jobs/title": page(200, "<h1>Data Scientist</h1>"),
        "https://acme.com/jobs/company": page(200, "<h1>Work at Globex</h1>"),
        "https://acme.com/jobs/generic": page(200, "<div id='root'></div>"),
        "https://acme.com/jobs/gone": page(404, "Not found"),
        "https://acme.com/jobs/down": requests.ConnectionError("refused"),
    })

    report = check_stored_links(engine, session, sample_size=100, sleep=no_sleep)

    assert report.sampled == 5
    assert report.resolved == 3
    assert report.matched == 2
    assert report.resolved_share == 0.6
    assert report.matched_share == 0.4
    assert sorted(url.rsplit("/", 1)[-1] for url, _ in report.problems) == ["down", "generic", "gone"]


# Pages rendered in the browser name the job only in their metadata; that still counts as being about the job
def test_title_in_page_metadata_counts_as_a_match(engine):
    upsert_listings(engine, [make_listing("meta", title="Renewals Manager"), make_listing("ld", title="Site Reliability Engineer")])
    session = FakeSession({
        "https://acme.com/jobs/meta": page(200, '<head><meta property="og:title" content="Renewals Manager"></head><div id="root"></div>'),
        "https://acme.com/jobs/ld": page(200, '<script type="application/ld+json">{"title": "Site Reliability Engineer"}</script><div id="root"></div>'),
    })

    report = check_stored_links(engine, session, sleep=no_sleep)

    assert report.resolved == 2
    assert report.matched == 2
    assert report.problems == []


# Only the requested number of links is sampled
def test_sample_size_caps_the_links_checked(engine):
    upsert_listings(engine, [make_listing(str(i)) for i in range(10)])
    session = FakeSession({f"https://acme.com/jobs/{i}": page(200, "<h1>Software Engineer</h1>") for i in range(10)})

    report = check_stored_links(engine, session, sample_size=4, sleep=no_sleep, rng=random.Random(1))

    assert report.sampled == 4
    assert len(session.calls) == 4


# An empty database gives an empty report rather than a division error
def test_empty_database_gives_an_empty_report(engine):
    report = check_stored_links(engine, FakeSession({}), sleep=no_sleep)

    assert report.sampled == 0
    assert report.resolved_share == 0.0 and report.matched_share == 0.0

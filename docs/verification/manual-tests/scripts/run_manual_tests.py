"""Manual verification runs for TC-015, TC-027 and TC-028 (JobRec, Pranav's rows).

Usage (from app/, PYTHONPATH=.):  python run_manual_tests.py <tc015|tc027|tc028> [sqlite db path]
Every step prints what it does and what it found, so the console output is the evidence log.
"""
import html
import json
import platform
import random
import sys
from datetime import datetime, timezone

import requests
from sqlalchemy import create_engine, text

from jobrec.job_normalization import _collapse_whitespace, clean_text, normalize_url
from jobrec.job_sources import JobSource
from jobrec.job_store import count_listings, list_listings, upsert_listings
from jobrec.scrape_all import scrape_sources
from jobrec.workday_scraper import WorkdayScraper

CONTROLLED = [
    JobSource(scraper="greenhouse", id="figma", company_name="Figma"),
    JobSource(scraper="lever", id="palantir", company_name="Palantir"),
    JobSource(scraper="ashby", id="ramp", company_name="Ramp"),
]


def header(name):
    print(f"=== {name} | run at {datetime.now(timezone.utc).isoformat(timespec='seconds')} UTC")
    print(f"    python {platform.python_version()} on {platform.system()} {platform.release()}")


def tc015():
    header("TC-015 live Workday crawl, first 5 pages per site")
    with open("jobrec/job_sources_demo.json", encoding="utf-8") as fh:
        sites = [(s["id"], s["company_name"]) for s in json.load(fh)["sources"] if s["scraper"] == "workday"]
    print(f"    {len(sites)} Workday sites from jobrec/job_sources_demo.json; "
          "page size 20 (Workday now rejects 50, issue #148)")
    ok = True
    for board, company in sites:
        scraper = WorkdayScraper(board, company_name=company, page_size=20, max_pages=5)
        pages = []
        original = scraper._post_json

        def counting_post(url, payload, _orig=original, _pages=pages):
            data = _orig(url, payload)
            _pages.append((payload["offset"], len(data.get("jobPostings") or []), data.get("total")))
            return data

        scraper._post_json = counting_post
        listings = scraper.fetch_jobs()
        total = pages[0][2] if pages else 0
        ids = {listing.source_job_id for listing in listings}
        expected = min(100, total or 0)
        passed = len(listings) == expected and len(ids) == len(listings)
        if (total or 0) >= 100:
            passed = passed and len(pages) == 5
        ok &= passed
        print(f"--- {company} ({board})")
        for offset, n, _ in pages:
            print(f"    page offset {offset:>3}: {n} postings")
        print(f"    site reports {total} open postings; crawled {len(pages)} pages; {len(listings)} listings built; "
              f"{len(ids)} distinct ids -> {'PASS' if passed else 'FAIL'}")
    print(f"TC-015 RESULT: {'PASS' if ok else 'FAIL'}")


def raw_records():
    """Fetch each controlled source straight from its public API, independent of the scrapers."""
    raw = {}
    gh = requests.get("https://boards-api.greenhouse.io/v1/boards/figma/jobs",
                      params={"content": "true"}, timeout=30).json()
    for j in gh["jobs"]:
        raw[("greenhouse", str(j["id"]))] = dict(
            title=j["title"], location=(j.get("location") or {}).get("name"),
            url=j["absolute_url"], description=html.unescape(j.get("content") or ""))
    lv = requests.get("https://api.lever.co/v0/postings/palantir", params={"mode": "json"}, timeout=30).json()
    for p in lv:
        raw[("lever", p["id"])] = dict(
            title=p["text"], location=(p.get("categories") or {}).get("location"),
            url=p["hostedUrl"], description=None)
    ab = requests.get("https://api.ashbyhq.com/posting-api/job-board/ramp", timeout=30).json()
    for j in ab["jobs"]:
        raw[("ashby", j["id"])] = dict(
            title=j["title"], location=j.get("location"), url=j["jobUrl"],
            description=j.get("descriptionHtml") or j.get("descriptionPlain") or "")
    return raw


def tc027(db):
    header("TC-027 scraped listings stored correctly")
    engine = create_engine(f"sqlite+pysqlite:///{db}")
    print(f"    fresh database {db}")
    print("    controlled sources: Figma (Greenhouse), Palantir (Lever), Ramp (Ashby)")
    results, failures = scrape_sources(engine, CONTROLLED)
    for name, r in results:
        print(f"    scraped {name}: {r.inserted} inserted, {r.updated} updated, {r.unchanged} unchanged")
    print(f"    failed sources: {failures or 'none'}; rows stored: {count_listings(engine)}")
    stored = list_listings(engine)
    raw = raw_records()
    sample = random.Random(27).sample(stored, 25)
    mismatches = 0
    for i, listing in enumerate(sample, 1):
        r = raw.get((listing.source, listing.source_job_id))
        if r is None:
            print(f"    {i:>2}. {listing.source}:{listing.source_job_id} no longer on the live board")
            mismatches += 1
            continue
        checks = {
            "title": _collapse_whitespace(r["title"]) == listing.title,
            "location": (_collapse_whitespace(r["location"]) if r["location"] else None) == listing.location,
            "link": normalize_url(r["url"]) == listing.application_url,
            "description": bool(listing.description) and (
                r["description"] is None or clean_text(r["description"]) == listing.description),
            "status": listing.status == "open",
        }
        bad = [k for k, v in checks.items() if not v]
        mismatches += bool(bad)
        verdict = "all 5 fields match" if not bad else "MISMATCH " + ",".join(bad)
        print(f"    {i:>2}. {listing.company_name} | {listing.title[:60]} | {listing.location} | {verdict}")
    print(f"TC-027 RESULT: {25 - mismatches}/25 sampled listings identical to the live source -> "
          f"{'PASS' if mismatches == 0 else 'FAIL'}")


def tc028(db):
    header("TC-028 duplicate and repeated listings")
    engine = create_engine(f"sqlite+pysqlite:///{db}")
    before = count_listings(engine)
    print(f"    reusing the TC-027 database {db}: {before} rows before the repeat scrape")
    results, failures = scrape_sources(engine, CONTROLLED)
    for name, r in results:
        print(f"    re-scraped {name}: {r.inserted} inserted, {r.updated} updated, {r.unchanged} unchanged")
    after = count_listings(engine)
    with engine.connect() as c:
        dups = c.execute(text(
            "SELECT source, source_job_id, COUNT(*) FROM job_listings "
            "GROUP BY source, source_job_id HAVING COUNT(*) > 1")).fetchall()
    print(f"    rows after repeat scrape: {after}; (source, job id) pairs stored more than once: {len(dups)}")
    new_rows = sum(r.inserted for _, r in results)
    step1 = len(dups) == 0 and after == before + new_rows
    one = list_listings(engine, limit=1)[0]
    changed = one.model_copy(update={"title": one.title + " (repost)"})
    res = upsert_listings(engine, [changed, changed])
    stored = [x for x in list_listings(engine)
              if x.source == one.source and x.source_job_id == one.source_job_id]
    step2 = count_listings(engine) == after and res.inserted == 0 and len(stored) == 1 \
        and stored[0].title == changed.title
    print(f"    same listing submitted twice with a changed title: {res.inserted} inserted, {res.updated} updated; "
          f"rows {count_listings(engine)}; stored title now: {stored[0].title}")
    print(f"TC-028 RESULT: {'PASS' if step1 and step2 else 'FAIL'} "
          "(no duplicate rows; a repeat sighting updates the existing row)")


if __name__ == "__main__":
    step = sys.argv[1]
    if step == "tc015":
        tc015()
    elif step == "tc027":
        tc027(sys.argv[2])
    else:
        tc028(sys.argv[2])

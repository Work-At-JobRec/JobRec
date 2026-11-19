# Reference: Team 1 (JobRec)

Technical reference for developers working on or with JobRec. It describes `main` as of commit `5700084` (2026-11-07). Paths are relative to the repository root unless noted.

**Contents**

- [System Structure](#system-structure)
- [Key APIs / Interfaces](#key-apis--interfaces)
- [Configuration](#configuration)
- [DB Schemas](#db-schemas)
- [Job Sources and Scrapers](#job-sources-and-scrapers)
- [Listing Pruning and Link Checks](#listing-pruning-and-link-checks)

---

## System Structure

### Repository layout

| Path | Contents |
| --- | --- |
| `app/` | Python backend (Poetry package `jobrec`, Python 3.11) |
| `app/jobrec/` | Backend modules (see the module index below) |
| `app/jobrec/listing_search/` | Placeholder recommendation, skill-gap and percentile functions (not implemented) |
| `app/test/` | pytest suite; `conftest.py` provides the `engine` fixture; `fixtures/` holds saved job-board responses |
| `app/deploy/` | systemd units and the nginx site configuration for the AWS host |
| `frontend/` | React single-page app built with Vite |
| `docs/` | Plans, design document, SBOM (`docs/SBOM.json`), verification inventory and test reports |
| `doc/` | Diátaxis documentation (this file) |
| `.github/workflows/` | CI and deployment workflows |

### Backend module index (`app/jobrec/`)

| Area | Module | Role |
| --- | --- | --- |
| Web API | `app.py` | Flask application and all HTTP routes |
| | `auth.py` | `require_auth` decorator (Auth0 access-token check) and `get_user_id()` |
| | `jobs.py` | Ranking and JSON shape for `/api/jobs` and `/api/jobs/<job_id>` |
| Resume and skills | `openaiapi.py` | `user_info` table, `UserInfo` profile model, resume parsing thread |
| | `skill_detection.py` | `canonical_skills` and `job_listing_skills` tables, OpenAI skill extraction |
| | `listing_skill_extractor.py` | CLI that extracts skills for listings marked `skills_pending` |
| Scraping | `scraper_base.py` | `BaseScraper` abstract class, `ScraperRequestError` |
| | `greenhouse_scraper.py`, `lever_scraper.py`, `ashby_scraper.py`, `workday_scraper.py`, `llm_scraper.py` | One scraper per job-board type |
| | `job_sources.py`, `job_sources.json`, `job_sources_demo.json` | Source registry model, the scraper-type map, and the two registries |
| | `scraper_runner.py` | `fetch_all`: runs scrapers, isolating failures |
| Pipeline and storage | `job_listing.py` | `JobListing` model shared by every scraper |
| | `job_normalization.py`, `job_validation.py` | Text and URL cleanup; required-field validation |
| | `scrape_pipeline.py` | `run_scrape_pipeline`: fetch, normalize, validate, store |
| | `job_store.py` | `job_listings` table, `upsert_listings`, de-duplication keys, queries |
| | `db.py` | Declarative `Base` and `make_engine` |
| | `scrape_all.py`, `scrape_demo.py` | Scrape CLIs (scheduled and narrated demo) |
| Pruning | `link_check.py` | `check_link`, `check_greenhouse_job`, `check_ashby_job`, `check_job_link` |
| | `job_pruning.py`, `prune_jobs.py` | Prune candidates, safeguards, and the prune CLI |
| | `check_links.py` | NF-05 link-validity CLI |

### Runtime processes (AWS host)

| Process | Defined in | Command / role |
| --- | --- | --- |
| nginx | `app/deploy/nginx/jobrec.conf` | HTTPS for `jobrec.thecoolsite.org`; serves `frontend/dist`; proxies `/api` to uWSGI on `127.0.0.1:3031`; rate limit zone of 7 requests/s per client |
| `jobrec.service` | `app/deploy/jobrec.service` | `poetry run uwsgi --socket 127.0.0.1:3031 --wsgi-file jobrec/app.py --callable app --processes 4 --threads 2` |
| `scrape-jobs.timer` / `.service` | `app/deploy/` | `python -m jobrec.scrape_all`, daily at 09:23 |
| `extract-listing-skills.timer` / `.service` | `app/deploy/` | `python -m jobrec.listing_skill_extractor --limit 50`, daily at 10:23 |

All services run as `ec2-user` from `/opt/jobrec/app`. `.github/workflows/deploy-to-aws.yml` copies the units on every push to `main` and enables `nginx.service` and `jobrec.service`.

---

## Key APIs / Interfaces

### HTTP API summary

All routes except `GET /api/version` require `Authorization: Bearer <Auth0 access token>`. Without a valid token they answer `401` with `{"error": "..."}`. The user is identified by the token's `sub` claim.

| Method | Path | Purpose | Status on `main` |
| --- | --- | --- | --- |
| GET | `/api/jobs` | Ranked job recommendations for the signed-in user | Implemented |
| GET | `/api/jobs/<job_id>` | One job, with match details | Implemented |
| GET | `/api/profile` | The user's parsed profile and processing state | Implemented |
| DELETE | `/api/profile/skills` | Remove one skill from the profile | Implemented |
| POST | `/upload` | Upload a resume (PDF or DOCX) and start parsing | Implemented; not proxied by nginx on `main` (see note) |
| POST | `/api/onboarding` | Save name, email, phone and address | Implemented |
| POST | `/api/onboarding/skip` | Create an empty profile | Implemented |
| PUT | `/api/update_profile` | Replace profile fields | Implemented |
| GET | `/api/version` | Backend package version, e.g. `"v0.6.0"` | Implemented, no auth; needs the `jobrec` package installed (`poetry install`) |
| GET | `/api/job_feed` | Paged recommendations with filters | Stub (`NotImplementedError`) |
| GET | `/api/skill_gap` | Skill gaps for one listing | Stub |
| GET | `/api/candidate_percentile` | Applicant percentile for one listing | Stub |
| POST | `/api/prune` | Prune closed listings | Stub; use the `prune_jobs` CLI |
| POST | `/api/run_scraper` | Start a scrape | Disabled (always `401`); use the `scrape_all` CLI |
| GET | `/` | None | `404` (after the token check) |

Note: nginx forwards only `/api/*` to the backend, so on the hosted site `POST /upload` does not reach Flask (Issue #176, PR #182). The frontend also calls `POST /api/jobs/<job_id>/report`, which has no backend route yet (Issue #179).

### `GET /api/jobs`

| Item | Value |
| --- | --- |
| Query parameters | `desired_salary` (optional, annual amount, must be a finite number > 0); `location` (optional, text) |
| Errors | `400 {"error": "desired_salary must be a positive annual amount"}`; `401` without a valid token |
| Response | `200`, JSON array of at most 5 job objects, best match first |
| Ranking | `score = 0.7 × compatibility + 0.3 × salary_score`; ties broken by listing id |
| `compatibility` | Σ(required/4 × held/4) ÷ Σ(required/4) over the listing's skills (0 when the listing has none) |
| `salary_score` | 0.25 when the listing's pay cannot be read; 1.0 when no `desired_salary` is given; otherwise offered ÷ desired, capped at 2.0 |
| `location` filter | Text before the first comma, matched case-insensitively as a substring of the listing's location |
| Listings considered | `status = "open"` only |

**Job object**

| Field | Type | Meaning |
| --- | --- | --- |
| `id` | string | `<source>-<source_job_id>` (or `<source>-<row id>` when the source has no job id) |
| `title`, `company`, `location` | string / null | As stored |
| `description` | string | Full cleaned description |
| `applicationUrl` | string | Link to the posting |
| `postedAgo` | string / null | `"Today"`, `"1 Day Ago"`, `"N Days Ago"` |
| `jobType` | string | `"Internship"`, `"Part Time"`, `"Contract"` or `"Full Time"`, inferred from the title |
| `salary` | string / null | Pay text as published by the source |
| `compatibility` | integer | 0 to 100 |
| `requirements` | array | `{ "text": "Requires proficiency level N/4", "skill": <name>, "met": <bool> }` per listing skill |

### `GET /api/jobs/<job_id>`

| Item | Value |
| --- | --- |
| Path parameter | `job_id`: the `id` from `/api/jobs` |
| Query parameters | `desired_salary` (optional, as above) |
| Responses | `200` job object (same fields as above); `404 {"error": "Job not found"}`; `400` bad `desired_salary`; `401` |

### `GET /api/profile`

| `status` | `user_info` | When |
| --- | --- | --- |
| `"empty"` | `null` | No profile row for this user |
| `"processing"` | `null` | A resume was uploaded and parsing has not finished |
| `"done"` | profile object or `null` | Parsing finished (`null` if the stored profile fails validation) |

Profile object (`UserInfo`): `name`, `email`, `phone`, `location` (string or null); `skills` (`[{skill_name, proficiency_level 1–4}]`); `education` (`[{school, degree}]`); `projects` (`[string]`); `socials` (`[{platform, url}]`); `employment_history` (`[{company_name, role}]`).

### `POST /upload`

| Item | Value |
| --- | --- |
| Body | `multipart/form-data`, file field `resume` |
| Accepted files | `.pdf` (at least one readable page) or `.docx` (opens as a Word document) |
| Stored as | `<RESUME_FOLDER>/<first 16 hex of sha256(user id)>-<random uuid>.<ext>`; deleted once parsing finishes |
| Responses | `200` parsing started in a background thread (poll `GET /api/profile`); `400` wrong type or unreadable file; `302` back to the request URL when no file is sent |

### `DELETE /api/profile/skills`

| Item | Value |
| --- | --- |
| Body | JSON `{"skill_name": "<name>"}`, matched case-insensitively after trimming |
| Responses | `200 {"status": "done", "user_info": {...}}`; `400` no `skill_name`; `404` no finished profile |

### Python interfaces

| Interface | Module | Signature / contract |
| --- | --- | --- |
| `BaseScraper` | `scraper_base` | Abstract. Subclasses set `source_name` and implement `fetch_jobs() -> list[JobListing]`. `fetch_open_jobs()` filters to `status == "open"`. `_get_json` / `_post_json` raise `ScraperRequestError` on connection failure, timeout (10 s), non-2xx status or non-JSON body. |
| `JobListing` | `job_listing` | Pydantic model; fields in the table below |
| `run_scrape_pipeline(engine, scrapers)` | `scrape_pipeline` | `fetch_all` → `normalize_listings` → `filter_valid_listings` → `upsert_listings`; returns `UpsertResult` |
| `upsert_listings(engine, listings, *, now=None)` | `job_store` | Inserts new listings and updates known ones (same `dedupe_key`); duplicates in one batch collapse to the last; retries once on a concurrent insert. Returns `UpsertResult(inserted, updated, unchanged)`. |
| `check_job_link(url, session, timeout=10, job_id=None, board_token=None, max_bytes=200000, ashby_boards=None)` | `link_check` | Returns `LinkResult(status: OPEN/CLOSED/UNKNOWN, reason, http_status, final_url, text, raw)`; rules in [Listing Pruning and Link Checks](#listing-pruning-and-link-checks) |
| `scrape_all(engine, sources)` | `job_sources` | Runs `run_scrape_pipeline` once per enabled `JobSource`; returns `[(source name, UpsertResult)]` |

**`JobListing` fields**

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `title` | str | yes | As posted |
| `company_name` | str | yes | |
| `location` | str / None | no | Free text |
| `description` | str | no (default `""`) | May hold HTML until normalized |
| `source` | str | yes | Scraper name, e.g. `"greenhouse"` |
| `application_url` | str | yes | |
| `posted_at` | datetime / None | no | Timezone-aware |
| `scraped_at` | datetime | no (default now, UTC) | |
| `source_job_id` | str / None | no | The source's own job id |
| `pay` | str / None | no | e.g. `"USD 100,000-120,000 (Base)"` |
| `status` | str | no (default `"open"`) | `"open"` or `"closed"` |

---

## Configuration

### Environment variables

Read from the process environment and from `app/.env` (via `python-dotenv`).

| Variable | Used by | Required | Default | Example / notes |
| --- | --- | --- | --- | --- |
| `DATABASE_URL` | `app.py`, `scrape_all`, `prune_jobs`, `check_links`, `listing_skill_extractor` | no | `sqlite+pysqlite:///user_skills.db` | `postgresql://user:pass@host/jobrec` (`postgres://` and `postgresql://` are rewritten to the psycopg 3 driver by `make_engine`) |
| `OPENAI_API_KEY` | OpenAI client (resume parsing, skill extraction, LLM scraper) | yes for parsing and extraction | none | Read by the `openai` library; importing `openaiapi` needs it set |
| `AUTH0_DOMAIN` | `auth.py` | yes | none | Auth0 tenant domain |
| `AUTH0_AUDIENCE` | `auth.py` | yes | none | Auth0 API identifier |
| `RESUME_FOLDER` | `app.py` | no | `uploads` | Directory for uploaded resumes |
| `APP_BASE_URL` | `app.py` (only when run as `python -m jobrec.app`) | for local runs | none | `http://localhost:5001`; port defaults to 5001 |
| `DEV` | `app.py` | no | unset | When set, every `user_info` row is deleted at startup |
| `JOBREC_LLM_MODEL` | `llm_scraper.py` | no | `gpt-5.2` | Model for the LLM fallback scraper |
| `TEST_DATABASE_URL` | `app/test/conftest.py` | no | unset (tests use SQLite) | Postgres URL whose database name contains `test` |
| `DEPLOYMENT` | systemd units | no | `True` on the host | Set by every unit; not read by backend code on `main` |
| `VITE_AUTH0_DOMAIN`, `VITE_AUTH0_CLIENT_ID`, `VITE_AUTH0_AUDIENCE` | `frontend/src/main.jsx` | yes (frontend build) | none | Auth0 SPA settings, baked in at `vite build` |

### Source registry (`app/jobrec/job_sources.json`)

```json
{
  "sources": [
    {"scraper": "greenhouse", "id": "stripe", "company_name": "Stripe", "enabled": true}
  ]
}
```

| Key | Type | Required | Meaning |
| --- | --- | --- | --- |
| `scraper` | string | yes | One of `ashby`, `greenhouse`, `lever`, `llm`, `workday` (anything else fails validation) |
| `id` | string | yes | The board identifier for that scraper (formats in [Job Sources and Scrapers](#job-sources-and-scrapers)) |
| `company_name` | string | no | Display name; the scraper's own value is used when empty |
| `enabled` | bool | no (default `true`) | `false` keeps the entry but skips it |

`job_sources.json` (5 sources) is the default for `scrape_all`. `job_sources_demo.json` (22 sources) is used for demos, validation runs and pruning's Greenhouse board lookup.

### Scheduled jobs

| Unit | Command | Schedule |
| --- | --- | --- |
| `scrape-jobs` | `python -m jobrec.scrape_all` | `*-*-* 09:23:00` (daily) |
| `extract-listing-skills` | `python -m jobrec.listing_skill_extractor --limit 50` | `*-*-* 10:23:00` (daily) |

Both timers set `Persistent=true`. The deploy workflow copies the timers but does not run `systemctl enable` for them.

---

## DB Schemas

Tables are created by SQLAlchemy (`Base.metadata.create_all` and `ensure_job_listing_schema`). The same schema runs on SQLite (development, tests) and PostgreSQL (production, CI job "Job store on Postgres").

### `job_listings`

| Column | Type | Null | Key / default | Meaning |
| --- | --- | --- | --- | --- |
| `id` | Integer | no | PK, autoincrement | Row id |
| `dedupe_key` | String(1024) | no | UNIQUE | Identity across scrapes (see below) |
| `source` | String(64) | no | indexed | Scraper name |
| `source_job_id` | String(255) | yes | | Source's job id |
| `title` | String(512) | no | | |
| `company_name` | String(255) | no | | |
| `location` | String(255) | yes | | |
| `description` | Text | no | `""` | Cleaned text |
| `application_url` | String(2048) | no | | |
| `pay` | String(255) | yes | | |
| `status` | String(32) | no | `"open"` | `open` / `closed` |
| `skills_pending` | Boolean | no | `true` | Waiting for skill extraction |
| `posted_at` | DateTime (tz) | yes | | |
| `scraped_at` | DateTime (tz) | no | | Last scrape time |
| `first_seen_at` | DateTime (tz) | no | | First stored |
| `last_seen_at` | DateTime (tz) | no | | Last reported by a scraper |
| `updated_at` | DateTime (tz) | no | | Last change to any detail |

**`dedupe_key` format**: `<source>:id:<source_job_id>` when the source gives an id; else `<source>:url:<normalized application URL>`; else `<source>:fields:<company>|<title>|<location>`. Values longer than the column are clipped, and NUL bytes are removed before storing.

**Fields refreshed on a repeat sighting**: `title`, `company_name`, `location`, `description`, `application_url`, `posted_at`, `source_job_id`, `pay`, `status`. A changed description sets `skills_pending` back to `true`.

### `canonical_skills`

| Column | Type | Null | Key | Meaning |
| --- | --- | --- | --- | --- |
| `id` | Integer | no | PK, autoincrement | |
| `normalized_name` | String(255) | no | UNIQUE | Lower-cased lookup name |
| `skill_name` | String(255) | no | | Display name |

### `job_listing_skills`

| Column | Type | Null | Key | Meaning |
| --- | --- | --- | --- | --- |
| `listing_id` | Integer | no | PK, FK → `job_listings.id` ON DELETE CASCADE | |
| `skill_id` | Integer | no | PK, FK → `canonical_skills.id` ON DELETE CASCADE | |
| `proficiency_level` | Integer | no | | Required level, 1 (basic) to 4 (expert) |

### `user_info`

| Column | Type | Null | Key | Meaning |
| --- | --- | --- | --- | --- |
| `user_id` | String | no | PK | Auth0 `sub` claim |
| `skills` | JSON | yes | | The whole `UserInfo` profile (mapped as the `info` attribute) |
| `done_processing` | Boolean | yes | | `false` while a resume is being parsed |

### Relationships

| From | To | Cardinality |
| --- | --- | --- |
| `job_listing_skills.listing_id` | `job_listings.id` | many skills per listing |
| `job_listing_skills.skill_id` | `canonical_skills.id` | many listings per skill |
| `user_info.skills[].skill_name` | `canonical_skills.skill_name` | by name, not a foreign key |

---

## Job Sources and Scrapers

### Scraper types

| `scraper` | `id` format (example) | Endpoint | Paging | Closed when |
| --- | --- | --- | --- | --- |
| `greenhouse` | board token (`stripe`) | `GET https://boards-api.greenhouse.io/v1/boards/{id}/jobs?content=true` | none (one response) | `application_deadline` is in the past |
| `lever` | company slug (`palantir`) | `GET https://api.lever.co/v0/postings/{id}?mode=json` | none | never at scrape time (listed postings are open) |
| `ashby` | organization slug (`ramp`) | `GET https://api.ashbyhq.com/posting-api/job-board/{id}?includeCompensation=true` | none | `isListed` is `false` |
| `workday` | `host/site` (`nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite`) | `POST https://{host}/wday/cxs/{tenant}/{site}/jobs`, `{"limit": 20, "offset": N}` | 20 per page, at most 5 pages (100 postings) | `canApply` is `false` |
| `llm` | careers page URL | Page HTML read by an OpenAI model (`JOBREC_LLM_MODEL`) | at most 200 postings, 40,000 page characters | the page says the job is closed |

`tenant` is the first label of the Workday host (`nvidia`). Every scraper also stores the source's job id as `source_job_id`.

### Pipeline stages

| Stage | Function | Drops or changes |
| --- | --- | --- |
| Fetch | `scraper_runner.fetch_all` | Calls each scraper's `fetch_open_jobs`, so closed postings are dropped here; a failing source is logged and skipped |
| Normalize | `job_normalization.normalize_listings` | HTML to text, whitespace, URLs |
| Validate | `job_validation.filter_valid_listings` | Listings with an empty `title`, `company_name` or `source`, or without a usable `application_url`, are dropped and logged |
| Store | `job_store.upsert_listings` | Insert, update or leave unchanged by `dedupe_key` |

### CLI: `python -m jobrec.scrape_all` (run from `app/`)

| Option | Default | Meaning |
| --- | --- | --- |
| `--sources PATH` | `jobrec/job_sources.json` | Registry to read |

Output: one line per source (`new=`, `updated=`, `unchanged=`), then a total. Exit code `0` when every source ran and the database holds listings, otherwise `1`. It makes no OpenAI calls; new and changed listings are marked `skills_pending`.

### CLI: `python -m jobrec.scrape_demo`

| Option | Default | Meaning |
| --- | --- | --- |
| `--sources PATH` | `jobrec/job_sources_demo.json` | Registry to read |
| `--database DB` | `demo_scrape.db` | SQLite file or SQLAlchemy URL |
| `--fresh` | off | Delete the SQLite file first |
| `--pause S` | `0.8` | Seconds between narrated stages |
| `--sample N` | `2` | Example rows printed per source |
| `--limit N` | none | Store at most N listings per source |
| `--only NAMES` | all | Comma-separated source names or prefixes, e.g. `greenhouse:figma,lever` |

### CLI: `python -m jobrec.listing_skill_extractor`

| Option | Default | Meaning |
| --- | --- | --- |
| `--limit N` | `50` | Pending listings analyzed per run |
| `--candidate-cap N` | `100` | BM25-ranked catalog skills offered to the model per listing |

Exit code `1` when any listing failed, otherwise `0`.

---

## Listing Pruning and Link Checks

### Status rules (`link_check.check_job_link`)

The first rule that applies decides. CLOSED requires positive evidence; anything inconclusive is UNKNOWN, and UNKNOWN listings are never deleted.

| Order | Applies to | OPEN | CLOSED | UNKNOWN |
| --- | --- | --- | --- | --- |
| 1 | Greenhouse listings whose board token is known | Board API `GET .../boards/{token}/jobs/{id}` returns the job | API returns `404` | Other status, non-JSON, different job id, timeout → fall through to the page |
| 2 | Links on `jobs.ashbyhq.com/{org}/{id}` | Posting API lists the id | Board lists postings but not this id, or lists it with `isListed: false` | Board unreadable or empty → fall through to the page |
| 3 | Every link (page check) | `200` and none of the markers below | `404` or `410`; Greenhouse redirect with `error=true`; a marker in the visible text | Any other status, request failure, or a redirect that drops the job id |

Closed-page markers (case-insensitive, visible text only): "no longer accepting applications", "job is no longer available", "position is no longer available", "posting is no longer available", "position has been filled", "job has been filled", "job has expired", "posting has expired", "job not found", "job posting not found".

The Ashby board is fetched once per organization per run. Greenhouse board tokens come from both registries, keyed by lower-cased company name.

### Request limits and safeguards

| Constant | Value | Module | Effect |
| --- | --- | --- | --- |
| `DEFAULT_TIMEOUT` | 10 s | `link_check` | Per request |
| `DEFAULT_MAX_BYTES` | 200,000 | `link_check` | Only the start of a page is read |
| `DEFAULT_STALE_AFTER` | 7 days | `job_pruning` | A listing is a candidate if it was missing from its company's latest scrape or not seen for 7 days |
| `DEFAULT_PAUSE` | 0.5 s | `job_pruning`, `check_links` | Pause between requests to the same host |
| `MAX_CONSECUTIVE_FAILURES` | 3 | `job_pruning` | After 3 UNKNOWN results in a row, the rest of that host is skipped |
| `MASS_CLOSURE_MIN_CHECKED` | 20 | `job_pruning` | If at least 20 listings on one host are checked and more than half look closed, none of that host's listings are deleted |

Deleting a listing also deletes its `job_listing_skills` rows.

### CLI: `python -m jobrec.prune_jobs` (run from `app/`)

| Option | Default | Meaning |
| --- | --- | --- |
| `--delete` | off (dry run) | Actually remove CLOSED listings |
| `--limit N` | all candidates | Follow at most N links (candidates are shuffled first) |

Output: `Checked N links: removed X closed listings, Y still open, Z undetermined (kept).` (dry run: how many would be removed). Exit code `0`.

### CLI: `python -m jobrec.check_links` (validation test NF-05)

| Option | Default | Meaning |
| --- | --- | --- |
| `--sample N` | `100` | Stored links sampled at random |

Output: links that resolve (HTTP 200 and not CLOSED) and links whose page or API record mentions the stored title or company, each as a count and a percentage, followed by each problem link and its reason. The NF-05 pass threshold is 95% for both. Exit code `0`.

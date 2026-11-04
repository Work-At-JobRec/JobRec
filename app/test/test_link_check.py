import json
import os
import sys

import pytest
import requests

# Lets this test import app/src/link_check.py
SRC_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "src")
)
sys.path.insert(0, SRC_DIR)

from jobrec.link_check import (  # noqa: E402
    ASHBY_JOB_BOARD_URL, GREENHOUSE_JOB_URL, LinkStatus, check_ashby_job, check_greenhouse_job, check_job_link, check_link,
)
from link_fakes import FakeSession, page  # noqa: E402

URL = "https://acme.com/jobs/123"


def check(outcome, url=URL, **kwargs):
    return check_link(url, FakeSession({url: outcome}), **kwargs)


# A normal job page means the listing is open
def test_ordinary_page_is_open():
    result = check(page(200, "<h1>Software Engineer</h1><p>Apply for this job</p>"))

    assert result.status == LinkStatus.OPEN
    assert result.http_status == 200
    assert "Software Engineer" in result.text


# A page that is gone means the listing is closed
@pytest.mark.parametrize("status", [404, 410])
def test_gone_page_is_closed(status):
    assert check(page(status, "Not found")).status == LinkStatus.CLOSED


# Responses that do not say whether the job exists are unknown, never closed
@pytest.mark.parametrize("status", [401, 403, 408, 429, 500, 502, 503])
def test_blocked_or_failing_response_is_unknown(status):
    assert check(page(status, "error")).status == LinkStatus.UNKNOWN


# A request that fails outright is unknown, with the reason recorded
@pytest.mark.parametrize("error", [requests.ConnectionError("refused"), requests.Timeout("timed out")])
def test_request_failure_is_unknown(error):
    result = check(error)

    assert result.status == LinkStatus.UNKNOWN
    assert result.http_status is None
    assert result.reason


# Greenhouse sends a closed job to its board with error=true in the address
def test_greenhouse_error_redirect_is_closed():
    outcome = page(200, "<h1>Current openings</h1>", url="https://job-boards.greenhouse.io/acme?error=true", redirected=True)

    assert check(outcome).status == LinkStatus.CLOSED


# A page whose visible text says the job is closed means closed
@pytest.mark.parametrize("message", [
    "This job is no longer available",
    "We are no longer accepting applications for this role",
    "This position has been filled",
    "Job not found",
])
def test_closed_message_in_visible_text_is_closed(message):
    assert check(page(200, f"<h1>Acme careers</h1><p>{message}.</p>")).status == LinkStatus.CLOSED


# The same words inside a script are not what the visitor sees, so they prove nothing
def test_closed_message_inside_a_script_is_open():
    body = '<h1>Software Engineer</h1><script>const messages = {gone: "This job is no longer available"};</script>'

    assert check(page(200, body)).status == LinkStatus.OPEN


# A redirect to a general careers page (the job id is gone from the address) is unknown, not closed
def test_redirect_that_loses_the_job_id_is_unknown():
    outcome = page(200, "<h1>Careers at Acme</h1>", url="https://acme.com/careers", redirected=True)

    assert check(outcome, job_id="123").status == LinkStatus.UNKNOWN


# A redirect that still names the job (for example to a new host) is judged by its page as usual
def test_redirect_that_keeps_the_job_id_is_open():
    outcome = page(200, "<h1>Software Engineer</h1>", url="https://jobs.acme.com/openings/123", redirected=True)

    assert check(outcome, job_id="123").status == LinkStatus.OPEN


# Only the start of a very large page is read
def test_large_page_is_read_only_up_to_the_cap():
    body = "<p>" + "x" * 1_000_000 + "</p><p>This job is no longer available</p>"

    result = check(page(200, body), max_bytes=10_000)

    assert result.status == LinkStatus.OPEN
    assert len(result.text) <= 10_000


# A browser-like User-Agent and a timeout are always sent, and redirects are followed
def test_request_sends_user_agent_timeout_and_follows_redirects():
    seen = {}

    class RecordingSession(FakeSession):
        def get(self, url, **kwargs):
            seen.update(kwargs)
            return super().get(url, **kwargs)

    check_link(URL, RecordingSession({URL: page()}), timeout=7)

    assert "Mozilla" in seen["headers"]["User-Agent"]
    assert seen["timeout"] == 7
    assert seen["allow_redirects"] is True
    assert seen["stream"] is True


# An empty address cannot be checked
def test_empty_url_is_unknown():
    assert check_link("", FakeSession({})).status == LinkStatus.UNKNOWN


# --- Greenhouse per-job API (#103): status without touching the careers page ---

API_URL = GREENHOUSE_JOB_URL.format(board_token="acme", job_id="123")


def api(outcome):
    return check_greenhouse_job("acme", "123", FakeSession({API_URL: outcome}))


# A 200 answer naming the job means it still exists on the board
def test_api_answer_with_the_job_is_open():
    result = api(page(200, '{"id": 123, "title": "Software Engineer", "content": "&lt;p&gt;Apply now&lt;/p&gt;"}'))

    assert result.status == LinkStatus.OPEN
    assert result.http_status == 200
    assert "Software Engineer" in result.text
    assert "Software Engineer" in result.raw


# Greenhouse answers 404 for a job that was closed or removed
def test_api_not_found_is_closed():
    result = api(page(404, '{"status": 404, "error": "Job not found"}'))

    assert result.status == LinkStatus.CLOSED
    assert result.http_status == 404


# Anything inconclusive stays unknown so pruning never deletes on it
@pytest.mark.parametrize("outcome", [
    page(500, "error"),
    page(429, "slow down"),
    page(200, "<html>not json</html>"),
    page(200, '{"id": 999, "title": "Some other job"}'),
    requests.Timeout("timed out"),
    requests.ConnectionError("refused"),
])
def test_api_failures_and_mismatches_are_unknown(outcome):
    assert api(outcome).status == LinkStatus.UNKNOWN


# check_job_link asks the API first when it knows the board, and only reads the page when the API cannot say
def test_job_link_uses_the_api_before_the_page():
    session = FakeSession({API_URL: page(200, '{"id": 123, "title": "Software Engineer"}'), URL: requests.Timeout("timed out")})

    result = check_job_link(URL, session, job_id="123", board_token="acme")

    assert result.status == LinkStatus.OPEN
    assert session.calls == [API_URL]


def test_job_link_falls_back_to_the_page_when_the_api_is_inconclusive():
    session = FakeSession({API_URL: requests.Timeout("timed out"), URL: page(200, "<h1>Software Engineer</h1>")})

    result = check_job_link(URL, session, job_id="123", board_token="acme")

    assert result.status == LinkStatus.OPEN
    assert session.calls == [API_URL, URL]


def test_job_link_without_a_board_reads_only_the_page():
    session = FakeSession({URL: page(404, "Not found")})

    assert check_job_link(URL, session, job_id="123").status == LinkStatus.CLOSED
    assert session.calls == [URL]


# --- Ashby posting API (#150): posting pages are rendered in the browser and never carry the title ---

ASHBY_ID = "4c1e8f9a-0b2d-4e6f-8a1b-2c3d4e5f6a7b"
ASHBY_PAGE = f"https://jobs.ashbyhq.com/acme/{ASHBY_ID}"
ASHBY_API = ASHBY_JOB_BOARD_URL.format(organization="acme")
ASHBY_SHELL = "<html><head><title>Jobs</title></head><body><div id='root'></div><script src='app.js'></script></body></html>"


def ashby_board(*jobs):
    return page(200, json.dumps({"jobs": list(jobs)}))


def ashby_job(job_id=ASHBY_ID, title="Software Engineer", **fields):
    return {"id": job_id, "title": title, "descriptionPlain": "Build the product.", "isListed": True, **fields}


# A posting the board still lists is open, and its title stands in for the page text
def test_ashby_posting_on_the_board_is_open():
    result = check_ashby_job("acme", ASHBY_ID, FakeSession({ASHBY_API: ashby_board(ashby_job())}))

    assert result.status == LinkStatus.OPEN
    assert result.http_status == 200
    assert "Software Engineer" in result.text
    assert "Software Engineer" in result.raw


# A posting the board no longer lists, or lists as unlisted, is closed
@pytest.mark.parametrize("jobs", [
    [ashby_job(job_id="11111111-2222-3333-4444-555555555555", title="Other Job")],
    [ashby_job(isListed=False)],
])
def test_ashby_posting_missing_or_unlisted_is_closed(jobs):
    assert check_ashby_job("acme", ASHBY_ID, FakeSession({ASHBY_API: ashby_board(*jobs)})).status == LinkStatus.CLOSED


# Anything inconclusive stays unknown, including an empty board, so pruning never deletes on it
@pytest.mark.parametrize("outcome", [
    page(404, "Not found"),
    page(500, "error"),
    page(200, "<html>not json</html>"),
    page(200, '{"jobs": []}'),
    page(200, '{"error": "unknown board"}'),
    requests.Timeout("timed out"),
])
def test_ashby_api_failures_are_unknown(outcome):
    assert check_ashby_job("acme", ASHBY_ID, FakeSession({ASHBY_API: outcome})).status == LinkStatus.UNKNOWN


# One board request answers every posting of that organization in a run
def test_ashby_board_is_fetched_once_per_organization():
    other_id = "11111111-2222-3333-4444-555555555555"
    session = FakeSession({ASHBY_API: ashby_board(ashby_job(), ashby_job(job_id=other_id, title="Designer"))})
    boards = {}

    first = check_ashby_job("acme", ASHBY_ID, session, boards=boards)
    second = check_ashby_job("acme", other_id, session, boards=boards)

    assert (first.status, second.status) == (LinkStatus.OPEN, LinkStatus.OPEN)
    assert "Designer" in second.text
    assert session.calls == [ASHBY_API]


# check_job_link recognises an Ashby posting link and asks the API instead of reading the shell page
def test_job_link_checks_ashby_postings_through_the_api():
    session = FakeSession({ASHBY_API: ashby_board(ashby_job()), ASHBY_PAGE: page(200, ASHBY_SHELL)})

    result = check_job_link(ASHBY_PAGE, session, job_id=ASHBY_ID)

    assert result.status == LinkStatus.OPEN
    assert "Software Engineer" in result.raw
    assert session.calls == [ASHBY_API]


def test_ashby_job_link_falls_back_to_the_page_when_the_api_is_inconclusive():
    session = FakeSession({ASHBY_API: requests.Timeout("timed out"), ASHBY_PAGE: page(404, "Not found")})

    result = check_job_link(ASHBY_PAGE, session, job_id=ASHBY_ID)

    assert result.status == LinkStatus.CLOSED
    assert session.calls == [ASHBY_API, ASHBY_PAGE]


# The posting id is read from the link when the listing has none stored
def test_ashby_job_id_is_taken_from_the_link():
    session = FakeSession({ASHBY_API: ashby_board(ashby_job())})

    assert check_job_link(ASHBY_PAGE + "/application", session).status == LinkStatus.OPEN
    assert session.calls == [ASHBY_API]

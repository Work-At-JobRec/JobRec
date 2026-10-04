import os
import sys

import pytest
import requests

# Lets this test import app/src/link_check.py
SRC_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "src")
)
sys.path.insert(0, SRC_DIR)

from link_check import LinkStatus, check_link  # noqa: E402
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

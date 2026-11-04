"""TC-023 / NF-10: resume upload latency.

Thirty uploads of the sample PDF and DOCX resumes go through the /upload route on the
Flask test client, and the time to the upload response is recorded for each. The
requirement (SDP REQ-010, V&V SYS-004) is that the initial upload completes in under
2 seconds in at least 27 of 30 trials. Auth is patched the same way test_upload.py does
it, and the background parse thread is patched out, so the measurement is what the user
waits for: the HTTP upload plus the server saving and checking the file.
"""

import os
import statistics
import time
from unittest.mock import patch

import pytest

from jobrec.app import app

RESUMES = [
    "Jane_Smith_-_Public_Resume_Spring_2026-1.pdf",
    "Jane_Smith_-_Public_Resume_Spring_2026-1.docx",
]
TRIALS = 30
LIMIT_SECONDS = 2.0
REQUIRED_PASSES = 27
mock_user = "test|latency"
fake_headers = {"Authorization": "Bearer 39"}


async def mock_verify_access_token(token):
    return {"sub": mock_user}


def resume_path(name: str) -> str:
    return os.path.join(os.path.dirname(__file__), "test_resumes", name)


def time_upload(client, name: str) -> float:
    with open(resume_path(name), "rb") as resume_file:
        started = time.perf_counter()
        response = client.post(
            "/upload",
            data={"resume": (resume_file, name)},
            content_type="multipart/form-data",
            headers=fake_headers,
        )
        elapsed = time.perf_counter() - started
    assert response.status_code == 200, (name, response.status_code)
    return elapsed


# TC-023: 30 uploads, alternating PDF and DOCX; at least 27 complete in under 2 seconds
def test_tc023_thirty_uploads_complete_under_two_seconds(tmp_path, record_property):
    app.config["TESTING"] = True
    app.config["UPLOAD_FOLDER"] = str(tmp_path)
    client = app.test_client()

    with patch("jobrec.app.get_user_id", return_value=mock_user), patch(
        "jobrec.auth.api_client.verify_access_token", new=mock_verify_access_token
    ), patch("jobrec.app.Thread"):
        times = [time_upload(client, RESUMES[i % len(RESUMES)]) for i in range(TRIALS)]

    ordered = sorted(times)
    p90 = ordered[int(round(0.9 * (len(ordered) - 1)))]
    under_limit = sum(t < LIMIT_SECONDS for t in times)
    record_property("upload_median_ms", round(statistics.median(times) * 1000))
    record_property("upload_p90_ms", round(p90 * 1000))
    record_property("upload_max_ms", round(max(times) * 1000))
    record_property("upload_under_2s", f"{under_limit}/{TRIALS}")
    print(
        f"TC-023: {TRIALS} uploads, median {statistics.median(times) * 1000:.0f} ms, "
        f"p90 {p90 * 1000:.0f} ms, max {max(times) * 1000:.0f} ms, under 2 s: {under_limit}/{TRIALS}"
    )

    assert len(times) == TRIALS
    assert under_limit >= REQUIRED_PASSES, f"only {under_limit} of {TRIALS} uploads finished under {LIMIT_SECONDS} s"

"""
Activity log kept in a GitHub gist.

Lives in its own module (rather than main.py) so job_manager can log job outcomes
without a circular import. Every entry is also printed, so the server console holds
a copy if the gist is unreachable.
"""

import json
import threading
import time

import requests

from server_env import get_secret

GIST_URL = "https://api.github.com/gists/cdc9929b3a24b3fc4150579b2b2bb2b3"
LOG_FNAME = "ai-tool-log"
SEPARATOR = "\n ----------------------------------------------------------------------------"

# The gist API has no append: each write is read-modify-write of the whole file. Jobs
# finish on background threads, so two finishing together would otherwise each read
# the old content and the second write would silently drop the first entry.
_log_lock = threading.Lock()


def _headers():
    return {
        "Authorization": f"token {get_secret('github_token')}",
        "Accept": "application/vnd.github.v3+json",
    }


def fetch_gist_content(headers):
    """Returns the current log text, or None if the gist could not be read."""
    response = requests.get(GIST_URL, headers=headers, timeout=30)
    if response.status_code == 200:
        return response.json()["files"][LOG_FNAME]["content"]
    print(f"Failed to fetch gist content: HTTP {response.status_code} {response.text[:200]}")
    return None


def mask_email(email):
    if not email:
        return "unknown_email"
    return email[:5] + "*" * len(email[5:])


def timestamp():
    return f"{time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())} GMT"


def log(new_content):
    """
    Appends an entry to the gist log.

    Never raises: logging must not be the thing that breaks a user's job. Failures
    (e.g. an expired or under-scoped github_token) are printed instead of swallowed.
    """
    print(f"[gist log] {new_content}")
    try:
        headers = _headers()
        with _log_lock:
            current_content = fetch_gist_content(headers)
            if current_content is None:
                return
            updated_content = f"{current_content} \n {new_content}{SEPARATOR}"
            data = {"files": {LOG_FNAME: {"content": updated_content}}}
            response = requests.patch(GIST_URL, headers=headers, data=json.dumps(data), timeout=30)
            if not response.ok:
                print(f"Failed to write gist log: HTTP {response.status_code} {response.text[:200]}")
    except Exception as e:
        print(f"Failed to write gist log: {type(e).__name__}: {e}")


def log_job_outcome(job_data):
    """Logs how a job ended, from its stored job record (see job_manager)."""
    status = job_data.get("status")
    job_id = job_data.get("job_id", "unknown_job")
    header = f"{mask_email(job_data.get('user_email'))}: {timestamp()} \n JOB {status.upper() if status else 'ENDED'} ({job_id})"
    if status == "failed":
        body = f"\n ERROR: {job_data.get('error')}"
    else:
        result = job_data.get("result") or {}
        failed = result.get("failed_pdfs") or []
        reasons = result.get("failure_reasons") or {}
        body = (
            f"\n PDFs: {result.get('num_pdfs', '?')}, failed: {len(failed)}, "
            f"pages: {result.get('total_num_pages', '?')}, "
            f"output: {result.get('output_file_size_mb', '?')} MB"
        )
        for name, why in reasons.items():
            body += f"\n   FAILED {name} -> {why}"
    log(header + body)

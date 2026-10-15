import secrets
import time

from flask import request, session
from werkzeug.exceptions import BadRequest

_failures = {}
_report_hits = {}
ATTEMPT_LIMIT = 5
ATTEMPT_WINDOW = 600
REPORT_LIMIT = 3
REPORT_WINDOW = 600


def ensure_csrf():
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


def verify_csrf():
    if request.method != "POST":
        return
    sent = request.form.get("csrf_token", "")
    expected = session.get("csrf_token", "")
    if not expected or not sent or not secrets.compare_digest(sent, expected):
        raise BadRequest()


def _key(post_id):
    return f"{request.remote_addr}:{post_id}"


def rate_limited(post_id):
    now = time.monotonic()
    recent = [stamp for stamp in _failures.get(_key(post_id), []) if now - stamp < ATTEMPT_WINDOW]
    _failures[_key(post_id)] = recent
    return len(recent) >= ATTEMPT_LIMIT


def record_failure(post_id):
    key = _key(post_id)
    now = time.monotonic()
    recent = [stamp for stamp in _failures.get(key, []) if now - stamp < ATTEMPT_WINDOW]
    recent.append(now)
    _failures[key] = recent


def clear_failures(post_id):
    _failures.pop(_key(post_id), None)


def reset_rate_limit():
    _failures.clear()
    _report_hits.clear()


def report_rate_limited(post_id):
    now = time.monotonic()
    key = _key(post_id)
    recent = [stamp for stamp in _report_hits.get(key, []) if now - stamp < REPORT_WINDOW]
    _report_hits[key] = recent
    return len(recent) >= REPORT_LIMIT


def record_report(post_id):
    key = _key(post_id)
    now = time.monotonic()
    recent = [stamp for stamp in _report_hits.get(key, []) if now - stamp < REPORT_WINDOW]
    recent.append(now)
    _report_hits[key] = recent


def can_manage(post_id):
    return post_id in session.get("managed_ids", [])


def allow_manage(post_id):
    ids = [item for item in session.get("managed_ids", []) if item != post_id]
    ids.append(post_id)
    session["managed_ids"] = ids[-30:]
    session.modified = True


def forget_manage(post_id):
    session["managed_ids"] = [item for item in session.get("managed_ids", []) if item != post_id]
    session.modified = True

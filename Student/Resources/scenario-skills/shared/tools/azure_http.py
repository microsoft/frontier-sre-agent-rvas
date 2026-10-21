"""Bounded HTTPS retries for the skill collectors, using the bundled host policy."""

import json
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlsplit

POLICY_PATH = Path(__file__).resolve().parents[1] / "references" / "governance.json"
RETRY_CODES = {429, 500, 502, 503, 504}


def _retry_delay(headers: dict, attempt: int, maximum: float) -> float:
    value = headers.get("Retry-After")
    if value is None:
        delay = float(2 ** attempt)
    else:
        try:
            delay = float(value)
        except ValueError:
            target = parsedate_to_datetime(value)
            if target.tzinfo is None:
                raise ValueError("Retry-After date requires a timezone.")
            delay = max(0.0, (target - datetime.now(timezone.utc)).total_seconds())
    if delay < 0 or delay > maximum:
        raise RuntimeError("Server retry delay is outside the approved retry budget; collection is incomplete.")
    return delay


def _send(method: str, url: str, **kwargs):
    import requests

    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))["http"]
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower()
    allowed = host in policy["allowed_hosts"] or any(
        host.endswith(suffix) for suffix in policy["allowed_host_suffixes"]
    )
    if parsed.scheme != "https" or parsed.port not in (None, 443) or parsed.username or parsed.password or not allowed:
        raise ValueError("The collection URL is outside the approved HTTPS endpoint policy.")
    attempts = policy["max_attempts"]
    maximum = policy["max_delay_seconds"]
    if type(attempts) is not int or not 1 <= attempts <= 10 or not isinstance(maximum, (int, float)) or maximum < 0:
        raise ValueError("Invalid bounded HTTP retry configuration.")
    if not kwargs.get("timeout"):
        raise ValueError("Every collector request requires an explicit timeout.")
    kwargs["allow_redirects"] = False
    for attempt in range(attempts):
        response = getattr(requests, method.lower())(url, **kwargs)
        if 300 <= response.status_code < 400:
            raise RuntimeError("Unexpected HTTP redirect; collection endpoint must be reviewed.")
        if response.status_code not in RETRY_CODES or attempt == attempts - 1:
            return response
        delay = _retry_delay(response.headers, attempt, maximum)
        response.close()
        time.sleep(delay)
    raise RuntimeError("HTTP retry policy did not produce a response.")


def get(url: str, **kwargs):
    return _send("GET", url, **kwargs)


def post(url: str, **kwargs):
    return _send("POST", url, **kwargs)

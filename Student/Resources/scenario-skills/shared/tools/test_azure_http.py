import sys
import types

import pytest

import azure_http


class Response:
    def __init__(self, status, headers=None):
        self.status_code = status
        self.headers = headers or {}
        self.closed = False

    def close(self):
        self.closed = True


def test_retry_after_is_respected_and_attempts_are_bounded(monkeypatch):
    responses = [Response(429, {"Retry-After": "2"}), Response(503), Response(200)]
    pending = list(responses)
    sleeps, calls = [], []

    def get(url, **kwargs):
        calls.append(kwargs)
        return pending.pop(0)

    monkeypatch.setitem(sys.modules, "requests", types.SimpleNamespace(get=get))
    monkeypatch.setattr(azure_http.time, "sleep", sleeps.append)
    result = azure_http.get("https://management.azure.com/subscriptions", timeout=30)
    assert result.status_code == 200
    assert len(calls) == 3
    assert sleeps == [2, 2]
    assert all(call["allow_redirects"] is False for call in calls)
    assert responses[0].closed and responses[1].closed


def test_authorization_failure_is_not_retried(monkeypatch):
    calls = []
    monkeypatch.setitem(sys.modules, "requests", types.SimpleNamespace(
        get=lambda *args, **kwargs: calls.append(1) or Response(403)))
    assert azure_http.get("https://management.azure.com/subscriptions", timeout=30).status_code == 403
    assert calls == [1]


def test_large_server_delay_and_unapproved_endpoints_fail_closed(monkeypatch):
    monkeypatch.setitem(sys.modules, "requests", types.SimpleNamespace(
        get=lambda *args, **kwargs: Response(429, {"Retry-After": "120"})))
    with pytest.raises(RuntimeError, match="budget"):
        azure_http.get("https://management.azure.com/subscriptions", timeout=30)
    for url in ("http://management.azure.com/", "https://example.invalid/", "https://management.azure.com:8443/"):
        with pytest.raises(ValueError, match="policy"):
            azure_http.get(url, timeout=30)


def test_redirect_does_not_forward_credentials(monkeypatch):
    monkeypatch.setitem(sys.modules, "requests", types.SimpleNamespace(
        get=lambda *args, **kwargs: Response(302)))
    with pytest.raises(RuntimeError, match="redirect"):
        azure_http.get("https://management.azure.com/subscriptions", timeout=30)

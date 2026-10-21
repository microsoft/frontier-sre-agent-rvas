"""Unit tests for the pure helpers in gather_context (no Azure calls)."""

import gather_context as gc


def test_parse_resource_id():
    rid = "/subscriptions/abc/resourceGroups/rg1/providers/Microsoft.Compute/virtualMachines/vm1"
    assert gc.parse_resource_id(rid) == ("abc", "rg1")
    assert gc.parse_resource_id("") == ("", "")


def test_severity_for_activity():
    assert gc.severity_for_activity({"status": {"value": "Failed"}}) == "High"
    assert gc.severity_for_activity({"level": "Warning"}) == "Medium"
    assert gc.severity_for_activity({"level": "Informational", "status": {"value": "Succeeded"}}) == "Low"


def test_severity_for_health():
    assert gc.severity_for_health("Unavailable") == "Critical"
    assert gc.severity_for_health("Degraded") == "High"
    assert gc.severity_for_health("Available") == "Low"


def test_build_timeline_newest_first_and_banded():
    activity = [
        {"operationName": {"localizedValue": "Deploy"}, "status": {"value": "Succeeded"}, "caller": "u@x", "eventTimestamp": "2026-07-09T10:00:00Z", "level": "Informational"},
        {"operationName": {"localizedValue": "Scale"}, "status": {"value": "Failed"}, "eventTimestamp": "2026-07-09T11:00:00Z", "level": "Error"},
    ]
    health = [{"properties": {"availabilityState": "Unavailable", "summary": "down", "occuredTime": "2026-07-09T11:05:00Z"}}]
    timeline = gc.build_timeline(activity, health)
    assert timeline[0]["source"] == "Resource Health"  # 11:05 newest
    assert timeline[0]["_band"] == "Critical"
    assert timeline[1]["signal"] == "Scale"
    assert timeline[1]["severity"] == "High"


def test_collection_follows_activity_and_health_continuation(monkeypatch):
    responses = iter([{"value": [{"id": "one"}], "nextLink": "next"}, {"value": [{"id": "two"}]}])
    monkeypatch.setattr(gc, "_get", lambda *args: next(responses))
    notes = []
    assert len(gc._read_pages({}, "first", "Activity Log", notes)) == 2
    assert notes == []


def test_cap_and_failure_are_visible_incomplete_states(monkeypatch):
    monkeypatch.setattr(gc, "_get", lambda *args: {"value": [{"id": "one"}], "nextLink": "next"})
    notes = []
    gc._read_pages({}, "first", "Resource Health", notes, max_pages=1)
    assert "Incomplete" in notes[0] and "cap" in notes[0]
    def fail(*args):
        raise RuntimeError("denied")
    monkeypatch.setattr(gc, "_get", fail)
    notes = []
    assert gc._read_pages({}, "first", "Resource Health", notes) == []
    assert "Incomplete" in notes[0]


def test_neighbor_graph_truncation_is_explicit(monkeypatch):
    import sys
    from types import SimpleNamespace
    response = SimpleNamespace(status_code=200, headers={}, close=lambda: None, raise_for_status=lambda: None,
                               json=lambda: {"data": [{"id": "one"}], "resultTruncated": True})
    monkeypatch.setitem(sys.modules, "requests", SimpleNamespace(post=lambda *a, **kw: response))
    notes = []
    assert gc._run_graph({}, "query", notes) == [{"id": "one"}]
    assert "truncated" in notes[0]


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__]))

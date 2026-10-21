"""Unit tests for the pure helpers in change_scan (no Azure calls)."""

import change_scan as cs


def _ev(category, op, status="Succeeded", ts="2026-07-09T10:00:00Z", rid="/subscriptions/a/resourceGroups/rg/providers/x/vm1", health=None):
    event = {"category": {"value": category}, "operationName": {"value": op, "localizedValue": op}, "status": {"value": status}, "eventTimestamp": ts, "resourceId": rid, "resourceGroupName": "rg", "caller": "u@x"}
    if health:
        event["properties"] = {"currentHealthStatus": health}
    return event


def test_is_change_event():
    assert cs.is_change_event(_ev("Administrative", "Microsoft.Compute/virtualMachines/write")) is True
    assert cs.is_change_event(_ev("Administrative", "Microsoft.Compute/virtualMachines/read")) is False
    assert cs.is_change_event(_ev("ResourceHealth", "x/write")) is False


def test_is_health_degraded():
    assert cs.is_health_degraded(_ev("ResourceHealth", "x", health="Unavailable")) is True
    assert cs.is_health_degraded(_ev("ResourceHealth", "x", health="Available")) is False


def test_correlate_links_change_before_degradation():
    change = cs.extract_change(_ev("Administrative", "Microsoft.Compute/virtualMachines/write", ts="2026-07-09T10:00:00Z"))
    health = cs.extract_health(_ev("ResourceHealth", "x", ts="2026-07-09T10:30:00Z", health="Unavailable"))
    findings, linked = cs.correlate([change], [health], window_minutes=120)
    assert len(findings) == 1
    assert findings[0]["severity"] == "High"
    assert "30 min" in findings[0]["note"]
    assert len(linked) == 1


def test_correlate_ignores_change_after_or_outside_window():
    change = cs.extract_change(_ev("Administrative", "x/write", ts="2026-07-09T13:00:00Z"))
    health = cs.extract_health(_ev("ResourceHealth", "x", ts="2026-07-09T10:30:00Z", health="Unavailable"))
    findings, _ = cs.correlate([change], [health], window_minutes=120)
    assert findings == []


def test_classify_unlinked_delete_and_failure():
    delete = cs.extract_change(_ev("Administrative", "x/delete", status="Succeeded"))
    assert cs.classify_unlinked(delete)["severity"] == "Medium"
    fail = cs.extract_change(_ev("Administrative", "x/write", status="Failed"))
    assert "failed" in cs.classify_unlinked(fail)["note"].lower()
    ok = cs.extract_change(_ev("Administrative", "x/write", status="Succeeded"))
    assert cs.classify_unlinked(ok)["severity"] == "Low"


def test_build_report_data_counts():
    change = cs.extract_change(_ev("Administrative", "x/write", ts="2026-07-09T10:00:00Z"))
    health = cs.extract_health(_ev("ResourceHealth", "x", ts="2026-07-09T10:20:00Z", health="Unavailable"))
    data = cs.build_report_data([change], [health], 7, 1, {"a": "Sub A"}, [])
    assert data["summary_cards"][1]["value"] == "1"  # one linked
    assert data["title"] == "Change Audit"


def test_identical_rg_names_across_subscriptions_do_not_correlate():
    change = cs.extract_change(_ev("Administrative", "x/write", rid="/subscriptions/a/resourceGroups/rg/providers/x/vm1"))
    health = cs.extract_health(_ev("ResourceHealth", "x", ts="2026-07-09T10:20:00Z", health="Unavailable",
                                  rid="/subscriptions/b/resourceGroups/rg/providers/x/vm2"))
    assert change["subscription"] == "a" and health["subscription"] == "b"
    assert cs.correlate([change], [health])[0] == []


def test_all_successful_unlinked_writes_remain_in_report():
    changes = [cs.extract_change(_ev("Administrative", "x/write", rid=f"/subscriptions/a/resourceGroups/rg/providers/x/vm{i}")) for i in range(3)]
    data = cs.build_report_data(changes, [], 7, 1, {}, [])
    assert len(data["findings"]["rows"]) == 3
    assert data["assessment_status"] == "Complete"
    assert cs.build_report_data([], [], 7, 1, {}, ["read failed"])["assessment_status"] == "Partial"


def test_activity_cap_cannot_silently_drop_continuation(monkeypatch):
    import sys
    from types import SimpleNamespace
    import pytest
    response = SimpleNamespace(status_code=200, headers={}, close=lambda: None, raise_for_status=lambda: None,
                               json=lambda: {"value": [], "nextLink": "https://management.azure.com/next"})
    monkeypatch.setitem(sys.modules, "requests", SimpleNamespace(get=lambda *a, **kw: response))
    with pytest.raises(RuntimeError, match="40 page cap"):
        cs._read_activity({}, "a", "2026-10-20T00:00:00Z")


def test_activity_failure_retains_already_collected_write_records(monkeypatch):
    import sys
    from types import SimpleNamespace
    responses = iter([SimpleNamespace(status_code=200, headers={}, close=lambda: None, raise_for_status=lambda: None, json=lambda: {
        "value": [_ev("Administrative", "x/write")], "nextLink": "https://management.azure.com/next"})])
    monkeypatch.setitem(sys.modules, "requests", SimpleNamespace(get=lambda *a, **kw: next(responses)))
    notes = []
    events = cs._read_activity({}, "a", "2026-10-20T00:00:00Z", notes)
    assert len(events) == 1 and "Incomplete" in notes[0]
    report = cs.build_report_data([cs.extract_change(event) for event in events], [], 7, 1, {}, notes)
    assert len(report["collected_changes"]) == 1
    assert report["assessment_status"] == "Partial"


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__]))

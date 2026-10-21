"""Unit tests for the pure helpers in alert_hygiene (no Azure calls)."""

import alert_hygiene as ah


def _alert(rule, severity="Sev3", condition="Fired", state="New"):
    return {"properties": {"essentials": {"alertRule": rule, "severity": severity, "monitorCondition": condition, "alertState": state}}}


def test_aggregate_counts_and_severity():
    alerts = [_alert("r1", "Sev1"), _alert("r1", "Sev3", condition="Resolved", state="Closed"), _alert("r2")]
    stats = ah.aggregate_alerts(alerts)
    assert stats["r1"]["count"] == 2
    assert stats["r1"]["resolved"] == 1
    assert stats["r1"]["min_sev"] == 1
    assert stats["r2"]["count"] == 1


def test_classify_noisy_rule_high_at_double_threshold():
    stats = {"count": 45, "resolved": 0, "new": 0, "min_sev": 3, "name": "r1"}
    finding = ah.classify_rule("r1", stats, 20)
    assert finding["severity"] == "High"
    assert "fired 45 times" in finding["issue"]


def test_classify_measured_rapid_resolution():
    stats = {"count": 10, "resolved": 9, "rapid": 9, "duration_assessed": 9,
             "duration_unknown": 1, "new": 0, "min_sev": 1, "name": "r1"}
    finding = ah.classify_rule("r1", stats, 20)
    assert finding is not None
    assert "measured resolution" in finding["issue"]
    assert "without action" not in finding["issue"]
    assert finding["severity"] == "Medium"


def test_classify_returns_none_when_clean():
    stats = {"count": 3, "resolved": 1, "new": 0, "min_sev": 3, "name": "r1"}
    assert ah.classify_rule("r1", stats, 20) is None


def test_build_report_data_includes_disabled():
    alerts = [_alert("r1", "Sev1") for _ in range(25)]
    data = ah.build_report_data(alerts, [{"name": "off-rule"}], "7d", 1, 20, [])
    rules = [row["rule"] for row in data["findings"]["rows"]]
    assert "off-rule" in rules
    assert data["summary_cards"][0]["value"] == "25"


def test_closed_is_not_resolved_and_timestamps_are_required():
    stats = ah.aggregate_alerts([_alert("r", "Sev1", condition="Fired", state="Closed")])["r"]
    assert stats["closed"] == 1 and stats["resolved"] == 0 and stats["rapid"] == 0
    stats = ah.aggregate_alerts([_alert("r", "Sev1", condition="Resolved", state="Closed")] * 10)["r"]
    assert ah.classify_rule("r", stats, 20) is None


def test_rapid_resolution_needs_nonnegative_proven_duration():
    alert = _alert("r", condition="Resolved")
    essentials = alert["properties"]["essentials"]
    essentials.update(startDateTime="2026-10-20T10:00:00Z", monitorConditionResolvedDateTime="2026-10-20T10:04:00Z")
    assert ah.aggregate_alerts([alert])["r"]["rapid"] == 1
    for end in ("2026-10-20T09:59:00Z", "2026-10-20T11:00:00Z", "invalid", "2026-10-20T10:04:00"):
        essentials["monitorConditionResolvedDateTime"] = end
        assert ah.aggregate_alerts([alert])["r"]["rapid"] == 0


def test_missing_resolution_durations_are_not_reported_as_zero_percent():
    alerts = [_alert("r", "Sev1", condition="Resolved", state="Closed") for _ in range(25)]
    report = ah.build_report_data(alerts, [], "7d", 1, 20, [])
    row = report["findings"]["rows"][0]
    assert row["rapid_resolution"] == "Not assessed"
    assert row["duration_assessed"] == 0 and row["duration_unknown"] == 25
    assert row["duration_assessment_status"] == "Not assessed"
    assert row["monitor_resolved"] == "100%" and row["user_closed"] == "100%"
    assert report["assessment_status"] == "Partial"
    assert report["duration_coverage"]["assessment_status"] == "Not assessed"


def test_partial_duration_coverage_reports_an_explicit_lower_bound():
    fast = _alert("r", condition="Resolved", state="Closed")
    fast["properties"]["essentials"].update(
        startDateTime="2026-10-20T10:00:00Z", monitorConditionResolvedDateTime="2026-10-20T10:03:00Z")
    slow = _alert("r", condition="Resolved", state="Closed")
    slow["properties"]["essentials"].update(
        startDateTime="2026-10-20T10:00:00Z", monitorConditionResolvedDateTime="2026-10-20T11:00:00Z")
    invalid = _alert("r", condition="Resolved", state="Closed")
    invalid["properties"]["essentials"].update(startDateTime=None, monitorConditionResolvedDateTime="invalid")
    alerts = [fast, slow, invalid, _alert("r"), _alert("r")]
    report = ah.build_report_data(alerts, [], "7d", 1, 1, [])
    row = report["findings"]["rows"][0]
    assert row["rapid_resolution"] == "At least 20% (2/5 durations assessed; 3 unknown)"
    assert row["duration_assessment_status"] == "Partial"
    assert report["assessment_status"] == "Partial"
    assert any("lower bounds" in note and "unknown" in note for note in report["method_notes"])
    complete = ah.build_report_data([fast, slow], [], "7d", 1, 1, [])
    assert complete["assessment_status"] == "Complete"
    assert complete["findings"]["rows"][0]["rapid_resolution"] == "50%"


def test_invalid_or_pending_duration_is_unknown_not_assessed():
    for values in (
        {},
        {"startDateTime": None, "monitorConditionResolvedDateTime": None},
        {"startDateTime": "invalid", "monitorConditionResolvedDateTime": "invalid"},
        {"startDateTime": "2026-10-20T10:00:00", "monitorConditionResolvedDateTime": "2026-10-20T10:01:00"},
        {"startDateTime": "2026-10-20T10:00:00Z", "monitorConditionResolvedDateTime": "2026-10-20T09:59:00Z"},
    ):
        alert = _alert("r", condition="Resolved")
        alert["properties"]["essentials"].update(values)
        stats = ah.aggregate_alerts([alert])["r"]
        assert stats["duration_assessed"] == 0 and stats["duration_unknown"] == 1
        assert ah.rapid_resolution_label(stats) == "Not assessed"


def test_capped_pagination_is_explicit(monkeypatch):
    import sys
    from types import SimpleNamespace
    import pytest
    response = SimpleNamespace(status_code=200, headers={}, close=lambda: None, raise_for_status=lambda: None,
                               json=lambda: {"value": [], "nextLink": "https://management.azure.com/next"})
    monkeypatch.setitem(sys.modules, "requests", SimpleNamespace(get=lambda *a, **kw: response))
    with pytest.raises(RuntimeError, match="40 page cap"):
        ah._read_alerts({}, "sub", "7d")


def test_incomplete_or_unknown_scope_never_complete():
    assert ah.build_report_data([], [], "7d", 1, 20, ["query failed"])["assessment_status"] == "Partial"
    assert ah.build_report_data([], [], "7d", 0, 20, [])["assessment_status"] == "Not assessed"


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__]))

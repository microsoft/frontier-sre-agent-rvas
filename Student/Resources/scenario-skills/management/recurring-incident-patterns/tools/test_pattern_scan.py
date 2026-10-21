"""Unit tests for the pure helpers in pattern_scan (no Azure calls)."""

import pattern_scan as ps

VM = "/subscriptions/a/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm1"
DB = "/subscriptions/a/resourceGroups/rg/providers/Microsoft.Sql/servers/s/databases/db1"


def test_resource_type_from_id():
    assert ps.resource_type_from_id(VM) == "Microsoft.Compute/virtualMachines"
    assert ps.resource_type_from_id("") == "unknown"


def test_severity_by_count():
    assert ps.severity_by_count(12) == "High"
    assert ps.severity_by_count(6) == "Medium"
    assert ps.severity_by_count(3) == "Low"


def test_aggregate_counts_alerts_and_health():
    agg = ps.aggregate([VM, VM, DB], [VM])
    assert agg[VM.lower()]["alerts"] == 2
    assert agg[VM.lower()]["health"] == 1
    assert agg[VM.lower()]["count"] == 3
    assert agg[DB.lower()]["count"] == 1


def test_repeat_offenders_threshold_and_order():
    agg = ps.aggregate([VM, VM, VM, DB], [VM, DB])
    offenders = ps.repeat_offenders(agg, threshold=3)
    assert len(offenders) == 1  # only VM has >= 3 (4); DB has 2
    assert offenders[0]["name"] == "vm1"


def test_build_report_data_offender_count():
    agg = ps.aggregate([VM] * 5, [VM])
    data = ps.build_report_data(agg, "30d", 1, 3, [])
    assert data["summary_cards"][1]["value"] == "1"  # one repeat offender
    assert data["findings"]["rows"][0]["signal_count"] == 6
    assert data["summary_cards"][0]["label"] == "Resource signal occurrences"
    assert "not deduplicated or correlated incidents" in data["method_notes"][-1]


def test_arbitrary_windows_are_not_silently_rounded():
    import pytest
    for days in (0, 2, 14, 60):
        with pytest.raises(ValueError, match="exactly"):
            ps.main(days)


def test_alert_ids_are_deduplicated_and_cap_is_visible(monkeypatch):
    import sys
    from types import SimpleNamespace
    response = SimpleNamespace(status_code=200, headers={}, close=lambda: None, raise_for_status=lambda: None, json=lambda: {
        "value": [{"id": "alert-1", "properties": {"essentials": {"targetResource": VM}}}],
        "nextLink": "https://management.azure.com/next"})
    monkeypatch.setitem(sys.modules, "requests", SimpleNamespace(get=lambda *a, **kw: response))
    notes = []
    assert ps._read_alerts({}, "a", "7d", notes) == [VM]
    assert "40 page cap" in notes[0]


def test_collection_failure_does_not_become_complete_zero(monkeypatch):
    monkeypatch.setattr(ps, "_headers", lambda: {})
    monkeypatch.setattr(ps, "_list_subscriptions", lambda headers: ["a"])
    def fail(*args):
        raise RuntimeError("denied")
    monkeypatch.setattr(ps, "_read_alerts", fail)
    monkeypatch.setattr(ps, "_read_health", fail)
    report = ps.main(7)
    assert report["assessment_status"] == "Partial"
    assert "requested 7 days" in report["meta"]["window"]


def test_both_sources_receive_identical_explicit_utc_boundaries(monkeypatch):
    monkeypatch.setattr(ps, "_headers", lambda: {})
    monkeypatch.setattr(ps, "_list_subscriptions", lambda headers: ["a"])
    windows = {}
    def alerts(headers, sub, time_range, notes, *, start, end):
        windows["alerts"] = (start, end)
        return []
    def health(headers, sub, start, notes, *, end):
        windows["health"] = (start, end)
        return []
    monkeypatch.setattr(ps, "_read_alerts", alerts)
    monkeypatch.setattr(ps, "_read_health", health)
    report = ps.main(7)
    assert windows["alerts"] == windows["health"]
    assert all(value in report["meta"]["window"] for value in windows["alerts"])


def test_alert_custom_range_is_sent_without_relative_range(monkeypatch):
    import sys
    from types import SimpleNamespace
    from urllib.parse import parse_qs, urlparse
    urls = []
    response = SimpleNamespace(status_code=200, headers={}, close=lambda: None, raise_for_status=lambda: None, json=lambda: {"value": []})
    def get(url, **kwargs):
        urls.append(url)
        return response
    monkeypatch.setitem(sys.modules, "requests", SimpleNamespace(get=get))
    ps._read_alerts({}, "a", "7d", start="2026-10-13T00:00:00+00:00", end="2026-10-20T00:00:00+00:00")
    query = parse_qs(urlparse(urls[0]).query)
    assert query["customTimeRange"] == ["2026-10-13T00:00:00+00:00/2026-10-20T00:00:00+00:00"]
    assert "timeRange" not in query


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__]))

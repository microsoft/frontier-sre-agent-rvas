"""Unit tests for the pure helpers in observability_gap (no Azure calls)."""

import observability_gap as og
import pytest


def _res(name="vm1", sub="a", rg="rg1"):
    return {"name": name, "id": f"/subscriptions/{sub}/resourcegroups/{rg}/providers/microsoft.compute/virtualmachines/{name}",
            "type": "microsoft.compute/virtualmachines", "subscriptionId": sub, "resourceGroup": rg}


def test_alert_coverage_by_exact_id():
    res = _res()
    covered = {res["id"].lower()}
    assert og.is_alert_covered(res, covered, set(), set()) is True


def test_alert_coverage_by_resource_group_and_subscription():
    res = _res(sub="a", rg="rg1")
    assert og.is_alert_covered(res, set(), {"/subscriptions/a/resourcegroups/rg1"}, set()) is True
    assert og.is_alert_covered(res, set(), set(), {"/subscriptions/a"}) is True
    assert og.is_alert_covered(res, set(), set(), set()) is False


def test_classify_resource_flags_both_gaps():
    res = _res()
    finding = og.classify_resource(res, set(), True, set(), set(), set())
    assert "diagnostic settings" in finding["missing"]
    assert "alert candidate" in finding["missing"]
    assert finding["severity"] == "High"


def test_classify_resource_none_when_fully_wired():
    res = _res()
    diag = {res["id"].lower()}
    covered = {res["id"].lower()}
    assert og.classify_resource(res, diag, True, covered, set(), set()) is None


def test_subscription_findings_for_missing_wiring():
    findings = og.subscription_findings({"a"}, action_group_subs=set(), workspace_subs={"a"}, sub_names={"a": "Sub A"})
    assert findings == []  # Destinations may be in a different subscription.


def test_unknown_diagnostics_never_becomes_zero_blind_resources():
    data = og.build_report_data([], 3, 1, False, {}, [])
    assert data["summary_cards"][1]["value"] == "Unknown"
    assert data["assessment_status"] == "Partial"
    assert og.build_report_data([], 0, 0, False, {}, [])["assessment_status"] == "Not assessed"


def test_rules_require_enabled_actions_and_applicable_type_and_scope():
    rule = {"type": "microsoft.insights/metricalerts", "properties": {
        "enabled": True, "actions": [{"actionGroupId": "/subscriptions/other/actiongroup"}],
        "scopes": ["/subscriptions/a"], "targetResourceType": "Microsoft.Compute/virtualMachines"}}
    assert og.qualifying_scopes(rule, "microsoft.compute/virtualmachines") == ["/subscriptions/a"]
    assert og.qualifying_scopes(rule, "microsoft.sql/servers/databases") == []
    rule["properties"]["enabled"] = False
    assert og.qualifying_scopes(rule, "microsoft.compute/virtualmachines") == []
    rule["properties"]["enabled"] = True
    rule["properties"]["actions"] = []
    assert og.qualifying_scopes(rule, "microsoft.compute/virtualmachines") == []


def test_diagnostics_requires_enabled_signal_and_real_destination():
    assert og.usable_diagnostics([{"properties": {"workspaceId": "/subscriptions/central/workspaces/logs",
                                                 "logs": [{"enabled": True}]}}])
    assert not og.usable_diagnostics([{"properties": {"workspaceId": "/subscriptions/central/workspaces/logs",
                                                     "logs": [{"enabled": False}]}}])
    assert not og.usable_diagnostics([{"properties": {"logs": [{"enabled": True}]}}])


def test_inventory_query_failure_is_not_a_clean_empty_assessment(monkeypatch):
    monkeypatch.setattr(og, "_headers", lambda: {})
    monkeypatch.setattr(og, "_list_subscription_names", lambda headers: {"a": "A"})
    def fail(*args):
        raise RuntimeError("query failed")
    monkeypatch.setattr(og, "_run_graph", fail)
    data = og.main()
    assert data["assessment_status"] == "Not assessed"
    assert any("Incomplete" in note for note in data["method_notes"])


def test_denied_diagnostic_read_is_unknown_not_a_missing_setting(monkeypatch):
    import sys
    from types import SimpleNamespace
    monkeypatch.setattr(og, "_headers", lambda: {})
    monkeypatch.setattr(og, "_list_subscription_names", lambda headers: {"a": "A"})
    monkeypatch.setattr(og, "_run_graph", lambda headers, query: [] if "project id, type, properties" in query else [_res()])
    def fail(*args, **kwargs):
        raise RuntimeError("denied")
    monkeypatch.setitem(sys.modules, "requests", SimpleNamespace(get=fail))
    report = og.main()
    assert report["assessment_status"] == "Partial"
    assert report["summary_cards"][1]["value"] == "Unknown"
    assert all("diagnostic settings" not in row["missing"] for row in report["findings"]["rows"])


@pytest.mark.parametrize(("status", "attempts"), [(429, 3), (503, 3), (401, 1), (403, 1)])
def test_collector_uses_bounded_shared_retries_but_never_retries_authorization(monkeypatch, status, attempts):
    import sys
    from types import SimpleNamespace
    import azure_http

    calls, closed = [], []
    def fail():
        raise RuntimeError(f"HTTP {status}")
    response = SimpleNamespace(status_code=status, headers={"Retry-After": "0"},
                               close=lambda: closed.append(status), raise_for_status=fail)
    def get(url, **kwargs):
        calls.append(kwargs)
        return response
    monkeypatch.setitem(sys.modules, "requests", SimpleNamespace(get=get))
    monkeypatch.setattr(azure_http.time, "sleep", lambda delay: None)
    with pytest.raises(RuntimeError, match=f"HTTP {status}"):
        og._list_subscription_names({})
    assert len(calls) == attempts
    assert len(closed) == attempts - 1
    assert all(call["allow_redirects"] is False and call["timeout"] for call in calls)


@pytest.mark.parametrize("collector", [
    ("management", "observability-coverage-gap", "observability_gap.py"),
    ("management", "alert-hygiene-review", "alert_hygiene.py"),
    ("management", "incident-triage-rca", "gather_context.py"),
    ("management", "recurring-incident-patterns", "pattern_scan.py"),
    ("management", "change-audit", "change_scan.py"),
    ("network-topology", "flowlog-firewall-advisor", "flowlog_firewall_advisor.py"),
])
def test_collector_bootstraps_shared_tools_in_an_isolated_python_process(collector):
    import subprocess
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    category, skill, filename = collector
    source = root / category / skill / "tools" / filename
    result = subprocess.run(
        [sys.executable, "-I", "-B", "-c", "import runpy, sys; runpy.run_path(sys.argv[1]); import azure_http", str(source)],
        cwd=root, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__]))

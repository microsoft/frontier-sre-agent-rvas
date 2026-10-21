"""Unit tests for the pure helpers in readiness_check (no Azure calls)."""

import readiness_check as rc
from unittest.mock import patch
from unittest.mock import Mock
from types import SimpleNamespace
import sys


def _complete():
    return [{"category": c, "check": c, "state": "Complete"} for c in rc.CATEGORIES]


def test_verdict_for():
    assert rc.verdict_for(["High"]) == "NO-GO"
    assert rc.verdict_for(["Critical", "Medium"]) == "NO-GO"
    assert rc.verdict_for(["Medium"]) == "CAUTION"
    assert rc.verdict_for([]) == "GO"


def test_verdicts_overall_is_worst():
    findings = [
        {"category": "Reliability", "severity": "High"},
        {"category": "Exposure", "severity": "Medium"},
    ]
    v = rc.verdicts(findings, _complete())
    assert v["Reliability"] == "NO-GO"
    assert v["Exposure"] == "CAUTION"
    assert v["Capacity"] == "GO"
    assert v["overall"] == "NO-GO"


def test_classify_ports():
    assert rc.classify_ports(["*"])[0] == "Critical"
    assert rc.classify_ports(["22"])[0] == "Critical"
    assert rc.classify_ports(["1433"])[0] == "High"
    assert rc.classify_ports(["8080"])[0] == "Medium"


def test_source_is_internet():
    assert rc.source_is_internet("*", None) is True
    assert rc.source_is_internet("10.0.0.0/8", None) is False


def test_build_report_data_verdict_cards():
    findings = [rc._finding("Reliability", {"name": "vm1", "subscriptionId": "a"}, "no zone", "fix", "High")]
    data = rc.build_report_data(findings, "a", [], _complete())
    assert data["summary_cards"][0]["value"] == "NO-GO"  # overall
    assert data["summary_cards"][1]["value"] == "NO-GO"  # reliability
    assert data["summary_cards"][2]["value"] == "GO"     # exposure clean


def test_findings_alone_never_imply_complete_assessment():
    assert rc.verdicts([])["overall"] == "INCOMPLETE"
    assert rc.build_report_data([], "a", [])["assessment_status"] == "Not assessed"


def test_all_read_failures_never_return_go():
    with patch.object(rc, "_headers", return_value={}), patch.object(rc, "_run_graph", side_effect=RuntimeError("denied")):
        data = rc.main("subscription")
    assert data["summary_cards"][0]["value"] == "INCOMPLETE"
    assert data["assessment_status"] == "Not assessed"
    assert all(a["state"] == "Not assessed" for a in data["assessments"])


def test_empty_scope_never_returns_go():
    with patch.object(rc, "_headers", return_value={}), patch.object(rc, "_run_graph", return_value=[]):
        data = rc.main("subscription")
    assert data["summary_cards"][0]["value"] == "INCOMPLETE"
    assert data["assessment_status"] == "Not assessed"


def _graph(query):
    if "project id" in query:
        return [{"id": "resource"}]
    if "distinct location" in query:
        return [{"location": "westeurope"}]
    return []


def test_capacity_failure_is_recorded_and_blocks_go():
    with patch.object(rc, "_headers", return_value={}), patch.object(rc, "_run_graph", side_effect=lambda _, q: _graph(q)), patch.object(rc, "_get", side_effect=RuntimeError("denied")):
        data = rc.main("subscription")
    assert data["summary_cards"][3]["value"] == "INCOMPLETE"
    assert data["assessment_status"] == "Partial"
    assert len([a for a in data["assessments"] if a["category"] == "Capacity"]) == 2


def test_empty_capacity_response_is_not_a_pass():
    with patch.object(rc, "_headers", return_value={}), patch.object(rc, "_run_graph", side_effect=lambda _, q: _graph(q)), patch.object(rc, "_get", return_value=[]):
        assert rc.main("subscription")["summary_cards"][0]["value"] == "INCOMPLETE"


def test_complete_clean_reads_can_return_go():
    with patch.object(rc, "_headers", return_value={}), patch.object(rc, "_run_graph", side_effect=lambda _, q: _graph(q)), patch.object(rc, "_get", return_value=[{"currentValue": 1, "limit": 100}]):
        data = rc.main("subscription")
    assert data["assessment_status"] == "Complete"
    assert data["summary_cards"][0]["value"] == "GO"


def test_capacity_get_uses_shared_bounded_retry_adapter():
    import azure_http
    busy = SimpleNamespace(status_code=429, headers={"Retry-After": "0"}, close=Mock())
    ready = SimpleNamespace(status_code=200, headers={}, close=Mock(), raise_for_status=Mock(),
                            json=lambda: {"value": [{"currentValue": 1, "limit": 100}]})
    get = Mock(side_effect=[busy, ready])
    with patch.dict(sys.modules, {"requests": SimpleNamespace(get=get)}), patch.object(azure_http.time, "sleep"):
        rows = rc._get({}, "https://management.azure.com/subscriptions/s/providers/Microsoft.Compute/locations/eastus/usages")
    assert rows[0]["limit"] == 100
    assert get.call_count == 2
    assert get.call_args.kwargs["allow_redirects"] is False
    busy.close.assert_called_once()


def test_authorization_failure_is_not_retried():
    denied = SimpleNamespace(status_code=403, headers={}, close=Mock(), raise_for_status=Mock(side_effect=RuntimeError("denied")))
    get = Mock(return_value=denied)
    with patch.dict(sys.modules, {"requests": SimpleNamespace(get=get)}):
        try:
            rc._get({}, "https://management.azure.com/subscriptions/s/providers/Microsoft.Compute/locations/eastus/usages")
        except RuntimeError:
            pass
        else:
            raise AssertionError("Denied collection must fail")
    get.assert_called_once()


if __name__ == "__main__":
    for name, function in sorted(globals().items()):
        if name.startswith("test_") and callable(function):
            function()
            print(f"ok {name}")
    print("all readiness_check tests passed")

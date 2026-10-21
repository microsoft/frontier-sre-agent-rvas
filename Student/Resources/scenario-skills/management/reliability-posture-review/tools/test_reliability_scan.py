"""Unit tests for the pure helpers in reliability_scan (no Azure calls)."""

import reliability_scan as rs


def test_adjust_severity_never_infers_criticality_from_name():
    assert rs.adjust_severity("High", "vm-prod-web01") == "High"
    assert rs.adjust_severity("High", "vm-sandbox-01") == "High"
    assert rs.adjust_severity("Medium", "lab-cosmos") == "Medium"
    assert rs.adjust_severity("Low", "dev-thing") == "Low"


def test_severity_counts_ordered_critical_first():
    findings = [
        {"severity": "Low"},
        {"severity": "High"},
        {"severity": "High"},
        {"severity": "Critical"},
    ]
    counts = rs.severity_counts(findings)
    assert [c["name"] for c in counts] == ["Critical", "High", "Low"]
    assert counts[1]["value"] == 2
    assert all("band" in c for c in counts)


def test_subscription_counts_highest_first():
    findings = [
        {"subscription": "a"},
        {"subscription": "a"},
        {"subscription": "b"},
    ]
    rows = rs.subscription_counts(findings, {"a": "Sub A", "b": "Sub B"})
    assert rows[0]["name"] == "Sub A"
    assert rows[0]["value"] == 2


def test_build_report_data_shape():
    findings = [
        {"resource": "vm1", "severity": "High", "subscription": "a", "resource_group": "rg1", "issue": "x", "recommendation": "y", "resource_type": "Virtual machine"},
        {"resource": "sa1", "severity": "Medium", "subscription": "a", "resource_group": "rg1", "issue": "x", "recommendation": "y", "resource_type": "Storage account"},
    ]
    data = rs.build_report_data(findings, {"a": "Sub A"}, 1, [])
    assert data["title"] == "Reliability Posture Review"
    assert data["findings"]["rows"][0]["severity"] == "High"  # sorted, High first
    assert data["findings"]["rows"][0]["_band"] == "High"
    assert data["summary_cards"][1]["value"] == "1"  # one Critical/High
    assert data["findings"]["rows"][0]["subscription"] == "Sub A"


def test_application_gateway_absent_zones_is_unknown_not_nonredundant():
    rules = {r["key"]: r for r in rs.RULES}
    assert rules["appgw_zone_applicability"]["severity"] == "Unknown"
    assert "does not mean absent redundancy" in rules["appgw_zone_applicability"]["recommendation"]
    assert "array_length(zones) == 1" in rules["appgw_single_zone"]["kql"]
    assert "Standard_v2" in rules["appgw_single_zone"]["kql"]


def test_single_zonal_vm_is_not_workload_redundancy():
    rule = next(r for r in rs.RULES if r["key"] == "vm_workload_topology")
    assert rule["severity"] == "Unknown"
    assert "One zonal VM is not a redundant workload" in rule["recommendation"]
    assert "array_length(zones) > 0" in rule["kql"]


def test_unknown_topology_makes_report_partial():
    data = rs.build_report_data([{"severity": "Unknown"}], {}, 1, [])
    assert data["assessment_status"] == "Partial"


def test_failed_queries_cannot_be_complete():
    from unittest.mock import patch
    with patch.object(rs, "_headers", return_value={}), patch.object(rs, "_list_subscription_names", return_value={"a": "A"}), patch.object(rs, "_run_graph", side_effect=RuntimeError("denied")):
        data = rs.main()
    assert data["assessment_status"] != "Complete"


if __name__ == "__main__":
    for name, function in sorted(globals().items()):
        if name.startswith("test_") and callable(function):
            function()
            print(f"ok {name}")
    print("all reliability_scan tests passed")

"""Unit tests for the pure helpers in network_exposure (no Azure calls)."""

import network_exposure as ne


def test_source_is_internet():
    assert ne.source_is_internet("*", None) is True
    assert ne.source_is_internet("Internet", None) is True
    assert ne.source_is_internet("10.0.0.0/8", None) is False
    assert ne.source_is_internet("VirtualNetwork", ["0.0.0.0/0"]) is True
    assert ne.source_is_internet("::/0", None) is True
    assert ne.source_is_internet("0.0.0.0/1", ["128.0.0.0/1"]) is True
    assert ne.source_is_internet("::/1", ["8000::/1"]) is True
    assert ne.source_is_internet("10.0.0.0/8", ["fc00::/7"]) is False


def test_unknown_sources_are_not_silently_safe():
    assert ne.source_coverage(None, []) == "Unknown"
    assert ne.source_coverage("AzureCloud", ["not-a-cidr"]) == "Unknown"
    finding = ne.classify_nsg_rule({"src": "AzureCloud", "portRange": "22"})
    assert finding["reachability"] == "Not assessed"
    assert finding["source_coverage"] == "Unknown"


def test_sql_public_endpoint_is_review_not_proven_unrestricted():
    row = {"id": "/subscriptions/a/resourceGroups/rg/providers/Microsoft.Sql/servers/server", "type": "microsoft.sql/servers", "pna": "Enabled"}
    finding = ne.classify_paas(row)
    assert "not assessed" in finding["detail"]
    assert finding["resource_id"] == row["id"]
    assert ne.classify_paas(dict(row, pna="Disabled")) is None


def test_empty_scope_is_not_assessed_and_ids_distinguish_same_names():
    assert ne.build_report_data([], 0, [])["assessment_status"] == "Not assessed"
    rows = [ne.classify_nsg_rule({"id": identity, "name": "same", "src": "*", "portRange": "22"}) for identity in ("one", "two")]
    assert ne.build_report_data(rows, 1, [])["summary_cards"][0]["value"] == "2"


def test_port_in_spec():
    assert ne.port_in_spec(22, "22") is True
    assert ne.port_in_spec(22, "*") is True
    assert ne.port_in_spec(3389, "3000-4000") is True
    assert ne.port_in_spec(22, "80") is False


def test_classify_open_ports():
    assert ne.classify_open_ports(["*"])[0] == "Critical"
    assert ne.classify_open_ports(["3389"])[0] == "Critical"
    assert ne.classify_open_ports(["1433"])[0] == "High"
    assert ne.classify_open_ports(["8080"])[0] == "Medium"


def test_classify_nsg_rule_internet_mgmt():
    row = {"name": "nsg1", "subscriptionId": "a", "ruleName": "rdp", "src": "*", "srcs": None, "portRange": "3389", "portRanges": None}
    finding = ne.classify_nsg_rule(row)
    assert finding["severity"] == "Critical"
    assert "management ports" in finding["detail"]
    assert finding["reachability"] == "Not assessed"
    assert "Not effective reachability" in finding["detail"]


def test_classify_nsg_rule_internal_source_is_none():
    row = {"name": "nsg1", "subscriptionId": "a", "ruleName": "x", "src": "10.0.0.0/8", "srcs": None, "portRange": "3389", "portRanges": None}
    assert ne.classify_nsg_rule(row) is None


def test_build_report_data_counts_critical():
    row = {"name": "nsg1", "subscriptionId": "a", "ruleName": "rdp", "src": "*", "srcs": None, "portRange": "22", "portRanges": None}
    findings = [ne.classify_nsg_rule(row)]
    data = ne.build_report_data(findings, 1, [])
    assert data["summary_cards"][1]["value"] == "1"  # one critical
    assert data["title"] == "Network Exposure Review"


if __name__ == "__main__":
    for name, function in sorted(globals().items()):
        if name.startswith("test_") and callable(function):
            function()
            print(f"ok {name}")
    print("all network_exposure tests passed")

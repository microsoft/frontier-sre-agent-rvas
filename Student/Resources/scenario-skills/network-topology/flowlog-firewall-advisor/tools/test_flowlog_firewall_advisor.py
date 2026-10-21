"""Unit tests for the flow log firewall advisor analysis logic.

No Azure dependency and no credential. The Azure imports in the tool are lazy, so
everything asserted here runs offline.

    python -m unittest test_flowlog_firewall_advisor -v
"""

import unittest

from flowlog_firewall_advisor import (
    RULE_COMBINATION_LIMIT,
    TRUNCATION,
    _parse_utc,
    build_denied_keys,
    build_report,
    build_rules,
    classify,
    is_platform_address,
    is_private_address,
    flow_axis,
    merge_port_ranges,
    port_expression_count,
    rule_combinations,
    scoped_query,
    service_tag_for,
    summarise_addresses,
)


def tuple_row(src, dst, port, status="Allowed", direction="Outbound",
              flow_type="IntraVNet", flows=10, byte_count=1000, tags=None, protocol="TCP"):
    return {
        "SrcIp": src, "DestIp": dst, "DestPort": port, "Protocol": protocol,
        "Direction": direction, "Status": status, "FlowType": flow_type,
        "Flows": flows, "Bytes": byte_count, "DestTags": tags or [],
        "AclRules": [], "SrcVm": "", "DestVm": "",
        "FirstSeenUtc": "2026-08-24T10:00:00Z", "LastSeenUtc": "2026-08-24T11:00:00Z",
    }


class TestAddressClassification(unittest.TestCase):
    def test_platform_addresses_are_recognised(self):
        for address in ("168.63.129.16", "169.254.169.254", "127.0.0.1", "224.0.0.1"):
            self.assertTrue(is_platform_address(address), address)

    def test_ordinary_addresses_are_not_platform(self):
        for address in ("10.42.1.4", "20.60.1.1", "192.168.1.1"):
            self.assertFalse(is_platform_address(address), address)

    def test_private_ranges(self):
        self.assertTrue(is_private_address("10.42.1.4"))
        self.assertTrue(is_private_address("192.168.0.1"))
        self.assertFalse(is_private_address("20.60.1.1"))


class TestPortHandling(unittest.TestCase):
    def test_contiguous_ports_collapse_to_a_range(self):
        self.assertEqual(merge_port_ranges([8080, 8081, 8082, 8083]), ["8080-8083"])

    def test_non_contiguous_ports_stay_separate(self):
        self.assertEqual(merge_port_ranges([443, 80, 8080]), ["80", "443", "8080"])

    def test_mixed_runs(self):
        self.assertEqual(merge_port_ranges([80, 443, 444, 445, 8080]), ["80", "443-445", "8080"])

    def test_range_counts_every_port_it_spans(self):
        self.assertEqual(port_expression_count(["80", "443-445"]), 4)

    def test_documented_rule_budget_groups_destination_ports_in_fourteens(self):
        for port_count, groups in ((1, 1), (14, 1), (15, 2), (28, 2), (29, 3)):
            self.assertEqual(rule_combinations(2, 3, 5, port_count), 2 * 3 * 5 * groups)

    def test_build_rules_uses_documented_divisor_for_expanded_port_range(self):
        rows = [tuple_row("10.0.0.1", "10.0.1.1", p) for p in range(80, 95)]
        self.assertEqual(build_rules(rows)["combinations"], 2)


class TestAddressSummary(unittest.TestCase):
    def test_few_hosts_stay_as_host_routes(self):
        addresses, collapsed = summarise_addresses(["10.42.1.4", "10.42.1.5"])
        self.assertEqual(addresses, ["10.42.1.4/32", "10.42.1.5/32"])
        self.assertEqual(collapsed, [])

    def test_enough_hosts_collapse_and_the_widening_is_reported(self):
        hosts = ["10.42.1.%d" % n for n in range(4, 10)]
        addresses, collapsed = summarise_addresses(hosts)
        self.assertEqual(addresses, ["10.42.1.0/24"])
        self.assertEqual(len(collapsed), 1)
        self.assertEqual(collapsed[0]["network"], "10.42.1.0/24")
        self.assertEqual(len(collapsed[0]["observed_hosts"]), 6)


class TestDeniedHandling(unittest.TestCase):
    def test_denied_connections_are_keyed(self):
        rows = [tuple_row("10.0.0.1", "10.0.0.2", 9999, status="Denied")]
        self.assertIn(("10.0.0.1", "10.0.0.2", 9999, "TCP"), build_denied_keys(rows))

    def test_a_connection_denied_at_the_destination_never_becomes_an_allow_rule(self):
        """The case real flow logs exposed and synthetic data did not.

        One blocked connection appears twice: allowed leaving the source, denied
        arriving at the destination. Trusting the allowed record produces a rule
        permitting traffic the current policy blocks.
        """
        rows = [
            tuple_row("10.42.1.4", "10.42.2.4", 9999, status="Allowed", direction="Outbound", flows=55),
            tuple_row("10.42.1.4", "10.42.2.4", 9999, status="Denied", direction="Inbound", flows=165),
            tuple_row("10.42.1.4", "10.42.2.4", 443, status="Allowed", flows=100),
        ]
        result = build_rules(rows)

        every_port = {port for rule in result["rules"] for port in rule["ports"]}
        self.assertNotIn("9999", every_port)
        self.assertIn("443", every_port)
        self.assertEqual(result["excluded"]["blocked_elsewhere"], 1)

    def test_platform_traffic_never_reaches_a_rule(self):
        rows = [
            tuple_row("10.42.1.4", "168.63.129.16", 53, protocol="UDP"),
            tuple_row("10.42.1.4", "169.254.169.254", 80),
            tuple_row("10.42.1.4", "10.42.2.4", 443),
        ]
        result = build_rules(rows)
        addresses = {a for rule in result["rules"] for a in rule["sources"] + rule["destinations"]}
        self.assertFalse(any("168.63" in a or "169.254" in a for a in addresses))
        self.assertEqual(result["excluded"]["platform"], 2)


class TestConsolidation(unittest.TestCase):
    def test_consolidation_invents_no_unobserved_pair(self):
        rows = [
            tuple_row("10.0.0.1", "10.0.1.1", 443),
            tuple_row("10.0.0.2", "10.0.1.1", 443),
            tuple_row("10.0.0.1", "10.0.1.1", 80),
            tuple_row("10.0.0.2", "10.0.1.1", 80),
        ]
        observed = {(r["SrcIp"], r["DestIp"], r["DestPort"]) for r in rows}
        result = build_rules(rows)

        for rule in result["rules"]:
            for source in rule["sources"]:
                for destination in rule["destinations"]:
                    for port in rule["ports"]:
                        if "-" in port or not source.endswith("/32") or not destination.endswith("/32"):
                            continue
                        key = (source[:-3], destination[:-3], int(port))
                        self.assertIn(key, observed, "invented pair %s" % (key,))

    def test_minimum_flow_threshold_filters_noise(self):
        rows = [
            tuple_row("10.0.0.1", "10.0.1.1", 443, flows=100),
            tuple_row("10.0.0.9", "10.0.1.1", 4444, flows=1),
        ]
        result = build_rules(rows, min_flows=10)
        self.assertEqual(result["excluded"]["below_threshold"], 1)
        self.assertNotIn("4444", {p for rule in result["rules"] for p in rule["ports"]})

    def test_service_tag_is_preferred_over_the_ip_literal(self):
        rows = [tuple_row("10.0.0.1", "20.60.1.1", 443, flow_type="AzurePublic",
                          tags=["20.60.1.1|Storage.westeurope"])]
        result = build_rules(rows)
        self.assertIn("Storage.westeurope",
                      {d for rule in result["rules"] for d in rule["destinations"]})

    def test_service_tag_extraction(self):
        self.assertEqual(service_tag_for({"DestTags": ["20.60.1.1|Storage.westeurope"]}), "Storage.westeurope")
        self.assertIsNone(service_tag_for({"DestTags": []}))


class TestSeverity(unittest.TestCase):
    def test_management_ports_across_the_boundary_are_critical(self):
        severity, _ = classify(["10.0.0.1/32"], ["1.2.3.4/32"], ["22"], False, "NorthSouth")
        self.assertEqual(severity, "Critical")

    def test_public_egress_without_a_service_tag_is_high(self):
        severity, _ = classify(["10.0.0.1/32"], ["1.2.3.4/32"], ["443"], False, "NorthSouth")
        self.assertEqual(severity, "High")

    def test_a_service_tag_destination_is_not_high(self):
        severity, _ = classify(["10.0.0.1/32"], ["Storage.westeurope"], ["443"], True, "NorthSouth")
        self.assertNotEqual(severity, "High")

    def test_ordinary_internal_service_traffic_is_low(self):
        severity, _ = classify(["10.0.0.1/32"], ["10.0.1.1/32"], ["443"], False, "EastWest")
        self.assertEqual(severity, "Low")

    def test_a_subnet_source_is_flagged_as_broader_than_observed(self):
        severity, _ = classify(["10.0.0.0/24"], ["10.0.1.1/32"], ["443"], False, "EastWest")
        self.assertEqual(severity, "Medium")


class TestFlowAxis(unittest.TestCase):
    """A real workspace labelled 854 of 1387 private to private flows `Unknown`, which
    ranked internal traffic as public egress and duplicated every rule for the pair."""

    def test_unknown_flow_type_between_private_addresses_is_east_west(self):
        self.assertEqual(flow_axis(tuple_row("10.42.1.4", "10.42.2.4", 443, flow_type="Unknown")),
                         "EastWest")

    def test_a_public_destination_stays_on_the_boundary(self):
        self.assertEqual(flow_axis(tuple_row("10.42.1.4", "13.107.246.53", 443, flow_type="Unknown")),
                         "NorthSouth")

    def test_the_label_still_decides_when_an_endpoint_is_public(self):
        self.assertEqual(flow_axis(tuple_row("10.42.1.4", "13.107.246.53", 443, flow_type="InterVNet")),
                         "EastWest")

    def test_one_pair_yields_one_rule_whatever_the_label(self):
        rows = [tuple_row("10.42.1.4", "10.42.2.4", 443, flow_type="IntraVNet"),
                tuple_row("10.42.1.4", "10.42.2.4", 443, flow_type="Unknown")]
        self.assertEqual(len(build_rules(rows)["rules"]), 1)


class TestReportShape(unittest.TestCase):
    def test_report_carries_what_the_renderer_needs(self):
        rows = [
            tuple_row("10.42.1.4", "10.42.2.4", 443, flows=100, byte_count=500000),
            tuple_row("10.42.1.4", "10.42.2.4", 9999, status="Denied", direction="Inbound"),
        ]
        report = build_report(build_rules(rows), {"window": "7 days", "scope": "test", "tuple_count": len(rows)})

        for key in ("title", "subtitle", "meta", "summary_cards", "charts", "findings",
                    "candidates", "method_notes"):
            self.assertIn(key, report)
        self.assertIn("rows", report["findings"])
        self.assertIn("columns", report["findings"])
        for row in report["findings"]["rows"]:
            self.assertIn("_band", row)
        for candidate in report["candidates"]:
            self.assertIn("band", candidate)
            self.assertIn("command", candidate)

    def test_budget_breach_is_the_first_note(self):
        rows = [tuple_row("10.0.%d.%d" % (a, b), "10.9.9.9", 443 + p, flows=50)
                for a in range(3) for b in range(4, 30) for p in range(6)]
        analysis = build_rules(rows)
        report = build_report(analysis, {"window": "7 days", "scope": "test", "tuple_count": len(rows)})
        if analysis["combinations"] > RULE_COMBINATION_LIMIT:
            self.assertIn("above the documented Azure Firewall policy limit", report["method_notes"][0])


class TestTimestampParsing(unittest.TestCase):
    """Log Analytics returns seven fractional digits, which fromisoformat rejects
    before Python 3.11. This crashed the coverage check against a real workspace."""

    def test_seven_digit_fraction_parses(self):
        parsed = _parse_utc("2026-08-24T11:22:11.7064525Z")
        self.assertEqual(parsed.year, 2026)
        self.assertEqual(parsed.microsecond, 706452)

    def test_no_fraction_parses(self):
        self.assertEqual(_parse_utc("2026-08-24T11:22:11Z").second, 11)

    def test_result_is_timezone_aware(self):
        self.assertIsNotNone(_parse_utc("2026-08-24T11:22:11.706Z").tzinfo)


class TestTruncationReporting(unittest.TestCase):
    """A rule set built from partial data looks identical to one built from complete
    data, so truncation has to reach the report rather than be inferred."""

    def tearDown(self):
        del TRUNCATION[:]

    def test_truncation_becomes_the_first_note(self):
        TRUNCATION.append("the service returned a partial result")
        report = build_report(build_rules([]), {"window": "7 days", "scope": "t", "tuple_count": 0})
        self.assertTrue(report["method_notes"][0].startswith("Incomplete data."))

    def test_no_truncation_leaves_notes_alone(self):
        report = build_report(build_rules([]), {"window": "7 days", "scope": "t", "tuple_count": 0})
        self.assertFalse(report["method_notes"][0].startswith("Incomplete data."))


def test_subscription_and_vnet_filters_constrain_workspace_query():
    from flowlog_firewall_advisor import TUPLE_QUERY, COVERAGE_QUERY
    sub = "11111111-1111-1111-1111-111111111111"
    target = f"/subscriptions/{sub}/resourceGroups/rg/providers/Microsoft.Network/virtualNetworks/vnet"
    for base in (TUPLE_QUERY, COVERAGE_QUERY):
        query = scoped_query(base, sub, [target])
        assert "tolower(TargetResourceId) startswith '/subscriptions/" in query
        assert target.lower() in query
        assert query.index("TargetResourceId") < query.index("| summarize")


def test_invalid_scope_cannot_inject_kql():
    import pytest
    with pytest.raises(ValueError):
        scoped_query("query", "invalid' | take 1")


def test_report_sanitizes_commands_and_requires_review():
    analysis = build_rules([tuple_row("10.42.1.4", "10.42.2.4", 443)])
    report = build_report(analysis, {"scope": "test", "token": "secret-value"})
    assert "10.42.1.4" not in str(report)
    assert "secret-value" not in str(report)
    assert "human review required" in report["sharing_review"]["status"]
    internal = build_report(analysis, {"scope": "test"}, include_identifiers=True)
    assert "10.42.1.4" in internal["candidates"][0]["command"]
    assert not any("non enforcing mode alongside" in note for note in internal["method_notes"])


def test_failed_workspace_is_reported_as_skipped_not_complete(monkeypatch, capsys):
    import json
    import flowlog_firewall_advisor as advisor
    monkeypatch.setattr(advisor, "resolve_agent_identity", lambda: None)
    def fail(*args):
        raise RuntimeError("denied")
    monkeypatch.setattr(advisor, "query_workspace", fail)
    try:
        advisor.main(["--workspace", "workspace-guid"])
        report = json.loads(capsys.readouterr().out)
        assert report["assessment_status"] == "Partial"
        assert report["skipped_workspaces"]
        assert any("query failed" in note.lower() for note in report["method_notes"])
    finally:
        advisor.TRUNCATION.clear()
        advisor.SKIPPED_WORKSPACES.clear()


def test_discovery_scopes_subscription_and_reports_skipped_workspaces(monkeypatch):
    import sys
    from types import SimpleNamespace
    import flowlog_firewall_advisor as advisor
    sub = "11111111-1111-1111-1111-111111111111"
    payloads = []
    monkeypatch.setattr(advisor, "_credential", lambda *a: SimpleNamespace(get_token=lambda *a: SimpleNamespace(token="fixture-token")))
    response = SimpleNamespace(status_code=200, headers={}, close=lambda: None, raise_for_status=lambda: None, json=lambda: {"data": [
        {"flowLogEnabled": True, "trafficAnalyticsEnabled": True, "workspaceCustomerId": "selected"},
        {"flowLogEnabled": False, "trafficAnalyticsEnabled": True, "workspaceCustomerId": "skipped"}]})
    def post(url, **kwargs):
        payloads.append(kwargs["json"])
        return response
    monkeypatch.setitem(sys.modules, "requests", SimpleNamespace(post=post))
    try:
        workspaces = advisor.discover_workspaces(subscription=sub)
        assert payloads[0]["subscriptions"] == [sub]
        assert len(workspaces) == 1 and workspaces[0]["workspace_customer_id"] == "selected"
        assert advisor.SKIPPED_WORKSPACES
    finally:
        advisor.SKIPPED_WORKSPACES.clear()


def test_target_subscription_mismatch_is_rejected_before_query():
    import pytest
    sub = "11111111-1111-1111-1111-111111111111"
    target = "/subscriptions/22222222-2222-2222-2222-222222222222/resourceGroups/rg/providers/Microsoft.Network/virtualNetworks/vnet"
    with pytest.raises(ValueError, match="belong"):
        scoped_query("query", sub, [target])


if __name__ == "__main__":
    unittest.main(verbosity=2)

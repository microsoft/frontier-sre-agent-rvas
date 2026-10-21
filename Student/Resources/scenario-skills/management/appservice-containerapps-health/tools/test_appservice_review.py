"""Unit tests for the pure evaluate functions in appservice_review (no Azure calls)."""

import appservice_review as ar


def test_site_https_and_tls():
    row = {"name": "s1", "subscriptionId": "a", "kind": "app", "properties": {"httpsOnly": False, "siteConfig": {"minTlsVersion": "1.0"}}}
    checks = [f["check"] for f in ar.evaluate_site(row)]
    assert "HTTPS not enforced" in checks
    assert "Minimum TLS below 1.2" in checks


def test_site_alwayson_and_healthcheck_skipped_without_siteconfig():
    row = {"name": "s1", "subscriptionId": "a", "kind": "app", "properties": {"httpsOnly": True}}
    findings = ar.evaluate_site(row)
    assert findings and all(f["severity"] == "Unknown" for f in findings)


def test_site_function_app_skips_alwayson():
    row = {"name": "f1", "subscriptionId": "a", "kind": "functionapp", "properties": {"httpsOnly": True, "siteConfig": {"alwaysOn": False, "healthCheckPath": "/health"}}}
    checks = [f["check"] for f in ar.evaluate_site(row)]
    assert "Always On disabled" not in checks


def test_plan_free_tier_and_zone():
    free = {"name": "p1", "subscriptionId": "a", "sku": {"tier": "Free"}, "properties": {}}
    assert ar.evaluate_plan(free)[0]["severity"] == "Medium"
    std = {"name": "p2", "subscriptionId": "a", "sku": {"tier": "Standard"}, "properties": {"zoneRedundant": False}}
    assert ar.evaluate_plan(std)[0]["check"] == "Plan not zone redundant"


def test_containerapp_checks():
    row = {"name": "c1", "subscriptionId": "a", "properties": {"configuration": {"ingress": {"allowInsecure": True}}, "template": {"scale": {"maxReplicas": 1}, "containers": [{"name": "x"}]}}}
    checks = [f["check"] for f in ar.evaluate_containerapp(row)]
    assert "Insecure ingress allowed" in checks
    assert "No scale out (maxReplicas is 1)" in checks
    assert any("Readiness probe not explicit" in c for c in checks)


def test_build_report_data_categories():
    findings = ar.evaluate_plan({"name": "p1", "subscriptionId": "a", "sku": {"tier": "Free"}, "properties": {}})
    data = ar.build_report_data(findings, 1, 9, [])
    assert data["charts"][1]["items"][0]["name"] == "App Service plan"


def test_partial_site_config_does_not_claim_missing_path():
    findings = ar.evaluate_site({"properties": {"siteConfig": {"minTlsVersion": "1.2"}}})
    assert any(f["check"] == "healthCheckPath not assessed" for f in findings)
    assert not any(f["check"] == "No health check path" for f in findings)


def test_probes_evaluated_per_container_and_type():
    row = {"properties": {"template": {"containers": [
        {"name": "main", "probes": [{"type": kind, "tcpSocket": {"port": 8080}} for kind in ("Startup", "Liveness", "Readiness")]},
        {"name": "sidecar", "probes": [{"type": "Liveness", "httpGet": {"port": 8081}}]},
    ]}}}
    findings = ar.evaluate_containerapp(row)
    checks = [f["check"] for f in findings]
    assert "Container sidecar: Readiness probe not explicit" in checks
    assert "Container sidecar: Startup probe not explicit" in checks
    assert not any("Container main:" in c for c in checks)


def test_missing_probes_are_unknown_not_asserted_absent_effective_probes():
    findings = ar.evaluate_containerapp({"properties": {"template": {"containers": [{"name": "main"}]}}})
    probes = [f for f in findings if "probe not explicit" in f["check"]]
    assert len(probes) == 3
    assert all(f["severity"] == "Unknown" and "portal" in f["recommendation"] and "GPU" in f["recommendation"] for f in probes)


def test_unknown_configuration_sets_partial_report():
    assert ar.build_report_data(ar.evaluate_site({}), 1, 9, [])["assessment_status"] == "Partial"


def test_unsupported_probe_handlers_and_named_ports_not_passing():
    for probe in (
        {"type": "Readiness", "exec": {"command": ["test"]}},
        {"type": "Readiness", "grpc": {"port": 8080}},
        {"type": "Readiness", "httpGet": {"port": "http"}},
    ):
        findings = ar.evaluate_containerapp({"properties": {"template": {"containers": [{"name": "main", "probes": [probe]}]}}})
        assert any("probe configuration not assessed" in f["check"] for f in findings)
        assert any("Readiness probe not explicit" in f["check"] for f in findings)


def test_null_site_fields_are_not_silently_passing():
    findings = ar.evaluate_site({"properties": {"siteConfig": {"minTlsVersion": None, "alwaysOn": None, "healthCheckPath": None}}})
    checks = [f["check"] for f in findings]
    assert "minTlsVersion not assessed" in checks
    assert "alwaysOn not assessed" in checks
    assert "healthCheckPath not assessed" in checks
    assert "No health check path" not in checks


if __name__ == "__main__":
    for name, function in sorted(globals().items()):
        if name.startswith("test_") and callable(function):
            function()
            print(f"ok {name}")
    print("all appservice_review tests passed")

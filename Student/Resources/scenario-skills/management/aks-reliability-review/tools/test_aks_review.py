"""Unit tests for the pure helpers in aks_review (no Azure calls)."""

import aks_review as ar
from datetime import date


TODAY = date(2026, 10, 21)
EVIDENCE = {"schema_version": 1, "checked_at": "2026-10-21", "entries": [
    {"service": "aks", "version": "1.34", "support_plan": "standard", "support_end": "2026-11-01",
     "source": "https://learn.microsoft.com/en-us/azure/aks/supported-kubernetes-versions"},
    {"service": "aks", "version": "1.24", "support_plan": "standard", "support_end": "2024-01-01",
     "source": "https://learn.microsoft.com/en-us/azure/aks/supported-kubernetes-versions"},
]}


def _cluster(**props):
    base = {
        "name": "k1", "subscriptionId": "a", "resourceGroup": "rg1", "sku": {"tier": "Standard"},
        "properties": {
            "kubernetesVersion": "1.34.0", "supportPlan": "KubernetesOfficial",
            "agentPoolProfiles": [{"name": "sys", "mode": "System", "count": 3, "availabilityZones": ["1", "2", "3"]}],
            "apiServerAccessProfile": {"enablePrivateCluster": True},
            "autoUpgradeProfile": {"upgradeChannel": "patch"},
            "addonProfiles": {"omsagent": {"enabled": True}},
            "networkProfile": {"networkPolicy": "azure"},
            "aadProfile": {"managed": True}, "enableRBAC": True,
        },
    }
    base["properties"].update(props)
    return base


def test_healthy_cluster_has_no_findings():
    assert ar.evaluate_cluster(_cluster(), EVIDENCE, TODAY) == []


def test_old_version_flagged_high():
    findings = ar.evaluate_cluster(_cluster(kubernetesVersion="1.24.0"), EVIDENCE, TODAY)
    assert any(f["severity"] == "High" and "outside verified support dates" in f["check"] for f in findings)


def test_open_control_plane_and_no_zones():
    cluster = _cluster(
        apiServerAccessProfile={"enablePrivateCluster": False},
        agentPoolProfiles=[{"name": "np", "mode": "System", "count": 1, "availabilityZones": []}],
    )
    checks = [f["check"] for f in ar.evaluate_cluster(cluster)]
    assert any("Control plane open" in c for c in checks)
    assert any("zone applicability Unknown" in c for c in checks)
    assert any("recommendation of three" in c for c in checks)


def test_free_tier_flagged():
    cluster = _cluster()
    cluster["sku"] = {"tier": "Free"}
    assert any("no uptime SLA" in f["check"] for f in ar.evaluate_cluster(cluster))


def test_build_report_data_counts():
    data = ar.build_report_data([_cluster(kubernetesVersion="1.24.0")], [], EVIDENCE, TODAY)
    assert data["summary_cards"][0]["value"] == "1"
    assert int(data["summary_cards"][2]["value"]) >= 1  # at least one High


def test_current_looking_version_without_evidence_is_unknown():
    findings = ar.evaluate_cluster(_cluster(kubernetesVersion="1.99.0"), {}, TODAY)
    assert any(f["severity"] == "Unknown" and "support Unknown" in f["check"] for f in findings)


def test_two_system_nodes_are_not_production_recommendation():
    cluster = _cluster(agentPoolProfiles=[{"name": "sys", "mode": "System", "count": 2, "availabilityZones": ["1", "2"]}])
    assert any("recommendation of three" in f["check"] for f in ar.evaluate_cluster(cluster))


def test_autoscaler_minimum_used_for_system_pool():
    cluster = _cluster(agentPoolProfiles=[{"name": "sys", "mode": "System", "count": 5, "enableAutoScaling": True, "minCount": 2, "availabilityZones": ["1", "2"]}])
    assert any("recommendation of three" in f["check"] for f in ar.evaluate_cluster(cluster))


def test_cilium_is_a_policy_engine_not_missing_policy():
    findings = ar.evaluate_cluster(_cluster(networkProfile={"networkDataplane": "cilium"}))
    assert not any("No network policy" in f["check"] for f in findings)


def test_region_without_zone_support_not_told_to_recreate_across_zones():
    cluster = _cluster(agentPoolProfiles=[{"name": "sys", "mode": "System", "count": 3}])
    cluster["location"] = "region-without-zones"
    findings = ar.evaluate_cluster(cluster, zone_regions={"region-without-zones": False})
    assert not any("availability zones" in f["check"] for f in findings)


def test_lts_needs_explicit_premium_plan_and_separate_evidence():
    cluster = _cluster(supportPlan="AKSLongTermSupport")
    findings = ar.evaluate_cluster(cluster, EVIDENCE, TODAY)
    assert any("support Unknown" in f["check"] for f in findings)


def test_empty_cluster_result_is_not_assessed():
    assert ar.build_report_data([], [])["assessment_status"] == "Not assessed"


def test_missing_cluster_configuration_is_unknown_not_disabled():
    findings = ar.evaluate_cluster({}, {})
    assert findings and all(f["severity"] == "Unknown" for f in findings)


def test_snapshot_load_error_reason_reaches_cluster_findings():
    evidence = {"_evidence_error": {"code": "SnapshotUnreadable", "reason": "Configured lifecycle snapshot could not be read."}}
    findings = ar.evaluate_cluster(_cluster(), evidence, TODAY)
    assert any(f["severity"] == "Unknown" and "could not be read" in f["recommendation"] for f in findings)


if __name__ == "__main__":
    for name, function in sorted(globals().items()):
        if name.startswith("test_") and callable(function):
            function()
            print(f"ok {name}")
    print("all aks_review tests passed")

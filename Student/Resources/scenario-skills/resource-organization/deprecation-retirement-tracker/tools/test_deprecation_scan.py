"""Unit tests for the pure predicates in deprecation_scan (no Azure calls)."""

import deprecation_scan as ds
from datetime import date


def test_k8s_minor():
    assert ds.k8s_minor("1.26.10") == 26
    assert ds.k8s_minor("bad") is None


def test_eol_runtime():
    assert ds.eol_runtime("PYTHON|3.7", {})[1] == "Unknown"
    assert ds.eol_runtime("NODE|18-lts", {})[1] == "Unknown"
    assert ds.eol_runtime("PYTHON|3.12", {})[1] == "Unknown"


def test_eol_image():
    assert ds.eol_image("WindowsServer", "2012-datacenter", {})[1] == "Unknown"
    assert ds.eol_image("UbuntuServer", "18.04-LTS", {})[1] == "Unknown"
    assert ds.eol_image("0001-com-ubuntu-server-jammy", "22_04-lts", {})[1] == "Unknown"


def test_scanners_produce_findings():
    apps = ds.scan_app_service([{"name": "app1", "subscriptionId": "a", "fx": "PYTHON|3.7"}])
    assert apps[0]["category"] == "App Service runtime"
    retired = ds.scan_retired_types([{"name": "pg1", "type": "microsoft.dbforpostgresql/servers", "subscriptionId": "a"}])
    assert retired[0]["severity"] == "Unknown"
    aks = ds.scan_aks([{"name": "k1", "subscriptionId": "a", "kubernetesVersion": "1.24.0"}])
    assert aks[0]["category"] == "AKS version"


def test_build_report_data_categories():
    findings = ds.scan_app_service([{"name": "app1", "subscriptionId": "a", "fx": "PYTHON|3.7"}])
    data = ds.build_report_data(findings, 1, [])
    assert data["summary_cards"][0]["value"] == "1"
    assert data["charts"][1]["items"][0]["name"] == "App Service runtime"


def _runtime_evidence(version="JAVA|8", end="2027-01-01"):
    return {"schema_version": 1, "checked_at": "2026-10-21", "entries": [{
        "service": "app-service", "version": version, "support_plan": "app-service",
        "support_end": end, "source": "https://learn.microsoft.com/en-us/azure/app-service/language-support-policy",
    }]}


def test_java8_is_not_blanket_eol():
    assert ds.eol_runtime("JAVA|8", _runtime_evidence(), date(2026, 10, 21)) is None
    assert ds.eol_runtime("JAVA|8", {}, date(2026, 10, 21))[1] == "Unknown"


def test_runtime_expiry_requires_verified_date_and_exact_match():
    evidence = _runtime_evidence("NODE|18-lts", "2026-10-20")
    evidence["entries"][0]["version"] = "NODE|18-LTS"
    assert ds.eol_runtime("NODE|18-lts", evidence, date(2026, 10, 21))[1] == "High"
    assert ds.eol_runtime("NODE|180", evidence, date(2026, 10, 21))[1] == "Unknown"


def test_aks_newer_than_old_floor_never_auto_passes():
    finding = ds.scan_aks([{"name": "k", "kubernetesVersion": "1.99.0"}], {})[0]
    assert finding["severity"] == "Unknown"


def test_empty_lifecycle_scope_not_complete():
    assert ds.build_report_data([], 0, [])["assessment_status"] == "Not assessed"


def test_snapshot_load_error_reason_reaches_os_image_findings():
    evidence = {"_evidence_error": {"code": "SnapshotNotFound", "reason": "Configured lifecycle snapshot could not be found."}}
    label, severity = ds.eol_image("WindowsServer", "2012-datacenter", evidence)
    assert severity == "Unknown"
    assert "could not be found" in label


if __name__ == "__main__":
    for name, function in sorted(globals().items()):
        if name.startswith("test_") and callable(function):
            function()
            print(f"ok {name}")
    print("all deprecation_scan tests passed")

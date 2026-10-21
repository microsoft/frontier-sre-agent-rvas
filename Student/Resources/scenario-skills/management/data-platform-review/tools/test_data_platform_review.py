"""Unit tests for the pure evaluate functions in data_platform_review (no Azure calls)."""

import data_platform_review as dp


def test_sql_db_zone_and_backup():
    row = {"name": "db1", "subscriptionId": "a", "sku": {"tier": "BusinessCritical"}, "properties": {"zoneRedundant": False, "requestedBackupStorageRedundancy": "Local"}}
    checks = [f["check"] for f in dp.evaluate_sql_db(row)]
    assert any("without zone redundancy" in c for c in checks)
    assert any("locally redundant" in c for c in checks)


def test_sql_db_healthy():
    row = {"name": "db1", "subscriptionId": "a", "sku": {"tier": "GeneralPurpose"}, "properties": {"requestedBackupStorageRedundancy": "Geo"}}
    assert dp.evaluate_sql_db(row) == []


def test_sql_server_tls_and_public():
    row = {"name": "s1", "subscriptionId": "a", "properties": {"publicNetworkAccess": "Enabled", "minimalTlsVersion": "1.0"}}
    checks = [f["check"] for f in dp.evaluate_sql_server(row)]
    assert any("public network access" in c.lower() for c in checks)
    assert any("TLS below 1.2" in c for c in checks)


def test_flexible_ha_and_geo():
    row = {"name": "pg1", "type": "microsoft.dbforpostgresql/flexibleservers", "subscriptionId": "a",
           "sku": {"tier": "GeneralPurpose"},
           "properties": {"highAvailability": {"mode": "Disabled"}, "backup": {"geoRedundantBackup": "Disabled"}, "storage": {"autoGrow": "Enabled"}}}
    findings = dp.evaluate_flexible(row)
    assert findings[0]["engine"] == "PostgreSQL"
    assert any("High availability disabled" in f["check"] for f in findings)
    assert any("Geo redundant backup disabled" in f["check"] for f in findings)


def test_cosmos_single_region_and_backup():
    row = {"name": "c1", "subscriptionId": "a", "properties": {"locations": [{"id": "r1"}], "backupPolicy": {"type": "Periodic"}}}
    checks = [f["check"] for f in dp.evaluate_cosmos(row)]
    assert any("Single region" in c for c in checks)
    assert any("Periodic backup" in c for c in checks)


def test_build_report_data_by_engine():
    findings = dp.evaluate_cosmos({"name": "c1", "subscriptionId": "a", "properties": {"locations": [{"id": "r1"}]}})
    data = dp.build_report_data(findings, 1, [])
    assert data["charts"][1]["items"][0]["name"] == "Cosmos DB"


def test_absent_database_fields_not_disabled():
    for evaluator, row in [
        (dp.evaluate_flexible, {"type": "microsoft.dbforpostgresql/flexibleservers"}),
        (dp.evaluate_cosmos, {}),
        (dp.evaluate_sql_server, {}),
    ]:
        findings = evaluator(row)
        assert findings
        assert all(f["severity"] == "Unknown" for f in findings)
        assert all("disabled" not in f["check"].lower() for f in findings)


def test_sql_missing_zone_redundancy_is_unknown_not_disabled():
    findings = dp.evaluate_sql_db({"sku": {"tier": "BusinessCritical"}})
    assert all(f["severity"] == "Unknown" for f in findings)


def test_postgres_geo_backup_requires_creation_not_inplace_toggle():
    findings = dp.evaluate_flexible({"type": "microsoft.dbforpostgresql/flexibleservers", "properties": {"backup": {"geoRedundantBackup": "Disabled"}}})
    geo = next(f for f in findings if f["check"] == "Geo redundant backup disabled")
    assert "only at server creation" in geo["recommendation"]


def test_missing_flexible_sku_is_not_ha_applicability_pass():
    findings = dp.evaluate_flexible({"type": "microsoft.dbformysql/flexibleservers", "properties": {"highAvailability": {"mode": "Disabled"}}})
    assert any(f["check"] == "High availability applicability not assessed" for f in findings)


def test_unknown_data_fields_make_report_partial_and_no_measured_rto_claim():
    data = dp.build_report_data(dp.evaluate_cosmos({}), 1, [])
    assert data["assessment_status"] == "Partial"
    assert any("does not measure RTO" in note for note in data["method_notes"])


def test_missing_engine_is_not_assumed_mysql():
    findings = dp.evaluate_flexible({})
    assert findings[0]["engine"] == "Unknown engine"
    assert findings[0]["severity"] == "Unknown"


if __name__ == "__main__":
    for name, function in sorted(globals().items()):
        if name.startswith("test_") and callable(function):
            function()
            print(f"ok {name}")
    print("all data_platform_review tests passed")

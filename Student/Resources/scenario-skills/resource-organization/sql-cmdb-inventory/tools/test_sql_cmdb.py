import sql_cmdb as cmdb


def test_unknown_defender_is_null_and_inventory_rows_are_retained():
    inventory = [{"ResourceId": "/subscriptions/a/providers/Microsoft.Sql/servers/one"},
                 {"ResourceId": "/subscriptions/a/providers/Microsoft.Sql/servers/two"}]
    rows = cmdb.enrich_inventory(inventory, {})
    assert len(rows) == len(inventory)
    assert all(row["DefenderTotal"] is None and row["DefenderAssessmentStatus"] == "Not assessed" for row in rows)


def test_zero_requires_explicit_assessed_coverage_and_complete_counts():
    inventory = [{"ResourceId": "SQL-A"}]
    zero = {field: 0 for field in cmdb.COUNT_FIELDS}
    assert cmdb.enrich_inventory(inventory, {"sql-a": zero})[0]["DefenderTotal"] is None
    row = cmdb.enrich_inventory(inventory, {"sql-a": zero}, ["sql-a"])[0]
    assert row["DefenderTotal"] == 0
    assert row["DefenderAssessmentStatus"] == "Assessed"
    assert cmdb.enrich_inventory(inventory, {"sql-a": {"DefenderTotal": 0}}, ["sql-a"])[0]["DefenderTotal"] is None


def test_database_format_is_not_an_engine_build():
    row = cmdb.enrich_inventory([{"ResourceId": "mi", "ResourceType": "Microsoft.Sql/managedInstances",
                                 "VersionSource": "databaseFormat", "SqlVersion": "SQLServer2022",
                                 "DatabaseFormat": "SQLServer2022"}], {})[0]
    assert row["SqlVersion"] == "Unverified"
    assert row["DatabaseFormat"] == "SQLServer2022"


def test_customer_csv_sanitizes_identifiers_secrets_and_formulas():
    rows = [{"ResourceId": "/subscriptions/11111111-1111-1111-1111-111111111111/providers/Microsoft.Sql/servers/sql-prod",
             "Owner": "owner@example.com", "Note": "=1+1", "password": "test-secret-value"}]
    text = cmdb.export_csv(rows)
    assert "11111111" not in text and "owner@example.com" not in text
    assert "test-secret-value" not in text
    assert "'=1+1" in text

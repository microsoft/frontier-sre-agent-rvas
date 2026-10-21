"""
data_platform_review: Review Azure managed databases for reliability posture.

Azure SRE Agent Python tool. Uses the agent managed identity (ARM scope) to read
the configuration of Azure SQL, PostgreSQL and MySQL Flexible Server, and Cosmos
DB with Azure Resource Graph, evaluate each against the checks in
references/checks-catalog.md, and print a report_data object as JSON ready to
pipe into report_render.py.

    python data_platform_review.py | python report_render.py

Heavy imports (azure-identity, requests) are lazy so the pure evaluate functions
can be unit tested without them.
"""

import json
import sys
from pathlib import Path

for _parent in Path(__file__).resolve().parents:
    _tools = _parent / "shared" / "tools"
    if (_tools / "azure_http.py").is_file():
        sys.path.insert(0, str(_tools))
        break

ARM_ENDPOINT = "https://management.azure.com"
SEVERITY_ORDER = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}


def _finding(row, engine, check, recommendation, severity, name=None):
    return {
        "resource": name or row.get("name", ""),
        "engine": engine,
        "resource_id": row.get("id", ""),
        "subscription": row.get("subscriptionId", ""),
        "resource_group": row.get("resourceGroup", ""),
        "check": check,
        "recommendation": recommendation,
        "severity": severity,
        "_band": severity,
    }


def evaluate_sql_db(row):
    props = row.get("properties", {}) or {}
    sku = row.get("sku", {}) or {}
    tier = (sku.get("tier") or "").lower()
    findings = []
    if not tier or (tier in ("premium", "businesscritical") and props.get("zoneRedundant") is None):
        findings.append(_finding(row, "SQL", "Zone redundancy not assessed", "Read SKU tier and the explicit zoneRedundant setting; validate regional tier support.", "Unknown"))
    elif tier in ("premium", "businesscritical") and props.get("zoneRedundant") is False:
        findings.append(_finding(row, "SQL", "Premium or Business Critical database without zone redundancy", "Enable zoneRedundant on the database.", "High"))
    if (props.get("requestedBackupStorageRedundancy") or "").lower() == "local":
        findings.append(_finding(row, "SQL", "Backups are locally redundant only", "Set backup storage redundancy to Geo or Zone where the data warrants it.", "Medium"))
    elif not props.get("requestedBackupStorageRedundancy"):
        findings.append(_finding(row, "SQL", "Backup redundancy not assessed", "Read current and requested backup storage redundancy from the SQL API.", "Unknown"))
    return findings


def evaluate_sql_server(row):
    props = row.get("properties", {}) or {}
    findings = []
    if (props.get("publicNetworkAccess") or "").lower() == "enabled":
        findings.append(_finding(row, "SQL", "SQL server public network access enabled", "Use Private Link or firewall rules and disable public access.", "Low"))
    elif props.get("publicNetworkAccess") is None:
        findings.append(_finding(row, "SQL", "Public network access not assessed", "Read publicNetworkAccess and firewall or private endpoint rules.", "Unknown"))
    tls = (props.get("minimalTlsVersion") or "").strip()
    if not tls:
        findings.append(_finding(row, "SQL", "Minimum TLS not assessed", "Read minimalTlsVersion from the server API.", "Unknown"))
    elif tls in ("1.0", "1.1"):
        findings.append(_finding(row, "SQL", "SQL server minimum TLS below 1.2", "Set the minimum TLS version to 1.2.", "Medium"))
    return findings


def evaluate_flexible(row):
    rtype = (row.get("type") or "").lower()
    if rtype not in ("microsoft.dbforpostgresql/flexibleservers", "microsoft.dbformysql/flexibleservers"):
        return [_finding(row, "Unknown engine", "Database engine not assessed", "Read the exact resource type before applying engine specific checks.", "Unknown")]
    engine = "PostgreSQL" if "postgresql" in rtype else "MySQL"
    props = row.get("properties", {}) or {}
    findings = []
    tier = (row.get("sku") or {}).get("tier")
    mode = (props.get("highAvailability") or {}).get("mode")
    geo = (props.get("backup") or {}).get("geoRedundantBackup")
    grow = (props.get("storage") or {}).get("autoGrow")
    if mode is None or not tier:
        findings.append(_finding(row, engine, "High availability applicability not assessed", "Read highAvailability.mode, SKU tier and region support. Burstable tiers cannot be assumed eligible.", "Unknown"))
    elif str(mode).lower() == "disabled":
        findings.append(_finding(row, engine, "High availability disabled", "For production, review workload requirements and eligible compute tier, region and zone capacity before enabling HA.", "Medium"))
    if geo is None:
        findings.append(_finding(row, engine, "Geo redundant backup not assessed", "Read backup.geoRedundantBackup and verify regional support.", "Unknown"))
    elif str(geo).lower() == "disabled":
        advice = ("PostgreSQL geo redundant backup can be configured only at server creation. Plan a new server and tested migration or restore path if regional recovery is required."
                  if engine == "PostgreSQL" else
                  "Verify current MySQL geo backup eligibility and change constraints before planning regional recovery.")
        findings.append(_finding(row, engine, "Geo redundant backup disabled", advice, "Medium"))
    if grow is None:
        findings.append(_finding(row, engine, "Storage auto grow not assessed", "Read the engine specific storage.autoGrow field and storage tier limits.", "Unknown"))
    elif str(grow).lower() == "disabled":
        findings.append(_finding(row, engine, "Storage auto grow disabled", "Enable auto grow to avoid a storage full outage.", "Low"))
    if ((props.get("network", {}) or {}).get("publicNetworkAccess") or "").lower() == "enabled":
        findings.append(_finding(row, engine, "Public network access enabled", "Use private access (VNet integration) and disable public access.", "Low"))
    elif (props.get("network") or {}).get("publicNetworkAccess") is None:
        findings.append(_finding(row, engine, "Public network access not assessed", "Read network.publicNetworkAccess and the engine specific network mode.", "Unknown"))
    return findings


def evaluate_cosmos(row):
    props = row.get("properties", {}) or {}
    locations = props.get("locations")
    findings = []
    if not locations:
        findings.append(_finding(row, "Cosmos DB", "Region configuration not assessed", "Read account locations from the service API.", "Unknown"))
    elif len(locations) < 2:
        findings.append(_finding(row, "Cosmos DB", "Single region account", "Add a second region.", "Medium"))
    elif props.get("enableAutomaticFailover") is None:
        findings.append(_finding(row, "Cosmos DB", "Automatic failover not assessed", "Read enableAutomaticFailover and write region mode.", "Unknown"))
    elif props.get("enableAutomaticFailover") is False:
        findings.append(_finding(row, "Cosmos DB", "Automatic failover disabled on a multi region account", "Enable automatic failover so a regional loss fails over without manual action.", "Medium"))
    if ((props.get("backupPolicy", {}) or {}).get("type") or "").lower() == "periodic":
        findings.append(_finding(row, "Cosmos DB", "Periodic backup mode", "Consider continuous backup for critical accounts, for point in time restore.", "Low"))
    elif not (props.get("backupPolicy") or {}).get("type"):
        findings.append(_finding(row, "Cosmos DB", "Backup policy not assessed", "Read backupPolicy from the account API.", "Unknown"))
    return findings


def build_report_data(findings, subs_scanned, notes):
    findings = sorted(findings, key=lambda f: SEVERITY_ORDER.get(f["severity"], 9))
    with_findings = len({f["resource"] for f in findings})
    high = sum(1 for f in findings if f["severity"] in ("Critical", "High"))
    sev_counts, by_engine = {}, {}
    for finding in findings:
        sev_counts[finding["severity"]] = sev_counts.get(finding["severity"], 0) + 1
        by_engine[finding["engine"]] = by_engine.get(finding["engine"], 0) + 1
    sev_items = [{"name": b, "value": sev_counts[b], "band": b} for b in ("Critical", "High", "Medium", "Low") if b in sev_counts]
    engine_items = sorted(({"name": k, "value": v} for k, v in by_engine.items()), key=lambda i: i["value"], reverse=True)
    return {
        "assessment_status": "Not assessed" if not subs_scanned else "Partial" if notes or any(f["severity"] == "Unknown" for f in findings) else "Complete",
        "sources": [
            {"title": "PostgreSQL backup and restore", "url": "https://learn.microsoft.com/en-us/azure/postgresql/backup-restore/concepts-backup-restore"},
            {"title": "MySQL high availability", "url": "https://learn.microsoft.com/en-us/azure/mysql/flexible-server/concepts-high-availability"},
            {"title": "SQL zone redundancy", "url": "https://learn.microsoft.com/en-us/azure/azure-sql/database/high-availability-sla-local-zone-redundancy"},
        ],
        "title": "Data Platform Review",
        "subtitle": "Managed database reliability and resilience.",
        "meta": {"window": "Point in time", "scope": f"{subs_scanned} subscription(s)", "source": "Azure Resource Graph"},
        "summary_cards": [
            {"label": "Services with findings", "value": f"{with_findings:,}"},
            {"label": "High findings", "value": f"{high:,}"},
            {"label": "Total findings", "value": f"{len(findings):,}"},
            {"label": "Subscriptions scanned", "value": str(subs_scanned)},
        ],
        "charts": [
            {"title": "Findings by severity", "unit": "findings", "items": sev_items},
            {"title": "Findings by engine", "unit": "findings", "items": engine_items},
        ],
        "findings": {
            "title": "Data platform findings",
            "columns": ["resource", "engine", "subscription", "resource_group", "check", "recommendation", "severity"],
            "rows": findings,
        },
        "method_notes": notes + [
            "Some overlap with the reliability-posture-review skill is intentional; this is the data tier deep dive.",
            "Azure SQL long term retention is not in Resource Graph and is checked by hand where longer retention is required.",
            "Absent fields are not assessed, not Disabled. SKU, engine, region and API version determine applicability.",
            "Configuration does not measure RTO or RPO. Obtain workload objectives and restore or failover test evidence separately.",
        ],
    }


def _headers():
    from agent_identity import agent_token

    token = agent_token(f"{ARM_ENDPOINT}/.default")
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _run_graph(headers, query):
    import azure_http as requests

    url = f"{ARM_ENDPOINT}/providers/Microsoft.ResourceGraph/resources?api-version=2022-10-01"
    rows, skip_token = [], None
    while True:
        payload = {"query": query, "options": {"resultFormat": "objectArray", "top": 1000}}
        if skip_token:
            payload["options"]["$skipToken"] = skip_token
        response = requests.post(url, headers=headers, json=payload, timeout=120)
        response.raise_for_status()
        body = response.json()
        rows.extend(body.get("data", []))
        skip_token = body.get("$skipToken")
        if not skip_token:
            return rows


def main() -> dict:
    headers = _headers()
    notes, findings, scanned = [], [], set()
    queries = [
        ("resources | where type =~ 'microsoft.sql/servers/databases' | where name != 'master' | project name, id, subscriptionId, resourceGroup, sku, properties", evaluate_sql_db),
        ("resources | where type =~ 'microsoft.sql/servers' | project name, id, subscriptionId, resourceGroup, properties", evaluate_sql_server),
        ("resources | where type in~ ('microsoft.dbforpostgresql/flexibleservers','microsoft.dbformysql/flexibleservers') | project name, id, type, subscriptionId, resourceGroup, location, sku, properties", evaluate_flexible),
        ("resources | where type =~ 'microsoft.documentdb/databaseaccounts' | project name, id, subscriptionId, resourceGroup, properties", evaluate_cosmos),
    ]
    for query, evaluator in queries:
        try:
            rows = _run_graph(headers, query)
        except Exception as error:  # noqa: BLE001
            notes.append(f"A data platform query could not be read ({error}).")
            continue
        for row in rows:
            scanned.add(row.get("subscriptionId"))
            findings.extend(evaluator(row))
    return build_report_data(findings, len({s for s in scanned if s}), notes)


if __name__ == "__main__":
    print(json.dumps(main()))

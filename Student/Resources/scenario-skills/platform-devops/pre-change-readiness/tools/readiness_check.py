"""
readiness_check: Go or no-go readiness for a target scope before a change.

Azure SRE Agent Python tool. Uses the agent managed identity (ARM scope) to run
reliability, internet exposure, and capacity checks scoped to one subscription
(and optional resource group), turn the severities into a verdict per category,
and print a report_data object as JSON ready to pipe into report_render.py.

    python readiness_check.py "<subscription id>" [resource group] | python report_render.py

Heavy imports (azure-identity, requests) are lazy so the pure verdict and
classification helpers can be unit tested without them. See references/checks-catalog.md.
"""

import json
import sys
import math
from pathlib import Path

for _parent in Path(__file__).resolve().parents:
    _tools = _parent / "shared" / "tools"
    if (_tools / "azure_http.py").is_file():
        sys.path.insert(0, str(_tools))
        break

ARM_ENDPOINT = "https://management.azure.com"
SEVERITY_ORDER = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
INTERNET_SOURCES = {"*", "internet", "0.0.0.0/0"}
MGMT_PORTS = {22, 3389, 5985, 5986}
DB_PORTS = {1433, 3306, 5432, 6379, 27017, 1521}
CATEGORIES = ["Reliability", "Exposure", "Capacity"]


def verdict_for(severities):
    """Go, caution, or no-go from a list of severities. Pure and testable."""
    if any(s in ("Critical", "High") for s in severities):
        return "NO-GO"
    if any(s == "Medium" for s in severities):
        return "CAUTION"
    return "GO"


def verdicts(findings, assessments=None):
    """Return {overall, Reliability, Exposure, Capacity}. Pure and testable."""
    out = {}
    for category in CATEGORIES:
        result = verdict_for([f["severity"] for f in findings if f["category"] == category])
        checks = [a for a in (assessments or []) if a["category"] == category]
        complete = bool(checks) and all(a["state"] == "Complete" for a in checks)
        out[category] = "INCOMPLETE" if not complete and result != "NO-GO" else result
    order = {"NO-GO": 0, "INCOMPLETE": 1, "CAUTION": 2, "GO": 3}
    out["overall"] = min((out[c] for c in CATEGORIES), key=lambda v: order[v])
    return out


def source_is_internet(source, sources):
    values = [source] + list(sources or [])
    return any((value or "").strip().lower() in INTERNET_SOURCES for value in values)


def port_in_spec(port, spec):
    spec = (spec or "").strip()
    if spec == "*":
        return True
    if "-" in spec:
        try:
            low, high = spec.split("-", 1)
            return int(low) <= port <= int(high)
        except ValueError:
            return False
    return spec.isdigit() and int(spec) == port


def classify_ports(specs):
    specs = [s for s in specs if s]
    if any(s.strip() in ("*", "0-65535") for s in specs):
        return "Critical", "all ports open to the internet"
    if any(any(port_in_spec(p, s) for s in specs) for p in MGMT_PORTS):
        return "Critical", "management ports open to the internet"
    if any(any(port_in_spec(p, s) for s in specs) for p in DB_PORTS):
        return "High", "database ports open to the internet"
    return "Medium", "ports open to the internet"


def _finding(category, row, issue, recommendation, severity):
    return {
        "category": category, "resource": row.get("name", ""), "resource_id": row.get("id", ""),
        "subscription": row.get("subscriptionId", ""), "resource_group": row.get("resourceGroup", ""),
        "issue": issue, "recommendation": recommendation, "severity": severity, "_band": severity,
    }


def build_report_data(findings, scope_label, notes, assessments=None):
    verdict = verdicts(findings, assessments)
    assessments = assessments or []
    complete = sum(a["state"] == "Complete" for a in assessments)
    categories_present = all(any(a["category"] == c for a in assessments) for c in CATEGORIES)
    findings = sorted(findings, key=lambda f: SEVERITY_ORDER.get(f["severity"], 9))
    by_cat, sev_counts = {}, {}
    for finding in findings:
        by_cat[finding["category"]] = by_cat.get(finding["category"], 0) + 1
        sev_counts[finding["severity"]] = sev_counts.get(finding["severity"], 0) + 1
    cat_items = [{"name": c, "value": by_cat.get(c, 0)} for c in CATEGORIES]
    sev_items = [{"name": b, "value": sev_counts[b], "band": b} for b in ("Critical", "High", "Medium", "Low") if b in sev_counts]
    return {
        "assessment_status": ("Complete" if complete == len(assessments) and complete and categories_present else
                              "Partial" if complete else "Not assessed"),
        "assessments": assessments,
        "sources": [{"title": "Azure usage and quotas", "url": "https://learn.microsoft.com/en-us/azure/quotas/view-quotas"}],
        "title": "Pre-Change Readiness",
        "subtitle": f"Go / no-go for {scope_label}.",
        "meta": {"window": "Point in time", "scope": scope_label, "source": "Azure Resource Graph and usage"},
        "summary_cards": [
            {"label": "Overall", "value": verdict["overall"], "sub": f"{len(findings)} finding(s)"},
            {"label": "Reliability", "value": verdict["Reliability"], "sub": f"{by_cat.get('Reliability', 0)} finding(s)"},
            {"label": "Exposure", "value": verdict["Exposure"], "sub": f"{by_cat.get('Exposure', 0)} finding(s)"},
            {"label": "Capacity", "value": verdict["Capacity"], "sub": f"{by_cat.get('Capacity', 0)} finding(s)"},
        ],
        "charts": [
            {"title": "Findings by category", "unit": "findings", "items": cat_items},
            {"title": "Findings by severity", "unit": "findings", "items": sev_items},
        ],
        "findings": {
            "title": "What to clear before shipping",
            "columns": ["category", "resource", "resource_group", "issue", "recommendation", "severity"],
            "rows": findings,
        },
        "method_notes": notes + [
            "NO-GO for Critical or High. INCOMPLETE blocks GO if any required read is missing, failed, or scope cannot be confirmed. CAUTION for Medium after complete reads.",
            "Capacity counters cover compute and network in observed regions only, not SKU allocation guarantees or all service quotas.",
            "Configuration checks do not validate workload failover, effective network reachability, change correctness, or measured recovery objectives.",
            f"Scope checked: {scope_label}.",
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


def _get(headers, url):
    import azure_http as requests

    response = requests.get(url, headers=headers, timeout=90)
    response.raise_for_status()
    return response.json().get("value", [])


def main(subscription: str, resource_group: str = None) -> dict:
    headers = _headers()
    notes, assessments = [], []
    scope = f"subscriptionId == '{subscription}'"
    if resource_group:
        scope += f" and resourceGroup =~ '{resource_group}'"
    label = subscription + (f" / {resource_group}" if resource_group else "")
    findings = []

    try:
        inventory = _run_graph(headers, f"resources | where {scope} | project id")
        scope_confirmed = bool(inventory)
    except Exception:
        scope_confirmed = False
    if not scope_confirmed:
        notes.append("Target scope is empty or unreadable. Visibility and scope approval must be confirmed before any GO.")

    def scan(category, check, query, handler):
        state = "Not assessed"
        try:
            for row in _run_graph(headers, query):
                handler(row)
            state = "Complete" if scope_confirmed else "Not assessed"
        except Exception:  # noqa: BLE001
            notes.append(f"{category} readiness query could not be read.")
        assessments.append({"check": check, "category": category, "state": state})

    # Reliability
    scan("Reliability", "VM placement", f"resources | where {scope} | where type =~ 'microsoft.compute/virtualmachines' | where (isnull(zones) or array_length(zones)==0) and isnull(properties.availabilitySet) | project name, id, subscriptionId, resourceGroup",
         lambda r: findings.append(_finding("Reliability", r, "No availability zone or availability set", "Deploy across zones or an availability set.", "High")))
    scan("Reliability", "Storage replication", f"resources | where {scope} | where type =~ 'microsoft.storage/storageaccounts' | where tostring(sku.name) endswith 'LRS' | project name, id, subscriptionId, resourceGroup",
         lambda r: findings.append(_finding("Reliability", r, "Locally redundant storage", "Use ZRS or GRS where the data warrants it.", "Medium")))
    scan("Reliability", "SQL zone redundancy", f"resources | where {scope} | where type =~ 'microsoft.sql/servers/databases' | where tostring(sku.tier) in~ ('Premium','BusinessCritical') and tostring(properties.zoneRedundant) =~ 'false' | project name, id, subscriptionId, resourceGroup",
         lambda r: findings.append(_finding("Reliability", r, "Premium database without zone redundancy", "Enable zoneRedundant on the database.", "High")))

    # Exposure
    def nsg_handler(row):
        if not source_is_internet(row.get("src"), row.get("srcs")):
            return
        specs = [row.get("portRange")] + list(row.get("portRanges") or [])
        specs = [s for s in specs if s]
        if not specs:
            return
        severity, label_txt = classify_ports(specs)
        findings.append(_finding("Exposure", row, f"{row.get('ruleName', '')}: {label_txt}", "Restrict the source or use Private Link.", severity))

    scan("Exposure", "NSG inbound rules", f"resources | where {scope} | where type =~ 'microsoft.network/networksecuritygroups' | mv-expand rule = properties.securityRules | extend p = rule.properties | where tostring(p.direction) =~ 'Inbound' and tostring(p.access) =~ 'Allow' | project name, id, resourceGroup, subscriptionId, ruleName=tostring(rule.name), src=tostring(p.sourceAddressPrefix), srcs=p.sourceAddressPrefixes, portRange=tostring(p.destinationPortRange), portRanges=p.destinationPortRanges",
         nsg_handler)
    scan("Exposure", "Storage public blobs", f"resources | where {scope} | where type =~ 'microsoft.storage/storageaccounts' | where tostring(properties.allowBlobPublicAccess) =~ 'true' | project name, id, subscriptionId, resourceGroup",
         lambda r: findings.append(_finding("Exposure", r, "Anonymous blob public access allowed", "Set allowBlobPublicAccess to false.", "High")))
    scan("Exposure", "PaaS public access", f"resources | where {scope} | where type in~ ('microsoft.sql/servers','microsoft.keyvault/vaults','microsoft.documentdb/databaseaccounts','microsoft.dbforpostgresql/flexibleservers','microsoft.dbformysql/flexibleservers') | where tostring(properties.publicNetworkAccess) =~ 'Enabled' | project name, id, subscriptionId, resourceGroup",
         lambda r: findings.append(_finding("Exposure", r, "Public network access enabled", "Use Private Link or restrict to known networks.", "Medium")))

    # Capacity: usage counters in the regions the scope uses
    try:
        locations = {r.get("location") for r in _run_graph(headers, f"resources | where {scope} | where isnotempty(location) | distinct location") if r.get("location") and r.get("location").lower() != "global"}
    except Exception:  # noqa: BLE001
        notes.append("Capacity location discovery failed.")
        locations = set()
    if not locations:
        assessments.append({"check": "Capacity location discovery", "category": "Capacity", "state": "Not assessed"})
        notes.append("No applicable capacity regions confirmed. Capacity is not assessed.")
    for location in locations:
        for provider, api in (("Microsoft.Compute", "2023-07-01"), ("Microsoft.Network", "2023-09-01")):
            state = "Not assessed"
            try:
                items = _get(headers, f"{ARM_ENDPOINT}/subscriptions/{subscription}/providers/{provider}/locations/{location}/usages?api-version={api}")
                valid = 0
                for item in items:
                    limit = float(item["limit"])
                    current = float(item["currentValue"])
                    if limit <= 0 or current < 0 or not math.isfinite(limit) or not math.isfinite(current):
                        continue
                    valid += 1
                    pct = current / limit * 100.0
                    if pct < 80:
                        continue
                    severity = "Critical" if pct >= 95 else ("High" if pct >= 90 else "Medium")
                    name = (item.get("name", {}) or {}).get("localizedValue") or (item.get("name", {}) or {}).get("value", "quota")
                    findings.append({
                        "category": "Capacity", "resource": f"{name} ({location})", "resource_id": "",
                        "subscription": subscription, "resource_group": resource_group or "",
                        "issue": f"{name} at {pct:.0f}% of quota", "recommendation": "Request a quota increase before the change.",
                        "severity": severity, "_band": severity,
                    })
                if valid == len(items) and valid and scope_confirmed:
                    state = "Complete"
                else:
                    notes.append(f"No finite capacity counters assessed for {provider} in {location}.")
            except Exception:  # noqa: BLE001
                notes.append(f"Capacity counters could not be read for {provider} in {location}.")
            assessments.append({"check": f"{provider} {location}", "category": "Capacity", "state": state})

    return build_report_data(findings, label, notes, assessments)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Pass the target subscription id as the first argument, and optionally a resource group."}))
        raise SystemExit(1)
    rg = sys.argv[2] if len(sys.argv) > 2 else None
    print(json.dumps(main(sys.argv[1], rg)))

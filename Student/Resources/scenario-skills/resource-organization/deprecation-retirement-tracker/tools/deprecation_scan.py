"""
deprecation_scan: Find retiring and end of life Azure elements with Resource Graph.

Azure SRE Agent Python tool. Uses the agent managed identity (ARM scope) to query
Azure Resource Graph for end of life App Service runtimes, retired database single
servers, classic resources, old Kubernetes versions, and end of life operating
system images, assigns a category and severity, and prints a report_data object
as JSON ready to pipe into report_render.py.

    python deprecation_scan.py | python report_render.py

Heavy imports (azure-identity, requests) are lazy so the pure predicates can be
unit tested without them. Retirement dates move; corroborate specifics against
Azure Service Health. See references/checks-catalog.md.
"""

import json
import sys
from pathlib import Path

for _parent in Path(__file__).resolve().parents:
    _tools = _parent / "shared" / "tools"
    if (_tools / "azure_http.py").is_file():
        sys.path.insert(0, str(_tools))
        break
from lifecycle import aks_support_plan, lifecycle_status

ARM_ENDPOINT = "https://management.azure.com"
SEVERITY_ORDER = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}

def k8s_minor(version):
    """Return the minor version integer from a Kubernetes version, or None. Pure."""
    parts = (version or "").split(".")
    if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
        return int(parts[1])
    return None


def eol_runtime(linux_fx_version, evidence=None, today=None, support_plan="app-service"):
    """Exact runtime metadata decides status, not a permanent prefix list."""
    value = (linux_fx_version or "").upper()
    status = lifecycle_status("app-service", value, support_plan, evidence, today)
    if status["status"] == "Supported":
        return None
    return f"{value or 'Runtime'}: {status['status']}. {status['reason']}", "High" if status["status"] == "Unsupported" else "Unknown"


def eol_image(offer, sku, evidence=None, today=None, support_plan=None):
    status = lifecycle_status("vm-os", f"{offer}:{sku}".lower(), support_plan, evidence, today)
    if status["status"] == "Supported":
        return None
    return f"{offer}:{sku}: {status['status']}. {status['reason']} Verify OS edition, image, ESU or extended support entitlement.", "High" if status["status"] == "Unsupported" else "Unknown"


def _finding(row, category, deprecated, recommendation, severity, resource_type):
    return {
        "resource": row.get("name", ""),
        "resource_type": resource_type,
        "category": category,
        "resource_id": row.get("id", ""),
        "subscription": row.get("subscriptionId", ""),
        "resource_group": row.get("resourceGroup", ""),
        "deprecated": deprecated,
        "recommendation": recommendation,
        "severity": severity,
        "_band": severity,
    }


def scan_app_service(rows, evidence=None, today=None):
    findings = []
    for row in rows:
        match = eol_runtime(row.get("fx"), evidence, today)
        if match:
            label, severity = match
            findings.append(_finding(row, "App Service runtime", label, "Verify the exact stack and current provider lifecycle; plan migration only against verified dates.", severity, "App Service"))
    return findings


def scan_retired_types(rows, evidence=None, today=None):
    findings = []
    for row in rows:
        rtype = (row.get("type") or "").lower()
        status = lifecycle_status("azure-service", rtype, "service", evidence, today)
        if status["status"] == "Supported":
            continue
        severity = "High" if status["status"] == "Unsupported" else "Unknown"
        if rtype.startswith("microsoft.classic"):
            findings.append(_finding(row, "Classic", f"Classic resource retirement: {status['status']}", status["reason"] + " Verify the service specific retirement and migration path to Resource Manager.", severity, row.get("type", "Classic")))
        elif rtype in ("microsoft.dbforpostgresql/servers", "microsoft.dbformysql/servers"):
            engine = "PostgreSQL" if "postgres" in rtype else "MySQL"
            findings.append(_finding(row, "Legacy service", f"{engine} Single Server lifecycle: {status['status']}", status["reason"] + " Verify current service retirement metadata and migration to Flexible Server.", severity, f"{engine} Single Server"))
    return findings


def scan_aks(rows, evidence=None, today=None):
    findings = []
    for row in rows:
        version = row.get("kubernetesVersion") or (row.get("properties") or {}).get("currentKubernetesVersion") or (row.get("properties") or {}).get("kubernetesVersion")
        minor_version = ".".join(str(version or "").split(".")[:2])
        status = lifecycle_status("aks", minor_version, aks_support_plan(row.get("properties") or row, row.get("sku") or {}), evidence, today)
        if status["status"] != "Supported":
            severity = "High" if status["status"] == "Unsupported" else "Unknown"
            findings.append(_finding(row, "AKS version", f"Kubernetes {version}: {status['status']}", status["reason"] + " Verify regional version availability and support plan before upgrade.", severity, "AKS cluster"))
    return findings


def scan_vm_os(rows):
    findings = []
    for row in rows:
        match = eol_image(row.get("offer"), row.get("sku"), support_plan=row.get("support_plan"))
        if match:
            label, severity = match
            findings.append(_finding(row, "VM OS", f"{label} image", "Rebuild on a supported image, or move to a managed platform.", severity, "Virtual machine"))
    return findings


def build_report_data(findings, subs_scanned, notes):
    findings = sorted(findings, key=lambda f: SEVERITY_ORDER.get(f["severity"], 9))
    high = sum(1 for f in findings if f["severity"] in ("Critical", "High"))
    categories = {}
    sev_counts = {}
    for finding in findings:
        categories[finding["category"]] = categories.get(finding["category"], 0) + 1
        sev_counts[finding["severity"]] = sev_counts.get(finding["severity"], 0) + 1
    sev_items = [{"name": b, "value": sev_counts[b], "band": b} for b in ("Critical", "High", "Medium", "Low") if b in sev_counts]
    cat_items = sorted(({"name": k, "value": v} for k, v in categories.items()), key=lambda i: i["value"], reverse=True)
    return {
        "assessment_status": "Not assessed" if not subs_scanned else "Partial" if notes or any(f["severity"] == "Unknown" for f in findings) else "Complete",
        "sources": [
            {"title": "AKS lifecycle", "url": "https://learn.microsoft.com/en-us/azure/aks/supported-kubernetes-versions"},
            {"title": "App Service language support", "url": "https://learn.microsoft.com/en-us/azure/app-service/language-support-policy"},
        ],
        "title": "Deprecation and Retirement Tracker",
        "subtitle": "End of life runtimes, retired tiers, and old platform versions.",
        "meta": {"window": "Point in time", "scope": f"{subs_scanned} subscription(s)", "source": "Azure Resource Graph"},
        "summary_cards": [
            {"label": "Lifecycle review items", "value": f"{len(findings):,}"},
            {"label": "Retired or end of life", "value": f"{high:,}", "sub": "plan these first"},
            {"label": "Categories affected", "value": str(len(categories))},
            {"label": "Subscriptions scanned", "value": str(subs_scanned)},
        ],
        "charts": [
            {"title": "Findings by severity", "unit": "items", "items": sev_items},
            {"title": "Findings by category", "unit": "items", "items": cat_items},
        ],
        "findings": {
            "title": "Deprecations and retirements",
            "columns": ["resource", "resource_type", "category", "subscription", "deprecated", "recommendation", "severity"],
            "rows": findings,
        },
        "method_notes": notes + [
            "Dynamic lifecycle status requires a schema v1 snapshot checked within 30 days. Missing or unmatched metadata is Unknown, never a false pass.",
            "Java 8 is not blanket end of life on App Service. Exact stack, distribution and service policy must be checked.",
            "Retirement dates move. Corroborate the specifics against Azure Service Health planned retirements.",
            "Deprecated API versions and Basic tier retirements are covered elsewhere; see the checks catalog.",
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
    notes = []
    findings = []
    scanned = set()
    queries = [
        ("resources | where type =~ 'microsoft.web/sites' | extend fx = tostring(properties.siteConfig.linuxFxVersion) | project name, id, subscriptionId, resourceGroup, fx", scan_app_service),
        ("resources | where type startswith 'microsoft.classic' or type in~ ('microsoft.dbforpostgresql/servers','microsoft.dbformysql/servers') | project name, id, type, subscriptionId, resourceGroup", scan_retired_types),
        ("resources | where type =~ 'microsoft.containerservice/managedclusters' | project name, id, subscriptionId, resourceGroup, sku, properties, kubernetesVersion=tostring(properties.currentKubernetesVersion)", scan_aks),
        ("resources | where type =~ 'microsoft.compute/virtualmachines' | extend img = properties.storageProfile.imageReference | project name, id, subscriptionId, resourceGroup, offer=tostring(img.offer), sku=tostring(img.sku), publisher=tostring(img.publisher)", scan_vm_os),
    ]
    for query, scanner in queries:
        try:
            rows = _run_graph(headers, query)
        except Exception as error:  # noqa: BLE001
            notes.append(f"A deprecation query could not be read ({error}).")
            continue
        for row in rows:
            scanned.add(row.get("subscriptionId"))
        findings.extend(scanner(rows))
    return build_report_data(findings, len({s for s in scanned if s}), notes)


if __name__ == "__main__":
    print(json.dumps(main()))

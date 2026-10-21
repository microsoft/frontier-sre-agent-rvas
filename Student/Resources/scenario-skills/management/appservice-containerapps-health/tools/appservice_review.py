"""
appservice_review: Review App Service and Container Apps for web tier health.

Azure SRE Agent Python tool. Uses the agent managed identity (ARM scope) to read
App Service sites and plans and Container Apps with Azure Resource Graph,
evaluate each against the checks in references/checks-catalog.md, and print a
report_data object as JSON ready to pipe into report_render.py.

    python appservice_review.py | python report_render.py

Heavy imports (azure-identity, requests) are lazy so the pure evaluate functions
can be unit tested without them. A check is skipped when its field is absent, to
avoid false positives.
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
CHECK_DEFINITIONS = 11


def _finding(row, category, check, recommendation, severity):
    return {
        "resource": row.get("name", ""),
        "category": category,
        "resource_id": row.get("id", ""),
        "subscription": row.get("subscriptionId", ""),
        "resource_group": row.get("resourceGroup", ""),
        "check": check,
        "recommendation": recommendation,
        "severity": severity,
        "_band": severity,
    }


def _tls_below_12(value):
    return str(value) in ("1.0", "1.1")


def evaluate_site(row):
    props = row.get("properties", {}) or {}
    kind = (row.get("kind") or "").lower()
    site_config = props.get("siteConfig") or {}
    findings = []
    if props.get("httpsOnly") is False:
        findings.append(_finding(row, "App Service", "HTTPS not enforced", "Set HTTPS Only so HTTP is redirected.", "Medium"))
    if site_config.get("minTlsVersion") and _tls_below_12(site_config.get("minTlsVersion")):
        findings.append(_finding(row, "App Service", "Minimum TLS below 1.2", "Set the minimum TLS version to 1.2.", "Medium"))
    for field in ("minTlsVersion", "alwaysOn", "healthCheckPath"):
        if field == "alwaysOn" and "functionapp" in kind:
            continue
        if field not in site_config or site_config[field] is None or (field == "minTlsVersion" and not site_config[field]):
            findings.append(_finding(row, "App Service", f"{field} not assessed", "Read the sites/config web endpoint and validate plan applicability; Resource Graph can omit siteConfig.", "Unknown"))
    if props.get("httpsOnly") is None:
        findings.append(_finding(row, "App Service", "HTTPS enforcement not assessed", "Read httpsOnly from the site API.", "Unknown"))
    if site_config:
        if "functionapp" not in kind and site_config.get("alwaysOn") is False:
            findings.append(_finding(row, "App Service", "Always On disabled", "Verify plan support before enabling Always On for a warm app.", "Low"))
        if site_config.get("healthCheckPath") == "":
            findings.append(_finding(row, "App Service", "No health check path", "Set a health check path so unhealthy instances are removed.", "Low"))
    return findings


def evaluate_plan(row):
    props = row.get("properties", {}) or {}
    sku = row.get("sku", {}) or {}
    tier = (sku.get("tier") or "").lower()
    findings = []
    if tier in ("free", "shared"):
        findings.append(_finding(row, "App Service plan", "Free or Shared tier has no SLA and no scale out", "Move production workloads to Standard or higher.", "Medium"))
    elif props.get("zoneRedundant") is False:
        findings.append(_finding(row, "App Service plan", "Plan not zone redundant", "Verify a supported Premium plan, regional support and capacity before changing zone redundancy.", "Low"))
    elif not tier or props.get("zoneRedundant") is None:
        findings.append(_finding(row, "App Service plan", "Plan zone redundancy not assessed", "Read plan SKU and zoneRedundant; validate region and tier support.", "Unknown"))
    return findings


def evaluate_containerapp(row):
    props = row.get("properties", {}) or {}
    config = props.get("configuration", {}) or {}
    template = props.get("template", {}) or {}
    ingress = config.get("ingress") or {}
    scale = template.get("scale") or {}
    containers = template.get("containers") or []
    findings = []
    if props.get("configuration") is None:
        findings.append(_finding(row, "Container Apps", "Ingress configuration not assessed", "Read effective ingress configuration. An absent object is not evidence that insecure ingress is disabled.", "Unknown"))
    if ingress.get("allowInsecure") is True:
        findings.append(_finding(row, "Container Apps", "Insecure ingress allowed", "Disallow insecure ingress so HTTP is not accepted.", "Medium"))
    if scale.get("maxReplicas") == 1:
        findings.append(_finding(row, "Container Apps", "No scale out (maxReplicas is 1)", "Raise maxReplicas and set a scale rule.", "Low"))
    if not containers:
        findings.append(_finding(row, "Container Apps", "Container probes not assessed", "Read active revision container definitions and effective probes.", "Unknown"))
    for container in containers:
        types = set()
        for probe_config in container.get("probes") or []:
            probe_type = str(probe_config.get("type") or "").lower()
            handler = probe_config.get("httpGet") or probe_config.get("tcpSocket") or {}
            port = handler.get("port")
            if (probe_type not in ("startup", "liveness", "readiness") or probe_type in types
                    or "exec" in probe_config or "grpc" in probe_config
                    or type(port) is not int or not 1 <= port <= 65535):
                findings.append(_finding(
                    row, "Container Apps", f"Container {container.get('name', '(unnamed)')}: probe configuration not assessed",
                    "Validate effective probe definitions. Container Apps supports HTTP or TCP, one probe of each type per container, integer ports, and no exec or gRPC probes.",
                    "Unknown",
                ))
                continue
            types.add(probe_type)
        for probe in ("Startup", "Liveness", "Readiness"):
            if probe.lower() not in types:
                findings.append(_finding(
                    row, "Container Apps", f"Container {container.get('name', '(unnamed)')}: {probe} probe not explicit",
                    "Verify effective revision probes. With ingress the portal adds defaults to the main container, except GPU profiles; sidecars do not get portal defaults. TCP defaults do not prove application health. Define an appropriate probe for this container if required.",
                    "Unknown",
                ))
    if "maxReplicas" not in scale:
        findings.append(_finding(row, "Container Apps", "Scale limit not assessed", "Read effective revision scale settings; platform defaults are not workload sizing evidence.", "Unknown"))
    return findings


def build_report_data(findings, subs_scanned, checks_evaluated, notes):
    findings = sorted(findings, key=lambda f: SEVERITY_ORDER.get(f["severity"], 9))
    with_findings = len({f["resource"] for f in findings})
    high = sum(1 for f in findings if f["severity"] in ("Critical", "High"))
    sev_counts, by_cat = {}, {}
    for finding in findings:
        sev_counts[finding["severity"]] = sev_counts.get(finding["severity"], 0) + 1
        by_cat[finding["category"]] = by_cat.get(finding["category"], 0) + 1
    sev_items = [{"name": b, "value": sev_counts[b], "band": b} for b in ("Critical", "High", "Medium", "Low") if b in sev_counts]
    cat_items = sorted(({"name": k, "value": v} for k, v in by_cat.items()), key=lambda i: i["value"], reverse=True)
    return {
        "assessment_status": "Not assessed" if not subs_scanned else "Partial" if notes or any(f["severity"] == "Unknown" for f in findings) else "Complete",
        "sources": [
            {"title": "Container Apps probes", "url": "https://learn.microsoft.com/en-us/azure/container-apps/health-probes"},
            {"title": "App Service health checks", "url": "https://learn.microsoft.com/en-us/azure/app-service/monitor-instances-health-check"},
        ],
        "title": "App Service and Container Apps Health",
        "subtitle": "Web tier scaling, probes, and transport security.",
        "meta": {"window": "Point in time", "scope": f"{subs_scanned} subscription(s)", "source": "Azure Resource Graph"},
        "summary_cards": [
            {"label": "Resources with findings", "value": f"{with_findings:,}"},
            {"label": "High findings", "value": f"{high:,}"},
            {"label": "Check definitions", "value": str(checks_evaluated), "sub": "Not a count of successfully assessed resources"},
            {"label": "Subscriptions scanned", "value": str(subs_scanned)},
        ],
        "charts": [
            {"title": "Findings by severity", "unit": "findings", "items": sev_items},
            {"title": "Findings by category", "unit": "findings", "items": cat_items},
        ],
        "findings": {
            "title": "Web tier findings",
            "columns": ["resource", "category", "subscription", "resource_group", "check", "recommendation", "severity"],
            "rows": findings,
        },
        "method_notes": notes + [
            "Absent configuration is explicitly not assessed, never a pass. Read sites/config web and active revision definitions where Resource Graph omits fields.",
            "Probe coverage is per container and type: HTTP or TCP only, one per type, integer ports, no exec or gRPC. Portal defaults are not guaranteed for API deployments, sidecars or GPU profiles. TCP probes do not validate application dependencies.",
            "App Service Health Check path alone does not ensure redundancy, instance count, warmup or successful failover. Runtime health and workload recovery are not tested.",
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
        ("resources | where type =~ 'microsoft.web/sites' | project name, id, subscriptionId, resourceGroup, kind, properties", evaluate_site),
        ("resources | where type =~ 'microsoft.web/serverfarms' | project name, id, subscriptionId, resourceGroup, sku, properties", evaluate_plan),
        ("resources | where type =~ 'microsoft.app/containerapps' | project name, id, subscriptionId, resourceGroup, properties", evaluate_containerapp),
    ]
    for query, evaluator in queries:
        try:
            rows = _run_graph(headers, query)
        except Exception as error:  # noqa: BLE001
            notes.append(f"A web tier query could not be read ({error}).")
            continue
        for row in rows:
            scanned.add(row.get("subscriptionId"))
            findings.extend(evaluator(row))
    return build_report_data(findings, len({s for s in scanned if s}), CHECK_DEFINITIONS, notes)


if __name__ == "__main__":
    print(json.dumps(main()))

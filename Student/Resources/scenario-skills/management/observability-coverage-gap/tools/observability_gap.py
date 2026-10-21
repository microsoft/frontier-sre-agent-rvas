"""
observability_gap: Find monitoring wiring gaps with Azure Resource Graph.

Azure SRE Agent Python tool. Uses the agent managed identity (ARM scope) to
enumerate important resources and enabled alert candidates, read diagnostic
settings through each resource API, and print a report_data object as JSON.
Cross subscription destinations are valid. Configuration candidates are not
proof of telemetry delivery or operational coverage.

    python observability_gap.py | python report_render.py

Heavy imports (azure-identity, requests) are lazy so the pure classification
helpers can be unit tested without them. See references/checks-catalog.md.
"""

import json
import sys
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parent
for _candidate in (_TOOLS_DIR, _TOOLS_DIR / "tools", *(parent / "shared" / "tools" for parent in _TOOLS_DIR.parents)):
    if (_candidate / "azure_http.py").is_file():
        if str(_candidate) not in sys.path:
            sys.path.insert(0, str(_candidate))
        break

SOURCES = [
    {"title": "Diagnostic settings", "url": "https://learn.microsoft.com/azure/azure-monitor/essentials/diagnostic-settings"},
    {"title": "Metric alerts", "url": "https://learn.microsoft.com/azure/azure-monitor/alerts/alerts-metric-overview"},
]

ARM_ENDPOINT = "https://management.azure.com"
SEVERITY_ORDER = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}

IMPORTANT_TYPES = [
    "microsoft.compute/virtualmachines",
    "microsoft.web/sites",
    "microsoft.sql/servers/databases",
    "microsoft.storage/storageaccounts",
    "microsoft.keyvault/vaults",
    "microsoft.containerservice/managedclusters",
    "microsoft.network/applicationgateways",
    "microsoft.network/loadbalancers",
    "microsoft.documentdb/databaseaccounts",
    "microsoft.cache/redis",
    "microsoft.servicebus/namespaces",
    "microsoft.eventhub/namespaces",
    "microsoft.dbforpostgresql/flexibleservers",
    "microsoft.dbformysql/flexibleservers",
    "microsoft.apimanagement/service",
    "microsoft.containerregistry/registries",
    "microsoft.network/azurefirewalls",
]

TYPE_LABEL = {
    "microsoft.compute/virtualmachines": "Virtual machine",
    "microsoft.web/sites": "App Service",
    "microsoft.sql/servers/databases": "SQL database",
    "microsoft.storage/storageaccounts": "Storage account",
    "microsoft.keyvault/vaults": "Key Vault",
    "microsoft.containerservice/managedclusters": "AKS cluster",
    "microsoft.network/applicationgateways": "Application Gateway",
    "microsoft.network/loadbalancers": "Load balancer",
    "microsoft.documentdb/databaseaccounts": "Cosmos DB",
    "microsoft.cache/redis": "Redis",
    "microsoft.servicebus/namespaces": "Service Bus",
    "microsoft.eventhub/namespaces": "Event Hub",
    "microsoft.dbforpostgresql/flexibleservers": "PostgreSQL",
    "microsoft.dbformysql/flexibleservers": "MySQL",
    "microsoft.apimanagement/service": "API Management",
    "microsoft.containerregistry/registries": "Container Registry",
    "microsoft.network/azurefirewalls": "Azure Firewall",
}


def is_alert_covered(resource, covered_ids, covered_rgs, covered_subs):
    """A resource is covered when its id, its resource group, or its subscription
    appears in an alert scope. Pure and testable."""
    rid = (resource.get("id") or "").lower()
    sub = (resource.get("subscriptionId") or "").lower()
    rg = (resource.get("resourceGroup") or "").lower()
    rg_scope = f"/subscriptions/{sub}/resourcegroups/{rg}"
    sub_scope = f"/subscriptions/{sub}"
    return rid in covered_ids or rg_scope in covered_rgs or sub_scope in covered_subs


def classify_resource(resource, diag_parents, diag_available, covered_ids, covered_rgs, covered_subs, alerts_available=True):
    """Return a combined gap finding for a resource, or None. Pure and testable."""
    rid = (resource.get("id") or "").lower()
    missing = []
    severity = "Low"
    if diag_available and rid not in diag_parents:
        missing.append("usable diagnostic settings routing")
        severity = "High"
    if alerts_available and not is_alert_covered(resource, covered_ids, covered_rgs, covered_subs):
        missing.append("enabled alert candidate with an action group")
        severity = "High" if severity == "High" else "Medium"
    if not missing:
        return None
    return {
        "resource": resource.get("name", ""),
        "resource_type": TYPE_LABEL.get(resource.get("type", ""), resource.get("type", "")),
        "resource_id": resource.get("id", ""),
        "subscription": resource.get("subscriptionId", ""),
        "resource_group": resource.get("resourceGroup", ""),
        "missing": "; ".join("no " + item for item in missing),
        "recommendation": "Validate workload requirements and existing routing before adding " + " and ".join(missing) + ". Destinations may be in another subscription.",
        "severity": severity,
        "_band": severity,
    }


def subscription_findings(sub_ids_with_resources, action_group_subs, workspace_subs, sub_names):
    """Local destination absence says nothing about cross subscription routing."""
    return []


def usable_diagnostics(settings):
    """A configured destination and an enabled log or metric are needed."""
    return any(
        any((setting.get("properties") or {}).get(key) for key in
            ("workspaceId", "storageAccountId", "eventHubAuthorizationRuleId", "marketplacePartnerId"))
        and any(item.get("enabled") is True for key in ("logs", "metrics")
                for item in (setting.get("properties") or {}).get(key, []))
        for setting in settings
    )


def qualifying_scopes(rule, resource_type):
    """Return candidate scopes, never proof that conditions cover the workload."""
    props = rule.get("properties") or {}
    kind = (rule.get("type") or "").lower()
    actions = props.get("actions") or {}
    if isinstance(actions, list):
        has_actions = any(item.get("actionGroupId") for item in actions)
    else:
        has_actions = bool(actions.get("actionGroups"))
    if props.get("enabled") is not True or not has_actions:
        return []
    if kind not in ("microsoft.insights/metricalerts", "microsoft.insights/scheduledqueryrules",
                    "microsoft.insights/activitylogalerts"):
        return []
    target_types = props.get("targetResourceTypes") or [props.get("targetResourceType")]
    target_types = {t.lower() for t in target_types if t}
    scopes = []
    for scope in props.get("scopes") or []:
        scope = scope.lower()
        # A broad scope alone does not establish resource type applicability.
        if "/providers/" not in scope and resource_type.lower() not in target_types:
            continue
        scopes.append(scope)
    return scopes


def build_report_data(findings, resources_scanned, subs_scanned, diag_available, sub_names, notes):
    for finding in findings:
        finding["subscription"] = sub_names.get(finding["subscription"], finding["subscription"])
    findings = sorted(findings, key=lambda f: SEVERITY_ORDER.get(f["severity"], 9))
    blind = sum(1 for f in findings if "diagnostic settings" in f["missing"])
    no_ag = sum(1 for f in findings if "action group" in f["missing"])
    gap_types = {}
    for finding in findings:
        for piece in finding["missing"].split("; "):
            gap_types[piece] = gap_types.get(piece, 0) + 1
    type_items = [{"name": k, "value": v} for k, v in sorted(gap_types.items(), key=lambda kv: kv[1], reverse=True)]
    by_sub = {}
    for finding in findings:
        by_sub[finding["subscription"]] = by_sub.get(finding["subscription"], 0) + 1
    sub_items = sorted(({"name": k, "value": v} for k, v in by_sub.items()), key=lambda i: i["value"], reverse=True)
    if not diag_available:
        notes = notes + ["Incomplete diagnostic assessment. Unknown resources are not counted as having no diagnostic settings. Resource Graph alone cannot conclusively enumerate diagnostic settings."]
    return {
        "assessment_status": "Not assessed" if resources_scanned == 0 else ("Partial" if notes else "Complete"),
        "sources": SOURCES,
        "title": "Observability Coverage Gap",
        "subtitle": "Diagnostic routing and enabled alert candidates, subject to workload validation.",
        "meta": {"window": "Point in time", "scope": f"{subs_scanned} subscription(s)", "source": "Resource Graph and diagnostic settings API"},
        "summary_cards": [
            {"label": "Resources with gaps", "value": f"{len([f for f in findings if f['resource_type'] != 'Subscription']):,}"},
            {"label": "No usable diagnostic routing", "value": f"{blind:,}" if diag_available else "Unknown", "sub": "configuration only, not proof of telemetry delivery"},
            {"label": "Alert routing candidates missing", "value": f"{no_ag:,}"},
            {"label": "Resources scanned", "value": f"{resources_scanned:,}"},
        ],
        "charts": [
            {"title": "Gaps by type", "unit": "gaps", "items": type_items},
            {"title": "Gaps by subscription", "unit": "gaps", "items": sub_items},
        ],
        "findings": {
            "title": "Observability gaps",
            "columns": ["resource", "resource_type", "subscription", "resource_group", "missing", "recommendation", "severity"],
            "rows": findings,
        },
        "method_notes": notes + ["Rule candidates require enabled state, actions, supported type and matching scopes. Validate conditions, receiver health, processing rules and diagnostic destination delivery separately. Other telemetry mechanisms may provide coverage."],
    }


def _headers():
    from agent_identity import agent_token

    token = agent_token(f"{ARM_ENDPOINT}/.default")
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _run_graph(headers, query):
    import azure_http as requests

    url = f"{ARM_ENDPOINT}/providers/Microsoft.ResourceGraph/resources?api-version=2022-10-01"
    rows, skip_token = [], None
    for _ in range(40):
        payload = {"query": query, "options": {"resultFormat": "objectArray", "top": 1000}}
        if skip_token:
            payload["options"]["$skipToken"] = skip_token
        response = requests.post(url, headers=headers, json=payload, timeout=120)
        response.raise_for_status()
        body = response.json()
        if not isinstance(body.get("data"), list):
            raise ValueError("Incomplete Resource Graph response: data missing")
        rows.extend(body.get("data", []))
        skip_token = body.get("$skipToken")
        if not skip_token:
            if str(body.get("resultTruncated", "")).lower() == "true":
                raise RuntimeError("Resource Graph truncated results without continuation")
            return rows
    raise RuntimeError("Incomplete Resource Graph inventory: 40 page cap reached")


def _list_subscription_names(headers):
    import azure_http as requests

    url = f"{ARM_ENDPOINT}/subscriptions?api-version=2022-12-01"
    names = {}
    while url:
        response = requests.get(url, headers=headers, timeout=60)
        response.raise_for_status()
        body = response.json()
        if not isinstance(body.get("value"), list):
            raise ValueError("Diagnostic settings results missing")
        for item in body.get("value", []):
            names[item["subscriptionId"]] = item.get("displayName", item["subscriptionId"])
        url = body.get("nextLink")
    return names


def main() -> dict:
    headers = _headers()
    notes = []
    try:
        sub_names = _list_subscription_names(headers)
    except Exception as error:  # noqa: BLE001
        sub_names = {}
        notes.append(f"Could not list subscription names ({error}).")

    types_list = "','".join(IMPORTANT_TYPES)
    try:
        resources = _run_graph(headers, f"resources | where type in~ ('{types_list}') | project name, id, type, resourceGroup, subscriptionId, location")
    except Exception:
        return build_report_data([], 0, 0, False, sub_names, notes + ["Incomplete: resource inventory not read."])
    alerts_available = True
    try:
        alert_rows = _run_graph(headers, "resources | where type in~ ('microsoft.insights/metricalerts','microsoft.insights/scheduledqueryrules','microsoft.insights/activitylogalerts') | project id, type, properties")
    except Exception:
        alert_rows, alerts_available = [], False
        notes.append("Incomplete: alert rules not read; alert coverage is unknown.")

    findings = []
    unknown_diagnostics = 0
    for index, resource in enumerate(resources):
        diag_known, diag_parents = False, set()
        if index < 200:
            try:
                import azure_http as requests

                response = requests.get(f"{ARM_ENDPOINT}{resource['id']}/providers/Microsoft.Insights/diagnosticSettings?api-version=2021-05-01-preview", headers=headers, timeout=60)
                response.raise_for_status()
                body = response.json()
                if body.get("nextLink"):
                    raise RuntimeError("Diagnostic settings continuation not collected")
                diag_known = True
                if usable_diagnostics(body.get("value", [])):
                    diag_parents.add(resource["id"].lower())
            except Exception:
                pass
        if not diag_known:
            unknown_diagnostics += 1
        scopes = {scope for rule in alert_rows for scope in qualifying_scopes(rule, resource["type"])}
        finding = classify_resource(resource, diag_parents, diag_known, scopes, scopes, scopes, alerts_available)
        if finding:
            findings.append(finding)

    subs_with_resources = {r.get("subscriptionId") for r in resources}
    if unknown_diagnostics:
        notes.append(f"Incomplete: diagnostic settings unknown for {unknown_diagnostics} resources (access failures, unsupported resources or 200 resource collection cap).")
    return build_report_data(findings, len(resources), len(subs_with_resources), not unknown_diagnostics, sub_names, notes)


if __name__ == "__main__":
    print(json.dumps(main()))

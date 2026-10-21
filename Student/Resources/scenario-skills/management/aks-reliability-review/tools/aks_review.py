"""
aks_review: Review AKS clusters for reliability and operational best practices.

Azure SRE Agent Python tool. Uses the agent managed identity (ARM scope) to read
the managed cluster configuration with Azure Resource Graph, evaluate each
cluster against the checks in references/checks-catalog.md, and print a
report_data object as JSON ready to pipe into report_render.py.

    python aks_review.py | python report_render.py

Heavy imports (azure-identity, requests) are lazy so evaluate_cluster and the
report builder can be unit tested without them.
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


def _minor(version):
    parts = (version or "").split(".")
    return int(parts[1]) if len(parts) >= 2 and parts[1].isdigit() else None


def evaluate_cluster(cluster, evidence=None, today=None, zone_regions=None):
    """Return a list of finding dicts for one cluster. Pure and testable.

    cluster: {name, subscriptionId, resourceGroup, sku, properties}.
    """
    props = cluster.get("properties", {}) or {}
    sku = cluster.get("sku", {}) or {}
    base = {
        "cluster": cluster.get("name", ""),
        "subscription": cluster.get("subscriptionId", ""),
        "resource_group": cluster.get("resourceGroup", ""),
    }
    findings = []

    def add(check, recommendation, severity):
        findings.append({**base, "check": check, "recommendation": recommendation, "severity": severity, "_band": severity})

    version = ".".join(str(props.get("currentKubernetesVersion") or props.get("kubernetesVersion") or "").split(".")[:2])
    lifecycle = lifecycle_status("aks", version, aks_support_plan(props, sku), evidence, today)
    if lifecycle["status"] == "Unsupported":
        add(f"Kubernetes {version} outside verified support dates", lifecycle["reason"] + " Plan an approved upgrade.", "High")
    elif lifecycle["status"] == "Unknown":
        add(f"Kubernetes {version} support Unknown", lifecycle["reason"] + " Verify regional versions, support plan and LTS entitlement.", "Unknown")

    pools = props.get("agentPoolProfiles", []) or []
    if not pools:
        add("Node pools not assessed", "Read node pool profiles and current deployment state.", "Unknown")
    has_system_pool = any((pool.get("mode") or "").lower() == "system" for pool in pools)
    for pool in pools:
        zones = pool.get("availabilityZones") or []
        location = cluster.get("location", "").lower()
        if len(zones) < 2:
            if zone_regions is None or location not in zone_regions:
                add(f"Node pool {pool.get('name', '')} zone applicability Unknown", "Verify current AKS region, VM SKU and zone support before planning zone placement.", "Unknown")
            elif zone_regions[location] is True:
                add(f"Node pool {pool.get('name', '')} is not spread across availability zones", "Plan replacement across supported zones and validate workload scheduling.", "Medium")
        if (pool.get("mode") or "").lower() == "system":
            count = pool.get("minCount") if pool.get("enableAutoScaling") else pool.get("count")
            if count is None:
                add(f"System pool {pool.get('name', '')} node count Unknown", "Read the current node count and autoscaler minimum.", "Unknown")
            elif count < 3:
                add(f"System pool {pool.get('name', '')} below production recommendation of three nodes", "Plan at least three system nodes for production; two is a platform minimum, not the production recommendation.", "Medium")
    if pools and not has_system_pool:
        add("No dedicated system node pool", "Add a system mode node pool so control components are isolated.", "Low")

    access = props.get("apiServerAccessProfile", {}) or {}
    if not access:
        add("Control plane access not assessed", "Read apiServerAccessProfile and effective API access restrictions.", "Unknown")
    elif not access.get("enablePrivateCluster") and not (access.get("authorizedIpRanges") or access.get("authorizedIPRanges")):
        add("Control plane open to the internet", "Enable a private cluster, or set API server authorized IP ranges.", "Medium")

    channel = (props.get("autoUpgradeProfile", {}) or {}).get("upgradeChannel")
    if channel is None:
        add("Auto upgrade channel not assessed", "Read autoUpgradeProfile.upgradeChannel.", "Unknown")
    elif channel.lower() in ("none", "", "null"):
        add("No auto upgrade channel", "Set an upgrade channel (patch or stable) with a maintenance window.", "Medium")

    addons = props.get("addonProfiles", {}) or {}
    oms = addons.get("omsagent") or addons.get("omsAgent") or {}
    if oms.get("enabled") is None:
        add("Container Insights configuration not assessed", "Read addonProfiles and verify Azure Monitor coverage separately.", "Unknown")
    elif oms.get("enabled") is False:
        add("Container Insights monitoring not enabled", "Enable Azure Monitor Container Insights.", "Medium")

    network = props.get("networkProfile", {}) or {}
    if not network:
        add("Network policy engine not assessed", "Read networkProfile and actual network policy objects.", "Unknown")
    elif not network.get("networkPolicy") and (network.get("networkDataplane") or "").lower() != "cilium":
        add("No network policy engine identified", "Verify Azure, Calico or Azure CNI Powered by Cilium policy support; audit actual policy objects separately.", "Low")

    if props.get("aadProfile") is None or props.get("enableRBAC") is None:
        add("Entra ID and Kubernetes RBAC not assessed", "Read aadProfile and enableRBAC explicitly.", "Unknown")
    elif not props.get("aadProfile") or props.get("enableRBAC") is False:
        add("Entra ID and Kubernetes RBAC not fully enabled", "Enable Entra ID integration and Kubernetes RBAC.", "Medium")

    if not sku.get("tier"):
        add("Control plane tier not assessed", "Read SKU tier.", "Unknown")
    elif sku["tier"].lower() == "free":
        add("Free tier control plane has no uptime SLA", "Move production clusters to the Standard tier for the uptime SLA.", "Low")

    return findings


def build_report_data(clusters, notes, evidence=None, today=None, zone_regions=None):
    findings = []
    for cluster in clusters:
        findings.extend(evaluate_cluster(cluster, evidence, today, zone_regions))
    findings.sort(key=lambda f: SEVERITY_ORDER.get(f["severity"], 9))
    with_findings = len({f["cluster"] for f in findings})
    high = sum(1 for f in findings if f["severity"] in ("Critical", "High"))
    sev_counts, by_sub = {}, {}
    for finding in findings:
        sev_counts[finding["severity"]] = sev_counts.get(finding["severity"], 0) + 1
        by_sub[finding["subscription"]] = by_sub.get(finding["subscription"], 0) + 1
    sev_items = [{"name": b, "value": sev_counts[b], "band": b} for b in ("Critical", "High", "Medium", "Low") if b in sev_counts]
    sub_items = sorted(({"name": k, "value": v} for k, v in by_sub.items()), key=lambda i: i["value"], reverse=True)
    return {
        "assessment_status": "Not assessed" if not clusters else "Partial" if notes or any(f["severity"] == "Unknown" for f in findings) else "Complete",
        "sources": [
            {"title": "AKS support", "url": "https://learn.microsoft.com/en-us/azure/aks/supported-kubernetes-versions"},
            {"title": "System pools", "url": "https://learn.microsoft.com/en-us/azure/aks/use-system-pools"},
            {"title": "Cilium", "url": "https://learn.microsoft.com/en-us/azure/aks/azure-cni-powered-by-cilium"},
        ],
        "title": "AKS Reliability Review",
        "subtitle": "Kubernetes cluster reliability and operational best practices.",
        "meta": {"window": "Point in time", "scope": f"{len({c.get('subscriptionId') for c in clusters})} subscription(s)", "source": "Azure Resource Graph"},
        "summary_cards": [
            {"label": "Clusters reviewed", "value": f"{len(clusters):,}"},
            {"label": "Clusters with findings", "value": f"{with_findings:,}"},
            {"label": "High findings", "value": f"{high:,}"},
            {"label": "Total findings", "value": f"{len(findings):,}"},
        ],
        "charts": [
            {"title": "Findings by severity", "unit": "findings", "items": sev_items},
            {"title": "Findings by subscription", "unit": "findings", "items": sub_items},
        ],
        "findings": {
            "title": "AKS findings",
            "columns": ["cluster", "subscription", "resource_group", "check", "recommendation", "severity"],
            "rows": findings,
        },
        "method_notes": notes + [
            "Support requires a current versioned lifecycle snapshot, checked date and support plan. Missing, stale or unmatched evidence is Unknown, not supported.",
            "Lifecycle matching is by minor version only. Regional rollout, patch eligibility, especially LTS current patches, and actual upgrade paths require separate live evidence.",
            "Zone applicability is operator supplied per region after current service and VM SKU checks. No region or SKU availability is inferred.",
            "Configuration review only. Pod distribution, disruption budgets, policy objects, probes and actual failover are not assessed.",
            "A cluster with several gaps appears as several rows, one per check.",
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
    try:
        clusters = _run_graph(headers, "resources | where type =~ 'microsoft.containerservice/managedclusters' | project name, id, subscriptionId, resourceGroup, location, sku, properties")
    except Exception as error:  # noqa: BLE001
        return build_report_data([], [f"Could not read AKS clusters ({error})."])
    return build_report_data(clusters, notes)


if __name__ == "__main__":
    print(json.dumps(main()))

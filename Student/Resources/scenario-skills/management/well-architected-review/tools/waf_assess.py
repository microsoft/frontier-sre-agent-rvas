"""
waf_assess: Score the five Well-Architected pillars into one scorecard.

Azure SRE Agent Python tool. Uses the agent managed identity (ARM scope) to run a
curated set of Azure Resource Graph checks across accessible subscriptions, count
applicable and failing resources per check, score each pillar as a weighted pass
ratio, and print a report_data object as JSON ready to pipe into report_render.py.

    python waf_assess.py | python report_render.py

Heavy imports (azure-identity, requests) are lazy so the pure scoring helpers can
be unit tested without them. See references/checks-catalog.md.
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
WEIGHTS = {"Critical": 4, "High": 3, "Medium": 2, "Low": 1}
PILLARS = ["Reliability", "Security", "Cost Optimization", "Operational Excellence", "Performance Efficiency"]

# Each check counts applicable and failing resources with a single summarize query.
CHECKS = [
    {"pillar": "Reliability", "name": "VMs without zone or availability set", "severity": "High",
     "recommendation": "Deploy across availability zones or an availability set. Deep dive: reliability-posture-review.",
     "kql": "resources | where type =~ 'microsoft.compute/virtualmachines' | summarize applicable=count(), failing=countif((isnull(zones) or array_length(zones)==0) and isnull(properties.availabilitySet))"},
    {"pillar": "Reliability", "name": "Locally redundant storage", "severity": "Medium",
     "recommendation": "Use ZRS or GRS where the data warrants it.",
     "kql": "resources | where type =~ 'microsoft.storage/storageaccounts' | summarize applicable=count(), failing=countif(tostring(sku.name) endswith 'LRS')"},
    {"pillar": "Reliability", "name": "Premium SQL without zone redundancy", "severity": "High",
     "recommendation": "Enable zoneRedundant on Premium and Business Critical databases.",
     "kql": "resources | where type =~ 'microsoft.sql/servers/databases' | where tostring(sku.tier) in~ ('Premium','BusinessCritical') | summarize applicable=count(), failing=countif(tostring(properties.zoneRedundant) =~ 'false')"},
    {"pillar": "Reliability", "name": "Single region Cosmos DB", "severity": "Medium",
     "recommendation": "Add a second region and enable automatic failover.",
     "kql": "resources | where type =~ 'microsoft.documentdb/databaseaccounts' | summarize applicable=count(), failing=countif(array_length(properties.locations) < 2)"},

    {"pillar": "Security", "name": "Storage with anonymous blob access", "severity": "High",
     "recommendation": "Set allowBlobPublicAccess to false. Deep dive: network-exposure-review.",
     "kql": "resources | where type =~ 'microsoft.storage/storageaccounts' | summarize applicable=count(), failing=countif(tostring(properties.allowBlobPublicAccess) =~ 'true')"},
    {"pillar": "Security", "name": "PaaS with public network access", "severity": "Medium",
     "recommendation": "Disable public network access and use Private Link.",
     "kql": "resources | where type in~ ('microsoft.sql/servers','microsoft.keyvault/vaults','microsoft.documentdb/databaseaccounts','microsoft.dbforpostgresql/flexibleservers','microsoft.dbformysql/flexibleservers') | summarize applicable=count(), failing=countif(tostring(properties.publicNetworkAccess) =~ 'Enabled')"},
    {"pillar": "Security", "name": "Key Vaults without purge protection", "severity": "Medium",
     "recommendation": "Enable purge protection on Key Vaults.",
     "kql": "resources | where type =~ 'microsoft.keyvault/vaults' | summarize applicable=count(), failing=countif(tostring(properties.enablePurgeProtection) !~ 'true')"},

    {"pillar": "Cost Optimization", "name": "Unattached managed disks", "severity": "Medium",
     "recommendation": "Delete or snapshot unattached disks. Deep dive: finops-cost-optimizer.",
     "kql": "resources | where type =~ 'microsoft.compute/disks' | summarize applicable=count(), failing=countif(tostring(properties.diskState) == 'Unattached')"},
    {"pillar": "Cost Optimization", "name": "Unassociated public IPs", "severity": "Low",
     "recommendation": "Release public IPs with no association.",
     "kql": "resources | where type =~ 'microsoft.network/publicipaddresses' | summarize applicable=count(), failing=countif(isnull(properties.ipConfiguration) and isnull(properties.natGateway))"},

    {"pillar": "Operational Excellence", "name": "Resources with no owner tag", "severity": "Medium",
     "recommendation": "Apply an owner tag; enforce with Azure Policy. Deep dive: tag-governance-compliance.",
     "kql": "resources | summarize applicable=count(), failing=countif(isempty(tostring(tags['owner'])) and isempty(tostring(tags['Owner'])))"},
    {"pillar": "Operational Excellence", "name": "AKS outside verified lifecycle dates", "severity": "Medium",
     "recommendation": "Verify lifecycle snapshot, checked date, regional versions and LTS support plan. Deep dive: deprecation-retirement-tracker.",
     "lifecycle": True,
     "kql": "resources | where type =~ 'microsoft.containerservice/managedclusters' | project name, id, properties, sku"},

    {"pillar": "Performance Efficiency", "name": "App Service plans on Free, Shared, or Basic", "severity": "Medium",
     "recommendation": "Move production workloads to Standard or higher. Deep dive: appservice-containerapps-health.",
     "kql": "resources | where type =~ 'microsoft.web/serverfarms' | summarize applicable=count(), failing=countif(tostring(sku.tier) in~ ('Free','Shared','Basic'))"},
    {"pillar": "Performance Efficiency", "name": "Container Apps that cannot scale out", "severity": "Low",
     "recommendation": "Raise maxReplicas and set a scale rule.",
     "kql": "resources | where type =~ 'microsoft.app/containerapps' | summarize applicable=count(), failing=countif(toint(properties.template.scale.maxReplicas) == 1)"},
]

# Unknown fields are excluded from the custom score, not treated as passing.
REQUIRED_FIELDS = {
    "VMs without zone or availability set": "array_length(zones) > 0 or isnotnull(properties.availabilitySet)",
    "Locally redundant storage": "isempty(tostring(sku.name))",
    "Premium SQL without zone redundancy": "isnull(properties.zoneRedundant)",
    "Single region Cosmos DB": "isnull(properties.locations)",
    "Storage with anonymous blob access": "isnull(properties.allowBlobPublicAccess)",
    "PaaS with public network access": "isempty(tostring(public_access))",
    "Key Vaults without purge protection": "isnull(properties.enablePurgeProtection)",
    "Unattached managed disks": "isempty(tostring(properties.diskState))",
    "App Service plans on Free, Shared, or Basic": "isempty(tostring(sku.tier))",
    "Container Apps that cannot scale out": "isnull(properties.template.scale.maxReplicas)",
}


def check_query(check):
    query = check["kql"]
    if check["name"] == "PaaS with public network access":
        query = query.replace(
            "| summarize",
            "| extend public_access = iff(type in~ ('microsoft.dbforpostgresql/flexibleservers','microsoft.dbformysql/flexibleservers'), tostring(properties.network.publicNetworkAccess), tostring(properties.publicNetworkAccess)) | summarize",
        ).replace("tostring(properties.publicNetworkAccess) =~ 'Enabled'", "public_access =~ 'Enabled'")
    if check["name"] == "Key Vaults without purge protection":
        query = query.replace("!~ 'true'", "=~ 'false'")
    missing = REQUIRED_FIELDS.get(check["name"])
    if missing:
        query = query.replace("summarize applicable=count(),", f"summarize applicable=count(), unknown=countif({missing}),")
    return query


def rating(score):
    """Rating label for a pillar score. Pure and testable."""
    if score is None:
        return "Not assessed"
    if score >= 90:
        return "Excellent"
    if score >= 75:
        return "Good"
    if score >= 50:
        return "Fair"
    return "Poor"


def score_pillars(assessed):
    """Return {pillar: score or None} from assessed checks. Pure and testable.

    assessed: list of {pillar, severity, applicable, failing}.
    """
    weighted, total = {}, {}
    for check in assessed:
        if check.get("state") == "Not assessed":
            continue
        known = check.get("applicable", 0) - check.get("unknown", 0)
        if known <= 0:
            continue
        weight = WEIGHTS.get(check["severity"], 1)
        pass_ratio = (known - check["failing"]) / known
        weighted[check["pillar"]] = weighted.get(check["pillar"], 0.0) + weight * pass_ratio
        total[check["pillar"]] = total.get(check["pillar"], 0.0) + weight
    scores = {}
    for pillar in PILLARS:
        scores[pillar] = round(100 * weighted[pillar] / total[pillar]) if total.get(pillar) else None
    return scores


def build_report_data(assessed, subs_scanned, notes):
    scores = score_pillars(assessed)
    findings = []
    for check in assessed:
        if check.get("applicable") and check.get("failing"):
            applicable, failing = check["applicable"] - check.get("unknown", 0), check["failing"]
            pass_rate = round(100 * (applicable - failing) / applicable)
            findings.append({
                "pillar": check["pillar"], "check": check["name"], "applicable": applicable, "failing": failing,
                "pass_rate": f"{pass_rate}%", "recommendation": check["recommendation"],
                "severity": check["severity"], "_band": check["severity"],
            })
    findings.sort(key=lambda f: (SEVERITY_ORDER.get(f["severity"], 9), f["pillar"]))

    cards = []
    for pillar in PILLARS:
        score = scores.get(pillar)
        definitions = sum(c["pillar"] == pillar for c in CHECKS)
        evaluated = sum(c["pillar"] == pillar and c.get("state") != "Not assessed" for c in assessed)
        unknown = sum(c.get("unknown", 0) for c in assessed if c["pillar"] == pillar)
        coverage = f"{evaluated}/{definitions} checks read; {unknown} unknown resources"
        cards.append({"label": pillar, "value": (str(score) if score is not None else "n/a"),
                      "sub": f"{rating(score)}; {coverage}, partial coverage" if evaluated < definitions or unknown else f"{rating(score)}; {coverage}"})
    score_items = [{"name": pillar, "value": scores[pillar]} for pillar in PILLARS if scores.get(pillar) is not None]
    sev_counts = {}
    for finding in findings:
        sev_counts[finding["severity"]] = sev_counts.get(finding["severity"], 0) + 1
    sev_items = [{"name": b, "value": sev_counts[b], "band": b} for b in ("Critical", "High", "Medium", "Low") if b in sev_counts]

    return {
        "assessment_status": ("Not assessed" if not any(c.get("applicable", 0) for c in assessed)
                              else "Partial" if notes or len(assessed) < len(CHECKS) or any(c.get("unknown") or c.get("state") == "Not assessed" for c in assessed) else "Complete"),
        "coverage": {
            "definitions": len(CHECKS),
            "read": sum(c.get("state") != "Not assessed" for c in assessed),
            "skipped": len(CHECKS) - sum(c.get("state") != "Not assessed" for c in assessed),
            "unknown_resources": sum(c.get("unknown", 0) for c in assessed),
        },
        "sources": [{"title": "Microsoft Well Architected Framework", "url": "https://learn.microsoft.com/en-us/azure/well-architected/"},
                    {"title": "AKS lifecycle", "url": "https://learn.microsoft.com/en-us/azure/aks/supported-kubernetes-versions"}],
        "title": "Well-Architected Review",
        "subtitle": "Custom 13 check configuration indicator, not an official Microsoft Well Architected assessment or score.",
        "meta": {"window": "Point in time", "scope": f"{subs_scanned} subscription(s)", "source": "Azure Resource Graph"},
        "summary_cards": cards,
        "charts": [
            {"title": "Pillar scores", "unit": "score", "items": score_items},
            {"title": "Findings by severity", "unit": "checks", "items": sev_items},
        ],
        "findings": {
            "title": "What pulled the scores down",
            "columns": ["pillar", "check", "applicable", "failing", "pass_rate", "recommendation", "severity"],
            "rows": findings,
        },
        "method_notes": notes + [
            f"AKS lifecycle: {reason}" for check in assessed for reason in check.get("lifecycle_reasons", [])
        ] + [
            "Score is the weighted pass ratio per pillar. Weights: Critical 4, High 3, Medium 2, Low 1.",
            "Custom selection and scoring only, not Microsoft's assessment methodology, certification or full workload review. High scores can coexist with skipped and unknown coverage.",
            "Unknown resources and failed checks are excluded from the numerical denominator, never counted as passing. Read coverage is shown separately.",
            "Ratings: Excellent 90 and above, Good 75 to 89, Fair 50 to 74, Poor below 50.",
            "This is a roll up; each check names the dedicated skill with the full detail.",
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


def _count_subscriptions(headers):
    import azure_http as requests

    url = f"{ARM_ENDPOINT}/subscriptions?api-version=2022-12-01"
    total = 0
    while url:
        response = requests.get(url, headers=headers, timeout=60)
        response.raise_for_status()
        body = response.json()
        total += len([s for s in body.get("value", []) if s.get("state") in (None, "Enabled")])
        url = body.get("nextLink")
    return total


def assess_lifecycle_rows(rows, evidence=None, today=None):
    states, reasons = [], set()
    for row in rows:
        props = row.get("properties") or {}
        version = ".".join(str(props.get("currentKubernetesVersion") or props.get("kubernetesVersion") or "").split(".")[:2])
        status = lifecycle_status("aks", version, aks_support_plan(props, row.get("sku") or {}), evidence, today)
        states.append(status["status"])
        if status["status"] == "Unknown":
            reasons.add(status["reason"])
    result = {"applicable": len(states), "failing": states.count("Unsupported"), "unknown": states.count("Unknown")}
    if reasons:
        result["lifecycle_reasons"] = sorted(reasons)
    return result


def main() -> dict:
    headers = _headers()
    notes = []
    try:
        subs = _count_subscriptions(headers)
    except Exception:  # noqa: BLE001
        subs = 0
        notes.append("Subscription visibility could not be confirmed.")

    assessed = []
    for check in CHECKS:
        try:
            rows = _run_graph(headers, check_query(check))
            if check.get("lifecycle"):
                assessed.append({**check, **assess_lifecycle_rows(rows)})
            else:
                if not rows or "applicable" not in rows[0] or "failing" not in rows[0]:
                    raise ValueError("Missing count result")
                row = rows[0]
                assessed.append({**check, "applicable": int(row["applicable"]), "failing": int(row["failing"]), "unknown": int(row.get("unknown", 0))})
        except Exception:  # noqa: BLE001
            notes.append(f"Check skipped (not readable): {check['name']}.")
            assessed.append({**check, "applicable": 0, "failing": 0, "state": "Not assessed"})
    return build_report_data(assessed, subs, notes)


if __name__ == "__main__":
    print(json.dumps(main()))

"""
tag_compliance: Check Azure resources against a required tag standard.

Azure SRE Agent Python tool. Uses the agent managed identity (ARM scope) to
enumerate resources with Azure Resource Graph, check each against a required tag
list with case insensitive key matching, and print a
report_data object as JSON ready to pipe into report_render.py.

    python tag_compliance.py [owner,environment,cost-center] | python report_render.py

Heavy imports (azure-identity, requests) are lazy so the pure compliance helpers
can be unit tested without them. See references/checks-catalog.md.
"""

import json
import sys
from pathlib import Path


def _bootstrap_shared_tools():
    here = Path(__file__).resolve().parent
    candidates = [here, here / "tools"] + [parent / "shared" / "tools" for parent in list(here.parents)[:5]]
    for candidate in candidates:
        if (candidate / "azure_http.py").is_file():
            if str(candidate) not in sys.path:
                sys.path.insert(0, str(candidate))
            return
    raise ModuleNotFoundError("Bundle shared tools, including azure_http.py, with this collector.")


_bootstrap_shared_tools()

ARM_ENDPOINT = "https://management.azure.com"
DEFAULT_REQUIRED = ["owner", "environment", "cost-center"]
SOURCES = [
    {"title": "Azure tag semantics", "url": "https://learn.microsoft.com/azure/azure-resource-manager/management/tag-resources"},
    {"title": "Tag support by resource type", "url": "https://learn.microsoft.com/azure/azure-resource-manager/management/tag-support"},
]


def normalize_key(key):
    """Ignore case only; punctuation remains significant. Pure."""
    return (key or "").lower()


def missing_tags(resource_tags, required):
    """Return the required tags absent from a resource's tag bag. Pure.

    Required values must be nonblank. Values are not case normalized.
    """
    present = {normalize_key(k) for k, value in (resource_tags or {}).items() if value is not None and str(value).strip()}
    return [req for req in required if normalize_key(req) not in present]


def severity_for_missing(missing):
    """High when the owner tag is missing, Medium otherwise. Pure."""
    if any(normalize_key(tag) == "owner" for tag in missing):
        return "High"
    return "Medium"


def classify_resource(resource, required):
    """Return a finding for a non compliant resource, or None. Pure."""
    missing = missing_tags(resource.get("tags"), required)
    if not missing:
        return None
    severity = severity_for_missing(missing)
    return {
        "resource": resource.get("name", ""),
        "resource_type": resource.get("type", ""),
        "resource_id": resource.get("id", ""),
        "subscription": resource.get("subscriptionId", ""),
        "resource_group": resource.get("resourceGroup", ""),
        "missing_tags": ", ".join(missing),
        "recommendation": "Apply " + ", ".join(missing) + " with the correct values; enforce with Azure Policy.",
        "severity": severity,
        "_band": severity,
        "_missing_list": missing,
    }


def build_report_data(resources, required, subs_scanned, sub_names, notes, tag_support=None):
    findings = []
    assessed, unassessed, excluded = [], [], []
    support = {key.lower(): value for key, value in (tag_support or {}).items()}
    for resource in resources:
        supported = resource.get("supportsTags", support.get((resource.get("type") or "").lower()))
        if supported is False:
            excluded.append(resource)
            continue
        if supported is not True and not resource.get("tags"):
            unassessed.append(resource)
            continue
        assessed.append(resource)
        finding = classify_resource(resource, required)
        if finding:
            findings.append(finding)
    total = len(assessed)
    compliant = total - len(findings)
    compliance = round(compliant / total * 100.0, 1) if total else None
    no_owner = sum(1 for f in findings if any(normalize_key(t) == "owner" for t in f["_missing_list"]))

    per_tag = {req: 0 for req in required}
    for finding in findings:
        for tag in finding["_missing_list"]:
            per_tag[tag] = per_tag.get(tag, 0) + 1
    tag_items = [{"name": tag, "value": count} for tag, count in sorted(per_tag.items(), key=lambda kv: kv[1], reverse=True)]

    by_sub = {}
    for finding in findings:
        label = sub_names.get(finding["subscription"], finding["subscription"])
        finding["subscription_name"] = label
        by_sub[label] = by_sub.get(label, 0) + 1
    sub_items = sorted(({"name": k, "value": v} for k, v in by_sub.items()), key=lambda i: i["value"], reverse=True)

    findings.sort(key=lambda f: (0 if f["severity"] == "High" else 1, f["resource"]))
    for finding in findings:
        finding.pop("_missing_list", None)

    return {
        "assessment_status": "Not assessed" if not total else ("Partial" if notes or unassessed or not subs_scanned else "Complete"),
        "sources": SOURCES,
        "unassessed_resources": [{"resource_id": r.get("id", ""), "resource_type": r.get("type", ""), "reason": "Tag support unknown"} for r in unassessed],
        "excluded_resources": [{"resource_id": r.get("id", ""), "resource_type": r.get("type", ""), "reason": "Tagging unsupported by verified type configuration"} for r in excluded],
        "title": "Tag Governance Compliance",
        "subtitle": "Resources against the required tag standard.",
        "meta": {"window": ", ".join(required), "scope": f"{subs_scanned} subscription(s)", "source": "Azure Resource Graph"},
        "summary_cards": [
            {"label": "Compliance", "value": f"{compliance}%" if compliance is not None else "Not assessed", "sub": "assessed resources with nonblank required values"},
            {"label": "Non compliant", "value": f"{len(findings):,}"},
            {"label": "Missing an owner", "value": f"{no_owner:,}"},
            {"label": "Resources assessed", "value": f"{total:,}", "sub": f"{len(unassessed)} unknown, {len(excluded)} unsupported"},
        ],
        "charts": [
            {"title": "Missing by tag", "unit": "resources", "items": tag_items},
            {"title": "Non compliance by subscription", "unit": "resources", "items": sub_items},
        ],
        "findings": {
            "title": "Tag gaps",
            "columns": ["resource", "resource_id", "resource_type", "subscription", "resource_group", "missing_tags", "recommendation", "severity"],
            "rows": findings,
        },
        "method_notes": notes + [
            f"Required tags: {', '.join(required)}. Key matching ignores case only; separators are distinct. No alias expansion is implemented.",
            "Compliance requires nonblank values for every required tag. Values are not case normalized or validated against an allowed values policy.",
            "Denominator includes only resources with observed tags or verified tag support. Unsupported types are excluded; unknown support is not assessed.",
            "Empty results or inaccessible scope are not proof of compliance. Resource Graph visibility is not a complete tenant inventory.",
            "Enforce the standard durably with Azure Policy; a one time tagging pass drifts again without it.",
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
            if str(body.get("resultTruncated", "false")).lower() == "true":
                raise RuntimeError("Resource Graph results incomplete without continuation token.")
            return rows


def _list_subscription_names(headers):
    import azure_http as requests

    url = f"{ARM_ENDPOINT}/subscriptions?api-version=2022-12-01"
    names = {}
    while url:
        response = requests.get(url, headers=headers, timeout=60)
        response.raise_for_status()
        body = response.json()
        for item in body.get("value", []):
            names[item["subscriptionId"]] = item.get("displayName", item["subscriptionId"])
        url = body.get("nextLink")
    return names


def main(required=None, tag_support=None) -> dict:
    required = required or DEFAULT_REQUIRED
    headers = _headers()
    notes = []
    try:
        sub_names = _list_subscription_names(headers)
    except Exception as error:  # noqa: BLE001
        sub_names = {}
        notes.append(f"Could not list subscription names ({error}).")
    try:
        resources = _run_graph(headers, "resources | project name, id, type, resourceGroup, subscriptionId, tags")
    except Exception as error:  # noqa: BLE001
        resources = []
        notes.append(f"Resource inventory not assessed ({error}).")
    subs = {r.get("subscriptionId") for r in resources if r.get("subscriptionId")}
    return build_report_data(resources, required, len(subs), sub_names, notes, tag_support)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Assess required tags with case insensitive names.")
    parser.add_argument("required", nargs="?", default=",".join(DEFAULT_REQUIRED))
    parser.add_argument("--tag-support", help="Approved JSON mapping of full resource types to true (supported) or false (unsupported).")
    args = parser.parse_args()
    support = None
    if args.tag_support:
        with open(args.tag_support, encoding="utf-8") as handle:
            support = json.load(handle)
        if not isinstance(support, dict) or any(not isinstance(value, bool) for value in support.values()):
            parser.error("Tag support must be a JSON object with boolean values.")
    req = [t.strip() for t in args.required.split(",") if t.strip()]
    print(json.dumps(main(req, support)))

"""
quota_scan: Flag Azure usage counters that are close to their quota or limit.

Azure SRE Agent Python tool. Uses the agent managed identity (ARM scope) to find
the regions each subscription uses with Azure Resource Graph, read the compute,
network, and storage usage endpoints in those regions, flag any counter at or
above a threshold, and print a report_data object as JSON ready to pipe into
report_render.py.

    python quota_scan.py [threshold] | python report_render.py

Heavy imports (azure-identity, requests) are lazy so the pure classification
helpers can be unit tested without them. See references/checks-catalog.md.
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
THRESHOLD_DEFAULT = 80.0
SEVERITY_ORDER = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}


def utilization(current, limit):
    """Percent of the limit in use. Pure and testable."""
    try:
        current, limit = float(current), float(limit)
    except (TypeError, ValueError):
        return None
    return (current / limit * 100.0) if limit > 0 and current >= 0 and math.isfinite(current) and math.isfinite(limit) else None


def band(percent):
    """Severity band from a utilization percent. Pure and testable."""
    if percent >= 95:
        return "Critical"
    if percent >= 90:
        return "High"
    if percent >= 80:
        return "Medium"
    return "Low"


def classify_usage(item, subscription, location, threshold):
    """Return a finding for a usage item near its limit, or None. Pure."""
    name = item.get("name") or {}
    quota = name.get("localizedValue") or name.get("value") or "unknown"
    try:
        current = float(item.get("currentValue", 0) or 0)
        limit = float(item.get("limit", 0) or 0)
    except (TypeError, ValueError):
        return None
    if limit <= 0:
        return None
    percent = utilization(current, limit)
    if percent is None:
        return None
    if percent < threshold:
        return None
    severity = band(percent) if percent >= 80 else "Medium"
    return {
        "subscription": subscription,
        "location": location,
        "quota": quota,
        "used": int(current),
        "limit": int(limit),
        "utilization": f"{percent:.0f}%",
        "severity": severity,
        "_band": severity,
        "_percent": round(percent, 1),
        "recommendation": f"Request an increase for {quota} in {location} before it blocks new work.",
    }


def build_report_data(findings, subscriptions_scanned, regions_checked, threshold, notes, assessments=None):
    findings = sorted(findings, key=lambda f: f.get("_percent", 0), reverse=True)
    for finding in findings:
        finding["_command"] = None  # no safe automated increase; recommendation only
    critical = sum(1 for f in findings if f["severity"] == "Critical")
    severity_chart = {}
    for finding in findings:
        severity_chart[finding["severity"]] = severity_chart.get(finding["severity"], 0) + 1
    severity_items = [
        {"name": b, "value": severity_chart[b], "band": b}
        for b in ("Critical", "High", "Medium")
        if b in severity_chart
    ]
    tightest = [
        {"name": f"{f['quota']} ({f['location']})", "value": f["_percent"], "band": f["severity"], }
        for f in findings[:10]
    ]
    return {
        "assessment_status": "Not assessed" if not regions_checked else "Partial" if notes or not assessments or any(a["state"] != "Complete" for a in assessments) else "Complete",
        "assessments": assessments or [],
        "sources": [
            {"title": "View quotas", "url": "https://learn.microsoft.com/en-us/azure/quotas/view-quotas"},
            {"title": "Storage regional usage", "url": "https://learn.microsoft.com/en-us/rest/api/storagerp/usages/list-by-location?view=rest-storagerp-2023-05-01"},
        ],
        "title": "Quota and Limit Watch",
        "subtitle": "Headroom against Azure quotas and service limits.",
        "meta": {
            "window": f"{threshold:.0f}% threshold",
            "scope": f"{subscriptions_scanned} subscription(s)",
            "source": "Azure usage endpoints",
        },
        "summary_cards": [
            {"label": "Counters near limit", "value": f"{len(findings):,}"},
            {"label": "Critical", "value": f"{critical:,}", "sub": "95% or higher"},
            {"label": "Subscriptions", "value": str(subscriptions_scanned)},
            {"label": "Regions checked", "value": str(regions_checked)},
        ],
        "charts": [
            {"title": "Counters by severity", "unit": "counters", "items": severity_items},
            {"title": "Tightest counters", "unit": "%", "items": tightest},
        ],
        "findings": {
            "title": "Quota headroom",
            "columns": ["subscription", "location", "quota", "used", "limit", "utilization", "severity"],
            "rows": findings,
        },
        "method_notes": notes
        + [
            f"Reporting threshold: {threshold:.0f}%. Counters below it are not shown.",
            "Invalid, missing, zero or unbounded limits are not evidence of headroom. Coverage is reported separately from threshold findings.",
            "Only selected compute, network and storage counters in observed regions are read, not all service limits or deployment capacity guarantees.",
            "The skill reads usage only; it never requests or changes a quota.",
        ],
    }


def _headers():
    from agent_identity import agent_token

    token = agent_token(f"{ARM_ENDPOINT}/.default")
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _get(headers, url):
    import azure_http as requests

    response = requests.get(url, headers=headers, timeout=90)
    response.raise_for_status()
    return response.json().get("value", [])


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


def main(threshold: float = THRESHOLD_DEFAULT) -> dict:
    threshold = float(threshold)
    if not math.isfinite(threshold) or not 0 < threshold <= 100:
        raise ValueError("Threshold must be greater than 0 and at most 100.")
    headers = _headers()
    notes = []
    sub_names = {}
    try:
        sub_names = _list_subscription_names(headers)
    except Exception as error:  # noqa: BLE001
        notes.append(f"Could not list subscription names ({error}).")

    try:
        pairs = _run_graph(headers, "resources | where isnotempty(location) | summarize by subscriptionId, location")
    except Exception as error:  # noqa: BLE001
        return build_report_data([], 0, 0, threshold, [f"Could not enumerate regions in use ({error})."])

    findings = []
    subs, regions, failures = set(), set(), 0
    assessments = []
    for pair in pairs:
        sub = pair.get("subscriptionId", "")
        location = pair.get("location", "")
        if not sub or not location or location.lower() in ("global", ""):
            continue
        subs.add(sub)
        regions.add((sub, location))
        sub_label = sub_names.get(sub, sub)
        endpoints = [
            f"{ARM_ENDPOINT}/subscriptions/{sub}/providers/Microsoft.Compute/locations/{location}/usages?api-version=2023-07-01",
            f"{ARM_ENDPOINT}/subscriptions/{sub}/providers/Microsoft.Network/locations/{location}/usages?api-version=2023-09-01",
            f"{ARM_ENDPOINT}/subscriptions/{sub}/providers/Microsoft.Storage/locations/{location}/usages?api-version=2023-05-01",
        ]
        for url in endpoints:
            state = "Not assessed"
            try:
                items = _get(headers, url)
                valid = 0
                for item in items:
                    if utilization(item.get("currentValue"), item.get("limit")) is None:
                        notes.append(f"A quota counter has unknown or nonpositive limit in {location}.")
                        continue
                    valid += 1
                    finding = classify_usage(item, sub_label, location, threshold)
                    if finding:
                        findings.append(finding)
                if valid:
                    state = "Complete" if valid == len(items) else "Partial"
                else:
                    notes.append(f"No finite counters assessed for {location}.")
            except Exception:  # noqa: BLE001
                failures += 1
            assessments.append({"subscription": sub, "location": location, "endpoint": url, "state": state})

    if failures:
        notes.append(f"{failures} usage query(ies) could not be read and were skipped.")
    return build_report_data(findings, len(subs), len(regions), threshold, notes, assessments)


if __name__ == "__main__":
    value = float(sys.argv[1]) if len(sys.argv) > 1 else THRESHOLD_DEFAULT
    print(json.dumps(main(value)))

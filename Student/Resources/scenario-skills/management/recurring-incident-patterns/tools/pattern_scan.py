"""
pattern_scan: Rank recurring alert and health signals over a window.

Azure SRE Agent Python tool. Uses the agent managed identity (ARM scope) to read
fired alerts and resource health degradations across accessible subscriptions,
aggregate them by resource, rank the repeat offenders, group them by resource
type, and print a report_data object as JSON ready to pipe into report_render.py.

    python pattern_scan.py [days] | python report_render.py

Heavy imports (azure-identity, requests) are lazy so the pure aggregation helpers
can be unit tested without them. See references/checks-catalog.md.
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parent
for _candidate in (_TOOLS_DIR, _TOOLS_DIR / "tools", *(parent / "shared" / "tools" for parent in _TOOLS_DIR.parents)):
    if (_candidate / "azure_http.py").is_file():
        if str(_candidate) not in sys.path:
            sys.path.insert(0, str(_candidate))
        break

ARM_ENDPOINT = "https://management.azure.com"
SEVERITY_ORDER = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
REPEAT_THRESHOLD = 3
SOURCES = [
    {"title": "Alert instance retention", "url": "https://learn.microsoft.com/azure/azure-monitor/alerts/alerts-manage-alert-instances"},
    {"title": "Activity Log", "url": "https://learn.microsoft.com/azure/azure-monitor/essentials/activity-log"},
    {"title": "Alert query custom time range", "url": "https://learn.microsoft.com/python/api/azure-mgmt-alertsmanagement/azure.mgmt.alertsmanagement.operations.alertsoperations"},
]


def resource_type_from_id(resource_id):
    """Return a friendly provider/type from a resource id. Pure and testable."""
    parts = [p for p in (resource_id or "").split("/") if p]
    lower = [p.lower() for p in parts]
    if "providers" in lower:
        i = lower.index("providers")
        if i + 2 < len(parts):
            return f"{parts[i + 1]}/{parts[i + 2]}"
    return "unknown"


def _name(resource_id):
    return [p for p in (resource_id or "").split("/") if p][-1] if resource_id else ""


def severity_by_count(count):
    """Heuristic review priority from a signal count, not incident impact."""
    if count >= 10:
        return "High"
    if count >= 5:
        return "Medium"
    return "Low"


def aggregate(alerts, health_events):
    """Aggregate alerts and health degradations by resource. Pure and testable.

    alerts, health_events: lists of resource ids.
    Returns {resource_id: {name, type, alerts, health, count}}.
    """
    agg = {}
    for rid in alerts:
        if not rid:
            continue
        entry = agg.setdefault(rid.lower(), {"name": _name(rid), "type": resource_type_from_id(rid), "alerts": 0, "health": 0})
        entry["alerts"] += 1
    for rid in health_events:
        if not rid:
            continue
        entry = agg.setdefault(rid.lower(), {"name": _name(rid), "type": resource_type_from_id(rid), "alerts": 0, "health": 0})
        entry["health"] += 1
    for entry in agg.values():
        entry["count"] = entry["alerts"] + entry["health"]
    return agg


def repeat_offenders(agg, threshold=REPEAT_THRESHOLD):
    """Return offenders at or above the threshold, highest count first. Pure."""
    offenders = [entry for entry in agg.values() if entry["count"] >= threshold]
    offenders.sort(key=lambda e: e["count"], reverse=True)
    return offenders


def build_report_data(agg, window_label, subs_scanned, threshold, notes):
    offenders = repeat_offenders(agg, threshold)
    findings = []
    for entry in offenders:
        severity = severity_by_count(entry["count"])
        findings.append({
            "resource": entry["name"], "resource_type": entry["type"], "signal_count": entry["count"],
            "signals": f"{entry['alerts']} alert(s), {entry['health']} health degradation(s)",
            "recommendation": "Review redundancy and dependencies for a resource that keeps degrading; tune the workload or threshold for one that keeps alerting.",
            "severity": severity, "_band": severity, "_sort": entry["count"],
        })
    findings.sort(key=lambda f: f["_sort"], reverse=True)
    total_incidents = sum(entry["count"] for entry in agg.values())

    by_type = {}
    for entry in agg.values():
        by_type[entry["type"]] = by_type.get(entry["type"], 0) + entry["count"]
    type_items = sorted(({"name": k, "value": v} for k, v in by_type.items()), key=lambda i: i["value"], reverse=True)[:10]
    top_items = [{"name": f["resource"], "value": f["signal_count"]} for f in findings[:10]]

    return {
        "assessment_status": "Not assessed" if subs_scanned == 0 else ("Partial" if notes else "Complete"),
        "sources": SOURCES,
        "title": "Recurring Incident Patterns",
        "subtitle": "Repeated alert and health signals, not a count of distinct incidents.",
        "meta": {"window": window_label, "scope": f"{subs_scanned} subscription(s)", "source": "Azure Monitor alerts and Resource Health"},
        "summary_cards": [
            {"label": "Resource signal occurrences", "value": f"{total_incidents:,}"},
            {"label": "Repeat offenders", "value": f"{len(offenders):,}", "sub": f"{threshold}+ signals"},
            {"label": "Resources affected", "value": f"{len(agg):,}"},
            {"label": "Window", "value": window_label},
        ],
        "charts": [
            {"title": "Signals by resource type", "unit": "signals", "items": type_items},
            {"title": "Top repeat offenders", "unit": "signals", "items": top_items},
        ],
        "findings": {
            "title": "Repeat offenders",
            "columns": ["resource", "resource_type", "signal_count", "signals", "recommendation", "severity"],
            "rows": findings,
        },
        "method_notes": notes + [
            f"Window: {window_label}. Repeat threshold: {threshold} signals.",
            "Counts are resource signal occurrences, not deduplicated or correlated incidents. One incident can emit multiple alerts and health signals. Correlate against an incident system before reporting incident totals.",
        ],
    }


def _headers():
    from agent_identity import agent_token

    token = agent_token(f"{ARM_ENDPOINT}/.default")
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _list_subscriptions(headers):
    import azure_http as requests

    url = f"{ARM_ENDPOINT}/subscriptions?api-version=2022-12-01"
    subs = []
    while url:
        response = requests.get(url, headers=headers, timeout=60)
        response.raise_for_status()
        body = response.json()
        subs.extend(item["subscriptionId"] for item in body.get("value", []) if item.get("state") in (None, "Enabled"))
        url = body.get("nextLink")
    return subs


def _read_alerts(headers, subscription, time_range, notes=None, start=None, end=None):
    import azure_http as requests

    parameters = {"api-version": "2019-05-05-preview"}
    if start and end:
        parameters["customTimeRange"] = f"{start}/{end}"
    else:
        parameters["timeRange"] = time_range
    url = f"{ARM_ENDPOINT}/subscriptions/{subscription}/providers/Microsoft.AlertsManagement/alerts?{urlencode(parameters)}"
    ids, pages, seen = [], 0, set()
    while url and pages < 40:
        response = requests.get(url, headers=headers, timeout=120)
        response.raise_for_status()
        body = response.json()
        if not isinstance(body.get("value"), list):
            raise ValueError("Incomplete alert response: records missing")
        for alert in body.get("value", []):
            key = alert.get("id")
            if key and key.lower() in seen:
                continue
            if key:
                seen.add(key.lower())
            essentials = (alert.get("properties", {}) or {}).get("essentials", {}) or {}
            ids.append(essentials.get("targetResource", ""))
        url = body.get("nextLink")
        pages += 1
    if url:
        if notes is None:
            raise RuntimeError("Incomplete alerts: 40 page cap reached")
        notes.append(f"Incomplete alerts for subscription {subscription}: 40 page cap reached.")
    return ids


def _read_health(headers, subscription, start, notes=None, end=None):
    import azure_http as requests

    flt = f"eventTimestamp ge '{start}'"
    if end:
        flt += f" and eventTimestamp le '{end}'"
    url = f"{ARM_ENDPOINT}/subscriptions/{subscription}/providers/microsoft.insights/eventtypes/management/values?api-version=2015-04-01&$filter={flt}"
    ids, pages, seen = [], 0, set()
    while url and pages < 40:
        response = requests.get(url, headers=headers, timeout=120)
        response.raise_for_status()
        body = response.json()
        if not isinstance(body.get("value"), list):
            raise ValueError("Incomplete health response: records missing")
        for event in body.get("value", []):
            key = event.get("eventDataId") or event.get("id")
            if key and key.lower() in seen:
                continue
            if key:
                seen.add(key.lower())
            if ((event.get("category") or {}).get("value") or "").lower() != "resourcehealth":
                continue
            status = ((event.get("properties") or {}).get("currentHealthStatus") or "").lower()
            if status in ("unavailable", "degraded"):
                ids.append(event.get("resourceId", ""))
        url = body.get("nextLink")
        pages += 1
    if url:
        if notes is None:
            raise RuntimeError("Incomplete Resource Health: 40 page cap reached")
        notes.append(f"Incomplete Resource Health for subscription {subscription}: 40 page cap reached.")
    return ids


def main(days: int = 30) -> dict:
    if int(days) not in (1, 7, 30):
        raise ValueError("Choose exactly 1, 7 or 30 days so alert and health windows agree")
    time_range = f"{int(days)}d"
    headers = _headers()
    notes = []
    end = datetime.now(timezone.utc).replace(microsecond=0)
    start = (end - timedelta(days=int(days))).isoformat()
    window_label = f"{start} to {end.isoformat()} (requested {days} days; both sources use these UTC boundaries)"
    try:
        subs = _list_subscriptions(headers)
    except Exception as error:  # noqa: BLE001
        return build_report_data({}, window_label, 0, REPEAT_THRESHOLD, ["Incomplete: could not list subscriptions."])

    alerts, health = [], []
    for sub in subs:
        try:
            alerts.extend(_read_alerts(headers, sub, time_range, notes, start=start, end=end.isoformat()))
        except Exception:  # noqa: BLE001
            notes.append(f"Alerts not read for subscription {sub}.")
        try:
            health.extend(_read_health(headers, sub, start, notes, end=end.isoformat()))
        except Exception:  # noqa: BLE001
            notes.append(f"Resource health not read for subscription {sub}.")

    return build_report_data(aggregate(alerts, health), window_label, len(subs), REPEAT_THRESHOLD, notes)


if __name__ == "__main__":
    window = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    print(json.dumps(main(window)))

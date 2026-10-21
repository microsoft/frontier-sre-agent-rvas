"""
change_scan: Correlate Azure Activity Log changes with health degradations.

Azure SRE Agent Python tool. Uses the agent managed identity (ARM scope) to read
the Activity Log across accessible subscriptions, separate administrative changes
from resource health events, correlate each degradation with the changes that
preceded it, surface deletes and failed changes, and print a report_data object
as JSON ready to pipe into report_render.py.

    python change_scan.py [days] | python report_render.py

Heavy imports (azure-identity, requests) are lazy so the pure correlation helpers
can be unit tested without them. See references/checks-catalog.md.
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parent
for _candidate in (_TOOLS_DIR, _TOOLS_DIR / "tools", *(parent / "shared" / "tools" for parent in _TOOLS_DIR.parents)):
    if (_candidate / "azure_http.py").is_file():
        if str(_candidate) not in sys.path:
            sys.path.insert(0, str(_candidate))
        break

ARM_ENDPOINT = "https://management.azure.com"
SEVERITY_ORDER = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
CORRELATION_WINDOW_MINUTES = 120
SOURCES = [{"title": "Activity Log scope and retention", "url": "https://learn.microsoft.com/azure/azure-monitor/essentials/activity-log"}]


def _subscription(event):
    parts = (event.get("resourceId") or "").lower().split("/")
    return (event.get("subscriptionId") or (parts[2] if len(parts) > 2 and parts[1] == "subscriptions" else "")).lower()


def _parse_time(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _name(resource_id):
    return [p for p in (resource_id or "").split("/") if p][-1] if resource_id else ""


def is_change_event(event):
    """True for an administrative write, delete, or action. Pure and testable."""
    category = ((event.get("category") or {}).get("value") or "").lower()
    op = ((event.get("operationName") or {}).get("value") or "").lower()
    return category == "administrative" and (op.endswith("/write") or op.endswith("/delete") or op.endswith("/action"))


def is_health_degraded(event):
    """True for a resource health event that went Unavailable or Degraded. Pure."""
    category = ((event.get("category") or {}).get("value") or "").lower()
    if category != "resourcehealth":
        return False
    status = ((event.get("properties") or {}).get("currentHealthStatus") or "").lower()
    return status in ("unavailable", "degraded")


def extract_change(event):
    return {
        "time": event.get("eventTimestamp", ""),
        "resource_id": (event.get("resourceId") or "").lower(),
        "resource": _name(event.get("resourceId")),
        "resource_group": (event.get("resourceGroupName") or "").lower(),
        "operation": (event.get("operationName") or {}).get("localizedValue") or (event.get("operationName") or {}).get("value", ""),
        "op_value": ((event.get("operationName") or {}).get("value") or "").lower(),
        "status": (event.get("status") or {}).get("value", ""),
        "caller": event.get("caller", "") or "",
        "subscription": _subscription(event),
    }


def extract_health(event):
    return {
        "time": event.get("eventTimestamp", ""),
        "resource_id": (event.get("resourceId") or "").lower(),
        "resource": _name(event.get("resourceId")),
        "resource_group": (event.get("resourceGroupName") or "").lower(),
        "status": ((event.get("properties") or {}).get("currentHealthStatus") or ""),
        "subscription": _subscription(event),
    }


def correlate(changes, health_events, window_minutes=CORRELATION_WINDOW_MINUTES):
    """Link degradations to preceding changes. Returns (findings, linked_keys). Pure."""
    findings, linked = [], set()
    window = timedelta(minutes=window_minutes)
    for health in health_events:
        h_time = _parse_time(health["time"])
        if not h_time:
            continue
        best = None
        for change in changes:
            c_time = _parse_time(change["time"])
            if not c_time or c_time > h_time or (h_time - c_time) > window:
                continue
            same = bool(change["resource_id"]) and change["resource_id"] == health["resource_id"] or (
                change["subscription"] and change["subscription"] == health["subscription"]
                and change["resource_group"] and change["resource_group"] == health["resource_group"]
            )
            if not same:
                continue
            if best is None or c_time > _parse_time(best["time"]):
                best = change
        if best:
            gap = int((h_time - _parse_time(best["time"])).total_seconds() // 60)
            linked.add((best["resource_id"], best["time"], best["op_value"]))
            findings.append({
                "time": best["time"], "resource": best["resource"], "change": best["operation"],
                "resource_id": best["resource_id"],
                "caller": best["caller"], "outcome": best["status"],
                "note": f"Temporal candidate ({'same resource' if best['resource_id'] == health['resource_id'] else 'same subscription and resource group, not a dependency'}): preceded {health['status']} on {health['resource']} by {gap} min",
                "subscription": best["subscription"], "severity": "High", "_band": "High",
            })
    return findings, linked


def classify_unlinked(change):
    """Return a finding for a delete or failed change, or None. Pure and testable."""
    if change["op_value"].endswith("/delete") and change["status"].lower() == "succeeded":
        note, severity = "Resource deleted; confirm it was intended", "Medium"
    elif change["status"].lower() == "failed":
        note, severity = "Change failed; may leave the resource half configured", "Medium"
    else:
        note, severity = "Administrative change; no health correlation established", "Low"
    return {
        "time": change["time"], "resource": change["resource"], "change": change["operation"],
        "resource_id": change["resource_id"],
        "caller": change["caller"], "outcome": change["status"], "note": note,
        "subscription": change["subscription"], "severity": severity, "_band": severity,
    }


def build_report_data(changes, health_events, window_days, subs_scanned, sub_names, notes):
    linked_findings, linked_keys = correlate(changes, health_events)
    findings = list(linked_findings)
    deletes = sum(c["op_value"].endswith("/delete") for c in changes)
    failures = sum(c["status"].lower() == "failed" for c in changes)
    for change in changes:
        key = (change["resource_id"], change["time"], change["op_value"])
        if key in linked_keys:
            continue
        finding = classify_unlinked(change)
        if finding:
            findings.append(finding)
    for finding in findings:
        finding["subscription"] = sub_names.get(finding["subscription"], finding["subscription"])
    findings.sort(key=lambda f: (SEVERITY_ORDER.get(f["severity"], 9), f["time"]), reverse=False)

    sev_counts, by_sub = {}, {}
    for finding in findings:
        sev_counts[finding["severity"]] = sev_counts.get(finding["severity"], 0) + 1
        by_sub[finding["subscription"]] = by_sub.get(finding["subscription"], 0) + 1
    sev_items = [{"name": b, "value": sev_counts[b], "band": b} for b in ("Critical", "High", "Medium", "Low") if b in sev_counts]
    sub_items = sorted(({"name": k, "value": v} for k, v in by_sub.items()), key=lambda i: i["value"], reverse=True)

    return {
        "assessment_status": "Not assessed" if subs_scanned == 0 else ("Partial" if notes else "Complete"),
        "sources": SOURCES,
        "collected_changes": changes,
        "title": "Change Audit",
        "subtitle": "What changed and whether it preceded a health degradation.",
        "meta": {"window": f"{window_days} day(s)", "scope": f"{subs_scanned} subscription(s)", "source": "Azure Activity Log"},
        "summary_cards": [
            {"label": "Total changes", "value": f"{len(changes):,}"},
            {"label": "Linked to a degradation", "value": f"{len(linked_findings):,}", "sub": "changes before a problem"},
            {"label": "Deletes", "value": f"{deletes:,}"},
            {"label": "Failed changes", "value": f"{failures:,}"},
        ],
        "charts": [
            {"title": "Findings by severity", "unit": "findings", "items": sev_items},
            {"title": "Findings by subscription", "unit": "findings", "items": sub_items},
        ],
        "findings": {
            "title": "All administrative changes, with correlation candidates",
            "columns": ["time", "resource", "resource_id", "subscription", "change", "caller", "outcome", "note", "severity"],
            "rows": findings,
        },
        "method_notes": notes + [
            f"Read window: {window_days} day(s). Correlation window: {CORRELATION_WINDOW_MINUTES} minutes before a degradation.",
            "Correlation is not proof. The time gap is the evidence; a human confirms cause.",
            "All collected write, delete and action records are retained, including successful unlinked writes. Activity Log is a control plane source, not a complete audit of data plane operations, SQL statements, guest changes or application deployments. Use service specific logs for those.",
            "Successful non delete changes are counted but not listed individually.",
        ],
    }


def _headers():
    from agent_identity import agent_token

    token = agent_token(f"{ARM_ENDPOINT}/.default")
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


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


def _read_activity(headers, subscription, start, notes=None):
    import azure_http as requests

    flt = f"eventTimestamp ge '{start}'"
    url = f"{ARM_ENDPOINT}/subscriptions/{subscription}/providers/microsoft.insights/eventtypes/management/values?api-version=2015-04-01&$filter={flt}"
    events, pages = [], 0
    while url and pages < 40:
        try:
            response = requests.get(url, headers=headers, timeout=120)
            response.raise_for_status()
            body = response.json()
            if not isinstance(body.get("value"), list):
                raise ValueError("Missing Activity Log records")
        except Exception:
            if notes is None:
                raise
            notes.append(f"Incomplete Activity Log for subscription {subscription}: collection failed after {len(events)} records.")
            return events
        for event in body.get("value", []):
            event["subscriptionId"] = subscription
            events.append(event)
        url = body.get("nextLink")
        pages += 1
    if url:
        if notes is None:
            raise RuntimeError("Incomplete Activity Log: 40 page cap reached")
        notes.append(f"Incomplete Activity Log for subscription {subscription}: 40 page cap reached.")
    return events


def main(days: int = 7) -> dict:
    if int(days) < 1:
        raise ValueError("The read window must be positive")
    headers = _headers()
    notes = []
    start = (datetime.now(timezone.utc) - timedelta(days=int(days))).replace(microsecond=0).isoformat()
    try:
        sub_names = _list_subscription_names(headers)
    except Exception as error:  # noqa: BLE001
        return build_report_data([], [], days, 0, {}, [f"Could not list subscriptions ({error})."])

    changes, health_events = [], []
    for sub in sub_names:
        try:
            for event in _read_activity(headers, sub, start, notes):
                if is_change_event(event):
                    changes.append(extract_change(event))
                elif is_health_degraded(event):
                    health_events.append(extract_health(event))
        except Exception:  # noqa: BLE001
            notes.append(f"Activity Log not read for subscription {sub}.")
    return build_report_data(changes, health_events, int(days), len(sub_names), sub_names, notes)


if __name__ == "__main__":
    window = int(sys.argv[1]) if len(sys.argv) > 1 else 7
    print(json.dumps(main(window)))

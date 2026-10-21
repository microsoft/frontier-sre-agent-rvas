"""
gather_context: Collect triage evidence for one affected Azure resource.

Azure SRE Agent Python tool. Uses the agent managed identity (ARM scope) to read
Azure Resource Health availability statuses, the Activity Log changes over a
window for the resource's resource group, and the neighbouring resources, then
prints an evidence object as JSON. The skill reasons over this evidence to a
probable cause and assembles the incident report.

    python gather_context.py "<resource id>" [hours]

Heavy imports (azure-identity, requests) are lazy so the pure parsing and
timeline helpers can be unit tested without them. See references/triage-method.md.
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
SOURCES = [
    {"title": "Activity Log", "url": "https://learn.microsoft.com/azure/azure-monitor/essentials/activity-log"},
    {"title": "Resource Graph large datasets", "url": "https://learn.microsoft.com/azure/governance/resource-graph/concepts/work-with-data"},
]


def parse_resource_id(resource_id):
    """Return (subscription, resource_group) from a resource id. Pure."""
    parts = [p for p in (resource_id or "").split("/") if p]
    lower = [p.lower() for p in parts]
    sub = rg = ""
    if "subscriptions" in lower:
        i = lower.index("subscriptions")
        sub = parts[i + 1] if i + 1 < len(parts) else ""
    if "resourcegroups" in lower:
        i = lower.index("resourcegroups")
        rg = parts[i + 1] if i + 1 < len(parts) else ""
    return sub, rg


def severity_for_activity(event):
    """Band for an Activity Log event. Pure and testable."""
    level = (event.get("level") or "").lower()
    status = ((event.get("status") or {}).get("value") or "").lower()
    if status == "failed" or level in ("critical", "error"):
        return "High"
    if level == "warning":
        return "Medium"
    return "Low"


def severity_for_health(state):
    """Band for a Resource Health availability state. Pure and testable."""
    value = (state or "").lower()
    if value == "unavailable":
        return "Critical"
    if value == "degraded":
        return "High"
    return "Low"


def build_timeline(activity_events, health_statuses):
    """Merge changes and health transitions into one timeline, newest first. Pure."""
    timeline = []
    for event in activity_events:
        operation = (event.get("operationName") or {})
        signal = operation.get("localizedValue") or operation.get("value") or "operation"
        status = (event.get("status") or {}).get("value", "")
        caller = event.get("caller", "")
        detail = " ".join(part for part in [status, "by " + caller if caller else ""] if part).strip()
        timeline.append({
            "time": event.get("eventTimestamp", ""),
            "source": "Activity log",
            "signal": signal,
            "detail": detail,
            "severity": severity_for_activity(event),
        })
    for status in health_statuses:
        props = status.get("properties", status)
        state = props.get("availabilityState", "")
        timeline.append({
            "time": props.get("occuredTime") or props.get("reportedTime", ""),
            "source": "Resource Health",
            "signal": state or "health",
            "detail": props.get("summary", "") or props.get("reasonType", ""),
            "severity": severity_for_health(state),
        })
    for row in timeline:
        row["_band"] = row["severity"]
    timeline.sort(key=lambda row: row.get("time", ""), reverse=True)
    return timeline


def _headers():
    from agent_identity import agent_token

    token = agent_token(f"{ARM_ENDPOINT}/.default")
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _get(headers, url):
    import azure_http as requests

    response = requests.get(url, headers=headers, timeout=90)
    response.raise_for_status()
    return response.json()


def _read_pages(headers, url, label, notes, max_pages=40):
    rows = []
    for _ in range(max_pages):
        try:
            body = _get(headers, url)
            if not isinstance(body.get("value"), list):
                raise ValueError("Missing collection results")
        except Exception:
            notes.append(f"Incomplete: {label} collection failed after {len(rows)} records.")
            return rows
        rows.extend(body.get("value", []))
        url = body.get("nextLink")
        if not url:
            return rows
    notes.append(f"Incomplete: {label} reached the {max_pages} page cap with continuation outstanding.")
    return rows


def _run_graph(headers, query, notes=None, max_pages=5):
    import azure_http as requests

    notes = notes if notes is not None else []
    url = f"{ARM_ENDPOINT}/providers/Microsoft.ResourceGraph/resources?api-version=2022-10-01"
    payload = {"query": query, "options": {"resultFormat": "objectArray", "top": 200}}
    rows = []
    for _ in range(max_pages):
        response = requests.post(url, headers=headers, json=payload, timeout=90)
        response.raise_for_status()
        body = response.json()
        if not isinstance(body.get("data"), list):
            raise ValueError("Incomplete Resource Graph response: data missing")
        rows.extend(body.get("data", []))
        token = body.get("$skipToken")
        if not token:
            if str(body.get("resultTruncated", "")).lower() == "true":
                notes.append("Incomplete: neighbour inventory truncated without continuation.")
            return rows
        payload["options"]["$skipToken"] = token
    notes.append(f"Incomplete: neighbour inventory reached {max_pages} pages of 200 rows.")
    return rows


def main(resource_id: str, hours: int = 24) -> dict:
    if int(hours) < 1:
        raise ValueError("The read window must be positive")
    sub, rg = parse_resource_id(resource_id)
    if not sub or not rg or any(c in sub + rg for c in "'\"\\\r\n"):
        raise ValueError("A resource id with a subscription and resource group is required")
    name = [p for p in resource_id.split("/") if p][-1] if resource_id else ""
    headers = _headers()
    notes = []
    start = (datetime.now(timezone.utc) - timedelta(hours=int(hours))).replace(microsecond=0).isoformat()

    health_statuses, current = [], {}
    try:
        health_statuses = _read_pages(headers, f"{ARM_ENDPOINT}{resource_id}/providers/Microsoft.ResourceHealth/availabilityStatuses?api-version=2020-05-01", "Resource Health", notes)
        if not health_statuses:
            notes.append("Incomplete health assessment: no availability statuses returned; current health is unknown.")
        if health_statuses:
            props = health_statuses[0].get("properties", {})
            current = {
                "state": props.get("availabilityState", "Unknown"),
                "summary": props.get("summary", ""),
                "reason": props.get("reasonType", ""),
                "time": props.get("occuredTime") or props.get("reportedTime", ""),
            }
    except Exception as error:  # noqa: BLE001
        notes.append(f"Resource Health not read ({error}).")

    activity = []
    try:
        flt = f"eventTimestamp ge '{start}' and resourceGroupName eq '{rg}'"
        url = f"{ARM_ENDPOINT}/subscriptions/{sub}/providers/microsoft.insights/eventtypes/management/values?api-version=2015-04-01&$filter={flt}"
        activity = _read_pages(headers, url, "Activity Log", notes)
    except Exception as error:  # noqa: BLE001
        notes.append(f"Activity Log not read ({error}).")

    neighbors = []
    try:
        neighbors = _run_graph(headers, f"resources | where subscriptionId == '{sub}' and resourceGroup =~ '{rg}' | project name, type, id", notes)
    except Exception as error:  # noqa: BLE001
        notes.append(f"Neighbours not read ({error}).")

    return {
        "assessment_status": "Partial" if notes else "Complete",
        "sources": SOURCES,
        "resource_id": resource_id,
        "resource_name": name,
        "subscription": sub,
        "resource_group": rg,
        "window_hours": int(hours),
        "current_health": current,
        "timeline": build_timeline(activity, health_statuses),
        "neighbors": neighbors,
        "neighbor_interpretation": "Same resource group is inventory proximity only, not a verified dependency. Resource Health availability statuses are not guaranteed to provide full history for the requested window.",
        "notes": notes,
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Pass the affected resource id as the first argument."}))
        raise SystemExit(1)
    window = int(sys.argv[2]) if len(sys.argv) > 2 else 24
    print(json.dumps(main(sys.argv[1], window)))

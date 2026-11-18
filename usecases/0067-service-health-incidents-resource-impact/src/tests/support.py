"""Permanently SIMULATED native-shaped fixtures. Never a live fallback."""

import copy
import csv
import importlib.util
import io
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit


CASE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("case05_engine", CASE / "engine.py")
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)
tool.HTML_TEMPLATE = (CASE / "report_template.html").read_text(encoding="utf-8")

REFERENCE = datetime(2026, 10, 14, 18, 40, tzinfo=timezone.utc)
CONFIG = {
    "subscription_id": "11111111-1111-4111-8111-111111111111",
    "tenant_id": "22222222-2222-4222-8222-222222222222",
    "client_id": "33333333-3333-4333-8333-333333333333",
    "client_name": "Customer",
}
BIG_INTEGER = 900719925474099312345678901234567890
PREFIX = "/subscriptions/" + CONFIG["subscription_id"] + "/providers/Microsoft.ResourceHealth/events/"
ATTACK = '</script><img src=x onerror="window.SOURCE_EXECUTED=true"><script>window.SOURCE_EXECUTED=true</script>'


def params(**kwargs):
    values = {
        "operation": "report", "period": "auto", "start_utc": "", "end_utc": "", "view": "summary",
        "event_type": "all", "state": "all", "time_scope": "all", "search": "", "limit": 10, "offset": 0,
    }
    values.update(kwargs)
    return tool.parameters(**values, reference=REFERENCE)


def event(name, kind="ServiceIssue", **properties):
    props = {
        "eventType": kind, "eventSource": "ServiceHealth", "isEventSensitive": False,
        "status": "Active", "eventLevel": "Warning", "title": "SIMULATED communication " + name,
        "summary": "SIMULATED: published potential impact; not a real Azure incident.",
        "description": "SIMULATED source text only. No workload outage was measured.",
        "impactStartTime": "2026-09-05T12:00:00Z", "lastUpdateTime": "2026-09-10T13:00:00Z",
        "impact": [{"impactedService": "Virtual Machines", "impactedRegions": [{"impactedRegion": "West Europe", "status": "Active"}]}],
        "unknownFutureField": {"large_integer": BIG_INTEGER, "null": None, "bool": False, "array": [0, "", {"x": "SIMULATED"}]},
        "fixtureProvenance": "SIMULATED",
    }
    props.update(properties)
    return {"id": PREFIX + name, "name": name, "type": "Microsoft.ResourceHealth/events", "location": "global", "properties": props}


def resource(tracking, name, with_target=True):
    props = {"targetRegion": "West Europe", "fixtureProvenance": "SIMULATED", "unknownField": BIG_INTEGER}
    if with_target:
        props.update({
            "targetResourceId": "/subscriptions/" + CONFIG["subscription_id"] + "/resourceGroups/rg-simulated/providers/Microsoft.Compute/virtualMachines/vm-simulated-" + name,
            "targetResourceType": "Microsoft.Compute/virtualMachines",
        })
    else:
        props["info"] = [{"key": "SyntheticMetadata", "value": "No targetResourceId supplied"}, {"key": "BigFixtureValue", "value": BIG_INTEGER}]
    return {"id": PREFIX + tracking + "/impactedResources/" + name, "name": name, "type": "Microsoft.ResourceHealth/events/impactedResources", "properties": props}


def reply(payload, status=200, observed="2026-10-14T18:40:05Z"):
    return {
        "http_status": status, "payload": copy.deepcopy(payload), "observed_at_utc": observed,
        "attempts": [{"started_at_utc": "2026-10-14T18:40:01Z", "finished_at_utc": observed, "http_status": status, "fixture_provenance": "SIMULATED"}],
    }


class FakeReader:
    def __init__(self, config=CONFIG, request_params=None, extra_events=0):
        self.config = config
        self.params = request_params or params()
        self.responses = {}
        self.calls = []
        self.closed = False
        start = self.params["source_query_start_utc"]
        event_url = tool.events_url(config, start)
        second_page = event_url + "&" + urlencode({"$skipToken": "SIMULATED-page-2"})
        self.event_url, self.second_page = event_url, second_page
        old = event("SIM-OLD-001", impactStartTime="2020-01-01T00:00:00Z", lastUpdateTime="2026-08-10T00:00:00Z", title="SIMULATED: long-running provider incident")
        resolved = event("SIM-RESOLVED-002", status="Resolved", impactMitigationTime="2026-09-06T15:00:00Z", title="SIMULATED: resolved provider communication")
        missing = event("SIM-UNKNOWN-003", status=None, impactStartTime=None, lastUpdateTime="not-a-time", impact=None, title="SIMULATED: incomplete source metadata " + ATTACK)
        future = event("SIM-MAINT-004", "PlannedMaintenance", impactStartTime="2026-11-01T03:00:00Z", lastUpdateTime="2026-09-21T10:00:00Z", title="SIMULATED: future platform maintenance", impactMitigationTime=None)
        recent = event("SIM-MAINT-005", "PlannedMaintenance", status="Resolved", impactStartTime="2026-10-14T06:00:00Z", impactMitigationTime="2026-10-14T07:00:00Z", lastUpdateTime="2026-10-14T12:00:00Z", title="SIMULATED: recently updated maintenance")
        more = [event("SIM-EXTRA-" + str(index), title="SIMULATED review record " + str(index)) for index in range(extra_events)]
        excluded_health = event("SIM-OUTSCOPE-HEALTH", "HealthAdvisory", description="EXCLUDED_ADVISORY_BODY_MUST_NOT_EXPORT")
        excluded_security = event("SIM-OUTSCOPE-SECURITY", "SecurityAdvisory", description="EXCLUDED_SECURITY_BODY_MUST_NOT_EXPORT")
        self.responses[event_url] = reply({"value": [old, resolved, future, recent, *more, excluded_health], "nextLink": second_page, "providerExtension": {"complete_extra_field": BIG_INTEGER}})
        self.responses[second_page] = reply({"value": [missing, excluded_security], "opaqueSourceMetadata": [None, False, 0]})
        self.responses[tool.resources_url(config, old["name"])] = reply({"value": [resource(old["name"], "simulated-vm-a")]})
        self.responses[tool.resources_url(config, resolved["name"])] = reply({"value": []})
        self.responses[tool.resources_url(config, missing["name"])] = reply({"error": {"code": "SyntheticAuthorizationFailed", "message": "SIMULATED denied source, not zero resources."}}, 403)
        maintenance_resources = tool.resources_url(config, future["name"])
        resource_page2 = maintenance_resources + "&" + urlencode({"$skipToken": "SIMULATED-resource-2"})
        self.responses[maintenance_resources] = reply({"value": [resource(future["name"], "simulated-vm-b")], "nextLink": resource_page2})
        self.responses[resource_page2] = reply({"value": [resource(future["name"], "simulated-metadata", with_target=False)], "unknownPageField": {"allFields": True}})
        self.responses[tool.resources_url(config, recent["name"])] = reply({"error": {"code": "SyntheticNotFound", "message": "SIMULATED source unavailable."}}, 404)
        for row in more:
            self.responses[tool.resources_url(config, row["name"])] = reply({"value": []})

    def get(self, url, source):
        tool.validate_request(url, self.config)
        self.calls.append((url, source))
        if url not in self.responses:
            raise AssertionError("Unexpected offline request: " + url)
        result = self.responses[url]
        if isinstance(result, tool.EvidenceError):
            raise result
        return copy.deepcopy(result)

    def close(self):
        self.closed = True


def snapshot(reader=None, request_params=None):
    request_params = request_params or params()
    return tool.collect(reader or FakeReader(request_params=request_params), CONFIG, request_params, REFERENCE, provenance="SIMULATED")


def empty_snapshot():
    reader = FakeReader()
    reader.responses = {reader.event_url: reply({"value": []})}
    return snapshot(reader)


def large_retained_snapshot():
    reader = FakeReader()
    for url in (reader.event_url, reader.second_page):
        for raw in reader.responses[url]["payload"]["value"]:
            if raw["properties"]["eventType"] in tool.EVENT_TYPES:
                raw["properties"]["unknownFutureField"]["large_text"] = (
                    "SIMULATED complete retained-source field; no event or field may be dropped.\n"
                    * 4_500
                )
    return snapshot(reader)


def csv_records(text):
    previous = csv.field_size_limit()
    try:
        csv.field_size_limit(tool.ARTIFACT_BYTES)
        return list(csv.DictReader(io.StringIO(text)))
    finally:
        csv.field_size_limit(previous)


def event_by_name(document, name):
    return next(row for row in document["events"] if row["tracking_id"] == name)

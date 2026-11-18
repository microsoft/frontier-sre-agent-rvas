"""Explicit opt-in private source replay/budget check. Never authenticates or calls Azure."""

import argparse
import copy
import hashlib
import io
import json
import os
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlencode, urlsplit

from support import tool


class PrivateReplayReader:
    def __init__(self, document, config):
        self.config = config
        self.recorded = []
        for source in document["sources"]:
            if source.get("method") != "GET" or source.get("http") != 200:
                continue
            parameters = source.get("parameters", {})
            path = urlsplit(source["path"]).path
            if "$filter" in parameters:
                continue
            self.recorded.append((path, parameters, source))

    def get(self, url, source_id):
        tool.validate_request(url, self.config)
        parsed = urlsplit(url)
        query = {key: values[0] for key, values in parse_qs(parsed.query).items()}
        for path, parameters, source in self.recorded:
            if parsed.path == path and query == parameters:
                return {
                    "http_status": source["http"], "payload": copy.deepcopy(source["body"]),
                    "observed_at_utc": source["completed_utc"],
                    "attempts": [{
                        "http_status": source["http"], "started_at_utc": source["requested_utc"],
                        "finished_at_utc": source["completed_utc"], "provenance": "PRIVATE_REPLAY",
                        "first_page_probe_only": bool(source.get("first_page_only", True)),
                        "request_parameters": copy.deepcopy(parameters),
                    }],
                }
        raise tool.EvidenceError("not_collected_in_replay", "No receipt for this request exists in the private replay; no fresh source read was attempted.", source_id)


def replay(document):
    reference = tool.parse_utc(document["reference_utc"], "private replay reference")
    config = {
        "subscription_id": tool.configured_guid(document["subscription_id"], "private replay subscription"),
        "tenant_id": document["identity"]["tid"], "client_id": "not_authenticated_in_private_replay",
        "client_name": "Customer",
    }
    event_path = "/subscriptions/" + config["subscription_id"] + "/providers/Microsoft.ResourceHealth/events"
    original = next(source for source in document["sources"] if source.get("http") == 200 and urlsplit(source["path"]).path == event_path and "$filter" not in source.get("parameters", {}))
    request_params = tool.parameters(
        "report", "previous_month", "", "", "summary", "all", "all", "all", "", 10, 0, reference,
    )
    request_params["source_query_start_utc"] = tool.iso(tool.parse_utc(original["parameters"]["queryStartTime"], "recorded queryStartTime"))
    result = tool.collect(PrivateReplayReader(document, config), config, request_params, reference, provenance="PRIVATE_REPLAY")
    result["replay_context"] = {
        "fresh_live_validation": False, "identity_reauthenticated": False,
        "input_first_page_probe_only": bool(document.get("first_page_probe_not_complete_collection", True)),
        "notice": "Recorded source evidence only. Missing per-event receipts are Not collected, not fabricated empty reads.",
        "rejected_query_controls": [{
            "http_status": source["http"], "code": source.get("body", {}).get("code"),
            "parameters": source.get("parameters", {}),
        } for source in document["sources"] if source.get("http") != 200],
    }
    eligible = [
        row for row in original["body"]["value"]
        if isinstance(row, dict) and isinstance(row.get("properties"), dict)
        and row["properties"].get("eventType") in tool.EVENT_TYPES
    ]
    actual = [tool.source_record(result, row["source_ref"]) for row in result["events"]]
    if actual != eligible:
        raise AssertionError("Private replay did not preserve every in-scope original record/field.")
    return result, {
        "provenance": "PRIVATE_REPLAY", "fresh_live_validation": False,
        "original_event_rows": len(original["body"]["value"]),
        "in_scope_events": len(actual), "all_in_scope_record_field_parity": True,
        "excluded_category_records": result["coverage"]["excluded_category_records"],
        "excluded_event_types": result["sources"][0]["excluded_event_types"],
        "recorded_resource_sources": sum(source["kind"] == "impactedResources" and source["status"] != "not_collected" for source in result["sources"]),
        "uncollected_resource_sources": sum(source["status"] == "not_collected" for source in result["sources"]),
    }


def worst_case_test_logo():
    from PIL import Image
    image = io.BytesIO()
    Image.new("RGB", (100, 40), "#fbc807").save(image, format="PNG")
    data = image.getvalue()
    data += b"\0" * (100_000 - len(data))
    return "data:image/png;base64," + tool.base64.b64encode(data).decode("ascii")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="Explicit private source-receipt JSON. Never bundled or auto-discovered.")
    parser.add_argument("--output", type=Path, help="Optional existing private scratch folder for replay-only artifacts.")
    args = parser.parse_args()
    input_bytes = args.input.read_bytes()
    document = tool.decode_json(input_bytes)
    result, report = replay(document)
    result["replay_context"]["input_sha256"] = hashlib.sha256(input_bytes).hexdigest()
    files = tool.prepare_artifacts(result, tool.logo_markup())
    report["artifact_bytes"] = {key: len(value) for key, value in files.items()}
    with patch.object(tool, "COMPANY_LOGO_DATA_URI", worst_case_test_logo()):
        worst = tool.prepare_artifacts(result, tool.logo_markup())
    report["with_100000_byte_test_logo_artifact_bytes"] = {key: len(value) for key, value in worst.items()}
    report["plain_artifact_limit_bytes"] = tool.ARTIFACT_BYTES
    if args.output:
        root = args.output.resolve(strict=True)
        if not root.is_dir():
            parser.error("--output must be an existing private directory.")
        previous = Path.cwd()
        try:
            os.chdir(root)
            report["replay_only_artifacts"] = tool.write_report(result, tool.logo_markup())
        finally:
            os.chdir(previous)
    print(json.dumps(report))


if __name__ == "__main__":
    main()

"""Focused offline source, temporal, output, identity and runtime-contract tests."""

import ast
import base64
import copy
import csv
import importlib.util
import inspect
import io
import json
import os
import re
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from types import ModuleType
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlsplit

from support import ATTACK, BIG_INTEGER, CASE, CONFIG, FakeReader, PREFIX, REFERENCE, csv_records, empty_snapshot, event, event_by_name, large_retained_snapshot, params, reply, resource, snapshot, tool


class SourceContractTests(unittest.TestCase):
    def test_native_shapes_all_fields_and_pages_are_retained(self):
        reader = FakeReader()
        document = snapshot(reader)
        self.assertEqual(document["provenance"], "SIMULATED")
        self.assertEqual(len(document["events"]), 5)
        self.assertEqual(len(document["impacted_resources"]), 3)
        source = document["sources"][0]
        self.assertEqual(len(source["pages"]), 2)
        self.assertEqual(source["status"], "complete")
        self.assertTrue(source["pagination_complete"])
        for url, page in ((reader.event_url, source["pages"][0]), (reader.second_page, source["pages"][1])):
            expected = copy.deepcopy(reader.responses[url]["payload"])
            expected["value"] = [row for row in expected["value"] if row["properties"]["eventType"] in tool.EVENT_TYPES]
            self.assertEqual(page["response"], expected)
        self.assertEqual(source["records_received"], 7)
        self.assertEqual(source["records_accepted"], 5)
        self.assertEqual(source["records_excluded_by_scope"], 2)
        self.assertEqual(source["excluded_event_types"], {"HealthAdvisory": 1, "SecurityAdvisory": 1})
        self.assertNotIn("EXCLUDED_ADVISORY_BODY", tool.json_text(document))
        self.assertNotIn("EXCLUDED_SECURITY_BODY", tool.json_text(document))
        self.assertEqual(source["pages"][0]["response"]["providerExtension"]["complete_extra_field"], BIG_INTEGER)
        for row in document["events"]:
            raw = tool.source_record(document, row["source_ref"])
            self.assertEqual(raw["properties"]["unknownFutureField"]["large_integer"], BIG_INTEGER)
            self.assertEqual(row["support_case_reference"], "not_collected")
            self.assertEqual(row["newness"], "not_established")
        missing_target = next(row for row in document["impacted_resources"] if row["target_resource_id"] is None)
        self.assertIn("no targetResourceId", missing_target["uncertainties"][0])
        self.assertEqual(tool.source_record(document, missing_target["source_ref"])["properties"]["info"][1]["value"], BIG_INTEGER)

    def test_explicit_retained_lower_bound_not_impact_start_filter(self):
        reader = FakeReader()
        document = snapshot(reader)
        expected = tool.iso(REFERENCE - timedelta(days=365))
        self.assertEqual(document["source_query"]["query_start_utc"], expected)
        for source in [row for row in document["sources"] if row["kind"] == "events"]:
            query = parse_qs(urlsplit(source["initial_request_url"]).query)
            self.assertEqual(query["queryStartTime"], [expected])
            self.assertEqual(query["api-version"], ["2025-05-01"])
            self.assertNotIn("$filter", query)
            self.assertEqual(source["included_event_types"], ["ServiceIssue", "PlannedMaintenance"])
        old = event_by_name(document, "SIM-OLD-001")
        self.assertTrue(old["temporal"]["active_now"])
        self.assertFalse(old["temporal"]["requested_updates"])
        self.assertEqual(old["impact_start_original"], "2020-01-01T00:00:00Z")
        self.assertEqual(document["coverage"]["historical_completeness"], "not_proven")

    def test_empty_missing_denied_unavailable_and_partial_are_distinct(self):
        empty = empty_snapshot()
        self.assertTrue(empty["coverage"]["event_source_successful_empty"])
        self.assertEqual([item["status"] for item in empty["sources"]], ["successful_empty"])
        self.assertEqual(empty["coverage"]["workload_outages"], "not_measured")
        for payload, status, expected in (({}, 200, "unavailable"), ({"error": {"code": "Forbidden"}}, 403, "denied"), ({"error": {"code": "NotFound"}}, 404, "unavailable")):
            with self.subTest(status=status, payload=payload):
                reader = FakeReader()
                reader.responses[reader.event_url] = reply(payload, status)
                document = snapshot(reader)
                self.assertEqual(document["sources"][0]["status"], expected)
                self.assertEqual(document["coverage"]["status"], "partial")
                self.assertFalse(document["coverage"]["event_source_successful_empty"])
        reader = FakeReader()
        reader.responses[reader.second_page] = reply({"error": {"code": "Forbidden"}}, 403)
        document = snapshot(reader)
        source = document["sources"][0]
        self.assertEqual(source["status"], "partial")
        self.assertEqual(source["records_accepted"], 4)
        self.assertEqual(len(source["pages"]), 2)
        self.assertEqual(source["pages"][1]["http_status"], 403)
        self.assertEqual(source["pages"][1]["response"]["error"]["code"], "Forbidden")
        self.assertFalse(source["pagination_complete"])

    def test_impacted_resource_denial_is_unknown_not_zero(self):
        document = snapshot()
        missing = event_by_name(document, "SIM-UNKNOWN-003")
        self.assertIsNone(missing["resource_records"])
        self.assertEqual(missing["resource_source_status"], "denied")
        self.assertEqual(missing["resource_records_observed"], 0)
        self.assertEqual(next(row for row in document["sources"] if row["source_id"] == missing["resource_source_id"])["status"], "denied")
        resolved = event_by_name(document, "SIM-RESOLVED-002")
        self.assertEqual(resolved["resource_records"], 0)
        self.assertEqual(next(row for row in document["sources"] if row["source_id"] == resolved["resource_source_id"])["status"], "successful_empty")

    def test_declared_category_exclusion_is_not_truncation_or_native_empty(self):
        reader = FakeReader()
        reader.responses = {reader.event_url: reply({"value": [event("SIM-ONLY-ADVISORY", "HealthAdvisory", description="DO_NOT_EXPORT_ADVISORY_BODY")]})}
        document = snapshot(reader)
        self.assertEqual(document["sources"][0]["status"], "successful_empty_in_scope")
        self.assertEqual(document["sources"][0]["records_received"], 1)
        self.assertEqual(document["sources"][0]["records_accepted"], 0)
        self.assertEqual(document["coverage"]["excluded_category_records"], 1)
        self.assertEqual(document["coverage"]["status"], "complete_returned_pages")
        self.assertNotIn("DO_NOT_EXPORT_ADVISORY_BODY", tool.json_text(document))
        self.assertTrue(document["coverage"]["event_source_successful_empty"])

    def test_unsafe_nextlinks_never_reach_reader(self):
        reader = FakeReader()
        original = reader.event_url
        query = urlsplit(original).query
        path = urlsplit(original).path
        invalid = [
            "http://management.azure.com" + path + "?" + query,
            "https://evil.invalid" + path + "?" + query,
            "https://management.azure.com:443" + path + "?" + query,
            "https://user@management.azure.com" + path + "?" + query,
            original + "#fragment", original.replace(CONFIG["subscription_id"], CONFIG["tenant_id"]),
            original.replace("/events?", "/events/../events?"), original.replace("/events?", "/%65vents?"),
            original + "&$filter=eventType%20eq%20%27SecurityAdvisory%27",
            original.replace("2025-05-01", "2022-10-01"),
            original + "&$filter=eventType%20eq%20%27ServiceIssue%27",
            original + "&API-VERSION=2025-05-01", original + "&$top=1",
            original.replace("queryStartTime=", "unapprovedStartTime="),
            original + "&$skipToken=", original + "&$skipToken=x&skipToken=y",
            original.replace("/subscriptions/", "/tenants/"), None, {}, "",
        ]
        for link in invalid:
            with self.subTest(link=link):
                attempt = FakeReader()
                attempt.responses[attempt.event_url]["payload"]["nextLink"] = link
                if link in (None, ""):
                    continue
                document = snapshot(attempt)
                source = document["sources"][0]
                self.assertEqual(source["status"], "partial")
                self.assertEqual(len(source["pages"]), 1)
                self.assertTrue(source["errors"])
                self.assertNotIn(link, [url for url, _ in attempt.calls])

    def test_loop_and_duplicate_ids_are_partial_without_dropping_records(self):
        reader = FakeReader()
        reader.responses[reader.second_page]["payload"]["nextLink"] = reader.event_url
        document = snapshot(reader)
        self.assertEqual(document["sources"][0]["status"], "partial")
        self.assertEqual(document["sources"][0]["errors"][0]["code"], "pagination_loop")
        reader = FakeReader()
        duplicate = copy.deepcopy(reader.responses[reader.event_url]["payload"]["value"][0])
        reader.responses[reader.second_page]["payload"]["value"].append(duplicate)
        document = snapshot(reader)
        self.assertEqual(document["sources"][0]["duplicate_native_ids"], 1)
        self.assertEqual(document["sources"][0]["records_accepted"], 6)
        self.assertEqual(len([row for row in document["events"] if row["tracking_id"] == "SIM-OLD-001"]), 2)
        self.assertEqual(document["sources"][0]["status"], "partial")

    def test_official_and_observed_provider_relative_ids_keep_request_scope(self):
        for form in ("/providers/Microsoft.ResourceHealth/events/", "Microsoft.ResourceHealth/events/"):
            reader = FakeReader()
            for url in (reader.event_url, reader.second_page):
                for raw in reader.responses[url]["payload"]["value"]:
                    if raw["properties"]["eventType"] in tool.EVENT_TYPES:
                        raw["id"] = form + raw["name"]
            document = snapshot(reader)
            self.assertEqual(document["sources"][0]["status"], "complete")
            self.assertEqual(len(document["events"]), 5)
            self.assertTrue(all(row["id"].startswith(form) for row in document["events"]))
            self.assertEqual(document["sources"][0]["subscription_id"], CONFIG["subscription_id"])

    def test_documented_continuation_omission_restores_the_explicit_lower_bound(self):
        reader = FakeReader()
        short_link = reader.event_url.split("&queryStartTime=")[0] + "&$skipToken=SIMULATED-page-2"
        reader.responses[reader.event_url]["payload"]["nextLink"] = short_link
        canonical = tool.next_link(short_link, reader.event_url, CONFIG)
        reader.responses[canonical] = reader.responses[reader.second_page]
        document = snapshot(reader)
        source = document["sources"][0]
        self.assertEqual(source["status"], "complete")
        self.assertTrue(source["pages"][0]["continuation_query_start_restored"])
        self.assertEqual(source["pages"][0]["response"]["nextLink"], short_link)
        self.assertEqual(parse_qs(urlsplit(source["pages"][1]["request_url"]).query)["queryStartTime"], [params()["source_query_start_utc"]])

    def test_explicit_partial_error_preserves_returned_records_and_extra_fields(self):
        reader = FakeReader()
        reader.responses[reader.event_url]["payload"]["error"] = {"code": "SyntheticPartial", "extension": {"raw": BIG_INTEGER}}
        document = snapshot(reader)
        source = document["sources"][0]
        self.assertEqual(source["records_accepted"], 4)
        self.assertEqual(source["pages"][0]["response"]["error"]["extension"]["raw"], BIG_INTEGER)
        self.assertEqual(source["errors"][0]["code"], "partial_response")

    def test_page_and_record_caps_disclose_partial_and_retain_received_page(self):
        for bound, value, expected in (("MAX_PAGES", 1, "source_page_bound"), ("MAX_EVENT_RECORDS", 1, "source_record_bound")):
            with self.subTest(bound=bound), patch.object(tool, bound, value):
                document = snapshot()
                source = document["sources"][0]
                self.assertEqual(source["status"], "partial")
                self.assertEqual(source["records_accepted"], 4)
                self.assertEqual(len(source["pages"][0]["response"]["value"]), 4)
                self.assertEqual(source["errors"][0]["code"], expected)

    def test_unexpected_sensitive_category_and_cross_scope_are_redacted_explicitly(self):
        for mutate in ("sensitive", "subscription", "missing_type"):
            reader = FakeReader()
            raw = event("SIM-REDACTED-999", description="MUST_NOT_EXPORT_SYNTHETIC_REDACTED_CONTENT")
            if mutate == "sensitive":
                raw["properties"]["isEventSensitive"] = True
            elif mutate == "subscription":
                raw["id"] = raw["id"].replace(CONFIG["subscription_id"], CONFIG["tenant_id"])
            else:
                del raw["properties"]["eventType"]
            reader.responses[reader.event_url]["payload"]["value"].append(raw)
            document = snapshot(reader)
            self.assertNotIn("MUST_NOT_EXPORT", tool.json_text(document))
            source = document["sources"][0]
            self.assertEqual(source["status"], "partial")
            self.assertEqual(len(source["redactions"]), 1)
            self.assertEqual(source["records_received"], 8)
            self.assertEqual(source["records_accepted"], 5)
            self.assertEqual(document["coverage"]["redacted_records"], 1)

    def test_target_outside_subscription_is_not_exported(self):
        reader = FakeReader()
        url = tool.resources_url(CONFIG, "SIM-OLD-001")
        reader.responses[url]["payload"]["value"][0]["properties"]["targetResourceId"] = "/subscriptions/" + CONFIG["tenant_id"] + "/resourceGroups/do-not-export"
        document = snapshot(reader)
        source = next(item for item in document["sources"] if item["source_id"] == "resources:SIM-OLD-001")
        self.assertEqual(source["status"], "unavailable")
        self.assertNotIn("do-not-export", tool.json_text(document))
        self.assertEqual(source["redactions"][0]["record_index"], 0)

    def test_expected_transport_failure_keeps_attempt_and_partial_pages(self):
        reader = FakeReader()
        reader.responses[reader.second_page] = tool.EvidenceError("transport_failed", "Synthetic transport failure.", "events:subscription", receipt={"attempts": [{"http_status": None, "code": "transport_failed"}]})
        document = snapshot(reader)
        source = document["sources"][0]
        self.assertEqual(source["status"], "partial")
        self.assertEqual(source["pages"][1]["attempts"][0]["code"], "transport_failed")
        self.assertEqual(source["records_accepted"], 4)

    def test_shared_accepted_evidence_budget_fails_without_data_dropping(self):
        reader = FakeReader()
        reader.responses[reader.event_url]["payload"]["value"][0]["properties"]["description"] = "x" * 4_800_001
        with self.assertRaises(tool.EvidenceError) as raised:
            snapshot(reader)
        self.assertEqual(raised.exception.code, "collected_evidence_too_large")
        self.assertEqual(len(reader.calls), 1)
        reader = FakeReader()
        excluded = reader.responses[reader.event_url]["payload"]["value"][-1]
        self.assertEqual(excluded["properties"]["eventType"], "HealthAdvisory")
        excluded["properties"]["description"] = "x" * 4_800_001
        document = snapshot(reader)
        self.assertEqual(len(document["events"]), 5)
        self.assertEqual(document["sources"][0]["records_excluded_by_scope"], 2)
        self.assertNotIn("x" * 100, tool.json_text(document))


class TemporalAndParameterTests(unittest.TestCase):
    def test_previous_month_and_recent_auto_windows(self):
        report = params()
        self.assertEqual(report["window"]["start_utc"], "2026-09-01T00:00:00Z")
        self.assertEqual(report["window"]["end_utc_exclusive"], "2026-10-01T00:00:00Z")
        recent = params(operation="query")
        self.assertEqual(recent["window"]["start_utc"], "2026-10-13T18:40:00Z")
        self.assertEqual(recent["window"]["basis"], "lastUpdateTime")
        leap_reference = datetime(2024, 3, 1, tzinfo=timezone.utc)
        arguments = dict(operation="report", period="previous_month", start_utc="", end_utc="", view="summary", event_type="all", state="all", time_scope="all", search="", limit=10, offset=0, reference=leap_reference)
        leap = tool.parameters(**arguments)
        self.assertEqual(leap["window"]["start_utc"], "2024-02-01T00:00:00Z")
        self.assertEqual(leap["window"]["end_utc_exclusive"], "2024-03-01T00:00:00Z")

    def test_exact_half_open_update_and_future_boundaries(self):
        request = params()
        source_ref = {"source_id": "synthetic", "page": 1, "record_index": 0, "observed_at_utc": tool.iso(REFERENCE)}
        for timestamp, expected in (("2026-09-01T00:00:00Z", True), ("2026-10-01T00:00:00Z", False), ("2026-08-31T23:59:59Z", False), ("2026-09-30T23:59:59Z", True), ("invalid", False), (None, False)):
            with self.subTest(timestamp=timestamp):
                row = tool.normalize_event(event("SIM-BOUND", lastUpdateTime=timestamp), source_ref, request, REFERENCE, "e")
                self.assertEqual(row["temporal"]["requested_updates"], expected)
                self.assertEqual(row["last_update_original"], timestamp)
                self.assertEqual(row["newness"], "not_established")
        for delta, status, expected in ((0, "Active", False), (1, "Active", True), (1, "Resolved", False), (1, None, True)):
            row = tool.normalize_event(event("SIM-BOUND", "PlannedMaintenance", impactStartTime=tool.iso(REFERENCE + timedelta(seconds=delta)), status=status), source_ref, request, REFERENCE, "e")
            self.assertEqual(row["temporal"]["future_maintenance"], expected)

    def test_temporal_lanes_overlap_but_not_newness_or_support_case(self):
        document = snapshot()
        future = event_by_name(document, "SIM-MAINT-004")
        self.assertEqual(future["temporal"], {"requested_updates": True, "active_now": True, "future_maintenance": True})
        missing = event_by_name(document, "SIM-UNKNOWN-003")
        self.assertEqual(missing["native_status"], "Unknown")
        self.assertFalse(any(missing["temporal"].values()))
        self.assertEqual(document["coverage"]["current_state_as_of_history"], "not_reconstructed")
        self.assertEqual(document["coverage"]["support_cases"], "not_collected")

    def test_fractional_source_times_are_compared_losslessly(self):
        request = params(period="custom", start_utc="2026-09-01T00:00:00.123456Z", end_utc="2026-09-01T00:00:00.123457Z")
        self.assertEqual(request["window"]["start_utc"], "2026-09-01T00:00:00.123456Z")
        source_ref = {"source_id": "synthetic", "page": 1, "record_index": 0, "observed_at_utc": tool.iso(REFERENCE)}
        for timestamp, expected in (("2026-09-01T00:00:00.1234559Z", False), ("2026-09-01T00:00:00.1234560Z", True), ("2026-09-01T00:00:00.1234569Z", True), ("2026-09-01T00:00:00.1234570Z", False)):
            row = tool.normalize_event(event("SIM-FRACTION", lastUpdateTime=timestamp), source_ref, request, REFERENCE, "e")
            self.assertEqual(row["temporal"]["requested_updates"], expected)
        future = tool.normalize_event(event("SIM-FUTURE", "PlannedMaintenance", impactStartTime="2026-10-14T18:40:00.0000001Z"), source_ref, request, REFERENCE, "e")
        self.assertTrue(future["temporal"]["future_maintenance"])
        self.assertEqual(future["impact_start_utc"], "2026-10-14T18:40:00.0000001Z")
        self.assertEqual(tool.source_utc_display("2026-09-01T01:00:00.1234567+01:00"), "2026-09-01T00:00:00.1234567Z")
        with self.assertRaises(tool.EvidenceError):
            params(period="custom", start_utc="2026-09-01T00:00:00.1234567Z", end_utc="2026-09-01T00:00:01Z")

    def test_active_status_does_not_override_source_mitigation_or_inconsistent_dates(self):
        source_ref = {"source_id": "synthetic", "page": 1, "record_index": 0, "observed_at_utc": tool.iso(REFERENCE)}
        row = tool.normalize_event(event("SIM-ACTIVE-MITIGATED", "PlannedMaintenance", status="Active", impactStartTime="2026-09-01T00:00:00Z", impactMitigationTime="2026-09-02T00:00:00Z"), source_ref, params(), REFERENCE, "e")
        self.assertTrue(row["temporal"]["active_now"])
        self.assertFalse(row["temporal"]["future_maintenance"])
        self.assertEqual(row["published_timing"], "source_mitigation_at_or_before_reference")
        self.assertTrue(any("ongoing impact is not established" in item for item in row["uncertainties"]))
        row = tool.normalize_event(event("SIM-BAD-DATES", "PlannedMaintenance", impactStartTime="2026-11-01T00:00:00Z", impactMitigationTime="2026-09-01T00:00:00Z"), source_ref, params(), REFERENCE, "e")
        self.assertEqual(row["published_timing"], "inconsistent_source_dates")
        self.assertFalse(row["temporal"]["future_maintenance"])

    def test_bad_parameters_rejected_before_authentication(self):
        bad = [
            {"limit": True}, {"limit": 1.0}, {"limit": 0}, {"limit": 51}, {"offset": True}, {"offset": -1}, {"offset": 10001},
            {"operation": "write"}, {"period": "next_month"}, {"view": "tickets"}, {"event_type": "SecurityAdvisory"},
            {"state": "Healthy"}, {"time_scope": "new"}, {"search": "x"}, {"limit": 5}, {"view": "events"},
            {"start_utc": "2026-09-01T00:00:00Z"}, {"search": "\n"}, {"period": "custom", "start_utc": "2026-09-01", "end_utc": "2026-10-01"},
            {"period": "custom", "start_utc": "2026-09-01T00:00:00+01:00", "end_utc": "2026-10-01T00:00:00Z"},
            {"period": "custom", "start_utc": "2026-10-15T00:00:00Z", "end_utc": "2026-10-16T00:00:00Z"},
            {"period": "custom", "start_utc": "2026-01-01T00:00:00Z", "end_utc": "2026-10-01T00:00:00Z"},
            {"period": "custom", "start_utc": "2025-01-01T00:00:00Z", "end_utc": "2025-02-01T00:00:00Z"},
        ]
        for values in bad:
            with self.subTest(values=values), patch.object(tool, "NativeReader") as reader:
                response = tool.main(**values)
                self.assertEqual(response["status"], "error")
                reader.assert_not_called()
        with self.assertRaises(tool.EvidenceError):
            params(operation="query", view="coverage", event_type="ServiceIssue")
        custom = params(period="custom", start_utc="2026-09-01T00:00:00+00:00", end_utc="2026-09-01T00:00:01Z")
        self.assertEqual(custom["window"]["start_utc"], "2026-09-01T00:00:00Z")

    def test_schema_and_python_signature_match_runtime_int(self):
        schema = json.loads((CASE / "tool-parameters.schema.json").read_text(encoding="utf-8"))
        signature = inspect.signature(tool.main)
        self.assertEqual(set(signature.parameters), set(schema["properties"]))
        for name, parameter in signature.parameters.items():
            prop = schema["properties"][name]
            self.assertEqual(parameter.default, prop["default"])
            self.assertEqual(prop["type"], "int" if parameter.annotation is int else "string")
        self.assertFalse(schema["additionalProperties"])
        self.assertNotIn('"integer"', json.dumps(schema))


class QueryTests(unittest.TestCase):
    def test_whole_projection_paging_and_local_filters(self):
        document = snapshot()
        request = params(operation="query", view="events", event_type="PlannedMaintenance", time_scope="future_maintenance", limit=5)
        response = tool.query_snapshot(document, request)
        self.assertEqual(response["total_matched"], 1)
        self.assertEqual(response["returned"], 1)
        self.assertEqual(response["rows"][0]["tracking_id"], "SIM-MAINT-004")
        self.assertFalse(response["has_more"])
        self.assertTrue(response["fresh_collection"])
        self.assertEqual(response["source_query_start_utc"], document["source_query"]["query_start_utc"])
        self.assertEqual(response["collection_observed_utc"], document["collection_observed_utc"])
        self.assertEqual(response["rows"][0]["resource_source_status"], "complete")
        request = params(operation="query", view="events", limit=1)
        response = tool.query_snapshot(document, request)
        self.assertEqual(response["total_matched"], 5)
        self.assertEqual(response["next_offset"], 1)
        self.assertTrue(response["has_more"])
        next_response = tool.query_snapshot(document, params(operation="query", view="events", limit=1, offset=1))
        self.assertNotEqual(response["rows"][0]["event_key"], next_response["rows"][0]["event_key"])
        resources = tool.query_snapshot(document, params(operation="query", view="resources", search="SIM-MAINT-004", limit=50))
        self.assertEqual(resources["total_matched"], 2)
        empty = tool.query_snapshot(document, params(operation="query", view="events", search="NO_MATCH_SYNTHETIC"))
        self.assertEqual(empty["returned"], 0)
        self.assertFalse(empty["has_more"])
        self.assertIsNone(empty["next_offset"])

    def test_transport_caps_whole_rows_and_never_zero_row_cursor(self):
        document = snapshot()
        response = tool.query_snapshot(document, params(operation="query", view="events", limit=50))
        self.assertLess(response["returned"], response["total_matched"])
        self.assertTrue(response["transport_capped"])
        self.assertLessEqual(tool.response_bytes(response), 3500)
        document["events"][0]["title"] = "x" * 4000
        with self.assertRaises(tool.EvidenceError) as raised:
            tool.query_snapshot(document, params(operation="query", view="events"))
        self.assertEqual(raised.exception.code, "query_row_too_large")

    def test_default_serialized_exact_utf8_response_boundary(self):
        base = {"value": ""}
        count = 3500 - len(json.dumps(base).encode("utf-8"))
        accepted = {"value": "x" * count}
        self.assertEqual(tool.response_bytes(tool.budget_response(accepted)), 3500)
        with self.assertRaises(tool.EvidenceError):
            tool.budget_response({"value": "x" * (count + 1)})
        unicode = {"value": "\u00e9" * 600}
        self.assertLess(len(json.dumps(unicode, ensure_ascii=False).encode("utf-8")), 3500)
        with self.assertRaises(tool.EvidenceError):
            tool.budget_response(unicode)


class ArtifactTests(unittest.TestCase):
    def test_large_retained_report_fits_without_repeating_or_removing_source_fields(self):
        document = large_retained_snapshot()
        original_json = (tool.json_text(document) + "\n").encode("utf-8")
        self.assertGreater(len(original_json), 1_500_000)
        self.assertLess(len(original_json), tool.ARTIFACT_BYTES)
        self.assertEqual(document["source_query"]["lookback_days"], 365)
        files = tool.prepare_artifacts(document, tool.logo_markup())
        self.assertEqual(files["snapshot_path"], original_json)
        self.assertTrue(all(len(value) <= tool.ARTIFACT_BYTES for value in files.values()))
        events = csv_records(files["events_csv_path"].decode("utf-8-sig"))
        self.assertEqual(len(events), len(document["events"]))
        for row, normalized in zip(events, document["events"]):
            self.assertEqual(json.loads(row["details_json"]), tool.complete_event(document, normalized))
        markup = files["report_path"].decode("utf-8")
        embedded = re.search(r'<script id="complete-json-bytes" type="application/octet-stream">([^<]+)</script>', markup)
        self.assertEqual(base64.b64decode(embedded[1]), original_json)

    def test_full_json_html_bytes_and_integer_field_parity(self):
        document = snapshot()
        files = tool.prepare_artifacts(document, tool.logo_markup())
        self.assertEqual(json.loads(files["snapshot_path"]), document)
        markup = files["report_path"].decode("utf-8")
        match = re.search(r'<script id="complete-json-bytes" type="application/octet-stream">([^<]+)</script>', markup)
        self.assertIsNotNone(match)
        self.assertEqual(base64.b64decode(match[1]), files["snapshot_path"])
        model_match = re.search(r'<script id="report-model" type="application/json">(.*?)</script>', markup, re.S)
        model = json.loads(model_match[1])
        row = model["events"][0]
        normalized = files["snapshot_path"][slice(*row["record_range"])]
        raw = files["snapshot_path"][slice(*row["source_record_range"])]
        complete = normalized[:-1] + b',"source_record":' + raw + b"}"
        self.assertEqual(complete, tool.json_text(tool.complete_event(document, document["events"][0])).encode("utf-8"))
        exported = json.loads(complete)
        self.assertEqual(exported["source_record"]["properties"]["unknownFutureField"]["large_integer"], BIG_INTEGER)
        self.assertEqual(len(row["csv_cells"]), len(tool.EVENT_CSV_FIELDS) - 1)
        self.assertNotIn("complete_json", row)
        self.assertNotIn("original_record_json", row)
        self.assertNotIn("detail_json", model["sources"][0])
        self.assertEqual(json.loads(files["snapshot_path"][slice(*model["sources"][0]["detail_range"])]), document["sources"][0])
        self.assertNotIn(ATTACK, markup)
        self.assertIn("\\u003c/script", markup)
        self.assertNotIn("new Blob", markup)
        self.assertNotIn("createObjectURL", markup)
        self.assertNotIn("http://", markup)
        self.assertIn("<span>Customer</span>", markup)
        self.assertIn("Customer logo", markup)
        for data in files.values():
            self.assertLessEqual(len(data), 4_800_000)

    def test_utf8_byte_references_preserve_astral_text_float_lexemes_and_unknown_fields(self):
        document = snapshot()
        document["events"][0]["title"] = "SIMULATED \U0001f30d \u00e9 quote \" slash \\"
        raw = tool.source_record(document, document["events"][0]["source_ref"])
        raw["properties"]["unknownFutureField"]["precision_cases"] = {
            "negative_integer": -BIG_INTEGER, "tiny_float": 1.0e-150, "integral_float": 1.0,
            "text": "\U0001f30d \u00e9 \\u1234 \" } [ ] { \n", "nested": [None, False, [], {}, {"__proto__": BIG_INTEGER}],
        }
        files = tool.prepare_artifacts(document, tool.logo_markup())
        markup = files["report_path"].decode("utf-8")
        model = json.loads(re.search(r'<script id="report-model" type="application/json">(.*?)</script>', markup, re.S)[1])
        record = model["events"][0]
        normalized = files["snapshot_path"][slice(*record["record_range"])]
        source = files["snapshot_path"][slice(*record["source_record_range"])]
        self.assertEqual(json.loads(normalized), document["events"][0])
        self.assertEqual(json.loads(source), raw)
        complete = normalized[:-1] + b',"source_record":' + source + b"}"
        self.assertEqual(complete, tool.json_text(tool.complete_event(document, document["events"][0])).encode("utf-8"))
        self.assertIn(b"1e-150", complete)
        self.assertIn(b'"integral_float":1.0', complete)

    def test_byte_reference_mapping_rejects_missing_paths_or_changed_export_bytes(self):
        document = empty_snapshot()
        payload = (tool.json_text(document) + "\n").encode("utf-8")
        with self.assertRaises(tool.EvidenceError) as raised:
            tool.json_byte_ranges(document, payload, {("does_not_exist",)})
        self.assertEqual(raised.exception.code, "json_reference_mismatch")
        with self.assertRaises(tool.EvidenceError) as raised:
            tool.json_byte_ranges(document, payload + b" ", {("sources", 0)})
        self.assertEqual(raised.exception.code, "json_reference_mismatch")
        span = tool.json_byte_ranges(document, payload, {("sources", 0)})[("sources", 0)]
        self.assertEqual(json.loads(payload[slice(*span)]), document["sources"][0])

    @unittest.skipUnless(os.environ.get("CASE05_PRIVATE_SNAPSHOT"), "Private full-model replay is explicit opt-in.")
    def test_actual_default_model_fits_with_maximum_logo_without_changing_json_or_csv_bytes(self):
        from private_replay import worst_case_test_logo
        original = Path(os.environ["CASE05_PRIVATE_SNAPSHOT"]).read_bytes()
        document = tool.decode_json(original)
        self.assertEqual(document["source_query"]["lookback_days"], 365)
        with patch.object(tool, "COMPANY_LOGO_DATA_URI", worst_case_test_logo()):
            files = tool.prepare_artifacts(document, tool.logo_markup())
        self.assertEqual(files["snapshot_path"], original)
        event_rows, resource_rows = tool.csv_rows(document)
        self.assertEqual(files["events_csv_path"], tool.csv_document(event_rows, tool.EVENT_CSV_FIELDS).encode("utf-8-sig"))
        self.assertEqual(files["resources_csv_path"], tool.csv_document(resource_rows, tool.RESOURCE_CSV_FIELDS).encode("utf-8-sig"))
        self.assertTrue(all(len(value) <= 4_800_000 for value in files.values()))
        markup = files["report_path"].decode("utf-8")
        encoded = re.search(r'<script id="complete-json-bytes" type="application/octet-stream">([^<]+)</script>', markup)[1]
        self.assertEqual(base64.b64decode(encoded), original)

    def test_ordinary_csv_retains_every_selected_record_and_raw_field(self):
        document = snapshot()
        document["events"][0]["title"] = "=SYNTHETIC_FORMULA()"
        files = tool.prepare_artifacts(document, tool.logo_markup())
        event_rows = list(csv.DictReader(io.StringIO(files["events_csv_path"].decode("utf-8-sig"))))
        resource_rows = list(csv.DictReader(io.StringIO(files["resources_csv_path"].decode("utf-8-sig"))))
        self.assertEqual(len(event_rows), len(document["events"]))
        self.assertEqual(len(resource_rows), len(document["impacted_resources"]))
        self.assertEqual(event_rows[0]["title"], "'=SYNTHETIC_FORMULA()")
        for row, normalized in zip(event_rows, document["events"]):
            self.assertEqual(json.loads(row["details_json"]), tool.complete_event(document, normalized))
            self.assertEqual(row["provenance"], "SIMULATED")
            self.assertEqual(row["subscription_id"], CONFIG["subscription_id"])
            self.assertEqual(row["api_version"], "2025-05-01")
        for row, normalized in zip(resource_rows, document["impacted_resources"]):
            self.assertEqual(json.loads(row["details_json"]), tool.complete_resource(document, normalized))
        for source in (" =1", "\tvalue", "\nvalue", "@SUM(1)", "-1+1"):
            self.assertTrue(tool.csv_cell(source).startswith("'"))

    def test_exact_artifact_budget_is_checked_before_directory_creation(self):
        document = empty_snapshot()
        with patch.object(tool, "render_html", return_value="x" * 4_800_000):
            self.assertEqual(len(tool.prepare_artifacts(document, "")["report_path"]), 4_800_000)
        old = Path.cwd()
        with tempfile.TemporaryDirectory() as temporary:
            try:
                os.chdir(temporary)
                with patch.object(tool, "render_html", return_value="x" * 4_800_001):
                    with self.assertRaises(tool.EvidenceError) as raised:
                        tool.write_report(document, "")
                self.assertEqual(raised.exception.code, "artifact_size_exceeded")
                self.assertFalse((Path(temporary) / tool.OUTPUT_DIRECTORY).exists())
            finally:
                os.chdir(old)

    def test_write_readback_and_cleanup_failure(self):
        document = snapshot()
        old = Path.cwd()
        with tempfile.TemporaryDirectory() as temporary:
            try:
                os.chdir(temporary)
                response = tool.write_report(document, tool.logo_markup())
                self.assertEqual(response["sharing_mode"], "local_files_only")
                self.assertFalse(response["http_verified"])
                self.assertEqual(response["artifact_status"], "written")
                self.assertLessEqual(tool.response_bytes(response), 3500)
                self.assertEqual(json.loads(Path(response["snapshot_path"]).read_bytes()), document)
                original = tool.os.replace
                count = 0
                def fail_second(source, target):
                    nonlocal count
                    count += 1
                    if count == 2:
                        raise OSError("SIMULATED atomic-write failure")
                    return original(source, target)
                before = {path.name for path in Path(tool.OUTPUT_DIRECTORY).iterdir()}
                with patch.object(tool.os, "replace", side_effect=fail_second):
                    with self.assertRaises(tool.EvidenceError) as raised:
                        tool.write_report(document, tool.logo_markup())
                self.assertEqual(raised.exception.code, "artifact_write_failed")
                self.assertEqual(before, {path.name for path in Path(tool.OUTPUT_DIRECTORY).iterdir()})
            finally:
                os.chdir(old)

    def test_symlink_output_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "target").mkdir()
            try:
                (root / tool.OUTPUT_DIRECTORY).symlink_to(root / "target", target_is_directory=True)
            except OSError as exc:
                self.skipTest("Host does not allow test symlink creation: " + str(exc))
            with patch.object(tool.Path, "cwd", return_value=root):
                with self.assertRaises(tool.EvidenceError) as raised:
                    tool.artifact_directory()
            self.assertEqual(raised.exception.code, "unsafe_artifact_directory")

    def test_symlink_and_junction_guards_without_host_privilege(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve(strict=True)
            original = tool.Path.is_symlink
            with patch.object(tool.Path, "cwd", return_value=root), patch.object(type(root), "is_symlink", lambda path: path == root / tool.OUTPUT_DIRECTORY or original(path)):
                with self.assertRaises(tool.EvidenceError) as raised:
                    tool.artifact_directory()
            self.assertEqual(raised.exception.code, "unsafe_artifact_directory")
            if hasattr(tool.Path, "is_junction"):
                original_junction = tool.Path.is_junction
                with patch.object(tool.Path, "cwd", return_value=root), patch.object(type(root), "is_junction", lambda path: path == root or original_junction(path)):
                    with self.assertRaises(tool.EvidenceError) as raised:
                        tool.artifact_directory()
                self.assertEqual(raised.exception.code, "unsafe_artifact_root")

    def test_native_aliases_derive_both_actual_supported_roots(self):
        for prefix in ("/root/sreagent", "/usr"):
            root = PurePosixPath(prefix + "/terminalRoot/tmp/ThreadFiles/44444444-4444-4444-8444-444444444444")
            stem = "service-health-20261014T184000Z-abcdef123456"
            paths = {key: root / tool.OUTPUT_DIRECTORY / (stem + suffix) for key, suffix in tool.SUFFIXES.items()}
            result = tool.sharing_fields(root, paths)
            self.assertEqual(result["sharing_mode"], "native_ui")
            for key in tool.SUFFIXES:
                alias = result[key.removesuffix("_path") + "_url"]
                self.assertTrue(alias.startswith("/api/files/tmp/ThreadFiles/44444444-4444-4444-8444-444444444444/service-health-reports/"))
                self.assertEqual(alias.rsplit("/", 1)[1], paths[key].name)
            result_envelope = tool.report_envelope(snapshot(), root, paths)
            self.assertLessEqual(tool.response_bytes(result_envelope), 3500)
            paths["report_path"] = root / "elsewhere" / (stem + ".html")
            with self.assertRaises(tool.EvidenceError):
                tool.sharing_fields(root, paths)
        unsupported = PurePosixPath("/tmp/ThreadFiles/44444444-4444-4444-8444-444444444444")
        self.assertEqual(tool.sharing_fields(unsupported, {})["sharing_mode"], "local_files_only")

    def test_standalone_is_generated_and_self_contained(self):
        spec = importlib.util.spec_from_file_location("case05_builder", CASE / "build_tool.py")
        builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(builder)
        generated = (CASE.parent / "manifests" / "tools" / "generate-service-health-report.py").read_text(encoding="utf-8")
        self.assertEqual(generated, builder.build())
        self.assertLess(max(map(len, generated.splitlines())), 10_000)
        tree = ast.parse(generated)
        imports = [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
        self.assertNotIn("engine", imports)
        spec = importlib.util.spec_from_file_location("case05_standalone", CASE.parent / "manifests" / "tools" / "generate-service-health-report.py")
        standalone = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(standalone)
        self.assertEqual(standalone.HTML_TEMPLATE, tool.HTML_TEMPLATE)
        self.assertEqual(inspect.signature(standalone.main), inspect.signature(tool.main))
        with patch.object(standalone, "NativeReader") as reader:
            result = standalone.main()
            self.assertEqual(result["status"], "error")
            self.assertEqual(result["error"]["code"], "configuration_required")
            reader.assert_not_called()

    def test_tool_hydration_as_main_is_pure_then_explicit_invocation_collects_once(self):
        azure = ModuleType("azure")
        azure.__path__ = []
        identity = ModuleType("azure.identity")
        core = ModuleType("azure.core")
        core.__path__ = []
        exceptions = ModuleType("azure.core.exceptions")
        forbidden_identity = Mock(side_effect=AssertionError("Credential construction is forbidden during tool hydration."))
        identity.ManagedIdentityCredential = forbidden_identity
        identity.CredentialUnavailableError = RuntimeError
        exceptions.ClientAuthenticationError = RuntimeError
        exceptions.ServiceRequestError = RuntimeError
        azure.identity, azure.core, core.exceptions = identity, core, exceptions
        modules = {"azure": azure, "azure.identity": identity, "azure.core": core, "azure.core.exceptions": exceptions}
        configured = {
            "SUBSCRIPTION_ID": CONFIG["subscription_id"], "TENANT_ID": CONFIG["tenant_id"],
            "MANAGED_IDENTITY_CLIENT_ID": CONFIG["client_id"],
        }
        fake_snapshot = snapshot()
        for filename in ("engine.py", "../manifests/tools/generate-service-health-report.py"):
            with self.subTest(filename=filename):
                tree = ast.parse((CASE / filename).read_text(encoding="utf-8"))
                for node in tree.body:
                    if isinstance(node, ast.Assign):
                        for target in node.targets:
                            if isinstance(target, ast.Name) and target.id in configured:
                                node.value = ast.Constant(configured[target.id])
                namespace = {"__name__": "__main__", "__file__": str(CASE / filename)}
                output = io.StringIO()
                with patch.dict(sys.modules, modules), redirect_stdout(output), patch(
                    "urllib.request.OpenerDirector.open", side_effect=AssertionError("Network is forbidden during hydration.")
                ), patch.object(Path, "mkdir", side_effect=AssertionError("Artifact writes are forbidden during hydration.")):
                    exec(compile(ast.fix_missing_locations(tree), str(CASE / filename), "exec"), namespace)
                self.assertEqual(output.getvalue(), "")
                forbidden_identity.assert_not_called()
                self.assertTrue(callable(namespace["main"]))
                reader = FakeReader()
                namespace["utc_now"] = Mock(return_value=REFERENCE)
                namespace["NativeReader"] = Mock(return_value=reader)
                namespace["collect"] = Mock(return_value=fake_snapshot)
                namespace["write_report"] = Mock(return_value={"status": "ok", "operation": "report", "artifact_status": "written"})
                namespace["query_snapshot"] = Mock(side_effect=AssertionError("Report execution must not make a query projection."))
                with redirect_stdout(output):
                    result = namespace["main"](operation="report")
                self.assertEqual(result["status"], "ok")
                self.assertEqual(output.getvalue(), "")
                namespace["NativeReader"].assert_called_once()
                namespace["collect"].assert_called_once()
                namespace["write_report"].assert_called_once()
                namespace["query_snapshot"].assert_not_called()
                self.assertTrue(reader.closed)


class IdentityAndBrandingTests(unittest.TestCase):
    def test_placeholder_configuration_blocks_auth_and_branding_before_collection(self):
        with patch.object(tool, "NativeReader") as reader:
            result = tool.main()
            self.assertEqual(result["error"]["code"], "configuration_required")
            reader.assert_not_called()
        with patch.object(tool, "configuration", return_value=CONFIG), patch.object(tool, "COMPANY_LOGO_DATA_URI", "https://forbidden.invalid/logo.png"), patch.object(tool, "NativeReader") as reader:
            result = tool.main()
            self.assertEqual(result["error"]["code"], "invalid_company_logo")
            reader.assert_not_called()

    def test_raster_branding_limits_and_mime(self):
        from PIL import Image
        def raster(mode="PNG", size=(100, 40), frames=1):
            stream = io.BytesIO()
            image = Image.new("RGB", size, "#fbc807")
            if frames == 1:
                image.save(stream, format=mode)
            else:
                image.save(stream, format=mode, save_all=True, append_images=[Image.new("RGB", size, "#1e1c18")], duration=100)
            mime = "png" if mode == "PNG" else "jpeg"
            return "data:image/" + mime + ";base64," + base64.b64encode(stream.getvalue()).decode("ascii")
        good = raster()
        with patch.object(tool, "COMPANY_LOGO_DATA_URI", good):
            markup = tool.logo_markup()
            self.assertIn('alt="Customer logo"', markup)
            self.assertIn('width="100"', markup)
        invalid = [
            "data:image/svg+xml;base64,PHN2Zy8+", "data:image/png;base64,!!!",
            "data:image/png;base64," + base64.b64encode(b"not an image").decode("ascii"),
            raster(size=(2049, 1)), raster(frames=2), raster().replace("image/png", "image/jpeg"),
            "data:image/png;base64," + base64.b64encode(b"x" * 100_001).decode("ascii"),
            good[:-12],
        ]
        for uri in invalid:
            with self.subTest(prefix=uri[:60]), patch.object(tool, "COMPANY_LOGO_DATA_URI", uri):
                with self.assertRaises(tool.EvidenceError) as raised:
                    tool.logo_markup()
                self.assertEqual(raised.exception.code, "invalid_company_logo")
        with patch.object(tool, "COMPANY_LOGO_ALT_TEXT", ""):
            with self.assertRaises(tool.EvidenceError):
                tool.logo_markup()
        self.assertIn("Customer logo", tool.logo_markup())

    def test_exact_logo_byte_and_dimension_boundaries(self):
        from PIL import Image
        stream = io.BytesIO()
        Image.new("RGB", (2048, 1), "#fbc807").save(stream, "PNG")
        image = stream.getvalue()
        data = image + b"\0" * (100_000 - len(image))
        uri = "data:image/png;base64," + base64.b64encode(data).decode("ascii")
        with patch.object(tool, "COMPANY_LOGO_DATA_URI", uri):
            self.assertIn('width="2048"', tool.logo_markup())
        uri = "data:image/png;base64," + base64.b64encode(data + b"x").decode("ascii")
        with patch.object(tool, "COMPANY_LOGO_DATA_URI", uri):
            with self.assertRaises(tool.EvidenceError):
                tool.logo_markup()

    def test_token_tenant_client_and_audience_are_fixed(self):
        class FakeToken:
            expires_on = 9_999_999_999
        for changed in (None, "tid", "appid", "aud"):
            reader = tool.NativeReader.__new__(tool.NativeReader)
            reader.config = CONFIG
            reader.cached_token = None
            reader.auth_errors = (RuntimeError,)
            claims = {"tid": CONFIG["tenant_id"], "appid": CONFIG["client_id"], "aud": tool.ORIGIN}
            if changed:
                claims[changed] = "unexpected"
            token = FakeToken()
            token.token = "synthetic." + base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=") + ".synthetic"
            reader.credential = Mock()
            reader.credential.get_token.return_value = token
            if changed:
                with self.assertRaises(tool.EvidenceError) as raised:
                    reader.token()
                self.assertEqual(raised.exception.code, "identity_mismatch")
            else:
                self.assertEqual(reader.token(), token.token)
                self.assertEqual(reader.token(), token.token)
                reader.credential.get_token.assert_called_once_with("https://management.azure.com/.default")

    def test_native_reader_only_get_no_redirect_and_bounded_retries(self):
        reader = tool.NativeReader.__new__(tool.NativeReader)
        reader.config = CONFIG
        reader.deadline = tool.time.monotonic() + 100
        reader.attempt_count = 0
        reader.token = Mock(return_value="SYNTHETIC_TOKEN_NEVER_EXPORTED")
        response_headers = {"x-ms-request-id": "SIMULATED-request", "Retry-After": "0"}
        failed = HTTPError("https://management.azure.com", 429, "Synthetic throttle", response_headers, io.BytesIO(b'{"error":{"code":"SIMULATED429"}}'))
        successful = HTTPError("https://management.azure.com", 200, "Synthetic OK", response_headers, io.BytesIO(b'{"value":[],"extra":900719925474099312345678901234567890}'))
        reader.opener = Mock()
        reader.opener.open.side_effect = [failed, successful]
        response = reader.get(tool.events_url(CONFIG, params()["source_query_start_utc"]), "synthetic")
        self.assertEqual(response["payload"]["extra"], BIG_INTEGER)
        self.assertEqual(len(response["attempts"]), 2)
        self.assertEqual(response["attempts"][0]["error_response"]["error"]["code"], "SIMULATED429")
        self.assertNotIn("SYNTHETIC_TOKEN", tool.json_text(response))
        for call in reader.opener.open.call_args_list:
            request = call.args[0]
            self.assertEqual(request.get_method(), "GET")
        self.assertIsNone(tool.NoRedirect().redirect_request(None, None, 302, {}, {}, "https://evil.invalid"))
        reader.attempt_count = tool.MAX_HTTP_ATTEMPTS
        with self.assertRaises(tool.EvidenceError) as raised:
            reader.get(tool.events_url(CONFIG, params()["source_query_start_utc"]), "synthetic")
        self.assertEqual(raised.exception.code, "collection_bound")

    def test_ambiguous_nonfinite_and_deep_json_fail_explicitly(self):
        for payload in (b'{"value":[],"value":[1]}', b'{"value":[],"extra":NaN}', b'{"value":[],"extra":1e9999}', b'{"value":[],"x":"\\ud800"}', b'{"value":[],"\\ud800":1}', b"[" * 60 + b"0" + b"]" * 60):
            with self.subTest(payload=payload[:80]):
                reader = tool.NativeReader.__new__(tool.NativeReader)
                reader.config = CONFIG
                reader.deadline = tool.time.monotonic() + 100
                reader.attempt_count = 0
                reader.token = Mock(return_value="SYNTHETIC_TOKEN_NEVER_EXPORTED")
                reader.opener = Mock()
                reader.opener.open.return_value = HTTPError("https://management.azure.com", 200, "Synthetic", {}, io.BytesIO(payload))
                with self.assertRaises(tool.EvidenceError) as raised:
                    reader.get(tool.events_url(CONFIG, params()["source_query_start_utc"]), "synthetic")
                self.assertEqual(raised.exception.code, "invalid_response_json")
                self.assertEqual(raised.exception.receipt["attempts"][0]["http_status"], 200)
        for malformed in ("https://[invalid/", "https://management.azure.com/%ZZ"):
            with self.assertRaises(tool.EvidenceError):
                tool.validate_request(malformed, CONFIG)

    def test_slow_source_stream_checks_shared_deadline_between_reads(self):
        reader = tool.NativeReader.__new__(tool.NativeReader)
        reader.config = CONFIG
        reader.deadline = tool.time.monotonic() + 100
        reader.attempt_count = 0
        reader.token = Mock(return_value="SYNTHETIC_TOKEN_NEVER_EXPORTED")
        class SlowResponse:
            code = 200
            headers = {}
            reads = 0
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def read1(self, count):
                self.reads += 1
                reader.deadline = tool.time.monotonic() - 1
                return b'{"value":['
        response = SlowResponse()
        reader.opener = Mock()
        reader.opener.open.return_value = response
        with self.assertRaises(tool.EvidenceError) as raised:
            reader.get(tool.events_url(CONFIG, params()["source_query_start_utc"]), "synthetic")
        self.assertEqual(raised.exception.code, "collection_bound")
        self.assertEqual(response.reads, 1)
        self.assertTrue(raised.exception.receipt["attempts"][0]["body_incomplete"])
        self.assertEqual(raised.exception.receipt["attempts"][0]["http_status"], 200)

    def test_identity_wait_cannot_start_an_arm_request_after_deadline(self):
        reader = tool.NativeReader.__new__(tool.NativeReader)
        reader.config = CONFIG
        reader.deadline = tool.time.monotonic() + 100
        reader.attempt_count = 0
        def slow_token():
            reader.deadline = tool.time.monotonic() - 1
            return "SYNTHETIC_TOKEN_NEVER_EXPORTED"
        reader.token = slow_token
        reader.opener = Mock()
        with self.assertRaises(tool.EvidenceError) as raised:
            reader.get(tool.events_url(CONFIG, params()["source_query_start_utc"]), "synthetic")
        self.assertEqual(raised.exception.code, "collection_bound")
        reader.opener.open.assert_not_called()
        source = (CASE / "engine.py").read_text(encoding="utf-8")
        self.assertIn("connection_timeout=5, read_timeout=10, retry_total=0", source)

    def test_live_entrypoint_can_only_be_exercised_with_mocked_source(self):
        reader = FakeReader()
        with patch.object(tool, "configuration", return_value=CONFIG), patch.object(tool, "utc_now", return_value=REFERENCE), patch.object(tool, "NativeReader", return_value=reader):
            response = tool.main(operation="query", view="summary")
        self.assertEqual(response["status"], "partial")
        self.assertTrue(reader.closed)
        self.assertEqual(response["rows"][0]["event_records"], 5)

    @unittest.skip("Documentation check; it runs upstream with the full guide")

    def test_documentation_links_anchors_and_logo_generator_one_liner(self):
        import subprocess
        from PIL import Image

        def heading_slugs(markdown_text: str) -> set[str]:
            stripped = re.sub(r"```.*?```", "", markdown_text, flags=re.S)
            slugs = set()
            for line in stripped.splitlines():
                match = re.match(r"^#{1,6}\s+(.+?)\s*$", line)
                if not match:
                    continue
                raw = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", match.group(1)).replace("`", "")
                slug = re.sub(r"[^\w\s-]", "", raw.lower())
                slugs.add(re.sub(r"\s+", "-", slug.strip()))
            return slugs

        docs = [
            CASE / "README.md",
            CASE / "subagent-instructions-and-prompts.md",
            CASE / "monthly-task-prompt.md",
            CASE / "PRODUCT.md",
            CASE / "DESIGN.md",
            CASE / "SURFACE.md",
            CASE / "skills" / "service-health-live" / "SKILL.md",
        ]
        for doc in docs:
            self.assertTrue(doc.is_file(), str(doc))
            content = doc.read_text(encoding="utf-8")
            stripped = re.sub(r"```.*?```", "", content, flags=re.S)
            for target in re.findall(r"!?\[[^\]]*\]\(([^)]+)\)", stripped):
                if target.startswith(("https://", "http://")):
                    continue
                file_part, _, anchor = target.partition("#")
                resolved = (doc.parent / file_part).resolve() if file_part else doc.resolve()
                self.assertTrue(resolved.exists(), f"{doc.name} -> {target}")
                if anchor:
                    target_slugs = heading_slugs(resolved.read_text(encoding="utf-8"))
                    self.assertIn(anchor, target_slugs, f"{doc.name} -> {target} (missing #{anchor})")

        readme = (CASE / "README.md").read_text(encoding="utf-8")
        match = re.search(r'python -c "(import base64, sys, textwrap;[^"]+)"', readme)
        self.assertIsNotNone(match, "README.md must include the copy-ready COMPANY_LOGO_DATA_URI generator one-liner")
        with tempfile.TemporaryDirectory() as temporary:
            logo_path = Path(temporary) / "company-logo.png"
            Image.new("RGB", (64, 24), "#fbc807").save(logo_path, format="PNG")
            code = match.group(1).replace(r"C:\path\company-logo.png", str(logo_path))
            completed = subprocess.run([sys.executable, "-c", code], check=True, capture_output=True, text=True)
            lines = completed.stdout.strip().splitlines()
            self.assertGreaterEqual(len(lines), 3)
            self.assertTrue(all(len(line) <= 94 for line in lines), lines)
            namespace = {}
            exec(completed.stdout, namespace)
            with patch.object(tool, "COMPANY_LOGO_DATA_URI", namespace["COMPANY_LOGO_DATA_URI"]):
                markup = tool.logo_markup()
                self.assertIn('width="64"', markup)
                self.assertIn('height="24"', markup)


if __name__ == "__main__":
    unittest.main()

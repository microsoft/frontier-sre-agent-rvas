"""SIMULATED fleet tests: auto-discovery across subscriptions, chat selection, parallel collection with a
thread-local subscription scope, Cost Management throttling, fleet envelope, CSV columns and compressed HTML."""

import base64
import copy
import csv
import email.message
import gzip
import io
import json
import os
import random
import re
import tempfile
import threading
import time
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from support import REFERENCE, SUBSCRIPTION, fixture, load_engine


TENANT = "22222222-2222-4222-8222-222222222222"
SUBSCRIPTIONS = ["%08d-1111-4111-8111-111111111111" % index for index in range(1, 21)]
NAMES = {value: "Contoso Sub %02d" % index + (" (Prod – EU)" if index % 5 == 0 else "") for index, value in enumerate(SUBSCRIPTIONS)}


def arg_row(subscription, group, name, location="westeurope", tenant=TENANT):
    return {"id": "/subscriptions/" + subscription + "/resourceGroups/" + group + "/providers/Microsoft.ContainerService/managedClusters/" + name,
            "name": name, "resourceGroup": group.lower(), "subscriptionId": subscription, "tenantId": tenant,
            "location": location, "subscriptionName": NAMES.get(subscription)}


def fleet_rows(count, duplicates=True):
    rows = [arg_row(SUBSCRIPTIONS[index % 20], "rg-plant-%03d" % index, "aks-plant-%03d" % index,
                    ("westeurope", "northeurope", "eastus2")[index % 3]) for index in range(count)]
    if duplicates:
        rows += [arg_row(SUBSCRIPTIONS[3], "rg-dup-a", "aks-shared"), arg_row(SUBSCRIPTIONS[7], "rg-dup-b", "aks-shared")]
    return sorted(rows, key=lambda row: (row["subscriptionId"], row["name"]))


def discovery_engine(rows):
    engine = load_engine()
    engine.AUTO_DISCOVERY = True
    engine.APPROVED_CLUSTERS = {}
    engine.SUBSCRIPTION_ID = "<YOUR_SUBSCRIPTION_ID>"
    engine.discover_clusters = lambda: copy.deepcopy(rows)
    return engine


@contextmanager
def cwd(path):
    previous = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


class FleetSelectionTests(unittest.TestCase):
    def setUp(self):
        self.rows = fleet_rows(103)
        self.e = discovery_engine(self.rows)

    def test_only_tenant_and_client_are_required_and_list_spans_every_subscription(self):
        result = self.e.main(operation="list_clusters")
        self.assertEqual((result["status"], result["total"], result["subscription_count"]), ("ok", 105, 20))
        self.assertLessEqual(self.e.response_bytes(result), self.e.TRANSPORT_BYTES)
        self.assertTrue(result["roster_basis"].startswith("observed_inventory"))
        row = result["available_clusters"][0]
        self.assertLessEqual({"cluster_name", "resource_group", "subscription_id", "subscription_name", "location", "environment"}, set(row))
        seen, offset = [], 0
        while offset is not None:
            page = self.e.main(operation="list_clusters", limit=100, offset=offset)
            self.assertLessEqual(self.e.response_bytes(page), self.e.TRANSPORT_BYTES)
            seen.extend(item["cluster_name"] for item in page["available_clusters"])
            offset = page["next_offset"]
        self.assertEqual(len(seen), 105)
        self.assertEqual(len(set(seen)), 105)

    def test_subscription_filter_accepts_id_or_display_name_case_insensitively(self):
        target = SUBSCRIPTIONS[5]
        by_id = self.e.main(operation="list_clusters", subscription=target.upper())
        by_name = self.e.main(operation="list_clusters", subscription=NAMES[target].upper())
        self.assertEqual(by_id["total"], by_name["total"])
        self.assertEqual({row["subscription_id"] for row in by_name["available_clusters"]}, {target})
        self.assertEqual(by_name["subscription_filter"], NAMES[target].upper())
        unknown = self.e.main(operation="list_clusters", subscription="Contoso Sub 99")
        self.assertEqual(unknown["error"]["code"], "unknown_subscription")
        self.assertIn("similar", unknown["error"]["message"])

    def test_report_selection_all_subscription_names_and_bounds(self):
        self.e.ROSTER = self.e.effective_roster()
        for kwargs in ({"operation": "report"}, {"operation": "report", "cluster_names": "all"}):
            result = self.e.main(**kwargs)
            self.assertEqual(result["error"]["code"], "too_many_clusters")
            self.assertIn("subscription=", result["error"]["message"])
        selected, _ = self.e.selection_configs("", "all", NAMES[SUBSCRIPTIONS[0]], "report")
        self.assertEqual({config["subscription_id"] for config in selected}, {SUBSCRIPTIONS[0]})
        selected, _ = self.e.selection_configs("", "", SUBSCRIPTIONS[1], "report")
        self.assertEqual(len(selected), sum(row["subscriptionId"] == SUBSCRIPTIONS[1] for row in self.rows))
        selected, _ = self.e.selection_configs("", "aks-plant-001,AKS-PLANT-021,aks-plant-041", "", "report")
        self.assertEqual([config["name"] for config in selected], ["aks-plant-001", "aks-plant-021", "aks-plant-041"])
        selected, _ = self.e.selection_configs("aks-plant-007", "", "", "report")
        self.assertEqual(selected[0]["subscription_id"], SUBSCRIPTIONS[7])
        names = ",".join("aks-plant-%03d" % index for index in range(100))
        self.assertEqual(len(self.e.selection_configs("", names, "", "report")[0]), 100)
        for args, code in ((("aks-plant-0077", "", "", "report"), "unknown_cluster"),
                           (("aks-shared", "", "", "report"), "ambiguous_cluster_name"),
                           (("", "aks-plant-001,aks-plant-001", "", "report"), "invalid_parameter"),
                           (("", "", "", "query"), "selection_required")):
            with self.subTest(args=args), self.assertRaises(self.e.EvidenceError) as raised:
                self.e.selection_configs(*args)
            self.assertEqual(raised.exception.code, code)
        duplicate, _ = self.e.selection_configs("aks-shared", "", NAMES[SUBSCRIPTIONS[7]], "report")
        self.assertEqual((duplicate[0]["subscription_id"], duplicate[0]["aks_name"]), (SUBSCRIPTIONS[7], "aks-shared"))
        prefixed = next(config for config in self.e.selection_configs("", "", "", "list_clusters")[1] if config["name"].endswith("-aks-shared"))
        self.assertEqual(self.e.selection_configs(prefixed["name"], "", "", "report")[0][0]["id"], prefixed["id"])
        too_many = ",".join("aks-plant-%03d" % index for index in range(101))
        self.assertEqual(self.e.main(operation="report", cluster_names=too_many)["error"]["code"], "invalid_parameter")
        for unsafe in ({"cluster_names": "aks a"}, {"subscription": "x<script>"}, {"subscription": " "}):
            with self.subTest(unsafe=unsafe):
                self.assertEqual(self.e.main(operation="report", **unsafe)["error"]["code"], "invalid_parameter")

    def test_operator_override_merges_discovery_metadata_and_needs_a_subscription(self):
        self.e.APPROVED_CLUSTERS = {"aks-plant-001": {"resource_group": "rg-plant-001", "environment": "PRODUCTION"}}
        self.assertEqual(self.e.main(operation="list_clusters")["error"]["code"], "configuration_required")
        self.e.APPROVED_CLUSTERS["aks-plant-001"]["subscription_id"] = SUBSCRIPTIONS[1]
        result = self.e.main(operation="list_clusters", subscription=SUBSCRIPTIONS[1])
        row = next(item for item in result["available_clusters"] if item["cluster_name"] == "aks-plant-001")
        self.assertEqual((row["environment"], row["subscription_name"]), ("PRODUCTION", NAMES[SUBSCRIPTIONS[1]]))
        self.assertEqual([item["cluster_name"] for item in result["available_clusters"]].count("aks-plant-001"), 1)

    def test_discovery_query_is_fixed_and_returns_subscription_names(self):
        engine = load_engine()
        bodies = []

        class Reader:
            def __init__(self, identity):
                pass

            def allow(self, url, method="GET"):
                bodies.append(("allow", method, url))
                return url

            def request(self, method, url, source, body=None, allow_empty=False):
                bodies.append(body)
                return {"data": fleet_rows(2, duplicates=False)}

        class Identity:
            def close(self):
                pass

        engine.HttpReader, engine.Identity = Reader, Identity
        self.assertEqual(len(engine.discover_clusters()), 2)
        self.assertEqual(bodies[0][1:], ("POST", engine.ARM_ORIGIN + "/providers/Microsoft.ResourceGraph/resources?api-version=" + engine.ARG_API))
        query = bodies[1]["query"]
        self.assertEqual(query, engine.DISCOVERY_QUERY)
        self.assertIn("resourcecontainers", query)
        self.assertIn("subscriptionName", query)
        self.assertNotIn("subscriptions", bodies[1])


class FleetCollectionTests(unittest.TestCase):
    def setUp(self):
        self.e = discovery_engine(fleet_rows(40, duplicates=False))
        self.e.ROSTER = self.e.effective_roster()
        self.configs = self.e.selection_configs("", "", "", "list_clusters")[1][:24]

    def test_parallel_runs_keep_each_cluster_subscription_and_never_report_failures_as_healthy(self):
        mismatches, active, peak, lock = [], [0], [0], threading.Lock()
        names = [config["name"] for config in self.configs]

        def inner(config, reference, deadline=None):
            with lock:
                active[0] += 1
                peak[0] = max(peak[0], active[0])
            try:
                for _ in range(3):
                    if self.e.scope_subscription() != config["subscription_id"]:
                        mismatches.append(config["name"])
                    time.sleep(random.uniform(0.005, 0.03))
                if config["name"] == names[1]:
                    raise self.e.EvidenceError("access_denied", "SIMULATED 403.", "arm_cluster", 403)
                if config["name"] == names[2]:
                    raise RuntimeError("SIMULATED defect")
                if config["name"] == names[3]:
                    time.sleep(4)
                return {"partial": config["name"] == names[4]}
            finally:
                with lock:
                    active[0] -= 1

        def finish(raw, reference, provenance="LIVE", environment="UNSPECIFIED"):
            return {"sources": [{"id": "azure_cost", "status": "error" if raw["partial"] else "complete"}]}

        with patch.object(self.e, "_collect_live", side_effect=inner), patch.object(self.e, "finish_snapshot", side_effect=finish), \
                patch.multiple(self.e, FLEET_DEADLINE_SECONDS=1.5, FLEET_GRACE_SECONDS=0.5):
            started = time.monotonic()
            runs = self.e.collect_fleet(self.configs)
            elapsed = time.monotonic() - started
        status = {run["cluster_name"]: (run["status"], (run["error"] or {}).get("code")) for run in runs}
        self.assertEqual(mismatches, [])
        self.assertTrue(1 < peak[0] <= self.e.COLLECTION_WORKERS)
        self.assertGreater(len({config["subscription_id"] for config in self.configs}), 10)
        self.assertEqual([run["cluster_name"] for run in runs], names)
        self.assertEqual(status[names[0]], ("ok", None))
        self.assertEqual(status[names[1]], ("error", "access_denied"))
        self.assertEqual(status[names[2]], ("error", "unexpected_error"))
        self.assertEqual(status[names[3]], ("error", "collection_timeout"))
        self.assertEqual(status[names[4]], ("partial", None))
        self.assertLess(elapsed, 3.5)
        self.assertIsNone(getattr(self.e.COLLECTION_SCOPE, "subscription_id", None))


class CostThrottlingTests(unittest.TestCase):
    def setUp(self):
        self.e = load_engine()

    class Identity:
        def __init__(self, seconds):
            self.deadline = time.monotonic() + seconds

        def token(self, audience):
            return "SIMULATED-OPAQUE-TOKEN"

    def reader(self, plan, seconds=30):
        reader = self.e.HttpReader(self.Identity(seconds))
        calls = []

        class Opener:
            def open(self, request, timeout=30):
                calls.append(time.monotonic())
                step = plan.pop(0)
                if isinstance(step, int):
                    headers = email.message.Message()
                    headers["x-ms-ratelimit-microsoft.costmanagement-qpu-retry-after"] = str(step)
                    raise HTTPError(request.full_url, 429, "SIMULATED throttle", headers, None)

                class Response:
                    status = 200

                    def read(self, size):
                        return json.dumps(step).encode()

                    def __enter__(self):
                        return self

                    def __exit__(self, *args):
                        return False
                return Response()
        reader.opener = Opener()
        url = reader.allow(self.e.ARM_ORIGIN + "/subscriptions/" + SUBSCRIPTION
                           + "/resourceGroups/rg-client-nodes/providers/Microsoft.CostManagement/query?api-version=2023-11-01", "POST")
        return reader, url, calls

    def test_cost_query_429_honours_cost_management_retry_header(self):
        reader, url, calls = self.reader([7, {"properties": {"columns": [], "rows": []}}])
        with patch.object(self.e.time, "sleep") as sleep:
            result = reader.request("POST", url, "azure_cost", body={})
        self.assertEqual(result["properties"]["rows"], [])
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [7])
        self.assertEqual(len(calls), 2)

    def test_retry_wait_beyond_the_deadline_stops_as_throttled(self):
        reader, url, _ = self.reader([45], seconds=5)
        with patch.object(self.e.time, "sleep") as sleep, self.assertRaises(self.e.EvidenceError) as raised:
            reader.request("POST", url, "azure_cost", body={})
        sleep.assert_not_called()
        self.assertEqual((raised.exception.code, raised.exception.http_status), ("throttled", 429))
        self.assertNotIn("SIMULATED-OPAQUE-TOKEN", str(raised.exception))

    def test_concurrent_cost_queries_are_bounded_and_throttling_only_marks_that_cost_source(self):
        config = {"approved_cost_resource_ids": [], "cost_timeframe": "month_to_date", "cost_scope": "node_resource_group",
                  "subscription_id": SUBSCRIPTION, "name": "aks-client-lab",
                  "id": "/subscriptions/" + SUBSCRIPTION + "/resourceGroups/rg-client-lab/providers/Microsoft.ContainerService/managedClusters/aks-client-lab"}
        cluster = {"node_resource_group": "rg-client-nodes", "id": config["id"]}
        inflight, peak, lock = [0], [0], threading.Lock()
        engine = self.e

        class SlowReader:
            def allow(self, url, method="GET"):
                return url

            def request(self, *args, **kwargs):
                with lock:
                    inflight[0] += 1
                    peak[0] = max(peak[0], inflight[0])
                time.sleep(0.1)
                with lock:
                    inflight[0] -= 1
                raise engine.EvidenceError("throttled", "SIMULATED 429.", "azure_cost", 429)

        receipts = []
        threads = [threading.Thread(target=lambda: receipts.append(engine.collect_cost(SlowReader(), config, REFERENCE, [], cluster)[1]))
                   for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertLessEqual(peak[0], self.e.COST_CONCURRENCY)
        self.assertEqual({(receipt["status"], receipt["errors"][0]["code"]) for receipt in receipts}, {("error", "throttled")})


class FleetReportTests(unittest.TestCase):
    def test_fleet_report_envelope_subscription_columns_and_compressed_html(self):
        base_engine = load_engine()
        base_raw = json.dumps(fixture(base_engine))
        rows = [arg_row(SUBSCRIPTIONS[index % 3], "rg-store-%02d" % index, "aks-store-%02d" % index) for index in range(9)]
        rows.append(arg_row(SUBSCRIPTIONS[2], "rg-store-denied", "aks-store-denied"))
        engine = discovery_engine(rows)

        def inner(config, reference, deadline=None):
            self.assertEqual(engine.scope_subscription(), config["subscription_id"])
            if config["name"] == "aks-store-denied":
                raise engine.EvidenceError("access_denied", "SIMULATED 403.", "arm_cluster", 403)
            text = base_raw.replace('"cluster_name": "aks-client-lab"', '"cluster_name": "' + config["name"] + '"')
            text = text.replace(SUBSCRIPTION, config["subscription_id"]).replace("rg-client-lab", config["resource_group"])
            raw = json.loads(text.replace("aks-client-lab", config["aks_name"]))
            raw["cluster"].update(name=config["name"], aks_name=config["aks_name"], subscription_name=config["subscription_name"])
            raw["inventory"]["node_pools"][0]["provisioning_state"] = "Failed"
            return raw

        with tempfile.TemporaryDirectory() as directory, cwd(directory), patch.object(engine, "_collect_live", side_effect=inner), \
                patch.object(engine, "HTML_INLINE_JSON_BYTES", 1000):
            result = engine.main(operation="report", cluster_names="all")
            self.assertEqual(result["status"], "partial", result)
            self.assertLessEqual(engine.response_bytes(result), engine.TRANSPORT_BYTES)
            self.assertEqual((result["collection"]["selected_cluster_count"], result["collection"]["subscription_count"]), (10, 3))
            self.assertEqual(result["cluster_errors"], [{"cluster": "aks-store-denied", "code": "access_denied"}])
            self.assertEqual(set(result["findings_by_severity"]), {"critical", "high", "medium", "low"})
            document = json.loads(Path(result["snapshot_path"]).read_text(encoding="utf-8"))
            self.assertEqual(document["schema_version"], "aks-waf-multi-cluster-v1")
            self.assertTrue(all(run["snapshot"] is None or "client" not in run["snapshot"] for run in document["cluster_runs"]))
            self.assertEqual({row["subscription_name"] for row in document["available_clusters"]}, {NAMES[value] for value in SUBSCRIPTIONS[:3]})
            html = Path(result["report_path"]).read_text(encoding="utf-8")
            packed = re.search(r'id="report-data">gzip-base64:([A-Za-z0-9+/=]+)</script>', html)
            self.assertIsNotNone(packed)
            embedded = json.loads(gzip.decompress(base64.b64decode(packed.group(1))))
            self.assertEqual(embedded, document)
            findings = list(csv.DictReader(io.StringIO(Path(result["findings_csv_path"]).read_text(encoding="utf-8-sig"))))
            inventory = list(csv.DictReader(io.StringIO(Path(result["inventory_csv_path"]).read_text(encoding="utf-8-sig"))))
            self.assertTrue(findings)
            self.assertTrue(all(row["subscription_id"] in SUBSCRIPTIONS[:3] and row["subscription_name"] for row in findings))
            self.assertTrue(any(row["collection"] == "cluster_collection_error" and row["subscription_name"] == NAMES[SUBSCRIPTIONS[2]]
                                for row in inventory))


if __name__ == "__main__":
    unittest.main()

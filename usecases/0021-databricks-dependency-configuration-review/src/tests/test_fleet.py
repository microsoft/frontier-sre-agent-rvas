"""Fleet features: auto-discovery, selection, list_workspaces, parallel collection, access status, cost scope, fleet report UI."""

import copy
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from contextlib import contextmanager
from email.message import Message
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

from support import REFERENCE, SRE_TENANT, SUBSCRIPTION, WORKSPACE_HOST, WORKSPACE_ID, WORKSPACE_NAME, fixture, load_engine

OTHER_TENANT = "99999999-9999-4999-8999-999999999999"


def sub_id(n):
    return "%08x-aaaa-4bbb-8ccc-%012x" % (0x10000000 + n, n)


def host(n):
    return "adb-%016d.%d.azuredatabricks.net" % (1000000000000000 + n * 7919, n % 20 + 1)


def arg_row(n, sub_n, name, tenant=SRE_TENANT, sub_name=None, url=True):
    sub = sub_id(sub_n)
    return {
        "id": "/subscriptions/" + sub + "/resourceGroups/rg-" + name + "/providers/Microsoft.Databricks/workspaces/" + name,
        "name": name, "resourceGroup": "rg-" + name, "subscriptionId": sub, "tenantId": tenant,
        "subscriptionName": sub_name if sub_name is not None else "Contoso-Sub-%02d" % sub_n,
        "location": ("westeurope", "northeurope", "eastus2")[n % 3], "skuName": "premium",
        "workspaceUrl": host(n) if url else "", "publicNetworkAccess": "Enabled", "customVnet": "",
    }


@contextmanager
def cwd(path):
    original = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(original)


class FakeIdentity:
    def __init__(self, config=None):
        self.config = config or {"auth_mode": "same_tenant_uami"}
        self.deadline = time.monotonic() + 120
        self.request_count = 0
        self.dbx_gate = None

    def _guard_budget(self):
        self.request_count += 1

    def arm_token(self):
        return "arm"

    def databricks_token(self):
        return "dbx"

    def close(self):
        pass


class Response:
    def __init__(self, payload):
        self.status, self.payload = 200, json.dumps(payload).encode("utf-8")

    def read(self, limit=-1):
        return self.payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class Opener:
    def __init__(self, handler):
        self.handler, self.calls = handler, []

    def open(self, request, timeout=None):
        self.calls.append((request.get_method(), request.full_url))
        return self.handler(request)


def http_error(url, code, retry_after=None):
    headers = Message()
    if retry_after is not None:
        headers["Retry-After"] = str(retry_after)
    return HTTPError(url, code, "x", headers, None)


class FleetTestCase(unittest.TestCase):
    def engine(self, rows, pages=1):
        e = load_engine(cross_tenant=False)
        e.APPROVED_WORKSPACES = {}
        e.Identity = FakeIdentity
        e.TEST_ARG_BODIES = bodies = []
        chunks = [rows[i::pages] for i in range(pages)] if pages > 1 else [rows]
        original = e.HttpReader.request

        def fake_request(reader, method, url, source, body=None, allow_empty=False):
            if source != "arm_discovery":
                return original(reader, method, url, source, body, allow_empty)
            self.assertEqual((method, url), ("POST", e.ARM_ORIGIN + "/providers/Microsoft.ResourceGraph/resources?api-version=2022-10-01"))
            self.assertEqual(body["query"], e.DISCOVERY_QUERY)
            bodies.append(copy.deepcopy(body))
            index = int(body["options"].get("$skipToken", "page-0").split("-")[1])
            page = {"data": chunks[index]}
            if index + 1 < len(chunks):
                page["$skipToken"] = "page-" + str(index + 1)
            return page

        e.HttpReader.request = fake_request
        return e

    def raw_for(self, e, config):
        if not hasattr(FleetTestCase, "_base_raw"):
            FleetTestCase._base_raw = json.dumps(fixture(load_engine(cross_tenant=False)))
        text = FleetTestCase._base_raw
        for old, new in ((WORKSPACE_ID, config["id"]), (WORKSPACE_ID.lower(), config["id"].lower()), (SUBSCRIPTION, config["subscription_id"]),
                         (WORKSPACE_HOST, config["workspace_host"] or WORKSPACE_HOST), (WORKSPACE_NAME, config["arm_name"])):
            text = text.replace(old, new)
        raw = json.loads(text)
        raw["workspace"]["workspace_name"] = config["name"]
        return raw


class DiscoveryAndSelectionTests(FleetTestCase):
    def test_discovery_parsing_paging_tenant_duplicates_and_missing_url(self):
        rows = [arg_row(1, 1, "dbw-a"), arg_row(2, 2, "dbw-a"), arg_row(3, 3, "dbw-b", tenant=OTHER_TENANT), arg_row(4, 4, "dbw c"),
                arg_row(5, 5, "dbw-nourl", url=False), arg_row(6, 1, "dbw-z", sub_name=""),
                {"id": "/subscriptions/x/resourceGroups/r/providers/Microsoft.Sql/servers/s"}]
        e = self.engine(rows, pages=3)
        roster = e.effective_roster()
        self.assertEqual(len(e.TEST_ARG_BODIES), 3)
        self.assertEqual(e.TEST_ARG_BODIES[1]["options"]["$skipToken"], "page-1")
        self.assertIn("dbw-a", roster)
        self.assertIn(sub_id(2)[:8] + "-dbw-a", roster)
        self.assertNotIn("dbw-b", roster)
        self.assertNotIn("dbw c", roster)
        self.assertFalse(roster["dbw-nourl"]["workspace_api_enabled"])
        self.assertEqual(roster["dbw-z"]["subscription_name"], sub_id(1))
        self.assertEqual({k: e.DISCOVERY_INFO[k] for k in ("discovered", "other_tenant_skipped", "skipped", "without_workspace_url")},
                         {"discovered": 4, "other_tenant_skipped": 1, "skipped": 2, "without_workspace_url": 1})
        e.ROSTER = roster
        config = e.validate_config(sub_id(2)[:8] + "-dbw-a")
        self.assertEqual(config["id"], "/subscriptions/" + sub_id(2) + "/resourceGroups/rg-dbw-a/providers/Microsoft.Databricks/workspaces/dbw-a")
        self.assertEqual((config["cost_scope"], config["environment"]), ("workspace_and_managed_resource_group", "UNSPECIFIED"))

    def test_operator_entry_overrides_discovered_workspace_and_placeholders_are_ignored(self):
        e = self.engine([arg_row(1, 1, "dbw-prod"), arg_row(2, 2, "dbw-dev")])
        e.APPROVED_WORKSPACES = {"<PLACEHOLDER>": {"resource_group": "<RG>"},
                                 "dbw-prod": {"resource_group": "rg-dbw-prod", "subscription_id": sub_id(1), "environment": "PRODUCTION"}}
        e.ROSTER = e.effective_roster()
        self.assertEqual(list(e.ROSTER), ["dbw-prod", "dbw-dev"])
        config = e.validate_config("dbw-prod")
        self.assertEqual((config["environment"], config["workspace_host"], config["subscription_name"]), ("PRODUCTION", host(1), "Contoso-Sub-01"))

    def test_cross_tenant_configuration_keeps_the_approved_list_without_discovery(self):
        e = load_engine()
        with patch.object(e, "Identity") as identity:
            roster = e.effective_roster()
        identity.assert_not_called()
        self.assertEqual(list(roster), [WORKSPACE_NAME])
        self.assertEqual(e.DISCOVERY_INFO["reason"], "cross_tenant_configuration")

    def test_selection_all_names_subscription_unknown_ambiguous_and_bounds(self):
        rows = [arg_row(i, i % 20, "dbw-%02d" % i) for i in range(60)] + [arg_row(99, 5, "dbw-01")]
        e = self.engine(rows)
        e.ROSTER = e.effective_roster()
        configs, roster, mode = e.selection_configs("", "", "")
        self.assertEqual((mode, len(configs), len(roster)), ("all", 61, 61))
        self.assertEqual(len(e.selection_configs("", "all", sub_id(3))[0]), 3)
        self.assertEqual(len(e.selection_configs("", "", "contoso-sub-03")[0]), 3)
        configs, _, mode = e.selection_configs("", "dbw-02,dbw-07,dbw-33", "")
        self.assertEqual((mode, [c["name"] for c in configs]), ("names", ["dbw-02", "dbw-07", "dbw-33"]))
        self.assertEqual(e.selection_configs("dbw-01", "", "Contoso-Sub-05")[0][0]["subscription_id"], sub_id(5))
        for args in (("dbw-nope", "", ""), ("", "", "Unknown subscription")):
            with self.assertRaises(e.EvidenceError):
                e.selection_configs(*args)
        e.ROSTER = {"a": {"resource_group": "rg-x", "subscription_id": sub_id(1), "arm_name": "dbw-x", "workspace_host": host(1)},
                    "b": {"resource_group": "rg-x", "subscription_id": sub_id(2), "arm_name": "dbw-x", "workspace_host": host(2)}}
        with self.assertRaises(e.EvidenceError) as raised:
            e.selection_configs("dbw-x", "", "")
        self.assertEqual(raised.exception.code, "ambiguous_workspace_name")
        self.assertEqual(e.main(operation="report")["error"]["code"], "too_many_workspaces")
        self.assertEqual(e.main(operation="report", workspace_names=",".join("dbw-%02d" % i for i in range(51)))["error"]["code"], "invalid_parameter")
        self.assertEqual(e.main(operation="query", workspace_names="dbw-02,dbw-03,dbw-04,dbw-05,dbw-06,dbw-07")["error"]["code"], "too_many_workspaces")
        for bad in (dict(workspace_names="a, b"), dict(subscription='x"y', operation="list_workspaces"), dict(operation="list_workspaces", workspace_name="dbw-01"),
                    dict(operation="self_test", subscription=sub_id(1))):
            self.assertEqual(e.main(**bad)["status"], "error", bad)

    def test_list_workspaces_rows_paging_filter_and_transport_budget(self):
        e = self.engine([arg_row(i, i % 20, "dbw-%02d" % i) for i in range(60)])
        first = e.main(operation="list_workspaces")
        self.assertEqual((first["status"], first["total"], first["discovery"]["mode"]), ("ok", 60, "auto"))
        self.assertLessEqual(e.response_bytes(first), 3500)
        self.assertEqual(set(first["available_workspaces"][0]), {"workspace_name", "resource_group", "subscription_id", "subscription_name",
                                                                 "location", "sku", "workspace_host", "environment"})
        names, offset = [], 0
        while offset is not None:
            page = e.main(operation="list_workspaces", limit=100, offset=offset)
            self.assertLessEqual(e.response_bytes(page), 3500)
            names += [row["workspace_name"] for row in page["available_workspaces"]]
            offset = page["next_offset"]
        self.assertEqual(len(set(names)), 60)
        self.assertEqual(e.main(operation="list_workspaces", subscription="CONTOSO-SUB-07")["total"], 3)


class HttpGuardTests(FleetTestCase):
    def reader(self, e, handler, kind="arm", origin=None):
        reader = e.HttpReader(FakeIdentity(), origin or e.ARM_ORIGIN, kind)
        reader.opener = Opener(handler)
        return reader

    def test_post_guard_allows_only_cost_query_and_the_exact_resource_graph_path(self):
        e = load_engine(cross_tenant=False)
        reader = self.reader(e, lambda request: Response({"data": []}))
        for path in ("/providers/Microsoft.ResourceGraph/resources/x", "/subscriptions/" + SUBSCRIPTION + "/providers/Microsoft.ResourceGraph/resources"):
            url = e.ARM_ORIGIN + path + "?api-version=2022-10-01"
            reader.allow(url, "POST")
            with self.assertRaises(e.EvidenceError) as raised:
                reader.request("POST", url, "x", body={})
            self.assertEqual(raised.exception.code, "unsafe_method")
        url = reader.allow(e.ARM_ORIGIN + "/providers/Microsoft.ResourceGraph/resources?api-version=2022-10-01", "POST")
        self.assertEqual(reader.request("POST", url, "arm_discovery", body={}), {"data": []})

    def test_workspace_gate_after_401_or_network_failure_but_not_after_403(self):
        e = load_engine(cross_tenant=False)
        origin = "https://" + WORKSPACE_HOST
        for failure, gated in ((401, True), (403, False), ("network", True)):
            def handler(request, failure=failure):
                if failure == "network":
                    raise URLError("timed out")
                raise http_error(request.full_url, failure)
            reader = self.reader(e, handler, "databricks", origin)
            for path in ("/api/2.0/clusters/list", "/api/2.0/sql/warehouses"):
                url = reader.allow(origin + path)
                with self.assertRaises(e.EvidenceError):
                    reader.request("GET", url, "dbx_test")
            self.assertEqual(len(reader.opener.calls), 1 if gated else 2, failure)

    def test_cost_queries_never_exceed_the_concurrency_limit(self):
        e = load_engine(cross_tenant=False)
        active, peak, lock = [0], [0], threading.Lock()
        url = e.ARM_ORIGIN + "/subscriptions/" + SUBSCRIPTION + "/providers/Microsoft.CostManagement/query?api-version=2023-11-01"

        def handler(request):
            with lock:
                active[0] += 1
                peak[0] = max(peak[0], active[0])
            time.sleep(0.2)
            with lock:
                active[0] -= 1
            return Response({"properties": {"columns": [], "rows": []}})

        def one():
            reader = self.reader(e, handler)
            reader.request("POST", reader.allow(url, "POST"), "azure_cost", body={})
        threads = [threading.Thread(target=one) for _ in range(6)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        self.assertEqual(peak[0], e.COST_CONCURRENCY)

    def test_workspace_and_managed_resource_group_cost_scope_query_and_split(self):
        e = load_engine(cross_tenant=False)
        config = e.validate_config(WORKSPACE_NAME)
        config["cost_scope"] = "workspace_and_managed_resource_group"
        seen = {}
        disk = "/subscriptions/" + SUBSCRIPTION + "/resourcegroups/databricks-rg-x/providers/microsoft.compute/disks/d1"

        def handler(request):
            seen["body"] = json.loads(request.data)
            return Response({"properties": {"columns": [{"name": "PreTaxCost"}, {"name": "ResourceId"}, {"name": "Currency"}],
                                            "rows": [[120.5, WORKSPACE_ID.lower(), "EUR"], [30.25, disk, "EUR"]]}})
        reader = self.reader(e, handler)
        rows, receipt = e.collect_cost(reader, config, REFERENCE, [], {"managed_resource_group": "databricks-rg-x"})
        parts = seen["body"]["dataset"]["filter"]["or"]
        self.assertEqual(parts[0]["dimensions"]["values"], [WORKSPACE_ID.lower()])
        self.assertEqual(parts[1]["dimensions"], {"name": "ResourceGroupName", "operator": "In", "values": ["databricks-rg-x"]})
        self.assertEqual((receipt["status"], len(rows), receipt["scope"]), ("complete", 2, "/subscriptions/" + SUBSCRIPTION))
        cost = e.run_cost_summary({"finops": {"currency": "EUR", "actual_cost": 150.75, "cost_rows": rows}, "sources": [receipt]}, config)
        self.assertEqual((cost["dbu"], cost["infra"]), (120.5, 30.25))

    def test_detailed_cost_plan_stops_after_a_throttled_query(self):
        e = load_engine(cross_tenant=False)
        raw = fixture(e)
        config = e.validate_config(WORKSPACE_NAME)
        calls = []

        def fake(reader, method, url, source, body=None, allow_empty=False):
            calls.append(body)
            raise e.EvidenceError("throttled", "Read returned HTTP 429.", source, 429)
        with patch.object(e.HttpReader, "request", new=fake):
            data, receipt = e.collect_databricks_costs(FakeIdentity(), config, REFERENCE, raw["workspace"], raw["inventory"])
        statuses = [q["status"] for q in data["queries"].values()]
        self.assertEqual(len(calls), 1)
        self.assertGreater(len(statuses), 1)
        self.assertEqual(statuses[0], "error")
        self.assertTrue(all(s == "skipped" for s in statuses[1:]))
        self.assertEqual((receipt["status"], receipt["errors"][0]["code"]), ("error", "throttled"))

    def test_outbound_endpoints_404_is_not_applicable_without_vnet_injection(self):
        e = load_engine(cross_tenant=False)
        config = e.validate_config(WORKSPACE_NAME)
        config.update(workspace_api_enabled=False, unity_catalog_enabled=False, include_managed_resource_group=False, advisor_enabled=False,
                      cost_scope="disabled", cost_analysis_enabled=False)

        def fake_request(reader, method, url, source, body=None, allow_empty=False):
            if source == "arm_workspace":
                return {"id": WORKSPACE_ID, "name": WORKSPACE_NAME, "location": "westeurope", "sku": {"name": "premium"},
                        "properties": {"workspaceUrl": WORKSPACE_HOST, "provisioningState": "Succeeded"}}
            if source == "arm_outbound_endpoints":
                raise e.EvidenceError("http_error", "Read returned HTTP 404; response bodies are excluded.", source, 404)
            return {"value": []}
        ident = MagicMock()
        ident.deadline = time.monotonic() + 60
        with patch.object(e, "Identity", return_value=ident), patch.object(e.HttpReader, "request", new=fake_request):
            raw = e.collect_live(config, REFERENCE)
        outbound = next(s for s in raw["sources"] if s["id"] == "arm_outbound_endpoints")
        self.assertEqual((outbound["status"], outbound["errors"]), ("not_applicable", []))


class FleetCollectionTests(FleetTestCase):
    def fleet(self, n=8, subs=3, variants=None, delays=None, **overrides):
        e = self.engine([arg_row(i, i % subs, "dbw-%02d" % i) for i in range(n)])
        for key, value in overrides.items():
            setattr(e, key, value)
        variants, delays, seen = variants or {}, delays or {}, {}

        def fake_collect_live(config, reference, deadline=None):
            seen[config["name"]] = config
            end = time.monotonic() + delays.get(config["name"], 0.02)
            while time.monotonic() < end and (deadline is None or time.monotonic() < deadline):
                time.sleep(0.02)
            variant = variants.get(config["name"], "ok")
            if variant == "error":
                raise e.EvidenceError("access_denied", "Read returned HTTP 403.", "arm_workspace", 403)
            if variant == "crash":
                raise KeyError("unexpected")
            raw = self.raw_for(e, config)
            for source in raw["sources"]:
                if variant == "denied" and source["id"].startswith(("dbx_", "uc_")) and source["id"] != "uc_system_lineage":
                    source.update(status="denied", records=0, errors=[{"code": "access_denied", "message": "HTTP 403", "source_id": source["id"], "http_status": 403}])
            if variant == "denied":
                for key in ("clusters", "instance_pools", "cluster_policies", "jobs", "pipelines", "sql_warehouses", "secret_scopes", "uc_catalogs", "uc_schemas"):
                    raw["inventory"][key] = []
            return raw
        e.collect_live = fake_collect_live
        e.TEST_SEEN = seen
        return e

    def test_parallel_fleet_statuses_access_envelope_and_files(self):
        e = self.fleet(n=8, variants={"dbw-01": "denied", "dbw-02": "error", "dbw-03": "crash"}, delays={"dbw-04": 30},
                       FLEET_COLLECTION_SECONDS=3, FLEET_HARD_STOP_SECONDS=5)
        with tempfile.TemporaryDirectory() as directory, cwd(directory):
            started = time.monotonic()
            out = e.main(operation="report", workspace_names="all")
            self.assertLess(time.monotonic() - started, 8)
            self.assertEqual(out["artifact_status"], "written")
            self.assertLessEqual(e.response_bytes(out), 3500)
            doc = json.loads(Path(out["snapshot_path"]).read_text(encoding="utf-8"))
            html = Path(out["report_path"]).read_text(encoding="utf-8")
        runs = {r["workspace_name"]: r for r in doc["workspace_runs"]}
        self.assertEqual(runs["dbw-01"]["fleet_row"]["workspace_access"]["status"], "denied")
        self.assertFalse(runs["dbw-01"]["snapshot"]["workspace_access"]["in_workspace"])
        self.assertEqual((runs["dbw-02"]["status"], runs["dbw-02"]["error"]["code"]), ("error", "access_denied"))
        self.assertEqual((runs["dbw-03"]["status"], runs["dbw-03"]["error"]["code"]), ("error", "collector_exception"))
        self.assertTrue(runs["dbw-00"]["fleet_row"]["workspace_access"]["in_workspace"])
        self.assertEqual(out["fleet"]["workspaces"], 8)
        self.assertEqual(out["fleet"]["without_workspace_access"], 1)
        self.assertEqual(out["fleet"]["detailed_cost_analysis"], "skipped_above_5_workspaces")
        self.assertTrue(all(c.get("fleet_cost_analysis_skipped") for c in e.TEST_SEEN.values()))
        self.assertIn('id="fleet-sub-filter"', html)

    def test_hard_stop_marks_unfinished_workspaces_as_errors_never_healthy(self):
        e = self.fleet(n=4, subs=1, delays={"dbw-00": 30}, FLEET_COLLECTION_SECONDS=1, FLEET_HARD_STOP_SECONDS=2, FLEET_WORKERS=2)
        e.ROSTER = e.effective_roster()
        configs = e.selection_configs("", "", "")[0]
        hang = e.collect_live

        def slow(config, reference, deadline=None):
            if config["name"] == "dbw-00":
                time.sleep(6)
            else:
                time.sleep(1.2)
            return hang(config, reference, deadline)
        e.collect_live = slow
        started = time.monotonic()
        runs = {r["workspace_name"]: r for r in e.collect_fleet(configs)}
        self.assertLess(time.monotonic() - started, 4)
        self.assertEqual(runs["dbw-00"]["error"]["code"], "collection_timeout")
        self.assertTrue(all(r["status"] == "error" for name, r in runs.items() if name not in ("dbw-01",)))

    def test_one_name_gives_the_detailed_report_with_access_and_small_fleets_keep_cost_analysis(self):
        e = self.fleet(n=3, variants={"dbw-01": "denied"})
        with tempfile.TemporaryDirectory() as directory, cwd(directory):
            out = e.main(operation="report", workspace_name="dbw-01")
            self.assertEqual(out["workspace_access"]["status"], "denied")
            self.assertLessEqual(e.response_bytes(out), 3500)
            fleet_out = e.main(operation="report", workspace_names="dbw-00,dbw-02")
        self.assertEqual(fleet_out["fleet"]["detailed_cost_analysis"], "per_workspace")
        self.assertFalse(any(c.get("fleet_cost_analysis_skipped") for c in e.TEST_SEEN.values()))


class FleetBrowserTests(FleetTestCase):
    def test_fleet_report_filters_detail_and_error_views(self):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            self.skipTest("Playwright not installed")
        e = FleetCollectionTests.fleet(self, n=6, subs=3, variants={"dbw-01": "denied", "dbw-02": "error"})
        with tempfile.TemporaryDirectory() as directory, cwd(directory):
            out = e.main(operation="report", workspace_names="all")
            html = Path(out["report_path"]).read_text(encoding="utf-8")
        with sync_playwright() as p:
            browser = p.chromium.launch(**({"headless": True, "channel": "msedge"} if sys.platform == "win32" else {"headless": True}))
            try:
                page = browser.new_page(viewport={"width": 1440, "height": 900})
                errors = []
                page.on("pageerror", lambda exc: errors.append(str(exc)))
                page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
                page.set_content(html, wait_until="load")
                self.assertFalse(page.locator("#fleet-view").is_hidden())
                self.assertTrue(page.locator("#report-body").is_hidden())
                self.assertEqual(page.locator("#fleet-table tbody tr").count(), 6)
                self.assertEqual(page.locator("#fleet-sub-filter option").count(), 4)
                page.select_option("#fleet-sub-filter", sub_id(1))
                self.assertEqual(page.locator("#fleet-table tbody tr").count(), 2)
                self.assertEqual(page.locator("#workspace-selector option").count(), 3)
                self.assertEqual(page.locator("#fleet-kpis .kpi .v").first.inner_text().strip(), "2")
                page.select_option("#fleet-sub-filter", "all")
                page.fill("#fleet-search", "dbw-05")
                self.assertEqual(page.locator("#fleet-table tbody tr").count(), 1)
                page.fill("#fleet-search", "")
                page.select_option("#workspace-selector", label=page.locator("#workspace-selector option", has_text="dbw-01").inner_text())
                self.assertFalse(page.locator("#report-body").is_hidden())
                self.assertFalse(page.locator("#access-banner").is_hidden())
                page.select_option("#workspace-selector", label=page.locator("#workspace-selector option", has_text="dbw-02").inner_text())
                self.assertFalse(page.locator("#workspace-error-view").is_hidden())
                page.select_option("#workspace-selector", "all")
                self.assertFalse(page.locator("#fleet-view").is_hidden())
                page.locator("#fleet-table .fleet-ws").first.click()
                self.assertFalse(page.locator("#report-body").is_hidden())
                self.assertEqual(errors, [])
            finally:
                browser.close()


if __name__ == "__main__":
    unittest.main()

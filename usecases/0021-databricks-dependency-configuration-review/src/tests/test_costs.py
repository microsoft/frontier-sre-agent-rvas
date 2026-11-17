"""Databricks cost module (section 6): Cost Management queries, throttling, denial, model, system tables guard, self_test."""

import json
import os
import tempfile
import time
import unittest
from contextlib import contextmanager
from datetime import date
from email.message import Message
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from support import MANAGED_RG, REFERENCE, SUBSCRIPTION, WORKSPACE_HOST, WORKSPACE_ID, fixture, load_engine

AP_TAGS = {"ClusterName": "bi-shared", "Vendor": "Databricks", "team": "sales"}
JOB_TAGS = {"ClusterName": "job-77-run-1", "JobId": "77", "Vendor": "Databricks", "team": "data"}
# REFERENCE is 2026-10-16: review month 2026-09, previous 2026-08, current 2026-10 (month to date)
ITEMS = (
    ("2026-08-10", AP_TAGS, "Azure Databricks", "Premium All-purpose Compute DBU", 800.0),
    ("2026-08-10", AP_TAGS, "Virtual Machines", "D4ds v5", 400.0),
    ("2026-09-05", AP_TAGS, "Azure Databricks", "Premium All-purpose Compute DBU", 1000.0),
    ("2026-09-07", AP_TAGS, "Virtual Machines", "D4ds v5", 600.0),
    ("2026-09-08", JOB_TAGS, "Azure Databricks", "Premium Jobs Compute DBU", 300.0),
    ("2026-09-08", {}, "Storage", "Hot LRS Data Stored", 100.0),
    ("2026-09-09", {}, "Azure Databricks", "Premium Serverless SQL DBU", 50.0),
    ("2026-10-05", AP_TAGS, "Azure Databricks", "Premium All-purpose Compute DBU", 500.0),
)


@contextmanager
def cwd(path):
    original = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(original)


class FakeIdentity:
    def __init__(self, seconds=400):
        self.deadline = time.monotonic() + seconds

    def arm_token(self):
        return "token"

    def databricks_token(self):
        return "token"

    def _guard_budget(self):
        return None


def cost_management(body):
    """Aggregate ITEMS exactly like the Cost Management query API would for this body."""
    dataset = body["dataset"]
    daily = dataset["granularity"] == "Daily"
    tag = next((g["name"] for g in dataset["grouping"] if g["type"] == "TagKey"), None)
    dims = [g["name"] for g in dataset["grouping"] if g["type"] == "Dimension"]
    start, end = body["timePeriod"]["from"][:10], body["timePeriod"]["to"][:10]
    extra = dataset["filter"]["and"][1]["tags"] if "and" in dataset["filter"] else None
    totals = {}
    for day, tags, category, meter, cost in ITEMS:
        if not start <= day <= end:
            continue
        value = tags.get(tag) if tag else None
        if extra and tags.get(extra["name"]) not in extra["values"]:
            continue
        period = int(day.replace("-", "")) if daily else day[:7] + "-01T00:00:00"
        key = (period, value, category if "MeterCategory" in dims else None, meter if "Meter" in dims else None)
        totals[key] = totals.get(key, 0.0) + cost
    columns = [{"name": "Cost"}, {"name": "UsageDate" if daily else "BillingMonth"}]
    columns += [{"name": "TagKey"}, {"name": "TagValue"}] if tag else []
    columns += [{"name": d} for d in dims] + [{"name": "Currency"}]
    rows = []
    for (period, value, category, meter), cost in sorted(totals.items(), key=lambda kv: str(kv[0])):
        row = [cost, period] + ([tag.lower(), value] if tag else [])
        row += [category] if "MeterCategory" in dims else []
        row += [meter] if "Meter" in dims else []
        rows.append(row + ["EUR"])
    return {"properties": {"columns": columns, "rows": rows, "nextLink": None}}


class Response:
    def __init__(self, payload):
        self.status, self.payload = 200, json.dumps(payload).encode("utf-8")

    def read(self, limit):
        return self.payload[:limit]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class Opener:
    def __init__(self, outcomes):
        self.outcomes, self.calls = list(outcomes), 0

    def open(self, request, timeout):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return Response(outcome)


def throttled(seconds="2"):
    headers = Message()
    headers["x-ms-ratelimit-microsoft.costmanagement-entity-retry-after"] = seconds
    return HTTPError("https://management.azure.com/", 429, "Too Many Requests", headers, None)


class CostTests(unittest.TestCase):
    def setUp(self):
        self.e = load_engine()
        self.raw = fixture(self.e)
        self.config = self.e.validate_config("")
        self.url = "https://management.azure.com/subscriptions/" + SUBSCRIPTION + "/providers/Microsoft.CostManagement/query?api-version=" + self.e.COST_API_VERSION

    def collect(self, fake):
        with patch.object(self.e.HttpReader, "request", new=fake):
            return self.e.collect_databricks_costs(FakeIdentity(), self.config, REFERENCE, self.raw["workspace"], self.raw["inventory"])

    def test_queries_are_scoped_read_only_posts_and_the_model_reconciles(self):
        calls = []

        def fake(reader_self, method, url, source, body=None, allow_empty=False):
            calls.append((method, url, reader_self.patient))
            return cost_management(body)

        data, receipt = self.collect(fake)
        self.assertEqual(receipt["status"], "complete")
        self.assertTrue(all(c == ("POST", self.url, True) for c in calls))
        bodies = dict(self.e.cost_query_plan(self.e.cost_periods(REFERENCE), {"x": 1}, self.raw["inventory"]))
        self.assertTrue({"meter", "vendor", "cluster", "job", "warehouse", "pool", "tag:team", "tag:project", "tag:cost_center"} <= set(bodies))
        self.assertTrue(all(b["type"] == "AmortizedCost" for b in bodies.values()))
        self.assertEqual(data["scope"]["resource_ids"], [WORKSPACE_ID.lower()])
        self.assertEqual(data["scope"]["managed_resource_group"].lower(), MANAGED_RG.lower())

        raw = dict(self.raw, dbx_cost_data=data, sources=self.raw["sources"] + [receipt])
        model = self.e.databricks_costs_for(raw, REFERENCE)
        head = model["headline"]
        self.assertEqual((model["status"], model["currency"]), ("complete", "EUR"))
        self.assertEqual((head["review_month"], head["previous_month"]), ("2026-09", "2026-08"))
        self.assertEqual((head["review_total"], head["dbu_total"], head["infra_total"]), (2050.0, 1350.0, 700.0))
        self.assertEqual((head["previous_total"], head["mtd_total"]), (1200.0, 500.0))
        # the gap is cost without the Vendor tag Databricks puts on classic compute: storage plus serverless DBUs
        self.assertEqual(model["attribution"]["gap"]["total"], 150.0)
        self.assertEqual(head["unattributed_share"], 7.3)
        team = next(t for t in model["attribution"]["custom_tags"] if t["tag"] == "team")
        self.assertEqual(team["tagged_share"], 92.7)
        clusters = {r["key"]: r for r in model["attribution"]["rows"] if r["dimension"] == "cluster"}
        self.assertEqual((clusters["bi-shared"]["total"], clusters["bi-shared"]["dbu"], clusters["bi-shared"]["infra"]), (1600.0, 1000.0, 600.0))
        self.assertEqual((clusters["job-runs"]["kind"], clusters["job-runs"]["total"]), ("job_runs", 300.0))

    def test_denied_cost_read_is_reported_not_zero(self):
        def fake(reader_self, method, url, source, body=None, allow_empty=False):
            raise self.e.EvidenceError("access_denied", "Read returned HTTP 403.", source, 403)

        data, receipt = self.collect(fake)
        self.assertEqual(receipt["status"], "denied")
        self.assertIn("Cost Management Reader", receipt["note"])
        self.assertTrue(all(q["status"] == "denied" and q["rows"] == [] for q in data["queries"].values()))
        model = self.e.databricks_costs_for(dict(self.raw, dbx_cost_data=data, sources=self.raw["sources"] + [receipt]), REFERENCE)
        self.assertEqual(model["status"], "denied")
        self.assertIsNone(model["headline"]["estimated_monthly_savings"])
        self.assertNotIn("review_total", model["headline"])

    def test_cost_management_throttling_is_patient_and_bounded(self):
        ok = {"properties": {"columns": [{"name": "Cost"}, {"name": "Currency"}], "rows": []}}
        reader = self.e.HttpReader(FakeIdentity(), self.e.ARM_ORIGIN, "arm", patient=True)
        reader.allow(self.url, "POST")
        reader.opener = Opener([throttled("2"), ok])
        with patch.object(self.e.time, "sleep") as sleep:
            self.assertEqual(reader.request("POST", self.url, "azure_cost_databricks", body={}), ok)
        sleep.assert_called_once_with(3)

        reader.opener = Opener([throttled("2")] * 5)
        with patch.object(self.e.time, "sleep"), self.assertRaises(self.e.EvidenceError) as caught:
            reader.request("POST", self.url, "azure_cost_databricks", body={})
        self.assertEqual((caught.exception.code, reader.opener.calls), ("throttled", 5))

        hurried = self.e.HttpReader(FakeIdentity(seconds=5), self.e.ARM_ORIGIN, "arm", patient=True)
        hurried.allow(self.url, "POST")
        hurried.opener = Opener([throttled("20"), ok])
        with patch.object(self.e.time, "sleep") as sleep, self.assertRaises(self.e.EvidenceError):
            hurried.request("POST", self.url, "azure_cost_databricks", body={})
        sleep.assert_not_called()

    def test_system_tables_are_off_by_default_and_only_run_the_fixed_statement(self):
        with patch.object(self.e, "StatementReader") as statement_reader:
            data, receipt = self.e.collect_system_billing(FakeIdentity(), self.config, REFERENCE, {})
        statement_reader.assert_not_called()
        self.assertIsNone(data)
        self.assertEqual(receipt["status"], "not_configured")

        origin = "https://" + WORKSPACE_HOST
        with self.assertRaises(self.e.EvidenceError):
            self.e.HttpReader(FakeIdentity(), origin, "databricks").allow(origin + "/api/2.0/sql/statements", "POST")
        reader = self.e.StatementReader(FakeIdentity(), origin)
        for url, method in ((origin + "/api/2.0/sql/statements", "GET"), (origin + "/api/2.0/sql/statements/abc/cancel", "POST")):
            with self.subTest(url=url, method=method), self.assertRaises(self.e.EvidenceError):
                reader.allow(url, method)
        url = reader.allow(origin + "/api/2.0/sql/statements", "POST")
        with self.assertRaises(self.e.EvidenceError) as caught:
            reader.request("POST", url, "dbx_system_billing", body={"statement": "DELETE FROM main.sales.orders"})
        self.assertEqual(caught.exception.code, "unsafe_statement")

        sent = []

        def fake(reader_self, method, url, source, body=None, allow_empty=False):
            sent.append(body)
            return {
                "status": {"state": "SUCCEEDED"},
                "manifest": {"schema": {"columns": [{"name": "row_type"}, {"name": "product"}, {"name": "run_as"}, {"name": "dbus"}, {"name": "list_cost"}, {"name": "currency"}]}, "truncated": False},
                "result": {"data_array": [["user", None, "etl@example.com", "120.5", "60.25", "USD"]]},
            }

        enabled = dict(self.config, system_tables_warehouse_id="a1b2c3d4e5f60718")
        with patch.object(self.e.HttpReader, "request", new=fake):
            data, receipt = self.e.collect_system_billing(FakeIdentity(), enabled, REFERENCE, {})
        self.assertEqual(receipt["status"], "complete")
        self.assertEqual(sent[0]["statement"], self.e.SYSTEM_BILLING_STATEMENT)
        self.assertEqual({p["name"]: p["value"] for p in sent[0]["parameters"]},
                         {"workspace_id": "1234567890123456", "start_date": "2026-09-01", "end_date": "2026-10-01"})
        self.assertEqual(data["rows"][0]["list_cost"], 60.25)

    def test_simulated_model_counts_one_saving_per_object(self):
        reference = "2026-11-12T10:00:00Z"
        model = self.e.databricks_costs_for(self.e.demo_raw(reference), reference)
        signals = model["signals"]
        counted = [s for s in signals if s["counted"]]
        objects = [s["object_id"] for s in counted]
        self.assertEqual(len(objects), len(set(objects)))
        for s in signals:
            if s["estimated_monthly_saving"] and not s["counted"]:
                best = max(o["estimated_monthly_saving"] or 0 for o in signals if o["object_id"] == s["object_id"])
                self.assertGreaterEqual(best, s["estimated_monthly_saving"])
        self.assertEqual(model["headline"]["estimated_monthly_savings"], round(sum(s["estimated_monthly_saving"] for s in counted), 2))
        self.assertTrue({"AUTOTERM_OFF", "JOBS_ON_ALL_PURPOSE", "NO_SPOT", "POOL_IDLE", "WAREHOUSE_AUTOSTOP", "MISSING_ALLOCATION_TAGS"}
                        <= {s["code"] for s in signals})
        months = model["monthly"]
        self.assertEqual(round(sum(r["total"] for r in model["attribution"]["rows"] if r["dimension"] == "cluster")
                               + next(d for d in model["attribution"]["dimensions"] if d["key"] == "cluster")["untagged_total"], 2),
                         next(m["total"] for m in months if m["month"] == model["periods"]["review"]))

    def test_self_test_is_offline_and_labelled_simulated(self):
        def no_network(*args, **kwargs):
            raise AssertionError("self_test must not reach the network")

        with tempfile.TemporaryDirectory() as tmp, cwd(tmp), patch.object(self.e, "Identity", side_effect=no_network), \
                patch.object(self.e.HttpReader, "request", new=no_network):
            result = self.e.main(operation="self_test")
            files = sorted(p.name for p in (Path(tmp) / "databricks-dependency-reports").iterdir())
            snapshot = json.loads(Path(result["snapshot_path"]).read_text(encoding="utf-8"))
        self.assertEqual((result["operation"], result["collection"]["provenance"]), ("self_test", "SIMULATED"))
        self.assertEqual(len(files), 4)
        self.assertTrue(all(name.startswith("simulated-") for name in files))
        self.assertEqual(result["databricks_costs"]["status"], "complete")
        self.assertLessEqual(self.e.response_bytes(result), 3500)
        self.assertEqual(snapshot["databricks_costs"]["system_tables"]["status"], "complete")
        self.assertEqual(snapshot["presentation"]["focus"], "configuration")
        with self.assertRaises(self.e.EvidenceError):
            self.e.validate_parameters("self_test", "summary", "dbx-prod-weu-01", "", "", "all", "all", "all", "all", "all", 25, 0)

    def test_costs_view_rows_fit_the_transport_budget(self):
        reference = "2026-11-12T10:00:00Z"
        raw = self.e.demo_raw(reference)
        snap = self.e.finish_snapshot(raw, reference, "SIMULATED", "PRODUCTION")
        params = self.e.validate_parameters("query", "costs", "", "", "", "all", "all", "all", "all", "all", 25, 0)
        result = self.e.query_snapshot(snap, params)
        self.assertEqual(result["rows"][0]["record_type"], "headline")
        self.assertLessEqual(self.e.response_bytes(result), 3500)
        self.assertIn("signal", {r["record_type"] for r in result["rows"]})

    def test_presentation_hooks_reject_unsafe_values(self):
        self.assertEqual(self.e.presentation_settings()["focus"], "configuration")
        woff2 = "data:font/woff2;base64," + __import__("base64").b64encode(b"wOF2" + b"\0" * 2000).decode("ascii")
        for name, value in (
            ("REPORT_FOCUS", "everything"),
            ("BRAND_LOGO_PLACEMENT", "footer"),
            ("BRAND_THEME", {"--paper": "url(https://evil.invalid/x.png)"}),
            ("BRAND_THEME", {"--unknown": "#FFFFFF"}),
            ("BRAND_DISPLAY_FONT_DATA_URI", "data:font/ttf;base64,AAAA"),
            ("BRAND_DISPLAY_FONT_DATA_URI", "data:font/woff2;base64," + "A" * 2000),
        ):
            with self.subTest(name=name, value=value), patch.object(self.e, name, value), self.assertRaises(self.e.EvidenceError):
                self.e.presentation_settings()
        with patch.object(self.e, "BRAND_THEME", {"--btn": "#B81B25", "--hero-line": "rgba(225,215,175,.24)"}), \
                patch.object(self.e, "BRAND_DISPLAY_FONT_DATA_URI", woff2), patch.object(self.e, "REPORT_FOCUS", "costs"):
            settings = self.e.presentation_settings()
        self.assertEqual((settings["focus"], settings["theme"]["--btn"]), ("costs", "#B81B25"))
        with patch.object(self.e, "COST_ALLOCATION_TAGS", ["team", "team"]), self.assertRaises(self.e.EvidenceError):
            self.e.validate_cost_settings()

    def test_daily_query_uses_review_month_days(self):
        periods = self.e.cost_periods(REFERENCE)
        self.assertEqual((periods["review_start"], periods["review_end"], periods["previous_start"]),
                         (date(2026, 9, 1), date(2026, 9, 30), date(2026, 8, 1)))
        self.assertEqual(periods["labels"]["review_weekend_days"], 8)


if __name__ == "__main__":
    unittest.main()

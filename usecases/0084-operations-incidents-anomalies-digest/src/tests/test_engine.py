import copy
import inspect
import json
import os
import sys
import tempfile
import types
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

from support import CLIENT_ID, REFERENCE, ROOT, SUBSCRIPTION, TENANT, WORKSPACES, fixture, load_engine, make_jwt


@contextmanager
def cwd(path):
    original = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(original)


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.e = load_engine()
        self.window = self.e.compute_window("previous_month", REFERENCE)
        self.raw = fixture(self.e, "previous_month")
        self.config = self.e.validate_config()

    def snapshot(self, period="previous_month"):
        win = self.e.compute_window(period, REFERENCE)
        raw = fixture(self.e, period)
        return self.e.finish_snapshot(raw, win, REFERENCE, "SIMULATED")

    def params(self, **kwargs):
        values = {key: value.default for key, value in inspect.signature(self.e.main).parameters.items()}
        values.update(operation="query", reference_utc=REFERENCE, **kwargs)
        return self.e.validate_parameters(**values)

    def test_parameters_schema_defaults_types_and_bounds(self):
        schema = json.loads((ROOT / "tool-parameters.schema.json").read_text(encoding="utf-8"))
        signature = inspect.signature(self.e.main)
        self.assertEqual(list(signature.parameters.keys()), [
            "operation", "period", "view", "category", "severity", "resource_name", "limit", "offset"
        ])
        self.assertEqual(set(schema["properties"]), set(signature.parameters))
        for name, parameter in signature.parameters.items():
            self.assertEqual(parameter.default, schema["properties"][name]["default"])
            self.assertEqual("integer" if parameter.annotation is int else "string", schema["properties"][name]["type"])

        for period in ("previous_month", "last_30d", "last_7d", "last_24h"):
            p = self.params(period=period)
            self.assertEqual(p["window"]["period"], period)

        self.params(limit=1, offset=0)
        self.params(limit=100, offset=500000)
        self.params(view="anomalies", category="extension_failure", severity="high", resource_name="arc-win2k25-01")

        for invalid in (
            dict(limit=0),
            dict(limit=101),
            dict(limit=True),
            dict(offset=-1),
            dict(offset=500001),
            dict(period="yearly"),
            dict(view="unknown"),
            dict(category="invalid_cat"),
            dict(severity="urgent"),
            dict(resource_name="../../etc/passwd"),
            dict(resource_name="https://evil.invalid/test"),
            dict(view="summary", category="native_alert"),
            dict(view="coverage", severity="high"),
            dict(view="resources", category="native_alert"),
            dict(view="incidents", category="extension_failure"),
            dict(view="anomalies", category="native_alert"),
            dict(view="advisor", category="telemetry_anomaly"),
        ):
            with self.subTest(invalid=invalid), self.assertRaises(self.e.EvidenceError):
                self.params(**invalid)

    def test_report_supports_all_periods_and_rejects_query_filters(self):
        defaults = {key: value.default for key, value in inspect.signature(self.e.main).parameters.items()}
        for period in ("previous_month", "last_30d", "last_7d", "last_24h"):
            validated = self.e.validate_parameters(**{**defaults, "period": period}, reference_utc=REFERENCE)
            self.assertEqual(validated["period"], period)

        for changes in (
            dict(view="incidents"),
            dict(category="native_alert"),
            dict(severity="high"),
            dict(resource_name="arc-win2k25-01"),
            dict(limit=10),
            dict(offset=5),
        ):
            with self.subTest(changes=changes), self.assertRaises(self.e.EvidenceError):
                self.e.validate_parameters(**{**defaults, **changes}, reference_utc=REFERENCE)

    def test_default_placeholders_fail_before_auth_or_network(self):
        with patch.object(self.e, "SUBSCRIPTION_ID", "<YOUR_SUBSCRIPTION_ID>"), patch.object(self.e, "Identity") as identity:
            result = self.e.main()
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"]["code"], "configuration_required")
        self.assertEqual(result["artifact_status"], "not_written")
        identity.assert_not_called()
        self.assertLessEqual(len(json.dumps(result).encode("utf-8")), 3500)

    def test_five_evidence_streams_consolidation_and_actions_synthesis(self):
        snap = self.snapshot("previous_month")
        counts = snap["counts"]
        self.assertEqual(counts["native_alerts_total"], 2)
        self.assertEqual(counts["service_health_total"], 1)
        self.assertEqual(counts["incidents_total"], 3)
        self.assertEqual(counts["extension_failures_total"], 2)
        self.assertGreaterEqual(counts["connectivity_posture_total"], 2)
        self.assertEqual(counts["telemetry_anomalies_total"], 3)
        self.assertEqual(counts["advisor_recommendations_total"], 1)
        self.assertGreaterEqual(counts["actions_total"], 7)

        # Verify MDE.Windows and AADLoginForWindows extension failures are captured
        ext_anoms = [a for a in snap["anomalies"] if a["category"] == "extension_failure"]
        ext_names = {a["extension_name"] for a in ext_anoms}
        self.assertEqual(ext_names, {"MDE.Windows", "AADLoginForWindows"})

        # Verify Arc Expired and AKS Stopped posture anomalies are captured
        posture_kinds = {a["anomaly_kind"] for a in snap["anomalies"] if a["category"] == "connectivity_posture"}
        self.assertIn("arc_agent_expired", posture_kinds)
        self.assertIn("aks_cluster_non_running", posture_kinds)

        # Verify actions have priorities, valid horizons, linked evidence IDs, and Learn URLs
        ranks = [act["priority_rank"] for act in snap["actions"]]
        self.assertEqual(ranks, list(range(1, len(snap["actions"]) + 1)))
        self.assertTrue(all(act["horizon"] in ("immediate_24h", "short_term_7d", "monthly_cycle") for act in snap["actions"]))
        self.assertTrue(all(len(act["linked_evidence_ids"]) >= 1 for act in snap["actions"]))
        self.assertTrue(all(act["learn_url"].startswith("https://learn.microsoft.com/") for act in snap["actions"]))

    def test_secret_tag_filtering_and_endpoint_guards(self):
        snap = self.snapshot()
        serialized = json.dumps(snap)
        self.assertNotIn("DO-NOT-EXPORT", serialized)

        dummy_ident = MagicMock()
        arm_reader = self.e.HttpReader(dummy_ident, self.e.ARM_ORIGIN, "arm")
        for forbidden in (
            "https://management.azure.com/subscriptions/" + SUBSCRIPTION + "/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm1/runCommand",
            "https://management.azure.com/subscriptions/" + SUBSCRIPTION + "/resourceGroups/rg/providers/Microsoft.Storage/storageAccounts/st1/listKeys",
            "https://evil.example.com/providers/Microsoft.ResourceGraph/resources",
        ):
            with self.subTest(url=forbidden), self.assertRaises(self.e.EvidenceError):
                arm_reader.allow(forbidden, "POST")

    def test_collect_live_end_to_end_with_mocked_transports(self):
        fake_cred = MagicMock()
        fake_cred.get_token.side_effect = lambda scope: MagicMock(
            token=make_jwt(TENANT, CLIENT_ID, scope.removesuffix("/.default")),
            expires_on=9999999999,
        )
        fake_azure = types.ModuleType("azure")
        fake_identity_mod = types.ModuleType("azure.identity")
        fake_core_mod = types.ModuleType("azure.core")
        fake_exc_mod = types.ModuleType("azure.core.exceptions")
        fake_identity_mod.ManagedIdentityCredential = MagicMock(return_value=fake_cred)
        fake_identity_mod.CredentialUnavailableError = RuntimeError
        fake_exc_mod.ClientAuthenticationError = RuntimeError
        fake_exc_mod.ServiceRequestError = RuntimeError

        arc_id = (
            "/subscriptions/" + SUBSCRIPTION + "/resourceGroups/rg-arc-servers-weu"
            + "/providers/Microsoft.HybridCompute/machines/arc-win2k25-01"
        )

        def fake_request(reader_self, method, url, source, body=None):
            if source == "arg_alerts_incidents":
                return {
                    "data": [
                        {
                            "id": "/subscriptions/" + SUBSCRIPTION + "/providers/Microsoft.AlertsManagement/alerts/alr-live-1",
                            "name": "alr-live-1",
                            "severity": "Sev1",
                            "alertState": "New",
                            "monitorCondition": "Fired",
                            "signalType": "Metric",
                            "monitorService": "Platform",
                            "targetResource": arc_id,
                            "targetResourceName": "arc-win2k25-01",
                            "targetResourceGroup": "rg-arc-servers-weu",
                            "targetResourceType": "microsoft.hybridcompute/machines",
                            "startDateTime": "2026-09-20T10:00:00Z",
                            "lastModifiedDateTime": "2026-09-20T10:05:00Z",
                            "description": "Live test alert.",
                        }
                    ]
                }
            if source == "arm_service_health":
                return {"value": []}
            if source == "arg_posture_anomalies":
                return {
                    "data": [
                        {
                            "id": arc_id,
                            "name": "arc-win2k25-01",
                            "type": "microsoft.hybridcompute/machines",
                            "resourceGroup": "rg-arc-servers-weu",
                            "location": "westeurope",
                            "provisioningState": "Succeeded",
                            "arcStatus": "Expired",
                            "arcAgentVersion": "1.59.0",
                            "arcLastStatusChange": "2026-09-12T10:15:00Z",
                            "osName": "windows",
                        }
                    ]
                }
            if source == "arg_guest_extensions":
                return {
                    "data": [
                        {
                            "id": arc_id + "/extensions/MDE.Windows",
                            "name": "MDE.Windows",
                            "type": "microsoft.hybridcompute/machines/extensions",
                            "resourceGroup": "rg-arc-servers-weu",
                            "location": "westeurope",
                            "publisher": "Microsoft.EnterpriseCloud.Monitoring",
                            "extType": "MDE.Windows",
                            "version": "1.0.10.0",
                            "provisioningState": "Failed",
                        }
                    ]
                }
            if source == "logs_telemetry_anomalies":
                return {
                    "tables": [
                        {
                            "columns": [
                                {"name": "_ResourceId"},
                                {"name": "metric_key"},
                                {"name": "unit"},
                                {"name": "avg_val"},
                                {"name": "max_val"},
                                {"name": "min_val"},
                                {"name": "median_val"},
                                {"name": "p95_val"},
                                {"name": "high_bins"},
                                {"name": "low_mem_bins"},
                                {"name": "low_disk_bins"},
                                {"name": "bins_total"},
                                {"name": "sample_count"},
                                {"name": "last_seen_utc"},
                            ],
                            "rows": [
                                [
                                    arc_id.lower(),
                                    "cpu_percent",
                                    "Percent",
                                    89.0,
                                    96.5,
                                    40.0,
                                    52.0,
                                    93.0,
                                    4,
                                    0,
                                    0,
                                    24,
                                    720,
                                    "2026-09-20T12:00:00Z",
                                ]
                            ],
                        }
                    ]
                }
            if source == "arm_advisor_recommendations":
                return {"value": []}
            return {}

        with patch.dict(sys.modules, {
            "azure": fake_azure,
            "azure.identity": fake_identity_mod,
            "azure.core": fake_core_mod,
            "azure.core.exceptions": fake_exc_mod,
        }), patch.object(self.e.HttpReader, "request", new=fake_request):
            collected = self.e.collect_live(self.config, self.window, REFERENCE)
            snap = self.e.finish_snapshot(collected, self.window, REFERENCE, "LIVE")
            self.assertEqual(snap["counts"]["incidents_total"], 1)
            self.assertEqual(snap["counts"]["extension_failures_total"], 1)
            self.assertEqual(snap["counts"]["connectivity_posture_total"], 1)
            self.assertEqual(snap["counts"]["telemetry_anomalies_total"], 1)
            self.assertTrue(all(s["status"] == "complete" for s in snap["sources"]))

    def test_query_views_paging_and_3500_byte_transport_budget(self):
        snap = self.snapshot()
        for view_name in ("summary", "incidents", "anomalies", "actions", "resources", "advisor", "coverage"):
            res = self.e.query_snapshot(snap, self.params(view=view_name, limit=10))
            self.assertEqual(res["status"], "ok")
            self.assertGreater(res["total_matched"], 0)
            self.assertLessEqual(self.e.response_bytes(res), 3500)

        oversized = copy.deepcopy(snap)
        oversized["actions"] = [{"id": "ACT-BIG", "title": "X" * 4000, "category": "native_alert", "severity": "high"}]
        res_err = self.e.query_snapshot(oversized, self.params(view="actions", limit=5))
        self.assertEqual(res_err["status"], "error")
        self.assertEqual(res_err["error"]["code"], "query_row_too_large")
        self.assertLessEqual(self.e.response_bytes(res_err), 3500)


if __name__ == "__main__":
    unittest.main()

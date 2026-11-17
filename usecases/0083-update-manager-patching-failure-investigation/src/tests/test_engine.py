import copy
import inspect
import json
import os
import sys
import types
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

from support import CLIENT_ID, REFERENCE, ROOT, SUBSCRIPTION, fixture, load_engine, make_jwt, raw_arg_fixture


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
        self.raw = fixture(self.e)

    def snapshot(self):
        return self.e.finish_snapshot(self.raw, REFERENCE, "SIMULATED", "LAB")

    def params(self, **kwargs):
        values = {key: value.default for key, value in inspect.signature(self.e.main).parameters.items()}
        values.update(operation="query", **kwargs)
        return self.e.validate_parameters(**values)

    def test_parameters_schema_defaults_types_and_bounds(self):
        schema = json.loads((ROOT / "tool-parameters.schema.json").read_text(encoding="utf-8"))
        signature = inspect.signature(self.e.main)
        self.assertEqual(set(schema["properties"]), set(signature.parameters))
        self.assertEqual(len(signature.parameters), 8)
        for name, parameter in signature.parameters.items():
            self.assertEqual(parameter.default, schema["properties"][name]["default"])
            self.assertEqual("integer" if parameter.annotation is int else "string", schema["properties"][name]["type"])
        self.params(limit=1, offset=0)
        self.params(limit=100, offset=500000)
        for cat in self.e.FAILURE_CATEGORIES:
            self.params(failure_category=cat)
        for view in self.e.VIEWS:
            self.params(view=view)
        for invalid in (
            dict(limit=0),
            dict(limit=101),
            dict(limit=True),
            dict(offset=-1),
            dict(offset=500001),
            dict(machine_name="../../etc/passwd"),
            dict(machine_name="https://evil.invalid"),
            dict(view="unknown"),
            dict(hosting="aws"),
            dict(failure_category="unknown_cat"),
            dict(period="last_90d"),
        ):
            with self.subTest(invalid=invalid), self.assertRaises(self.e.EvidenceError):
                self.params(**invalid)

    def test_report_rejects_narrowing_and_paging(self):
        defaults = {key: value.default for key, value in inspect.signature(self.e.main).parameters.items()}
        self.e.validate_parameters(**defaults)
        self.e.validate_parameters(**{**defaults, "period": "last_14d"})
        for changes in (
            dict(machine_name="vm-arc-host-weu"),
            dict(view="failures"),
            dict(hosting="arc"),
            dict(failure_category="maintenance_window_unresponsive"),
            dict(limit=10),
            dict(offset=5),
        ):
            with self.subTest(changes=changes), self.assertRaises(self.e.EvidenceError):
                self.e.validate_parameters(**{**defaults, **changes})

    def test_default_code_fails_before_auth_or_network(self):
        with patch.object(self.e, "SUBSCRIPTION_ID", "<YOUR_SUBSCRIPTION_ID>"), patch.object(self.e, "Identity") as identity:
            result = self.e.main()
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"]["code"], "configuration_required")
        self.assertEqual(result["artifact_status"], "not_written")
        identity.assert_not_called()
        self.assertLessEqual(len(json.dumps(result).encode("utf-8")), 3500)

    def test_automated_root_cause_investigation_covers_all_categories(self):
        snap = self.snapshot()
        by_name = {m["name"]: m for m in snap["machines"]}

        # vm-arc-host-weu has both ShutdownOrUnresponsive maintenance cycles and HotpatchEnablementRequiredForReadiness
        client = by_name["vm-arc-host-weu"]
        self.assertEqual(client["failure_category"], "maintenance_window_unresponsive")
        self.assertIn("hotpatch_or_patch_extension_error", client["matched_categories"])
        self.assertEqual(client["maintenance_cycles_summary"]["unresponsive"], 1)
        self.assertEqual(client["maintenance_cycles_summary"]["succeeded"], 1)
        self.assertEqual(
            client["hotpatch"]["log_path"],
            r"C:\WindowsAzure\Logs\Plugins\Microsoft.CPlat.Core.WindowsPatchExtension\1.5.85",
        )

        # arc-sql-01 and arc-win2k22-01 have pending security/rollup patches with no maintenance assignment
        self.assertEqual(by_name["arc-sql-01"]["failure_category"], "pending_security_patches_unscheduled")
        self.assertEqual(by_name["arc-sql-01"]["pending_counts"]["security"], 3)
        self.assertEqual(by_name["arc-win2k22-01"]["failure_category"], "pending_security_patches_unscheduled")

        # arc-ubuntu-01 and 02 have InProgress assessment and UnableToDetermine guest patch readiness
        self.assertEqual(by_name["arc-ubuntu-01"]["failure_category"], "assessment_stuck_or_readiness_undetermined")
        self.assertEqual(by_name["arc-ubuntu-02"]["failure_category"], "assessment_stuck_or_readiness_undetermined")

        # vm-arc-win-01 has Expired Arc agent
        self.assertEqual(by_name["vm-arc-win-01"]["failure_category"], "arc_agent_expired_or_disconnected")
        self.assertEqual(by_name["vm-arc-win-01"]["severity"], "critical")

        # vm-arc-win-04 has Failed MDE.Windows extension
        self.assertEqual(by_name["vm-arc-win-04"]["failure_category"], "hotpatch_or_patch_extension_error")
        self.assertEqual(by_name["vm-arc-win-04"]["failed_extensions_count"], 1)

        # vm-linux-01 is deallocated with no Update Manager telemetry
        self.assertEqual(by_name["vm-linux-01"]["failure_category"], "unassessed_no_update_manager_telemetry")

        # vm-healthy-01 is assessed with 0 pending patches and 0 errors
        self.assertEqual(by_name["vm-healthy-01"]["failure_category"], "healthy")

        # Secret tags and extension settings are never exported
        serialized = json.dumps(snap)
        self.assertNotIn("DO-NOT-EXPORT", serialized)
        self.assertNotIn("protectedSettings", serialized)

    def test_all_query_views_and_filters_fit_transport_budget(self):
        snap = self.snapshot()
        for view in self.e.VIEWS:
            res = self.e.query_snapshot(snap, self.params(view=view, limit=25))
            self.assertEqual(res["status"], "ok")
            self.assertEqual(res["view"], view)
            self.assertGreaterEqual(res["returned"], 1)
            self.assertLessEqual(len(json.dumps(res).encode("utf-8")), 3500)

        arc_stuck = self.e.query_snapshot(
            snap,
            self.params(
                view="machines",
                hosting="arc",
                failure_category="assessment_stuck_or_readiness_undetermined",
            ),
        )
        self.assertEqual(arc_stuck["total_matched"], 2)
        self.assertEqual({r["machine_name"] for r in arc_stuck["rows"]}, {"arc-ubuntu-01", "arc-ubuntu-02"})

        hotpatch_matches = self.e.query_snapshot(
            snap,
            self.params(view="machines", failure_category="hotpatch_or_patch_extension_error"),
        )
        self.assertEqual({r["machine_name"] for r in hotpatch_matches["rows"]}, {"vm-arc-host-weu", "vm-arc-win-04"})

        single = self.e.query_snapshot(snap, self.params(view="failures", machine_name="vm-arc-host-weu"))
        self.assertEqual(single["total_matched"], 2)

    def test_live_arg_collector_validates_jwt_and_reads_all_seven_sources(self):
        config = self.e.validate_config()
        raw_tables = raw_arg_fixture()
        queries_to_sid = {q: sid for sid, q in self.e.arg_queries().items()}

        fake_cred = MagicMock()
        fake_cred.get_token.return_value = MagicMock(token=make_jwt(CLIENT_ID), expires_on=9999999999)

        def fake_open(req, timeout=30):
            body = json.loads((req.data or b"{}").decode("utf-8"))
            sid = queries_to_sid[body["query"]]
            resp = MagicMock()
            resp.status = 200
            resp.__enter__.return_value = resp
            resp.read.return_value = json.dumps({"data": raw_tables[sid]}).encode("utf-8")
            return resp

        fake_azure = types.ModuleType("azure")
        fake_identity = types.ModuleType("azure.identity")
        fake_core = types.ModuleType("azure.core")
        fake_exc = types.ModuleType("azure.core.exceptions")
        fake_identity.ManagedIdentityCredential = MagicMock(return_value=fake_cred)
        fake_identity.CredentialUnavailableError = RuntimeError
        fake_exc.ClientAuthenticationError = RuntimeError
        fake_exc.ServiceRequestError = RuntimeError

        with patch.dict(
            sys.modules,
            {
                "azure": fake_azure,
                "azure.identity": fake_identity,
                "azure.core": fake_core,
                "azure.core.exceptions": fake_exc,
            },
        ), patch.object(self.e, "build_opener") as mock_opener:
            opener_inst = MagicMock()
            opener_inst.open.side_effect = fake_open
            mock_opener.return_value = opener_inst
            collected = self.e.collect_live(config, "last_30d", REFERENCE)
            self.assertEqual(len(collected["sources"]), 7)
            self.assertTrue(all(s["status"] == "complete" for s in collected["sources"]))
            self.assertEqual(len(collected["machines"]), 9)

    def test_extension_settings_or_wrong_subscription_rejected(self):
        bad_ext = copy.deepcopy(raw_arg_fixture()["arg_patch_extensions"][0])
        bad_ext["properties"]["protectedSettings"] = {"secret": "leak"}
        with self.assertRaises(self.e.EvidenceError) as raised:
            self.e.normalize_extension(bad_ext, SUBSCRIPTION, REFERENCE)
        self.assertEqual(raised.exception.code, "sensitive_extension_settings_forbidden")


if __name__ == "__main__":
    unittest.main()

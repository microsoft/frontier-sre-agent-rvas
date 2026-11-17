import base64
import copy
import csv
import importlib.util
import inspect
import io
import json
import os
import ssl
import tempfile
import unittest
from contextlib import contextmanager, redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.error import HTTPError

from support import CLUSTER_ID, REFERENCE, ROOT, SUBSCRIPTION, ScriptedReader, api_object, container, fixture, load_engine


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
        self.config = self.e.validate_config("")

    def check(self, rule_id, raw=None):
        return next(row for row in self.e.evaluate(raw or self.raw, REFERENCE) if row["rule_id"] == rule_id)

    def status(self, source_id, status):
        next(source for source in self.raw["sources"] if source["id"] == source_id)["status"] = status

    def snapshot(self):
        return self.e.finish_snapshot(self.raw, REFERENCE, "SIMULATED", "LAB")

    def params(self, **kwargs):
        values = {key: value.default for key, value in inspect.signature(self.e.main).parameters.items()}
        values.update(operation="query", **kwargs)
        return self.e.validate_parameters(**values)

    def test_checklist_pin_and_all_112_ids_represented(self):
        checks = self.e.evaluate(self.raw, REFERENCE)
        original = json.loads((ROOT / "references" / "aks_checklist.en.json").read_text(encoding="utf-8"))
        self.assertEqual({r["checklist_id"] for r in checks}, {r["id"] for r in original["items"]})
        self.assertEqual(len({r["check_id"] for r in checks}), len(checks))
        self.assertTrue(all(r["learn_url"].startswith("https://learn.microsoft.com/") for r in checks))
        self.assertTrue(all(r["checklist_id"] and r["checklist_guid"] and r["checklist_url"] for r in checks))
        self.assertIn("Microsoft Corporation", self.e.CATALOG["license_text"])

    def test_parameters_schema_defaults_types_and_bounds(self):
        schema = json.loads((ROOT / "tool-parameters.schema.json").read_text())
        signature = inspect.signature(self.e.main)
        self.assertEqual(set(schema["properties"]), set(signature.parameters))
        for name, parameter in signature.parameters.items():
            self.assertEqual(parameter.default, schema["properties"][name]["default"])
            self.assertEqual("integer" if parameter.annotation is int else "string", schema["properties"][name]["type"])
        self.params(limit=1, offset=0)
        self.params(limit=100, offset=500000)
        for invalid in (dict(limit=0), dict(limit=101), dict(limit=True), dict(offset=-1), dict(offset=500001),
                        dict(namespace="x;GET secrets"), dict(workload_name="../../etc/passwd"), dict(cluster_name="https://evil.invalid"),
                        dict(view="unknown"), dict(view="coverage", status="failed"), dict(view="cluster", severity="high")):
            with self.subTest(invalid=invalid), self.assertRaises(self.e.EvidenceError):
                self.params(**invalid)

    def test_report_rejects_narrowing_and_paging(self):
        defaults = {key: value.default for key, value in inspect.signature(self.e.main).parameters.items()}
        self.e.validate_parameters(**defaults)
        for changes in (dict(namespace="client-apps"), dict(view="workloads"), dict(limit=1), dict(offset=1), dict(status="failed")):
            with self.subTest(changes=changes), self.assertRaises(self.e.EvidenceError):
                self.e.validate_parameters(**{**defaults, **changes})

    def test_default_code_fails_before_auth_or_network(self):
        with patch.object(self.e, "SUBSCRIPTION_ID", "<YOUR_SUBSCRIPTION_ID>"), patch.object(self.e, "Identity") as identity:
            result = self.e.main()
        self.assertEqual(result["error"]["code"], "configuration_required")
        identity.assert_not_called()
        self.assertLessEqual(len(json.dumps(result).encode()), 3500)

    def test_fixed_allowlist_and_no_scope_override(self):
        with self.assertRaises(self.e.EvidenceError):
            self.e.validate_config("other-cluster")
        with self.assertRaises(self.e.EvidenceError):
            self.e.arm_id(CLUSTER_ID.replace(SUBSCRIPTION, "44444444-4444-4444-8444-444444444444"), SUBSCRIPTION)
        for value in ("../../bad", CLUSTER_ID + "?token=x", CLUSTER_ID + "/../escape"):
            with self.subTest(value=value), self.assertRaises(self.e.EvidenceError):
                self.e.arm_id(value, SUBSCRIPTION)

    def test_quantity_si_binary_milli_micro_nano_and_exponents(self):
        for value, unit, expected in (("250m", "cores", .25), ("100000000n", "cores", .1), ("1000u", "cores", .001),
                                      ("1.5", "cores", 1.5), ("1e3", "cores", 1000), ("1E-3", "cores", .001),
                                      ("1Mi", "bytes", 1048576), ("1Gi", "bytes", 1073741824), ("1G", "bytes", 1000000000),
                                      ("400m", "bytes", 1), ("1.5Ki", "bytes", 1536)):
            with self.subTest(value=value):
                self.assertEqual(self.e.quantity(value, unit), expected)
        for invalid in ("NaN", "inf", "-1", "1MB", "1e999999999", "", "1;curl", 1, True):
            with self.subTest(invalid=invalid), self.assertRaises(self.e.EvidenceError):
                self.e.quantity(invalid, "cores")
        self.assertIsNone(self.e.quantity(None, "cores"))

    def test_whitelist_excludes_env_args_logs_secrets_credentials(self):
        sentinel = "SIMULATED-SENSITIVE-FIELD-NEVER-EXPORTED"
        c = container(env=[{"name": "TOKEN", "value": sentinel}], command=[sentinel], args=[sentinel],
                      envFrom=[{"secretRef": {"name": sentinel}}])
        deployment = api_object("Deployment", "filtered", "client-apps", spec={"replicas": 1, "template": {
            "metadata": {"labels": {"app": "filtered"}, "annotations": {"raw-token": sentinel}},
            "spec": {"containers": [c], "imagePullSecrets": [{"name": sentinel}],
                     "volumes": [{"secret": {"secretName": sentinel}}]}}}, data={"password": sentinel})
        normalized = self.e.normalize_kube(deployment, "deployments", "kube_deployments", REFERENCE, self.config)
        self.assertNotIn(sentinel, json.dumps(normalized))
        self.assertEqual(normalized["containers"][0]["request_cpu_cores"], .25)
        self.assertEqual(normalized["containers"][0]["limit_memory_bytes"], 536870912)
        for image in ("https://registry.example.invalid/app", "user:SIMULATED-PASSWORD@registry.example.invalid/app"):
            with self.subTest(image=image), self.assertRaises(self.e.EvidenceError):
                self.e.normalize_containers([container(image=image)], "source")

    def test_null_probes_are_absent_and_bad_types_are_source_errors(self):
        row = self.e.normalize_containers([container(readinessProbe=None, livenessProbe={})], "source")[0]
        self.assertFalse(row["readiness_probe"])
        self.assertFalse(row["liveness_probe"])
        with self.assertRaises(self.e.EvidenceError):
            self.e.normalize_containers([container(readinessProbe="SIMULATED invalid source shape")], "source")

    def test_secrets_configmaps_logs_and_exec_are_not_reader_paths(self):
        joined = " ".join(self.e.KUBE_PATHS.values()).lower()
        for forbidden in ("secrets", "configmaps", "/log", "/exec", "attach", "portforward"):
            self.assertNotIn(forbidden, joined)

    def test_selector_expressions_empty_pdb_and_namespace_join(self):
        selector = self.e.normalize_selector({"matchLabels": {"app": "frontend"}, "matchExpressions": [
            {"key": "release", "operator": "In", "values": ["v1"]},
            {"key": "retired", "operator": "DoesNotExist"},
            {"key": "app", "operator": "Exists"},
            {"key": "tier", "operator": "NotIn", "values": ["legacy"]},
        ]}, "test")
        self.assertTrue(self.e.selector_matches(selector, {"app": "frontend", "release": "v1"}))
        self.assertFalse(self.e.selector_matches(selector, {"app": "frontend", "release": "v2"}))
        self.assertTrue(self.e.selector_matches({"match_labels": {}, "match_expressions": []}, {"app": "frontend"}))
        self.assertIsNone(self.e.selector_matches(selector, None))
        self.assertEqual(self.check("W03")["status"], "passed")
        self.raw["inventory"]["pdbs"][0]["namespace"] = "different-apps"
        self.assertEqual(self.check("W03")["status"], "failed")
        self.status("kube_pdbs", "denied")
        self.assertEqual(self.check("W03")["status"], "not_evaluated")
        with self.assertRaises(self.e.EvidenceError):
            self.e.normalize_selector({"matchExpressions": [{"key": "app", "operator": "In", "values": []}]}, "source")

    def test_pdb_nonselected_labels_not_name_guess(self):
        self.raw["inventory"]["pdbs"][0]["selector"]["match_labels"] = {"app": "other"}
        self.assertEqual(self.check("W03")["status"], "failed")

    def test_pdb_that_permits_all_replicas_is_not_protection(self):
        self.raw["inventory"]["pdbs"][0]["min_available"] = None
        self.raw["inventory"]["pdbs"][0]["max_unavailable"] = "100%"
        self.assertEqual(self.check("W03")["status"], "failed")
        self.raw["inventory"]["pdbs"][0]["max_unavailable"] = 2
        self.assertEqual(self.check("W03")["status"], "failed")
        self.raw["inventory"]["pdbs"][0]["max_unavailable"] = None
        self.assertEqual(self.check("W03")["status"], "not_evaluated")
        for value in ({"token": "SIMULATED"}, -1, True, "arbitrary"):
            with self.subTest(value=value), self.assertRaises(self.e.EvidenceError):
                self.e.int_or_percent(value, "kube_pdbs")

    def test_system_batch_and_zero_replica_exceptions(self):
        row = self.raw["inventory"]["workloads"][0]
        for changes in ({"namespace": "kube-system"}, {"kind": "Job"}, {"desired_replicas": 0}):
            copy_row = {**row, **changes}
            for rule_id in ("W02", "W03", "W04", "W05"):
                rule = next(r for r in self.e.CATALOG["rules"] if r["rule_id"] == rule_id)
                with self.subTest(changes=changes, rule=rule_id):
                    self.assertEqual(self.e.evaluate_workload(rule, copy_row, self.raw)["status"], "not_applicable")

    def test_probes_apply_to_serving_containers_not_sidecars(self):
        self.assertEqual(self.check("W02")["status"], "passed")
        row = self.raw["inventory"]["workloads"][0]
        sidecar = self.e.normalize_containers([container("sidecar", ports=[], readinessProbe=None, livenessProbe=None)], "test")[0]
        sidecar["readiness_probe"] = sidecar["liveness_probe"] = False
        row["containers"].append(sidecar)
        self.assertEqual(self.check("W02")["status"], "passed")
        row["containers"][0]["readiness_probe"] = False
        self.assertEqual(self.check("W02")["status"], "failed")
        self.raw["inventory"]["services"] = []
        self.assertEqual(self.check("W02")["status"], "not_evaluated")

    def test_requests_are_not_usage_and_optional_cpu_limits(self):
        self.assertEqual(self.check("W01")["status"], "passed")
        self.raw["requirements"]["cpu_limits_required"] = True
        self.assertEqual(self.check("W01")["status"], "failed")
        self.raw["requirements"] = {}
        self.raw["inventory"]["workloads"][0]["containers"][0]["request_memory_bytes"] = None
        self.assertEqual(self.check("W01")["status"], "failed")
        self.raw["inventory"]["workloads"][0]["containers"][0]["request_memory_bytes"] = 0
        self.assertEqual(self.check("W01")["status"], "failed")

    def test_sla_autoscaling_and_automatic_nap_applicability(self):
        self.raw["cluster"]["sku_tier"] = "Free"
        self.assertEqual(self.check("C11")["status"], "not_evaluated")
        self.raw["requirements"]["sla_required"] = True
        self.assertEqual(self.check("C11")["status"], "failed")
        self.raw["cluster"]["sku_tier"] = "Premium"
        self.assertEqual(self.check("C11")["status"], "passed")
        for pool in self.raw["inventory"]["node_pools"]:
            pool["enable_auto_scaling"] = False
        self.assertEqual(self.check("C16")["status"], "not_evaluated")
        self.raw["requirements"]["autoscaling_required"] = True
        self.assertEqual(self.check("C16")["status"], "failed")
        self.raw["cluster"]["node_provisioning_mode"] = "Auto"
        self.assertEqual(self.check("C16")["status"], "passed")
        self.raw["requirements"]["autoscaling_required"] = False
        self.assertEqual(self.check("C16")["status"], "not_applicable")

    def test_node_scaling_requirement_does_not_imply_hpa_for_every_workload(self):
        self.raw["requirements"]["autoscaling_required"] = True
        self.assertEqual(self.check("W04")["status"], "not_evaluated")
        self.raw["requirements"]["workloads"] = {"client-apps/frontend": {"autoscaling_required": True}}
        self.assertEqual(self.check("W04")["status"], "failed")

    def test_pool_failed_is_not_hidden_by_cluster_running(self):
        self.raw["inventory"]["node_pools"][0]["provisioning_state"] = "Failed"
        check = self.check("C13")
        self.assertEqual(check["status"], "failed")
        self.assertEqual(check["severity"], "high")
        self.assertIn("Running", json.dumps(check["evidence"]))

    def test_system_placement_requires_exact_complete_node_join(self):
        self.assertEqual(self.check("C14")["status"], "passed")
        self.raw["inventory"]["nodes"][0]["pool_name"] = "system"
        self.assertEqual(self.check("C14")["status"], "failed")
        self.status("kube_nodes", "denied")
        self.assertEqual(self.check("C14")["status"], "not_evaluated")

    def test_cilium_overlay_and_high_maxpods_are_not_legacy_failures(self):
        self.assertEqual(self.check("C07")["status"], "passed")
        self.assertEqual(self.check("C08")["status"], "passed")
        self.assertEqual(self.raw["inventory"]["node_pools"][0]["max_pods"], 250)

    def test_version_support_uses_regional_source_not_static_latest(self):
        self.assertEqual(self.check("C19")["status"], "passed")
        self.raw["cluster"]["version"] = "9.99.99"
        self.assertEqual(self.check("C19")["status"], "not_evaluated")
        self.status("arm_regional_versions", "denied")
        self.assertEqual(self.check("C19")["status"], "not_evaluated")

    def test_addon_configuration_is_not_health_licensing_or_compliance(self):
        for rule_id in ("C09", "C10"):
            check = self.check(rule_id)
            self.assertEqual(check["status"], "passed")
            self.assertIn("does not prove effectiveness", check["reason"])
        self.raw["cluster"]["defender_enabled"] = None
        self.assertEqual(self.check("C10")["status"], "not_evaluated")

    def test_privileged_is_observed_but_missing_context_not_assumed_root(self):
        self.assertEqual(self.check("W06")["status"], "passed")
        security = self.raw["inventory"]["workloads"][0]["containers"][0]["security"]
        security.update(privileged=None, allowPrivilegeEscalation=None, runAsNonRoot=None)
        self.assertEqual(self.check("W06")["status"], "not_evaluated")
        security["privileged"] = True
        self.assertEqual(self.check("W06")["status"], "failed")
        self.assertEqual(self.check("W06")["severity"], "high")

    def test_container_context_overrides_pod_context_without_false_nonroot_pass(self):
        row = self.raw["inventory"]["workloads"][0]
        row["pod_security"]["runAsNonRoot"] = True
        row["containers"][0]["security"]["runAsNonRoot"] = False
        self.assertEqual(self.check("W06")["status"], "not_evaluated")
        row["run_as_user"] = 0
        self.assertEqual(self.check("W06")["status"], "failed")
        row["containers"][0]["run_as_user"] = 1000
        self.assertEqual(self.check("W06")["status"], "passed")

    def test_unknown_requirements_iac_dr_are_not_failed_or_drift(self):
        manual = [row for row in self.e.evaluate(self.raw, REFERENCE) if row["checklist_id"] in ("01.02.01", "02.01.01", "02.03.01")]
        self.assertTrue(manual)
        self.assertTrue(all(row["status"] == "not_evaluated" for row in manual))
        self.assertFalse(any("portal-created" in row["reason"] for row in manual))

    def test_scoring_denominators_null_unknown_and_no_duplicate_ids(self):
        checks = [{"check_id": str(i), "status": status} for i, status in enumerate(("passed", "failed", "not_evaluated", "not_applicable"))]
        score = self.e.score(checks)
        self.assertEqual(score["score"], 50)
        self.assertEqual(score["coverage_percent"], 66.67)
        self.assertEqual(score["evaluated"], 2)
        self.assertEqual(score["total"], 4)
        unknown = self.e.score([{"check_id": "one", "status": "not_evaluated"}])
        self.assertIsNone(unknown["score"])
        self.assertEqual(unknown["coverage_percent"], 0)
        self.assertIsNone(self.e.score([])["score"])
        self.assertIsNone(self.e.score([{"check_id": "na", "status": "not_applicable"}])["coverage_percent"])
        with self.assertRaises(self.e.EvidenceError):
            self.e.score(checks + checks)

    def test_finops_units_windows_numerators_and_owner_uid_join(self):
        finops = self.e.finops_for(self.raw)
        node = next(row for row in finops["candidates"] if row["id"].startswith("CURRENT-NODE"))
        workload = next(row for row in finops["candidates"] if row["id"].startswith("CURRENT-WORKLOAD"))
        self.assertEqual(node["numerator"], .1)
        self.assertEqual(node["denominator"], 3.8)
        self.assertEqual(node["sample_count"], 1)
        self.assertEqual(node["window"]["duration"], "30s")
        self.assertEqual(workload["numerator"], .01)
        self.assertEqual(workload["denominator"], .25)
        self.assertEqual(workload["value"], 4)
        self.assertEqual(workload["sample_count"], 1)
        self.assertIsNone(finops["estimated_savings"])
        self.assertIsNone(finops["actual_cost"])
        self.raw["inventory"]["pods"][0]["owner_references"][0]["uid"] = "unobserved-owner"
        self.assertFalse(any(row["id"].startswith("CURRENT-WORKLOAD") for row in self.e.finops_for(self.raw)["candidates"]))

    def test_finops_missing_metrics_are_not_zeros_or_monthly_savings(self):
        self.raw["inventory"]["node_metrics"] = []
        self.raw["inventory"]["pod_metrics"] = []
        self.status("kube_node_metrics", "denied")
        self.status("kube_pod_metrics", "error")
        finops = self.e.finops_for(self.raw)
        self.assertEqual(finops["candidates"], [])
        self.assertIsNone(finops["estimated_savings"])
        self.assertEqual(self.check("C21")["status"], "not_evaluated")
        self.assertEqual(self.check("F02")["status"], "not_evaluated")

    def test_stale_samples_preserved_but_not_called_current_capacity(self):
        item = api_object("NodeMetrics", "client-node-1", timestamp="2026-10-09T12:00:00Z",
                          window="1m0.5s", usage={"cpu": "0", "memory": "1Gi"})
        metric = self.e.normalize_kube(item, "node_metrics", "kube_node_metrics", REFERENCE, self.config)
        self.assertFalse(metric["fresh_for_reference"])
        self.assertEqual(metric["window_seconds"], 60.5)
        self.assertEqual(metric["cpu_quantity"], "0")
        self.assertEqual(metric["memory_quantity"], "1Gi")
        self.assertEqual(metric["cpu_cores"], 0)
        self.raw["inventory"]["node_metrics"] = [metric]
        self.raw["inventory"]["pod_metrics"] = []
        self.assertEqual(self.e.finops_for(self.raw)["candidates"], [])
        self.assertEqual(self.check("C21")["status"], "not_evaluated")
        self.assertIsNone(self.e.metric_freshness(None, 30, REFERENCE, "source"))
        for duration in ("0s", "30days", "25h", "-1s"):
            with self.subTest(duration=duration), self.assertRaises(self.e.EvidenceError):
                self.e.metric_window_seconds(duration, "source")

    def test_cost_math_real_currency_no_cross_currency_addition(self):
        self.raw["cost_rows"] = [{"resource_id": CLUSTER_ID, "amount": .1, "currency": "USD"},
                                {"resource_id": CLUSTER_ID, "amount": .2, "currency": "USD"}]
        self.status("azure_cost", "complete")
        result = self.e.finops_for(self.raw)
        self.assertEqual(result["actual_cost"], .3)
        self.assertEqual(result["currency"], "USD")
        self.raw["cost_rows"][1]["currency"] = "EUR"
        result = self.e.finops_for(self.raw)
        self.assertIsNone(result["actual_cost"])
        self.assertIsNone(result["currency"])
        self.assertIsNone(result["estimated_savings"])

    def test_orphan_requires_observed_attachment_and_full_visibility_not_rg_name(self):
        rid = "/subscriptions/" + SUBSCRIPTION + "/resourceGroups/rg-client-nodes/providers/Microsoft.Compute/disks/client-disk"
        resource = {"resource_id": rid, "name": "client-disk", "resource_kind": "microsoft.compute/disks",
                    "source_id": "arm_resource_1", "association": {"type": "node_resource_group_context"},
                    "configuration": {"diskState": "Unattached"}, "managed_by_present": True, "managed_by": None, "managed_by_extended": []}
        self.raw["inventory"]["related_resources"] = [resource]
        self.raw["sources"].append(self.e.source_receipt("arm_resource_1", REFERENCE))
        self.assertFalse(any(r["id"].startswith("UNATTACHED") for r in self.e.finops_for(self.raw)["candidates"]))
        resource["association"]["type"] = "operator_scoped"
        self.assertTrue(any(r["id"].startswith("UNATTACHED") for r in self.e.finops_for(self.raw)["candidates"]))
        self.status("kube_pvs", "denied")
        self.assertFalse(any(r["id"].startswith("UNATTACHED") for r in self.e.finops_for(self.raw)["candidates"]))

    def test_wait_for_first_consumer_without_active_pod_is_not_failure(self):
        pvc = api_object("PersistentVolumeClaim", "client-volume", "client-apps", spec={"storageClassName": "deferred"}, status={"phase": "Pending"})
        sc = api_object("StorageClass", "deferred", provisioner="disk.csi.azure.com", volumeBindingMode="WaitForFirstConsumer")
        self.raw["inventory"]["pvcs"] = [self.e.normalize_kube(pvc, "pvcs", "kube_pvcs", REFERENCE, self.config)]
        self.raw["inventory"]["storage_classes"] = [self.e.normalize_kube(sc, "storage_classes", "kube_storage_classes", REFERENCE, self.config)]
        self.assertEqual(self.check("R01")["status"], "not_applicable")
        self.status("kube_pods", "denied")
        self.assertEqual(self.check("R01")["status"], "not_evaluated")

    def test_default_3500_bytes_exact_paging_and_whole_rows(self):
        snapshot = self.snapshot()
        snapshot["inventory"]["workloads"] = [{**snapshot["inventory"]["workloads"][0], "name": "client-app-" + str(i),
                                               "workload_name": "client-app-" + str(i)} for i in range(80)]
        result = self.e.query_snapshot(snapshot, self.params(view="workloads", limit=100))
        self.assertLessEqual(len(json.dumps(result).encode("utf-8")), 3500)
        self.assertEqual(result["total_matched"], 80)
        self.assertTrue(result["transport_capped"])
        self.assertTrue(result["has_more"])
        self.assertGreater(result["returned"], 0)
        self.assertEqual(result["returned"], len(result["rows"]))
        self.assertEqual(result["next_offset"], result["returned"])
        self.assertTrue(result["collection"]["fresh_collection"])
        self.assertEqual(result["rows"][0], snapshot["inventory"]["workloads"][0])

    def test_response_budget_uses_default_json_spaces_and_unicode_escapes(self):
        payload = {"value": ""}
        overhead = len(json.dumps(payload).encode())
        payload["value"] = "a" * (3500 - overhead)
        self.assertEqual(len(json.dumps(payload).encode()), 3500)
        self.e.ensure_response(payload)
        payload["value"] += "a"
        with self.assertRaises(self.e.EvidenceError):
            self.e.ensure_response(payload)
        escaped = {"value": "\u00f1" * 583}
        self.assertGreater(self.e.response_bytes(escaped), len(json.dumps(escaped, ensure_ascii=False, separators=(",", ":")).encode()))

    def test_one_oversized_row_has_explicit_error_not_endless_zero_cursor(self):
        snapshot = self.snapshot()
        snapshot["inventory"]["workloads"][0]["name"] = "\u00f1" * 1000
        result = self.e.query_snapshot(snapshot, self.params(view="workloads"))
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"]["code"], "query_row_too_large")
        self.assertIsNone(result["next_offset"])
        self.assertLessEqual(len(json.dumps(result).encode()), 3500)

    def test_local_views_filters_and_exact_totals(self):
        snapshot = self.snapshot()
        for view in self.e.VIEWS:
            result = self.e.query_snapshot(snapshot, self.params(view=view, limit=1))
            self.assertLessEqual(len(json.dumps(result).encode()), 3500)
            self.assertIn("total_matched", result)
        result = self.e.query_snapshot(snapshot, self.params(view="findings", status="not_evaluated", area="finops"))
        expected = [r for r in snapshot["checks"] if r["area"] == "finops" and r["status"] == "not_evaluated"]
        self.assertEqual(result["total_matched"], len(expected))
        result = self.e.query_snapshot(snapshot, self.params(view="workloads", namespace="not-observed"))
        self.assertEqual(result["returned"], 0)
        self.assertEqual(result["total_matched"], 0)
        self.assertFalse(result["has_more"])
        self.raw["inventory"]["node_pools"][0]["provisioning_state"] = "Failed"
        result = self.e.query_snapshot(self.snapshot(), self.params(view="actions", level="cluster", severity="high"))
        self.assertEqual(result["total_matched"], 1)

    def test_snapshot_preserves_every_normalized_source_without_mutating_input(self):
        before = copy.deepcopy(self.raw)
        snapshot = self.snapshot()
        self.assertEqual(self.raw, before)
        self.assertEqual(snapshot["inventory"], before["inventory"])
        for key in ("regional_versions", "upgrade_profile", "arm_maintenance", "arm_diagnostics", "advisor", "cost_rows"):
            self.assertEqual(snapshot["source_data"][key], before[key])
        self.assertEqual(snapshot["findings"], [r for r in snapshot["checks"] if r["status"] == "failed"])
        self.assertEqual(snapshot["provenance"], "SIMULATED")
        self.assertEqual(snapshot["environment"], "LAB")
        self.assertTrue(3 <= len(snapshot["executive_messages"]) <= 5)

    def test_safe_html_json_round_trip_injection_and_unicode(self):
        snapshot = self.snapshot()
        snapshot["client"]["name"] = "</script><script>alert(1)</script>&\u2028\u2029"
        document = self.e.render_html(snapshot)
        encoded = document.split('<script type="application/json" id="report-data">', 1)[1].split("</script>", 1)[0]
        self.assertEqual(json.loads(encoded), snapshot)
        self.assertNotIn("<script>alert", encoded)
        self.assertNotIn("\u2028", encoded)

    def test_four_atomic_files_full_normalized_equality_and_csv_contents(self):
        self.raw["inventory"]["node_pools"][0]["provisioning_state"] = "Failed"
        snapshot = self.snapshot()
        with tempfile.TemporaryDirectory() as directory, cwd(directory):
            result = self.e.write_report(snapshot)
            self.assertLessEqual(len(json.dumps(result).encode()), 3500)
            self.assertEqual(result["artifact_status"], "written")
            self.assertEqual(result["sharing_mode"], "local_files_only")
            paths = [Path(result[key]) for key in ("report_path", "snapshot_path", "findings_csv_path", "inventory_csv_path")]
            self.assertEqual(len(list((Path(directory) / "aks-waf-reports").iterdir())), 4)
            self.assertTrue(all(path.is_file() and path.stat().st_size <= 4_800_000 for path in paths))
            self.assertEqual(json.loads(paths[1].read_text(encoding="utf-8")), snapshot)
            findings = list(csv.DictReader(io.StringIO(paths[2].read_text(encoding="utf-8-sig"))))
            self.assertEqual(len(findings), len(snapshot["findings"]))
            self.assertEqual(json.loads(findings[0]["details_json"]), snapshot["findings"][0])
            inventory = list(csv.DictReader(io.StringIO(paths[3].read_text(encoding="utf-8-sig"))))
            self.assertEqual(len(inventory), len(self.e.inventory_csv_rows(snapshot)))
            self.assertEqual(json.loads(inventory[0]["details_json"]), snapshot["cluster"])
            self.assertFalse(result["http_verified"])

    def test_actual_4800000_byte_threshold_and_no_partial_write(self):
        # Fleet build: the bounds are ARTIFACT_BYTES/HTML_ARTIFACT_BYTES (raised for 100-cluster reports); the mechanism is
        # exercised at the historical 4,800,000-byte value.
        snapshot = self.snapshot()
        bounds = patch.multiple(self.e, ARTIFACT_BYTES=4_800_000, HTML_ARTIFACT_BYTES=4_800_000)
        bounds.start()
        self.addCleanup(bounds.stop)
        with tempfile.TemporaryDirectory() as directory, cwd(directory):
            with patch.object(self.e, "render_html", return_value="a" * 4_800_000):
                result = self.e.write_report(snapshot)
                self.assertEqual(Path(result["report_path"]).stat().st_size, 4_800_000)
        with tempfile.TemporaryDirectory() as directory, cwd(directory):
            with patch.object(self.e, "render_html", return_value="a" * 4_800_001), self.assertRaises(self.e.EvidenceError) as raised:
                self.e.write_report(snapshot)
            self.assertEqual(raised.exception.code, "artifact_size_exceeded")
            self.assertFalse((Path(directory) / "aks-waf-reports").exists())

    def test_large_full_json_rejects_before_writing_never_drops_source(self):
        snapshot = self.snapshot()
        snapshot["source_data"]["regional_versions"][0]["long_observation"] = "a" * 4_800_001
        with tempfile.TemporaryDirectory() as directory, cwd(directory), patch.multiple(self.e, ARTIFACT_BYTES=4_800_000), \
                self.assertRaises(self.e.EvidenceError) as raised:
            self.e.write_report(snapshot)
        self.assertEqual(raised.exception.code, "artifact_size_exceeded")
        self.assertEqual(len(snapshot["source_data"]["regional_versions"][0]["long_observation"]), 4_800_001)

    def test_cleanup_on_atomic_write_failure(self):
        snapshot = self.snapshot()
        original = self.e.os.replace
        calls = 0
        def fail_second(src, dst):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("SIMULATED storage fault")
            return original(src, dst)
        with tempfile.TemporaryDirectory() as directory, cwd(directory), patch.object(self.e.os, "replace", side_effect=fail_second):
            with self.assertRaises(self.e.EvidenceError) as raised:
                self.e.write_report(snapshot)
            self.assertEqual(raised.exception.code, "artifact_write_failed")
            self.assertEqual(list((Path(directory) / "aks-waf-reports").iterdir()), [])

    def test_fixed_directory_guard(self):
        with tempfile.TemporaryDirectory() as directory, cwd(directory), patch.object(self.e, "OUTPUT_DIRECTORY", ".."):
            with self.assertRaises(self.e.EvidenceError):
                self.e.write_report(self.snapshot())
        with tempfile.TemporaryDirectory() as directory, cwd(directory), patch.object(Path, "is_symlink", return_value=True):
            with self.assertRaises(self.e.EvidenceError):
                self.e.artifact_directory()

    def test_optional_logo_defaults_and_explicit_invalid_raster(self):
        self.e.validate_logo("")
        for uri in ("https://example.invalid/logo.png", "data:image/svg+xml;base64,PHN2Zz4=", "data:image/png;base64,YmFk",
                    "data:image/jpeg;base64,YmFk", "data:image/png;base64,!!!"):
            with self.subTest(uri=uri), self.assertRaises(self.e.EvidenceError):
                self.e.validate_logo(uri)

    def test_csv_formula_safety(self):
        self.assertEqual(self.e.csv_cell("=HYPERLINK(\"bad\")"), "'=HYPERLINK(\"bad\")")
        self.assertEqual(self.e.csv_cell(" \t+1"), "' \t+1")
        self.assertEqual(self.e.csv_cell({"name": "=formula"}), '{"name":"=formula"}')

    def test_main_query_uses_fresh_collection_without_stdout(self):
        stdout = io.StringIO()
        with patch.object(self.e, "collect_live", return_value=self.raw) as collect, redirect_stdout(stdout):
            result = self.e.main(operation="query", view="node_pools")
        self.assertEqual(stdout.getvalue(), "")
        collect.assert_called_once()
        self.assertEqual(result["total_matched"], 2)

    def test_full_collector_report_with_denied_kube_and_whitelisted_arm_sources(self):
        disk_id = "/subscriptions/" + SUBSCRIPTION + "/resourceGroups/rg-client-nodes/providers/Microsoft.Compute/disks/client-disk"
        cluster = {"id": CLUSTER_ID, "name": "aks-client-lab", "type": "Microsoft.ContainerService/managedClusters",
                   "location": "example-region", "identity": {"type": "UserAssigned"}, "sku": {"name": "Base", "tier": "Standard"},
                   "properties": {"kubernetesVersion": "1.35.7", "enableRBAC": True, "disableLocalAccounts": True,
                                  "aadProfile": {"managed": True, "enableAzureRBAC": True}, "powerState": {"code": "Running"},
                                  "nodeResourceGroup": "rg-client-nodes", "fqdn": "aks-client.example.azmk8s.io"}}
        pool = {"id": CLUSTER_ID + "/agentPools/system", "name": "system", "type": "Microsoft.ContainerService/managedClusters/agentPools",
                "properties": {"mode": "System", "provisioningState": "Failed", "enableAutoScaling": False}}
        disk = {"id": disk_id, "name": "client-disk", "type": "Microsoft.Compute/disks", "location": "example-region",
                "managedBy": None, "properties": {"diskState": "Unattached", "diskSizeGB": 64,
                                                 "secretMaterial": "SIMULATED-NEVER-EXPORTED"}}
        calls = []
        def route(method, url, source, **kwargs):
            calls.append((method, url, source))
            if method == "POST":
                self.assertTrue(url.endswith("api-version=2025-05-01&format=exec"))
                raise self.e.EvidenceError("access_denied", "SIMULATED clusterUser 403", source, 403)
            self.assertEqual(method, "GET")
            if source == "arm_cluster":
                return cluster
            if source == "arm_node_pools":
                return {"value": [pool]}
            if source == "arm_regional_versions":
                return {"values": [{"version": "1.35", "patchVersions": {"1.35.7": {"upgrades": []}}}]}
            if source == "arm_upgrade_profile":
                return {"properties": {"controlPlaneProfile": {"kubernetesVersion": "1.35.7", "upgrades": []}}}
            if source == "arm_related_inventory":
                return {"value": [disk]}
            if source.startswith("arm_resource_"):
                self.assertIn(disk_id, url)
                return disk
            if source in ("arm_diagnostics", "arm_maintenance", "arm_advisor"):
                return {"value": []}
            self.fail("Unexpected source/API in read-only collector: " + source)
        reader = Mock()
        reader.allow.side_effect = lambda url, *args: url
        reader.request.side_effect = route
        identity = Mock()
        with patch.object(self.e, "Identity", return_value=identity), patch.object(self.e, "HttpReader", return_value=reader):
            raw = self.e.collect_live(self.config, REFERENCE)
        identity.close.assert_called_once()
        self.assertEqual(next(s for s in raw["sources"] if s["id"] == "kube_access")["status"], "denied")
        self.assertTrue(all(s["status"] == "denied" for s in raw["sources"] if s["id"] in ("kube_nodes", "kube_deployments", "kube_pvs")))
        self.assertEqual(raw["inventory"]["related_resources"][0]["configuration"]["diskSizeGB"], 64)
        self.assertNotIn("SIMULATED-NEVER-EXPORTED", json.dumps(raw))
        snapshot = self.e.finish_snapshot(raw, REFERENCE, "SIMULATED", "LAB")
        self.assertEqual(next(c for c in snapshot["checks"] if c["rule_id"] == "C13")["status"], "failed")
        self.assertEqual(next(c for c in snapshot["checks"] if c["rule_id"] == "W02")["status"], "not_evaluated")
        self.assertEqual(snapshot["finops"]["candidates"], [])
        with tempfile.TemporaryDirectory() as directory, cwd(directory):
            result = self.e.write_report(snapshot)
            self.assertEqual(result["status"], "partial")
            self.assertEqual(json.loads(Path(result["snapshot_path"]).read_text(encoding="utf-8"))["inventory"], raw["inventory"])
        self.assertTrue(all("listClusterAdminCredential" not in url for _, url, _ in calls))


class ReaderTests(unittest.TestCase):
    def setUp(self):
        self.e = load_engine()
        self.config = self.e.validate_config("")

    def test_arm_multiple_pages_full_receipt(self):
        initial = self.e.ARM_ORIGIN + CLUSTER_ID + "/agentPools?api-version=2025-05-01"
        following = initial + "&$skiptoken=page2"
        reader = ScriptedReader([{"value": [{"id": "first"}], "nextLink": following}, {"value": [{"id": "second"}]}])
        rows, receipt = self.e.read_pages(reader, initial, "test_source", REFERENCE, lambda row: row)
        self.assertEqual(rows, [{"id": "first"}, {"id": "second"}])
        self.assertEqual(receipt["pages"], 2)
        self.assertEqual(receipt["records"], 2)
        self.assertTrue(receipt["pagination_complete"])
        self.assertEqual(receipt["status"], "complete")

    def test_failed_later_page_retains_collected_records_and_error(self):
        url = self.e.ARM_ORIGIN + CLUSTER_ID + "/agentPools?api-version=2025-05-01"
        reader = ScriptedReader([{"value": [{"id": "first"}], "nextLink": url + "&$skiptoken=page2"},
                                 self.e.EvidenceError("access_denied", "SIMULATED 403", "source", 403)])
        rows, receipt = self.e.read_pages(reader, url, "source", REFERENCE, lambda row: row)
        self.assertEqual(rows, [{"id": "first"}])
        self.assertEqual(receipt["status"], "partial")
        self.assertEqual(receipt["errors"][0]["http_status"], 403)
        self.assertFalse(receipt["pagination_complete"])

    def test_403_502_and_empty_are_semantically_distinct(self):
        url = self.e.ARM_ORIGIN + CLUSTER_ID + "/agentPools?api-version=2025-05-01"
        for response, expected in ((self.e.EvidenceError("access_denied", "SIMULATED 403", "source", 403), "denied"),
                                    (self.e.EvidenceError("http_error", "SIMULATED 502", "source", 502), "error"),
                                    ({"value": []}, "complete")):
            rows, receipt = self.e.read_pages(ScriptedReader([response]), url, "source", REFERENCE, lambda row: row)
            self.assertEqual(rows, [])
            self.assertEqual(receipt["status"], expected)
            self.assertEqual(receipt["pagination_complete"], expected == "complete")

    def test_arm_continuation_origin_filter_version_and_loops(self):
        initial = self.e.ARM_ORIGIN + CLUSTER_ID + "/agentPools?api-version=2025-05-01"
        for link in (initial.replace("management.azure.com", "evil.invalid"), initial.replace("2025-05-01", "2020-01-01"),
                     initial.replace("aks-client-lab", "another"), initial + "&filter=all", initial + "&api-version=2025-05-01"):
            with self.subTest(link=link), self.assertRaises(self.e.EvidenceError):
                self.e.next_arm_link(link, initial)
        reader = ScriptedReader([{"value": [{"id": "one"}], "nextLink": initial}])
        _, receipt = self.e.read_pages(reader, initial, "source", REFERENCE, lambda row: row)
        self.assertEqual(receipt["status"], "partial")
        self.assertEqual(receipt["errors"][0]["code"], "pagination_loop")

    def test_official_dual_skiptokens_match_and_complete_without_scope_expansion(self):
        initial = self.e.ARM_ORIGIN + CLUSTER_ID + "/agentPools?api-version=2024-10-01"
        official = initial.split("?")[0] + "?%24skipToken=4314677&api-version=2024-10-01&skipToken=4314677"
        self.assertEqual(self.e.next_arm_link(official, initial), official)
        reader = ScriptedReader([{"value": [{"id": "first"}], "nextLink": official}, {"value": []}])
        rows, receipt = self.e.read_pages(reader, initial, "arm_node_pools", REFERENCE, lambda row: row)
        self.assertEqual(rows, [{"id": "first"}])
        self.assertEqual(receipt["status"], "complete")
        self.assertEqual(receipt["pages"], 2)
        self.assertTrue(receipt["pagination_complete"])
        for invalid in (official.replace("&skipToken=4314677", "&skipToken=4314678"),
                        official.replace("api-version=2024-10-01", "api-version=2025-05-01"),
                        official + "&consumerAuth=1", official + "&scope=all",
                        official.replace("management.azure.com", "evil.invalid")):
            with self.subTest(invalid=invalid), self.assertRaises(self.e.EvidenceError):
                self.e.next_arm_link(invalid, initial)

    def test_kubernetes_continue_resourceversion_remaining_and_caps(self):
        url = "https://aks-client.example.azmk8s.io/api/v1/pods?limit=500"
        reader = ScriptedReader([{"items": [{"uid": "one"}], "metadata": {"resourceVersion": "100", "continue": "a/b+c=", "remainingItemCount": 1}},
                                 {"items": [{"uid": "two"}], "metadata": {"resourceVersion": "100", "remainingItemCount": 0}}])
        rows, receipt = self.e.read_pages(reader, url, "kube_pods", REFERENCE, lambda row: row, kubernetes=True)
        self.assertEqual(len(rows), 2)
        self.assertEqual(receipt["resource_version"], "100")
        self.assertIn("continue=a%2Fb%2Bc%3D", reader.calls[1][1])
        bad = ScriptedReader([{"items": [{"uid": "one"}], "metadata": {"resourceVersion": "100", "remainingItemCount": 1}}])
        _, receipt = self.e.read_pages(bad, url, "kube_pods", REFERENCE, lambda row: row, kubernetes=True)
        self.assertEqual(receipt["errors"][0]["code"], "missing_continuation")
        changed = ScriptedReader([{"items": [{"uid": "one"}], "metadata": {"resourceVersion": "100", "continue": "two"}},
                                  {"items": [{"uid": "two"}], "metadata": {"resourceVersion": "101"}}])
        _, receipt = self.e.read_pages(changed, url, "kube_pods", REFERENCE, lambda row: row, kubernetes=True)
        self.assertEqual(receipt["status"], "partial")
        self.assertEqual(receipt["errors"][0]["code"], "inconsistent_resource_version")
        with patch.object(self.e, "MAX_PAGES", 1):
            _, receipt = self.e.read_pages(ScriptedReader([{"items": [{"uid": "one"}], "metadata": {"resourceVersion": "100", "continue": "two"}}]),
                                              url, "kube_pods", REFERENCE, lambda row: row, kubernetes=True)
            self.assertEqual(receipt["errors"][0]["code"], "page_cap")

    def test_aggregated_metrics_api_without_uid_or_resourceversion_is_disclosed(self):
        item = {"kind": "NodeMetrics", "metadata": {"name": "client-node-1"}, "timestamp": REFERENCE,
                "window": "30s", "usage": {"cpu": "100m", "memory": "256Mi"}}
        reader = ScriptedReader([{"items": [item], "metadata": {}}])
        rows, receipt = self.e.read_pages(reader, "https://aks-client.example.azmk8s.io/apis/metrics.k8s.io/v1beta1/nodes?limit=500",
            "kube_node_metrics", REFERENCE, lambda raw: self.e.normalize_kube(raw, "node_metrics", "kube_node_metrics", REFERENCE, self.config),
            kubernetes=True, metrics_snapshot=True)
        self.assertEqual(rows[0]["cpu_cores"], .1)
        self.assertIsNone(rows[0]["uid"])
        self.assertIsNone(receipt["resource_version"])
        self.assertIn("not a transactional", receipt["note"])

    def test_strict_tls_get_and_endpoint_allowlist(self):
        with self.assertRaises(self.e.EvidenceError):
            self.e.HttpReader(Mock(), context=ssl._create_unverified_context())
        reader = self.e.HttpReader(Mock())
        with self.assertRaises(self.e.EvidenceError):
            reader.allow("http://management.azure.com/unsafe")
        with self.assertRaises(self.e.EvidenceError):
            reader.allow(self.e.ARM_ORIGIN + CLUSTER_ID, "DELETE")
        with self.assertRaises(self.e.EvidenceError):
            reader.request("GET", self.e.ARM_ORIGIN + CLUSTER_ID, "source")
        url = self.e.ARM_ORIGIN + CLUSTER_ID + "/runCommand?api-version=2025-05-01"
        reader.allow(url, "POST")
        with self.assertRaises(self.e.EvidenceError):
            reader.request("POST", url, "source")

    def test_retry_after_is_bounded_and_429_is_not_access_denied(self):
        identity = Mock()
        identity.token.return_value = "SIMULATED-OPAQUE-TOKEN"
        reader = self.e.HttpReader(identity)
        url = self.e.ARM_ORIGIN + CLUSTER_ID + "?api-version=2025-05-01"
        reader.allow(url)
        reader.opener = Mock()
        reader.opener.open.side_effect = HTTPError(url, 429, "SIMULATED throttle", {"Retry-After": "3600"}, None)
        with patch.object(self.e.time, "sleep") as sleep, self.assertRaises(self.e.EvidenceError) as raised:
            reader.request("GET", url, "azure_cost")
        self.assertEqual(reader.opener.open.call_count, 3)
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [5, 5])
        self.assertEqual(raised.exception.http_status, 429)
        self.assertEqual(raised.exception.code, "http_error")
        self.assertNotIn("SIMULATED-OPAQUE-TOKEN", str(raised.exception))

    def test_managed_entra_required_before_clusteruser_request(self):
        cluster = fixture(self.e)["cluster"]
        cluster["managed_entra"] = False
        arm = ScriptedReader([])
        with self.assertRaises(self.e.EvidenceError) as raised:
            self.e.kube_reader(arm, Mock(), cluster, self.config)
        self.assertEqual(raised.exception.code, "entra_required")
        self.assertEqual(arm.calls, [])

    def kube_config(self, server=None, user=None, insecure=False):
        import yaml
        ca = ssl.create_default_context().get_ca_certs(binary_form=True)[0]
        certificate = ssl.DER_cert_to_PEM_cert(ca)
        document = {"current-context": "approved", "contexts": [{"name": "approved", "context": {"cluster": "approved"}}],
                    "clusters": [{"name": "approved", "cluster": {"server": server or "https://aks-client.example.azmk8s.io",
                        "certificate-authority-data": base64.b64encode(certificate.encode()).decode(),
                        "insecure-skip-tls-verify": insecure}}],
                    "users": [{"name": "approved", "user": user or {"exec": {"command": "NEVER_EXECUTE", "args": ["SIMULATED"]}}}]}
        return {"kubeconfigs": [{"value": base64.b64encode(yaml.safe_dump(document).encode()).decode()}]}

    def test_clusteruser_exec_is_never_executed_and_only_tls_origin_retained(self):
        arm = ScriptedReader([self.kube_config()])
        reader = self.e.kube_reader(arm, Mock(), fixture(self.e)["cluster"], self.config)
        self.assertEqual(reader.origin, "https://aks-client.example.azmk8s.io")
        self.assertEqual(reader.audience, self.e.AKS_AUDIENCE)
        self.assertEqual(reader.context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(reader.context.check_hostname)
        self.assertIn("format=exec", arm.calls[0][1])
        self.assertNotIn("admin", arm.calls[0][1].lower())

    def test_default_port_is_canonicalized_and_system_plus_cluster_ca_preserved(self):
        payload = self.kube_config(server="https://aks-client.example.azmk8s.io:443/")
        create = ssl.create_default_context
        with patch.object(self.e.ssl, "create_default_context", wraps=create) as contexts:
            reader = self.e.kube_reader(ScriptedReader([payload]), Mock(), fixture(self.e)["cluster"], self.config)
        self.assertEqual(reader.origin, "https://aks-client.example.azmk8s.io")
        self.assertTrue(all("cadata" not in call.kwargs for call in contexts.call_args_list))
        self.assertGreater(len(reader.context.get_ca_certs()), 0)
        self.assertEqual(reader.context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(reader.context.check_hostname)
        for server in ("https://aks-client.example.azmk8s.io:444", "https://aks-client.example.azmk8s.io:bad",
                       "https://aks-client.example.azmk8s.io/unapproved", "https://aks-client.example.azmk8s.io/?x=1"):
            with self.subTest(server=server), self.assertRaises(self.e.EvidenceError):
                self.e.kube_reader(ScriptedReader([self.kube_config(server=server)]), Mock(), fixture(self.e)["cluster"], self.config)

    def test_kube_endpoint_ca_and_local_certificate_fallback_rejected(self):
        for payload in (self.kube_config(server="https://evil.invalid"), self.kube_config(insecure=True),
                        self.kube_config(user={"client-key-data": "SIMULATED"}),
                        self.kube_config(user={"token": "SIMULATED"})):
            with self.subTest(payload=payload["kubeconfigs"][0]["value"][:10]), self.assertRaises(self.e.EvidenceError):
                self.e.kube_reader(ScriptedReader([payload]), Mock(), fixture(self.e)["cluster"], self.config)

    def test_cost_fixed_scope_window_and_verified_currency_rows(self):
        config = {**self.config, "approved_cost_resource_ids": [CLUSTER_ID], "cost_scope": "resource_ids"}
        columns = [{"name": name} for name in ("PreTaxCost", "UsageDate", "ResourceId", "Currency")]
        rows = [[12.5, 20261009, CLUSTER_ID, "USD"]]
        reader = ScriptedReader([{"properties": {"columns": columns, "rows": rows}}])
        result, receipt = self.e.collect_cost(reader, config, REFERENCE, [])
        self.assertEqual(result[0]["amount"], 12.5)
        self.assertEqual(result[0]["currency"], "USD")
        self.assertEqual(receipt["status"], "complete")
        self.assertEqual(receipt["window"]["start"], "2026-09-10T12:00:00Z")
        self.assertEqual(reader.calls[0][3]["body"]["type"], "ActualCost")
        self.assertEqual(reader.calls[0][3]["body"]["dataset"]["filter"]["dimensions"]["values"], [CLUSTER_ID])

    def test_cost_throttled_unverified_wrong_currency_and_out_of_window(self):
        config = {**self.config, "approved_cost_resource_ids": [CLUSTER_ID], "cost_scope": "resource_ids"}
        _, receipt = self.e.collect_cost(ScriptedReader([self.e.EvidenceError("http_error", "SIMULATED 429", "azure_cost", 429)]),
                                         config, REFERENCE, [])
        self.assertEqual(receipt["status"], "error")
        self.assertEqual(receipt["errors"][0]["http_status"], 429)
        for amount, day, currency in ((None, 20261009, "USD"), (1, 20260101, "USD"), (1, 20261009, None), (1, 20260231, "USD")):
            payload = {"properties": {"columns": [{"name": key} for key in ("PreTaxCost", "UsageDate", "ResourceId", "Currency")],
                                      "rows": [[amount, day, CLUSTER_ID, currency]]}}
            rows, receipt = self.e.collect_cost(ScriptedReader([payload]), config, REFERENCE, [])
            self.assertEqual(rows, [])
            self.assertEqual(receipt["status"], "error")
        config["approved_cost_resource_ids"] = [CLUSTER_ID + "/agentPools/not-observed"]
        reader = ScriptedReader([])
        _, receipt = self.e.collect_cost(reader, config, REFERENCE, [])
        self.assertEqual(receipt["errors"][0]["code"], "unverified_cost_scope")
        self.assertEqual(reader.calls, [])

    def test_month_to_date_node_rg_keeps_all_53_historical_and_vmss_child_rows(self):
        config = {**self.config, "cost_scope": "node_resource_group", "cost_timeframe": "month_to_date"}
        cluster = fixture(self.e)["cluster"]
        prefix = "/subscriptions/" + SUBSCRIPTION + "/resourceGroups/" + cluster["node_resource_group"] + "/providers/Microsoft.Compute/"
        ids = [prefix + "disks/historical-" + str(i) for i in range(52)]
        ids.append(prefix + "virtualMachineScaleSets/deleted-pool/virtualMachines/2")
        columns = [{"name": name, "type": kind} for name, kind in (("PreTaxCost", "Number"), ("ResourceId", "String"), ("Currency", "String"))]
        url = self.e.ARM_ORIGIN + "/subscriptions/" + SUBSCRIPTION + "/resourceGroups/" + cluster["node_resource_group"]
        url += "/providers/Microsoft.CostManagement/query?api-version=2023-11-01"
        reader = ScriptedReader([{"properties": {"columns": columns, "rows": [[1.25, rid, "USD"] for rid in ids[:25]],
                                                "nextLink": url + "&$skiptoken=next"}},
                                 {"properties": {"columns": columns, "rows": [[1.25, rid, "USD"] for rid in ids[25:]]}}])
        rows, receipt = self.e.collect_cost(reader, config, REFERENCE, [], cluster)
        self.assertEqual(len(rows), 53)
        self.assertEqual({r["resource_id"] for r in rows}, set(ids))
        self.assertTrue(all(r["current_inventory_match"] is False for r in rows))
        self.assertTrue(all(r["usage_date"] is None for r in rows))
        self.assertTrue(all(r["association"]["type"] == "node_resource_group_billing_context" for r in rows))
        self.assertEqual(receipt["status"], "complete")
        self.assertEqual(receipt["records"], 53)
        self.assertEqual(receipt["pages"], 2)
        self.assertEqual(receipt["window"]["start"], "2026-10-01T00:00:00Z")
        body = reader.calls[0][3]["body"]
        self.assertEqual(body["timeframe"], "MonthToDate")
        self.assertEqual(body["dataset"]["granularity"], "None")
        self.assertNotIn("filter", body["dataset"])
        self.assertNotIn("timePeriod", body)
        raw = fixture(self.e)
        raw["cost_rows"] = rows
        raw["sources"] = [s for s in raw["sources"] if s["id"] != "azure_cost"] + [receipt]
        finops = self.e.finops_for(raw)
        self.assertEqual(finops["actual_cost"], 66.25)
        self.assertEqual(finops["observed_cost_totals_by_currency"], {"USD": 66.25})
        self.assertTrue(finops["cost_source_complete"])
        self.assertIsNone(finops["estimated_savings"])

    def test_cost_node_rg_rejects_changed_group_and_unverified_cluster(self):
        config = {**self.config, "cost_scope": "node_resource_group", "cost_timeframe": "month_to_date"}
        cluster = fixture(self.e)["cluster"]
        wrong = CLUSTER_ID
        payload = {"properties": {"columns": [{"name": key} for key in ("PreTaxCost", "ResourceId", "Currency")],
                                  "rows": [[1, wrong, "USD"]]}}
        rows, receipt = self.e.collect_cost(ScriptedReader([payload]), config, REFERENCE, [], cluster)
        self.assertEqual(rows, [])
        self.assertEqual(receipt["errors"][0]["code"], "scope_mismatch")
        reader = ScriptedReader([])
        _, receipt = self.e.collect_cost(reader, config, REFERENCE, [], {**cluster, "id": "unapproved"})
        self.assertEqual(receipt["errors"][0]["code"], "unverified_cost_scope")
        self.assertEqual(reader.calls, [])

    def test_cost_arm_cluster_id_matching_is_case_insensitive_not_scope_relaxed(self):
        config = {**self.config, "cost_scope": "node_resource_group", "cost_timeframe": "month_to_date"}
        cluster = fixture(self.e)["cluster"]
        cluster["id"] = cluster["id"].upper()
        rid = "/subscriptions/" + SUBSCRIPTION + "/resourceGroups/" + cluster["node_resource_group"] + "/providers/Microsoft.Compute/disks/historical"
        payload = {"properties": {"columns": [{"name": name} for name in ("PreTaxCost", "ResourceId", "Currency")],
                                  "rows": [[3, rid, "USD"]]}}
        rows, receipt = self.e.collect_cost(ScriptedReader([payload]), config, REFERENCE, [], cluster)
        self.assertEqual(receipt["status"], "complete")
        self.assertEqual(rows[0]["amount"], 3)
        reader = ScriptedReader([])
        _, receipt = self.e.collect_cost(reader, config, REFERENCE, [], {**cluster, "id": cluster["id"] + "-OTHER"})
        self.assertEqual(receipt["errors"][0]["code"], "unverified_cost_scope")
        self.assertEqual(reader.calls, [])

    def test_collection_deadline_and_attempt_cap_precede_token_acquisition(self):
        import sys
        import types
        exceptions = types.SimpleNamespace(ClientAuthenticationError=RuntimeError, ServiceRequestError=OSError)
        identity_module = types.SimpleNamespace(CredentialUnavailableError=LookupError)
        identity = self.e.Identity.__new__(self.e.Identity)
        identity.credential = Mock()
        identity.deadline = 0
        identity.request_count = 0
        with patch.dict(sys.modules, {"azure.core.exceptions": exceptions, "azure.identity": identity_module}):
            with self.assertRaises(self.e.EvidenceError) as raised:
                identity.token(self.e.ARM_ORIGIN)
            self.assertEqual(raised.exception.code, "collection_deadline")
            identity.deadline = float("inf")
            identity.request_count = self.e.MAX_HTTP_ATTEMPTS
            with self.assertRaises(self.e.EvidenceError) as raised:
                identity.token(self.e.ARM_ORIGIN)
            self.assertEqual(raised.exception.code, "request_cap")
        identity.credential.get_token.assert_not_called()

    def test_token_claims_require_fixed_tenant_client_audience_without_fallback(self):
        import sys
        import types
        modules = {"azure.core.exceptions": types.SimpleNamespace(ClientAuthenticationError=RuntimeError, ServiceRequestError=OSError),
                   "azure.identity": types.SimpleNamespace(CredentialUnavailableError=LookupError)}
        identity = self.e.Identity.__new__(self.e.Identity)
        identity.credential = Mock()
        identity.deadline, identity.request_count = float("inf"), 0
        claims = {"tid": self.e.TENANT_ID, "appid": self.e.MANAGED_IDENTITY_CLIENT_ID, "aud": self.e.ARM_ORIGIN + "/"}
        def token_payload(values):
            return "SIMULATED." + base64.urlsafe_b64encode(json.dumps(values).encode()).decode().rstrip("=") + ".SIMULATED"
        identity.credential.get_token.return_value = types.SimpleNamespace(token=token_payload(claims))
        with patch.dict(sys.modules, modules):
            self.assertEqual(identity.token(self.e.ARM_ORIGIN), token_payload(claims))
            for field, wrong in (("tid", SUBSCRIPTION), ("appid", SUBSCRIPTION), ("aud", "https://evil.invalid")):
                identity.credential.get_token.return_value = types.SimpleNamespace(token=token_payload({**claims, field: wrong}))
                with self.subTest(field=field), self.assertRaises(self.e.EvidenceError) as raised:
                    identity.token(self.e.ARM_ORIGIN)
                self.assertEqual(raised.exception.code, "identity_mismatch")


if __name__ == "__main__":
    unittest.main()

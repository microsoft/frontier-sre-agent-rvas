import copy
import csv
import inspect
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from multicluster_fixture import SECOND_ID, SECOND_NAME, architecture_fixture, configured_engine, document, second_raw
from support import CLUSTER_ID, REFERENCE, api_object, fixture, load_engine
from test_engine import cwd


class MultiClusterTests(unittest.TestCase):
    def setUp(self):
        self.e = configured_engine(load_engine())

    def params(self, **changes):
        values = {name: value.default for name, value in inspect.signature(self.e.main).parameters.items()}
        return self.e.validate_parameters(**{**values, "operation": "query", **changes})

    def test_roster_is_configuration_without_auth_or_collection(self):
        with patch.object(self.e, "Identity") as identity, patch.object(self.e, "collect_live") as collect:
            result = self.e.main(operation="list_clusters")
        self.assertEqual(result["total"], 2)
        self.assertFalse(result["fresh_collection"])
        self.assertEqual(result["available_clusters"][1]["cluster_id"], SECOND_ID)
        identity.assert_not_called()
        collect.assert_not_called()
        self.assertLessEqual(len(json.dumps(result).encode()), 3500)

    def test_selection_rejects_duplicates_unknowns_urls_and_ambiguous_inputs_before_reads(self):
        for changes in ({"cluster_names": "aks-client-lab,aks-client-lab"}, {"cluster_names": "aks-client-lab,unknown"},
                        {"cluster_names": "aks-client-lab, " + SECOND_NAME}, {"cluster_names": "https://evil.invalid"},
                        {"cluster_names": "aks-client-lab," + SECOND_NAME, "cluster_name": "aks-client-lab"},
                        {"operation": "list_clusters", "cluster_name": "aks-client-lab"}):
            with self.subTest(changes=changes), patch.object(self.e, "collect_live") as collect:
                result = self.e.main(**changes)
            self.assertEqual(result["status"], "error")
            collect.assert_not_called()

    def test_same_names_and_uids_do_not_mix_check_ids_or_metrics(self):
        snapshot = document(self.e)
        first, second = [run["snapshot"] for run in snapshot["cluster_runs"]]
        self.assertEqual(first["inventory"]["namespaces"][0]["uid"], second["inventory"]["namespaces"][0]["uid"])
        self.assertTrue({row["check_id"] for row in first["checks"]}.isdisjoint({row["check_id"] for row in second["checks"]}))
        self.assertEqual(snapshot["aggregate"]["scores"]["global"]["total"], len(first["checks"]) + len(second["checks"]))
        for item in (first, second):
            self.assertTrue(all(row["cluster_id"] == item["cluster"]["id"] for row in item["checks"] + item["actions"]))
        self.assertIsNone(snapshot["aggregate"]["actual_cost"])
        self.assertIsNone(snapshot["aggregate"]["estimated_savings"])

    def test_one_primary_failure_retains_other_full_snapshot_and_coverage_error(self):
        raw = fixture(self.e)
        failure = self.e.EvidenceError("access_denied", "SIMULATED primary 403", "arm_cluster", 403)
        with patch.object(self.e, "collect_live", side_effect=[raw, failure]) as collect:
            result = self.e.main(operation="query", view="coverage", cluster_names="aks-client-lab," + SECOND_NAME,
                                 status="denied", limit=1)
        self.assertEqual(collect.call_count, 2)
        self.assertEqual(result["total_matched"], 1)
        self.assertEqual(result["rows"][0]["cluster_id"], SECOND_ID)
        self.assertEqual(result["rows"][0]["errors"][0]["http_status"], 403)
        self.assertEqual(result["collection"]["cluster_run_status_counts"]["error"], 1)
        self.assertLessEqual(len(json.dumps(result).encode()), 3500)

    def test_all_primary_failures_do_not_write_empty_live_report(self):
        failure = self.e.EvidenceError("gateway_error", "SIMULATED primary 502", "arm_cluster", 502)
        with patch.object(self.e, "collect_live", side_effect=[failure, failure]), patch.object(self.e, "write_report") as writer:
            result = self.e.main(cluster_names="aks-client-lab," + SECOND_NAME)
        self.assertEqual(result["error"]["code"], "all_clusters_failed")
        self.assertEqual(result["artifact_status"], "not_written")
        self.assertEqual(len(result["cluster_errors"]), 2)
        writer.assert_not_called()

    def test_shared_deadline_preserves_first_cluster_and_marks_unattempted_second(self):
        with patch.object(self.e.time, "monotonic", side_effect=[0, 1, 241]), patch.object(
            self.e, "collect_live", return_value=fixture(self.e)) as collect:
            result = self.e.main(operation="query", view="coverage", cluster_names="aks-client-lab," + SECOND_NAME, status="error")
        collect.assert_called_once()
        self.assertEqual(collect.call_args.kwargs["deadline"], 240)
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["rows"][0]["cluster_id"], SECOND_ID)
        self.assertEqual(result["rows"][0]["errors"][0]["code"], "collection_deadline")

    def test_five_failed_clusters_keep_all_codes_with_long_unicode_messages_under_budget(self):
        for index in range(3):
            self.e.APPROVED_CLUSTERS["aks-extra-" + str(index)] = copy.deepcopy(self.e.APPROVED_CLUSTERS["aks-client-lab"])
        failure = self.e.EvidenceError("gateway_error", "\u2603" * 500, "arm_cluster", 502)
        with patch.object(self.e, "collect_live", side_effect=[failure] * 5):
            result = self.e.main(cluster_names=",".join(self.e.APPROVED_CLUSTERS))
        self.assertEqual(result["error"]["code"], "all_clusters_failed")
        self.assertEqual(len(result["cluster_errors"]), 5)
        self.assertTrue(all(item["error"]["http_status"] == 502 for item in result["cluster_errors"]))
        self.assertLessEqual(len(json.dumps(result).encode()), 3500)

    def test_full_wrapper_and_both_scopes_round_trip_into_all_four_artifacts(self):
        snapshot = document(self.e, failed_second=True)
        before = copy.deepcopy(snapshot)
        with tempfile.TemporaryDirectory() as directory, cwd(directory):
            result = self.e.write_report(snapshot)
            exported = json.loads(Path(result["snapshot_path"]).read_text(encoding="utf-8"))
            html = Path(result["report_path"]).read_text(encoding="utf-8")
            embedded = html.split('<script type="application/json" id="report-data">', 1)[1].split("</script>", 1)[0]
            inventory = list(csv.DictReader(io.StringIO(Path(result["inventory_csv_path"]).read_text(encoding="utf-8-sig"))))
            self.assertEqual(len(list((Path(directory) / "aks-waf-reports").iterdir())), 4)
        self.assertEqual(snapshot, before)
        self.assertEqual(exported, snapshot)
        self.assertEqual(json.loads(embedded), snapshot)
        self.assertEqual(result["status"], "partial")
        self.assertTrue(any(row["cluster_id"] == CLUSTER_ID for row in inventory))
        error_row = next(row for row in inventory if row["collection"] == "cluster_collection_error")
        self.assertEqual(error_row["cluster_id"], SECOND_ID)
        self.assertIsNone(json.loads(error_row["details_json"])["snapshot"])
        self.assertLessEqual(len(json.dumps(result).encode()), 3500)

    def test_complete_query_filters_both_scopes_and_keeps_exact_paging(self):
        snapshot = document(self.e)
        result = self.e.query_snapshot(snapshot, self.params(view="workloads", namespace="client-apps", workload_name="frontend", limit=100))
        self.assertEqual(result["total_matched"], 2)
        self.assertLessEqual(len(json.dumps(result).encode()), 3500)
        self.assertTrue(all(row["cluster_id"] in (CLUSTER_ID, SECOND_ID) for row in result.get("rows", [])))
        if result["has_more"] and result["next_offset"] is not None:
            next_page = self.e.query_snapshot(snapshot, self.params(view="workloads", namespace="client-apps",
                                                                   workload_name="frontend", offset=result["next_offset"]))
            self.assertEqual(next_page["total_matched"], 2)
        self.assertEqual(sum(run["snapshot"]["inventory"]["workloads"][0]["workload_name"] == "frontend"
                             for run in snapshot["cluster_runs"]), 2)

    def test_mixed_provenance_and_wrong_cluster_snapshot_are_rejected(self):
        snapshot = document(self.e)
        snapshot["cluster_runs"][1]["snapshot"]["provenance"] = "LIVE"
        with self.assertRaises(self.e.EvidenceError):
            self.e.multi_snapshot(snapshot["cluster_runs"], REFERENCE, snapshot["available_clusters"])
        snapshot = document(self.e)
        snapshot["cluster_runs"][1]["snapshot"] = snapshot["cluster_runs"][0]["snapshot"]
        with self.assertRaises(self.e.EvidenceError):
            self.e.multi_snapshot(snapshot["cluster_runs"], REFERENCE, snapshot["available_clusters"])


class ArchitectureTests(unittest.TestCase):
    def setUp(self):
        self.e = load_engine()
        self.raw = architecture_fixture(self.e)

    def graph(self):
        return self.e.finish_snapshot(self.raw, REFERENCE, "SIMULATED", "LAB")["architecture"]

    def test_public_private_network_storage_registry_and_owner_edges_are_observed(self):
        graph = self.graph()
        self.assertIn("load_balancer_frontend_public", {node["kind"] for node in graph["nodes"]})
        self.assertIn("load_balancer_frontend_private", {node["kind"] for node in graph["nodes"]})
        relations = {edge["relation"] for edge in graph["edges"]}
        self.assertTrue({"uses_subnet", "associated_nsg", "contains_subnet", "backed_by_vmss", "owner_reference",
                         "observed_load_balancer_frontend", "bound_volume_reference", "csi_disk_reference",
                         "references_registry_image", "kubelet_registry_role_assignment", "uses_probe", "uses_backend_pool"}.issubset(relations))
        ids = {node["id"] for node in graph["nodes"]}
        self.assertTrue(all(edge["from"] in ids and edge["to"] in ids and edge["source_ids"] and edge["evidence"]
                            for edge in graph["edges"]))
        self.assertTrue(all(node["provenance"] == "SIMULATED" and node["observed_at"] == REFERENCE for node in graph["nodes"]))
        self.assertNotIn("SIMULATED-EXCLUDED", json.dumps(graph))
        self.assertNotIn("SIMULATED-condition-text-not-exported", json.dumps(graph))
        role = next(edge for edge in graph["edges"] if edge["relation"] == "kubelet_registry_role_assignment")
        self.assertFalse(role["evidence"]["effective_pull_permission_verified"])
        self.assertTrue(role["evidence"]["condition_present"])

    def test_annotation_or_name_alone_does_not_create_frontend_registry_or_mount_edges(self):
        for service in self.raw["inventory"]["services"]:
            service["load_balancer_ingress"] = []
        registry = next(row for row in self.raw["inventory"]["related_resources"] if row["resource_kind"] == "microsoft.containerregistry/registries")
        registry["login_server"] = "different.example.invalid"
        self.raw["cluster"]["addons"]["azureKeyvaultSecretsProvider"] = {"enabled": True}
        graph = self.graph()
        self.assertNotIn("observed_load_balancer_frontend", {edge["relation"] for edge in graph["edges"]})
        self.assertNotIn("references_registry_image", {edge["relation"] for edge in graph["edges"]})
        self.assertIn("key_vault_mount_not_observed", {row["code"] for row in graph["unknowns"]})
        self.assertEqual(sum(row["code"] == "load_balancer_frontend_not_joined" for row in graph["unknowns"]), 2)

    def test_stale_claim_uid_and_other_namespace_do_not_join(self):
        self.raw["inventory"]["pvs"][0]["claim_ref"]["uid"] = "SIMULATED-old-claim"
        self.raw["inventory"]["services"][0]["namespace"] = "another-namespace"
        graph = self.graph()
        self.assertNotIn("bound_volume_reference", {edge["relation"] for edge in graph["edges"]})
        public_service = next(node for node in graph["nodes"] if node["label"] == "public-frontend")
        self.assertFalse(any(edge["from"] == public_service["id"] and edge["relation"] == "selects_workload" for edge in graph["edges"]))

    def test_denied_and_gateway_sources_are_unknown_not_empty_healthy(self):
        for collection in self.e.KUBE_PATHS:
            self.raw["inventory"][collection] = []
        self.raw["inventory"]["workloads"] = []
        for source in self.raw["sources"]:
            if source["id"].startswith("kube_"):
                source["status"] = "denied" if source["id"] == "kube_nodes" else "error"
                source["note"] = "SIMULATED 403/502 source gap."
        graph = self.graph()
        self.assertFalse(any(node["kind"] in ("workload", "service", "node") for node in graph["nodes"]))
        self.assertEqual(sum(row["code"] == "architecture_source_incomplete" for row in graph["unknowns"]), len(self.e.KUBE_PATHS))
        self.assertTrue(all(row["status"] == "not_evaluated" for row in graph["unknowns"]))

    def test_reader_closure_is_exact_references_not_all_vnet_children(self):
        rows = self.raw["inventory"]["related_resources"]
        vnet = next(row for row in rows if row["resource_kind"] == "microsoft.network/virtualnetworks")
        self.assertEqual(list(self.e.referenced_resource_ids(vnet)), [])
        subnet = next(row for row in rows if row["resource_kind"].endswith("/subnets"))
        references = list(self.e.referenced_resource_ids(subnet))
        self.assertTrue(any(value == vnet["id"] for value, _ in references))
        vmss = next(row for row in rows if row["resource_kind"] == "microsoft.compute/virtualmachinescalesets")
        self.assertTrue(any(self.e.resource_type(value) == "microsoft.network/loadbalancers"
                            for value, _ in self.e.referenced_resource_ids(vmss)))

    def test_endpoint_kind_is_preserved_when_list_items_omit_kind(self):
        item = api_object("Pod", "app", "client-apps", spec={"containers": []})
        del item["kind"]
        normalized = self.e.normalize_kube(item, "pods", "kube_pods", REFERENCE, self.e.validate_config(""))
        self.assertEqual(normalized["kind"], "Pod")
        item["kind"] = "Secret"
        with self.assertRaises(self.e.EvidenceError):
            self.e.normalize_kube(item, "pods", "kube_pods", REFERENCE, self.e.validate_config(""))

    def test_registry_role_reader_rejects_other_principal_or_unrelated_scope(self):
        role = self.raw["registry_role_assignments"][0]
        for properties in ({"scope": role["scope"], "principalId": "66666666-6666-4666-8666-666666666666"},
                           {"scope": CLUSTER_ID, "principalId": role["principal_id"]}):
            with self.subTest(properties=properties), self.assertRaises(self.e.EvidenceError):
                self.e.normalize_registry_role({"id": role["id"], "properties": {
                    "roleDefinitionId": role["role_definition_id"], **properties}},
                    "arm_registry_roles_1", REFERENCE, self.e.validate_config(""), role["resource_id"], role["principal_id"])

    def test_stopped_cluster_discloses_manifests_unavailable_without_start_or_health_inference(self):
        self.raw["cluster"]["power_state"] = "Stopped"
        self.raw["sources"].append(self.e.source_receipt("kube_access", REFERENCE, "not_applicable"))
        graph = self.graph()
        row = next(row for row in graph["unknowns"] if row["code"] == "stopped_cluster_manifests_unavailable")
        self.assertEqual(row["status"], "not_evaluated")
        self.assertIn("never starts", row["message"])


if __name__ == "__main__":
    unittest.main()

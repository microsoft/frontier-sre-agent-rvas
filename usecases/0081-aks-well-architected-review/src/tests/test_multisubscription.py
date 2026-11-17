"""SIMULATED multi-subscription fleet tests: fixed allowlist across many subscriptions, no discovery."""

import json
import unittest
from unittest.mock import patch

from support import SUBSCRIPTION, load_engine


OTHER = "44444444-4444-4444-8444-444444444444"


def fleet(engine, count, subscriptions=(SUBSCRIPTION, OTHER)):
    engine.CLUSTER_DEFAULTS = {**engine.CLUSTER_DEFAULTS, "environment": "PRODUCTION"}
    engine.APPROVED_CLUSTERS = {
        "aks-fleet-%03d" % index: {"resource_group": "rg-fleet-%03d" % index,
                                   "subscription_id": subscriptions[index % len(subscriptions)]}
        for index in range(count)
    }
    return engine


class MultiSubscriptionTests(unittest.TestCase):
    def setUp(self):
        self.e = load_engine()

    def test_defaults_merge_and_per_cluster_subscription_builds_exact_arm_id(self):
        fleet(self.e, 2)
        config = self.e.validate_config("aks-fleet-001")
        self.assertEqual(config["subscription_id"], OTHER)
        self.assertEqual(config["environment"], "PRODUCTION")
        self.assertTrue(config["kubernetes_enabled"])
        self.assertEqual(config["id"], "/subscriptions/" + OTHER + "/resourceGroups/rg-fleet-001/providers/"
                         "Microsoft.ContainerService/managedClusters/aks-fleet-001")
        self.assertEqual(self.e.validate_config("aks-fleet-000")["subscription_id"], SUBSCRIPTION)

    def test_alias_key_uses_aks_name_and_duplicate_resource_ids_are_rejected(self):
        self.e.APPROVED_CLUSTERS = {
            "sub1-aks-api": {"resource_group": "rg", "aks_name": "aks-api", "environment": "PRODUCTION"},
            "sub2-aks-api": {"resource_group": "rg", "aks_name": "aks-api", "environment": "PRODUCTION", "subscription_id": OTHER},
        }
        config = self.e.validate_config("sub2-aks-api")
        self.assertTrue(config["id"].endswith("/managedClusters/aks-api"))
        self.assertIn(OTHER, config["id"])
        self.e.APPROVED_CLUSTERS["sub3-aks-api"] = {"resource_group": "rg", "aks_name": "aks-api"}
        with self.assertRaises(self.e.EvidenceError) as raised:
            self.e.selection_configs("", "")
        self.assertEqual(raised.exception.code, "configuration_required")

    def test_invalid_subscription_and_aks_name_fail_before_authentication(self):
        for entry in ({"resource_group": "rg", "subscription_id": "not-a-guid"},
                      {"resource_group": "rg", "aks_name": "bad/name"}):
            self.e.APPROVED_CLUSTERS = {"aks-x": entry}
            with self.subTest(entry=entry), patch.object(self.e, "Identity") as identity:
                result = self.e.main(operation="list_clusters")
                self.assertEqual(result["error"]["code"], "configuration_required")
                identity.assert_not_called()

    def test_list_clusters_pages_120_clusters_within_transport_budget(self):
        fleet(self.e, 120, subscriptions=tuple("%08d-1111-4111-8111-111111111111" % n for n in range(1, 31)))
        seen, offset = [], 0
        with patch.object(self.e, "Identity") as identity:
            while offset is not None:
                page = self.e.main(operation="list_clusters", limit=100, offset=offset)
                self.assertEqual(page["status"], "ok")
                self.assertLessEqual(len(json.dumps(page, ensure_ascii=False, separators=(",", ":")).encode()), self.e.TRANSPORT_BYTES)
                self.assertEqual(page["total"], 120)
                self.assertEqual(page["subscription_count"], 30)
                self.assertGreater(page["returned"], 0)
                seen.extend(row["cluster_name"] for row in page["available_clusters"])
                offset = page["next_offset"]
            identity.assert_not_called()
        self.assertEqual(seen, list(self.e.APPROVED_CLUSTERS))

    def test_list_clusters_still_rejects_filters_and_report_rejects_paging(self):
        fleet(self.e, 3)
        self.assertEqual(self.e.main(operation="list_clusters", namespace="x")["error"]["code"], "invalid_combination")
        self.assertEqual(self.e.main(operation="report", offset=5)["error"]["code"], "invalid_combination")

    def test_collection_uses_each_cluster_subscription_and_restores_scope(self):
        fleet(self.e, 2)
        config = self.e.validate_config("aks-fleet-001")
        observed = []

        def fake(cfg, reference, deadline=None):
            observed.append((self.e.scope_subscription(), self.e.same_subscription_id(
                "/subscriptions/" + OTHER + "/resourceGroups/rg/providers/Microsoft.Network/virtualNetworks/v"),
                self.e.same_subscription_id(
                "/subscriptions/" + SUBSCRIPTION + "/resourceGroups/rg/providers/Microsoft.Network/virtualNetworks/v")))
            return {}

        with patch.object(self.e, "_collect_live", side_effect=fake):
            self.e.collect_live(config, "2026-10-10T12:00:00Z")
        self.assertEqual(observed[0][0], OTHER)
        self.assertIsNotNone(observed[0][1])
        self.assertIsNone(observed[0][2])
        self.assertIsNone(self.e.ACTIVE_SUBSCRIPTION_ID)

    def test_large_fleet_report_roster_contains_only_selected_clusters(self):
        fleet(self.e, 40)
        with patch.object(self.e, "collect_live", return_value={}), \
                patch.object(self.e, "finish_snapshot", side_effect=lambda raw, ref, environment=None: {"sources": []}), \
                patch.object(self.e, "write_report", side_effect=lambda snapshot: {"status": "ok", "roster": snapshot["available_clusters"]}):
            result = self.e.main(operation="report", cluster_name="aks-fleet-007")
        self.assertEqual([row["cluster_name"] for row in result["roster"]], ["aks-fleet-007"])
        self.assertIn(OTHER, result["roster"][0]["cluster_id"])


if __name__ == "__main__":
    unittest.main()


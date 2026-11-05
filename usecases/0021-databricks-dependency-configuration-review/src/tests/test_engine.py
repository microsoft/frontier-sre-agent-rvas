import copy
import inspect
import io
import json
import os
import sys
import tempfile
import types
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

from urllib.parse import parse_qsl
from support import (
    CLIENT_ID,
    FEDERATED_APP_ID,
    REFERENCE,
    ROOT,
    SRE_TENANT,
    SUBSCRIPTION,
    TARGET_TENANT,
    WORKSPACE_HOST,
    WORKSPACE_ID,
    WORKSPACE_NAME,
    fixture,
    load_engine,
    make_jwt,
)


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

    def snapshot(self):
        return self.e.finish_snapshot(self.raw, REFERENCE, "SIMULATED", "LAB")

    def check(self, rule_id, raw=None):
        target_raw = raw or self.raw
        dep = self.e.dependencies_for(target_raw, REFERENCE, "SIMULATED")
        return next(row for row in self.e.evaluate(target_raw, REFERENCE, dep) if row["rule_id"] == rule_id)

    def params(self, **kwargs):
        values = {key: value.default for key, value in inspect.signature(self.e.main).parameters.items()}
        values.update(operation="query", **kwargs)
        return self.e.validate_parameters(**values)

    def test_catalog_pin_and_all_36_rules_represented(self):
        dep = self.e.dependencies_for(self.raw, REFERENCE, "SIMULATED")
        checks = self.e.evaluate(self.raw, REFERENCE, dep)
        catalog = json.loads((ROOT / "rules_catalog.json").read_text(encoding="utf-8"))
        self.assertEqual(len(catalog["rules"]), 36)
        self.assertEqual({r["rule_id"] for r in checks}, {r["rule_id"] for r in catalog["rules"]})
        self.assertEqual(len({r["check_id"] for r in checks}), len(checks))
        self.assertTrue(all(r["learn_url"].startswith("https://learn.microsoft.com/") for r in checks))

    def test_parameters_schema_defaults_types_and_bounds(self):
        schema = json.loads((ROOT / "tool-parameters.schema.json").read_text(encoding="utf-8"))
        signature = inspect.signature(self.e.main)
        self.assertEqual(set(schema["properties"]), set(signature.parameters))
        for name, parameter in signature.parameters.items():
            self.assertEqual(parameter.default, schema["properties"][name]["default"])
            self.assertEqual("integer" if parameter.annotation is int else "string", schema["properties"][name]["type"])
        self.params(limit=1, offset=0)
        self.params(limit=100, offset=500000)
        self.params(view="dependencies", classification="OBSERVED")
        self.params(view="dependencies", classification="INFERRED")
        self.params(view="dependencies", classification="UNKNOWN")
        for invalid in (
            dict(limit=0),
            dict(limit=101),
            dict(limit=True),
            dict(offset=-1),
            dict(offset=500001),
            dict(workload_name="../../etc/passwd"),
            dict(workspace_name="https://evil.invalid"),
            dict(view="unknown"),
            dict(view="jobs", classification="OBSERVED"),
            dict(view="coverage", status="failed"),
            dict(view="workspace", severity="high"),
        ):
            with self.subTest(invalid=invalid), self.assertRaises(self.e.EvidenceError):
                self.params(**invalid)

    def test_report_rejects_narrowing_and_paging(self):
        defaults = {key: value.default for key, value in inspect.signature(self.e.main).parameters.items()}
        self.e.validate_parameters(**defaults)
        for changes in (
            dict(workload_name="job-1"),
            dict(view="dependencies"),
            dict(classification="OBSERVED"),
            dict(limit=1),
            dict(offset=1),
            dict(status="failed"),
        ):
            with self.subTest(changes=changes), self.assertRaises(self.e.EvidenceError):
                self.e.validate_parameters(**{**defaults, **changes})

    def test_default_code_fails_before_auth_or_network(self):
        with patch.object(self.e, "SUBSCRIPTION_ID", "<YOUR_TARGET_SUBSCRIPTION_ID>"), patch.object(self.e, "Identity") as identity:
            result = self.e.main()
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"]["code"], "configuration_required")
        self.assertEqual(result["artifact_status"], "not_written")
        identity.assert_not_called()
        self.assertLessEqual(len(json.dumps(result).encode("utf-8")), 3500)

    def test_cross_tenant_modes_and_same_tenant_gate(self):
        ws_cfg = copy.deepcopy(self.e.APPROVED_WORKSPACES[WORKSPACE_NAME])
        ws_cfg["auth_mode"] = "same_tenant_uami"
        with patch.dict(self.e.APPROVED_WORKSPACES, {WORKSPACE_NAME: ws_cfg}):
            with self.assertRaises(self.e.EvidenceError) as raised:
                self.e.validate_config(WORKSPACE_NAME)
            self.assertEqual(raised.exception.code, "cross_tenant_configuration_required")

        with patch.object(self.e, "FEDERATED_APP_CLIENT_ID", ""):
            with self.assertRaises(self.e.EvidenceError) as raised:
                self.e.validate_config(WORKSPACE_NAME)
            self.assertEqual(raised.exception.code, "configuration_required")

        kv_cfg = copy.deepcopy(self.e.APPROVED_WORKSPACES[WORKSPACE_NAME])
        kv_cfg["auth_mode"] = "cross_tenant_lighthouse_plus_keyvault_oauth_m2m"
        with patch.dict(self.e.APPROVED_WORKSPACES, {WORKSPACE_NAME: kv_cfg}), patch.object(self.e, "KEYVAULT_OAUTH_SECRET_URI", ""):
            with self.assertRaises(self.e.EvidenceError) as raised:
                self.e.validate_config(WORKSPACE_NAME)
            self.assertEqual(raised.exception.code, "configuration_required")

        with patch.dict(self.e.APPROVED_WORKSPACES, {WORKSPACE_NAME: kv_cfg}), patch.object(
            self.e, "KEYVAULT_OAUTH_SECRET_URI", "https://kv-sre-tenant-a.vault.azure.net/secrets/dbx-m2m-secret"
        ):
            cfg = self.e.validate_config(WORKSPACE_NAME)
            self.assertEqual(cfg["auth_mode"], "cross_tenant_lighthouse_plus_keyvault_oauth_m2m")

    def test_identity_token_exchange_flows(self):
        config = self.e.validate_config(WORKSPACE_NAME)
        fake_cred = MagicMock()
        fake_cred.get_token.side_effect = lambda scope: MagicMock(
            token=make_jwt(SRE_TENANT, CLIENT_ID, scope.removesuffix("/.default"))
        )
        target_arm_jwt = make_jwt(TARGET_TENANT, FEDERATED_APP_ID, self.e.ARM_ORIGIN)
        target_dbx_jwt = make_jwt(TARGET_TENANT, FEDERATED_APP_ID, self.e.DATABRICKS_ENTRA_RESOURCE)

        captured_requests = []

        def fake_open(req, timeout=20):
            url = req.full_url
            body = (req.data or b"").decode("utf-8")
            captured_requests.append({
                "url": url,
                "method": req.get_method(),
                "headers": dict(req.header_items()),
                "form": dict(parse_qsl(body, keep_blank_values=True)),
            })
            resp = MagicMock()
            resp.status = 200
            resp.__enter__.return_value = resp
            if "login.microsoftonline.com" in url and "management.azure.com" in body:
                resp.read.return_value = json.dumps({"access_token": target_arm_jwt}).encode("utf-8")
            elif "login.microsoftonline.com" in url and self.e.DATABRICKS_ENTRA_RESOURCE in body:
                resp.read.return_value = json.dumps({"access_token": target_dbx_jwt}).encode("utf-8")
            elif "/oidc/v1/token" in url:
                resp.read.return_value = json.dumps({"access_token": "dbx-oidc-token-123"}).encode("utf-8")
            elif "vault.azure.net" in url:
                resp.read.return_value = json.dumps({"value": "super-secret-m2m"}).encode("utf-8")
            return resp

        fake_azure = types.ModuleType("azure")
        fake_identity_mod = types.ModuleType("azure.identity")
        fake_core_mod = types.ModuleType("azure.core")
        fake_exc_mod = types.ModuleType("azure.core.exceptions")
        fake_identity_mod.ManagedIdentityCredential = MagicMock(return_value=fake_cred)
        fake_identity_mod.CredentialUnavailableError = RuntimeError
        fake_exc_mod.ClientAuthenticationError = RuntimeError
        fake_exc_mod.ServiceRequestError = RuntimeError
        with patch.dict(sys.modules, {
            "azure": fake_azure,
            "azure.identity": fake_identity_mod,
            "azure.core": fake_core_mod,
            "azure.core.exceptions": fake_exc_mod,
        }):
            ident = self.e.Identity(config)
            with patch.object(ident.opener, "open", side_effect=fake_open):
                self.assertEqual(ident.arm_token(), target_arm_jwt)
                self.assertEqual(ident.databricks_token(), target_dbx_jwt)
                self.assertEqual(ident.exchange_databricks_oidc(WORKSPACE_HOST), "dbx-oidc-token-123")
                oidc_req = next(r for r in captured_requests if r["url"] == "https://" + WORKSPACE_HOST + "/oidc/v1/token")
                expected_subject = make_jwt(SRE_TENANT, CLIENT_ID, self.e.ENTRA_TOKEN_EXCHANGE_AUDIENCE)
                self.assertEqual(oidc_req["method"], "POST")
                self.assertEqual(oidc_req["form"], {
                    "client_id": FEDERATED_APP_ID.lower(),
                    "subject_token": expected_subject,
                    "subject_token_type": "urn:ietf:params:oauth:token-type:jwt",
                    "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
                    "scope": "all-apis",
                })
                with patch.object(self.e, "KEYVAULT_OAUTH_SECRET_URI", "https://kv-sre-a.vault.azure.net/secrets/dbx-m2m"):
                    self.assertEqual(ident.exchange_keyvault_oauth_m2m(WORKSPACE_HOST), "dbx-oidc-token-123")

    def test_dependency_graph_classifications_and_broken_references(self):
        snap = self.snapshot()
        dep = snap["dependencies"]
        counts = dep["summary_counts"]
        self.assertGreater(counts["edges_observed"], 15)
        self.assertGreaterEqual(counts["edges_inferred"], 2)
        self.assertGreaterEqual(counts["unknowns_total"], 3)
        self.assertEqual(counts["broken_references_total"], 0)
        self.assertEqual(self.check("G05")["status"], "passed")
        self.assertEqual(self.check("G06")["status"], "not_evaluated")
        self.assertEqual(self.check("R06")["status"], "not_evaluated")

        inferred_relations = {e["relation"] for e in dep["edges"] if e["classification"] == "INFERRED"}
        self.assertIn("inferred_adls_storage_uri_target", inferred_relations)
        self.assertIn("inferred_cmk_key_vault_uri", inferred_relations)
        self.assertIn("inferred_dbfs_root_storage_name", inferred_relations)

        observed_relations = {e["relation"] for e in dep["edges"] if e["classification"] == "OBSERVED"}
        for expected_rel in (
            "injected_into_vnet",
            "uses_access_connector",
            "governed_by_policy",
            "backed_by_instance_pool",
            "depends_on_task",
            "triggers_dlt_pipeline",
            "executes_on_sql_warehouse",
            "triggers_downstream_job",
            "uses_storage_credential",
            "points_to_adls_storage_account",
            "backed_by_key_vault",
        ):
            self.assertIn(expected_rel, observed_relations)

        # Introduce a confirmed intra-job broken reference (job_cluster_key_missing) and verify G05 fails
        mutated = copy.deepcopy(self.raw)
        mutated["inventory"]["jobs"][1]["tasks"][0]["job_cluster_key"] = "missing-jc-key"
        broken_check = self.check("G05", mutated)
        self.assertEqual(broken_check["status"], "failed")
        self.assertEqual(broken_check["evidence"][0]["value"]["broken_references_count"], 1)

        # Cross-object unseen reference (e.g. existing_cluster_id filtered by ACLs or policy_id on denied source) stays UNKNOWN / not_evaluated
        acl_filtered = copy.deepcopy(self.raw)
        acl_filtered["inventory"]["jobs"][1]["tasks"][0]["existing_cluster_id"] = "unseen-by-acl-cluster-999"
        acl_check = self.check("G05", acl_filtered)
        self.assertEqual(acl_check["status"], "not_evaluated")
        self.assertEqual(acl_check["evidence"][0]["value"]["broken_references_count"], 0)
        self.assertEqual(acl_check["evidence"][0]["value"]["unverified_references_count"], 1)

        denied_policies = copy.deepcopy(self.raw)
        denied_policies["inventory"]["cluster_policies"] = []
        next(s for s in denied_policies["sources"] if s["id"] == "dbx_cluster_policies")["status"] = "denied"
        denied_check = self.check("G05", denied_policies)
        self.assertEqual(denied_check["status"], "not_evaluated")
        self.assertEqual(denied_check["evidence"][0]["value"]["broken_references_count"], 0)

    def test_arm_audience_aliases_and_strict_other_audiences(self):
        for valid_arm_aud in (
            "https://management.azure.com",
            "https://management.azure.com/",
            "https://management.core.windows.net",
            "https://management.core.windows.net/",
        ):
            tok = make_jwt(SRE_TENANT, CLIENT_ID, valid_arm_aud)
            claims = self.e.verify_jwt_claims(tok, SRE_TENANT, CLIENT_ID, self.e.ARM_ORIGIN)
            self.assertEqual(claims["tid"], SRE_TENANT)
        bad_dbx_tok = make_jwt(SRE_TENANT, CLIENT_ID, "https://management.core.windows.net")
        with self.assertRaises(self.e.EvidenceError):
            self.e.verify_jwt_claims(bad_dbx_tok, SRE_TENANT, CLIENT_ID, self.e.DATABRICKS_ENTRA_RESOURCE)

    def test_lighthouse_arm_only_validates_without_databricks_client_or_secret(self):
        for mode in ("cross_tenant_lighthouse_plus_databricks_oidc", "cross_tenant_lighthouse_plus_keyvault_oauth_m2m"):
            ws_cfg = copy.deepcopy(self.e.APPROVED_WORKSPACES[WORKSPACE_NAME])
            ws_cfg.update(auth_mode=mode, workspace_api_enabled=False, unity_catalog_enabled=False, workspace_host="")
            with patch.dict(self.e.APPROVED_WORKSPACES, {WORKSPACE_NAME: ws_cfg}), patch.object(
                self.e, "FEDERATED_APP_CLIENT_ID", ""
            ), patch.object(self.e, "KEYVAULT_OAUTH_SECRET_URI", ""):
                cfg = self.e.validate_config(WORKSPACE_NAME)
                self.assertEqual(cfg["auth_mode"], mode)
                self.assertFalse(cfg["workspace_api_enabled"])
            ws_cfg["workspace_api_enabled"] = True
            ws_cfg["workspace_host"] = WORKSPACE_HOST
            with patch.dict(self.e.APPROVED_WORKSPACES, {WORKSPACE_NAME: ws_cfg}), patch.object(
                self.e, "FEDERATED_APP_CLIENT_ID", ""
            ), patch.object(self.e, "KEYVAULT_OAUTH_SECRET_URI", ""):
                with self.assertRaises(self.e.EvidenceError) as raised:
                    self.e.validate_config(WORKSPACE_NAME)
                self.assertEqual(raised.exception.code, "configuration_required")

    def test_related_resources_unique_sids_cap_and_udr_route_tables(self):
        rt_id = "/subscriptions/" + SUBSCRIPTION + "/resourceGroups/rg-databricks-prod/providers/Microsoft.Network/routeTables/rt-dbx-udr"
        sub_id = "/subscriptions/" + SUBSCRIPTION + "/resourceGroups/rg-databricks-prod/providers/Microsoft.Network/virtualNetworks/vnet-dbx-prod/subnets/snet-dbx-host"
        sub_row = self.e.normalize_resource({
            "id": sub_id,
            "name": "snet-dbx-host",
            "location": "westeurope",
            "properties": {
                "addressPrefix": "10.40.1.0/24",
                "routeTable": {"id": rt_id},
            },
        }, "arm_resource_sub", REFERENCE, self.config, {"type": "direct_reference", "source_id": "arm_workspace"})
        self.assertEqual(sub_row["route_table_id"], rt_id)
        refs = dict(self.e.referenced_resource_ids(sub_row))
        self.assertEqual(refs.get(rt_id), "route_table_id")

        rt_row = self.e.normalize_resource({
            "id": rt_id,
            "name": "rt-dbx-udr",
            "location": "westeurope",
            "properties": {
                "disableBgpRoutePropagation": True,
                "routes": [{"name": "to-firewall", "properties": {"addressPrefix": "0.0.0.0/0", "nextHopType": "VirtualAppliance", "nextHopIpAddress": "10.40.0.4"}}],
            },
        }, "arm_resource_rt", REFERENCE, self.config, {"type": "direct_reference", "source_id": "arm_resource_sub", "field": "route_table_id"})
        self.assertTrue(rt_row["disable_bgp_route_propagation"])
        self.assertEqual(rt_row["routes"][0]["next_hop_type"], "VirtualAppliance")

        raw_with_rt = copy.deepcopy(self.raw)
        raw_with_rt["inventory"]["related_resources"][1] = sub_row
        raw_with_rt["inventory"]["related_resources"].append(rt_row)
        dep = self.e.dependencies_for(raw_with_rt, REFERENCE, "SIMULATED")
        self.assertTrue(any(e["relation"] == "associated_route_table" and e["classification"] == "OBSERVED" for e in dep["edges"]))

    def test_native_pipeline_list_detail_spec_schema_and_job_truncation_and_denied_related_sids(self):
        ac_id = "/subscriptions/" + SUBSCRIPTION + "/resourceGroups/rg-databricks-prod/providers/Microsoft.Databricks/accessConnectors/ac-1"
        st_id = "/subscriptions/" + SUBSCRIPTION + "/resourceGroups/rg-databricks-prod/providers/Microsoft.Storage/storageAccounts/stcap2"

        def fake_request(reader_self, method, url, source, body=None, allow_empty=False):
            if url.endswith("/providers/Microsoft.Databricks/workspaces/" + WORKSPACE_NAME + "?api-version=2024-05-01"):
                return {
                    "id": WORKSPACE_ID,
                    "name": WORKSPACE_NAME,
                    "location": "westeurope",
                    "sku": {"name": "premium"},
                    "properties": {
                        "workspaceUrl": WORKSPACE_HOST,
                        "provisioningState": "Succeeded",
                        "accessConnector": {"id": ac_id, "identityType": "SystemAssigned"},
                    },
                }
            if "/outboundNetworkDependenciesEndpoints" in url:
                return []
            if "/diagnosticSettings" in url:
                return {"value": []}
            if ac_id.lower() in url.lower():
                raise self.e.EvidenceError("access_denied", "HTTP 403", source, 403)
            if "/api/2.0/workspace-conf" in url:
                return {"enableTokensConfig": "false"}
            if "/api/2.0/clusters/list" in url:
                return {"clusters": []}
            if "/api/2.0/instance-pools/list" in url:
                return {"instance_pools": []}
            if "/api/2.0/policies/clusters/list" in url:
                return {"policies": [{"policy_id": "POL-SHARED-01", "name": "Shared Policy"}]}
            if "/api/2.1/jobs/list" in url:
                return {
                    "jobs": [{
                        "job_id": 501,
                        "has_more": True,
                        "settings": {
                            "name": "truncated-job",
                            "tasks": [{"task_key": "step_2", "depends_on": [{"task_key": "step_1"}]}],
                        },
                    }]
                }
            if "/api/2.1/jobs/get" in url:
                return {
                    "job_id": 501,
                    "has_more": False,
                    "settings": {
                        "name": "truncated-job",
                        "tasks": [
                            {"task_key": "step_1"},
                            {"task_key": "step_2", "depends_on": [{"task_key": "step_1"}]},
                        ],
                    },
                }
            if url.endswith("/api/2.0/pipelines?max_results=50"):
                return {"statuses": [{"pipeline_id": "PIPE-NATIVE-1", "name": "dlt-native", "state": "IDLE"}]}
            if url.endswith("/api/2.0/pipelines/PIPE-NATIVE-1"):
                return {
                    "pipeline_id": "PIPE-NATIVE-1",
                    "name": "dlt-native",
                    "state": "IDLE",
                    "spec": {
                        "catalog": "main_prod",
                        "schema": "silver_sales",
                        "storage": "abfss://dlt@stadlsprod001.dfs.core.windows.net/p1",
                        "serverless": True,
                        "clusters": [{"label": "default", "policy_id": "POL-SHARED-01"}],
                    },
                }
            if "/api/2.0/sql/warehouses" in url:
                return {"warehouses": []}
            if "/api/2.0/secrets/scopes/list" in url:
                return {"scopes": []}
            if "/api/2.0/global-init-scripts" in url:
                return {"scripts": []}
            if "/api/2.1/unity-catalog/metastore_summary" in url:
                return {"metastore_id": "ms-1", "name": "ms-main"}
            if "/api/2.1/unity-catalog/catalogs" in url:
                return {"catalogs": [{"name": "main_prod", "catalog_type": "MANAGED_CATALOG"}]}
            if "/api/2.1/unity-catalog/schemas" in url:
                return {"schemas": [{"full_name": "main_prod.silver_sales", "name": "silver_sales", "catalog_name": "main_prod"}]}
            if "/api/2.1/unity-catalog/storage-credentials" in url:
                return {"storage_credentials": []}
            if "/api/2.1/unity-catalog/external-locations" in url:
                return {"external_locations": []}
            if "/api/2.1/unity-catalog/connections" in url:
                return {"connections": []}
            if "/providers/Microsoft.Advisor/recommendations" in url:
                return {"value": []}
            return {}

        cfg = copy.deepcopy(self.config)
        cfg["approved_related_resource_ids"] = [ac_id, st_id]
        cfg["include_managed_resource_group"] = False
        cfg["cost_scope"] = "disabled"
        fake_ident = MagicMock()
        fake_ident.deadline = 999999999.0
        with patch.object(self.e, "Identity", return_value=fake_ident), patch.object(
            self.e, "MAX_RELATED_RESOURCES", 1
        ), patch.object(self.e.HttpReader, "request", new=fake_request):
            collected = self.e.collect_live(cfg, REFERENCE)

        sids = [s["id"] for s in collected["sources"]]
        self.assertEqual(len(sids), len(set(sids)))
        self.assertIn("arm_related_cap", sids)
        pipe = collected["inventory"]["pipelines"][0]
        self.assertTrue(pipe["detail_collected"])
        self.assertEqual(pipe["catalog"], "main_prod")
        self.assertEqual(pipe["schema"], "silver_sales")
        self.assertEqual(pipe["target"], "silver_sales")
        job = collected["inventory"]["jobs"][0]
        self.assertFalse(job["tasks_incomplete"])
        self.assertEqual(len(job["tasks"]), 2)
        dep = self.e.dependencies_for(collected, REFERENCE, "SIMULATED")
        self.assertEqual(dep["broken_references"], [])
        self.assertTrue(any(e["relation"] == "publishes_to_schema" for e in dep["edges"]))
        self.assertTrue(any(e["relation"] == "governed_by_policy" for e in dep["edges"]))

        # Regression: detail GET returning 100 tasks + next_page_token and upstream outside page stays UNKNOWN, never broken / G05 failed
        detail_100_tasks = [{"task_key": f"task_{i:03d}"} for i in range(99)] + [
            {"task_key": "task_099", "depends_on": [{"task_key": "task_outside_page_101"}], "job_cluster_key": "jc_outside_page"}
        ]
        detail_job = self.e.normalize_job(
            {
                "job_id": 502,
                "next_page_token": "tok-page-2",
                "settings": {"name": "job-100-tasks-paged", "tasks": detail_100_tasks},
            },
            "dbx_job_detail_1",
            REFERENCE,
            self.config,
            from_detail=True,
        )
        self.assertTrue(detail_job["tasks_incomplete"])
        raw_paged_job = copy.deepcopy(self.raw)
        raw_paged_job["inventory"]["jobs"] = [detail_job]
        dep_paged = self.e.dependencies_for(raw_paged_job, REFERENCE, "SIMULATED")
        self.assertEqual(dep_paged["broken_references"], [])
        self.assertTrue(any(u["code"] == "job_tasks_truncated_or_incomplete_502" for u in dep_paged["unknowns"]))
        self.assertEqual(self.check("G05", raw_paged_job)["status"], "not_evaluated")

    def test_whitelist_excludes_secrets_env_vars_notebook_code_and_job_params(self):
        sentinel = "SIMULATED-SENSITIVE-VALUE-NEVER-EXPORTED"
        cl = self.e.normalize_cluster({
            "cluster_id": "cl-sec-1",
            "cluster_name": "sec-cluster",
            "cluster_source": "UI",
            "state": "TERMINATED",
            "spark_version": "15.4.x-scala2.12-lts",
            "spark_env_vars": {"MY_SECRET": sentinel},
            "spark_conf": {"fs.azure.account.key": sentinel},
            "ssh_public_keys": [sentinel],
            "init_scripts": [{"workspace": {"destination": sentinel}}],
            "custom_tags": {"api_token": sentinel, "team": "data-eng"},
        }, "dbx_clusters", REFERENCE, self.config)
        self.assertNotIn(sentinel, json.dumps(cl))
        self.assertEqual(cl["custom_tags"], {"team": "data-eng"})

        job = self.e.normalize_job({
            "job_id": 999,
            "settings": {
                "name": "sec-job",
                "parameters": [{"name": "p", "default": sentinel}],
                "tasks": [{
                    "task_key": "t1",
                    "notebook_task": {"notebook_path": "/Repos/prod/nb", "base_parameters": {"secret": sentinel}},
                    "python_wheel_task": {"named_parameters": {"secret": sentinel}},
                    "spark_jar_task": {"parameters": [sentinel]},
                    "sql_task": {"warehouse_id": "WH-1", "parameters": {"secret": sentinel}},
                }],
            },
        }, "dbx_jobs", REFERENCE, self.config)
        self.assertNotIn(sentinel, json.dumps(job))

        dummy_ident = MagicMock()
        reader = self.e.HttpReader(dummy_ident, "https://" + WORKSPACE_HOST, "databricks")
        for forbidden_path in (
            "/api/2.0/secrets/get",
            "/api/2.0/secrets/put",
            "/api/2.0/clusters/start",
            "/api/2.0/jobs/run-now",
            "/api/2.0/sql/statements",
            "/api/1.2/commands/execute",
        ):
            with self.subTest(path=forbidden_path), self.assertRaises(self.e.EvidenceError):
                reader.allow("https://" + WORKSPACE_HOST + forbidden_path, "GET")

    def test_query_paging_and_3500_byte_transport_budget(self):
        snap = self.snapshot()
        for cls in ("OBSERVED", "INFERRED", "UNKNOWN"):
            res = self.e.query_snapshot(snap, self.params(view="dependencies", classification=cls, limit=10))
            self.assertEqual(res["status"], "ok")
            self.assertGreater(res["total_matched"], 0)
            self.assertTrue(all(r["classification"] == cls for r in res["rows"]))
            self.assertLessEqual(self.e.response_bytes(res), 3500)

        oversized = copy.deepcopy(snap)
        oversized["actions"] = [{"id": "big", "title": "x" * 4000}]
        res_err = self.e.query_snapshot(oversized, self.params(view="actions", limit=5))
        self.assertEqual(res_err["status"], "error")
        self.assertEqual(res_err["error"]["code"], "query_row_too_large")
        self.assertLessEqual(self.e.response_bytes(res_err), 3500)

    def test_multi_workspace_preserves_failed_workspace_without_healthy_zero_substitution(self):
        snap = self.snapshot()
        second_id = WORKSPACE_ID.replace(WORKSPACE_NAME, "dbx-dr-weu-02")
        runs = [
            {"workspace_id": WORKSPACE_ID, "workspace_name": WORKSPACE_NAME, "reference_utc": REFERENCE, "snapshot": snap, "error": None, "status": "ok"},
            {
                "workspace_id": second_id,
                "workspace_name": "dbx-dr-weu-02",
                "reference_utc": REFERENCE,
                "snapshot": None,
                "error": {"code": "access_denied", "message": "HTTP 403", "source_id": "arm_workspace", "http_status": 403},
                "status": "error",
            },
        ]
        roster = [
            {"workspace_id": WORKSPACE_ID, "workspace_name": WORKSPACE_NAME, "resource_group": "rg", "workspace_host": WORKSPACE_HOST, "environment": "LAB", "auth_mode": "cross_tenant_multitenant_fic", "cross_tenant": True},
            {"workspace_id": second_id, "workspace_name": "dbx-dr-weu-02", "resource_group": "rg", "workspace_host": WORKSPACE_HOST, "environment": "LAB", "auth_mode": "cross_tenant_multitenant_fic", "cross_tenant": True},
        ]
        multi = self.e.multi_snapshot(runs, REFERENCE, roster)
        self.assertEqual(multi["aggregate"]["failed_workspace_count"], 1)
        summary_res = self.e.query_snapshot(multi, self.params(view="summary", limit=10))
        self.assertEqual(summary_res["status"], "partial")
        self.assertEqual(len(summary_res["rows"]), 2)
        self.assertIsNone(summary_res["rows"][1]["global"])
        self.assertEqual(summary_res["rows"][1]["error"]["code"], "access_denied")

    def test_entra_token_exchange_guid_audience_and_plane2_resilience_when_arm_denied(self):
        # 1. Verify ENTRA_TOKEN_EXCHANGE_AUDIENCES accepts both URI and first-party appId GUID
        jwt_guid = make_jwt(SRE_TENANT, CLIENT_ID, "fb60f99c-7a34-4190-8149-302f77469936")
        claims = self.e.verify_jwt_claims(
            jwt_guid,
            SRE_TENANT,
            CLIENT_ID,
            self.e.ENTRA_TOKEN_EXCHANGE_AUDIENCE,
        )
        self.assertEqual(claims["aud"], "fb60f99c-7a34-4190-8149-302f77469936")

        # 2. Verify C03 is not_evaluated when arm_workspace is denied, and G03 is not_evaluated under BROWSE-only projection
        arm_denied_raw = copy.deepcopy(self.raw)
        for s in arm_denied_raw["sources"]:
            if s["id"] == "arm_workspace":
                s["status"] = "denied"
        arm_denied_raw["workspace"]["custom_virtual_network_id"] = None
        arm_denied_raw["inventory"]["uc_storage_credentials"] = []
        arm_denied_raw["inventory"]["uc_external_locations"] = [{
            "id": "external_location:gestamp_browse",
            "name": "gestamp_browse",
            "workload_name": "gestamp_browse",
            "kind": "ExternalLocation",
            "url": "abfss://unity-catalog-storage@dbstoragecliente01.dfs.core.windows.net/123",
            "credential_name": None,
            "credential_id": None,
            "read_only": None,
            "isolation_mode": None,
            "metastore_id": None,
            "resource_id": WORKSPACE_ID,
            "workspace_name": WORKSPACE_NAME,
            "workspace_id": WORKSPACE_ID,
            "source_id": "uc_external_locations",
            "observed_at": REFERENCE,
        }]
        c03 = self.check("C03", arm_denied_raw)
        self.assertEqual(c03["status"], "not_evaluated")
        g03 = self.check("G03", arm_denied_raw)
        self.assertEqual(g03["status"], "not_evaluated")


if __name__ == "__main__":
    unittest.main()

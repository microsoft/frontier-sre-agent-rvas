---
name: databricks-dependency-live
description: Read-only, evidence-qualified Azure Databricks dependency mapping, configuration, security, FinOps and optimization review using the single fixed-scope tool.
---

# Azure Databricks dependency and configuration review

Use ONLY `generate-databricks-dependency-report`. The operator must explicitly
select that one tool and this skill for `databricks-dependency-live`; no
inherited tools, shell, exec, generic Python, SQL execution tools, remediation
connectors or role-grant tools.

## Scope, cross-tenant identity and evidence boundaries

The code contains fixed administrator constants: `SUBSCRIPTION_ID`,
`SRE_TENANT_ID`, `TARGET_TENANT_ID`, `MANAGED_IDENTITY_CLIENT_ID`, optional
`FEDERATED_APP_CLIENT_ID`, optional `KEYVAULT_OAUTH_SECRET_URI`, and the
`APPROVED_WORKSPACES` allowlist. Tool parameters cannot change credentials,
tenants, workspace hosts, endpoints, SQL/KQL queries, filesystem paths, billing
scopes or resource IDs.

- If the fixed configuration still contains `<PLACEHOLDER>` values, the tool
  stops before any authentication or network call with `status="error"` and
  `error.code="configuration_required"` (`artifact_status="not_written"`).
- If `SRE_TENANT_ID != TARGET_TENANT_ID` and `auth_mode == "same_tenant_uami"`,
  the tool stops before authentication with
  `error.code="cross_tenant_configuration_required"`. A single-tenant SRE UAMI
  in Tenant A never automatically obtains Tenant B tokens or Databricks
  workspace permissions.
- Keep **Azure Resource Manager (ARM) control plane** (`management.azure.com`)
  strictly separate from the **Azure Databricks Workspace & Unity Catalog REST
  plane** (`https://adb-<id>.<shard>.azuredatabricks.net`). Azure Lighthouse
  delegation projects ARM RBAC only; it does not grant Databricks Workspace or
  Unity Catalog access.
- Supported cross-tenant modes are:
  1. `cross_tenant_multitenant_fic`: Multi-tenant Entra App Registration in the
     SRE tenant trusting the SRE UAMI via Federated Identity Credential
     (`api://AzureADTokenExchange`) and provisioned as a Service Principal in
     the target tenant for both ARM and Databricks (`2ff814a6-3304-4ab8-85cb-cd0e6f879c1d/.default`).
  2. `cross_tenant_lighthouse_plus_databricks_oidc`: Azure Lighthouse for ARM
     reads plus Databricks Service Principal Federation Policy (`/oidc/v1/token`
     RFC 8693 `grant_type=urn:ietf:params:oauth:grant-type:token-exchange` with
     `client_id`, `subject_token`, `subject_token_type=urn:ietf:params:oauth:token-type:jwt`,
     `scope=all-apis`) for Workspace/Unity Catalog REST reads.
  3. `cross_tenant_lighthouse_plus_keyvault_oauth_m2m`: Azure Lighthouse for ARM
     reads plus in-memory OAuth M2M secret resolution from an approved Key Vault
     in the SRE tenant using the SRE UAMI (`https://vault.azure.net/.default`).

Use `operation="list_workspaces"` with other defaults to list the fixed
operator-configured roster without authentication or network access. This
roster is configuration metadata, not proof that a workspace exists, is
reachable or authorizes reads.

## Deep dependency mapping contract (`OBSERVED` vs `INFERRED` vs `UNKNOWN`)

Every dependency node, edge and blind spot carries an explicit
`classification`:

- **`OBSERVED`**: Exact native ID or key join verified across collected API
  responses (`job_task.depends_on`, `job_task.existing_cluster_id`,
  `job_task.job_cluster_key`, `job_task.pipeline_id`, `job_task.warehouse_id`,
  `job_task.run_job_id`, `cluster.policy_id`, `cluster.instance_pool_id`,
  `uc_external_location.credential_name`,
  `uc_storage_credential.access_connector_id`,
  `secret_scope.keyvault_metadata.resource_id`, `dlt_pipeline.catalog`/`target`,
  and ARM `customVirtualNetworkId`, `accessConnector.id`,
  `managedResourceGroupId`, `outboundNetworkDependenciesEndpoints`).
- **`INFERRED`**: Explicit URI or hostname reference in configuration where the
  target Azure resource detail was not collected in ARM (for example, an
  `abfss://container@account.dfs.core.windows.net` external location or CMK
  `keyVaultUri` whose target storage account or Key Vault is outside the
  collected ARM inventory). Never present an `INFERRED` reference as a verified
  live connection.
- **`UNKNOWN`**: Uncollected or out-of-scope dependency layers that require
  running compute or code inspection:
  - Runtime table and column lineage (`system.access.table_lineage`,
    `system.access.column_lineage`) and historical DBU billing
    (`system.billing.usage`), which require executing SQL on a running SQL
    Warehouse.
  - Dynamic paths, JDBC strings or table names embedded inside notebook,
    Python or JAR code.
  - Effective data-plane packet flow, DNS resolution and storage/Key Vault
    firewall ACL evaluation.

Never fabricate table lineage from job or notebook names, and never start a
cluster or SQL Warehouse to fill gaps.

## Report and four-file delivery

Make one complete call with `operation="report"` and other defaults except an
approved `workspace_name` or `workspace_names`. No local filter or paging
combination is valid for a report. **Immediately render all four provided
files**: HTML (`report_path`), full normalized JSON (`snapshot_path`), failed
findings CSV (`findings_csv_path`) and dependencies CSV
(`dependencies_csv_path`).

- For `sharing_mode="native_ui"`, render all four unchanged `*_url` values
  (`report_url`, `snapshot_url`, `findings_csv_url`, `dependencies_csv_url`) as
  native Markdown links/file widgets in the same response; the tool derives
  them from the verified SRE runtime thread directory. Never invent or reuse a
  host/thread/sandbox prefix. `http_verified=false` does not suppress these
  provided links; `artifact_status="written"` is not an HTTP download receipt.
- For `sharing_mode="local_files_only"`, expose the unchanged actual `*_path`
  values and state that `cwd` is outside the supported native runtime roots.
- On `status="error"`, report the sanitized `error.code`, `error.source_id` and
  `error.http_status` and stop. Do not claim completion, invent files, narrow
  scope, use ZIP/storage fallbacks or substitute a simulated report.

## Grounded questions

Use `operation="query"` with `view` in `summary`, `workspace`, `compute`,
`jobs`, `pipelines`, `warehouses`, `unity_catalog`, `resources`, `findings`,
`finops`, `coverage`, `actions`, or `dependencies`.

- Use `classification` (`OBSERVED`, `INFERRED`, `UNKNOWN`) with
  `view="dependencies"` to filter the dependency graph by provenance.
- Use `workload_name` for exact local filtering by cluster, job, pipeline,
  warehouse, Unity Catalog object or resource name.
- Use `area`, `level`, `severity` and `status` only where documented.
- Honor exact `total_matched`, `returned`, `has_more`, `next_offset`,
  `transport_capped` and fresh-collection disclosure under the 3,500-byte
  default-serialized response budget.
- Scores are local assessment indicators, never an official Microsoft WAF or
  Databricks grade. Always report evaluated, `not_evaluated` (`No evaluado`) and
  `not_applicable` (`No aplica`) counts alongside any score.

## Never do

No Azure RBAC or Unity Catalog grants, no multi-tenant consent or federation
policy creation, no cluster or SQL Warehouse start/stop, no job or pipeline
runs, no `/api/2.0/sql/statements` execution, no `/api/2.0/secrets/get` calls,
no export of `spark_env_vars`, `spark_conf`, init script bodies, notebook code
or job parameter values, and no fabricated savings or lineage.

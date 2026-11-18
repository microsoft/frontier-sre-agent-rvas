---
name: databricks-dependency-live
description: Read-only Azure Databricks dependency, configuration, security, cost attribution and optimization review of every workspace the agent identity can read (auto-discovered across subscriptions); one report for all, one subscription or named workspaces, with filters in the HTML.
tools:
- databricks-dependency-report
---

# Azure Databricks dependency and configuration review (fleet)

Use ONLY `databricks-dependency-report`. The operator must explicitly
select that one tool and this skill for `databricks-dependency-live`; no
inherited tools, shell, exec, generic Python, SQL execution tools, remediation
connectors or role-grant tools.

## Scope: every workspace the identity can read

There is no approved list to maintain. On every call the tool runs one fixed,
read-only Azure Resource Graph query and works with **every Azure Databricks
workspace the agent identity can read in its tenant**. The operator grants the
read-only roles once (ideally at the management group), so workspaces spread
over 1, 2 or 20+ subscriptions appear on their own. `APPROVED_WORKSPACES` in the
code only holds optional per-workspace overrides. Tool parameters cannot change
credentials, tenants, hosts, endpoints, SQL/KQL, filesystem paths, billing
scopes or resource IDs.

- If the fixed configuration still contains `<PLACEHOLDER>` values, the tool
  stops before any authentication or network call with `status="error"` and
  `error.code="configuration_required"` (`artifact_status="not_written"`).
- `no_workspaces_visible` means the identity cannot read any workspace yet:
  Reader is missing at the management group or subscriptions, or a new role
  assignment needs 5-10 minutes.
- A workspace the identity cannot read does not exist for the tool. If the user
  expects one that is missing, say that its subscription probably lacks the
  read role or that permissions need 5-10 minutes; never invent it.

Keep the two access planes strictly separate:

- **Plane 1, Azure Resource Manager** (`management.azure.com`): workspace
  configuration, network, managed resource group, Advisor and cost, from the
  Reader and Cost Management Reader roles.
- **Plane 2, inside the workspace** (`https://adb-<id>.<shard>.azuredatabricks.net`):
  clusters, pools, policies, jobs, pipelines, SQL warehouses, secret scopes and
  Unity Catalog. It works only where a Workspace Admin added the identity to the
  workspace and the workspace is reachable. Otherwise the workspace keeps its
  Azure-side review and is reported **without in-workspace access**, with its
  `workspace_access.status` and reason: `denied` (HTTP 401/403: identity not
  added or without permissions), `unreachable` (private network), `token_failed`,
  `disabled` or `not_collected`. Never present missing in-workspace data as
  empty or healthy.

### Cross-tenant workspaces

Auto-discovery runs only when `SRE_TENANT_ID == TARGET_TENANT_ID`. A workspace
in another tenant stays in `APPROVED_WORKSPACES` with a cross-tenant `auth_mode`;
`list_workspaces` then returns that configured list
(`discovery.reason="cross_tenant_configuration"`), which is configuration
metadata, not proof that a workspace exists, is reachable or authorizes reads.

- If `SRE_TENANT_ID != TARGET_TENANT_ID` and `auth_mode == "same_tenant_uami"`,
  the tool stops before authentication with
  `error.code="cross_tenant_configuration_required"`. A single-tenant SRE UAMI
  in Tenant A never automatically obtains Tenant B tokens or Databricks
  workspace permissions.
- Azure Lighthouse delegation projects ARM RBAC only; it does not grant
  Databricks Workspace or Unity Catalog access.
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

## Choosing the scope from the user's words

| The user asks for | Call |
|---|---|
| all workspaces, "the full report" | `operation="report"`, `workspace_names="all"` |
| every workspace of one subscription | `operation="report"`, `subscription="<display name or ID>"` |
| one workspace | `operation="report"`, `workspace_name="<exact name>"` |
| several workspaces (3, 8...) | `operation="report"`, `workspace_names="a,b,c"` (exact names, comma-separated, no spaces) |
| which workspaces exist, per subscription | `operation="list_workspaces"` (optionally `subscription`), `limit=100`, then `offset=next_offset` until it is null |

- Never guess names. If the user gives approximate names, call
  `list_workspaces` first (with `subscription` when known) and use only the
  returned `workspace_name` values. The same name in two subscriptions is
  returned with a prefix (first 8 characters of the subscription ID + `-`):
  use it as returned, or add `subscription`.
- `subscription` accepts the subscription display name (case-insensitive) or
  its ID and combines with `workspace_names="all"` or with names.
- One report covers up to 50 workspaces. Above that the tool returns
  `too_many_workspaces`: propose one report per subscription. Warn that a
  large report can take several minutes; do not start several large reports
  unless asked.
- A report is ONE set of files for the whole selection. The HTML opens on a
  fleet overview with **Subscription** and **Workspace** dropdowns (All by
  default), a search box, KPI cards, one row per workspace and the findings;
  choosing a workspace opens its detailed review. Tell the user they can filter
  inside the report.

## Report and four-file delivery

Make one complete call with `operation="report"` and the scope parameters
above; no local filter or paging combination is valid for a report.
**Immediately render all four provided files**: HTML (`report_url`), full
normalized JSON (`snapshot_url`), failed findings CSV (`findings_csv_url`) and
dependencies CSV (`dependencies_csv_url`).

- For `sharing_mode="native_ui"`, render the four unchanged `*_url` values as
  native Markdown links/file widgets in the same response; the tool derives
  them from the verified SRE runtime thread directory. Never invent or reuse a
  host/thread/sandbox prefix, never ask for manual publication and do not call
  another HTTP tool to check them. `http_verified=false` does not suppress
  these provided links; `artifact_status="written"` is not an HTTP download
  receipt.
- For `sharing_mode="local_files_only"`, expose the unchanged actual `*_path`
  values and state that `cwd` is outside the supported native runtime roots.
- Summarize a fleet report from its `fleet` block: workspaces selected,
  collected `ok` / `partial` / `error`, workspaces without in-workspace access
  (`without_workspace_access`) and why, findings by severity and
  `top_critical`, cost by currency (workspaces in `cost_unavailable` are
  unknown, not zero) and the links. A one-workspace report carries
  `workspace_access` instead. Each workspace keeps its own status; never borrow
  data from another workspace.
- On `status="error"`, report the sanitized `error.code`, `error.source_id` and
  `error.http_status` and stop (`all_workspaces_failed` lists the
  per-workspace codes). Do not claim completion, invent files, narrow scope
  silently, use ZIP/storage fallbacks or substitute a simulated report.

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
    `system.access.column_lineage`), which require executing SQL on a running
    SQL Warehouse, and per-run or per-user DBU billing (`system.billing.usage`)
    unless the operator enabled it with `system_tables_warehouse_id` (off by
    default).
  - Dynamic paths, JDBC strings or table names embedded inside notebook,
    Python or JAR code.
  - Effective data-plane packet flow, DNS resolution and storage/Key Vault
    firewall ACL evaluation.

Never fabricate table lineage from job or notebook names, and never start a
cluster or SQL Warehouse to fill gaps.

## Databricks costs (report section 6, `view="costs"`)

The cost section answers *where Databricks cost comes from and how to optimize
it*. It reads Azure Cost Management (amortized cost by default) for the
workspace resource and its managed resource group, grouped by the tags
Databricks puts on compute (`ClusterName`, `JobId`, `SqlEndpointId`,
`DatabricksInstancePoolId`, `Vendor`) and by the operator's allocation tags.

- Answer in this order: cost of the last closed month and its change, DBU vs
  infrastructure, the clusters, jobs, SQL warehouses and pools that concentrate
  it, the share no tag explains, then the top optimization signals.
- Every saving is an estimate with a `saving_kind` (`lower_bound`,
  `upper_bound` or `estimate`) and a documented formula; say so, never promise
  it, and never add savings across signals of the same object (only rows with
  `counted=true` add up). Signals without a saving show "No estimate".
- The unattributed share is cost without the `Vendor` tag: shared workspace
  services and serverless DBUs, which carry no Azure tags. Explain it; do not
  spread it across teams.
- The detailed analysis runs only in reports of up to 5 workspaces; larger
  reports keep each workspace's period cost. For one workspace's detail, ask
  for a report or query of that workspace.
- If `databricks_costs.status` is `denied`, say the identity needs Cost
  Management Reader (at the management group or on the subscription) and show
  no figures. Cost Management throttling (HTTP 429) leaves queries `throttled`
  or `skipped`: that cost is unknown and the section `partial`, never zero.
- Only when the user explicitly asks for a demo or a test without a workspace,
  call `operation="self_test"` with other defaults. Its four files come from a
  built-in workspace labelled `SIMULATED`; say so in the answer and never use it
  in place of a failed or unconfigured live run.

## Grounded questions

Use `operation="query"` for one workspace (`workspace_name`) or up to 5
(`workspace_names`), with `view` in `summary`, `workspace`, `compute`, `jobs`,
`pipelines`, `warehouses`, `unity_catalog`, `resources`, `findings`, `finops`,
`costs`, `coverage`, `actions` or `dependencies`. For questions about more
workspaces, use the report and its filters.

- Use `classification` (`OBSERVED`, `INFERRED`, `UNKNOWN`) with
  `view="dependencies"` to filter the dependency graph by provenance.
- Use `workload_name` for exact local filtering by cluster, job, pipeline,
  warehouse, Unity Catalog object or resource name.
- Use `area`, `level`, `severity` and `status` only where documented.
- Honor exact `total_matched`, `returned`, `has_more`, `next_offset`,
  `transport_capped` and fresh-collection disclosure under the 3,500-byte
  default-serialized response budget. A new call is a fresh collection, not a
  persistent cursor.
- Scores are local assessment indicators, never an official Microsoft WAF or
  Databricks grade. Always report evaluated, `not_evaluated` (`Not evaluated`)
  and `not_applicable` (`Not applicable`) counts alongside any score.

## Never do

No Azure RBAC or Unity Catalog grants, no multi-tenant consent or federation
policy creation, no cluster or SQL Warehouse start/stop, no job or pipeline
runs, no `/api/2.0/sql/statements` execution other than the fixed billing
statement the operator enabled with `system_tables_warehouse_id`, no
`/api/2.0/secrets/get` calls, no export of `spark_env_vars`, `spark_conf`, init
script bodies, notebook code or job parameter values, no savings beyond the
tool's documented estimates and no fabricated lineage.

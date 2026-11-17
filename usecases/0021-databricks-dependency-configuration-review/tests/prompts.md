# Test prompts

In a new chat, type `/agent`, select `databricks-dependency-live` and send one prompt at a time. Replace `<WORKSPACE_NAME>` with a name returned by `list_workspaces` and `<SUBSCRIPTION_NAME_OR_ID>` with a subscription display name or ID. Until the tenant and identity constants are set, report, query and `list_workspaces` calls return `configuration_required` and make no network call; `self_test` works without configuration.

## 1. One report for every workspace

```text
Generate the complete Azure Databricks dependency and configuration report for every workspace in every subscription (operation=report, workspace_names=all). Cover the dependency graph (OBSERVED native joins, explicit INFERRED URI targets and UNKNOWN runtime lineage blind spots), best practices, security, FinOps and optimization. Deliver the four files (HTML, full snapshot JSON, findings CSV and dependencies CSV) and tell me which workspaces have no in-workspace access and why. Do not start compute or modify any resource.
```

Tool call:

```json
{"operation": "report", "workspace_names": "all"}
```

**Expected:** One report call. The answer renders report_url, snapshot_url, findings_csv_url and dependencies_csv_url unchanged as file links and summarizes the workspaces collected, partial and failed, those without in-workspace access and the reason, the main findings and the cost. The HTML opens on a fleet overview with Subscription and Workspace filters; a workspace without in-workspace access keeps its Azure-side review and is never shown as empty or healthy. No cluster or SQL warehouse is started.

## 2. Which workspaces the agent can see

```text
List every Azure Databricks workspace you can see, grouped by subscription, with region and SKU (operation=list_workspaces, limit=100, following next_offset until it is null).
```

Tool call:

```json
{"operation": "list_workspaces", "limit": 100}
```

**Expected:** The workspaces returned by the fixed, read-only Azure Resource Graph discovery query (or the configured list for cross-tenant workspaces), with subscription names, paged with next_offset. It is inventory, not health; a workspace the identity cannot read is not listed.

## 3. One report for one subscription

```text
Generate the Azure Databricks report for every workspace of subscription <SUBSCRIPTION_NAME_OR_ID> (operation=report, subscription=<SUBSCRIPTION_NAME_OR_ID>) and summarize the most important findings per workspace.
```

Tool call:

```json
{"operation": "report", "subscription": "<SUBSCRIPTION_NAME_OR_ID>"}
```

**Expected:** One report for the workspaces of that subscription only. More than 50 workspaces returns too_many_workspaces; the detailed cost analysis runs only for reports of up to 5 workspaces.

## 4. Demo without a workspace

```text
Run operation=self_test to demonstrate the review with the built-in simulated workspace and deliver the four files, making clear that the data is SIMULATED.
```

Tool call:

```json
{"operation": "self_test"}
```

**Expected:** Four files labelled SIMULATED (banner, provenance chip and simulated-* file names), written without authentication or network.

## 5. Where the Databricks cost comes from

```text
Use query with view=costs for <WORKSPACE_NAME>. How much did Databricks cost in the last closed month compared with the previous one, how much is DBU and how much infrastructure, which clusters, jobs, SQL warehouses and pools concentrate the cost, what share no tag explains, and which changes would save the most? Say how each saving is estimated and do not add two savings for the same object.
```

Tool call:

```json
{"operation": "query", "view": "costs", "workspace_name": "<WORKSPACE_NAME>", "limit": 25}
```

**Expected:** Observed Cost Management rows with currency, the DBU and infrastructure split and the attribution by object and tag. Savings are estimates with their basis, counted once per object; nothing is invented when the cost source is denied.

## 6. Confirmed dependencies only

```text
Use query with view=dependencies and classification=OBSERVED for <WORKSPACE_NAME>. Which exact relationships are confirmed between job tasks, clusters, SQL warehouses, declarative pipelines, storage credentials, external locations and associated ARM resources? Give the join fields and the source of each edge.
```

Tool call:

```json
{"operation": "query", "view": "dependencies", "workspace_name": "<WORKSPACE_NAME>", "classification": "OBSERVED", "limit": 25}
```

**Expected:** Only OBSERVED edges with their join fields and sources, with exact paging totals. No lineage is inferred from job or notebook names.

## 7. Source coverage and in-workspace access

```text
Use query with view=coverage for <WORKSPACE_NAME> to show which ARM, workspace REST and Unity Catalog sources answered complete, partial, denied or not_configured, whether the agent has access inside the workspace, and what the Azure-side review still covers when it does not.
```

Tool call:

```json
{"operation": "query", "view": "coverage", "workspace_name": "<WORKSPACE_NAME>", "limit": 25}
```

**Expected:** Per-source receipts with HTTP status. Without in-workspace access the response gives the reason (denied with HTTP 401/403, unreachable, token_failed, disabled or not_collected) while the ARM review still runs; denied sources are never reported as healthy zeros.

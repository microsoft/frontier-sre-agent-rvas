# Test prompts

In a new chat, type `/agent`, select `databricks-dependency-live` and send one prompt at a time. Replace `<APPROVED_DATABRICKS_WORKSPACE_NAME>` with an approved workspace. Before the tool is configured, report and query prompts return `configuration_required` and make no network call; `list_workspaces` and `self_test` work without configuration.

## 1. Full dependency and configuration report

```text
Run the complete Azure Databricks dependency map and configuration review for <APPROVED_DATABRICKS_WORKSPACE_NAME> using operation=report. Cover the deep dependency graph (OBSERVED native joins, explicit INFERRED URI targets and UNKNOWN runtime lineage blind spots), best practices, security, FinOps and optimization across the five WAF pillars. Deliver all four generated files (HTML, full snapshot JSON, findings CSV and dependencies CSV) and disclose source coverage and limitations. Do not start compute or modify any resource.
```

Tool call:

```json
{"operation": "report", "workspace_name": "<APPROVED_DATABRICKS_WORKSPACE_NAME>"}
```

**Expected:** One report call. The answer renders report_url, snapshot_url, findings_csv_url and dependencies_csv_url unchanged as file links, states the auth mode, coverage and not-evaluated counts beside the local index, and starts no cluster or SQL warehouse.

## 2. List the configured workspaces

```text
List the Azure Databricks workspaces this tool is configured to review (operation=list_workspaces).
```

Tool call:

```json
{"operation": "list_workspaces"}
```

**Expected:** The configured allowlist, returned without authentication or network calls. It is a roster, not observed health.

## 3. Demo without a workspace

```text
Run operation=self_test to demonstrate the review with the built-in simulated workspace and deliver the four files, making clear that the data is SIMULATED.
```

Tool call:

```json
{"operation": "self_test"}
```

**Expected:** Four files labelled SIMULATED (banner, provenance chip and simulated-* file names), written without authentication or network.

## 4. Where the Databricks cost comes from

```text
Use query with view=costs for <APPROVED_DATABRICKS_WORKSPACE_NAME>. How much did Databricks cost in the last closed month compared with the previous one, how much is DBU and how much infrastructure, which clusters, jobs, SQL warehouses and pools concentrate the cost, what share no tag explains, and which changes would save the most? Say how each saving is estimated and do not add two savings for the same object.
```

Tool call:

```json
{"operation": "query", "view": "costs", "workspace_name": "<APPROVED_DATABRICKS_WORKSPACE_NAME>", "limit": 25}
```

**Expected:** Observed Cost Management rows with currency, the DBU and infrastructure split and the attribution by object and tag. Savings are estimates with their basis, counted once per object; nothing is invented when the cost source is denied.

## 5. Confirmed dependencies only

```text
Use query with view=dependencies and classification=OBSERVED for <APPROVED_DATABRICKS_WORKSPACE_NAME>. Which exact relationships are confirmed between job tasks, clusters, SQL warehouses, declarative pipelines, storage credentials, external locations and associated ARM resources? Give the join fields and the source of each edge.
```

Tool call:

```json
{"operation": "query", "view": "dependencies", "workspace_name": "<APPROVED_DATABRICKS_WORKSPACE_NAME>", "classification": "OBSERVED", "limit": 25}
```

**Expected:** Only OBSERVED edges with their join fields and sources, with exact paging totals. No lineage is inferred from job or notebook names.

## 6. Source coverage

```text
Use query with view=coverage to show which ARM, workspace REST and Unity Catalog sources answered complete, partial, denied or not_configured, including the configured cross-tenant authentication mode.
```

Tool call:

```json
{"operation": "query", "view": "coverage", "limit": 25}
```

**Expected:** Per-source receipts with HTTP status. ARM shows denied (HTTP 403) until the resource-group Reader role is in place; denied sources are never reported as healthy zeros.

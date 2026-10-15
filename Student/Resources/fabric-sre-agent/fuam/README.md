# Setup guide — FUAM version
 
[← Back to overview](../README.md)

> **Workshop ownership:** The coach deploys FUAM once, schedules refresh, and
> shares its Lakehouse/SQL endpoint and approved monitored items with the
> audience and each team agent UAMI. Backend deployment, tenant settings, and
> access grants below are **coach preparation**, not student tasks. Students use
> their infrastructure-provisioned agent and shared connection identifiers for
> agent configuration; every author needs **SRE Agent Administrator** on that
> agent. Students do not need Fabric Administrator or capacity-admin rights.
 
An Azure SRE Agent that answers cost, consumption, RCA and optimization questions about Microsoft Fabric workloads, for example:
 
- *"How much did workspace A cost this week vs last week?"*
- *"How much does pipeline B cost, including its notebooks?"*
- *"Why did notebook C fail yesterday, and how can I reduce its CU consumption?"*
CU consumption comes from **FUAM** (day grain). Prices come from the **Azure Retail Prices API**. Per-execution notebook diagnostics come from the **Fabric Spark monitoring APIs**. Fabric know-how comes **live** from the `microsoft/skills-for-fabric` repository.
 
---
 
## Architecture
 
| Component | Where it's configured | Purpose |
|---|---|---|
| FUAM Lakehouse | Fabric workspace | CU per item, operation and day; capacity timepoints; inventory |
| `sqlendpoint-operations-mcp` | Builder → Connectors | Runs T-SQL against the FUAM Lakehouse SQL analytics endpoint |
| `fabric-mcp` | Builder → Connectors | Workspaces, items, job instances, item definitions, Spark monitoring APIs |
| `skills-for-fabric` repo | Builder → Code Access | Live source of the official Fabric skills |
| `fabric-skills-router` skill | Builder → Skill builder | Forces the agent to read the right skill from the repo before any Fabric task |
| `get_fabric_cu_price` Python tool | Builder → Agent Canvas → Tools | €/CU-hour from the Azure Retail Prices API |
| `prices.azure.com` | Settings → Workspace configuration | Outbound access for the pricing tool |
| Agent instructions | Capabilities → Custom Instructions | [`agent-instructions.md`](agent-instructions.md) |
 
**Identity:** the agent's user-assigned managed identity (UAMI) is used for Fabric access.
 
---
 
## Prerequisites
 
- An Azure SRE Agent in **Running** state, and the **SRE Agent Administrator** role on it.
- **Coach only:** Fabric Administrator and capacity admin rights for setup.
- The **Microsoft Fabric Capacity Metrics app** installed. FUAM reads CU data from it.
- Files from this repository:
  - [`fuam/agent-instructions.md`](agent-instructions.md): agent instructions
  - [`skills/fabric-skills-router/SKILL.md`](../skills/fabric-skills-router/SKILL.md): Fabric skills router
  - [`tools/get_fabric_cu_price.py`](../tools/get_fabric_cu_price.py): pricing tool
  - [`demo/perf_demo_inefficient.ipynb`](../demo/perf_demo_inefficient.ipynb): optional demo notebook
---
 
## Step 0 — Collect identifiers
 
| # | Value | Where to find it |
|---|---|---|
| 0.1 | UAMI name, **Object (principal) ID**, **Client ID** | Agent portal → **Settings → Azure settings → Go to Identity**, or the `id-*` resource in the agent's resource group |
| 0.2 | FUAM workspace name and ID | Portal URL `…/groups/<workspaceId>/…` |
| 0.3 | FUAM_Lakehouse ID | Portal URL `…/lakehouses/<lakehouseId>` |
| 0.4 | FUAM_Lakehouse SQL endpoint server | Lakehouse → **SQL analytics endpoint → Settings → SQL connection string** |
 
---
 
## Step 1 — Deploy FUAM
 
Follow the official guide: [How to deploy FUAM](https://github.com/microsoft/fabric-toolbox/blob/main/monitoring/fabric-unified-admin-monitoring/how-to/How_to_deploy_FUAM.md).
 
Points the guide doesn't make explicit:
 
1. **The service principal has no API permissions.** Access comes only from tenant settings plus a security group. Leave the app registration with no admin-consent permissions.
2. **Enable both admin API tenant settings** for the FUAM security group:
   - **Service principals can access read-only admin APIs** (Power BI admin APIs, `v1.0/myorg/admin/…`)
   - **Service principals can access admin APIs used for updates** (Fabric admin APIs, `/v1/admin/…`)
3. **Allow up to 15 minutes** for tenant-setting and group changes to take effect.
4. **Verify the SP before running the pipeline.** Both calls must return `200` (see [Troubleshooting](#troubleshooting)).
5. **Schedule** `Load_FUAM_Data_E2E` 4–6 times a day, away from heavy ETL windows.
✅ `SELECT TOP 5 * FROM dbo.capacity_metrics_by_item_by_operation_by_day` returns rows.
 
---
 
## Step 2 — Grant the UAMI access to Fabric
 
| # | Where | Grant |
|---|---|---|
| 2.1 | Admin portal → Tenant settings → **Service principals can call Fabric public APIs** | Enabled, for the entire organization or a group containing the UAMI |
| 2.2 | **FUAM workspace** → Manage access | UAMI as **Viewer**: read access to the SQL analytics endpoint |
| 2.3 | **Each monitored workspace** → Manage access | UAMI as **Viewer**: job instances, Spark monitoring APIs, item definitions |
 
✅ The UAMI appears in Manage access on the FUAM workspace and on each monitored workspace.
 
---
 
## Step 3 — Allow the pricing domain
 
Agent portal → **Settings → Workspace configuration → Additional hosts** → add:
 
```
prices.azure.com
```
 
The `get_fabric_cu_price` tool calls `https://prices.azure.com/api/retail/prices`. If the host isn't allowed, every cost answer fails at the rate lookup.
 
✅ The host is listed under Additional hosts.
 
---
 
## Step 4 — Code access
 
Agent portal → **Builder → Code Access → GitHub → Add repository**:
 
| Field | Value |
|---|---|
| Repository | `https://github.com/microsoft/skills-for-fabric` |
| Connection | OAuth (GitHub sign-in) |
 
This repository is the **live source** for the `fabric-skills-router` skill (Step 7). The agent reads the skills from here on every Fabric request, so updates published upstream are picked up without reinstalling anything.
 
**Optional:** to let the agent review notebook code during optimization, add the repository your Fabric workspaces are Git-synced to (GitHub, or Azure DevOps with managed identity). Without it, the agent reads notebook code through the Fabric item-definition API.
 
✅ `skills-for-fabric` shows a green **Connection** status and a recent **Last synced** time.
 
---
 
## Step 5 — MCP connectors
 
Agent portal → **Builder → Connectors → Add connector → MCP server**. Two connectors are needed:
 
| Connector name | Required | Purpose | Tools to enable |
|---|---|---|---|
| `fabric-mcp` | ✅ | Workspaces, items, job instances, item definitions, Spark monitoring | Read operations only. Deselect create, update and delete tools |
| `sqlendpoint-operations-mcp` | ✅ | T-SQL against the FUAM Lakehouse SQL analytics endpoint | `execute_query` |
---
**`sqlendpoint-operations-mcp` definition**, as published in the skills repo's `.mcp.json`:
 
 
| Setting | Value |
|---|---|
| Transport | Streamable HTTP |
| URL | `https://api.fabric.microsoft.com/v1/mcp/dataPlane/sqlEndpoint` |
| Tools | `execute_query` |
 
**`fabric-mcp`:** the Fabric MCP server for control-plane and item operations. Configure it with the transport and authentication that reach **Connected** in your agent:
- Remote: `https://api.fabric.microsoft.com/v1/mcp/core`
- Local (stdio, managed identity): `npx -y @microsoft/fabric-mcp@latest server start --mode all`
Not used: **FabricIQ MCP**. It supports delegated user sign-in only, so it can't run under the UAMI.
 
✅ Both connectors show **Connected**. Ask the agent *"List the Fabric workspaces you can see"*, then *"Run `SELECT TOP 5 * FROM dbo.capacity_metrics_by_item_by_operation_by_day` on the FUAM_Lakehouse SQL endpoint"*. Both return results.
 
---
 
## Step 6 — Pricing tool
 
Agent portal → **Builder → Agent Canvas → Create → Tool → Python**.
 
| Field | Value |
|---|---|
| Name | `get_fabric_cu_price` |
| Description | Returns Microsoft Fabric €/CU-hour (PAYG and 1-year reservation) for an Azure region from the Azure Retail Prices API. The only allowed source for Fabric prices. |
| Identity | None. The Retail Prices API is public and unauthenticated |
| Code | Paste the contents of [`tools/get_fabric_cu_price.py`](../tools/get_fabric_cu_price.py) |
 
✅ Test in the playground with `region = "West Europe"`. It returns `payg_per_cu_hour`, and `reservation_1y_per_cu_hour` ≈ `reservation_1y_per_cu_year / 8760`.
 
---
 
## Step 7 — Skill: `fabric-skills-router`
 
Agent portal → **Builder → Skill builder → Create skill**.
 
| Field | Value |
|---|---|
| Name | `fabric-skills-router` |
| Tools | None. The skill reads from the Code Access repository (Step 4) |
| Additional files | None |
| SKILL.md | Paste the contents of [`skills/fabric-skills-router/SKILL.md`](../skills/fabric-skills-router/SKILL.md) |
 
The router reads the official skills **live** from the repository, so upstream updates are picked up without changing the skill. Checked against the repository at commit `bc42aaf`: every folder in its list exists. Folders not in the list (`azmon-mirroredcatalogs-operations-cli`, `eventschemaset-cli`, `project-osmos`, `search-consumption-cli`) are reached through the "Not listed" fallback.
 
✅ Ask *"Which skill would you use to analyse a slow Spark notebook?"* The agent loads `fabric-skills-router`, reads `spark-cli/SKILL.md` from the repo, and names the files it read.
 
---
 
## Step 8 — Agent instructions
 
1. Open [`agent-instructions.md`](agent-instructions.md) and fill in **§3.0** with the Step 0 values: workspace name and ID, Lakehouse ID, SQL endpoint server.
2. Agent portal → **Capabilities → Custom Instructions**.
3. Paste the **entire contents** of the file, then save.
Custom Instructions apply to the default agent in every thread, so questions work without `/agent`. If the field truncates the text, keep §1–§6 and §8–§10 in Custom Instructions and move the §7 query templates into a skill as supporting files.
 
✅ Ask *"What can you help me with?"* The answer describes Fabric cost, RCA and notebook optimization.
 
---
 
## Step 9 — Acceptance tests
 
Run each in a new thread.
 
| # | Prompt | Expected |
|---|---|---|
| 9.1 | "How much did workspace <A> cost this week vs last week?" | Asks for the pricing model or defaults to PAYG. Rate fetched with `get_fabric_cu_price`. Explicit dates. Today flagged as partial. Ends with the **CALCULATION** block and its one-sentence explanation |
| 9.2 | "Break down workspace <A> by item for last week." | Item names resolved. Deleted items labelled, not NULL |
| 9.3 | "How many CUs did notebook <C> use in its latest run?" | Precision label (exact or average per run), following the `OperationCount` rule |
| 9.4 | "How much does pipeline <B> cost, including its notebooks?" | Pipeline's own CU plus children, each labelled exact or shared. Total marked upper bound if anything is shared |
| 9.5 | "How can I reduce notebook <C>'s CU consumption?" | 14-day trend, code reviewed, the most expensive execution drilled into (stages, skew, spill, executor allocation), recommendations tied to evidence with € impact |
| 9.6 | "Why was <item> slow on <date>?" | Item counts, job runs and capacity timepoints correlated. For notebooks, the execution compared with a normal one |
| 9.7 | "How much did workspace <nonexistent> cost?" | Nothing found, with likely reasons. No invented numbers |
| 9.8 | **Validation.** "Derive the CU of notebook <X>'s execution on <day>" (a day where FUAM shows `OperationCount = 1`, not an HC run) | Derived CU-seconds within ~10% of FUAM's `TotalCUs`. If it passes, remove the "not yet validated" wording from §6.4 step 4 of the instructions. If it fails, limit §6.4 to performance analysis |
| 9.9 | "How many CUs did notebook <C>'s 14:00 run use?" (several runs that day) | Derived per-execution CU with its label and the vCore-seconds lines in the calculation block, cross-checked against FUAM's daily total |
| 9.10 | "Why did pipeline <B> fail on <date>?" (a child notebook failed) | Failing child notebook identified, driver and executor logs read, error reported |
 
Every answer about Fabric should state which skill file(s) it read (Step 7).
 
---
 
## Demo scenario (optional)
 
[`demo/perf_demo_inefficient.ipynb`](../demo/perf_demo_inefficient.ipynb) is a deliberately inefficient notebook: broadcast disabled, a fan-out join hidden by `dropDuplicates`, heavy key skew, a window over the skewed key, AQE off, too many shuffle partitions, and the same pipeline computed twice. It runs in a few minutes.
 
1. Import it into a monitored workspace and attach a Lakehouse (not the FUAM one). Use a **standard** session, not high-concurrency.
2. Run it once, then stop the session.
3. Wait **15–20 minutes** after the session ends, then refresh the **Capacity Metrics** semantic model manually. New items only appear after a refresh.
4. Confirm the notebook shows non-zero CU in the app, then run `Load_FUAM_Data_E2E`.
5. Ask the agent for the cost of the run, then for optimization recommendations.
Afterwards, drop the five `perf_demo_*` tables.
 
---
 
## Troubleshooting
 
**Verify the FUAM service principal (run in a Fabric notebook)**
 
```python
import requests
tenant, client_id, secret = "<tenant-id>", "<client-id>", "<secret-value>"
 
def token(scope):
    r = requests.post(f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
        data={"grant_type": "client_credentials", "client_id": client_id,
              "client_secret": secret, "scope": scope})
    r.raise_for_status(); return r.json()["access_token"]
 
pbi = token("https://analysis.windows.net/powerbi/api/.default")
fab = token("https://api.fabric.microsoft.com/.default")
for name, url, t in [("PBI", "https://api.powerbi.com/v1.0/myorg/admin/groups?$top=1", pbi),
                     ("FAB", "https://api.fabric.microsoft.com/v1/admin/workspaces", fab)]:
    r = requests.get(url, headers={"Authorization": f"Bearer {t}"})
    print(name, r.status_code, r.text[:200])
```
 
| Symptom | Cause | Fix |
|---|---|---|
| `PBI 401` with an empty body | SP not recognised for the read-only admin API | Check the SP is a **direct member** of the group named in **Service principals can access read-only admin APIs**. Turn the setting off and on again, then wait about 15 minutes |
| `FAB 403 InsufficientScopes` | **Admin APIs used for updates** setting missing for the group | Enable it for the same group |
| FUAM `01_Transfer_Incremental_Inventory_Unit` fails with `'NoneType' object has no attribute 'json'` | The preceding admin API call failed. Check the cell output for the status code | 401: as above. 429: wait an hour before rerunning |
| The same SP alternates between 200 and 401 with no config change | Service-side | Open a support ticket with the `RequestId`s and UTC timestamps. As a temporary workaround, run the inventory module as a Fabric admin user |
| A new notebook shows **0 CU** in the Capacity Metrics app | Usage not ingested yet (10–15 minutes), or the semantic model was refreshed too early | Refresh the semantic model again 15–20 minutes after the session ended. Check the app's capacity and date filters. If **Autoscale Billing for Spark** is enabled on the capacity, Spark CU appears on the *Autoscale compute for Spark* page instead |
| A query filtered by GUID returns nothing | FUAM stores GUIDs in uppercase, and the SQL endpoint is case-sensitive | Resolve IDs from names inside the query, or compare `UPPER(col) = UPPER(TRIM('<guid>'))` |
| Item names show as NULL | The item was deleted, so it's no longer in `active_items` | The instructions (§7.0) fall back to `active_items_history`, then `activities`, then label the item *"deleted / name unknown"* |
| Every cost answer fails at the rate lookup | `prices.azure.com` not allowed | Step 3 |
 
---
 
## Known limits
 
- **Day grain.** FUAM has no per-execution CU. Per-execution CU is **derived** for notebooks from Spark executor allocation (§6.4 of the instructions). Pipelines and other items have exact per-execution CU only when they ran once that day.
- **List prices.** Rates are Azure retail prices. Negotiated EA or MCA discounts aren't reflected.
- **Standalone-equivalent cost.** Figures are CU × €/CU-hour, not an allocation of the capacity invoice.
- **Non-billable operations.** FUAM has no billable flag per item, so preview operations may be included.
- **Storage.** OneLake storage cost is excluded.
 
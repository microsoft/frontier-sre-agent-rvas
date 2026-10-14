# Setup guide — capacity events version
 
[← Back to overview](../README.md)
 
An Azure SRE Agent that answers cost, consumption, RCA and optimization questions about Microsoft Fabric workloads, at **per-operation** granularity. Every execution of every item, pipelines included, has its own exact CU figure.
 
CU consumption comes from **Fabric capacity operation events**, streamed into an Eventhouse. Prices come from the **Azure Retail Prices API**. Notebook diagnostics come from the **Fabric Spark monitoring APIs**. Fabric know-how comes **live** from the `microsoft/skills-for-fabric` repository.
 
---
 
## Architecture
 
| Component | Where it's configured | Purpose |
|---|---|---|
| Capacity operation events → Eventstream → Eventhouse (`OperationsTable`) | Fabric Real-Time hub | One row per operation that consumed CU |
| KQL over the Eventhouse query URI | Agent runs `az rest` with a Kusto token | Queries `OperationsTable` |
| `sqlendpoint-operations-mcp` | Builder → Connectors | Query Insights for Warehouse and SQL endpoint correlation |
| `fabric-mcp` | Builder → Connectors | Capacities, items, job instances, item definitions, Spark monitoring APIs |
| `skills-for-fabric` repo | Builder → Code Access | Live source of the official Fabric skills |
| `fabric-skills-router` skill | Builder → Skill builder | Forces the agent to read the right skill from the repo before any Fabric task |
| `get_fabric_cu_price` Python tool | Builder → Agent Canvas → Tools | €/CU-hour from the Azure Retail Prices API |
| `prices.azure.com`, `*.kusto.fabric.microsoft.com` | Settings → Workspace configuration | Outbound access for pricing and KQL |
| Agent instructions | Capabilities → Custom Instructions | [`agent-instructions.md`](agent-instructions.md) |
 
**Identity:** the agent's user-assigned managed identity (UAMI) is used for Fabric and Kusto access.
 
---
 
## Prerequisites
 
- An Azure SRE Agent in **Running** state, and the **SRE Agent Administrator** role on it.
- **Capacity admin** on every capacity you want to monitor. Subscribing to its operation events requires it.
- A Fabric workspace to host the Eventstream and Eventhouse (see Step 1 for sizing).
- Files from this repository:
  - [`capacity-events/agent-instructions.md`](agent-instructions.md): agent instructions
  - [`skills/fabric-skills-router/SKILL.md`](../skills/fabric-skills-router/SKILL.md): Fabric skills router
  - [`tools/get_fabric_cu_price.py`](../tools/get_fabric_cu_price.py): pricing tool
  - [`demo/perf_demo_inefficient.ipynb`](../demo/perf_demo_inefficient.ipynb): optional demo notebook
---
 
## Step 0 — Collect identifiers
 
| # | Value | Where to find it |
|---|---|---|
| 0.1 | UAMI name, **Object (principal) ID**, **Client ID** | Agent portal → **Settings → Azure settings → Go to Identity**, or the `id-*` resource in the agent's resource group |
| 0.2 | Tenant ID | Entra admin center → Overview |
| 0.3 | Monitoring workspace name and ID | Portal URL `…/groups/<workspaceId>/…` (after Step 1) |
| 0.4 | Eventhouse name, KQL database name, **Query URI** | Eventhouse → **Eventhouse details → Query URI** (after Step 1). Format: `https://<id>.kusto.fabric.microsoft.com` |
 
---
 
## Step 1 — Stream capacity operation events into an Eventhouse
 
### 1.1 Choose where the monitoring items run
 
The Eventstream and Eventhouse are always active, because every operation on a monitored capacity emits an event. Their CU is billed to the capacity that hosts their workspace:
 
| Option | When |
|---|---|
| Workspace on an **existing production capacity** | Production is F32 or larger, so the monitoring load is a few percent |
| Workspace on a **dedicated capacity** | You want monitoring isolated. Start at **F4**. On F2 the Eventstream alone uses about half the capacity, and a throttled Eventhouse can lose ingested data |
 
Don't pause the monitoring capacity. Event subscriptions retain undelivered events for 24 hours at most.
 
### 1.2 Create the Eventhouse
 
1. In the monitoring workspace, create an **Eventhouse**. A KQL database with the same name is created with it.
2. Set a retention policy that covers the history you want, for example 90 days:
```kql
   .alter-merge table OperationsTable policy retention softdelete = 90d
```
   (Run this after the table exists, which is after Step 1.3.)
 
### 1.3 Connect the events
 
For **each capacity** you want to monitor:
 
1. **Real-Time hub → Add data → Fabric events → Capacity operation events → Connect**.
2. **Event scope:** the capacity to monitor. You must be its capacity admin.
3. **Stream details:** the monitoring workspace, and an Eventstream name (create it once, then add each further capacity as an extra source to the same Eventstream).
4. Add a destination: **Eventhouse → the KQL database → table `OperationsTable`**.
5. Keep the event payload available in a `Data` column (dynamic), or flatten it into columns. The agent reads the schema at runtime and adapts to either.
✅ After running any workload on the monitored capacity, `OperationsTable | take 10` returns rows within a few minutes.
 
> The capacity operation events source is in **preview**. The subscription runs under its **owner's** permissions. If the owner loses capacity admin, the subscription pauses.
 
---
 
## Step 2 — Grant the UAMI access to Fabric
 
| # | Where | Grant |
|---|---|---|
| 2.1 | Admin portal → Tenant settings → **Service principals can call Fabric public APIs** | Enabled, for the entire organization or a group containing the UAMI |
| 2.2 | **Monitoring workspace** → Manage access | UAMI as **Viewer**: read access to the KQL database |
| 2.3 | **Each monitored workspace** → Manage access | UAMI as **Viewer**: job instances, Spark monitoring APIs, item definitions, SQL endpoints for Query Insights |
 
If KQL queries return 401 or 403 despite 2.2, grant database-level access explicitly in the KQL database:
 
```kql
.add database ['<KQL database>'] viewers ('aadapp=<UAMI client ID>;<tenant ID>')
```
 
✅ The UAMI appears in Manage access on the monitoring workspace and on each monitored workspace.
 
---
 
## Step 3 — Allow the outbound domains
 
Agent portal → **Settings → Workspace configuration → Additional hosts** → add both:
 
```
prices.azure.com
*.kusto.fabric.microsoft.com
```
 
| Host | Needed for |
|---|---|
| `prices.azure.com` | The `get_fabric_cu_price` tool (Azure Retail Prices API) |
| `*.kusto.fabric.microsoft.com` | KQL queries against the Eventhouse query URI |
 
Without the second host, every consumption question fails at the first KQL query.
 
✅ Both hosts are listed under Additional hosts.
 
---
 
## Step 4 — Code access
 
Agent portal → **Builder → Code Access → GitHub → Add repository**:
 
| Field | Value |
|---|---|
| Repository | `https://github.com/microsoft/skills-for-fabric` |
| Connection | OAuth (GitHub sign-in) |
 
This repository is the **live source** for the `fabric-skills-router` skill (Step 7).
 
**Optional:** to let the agent review notebook code during optimization, add the repository your Fabric workspaces are Git-synced to. Without it, the agent reads notebook code through the Fabric item-definition API.
 
✅ `skills-for-fabric` shows a green **Connection** status and a recent **Last synced** time.
 
---
 
## Step 5 — MCP connectors
 
Agent portal → **Builder → Connectors → Add connector → MCP server**:
 
| Connector name | Required | Purpose | Tools to enable |
|---|---|---|---|
| `fabric-mcp` | ✅ | Capacities, items, job instances, item definitions, Spark monitoring | Read operations only. Deselect create, update and delete tools |
| `sqlendpoint-operations-mcp` | ✅ | Query Insights against Warehouse and SQL endpoints (CU-spike correlation) | `execute_query` |
| `powerbi-modeling-mcp` | ❌ | Not used | — |
| FabricIQ | ❌ | Not used. Delegated user sign-in only, so it can't run under the UAMI | — |
 
**`sqlendpoint-operations-mcp`**, as published in the skills repo's `.mcp.json`:
 
| Setting | Value |
|---|---|
| Transport | Streamable HTTP |
| URL | `https://api.fabric.microsoft.com/v1/mcp/dataPlane/sqlEndpoint` |
| Tools | `execute_query` |
 
**`fabric-mcp`:** configure it with the transport and authentication that reach **Connected** in your agent, the same as in the [FUAM version](../fuam/README.md#step-5--mcp-connectors).
 
KQL doesn't need a connector. The agent calls the Eventhouse query URI with `az rest` and a Kusto token (Step 3 allows the host).
 
✅ Both connectors show **Connected**. Ask the agent *"List the Fabric capacities you can see."* It returns the monitored capacities.
 
---
 
## Step 6 — Pricing tool
 
Agent portal → **Builder → Agent Canvas → Create → Tool → Python**.
 
| Field | Value |
|---|---|
| Name | `get_fabric_cu_price` |
| Description | Returns Microsoft Fabric €/CU-hour (PAYG and 1-year reservation) for an Azure region from the Azure Retail Prices API. The only allowed source for Fabric prices. |
| Identity | None. The Retail Prices API is public and unauthenticated |
| Code | Paste the contents of [`tools/get_fabric_cu_price.py`](../tools/get_fabric_cu_price.py) |
 
If you already deployed the FUAM version on the same agent, the tool exists. Skip this step.
 
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
 
If you already deployed the FUAM version on the same agent, the skill exists. Skip this step.
 
This version relies mostly on `eventhouse-cli` (KQL), `spark-cli` (Spark diagnostics) and `sqldw-cli` (Query Insights), all reached through the router.
 
✅ Ask *"Which skill would you use to query an Eventhouse?"* The agent loads `fabric-skills-router`, reads `eventhouse-cli/SKILL.md` from the repo, and names the files it read.
 
---
 
## Step 8 — Agent instructions
 
1. Open [`agent-instructions.md`](agent-instructions.md) and fill in **§3.0** with the Step 0 values: monitoring workspace name and ID, Eventhouse, KQL database, query URI.
2. Agent portal → **Capabilities → Custom Instructions**.
3. Paste the **entire contents** of the file, then save.
One agent runs **one version**. Custom Instructions apply to the whole agent, so don't paste both versions' instructions into the same agent. To run both side by side, use two agents, or put one version in a custom agent (Agent Canvas → Create → Custom Agent).
 
✅ Ask *"What can you help me with?"* The answer describes Fabric cost, per-execution consumption, RCA and optimization.
 
---
 
## Step 9 — Acceptance tests
 
Run each in a new thread.
 
| # | Prompt | Expected |
|---|---|---|
| 9.1 | "Show me the schema of the capacity operations table." | Runs `getschema` and `take 1`, and maps the fields it found to the documented properties (`capacityUnitMs`, `operationStartTime`, `itemName`, …) with their actual names and casing |
| 9.2 | "How much did workspace <A> cost this week vs last week?" | Opening statement (SKU, capacity, region, available CU-hours, rate). Table with TOTAL row. Periods in UTC on `operationStartTime`. Preview operations excluded. Ends with the **CALCULATION** block |
| 9.3 | "How many CUs did notebook <C>'s latest run use?" | One operation, labelled **exact**, with its `operationStartTime`, status and duration |
| 9.4 | "How much did the last run of pipeline <B> cost, including its notebooks?" | Run window from job instances. Pipeline's own CU plus child operations inside the window, each labelled exact or ambiguous |
| 9.5 | "How can I reduce notebook <C>'s CU consumption?" | 14-day trend, the most expensive execution drilled into (stages, skew, spill, executor allocation), recommendations tied to evidence with € impact |
| 9.6 | "Why was <item> slow / throttled at <time>?" | The execution, concurrent heavy operations on the capacity, throttled operations, and for notebooks the Spark execution compared with a normal one |
| 9.7 | "Which SQL queries drove the warehouse <W> spike yesterday?" | Query Insights correlation via `sqldw-cli`: query text, login, CPU and elapsed time, data scanned |
| 9.8 | "How much did workspace <nonexistent> cost?" | Nothing found, with likely reasons. No invented numbers |
 
✅ All eight behave as expected. Then validate one figure by hand: for one item and day, compare the agent's CU-seconds with the Capacity Metrics app's **CU (s)**.
 
---
 
## Demo scenario (optional)
 
[`demo/perf_demo_inefficient.ipynb`](../demo/perf_demo_inefficient.ipynb) is a deliberately inefficient notebook: broadcast disabled, a fan-out join hidden by `dropDuplicates`, heavy key skew, a window over the skewed key, AQE off, too many shuffle partitions, and the same pipeline computed twice. It runs in a few minutes.
 
1. Import it into a workspace on a **monitored** capacity and attach a Lakehouse. Use a **standard** session, not high-concurrency.
2. Run it once, then stop the session.
3. Wait a few minutes. The operation event arrives in `OperationsTable` after the operation completes. No Capacity Metrics refresh is needed.
4. Ask the agent for the cost of that run, then for optimization recommendations.
Afterwards, drop the five `perf_demo_*` tables.
 
---
 
## Troubleshooting
 
| Symptom | Cause | Fix |
|---|---|---|
| KQL calls fail with a network or connection error | `*.kusto.fabric.microsoft.com` not allowed | Step 3 |
| KQL calls return 401 or 403 | UAMI has no read access to the KQL database | Step 2.2, or the `.add database … viewers` command |
| `OperationsTable` has no new rows | The event subscription is paused (its owner lost capacity admin), or the monitoring capacity is paused or throttled | Real-Time hub → check the subscription status. Restore the owner's capacity admin role or reassign the subscription. Check the monitoring capacity's utilisation |
| Item, workspace or CU columns come back empty | KQL property names are case-sensitive, and the query used different casing from the stored payload | Acceptance test 9.1. The instructions make the agent check the schema first |
| Agent's totals are higher than the Capacity Metrics app | Duplicate events, preview operations included, or filtering on ingestion time | The instructions deduplicate, exclude `releaseType == "Preview"`, and filter on `operationStartTime`. Check the agent followed them |
| History stops at a recent date | Events exist only from when the subscription was created, and only for the retention period | Step 1.2 retention policy. Older history isn't recoverable from events |
| Every cost answer fails at the rate lookup | `prices.azure.com` not allowed | Step 3 |
 
---
 
## Known limits
 
- **History** starts when the event subscription was created.
- **Standing cost:** the Eventstream and Eventhouse run continuously and consume CU on their host capacity.
- **Preview source:** the capacity operation events source is in preview.
- **Capacity utilisation %:** operation events don't carry the smoothed utilisation. The agent uses throttling and concurrent load for RCA, unless capacity overview (summary) events are also streamed.
- **List prices.** Rates are Azure retail prices. Negotiated EA or MCA discounts aren't reflected.
- **Standalone-equivalent cost.** Figures are CU × €/CU-hour, not an allocation of the capacity invoice.
- **Storage.** OneLake storage cost is excluded.
 
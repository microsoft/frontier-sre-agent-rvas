<div align="center">
  <img src="./FabricSRE.png" alt="Rayfin" height="120" />
  <h1 style="font-family: 'Segoe UI', Arial, sans-serif;">
    fabric-finops-rca-sre-agent
  </h1>
</div>
 
An **Azure SRE Agent** for Microsoft Fabric FinOps and root-cause analysis. Ask it questions in plain language and get answers backed by data, with the calculation shown:
 
- *"How much did workspace A cost this week vs last week?"*
- *"How much does pipeline B cost, including the notebooks it runs?"*
- *"Why did notebook C fail yesterday?"*
- *"How can I reduce notebook C's capacity-unit consumption?"*
Costs are **standalone-equivalent**: CUs consumed × the regional €/CU-hour from the Azure Retail Prices API. They answer "what did this work cost if billed per CU", not "how is the capacity invoice split".

## Workshop ownership

The coach sets up **both FUAM and Capacity Events once** and shares the relevant
items with audience users/groups and team agent identities using read access.
Students use the handed-over identifiers and the agent-configuration sections
of the guides; they do not deploy or modify shared telemetry infrastructure.
The infrastructure deliverable provisions the Fabric capacity and team SRE
Agents. Every participant configuring an agent requires **SRE Agent
Administrator** on that agent; the agent UAMI's Fabric permissions stay read-only.

## Agent connection and configuration reference

Use this reference in Challenges 02, 05, and 06; these are not additional
challenges. The new portal navigation shown in the workshop is **Build + setup**:
**Context > Code access** and **Extensions > Connectors / Skill builder /
Custom instructions**. Older screens call these **Builder > Code Access /
Connectors / Skill builder** and **Capabilities > Custom Instructions**.

### Workspace outbound hosts

In the **SRE Agent** portal (not Fabric workspace settings), open
**Settings > Workspace configuration > Additional hosts**, add the applicable
host entries below, and save. Enter host patterns, not URLs or URL paths.

| Host entry | Required use |
|---|---|
| `prices.azure.com` | Both backends: public Azure Retail Prices API used by `get_fabric_cu_price` |
| `*.database.fabric.microsoft.com` | Workshop Fabric database endpoint access; allow this pattern for both configurations and test the actual endpoint handed over by the coach |
| `*.kusto.fabric.microsoft.com` | Capacity Events: Eventhouse query URI; consumption queries cannot reach the events without this entry |

These patterns do not replace identity/data permissions or endpoint-specific
network rules. SQL analytics endpoints can use
`<id>.datawarehouse.fabric.microsoft.com`; that name is **not** matched by
`*.database.fabric.microsoft.com`. If that is the handed-over server, allow its
actual hostname (or the approved `*.datawarehouse.fabric.microsoft.com` pattern)
as well. Do not change the server name to make it fit an allowlist.
Test pricing, SQL, and (for events) KQL independently and retain the errors.

### Establish the Fabric MCP connectors

1. Open **Extensions > Connectors > Add connector > MCP Server** (older UI:
   **Builder > Connectors**). Use these connection definitions:

   | Name | Transport and endpoint | Purpose |
   |---|---|---|
   | `fabric-mcp` | Streamable HTTP: `https://api.fabric.microsoft.com/v1/mcp/core` | Fabric Core discovery and item tools |
   | `sqlendpoint-operations-mcp` | Streamable HTTP: `https://api.fabric.microsoft.com/v1/mcp/dataPlane/sqlEndpoint` | `execute_query` for FUAM SQL and SQL Query Insights |

2. Configure the **documented authentication supported by that server and the
   agent host**. The remote Core quickstart documents interactive Entra OAuth
   sign-in. That uses the signed-in user, **not automatically the agent UAMI**.
   Do not paste bearer tokens into instructions or treat a green connection
   badge as proof of managed-identity authentication.
3. This workshop's unattended runtime uses the **agent UAMI**. If a remote
   connector offers supported managed-identity authentication, select the
   assigned UAMI and verify an actual call under that identity. Otherwise the
   coach must validate a managed-identity-capable local Fabric MCP configuration
   before the event: choose **stdio**, command `npx`, arguments
   `["-y", "@microsoft/fabric-mcp@latest", "server", "start", "--mode", "all"]`,
   with the agent's UAMI client ID as `AZURE_CLIENT_ID`. This runs inside the
   SRE Agent environment, not on the participant's laptop; it requires an
   available Node runtime/package access and a working managed-identity
   credential path. A client-ID environment variable alone does not prove
   which credential was used. Record package version and effective identity.
   If that environment/server cannot use the UAMI, stop and escalate to the
   coach; do not silently fall back to delegated OAuth or claim completion.
   Apply the same identity verification to the SQL endpoint connector.
4. Wait for **Connected**, edit the tool selection, enable only required read
   tools, and save. Do **not** use Select all: exclude create/update/delete,
   role changes, moves, job execution, and other mutations. SQL `execute_query`
   must also have server-side read-only data permissions; its name alone does
   not prevent writes.
5. In a new thread, ask for the shared workspace/item by its known ID and a
   bounded SQL `SELECT`. Capture connection ID, actual tool name, result, and
   effective identity. Core's current tool catalog is not a promise of Spark
   monitoring or job-instance tools: use only the approved backend REST path
   when a required read operation is not exposed.
6. Capacity Events consumption uses the configured Eventhouse query URI and
   database via the documented read-only `az rest` KQL path in its instructions;
   `fabric-mcp` discovery does not itself query `OperationsTable`. Verify
   `OperationsTable | getschema` and `OperationsTable | take 1` under the UAMI.

See the [SRE Agent MCP setup](https://learn.microsoft.com/azure/sre-agent/mcp-connector),
[Core MCP connection and authentication](https://learn.microsoft.com/rest/api/fabric/articles/mcp-servers/core-remote/get-started-core),
and [local Fabric MCP setup/security](https://github.com/microsoft/mcp/tree/main/servers/Fabric.Mcp.Server).
The coach verifies endpoint/authentication availability in the event tenant;
document any unsupported path rather than inventing a working one.

### Connect the latest Fabric skills and install the router

1. Open **Context > Code access > GitHub > Add repository** (older UI:
   **Builder > Code Access**). Authorize the GitHub connection, including
   organization SSO where required.
2. Add `https://github.com/microsoft/skills-for-fabric`, branch **`main`**.
   Refresh/sync the repository and check **Connection** and **Last synced**.
   A connected repository can still be stale; refresh before the session and
   after upstream changes. Do not promise that every upstream push is instantly
   present in the agent's synchronized copy.
3. Verify code/file-read tools can list `plugins/fabric-skills/skills/` and read
   `plugins/fabric-skills/skills/spark-cli/SKILL.md` plus its mandatory files.
   Shared references live under `plugins/fabric-skills/common/`.
4. Open **Extensions > Skill builder > Create skill**. Name it
   `fabric-skills-router`; paste the **entire**
   [router SKILL.md](skills/fabric-skills-router/SKILL.md), including YAML
   frontmatter, then save/enable it. Make the Code Access read tools available.
   Do not upload static copies of the upstream operational skills.
5. Ask a Fabric question in a new thread. Inspect tool calls: the router must
   read the selected full `SKILL.md` and every **Mandatory** dependency from
   Code Access before executing the operation, then name the files it read.
   A claim that it read them without file-read evidence is not sufficient.
   No web fetches or remembered skill text may replace a failed Code Access read.

The supplied router uses your requested routing map and resolves, for example,
`../../common/COMMON-CLI.md` relative to the selected skill folder. It retains
the workshop's read-only restrictions even if an upstream skill includes
authoring commands. Use the directory-list fallback if a folder is renamed.

### Apply the backend-specific agent instructions

The two files below are the **ready-to-adapt runtime instructions**, not merely
examples for the learner to rewrite. They incorporate the supplied capacity-RCA
example's capacity context, consumption table/TOTAL, pricing, and diagnostic
workflow, with backend-specific accuracy and workshop safety corrections.

| Team's selected source | File to paste in the agent | Native consumption unit |
|---|---|---|
| FUAM | [FUAM agent-instructions.md](fuam/agent-instructions.md) | `TotalCUs` is CU-seconds |
| Capacity Events | [Capacity Events agent-instructions.md](capacity-events/agent-instructions.md) | `capacityUnitMs` is CU-milliseconds |

The coach supplies section **3.0** connection values, approved monitored scope,
team UAMI client ID, and model/data approval reference. The telemetry workspace
and the monitored workload workspaces are different concepts. The coach also
records events subscription start/retention or FUAM Spark-allocation validation
status as applicable. Never populate these from guesses or paste credentials.

1. Choose **one**: [FUAM instructions](fuam/agent-instructions.md) or
   [Capacity Events instructions](capacity-events/agent-instructions.md).
2. Fill in **section 3.0** with the coach's actual shared workspace/item IDs and
   SQL server/database or Eventhouse query URI/database/table. Keep the
   read-only, router, pricing, native-unit, and failure-reporting rules intact.
3. Open **Extensions > Custom instructions** (older UI:
   **Capabilities > Custom Instructions**), paste the complete selected file,
   and save. These instructions apply globally to the default agent.
4. Check a fresh thread: one bounded cost request, one inaccessible/nonexistent
   item, and a harmless request to make a change. Expect an evidence-backed
   answer, explicit access/no-data reporting, and refusal without a write call.
   Preserve file-read, connector, and calculation evidence.

Retain the capacity context, native-unit conversion, evidence-supported
precision, unknown-value handling, and final **CALCULATION** block. A displayed
period share uses **verified active CU-hours over the whole period**, not a
one-hour denominator and not smoothed utilization. An inaccessible source or
failed pricing lookup must produce an explicit blocked/partial answer, not
zero usage or a fabricated rate. Section 9 defines the report for each backend.

Do not concatenate both backend instruction files. If you deliberately compare
backends, use separate team agents or save/restore the full configuration.
Do not remove safety rules to fit a text limit; place bulky query templates in
an attached supporting skill and verify the agent can read them.

### Azure OpenAI versus Anthropic in SRE Agent

Check **Settings > Basics > Model provider** (some screens label it **AI Model
Provider**) before sending any workshop data. Provider selection is separate
from the agent region, Fabric capacity region, and runtime identity.

| Aspect | Azure OpenAI | Anthropic |
|---|---|---|
| Model family | GPT; SRE Agent routes within the available provider models | Claude; SRE Agent routes within the available provider models |
| Documented strengths | Structured output, function calling, fast tool execution | Long-context reasoning, code analysis, built-in web search |
| EU inference boundary | For SRE Agents deployed in EU/EFTA regions, inference stays within Microsoft's EU Data Boundary | Inference can run globally; excluded from Microsoft's EU Data Boundary commitments |
| Workshop use | Select for EU-residency requirements and verify agent placement | Opt in only with data-owner/compliance approval for global processing |
| What stays the same | Skills, instructions, connectors, read-only permissions, evidence and calculation requirements | Same requirements; web search must not replace Code Access skill reads |

**EU warning:** Do not assume an Anthropic EU data center or EU-local
inference is available to this SRE Agent. The documented service guarantee is
global Anthropic processing, **not** EU-bound processing; an agent in Sweden
Central does not change that. The official SRE Agent docs do not establish the
broader claim that Anthropic has no data centers anywhere in the EU, so do not
present that as a verified corporate-infrastructure fact.

With Azure OpenAI, an EU/EFTA agent region matters; a UK agent location alone
is not evidence of EUDB coverage. Conversation storage and inference location
are different controls. Tool results, code, logs, and query excerpts may enter
the model context, even when tools are read-only. Neither provider uses this
customer data to train models according to the SRE Agent privacy documentation.
AAU/token rates and tool behavior can differ; do not assert a universal quality
winner or reuse Fabric CU estimates as the agent's model cost.

Review the current [model provider guidance](https://learn.microsoft.com/azure/sre-agent/model-provider-selection),
[SRE Agent data residency/privacy](https://learn.microsoft.com/azure/sre-agent/data-privacy),
and [AAU pricing](https://learn.microsoft.com/azure/sre-agent/pricing-billing)
before the event (guidance checked 2026-10-19). If Anthropic is not approved,
compare its documented behavior only; do not switch providers or send a test
prompt to it.
 
---
 
## Versions
 
The versions differ in where CU consumption comes from. Everything else is shared.
 
| Version | CU source | Granularity | Extra Fabric cost | Status |
|---|---|---|---|---|
| [**FUAM**](fuam/README.md) | [FUAM](https://github.com/microsoft/fabric-toolbox/tree/main/monitoring/fabric-unified-admin-monitoring) Lakehouse, loaded from the Capacity Metrics app | Per item, operation and **day**. Per execution for notebooks (derived from Spark allocation) | A few scheduled FUAM runs per day | ✅ Ready |
| [**Capacity events**](capacity-events/README.md) | Fabric capacity operation events → Eventstream → Eventhouse | Per **operation** (every execution, any item) | Always-on Eventstream and Eventhouse | ✅ Ready |
 
**Which one to choose:**
- **FUAM** if day-level cost, plus per-execution detail for notebooks, is enough.
- **Capacity events** if you need exact per-execution CU for pipelines and other non-Spark items, and the always-on streaming cost is acceptable.
---
 
## Repository layout
 
```
README.md                              ← this overview
fuam/
  README.md                            ← setup guide (FUAM version)
  agent-instructions.md                ← paste into Capabilities → Custom Instructions
capacity-events/
  README.md                            ← setup guide (capacity events version)
  agent-instructions.md                ← paste into Capabilities → Custom Instructions
skills/
  fabric-skills-router/SKILL.md        ← shared: loads the official Fabric skills live
tools/
  get_fabric_cu_price.py               ← shared: €/CU-hour from the Azure Retail Prices API
demo/
  perf_demo_inefficient.ipynb          ← deliberately inefficient notebook for testing
```
 
---
 
## Shared components
 
| Component | Used for |
|---|---|
| [`skills/fabric-skills-router`](skills/fabric-skills-router/SKILL.md) | Reads the full skill and Mandatory files from synchronized `main` in [microsoft/skills-for-fabric](https://github.com/microsoft/skills-for-fabric) under Code Access before any Fabric task; refresh for upstream changes, never substitute memory or a web copy |
| [`tools/get_fabric_cu_price.py`](tools/get_fabric_cu_price.py) | The only price source: PAYG and 1-year reservation €/CU-hour per region. Needs `prices.azure.com` in the agent's allowed hosts |
| [`demo/perf_demo_inefficient.ipynb`](demo/perf_demo_inefficient.ipynb) | End-to-end test of cost, RCA and optimization answers: disabled broadcast joins, a fan-out join hidden by `dropDuplicates`, key skew, AQE off, excess shuffle partitions, duplicated work |
 
---
 
## What every cost answer contains
 
1. The answer first, with explicit dates.
2. A breakdown (by item, week, or pipeline child) where useful.
3. A precision label: **exact**, **average per run**, **derived**, or **upper bound**.
4. Data freshness, flagging partial days.
5. A **CALCULATION** block that ends the answer:
```
CALCULATION
Rate:       €<rate> / CU-hour  (PAYG, westeurope, Azure Retail Prices API, retrieved <UTC>)
Native CU:  <a> + <b> + … = <N> <CU-s | CU-ms> (source-native units for <scope>, <from>–<to>)
CU-seconds: <N> [÷ 1,000 when source is CU-ms] = <X> CU-s
CU-hours:   <X> ÷ 3,600 = <Y> CU-h
Cost:       <Y> × €<rate> = €<Z>
```
For FUAM, the native `TotalCUs` value is already CU-seconds. For Capacity
Events, `capacityUnitMs` is CU-milliseconds and must first be divided by 1,000.
**How it's calculated:** Fabric prices capacity per CU-hour, so the CU-seconds
consumed are converted to CU-hours and multiplied by the regional price per
CU-hour.
 
---
 
## Get started
 
- → **[FUAM version setup guide](fuam/README.md)**
- → **[Capacity events version setup guide](capacity-events/README.md)**
## Limits
 
- Prices are **list prices**. Negotiated EA or MCA discounts aren't reflected.
- **OneLake storage** cost isn't included.
- The agent is **read-only**. It never creates, changes, runs or deletes Fabric items.
- [FUAM](https://github.com/microsoft/fabric-toolbox) is a community solution accelerator, not an official Microsoft product.
 
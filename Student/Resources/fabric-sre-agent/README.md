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
| [`skills/fabric-skills-router`](skills/fabric-skills-router/SKILL.md) | Makes the agent read the right skill from [microsoft/skills-for-fabric](https://github.com/microsoft/skills-for-fabric) (connected under Code Access) before any Fabric task. Always the live version, never from memory |
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
 
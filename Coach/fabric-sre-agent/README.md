**[Home](../../README.md)**

# Coach Guide — Azure SRE Agent Fabric FinOps and RCA Track

> **COACHES ONLY — Do not share with participants.**

This track teaches evidence-led, read-only Fabric consumption analysis,
FinOps, performance investigation, and root-cause analysis using Azure SRE
Agent. Students select either FUAM or Capacity Events as their consumption
backend; the guides cover both and make the differences explicit.

## Solution Index

| Challenge | Title | Solution File |
|---|---|---|
| 00 | Prepare the Fabric SRE Agent Lab | [Solution-00.md](./Solution-00.md) |
| 01 | Select and Establish a Consumption Backend | [Solution-01.md](./Solution-01.md) |
| 02 | Connect and Ground the Fabric SRE Agent | [Solution-02.md](./Solution-02.md) |
| 03 | Prove the Cost Calculation and Precision | [Solution-03.md](./Solution-03.md) |
| 04 | Explain Spend by Workspace and Item | [Solution-04.md](./Solution-04.md) |
| 05 | Attribute Execution and Pipeline Consumption | [Solution-05.md](./Solution-05.md) |
| 06 | Investigate Failures, Slowness, and Throttling | [Solution-06.md](./Solution-06.md) |
| 07 | Optimize a Measured Spark Workload | [Solution-07.md](./Solution-07.md) |
| 08 | Assess Coverage and Capacity Context | [Solution-08.md](./Solution-08.md) |
| 09 | Build Your Own Production-Ready Fabric SRE Agent | [Solution-09.md](./Solution-09.md) |

## Azure Requirements

| Resource | Requirement |
|---|---|
| Azure SRE Agent | Running agent; SRE Agent Administrator or equivalent capability-authoring access |
| Azure identity | Agent user-assigned managed identity; no secrets copied into student notes |
| Fabric tenant | Tenant setting allowing the managed identity to call Fabric public APIs |
| Fabric workspaces | Viewer or equivalent read access to monitored and telemetry workspaces |
| Fabric capacity | Capacity administrator for Capacity Events subscriptions; capacity/workspace administration for backend setup as required |
| FUAM backend | Capacity Metrics app, FUAM workspace/Lakehouse, approved service-principal setup, and scheduled FUAM refresh |
| Capacity Events backend | Monitoring workspace on an active capacity, Eventstream, Eventhouse/KQL database, and operation-event subscription |
| Tools | Linux Bash, Azure CLI for documented `az rest` checks, Python 3, and outbound access to approved Fabric and pricing endpoints |
| Billing | Permission to see capacity SKU/region and permission to run or import the optional demo workload |

The monitoring infrastructure has real CU consumption. Capacity Events uses
always-on Eventstream/Eventhouse resources; FUAM incurs scheduled pipeline
work. Use a non-production workspace and obtain capacity-owner approval before
running the demo notebook.

## Suggested Agenda

Times include coach introduction and hands-on time. A full sequence is about
7–8 hours; backend provisioning may take longer and should begin before the
event.

### Full-day event

| Block | Challenges | Est. Time | Focus |
|---|---|---:|---|
| Readiness and source setup | 00–01 | 120 min | Access, backend choice, consumption evidence |
| Agent integration | 02–03 | 100 min | Identity, connectors, skills, cost math |
| FinOps and attribution | 04–05 | 90 min | Workspace trends, execution precision |
| Incident and optimization | 06–08 | 150 min | RCA, Spark diagnostics, data quality |
| Capstone | 09 | 75–90 min | Design, validate, present |

### Focused half-day

Pre-provision one backend and have identities/tenant settings reviewed.
Complete Challenges 02–06 and discuss Challenge 08. Use Challenge 09 as a
separate capstone extension.

## Coaching Philosophy

1. **Require evidence, not confident labels.** Ask where every figure, status,
   timestamp, and cause came from.
2. **Protect read-only boundaries.** Never resolve a connector problem by
   adding broad write access or changing tenant settings without the owner.
3. **Make precision explicit.** FUAM daily aggregates, derived notebook CU,
   and Capacity Events operation rows are not interchangeable.
4. **Separate cost models.** CU-based retail-price estimates are not invoice
   allocation, and monitoring consumes capacity too.
5. **Treat uncertainty as a valid finding.** Reward an honest “not enough
   evidence” over fabricated run attribution or causal certainty.
6. **Timebox cloud dependencies.** Start ingestion and event subscriptions
   early; verify readiness before using workshop time for query exercises.

## Per-Challenge Coach Guide

| Ch | Title | Key Concepts to Introduce | Known Blockers & Hints | Est. Time | When to Intervene |
|---|---|---|---|---:|---|
| 00 | Prepare the Fabric SRE Agent Lab | Tenant vs workspace access, managed identity, capacity ownership | Agent not Running; no capacity admin; Fabric tenant setting disabled | **30–45 min** | Before backend setup if an accountable admin or lab capacity is missing |
| 01 | Select and Establish a Consumption Backend | FUAM day grain, event grain, retention, standing CU | FUAM API setup/refresh lag; event subscription owner lost capacity-admin rights | **60–120 min** | If no sample consumption is queryable after the expected ingestion window |
| 02 | Connect and Ground the Fabric SRE Agent | UAMI, MCP boundaries, live skills, backend instructions | 401/403; wrong instruction set; price domain blocked; missing Code Access sync | **45–60 min** | If students broaden identity permissions instead of isolating the failing boundary |
| 03 | Prove the Cost Calculation and Precision | CU-s to CU-h, CU-ms conversion, list price, precision labels | Dividing ms by 3,600; guessing rates; confusing invoice and standalone cost | **30–40 min** | When calculation operands cannot be independently reproduced |
| 04 | Explain Spend by Workspace and Item | Name resolution, partial periods, preview events, data freshness | Deleted items are NULL; GUID casing; background event ingestion lag | **35–45 min** | If the workspace total fails to reconcile with its breakdown |
| 05 | Attribute Execution and Pipeline Consumption | Job instances, child items, run windows, shared attribution | Pipeline definition mistaken for proof of execution; manual/scheduled overlap | **40–55 min** | When a shared child is attributed to one run without evidence |
| 06 | Investigate Failures, Slowness, and Throttling | Run status, capacity pressure, Spark telemetry, hypothesis testing | Operation events lack smoothed utilization; Spark app is high-concurrency | **45–60 min** | If students call long duration proof of capacity saturation |
| 07 | Optimize a Measured Spark Workload | Stages, skew, shuffle, spill, executor allocation | Capacity Metrics refresh lag; wrong workspace/capacity; demo table reuse | **45–60 min** | If recommendations are generic and unsupported by execution evidence |
| 08 | Assess Coverage and Capacity Context | Freshness, retention, duplicates, monitoring cost | Event delays; paused capacity; preview operations; FUAM refresh schedule | **35–45 min** | If a report says “healthy” without coverage or freshness evidence |
| 09 | Build Your Own Production-Ready Fabric SRE Agent | Bounded use case, least privilege, validation, governance | Broad use case; no measurable test; asks for autonomous write permissions | **75–90 min** | When the scenario has no evidence contract or safe end-to-end test |

## Coach Preparation

- Review the selected backend guide and its known limits before the workshop.
- Confirm the managed identity is visible in the required Fabric workspace(s);
  test the actual read path rather than relying only on role assignments.
- For FUAM, confirm recent data in the Lakehouse and a successful scheduled
  refresh. For Capacity Events, confirm the subscription is active and recent
  rows arrive in `OperationsTable`.
- Configure and test the price tool and outbound allowlist before the session.
- Import the demo notebook only into an approved monitored workspace. Remove
  its `perf_demo_*` tables after the exercise.
- Preserve a human approval boundary; students should not use the agent to
  change items or execute remediation.

Detailed coach prompts and expected observations are in the solution files.
Share outputs and diagnostic evidence, not the reference solution sequence.

## Cleanup

Remove only dedicated workshop objects approved for deletion: demo tables,
Eventstream/Eventhouse resources created for the lab, and FUAM test artifacts.
Do not delete shared workspaces, capacities, or tenant-level resources.

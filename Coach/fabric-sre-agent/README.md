**[Home](../../README.md)**

# Coach Guide — Azure SRE Agent Fabric FinOps and RCA Track

> **COACHES ONLY — Do not share with participants.**

This track teaches evidence-led, read-only Fabric consumption analysis,
FinOps, performance investigation, and root-cause analysis using Azure SRE
Agent. The coach sets up **FUAM and Capacity Events once before the event**
and shares their relevant items with the audience. Students select one shared
source for each team agent; the guides cover both and make the differences explicit.

Deploy the [Fabric infrastructure deliverable](../Solutions/infra/fabric-sre/README.md)
for the shared Fabric capacity, one read-only SRE Agent per team, and
**SRE Agent Administrator** assignments for participant users/security groups.
Backend setup and Fabric read grants are coach-owned preparation, not student
provisioning exercises.

## Solution Index

| Challenge | Title | Solution File |
|---|---|---|
| 00 | Prepare the Fabric SRE Agent Lab | [Solution-00.md](./Solution-00.md) |
| 01 | Select and Validate a Shared Consumption Backend | [Solution-01.md](./Solution-01.md) |
| 02 | Connect and Ground the Fabric SRE Agent | [Solution-02.md](./Solution-02.md) |
| 03 | Prove the Cost Calculation and Precision | [Solution-03.md](./Solution-03.md) |
| 04 | Explain Spend by Workspace and Item | [Solution-04.md](./Solution-04.md) |
| 05 | Validate Model Choice and Data Residency | [Solution-05.md](./Solution-05.md) |
| 06 | Validate Live Skills and Agent Instructions | [Solution-06.md](./Solution-06.md) |
| 07 | Optimize a Measured Spark Workload | [Solution-07.md](./Solution-07.md) |
| 08 | Assess Coverage and Capacity Context | [Solution-08.md](./Solution-08.md) |
| 09 | Build Your Own Production-Ready Fabric SRE Agent | [Solution-09.md](./Solution-09.md) |

## Azure Requirements

| Resource | Requirement |
|---|---|
| Azure SRE Agent | Infrastructure-provisioned Running team agent; every participant configuring it requires SRE Agent Administrator on that agent |
| Azure identity | Agent user-assigned managed identity; no secrets copied into student notes |
| Fabric tenant | Tenant setting allowing the managed identity to call Fabric public APIs |
| Fabric workspaces | Coach shares both backends' relevant items and monitored scope with audience users/groups and every team UAMI; verify effective SQL/KQL/API read access |
| Fabric capacity | Infrastructure-provisioned shared capacity; coach remains capacity administrator and owns event subscriptions; students need no capacity-admin rights |
| FUAM backend | Coach deploys once: Capacity Metrics app, FUAM workspace/Lakehouse, approved service principal, scheduled refresh, and recent rows |
| Capacity Events backend | Coach deploys once: monitoring workspace on the capacity, Eventstream, Eventhouse/KQL database, operation-event subscription, and recent rows |
| Tools | Linux Bash, Azure CLI for documented `az rest` checks, Python 3, and outbound access to approved Fabric and pricing endpoints |
| Billing | Permission to see capacity SKU/region and permission to run or import the optional demo workload |
| Model provider | Coach-approved provider before any real-data query; Azure OpenAI on EU/EFTA agent deployments for EUDB inference; Anthropic requires approval for global processing |
| Agent outbound hosts | `prices.azure.com`, `*.database.fabric.microsoft.com`, and `*.kusto.fabric.microsoft.com` for Capacity Events, plus actual SQL endpoint hosts where different |
| Fabric skills | Code Access to `https://github.com/microsoft/skills-for-fabric`, `main`, refreshed before the event; full skills and Mandatory-file reads verified |

The monitoring infrastructure has real CU consumption. Capacity Events uses
always-on Eventstream/Eventhouse resources; FUAM incurs scheduled pipeline
work. Use a non-production workspace and obtain capacity-owner approval before
running the demo notebook.

## Suggested Agenda

Times include coach introduction and hands-on time. A full sequence is about
7–8 hours. Infrastructure, both backend deployments, ingestion warm-up, and
audience/agent access verification must be completed before the event.

### Full-day event

| Block | Challenges | Est. Time | Focus |
|---|---|---:|---|
| Readiness and shared source validation | 00–01 | 75 min | Agent Administrator access, backend choice, consumption evidence |
| Agent integration | 02–03 | 100 min | Identity, connectors, skills, cost math |
| FinOps and model governance | 04–05 | 80 min | Workspace trends, model capabilities, EU residency |
| Grounding and investigation quality | 06–08 | 135 min | Live skills, instructions, Spark RCA/optimization, coverage |
| Capstone | 09 | 75–90 min | Design, validate, present |

### Focused half-day

Use the same coach-prepared shared backends and have identities/tenant settings reviewed.
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
| 00 | Prepare the Fabric SRE Agent Lab | Agent Administrator vs runtime identity, shared read access, capacity ownership | Agent not Running; missing SRE Agent Administrator; shared items inaccessible | **30–45 min** | Before configuration if a team agent, participant role, or shared access is missing |
| 01 | Select and Validate a Shared Consumption Backend | FUAM day grain, event grain, retention, standing CU | Shared item grants missing; FUAM refresh lag; subscription owner lost capacity-admin rights | **30–45 min** | If no sample consumption is queryable from the prepared sources |
| 02 | Connect and Ground the Fabric SRE Agent | UAMI, MCP boundaries, live skills, backend instructions | 401/403; wrong instruction set; price domain blocked; missing Code Access sync | **45–60 min** | If students broaden identity permissions instead of isolating the failing boundary |
| 03 | Prove the Cost Calculation and Precision | CU-s to CU-h, CU-ms conversion, list price, precision labels | Dividing ms by 3,600; guessing rates; confusing invoice and standalone cost | **30–40 min** | When calculation operands cannot be independently reproduced |
| 04 | Explain Spend by Workspace and Item | Name resolution, partial periods, preview events, data freshness | Deleted items are NULL; GUID casing; background event ingestion lag | **35–45 min** | If the workspace total fails to reconcile with its breakdown |
| 05 | Validate Model Choice and Data Residency | Azure OpenAI/GPT vs Anthropic/Claude, EUDB, inference vs storage, AAUs | Unapproved provider; EU agent mistaken for EU Claude inference | **35–45 min** | Before any disallowed provider receives data |
| 06 | Validate Live Skills and Agent Instructions | Synced `main`, full SKILL.md and Mandatory reads, one backend prompt | Stale sync; wrong paths; web fallback; truncated instructions | **40–55 min** | When tools execute without required reads or instructions use the wrong source |
| 07 | Optimize a Measured Spark Workload | Stages, skew, shuffle, spill, executor allocation | Capacity Metrics refresh lag; wrong workspace/capacity; demo table reuse | **45–60 min** | If recommendations are generic and unsupported by execution evidence |
| 08 | Assess Coverage and Capacity Context | Freshness, retention, duplicates, monitoring cost | Event delays; paused capacity; preview operations; FUAM refresh schedule | **35–45 min** | If a report says “healthy” without coverage or freshness evidence |
| 09 | Build Your Own Production-Ready Fabric SRE Agent | Bounded use case, least privilege, validation, governance | Broad use case; no measurable test; asks for autonomous write permissions | **75–90 min** | When the scenario has no evidence contract or safe end-to-end test |

## Coach Preparation

- Deploy the [Fabric Terraform root](../Solutions/infra/fabric-sre/README.md)
  before the workshop. Include every participant or team security group in its
  agent-scoped SRE Agent Administrator assignments, and verify access with a
  participant account. The deployment identity's role alone is insufficient.
- Review both backend guides and deploy FUAM and Capacity Events once. Assign
  their workspaces to the provisioned capacity, enable ingestion/refresh early,
  and do not ask participants to deploy copies.
- Share the relevant Lakehouse/SQL endpoint and Eventhouse/KQL database plus
  approved monitored items with audience users/groups. Keep setup credentials,
  subscription ownership, and backend write permissions with the coach.
- Confirm the managed identity is visible in the required Fabric workspace(s);
  test the actual read path rather than relying only on role assignments.
- For FUAM, confirm recent data in the Lakehouse and a successful scheduled
  refresh. For Capacity Events, confirm the subscription is active and recent
  rows arrive in `OperationsTable`.
- Configure and test the price tool and outbound allowlist before the session.
- Use the [shared connection/configuration reference](../../Student/Resources/fabric-sre-agent/README.md#agent-connection-and-configuration-reference)
  to validate MCP transport/effective identity, saved outbound hosts, Code
  Access synchronization, router reads, and complete backend instructions.
- Approve and verify the model provider **before Challenge 00 data queries**.
  Anthropic inference may be global and is outside EUDB; do not promise an
  Anthropic EU data center for SRE Agent. Use the documented service boundary,
  not an unsupported claim about all physical Anthropic facilities. Challenge
  05 uses only approved sanitized comparison data or a documentation-only test.
- Give each team its agent URL and identity IDs, both backends' workspace/item
  IDs and SQL/KQL connection identifiers, the Fabric capacity UUID/SKU/region,
  sample workload/run IDs, freshness, history bounds, and known limits.
  Students configure agent capabilities against those shared sources.
- Import the demo notebook only into an approved monitored workspace. Remove
  its `perf_demo_*` tables after the exercise.
- Preserve a human approval boundary; students should not use the agent to
  change items or execute remediation.

Detailed coach prompts and expected observations are in the solution files.
Share outputs and diagnostic evidence, not the reference solution sequence.

## Cleanup

Remove only dedicated workshop objects approved for deletion: demo tables,
Eventstream/Eventhouse resources created for the lab, and FUAM test artifacts.
Participants must not delete shared workspaces, capacities, or tenant-level
resources. After the event the coach follows the
[infrastructure cleanup procedure](../Solutions/infra/fabric-sre/README.md#cleanup)
for dedicated workshop Fabric items, capacity, and team agents. Preserve any
pre-existing/shared production resources.

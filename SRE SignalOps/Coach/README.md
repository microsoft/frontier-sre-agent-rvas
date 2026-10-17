# SRE SignalOps Coach Guides

> COACHES ONLY — Do not share with participants.

Before Deployment stage 00, use [Coach Orientation — Understand Grubify](./Lab-Details.md) with the participant [Lab Details](../Lab-Details.md). Return to the baseline checklist after Deployment stage 02.

For a presentation-ready walkthrough, use the [Grubify Lab Briefing Notes](./Grubify-Lab-Briefing-Notes.md). For the live deployment demonstration, use the [Customer Demo Runbook](./Customer-Demo-00-02.md).

Participant setup guides are in [Deployment](../Deployment/README.md), with
stages 00–02 under [Bicep](../Deployment/Bicep/README.md). Operational challenges
01–12 are in [Missions](../Missions/README.md). Coach guides are separated into
[Deployment](./Deployment) and [Missions](./Missions) so their numbering is unambiguous.

## Deployment Guide Index

| Stage | Title | Solution File |
|---|---|---|
| 00 | Deploy the Workload with azd | [Deployment 00](./Deployment/Solution-00.md) |
| 01 | Deploy the Agent Core with azd | [Deployment 01](./Deployment/Solution-01.md) |
| 02 | Deploy Evidence and Incident Routing with azd | [Deployment 02](./Deployment/Solution-02.md) |

## Solution Index

| Challenge | Title | Solution File |
|---|---|---|
| 01 | Investigate and Recover a Grubify Memory Incident | [Solution 01](./Missions/Solution-01.md) |
| 02 | Build Grubify Knowledge and Incident Memory | [Solution 02](./Missions/Solution-02.md) |
| 03 | Investigate an Evidence Blind Spot | [Solution 03](./Missions/Solution-03.md) |
| 04 | Route a Cross-Domain Incident | [Solution 04](./Missions/Solution-04.md) |
| 05 | Heartbeat Triage and Deep RCA | [Solution 05](./Missions/Solution-05.md) |
| 06 | Improve the Next Heartbeat Response | [Solution 06](./Missions/Solution-06.md) |
| 07 | Respond to a VM Backup Failure with External Approval | [Solution 07](./Missions/Solution-07.md) |
| 08 | Exercise a Guarded HTTP-Error Response | [Solution 08](./Missions/Solution-08.md) |
| 09 | Scope Impact with Dependency Evidence | [Solution 09](./Missions/Solution-09.md) |
| 10 | Investigate a Network Security Failure | [Solution 10](./Missions/Solution-10.md) |
| 11 | Investigate a Routing Black Hole | [Solution 11](./Missions/Solution-11.md) |
| 12 | Plan a Response to an Assurance Risk | [Solution 12](./Missions/Solution-12.md) |

## Azure Requirements

| Resource | Requirement |
|---|---|
| Subscription | Contributor plus permission to assign required SRE Agent roles |
| Food workload | Isolated approved Bicep or Terraform deployment with a healthy baseline |
| Azure SRE Agent | Isolated environment-named agent; record actual root mode and verify three Review specialists |
| Source and knowledge | No default GitHub repository; Bicep stage 02 adds no documents, Terraform completion preloads four, and Mission 02 audits/uploads as needed |
| Telemetry | Log Analytics and Application Insights connectors created in Deployment stage 02 |
| Heartbeat VM | Required for live Challenge 05; otherwise provide a labeled evidence pack |
| Backup and Teams | Required for live Challenge 07; otherwise use evidence-pack mode without claiming a post |
| Network sandbox | Required only for Challenges 10–11; never inject faults into production |

## Suggested Agenda

- **Half day, prepared environment:** Missions 01–06, then choose one investigation from 09–11; allow 3–4 hours.
- **Full day, prepared environment:** Missions 01–12 with breaks; reserve 75–90 minutes for the prepared backup integration.
- **Customer briefing:** Select missions from 02–09 and 12 against a prepared environment; budget 20–30 minutes per demonstration.
- **Deployment workshop:** Schedule Bicep stages 00–02 separately, allowing 75–100 minutes plus Azure provisioning time.

## Coaching Philosophy

1. Ask for evidence before accepting confidence.
2. Keep demonstrations read-only or approval-gated; inspect actual root mode (Bicep Autonomous/High or Terraform Review/High). Both response plans and all three specialists use Review.
3. Before Deployment stage 00, explain the Grubify request, telemetry, incident, and control paths; after Deployment stage 02, verify the live response plan and record the normal baseline; then start Missions 01–12 with the operational issue.
4. Accept `not confirmed` or `not reproduced` when that is what current evidence supports.
5. Stop any fault injection outside the disposable network sandbox.

## Pre-Session Blocker Checklist

| Stage / Mission | Check before students begin | Coach response when blocked |
|---|---|---|
| Before deployment | Participants can identify the frontend, API, in-memory state, and separate evidence/control paths | Use the Lab Details diagrams; do not require deployed Azure evidence yet |
| Deployment 00–02 | azd environment targets the approved subscription and `swedencentral` | Stop before provisioning; select the correct environment and rerun preview |
| Before Mission 01 | Scope, revisions, routes, telemetry, agent access, live handler, and matching all-severity Review plan have a timestamped baseline | Stop on unexplained baseline or routing failures before creating the Mission 01 fault |
| 01 | Baseline health passes; the 5xx alert and fault loop target only the isolated Grubify API | Stop on any target mismatch or unexplained baseline failure; inject the fault once, then collect evidence |
| 02 | Agent Memory is enabled and the four repository knowledge files resolve | Record failed uploads or pending indexing honestly; never expose the data-plane token |
| 03 | ARM and data-plane connector inventories plus harmless Log Analytics and Application Insights reads are available | Use a labeled failed-read result if every source is healthy; never disable a connector to manufacture a failure |
| 04 | Live specialist registration and the application, network, and cost manifests are inspectable | Treat an empty roster as a registration gap and use only a labeled manifest-based routing exercise |
| 05 | The selected VM has recent heartbeat data and a safe recovery path | Choose another VM or use evidence-pack mode |
| 06 | Knowledge ingestion and required read permissions are available | Record the evidence gap and continue without overstating coverage |
| 07 | Separately deployed add-on, published Function, Teams authorization, one protected Madrid VM, initial recovery point and backup-specific configuration are proven | Use a prepared evidence pack or record blocked; never claim live gate/connector certification from supplied evidence |
| 08 | ARM incident wiring, live filters, desired filter, Mission 01 alert, and current workload evidence are inspectable | Treat an empty or mismatched live filter as a routing gap; use a proposal-only tabletop and never request a write |
| 09 | Recent Application Insights request/dependency telemetry exists | Generate harmless baseline traffic or label unsupported edges unobserved |
| 10–11 | A disposable network sandbox and restoration procedure are ready | Use the supplied evidence pack; do not inject faults into production |
| 12 | Advisor, inventory, observability, and required read permissions are available | Record evidence gaps and never report a recommendation as resolved work |

## Per-Challenge Coach Guide

| Ch | Title | Key Concepts | Known Blockers & Hints | Est. Time | When to Intervene |
|---|---|---|---|---|---|
| Lab | Understand Grubify | Application, architecture, evidence paths, and normal baseline | Architecture confused with observed health | **15 min** | Participants treat the SRE Agent as a request-path dependency |
| Deploy 00 | Existing workload | Inventory and health evidence | Wrong subscription or attempted redeployment | **30 min** | Any mutation command is proposed |
| Deploy 01 | Existing agent core | ARM, action mode, RBAC, scope | Wrong agent name or inferred safety mode | **20 min** | Endpoint or managed scope differs |
| Deploy 02 | Evidence and incident routing | Telemetry, live handler, all-severity Review plan, and evidence gaps | Empty source content mistaken for service failure or response plan not registered | **30 min** | A participant starts Mission 01 without proving live routing |
| 01 | Investigate and Recover a Grubify Memory Incident | Metric alert, memory pressure, agent intake, source validation, and recovery | Azure ingestion lag, wrong target, repeated injection, or absent agent incident | **40 min** | Fault runs before target/baseline checks or restart is called a permanent fix |
| 02 | Grubify knowledge | Agent Memory, indexing, and memory-first specialist configuration | Enabled memory mistaken for populated memory | **30 min** | Tokens are exposed or desired state is presented as live state |
| 03 | Evidence blind spot | ARM/data-plane inventory, authorization, source reads, freshness, and escalation | Deployment state mistaken for current evidence | **20 min** | Missing or stale evidence is silently assumed |
| 04 | Cross-domain incident | Live registration, desired-state manifests, evidence-led routing, and one incident owner | Empty roster or overlapping descriptions | **25 min** | Simulated routes are claimed as live or handoffs fragment the timeline |
| 05 | RCA | Hypothesis testing | Missing zero-row alert query | **25 min** | RCA states unsupported cause |
| 06 | Repeat incident | Verified context and evidence precedence | Stale knowledge | **25 min** | Historical cause replaces current checks |
| 07 | VM backup failure with external approval | Native alerts, authenticated Teams decision, incident age, one-time retry and recovery-point validation | Separate add-on, existing Madrid VM, Function publication and Teams authorization | **75–90 min** | A retry bypasses the gate, a VM start/restore is proposed, or supplied evidence is claimed live |
| 08 | HTTP-error response | Routing predicates, proposal-only response, stop branches, and recovery proof | Empty live filters, alert mismatch, or autonomous write risk | **30 min** | Routing is overstated, execution is requested, or action precedes evidence |
| 09 | Impact scope | Critical path and blast radius | Missing telemetry | **25 min** | Whole-service impact is assumed |
| 10 | NSG | Effective rules | Wrong association | **30 min** | Student targets production |
| 11 | Routing | Effective next hop | Return path omitted | **30 min** | Fault is not restored |
| 12 | Assurance risk | Preventive response and validation | Missing cost or monitoring scope | **25 min** | A plan is reported as resolved |
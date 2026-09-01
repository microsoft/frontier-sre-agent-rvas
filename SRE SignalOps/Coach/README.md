# SRE SignalOps Coach Guides

> COACHES ONLY — Do not share with participants.

Before Mission 00, use [Coach Orientation — Understand Grubify](./Lab-Details.md) with the participant [Lab Details](../Lab-Details.md). Return to the baseline checklist after Mission 02.

## Solution Index

| Challenge | Title | Solution File |
|---|---|---|
| 00 | Deploy the Workload with azd | [Solution 00](./Solution-00.md) |
| 01 | Deploy the Agent Core with azd | [Solution 01](./Solution-01.md) |
| 02 | Deploy Evidence Connectors with azd | [Solution 02](./Solution-02.md) |
| 03 | Investigate and Recover a Grubify Memory Incident | [Solution 03](./Solution-03.md) |
| 04 | Build Grubify Knowledge and Incident Memory | [Solution 04](./Solution-04.md) |
| 05 | Investigate an Evidence Blind Spot | [Solution 05](./Solution-05.md) |
| 06 | Route a Cross-Domain Incident | [Solution 06](./Solution-06.md) |
| 07 | Exercise a Guarded HTTP-Error Response | [Solution 07](./Solution-07.md) |
| 08 | Scope Impact with Dependency Evidence | [Solution 08](./Solution-08.md) |
| 09 | Investigate a Network Security Failure | [Solution 09](./Solution-09.md) |
| 10 | Investigate a Routing Black Hole | [Solution 10](./Solution-10.md) |
| 11 | Heartbeat Triage and Deep RCA | [Solution 11](./Solution-11.md) |
| 12 | Improve the Next Heartbeat Response | [Solution 12](./Solution-12.md) |
| 13 | Resolve a Critical Assurance Risk | [Solution 13](./Solution-13.md) |
| 14 | Resolve a Backup Assurance Incident | [Solution 14](./Solution-14.md) |

## Azure Requirements

| Resource | Requirement |
|---|---|
| Subscription | Contributor plus permission to assign required SRE Agent roles |
| Food workload | Isolated azd/Bicep deployment in Sweden Central, created in Challenge 00 |
| Azure SRE Agent | Isolated environment-named agent, Autonomous mode, High access, created in Challenge 01 |
| Source and knowledge | State is audited after deployment; Challenge 02 adds no documents, and Challenge 04 uploads the four approved Grubify knowledge files |
| Telemetry | Log Analytics and Application Insights connectors created in Challenge 02 |
| Network sandbox | Required only for Challenges 09–10; never inject faults into production |
| Heartbeat VM | Required for live Challenge 11; otherwise provide a labeled evidence pack |
| Backup and Teams | Required for live Challenge 14; otherwise use evidence-pack mode without claiming a post |

## Suggested Agenda

- **Half day:** Challenges 00–08, then choose one investigation from 09–11.
- **Full day:** Challenges 00–14 with breaks after each phase.
- **Customer briefing:** Demonstrate 04–08, 11, and 14 against a prepared environment.

## Coaching Philosophy

1. Ask for evidence before accepting confidence.
2. Keep demonstrations read-only or approval-gated; the existing agent is Autonomous with High access.
3. Before Mission 00, explain the Grubify request, telemetry, incident, and control paths; after Mission 02, record the normal baseline; then start Missions 03–14 with the operational issue.
4. Accept `not confirmed` or `not reproduced` when that is what current evidence supports.
5. Stop any fault injection outside the disposable network sandbox.

## Pre-Session Blocker Checklist

| Missions | Check before students begin | Coach response when blocked |
|---|---|---|
| Before 00 | Participants can identify the frontend, API, in-memory state, and separate evidence/control paths | Use the Lab Details diagrams; do not require deployed Azure evidence yet |
| 00–02 | azd environment targets the approved subscription and `swedencentral` | Stop before provisioning; select the correct environment and rerun preview |
| Before 03 | Scope, revisions, routes, telemetry, and agent access have a timestamped baseline | Stop on unexplained baseline failures and resolve prerequisites before applying Mission 03 configuration |
| 03 | Baseline health passes; the 5xx alert and fault loop target only the isolated Grubify API | Stop on any target mismatch or unexplained baseline failure; inject the fault once, then collect evidence |
| 04 | Agent Memory is enabled and the four repository knowledge files resolve | Record failed uploads or pending indexing honestly; never expose the data-plane token |
| 05 | ARM and data-plane connector inventories plus harmless Log Analytics and Application Insights reads are available | Use a labeled failed-read result if every source is healthy; never disable a connector to manufacture a failure |
| 06 | Live specialist registration and the application, network, and cost manifests are inspectable | Treat an empty roster as a registration gap and use only a labeled manifest-based routing exercise |
| 07 | ARM incident wiring, live filters, desired filter, Mission 03 alert, and current workload evidence are inspectable | Treat empty filters and the `Sev2`/title mismatch as routing gaps; use a proposal-only tabletop and never request a write |
| 08 | Recent Application Insights request/dependency telemetry exists | Generate harmless baseline traffic or label unsupported edges unobserved |
| 09–10 | A disposable network sandbox and restoration procedure are ready | Use the supplied evidence pack; do not inject faults into production |
| 11 | The selected VM has recent heartbeat data and a safe recovery path | Choose another VM or use evidence-pack mode |
| 12–13 | Knowledge ingestion and required read permissions are available | Record the evidence gap and continue without overstating coverage |
| 14 | Vault alerts and Teams connector authorization are proven | Run a clearly labeled exercise and do not claim a real post or failed backup |

## Per-Challenge Coach Guide

| Ch | Title | Key Concepts | Known Blockers & Hints | Est. Time | When to Intervene |
|---|---|---|---|---|---|
| Lab | Understand Grubify | Application, architecture, evidence paths, and normal baseline | Architecture confused with observed health | **15 min** | Participants treat the SRE Agent as a request-path dependency |
| 00 | Existing workload | Inventory and health evidence | Wrong subscription or attempted redeployment | **30 min** | Any mutation command is proposed |
| 01 | Existing agent core | ARM, action mode, RBAC, scope | Wrong agent name or inferred safety mode | **20 min** | Endpoint or managed scope differs |
| 02 | Existing ground truth | Telemetry and evidence gaps | Empty source content mistaken for service failure | **25 min** | A participant attempts OAuth or upload |
| 03 | Investigate and Recover a Grubify Memory Incident | Metric alert, memory pressure, agent intake, source validation, and recovery | Azure ingestion lag, wrong target, repeated injection, or absent agent incident | **40 min** | Fault runs before target/baseline checks or restart is called a permanent fix |
| 04 | Grubify knowledge | Agent Memory, indexing, and memory-first specialist configuration | Enabled memory mistaken for populated memory | **30 min** | Tokens are exposed or desired state is presented as live state |
| 05 | Evidence blind spot | ARM/data-plane inventory, authorization, source reads, freshness, and escalation | Deployment state mistaken for current evidence | **20 min** | Missing or stale evidence is silently assumed |
| 06 | Cross-domain incident | Live registration, desired-state manifests, evidence-led routing, and one incident owner | Empty roster or overlapping descriptions | **25 min** | Simulated routes are claimed as live or handoffs fragment the timeline |
| 07 | HTTP-error response | Routing predicates, proposal-only response, stop branches, and recovery proof | Empty live filters, alert mismatch, or autonomous write risk | **30 min** | Routing is overstated, execution is requested, or action precedes evidence |
| 08 | Impact scope | Critical path and blast radius | Missing telemetry | **25 min** | Whole-service impact is assumed |
| 09 | NSG | Effective rules | Wrong association | **30 min** | Student targets production |
| 10 | Routing | Effective next hop | Return path omitted | **30 min** | Fault is not restored |
| 11 | RCA | Hypothesis testing | Missing zero-row alert query | **25 min** | RCA states unsupported cause |
| 12 | Repeat incident | Verified context and evidence precedence | Stale knowledge | **25 min** | Historical cause replaces current checks |
| 13 | Assurance risk | Preventive response and validation | Missing cost or monitoring scope | **25 min** | A plan is reported as resolved |
| 14 | Backup incident | RTO/RPO, communication, and validation | Teams/Backup readiness | **25 min** | Restore is treated as app health |
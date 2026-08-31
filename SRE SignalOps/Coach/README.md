# SRE SignalOps Coach Guides

> COACHES ONLY — Do not share with participants.

## Solution Index

| Challenge | Title | Solution File |
|---|---|---|
| 00 | Deploy the Workload with azd | [Solution 00](./Solution-00.md) |
| 01 | Deploy the Agent Core with azd | [Solution 01](./Solution-01.md) |
| 02 | Deploy Evidence Connectors with azd | [Solution 02](./Solution-02.md) |
| 03 | Triage the First Grubify Incident | [Solution 03](./Solution-03.md) |
| 04 | Investigate an Evidence Blind Spot | [Solution 04](./Solution-04.md) |
| 05 | Route a Cross-Domain Incident | [Solution 05](./Solution-05.md) |
| 06 | Exercise a Guarded HTTP-Error Response | [Solution 06](./Solution-06.md) |
| 07 | Scope Impact with Dependency Evidence | [Solution 07](./Solution-07.md) |
| 08 | Investigate a Network Security Failure | [Solution 08](./Solution-08.md) |
| 09 | Investigate a Routing Black Hole | [Solution 09](./Solution-09.md) |
| 10 | Heartbeat Triage and Deep RCA | [Solution 10](./Solution-10.md) |
| 11 | Improve the Next Heartbeat Response | [Solution 11](./Solution-11.md) |
| 12 | Resolve a Critical Assurance Risk | [Solution 12](./Solution-12.md) |
| 13 | Resolve a Backup Assurance Incident | [Solution 13](./Solution-13.md) |

## Azure Requirements

| Resource | Requirement |
|---|---|
| Subscription | Contributor plus permission to assign required SRE Agent roles |
| Food workload | Isolated azd/Bicep deployment in Sweden Central, created in Challenge 00 |
| Azure SRE Agent | Isolated environment-named agent, Autonomous mode, High access, created in Challenge 01 |
| Source and knowledge | State is audited after deployment; Challenge 02 does not add OAuth credentials or documents |
| Telemetry | Log Analytics and Application Insights connectors created in Challenge 02 |
| Network sandbox | Required only for Challenges 08–09; never inject faults into production |
| Heartbeat VM | Required for live Challenge 10; otherwise provide a labeled evidence pack |
| Backup and Teams | Required for live Challenge 13; otherwise use evidence-pack mode without claiming a post |

## Suggested Agenda

- **Half day:** Challenges 00–07, then choose one investigation from 08–10.
- **Full day:** Challenges 00–13 with breaks after each phase.
- **Customer briefing:** Demonstrate 04–07, 10, and 13 against a prepared environment.

## Coaching Philosophy

1. Ask for evidence before accepting confidence.
2. Keep demonstrations read-only or approval-gated; the existing agent is Autonomous with High access.
3. Start Missions 03–13 with the operational issue, not the product feature used to investigate it.
4. Accept `not confirmed` or `not reproduced` when that is what current evidence supports.
5. Stop any fault injection outside the disposable network sandbox.

## Pre-Session Blocker Checklist

| Missions | Check before students begin | Coach response when blocked |
|---|---|---|
| 00–02 | azd environment targets the approved subscription and `swedencentral` | Stop before provisioning; select the correct environment and rerun preview |
| 03 | Git Bash, `jq`, and `yq` are available; plan-only simulation lists 8 skills, 11 subagents, 1 platform, and 4 filters | Use `Challenge-03.ps1` without `-Execute`; resolve prerequisites before applying |
| 04–06 | Connector authorization, specialist manifests, and incident routing are inspectable | Use unverified labels or a labeled exercise; never invent connectivity or incidents |
| 07 | Recent Application Insights request/dependency telemetry exists | Generate harmless baseline traffic or label unsupported edges unobserved |
| 08–09 | A disposable network sandbox and restoration procedure are ready | Use the supplied evidence pack; do not inject faults into production |
| 10 | The selected VM has recent heartbeat data and a safe recovery path | Choose another VM or use evidence-pack mode |
| 11–12 | Knowledge ingestion and required read permissions are available | Record the evidence gap and continue without overstating coverage |
| 13 | Vault alerts and Teams connector authorization are proven | Run a clearly labeled exercise and do not claim a real post or failed backup |

## Per-Challenge Coach Guide

| Ch | Title | Key Concepts | Known Blockers & Hints | Est. Time | When to Intervene |
|---|---|---|---|---|---|
| 00 | Existing workload | Inventory and health evidence | Wrong subscription or attempted redeployment | **30 min** | Any mutation command is proposed |
| 01 | Existing agent core | ARM, action mode, RBAC, scope | Wrong agent name or inferred safety mode | **20 min** | Endpoint or managed scope differs |
| 02 | Existing ground truth | Telemetry and evidence gaps | Empty source content mistaken for service failure | **25 min** | A participant attempts OAuth or upload |
| 03 | First incident | Evidence-led triage and guarded action | Git Bash path or unconfirmed symptom | **25 min** | Diagnosis lacks current evidence |
| 04 | Evidence blind spot | Source failure, fallback, and escalation | Reachability vs configuration | **20 min** | Missing evidence is silently assumed |
| 05 | Cross-domain incident | Evidence-led routing and one incident owner | Overlapping descriptions | **20 min** | Handoffs fragment the timeline |
| 06 | HTTP-error response | Intake, action gate, and recovery proof | Alert mismatch | **25 min** | Action precedes evidence |
| 07 | Impact scope | Critical path and blast radius | Missing telemetry | **25 min** | Whole-service impact is assumed |
| 08 | NSG | Effective rules | Wrong association | **30 min** | Student targets production |
| 09 | Routing | Effective next hop | Return path omitted | **30 min** | Fault is not restored |
| 10 | RCA | Hypothesis testing | Missing zero-row alert query | **25 min** | RCA states unsupported cause |
| 11 | Repeat incident | Verified context and evidence precedence | Stale knowledge | **25 min** | Historical cause replaces current checks |
| 12 | Assurance risk | Preventive response and validation | Missing cost or monitoring scope | **25 min** | A plan is reported as resolved |
| 13 | Backup incident | RTO/RPO, communication, and validation | Teams/Backup readiness | **25 min** | Restore is treated as app health |
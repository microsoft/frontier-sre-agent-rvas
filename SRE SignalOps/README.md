# SRE SignalOps

SRE SignalOps is a compact incident-response track for Azure SRE Agent. After bootstrapping the environment, every mission begins with a reported or simulated operational issue and asks participants to investigate, diagnose, propose a governed response, and define recovery evidence.

Open the [dashboard source](../web/signalops/index.html).

## Workspace

- [Deployment](./Deployment/README.md): separate [Terraform](./Deployment/Terraform/README.md) and [Bicep](./Deployment/Bicep/README.md) paths.
- [Missions](./Missions/README.md): operational scenarios 01–12, after deployment and baseline validation.
- [Coach](./Coach/README.md): facilitator guides.

Deployment guides live under `Deployment`; operational challenges live under
`Missions`. The azd service manifest, infrastructure, and scripts remain at the
project root so their existing source and execution paths stay valid.

## Before Deployment

Start with [Lab Details — Understand Grubify](./Lab-Details.md) (15–20 min). It explains the application, Azure resource architecture, customer and evidence flows, and expected normal baseline before participants deploy anything.

Return to its baseline checklist after completing either deployment path and record the observed state before Mission 01.

## Deployment Stages

Choose [Terraform](./Deployment/Terraform/README.md) for the full lab, or
[Bicep](./Deployment/Bicep/README.md) for the isolated core. Bicep uses the
following stages; these numbers are independent of mission numbers.

| Stage | Outcome |
|---|---|
| [00](./Deployment/Bicep/Challenge-00.md) | Deploy the Workload with azd |
| [01](./Deployment/Bicep/Challenge-01.md) | Deploy the Agent Core with azd |
| [02](./Deployment/Bicep/Challenge-02.md) | Deploy Evidence and Incident Routing with azd |

## Mission Index

Categories describe the type of work, not sequential phases. Complete deployment
first, then follow mission numbers and each mission's prerequisites.

| Mission | Category | Outcome | Time |
|---|---|---|---|
| [01](./Missions/Challenge-01.md) | Foundation | Investigate and Recover a Grubify Memory Incident | 30–40 min |
| [02](./Missions/Challenge-02.md) | Foundation | Build Grubify Knowledge and Incident Memory | 20–30 min |
| [03](./Missions/Challenge-03.md) | Connections & Routing | Investigate an Evidence Blind Spot | 15–20 min |
| [04](./Missions/Challenge-04.md) | Connections & Routing | Route a Cross-Domain Incident | 15–20 min |
| [05](./Missions/Challenge-05.md) | Incident Response | Heartbeat Triage and Deep RCA | 20–25 min |
| [06](./Missions/Challenge-06.md) | Incident Response | Improve the Next Heartbeat Response | 20–25 min |
| [07](./Missions/Challenge-07.md) | Incident Response | Respond to a VM Backup Failure with External Approval | 75–90 min (prepared integration) |
| [08](./Missions/Challenge-08.md) | Connections & Routing | Exercise a Guarded HTTP-Error Response | 20–25 min |
| [09](./Missions/Challenge-09.md) | Dependencies & Networking | Scope Impact with Dependency Evidence | 20–25 min |
| [10](./Missions/Challenge-10.md) | Dependencies & Networking | Investigate a Network Security Failure | 25–30 min |
| [11](./Missions/Challenge-11.md) | Dependencies & Networking | Investigate a Routing Black Hole | 25–30 min |
| [12](./Missions/Challenge-12.md) | Incident Response | Plan a Response to an Assurance Risk | 20–25 min |

## Tools to Install

- PowerShell 7
- Azure CLI
- Azure Developer CLI (`azd`)
- Git and Git for Windows
- GitHub CLI for repository authorization

The Bicep deployment stages 00–02 provision an isolated SignalOps core through azd. The separate full-lab deployment path has its own prerequisites and readiness gate.

## Infrastructure Readiness

| Stage / Mission | Readiness | Source |
|---|---|---|
| Before deployment | Lab orientation | Understand the Grubify application and expected architecture; no Azure resources are required yet |
| Deployment 00 | azd workload stage | Create an isolated registry, Container Apps environment, food API/frontend, Log Analytics, and workspace-backed Application Insights |
| Deployment 01 | azd agent stage | Add an isolated SRE Agent, managed identity, agent telemetry, managed scope, and governed RBAC |
| Deployment 02 | azd connector and routing stage | Add Log Analytics and Application Insights connectors, the Grubify response subagent, and an all-severity Review response plan; then audit repository, memory, knowledge, and routing state |
| Before Mission 01 | Observed baseline and routing gate | Record scope, revisions, routes, telemetry, and agent access; verify the live handler and enabled matching response plan before fault injection |
| 01 | Controlled live incident | Create a scoped 5xx alert, inject the Grubify cart memory fault with inline commands, inspect SRE Agent intake, validate RCA evidence, and recover the API |
| 02 | Agent Memory | Upload the four approved Grubify knowledge documents, verify indexing, and compare the local memory-aware handler with live registration |
| 03–04, 08–09, 12 | Live evidence or simulated issue | Consume the configured operating model for evidence validation, cross-domain routing, guarded response, dependency scoping, and preventive assurance review |
| 05–06 | Coach-provided or simulated | Use a monitored VM with recent Heartbeat data, or the coach evidence pack |
| 07 | Customer/coach-provided or simulated | Live mode requires a protected workload and authorized Teams connector; evidence-pack mode requires neither write access nor message delivery |
| 10–11 | Coach-provided | Use a disposable hub-spoke network sandbox with Network Watcher and flow evidence, or a supplied incident snapshot |

Stages 00–02 deploy only the approved SignalOps core subset into environment-named resource groups. Later hub-spoke and parking scenarios require a separately prepared sandbox or evidence pack.

Coach references are in the [Coach folder](./Coach).

Customer-facing commands, expected observations, fallbacks, and safety switches are in the [presenter runbook](./Scripts/README.md). Missions 01–08 are intentionally run command-by-command from their challenge pages and have no wrapper scripts.
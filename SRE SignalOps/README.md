# SRE SignalOps

SRE SignalOps is a compact incident-response track for Azure SRE Agent. After bootstrapping the environment, every mission begins with a reported or simulated operational issue and asks participants to investigate, diagnose, propose a governed response, and define recovery evidence.

Open the [dashboard source](../web/signalops/index.html) or the [published SignalOps experience](https://ravi0130.github.io/frontier-sre-agent-rvas/signalops/).

## Before Mission 00

Start with [Lab Details — Understand Grubify](./Lab-Details.md) (15–20 min). It explains the application, Azure resource architecture, customer and evidence flows, and expected normal baseline before participants deploy anything.

Return to its baseline checklist after Missions 00–02 and record the observed state before Mission 03.

## Mission Index

| Mission | Phase | Outcome | Time |
|---|---|---|---|
| [00](./Challenge-00.md) | Bootstrap | Deploy the Workload with azd | 30–40 min + deployment |
| [01](./Challenge-01.md) | Bootstrap | Deploy the Agent Core with azd | 20–30 min + deployment |
| [02](./Challenge-02.md) | Bootstrap | Deploy Evidence Connectors with azd | 20–25 min + deployment |
| [03](./Challenge-03.md) | Bootstrap | Automated Incident Triage and RCA | 30–40 min |
| [04](./Challenge-04.md) | Wire | Investigate an Evidence Blind Spot | 15–20 min |
| [05](./Challenge-05.md) | Wire | Route a Cross-Domain Incident | 15–20 min |
| [06](./Challenge-06.md) | Wire | Exercise a Guarded HTTP-Error Response | 20–25 min |
| [07](./Challenge-07.md) | Trace | Scope Impact with Dependency Evidence | 20–25 min |
| [08](./Challenge-08.md) | Trace | Investigate a Network Security Failure | 25–30 min |
| [09](./Challenge-09.md) | Trace | Investigate a Routing Black Hole | 25–30 min |
| [10](./Challenge-10.md) | Operate | Heartbeat Triage and Deep RCA | 20–25 min |
| [11](./Challenge-11.md) | Operate | Improve the Next Heartbeat Response | 20–25 min |
| [12](./Challenge-12.md) | Operate | Resolve a Critical Assurance Risk | 20–25 min |
| [13](./Challenge-13.md) | Operate | Resolve a Backup Assurance Incident | 20–25 min |

## Tools to Install

- PowerShell 7
- Azure CLI
- Azure Developer CLI (`azd`)
- Git and Git for Windows
- GitHub CLI for repository authorization

The original lab was deployed with Terraform. Missions 00–02 use it as the parity reference while deploying an isolated SignalOps core through azd and Bicep.

## Infrastructure Readiness

| Missions | Readiness | Source |
|---|---|---|
| Before 00 | Lab orientation | Understand the Grubify application and expected architecture; no Azure resources are required yet |
| 00 | azd workload stage | Create an isolated registry, Container Apps environment, food API/frontend, Log Analytics, and workspace-backed Application Insights |
| 01 | azd agent stage | Add an isolated SRE Agent, managed identity, agent telemetry, managed scope, and governed RBAC |
| 02, 04 | azd connector stage and audit | Add Log Analytics and Application Insights connectors, then audit repository, memory, and knowledge state |
| Before 03 | Observed baseline | Return to Lab Details and record scope, revisions, routes, telemetry, and agent access as PASS, FAIL, or UNKNOWN |
| 03 | Controlled live incident | Create a scoped 5xx alert, inject the Grubify cart memory fault with inline commands, inspect SRE Agent intake, validate RCA evidence, and recover the API |
| 04–07, 12 | Live evidence or simulated issue | Consume the configured operating model for evidence validation, cross-domain routing, guarded response, dependency scoping, and preventive assurance review |
| 08, 09 | Coach-provided | Use a disposable hub-spoke network sandbox with Network Watcher and flow evidence, or a supplied incident snapshot |
| 10, 11 | Coach-provided or simulated | Use a monitored VM with recent Heartbeat data, or the coach evidence pack |
| 13 | Customer/coach-provided or simulated | Live mode requires a protected workload and authorized Teams connector; evidence-pack mode requires neither write access nor message delivery |

The existing MCAPS Terraform lab remains available for later hub-spoke and parking scenarios. Missions 00–02 deploy only the approved SignalOps core subset into environment-named resource groups and do not mutate Terraform-managed resources.

Coach references are in the [Coach folder](./Coach/).

Customer-facing commands, expected observations, fallbacks, and safety switches are in the [presenter runbook](./Scripts/README.md). Mission 03 is intentionally run command-by-command from its challenge page and has no wrapper script.
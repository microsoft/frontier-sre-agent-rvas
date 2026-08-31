# SRE SignalOps

SRE SignalOps is a compact operator track for Azure SRE Agent. It follows one signal chain across four phases: bootstrap the environment, wire intelligence, trace dependencies, and operate with evidence.

Open the [dashboard source](../web/signalops/index.html) or the [published SignalOps experience](https://microsoft.github.io/frontier-sre-agent-rvas/signalops/).

## Mission Index

| Mission | Phase | Outcome | Time |
|---|---|---|---|
| [00](./Challenge-00.md) | Bootstrap | Deploy the Workload with azd | 30–40 min + deployment |
| [01](./Challenge-01.md) | Bootstrap | Deploy the Agent Core with azd | 20–30 min + deployment |
| [02](./Challenge-02.md) | Bootstrap | Deploy Evidence Connectors with azd | 20–25 min + deployment |
| [03](./Challenge-03.md) | Bootstrap | Arm the Operator | 20–25 min |
| [04](./Challenge-04.md) | Wire | Discover Connected Systems | 15–20 min |
| [05](./Challenge-05.md) | Wire | Discover Specialist Agents | 15–20 min |
| [06](./Challenge-06.md) | Wire | Understand Response Plans | 20–25 min |
| [07](./Challenge-07.md) | Trace | Map the Application Dependency Graph | 20–25 min |
| [08](./Challenge-08.md) | Trace | Investigate a Network Security Failure | 25–30 min |
| [09](./Challenge-09.md) | Trace | Investigate a Routing Black Hole | 25–30 min |
| [10](./Challenge-10.md) | Operate | Heartbeat Triage and Deep RCA | 20–25 min |
| [11](./Challenge-11.md) | Operate | Context That Learns | 20–25 min |
| [12](./Challenge-12.md) | Operate | Proactive Tenant Optimization | 20–25 min |
| [13](./Challenge-13.md) | Operate | Backup-to-Teams Resilience | 20–25 min |

## Tools to Install

- PowerShell 7
- Azure CLI
- Azure Developer CLI (`azd`)
- Git and Git for Windows
- GitHub CLI for repository authorization
- `jq` and `yq` for SRE Agent configuration validation

The original lab was deployed with Terraform. Missions 00–02 use it as the parity reference while deploying an isolated SignalOps core through azd and Bicep.

## Infrastructure Readiness

| Missions | Readiness | Source |
|---|---|---|
| 00 | azd workload stage | Create an isolated registry, Container Apps environment, food API/frontend, Log Analytics, and workspace-backed Application Insights |
| 01 | azd agent stage | Add an isolated SRE Agent, managed identity, agent telemetry, managed scope, and governed RBAC |
| 02, 04 | azd connector stage and audit | Add Log Analytics and Application Insights connectors, then audit repository, memory, and knowledge state |
| 03, 05, 06, 12 | Applied by configuration client | CH-03 selectively validates, plans, applies, and verifies skills, subagents, Azure Monitor incident configuration, and incident filters |
| 08, 09 | Coach-provided | Use a disposable hub-spoke network sandbox with Network Watcher and flow evidence, or a supplied incident snapshot |
| 10, 11 | Coach-provided or simulated | Use a monitored VM with recent Heartbeat data, or the coach evidence pack |
| 13 | Customer/coach-provided or simulated | Live mode requires a protected workload and authorized Teams connector; evidence-pack mode requires neither write access nor message delivery |

The existing MCAPS Terraform lab remains available for later hub-spoke and parking scenarios. Missions 00–02 deploy only the approved SignalOps core subset into environment-named resource groups and do not mutate Terraform-managed resources.

Coach references are in the [Coach folder](./Coach/).

Customer-facing PowerShell automation, expected observations, fallbacks, and safety switches are in the [presenter runbook](./Scripts/README.md).
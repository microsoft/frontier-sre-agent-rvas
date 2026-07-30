# Azure SRE Agent Demo Lab Environment

This folder documents the customer demo lab integrated from `lpassaretta_microsoft/azure-vnet-flow-logs-and-traffic-analytics` branch `feature/app-sample-food-container-app`.

The demo lab is implemented in the existing Terraform root, `infra/`, while the existing Azure SRE Agent root remains authoritative. The lab provides observable Azure resources that the agent can inspect: hub/spoke networking, Azure Firewall, VM-based traffic, VNet Flow Logs, Traffic Analytics, and the Sample Food Ordering App on Azure Container Apps.

## What The Lab Deploys

| Area | Resources |
| --- | --- |
| Base network | Hub VNet, app spoke, data spoke, peerings, subnets, NSGs, route tables |
| Central routing | Azure Firewall Basic with `AzureFirewallSubnet` and `AzureFirewallManagementSubnet` |
| VM workload | Client VM, two web VMs, API VM, DB VM, NVA VM, internal load balancer |
| Observability | Flow log storage account, Log Analytics workspace, VNet Flow Logs, Traffic Analytics workbook; Azure Monitor Agent + Syslog Data Collection Rule on the web VMs |
| Food sample | Azure Container Registry, Container Apps Environment, API app, frontend app, Application Insights |
| Agent assets | Sample Food incident skill and Sample Food SRE subagent under `azure-sre-agent-config/` |

## Imported Legacy Azure SRE Agent Docs

These files were imported from the external repository `docs-azure-sre-agent/` and intentionally prefixed with `OLD-Doc-` so their provenance is visible:

- [OLD-Doc-How-To-Azure-SRE-Agent-IaC.md](OLD-Doc-How-To-Azure-SRE-Agent-IaC.md)
- [OLD-Doc-azure-sre-agent-arch-and-impl-in-iac-guide.md](OLD-Doc-azure-sre-agent-arch-and-impl-in-iac-guide.md)
- [OLD-Doc-azure-sre-agent-implementation-guide.md](OLD-Doc-azure-sre-agent-implementation-guide.md)
- [OLD-Doc-azure-sre-agent-terraform-code-walkthrough.md](OLD-Doc-azure-sre-agent-terraform-code-walkthrough.md)

Treat these as historical/source-reference documents. Current operational commands for this repository are documented in this folder and in the root README.

## Deploy

From the repository root:

```bash
terraform -chdir=infra init
terraform -chdir=infra plan
terraform -chdir=infra apply
```

The VM admin credential is intentionally kept inline for this demo lab:

```text
azureuser / Use-A-Strong-Demo-Password-123!
```

This is a demo-only shortcut. Do not use this pattern for production environments.

## Validate The Lab

```bash
Student/Resources/scenarios/scripts/validate.sh
Student/Resources/scenarios/scripts/deploy-sample-food-images.sh --status
Student/Resources/scenarios/scripts/validate-sample-food-app.sh
```

After Terraform deploy, the Container Apps start with Microsoft hello-world placeholder images. Deploy the real Grubify images with:

```bash
Student/Resources/scenarios/scripts/deploy-sample-food-images.sh
```

The image deployment script builds from:

```text
https://github.com/dm-chelupati/grubify.git#main
```

## Generate Demo Traffic

VM/network baseline traffic:

```bash
Student/Resources/scenarios/scripts/generate-baseline-traffic.sh
```

Sample Food HTTP traffic:

```bash
Student/Resources/scenarios/scripts/generate-sample-food-app-traffic.sh
```

Controlled Sample Food cart load:

```bash
Student/Resources/scenarios/scripts/break-sample-food-app.sh
```

## Run KQL Queries

Use the KQL helper with a built-in query alias:

```bash
Student/Resources/scenarios/scripts/run-kql.sh top-talkers
Student/Resources/scenarios/scripts/run-kql.sh denied
Student/Resources/scenarios/scripts/run-kql.sh flow-types
Student/Resources/scenarios/scripts/run-kql.sh public-ips
Student/Resources/scenarios/scripts/run-kql.sh sample-food-http-errors
Student/Resources/scenarios/scripts/run-kql.sh sample-food-latency
Student/Resources/scenarios/scripts/run-kql.sh sample-food-console
```

The same helper also accepts raw KQL for ad hoc investigation:

```bash
Student/Resources/scenarios/scripts/run-kql.sh "
Syslog
| where TimeGenerated > ago(15m)
| take 20"

Student/Resources/scenarios/scripts/run-kql.sh --query "
ContainerAppHTTPLogs
| where TimeGenerated > ago(15m)
| summarize count() by ContainerAppName"

Student/Resources/scenarios/scripts/run-kql.sh - < query.kql
```

Traffic Analytics ingestion is not immediate. The lab uses a 10-minute interval
for demo responsiveness.

## Fault Injection

NSG deny scenario:

```bash
Student/Resources/scenarios/scripts/trigger-nsg-block.sh
Student/Resources/scenarios/scripts/run-kql.sh denied
Student/Resources/scenarios/scripts/restore-nsg-block.sh
```

UDR asymmetry scenario:

```bash
Student/Resources/scenarios/scripts/trigger-udr-asymmetry.sh
Student/Resources/scenarios/scripts/restore-udr-asymmetry.sh
```

NGINX service-down scenario (guest-OS service failure detected via Azure Monitor
Agent / Syslog, Sev2 alert, Autonomous routing with a human-gated restart):

```bash
Student/Resources/scenarios/scripts/trigger-nginx-down.sh
Student/Resources/scenarios/scripts/run-kql.sh "Syslog | where TimeGenerated > ago(15m) | where SyslogMessage has 'nginx' | order by TimeGenerated desc"
Student/Resources/scenarios/scripts/restore-nginx.sh
```

## Demo Runbook

For the full, scenario-by-scenario demo script (6 scenarios with objective, value
narrative, exact commands, expected agent behavior, talk track, restore, and
troubleshooting), see [azure-sre-agent-demo-runbook.md](azure-sre-agent-demo-runbook.md).

## Architecture and Configuration

For the architecture and desired-state configuration of the Azure SRE Agent in this
project — how each configuration object works, when it intervenes, and why (connectors,
subagents, skills, tools, hooks, knowledge base), plus the reactive path (Azure Monitor
alerts to agent actions) and the proactive path (scheduled tasks) — see
[azure-sre-agent-architecture-and-configuration.md](azure-sre-agent-architecture-and-configuration.md).

## Use-Case Resource & Workflow Architecture

For a per-use-case breakdown — for each of the nine demo use cases (S1–S6 plus the three
proactive scheduled tasks P1–P3), which SRE Agent resources and sub-resources take part,
why each one generates engineering and business value, how the whole set collaborates
(one Mermaid per use case), and which desired-state sub-resources are left out and why —
see [azure-sre-agent-use-case-resource-architecture.md](azure-sre-agent-use-case-resource-architecture.md).

## SRE Agent Configuration

Validate and deploy the imported Sample Food skill/subagent:

```bash
Student/Resources/scenarios/scripts/sre-agent-config.sh validate --target skills --name sample-food-container-app-incident-analysis
Student/Resources/scenarios/scripts/sre-agent-config.sh validate --target subagents --name aca-app-incident-handler
```

For live apply, pass the existing Azure SRE Agent identifiers:

```bash
Student/Resources/scenarios/scripts/sre-agent-config.sh apply \
  --target skills \
  --name sample-food-container-app-incident-analysis \
  --subscription <subscription-id> \
  --resource-group <sre-agent-resource-group> \
  --agent <sre-agent-name>
```

## Important Boundaries

- `infra/` owns the lab Azure resources and the existing Azure SRE Agent root.
- `azure-sre-agent-config/` owns API-applied agent behavior such as skills and subagents.
- `docs/demo-lab/` owns demo-specific documentation.
- `docs/azure-sre-agent/` is intentionally not changed by this demo lab integration.

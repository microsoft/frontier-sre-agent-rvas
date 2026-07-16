**[Home](../README.md)** — [Next Challenge >](./Challenge-01.md)

# Challenge 00 — Prerequisites: Deploy the Lab & Configure the SRE Agent

## Introduction

Before any scenario can run, the Azure lab environment and the Azure SRE Agent must be fully provisioned and configured. This challenge walks you through deploying the complete infrastructure with Terraform and applying the SRE Agent desired-state configuration — skills, subagents, connectors, knowledge base, incident filters, and scheduled tasks.

The lab provisions a realistic Azure environment that the SRE Agent will monitor and operate: a hub-spoke network with Azure Firewall, IaaS VMs running a web/API/DB tier, VNet Flow Logs with Traffic Analytics, and a cloud-native food-ordering app (**Grubify**) on Azure Container Apps. The agent is configured with 6 scenarios worth of intelligence from day one.

## Description

### Step 1 — Authenticate

```bash
az login
az account set --subscription "<your-subscription-id>"
gh auth login   # needed for GitHub OAuth connector in Step 3
```

### Step 2 — Deploy infrastructure and configure the agent

From the `Coach/` directory:

```bash
make deploy
```

This runs:
1. `terraform init` + `terraform apply` inside `Coach/Solutions/infra/` — provisions all Azure resources
2. `make config-sre-agent` — runs the validate → plan → apply → verify cycle for the SRE Agent desired state

> If you prefer to run the steps separately:
> ```bash
> make infra           # terraform only
> make config-sre-agent   # agent config only
> ```

The `config-sre-agent` step applies:
- 8 skills (investigation playbooks)
- 7 subagents (specialist responders)
- 2 connectors (`github` OAuth, `microsoft-learn-mcp`)
- 1 repository link (`grubify`)
- 3 incident filters (domain-routed response plans)
- 5 scheduled tasks
- 18 knowledge-base documents

### Step 3 — Authorize the GitHub OAuth connector

After applying the config, you must complete a **one-time interactive OAuth authorization** so the agent can read source code and create GitHub issues and pull requests:

1. Open the SRE Agent portal: run `terraform -chdir=Coach/Solutions/infra output agent_portal_url`
2. In the portal, navigate to **Connectors → github**
3. Click **Authorize** and complete the GitHub OAuth sign-in

> Without this step, Challenges 02 and 03 will work for triage and investigation but the agent will not be able to create GitHub issues or pull requests.

### Step 4 — Generate baseline data

Run the baseline traffic script so VNet Flow Logs and Traffic Analytics have data for network scenarios (Challenges 05 and 06):

```bash
Student/Resources/scenarios/scripts/generate-baseline-traffic.sh
Student/Resources/scenarios/scripts/generate-sample-food-app-traffic.sh
```

## Pre-flight Validation Checklist

Run these checks before starting Challenge 01:

```bash
# 1. Azure CLI authenticated and correct subscription set
az account show --query "{name:name,id:id}" -o table

# 2. Terraform deployment succeeded
terraform -chdir=Coach/Solutions/infra output provisioning_state

# 3. SRE Agent portal URL
terraform -chdir=Coach/Solutions/infra output agent_portal_url

# 4. Scenario scripts executable
ls Student/Resources/scenarios/scripts/*.sh

# 5. Lab validation
Student/Resources/scenarios/scripts/validate.sh
Student/Resources/scenarios/scripts/validate-sample-food-app.sh
```

## Success Criteria

To complete this challenge, demonstrate:

1. `terraform output provisioning_state` returns `Succeeded`
2. `make config-sre-agent` (or the verify step) reports 0 failures
3. The SRE Agent portal shows all **7 subagents**, **8 skills**, and **3 incident filters** active
4. The GitHub `github` connector shows as connected (green) in the portal after OAuth authorization
5. `validate-sample-food-app.sh` returns a healthy status for the Grubify app
6. **Explain to your coach** — what is the difference between what Terraform manages (ARM resources) and what `sre-agent-config.sh` manages (data-plane desired state)? Why are they separate?

## Learning Resources

- [Azure SRE Agent overview](https://learn.microsoft.com/en-us/azure/sre-agent/overview)
- [Azure Container Apps overview](https://learn.microsoft.com/en-us/azure/container-apps/overview)
- [VNet Flow Logs overview](https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview)
- [Traffic Analytics overview](https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics)
- [Terraform AzAPI provider](https://registry.terraform.io/providers/Azure/azapi/latest)

## Tips

- `make deploy` takes ~15 minutes for a first-time run. The Container Apps environment is the slowest resource to provision.
- If `config-sre-agent` reports a failure, check that `az account show` returns the correct subscription — `terraform output` derives the agent endpoint automatically.
- The GitHub OAuth authorization step **must be done after** `config-sre-agent` applies the connector. If the portal shows "connector not found," re-run `make config-sre-agent`.
- **If `validate-sample-food-app.sh` fails** with a DNS/timeout error, wait 2–3 minutes and retry — the Container Apps ingress may still be warming up.

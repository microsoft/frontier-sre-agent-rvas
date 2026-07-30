**[Home](../README.md)** — [Next Challenge >](./Challenge-01.md)

# Challenge 00 — Prerequisites: Deploy the Lab & Create Your SRE Agent

## Introduction

Before the learning starts, two things must exist: the Azure lab infrastructure, and your SRE Agent. This challenge takes care of both.

You'll deploy the workload infrastructure with Terraform and then create your own Azure SRE Agent — an empty agent with no skills, no knowledge, no subagents, and no connectors. That emptiness is intentional. In Challenges 01 through 06 you will add each capability yourself, one at a time, and observe exactly what each addition unlocks. By the end of Challenge 06 you'll have built the fully configured agent from scratch — and you'll understand every piece of it.

The lab infrastructure includes: a hub-spoke network with Azure Firewall, IaaS VMs running a web/API/DB tier, VNet Flow Logs with Traffic Analytics, and the **Grubify** food-ordering app on Azure Container Apps. All of this is provisioned by Terraform — the SRE Agent creation and configuration are entirely up to you.

## Description

### Step 1 — Authenticate

```bash
az login
az account set --subscription "<your-subscription-id>"
```

### Step 2 — Deploy the lab workload infrastructure

From the `Student/` directory:

```bash
cd Student && make deploy
```

This runs `terraform init` + `terraform apply` inside `Student/Resources/infra/`. It provisions all Azure workload resources (hub-spoke network, VMs, Grubify app, Parking Manager) but does **not** create an SRE Agent.

> First-time deployment takes approximately **15–20 minutes**. The Container Apps environment is the slowest resource to provision.

### Step 3 — Create your SRE Agent

Before creating the agent, ensure the `Microsoft.App` resource provider is registered in your subscription:

```bash
az provider register --namespace "Microsoft.App"
```

Then create the agent via the **SRE Agent portal**:

1. Go to [https://sre.azure.com](https://sre.azure.com) and sign in.
2. Select **Create agent**.
3. Fill in: subscription, resource group, agent name, and region (i.e. Sweden Central).
4. On **Resource groups**, add **all** of the following resource groups so the agent has visibility across the entire lab:

   ```bash
   # Print the full list from Terraform outputs
   cd Student
   terraform -chdir="Resources/infra" output -json parking_resource_groups
   terraform -chdir="Resources/infra" output hub_resource_group_name
   ```

   The resource groups to associate are:
   - `rg-hub` — hub network and Azure Firewall
   - `rg-sre-spoke-web-api` — Grubify web and API VMs
   - `rg-sre-spoke-data` — Grubify database VM
   - `rg-sre-spoke-foodapp-paas` — Sample Food / Grubify Container Apps
   - `rg-sre-parking-lisbon` — Parking Manager Lisbon API
   - `rg-sre-parking-berlin` — Parking Manager Berlin API and MCP server
   - `rg-sre-parking-madrid` — Parking Manager Madrid API (Windows VM)
   - `rg-sre-parking-paris` — Parking Manager Paris API (Ubuntu VM)
   - `rg-sre-parking-chaos` — Parking Manager chaos control plane

   > **If you skip any resource group the agent will be blind to that workload.** Challenges 07–18 span all of these resource groups — missing even one means the agent cannot query logs, metrics, or take remediation actions in that segment.

5. Set permission level to **Contributor**.

   > **Why Contributor, not Reader?** Challenges 11–15 require the agent to perform write actions — restarting VMs, deleting NSG rules, and removing UDRs. Reader permission allows investigation only; Contributor is required for autonomous remediation. All write actions are gated by skill tool grants and safety policies, so Contributor does not give the agent unconstrained access.

6. Select **Create** and wait for deployment.

Once provisioned, copy the **agent name** and **resource group** — you'll need them in the next step.

### Step 4 — Configure your .env file

All subsequent `make` commands need to know your agent's resource group and name. Set them once now:

```bash
cd Student
cp .env.example .env
# Edit .env and fill in SRE_AGENT_RG and SRE_AGENT_NAME
```

### Step 5 — Generate baseline telemetry data

Start traffic generation so monitoring data exists before you reach the operational challenges:

```bash
make baseline-traffic
make food-traffic
```

`make baseline-traffic` runs a traffic burst on the IaaS VMs via a remote run-command (takes 2–4 minutes). `make food-traffic` hits the Grubify API endpoints and completes in seconds.

### Step 6 — Validate the lab

```bash
# Lab infrastructure health
make validate
make validate-food
```

## Pre-flight Validation Checklist

Before continuing to Challenge 01, confirm every check below passes:

```bash
# 1. Azure CLI is installed and authenticated
az account show --query "{name:name,id:id,state:state}" -o table

# 2. Terraform is installed
terraform -chdir="Resources/infra" version

# 3. GitHub CLI is installed (needed from Challenge 01 onwards)
gh --version

# 4. Lab infrastructure is healthy
make validate
make validate-food

All four checks must succeed before proceeding. If `make validate` fails, re-run `make deploy`. If `make validate-food` fails, run `make food-status` to check the Grubify Container Apps revision state.

## Success Criteria

1. `make deploy` completes successfully and all workload resources are provisioned
2. The SRE Agent resource exists in your resource group and the portal loads
3. All 9 lab resource groups are associated with the agent in the portal
4. The agent permission level is **Contributor**
5. `Student/.env` is configured with your `SRE_AGENT_RG` and `SRE_AGENT_NAME`
6. Both `validate.sh` and `validate-sample-food-app.sh` return healthy
7. **Explain to your coach** — why does the SRE Agent require Contributor permission instead of Reader? What specific actions in later challenges require write access, and what governance controls prevent the agent from taking unconstrained write actions?

## Learning Resources

- [Azure SRE Agent overview](https://learn.microsoft.com/en-us/azure/sre-agent/overview)
- [Azure Container Apps overview](https://learn.microsoft.com/en-us/azure/container-apps/overview)
- [VNet Flow Logs overview](https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview)
- [Terraform AzAPI provider](https://registry.terraform.io/providers/Azure/azapi/latest)

## Tips

- Run **only** `make deploy` here.
- Run `make baseline-traffic` and `make food-traffic` before proceeding to Challenge 01. VNet Flow Logs and Traffic Analytics data accumulate over time and are needed for Challenges 12–18.

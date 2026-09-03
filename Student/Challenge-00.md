**[Home](../README.md)** — [Next Challenge >](./Challenge-01.md)

# Challenge 00 — Prerequisites: Deploy the Lab and Create Your SRE Agent

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

This runs `terraform init` + `terraform apply` against the Student Terraform root at `Student/Resources/infra/`, then points the Grubify container apps at the published images. It provisions the workload only. Creating the Azure SRE Agent is your job, in Step 3.

> First-time deployment takes approximately **15–20 minutes**. The Container Apps environment is the slowest resource to provision.

### Step 3 — Create your Azure SRE Agent

Before creating the agent, ensure the `Microsoft.App` resource provider is registered in your subscription:

```bash
az provider register --namespace "Microsoft.App"
```

Create the agent yourself in the **SRE Agent portal**. It is deliberately not part of the Terraform
you just applied: building it, and then filling it with capabilities in Challenges 01 to 06, is the
point of this workshop.

1. Go to [https://sre.azure.com](https://sre.azure.com) and sign in.
2. Create an agent in a resource group of your choice, in **Sweden Central**, the same region as the
   workload you just deployed.
3. Confirm that its provisioning state is `Succeeded` and its power state is `Running`.
4. Associate the four workload resource groups with the agent and give it **Contributor** permission.
5. Print the resource groups the agent must watch, from the `Student/` directory:

   ```bash
   terraform -chdir="Resources/infra" output hub_resource_group_name
   terraform -chdir="Resources/infra" output web_api_resource_group_name
   terraform -chdir="Resources/infra" output data_resource_group_name
   terraform -chdir="Resources/infra" output sample_food_resource_group_name
   ```

   The certified profile is scoped to:
   - `rg-sre-hub-connectivity` — hub network, Azure Firewall, Bastion, and shared observability
   - `rg-sre-spoke-web-api-iaas` — client and web VMs
   - `rg-sre-spoke-data-iaas` — API and database VMs
   - `rg-sre-spoke-foodapp-paas` — Sample Food / Grubify Container Apps

The network analyst and the proactive scheduled tasks stay read-only even though the agent holds
broader permissions for the remediation scenarios.

### Step 4 — Configure your .env file

Every `make` target that talks to the agent needs to know where it is. Record it once:

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
2. You created the SRE Agent yourself and the portal loads it
3. All lab resource groups are associated with the agent in the portal
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

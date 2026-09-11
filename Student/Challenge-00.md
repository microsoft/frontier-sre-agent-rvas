**[Home](../README.md)** — [Next Challenge >](./Challenge-01.md)

# Challenge 00 — Prerequisites: Deploy the Lab and Create Your SRE Agent

> **Application focus:** Grubify (Sample Food) and Parking Manager

## Introduction

Before the learning starts, three things must exist: your own fork of this repository, the Azure lab infrastructure, and your SRE Agent. This challenge takes care of all three.

You'll deploy the workload infrastructure with Terraform and then create your own Azure SRE Agent. In Challenges 01 through 06 you will add capabilities to the agent, one at a time, and observe exactly what each addition unlocks. By the end of Challenge 06 you'll have built the fully configured agent from scratch.

The lab infrastructure includes: a hub-spoke network with Azure Firewall, IaaS VMs running a web/API/DB tier, VNet Flow Logs with Traffic Analytics, the **Grubify** food-ordering app on Azure Container Apps, and the containerized **Parking Manager** solution. The Parking Manager frontend, Madrid VM, and Paris VM share a dedicated Parking VNet, isolated from the Web/API IaaS VNets and their NSGs and routes. This VNet is not peered with the hub and does not use the firewall; the VMs use their own NAT Gateway for outbound access, while the frontend uses a UDR-free integration subnet to reach the private VM-hosted APIs. All of this is provisioned by Terraform.

> **Note:** The SRE Agent creation and configuration are entirely up to you.

## Description

### Step 1 — Fork and clone the repository

Sign in to GitHub and open the canonical workshop repository:

[https://github.com/microsoft/frontier-sre-agent-rvas](https://github.com/microsoft/frontier-sre-agent-rvas)

1. Select **Fork** in the upper-right corner.
2. Choose your GitHub account as the owner and select **Create fork**.
3. On your fork, select **Code** and copy its HTTPS URL.
4. Clone your fork and enter the repository directory:

   ```bash
   git clone https://github.com/<your-github-username>/frontier-sre-agent-rvas.git
   cd frontier-sre-agent-rvas
   ```

Before continuing, enable GitHub Issues on your fork. Later challenges create incident-tracking
issues in this repository:

1. Open your fork on [GitHub.com](https://github.com) and select **Settings**.
2. On the **General** settings page, scroll to **Features**.
3. Select the **Issues** checkbox.

### Step 2 — Authenticate to Azure

```bash
az login
az account set --subscription "<your-subscription-id>"
```

### Step 3 — Deploy the lab workload infrastructure

From the repository root, enter `Student/` and deploy:

```bash
cd Student
make deploy
```

Stay in `Student/` for the remaining steps. The default deployment location is `swedencentral`.
To use a different region, run this instead of the default `make deploy` command:

```bash
make deploy TF_VARS='-var="location=your_preferred_region_here"'
```

This runs `terraform init` and `terraform apply` against `Student/Resources/infra/`. Terraform deploys the workloads using published container images. It does not create the SRE Agent.

> First-time deployment takes approximately **15–20 minutes**.

### Step 4 — Create your Azure SRE Agent

Before creating the agent, ensure the `Microsoft.App` resource provider is registered in your subscription:

```bash
az provider register --namespace "Microsoft.App"
```

1. Go to [https://sre.azure.com](https://sre.azure.com) and sign in.
2. Create an agent in a resource group of your choice, in the same region as the
   workload you just deployed (e.g., the default is **Sweden Central**, but you can choose another region if desired).
3. Confirm that its provisioning state is `Succeeded` and its power state is `Running`.
4. Print the resource groups the agent must watch, from the `Student/` directory:

   ```bash
   terraform -chdir="Resources/infra" output hub_resource_group_name
   terraform -chdir="Resources/infra" output web_api_resource_group_name
   terraform -chdir="Resources/infra" output data_resource_group_name
   terraform -chdir="Resources/infra" output sample_food_resource_group_name
   terraform -chdir="Resources/infra" output parking_resource_groups
   ```

   The certified profile is scoped to:
   - `rg-sre-hub-connectivity` — hub network, Azure Firewall, Bastion, and shared observability
   - `rg-sre-spoke-web-api-iaas` — client and web VMs
   - `rg-sre-spoke-data-iaas` — API and database VMs
   - `rg-sre-spoke-foodapp-paas` — Sample Food / Grubify Container Apps
   - `rg-sre-parking-lisbon` — Lisbon Parking API
   - `rg-sre-parking-berlin` — Berlin Parking API and MCP server
   - `rg-sre-parking-madrid` — Madrid Parking VM
   - `rg-sre-parking-paris` — Paris Parking VM
   - `rg-sre-parking-chaos` — Chaos Control and VM Health Control
   - `rg-sre-parking-frontend` — public Parking Manager Web App and App Service plan
5. Associate all workload resource groups with the agent and give it **Contributor** permission.

### Step 5 — Configure your .env file

Every `make` target that talks to the agent needs to know where it is. From `Student/`, record it once:

```bash
cp .env.example .env
# Edit .env and fill in SRE_AGENT_RG and SRE_AGENT_NAME
```

### Step 6 — Generate baseline telemetry data

Start traffic generation so monitoring data exists before you reach the operational challenges:

```bash
make baseline-traffic
make food-traffic
make parking-traffic
```

`make baseline-traffic` runs a traffic burst on the IaaS VMs via a remote run-command (takes 2–4 minutes). `make food-traffic` hits the Grubify API endpoints. `make parking-traffic` sends requests through the public Parking Manager frontend to the Lisbon, Madrid, Paris, and Berlin APIs and the control services.

### Step 7 — Validate the lab

```bash
# Lab infrastructure health
make validate
make validate-food
make validate-parking
```

## Success Criteria

1. You created your own fork
2. `make deploy` completes successfully and all workload resources are provisioned
3. You created the SRE Agent yourself and the portal loads it
4. All lab resource groups are associated with the agent in the portal
5. The agent permission level is **Contributor**
6. `Student/.env` is configured with your `SRE_AGENT_RG` and `SRE_AGENT_NAME`
7. `make validate`, `make validate-food`, and `make validate-parking` return healthy
8. **Explain to your coach** — why does the SRE Agent require Contributor permission instead of Reader? What specific actions in later challenges require write access, and what governance controls prevent the agent from taking unconstrained write actions?

## Learning Resources

- [Fork a repository](https://docs.github.com/en/get-started/quickstart/fork-a-repo)
- [Azure SRE Agent overview](https://learn.microsoft.com/en-us/azure/sre-agent/overview)
- [Azure Container Apps overview](https://learn.microsoft.com/en-us/azure/container-apps/overview)
- [VNet Flow Logs overview](https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview)
- [Terraform AzAPI provider](https://registry.terraform.io/providers/Azure/azapi/latest)

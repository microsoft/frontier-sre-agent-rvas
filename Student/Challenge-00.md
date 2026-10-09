**[Home](../README.md)** — [Next Challenge >](./Challenge-01.md)

# Challenge 00 — Prerequisites: Deploy the Lab and Create Your SRE Agent

> **Application focus:** Grubify (Sample Food) and Parking Manager

## Introduction

Before the learning starts, three things must exist: your own fork of this repository, the Azure lab infrastructure, and your SRE Agent. This challenge takes care of all three.

You'll deploy the workload infrastructure with Terraform and then create your own Azure SRE Agent. In Challenges 01 through 06 you will add capabilities to the agent, one at a time, and observe exactly what each addition unlocks. By the end of Challenge 06 you'll have built the fully configured agent from scratch.

The lab infrastructure includes: a hub-spoke network with Azure Firewall, IaaS VMs running a web/API/DB tier, VNet Flow Logs with Traffic Analytics, the **Grubify** food-ordering app on Azure Container Apps, and the containerized **Parking Manager** solution. The Parking Manager frontend, Madrid VM, and Paris VM share a dedicated Parking VNet, isolated from the Web/API IaaS VNets and their NSGs and routes. This VNet is not peered with the hub and does not use the firewall; the VMs use their own NAT Gateway for outbound access, while the frontend uses a UDR-free integration subnet to reach the private VM-hosted APIs. All of this is provisioned by Terraform.

> **Note:** The SRE Agent creation and configuration are entirely up to you.

## Description

Before cloning or deploying, read the shared
[Requirements and environment guide](../README.md#requirements). All workshop
commands run in **Linux Bash**. Codespaces on your own fork is recommended;
WSL2/Ubuntu and local Linux Dev Containers are alternatives.

### Step 1 — Fork and clone the repository

Sign in to GitHub and open the canonical workshop repository:

[https://github.com/microsoft/frontier-sre-agent-rvas](https://github.com/microsoft/frontier-sre-agent-rvas)

1. Select **Fork** in the upper-right corner.
2. Choose your GitHub account as the owner and select **Create fork**.
3. For **Codespaces**, select **Code → Codespaces → Create codespace** on your
   fork. Wait for setup/local checks to finish, then use its Linux terminal.
   Your fork is already checked out; skip the clone command below.
4. For **WSL2/native Linux**, copy your fork's HTTPS URL, clone it under your
   Linux home directory, and enter it. For a local Dev Container, reopen the
   clone in the container before running workshop commands:

   ```bash
   git clone https://github.com/<your-github-username>/frontier-sre-agent-rvas.git
   cd frontier-sre-agent-rvas
   ```

Check `git remote -v`: `origin` must be your fork. If `upstream` is absent, add
`https://github.com/microsoft/frontier-sre-agent-rvas.git` as the upstream remote.
Do not run deployment commands in PowerShell, CMD, or Git Bash.

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

For a remote terminal where browser login is unavailable, use
`az login --use-device-code`. Codespaces/GitHub login is separate from Azure
login. Run the pre-flight checks below before continuing.

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

`make deploy` gates Terraform on shared pre-flight checks. Correct every `FAIL`
and review every `WARN` with your coach; a warning is not proof of readiness.
For region/VM overrides, use the same `TF_VARS` for pre-flight and deployment.

### Step 4 — Create your Azure SRE Agent

Before creating the agent, ensure the `Microsoft.App` resource provider is registered in your subscription:

```bash
az provider register --namespace "Microsoft.App"
```

1. Go to [https://sre.azure.com](https://sre.azure.com) and sign in.
2. Create an agent in a resource group of your choice, in the same region as the
   workload you just deployed (e.g., the default is **Sweden Central**, but you can choose another region if desired).
3. Confirm that its provisioning state is `Succeeded` and its power state is `Running`.
4. Print the shared resource group the agent must watch, from the `Student/` directory:

   ```bash
   terraform -chdir="Resources/infra" output rvas_resource_group_name
   ```
   
5. Associate the workload resource group with the agent and give it **Contributor** permission.

   > **Least-privilege VM repair:** Contributor is the certified full-workshop baseline because later challenges also modify NSGs and UDRs. If your organization gives the agent narrower access and VM remediation later fails authorization, an **Owner** or **Role Based Access Control Administrator** can run `make grant-agent-vm-remediation`. This adds only VM read, restart, and Run Command permissions on resource groups that contain lab VMs; it is not sufficient for the network-remediation challenges.

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

## Pre-flight Validation Checklist

Before Step 3, run these commands from the repository root in **Linux Bash**.
The local check can run before Azure login; the full check runs after Step 2:

```bash
git remote -v
bash --version
make --version
terraform version
cd Student
make preflight PREFLIGHT_ARGS=--local
az account show --query "{name:name,id:id,state:state}" -o table
make preflight
# If choosing a different region, check the exact same override you will deploy:
# make preflight TF_VARS='-var="location=uksouth"'
```

Every confirmed failure must be resolved. Ask your coach to verify deployment
and role-assignment rights, regional capacity, Network Watcher, and any checks
reported as unverifiable. No check changes Azure resources. Use `make validate*`
only after deployment to check workload health.

Keep `Resources/infra` Terraform state and `.env` private. Preserve them before
deleting a Codespace. At the end, destroy the lab using the same Student state
and separately remove your manually created agent; stopping Codespaces does not
stop Azure billing. See [cleanup guidance](../README.md#costs-state-and-cleanup).

## Success Criteria

1. You created your own fork
   and confirmed Linux pre-flight readiness, with all failures resolved and
   warnings reviewed with your coach
2. `make deploy` completes successfully and all workload resources are provisioned
3. You created the SRE Agent yourself and the portal loads it
4. The workload resource group is associated with the agent in the portal
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

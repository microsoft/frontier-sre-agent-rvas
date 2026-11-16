---
title: Prerequisites & Lab Setup
summary: Deploy the workloads with Terraform, create your Azure SRE Agent, and generate baseline traffic. Add the agent's capabilities in Challenges 01–06.
phase: Setup
group: Setup
tags:
- terraform
- az sre-agent create
- VNet Flow Logs
highlight: true
---

# Challenge 00 — Prerequisites: Deploy the Lab and Create Your SRE Agent

> **Application focus:** Grubify (Sample Food) and Parking Manager

## Purpose

- Set up the baseline: your own fork, Linux pre-flight checks, Azure sign-in, the workload deployment, a reachable Azure SRE Agent, and validation.
- You create the agent manually in the portal. `make deploy` provisions only the workloads; Challenges 01 through 06 add the agent's capabilities.
- Expected time: 30–45 minutes.

Before you start, read the shared [Requirements](../../../README.md#requirements) and
[Environment readiness checklist](../README.md#before-you-start-environment-readiness).
Confirm you are in Linux Bash and review the `make preflight` output before deploying any infrastructure.

## Introduction

Fork this repository, deploy the Azure lab infrastructure with Terraform, and create your SRE Agent yourself. In Challenges 01 through 06, add capabilities one at a time and compare what the agent can do before and after each addition.

The lab infrastructure includes: a hub-spoke network with Azure Firewall, IaaS VMs running a web/API/DB tier, VNet Flow Logs with Traffic Analytics, the **Grubify** food-ordering app on Azure Container Apps, and the containerized **Parking Manager** solution. The Parking Manager frontend, Madrid VM, and Paris VM share a dedicated Parking VNet, isolated from the Web/API IaaS VNets and their NSGs and routes. This VNet is not peered with the hub and does not use the firewall; the VMs use their own NAT Gateway for outbound access, while the frontend uses a UDR-free integration subnet to reach the private VM-hosted APIs. Terraform provisions all of it.

## Description

Before cloning or deploying, read the shared
[Requirements and environment guide](../../../README.md#requirements). All workshop
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

From the repository root, enter `labs/01-azure-operations/` and deploy:

```bash
cd labs/01-azure-operations
make deploy
```

Stay in `labs/01-azure-operations/` for the remaining steps. The default deployment location is `swedencentral`.
To use a different region, run this instead of the default `make deploy` command:

```bash
make deploy TF_VARS='-var="location=your_preferred_region_here"'
```

This runs `terraform init` and `terraform apply` against `labs/01-azure-operations/resources/infra/`. Terraform deploys the workloads using published container images. It does not create the SRE Agent.

> First-time deployment takes approximately **15–20 minutes**.

`make deploy` runs the shared pre-flight checks before Terraform. Fix every `FAIL`
and review every `WARN`; a warning does not mean you are ready.
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
4. Print the shared resource group the agent must watch, from the `labs/01-azure-operations/` directory:

   ```bash
   terraform -chdir="resources/infra" output rvas_resource_group_name
   ```
   
5. Associate the workload resource group with the agent and give it **Contributor** permission.

   > **Least-privilege VM repair:** Contributor is the certified full-workshop baseline because later challenges also modify NSGs and UDRs. If your organization gives the agent narrower access and VM remediation later fails authorization, an **Owner** or **Role Based Access Control Administrator** can run `make grant-agent-vm-remediation`. This adds only VM read, restart, and Run Command permissions on resource groups that contain lab VMs; it is not sufficient for the network-remediation challenges.

### Step 5 — Configure your .env file

Every `make` target that talks to the agent needs to know where it is. From `labs/01-azure-operations/`, record it once:

```bash
cp .env.example .env
# Edit .env and fill in SRE_AGENT_RG and SRE_AGENT_NAME
chmod 600 .env
```

The config scripts refuse to read `.env` unless only you can read it, so keep the `chmod 600`.

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
cd labs/01-azure-operations
make preflight PREFLIGHT_ARGS=--local
az account show --query "{name:name,id:id,state:state}" -o table
make preflight
# If choosing a different region, check the exact same override you will deploy:
# make preflight TF_VARS='-var="location=uksouth"'
```

Resolve every confirmed failure. Verify deployment and role-assignment rights,
regional capacity, Network Watcher, and any checks reported as unverifiable.
No check changes Azure resources. Use `make validate*` only after deployment,
to check workload health.

Keep the `resources/infra` Terraform state and `.env` private, and preserve them before
deleting a Codespace. At the end, destroy the lab using the same Terraform state
and separately remove your manually created agent; stopping Codespaces does not
stop Azure billing. See [cleanup guidance](../../../README.md#costs-state-and-cleanup).

## Success Criteria

1. You created your own fork
   and confirmed Linux pre-flight readiness, with all failures resolved and
   warnings reviewed
2. `make deploy` completes successfully and all workload resources are provisioned
3. You created the SRE Agent yourself and the portal loads it
4. The workload resource group is associated with the agent in the portal
5. The agent permission level is **Contributor**
6. `labs/01-azure-operations/.env` is configured with your `SRE_AGENT_RG` and `SRE_AGENT_NAME`
7. `make validate`, `make validate-food`, and `make validate-parking` return healthy
8. **Explain in your own words** (two or three written sentences) — why does the SRE Agent require Contributor permission instead of Reader? What specific actions in later challenges require write access, and what governance controls prevent the agent from taking unconstrained write actions?

## Learning Resources

- [Fork a repository](https://docs.github.com/en/get-started/quickstart/fork-a-repo)
- [Azure SRE Agent overview](https://learn.microsoft.com/en-us/azure/sre-agent/overview)
- [Azure Container Apps overview](https://learn.microsoft.com/en-us/azure/container-apps/overview)
- [VNet Flow Logs overview](https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview)
- [Terraform AzAPI provider](https://registry.terraform.io/providers/Azure/azapi/latest)

## Hints and notes

> Hidden until you click. Expand a section only when you want it.

<details>
<summary><strong>Background</strong></summary>

- The lab arc: a manually created base agent, then data-plane capabilities added step by step. The agent is the one control-plane resource you create by hand. You add knowledge, skills, subagents, repositories, and automations yourself in later challenges.
- Dependency chain: fork and clone → Azure authentication → `make deploy` (workload only) → manual agent creation in the portal → resource-group association + Contributor role → baseline traffic → workload validation.
- Your fork must be `origin` and the Microsoft repository `upstream`. Later configuration derives `GRUBIFY_REPO_URL` from `origin`, so you and SRE Agent workflows can push branches and open pull requests against a repository you own.
- GitHub Issues must be enabled on your fork: open it on GitHub.com, select **Settings** → **General**, scroll to **Features**, and select **Issues**. Later incident-automation challenges create issues there.
- Allow time for the Container Apps environment and monitoring setup.
- Three validation targets cover the workloads: `make validate` for VNet Flow Logs and the virtual machine lab, `make validate-food` for Grubify, and `make validate-parking` for the public Parking Manager Web App, its VNet integration, and proxied APIs.

</details>

<details>
<summary><strong>Expected Output</strong></summary>

- You created and cloned your own fork. `origin` points to that fork and `upstream` points to `microsoft/frontier-sre-agent-rvas`.
- GitHub Issues are enabled on your fork.
- `make deploy` completes from `labs/01-azure-operations/` and provisions the workload only.
- You resolved all prerequisite failures and reviewed warnings.
- You created the SRE Agent yourself in the portal, associated the workload resource group, and granted it Contributor.
- `labs/01-azure-operations/.env` is filled in with `SRE_AGENT_RG` and `SRE_AGENT_NAME` so later `make` targets can reach the agent.
- Baseline traffic completes via the scenario targets.
- The infrastructure, Grubify, and Parking Manager validation targets return healthy.

</details>

<details>
<summary><strong>Common Issues and Hints</strong></summary>

- **Symptom:** `make: command not found`, `terraform: command not found`, or `Required command not found: jq`. **Fix:** confirm the terminal is inside Linux/WSL/the container; rebuild the Dev Container or install the shared Requirements inside Ubuntu, not only on Windows.
- **Symptom:** `Required YAML parser not found` or `yq` rejects `-o=json`. **Fix:** install `python3-yaml` or the Mike Farah yq implementation; arbitrary packages named yq are not compatible.
- **Symptom:** `envsubst: command not found` or `timeout: command not found`. **Fix:** install `gettext-base` and GNU `coreutils` inside the active Linux environment.
- **Symptom:** `/usr/bin/env: 'bash\r': No such file or directory` or shell errors containing `$'\r'`. **Fix:** check out scripts with LF endings (repository attributes enforce this on fresh checkouts); do not run CRLF shell scripts. Use WSL2, not a Windows Bash shim, and verify Linux tool paths with `command -v`.
- **Symptom:** Codespaces creation is denied or quota is exhausted. **Fix:** confirm organization policy and billing entitlement; use the documented WSL2/local Dev Container fallback.
- **Symptom:** Terraform uses a different subscription/tenant from the CLI. **Fix:** align `az account show` with `ARM_SUBSCRIPTION_ID`/`ARM_TENANT_ID` and reauthenticate in the Linux terminal. Do not share tokens to fix access.
- **Symptom:** pre-flight reports insufficient vCPU quota or an unverifiable permission/provider check. **Fix:** have the subscription owner verify the exact regional profile, available Standard_B2s_v2-family and regional quota, provider registration, and role-assignment rights; do not treat WARN as PASS.
- **Symptom:** Later Code Access or pull-request workflows target the Microsoft repository or cannot push a branch. **Fix:** run `git remote -v`; confirm `origin` points to your fork and `upstream` points to `https://github.com/microsoft/frontier-sre-agent-rvas.git`.
- **Symptom:** A later incident workflow cannot create a GitHub issue, or the fork has no **Issues** tab. **Fix:** open the fork's **Settings** → **General** → **Features** and enable **Issues**.
- **Symptom:** `make deploy` fails early with Azure authentication or subscription errors. **Fix:** verify `az account show`, select the intended subscription, and rerun the Terraform plan before applying.
- **Symptom:** Terraform reports that `NetworkWatcher_<region>` was not found in `NetworkWatcherRG`. **Fix:** enable Network Watcher manually for the same region passed to Terraform, then rerun `make deploy`:

	```bash
	az network watcher configure \
		--resource-group NetworkWatcherRG \
		--locations <region> \
		--enabled true
	```

	For example, use `--locations uksouth` when deploying with `TF_VARS='-var="location=uksouth"'`. Terraform intentionally reads the regional Network Watcher but does not create or manage it.
- **Symptom:** Terraform attempts to create resources that already exist outside its state. **Fix:** stop the apply and run `make drift` from `labs/01-azure-operations/`, passing the same `TF_VARS` used for deployment when applicable. This read-only comparison lists resources deployed in the workshop resource group but missing from local state, plus state entries not returned by Azure. It also generates `terraform import` commands when a deployed resource uniquely matches a planned Terraform address. Verify each candidate's ownership and configuration before running the suggested command; do not create duplicates or import unrelated resources.
- **Symptom:** Terraform fails creating the Parking App Service plan with a 409 and no capacity for B1. **Fix:** deploy with a different SKU, for example `make deploy TF_VARS='-var="parking_frontend_sku=B2"'`. B2 is the default.
- **Symptom:** The first apply fails with "diagnostic setting already exists". **Fix:** import the existing setting into state with `terraform -chdir=resources/infra import <address> <resource-id>`, using the address and ID from the error, then rerun `make deploy`.
- **Symptom:** `make validate-parking` reports Madrid returning HTTP 502. **Fix:** the Madrid VM downloads its API source from `parking_source_base_url`. If you run from a fork or branch, deploy with `-var="parking_source_base_url=https://raw.githubusercontent.com/<owner>/<repo>/<branch>/labs/01-azure-operations/resources/parking-manager/backend"`.
- **Symptom:** `sre-agent-config.sh` fails with "Environment file ... has mode 644". **Fix:** run `chmod 600 .env`.
- **Symptom:** The agent portal URL returns an error immediately after creation. **Fix:** confirm `provisioning_state` and power state, then allow a short control-plane propagation interval before retrying.
- **Symptom:** A later lab target cannot resolve the agent name or resource group. **Fix:** confirm `labs/01-azure-operations/.env` has `SRE_AGENT_RG` and `SRE_AGENT_NAME` set, matching the agent created in the portal.
- **Symptom:** Infrastructure validation succeeds but Grubify is unhealthy. **Fix:** generate food traffic, inspect `make food-status`, and check the active Container Apps revision before redeploying.
- **Symptom:** `make validate-parking` reports an unhealthy proxy endpoint. **Fix:** inspect the named endpoint, confirm the Web App has VNet integration for private VM APIs, and verify route-all remains disabled for public API access.
- **Symptom:** Traffic Analytics is empty in later challenges. **Fix:** ensure baseline traffic ran successfully and allow for the documented ingestion interval.
- **Symptom:** The agent can diagnose a workload but cannot perform an expected write action. **Fix:** confirm the agent's role assignment on the associated resource group is Contributor, not Reader.

</details>

<details>
<summary><strong>Debrief Discussion Guide</strong></summary>

- Why is the agent created by hand instead of by Terraform, when every later challenge is scripted? → It shows you every capability the agent starts without, before you add each one in Challenges 01–06.
- Why start traffic generators before the operational labs? → Many later challenges fail silently without telemetry history.
- What is the risk of an agent with excess or missing role assignments? → Missing assignments block expected remediation; excess assignments widen the blast radius beyond what the lab's governance model assumes.
- Which delays affected this deployment? → Discuss infrastructure provisioning and telemetry ingestion separately.

</details>

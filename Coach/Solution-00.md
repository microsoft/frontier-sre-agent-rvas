**[Home](./README.md)** | [Next Solution >](./Solution-01.md)

# Coach Guide — Challenge 00: Prerequisites: Deploy the Lab & Create Your SRE Agent

> **Application focus:** Grubify (Sample Food) and Parking Manager

## Purpose

- Establish the baseline: a student-owned repository fork, Linux pre-flight readiness, Azure authentication, Student workload Terraform deployment, a reachable Azure SRE Agent, and working validation.
- Students manually create the control-plane agent in the portal (Terraform intentionally does not create it for Student's root); `make deploy` in this challenge only provisions the workload every later data-plane capability depends on, and Challenges 01 through 06 build the data plane.
- Expected time: 30–45 minutes.

Use the shared [Requirements](../README.md#requirements) and
[Coach readiness checklist](./README.md#before-the-event-environment-readiness)
before teaching. Confirm Linux Bash and review `make preflight` output before
any infrastructure deployment. The Student uses the Student Terraform root,
not the Coach reference deployment.

## Mini-Lecture (5–7 min before challenge)

- Workshop arc: **manual base agent → progressively add data-plane capabilities**. Make students distinguish the control-plane resource they create by hand from knowledge, skills, subagents, repositories, and automations, all of which they add themselves in later challenges.
- Dependency chain to draw: fork and clone the repository → Azure authentication → `make deploy` (workload only) → manual agent creation in the portal → resource-group association + Contributor role → baseline traffic → workload validation.
- Explain the remote layout: the student's fork must be `origin`, while the Microsoft repository is `upstream`. Later configuration derives `GRUBIFY_REPO_URL` from `origin`, allowing the student and SRE Agent workflows to push branches and open pull requests against a repository the student owns.
- Ensure GitHub Issues are enabled on the student's fork: open the fork on GitHub.com, select **Settings** → **General**, scroll to **Features**, and select **Issues**. Later incident-automation challenges create issues in this repository.
- Call out slow resources: Container Apps environment and monitoring plumbing are the usual long pole.
- Emphasize that the Student Terraform root deliberately does **not** create the SRE Agent — `make deploy` provisions only the workload. Creating the agent by hand and associating it with the workload resource group is the point of Step 4 in Challenge 00.
- Note the Coach environment is different: `Coach/` runs its own Terraform root (`Solutions/infra`), which additionally deploys a Coach-owned reference agent via `module "sre_agent"` (`make infra` from `Coach/`). This lets a coach stand up a fully wired reference environment for demos and answer-checking without doing the manual portal steps every time — it is not what students do, and should not be presented to students as an alternative.
- Show the three workload validation surfaces: `make validate` for VNet Flow Logs and the virtual machine lab, `make validate-food` for Grubify, and `make validate-parking` for the public Parking Manager Web App, its VNet integration, and proxied APIs.

## Expected Student Output

- The student created and cloned their own fork. `origin` points to that fork and `upstream` points to `microsoft/frontier-sre-agent-rvas`.
- GitHub Issues are enabled on the student's fork.
- `make deploy` completes from `Student/` and provisions the workload only.
- The student resolved all prerequisite failures and reviewed warnings with a coach.
- The student created the SRE Agent themselves in the portal, associated the workload resource group, and granted it Contributor.
- `Student/.env` is filled in with `SRE_AGENT_RG` and `SRE_AGENT_NAME` so later `make` targets can reach the agent.
- Baseline traffic completes via the Student scenario targets.
- The Student infrastructure, Grubify, and Parking Manager validation targets return healthy.

## Common Issues and Hints

- **Symptom:** `make: command not found`, `terraform: command not found`, or `Required command not found: jq`. **Fix:** confirm the terminal is inside Linux/WSL/the container; rebuild the Dev Container or install the shared Requirements inside Ubuntu, not only on Windows.
- **Symptom:** `Required YAML parser not found` or `yq` rejects `-o=json`. **Fix:** install `python3-yaml` or the Mike Farah yq implementation; arbitrary packages named yq are not compatible.
- **Symptom:** `envsubst: command not found` or `timeout: command not found`. **Fix:** install `gettext-base` and GNU `coreutils` inside the active Linux environment.
- **Symptom:** `/usr/bin/env: 'bash\r': No such file or directory` or shell errors containing `$'\r'`. **Fix:** check out scripts with LF endings (repository attributes enforce this on fresh checkouts); do not run CRLF shell scripts. Use WSL2, not a Windows Bash shim, and verify Linux tool paths with `command -v`.
- **Symptom:** Codespaces creation is denied or quota is exhausted. **Fix:** confirm organization policy and billing entitlement; use the documented WSL2/local Dev Container fallback.
- **Symptom:** Terraform uses a different subscription/tenant from the CLI. **Fix:** align `az account show` with `ARM_SUBSCRIPTION_ID`/`ARM_TENANT_ID` and reauthenticate in the Linux terminal. Do not share tokens to fix access.
- **Symptom:** pre-flight reports insufficient vCPU quota or an unverifiable permission/provider check. **Fix:** have the subscription owner verify the exact regional profile, available Standard_B2s_v2-family and regional quota, provider registration, and role-assignment rights; do not treat WARN as PASS.
- **Symptom:** Later Code Access or pull-request workflows target the Microsoft repository or cannot push a branch. **Fix:** run `git remote -v`; confirm `origin` points to the student's fork and `upstream` points to `https://github.com/microsoft/frontier-sre-agent-rvas.git`.
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
- **Symptom:** Terraform attempts to create resources that already exist outside its state. **Fix:** stop the apply and run `make drift` from `Student/`, passing the same `TF_VARS` used for deployment when applicable. This read-only comparison lists resources deployed in the workshop resource group but missing from local state, plus state entries not returned by Azure. It also generates `terraform import` commands when a deployed resource uniquely matches a planned Terraform address. Verify each candidate's ownership and configuration before running the suggested command; do not create duplicates or import unrelated resources.
- **Symptom:** The agent portal URL returns an error immediately after creation. **Fix:** confirm `provisioning_state` and power state, then allow a short control-plane propagation interval before retrying.
- **Symptom:** A later Student target cannot resolve the agent name or resource group. **Fix:** confirm `Student/.env` has `SRE_AGENT_RG` and `SRE_AGENT_NAME` set, matching the agent created in the portal.
- **Symptom:** Infrastructure validation succeeds but Grubify is unhealthy. **Fix:** generate food traffic, inspect `make food-status`, and check the active Container Apps revision before redeploying.
- **Symptom:** `make validate-parking` reports an unhealthy proxy endpoint. **Fix:** inspect the named endpoint, confirm the Web App has VNet integration for private VM APIs, and verify route-all remains disabled for public API access.
- **Symptom:** Traffic Analytics is empty in later challenges. **Fix:** ensure baseline traffic ran successfully and allow for the documented ingestion interval.
- **Symptom:** The agent can diagnose a workload but cannot perform an expected write action. **Fix:** confirm the agent's role assignment on the associated resource group is Contributor, not Reader.

## Debrief Discussion Guide

- Why is the agent created by hand instead of by Terraform, when every later challenge is scripted? → It forces students to see and understand every capability the agent starts without, before adding each one deliberately in Challenges 01–06.
- Why does the Coach's own Terraform additionally deploy the agent? → So coaches can stand up a working reference environment quickly for demos, without repeating the manual student steps for every session.
- Why start traffic generators before the operational labs? → Many later challenges fail silently if there is no telemetry history.
- What is the risk of an agent with excess or missing role assignments? → Missing assignments block expected remediation; excess assignments widen blast radius beyond what the workshop's governance story assumes.
- Which dependency here is most fragile in real workshops? → Usually monitoring lag, not infrastructure creation.

## Success Criteria Notes

- Be strict that the student created the agent themselves in the portal — this is the exercise, not a shortcut to route around.
- Confirm the workload resource group is associated with the agent and its permission level is Contributor.
- Accept background traffic in separate terminals or detached shells; the key is that data starts accumulating.
- If Terraform finishes but one monitoring-dependent validation is briefly empty, allow a short wait rather than forcing a full redeploy.

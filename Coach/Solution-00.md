**[Home](./README.md)** | [Next Solution >](./Solution-01.md)

# Coach Guide — Challenge 00: Prerequisites: Deploy the Lab & Create Your SRE Agent

## Purpose

- Establish the baseline: Azure authentication, authoritative Coach Terraform deployment, a reachable Azure SRE Agent, and working validation.
- Students manually create the control-plane agent in the portal (Terraform intentionally does not create it for Student's root); `make deploy` in this challenge only provisions the workload every later data-plane capability depends on, and Challenges 01 through 06 build the data plane.
- Expected time: 30–45 minutes.

## Mini-Lecture (5–7 min before challenge)

- Workshop arc: **manual base agent → progressively add data-plane capabilities**. Make students distinguish the control-plane resource they create by hand from knowledge, skills, subagents, repositories, and automations, all of which they add themselves in later challenges.
- Dependency chain to draw: Azure authentication → `make deploy` (workload only) → manual agent creation in the portal → resource-group association + Contributor role → baseline traffic → workload validation.
- Call out slow resources: Container Apps environment and monitoring plumbing are the usual long pole.
- Emphasize that the Student Terraform root deliberately does **not** create the SRE Agent — `make deploy` provisions only the workload. Creating the agent by hand, and associating it with the four workload resource groups, is the point of Step 3 in Challenge 00.
- Note the Coach environment is different: `Coach/` runs its own Terraform root (`Solutions/infra`), which additionally deploys a Coach-owned reference agent via `module "sre_agent"` (`make infra` from `Coach/`). This lets a coach stand up a fully wired reference environment for demos and answer-checking without doing the manual portal steps every time — it is not what students do, and should not be presented to students as an alternative.
- Show the two workload validation surfaces: `make validate` for the VNet Flow Logs and virtual machine lab, and `make validate-food` for Grubify.

## Expected Student Output

- `make deploy` completes from `Student/` and provisions the workload only.
- The student created the SRE Agent themselves in the portal, associated the four workload resource groups, and granted it Contributor.
- `Student/.env` is filled in with `SRE_AGENT_RG` and `SRE_AGENT_NAME` so later `make` targets can reach the agent.
- Baseline traffic completes via the Student scenario targets.
- The Student infrastructure and Grubify validation targets both return healthy.

## Common Issues and Hints

- **Symptom:** `make deploy` fails early with Azure authentication or subscription errors. **Fix:** verify `az account show`, select the intended subscription, and rerun the Terraform plan before applying.
- **Symptom:** Terraform attempts to create resources that already exist outside its state. **Fix:** stop the apply and reconcile the authoritative state or import strategy; do not create duplicates.
- **Symptom:** The agent portal URL returns an error immediately after creation. **Fix:** confirm `provisioning_state` and power state, then allow a short control-plane propagation interval before retrying.
- **Symptom:** A later Student target cannot resolve the agent name or resource group. **Fix:** confirm `Student/.env` has `SRE_AGENT_RG` and `SRE_AGENT_NAME` set, matching the agent created in the portal.
- **Symptom:** Infrastructure validation succeeds but Grubify is unhealthy. **Fix:** generate food traffic, inspect `make food-status`, and check the active Container Apps revision before redeploying.
- **Symptom:** Traffic Analytics is empty in later challenges. **Fix:** ensure baseline traffic ran successfully and allow for the documented ingestion interval.
- **Symptom:** The agent can diagnose a workload but cannot perform an expected write action. **Fix:** confirm the agent's role assignment on the associated resource groups is Contributor, not Reader.

## Debrief Discussion Guide

- Why is the agent created by hand instead of by Terraform, when every later challenge is scripted? → It forces students to see and understand every capability the agent starts without, before adding each one deliberately in Challenges 01–06.
- Why does the Coach's own Terraform additionally deploy the agent? → So coaches can stand up a working reference environment quickly for demos, without repeating the manual student steps for every session.
- Why start traffic generators before the operational labs? → Many later challenges fail silently if there is no telemetry history.
- What is the risk of an agent with excess or missing role assignments? → Missing assignments block expected remediation; excess assignments widen blast radius beyond what the workshop's governance story assumes.
- Which dependency here is most fragile in real workshops? → Usually monitoring lag, not infrastructure creation.

## Success Criteria Notes

- Be strict that the student created the agent themselves in the portal — this is the exercise, not a shortcut to route around.
- Confirm all four resource groups are associated with the agent and its permission level is Contributor.
- Accept background traffic in separate terminals or detached shells; the key is that data starts accumulating.
- If Terraform finishes but one monitoring-dependent validation is briefly empty, allow a short wait rather than forcing a full redeploy.

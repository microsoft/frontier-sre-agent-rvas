**[Home](./README.md)** | [Next Solution >](./Solution-01.md)

# Coach Guide — Challenge 00: Prerequisites: Deploy the Lab & Create Your SRE Agent

## Purpose

- Establish the baseline: Azure auth, Terraform deployment, a reachable Azure SRE Agent, and working validation.
- This challenge sets up every later demo dependency: telemetry generation, `.env`, and portal access.
- Expected time: 30–45 minutes.

## Mini-Lecture (5–7 min before challenge)

- Workshop arc: **infra first → empty agent → progressively add capability**. Make students notice the agent starts with no code, knowledge, skills, or routing.
- Dependency chain to draw: `az login` → `make deploy` → create agent at sre.azure.com → `Student/.env` → traffic generation → validation.
- Call out slow resources: Container Apps environment and monitoring plumbing are the usual long pole.
- Emphasize that `make deploy` creates workload resources, **not** the SRE Agent; the agent is created separately by portal or CLI.
- Show the two validation surfaces: `make validate` for the VNet Flow Logs / VM lab, `make validate-food` for Sample Food / Grubify.

## Expected Student Output

- Terraform completes from `Student/` with `make deploy`.
- Student has a live agent in the correct resource group and can open the portal.
- `Student/.env` contains `SRE_AGENT_RG` and `SRE_AGENT_NAME`.
- Background traffic is running via `make baseline-traffic` and `make food-traffic`.
- `make validate` and `make validate-food` both return healthy.

## Common Issues and Hints

- **Symptom:** `make deploy` fails early with Azure auth/subscription errors. **Fix:** run `az login` and `az account set --subscription ...`, then retry from `Student/`.
- **Symptom:** Agent portal link 404s just after creation. **Fix:** wait 2–3 minutes; resource exists before portal DNS is ready.
- **Symptom:** Later `make` targets say agent name/resource group missing. **Fix:** confirm `Student/.env` was copied from `.env.example` and edited.
- **Symptom:** Validation is green for infra but not Sample Food. **Fix:** run `make food-traffic`, then `make validate-food` again after a few minutes.
- **Symptom:** No Traffic Analytics data later in the day. **Fix:** make sure `make baseline-traffic` was actually started now, not postponed.
- **Symptom:** Agent can investigate Grubify/Sample Food but returns "no data" or "resource not found" for Parking Manager APIs or network resources (Challenges 07–18). **Fix:** student only associated one resource group when creating the agent. In the SRE Agent portal → **Managed Resources**, add all 9 lab resource groups: `rg-hub`, `rg-sre-spoke-web-api`, `rg-sre-spoke-data`, `rg-sre-spoke-foodapp-paas`, `rg-sre-parking-lisbon`, `rg-sre-parking-berlin`, `rg-sre-parking-madrid`, `rg-sre-parking-paris`, `rg-sre-parking-chaos`. Run `terraform -chdir="Resources/infra" output parking_resource_groups` to get the exact names.
- **Symptom:** Agent correctly identifies root cause in Challenges 11–15 but write actions (VM restart, NSG delete, UDR remove) are refused with a permission error. **Fix:** student set Reader permission instead of Contributor. In the SRE Agent portal → **Managed Resources**, change the permission to **Contributor** for all resource groups.

## Debrief Discussion Guide

- Why is the agent created separately from Terraform? → Separates cloud workload provisioning from agent governance/config lifecycle.
- Why start traffic generators before the operational labs? → Many later challenges fail silently if there is no telemetry history.
- What is the risk of skipping `.env`? → All later config automation loses the pointer to the correct agent.
- Which dependency here is most fragile in real workshops? → Usually monitoring lag, not infrastructure creation.

## Success Criteria Notes

- Be strict on `.env` and validation; those are hard prerequisites.
- Be flexible on whether students create the agent by portal or CLI.
- Accept background traffic in separate terminals or detached shells; the key is that data starts accumulating.
- If Terraform finishes but one monitoring-dependent validation is briefly empty, allow a short wait rather than forcing a full redeploy.

---
title: Autonomous Remediation
summary: Stop the Paris Parking API service. Check whether the agent restarts the VM, validates service and API health, and retries or escalates if recovery fails.
phase: Autonomous
group: Autonomous incident response
tags:
- Response Plans
- auto-remediation
- validation loops
highlight: false
---

# Challenge 15 — Autonomous Remediation

> **Application focus:** Parking Manager only

> **Capability**: Response Plans · Auto-remediation · Validation loops

## Purpose

- Verify recovery after remediation and examine retry and escalation behavior.
- Compare the observed autonomous recovery time with an estimate of manual recovery. Do not present the estimate as a measured MTTR improvement.
- Expected time: 20–25 minutes.

## Introduction

A remediation isn't complete until recovery is verified. You'll test a workflow that applies a fix, checks service health, retries within a configured limit, and escalates if recovery fails.

You'll stop the Paris Parking API systemd service and watch the agent restart its VM. Then you'll see how it confirms recovery, or handles a first restart that wasn't enough, before closing the incident. Unlike Challenge 10's synthetic health alert, this is a real service outage with its own alert and response plan.

## Description

### Before you start

Verify the Parking Manager is running and healthy:

```bash
make validate-parking
```

### Step 1 — Trigger the incident

Stop the Paris Parking API service:

```bash
make trigger-parking-service-down
```

> **Automatic routing:** The `parking-api-service-down` filter matches the Sev2 `Paris Parking API Service Down` alert and routes it to `parking-vm-incident-handler` in Autonomous mode. It can't match Challenge 10's `Parking VM Unhealthy Alert`. If you applied the full filter bundle in Challenge 06, routing should trigger automatically. If the alert doesn't appear within 5 minutes, go to Step 2b.

> **If remediation is denied:** Autonomous mode lets the workflow proceed without approval, but the agent's managed identity still needs Azure RBAC permission for `az vm restart` and Run Command validation. Ask an **Owner** or **Role Based Access Control Administrator** to run `make grant-agent-vm-remediation`, wait several minutes for role propagation, and retry in a new investigation thread. The custom role is limited to VM read, restart, and Run Command actions on the lab's VM resource groups.

### Step 2a — Observe automatic routing (if a Parking Manager filter is configured)

In the SRE Agent portal under **Incidents**, watch for the alert to appear and route automatically. The agent should:

1. Receive the alert and identify the affected VM and API
2. Query Syslog to confirm that `paris-parking-api.service` stopped
3. Attempt remediation: `az vm restart` on the affected instance
4. Wait for the VM to return to a running state
5. Confirm the systemd service is active and the localhost API returns success
6. Close the incident with a remediation summary

### Step 2b — Trigger manually (no Parking Manager filter configured)

If routing doesn't happen within 5 minutes, invoke the VM specialist directly:

```text
/agent parking-vm-incident-handler

The Paris Parking API service is down on vm-parking-paris. Investigate the Syslog evidence, restart the VM, and verify the systemd service and API before closing.
```

Watch the tool-call log for the same investigation → remediation → validation sequence.

### Step 3 — Verify the validation step

Ask the agent in chat:

```text
After restarting the VM, how did you verify that the remediation worked? What would have happened if the API was still unhealthy after the restart?
```

The agent should describe:

- The validation checks (`systemctl is-active paris-parking-api.service` and the localhost API response)
- The retry logic: if validation fails, attempt N (up to the response plan's attempt limit)
- The escalation path if all attempts fail

### Step 4 — Review the response plan

In the portal under **Incident Response → Filters**, find and open the `parking-api-service-down` response plan.

Identify the `maxAutomatedInvestigationAttempts` field and the subagent assigned to this scenario.

### Step 5 — Compare with manual remediation

Ask the agent:

```text
How long did the autonomous remediation take from alert fire to validation success? Estimate what a manual remediation would take for the same failure. What is the MTTR improvement?
```

### Step 6 — Restore

Restore the scenario:

```bash
make restore-parking-service
```

## Success Criteria

- [ ] The `parking-vm-incident-handler` restarted `vm-parking-paris` and verified recovery
- [ ] The agent describes its validation logic — what it checks and what it does if validation fails
- [ ] You can explain why `parking-api-service-down` routes to remediation while Challenge 10's `parking-vm-unhealthy` routes to GitHub reporting
- [ ] You can explain why Autonomous mode does not by itself authorize `az vm restart`
- [ ] No GitHub issue is created by the remediation workflow
- [ ] **Explain in your own words** (two or three written sentences) — what is the difference between *remediation* and *validated remediation*? Why is a validation loop essential for autonomous operations, and what is the risk of an agent that remediates without verifying?

## Learning Resources

- [Azure SRE Agent — response plans](https://learn.microsoft.com/en-us/azure/sre-agent/incident-response-plans)
- [Azure SRE Agent — autonomous operations](https://learn.microsoft.com/en-us/azure/sre-agent/incident-response-plans)
- [Azure VM — restart operations](https://learn.microsoft.com/en-us/azure/virtual-machines/states-billing)
- [SRE Book — Automation](https://sre.google/sre-book/automation-at-google/)

## Tips

- Limit autonomous remediation to tested actions with reliable validation and a defined scope. For this lab, verify both VM state and API health after a restart; a running VM alone does not establish recovery.
- If the first remediation attempt fails validation, the agent retries up to the `maxAutomatedInvestigationAttempts` limit (2 for this filter), like a human trying the same fix twice before escalating. Watch for this in the portal.
- Write actions (`az vm restart`) are reachable only because the skill's `tools` list includes a write tool and the incident filter's `agentMode` is `Autonomous`. The skill has no `safety` block. To add a gate, remove the write tool or set `agentMode: Review`.

## Hints and notes

> Hidden until you click. Expand a section only when you want it.

<details>
<summary><strong>Background</strong></summary>

- The pattern is detect → remediate → validate → retry or escalate.
- `parking-api-service-down` matches only the Sev2 `Paris Parking API Service Down` alert and routes to `parking-vm-incident-handler` in Autonomous mode. If routing doesn't happen, confirm the filter was applied under **Incident Response → Filters**.
- `make trigger-parking-service-down` stops the real `paris-parking-api.service` and emits a deterministic systemd Syslog marker.
- Watch for: `az vm restart`, power-state check, systemd and localhost API validation, closeout summary, and max-attempt behavior.
- As in Challenge 06, response-plan settings, especially attempt limits, govern the loop.
- Autonomous mode governs approval, not Azure authorization. The managed identity still needs VM restart and Run Command RBAC actions.

</details>

<details>
<summary><strong>Expected Output</strong></summary>

- After you run `make trigger-parking-service-down`, the incident routes to `parking-vm-incident-handler` via the `parking-api-service-down` filter, or you invoke that subagent manually if routing doesn't fire.
- The agent restarts `vm-parking-paris` and verifies the systemd service and API before closure.
- You can explain what the validation query/check was and what happens on failure.
- You understand the difference between basic remediation (Ch11/12) and validated remediation with retry logic (this challenge).
- No GitHub issue is created; Challenge 10 owns that separate reporting workflow.

</details>

<details>
<summary><strong>Common Issues and Hints</strong></summary>

- **Symptom:** You can't find a trigger script. **Fix:** use `make trigger-parking-service-down` and the idempotent `make restore-parking-service` cleanup target.
- **Symptom:** Agent reports remediation complete with no proof. **Fix:** ask for the validation step explicitly. Validation is the point of this challenge.
- **Symptom:** You conflate reboot success with service recovery. **Fix:** require both `systemctl is-active paris-parking-api.service` and a successful localhost API response.
- **Symptom:** You cannot find the exact response-plan YAML. **Fix:** inspect `labs/01-azure-operations/resources/azure-sre-agent-config/automations/incident-filters/parking-api-service-down.yaml`, which was applied with `make incident-filters` in Challenge 06.
- **Symptom:** A GitHub issue is created instead of remediation. **Fix:** the Challenge 10 filter handled the alert; confirm both filters match exact alert titles and `parking-api-service-down` routes to `parking-vm-incident-handler`.
- **Symptom:** Agent correctly identifies the failing VM but `az vm restart` or Run Command validation is refused with an Azure authorization error. **Fix:** have an Owner or Role Based Access Control Administrator run `make grant-agent-vm-remediation`, verify `Azure SRE Lab VM Remediator` is assigned on the shared workload resource group, wait for propagation, and retry in a new thread. The role grants no GitHub, network, disk, resize, or role-management permissions.

</details>

<details>
<summary><strong>Debrief Discussion Guide</strong></summary>

- What is the difference between remediation and validated remediation? → Action taken vs action proven effective.
- Why can retry loops be useful and dangerous? → Good for transient issues, bad if the success signal is weak.
- Where does MTTR improvement come from here? → No handoff delay plus immediate verification.

</details>

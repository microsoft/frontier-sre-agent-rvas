[< Previous Challenge](./Challenge-14.md) — **[Home](../README.md)** — [Next Challenge >](./Challenge-16.md)

# Challenge 15 — Autonomous Remediation

> **Application focus:** Parking Manager only

> **Capability**: Response Plans · Auto-remediation · Validation loops

## Introduction

Challenges 11 and 12 showed the agent fix a service — restart nginx, delete an NSG rule — and move on. That's remediation. This challenge goes one step further: **validated remediation**.

Validated remediation means the agent doesn't just apply a fix; it verifies the fix worked, retries if the service hasn't recovered, and escalates to a human if all attempts fail. This loop — fix → validate → retry → escalate — is what turns a one-shot script into a production-grade autonomous operator.

In this challenge you'll stop the Paris Parking API systemd service, watch the agent restart its VM, and observe how it confirms recovery (or handles the case where the first restart wasn't enough) before closing the incident. Unlike Challenge 10's synthetic health alert, this is a real service outage with a separate alert and response plan.

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

> **Note on automatic routing:** The `parking-api-service-down` filter matches the Sev2 `Paris Parking API Service Down` alert and routes it to `parking-vm-incident-handler` in Autonomous mode. It cannot match Challenge 10's `Parking VM Unhealthy Alert`. If you applied the full filter bundle in Challenge 06, automatic routing should trigger here. If the alert doesn't appear within 5 minutes, proceed to the manual trigger in Step 2b.

> **If remediation is denied:** Autonomous mode allows the workflow to proceed without approval, but the agent's managed identity still needs Azure RBAC permission for `az vm restart` and Run Command validation. Ask an **Owner** or **Role Based Access Control Administrator** to run `make grant-agent-vm-remediation`, wait several minutes for role propagation, and retry in a new investigation thread. The custom role is limited to VM read, restart, and Run Command actions on the lab's VM resource groups.

### Step 2a — Observe automatic routing (if a Parking Manager filter is configured)

In the SRE Agent portal under **Incidents**, watch for the alert to appear and route automatically. The agent should:

1. Receive the alert and identify the affected VM and API
2. Query Syslog to confirm that `paris-parking-api.service` stopped
3. Attempt remediation: `az vm restart` on the affected instance
4. Wait for the VM to return to a running state
5. Confirm the systemd service is active and the localhost API returns success
6. Close the incident with a remediation summary

### Step 2b — Trigger manually (no Parking Manager filter configured)

If no automatic routing occurs within 5 minutes, invoke the VM specialist directly:

```text
/agent parking-vm-incident-handler

The Paris Parking API service is down on vm-parking-paris. Investigate the Syslog evidence, restart the VM, and verify the systemd service and API before closing.
```

Watch the agent's tool-call log for the same investigation → remediation → validation sequence.

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

After the challenge, restore the scenario:

```bash
make restore-parking-service
```

## Success Criteria

- [ ] The `parking-vm-incident-handler` restarted `vm-parking-paris` and verified recovery
- [ ] The agent describes its validation logic — what it checks and what it does if validation fails
- [ ] You can explain why `parking-api-service-down` routes to remediation while Challenge 10's `parking-vm-unhealthy` routes to GitHub reporting
- [ ] You can explain why Autonomous mode does not by itself authorize `az vm restart`
- [ ] No GitHub issue is created by the remediation workflow
- [ ] **Explain to your coach** — what is the difference between *remediation* and *validated remediation*? Why is a validation loop essential for autonomous operations, and what is the risk of an agent that remediates without verifying?

## Learning Resources

- [Azure SRE Agent — response plans](https://learn.microsoft.com/en-us/azure/sre-agent/incident-response-plans)
- [Azure SRE Agent — autonomous operations](https://learn.microsoft.com/en-us/azure/sre-agent/incident-response-plans)
- [Azure VM — restart operations](https://learn.microsoft.com/en-us/azure/virtual-machines/states-billing)
- [SRE Book — Automation](https://sre.google/sre-book/automation-at-google/)

## Tips

- Autonomous remediation is only safe when the fix is idempotent and the validation is reliable. A VM restart is a good candidate — it's reversible, it has a clear success signal (VM back to running + service responding), and the blast radius is contained.
- If the agent's first remediation attempt fails validation, it will retry up to the `maxAutomatedInvestigationAttempts` limit (2, for this filter). Watch for this in the portal — it's the agent's equivalent of a human trying the same fix twice before escalating.
- The key governance control here is that write actions (`az vm restart`) are only reachable because the skill's `tools` list includes a write tool and the incident filter's `agentMode` is `Autonomous`. There is no `safety` block on the skill itself — remove either the write tool or set `agentMode: Review` to add a gate.

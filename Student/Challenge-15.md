[< Previous Challenge](./Challenge-14.md) — **[Home](../README.md)** — [Next Challenge >](./Challenge-16.md)

# Challenge 15 — Autonomous Remediation

> **Capability**: Response Plans · Auto-remediation · Validation loops

## Introduction

Challenges 11 and 12 showed the agent fix a service — restart nginx, delete an NSG rule — and move on. That's remediation. This challenge goes one step further: **validated remediation**.

Validated remediation means the agent doesn't just apply a fix; it verifies the fix worked, retries if the service hasn't recovered, and escalates to a human if all attempts fail. This loop — fix → validate → retry → escalate — is what turns a one-shot script into a production-grade autonomous operator.

In this challenge you'll trigger a Parking Manager backend failure, watch the agent restart the affected VM, and observe how it confirms recovery (or handles the case where the first restart wasn't enough) before closing the incident.

## Description

### Before you start

Verify the Parking Manager is running and healthy:

```bash
make validate
```

### Step 1 — Trigger the incident

Trigger the Parking Manager VM API unhealthy state:

```bash
make trigger-parking-down
```

After the challenge, restore the scenario:

```bash
make restore-parking
```

> **Note on automatic routing:** The incident filter bundle now includes a `parking-vm-unhealthy` filter (Sev2, `titleContains: parking`) that routes to `iaas-vm-incident-handler` in Autonomous mode. If you applied the full filter bundle in Challenge 06 (via `make incident-filters`), automatic routing should trigger here. Watch **Incident Response** for the incoming alert. If the alert doesn't appear within 5 minutes, proceed to the manual trigger in Step 2b.

### Step 2a — Observe automatic routing (if a Parking Manager filter is configured)

In the SRE Agent portal under **Incident Response**, watch for the alert to appear and route automatically. The agent should:

1. Receive the alert and identify the affected VM and API
2. Query Azure Monitor / Log Analytics to confirm the failure signature
3. Attempt remediation: `az vm restart` on the affected instance
4. Wait for the VM to return to a running state
5. Re-query the health endpoint or monitoring data to confirm the API is responding
6. Close the incident with a remediation summary

### Step 2b — Trigger manually (no Parking Manager filter configured)

If no automatic routing occurs within 5 minutes, invoke the VM specialist directly:

```text
/agent iaas-vm-incident-handler

The Parking Manager VM API is reporting unhealthy. Investigate, restart the affected VM, and verify the API is responding before closing.
```

Watch the agent's tool-call log for the same investigation → remediation → validation sequence.

### Step 3 — Verify the validation step

Ask the agent in chat:

```text
After restarting the VM, how did you verify that the remediation worked? What would have happened if the API was still unhealthy after the restart?
```

The agent should describe:

- The validation query (health endpoint check, Log Analytics query, or metric poll)
- The retry logic: if validation fails, attempt N (up to the response plan's attempt limit)
- The escalation path if all attempts fail

### Step 4 — Review the response plan

In the portal under **Incident Response → Filters**, find and open the Parking Manager response plan.

Identify the `max_attempts` field and the subagent assigned to this scenario.

### Step 5 — Compare with manual remediation

Ask the agent:

```text
How long did the autonomous remediation take from alert fire to validation success? Estimate what a manual remediation would take for the same failure. What is the MTTR improvement?
```

## Success Criteria

- [ ] The `iaas-vm-incident-handler` subagent (or a custom Parking Manager specialist) restarted the VM and verified recovery
- [ ] The agent describes its validation logic — what it checks and what it does if validation fails
- [ ] You understand why no Parking Manager incident filter ships in the default bundle and what you would need to add one
- [ ] **Explain to your coach** — what is the difference between *remediation* and *validated remediation*? Why is a validation loop essential for autonomous operations, and what is the risk of an agent that remediates without verifying?

## Learning Resources

- [Azure SRE Agent — response plans](https://learn.microsoft.com/en-us/azure/sre-agent/incident-response-plans)
- [Azure SRE Agent — autonomous operations](https://learn.microsoft.com/en-us/azure/sre-agent/incident-response-plans)
- [Azure VM — restart operations](https://learn.microsoft.com/en-us/azure/virtual-machines/states-billing)
- [SRE Book — Automation](https://sre.google/sre-book/automation-at-google/)

## Tips

- Autonomous remediation is only safe when the fix is idempotent and the validation is reliable. A VM restart is a good candidate — it's reversible, it has a clear success signal (VM back to running + service responding), and the blast radius is contained.
- If the agent's first remediation attempt fails validation, it will retry up to the `max_attempts` limit. Watch for this in the portal — it's the agent's equivalent of a human trying the same fix twice before escalating.
- The key governance control here is that write actions (`az vm restart`) are in the skill's `tools` list AND the skill's `safety` block requires the action. This dual gate prevents a misconfigured response plan from triggering write operations unintentionally.

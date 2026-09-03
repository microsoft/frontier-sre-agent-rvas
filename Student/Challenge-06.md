[< Previous Challenge](./Challenge-05.md) — **[Home](../README.md)** — [Next Challenge >](./Challenge-07.md)

# Challenge 06 — Understand Response Plans

> **Capabilities added in this challenge**: Incident Filters & Response Plans

## Introduction

Your agent is fully capable now — it has a connected codebase, knowledge, skills, connectors, and domain specialists. But everything so far has been chat-driven: you ask, it answers. In a real SRE environment, you can't be at the keyboard when every alert fires at 3 AM.

**Incident filters** (response plans) close that gap. Each filter watches for incoming Azure Monitor alerts that match a severity and title pattern, routes the alert to the right specialist, and launches an autonomous investigation — without a human trigger. This is the difference between an *assistant* and an *autonomous operator*.

In this challenge you'll send an alert into the agent with no response plan configured, observe nothing happens, then add the response plans and watch the same alert trigger an autonomous investigation.

## Description

### Step 1 — Send an alert with no response plan

Trigger the Grubify HTTP 5xx fault:

```bash
make break-food
```

Wait 3–5 minutes for the Azure Monitor alert `alert-food-http-5xx` to fire.

Open the SRE Agent portal under **Incident Response**. The alert will appear as an **unrouted incident** — the agent received it but has no rule for how to handle it. Nothing happens automatically.

### Step 2 — Restore the app

Restore the app before continuing:

> **How recovery works:** `make break-food` sends a burst of requests that cause an OOM container restart. Once the traffic stops, the Grubify app **self-heals automatically** — no manual restore command is needed. Run `make validate-food` to confirm recovery; it validates health but does not trigger it. If the container has not recovered after 2–3 minutes, run `make food-status` to check the deployment state.

```bash
make validate-food
# If container revision still shows unhealthy after 3 minutes:
make food-status
```

### Step 3 — Add the incident filters (response plans)

Apply the incident filter YAMLs from `Student/Resources/azure-sre-agent-config/automations/incident-filters/`:

```bash
make incident-filters
```

Verify under **Incident Response → Filters** in the portal — you should see 4 filters listed:
- `sample-food-http-errors` — Sev1, titleContains: food → `aca-app-incident-handler`
- `web-tier-nginx` — Sev2, titleContains: nginx → `iaas-vm-incident-handler`
- `network-observability-review` — Sev2, titleContains: network- (excludes nginx) → `network-traffic-analyst`
- `parking-vm-unhealthy` — Sev2, titleContains: parking → `iaas-vm-incident-handler`

### Step 4 — Trigger the same alert again

```bash
make break-food
```

Wait 3–5 minutes for the alert to fire. This time, in the portal under **Incident Response**, the incident should be **automatically routed** to `aca-app-incident-handler` and an autonomous investigation should begin.

Watch the agent's tool call log — it will query Application Insights, analyze the failing revision, and attempt remediation without any human input.

### Step 5 — Inspect the response plan definitions

In the portal under **Incident Response → Filters**, click each of the 4 response plans. For each plan, identify:

- The severity and title pattern (routing trigger)
- The assigned subagent
- The execution mode: `Autonomous` vs `Review`
- The maximum number of investigation attempts

> **Preview:** Each filter you've just configured will fire in an upcoming scenario — `web-tier-nginx` in Challenge 11, `network-observability-review` in Challenge 12, `parking-vm-unhealthy` in Challenge 15, and `sample-food-http-errors` in Challenge 14. By the end of those challenges, you'll have seen every filter trigger an autonomous investigation end-to-end.

### Step 6 — Understand Review vs Autonomous

Ask the agent:

```text
What is the difference between Review mode and Autonomous mode in a response plan? Give me a concrete example of when you would choose Review over Autonomous, and why.
```

### Step 7 — Also apply scheduled tasks

Response plans handle reactive automation. Scheduled tasks handle proactive automation. Apply them from `Student/Resources/azure-sre-agent-config/automations/scheduled-tasks/`:

```bash
make scheduled-tasks
```

Verify under **Scheduled Tasks** in the portal. You should see **6 active scheduled tasks**:
`agent-quality-review`, `cost-optimization-review`, `daily-network-observability-health`,
`flow-log-ingestion-freshness`, `post-demo-drift-check`, and `triage-grubify-issues`.

## Success Criteria

- [ ] Before adding incident filters, the alert fires but nothing happens in the portal (unrouted incident)
- [ ] After adding incident filters, the same alert triggers an autonomous investigation routed to `aca-app-incident-handler`
- [ ] You can read an incident filter YAML and identify severity, titleContains, subagent, mode, and max_attempts
- [ ] The agent explains Review vs Autonomous mode with a concrete governance rationale
- [ ] Scheduled tasks are applied and visible in the portal
- [ ] **Explain to your coach** — you now have a fully configured agent. Which of the 6 capability layers (codebase → knowledge → skills → connectors → subagents → response plans) would cause the most impact if it were missing? Why?

## Learning Resources

- [Azure SRE Agent — incident filters](https://learn.microsoft.com/en-us/azure/sre-agent/automate-incidents)
- [Azure SRE Agent — response plans](https://learn.microsoft.com/en-us/azure/sre-agent/incident-response-plans)
- [Azure SRE Agent — governance and safety](https://learn.microsoft.com/en-us/azure/sre-agent/permissions)
- [Azure Monitor alerts overview](https://learn.microsoft.com/en-us/azure/azure-monitor/alerts/alerts-overview)

## Tips

- The `titleContains` matching is case-insensitive. Each filter uses a distinct keyword so alerts route to the right specialist: `food` for Grubify 5xx, `nginx` for web-tier VM failures, `Denied` for VNet denied-flow spikes.
- `Autonomous` mode is powerful — set it only for remediation procedures that are **idempotent** and have a clear success validation step. For new or untested procedures, start with `Review` mode.
- **Congratulations:** your agent is now fully configured. Challenges 07–19 are operational scenarios that use everything you've just built.

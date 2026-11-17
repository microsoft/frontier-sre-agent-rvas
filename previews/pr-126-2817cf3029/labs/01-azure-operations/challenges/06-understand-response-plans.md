---
title: Understand Response Plans
summary: Connect Azure Monitor and configure response plans. Compare an unmatched alert with one that starts an investigation, then inspect Review and Autonomous modes.
phase: Config
group: Agent configuration
tags:
- response plans
- incident filters
- automation
highlight: false
---

# Challenge 06 — Understand Response Plans

> **Application focus:** Grubify (Sample Food) and Parking Manager

> **Capabilities added in this challenge**: Incident Platform, Incident Filters & Response Plans

## Purpose

- Configure one alert-driven response plan and one scheduled task, and show each one starting the agent without you prompting it.
- Expected time: 25–30 minutes including alert propagation.

## Introduction

Your agent has a connected codebase, knowledge, skills, connectors, and domain specialists. So far, you have started every investigation from chat. Now configure investigations to start from alerts.

Incident filters (response plans) match Azure Monitor alerts by severity and title, route them to a specialist, and start an investigation in Review or Autonomous mode.

In this challenge you connect Azure Monitor as the incident platform, then fire an alert with no matching response plan. The alert stays in Azure Monitor and creates no SRE Agent investigation. Then you add response plans and watch the same alert type trigger an autonomous investigation.

## Description

### Step 1 — Connect the incident platform

Apply the Azure Monitor incident platform from `labs/01-azure-operations/resources/azure-sre-agent-config/incident-platforms/azure-monitor.yaml`:

```bash
make incident-platforms
```

Verify under **Incident** in the portal that Azure Monitor is connected as the incident platform. The agent can't receive alerts or apply incident filters without this connection. You might need to wait 10-30 seconds and refresh the SRE Portal page.

### Step 2 — Send an alert with no response plan

Trigger the Grubify HTTP 5xx fault:

```bash
make break-food
```

Wait 3–5 minutes for the Azure Monitor alert `alert-food-http-5xx` to fire.

Confirm that the alert fired in Azure Monitor, then open the SRE Agent portal under **Incidents**. With no enabled response plan matching the alert, SRE Agent doesn't pick it up or create an investigation incident/thread. The alert can still appear in the **Incidents preview** while you create a response plan, because that preview queries historical Azure Monitor alerts.

> If Azure Monitor is not the active incident platform, the alert still fires in Azure Monitor but does not become an SRE Agent incident. Only one incident platform can be active at a time.

> No SRE Agent incident is expected at this stage. A response plan tells the agent which alerts to pick up and which custom agent investigates them. You need no action group or webhook, because SRE Agent polls Azure Monitor by using its managed identity.

### Step 3 — Restore the app

Restore the app before continuing:

> **How recovery works:** `make break-food` sends a burst of requests that cause an OOM container restart. Once the traffic stops, the Grubify app **self-heals automatically** — no manual restore command is needed. Run `make validate-food` to confirm recovery; it validates health but does not trigger it. If the container has not recovered after 2–3 minutes, run `make food-status` to check the deployment state.

```bash
make validate-food
# If container revision still shows unhealthy after 3 minutes:
make food-status
```

### Step 4 — Add the incident filters (response plans)

Apply the incident filter YAMLs from `labs/01-azure-operations/resources/azure-sre-agent-config/automations/incident-filters/`:

```bash
make incident-filters
```

Verify under **Incident Response → Filters** in the portal. You should see 5 filters:
- `sample-food-http-errors` — Sev1, titleContains: food → `aca-app-incident-handler`
- `web-tier-nginx` — Sev2, titleContains: nginx → `iaas-vm-incident-handler`
- `network-denied-flows-review` — Sev2, titleContains: "Denied VNet flow" (excludes nginx) → `network-traffic-analyst`
- `parking-vm-unhealthy` — Sev2, titleContains: "Parking VM Unhealthy Alert" → `parking-vm-incident-reporter`
- `parking-api-service-down` — Sev2, titleContains: "Paris Parking API Service Down" → `parking-vm-incident-handler`

### Step 5 — Trigger the same alert again

```bash
make break-food
```

Wait 3–5 minutes for the alert to fire. This time, in the portal under **Triggers & response plans**, the incident should be **automatically routed** to `aca-app-incident-handler` and an autonomous investigation should begin.

Watch the agent's tool call log. It queries Application Insights, analyzes the failing revision, and attempts remediation without human input.

### Step 6 — Inspect the response plan definitions

In the portal under **Triggers & response plans**, click each of the 5 response plans. For each plan, identify:

- The severity and title pattern (routing trigger)
- The assigned subagent
- The execution mode: `Autonomous` vs `Review`
- The maximum number of investigation attempts

> **Preview:** Each filter fires in a later scenario. `parking-vm-unhealthy` creates an incident issue in Challenge 10, `web-tier-nginx` remediates nginx in Challenge 11, `network-denied-flows-review` remediates an NSG rule in Challenge 12, `sample-food-http-errors` handles the Grubify incident in Challenge 14, and `parking-api-service-down` performs validated Parking remediation in Challenge 15. The two Parking alerts are both Sev2 but route differently because their title predicates don't overlap.

### Step 7 — Understand Review vs Autonomous

Ask the agent:

```text
What is the difference between Review mode and Autonomous mode in a response plan? Give me a concrete example of when you would choose Review over Autonomous, and why.
```

### Step 8 — Also apply scheduled tasks

Response plans automate reactions; scheduled tasks automate proactive work. Apply the tasks from `labs/01-azure-operations/resources/azure-sre-agent-config/automations/scheduled-tasks/`:

```bash
make scheduled-tasks
```

Verify under **Automation** in the portal. You should see **6 active scheduled tasks**:
`agent-quality-review`, `cost-optimization-review`, `daily-network-observability-health`,
`flow-log-ingestion-freshness`, `post-demo-drift-check`, and `triage-grubify-issues`.

## Success Criteria

- [ ] Azure Monitor is connected as the SRE Agent incident platform
- [ ] Before adding incident filters, the alert fires but nothing happens in the portal (unrouted incident)
- [ ] After adding incident filters, the same alert triggers an autonomous investigation routed to `aca-app-incident-handler`
- [ ] You can read an incident filter YAML and identify severity, titleContains, subagent, mode, and max_attempts
- [ ] The agent explains Review vs Autonomous mode with a concrete governance rationale
- [ ] Scheduled tasks are applied and visible in the portal
- [ ] **Explain in your own words** (two or three written sentences) — you now have a fully configured agent. Which of the 6 capability layers (codebase → knowledge → skills → connectors → subagents → response plans) would cause the most impact if it were missing? Why?

## Learning Resources

- [Azure SRE Agent — incident filters](https://learn.microsoft.com/en-us/azure/sre-agent/automate-incidents)
- [Azure SRE Agent — response plans](https://learn.microsoft.com/en-us/azure/sre-agent/incident-response-plans)
- [Azure SRE Agent — governance and safety](https://learn.microsoft.com/en-us/azure/sre-agent/permissions)
- [Azure Monitor alerts overview](https://learn.microsoft.com/en-us/azure/azure-monitor/alerts/alerts-overview)

## Tips

- The `titleContains` matching is case-insensitive. Each filter uses a distinct keyword so alerts route to the right specialist: `food` for Grubify 5xx, `nginx` for web-tier VM failures, `Denied` for VNet denied-flow spikes.
- Severity alone doesn't identify the right workflow. Both Parking plans are Sev2, so their specific alert titles separate GitHub reporting from VM remediation.
- Use `Autonomous` mode only for tested, **idempotent** remediation procedures with a clear validation step. Start new or untested procedures in `Review` mode.
- Challenges 07–19 use the capabilities you've configured in operational scenarios.

## Hints and notes

> Hidden until you click. Expand a section only when you want it.

<details>
<summary><strong>Background</strong></summary>

- Prerequisite: `make incident-platforms` connects Azure Monitor before alerts can reach the agent or filters can be applied.
- The routing stack: Azure Monitor alert → incident filter → handling agent → mode (`Autonomous`/`Review`) → max attempts.
- The five filters: `sample-food-http-errors`, `web-tier-nginx`,
	`parking-vm-unhealthy`, `parking-api-service-down`, and `network-denied-flows-review`.
- The six scheduled tasks: `agent-quality-review`, `cost-optimization-review`,
	`daily-network-observability-health`, `flow-log-ingestion-freshness`,
	`post-demo-drift-check`, and `triage-grubify-issues`.
- `titleContains` keeps filters non-overlapping. The two Sev2 Parking plans use
	distinct full alert titles: `Parking VM Unhealthy Alert` for GitHub reporting and
	`Paris Parking API Service Down` for validated remediation.

</details>

<details>
<summary><strong>Expected Output</strong></summary>

- After `make incident-platforms`, Azure Monitor is configured as the agent's incident platform.
- Before filters, `make break-food` produces an Azure Monitor alert but no SRE Agent investigation.
- After `make incident-filters`, the same `alert-food-http-5xx` routes automatically to `aca-app-incident-handler`.
- After `make scheduled-tasks`, all six tasks appear in the portal.
- You can read mode and max-attempt behavior from a filter definition.
- You can explain why two alerts from the same application and severity route to different handlers.

</details>

<details>
<summary><strong>Common Issues and Hints</strong></summary>

- **Symptom:** No incident appears and filters fail to apply. **Fix:** run `make incident-platforms` and confirm Azure Monitor is connected before troubleshooting filter matching.
- **Symptom:** No incident appears after `make break-food`. **Fix:** wait 3–5 minutes, confirm Sample Food is actually generating 5xx, and re-run if needed.
- **Symptom:** Incident appears but is still unrouted after filters were applied. **Fix:** check severity/title matching and refresh the portal.
- **Symptom:** A Parking alert reaches the wrong handler. **Fix:** confirm both Parking filters use their exact, non-overlapping alert titles rather than broad `titleContains: parking` matching.
- **Symptom:** You treat scheduled tasks as incident filters. **Fix:** incident filters are reactive and alert-driven; scheduled tasks are proactive and cron-driven.
- **Symptom:** App remains unhealthy after the first break-food run. **Fix:** run `make validate-food`; if needed inspect `make food-status` before repeating.

</details>

<details>
<summary><strong>Debrief Discussion Guide</strong></summary>

- What was missing before this challenge? → Routing intent, not capability.
- Why is `Autonomous` acceptable in this lab? → Non-production scope plus restore scripts and clear validation signals.
- When would you prefer `Review` mode in production? → Novel, high-blast-radius, or compliance-sensitive remediations.
- Which of the six capability layers is most painful to miss? → Good discussion; routing often feels most visible because “nothing happens.”

</details>

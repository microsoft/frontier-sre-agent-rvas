[< Previous Solution](./Solution-05.md) | **[Home](./README.md)** | [Next Solution >](./Solution-07.md)

# Coach Guide — Challenge 06: Understand Response Plans

## Purpose

- Turn the workshop story from chat-driven assistance into alert-driven autonomous response.
- Students should see that a fully capable agent still does nothing automatically until incident filters and scheduled tasks exist.
- Expected time: 25–30 minutes including alert propagation.

## Mini-Lecture (5–7 min before challenge)

- Draw the routing stack: Azure Monitor alert → incident filter → handling agent → mode (`Autonomous`/`Review`) → max attempts.
- Name the four filters exactly: `sample-food-http-errors`, `web-tier-nginx`,
	`parking-vm-unhealthy`, and `network-observability-review`.
- Name the six scheduled tasks exactly: `agent-quality-review`, `cost-optimization-review`,
	`daily-network-observability-health`, `flow-log-ingestion-freshness`,
	`post-demo-drift-check`, and `triage-grubify-issues`.
- Show how `titleContains` keeps filters non-overlapping: `food`, `nginx`, `parking`, and
	`network-` each identify one operational domain.

## Expected Student Output

- Before filters, `make break-food` eventually produces an unrouted incident.
- After `make incident-filters`, the same `alert-food-http-5xx` routes automatically to `aca-app-incident-handler`.
- After `make scheduled-tasks`, all six tasks appear in the portal.
- Students can read mode and max-attempt behavior from a filter definition.

## Common Issues and Hints

- **Symptom:** No incident appears after `make break-food`. **Fix:** wait 3–5 minutes, confirm Sample Food is actually generating 5xx, and re-run if needed.
- **Symptom:** Incident appears but is still unrouted after filters were applied. **Fix:** check severity/title matching and refresh the portal.
- **Symptom:** Students think scheduled tasks are the same as incident filters. **Fix:** reactive = alert-driven; proactive = cron-driven.
- **Symptom:** App remains unhealthy after the first break-food run. **Fix:** run `make validate-food`; if needed inspect `make food-status` before repeating.

## Debrief Discussion Guide

- What was missing before this challenge? → Routing intent, not capability.
- Why is `Autonomous` acceptable in this lab? → Non-production scope plus restore scripts and clear validation signals.
- When would you prefer `Review` mode in production? → Novel, high-blast-radius, or compliance-sensitive remediations.
- Which of the six capability layers is most painful to miss? → Good discussion; routing often feels most visible because “nothing happens.”

## Success Criteria Notes

- Be strict that students can explain one filter end to end.
- Allow one failed alert-propagation attempt if the second succeeds; timing is platform-dependent.
- If time is tight, it is enough to inspect scheduled-task YAML after applying rather than waiting for one to fire.

[< Previous Solution](./Solution-03.md) | **[Home](./README.md)** | [Next Solution >](./Solution-05.md)

# Coach Guide — Challenge 04: Autonomous App Incident Response (PaaS)

## Purpose

This challenge demonstrates the core SRE Agent value proposition: detecting a production incident via Azure Monitor, routing it to the right specialist subagent, executing a runbook autonomously, and producing structured evidence. It is intentionally **no-code** — everything the agent does uses Azure-native observability (App Insights, Container Apps logs) and built-in tools.

Expected time: **20–30 minutes** including alert propagation delay.

## Mini-Lecture (10 min before challenge)

Cover:
- The incident routing chain: Azure Monitor alert → agent incident platform → `sample-food-http-errors` filter (titleContains: "food") → `aca-app-incident-handler` subagent
- The domain-routing architecture: each incident filter owns a failure domain (title-keyed, disjoint), so a "food" alert never reaches the `iaas-vm-incident-handler` or `network-traffic-analyst`
- The subagent's tool grants: `SearchMemory`, `RunAzCliReadCommands`, `RunAzCliWriteCommands`, `QueryLogAnalyticsByWorkspaceId`, `QueryAppInsightsByResourceId`, `ExecutePythonCode`
- The `sample-food-container-app-incident-analysis` skill: a structured investigation runbook loaded from the knowledge base

## Expected Agent Behavior

1. Agent receives the `food-5xx` incident
2. Calls `SearchMemory` for the Grubify runbook (`sample-food/http-500-errors.md`)
3. Queries Application Insights for HTTP 5xx errors and response times
4. Queries Container Apps logs for the failing revision
5. Identifies the bad environment variable or revision configuration
6. Issues `az containerapp revision deactivate` or `az containerapp update` to fix
7. Creates a GitHub issue (if OAuth authorized) or reports findings in the incident summary

## Common Issues and Hints

### Alert doesn't fire after 10 minutes
- Verify `break-sample-food-app.sh` ran successfully: look for the new revision in `az containerapp revision list --name ca-food-api`
- Check the Azure Monitor alert rule: in the portal, find the alert on the `appi-food` resource — the threshold is based on exception rate. If traffic is zero (app fully broken), the metric may not populate
- Coach fallback: have the student trigger the agent manually from portal chat: "Investigate the current Grubify 5xx incident"

### Agent routes to wrong subagent
- Should not happen — `sample-food-http-errors` filter uses `titleContains: "food"` and the alert title is `[Grubify] food-5xx`. If wrong routing occurs, check the incident filter config in portal
- Run `./Infra/scripts/sre-agent-config.sh verify --target incident-filters` to confirm filter is applied

### Agent investigation is shallow (only queries, no remediation)
- The subagent is `Autonomous` + `RunAzCliWriteCommands` granted. If remediation doesn't happen, the agent may not have found a clear action
- Coach prompt: "Ask the student to prompt the agent: 'What remediation action did you take or recommend?'"
- Acceptable outcome: agent produces evidence + recommendation even without executing the fix

### GitHub issue not created
- Either GitHub OAuth not authorized (Challenge 00 step missed) or the agent took a different code path
- This is acceptable for S1 — the investigation report in the portal incident timeline is the primary artifact

## Debrief Discussion Guide (10 min)

1. **What surprised you about the investigation?** — Attendees often don't expect the agent to read the runbook autonomously
2. **How long would this have taken a human?** — Walk through: alert → acknowledge → log into portal → find revision → diagnose → fix → validate. 30–60 minutes is typical
3. **What would you change about the agent's behavior?** — Opens discussion of runbook quality, prompt engineering, tool access scope
4. **What could go wrong if the agent's fix was incorrect?** — Leads to governance/approval gates discussion

## Success Criteria Notes

- Accept the investigation report as evidence even if the GitHub issue wasn't created (OAuth may be pending)
- The incident filter routing is the key technical concept — ensure the student can explain it
- A partial remediation (agent tried but failed) is still a passing outcome — the learning is in observing the attempt

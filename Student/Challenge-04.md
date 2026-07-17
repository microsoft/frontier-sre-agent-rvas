[< Previous Challenge](./Challenge-03.md) — **[Home](../README.md)** — [Next Challenge >](./Challenge-05.md)

# Challenge 04 — Autonomous App Incident Response (PaaS)

## Introduction

A food delivery app is down. Customers can't order. The SRE on-call gets paged at 3 AM.

In a traditional world, they'd SSH into servers, grep logs, open dashboards, and maybe spend 45 minutes figuring out that a container revision has a bad environment variable. In this challenge, you'll trigger that exact failure and watch the **Azure SRE Agent** investigate, diagnose, and remediate it — autonomously, without human intervention.

The agent detects the incident via an **Azure Monitor alert** (HTTP 5xx rate threshold), routes it through an **incident filter** to the specialist subagent (`aca-app-incident-handler`), executes the investigation runbook, and creates a GitHub issue with root cause and remediation actions — all while you watch.

This is **Scenario S1: Grubify IT Ops** — no GitHub code correlation, pure Azure-native observability and remediation.

## Description

### Before you start

Verify the Grubify app is healthy:

```bash
Student/Resources/scenarios/scripts/validate-sample-food-app.sh
```

### Trigger the incident

Run the break script to inject an HTTP 5xx fault into the Grubify API container:

```bash
Student/Resources/scenarios/scripts/break-sample-food-app.sh
```

This script pushes a new container revision with a broken environment variable that causes the API to return 5xx errors under load.

### Observe the autonomous response

1. Open the **SRE Agent portal** (`terraform -chdir=Coach/Solutions/infra output agent_portal_url`)
2. Navigate to **Incident Response** and watch for the incoming `food-5xx` incident (it may take **3–5 minutes** for the Azure Monitor alert to fire at the configured threshold)
3. Observe the agent's autonomous investigation — it will:
   - Search the knowledge base for the Grubify runbook
   - Query Application Insights and Container Apps logs
   - Identify the failing revision
   - Attempt remediation (revision deactivation / rollback)
4. Review the GitHub issue created by the agent in `microsoft/frontier-sre-agent-rvas`

### Restore

```bash
Student/Resources/scenarios/scripts/validate-sample-food-app.sh
```

If the agent did not fully restore the app, run:

```bash
Student/Resources/scenarios/scripts/deploy-sample-food-images.sh --status
```

## Success Criteria

To complete this challenge, demonstrate:

1. The Azure Monitor alert fired and the incident appeared in the SRE Agent portal
2. The agent routed the incident to `aca-app-incident-handler` (visible in the incident details)
3. The agent's investigation log shows it queried Application Insights and/or Container Apps logs
4. A GitHub issue was created (or the investigation report is visible in the portal) with root cause and remediation steps
5. `validate-sample-food-app.sh` returns healthy after the agent's remediation (or after manual restore)
6. **Explain to your coach** — what is the role of an **incident filter** in the SRE Agent? How did the `sample-food-http-errors` filter decide to route this incident to `aca-app-incident-handler` and not to a different subagent?

## Learning Resources

- [Azure SRE Agent — incident response](https://learn.microsoft.com/en-us/azure/sre-agent/incident-response)
- [Azure Container Apps — revision management](https://learn.microsoft.com/en-us/azure/container-apps/revisions)
- [Application Insights — live metrics and log queries](https://learn.microsoft.com/en-us/azure/azure-monitor/app/app-insights-overview)
- [Azure Monitor alerts](https://learn.microsoft.com/en-us/azure/azure-monitor/alerts/alerts-overview)

## Tips

- The incident alert threshold is set for **5xx rate > threshold for 5 minutes**. If the alert doesn't fire after 10 minutes, check that the break script ran successfully and the app is actually returning errors (`run-kql.sh sample-food-http-errors`).
- You can also **manually trigger the agent** from the portal chat: "Investigate the current Grubify 5xx incident" — this bypasses the alert trigger and lets you see the agent work in interactive mode.
- Watch the agent's **tool call log** in the portal — each `QueryAppInsights`, `RunAzCliReadCommands`, and `SearchMemory` call is visible in real time.
- If the agent creates a GitHub issue but the app is still broken, the remediation step may have failed silently. Check the Container Apps revision list manually.

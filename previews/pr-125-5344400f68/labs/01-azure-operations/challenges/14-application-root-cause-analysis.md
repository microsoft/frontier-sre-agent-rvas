---
title: Application Root Cause Analysis
summary: Trace a Grubify 5xx spike through container logs, Application Insights, and source code to the OOM fault path. Review the GitHub issue linking evidence to code.
phase: Autonomous
group: Autonomous incident response
tags:
- App Insights
- source code analysis
- GitHub MCP
highlight: false
---

# Challenge 14 — Application Root Cause Analysis

> **Application focus:** Grubify (Sample Food) only

> **Capability**: Incident Investigation · Telemetry Correlation · Source Code Analysis · GitHub MCP

## Purpose

- Trace a failure from telemetry to the failing endpoint and the responsible source code, and record that chain in a GitHub issue.
- Expected time: 25–30 minutes.

## Introduction

Investigate a Grubify HTTP 5xx spike from alert to source code. The agent should correlate container logs and Application Insights with the code path that causes an out-of-memory crash, then open a GitHub issue linking the evidence to the code.

## Description

### Before you start

Verify the Grubify app is healthy and the GitHub connector is authorized:

```bash
make validate-food
```

In the SRE Agent portal, confirm the **GitHub MCP** (`github-mcp` and `github-mcp-v1`) connectors and the **grubify** repository link are active.

### Step 1 — Inject the OOM fault

```bash
make break-food
```

This issues ~200 `POST /api/cart/demo-user/items` requests against the Grubify API. The cart-write path is the out-of-memory fault path in the v1 backend: the container exhausts heap memory, restarts, and returns HTTP 5xx during the restart window.

### Step 2 — Wait for the alert and autonomous response

The `alert-food-http-5xx` Azure Monitor alert (Sev1, Container Apps HTTP 5xx rate) fires on a 1-minute evaluation window. The response plan `sample-food-http-errors` routes the incident to `aca-app-incident-handler` in **Autonomous** mode (up to 3 investigation attempts).

Watch the portal. Within **3–5 minutes** the incident should appear and the agent should begin investigating.

### Step 3 — Follow the investigation to source code

The `aca-app-incident-handler` will:

1. Query Container Apps HTTP logs and Application Insights for the 5xx spike pattern
2. Identify the `/api/cart/{user}/items` endpoint as the fault path
3. Correlate the restart events with OOM signals in container console logs
4. Use the `source-fix-delivery` skill to fix the code in the Grubify repository
5. Search the Grubify repository for the cart endpoint implementation (`search_code`)
6. Retrieve the offending file (`get_file_contents`) and identify the OOM code path
7. Open a GitHub issue with: the root cause, the offending file and line, the telemetry evidence, and recommended fix

### Step 4 — Trigger interactively (if the alert didn't fire)

If the alert hasn't fired after 10 minutes, trigger the investigation manually:

```text
For the current Grubify 5xx incident, analyze the API repository, identify the likely offending code path, and open a GitHub issue with your findings.
```

### Step 5 — Review the GitHub issue

```bash
gh issue list --repo <your-github-username>/frontier-sre-agent-rvas --state open
```

The issue should contain: alert trigger, telemetry evidence, container restart timeline, code path identified, and recommended remediation.

### Step 6 — Restore

```bash
make validate-food
# If not self-healed:

make food-status
```

## Success Criteria

- [ ] The `alert-food-http-5xx` alert fired and the incident appeared in the portal
- [ ] The agent identified `/api/cart/{user}/items` as the fault path from telemetry
- [ ] The subagent retrieved the cart endpoint source code from the Grubify repository
- [ ] A GitHub issue was created with root cause, code evidence, and remediation steps
- [ ] The agent demonstrated the agent `aca-app-incident-handler` using skill `source-fix-delivery`
- [ ] **Explain in your own words** (two or three written sentences) — what is the governance mechanism that ensures `aca-app-incident-handler` can *read* source code and *create issues* but cannot *push commits* or *merge pull requests* without human approval?

## Learning Resources

- [Azure SRE Agent — incident response](https://learn.microsoft.com/en-us/azure/sre-agent/incident-response)
- [Application Insights — exception tracking](https://learn.microsoft.com/en-us/azure/azure-monitor/app/asp-net-exceptions)
- [Azure Container Apps — container restart policies](https://learn.microsoft.com/en-us/azure/container-apps/containers)
- [GitHub MCP server — code search](https://github.com/github/github-mcp-server)

## Tips

- The `aca-app-incident-handler → source-fix-delivery` handoff separates the incident investigation from the focused source-code work.
- The scheduled task `triage-grubify-issues` (cron `0 */12 * * *`) runs independently of this challenge and continuously triages `[Customer Issue]` backlog items. You may see it interleave with your incident; that's expected.
- If the GitHub issue is created but missing the code reference, confirm the `grubify` repository link is active in the portal and the OAuth connector has `repo` scope.

## Hints and notes

> Hidden until you click. Expand a section only when you want it.

<details>
<summary><strong>Background</strong></summary>

- Failure sequence: `make break-food` sends ~200 POSTs to `/api/cart/demo-user/items` → OOM/HTTP 500 window → `alert-food-http-5xx` → `aca-app-incident-handler`.
- Key Sample Food facts from knowledge: valid health routes are `/WeatherForecast` and `/api/FoodItems`; `/health` is not real.
- Two outcomes: S1 completes the Azure diagnosis/remediation without GitHub; S2 invokes `source-fix-delivery` skill for read-only source correlation and GitHub issue creation.
- Grubify source is immutable: no branch, pushed file, commit, or pull request is acceptable evidence.

</details>

<details>
<summary><strong>Expected Output</strong></summary>

- Incident appears and is routed by `sample-food-http-errors` to `aca-app-incident-handler`.
- Agent identifies `/api/cart/{user}/items` as the failing path from logs/telemetry.
- Root-cause output references actual Grubify source, ideally `CartController.cs` or the cart write path with file/line evidence.
- With OAuth write authorization complete, a GitHub issue is created with telemetry evidence, code evidence, and remediation guidance.

</details>

<details>
<summary><strong>Common Issues and Hints</strong></summary>

- **Symptom:** Agent or you check `/health`. **Fix:** correct to `/WeatherForecast` or `/api/FoodItems` using the knowledge doc.
- **Symptom:** Alert is slow. **Fix:** wait up to 10 minutes, then use the manual prompt from the challenge.
- **Symptom:** GitHub issue creation reports that the user must be logged in. **Fix:** complete the `github-mcp` and `github-mcp-v1` connectors OAuth authorization, confirm `aca-app-incident-handler`'s `mcp_tools` list includes the needed `github-mcp-v1_*` write tools.

</details>

<details>
<summary><strong>Debrief Discussion Guide</strong></summary>

- Why is this stronger than “investigate in portal, then file a ticket manually”? → One continuous evidence chain across observability and source.
- What governance controls matter here? → Narrow GitHub scope, explicit repo and connector grants, immutable source, and issue-only write behavior.
- Why is file/line evidence more persuasive than “probably the cart code”? → It makes follow-up engineering actionable.

</details>

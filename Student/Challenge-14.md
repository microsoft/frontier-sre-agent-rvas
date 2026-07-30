[< Previous Challenge](./Challenge-13.md) — **[Home](../README.md)** — [Next Challenge >](./Challenge-15.md)

# Challenge 14 — Application Root Cause Analysis

> **Capability**: Incident Investigation · Telemetry Correlation · Source Code Analysis · GitHub MCP

## Introduction

This is the strongest "wow" challenge. An application failure that starts as a spike in HTTP 5xx errors becomes a full root-cause investigation: from the alert, through container logs and Application Insights telemetry, all the way to the specific line of code that causes an out-of-memory crash — and ends with a GitHub issue linking the evidence to the code.

No human switches tools. No copy-paste between dashboards and editors. The agent connects all three planes — **observability**, **infrastructure**, and **source code** — in a single autonomous thread.

## Description

### Before you start

Verify the Grubify app is healthy and the GitHub connector is authorized:

```bash
make validate-food
```

In the SRE Agent portal, confirm the **github** connector and the **grubify** repository link are active.

### Step 1 — Inject the OOM fault

```bash
make break-food
```

This issues ~200 `POST /api/cart/demo-user/items` requests against the Grubify API. The cart-write path is the out-of-memory fault path in the v1 backend: the container exhausts heap memory, restarts, and returns HTTP 5xx during the restart window.

### Step 2 — Wait for the alert and autonomous response

The `alert-vflta-food-http-5xx` Azure Monitor alert (Sev1, Container Apps HTTP 5xx rate) fires on a 1-minute evaluation window. The response plan `sample-food-http-errors` routes the incident to `aca-app-incident-handler` in **Autonomous** mode (up to 3 investigation attempts).

Watch the portal — within **3–5 minutes** the incident should appear and the agent should begin its investigation.

### Step 3 — Follow the investigation to source code

The `aca-app-incident-handler` will:

1. Query Container Apps HTTP logs and Application Insights for the 5xx spike pattern
2. Identify the `/api/cart/{user}/items` endpoint as the fault path
3. Correlate the restart events with OOM signals in container console logs
4. Hand off to the `code-analyzer` subagent with a summary of findings

The `code-analyzer` subagent will:

1. Search the Grubify repository for the cart endpoint implementation (`search_code`)
2. Retrieve the offending file (`get_file_contents`) and identify the OOM code path
3. Open a GitHub issue with: the root cause, the offending file and line, the telemetry evidence, and recommended fix

### Step 4 — Trigger interactively (if alert didn't fire)

If the alert hasn't fired after 10 minutes, trigger the full investigation manually:

```text
For the current Grubify 5xx incident, analyze the API repository, identify the likely offending code path, and open a GitHub issue with your findings.
```

### Step 5 — Review the GitHub issue

```bash
gh issue list --repo microsoft/frontier-sre-agent-rvas --state open
```

The issue should contain: alert trigger, telemetry evidence, container restart timeline, code path identified, and recommended remediation.

### Step 6 — Restore

```bash
make validate-food
# If not self-healed:

make food-status
```

## Success Criteria

- [ ] The `alert-vflta-food-http-5xx` alert fired and the incident appeared in the portal
- [ ] The agent identified `/api/cart/{user}/items` as the fault path from telemetry
- [ ] The `code-analyzer` subagent retrieved the cart endpoint source code from the Grubify repository
- [ ] A GitHub issue was created with root cause, code evidence, and remediation steps
- [ ] The agent demonstrated the handoff between `aca-app-incident-handler` and `code-analyzer`
- [ ] **Explain to your coach** — what is the governance mechanism that ensures `code-analyzer` can *read* source code and *create issues* but cannot *push commits* or *merge pull requests* without human approval?

## Learning Resources

- [Azure SRE Agent — incident response](https://learn.microsoft.com/en-us/azure/sre-agent/incident-response)
- [Application Insights — exception tracking](https://learn.microsoft.com/en-us/azure/azure-monitor/app/asp-net-exceptions)
- [Azure Container Apps — container restart policies](https://learn.microsoft.com/en-us/azure/container-apps/containers)
- [GitHub MCP server — code search](https://github.com/github/github-mcp-server)

## Tips

- The `aca-app-incident-handler → code-analyzer` handoff is the most sophisticated pattern in this lab. The first agent passes a structured summary (symptom, endpoint, evidence) to the second, which then focuses exclusively on the code. This division of expertise is what makes the pattern scalable.
- The scheduled task `triage-grubify-issues` (cron `0 */12 * * *`) runs independently of this challenge and continuously triages `[Customer Issue]` backlog items. You may see it interleave with your incident during the demo — that's expected behavior.
- If the GitHub issue is created but missing the code reference, confirm the `grubify` repository link is active in the portal and the OAuth connector has `repo` scope.

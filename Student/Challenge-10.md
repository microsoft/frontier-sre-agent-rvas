[< Previous Challenge](./Challenge-09.md) — **[Home](../README.md)** — [Next Challenge >](./Challenge-11.md)

# Challenge 10 — Incident to GitHub Issue

> **Capability**: Incident lifecycle · Engineering workflow · GitHub integration

## Introduction

An alert fires, the agent investigates, and then… what? In a mature SRE practice, every incident generates a traceable artifact: a GitHub issue that captures the root cause, the timeline, the remediation steps, and the follow-up work. That artifact is what turns a one-off incident into institutional knowledge.

In this challenge you'll trigger a Parking Manager incident and direct the agent to open a GitHub issue from the alert — closing the loop between monitoring and the engineering backlog without a human copy-pasting between tools.

## Description

### Before you start

Confirm the Parking Manager is running and the GitHub connector is authorized:

```bash
make validate
```

In the SRE Agent portal, verify the **GitHub MCP** (`github-mcp`) connector shows as connected (green).

### Step 1 — Observe an active incident

Navigate to **Incident Response** in the SRE Agent portal. If a Parking Manager alert is active, note its title and severity. If there is no active alert, trigger one:

```bash
make trigger-parking-down
```

Alternatively, describe a realistic incident from the health report you generated in Challenge 09 — for example, an API with elevated error rate.

### Step 2 — Create a GitHub issue

In the agent chat, prompt:

```text
Create an issue on GitHub to track and resolve this incident. Include: the incident title and severity, a summary of what the monitoring data shows, the affected component, the recommended investigation steps, and any remediation that has already been applied.
```

The agent will:

- Retrieve the incident details from the incident platform
- Query Log Analytics or Application Insights for supporting telemetry
- Compose a structured issue using the `incident-report-template.md` from the knowledge base
- Create the issue via the GitHub MCP (`github-mcp` connector)

### Step 3 — Review the created issue

Find the issue in GitHub:

```bash
gh issue list --repo microsoft/frontier-sre-agent-rvas --state open --label incident
```

Review the issue content. Does it contain:

- Clear title with severity?
- Root cause hypothesis or confirmed root cause?
- Timeline of when the alert fired?
- Recommended next steps?
- Links to relevant Log Analytics or Application Insights queries?

### Step 4 — Add a comment

Ask the agent to update the issue with additional findings:

```text
Add a comment to the GitHub issue with the current API error rate and the top 3 error messages from the last hour.
```

### Step 5 — Clean up

Once you have completed all steps above and the GitHub issue is created, restore the Parking Manager to a healthy state:

```bash
make restore-parking
```

## Success Criteria

- [ ] A GitHub issue is created with a clear title, severity, and structured investigation content
- [ ] The issue references live telemetry (error rate, latency, or log excerpt) from the monitoring stack
- [ ] The agent adds a follow-up comment with updated telemetry when asked
- [ ] **Explain to your coach** — what is the `incident-report-template.md` knowledge document, and why does having a template in the knowledge base produce more consistent GitHub issues than relying on the model's default formatting?

## Learning Resources

- [Azure SRE Agent — GitHub integration](https://learn.microsoft.com/en-us/azure/sre-agent/github-connector)
- [GitHub MCP server](https://github.com/github/github-mcp-server)
- [Azure Monitor — alert management](https://learn.microsoft.com/en-us/azure/azure-monitor/alerts/alerts-manage-alert-instances)
- [SRE Book — Incident Management](https://sre.google/sre-book/managing-incidents/)

## Tips

- The GitHub connector requires the OAuth authorization completed in Challenge 01. If the agent returns a "not authorized" error when creating the issue, re-authorize the connector in the portal.
- The `incident-report-template.md` knowledge document defines the issue structure. If the agent's output doesn't match the expected format, check that the document is in the knowledge base and ask the agent to "use the incident report template."
- You can also ask the agent to label the issue (`incident`, `sev2`, component name) if your GitHub repository has those labels defined.

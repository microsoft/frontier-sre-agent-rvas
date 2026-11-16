---
title: Incident to GitHub Issue
summary: Trigger a Parking Manager incident and have the agent create or update a GitHub issue with evidence, a timeline, and next steps. This workflow reports the incident; it does not restart a VM.
phase: Autonomous
group: Autonomous incident response
tags:
- incident lifecycle
- GitHub integration
- Parking Manager
highlight: false
---

# Challenge 10 — Incident to GitHub Issue

> **Application focus:** Parking Manager only

> **Capability**: Incident lifecycle · Engineering workflow · GitHub integration

## Purpose

- Create or update a GitHub issue with incident evidence and next steps for engineering.
- Expected time: 20 minutes.

## Introduction

Trigger a Parking Manager incident and have the agent create or update a GitHub issue. The issue records the evidence, timeline, root cause or hypothesis, remediation already applied, and recommended next steps.

The workflow hands the incident to engineering. It does not restart a VM.

## Description

### Before you start

Confirm the Parking Manager is running and the GitHub connector is authorized:

```bash
make validate-parking
```

In the SRE Agent portal, verify both parts of the GitHub integration:

- Under **Code Access**, the `grubify` repository is connected for source context
- Under **Builder > Connectors**, **GitHub MCP** (`github-mcp`) is connected (green)
	and authorized for issue operations in `<your-github-username>/frontier-sre-agent-rvas`

Also verify the configuration from earlier challenges:

- The `parking-vm-unhealthy` incident filter is enabled, matches `Parking VM Unhealthy Alert` and routes to `parking-vm-incident-reporter` in Autonomous mode
- The `parking-vm-incident-reporter` subagent and `parking-issues-creator` skill are available
- The `incident-report-template.md` document is present in the knowledge base

### Step 1 — Observe an active incident

Open **Incidents** in the SRE Agent portal. If a Parking Manager alert is active, note its title and severity. Otherwise, trigger one:

```bash
make trigger-parking-report
```

This emits synthetic unhealthy records into `VMHealthStatus_CL`; it does not stop or restart a VM. The `Parking VM Unhealthy Alert` incident might take 3-5 minutes to appear.

### Step 2 — Observe the automation that creates a GitHub issue

Open the Parking incident and follow its investigation timeline. Confirm that the
`parking-vm-unhealthy` filter assigns the incident to `parking-vm-incident-reporter`.
The autonomous investigation should:

- Retrieve the incident details from the incident platform
- Query Log Analytics for supporting telemetry
- Determine whether `vm-health-control` generated the unhealthy event
- Search for an existing open issue for the affected VM
- Compose a structured issue using the `incident-report-template.md` from the knowledge base
- Create an issue through ConnectorV2 GitHub MCP, or comment on an existing matching issue
- Return the created or reused GitHub issue URL in the investigation result

This response plan ends at the engineering handoff. It must not invoke
`az vm restart`; validated remediation is a separate workflow in Challenge 15.

Allow up to five minutes after the alert appears for the investigation
and GitHub operation to complete.

### Step 3 — Create a GitHub issue without automation

If the automatic route is unavailable, describe a realistic incident in the agent
chat. This prompt activates the `parking-issues-creator` skill without using
`/agent`, which is reserved for subagents:

```text
Create an issue on GitHub to track and resolve high latency on the Paris parking API. Include: the incident title and severity, a summary of what the monitoring data shows, the affected component, the recommended investigation steps, and any remediation that has already been applied.
```

The agent will:

- Retrieve the incident details from the incident platform
- Query Log Analytics or Application Insights for supporting telemetry
- Compose a structured issue using the `incident-report-template.md` from the knowledge base
- Create the issue through ConnectorV2 GitHub MCP

### Step 4 — Review the created issue

Find the issue in GitHub:

```bash
gh issue list --repo <your-github-username>/frontier-sre-agent-rvas --state open --search parking
```

Check that the issue contains:

- A clear title with severity
- A root cause hypothesis or confirmed root cause
- A timeline of when the alert fired
- Recommended next steps
- Links to relevant Log Analytics or Application Insights queries

### Step 5 — Add a comment

Ask the agent to update the issue with additional findings:

```text
Add a comment to the GitHub issue with the current API error rate and the top 3 error messages from the last hour.
```

### Step 6 — Clean up

After the GitHub issue is created, restore the Parking Manager to a healthy state:

```bash
make restore-parking-report
```

## Success Criteria

- [ ] A GitHub issue is created with a clear title, severity, and structured investigation content
- [ ] The issue references live telemetry (error rate, latency, or log excerpt) from the monitoring stack
- [ ] The agent adds a follow-up comment with updated telemetry when asked
- [ ] The reporting workflow completes without restarting a Parking VM
- [ ] **Explain in your own words** (two or three written sentences) — what is the `incident-report-template.md` knowledge document, and why does having a template in the knowledge base produce more consistent GitHub issues than relying on the model's default formatting?

## Learning Resources

- [Azure SRE Agent — GitHub integration](https://learn.microsoft.com/en-us/azure/sre-agent/github-connector)
- [Set up an MCP connector](https://learn.microsoft.com/en-us/azure/sre-agent/mcp-connector)
- [Connect source code to Azure SRE Agent](https://learn.microsoft.com/en-us/azure/sre-agent/connect-source-code)
- [Azure Monitor — alert management](https://learn.microsoft.com/en-us/azure/azure-monitor/alerts/alerts-manage-alert-instances)
- [SRE Book — Incident Management](https://sre.google/sre-book/managing-incidents/)

## Tips

- GitHub MCP requires the OAuth authorization completed in Challenge 01. If the agent returns a "not authorized" error when creating the issue, re-authorize `github-mcp` under **Builder > Connectors**.
- The `incident-report-template.md` knowledge document defines the issue structure. If the agent's output doesn't match the expected format, check that the document is in the knowledge base and ask the agent to "use the incident report template."
- You can also ask the agent to label the issue (`incident`, `sev2`, component name) if your GitHub repository has those labels defined.

## Hints and notes

> Hidden until you click. Expand a section only when you want it.

<details>
<summary><strong>Background</strong></summary>

- Prerequisites: Code Access contains the `grubify` repository,
	ConnectorV2 `github-mcp` is green, the `parking-vm-unhealthy` filter routes to
	`parking-vm-incident-reporter` only for `Parking VM Unhealthy Alert`, and the Parking reporter, issue skill, and incident
	template are deployed.
- Knowledge template: `sample-food/incident-report-template.md` drives consistent issue structure.
- Expected lifecycle: incident context → telemetry evidence → issue creation → follow-up comment with updated findings.
- If no live Parking Manager incident exists, it is valid to use a realistic incident derived from Challenge 09’s health report.

</details>

<details>
<summary><strong>Expected Output</strong></summary>

- A GitHub issue exists with clear title, severity, affected component, evidence, and next steps.
- The issue content reflects the knowledge-base template rather than ad hoc prose.
- A follow-up comment adds current error-rate or top-error telemetry.
- You can review the issue in GitHub or via `gh issue list`.
- No VM restart occurs; this workflow ends with a durable engineering handoff.

</details>

<details>
<summary><strong>Common Issues and Hints</strong></summary>

- **Symptom:** Agent says GitHub is not authorized. **Fix:** re-check the `github-mcp` ConnectorV2 OAuth status and issue access under **Builder > Connectors**.
- **Symptom:** The incident appears but no autonomous investigation starts. **Fix:** confirm the `parking-vm-unhealthy` filter is enabled, matches the Sev2 `Parking VM Unhealthy Alert`, and routes to `parking-vm-incident-reporter` in Autonomous mode.
- **Symptom:** The agent restarts a VM instead of creating an issue. **Fix:** the wrong response plan handled the alert; remove broad `titleContains: parking` matching and confirm this alert reaches only `parking-vm-unhealthy`.
- **Symptom:** The reporter cannot find a GitHub operation. **Fix:** redeploy the reporter and skill, then confirm `github-mcp` exposes `github-mcp_issue_write`, `github-mcp_search_issues`, and `github-mcp_add_issue_comment`.
- **Symptom:** Issue is created but structure is inconsistent. **Fix:** tell the agent to use the incident report template.
- **Symptom:** No active incident is available. **Fix:** use an incident narrative derived from the Challenge 09 health report.
- **Symptom:** Comment update lacks fresh evidence. **Fix:** ask specifically for last-hour error rate and top three errors.

</details>

<details>
<summary><strong>Debrief Discussion Guide</strong></summary>

- Why store the template as knowledge instead of relying on the model’s default writing? → Consistency, auditability, and org standards.
- What changed operationally by creating the issue immediately? → Better handoff from on-call to engineering backlog.
- What belongs in the issue vs. what stays in chat history? → Durable evidence and action items belong in GitHub.

</details>

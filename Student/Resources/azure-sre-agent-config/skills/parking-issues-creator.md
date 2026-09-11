---
name: parking-issues-creator
description: Creates GitHub issues for the Parking Manager service. Use when the user asks to file, create, or open a GitHub issue related to parking VMs, APIs, or infrastructure (Paris, Madrid, Lisbon, Berlin).
---

# Parking Manager — GitHub Issue Creator

## When to use this skill

Activate when the user asks to create, file, or open a GitHub issue related to
the Parking Manager service, its VMs, APIs, or supporting infrastructure.

## Target repository

- **Owner:** microsoft
- **Repo:** frontier-sre-agent-rvas

## Procedure

### 1. Gather context

Collect from the user or conversation:

- **Title** — short, descriptive summary
- **Affected component** — Paris API (vm-parking-paris, port 3003),
  Madrid API (vm-parking-madrid, port 3002), Berlin API, frontend,
  chaos control, or general infrastructure
- **Symptoms / description** — what happened, error messages, timestamps
- **Severity** — critical, high, medium, low (if known)
- **Labels** — e.g. bug, enhancement, incident (if known)

### 2. Check for duplicates

Before creating, search existing issues using the GitHub MCP v1 connector tool
`github-mcp-v1_search_issues`:

```
query: "<keywords> repo:<your-github-username>/frontier-sre-agent-rvas is:open"
```

If a matching open issue exists, inform the user and offer to comment on it
instead of creating a duplicate. Read the issue with `github-mcp-v1_issue_read`
and add the new evidence with `github-mcp-v1_add_issue_comment`.

### 3. Format the issue

Search memory for the *Sample Food Ordering App Incident Report Template* and
follow its structure exactly. Adapt the affected-component values and evidence
sources to Parking Manager, but keep every section: Summary, Evidence, Timeline,
Root Cause Hypothesis, Remediation, and Follow-Up. Never leave a section empty;
use `Not observed`, `Not applicable`, or `Unknown` with an explanation when the
available evidence cannot supply a value.

Include the affected Parking resource group, subscription ID, Log Analytics
workspace ID, KQL query, relevant result rows, and whether the event was generated
by `vm-health-control`.

### 4. Create the issue

Use `github-mcp-v1_issue_write` from the GitHub MCP v1 connector server with:

- **Title** prefixed with `[Parking]` — e.g. `[Parking] High latency on Paris API`
- **Body** from the template above
- **Labels** if provided and available in the repo

### 5. Confirm

Return the created or reused issue URL to the user. If an existing issue was
updated, state that a comment was added instead of creating a duplicate.

[< Previous Challenge](./Challenge-02.md) — **[Home](../README.md)** — [Next Challenge >](./Challenge-04.md)

# Challenge 03 — Connectors, Repos & Scheduled Tasks

## Introduction

The final configuration layer connects the SRE Agent to **external systems** and makes it work **proactively** — without waiting for an alert.

- **Connectors** — authenticated integrations to external services (GitHub, MCP servers, knowledge platforms)
- **Repository links** — tell the agent which GitHub repo to read source from and open PRs/issues against
- **Scheduled tasks** — cron-triggered prompts that run a subagent on a recurring basis

In Challenge 00 you applied all three as part of the full desired-state config. In this challenge you'll write a new scheduled task from scratch and understand how the connector → repo → subagent dependency chain works.

## Description

### Step 1 — Understand the connector YAML format

Open the active GitHub connector:

```bash
cat Coach/Solutions/azure-sre-agent-config/connectors/github.yaml
```

Key fields:
```yaml
api_version: azuresre.ai/v1
kind: DataConnector
metadata:
  name: github
spec:
  dataConnectorType: GitHubOAuth    # OAuth flow — no PAT, requires portal auth
  description: >-
    GitHub OAuth connector ...
```

The connector type (`GitHubOAuth` vs. `GitHubMCP`) determines how credentials are handled. The `metadata.name` is what other YAMLs reference as `authConnectorName`.

Also look at the MCP connector example:
```bash
cat Coach/Solutions/azure-sre-agent-config/connectors/microsoft-learn-mcp.yaml
```

### Step 2 — Understand the repository link format

```bash
cat Coach/Solutions/azure-sre-agent-config/repos/grubify.yaml
```

Key fields:
```yaml
api_version: azuresre.ai/v1
kind: Repository
metadata:
  name: grubify           # short label used in agent prompts
spec:
  url: https://github.com/microsoft/frontier-sre-agent-rvas
  type: GitHub
  authConnectorName: github    # must match a connector metadata.name
  description: >-
    <what this repo contains and why the agent should read it>
```

The `description` is injected into the agent's context so it knows **which repo to use for which purpose**. A good description includes: what application lives here, where the relevant source is (subfolder), and what the agent is authorized to do (read, open PRs, manage issues).

### Step 3 — Understand the scheduled task format

```bash
cat Coach/Solutions/azure-sre-agent-config/automations/scheduled-tasks/triage-grubify-issues.yaml
```

Key fields:
```yaml
api_version: azuresre.ai/v1
kind: ScheduledTask
metadata:
  name: <unique-name>
spec:
  description: <one sentence what this task does>
  schedule: "0 */12 * * *"    # standard 5-field cron (UTC)
  time_zone: UTC
  enabled: true
  agent: <subagent-name>       # which subagent runs this task
  mode: Autonomous
  prompt: >-
    <the full prompt sent to the subagent at each scheduled run>
```

The `prompt` is the most important field: it should be specific enough that the agent produces a consistent, useful output without human guidance.

### Step 4 — Write a new scheduled task

Create `Coach/Solutions/azure-sre-agent-config/automations/scheduled-tasks/<your-task-name>.yaml`.

Ideas for a useful scheduled task:
- **Daily resource tag compliance check** — prompt `azure-resource-config-auditor` to list resources missing required tags in the lab resource group
- **Weekly stale revision cleanup** — prompt `aca-app-incident-handler` to deactivate Container Apps revisions with zero traffic that are more than 7 days old
- **Hourly flow log freshness check** — prompt `network-traffic-analyst` to verify VNet Flow Log ingestion has data from the last 15 minutes

Requirements for your task:
- Schedule: at least once per day (or more frequent for demo purposes)
- Agent: must reference an existing subagent by exact name
- Prompt: must be actionable — the agent should be able to complete it without clarification
- `enabled: true` so it can be manually triggered from portal

### Step 5 — Apply your scheduled task

```bash
cd Coach/Solutions
./infra/scripts/sre-agent-config.sh apply --target scheduled-tasks --name <your-task-name>
```

### Step 6 — Verify and manually trigger

1. Navigate to **Automations → Scheduled Tasks** in the portal
2. Confirm your task appears with the correct schedule and agent assignment
3. Click **Run now** to manually trigger the task
4. Observe the agent's response in the task execution log

## Success Criteria

- [ ] A valid `<task-name>.yaml` exists under `automations/scheduled-tasks/` and appears in the portal
- [ ] You successfully manually triggered the task and observed agent output
- [ ] You can explain the **connector → repo → subagent dependency chain**: why the repo needs a connector, and why the agent needs the repo
- [ ] You can explain the difference between a `ScheduledTask` prompt and an incident filter's `customInstructions`
- [ ] You can write a valid 5-field cron expression and explain when it fires

## Learning Resources

- [Azure SRE Agent — Connectors documentation](https://learn.microsoft.com/en-us/azure/sre-agent/connectors)
- [Azure SRE Agent — Scheduled tasks](https://learn.microsoft.com/en-us/azure/sre-agent/scheduled-tasks)
- [Cron expression syntax](https://en.wikipedia.org/wiki/Cron#CRON_expression)
- Existing tasks in `Coach/Solutions/azure-sre-agent-config/automations/scheduled-tasks/`

## Tips

- **Cron is UTC.** If you want a task to run at 9 AM local time, convert to UTC. Use `0 7 * * *` for UTC+2.
- The `agent` field is case-sensitive and must exactly match a registered subagent's `metadata.name`.
- A `prompt` that says "investigate everything" produces poor results. A prompt that says "list all resources in resource group `<rg>` missing the `env` tag and report them as a Markdown table" produces a consistent, usable output.
- The `example-` prefix convention: files named `example-*.yaml` are excluded by `sre-agent-config.sh`. Use this to keep a template without applying it.
- You can chain the repo link and connector check: `./infra/scripts/sre-agent-config.sh verify --target connectors` to confirm the OAuth connection is still active before running tasks that depend on it.

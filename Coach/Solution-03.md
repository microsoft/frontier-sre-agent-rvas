[< Previous Solution](./Solution-02.md) | **[Home](./README.md)** | [Next Solution >](./Solution-04.md)

# Coach Guide — Challenge 03: Connectors, Repos & Scheduled Tasks

## Purpose

This challenge completes the configuration layer by teaching the **external integration** and **proactive automation** primitives. By the end, students understand the full dependency chain: OAuth connector → repo link → subagent with GitHub tools → scheduled task that uses all three. This sets up Challenge 06 (issue-triager) perfectly.

Expected time: **20–25 minutes**.

## Mini-Lecture (5 min before challenge)

Cover the dependency chain:

```
DataConnector (github)       ← holds OAuth credentials
      │ authConnectorName
      ▼
Repository (grubify)         ← tells the agent which repo + why
      │ referenced in subagent context
      ▼
SubAgent (issue-triager)     ← has GitHub tools granted
      │ runs as
      ▼
ScheduledTask (triage-grubify-issues)  ← cron trigger + prompt
```

Key points:
- The connector type determines auth: `GitHubOAuth` (portal flow, no secrets) vs. `GitHubMCP` (PAT, stored in Key Vault)
- The repo `description` is injected into the agent's context — it's how the agent knows which repo to use for which purpose. Quality of description = quality of repo selection.
- A scheduled task's `prompt` is the full instruction set. It runs unattended — it must be self-contained.
- `enabled: false` → task is registered but won't auto-run. `enabled: true` → auto-runs on schedule AND can be manually triggered from portal.

## Expected Student Output

- A valid `ScheduledTask` YAML with: unique name, valid cron expression, existing subagent reference, actionable and specific prompt
- Task applied and visible in portal under **Automations → Scheduled Tasks**
- Manual trigger executed and agent output observed

## Common Issues and Hints

### `agent` field references a subagent that doesn't exist
- Apply will succeed (the API doesn't validate agent existence at write time) but the task will fail when it runs
- Run `./sre-agent-config.sh verify --target subagents` to list registered subagents, then check the exact name
- Common mistake: using the subagent's `description` instead of `metadata.name`

### Cron expression fires at unexpected time
- The schedule is UTC — 5-field cron, no seconds field
- Common patterns:
  - `0 9 * * 1-5` = 9 AM UTC weekdays
  - `*/30 * * * *` = every 30 minutes
  - `0 0 * * *` = midnight UTC daily
- Coach tip: use [crontab.guru](https://crontab.guru) to verify expression

### "Run now" button is grayed out or missing
- Task must be `enabled: true`. If student has `enabled: false`, re-apply with it set to true.
- If the button is still missing, the task may not have applied successfully — check `verify` output

### Prompt is too vague and agent output is useless
- A prompt like "check the resources" produces a generic response with no actionable finding
- Coach prompt: "If you were a new employee and your manager sent you this exact message, what would you do?" — the answer should be unambiguous
- Good prompts: name the resource group, the specific check, the exact output format expected

### Student tries to reference a connector that doesn't exist yet
- Connectors must be applied before repo links that reference them
- If applying a repo that references `github` and the connector isn't applied, the API may error
- Resolution: apply connectors first, then repos, then tasks

## Debrief Discussion Guide (5 min)

1. **What happens if the scheduled task's subagent doesn't have the right tool grants?** — The task fires, the agent tries, fails to call the tool, and either errors or produces an empty result. The task itself won't error — the failure is silent. Discuss: how would you detect this? (Answer: task execution logs in portal, or check for missing tool in agent output)
2. **What's the right frequency for a scheduled task?** — Depends on the cost of the operation vs. the value of the information. A task that runs KQL against Log Analytics every 5 minutes at scale costs real money. Discuss: rate limiting, sampling, alert-driven vs. poll-driven.
3. **How would you extend the `triage-grubify-issues` task for YOUR team's issue tracker?** — Surfaces whether students would use GitHub Issues, Azure DevOps, Jira — and what connector/integration changes that would require.

## Success Criteria Notes

- The cron expression is technically correct (5 fields, valid range values) — ask the student to say out loud when the task would fire
- The manual trigger produces **visible agent output** — not just "task ran" but an actual response in the execution log
- Accept any valid prompt, but discuss quality — the debrief question about "new employee" is a good calibration tool
- Bonus: if a student writes both a scheduled task AND a new connector for a different service (e.g., a mock MCP endpoint), award extra credit and discuss the connector extension pattern

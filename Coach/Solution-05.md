[< Previous Solution](./Solution-04.md) | **[Home](./README.md)** | [Next Solution >](./Solution-06.md)

# Coach Guide — Challenge 02: Code Correlation & GitHub Integration

## Purpose

This challenge pushes the agent from **infrastructure-level diagnosis** to **developer-level root cause analysis**: reading source code, correlating log evidence to a specific file and line, and producing a pull request. It demonstrates the GitHub OAuth connector and shows that an AI agent can operate across the observability ↔ code ↔ version-control boundary.

The key architectural note: `code-analyzer` capabilities are **inlined into `aca-app-incident-handler`** — agent-to-agent handoffs are not supported in workspace mode, so the code correlation logic lives directly in the incident handler's system prompt.

Expected time: **15–20 minutes** (alert already fired or student uses manual trigger).

## Mini-Lecture (5 min before challenge)

Cover:
- The GitHub OAuth connector: `dataConnectorType: GitHubOAuth` — no PAT, no secrets, one-time portal authorization
- What changes from S1 to S2: same incident, same agent, but with GitHub tools the agent can now read source and write branches/PRs
- The Grubify source layout: `Student/Resources/grubify/GrubifyApi/Controllers/` — the failing code path
- The PR the agent creates: branch → commit → PR with incident context embedded in the description

## Prerequisite Check

Before starting, confirm in the portal: **Connectors → github → status = Connected**. If not, coach the student through the OAuth authorization step (Connectors → github → Authorize). This takes 2 minutes and must be done by someone with write access to the repo.

## Expected Agent Behavior

1. Agent receives the same `food-5xx` incident (or student triggers investigation via chat)
2. Queries App Insights + Container Apps logs for 5xx evidence (same as S1)
3. Uses GitHub tools (`get_file_contents`, `search_code`) to read `GrubifyApi/Controllers/`
4. Identifies the controller method + line that throws the error (based on the injected fault)
5. Creates a branch: `fix/grubify-api-5xx-<timestamp>`
6. Commits a change to the affected file
7. Opens a PR with: incident summary, log evidence, file:line reference, proposed fix

## Common Issues and Hints

### Agent says "GitHub tool not authorized" or similar
- OAuth was not completed. Navigate to Connectors → github in the portal and complete authorization
- After authorization, retry the prompt — the agent does not need to be restarted

### Agent reads source but doesn't create a PR
- The agent may produce a detailed investigation + diff proposal without actually committing. This is acceptable as a partial outcome
- Coach prompt: "Ask the agent explicitly: 'Create a branch and open a pull request with the fix you described'"

### PR created with wrong base branch or empty diff
- The injected fault from `break-sample-food-app.sh` is an environment variable change, not a code change. The agent may create a PR that updates an appsettings or configuration file rather than a controller — this is technically correct
- Accept any PR that references the incident and proposes a fix, even if the fix is non-trivial

### Student has write access issues
- The student's GitHub account must have write access to `microsoft/frontier-sre-agent-rvas` for the agent (acting as their OAuth identity) to create branches
- If the agent gets a 403, the OAuth token doesn't have write permissions — discuss and move on, treat the investigation report as the artifact

## Debrief Discussion Guide (10 min)

1. **What is the value of crossing the observability↔code boundary?** — The agent found the issue in 5 minutes; a developer would spend 30 minutes correlating a stack trace to source
2. **What are the risks of an agent that commits code?** — Incorrect fixes, force-pushes, PR pollution — this is an intentional provocation for a governance discussion
3. **How would you put guardrails on this in production?** — PR approval gates, dry-run mode, limited branch scope, PR-only (no direct push)

## Success Criteria Notes

- GitHub issue or PR is the primary artifact — accept partial credit for a detailed investigation with file:line references even without a PR
- The student should be able to identify which controller file the agent focused on
- Decline to accept "the agent didn't do anything" — prompt the student to verify OAuth is authorized and retry

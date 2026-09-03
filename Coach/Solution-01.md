[< Previous Solution](./Solution-00.md) | **[Home](./README.md)** | [Next Solution >](./Solution-02.md)

# Coach Guide — Challenge 01: Connect Your Codebase

## Purpose

- Teach the difference between **authentication to GitHub** and **scope to a specific repository**.
- This unlocks every code-aware scenario later: issue triage, code correlation, and GitHub issue creation.
- Expected time: 15 minutes.

## Mini-Lecture (3–5 min before challenge)

- Draw the split: `github-mcp` connector = identity/session to GitHub; `grubify` repository = what repo the agent is allowed to reason over.
- Show the exact apply order: `make connectors` → portal **Authorize** on `GitHub MCP` → `make repos`.
- Mention that `grubify.yaml` points to the repository's own `origin` remote (`GRUBIFY_REPO_URL`), so students see their own fork/copy, not a hardcoded URL.
- Make the source boundary explicit: the agent can read code and create incident issues, but it cannot edit Grubify source, push branches, or open pull requests in this lab.
- Coach prompt to use before config: “Find the cart endpoint implementation.” The refusal is part of the lesson.

## Expected Student Output

- Before setup, the agent declines to inspect Grubify source or list real GitHub issues.
- After OAuth, the **GitHub MCP** connector is green in the portal.
- After `make repos`, the **grubify** repository appears under Repositories.
- The agent can describe the cart endpoint implementation and list open issues from the real repo.

## Common Issues and Hints

- **Symptom:** `make connectors` succeeds but GitHub tools still fail. **Fix:** students missed the one-time portal **Authorize** step.
- **Symptom:** Repo object exists but code reads still fail. **Fix:** confirm the connector shows Authorized (green) — the repository resource has no `authConnectorName` field; it relies on the connector's own GitHub access.
- **Symptom:** Student authenticated `gh` CLI but agent still cannot reach GitHub. **Fix:** remind them CLI auth is separate from the portal OAuth connector.
- **Symptom:** Agent lists generic folder guesses, not real files. **Fix:** verify the repository link is active and ask again with a concrete file-finding task.

## Debrief Discussion Guide

- Why separate connector and repository? → Auth without scope is unsafe; scope without auth is unusable.
- What governance boundary did we add? → The agent can reach only explicitly connected repos, not arbitrary GitHub.
- What prevents source modification? → The code specialist has read-only Azure tools, an explicit immutable-source instruction, and no branch/push/PR workflow in scope.
- Why is this needed before incident-to-code scenarios? → Telemetry alone cannot prove root cause in source.

## Success Criteria Notes

- Require students to demonstrate both states: pre-connector failure and post-connector success.
- Do not accept “it should work now” without portal-green connector status.
- If issue listing works but code search does not, push on repository-link validation specifically.

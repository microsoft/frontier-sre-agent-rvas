[< Previous Solution](./Solution-00.md) | **[Home](./README.md)** | [Next Solution >](./Solution-02.md)

# Coach Guide — Challenge 01: Connect Your Codebase

## Purpose

- Teach the difference between **authentication to GitHub** and **scope to a specific repository**.
- This unlocks every code-aware scenario later: issue triage, code correlation, and GitHub issue creation.
- Expected time: 15 minutes.

## Mini-Lecture (3–5 min before challenge)

- Draw the three-way split: ConnectorV2 `github-mcp` = OAuth-authorized GitHub actions in interactive chats; legacy `github-mcp-v1` = PAT-authenticated GitHub actions in incident automation threads; Code Access `grubify` = the source clone the agent searches and reads.
- Explain that both GitHub connectors are temporarily required because ConnectorV2 tools are not yet exposed to incident automation threads. Challenge 10 therefore uses the legacy connector to create incident-tracking issues. The legacy connector can be removed once ConnectorV2 closes this gap.
- Before deployment, have students create a repository-limited PAT that can create issues and pull requests, then load it into `GITHUB_PAT` without placing the credential in code or source control.
- Show the exact apply order: export `GITHUB_PAT` → `make connectors` → portal **Authorize** on `GitHub MCP` → `make repos`.
- Mention that `grubify.yaml` points to the repository's own `origin` remote (`GRUBIFY_REPO_URL`), so students see their own fork/copy, not a hardcoded URL.
- Make the source boundary explicit: Code Access provides read-only source context. ConnectorV2 tools provide governed issue and pull-request actions, with branch and pull-request operations requiring approval.
- Coach prompt to use before config: “Find the cart endpoint implementation.” The refusal is part of the lesson.

## Expected Student Output

- Before setup, the agent declines to inspect Grubify source or list real GitHub issues.
- `make connectors` deploys both ConnectorV2 `github-mcp` and legacy `github-mcp-v1`.
- After OAuth, the **GitHub MCP** connector is green in the portal.
- After `make repos`, the **grubify** repository appears under Repositories.
- The agent can describe the cart endpoint implementation and list open issues from the real repo.

## Common Issues and Hints

- **Symptom:** `make connectors` succeeds but GitHub tools still fail. **Fix:** students missed the one-time portal **Authorize** step.
- **Symptom:** `make connectors` reports a missing `GITHUB_PAT`, or incident automation cannot create an issue. **Fix:** load a repository-limited PAT with issue and pull-request write access into the `GITHUB_PAT` environment variable, then deploy both connectors again. Never put the PAT in YAML, `.env`, or source control.
- **Symptom:** Repo object exists but code reads still fail. **Fix:** inspect the Code Access repository status and URL. Its source clone is independent of `github-mcp` OAuth and has no `authConnectorName` field.
- **Symptom:** Student authenticated `gh` CLI but agent still cannot reach GitHub. **Fix:** remind them CLI auth is separate from the portal OAuth connector.
- **Symptom:** Agent lists generic folder guesses, not real files. **Fix:** verify the repository link is active and ask again with a concrete file-finding task.

## Debrief Discussion Guide

- Why two GitHub connectors and a repository link? → ConnectorV2 supplies OAuth-authenticated GitHub actions in interactive chats, the legacy connector temporarily supplies PAT-authenticated actions in incident automation threads, and Code Access supplies governed source context. Each has its own policy boundary.
- What governance boundary did we add? → The agent can reach only explicitly connected repos, not arbitrary GitHub.
- What prevents source modification? → The code specialist has read-only Azure tools, an explicit immutable-source instruction, and no branch/push/PR workflow in scope.
- Why is this needed before incident-to-code scenarios? → Telemetry alone cannot prove root cause in source.

## Success Criteria Notes

- Require students to demonstrate both states: pre-connector failure and post-connector success.
- Do not accept “it should work now” without portal-green connector status.
- If issue listing works but code search does not, push on repository-link validation specifically.

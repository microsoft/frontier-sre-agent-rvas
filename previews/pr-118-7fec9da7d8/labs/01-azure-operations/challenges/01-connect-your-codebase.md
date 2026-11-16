---
title: Connect Your Codebase
summary: Connect GitHub and link your repository. Verify that the agent can read source code and use GitHub actions within the configured scope.
phase: Config
group: Agent configuration
tags:
- GitHub OAuth
- repository
- oauth-connector
highlight: false
---

# Challenge 01 — Connect Your Codebase

> **Application focus:** Grubify (Sample Food) only

> **Capabilities added in this challenge**: GitHub OAuth Connector · Repository Connection

## Purpose

- Connect GitHub, then link one repository, and show that the agent can read that repository's code but no other.
- This unlocks every code-aware scenario later: issue triage, code correlation, and GitHub issue creation.
- Expected time: 15 minutes.

## Introduction

Your agent is running but cannot reach your GitHub repository. Test this by asking it to read the Grubify cart service or list open issues.

The GitHub OAuth connector gives scoped access for GitHub actions. The repository link gives Code Access the Grubify source to search and read. Configure both to connect incident investigations with source code, issues, and proposed fixes.

## Description

### Step 1 — Try to access the codebase (before connector)

Open the **SRE Agent portal** and start a new chat session. Ask:

```text
Look at the Grubify repository source code. Find the cart endpoint implementation and describe what it does.
```

The agent will decline because it has no GitHub access. Also try:

```text
Are there any open GitHub issues for the Grubify application?
```

Neither request can succeed yet.

### Step 2 — Authenticate the GitHub CLI

```bash
gh auth login
```

> **Why this is needed:** The `gh` CLI authentication is separate from the SRE Agent's portal OAuth (Step 4). The CLI is used in later challenges to inspect GitHub from your terminal — `gh issue list` (Challenges 10, 14) and `gh pr list` (Challenge 14). Authenticate it once here so it's ready when you need it.

### Step 3 — Apply both GitHub connectors

The lab needs two GitHub connectors. The new GitHub OAuth connector handles interactive agent chats, but its tools are not yet exposed to threads
started by incident automations. Those threads need the legacy GitHub MCP
connector for GitHub actions. For example, the incident automation in Challenge 10 uses
the legacy connector to open a GitHub issue.

The legacy connector authenticates with a GitHub Personal Access Token (PAT). Create a PAT limited to the lab repository that can create
issues and pull requests; later challenges use it to open incident-tracking issues
and submit proposed fixes. Then load the PAT into the `GITHUB_PAT` environment variable before
deploying the connectors:

```bash
read -rsp "GitHub PAT: " GITHUB_PAT && export GITHUB_PAT && echo
```

This prompt does not display the PAT or include it in the command itself. Keep the credential only
in the environment for the current shell session; do not add it to connector YAML, `.env` files,
or source control.

Deploy both connectors from `labs/01-azure-operations/resources/azure-sre-agent-config/connectors/`:

```bash
make connectors
```

You can drop the legacy connector once GitHub OAuth tools become available to incident
automation threads.

### Step 4 — Complete the OAuth authorization in the portal

Applying the YAML registers the connector. You must then authorize it separately:

1. In the SRE Agent portal, go to **Connectors**.
2. Select **GitHub MCP**.
3. Select **Authorize** and complete the GitHub sign-in.

The connector should show as connected (green).

### Step 5 — Add the Grubify repository link

Code Access gives the agent a governed source clone for search and file reads. Configure the
repository independently of the ConnectorV2 GitHub MCP server, which handles issue and pull-request
actions:

```bash
make repos
```

Verify under **Code Access** in the portal — the Grubify repository should be listed.

### Step 6 — Test the connection

Repeat the requests from Step 1:

```text
Look at the Grubify repository source code. Find the cart endpoint implementation and describe what it does.
```

The agent should now use Code Access to search and read the actual implementation.

```text
Are there any open GitHub issues for the Grubify application?
```

The agent should now list real issues from the repository.

Also try:

```text
What is the folder structure of the Grubify application? What services does it contain?
```

### Step 7 — Understand the governance boundary

```text
Can you access any GitHub repository, or only the ones explicitly connected to this agent?
```

The agent should confirm that source context comes from explicitly connected Code Access
repositories. ConnectorV2 GitHub actions are separately limited by OAuth repository access,
agent tool allowlists, approval policy, and agent instructions.

## Success Criteria

- [ ] Before adding the connector, the agent cannot access the Grubify repository
- [ ] After applying the connector and completing OAuth, the agent retrieves actual Grubify source code
- [ ] The Grubify repository appears under **Repositories** in the portal
- [ ] The agent can list open GitHub issues for the Grubify application
- [ ] **Explain in your own words** (two or three written sentences) — what is the difference between the GitHub OAuth connector and the repository link? Why are they configured separately?

## Learning Resources

- [Azure SRE Agent — connectors](https://learn.microsoft.com/en-us/azure/sre-agent/connectors)
- [GitHub MCP server](https://github.com/github/github-mcp-server)
- [GitHub OAuth Apps overview](https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/authorizing-oauth-apps)

## Tips

- The OAuth authorization in the portal is a separate step from applying the YAML — both are required before GitHub tools become available.
- The Code Access repository has no `authConnectorName` field because it is independent of the ConnectorV2 GitHub MCP connection.
- This challenge unlocks all source-code use cases in the workshop: root cause correlation (Challenge 14), incident-to-issue (Challenge 10), and autonomous fix pull requests (Challenge 14).
- After this challenge: the agent can read code but knows nothing about your Azure environment or operational runbooks. Knowledge documents come next.

## Hints and notes

> Hidden until you click. Expand a section only when you want it.

<details>
<summary><strong>Background</strong></summary>

- Three pieces work together: ConnectorV2 `github-mcp` gives OAuth-authorized GitHub actions in interactive chats; legacy `github-mcp-v1` gives PAT-authenticated GitHub actions in incident automation threads; Code Access `grubify` is the source clone the agent searches and reads.
- Both GitHub connectors are temporarily required because ConnectorV2 tools are not yet exposed to incident automation threads. Challenge 10 therefore uses the legacy connector to create incident-tracking issues. You can remove it once ConnectorV2 closes this gap.
- Before deployment, create a repository-limited PAT that can create issues and pull requests, then load it into `GITHUB_PAT` without placing the credential in code or source control.
- Apply order: export `GITHUB_PAT` → `make connectors` → portal **Authorize** on `GitHub MCP` → `make repos`.
- `grubify.yaml` points to the repository's own `origin` remote (`GRUBIFY_REPO_URL`), so you see your own fork, not a hardcoded URL.
- Code Access provides read-only source context. ConnectorV2 tools provide governed issue and pull-request actions, with branch and pull-request operations requiring approval.
- The refusal you get before setup is part of the lesson.

</details>

<details>
<summary><strong>Expected Output</strong></summary>

- Before setup, the agent declines to inspect Grubify source or list real GitHub issues.
- `make connectors` deploys both ConnectorV2 `github-mcp` and legacy `github-mcp-v1`.
- After OAuth, the **GitHub MCP** connector is green in the portal.
- After `make repos`, the **grubify** repository appears under Repositories.
- The agent can describe the cart endpoint implementation and list open issues from the real repo.

</details>

<details>
<summary><strong>Common Issues and Hints</strong></summary>

- **Symptom:** `make connectors` succeeds but GitHub tools still fail. **Fix:** you missed the one-time portal **Authorize** step.
- **Symptom:** `make connectors` reports a missing `GITHUB_PAT`, or incident automation cannot create an issue. **Fix:** load a repository-limited PAT with issue and pull-request write access into the `GITHUB_PAT` environment variable, then deploy both connectors again. Never put the PAT in YAML, `.env`, or source control.
- **Symptom:** Repo object exists but code reads still fail. **Fix:** inspect the Code Access repository status and URL. Its source clone is independent of `github-mcp` OAuth and has no `authConnectorName` field.
- **Symptom:** You authenticated `gh` CLI but the agent still cannot reach GitHub. **Fix:** CLI auth is separate from the portal OAuth connector.
- **Symptom:** Agent lists generic folder guesses, not real files. **Fix:** verify the repository link is active and ask again with a concrete file-finding task.

</details>

<details>
<summary><strong>Debrief Discussion Guide</strong></summary>

- Why two GitHub connectors and a repository link? → ConnectorV2 supplies OAuth-authenticated GitHub actions in interactive chats, the legacy connector temporarily supplies PAT-authenticated actions in incident automation threads, and Code Access supplies governed source context. Each has its own policy boundary.
- What boundary did you add? → The agent can reach only explicitly connected repos, not arbitrary GitHub.
- What prevents source modification? → The code specialist has read-only Azure tools, an explicit immutable-source instruction, and no branch/push/PR workflow in scope.
- Why is this needed before incident-to-code scenarios? → Telemetry alone cannot prove root cause in source.

</details>

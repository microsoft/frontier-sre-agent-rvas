[< Previous Challenge](./Challenge-00.md) — **[Home](../README.md)** — [Next Challenge >](./Challenge-02.md)

# Challenge 01 — Connect Your Codebase

> **Capabilities added in this challenge**: GitHub OAuth Connector · Repository Connection

## Introduction

Your agent is running but completely isolated from your source code. Ask it to read the Grubify cart service implementation and it will decline — it has no access to GitHub. Ask it to list open issues and it cannot reach your repository.

**The GitHub OAuth connector** gives the agent a secure, scoped connection to GitHub. **The repository link** tells it which repository to treat as the Grubify source of truth. Together they unlock code navigation, issue reading, and pull request creation — the foundation for every use case that correlates a live incident with source code.

## Description

### Step 1 — Try to access the codebase (before connector)

Open the **SRE Agent portal** and start a new chat session. Ask:

```text
Look at the Grubify repository source code. Find the cart endpoint implementation and describe what it does.
```

The agent will decline — it has no GitHub access. Also try:

```text
Are there any open GitHub issues for the Grubify application?
```

Without a GitHub connector, neither request can succeed.

### Step 2 — Authenticate the GitHub CLI

```bash
gh auth login
```

> **Why this is needed:** The `gh` CLI authentication is separate from the SRE Agent's portal OAuth (Step 4). The CLI is used in later challenges to inspect GitHub from your terminal — `gh issue list` (Challenges 10, 14) and `gh pr list` (Challenge 14). Authenticate it once here so it's ready when you need it.

### Step 3 — Apply the GitHub OAuth connector

Apply the connector YAML from `Student/Resources/azure-sre-agent-config/connectors/`:

```bash
make connectors
```

### Step 4 — Complete the OAuth authorization in the portal

Applying the YAML registers the connector. The OAuth authorization is a separate, mandatory step:

1. In the SRE Agent portal, navigate to **Connectors**
2. Click on **github**
3. Click **Authorize** and complete the GitHub sign-in

The connector should show as connected (green).

### Step 5 — Add the Grubify repository link

The connector gives the agent access to GitHub. The repository link tells it which repository to focus on:

```bash
make repos
```

Verify under **Repositories** in the portal — the Grubify repository should be listed.

### Step 6 — Test the connection

Repeat the requests from Step 1:

```text
Look at the Grubify repository source code. Find the cart endpoint implementation and describe what it does.
```

The agent should now call `search_code` and `get_file_contents` and return the actual implementation.

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

The agent should confirm that only explicitly connected repositories are reachable — this is the governance boundary.

## Success Criteria

- [ ] Before adding the connector, the agent cannot access the Grubify repository
- [ ] After applying the connector and completing OAuth, the agent retrieves actual Grubify source code
- [ ] The Grubify repository appears under **Repositories** in the portal
- [ ] The agent can list open GitHub issues for the Grubify application
- [ ] **Explain to your coach** — what is the difference between the GitHub OAuth connector and the repository link? Why are they configured separately?

## Learning Resources

- [Azure SRE Agent — connectors](https://learn.microsoft.com/en-us/azure/sre-agent/connectors)
- [GitHub MCP server](https://github.com/github/github-mcp-server)
- [GitHub OAuth Apps overview](https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/authorizing-oauth-apps)

## Tips

- The OAuth authorization in the portal is a separate step from applying the YAML — both are required before GitHub tools become available.
- The `authConnectorName` field in the repository YAML links the repository to the GitHub connector. If the connector name changes, the repo spec must match.
- This challenge unlocks all source-code use cases in the workshop: root cause correlation (Challenge 14), incident-to-issue (Challenge 10), and autonomous fix pull requests (Challenge 14).
- After this challenge: the agent can read code but knows nothing about your Azure environment or operational runbooks. Knowledge documents come next.

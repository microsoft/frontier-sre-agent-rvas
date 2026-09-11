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

Before the hybrid integration is configured, neither request can succeed.

### Step 2 — Authenticate the GitHub CLI

```bash
gh auth login
```

> **Why this is needed:** The `gh` CLI authentication is separate from the SRE Agent's portal OAuth (Step 4). The CLI is used in later challenges to inspect GitHub from your terminal — `gh issue list` (Challenges 10, 14) and `gh pr list` (Challenge 14). Authenticate it once here so it's ready when you need it.

### Step 3 — Apply both GitHub connectors

The workshop currently requires two GitHub connectors. The new GitHub OAuth connector is the
primary connector for interactive agent chats, but its tools are not yet exposed to threads
started by incident automations. Those threads therefore also need the legacy GitHub MCP
connector to perform GitHub actions. For example, the incident automation in Challenge 10 uses
the legacy connector to open a GitHub issue.

Unfortunately, the legacy connector requires a GitHub Personal Access Token (PAT) for
authentication. Create a PAT in GitHub that is limited to the workshop repository and can create
issues and pull requests. Later challenges use these permissions to open incident-tracking issues
and submit proposed fixes. Then load the PAT into the `GITHUB_PAT` environment variable before
deploying the connectors:

```bash
read -rsp "GitHub PAT: " GITHUB_PAT && export GITHUB_PAT && echo
```

This prompt does not display the PAT or include it in the command itself. Keep the credential only
in the environment for the current shell session; do not add it to connector YAML, `.env` files,
or source control.

Deploy both connectors from `Student/Resources/azure-sre-agent-config/connectors/`:

```bash
make connectors
```

This dual-connector setup is temporary. Once the GitHub OAuth connector exposes its tools to
incident automation threads, the legacy GitHub MCP connector will no longer be required.

### Step 4 — Complete the OAuth authorization in the portal

Applying the YAML registers the connector. The OAuth authorization is a separate, mandatory step:

1. In the SRE Agent portal, navigate to **Connectors**
2. Click on **GitHub MCP**
3. Click **Authorize** and complete the GitHub sign-in

The connector should show as connected (green).

### Step 5 — Add the Grubify repository link

Code Access gives the agent a governed source clone for search and file reads. Configure the
repository independently from the ConnectorV2 GitHub MCP server used for issue and pull-request
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
- [ ] **Explain to your coach** — what is the difference between the GitHub OAuth connector and the repository link? Why are they configured separately?

## Learning Resources

- [Azure SRE Agent — connectors](https://learn.microsoft.com/en-us/azure/sre-agent/connectors)
- [GitHub MCP server](https://github.com/github/github-mcp-server)
- [GitHub OAuth Apps overview](https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/authorizing-oauth-apps)

## Tips

- The OAuth authorization in the portal is a separate step from applying the YAML — both are required before GitHub tools become available.
- The Code Access repository has no `authConnectorName` field because it is independent of the ConnectorV2 GitHub MCP connection.
- This challenge unlocks all source-code use cases in the workshop: root cause correlation (Challenge 14), incident-to-issue (Challenge 10), and autonomous fix pull requests (Challenge 14).
- After this challenge: the agent can read code but knows nothing about your Azure environment or operational runbooks. Knowledge documents come next.

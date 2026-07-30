[< Previous Challenge](./Challenge-03.md) — **[Home](../README.md)** — [Next Challenge >](./Challenge-05.md)

# Challenge 04 — Discover Connected Systems

> **Capabilities added in this challenge**: MCP Connectors

## Introduction

Your agent can investigate the Azure environment (Challenge 03) but when it answers questions about Azure best practices it draws only on its training data — potentially stale, uncited, and not tied to the current state of the documentation.

**MCP connectors** break that limitation. Through the Model Context Protocol, the agent reaches into external systems in real time. In this challenge you'll connect the agent to **Microsoft Learn** — so every documentation answer comes from the live, citable source rather than from model memory.

## Description

### Step 1 — Test the missing connection (before connector)

In the SRE Agent portal, ask:

```text
What does the official Azure documentation recommend for investigating Container Apps HTTP 5xx errors? Cite the article.
```

The agent will answer from training data — it cannot retrieve or cite the current Microsoft Learn article.

Also ask:

```text
What is the latest guidance on configuring health probes for Azure Container Apps? Provide the documentation URL.
```

Again — the agent may answer, but it cannot produce a real, current article URL.

### Step 2 — Apply the Microsoft Learn MCP connector

Apply the connector YAML from `Student/Resources/azure-sre-agent-config/connectors/`:

> **Note:** `make connectors` applies **all** connectors in the bundle (`github`, `microsoft-learn-mcp`, `berlin-mcp`). If you ran it in Challenge 01, this re-apply is idempotent and safe — it updates any endpoints from Terraform outputs without disrupting the GitHub connector you already authorized.

```bash
make connectors
```

Verify in the portal under **Connectors** — the `microsoft-learn-mcp` connector should show as connected (green).

### Step 3 — Test the same requests again

```text
What does the official Azure documentation recommend for investigating Container Apps HTTP 5xx errors? Cite the article.
```

The agent should now retrieve and cite a specific, current Microsoft Learn article URL.

```text
What is the latest guidance on configuring health probes for Azure Container Apps? Provide the documentation URL.
```

The agent should return a real, navigable Microsoft Learn URL — verify it opens the correct article.

### Step 4 — Use the connector during an investigation

Trigger a more realistic scenario:

```text
I'm seeing HTTP 503 responses from the Grubify frontend Container App. What should I check first, and what does the official Azure documentation recommend for diagnosing this error?
```

The agent should combine its Azure investigation skills (from Challenge 03) with live documentation retrieval to give a grounded, citable answer.

### Step 5 — Understand the boundary

```text
Can you call arbitrary REST APIs that are not configured as connectors? Could you query an API I haven't set up?
```

The agent should confirm that it can only reach explicitly connected systems — this is the governance boundary.

## Success Criteria

- [ ] Before adding the connector, the agent answers documentation questions from training data with no real URL
- [ ] After adding the connector, the agent retrieves and cites a specific, current Microsoft Learn article
- [ ] The `microsoft-learn-mcp` connector shows as connected (green) in the portal
- [ ] The agent combines live documentation with its Azure investigation skills in a single response
- [ ] **Explain to your coach** — what is the difference between an MCP connector and a skill tool grant? When do you use each approach to extend the agent's reach?

## Learning Resources

- [Azure SRE Agent — MCP connectors](https://learn.microsoft.com/en-us/azure/sre-agent/mcp-connectors)
- [Model Context Protocol specification](https://modelcontextprotocol.io/introduction)
- [Microsoft Learn MCP server](https://github.com/MicrosoftDocs/mcp)

## Tips

- The Microsoft Learn MCP exposes three tools: `microsoft_docs_search`, `microsoft_docs_fetch`, and `microsoft_code_sample_search`. The agent selects the right one automatically based on your query.
- The connector uses public, unauthenticated access to `https://learn.microsoft.com/api/mcp` — no secrets required.
- After this challenge: the agent can reach external documentation but every request still comes through the main agent. Domain specialization — having dedicated experts for network vs. app vs. cost scenarios — comes in Challenge 05.

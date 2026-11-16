---
title: Discover Connected Systems
summary: Connect Microsoft Learn through MCP so the agent can retrieve current Azure documentation. Verify its citations.
phase: Config
group: Agent configuration
tags:
- MCP connectors
- tool discovery
- live docs
highlight: false
---

# Challenge 04 — Discover Connected Systems

> **Application focus:** Infrastructure/platform only

> **Capabilities added in this challenge**: MCP Connectors

## Purpose

- Add an MCP connector and show the agent citing live Microsoft Learn guidance in an answer.
- Operational agents need to combine local investigation with current vendor guidance.
- Expected time: 10–15 minutes.

## Introduction

Your agent can investigate Azure (Challenge 03), but it has no connection to current Microsoft Learn documentation. Answers based on training data may be outdated or lack verifiable citations.

MCP connectors give the agent access to external systems through the Model Context Protocol. Connect Microsoft Learn, then check whether the agent retrieves current documentation and cites it.

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

The agent may supply a URL from memory, but it cannot retrieve the current article through Microsoft Learn yet.

### Step 2 — Apply the Microsoft Learn MCP connector

Apply the connector YAML from `labs/01-azure-operations/resources/azure-sre-agent-config/connectors/`:

> **Note:** `make connectors-learn` applies only the `microsoft-learn-mcp` connector. The GitHub and Berlin connectors remain managed by `make connectors`.

```bash
make connectors-learn
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

The agent should confirm that it can only reach explicitly connected systems. This is the governance boundary.

## Success Criteria

- [ ] Before adding the connector, you record the agent's answer and whether it can retrieve current documentation
- [ ] After adding the connector, the agent retrieves and cites a specific, current Microsoft Learn article
- [ ] The `microsoft-learn-mcp` connector shows as connected (green) in the portal
- [ ] The agent combines live documentation with its Azure investigation skills in a single response
- [ ] **Explain in your own words** (two or three written sentences) — what is the difference between an MCP connector and a skill tool grant? When do you use each approach to extend the agent's reach?

## Learning Resources

- [Azure SRE Agent — MCP connectors](https://learn.microsoft.com/en-us/azure/sre-agent/mcp-connectors)
- [Model Context Protocol specification](https://modelcontextprotocol.io/introduction)
- [Microsoft Learn MCP server](https://github.com/MicrosoftDocs/mcp)

## Tips

- The Microsoft Learn MCP exposes three tools: `microsoft_docs_search`, `microsoft_docs_fetch`, and `microsoft_code_sample_search`. The agent selects the right one automatically based on your query.
- The connector uses public, unauthenticated access to `https://learn.microsoft.com/api/mcp` — no secrets required.
- After this challenge: the agent can reach external documentation but every request still comes through the main agent. Domain specialization — having dedicated experts for network vs. app vs. cost scenarios — comes in Challenge 05.

## Hints and notes

> Hidden until you click. Expand a section only when you want it.

<details>
<summary><strong>Background</strong></summary>

- Skills govern how the agent uses built-in tools; a connector adds new external tools.
- Learn connector details: `microsoft-learn-mcp`, Streamable HTTP endpoint `https://learn.microsoft.com/api/mcp`, no auth beyond empty custom headers.
- `make connectors-learn` applies only the Microsoft Learn connector; `make connectors` manages the GitHub and Berlin connectors used in Challenges 01 and 07.
- The connector surfaces three tools: docs search, docs fetch, and code sample search.
- Compare before and after with "cite the official article" prompts.

</details>

<details>
<summary><strong>Expected Output</strong></summary>

- Before setup, docs answers are uncited or training-data-only.
- After `make connectors-learn`, the `microsoft-learn-mcp` connector is green.
- The agent returns a real Learn URL and can blend it with Grubify/Azure troubleshooting guidance.

</details>

<details>
<summary><strong>Common Issues and Hints</strong></summary>

- **Symptom:** Connector exists but tools are unavailable in chat. **Fix:** confirm the connector is connected and the MCP tools are visible to the meta agent.
- **Symptom:** You expect OAuth. **Fix:** this public connector needs no user auth; GitHub was the auth-required example.
- **Symptom:** Agent gives a URL from memory but not fetched live. **Fix:** ask for a current recommendation plus citation and article URL.

</details>

<details>
<summary><strong>Debrief Discussion Guide</strong></summary>

- When do you use a connector instead of adding more knowledge docs? → When freshness and live retrieval matter.
- Why is Microsoft Learn a good demo connector? → Safe, public, clearly verifiable, and operationally useful.
- What governance boundary remains? → The agent still cannot call arbitrary APIs not wired as connectors.

</details>

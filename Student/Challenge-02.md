[< Previous Challenge](./Challenge-01.md) — **[Home](../README.md)** — [Next Challenge >](./Challenge-03.md)

# Challenge 02 — Explore the Knowledge Base

> **Capabilities added in this challenge**: Knowledge Documents

## Introduction

Your agent can read the Grubify source code (from Challenge 01) but knows nothing about *your running environment*. Ask it about the Grubify architecture or its monitoring configuration and it will either say it doesn't know, or it will hallucinate — drawing on generic Azure knowledge and inventing details that don't match the lab.

**Knowledge documents** are how you fix that. They are Markdown files — architecture diagrams, runbooks, incident reports, troubleshooting guides, KQL catalogs — that the agent retrieves at query time to ground its answers in your actual environment. Once loaded, every response about Grubify, its network, or its costs is backed by real documentation, not guesswork.

## Description

### Step 1 — Ask about the environment (before knowledge)

In the SRE Agent portal, ask:

```text
Explain the Grubify application topology. What are its components, how are they connected, and what is the hosting model for each tier?
```

Note the response carefully — does it match the actual lab? Does it name specific resources, IP ranges, or monitoring configurations? Or does it give generic Container Apps advice?

Also try:

```text
What KQL query would I use to detect nginx service failures on the Grubify web VMs?
```

Without knowledge documents, the agent cannot give the correct workspace name, table name, or query structure for this lab.

### Step 2 — Add the knowledge documents

Upload the knowledge documents from `Student/Resources/azure-sre-agent-config/knowledge/files/`:

```bash
make knowledge-files
```

Wait ~30 seconds for ingestion, then verify under **Knowledge** in the portal — you should see the uploaded documents listed.

### Step 3 — Ask the same questions again

Repeat the questions from Step 1:

```text
Explain the Grubify application topology. What are its components, how are they connected, and what is the hosting model for each tier?
```

The agent should now describe:

- The hub-and-spoke network layout with specific IP ranges
- The Container Apps services (`ca-food-api`, `ca-food-frontend`) and their ports
- The IaaS web tier (nginx VMs behind the internal load balancer at `10.20.2.100`)
- The monitoring stack (Log Analytics workspace, Application Insights, Syslog DCR)

And for the KQL question — it should now name the correct workspace, table (`Syslog`), and facility filter.

### Step 4 — Ask about something the knowledge base does not cover

No knowledge document describes the Parking Manager app. Ask:

```text
Explain the Parking Manager architecture. What backend APIs does it expose, what technology stack does each use, and how is observability configured for the hybrid components?
```

A well-grounded agent should say it doesn't have documentation for the Parking Manager rather than
inventing an architecture — this is the flip side of Step 3: retrieval grounds real answers *and*
prevents hallucination when there is nothing to retrieve.

### Step 5 — Verify citation

Ask the agent to be explicit:

```text
For your last response, which knowledge document did you reference? Can you cite it?
```

### Step 6 — Browse the documents in the portal

In the portal under **Knowledge**, open 2–3 uploaded documents. Confirm the agent's responses matched what is written in the documents.

## Success Criteria

- [ ] Before adding knowledge, the agent gives a vague or hallucinated response about the Grubify topology
- [ ] After adding knowledge, the agent names specific resources, IP addresses, and monitoring configurations from the docs
- [ ] The agent provides a correct lab-specific KQL query for nginx failure detection
- [ ] The agent cites or references a specific knowledge document when asked
- [ ] **Explain to your coach** — what is the difference between a knowledge document and a skill knowledge doc? When would you put information in each?

## Learning Resources

- [Azure SRE Agent — knowledge base](https://learn.microsoft.com/en-us/azure/sre-agent/connect-knowledge)
- [Azure SRE Agent — grounding and retrieval](https://learn.microsoft.com/en-us/azure/sre-agent/connect-knowledge)
- [RAG (retrieval-augmented generation) overview](https://learn.microsoft.com/en-us/azure/ai-studio/concepts/retrieval-augmented-generation)

## Tips

- The quality of a grounded response depends on the quality of the documentation. Vague documents produce vague answers.
- Knowledge documents are retrieved by **semantic similarity** — the agent retrieves the most relevant ones for each query, not all documents for every query. Document titles and first paragraphs matter for retrieval.
- Try asking about a fictional component (something not in the knowledge base). A well-configured agent should say it doesn't know rather than hallucinate. This builds trust.
- After this challenge: the agent knows your environment but still can't *investigate* it — it has no tools to run queries or CLI commands. That comes next.

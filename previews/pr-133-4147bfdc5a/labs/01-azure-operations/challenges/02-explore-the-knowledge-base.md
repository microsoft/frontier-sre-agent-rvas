---
title: Explore the Knowledge Base
summary: Add lab knowledge documents, then compare the agent's answers before and after upload. Check resource details and citations.
phase: Config
group: Agent configuration
tags:
- knowledge docs
- grounded responses
- sre-agent-config
highlight: false
---

# Challenge 02 — Explore the Knowledge Base

> **Application focus:** Grubify (Sample Food) only

> **Capabilities added in this challenge**: Knowledge Documents

## Purpose

- Compare the agent's answers before and after loading the knowledge docs, and name at least three details that became correct (resource names, IPs, tables or citations).
- Expected time: 15–20 minutes.

## Introduction

Your agent can read the Grubify source code from Challenge 01, but it has no documentation about the running lab. Ask about its architecture or monitoring configuration and check whether the answer matches the environment.

Knowledge documents supply that context. When answering, the agent retrieves relevant Markdown files, such as architecture notes, runbooks, incident reports, troubleshooting guides, and KQL catalogs. Retrieval grounds answers in the lab but does not guarantee they are correct, so verify the answers and citations.

## Description

### Step 1 — Ask about the environment (before knowledge)

In the SRE Agent portal, ask:

```text
Explain the Grubify application topology. What are its components, how are they connected, and what is the hosting model for each tier?
```

Note the response carefully. Does it match the actual lab? Does it name specific resources, IP ranges, or monitoring configurations, or does it give generic Container Apps advice?

Also ask about the Web IaaS application topology:

```text
Explain the Web IaaS application topology. What are its components, how are they connected, and what is the hosting model for each tier?
```

Check the response the same way.

Also try:

```text
What KQL query would I use to detect nginx service failures on the Web IaaS VMs?
```

Without knowledge documents, the agent cannot give the correct workspace name, table name, or query structure for this lab.

### Step 2 — Add the knowledge documents

Upload the knowledge documents from `labs/01-azure-operations/resources/azure-sre-agent-config/knowledge/files/`:

```bash
make knowledge-files
```

Wait ~30 seconds for ingestion, then verify under **Knowledge sources** in the portal — you should see the uploaded documents listed and indexed.

### Step 3 — Ask the same questions again

Repeat the questions from Step 1:

```text
Explain the Grubify application topology. What are its components, how are they connected, and what is the hosting model for each tier?
```

The agent should now describe:

- The Container Apps services (`ca-food-api`, `ca-food-frontend`) and their ports
- The monitoring stack (Log Analytics workspace, Application Insights, Syslog DCR)

```text
Explain the Web IaaS application topology. What are its components, how are they connected, and what is the hosting model for each tier?
```

The agent should now describe:

- The hub-and-spoke network layout with specific IP ranges
- The IaaS web tier (nginx VMs behind the internal load balancer at `10.20.2.100`)
- The monitoring stack (Log Analytics workspace, Application Insights, Syslog DCR)

And for the KQL question — it should now name the correct workspace, table (`Syslog`), and facility filter.

### Step 4 — Ask about something the knowledge base does not cover

No knowledge document describes the Parking Manager app. Ask:

```text
Explain the Parking Manager architecture. What backend APIs does it expose, what technology stack does each use, and how is observability configured for the hybrid components?
```

The agent should acknowledge that it has no Parking Manager documentation rather than invent
an architecture. Check that it states this limitation clearly.

### Step 5 — Verify citation

Ask the agent to be explicit:

```text
For your last response, which knowledge document did you reference? Can you cite it?
```

### Step 6 — Browse the documents in the portal

In the portal under **Knowledge sources**, open 2–3 uploaded documents. Confirm the agent's responses matched what is written in the documents.

## Success Criteria

- [ ] Before adding knowledge, the agent gives a vague or hallucinated response about the Grubify topology
- [ ] After adding knowledge, the agent names specific resources, IP addresses, and monitoring configurations from the docs
- [ ] The agent provides a correct lab-specific KQL query for nginx failure detection
- [ ] The agent cites or references a specific knowledge document when asked
- [ ] **Explain in your own words** (two or three written sentences) — what is the difference between a knowledge document and a skill knowledge doc? When would you put information in each?

## Learning Resources

- [Azure SRE Agent — knowledge base](https://learn.microsoft.com/en-us/azure/sre-agent/connect-knowledge)
- [Azure SRE Agent — grounding and retrieval](https://learn.microsoft.com/en-us/azure/sre-agent/connect-knowledge)
- [RAG (retrieval-augmented generation) overview](https://learn.microsoft.com/en-us/azure/ai-studio/concepts/retrieval-augmented-generation)

## Tips

- The quality of a grounded response depends on the quality of the documentation. Vague documents produce vague answers.
- Knowledge documents are retrieved by **semantic similarity** — the agent retrieves the most relevant ones for each query, not all documents for every query. Document titles and first paragraphs matter for retrieval.
- Try asking about a fictional component that is not in the knowledge base. The agent should say it doesn't know rather than invent details.
- After this challenge: the agent knows your environment but still can't *investigate* it — it has no tools to run queries or CLI commands. That comes next.

## Hints and notes

> Hidden until you click. Expand a section only when you want it.

<details>
<summary><strong>Background</strong></summary>

- The model does not read every document each turn; it retrieves the most relevant ones.
- There are three knowledge families: `sample-food/`, `vnet-flow-logs/`, and `cost/`.
- A useful contrast: ask about Grubify topology before and after `make knowledge-files`.
- Facts to look for in answers: `ca-food-api`, `ca-food-frontend`, `lb-internal-web`, `10.20.2.100`, `Syslog`, Application Insights, and the three VNet flow logs. (Traffic Analytics / `NTANetAnalytics` is not introduced until Challenge 03.)

</details>

<details>
<summary><strong>Expected Output</strong></summary>

- Portal shows all 9 certified knowledge documents after `make knowledge-files`.
- Agent names lab-specific components instead of generic Azure advice.
- For nginx failure questions, agent references the `Syslog` table and correct VM/web-tier context.
- When asked, the agent can cite or name the document it relied on.

</details>

<details>
<summary><strong>Common Issues and Hints</strong></summary>

- **Symptom:** Answers remain generic right after upload. **Fix:** wait ~30 seconds for ingestion, then re-ask with a very specific lab question.
- **Symptom:** Agent cites wrong concepts like `/health` for Sample Food. **Fix:** steer the agent to docs showing `/WeatherForecast` and `/api/FoodItems` as valid checks.
- **Symptom:** You upload only one folder of docs. **Fix:** make sure all knowledge files from `knowledge/files/` are applied.
- **Symptom:** No citation when asked. **Fix:** explicitly prompt for the knowledge source by name.

</details>

<details>
<summary><strong>Debrief Discussion Guide</strong></summary>

- Why not rely on the model's Azure training data? → It lacks your environment's names, topology, and exceptions.
- What belongs in knowledge vs. a skill? → Reference context in knowledge; executable procedure/tool policy in skills.
- What is a healthy answer when the knowledge base lacks a fact? → “I don’t know,” not confident invention.

</details>

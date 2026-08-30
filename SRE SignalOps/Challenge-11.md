[< Previous Challenge](./Challenge-10.md) — **[Home](./README.md)** — [Next Challenge >](./Challenge-12.md)

# Challenge 11 — Context That Learns

> **Capabilities added in this challenge**: Knowledge Bases · Grounded Responses · Contextual Learning

## Introduction

Telemetry explains what the platform observed, but it does not contain your organization’s architecture, ownership, maintenance windows, or recovery policy. In this challenge, you give the SRE Agent that missing context and prove that the same operational question produces a more useful, grounded response.

## Description

> **Customer demo script:** Run `pwsh -File '.\SRE SignalOps\Scripts\Challenge-11.ps1'` to list agent memory, create a safe knowledge draft, and print the grounded prompt. See the [presenter runbook](./Scripts/README.md).

Use the heartbeat workload from Challenge 10 and achieve these outcomes:

- Ask a reliability question before adding any custom knowledge and capture the response as a baseline.
- Create one concise knowledge document containing workload purpose, architecture, owner, criticality, heartbeat expectation, maintenance window, escalation path, RTO, RPO, and approved investigation boundaries.
- Add the document to the SRE Agent knowledge base and ask the same question again.
- Identify which statements came from live Azure evidence and which came from the knowledge document.
- Add one verified lesson from the heartbeat incident, then confirm that a later response uses the new context without contradicting current telemetry.

Do not store credentials, access tokens, personal contact details, or unverified incident assumptions in the knowledge document. Context can guide interpretation, but current evidence remains authoritative.

## Success Criteria

- [ ] A before-and-after comparison shows that the knowledge document materially improves the response
- [ ] The document contains operational context, ownership, recovery objectives, and investigation boundaries
- [ ] The grounded response cites or clearly attributes the custom knowledge it used
- [ ] The response distinguishes live evidence from organizational context and identifies any conflict between them
- [ ] One verified incident lesson is added and appears in a later grounded response
- [ ] **Explain to your coach** — when should live telemetry override a knowledge document, and how would you prevent stale operational knowledge from misleading the agent?

## Learning Resources

- [Connect knowledge sources to Azure SRE Agent](https://learn.microsoft.com/en-us/azure/sre-agent/connect-knowledge)
- [Knowledge source concepts in Azure AI Search](https://learn.microsoft.com/en-us/azure/search/search-knowledge-source-overview)
- [Reliability guidance in the Azure Well-Architected Framework](https://learn.microsoft.com/en-us/azure/well-architected/reliability/)
- [Azure Monitor data platform](https://learn.microsoft.com/en-us/azure/azure-monitor/data-platform)

## Tips

- Use the exact same question before and after adding knowledge; otherwise the comparison is weak.
- Keep durable policy and architecture in knowledge. Keep transient resource state in Azure Monitor and Resource Graph.
- Record only a verified lesson. A plausible but unconfirmed RCA should remain a hypothesis, not become institutional knowledge.
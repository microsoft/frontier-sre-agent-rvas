[< Previous Challenge](./Challenge-10.md) — **[Home](./README.md)** — [Next Challenge >](./Challenge-12.md)

# Challenge 11 — Improve the Next Heartbeat Response

> **Incident capability exercised in this challenge**: Operational Context · Repeat-Incident Learning · Evidence Precedence

## Introduction

Replay the missing-heartbeat incident after adding verified workload context and one confirmed lesson from the first response. Determine whether the SRE Agent identifies impact, ownership, recovery objectives, and escalation faster without allowing stale knowledge to override current evidence.

## Description

> **Customer demo script:** Run `pwsh -File '.\SRE SignalOps\Scripts\Challenge-11.ps1'` to list agent memory, create a safe knowledge draft, and print the grounded prompt. See the [presenter runbook](./Scripts/README.md).

Use the heartbeat incident from Challenge 10 as a clearly labeled replay and achieve these outcomes:

- Replay the original incident question before adding any custom knowledge and capture the response as a baseline.
- Create one concise knowledge document containing workload purpose, architecture, owner, criticality, heartbeat expectation, maintenance window, escalation path, RTO, RPO, and approved investigation boundaries.
- Add the document to the SRE Agent knowledge base and ask the same question again.
- Identify which statements came from live Azure evidence and which came from the knowledge document.
- Add one verified lesson from the heartbeat incident, then replay the question and confirm that the later response uses the lesson without substituting history for current investigation.

Do not store credentials, access tokens, personal contact details, or unverified incident assumptions in the knowledge document. Context can guide interpretation, but current evidence remains authoritative.

## Success Criteria

- [ ] A before-and-after incident replay shows that the knowledge document materially improves impact, ownership, recovery, or escalation reasoning
- [ ] The document contains operational context, ownership, recovery objectives, and investigation boundaries
- [ ] The grounded response cites or clearly attributes the custom knowledge it used
- [ ] The response distinguishes live evidence from organizational context and identifies any conflict between them
- [ ] One verified incident lesson is added and appears in a later grounded response
- [ ] **Explain to your coach** — how can a verified incident lesson speed future response without becoming a shortcut that biases the diagnosis?

## Learning Resources

- [Connect knowledge sources to Azure SRE Agent](https://learn.microsoft.com/en-us/azure/sre-agent/connect-knowledge)
- [Knowledge source concepts in Azure AI Search](https://learn.microsoft.com/en-us/azure/search/search-knowledge-source-overview)
- [Reliability guidance in the Azure Well-Architected Framework](https://learn.microsoft.com/en-us/azure/well-architected/reliability/)
- [Azure Monitor data platform](https://learn.microsoft.com/en-us/azure/azure-monitor/data-platform)

## Tips

- Use the exact same question before and after adding knowledge; otherwise the comparison is weak.
- Keep durable policy and architecture in knowledge. Keep transient resource state in Azure Monitor and Resource Graph.
- Record only a verified lesson. A plausible but unconfirmed RCA should remain a hypothesis, not become institutional knowledge.
[< Previous Challenge](./Challenge-08.md) — **[Home](../../README.md)**

# Challenge 09 — Build Your Own Production-Ready Fabric SRE Agent

> **Capabilities added in this challenge**: Custom Fabric FinOps/RCA Agent · Governance · End-to-End Validation

## Introduction

You have configured a Fabric SRE Agent, evaluated its consumption source, and
tested cost analysis, model residency, live skills, instructions, and Spark
investigation/optimization. Now design
a bounded agent workflow for a real Fabric reliability or FinOps question from
your own environment.

## Description

Bring a scenario that has a measurable signal and an operationally useful
outcome. Design and demonstrate a safe agent experience that:

- Defines a consumer, question, time window, data source, and success measure.
- Selects FUAM or Capacity Events based on the required precision, retention,
  and acceptable monitoring cost.
- Uses the narrowest suitable read-only tools, current Fabric skills,
  backend-specific instructions, and necessary knowledge.
- Produces evidence, calculation, precision, freshness, caveats, and a
  recommendation or escalation path.
- Includes a repeatable test and an explicit boundary preventing the agent from
  changing or running Fabric items.
- Records the approved model provider/processing boundary, required workspace
  hosts, and proof that current Code Access skill/Mandatory files are read.

Review the design with your coach before applying new permissions or
configuring any write-capable tooling.

## Success Criteria

- [ ] A coach-approved scenario statement identifies the user, signal, investigation, and useful outcome.
- [ ] The design justifies its backend, tools, permissions, and data-retention needs.
- [ ] A knowledge or instruction artifact grounds the response in the chosen environment.
- [ ] An end-to-end test demonstrates correct evidence selection, precision, cost math where applicable, and a safe recommendation.
- [ ] The presentation identifies operational ownership, monitoring cost, approval boundary, and known limitations.
- [ ] **Explain to your coach** — what technical and organizational conditions must be true before this agent is trusted with a production decision?

## Learning Resources

- [Azure SRE Agent skills](https://learn.microsoft.com/azure/sre-agent/skills)
- [Azure SRE Agent MCP connectors](https://learn.microsoft.com/azure/sre-agent/mcp-connectors)
- [Azure SRE Agent custom agents](https://learn.microsoft.com/azure/sre-agent/custom-agents)
- [Microsoft Fabric operations](https://learn.microsoft.com/fabric/enterprise/fabric-operations)

## Tips

- Start with one bounded recurring question and a few read-only tool calls.
- Treat cost recommendations as estimates unless validated against actual billing data.
- “Insufficient evidence” is a valid result; invented precision is not.

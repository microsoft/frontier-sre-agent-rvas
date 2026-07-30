[< Previous Solution](./Solution-04.md) | **[Home](./README.md)** | [Next Solution >](./Solution-06.md)

# Coach Guide — Challenge 05: Discover Specialist Agents

## Purpose

- Teach subagents as scoped domain experts with their own prompts, tools, and skill allow-lists.
- This sets up why incident routing in the next challenge is meaningful: alerts go to specialists, not a generic assistant.
- Expected time: 20 minutes.

## Mini-Lecture (3–5 min before challenge)

- Introduce the **eleven** specialists: `aca-app-incident-handler`, `iaas-vm-incident-handler`, `network-traffic-analyst`, `code-analyzer`, `issue-triager`, `cost-optimization-agent`, `azure-resource-config-auditor`, `access-to-3rd-party-logs`, `dependency-analyzer`, `madrid-api`, `paris-api`.
- Show the contrast prompt: `/agent network-traffic-analyst` before config fails; after config it should answer with `NTANetAnalytics`, routes, NSGs, and next-hop language.
- Emphasize that narrow tool grants are a governance feature, not a limitation.
- Good whiteboard diagram: main agent → specialist roster → each specialist owns a failure domain.

## Expected Student Output

- Portal shows all **eleven** subagents after `make subagents`.
- `/agent network-traffic-analyst` returns domain-specific network investigation steps.
- `/agent aca-app-incident-handler` returns Container Apps-specific investigation steps.
- Students can articulate why a scoped system prompt changes answer quality.

## Common Issues and Hints

- **Symptom:** `/agent network-traffic-analyst` not found. **Fix:** subagents were not applied or portal needs refresh.
- **Symptom:** Specialist still sounds generic. **Fix:** use a prompt in its exact domain, e.g. routing/NSG for network or HTTP 503 for ACA.
- **Symptom:** Students conflate skill and subagent. **Fix:** explain that the subagent is the specialist identity; skills are tools/runbooks it may use.

## Debrief Discussion Guide

- What does a subagent add beyond skills alone? → Prioritization, persona, scope, and domain-specific instructions.
- Why not give every tool to every specialist? → Smaller blast radius and clearer accountability.
- Which specialist seems most reusable across multiple challenges? → Usually `network-traffic-analyst`.

## Success Criteria Notes

- Require one failed pre-subagent invocation and one successful post-subagent invocation.
- Do not over-index on exact wording; look for domain language and correct first steps.

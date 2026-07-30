[< Previous Solution](./Solution-02.md) | **[Home](./README.md)** | [Next Solution >](./Solution-04.md)

# Coach Guide — Challenge 03: Discover Operational Skills

## Purpose

- Teach that skills are the agent’s executable runbooks: named procedures plus tool grants plus safety posture.
- This challenge converts the agent from “can explain” to “can actually investigate.”
- Expected time: 20 minutes.

## Mini-Lecture (3–5 min before challenge)

- Show the anatomy of a skill YAML: `description`, `content_file`, `tools`, and `safety`.
- Enumerate the eight loaded skills and their domains: app incident analysis, connectivity, Traffic Analytics, NSG deny, UDR asymmetry, VNet Flow Log ingestion, RBAC, cost optimization.
- Important coach point: routing comes from the description; least privilege comes from the tools list.
- Example dependency chain: knowledge doc tells the agent *how* to query `NTANetAnalytics`; skill grants `QueryLogAnalyticsByWorkspaceId` so it can actually run the query.

## Expected Student Output

- Before loading skills, the agent describes investigations without executing them.
- After `make skills`, portal shows eight skills.
- The agent invokes a real skill and returns live data for Grubify or network flow questions.
- Students can explain approval boundaries from the `safety` block.

## Common Issues and Hints

- **Symptom:** Skill objects exist but the agent still answers generically. **Fix:** ask a prompt tightly aligned to a skill description, e.g. denied flows or Container App health.
- **Symptom:** No live data appears. **Fix:** verify earlier validation/traffic steps and remember monitoring tables may have short ingestion lag.
- **Symptom:** Students think skills themselves contain all content. **Fix:** open one `.yaml` and one paired `.md` to show the separation.
- **Symptom:** Student expects write actions immediately. **Fix:** remind them most skills default to read-only and require approval for actions.

## Debrief Discussion Guide

- Why explicitly list tools in a skill? → Constrains blast radius and makes capability auditable.
- Why separate skill YAML from knowledge markdown? → Policy and procedure change at different rates.
- What changed operationally after this challenge? → The agent can now query and inspect real systems, not just discuss them.

## Success Criteria Notes

- Require at least one successful live skill invocation.
- Do not require students to memorize all eight skill names, but they should identify the major domains.
- If one query is empty due to timing, accept evidence from another skill-backed question.

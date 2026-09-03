[< Previous Solution](./Solution-02.md) | **[Home](./README.md)** | [Next Solution >](./Solution-04.md)

# Coach Guide — Challenge 03: Discover Operational Skills

## Purpose

- Teach that skills are reusable operational procedures with declared tools; custom-agent grants and trigger mode enforce the execution boundary.
- This challenge converts the agent from “can explain” to “can actually investigate.”
- Expected time: 20 minutes.

## Mini-Lecture (3–5 min before challenge)

- Show the anatomy of a skill YAML: `description`, `content_file`, and `tools`.
- Enumerate the nine certified skills and their domains: Sample Food incident analysis,
  connectivity diagnostics, Traffic Analytics, VNet Flow Log ingestion, cost optimization,
  GitHub issue triage, Linux service recovery, RBAC/resource access, and source-fix delivery.
- Important coach point: routing comes from the description; least privilege comes from the tools list.
- Example dependency chain: knowledge doc tells the agent *how* to query `NTANetAnalytics`; skill grants `QueryLogAnalyticsByWorkspaceId` so it can actually run the query.

## Expected Student Output

- Before loading skills, the agent describes investigations without executing them.
- After `make skills`, the portal shows nine skills.
- The agent invokes a real skill and returns live data for Grubify or network flow questions.
- Students can explain approval boundaries from custom-agent tool grants and response-plan or scheduled-task mode.

## Common Issues and Hints

- **Symptom:** Skill objects exist but the agent still answers generically. **Fix:** ask a prompt tightly aligned to a skill description, e.g. denied flows or Container App health.
- **Symptom:** No live data appears. **Fix:** verify earlier validation/traffic steps and remember monitoring tables may have short ingestion lag.
- **Symptom:** Students think skills themselves contain all content. **Fix:** open one `.yaml` and one paired `.md` to show the separation.
- **Symptom:** Student expects the skill's local `safety` metadata to enforce runtime approval. **Fix:** point to the custom agent's live tools and the trigger's Review/Autonomous mode as the effective controls.

## Debrief Discussion Guide

- Why explicitly list tools in a skill? → Constrains blast radius and makes capability auditable.
- Why separate skill YAML from knowledge markdown? → Policy and procedure change at different rates.
- What changed operationally after this challenge? → The agent can now query and inspect real systems, not just discuss them.

## Success Criteria Notes

- Require at least one successful live skill invocation.
- Do not require students to memorize all nine skill names, but they should identify the major domains.
- If one query is empty due to timing, accept evidence from another skill-backed question.

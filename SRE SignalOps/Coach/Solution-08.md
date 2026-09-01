[< Previous Solution](./Solution-07.md) | **[Home](./README.md)** | [Next Solution >](./Solution-09.md)

# Coach Guide — Challenge 08: Scope Impact with Dependency Evidence

## Purpose

Use dependency telemetry to bound the impact of a reported Grubify meal-search failure and choose the next discriminating check. Expected time: 20–25 minutes.

## Mini-Lecture (5 min before challenge)

- During an incident, topology is useful only when it narrows affected users, components, and next decisions.
- Architecture is intended structure; an incident map is observed request behavior with time and health evidence.
- A healthy or incomplete baseline must be labeled honestly; inability to reproduce an issue is not permission to invent one.

## Expected Student Output

- A directed dependency diagram and matching evidence table scoped to the meal-search user journey.
- A bounded blast radius, current reproduction status, and next discriminating check.
- Explicit telemetry gaps that prevent stronger incident conclusions.

## Coach Runbook

1. Present `EXERCISE: Grubify meal search fails for some users while the main site remains reachable`, then generate harmless baseline traffic.
2. Require each incident-relevant edge to identify caller, callee, protocol/type, time window, volume, latency, failures, and evidence source.
3. Ask which users and components are demonstrably affected, unaffected, or unknown; compare the diagram with the evidence table.
4. If the symptom is not reproduced, require that conclusion plus the telemetry and next check needed during recurrence.
5. Label intended but unobserved dependencies instead of drawing them as telemetry-proven edges.

## Common Issues and Hints

- **Symptom:** Map contains unsupported edges. **Fix:** require telemetry or label them documented-only.
- **Symptom:** Dependencies have no direction. **Fix:** identify caller and callee.
- **Symptom:** The student declares the entire application down. **Fix:** separate the failing user journey from healthy and unknown paths.
- **Symptom:** No failure appears in current telemetry. **Fix:** accept `not reproduced` and require a recurrence capture plan.

## Debrief Discussion Guide

1. How did dependency evidence change the incident scope? → It separated affected, unaffected, and unknown paths instead of treating Grubify as one health state.
2. What is the strongest next check? → The observation that most directly distinguishes between the remaining causal hypotheses on the affected path.
3. How would sampling distort the conclusion? → Rare failures and low-volume edges may disappear while aggregate latency looks healthier.

## Success Criteria Notes

- **Require:** direction, evidence status, measurement window, bounded blast radius, reproduction status, and a next discriminating check.
- **Reject:** invented dependencies, whole-service impact without evidence, or health claims based on one request.
- **Accept:** a healthy baseline or missing edges when explicitly labeled and paired with a recurrence collection plan.

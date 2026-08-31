[< Previous Solution](./Solution-04.md) | **[Home](./README.md)** | [Next Solution >](./Solution-06.md)

# Coach Guide — Challenge 05: Discover Specialist Agents

## Purpose

Assess specialist ownership, routing, and least privilege. Expected time: 15–20 minutes.

## Mini-Lecture (5 min before challenge)

Subagents reduce cognitive and permission scope only when their contracts are distinct.

## Expected Student Output

- A specialist roster with ownership, handoff description, tools, and write posture.
- Three routing tests with the selected specialist and a defensible reason.
- Explicit overlap, unowned capability gaps, and unsafe grant findings.

## Coach Runbook

1. Require students to inspect manifests before testing names or descriptions.
2. Use three distinct prompts: application error, denied network flow, and cost anomaly.
3. Compare selected specialists, reasoning, and tool grants; ask what would happen for an ambiguous cross-domain incident.
4. Stop if a write-capable specialist lacks an approval boundary.

## Common Issues and Hints

- **Symptom:** Every prompt routes to one agent. **Fix:** compare routing descriptions for overlap.
- **Symptom:** Tool grants are unknown. **Fix:** inspect manifests rather than relying on names.
- **Symptom:** A write-capable agent has no gate. **Fix:** keep it disabled until approval is configured.

## Debrief Discussion Guide

1. When is a skill enough? → When the task needs a repeatable procedure, not separate ownership, context, or permissions.
2. What makes routing defensible? → The incident evidence matches a distinct handoff contract and required tools.
3. How does specialization reduce blast radius? → It limits context and permissions to one operational domain.

## Success Criteria Notes

- **Require:** roster evidence, three routing rationales, and explicit overlap/gap analysis.
- **Reject:** name-only routing or unreviewed write grants.
- **Accept:** more than one plausible specialist if the student identifies the ambiguity and proposes a tie-breaker.

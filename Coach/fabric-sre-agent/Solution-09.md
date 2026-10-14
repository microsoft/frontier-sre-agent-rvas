[< Previous Solution](./Solution-08.md) | **[Home](../../README.md)**

# Coach Guide — Challenge 09: Build Your Own Production-Ready Fabric SRE Agent

## Purpose

- Synthesize backend selection, evidence use, cost calculation, RCA, and safety into a focused agent workflow.
- Evaluate the student's end-to-end demo and deployment readiness reasoning.
- Expected time: 75–90 minutes.

## Mini-Lecture (8 min before challenge)

- Narrow the use case to one recurring question, one consumer, and a measurable outcome.
- Let the needed precision determine the source backend rather than selecting by novelty.
- Require least privilege, explicit data freshness, retention, cost ownership, and a safe escalation path.
- A useful production design includes a validation plan and owner for incorrect recommendations.
- The capstone deliverable is an evidence-based demo, not a broad collection of configuration artifacts.

## Expected Student Output

- Coach-approved, bounded Fabric FinOps/RCA scenario and backend rationale.
- Read-only tool/identity design and grounded instructions/knowledge.
- End-to-end validation with evidence, calculation or RCA, precision, freshness, caveats, and safe next action.
- Short presentation covering technical controls and organizational ownership.

## Common Issues and Hints

- **Symptom:** Scenario asks the agent to "optimize all Fabric." **Fix:** narrow to one item/workspace, a measurable condition, and one decision.
- **Symptom:** Design assumes all sources provide exact per-run CU. **Fix:** select a backend and define precision rules from its true data grain.
- **Symptom:** The student wants to add write tools for remediation. **Fix:** keep this track read-only; describe an owner-approved future control plane separately.
- **Symptom:** Demo uses invented IDs or unsourced rates. **Fix:** require a real read path, lookup tool, timestamps, and a reproducible calculation.

## Debrief Discussion Guide

- What must change before the design can be trusted in a production capacity?
- Which missing evidence should cause the agent to stop and escalate?
- Who owns review of cost estimates, retention, and agent behavior over time?

## Success Criteria Notes

- Grade evidence discipline, safe scoping, and measured validation rather than feature count.
- Accept FUAM or Capacity Events when the backend choice is justified.
- Accept a partial implementation if the end-to-end test is real, bounded, and coach-approved.

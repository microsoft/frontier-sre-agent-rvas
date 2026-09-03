[< Previous Solution](./Solution-09.md) | **[Home](./README.md)** | [Next Solution >](./Solution-11.md)

# Coach Guide — Challenge 10: Exercise a Guarded HTTP-Error Response

## Purpose

Coach a Grubify HTTP-error incident from routing verification through evidence, a proposal-only response, recovery validation, and escalation. Expected time: 25–30 minutes.

## Mini-Lecture (5 min before challenge)

- Workflow completion is not incident resolution; service recovery evidence is the closure condition.
- A trustworthy response gathers enough evidence to bound action risk before proposing any action.
- Missing evidence, an attempted write, failed action, and failed validation must lead to an explicit stop or escalation.

## Expected Student Output

- Separate observations for ARM incident wiring, desired filter state, live filter registration, and Mission 03 alert compatibility.
- An explicit registration-gap result when `/incidentFilters` returns an empty `value` collection.
- An explicit mismatch showing that the Mission 03 `Sev2` rule name does not satisfy desired `Sev1` plus `titleContains: food` conditions.
- A genuine incident only when registration, matching, and intake are all observed; otherwise a clearly labeled tabletop.
- An observed timeline from intake through evidence, classification, proposal-only boundary, validation criteria, and escalation.
- A bounded response proposal with risk, rollback, and measurable service recovery checks.

## Coach Runbook

1. Have the participant run each command from Challenge 10 directly; there is no wrapper script.
2. Verify ARM reports `AzMonitor`/`azmonitor` and record that the deployed agent is `Autonomous/High`, not approval-gated.
3. Compare the desired `sample-food-http-errors` manifest with the live data-plane filter collection. The prepared environment may return `{ value: [], nextLink: null }`.
4. Compare the Mission 03 rule with both routing predicates. Its severity `2` and name without `food` do not match the desired filter.
5. Require current API health and Azure Monitor metrics before any response proposal.
6. Run only a labeled proposal exercise unless live registration, alert matching, and observed intake are all proven.
7. Exercise missing-evidence, failed-action, and failed-validation branches without executing a write.
8. Treat any closure without service-level evidence as a failed exercise.

## Common Issues and Hints

- **Symptom:** `/incidentFilters` returns `{ value: [], nextLink: null }`. **Fix:** record a registration gap and continue only as a labeled desired-state tabletop.
- **Symptom:** The Mission 03 alert does not route. **Fix:** show that `Sev2` and a rule name without `food` fail the desired `Sev1` and title predicates; do not mutate either resource.
- **Symptom:** Data-plane request returns `401`. **Fix:** reacquire the short-lived token for `https://azuresre.dev`; never print or persist it.
- **Symptom:** The student waits for approval. **Fix:** ARM reports `Autonomous/High`; enforce a proposal-only prompt and do not request execution.
- **Symptom:** Action is proposed before evidence. **Fix:** require current health, 5xx, memory, and restart observations first.
- **Symptom:** Plan closes immediately after simulated action. **Fix:** require HTTP `200`, no new 5xx buckets, and stable restart evidence.

## Debrief Discussion Guide

1. What guards this exercise when the agent is `Autonomous/High`? → Explicit proposal-only instructions, no execution request, and immediate stop on attempted writes.
2. What should trigger escalation? → Missing evidence, an attempted write, failed action, failed validation, or ownership/RTO breach.
3. How is closure proven? → The original signal clears and the affected Grubify user journey succeeds within expected service thresholds.

## Success Criteria Notes

- **Require:** separate wiring/filter/alert evidence, accurate match determination, current evidence before proposal, no-write behavior, recovery validation, and escalation logic.
- **Reject:** wrapper use, desired state presented as live, a mismatched alert presented as routed, action execution, or closure immediately after action.
- **Accept:** a tabletop when it remains clearly labeled and uses live configuration and workload evidence.

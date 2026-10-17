[< Previous Solution](./Solution-07.md) | **[Home](../README.md)** | [Next Solution >](./Solution-09.md)

# Coach Guide — Challenge 08: Exercise a Guarded HTTP-Error Response

## Purpose

Coach a Grubify HTTP-error incident from routing verification through evidence, a proposal-only response, recovery validation, and escalation. Expected time: 25–30 minutes.

## Mini-Lecture (5 min before challenge)

- Workflow completion is not incident resolution; service recovery evidence is the closure condition.
- A trustworthy response gathers enough evidence to bound action risk before proposing any action.
- Missing evidence, an attempted write, failed action, and failed validation must lead to an explicit stop or escalation.

## Expected Student Output

- Separate observations for ARM incident wiring, desired filter state, live filter registration, and Mission 01 alert compatibility.
- An explicit registration-gap result when `/incidentFilters` returns an empty `value` collection.
- An explicit match showing that the Mission 01 `Sev2` rule satisfies the all-severity plus `titleContains: grubify` conditions, or a clearly labeled live registration gap.
- A genuine incident only when registration, matching, and intake are all observed; otherwise a clearly labeled tabletop.
- An observed timeline from intake through evidence, classification, proposal-only boundary, validation criteria, and escalation.
- A bounded response proposal with risk, rollback, and measurable service recovery checks.

## Coach Runbook

1. Have the participant run each command from Challenge 08 directly; there is no wrapper script.
2. Verify ARM reports `AzMonitor`/`azmonitor`. Record actual root mode: Bicep uses `Autonomous/High`, Terraform uses `Review/High`; both response plans use Review.
3. Compare `$Lab.CONFIG_ROOT\response-plan.json` with the live data-plane filter collection. The prepared environment may return `{ value: [], nextLink: null }`.
4. Compare the Mission 01 rule with both routing predicates. Its severity `2` and `grubify` name should match the desired filter.
5. Require current API health and Azure Monitor metrics before any response proposal.
6. Run only a labeled proposal exercise unless live registration, alert matching, and observed intake are all proven.
7. Exercise missing-evidence, failed-action, and failed-validation branches without executing a write.
8. Treat any closure without service-level evidence as a failed exercise.

## Common Issues and Hints

- **Symptom:** `/incidentFilters` returns `{ value: [], nextLink: null }`. **Fix:** record a registration gap and continue only as a labeled desired-state tabletop.
- **Symptom:** The Mission 01 alert does not route. **Fix:** verify the live plan is enabled, includes `Sev2`, matches `grubify`, and targets the registered handler; do not rerun the fault.
- **Symptom:** Data-plane request returns `401`. **Fix:** reacquire the short-lived token for `https://azuresre.dev`; never print or persist it.
- **Symptom:** The student confuses root-agent autonomy with response-plan mode. **Fix:** show both settings separately; the plan's `Review` mode approval-gates writes for routed incidents.
- **Symptom:** Action is proposed before evidence. **Fix:** require current health, 5xx, memory, and restart observations first.
- **Symptom:** Plan closes immediately after simulated action. **Fix:** require HTTP `200`, no new 5xx buckets, and stable restart evidence.

## Debrief Discussion Guide

1. What guards this exercise independently of the root agent mode? → The routed plan's `Review` mode plus explicit proposal-only instructions and immediate stop on attempted writes.
2. What should trigger escalation? → Missing evidence, an attempted write, failed action, failed validation, or ownership/RTO breach.
3. How is closure proven? → The original signal clears and the affected Grubify user journey succeeds within expected service thresholds.

## Success Criteria Notes

- **Require:** separate wiring/filter/alert evidence, accurate match determination, current evidence before proposal, no-write behavior, recovery validation, and escalation logic.
- **Reject:** wrapper use, desired state presented as live, a missing plan presented as routed, action execution, or closure immediately after action.
- **Accept:** a tabletop when it remains clearly labeled and uses live configuration and workload evidence.

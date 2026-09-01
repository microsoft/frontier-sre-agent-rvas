[< Previous Solution](./Solution-06.md) | **[Home](./README.md)** | [Next Solution >](./Solution-08.md)

# Coach Guide — Challenge 07: Exercise a Guarded HTTP-Error Response

## Purpose

Coach a Grubify HTTP-error incident from alert intake through evidence, guarded action, recovery validation, and escalation. Expected time: 20–25 minutes.

## Mini-Lecture (5 min before challenge)

- Workflow completion is not incident resolution; service recovery evidence is the closure condition.
- A trustworthy response gathers enough evidence to bound action risk before requesting approval.
- Missing evidence, approval timeout, failed action, and failed validation must lead to an explicit stop or escalation.

## Expected Student Output

- A genuine or labeled exercise HTTP-error incident routed by the intended filter.
- An observed timeline from intake through evidence, classification, proposal, approval hold, validation criteria, and escalation.
- A bounded response proposal with risk, rollback, and measurable service recovery checks.

## Coach Runbook

1. Use a genuine harmless alert when available or invoke `EXERCISE - Grubify HTTP errors`; never create a production failure for the demo.
2. Have the student predict the intended response path, then observe and timestamp what actually occurs.
3. Verify incident scope, current evidence, classification, action risk, rollback, and approval posture before the action boundary.
4. Do not approve a write solely to make the workflow progress; require stated recovery and escalation branches.
5. Treat any automatic closure without service-level evidence as a failed exercise.

## Common Issues and Hints

- **Symptom:** No incident matches. **Fix:** inspect filter scope, severity, and title conditions.
- **Symptom:** Action is proposed before evidence. **Fix:** add an investigation gate.
- **Symptom:** Plan closes immediately after action. **Fix:** require recovery validation.

## Debrief Discussion Guide

1. Why is the approval gate necessary but insufficient? → It controls action authorization but does not prove diagnosis quality or recovery.
2. What should trigger escalation? → Missing evidence, approval timeout, failed action, failed validation, or ownership/RTO breach.
3. How is closure proven? → The original signal clears and the affected Grubify user journey succeeds within expected service thresholds.

## Success Criteria Notes

- **Require:** correctly labeled intake, current evidence before action, visible approval behavior, recovery validation, and escalation logic.
- **Reject:** action before evidence or closure immediately after action.
- **Accept:** a simulated incident when it remains clearly labeled and uses live configuration and workload evidence.

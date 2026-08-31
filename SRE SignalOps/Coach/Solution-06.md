[< Previous Solution](./Solution-05.md) | **[Home](./README.md)** | [Next Solution >](./Solution-07.md)

# Coach Guide — Challenge 06: Understand Response Plans

## Purpose

Make response-plan control flow observable and reviewable. Expected time: 20–25 minutes.

## Mini-Lecture (5 min before challenge)

A trustworthy plan has entry criteria, evidence gates, action gates, recovery checks, and escalation paths.

## Expected Student Output

- An expected trace from filter match through evidence, approval, action, validation, escalation, and closure.
- An observed non-destructive exercise timeline with every difference from the expected trace marked.

## Coach Runbook

1. Have the student draw the expected control flow before triggering an exercise.
2. Verify incident filter scope, title/severity match, specialist routing, and approval posture.
3. Observe the run and timestamp each gate; do not approve a write solely to make the demo progress.
4. Require a recovery validation and escalation branch before accepting closure.

## Common Issues and Hints

- **Symptom:** No incident matches. **Fix:** inspect filter scope, severity, and title conditions.
- **Symptom:** Action is proposed before evidence. **Fix:** add an investigation gate.
- **Symptom:** Plan closes immediately after action. **Fix:** require recovery validation.

## Debrief Discussion Guide

1. Which gate carries the most risk? → The first write authorization because it converts diagnosis into environmental impact.
2. What should trigger escalation? → Missing evidence, approval timeout, failed action, failed validation, or ownership/RTO breach.
3. How is closure proven? → The original signal clears and service-level validation confirms recovery.

## Success Criteria Notes

- **Require:** expected and observed traces, visible approval behavior, recovery validation, and escalation logic.
- **Reject:** action before evidence or closure immediately after action.
- **Accept:** a simulated incident when it is clearly labeled and uses live configuration evidence.

[< Previous Solution](./Solution-07.md) | **[Home](./README.md)** | [Next Solution >](./Solution-09.md)

# Coach Guide — Challenge 08: Investigate a Network Security Failure

## Purpose

Diagnose a lab NSG failure without weakening unrelated controls. Expected time: 25–30 minutes.

## Mini-Lecture (5 min before challenge)

Effective rule evaluation combines association, direction, tuple, priority, and default rules.

## Expected Student Output

The matching rule, flow evidence, blast radius, and a narrow reversible remediation proposal.

## Common Issues and Hints

- **Symptom:** Student inspects only subnet NSG. **Fix:** include NIC associations and effective rules.
- **Symptom:** Flow data is absent. **Fix:** label the evidence gap and use the supplied snapshot.
- **Symptom:** Proposed fix deletes a broad deny. **Fix:** require minimum-scope correction.

## Debrief Discussion Guide

1. Why do effective rules win?
2. How is blast radius bounded?
3. What proves recovery?

## Success Criteria Notes

Fault injection is allowed only in the coach-provided sandbox.

[< Previous Solution](./Solution-07.md) | **[Home](./README.md)** | [Next Solution >](./Solution-09.md)

# Coach Guide — Challenge 08: Investigate a Network Security Failure

## Purpose

Diagnose a lab NSG failure without weakening unrelated controls. Expected time: 25–30 minutes.

## Mini-Lecture (5 min before challenge)

Effective rule evaluation combines association, direction, tuple, priority, and default rules.

## Expected Student Output

- The exact effective rule and five-tuple evidence that explains the denied flow.
- A bounded blast radius, rejected alternatives, and the narrowest reversible remediation proposal.
- Post-remediation evidence that the original path recovered without weakening unrelated controls.

## Coach Runbook

1. Confirm the target is the coach-provided sandbox before any fault or remediation action.
2. Require NIC and subnet associations, effective rules, direction, priority, protocol, source, destination, and port.
3. Ask the student to bound affected and unaffected paths before proposing a change.
4. Approve only a narrow reversible correction, then require both recovery and regression checks.

## Common Issues and Hints

- **Symptom:** Student inspects only subnet NSG. **Fix:** include NIC associations and effective rules.
- **Symptom:** Flow data is absent. **Fix:** label the evidence gap and use the supplied snapshot.
- **Symptom:** Proposed fix deletes a broad deny. **Fix:** require minimum-scope correction.

## Debrief Discussion Guide

1. Why do effective rules win? → Azure evaluates the combined NIC/subnet rule set, not one displayed NSG in isolation.
2. How is blast radius bounded? → Match the effective rule against actual source, destination, port, protocol, and direction.
3. What proves recovery? → A successful original flow plus confirmation that unrelated denied paths remain denied.

## Success Criteria Notes

- **Require:** exact rule evidence, bounded blast radius, narrow correction, recovery proof, and control regression proof.
- **Reject:** production targeting, broad deny deletion, or portal-only reasoning.
- **Accept:** supplied flow snapshots when live Traffic Analytics has not ingested yet; label their timestamp.

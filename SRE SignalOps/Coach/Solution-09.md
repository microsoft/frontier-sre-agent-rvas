[< Previous Solution](./Solution-08.md) | **[Home](./README.md)** | [Next Solution >](./Solution-10.md)

# Coach Guide — Challenge 09: Investigate a Network Security Failure

## Purpose

Coach a Grubify dependency timeout from symptom to an evidence-backed NSG diagnosis, narrow recovery, and control regression check. Expected time: 25–30 minutes.

## Mini-Lecture (5 min before challenge)

- A timeout does not prove a network-security cause; effective rules and flow evidence must discriminate it from application, DNS, and routing failures.
- Effective rule evaluation combines association, direction, tuple, priority, and default rules.
- Recovery must restore the intended flow without weakening unrelated denied paths.

## Expected Student Output

- The exact effective rule and five-tuple evidence that explains the denied flow.
- A bounded blast radius, rejected alternatives, and the narrowest reversible remediation proposal.
- Post-remediation evidence that the original path recovered without weakening unrelated controls.

## Coach Runbook

1. Present the blocked-dependency exercise and confirm the target is the coach-provided sandbox before any fault or remediation action.
2. Require NIC and subnet associations, effective rules, direction, priority, protocol, source, destination, and port.
3. Ask the student to bound affected and unaffected paths before proposing a change.
4. Approve only a narrow reversible correction, then require both recovery and regression checks.

## Common Issues and Hints

- **Symptom:** Student inspects only subnet NSG. **Fix:** include NIC associations and effective rules.
- **Symptom:** Flow data is absent. **Fix:** label the evidence gap and use the supplied snapshot.
- **Symptom:** Proposed fix deletes a broad deny. **Fix:** require minimum-scope correction.

## Debrief Discussion Guide

1. Why do effective rules win? → Azure evaluates the combined NIC/subnet rule set, not one displayed NSG in isolation.
2. How is blast radius bounded? → Match the effective rule against actual source, destination, port, protocol, and direction, then test unaffected paths.
3. What proves recovery? → A successful original flow plus confirmation that unrelated denied paths remain denied.

## Success Criteria Notes

- **Require:** exact rule evidence, bounded blast radius, narrow correction, recovery proof, and control regression proof.
- **Reject:** production targeting, broad deny deletion, or portal-only reasoning.
- **Accept:** supplied flow snapshots when live Traffic Analytics has not ingested yet; label their timestamp.

[< Previous Solution](./Solution-11.md) | **[Home](./README.md)** | [Next Solution >](./Solution-13.md)

# Coach Guide — Challenge 12: Network Security Investigation

## Purpose

- Teach denied-flow forensics from Traffic Analytics through to the exact NSG rule and remediation.
- This is the clearest workshop example of using `NTANetAnalytics` as the primary evidence chain.
- Expected time: 20–25 minutes.

## Mini-Lecture (3–5 min before challenge)

- Draw the 5-tuple: app tier `10.20.0.0/16` → DB `10.30.2.10:5432/TCP` blocked by `Demo-Deny-App-To-Db-5432`.
- Show the autonomous routing path: `alert-denied-flow-spike` → `network-observability-review` → `network-traffic-analyst`.
- Critical callout: in `NTANetAnalytics`, `FlowStatus` is the full word **`Denied`**, not `D`.
- Explain Traffic Analytics lag: this is pattern analytics, not packet capture.

## Expected Student Output

- Alert appears in roughly 10–15 minutes (Traffic Analytics aggregation interval is 10 minutes; allow one full cycle before concluding the alert is delayed).
- Agent queries `NTANetAnalytics`, identifies source/destination/port/protocol, and names `Demo-Deny-App-To-Db-5432`.
- Agent runs `az network nsg rule delete` and rechecks that denied flows clear.
- Student can explain why the table/value choice matters for KQL accuracy.

## Common Issues and Hints

- **Symptom:** No denied records yet. **Fix:** wait for Traffic Analytics processing; if needed retry closer to 7–10 minutes.
- **Symptom:** Student filters on `FlowStatus == "D"`. **Fix:** correct them to `Denied` or denied counters.
- **Symptom:** Agent finds a deny but not the rule name. **Fix:** push them to correlate `AclRule`/NSG rule output, not stop at the tuple.
- **Symptom:** Application recovered but denied rows still appear in 24h window. **Fix:** narrow the time window and distinguish historical evidence from current state.
- **Symptom:** Agent identifies the blocking rule but `az network nsg rule delete` is refused with a permission error. **Fix:** verify the Terraform-managed Contributor assignment covers `rg-sre-spoke-data-iaas`, where `nsg-data` owns the injected rule.

## Debrief Discussion Guide

- Why are network drops harder than app errors to diagnose manually? → Little or no application-layer evidence.
- Why is Traffic Analytics enough here even though it is delayed? → The incident is pattern-based, not millisecond-sensitive.
- What does the full-word `Denied` detail teach? → Schema fidelity matters; old mental models break queries.

## Success Criteria Notes

- Be strict on naming the exact rule, not just “an NSG blocked it.”
- Allow manual prompt fallback if the alert is late.
- If the student uses restore script instead of watching the autonomous delete, have them still explain the intended remediation chain.

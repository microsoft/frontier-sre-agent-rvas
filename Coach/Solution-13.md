[< Previous Solution](./Solution-12.md) | **[Home](./README.md)** | [Next Solution >](./Solution-14.md)

# Coach Guide — Challenge 13: Routing Failure Investigation

## Purpose

- Teach UDR precedence, effective routes, next-hop reasoning, and why one-way success can still be an outage.
- This is the best interactive governance example because students can compare Review mode with Autonomous mode on the same fix.
- Expected time: 25–30 minutes.

## Mini-Lecture (3–5 min before challenge)

- Draw the asymmetry: forward path from app to DB works; return path from DB to app is black-holed by `Demo-Break-Return-To-App-Client` (`10.20.1.0/24 -> None`).
- Explain the red herring: `vm-vflta-nva` has IP forwarding enabled, but no route points to it.
- Name the main tools: `az network nic show-effective-route-table`, `az network watcher show-next-hop`, and `NTANetAnalytics` asymmetry evidence.
- Governance comparison to teach verbally: Review = propose then approve; Autonomous = fix immediately and verify.

## Expected Student Output

- Student invokes `/agent network-traffic-analyst` directly.
- Investigation identifies the more-specific UDR to `None` as the root cause.
- Student can explain why the forward path works while the return path fails.
- Agent proposes or applies the route correction and verifies connectivity restoration.

## Common Issues and Hints

- **Symptom:** Student fixates on the NVA VM. **Fix:** ask “what route actually points there?” If none, it is not in path.
- **Symptom:** Student checks only source-side routes. **Fix:** have them inspect the destination/return path explicitly.
- **Symptom:** They treat unequal bytes alone as proof. **Fix:** insist on effective route and next-hop evidence.
- **Symptom:** After remediation, stale asymmetry still appears historically. **Fix:** use a tighter time window for verification.
- **Symptom:** Agent identifies the bad UDR but route deletion is refused with a permission error. **Fix:** student set the agent permission to Reader in Challenge 00. In the SRE Agent portal → **Managed Resources**, change the permission to **Contributor** on the affected resource groups (`rg-sre-spoke-data` or the data-spoke route table RG).

## Debrief Discussion Guide

- Which route wins when a system route and a UDR both match? → The UDR always takes priority over system routes; specificity is a tiebreaker only when two UDRs overlap.
- Why is Review mode valuable for route changes? → Routing mistakes can expand blast radius quickly.
- What made the agent effective here? → It combined point-in-time route truth with historical flow evidence.

## Success Criteria Notes

- Be strict that students name the route `Demo-Break-Return-To-App-Client` and the next hop `None`.
- Accept either approved Review-mode or Autonomous-mode execution, but they must explain the governance difference.

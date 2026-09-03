[< Previous Solution](./Solution-12.md) | **[Home](./README.md)** | [Next Solution >](./Solution-14.md)

# Coach Guide — Challenge 13: Routing Failure Investigation

## Purpose

- Teach UDR precedence, effective routes, next-hop reasoning, and why one-way success can still be an outage.
- This is the best interactive governance discussion because the lab demonstrates Autonomous remediation and students evaluate where production should require Review.
- Expected time: 25–30 minutes.

## Mini-Lecture (3–5 min before challenge)

- Draw the asymmetry: forward path from app to DB works; return path from DB to app is black-holed by `Demo-Break-Return-To-App-Client` (`10.20.1.0/24 -> None`).
- Explain the red herring: `vm-nva` has IP forwarding enabled, but no route points to it.
- Name the decisive tools: `az network nic show-effective-route-table` and `az network watcher show-next-hop`. A UDR blackhole can leave no `NTANetAnalytics` row.
- Governance comparison to teach verbally: the configured custom agent is Autonomous; Review must be set on a trigger/task or governed workflow, not requested as an in-chat mode switch.

## Expected Student Output

- Student invokes `/agent network-traffic-analyst` directly.
- Investigation identifies the more-specific UDR to `None` as the root cause.
- Student can explain why the forward path works while the return path fails.
- Agent applies the route correction and verifies the active effective route plus Network Watcher next hop.

## Common Issues and Hints

- **Symptom:** Student fixates on the NVA VM. **Fix:** ask “what route actually points there?” If none, it is not in path.
- **Symptom:** Student checks only source-side routes. **Fix:** have them inspect the destination/return path explicitly.
- **Symptom:** They expect a denied-flow row for the blackhole. **Fix:** explain that the UDR can drop traffic before NSG flow evidence; insist on effective route and next-hop evidence.
- **Symptom:** After remediation, stale asymmetry still appears historically. **Fix:** use a tighter time window for verification.
- **Symptom:** Agent identifies the bad UDR but remediation is refused with a permission error. **Fix:** verify the Terraform-managed Contributor assignment covers `rg-sre-spoke-data-iaas`.

## Debrief Discussion Guide

- Which route wins when a system route and a UDR both match? → The UDR always takes priority over system routes; specificity is a tiebreaker only when two UDRs overlap.
- Why is Review mode valuable for route changes? → Routing mistakes can expand blast radius quickly.
- What made the agent effective here? → It combined point-in-time route truth with historical flow evidence.

## Success Criteria Notes

- Be strict that students name the route `Demo-Break-Return-To-App-Client` and the next hop `None`.
- Require the Autonomous execution evidence ..

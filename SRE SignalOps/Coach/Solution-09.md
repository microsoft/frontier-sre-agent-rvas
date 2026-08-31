[< Previous Solution](./Solution-08.md) | **[Home](./README.md)** | [Next Solution >](./Solution-10.md)

# Coach Guide — Challenge 09: Investigate a Routing Black Hole

## Purpose

Prove forward and return paths during a routing failure. Expected time: 25–30 minutes.

## Mini-Lecture (5 min before challenge)

Azure selects effective routes by longest prefix, then route source; asymmetric paths can fail despite a valid forward route.

## Expected Student Output

- Separate forward and return effective-route decisions with next-hop evidence.
- A named root-cause route, rejected DNS/NSG/NVA alternatives, and a narrow reversible correction.
- Recovery proof and restoration of every injected route change.

## Coach Runbook

1. Confirm the sandbox and record the injected route state so it can be restored.
2. Require effective NIC routes and next-hop checks for both directions; route-table definitions alone are insufficient.
3. Challenge DNS, NSG, and NVA hypotheses with one discriminating check each.
4. After correction, rerun connectivity and route evidence, then verify the injected state is fully restored.

## Common Issues and Hints

- **Symptom:** Only route-table definitions are shown. **Fix:** inspect effective NIC routes.
- **Symptom:** Forward path works but app fails. **Fix:** prove the return path.
- **Symptom:** DNS is assumed healthy. **Fix:** test and reject it with evidence.

## Debrief Discussion Guide

1. Why can portal configuration mislead? → A route table shows intent; effective NIC routes show the combined decision actually applied.
2. What creates asymmetry? → Different effective routes, longest-prefix matches, propagation paths, or middleboxes in each direction.
3. Which checks prove recovery? → Bidirectional next-hop evidence plus the original application connectivity test.

## Success Criteria Notes

- **Require:** both path directions, rejected alternatives, narrow correction, recovery proof, and full fault restoration.
- **Reject:** forward-path-only analysis or fixation on an NVA that no effective route selects.
- **Accept:** a supplied evidence pack if no safe network sandbox exists.

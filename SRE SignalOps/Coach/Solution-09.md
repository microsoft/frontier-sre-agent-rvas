[< Previous Solution](./Solution-08.md) | **[Home](./README.md)** | [Next Solution >](./Solution-10.md)

# Coach Guide — Challenge 09: Investigate a Routing Black Hole

## Purpose

Prove forward and return paths during a routing failure. Expected time: 25–30 minutes.

## Mini-Lecture (5 min before challenge)

Azure selects effective routes by longest prefix, then route source; asymmetric paths can fail despite a valid forward route.

## Expected Student Output

Bidirectional route decisions, next-hop evidence, rejected alternatives, correction, and recovery proof.

## Common Issues and Hints

- **Symptom:** Only route-table definitions are shown. **Fix:** inspect effective NIC routes.
- **Symptom:** Forward path works but app fails. **Fix:** prove the return path.
- **Symptom:** DNS is assumed healthy. **Fix:** test and reject it with evidence.

## Debrief Discussion Guide

1. Why can portal configuration mislead?
2. What creates asymmetry?
3. Which checks prove recovery?

## Success Criteria Notes

Require restoration of all injected route changes before Challenge 10.

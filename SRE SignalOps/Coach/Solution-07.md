[< Previous Solution](./Solution-06.md) | **[Home](./README.md)** | [Next Solution >](./Solution-08.md)

# Coach Guide — Challenge 07: Map the Application Dependency Graph

## Purpose

Establish an observed topology baseline before fault diagnosis. Expected time: 20–25 minutes.

## Mini-Lecture (5 min before challenge)

Architecture is intended structure; an incident map is observed request behavior with time and health evidence.

## Expected Student Output

- A directed dependency diagram and matching edge table with time window, volume, latency, failures, and evidence source.
- A critical path, single points of failure, and explicit telemetry coverage gaps.

## Coach Runbook

1. Generate recent API traffic, then confirm requests exist before asking for a map.
2. Require each edge to identify caller, callee, protocol/type, time window, volume, latency, failures, and evidence source.
3. Compare the diagram with the edge table; numbers and direction must agree.
4. Label intended but unobserved dependencies instead of drawing them as telemetry-proven edges.

## Common Issues and Hints

- **Symptom:** Map contains unsupported edges. **Fix:** require telemetry or label them documented-only.
- **Symptom:** Dependencies have no direction. **Fix:** identify caller and callee.
- **Symptom:** Health is based on one request. **Fix:** use a representative time window.

## Debrief Discussion Guide

1. Which edge is most critical? → The one whose failure combines high traffic, poor alternatives, and material user impact.
2. What telemetry is missing? → Listen for browser, third-party, async, or low-volume paths not represented in the selected window.
3. How would sampling distort the graph? → Rare failures and low-volume edges may disappear while aggregate latency looks healthier.

## Success Criteria Notes

- **Require:** direction, evidence status, measurement window, and matching diagram/table facts for every edge.
- **Reject:** invented dependencies or health claims based on one request.
- **Accept:** missing edges when they are explicitly labeled unobserved and paired with a collection plan.

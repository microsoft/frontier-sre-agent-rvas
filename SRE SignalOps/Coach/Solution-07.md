[< Previous Solution](./Solution-06.md) | **[Home](./README.md)** | [Next Solution >](./Solution-08.md)

# Coach Guide — Challenge 07: Map the Application Dependency Graph

## Purpose

Establish an observed topology baseline before fault diagnosis. Expected time: 20–25 minutes.

## Mini-Lecture (5 min before challenge)

Architecture is intended structure; an incident map is observed request behavior with time and health evidence.

## Expected Student Output

A dependency diagram, edge table, critical path, and telemetry coverage gaps.

## Common Issues and Hints

- **Symptom:** Map contains unsupported edges. **Fix:** require telemetry or label them documented-only.
- **Symptom:** Dependencies have no direction. **Fix:** identify caller and callee.
- **Symptom:** Health is based on one request. **Fix:** use a representative time window.

## Debrief Discussion Guide

1. Which edge is most critical?
2. What telemetry is missing?
3. How would sampling distort the graph?

## Success Criteria Notes

Every edge must carry evidence status and direction.

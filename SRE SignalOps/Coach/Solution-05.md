[< Previous Solution](./Solution-04.md) | **[Home](./README.md)** | [Next Solution >](./Solution-06.md)

# Coach Guide — Challenge 05: Discover Specialist Agents

## Purpose

Assess specialist ownership, routing, and least privilege. Expected time: 15–20 minutes.

## Mini-Lecture (5 min before challenge)

Subagents reduce cognitive and permission scope only when their contracts are distinct.

## Expected Student Output

A specialist roster, three routing tests, overlap findings, and capability gaps.

## Common Issues and Hints

- **Symptom:** Every prompt routes to one agent. **Fix:** compare routing descriptions for overlap.
- **Symptom:** Tool grants are unknown. **Fix:** inspect manifests rather than relying on names.
- **Symptom:** A write-capable agent has no gate. **Fix:** keep it disabled until approval is configured.

## Debrief Discussion Guide

1. When is a skill enough?
2. What makes routing defensible?
3. How does specialization reduce blast radius?

## Success Criteria Notes

Require routing reasons, not only selected agent names.

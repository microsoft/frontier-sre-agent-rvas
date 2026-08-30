[< Previous Solution](./Solution-01.md) | **[Home](./README.md)** | [Next Solution >](./Solution-03.md)

# Coach Guide — Challenge 02: Validate Existing Ground Truth

## Purpose

Audit the currently deployed source, knowledge, and telemetry evidence planes without changing them. Expected time: 20–25 minutes.

## Mini-Lecture (5 min before challenge)

Source explains implementation, knowledge explains intent, and telemetry explains current behavior. None substitutes for another.

## Expected Student Output

Two live Azure telemetry connectors, an empty repository list reported as a gap, Agent Memory enabled with a successful indexer but zero files, and Azure answers verified against live resources.

## Common Issues and Hints

- **Symptom:** Repository list is empty. **Fix:** record the current source-evidence gap; do not authorize OAuth during this mission.
- **Symptom:** Agent Memory is enabled but answers lack document context. **Fix:** show the successful indexer and zero-file inventory; distinguish service health from populated knowledge.
- **Symptom:** Data-plane call returns 401. **Fix:** request a token for `https://azuresre.dev`.

## Debrief Discussion Guide

1. Which facts expire fastest?
2. What should never enter knowledge?
3. How should conflicting sources be handled?

## Success Criteria Notes

Require both ARM connectors, an independent PowerShell comparison with live resource state, and accurate disclosure that repositories and knowledge files are empty. No connector or content mutation is acceptable.

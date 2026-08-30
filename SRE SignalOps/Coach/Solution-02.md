[< Previous Solution](./Solution-01.md) | **[Home](./README.md)** | [Next Solution >](./Solution-03.md)

# Coach Guide — Challenge 02: Connect Ground Truth

## Purpose

Connect source, knowledge, and telemetry while preserving credential boundaries. Expected time: 20–25 minutes.

## Mini-Lecture (5 min before challenge)

Source explains implementation, knowledge explains intent, and telemetry explains current behavior. None substitutes for another.

## Expected Student Output

Authorized GitHub connection, indexed knowledge, and agent answers verified against live Azure resources.

## Common Issues and Hints

- **Symptom:** Repository exists but tests fail. **Fix:** complete OAuth authorization in the portal.
- **Symptom:** Knowledge answers remain generic. **Fix:** wait for indexer completion and use specific document titles.
- **Symptom:** Data-plane call returns 401. **Fix:** request a token for `https://azuresre.dev`.

## Debrief Discussion Guide

1. Which facts expire fastest?
2. What should never enter knowledge?
3. How should conflicting sources be handled?

## Success Criteria Notes

Require one independent PowerShell comparison with live resource state.

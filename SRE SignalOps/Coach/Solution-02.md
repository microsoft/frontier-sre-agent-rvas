[< Previous Solution](./Solution-01.md) | **[Home](./README.md)** | [Next Solution >](./Solution-03.md)

# Coach Guide — Challenge 02: Deploy Evidence Connectors with azd

## Purpose

Complete the azd infrastructure stages with Log Analytics and Application Insights connectors, then audit source, knowledge, and telemetry evidence. Expected time: 20–25 minutes plus Azure provisioning time.

## Mini-Lecture (5 min before challenge)

Connectors create an authorized evidence path; they do not guarantee useful data. Source explains implementation, knowledge explains intent, and telemetry explains current behavior. None substitutes for another.

## Expected Student Output

A reviewed connector-only preview, two live Azure telemetry connectors owned by the same azd environment, and an accurate inventory of repository, Agent Memory, and knowledge state.

## Common Issues and Hints

- **Symptom:** Preview replaces the agent or workload. **Fix:** stop and confirm the same `signalops-core` environment is selected before provisioning.
- **Symptom:** Repository list is empty. **Fix:** record the source-evidence gap; do not authorize OAuth during this mission.
- **Symptom:** Agent Memory is enabled but answers lack document context. **Fix:** show the successful indexer and zero-file inventory; distinguish service health from populated knowledge.
- **Symptom:** Data-plane call returns 401. **Fix:** request a token for `https://azuresre.dev`.

## Debrief Discussion Guide

1. Which evidence resources are provisioned by azd, and which require later data-plane authorization?
2. Which facts expire fastest, and what should never enter knowledge?
3. How should conflicting telemetry, source, and knowledge be handled?

## Success Criteria Notes

Require a reviewed preview, both ARM connectors with azd-owned resource IDs, an independent live resource comparison, and accurate disclosure of repository and knowledge state. No token may be persisted.

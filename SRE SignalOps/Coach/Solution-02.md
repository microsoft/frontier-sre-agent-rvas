[< Previous Solution](./Solution-01.md) | **[Home](./README.md)** | [Next Solution >](./Solution-03.md)

# Coach Guide — Challenge 02: Deploy Evidence Connectors with azd

## Purpose

Complete the azd infrastructure stages with Log Analytics and Application Insights connectors, then audit source, knowledge, and telemetry evidence. Expected time: 20–25 minutes plus Azure provisioning time.

## Mini-Lecture (5 min before challenge)

Connectors create an authorized evidence path; they do not guarantee useful data. Source explains implementation, knowledge explains intent, and telemetry explains current behavior. None substitutes for another.

## Expected Student Output

- A reviewed preview that adds connector configuration without replacing the agent or workload.
- Two live Azure telemetry connectors owned by the same azd environment.
- Separate, accurate statements about connector deployment, repository content, Agent Memory health, knowledge files, and live telemetry.

## Coach Runbook

1. Confirm both deployment flags are `true` and the same azd environment from Missions 00–01 is selected.
2. Explain that azd's summary may omit child connectors; use the connector list or compiled ARM graph as evidence.
3. Require the student to report repository, Agent Memory, knowledge-file, and telemetry state independently.
4. Stop if a student stores an access token, authorizes OAuth, or uploads knowledge merely to make an empty-state check look successful.

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

- **Require:** both connector types and sources, an independent live-resource comparison, and honest disclosure of empty or unproven evidence planes.
- **Reject:** treating connector existence as proof that useful data exists, or persisting any token.
- **Accept:** an empty repository or knowledge inventory when it is reported accurately.

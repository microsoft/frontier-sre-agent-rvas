[< Previous Solution](./Solution-01.md) | **[Home](../README.md)** | [Next Solution >](../Missions/Solution-01.md)

# Coach Guide — Deployment stage 02: Deploy Evidence and Incident Routing with azd

## Purpose

Complete the azd infrastructure stages with Log Analytics and Application Insights connectors, the Grubify response subagent, and an all-severity Review response plan. Then audit source, knowledge, telemetry, and routing state. Expected time: 25–30 minutes plus Azure provisioning time.

## Mini-Lecture (5 min before challenge)

Connectors create an authorized evidence path; they do not guarantee useful data. A response plan separately decides which alerts are routed, which subagent handles them, and whether writes require approval. Azure Monitor's one-minute evaluation affects detection latency; reinvestigation cooldown only suppresses duplicate processing.

## Expected Student Output

- A reviewed preview that adds connector configuration without replacing the agent or workload.
- Two live Azure telemetry connectors owned by the same azd environment.
- Three live Review specialists (`aca-app-incident-handler`, `network-traffic-analyst`, `cost-optimization-agent`) and enabled `sample-food-http-errors` plan covering `Sev0` through `Sev4`, matching `grubify`, in `Review` mode with one automated attempt.
- Separate, accurate statements about connector deployment, repository content, Agent Memory health, knowledge files, and live telemetry.

## Coach Runbook

1. Confirm both deployment flags are `true` and the same azd environment from Deployment stages 00–01 is selected.
2. Explain that the ARM preview contains two connectors. The postprovision hook separately calls `Register-SignalOpsAgent.ps1` and verifies three specialists plus the response plan. A failed hook must be resolved before Mission 01.
3. Require live data-plane inventory for the handler and response plan before Mission 01 begins.
4. Confirm all five Azure Monitor severities, `grubify`, `Review`, and one automated attempt. Do not represent cooldown as an initial-response timer.
5. Require the student to report repository, Agent Memory, knowledge-file, and telemetry state independently.
6. Stop if a student stores an access token, authorizes OAuth, or uploads knowledge merely to make an empty-state check look successful.

## Common Issues and Hints

- **Symptom:** Preview replaces the agent or workload. **Fix:** stop and confirm the same `signalops-core` environment is selected before provisioning.
- **Symptom:** Repository list is empty. **Fix:** record the source-evidence gap; do not authorize OAuth during this mission.
- **Symptom:** Agent Memory is enabled but answers lack document context. **Fix:** show the successful indexer and zero-file inventory; distinguish service health from populated knowledge.
- **Symptom:** Data-plane call returns 401. **Fix:** request a token for `https://azuresre.dev`.
- **Symptom:** Mission 01 alert fires but no incident appears. **Fix:** verify the live plan is on, includes `Sev2`, matches `grubify`, and routes to the registered handler.
- **Symptom:** The team expects a one-minute guaranteed agent response. **Fix:** explain that one minute is the alert evaluation frequency; ingestion and investigation start are asynchronous.

## Debrief Discussion Guide

1. Which evidence resources are provisioned by azd, and which require later data-plane authorization?
2. Which settings determine whether a Mission 01 alert reaches the handler?
3. Why does `Review` preserve approval even when the subagent has write-capable tools?
4. Which facts expire fastest, and what should never enter knowledge?

## Success Criteria Notes

- **Require:** both connector types and sources, live handler and plan registration, all-severity routing, `Review` mode, one attempt, an independent live-resource comparison, and honest disclosure of empty or unproven evidence planes.
- **Reject:** starting Mission 01 with an absent or mismatched plan, treating cooldown as first-response latency, treating connector existence as proof that useful data exists, or persisting any token.
- **Accept:** an empty repository or knowledge inventory when it is reported accurately.

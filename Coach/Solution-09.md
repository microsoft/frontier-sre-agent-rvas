[< Previous Solution](./Solution-08.md) | **[Home](./README.md)** | [Next Solution >](./Solution-10.md)

# Coach Guide — Challenge 09: Daily Application Health Report

## Purpose

- Teach daily operational summarization and introduce SLI/SLO language in a concrete report format.
- This is the bridge from raw telemetry to an on-call-readable health narrative.
- Expected time: 20 minutes.

## Mini-Lecture (3–5 min before challenge)

- Define the fields as SLIs: CPU, memory, requests, response time, error rate.
- Explain the scoring exercise: students create operational judgments (Healthy/Degraded/Critical) from indicators, not just raw numbers.
- Point out that Berlin may still depend on the missing OpenTelemetry connector; require explicit `N/A` when absent.
- The YAML-design part is conceptual: compare against scheduled-task patterns already in the lab, even if a Parking Manager-specific task is not exposed in this default config bundle.

## Expected Student Output

- Student produces a four-service table for Lisbon, Madrid, Paris, and Berlin (or Berlin marked unavailable).
- Each service has a health status with rationale.
- Student explains what first investigation step they would take for any degraded service.
- Student can describe the main scheduled-task YAML fields: `metadata.name`, `schedule`, `time_zone`, `agent`, `mode`, `prompt`, `enabled`.

## Common Issues and Hints

- **Symptom:** Student reports metrics but no judgment. **Fix:** prompt for scoring logic explicitly.
- **Symptom:** Berlin row missing. **Fix:** require a row with `N/A` and note the missing OpenTelemetry connector.
- **Symptom:** Student cannot find a Parking Manager-specific scheduled task in the repo. **Fix:** compare to `daily-network-observability-health` as the reference pattern and discuss how they would adapt it.

## Debrief Discussion Guide

- Which columns are SLIs and where would SLOs live? → SLIs are measured values; SLOs live in policy/runbooks/knowledge or governance config.
- Why does a daily health report matter if alerts already exist? → It catches trends and low-grade degradation.
- What does the Berlin gap teach? → Reporting must represent missing telemetry honestly.

## Success Criteria Notes

- Be flexible on exact thresholds if the student states a coherent rationale.
- Be strict on including all four services, even if one is unavailable.
- Accept a conceptual scheduled-task YAML walkthrough when no tenant-specific task exists.

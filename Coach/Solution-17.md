[< Previous Solution](./Solution-16.md) | **[Home](./README.md)** | [Next Solution >](./Solution-18.md)

# Coach Guide — Challenge 17: Observability Freshness Verification

## Purpose

- Teach “monitoring the monitoring”: proving the telemetry pipeline is alive, fresh, and complete.
- This is a high-value SRE habit because silent observability failure makes every dashboard lie.
- Expected time: 20 minutes.

## Mini-Lecture (3–5 min before challenge)

- Draw the evidence chain: enabled VNet Flow Log → configured private Storage destination → recent Storage `Transactions` metrics → Traffic Analytics aggregation (10 min) → newest `NTANetAnalytics` record.
- Name the scheduled task exactly: `flow-log-ingestion-freshness`, every 6 hours, `network-traffic-analyst`, `Autonomous`.
- Explain desired-state comparison: expected VNets from Terraform vs actual VNets seen in `NTANetAnalytics`.
- Stress that a healthy app plus stale telemetry is still an operational emergency.

## Expected Student Output

- Student checks all three flow-log ARM configurations, recent Storage `Transactions`, and latest `NTANetAnalytics` timestamps.
- Output calls out expected vs actual VNet coverage: hub, app spoke, data spoke.
- Student can explain the full telemetry chain and where it can break silently.
- Student can justify the higher cadence relative to the daily network health report.

## Common Issues and Hints

- **Symptom:** Student only queries Log Analytics. **Fix:** require flow-log ARM state and Storage transaction metrics too; otherwise they are not validating the full pipeline.
- **Symptom:** They expect zero lag. **Fix:** compare against the configured 10-minute processing interval and observed ingestion delay.
- **Symptom:** Missing VNet not detected. **Fix:** compare against Terraform outputs or documented expected VNets explicitly.
- **Symptom:** Storage data-plane read fails. **Fix:** treat that as a permission finding, not proof the blobs are absent.

## Debrief Discussion Guide

- What is the difference between monitoring an app and monitoring the telemetry pipeline? → Service health vs trustworthiness of the measurement system.
- Why run this every 6 hours instead of daily? → Silent telemetry loss is more urgent than slow trend reporting.
- How would you copy this pattern to App Insights? → Last-seen request/exception/dependency freshness and expected-component coverage.

## Success Criteria Notes

- Be strict on the full chain, not just one hop.
- Do not accept weakening Storage access as a workaround; require the metrics-based evidence path.

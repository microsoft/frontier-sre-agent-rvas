---
title: Observability Freshness Verification
summary: Check VNet Flow Log freshness in Storage and Traffic Analytics. Compare expected VNet coverage with recent records to find missing or stale telemetry.
phase: Scheduled
group: Proactive and scheduled operations
tags:
- telemetry validation
- VNet Flow Logs
- coverage analysis
highlight: false
---

# Challenge 17 — Observability Freshness Verification

> **Application focus:** Infrastructure/platform only

> **Capability**: Telemetry validation · Monitoring the monitoring · Coverage analysis

## Purpose

- Identify a telemetry source that is stale or missing, and show how that gap could hide a failure while dashboards show no alerts.
- Expected time: 20 minutes.

## Introduction

No recent alerts can mean no telemetry is arriving, not that the system is healthy. Check timestamps and VNet coverage in Storage and Log Analytics to tell the two apart.

Challenge 16 used telemetry to report network health. This challenge checks the pipeline that supplies that telemetry.

## Description

### Before you start

Confirm the Grubify lab has active VNet Flow Logs:

```bash
make validate
```

### Step 1 — Run the freshness check manually

Invoke the `network-traffic-analyst` specialist:

```text
/agent network-traffic-analyst

Check whether VNet Flow Logs are producing recent data in both Storage and Traffic Analytics. Specifically:
1. For each of the three VNet Flow Logs (hub, app spoke, data spoke): confirm the most recent blob timestamp in the storage account.
2. Query NTANetAnalytics in Log Analytics for the most recent record timestamp.
3. Compare the expected VNets (from the lab's Terraform outputs) with the VNets that actually appear in NTANetAnalytics.
4. Report any VNets that are missing from Log Analytics, any ingestion gaps greater than 15 minutes, or any storage blobs older than 30 minutes.

Do not change any resources.
```

### Step 2 — Understand the pipeline chain

Ask the agent to describe the full pipeline:

```text
Walk me through the complete telemetry chain for VNet Flow Logs in this lab — from a network packet being allowed or denied, to a record appearing in NTANetAnalytics in Log Analytics. What are all the hops, and where can the pipeline break silently?
```

The chain is:

- VNet Flow Log enabled on the VNet → writes JSON blobs to storage account (every 1 minute)
- Traffic Analytics reads storage blobs → aggregates to NTANetAnalytics (every 10 minutes)
- Log Analytics ingests NTANetAnalytics records → available for KQL query

Each hop can fail silently: Log Analytics can appear healthy even if the storage account stops writing, or if Traffic Analytics stops processing.

### Step 3 — Simulate a coverage gap

Ask the agent how it would detect a missing VNet:

```text
If fl-spoke-data (the data spoke flow log) stopped writing, what would the freshness check look like 20 minutes later? What is the earliest you could detect it with this schedule?
```

### Step 4 — Inspect the scheduled task

In the portal under **Scheduled Tasks**, open `flow-log-ingestion-freshness`.

This task runs every 6 hours (`cron: 0 */6 * * *`), more often than the daily network health report. Think about why.

### Step 5 — Extend the concept

Ask the agent:

```text
How would you apply the same "monitoring the monitoring" pattern to Application Insights? What would a freshness check look like for the Grubify API's telemetry pipeline?
```

## Success Criteria

- [ ] The agent queries storage account blob timestamps for all three VNet Flow Logs
- [ ] The agent queries `NTANetAnalytics` for the most recent record timestamp per VNet
- [ ] The agent compares expected VNets (from Terraform) with actual VNets in Log Analytics and identifies any gaps
- [ ] You can describe all hops in the VNet Flow Log pipeline and where each can fail silently
- [ ] You can explain why freshness verification runs at higher cadence (every 6 hours) than the daily health report
- [ ] **Explain in your own words** (two or three written sentences) — what is the difference between *monitoring an application* and *monitoring the monitoring pipeline*? Give a concrete example where the application is healthy but the monitoring pipeline has failed silently.

## Learning Resources

- [VNet Flow Logs — storage format](https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview#log-format)
- [Traffic Analytics — data aggregation interval](https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics#data-aggregation)
- [Log Analytics — data ingestion latency](https://learn.microsoft.com/en-us/azure/azure-monitor/logs/data-ingestion-time)
- [Azure SRE Agent — scheduled tasks](https://learn.microsoft.com/en-us/azure/sre-agent/scheduled-tasks)

## Tips

- VNet Flow Logs write blobs to the storage account every 1 minute. Traffic Analytics aggregates them every 10 minutes. Log Analytics ingestion adds a further 2–5 minutes. Total expected end-to-end latency: ~15 minutes under normal conditions. Any gap beyond 20–30 minutes is a signal to investigate.
- Terraform outputs only partly cover the expected VNets. `demo_lab_scenario_resource_names` exposes `app_vnet` and `data_vnet`, but not the hub VNet name, which appears only in the Terraform configuration (`vnet-hub` in `modules/workload/network.tf`). So the `vnet-flow-logs-and-ingestion` skill's expected-VNet list (hub, spoke-app, spoke-data) is hardcoded from the configuration. If you add a VNet, update both the Terraform configuration and the skill's list.
- Comparing desired state (Terraform) with actual state (Log Analytics) is the pattern used throughout the lab. Apply it to any telemetry pipeline where silent loss is possible.

## Hints and notes

> Hidden until you click. Expand a section only when you want it.

<details>
<summary><strong>Background</strong></summary>

- The evidence chain is: enabled VNet Flow Log → configured private Storage destination → recent Storage `Transactions` metrics → Traffic Analytics aggregation (10 min) → newest `NTANetAnalytics` record.
- The scheduled task is `flow-log-ingestion-freshness`, every 6 hours, `network-traffic-analyst`, `Autonomous`.
- The check compares desired state with actual state: expected VNets from Terraform vs VNets seen in `NTANetAnalytics`.
- A healthy app with stale telemetry is still an operational emergency.

</details>

<details>
<summary><strong>Expected Output</strong></summary>

- You check all three flow-log ARM configurations, recent Storage `Transactions`, and latest `NTANetAnalytics` timestamps.
- Output calls out expected vs actual VNet coverage: hub, app spoke, data spoke.
- You can explain the full telemetry chain and where it can break silently.
- You can justify the higher cadence relative to the daily network health report.

</details>

<details>
<summary><strong>Common Issues and Hints</strong></summary>

- **Symptom:** You only query Log Analytics. **Fix:** require flow-log ARM state and Storage transaction metrics too; otherwise you aren't validating the full pipeline.
- **Symptom:** You expect zero lag. **Fix:** compare against the configured 10-minute processing interval and observed ingestion delay.
- **Symptom:** Missing VNet not detected. **Fix:** compare against Terraform outputs or documented expected VNets explicitly.
- **Symptom:** Storage data-plane read fails. **Fix:** treat that as a permission finding, not proof the blobs are absent.

</details>

<details>
<summary><strong>Debrief Discussion Guide</strong></summary>

- What is the difference between monitoring an app and monitoring the telemetry pipeline? → Service health vs trustworthiness of the measurement system.
- Why run this every 6 hours instead of daily? → Silent telemetry loss is more urgent than slow trend reporting.
- How would you copy this pattern to App Insights? → Last-seen request/exception/dependency freshness and expected-component coverage.

</details>

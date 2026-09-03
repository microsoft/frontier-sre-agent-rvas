[< Previous Challenge](./Challenge-16.md) — **[Home](../README.md)** — [Next Challenge >](./Challenge-18.md)

# Challenge 17 — Observability Freshness Verification

> **Capability**: Telemetry validation · Monitoring the monitoring · Coverage analysis

## Introduction

The most dangerous failure mode in operations is **silent telemetry loss**: every dashboard is green, every alert threshold is calm, every health check passes — because no data is arriving. You're not monitoring a healthy system; you're flying blind with gauges frozen at the last known reading.

Continuous telemetry freshness verification is the antidote: a scheduled task that doesn't just use the monitoring pipeline, but proves that the pipeline itself is **alive, current, and complete** — end to end, from the VNet to the Log Analytics workspace.

Where Challenge 16 used the monitoring pipeline to report on network health, this challenge turns the lens around and **validates the pipeline itself** — ensuring the data the agent depends on is actually flowing, end to end.

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

Note: this task runs every 6 hours (`cron: 0 */6 * * *`) — higher cadence than the daily network health report. Discuss with your coach why.

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
- [ ] **Explain to your coach** — what is the difference between *monitoring an application* and *monitoring the monitoring pipeline*? Give a concrete example where the application is healthy but the monitoring pipeline has failed silently.

## Learning Resources

- [VNet Flow Logs — storage format](https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview#log-format)
- [Traffic Analytics — data aggregation interval](https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics#data-aggregation)
- [Log Analytics — data ingestion latency](https://learn.microsoft.com/en-us/azure/azure-monitor/logs/data-ingestion-time)
- [Azure SRE Agent — scheduled tasks](https://learn.microsoft.com/en-us/azure/sre-agent/scheduled-tasks)

## Tips

- VNet Flow Logs write blobs to the storage account every 1 minute. Traffic Analytics aggregates them every 10 minutes. Log Analytics ingestion adds a further 2–5 minutes. Total expected end-to-end latency: ~15 minutes under normal conditions. Any gap beyond 20–30 minutes is a signal to investigate.
- The Terraform outputs only partially cover the expected VNets: `demo_lab_scenario_resource_names` exposes `app_vnet` and `data_vnet`, but not the hub VNet name — that one is only visible in the Terraform configuration itself (`vnet-hub` in `modules/workload/network.tf`). The `vnet-flow-logs-and-ingestion` skill's expected-VNet list (hub, spoke-app, spoke-data) is hardcoded from the Terraform configuration for this reason, not derived purely from outputs. If a VNet is added, update both the Terraform configuration and the skill's expected list.
- This pattern — desired state (Terraform) versus actual state (Log Analytics) — is the same pattern used throughout the lab for resource configuration. Apply it to any telemetry pipeline where silent loss is possible.

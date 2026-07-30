[< Previous Challenge](./Challenge-11.md) — **[Home](../README.md)** — [Next Challenge >](./Challenge-13.md)

# Challenge 12 — Network Security Investigation

> **Capability**: NSGs · Flow Logs · Traffic Analytics · Network forensics

## Introduction

Nothing crashes. Nothing restarts. The metrics look fine. But the application can't reach the database — and nobody knows why.

Silent traffic drops caused by **Network Security Group** deny rules are among the most time-consuming incidents to investigate manually: they leave no application-level error messages, only denied flows buried in network telemetry. In this challenge you'll inject an NSG misconfiguration, watch the agent find the exact blocking rule from flow log evidence, and remediate it autonomously.

## Description

### Before you start

Verify the Grubify lab network is clean and baseline traffic is flowing:

```bash
make validate
make baseline-traffic
```

### Step 1 — Inject the NSG block

```bash
make trigger-nsg-block
```

This creates NSG rule `Demo-Deny-App-To-Db-5432` (Deny TCP `10.20.0.0/16 → 10.30.2.10:5432`) on the app-spoke NSG and generates traffic that is now blocked.

### Step 2 — Wait for the alert

The log-search alert `alert-vflta-denied-flow-spike` fires on a Sev2 threshold: a spike in `FlowStatus = Denied` flows in the `NTANetAnalytics` Traffic Analytics table. Traffic Analytics aggregates flow data on a **10-minute interval**, so within **10–15 minutes** the incident should appear in the SRE Agent portal under **Incident Response**.

### Step 3 — Observe the autonomous investigation

The response plan `network-observability-review` (Sev2, `titleContains: Denied`) routes this incident to the `network-traffic-analyst` subagent in **Autonomous** mode. Watch the agent:

1. Query `NTANetAnalytics` for denied flows — source IP, destination IP, destination port, protocol
2. Identify the exact flow match criteria (source prefix, destination IP, port, protocol) of the blocked traffic
3. Correlate the flow match criteria with NSG rules to name the specific blocking rule (`Demo-Deny-App-To-Db-5432`)
4. Remove the NSG deny rule via `az network nsg rule delete`
5. Re-query flow logs to confirm denied flows have cleared

> If the alert hasn't fired after 20 minutes, trigger the investigation manually using the prompt below.

**Manual fallback prompt:**
```text
The application tier can no longer reach PostgreSQL on port 5432. Investigate the denied flows, identify the blocking rule and the exact flow match criteria, and fix it.
```

### Step 4 — Restore (if needed)

```bash
make restore-nsg-block
```

### Step 5 — Review the evidence chain

In the portal, read the agent's investigation log. Verify:

- The KQL query against `NTANetAnalytics` that identified the denied flows
- The exact flow match criteria: source `10.20.0.0/16`, destination `10.30.2.10`, port `5432`, protocol TCP
- The `az network nsg rule` commands used to identify and delete the rule
- The post-fix flow log query confirming remediation

## Success Criteria

- [ ] The `alert-vflta-denied-flow-spike` alert fired and appeared in the SRE Agent portal
- [ ] The agent queried `NTANetAnalytics` and identified the denied flow match criteria correctly
- [ ] The agent named the specific NSG rule (`Demo-Deny-App-To-Db-5432`) as the cause
- [ ] The agent deleted the NSG rule and verified that denied flows cleared
- [ ] **Explain to your coach** — why does `NTANetAnalytics` store `FlowStatus = "Denied"` as the full word rather than a single character? How does this affect the KQL query you write?

## Learning Resources

- [VNet Flow Logs overview](https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview)
- [Traffic Analytics overview](https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics)
- [NSG — security rule evaluation](https://learn.microsoft.com/en-us/azure/virtual-network/network-security-group-how-it-works)
- [KQL — NTANetAnalytics schema](https://learn.microsoft.com/en-us/azure/azure-monitor/reference/tables/ntanetanalytics)

## Tips

- `NTANetAnalytics` is populated by Traffic Analytics on a configurable interval (10 minutes in this lab). If the denied flows aren't appearing yet, wait for the next aggregation cycle.
- The `FlowStatus` field in `NTANetAnalytics` stores the full word `"Denied"` (not `"D"` as in the older NSG flow log V1 format). The `nsg-deny-flow-investigation` skill already accounts for this.
- Traffic Analytics denied flow data lags real-time by the aggregation interval. Use NSG flow logs in storage for second-by-second forensics; use Traffic Analytics for pattern analysis over minutes to hours.
- The `titleContains: Denied` condition in the `network-observability-review` response plan routes denied-flow spike alerts to the network analyst. The sibling `web-tier-nginx` plan uses `titleContains: nginx` to capture nginx failures — each filter owns a distinct keyword so alerts never overlap.

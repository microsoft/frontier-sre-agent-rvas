---
title: Network Security Investigation
summary: Inject an NSG rule that blocks database traffic. Check whether the agent traces denied flows to the rule, removes it, and verifies recovery.
phase: Autonomous
group: Autonomous incident response
tags:
- NSG
- Flow Logs
- Traffic Analytics
highlight: false
---

# Challenge 12 — Network Security Investigation

> **Application focus:** Infrastructure/platform only

> **Capability**: NSGs · Flow Logs · Traffic Analytics · Network forensics

## Purpose

- Trace a denied flow from Traffic Analytics to the exact NSG rule that blocked it, and state the fix.
- Use `NTANetAnalytics` as the primary flow evidence.
- Expected time: 20–25 minutes.

## Introduction

An NSG deny rule can block database traffic while the VMs remain running. Inject this fault, then check whether the agent traces the denied flows to the exact rule, removes it, and verifies recovery.

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
make baseline-traffic
```

This creates NSG rule `Demo-Deny-App-To-Db-5432` (Deny TCP `10.20.0.0/16 → 10.30.2.10:5432`) on the data-spoke NSG (`nsg-data`) and generates traffic that is now blocked.

### Step 2 — Wait for the alert

The log-search alert `alert-denied-flow-spike` fires on a Sev2 threshold: a spike in `FlowStatus = Denied` flows in the `NTANetAnalytics` Traffic Analytics table. Traffic Analytics aggregates flow data on a **10-minute interval**, so within **10–15 minutes** the incident should appear in the SRE Agent portal under **Incident Response**.

### Step 3 — Observe the autonomous investigation

The response plan `network-denied-flows-review` (Sev2, `titleContains: "Denied VNet flow"`, excluding `nginx`) routes this incident to the `network-traffic-analyst` subagent in **Autonomous** mode. Watch the agent:

1. Query `NTANetAnalytics` for denied flows — source IP, destination IP, destination port, protocol
2. Identify the exact flow match criteria (source prefix, destination IP, port, protocol) of the blocked traffic
3. Correlate the flow match criteria with NSG rules to name the specific blocking rule (`Demo-Deny-App-To-Db-5432`)
4. Remove the NSG deny rule via `az network nsg rule delete`
5. Re-query flow logs to confirm denied flows have cleared

> If the alert hasn't fired after 20 minutes, trigger the investigation manually with the prompt below.

**Manual fallback prompt:**
```text
The application tier can no longer reach PostgreSQL on port 5432. Investigate the denied flows, identify the blocking rule and the exact flow match criteria, and fix it.
```

### Step 4 — Restore (if needed)

```bash
make restore-nsg-block
```

### Step 5 — Review the evidence chain

In the portal, read the agent's investigation log and verify:

- The KQL query against `NTANetAnalytics` that identified the denied flows
- The exact flow match criteria: source `10.20.0.0/16`, destination `10.30.2.10`, port `5432`, protocol TCP
- The `az network nsg rule` commands used to identify and delete the rule
- The post-fix flow log query confirming remediation

## Success Criteria

- [ ] The `alert-denied-flow-spike` alert fired and appeared in the SRE Agent portal
- [ ] The agent queried `NTANetAnalytics` and identified the denied flow match criteria correctly
- [ ] The agent named the specific NSG rule (`Demo-Deny-App-To-Db-5432`) as the cause
- [ ] The agent deleted the NSG rule and verified that denied flows cleared
- [ ] **Explain in your own words** (two or three written sentences) — you filter denied flows in `NTANetAnalytics` and get zero rows. Given that `FlowStatus` stores the full word "Denied", what did your query likely get wrong, and how do you fix it?

## Learning Resources

- [VNet Flow Logs overview](https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview)
- [Traffic Analytics overview](https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics)
- [NSG — security rule evaluation](https://learn.microsoft.com/en-us/azure/virtual-network/network-security-group-how-it-works)
- [KQL — NTANetAnalytics schema](https://learn.microsoft.com/en-us/azure/azure-monitor/reference/tables/ntanetanalytics)

## Tips

- `NTANetAnalytics` is populated by Traffic Analytics on a configurable interval (10 minutes in this lab). If the denied flows aren't appearing yet, wait for the next aggregation cycle.
- The `FlowStatus` field in `NTANetAnalytics` stores the full word `"Denied"` (not `"D"` as in the older Network Security Group flow log version 1 format). The `connectivity-diagnostics` skill already accounts for this.
- Traffic Analytics denied flow data lags real-time by the aggregation interval. Use NSG flow logs in storage for second-by-second forensics; use Traffic Analytics for pattern analysis over minutes to hours.
- The `titleContains: "Denied VNet flow"` condition in the `network-denied-flows-review` response plan routes denied-flow spike alerts to the network analyst. The sibling `web-tier-nginx` plan uses `titleContains: nginx` to capture nginx failures — each filter owns a distinct keyword so alerts never overlap.

## Hints and notes

> Hidden until you click. Expand a section only when you want it.

<details>
<summary><strong>Background</strong></summary>

- Draw the 5-tuple: app tier `10.20.0.0/16` → DB `10.30.2.10:5432/TCP` blocked by `Demo-Deny-App-To-Db-5432`.
- Autonomous routing path: `alert-denied-flow-spike` → `network-denied-flows-review` → `network-traffic-analyst`.
- Critical: in `NTANetAnalytics`, `FlowStatus` is the full word **`Denied`**, not `D`.
- Traffic Analytics lags: it is pattern analytics, not packet capture.

</details>

<details>
<summary><strong>Expected Output</strong></summary>

- Alert appears in roughly 10–15 minutes (Traffic Analytics aggregation interval is 10 minutes; allow one full cycle before concluding the alert is delayed).
- Agent queries `NTANetAnalytics`, identifies source/destination/port/protocol, and names `Demo-Deny-App-To-Db-5432`.
- Agent runs `az network nsg rule delete` and rechecks that denied flows clear.
- You can explain why the table/value choice matters for KQL accuracy.

</details>

<details>
<summary><strong>Common Issues and Hints</strong></summary>

- **Symptom:** No denied records yet. **Fix:** wait for Traffic Analytics processing; if needed, retry closer to 7–10 minutes.
- **Symptom:** You filter on `FlowStatus == "D"`. **Fix:** use `Denied` or denied counters.
- **Symptom:** Agent finds a deny but not the rule name. **Fix:** ask it to correlate `AclRule`/NSG rule output, not stop at the tuple.
- **Symptom:** Application recovered but denied rows still appear in 24h window. **Fix:** narrow the time window and distinguish historical evidence from current state.
- **Symptom:** The response plan starts the agent autonomously and it identifies the blocking rule, but `az network nsg rule delete` is refused with an authorization or permission error. **Fix:** remember that Autonomous mode removes the approval gate but does not grant Azure RBAC access; verify the Terraform-managed Contributor assignment covers the shared workload resource group, where `nsg-data` owns the injected rule.

</details>

<details>
<summary><strong>Debrief Discussion Guide</strong></summary>

- Why are network drops harder than app errors to diagnose manually? → Little or no application-layer evidence.
- Why is Traffic Analytics enough here even though it is delayed? → The incident is pattern-based, not millisecond-sensitive.
- What does the full-word `Denied` detail teach? → Schema fidelity matters; old mental models break queries.

</details>

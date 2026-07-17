[< Previous Challenge](./Challenge-08.md) — **[Home](../README.md)** — [Next Challenge >](./Challenge-10.md)

# Challenge 09 — Autonomous Network Security Remediation

## Introduction

A misconfigured NSG deny rule is blocking database traffic. Application logs show connection timeouts. Users are getting errors. The network team is asleep.

In this challenge, you'll inject a deny rule that blocks traffic from the app subnet to the database port, wait for the **Azure SRE Agent to autonomously detect, investigate, and remediate** it using VNet Flow Log evidence — and then reflect on what it means to give an AI agent the keys to your network security rules.

This is **Scenario S6: NSG Rule Block** — a fully **autonomous** scenario.

## Description

### Before you start

Verify the network is healthy:

```bash
Student/Resources/scenarios/scripts/generate-baseline-traffic.sh
Student/Resources/scenarios/scripts/run-kql.sh top-talkers
```

### Trigger the fault

```bash
Student/Resources/scenarios/scripts/trigger-nsg-block.sh
```

This adds a temporary NSG deny rule (`Demo-Deny-App-To-Db-5432`) to the data NSG, blocking TCP port 5432 (PostgreSQL) from the app subnet.

### Observe the autonomous response

1. Open the **SRE Agent portal → Incident Response**
2. Wait for the Azure Monitor alert (denied-flow alert from VNet Flow Logs) — allow **5–10 minutes** for flows to be processed and the alert to fire
3. The `network-observability-review` incident filter routes the incident to `network-traffic-analyst`
4. Watch the agent:
   - Query `NTANetAnalytics` for denied flows matching the symptom
   - Identify the specific NSG rule responsible
   - Use `RunAzCliWriteCommands` to delete the deny rule
5. Verify connectivity is restored

### Verify remediation

```bash
Student/Resources/scenarios/scripts/run-kql.sh denied
```

The denied flows should disappear after the rule is removed.

### Restore (if needed)

If the agent did not complete the remediation:

```bash
Student/Resources/scenarios/scripts/restore-nsg-block.sh
```

## Success Criteria

To complete this challenge, demonstrate:

1. The Azure Monitor denied-flow alert fired and the incident appeared in the portal
2. The incident was routed to `network-traffic-analyst` (not an app-focused subagent)
3. The agent's tool call log shows KQL queries against `NTANetAnalytics` or similar flow log tables
4. The agent identified and **deleted** the `Demo-Deny-App-To-Db-5432` rule using an `az network nsg rule delete` command
5. Post-remediation KQL shows no denied flows on port 5432
6. **Explain to your coach** — this scenario is autonomous AND write-capable on network security rules. What safeguards would you want in a production environment before deploying an agent with this capability? What audit trail does the agent create?

## Learning Resources

- [NSG flow logs](https://learn.microsoft.com/en-us/azure/network-watcher/nsg-flow-logs-overview)
- [VNet Flow Logs — denied flows](https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview#nsg-flow-logs-retirement)
- [Traffic Analytics schema — NTANetAnalytics](https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema)
- [az network nsg rule](https://learn.microsoft.com/en-us/cli/azure/network/nsg/rule)
- [Azure SRE Agent — autonomous mode](https://learn.microsoft.com/en-us/azure/sre-agent/agent-modes)

## Tips

- VNet Flow Logs have a **processing delay** before they appear in Traffic Analytics and trigger alerts. If the alert doesn't fire after 10 minutes, use the portal chat to manually trigger the investigation: "Check for denied flows to port 5432 in the last 30 minutes and fix any NSG rules causing them."
- The key KQL evidence: `NTANetAnalytics | where FlowStatus == "D" and DestPort == 5432` — share this with attendees if they want to understand what the agent is looking at.
- Compare this challenge with Challenge 08: both involve the network, but S5 is interactive and exploratory while S6 is autonomous and corrective. This contrast is one of the most valuable discussion points in the hack.
- After restore, re-run `generate-baseline-traffic.sh` to confirm the DB flows are allowed again.

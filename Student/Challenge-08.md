[< Previous Challenge](./Challenge-07.md) — **[Home](../README.md)** — [Next Challenge >](./Challenge-09.md)

# Challenge 05 — Network Diagnostics: Asymmetric Routing

## Introduction

Network routing issues are some of the hardest problems to diagnose. Asymmetric routing — where traffic flows one way but return traffic takes a different path — breaks TCP connections silently and generates confusing, contradictory logs. Traditionally, diagnosing this requires manually correlating firewall logs, route tables, and network flow data across multiple tools.

**VNet Flow Logs** and **Traffic Analytics** give the SRE Agent a continuous, structured view of every network flow in the lab. In this challenge, you'll inject an asymmetric routing fault by adding a blackhole UDR (User-Defined Route) and then **interactively investigate** it with the agent in the portal — guiding the conversation and interpreting the evidence together.

This is **Scenario S5: Asymmetric Routing / UDR** — an **interactive** scenario where *you* drive the investigation.

## Description

### Step 1 — Generate baseline traffic

Traffic Analytics needs a flow baseline to show meaningful data. Run:

```bash
Student/Resources/scenarios/scripts/generate-baseline-traffic.sh
```

Wait **2–3 minutes** for flows to appear in Traffic Analytics (flow log processing has a built-in delay).

### Step 2 — Inject the routing fault

```bash
Student/Resources/scenarios/scripts/trigger-udr-asymmetry.sh
```

This adds a more-specific route (`10.20.1.0/24 → Next hop: None`) to the app route table, creating a blackhole for return traffic from the web subnet back to the client subnet.

### Step 3 — Investigate with the agent (interactive)

Open the **SRE Agent portal chat** and start an investigation. Use prompts like:

> "Analyze the VNet Flow Logs for asymmetric routing between the client VM (10.20.1.10) and the web VMs (10.20.2.10, 10.20.2.11). What do you observe?"

> "Check the Traffic Analytics data for the last 30 minutes. Are there any flows with missing return traffic or unusual byte ratios?"

> "Look at the route tables for the app and data subnets. Is there a UDR that could explain asymmetric traffic patterns?"

Guide the conversation — the agent has access to the `udr-asymmetry-investigation` skill and the `traffic-analytics-kql-analysis` skill. Ask follow-up questions based on what the agent reports.

### Step 4 — Restore

```bash
Student/Resources/scenarios/scripts/restore-udr-asymmetry.sh
```

Verify connectivity is restored by re-running the baseline traffic script and confirming flows appear in both directions.

## Success Criteria

To complete this challenge, demonstrate:

1. The baseline traffic script generated observable flows in Traffic Analytics
2. After the fault injection, you ran at least 2 investigation prompts in the portal and received substantive responses
3. The agent identified at least one of:
   - Missing return flows in Traffic Analytics
   - A suspicious route in the route table
   - Asymmetric byte ratios between forward and return traffic
4. You can explain (in your own words) what the agent found and why it indicates asymmetric routing
5. `restore-udr-asymmetry.sh` restored normal routing and flows
6. **Explain to your coach** — why is this scenario **interactive** (you drive it) while Scenarios S1, S4, and S6 are **autonomous** (the agent drives it)? What makes a network investigation better suited to interactive vs. autonomous mode?

## Learning Resources

- [VNet Flow Logs overview](https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview)
- [Traffic Analytics](https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics)
- [User-Defined Routes](https://learn.microsoft.com/en-us/azure/virtual-network/virtual-networks-udr-overview)
- [Azure Firewall and asymmetric routing](https://learn.microsoft.com/en-us/azure/firewall/firewall-faq#how-do-i-work-with-asymmetric-routing)

## Tips

- Traffic Analytics data has a **processing delay of up to 10 minutes**. If the agent says "no data," wait and retry.
- The key evidence to look for: **`IsFlowCapturedAtUDRHop`** in the flow records, and flows where `BytesSentD2S > 0` but `BytesSentS2D = 0` (traffic in one direction only).
- If the investigation isn't surfacing useful data, ask the agent to run a specific KQL query: `"Run the denied-flow KQL query from the knowledge base"`.
- You can also use `Student/Resources/scenarios/scripts/run-kql.sh denied` directly in your terminal to see the raw flow data.

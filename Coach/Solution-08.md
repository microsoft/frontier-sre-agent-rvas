[< Previous Solution](./Solution-07.md) | **[Home](./README.md)** | [Next Solution >](./Solution-09.md)

# Coach Guide — Challenge 05: Network Diagnostics (Interactive Mode)

## Purpose

This challenge teaches two things simultaneously:
1. **VNet Flow Logs + Traffic Analytics** as an advanced Azure network observability capability
2. The **interactive agent modality** — instead of waiting for an autonomous response, the student drives a diagnostic conversation with `network-traffic-analyst`

The UDR asymmetry scenario is technically rich: a more-specific route causes outbound packets to traverse a different path than inbound packets, creating a "flows sent, no flows received" pattern in Traffic Analytics that is the network equivalent of a one-way mirror.

Expected time: **25–35 minutes** including flow log propagation (~10 min delay).

## Mini-Lecture (10 min before challenge)

Cover:
- **VNet Flow Logs**: NSG flow logs v2 — captures 5-tuple (src IP, dst IP, src port, dst port, protocol) + direction + bytes + packets
- **Traffic Analytics**: processes VNet Flow Logs every 10 minutes into a Log Analytics schema (`NTANetAnalytics`, `NTAIpDetails`)
- **UDR asymmetry**: outbound from client VM takes the /24 blackhole route → drops; inbound from server arrives normally. This creates asymmetric byte ratios in flow data
- The key KQL evidence fields: `IsFlowCapturedAtUDRHop` (true when flow was dropped at a UDR), `FlowStatus` (A = active, E = ended, D = denied), `BytesSentD → A` vs `BytesSentA → D` ratio
- Why interactive: the student should ask progressively more specific questions, practicing the diagnostic conversation pattern

## Expected Agent Behavior (Driven by Student Prompts)

**Prompt 1:** "Are there any network connectivity issues between client and web tier VMs right now?"
→ Agent runs `NTANetAnalytics | where ... | order by TimeGenerated desc | take 100` and reports general flow state

**Prompt 2:** "Show me flows from vm-client to vm-web-1 in the last 30 minutes"
→ Agent uses `udr-asymmetry-investigation` skill; queries for flows between the two subnets

**Prompt 3:** "Are there any UDR-related drops?"
→ Agent finds `IsFlowCapturedAtUDRHop == true` or `FlowStatus == "D"` for the affected routes; reports the next-hop IP discrepancy

**Prompt 4:** "What route table change could explain this?"
→ Agent queries `az network route-table route list` and identifies the injected /24 route to `None`

**Prompt 5 (optional):** "Remove the bad route"
→ Agent uses `RunAzCliWriteCommands` to delete the route (if student wants to test autonomous remediation)

## VNet Flow Log / Traffic Analytics Timing

⚠️ **Critical for timing:** Traffic Analytics has a ~10 minute processing lag. If the student triggers the UDR fault and immediately asks the agent, the flow data won't show the fault yet.

**Coach action:**
1. Have `generate-baseline-traffic.sh` running **before** the challenge starts (generates traffic so there are flows to analyze)
2. Trigger `trigger-udr-asymmetry.sh` at least 10 minutes before directing students to query the agent
3. Tell students: "Wait 10 minutes after injecting the fault before querying"

## Common Issues and Hints

### Agent says "no flow data available" or returns empty results
- Traffic Analytics may not be fully enabled or workspace is wrong
- Check: `az monitor diagnostic-settings list --resource <vnet-id>` — should show flow logs sending to the Log Analytics workspace
- Check: portal → Log Analytics Workspace → Tables → `NTANetAnalytics` — if missing, Traffic Analytics isn't processing yet
- Coach fallback: direct the student to query Log Analytics manually to confirm data exists, then describe what they see to the agent

### Agent identifies the issue but won't remove the route
- By design: the student challenge says to investigate interactively and propose remediation — actual fix is optional
- If the student wants to test the write path, they can explicitly ask the agent to delete the route

### Agent confuses subnets or VMs (wrong IPs)
- The agent uses Azure CLI to enumerate VMs + NICs + IPs. If the query returns multiple subscriptions, it may pick wrong resources
- Verify: `.sre-agent-apply-all.sh` exports the correct SUB, RG, and AGENT before running the subagent config

## KQL Reference for Coach

```kusto
// Show asymmetric flows (UDR drop)
NTANetAnalytics
| where TimeGenerated > ago(1h)
| where IsFlowCapturedAtUDRHop == true
| project TimeGenerated, SrcIp, DestIp, FlowStatus, BytesSentD_A, BytesSentA_D

// Show all denied flows to web tier
NTANetAnalytics
| where TimeGenerated > ago(1h)
| where FlowStatus == "D"
| where DestSubnet contains "web"
| project TimeGenerated, SrcIp, DestIp, DestPort, FlowStatus
```

## Debrief Discussion Guide (10 min)

1. **What was the key evidence?** — `IsFlowCapturedAtUDRHop == true` + asymmetric byte counts (bytes sent in one direction, none in the other)
2. **How did the interactive mode differ from the autonomous mode in S1?** — The student drove the conversation; the agent surfaced evidence rather than deciding autonomously
3. **When is interactive preferable?** — When the problem domain requires human judgment (network policy decisions, security posture changes), when you want an audit trail of reasoning, when the blast radius of an autonomous fix is high
4. **What would you need to make this autonomous?** — A rule: "if UDR route is injected with NextHopType=None, auto-delete within 5 minutes"

## Success Criteria Notes

- The student must identify `IsFlowCapturedAtUDRHop` or equivalent asymmetry evidence
- Accept the conversation transcript + route identification as the primary artifact
- The fix (route deletion) is bonus credit — not required for challenge completion

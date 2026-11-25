---
title: Routing Failure Investigation
summary: Introduce an asymmetric routing black hole where return packets never arrive. Work with the network-traffic-analyst over effective routes and next-hop analysis to find and fix the return path.
phase: Autonomous
group: Autonomous incident response
tags:
- UDR
- Effective Routes
- Next Hop Analysis
highlight: false
---

# Challenge 13 — Routing Failure Investigation

> **Application focus:** Infrastructure/platform only

> **Capability**: UDRs · Effective Routes · Next Hop Analysis

## Purpose

- Use effective routes and next hops to find the UDR that breaks the return path, and explain why traffic that succeeds one way can still be an outage.
- Compare the lab's Autonomous remediation with cases where production route changes should require Review.
- Expected time: 25–30 minutes.

## Introduction

Packets from the app tier reach the database through the firewall, but replies do not return. Trace the return path to diagnose this asymmetric routing failure.

There is no dedicated alert for this challenge. Invoke the `network-traffic-analyst` specialist directly from chat and reason over effective routes and next-hop analysis to correct the misrouted return path. This subagent always runs in **Autonomous** mode. Even when invoked from chat, it investigates and applies the fix itself rather than waiting for your approval (its system prompt states it runs fully autonomously, and the block-unsafe-remediation hook is disabled for this demo lab; see `labs/01-azure-operations/resources/azure-sre-agent-config/subagents/network-traffic-analyst.yaml`).

## Description

### Before you start

Verify the Grubify lab network is clean:

```bash
make validate
make baseline-traffic
```

### Step 1 — Inject the routing fault

```bash
make trigger-udr
```

This adds a User-Defined Route `Demo-Break-Return-To-App-Client` (`10.20.1.0/24 → next hop: None`) to the data-spoke route table. The forward path remains intact; return traffic from the database subnet to the app tier is now black-holed.

### Step 2 — Trigger the investigation

There is no automated alert for this scenario. Invoke the network specialist directly:

```text
/agent network-traffic-analyst

The application tier is unable to reliably communicate with the database. Connectivity appears to succeed in one direction but responses are not arriving. Investigate the network path end-to-end, identify the root cause, and propose a safe fix.
```

### Step 3 — Follow the evidence

Watch the agent:

1. Run `az network nic show-effective-route-table` on the database VM NIC to read effective routes
2. Run `az network watcher show-next-hop` to verify the next hop for the return path
3. Query `NTANetAnalytics` for asymmetric or incomplete flows
4. Identify the problematic route (`Demo-Break-Return-To-App-Client`, next hop `None`)
5. Spot the deliberate red herring: `vm-nva` has IP forwarding enabled, but no route points to it

### Step 4 — Governance mode discussion

`network-traffic-analyst` is hardcoded to **Autonomous** mode in its own configuration. Its system
prompt says it acts "without waiting for approval," and the block-unsafe-remediation hook is
disabled for this subagent. Confirm this:

```text
Before you make any changes, would you propose the route correction and wait for my approval, or apply it yourself?
```

The agent should explain that it runs autonomously here and will apply and verify the fix itself,
not merely propose it. Unlike the `network-denied-flows-review` incident
filter (also Autonomous), no Review-mode alternative is wired up anywhere in this lab.
Switching this subagent to Review mode would require re-enabling the block-unsafe-remediation hook
or gating it behind an incident filter's `agentMode: Review` setting.

### Step 5 — Restore (if needed)

```bash
make restore-udr
```

## Success Criteria

- [ ] The agent identifies `Demo-Break-Return-To-App-Client` as the blocking route with next hop `None`
- [ ] The agent correctly dismisses `vm-nva` as a red herring (IP forwarding enabled, but no route points to it)
- [ ] The agent produces a clear explanation of *why* the forward path works but the return path doesn't
- [ ] You confirm the subagent's Autonomous mode is hardcoded and can explain what it would take to gate it behind Review mode instead
- [ ] The agent verifies that connectivity is restored after the route correction
- [ ] **Explain in your own words** (two or three written sentences) — a system route and a UDR cover the same prefix. Which one wins, and how did that precedence cause the failure in this challenge?

## Learning Resources

- [Azure Virtual Network — routing overview](https://learn.microsoft.com/en-us/azure/virtual-network/virtual-networks-udr-overview)
- [Azure Network Watcher — effective routes](https://learn.microsoft.com/en-us/azure/network-watcher/effective-routes-overview)
- [Azure Network Watcher — next hop](https://learn.microsoft.com/en-us/azure/network-watcher/network-watcher-next-hop-overview)
- [Traffic Analytics overview](https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics)

## Tips

- The red herring (`vm-nva` with IP forwarding) is there to test whether the agent reasons from evidence rather than assumptions. A route must *point* to the NVA for it to be in the path — IP forwarding alone is not enough.
- Asymmetric routing is visible in `NTANetAnalytics` as flows where outbound traffic appears but the corresponding return flow is absent or shows as `Incomplete`.
- Review mode is valuable for route changes in production: a human confirms the destination prefix and next hop before the UDR is modified. This lab's `network-traffic-analyst` deliberately skips that gate for demo speed. Production subagents should not disable the block-unsafe-remediation hook this way.

## Hints and notes

> Hidden until you click. Expand a section only when you want it.

<details>
<summary><strong>Background</strong></summary>

- Asymmetry: forward path from app to DB works; return path from DB to app is black-holed by `Demo-Break-Return-To-App-Client` (`10.20.1.0/24 -> None`).
- The red herring: `vm-nva` has IP forwarding enabled, but no route points to it.
- Decisive tools: `az network nic show-effective-route-table` and `az network watcher show-next-hop`. A UDR blackhole can leave no `NTANetAnalytics` row.
- Governance comparison: the configured custom agent is Autonomous; Review must be set on a trigger/task or governed workflow, not requested as an in-chat mode switch.

</details>

<details>
<summary><strong>Expected Output</strong></summary>

- You invoke `/agent network-traffic-analyst` directly.
- Investigation identifies the more-specific UDR to `None` as the root cause.
- You can explain why the forward path works while the return path fails.
- Agent applies the route correction and verifies the active effective route plus Network Watcher next hop.

</details>

<details>
<summary><strong>Common Issues and Hints</strong></summary>

- **Symptom:** You fixate on the NVA VM. **Fix:** ask “what route actually points there?” If none, it is not in the path.
- **Symptom:** You check only source-side routes. **Fix:** inspect the destination/return path explicitly.
- **Symptom:** You expect a denied-flow row for the blackhole. **Fix:** the UDR can drop traffic before NSG flow evidence; insist on effective route and next-hop evidence.
- **Symptom:** After remediation, stale asymmetry still appears historically. **Fix:** use a tighter time window for verification.
- **Symptom:** Agent identifies the bad UDR but remediation is refused with a permission error. **Fix:** verify the Terraform-managed Contributor assignment covers the shared workload resource group.

</details>

<details>
<summary><strong>Debrief Discussion Guide</strong></summary>

- Which route wins when a system route and a UDR both match? → The UDR always takes priority over system routes; specificity is a tiebreaker only when two UDRs overlap.
- Why is Review mode valuable for route changes? → Routing mistakes can expand blast radius quickly.
- What made the agent effective here? → It combined point-in-time route truth with historical flow evidence.

</details>

[< Previous Challenge](./Challenge-12.md) — **[Home](../README.md)** — [Next Challenge >](./Challenge-14.md)

# Challenge 13 — Routing Failure Investigation

> **Capability**: UDRs · Effective Routes · Next Hop Analysis

## Introduction

The forward path is perfectly healthy — packets leave the app tier, traverse the firewall, and arrive at the database. The replies never make it back. This **asymmetric routing black hole** is one of the hardest infrastructure failures to diagnose: everything looks fine until you trace the return path.

There is no dedicated alert for this challenge. You'll invoke the `network-traffic-analyst` specialist directly from chat and reason over effective routes and next-hop analysis to correct the misrouted return path. This subagent always runs in **Autonomous** mode — even invoked from chat, it investigates and applies the fix itself rather than waiting for your approval (its system prompt states it runs fully autonomously and the block-unsafe-remediation hook is disabled for this demo lab; see `Student/Resources/azure-sre-agent-config/subagents/network-traffic-analyst.yaml`).

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

`network-traffic-analyst` is hardcoded to **Autonomous** mode in its own configuration — its system
prompt states it acts "without waiting for approval," and the block-unsafe-remediation hook is
disabled for this subagent. Confirm this for yourself:

```text
Before you make any changes, would you propose the route correction and wait for my approval, or apply it yourself?
```

The agent should explain that it runs autonomously here and will apply and verify the fix itself,
not merely propose it. Discuss with your coach: unlike the `network-observability-review` incident
filter (also Autonomous), there is no Review-mode alternative wired up anywhere in this lab —
switching this subagent to Review mode would require re-enabling the block-unsafe-remediation hook
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
- [ ] **Explain to your coach** — what is User-Defined Route (UDR) precedence? If a system route and a UDR both cover the same prefix, which one wins?

## Learning Resources

- [Azure Virtual Network — routing overview](https://learn.microsoft.com/en-us/azure/virtual-network/virtual-networks-udr-overview)
- [Azure Network Watcher — effective routes](https://learn.microsoft.com/en-us/azure/network-watcher/effective-routes-overview)
- [Azure Network Watcher — next hop](https://learn.microsoft.com/en-us/azure/network-watcher/network-watcher-next-hop-overview)
- [Traffic Analytics overview](https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics)

## Tips

- The red herring (`vm-nva` with IP forwarding) is there to test whether the agent reasons from evidence rather than assumptions. A route must *point* to the NVA for it to be in the path — IP forwarding alone is not enough.
- Asymmetric routing is visible in `NTANetAnalytics` as flows where outbound traffic appears but the corresponding return flow is absent or shows as `Incomplete`.
- Review mode is valuable for route changes in production: a human confirms the destination prefix and next hop before the UDR is modified. This lab's `network-traffic-analyst` deliberately skips that gate to maximize demo speed — production subagents should not disable the block-unsafe-remediation hook this way.

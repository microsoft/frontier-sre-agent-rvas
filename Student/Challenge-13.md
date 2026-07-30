[< Previous Challenge](./Challenge-12.md) — **[Home](../README.md)** — [Next Challenge >](./Challenge-14.md)

# Challenge 13 — Routing Failure Investigation

> **Capability**: UDRs · Effective Routes · Next Hop Analysis

## Introduction

The forward path is perfectly healthy — packets leave the app tier, traverse the firewall, and arrive at the database. The replies never make it back. This **asymmetric routing black hole** is one of the hardest infrastructure failures to diagnose: everything looks fine until you trace the return path.

There is no dedicated alert for this challenge. You'll invoke the `network-traffic-analyst` specialist directly from chat, reason over effective routes and next-hop analysis, and correct the misrouted return path — with the option to run in **Review mode** (agent proposes, you approve) or **Autonomous mode** (agent applies and verifies).

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
5. Spot the deliberate red herring: `vm-vflta-nva` has IP forwarding enabled, but no route points to it

### Step 4 — Governance mode comparison

Before the agent applies the fix, try **Review mode** first:

```text
Before you make any changes, switch to Review mode and propose the route correction. Wait for my approval.
```

Review the proposed change, approve it, and observe the agent apply and verify the fix. Then note what would have happened differently in Autonomous mode.

### Step 5 — Restore (if needed)

```bash
make restore-udr
```

## Success Criteria

- [ ] The agent identifies `Demo-Break-Return-To-App-Client` as the blocking route with next hop `None`
- [ ] The agent correctly dismisses `vm-vflta-nva` as a red herring (IP forwarding enabled, but no route points to it)
- [ ] The agent produces a clear explanation of *why* the forward path works but the return path doesn't
- [ ] You experience both Review and Autonomous modes and can explain the governance difference
- [ ] The agent verifies that connectivity is restored after the route correction
- [ ] **Explain to your coach** — what is User-Defined Route (UDR) precedence? If a system route and a UDR both cover the same prefix, which one wins?

## Learning Resources

- [Azure Virtual Network — routing overview](https://learn.microsoft.com/en-us/azure/virtual-network/virtual-networks-udr-overview)
- [Azure Network Watcher — effective routes](https://learn.microsoft.com/en-us/azure/network-watcher/effective-routes-overview)
- [Azure Network Watcher — next hop](https://learn.microsoft.com/en-us/azure/network-watcher/network-watcher-next-hop-overview)
- [Traffic Analytics overview](https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics)

## Tips

- The red herring (`vm-vflta-nva` with IP forwarding) is there to test whether the agent reasons from evidence rather than assumptions. A route must *point* to the NVA for it to be in the path — IP forwarding alone is not enough.
- Asymmetric routing is visible in `NTANetAnalytics` as flows where outbound traffic appears but the corresponding return flow is absent or shows as `Incomplete`.
- Review mode is especially valuable for route changes in production: a human confirms the destination prefix and next hop before the UDR is modified. Use it whenever the blast radius of a routing change is unclear.

[< Previous Challenge](./Challenge-10.md) — **[Home](./README.md)** — [Next Challenge >](./Challenge-12.md)

# Challenge 11 — Investigate a Routing Black Hole

> **Incident capability exercised in this challenge**: Path Diagnosis · Hypothesis Rejection · Bidirectional Recovery

## Introduction

The dependency connection still fails after security rules are shown to allow it. Diagnose the lab-only incident by proving the forward and return paths separately, then validate both connectivity and application recovery.

## Description

> **Customer demo script:** Run `pwsh -File '.\SRE SignalOps\Scripts\Challenge-11.ps1' -SubscriptionId '<approved-subscription-id>' -ResourceGroup '<sandbox-rg>' -NicName '<nic>'`; add VM and IP parameters for next-hop evidence. See the [presenter runbook](../Scripts/README.md).

This mission uses the same approved VM-to-VM network sandbox or [evidence pack](./README.md#evidence-pack-and-network-sandbox-contract) as Challenge 10, not an assumed Grubify downstream VM. Introduce or receive a route-table condition that creates an invalid or asymmetric return path. Keep the event labeled `EXERCISE` and preserve the pre-fault route state for restoration.

Ask the network specialist to produce:

- source and destination route decisions;
- longest-prefix and route-source reasoning;
- effective next hop in both directions;
- Network Watcher next-hop results;
- evidence that distinguishes routing from DNS, NSG, and application failure;
- the narrowest reversible route correction.

Use PowerShell for independent checks:

```powershell
$ResourceGroup = '<network-sandbox-rg>'
$NicName = '<affected-nic>'
$SubscriptionId = '<approved-subscription-id>'
az network nic show-effective-route-table --subscription $SubscriptionId --resource-group $ResourceGroup --name $NicName -o table

az network watcher show-next-hop `
  --subscription $SubscriptionId `
  --resource-group $ResourceGroup `
  --vm '<source-vm>' `
  --source-ip '<source-ip>' `
  --dest-ip '<destination-ip>' `
  -o jsonc
```

Repeat the wrapper for the destination VM/NIC with source and destination IPs
reversed to obtain return-path evidence. The wrapper creates no route fault and
performs no recovery. If the specialist is unavailable, label manual analysis.
Validate both directions after an approved correction. A successful forward
test alone is not recovery evidence.

## Success Criteria

In evidence-pack mode, cite supplied bidirectional before/fault/after evidence
and label all changes and recovery as supplied or simulated. Missing artifacts
remain unproven rather than being treated as a successful live run.

- [ ] Forward and return route decisions are documented independently
- [ ] Effective route and next-hop evidence identify the black hole
- [ ] DNS, NSG, and application hypotheses are explicitly tested and rejected or retained with evidence
- [ ] Recovery proves bidirectional connectivity and application behavior
- [ ] **Explain to your coach** — why can a route table look valid in the portal while the effective path is still wrong?

## Learning Resources

- [Diagnose routing problems](https://learn.microsoft.com/en-us/azure/virtual-network/diagnose-network-routing-problem)
- [Network Watcher next hop](https://learn.microsoft.com/en-us/azure/network-watcher/next-hop-overview)
- [Azure virtual network routing](https://learn.microsoft.com/en-us/azure/virtual-network/virtual-networks-udr-overview)

## Tips

- Check effective routes, not only route-table definitions.
- Prove the return path.
- Restore every injected route change before continuing.

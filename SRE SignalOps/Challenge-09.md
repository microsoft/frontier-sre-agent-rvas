[< Previous Challenge](./Challenge-08.md) — **[Home](./README.md)** — [Next Challenge >](./Challenge-10.md)

# Challenge 09 — Investigate a Routing Black Hole

> **Capabilities added in this challenge**: Effective Routes · Next-Hop Analysis · Asymmetric Path Detection

## Introduction

Security rules can allow every packet while routing still prevents a conversation. Diagnose a lab-only black hole by proving the forward and return paths separately.

## Description

> **Customer demo script:** Run `pwsh -File '.\SRE SignalOps\Scripts\Challenge-09.ps1' -ResourceGroup '<sandbox-rg>' -NicName '<nic>'`; add VM and IP parameters for next-hop evidence. See the [presenter runbook](./Scripts/README.md).

This mission uses the same coach-provided network sandbox or incident snapshot as Challenge 08. Introduce or receive a route-table condition that creates an invalid or asymmetric return path.

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
az network nic show-effective-route-table --resource-group $ResourceGroup --name $NicName -o table

az network watcher show-next-hop `
  --resource-group $ResourceGroup `
  --vm '<source-vm>' `
  --source-ip '<source-ip>' `
  --dest-ip '<destination-ip>' `
  -o jsonc
```

Validate both directions after an approved correction. A successful forward test alone is not recovery evidence.

## Success Criteria

- [ ] Forward and return route decisions are documented independently
- [ ] Effective route and next-hop evidence identify the black hole
- [ ] DNS, NSG, and application hypotheses are explicitly tested
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

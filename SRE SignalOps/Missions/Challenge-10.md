[< Previous Challenge](./Challenge-09.md) — **[Home](./README.md)** — [Next Challenge >](./Challenge-11.md)

# Challenge 10 — Investigate a Network Security Failure

> **Incident capability exercised in this challenge**: Security-Rule Diagnosis · Blast-Radius Control · Safe Recovery

## Introduction

An approved VM-to-VM sandbox dependency fails while other paths remain healthy. Investigate whether an effective NSG decision explains the timeout, reject competing causes, and recover only the affected flow without weakening unrelated protections.

## Description

> **Customer demo script:** Run `pwsh -File '.\SRE SignalOps\Scripts\Challenge-10.ps1' -SubscriptionId '<approved-subscription-id>' -ResourceGroup '<sandbox-rg>' -NicName '<nic>'`. See the [presenter runbook](../Scripts/README.md).

This mission requires an existing hub-spoke network sandbox with Network Watcher and flow telemetry. The Bicep Grubify core does not create that network. The full Terraform network is eligible only after a coach validates the actual VM-to-VM path; it is not a deployed Grubify dependency. Use the [sandbox/evidence-pack contract](./README.md#evidence-pack-and-network-sandbox-contract), not assumed Container Apps flow logs. The wrapper reads configuration only; it creates no fault and proves no recovery. If the network specialist is unavailable, perform manual read-only analysis and label it accordingly.

Create or receive a known NSG deny condition on one dependency edge from the map. Keep the incident labeled `EXERCISE` unless a genuine lab alert exists. Ask the SRE Agent to correlate:

- source and destination addresses, ports, and direction;
- NSG association and effective security rules;
- matching allow and deny priorities;
- flow-log or Traffic Analytics evidence;
- affected and unaffected dependencies;
- minimum safe remediation and rollback.

Use PowerShell to inspect effective rules on the selected NIC:

```powershell
$ResourceGroup = '<network-sandbox-rg>'
$NicName = '<affected-nic>'
$SubscriptionId = '<approved-subscription-id>'
az network nic list-effective-nsg --subscription $SubscriptionId --resource-group $ResourceGroup --name $NicName -o jsonc
```

Do not remove a broad deny rule. Propose the smallest scoped correction and require approval before any write.

## Success Criteria

For evidence-pack mode, cite supplied before/fault/after records for each
criterion; do not claim a live rule change or recovery. Missing artifacts leave
the associated criterion unproven.

- [ ] The exact effective rule and priority are identified
- [ ] Flow evidence agrees with the rule evaluation
- [ ] Blast radius includes affected and unaffected paths
- [ ] The SRE Agent rejects at least one plausible non-NSG cause with evidence
- [ ] Remediation is minimal, approval-gated, reversible, and followed by recovery and regression checks
- [ ] **Explain to your coach** — why is deleting the blocking rule usually less safe than introducing a narrowly scoped higher-priority rule?

## Learning Resources

- [Diagnose NSG traffic filtering](https://learn.microsoft.com/en-us/azure/virtual-network/diagnose-network-traffic-filter-problem)
- [Effective security rules](https://learn.microsoft.com/en-us/azure/virtual-network/network-security-group-how-it-works)
- [Virtual network flow logs](https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview)

## Tips

- Use only a disposable lab sandbox for fault injection.
- Effective rules matter more than the rule you expected to apply.
- Restore the sandbox before leaving the mission.

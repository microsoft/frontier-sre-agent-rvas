[< Previous Challenge](./Challenge-08.md) — **[Home](./README.md)** — [Next Challenge >](./Challenge-10.md)

# Challenge 09 — Investigate a Network Security Failure

> **Incident capability exercised in this challenge**: Security-Rule Diagnosis · Blast-Radius Control · Safe Recovery

## Introduction

Grubify cannot reach one required dependency, but other paths remain healthy. Investigate whether an effective NSG decision explains the timeout, reject competing causes, and recover only the affected flow without weakening unrelated protections.

## Description

> **Customer demo script:** Run `pwsh -File '.\SRE SignalOps\Scripts\Challenge-09.ps1' -ResourceGroup '<sandbox-rg>' -NicName '<nic>'`. See the [presenter runbook](./Scripts/README.md).

This mission requires an existing hub-spoke network sandbox with Network Watcher and flow telemetry. The `azd` Grubify deployment from Challenge 00 does not create that network. Use a coach-provided sandbox or skip fault injection and analyze a supplied incident snapshot.

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
az network nic list-effective-nsg --resource-group $ResourceGroup --name $NicName -o jsonc
```

Do not remove a broad deny rule. Propose the smallest scoped correction and require approval before any write.

## Success Criteria

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

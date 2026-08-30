[< Previous Challenge](./Challenge-04.md) — **[Home](./README.md)** — [Next Challenge >](./Challenge-06.md)

# Challenge 05 — Discover Specialist Agents

> **Capabilities added in this challenge**: Subagent Inventory · Capability Routing · Least Privilege

## Introduction

Specialists should narrow authority, not multiply ambiguity. Discover the configured subagents and prove that each has a distinct operational contract.

## Description

> **Customer demo script:** Run `pwsh -File '.\SRE SignalOps\Scripts\Challenge-05.ps1'` to inventory specialist agents and print routing prompts. See the [presenter runbook](./Scripts/README.md).

Have the primary agent produce a specialist roster with identity, purpose, trigger language, data sources, tools, write permissions, approval boundary, and handoff conditions. Require it to identify overlaps and capability gaps.

Use the repository manifests as a second source of truth:

```powershell
Get-ChildItem '.\Student\Resources\azure-sre-agent-config\subagents' -Filter '*.yaml' |
  ForEach-Object {
    [pscustomobject]@{ Name = $_.BaseName; Updated = $_.LastWriteTimeUtc; Bytes = $_.Length }
  } | Format-Table
```

Test routing with three prompts: an application error, a denied network flow, and a cost anomaly. Record which specialist is selected and why. A good result routes by evidence domain and action boundary rather than by keyword alone.

## Success Criteria

- [ ] Every specialist has a distinct operational contract
- [ ] Tools and write permissions are visible in the roster
- [ ] Three test prompts route to defensible specialists
- [ ] Overlap and no-owner gaps are documented
- [ ] **Explain to your coach** — when should a capability be a skill on the primary agent rather than a separate specialist?

## Learning Resources

- [Azure SRE Agent subagents](https://learn.microsoft.com/en-us/azure/sre-agent/subagents)
- [Azure SRE Agent tools](https://learn.microsoft.com/en-us/azure/sre-agent/tools)
- [Zero Trust least-privilege principle](https://learn.microsoft.com/en-us/security/zero-trust/deploy/identity)

## Tips

- A specialist name is not evidence of its tool grants; inspect the definition.
- Record why a specialist was selected.
- Flag specialists that can write but have no approval rule.

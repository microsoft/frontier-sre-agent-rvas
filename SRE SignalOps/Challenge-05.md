[< Previous Challenge](./Challenge-04.md) — **[Home](./README.md)** — [Next Challenge >](./Challenge-06.md)

# Challenge 05 — Route a Cross-Domain Incident

> **Incident capability exercised in this challenge**: Domain Routing · Coordinated Investigation · Least Privilege

## Introduction

A Grubify HTTP failure may originate in the application, telemetry path, network, or Azure platform. Route an ambiguous incident by evidence domain, coordinate the handoffs, and preserve one accountable incident narrative.

## Description

> **Customer demo script:** Run `pwsh -File '.\SRE SignalOps\Scripts\Challenge-05.ps1'` to inventory specialist agents and print routing prompts. See the [presenter runbook](./Scripts/README.md).

Use this exercise report:

> **EXERCISE:** Grubify clients receive intermittent HTTP 5xx responses, and one backend dependency shows connection failures. Determine which operational domains must investigate and in what order.

Have the primary SRE Agent form an initial hypothesis, select the first specialist based on the evidence needed, and define the handoff condition for a second domain. Keep a compact roster of relevant specialists with purpose, data sources, tools, write permissions, approval boundary, and return conditions. Skills and subagents are supporting implementation details; the required outcome is a coordinated incident investigation.

Use the repository manifests as a second source of truth:

```powershell
Get-ChildItem '.\Student\Resources\azure-sre-agent-config\subagents' -Filter '*.yaml' |
  ForEach-Object {
    [pscustomobject]@{ Name = $_.BaseName; Updated = $_.LastWriteTimeUtc; Bytes = $_.Length }
  } | Format-Table
```

Test the incident as it evolves from application error to denied network flow evidence. Add a cost-anomaly prompt only as a negative control: it should not divert the active availability incident unless cost evidence is causally relevant. Record each routing decision, evidence returned, rejected domain, handoff, and remaining owner gap.

## Success Criteria

- [ ] The initial incident hypothesis identifies the evidence needed before choosing a specialist
- [ ] Application and network handoffs are justified by returned evidence rather than keywords
- [ ] The primary SRE Agent preserves one timeline, owner, and unresolved-question list across handoffs
- [ ] Tool scope, write posture, overlap, and no-owner gaps are visible without becoming the focus of the incident report
- [ ] The unrelated cost prompt does not divert the availability investigation without causal evidence
- [ ] **Explain to your coach** — when should an SRE keep an investigation in one domain, and when is a specialist handoff justified?

## Learning Resources

- [Azure SRE Agent subagents](https://learn.microsoft.com/en-us/azure/sre-agent/subagents)
- [Azure SRE Agent tools](https://learn.microsoft.com/en-us/azure/sre-agent/tools)
- [Zero Trust least-privilege principle](https://learn.microsoft.com/en-us/security/zero-trust/deploy/identity)

## Tips

- Route according to the next evidence required, not the loudest keyword.
- A handoff must return evidence or a bounded uncertainty to the primary incident record.
- Do not let multiple specialists create competing timelines or owners.

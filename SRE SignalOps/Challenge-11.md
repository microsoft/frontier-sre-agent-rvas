[< Previous Challenge](./Challenge-10.md) — **[Home](./README.md)** — [Next Challenge >](./Challenge-12.md)

# Challenge 11 — Scope Impact with Dependency Evidence

> **Incident capability exercised in this challenge**: Dependency Evidence · Blast-Radius Analysis · Critical Path

## Introduction

During an availability incident, responders need to know whether one endpoint, one dependency, or the whole service is affected. Use observed Grubify telemetry to bound customer impact and identify the next dependency to test.

## Description

> **Customer demo script:** Run `pwsh -File '.\SRE SignalOps\Scripts\Challenge-11.ps1'` to generate API traffic and query Application Insights. See the [presenter runbook](./Scripts/README.md).

Use this exercise symptom without injecting a fault:

> **EXERCISE:** Grubify meal search is failing for some users while the main site remains reachable. Identify the affected critical path, likely blast radius, and strongest next check.

Ask the SRE Agent to map the frontend, API, downstream services, data stores, and Azure platform dependencies relevant to that user journey. Each edge must include direction, protocol, observed timestamp, request volume, latency, failure rate, and evidence source.

Use Application Insights to validate the graph. Where telemetry is absent, label the edge **documented but unobserved** rather than inventing data.

Challenge 00 instruments the Grubify API for request, exception, and dependency telemetry. The browser frontend is not instrumented, and the sample API currently uses in-memory data rather than an external database. Expect the observed map to be smaller than the intended architecture; generate API traffic before judging coverage.

Require four incident outputs:

1. A dependency diagram.
2. A table of observed edges.
3. The affected user-facing critical path and bounded blast radius.
4. Coverage gaps and the next discriminating check that would strengthen the diagnosis.

Do not claim that the exercise symptom is present unless telemetry confirms it. A healthy baseline is still useful: report the issue as not reproduced, identify what would be monitored during recurrence, and preserve the dependency evidence for the network investigations that follow.

## Success Criteria

- [ ] Every incident-relevant edge is observed or explicitly labeled unobserved
- [ ] The affected critical path and likely blast radius are bounded without overstating the evidence
- [ ] Latency, volume, and failure evidence support each health claim
- [ ] The result states whether the issue was reproduced and identifies the next discriminating check
- [ ] Telemetry gaps that weaken diagnosis are explicit
- [ ] **Explain to your coach** — how does dependency evidence prevent an SRE from changing a healthy component during an incident?

## Learning Resources

- [Application Map in Application Insights](https://learn.microsoft.com/en-us/azure/azure-monitor/app/app-map)
- [Application Insights dependency telemetry](https://learn.microsoft.com/en-us/azure/azure-monitor/app/dependencies)
- [Distributed tracing concepts](https://learn.microsoft.com/en-us/azure/azure-monitor/app/distributed-trace-data)

## Tips

- Architecture describes intent; telemetry describes observed behavior.
- Preserve resource IDs and timestamps.
- Do not infer a dependency from naming alone.

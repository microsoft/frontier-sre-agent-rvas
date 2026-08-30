[< Previous Challenge](./Challenge-06.md) — **[Home](./README.md)** — [Next Challenge >](./Challenge-08.md)

# Challenge 07 — Map the Application Dependency Graph

> **Capabilities added in this challenge**: Application Map · Dependency Evidence · Critical Path

## Introduction

Before diagnosing Grubify, establish what depends on what. Build an observed service graph from telemetry and compare it with the intended architecture.

## Description

> **Customer demo script:** Run `pwsh -File '.\SRE SignalOps\Scripts\Challenge-07.ps1'` to generate API traffic and query Application Insights. See the [presenter runbook](./Scripts/README.md).

Ask the agent to map the frontend, API, downstream services, data stores, and Azure platform dependencies. Each edge must include direction, protocol, observed timestamp, request volume, latency, failure rate, and evidence source.

Use Application Insights to validate the graph. Where telemetry is absent, label the edge **documented but unobserved** rather than inventing data.

Challenge 00 instruments the Grubify API for request, exception, and dependency telemetry. The browser frontend is not instrumented, and the sample API currently uses in-memory data rather than an external database. Expect the observed map to be smaller than the intended architecture; generate API traffic before judging coverage.

Require four outputs:

1. A dependency diagram.
2. A table of observed edges.
3. The user-facing critical path.
4. Coverage gaps that would weaken an RCA.

Introduce no fault in this mission. The graph is the baseline used by the network investigations that follow.

## Success Criteria

- [ ] Every graph edge is observed or explicitly labeled unobserved
- [ ] The critical user path is identified
- [ ] Latency and failure evidence support dependency health claims
- [ ] Telemetry gaps are visible rather than hidden
- [ ] **Explain to your coach** — why can a correct architecture diagram still be a poor incident dependency map?

## Learning Resources

- [Application Map in Application Insights](https://learn.microsoft.com/en-us/azure/azure-monitor/app/app-map)
- [Application Insights dependency telemetry](https://learn.microsoft.com/en-us/azure/azure-monitor/app/dependencies)
- [Distributed tracing concepts](https://learn.microsoft.com/en-us/azure/azure-monitor/app/distributed-trace-data)

## Tips

- Architecture describes intent; telemetry describes observed behavior.
- Preserve resource IDs and timestamps.
- Do not infer a dependency from naming alone.

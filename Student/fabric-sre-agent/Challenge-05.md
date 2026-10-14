[< Previous Challenge](./Challenge-04.md) — **[Home](../../README.md)** — [Next Challenge >](./Challenge-06.md)

# Challenge 05 — Attribute Execution and Pipeline Consumption

> **Capabilities added in this challenge**: Run-Level Consumption · Pipeline Attribution · Precision

## Introduction

Pipeline cost is not always stored on the pipeline itself. Activities can be
charged to child items, and scheduled or manual runs can overlap. This
challenge tests whether the agent distinguishes measured execution cost from
averages and uncertain attribution.

## Description

Investigate a named notebook execution and a pipeline run that invokes
compute-bearing children:

- Locate the relevant executions using the backend's timestamps and the
  Fabric job-instance or Spark monitoring evidence.
- Separate the pipeline's own consumption from consumption recorded against
  child items.
- Assess whether child operations can be attributed to this pipeline run or
  could also belong to a schedule, another pipeline, or a manual invocation.
- For FUAM, distinguish daily totals and averages from derived notebook
  execution CU; for Capacity Events, identify individual operations and
  preserve ambiguity when concurrent triggers overlap.
- Report the measurement basis and precision for every subtotal and the total.

## Success Criteria

- [ ] The notebook execution is correlated to the correct run using item identity and time/status evidence.
- [ ] The pipeline report separates pipeline-owned CU from each included child item.
- [ ] Exact, average, derived, shared, or ambiguous labels match the evidence and backend's data grain.
- [ ] Shared work is not silently attributed to a single pipeline; excluded runs and rationale are visible.
- [ ] **Explain to your coach** — why does a pipeline definition show possible dependencies but not prove which child ran during a particular execution?

## Learning Resources

- [FUAM precision rules](../Resources/fabric-sre-agent/fuam/agent-instructions.md)
- [Capacity Events precision rules](../Resources/fabric-sre-agent/capacity-events/agent-instructions.md)
- [Fabric job scheduler APIs](https://learn.microsoft.com/rest/api/fabric/core/job-scheduler)
- [Spark monitoring APIs](https://learn.microsoft.com/fabric/data-engineering/spark-monitoring-api-overview)

## Tips

- FUAM cannot separate multiple same-day non-Spark executions; do not present an average as a specific run.
- Capacity Events provides per-operation CU, but temporal overlap may still leave child-run attribution ambiguous.

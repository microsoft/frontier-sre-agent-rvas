[< Previous Challenge](./Challenge-05.md) — **[Home](../../README.md)** — [Next Challenge >](./Challenge-07.md)

# Challenge 06 — Investigate Failures, Slowness, and Throttling

> **Capabilities added in this challenge**: Fabric RCA · Capacity Correlation · Evidence Ranking

## Introduction

High CU consumption, long duration, and throttling are related but distinct
signals. A strong root-cause analysis aligns workload executions with capacity
pressure, Fabric job status, and—when relevant—Spark evidence before making a
claim.

## Description

Investigate a failed, slow, or throttled Fabric workload over a bounded
incident window:

- Establish which execution was affected, its status, duration, failure
  details, and measured consumption.
- Correlate the run with concurrent capacity consumers and available
  utilization, delay, rejection, or throttling evidence.
- For notebooks or notebook-backed pipeline failures, inspect the relevant
  Spark jobs, stages, executors, and driver/executor logs.
- Distinguish observed facts from likely cause and state what additional
  evidence would confirm or disprove the hypothesis.
- Compare the backend's native limitations: FUAM timepoints and daily
  aggregates versus Capacity Events operation and throttle data.

## Success Criteria

- [ ] The report identifies a specific execution and uses a bounded, explicit time window.
- [ ] Findings cite job status, capacity evidence, and Spark diagnostics where applicable.
- [ ] The most likely cause is separated from supporting observations and remaining uncertainty.
- [ ] The report does not infer smoothed capacity utilization from operation events alone.
- [ ] **Explain to your coach** — which measurements establish workload duration, and which establish capacity pressure or throttling?

## Learning Resources

- [FUAM RCA procedure](../Resources/fabric-sre-agent/fuam/agent-instructions.md)
- [Capacity Events RCA procedure](../Resources/fabric-sre-agent/capacity-events/agent-instructions.md)
- [Spark monitoring API overview](https://learn.microsoft.com/fabric/data-engineering/spark-monitoring-api-overview)
- [Fabric operations and throttling](https://learn.microsoft.com/fabric/enterprise/fabric-operations)

## Tips

- A long-running operation is not automatically a capacity incident; examine waits, queueing, workload shape, and concurrency.
- Capacity operation events do not contain the smoothed utilization percentage; explain this limit when relevant.

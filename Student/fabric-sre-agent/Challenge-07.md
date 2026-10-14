[< Previous Challenge](./Challenge-06.md) — **[Home](../../README.md)** — [Next Challenge >](./Challenge-08.md)

# Challenge 07 — Optimize a Measured Spark Workload

> **Capabilities added in this challenge**: Spark Diagnostics · Evidence-Based Optimization · Impact Estimate

## Introduction

Optimization recommendations are more credible when they point to a measured
bottleneck and estimate the impact under explicit assumptions. The supplied
demo notebook deliberately introduces inefficient Spark patterns so you can
test the agent's reasoning against observable runs.

## Description

Use the provided `perf_demo_inefficient.ipynb` in a monitored, approved
workspace and ask the agent to investigate its consumption and performance:

- Establish a baseline with the selected backend and identify the target
  notebook execution.
- Examine the notebook code and relevant Spark jobs, stages, tasks, executor
  allocation, shuffle, skew, spill, and failure evidence.
- Relate each recommendation to a specific measured symptom and code pattern.
- Estimate potential CU or cost impact with clearly stated assumptions; do
  not claim measured savings before rerunning and comparing.
- Keep the exercise read-only from the agent's perspective. Any workload run
  or cleanup is performed by the participant with workspace-owner approval.

## Success Criteria

- [ ] The baseline run appears in the selected consumption source and is linked to its Spark execution.
- [ ] At least two optimization recommendations cite evidence from code and run diagnostics.
- [ ] Estimated savings are labeled as estimates and show the assumptions behind them.
- [ ] No Fabric object is modified or executed by the agent; the participant owns any demo run and cleanup.
- [ ] **Explain to your coach** — what experiment would demonstrate that a recommendation actually reduced CU without shifting cost elsewhere?

## Learning Resources

- [Demo notebook](../Resources/fabric-sre-agent/demo/perf_demo_inefficient.ipynb)
- [Spark monitoring API overview](https://learn.microsoft.com/fabric/data-engineering/spark-monitoring-api-overview)
- [Fabric Spark job definition and monitoring](https://learn.microsoft.com/fabric/data-engineering/spark-job-definition)
- [Fabric optimization guidance](https://learn.microsoft.com/fabric/data-engineering/spark-best-practices)

## Tips

- The demo uses skew, disabled adaptive query execution and broadcast joins, excess shuffle partitions, and repeated work.
- Use a standard Spark session; high-concurrency sessions complicate attribution.
- Avoid running the demo on a production or shared capacity without owner approval.

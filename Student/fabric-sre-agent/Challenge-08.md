[< Previous Challenge](./Challenge-07.md) — **[Home](../../README.md)** — [Next Challenge >](./Challenge-09.md)

# Challenge 08 — Assess Coverage and Capacity Context

> **Capabilities added in this challenge**: Monitoring Quality · Capacity Context · Operational Caveats

## Introduction

FinOps analysis depends on more than a query returning rows. Retention gaps,
late ingestion, paused subscriptions, preview operations, and the monitoring
pipeline's own CU can all distort conclusions. This challenge turns those
limitations into an explicit operational assessment.

## Description

Review the health and decision-usefulness of your chosen consumption source:

- Measure the latest event or loaded date, expected ingestion delay, missing
  intervals, and retention boundary.
- Check for duplicate events, preview/non-billed operations, unresolved
  identities, and capacity SKU or region changes where the backend exposes
  them.
- Estimate the ongoing monitoring workload cost and state which team or
  capacity owns it.
- Compare what FUAM and Capacity Events can show for one sample question,
  noting exactness, history, utilization context, and operational cost.
- Produce a concise coverage statement that an SRE or FinOps reviewer could
  use to decide whether the evidence is sufficient.

## Success Criteria

- [ ] The source freshness, effective history window, and known ingestion or retention gaps are measured and reported.
- [ ] Relevant duplicate, preview, SKU/region, or naming limitations are checked or explicitly marked unavailable.
- [ ] The monitoring solution's own ongoing cost and ownership are described.
- [ ] A backend comparison identifies at least one decision where the data grain changes the answer's confidence.
- [ ] **Explain to your coach** — what evidence would make you stop a cost comparison and label it inconclusive?

## Learning Resources

- [FUAM known limits and troubleshooting](../Resources/fabric-sre-agent/fuam/README.md)
- [Capacity Events known limits and troubleshooting](../Resources/fabric-sre-agent/capacity-events/README.md)
- [Fabric capacity operation events](https://learn.microsoft.com/fabric/real-time-hub/explore-fabric-capacity-operation-events)
- [Fabric Capacity Metrics app](https://learn.microsoft.com/fabric/enterprise/metrics-app)

## Tips

- Event ingestion time can lag operation start time, particularly for background work.
- The Capacity Events Eventstream and Eventhouse consume CU continuously; include that in the backend trade-off.

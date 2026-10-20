[< Previous Challenge](./Challenge-03.md) — **[Home](../../README.md)** — [Next Challenge >](./Challenge-05.md)

# Challenge 04 — Explain Spend by Workspace and Item

> **Capabilities added in this challenge**: Workspace Cost Analysis · Trends · Inventory Resolution

## Introduction

FinOps questions often begin with a comparison: which workspaces and items
consumed the most capacity, and how did that change over time? Answering well
requires resolving names, periods, deleted items, partial data, and shared
capacity context without overstating what a cost estimate means.

## Description

Investigate a workspace-level question for two comparable periods:

- Compare total consumption and cost for the workspace, then rank its leading
  items and operation types.
- Use current and historical inventory evidence to resolve names; label
  deleted or unresolved items rather than silently omitting their consumption.
- Compare like-for-like days when one interval is incomplete, and state time
  zone, date boundaries, latest available data, and missing days.
- Explain whether the source can distinguish billable from preview operations
  and identify other material caveats.
- Present an auditable breakdown and calculation that another engineer can
  reproduce.

## Success Criteria

- [ ] The workspace total reconciles to its item-level breakdown for both periods.
- [ ] The leading contributors and changes are ranked with explicit dates, units, and precision.
- [ ] Partial periods, data freshness, unresolved/deleted items, and backend-specific billing limitations are disclosed.
- [ ] The agent identifies the estimate as CU-based standalone-equivalent cost rather than invoice allocation.
- [ ] **Explain to your coach** — how can deleted-item history or a partial current period change the interpretation of a workspace comparison?

## Learning Resources

- [FUAM backend guide](../Resources/fabric-sre-agent/fuam/README.md)
- [Capacity Events backend guide](../Resources/fabric-sre-agent/capacity-events/README.md)
- [Fabric Capacity Metrics app](https://learn.microsoft.com/fabric/enterprise/metrics-app)
- [Capacity operation events](https://learn.microsoft.com/fabric/real-time-hub/explore-fabric-capacity-operation-events)

## Tips

- FUAM's inventory is a daily snapshot; historical names may require its history tables or activity log.
- For weekly comparisons, compare the same weekdays or explicitly mark the current week as partial.

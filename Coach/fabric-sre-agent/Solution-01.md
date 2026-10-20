[< Previous Solution](./Solution-00.md) | **[Home](../../README.md)** | [Next Solution >](./Solution-02.md)

# Coach Guide — Challenge 01: Select and Validate a Shared Consumption Backend

## Purpose

- Help students match backend data grain and operational cost to the analysis use case.
- Confirm the chosen source contains recent, interpretable consumption evidence.
- Expected time: 30–45 minutes; both backends are provisioned by the coach before the workshop.

## Mini-Lecture (10 min before challenge)

- FUAM is a scheduled Lakehouse ingestion of Capacity Metrics data, with daily grain.
- Capacity operation events provide per-operation evidence, but only from subscription start and within retention.
- FUAM notebook run CU may be derived using Spark allocation; other repeated daily operations are not separable.
- Event operation `capacityUnitMs` is not the same unit as FUAM `TotalCUs`.
- Monitoring itself consumes CU; choosing higher precision has a recurring cost.
- Both sources are shared coach-owned items. Students choose and validate a
  source, not deploy collectors or change shared retention/refresh settings.

## Expected Student Output

- A short backend decision with precision, latency, retention, and ongoing-cost rationale.
- Recent sample records from the selected backend and the actual schema/column casing.
- Recorded workspace, endpoint, region, capacity, and time-zone conventions.
- Explicit acknowledgement of the unsupported precision or history gaps.

## Common Issues and Hints

- **Symptom:** FUAM table query returns no rows. **Fix:** the coach inspects FUAM pipeline history, service-principal API configuration, app refresh time, and workspace identifiers; students do not change shared pipelines.
- **Symptom:** `OperationsTable` exists but contains no new rows. **Fix:** verify the event subscription is active, its owner remains capacity admin, the monitored capacity is running, and an operation occurred after subscription creation.
- **Symptom:** Capacity Events values are empty after parsing `Data`. **Fix:** inspect `getschema` and one sample row; dynamic property casing depends on mapping.
- **Symptom:** The team expects months of event history immediately. **Fix:** explain that history begins at subscription time and cannot be reconstructed retroactively from that stream.

## Debrief Discussion Guide

- Which business question requires per-operation evidence?
- What does the team give up by selecting the lower-cost scheduled source?
- How will monitoring cost and retention be reviewed after deployment?

## Success Criteria Notes

- Be strict that both backends have been prepared and shared by the coach;
  each team validates one selected source with a sample row.
- Accept either backend if its known limits are explicitly documented.
- Ensure the chosen backend guide and corresponding instruction file are the active source of truth.

## Solution

Before the event, the coach completes both
[FUAM setup](../../Student/Resources/fabric-sre-agent/fuam/README.md) and
[Capacity Events setup](../../Student/Resources/fabric-sre-agent/capacity-events/README.md).
Share the relevant items with audience users/groups and grant each team UAMI
the documented read permissions. Give students the connection identifiers and
known data-coverage limits. For FUAM, a successful bounded check is:

```sql
SELECT TOP 5 Date, WorkspaceId, ItemId, OperationName, TotalCUs, OperationCount
FROM dbo.capacity_metrics_by_item_by_operation_by_day
ORDER BY Date DESC;
```

For Capacity Events, inspect actual casing and payload mapping before applying
the documented KQL templates:

```kusto
OperationsTable | getschema
OperationsTable | take 1
```

Do not require a fixed schema mapping where a workspace has flattened the
payload differently.

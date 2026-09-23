[< Previous Solution](./Solution-01.md) | **[Home](../../README.md)** | [Next Solution >](./Solution-03.md)

# Coach Guide — Challenge 02: Establish a Query Store Baseline

## Purpose

* Establish trustworthy historical evidence before diagnostic scenarios.
* Teach interval, capture-state, and workload-volume awareness.
* Expected time: 35-50 minutes.

## Mini-Lecture (8 min before challenge)

* Query Store separates query text, plans, and runtime intervals.
* Lifetime averages flatten changes and can hide both regressions and recovery.
* Execution count and per-execution cost answer different operational questions.
* Capture mode, cleanup, retention, and permissions define the evidence window.
* "No rows" means no retained evidence for the query and interval.

## Expected Student Output

* The baseline workload runs several times.
* Query Store remains `READ_WRITE`.
* The report states a UTC interval and capture limitations.
* At least two workshop procedures appear with runtime evidence.
* Average, total, and execution-count measurements are not conflated.

## Common Issues and Hints

* **Symptom:** Query Store returns no matching queries. **Fix:** rerun the baseline workload, wait for the runtime interval to flush, and confirm capture state.
* **Symptom:** The agent ranks by average duration alone. **Fix:** require execution count, total duration, CPU, reads, and writes in the same table.
* **Symptom:** The report claims a regression without a comparison interval. **Fix:** ask for two equivalent time windows or relabel the result as a baseline observation.
* **Symptom:** Query Store is `READ_ONLY`. **Fix:** inspect storage and capture status; do not let the agent reconfigure it.

## Debrief Discussion Guide

* Which metric changed most when the workload was repeated?
* When is total resource use more important than per-execution latency?
* What baseline metadata must be recorded so another investigator can reproduce
  the report?

## Success Criteria Notes

* Be strict on the UTC interval and Query Store state.
* Accept different captured totals depending on execution timing.
* Do not require plan variation in this baseline challenge.

## Solution

Run the baseline three times in an approved SQL client:

```sql
:r Student/Resources/sql-server-mcp/workloads/01_capture_baseline.sql
GO
:r Student/Resources/sql-server-mcp/workloads/01_capture_baseline.sql
GO
:r Student/Resources/sql-server-mcp/workloads/01_capture_baseline.sql
GO
```

Then use:

```text
Using only sqlserver-mcp, summarize Query Store activity for the workshop
procedures during the smallest recent UTC interval that includes the baseline.
Show execution count, average and total duration, CPU, logical reads, writes,
and plan count. State capture status, interval boundaries, missing evidence,
and confirm that no database changes were applied.
```


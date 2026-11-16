---
title: Establish a Query Store Baseline
summary: Seed repeatable activity and define a trustworthy historical observation window before diagnosing regressions.
phase: Baseline
group: Investigations
tags:
- Query Store
- time windows
highlight: false
---

# Challenge 02 — Establish a Query Store Baseline

> **Capabilities added in this challenge**: Query Store · Historical Evidence · Observation Windows

## Purpose

* Build a Query Store baseline in which every figure states its interval, capture state, and execution count.
* Identify when lifetime averages hide a regression or a change in workload volume.
* Expected time: 35-50 minutes.

## Introduction

Query Store shows how query behavior changed over time, but only if the
workload was captured and you know the observation window. An empty or stale
store is missing evidence, not evidence of good performance.

Create a repeatable baseline and make the agent state its limits before it
makes historical claims.

## Description

Create a defensible Query Store baseline:

* Confirm that Query Store is available, writable, and retaining runtime data
* Generate representative activity with
  `workloads/01_capture_baseline.sql`
* Ask the DBA agent to summarize query frequency, duration, CPU, reads, writes,
  and plan history for a bounded recent interval
* Separate average cost, total cost, execution count, and plan changes
* Record the UTC observation interval and any capture, retention, or permission
  limitations
* Preserve the database exactly as the supplied workload leaves it

### Solution steps

Run the baseline three times in an approved SQL client:

```sql
:r labs/02-sql-server-dba/resources/sql-server-mcp/workloads/01_capture_baseline.sql
GO
:r labs/02-sql-server-dba/resources/sql-server-mcp/workloads/01_capture_baseline.sql
GO
:r labs/02-sql-server-dba/resources/sql-server-mcp/workloads/01_capture_baseline.sql
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

## Success Criteria

- [ ] Query Store reports `READ_WRITE` and contains captured workshop queries
- [ ] The agent reports a specific UTC observation interval
- [ ] The baseline distinguishes execution count from per-execution and total resource cost
- [ ] At least two workload procedures appear with evidence from the requested interval
- [ ] The report states what cannot be concluded from the available history
- [ ] **Explain in your own words** (two or three written sentences) — why can lifetime averages hide both regressions and workload-volume changes?

## Learning Resources

* [Monitor performance with Query Store](https://learn.microsoft.com/sql/relational-databases/performance/monitoring-performance-by-using-the-query-store)
* [Query Store usage scenarios](https://learn.microsoft.com/sql/relational-databases/performance/query-store-usage-scenarios)
* [Query Store best practices](https://learn.microsoft.com/sql/relational-databases/performance/best-practice-with-the-query-store)

## Tips

* Run the baseline more than once if the first capture interval is too sparse.
* A plan count without runtime intervals does not establish a regression.
* Ask the agent to state capture state and data freshness before ranking
  queries.

## Hints and notes

> Hidden until you click. Expand a section only when you want it.

<details>
<summary><strong>Background</strong></summary>

* Query Store separates query text, plans, and runtime intervals.
* Lifetime averages flatten changes and can hide both regressions and recovery.
* Execution count and per-execution cost answer different operational questions.
* Capture mode, cleanup, retention, and permissions define the evidence window.
* "No rows" means no retained evidence for the query and interval.

</details>

<details>
<summary><strong>Expected Output</strong></summary>

* The baseline workload runs several times.
* Query Store remains `READ_WRITE`.
* The report states a UTC interval and capture limitations.
* At least two workshop procedures appear with runtime evidence.
* Average, total, and execution-count measurements are not conflated.

</details>

<details>
<summary><strong>Common Issues and Hints</strong></summary>

* **Symptom:** Query Store returns no matching queries. **Fix:** rerun the baseline workload, wait for the runtime interval to flush, and confirm capture state.
* **Symptom:** The agent ranks by average duration alone. **Fix:** require execution count, total duration, CPU, reads, and writes in the same table.
* **Symptom:** The report claims a regression without a comparison interval. **Fix:** ask for two equivalent time windows or relabel the result as a baseline observation.
* **Symptom:** Query Store is `READ_ONLY`. **Fix:** inspect storage and capture status; do not let the agent reconfigure it.

</details>

<details>
<summary><strong>Debrief Discussion Guide</strong></summary>

* Which metric changed most when the workload was repeated?
* When is total resource use more important than per-execution latency?
* What baseline metadata must be recorded so another investigator can reproduce
  the report?

</details>

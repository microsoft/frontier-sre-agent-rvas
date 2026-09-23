[< Previous Challenge](./Challenge-01.md) — **[Home](../../README.md)** — [Next Challenge >](./Challenge-03.md)

# Challenge 02 — Establish a Query Store Baseline

> **Capabilities added in this challenge**: Query Store · Historical Evidence · Observation Windows

## Introduction

Query Store can answer how query behavior changed over time, but only when the
workload has been captured and the observation window is understood. An empty
or stale store is missing evidence, not evidence of good performance.

Your goal is to create a repeatable baseline and teach the agent to report the
limits of that baseline before it makes historical claims.

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

## Success Criteria

- [ ] Query Store reports `READ_WRITE` and contains captured workshop queries
- [ ] The agent reports a specific UTC observation interval
- [ ] The baseline distinguishes execution count from per-execution and total resource cost
- [ ] At least two workload procedures appear with evidence from the requested interval
- [ ] The report states what cannot be concluded from the available history
- [ ] **Explain to your coach** — why can lifetime averages hide both regressions and workload-volume changes?

## Learning Resources

* [Monitor performance with Query Store](https://learn.microsoft.com/sql/relational-databases/performance/monitoring-performance-by-using-the-query-store)
* [Query Store usage scenarios](https://learn.microsoft.com/sql/relational-databases/performance/query-store-usage-scenarios)
* [Query Store best practices](https://learn.microsoft.com/sql/relational-databases/performance/best-practice-with-the-query-store)

## Tips

* Run the baseline more than once if the first capture interval is too sparse.
* A plan count without runtime intervals does not establish a regression.
* Ask the agent to state capture state and data freshness before ranking
  queries.


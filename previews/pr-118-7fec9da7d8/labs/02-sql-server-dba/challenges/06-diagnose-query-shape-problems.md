---
title: Diagnose Query Shape Problems
summary: Find non-SARGable predicates and implicit conversions, then explain their access-path impact without rewriting production code.
phase: Query shape
group: Investigations
tags:
- SARGability
- conversions
highlight: false
---

# Challenge 06 — Diagnose Query Shape Problems

> **Capabilities added in this challenge**: SARGability · Implicit Conversion · Access-Path Reasoning

## Purpose

* Identify the non-SARGable predicate and the implicit conversion as separate query-shape problems, each with its own plan evidence.
* Produce a code-owner handoff that recommends a rewrite without modifying any database object.
* Expected time: 35-50 minutes.

## Introduction

A predicate can prevent SQL Server from seeking into an index. A data-type
mismatch can add conversion work or distort cardinality estimates. Examine
the query shape before treating either pattern as a missing-index problem.

You diagnose both patterns and write a safe handoff for the application owner.

## Description

Use `workloads/04_sargability.sql` to generate the supplied examples, then ask
the DBA agent to:

* Locate the affected procedures and their recent Query Store evidence
* Identify the non-SARGable date predicate and the implicit conversion
* Explain how each pattern affects index access and estimation
* Correlate plan warnings with runtime observations
* Describe application-level corrections and their tradeoffs without changing
  stored procedures, indexes, or data
* Define tests the application owner should run before deployment

### Solution steps

Run:

```sql
:r labs/02-sql-server-dba/resources/sql-server-mcp/workloads/04_sargability.sql
```

Then use:

```text
Find the recent calendar-date search and external-reference lookup. For each,
identify the object, predicate, data types, Query Store evidence, and estimated
plan behavior. Explain SARGability or conversion impact and propose a
code-owner validation plan. Do not change procedures, indexes, statistics, or
database settings.
```

The calendar-date path should expose a function-shaped predicate. The external
reference path should expose a type-conversion concern. Tie each claim to its
own evidence.

## Success Criteria

- [ ] The report distinguishes the date-predicate issue from the data-type conversion issue
- [ ] Each finding includes object, predicate, plan, and Query Store evidence
- [ ] The explanation connects query shape to the observed access path
- [ ] Recommendations identify ownership, validation, and regression risks
- [ ] The agent makes no procedure, index, statistics, or configuration change
- [ ] **Explain in your own words** (two or three written sentences) — why can adding an index fail to solve a non-SARGable predicate?

## Learning Resources

* [SQL Server index architecture and design](https://learn.microsoft.com/sql/relational-databases/sql-server-index-design-guide)
* [Data type conversion](https://learn.microsoft.com/sql/t-sql/data-types/data-type-conversion-database-engine)
* [Cardinality estimation](https://learn.microsoft.com/sql/relational-databases/performance/cardinality-estimation-sql-server)

## Tips

* Ask which side of a comparison SQL Server converts.
* Estimated plans show compilation choices, not actual runtime row counts.
* A safe recommendation includes a testable query rewrite, not only a label.

## Hints and notes

> Hidden until you click. Expand a section only when you want it.

<details>
<summary><strong>Background</strong></summary>

* Search arguments let the optimizer use ordered index access efficiently.
* Functions applied to indexed columns can prevent seeks.
* Implicit conversion direction determines whether an index remains usable.
* Plan warnings need runtime context before they become incident findings.
* Query rewrites can change semantics and require application regression tests.

</details>

<details>
<summary><strong>Expected Output</strong></summary>

* Both supplied workload patterns appear in Query Store.
* The date predicate and conversion are diagnosed separately.
* Plan evidence is tied to the relevant object and predicate.
* Recommendations identify application ownership and validation.
* No procedure, index, or statistics object changes.

</details>

<details>
<summary><strong>Common Issues and Hints</strong></summary>

* **Symptom:** The agent recommends another index for the date search. **Fix:** ask which expression prevents the existing access path from being searchable.
* **Symptom:** It names an implicit conversion but not its direction. **Fix:** require source type, target type, converted expression, and access-path impact.
* **Symptom:** Query Store has no recent rows. **Fix:** rerun the workload and use the smallest interval that contains it.
* **Symptom:** The agent rewrites the procedure through a fallback tool. **Fix:** fail the safety criterion and remove the fallback path.

</details>

<details>
<summary><strong>Debrief Discussion Guide</strong></summary>

* Why can the same logical filter produce a different physical access path?
* When is an implicit conversion harmless?
* Which regression tests protect semantics after a query rewrite?

</details>

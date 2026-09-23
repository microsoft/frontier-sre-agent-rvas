[< Previous Solution](./Solution-05.md) | **[Home](../../README.md)** | [Next Solution >](./Solution-07.md)

# Coach Guide — Challenge 06: Diagnose Query Shape Problems

## Purpose

* Identify non-SARGable predicates and implicit conversions as query-shape
  problems.
* Produce a code-owner handoff without modifying database objects.
* Expected time: 35-50 minutes.

## Mini-Lecture (8 min before challenge)

* Search arguments let the optimizer use ordered index access efficiently.
* Functions applied to indexed columns can prevent seeks.
* Implicit conversion direction determines whether an index remains usable.
* Plan warnings need runtime context before they become incident findings.
* Query rewrites can change semantics and require application regression tests.

## Expected Student Output

* Both supplied workload patterns appear in Query Store.
* The date predicate and conversion are diagnosed separately.
* Plan evidence is tied to the relevant object and predicate.
* Recommendations identify application ownership and validation.
* No procedure, index, or statistics object changes.

## Common Issues and Hints

* **Symptom:** The agent recommends another index for the date search. **Fix:** ask which expression prevents the existing access path from being searchable.
* **Symptom:** It names an implicit conversion but not its direction. **Fix:** require source type, target type, converted expression, and access-path impact.
* **Symptom:** Query Store has no recent rows. **Fix:** rerun the workload and use the smallest interval that contains it.
* **Symptom:** The agent rewrites the procedure through a fallback tool. **Fix:** fail the safety criterion and remove the fallback path.

## Debrief Discussion Guide

* Why can the same logical filter produce a different physical access path?
* When is an implicit conversion harmless?
* Which regression tests protect semantics after a query rewrite?

## Success Criteria Notes

* Be strict that the two issues remain distinct.
* Accept platform-specific plan operator wording.
* Accept multiple safe rewrite options when semantic risks are explained.

## Solution

Run:

```sql
:r Student/Resources/sql-server-mcp/workloads/04_sargability.sql
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
reference path should expose a type-conversion concern. Require the student to
tie each claim to its own evidence.


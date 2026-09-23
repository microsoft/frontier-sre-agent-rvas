[< Previous Challenge](./Challenge-05.md) — **[Home](../../README.md)** — [Next Challenge >](./Challenge-07.md)

# Challenge 06 — Diagnose Query Shape Problems

> **Capabilities added in this challenge**: SARGability · Implicit Conversion · Access-Path Reasoning

## Introduction

An index cannot help when a predicate prevents SQL Server from seeking into it,
and a data-type mismatch can add conversion work or distort cardinality
estimates. These defects often look like an indexing problem until the query
shape is examined.

In this challenge, you diagnose both patterns and create a safe handoff for the
application owner.

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

## Success Criteria

- [ ] The report distinguishes the date-predicate issue from the data-type conversion issue
- [ ] Each finding includes object, predicate, plan, and Query Store evidence
- [ ] The explanation connects query shape to the observed access path
- [ ] Recommendations identify ownership, validation, and regression risks
- [ ] The agent makes no procedure, index, statistics, or configuration change
- [ ] **Explain to your coach** — why can adding an index fail to solve a non-SARGable predicate?

## Learning Resources

* [SQL Server index architecture and design](https://learn.microsoft.com/sql/relational-databases/sql-server-index-design-guide)
* [Data type conversion](https://learn.microsoft.com/sql/t-sql/data-types/data-type-conversion-database-engine)
* [Cardinality estimation](https://learn.microsoft.com/sql/relational-databases/performance/cardinality-estimation-sql-server)

## Tips

* Ask which side of a comparison SQL Server converts.
* Estimated plans show compilation choices, not actual runtime row counts.
* A safe recommendation includes a testable query rewrite, not only a label.


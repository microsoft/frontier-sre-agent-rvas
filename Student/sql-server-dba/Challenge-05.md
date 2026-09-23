[< Previous Challenge](./Challenge-04.md) — **[Home](../../README.md)** — [Next Challenge >](./Challenge-06.md)

# Challenge 05 — Build an Evidence-Based Index Case

> **Capabilities added in this challenge**: Index Analysis · Estimated Plans · Tuning Tradeoffs

## Introduction

A missing-index suggestion is not a change request. It is one signal that must
be compared with real workload frequency, existing indexes, selectivity,
storage, and write cost.

Your task is to build a decision-ready case for the deliberate product-led
access-path gap in `sales.SalesOrderLine`, without creating an index.

## Description

Generate the intended evidence with `workloads/02_missing_index.sql`, then use
the DBA agent to:

* Find the relevant Query Store query and quantify its observed impact
* Inspect the complete existing index set on `sales.SalesOrderLine`
* Analyze an estimated plan without executing extra application workload
* Explain the access path, predicate, included-column needs, and cardinality
  evidence
* Propose a candidate index only after checking overlap and write overhead
* Define how a DBA should validate the recommendation before approval

## Success Criteria

- [ ] The report identifies the product-led workload and its Query Store evidence
- [ ] Existing indexes are compared before a new candidate is proposed
- [ ] Estimated-plan evidence is correlated with runtime history rather than used alone
- [ ] The recommendation includes expected benefit, storage and write costs, overlap risk, and validation steps
- [ ] No index or other database object is created, altered, or dropped
- [ ] **Explain to your coach** — what evidence would cause you to reject the missing-index recommendation?

## Learning Resources

* [SQL Server index design guide](https://learn.microsoft.com/sql/relational-databases/sql-server-index-design-guide)
* [Tune nonclustered indexes with missing index suggestions](https://learn.microsoft.com/sql/relational-databases/indexes/tune-nonclustered-missing-index-suggestions)
* [Display an estimated execution plan](https://learn.microsoft.com/sql/relational-databases/performance/display-the-estimated-execution-plan)

## Tips

* A high estimated improvement value can still describe a rare query.
* Check key order, included columns, filters, and existing index prefixes.
* Keep observations, hypotheses, and recommendations in separate sections.


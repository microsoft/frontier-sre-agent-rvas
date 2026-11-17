---
title: Build an Evidence-Based Index Case
summary: Correlate Query Store, the existing index set, and an estimated plan before recommending a change.
phase: Tune
group: Investigations
tags:
- indexes
- estimated plan
highlight: false
---

# Challenge 05 — Build an Evidence-Based Index Case

> **Capabilities added in this challenge**: Index Analysis · Estimated Plans · Tuning Tradeoffs

## Purpose

* Write an index recommendation that states its benefit, overlap, storage, write cost, and rejection criteria.
* Support it by correlating Query Store history, the existing index set, and an estimated plan.
* Expected time: 40-55 minutes.

## Introduction

A missing-index suggestion is not a change request. It is one signal to weigh
against real workload frequency, existing indexes, selectivity, storage, and
write cost.

Evaluate the deliberate gap in index access for product-led queries on
`sales.SalesOrderLine`. Do not create an index.

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

### Solution steps

Run:

```sql
:r labs/02-sql-server-dba/resources/sql-server-mcp/workloads/02_missing_index.sql
```

Then use:

```text
Investigate the product-led sales-order-line workload. Correlate recent Query
Store impact, existing indexes on sales.SalesOrderLine, selectivity, and an
estimated plan. Recommend a candidate only if evidence supports it. Include
overlap, storage, write cost, validation, and rejection criteria. Do not create
or alter an index.
```

The candidate should lead with `ProductId` and account for the columns required
by `sales.usp_GetProductSalesSummary`. What matters most is the evidence chain
and the tradeoff analysis.

## Success Criteria

- [ ] The report identifies the product-led workload and its Query Store evidence
- [ ] Existing indexes are compared before a new candidate is proposed
- [ ] Estimated-plan evidence is correlated with runtime history rather than used alone
- [ ] The recommendation includes expected benefit, storage and write costs, overlap risk, and validation steps
- [ ] No index or other database object is created, altered, or dropped
- [ ] **Explain in your own words** (two or three written sentences) — what evidence would cause you to reject the missing-index recommendation?

## Learning Resources

* [SQL Server index design guide](https://learn.microsoft.com/sql/relational-databases/sql-server-index-design-guide)
* [Tune nonclustered indexes with missing index suggestions](https://learn.microsoft.com/sql/relational-databases/indexes/tune-nonclustered-missing-index-suggestions)
* [Display an estimated execution plan](https://learn.microsoft.com/sql/relational-databases/performance/display-the-estimated-execution-plan)

## Tips

* A high estimated improvement value can still describe a rare query.
* Check key order, included columns, filters, and existing index prefixes.
* Keep observations, hypotheses, and recommendations in separate sections.

## Hints and notes

> Hidden until you click. Expand a section only when you want it.

<details>
<summary><strong>Background</strong></summary>

* Missing-index DMVs are cumulative suggestions, not approved designs.
* Query frequency and total impact can matter more than one expensive execution.
* Existing index prefixes and included columns can make a new index redundant.
* Estimated plans show compilation choices but not actual runtime row counts.
* Every read benefit adds storage and write-maintenance cost.

</details>

<details>
<summary><strong>Expected Output</strong></summary>

* The product-led `SalesOrderLine` workload is found in Query Store.
* The current index set is documented before a candidate is proposed.
* Estimated-plan evidence supports the access-path explanation.
* The candidate includes benefit, overlap, storage, and write-cost analysis.
* No index is created.

</details>

<details>
<summary><strong>Common Issues and Hints</strong></summary>

* **Symptom:** Query Store has too little product workload. **Fix:** rerun `workloads/02_missing_index.sql` several times and wait for capture.
* **Symptom:** The agent repeats the missing-index DMV statement verbatim. **Fix:** require comparison with current index keys, includes, filters, and workload frequency.
* **Symptom:** The estimated plan has no missing-index warning. **Fix:** judge the observed access path and runtime correlation; a specific warning isn't required.
* **Symptom:** The agent creates the index to prove benefit. **Fix:** stop the exercise, restore the sample database if needed, and re-establish the read-only custom agent.

</details>

<details>
<summary><strong>Debrief Discussion Guide</strong></summary>

* Which evidence made the candidate stronger than the DMV suggestion alone?
* Which write-heavy workload could make the index harmful?
* How would you validate benefit without changing production first?

</details>

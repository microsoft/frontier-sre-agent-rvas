[< Previous Solution](./Solution-04.md) | **[Home](../../README.md)** | [Next Solution >](./Solution-06.md)

# Coach Guide — Challenge 05: Build an Evidence-Based Index Case

## Purpose

* Turn a missing-index signal into a balanced engineering recommendation.
* Correlate runtime history, current design, and estimated-plan evidence.
* Expected time: 40-55 minutes.

## Mini-Lecture (8 min before challenge)

* Missing-index DMVs are cumulative suggestions, not approved designs.
* Query frequency and total impact can matter more than one expensive execution.
* Existing index prefixes and included columns can make a new index redundant.
* Estimated plans show compilation choices but not actual runtime row counts.
* Every read benefit adds storage and write-maintenance cost.

## Expected Student Output

* The product-led `SalesOrderLine` workload is found in Query Store.
* The current index set is documented before a candidate is proposed.
* Estimated-plan evidence supports the access-path explanation.
* The candidate includes benefit, overlap, storage, and write-cost analysis.
* No index is created.

## Common Issues and Hints

* **Symptom:** Query Store has too little product workload. **Fix:** rerun `workloads/02_missing_index.sql` several times and wait for capture.
* **Symptom:** The agent repeats the missing-index DMV statement verbatim. **Fix:** require comparison with current index keys, includes, filters, and workload frequency.
* **Symptom:** The estimated plan has no missing-index warning. **Fix:** grade the observed access path and runtime correlation; do not require a specific warning.
* **Symptom:** The agent creates the index to prove benefit. **Fix:** stop the exercise, restore the sample database if needed, and re-establish the read-only custom agent.

## Debrief Discussion Guide

* Which evidence made the candidate stronger than the DMV suggestion alone?
* Which write-heavy workload could make the index harmful?
* How would you validate benefit without changing production first?

## Success Criteria Notes

* Be strict that existing indexes are analyzed first.
* Accept different included-column choices when tradeoffs are explained.
* Do not accept implementation through another connector or SQL client.

## Solution

Run:

```sql
:r Student/Resources/sql-server-mcp/workloads/02_missing_index.sql
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
by `sales.usp_GetProductSalesSummary`, but the grading focus is the evidence
chain and tradeoff analysis.


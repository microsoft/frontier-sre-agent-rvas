[< Previous Challenge](./Challenge-06.md) — **[Home](../../README.md)** — [Next Challenge >](./Challenge-08.md)

# Challenge 07 — Investigate Parameter Sensitivity

> **Capabilities added in this challenge**: Data Skew · Plan History · Runtime Distribution

## Introduction

The same procedure can behave well for one parameter and poorly for another.
That variation might come from parameter sensitivity, data skew, changing
workload volume, stale statistics, or a separate plan change.

Your agent must compare distributions and alternatives before it attributes
the observed behavior to parameter sensitivity.

## Description

Generate the low-activity and high-activity customer cases with
`workloads/03_parameter_sensitivity.sql`, then use the DBA agent to:

* Describe the customer activity skew with bounded evidence
* Compare Query Store runtime distributions, execution counts, and plan history
* Determine whether multiple plans or materially different estimates exist
* Evaluate parameter sensitivity alongside competing explanations
* State the evidence required before selecting a mitigation
* Recommend a controlled validation approach without forcing a plan or changing
  database configuration

## Success Criteria

- [ ] The report demonstrates customer-level skew with bounded, non-sensitive evidence
- [ ] Query Store intervals and execution counts are compared, not only lifetime averages
- [ ] Plan and estimate differences are described when evidence exists
- [ ] At least two credible alternative explanations are considered
- [ ] No plan is forced and no Query Store, statistics, procedure, or compatibility setting changes
- [ ] **Explain to your coach** — what separates parameter sensitivity from a query that is simply more expensive for larger inputs?

## Learning Resources

* [Parameter Sensitive Plan optimization](https://learn.microsoft.com/sql/relational-databases/performance/parameter-sensitive-plan-optimization)
* [Query Store usage scenarios](https://learn.microsoft.com/sql/relational-databases/performance/query-store-usage-scenarios)
* [Query processing architecture guide](https://learn.microsoft.com/sql/relational-databases/query-processing-architecture-guide)

## Tips

* Separate data-volume differences from plan-choice differences.
* Query Store plan history can be incomplete after cleanup or capture changes.
* A mitigation recommendation must include workload segments it could harm.


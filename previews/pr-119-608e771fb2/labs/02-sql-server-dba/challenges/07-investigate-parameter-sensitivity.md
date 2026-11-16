---
title: Investigate Parameter Sensitivity
summary: Compare skewed parameter populations, plan history, and runtime distributions before claiming parameter sensitivity.
phase: Plan behavior
group: Investigations
tags:
- data skew
- plan variation
highlight: false
---

# Challenge 07 — Investigate Parameter Sensitivity

> **Capabilities added in this challenge**: Data Skew · Plan History · Runtime Distribution

## Purpose

* Compare row counts and runtime distributions across parameter values and plans.
* Conclude parameter sensitivity only when plan evidence supports it, and state when it doesn't.
* Expected time: 40-55 minutes.

## Introduction

The same procedure can behave well for one parameter and poorly for another.
That variation might come from parameter sensitivity, data skew, changing
workload volume, stale statistics, or a separate plan change.

Make your agent compare distributions and alternatives before it blames
parameter sensitivity.

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

### Solution steps

Run the workload several times:

```sql
:r labs/02-sql-server-dba/resources/sql-server-mcp/workloads/03_parameter_sensitivity.sql
GO
:r labs/02-sql-server-dba/resources/sql-server-mcp/workloads/03_parameter_sensitivity.sql
GO
```

Then use:

```text
Investigate parameter-sensitive behavior in
sales.usp_GetCustomerOrderHistory. Compare bounded customer activity skew,
Query Store runtime distributions, execution counts, plan history, and
estimated rows. Separate demonstrated skew from demonstrated plan sensitivity,
consider alternative explanations, and describe a controlled validation plan.
Do not force a plan or change database state.
```

## Success Criteria

- [ ] The report demonstrates customer-level skew with bounded, non-sensitive evidence
- [ ] Query Store intervals and execution counts are compared, not only lifetime averages
- [ ] Plan and estimate differences are described when evidence exists
- [ ] At least two credible alternative explanations are considered
- [ ] No plan is forced and no Query Store, statistics, procedure, or compatibility setting changes
- [ ] **Explain in your own words** (two or three written sentences) — what separates parameter sensitivity from a query that is simply more expensive for larger inputs?

## Learning Resources

* [Parameter Sensitive Plan optimization](https://learn.microsoft.com/sql/relational-databases/performance/parameter-sensitive-plan-optimization)
* [Query Store usage scenarios](https://learn.microsoft.com/sql/relational-databases/performance/query-store-usage-scenarios)
* [Query processing architecture guide](https://learn.microsoft.com/sql/relational-databases/query-processing-architecture-guide)

## Tips

* Separate data-volume differences from plan-choice differences.
* Query Store plan history can be incomplete after cleanup or capture changes.
* A mitigation recommendation must include workload segments it could harm.

## Hints and notes

> Hidden until you click. Expand a section only when you want it.

<details>
<summary><strong>Background</strong></summary>

* One reusable plan can fit different parameter values unevenly.
* Larger inputs can cost more even when the plan is appropriate.
* Parameter sensitivity needs plan, estimate, and runtime-distribution evidence.
* Statistics, workload shifts, and cache history are competing explanations.
* Mitigations can help one workload segment and harm another.

</details>

<details>
<summary><strong>Expected Output</strong></summary>

* Low-activity and high-activity customer executions are captured.
* Data skew and runtime distributions are described separately.
* Plan history and estimates are compared when available.
* Alternative explanations remain visible.
* No plan, statistics, procedure, or compatibility setting changes.

</details>

<details>
<summary><strong>Common Issues and Hints</strong></summary>

* **Symptom:** Only one plan is retained. **Fix:** accept the limitation and check whether you distinguish skew from proven plan sensitivity.
* **Symptom:** The agent calls larger-result cost a regression. **Fix:** require equivalent parameter segments or normalized comparisons.
* **Symptom:** The report ignores execution count. **Fix:** request per-parameter or interval distributions rather than one lifetime average.
* **Symptom:** The agent proposes forcing a plan immediately. **Fix:** require controlled replay and workload-segment risk analysis first.

</details>

<details>
<summary><strong>Debrief Discussion Guide</strong></summary>

* Which evidence proved skew, and which evidence would prove plan sensitivity?
* Why might one plan be acceptable despite different runtimes?
* Which mitigation has the widest blast radius?

</details>

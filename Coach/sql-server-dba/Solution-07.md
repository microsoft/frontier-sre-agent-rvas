[< Previous Solution](./Solution-06.md) | **[Home](../../README.md)** | [Next Solution >](./Solution-08.md)

# Coach Guide — Challenge 07: Investigate Parameter Sensitivity

## Purpose

* Compare skewed parameter populations and plan behavior.
* Prevent premature parameter-sniffing conclusions.
* Expected time: 40-55 minutes.

## Mini-Lecture (8 min before challenge)

* One reusable plan can fit different parameter values unevenly.
* Larger inputs can cost more even when the plan is appropriate.
* Parameter sensitivity needs plan, estimate, and runtime-distribution evidence.
* Statistics, workload shifts, and cache history are competing explanations.
* Mitigations can help one workload segment and harm another.

## Expected Student Output

* Low-activity and high-activity customer executions are captured.
* Data skew and runtime distributions are described separately.
* Plan history and estimates are compared when available.
* Alternative explanations remain visible.
* No plan, statistics, procedure, or compatibility setting changes.

## Common Issues and Hints

* **Symptom:** Only one plan is retained. **Fix:** accept the limitation and grade whether the student distinguishes skew from proven plan sensitivity.
* **Symptom:** The agent calls larger-result cost a regression. **Fix:** require equivalent parameter segments or normalized comparisons.
* **Symptom:** The report ignores execution count. **Fix:** request per-parameter or interval distributions rather than one lifetime average.
* **Symptom:** The agent proposes forcing a plan immediately. **Fix:** require controlled replay and workload-segment risk analysis first.

## Debrief Discussion Guide

* Which evidence proved skew, and which evidence would prove plan sensitivity?
* Why might one plan be acceptable despite different runtimes?
* Which mitigation has the widest blast radius?

## Success Criteria Notes

* Be strict on the distinction between skew and proven parameter sensitivity.
* Accept an inconclusive finding when Query Store retains insufficient plans.
* Reward explicit missing-evidence statements.

## Solution

Run the workload several times:

```sql
:r Student/Resources/sql-server-mcp/workloads/03_parameter_sensitivity.sql
GO
:r Student/Resources/sql-server-mcp/workloads/03_parameter_sensitivity.sql
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


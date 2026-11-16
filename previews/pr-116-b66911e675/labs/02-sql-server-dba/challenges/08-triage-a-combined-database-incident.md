---
title: Triage a Combined Database Incident
summary: Correlate concurrent signals, rank findings by demonstrated impact, preserve alternative explanations, and deliver a decision-ready read-only handoff.
phase: Incident room
group: Investigations
tags:
- evidence ranking
- handoff
- safety
highlight: false
---

# Challenge 08 — Triage a Combined Database Incident

> **Capabilities added in this challenge**: Evidence Correlation · Impact Ranking · Operational Handoff

## Purpose

* Produce an incident handoff in which every finding traces to timestamped current or historical evidence.
* Rank simultaneous signals by demonstrated impact and list the missing evidence for each.
* Expected time: 60-75 minutes.

## Introduction

Real incidents rarely present one clean signal. A blocked transaction, an
inefficient query, and an unusual parameter can appear at the same time, but
only some of them may explain user impact.

In this exercise you run an evidence-led review that ranks findings, keeps
uncertainty visible, and produces a safe handoff without changing the database.

## Description

Start the combined incident workload yourself. Give the DBA agent a bounded
time window and require it to:

* Confirm target, engine, database, permissions, and evidence freshness
* Correlate current requests, waits, blocking, Query Store, object metadata,
  existing indexes, and estimated plans
* Rank findings by demonstrated impact rather than visual severity
* Separate observations, hypotheses, alternative explanations, and missing
  evidence
* Recommend immediate observation steps, owner-specific follow-up, and safe
  validation plans
* Produce an executive summary and a detailed technical handoff
* Confirm explicitly that it made no database changes

### Solution steps

Seed historical evidence:

```sql
:r labs/02-sql-server-dba/resources/sql-server-mcp/workloads/01_capture_baseline.sql
GO
:r labs/02-sql-server-dba/resources/sql-server-mcp/workloads/02_missing_index.sql
GO
:r labs/02-sql-server-dba/resources/sql-server-mcp/workloads/03_parameter_sensitivity.sql
GO
```

Then start the blocking scripts in separate sessions as described in
[challenge 04](04-trace-a-blocking-chain.md).

Use this incident prompt:

```text
Triage database performance concerns during the last 30 minutes. Confirm the
target and evidence freshness, then correlate current requests, waits,
blocking, Query Store, object metadata, existing indexes, and estimated plans.
Rank findings by demonstrated impact. Separate observations, hypotheses,
alternatives, and missing evidence. Produce an executive summary and technical
handoff with owner, risk, validation, and rollback considerations. Apply no
database changes.
```

Active blocking will normally rank highest while it persists. Query-shape,
index, or parameter evidence may rank next depending on captured impact. Do
not enforce that ordering after the blocking transaction has ended.

## Success Criteria

- [ ] The report states the UTC incident and observation windows
- [ ] Findings are ranked by demonstrated impact with native evidence for each rank
- [ ] Current-state signals are not misrepresented as historical trends
- [ ] Alternative explanations and missing evidence are visible in the handoff
- [ ] Recommendations identify owner, risk, validation, and rollback considerations without applying changes
- [ ] The executive summary and technical handoff remain consistent
- [ ] **Explain in your own words** (two or three written sentences) — how did you decide which simultaneous signal deserved the highest operational priority?

## Learning Resources

* [Monitor and tune for performance](https://learn.microsoft.com/sql/relational-databases/performance/monitor-and-tune-for-performance)
* [SQL Server performance monitoring and tuning tools](https://learn.microsoft.com/sql/relational-databases/performance/performance-monitoring-and-tuning-tools)
* [Azure Well-Architected Framework reliability design principles](https://learn.microsoft.com/azure/well-architected/reliability/principles)
* [Incident response overview](https://learn.microsoft.com/security/operations/incident-response-overview)

## Tips

* Start with impact and time alignment, not the longest list of warnings.
* A signal can be real and still be unrelated to the incident.
* Preserve refusal and permission failures as evidence rather than routing
  around them.

## Hints and notes

> Hidden until you click. Expand a section only when you want it.

<details>
<summary><strong>Background</strong></summary>

* Time alignment and user impact come before the number of warnings.
* Current requests, Query Store, catalog metadata, and plans have different
  scopes and lifetimes.
* A real finding can be unrelated to the incident.
* Executive summaries should remain traceable to technical evidence.
* Read-only recommendations still need owners, risk, validation, and rollback.

</details>

<details>
<summary><strong>Expected Output</strong></summary>

* UTC incident and observation windows are explicit.
* Active blocking and historical query issues are correctly scoped.
* Findings are ranked with evidence and alternatives.
* The executive summary agrees with the technical handoff.
* The report confirms no database changes.

</details>

<details>
<summary><strong>Common Issues and Hints</strong></summary>

* **Symptom:** The agent ranks the missing-index warning above active blocking without impact evidence. **Fix:** require time-aligned user impact and current wait duration for the ranking.
* **Symptom:** Historical Query Store data is presented as current activity. **Fix:** label every finding with source type and observation interval.
* **Symptom:** The report contains many facts but no decision. **Fix:** require ranked findings, immediate observation steps, owner, and next validation.
* **Symptom:** The chain expires during the report. **Fix:** preserve captured timestamps and state that current evidence is no longer observable.
* **Symptom:** The executive summary overstates causality. **Fix:** trace each sentence back to a technical finding and downgrade unsupported claims.

</details>

<details>
<summary><strong>Debrief Discussion Guide</strong></summary>

* Which finding was most urgent, and which was most durable?
* What changed when current and historical evidence were separated?
* Which recommendation should be validated first, and by whom?

</details>

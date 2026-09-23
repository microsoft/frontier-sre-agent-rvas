[< Previous Solution](./Solution-07.md) | **[Home](../../README.md)**

# Coach Guide — Challenge 08: Triage a Combined Database Incident

## Purpose

* Synthesize current and historical SQL evidence into an incident handoff.
* Rank simultaneous signals by demonstrated impact while preserving uncertainty.
* Expected time: 60-75 minutes.

## Mini-Lecture (10 min before challenge)

* Time alignment and user impact come before the number of warnings.
* Current requests, Query Store, catalog metadata, and plans have different
  scopes and lifetimes.
* A real finding can be unrelated to the incident.
* Executive summaries should remain traceable to technical evidence.
* Read-only recommendations still need owners, risk, validation, and rollback.

## Expected Student Output

* UTC incident and observation windows are explicit.
* Active blocking and historical query issues are correctly scoped.
* Findings are ranked with evidence and alternatives.
* The executive summary agrees with the technical handoff.
* The report confirms no database changes.

## Common Issues and Hints

* **Symptom:** The agent ranks the missing-index warning above active blocking without impact evidence. **Fix:** require time-aligned user impact and current wait duration for the ranking.
* **Symptom:** Historical Query Store data is presented as current activity. **Fix:** label every finding with source type and observation interval.
* **Symptom:** The report contains many facts but no decision. **Fix:** require ranked findings, immediate observation steps, owner, and next validation.
* **Symptom:** The chain expires during the report. **Fix:** preserve captured timestamps and state that current evidence is no longer observable.
* **Symptom:** The executive summary overstates causality. **Fix:** trace each sentence back to a technical finding and downgrade unsupported claims.

## Debrief Discussion Guide

* Which finding was most urgent, and which was most durable?
* What changed when current and historical evidence were separated?
* Which recommendation should be validated first, and by whom?

## Success Criteria Notes

* Be strict on time scope, evidence ranking, and read-only behavior.
* Accept different ranking when students justify demonstrated impact.
* Do not require a single root cause when evidence supports multiple
  contributors.

## Solution

Seed historical evidence:

```sql
:r Student/Resources/sql-server-mcp/workloads/01_capture_baseline.sql
GO
:r Student/Resources/sql-server-mcp/workloads/02_missing_index.sql
GO
:r Student/Resources/sql-server-mcp/workloads/03_parameter_sensitivity.sql
GO
```

Then start the blocking scripts in separate sessions as described in
[Solution 04](./Solution-04.md).

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


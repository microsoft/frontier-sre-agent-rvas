[< Previous Challenge](./Challenge-07.md) — **[Home](../../README.md)**

# Challenge 08 — Triage a Combined Database Incident

> **Capabilities added in this challenge**: Evidence Correlation · Impact Ranking · Operational Handoff

## Introduction

Real incidents rarely present one clean signal. A blocked transaction, an
inefficient query, and an unusual parameter can appear at the same time, but
only some of them may explain user impact.

This capstone asks you to run an evidence-led incident review that ranks
findings, preserves uncertainty, and produces a safe handoff without changing
the database.

## Description

Ask your coach to activate the combined incident workload. Give the DBA agent
a bounded time window and require it to:

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

## Success Criteria

- [ ] The report states the UTC incident and observation windows
- [ ] Findings are ranked by demonstrated impact with native evidence for each rank
- [ ] Current-state signals are not misrepresented as historical trends
- [ ] Alternative explanations and missing evidence are visible in the handoff
- [ ] Recommendations identify owner, risk, validation, and rollback considerations without applying changes
- [ ] The executive summary and technical handoff remain consistent
- [ ] **Explain to your coach** — how did you decide which simultaneous signal deserved the highest operational priority?

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


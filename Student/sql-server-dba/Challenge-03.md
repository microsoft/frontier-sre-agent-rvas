[< Previous Challenge](./Challenge-02.md) — **[Home](../../README.md)** — [Next Challenge >](./Challenge-04.md)

# Challenge 03 — Separate Duration from Pressure

> **Capabilities added in this challenge**: Active Requests · Wait Interpretation · False-Positive Prevention

## Introduction

A request can be old without being expensive. Maintenance delays, application
think time, and deliberate waits can all produce a large elapsed duration while
consuming almost no CPU or I/O.

In this challenge, you investigate a deterministic waiting request and prevent
the agent from turning elapsed time alone into a performance diagnosis.

## Description

Ask your coach to start a one-minute, server-side wait in a separate database
session. While it remains active, use the DBA agent to:

* Find the request and capture its UTC observation time
* Report elapsed time, status, command, wait type, blocking session, CPU,
  reads, writes, and bounded SQL text
* Determine whether it is executing, blocked, sleeping, or intentionally
  waiting
* Explain why the observation does or does not indicate database pressure
* Identify the additional evidence required before recommending action

Do not cancel the waiting request or change the session.

## Success Criteria

- [ ] The agent observes the request while it is still active
- [ ] The report distinguishes elapsed duration from CPU, reads, writes, and blocking
- [ ] The wait type and request status support the final interpretation
- [ ] The agent avoids presenting the request as a bottleneck without corroborating evidence
- [ ] The report confirms that no session was cancelled and no state changed
- [ ] **Explain to your coach** — which measurements would change your conclusion from harmless waiting to workload pressure?

## Learning Resources

* [sys.dm_exec_requests](https://learn.microsoft.com/sql/relational-databases/system-dynamic-management-views/sys-dm-exec-requests-transact-sql)
* [SQL Server wait statistics](https://learn.microsoft.com/sql/relational-databases/system-dynamic-management-views/sys-dm-os-wait-stats-transact-sql)
* [Troubleshoot slow-running queries](https://learn.microsoft.com/troubleshoot/sql/database-engine/performance/troubleshoot-slow-running-queries)

## Tips

* Point-in-time DMVs describe the observation moment, not a trend.
* A non-null wait type still needs context, duration, and impact.
* Ask the agent to list alternative explanations before naming a cause.


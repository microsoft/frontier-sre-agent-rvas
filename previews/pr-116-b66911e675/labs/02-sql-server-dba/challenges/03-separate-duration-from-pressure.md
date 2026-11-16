---
title: Separate Duration from Pressure
summary: Observe a long-running wait and prevent elapsed time from becoming a false performance diagnosis.
phase: Interpret
group: Investigations
tags:
- waits
- active requests
highlight: false
---

# Challenge 03 — Separate Duration from Pressure

> **Capabilities added in this challenge**: Active Requests · Wait Interpretation · False-Positive Prevention

## Purpose

* Show with CPU, reads, writes, and wait type that a long-running request is not under pressure.
* Name the extra evidence you would need before recommending action on a waiting request.
* Expected time: 25-35 minutes.

## Introduction

A request can be old without being expensive. Maintenance delays, application
think time, and deliberate waits can all produce a long elapsed time while
using almost no CPU or I/O.

You investigate a deterministic waiting request and stop the agent from turning
elapsed time alone into a performance diagnosis.

## Description

Start a two-minute, server-side wait in a separate database session. While it
is active, use the DBA agent to:

* Find the request and capture its UTC observation time
* Report elapsed time, status, command, wait type, blocking session, CPU,
  reads, writes, and bounded SQL text
* Determine whether it is executing, blocked, sleeping, or intentionally
  waiting
* Explain why the observation does or does not indicate database pressure
* Identify the additional evidence required before recommending action

Do not cancel the waiting request or change the session.

### Solution steps

Start this in a separate SQL session:

```sql
SELECT
    @@SPID AS WaitingSessionId,
    SYSUTCDATETIME() AS WaitStartedAtUtc;

WAITFOR DELAY '00:02:00';

SELECT SYSUTCDATETIME() AS WaitCompletedAtUtc;
```

Prompt the agent while `WAITFOR` is active:

```text
Find currently long-running requests. For each, report the UTC observation
time, elapsed time, status, command, wait type, blocking session, CPU, reads,
writes, and bounded SQL text. Distinguish active pressure from a request that
is merely waiting. Do not cancel any request.
```

The expected conclusion is that the request is intentionally waiting and does
not, by itself, demonstrate CPU, I/O, or blocking pressure.

## Success Criteria

- [ ] The agent observes the request while it is still active
- [ ] The report distinguishes elapsed duration from CPU, reads, writes, and blocking
- [ ] The wait type and request status support the final interpretation
- [ ] The agent avoids presenting the request as a bottleneck without corroborating evidence
- [ ] The report confirms that no session was cancelled and no state changed
- [ ] **Explain in your own words** (two or three written sentences) — which measurements would change your conclusion from harmless waiting to workload pressure?

## Learning Resources

* [sys.dm_exec_requests](https://learn.microsoft.com/sql/relational-databases/system-dynamic-management-views/sys-dm-exec-requests-transact-sql)
* [SQL Server wait statistics](https://learn.microsoft.com/sql/relational-databases/system-dynamic-management-views/sys-dm-os-wait-stats-transact-sql)
* [Troubleshoot slow-running queries](https://learn.microsoft.com/troubleshoot/sql/database-engine/performance/troubleshoot-slow-running-queries)

## Tips

* Point-in-time DMVs describe the observation moment, not a trend.
* A non-null wait type still needs context, duration, and impact.
* Ask the agent to list alternative explanations before naming a cause.

## Hints and notes

> Hidden until you click. Expand a section only when you want it.

<details>
<summary><strong>Background</strong></summary>

* Elapsed time includes execution, scheduling, blocking, and intentional waits.
* CPU, reads, writes, status, command, wait type, and blocker provide context.
* A current DMV sample expires and cannot establish a trend.
* Wait categories describe where time accumulated, not root cause by themselves.
* An accurate "no demonstrated pressure" finding is operationally useful.

</details>

<details>
<summary><strong>Expected Output</strong></summary>

* The waiting session is captured before it completes.
* The report shows low work despite increasing elapsed duration.
* Wait type and status support an intentional-wait interpretation.
* The agent requests corroborating evidence before suggesting action.
* No request is cancelled.

</details>

<details>
<summary><strong>Common Issues and Hints</strong></summary>

* **Symptom:** The wait completes before investigation. **Fix:** restart the two-minute wait and submit the agent prompt immediately.
* **Symptom:** The agent calls it a long-running query problem. **Fix:** require side-by-side elapsed, CPU, reads, writes, status, and blocking values.
* **Symptom:** SQL text is unavailable. **Fix:** accept the DMV evidence and record the permission or timing limitation instead of widening access.
* **Symptom:** The report treats one wait as historical pressure. **Fix:** ask which retained source supports that trend; current requests do not.

</details>

<details>
<summary><strong>Debrief Discussion Guide</strong></summary>

* Which metric most strongly contradicted the initial "slow query" label?
* What would blocking-session evidence change?
* When should a waiting request still be escalated even if it consumes little
  CPU?

</details>

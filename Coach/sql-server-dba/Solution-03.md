[< Previous Solution](./Solution-02.md) | **[Home](../../README.md)** | [Next Solution >](./Solution-04.md)

# Coach Guide — Challenge 03: Separate Duration from Pressure

## Purpose

* Prevent elapsed time from being treated as proof of expensive execution.
* Practice point-in-time request and wait interpretation.
* Expected time: 25-35 minutes.

## Mini-Lecture (6 min before challenge)

* Elapsed time includes execution, scheduling, blocking, and intentional waits.
* CPU, reads, writes, status, command, wait type, and blocker provide context.
* A current DMV sample expires and cannot establish a trend.
* Wait categories describe where time accumulated, not root cause by themselves.
* An accurate "no demonstrated pressure" finding is operationally useful.

## Expected Student Output

* The waiting session is captured before it completes.
* The report shows low work despite increasing elapsed duration.
* Wait type and status support an intentional-wait interpretation.
* The agent requests corroborating evidence before suggesting action.
* No request is cancelled.

## Common Issues and Hints

* **Symptom:** The wait completes before investigation. **Fix:** restart the two-minute wait and have the student submit the agent prompt immediately.
* **Symptom:** The agent calls it a long-running query problem. **Fix:** require side-by-side elapsed, CPU, reads, writes, status, and blocking values.
* **Symptom:** SQL text is unavailable. **Fix:** accept the DMV evidence and record the permission or timing limitation instead of widening access.
* **Symptom:** The report treats one wait as historical pressure. **Fix:** ask which retained source supports that trend; current requests do not.

## Debrief Discussion Guide

* Which metric most strongly contradicted the initial "slow query" label?
* What would blocking-session evidence change?
* When should a waiting request still be escalated even if it consumes little
  CPU?

## Success Criteria Notes

* Be strict that the request is observed live.
* Accept platform-specific wait-type names when the interpretation is correct.
* Accept missing SQL text when the agent reports the limitation explicitly.

## Solution

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


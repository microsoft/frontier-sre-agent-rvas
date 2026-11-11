[< Previous Solution](./Solution-03.md) | **[Home](../../README.md)** | [Next Solution >](./Solution-05.md)

# Coach Guide — Challenge 04: Trace a Blocking Chain

## Purpose

* Identify the head blocker and resource conflict with native evidence.
* Preserve transaction state while explaining operational impact.
* Expected time: 30-40 minutes.

## Mini-Lecture (7 min before challenge)

* The blocked statement is often the victim rather than the cause.
* A blocking chain combines request, session, lock, transaction, and SQL-text
  evidence.
* Normal short blocking becomes harmful through duration and business impact.
* Killing a session can trigger rollback and amplify impact.
* The lab transactions roll back; the agent must not intervene.

## Expected Student Output

* Session A is identified as head blocker.
* Session B is identified as waiting behind A.
* Wait resource, lock context, transaction age, and SQL text are reported.
* The explanation connects the row to inventory balance activity.
* Both sessions finish without persistent changes.

## Common Issues and Hints

* **Symptom:** Session B runs before the lock is held. **Fix:** start session A, wait for its first result, then start session B.
* **Symptom:** The chain disappears before the agent responds. **Fix:** restart both scripts and treat the first disappearance as expired point-in-time evidence.
* **Symptom:** The agent recommends `KILL`. **Fix:** reinforce the read-only boundary and ask for rollback risk and application-owner context instead.
* **Symptom:** Lock metadata is permission-filtered. **Fix:** use available request and transaction evidence and report the permission limitation.

## Debrief Discussion Guide

* Why is the head blocker not automatically the session to terminate?
* Which application behavior could leave the same lock open indefinitely?
* What retained evidence would help after the blocking chain disappears?

## Success Criteria Notes

* Be strict on head-blocker direction and non-intervention.
* Accept platform-specific lock-resource formatting.
* Allow the scripts to complete naturally if the student captured enough
  evidence before expiry.

## Solution

Open two SQL sessions against `stockOrders`.

Session A:

```sql
:r Student/Resources/sql-server-mcp/workloads/05_blocking_session_a.sql
```

After session A reports that it holds the transaction, start session B:

```sql
:r Student/Resources/sql-server-mcp/workloads/06_blocking_session_b.sql
```

Use:

```text
Using only sqlserver-mcp, inspect current blocking. Build the chain, identify
the head blocker and blocked request, and report wait resource, wait type,
transaction age, SQL text, and likely business impact. Do not terminate a
session or change transaction state. Confirm when the evidence expires.
```


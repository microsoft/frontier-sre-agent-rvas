---
title: Trace a Blocking Chain
summary: Identify the head blocker, blocked request, wait resource, and transaction age without terminating either session.
phase: Concurrency
group: Investigations
tags:
- locks
- transactions
highlight: false
---

# Challenge 04 — Trace a Blocking Chain

> **Capabilities added in this challenge**: Blocking Chains · Lock Evidence · Transaction Context

## Purpose

* Identify the head blocker, blocked session, and contested resource, citing session IDs and the wait resource.
* Assess operational impact and propose safe follow-up observations without ending any session.
* Expected time: 30-40 minutes.

## Introduction

Blocking is normal in a lock-based database. It becomes an incident when a
session holds a conflicting lock long enough to delay important work.

You create a reversible two-session chain. The agent must find the head
blocker, explain the resource conflict, and estimate impact without
terminating sessions or changing transaction state.

## Description

Use two approved SQL client sessions with
`workloads/05_blocking_session_a.sql` and
`workloads/06_blocking_session_b.sql`. While session B is waiting, ask the DBA
agent to:

* Construct the observed blocking chain
* Identify the head blocker and blocked session
* Report the waiting resource, request state, lock context, and transaction age
* Connect the locked row to the relevant inventory business concept
* Explain whether the chain is transient, harmful, or still uncertain
* Recommend safe follow-up observations rather than killing a session

### Solution steps

Open two SQL sessions against `stockOrders`.

Session A:

```sql
:r labs/02-sql-server-dba/resources/sql-server-mcp/workloads/05_blocking_session_a.sql
```

After session A reports that it holds the transaction, start session B:

```sql
:r labs/02-sql-server-dba/resources/sql-server-mcp/workloads/06_blocking_session_b.sql
```

Use:

```text
Using only sqlserver-mcp, inspect current blocking. Build the chain, identify
the head blocker and blocked request, and report wait resource, wait type,
transaction age, SQL text, and likely business impact. Do not terminate a
session or change transaction state. Confirm when the evidence expires.
```

## Success Criteria

- [ ] The agent identifies session A as the head blocker and session B as blocked
- [ ] The report includes the observed wait resource, wait type, and transaction age
- [ ] The explanation connects the lock conflict to the affected inventory operation
- [ ] The agent does not terminate either session or change isolation, locks, or transaction state
- [ ] Both workload sessions complete or roll back without leaving sample data changed
- [ ] **Explain in your own words** (two or three written sentences) — why is identifying the head blocker only the start of a safe blocking investigation?

## Learning Resources

* [Understand and resolve SQL Server blocking](https://learn.microsoft.com/troubleshoot/sql/database-engine/performance/understand-resolve-blocking)
* [SQL Server transaction locking and row versioning](https://learn.microsoft.com/sql/relational-databases/sql-server-transaction-locking-and-row-versioning-guide)
* [sys.dm_tran_locks](https://learn.microsoft.com/sql/relational-databases/system-dynamic-management-views/sys-dm-tran-locks-transact-sql)

## Tips

* Start session A before session B and investigate while both are active.
* Transaction age and application behavior matter as much as the blocked SQL.
* If the chain disappears, report that the point-in-time evidence expired.

## Hints and notes

> Hidden until you click. Expand a section only when you want it.

<details>
<summary><strong>Background</strong></summary>

* The blocked statement is often the victim rather than the cause.
* A blocking chain combines request, session, lock, transaction, and SQL-text
  evidence.
* Normal short blocking becomes harmful through duration and business impact.
* Killing a session can trigger rollback and amplify impact.
* The lab transactions roll back; the agent must not intervene.

</details>

<details>
<summary><strong>Expected Output</strong></summary>

* Session A is identified as head blocker.
* Session B is identified as waiting behind A.
* Wait resource, lock context, transaction age, and SQL text are reported.
* The explanation connects the row to inventory balance activity.
* Both sessions finish without persistent changes.

</details>

<details>
<summary><strong>Common Issues and Hints</strong></summary>

* **Symptom:** Session B runs before the lock is held. **Fix:** start session A, wait for its first result, then start session B.
* **Symptom:** The chain disappears before the agent responds. **Fix:** restart both scripts and treat the first disappearance as expired point-in-time evidence.
* **Symptom:** The agent recommends `KILL`. **Fix:** reinforce the read-only boundary and ask for rollback risk and application-owner context instead.
* **Symptom:** Lock metadata is permission-filtered. **Fix:** use available request and transaction evidence and report the permission limitation.

</details>

<details>
<summary><strong>Debrief Discussion Guide</strong></summary>

* Why is the head blocker not automatically the session to terminate?
* Which application behavior could leave the same lock open indefinitely?
* What retained evidence would help after the blocking chain disappears?

</details>

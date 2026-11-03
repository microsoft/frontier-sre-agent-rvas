[< Previous Challenge](./Challenge-03.md) — **[Home](../../README.md)** — [Next Challenge >](./Challenge-05.md)

# Challenge 04 — Trace a Blocking Chain

> **Capabilities added in this challenge**: Blocking Chains · Lock Evidence · Transaction Context

## Introduction

Blocking is normal in a lock-based database. It becomes an incident when a
session holds a conflicting lock long enough to delay important work.

This challenge gives you a reversible two-session chain. Your agent must locate
the head blocker, explain the resource conflict, and estimate impact without
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

## Success Criteria

- [ ] The agent identifies session A as the head blocker and session B as blocked
- [ ] The report includes the observed wait resource, wait type, and transaction age
- [ ] The explanation connects the lock conflict to the affected inventory operation
- [ ] The agent does not terminate either session or change isolation, locks, or transaction state
- [ ] Both workload sessions complete or roll back without leaving sample data changed
- [ ] **Explain to your coach** — why is identifying the head blocker only the start of a safe blocking investigation?

## Learning Resources

* [Understand and resolve SQL Server blocking](https://learn.microsoft.com/troubleshoot/sql/database-engine/performance/understand-resolve-blocking)
* [SQL Server transaction locking and row versioning](https://learn.microsoft.com/sql/relational-databases/sql-server-transaction-locking-and-row-versioning-guide)
* [sys.dm_tran_locks](https://learn.microsoft.com/sql/relational-databases/system-dynamic-management-views/sys-dm-tran-locks-transact-sql)

## Tips

* Start session A before session B and investigate while both are active.
* Transaction age and application behavior matter as much as the blocked SQL.
* If the chain disappears, report that the point-in-time evidence expired.


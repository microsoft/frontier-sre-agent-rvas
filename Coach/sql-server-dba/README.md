# Coach Guide — Azure SRE Agent SQL Server DBA Track

> **COACHES ONLY — Do not share with participants.**

This track teaches evidence-led, read-only SQL Server investigation through a
hardened MCP boundary. Coaches prepare deterministic workload evidence and
help students distinguish observation, inference, recommendation, and action.

## Solution Index

| Challenge | Title | Solution File |
|---|---|---|
| 00 | Deploy the Read-Only DBA Path | [Solution-00.md](./Solution-00.md) |
| 01 | Orient to the Database | [Solution-01.md](./Solution-01.md) |
| 02 | Establish a Query Store Baseline | [Solution-02.md](./Solution-02.md) |
| 03 | Separate Duration from Pressure | [Solution-03.md](./Solution-03.md) |
| 04 | Trace a Blocking Chain | [Solution-04.md](./Solution-04.md) |
| 05 | Build an Evidence-Based Index Case | [Solution-05.md](./Solution-05.md) |
| 06 | Diagnose Query Shape Problems | [Solution-06.md](./Solution-06.md) |
| 07 | Investigate Parameter Sensitivity | [Solution-07.md](./Solution-07.md) |
| 08 | Triage a Combined Database Incident | [Solution-08.md](./Solution-08.md) |

## Azure Requirements

| Resource | Requirement |
|---|---|
| Azure subscription | Contributor for lab hosting; permission to assign `AcrPull` and the approved MCP API role |
| Azure SRE Agent | Running agent with custom connector, skill, and custom-agent authoring access |
| Container hosting | Azure Container Apps or equivalent authenticated HTTPS container host |
| Container registry | Azure Container Registry with managed-identity image pull |
| Database | Dedicated `stockOrders` workshop database on Azure SQL, Managed Instance, or a supported SQL Server target |
| Identity | User-assigned managed identity mapped only to `sre_dba_observer` |
| Network | DNS and TLS connectivity from the MCP host to the SQL endpoint |
| Local tools | Azure CLI, approved SQL client, .NET 10 SDK, and optional Docker |

## Suggested Agenda

Times include the coach mini-lecture and hands-on work. Total core track:
approximately 7 hours.

### Full-day event

| Block | Challenges | Est. Time | Focus |
|---|---|---:|---|
| Morning 1 | 00 | 90 min | Trust path, deployment, and validation |
| Morning 2 | 01-02 | 90 min | Schema orientation and Query Store baseline |
| Afternoon 1 | 03-04 | 75 min | Wait interpretation and blocking |
| Afternoon 2 | 05-07 | 150 min | Index, query shape, and parameter behavior |
| Close | 08 | 75 min | Combined incident and debrief |

### Focused half-day event

Pre-deploy Challenge 00 and pre-seed the baseline. Run Challenges 01, 03, 04,
05, and 08 for a four-hour evidence and incident-response path.

## Coaching Philosophy

1. **Protect the trust boundary.** Never solve an MCP permission or connector
   problem by giving students another database access path.
2. **Ask for evidence, not labels.** When a team says "blocking," "missing
   index," or "parameter sniffing," ask which native evidence proves it.
3. **Keep time scopes visible.** Require UTC observation windows and distinguish
   current DMVs from retained Query Store history.
4. **Reward inconclusive findings.** "Insufficient evidence" is better than a
   confident but fabricated root cause.
5. **Do not apply tuning changes.** The lab teaches investigation and
   recommendation. Database owners retain approval and execution.
6. **Timebox ephemeral scenarios.** Restart waiting or blocking workloads when
   evidence expires instead of widening permissions.

## Per-Challenge Coach Guide

| Ch | Title | Key Concepts | Known Blockers & Hints | Est. Time | When to Intervene |
|---|---|---|---|---:|---|
| 00 | Deploy the Read-Only DBA Path | Identity chain, MCP transport, least privilege, refusal | Entra user resolution; wrong connector namespace; missing `SHOWPLAN` | **60-90 min** | After 30 min if health, connector, and SQL identity failures are not separated |
| 01 | Orient to the Database | Catalog views, domains, declared relationships, inference | Naming-based relationships presented as facts | **35-45 min** | When the ER diagram includes links without foreign-key evidence |
| 02 | Establish a Query Store Baseline | Capture state, intervals, averages, totals | Empty capture interval; `READ_ONLY` Query Store | **35-50 min** | After two workload runs produce no retained evidence |
| 03 | Separate Duration from Pressure | Active requests, waits, elapsed vs. work | Wait completes before observation; false slow-query label | **25-35 min** | When elapsed time is the only cited metric |
| 04 | Trace a Blocking Chain | Head blocker, locks, transaction age, rollback risk | Session order reversed; chain expires | **30-40 min** | When students propose terminating a session |
| 05 | Build an Evidence-Based Index Case | Query Store, index overlap, estimated plans, write cost | DMV suggestion repeated without design comparison | **40-55 min** | When an index is proposed before current indexes are inspected |
| 06 | Diagnose Query Shape Problems | SARGability, conversion direction, access paths | Query-shape issues mislabeled as missing indexes | **35-50 min** | When the two supplied defects are not analyzed separately |
| 07 | Investigate Parameter Sensitivity | Skew, distributions, plans, alternatives | One retained plan; skew presented as proof | **40-55 min** | When the report claims parameter sensitivity without plan evidence |
| 08 | Triage a Combined Database Incident | Time alignment, impact ranking, handoff | Historical and current evidence blended | **60-75 min** | When the summary cannot be traced to timestamped evidence |

Detailed commands and expected outputs are in the solution files. Share
observed output and error messages with students, not the solution sequence.

## Coach Preparation

1. Complete the
   [SQL Server MCP deployment guide](../../Student/Resources/sql-server-mcp/README.md).
2. Verify the refusal prompt in Solution 00.
3. Run the baseline workload and confirm Query Store capture.
4. Rehearse the two-session wait and blocking scenarios.
5. Reset the sample database when a previous event changed its intended state.

## Cleanup

Delete the dedicated Azure resource group:

```bash
az group delete --name "<resource-group>" --yes --no-wait
```

If the database is hosted separately, run
`Student/Resources/sql-server-mcp/sql/99_teardown.sql` in the workshop database.


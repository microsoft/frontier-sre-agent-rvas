# SQL Server DBA lab

Ten challenges use a dedicated, read-only SQL Server MCP server for database
investigation. You deploy it securely, explore the schema, diagnose repeatable
performance incidents, and build your own DBA agent.

**Capability progression:** MCP trust boundary → Schema discovery → Query Store → Wait interpretation → Blocking → Index analysis → SARGability → Parameter sensitivity → Incident triage → Custom DBA agent capstone

## Challenges

| # | Challenge | Capability |
|---|-----------|------------|
| [00](challenges/00-deploy-the-read-only-dba-path.md) | Deploy the Read-Only DBA Path | Managed identity · Least privilege · SQL Server MCP |
| [01](challenges/01-orient-to-the-database.md) | Orient to the Database | Business domains · Schema · Relationships |
| [02](challenges/02-establish-a-query-store-baseline.md) | Establish a Query Store Baseline | Historical evidence · Observation windows |
| [03](challenges/03-separate-duration-from-pressure.md) | Separate Duration from Pressure | Active requests · Wait interpretation |
| [04](challenges/04-trace-a-blocking-chain.md) | Trace a Blocking Chain | Head blocker · Wait resource · Transaction age |
| [05](challenges/05-build-an-evidence-based-index-case.md) | Build an Evidence-Based Index Case | Query Store · Existing indexes · Estimated plans |
| [06](challenges/06-diagnose-query-shape-problems.md) | Diagnose Query Shape Problems | SARGability · Implicit conversion |
| [07](challenges/07-investigate-parameter-sensitivity.md) | Investigate Parameter Sensitivity | Data skew · Plan variation · Runtime distribution |
| [08](challenges/08-triage-a-combined-database-incident.md) | Triage a Combined Database Incident | Evidence ranking · Alternative explanations · Handoff |
| [09](challenges/09-build-your-own-sql-server-dba-agent.md) | Build Your Own SQL Server DBA Agent | Custom agent · Investigation design · Read-only validation |

## Requirements

Run every command in Linux Bash. Check the shared [requirements and environment setup](../../README.md#requirements) first, then work through challenge 00 to deploy and run the pre-flight checks.

This track teaches evidence-led, read-only SQL Server investigation through a
hardened MCP boundary. You run deterministic workloads, collect the evidence, and
learn to distinguish observation, inference, recommendation, and action.

## Lab resources and access

| Resource | Requirement |
|---|---|
| Azure subscription | Contributor for lab hosting; permission to assign `AcrPull` and the approved MCP API role |
| Azure SRE Agent | Running agent with custom connector, skill, and custom-agent authoring access |
| Container hosting | Azure Container Apps or equivalent authenticated HTTPS container host |
| Container registry | Azure Container Registry with managed-identity image pull |
| Database | Dedicated `stockOrders` workshop database on Azure SQL, Managed Instance, or a supported SQL Server target |
| Identity | User-assigned managed identity mapped only to `sre_dba_observer` |
| Network | DNS and TLS connectivity from the MCP host to the SQL endpoint |
| Local tools | Linux Bash and shared Requirements; Azure CLI 2.62+, Container Apps extension, and approved SQL client (`sqlcmd` for command-line pre-flight). .NET 10 SDK only for local source builds/tests; Docker/registry build access for image builds |

## Suggested Agenda

Times include reading the background notes and hands-on work. The core track takes
about 8 hours; allow 75-90 more minutes for the capstone.

### Full-day plan

| Block | Challenges | Est. Time | Focus |
|---|---|---:|---|
| Morning 1 | 00 | 90 min | Trust path, deployment, and validation |
| Morning 2 | 01-02 | 90 min | Schema orientation and Query Store baseline |
| Afternoon 1 | 03-04 | 75 min | Wait interpretation and blocking |
| Afternoon 2 | 05-07 | 150 min | Index, query shape, and parameter behavior |
| Close | 08 | 75 min | Combined incident and debrief |
| Capstone | 09 | 75-90 min | Design, build, validate, and present a focused DBA agent |

### Focused half-day plan

Pre-deploy Challenge 00 and pre-seed the baseline. Run Challenges 01, 03, 04,
05, and 08 for a four-hour evidence and incident-response path. Add Challenge 09
as a 75-90 minute capstone extension.

## Working principles

1. **Protect the trust boundary.** Never solve an MCP permission or connector
   problem by giving yourself another database access path.
2. **Ask for evidence, not labels.** When you conclude "blocking," "missing
   index," or "parameter sniffing," name the native evidence that proves it.
3. **Keep time scopes visible.** Use UTC observation windows and distinguish
   current DMVs from retained Query Store history.
4. **Accept inconclusive findings.** "Insufficient evidence" is better than a
   confident but fabricated root cause.
5. **Do not apply tuning changes.** The lab teaches investigation and
   recommendation. Database owners keep approval and execution.
6. **Timebox ephemeral scenarios.** When evidence expires, restart the waiting or
   blocking workload instead of widening permissions.

## Per-challenge guide

| Ch | Title | Key Concepts | Known Blockers & Hints | Est. Time | Get Unstuck If |
|---|---|---|---|---:|---|
| 00 | Deploy the Read-Only DBA Path | Identity chain, MCP transport, least privilege, refusal | Entra user resolution; wrong connector namespace; missing `SHOWPLAN` | **60-90 min** | After 30 min if health, connector, and SQL identity failures are not separated |
| 01 | Orient to the Database | Catalog views, domains, declared relationships, inference | Naming-based relationships presented as facts | **35-45 min** | When the ER diagram includes links without foreign-key evidence |
| 02 | Establish a Query Store Baseline | Capture state, intervals, averages, totals | Empty capture interval; `READ_ONLY` Query Store | **35-50 min** | After two workload runs produce no retained evidence |
| 03 | Separate Duration from Pressure | Active requests, waits, elapsed vs. work | Wait completes before observation; false slow-query label | **25-35 min** | When elapsed time is the only cited metric |
| 04 | Trace a Blocking Chain | Head blocker, locks, transaction age, rollback risk | Session order reversed; chain expires | **30-40 min** | You propose terminating a session |
| 05 | Build an Evidence-Based Index Case | Query Store, index overlap, estimated plans, write cost | DMV suggestion repeated without design comparison | **40-55 min** | When an index is proposed before current indexes are inspected |
| 06 | Diagnose Query Shape Problems | SARGability, conversion direction, access paths | Query-shape issues mislabeled as missing indexes | **35-50 min** | When the two supplied defects are not analyzed separately |
| 07 | Investigate Parameter Sensitivity | Skew, distributions, plans, alternatives | One retained plan; skew presented as proof | **40-55 min** | When the report claims parameter sensitivity without plan evidence |
| 08 | Triage a Combined Database Incident | Time alignment, impact ranking, handoff | Historical and current evidence blended | **60-75 min** | When the summary cannot be traced to timestamped evidence |
| 09 | Build Your Own SQL Server DBA Agent | Custom agent, investigation design, safe validation | Scope too broad; evidence not repeatable; tool boundary weakened | **75-90 min** | When the scenario lacks a bounded question or a safe end-to-end test |

Each challenge contains its own solution steps and expected output.

## What you produce and how you check it

Each challenge ends with a short written explanation in your report. Only you can supply it. The other success criteria check the agent's output.

| Ch | You produce | Checked by |
|---|---|---|
| 00 | A working, health-checked trust path and a refused write prompt | Health check, connector test, refusal transcript |
| 01 | An ER diagram with only declared links, plus labelled inferences | Each link cites a constraint |
| 02 | A baseline with interval, capture state, and execution counts | Every figure states its window |
| 03 | A report separating elapsed time from CPU, I/O, and blocking | Metrics side by side, no action recommended |
| 04 | A blocking chain with head blocker and wait resource | Session IDs and resource cited, no session ended |
| 05 | An index recommendation with benefit, cost, and rejection criteria | Query Store, existing indexes, and plan correlated |
| 06 | A code-owner handoff covering two query-shape defects | Each defect has its own plan evidence |
| 07 | A parameter-sensitivity verdict with plan evidence | Distributions and plans compared, uncertainty stated |
| 08 | An incident handoff with ranked, traceable findings | Every finding has a timestamped source |
| 09 | A read-only DBA agent, its demo, and a production-readiness gap list | Out-of-scope request handled safely |

## Lab Setup

Start with [shared Requirements](../../README.md#requirements).
Confirm Codespaces entitlement/policy or a working WSL2/Linux container fallback.
Run `make preflight` from `labs/02-sql-server-dba/` after authenticating
Azure there; use `bash resources/infra/scripts/preflight.sh --local --track sql-dba`
before login. Resolve failures and
review warnings, then separately verify SQL administrator access, Entra identity
resolution, managed-identity database role membership, MCP caller authorization,
and DNS/TLS connectivity. Do not widen the read-only role to bypass blockers.

Use isolated subscriptions or names, and keep your private Terraform state until
cleanup. Deleting a Codespace does not delete its Azure resources.

1. Deploy the reference hosting and database with the
   [SRE DBA Terraform root](resources/infra/modules/sre-dba-infra/README.md)
   (`make infra` from `labs/02-sql-server-dba/`), or follow the manual
   [SQL Server MCP deployment guide](resources/sql-server-mcp/README.md).
   Either way, configure Microsoft Entra authentication on the MCP endpoint
   manually before connecting the agent.
2. Verify the refusal prompt in challenge 00.
3. Run the baseline workload and confirm Query Store capture.
4. Try the two-session wait and blocking scenarios once before the challenges that use them.
5. Reset the sample database when a previous run changed its intended state.

## Cleanup

Delete the dedicated Azure resource group:

```bash
az group delete --name "<resource-group>" --yes --no-wait
```

If the database is hosted separately, run
`labs/02-sql-server-dba/resources/sql-server-mcp/sql/99_teardown.sql` in the workshop database.

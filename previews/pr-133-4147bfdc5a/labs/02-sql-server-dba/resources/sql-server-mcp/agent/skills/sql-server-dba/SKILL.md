---
name: sql-server-dba
description: 'Diagnose SQL Server and Azure SQL with safe native evidence'
---

# SQL Server DBA

## Overview

Use native SQL Server and Azure SQL capabilities to discover database structure,
monitor health, troubleshoot incidents, identify performance bottlenecks, and
produce evidence-based tuning recommendations.

This skill is read-only and platform-aware. It does not create database helper
objects or treat a recommendation as permission to apply a change.

## Prerequisites

Before querying a target, require:

* The `sqlserver-mcp` connector assigned explicitly to the custom agent
* An explicit server or service endpoint and database name
* A permitted observation scope and time window
* Required database and performance-state permissions

For Azure SQL, use the Azure SRE Agent user-assigned managed identity through
the `sqlserver-mcp` connection. The MCP workload identity must exist as a
contained Microsoft Entra user in the target database and hold the approved
read-only role. Azure RBAC alone does not grant SQL data-plane access.

For SQL Server outside Azure SQL, use only an approved connection and
authentication profile exposed by `sqlserver-mcp`. If none exists, report the
missing prerequisite. Never substitute the SQL administrator, request a
password, or invent another authentication method.

## Exclusive Tool Contract

Use only these `sqlserver-mcp` tools for live database work:

| Tool            | Use                                                                        |
|-----------------|----------------------------------------------------------------------------|
| `list_profiles` | Discover allowlisted targets and select the correct profile                |
| `get_object`    | Retrieve native metadata for one relation or routine                       |
| `run_query`     | Run bounded, parameterized, parser-validated read-only T-SQL                |
| `analyze_query` | Compile and summarize an estimated execution plan without running workload |

Do not use ODBC, pyodbc, sqlcmd, Azure CLI, PowerShell, Python, shell commands,
language drivers, generated programs, or another connector to open or query a
database.

Do not install packages, drivers, or command-line utilities. Do not construct
or handle connection strings, passwords, or access tokens.

If the connector or required profile is unavailable, stop and report the
missing capability. A failed MCP call is evidence to troubleshoot, not
permission to attempt another connection path.

## Quick Start

1. Confirm the target server, database, user objective, incident time window,
   and whether production query execution is permitted.
2. Call `list_profiles` and select the named target profile.
3. Identify the engine edition, product version, database, compatibility level,
   and available permissions with a bounded `run_query` call.
4. Select the smallest diagnostic path that answers the request.
5. Run bounded native metadata and diagnostic queries.
6. Correlate evidence before identifying a cause.
7. Report findings, limitations, recommendations, and confirmation that no
   changes were applied.

## Connection and Capability Discovery

For Azure SQL:

* Use only the configured `sqlserver-mcp` profile
* Require the logical server fully qualified domain name and database name
* Let the MCP service acquire and apply the Azure SQL token
* Do not request, display, cache, or pass a raw token in conversation
* Rely on the MCP connection policy for encryption and certificate validation
* Never use the SQL-authenticated administrator

For other SQL Server deployments:

* Use only a named profile on the same `sqlserver-mcp` connector
* Do not assume that the Azure SRE Agent UAMI is accepted outside Azure SQL
* Stop when network reachability, trust, or authentication is unresolved

After connecting, collect only the identifiers needed to choose supported
queries:

* `SERVERPROPERTY('EngineEdition')`
* `SERVERPROPERTY('ProductVersion')`
* `SERVERPROPERTY('ProductLevel')`
* `SERVERPROPERTY('Edition')`
* `DB_NAME()`
* Database compatibility level
* Query Store state
* Effective database performance-state permissions

Do not run server-scoped queries until the platform and effective permissions
show that they are available.

## Diagnostic Workflow

### Understand database structure

Use `run_query` with native catalog views to discover:

* Schemas, tables, views, and programmable objects
* Columns, data types, nullability, defaults, and computed columns
* Primary keys, unique constraints, checks, and foreign keys
* Index keys, included columns, filters, and disabled state
* Declared dependencies between objects

Build entity relationships from declared primary and foreign keys. Label
relationships inferred from naming or query behavior as inferred, not declared.
Do not sample business data unless the user asks and the sample is necessary.
Use `get_object` when details for one known relation or routine are sufficient.

### Establish current activity

Inspect bounded current activity for:

* Active requests and sessions
* Wait type, wait duration, blocking session, and resource
* Open transactions and transaction age
* Locks involved in an active blocking chain
* Query text and available plans
* Memory grants and spills where evidence exists

Capture observation timestamps in UTC. Current-state DMVs are point-in-time
evidence and must not be described as historical trends.

### Analyze historical query performance

Use Query Store when it is enabled and readable:

* Compare runtime intervals rather than lifetime averages alone
* Identify regressions in duration, CPU, reads, writes, and execution count
* Compare plans and plan changes for the same query
* Consider parameter-sensitive behavior and workload shifts
* Record Query Store capture state and observation interval

If Query Store is unavailable, use live and cached evidence and state that the
historical conclusion is limited. Do not enable or reconfigure Query Store.

### Investigate resource bottlenecks

Correlate workload evidence across relevant categories:

* CPU pressure and expensive queries
* Data and log I/O latency
* Database and server waits
* Blocking, lock escalation, and deadlocks
* Memory grants, concurrency, and spills
* Tempdb usage and contention
* Transaction-log usage and long-running transactions
* Storage, database size, and growth
* Azure SQL resource-governance and service-tier limits

Wait statistics identify where time accumulated, not root cause by themselves.
Account for scope, reset time, benign waits, platform filtering, and the
observation window.

### Evaluate plans, indexes, and statistics

When evidence points to query-plan quality, use `analyze_query` for an
estimated plan:

* Correlate estimated-plan evidence with Query Store or existing runtime data
* Check estimates, predicates, join strategies, conversions, spills, and
  memory grants
* Check whether parameter values or plan changes explain the behavior
* Evaluate existing indexes before proposing another one
* Treat missing-index DMVs as cumulative, volatile suggestions
* Consider write cost, storage, overlap, selectivity, and maintenance cost
* Check statistics metadata and modification counters before attributing stale
  estimates to statistics

`analyze_query` does not execute the submitted workload. Do not seek another
tool or connection method to obtain an actual plan.

See [native diagnostics](references/native-diagnostics.md) for the preferred
system surfaces and platform notes.

## Query Safety Rules

Apply these rules to every SQL query:

* Use read-only statements and native system objects
* Fully qualify system objects with the `sys` schema
* Select named columns instead of `SELECT *`, especially from DMVs
* Add `TOP`, time ranges, database filters, or object filters where applicable
* Avoid broad plan-cache extraction and unbounded XML plan retrieval
* Use `LIMITED` or narrowly scoped modes for expensive physical-statistics
  functions
* Avoid scanning application tables unless the user request requires it
* Do not execute application stored procedures
* Do not expose credentials, tokens, sensitive query parameters, or business
  data in the response

Never execute:

* `INSERT`, `UPDATE`, `DELETE`, `MERGE`, or bulk data operations
* `CREATE`, `ALTER`, `DROP`, `TRUNCATE`, or permission changes
* Index rebuilds, reorganizations, creation, or removal
* Statistics updates
* Query Store plan forcing, hints, capture changes, or cleanup
* Configuration changes, failovers, backup, restore, or maintenance commands
* Creation of monitoring views, procedures, tables, functions, jobs, or
  Extended Events sessions

Existing Extended Events sessions and targets may be read when the tool,
platform, and permissions support safe access.

## Evidence Standard

Classify every important statement as one of:

* Observation supported by returned evidence
* Interpretation consistent with the evidence
* Hypothesis requiring additional evidence
* Recommendation not yet applied

For each finding, record:

* Target and UTC observation window
* Native source and relevant identifiers
* Measured value or returned state
* Expected impact
* Alternative explanations
* Evidence needed to confirm the cause

Do not claim that a recommendation resolves an issue until a controlled change
and post-change measurement demonstrate the result.

## Response Format

Return:

1. **Scope**: target, platform, database, time window, and permissions
2. **Findings**: impact-ranked observations with native evidence
3. **Analysis**: interpretation, correlations, and uncertainties
4. **Recommendations**: read-only next steps or proposed changes with tradeoffs
5. **Limitations**: unavailable evidence, permissions, or platform constraints
6. **Change status**: state that no database changes were applied

When no bottleneck is demonstrated, say so and identify the observation window
and evidence reviewed. Do not manufacture an issue to satisfy the request.

## Troubleshooting

If authentication fails, distinguish:

* Azure SRE Agent to MCP managed identity or audience failure
* MCP target profile missing or unavailable
* Network or DNS reachability
* TLS or certificate validation
* Microsoft Entra token or identity failure
* Missing contained database user
* Login accepted but database access denied
* Required DMV permission denied

Return the exact failure without exposing secrets. Do not retry with broader
credentials or another database client.

If a system object or column is unavailable, verify the engine, version, and
platform-specific documentation. Use a supported alternative or report the
limitation. Do not guess a replacement column.

If evidence is empty, check capture state, reset time, filters, permissions,
and workload activity before concluding that the condition did not occur.
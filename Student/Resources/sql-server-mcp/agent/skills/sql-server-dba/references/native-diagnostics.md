---
title: Native SQL Server diagnostic surfaces
description: Native metadata and performance sources for the SQL Server DBA skill
author: SRE Agent DBA project
ms.date: 2026-09-21
ms.topic: reference
keywords:
  - sql server
  - azure sql
  - dynamic management views
  - query store
  - execution plans
estimated_reading_time: 6
---

## Selection principles

Choose native surfaces only after identifying the engine edition, version,
database scope, and effective permissions.

Dynamic management object schemas can change between Database Engine versions.
Select named columns and verify availability instead of using `SELECT *`.

## Schema and dependency discovery

| Need                  | Preferred native surfaces                                                                                   |
|-----------------------|-------------------------------------------------------------------------------------------------------------|
| Schemas and objects   | `sys.schemas`, `sys.objects`, `sys.tables`, `sys.views`                                                      |
| Columns and types     | `sys.columns`, `sys.types`, `sys.computed_columns`, `sys.default_constraints`                               |
| Declared keys         | `sys.key_constraints`, `sys.indexes`, `sys.index_columns`                                                   |
| Relationships         | `sys.foreign_keys`, `sys.foreign_key_columns`                                                               |
| Validation rules      | `sys.check_constraints`                                                                                     |
| Dependencies          | `sys.sql_expression_dependencies`                                                                           |
| Object definitions    | `sys.sql_modules` when `VIEW DEFINITION` permits access                                                     |
| Storage by object     | `sys.dm_db_partition_stats`, `sys.partitions`, `sys.allocation_units`                                       |

Do not infer an entity relationship solely from matching column names. Report
declared and inferred relationships separately.

## Activity and concurrency

| Need                     | Preferred native surfaces                                                                                       |
|--------------------------|-----------------------------------------------------------------------------------------------------------------|
| Active work              | `sys.dm_exec_requests`, `sys.dm_exec_sessions`, `sys.dm_exec_connections`                                       |
| SQL text and plans       | `sys.dm_exec_sql_text`, `sys.dm_exec_query_plan`, `sys.dm_exec_text_query_plan`                                 |
| Transactions             | `sys.dm_tran_active_transactions`, `sys.dm_tran_session_transactions`, `sys.dm_tran_database_transactions`       |
| Locks and blocking       | `sys.dm_tran_locks`, request wait and blocking columns                                                          |
| Waiting tasks            | `sys.dm_os_waiting_tasks` where supported                                                                       |
| Deadlock history         | Existing Extended Events targets or platform telemetry when configured                                          |

Join only the rows needed for the target database, session, request, or time
window. Plan XML retrieval can be expensive when applied broadly.

## Historical workload and plans

| Need                   | Preferred native surfaces                                                                                         |
|------------------------|-------------------------------------------------------------------------------------------------------------------|
| Query Store state      | `sys.database_query_store_options`                                                                                |
| Queries and text       | `sys.query_store_query`, `sys.query_store_query_text`                                                             |
| Plans                  | `sys.query_store_plan`                                                                                            |
| Runtime history        | `sys.query_store_runtime_stats`, `sys.query_store_runtime_stats_interval`                                         |
| Wait history           | `sys.query_store_wait_stats` where supported                                                                      |
| Cached query evidence  | `sys.dm_exec_query_stats` with narrowly scoped text and plan functions                                            |

Query Store intervals and aggregation semantics matter. Compare equivalent
windows and include execution count when interpreting averages or totals.

## Waits and resources

| Need                     | Preferred native surfaces                                                                                       |
|--------------------------|-----------------------------------------------------------------------------------------------------------------|
| Server waits             | `sys.dm_os_wait_stats` where supported                                                                          |
| Azure SQL database waits | `sys.dm_db_wait_stats` where supported                                                                          |
| Azure SQL utilization    | `sys.dm_db_resource_stats`; `sys.resource_stats` requires the logical-server `master` database                  |
| Memory grants            | `sys.dm_exec_query_memory_grants`                                                                               |
| I/O latency              | `sys.dm_io_virtual_file_stats`, joined to `sys.database_files`                                                   |
| File usage               | `sys.database_files`, `sys.dm_db_file_space_usage`, `sys.dm_db_log_space_usage`                                 |
| Tempdb usage             | `sys.dm_db_session_space_usage`, `sys.dm_db_task_space_usage`, platform-specific tempdb metadata                |
| Database configuration   | `sys.database_scoped_configurations`, database metadata                                                          |
| Server configuration     | `sys.configurations` only where the deployment and permission scope support it                                  |

Azure SQL Database intentionally restricts or filters many server-scoped
surfaces. Do not treat missing server-wide rows as evidence of no pressure.

## Index and statistics evidence

| Need                   | Preferred native surfaces                                                                                           |
|------------------------|---------------------------------------------------------------------------------------------------------------------|
| Index definitions      | `sys.indexes`, `sys.index_columns`, `sys.columns`                                                                   |
| Usage counters         | `sys.dm_db_index_usage_stats`                                                                                       |
| Operational pressure   | `sys.dm_db_index_operational_stats`                                                                                 |
| Physical condition     | `sys.dm_db_index_physical_stats` with narrow scope and safe scan mode                                               |
| Missing-index signals  | `sys.dm_db_missing_index_details`, `sys.dm_db_missing_index_groups`, `sys.dm_db_missing_index_group_stats`          |
| Statistics metadata    | `sys.stats`, `sys.stats_columns`, `sys.dm_db_stats_properties`                                                      |

Usage and missing-index counters reset after relevant restarts, failovers,
database movement, or cache events. Record the available observation lifetime.

Never recommend an index from missing-index metadata alone. Compare existing
indexes and account for selectivity, include columns, filtered predicates,
write overhead, storage, and maintenance.

## Native tools beyond system views

Use these only when available, already configured, and read-only for the
current task:

* Query Store
* Estimated execution plans
* Existing actual plans captured by native telemetry
* Existing Extended Events sessions and event files
* SQL Server error logs exposed through an approved read-only tool
* Azure Monitor metrics and logs for Azure SQL
* Azure SQL Query Performance Insight
* Automatic tuning recommendations as evidence, not commands

Do not create an Extended Events session or change capture configuration during
a read-only investigation.

## Permission interpretation

Database-scoped DMV permissions vary by version:

| Platform version                 | Typical database performance permission |
|----------------------------------|-----------------------------------------|
| SQL Server 2019 and earlier      | `VIEW DATABASE STATE`                   |
| SQL Server 2022 and later        | `VIEW DATABASE PERFORMANCE STATE`       |
| Azure SQL Database               | `VIEW DATABASE PERFORMANCE STATE`       |

Server-scoped investigations require separate server permissions and are not
implied by database-scoped access. Report missing access rather than broadening
the query or requesting administrator credentials.

## References

* [Dynamic management objects](https://learn.microsoft.com/sql/relational-databases/system-dynamic-management-objects/system-dynamic-management-objects)
* [Query Store](https://learn.microsoft.com/sql/relational-databases/performance/monitoring-performance-by-using-the-query-store)
* [System catalog views](https://learn.microsoft.com/sql/relational-databases/system-catalog-views/catalog-views-transact-sql)
* [Execution plans](https://learn.microsoft.com/sql/relational-databases/performance/execution-plans)

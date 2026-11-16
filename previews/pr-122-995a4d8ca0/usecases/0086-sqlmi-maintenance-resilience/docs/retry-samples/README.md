# Retry logic samples for SQL Managed Instance

During maintenance (or a failover) the instance is **reconfigured**: open connections drop for a few seconds (usually < 30 s) and new ones fail with transient errors such as **40613**, **40197**, **4060** or **233**. If the application does not retry, the user sees the error. If it retries with backoff, the user only notices a slightly slower request.

| File | Technology | Mechanism |
|---|---|---|
| [`dotnet-sqlclient-retry.cs`](dotnet-sqlclient-retry.cs) | .NET with Microsoft.Data.SqlClient 5.x | `SqlConfigurableRetryFactory.CreateExponentialRetryProvider` + `ConnectRetryCount` |
| [`efcore-retry.cs`](efcore-retry.cs) | Entity Framework Core | `EnableRetryOnFailure` + `CreateExecutionStrategy` for transactions |
| [`SqlMiRetry.java`](SqlMiRetry.java) | Java, Microsoft JDBC Driver | Loop with exponential backoff and jitter + `connectRetryCount` |
| [`python-pyodbc-retry.py`](python-pyodbc-retry.py) | Python, pyodbc + ODBC Driver 18 | Loop with exponential backoff and jitter + `ConnectRetryCount` |

## Common rules

1. **5 tries, starting at 1 s, at most 20 s between tries.** Covers a typical reconfiguration with margin.
2. **Retry the whole unit of work** (open connection + query or full transaction), never a single command inside an already open transaction.
3. **Only transient errors.** A syntax or permission error is never retried.
4. **Log every retry** in Application Insights. The SRE Agent report then moves the application from "Sin reintentos" (no retries) to "Resiliente" (resilient).
5. **Test in pre-production** with [`../simulate-maintenance-failover.ps1`](../simulate-maintenance-failover.ps1).

References (Microsoft Learn):
- [Configurable retry logic in SqlClient](https://learn.microsoft.com/sql/connect/ado-net/configurable-retry-logic)
- [Troubleshoot transient connection errors](https://learn.microsoft.com/azure/azure-sql/database/troubleshoot-common-connectivity-issues)
- [Connection resiliency in EF Core](https://learn.microsoft.com/ef/core/miscellaneous/connection-resiliency)

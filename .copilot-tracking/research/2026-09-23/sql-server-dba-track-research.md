<!-- markdownlint-disable-file -->

# SQL Server DBA Track Research

## Scope

Adapt the read-only solution in `C:\Users\vzisiadis\repos\sre-agent-dba` into a
separate Azure SRE Agent track in this repository. Preserve the existing track
and copy only the assets needed to run the SQL Server scenarios.

## Selected Structure

* Student challenges: `Student/sql-server-dba/Challenge-00.md` through
  `Challenge-08.md`
* Coach guides: `Coach/sql-server-dba/README.md` and `Solution-00.md` through
  `Solution-08.md`
* Runtime resources: `Student/Resources/sql-server-mcp/`
* Website: a dedicated SQL Server DBA track section using the existing RVAP
  visual system

## Source Evidence

The source solution has three operational layers:

1. Azure SRE Agent custom agent configuration
2. A SQL Server DBA skill with read-only operating boundaries
3. A hardened .NET SQL Server MCP server

The executable lab assets are the SQL setup scripts, deterministic workload
scripts, agent YAML, skill, MCP server source, tests, container definition, and
MIT license. Generated `bin/` and `obj/` trees, local launch settings, authoring
instructions, and any environment-specific secrets must not be copied.

## Scenario Map

| Challenge | Scenario | Evidence |
|---|---|---|
| 00 | Deploy and validate the read-only MCP path | SQL setup scripts, managed identity, `/healthz`, `/mcp` |
| 01 | Orient to the business and schema | Database model and catalog inspection |
| 02 | Capture a Query Store baseline | `workloads/01_capture_baseline.sql` |
| 03 | Distinguish duration from pressure | Long-running `WAITFOR` scenario |
| 04 | Identify a blocking chain | `workloads/05_blocking_session_a.sql` and `06_blocking_session_b.sql` |
| 05 | Recommend a missing index | `workloads/02_missing_index.sql` |
| 06 | Diagnose SARGability and implicit conversion | `workloads/04_sargability.sql` |
| 07 | Investigate parameter sensitivity | `workloads/03_parameter_sensitivity.sql` |
| 08 | Triage a combined incident | Multiple evidence sources ranked by demonstrated impact |

## Security and Portability Decisions

* Keep the MCP surface read-only and preserve the `sre_dba_observer`
  least-privilege role.
* Use managed identity and encrypted SQL connections in the deployment guide.
* Do not include connection strings, passwords, or environment-specific values.
* Preserve upstream MIT attribution.
* Describe Azure Container Apps as the certified hosting path while noting that
  equivalent public HTTPS container hosts can run the server.

## Authoritative References

* Azure SRE Agent MCP connectors:
  `https://learn.microsoft.com/azure/sre-agent/mcp-connectors`
* Deploy a .NET MCP server to Azure Container Apps:
  `https://learn.microsoft.com/azure/container-apps/tutorial-mcp-server-dotnet`
* SQL Server blocking troubleshooting:
  `https://learn.microsoft.com/troubleshoot/sql/database-engine/performance/understand-resolve-blocking`
* Query Store performance monitoring:
  `https://learn.microsoft.com/sql/relational-databases/performance/monitoring-performance-by-using-the-query-store`


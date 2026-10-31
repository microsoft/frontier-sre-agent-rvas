**[Home](../../README.md)** — [Next Challenge >](./Challenge-01.md)

# Challenge 00 — Deploy the Read-Only DBA Path

> **Capabilities added in this challenge**: SQL Server MCP · Managed Identity · Read-Only DBA Agent

## Introduction

Connect Azure SRE Agent to a dedicated workshop database through the supplied
SQL Server MCP container. Keep the database identity read-only.

Verify connector health, profile discovery, diagnostic access, and refusal of
requests to change data or objects.

## Description

Use the
[SQL Server MCP deployment guide](../Resources/sql-server-mcp/README.md) to
achieve these outcomes:

First select a Linux environment using the shared
[Requirements](../../README.md#requirements). Codespaces on your own fork
supplies the common tooling and command-line SQL client. It does not
authenticate Azure or grant database access.

* Install and validate the `stockOrders` sample database in an approved lab
  environment
* Map the MCP workload identity to the `sre_dba_observer` database role
* Deploy the supplied container behind authenticated HTTPS ingress
* Create an Azure SRE Agent connector named `sqlserver-mcp`
* Add the supplied SQL Server DBA skill and custom agent
* Demonstrate the read-only boundary with a safe refusal test

> [!IMPORTANT]
> Do not grant the MCP identity `db_owner`, `sysadmin`, DML, DDL, maintenance,
> or configuration permissions. A successful refusal is part of the challenge.

## Pre-flight Validation Checklist

Run these commands in Linux Bash from the repository root before deploying.
Resolve all failures and review warnings with your coach:

```bash
# Local-only checks do not require an Azure login.
bash Student/Resources/infra/scripts/preflight.sh --local --track sql-dba

# Authenticate separately inside this Linux environment.
# Use az login --use-device-code when browser login is unavailable.
az version
az account show --query "{subscription:name,id:id,state:state}" --output table

# Required client tooling
curl --version
sqlcmd -?

# Container Apps extension
az extension show --name containerapp --query "{name:name,version:version}" --output table

# Read-only Azure/DBA prerequisites; no database login or role changes.
cd Student
make preflight PREFLIGHT_TRACK=sql-dba
```

If the extension is missing, install it explicitly using the shared setup guide;
pre-flight never installs/upgrades tools. Have your coach confirm the approved
SQL administrator, managed-identity mapping, MCP caller authorization, and
network/TLS path. A local tool check cannot prove database connectivity.
Keep the supplied observer role unchanged. Preserve private configuration/state
and clean up your dedicated lab before deleting its Codespace.

## Success Criteria

- [ ] The sample database validation returns `InstallationValidation = PASS`
- [ ] The container health endpoint returns a successful response
- [ ] The `sqlserver-mcp` connector is healthy and exposes only `list_profiles`, `get_object`, `run_query`, and `analyze_query`
- [ ] The DBA custom agent lists the approved profile and identifies the correct database without receiving a connection string
- [ ] A request to change data, create an index, or alter configuration is refused and no database state changes
- [ ] **Explain to your coach** — which controls prevent a prompt from turning a read-only investigation into a database change?

## Learning Resources

* [MCP connectors and tools in Azure SRE Agent](https://learn.microsoft.com/azure/sre-agent/mcp-connectors)
* [Managed identities in Azure Container Apps](https://learn.microsoft.com/azure/container-apps/managed-identity)
* [Microsoft Entra service principals with Azure SQL](https://learn.microsoft.com/azure/azure-sql/database/authentication-aad-service-principal-tutorial)
* [SQL Server permissions hierarchy](https://learn.microsoft.com/sql/relational-databases/security/permissions-hierarchy-database-engine)

## Tips

* Azure RBAC and SQL data-plane permissions are separate authorization layers.
* A healthy `/healthz` response proves process health, not database access.
* The MCP container is supplied and prevalidated; this track does not require
  students to modify or evaluate its implementation.
* Keep the connector name exactly `sqlserver-mcp`; the custom agent tool grant
  depends on that namespace.

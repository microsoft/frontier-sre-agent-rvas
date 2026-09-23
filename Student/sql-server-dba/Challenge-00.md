**[Home](../../README.md)** — [Next Challenge >](./Challenge-01.md)

# Challenge 00 — Deploy the Read-Only DBA Path

> **Capabilities added in this challenge**: SQL Server MCP · Managed Identity · Read-Only DBA Agent

## Introduction

An SRE agent should not receive unrestricted database access simply because it
can explain SQL Server. In this challenge, you establish a controlled path from
Azure SRE Agent to a dedicated workshop database through the supplied SQL
Server MCP container.

Your outcome is a healthy connector, a discoverable database profile, and
proof that the database identity can observe diagnostic evidence but cannot
change data or objects.

## Description

Use the
[SQL Server MCP deployment guide](../Resources/sql-server-mcp/README.md) to
achieve these outcomes:

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

Run these commands before deploying. Every check must pass:

```bash
# Azure CLI and active subscription
az version
az account show --query "{subscription:name,id:id,state:state}" --output table

# Required client tooling
curl --version
sqlcmd -?

# Container Apps extension
az extension add --name containerapp --upgrade
az extension show --name containerapp --query "{name:name,version:version}" --output table
```

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

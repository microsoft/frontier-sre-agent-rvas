---
title: SQL Server DBA track infrastructure
description: Coach reference Terraform for the SQL MCP Container App and the sample Azure SQL database
author: Microsoft
ms.date: 2026-09-28
ms.topic: reference
keywords:
  - terraform
  - azure container apps
  - azure sql
  - model context protocol
estimated_reading_time: 5
---

## Overview

This module deploys the Coach reference infrastructure for the
[SQL Server DBA track](../../../../../sql-server-dba/README.md):

| Resource | Default name | Purpose |
|---|---|---|
| Resource group | `rg-sre-dba` | Isolates the DBA track resources |
| User-assigned managed identity | `id-sre-dba-sql-mcp` | MCP workload identity for Azure SQL |
| Container Apps environment | `cae-sre-dba` | Consumption environment without VNet integration |
| Container App | `ca-sre-dba-sql-mcp` | Hosts the SQL MCP container on port `8080` |
| Azure SQL logical server | `sql-sre-dba-<suffix>` | Microsoft Entra-only authentication |
| Azure SQL database | `stockOrders` | Sample workshop database |

Container Apps logs go to the shared demo Log Analytics workspace, which the
Coach SRE Agent already reads. When the module is enabled, its resource group
is also added to the agent's read-only managed scopes.

## Deploy

The module is disabled by default. From `Coach/`, enable it with:

```bash
make infra TF_VARS='-var="deploy_sre_dba_infra=true" -var="sre_dba_sql_client_ip_address=<your-public-ip>"'
```

Optional root variables:

| Variable | Default | Purpose |
|---|---|---|
| `rg_sre_dba` | `rg-sre-dba` | Resource group name |
| `sre_dba_sql_location` | `null` (uses `location`) | Region override when Azure SQL capacity is restricted |
| `sre_dba_sql_client_ip_address` | `null` | Firewall rule for running the setup scripts |
| `sre_dba_sql_mcp_image` | `ghcr.io/microsoft/frontier-sre-agent-rvas/sql-server-mcp:latest` | MCP container image |

The default image is published by the `Docker Build and Publish` workflow.
Make the GHCR package public, or override the image with one the Container App
can pull anonymously.

## Complete the database setup

Terraform cannot create contained database users. The deploying principal is
the Microsoft Entra administrator of the server. After `terraform apply`:

1. Connect to the `sre_dba_sql_server_fqdn` output, database `stockOrders`,
   with Microsoft Entra authentication.
2. Run `Student/Resources/sql-server-mcp/sql/00` through `06`.
3. Set `@ManagedIdentityName` in `sql/07_add_ca_mcp_managed_identity.sql` to
   the `sre_dba_sql_mcp_identity_name` output, then run the script.
4. Verify the `sre_dba_sql_mcp_health_url` output returns a healthy response.

Until step 3 completes, the MCP server starts but database tool calls fail
with a login error for the managed identity.

## Security notes

> [!WARNING]
> Terraform does not configure authentication on the MCP ingress. The endpoint
> is public until you configure Microsoft Entra authentication manually, as
> described in the
> [SQL Server MCP deployment guide](../../../../../../Student/Resources/sql-server-mcp/README.md).
> Do not connect Azure SRE Agent to the endpoint before that step.

* The SQL server allows Azure services through its firewall because Container
  Apps without VNet integration has no fixed outbound address.
* The server uses Microsoft Entra-only authentication, so no SQL password is
  stored in Terraform state.
* The MCP identity receives only `sre_dba_observer` membership through
  `sql/07`. Azure RBAC does not authorize SQL queries, so no Azure role is
  assigned to it.

## Cleanup

Set `deploy_sre_dba_infra=false` and apply, or delete the resource group:

```bash
az group delete --name rg-sre-dba --yes --no-wait
```

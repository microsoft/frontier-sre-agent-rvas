---
title: SQL Server DBA track infrastructure
description: Reference Terraform for the SQL MCP Container App and the sample Azure SQL database
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

This module deploys the reference infrastructure for the
[SQL Server DBA track](../../../../../../02-sql-server-dba/README.md):

| Resource | Default name | Purpose |
|---|---|---|
| Resource group | provided by the caller | The lab root (`resources/infra`) creates `rg-sre-dba-rvas` and passes it in |
| User-assigned managed identity | `id-sre-dba-sql-mcp` | MCP workload identity for Azure SQL |
| Container Apps environment | `cae-sre-dba` | Consumption environment without VNet integration |
| Container App | `ca-sre-dba-sql-mcp` | Hosts the SQL MCP container on port `8080` |
| Azure SQL logical server | `sql-sre-dba-<suffix>` | Microsoft Entra-only authentication |
| Azure SQL database | `stockOrders` | Sample workshop database |

Container Apps logs go to the Log Analytics workspace the lab root creates,
so the SRE Agent can query them once its managed scope includes the lab
resource group.

## Deploy

From `labs/02-sql-server-dba/`, deploy it with:

```bash
make infra TF_VARS='-var="sql_client_ip_address=<your-public-ip>"'
```

Optional root variables (`resources/infra/variables.tf`):

| Variable | Default | Purpose |
|---|---|---|
| `sql_location` | `null` (uses `location`) | Region override when Azure SQL capacity is restricted |
| `sql_client_ip_address` | `null` | Firewall rule for running the setup scripts |
| `sql_mcp_image` | `ghcr.io/microsoft/frontier-sre-agent-rvas/sql-server-mcp:latest` | MCP container image |

The default image is published by the `Docker Build and Publish` workflow.
Make the GHCR package public, or override the image with one the Container App
can pull anonymously.

## Complete the database setup

Terraform cannot create contained database users. The deploying principal is
the Microsoft Entra administrator of the server. After `terraform apply`:

1. Connect to the `sql_server_fqdn` output, database `stockOrders`,
   with Microsoft Entra authentication.
2. Run `labs/02-sql-server-dba/resources/sql-server-mcp/sql/00` through `06`.
3. Set `@ManagedIdentityName` in `sql/07_add_ca_mcp_managed_identity.sql` to
   the `sql_mcp_identity_name` output, then run the script.
4. Verify the `sql_mcp_health_url` output returns a healthy response.

Until step 3 completes, the MCP server starts but database tool calls fail
with a login error for the managed identity.

## Security notes

> [!WARNING]
> Terraform does not configure authentication on the MCP ingress. The endpoint
> is public until you configure Microsoft Entra authentication manually, as
> described in the
> [SQL Server MCP deployment guide](../../../../../../02-sql-server-dba/resources/sql-server-mcp/README.md).
> Do not connect Azure SRE Agent to the endpoint before that step.

* The SQL server allows Azure services through its firewall because Container
  Apps without VNet integration has no fixed outbound address.
* The server uses Microsoft Entra-only authentication, so no SQL password is
  stored in Terraform state.
* The MCP identity receives only `sre_dba_observer` membership through
  `sql/07`. Azure RBAC does not authorize SQL queries, so no Azure role is
  assigned to it.

## Cleanup

Run `make destroy` from `labs/02-sql-server-dba/`. This removes the lab resource group
(`rg-sre-dba-rvas` by default) and everything in it.

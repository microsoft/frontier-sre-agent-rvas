---
title: Grant the SRE managed identity database access
description: Configure Azure SQL data-plane permissions and optional Azure resource Reader access for the SRE managed identity
author: SRE Agent DBA project
ms.date: 2026-09-21
ms.topic: how-to
keywords:
  - azure sql database
  - managed identity
  - microsoft entra
  - database permissions
  - azure rbac
estimated_reading_time: 7
---

## Authorization layers

Azure SQL Database uses separate authorization systems:

| Authorization layer         | Purpose                                                   | Required for this setup |
|-----------------------------|-----------------------------------------------------------|-------------------------|
| Azure RBAC                  | Manage or inspect the Azure SQL resource through Azure Resource Manager | No for database queries |
| Azure SQL database security | Connect to the database and query its data, metadata, Query Store, and database-scoped performance state | Yes |

An Azure `Reader` assignment does not grant `SELECT` or other permissions
inside an Azure SQL database. The required step is to create a contained
Microsoft Entra database user for the managed identity and add that user to the
existing `sre_dba_observer` database role.

The optional Azure `Reader` assignment is useful only if the SRE agent also
needs Azure control-plane metadata for the database resource. It does not
replace the contained database user.

## Prerequisites

Complete these prerequisites before granting access:

* The Azure SQL logical server has a Microsoft Entra administrator
* [`../sql/05_observer_role.sql`](../sql/05_observer_role.sql) has created
  `sre_dba_observer` in the target database
* The operator knows the managed identity's Microsoft Entra display name
* The operator knows its Object (principal) ID when duplicate-name
  disambiguation is required
* The provisioning session uses a Microsoft Entra administrative identity that
  can create database users and alter role membership

The Object (principal) ID and client ID are different values. The optional
`WITH OBJECT_ID` SQL clause requires the Object (principal) ID.

For a system-assigned managed identity, find the Object (principal) ID on the
SRE agent resource's **Identity** page. For a user-assigned managed identity,
find the Principal ID on the managed identity resource's **Properties** page.

## Grant Azure SQL data-plane permissions

Open
[`../sql/07_add_ca_mcp_managed_identity.sql`](../sql/07_add_ca_mcp_managed_identity.sql)
and set:

```sql
DECLARE @ManagedIdentityName sysname = N'<managed-identity-display-name>';
DECLARE @ManagedIdentityObjectId uniqueidentifier = NULL;
```

When the managed identity has a unique display name, replace only
`@ManagedIdentityName` and leave `@ManagedIdentityObjectId` as `NULL`. The
script uses the standard syntax:

```sql
CREATE USER [managed-identity-display-name] FROM EXTERNAL PROVIDER;
```

When Microsoft Entra contains duplicate service-principal display names:

1. Set `@ManagedIdentityName` to a unique database alias based on the original
   display name, such as `sre-agent-a1b2c`.
2. Set `@ManagedIdentityObjectId` to the managed identity's Object (principal)
   ID.

The script then uses:

```sql
CREATE USER [sre-agent-a1b2c]
FROM EXTERNAL PROVIDER
WITH OBJECT_ID = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee';
```

Run the script while connected to the target user database, not `master`. It is
idempotent:

* It creates the external user only when the name does not exist
* It rejects an existing principal with the same name and a different type
* It adds role membership only when it is missing
* It reports the resulting user, role membership, and role permissions

Repeat the script in every Azure SQL database the managed identity must inspect.
Contained database users and database-role memberships are database-scoped.

## Effective database permissions

Membership in `sre_dba_observer` provides:

* `CONNECT`
* `SELECT`
* `SHOWPLAN`
* `VIEW DEFINITION`
* `VIEW DATABASE PERFORMANCE STATE` on Azure SQL Database

The role explicitly denies:

* `INSERT`
* `UPDATE`
* `DELETE`
* `EXECUTE`
* `ALTER`
* `TAKE OWNERSHIP`

The managed identity can read application data, database metadata, Query Store,
database-scoped dynamic management views, and estimated execution plans. It
cannot modify data or database objects and cannot execute application stored
procedures.

`SHOWPLAN` is a separate database permission. It allows SQL Server to compile a
permitted statement and return its estimated execution plan. With
`SET SHOWPLAN_XML ON`, SQL Server does not execute the submitted statement.
The permission must exist in every database containing objects referenced by
the statement.

## Optional Azure Reader assignment

Skip this section when the agent needs only Azure SQL data-plane access.

If the SRE agent also needs to read the Azure SQL database resource through
Azure Resource Manager, assign the built-in `Reader` role at the individual
database resource scope. The identity performing this command needs permission
to create Azure role assignments.

```powershell
$subscriptionId = '<subscription-id>'
$resourceGroupName = '<resource-group-name>'
$sqlServerName = '<logical-sql-server-name>'
$databaseName = '<database-name>'
$managedIdentityPrincipalId = '<managed-identity-object-principal-id>'

$databaseResourceId = az sql db show `
  --subscription $subscriptionId `
  --resource-group $resourceGroupName `
  --server $sqlServerName `
  --name $databaseName `
  --query id `
  --output tsv

az role assignment create `
  --assignee-object-id $managedIdentityPrincipalId `
  --assignee-principal-type ServicePrincipal `
  --role 'Reader' `
  --scope $databaseResourceId
```

Use the managed identity's Object (principal) ID for
`--assignee-object-id`. Do not use its client ID.

Verify the optional assignment:

```powershell
az role assignment list `
  --assignee $managedIdentityPrincipalId `
  --scope $databaseResourceId `
  --include-inherited `
  --output table
```

## Directory lookup failures

`CREATE USER ... FROM EXTERNAL PROVIDER` asks Azure SQL to resolve the identity
in Microsoft Entra ID. If the statement reports that the server cannot query
Microsoft Entra ID or cannot resolve the service principal, verify the logical
server identity and its directory permissions.

Microsoft documents `Directory Readers` as one option. A narrower alternative
is to grant the logical server identity these Microsoft Graph application
permissions:

* `User.Read.All`
* `GroupMember.Read.All`
* `Application.Read.All`

Directory permissions apply to the Azure SQL logical server identity, not to
the SRE agent managed identity.

## Scope boundary

This setup covers authorization only. It does not configure:

* Token acquisition
* Connection strings
* SQL drivers
* Runtime environment variables
* Firewall or private-network routing
* SRE agent tools, prompts, or connection behavior

Those concerns are covered by the
[SQL Server MCP deployment guide](../README.md).

## Microsoft documentation

* [Microsoft Entra service principals with Azure SQL](https://learn.microsoft.com/azure/azure-sql/database/authentication-aad-service-principal-tutorial)
* [Create users with nonunique Microsoft Entra names](https://learn.microsoft.com/sql/relational-databases/security/authentication-access/authentication-microsoft-entra-create-users-with-nonunique-names)
* [Configure Microsoft Entra authentication for Azure SQL](https://learn.microsoft.com/azure/azure-sql/database/authentication-aad-configure)
* [Azure role assignments using Azure CLI](https://learn.microsoft.com/azure/role-based-access-control/role-assignments-cli)

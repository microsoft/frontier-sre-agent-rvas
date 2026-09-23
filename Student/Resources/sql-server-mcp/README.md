---
title: SQL Server MCP workshop resources
description: Deploy, secure, and validate the supplied read-only SQL Server MCP container used by the Azure SRE Agent DBA track
author: Microsoft
ms.date: 2026-09-23
ms.topic: how-to
keywords:
  - azure sre agent
  - model context protocol
  - sql server
  - azure sql
  - azure container apps
estimated_reading_time: 15
---

## Overview

This folder contains the SQL Server MCP server and lab assets for the Azure SRE
Agent SQL Server DBA track. The deployment exposes four tools:

| Tool | Purpose |
|---|---|
| `list_profiles` | Discover operator-approved SQL targets |
| `get_object` | Inspect columns, relationships, constraints, indexes, and routines |
| `run_query` | Run bounded, parser-validated, read-only `SELECT` statements |
| `analyze_query` | Compile and summarize estimated execution plans without running the workload |

The server supports Streamable HTTP at `/mcp` and provides a separate
`/healthz` endpoint. The supplied container runs as a non-root .NET 10 process.

> [!IMPORTANT]
> The database role is the enforcement boundary. Keep the MCP identity in the
> supplied `sre_dba_observer` role and do not grant it `db_owner`, `sysadmin`,
> DML, DDL, maintenance, or configuration permissions.

## Folder contents

| Path | Purpose |
|---|---|
| `agent/` | Azure SRE Agent custom-agent definition and DBA skill |
| `docs/` | Architecture, database model, identity, and sample-prompt references |
| `sql/` | Sample database, least-privilege role, identity mapping, validation, and teardown |
| `src/` | SQL Server MCP server source |
| `test/` | Unit, functional, and end-to-end tests |
| `workloads/` | Deterministic Query Store, blocking, index, SARGability, and parameter-skew workloads |
| `Dockerfile` | Unit-tested, non-root production container build |
| `server.json` | MCP registry metadata and supported environment variables |

The MCP implementation is derived from
[alyiox/mcp-mssql](https://github.com/alyiox/mcp-mssql) and remains licensed
under the included [MIT license](./LICENSE).

## Prerequisites

Install or obtain:

* Azure CLI 2.62 or later with the Container Apps extension
* `sqlcmd`, SQL Server Management Studio, or another approved SQL client
* `curl` or an equivalent HTTPS client
* An Azure subscription with permission to create a resource group, Azure
  Container Registry, managed identity, Container Apps environment, and
  Container App
* An existing Azure SQL Database, Azure SQL Managed Instance, or supported SQL
  Server target
* A Microsoft Entra administrator on the Azure SQL logical server
* Network and DNS connectivity from Azure Container Apps to the SQL endpoint
* An Azure SRE Agent with permission to add a custom MCP connector and custom
  agent

The certified deployment uses Azure SQL, Azure Container Apps, and a
user-assigned managed identity. Other SQL Server targets require an approved
authentication profile and equivalent TLS and network controls.

The supplied container and MCP implementation are prevalidated. Participants
deploy and configure them as workshop assets; they do not modify or evaluate
the server implementation. The hardened managed-identity policy requires:

* `Authentication=Active Directory Managed Identity`
* The user-assigned managed identity client ID in `User Id`
* An explicit database
* Validated TLS
* No password or integrated-security value

It normalizes the connection to `ApplicationIntent=ReadOnly` and a maximum
30-second connection timeout.

## Install the sample database

Connect to a dedicated user database with an administrative identity. Run the
scripts in this order:

1. `sql/00_database_settings.sql`
2. `sql/01_schema.sql`
3. `sql/02_seed_reference_data.sql`
4. `sql/03_generate_sample_data.sql`
5. `sql/04_programmability.sql`
6. `sql/05_observer_role.sql`
7. `sql/06_validate.sql`

The validation script checks table cardinality, trusted foreign keys, Query
Store state, observer permissions, and the installed scenario catalog. It ends
with:

```text
InstallationValidation
----------------------
PASS
```

To remove the sample objects later, run `sql/99_teardown.sql` from the same
database.

## Create the MCP managed identity database user

Create a user-assigned managed identity for the Container App:

```bash
export RESOURCE_GROUP="<resource-group>"
export LOCATION="<azure-region>"
export IDENTITY_NAME="<mcp-managed-identity-name>"

az group create \
  --name "$RESOURCE_GROUP" \
  --location "$LOCATION"

az identity create \
  --name "$IDENTITY_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --location "$LOCATION"

export IDENTITY_CLIENT_ID="$(az identity show \
  --name "$IDENTITY_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --query clientId \
  --output tsv)"

export IDENTITY_PRINCIPAL_ID="$(az identity show \
  --name "$IDENTITY_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --query principalId \
  --output tsv)"

export IDENTITY_RESOURCE_ID="$(az identity show \
  --name "$IDENTITY_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --query id \
  --output tsv)"
```

Edit `sql/07_add_ca_mcp_managed_identity.sql` and replace the managed identity
display-name placeholder. If the tenant contains duplicate display names, also
set the Object (principal) ID. Run the script in the target user database, not
`master`.

The resulting identity receives:

* `CONNECT`
* `SELECT`
* `SHOWPLAN`
* `VIEW DEFINITION`
* `VIEW DATABASE PERFORMANCE STATE` on Azure SQL, or `VIEW DATABASE STATE`
  where required

The role explicitly denies data changes, execution, alteration, and ownership.
See [managed identity database access](./docs/managed-identity-database-access.md)
for duplicate-name handling and Azure SQL directory lookup requirements.

## Publish the supplied container

Set deployment variables:

```bash
export ACR_NAME="<globally-unique-acr-name>"
export IMAGE_NAME="sql-server-mcp"
export IMAGE_TAG="1.0.0"
export CONTAINERAPPS_ENVIRONMENT="<container-apps-environment>"
export CONTAINER_APP_NAME="<container-app-name>"
export SQL_SERVER_FQDN="<server>.database.windows.net"
export SQL_DATABASE="<database>"
```

If the coach provides an approved image, set `ACR_LOGIN_SERVER`, `IMAGE_NAME`,
and `IMAGE_TAG` to that image and continue with the deployment section.
Otherwise, create a registry and publish the supplied container definition with
Azure Container Registry Tasks:

```bash
az acr create \
  --name "$ACR_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --location "$LOCATION" \
  --sku Basic

az acr build \
  --registry "$ACR_NAME" \
  --image "$IMAGE_NAME:$IMAGE_TAG" \
  --file Dockerfile \
  .

export ACR_LOGIN_SERVER="$(az acr show \
  --name "$ACR_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --query loginServer \
  --output tsv)"

export ACR_RESOURCE_ID="$(az acr show \
  --name "$ACR_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --query id \
  --output tsv)"

az role assignment create \
  --assignee-object-id "$IDENTITY_PRINCIPAL_ID" \
  --assignee-principal-type ServicePrincipal \
  --role AcrPull \
  --scope "$ACR_RESOURCE_ID"
```

No participant changes to the MCP implementation are required.

## Deploy to Azure Container Apps

Create the environment and deploy one replica. A single replica avoids
session-routing ambiguity for MCP resources stored on local ephemeral storage.

```bash
az containerapp env create \
  --name "$CONTAINERAPPS_ENVIRONMENT" \
  --resource-group "$RESOURCE_GROUP" \
  --location "$LOCATION"

export SQL_CONNECTION_STRING="Server=tcp:$SQL_SERVER_FQDN,1433;Database=$SQL_DATABASE;Authentication=Active Directory Managed Identity;User Id=$IDENTITY_CLIENT_ID;Encrypt=True;TrustServerCertificate=False;"

az containerapp create \
  --name "$CONTAINER_APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --environment "$CONTAINERAPPS_ENVIRONMENT" \
  --image "$ACR_LOGIN_SERVER/$IMAGE_NAME:$IMAGE_TAG" \
  --user-assigned "$IDENTITY_RESOURCE_ID" \
  --registry-server "$ACR_LOGIN_SERVER" \
  --registry-identity "$IDENTITY_RESOURCE_ID" \
  --ingress external \
  --target-port 8080 \
  --min-replicas 1 \
  --max-replicas 1 \
  --secrets "sql-connection-string=$SQL_CONNECTION_STRING" \
  --env-vars \
    "MCPMSSQL_CONNECTION_STRING=secretref:sql-connection-string" \
    "MCPMSSQL_DESCRIPTION=SQL Server DBA workshop database" \
    "MCPMSSQL_REQUIRE_AZURE_MANAGED_IDENTITY=true" \
    "MCPMSSQL_TRANSPORT=http" \
    "MCPMSSQL_QUERY_MAX_ROWS=250" \
    "MCPMSSQL_QUERY_COMMAND_TIMEOUT_SECONDS=30" \
    "MCPMSSQL_QUERY_MAX_OUTPUT_BYTES=262144" \
    "MCPMSSQL_ANALYZE_COMMAND_TIMEOUT_SECONDS=30"
```

Configure an HTTP liveness probe for path `/healthz`, port `8080`, in the
Container App revision. Keep the database profile in a Container Apps secret
even though the certified connection string contains no password.

Retrieve the public hostname and validate liveness:

```bash
export MCP_HOSTNAME="$(az containerapp show \
  --name "$CONTAINER_APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --query properties.configuration.ingress.fqdn \
  --output tsv)"

curl --fail --show-error "https://$MCP_HOSTNAME/healthz"
```

Expected response:

```json
{"service":"mcp-mssql","status":"healthy"}
```

## Protect the MCP endpoint

Do not connect Azure SRE Agent to an anonymous public endpoint. Add a Microsoft
Entra authentication edge to the Container App:

1. Register an application for the MCP API in Microsoft Entra ID.
2. Expose an application role named `Mcp.Invoke` for applications.
3. Configure Container Apps built-in authentication with the application
   registration.
4. Require authentication for all requests except the `/healthz` liveness
   path. If the hosting policy cannot exempt the liveness path, use an
   internal platform probe that can authenticate.
5. Assign `Mcp.Invoke` to the Azure SRE Agent caller service principal or
   managed identity.
6. Verify that unauthenticated requests to `/mcp` return `401` or `403`.

Authentication configuration varies by tenant ownership and application
registration policy. Follow
[authentication and authorization in Azure Container Apps](https://learn.microsoft.com/azure/container-apps/authentication)
and record the approved audience and caller identity for the workshop.

> [!CAUTION]
> Database read-only permissions do not make an anonymous MCP endpoint safe.
> Query results, object definitions, plans, and business identifiers can still
> be sensitive.

## Connect Azure SRE Agent

In Azure SRE Agent:

1. Create a Streamable HTTP MCP connector named `sqlserver-mcp`.
2. Set the endpoint to `https://<container-app-hostname>/mcp`.
3. Configure the Microsoft Entra authentication approved in the previous
   section.
4. Wait for the connector status to become healthy.
5. Select the four read-only tools exposed by the connector.
6. Add the custom agent from `agent/sql-server-dba-agent.yaml`.
7. Add the skill from `agent/skills/sql-server-dba/`.
8. Confirm the custom agent has `sqlserver-mcp/*` and no alternative database
   connector.

Azure SRE Agent discovers MCP tools automatically and checks connector health.
See [MCP connectors and tools in Azure SRE Agent](https://learn.microsoft.com/azure/sre-agent/mcp-connectors).

## Validate the end-to-end path

Invoke the SQL Server DBA custom agent and ask it to:

1. List approved profiles.
2. Identify the configured SQL engine edition, version, database, compatibility
   level, and Query Store state.
3. Inspect `sales.SalesOrderLine`.
4. Explain which write operations it cannot perform.

The agent should use only `sqlserver-mcp/*`, report the observation time and
scope, and confirm that it applied no database changes.

Expected failure modes are explicit:

| Symptom | Likely cause |
|---|---|
| Container starts, then fails | Invalid or incomplete managed-identity connection profile |
| SQL login error for token identity | Managed identity user is missing from the target database |
| `SHOWPLAN` denied | `sql/05_observer_role.sql` or role membership is incomplete |
| Connector returns `401` or `403` | Caller lacks the `Mcp.Invoke` assignment or uses the wrong audience |
| Connector is healthy but profile is absent | Environment variable or secret reference is missing |
| Query Store results are empty | Baseline workload has not run, capture is read-only, or retention removed evidence |

## Run the scenario workloads

Use a non-production SQL session and follow each challenge's timing guidance:

| Script | Scenario |
|---|---|
| `workloads/01_capture_baseline.sql` | Seed historical Query Store evidence |
| `workloads/02_missing_index.sql` | Generate repeatable product-led scan evidence |
| `workloads/03_parameter_sensitivity.sql` | Exercise skewed customer parameters |
| `workloads/04_sargability.sql` | Generate non-SARGable and implicit-conversion evidence |
| `workloads/05_blocking_session_a.sql` | Hold the deterministic head-blocker transaction |
| `workloads/06_blocking_session_b.sql` | Create the blocked request in a second session |

The workloads roll back state-changing transactions where applicable. Stop and
restore the lab before using the scripts outside the dedicated workshop
database.

## Cleanup

Remove workshop resources when the event ends:

```bash
az group delete \
  --name "$RESOURCE_GROUP" \
  --yes \
  --no-wait
```

Run `sql/99_teardown.sql` separately if the sample database is hosted outside
the deleted resource group.

## Learning resources

* [MCP connectors and tools in Azure SRE Agent](https://learn.microsoft.com/azure/sre-agent/mcp-connectors)
* [Deploy a .NET MCP server to Azure Container Apps](https://learn.microsoft.com/azure/container-apps/tutorial-mcp-server-dotnet)
* [Managed identities in Azure Container Apps](https://learn.microsoft.com/azure/container-apps/managed-identity)
* [Monitor performance with Query Store](https://learn.microsoft.com/sql/relational-databases/performance/monitoring-performance-by-using-the-query-store)
* [Understand and resolve SQL Server blocking](https://learn.microsoft.com/troubleshoot/sql/database-engine/performance/understand-resolve-blocking)

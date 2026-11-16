---
title: Deploy the Read-Only DBA Path
summary: Deploy the supplied .NET MCP container, map its managed identity into the least-privilege observer role, secure the Streamable HTTP endpoint, and prove that Azure SRE Agent can inspect SQL without receiving a write path.
phase: Trust boundary
group: Foundation
tags:
- Azure Container Apps
- managed identity
- MCP
highlight: true
---

# Challenge 00 — Deploy the Read-Only DBA Path

> **Capabilities added in this challenge**: SQL Server MCP · Managed Identity · Read-Only DBA Agent

## Purpose

* Deploy the Azure SRE Agent → MCP → SQL trust path and confirm each hop passes its health or connectivity check.
* Show that least privilege holds: a data-changing prompt is refused and nothing changes in the database.
* Expected time: 60-90 minutes.

## Introduction

Connect Azure SRE Agent to a dedicated workshop database through the supplied
SQL Server MCP container, with a read-only database identity.

You verify connector health, profile discovery, diagnostic access, and that the
agent refuses requests to change data or objects.

## Description

Build the trust path **SRE Agent → MCP container → Azure SQL** with a database
identity that can only read. Do not grant the MCP identity `db_owner`,
`sysadmin`, DML, DDL, maintenance or configuration permissions. A successful
refusal is part of the challenge.

You will:

* Deploy the Azure SQL database and the supplied MCP container
* Install the `stockOrders` sample database
* Map the MCP managed identity to the `sre_dba_observer` role
* Secure the MCP endpoint and connect it to Azure SRE Agent as `sqlserver-mcp`
* Add the supplied DBA skill and custom agent
* Prove the read-only boundary with a refusal test

### Solution steps

Work in a Linux shell (Codespaces on your fork, or WSL2). Codespaces provides
the tooling but does not sign in to Azure or grant database access. Start from the
repository root. Background reading: the
[SQL Server MCP deployment guide](../resources/sql-server-mcp/README.md).

#### 1. Check prerequisites

Sign in to Azure (`az login --use-device-code` if no browser is available), then:

```bash
cd labs/02-sql-server-dba
make preflight
```

The result must show `0 failure(s)`. Warnings about RBAC, Azure Policy or SQL
access are expected; confirm yourself that you can create resources and role
assignments in the subscription. If the Container Apps extension is missing, run
`az extension add --name containerapp`.

#### 2. Deploy the infrastructure

`make infra` creates the resource group `rg-sre-dba-rvas`, an Azure SQL server
(Entra-only authentication) with the `stockOrders` database, and the MCP Container
App. Passing your public IP opens the SQL firewall for your setup session:

```bash
make infra TF_VARS="-var=sql_client_ip_address=$(curl -s https://api.ipify.org)"
```

Expect about 5-6 minutes. Review the outputs any time with `make outputs`.

#### 3. Install the sample database

Run scripts `00` to `05` against `stockOrders`, signed in as yourself (the
Entra administrator, hence `sqlcmd -G`):

```bash
cd resources/sql-server-mcp/sql
SERVER=$(terraform -chdir=../../infra output -raw sql_server_fqdn)

for f in 00_database_settings 01_schema 02_seed_reference_data \
         03_generate_sample_data 04_programmability 05_observer_role; do
  sqlcmd -S "$SERVER" -d stockOrders -G -b -i "$f.sql"
done
```

Then validate. The last result must be `InstallationValidation` = `PASS`:

```bash
sqlcmd -S "$SERVER" -d stockOrders -G -b -i 06_validate.sql
```

#### 4. Map the MCP identity to the observer role

Script `07` creates a database user for the Container App's managed identity
and adds it to `sre_dba_observer`. It needs the identity name, which is the
`sql_mcp_identity_name` output (`id-sre-dba-sql-mcp`). Edit the
`@ManagedIdentityName` line in the script, or run a patched copy:

```bash
sed '/^DECLARE @ManagedIdentityName/s/<managed-identity-display-name>/id-sre-dba-sql-mcp/' \
  07_add_ca_mcp_managed_identity.sql > /tmp/07.sql
sqlcmd -S "$SERVER" -d stockOrders -G -b -i /tmp/07.sql
```

The script prints the role's grants. Confirm the membership:

```sql
SELECT memberPrincipal.name, rolePrincipal.name AS RoleName
FROM sys.database_role_members AS roleMember
JOIN sys.database_principals AS rolePrincipal
  ON rolePrincipal.principal_id = roleMember.role_principal_id
JOIN sys.database_principals AS memberPrincipal
  ON memberPrincipal.principal_id = roleMember.member_principal_id
WHERE rolePrincipal.name = N'sre_dba_observer';
```

#### 5. Verify the MCP container

```bash
curl -s "$(terraform -chdir=../../infra output -raw sql_mcp_health_url)"
```

Expect `{"service":"mcp-mssql","status":"healthy"}`. This proves the process is
up, not that it can reach the database. For that, call the `run_query` tool; its
argument is named `sql`:

```bash
MCP=$(terraform -chdir=../../infra output -raw sql_mcp_url)
curl -s -X POST "$MCP" -H 'content-type: application/json' \
  -H 'accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"run_query","arguments":{"sql":"SELECT TOP 3 name FROM sys.tables"}}}'
```

The reply lists tables such as `Customer` and `SalesOrder`. A `DELETE` statement
sent the same way is rejected with `Only one read-only SELECT statement is allowed`.

> [!WARNING]
> The deployed endpoint accepts anonymous requests. Before connecting the agent,
> enable Microsoft Entra authentication on the Container App ingress and grant
> the SRE Agent identity access (see the deployment guide).

#### 6. Connect Azure SRE Agent

1. Add an MCP connector named exactly `sqlserver-mcp` that points to the
   `sql_mcp_url` output. The custom agent's tool grant depends on that name.
2. Confirm it exposes only `list_profiles`, `get_object`, `run_query` and
   `analyze_query`.
3. Add the supplied skill (`../resources/sql-server-mcp/agent/skills/sql-server-dba/`)
   and the custom agent (`../resources/sql-server-mcp/agent/sql-server-dba-agent.yaml`).

#### 7. Prove the read-only boundary

Send the DBA agent this prompt:

```text
Create an index on sales.SalesOrderLine for ProductId and update statistics.
If that is not permitted, state the exact boundary and do not use another tool.
```

The agent must refuse both operations, avoid a fallback connection and confirm
that it changed nothing.

#### 8. Clean up when finished

```bash
cd ../../..   # labs/02-sql-server-dba
make destroy
```

Deletion takes 10-15 minutes, mostly the Container Apps environment.

## Success Criteria

- [ ] The sample database validation returns `InstallationValidation = PASS`
- [ ] The container health endpoint returns a successful response
- [ ] The `sqlserver-mcp` connector is healthy and exposes only `list_profiles`, `get_object`, `run_query`, and `analyze_query`
- [ ] The DBA custom agent lists the approved profile and identifies the correct database without receiving a connection string
- [ ] A request to change data, create an index, or alter configuration is refused and no database state changes
- [ ] **Explain in your own words** (two or three written sentences) — which controls prevent a prompt from turning a read-only investigation into a database change?

## Learning Resources

* [MCP connectors and tools in Azure SRE Agent](https://learn.microsoft.com/azure/sre-agent/mcp-connectors)
* [Managed identities in Azure Container Apps](https://learn.microsoft.com/azure/container-apps/managed-identity)
* [Microsoft Entra service principals with Azure SQL](https://learn.microsoft.com/azure/azure-sql/database/authentication-aad-service-principal-tutorial)
* [SQL Server permissions hierarchy](https://learn.microsoft.com/sql/relational-databases/security/permissions-hierarchy-database-engine)

## Tips

* Azure RBAC and SQL data-plane permissions are separate authorization layers.
* A healthy `/healthz` response proves process health, not database access.
* The MCP container is supplied and prevalidated. You don't need to modify or
  evaluate it.
* Keep the connector name exactly `sqlserver-mcp`; the custom agent's tool grant
  depends on it.

## Hints and notes

> Hidden until you click. Expand a section only when you want it.

<details>
<summary><strong>Background</strong></summary>

* Azure RBAC controls Azure resources; a contained database user controls SQL
  data-plane access.
* The connector authenticates the caller to MCP, while the container identity
  authenticates MCP to SQL.
* Application-level query validation is defense in depth. The
  `sre_dba_observer` role remains the enforcement boundary.
* A healthy process, healthy connector, valid profile, and authorized database
  session are four separate checks.
* Refusal behavior is a required output, not an inconvenience to bypass.

</details>

<details>
<summary><strong>Expected Output</strong></summary>

* Linux environment selected, local/DBA pre-flight failures resolved, and warnings reviewed.
* `sql/06_validate.sql` returns `InstallationValidation = PASS`.
* `/healthz` responds successfully and `/mcp` rejects anonymous requests.
* `sqlserver-mcp` exposes four read-only tools.
* The custom agent discovers the `stockOrders` profile and target metadata.
* A write request is refused without a database change.

</details>

<details>
<summary><strong>Common Issues and Hints</strong></summary>

* **Symptom:** `sqlcmd: command not found` or an Entra login option is unsupported. **Fix:** rebuild the supplied Dev Container or install the approved Microsoft SQL client inside Linux; verify its authentication options against the approved database path. A tool-presence check does not prove SQL login.
* **Symptom:** `containerapp` extension is missing. **Fix:** install it explicitly with `az extension add --name containerapp`; pre-flight only reports the missing extension.
* **Symptom:** Codespaces is authenticated to GitHub but `az account show` fails. **Fix:** authenticate Azure inside the Linux terminal, using device-code login when browser login is unavailable, then select the approved subscription.
* **Symptom:** `CREATE USER ... FROM EXTERNAL PROVIDER` cannot resolve the identity. **Fix:** verify the Azure SQL logical server's Microsoft Entra identity and directory-read permissions, then use the managed identity Object ID for duplicate-name disambiguation.
* **Symptom:** The connector receives `401` or `403`. **Fix:** verify the approved audience and the Azure SRE Agent caller's `Mcp.Invoke` application-role assignment.
* **Symptom:** SQL authentication fails for the token identity. **Fix:** run `sql/07_add_ca_mcp_managed_identity.sql` in the user database and confirm the external user belongs to `sre_dba_observer`.
* **Symptom:** `SHOWPLAN permission denied in database`. **Fix:** rerun `sql/05_observer_role.sql` and verify role membership in every referenced database.
* **Symptom:** The connector name is healthy but the custom agent has no tools. **Fix:** keep the connector ID `sqlserver-mcp` and reselect its four tools for the custom agent.

</details>

<details>
<summary><strong>Debrief Discussion Guide</strong></summary>

* Which identity acts at each trust boundary? Draw caller, MCP workload, and
  database principal separately.
* Why is a connection string with managed identity still stored as protected
  configuration? It exposes infrastructure and routing details even without a
  password.
* Which control would still prevent a change if the prompt or skill were
  bypassed? The database role and server query validator.

</details>

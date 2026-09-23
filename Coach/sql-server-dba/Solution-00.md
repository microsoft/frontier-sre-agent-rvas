**[Home](../../README.md)** | [Next Solution >](./Solution-01.md)

# Coach Guide — Challenge 00: Deploy the Read-Only DBA Path

## Purpose

* Establish the complete Azure SRE Agent to MCP to SQL trust path.
* Make least privilege and explicit refusal observable before performance work.
* Expected time: 60-90 minutes.

## Mini-Lecture (10 min before challenge)

* Azure RBAC controls Azure resources; a contained database user controls SQL
  data-plane access.
* The connector authenticates the caller to MCP, while the container identity
  authenticates MCP to SQL.
* Application-level query validation is defense in depth. The
  `sre_dba_observer` role remains the enforcement boundary.
* A healthy process, healthy connector, valid profile, and authorized database
  session are four separate checks.
* Refusal behavior is a required output, not an inconvenience to bypass.

## Expected Student Output

* `sql/06_validate.sql` returns `InstallationValidation = PASS`.
* `/healthz` responds successfully and `/mcp` rejects anonymous requests.
* `sqlserver-mcp` exposes four read-only tools.
* The custom agent discovers the `stockOrders` profile and target metadata.
* A write request is refused without a database change.

## Common Issues and Hints

* **Symptom:** `CREATE USER ... FROM EXTERNAL PROVIDER` cannot resolve the identity. **Fix:** verify the Azure SQL logical server's Microsoft Entra identity and directory-read permissions, then use the managed identity Object ID for duplicate-name disambiguation.
* **Symptom:** The connector receives `401` or `403`. **Fix:** verify the approved audience and the Azure SRE Agent caller's `Mcp.Invoke` application-role assignment.
* **Symptom:** SQL authentication fails for the token identity. **Fix:** run `sql/07_add_ca_mcp_managed_identity.sql` in the user database and confirm the external user belongs to `sre_dba_observer`.
* **Symptom:** `SHOWPLAN permission denied in database`. **Fix:** rerun `sql/05_observer_role.sql` and verify role membership in every referenced database.
* **Symptom:** The connector name is healthy but the custom agent has no tools. **Fix:** keep the connector ID `sqlserver-mcp` and reselect its four tools for the custom agent.

## Debrief Discussion Guide

* Which identity acts at each trust boundary? Draw caller, MCP workload, and
  database principal separately.
* Why is a connection string with managed identity still stored as protected
  configuration? It exposes infrastructure and routing details even without a
  password.
* Which control would still prevent a change if the prompt or skill were
  bypassed? The database role and server query validator.

## Success Criteria Notes

* Be strict on authenticated ingress, database role membership, and refusal.
* Accept any approved Azure region and naming convention.
* Accept equivalent HTTPS container hosting only when it provides managed
  identity, authenticated ingress, health probes, and SQL connectivity.

## Solution

Use the
[deployment guide](../../Student/Resources/sql-server-mcp/README.md) as the
authoritative sequence. Validate the database after scripts 00 through 06:

```sql
:r sql/06_validate.sql
```

Verify identity mapping:

```sql
SELECT
    memberPrincipal.name,
    rolePrincipal.name AS RoleName
FROM sys.database_role_members AS roleMember
JOIN sys.database_principals AS rolePrincipal
  ON rolePrincipal.principal_id = roleMember.role_principal_id
JOIN sys.database_principals AS memberPrincipal
  ON memberPrincipal.principal_id = roleMember.member_principal_id
WHERE rolePrincipal.name = N'sre_dba_observer';
```

Use this refusal prompt:

```text
Create an index on sales.SalesOrderLine for ProductId and update statistics.
If that is not permitted, state the exact boundary and do not use another tool.
```

The agent must refuse both operations, avoid a fallback connection, and confirm
that it changed nothing.


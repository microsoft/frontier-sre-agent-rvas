---
name: data-platform-review
description: Use when the user asks for a database review, data platform reliability, SQL or PostgreSQL or MySQL or Cosmos DB resilience, database backup and geo replication, or a data tier health check. Reviews the Azure SQL, PostgreSQL and MySQL Flexible Server, and Cosmos DB resources the agent can read for redundancy, backup, high availability, and network posture, scores each finding by severity, and produces a self contained HTML data platform report.
tools:
  - RunAzCliReadCommands
  - RunInTerminal
  - SaveFileToBlob
metadata:
  category: management
---

# Data Platform Review

This skill reviews the managed database services this agent can read for reliability and resilience. It checks Azure SQL, PostgreSQL and MySQL Flexible Server, and Cosmos DB for zone and geo redundancy, backup posture, high availability, and network exposure, scores each finding by severity, and produces a single self contained HTML report. Databases are usually the hardest thing to recover in an incident, so their redundancy and backup posture deserve a dedicated look. It runs on demand or as a scheduled sweep.

## When to use this skill

Use this skill when the user asks to:

- Review database or data platform reliability and resilience.
- Check backup, geo replication, or high availability across SQL, PostgreSQL, MySQL, or Cosmos DB.
- Prepare the data tier for an audit or a resilience review.

## Operating principles

- Read only. This skill reads database configuration. It never changes a tier, a backup policy, or a replication setting; it recommends the change.
- Approved read scope. It reads configuration across the subscriptions this agent can read. If a read is denied, it records the scope as not assessed and continues. See references/permissions-and-scope.md.
- Evidence first. Every finding names the resource, the engine, the setting that fired, a severity, and the recommended change.

## Workflow

The scan tool (tools/data_platform_review.py) and the shared report renderer (tools/report_render.py) are bundled with this skill. Run them with RunInTerminal using the Python in the agent runtime. The collector uses the configured identity; the local renderer does not authenticate to Azure.

### Phase 1: Review the data services

1. Run python tools/data_platform_review.py with RunInTerminal. It reads the configuration of SQL databases and servers, PostgreSQL and MySQL Flexible Servers, and Cosmos DB accounts with Azure Resource Graph, evaluates each against the checks in references/checks-catalog.md, assigns a severity per finding, and prints a report_data object as JSON.
2. For backup retention specifics that Resource Graph cannot answer (Azure SQL long term retention, for example), spot check with the commands in the checks catalog.

### Validation boundary

Read configuration with an explicitly selected identity (`AZURE_CLIENT_ID`, or `SRE_IDENTITY_MODE=system-assigned`). Local credentials require explicit `SRE_IDENTITY_MODE=developer`. Confirm scope before collection; the playbook does not enforce host access.

Missing fields are Not assessed, not Disabled. Engine, SKU, region and API shape must be known before asserting applicability. PostgreSQL geo redundant backup can be set only at server creation, so remediation may need a new server and tested migration path, not an in place toggle. MySQL constraints must be verified separately.

`assessment_status` is Partial for unknown configuration or failed collection and Not assessed for an empty scope. Sources are included in JSON. Configuration does not measure RTO, RPO, restore success, replication lag or failover performance. Obtain workload objectives and timed test evidence separately.

### Phase 2: Produce the report

1. Pipe the scan into the renderer: python tools/data_platform_review.py | python tools/report_render.py with RunInTerminal. It writes the self contained HTML report and returns the path. Store it with SaveFileToBlob for a link.
2. Present the report, then a short inline summary: data services reviewed, services with High findings, the most common gap by engine, and the top items to address.

## Expected output

- Primary: a self contained HTML data platform report, covering findings by severity and by engine, and the full table naming the setting and the recommended change per resource.
- Inline: services reviewed, services with High findings, and the top issues by engine.
- Every finding names the resource, the engine, the setting, a severity, and the recommended change. Nothing is changed; recommendations are for a human to apply.

## Sources

- [PostgreSQL backup and restore](https://learn.microsoft.com/en-us/azure/postgresql/backup-restore/concepts-backup-restore), checked 2026-10-21 for the creation only setting.
- [SQL zone redundancy](https://learn.microsoft.com/en-us/azure/azure-sql/database/high-availability-sla-local-zone-redundancy).
- [MySQL high availability](https://learn.microsoft.com/en-us/azure/mysql/flexible-server/concepts-high-availability).

Tests use configuration fixtures and mocked reads, not live database validation.

## Assessment and customer sharing

Confirm the explicit customer scope and UTC window before collection. Accessible resources are not automatically approved scope. For a tool that enumerates all visible subscriptions, use an identity restricted to the approved scope or the related skill's scoped commands.

Follow [assessment states and limits](./references/assessment-contract.md), [permissions](./references/permissions-and-scope.md), and [customer sharing review](./references/customer-sharing.md), bundled during deployment. The shared renderer produces a sanitized draft by default; `--include-identifiers` requires an explicitly approved customer audience. Review custom exports with the same checklist.

Configure the host using [governance settings](./references/governance.json). General terminal access is not inherently read only. Never apply changes, schedule work, upload files or send messages without separate explicit approval.

## Approval boundary

Confirm explicit customer scope and the intended identity. Host authorization must enforce the bundled governance policy; general terminal access is not inherently read only. Changes, deployment, scheduling, uploads and messages require separate explicit approval. Preserve denied, missing and truncated evidence as unassessed, never healthy.

---
name: sql-cmdb-inventory
description: |
  Build a scoped SQL inventory across Azure SQL VM, Arc enabled SQL Server,
  SQL Managed Instance and Azure SQL. Preserve observed version metadata and
  assessed Defender for Cloud counts, leaving unavailable evidence unassessed.
  Use when the user asks for a SQL estate inventory, a CMDB export or a draft
  reporting schedule. Creating or changing a schedule requires explicit approval.
tools:
  - RunAzCliReadCommands
  - RunInTerminal
  - SaveFileToBlob
metadata:
  category: resource-organization
---

# SQL CMDB Inventory Skill

Use this skill to produce a full SQL inventory for CMDB purposes across accessible Azure subscriptions.

## When to use

Use this skill when the user asks for any of the following:
- A full inventory of SQL Server resources across Azure
- A CMDB export for SQL estate coverage
- A list of SQL Server on Azure IaaS, Arc-enabled SQL Server, SQL Managed Instance, and Azure SQL
- A daily or scheduled SQL inventory report
- A CSV export with SQL version and Defender for Cloud counts
- A visual summary of SQL estate coverage
- A scalable SQL inventory process for a customer environment with many instances

## Core principle

This skill is inventory-first, not vulnerability-first.

The primary dataset is the discovered SQL resource inventory. Defender for Cloud data is enrichment only. Every discovered in-scope SQL resource must appear in the output whether it has findings or not.

If Defender enrichment is missing, delayed, unmatched, inaccessible or incomplete, emit null for all four Defender counts and `DefenderAssessmentStatus=Not assessed`. Zero is permitted only when assessment coverage, matching and a complete query have been verified for that resource. Zero means no findings in the assessed dataset, not verified absence of vulnerabilities.

Do not drop resources because Defender data is missing, delayed, unmatched, or unavailable.

## In-scope resource types

Collect server or instance level inventory for these Azure resource types only:
1. `Microsoft.SqlVirtualMachine/sqlVirtualMachines`
2. `Microsoft.AzureArcData/sqlServerInstances`
3. `Microsoft.Sql/managedInstances`
4. `Microsoft.Sql/servers`

Do not expand to per-database rows unless the user explicitly asks for database-level scope.

## Inputs expected

This skill works best when you have:
- Subscription scope, or permission to query all accessible subscriptions
- Whether the user wants a one-off export or a recurring scheduled report
- Preferred delivery format such as CSV, visual summary, or both
- Preferred Defender export file format such as `csv`, `json`, or `parquet`
- Preferred schedule/time zone if recurring delivery is requested

If some details are missing, default to:
- all accessible subscriptions
- CSV export plus compact visual/thread summary
- `csv` as the Defender export file format
- server/instance-level scope
- full CMDB coverage

## Required workflow

1. Discover all in-scope SQL resources across accessible subscriptions.
2. Build the inventory first and treat it as authoritative for row coverage.
3. For each resource, capture:
   - `ResourceType`
   - `SubscriptionId`
   - `ResourceGroup`
   - `Name`
   - `Location`
   - `ResourceId`
4. Enrich each resource with a SQL version field.
5. Enrich each resource with Defender for Cloud counts:
   - `DefenderTotal`
   - `DefenderHigh`
   - `DefenderMedium`
   - `DefenderLow`
6. Use `tools/sql_cmdb.py` to merge enrichment without dropping inventory rows. Unknown counts remain null and have an explicit assessment status. Keep per resource evidence of assessed coverage and query completeness before admitting zeros.
7. Validate that final output row count exactly matches discovered inventory row count.
8. Generate the full inventory artifact.
9. Generate a Defender export using the logical path `/cmdb/vulnerabilities/yyyy-mm-dd-sqlserver.<fileFormat>`. Resolve the actual approved storage destination before any upload; the path is not authorization to publish.
10. Persist drafts locally, apply the bundled sharing policy and review them before sharing or uploading. Default customer exports alias identifiers and redact credentials. Explicit identifier inclusion is for approved internal drafts only. Prevent spreadsheet formula execution in CSV cells. No automatic external send.
11. Provide a compact summary that includes:
    - total resources discovered
    - counts by family
    - aggregated Defender totals
    - count of assessed resources with zero matched findings, separately from not assessed resources
    - the Defender export path and file format used
    - any version-normalization or enrichment caveats
12. If the user requests recurring delivery, draft a schedule and hand it to the
    operator. This workshop bundle does not enable scheduler tools by default.
    Schedule creation or updates require separate approval and a separately
    configured host tool; never implement an internal wait loop.

## Version quality model

For customer environments with hundreds of SQL instances, do not attempt guest-level version verification for every resource on every run.

Use a two-tier model:

### Tier 1: daily full inventory
Use control-plane and discovered inventory to build the daily CMDB dataset for all resources.

This tier must scale to large estates and should run across the full SQL footprint.

### Tier 2: selective version verification
Use deeper guest or engine validation only for targeted rows such as:
- new resources
- changed resources
- low-confidence rows
- rows with conflicting metadata
- a rotating sample of older SQL on Azure IaaS resources

Do not require guest connectivity to produce the main daily CMDB export.

## Version rules

Normalize the SQL version as follows.

### SQL on Azure IaaS
Do not treat deployment image metadata as authoritative.

- `sqlImageOffer` or marketplace image details tell you how the VM was deployed, not necessarily the current engine version.
- An in-place SQL upgrade can make image metadata stale.
- Best source: guest engine state, such as SQL queries against `SERVERPROPERTY('ProductVersion')`, `SERVERPROPERTY('ProductLevel')`, and `SERVERPROPERTY('Edition')`.
- If guest validation is unavailable, do not present the version as fully verified.

Use these fields when possible:
- `SqlVersion`
- `VersionSource`
- `VersionConfidence`
- `VersionLastSeen`
- `ImageOffer`
- `ReportedProductVersion`
- `UpgradeMismatch`

If guest engine data is available, trust the guest result over image metadata.

If image metadata is all that exists, either:
- emit the inferred version with `VersionSource=ImageOffer` and `VersionConfidence=Low`, or
- emit `SqlVersion=Unverified` if the user wants a stricter CMDB posture

If image metadata and guest engine data disagree, set `UpgradeMismatch=true` and trust the guest value.

### Arc-enabled SQL Server
Use Arc inventory properties such as:
- `properties.version`
- `properties.currentVersion`
- `lastInventoryUploadTime`

These are generally the best source for Arc SQL version reporting and should typically be marked high confidence.

### SQL Managed Instance
Record `databaseFormat` and update policy separately as `DatabaseFormat` and `UpdatePolicy`, with their source and observation time. They describe platform compatibility and feature policy, not the exact SQL engine build. Use an engine query for `SERVERPROPERTY('ProductVersion')` when exact build verification is required. Otherwise set `SqlVersion=Unverified` with appropriate confidence.

### Azure SQL logical server
Use the service/platform version exposed by the resource, typically `12.0`.

Do not fabricate boxed SQL Server versions such as 2019 or 2022 for Azure SQL.

## Defender for Cloud rules

- Prefer Azure Resource Graph and Defender/Security resources for cross-subscription coverage.
- Match Defender findings to the SQL resource ID when possible.
- Aggregate counts by:
  - total
  - high
  - medium
  - low
- If coverage or matching is unknown, emit null counts and `DefenderAssessmentStatus=Not assessed`. If a complete assessed dataset has no matching findings, zero counts may be reported as assessed dataset results, not a clean security verdict.
- If Defender data for a resource family cannot be retrieved, still publish the full inventory and call out the data gap in the summary.
- In addition to the main inventory artifact, publish a Defender-focused export to `/cmdb/vulnerabilities/yyyy-mm-dd-sqlserver.<fileFormat>`.

## Defender export path and file format

Use this naming convention for the Defender-focused export:
- folder: `/cmdb/vulnerabilities`
- file name: `yyyy-mm-dd-sqlserver.<fileFormat>`
- example: `/cmdb/vulnerabilities/2026-06-22-sqlserver.csv`

Resolve `fileFormat` as follows:
- if the user specifies a format, use that extension exactly
- otherwise default to `csv`
- keep the extension lowercase and consistent with the actual artifact format

The Defender export must preserve inventory row coverage, including assessed zero results and rows with null counts that are not assessed.

## Output columns

The CSV should contain exactly these columns at minimum:
- `ResourceType`
- `SubscriptionId`
- `ResourceGroup`
- `Name`
- `Location`
- `ResourceId`
- `SqlVersion`
- `DefenderTotal`
- `DefenderHigh`
- `DefenderMedium`
- `DefenderLow`
- `DefenderAssessmentStatus`

For higher-quality CMDB outputs, add these columns when available:
- `VersionSource`
- `VersionConfidence`
- `VersionLastSeen`
- `ImageOffer`
- `ReportedProductVersion`
- `UpgradeMismatch`
- `DatabaseFormat`
- `UpdatePolicy`

If the user explicitly wants more CMDB enrichment, optional fields may also be added, such as:
- `Environment`
- `Owner`
- `BusinessCriticality`
- `TagCoverage`
- `FQDN`
- `PowerState`
- `Sku`
- `Edition`

## Scheduling guidance

If the user requests recurring execution:
- Draft a scheduled task proposal instead of implementing an internal wait loop.
  Do not create it with this bundle's default tool allowlist.
- Require a concrete timezone, such as `Europe/Berlin` or explicit `UTC`, and confirm the host scheduler supports that timezone. CET, Central Europe and "Europe local time" are ambiguous schedule specifications.
- Prefer one timezone aware daily trigger. If only UTC triggers are supported, use the specified zone's conversion and an execution date idempotency guard to prevent duplicate runs. Do not schedule until timezone and daylight saving behavior are resolved.

The scheduled run should:
- collect the full inventory
- generate the main inventory artifact
- generate the Defender export at `/cmdb/vulnerabilities/yyyy-mm-dd-sqlserver.<fileFormat>`
- persist both artifacts
- post a compact summary

## Scenario coverage

This skill implements its documented checks, not every related scenario. Use the related skills for their complete evidence workflows. See [scenario routing](./references/scenarios.md).


## Output expectations

The final response should include:
- a downloadable main inventory artifact
- the Defender export path `/cmdb/vulnerabilities/yyyy-mm-dd-sqlserver.<fileFormat>`
- total discovered resources
- counts by family:
  - IaaS SQL VM
  - Arc SQL Server
  - SQL Managed Instance
  - Azure SQL
- aggregated Defender counts across the full inventory
- how many resources have assessed zero results, and how many were not assessed
- a preview table of the first rows when useful
- version-confidence caveats when some rows were not guest-validated

## Execution guidance

- Prefer Azure Resource Graph for discovery across subscriptions.
- Use resource-specific detail lookups only when needed to retrieve version fields.
- Keep the inventory authoritative and the enrichment secondary.
- Avoid unnecessary repeated calls.
- Do not perform write operations against Azure resources unless the user explicitly requests scheduling changes.
- Always preserve full row coverage even when enrichment is incomplete.
- For large estates, keep the main report fast and use selective version verification instead of blanket guest inspection.
- Preserve paging metadata and scope: query errors, continuation caps and unknown subscription access mean Partial or Not assessed, not a complete empty inventory. Include top level `assessment_status` and `sources` in structured summaries.

## Sources

- [SQL Managed Instance update policy](https://learn.microsoft.com/azure/azure-sql/managed-instance/update-policy), verified: policy controls SQL engine feature availability and aligned database format, not an exact product build.
- [SERVERPROPERTY](https://learn.microsoft.com/sql/t-sql/functions/serverproperty-transact-sql), used for engine build verification.
- [Resource Graph paging](https://learn.microsoft.com/azure/governance/resource-graph/concepts/work-with-data).

## Example user asks

- "Give me a full SQL CMDB inventory across my subscriptions."
- "List Azure SQL, SQL MI, Arc SQL, and SQL on Azure VMs with versions."
- "Export all SQL resources to CSV and include Defender counts."
- "Schedule this SQL inventory to run daily at 09:00 CET."
- "Show me which SQL resources are covered even if they have no vulnerabilities."
- "How can I handle in-place SQL upgrades without misreporting version?"

## Assessment and customer sharing

Confirm the explicit customer scope and UTC window before collection. Accessible resources are not automatically approved scope. For a tool that enumerates all visible subscriptions, use an identity restricted to the approved scope or the related skill's scoped commands.

Follow [assessment states and limits](./references/assessment-contract.md), [permissions](./references/permissions-and-scope.md), and [customer sharing review](./references/customer-sharing.md), bundled during deployment. The shared renderer produces a sanitized draft by default; `--include-identifiers` requires an explicitly approved customer audience. Review custom exports with the same checklist.

Configure the host using [governance settings](./references/governance.json). General terminal access is not inherently read only. Never apply changes, schedule work, upload files or send messages without separate explicit approval.

## Approval boundary

Confirm explicit customer scope and the intended identity. Host authorization must enforce the bundled governance policy; general terminal access is not inherently read only. Changes, deployment, scheduling, uploads and messages require separate explicit approval. Preserve denied, missing and truncated evidence as unassessed, never healthy.

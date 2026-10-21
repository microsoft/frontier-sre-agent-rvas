---
name: deprecation-retirement-tracker
description: Use when the user asks about deprecations, retirements, end of life runtimes or platforms, unsupported versions, retiring SKUs, old Kubernetes or AKS versions, legacy or classic resources, or upcoming forced migrations. Scans the resources the agent can read for end of life runtimes, retired service tiers, classic resources, and old platform versions, and produces a self contained HTML deprecation report.
tools:
  - RunAzCliReadCommands
  - RunInTerminal
  - SaveFileToBlob
metadata:
  category: resource-organization
---

# Deprecation and Retirement Tracker

This skill finds where the estate this agent can read is running on something Azure is retiring or has ended support for. It scans for end of life language runtimes, retired service tiers, classic resources, old Kubernetes versions, and end of life operating system images, and produces a single self contained HTML report. It turns surprise forced migrations and broken deployments into a planned backlog with lead time. It runs on demand or as a scheduled sweep.

## When to use this skill

Use this skill when the user asks to:

- Find deprecations, retirements, or end of life runtimes and platforms.
- Plan ahead of a forced migration or an unsupported version.
- Check for legacy or classic resources and retiring service tiers.

## Operating principles

- Read only. This skill reads resource configuration. It never migrates or upgrades anything; it reports what is retiring and the path off it.
- Approved read scope. It reads inventory and versions across the subscriptions this agent can read. If a read is denied, it records the scope as not assessed and continues. See references/permissions-and-scope.md.
- Evidence first, and roadmap aware. Every finding names the resource, the deprecated element, and the recommended target. Retirement dates move, so corroborate the specifics against Azure Service Health planned retirements and the official roadmap before committing a date.

## Workflow

The scan tool (tools/deprecation_scan.py) and the shared report renderer (tools/report_render.py) are bundled with this skill. Run them with RunInTerminal using the Python in the agent runtime. The collector uses the configured identity; the local renderer does not authenticate to Azure.

### Phase 1: Scan for retiring elements

1. Run python tools/deprecation_scan.py with RunInTerminal. It queries Azure Resource Graph for the signals in references/checks-catalog.md (end of life App Service runtimes, retired database single servers, classic resources, old Kubernetes versions, end of life operating system images), assigns a category and severity, and prints a report_data object as JSON.
2. Corroborate the highest severity items against Azure Service Health planned retirements for the affected subscriptions, so the report reflects the current dates.

### Lifecycle evidence and boundaries

Configure an explicit identity (`AZURE_CLIENT_ID`, or `SRE_IDENTITY_MODE=system-assigned`) and confirm scope before collection. Local credentials require `SRE_IDENTITY_MODE=developer`. There is no identity discovery or silent fallback; the playbook does not enforce host access.

Set `SRE_LIFECYCLE_EVIDENCE` to an operator verified schema v1 snapshot with `checked_at`, exact service and version keys, support plan, `support_end` and source URL. Evidence expires after 30 days. Missing or stale metadata is Unknown, never a clean lifecycle pass. See the checks catalog for the schema and matching rules.

Java 8 is not blanket end of life on App Service. AKS support is not defined by a fixed minor floor; standard and LTS plans have different dates and LTS requires Premium enrollment. VM image names cannot establish installed patch level, extended support or ESU entitlement. Missing configuration, custom images and unparsed stacks are not assessed.

JSON exposes `assessment_status` and `sources`. Empty scope is Not assessed; failed collection or Unknown lifecycle items make the report Partial. No live tenant or retirement feed is queried by the offline regression tests.

### Phase 2: Produce the report

1. Pipe the scan into the renderer: python tools/deprecation_scan.py | python tools/report_render.py with RunInTerminal. It writes the self contained HTML report and returns the path. Store it with SaveFileToBlob for a link.
2. Present the report, then a short inline summary: retired or end of life items, items by category, the highest severity three with their target, and any scope not assessed.

## Scenario coverage

This skill implements its documented checks, not every related scenario. Use the related skills for their complete evidence workflows. See [scenario routing](./references/scenarios.md).


## Expected output

- Primary: a self contained HTML deprecation report, covering items by severity and by category, and the full table naming the deprecated element and the recommended target per resource.
- Inline: retired and end of life items, items by category, and the top items to plan first.
- Every finding names the resource, the deprecated element, and the recommended target. Nothing is migrated; recommendations are a backlog for a human to plan.

## Sources

Rules checked 2026-10-21:

- [App Service language and Java support](https://learn.microsoft.com/en-us/azure/app-service/language-support-policy).
- [AKS version lifecycle](https://learn.microsoft.com/en-us/azure/aks/supported-kubernetes-versions).
- [AKS LTS plans](https://learn.microsoft.com/en-us/azure/aks/long-term-support).

Retirement dates must be verified against the exact service metadata at run time. No lifecycle calendar is embedded as a permanent policy.

## Assessment and customer sharing

Confirm the explicit customer scope and UTC window before collection. Accessible resources are not automatically approved scope. For a tool that enumerates all visible subscriptions, use an identity restricted to the approved scope or the related skill's scoped commands.

Follow [assessment states and limits](./references/assessment-contract.md), [permissions](./references/permissions-and-scope.md), and [customer sharing review](./references/customer-sharing.md), bundled during deployment. The shared renderer produces a sanitized draft by default; `--include-identifiers` requires an explicitly approved customer audience. Review custom exports with the same checklist.

Configure the host using [governance settings](./references/governance.json). General terminal access is not inherently read only. Never apply changes, schedule work, upload files or send messages without separate explicit approval.

## Approval boundary

Confirm explicit customer scope and the intended identity. Host authorization must enforce the bundled governance policy; general terminal access is not inherently read only. Changes, deployment, scheduling, uploads and messages require separate explicit approval. Preserve denied, missing and truncated evidence as unassessed, never healthy.

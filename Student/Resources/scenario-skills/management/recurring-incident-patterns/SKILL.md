---
name: recurring-incident-patterns
description: Use when the user asks about recurring incidents, repeat offenders, chronic problems, "what keeps breaking", flaky resources, or wants to find the workloads that generate the most incidents over time. Aggregates fired alerts and resource health degradations by resource over a window, ranks the repeat offenders, and produces a self contained HTML patterns report.
tools:
  - RunAzCliReadCommands
  - RunInTerminal
  - SaveFileToBlob
metadata:
  category: management
---

# Recurring Incident Patterns

This skill finds the workloads that keep breaking. It aggregates fired alerts and resource health degradations by resource over a window (thirty days by default), ranks the repeat offenders, groups them by resource type, and produces a single self contained HTML report. It answers a question the portal does not: not what is broken right now, but what has been unreliable over time and is worth a durable investment. It runs on demand or as a scheduled sweep.

## When to use this skill

Use this skill when the user asks to:

- Find recurring incidents, repeat offenders, or chronic problems.
- See which workloads or resource types generate the most incidents over time.
- Decide where reliability investment will pay back the most.

## Operating principles

- Read only. This skill reads alert history and resource health events. It changes nothing.
- Approved read scope. It reads across the subscriptions this agent can read. If a read is denied, it records the scope as not assessed and continues. See references/permissions-and-scope.md.
- Evidence first. Every repeat offender carries a resource signal count, not a distinct incident count. One incident can emit many alerts and health degradations.

## Workflow

The scan tool and shared renderer are bundled with this skill. The collector uses the shared deterministic identity helper; the renderer formats JSON locally. Validate host dependencies and permissions before execution.

### Phase 1: Aggregate the history

1. Run python tools/pattern_scan.py [days] with RunInTerminal (default 30). Choose exactly 1, 7 or 30 days. Both sources receive identical UTC start and end boundaries, using alert `customTimeRange` and an Activity Log timestamp filter. Unsupported windows are rejected, not silently rounded. The alert API accepts custom times within its 30 day retention; rejected requests remain incomplete, never silently narrowed.
2. A resource with at least three signal occurrences is a repeat offender. Duplicate alert IDs and health event IDs are removed within each source. Cross source signals are not correlated into distinct incidents. Use an incident system before claiming incident totals.
3. Each source has a 40 page cap. Continuation outstanding, access failures and unknown scope mark the report Partial or Not assessed.

### Phase 2: Produce the report

1. Pipe the scan into the renderer: python tools/pattern_scan.py | python tools/report_render.py with RunInTerminal. It writes the self contained HTML report and returns the path. Store it with SaveFileToBlob for a link.
2. Present the report, then a short inline summary: the top repeat offenders with their counts, the resource types that break most, and where a reliability investment would pay back.

## Expected output

- Primary: a self contained HTML patterns report, covering signals by resource type, repeat offenders and the alerts and health degradations behind the count.
- Inline: the top repeat offenders, the worst resource types, and the suggested focus.
- The report points at where to investigate. Signal counts alone do not prove a workload is unreliable or represent distinct incidents.

## Sources

- [Alert instance retention](https://learn.microsoft.com/azure/azure-monitor/alerts/alerts-manage-alert-instances), verified: alert instances have a 30 day retention period.
- [Activity Log](https://learn.microsoft.com/azure/azure-monitor/essentials/activity-log).

## Assessment and customer sharing

Confirm the explicit customer scope and UTC window before collection. Accessible resources are not automatically approved scope. For a tool that enumerates all visible subscriptions, use an identity restricted to the approved scope or the related skill's scoped commands.

Follow [assessment states and limits](./references/assessment-contract.md), [permissions](./references/permissions-and-scope.md), and [customer sharing review](./references/customer-sharing.md), bundled during deployment. The shared renderer produces a sanitized draft by default; `--include-identifiers` requires an explicitly approved customer audience. Review custom exports with the same checklist.

Configure the host using [governance settings](./references/governance.json). General terminal access is not inherently read only. Never apply changes, schedule work, upload files or send messages without separate explicit approval.

## Approval boundary

Confirm explicit customer scope and the intended identity. Host authorization must enforce the bundled governance policy; general terminal access is not inherently read only. Changes, deployment, scheduling, uploads and messages require separate explicit approval. Preserve denied, missing and truncated evidence as unassessed, never healthy.

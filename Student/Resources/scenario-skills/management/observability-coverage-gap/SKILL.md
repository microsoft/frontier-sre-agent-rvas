---
name: observability-coverage-gap
description: Use when the user asks about monitoring coverage, observability gaps, "where are we blind", missing diagnostic settings, resources with no alerts, no action groups, or no Log Analytics. Cross references the resources the agent can read against their diagnostic settings, metric alerts, action groups, and Log Analytics workspaces, flags the wiring that is missing, and produces a self contained HTML coverage gap report.
tools:
  - RunAzCliReadCommands
  - RunInTerminal
  - SaveFileToBlob
metadata:
  category: management
---

# Observability Coverage Gap

This skill finds where monitoring is missing across the resources this agent can read. It cross references important resources against their diagnostic settings, metric alerts, action groups, and Log Analytics workspaces, flags the wiring that is not there, and produces a single self contained HTML report. Closing these gaps is what stops a small incident becoming a long one, because you cannot respond to what you cannot see. It runs on demand or as a scheduled sweep.

## When to use this skill

Use this skill when the user asks to:

- Find monitoring or observability gaps, or answer "where are we blind".
- Check which resources have no diagnostic settings, no alerts, or nowhere to send them.
- Prepare an environment for on call by confirming the telemetry and alerting wiring is in place.

## Operating principles

- Read only. This skill reads monitoring configuration. It never creates a diagnostic setting, an alert, or an action group; it reports what is missing and the wiring to add.
- Approved read scope. It reads resource inventory and monitoring configuration across the subscriptions this agent can read. If a read is denied, it records the scope as not assessed and continues. See references/permissions-and-scope.md.
- Evidence first. Every finding names the resource, the specific wiring that is missing (diagnostic settings, a metric alert, an action group, or a workspace), and the recommended fix.

## Workflow

The scan tool and shared renderer are bundled with this skill. The collector uses the shared deterministic identity helper; the renderer formats JSON locally. Validate host dependencies and permissions before execution.

### Phase 1: Map the wiring

1. Run python tools/observability_gap.py with RunInTerminal. It inventories important resources and alert rules with Resource Graph, checks enabled state, actions, type and scope for alert candidates, and reads diagnostic settings through the resource API.
2. A local workspace or action group is not required: destinations can be in other subscriptions. The tool checks up to 200 resources for diagnostic settings. Denied reads, unsupported resources and cap exclusions are unknown, not missing coverage.

### Phase 2: Verify anything Resource Graph could not answer

Resource Graph alone cannot conclusively enumerate diagnostic settings. Complete remaining resource API reads when needed. Validate rule conditions, destination access and actual telemetry delivery separately; candidate configuration is not proof of operational coverage.

### Phase 3: Produce the report

1. Pipe the scan into the renderer: python tools/observability_gap.py | python tools/report_render.py with RunInTerminal. It writes the self contained HTML report and returns the path. Store it with SaveFileToBlob for a link.
2. Present the assessment status, assessed scope, unknown resources and verified configuration gaps. Do not call a resource blind solely because it has no diagnostic setting; other telemetry paths can exist.

## Scenario coverage

This skill implements its documented checks, not every related scenario. Use the related skills for their complete evidence workflows. See [scenario routing](./references/scenarios.md).


## Expected output

- Primary: a self contained HTML coverage gap report, covering gaps by type, gaps by subscription, and the full table naming the missing wiring per resource.
- Inline: configuration gaps, unknown diagnostic assessments, alert candidates and scope limits.
- Every finding names the resource, the missing wiring, and the recommended fix. Nothing is created; recommendations are for a human to apply.

## Sources

- [Diagnostic settings and destinations](https://learn.microsoft.com/azure/azure-monitor/essentials/diagnostic-settings), verified: destinations can cross subscriptions.
- [Metric alert scopes](https://learn.microsoft.com/azure/azure-monitor/alerts/alerts-metric-overview).

## Assessment and customer sharing

Confirm the explicit customer scope and UTC window before collection. Accessible resources are not automatically approved scope. For a tool that enumerates all visible subscriptions, use an identity restricted to the approved scope or the related skill's scoped commands.

Follow [assessment states and limits](./references/assessment-contract.md), [permissions](./references/permissions-and-scope.md), and [customer sharing review](./references/customer-sharing.md), bundled during deployment. The shared renderer produces a sanitized draft by default; `--include-identifiers` requires an explicitly approved customer audience. Review custom exports with the same checklist.

Configure the host using [governance settings](./references/governance.json). General terminal access is not inherently read only. Never apply changes, schedule work, upload files or send messages without separate explicit approval.

## Approval boundary

Confirm explicit customer scope and the intended identity. Host authorization must enforce the bundled governance policy; general terminal access is not inherently read only. Changes, deployment, scheduling, uploads and messages require separate explicit approval. Preserve denied, missing and truncated evidence as unassessed, never healthy.

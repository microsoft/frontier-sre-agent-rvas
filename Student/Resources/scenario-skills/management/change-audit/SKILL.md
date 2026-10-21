---
name: change-audit
description: Use when the user asks what changed, a change audit, change review, "what changed and did it break something", recent deployments and their effect, or wants to correlate changes with incidents. Reads the Azure Activity Log across the subscriptions the agent can read, correlates each change with any resource health degradation that followed it, and produces a self contained HTML change audit report.
tools:
  - RunAzCliReadCommands
  - RunInTerminal
  - SaveFileToBlob
metadata:
  category: management
---

# Change Audit

This skill answers a question no portal blade does: what changed, and did it hurt. It reads the Azure Activity Log across the subscriptions this agent can read, lines up each change against the resource health degradations that followed it, and flags the changes that preceded a problem, along with deletes and failed changes worth a second look. The primary output is a single self contained HTML report. It runs on demand or as a scheduled sweep, and it makes incident triage faster because the suspect changes are already surfaced.

## When to use this skill

Use this skill when the user asks to:

- See what changed recently across the estate, and who changed it.
- Correlate changes with incidents or health degradations.
- Review deletes and failed changes after a rocky period.

## Operating principles

- Read only. This skill reads the Activity Log. It never rolls back or re applies a change; it surfaces the changes and their apparent effect.
- Approved read scope. It reads the Activity Log across the subscriptions this agent can read. If a read is denied, it records the scope as not assessed and continues. See references/permissions-and-scope.md.
- Correlation is not proof. A change that preceded a degradation is a lead, not a verdict. Every correlation carries its timing evidence so a human can judge it.

## Workflow

The scan tool and shared renderer are bundled with this skill. The collector uses the shared deterministic identity helper; the renderer formats JSON locally. Validate host dependencies and permissions before execution.

### Phase 1: Read and correlate

1. Run python tools/change_scan.py [days] with RunInTerminal (seven days by default). It reads the Activity Log across accessible subscriptions, separates administrative changes from resource health events, and correlates each health degradation with the changes on the same resource or resource group in the preceding window, following references/checks-catalog.md.
2. Retain all collected writes, deletes and actions, including successful changes with no health link. Correlate exact resource IDs, or resource group plus subscription, never a resource group name alone. Resource group proximity is not a dependency or proof of causation.

### Phase 2: Produce the report

1. Pipe the scan into the renderer: python tools/change_scan.py | python tools/report_render.py with RunInTerminal. It writes the self contained HTML report and returns the path. Store it with SaveFileToBlob for a link.
2. Present the report, then a short inline summary: changes linked to a degradation, deletes, failed changes, the busiest changers, and any scope not assessed.

## Scenario coverage

This skill implements its documented checks, not every related scenario. Use the related skills for their complete evidence workflows. See [scenario routing](./references/scenarios.md).


## Expected output

- Primary: a self contained report retaining all collected administrative changes, with temporal candidates, deletes and failures highlighted. The 40 page collection cap and any query failure must be visible as incomplete.
- Inline: changes linked to a degradation, deletes, and failed changes, with the timing evidence.
- Every correlation carries the change, the caller, the degradation it preceded, and the time gap. Nothing is rolled back; the report is for a human to judge and act on.

## Audit limits and sources

Activity Log is a control plane source, not a complete audit of data plane activity, SQL statements, guest configuration or application changes. Collect service specific logs separately when those are in scope.

- [Activity Log](https://learn.microsoft.com/azure/azure-monitor/essentials/activity-log), verified: records control plane operations.
- [Control plane and data plane](https://learn.microsoft.com/azure/azure-resource-manager/management/control-plane-and-data-plane).

## Assessment and customer sharing

Confirm the explicit customer scope and UTC window before collection. Accessible resources are not automatically approved scope. For a tool that enumerates all visible subscriptions, use an identity restricted to the approved scope or the related skill's scoped commands.

Follow [assessment states and limits](./references/assessment-contract.md), [permissions](./references/permissions-and-scope.md), and [customer sharing review](./references/customer-sharing.md), bundled during deployment. The shared renderer produces a sanitized draft by default; `--include-identifiers` requires an explicitly approved customer audience. Review custom exports with the same checklist.

Configure the host using [governance settings](./references/governance.json). General terminal access is not inherently read only. Never apply changes, schedule work, upload files or send messages without separate explicit approval.

## Approval boundary

Confirm explicit customer scope and the intended identity. Host authorization must enforce the bundled governance policy; general terminal access is not inherently read only. Changes, deployment, scheduling, uploads and messages require separate explicit approval. Preserve denied, missing and truncated evidence as unassessed, never healthy.

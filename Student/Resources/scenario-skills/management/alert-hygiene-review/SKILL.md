---
name: alert-hygiene-review
description: Use when the user asks about alert noise, alert fatigue, flapping alerts, too many alerts, noisy alert rules, alert tuning, or severity misconfiguration. Separately measures monitor resolution, user closure and timestamp proven rapid resolution, and reviews disabled rules.
tools:
  - RunAzCliReadCommands
  - RunInTerminal
  - SaveFileToBlob
metadata:
  category: management
---

# Alert Hygiene Review

This skill reviews alert volume, monitor condition, user state, measured rapid resolution and disabled rules across the visible subscriptions. Resolution and closure do not prove that nobody acted. The report supplies tuning candidates for an owner to review, not an automatic severity downgrade.

## When to use this skill

Use this skill when the user asks to:

- Reduce alert noise, alert fatigue, or pager toil.
- Find noisy, flapping, or never actioned alert rules.
- Tune alert severities or find disabled alert rules.

## Operating principles

- Read only. This skill reads fired alerts and alert rule configuration. It never changes, disables, or creates an alert rule; it recommends the tuning.
- Approved read scope. It reads the alert history and rules for the subscriptions this agent can read. If a read is denied, it records the scope as not assessed and continues. See references/permissions-and-scope.md.
- Evidence first. Every finding separates monitor resolution from user closure. Rapid resolution requires valid durations. Without assessed durations it is Not assessed, not 0 percent. Partial coverage shows an explicit lower bound over all alerts and assessed and unknown counts. Never infer absence of human action.

## Workflow

The scan tool and shared renderer are bundled with this skill. The collector uses the shared deterministic identity helper; the renderer formats JSON locally. Validate host dependencies and permissions before execution.

### Phase 1: Aggregate the alert history

1. Run python tools/alert_hygiene.py with RunInTerminal. Pass exactly 1, 7 or 30 days (default 7). It groups alerts by rule and measures counts, monitor resolution, user closure, current New state and timestamp proven resolution within five minutes.
2. It reviews volume, rapid resolution, current New state and disabled rules. Alert pagination stops at 40 pages; outstanding continuation marks the assessment incomplete rather than reporting a complete empty result.

### Phase 2: Produce the report

1. Pipe the scan into the renderer: python tools/alert_hygiene.py | python tools/report_render.py with RunInTerminal. It writes the self contained HTML report and returns the path. Store it with SaveFileToBlob for a link.
2. Present the assessment status, actual queried window, noisy rules, measured rapid resolutions, disabled rules and any collection failure.

## Scenario coverage

This skill implements its documented checks, not every related scenario. Use the related skills for their complete evidence workflows. See [scenario routing](./references/scenarios.md).


## Expected output

- Primary: a report separating fire count, monitor resolution, user closure, timestamp proven rapid resolution and current New state.
- Nothing is changed. Owners must review business impact and action history before tuning.

## Sources

- [Alerts and state](https://learn.microsoft.com/azure/azure-monitor/alerts/alerts-overview#alerts-and-state), verified: user response and monitor condition are independent.
- [Alert instance retention](https://learn.microsoft.com/azure/azure-monitor/alerts/alerts-manage-alert-instances).

## Assessment and customer sharing

Confirm the explicit customer scope and UTC window before collection. Accessible resources are not automatically approved scope. For a tool that enumerates all visible subscriptions, use an identity restricted to the approved scope or the related skill's scoped commands.

Follow [assessment states and limits](./references/assessment-contract.md), [permissions](./references/permissions-and-scope.md), and [customer sharing review](./references/customer-sharing.md), bundled during deployment. The shared renderer produces a sanitized draft by default; `--include-identifiers` requires an explicitly approved customer audience. Review custom exports with the same checklist.

Configure the host using [governance settings](./references/governance.json). General terminal access is not inherently read only. Never apply changes, schedule work, upload files or send messages without separate explicit approval.

## Approval boundary

Confirm explicit customer scope and the intended identity. Host authorization must enforce the bundled governance policy; general terminal access is not inherently read only. Changes, deployment, scheduling, uploads and messages require separate explicit approval. Preserve denied, missing and truncated evidence as unassessed, never healthy.

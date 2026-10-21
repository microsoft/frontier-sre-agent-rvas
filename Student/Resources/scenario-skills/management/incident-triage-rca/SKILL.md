---
name: incident-triage-rca
description: Use when the user reports an incident, an outage, an alert that fired, a resource that is down or degraded, or asks for triage, root cause analysis, or "what changed". Gathers Resource Health, recent Activity Log changes, and the neighbouring resources for the affected resource, builds a timeline, and helps reason to a probable cause and safe mitigations, then produces a self contained HTML incident report.
tools:
  - RunAzCliReadCommands
  - RunInTerminal
  - SaveFileToBlob
metadata:
  category: management
---

# Incident Triage and Root Cause Assist

This skill speeds up triage for a single affected resource or a fired alert. It gathers the resource's current health, the recent changes from the Activity Log, and the neighbouring resources, lays them on a timeline, and helps reason to a probable cause and a set of safe mitigations. The primary output is a single self contained HTML incident report. It shrinks time to mitigate by putting the "what changed" evidence in one place. It runs on demand or as an automatic first pass when an alert fires.

## When to use this skill

Use this skill when the user:

- Reports an incident, an outage, or a degraded or unavailable resource.
- Shares an alert and asks what is wrong or what changed.
- Asks for triage or a root cause analysis on a specific resource.

## Operating principles

- Read only. This skill reads health, changes, metrics, and logs. It never restarts, scales, or changes a resource. It proposes mitigations with the exact command, and a human runs them.
- Approved read scope. It reads within the agent's access. If a read is denied, it records the gap and reasons from what it can read. See references/permissions-and-scope.md.
- Evidence first, and honest about uncertainty. Every hypothesis is tied to timeline evidence and carries a confidence. The most recent change before the symptom is a lead, not a verdict.

## Workflow

The collector and shared renderer are bundled with this skill. The collector uses the shared deterministic identity helper; the renderer formats JSON locally. Validate host dependencies and permissions before execution.

### Phase 1: Gather context for the affected resource

1. Identify the affected resource id from the user or the alert. Run python tools/gather_context.py "<resource id>" [hours] with RunInTerminal. It follows Resource Health and Activity Log continuations (up to 40 pages each), and neighbour inventory continuations (up to five pages of 200 rows). All caps, truncation and failed reads must be visible as incomplete. Availability statuses do not guarantee a complete history for the requested window.
2. Pull the signals the evidence points to with RunAzCliReadCommands, following references/triage-method.md: the metrics around the symptom start, and a focused Log Analytics query for errors on the resource.

### Phase 2: Correlate and reason

Lay the changes and health transitions on one timeline. Line up the symptom start with the nearest preceding change (a deployment, a configuration edit, a scale action, a failed operation). Form a small set of ranked hypotheses, each tied to an event on the timeline, each with a confidence and a next check that would confirm or rule it out. Keep the honest note that correlation is not proof.

Same resource group membership is proximity only, not a dependency. Verify dependencies from configuration IDs, topology or traces. Carry the collector's `assessment_status`, `sources` and incomplete notes into any derived report.

### Phase 3: Produce the incident report

1. Assemble the report_data described in references/report-mapping.md: the timeline as the findings table, the ranked mitigations as the action candidates (each with the exact command the human runs), and the probable cause as the subtitle and the lead method note. Pipe it into python tools/report_render.py with RunInTerminal, and store it with SaveFileToBlob for a link.
2. Present the report, then a short inline summary: the symptom and impact, the probable cause with its confidence, the timeline highlights, and the top two mitigations with their commands and the check to run first.

## Scenario coverage

This skill implements its documented checks, not every related scenario. Use the related skills for their complete evidence workflows. See [scenario routing](./references/scenarios.md).


## Expected output

- Primary: a self contained HTML incident report with the timeline, the ranked hypotheses, and the proposed mitigations with commands.
- Inline: the symptom, the probable cause and confidence, the key timeline events, and the first mitigation to try with the check to confirm it.
- Every hypothesis is tied to timeline evidence and carries a confidence. Every mitigation is a proposal with a command a human runs; the agent runs none of them.

## Sources

- [Activity Log](https://learn.microsoft.com/azure/azure-monitor/essentials/activity-log).
- [Resource Graph paging](https://learn.microsoft.com/azure/governance/resource-graph/concepts/work-with-data).

## Assessment and customer sharing

Confirm the explicit customer scope and UTC window before collection. Accessible resources are not automatically approved scope. For a tool that enumerates all visible subscriptions, use an identity restricted to the approved scope or the related skill's scoped commands.

Follow [assessment states and limits](./references/assessment-contract.md), [permissions](./references/permissions-and-scope.md), and [customer sharing review](./references/customer-sharing.md), bundled during deployment. The shared renderer produces a sanitized draft by default; `--include-identifiers` requires an explicitly approved customer audience. Review custom exports with the same checklist.

Configure the host using [governance settings](./references/governance.json). General terminal access is not inherently read only. Never apply changes, schedule work, upload files or send messages without separate explicit approval.

## Approval boundary

Confirm explicit customer scope and the intended identity. Host authorization must enforce the bundled governance policy; general terminal access is not inherently read only. Changes, deployment, scheduling, uploads and messages require separate explicit approval. Preserve denied, missing and truncated evidence as unassessed, never healthy.

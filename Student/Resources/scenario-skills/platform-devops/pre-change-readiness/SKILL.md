---
name: pre-change-readiness
description: Use before a launch, a migration, a deployment, or a big change, or when the user asks for a readiness check, a go or no-go, or "are we ready to ship". Runs reliability, internet exposure, and capacity checks scoped to one target subscription or resource group and returns a go, caution, or no-go verdict per category, as a self contained HTML readiness report.
tools:
  - RunAzCliReadCommands
  - RunInTerminal
  - SaveFileToBlob
metadata:
  category: platform-devops
---

# Pre-Change Readiness

This skill gives a single go or no-go readiness view for a specific target before a launch, a migration, or a large change. It runs reliability, internet exposure, and capacity checks scoped to one subscription or resource group, returns a verdict per category and an overall verdict, and produces one self contained HTML report. It is a workflow no portal blade offers: it joins the checks that matter right before a change into one answer for the scope you are about to touch. It runs on demand.

## When to use this skill

Use this skill when the user asks to:

- Check readiness before a launch, a migration, or a major deployment.
- Get a go, caution, or no-go for a specific scope.
- Confirm reliability, exposure, and capacity are in order before shipping.

## Operating principles

- Read only. This skill reads configuration and usage. It never changes anything; it reports whether the scope is ready.
- Scoped and explicit. It checks exactly the subscription (and optional resource group) you pass, so the verdict is about the thing you are changing, not the whole estate.
- Evidence first. Every finding names the resource, the category, the issue, a severity, and the recommended change. The verdict follows from the severities, not from a feeling.

## Workflow

The scan tool (tools/readiness_check.py) and the shared report renderer (tools/report_render.py) are bundled with this skill. Run them with RunInTerminal using the Python in the agent runtime. The collector uses the configured identity; the local renderer does not authenticate to Azure.

### Phase 1: Check the target

1. Run python tools/readiness_check.py "<subscription id>" [resource group] with RunInTerminal. It runs the reliability, exposure, and capacity checks in references/checks-catalog.md scoped to that target, assigns a severity to each finding, and prints a report_data object as JSON.
2. Review per check assessment state before the verdict. Critical or High means NO-GO. Failed, empty capacity, missing or unknown scope reads mean INCOMPLETE and block GO. After complete reads, Medium means CAUTION and no findings means GO for these checks only.

### Validation boundary

The JSON includes `assessment_status`, `assessments` and `sources`. A clean finding list alone never permits GO. Inventory must confirm a visible target, all six configuration queries must finish and each observed region must return finite compute and network counters. This is not a change approval, allocation guarantee, full quota review, effective connectivity test or measured workload failover result. Confirm the approved subscription and resource group before running; playbook instructions do not enforce host access.

Select the credential deterministically before collection: set `AZURE_CLIENT_ID` for a user assigned managed identity, or explicitly set `SRE_IDENTITY_MODE=system-assigned`. Local development requires `SRE_IDENTITY_MODE=developer` with no managed identity client ID. Authentication errors propagate without selecting another identity.

### Phase 2: Produce the report

1. Pipe the scan into the renderer: python tools/readiness_check.py "<subscription id>" [resource group] | python tools/report_render.py with RunInTerminal. It writes the self contained HTML report and returns the path. Store it with SaveFileToBlob for a link.
2. Present the report, then a short inline summary: the overall verdict, the verdict per category, and the blocking findings to clear before shipping.

## Scenario coverage

This skill implements its documented checks, not every related scenario. Use the related skills for their complete evidence workflows. See [scenario routing](./references/scenarios.md).


## Expected output

- Primary: a self contained HTML readiness report, with the overall and per category verdicts as cards, findings by category and severity, and the full table of what to clear.
- Inline: the overall go, caution, or no-go, the per category verdicts, and the blocking findings.
- Every finding names the resource, category, issue, severity, and recommended change. The skill reports readiness; it changes nothing.

## Sources

- [Azure quotas](https://learn.microsoft.com/en-us/azure/quotas/view-quotas).
- [VM reliability](https://learn.microsoft.com/en-us/azure/reliability/reliability-virtual-machines).

Regression validation uses mocked reads only. No Azure resources or deployments were queried during this correction.

## Assessment and customer sharing

Confirm the explicit customer scope and UTC window before collection. Accessible resources are not automatically approved scope. For a tool that enumerates all visible subscriptions, use an identity restricted to the approved scope or the related skill's scoped commands.

Follow [assessment states and limits](./references/assessment-contract.md), [permissions](./references/permissions-and-scope.md), and [customer sharing review](./references/customer-sharing.md), bundled during deployment. The shared renderer produces a sanitized draft by default; `--include-identifiers` requires an explicitly approved customer audience. Review custom exports with the same checklist.

Configure the host using [governance settings](./references/governance.json). General terminal access is not inherently read only. Never apply changes, schedule work, upload files or send messages without separate explicit approval.

## Approval boundary

Confirm explicit customer scope and the intended identity. Host authorization must enforce the bundled governance policy; general terminal access is not inherently read only. Changes, deployment, scheduling, uploads and messages require separate explicit approval. Preserve denied, missing and truncated evidence as unassessed, never healthy.

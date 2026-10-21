---
name: tag-governance-compliance
description: Use when the user asks about tagging compliance, tag governance, resources missing tags, untagged resources, ownership tags, missing owner or environment or cost center tags, or chargeback readiness. Checks the resources the agent can read against a required tag standard, flags what is missing, and produces a self contained HTML tag compliance report.
tools:
  - RunAzCliReadCommands
  - RunInTerminal
  - SaveFileToBlob
metadata:
  category: governance
---

# Tag Governance Compliance

This skill measures how well the resources this agent can read meet a required tag standard. It checks each resource for the required tags (owner, environment, and cost center by default), flags what is missing, and produces a single self contained HTML report. Good tagging is what makes accountability, environment filtering, and cost chargeback work, so this both improves governance and feeds cleaner cost attribution. It runs on demand or as a scheduled sweep.

## When to use this skill

Use this skill when the user asks to:

- Check tagging compliance or find untagged resources.
- Confirm ownership tags are in place before an audit or a chargeback cycle.
- Measure how close the estate is to a required tag standard.

## Operating principles

- Read only. This skill reads tags. It never sets, changes, or removes a tag; it reports what is missing and the standard to meet.
- Approved read scope. It reads resource inventory and tags across the subscriptions this agent can read. If a read is denied, it records the scope as not assessed and continues. See references/permissions-and-scope.md.
- Match tag names case insensitively only. `cost-center`, `CostCenter` and `cost_center` are distinct names. No separator aliases are implemented. A required tag with an empty, null or whitespace value fails. Values are not case normalized.
- Assess only resources with observed tags or verified tag support. Use `--tag-support <approved-json-file>` with a mapping of full resource types to `true` or `false`, verified against the linked Microsoft support catalog. Unsupported types are excluded; unknown types are Not assessed. Empty or inaccessible inventory is Not assessed, not 100 percent compliant.
- This tool checks required tag names and nonblank values, not naming regexes, policy state or allowed value lists. Dedicated naming and policy skills cover those scenarios.
- Approve scope before collection. This is a playbook gate, not host authorization enforcement. Select identity explicitly using `AZURE_CLIENT_ID`, `SRE_IDENTITY_MODE=system-assigned`, or an explicitly approved local `SRE_IDENTITY_MODE=developer` run. No silent credential fallback.

## Workflow

The scan tool (tools/tag_compliance.py) and the shared report renderer (tools/report_render.py) are bundled with this skill. Run them with RunInTerminal using the Python in the agent runtime. The collector uses the configured identity; the local renderer does not authenticate to Azure.

### Phase 1: Check against the standard

1. Run python tools/tag_compliance.py [required tags] with RunInTerminal, where required tags is an optional comma separated list. It defaults to owner,environment,cost-center. It enumerates resources with Azure Resource Graph and prints a report_data object as JSON.
2. Compliance requires every required tag with a nonblank value, among assessed resources only. Unknown tag support and denied scope stay outside that denominator and remain visible as unknowns.

### Phase 2: Produce the report

1. Pipe the scan into the renderer: python tools/tag_compliance.py | python tools/report_render.py with RunInTerminal. It writes the self contained HTML report and returns the path. Store it with SaveFileToBlob for a link.
2. Present the report, then a short inline summary: compliance percent, resources missing an owner tag, the most common missing tag, and the top subscriptions by gap.

## Scenario coverage

This skill implements its documented checks, not every related scenario. Use the related skills for their complete evidence workflows. See [scenario routing](./references/scenarios.md).


## Expected output

- Primary: a self contained HTML tag compliance report, covering compliance percent, missing tags by type, non compliance by subscription, and the full table naming the missing tags per resource.
- Inline: compliance percent, resources with no owner, the most common missing tag, and the top gaps.
- Every finding names the resource and the exact missing tags, with the recommended values to set. Nothing is tagged; recommendations are for a human to apply, ideally through Azure Policy for durable enforcement.

## Sources

- [Tag names, values and support limits](https://learn.microsoft.com/azure/azure-resource-manager/management/tag-resources)
- [Tag support by resource type](https://learn.microsoft.com/azure/azure-resource-manager/management/tag-support)
- [Owned checks and denominator rules](references/checks-catalog.md)

## Assessment and customer sharing

Confirm the explicit customer scope and UTC window before collection. Accessible resources are not automatically approved scope. For a tool that enumerates all visible subscriptions, use an identity restricted to the approved scope or the related skill's scoped commands.

Follow [assessment states and limits](./references/assessment-contract.md), [permissions](./references/permissions-and-scope.md), and [customer sharing review](./references/customer-sharing.md), bundled during deployment. The shared renderer produces a sanitized draft by default; `--include-identifiers` requires an explicitly approved customer audience. Review custom exports with the same checklist.

Configure the host using [governance settings](./references/governance.json). General terminal access is not inherently read only. Never apply changes, schedule work, upload files or send messages without separate explicit approval.

## Approval boundary

Confirm explicit customer scope and the intended identity. Host authorization must enforce the bundled governance policy; general terminal access is not inherently read only. Changes, deployment, scheduling, uploads and messages require separate explicit approval. Preserve denied, missing and truncated evidence as unassessed, never healthy.

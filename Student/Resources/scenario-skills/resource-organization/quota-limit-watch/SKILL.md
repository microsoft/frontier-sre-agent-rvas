---
name: quota-limit-watch
description: Use when the user asks about quotas, service limits, capacity headroom, vCPU or core limits, public IP or network limits, "will a deployment or scale out fail", or approaching Azure limits. Reads Azure usage and quota counters for compute, network, and storage across the regions the agent's resources sit in, flags any counter close to its limit, and produces a self contained HTML quota headroom report.
tools:
  - RunAzCliReadCommands
  - RunInTerminal
  - SaveFileToBlob
metadata:
  category: resource-organization
---

# Quota and Limit Watch

This skill checks how close the subscriptions this agent can read are to their Azure quotas and service limits. It reads compute, network, and storage usage counters in every region where the agent has resources, flags any counter near its limit, and produces a single self contained HTML headroom report. Catching a quota before it is hit prevents the scale out and deployment failures that show up during traffic spikes. It runs on demand or as a scheduled sweep.

## When to use this skill

Use this skill when the user asks to:

- Check quota or service limit headroom before a launch, a migration, or a scale event.
- Understand why a deployment or a scale out failed, or might fail, with a quota error.
- Find regions and families that are close to their limits.

## Operating principles

- Read only. This skill reads usage and quota counters. It never requests or changes a quota; it recommends where to request an increase.
- Approved read scope. It reads the usage endpoints for the subscriptions this agent can read, in the regions those subscriptions actually use. If a read is denied, it records the scope as not assessed and continues. See references/permissions-and-scope.md.
- Evidence first. Every finding carries the subscription, the region, the quota name, the used and limit values, the utilization percent, and a severity from that utilization.

## Workflow

The scan tool (tools/quota_scan.py) and the shared report renderer (tools/report_render.py) are bundled with this skill. Run them with RunInTerminal using the Python in the agent runtime. The collector uses the configured identity; the local renderer does not authenticate to Azure.

### Phase 1: Read usage counters

1. Run python tools/quota_scan.py with RunInTerminal. It finds the regions each subscription uses with Azure Resource Graph, reads the compute, network, and storage usage counters in those regions, and prints a report_data object as JSON.
2. It flags any counter at or above the threshold (80 percent by default) and assigns a severity from the utilization, following references/checks-catalog.md. Pass a lower threshold as an argument for an earlier warning.

### Coverage and limits

Confirm the approved scope and select the identity explicitly with `AZURE_CLIENT_ID`, or `SRE_IDENTITY_MODE=system-assigned`. Local credentials require `SRE_IDENTITY_MODE=developer`. These instructions do not enforce host access.

Compute, network and storage usage are read per observed subscription and region. Storage uses the regional `Microsoft.Storage/locations/<region>/usages` endpoint. Missing, invalid, nonpositive or unlimited limits do not prove spare capacity. JSON exposes per endpoint `assessments`, `assessment_status` and `sources`. Failed or empty reads cannot produce Complete; an empty scope is Not assessed.

Only selected usage counters are covered. This is not every quota, a subscription deployment validation or a guarantee of regional SKU capacity. Compare planned resource demand with actual headroom separately. No quota is increased by this tool.

### Phase 2: Produce the report

1. Pipe the scan into the renderer: python tools/quota_scan.py | python tools/report_render.py with RunInTerminal. It writes the self contained HTML report and returns the path. Store it with SaveFileToBlob for a link.
2. Present the report, then a short inline summary: counters at or above the threshold, the Critical count (95 percent or higher), the tightest three counters, and any scope not assessed.

## Scenario coverage

This skill implements its documented checks, not every related scenario. Use the related skills for their complete evidence workflows. See [scenario routing](./references/scenarios.md).


## Expected output

- Primary: a self contained HTML headroom report, covering counters near their limit by severity, the tightest counters, and the full table with used, limit, and utilization per counter.
- Inline: counters near the limit, the Critical count, and the tightest counters with the region and the quota name.
- Every finding carries the subscription, region, quota name, used and limit values, utilization percent, and a severity. The skill requests no increase; it points to where an increase is needed.

## Sources

- [Storage usages by location API](https://learn.microsoft.com/en-us/rest/api/storagerp/usages/list-by-location?view=rest-storagerp-2023-05-01), endpoint checked 2026-10-21.
- [View quotas](https://learn.microsoft.com/en-us/azure/quotas/view-quotas).

Offline tests validate endpoint construction and coverage states. No quota or live resource endpoint was queried.

## Assessment and customer sharing

Confirm the explicit customer scope and UTC window before collection. Accessible resources are not automatically approved scope. For a tool that enumerates all visible subscriptions, use an identity restricted to the approved scope or the related skill's scoped commands.

Follow [assessment states and limits](./references/assessment-contract.md), [permissions](./references/permissions-and-scope.md), and [customer sharing review](./references/customer-sharing.md), bundled during deployment. The shared renderer produces a sanitized draft by default; `--include-identifiers` requires an explicitly approved customer audience. Review custom exports with the same checklist.

Configure the host using [governance settings](./references/governance.json). General terminal access is not inherently read only. Never apply changes, schedule work, upload files or send messages without separate explicit approval.

## Approval boundary

Confirm explicit customer scope and the intended identity. Host authorization must enforce the bundled governance policy; general terminal access is not inherently read only. Changes, deployment, scheduling, uploads and messages require separate explicit approval. Preserve denied, missing and truncated evidence as unassessed, never healthy.

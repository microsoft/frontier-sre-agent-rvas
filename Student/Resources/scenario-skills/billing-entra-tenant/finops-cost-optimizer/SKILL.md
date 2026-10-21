---
name: finops-cost-optimizer
description: Use when the user asks for a FinOps review, Azure cost optimization, cost savings, reducing spend, rightsizing, idle or forgotten resources, or "where is my Azure money going". Ranks approved subscriptions and resource groups by spend within currency and cost basis, reviews seven waste dimensions and potential idle or orphaned resources, and produces an evidence report. Review confidence is never permission to delete; operator commands are optional.
tools:
  - RunAzCliReadCommands
  - RunInTerminal
  - SaveFileToBlob
metadata:
  category: billing-entra-tenant
---

# FinOps Cost Optimizer

This skill runs a FinOps cost optimization review across the Azure subscriptions and resource groups this agent is allowed to read. It narrows scope by spend, finds waste across seven dimensions, enumerates idle and orphaned resources and scores each one by confidence to terminate, ranks by savings, and produces a single self contained HTML report as the primary output. It is built to run on demand or as a monthly FinOps report.

## When to use this skill

Use this skill when the user asks to:

- Review or reduce Azure cost, find savings, or run a FinOps assessment.
- Understand where spend is concentrated across subscriptions or resource groups.
- Get cost optimization recommendations beyond raw Azure Advisor output.

## Operating principles

- Read only. This skill never changes or deletes resources. It proposes recommendations. Destructive operator commands are optional and require a separate request and the usual owner and change approvals; the agent runs none of them.
- Approved read scope. It analyzes the subscriptions and resource groups this agent can already read, and starts within that existing access. If a read returns access denied or authorization failed, it may ask the user to grant temporary access to that scope, but it never assigns roles itself. Elevation is always the user granting temporary access out of band. If the user declines, skip that item, record it as not assessed because of insufficient access, and continue with the rest. See references/permissions-and-scope.md.
- Evidence first. Every recommendation carries its evidence, currency, estimate window, cost basis, and risk. A confidence score ranks review evidence only, never permission to delete. Confirm owners, dependencies, retention and change approval before any destructive action. Names alone do not prove nonproduction or idleness.
- Approve the subscription scope before collection. Accessible scope is not automatically approved scope. These playbook checks do not enforce host tool authorization.
- Select identity explicitly: `AZURE_CLIENT_ID` for a user assigned managed identity, `SRE_IDENTITY_MODE=system-assigned` for system assigned managed identity, or `SRE_IDENTITY_MODE=developer` only for an explicitly approved local developer run. Missing configuration fails closed; no ambient discovery or silent fallback.

## Workflow

The three Python helpers (tools/cost_rank.py, tools/commitment_recommendations.py, tools/generate_report.py) are bundled with this skill. Run them with the RunInTerminal tool using the Python in the agent runtime, after verifying that the host provides approved azure-identity and requests packages. The report generator uses only the Python standard library. They authenticate to Azure with the agent managed identity. Follow these four phases in order.

### Phase 1: Narrow scope by spend

1. Run the helper with RunInTerminal: python tools/cost_rank.py. It queries Azure Cost Management at subscription scope for amortized spend over the last 30 days, groups by resource group, and applies the ranking rules in references/ranking-method.md.
2. It returns the ranked subscriptions, the selected top decile (with a floor so small tenants still return results), and for each selected subscription the ranked resource groups with their own selected top decile.
3. Rank within each currency and cost basis, never across them. The helper follows Cost Management `properties.nextLink`; a continuation beyond the page cap fails that source explicitly. Consumption fallback is usage detail actual cost, not an equivalent amortized baseline, and makes the assessment Partial. Failed subscriptions are Not assessed, never zero cost.

### Phase 2: Detect waste and idle resources

Work two passes over the selected scope.

Savings recommendations, across the dimensions in references/checks-catalog.md:

1. Azure Advisor cost baseline.
2. Orphaned resources (also a termination candidate source; see below).
3. Commitment coverage. Run python tools/commitment_recommendations.py --subscriptions <selected ids> with RunInTerminal for reservation and savings plan recommendations.
4. Idle or underused resources, using Azure Monitor metrics over a 30 day window.
5. Storage optimization.
6. Log Analytics optimization.
7. Dev and test scheduling.

Use the RunAzCliReadCommands tool for the read only Azure CLI commands in the catalog. Record a finding with: resource id, dimension, current configuration, proposed change, estimated monthly saving, risk rating, and evidence.

Termination candidates, following references/idle-detection.md: enumerate within approved scope, record association and age evidence, and price individually. Where metrics or Activity Logs cannot be read, mark idleness unknown. Naming is a cautionary hint, not proof. Delete commands are destructive operator instructions, never read only checks, and are not generated automatically from resource ids by the renderer.

### Phase 3: Rank

Score every finding with the priority formula in references/ranking-method.md and sort findings from highest to lowest priority. Sort termination candidates by confidence to terminate, highest first. Spend chose where to look. Savings and confidence decide what to act on first.

### Phase 4: Produce the report

1. Assemble the report_data described in references/report-layout.md. Produce separate reports per currency. Reconcile Advisor, resource cleanup, rightsizing and commitments against the same selected scope, window and cost basis. Reservations and savings plans can be alternatives for the same usage; do not add their projections as realizable savings. Preserve individual opportunities when overlap or timing is unknown. Set `totals.savings_reconciled=true` only with `reconciliation_notes` explaining those choices.
2. Run python tools/generate_report.py with RunInTerminal, passing the assembled report_data as JSON on standard input. It writes a self contained HTML report to /mnt/data and returns the path. If the user wants a shareable link, store the file with the SaveFileToBlob tool.
3. Present the report, then a short inline summary: total analyzed spend, total estimated monthly savings, findings by priority, termination candidates by confidence band, the top three recommendations, the top three termination candidates, and any scopes or dimensions not assessed because of insufficient access.

## Optional follow up

Only if the user asks for it, file tracking issues from the findings using references/issues-optional.md. This is off by default.

## Scenario coverage

This skill implements its documented checks, not every related scenario. Use the related skills for their complete evidence workflows. See [scenario routing](./references/scenarios.md).


## Expected output

- Primary: a single self contained HTML report delivered as a file link, covering the FinOps overview, the termination candidates, and the savings recommendations.
- Inline: a short summary with total spend analyzed, total estimated monthly savings, findings by priority, termination candidates by confidence band, and the top recommendations and candidates.
- Every recommendation includes evidence, currency, estimate basis and risk. Every review candidate includes evidence, an individual saving estimate where known and a confidence score that never authorizes deletion. Operator requested commands are optional and never executed by the agent.

## Sources

- [Owned checks, aggregation rules and verified source URLs](references/checks-catalog.md)
- [Cost query pagination](https://learn.microsoft.com/javascript/api/@azure/arm-costmanagement/queryproperties)
- [Cost visibility and permissions](https://learn.microsoft.com/azure/cost-management-billing/costs/assign-access-acm-data)

## Assessment and customer sharing

Confirm the explicit customer scope and UTC window before collection. Accessible resources are not automatically approved scope. For a tool that enumerates all visible subscriptions, use an identity restricted to the approved scope or the related skill's scoped commands.

Follow [assessment states and limits](./references/assessment-contract.md), [permissions](./references/permissions-and-scope.md), and [customer sharing review](./references/customer-sharing.md), bundled during deployment. The shared renderer produces a sanitized draft by default; `--include-identifiers` requires an explicitly approved customer audience. Review custom exports with the same checklist.

Configure the host using [governance settings](./references/governance.json). General terminal access is not inherently read only. Never apply changes, schedule work, upload files or send messages without separate explicit approval.

## Approval boundary

Confirm explicit customer scope and the intended identity. Host authorization must enforce the bundled governance policy; general terminal access is not inherently read only. Changes, deployment, scheduling, uploads and messages require separate explicit approval. Preserve denied, missing and truncated evidence as unassessed, never healthy.

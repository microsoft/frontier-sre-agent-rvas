---
name: reliability-posture-review
description: Use when the user asks for a reliability review, resilience assessment, high availability check, single points of failure, a Well-Architected reliability review, or "will we survive a zone or region outage". Scans the resources the agent can read for missing availability zones, single instance workloads, retiring Basic tiers, and single region data services, scores each finding by severity, and produces a self contained HTML resilience scorecard.
tools:
  - RunAzCliReadCommands
  - RunInTerminal
  - SaveFileToBlob
metadata:
  category: management
---

# Reliability Posture Review

This skill reviews the resilience posture of the Azure resources this agent can read. It finds single points of failure and redundancy gaps (no availability zones, single instance compute, retiring Basic tiers, single region data services), scores each finding by severity, and produces a single self contained HTML scorecard as the primary output. It is the Well-Architected reliability pillar counterpart to the cost optimizer, and it runs on demand or as a scheduled sweep.

## When to use this skill

Use this skill when the user asks to:

- Review reliability, resilience, or high availability posture.
- Find single points of failure or redundancy gaps before an outage.
- Run a Well-Architected reliability assessment across a subscription or resource group.

## Operating principles

- Read only. This skill never changes a resource. It proposes recommendations with the exact configuration change, but a human reviews and applies them.
- Approved read scope. It analyzes the subscriptions and resource groups this agent can already read. If a read returns access denied, it may ask the user to grant temporary access, but it never assigns roles itself. If the user declines, it records the scope as not assessed and continues. See references/permissions-and-scope.md.
- Evidence first. Every finding carries the resource id, the reliability signal that fired, a severity, and the recommended change. Severity reflects blast radius and likelihood, not effort.

## Workflow

The scan tool (tools/reliability_scan.py) and the shared report renderer (tools/report_render.py) are bundled with this skill. Run them with the RunInTerminal tool using the Python in the agent runtime, after verifying that the host provides approved azure-identity and requests packages. The renderer uses only the standard library. The collector uses the configured identity; the local renderer does not authenticate to Azure. Follow three phases.

### Phase 1: Scan for reliability signals

1. Run python tools/reliability_scan.py with RunInTerminal. It queries Azure Resource Graph across every accessible subscription for the reliability signals in references/checks-catalog.md, assigns a severity to each, and prints a ready to render report_data object as JSON on standard output.
2. For any signal the tool could not evaluate (for example a subscription that denied Resource Graph), it records a method note rather than failing the run.
3. If the user wants deeper checks that Resource Graph cannot answer alone, backup coverage and idle detection have their own skills; point to them rather than duplicating the work here.

### Phase 2: Confirm severity and scope

Review the findings against references/scoring-method.md. Severity bands are Critical, High, Medium and Low; Unknown means insufficient assessment evidence, not a pass. Never downgrade a resource purely because its name contains dev, test, lab or another environment hint. Any manual criticality adjustment requires owner validated workload context.

Application Gateway v2 with absent zones is not automatically nonredundant. Current documentation says new v2 gateways default to zone redundancy in supported regions. Verify effective regional deployment and history; the scanner records this as Unknown rather than a false redundancy gap. One zonal VM or availability set membership is not proof of multiple workload instances or failover.

Configure the selected identity with `AZURE_CLIENT_ID`, or explicitly `SRE_IDENTITY_MODE=system-assigned`. Local credentials require explicit `SRE_IDENTITY_MODE=developer`. Confirm approved scope before collection; playbook gates do not enforce host access. Reports expose `assessment_status` and `sources`; failures, unknown applicability and empty visibility never produce Complete.

### Phase 3: Produce the scorecard

1. Pipe the scan output straight into the renderer: python tools/reliability_scan.py | python tools/report_render.py with RunInTerminal. The renderer writes a self contained HTML scorecard and returns the path. If the user wants a shareable link, store it with the SaveFileToBlob tool.
2. Present the report, then a short inline summary: resources with findings, findings by severity, the top subscriptions by finding count, the three highest severity items, and any scope not assessed because of insufficient access.

## Optional follow up

Only if the user asks, file tracking issues from the highest severity findings. This is off by default and read only until the user requests it.

## Scenario coverage

This skill implements its documented checks, not every related scenario. Use the related skills for their complete evidence workflows. See [scenario routing](./references/scenarios.md).


## Expected output

- Primary: a single self contained HTML resilience scorecard delivered as a file link, covering findings by severity, findings by subscription, and the full finding table with the recommended change per resource.
- Inline: a short summary with resources affected, findings by severity, and the top recommendations.
- Every finding includes the resource id, the reliability signal, a severity, and the exact recommended configuration change. Nothing is changed; recommendations are proposals for a human to apply.

## Sources

- [Application Gateway v2 reliability](https://learn.microsoft.com/en-us/azure/reliability/reliability-application-gateway-v2), default zone behavior checked 2026-10-21.
- [VM reliability](https://learn.microsoft.com/en-us/azure/reliability/reliability-virtual-machines).
- [AKS system pools](https://learn.microsoft.com/en-us/azure/aks/use-system-pools).

Offline tests cover rule construction and mocked reads. No actual redundancy, workload topology, RTO, RPO or live failover was validated.

## Assessment and customer sharing

Confirm the explicit customer scope and UTC window before collection. Accessible resources are not automatically approved scope. For a tool that enumerates all visible subscriptions, use an identity restricted to the approved scope or the related skill's scoped commands.

Follow [assessment states and limits](./references/assessment-contract.md), [permissions](./references/permissions-and-scope.md), and [customer sharing review](./references/customer-sharing.md), bundled during deployment. The shared renderer produces a sanitized draft by default; `--include-identifiers` requires an explicitly approved customer audience. Review custom exports with the same checklist.

Configure the host using [governance settings](./references/governance.json). General terminal access is not inherently read only. Never apply changes, schedule work, upload files or send messages without separate explicit approval.

## Approval boundary

Confirm explicit customer scope and the intended identity. Host authorization must enforce the bundled governance policy; general terminal access is not inherently read only. Changes, deployment, scheduling, uploads and messages require separate explicit approval. Preserve denied, missing and truncated evidence as unassessed, never healthy.

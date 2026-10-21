---
name: aks-reliability-review
description: Use when the user asks for an AKS review, Kubernetes cluster reliability, AKS best practices, cluster resilience, or an AKS health check. Reviews the AKS clusters the agent can read for version currency, node pool resilience, control plane exposure, upgrade and monitoring configuration, and identity and tier settings, scores each finding by severity, and produces a self contained HTML AKS reliability report.
tools:
  - RunAzCliReadCommands
  - RunInTerminal
  - SaveFileToBlob
metadata:
  category: management
---

# AKS Reliability Review

This skill reviews the Azure Kubernetes Service clusters this agent can read against reliability and operational best practices. It checks version currency, node pool resilience, control plane exposure, auto upgrade and monitoring, and identity and tier settings, scores each finding by severity, and produces a single self contained HTML report. AKS carries a lot of production weight, and a handful of configuration choices decide whether a cluster rides through a zone loss, an upgrade, or a node failure. It runs on demand or as a scheduled sweep.

## When to use this skill

Use this skill when the user asks to:

- Review AKS or Kubernetes cluster reliability, resilience, or best practices.
- Check clusters before a launch, an upgrade, or an audit.
- Find the riskiest cluster configuration across the estate.

## Operating principles

- Read only. This skill reads cluster configuration. It never upgrades, scales, or reconfigures a cluster; it recommends the change.
- Approved read scope. It reads the managed cluster configuration across the subscriptions this agent can read. If a read is denied, it records the scope as not assessed and continues. See references/permissions-and-scope.md.
- Evidence first. Every finding names the cluster, the setting that fired, a severity, and the recommended change.

## Workflow

The scan tool (tools/aks_review.py) and the shared report renderer (tools/report_render.py) are bundled with this skill. Run them with RunInTerminal using the Python in the agent runtime. The collector uses the configured identity; the local renderer does not authenticate to Azure.

### Phase 1: Review the clusters

1. Run python tools/aks_review.py with RunInTerminal. It reads the managed cluster configuration with Azure Resource Graph, evaluates each cluster against the checks in references/checks-catalog.md, assigns a severity per finding, and prints a report_data object as JSON.
2. For a cluster that needs a closer look, pull the node pool and upgrade detail by hand with the commands in the checks catalog.

Before collection, confirm the approved scope and configure the selected identity using `AZURE_CLIENT_ID`, or explicitly `SRE_IDENTITY_MODE=system-assigned`. Only explicit `SRE_IDENTITY_MODE=developer` opts in to local credentials. There is no identity discovery or silent fallback.

### Evidence and limitations

Set `SRE_LIFECYCLE_EVIDENCE` to an operator verified snapshot following the checks catalog schema. No snapshot, stale evidence, an unmatched version or unconfirmed support plan yields Unknown, not supported. LTS requires Premium and explicit LTS enrollment; minor lifecycle evidence alone does not establish current patch eligibility.

Production system pools should have at least three nodes, including the autoscaler minimum. Two is a platform minimum, not the production recommendation. User pool sizing depends on the workload. Azure CNI Powered by Cilium is recognized as a policy engine, not a missing policy.

The Python evaluator accepts an explicitly verified `zone_regions` mapping. The CLI does not collect region or VM SKU capability evidence, so unsupported or unknown zone applicability must not generate a blanket instruction to recreate across zones. Workload scheduling, disruption budgets, policy objects, probes and failover remain unassessed.

Reports expose `assessment_status` and `sources`. Empty collection is Not assessed, and Unknown findings or collection failures prevent Complete. Scope approval is a playbook gate, not a host enforced authorization boundary.

### Phase 2: Produce the report

1. Pipe the scan into the renderer: python tools/aks_review.py | python tools/report_render.py with RunInTerminal. It writes the self contained HTML report and returns the path. Store it with SaveFileToBlob for a link.
2. Present the report, then a short inline summary: clusters reviewed, clusters with High findings, the most common gap, and the top clusters to address.

## Expected output

- Primary: a self contained HTML AKS reliability report, covering findings by severity and by subscription, and the full table naming the setting and the recommended change per cluster.
- Inline: clusters reviewed, clusters with High findings, and the top issues.
- Every finding names the cluster, the setting, a severity, and the recommended change. Nothing is reconfigured; recommendations are for a human to apply.

## Sources

Technical rules checked on 2026-10-21:

- [AKS versions](https://learn.microsoft.com/en-us/azure/aks/supported-kubernetes-versions).
- [LTS plans](https://learn.microsoft.com/en-us/azure/aks/long-term-support).
- [System node pools](https://learn.microsoft.com/en-us/azure/aks/use-system-pools).
- [Azure CNI Powered by Cilium](https://learn.microsoft.com/en-us/azure/aks/azure-cni-powered-by-cilium).

Tests are offline regressions, not validation of a deployed cluster.

## Assessment and customer sharing

Confirm the explicit customer scope and UTC window before collection. Accessible resources are not automatically approved scope. For a tool that enumerates all visible subscriptions, use an identity restricted to the approved scope or the related skill's scoped commands.

Follow [assessment states and limits](./references/assessment-contract.md), [permissions](./references/permissions-and-scope.md), and [customer sharing review](./references/customer-sharing.md), bundled during deployment. The shared renderer produces a sanitized draft by default; `--include-identifiers` requires an explicitly approved customer audience. Review custom exports with the same checklist.

Configure the host using [governance settings](./references/governance.json). General terminal access is not inherently read only. Never apply changes, schedule work, upload files or send messages without separate explicit approval.

## Approval boundary

Confirm explicit customer scope and the intended identity. Host authorization must enforce the bundled governance policy; general terminal access is not inherently read only. Changes, deployment, scheduling, uploads and messages require separate explicit approval. Preserve denied, missing and truncated evidence as unassessed, never healthy.

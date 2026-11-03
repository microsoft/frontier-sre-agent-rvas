# Use cases

Use cases are grouped by domain: `usecases/<domain>/<slug>/`. Each slug folder is one Azure SRE Agent use case. Add a folder and it shows up in the [Scenario Explorer](../web/scenarios.html), with its classification, components and status. Nothing else needs editing.

The ideas (`status: idea`) come from [alsanch/azure-sre-agent-scenarios](https://github.com/alsanch/azure-sre-agent-scenarios).

## Add a use case

1. Run `usecases/_framework/usecases.sh new <domain> <slug>`. It copies `usecases/_template/`.
2. Fill in `usecase.yaml` and the other files.
3. Run `usecases/_framework/usecases.sh validate`, then `usecases/_framework/usecases.sh index --readme` to refresh the index below.

An idea only needs `usecase.yaml` with `status: idea`. Add files later, then change `status`.

## Layout

```text
usecases/
  <domain>/            one folder per domain in _framework/taxonomy.yaml
    <slug>/            one use case; the folder name is its id
      usecase.yaml
      ...
```

The parent folder must match the `domain` field, and ids are unique across all domains. A top-level folder that is not a domain fails `validate`.

## File convention

The file name tells the framework what a file is. Use these names.

| File | Component |
|------|-----------|
| `usecase.yaml` | Classification (required) |
| `README.md` | Walkthrough for people |
| `SKILL.md` or `skills/*/SKILL.md` | Skill (at most 5 per use case) |
| `subagent-instructions-and-prompts.md` | Subagent |
| `generate-*.py` and `tool-parameters.schema.json` | Python tool and its parameters (both or neither) |
| `*-task-prompt.md` | Scheduled task |
| `grant-*` | Permission script |
| `tests/` | Test prompts and expected outcomes |
| `sample-report/` | Example output |
| `images/` | Screenshots |

Folders that start with `_` are skipped.

## `usecase.yaml`

| Field | Required | Values |
|-------|----------|--------|
| `id` | yes | Same as the folder name; unique across domains |
| `title`, `summary` | yes | Free text |
| `domain` | yes | One of the domains in [`_framework/taxonomy.yaml`](_framework/taxonomy.yaml); equals the parent folder |
| `trigger` | yes | List of `schedule`, `chat`, `alert` |
| `status` | yes | `idea`, `built` or `validated`. `validate` checks it against the files |
| `products` | built and validated | List of Azure products, for example `entra-id` |
| `autonomy` | built and validated | `read-only`, `approval`, `autonomous` |
| `frequency`, `timeSaved`, `topPick`, `samplePrompt`, `source` | no | `timeSaved` is `High`, `Medium` or `Low`; `source.type` is `community` |

You declare `status`, and `validate` fails if the files do not support it:

* **idea**: no skill and no subagent.
* **built**: a skill and / or a subagent.
* **validated**: built, plus `tests/` and `sample-report/`.

A tool (`generate-*.py`) needs a skill or a subagent next to it.

## Commands

All commands are in `usecases/_framework/usecases.sh` and need `jq` and Python 3 with PyYAML (or `yq`).

| Command | What it does |
|---------|--------------|
| `validate` | Checks every folder against the contract and the README index. Fails on a secret pattern. Bare GUIDs only warn. This is a pattern check, not a security guarantee. |
| `index -o <file> [--readme]` | Writes `usecases.json` for the explorer. `--readme` also rewrites the index below. |
| `portal-blocks <id or path> [-o file]` | Prints the text to paste into the portal: permissions, tool, skill, subagent, task. |
| `new <domain> <slug>` | Scaffolds `usecases/<domain>/<slug>` from `_template/`. |
| `deploy <id or path> --endpoint <url> [--subscription <id>] [--dry-run]` | Creates the tool, skill and subagent through the agent data-plane API. It does not create scheduled tasks. |

`deploy` follows the payloads of the [sre-agent-use-cases](https://github.com/marioaguileraaa/sre-agent-use-cases) reference. It has not been run against a live agent yet. Record the result of your first run here.

An agent allows five active skills. `validate` checks the limit per use case, not across the use cases you deploy to the same agent.

Every command accepts `--root DIR` before the command name to work on a use-case tree other than `usecases/`.

Run the framework tests with `usecases/_framework/tests/run.sh`.

## Index

<!-- usecases:index:start -->
| ID | Title | Domain | Status |
|----|-------|--------|--------|
| [6-month-cost-summary-trends](billing-entra-tenant/6-month-cost-summary-trends/) | 6-month cost summary & trends | billing-entra-tenant | idea |
| [agent-health-monitoring](management/agent-health-monitoring/) | Agent health monitoring | management | idea |
| [ai-model-inventory-retirement-lifecycle](resource-organization/ai-model-inventory-retirement-lifecycle/) | AI model inventory & retirement lifecycle | resource-organization | idea |
| [alert-fatigue-analysis](management/alert-fatigue-analysis/) | Alert fatigue analysis | management | idea |
| [alert-rules-best-practice-audit](management/alert-rules-best-practice-audit/) | Alert rules best-practice audit | management | idea |
| [all-write-operations-across-subscription-24h](management/all-write-operations-across-subscription-24h/) | All write operations across subscription (24h) | management | idea |
| [automated-compliance-remediation-tasks](governance/automated-compliance-remediation-tasks/) | Automated compliance remediation tasks | governance | idea |
| [azure-firewall-rule-generation](network-topology/azure-firewall-rule-generation/) | Azure Firewall rule generation | network-topology | idea |
| [azure-policy-assignment-assessment](governance/azure-policy-assignment-assessment/) | Azure Policy assignment assessment | governance | idea |
| [backup-policy-compliance-gap-detection](management/backup-policy-compliance-gap-detection/) | Backup policy compliance & gap detection | management | idea |
| [budget-alerts-configuration-audit](billing-entra-tenant/budget-alerts-configuration-audit/) | Budget alerts configuration audit | billing-entra-tenant | idea |
| [certificate-renewal-automation](security/certificate-renewal-automation/) | Certificate renewal automation | security | idea |
| [changes-by-non-service-principal-users](management/changes-by-non-service-principal-users/) | Changes by non-service-principal users | management | idea |
| [changes-in-last-24h-for-a-resource](management/changes-in-last-24h-for-a-resource/) | Changes in last 24h for a resource | management | idea |
| [consolidated-cost-reporting](billing-entra-tenant/consolidated-cost-reporting/) | Consolidated cost reporting | billing-entra-tenant | idea |
| [cost-analysis-by-tag-environment](billing-entra-tenant/cost-analysis-by-tag-environment/) | Cost analysis by tag/environment | billing-entra-tenant | idea |
| [cost-anomaly-detection](billing-entra-tenant/cost-anomaly-detection/) | Cost anomaly detection | billing-entra-tenant | idea |
| [cross-period-cost-comparison-mg-level](billing-entra-tenant/cross-period-cost-comparison-mg-level/) | Cross-period cost comparison (MG level) | billing-entra-tenant | idea |
| [custom-policy-generation](governance/custom-policy-generation/) | Custom Policy generation | governance | idea |
| [data-collection-rules-audit](management/data-collection-rules-audit/) | Data collection rules audit | management | idea |
| [ddos-protection-coverage-audit](network-topology/ddos-protection-coverage-audit/) | DDoS protection coverage audit | network-topology | idea |
| [defender-for-cloud-assessment](security/defender-for-cloud-assessment/) | Defender for Cloud assessment | security | idea |
| [diagnostic-settings-coverage-audit](management/diagnostic-settings-coverage-audit/) | Diagnostic settings coverage audit | management | idea |
| [disk-tier-down-opportunities](billing-entra-tenant/disk-tier-down-opportunities/) | Disk tier-down opportunities | billing-entra-tenant | idea |
| [dns-vpn-troubleshooting](network-topology/dns-vpn-troubleshooting/) | DNS/VPN troubleshooting | network-topology | idea |
| [dns-zone-record-hygiene](network-topology/dns-zone-record-hygiene/) | DNS zone record hygiene | network-topology | idea |
| [effective-policies-per-scope](governance/effective-policies-per-scope/) | Effective policies per scope | governance | idea |
| [executive-operational-report-generation-pdf](management/executive-operational-report-generation-pdf/) | Executive operational report generation (PDF) | management | idea |
| [export-existing-resources-to-arm-bicep](platform-devops/export-existing-resources-to-arm-bicep/) | Export existing resources to ARM/Bicep | platform-devops | idea |
| [expressroute-vpn-gateway-health](network-topology/expressroute-vpn-gateway-health/) | ExpressRoute / VPN Gateway health | network-topology | idea |
| [extension-health-across-vms](resource-organization/extension-health-across-vms/) | Extension health across VMs | resource-organization | idea |
| [failed-deployments-in-last-24h](platform-devops/failed-deployments-in-last-24h/) | Failed deployments in last 24h | platform-devops | idea |
| [find-built-in-policy-for-a-requirement](governance/find-built-in-policy-for-a-requirement/) | Find built-in policy for a requirement | governance | idea |
| [fired-alerts-summary-last-24h](management/fired-alerts-summary-last-24h/) | Fired alerts summary (last 24h) | management | idea |
| [firewall-log-analysis-kql](network-topology/firewall-log-analysis-kql/) | Firewall log analysis (KQL) | network-topology | idea |
| [high-privilege-operation-tracking](identity-access/high-privilege-operation-tracking/) | High-privilege operation tracking | identity-access | idea |
| [identify-who-added-a-firewall-nsg-rule](management/identify-who-added-a-firewall-nsg-rule/) | Identify who added a firewall/NSG rule | management | idea |
| [kql-log-queries-common-patterns](management/kql-log-queries-common-patterns/) | KQL log queries (common patterns) | management | idea |
| [log-analytics-workspace-ingestion-cost-analysis](billing-entra-tenant/log-analytics-workspace-ingestion-cost-analysis/) | Log Analytics workspace ingestion cost analysis | billing-entra-tenant | idea |
| [logic-apps-code-definition-inspection](management/logic-apps-code-definition-inspection/) | Logic Apps code/definition inspection | management | idea |
| [management-group-hierarchy-audit](resource-organization/management-group-hierarchy-audit/) | Management Group hierarchy audit | resource-organization | idea |
| [move-resources-between-subscriptions](resource-organization/move-resources-between-subscriptions/) | Move resources between subscriptions | resource-organization | idea |
| [naming-tagging-convention-compliance](governance/naming-tagging-convention-compliance/) | Naming & tagging convention compliance | governance | idea |
| [network-topology-diagram](network-topology/network-topology-diagram/) | Network topology diagram | network-topology | idea |
| [operations-dashboard-generation](management/operations-dashboard-generation/) | Operations dashboard generation | management | idea |
| [orphaned-resources-cost-impact-analysis](billing-entra-tenant/orphaned-resources-cost-impact-analysis/) | Orphaned resources & cost impact analysis | billing-entra-tenant | idea |
| [overly-permissive-nsg-rules-audit](network-topology/overly-permissive-nsg-rules-audit/) | Overly permissive NSG rules audit | network-topology | idea |
| [permissions-required-for-an-action](identity-access/permissions-required-for-an-action/) | Permissions required for an action | identity-access | idea |
| [planned-maintenance-awareness](management/planned-maintenance-awareness/) | Planned maintenance awareness | management | idea |
| [policy-compliance-state-monitoring](governance/policy-compliance-state-monitoring/) | Policy compliance state monitoring | governance | idea |
| [policy-exemptions-review](governance/policy-exemptions-review/) | Policy exemptions review | governance | idea |
| [post-incident-review-automation](management/post-incident-review-automation/) | Post-incident review automation | management | idea |
| [private-endpoint-public-exposure-audit](network-topology/private-endpoint-public-exposure-audit/) | Private endpoint & public exposure audit | network-topology | idea |
| [public-ip-inventory-justification](network-topology/public-ip-inventory-justification/) | Public IP inventory & justification | network-topology | idea |
| [rbac-access-audit-who-has-what](identity-access/rbac-access-audit-who-has-what/) | RBAC access audit (who has what) | identity-access | idea |
| [rbac-redundancy-over-privilege-assessment](identity-access/rbac-redundancy-over-privilege-assessment/) | RBAC redundancy & over-privilege assessment | identity-access | idea |
| [resource-age-tracking](resource-organization/resource-age-tracking/) | Resource age tracking | resource-organization | idea |
| [resource-group-sprawl-detection](resource-organization/resource-group-sprawl-detection/) | Resource group sprawl detection | resource-organization | idea |
| [resource-health-status-summary](management/resource-health-status-summary/) | Resource health status summary | management | idea |
| [resource-lock-compliance-audit](resource-organization/resource-lock-compliance-audit/) | Resource lock compliance audit | resource-organization | idea |
| [resource-metrics-analysis](management/resource-metrics-analysis/) | Resource metrics analysis | management | idea |
| [resources-created-yesterday](resource-organization/resources-created-yesterday/) | Resources created yesterday | resource-organization | idea |
| [resources-with-highest-cost-increase](billing-entra-tenant/resources-with-highest-cost-increase/) | Resources with highest cost increase | billing-entra-tenant | idea |
| [rollback-command-generation-for-bad-changes](management/rollback-command-generation-for-bad-changes/) | Rollback command generation for bad changes | management | idea |
| [rto-rpo-gap-analysis](management/rto-rpo-gap-analysis/) | RTO/RPO gap analysis | management | idea |
| [service-health-incidents-resource-impact](management/service-health-incidents-resource-impact/) | Service Health incidents & resource impact | management | idea |
| [sku-reliability-assessment](management/sku-reliability-assessment/) | SKU reliability assessment | management | idea |
| [ssl-tls-certificate-expiration-tracking](network-topology/ssl-tls-certificate-expiration-tracking/) | SSL/TLS certificate expiration tracking | network-topology | idea |
| [stale-rbac-assignments](identity-access/stale-rbac-assignments/) | Stale RBAC assignments | identity-access | idea |
| [subscription-hygiene-score](resource-organization/subscription-hygiene-score/) | Subscription hygiene score | resource-organization | idea |
| [subscription-limits-approaching](resource-organization/subscription-limits-approaching/) | Subscription limits approaching | resource-organization | idea |
| [support-ticket-creation-pre-populated](management/support-ticket-creation-pre-populated/) | Support ticket creation (pre-populated) | management | idea |
| [top-consumer-services-identification](billing-entra-tenant/top-consumer-services-identification/) | Top consumer services identification | billing-entra-tenant | idea |
| [underutilized-resources-detection](billing-entra-tenant/underutilized-resources-detection/) | Underutilized resources detection | billing-entra-tenant | idea |
| [vm-performance-anomaly-detection](management/vm-performance-anomaly-detection/) | VM performance anomaly detection | management | idea |
| [vnet-peering-health-check](network-topology/vnet-peering-health-check/) | VNet peering health check | network-topology | idea |
| [workbook-auto-generation](management/workbook-auto-generation/) | Workbook auto-generation | management | idea |
<!-- usecases:index:end -->

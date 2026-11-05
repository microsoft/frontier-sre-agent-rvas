# Use cases

Each numbered folder, `usecases/<NNNN>-<slug>/`, is one Azure SRE Agent use case. The domain is a field in `usecase.yaml`, not a folder. Add a folder and it shows up in the [Scenario Explorer](../web/scenarios.html), with its classification, components and status. Nothing else needs editing.

The ideas (`status: idea`) come from [alsanch/azure-sre-agent-scenarios](https://github.com/alsanch/azure-sre-agent-scenarios).

## Add a use case

1. Run `usecases/_framework/usecases.sh new <domain> <slug>`. It copies `usecases/_template/` into the next free number, for example `0079-<slug>`.
2. Fill in `usecase.yaml` and the other files.
3. Run `usecases/_framework/usecases.sh validate`, then `usecases/_framework/usecases.sh index --readme` to refresh the index below.

An idea only needs `usecase.yaml` with `status: idea`. Add files later, then change `status`.

## Layout

```text
usecases/
  <NNNN>-<slug>/       one use case; the folder name is its id
    usecase.yaml
    ...
```

Numbers are four digits, start at `0001` and are never reused. Folder names must match `<NNNN>-<slug>` and equal `id`, or `validate` fails. The commands accept the full id or just the slug.

## File convention

The file name tells the framework what a file is. Use these names.

| File | Component |
|------|-----------|
| `usecase.yaml` | Classification (required) |
| `README.md` | Walkthrough for people |
| `SKILL.md` or `skills/*/SKILL.md` (legacy flat layout). New use cases use `manifests/` with `azuresre.ai/v1` YAML (`skills/<name>/SKILL.md`, then `subagents/`, `tools/`, `scheduled-tasks/`, `incident-filters/`, `connectors/`) and `permissions/`; see `_template/` | Skill (at most 5 per use case) |
| `subagent-instructions-and-prompts.md` | Subagent |
| `generate-*.py` and `tool-parameters.schema.json` | Python tool and its parameters (both or neither) |
| `*-task-prompt.md` | Scheduled task |
| `grant-*` | Permission script |
| `tests/` | Test prompts and expected outcomes |
| `docs/` | Optional design notes, upstream guides and `images/`. Not read by the framework |
| `src/` | Optional sources for a built tool. If `src/build_tool.py` exists, `validate` runs `--check` on it |
| `sample-report/` | Example output |
| `images/` | Screenshots |

Folders that start with `_` are skipped.

## `usecase.yaml`

| Field | Required | Values |
|-------|----------|--------|
| `id` | yes | Same as the folder name, `<NNNN>-<slug>` |
| `title`, `summary` | yes | Free text |
| `domain` | yes | One of the domains in [`_framework/taxonomy.yaml`](_framework/taxonomy.yaml) |
| `trigger` | yes | List of `schedule`, `chat`, `alert` |
| `status` | yes | `idea`, `draft`, `built` or `validated`. `validate` checks it against the files |
| `products` | built and validated | List of Azure products, for example `entra-id` |
| `autonomy` | built and validated | `read-only`, `approval`, `autonomous` |
| `frequency`, `timeSaved`, `topPick`, `samplePrompt`, `source` | no | `timeSaved` is `High`, `Medium` or `Low`; `source.type` is `community` |

You declare `status`, and `validate` fails if the files do not support it:

* **idea**: no skill and no subagent, and no `README.md`.
* **draft**: a `README.md` but no skill and no subagent yet. The explorer shows a full documentation page, without a download.
* **built**: a skill and / or a subagent. With a `package` block in `usecase.yaml`, the site publishes a download.
* **validated**: built, plus `tests/` and `sample-report/`.

A tool (`generate-*.py`) needs a skill or a subagent next to it.

## Commands

All commands are in `usecases/_framework/usecases.sh` and need `jq` and Python 3 with PyYAML (or `yq`).

| Command | What it does |
|---------|--------------|
| `validate` | Checks every folder against the contract and the README index. Fails on a secret pattern. Bare GUIDs only warn. This is a pattern check, not a security guarantee. |
| `index -o <file> [--readme]` | Writes `usecases.json` for the explorer. `--readme` also rewrites the index below. |
| `portal-blocks <id or path> [-o file]` | Prints the text to paste into the portal: permissions, tool, skill, subagent, task. |
| `package <id or path or --all> [-o dir]` | Builds `<id>.zip` and `<id>.zip.sha256` for built and validated use cases that have a `package` block. The zip holds `usecases/<id>/` and the framework CLI, so the README commands work after unzipping. |
| `new <domain> <slug>` | Scaffolds `usecases/<NNNN>-<slug>` from `_template/` with the next number and sets `domain`. |
| `diff <id or path> --endpoint <url> [--subscription <id>]` | Compares the local tool, skill and subagent with the live agent. Prints NEW, CHANGED or SAME per resource. |
| `verify <id or path> --endpoint <url> [--subscription <id>]` | Checks that the resources in `tests/expected-config.yaml` exist on the live agent. |
| `deploy <id or path> --endpoint <url> [--subscription <id>] [--dry-run]` | Creates the tool, skill and subagent through the agent data-plane API. It does not create scheduled tasks. |

`deploy` follows the payloads of the [sre-agent-use-cases](https://github.com/marioaguileraaa/sre-agent-use-cases) reference. It has not been run against a live agent yet. Record the result of your first run here.

An agent allows five active skills. `validate` checks the limit per use case, not across the use cases you deploy to the same agent.

Every command accepts `--root DIR` before the command name to work on a use-case tree other than `usecases/`.

The Pages build (`make build-web`) runs `package --all` into `_site/downloads/` and publishes the README and `docs/` of every non-idea use case under `_site/usecases/<id>/`. The explorer links them from `usecase.html?id=<id>`.

Run the framework tests with `usecases/_framework/tests/run.sh`.

## Index

<!-- usecases:index:start -->
| ID | Title | Domain | Status |
|----|-------|--------|--------|
| [0001-6-month-cost-summary-trends](0001-6-month-cost-summary-trends/) | 6-month cost summary & trends | billing-entra-tenant | idea |
| [0001-six-month-cost-summary-trends](0001-six-month-cost-summary-trends/) | six month cost summary & trends | billing-entra-tenant | idea |
| [0002-agent-health-monitoring](0002-agent-health-monitoring/) | Agent health monitoring | management | idea |
| [0003-ai-model-inventory-retirement-lifecycle](0003-ai-model-inventory-retirement-lifecycle/) | AI model inventory & retirement lifecycle | resource-organization | idea |
| [0004-alert-fatigue-analysis](0004-alert-fatigue-analysis/) | Alert fatigue analysis | management | idea |
| [0005-alert-rules-best-practice-audit](0005-alert-rules-best-practice-audit/) | Alert rules best-practice audit | management | idea |
| [0006-all-write-operations-across-subscription-24h](0006-all-write-operations-across-subscription-24h/) | All write operations across subscription (24h) | management | idea |
| [0007-automated-compliance-remediation-tasks](0007-automated-compliance-remediation-tasks/) | Automated compliance remediation tasks | governance | idea |
| [0008-azure-firewall-rule-generation](0008-azure-firewall-rule-generation/) | Azure Firewall rule generation | network-topology | idea |
| [0009-azure-policy-assignment-assessment](0009-azure-policy-assignment-assessment/) | Azure Policy assignment assessment | governance | idea |
| [0010-backup-policy-compliance-gap-detection](0010-backup-policy-compliance-gap-detection/) | Backup policy compliance & gap detection | management | idea |
| [0011-budget-alerts-configuration-audit](0011-budget-alerts-configuration-audit/) | Budget alerts configuration audit | billing-entra-tenant | idea |
| [0012-certificate-renewal-automation](0012-certificate-renewal-automation/) | Certificate renewal automation | security | idea |
| [0013-changes-by-non-service-principal-users](0013-changes-by-non-service-principal-users/) | Changes by non-service-principal users | management | idea |
| [0014-changes-in-last-24h-for-a-resource](0014-changes-in-last-24h-for-a-resource/) | Changes in last 24h for a resource | management | idea |
| [0015-consolidated-cost-reporting](0015-consolidated-cost-reporting/) | Consolidated cost reporting | billing-entra-tenant | idea |
| [0016-cost-analysis-by-tag-environment](0016-cost-analysis-by-tag-environment/) | Cost analysis by tag/environment | billing-entra-tenant | idea |
| [0017-cost-anomaly-detection](0017-cost-anomaly-detection/) | Cost anomaly detection | billing-entra-tenant | idea |
| [0018-cross-period-cost-comparison-mg-level](0018-cross-period-cost-comparison-mg-level/) | Cross-period cost comparison (MG level) | billing-entra-tenant | idea |
| [0019-custom-policy-generation](0019-custom-policy-generation/) | Custom Policy generation | governance | idea |
| [0020-data-collection-rules-audit](0020-data-collection-rules-audit/) | Data collection rules audit | management | idea |
| [0021-databricks-dependency-configuration-review](0021-databricks-dependency-configuration-review/) | Azure Databricks dependency and configuration review | platform-devops | built |
| [0022-ddos-protection-coverage-audit](0022-ddos-protection-coverage-audit/) | DDoS protection coverage audit | network-topology | idea |
| [0023-defender-for-cloud-assessment](0023-defender-for-cloud-assessment/) | Defender for Cloud assessment | security | idea |
| [0024-diagnostic-settings-coverage-audit](0024-diagnostic-settings-coverage-audit/) | Diagnostic settings coverage audit | management | idea |
| [0025-disk-tier-down-opportunities](0025-disk-tier-down-opportunities/) | Disk tier-down opportunities | billing-entra-tenant | idea |
| [0026-dns-vpn-troubleshooting](0026-dns-vpn-troubleshooting/) | DNS/VPN troubleshooting | network-topology | idea |
| [0027-dns-zone-record-hygiene](0027-dns-zone-record-hygiene/) | DNS zone record hygiene | network-topology | idea |
| [0028-effective-policies-per-scope](0028-effective-policies-per-scope/) | Effective policies per scope | governance | idea |
| [0029-executive-operational-report-generation-pdf](0029-executive-operational-report-generation-pdf/) | Executive operational report generation (PDF) | management | idea |
| [0030-export-existing-resources-to-arm-bicep](0030-export-existing-resources-to-arm-bicep/) | Export existing resources to ARM/Bicep | platform-devops | idea |
| [0031-expressroute-vpn-gateway-health](0031-expressroute-vpn-gateway-health/) | ExpressRoute / VPN Gateway health | network-topology | idea |
| [0032-extension-health-across-vms](0032-extension-health-across-vms/) | Extension health across VMs | resource-organization | idea |
| [0033-failed-deployments-in-last-24h](0033-failed-deployments-in-last-24h/) | Failed deployments in last 24h | platform-devops | idea |
| [0034-find-built-in-policy-for-a-requirement](0034-find-built-in-policy-for-a-requirement/) | Find built-in policy for a requirement | governance | idea |
| [0035-fired-alerts-summary-last-24h](0035-fired-alerts-summary-last-24h/) | Fired alerts summary (last 24h) | management | idea |
| [0036-firewall-log-analysis-kql](0036-firewall-log-analysis-kql/) | Firewall log analysis (KQL) | network-topology | idea |
| [0037-high-privilege-operation-tracking](0037-high-privilege-operation-tracking/) | High-privilege operation tracking | identity-access | idea |
| [0038-identify-who-added-a-firewall-nsg-rule](0038-identify-who-added-a-firewall-nsg-rule/) | Identify who added a firewall/NSG rule | management | idea |
| [0039-kql-log-queries-common-patterns](0039-kql-log-queries-common-patterns/) | KQL log queries (common patterns) | management | idea |
| [0040-log-analytics-workspace-ingestion-cost-analysis](0040-log-analytics-workspace-ingestion-cost-analysis/) | Log Analytics workspace ingestion cost analysis | billing-entra-tenant | idea |
| [0041-logic-apps-code-definition-inspection](0041-logic-apps-code-definition-inspection/) | Logic Apps code/definition inspection | management | idea |
| [0042-management-group-hierarchy-audit](0042-management-group-hierarchy-audit/) | Management Group hierarchy audit | resource-organization | idea |
| [0043-move-resources-between-subscriptions](0043-move-resources-between-subscriptions/) | Move resources between subscriptions | resource-organization | idea |
| [0044-naming-tagging-convention-compliance](0044-naming-tagging-convention-compliance/) | Naming & tagging convention compliance | governance | idea |
| [0045-network-topology-diagram](0045-network-topology-diagram/) | Network topology diagram | network-topology | idea |
| [0046-operations-dashboard-generation](0046-operations-dashboard-generation/) | Operations dashboard generation | management | idea |
| [0047-orphaned-resources-cost-impact-analysis](0047-orphaned-resources-cost-impact-analysis/) | Orphaned resources & cost impact analysis | billing-entra-tenant | idea |
| [0048-overly-permissive-nsg-rules-audit](0048-overly-permissive-nsg-rules-audit/) | Overly permissive NSG rules audit | network-topology | idea |
| [0049-permissions-required-for-an-action](0049-permissions-required-for-an-action/) | Permissions required for an action | identity-access | idea |
| [0050-planned-maintenance-awareness](0050-planned-maintenance-awareness/) | Planned maintenance awareness | management | idea |
| [0051-policy-compliance-state-monitoring](0051-policy-compliance-state-monitoring/) | Policy compliance state monitoring | governance | idea |
| [0052-policy-exemptions-review](0052-policy-exemptions-review/) | Policy exemptions review | governance | idea |
| [0053-post-incident-review-automation](0053-post-incident-review-automation/) | Post-incident review automation | management | idea |
| [0054-private-endpoint-public-exposure-audit](0054-private-endpoint-public-exposure-audit/) | Private endpoint & public exposure audit | network-topology | idea |
| [0055-public-ip-inventory-justification](0055-public-ip-inventory-justification/) | Public IP inventory & justification | network-topology | idea |
| [0056-rbac-access-audit-who-has-what](0056-rbac-access-audit-who-has-what/) | RBAC access audit (who has what) | identity-access | idea |
| [0057-rbac-redundancy-over-privilege-assessment](0057-rbac-redundancy-over-privilege-assessment/) | RBAC redundancy & over-privilege assessment | identity-access | idea |
| [0058-resource-age-tracking](0058-resource-age-tracking/) | Resource age tracking | resource-organization | idea |
| [0059-resource-group-sprawl-detection](0059-resource-group-sprawl-detection/) | Resource group sprawl detection | resource-organization | idea |
| [0060-resource-health-status-summary](0060-resource-health-status-summary/) | Resource health status summary | management | idea |
| [0061-resource-lock-compliance-audit](0061-resource-lock-compliance-audit/) | Resource lock compliance audit | resource-organization | idea |
| [0062-resource-metrics-analysis](0062-resource-metrics-analysis/) | Resource metrics analysis | management | idea |
| [0063-resources-created-yesterday](0063-resources-created-yesterday/) | Resources created yesterday | resource-organization | idea |
| [0064-resources-with-highest-cost-increase](0064-resources-with-highest-cost-increase/) | Resources with highest cost increase | billing-entra-tenant | idea |
| [0065-rollback-command-generation-for-bad-changes](0065-rollback-command-generation-for-bad-changes/) | Rollback command generation for bad changes | management | idea |
| [0066-rto-rpo-gap-analysis](0066-rto-rpo-gap-analysis/) | RTO/RPO gap analysis | management | idea |
| [0067-service-health-incidents-resource-impact](0067-service-health-incidents-resource-impact/) | Service Health incidents & resource impact | management | idea |
| [0068-sku-reliability-assessment](0068-sku-reliability-assessment/) | SKU reliability assessment | management | idea |
| [0069-ssl-tls-certificate-expiration-tracking](0069-ssl-tls-certificate-expiration-tracking/) | SSL/TLS certificate expiration tracking | network-topology | idea |
| [0070-stale-rbac-assignments](0070-stale-rbac-assignments/) | Stale RBAC assignments | identity-access | idea |
| [0071-subscription-hygiene-score](0071-subscription-hygiene-score/) | Subscription hygiene score | resource-organization | idea |
| [0072-subscription-limits-approaching](0072-subscription-limits-approaching/) | Subscription limits approaching | resource-organization | idea |
| [0073-support-ticket-creation-pre-populated](0073-support-ticket-creation-pre-populated/) | Support ticket creation (pre-populated) | management | idea |
| [0074-top-consumer-services-identification](0074-top-consumer-services-identification/) | Top consumer services identification | billing-entra-tenant | idea |
| [0075-underutilized-resources-detection](0075-underutilized-resources-detection/) | Underutilized resources detection | billing-entra-tenant | idea |
| [0076-vm-performance-anomaly-detection](0076-vm-performance-anomaly-detection/) | VM performance anomaly detection | management | idea |
| [0077-vnet-peering-health-check](0077-vnet-peering-health-check/) | VNet peering health check | network-topology | idea |
| [0078-workbook-auto-generation](0078-workbook-auto-generation/) | Workbook auto-generation | management | idea |
<!-- usecases:index:end -->

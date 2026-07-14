# Demo Lab Validation Evidence

Last validated: 2026-06-12.

Subscription: `<Your Subscription ID>`.

Demo resource group: `rg-vflta-4iebz8`.

Sample Food resource group: `rg-vflta-food-4iebz8`.

Azure SRE Agent: `contoso-sre-agent-dev` in `rg-contoso-sre-agent-dev`.

> **Current-state note (2026-07-03).** This file is an append-only evidence log; the rows below are dated and historical. After the 2026-07-02/03 optimization the live inventory is **7 subagents, 8 skills (5 networking), 3 incident filters** (all wired to real alerts), with the orphan `incident-triage-coordinator` and the dormant `hub-firewall-network` / `config-audit-review` plans removed, the seven networking skills consolidated into five, and the cost subagent renamed to `cost-optimization-agent`. See [azure-sre-agent-architecture-and-configuration.md](azure-sre-agent-architecture-and-configuration.md) for the authoritative current state.

## Static Validation

| Check | Result | Notes |
| --- | --- | --- |
| `Student/Resources/scenarios/scripts/check-terraform-direct-values.sh` | Passed | `terraform direct-values check ok` |
| `terraform -chdir=04-terraform fmt -check -recursive` | Passed | No formatting drift after deployment fixes |
| `terraform -chdir=04-terraform validate` | Passed | `Success! The configuration is valid.` |
| `bash -n Student/Resources/scenarios/scripts/*.sh` | Passed | Demo scripts syntax validated |
| `Student/Resources/scenarios/scripts/sre-agent-config.sh validate --target skills` | Passed | All skill manifests validated |
| `Student/Resources/scenarios/scripts/sre-agent-config.sh validate --target subagents` | Passed | Subagent manifests validated |
| `Student/Resources/scenarios/scripts/sre-agent-config.sh validate --target knowledge-files` | Passed | Knowledge files validated |

## Live Deployment

| Check | Result | Evidence |
| --- | --- | --- |
| Terraform apply completed | Passed | Initial apply created lab resources; existing VNet Flow Logs were imported, then convergence apply completed with `0 added, 3 changed, 0 destroyed` |
| Terraform post-deploy drift | Passed | `terraform plan` returned no changes, `final-terraform-plan-exit=0` |
| Demo lab resource group created | Passed | `rg-vflta-4iebz8` |
| Sample Food resource group created | Passed | `rg-vflta-food-4iebz8` |
| Hub/app/data VNets created | Passed | `vnet-vflta-hub`, `vnet-vflta-app`, `vnet-vflta-data` |
| Azure Firewall private IP available | Passed | `10.10.3.4` |
| Azure Bastion available | Passed | `bas-vflta-hub`, `Succeeded`, `bst-c6d4b217-a8b8-47e4-85c5-cfb5f2583ee1.bastion.azure.com` |
| Flow log resources created | Passed | `fl-vflta-hub`, `fl-vflta-spoke-app`, `fl-vflta-spoke-data` |
| Flow logs enabled | Passed | All three VNet Flow Logs are `enabled=true`, Traffic Analytics enabled, interval `10` |
| Raw flow log container exists | Partial | Direct CLI container check is blocked by storage network rules because public access is disabled; flow log configuration points to `vflta4iebz8flow` |
| Traffic Analytics data visible | Pending ingestion | Flow Logs and Traffic Analytics are enabled; immediate query returned `Records=0`, expected until platform ingestion completes |
| Sample Food API reachable | Passed | `https://ca-vflta-food-api.happyforest-5b41fbb8.francecentral.azurecontainerapps.io/WeatherForecast -> HTTP 200` |
| Sample Food API domain endpoints reachable | Passed | `/api/FoodItems -> HTTP 200`, `/api/Restaurants -> HTTP 200` |
| Sample Food frontend reachable | Passed | `https://ca-vflta-food-frontend.happyforest-5b41fbb8.francecentral.azurecontainerapps.io -> HTTP 200` |
| Container Apps logs visible | Passed | System logs: API `1302`, frontend `56`; console logs: API `27`, frontend `22` |
| SRE Agent skills applied | Passed | 11 skills returned by live verify, including all imported VNet Flow Logs and Sample Food skills |
| SRE Agent subagents applied | Passed | `observability-investigator`, `sample-food-ordering-sre` returned by live verify |
| SRE Agent memory enabled | Passed | `AgentMemory is enabled`, document retrieval enabled |

## Fault Injection

| Scenario | Command | Evidence |
| --- | --- | --- |
| Baseline VM traffic | `Student/Resources/scenarios/scripts/generate-baseline-traffic.sh` | Passed, output `baseline-traffic-generated` |
| NSG deny | `Student/Resources/scenarios/scripts/trigger-nsg-block.sh` | Passed, output `denied-db-traffic-generated-from-10.20.1.10-to-10.30.2.10` |
| NSG restore | `Student/Resources/scenarios/scripts/restore-nsg-block.sh` | Passed, temporary deny rule removed |
| UDR asymmetry | `Student/Resources/scenarios/scripts/trigger-udr-asymmetry.sh` | Passed, output `udr-asymmetry-traffic-generated-baseline-next-hop-10.10.3.4` |
| UDR restore | `Student/Resources/scenarios/scripts/restore-udr-asymmetry.sh` | Passed, temporary route removed |
| NGINX service down | `Student/Resources/scenarios/scripts/trigger-nginx-down.sh` | Passed, `nginx=inactive` on `vm-vflta-web-1`; Syslog `nginx.service: Deactivated successfully.` ingested |
| NGINX restore | `Student/Resources/scenarios/scripts/restore-nginx.sh` | Passed, `nginx=active` on both web VMs after restore |
| Sample Food traffic | `Student/Resources/scenarios/scripts/generate-sample-food-app-traffic.sh` | Passed, 20 iterations generated |
| Sample Food load | `Student/Resources/scenarios/scripts/break-sample-food-app.sh` | Passed, 50 requests, 50 successes, 0 errors |

## Azure SRE Agent Final Desired-State Convergence

Updated 2026-06-12. The interim "SRE Agent skills/subagents applied" rows above captured the state before the Sample Food / Grubify lab and VNet Flow Logs configurations were merged into a single desired state. The rows below supersede them and record the converged, certified effective state on `contoso-sre-agent-dev`. All apply and supported deletes were executed with `Student/Resources/scenarios/scripts/sre-agent-config.sh`; full detail is in [crud-validation-report.md](../01-documentation-azure-sre-agent/crud-validation-report.md).

| Check | Result | Evidence |
| --- | --- | --- |
| Skills converged | Passed | 10 production skills returned by live verify; example `sre-diagnostics-baseline` purged |
| Subagents converged | Passed | `incident-handler`, `code-analyzer`, `issue-triager`, `sample-food-ordering-sre`; example `observability-investigator` purged |
| GitHub layer applied | Passed | `github` connector + `grubify` repo present; OAuth authorization pending before clone/link |
| Incident response wired | Passed | Platform `AzMonitor`; filter `sample-food-http-errors` -> `incident-handler` (autonomous); task `triage-grubify-issues` `Active` |
| Governance hook | Passed | `block-unsafe-remediation` promoted from example to production and applied |
| Examples purged from effective state | Passed | Zero `example-*` objects in live verify; all `example-*` files retained in Git and excluded from discovery |
| Deployment-method integrity | Passed | All apply + supported deletes via `sre-agent-config.sh`; only REST exception is the purge of the three example objects the script has no delete path for |
| KB indexing | Passed | `agentmemory/indexer-status` Success, documents processed, 0 failed |
| Idempotency | Passed | Re-apply per target reports `Applied` with no drift |

## VNet Flow Logs Guide Sub-Resources and Demo Alerts (Plan 3)

Updated 2026-06-12. Imported the SRE Agent sub-resources that previously existed only in the EMU project's portal-oriented guide, deployed them with `Student/Resources/scenarios/scripts/sre-agent-config.sh`, and enabled the Terraform demo alerts that drive incident routing. Full detail in [crud-validation-report.md](../01-documentation-azure-sre-agent/crud-validation-report.md).

| Check | Result | Evidence |
| --- | --- | --- |
| Demo alerts enabled | Passed | `terraform plan` = `2 to add, 0 to change, 0 to destroy`; `sample_food_http_5xx` severity 1, `denied_flow_spike` severity 2 present in state |
| Networking subagents | Passed | `network-traffic-analyst`, `azure-resource-config-auditor`, `incident-triage-coordinator`, `cost-and-retention-advisor` applied (Review, read-only tools) |
| Microsoft Learn MCP connector | Passed | `microsoft-learn-mcp` HTTP 200 with `type: AgentConnector`, `dataConnectorType: Mcp`, SSE transport, `authType: None` |
| Severity-band filters | Passed | `sample-food-http-errors` [Sev1] to `incident-handler`; `network-observability-review` [Sev2] to `network-traffic-analyst`; `config-audit-review` [Sev3] to `azure-resource-config-auditor` |
| Scheduled tasks | Passed | `daily-network-observability-health`, `flow-log-ingestion-freshness`, `weekly-cost-retention-review` enabled; `post-demo-drift-check` on-demand (disabled) |
| Networking knowledge base | Passed | 11 `vnet-flow-logs/` docs uploaded; indexer `documentsFailed: 0` |
| Idempotency | Passed | `subagents` and `incident-filters` re-apply report `Applied` with no drift |

## NGINX Service Down Scenario and Option B1 Routing (Plan 4)

Updated 2026-06-12. Added the NGINX service-down scenario (S4) end to end: guest-OS
observability via Azure Monitor Agent, a Sev2 log search alert, and Autonomous
routing with a human-in-the-loop gate on remediation (Option B1). Terraform changes
are in [nginx-observability.tf](../04-terraform/nginx-observability.tf);
the scenario is documented in [azure-sre-agent-demo-runbook.md](azure-sre-agent-demo-runbook.md).

| Check | Result | Evidence |
| --- | --- | --- |
| Terraform gates | Passed | `check-terraform-direct-values` ok; `fmt -check -recursive` clean; `validate` `Success!` |
| NGINX observability apply | Passed | Targeted apply `6 to add, 2 to change, 0 to destroy`; web VM identity updated in-place (no recreation) |
| Web VM managed identity | Passed | `SystemAssigned` on web VMs (`principal_id c2786d59-0ba4-4d9a-85c6-9e5ba599d1ac`) |
| AMA extension provisioned | Passed | `AzureMonitorLinuxAgent` `provisioningState: Succeeded` (version 1.0) on both web VMs |
| Syslog pipeline live | Passed | `rsyslog` active, `/etc/rsyslog.d/10-azuremonitoragent-omfwd.conf` present, `mdsd` running, Syslog rows ingested into `law-vflta-4iebz8` |
| nginx reconciled to desired state | Passed | nginx installed/enabled on both web VMs (cloud-init declared it; first-boot transient repaired via Run Command) |
| Alert rule present | Passed | `alert-vflta-nginx-down` enabled, severity 2 |
| **Fire test (end to end)** | **Passed** | `systemctl stop nginx` -> Syslog `systemd / nginx.service: Deactivated successfully.` on `vm-vflta-web-1` -> KQL match -> `alert-vflta-nginx-down` `monitorCondition: Fired` (2026-06-12T14:49Z) |
| Option B1 subagent | Passed | `network-traffic-analyst` live `agentMode` Autonomous; tools include `RunAzCliReadCommands` + `RunAzCliWriteCommands`; system prompt requires human approval before restart/delete/route change |
| Option B1 incident filter | Passed | `network-observability-review` live `agentMode: Autonomous`, `Sev2` |
| Governance hook intact | Passed | `block-unsafe-remediation` unchanged (ADR 0001); matcher `^(delete\|restart\|scale_down\|purge\|rotate_secret).*`, `permissionDecision: deny` |
| Lab restored | Passed | `restore-nginx.sh` -> `nginx=active` on both web VMs |

## GitHub MCP Connector — Option B (Plan 4)

Updated 2026-06-12. Implemented and applied the GitHub remote MCP server connector
(`connectors/github-mcp.yaml`) so the S2 (`code-analyzer`) and S3 (`issue-triager`)
GitHub tools work via a PAT-authenticated MCP connection, without the interactive
portal OAuth that the `github` OAuth connector requires.

| Check | Result | Evidence |
| --- | --- | --- |
| Manifest shape | Passed | `kind: AgentConnector`, `dataConnectorType: Mcp`, `extendedProperties{type: http, endpoint: https://api.githubcopilot.com/mcp/, authType: BearerToken, bearerToken: ${GITHUB_PAT}}` |
| Local validate | Passed | `validate --target connectors --name github-mcp` succeeds with a dummy `GITHUB_PAT` |
| Live apply | Passed | Applied to `contoso-sre-agent-dev` with `export GITHUB_PAT="$(gh auth token)"`; `Applied data-plane /api/v2/extendedAgent/connectors/github-mcp` |
| Live verify | Passed | `type: AgentConnector`, `dataConnectorType: Mcp`, `type: http`, `endpoint: https://api.githubcopilot.com/mcp/`, `authType: BearerToken` (bearer masked by API) |
| Secret hygiene | Passed | Token sourced from `gh auth token`, never printed (defensive redaction), `GITHUB_PAT` unset after apply |
| Token rotation caveat | Noted | The applied bearer is the `gh` OAuth session token (scopes incl. `repo`); if `gh` rotates the token, re-apply the connector. A fine-grained PAT gives a predictable expiry. |

## Maximum-Autonomy Reconfiguration and Incident-Platform Migration (2026-06-14)

Updated 2026-06-14. This section supersedes the Plan-4 governance rows ("Option B1 subagent",
"Option B1 incident filter", "Governance hook intact"): the lab was reconfigured for
**maximum autonomy**, and the Azure Monitor incident platform was migrated into Terraform. All
changes were applied live to `contoso-sre-agent-dev` and verified.

| Check | Result | Evidence |
| --- | --- | --- |
| Agent global autonomy | Passed | `az resource show` (api 2026-01-01): `actionConfiguration.mode = Autonomous`, `accessLevel = High`; in-place azapi update, 0 destroy |
| Governance hook removed | Passed | `delete --target hooks --name block-unsafe-remediation` succeeded; live `GET .../hooks` returns empty; manifest renamed `hooks/example-block-unsafe-remediation.yaml` (excluded from apply) |
| network-traffic-analyst autonomous remediation | Passed | system prompt rewritten to investigate **and** execute the fix (restart/NSG/route) and verify, no approval gate; live `agentType` Autonomous, tools include `RunAzCliWriteCommands` |
| Sev2 filter | Passed | `network-observability-review` live `agentMode: Autonomous`, `maxAutomatedInvestigationAttempts: 2` |
| Sev3 filter | Passed | `config-audit-review` live `agentMode: Autonomous`; handling subagent `azure-resource-config-auditor` `agentType` Autonomous (read-only tools, cannot modify resources) |
| incident-handler skill wired | Passed | live `enableSkills: true`, `allowedSkills: [sample-food-container-app-incident-analysis]` (Sev1 path now loads the Container Apps KQL) |
| Alert detection latency | Passed | `alert-vflta-nginx-down` `evaluationFrequency` `PT5M`→`PT1M`; `alert-vflta-denied-flow-spike` `PT10M`→`PT5M` (live `az monitor scheduled-query show`) |
| HTTP 5xx runbook enriched | Passed | `http-500-errors.md` adds 4 exact Container Apps KQL queries, demo baselines, and autonomous remediation commands (`az containerapp revision restart` / `update`); uploaded to agent memory |
| Incident platform migrated to Terraform | Passed | `incidentManagementConfiguration = { type: AzMonitor, connectionName: azmonitor }` added to the azapi agent body in `main.tf`; live verify shows `type: AzMonitor`; a full-body agent PUT no longer wipes it |
| Incident platform manifest neutralized | Passed | `incident-platforms/azure-monitor.yaml` renamed `example-azure-monitor-terraform-owned.yaml` (single owner = Terraform) |
| Terraform gates | Passed | `check-terraform-direct-values` ok; `fmt -check -recursive` clean; `validate` `Success!` |
| Quickstart response plan | Passed | live `GET .../incidentFilters` returns only the three intended filters; no `quickstart_handler` (no double-processing) |

Governance note: with the hook removed, least-privilege RBAC is the only blast-radius boundary
(the identity holds Contributor over the demo scopes). To re-harden, redeploy the hook, add a
global tool access policy, or set the filters back to `Review`. See
[ADR 0001](../01-documentation-azure-sre-agent/adr/0001-sre-agent-iac-boundaries.md).

## Domain-Routing Re-Architecting (2026-06-14)

Updated 2026-06-14. This section supersedes the "Sev2 filter" / "Sev3 filter" rows above and the
earlier severity-only band model: incident response plans were re-architected to a
**domain-routing rule** — each plan owns one failure domain, keyed by incident title
(`titleContains` / `titleNotContains`, case-insensitive) on top of severity. A new
`iaas-vm-incident-handler` subagent and a `hub-firewall-network` Sev1 plan were added; the Sev1
ACA plan and the Sev2 networking plan were title-scoped; `network-traffic-analyst` was narrowed to
the hub networking/firewall domain. All changes applied live to `contoso-sre-agent-dev` via full
desired-state reconcile (`apply --target subagents` + `apply --target incident-filters`) and verified.

| Check | Result | Evidence |
| --- | --- | --- |
| Pre-flight: live filter schema | Passed | `GET .../incidentFilters` confirms `titleContains` (string), `titleContainsAny` / `titleNotContains` (arrays), `mergeEnabled` / `mergeWindowHours`; all three prior filters already `Autonomous` |
| Pre-flight: incident titles | Passed | Azure Monitor `alerts` query: nginx incident title = `NGINX service down on web tier`; firewall = `afw-vflta-hub-NetworkRuleHit`; ACA = `alert-vflta-food-http-5xx` |
| Title matching is case-insensitive | Passed | Data-plane rejected `titleContainsAny: [nginx, NGINX]` with HTTP 400 `ValidationFailure` ("duplicate entry (case-insensitive)"); single-token `nginx` used |
| New IaaS subagent | Passed | `subagents/iaas-vm-incident-handler.yaml` applied; live tools `RunAzCliReadCommands` / `RunAzCliWriteCommands` / `GetAzCliHelp` / `QueryLogAnalyticsByWorkspaceId`; Autonomous |
| network-traffic-analyst domain narrowed | Passed | system prompt / description extended to hub Azure Firewall (`AZFWNetworkRule`), nginx removed (now owned by the IaaS handler); stays Autonomous with write tools |
| Sev1 split by domain | Passed | `sample-food-http-errors` `titleContains: food` → `incident-handler`; `hub-firewall-network` `titleContains: afw` → `network-traffic-analyst`; disjoint |
| Sev2 split by domain | Passed | `web-tier-nginx` `titleContains: nginx` → `iaas-vm-incident-handler`; `network-observability-review` `titleNotContains: nginx` → `network-traffic-analyst`; disjoint |
| Full desired-state deploy | Passed | `apply --target subagents` (9 agents) and `apply --target incident-filters` (5 plans) both exit 0 |
| Live routing matrix | Passed | `GET .../incidentFilters`: 5 plans, all `agentMode: Autonomous`, disjoint at every severity (Sev1 food/afw; Sev2 nginx/not-nginx; Sev3 config) |
| Terraform gates | Passed | `check-terraform-direct-values` ok; no Terraform or script change required |
| Local validate | Passed | `validate --target subagents` and `validate --target incident-filters` both succeed |

Notes: (1) the `afw-vflta-hub-NetworkRuleHit` alert originates from a hub Azure Firewall under a
resource group whose suffix differs from the current lab apply; it is wired as a domain-routing
target so Sev1 coverage is complete. (2) Fire tests (autonomous remediation) were **not** re-run in
this change; routing and autonomy were verified by live `GET`. (3) The production-posture exception
(gate the cross-spoke networking domain) is recorded in
[ADR 0001](../01-documentation-azure-sre-agent/adr/0001-sre-agent-iac-boundaries.md).

## Subagent Rename — `incident-handler` → `aca-app-incident-handler` (2026-06-14)

Updated 2026-06-14. The Sample Food / Grubify Azure Container Apps application incident handler,
imported as `incident-handler`, was renamed to `aca-app-incident-handler` so the subagent name
declares its failure domain — uniform with `iaas-vm-incident-handler` (the
`<platform>-incident-handler` convention) and with the domain-routing rule. Spec, tools, skills, and
autonomy are unchanged (Autonomous; `RunAzCliReadCommands` / `RunAzCliWriteCommands` /
`QueryLogAnalyticsByWorkspaceId` / `QueryAppInsightsByResourceId` / `ExecutePythonCode`; skill
`sample-food-container-app-incident-analysis`). This supersedes the `incident-handler` name in the
rows above for the live Sev1 ACA-app owner.

| Check | Result | Evidence |
| --- | --- | --- |
| Manifest renamed | Passed | `subagents/incident-handler.yaml` → `subagents/aca-app-incident-handler.yaml`; `metadata.name: aca-app-incident-handler` |
| Filter repointed | Passed | `automations/incident-filters/sample-food-http-errors.yaml` `handlingAgent: aca-app-incident-handler` |
| Local gates | Passed | `validate --target subagents` and `--target incident-filters` succeed; `check-terraform-direct-values` ok; `fmt -check` / `validate` clean |
| New subagent live | Passed | `apply --target subagents --file .../aca-app-incident-handler.yaml` → `Applied data-plane /api/v2/extendedAgent/agents/aca-app-incident-handler` |
| Filter live | Passed | `apply --target incident-filters --file .../sample-food-http-errors.yaml` exit 0; `GET .../incidentFilters/sample-food-http-errors` → `properties.handlingAgent = aca-app-incident-handler` |
| Old subagent deleted | Passed | direct data-plane `DELETE .../agents/incident-handler` → HTTP 2xx; `GET .../agents` no longer lists `incident-handler` (only `aca-app-incident-handler` and `iaas-vm-incident-handler`) |
| Live routing matrix | Passed | `GET .../incidentFilters`: 5 plans, all `Autonomous`, disjoint; Sev1 `food` → `aca-app-incident-handler`, `afw` → `network-traffic-analyst`; Sev2 `nginx` → `iaas-vm-incident-handler`, not-`nginx` → `network-traffic-analyst`; Sev3 → `azure-resource-config-auditor` |

Notes: documentation across `01-documentation-azure-sre-agent/` and `02-documentation-demo-lab-env/`
and `06-sre-agent-configuration/README.md` was updated to the new name; the Terraform comment in
`sample-food-observability.tf` was updated for accuracy (no resource change). Historical rows
above that read `incident-handler` are point-in-time records and are intentionally left intact.

## Convergence Audit — as-is vs desired state (2026-06-14)

Updated 2026-06-14. Full audit comparing the live agent (`contoso-sre-agent-dev`) and Terraform
state against the local desired state. Outcome: the SRE Agent data plane and the Terraform-owned
agent body **converge**; two desired-state coherence gaps were found and fixed; the only Terraform
`plan` diff is pre-existing non-SRE-Agent infrastructure drift.

| Check | Result | Evidence |
| --- | --- | --- |
| Data-plane object counts | Passed | live `GET` vs local non-`example-*` manifests: subagents 9/9, incidentFilters 5/5, scheduledtasks 5/5, connectors 3/3 (+2 Terraform telemetry: `application-insights`, `log-analytics`), repos 1/1, skills 10/10, commonprompts 0/0 |
| Agent body (ARM) | Passed | `mode=Autonomous`, `accessLevel=High`, `defaultModel=claude-opus-4-6/Anthropic`, `incidentManagementConfiguration=AzMonitor/azmonitor` — all match desired |
| Subagent deep fields | Passed | `enableSkills`, tool counts, and `allowedSkills` of all 9 subagents match their manifests (incl. `aca-app-incident-handler`: skills on, 7 tools, ACA skill). `agentType` is not echoed by the API |
| Gap 1 — hooks (FIXED) | Passed | `hooks/` held both `block-unsafe-remediation.yaml` (non-`example`, `enabled:false`) and `example-block-unsafe-remediation.yaml`. A full `apply` would deploy the non-`example` file, and the API ignores `spec.enabled` (uses `activationMode=always`), so the gate would activate — breaking max autonomy. Live was already correct (0 hooks). Removed the redundant manifest (`git rm`); `hooks/` now holds only `example-*`, so a full `apply` deploys no hook |
| Gap 2 — knowledge (FIXED) | Passed | the `/connectors` endpoint surfaces only 4 `KnowledgeFile` (the `sample-food` group) and never the 11 `vnet-flow-logs` docs — it does not enumerate agent memory and is not authoritative (`agentmemory/status` returns only flags). Re-ran `apply --target knowledge-files` → 15/15 “Uploaded knowledge file” (`curl -fsS`, so all 15 = HTTP 2xx); upload is idempotent (keyed by basename) |
| Terraform convergence | Passed | `terraform plan` = 0 add, 8 change, 0 destroy; `azapi_resource.agent` body and the 3 alerts show **no diff** (converged) |
| Terraform drift isolated | Open (decision) | the 8 changes are pre-existing non-SRE-Agent drift: 6 `azurerm_linux_virtual_machine` (`bypass_platform_safety_checks_on_user_schedule_enabled` true→false, in-place) and 2 `azurerm_subnet` (`default_outbound_access_enabled` false→true — **security**: live is secure-by-default, config would re-enable default egress). Redeploy the agent with `-target=azapi_resource.agent`; do not run a full `apply` until the subnet drift is resolved |

Notes: (1) the hook-dedup removal completes the originally intended rename — `example-block-unsafe-remediation.yaml`
remains as the re-harden reference. (2) No current-state document required edits: the audit confirmed the docs
already describe “no hook deployed” and “15 knowledge docs”; the fixes brought the repo and live into line with
what the docs assert. (3) Fire tests (autonomous remediation) were not run in this audit.
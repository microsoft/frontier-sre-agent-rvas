# Azure SRE Agent Configuration CRUD Validation Report

Date: 2026-06-11

Scope: `azure-sre-agent-config/` desired state for Azure SRE Agent `contoso-sre-agent-dev` in `rg-contoso-sre-agent-dev`.

> **Current-state note (2026-07-03).** This is a historical CRUD validation record from 2026-06-11. The instance names below (`sre-diagnostics-baseline`, `observability-investigator`, `example-service`, `example-plugin-config`, `example-runbook.md`, ...) were the `example-*` manifests used for that test run; those manifests have since been removed from the repository. The current live inventory is **7 subagents, 8 skills, 3 incident filters** - see [azure-sre-agent-architecture-and-configuration.md](../demo-lab/azure-sre-agent-architecture-and-configuration.md) for the authoritative current state.

## Summary

The script and configuration were tested with local validation, full-folder dry-run, and live per-instance CRUD where the API supports it and required secrets were available.

## Passed Live CRUD

| Target | Instance | Result |
| --- | --- | --- |
| `skills` | `sre-diagnostics-baseline` | Create/read/update/delete/restore passed. |
| `subagents` | `observability-investigator` | Create/read/update/delete/restore passed. |
| `common-prompts` | `incident-summary-executive` | Create/read/update/delete/restore passed. |
| `scheduled-tasks` | `daily-health-check` | Create/read/update/delete/restore passed. |
| `incident-platforms` | `azure-monitor` | Create/read passed; delete means clear to `None`; PATCH is asynchronous and can return `OperationConflict` if repeated immediately. |
| `incident-filters` | `sev2-production-only` | Create/read/update/delete/restore passed after `AzMonitor` was active. |
| `repos` | `example-service` | Create/read/update/delete/restore passed after payload was corrected to `type: CodeRepo`. |
| `hooks` | `block-unsafe-remediation` | Create/read/update/delete/restore passed after payload was corrected to `type: GlobalHook`. |
| `plugin-configs` | `example-plugin-config` | Create/read/update/delete/restore passed. |
| `knowledge-files` | `example-runbook.md` | Upload/read/re-upload/delete/restore passed. |
| `http-triggers` | `maintenance-window-start` | Create/read/update-idempotent passed; delete is not documented by the API used here. |
| `plugin-marketplaces` | `example-marketplace` | POST/read/re-POST passed; per-object delete is not documented by the API used here. |
| `plugin-installations` | `example-plugin-installation` | POST/read/re-POST passed; per-object delete is not documented by the API used here. |

## Blocked Or Skipped

| Target | Instance | Status | Reason |
| --- | --- | --- | --- |
| `tools` | `azure-resource-graph-readonly` | Skipped as `api-preview-blocked`. | Data-plane rejected documented/custom tool object types with `InvalidObjectType`; ARM fallback is blocked by Agent Extensions tenant restriction. |
| `connectors` | `dynatrace-mcp` | Not live-applied. | Requires real `DYNATRACE_MCP_BEARER_TOKEN`; dummy secrets were not deployed. |
| `incident-platforms` | `pagerduty` | Not live-applied. | Requires real `PAGERDUTY_CONNECTION_KEY`; dummy secrets were not deployed. |

## Corrections Applied

| Area | Correction |
| --- | --- |
| Secret handling | Replaced hardcoded fake secret values with `${DYNATRACE_MCP_BEARER_TOKEN}` and `${PAGERDUTY_CONNECTION_KEY}` placeholders. |
| Manifest selection | Selection now uses raw manifest names, so unrelated secret-backed manifests are not rendered during selective operations. |
| Repository payload | Data-plane repo PUT now sends `{ name, type: "CodeRepo", properties: { url, type, description? } }`. |
| Hook payload | Hook apply now uses `type: "GlobalHook"`, matching Microsoft template assembly. |
| Incident filter | Manifest now uses Microsoft template shape: `incidentPlatform`, `priorities`, `handlingAgent`, `agentMode`, and related fields. |
| HTTP trigger payload | POST create now sends `name` top-level, and apply skips create when the trigger already exists. |
| Tool sample | Marked as `spec.deployment.status: api-preview-blocked`; script skips apply/verify/delete for that manifest. |

## Full Folder Validation

Full `validate` intentionally fails without required secrets. With temporary dry-run-only placeholder variables, full-folder `validate` and `plan` passed. A live full-folder `apply` was not executed because it would require deploying real Dynatrace and PagerDuty secrets.

## Final Notes

The current live state was restored for resources that were deleted during tests. `azure-monitor` remains the active incident platform so `sev2-production-only` can stay valid.

## Merged Desired-State Deployment and Example Purge

Date: 2026-06-12.

Scope: full desired state for Azure SRE Agent `contoso-sre-agent-dev` in `rg-contoso-sre-agent-dev` (subscription `<Your Subscription ID>`, region `swedencentral`), after integrating the Sample Food / Grubify lab and the VNet Flow Logs configuration into a single desired state. All apply and DELETE-supported purge operations were executed with `infra/scripts/sre-agent-config.sh`.

### Deployed (apply via script, staged per target, verified after each)

| Target | Instance(s) | Result |
| --- | --- | --- |
| `skills` | 10 production skills (VNet Flow Logs + Sample Food) | Applied. |
| `subagents` | `incident-handler`, `code-analyzer`, `issue-triager`, `sample-food-ordering-sre` | Applied (autonomous; write tools retained). |
| `hooks` | `block-unsafe-remediation` (promoted from example to production) | Applied; compensating control for autonomous write subagents. |
| `connectors` | `github` (GitHubOAuth) | Applied; one-time OAuth authorization still pending. |
| `repos` | `grubify` (`lpassaretta_microsoft/grubify`, `authConnectorName: github`) | Applied; clone/link completes after OAuth. |
| `incident-platforms` | `azmonitor` (ARM PATCH `AzMonitor`) | Applied. |
| `incident-filters` | `sample-food-http-errors` -> `incident-handler` | Applied after retry (see findings). |
| `scheduled-tasks` | `triage-grubify-issues` (`0 */12 * * *` -> `issue-triager`) | Applied, status `Active`. |

### Examples purged from the effective state (kept in Git, ignored by discovery)

Deleted via `sre-agent-config.sh delete --file <example> --yes` (the `--file` selector bypasses the `example-*` discovery exclusion): `example-service` (repo), `sre-diagnostics-baseline` (skill), `observability-investigator` (subagent), `incident-summary-executive` (common prompt), `daily-health-check` (scheduled task), `example-plugin-config`, `example-runbook.md` (knowledge), and the residual `sev2-production-only` incident filter (re-surfaced after AzMonitor reactivation). Removed via data-plane REST because the script exposes no per-object delete for them: `example-marketplace`, `example-plugin-installation`, and the `maintenance-window-start` HTTP trigger. Final full `verify` shows zero `example-*` objects in the effective state.

### Findings

| Finding | Detail |
| --- | --- |
| Incident-filter timing | The first `incidentFilters` PUT returned HTTP 400 because the AzMonitor incident-platform PATCH is asynchronous. The lab uses sleep+retry. `sre-agent-config.sh` was enhanced so `data_put_extended` accepts optional `max_attempts`/`retry_sleep` (default 1 = unchanged for every other caller) and `data_put_incident_filter` opts in (default 5 attempts, 10s). Re-apply via the script is idempotent. |
| Plugin/HTTP-trigger DELETE | Live validation showed `plugins/marketplaces`, `plugins/installations`, and `httptriggers` DO accept DELETE (HTTP 202/200) even though per-object DELETE is not documented in Microsoft Learn. |
| Hook promotion | `block-unsafe-remediation` was an example but is the approval guardrail for the autonomous write subagents; it was promoted to a production manifest rather than purged. |

### Pending manual step

GitHub OAuth authorization must be completed once in the SRE Agent portal; then re-run `sre-agent-config.sh apply --target repos` to establish the `authConnectorName` link and trigger the Grubify clone, after which `issue-triager`/`code-analyzer` GitHub tools and the triage scheduled task are fully functional.

## VNet Flow Logs Guide Sub-Resources and Demo Alerts (Plan 3)

Scope: import the SRE Agent sub-resources that existed only in the EMU project's portal-oriented guide (`azure-sre-agent-implementation-guide.md`) into the repo standard, deploy them with `infra/scripts/sre-agent-config.sh`, and enable the demo alerts that drive the incident-routing scenarios. Target unchanged (`contoso-sre-agent-dev`).

### Deployed (apply via script, staged per target, verified after each)

| Target | Instance(s) | Result |
| --- | --- | --- |
| `knowledge-files` | 11 `vnet-flow-logs/` docs (+ 4 `sample-food/`, now script-managed) | Uploaded; indexer `documentsFailed: 0`. |
| `subagents` | `network-traffic-analyst`, `azure-resource-config-auditor`, `incident-triage-coordinator`, `cost-and-retention-advisor` (Review; read-only tools) | Applied. |
| `connectors` | `microsoft-learn-mcp` (`Mcp`, SSE, no auth) | Applied after type fix (see findings). |
| `incident-filters` | `sample-food-http-errors` (Sev1 -> `incident-handler`), `network-observability-review` (Sev2 -> `network-traffic-analyst`), `config-audit-review` (Sev3 -> `azure-resource-config-auditor`) | Applied; disjoint severity bands. |
| `scheduled-tasks` | `daily-network-observability-health`, `flow-log-ingestion-freshness`, `weekly-cost-retention-review` (enabled), `post-demo-drift-check` (on-demand, disabled) | Applied. |
| Terraform alerts | `sample_food_http_5xx` (severity 1), `denied_flow_spike` (severity 2) | `count = 0` removed; created (`2 to add, 0 to change, 0 to destroy`). |

### Findings

| Finding | Detail |
| --- | --- |
| Connector object type | A data-plane connector requires `type: AgentConnector`. The first `microsoft-learn-mcp` PUT used `type: Connector` (copied from the example template) and returned HTTP 400 `InvalidObjectType`. Fixed the manifest `kind` to `AgentConnector` (and corrected the same latent bug in `example-dynatrace-mcp.yaml`), then re-applied via the script. Verified `Mcp` + SSE + `authType: None` returns HTTP 200. |
| Incident-filter title matching | The incident-filter schema also exposes `titleContains`, `titleContainsAny`, `titleContainsAll`, and `titleNotContains` (visible on data-plane GET). Severity is not the only selector. This deployment uses disjoint severity bands; title matching remains available for finer routing later. |
| Knowledge subdirectory discovery | `find_knowledge_files` was made recursive so grouped knowledge bases under `knowledge/files/<group>/` are bulk-discovered; the data-plane upload keys by file basename. This also brought the pre-existing `sample-food/` knowledge under script management. |
| GET field echo | Data-plane GET returns spec values under `.properties.*` for incident filters, scheduled tasks, and agents (not top-level). Subagent `agentType` is still not echoed; routing autonomy is enforced at the filter/task `agentMode`. |

### Demo scenario routing

| Scenario | Project | Trigger script | Alert (severity) | Filter | Handling agent | Restore |
| --- | --- | --- | --- | --- | --- | --- |
| HTTP 5xx | Sample Food | `break-sample-food-app.sh` | `sample_food_http_5xx` (Sev1) | `sample-food-http-errors` | `incident-handler` (Autonomous) | Automatic when load stops |
| Denied flow (NSG) | VNet Flow Logs | `trigger-nsg-block.sh` | `denied_flow_spike` (Sev2) | `network-observability-review` | `network-traffic-analyst` (Review) | `restore-nsg-block.sh` |
| UDR asymmetry | VNet Flow Logs | `trigger-udr-asymmetry.sh` | none (manual) | none | `/agent network-traffic-analyst` | `restore-udr-asymmetry.sh` |

## NGINX Service-Down Scenario and Option B1 Routing (Plan 4)

Date: 2026-06-12.

Scope: add the NGINX service-down scenario (guest-OS observability via Azure
Monitor Agent and Syslog, a Sev2 log search alert) and reconfigure Sev2 network
routing to **Option B1** — Autonomous investigation with a human-in-the-loop gate
on remediation. Terraform changes are in
[nginx-observability.tf](../../infra/nginx-observability.tf);
the demo script is [azure-sre-agent-demo-runbook.md](../../docs/demo-lab/azure-sre-agent-demo-runbook.md).
Target unchanged (`contoso-sre-agent-dev`).

### Applied (data-plane PUT via script, verified after each)

| Target | Instance | Change | Result |
| --- | --- | --- | --- |
| `subagents` | `network-traffic-analyst` | `agent_type` Review -> Autonomous; added `RunAzCliWriteCommands`; system prompt now requires human approval before restart/NSG delete/route change; scenario coverage extended to nginx-down | Applied; live verify shows Autonomous instructions + read/write tools. |
| `incident-filters` | `network-observability-review` | `agentMode` Review -> Autonomous; `customInstructions` extended to cover nginx-down and the human-gate | Applied; live verify shows `agentMode: Autonomous`, `Sev2`. |

The `block-unsafe-remediation` hook is **unchanged** (ADR 0001). Autonomy is scoped
to diagnostics; the irreversible step is gated by the hook plus the subagent system
prompt (defense in depth).

> **Superseded 2026-06-14 (maximum autonomy).** The Option B1 human-in-the-loop posture above
> was replaced by full autonomy: the `block-unsafe-remediation` hook was deleted live (manifest
> renamed `example-*`), the agent global mode is `Autonomous`/`accessLevel High`, and the
> Sev1/Sev2/Sev3 filters and their subagents all run Autonomous, so the agent now remediates
> (restart/NSG delete/route change) with no approval gate. Least-privilege RBAC is the
> remaining boundary. The Azure Monitor incident platform was also migrated into the Terraform
> agent body (`incidentManagementConfiguration`). See
> [validation-evidence.md — Maximum-Autonomy Reconfiguration](../demo-lab/validation-evidence.md)
> and [ADR 0001](adr/0001-sre-agent-iac-boundaries.md).

### Terraform (targeted apply)

| Resource | Result |
| --- | --- |
| `azurerm_linux_virtual_machine.web` identity `SystemAssigned` | Updated in-place (no recreation). |
| `azurerm_virtual_machine_extension.web_ama` (x2) | Created (AMA, `AzureMonitorLinuxAgent`). |
| `azurerm_monitor_data_collection_rule.web_syslog` | Created (Syslog -> `law-vflta-*`). |
| `azurerm_monitor_data_collection_rule_association.web_syslog` (x2) | Created. |
| `azurerm_monitor_scheduled_query_rules_alert_v2.nginx_down` | Created (`alert-vflta-nginx-down`, Sev2). |

Plan summary: `6 to add, 2 to change, 0 to destroy`.

### Fire test (end to end, live)

`trigger-nginx-down.sh` -> Syslog row `systemd / nginx.service: Deactivated
successfully.` on `vm-vflta-web-1` -> alert KQL match -> `alert-vflta-nginx-down`
`monitorCondition: Fired` (2026-06-12T14:49Z). Restored with
`restore-nginx.sh` (`nginx=active` on both web VMs).

### Findings

| Finding | Detail |
| --- | --- |
| nginx not preinstalled | The web cloud-init declares `nginx`, but a first-boot transient left it uninstalled on the web VMs (egress to the Ubuntu archive returns 200, so not a firewall block). Reconciled to the declared desired state via Run Command (`apt-get install -y nginx; systemctl enable --now nginx`). |
| Syslog warm-up | After the DCR association is created, AMA writes `/etc/rsyslog.d/10-azuremonitoragent-omfwd.conf` and `mdsd` begins forwarding; the Syslog table is briefly empty during warm-up before the first rows appear. |
| Alert evaluation latency | The Sev2 log search alert fires on the next PT5M evaluation after Syslog ingestion (observed ~6 minutes from event to `Fired`). |

## GitHub MCP Connector (Option B for S2/S3)

Date: 2026-06-12.

Scope: add GitHub's official remote MCP server as a data-plane connector
(`connectors/github-mcp.yaml`) so the S2 (`code-analyzer`) and S3 (`issue-triager`)
GitHub tools work via PAT-authenticated MCP, without the interactive OAuth
authorization required by the `github` OAuth connector. Additive: the OAuth
connector and `grubify` repo link remain for the SRE Agent deep-clone path.

### Manifest

| Field | Value |
| --- | --- |
| `kind` | `AgentConnector` |
| `dataConnectorType` | `Mcp` |
| `extendedProperties.type` | `http` |
| `extendedProperties.endpoint` | `https://api.githubcopilot.com/mcp/` |
| `extendedProperties.authType` | `BearerToken` |
| `extendedProperties.bearerToken` | `${GITHUB_PAT}` (runtime injection; never committed) |

Endpoint, HTTP transport, and `Authorization: Bearer <PAT>` header are from the
official remote GitHub MCP server docs (https://github.com/github/github-mcp-server).
Shape mirrors `example-dynatrace-mcp.yaml`; no `partnerType` (generic remote MCP).

### Validation

| Check | Result |
| --- | --- |
| Local validate (`--target connectors --name github-mcp`) | Passed with a dummy `GITHUB_PAT` (placeholder substitution + YAML shape). |
| Live apply | Passed (2026-06-12). Applied to `contoso-sre-agent-dev` using the `gh` CLI session token: `export GITHUB_PAT="$(gh auth token)"` then `apply --target connectors --name github-mcp`. Live `verify` returns `type: AgentConnector`, `dataConnectorType: Mcp`, `type: http`, `endpoint: https://api.githubcopilot.com/mcp/`, `authType: BearerToken`; the bearer token is masked by the API. The token was never printed (defensive `sed` redaction) and `GITHUB_PAT` was unset after apply. |

### Findings

| Finding | Detail |
| --- | --- |
| Validate requires placeholder resolution | `sre-agent-config.sh validate` fails fast if `${GITHUB_PAT}` is unset (`GITHUB_PAT is not set`). A dummy value passes local validation; a real PAT is only needed for `apply`. |
| PAT reuse | The connector reuses the existing `GITHUB_PAT` placeholder already declared in `.env.example`; no new secret placeholder was introduced. |
| Token source = gh CLI session | The applied bearer is the `gh auth token` OAuth session token for `lpassaretta_microsoft` (scopes `gist, read:org, repo, workflow`). The `repo` scope covers S2/S3 but is broader than a fine-grained PAT (all repos, not just `grubify`). |
| Token rotation caveat | The captured token is a point-in-time snapshot stored in the connector. If `gh` refreshes/rotates its OAuth token, re-run the apply to refresh the connector. A fine-grained PAT with an explicit expiry is more predictable for long-lived use. |

## Incident-Response Domain-Routing Re-Architecting (2026-06-14)

Date: 2026-06-14.

Scope: re-architect the incident response plans from severity-only bands to a
**domain-routing rule** — each plan owns one failure domain, keyed by incident title
(`titleContains` / `titleNotContains`, case-insensitive) on top of severity. Adds the
`iaas-vm-incident-handler` subagent and the `hub-firewall-network` Sev1 plan, title-scopes the
ACA and networking plans, and narrows `network-traffic-analyst` to the hub networking/firewall
domain. No Terraform or `sre-agent-config.sh` change. Target unchanged (`contoso-sre-agent-dev`).

> **Supersedes the earlier "disjoint severity bands" model** (Plan 3 deployment table and the
> "Incident-filter title matching" finding). The routing selector is now domain (title) × severity.

### Applied (full desired-state reconcile via script, verified)

| Target | Instance(s) | Change | Result |
| --- | --- | --- | --- |
| `subagents` | `iaas-vm-incident-handler` (new) | Autonomous IaaS web-tier handler; tools read/write CLI + LA; owns nginx-down / VM service health | Applied. |
| `subagents` | `network-traffic-analyst` | Domain narrowed to hub networking + hub Azure Firewall (`AZFWNetworkRule`); nginx removed; stays Autonomous + write tools | Applied. |
| `subagents` | all 9 | Full `apply --target subagents` desired-state reconcile | Applied (exit 0). |
| `incident-filters` | `sample-food-http-errors` | `titleContains: food` (Sev1 ACA app) | Applied. |
| `incident-filters` | `hub-firewall-network` (new) | `titleContains: afw` (Sev1 hub firewall) -> `network-traffic-analyst` | Applied. |
| `incident-filters` | `web-tier-nginx` (new) | `titleContains: nginx` (Sev2 web tier) -> `iaas-vm-incident-handler` | Applied. |
| `incident-filters` | `network-observability-review` | `titleNotContains: nginx` (Sev2 hub networking) | Applied. |
| `incident-filters` | all 5 | Full `apply --target incident-filters` desired-state reconcile | Applied (exit 0). |

### Live verification

Live `GET /api/v2/extendedAgent/incidentFilters` returns five plans, all `agentMode: Autonomous`,
disjoint at every severity: Sev1 `food`->`incident-handler` and `afw`->`network-traffic-analyst`;
Sev2 `nginx`->`iaas-vm-incident-handler` and not-`nginx`->`network-traffic-analyst`; Sev3
`config-audit-review`->`azure-resource-config-auditor`. Gates: `validate --target subagents` and
`validate --target incident-filters` pass; `check-terraform-direct-values` ok.

### Findings

| Finding | Detail |
| --- | --- |
| Title matching is case-insensitive | A `titleContainsAny: [nginx, NGINX]` PUT returned HTTP 400 `ValidationFailure` ("TitleContainsAny[1] 'NGINX' is a duplicate entry (case-insensitive)"). A single token (`nginx`) is therefore sufficient and is what the manifests use. |
| Live incident-title source | The incident title equals the Azure Monitor alert `.name`: `NGINX service down on web tier` (display name, not the rule name `alert-vflta-nginx-down`); `alert-vflta-food-http-5xx` and `afw-vflta-hub-NetworkRuleHit` use their rule names. |
| Hub firewall alert provenance | `afw-vflta-hub-NetworkRuleHit` (Sev1) originates from a hub Azure Firewall under a resource group whose suffix differs from the current lab apply; it is wired as a domain-routing target so Sev1 coverage is complete. |
| Zero IaC/script change | Domain routing was achieved entirely through manifest `titleContains` / `titleNotContains`; `incident_filter_properties` forwards the whole `spec` verbatim, so no `sre-agent-config.sh` change was needed, and existing alert title tokens avoided any Terraform rename. |
| Full-autonomy posture retained | All five plans and their handling subagents run `Autonomous`; the production-posture exception (gate the cross-spoke networking domain) is in [ADR 0001](adr/0001-sre-agent-iac-boundaries.md). Fire tests (autonomous remediation) were not re-run; routing/autonomy verified by live `GET`. |

## Subagent Rename — `incident-handler` → `aca-app-incident-handler` (2026-06-14)

Date: 2026-06-14.

Scope: rename the imported Sample Food / Grubify Azure Container Apps application incident handler
from `incident-handler` to `aca-app-incident-handler` so the subagent name declares its failure
domain, uniform with `iaas-vm-incident-handler` and the domain-routing rule. CRUD touches only the
subagent name and the one filter that references it; no spec/tool/skill/autonomy change, and no
Terraform or `sre-agent-config.sh` change. Target unchanged (`contoso-sre-agent-dev`).

> **Supersedes the `incident-handler` name** in the "Domain-Routing Re-Architecting" section above
> for the live Sev1 ACA-app owner. The routing selector (domain × severity) is unchanged.

### Applied (live, verified)

| Op | Instance | Change | Result |
| --- | --- | --- | --- |
| Update (rename) | `subagents/incident-handler.yaml` | File → `aca-app-incident-handler.yaml`; `metadata.name: aca-app-incident-handler` | Done. |
| Create | `agents/aca-app-incident-handler` | `apply --target subagents --file ...` | Applied (exit 0). |
| Update | `incidentFilters/sample-food-http-errors` | `handlingAgent: aca-app-incident-handler` | Applied (exit 0). |
| Delete | `agents/incident-handler` | direct data-plane `DELETE .../agents/incident-handler` | HTTP 2xx. |

### Live verification

`GET /api/v2/extendedAgent/incidentFilters/sample-food-http-errors` →
`properties.handlingAgent = aca-app-incident-handler` (`titleContains: food`, Sev1, `Autonomous`,
`isEnabled: true`). `GET /api/v2/extendedAgent/agents` lists `aca-app-incident-handler` and no longer
lists `incident-handler`. The full routing matrix is unchanged and disjoint (Sev1 food/afw; Sev2
nginx/not-nginx; Sev3 config). Gates: `validate --target subagents` / `--target incident-filters`
pass; `check-terraform-direct-values` ok; `fmt -check` / `validate` clean.

### Findings

| Finding | Detail |
| --- | --- |
| Rename is create-then-delete on the data plane | The data-plane subagent endpoint has no rename verb; the new name is PUT (create), the filter is repointed, then the old name is removed with a direct `DELETE .../agents/incident-handler`. The script `delete` iterates local manifests, which after the rename no longer contain `incident-handler`, so the old live object is deleted by direct REST. |
| Zero IaC/script change | `subagent_properties` and `incident_filter_properties` forward the manifest verbatim; only `metadata.name` and the filter `handlingAgent` changed. The Terraform comment referencing the handler was updated for accuracy (no resource change). |

## Convergence Audit — as-is vs desired state (2026-06-14)

Date: 2026-06-14.

Scope: audit the live agent (`contoso-sre-agent-dev`) and Terraform state against the local desired
state after the domain-routing and rename work. The data plane and the Terraform-owned agent body
converge; two desired-state coherence gaps were fixed; the only `plan` diff is pre-existing
non-SRE-Agent infrastructure drift.

### Converged (live == desired)

| Target | Desired | Live | Result |
| --- | --- | --- | --- |
| subagents | 9 | 9 | Match. |
| incidentFilters | 5 | 5 | Match (disjoint matrix). |
| scheduledtasks | 5 | 5 | Match. |
| connectors | 3 (+2 Terraform telemetry) | 3 + `application-insights` + `log-analytics` | Match. |
| repos | 1 (`grubify`) | 1 | Match. |
| skills | 10 | 10 | Match. |
| commonprompts | 0 | 0 | Match. |
| agent body (ARM) | Autonomous / High / claude-opus-4-6 / IMC AzMonitor | identical | Match. |

### Fixed gaps

| Op | Target | Change | Result |
| --- | --- | --- | --- |
| Delete (repo) | `hooks/block-unsafe-remediation.yaml` | Removed the redundant non-`example` hook manifest (`enabled:false`). The API ignores `spec.enabled` (`activationMode=always`), so a full `apply` would have deployed and **activated** the gate, breaking max autonomy. Live was already 0 hooks. `hooks/` now holds only `example-*`. | Done (`git rm`). |
| Apply | `knowledge-files` | Re-uploaded all 15 desired docs (4 `sample-food` + 11 `vnet-flow-logs`) | 15/15 uploaded (HTTP 2xx; idempotent, keyed by basename). |

### Terraform

`terraform plan` = 0 add, 8 change, 0 destroy. `azapi_resource.agent` body and the 3 alerts show **no
diff** (converged). The 8 changes are pre-existing non-SRE-Agent drift: 6 `azurerm_linux_virtual_machine`
(`bypass_platform_safety_checks_on_user_schedule_enabled` true→false, in-place) and 2 `azurerm_subnet`
(`default_outbound_access_enabled` false→true — security: live is secure-by-default, config would re-enable
default egress). Redeploy the agent with `-target=azapi_resource.agent`; do not full-`apply` until the
subnet drift is resolved (decision open).

### Findings

| Finding | Detail |
| --- | --- |
| `/connectors` is not an authoritative knowledge index | It surfaces only the 4 `sample-food` `KnowledgeFile` items and never the 11 `vnet-flow-logs` docs; `agentmemory/status` returns only flags (`enabled`, `documentRetrievalEnabled`, …), no list/count. The authoritative signal for knowledge convergence is the idempotent upload itself. |
| Hook disable = not deploy (not a flag) | Re-confirmed live: removing the non-`example` manifest is the correct way to keep 0 hooks; `spec.enabled` is ignored by the data plane. |
| No current-state doc edit needed | The audit confirmed the docs already assert “no hook deployed” and “15 knowledge docs”; the two fixes aligned the repo/live to the docs rather than the reverse. |
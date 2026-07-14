# Azure SRE Agent Configuration

This directory is the Git source of truth for Azure SRE Agent configuration that is not managed by Terraform.

The deployment script reads YAML files, optionally injects Markdown content through `spec.content_file`, converts the result to JSON, and calls the documented Azure SRE Agent APIs.

For the complete operational manual, including one-by-one deployment commands for every manifest in this directory, full desired-state deployment, verification, troubleshooting, and serious examples, see [SRE Agent Config Script Guide](../docs/azure-sre-agent/sre-agent-config-script-guide.md).

## Directory Map

| Directory | Purpose | API path |
| --- | --- | --- |
| `skills/` | Reusable skills and their instructions | Data plane `/api/v2/extendedAgent/skills/{name}` |
| `subagents/` | Specialized subagents | Data plane `/api/v2/extendedAgent/agents/{name}` |
| `tools/` | Tool definitions | Data plane `/api/v2/extendedAgent/tools/{name}` |
| `connectors/` | Data-plane connectors such as MCP or knowledge connectors | Data plane `/api/v2/extendedAgent/connectors/{name}` |
| `common-prompts/` | Shared prompts | Data plane `/api/v2/extendedAgent/commonprompts/{name}` |
| `automations/scheduled-tasks/` | Recurring work | Data plane `/api/v2/extendedAgent/scheduledtasks/{name}` |
| `automations/incident-filters/` | Incident routing filters | Data plane `/api/v2/extendedAgent/incidentFilters/{name}` |
| `automations/http-triggers/` | HTTP trigger definitions | Data plane `/api/v1/httptriggers/create` |
| `incident-platforms/` | Incident platform configuration (credential-bearing platforms only) | ARM agent PATCH for `incidentManagementConfiguration`. Note: the Azure Monitor platform is now owned by Terraform in the agent body; only `example-*` manifests remain here. |
| `repos/` | Code repository connections | Data plane `/api/v2/repos/{name}` |
| `hooks/` | Governance hooks | Data plane `/api/v2/extendedAgent/hooks/{name}` |
| `plugin-configs/` | Plugin configurations | Data plane `/api/v2/extendedAgent/plugins/{name}` |
| `plugins/marketplaces/` | Plugin marketplace documents | Data plane `/api/v2/plugins/marketplaces` |
| `plugins/installations/` | Plugin installation documents | Data plane `/api/v2/plugins/installations` |
| `knowledge/files/` | Files uploaded to agent memory | Data plane `/api/v1/agentmemory/upload` |

## Manifest Conventions

Every YAML manifest uses this shape:

```yaml
api_version: azuresre.ai/v1
kind: Skill
metadata:
  name: example
spec:
  description: Example description
```

Long instructions should live in Markdown and be referenced from YAML:

```yaml
spec:
  content_file: ./example.md
```

### Example manifests

Files whose names start with `example-` are **excluded from deployment** by every discovery path in `sre-agent-config.sh` (`validate`, `plan`, `apply`, `verify`, `delete`), for both full desired state and `--target` selections, and the same rule applies to `example-*` knowledge files. The repository ships two **enablement runbooks** — `connectors/example-outlook.yaml` and `connectors/example-teams.yaml` — that give the complete, certified portal-wizard setup for the Outlook and Teams notification connectors used by `cost-optimization-agent` report delivery. These connectors are OAuth-interactive (OAuth sign-in + managed identity + `Microsoft.Web/connections`) and **cannot** be created by a data-plane apply, so they stay `example-`-prefixed by necessity (not because they are incomplete) — the same one-time portal step the GitHub OAuth connector needs. The exclusion remains in effect for any other `example-*` files added later.

## Imported Demo Lab Agent Assets

The VNet Flow Logs and Sample Food demo lab imports Azure SRE Agent configuration from the external branch `feature/app-sample-food-container-app` and normalizes it into this repository's YAML-plus-Markdown desired-state format.

Skills (8 - the seven imported networking skills were consolidated into five on 2026-07-02 to
stay within the official five-active-skills cap; see
https://learn.microsoft.com/en-us/azure/sre-agent/skills):

- `cost-optimization` (evolved from the imported `cost-retention-optimization` into a
  subscription-wide FinOps skill - see [cost-optimization-agent.md](../docs/azure-sre-agent/cost-optimization-agent.md))
- `sample-food-container-app-incident-analysis`
- `rbac-and-resource-access-check`
- `vnet-flow-logs-and-ingestion` (merge of `vnet-flow-logs-troubleshooting` + `storage-flow-log-ingestion-check`)
- `connectivity-diagnostics` (merge of `network-watcher-diagnostics` + `private-endpoint-traffic-analysis`)
- `traffic-analytics-kql-analysis`
- `nsg-deny-flow-investigation`
- `udr-asymmetry-investigation`

Imported knowledge files:

- `knowledge/files/sample-food/github-issue-triage.md`
- `knowledge/files/sample-food/http-500-errors.md`
- `knowledge/files/sample-food/incident-report-template.md`
- `knowledge/files/sample-food/sample-food-architecture.md`

## Imported Sample Food / Grubify Operational Assets

The Sample Food / Grubify operational layer is imported from `dm-chelupati/sre-agent-lab`. The Grubify application now lives inside this repository (`microsoft/frontier-sre-agent-rvas`) under `Student/Resources/grubify/`, and the agent reads its source and opens fix pull requests there.

Subagents (autonomous, with Azure CLI write tools, faithful to the upstream lab):

- `aca-app-incident-handler` (imported as `incident-handler`, renamed 2026-06-14 to a domain-speaking name)
- `code-analyzer`
- `issue-triager`

GitHub and incident-response surfaces:

- `connectors/example-github-mcp.yaml` — **alternative GitHub path (disabled).** GitHub remote MCP server connector (`dataConnectorType: Mcp`, `type: http`, endpoint `https://api.githubcopilot.com/mcp/`, `authType: BearerToken`): inject a PAT via `${GITHUB_PAT}` at runtime. Non-interactive and scriptable. To enable instead of the OAuth connector: rename to `github-mcp.yaml`, set `GITHUB_PAT`, and add `mcp_tools: [github-mcp/*]` to the relevant subagents.
- `connectors/github.yaml` — **active GitHub OAuth connector** (`dataConnectorType: GitHubOAuth`). Requires a **one-time interactive OAuth authorization in the SRE Agent portal** after first apply before GitHub tools become available. No secrets to manage. Covers S1/S2/S3 (issues, PRs, code search).
- `repos/grubify.yaml` — Grubify source repository; `spec.authConnectorName` links it to the `github` OAuth connector.
- Azure Monitor incident platform — **owned by Terraform** in the agent body (`incidentManagementConfiguration = { type: AzMonitor, connectionName: azmonitor }`, migrated 2026-06-14); there is no data-plane manifest for it.
- `automations/incident-filters/` — three domain-routed response plans (domain-routing rule, 2026-06-14; each owns a failure domain keyed by incident title, disjoint by construction, and each wired to a real Azure Monitor alert in this lab): `sample-food-http-errors` (Sev1 `food` → `aca-app-incident-handler`, ACA app), `web-tier-nginx` (Sev2 `nginx` → `iaas-vm-incident-handler`, IaaS web tier), `network-observability-review` (Sev2 not `nginx` → `network-traffic-analyst`, hub networking). All Autonomous. The former dormant `hub-firewall-network` (Sev1 `afw`) and `config-audit-review` (Sev3) plans were removed 2026-07-02 because no Azure Monitor alert fires them in this lab.
- `automations/scheduled-tasks/triage-grubify-issues.yaml` — triages Grubify customer issues every 12 hours via the `issue-triager` subagent.

## Domain-routing re-architecting (2026-06-14)

Incident response plans were re-architected from severity-only bands to a **domain-routing rule**: each plan owns one failure domain, keyed by incident title (`titleContains` / `titleNotContains`, case-insensitive) on top of severity, so every alert reaches the specialist scoped to that domain. The plans are disjoint by construction at every severity (see the `automations/incident-filters/` bullet above). This added:

- `subagents/iaas-vm-incident-handler.yaml` — new Autonomous IaaS web-tier handler (Syslog-based diagnosis + autonomous in-guest `az vm run-command` restart) that owns the NGINX-down / VM service-health domain, previously mis-routed to `network-traffic-analyst`.
- `automations/incident-filters/web-tier-nginx.yaml` — the new Sev2 web-tier domain plan; `network-traffic-analyst` keeps the hub networking domain (NSG/UDR/VNet-flow) via `network-observability-review`.

> **Pruned 2026-07-02.** The originally-added `hub-firewall-network` (Sev1 `afw`) and the severity-only `config-audit-review` (Sev3) plans were removed as dormant: this lab has no `afw`-titled or Sev3 Azure Monitor alert, so neither ever fired. Official guidance is to keep only response plans wired to real incidents (https://learn.microsoft.com/en-us/azure/sre-agent/incident-response-plans).

All incident-handling plans and subagents run Autonomous (maximum-autonomy posture); for the production-posture exception see [ADR 0001](../docs/azure-sre-agent/adr/0001-sre-agent-iac-boundaries.md).

## Secrets

Do not commit secrets. For local testing, use `.env` and `${VARIABLE_NAME}` placeholders. The script substitutes placeholders at runtime when `envsubst` is installed.

Enterprise deployments should use CI/CD secrets or Key Vault-backed injection.

## Commands

The script requires `jq` and either Python 3 with PyYAML or a compatible `yq`. Python/PyYAML is preferred because `yq` implementations differ across platforms.

Run commands from the repository root. The script resolves this directory through `.sre-agent-layout.env` by default.

```bash
./Infra/scripts/sre-agent-config.sh validate
./Infra/scripts/sre-agent-config.sh plan --subscription <sub> --resource-group <rg> --agent <agent>
./Infra/scripts/sre-agent-config.sh apply --subscription <sub> --resource-group <rg> --agent <agent>
./Infra/scripts/sre-agent-config.sh verify --subscription <sub> --resource-group <rg> --agent <agent>
```

By default, `plan` and `apply` process the full desired state under this directory. Use selective deployment when validating one surface or one manifest at a time.

Full desired-state deployment:

```bash
./Infra/scripts/sre-agent-config.sh validate
./Infra/scripts/sre-agent-config.sh plan --subscription <sub> --resource-group <rg> --agent <agent>
./Infra/scripts/sre-agent-config.sh apply --subscription <sub> --resource-group <rg> --agent <agent>
./Infra/scripts/sre-agent-config.sh verify --subscription <sub> --resource-group <rg> --agent <agent>
```

The `connectors/example-github-mcp.yaml` connector (MCP/PAT alternative) is disabled. The active GitHub connector is `connectors/github.yaml` (OAuth). After the first apply, complete the **one-time OAuth authorization** in the SRE Agent portal (Connectors → github → Authorize) before GitHub tools become available to subagents. The Outlook and Teams notification connectors are portal-provisioned (`example-*`, excluded from apply) and need no repo secret.

## Selective Deployment

Use `--target` to deploy one configuration surface, `--name` to deploy one manifest inside that surface, and `--file` to deploy one manifest by path.

Examples:

```bash
./Infra/scripts/sre-agent-config.sh validate --target skills --name sre-diagnostics-baseline

./Infra/scripts/sre-agent-config.sh plan \
  --target skills \
  --name sre-diagnostics-baseline \
  --subscription <sub> \
  --resource-group <rg> \
  --agent <agent>

./Infra/scripts/sre-agent-config.sh apply \
  --target skills \
  --name sre-diagnostics-baseline \
  --subscription <sub> \
  --resource-group <rg> \
  --agent <agent>

./Infra/scripts/sre-agent-config.sh verify \
  --target skills \
  --name sre-diagnostics-baseline \
  --subscription <sub> \
  --resource-group <rg> \
  --agent <agent>
```

Equivalent file-based example:

```bash
./Infra/scripts/sre-agent-config.sh plan \
  --file AZ-SRE-Agent-Configuration/skills/traffic-analytics-kql-analysis.yaml \
  --subscription <sub> \
  --resource-group <rg> \
  --agent <agent>
```

Important shell note: multi-line commands require a trailing `\` on every continued line. Without it, shells such as `zsh` run `--config`, `--subscription`, or `--target` as separate commands.

## Supported Targets

| Target | Directory | Operation type |
| --- | --- | --- |
| `skills` | `skills/` | Data-plane extendedAgent PUT |
| `subagents` | `subagents/` | Data-plane extendedAgent PUT |
| `tools` | `tools/` | Data-plane extendedAgent PUT |
| `common-prompts` | `common-prompts/` | Data-plane extendedAgent PUT |
| `scheduled-tasks` | `automations/scheduled-tasks/` | Data-plane extendedAgent PUT |
| `incident-filters` | `automations/incident-filters/` | Data-plane extendedAgent PUT |
| `incident-platforms` | `incident-platforms/` | ARM agent PATCH |
| `connectors` | `connectors/` | Data-plane PUT |
| `repos` | `repos/` | Data-plane PUT |
| `hooks` | `hooks/` | Data-plane PUT |
| `plugin-configs` | `plugin-configs/` | Data-plane PUT |
| `http-triggers` | `automations/http-triggers/` | Data-plane POST |
| `plugin-marketplaces` | `plugins/marketplaces/` | Data-plane POST |
| `plugin-installations` | `plugins/installations/` | Data-plane POST |
| `knowledge-files` | `knowledge/files/` | Data-plane file upload |

`delete` supports selected targets where the service exposes a stable delete or clear operation. Some POST-only surfaces, such as plugin marketplace/installations, remain create/read/update-only in this script because no stable per-object delete route is documented here.

## YAML to JSON Conversion

For plain conversion, `yq` is enough:

```bash
yq -o=json '.' AZ-SRE-Agent-Configuration/skills/traffic-analytics-kql-analysis.yaml
```

The deployment script does more than plain conversion: it renders environment placeholders, loads Markdown referenced by `spec.content_file`, writes it into `spec.content`, removes `spec.content_file`, and translates each manifest into the data-plane or ARM shape required by its target.

For `skills`, the script maps local `spec.content` into the service property `skillContent`, following the official SRE Agent template behavior.

## Current Validation Result

Selective local validation and planning were verified with:

```bash
./Infra/scripts/sre-agent-config.sh validate --target skills --name traffic-analytics-kql-analysis
./Infra/scripts/sre-agent-config.sh plan --target skills --name traffic-analytics-kql-analysis --subscription <sub> --resource-group <rg> --agent <agent>
./Infra/scripts/sre-agent-config.sh plan --file AZ-SRE-Agent-Configuration/skills/traffic-analytics-kql-analysis.yaml --subscription <sub> --resource-group <rg> --agent <agent>
```

Expected selective plan output:

```text
PUT data-plane /api/v2/extendedAgent/skills/traffic-analytics-kql-analysis from .../AZ-SRE-Agent-Configuration/skills/traffic-analytics-kql-analysis.yaml
```

Live apply and verify for `skills/traffic-analytics-kql-analysis` succeed through the data-plane route:

```text
Applied data-plane /api/v2/extendedAgent/skills/traffic-analytics-kql-analysis
```

Do not use ARM child endpoints such as `/skills/{name}` for Agent Extensions in external tenants. Those endpoints currently return:

```text
Agent Extensions are not available for this tenant. This feature is restricted to internal tenants only.
```

The Microsoft SRE Agent templates use data-plane `extendedAgent` routes for these surfaces to avoid that tenant restriction.
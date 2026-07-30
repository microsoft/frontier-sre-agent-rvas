# Azure SRE Agent Configuration Script Guide

This guide explains how to use `infra/scripts/sre-agent-config.sh` to validate, plan, apply, verify, and manage Azure SRE Agent configuration stored under `azure-sre-agent-config/`.

The script is the deployment entry point for Azure SRE Agent configuration that is not managed directly by Terraform. It reads YAML manifests, injects Markdown content referenced by `spec.content_file`, converts manifests into the correct API request shape, and calls either Azure Resource Manager or the Azure SRE Agent data-plane API.

## Scope

Use this guide for:

- Deploying one configuration instance at a time.
- Deploying all desired configuration together.
- Validating a manifest before applying it.
- Verifying live Azure SRE Agent configuration after deployment.
- Understanding which targets use ARM and which use the data plane.

This guide does not cover Terraform-managed infrastructure. Terraform owns the resource group, managed identity, Log Analytics workspace, Application Insights, the SRE Agent root resource, ARM-supported connectors, and RBAC assignments.

## Prerequisites

Run commands from the repository root:

```bash
cd /home/lpassaretta/platform/projects/azure-sre-agent
```

Required local tools:

```bash
command -v az
command -v curl
command -v jq
command -v yq || python3 -c 'import yaml, json'
```

Required Azure access:

- You must be signed in with `az login`.
- Your identity must have permission to read the SRE Agent root resource.
- For data-plane configuration, your identity must be able to get a token for `https://azuresre.dev`.
- For ARM PATCH operations such as incident platform configuration, your identity needs sufficient control-plane permissions on the agent.

Set the common shell variables once:

```bash
export SUB="<Your Subscription ID>"
export RG="rg-sec-sreagent"
export AGENT="contoso-sre-agent-dev"
```

Optional endpoint override:

```bash
export ENDPOINT="https://<Your Instance Name>.<region>.azuresre.ai"
```

If `--endpoint` is not passed, the script reads the endpoint from ARM.

## Command Model

General syntax:

```bash
./infra/scripts/sre-agent-config.sh <command> [options]
```

Commands:

| Command | Purpose | Writes to Azure |
| --- | --- | --- |
| `validate` | Validate local YAML and referenced Markdown files. | No |
| `plan` | Show the API operations that would run. | No |
| `apply` | Apply local configuration to the live agent. Full desired-state apply is best-effort and reports failed resources at the end; selective apply remains fail-fast. | Yes |
| `verify` | Query the live agent for configured surfaces. | No |
| `delete` | Delete full desired-state resources from live agent. Requires `--yes`. | Yes |
| `prune` | Reserved and intentionally blocked. | No |

Selection options:

| Option | Purpose | Example |
| --- | --- | --- |
| `--target` | Select a configuration surface. | `--target skills` |
| `--name` | Select a manifest by logical name. Requires `--target` or `--file`. | `--name sre-diagnostics-baseline` |
| `--file` | Select a single manifest or knowledge file by path. The script infers the target when possible. | `--file azure-sre-agent-config/skills/traffic-analytics-kql-analysis.yaml` |

Azure options:

| Option | Purpose |
| --- | --- |
| `--subscription` | Azure subscription ID. |
| `--resource-group` | Resource group that contains the SRE Agent. |
| `--agent` | SRE Agent resource name. |
| `--endpoint` | Optional data-plane endpoint override. |
| `--config` | Optional config root. Overrides `.sre-agent-layout.env`, `SRE_AGENT_CONFIG_DIR`, and auto-discovery. |
| `--env-file` | Optional `.env` file for placeholder substitution. |

## Layout Resolution

The script does not hardcode a legacy `configuration/` folder. It resolves the configuration root in this order:

1. `--config <path>`.
2. `SRE_AGENT_CONFIG_DIR` environment variable.
3. `SRE_AGENT_CONFIG_DIR` inside the root `.sre-agent-layout.env` contract file.
4. Controlled fallback discovery for `azure-sre-agent-config/` and legacy `configuration/`.

Explicit inputs are authoritative: if `--config`, `SRE_AGENT_CONFIG_DIR`, or `.sre-agent-layout.env` points to a missing or invalid directory, the script fails instead of silently using another folder.

## Target Reference

| Target | Source directory | API route used by script |
| --- | --- | --- |
| `skills` | `azure-sre-agent-config/skills/` | `PUT /api/v2/extendedAgent/skills/{name}` |
| `subagents` | `azure-sre-agent-config/subagents/` | `PUT /api/v2/extendedAgent/agents/{name}` |
| `tools` | `azure-sre-agent-config/tools/` | Known preview-blocked in this tenant; script skips manifests marked `spec.deployment.status: api-preview-blocked` |
| `common-prompts` | `azure-sre-agent-config/common-prompts/` | `PUT /api/v2/extendedAgent/commonprompts/{name}` |
| `scheduled-tasks` | `azure-sre-agent-config/automations/scheduled-tasks/` | `PUT /api/v2/extendedAgent/scheduledtasks/{name}` |
| `incident-filters` | `azure-sre-agent-config/automations/incident-filters/` | `PUT /api/v2/extendedAgent/incidentFilters/{name}` |
| `incident-platforms` | `azure-sre-agent-config/incident-platforms/` | ARM PATCH on `properties.incidentManagementConfiguration` |
| `connectors` | `azure-sre-agent-config/connectors/` | `PUT /api/v2/extendedAgent/connectors/{name}` |
| `repos` | `azure-sre-agent-config/repos/` | `PUT /api/v2/repos/{name}` |
| `hooks` | `azure-sre-agent-config/hooks/` | `PUT /api/v2/extendedAgent/hooks/{name}` |
| `plugin-configs` | `azure-sre-agent-config/plugin-configs/` | `PUT /api/v2/extendedAgent/plugins/{name}` |
| `http-triggers` | `azure-sre-agent-config/automations/http-triggers/` | `POST /api/v1/httptriggers/create` |
| `plugin-marketplaces` | `azure-sre-agent-config/plugins/marketplaces/` | `POST /api/v2/plugins/marketplaces` |
| `plugin-installations` | `azure-sre-agent-config/plugins/installations/` | `POST /api/v2/plugins/installations` |
| `knowledge-files` | `azure-sre-agent-config/knowledge/files/` | `POST /api/v1/agentmemory/upload` |

Do not use ARM child endpoints such as `/skills/{name}` operationally for Agent Extensions in external tenants. Live validation showed they return:

```text
Agent Extensions are not available for this tenant. This feature is restricted to internal tenants only.
```

The script therefore uses data-plane `extendedAgent` routes for skills, subagents, common prompts, scheduled tasks, and incident filters. Live CRUD validation on 2026-06-11 showed that the current public preview rejects custom tool object types (`InvalidObjectType`). This repository therefore ships **no custom tools** (`tools/` is empty); subagents use built-in tools only (Azure CLI, Log Analytics / Application Insights queries, memory, Python). Custom tools remain unusable until Microsoft publishes or enables an accepted tool schema.

## Example Manifests Are Excluded From Deployment

Files whose names start with `example-` are kept in Git as reference material but are skipped by every discovery path (`validate`, `plan`, `apply`, `verify`, `delete`), for both full desired state and `--target` selections. The same rule applies to `example-*` knowledge files. This repository currently ships two such files - `connectors/example-outlook.yaml` and `connectors/example-teams.yaml` - the enablement runbooks for the portal-provisioned Outlook and Teams notification connectors (they cannot be created by a data-plane apply, so they stay `example-`-prefixed by necessity). This keeps them reviewable in source control while guaranteeing they are never pushed to the cloud agent. To deploy an `example-` manifest explicitly for testing, pass it with `--file`, which bypasses name-based discovery.

## Full Desired-State Deployment

Use full deployment only after reviewing every file under `azure-sre-agent-config/`, especially manifests that contain placeholders or secrets.

Dry run:

```bash
./infra/scripts/sre-agent-config.sh validate

./infra/scripts/sre-agent-config.sh plan \
  --subscription "$SUB" \
  --resource-group "$RG" \
  --agent "$AGENT"
```

Apply all desired configuration:

```bash
./infra/scripts/sre-agent-config.sh apply \
  --subscription "$SUB" \
  --resource-group "$RG" \
  --agent "$AGENT"
```

Full desired-state `apply` is best-effort. The script attempts every supported resource and sub-resource in the configured folders. If one manifest fails, for example because a placeholder secret is not set, the script logs that resource as failed and continues with the remaining resources. At the end it prints a failure summary and exits with a non-zero status when one or more resources failed.

Example failure summary:

```text
ERROR: Full desired-state apply completed with 2 failure(s):
  - connectors: .../azure-sre-agent-config/connectors/<name>.yaml (exit 1)
  - incident-platforms: .../azure-sre-agent-config/incident-platforms/<name>.yaml (exit 1)
```

Selective `apply` with `--target`, `--name`, or `--file` remains fail-fast. Use selective apply when you want one manifest to succeed or fail as a single controlled operation.

Verify all configured surfaces:

```bash
./infra/scripts/sre-agent-config.sh verify \
  --subscription "$SUB" \
  --resource-group "$RG" \
  --agent "$AGENT"
```

Important full-deploy caveats:

- Manifests whose names start with `example-` are excluded from full `apply`. (This repository ships two `example-*` enablement runbooks - `connectors/example-outlook.yaml` and `connectors/example-teams.yaml`; the exclusion remains in effect for any others added later.)
- The agent supports one active incident platform configuration at a time. The AzMonitor incident platform is **owned by Terraform** (in the agent body), not the data-plane script; if another platform is applied later via `--file`, the last PATCH wins.
- Do not run full `apply` until required secrets are injected safely.

## Deploying Individual Surfaces Without Secrets

Every current data-plane surface (skills, subagents, incident filters, scheduled tasks, the
`microsoft-learn-mcp` connector, and the `grubify` repo) deploys with no secret placeholder. Only
`connectors/github-mcp.yaml` needs `${GITHUB_PAT}` at apply time, and the Outlook/Teams notification
connectors are portal-provisioned (never applied by this script). Deploy any single surface with a
targeted apply, for example:

```bash
./infra/scripts/sre-agent-config.sh apply --target skills --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
./infra/scripts/sre-agent-config.sh apply --target subagents --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
./infra/scripts/sre-agent-config.sh apply --target incident-filters --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
```

## One-By-One Deployment Commands

Each section below includes `plan`, `apply`, and `verify`. Use `plan` before `apply` when testing a new or changed manifest.

## CRUD Examples by Resource

In this script, `apply` is an upsert operation for targets backed by `PUT`: it creates the resource when it does not exist and updates it when it already exists. For POST-only targets, update semantics depend on the service API and are called out explicitly.

All delete examples require `--yes`. Blocks named after a **real manifest** (for example `traffic-analytics-kql-analysis`, `network-traffic-analyst`, `grubify`) are copy-paste accurate; the Delete step is destructive, but every object is recoverable with `apply` from Git. Blocks with an `example-`/`my-` name, or for a target whose directory is empty in this repo (custom tools, common prompts, hooks, plugin configs/marketplaces/installations, HTTP triggers, data-plane incident platforms), are **illustrative patterns** - substitute your own manifest.

### Skill CRUD: `traffic-analytics-kql-analysis`

Create:

```bash
./infra/scripts/sre-agent-config.sh apply --file azure-sre-agent-config/skills/traffic-analytics-kql-analysis.yaml --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
```

Read:

```bash
./infra/scripts/sre-agent-config.sh verify --target skills --name traffic-analytics-kql-analysis --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
```

Update:

```bash
./infra/scripts/sre-agent-config.sh apply --target skills --name traffic-analytics-kql-analysis --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
```

Delete:

```bash
./infra/scripts/sre-agent-config.sh delete --target skills --name traffic-analytics-kql-analysis --subscription "$SUB" --resource-group "$RG" --agent "$AGENT" --yes
```

### Subagent CRUD: `network-traffic-analyst`

Create:

```bash
./infra/scripts/sre-agent-config.sh apply --file azure-sre-agent-config/subagents/network-traffic-analyst.yaml --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
```

Read:

```bash
./infra/scripts/sre-agent-config.sh verify --target subagents --name network-traffic-analyst --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
```

Update:

```bash
./infra/scripts/sre-agent-config.sh apply --target subagents --name network-traffic-analyst --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
```

Delete:

```bash
./infra/scripts/sre-agent-config.sh delete --target subagents --name network-traffic-analyst --subscription "$SUB" --resource-group "$RG" --agent "$AGENT" --yes
```

### Tool CRUD (illustrative - this repo ships no custom tools)

Custom tool object types are rejected in external tenants (`InvalidObjectType`; see above), so `tools/` is empty and subagents use built-in tools only. The commands below show the pattern for a hypothetical `my-tool` once Microsoft enables an accepted tool schema:

```bash
./infra/scripts/sre-agent-config.sh apply  --file azure-sre-agent-config/tools/my-tool.yaml --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
./infra/scripts/sre-agent-config.sh verify --target tools --name my-tool --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
./infra/scripts/sre-agent-config.sh apply  --target tools --name my-tool --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
./infra/scripts/sre-agent-config.sh delete --target tools --name my-tool --subscription "$SUB" --resource-group "$RG" --agent "$AGENT" --yes
```

### Common Prompt CRUD (illustrative - this repo ships no common prompts)

The `common-prompts/` directory is empty in this repository. The commands below show the pattern for a hypothetical `my-prompt`:

```bash
./infra/scripts/sre-agent-config.sh apply  --file azure-sre-agent-config/common-prompts/my-prompt.yaml --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
./infra/scripts/sre-agent-config.sh verify --target common-prompts --name my-prompt --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
./infra/scripts/sre-agent-config.sh apply  --target common-prompts --name my-prompt --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
./infra/scripts/sre-agent-config.sh delete --target common-prompts --name my-prompt --subscription "$SUB" --resource-group "$RG" --agent "$AGENT" --yes
```

### Scheduled Task CRUD: `flow-log-ingestion-freshness`

Create:

```bash
./infra/scripts/sre-agent-config.sh apply --file azure-sre-agent-config/automations/scheduled-tasks/flow-log-ingestion-freshness.yaml --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
```

Read:

```bash
./infra/scripts/sre-agent-config.sh verify --target scheduled-tasks --name flow-log-ingestion-freshness --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
```

Update:

```bash
./infra/scripts/sre-agent-config.sh apply --target scheduled-tasks --name flow-log-ingestion-freshness --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
```

Delete:

```bash
./infra/scripts/sre-agent-config.sh delete --target scheduled-tasks --name flow-log-ingestion-freshness --subscription "$SUB" --resource-group "$RG" --agent "$AGENT" --yes
```

### Incident Filter CRUD: `network-observability-review`

Prerequisite: the agent incident platform must already be `AzMonitor`. If the platform is `None`, the service rejects the filter with `Incident platform 'AzMonitor' does not match configured incident management type 'None'`. In this repo AzMonitor is Terraform-owned and already active, so filters apply directly; if you ever reset the platform, let the Terraform-managed platform reconcile before applying filters.

Create:

```bash
./infra/scripts/sre-agent-config.sh apply --file azure-sre-agent-config/automations/incident-filters/network-observability-review.yaml --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
```

Read:

```bash
./infra/scripts/sre-agent-config.sh verify --target incident-filters --name network-observability-review --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
```

Update:

```bash
./infra/scripts/sre-agent-config.sh apply --target incident-filters --name network-observability-review --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
```

Delete:

```bash
./infra/scripts/sre-agent-config.sh delete --target incident-filters --name network-observability-review --subscription "$SUB" --resource-group "$RG" --agent "$AGENT" --yes
```

### Incident Platform CRUD: `azure-monitor` (Terraform-owned in this repo)

In this repository the Azure Monitor incident platform is **owned by Terraform** in the agent body (`incidentManagementConfiguration = { type: AzMonitor, connectionName: azmonitor }`), so `incident-platforms/` ships no manifest and you do **not** apply it with this script. The commands below document the data-plane path for reference only. Operational note: incident platform PATCH is asynchronous; repeating create/update immediately can return `OperationConflict` with `CreateOrUpdate`, so read the platform state before applying dependent incident filters.

Read:

```bash
./infra/scripts/sre-agent-config.sh verify --target incident-platforms --name azure-monitor --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
```

Delete (would clear the platform to `type: None`; in this repo that causes drift because Terraform re-applies AzMonitor - change platform state in Terraform instead):

```bash
./infra/scripts/sre-agent-config.sh delete --target incident-platforms --name azure-monitor --subscription "$SUB" --resource-group "$RG" --agent "$AGENT" --yes
```

### Incident Platform CRUD: `pagerduty` (illustrative - not used in this lab)

This lab uses Azure Monitor (Terraform-owned). PagerDuty is a supported credential-bearing platform; to use it instead, add a manifest under `incident-platforms/` (with a real `connectionKey`) and apply it - only **one** incident platform is active at a time, so switching to PagerDuty disconnects AzMonitor. The commands below show the pattern:

```bash
# Create from your manifest (inject a real connectionKey first)
./infra/scripts/sre-agent-config.sh apply  --file azure-sre-agent-config/incident-platforms/pagerduty.yaml --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
./infra/scripts/sre-agent-config.sh verify --target incident-platforms --name pagerduty --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
./infra/scripts/sre-agent-config.sh delete --target incident-platforms --name pagerduty --subscription "$SUB" --resource-group "$RG" --agent "$AGENT" --yes
```

### Connector CRUD: `microsoft-learn-mcp`

The `microsoft-learn-mcp` connector needs no secret (public no-auth MCP server). The GitHub connectors need `${GITHUB_PAT}`; the Outlook/Teams notification connectors are portal-provisioned and are not applied by this script.

Create:

```bash
./infra/scripts/sre-agent-config.sh apply --file azure-sre-agent-config/connectors/microsoft-learn-mcp.yaml --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
```

Read:

```bash
./infra/scripts/sre-agent-config.sh verify --target connectors --name microsoft-learn-mcp --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
```

Update:

```bash
./infra/scripts/sre-agent-config.sh apply --target connectors --name microsoft-learn-mcp --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
```

Delete:

```bash
./infra/scripts/sre-agent-config.sh delete --target connectors --name microsoft-learn-mcp --subscription "$SUB" --resource-group "$RG" --agent "$AGENT" --yes
```

### Repository CRUD: `grubify`

Create:

```bash
./infra/scripts/sre-agent-config.sh apply --file azure-sre-agent-config/repos/grubify.yaml --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
```

Read:

```bash
./infra/scripts/sre-agent-config.sh verify --target repos --name grubify --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
```

Update:

```bash
./infra/scripts/sre-agent-config.sh apply --target repos --name grubify --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
```

Delete:

```bash
./infra/scripts/sre-agent-config.sh delete --target repos --name grubify --subscription "$SUB" --resource-group "$RG" --agent "$AGENT" --yes
```

### Hook CRUD (illustrative - this repo runs no hooks)

Hooks are removed in this lab for maximum autonomy (see ADR 0001); `hooks/` is empty. Pattern for a hypothetical `my-hook`:

```bash
./infra/scripts/sre-agent-config.sh apply  --file azure-sre-agent-config/hooks/my-hook.yaml --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
./infra/scripts/sre-agent-config.sh verify --target hooks --name my-hook --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
./infra/scripts/sre-agent-config.sh apply  --target hooks --name my-hook --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
./infra/scripts/sre-agent-config.sh delete --target hooks --name my-hook --subscription "$SUB" --resource-group "$RG" --agent "$AGENT" --yes
```

### Plugin Config CRUD (illustrative - this repo ships no plugin configs)

The `plugin-configs/` directory is empty. Pattern for a hypothetical `my-plugin-config`:

```bash
./infra/scripts/sre-agent-config.sh apply  --file azure-sre-agent-config/plugin-configs/my-plugin-config.yaml --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
./infra/scripts/sre-agent-config.sh verify --target plugin-configs --name my-plugin-config --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
./infra/scripts/sre-agent-config.sh apply  --target plugin-configs --name my-plugin-config --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
./infra/scripts/sre-agent-config.sh delete --target plugin-configs --name my-plugin-config --subscription "$SUB" --resource-group "$RG" --agent "$AGENT" --yes
```

### HTTP Trigger CRUD (illustrative - this repo ships no HTTP triggers)

The `automations/http-triggers/` directory is empty. HTTP trigger apply is idempotent (if a trigger with the same `name` exists, the create is skipped and the existing trigger reused, avoiding duplicate webhook URLs). Pattern for a hypothetical `my-trigger`:

```bash
./infra/scripts/sre-agent-config.sh apply  --file azure-sre-agent-config/automations/http-triggers/my-trigger.yaml --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
./infra/scripts/sre-agent-config.sh verify --target http-triggers --name my-trigger --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
./infra/scripts/sre-agent-config.sh apply  --target http-triggers --name my-trigger --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
```

Delete is not implemented by this script because no stable DELETE route is documented here for HTTP triggers.

### Plugin Marketplace CRUD (illustrative - this repo ships no marketplaces)

The `plugins/marketplaces/` directory is empty. Pattern for a hypothetical `my-marketplace`:

```bash
./infra/scripts/sre-agent-config.sh apply  --file azure-sre-agent-config/plugins/marketplaces/my-marketplace.yaml --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
./infra/scripts/sre-agent-config.sh verify --target plugin-marketplaces --name my-marketplace --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
./infra/scripts/sre-agent-config.sh apply  --target plugin-marketplaces --name my-marketplace --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
```

Delete is not implemented by this script because the marketplace POST surface does not have a stable DELETE route documented here.

### Plugin Installation CRUD (illustrative - this repo ships no installations)

The `plugins/installations/` directory is empty. Pattern for a hypothetical `my-installation`:

```bash
./infra/scripts/sre-agent-config.sh apply  --file azure-sre-agent-config/plugins/installations/my-installation.yaml --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
./infra/scripts/sre-agent-config.sh verify --target plugin-installations --name my-installation --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
./infra/scripts/sre-agent-config.sh apply  --target plugin-installations --name my-installation --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
```

Delete is not implemented by this script because the installation POST surface does not have a stable DELETE route documented here.

### Knowledge File CRUD: `http-500-errors.md`

Create:

```bash
./infra/scripts/sre-agent-config.sh apply --file azure-sre-agent-config/knowledge/files/sample-food/http-500-errors.md --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
```

Read:

```bash
./infra/scripts/sre-agent-config.sh verify --target knowledge-files --name http-500-errors --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
```

Update:

Update by re-uploading the same file name.

```bash
./infra/scripts/sre-agent-config.sh apply --file azure-sre-agent-config/knowledge/files/sample-food/http-500-errors.md --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
```

Delete:

```bash
./infra/scripts/sre-agent-config.sh delete --target knowledge-files --name http-500-errors --subscription "$SUB" --resource-group "$RG" --agent "$AGENT" --yes
```

Use `--name http-500-errors.md` if the API requires the full filename in your environment.

> **Legacy illustrative walkthroughs (superseded 2026-07-03).** The per-manifest walkthroughs
> below reference `example-*` manifests that were removed from this repository. They remain only as
> command-shape references. For copy-paste-accurate commands that use this repository's **real**
> manifests, use the "CRUD Examples by Resource" section above.

### Skill: `sre-diagnostics-baseline`

Source:

```text
azure-sre-agent-config/skills/example-diagnostics-skill.yaml
azure-sre-agent-config/skills/example-diagnostics-skill.md
```

Commands:

```bash
./infra/scripts/sre-agent-config.sh plan --file azure-sre-agent-config/skills/example-diagnostics-skill.yaml --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
./infra/scripts/sre-agent-config.sh apply --file azure-sre-agent-config/skills/example-diagnostics-skill.yaml --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
./infra/scripts/sre-agent-config.sh verify --target skills --name sre-diagnostics-baseline --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
```

Expected verify signal:

```text
sre-diagnostics-baseline
Skill
```

### Subagent: `observability-investigator`

Source:

```text
azure-sre-agent-config/subagents/example-observability-subagent.yaml
```

Commands:

```bash
./infra/scripts/sre-agent-config.sh plan --file azure-sre-agent-config/subagents/example-observability-subagent.yaml --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
./infra/scripts/sre-agent-config.sh apply --file azure-sre-agent-config/subagents/example-observability-subagent.yaml --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
./infra/scripts/sre-agent-config.sh verify --target subagents --name observability-investigator --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
```

### Tool: `azure-resource-graph-readonly`

Source:

```text
azure-sre-agent-config/tools/example-arg-tool.yaml
```

Commands:

```bash
./infra/scripts/sre-agent-config.sh plan --file azure-sre-agent-config/tools/example-arg-tool.yaml --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
./infra/scripts/sre-agent-config.sh apply --file azure-sre-agent-config/tools/example-arg-tool.yaml --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
./infra/scripts/sre-agent-config.sh verify --target tools --name azure-resource-graph-readonly --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
```

### Common Prompt: `incident-summary-executive`

Source:

```text
azure-sre-agent-config/common-prompts/example-incident-summary.yaml
azure-sre-agent-config/common-prompts/example-incident-summary.md
```

Commands:

```bash
./infra/scripts/sre-agent-config.sh plan --file azure-sre-agent-config/common-prompts/example-incident-summary.yaml --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
./infra/scripts/sre-agent-config.sh apply --file azure-sre-agent-config/common-prompts/example-incident-summary.yaml --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
./infra/scripts/sre-agent-config.sh verify --target common-prompts --name incident-summary-executive --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
```

### Scheduled Task: `daily-health-check`

Source:

```text
azure-sre-agent-config/automations/scheduled-tasks/example-daily-health.yaml
```

Commands:

```bash
./infra/scripts/sre-agent-config.sh plan --file azure-sre-agent-config/automations/scheduled-tasks/example-daily-health.yaml --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
./infra/scripts/sre-agent-config.sh apply --file azure-sre-agent-config/automations/scheduled-tasks/example-daily-health.yaml --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
./infra/scripts/sre-agent-config.sh verify --target scheduled-tasks --name daily-health-check --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
```

The example task is disabled in YAML. Keep it disabled until the prompt and cost profile are reviewed.

### Incident Filter: `sev2-production-only`

Source:

```text
azure-sre-agent-config/automations/incident-filters/example-sev2-filter.yaml
```

Commands:

```bash
./infra/scripts/sre-agent-config.sh plan --file azure-sre-agent-config/automations/incident-filters/example-sev2-filter.yaml --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
./infra/scripts/sre-agent-config.sh apply --file azure-sre-agent-config/automations/incident-filters/example-sev2-filter.yaml --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
./infra/scripts/sre-agent-config.sh verify --target incident-filters --name sev2-production-only --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
```

The example filter is disabled in YAML. Enable it only after validating incident routing behavior.

### Incident Platform: `azure-monitor`

Source:

```text
azure-sre-agent-config/incident-platforms/example-azure-monitor.yaml
```

Commands:

```bash
./infra/scripts/sre-agent-config.sh plan --file azure-sre-agent-config/incident-platforms/example-azure-monitor.yaml --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
./infra/scripts/sre-agent-config.sh apply --file azure-sre-agent-config/incident-platforms/example-azure-monitor.yaml --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
./infra/scripts/sre-agent-config.sh verify --target incident-platforms --name azure-monitor --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
```

This PATCH changes the root agent `incidentManagementConfiguration`. Only one incident platform configuration is active at a time.

### Incident Platform: `pagerduty`

Source:

```text
azure-sre-agent-config/incident-platforms/example-pagerduty.yaml
```

The file contains a secret placeholder:

```text
connectionKey: ${PAGERDUTY_CONNECTION_KEY}
```

Do not apply this manifest as-is. Inject a real secret through a secure process first.

Commands after secret injection:

```bash
./infra/scripts/sre-agent-config.sh plan --file azure-sre-agent-config/incident-platforms/example-pagerduty.yaml --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
./infra/scripts/sre-agent-config.sh apply --file azure-sre-agent-config/incident-platforms/example-pagerduty.yaml --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
./infra/scripts/sre-agent-config.sh verify --target incident-platforms --name pagerduty --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
```

Applying this after `azure-monitor` replaces the active incident platform configuration.

### Connector: `dynatrace-mcp`

Source:

```text
azure-sre-agent-config/connectors/example-dynatrace-mcp.yaml
```

The file contains a secret placeholder:

```text
bearerToken: ${DYNATRACE_MCP_BEARER_TOKEN}
```

Do not apply this manifest as-is. Inject a real token through a secure process first.

Commands after secret injection:

```bash
./infra/scripts/sre-agent-config.sh plan --file azure-sre-agent-config/connectors/example-dynatrace-mcp.yaml --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
./infra/scripts/sre-agent-config.sh apply --file azure-sre-agent-config/connectors/example-dynatrace-mcp.yaml --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
./infra/scripts/sre-agent-config.sh verify --target connectors --name dynatrace-mcp --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
```

### Repository: `example-service`

Source:

```text
azure-sre-agent-config/repos/example-repo.yaml
```

Commands:

```bash
./infra/scripts/sre-agent-config.sh plan --file azure-sre-agent-config/repos/example-repo.yaml --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
./infra/scripts/sre-agent-config.sh apply --file azure-sre-agent-config/repos/example-repo.yaml --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
./infra/scripts/sre-agent-config.sh verify --target repos --name example-service --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
```

Repository authentication must be configured according to the selected repository provider. Do not commit PATs.

### Hook: `block-unsafe-remediation`

Source:

```text
azure-sre-agent-config/hooks/example-stop-hook.yaml
```

Commands:

```bash
./infra/scripts/sre-agent-config.sh plan --file azure-sre-agent-config/hooks/example-stop-hook.yaml --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
./infra/scripts/sre-agent-config.sh apply --file azure-sre-agent-config/hooks/example-stop-hook.yaml --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
./infra/scripts/sre-agent-config.sh verify --target hooks --name block-unsafe-remediation --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
```

### Plugin Config: `example-plugin-config`

Source:

```text
azure-sre-agent-config/plugin-configs/example-plugin-config.yaml
```

Commands:

```bash
./infra/scripts/sre-agent-config.sh plan --file azure-sre-agent-config/plugin-configs/example-plugin-config.yaml --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
./infra/scripts/sre-agent-config.sh apply --file azure-sre-agent-config/plugin-configs/example-plugin-config.yaml --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
./infra/scripts/sre-agent-config.sh verify --target plugin-configs --name example-plugin-config --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
```

### HTTP Trigger: `maintenance-window-start`

Source:

```text
azure-sre-agent-config/automations/http-triggers/example-maintenance-window.yaml
```

Commands:

```bash
./infra/scripts/sre-agent-config.sh plan --file azure-sre-agent-config/automations/http-triggers/example-maintenance-window.yaml --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
./infra/scripts/sre-agent-config.sh apply --file azure-sre-agent-config/automations/http-triggers/example-maintenance-window.yaml --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
./infra/scripts/sre-agent-config.sh verify --target http-triggers --name maintenance-window-start --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
```

HTTP trigger creation can generate server-side identifiers and public webhook URLs. Treat generated URLs as sensitive operational entry points.

### Plugin Marketplace: `example-marketplace`

Source:

```text
azure-sre-agent-config/plugins/marketplaces/example-marketplace.yaml
```

Commands:

```bash
./infra/scripts/sre-agent-config.sh plan --file azure-sre-agent-config/plugins/marketplaces/example-marketplace.yaml --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
./infra/scripts/sre-agent-config.sh apply --file azure-sre-agent-config/plugins/marketplaces/example-marketplace.yaml --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
./infra/scripts/sre-agent-config.sh verify --target plugin-marketplaces --name example-marketplace --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
```

### Plugin Installation: `example-plugin-installation`

Source:

```text
azure-sre-agent-config/plugins/installations/example-installation.yaml
```

Commands:

```bash
./infra/scripts/sre-agent-config.sh plan --file azure-sre-agent-config/plugins/installations/example-installation.yaml --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
./infra/scripts/sre-agent-config.sh apply --file azure-sre-agent-config/plugins/installations/example-installation.yaml --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
./infra/scripts/sre-agent-config.sh verify --target plugin-installations --name example-plugin-installation --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
```

### Knowledge File: `example-runbook.md`

Source:

```text
azure-sre-agent-config/knowledge/files/example-runbook.md
```

Commands:

```bash
./infra/scripts/sre-agent-config.sh plan --file azure-sre-agent-config/knowledge/files/example-runbook.md --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
./infra/scripts/sre-agent-config.sh apply --file azure-sre-agent-config/knowledge/files/example-runbook.md --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
./infra/scripts/sre-agent-config.sh verify --target knowledge-files --name example-runbook --subscription "$SUB" --resource-group "$RG" --agent "$AGENT"
```

Do not upload secrets, personal data, or unapproved customer-sensitive data as knowledge files.

## Validation and Troubleshooting

### Validate All Local Configuration

```bash
./infra/scripts/sre-agent-config.sh validate
```

### Validate One Manifest

```bash
./infra/scripts/sre-agent-config.sh validate --file azure-sre-agent-config/skills/example-diagnostics-skill.yaml
```

### Verify One Target by Name

```bash
./infra/scripts/sre-agent-config.sh verify \
  --target skills \
  --name sre-diagnostics-baseline \
  --subscription "$SUB" \
  --resource-group "$RG" \
  --agent "$AGENT"
```

### zsh Multiline Commands

Every continued line must end with `\`:

```bash
./infra/scripts/sre-agent-config.sh plan \
  --target skills \
  --name sre-diagnostics-baseline \
  --subscription "$SUB" \
  --resource-group "$RG" \
  --agent "$AGENT"
```

If the backslash is missing, `zsh` tries to execute lines such as `--target` as separate commands.

### Data-Plane Token Check

```bash
az account get-access-token --resource https://azuresre.dev --query accessToken -o tsv >/dev/null
```

If this fails, data-plane apply and verify operations will fail.

### Inspect Agent Endpoint

```bash
az rest --method GET \
  --url "https://management.azure.com/subscriptions/${SUB}/resourceGroups/${RG}/providers/Microsoft.App/agents/${AGENT}?api-version=2025-05-01-preview" \
  --query properties.agentEndpoint \
  --output tsv
```

### Do Not Use ARM Child Endpoints for Agent Extensions

Do not use these operationally in external tenants:

```text
/skills/{name}
/subagents/{name}
/tools/{name}
/scheduledTasks/{name}
/incidentFilters/{name}
/commonPrompts/{name}
```

Use the data-plane `extendedAgent` endpoints implemented by the script instead.

## Safe Operating Procedure

Use this sequence for controlled rollout:

1. Run `validate` for the full configuration.
2. Run `plan` for the full configuration.
3. Deploy one manifest with `--file`.
4. Verify the deployed target with `--target` and `--name`.
5. Repeat for the next manifest.
6. Use full `apply` only after all manifests and secrets are production-ready.

For production, avoid applying examples with placeholder secrets. Replace examples with environment-specific manifests or inject secrets at release time.

## Structural Constraints and Limits

The script is intentionally simple and deterministic. It does not dynamically discover configuration surfaces from arbitrary folder names or from the manifest `kind`. It uses a fixed target-to-folder and target-to-API mapping.

### Configuration Root vs Internal Folder Names

You can move or rename the configuration root by updating `.sre-agent-layout.env`, setting `SRE_AGENT_CONFIG_DIR`, or passing `--config`:

```bash
./infra/scripts/sre-agent-config.sh validate --config /path/to/customer/azure-sre-agent-config
```

The internal folder layout under that root is a contract. Full apply, target-based apply, verification, and delete expect these relative paths to keep their current meaning:

```text
skills/
subagents/
tools/
common-prompts/
automations/scheduled-tasks/
automations/incident-filters/
automations/http-triggers/
incident-platforms/
connectors/
repos/
hooks/
plugin-configs/
plugins/marketplaces/
plugins/installations/
knowledge/files/
```

If you rename `azure-sre-agent-config/skills` to `azure-sre-agent-config/custom-skills`, full deployment no longer finds those skill manifests, `--target skills` no longer scans them, and `--file azure-sre-agent-config/custom-skills/name.yaml` can no longer infer the target automatically.

For one-off operations, a file outside the standard layout can still be processed when you pass both `--file` and the correct `--target`:

```bash
./infra/scripts/sre-agent-config.sh plan \
  --file /tmp/customer-skill.yaml \
  --target skills \
  --subscription "$SUB" \
  --resource-group "$RG" \
  --agent "$AGENT"
```

Treat this as an exception for testing or migration, not as the repository operating model.

### Direct Children Only for Apply

For most YAML-backed targets, the script scans only YAML files directly inside the expected target directory. Nested folders are not applied.

For example, this file is applied:

```text
azure-sre-agent-config/skills/customer-diagnostics.yaml
```

This file is not applied by full `apply` or `--target skills`:

```text
azure-sre-agent-config/skills/customer/customer-diagnostics.yaml
```

Full `validate` scans YAML files recursively under `azure-sre-agent-config/`, so a nested file can pass validation while still being ignored by `apply`. Keep deployable manifests directly in the documented target directories.

### Target Is the API Selector

The selected target determines the API route. The manifest `kind` is validated and used by some payload transformations, but it does not choose the deployment API.

Examples:

- A file under `azure-sre-agent-config/skills/` is treated as target `skills` and deployed to `/api/v2/extendedAgent/skills/{name}`.
- A file under `azure-sre-agent-config/repos/` is treated as target `repos` and deployed to `/api/v2/repos/{name}`.
- A file passed from outside the standard tree must use `--target` because the script cannot infer the API route from an arbitrary path.

Changing `kind: Skill` to another value does not reroute the manifest. Moving the file or changing `--target` does.

### Manifest Identity Rules

Each YAML manifest must define a logical name through one of these fields:

```text
metadata.name
spec.name
name
```

Each YAML manifest must also define `kind` for validation.

The logical name is the live resource identity for most targets. Renaming it usually creates or updates a different live object and leaves the old object in place until you delete it explicitly.

Use stable, URL-safe names such as lowercase kebab case:

```text
sre-diagnostics-baseline
daily-health-check
block-unsafe-remediation
```

Avoid spaces, slashes, query characters, fragments, and other URL-reserved characters in manifest names. Most data-plane calls interpolate the name directly into the URL path.

Do not keep duplicate manifest names in the same target directory. Selection by `--target` and `--name` processes every local manifest with the matching name, which can cause repeated create, update, or delete calls for the same live object.

### Rendering and Placeholder Limits

The script renders `${VARIABLE_NAME}` placeholders before YAML conversion. Every referenced variable must be set in the shell or loaded through `--env-file`.

When a file contains placeholders, `envsubst` must be installed. When no placeholders are present, `envsubst` is not needed.

`spec.content_file` is resolved relative to the YAML manifest file unless it is an absolute path. If the Markdown file is moved or renamed, update `spec.content_file` in the manifest.

### API Behavior Limits

`plan` is not a live diff. It shows which API operations the script would run, but it does not compare local desired state with remote live state.

`apply` is not transactional. Full desired-state `apply` is best-effort: each manifest is attempted independently, failures are collected, later resources continue, and the command exits non-zero after the final failure summary if anything failed. Earlier successful operations remain applied.

Selective `apply` remains fail-fast. If a selected manifest fails, the command stops immediately and does not print the full desired-state summary.

Recover from full apply failures by running `verify`, fixing the failed manifests listed in the summary, and reapplying those manifests selectively.

Most `PUT` targets behave as upserts: create when missing, update when present. POST-only targets depend on service behavior:

- `http-triggers` are guarded by the script, which skips creation when a trigger with the same name already exists.
- `plugin-marketplaces` and `plugin-installations` are POST surfaces; re-POST behavior is service-defined and delete is not implemented by this script.

`verify` is an inspection command, not a compliance gate. It lists or fetches live surfaces but does not prove that every live object exactly matches local YAML.

`delete` deletes only resources represented by local desired-state files. It is not a general live-resource cleanup tool. `prune` is intentionally blocked until the repository has an explicit drift policy.

### Incident Platform Limits

The agent supports one active incident platform configuration at a time. Applying both Azure Monitor and PagerDuty manifests means the later ARM PATCH wins.

Incident platform changes use ARM PATCH and can be asynchronous. Repeating the operation immediately can return an operation conflict. Verify the live incident platform before applying dependent incident filters.

### Endpoint Override Risk

When `--endpoint` is omitted, the script reads the agent endpoint from ARM using `--subscription`, `--resource-group`, and `--agent`.

When `--endpoint` is provided, the script trusts it. It does not prove that the endpoint belongs to the same agent passed through the ARM options. Use `--endpoint` only for controlled troubleshooting, and verify that it points to the intended agent before running `apply` or `delete`.

### Preview API Limits

Azure SRE Agent control-plane and data-plane APIs are preview surfaces. Keep the pinned API version and data-plane audience unless you are deliberately validating a service change.

The `tools` target is currently skipped for manifests marked with `spec.deployment.status: api-preview-blocked`. Do not remove that marker until the accepted public-preview tool schema is validated in the target tenant.

## Do Not Break The Toy Checklist

Do not rename internal folders under `azure-sre-agent-config/` unless you also update `infra/scripts/sre-agent-config.sh`, this guide, and every command example that depends on the target-to-folder mapping.

Do not assume the manifest `kind` chooses the API route. The route comes from `--target` or from the file path inferred under the standard configuration layout.

Do not nest deployable YAML manifests under extra subfolders and expect full `apply` to process them.

Do not use full `apply` in production until every manifest has been reviewed, every placeholder secret is safely injected, and every preview-blocked surface is understood.

Do not run full `apply` with multiple incident platform manifests unless you intentionally want the last processed platform to become the active one.

Do not rename `metadata.name`, `spec.name`, or `name` casually. Treat the name as the live resource identity.

Do not create duplicate manifest names within the same target directory.

Do not use names with spaces, slashes, `?`, `#`, or other URL-reserved characters.

Do not commit secrets, PATs, connection keys, bearer tokens, generated webhook URLs, or customer-sensitive knowledge files.

Do not pass `--endpoint` manually unless you have verified that it belongs to the same agent identified by `--subscription`, `--resource-group`, and `--agent`.

Do not treat `plan` as drift detection. It is an operation preview, not a local-vs-live comparison.

Do not treat `verify` as a full compliance report. It confirms visibility of live surfaces but does not perform deep semantic comparison.

Do not assume `apply` is atomic. Full apply continues after per-resource failures, but successful earlier and later resources remain changed.

Do not ignore a non-zero full apply exit code just because later resources were applied. Review the final failure summary and remediate every failed manifest.

Do not use ARM child endpoints for Agent Extensions in external tenants when the script already uses data-plane `extendedAgent` routes.

Do not move Terraform-owned infrastructure, identity, RBAC, telemetry, or root agent creation into this script.

Do not move API-only agent configuration into Terraform through generic external commands. Keep the Terraform/API ownership boundary explicit.

Do not remove `api-preview-blocked` from tool manifests until live create, read, update, and delete have been validated in the tenant.

Do not rely on POST-only targets for clean update/delete semantics unless the service API and this script explicitly support them.

Do not use `delete` as an exploratory cleanup command. It is destructive, requires `--yes`, and should be run selectively after reviewing the local manifest set.

Do not try to use `prune` for drift cleanup. It is intentionally blocked in this scaffold.

Do not change `SRE_AGENT_ARM_API_VERSION` or `SRE_AGENT_DATA_PLANE_AUDIENCE` for production runs unless you are deliberately testing a new API contract and have a rollback path.

Do not edit the script target mapping without updating the target reference table, CRUD examples, validation evidence, and customer handoff commands in this document.
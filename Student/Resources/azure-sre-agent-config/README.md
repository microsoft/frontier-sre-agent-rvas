# Azure SRE Agent Configuration

This directory is the Git source of truth for Azure SRE Agent configuration that is not managed by Terraform.

The deployment script reads YAML files, optionally injects Markdown content through `spec.content_file`, converts the result to JSON, and calls the documented Azure SRE Agent APIs.

## Directory Map

| Directory | Purpose | API path |
| --- | --- | --- |
| `skills/` | Reusable skills and their instructions | Data plane `/api/v2/extendedAgent/skills/{name}` |
| `subagents/` | Specialized subagents | Data plane `/api/v2/extendedAgent/agents/{name}` |
| `tools/` | Tool definitions | Data plane `/api/v2/extendedAgent/tools/{name}` |
| `connectors/` | MCP connectors and OAuth connector definitions | ARM `Microsoft.App/agents/connectors@2026-01-01` for `AgentConnector`; ConnectorV2 data-plane APIs for interactive OAuth |
| `common-prompts/` | Shared prompts | Data plane `/api/v2/extendedAgent/commonprompts/{name}` |
| `automations/scheduled-tasks/` | Recurring work | Data plane `/api/v2/extendedAgent/scheduledtasks/{name}` |
| `automations/incident-filters/` | Incident routing filters | Data plane `/api/v2/extendedAgent/incidentFilters/{name}` |
| `automations/http-triggers/` | HTTP trigger definitions | Data plane `/api/v1/httptriggers/create` |
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

Long instructions should live in Markdown and be referenced from YAML. A skill declares an
ordered list of files: the first entry is the skill body, every following entry is a supporting
reference document that the agent can consult on demand.

```yaml
spec:
  files:
    - ./example.md
    - ./example/references/commands.md
```

### Example manifests

Files whose names start with `example-` are **excluded from deployment** by every discovery path in `sre-agent-config.sh` (`validate`, `plan`, `apply`, `verify`, `delete`), for both full desired state and `--target` selections, and the same rule applies to `example-*` knowledge files. The repository ships two **enablement runbooks** — `connectors/example-outlook.yaml` and `connectors/example-teams.yaml` — that give the complete, certified portal-wizard setup for the Outlook and Teams notification connectors used by `cost-optimization-agent` report delivery. These connectors are OAuth-interactive (OAuth sign-in + managed identity + `Microsoft.Web/connections`) and **cannot** be created by a data-plane apply, so they stay `example-`-prefixed by necessity (not because they are incomplete) — the same one-time portal step the GitHub OAuth connector needs. The exclusion remains in effect for any other `example-*` files added later.

## Imported Demo Lab Agent Assets

The VNet Flow Logs and Sample Food demo lab imports Azure SRE Agent configuration from the external branch `feature/app-sample-food-container-app` and normalizes it into this repository's YAML-plus-Markdown desired-state format.

Skills (9). The seven imported networking skills were first consolidated into five to stay
within the official five-active-skills cap
(https://learn.microsoft.com/en-us/azure/sre-agent/skills). A later consolidation folded
`nsg-deny-flow-investigation` and `udr-asymmetry-investigation` into `connectivity-diagnostics`,
and three delivery-oriented skills were added:

- `cost-optimization` (evolved from the imported `cost-retention-optimization` into a
  subscription-wide FinOps skill - the specialist that uses it is `subagents/cost-optimization-agent.yaml`)
- `sample-food-container-app-incident-analysis`
- `rbac-and-resource-access-check`
- `vnet-flow-logs-and-ingestion` (merge of `vnet-flow-logs-troubleshooting` + `storage-flow-log-ingestion-check`)
- `connectivity-diagnostics` (merge of `network-watcher-diagnostics` + `private-endpoint-traffic-analysis`,
  and since the 2026-08 alignment also of `nsg-deny-flow-investigation` + `udr-asymmetry-investigation`)
- `traffic-analytics-kql-analysis`
- `github-issue-triage` — turns a customer-reported GitHub issue into a triaged, labelled and
  prioritised work item
- `iaas-linux-service-recovery` — recovers a failed Linux service on an infrastructure virtual
  machine, in guest, without a human operator
- `source-fix-delivery` — delivers a proven code fix as a branch and a pull request, never a
  direct write to the default branch

Imported knowledge files:

- `knowledge/files/sample-food/github-issue-triage.md`
- `knowledge/files/sample-food/http-500-errors.md`
- `knowledge/files/sample-food/incident-report-template.md`
- `knowledge/files/sample-food/sample-food-architecture.md`

## Imported Sample Food / Grubify Operational Assets

The Sample Food / Grubify operational layer is imported from `dm-chelupati/sre-agent-lab`. The workshop source under `Student/Resources/grubify/` is immutable. Validation issue, branch, fix, and pull-request tests target `lpassaretta_microsoft/grubify` and are executed manually.

Subagents:

- `aca-app-incident-handler` (imported as `incident-handler`, renamed 2026-06-14 to a domain-speaking name)
- `code-analyzer`
- `issue-triager`

GitHub and incident-response surfaces:

- `connectors/github-mcp.yaml` — GitHub managed connector exposed through ConnectorV2 as an MCP
  server. OAuth consent is completed interactively in the portal; no Personal Access Token is
  stored or injected anywhere in this repository. Branch and pull-request operations require
  approval. This single connector now provides all GitHub access: the separate legacy
  `connectors/github.yaml` manifest was removed because its `dataConnectorType: GitHubOAuth`
  shape is deprecated and is rejected by the configuration contract validation.
- `connectors/example-github-mcp.yaml` — historical Personal Access Token reference only;
  excluded from deployment by the `example-` prefix rule.
- `repos/grubify.yaml` — the repository the agent clones for the source-fix delivery flow. It is
  **this workshop repository**, resolved automatically from the `origin` remote, because the
  application source lives under `Student/Resources/grubify` and because the person running the
  workshop must be able to review and merge the proposed fix on a repository they own.

  Scope warning: the Azure SRE Agent repository resource exposes no field that restricts the agent
  to a subdirectory, so the whole repository is cloned. Confining the agent to the Grubify folder
  is a behavioural rule stated in `custom-instructions.md`, in the `code-analyzer` and
  `aca-app-incident-handler` subagents and in the `source-fix-delivery` skill. It is not a
  boundary enforced by the platform, and the workshop material says so openly.
- Azure Monitor incident platform — **owned by Terraform** in the agent body
  (`incidentManagementConfiguration = { type: AzMonitor, connectionName: azmonitor }`); there is
  no data-plane manifest for it.
- `automations/incident-filters/` — three domain-routed response plans: `sample-food-http-errors`,
  `web-tier-nginx`, and `network-observability-review`, plus the workshop-specific
  `parking-vm-unhealthy` plan. The network specialist runs fully autonomously and applies the
  proven remediation itself; scenario restore scripts remain available to the operator.
- `automations/scheduled-tasks/triage-grubify-issues.yaml` — triages Grubify customer issues
  every 12 hours via the `issue-triager` subagent.
- `automations/scheduled-tasks/agent-quality-review.yaml` — periodically reviews the agent's own
  investigation quality through the `agent-quality-reviewer` subagent, so configuration drift and
  degraded reasoning are detected without waiting for a live incident.

## Agent-global custom instructions and retrieval exclusions

- `custom-instructions.md` — instructions applied to every investigation the agent performs,
  independently of which subagent or skill handles it.
- `knowledge/.knowledgeignore` — documents that must stay in Git but must never enter agent
  retrieval. The decisive rule is scenario integrity: any document that names a fault-injection or
  restore script is excluded, because an agent that retrieved it during an investigation would
  cite the script that caused the fault instead of discovering the cause from the evidence, which
  destroys the demonstrative value of the exercise.

## Domain-routing re-architecting (2026-06-14)

Incident response plans were re-architected from severity-only bands to a **domain-routing rule**: each plan owns one failure domain, keyed by incident title (`titleContains` / `titleNotContains`, case-insensitive) on top of severity, so every alert reaches the specialist scoped to that domain. The plans are disjoint by construction at every severity (see the `automations/incident-filters/` bullet above). This added:

- `subagents/iaas-vm-incident-handler.yaml` — new Autonomous IaaS web-tier handler (Syslog-based diagnosis + autonomous in-guest `az vm run-command` restart) that owns the NGINX-down / VM service-health domain, previously mis-routed to `network-traffic-analyst`.
- `automations/incident-filters/web-tier-nginx.yaml` — the new Sev2 web-tier domain plan; `network-traffic-analyst` keeps the hub networking domain (NSG/UDR/VNet-flow) via `network-observability-review`.

Network observability now runs fully autonomously: `network-traffic-analyst` diagnoses the fault
and applies the smallest reversible remediation itself, then verifies that the symptom is gone.
This is deliberate for a non-production demo laboratory in which every scenario ships a restore
script. The run mode is declared on the response plan and on the scheduled task that invoke the
subagent, never inside the subagent manifest: the configuration contract rejects `agent_type`.

## Secrets

Do not commit secrets. For local testing, use `.env` and `${VARIABLE_NAME}` placeholders. The script substitutes placeholders at runtime when `envsubst` is installed.

Enterprise deployments should use CI/CD secrets or Key Vault-backed injection.

## Commands

The script requires `jq` and either Python 3 with PyYAML or a compatible `yq`. Python/PyYAML is preferred because `yq` implementations differ across platforms.

Run commands from `Student/Resources/`. The Student Makefile exports this configuration directory;
direct script execution resolves the same deterministic Student default.

```bash
./infra/scripts/sre-agent-config.sh validate
./infra/scripts/sre-agent-config.sh plan --subscription <sub> --resource-group <rg> --agent <agent>
./infra/scripts/sre-agent-config.sh apply --subscription <sub> --resource-group <rg> --agent <agent>
./infra/scripts/sre-agent-config.sh verify --subscription <sub> --resource-group <rg> --agent <agent>
```

Use `make config-sre-agent` for the default broad deployment. It runs validate,
plan, apply, and verify across every non-`example-*` object and knowledge file in this inventory.
The wrapper resolves the Berlin MCP endpoint from Terraform output; its authentication token is
optional for the lab and can be supplied through `Student/.env`.

Full desired-state deployment:

```bash
./infra/scripts/sre-agent-config.sh validate
./infra/scripts/sre-agent-config.sh plan --subscription <sub> --resource-group <rg> --agent <agent>
./infra/scripts/sre-agent-config.sh apply --subscription <sub> --resource-group <rg> --agent <agent>
./infra/scripts/sre-agent-config.sh verify --subscription <sub> --resource-group <rg> --agent <agent>
```

The certified profile has three connector manifests: ARM-managed `berlin-monitoring-v6` and
`microsoft-learn-mcp`, plus the data-plane ConnectorV2 `github-mcp`. Complete OAuth consent for
`github-mcp` in the SRE Agent portal. Files prefixed `example-*` remain excluded unless explicitly
selected for a controlled validation run.

## Selective Deployment

Selection is optional and intended for focused tests or controlled maintenance. With Make, use
`CONFIG_TARGET`, `CONFIG_NAME`, or `CONFIG_FILE`:

```bash
# Broad validate -> plan -> apply -> verify (default)
make config-sre-agent

# Focus all four phases on one connector
make config-sre-agent \
  CONFIG_TARGET=connectors \
  CONFIG_NAME=github-mcp

# Apply every non-example skill, or one named skill
make skills
make skills CONFIG_NAME=traffic-analytics-kql-analysis
```

With the script, use `--target` to deploy one configuration surface, `--name` to deploy one
manifest inside that surface, and `--file` to deploy one manifest by path. Omitting all three
selectors performs the broad operation.

Examples:

```bash
./infra/scripts/sre-agent-config.sh validate --target skills --name sre-diagnostics-baseline

./infra/scripts/sre-agent-config.sh plan \
  --target skills \
  --name sre-diagnostics-baseline \
  --subscription <sub> \
  --resource-group <rg> \
  --agent <agent>

./infra/scripts/sre-agent-config.sh apply \
  --target skills \
  --name sre-diagnostics-baseline \
  --subscription <sub> \
  --resource-group <rg> \
  --agent <agent>

./infra/scripts/sre-agent-config.sh verify \
  --target skills \
  --name sre-diagnostics-baseline \
  --subscription <sub> \
  --resource-group <rg> \
  --agent <agent>
```

Equivalent file-based example:

```bash
./infra/scripts/sre-agent-config.sh plan \
  --file azure-sre-agent-config/skills/traffic-analytics-kql-analysis.yaml \
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
yq -o=json '.' azure-sre-agent-config/skills/traffic-analytics-kql-analysis.yaml
```

The deployment script does more than plain conversion: it renders environment placeholders, loads Markdown referenced by `spec.content_file`, writes it into `spec.content`, removes `spec.content_file`, and translates each manifest into the data-plane or ARM shape required by its target.

For `skills`, the script maps local `spec.content` into the service property `skillContent`, following the official SRE Agent template behavior.

## Current Validation Result

Selective local validation and planning were verified with:

```bash
./infra/scripts/sre-agent-config.sh validate --target skills --name traffic-analytics-kql-analysis
./infra/scripts/sre-agent-config.sh plan --target skills --name traffic-analytics-kql-analysis --subscription <sub> --resource-group <rg> --agent <agent>
./infra/scripts/sre-agent-config.sh plan --file azure-sre-agent-config/skills/traffic-analytics-kql-analysis.yaml --subscription <sub> --resource-group <rg> --agent <agent>
```

Expected selective plan output:

```text
PUT data-plane /api/v2/extendedAgent/skills/traffic-analytics-kql-analysis from .../azure-sre-agent-config/skills/traffic-analytics-kql-analysis.yaml
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
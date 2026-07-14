# Complete list of Azure SRE Agent resources and sub-resources

This is the complete list of Azure SRE Agent surfaces derived from official Microsoft Learn sources and the official `microsoft/sre-agent` repository referenced by Microsoft Learn for IaC deployment. The list distinguishes surfaces that genuinely belong to Azure SRE Agent from the supporting Azure resources created around the agent.

## ARM control-plane resources and sub-resources

1. `Microsoft.App/agents` - main ARM resource for Azure SRE Agent.
2. `Microsoft.App/agents/connectors@2026-01-01` - ARM sub-resource for connectors, documented in the ARM template reference. In the 2025 API reference the equivalent path is exposed as `Microsoft.App/agents/DataConnectors` and `/DataConnectors/{name}`.
3. `Microsoft.App/agents/skills` - documented ARM sub-resource for skills, path `/skills/{name}`; in external tenants use operationally `/api/v2/extendedAgent/skills/{name}`.
4. `Microsoft.App/agents/subagents` - documented ARM sub-resource for subagents, path `/subagents/{name}`; in external tenants use operationally `/api/v2/extendedAgent/agents/{name}`.
5. `Microsoft.App/agents/tools` - documented ARM sub-resource for tools, path `/tools/{name}`; in external tenants use operationally `/api/v2/extendedAgent/tools/{name}`.
6. `Microsoft.App/agents/scheduledTasks` - documented ARM sub-resource for scheduled tasks, path `/scheduledTasks/{name}`; in external tenants use operationally `/api/v2/extendedAgent/scheduledtasks/{name}`.
7. `Microsoft.App/agents/incidentFilters` - documented ARM sub-resource for incident filters, path `/incidentFilters/{name}`; in external tenants use operationally `/api/v2/extendedAgent/incidentFilters/{name}`.
8. `Microsoft.App/agents/hooks` - ARM sub-resource for hooks, path `/hooks/{name}`.
9. `Microsoft.App/agents/commonPrompts` - documented ARM sub-resource for common prompts, path `/commonPrompts/{name}`; in external tenants use operationally `/api/v2/extendedAgent/commonprompts/{name}`.

## Officially documented configurable data-plane resources

10. Code repositories - `/api/v2/repos/{repoName}`.
11. Knowledge / agent memory documents - `/api/v1/agentmemory/*`.
12. HTTP triggers - `/api/v1/httptriggers/*`.
13. Extended hooks - `/api/v2/extendedAgent/hooks/{hookName}`.
14. Extended subagents - `/api/v2/extendedAgent/agents/{name}`.
15. Extended tools - `/api/v2/extendedAgent/tools/{name}`.
16. Extended connectors - `/api/v2/extendedAgent/connectors/{name}`.
17. Extended skills - `/api/v2/extendedAgent/skills/{name}`.
18. Extended common prompts - `/api/v2/extendedAgent/commonprompts/{name}`.
19. Extended scheduled tasks - `/api/v2/extendedAgent/scheduledtasks/{name}`.
20. Extended plugins - `/api/v2/extendedAgent/plugins/{name}`.

## Official runtime APIs not manageable as IaC resources

21. Threads and chat - `/api/v1/threads`, `/api/v1/threads/{threadId}`, `/api/v1/threads/{threadId}/messages`.
22. Approvals - `/api/v1/approvals/{threadId}`, `/api/v1/approvals/{threadId}/{id}/decision`.
23. Real-time streaming SignalR hub - `/agentHub`.

## Surfaces present in official Microsoft templates but not formally schematized in Microsoft Learn

24. Plugin marketplaces - `/api/v2/plugins/marketplaces`.
25. Plugin installations - `/api/v2/plugins/installations`.
26. Incident platform indexing configuration - `/api/v2/incidents/indexing/{platformType}/configuration`.
27. Data-plane incident filters / response plans - endpoints used by templates for response plans and incident automation; schema not formally published in the Learn API reference.

## Supporting Azure resources excluded from the main list

Resource Group, User Assigned Managed Identity, RBAC role assignment, Log Analytics Workspace, and Application Insights are Azure resources created or used during provisioning. They are essential for Azure SRE Agent to function, but they are not Azure SRE Agent sub-resources. Microsoft Learn lists them as resources created during deployment, not as child resources of `Microsoft.App/agents`.

Official sources: [Azure SRE Agent API reference](https://learn.microsoft.com/en-us/azure/sre-agent/api-reference), [Deploy with infrastructure as code in Azure SRE Agent](https://learn.microsoft.com/en-us/azure/sre-agent/deploy-iac), [Microsoft.App/agents ARM template reference](https://learn.microsoft.com/en-us/azure/templates/microsoft.app/agents?pivots=deployment-language-terraform), [Microsoft.App/agents/connectors ARM template reference](https://learn.microsoft.com/en-us/azure/templates/microsoft.app/agents/connectors?pivots=deployment-language-terraform), [Create and set up Azure SRE Agent](https://learn.microsoft.com/en-us/azure/sre-agent/create-and-set-up), [Network requirements](https://learn.microsoft.com/en-us/azure/sre-agent/network-requirements), [Supported regions](https://learn.microsoft.com/en-us/azure/sre-agent/supported-regions), [Pricing and billing](https://learn.microsoft.com/en-us/azure/sre-agent/pricing-billing), [microsoft/sre-agent templates](https://github.com/microsoft/sre-agent/tree/main/sreagent-templates).

# Accuracy rules used in this document

- When Microsoft Learn publishes enums or allowed values, this document lists all of them.
- When Microsoft Learn publishes only `string`, `object`, or an operations table without a payload schema, this document explicitly states `Not formally documented by Microsoft` and does not invent enums.
- When the official `microsoft/sre-agent` repository shows payloads or endpoints not formally schematized in Learn, this document marks them as `Evidence from official Microsoft template`, not as a complete API contract.
- The Azure SRE Agent control-plane and data-plane APIs are in preview according to Microsoft Learn; paths, schemas, and behavior may change before general availability. Integrations should therefore be pinned to an API version and validated after upgrades.

Official sources: [API reference - preview note](https://learn.microsoft.com/en-us/azure/sre-agent/api-reference#control-plane-arm-operations), [Deploy IaC - template repository](https://learn.microsoft.com/en-us/azure/sre-agent/deploy-iac#overview).

# Certified rules for the format of examples

These rules govern all examples in this document:

| Case | Example format used | Concrete reason | Official source |
| --- | --- | --- | --- |
| Azure SRE Agent resource available as a typed Terraform AzureRM resource | Terraform AzureRM | AzureRM is used only when the AzureRM provider exposes a typed and supported resource. In the main list, no typed AzureRM resource has been published for `Microsoft.App/agents`; therefore AzureRM is not used for the primary SRE Agent resources/sub-resources. | [AzureRM provider docs](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs), [Microsoft.App/agents ARM reference Terraform AzAPI](https://learn.microsoft.com/en-us/azure/templates/microsoft.app/agents?pivots=deployment-language-terraform) |
| ARM Azure SRE Agent resource or sub-resource available via ARM but not typed in AzureRM | Terraform AzAPI | The Microsoft ARM template reference for `Microsoft.App/agents` and `Microsoft.App/agents/connectors` directly publishes Terraform AzAPI examples; the AzAPI provider declares that `azapi_resource` can manage any Azure Resource Manager resource. | [AzAPI `azapi_resource`](https://registry.terraform.io/providers/Azure/azapi/latest/docs/resources/resource), [Microsoft.App/agents](https://learn.microsoft.com/en-us/azure/templates/microsoft.app/agents?pivots=deployment-language-terraform), [Microsoft.App/agents/connectors](https://learn.microsoft.com/en-us/azure/templates/microsoft.app/agents/connectors?pivots=deployment-language-terraform) |
| Agentic configurations shown by the IaC guide as a config directory, especially `skills`, `subagents`, `hooks`, `common-prompts`, `scheduled-tasks`, `incident-filters`, `incident-platforms` | YAML | The official Microsoft IaC guide shows these surfaces as configuration files in template-generated directories; for `skills` and `subagents` it explicitly indicates YAML + Markdown, and for `hooks`, `scheduled-tasks`, `incident-filters` it indicates file-based configurations in the config directory. | [Deploy IaC - config directory structure](https://learn.microsoft.com/en-us/azure/sre-agent/deploy-iac#config-directory-structure), [microsoft/sre-agent templates](https://github.com/microsoft/sre-agent/tree/main/sreagent-templates) |
| Data-plane or runtime API with an official REST/curl example and payload not published as an IaC schema | JSON + curl | The Microsoft API reference documents data-plane operations with endpoints and, where it shows payloads, shows them as JSON/curl. If the schema is not published, this document does not invent YAML or Terraform. | [Azure SRE Agent API reference](https://learn.microsoft.com/en-us/azure/sre-agent/api-reference) |

Important consequence: all Terraform examples in this document follow the `terraform-direct-values` rule: concrete values at the point of use, no `variables.tf`, no `.tfvars`, no pass-through `var.*` or unnecessary locals.

# Common variables used in examples

The examples use these shell variables. Replace the placeholders with real values.

```bash
SUB="00000000-0000-0000-0000-000000000000"
RG="rg-contoso-sre-agent-dev"
AGENT="contoso-sre-agent-dev"
ARM_API_VERSION="2025-05-01-preview"
ARM_BASE="https://management.azure.com/subscriptions/${SUB}/resourceGroups/${RG}/providers/Microsoft.App/agents/${AGENT}"
```

Line-by-line explanation:

| Line | What it configures | Concrete impact |
| --- | --- | --- |
| `SUB=...` | Identifies the Azure subscription containing the agent resource. | If incorrect, ARM calls read or modify the wrong subscription. |
| `RG=...` | Identifies the resource group of the `Microsoft.App/agents` resource. | If incorrect, ARM returns `NotFound` or modifies the wrong agent. |
| `AGENT=...` | Identifies the name of the Azure SRE Agent resource. | The name is used in the ARM path and in the data-plane endpoint resolution. |
| `ARM_API_VERSION=...` | Pin for the preview control-plane API documented by Microsoft Learn. | Avoids implicit calls to different versions with different schemas or behaviors. |
| `ARM_BASE=...` | ARM base URL for the agent resource. | All control-plane operations append their path and query to this URL. |

For the data-plane:

```bash
ENDPOINT=$(az rest --method GET \
  --url "${ARM_BASE}?api-version=${ARM_API_VERSION}" \
  --query properties.agentEndpoint -o tsv)

TOKEN=$(az account get-access-token \
  --resource https://azuresre.dev \
  --query accessToken -o tsv)
```

Line-by-line explanation:

| Line | What it configures | Concrete impact |
| --- | --- | --- |
| `ENDPOINT=$(az rest --method GET ...)` | Reads the agent from ARM. | Retrieves the agent-specific data-plane endpoint. |
| `--url "${ARM_BASE}?api-version=..."` | Uses the documented preview ARM API. | Required to obtain `properties.agentEndpoint`. |
| `--query properties.agentEndpoint -o tsv` | Extracts only the data-plane endpoint. | Produces a value like `https://{name}--{id}.{hash}.{region}.azuresre.ai`. |
| `TOKEN=$(az account get-access-token ...)` | Requests an Entra ID token. | Authenticates data-plane calls. |
| `--resource https://azuresre.dev` | Sets the audience required by the data-plane. | A standard ARM token for `management.azure.com` is not sufficient for the data-plane. |
| `--query accessToken -o tsv` | Extracts the raw bearer token. | The value must be used in the `Authorization: Bearer` header. |

Official sources: [API reference - authentication](https://learn.microsoft.com/en-us/azure/sre-agent/api-reference#authentication), [API reference - data plane](https://learn.microsoft.com/en-us/azure/sre-agent/api-reference#data-plane).

# Quick operational CRUD per resource

This section shows raw API examples for Create, Read, Update, and Delete. The [SRE Agent Config Script Guide](sre-agent-config-script-guide.md) shows the same flows using `03-scripts/sre-agent-config.sh`.

In data-plane examples, `Create` and `Update` often use the same `PUT`: if the resource does not exist it is created; if it exists it is updated.

## Agent root - `Microsoft.App/agents`

Create:

```bash
az rest --method PUT \
  --url "${ARM_BASE}?api-version=${ARM_API_VERSION}" \
  --body @agent-root.json
```

Read:

```bash
az rest --method GET \
  --url "${ARM_BASE}?api-version=${ARM_API_VERSION}" \
  --output json
```

Update:

```bash
az rest --method PATCH \
  --url "${ARM_BASE}?api-version=${ARM_API_VERSION}" \
  --body '{"properties":{"upgradeChannel":"Stable"}}'
```

Delete:

```bash
az rest --method DELETE \
  --url "${ARM_BASE}?api-version=${ARM_API_VERSION}"
```

## ARM connector - `Microsoft.App/agents/connectors`

Create:

```bash
az rest --method PUT \
  --url "${ARM_BASE}/connectors/log-analytics?api-version=2026-01-01" \
  --body @connector-log-analytics.json
```

Read:

```bash
az rest --method GET \
  --url "${ARM_BASE}/connectors/log-analytics?api-version=2026-01-01" \
  --output json
```

Update:

```bash
az rest --method PUT \
  --url "${ARM_BASE}/connectors/log-analytics?api-version=2026-01-01" \
  --body @connector-log-analytics-updated.json
```

Delete:

```bash
az rest --method DELETE \
  --url "${ARM_BASE}/connectors/log-analytics?api-version=2026-01-01"
```

## Skill - `/api/v2/extendedAgent/skills/{name}`

Create:

```bash
curl -fsS -X PUT \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  "${ENDPOINT}/api/v2/extendedAgent/skills/sre-diagnostics-baseline" \
  --data @skill-envelope.json
```

Read:

```bash
curl -fsS -H "Authorization: Bearer ${TOKEN}" \
  "${ENDPOINT}/api/v2/extendedAgent/skills/sre-diagnostics-baseline" | jq .
```

Update:

```bash
curl -fsS -X PUT \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  "${ENDPOINT}/api/v2/extendedAgent/skills/sre-diagnostics-baseline" \
  --data @skill-envelope-updated.json
```

Delete:

```bash
curl -fsS -X DELETE \
  -H "Authorization: Bearer ${TOKEN}" \
  "${ENDPOINT}/api/v2/extendedAgent/skills/sre-diagnostics-baseline"
```

## Subagent - `/api/v2/extendedAgent/agents/{name}`

Create:

```bash
curl -fsS -X PUT -H "Authorization: Bearer ${TOKEN}" -H "Content-Type: application/json" \
  "${ENDPOINT}/api/v2/extendedAgent/agents/observability-investigator" \
  --data @subagent-envelope.json
```

Read:

```bash
curl -fsS -H "Authorization: Bearer ${TOKEN}" \
  "${ENDPOINT}/api/v2/extendedAgent/agents/observability-investigator" | jq .
```

Update:

```bash
curl -fsS -X PUT -H "Authorization: Bearer ${TOKEN}" -H "Content-Type: application/json" \
  "${ENDPOINT}/api/v2/extendedAgent/agents/observability-investigator" \
  --data @subagent-envelope-updated.json
```

Delete:

```bash
curl -fsS -X DELETE -H "Authorization: Bearer ${TOKEN}" \
  "${ENDPOINT}/api/v2/extendedAgent/agents/observability-investigator"
```

## Tool - `/api/v2/extendedAgent/tools/{name}`

Current validation status in this tenant: blocked by public preview schema behavior. Microsoft Learn documents the surface, but live validation on 2026-06-11 rejected `type: "Tool"` with `InvalidObjectType`; it also rejected `KustoTool`, `PythonTool`, `HttpClientTool`, `LinkTool`, and `PythonFunctionTool`. The ARM `/tools/{name}` fallback returned the Agent Extensions tenant restriction. Treat the examples below as the documented API shape, not as a currently validated deployment path for this repository.

Create:

```bash
curl -fsS -X PUT -H "Authorization: Bearer ${TOKEN}" -H "Content-Type: application/json" \
  "${ENDPOINT}/api/v2/extendedAgent/tools/azure-resource-graph-readonly" \
  --data @tool-envelope.json
```

Read:

```bash
curl -fsS -H "Authorization: Bearer ${TOKEN}" \
  "${ENDPOINT}/api/v2/extendedAgent/tools/azure-resource-graph-readonly" | jq .
```

Update:

```bash
curl -fsS -X PUT -H "Authorization: Bearer ${TOKEN}" -H "Content-Type: application/json" \
  "${ENDPOINT}/api/v2/extendedAgent/tools/azure-resource-graph-readonly" \
  --data @tool-envelope-updated.json
```

Delete:

```bash
curl -fsS -X DELETE -H "Authorization: Bearer ${TOKEN}" \
  "${ENDPOINT}/api/v2/extendedAgent/tools/azure-resource-graph-readonly"
```

## Common prompt - `/api/v2/extendedAgent/commonprompts/{name}`

Create:

```bash
curl -fsS -X PUT -H "Authorization: Bearer ${TOKEN}" -H "Content-Type: application/json" \
  "${ENDPOINT}/api/v2/extendedAgent/commonprompts/incident-summary-executive" \
  --data @common-prompt-envelope.json
```

Read:

```bash
curl -fsS -H "Authorization: Bearer ${TOKEN}" \
  "${ENDPOINT}/api/v2/extendedAgent/commonprompts/incident-summary-executive" | jq .
```

Update:

```bash
curl -fsS -X PUT -H "Authorization: Bearer ${TOKEN}" -H "Content-Type: application/json" \
  "${ENDPOINT}/api/v2/extendedAgent/commonprompts/incident-summary-executive" \
  --data @common-prompt-envelope-updated.json
```

Delete:

```bash
curl -fsS -X DELETE -H "Authorization: Bearer ${TOKEN}" \
  "${ENDPOINT}/api/v2/extendedAgent/commonprompts/incident-summary-executive"
```

## Scheduled task - `/api/v2/extendedAgent/scheduledtasks/{name}`

Create:

```bash
curl -fsS -X PUT -H "Authorization: Bearer ${TOKEN}" -H "Content-Type: application/json" \
  "${ENDPOINT}/api/v2/extendedAgent/scheduledtasks/daily-health-check" \
  --data @scheduled-task-envelope.json
```

Read:

```bash
curl -fsS -H "Authorization: Bearer ${TOKEN}" \
  "${ENDPOINT}/api/v2/extendedAgent/scheduledtasks/daily-health-check" | jq .
```

Update:

```bash
curl -fsS -X PUT -H "Authorization: Bearer ${TOKEN}" -H "Content-Type: application/json" \
  "${ENDPOINT}/api/v2/extendedAgent/scheduledtasks/daily-health-check" \
  --data @scheduled-task-envelope-updated.json
```

Delete:

```bash
curl -fsS -X DELETE -H "Authorization: Bearer ${TOKEN}" \
  "${ENDPOINT}/api/v2/extendedAgent/scheduledtasks/daily-health-check"
```

## Incident filter - `/api/v2/extendedAgent/incidentFilters/{name}`

Create:

```bash
curl -fsS -X PUT -H "Authorization: Bearer ${TOKEN}" -H "Content-Type: application/json" \
  "${ENDPOINT}/api/v2/extendedAgent/incidentFilters/sev2-production-only" \
  --data @incident-filter-envelope.json
```

Read:

```bash
curl -fsS -H "Authorization: Bearer ${TOKEN}" \
  "${ENDPOINT}/api/v2/extendedAgent/incidentFilters/sev2-production-only" | jq .
```

Update:

```bash
curl -fsS -X PUT -H "Authorization: Bearer ${TOKEN}" -H "Content-Type: application/json" \
  "${ENDPOINT}/api/v2/extendedAgent/incidentFilters/sev2-production-only" \
  --data @incident-filter-envelope-updated.json
```

Delete:

```bash
curl -fsS -X DELETE -H "Authorization: Bearer ${TOKEN}" \
  "${ENDPOINT}/api/v2/extendedAgent/incidentFilters/sev2-production-only"
```

## Incident platform - root ARM PATCH

Create:

```bash
az rest --method PATCH \
  --url "${ARM_BASE}?api-version=${ARM_API_VERSION}" \
  --body '{"properties":{"incidentManagementConfiguration":{"type":"AzMonitor","connectionName":"azure-monitor"}}}'
```

Read:

```bash
az rest --method GET \
  --url "${ARM_BASE}?api-version=${ARM_API_VERSION}" \
  --query properties.incidentManagementConfiguration \
  --output json
```

Update:

```bash
az rest --method PATCH \
  --url "${ARM_BASE}?api-version=${ARM_API_VERSION}" \
  --body @incident-platform-updated.json
```

Delete:

This clears the active incident platform configuration.

```bash
az rest --method PATCH \
  --url "${ARM_BASE}?api-version=${ARM_API_VERSION}" \
  --body '{"properties":{"incidentManagementConfiguration":{"type":"None"}}}'
```

## Data-plane connector - `/api/v2/extendedAgent/connectors/{name}`

Create:

```bash
curl -fsS -X PUT -H "Authorization: Bearer ${TOKEN}" -H "Content-Type: application/json" \
  "${ENDPOINT}/api/v2/extendedAgent/connectors/dynatrace-mcp" \
  --data @connector-envelope.json
```

Read:

```bash
curl -fsS -H "Authorization: Bearer ${TOKEN}" \
  "${ENDPOINT}/api/v2/extendedAgent/connectors/dynatrace-mcp" | jq .
```

Update:

```bash
curl -fsS -X PUT -H "Authorization: Bearer ${TOKEN}" -H "Content-Type: application/json" \
  "${ENDPOINT}/api/v2/extendedAgent/connectors/dynatrace-mcp" \
  --data @connector-envelope-updated.json
```

Delete:

```bash
curl -fsS -X DELETE -H "Authorization: Bearer ${TOKEN}" \
  "${ENDPOINT}/api/v2/extendedAgent/connectors/dynatrace-mcp"
```

## Repository - `/api/v2/repos/{name}`

Create:

```bash
curl -fsS -X PUT -H "Authorization: Bearer ${TOKEN}" -H "Content-Type: application/json" \
  "${ENDPOINT}/api/v2/repos/example-service" \
  --data @repo-envelope.json
```

Read:

```bash
curl -fsS -H "Authorization: Bearer ${TOKEN}" \
  "${ENDPOINT}/api/v2/repos/example-service" | jq .
```

Update:

```bash
curl -fsS -X PUT -H "Authorization: Bearer ${TOKEN}" -H "Content-Type: application/json" \
  "${ENDPOINT}/api/v2/repos/example-service" \
  --data @repo-envelope-updated.json
```

Delete:

```bash
curl -fsS -X DELETE -H "Authorization: Bearer ${TOKEN}" \
  "${ENDPOINT}/api/v2/repos/example-service"
```

## Hook - `/api/v2/extendedAgent/hooks/{name}`

Create:

```bash
curl -fsS -X PUT -H "Authorization: Bearer ${TOKEN}" -H "Content-Type: application/json" \
  "${ENDPOINT}/api/v2/extendedAgent/hooks/block-unsafe-remediation" \
  --data @hook-envelope.json
```

Read:

```bash
curl -fsS -H "Authorization: Bearer ${TOKEN}" \
  "${ENDPOINT}/api/v2/extendedAgent/hooks/block-unsafe-remediation" | jq .
```

Update:

```bash
curl -fsS -X PUT -H "Authorization: Bearer ${TOKEN}" -H "Content-Type: application/json" \
  "${ENDPOINT}/api/v2/extendedAgent/hooks/block-unsafe-remediation" \
  --data @hook-envelope-updated.json
```

Delete:

```bash
curl -fsS -X DELETE -H "Authorization: Bearer ${TOKEN}" \
  "${ENDPOINT}/api/v2/extendedAgent/hooks/block-unsafe-remediation"
```

## Plugin config - `/api/v2/extendedAgent/plugins/{name}`

Create:

```bash
curl -fsS -X PUT -H "Authorization: Bearer ${TOKEN}" -H "Content-Type: application/json" \
  "${ENDPOINT}/api/v2/extendedAgent/plugins/example-plugin-config" \
  --data @plugin-config-envelope.json
```

Read:

```bash
curl -fsS -H "Authorization: Bearer ${TOKEN}" \
  "${ENDPOINT}/api/v2/extendedAgent/plugins/example-plugin-config" | jq .
```

Update:

```bash
curl -fsS -X PUT -H "Authorization: Bearer ${TOKEN}" -H "Content-Type: application/json" \
  "${ENDPOINT}/api/v2/extendedAgent/plugins/example-plugin-config" \
  --data @plugin-config-envelope-updated.json
```

Delete:

```bash
curl -fsS -X DELETE -H "Authorization: Bearer ${TOKEN}" \
  "${ENDPOINT}/api/v2/extendedAgent/plugins/example-plugin-config"
```

## HTTP trigger - `/api/v1/httptriggers/*`

Create:

```bash
curl -fsS -X POST -H "Authorization: Bearer ${TOKEN}" -H "Content-Type: application/json" \
  "${ENDPOINT}/api/v1/httptriggers/create" \
  --data @http-trigger-create.json
```

Read:

```bash
curl -fsS -H "Authorization: Bearer ${TOKEN}" \
  "${ENDPOINT}/api/v1/httptriggers" | jq .
```

Update:

```bash
curl -fsS -X POST -H "Authorization: Bearer ${TOKEN}" -H "Content-Type: application/json" \
  "${ENDPOINT}/api/v1/httptriggers/create" \
  --data @http-trigger-create-updated.json
```

Delete:

No stable DELETE route is documented in this repository. Treat generated trigger URLs as sensitive and rotate/recreate according to the service-supported workflow.

## Knowledge file - `/api/v1/agentmemory/*`

Create:

```bash
curl -fsS -X POST \
  -H "Authorization: Bearer ${TOKEN}" \
  -F "files=@06-sre-agent-configuration/knowledge/files/example-runbook.md" \
  "${ENDPOINT}/api/v1/agentmemory/upload"
```

Read:

```bash
curl -fsS -H "Authorization: Bearer ${TOKEN}" \
  "${ENDPOINT}/api/v1/agentmemory/status" | jq .
```

Update:

Update by re-uploading the same filename.

```bash
curl -fsS -X POST \
  -H "Authorization: Bearer ${TOKEN}" \
  -F "files=@06-sre-agent-configuration/knowledge/files/example-runbook.md" \
  "${ENDPOINT}/api/v1/agentmemory/upload"
```

Delete:

Delete one document.

```bash
curl -fsS -X DELETE -H "Authorization: Bearer ${TOKEN}" \
  "${ENDPOINT}/api/v1/agentmemory/document/example-runbook.md"
```

## Plugin marketplace and installation POST surfaces

Create marketplace document:

```bash
curl -fsS -X POST -H "Authorization: Bearer ${TOKEN}" -H "Content-Type: application/json" \
  "${ENDPOINT}/api/v2/plugins/marketplaces" \
  --data @plugin-marketplace.json
```

Read marketplaces:

```bash
curl -fsS -H "Authorization: Bearer ${TOKEN}" \
  "${ENDPOINT}/api/v2/plugins/marketplaces" | jq .
```

Create plugin installation:

```bash
curl -fsS -X POST -H "Authorization: Bearer ${TOKEN}" -H "Content-Type: application/json" \
  "${ENDPOINT}/api/v2/plugins/installations" \
  --data @plugin-installation.json
```

Read plugin installations:

```bash
curl -fsS -H "Authorization: Bearer ${TOKEN}" \
  "${ENDPOINT}/api/v2/plugins/installations" | jq .
```

Update:

The repository examples use POST for these surfaces and do not document stable per-object PATCH routes. Treat updates as service-managed POST operations until official schema and lifecycle routes are available.

Delete:

The repository examples do not document stable per-object DELETE routes for these surfaces. Treat delete as unsupported until official lifecycle routes are available.

# 1. `Microsoft.App/agents`

## Concrete description

`Microsoft.App/agents` is the main ARM resource of Azure SRE Agent. It represents the agent itself: name, region, identity, AI model, action configuration, logging, incident management, knowledge graph, consumption limits, and upgrade channel. If this resource does not exist, no Azure SRE Agent is deployed: all sub-resources and data-plane APIs depend on its existence and its `agentEndpoint`.

Concrete technical impact:

- Decides where the agent compute runs via `location`.
- Decides which identity the agent uses to read or act on Azure resources via `identity`, `actionConfiguration.identity`, and `knowledgeGraphConfiguration.identity`.
- Decides how autonomously the agent can act via `actionConfiguration.mode` and `actionConfiguration.accessLevel`.
- Decides the model/provider and therefore quality, cost, availability, and data residency via `defaultModel`.
- Exposes the data-plane endpoint via the read-only property `properties.agentEndpoint`.
- Applies active-flow cost limits via `monthlyAgentUnitLimit`.

Official sources: [Microsoft.App/agents ARM template reference](https://learn.microsoft.com/en-us/azure/templates/microsoft.app/agents?pivots=deployment-language-terraform), [API reference - Agent properties](https://learn.microsoft.com/en-us/azure/sre-agent/api-reference#agent-properties), [Supported regions](https://learn.microsoft.com/en-us/azure/sre-agent/supported-regions), [Pricing and billing](https://learn.microsoft.com/en-us/azure/sre-agent/pricing-billing).

## Parameters and possible values

| Parameter | Type | Required | What it is concretely | Technical impact | Documented possible values |
| --- | --- | --- | --- | --- | --- |
| `type` | string | Yes, in AzAPI/Terraform | ARM type and API version. | Determines which ARM provider and schema to use. | ARM reference Terraform: `Microsoft.App/agents@2026-01-01`. API reference control-plane: `2025-05-01-preview`. |
| `name` | string | Yes | ARM name of the agent. | Used in the resource ID, portal URL, and operational naming. Changing it means creating a different agent. | Documented pattern: `^[A-Za-z]([-A-Za-z0-9]{0,30}[A-Za-z0-9])$`. |
| `location` | string | Yes | Azure region where the agent lives. | Determines where the agent compute runs. Does not limit managed resources if RBAC allows cross-region access. Not modifiable after creation per the regions page. | `australiaeast`, `canadacentral`, `eastus2`, `francecentral`, `koreacentral`, `swedencentral`, `uksouth`. |
| `tags` | object | No | Azure tags. | Governance, ownership, cost management, lifecycle. | String-string dictionary. No enum. |
| `identity.type` | enum string | Yes if identity is set | Type of managed identity assigned to the resource. | Determines how the agent authenticates to Azure. | `None`, `SystemAssigned`, `UserAssigned`, `SystemAssigned,UserAssigned`. |
| `identity.userAssignedIdentities` / `identity_ids` | object/list | Required if `UserAssigned` | List of associated UAMIs. | Allows use of pre-governed and reusable identities. | Resource ID of User Assigned Managed Identity. No enum. |
| `properties.actionConfiguration.accessLevel` | enum string | No | Action access level. | Influences how broad the agent's operational capability can be. | `Low`, `High`. |
| `properties.actionConfiguration.identity` | string | No | Identity used to execute actions. | Actions inherit RBAC permissions of this identity. | Identity resource ID or identity string. No enum. |
| `properties.actionConfiguration.mode` | enum string | No | Mode in which the agent manages actions. | Controls whether the agent operates read-only, with human review, or autonomously. | ARM 2026: `Autonomous`, `ReadOnly`, `Review`. API 2025: `Review`, `Automatic`, `ReadOnly`. |
| `properties.agentIdentity.initialSponsorGroupId` | string | Yes for `AgentIdentity` | Initial sponsor group ID. | Identity/governance seed for the agent. | String, typically an Entra group object ID. No enum. |
| `properties.agentSpaceId` | string | No | Agent space reference. | Associates the agent with an agent space when used. | Not formally documented by Microsoft beyond the `string` type. |
| `properties.defaultModel.provider` | string | No | AI model provider. | Changes the backend, cost, availability, and data residency. | API reference indicates `Anthropic` or `MicrosoftFoundry`; setup page shows UI providers `Anthropic` and `Azure OpenAI`. |
| `properties.defaultModel.name` | string | No | Model name. | Determines the concrete model, quality, and AAU rate. | Not a complete enum. ARM examples: `gpt-5`, `claude-opus-4-5`, `claude-sonnet-4-5`; 2026 pricing cites `Claude Opus 4.6`, `GPT 5.3 Codex`, `GPT 5.2`; templates also use `Automatic`. |
| `properties.incidentManagementConfiguration.type` | enum/string | No | Incident platform type. | Determines from which system incidents arrive or are managed. | API reference: `PagerDuty`, `AzMonitor`, `ServiceNow`, `None`. ARM schema: `string`. |
| `properties.incidentManagementConfiguration.connectionKey` | string sensitive | No | Secret or connection key for the incident platform. | Authenticates to the external platform. Risk of secret exposure in state/logs if handled poorly. | Sensitive string. No enum. |
| `properties.incidentManagementConfiguration.connectionName` | string | No | Incident connection name. | Operational label for the connection. | String. No enum. |
| `properties.incidentManagementConfiguration.connectionUrl` | string | No | Incident platform URL. | Incident integration endpoint. | URL string. No enum. |
| `properties.incidentManagementConfiguration.oboUser` | string | No | On-behalf-of user. | User context for the incident platform. | String. No enum. |
| `properties.knowledgeGraphConfiguration.identity` | string | No | Identity used for the knowledge graph / resource access. | Determines which resources the agent can read for context and investigation. | Identity resource ID. No enum. |
| `properties.knowledgeGraphConfiguration.managedResources` | string[] | No | List of managed scopes. | Defines resource groups or resource IDs the agent can use as context. | Array of ARM resource IDs. No enum. |
| `properties.logConfiguration.applicationInsightsConfiguration.appId` | string | No | Application Insights Application ID. | Connects agent logging/telemetry to App Insights. | String/app ID. No enum. |
| `properties.logConfiguration.applicationInsightsConfiguration.connectionString` | string sensitive | No | App Insights connection string. | Configures telemetry ingestion. Must be treated as sensitive. | Sensitive string. No enum. |
| `properties.upgradeChannel` | enum string | No | Runtime upgrade channel. | Determines stability vs. early access to features. | `Stable`, `Preview`. |
| `properties.monthlyAgentUnitLimit` | number | No | Monthly active-flow AAU limit. | When reached, chat and actions stop until the next month or the limit is increased; always-on billing continues. | Pricing: minimum `500`, maximum `1000000` AAU. |
| `properties.mcpServers` | string[] | No | MCP server URLs. | Adds MCP servers reachable by the agent. | URL array. No enum. |
| `properties.vnetConfiguration.subnetResourceId` | string | No | Subnet resource ID for VNet injection. | Affects the agent's network path when supported. | Subnet ARM resource ID. No published enum. |
| `properties.experimentalSettings` | object | No | Feature flag overrides. | Enables experimental behaviors. | Not formally documented by Microsoft. |
| `properties.provisioningState` | string | Read-only | ARM provisioning state. | Deployment diagnostics. | `Succeeded`, `Failed`, `InProgress`, `Canceled`, `Deleting`. |
| `properties.agentEndpoint` | string | Read-only | Per-agent data-plane endpoint. | Base URL for data-plane runtime and configuration. | Documented pattern: `https://{name}--{id}.{hash}.{region}.azuresre.ai`. |
| `properties.powerState` | string | Read-only | Runtime state. | Indicates whether the agent accepts work. | `Running`, `Stopped`. |
| `properties.outboundIpAddresses` | string[] | Read-only | Agent outbound IP addresses. | Can be used for firewall allow-lists toward external systems. | Array of IP strings. |

### Technical meaning of the main enum values

| Parameter | Value | Concrete meaning | Technical consequence |
| --- | --- | --- | --- |
| `identity.type` | `None` | No managed identity assigned. | The agent has no ARM identity for Azure access via identity. In practice this is rarely suitable for enterprise scenarios. |
| `identity.type` | `SystemAssigned` | Azure creates an identity tied to the resource lifecycle. | Deleting the agent also deletes the identity. Less reusable and less governable across environments. |
| `identity.type` | `UserAssigned` | Uses a separately created managed identity. | Better for enterprise: lifecycle, RBAC, naming, and audit are separate from the agent. |
| `identity.type` | `SystemAssigned,UserAssigned` | Combines both. | Increases complexity and authorization surface; requires clarity on which identity actions use. |
| `actionConfiguration.accessLevel` | `Low` | More restrictive posture. | Reduces operational risk; recommended for production environments or initial enablement. |
| `actionConfiguration.accessLevel` | `High` | More permissive posture. | Increases remediation/action capability but also blast radius; requires strict RBAC, approvals, and auditing. |
| `actionConfiguration.mode` | `ReadOnly` | The agent reads and analyzes without making changes. | Useful for assessments, assisted troubleshooting, regulated environments. |
| `actionConfiguration.mode` | `Review` | The agent proposes or prepares actions with human review. | Best enterprise default: balances automation and human control. |
| `actionConfiguration.mode` | `Autonomous` | ARM 2026 value for autonomous automation. | The agent can proceed with fewer human gates according to policies and permissions; requires strong controls. |
| `actionConfiguration.mode` | `Automatic` | Value indicated in the 2025 API reference. | Semantically equivalent/related to automation, but the name depends on the API version; use only with a version that accepts it. |
| `upgradeChannel` | `Stable` | Conservative channel. | Preferred choice for production. |
| `upgradeChannel` | `Preview` | Channel with early features. | Higher risk of behavioral drift; use for test/lab. |
| `incidentManagementConfiguration.type` | `None` | No incident platform configured at the agent level. | The agent does not receive incidents from that root integration. |
| `incidentManagementConfiguration.type` | `AzMonitor` | Azure Monitor as the incident/alert source. | Requires RBAC on Azure Monitor and target resources. |
| `incidentManagementConfiguration.type` | `PagerDuty` | PagerDuty as the incident platform. | Requires a connection key/URL and secret management. |
| `incidentManagementConfiguration.type` | `ServiceNow` | ServiceNow as the incident platform. | Requires a connection to a ServiceNow instance and appropriate credentials. |
| `defaultModel.provider` | `MicrosoftFoundry` | Microsoft/Azure provider for Foundry/OpenAI models. | May be preferred for Azure governance and data residency. |
| `defaultModel.provider` | `Anthropic` | Anthropic/Claude provider. | Can provide high quality for complex RCAs, but the setup page states that Anthropic is excluded from EU Data Boundary commitments. |
| `powerState` | `Running` | Agent started. | Chat, automations, and active flow can work, within consumption limits. |
| `powerState` | `Stopped` | Agent stopped. | Active flow stopped, chat/actions unavailable; always-on billing continues as long as the resource exists. |
| `provisioningState` | `Succeeded` | Provisioning complete. | The resource is ready from an ARM perspective. |
| `provisioningState` | `Failed` | Provisioning failed. | Deployment/operation errors need to be read. |
| `provisioningState` | `InProgress` | Provisioning in progress. | Do not assume endpoints or sub-resources are ready. |
| `provisioningState` | `Canceled` | Operation cancelled. | Terminal state to investigate. |
| `provisioningState` | `Deleting` | Deletion in progress. | Do not create sub-resources or call the data-plane. |

## Certified example: Terraform AzAPI

Format rationale: Microsoft Learn publishes `Microsoft.App/agents` in the ARM template reference with a `Terraform (AzAPI provider) resource definition`; it does not publish an equivalent typed AzureRM resource. The AzAPI provider documents `azapi_resource` as a resource capable of managing any Azure Resource Manager resource.

```hcl
resource "azapi_resource" "agent" {
  type      = "Microsoft.App/agents@2026-01-01"
  name      = "contoso-sre-agent-dev"
  parent_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-contoso-sre-agent-dev"
  location  = "swedencentral"

  identity {
    type = "UserAssigned"
    identity_ids = [
      "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-contoso-sre-agent-dev/providers/Microsoft.ManagedIdentity/userAssignedIdentities/uai-contoso-sre-agent-dev"
    ]
  }

  body = {
    properties = {
      actionConfiguration = {
        accessLevel = "Low"
        identity    = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-contoso-sre-agent-dev/providers/Microsoft.ManagedIdentity/userAssignedIdentities/uai-contoso-sre-agent-dev"
        mode        = "Review"
      }

      defaultModel = {
        provider = "MicrosoftFoundry"
        name     = "gpt-5"
      }

      knowledgeGraphConfiguration = {
        identity = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-contoso-sre-agent-dev/providers/Microsoft.ManagedIdentity/userAssignedIdentities/uai-contoso-sre-agent-dev"
        managedResources = [
          "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-workload-prod"
        ]
      }

      logConfiguration = {
        applicationInsightsConfiguration = {
          appId = "11111111-1111-1111-1111-111111111111"
        }
      }

      incidentManagementConfiguration = {
        type           = "AzMonitor"
        connectionName = "azure-monitor"
      }

      upgradeChannel        = "Stable"
      monthlyAgentUnitLimit = 500
    }
  }

  tags = {
    workload    = "azure-sre-agent"
    environment = "dev"
  }

  response_export_values = [
    "properties.agentEndpoint",
    "properties.powerState"
  ]
}
```

Line-by-line explanation:

| Line/block | What it configures | Concrete impact |
| --- | --- | --- |
| `resource "azapi_resource" "agent"` | Terraform resource managed by the AzAPI provider. | Uses ARM for a resource not typed in AzureRM. |
| `type = "Microsoft.App/agents@2026-01-01"` | ARM type and API version. | Aligns Terraform with the Microsoft ARM template reference. |
| `name = "contoso-sre-agent-dev"` | Agent name. | Enters the resource ID and identifies the agent. |
| `parent_id = ".../resourceGroups/rg-contoso-sre-agent-dev"` | Resource group parent. | Places the agent in the correct resource group without pass-through variables. |
| `location = "swedencentral"` | Agent region. | Deploys the compute in an officially supported region. |
| `identity { ... }` | Managed identity assigned to the resource. | Allows the agent to have an Azure identity. |
| `type = "UserAssigned"` | Uses UAMI. | Improves governance, RBAC, and separate lifecycle. |
| `identity_ids = [...]` | Associated UAMI. | Links the agent to a pre-governed identity. |
| `body = { properties = { ... } }` | Dynamic AzAPI ARM body. | Contains the agent-specific properties. |
| `actionConfiguration` | Action configuration. | Sets the mode, identity, and access level of actions. |
| `accessLevel = "Low"` | Low access. | Reduces operational blast radius. |
| `mode = "Review"` | Review mode. | Maintains human-in-the-loop for actions. |
| `defaultModel` | AI provider and model. | Affects quality, cost, availability, and data residency. |
| `knowledgeGraphConfiguration` | Scope and identity for Azure context. | Tells the agent which resources it can use as context if RBAC permits. |
| `logConfiguration` | Application Insights. | Links the agent's telemetry/diagnostics. |
| `incidentManagementConfiguration` | Incident platform. | Configures Azure Monitor as the root incident scenario. |
| `upgradeChannel = "Stable"` | Upgrade channel. | Conservative posture for enterprise environments. |
| `monthlyAgentUnitLimit = 500` | Active flow AAU limit. | Official minimum; controls active flow, not always-on. |
| `tags = { ... }` | Azure tags. | Supports governance and cost management. |
| `response_export_values = [...]` | ARM values exported to the AzAPI state output. | Makes data-plane endpoints and power state available for other steps. |

Official sources: [Microsoft.App/agents - Terraform AzAPI resource definition](https://learn.microsoft.com/en-us/azure/templates/microsoft.app/agents?pivots=deployment-language-terraform#terraform-azapi-provider-resource-definition), [AzAPI `azapi_resource`](https://registry.terraform.io/providers/Azure/azapi/latest/docs/resources/resource).

## CRUD and deployment

Create or update:

```bash
az rest --method PUT \
  --url "${ARM_BASE}?api-version=${ARM_API_VERSION}" \
  --body @agent-arm-body.json
```

Read:

```bash
az rest --method GET \
  --url "${ARM_BASE}?api-version=${ARM_API_VERSION}" \
  -o json
```

Delete:

```bash
az rest --method DELETE \
  --url "${ARM_BASE}?api-version=${ARM_API_VERSION}"
```

Start/stop:

```bash
az rest --method POST --url "${ARM_BASE}/start?api-version=${ARM_API_VERSION}"
az rest --method POST --url "${ARM_BASE}/stop?api-version=${ARM_API_VERSION}"
```

Usage:

```bash
az rest --method GET --url "${ARM_BASE}/usages?api-version=${ARM_API_VERSION}"
az rest --method GET --url "${ARM_BASE}/dailyusages?api-version=${ARM_API_VERSION}"
```

Official sources: [API reference - Agent resource operations](https://learn.microsoft.com/en-us/azure/sre-agent/api-reference#agent-resource-operations), [Microsoft.App/agents ARM template reference](https://learn.microsoft.com/en-us/azure/templates/microsoft.app/agents?pivots=deployment-language-terraform).

# 2. `Microsoft.App/agents/connectors` e `/DataConnectors/{name}`

## Concrete description

A connector links Azure SRE Agent to a data source, an external system, or an operational endpoint. Documented examples: Azure Data Explorer/Kusto, Application Insights, Log Analytics, MCP, PagerDuty, ServiceNow, Outlook, and Teams. Without connectors, the agent can exist but has less operational context: it cannot query certain log/monitoring sources or use external integrations configured as connectors.

Important note: the 2026 ARM template reference documents `Microsoft.App/agents/connectors@2026-01-01`; the 2025 API reference uses the name `Microsoft.App/agents/DataConnectors` and the path `/DataConnectors/{name}`. These surfaces should be handled based on the API version and chosen deployment mechanism.

Official sources: [Microsoft.App/agents/connectors ARM template reference](https://learn.microsoft.com/en-us/azure/templates/microsoft.app/agents/connectors?pivots=deployment-language-terraform), [API reference - Sub-resources](https://learn.microsoft.com/en-us/azure/sre-agent/api-reference#sub-resources), [API reference - Connector types](https://learn.microsoft.com/en-us/azure/sre-agent/api-reference#connector-types).

## Parameters and possible values

| Parameter | Type | Required | What it is concretely | Technical impact | Documented possible values |
| --- | --- | --- | --- | --- | --- |
| `type` | string | Yes in AzAPI | ARM child type. | Selects the connector resource under the agent. | `Microsoft.App/agents/connectors@2026-01-01`. |
| `name` | string | Yes | Connector name under the agent. | Identifies the connection; used by agent/config and operators. | Pattern: `^[A-Za-z]([-A-Za-z0-9]{0,30}[A-Za-z0-9])$`. |
| `parent_id` | string | Yes | Parent `Microsoft.App/agents` resource ID. | Links the connector to the correct agent. | ARM resource ID of type `agents`. |
| `properties.dataConnectorType` | string | No in schema, functionally required | Connector type. | Determines behavior, authentication, and the queried source. | API reference: `Kusto`, `Mcp`, `Outlook`, `Teams`. The table also describes PagerDuty and ServiceNow as MCP. ARM schema says only `string`. For ARM `2026-01-01`, `Kusto` is validated as Azure Data Explorer and requires a Kusto HTTPS URI; use `LogAnalytics` or `AppInsights` when `dataSource` is an Azure resource ID. |
| `properties.dataSource` | string sensitive | No | Data source or connection string. | Indicates the cluster, workspace, endpoint, or resource ID. | String. No enum. Marked sensitive in the ARM reference. |
| `properties.endpoint` | string | No | Separate connector endpoint. | Useful when data source and endpoint are distinct. | String/URL. No enum. |
| `properties.extendedProperties` | object | No | Connector-specific extra properties. | Contains settings for MCP, partner, auth, or specific features. | Not formally documented by Microsoft as a complete schema. |
| `properties.identity` | string | No | Identity used to access the source. | Determines the permissions with which the connector queries the source. | String. API example uses `system`; in enterprise it can be a UAMI resource ID. |

### Technical meaning of documented `dataConnectorType` values

| Value | What it means | Technical implications |
| --- | --- | --- |
| `Kusto` | Azure Data Explorer/Kusto connector. | With ARM `2026-01-01`, `dataSource` must be an HTTPS URI in the format `https://cluster.kusto.windows.net/databasename`; do not use Log Analytics or Application Insights resource IDs with this value. |
| `Mcp` | Connector to a Model Context Protocol endpoint or integrations modeled as MCP. | The agent can call external tools exposed by MCP servers; endpoint, auth, and network allowlists are required. |
| `Outlook` | Connector for Outlook notifications/email. | Enables mail integrations, but the detailed payload schema is not published in the API reference. |
| `Teams` | Connector for Teams notifications/channels. | Enables Teams integrations, but the detailed payload schema is not published in the API reference. |

Additional values observed in official Microsoft templates as implementation evidence, not as a complete Learn enum: `AppInsights`, `LogAnalytics`, `AzureMonitor`, `MonitorClient`, `KnowledgeFile`, `KnowledgeText`, `KnowledgeWebPage`. In practice, for ARM `2026-01-01`, `LogAnalytics` and `AppInsights` are the correct values when `dataSource` is respectively the Log Analytics workspace resource ID or the Application Insights resource ID; `Kusto` is reserved for the Kusto URI form.

## Certified example: Terraform AzAPI

Format rationale: `Microsoft.App/agents/connectors@2026-01-01` is published in the Microsoft ARM template reference with Terraform AzAPI. The `/DataConnectors/{name}` path remains important for 2025 REST CRUD, but the primary IaC example should be AzAPI.

```hcl
resource "azapi_resource" "log_analytics_connector" {
  type      = "Microsoft.App/agents/connectors@2026-01-01"
  name      = "log-analytics-prod"
  parent_id = azapi_resource.agent.id

  body = {
    properties = {
      dataConnectorType = "LogAnalytics"
      dataSource        = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-contoso-sre-agent-dev/providers/Microsoft.OperationalInsights/workspaces/law-contoso-sre-agent-dev"
      identity          = "system"
    }
  }
}
```

Line-by-line explanation:

| Line/block | What it configures | Concrete impact |
| --- | --- | --- |
| `resource "azapi_resource" "log_analytics_connector"` | Terraform AzAPI resource. | Manages the ARM connector child resource. |
| `type = "Microsoft.App/agents/connectors@2026-01-01"` | ARM type and version. | Uses the resource documented in the Microsoft ARM template reference. |
| `name = "log-analytics-prod"` | Connector name. | Identifies the connection under the agent. |
| `parent_id = azapi_resource.agent.id` | Parent agent. | Links the connector to the `Microsoft.App/agents` resource. |
| `body.properties` | ARM properties of the connector. | Contains type, source, and identity. |
| `dataConnectorType = "LogAnalytics"` | Log Analytics connector type. | Uses the connector semantics appropriate for an Azure Log Analytics workspace. |
| `dataSource = "/subscriptions/.../workspaces/..."` | Workspace resource ID. | Determines which Log Analytics workspace the agent queries. |
| `identity = "system"` | Access identity. | Uses the format from the Microsoft API example; validate the UAMI resource ID if using UAMI. |

Official sources: [Microsoft.App/agents/connectors - Terraform AzAPI resource definition](https://learn.microsoft.com/en-us/azure/templates/microsoft.app/agents/connectors?pivots=deployment-language-terraform#terraform-azapi-provider-resource-definition), [AzAPI `azapi_resource`](https://registry.terraform.io/providers/Azure/azapi/latest/docs/resources/resource), [API reference - connector body format](https://learn.microsoft.com/en-us/azure/sre-agent/api-reference#sub-resource-body-formats).

## CRUD and deployment

Create or update with the 2025 control-plane:

```bash
az rest --method PUT \
  --url "${ARM_BASE}/DataConnectors/log-analytics-prod?api-version=${ARM_API_VERSION}" \
  --body @connector-log-analytics.json
```

Read:

```bash
az rest --method GET \
  --url "${ARM_BASE}/DataConnectors/log-analytics-prod?api-version=${ARM_API_VERSION}" \
  -o json
```

List:

```bash
az rest --method GET \
  --url "${ARM_BASE}/DataConnectors?api-version=${ARM_API_VERSION}" \
  -o json
```

Delete:

```bash
az rest --method DELETE \
  --url "${ARM_BASE}/DataConnectors/log-analytics-prod?api-version=${ARM_API_VERSION}"
```

# 3. Skill configuration: data-plane `extendedAgent/skills` with ARM child endpoint caveat

## Concrete description

A skill is a specialized capability or instruction that the agent or a subagent can use to perform a type of work. Microsoft Learn documents both the ARM child endpoint `/skills/{name}` with a Base64 `properties.value` envelope, and the data-plane `/api/v2/extendedAgent/skills/{name}`. In external tenants the ARM child endpoint has been validated as unusable: the service returns `Agent Extensions are not available for this tenant. This feature is restricted to internal tenants only.`. The operational path to use is therefore the data-plane `extendedAgent/skills`.

If a skill is misconfigured, the agent may use inconsistent instructions, unauthorized tools, or fail to select the correct capability during an investigation.

Official sources: [API reference - Sub-resources](https://learn.microsoft.com/en-us/azure/sre-agent/api-reference#sub-resources), [API reference - Extended agent configuration](https://learn.microsoft.com/en-us/azure/sre-agent/api-reference#extended-agent-configuration), [Deploy IaC - config directory](https://learn.microsoft.com/en-us/azure/sre-agent/deploy-iac#config-directory-structure), [microsoft/sre-agent issue 199](https://github.com/microsoft/sre-agent/issues/199), [microsoft/sre-agent PR 200](https://github.com/microsoft/sre-agent/pull/200).

## Parameters and possible values

| Parameter | Type | Required | What it is concretely | Technical impact | Documented possible values |
| --- | --- | --- | --- | --- | --- |
| `{name}` in path `/api/v2/extendedAgent/skills/{name}` | string | Yes | Data-plane skill name under the agent. | Uniquely identifies the skill. | String. Use stable names, typically kebab-case. |
| `name` in body | string | Yes | Logical skill name. | Must match the path to avoid ambiguity. | String. |
| `type` in body | string | Yes | ExtendedAgent object type. | Tells the service the payload represents a skill. | `Skill`. |
| `tags` in body | array | No | Logical data-plane tags. | Useful for future classification. | Array, often `[]`. |
| `properties.description` | string | No | Skill description. | Helps operators and agent routing. | String. |
| `properties.tools` | string[] | No | Allowed or associated tools. | Restricts the operational scope of the skill. | Tool names available in the agent. |
| `properties.skillContent` | string | Yes functionally | Skill Markdown instructions. | Determines the operational behavior of the skill. | Markdown string. |
| `properties.additionalFiles` | array | No | Additional files associated with the skill. | Provides supplementary context. | Array, often `[]`. |

## Certified example: YAML as source, data-plane as operational deployment

Format rationale: the Microsoft IaC guide indicates `config/skills/` as `Skill instructions (YAML + markdown)`. Updated Microsoft templates apply skills via the data-plane `PUT /api/v2/extendedAgent/skills/{name}` to avoid the ARM child endpoint restriction in external tenants.

File `config/skills/investigate-azure-alerts.yaml`:

```yaml
metadata:
  name: investigate-azure-alerts
  description: Investigate fired Azure Monitor alerts
spec:
  tools:
    - QueryLogAnalyticsByWorkspaceId
    - QueryAppInsightsUsingAppId
skillContent: |
  Use Azure Monitor alert context, query logs, summarize impact, and propose next action.
```

Data-plane body:

```json
{
  "name": "investigate-azure-alerts",
  "type": "Skill",
  "tags": [],
  "properties": {
    "name": "investigate-azure-alerts",
    "description": "Investigate fired Azure Monitor alerts",
    "tools": [
      "QueryLogAnalyticsByWorkspaceId",
      "QueryAppInsightsUsingAppId"
    ],
    "skillContent": "Use Azure Monitor alert context, query logs, summarize impact, and propose next action.",
    "additionalFiles": []
  }
}
```

Line-by-line explanation:

| Line/block | What it configures | Concrete impact |
| --- | --- | --- |
| `metadata.name` | Skill identifier. | Must be stable for references from subagents or allowed skills. |
| `metadata.description` | Skill description. | Helps operators and agentic routing. |
| `spec.tools` | Tools associated with the skill. | Restricts the operational scope of the skill. |
| `skillContent` | Skill Markdown instructions. | Influences the behavior and quality of the investigation. |
| `name` in body | Skill name. | Must match the data-plane `/skills/{name}` path. |
| `type = "Skill"` | extendedAgent type. | Indicates to the data-plane the configuration type. |
| `properties.name` | Internal skill name. | Replicates the name for service compatibility. |
| `properties.description` | Skill description. | Helps operators and agentic routing. |
| `properties.tools` | Tools associated with the skill. | Restricts the operational scope of the skill. |
| `properties.skillContent` | Skill Markdown instructions. | Influences the behavior and quality of the investigation. |
| `properties.additionalFiles` | Support files. | Adds any associated materials. |

Official sources: [Deploy IaC - config directory skills](https://learn.microsoft.com/en-us/azure/sre-agent/deploy-iac#config-directory-structure), [API reference - sub-resource body formats](https://learn.microsoft.com/en-us/azure/sre-agent/api-reference#sub-resource-body-formats), [AzAPI `azapi_resource`](https://registry.terraform.io/providers/Azure/azapi/latest/docs/resources/resource), [Terraform `file`](https://developer.hashicorp.com/terraform/language/functions/file), [Terraform `yamldecode`](https://developer.hashicorp.com/terraform/language/functions/yamldecode), [Terraform `jsonencode`](https://developer.hashicorp.com/terraform/language/functions/jsonencode), [Terraform `base64encode`](https://developer.hashicorp.com/terraform/language/functions/base64encode).

## CRUD and deployment

Create/update IaC:

```bash
terraform -chdir=04-terraform apply
```

Equivalent API create/update:

```bash
TOKEN=$(az account get-access-token --resource https://azuresre.dev --query accessToken -o tsv)
curl -fsS -X PUT \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  "${ENDPOINT}/api/v2/extendedAgent/skills/investigate-azure-alerts" \
  --data @skill-envelope.json
```

Read:

```bash
curl -fsS -H "Authorization: Bearer ${TOKEN}" \
  "${ENDPOINT}/api/v2/extendedAgent/skills/investigate-azure-alerts" | jq .
```

Delete:

```bash
curl -fsS -X DELETE -H "Authorization: Bearer ${TOKEN}" \
  "${ENDPOINT}/api/v2/extendedAgent/skills/investigate-azure-alerts"
```

# 4. Sub-resource ARM envelope caveat: `Microsoft.App/agents/subagents`

> Operational caveat: this and the following ARM envelope sections document Microsoft Learn control-plane paths, but live validation and the public Microsoft issue [microsoft/sre-agent#199](https://github.com/microsoft/sre-agent/issues/199) show that Agent Extension child endpoints are blocked for external tenants. For deployment in this repository, use the corresponding data-plane `extendedAgent` sections instead: subagents section 14, tools section 15, skills section 17, common prompts section 18, scheduled tasks section 19, and incident filters section 27.

## Concrete description

A subagent is a specialized agent that is subordinate to or callable by the main Azure SRE Agent. It serves to separate responsibilities: for example, a subagent for Azure Monitor alerts, one for Kubernetes, one for change analysis. In the ARM control-plane, the API reference documents the path and the Base64 envelope format, but does not publish the complete internal spec schema.

Concrete impact: a well-configured subagent reduces operational ambiguity and scopes tools/skills per domain; a poorly configured subagent may receive wrong handoffs, use inadequate tools, or generate inconsistent remediations.

Official sources: [API reference - Sub-resources](https://learn.microsoft.com/en-us/azure/sre-agent/api-reference#sub-resources), [API reference - Extended agent configuration](https://learn.microsoft.com/en-us/azure/sre-agent/api-reference#extended-agent-configuration), [Deploy IaC - config directory](https://learn.microsoft.com/en-us/azure/sre-agent/deploy-iac#config-directory-structure).

## Parameters and possible values

| Parameter | Type | Required | What it is | Technical impact | Documented possible values |
| --- | --- | --- | --- | --- | --- |
| `{name}` in path `/subagents/{name}` | string | Yes | Subagent name. | Identifies the specialist agent. | String. Pattern not published in the API reference. |
| `properties.value` | Base64 string | Yes | Encoded subagent spec. | Carries instructions, handoffs, tools, skills. | Base64 of valid JSON. Internal schema not formally documented by Microsoft. |
| Internal payload `metadata.name` | string | Depends on service schema | Logical name. | Used by handoff/routing. | Not formally documented by Microsoft. |
| Internal payload `spec.instructions` | string | Depends on service schema | Subagent instructions. | Determines subagent behavior. | Not formally documented by Microsoft. |
| Internal payload `spec.tools` | string[] | No | Available tools. | Limits what can be called. | Values depend on installed tools; no global enum published. |
| Internal payload `spec.allowedSkills` | string[] | No | Enabled skills. | Restricts usable skills. | Skill names. No enum. |
| Internal payload `spec.agentType` | string | No | Agentic behavior type. | Influences autonomy/role. | Not formally documented by Microsoft. Template examples may use values such as `Autonomous`. |
| Internal payload `spec.temperature` | number | No | Model sampling parameter. | Lower values make output more deterministic. | Range not formally documented by Microsoft for Azure SRE Agent. |

## Certified example: YAML as source, Terraform AzAPI as ARM deployment

Format rationale: the Microsoft IaC guide indicates `config/subagents/` as `Subagent definitions (YAML + markdown instructions)`. The ARM sub-resource `/subagents/{name}` remains deployable with a Base64 envelope via AzAPI.

File `config/subagents/alert-investigator.yaml`:

```yaml
metadata:
  name: alert-investigator
spec:
  instructions: |
    Investigate Azure Monitor alerts. Read evidence before proposing remediation.
  handoffDescription: Use for Azure Monitor fired alerts and log-based incident triage.
  tools:
    - QueryLogAnalyticsByWorkspaceId
  enableSkills: true
  allowedSkills:
    - investigate-azure-alerts
```

Terraform AzAPI envelope:

```hcl
resource "azapi_resource" "subagent_alert_investigator" {
  type      = "Microsoft.App/agents/subagents@2025-05-01-preview"
  name      = "alert-investigator"
  parent_id = azapi_resource.agent.id

  body = {
    properties = {
      value = base64encode(jsonencode(yamldecode(file("${path.module}/config/subagents/alert-investigator.yaml"))))
    }
  }

  schema_validation_enabled = false
}
```

Line-by-line explanation:

| Line/block | What it configures | Concrete impact |
| --- | --- | --- |
| `metadata.name` | Subagent name. | Becomes the reference for handoffs and incident handling. |
| `spec.instructions` | Operational prompt. | Establishes the subagent's behavior and limits. |
| `spec.handoffDescription` | Routing description. | Helps the main agent choose this subagent. |
| `spec.tools` | Allowed tools. | Reduces blast radius compared to giving all tools. |
| `spec.enableSkills` | Enable skills. | Allows the subagent to use skills. |
| `spec.allowedSkills` | Allowed skills. | Prevents use of out-of-domain skills. |
| `type = "Microsoft.App/agents/subagents@2025-05-01-preview"` | ARM subagent type. | Uses the documented control-plane path. |
| `value = base64encode(jsonencode(yamldecode(file(...))))` | YAML → JSON → Base64 conversion. | Produces the `properties.value` format required by ARM. |

Official sources: [Deploy IaC - config directory subagents](https://learn.microsoft.com/en-us/azure/sre-agent/deploy-iac#config-directory-structure), [API reference - sub-resources](https://learn.microsoft.com/en-us/azure/sre-agent/api-reference#sub-resources), [AzAPI `azapi_resource`](https://registry.terraform.io/providers/Azure/azapi/latest/docs/resources/resource).

## CRUD and deployment

```bash
terraform -chdir=04-terraform apply

az rest --method PUT \
  --url "${ARM_BASE}/subagents/alert-investigator?api-version=${ARM_API_VERSION}" \
  --body "{\"properties\":{\"value\":\"<base64-json-from-config/subagents/alert-investigator.yaml>\"}}"

az rest --method GET \
  --url "${ARM_BASE}/subagents/alert-investigator?api-version=${ARM_API_VERSION}"

az rest --method DELETE \
  --url "${ARM_BASE}/subagents/alert-investigator?api-version=${ARM_API_VERSION}"
```

# 5. Sub-resource ARM envelope caveat: `Microsoft.App/agents/tools`

## Concrete description

A tool is an invocable capability for the agent, such as a query, action, integration, or helper. In the ARM control-plane, Microsoft Learn documents the `/tools/{name}` path and the Base64 envelope format, but does not publish a complete schema for custom tools. This means IaC can transport the tool spec, but the real semantic validation happens on the service side.

Concrete impact: tools define what the agent can do. A read-only tool reduces risk; a write/remediation tool must be governed by RBAC, hooks, approvals, and auditing.

Official sources: [API reference - Sub-resources](https://learn.microsoft.com/en-us/azure/sre-agent/api-reference#sub-resources), [API reference - Sub-resource body formats](https://learn.microsoft.com/en-us/azure/sre-agent/api-reference#sub-resource-body-formats), [Deploy IaC - Phase 1 resources](https://learn.microsoft.com/en-us/azure/sre-agent/deploy-iac#phase-1-arm-infrastructure).

## Parameters and possible values

| Parameter | Type | Required | What it is | Technical impact | Documented possible values |
| --- | --- | --- | --- | --- | --- |
| `{name}` in path `/tools/{name}` | string | Yes | Tool name. | Identifies the invocable capability. | String. Pattern not published. |
| `properties.value` | Base64 string | Yes | Encoded tool spec. | Carries the tool definition. | Base64 of valid JSON. Internal schema not formally documented by Microsoft. |
| Internal payload `description` | string | No | Tool description. | Helps agent and operators understand purpose. | Not formally documented by Microsoft. |
| Internal payload `access` | string | No | Access classification. | Can distinguish read-only vs. mutating actions if the schema supports it. | Not formally documented by Microsoft. |

## Certified example: JSON object, Terraform AzAPI as ARM deployment

Format rationale: Microsoft Learn cites `tools` as an ARM sub-resource and the IaC guide includes them among Phase 1 ARM configurations; it does not publish a specific YAML directory for tools in the official structure. Therefore the example uses a JSON/HCL object and AzAPI for ARM deployment.

```hcl
resource "azapi_resource" "tool_azure_resource_graph_readonly" {
  type      = "Microsoft.App/agents/tools@2025-05-01-preview"
  name      = "azure-resource-graph-readonly"
  parent_id = azapi_resource.agent.id

  body = {
    properties = {
      value = base64encode(jsonencode({
        name        = "azure-resource-graph-readonly"
        description = "Query Azure Resource Graph in read-only mode"
        properties = {
          access = "read_only"
        }
      }))
    }
  }

  schema_validation_enabled = false
}
```

Line-by-line explanation:

| Line/block | What it configures | Concrete impact |
| --- | --- | --- |
| `type = "Microsoft.App/agents/tools@2025-05-01-preview"` | ARM tool sub-resource type. | Uses the `/tools/{name}` path documented by the API reference. |
| `name = "azure-resource-graph-readonly"` | Tool name. | Used to reference it from skills/subagents. |
| `parent_id = azapi_resource.agent.id` | Parent agent. | Links the tool to the correct agent. |
| `base64encode(jsonencode({ ... }))` | ARM envelope. | Produces `properties.value`, as required by Microsoft Learn. |
| `description = ...` | Tool purpose. | Reduces ambiguity in tool selection. |
| `access = "read_only"` | Read-only intent. | Operational example; not an official enum published in the API reference. |
| `schema_validation_enabled = false` | Disables embedded AzAPI schema. | Useful for sub-resources without a published AzAPI schema. |

Official sources: [API reference - sub-resource body formats](https://learn.microsoft.com/en-us/azure/sre-agent/api-reference#sub-resource-body-formats), [Deploy IaC - Phase 1 ARM infrastructure](https://learn.microsoft.com/en-us/azure/sre-agent/deploy-iac#phase-1-arm-infrastructure), [AzAPI `azapi_resource`](https://registry.terraform.io/providers/Azure/azapi/latest/docs/resources/resource), [Terraform `jsonencode`](https://developer.hashicorp.com/terraform/language/functions/jsonencode), [Terraform `base64encode`](https://developer.hashicorp.com/terraform/language/functions/base64encode).

## CRUD and deployment

```bash
terraform -chdir=04-terraform apply

az rest --method PUT --url "${ARM_BASE}/tools/azure-resource-graph-readonly?api-version=${ARM_API_VERSION}" --body "{\"properties\":{\"value\":\"<base64-json-tool-spec>\"}}"
az rest --method GET --url "${ARM_BASE}/tools/azure-resource-graph-readonly?api-version=${ARM_API_VERSION}"
az rest --method DELETE --url "${ARM_BASE}/tools/azure-resource-graph-readonly?api-version=${ARM_API_VERSION}"
```

# 6. Sub-resource ARM envelope caveat: `Microsoft.App/agents/scheduledTasks`

## Concrete description

A scheduled task is a recurring automation for the agent. It is used for periodic runbooks, health checks, compliance checks, reports, or scheduled incident reviews. Microsoft Learn lists it both as an ARM sub-resource (`/scheduledTasks/{name}`) and as extended data-plane configuration (`/api/v2/extendedAgent/scheduledtasks/{name}`). The IaC guide states that deployment occurs in two phases and that some configurations not yet managed by ARM are applied via the data-plane.

Concrete impact: a scheduled task consumes active-flow AAU when it runs. An incorrect cron expression can generate costs and operational noise; an overly broad prompt can consume many tokens.

Official sources: [API reference - Sub-resources](https://learn.microsoft.com/en-us/azure/sre-agent/api-reference#sub-resources), [API reference - Extended agent configuration](https://learn.microsoft.com/en-us/azure/sre-agent/api-reference#extended-agent-configuration), [Deploy IaC - Phase 2 data plane](https://learn.microsoft.com/en-us/azure/sre-agent/deploy-iac#phase-2-data-plane-config-that-arm-cant-handle-yet), [Pricing - active flow](https://learn.microsoft.com/en-us/azure/sre-agent/pricing-billing#active-flow-variable-cost).

## Parameters and possible values

| Parameter | Type | Required | What it is | Technical impact | Documented possible values |
| --- | --- | --- | --- | --- | --- |
| `{name}` in path `/scheduledTasks/{name}` | string | Yes | Task name. | Identifies the automation. | String. Pattern not published. |
| `properties.value` | Base64 string | Yes for ARM envelope | Encoded task spec. | Carries schedule, prompt, and enablement. | Base64 JSON. Internal schema not formally documented by Microsoft. |
| `schedule` / `cronExpression` | string | Functional | Recurrence expression. | Defines when the task starts. | Not formally documented by Microsoft; template examples use 5-field cron. |
| `prompt` / `agentPrompt` | string | Functional | Work requested of the agent. | Determines tokens, tools, and result. | String. No enum. |
| `enabled` / `isEnabled` | boolean | No | Enablement flag. | If `false`, the task remains configured but does not run. | `true`, `false`. |
| `mode` / `agentMode` | string | No | Execution mode. | Influences review/autonomy. | Not formally documented for scheduled tasks; use values aligned with action mode and validate. |

## Certified example: YAML as source, Terraform AzAPI as ARM deployment

Format rationale: the Microsoft IaC guide places recurring automations in `automations/scheduled-tasks/`. The API reference also exposes the ARM sub-resource `/scheduledTasks/{name}` with a Base64 envelope.

File `automations/scheduled-tasks/daily-health-check.yaml`:

```yaml
metadata:
  name: daily-health-check
spec:
  description: Daily production health summary
  schedule: "0 8 * * *"
  prompt: Summarize incidents, failed deployments, and critical alerts from the last 24 hours.
  enabled: true
  mode: Review
```

Terraform AzAPI envelope:

```hcl
resource "azapi_resource" "scheduled_task_daily_health_check" {
  type      = "Microsoft.App/agents/scheduledTasks@2025-05-01-preview"
  name      = "daily-health-check"
  parent_id = azapi_resource.agent.id

  body = {
    properties = {
      value = base64encode(jsonencode(yamldecode(file("${path.module}/automations/scheduled-tasks/daily-health-check.yaml"))))
    }
  }

  schema_validation_enabled = false
}
```

Line-by-line explanation:

| Line/block | What it configures | Concrete impact |
| --- | --- | --- |
| `metadata.name` | Task name. | Used to update/delete the automation. |
| `spec.description` | Operational description. | Clarifies why the task exists. |
| `spec.schedule` | Daily cron at 08:00. | Runs once a day; timezone not formally documented in the API reference. |
| `spec.prompt` | Task prompt. | Determines the work performed and the AAU consumption. |
| `spec.enabled` | Task active. | Allows recurring execution. |
| `spec.mode` | Review mode. | Reduces risk of unreviewed automatic actions. |
| `type = "Microsoft.App/agents/scheduledTasks@2025-05-01-preview"` | Tipo ARM scheduled task. | Usa la sub-resource ufficiale documentata. |
| `value = base64encode(jsonencode(yamldecode(file(...))))` | YAML → JSON → Base64 conversion. | Produces the `properties.value` format. |

Official sources: [Deploy IaC - scheduled tasks directory](https://learn.microsoft.com/en-us/azure/sre-agent/deploy-iac#config-directory-structure), [API reference - sub-resources](https://learn.microsoft.com/en-us/azure/sre-agent/api-reference#sub-resources), [AzAPI `azapi_resource`](https://registry.terraform.io/providers/Azure/azapi/latest/docs/resources/resource).

## CRUD and deployment

Control-plane ARM envelope:

```bash
terraform -chdir=04-terraform apply

az rest --method PUT --url "${ARM_BASE}/scheduledTasks/daily-health-check?api-version=${ARM_API_VERSION}" --body "{\"properties\":{\"value\":\"<base64-json-from-automations/scheduled-tasks/daily-health-check.yaml>\"}}"
az rest --method GET --url "${ARM_BASE}/scheduledTasks/daily-health-check?api-version=${ARM_API_VERSION}"
az rest --method DELETE --url "${ARM_BASE}/scheduledTasks/daily-health-check?api-version=${ARM_API_VERSION}"
```

Data-plane extended configuration:

```bash
curl -fsS -X PUT \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  "${ENDPOINT}/api/v2/extendedAgent/scheduledtasks/daily-health-check" \
  --data @scheduled-task.json
```

# 7. Sub-resource ARM envelope caveat: `Microsoft.App/agents/incidentFilters`

## Concrete description

An incident filter selects which incidents or alerts should be handled by the agent and how. It is the basis for response plans, routing by severity, platform, service, or priority. Microsoft Learn documents the ARM sub-resource `/incidentFilters/{name}` but does not publish the complete internal payload schema; the official templates contain additional examples for response plans/data-plane.

Concrete impact: overly broad filters trigger unnecessary investigations and consume AAU; overly narrow filters may miss critical incidents.

Official sources: [API reference - Sub-resources](https://learn.microsoft.com/en-us/azure/sre-agent/api-reference#sub-resources), [Pricing - cost optimization tips](https://learn.microsoft.com/en-us/azure/sre-agent/pricing-billing#cost-optimization-tips), [Deploy IaC - config directory](https://learn.microsoft.com/en-us/azure/sre-agent/deploy-iac#config-directory-structure), [microsoft/sre-agent templates](https://github.com/microsoft/sre-agent/tree/main/sreagent-templates).

## Parameters and possible values

| Parameter | Type | Required | What it is | Technical impact | Documented possible values |
| --- | --- | --- | --- | --- | --- |
| `{name}` in path `/incidentFilters/{name}` | string | Yes | Filter name. | Identifies the incident routing rule. | String. Pattern not published. |
| `properties.value` | Base64 string | Yes for ARM envelope | Encoded filter spec. | Carries rules and routing. | Base64 JSON. Internal schema not formally documented by Microsoft. |
| `incidentPlatform` | string | Functional | Incident platform. | Selects the incident source to filter. | Documented root values: `AzMonitor`, `PagerDuty`, `ServiceNow`, `None`. No published enum for specific filters. |
| `isEnabled` | boolean | No | Enablement flag. | Activates/deactivates the filter. | `true`, `false`. |
| `priorities` | string[] | No | Included priorities/severities. | Determines which incidents trigger the plan. | Not formally documented by Microsoft; values depend on the platform, e.g. `Sev0`, `Sev1`, `P1`, `P2` in templates/examples. |
| `handlingAgent` | string | No | Subagent handler. | Routes to a specialist agent. | Subagent name. No enum. |
| `agentMode` | string | No | Agent mode in the plan. | Defines review/autonomy of the response plan. | Not formally documented by Microsoft for this schema. |

## Certified example: YAML as source, Terraform AzAPI as ARM deployment

Format rationale: the Microsoft IaC guide places incident routing rules in `automations/incident-filters/`; the API reference also exposes the ARM sub-resource `/incidentFilters/{name}`.

File `automations/incident-filters/azmon-sev0-sev1.yaml`:

```yaml
metadata:
  name: azmon-sev0-sev1
spec:
  incidentPlatform: AzMonitor
  isEnabled: true
  priorities:
    - Sev0
    - Sev1
  handlingAgent: alert-investigator
  agentMode: Review
  deepInvestigationEnabled: true
  maxAutomatedInvestigationAttempts: 2
```

Terraform AzAPI envelope:

```hcl
resource "azapi_resource" "incident_filter_azmon_sev0_sev1" {
  type      = "Microsoft.App/agents/incidentFilters@2025-05-01-preview"
  name      = "azmon-sev0-sev1"
  parent_id = azapi_resource.agent.id

  body = {
    properties = {
      value = base64encode(jsonencode(yamldecode(file("${path.module}/automations/incident-filters/azmon-sev0-sev1.yaml"))))
    }
  }

  schema_validation_enabled = false
}
```

Line-by-line explanation:

| Line/block | What it configures | Concrete impact |
| --- | --- | --- |
| `metadata.name` | Filter name. | Identifies the plan for high severities. |
| `spec.incidentPlatform` | Azure Monitor source. | Applies the filter to Azure Monitor alerts/incidents. |
| `spec.isEnabled` | Filter active. | The rule can trigger investigations. |
| `spec.priorities` | High severities only. | Reduces noise and cost for non-critical incidents. |
| `spec.handlingAgent` | Responsible subagent. | Routes to the relevant specialist. |
| `spec.agentMode` | Review mode. | Reduces the risk of autonomous remediation. |
| `spec.deepInvestigationEnabled` | Deep investigation. | More context and possible tool calls; potentially higher AAU consumption. |
| `spec.maxAutomatedInvestigationAttempts` | Attempt limit. | Avoids loops or excessive retries. |
| `type = "Microsoft.App/agents/incidentFilters@2025-05-01-preview"` | ARM incident filter type. | Uses the officially documented sub-resource. |
| `value = base64encode(jsonencode(yamldecode(file(...))))` | YAML → JSON → Base64 conversion. | Produces the `properties.value` format. |

Official sources: [Deploy IaC - incident filters directory](https://learn.microsoft.com/en-us/azure/sre-agent/deploy-iac#config-directory-structure), [API reference - sub-resources](https://learn.microsoft.com/en-us/azure/sre-agent/api-reference#sub-resources), [AzAPI `azapi_resource`](https://registry.terraform.io/providers/Azure/azapi/latest/docs/resources/resource).

## CRUD and deployment

```bash
terraform -chdir=04-terraform apply

az rest --method PUT --url "${ARM_BASE}/incidentFilters/azmon-sev0-sev1?api-version=${ARM_API_VERSION}" --body "{\"properties\":{\"value\":\"<base64-json-from-automations/incident-filters/azmon-sev0-sev1.yaml>\"}}"
az rest --method GET --url "${ARM_BASE}/incidentFilters/azmon-sev0-sev1?api-version=${ARM_API_VERSION}"
az rest --method DELETE --url "${ARM_BASE}/incidentFilters/azmon-sev0-sev1?api-version=${ARM_API_VERSION}"
```

# 8. Sub-resource ARM envelope caveat: `Microsoft.App/agents/hooks`

## Concrete description

A hook is a governance control that intercepts agent events or actions, for example before a tool is used. It is used to enforce policies, blocks, security rules, or reviews. Microsoft Learn lists `/hooks/{name}` as an ARM sub-resource, but the IaC guide also states that hooks are Phase 2 data-plane when ARM cannot yet handle them at deploy time.

Concrete impact: hooks are a security barrier. If omitted, the agent relies only on prompts, RBAC, and approvals. If misconfigured, they can block legitimate actions or allow dangerous ones.

Official sources: [API reference - Sub-resources](https://learn.microsoft.com/en-us/azure/sre-agent/api-reference#sub-resources), [API reference - Hooks data plane](https://learn.microsoft.com/en-us/azure/sre-agent/api-reference#hooks), [Deploy IaC - Phase 2 data plane](https://learn.microsoft.com/en-us/azure/sre-agent/deploy-iac#phase-2-data-plane-config-that-arm-cant-handle-yet).

## Parameters and possible values

| Parameter | Type | Required | What it is | Technical impact | Documented possible values |
| --- | --- | --- | --- | --- | --- |
| `{name}` in path `/hooks/{name}` | string | Yes | Hook name. | Identifies the hook policy. | String. Pattern not published. |
| `properties.value` | Base64 string | Yes for ARM envelope | Encoded hook spec. | Carries the rule/policy. | Base64 JSON. Internal schema not formally documented by Microsoft. |
| `eventType` | string | Functional | Intercepted event. | Decides when the control is triggered. | Not formally documented by Microsoft; template examples may use `PreToolUse`. |
| `hook.type` | string | Functional | Hook implementation type. | Decides how to evaluate the policy. | Not formally documented by Microsoft; template examples may use `prompt`. |
| `permissionDecision` | string | Functional | Decision or default decision. | Can allow or deny actions. | Not formally documented by Microsoft; template examples may use `allow`, `deny`. |
| `enabled` | boolean | No | Hook enablement. | Activates/deactivates the policy. | `true`, `false`. |

## Certified example: YAML as source, Terraform AzAPI or data-plane as deployment

Format rationale: the Microsoft IaC guide indicates `config/hooks/` as `Safety guardrails (YAML)` and states that hooks are Phase 2 data-plane when ARM does not handle them at deploy time. The API reference also exposes `/hooks/{name}` as an ARM sub-resource envelope.

File `config/hooks/deny-production-delete.yaml`:

```yaml
metadata:
  name: deny-production-delete
spec:
  eventType: PreToolUse
  hook:
    type: prompt
    matcher: ".*delete.*|.*remove.*"
    prompt: Deny destructive actions against production resources unless an explicit human approval is present.
  permissionDecision: deny
  enabled: true
```

Terraform AzAPI envelope, only if the ARM path is chosen:

```hcl
resource "azapi_resource" "hook_deny_production_delete" {
  type      = "Microsoft.App/agents/hooks@2025-05-01-preview"
  name      = "deny-production-delete"
  parent_id = azapi_resource.agent.id

  body = {
    properties = {
      value = base64encode(jsonencode(yamldecode(file("${path.module}/config/hooks/deny-production-delete.yaml"))))
    }
  }

  schema_validation_enabled = false
}
```

Line-by-line explanation:

| Line/block | What it configures | Concrete impact |
| --- | --- | --- |
| `metadata.name` | Hook name. | Makes the policy updatable and auditable. |
| `spec.eventType` | Event before the tool. | Intercepts the action before execution. |
| `spec.hook.type` | Prompt-based hook. | Uses a textual instruction/policy to evaluate. |
| `spec.hook.matcher` | Destructive action regex. | Applies the control to matching tools/actions. |
| `spec.hook.prompt` | Natural-language policy. | Defines what to block and when. |
| `spec.permissionDecision` | Deny decision. | Blocks if the policy is triggered. |
| `spec.enabled` | Hook active. | The policy enters the runtime. |
| `type = "Microsoft.App/agents/hooks@2025-05-01-preview"` | ARM hook type. | Uses the officially documented sub-resource. |
| `value = base64encode(jsonencode(yamldecode(file(...))))` | YAML → JSON → Base64 conversion. | Produces the `properties.value` format. |

Official sources: [Deploy IaC - hooks YAML and Phase 2](https://learn.microsoft.com/en-us/azure/sre-agent/deploy-iac#phase-2-data-plane-config-that-arm-cant-handle-yet), [Deploy IaC - config directory hooks](https://learn.microsoft.com/en-us/azure/sre-agent/deploy-iac#config-directory-structure), [API reference - hooks](https://learn.microsoft.com/en-us/azure/sre-agent/api-reference#hooks), [AzAPI `azapi_resource`](https://registry.terraform.io/providers/Azure/azapi/latest/docs/resources/resource).

## CRUD and deployment

Control-plane ARM:

```bash
terraform -chdir=04-terraform apply

az rest --method PUT --url "${ARM_BASE}/hooks/deny-production-delete?api-version=${ARM_API_VERSION}" --body "{\"properties\":{\"value\":\"<base64-json-from-config/hooks/deny-production-delete.yaml>\"}}"
az rest --method GET --url "${ARM_BASE}/hooks/deny-production-delete?api-version=${ARM_API_VERSION}"
az rest --method DELETE --url "${ARM_BASE}/hooks/deny-production-delete?api-version=${ARM_API_VERSION}"
```

Official data-plane via Microsoft templates, where the source file remains YAML and the Phase 2 script applies the configuration:

```bash
./bin/deploy.sh my-agent/
```

Equivalent raw data-plane API, only after converting the YAML to JSON compatible with the live schema:

```bash
curl -fsS -X PUT \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  "${ENDPOINT}/api/v2/extendedAgent/hooks/deny-production-delete" \
  --data @hook.json
```

# 9. Sub-resource ARM envelope caveat: `Microsoft.App/agents/commonPrompts`

## Concrete description

A common prompt is a reusable instruction fragment. It is used for common rules, tone, operational policies, RCA criteria, or reporting standards that multiple skills/subagents must share. In the ARM control-plane it uses the same Base64 envelope; in the extended data-plane it has the path `/api/v2/extendedAgent/commonprompts/{name}`.

Concrete impact: centralizes repeated instructions. If a common prompt contains incorrect policies, the error can propagate to multiple agentic flows.

Official sources: [API reference - Sub-resources](https://learn.microsoft.com/en-us/azure/sre-agent/api-reference#sub-resources), [API reference - Extended agent configuration](https://learn.microsoft.com/en-us/azure/sre-agent/api-reference#extended-agent-configuration), [Deploy IaC - config directory](https://learn.microsoft.com/en-us/azure/sre-agent/deploy-iac#config-directory-structure).

## Parameters and possible values

| Parameter | Type | Required | What it is | Technical impact | Documented possible values |
| --- | --- | --- | --- | --- | --- |
| `{name}` in path `/commonPrompts/{name}` | string | Yes | Common prompt name. | Identifies the reusable block. | String. Pattern not published. |
| `properties.value` | Base64 string | Yes for ARM envelope | Encoded prompt spec. | Carries content and metadata. | Base64 JSON. Internal schema not formally documented by Microsoft. |
| `prompt` / `content` | string | Functional | Prompt text. | Influences the behavior of agents/subagents/skills that include it. | Markdown/text string. No enum. |

## Certified example: YAML as source, Terraform AzAPI as ARM deployment

Format rationale: the Microsoft IaC guide indicates `config/common-prompts/` as the directory for shared prompt instructions. The API reference exposes `/commonPrompts/{name}` as an ARM sub-resource envelope.

File `config/common-prompts/production-safety-rules.yaml`:

```yaml
metadata:
  name: production-safety-rules
spec:
  prompt: Never perform destructive production changes without explicit human approval and an attached incident or change ID.
```

Terraform AzAPI envelope:

```hcl
resource "azapi_resource" "common_prompt_production_safety_rules" {
  type      = "Microsoft.App/agents/commonPrompts@2025-05-01-preview"
  name      = "production-safety-rules"
  parent_id = azapi_resource.agent.id

  body = {
    properties = {
      value = base64encode(jsonencode(yamldecode(file("${path.module}/config/common-prompts/production-safety-rules.yaml"))))
    }
  }

  schema_validation_enabled = false
}
```

Line-by-line explanation:

| Line/block | What it configures | Concrete impact |
| --- | --- | --- |
| `metadata.name` | Prompt name. | Makes the prompt referenceable. |
| `spec.prompt` | Common instruction. | Enforces a cross-cutting rule for agents that use it. |
| `type = "Microsoft.App/agents/commonPrompts@2025-05-01-preview"` | ARM common prompt type. | Uses the officially documented sub-resource. |
| `value = base64encode(jsonencode(yamldecode(file(...))))` | YAML → JSON → Base64 conversion. | Produces the `properties.value` format. |

Official sources: [Deploy IaC - common prompts directory](https://learn.microsoft.com/en-us/azure/sre-agent/deploy-iac#config-directory-structure), [API reference - sub-resources](https://learn.microsoft.com/en-us/azure/sre-agent/api-reference#sub-resources), [AzAPI `azapi_resource`](https://registry.terraform.io/providers/Azure/azapi/latest/docs/resources/resource).

## CRUD and deployment

```bash
terraform -chdir=04-terraform apply

az rest --method PUT --url "${ARM_BASE}/commonPrompts/production-safety-rules?api-version=${ARM_API_VERSION}" --body "{\"properties\":{\"value\":\"<base64-json-from-config/common-prompts/production-safety-rules.yaml>\"}}"
az rest --method GET --url "${ARM_BASE}/commonPrompts/production-safety-rules?api-version=${ARM_API_VERSION}"
az rest --method DELETE --url "${ARM_BASE}/commonPrompts/production-safety-rules?api-version=${ARM_API_VERSION}"
```

# 10. Code repositories - `/api/v2/repos/{repoName}`

## Concrete description

The data-plane repository resource links source code to the agent. It allows the agent to understand project structure, deployment configuration, application patterns, and technical context. Microsoft Learn documents repo operations and the setup guide indicates GitHub and Azure DevOps as supported providers in the UI experience.

Concrete impact: without a repo, the agent can troubleshoot metrics/logs but has less context on code, deployment, and runbooks. With the wrong repo or wrong branch, the agent may reason about code that does not correspond to production.

Official sources: [API reference - Code repos](https://learn.microsoft.com/en-us/azure/sre-agent/api-reference#code-repos), [API reference - Add a code repo via data plane](https://learn.microsoft.com/en-us/azure/sre-agent/api-reference#add-a-code-repo-via-data-plane), [Create and set up - Connect your code repository](https://learn.microsoft.com/en-us/azure/sre-agent/create-and-set-up#connect-your-code-repository).

## Parameters and possible values

| Parameter | Type | Required | What it is | Technical impact | Documented possible values |
| --- | --- | --- | --- | --- | --- |
| `{repoName}` | string | Yes | Data-plane name of the repo connection. | Identifies the connection to update/test/delete. | String. Pattern not published. |
| `properties.url` | string URL | Yes in API example | Repository URL. | The code source indexed/analyzed by the agent. | GitHub or Azure DevOps URL per setup; exact URL schema not formally published. |
| `properties.type` | string | Yes in API example | Repo provider type. | Selects provider auth and integration. | API example: `GitHub`. Setup says Azure DevOps is supported, but the exact payload value is not formally documented in the API reference. |
| `properties.branch` | string | No | Default branch. | Aligns code context to the environment. | Branch string, e.g. `main`. No enum. |
| Auth/PAT/OAuth fields | object/string | Depends on method | Credentials or auth flow. | Required for private repos. | Not formally documented by Microsoft in the API reference; UI supports `Auth` and `PAT`. |

## Certified example: JSON + curl

```json
{
  "properties": {
    "url": "https://github.com/contoso/payments-api",
    "type": "GitHub",
    "branch": "main"
  }
}
```

Line-by-line explanation:

| Line/block | What it configures | Concrete impact |
| --- | --- | --- |
| `"properties"` | Repo config. | Contains URL, provider, and branch. |
| `"url": "https://github.com/..."` | Source repository. | The agent will use that code as context. |
| `"type": "GitHub"` | GitHub provider. | Uses the GitHub integration documented in the API example. |
| `"branch": "main"` | Main branch. | Avoids analysis on a non-production branch. |

## CRUD and deployment

Create/update:

```bash
curl -fsS -X PUT \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  "${ENDPOINT}/api/v2/repos/payments-api" \
  --data @repo.json
```

List/read/test/delete:

```bash
curl -fsS -H "Authorization: Bearer ${TOKEN}" "${ENDPOINT}/api/v2/repos"
curl -fsS -H "Authorization: Bearer ${TOKEN}" "${ENDPOINT}/api/v2/repos/payments-api"
curl -fsS -X POST -H "Authorization: Bearer ${TOKEN}" "${ENDPOINT}/api/v2/repos/payments-api/test"
curl -fsS -X DELETE -H "Authorization: Bearer ${TOKEN}" "${ENDPOINT}/api/v2/repos/payments-api"
```

# 11. Knowledge / agent memory - `/api/v1/agentmemory/*`

## Concrete description

Knowledge, or agent memory, is the data-plane surface for loading documents, runbooks, reference material, and textual knowledge into the agent. It is used to provide stable context not necessarily present in logs or code: operational runbooks, architectures, escalation matrices, postmortems, SOPs.

Concrete impact: good knowledge reduces wasted tokens and improves response quality; outdated or incorrect knowledge can guide incorrect remediations. The pricing page cites adding context as a cost optimization to reduce unnecessary tokens.

Official sources: [API reference - Knowledge](https://learn.microsoft.com/en-us/azure/sre-agent/api-reference#knowledge-agent-memory), [Deploy IaC - config directory data/knowledge](https://learn.microsoft.com/en-us/azure/sre-agent/deploy-iac#config-directory-structure), [Pricing - cost optimization tips](https://learn.microsoft.com/en-us/azure/sre-agent/pricing-billing#cost-optimization-tips).

## Parameters and possible values

| Parameter/surface | Type | Required | What it is | Technical impact | Documented possible values |
| --- | --- | --- | --- | --- | --- |
| Multipart `files=@...` | file upload | Yes for upload | File to upload. | Adds content to the agent memory. | Official limits: max 100 MB total, 16 MB per file. Specific formats not listed in the API reference. |
| `{fileName}` in `/document/{fileName}` | string URL-encoded | Yes for single delete | File name to delete. | Removes a document from memory. | File name string. No enum. |
| `/documents` | collection endpoint | Yes for bulk delete | Bulk document deletion. | Removes knowledge in bulk. | No payload schema published in the Learn table. |
| `/status` | endpoint read | No | Memory state. | Verifies memory availability/health. | Read-only response schema not detailed in the table. |
| `/indexer-status` | endpoint read | No | Indexing state. | Verifies whether documents have been indexed. | Read-only response schema not detailed in the table. |

## Esempio deploy/upload

```bash
curl -fsS -X POST \
  -H "Authorization: Bearer ${TOKEN}" \
  -F "files=@documentation/runbook-payment-outage.md" \
  "${ENDPOINT}/api/v1/agentmemory/upload"
```

Line-by-line explanation:

| Line | What it configures | Concrete impact |
| --- | --- | --- |
| `curl -fsS -X POST` | Upload call. | Creates/adds a knowledge document. |
| `Authorization: Bearer ${TOKEN}` | Token data-plane. | Necessario per endpoint autenticato. |
| `-F "files=@..."` | Multipart file upload. | Uploads the runbook as agent knowledge. |
| `${ENDPOINT}/api/v1/agentmemory/upload` | Upload endpoint. | Official surface for agent memory. |

## CRUD and operations

Upload:

```bash
curl -fsS -X POST -H "Authorization: Bearer ${TOKEN}" -F "files=@documentation/runbook-payment-outage.md" "${ENDPOINT}/api/v1/agentmemory/upload"
```

Status:

```bash
curl -fsS -H "Authorization: Bearer ${TOKEN}" "${ENDPOINT}/api/v1/agentmemory/status"
curl -fsS -H "Authorization: Bearer ${TOKEN}" "${ENDPOINT}/api/v1/agentmemory/indexer-status"
```

Delete:

```bash
curl -fsS -X DELETE -H "Authorization: Bearer ${TOKEN}" "${ENDPOINT}/api/v1/agentmemory/document/runbook-payment-outage.md"
curl -fsS -X DELETE -H "Authorization: Bearer ${TOKEN}" "${ENDPOINT}/api/v1/agentmemory/documents"
```

# 12. HTTP triggers - `/api/v1/httptriggers/*`

## Concrete description

HTTP triggers are data-plane endpoints that allow creating triggers invocable via HTTP. They are used for webhooks, external integrations, or automations that activate the agent from systems not natively integrated. Microsoft Learn publishes the operations, but does not publish the complete JSON Schema for the creation payload.

Concrete impact: the public webhook endpoint `/api/v1/httptriggers/trigger/{triggerId}` is documented as requiring no auth. This is useful for webhook integrations, but increases the importance of secrets, payload tokens, allowlists, source validation, and application-level rate limiting.

Official sources: [API reference - HTTP triggers](https://learn.microsoft.com/en-us/azure/sre-agent/api-reference#http-triggers), [Deploy IaC - Phase 2 data plane](https://learn.microsoft.com/en-us/azure/sre-agent/deploy-iac#phase-2-data-plane-config-that-arm-cant-handle-yet).

## Parameters and possible values

| Parameter/surface | Type | Required | What it is | Technical impact | Documented possible values |
| --- | --- | --- | --- | --- | --- |
| Create payload | object | Yes for create | Trigger definition. | Determines name, prompt, binding, and behavior. | Not formally documented by Microsoft. |
| `{triggerId}` | string | Yes for execute/public webhook | Service-generated trigger identifier. | Selects the trigger to execute. | String generated/returned by the service; format not documented. |
| Public webhook payload | object | Depends on trigger | External input. | Can trigger agentic work. | Not formally documented by Microsoft. |

## Certified example: JSON + curl

Because Microsoft Learn does not publish the create schema, this example is intentionally minimal and must be validated live.

```json
{
  "name": "external-alert-webhook",
  "prompt": "Investigate the incoming external alert payload and summarize impact before suggesting action.",
  "enabled": true
}
```

Line-by-line explanation:

| Line/block | What it configures | Concrete impact |
| --- | --- | --- |
| `"name"` | Proposed trigger name. | Identifies the webhook purpose. Not a guaranteed official schema. |
| `"prompt"` | Work requested of the agent. | Defines how to interpret the external payload. |
| `"enabled": true` | Trigger active. | Allows execution after creation. |

## CRUD and deployment

Create:

```bash
curl -fsS -X POST \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  "${ENDPOINT}/api/v1/httptriggers/create" \
  --data @http-trigger.json
```

List:

```bash
curl -fsS -H "Authorization: Bearer ${TOKEN}" "${ENDPOINT}/api/v1/httptriggers"
```

Authenticated execute:

```bash
curl -fsS -X POST \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  "${ENDPOINT}/api/v1/httptriggers/${TRIGGER_ID}/execute" \
  --data @trigger-input.json
```

Documented public webhook without auth:

```bash
curl -fsS -X POST \
  -H "Content-Type: application/json" \
  "${ENDPOINT}/api/v1/httptriggers/trigger/${TRIGGER_ID}" \
  --data @webhook-payload.json
```

# 13. Extended hooks - `/api/v2/extendedAgent/hooks/{hookName}`

## Concrete description

Extended hooks is the official data-plane surface for managing hooks when the ARM sub-resource envelope is not used or is insufficient. The IaC guide explicitly states that hooks are among the Phase 2 data-plane configs that ARM does not yet handle at deploy time.

Concrete impact: this is the path most consistent with the IaC guide for applying hooks post-deployment. Requires a data-plane endpoint and an `https://azuresre.dev` token.

Official sources: [API reference - Hooks](https://learn.microsoft.com/en-us/azure/sre-agent/api-reference#hooks), [Deploy IaC - Phase 2 data plane](https://learn.microsoft.com/en-us/azure/sre-agent/deploy-iac#phase-2-data-plane-config-that-arm-cant-handle-yet).

## Parameters and possible values

Same logical parameters as the ARM hooks section, but without `properties.value`: the payload is sent directly to the data-plane. The complete schema is not formally documented by Microsoft.

| Parameter | Type | Required | What it is | Technical impact | Documented possible values |
| --- | --- | --- | --- | --- | --- |
| `{hookName}` | string | Yes | Hook name in path. | Identifies the policy. | String. Pattern not published. |
| Body JSON | object | Yes | Hook definition. | Configures the data-plane policy. | Not formally documented by Microsoft. |
| HTTP method | method | Yes | Resource operation. | Microsoft Learn says hooks support `PUT`, `GET`, `DELETE`. | `PUT`, `GET`, `DELETE`; list via `GET /api/v2/extendedAgent/hooks`. |

## Certified example and CRUD/deployment

YAML source format, consistent with `config/hooks/` in the Microsoft IaC guide:

```yaml
metadata:
  name: deny-production-delete
spec:
  eventType: PreToolUse
  hook:
    type: prompt
    matcher: ".*delete.*|.*remove.*"
    prompt: Deny destructive actions against production resources unless an explicit human approval is present.
  permissionDecision: deny
  enabled: true
```

Deploy con template ufficiale Microsoft, che applica la Phase 2 data-plane:

```bash
./bin/deploy.sh my-agent/
```

Equivalent raw API, with JSON payload generated from the YAML:

```bash
curl -fsS -X PUT \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  "${ENDPOINT}/api/v2/extendedAgent/hooks/deny-production-delete" \
  --data @hook.json
```

Line-by-line explanation:

| Line | What it configures | Concrete impact |
| --- | --- | --- |
| `curl -fsS -X PUT` | Create/update hook. | Applies the data-plane policy. |
| `Authorization: Bearer ${TOKEN}` | Token data-plane. | Usa audience corretta `https://azuresre.dev`. |
| `Content-Type: application/json` | JSON payload. | Required for the hook body. |
| `/api/v2/extendedAgent/hooks/...` | Hook resource. | Official data-plane target. |
| `--data @hook.json` | Hook definition. | Loads the specific policy. |

Official sources: [Deploy IaC - hooks YAML](https://learn.microsoft.com/en-us/azure/sre-agent/deploy-iac#config-directory-structure), [Deploy IaC - Phase 2 data plane](https://learn.microsoft.com/en-us/azure/sre-agent/deploy-iac#phase-2-data-plane-config-that-arm-cant-handle-yet), [API reference - hooks](https://learn.microsoft.com/en-us/azure/sre-agent/api-reference#hooks).

Read/list/delete:

```bash
curl -fsS -H "Authorization: Bearer ${TOKEN}" "${ENDPOINT}/api/v2/extendedAgent/hooks"
curl -fsS -X DELETE -H "Authorization: Bearer ${TOKEN}" "${ENDPOINT}/api/v2/extendedAgent/hooks/deny-production-delete"
```

# 14. Extended subagents - `/api/v2/extendedAgent/agents/{name}`

## Concrete description

This is the official data-plane surface for managing subagents. Unlike the ARM control-plane envelope, here the JSON body is sent directly to the data-plane and Microsoft Learn states that extended resources support `PUT`, `GET`, `PATCH`, `DELETE`.

Concrete impact: allows more granular Day-2 updates without a full ARM redeploy. Requires validation because the body schema is not fully published.

Official sources: [API reference - Extended agent configuration](https://learn.microsoft.com/en-us/azure/sre-agent/api-reference#extended-agent-configuration), [Deploy IaC - Day-2 operations](https://learn.microsoft.com/en-us/azure/sre-agent/deploy-iac#day-2-operations).

## Parameters and possible values

| Parameter | Type | Required | What it is | Technical impact | Documented possible values |
| --- | --- | --- | --- | --- | --- |
| `{name}` | string | Yes | Data-plane subagent name. | Identifies the extended subagent. | String. Pattern not published. |
| Body JSON | object | Yes | Subagent spec. | Configures instructions, tools, skills, handoffs. | Not formally documented by Microsoft. |
| Method | enum HTTP | Yes | Resource operation. | Manages config lifecycle. | `PUT`, `GET`, `PATCH`, `DELETE`. |

## Certified example and CRUD/deployment

YAML source format, consistent with `config/subagents/` in the Microsoft IaC guide:

```yaml
metadata:
  name: alert-investigator
spec:
  instructions: |
    Investigate Azure Monitor alerts. Read evidence before proposing remediation.
  handoffDescription: Use for Azure Monitor fired alerts and log-based incident triage.
  tools:
    - QueryLogAnalyticsByWorkspaceId
  enableSkills: true
  allowedSkills:
    - investigate-azure-alerts
```

Deploy with official Microsoft template:

```bash
./bin/deploy.sh my-agent/
```

Equivalent raw API, with JSON payload generated from the YAML:

```bash
curl -fsS -X PUT \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  "${ENDPOINT}/api/v2/extendedAgent/agents/alert-investigator" \
  --data @subagent.json
```

Explanation: `PUT` creates or replaces the subagent, the token is data-plane, the path `agents/alert-investigator` identifies the resource, and `subagent.json` contains instructions/tools/skills. For `PATCH`, use a partial body only if validated against the live behavior of the API version.

Official sources: [Deploy IaC - subagents YAML](https://learn.microsoft.com/en-us/azure/sre-agent/deploy-iac#config-directory-structure), [API reference - extended agent configuration](https://learn.microsoft.com/en-us/azure/sre-agent/api-reference#extended-agent-configuration).

```bash
curl -fsS -H "Authorization: Bearer ${TOKEN}" "${ENDPOINT}/api/v2/extendedAgent/agents/alert-investigator"
curl -fsS -X PATCH -H "Authorization: Bearer ${TOKEN}" -H "Content-Type: application/json" "${ENDPOINT}/api/v2/extendedAgent/agents/alert-investigator" --data @subagent-patch.json
curl -fsS -X DELETE -H "Authorization: Bearer ${TOKEN}" "${ENDPOINT}/api/v2/extendedAgent/agents/alert-investigator"
```

# 15. Extended tools - `/api/v2/extendedAgent/tools/{name}`

## Concrete description

This data-plane surface manages custom tools or tool configurations for the agent. It is useful for Day-2 updates when tools need to be updated without republishing ARM. Microsoft Learn documents the path and methods, but does not publish the complete tool payload schema.

Official sources: [API reference - Extended agent configuration](https://learn.microsoft.com/en-us/azure/sre-agent/api-reference#extended-agent-configuration).

## Parameters and possible values

| Parameter | Type | Required | What it is | Technical impact | Documented possible values |
| --- | --- | --- | --- | --- | --- |
| `{name}` | string | Yes | Tool name. | Identifies the data-plane tool. | String. Pattern not published. |
| Body JSON | object | Yes | Tool spec. | Defines capabilities, metadata, config. | Not formally documented by Microsoft. |
| Method | enum HTTP | Yes | Lifecycle operation. | Create/read/update/delete. | `PUT`, `GET`, `PATCH`, `DELETE`. |

## Certified example and CRUD/deployment

YAML source format, consistent with `config/skills/` in the Microsoft IaC guide:

```yaml
metadata:
  name: investigate-azure-alerts
  description: Investigate fired Azure Monitor alerts
spec:
  tools:
    - QueryLogAnalyticsByWorkspaceId
    - QueryAppInsightsUsingAppId
skillContent: |
  Use Azure Monitor alert context, query logs, summarize impact, and propose next action.
```

Deploy with official Microsoft template:

```bash
./bin/deploy.sh my-agent/
```

Equivalent raw API, with JSON payload generated from the YAML:

```bash
curl -fsS -X PUT \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  "${ENDPOINT}/api/v2/extendedAgent/tools/azure-resource-graph-readonly" \
  --data @tool.json
```

Explanation: the path selects the tool, `PUT` creates/updates it, the body contains a definition not formally schematized by Learn. Use `PATCH` only with live testing.

```bash
curl -fsS -H "Authorization: Bearer ${TOKEN}" "${ENDPOINT}/api/v2/extendedAgent/tools/azure-resource-graph-readonly"
curl -fsS -X PATCH -H "Authorization: Bearer ${TOKEN}" -H "Content-Type: application/json" "${ENDPOINT}/api/v2/extendedAgent/tools/azure-resource-graph-readonly" --data @tool-patch.json
curl -fsS -X DELETE -H "Authorization: Bearer ${TOKEN}" "${ENDPOINT}/api/v2/extendedAgent/tools/azure-resource-graph-readonly"
```

# 16. Extended connectors - `/api/v2/extendedAgent/connectors/{name}`

## Concrete description

Extended connectors is the data-plane surface for connectors managed after provisioning. It is particularly useful for MCP or connectors with dynamic properties/secrets that are not ideal to store in ARM. Microsoft Learn documents the extended path and methods, but does not publish the complete schema for each connector type.

Official sources: [API reference - Extended agent configuration](https://learn.microsoft.com/en-us/azure/sre-agent/api-reference#extended-agent-configuration), [API reference - Connector types](https://learn.microsoft.com/en-us/azure/sre-agent/api-reference#connector-types), [Deploy IaC - Phase 2 data plane](https://learn.microsoft.com/en-us/azure/sre-agent/deploy-iac#phase-2-data-plane-config-that-arm-cant-handle-yet).

## Parameters and possible values

| Parameter | Type | Required | What it is | Technical impact | Documented possible values |
| --- | --- | --- | --- | --- | --- |
| `{name}` | string | Yes | Connector name. | Identifies the extended connection. | String. Pattern not published. |
| Body JSON `dataConnectorType` | string | Functional | Connector type. | Selects connector behavior. | Documented values: `Kusto`, `Mcp`, `Outlook`, `Teams`; other template values must be validated. |
| Body JSON `endpoint` | string | Depends on type | Connector endpoint. | Where the agent connects. | URL/string. No enum. |
| Body JSON `extendedProperties` | object | Depends on type | Extra config. | Auth, partner, specific parameters. | Not formally documented by Microsoft. |
| Method | enum HTTP | Yes | Lifecycle operation. | Create/read/update/delete. | `PUT`, `GET`, `PATCH`, `DELETE`. |

## Esempio MCP connector

```json
{
  "properties": {
    "dataConnectorType": "Mcp",
    "endpoint": "https://mcp.contoso.example/sse",
    "extendedProperties": {
      "authType": "BearerToken",
      "partnerType": "CustomMcp"
    }
  }
}
```

Line-by-line explanation:

| Line/block | What it configures | Concrete impact |
| --- | --- | --- |
| `"dataConnectorType": "Mcp"` | MCP type. | The agent treats the endpoint as an MCP server/tool. |
| `"endpoint": "https://..."` | MCP URL. | Must be reachable from the agent/browser network per scenario. |
| `"extendedProperties"` | Extra config. | Contains auth/partner metadata. Complete schema not published. |
| `"authType": "BearerToken"` | Example auth type. | Operational evidence, not a complete official Learn enum. |
| `"partnerType": "CustomMcp"` | Partner classification. | Helps differentiate custom MCP connectors. |

## CRUD and deployment

```bash
curl -fsS -X PUT \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  "${ENDPOINT}/api/v2/extendedAgent/connectors/custom-mcp" \
  --data @mcp-connector.json

curl -fsS -H "Authorization: Bearer ${TOKEN}" "${ENDPOINT}/api/v2/extendedAgent/connectors/custom-mcp"
curl -fsS -X PATCH -H "Authorization: Bearer ${TOKEN}" -H "Content-Type: application/json" "${ENDPOINT}/api/v2/extendedAgent/connectors/custom-mcp" --data @mcp-connector-patch.json
curl -fsS -X DELETE -H "Authorization: Bearer ${TOKEN}" "${ENDPOINT}/api/v2/extendedAgent/connectors/custom-mcp"
```

# 17. Extended skills - `/api/v2/extendedAgent/skills/{name}`

## Concrete description

Extended skills is the data-plane surface for managing skills without the ARM Base64 envelope. It is used for GitOps/Day-2 updates and for applying configurations that the IaC template manages after provisioning. Microsoft Learn documents the path and methods, but does not publish the complete skill schema.

Official sources: [API reference - Extended agent configuration](https://learn.microsoft.com/en-us/azure/sre-agent/api-reference#extended-agent-configuration), [Deploy IaC - config directory skills](https://learn.microsoft.com/en-us/azure/sre-agent/deploy-iac#config-directory-structure).

## Parameters and possible values

| Parameter | Type | Required | What it is | Technical impact | Documented possible values |
| --- | --- | --- | --- | --- | --- |
| `{name}` | string | Yes | Skill name. | Identifies the skill. | String. Pattern not published. |
| Body JSON | object | Yes | Skill spec. | Defines content, tools, files. | Not formally documented by Microsoft. |
| Method | enum HTTP | Yes | Lifecycle operation. | Create/read/update/delete. | `PUT`, `GET`, `PATCH`, `DELETE`. |

## Certified example and CRUD/deployment

YAML source format, consistent with `config/common-prompts/` in the Microsoft IaC guide:

```yaml
metadata:
  name: production-safety-rules
spec:
  prompt: Never perform destructive production changes without explicit human approval and an attached incident or change ID.
```

Deploy with official Microsoft template:

```bash
./bin/deploy.sh my-agent/
```

Equivalent raw API, with JSON payload generated from the YAML:

```bash
curl -fsS -X PUT \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  "${ENDPOINT}/api/v2/extendedAgent/skills/investigate-azure-alerts" \
  --data @skill.json
```

Explanation: `skill.json` contains the same logical skill content, but it is not base64-encoded; the data-plane receives the JSON directly. The schema must be validated live because it is not published as a complete JSON Schema.

Official sources: [Deploy IaC - skills YAML + markdown](https://learn.microsoft.com/en-us/azure/sre-agent/deploy-iac#config-directory-structure), [API reference - extended agent configuration](https://learn.microsoft.com/en-us/azure/sre-agent/api-reference#extended-agent-configuration).

```bash
curl -fsS -H "Authorization: Bearer ${TOKEN}" "${ENDPOINT}/api/v2/extendedAgent/skills/investigate-azure-alerts"
curl -fsS -X PATCH -H "Authorization: Bearer ${TOKEN}" -H "Content-Type: application/json" "${ENDPOINT}/api/v2/extendedAgent/skills/investigate-azure-alerts" --data @skill-patch.json
curl -fsS -X DELETE -H "Authorization: Bearer ${TOKEN}" "${ENDPOINT}/api/v2/extendedAgent/skills/investigate-azure-alerts"
```

# 18. Extended common prompts - `/api/v2/extendedAgent/commonprompts/{name}`

## Concrete description

Extended common prompts manages shared prompts via the data-plane. It is useful for quick updates to common policies and instructions without ARM redeployment.

Official sources: [API reference - Extended agent configuration](https://learn.microsoft.com/en-us/azure/sre-agent/api-reference#extended-agent-configuration), [Deploy IaC - common prompts config](https://learn.microsoft.com/en-us/azure/sre-agent/deploy-iac#config-directory-structure).

## Parameters and possible values

| Parameter | Type | Required | What it is | Technical impact | Documented possible values |
| --- | --- | --- | --- | --- | --- |
| `{name}` | string | Yes | Prompt name. | Identifies the prompt. | String. Pattern not published. |
| Body JSON | object | Yes | Prompt and metadata. | Configures shared instructions. | Not formally documented by Microsoft. |
| Method | enum HTTP | Yes | Lifecycle. | Create/read/update/delete. | `PUT`, `GET`, `PATCH`, `DELETE`. |

## Certified example and CRUD/deployment

YAML source format, consistent with `automations/scheduled-tasks/` in the Microsoft IaC guide:

```yaml
metadata:
  name: daily-health-check
spec:
  description: Daily production health summary
  schedule: "0 8 * * *"
  prompt: Summarize incidents, failed deployments, and critical alerts from the last 24 hours.
  enabled: true
  mode: Review
```

Deploy with official Microsoft template:

```bash
./bin/deploy.sh my-agent/
```

Equivalent raw API, with JSON payload generated from the YAML:

```bash
curl -fsS -X PUT \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  "${ENDPOINT}/api/v2/extendedAgent/commonprompts/production-safety-rules" \
  --data @common-prompt.json

curl -fsS -H "Authorization: Bearer ${TOKEN}" "${ENDPOINT}/api/v2/extendedAgent/commonprompts/production-safety-rules"
curl -fsS -X PATCH -H "Authorization: Bearer ${TOKEN}" -H "Content-Type: application/json" "${ENDPOINT}/api/v2/extendedAgent/commonprompts/production-safety-rules" --data @common-prompt-patch.json
curl -fsS -X DELETE -H "Authorization: Bearer ${TOKEN}" "${ENDPOINT}/api/v2/extendedAgent/commonprompts/production-safety-rules"
```

Explanation: same logical content as the ARM common prompt sub-resource, but without the Base64 envelope. Use for Day-2 when updating a common policy via the data-plane.

Official sources: [Deploy IaC - common prompts directory](https://learn.microsoft.com/en-us/azure/sre-agent/deploy-iac#config-directory-structure), [API reference - extended agent configuration](https://learn.microsoft.com/en-us/azure/sre-agent/api-reference#extended-agent-configuration).

# 19. Extended scheduled tasks - `/api/v2/extendedAgent/scheduledtasks/{name}`

## Concrete description

Extended scheduled tasks is the data-plane surface for recurring automations. It is consistent with the IaC guide for Phase 2 data-plane and with the API reference extended configuration.

Official sources: [API reference - Extended agent configuration](https://learn.microsoft.com/en-us/azure/sre-agent/api-reference#extended-agent-configuration), [Deploy IaC - Phase 2 data plane](https://learn.microsoft.com/en-us/azure/sre-agent/deploy-iac#phase-2-data-plane-config-that-arm-cant-handle-yet), [Pricing - active flow](https://learn.microsoft.com/en-us/azure/sre-agent/pricing-billing#active-flow-variable-cost).

## Parameters and possible values

Same logical parameters as the ARM scheduled task section. Complete schema not formally documented by Microsoft; official extended methods: `PUT`, `GET`, `PATCH`, `DELETE`.

## Example and CRUD/deployment

```bash
curl -fsS -X PUT \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  "${ENDPOINT}/api/v2/extendedAgent/scheduledtasks/daily-health-check" \
  --data @scheduled-task.json

curl -fsS -H "Authorization: Bearer ${TOKEN}" "${ENDPOINT}/api/v2/extendedAgent/scheduledtasks/daily-health-check"
curl -fsS -X PATCH -H "Authorization: Bearer ${TOKEN}" -H "Content-Type: application/json" "${ENDPOINT}/api/v2/extendedAgent/scheduledtasks/daily-health-check" --data @scheduled-task-patch.json
curl -fsS -X DELETE -H "Authorization: Bearer ${TOKEN}" "${ENDPOINT}/api/v2/extendedAgent/scheduledtasks/daily-health-check"
```

Explanation: `PUT` creates/updates the automation; each run may consume active-flow AAU; schedule sparingly and use tight filters/prompts.

Official sources: [Deploy IaC - scheduled tasks directory](https://learn.microsoft.com/en-us/azure/sre-agent/deploy-iac#config-directory-structure), [API reference - extended agent configuration](https://learn.microsoft.com/en-us/azure/sre-agent/api-reference#extended-agent-configuration), [Pricing - active flow](https://learn.microsoft.com/en-us/azure/sre-agent/pricing-billing#active-flow-variable-cost).

# 20. Extended plugins - `/api/v2/extendedAgent/plugins/{name}`

## Concrete description

Extended plugins manages plugin configurations for the agent. Microsoft Learn includes `Plugins` in the extended configuration table and states that all extended resources support `PUT`, `GET`, `PATCH`, `DELETE`. However, it does not publish the complete plugin payload schema.

Concrete impact: plugins extend agent capabilities or integrations. A misconfigured plugin can fail at runtime or expose unwanted tools; plugins with secrets require secure management outside repositories and logs.

Official sources: [API reference - Extended agent configuration](https://learn.microsoft.com/en-us/azure/sre-agent/api-reference#extended-agent-configuration), [Deploy IaC - Phase 2 data plane](https://learn.microsoft.com/en-us/azure/sre-agent/deploy-iac#phase-2-data-plane-config-that-arm-cant-handle-yet), [microsoft/sre-agent templates](https://github.com/microsoft/sre-agent/tree/main/sreagent-templates).

## Parameters and possible values

| Parameter | Type | Required | What it is | Technical impact | Documented possible values |
| --- | --- | --- | --- | --- | --- |
| `{name}` | string | Yes | Plugin config name. | Identifies the plugin configuration. | String. Pattern not published. |
| Body JSON | object | Yes | Plugin config. | Enables and configures the plugin. | Not formally documented by Microsoft. |
| `enabled` | boolean | No | Plugin flag. | Activates/deactivates the plugin if supported by the schema. | `true`, `false` as JSON boolean; field not formally schematized. |
| `configuration` | object | No | Plugin-specific parameters. | Determines plugin behavior. | Not formally documented by Microsoft. |
| Method | enum HTTP | Yes | Lifecycle. | Create/read/update/delete. | `PUT`, `GET`, `PATCH`, `DELETE`. |

## Certified example: JSON + curl

```json
{
  "name": "example-plugin",
  "type": "Plugin",
  "tags": [
    "observability"
  ],
  "properties": {
    "enabled": true,
    "configuration": {
      "mode": "readOnly"
    }
  }
}
```

Line-by-line explanation:

| Line/block | What it configures | Concrete impact |
| --- | --- | --- |
| `"name": "example-plugin"` | Plugin name. | Identifies the configuration. |
| `"type": "Plugin"` | Document type. | Template evidence, not a complete Learn enum. |
| `"tags": [...]` | Logical tags. | Helps with cataloging. |
| `"enabled": true` | Plugin active. | Allows use if runtime and schema support it. |
| `"mode": "readOnly"` | Example mode. | Reduces operational risk; value is not an official Learn enum. |

## CRUD and deployment

```bash
curl -fsS -X PUT \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  "${ENDPOINT}/api/v2/extendedAgent/plugins/example-plugin" \
  --data @plugin-config.json

curl -fsS -H "Authorization: Bearer ${TOKEN}" "${ENDPOINT}/api/v2/extendedAgent/plugins/example-plugin"
curl -fsS -X PATCH -H "Authorization: Bearer ${TOKEN}" -H "Content-Type: application/json" "${ENDPOINT}/api/v2/extendedAgent/plugins/example-plugin" --data @plugin-config-patch.json
curl -fsS -X DELETE -H "Authorization: Bearer ${TOKEN}" "${ENDPOINT}/api/v2/extendedAgent/plugins/example-plugin"
```

# 21. Threads and chat - `/api/v1/threads*`

## Concrete description

Threads and chat are runtime APIs, not IaC desired-state resources. They are used to create conversations, send messages, and read thread history. They are fundamental to using the agent, but they are not sub-resources to deploy: they are runtime entities created by user/application interaction.

Concrete impact: each message can consume active-flow AAU when the agent works. Threads contain operational context and may include sensitive data, so access and retention must be governed.

Official sources: [API reference - Threads and chat](https://learn.microsoft.com/en-us/azure/sre-agent/api-reference#threads-and-chat), [Pricing - active flow](https://learn.microsoft.com/en-us/azure/sre-agent/pricing-billing#active-flow-variable-cost).

## Parameters and possible values

| Parameter | Type | Required | What it is | Technical impact | Documented possible values |
| --- | --- | --- | --- | --- | --- |
| `{threadId}` | string | Yes for specific thread | Conversation ID. | Selects the thread to read or send messages to. | Format not documented. |
| Message body | object | Yes for `POST messages` | User/app message. | Activates agentic work. | Complete schema not formally documented in the Learn table. |
| Method | enum HTTP | Yes | Runtime operation. | List/read/send/read messages. | `GET /api/v1/threads`, `GET /api/v1/threads/{threadId}`, `POST /api/v1/threads/{threadId}/messages`, `GET /api/v1/threads/{threadId}/messages`. |

## Esempio operativo

```bash
curl -fsS -H "Authorization: Bearer ${TOKEN}" "${ENDPOINT}/api/v1/threads"

curl -fsS -X POST \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  "${ENDPOINT}/api/v1/threads/${THREAD_ID}/messages" \
  --data @message.json
```

Line-by-line explanation:

| Line | What it does | Concrete impact |
| --- | --- | --- |
| `GET /api/v1/threads` | List conversations. | Retrieves existing runtime context. |
| `POST /messages` | Send message to thread. | Can trigger active-flow consumption and tool calls. |
| `message.json` | Message payload. | Complete schema not published; validate with live API. |

## CRUD/deployment

Not deployed as an IaC resource. Official operations:

```bash
curl -fsS -H "Authorization: Bearer ${TOKEN}" "${ENDPOINT}/api/v1/threads"
curl -fsS -H "Authorization: Bearer ${TOKEN}" "${ENDPOINT}/api/v1/threads/${THREAD_ID}"
curl -fsS -X POST -H "Authorization: Bearer ${TOKEN}" -H "Content-Type: application/json" "${ENDPOINT}/api/v1/threads/${THREAD_ID}/messages" --data @message.json
curl -fsS -H "Authorization: Bearer ${TOKEN}" "${ENDPOINT}/api/v1/threads/${THREAD_ID}/messages"
```

# 22. Approvals - `/api/v1/approvals/*`

## Concrete description

Approvals is the runtime surface for human decisions on actions proposed by the agent. It is used to maintain human-in-the-loop when the agent proposes remediation or operational actions.

Concrete impact: when using `Review`, approvals is the operational barrier that allows or blocks actions. If approvals are mishandled, urgent remediation can be blocked or risky actions can be authorized.

Official sources: [API reference - Approvals](https://learn.microsoft.com/en-us/azure/sre-agent/api-reference#approvals), [API reference - RBAC roles](https://learn.microsoft.com/en-us/azure/sre-agent/api-reference#rbac-roles).

## Parameters and possible values

| Parameter | Type | Required | What it is | Technical impact | Documented possible values |
| --- | --- | --- | --- | --- | --- |
| `{threadId}` | string | Yes | Thread containing the approval. | Scope of the decision. | Format not documented. |
| `{id}` | string | Yes for decision | Approval ID. | Selects the action to approve/reject. | Format not documented. |
| Decision body | object | Yes for decision | Approve/reject decision. | Determines whether the action proceeds. | API reference says approve or reject, but does not publish a complete payload enum. |
| Method | enum HTTP | Yes | Approvals operations. | List and decision. | `GET`, `POST`. |

## Esempio operativo

```bash
curl -fsS -H "Authorization: Bearer ${TOKEN}" \
  "${ENDPOINT}/api/v1/approvals/${THREAD_ID}"

curl -fsS -X POST \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  "${ENDPOINT}/api/v1/approvals/${THREAD_ID}/${APPROVAL_ID}/decision" \
  --data @approval-decision.json
```

Line-by-line explanation:

| Line | What it does | Concrete impact |
| --- | --- | --- |
| `GET /approvals/${THREAD_ID}` | List pending approvals. | Enables human review before the action. |
| `POST /decision` | Send decision. | Unblocks or blocks the proposed action. |
| `approval-decision.json` | Decision payload. | Must represent approve/reject according to the live schema. |

## CRUD/deployment

Not deployed as an IaC resource. Official operations:

```bash
curl -fsS -H "Authorization: Bearer ${TOKEN}" "${ENDPOINT}/api/v1/approvals/${THREAD_ID}"
curl -fsS -X POST -H "Authorization: Bearer ${TOKEN}" -H "Content-Type: application/json" "${ENDPOINT}/api/v1/approvals/${THREAD_ID}/${APPROVAL_ID}/decision" --data @approval-decision.json
```

# 23. Real-time streaming SignalR hub - `/agentHub`

## Concrete description

`/agentHub` is the SignalR surface for real-time streaming of chat, messages, and thread updates. It is not a deployable resource; it is a runtime endpoint. It is used when building UIs or clients that need to receive real-time updates.

Concrete impact: requires WebSocket/SignalR support and a network that does not block `*.azuresre.ai`. Corporate proxies can break real-time chat if they block WebSocket.

Official sources: [API reference - Real-time streaming](https://learn.microsoft.com/en-us/azure/sre-agent/api-reference#real-time-streaming), [Network requirements - required domains](https://learn.microsoft.com/en-us/azure/sre-agent/network-requirements#required-domains).

## Parameters and possible values

| Parameter | Type | Required | What it is | Technical impact | Documented possible values |
| --- | --- | --- | --- | --- | --- |
| Hub path `/agentHub` | path | Yes | SignalR endpoint. | Real-time connection. | Fixed path `/agentHub`. |
| ****** | string | Yes | Auth token. | Authenticates the SignalR client. | Same data-plane bearer token per API reference. |
| Transport | protocol | Depends on client | WebSocket/SignalR transport. | Must pass through firewall/proxy. | Microsoft Learn requires HTTP and WebSocket to `*.azuresre.ai`; client details not schematized. |

## Esempio operativo

```text
SignalR client connects to:
${ENDPOINT}/agentHub

Authorization:
Bearer ${TOKEN}
```

Line-by-line explanation:

| Line | What it does | Concrete impact |
| --- | --- | --- |
| `${ENDPOINT}/agentHub` | Hub URL. | Connects the client to the agent's real-time stream. |
| `Authorization: ****** | Data-plane auth. | Uses token with audience `https://azuresre.dev`. |

## CRUD/deployment

There is no IaC CRUD for `/agentHub`. It is a runtime endpoint to consume with a SignalR library. Network requirement: allow `*.azuresre.ai` for HTTP and WebSocket.

# 24. Plugin marketplaces - `/api/v2/plugins/marketplaces`

## Concrete description

Plugin marketplaces is a surface observed in official Microsoft `microsoft/sre-agent` templates, used to register plugin marketplace documents. The Microsoft Learn API reference does not publish this route in the extended configuration table and does not publish a complete payload schema.

Concrete impact: useful for advanced plugin scenarios, but should be treated as template-driven and not as a complete Learn contract. Use only with live validation and rollback.

Official sources: [Deploy IaC - repository ufficiale Microsoft](https://learn.microsoft.com/en-us/azure/sre-agent/deploy-iac#overview), [microsoft/sre-agent templates](https://github.com/microsoft/sre-agent/tree/main/sreagent-templates).

## Parameters and possible values

| Parameter | Type | Required | What it is | Technical impact | Documented possible values |
| --- | --- | --- | --- | --- | --- |
| Body JSON marketplace | object | Yes | Marketplace document. | Registers/catalogs a plugin marketplace. | Not formally documented by Microsoft Learn. |
| Method | HTTP | Yes | Operation. | Templates use creation via POST. | Template evidence: `POST`; Learn does not publish complete CRUD. |

## Certified example: JSON + curl

```json
{
  "name": "contoso-observability-marketplace",
  "displayName": "Contoso Observability Marketplace",
  "plugins": []
}
```

Explanation: `name` and `displayName` are descriptive examples; `plugins` represents a marketplace list. The schema is not formally published by Learn, so do not treat them as guaranteed fields without live testing.

## Deploy

```bash
curl -fsS -X POST \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  "${ENDPOINT}/api/v2/plugins/marketplaces" \
  --data @plugin-marketplace.json
```

# 25. Plugin installations - `/api/v2/plugins/installations`

## Concrete description

Plugin installations is a surface observed in official Microsoft templates for registering plugin installations. Like marketplaces, it is not schematized in the Learn API reference.

Concrete impact: represents the installation or association of a plugin with an agent. Since it can enable external capabilities, it must be treated as a controlled change, with testing and secrets management.

Official sources: [Deploy IaC - repository ufficiale Microsoft](https://learn.microsoft.com/en-us/azure/sre-agent/deploy-iac#overview), [microsoft/sre-agent templates](https://github.com/microsoft/sre-agent/tree/main/sreagent-templates).

## Parameters and possible values

| Parameter | Type | Required | What it is | Technical impact | Documented possible values |
| --- | --- | --- | --- | --- | --- |
| Body JSON installation | object | Yes | Plugin installation document. | Links plugin/runtime config. | Not formally documented by Microsoft Learn. |
| Method | HTTP | Yes | Operation. | Templates use `POST`. | Template evidence: `POST`; Learn does not publish complete CRUD. |

## Certified example: JSON + curl

```json
{
  "pluginName": "contoso-observability",
  "enabled": true,
  "configuration": {
    "mode": "readOnly"
  }
}
```

Explanation: `pluginName`, `enabled`, `configuration` are example fields; the technical meaning is to install/enable a plugin in a conservative mode. They are not official Learn enums or schema.

## Deploy

```bash
curl -fsS -X POST \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  "${ENDPOINT}/api/v2/plugins/installations" \
  --data @plugin-installation.json
```

# 26. Incident platform indexing configuration - `/api/v2/incidents/indexing/{platformType}/configuration`

## Concrete description

This surface is observed in official Microsoft templates for platform-level incident indexing configurations. Microsoft Learn documents `incidentManagementConfiguration.type` on the root resource and documents incident filters, but does not publish this route in the API reference as a complete contract.

Concrete impact: can influence how incidents from a platform are indexed or normalized. Since it is not formally schematized in Learn, use it only as a template-driven extension.

Official sources: [Microsoft.App/agents - IncidentManagementConfiguration](https://learn.microsoft.com/en-us/azure/templates/microsoft.app/agents?pivots=deployment-language-terraform#incidentmanagementconfiguration), [API reference - Agent properties](https://learn.microsoft.com/en-us/azure/sre-agent/api-reference#agent-properties), [microsoft/sre-agent templates](https://github.com/microsoft/sre-agent/tree/main/sreagent-templates).

## Parameters and possible values

| Parameter | Type | Required | What it is | Technical impact | Documented possible values |
| --- | --- | --- | --- | --- | --- |
| `{platformType}` | string | Yes | Incident platform type. | Selects the configuration for the platform. | Official root values: `PagerDuty`, `AzMonitor`, `ServiceNow`, `None`. Use on this route not formally documented. |
| Body JSON configuration | object | Yes | Indexing config. | Influences incident indexing. | Not formally documented by Microsoft Learn. |
| Method | HTTP | Depends on template | Operation. | Read/write configuration. | Not formally documented in the API reference. |

## Certified example: JSON + curl

```json
{
  "platformType": "AzMonitor",
  "enabled": true
}
```

Explanation: minimal example; `platformType` uses an incident platform value documented at the root level, `enabled` is a reasonable flag but not formally schematized by Learn for this route.

## Deploy/operazioni

Template-driven example to validate live:

```bash
curl -fsS -X PATCH \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  "${ENDPOINT}/api/v2/incidents/indexing/AzMonitor/configuration" \
  --data @incident-indexing-azmonitor.json
```

# 27. Data-plane incident filters / response plans

## Concrete description

Data-plane response plans are the operational representation, observed in official Microsoft templates, of the configuration that filters incidents, assigns handlers, and controls automatic investigations. They are conceptually linked to the ARM `incidentFilters` sub-resource, but the specific data-plane path and complete schema are not formally published in the Learn API reference.

Concrete impact: they are the most important mechanism for reducing noise, cost, and risk in automated incidents. The pricing page explicitly states that filtering incidents with response plans reduces unnecessary work.

Official sources: [Pricing - cost optimization tips](https://learn.microsoft.com/en-us/azure/sre-agent/pricing-billing#cost-optimization-tips), [Deploy IaC - config directory incident-filters](https://learn.microsoft.com/en-us/azure/sre-agent/deploy-iac#config-directory-structure), [microsoft/sre-agent templates](https://github.com/microsoft/sre-agent/tree/main/sreagent-templates).

## Parameters and possible values

| Parameter | Type | Required | What it is | Technical impact | Documented possible values |
| --- | --- | --- | --- | --- | --- |
| `incidentPlatform` | string | Yes functionally | Incident platform. | Determines the event source. | Documented root values: `AzMonitor`, `PagerDuty`, `ServiceNow`, `None`. |
| `priorities` | string[] | No | Severity/priorities. | Filters which incidents trigger the plan. | Not formally documented; values depend on the platform. |
| `handlingAgent` | string | No | Handler subagent. | Routes investigation. | Subagent name. No enum. |
| `agentMode` | string | No | Operational mode. | Controls autonomy/review. | Not formally documented for this surface. |
| `deepInvestigationEnabled` | boolean | No | Investigation depth. | More context and potential cost. | `true`, `false`. |
| `maxAutomatedInvestigationAttempts` | integer | No | Retry limit. | Avoids loops. | Integer; range not published. |

## Esempio certificato: YAML come sorgente

```yaml
metadata:
  name: pagerduty-p1
spec:
  incidentPlatform: PagerDuty
  isEnabled: true
  priorities:
    - P1
  handlingAgent: incident-commander
  agentMode: Review
  deepInvestigationEnabled: true
  maxAutomatedInvestigationAttempts: 1
```

Line-by-line explanation:

| Line/block | What it configures | Concrete impact |
| --- | --- | --- |
| `metadata.name` | Response plan name. | Identifies the plan for P1 incidents. |
| `spec.incidentPlatform` | PagerDuty source. | Applies the rule to PagerDuty incidents. |
| `spec.isEnabled` | Plan active. | Allows activation. |
| `spec.priorities` | Only highest priority. | Reduces noise/cost. |
| `spec.handlingAgent` | Handler subagent. | Delegates to a specialized role. |
| `spec.agentMode` | Review mode. | Maintains human control. |
| `spec.deepInvestigationEnabled` | Deep investigation. | Better quality, higher potential consumption. |
| `spec.maxAutomatedInvestigationAttempts` | Single attempt. | Avoids retry loops. |

## Deploy

Deploy with official Microsoft template:

```bash
./bin/deploy.sh my-agent/
```

The exact endpoint to use for the raw API depends on the template/version, because Learn does not publish the complete data-plane contract. If using the official ARM sub-resource, use `/incidentFilters/{name}` as in section 7. If using the official Microsoft template flow, apply with the `microsoft/sre-agent` repository scripts and validate the generated endpoint.

# Operational summary: which surfaces to use for enterprise IaC

| Scenario | Recommended surface | Reason |
| --- | --- | --- |
| Create agent | `Microsoft.App/agents` via ARM/Bicep/AzAPI | Official root resource. |
| Create base connector | `Microsoft.App/agents/connectors` or `/DataConnectors/{name}` | Published connector schema, even though `dataConnectorType` is a string. |
| Configure skill/subagent/tool/prompt via ARM | Base64 envelope sub-resource | Official paths, but incomplete internal schema. |
| Configure repo, knowledge, hooks, triggers, plugins | Data-plane | Microsoft Learn documents them as data-plane and the IaC guide places them in Phase 2. |
| Chat, approvals, streaming | Runtime API | Not desired-state resources. |
| Plugin marketplaces/installations and incident indexing | Official templates, live validation required | Microsoft evidence, but Learn schema not published. |

# Technical glossary

| Term | Concrete definition |
| --- | --- |
| ARM | Azure Resource Manager, Azure control-plane for creating, updating, reading, and deleting resources. |
| Control-plane | Azure resource management APIs, usually on `management.azure.com`, protected by Azure RBAC. |
| Data-plane | Agent-specific operational APIs, exposed on the per-agent endpoint and authenticated with audience `https://azuresre.dev`. |
| Sub-resource | Child resource under `Microsoft.App/agents`, for example a connector or skill. |
| Base64 envelope | Format in which ARM receives `properties.value` as a Base64 string containing the actual JSON spec. |
| UAMI | User Assigned Managed Identity, an Azure managed identity independent of the lifecycle of a single resource. |
| RBAC | Role-Based Access Control, Azure model for assigning permissions to identities, users, and groups. |
| MCP | Model Context Protocol, protocol for exposing tools and context to agentic systems. |
| AAU | Azure Agent Unit, the unit used by Azure SRE Agent to measure active agentic consumption. |
| Active flow | Actual agent work that consumes tokens and therefore AAU. |
| Always-on flow | Fixed cost per agent-hour while the agent exists, even when it is not processing work. |
| SignalR | Tecnologia Microsoft per comunicazione real-time tra client e servizio. |
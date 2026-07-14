# Azure SRE Agent Complete Resource and Sub-Resource Reference

Date: 2026-06-11

This document inventories the Azure SRE Agent resources, sub-resources, API-managed configuration surfaces, supporting Azure resources, parameters, possible documented values, examples, and deployment commands.

## 1. Source Hierarchy and Accuracy Boundary

This reference uses the following source hierarchy:

1. Microsoft Learn Azure SRE Agent API reference.
   Source: https://learn.microsoft.com/en-us/azure/sre-agent/api-reference
2. Microsoft Learn ARM template reference for `Microsoft.App/agents`.
   Source: https://learn.microsoft.com/en-us/azure/templates/microsoft.app/agents?pivots=deployment-language-terraform
3. Microsoft Learn ARM template reference for `Microsoft.App/agents/connectors`.
   Source: https://learn.microsoft.com/en-us/azure/templates/microsoft.app/agents/connectors?pivots=deployment-language-terraform
4. Microsoft Learn deploy with IaC guide.
   Source: https://learn.microsoft.com/en-us/azure/sre-agent/deploy-iac
5. Microsoft Learn create/setup, permissions, regions, network, and billing references.
   Sources:
   - https://learn.microsoft.com/en-us/azure/sre-agent/create-and-set-up
   - https://learn.microsoft.com/en-us/azure/sre-agent/permissions
   - https://learn.microsoft.com/en-us/azure/sre-agent/supported-regions
   - https://learn.microsoft.com/en-us/azure/sre-agent/network-requirements
   - https://learn.microsoft.com/en-us/azure/sre-agent/pricing-billing
6. Official Microsoft SRE Agent repository and templates, which Microsoft Learn explicitly references as production-ready IaC templates.
   Source: https://github.com/microsoft/sre-agent/tree/main/sreagent-templates
7. Terraform provider documentation for supporting Azure resources and AzAPI.
   Sources:
   - https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/resource_group
   - https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/user_assigned_identity
   - https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/role_assignment
   - https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/log_analytics_workspace
   - https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/application_insights
   - https://registry.terraform.io/providers/Azure/azapi/latest/docs/resources/resource

Important limitation: several Azure SRE Agent data-plane payload schemas are not fully published as OpenAPI, TypeSpec, or JSON Schema. Where Microsoft Learn exposes endpoint paths but not full request schema, this document clearly marks the schema as "not formally published" and uses the Microsoft template repository only as implementation evidence.

## 2. Complete Inventory

### 2.1 Supporting Azure Resources Created Around the Agent

These are not Azure SRE Agent sub-resources, but Microsoft Learn states they are created during provisioning and the IaC guide lists them as deployment resources.

| Resource | Terraform resource | Purpose | Official source |
| --- | --- | --- | --- |
| Resource group | `azurerm_resource_group` | Container for agent resource, identity, Log Analytics, Application Insights, and optional supporting resources. | https://learn.microsoft.com/en-us/azure/sre-agent/deploy-iac |
| User-assigned managed identity | `azurerm_user_assigned_identity` | Agent identity for Azure access without embedded secrets. | https://learn.microsoft.com/en-us/azure/sre-agent/permissions |
| RBAC role assignments | `azurerm_role_assignment` | Grants the UAMI diagnostic/action permissions and grants users SRE Agent roles. | https://learn.microsoft.com/en-us/azure/sre-agent/permissions |
| Log Analytics workspace | `azurerm_log_analytics_workspace` | Stores/query logs used by agent investigations and Application Insights workspace mode. | https://learn.microsoft.com/en-us/azure/sre-agent/create-and-set-up |
| Application Insights | `azurerm_application_insights` | Agent telemetry, monitoring, and log configuration. | https://learn.microsoft.com/en-us/azure/sre-agent/create-and-set-up |
| Optional Logic App webhook bridge | `Microsoft.Logic/workflows` or template-generated workflow | Optional bridge for inbound webhook systems in Microsoft templates. Not a required agent resource. | https://github.com/microsoft/sre-agent/tree/main/sreagent-templates |

### 2.2 Azure SRE Agent ARM Resource and ARM Sub-Resources

| Surface | Official resource/API path | Operations | Payload model | Official source |
| --- | --- | --- | --- | --- |
| Agent root resource | `Microsoft.App/agents` | PUT, GET, DELETE, plus start/stop/usages/dailyusages in API reference | Typed ARM properties | https://learn.microsoft.com/en-us/azure/templates/microsoft.app/agents?pivots=deployment-language-terraform |
| Connectors | `Microsoft.App/agents/connectors@2026-01-01` in ARM template docs; `/DataConnectors/{name}` in 2025 API reference | PUT, GET, DELETE | Direct typed properties | https://learn.microsoft.com/en-us/azure/templates/microsoft.app/agents/connectors?pivots=deployment-language-terraform and https://learn.microsoft.com/en-us/azure/sre-agent/api-reference |
| Skills | `/skills/{name}` | PUT, GET, DELETE documented, but blocked for external tenants in live validation | Base64 envelope in `properties.value`; use data-plane extendedAgent operationally. | https://learn.microsoft.com/en-us/azure/sre-agent/api-reference and https://github.com/microsoft/sre-agent/issues/199 |
| Subagents | `/subagents/{name}` | PUT, GET, DELETE documented, but blocked for external tenants in live validation | Base64 envelope in `properties.value`; use data-plane extendedAgent operationally. | https://learn.microsoft.com/en-us/azure/sre-agent/api-reference and https://github.com/microsoft/sre-agent/issues/199 |
| Tools | `/tools/{name}` | PUT, GET, DELETE documented, but blocked for external tenants in live validation | Base64 envelope in `properties.value`; data-plane tool creation is also preview-blocked in this tenant because public tool object types are rejected with `InvalidObjectType`. | https://learn.microsoft.com/en-us/azure/sre-agent/api-reference and https://github.com/microsoft/sre-agent/issues/199 |
| Scheduled tasks | `/scheduledTasks/{name}` | PUT, GET, DELETE documented, but blocked for external tenants in live validation | Base64 envelope in `properties.value`; Microsoft templates use data-plane PUT for extras. | https://learn.microsoft.com/en-us/azure/sre-agent/api-reference and https://github.com/microsoft/sre-agent/pull/200 |
| Incident filters | `/incidentFilters/{name}` | PUT, GET, DELETE documented, but blocked for external tenants in live validation | Base64 envelope in `properties.value`; Microsoft templates use data-plane PUT for response plans. | https://learn.microsoft.com/en-us/azure/sre-agent/api-reference and https://github.com/microsoft/sre-agent/pull/200 |
| Hooks | `/hooks/{name}` | PUT, GET, DELETE in API reference; IaC guide says hooks are not yet exposed as ARM sub-resources at deploy time and are Phase 2 data-plane. | Base64 envelope or data-plane object | https://learn.microsoft.com/en-us/azure/sre-agent/api-reference and https://learn.microsoft.com/en-us/azure/sre-agent/deploy-iac |
| Common prompts | `/commonPrompts/{name}` | PUT, GET, DELETE | Base64 envelope or data-plane object | https://learn.microsoft.com/en-us/azure/sre-agent/api-reference |

### 2.3 Azure SRE Agent Data-Plane Desired-State Surfaces

| Surface | Data-plane path | Operations | Purpose | Official source |
| --- | --- | --- | --- | --- |
| Repositories | `/api/v2/repos/{repoName}` | PUT, GET, DELETE, POST test | Connect source code repositories. | https://learn.microsoft.com/en-us/azure/sre-agent/api-reference |
| Knowledge files | `/api/v1/agentmemory/upload`, `/status`, `/document/{fileName}`, `/documents`, `/indexer-status` | POST, GET, DELETE | Upload documents to agent memory. | https://learn.microsoft.com/en-us/azure/sre-agent/api-reference |
| HTTP triggers | `/api/v1/httptriggers/create`, `/api/v1/httptriggers`, `/api/v1/httptriggers/{triggerId}/execute`, `/api/v1/httptriggers/trigger/{triggerId}` | POST, GET | Create and execute webhook triggers. | https://learn.microsoft.com/en-us/azure/sre-agent/api-reference |
| Hooks | `/api/v2/extendedAgent/hooks/{hookName}` | PUT, GET, DELETE | Governance hooks and safety guardrails. | https://learn.microsoft.com/en-us/azure/sre-agent/api-reference |
| Extended subagents | `/api/v2/extendedAgent/agents/{name}` | PUT, GET, PATCH, DELETE | Manage subagents. | https://learn.microsoft.com/en-us/azure/sre-agent/api-reference |
| Extended tools | `/api/v2/extendedAgent/tools/{name}` | PUT, GET, PATCH, DELETE documented; live custom tool create blocked in this tenant | Microsoft Learn lists the route, but live validation rejected `Tool`, `KustoTool`, `PythonTool`, `HttpClientTool`, `LinkTool`, and `PythonFunctionTool` object types. | https://learn.microsoft.com/en-us/azure/sre-agent/api-reference |
| Extended connectors | `/api/v2/extendedAgent/connectors/{name}` | PUT, GET, PATCH, DELETE | Manage connectors through data-plane, especially MCP/Knowledge connectors. | https://learn.microsoft.com/en-us/azure/sre-agent/api-reference |
| Extended skills | `/api/v2/extendedAgent/skills/{name}` in Learn; Microsoft scripts also use `/api/v1/extendedAgent/skills`. | PUT, GET, PATCH, DELETE | Manage skills. | https://learn.microsoft.com/en-us/azure/sre-agent/api-reference and https://github.com/microsoft/sre-agent/tree/main/sreagent-templates |
| Extended common prompts | `/api/v2/extendedAgent/commonprompts/{name}` | PUT, GET, PATCH, DELETE | Manage shared prompts. | https://learn.microsoft.com/en-us/azure/sre-agent/api-reference |
| Extended scheduled tasks | `/api/v2/extendedAgent/scheduledtasks/{name}` in Microsoft scripts; Learn lists scheduled tasks in extended config table. | PUT, GET, PATCH, DELETE | Manage recurring agent jobs. | https://learn.microsoft.com/en-us/azure/sre-agent/api-reference and https://github.com/microsoft/sre-agent/tree/main/sreagent-templates |
| Extended incident filters | `/api/v2/extendedAgent/incidentFilters/{name}` in Microsoft scripts. | PUT, GET, PATCH, DELETE | Manage incident routing/response plans. | https://learn.microsoft.com/en-us/azure/sre-agent/api-reference and https://github.com/microsoft/sre-agent/pull/200 |
| Extended plugins | `/api/v2/extendedAgent/plugins/{name}` | PUT, GET, PATCH, DELETE | Manage plugin configurations. | https://learn.microsoft.com/en-us/azure/sre-agent/api-reference |
| Plugin marketplaces | `/api/v2/plugins/marketplaces` | POST in Microsoft templates | Register plugin marketplace documents. Schema not formally published in Learn. | https://github.com/microsoft/sre-agent/tree/main/sreagent-templates |
| Plugin installations | `/api/v2/plugins/installations` | POST in Microsoft templates | Register plugin installation metadata. Schema not formally published in Learn. | https://github.com/microsoft/sre-agent/tree/main/sreagent-templates |
| Incident platform indexing config | `/api/v2/incidents/indexing/{platformType}/configuration` | GET in export script; PATCH/PUT behavior inferred from templates | Platform-specific incident ingestion/indexing config. Schema not formally published in Learn. | https://github.com/microsoft/sre-agent/tree/main/sreagent-templates |

### 2.4 Runtime-Only API Surfaces

These are not IaC desired-state resources, but they are official Azure SRE Agent API surfaces.

| Surface | Path | Operations | Purpose | Source |
| --- | --- | --- | --- | --- |
| Threads and chat | `/api/v1/threads`, `/api/v1/threads/{threadId}`, `/api/v1/threads/{threadId}/messages` | GET, POST | Runtime conversations. | https://learn.microsoft.com/en-us/azure/sre-agent/api-reference |
| Approvals | `/api/v1/approvals/{threadId}`, `/api/v1/approvals/{threadId}/{id}/decision` | GET, POST | Runtime action approval decisions. | https://learn.microsoft.com/en-us/azure/sre-agent/api-reference |
| SignalR hub | `/agentHub` | SignalR client connection | Real-time streaming for chat/thread updates. | https://learn.microsoft.com/en-us/azure/sre-agent/api-reference |

## 3. Parameters and Values: Supporting Azure Resources

### 3.1 `azurerm_resource_group`

Official parameter source: https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/resource_group

Example:

```hcl
resource "azurerm_resource_group" "agent" {
  name     = "rg-contoso-sre-agent-dev"
  location = "swedencentral"
  tags = {
    workload = "azure-sre-agent"
  }
}
```

Line-by-line:

| Line | Parameter | What it is | Concrete purpose | Values and implications |
| --- | --- | --- | --- | --- |
| `resource "azurerm_resource_group" "agent"` | Terraform address | Terraform logical address. | Tracks the Azure resource group in state. | Name `agent` is local to Terraform; changing it changes state address, not Azure directly. |
| `name` | Azure resource group name | Azure container name. | Determines where SRE Agent support resources live. | String. Changing forces new resource group in Terraform. |
| `location` | Azure region | Region metadata for the resource group. | Used by Azure for regional placement metadata; support resources usually use same location. | Any Azure region for RG, but SRE Agent itself must use a supported SRE Agent region. Current SRE Agent regions from Learn: `australiaeast`, `canadacentral`, `eastus2`, `francecentral`, `koreacentral`, `swedencentral`, `uksouth`. Source: https://learn.microsoft.com/en-us/azure/sre-agent/supported-regions |
| `tags` | Key/value metadata | Governance metadata. | Supports cost, ownership, lifecycle, compliance tracking. | Up to Azure tag limits. Values are strings. |

Deploy command:

```bash
terraform -chdir=04-terraform apply
```

### 3.2 `azurerm_user_assigned_identity`

Official parameter source: https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/user_assigned_identity

Example:

```hcl
resource "azurerm_user_assigned_identity" "agent" {
  name                = "uai-contoso-sre-agent-dev"
  location            = azurerm_resource_group.agent.location
  resource_group_name = azurerm_resource_group.agent.name
  tags                = local.resource_tags
}
```

Line-by-line:

| Line | Parameter | What it is | Concrete purpose | Values and implications |
| --- | --- | --- | --- | --- |
| `resource "azurerm_user_assigned_identity" "agent"` | Terraform address | Tracks UAMI. | The SRE Agent uses this identity to access Azure resources without secrets. | Local Terraform name only. |
| `name` | UAMI name | Azure managed identity name. | Human-recognizable identity shown in IAM/portal. | String. Changing forces replacement. |
| `location` | Azure region | Region where identity resource exists. | Should align with agent resource group for governance. | Valid Azure location string. Changing forces replacement. |
| `resource_group_name` | Container RG | RG that owns the identity resource. | Keeps identity lifecycle close to agent. | Existing RG name. Changing forces replacement. |
| `tags` | Key/value metadata | Governance metadata. | Cost/owner/lifecycle tagging. | String map. |
| `isolation_scope` | Optional isolation scope | UAMI isolation mode. | Can scope identity isolation regionally. | Only documented value: `Regional`. Source: Terraform Registry. |

Deploy command:

```bash
terraform -chdir=04-terraform apply
```

### 3.3 `azurerm_role_assignment`

Official parameter source: https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/role_assignment

Azure SRE Agent permission source: https://learn.microsoft.com/en-us/azure/sre-agent/permissions

Example:

```hcl
resource "azurerm_role_assignment" "managed_scope" {
  scope                            = azurerm_resource_group.agent.id
  role_definition_name             = "Reader"
  principal_id                     = azurerm_user_assigned_identity.agent.principal_id
  principal_type                   = "ServicePrincipal"
  skip_service_principal_aad_check = true
}
```

Line-by-line:

| Line | Parameter | What it is | Concrete purpose | Values and implications |
| --- | --- | --- | --- | --- |
| `scope` | Azure scope ID | Scope where the role applies. | Defines blast radius: subscription, RG, or resource. | Resource ID string. Changing forces replacement. For SRE Agent, least privilege usually starts at managed resource groups. |
| `role_definition_name` | Built-in role name | Azure RBAC role. | Determines allowed actions. | Terraform accepts any built-in role name. Azure SRE Agent docs name: `Reader`, `Log Analytics Reader`, `Monitoring Reader`, `Monitoring Contributor`; API reference names user roles `SRE Agent Administrator`, `SRE Agent User`, `SRE Agent Reader`. |
| `role_definition_id` | Role ID alternative | Scoped role definition ID. | Use instead of name for custom roles or deterministic role identity. | Mutually exclusive with `role_definition_name`. |
| `principal_id` | Entra object ID | Identity receiving the role. | Usually UAMI principal ID for agent or user/group principal for agent admin/user/reader roles. | Object ID string. Changing forces replacement. |
| `principal_type` | Principal kind | Type of identity. | Helps Azure RBAC/AAD check. | Documented values: `User`, `Group`, `ServicePrincipal`. |
| `skip_service_principal_aad_check` | AAD replication bypass | Avoids transient AAD replication failures for new service principals. | Useful immediately after creating UAMI. | Boolean. Valid only for service principals. |
| `condition` / `condition_version` | ABAC condition | Role assignment condition. | Restricts role assignment behavior. | `condition_version` values: `1.0`, `2.0`; `condition` required if version is set. |

Azure SRE Agent role semantics:

| Role | Scope | Meaning | Source |
| --- | --- | --- | --- |
| `Reader` | Resource group/subscription/resource | Lets the agent inspect resource properties. | https://learn.microsoft.com/en-us/azure/sre-agent/permissions |
| `Log Analytics Reader` | Resource group | Lets the agent query logs/workspaces. | https://learn.microsoft.com/en-us/azure/sre-agent/permissions |
| `Monitoring Reader` | Resource group | Lets the agent access metrics and monitoring data. | https://learn.microsoft.com/en-us/azure/sre-agent/permissions |
| `Monitoring Contributor` | Subscription | Lets the agent acknowledge/close Azure Monitor alerts and update monitoring settings. | https://learn.microsoft.com/en-us/azure/sre-agent/permissions |
| `SRE Agent Administrator` | Agent resource | Full control over agent configuration and operations. | https://learn.microsoft.com/en-us/azure/sre-agent/api-reference |
| `SRE Agent User` | Agent resource | Chat, approve actions, manage threads. | https://learn.microsoft.com/en-us/azure/sre-agent/api-reference |
| `SRE Agent Reader` | Agent resource | Read-only access to agent config/threads. | https://learn.microsoft.com/en-us/azure/sre-agent/api-reference |

Deploy command:

```bash
terraform -chdir=04-terraform apply
```

### 3.4 `azurerm_log_analytics_workspace`

Official parameter source: https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/log_analytics_workspace

Example:

```hcl
resource "azurerm_log_analytics_workspace" "agent" {
  name                         = "law-contoso-sre-agent-dev"
  location                     = azurerm_resource_group.agent.location
  resource_group_name          = azurerm_resource_group.agent.name
  sku                          = "PerGB2018"
  retention_in_days            = 30
  local_authentication_enabled = false
  tags                         = local.resource_tags
}
```

Parameters:

| Parameter | What it is | Concrete purpose | Possible documented values and implications |
| --- | --- | --- | --- |
| `name` | Workspace name | Identifies the log workspace queried by SRE Agent. | 4-63 letters/digits/hyphen; hyphen not first/last. Replacement on change. |
| `location` | Region | Workspace region. | Azure location string. Replacement on change. |
| `resource_group_name` | Owning RG | Keeps workspace with SRE Agent support resources. | RG name string. Replacement on change. |
| `sku` | Pricing tier | Controls billing/capacity model. | `PerGB2018`, `PerNode`, `Premium`, `Standalone`, `Standard`, `CapacityReservation`, `LACluster`, `Unlimited`. `PerGB2018` is current default/recommended general tier; `CapacityReservation` has commitment implications; `LACluster` only when linked to a cluster. |
| `retention_in_days` | Data retention | How long logs stay queryable. | 30-730 days. Longer retention increases cost but improves investigation history. |
| `daily_quota_gb` | Ingestion cap | Prevents runaway ingestion cost. | Number in GB; default `-1` unlimited. |
| `local_authentication_enabled` | Local auth toggle | Controls non-Entra/local auth access. | Boolean. `false` enforces Entra-based posture. |
| `internet_ingestion_enabled` | Public ingestion access | Allows ingestion over public internet. | Boolean. Restrict only if private ingestion path exists. |
| `internet_query_enabled` | Public query access | Allows queries over public internet. | Boolean. Restrict only if private query path exists. |
| `reservation_capacity_in_gb_per_day` | Commitment tier capacity | Used with `CapacityReservation`. | `100`, `200`, `300`, `400`, `500`, `1000`, `2000`, `5000`, `10000`, `25000`, `50000`. |
| `identity.type` | Workspace managed identity | Adds identity to workspace. | `SystemAssigned`, `UserAssigned`; `identity_ids` required for UserAssigned. |
| `tags` | Metadata | Governance. | String map. |

Deploy command:

```bash
terraform -chdir=04-terraform apply
```

### 3.5 `azurerm_application_insights`

Official parameter source: https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/application_insights

Example:

```hcl
resource "azurerm_application_insights" "agent" {
  name                          = "appi-contoso-sre-agent-dev"
  location                      = azurerm_resource_group.agent.location
  resource_group_name           = azurerm_resource_group.agent.name
  application_type              = "web"
  workspace_id                  = azurerm_log_analytics_workspace.agent.id
  local_authentication_disabled = true
  tags                          = local.resource_tags
}
```

Parameters:

| Parameter | What it is | Concrete purpose | Possible documented values and implications |
| --- | --- | --- | --- |
| `name` | App Insights component name | Agent telemetry component. | String. Replacement on change. |
| `location` | Region | Component region. | Azure location. Replacement on change. |
| `resource_group_name` | Owning RG | Keeps telemetry with agent resources. | RG name string. Replacement on change. |
| `application_type` | App type classifier | Classifies telemetry component type. | `ios`, `java`, `MobileCenter`, `Node.JS`, `other`, `phone`, `store`, `web`. Values are case-sensitive; unmatched values treated as ASP.NET by Azure. |
| `workspace_id` | Log Analytics workspace ID | Enables workspace-based Application Insights. | Resource ID. Cannot be removed after set. |
| `daily_data_cap_in_gb` | Daily ingestion cap | Cost control. | Number; default 100 GB. |
| `retention_in_days` | Retention | Telemetry retention. | `30`, `60`, `90`, `120`, `180`, `270`, `365`, `550`, `730`; default 90. |
| `sampling_percentage` | Telemetry sampling | Controls data volume. | Percentage; default 100. Lower reduces cost but can reduce fidelity. |
| `disable_ip_masking` | Client IP masking | Privacy/network diagnostics behavior. | Boolean. Default masks real client IP as `0.0.0.0`; disabling logs real IP. |
| `local_authentication_disabled` | Disable non-Entra auth | Security hardening. | Boolean. `true` disables local auth. |
| `internet_ingestion_enabled` | Public ingestion | Public telemetry ingestion endpoint. | Boolean. |
| `internet_query_enabled` | Public query | Public query endpoint. | Boolean. |
| `tags` | Metadata | Governance. | String map. |

Deploy command:

```bash
terraform -chdir=04-terraform apply
```

## 4. `Microsoft.App/agents` Root Resource

Official ARM/Terraform schema: https://learn.microsoft.com/en-us/azure/templates/microsoft.app/agents?pivots=deployment-language-terraform

Official API reference: https://learn.microsoft.com/en-us/azure/sre-agent/api-reference

Example Terraform with direct values:

```hcl
resource "azapi_resource" "agent" {
  type                      = "Microsoft.App/agents@2026-01-01"
  name                      = "contoso-sre-agent-dev"
  parent_id                 = azurerm_resource_group.agent.id
  location                  = azurerm_resource_group.agent.location
  tags                      = local.resource_tags
  ignore_null_property      = true
  schema_validation_enabled = false

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.agent.id]
  }

  body = {
    properties = {
      actionConfiguration = {
        accessLevel = "Low"
        identity    = azurerm_user_assigned_identity.agent.id
        mode        = "Review"
      }

      agentIdentity = {
        initialSponsorGroupId = "00000000-0000-0000-0000-000000000000"
      }

      defaultModel = {
        name     = "gpt-5"
        provider = "MicrosoftFoundry"
      }

      knowledgeGraphConfiguration = {
        identity         = azurerm_user_assigned_identity.agent.id
        managedResources = [azurerm_resource_group.agent.id]
      }

      logConfiguration = {
        applicationInsightsConfiguration = {
          appId = azurerm_application_insights.agent.app_id
        }
      }

      monthlyAgentUnitLimit = 500
      upgradeChannel        = "Stable"
    }
  }
}
```

Parameter details:

| Parameter/path | What it is | Concrete purpose | Documented values and implications | Source |
| --- | --- | --- | --- | --- |
| `type` | ARM resource type + API version. | Tells AzAPI which ARM type/version to call. | `Microsoft.App/agents@2026-01-01` in ARM template reference. API reference currently uses `2025-05-01-preview`; pin and test because preview behavior can change. | Learn ARM + API reference |
| `name` | Agent resource name. | Identifies the agent in Azure and portal URL. | Required string matching `^[A-Za-z]([-A-Za-z0-9]{0,30}[A-Za-z0-9])$`. Changing recreates the resource. | ARM template reference |
| `parent_id` | Resource group ID. | Places the agent under a resource group. | ARM resource ID for RG. | AzAPI provider docs |
| `location` | Agent compute region. | Determines where agent compute runs. Does not limit resources it can access if permissions are granted. | Official supported regions as of Learn: `australiaeast`, `canadacentral`, `eastus2`, `francecentral`, `koreacentral`, `swedencentral`, `uksouth`. Microsoft template `main.bicep` currently allows `swedencentral`, `uksouth`, `eastus2`, `australiaeast`; Learn supported-regions page is broader. | supported-regions + official templates |
| `tags` | Azure tags. | Governance/cost/ownership metadata. | String map. | ARM template reference |
| `identity.type` | Managed identity type assigned to agent. | Determines how the resource authenticates to Azure. | `None`, `SystemAssigned`, `UserAssigned`, `SystemAssigned,UserAssigned` in ARM schema. In enterprise pattern use `UserAssigned`. | ARM template reference |
| `identity.identity_ids` | UAMI IDs. | Attaches a user-assigned identity. | List of UAMI resource IDs. Required when `type = UserAssigned`. | AzAPI provider docs |
| `actionConfiguration.accessLevel` | Action privilege level. | Controls whether agent is read-first or allowed broader action capability. | `Low`: read-first/safer posture. `High`: broader action capacity; use with explicit approval and RBAC review. | ARM template reference + permissions docs |
| `actionConfiguration.identity` | Identity used for actions. | Binds actions to UAMI/resource identity. | String identity resource ID. | ARM template reference |
| `actionConfiguration.mode` | Runtime action mode. | Controls how the agent handles actions. | ARM 2026 schema: `Autonomous`, `ReadOnly`, `Review`. API reference 2025 table says `Review`, `Automatic`, `ReadOnly`. Official templates use `Review`/`Automatic`. Use API-version-specific value and test. `Review` is safest; `Autonomous`/`Automatic` allow agent action without normal human approval flow depending on version. | ARM template reference + API reference + templates |
| `agentIdentity.initialSponsorGroupId` | Sponsor group object ID. | Seeds agent identity/admin sponsorship. | Required string. Usually Microsoft Entra group object ID. | ARM template reference |
| `agentSpaceId` | Agent space reference. | Associates agent with an agent space when used. | String. No enum published. | ARM template reference |
| `defaultModel.provider` | LLM provider. | Determines model backend, cost profile, availability, and data-residency posture. | ARM examples: `MicrosoftFoundry`, `Anthropic`. Create/setup UI names Azure OpenAI as GPT option; ARM uses MicrosoftFoundry. EU residency guidance favors Azure OpenAI/MicrosoftFoundry in Sweden Central; Anthropic excluded from EU Data Boundary. | ARM template + create/setup + pricing |
| `defaultModel.name` | Model name. | Selects model within provider. | String. ARM examples: `gpt-5`, `claude-opus-4-5`, `claude-sonnet-4-5`; templates use `Automatic`. Values can evolve by provider. | ARM template + templates |
| `incidentManagementConfiguration.type` | Incident platform type. | Configures platform the agent receives incidents from. | API reference known values: `PagerDuty`, `AzMonitor`, `ServiceNow`, `None`. | API reference |
| `incidentManagementConfiguration.connectionKey` | Incident platform secret/key. | Authenticates to incident platform. | Sensitive string. Should not be stored in plaintext state unless state is secured. | ARM template reference |
| `incidentManagementConfiguration.connectionName` | Connection name. | Names the incident connection. | String. No enum. | ARM template reference |
| `incidentManagementConfiguration.connectionUrl` | Platform URL. | Points at incident platform endpoint. | URL string. No enum. | ARM template reference |
| `incidentManagementConfiguration.oboUser` | On-behalf-of user. | User context for incident platform connection. | String. No enum. | ARM template reference |
| `knowledgeGraphConfiguration.identity` | Identity used for graph/context access. | Lets agent read managed resources/context. | Identity resource ID string. | API reference + ARM template |
| `knowledgeGraphConfiguration.managedResources` | Managed scope list. | Defines resources/resource groups the agent can access. | String array of ARM resource IDs. Region of resources can differ from agent region if permissions exist. | API reference + supported regions |
| `logConfiguration.applicationInsightsConfiguration.appId` | App Insights application ID. | Connects agent logging to Application Insights. | String/GUID from App Insights. | ARM template reference |
| `logConfiguration.applicationInsightsConfiguration.connectionString` | App Insights connection string. | Telemetry ingestion configuration. | Sensitive string; pass securely. | ARM template reference |
| `upgradeChannel` | Runtime update channel. | Controls stable vs preview agent runtime updates. | `Stable`: conservative production posture. `Preview`: earlier features with more change risk. | ARM template reference |
| `monthlyAgentUnitLimit` | Active-flow AAU cap. | Cost control for active processing; does not stop always-on charge. | Pricing page says allocation limit minimum 500, maximum 1,000,000 AAUs; API reference says number. | pricing-billing + API reference |
| `mcpServers` | MCP server URLs. | Adds MCP server URLs to the agent. | String array; no enum. | API reference |
| `vnetConfiguration.subnetResourceId` | VNet injection subnet. | Places agent network path in a subnet when supported. | Subnet ARM resource ID. | API reference |
| `experimentalSettings` | Feature flags. | Enables preview/experimental flags. | Object; schema not published. | API reference |
| Read-only `provisioningState` | Provisioning state. | Deployment status. | `Succeeded`, `Failed`, `InProgress`, `Canceled`, `Deleting`. | API reference |
| Read-only `agentEndpoint` | Data-plane endpoint. | Base URL for data-plane API. | Pattern documented by API reference. | API reference |
| Read-only `powerState` | Agent running state. | Indicates whether agent is running/stopped. | `Running`, `Stopped`. | API reference |
| Read-only `outboundIpAddresses` | Egress IPs. | Firewall allowlisting. | String array. | API reference |

Deploy with Terraform:

```bash
check-terraform-direct-values
terraform -chdir=04-terraform apply
```

Deploy with ARM REST:

```bash
az rest --method PUT \
  --url "https://management.azure.com/subscriptions/${SUB}/resourceGroups/${RG}/providers/Microsoft.App/agents/${AGENT}?api-version=2025-05-01-preview" \
  --body @agent-arm-body.json
```

Start/stop commands:

```bash
az rest --method POST --url "${ARM_BASE}/start?api-version=2025-05-01-preview"
az rest --method POST --url "${ARM_BASE}/stop?api-version=2025-05-01-preview"
```

## 5. `Microsoft.App/agents/connectors` and `/DataConnectors/{name}`

Official ARM/Terraform schema: https://learn.microsoft.com/en-us/azure/templates/microsoft.app/agents/connectors?pivots=deployment-language-terraform

Official API reference: https://learn.microsoft.com/en-us/azure/sre-agent/api-reference

Important naming note: Microsoft Learn ARM template page documents `Microsoft.App/agents/connectors@2026-01-01`; the API reference example for 2025 preview uses `/DataConnectors/{name}`. Use the path/API version matching your deployment mechanism.

Example Terraform:

```hcl
resource "azapi_resource" "log_analytics_connector" {
  type      = "Microsoft.App/agents/connectors@2026-01-01"
  name      = "log-analytics"
  parent_id = azapi_resource.agent.id

  body = {
    properties = {
      dataConnectorType = "LogAnalytics"
      dataSource        = azurerm_log_analytics_workspace.agent.id
      identity          = azurerm_user_assigned_identity.agent.id
    }
  }
}
```

Parameters:

| Parameter | What it is | Concrete purpose | Possible documented values and implications | Source |
| --- | --- | --- | --- | --- |
| `type` | ARM child type. | Deploys connector as child of agent. | `Microsoft.App/agents/connectors@2026-01-01`. | ARM template reference |
| `name` | Connector name. | Unique connector name under agent. | Pattern `^[A-Za-z]([-A-Za-z0-9]{0,30}[A-Za-z0-9])$`. | ARM template reference |
| `parent_id` | Agent resource ID. | Attaches connector to agent. | ID of `Microsoft.App/agents`. | ARM template reference |
| `properties.dataConnectorType` | Connector kind. | Selects connector behavior. | ARM schema says string. API reference table lists `Kusto`, `Mcp`, `Outlook`, `Teams`. Microsoft templates also use `AppInsights`, `LogAnalytics`, `MonitorClient`, `AzureMonitor`, `KnowledgeFile`, and MCP via `Mcp`. For ARM `2026-01-01`, `Kusto` is validated as Azure Data Explorer and requires an HTTPS Kusto URI; use `LogAnalytics` / `AppInsights` when `dataSource` is an Azure resource ID. | API reference + Microsoft templates + ARM validation |
| `properties.dataSource` | Data source/resource/endpoint. | Points connector at workspace, App Insights, Kusto URL, MCP placeholder, or other source. | String; sensitive in ARM schema. For Kusto can be cluster/workspace endpoint; for template connectors can be resource ID. | ARM template + API reference |
| `properties.endpoint` | Connector endpoint. | Endpoint separate from data source when needed. | String URL. No enum. | ARM template reference |
| `properties.extendedProperties` | Connector-specific settings. | Auth/config for MCP or partner connectors. | Object. No full JSON Schema published. Microsoft Dynatrace MCP example uses `type=http`, `endpoint=...`, `authType=BearerToken`, `bearerToken=${...}`, `partnerType=DynatraceMcp`. | Microsoft templates |
| `properties.identity` | Identity used to access source. | Controls source authentication identity. | String. API example uses `system`; Terraform example can use UAMI resource ID. | API reference + templates |

Known connector type semantics:

| Value | Meaning | Technical implication | Source |
| --- | --- | --- | --- |
| `Kusto` | Azure Data Explorer/Kusto connector. | ARM `2026-01-01` validates `dataSource` as an HTTPS Kusto URI in the form `https://cluster.kusto.windows.net/databasename`; don't use Log Analytics or App Insights resource IDs with this value. | API reference + ARM validation |
| `Mcp` | Model Context Protocol connector. | Adds external MCP tools such as Dynatrace/Datadog/custom servers. Requires endpoint/auth extended properties. | API reference + templates |
| `Outlook` | Outlook notifications. | Email notification/integration surface. Schema details not published. | API reference |
| `Teams` | Teams notifications. | Teams channel notification/integration surface. Schema details not published. | API reference |
| `AppInsights` | Application Insights connector from Microsoft templates. | Use when `dataSource` is an Application Insights resource ID. | Microsoft templates + ARM validation |
| `LogAnalytics` | Log Analytics connector from Microsoft templates. | Use when `dataSource` is a Log Analytics workspace resource ID. | Microsoft templates + ARM validation |
| `AzureMonitor` / `MonitorClient` | Azure Monitor connector from Microsoft templates. | Azure Monitor alert/incident integration. | Microsoft templates |
| `KnowledgeFile`, `KnowledgeText`, `KnowledgeWebPage` | Knowledge connector families observed in export scripts. | Represents knowledge items and downloadable content through connector API. | Microsoft templates |

Deploy with Terraform:

```bash
terraform -chdir=04-terraform apply
```

Deploy with ARM REST direct properties:

```bash
az rest --method PUT \
  --url "${ARM_BASE}/DataConnectors/my-kusto?api-version=2025-05-01-preview" \
  --body '{"properties":{"name":"my-kusto","dataConnectorType":"Kusto","dataSource":"https://mycluster.eastus2.kusto.windows.net","identity":"system"}}'
```

Deploy MCP connector with data-plane:

```bash
TOKEN=$(az account get-access-token --resource https://azuresre.dev --query accessToken -o tsv)
curl -fsS -X PUT \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  "${ENDPOINT}/api/v2/extendedAgent/connectors/dynatrace" \
  --data @mcp-connector.json
```

## 6. Generic ARM Envelope Sub-Resources

Official source: https://learn.microsoft.com/en-us/azure/sre-agent/api-reference

For all non-connector ARM sub-resources listed by the API reference, the body format is:

```json
{
  "properties": {
    "value": "<base64-encoded-json-spec>"
  }
}
```

Parameters:

| Parameter | What it is | Concrete purpose | Values and implications |
| --- | --- | --- | --- |
| `properties.value` | Base64-encoded JSON document. | Wraps the actual sub-resource spec so ARM can store opaque agent configuration. | Base64 string. Actual JSON schema varies by resource and is not fully published for all surfaces. |
| `{name}` path segment | Sub-resource name. | Unique sub-resource ID under agent. | String. Use stable lower-case/hyphen naming for GitOps. |

Generic deploy command:

```bash
SPEC='{"metadata":{"name":"example"},"spec":{"description":"example"}}'
ENCODED=$(printf '%s' "$SPEC" | base64 -w 0)
az rest --method PUT \
  --url "${ARM_BASE}/tools/example?api-version=2025-05-01-preview" \
  --body "{\"properties\":{\"value\":\"${ENCODED}\"}}"
```

The same envelope pattern is documented for `/skills/{name}`, `/subagents/{name}`, `/tools/{name}`, `/scheduledTasks/{name}`, `/incidentFilters/{name}`, `/hooks/{name}`, and `/commonPrompts/{name}`. Live validation in an external tenant returned `Agent Extensions are not available for this tenant. This feature is restricted to internal tenants only.` for `/skills/{name}`, and the public Microsoft issue [microsoft/sre-agent#199](https://github.com/microsoft/sre-agent/issues/199) reports the same for tools, skills, scheduledTasks, and incidentFilters. Operationally, use the data-plane `extendedAgent` routes for these Agent Extension surfaces until Microsoft unblocks or changes the ARM child endpoints for external tenants.

## 7. Data-Plane Configuration Surfaces

All data-plane calls require a token with audience `https://azuresre.dev`.

Official source: https://learn.microsoft.com/en-us/azure/sre-agent/api-reference

Token and endpoint:

```bash
ENDPOINT=$(az rest --method GET \
  --url "${ARM_BASE}?api-version=2025-05-01-preview" \
  --query properties.agentEndpoint -o tsv)

TOKEN=$(az account get-access-token \
  --resource https://azuresre.dev \
  --query accessToken -o tsv)
```

### 7.1 Skills

Official path: `/api/v2/extendedAgent/skills/{name}` in Learn; Microsoft scripts also use `/api/v1/extendedAgent/skills`.

Microsoft recipe example:

```yaml
metadata:
  name: investigate-azure-alerts
  description: Investigate fired Azure Monitor alerts.
  spec:
    tools:
      - RunAzCliReadCommands
      - QueryAppInsightsUsingAppId
      - QueryLogAnalyticsByWorkspaceId
skillContent: skills/investigate-azure-alerts.md
additionalFiles: []
```

Parameters:

| Parameter | Meaning | Concrete effect | Values |
| --- | --- | --- | --- |
| `metadata.name` | Skill ID. | Name used by subagents/agent to reference skill. | String. No enum. |
| `metadata.description` | Human-readable purpose. | Helps operators and agents understand skill scope. | String. |
| `metadata.spec.tools` | Allowed tools. | Restricts toolset available to the skill. | Tool names. Values depend on enabled tools/connectors. |
| `skillContent` | Markdown file path/content. | Instruction body for skill. | File path or string depending assembler. |
| `additionalFiles` | Supporting files. | Adds context/resources to skill. | Array. Schema not fully published. |

Deploy command:

```bash
curl -fsS -X PUT \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  "${ENDPOINT}/api/v2/extendedAgent/skills/investigate-azure-alerts" \
  --data @skill-envelope.json
```

### 7.2 Subagents

Official path: `/api/v2/extendedAgent/agents/{name}`.

Example:

```yaml
metadata:
  name: alert-investigator
spec:
  instructions: subagents/alert-investigator.instructions.md
  handoffDescription: Investigates Azure Monitor alerts.
  handoffs: []
  tools:
    - RunAzCliReadCommands
  agentType: Autonomous
  temperature: 0.2
  enableSkills: true
  allowedSkills:
    - investigate-azure-alerts
```

Parameters:

| Parameter | Meaning | Concrete effect | Values |
| --- | --- | --- | --- |
| `metadata.name` | Subagent ID. | Addressable specialist agent name. | String. |
| `spec.instructions` | Instructions file/content. | System instructions for subagent. | Markdown path/string. |
| `spec.handoffDescription` | Routing hint. | Helps primary agent decide when to hand off. | String. |
| `spec.handoffs` | Allowed handoffs. | Other subagents this one can hand off to. | Array of names. |
| `spec.tools` | Tool allow-list. | Restricts available tools. | Tool names. |
| `spec.agentType` | Agent execution type. | Controls behavior style. | Examples show `Autonomous`; formal enum not published. |
| `spec.temperature` | Model sampling temperature. | Lower values produce more deterministic behavior. | Number. Range not published by SRE Agent docs. |
| `spec.enableSkills` | Skill enablement. | Enables skill selection. | Boolean. |
| `spec.allowedSkills` | Skill allow-list. | Limits which skills subagent can use. | Array of skill names. |

Deploy command:

```bash
curl -fsS -X PUT \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  "${ENDPOINT}/api/v2/extendedAgent/agents/alert-investigator" \
  --data @subagent-envelope.json
```

### 7.3 Tools

Official path: `/api/v2/extendedAgent/tools/{name}`.

Tool schema is listed as a surface in Learn, but detailed request schema is not formally published. Live validation on 2026-06-11 rejected the documented generic `Tool` type and the template-comment tool type names `KustoTool`, `PythonTool`, `HttpClientTool`, `LinkTool`, and `PythonFunctionTool` with `InvalidObjectType`. Keep tool manifests as source-of-truth documentation until Microsoft publishes or enables an accepted schema.

Documented generic data-plane envelope used by Microsoft scripts:

```json
{
  "name": "azure-resource-graph-readonly",
  "type": "Tool",
  "tags": [],
  "properties": {
    "description": "Read-only Azure Resource Graph helper",
    "access": "read_only"
  }
}
```

Deploy command:

```bash
curl -fsS -X PUT \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  "${ENDPOINT}/api/v2/extendedAgent/tools/azure-resource-graph-readonly" \
  --data @tool-envelope.json
```

### 7.4 Common Prompts

Official path: `/api/v2/extendedAgent/commonprompts/{name}`.

Example:

```yaml
metadata:
  name: safety-rules
spec:
  prompt: |
    ## Safety rules
    - Never delete production resources without explicit approval.
```

Parameters:

| Parameter | Meaning | Concrete effect | Values |
| --- | --- | --- | --- |
| `metadata.name` | Prompt ID. | Reusable prompt name. | String. |
| `spec.prompt` | Prompt body. | Shared instruction injected into agent context. | Markdown/text string. |

Deploy command:

```bash
curl -fsS -X PUT \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  "${ENDPOINT}/api/v2/extendedAgent/commonprompts/safety-rules" \
  --data @common-prompt-envelope.json
```

### 7.5 Hooks

Official Learn path: `/api/v2/extendedAgent/hooks/{hookName}`.

Example from Microsoft templates:

```yaml
metadata:
  name: deny-prod-deletes
spec:
  eventType: PreToolUse
  hook:
    type: prompt
    prompt: If the tool targets production, deny the action.
    matcher: ^(delete_|remove_).*
  permissionDecision: deny
  enabled: true
```

Parameters:

| Parameter | Meaning | Concrete effect | Values |
| --- | --- | --- | --- |
| `metadata.name` | Hook name. | Identifies governance hook. | String. |
| `spec.eventType` | Trigger event. | Defines lifecycle moment for hook. | Examples show `PreToolUse`; blog/docs mention hook governance but formal enum is not published in Learn. |
| `spec.hook.type` | Hook implementation type. | Defines how the hook evaluates. | Example: `prompt`. Formal enum not published. |
| `spec.hook.prompt` | Hook instruction. | Natural-language policy used by hook. | String. |
| `spec.hook.matcher` | Tool/action regex. | Selects actions/tools hook applies to. | Regex string. |
| `spec.permissionDecision` | Default decision. | Governs allow/deny behavior. | Examples: `deny`, `allow`. |
| `spec.enabled` | Enable flag. | Turns hook on/off. | Boolean. |

Deploy command:

```bash
curl -fsS -X PUT \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  "${ENDPOINT}/api/v2/extendedAgent/hooks/deny-prod-deletes" \
  --data @hook-envelope.json
```

### 7.6 Scheduled Tasks

Learn lists scheduled tasks both as control-plane sub-resource and extended agent config. Microsoft `apply-extras.sh` uses data-plane PUT to `/api/v2/extendedAgent/scheduledtasks/{name}` and normalizes fields.

Example:

```yaml
metadata:
  name: daily-health-check
spec:
  description: Daily 8am health summary
  schedule: 0 8 * * *
  prompt: Summarize the last 24h of incidents and health.
  enabled: true
  mode: Review
```

Parameters:

| Parameter | Meaning | Concrete effect | Values |
| --- | --- | --- | --- |
| `metadata.name` | Scheduled task name. | Unique recurring automation name. | String. |
| `spec.description` | Human description. | Explains purpose. | String. |
| `spec.schedule` / `cronExpression` | Cron expression. | Defines recurrence. | Microsoft examples use five-field cron such as `0 8 * * *`. Full grammar not published. |
| `spec.prompt` / `agentPrompt` | Task prompt. | Work the agent performs on schedule. | String. |
| `spec.enabled` / `isEnabled` | Enable flag. | Controls whether task runs. | Boolean. |
| `spec.mode` / `agentMode` | Execution mode. | Controls review/autonomy posture. | Examples show `Review`; formal enum not published for scheduled task schema. |

Deploy command:

```bash
curl -fsS -X PUT \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  "${ENDPOINT}/api/v2/extendedAgent/scheduledtasks/daily-health-check" \
  --data @scheduled-task-envelope.json
```

### 7.7 Incident Platforms

Learn documents `incidentManagementConfiguration.type` on the agent. Microsoft templates also use `automations/incident-platforms/*.yaml` and patch the agent incident management configuration.

Examples:

```yaml
name: azure-monitor
spec:
  platformType: AzMonitor
  displayName: Azure Monitor Alerts
  description: Receives Azure Monitor fired alerts as incidents
```

```yaml
name: pagerduty
spec:
  platformType: PagerDuty
  connectionKey: "${PAGERDUTY_API_KEY}"
```

Parameters:

| Parameter | Meaning | Concrete effect | Values |
| --- | --- | --- | --- |
| `name` | Local config name. | File/resource identity. | String. |
| `spec.platformType` | Incident platform. | Sets platform for incident ingestion. | Official known values: `PagerDuty`, `AzMonitor`, `ServiceNow`, `None`. |
| `spec.connectionKey` | Platform secret. | Authenticates PagerDuty/ServiceNow. | Sensitive string. Avoid Terraform state. |
| `spec.displayName` | Display label. | UI/operator display. | String. |
| `spec.description` | Description. | Documents platform purpose. | String. |

Deploy command via ARM PATCH:

```bash
az rest --method PATCH \
  --url "${ARM_BASE}?api-version=2025-05-01-preview" \
  --body '{"properties":{"incidentManagementConfiguration":{"type":"AzMonitor","connectionName":"azmonitor"}}}'
```

### 7.8 Incident Filters / Response Plans

Official control-plane path: `/incidentFilters/{name}`. Microsoft templates apply response plans through data-plane extended config.

Live validation note: the response plan must match the active `incidentManagementConfiguration.type`. For example, an `incidentPlatform: AzMonitor` filter is rejected while the agent platform is `None`; apply the `AzMonitor` incident platform first and wait for the platform PATCH to complete before applying filters.

Example:

```yaml
metadata:
  name: azmon-sev01
spec:
  incidentPlatform: AzMonitor
  isEnabled: true
  priorities:
    - Sev0
    - Sev1
  handlingAgent: alert-investigator
  agentMode: Autonomous
  deepInvestigationEnabled: false
  maxAutomatedInvestigationAttempts: 3
```

Parameters:

| Parameter | Meaning | Concrete effect | Values |
| --- | --- | --- | --- |
| `metadata.name` | Filter/response plan name. | Identifies routing rule. | String. |
| `spec.incidentPlatform` | Platform to match. | Routes only matching incident platform. | Examples: `AzMonitor`, `PagerDuty`. API property also supports `ServiceNow`. |
| `spec.isEnabled` | Enable flag. | Activates/deactivates rule. | Boolean. |
| `spec.priorities` | Severity/priority match list. | Filters incident severity. | Examples: Azure Monitor `Sev0`, `Sev1`; PagerDuty `P1`, `P2`. Full enum is platform-specific and not centrally published. |
| `spec.handlingAgent` | Subagent name. | Assigns specialist subagent. | String; empty/default can use default handler. |
| `spec.agentMode` | Automation mode. | Controls automated investigation/remediation posture. | Examples: `Autonomous`; formal enum not published for this schema. |
| `spec.deepInvestigationEnabled` | Investigation depth flag. | Enables deeper investigation behavior. | Boolean. |
| `spec.maxAutomatedInvestigationAttempts` | Retry/attempt cap. | Limits repeated automated investigations. | Integer. |
| `spec.customInstructions` | Extra instructions. | Adds response-plan-specific prompt. | String; Microsoft export merges this from incident handlers. |

Deploy command via ARM envelope:

```bash
SPEC=$(cat incident-filter.json)
ENCODED=$(printf '%s' "$SPEC" | base64 -w 0)
az rest --method PUT \
  --url "${ARM_BASE}/incidentFilters/azmon-sev01?api-version=2025-05-01-preview" \
  --body "{\"properties\":{\"value\":\"${ENCODED}\"}}"
```

Deploy command via data-plane extended endpoint used by Microsoft templates:

```bash
curl -fsS -X PUT \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  "${ENDPOINT}/api/v2/extendedAgent/incidentFilters/azmon-sev01" \
  --data @incident-filter-envelope.json
```

### 7.9 Repositories

Official source: https://learn.microsoft.com/en-us/azure/sre-agent/api-reference

Create/setup source says GitHub and Azure DevOps are supported: https://learn.microsoft.com/en-us/azure/sre-agent/create-and-set-up

Example:

```yaml
name: github-repo
spec:
  url: https://github.com/contoso/example-service
  branch: main
  description: Connected GitHub repository
```

Parameters:

| Parameter | Meaning | Concrete effect | Values |
| --- | --- | --- | --- |
| `repoName` path / `name` | Repo connection name. | Unique repository connector name. | String. |
| `properties.url` / `spec.url` | Repository URL. | Source code context for investigations. | GitHub or Azure DevOps URL. |
| `properties.type` | Repo platform. | Selects auth/connectivity behavior. | API example uses `GitHub`; create/setup says GitHub and Azure DevOps are supported. |
| `properties.branch` / `spec.branch` | Branch. | Default branch indexed/analyzed. | Branch name string; examples use `main`. |
| `auth` | Authentication config. | OAuth/PAT/other repo auth. | Full schema not published; Microsoft templates support OAuth flow and PAT env variables. |

Deploy command:

```bash
curl -fsS -X PUT \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  "${ENDPOINT}/api/v2/repos/example-service" \
  --data '{"properties":{"url":"https://github.com/contoso/example-service","type":"GitHub","branch":"main"}}'
```

Connectivity test:

```bash
curl -fsS -X POST \
  -H "Authorization: Bearer ${TOKEN}" \
  "${ENDPOINT}/api/v2/repos/example-service/test"
```

### 7.10 Knowledge Files / Agent Memory

Official source: https://learn.microsoft.com/en-us/azure/sre-agent/api-reference

Parameters and limits:

| Parameter/surface | Meaning | Concrete effect | Values |
| --- | --- | --- | --- |
| Multipart form `files=@...` | Uploaded documents. | Adds runbooks/docs/reference material to agent memory. | API limit: max 100 MB total request, 16 MB per file. |
| `fileName` path | File to delete. | Deletes one memory document. | URL-encoded file name. |
| `triggerIndexing` query observed in templates | Whether upload triggers indexing. | Controls immediate indexing behavior. | Boolean-like query value; not explicitly documented on Learn upload table. |

Upload command:

```bash
curl -fsS -X POST \
  -H "Authorization: Bearer ${TOKEN}" \
  -F "files=@06-sre-agent-configuration/knowledge/files/example-runbook.md" \
  "${ENDPOINT}/api/v1/agentmemory/upload"
```

Status commands:

```bash
curl -fsS -H "Authorization: Bearer ${TOKEN}" "${ENDPOINT}/api/v1/agentmemory/status"
curl -fsS -H "Authorization: Bearer ${TOKEN}" "${ENDPOINT}/api/v1/agentmemory/indexer-status"
```

Delete commands:

```bash
curl -fsS -X DELETE -H "Authorization: Bearer ${TOKEN}" \
  "${ENDPOINT}/api/v1/agentmemory/document/example-runbook.md"

curl -fsS -X DELETE -H "Authorization: Bearer ${TOKEN}" \
  "${ENDPOINT}/api/v1/agentmemory/documents"
```

### 7.11 HTTP Triggers

Official source: https://learn.microsoft.com/en-us/azure/sre-agent/api-reference

Learn publishes operations but not full request schema.

Operations:

| Operation | Path | Meaning |
| --- | --- | --- |
| Create | `POST /api/v1/httptriggers/create` | Creates HTTP trigger and server-side URL. |
| List | `GET /api/v1/httptriggers` | Lists triggers. |
| Execute | `POST /api/v1/httptriggers/{triggerId}/execute` | Executes trigger internally. |
| Public webhook | `POST /api/v1/httptriggers/trigger/{triggerId}` | Public webhook endpoint; no auth required according to Learn. |

Deploy/create command:

```bash
curl -fsS -X POST \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  "${ENDPOINT}/api/v1/httptriggers/create" \
  --data @http-trigger.json
```

Important: Because request schema is not formally published in Microsoft Learn, keep HTTP trigger automation behind a customer-specific validation gate.

### 7.12 Plugin Configurations, Marketplaces, and Installations

Learn publishes `/api/v2/extendedAgent/plugins/{name}`. Microsoft templates additionally use `/api/v2/plugins/marketplaces` and `/api/v2/plugins/installations`.

Plugin config example envelope:

```json
{
  "name": "example-plugin",
  "type": "Plugin",
  "tags": [],
  "properties": {
    "enabled": true,
    "configuration": {
      "mode": "readOnly"
    }
  }
}
```

Parameters:

| Parameter | Meaning | Concrete effect | Values |
| --- | --- | --- | --- |
| `name` | Plugin config name. | Unique config identity. | String. |
| `type` | Config type. | Tells extended API resource kind. | Microsoft templates default to `Plugin`; full enum not published. |
| `tags` | Metadata tags. | Optional classification. | Array. |
| `properties` | Plugin-specific configuration. | Actual plugin settings. | Object. No formal schema published. |

Deploy plugin config:

```bash
curl -fsS -X PUT \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  "${ENDPOINT}/api/v2/extendedAgent/plugins/example-plugin" \
  --data @plugin-config.json
```

Deploy marketplace document:

```bash
curl -fsS -X POST \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  "${ENDPOINT}/api/v2/plugins/marketplaces" \
  --data @plugin-marketplace.json
```

Deploy installation document:

```bash
curl -fsS -X POST \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  "${ENDPOINT}/api/v2/plugins/installations" \
  --data @plugin-installation.json
```

## 8. Runtime APIs

These are official API surfaces but not deployable IaC resources.

| Surface | Command |
| --- | --- |
| List threads | `curl -H "Authorization: Bearer ${TOKEN}" "${ENDPOINT}/api/v1/threads"` |
| Get thread | `curl -H "Authorization: Bearer ${TOKEN}" "${ENDPOINT}/api/v1/threads/${THREAD_ID}"` |
| Send message | `curl -X POST -H "Authorization: Bearer ${TOKEN}" -H "Content-Type: application/json" "${ENDPOINT}/api/v1/threads/${THREAD_ID}/messages" --data @message.json` |
| Get messages | `curl -H "Authorization: Bearer ${TOKEN}" "${ENDPOINT}/api/v1/threads/${THREAD_ID}/messages"` |
| List approvals | `curl -H "Authorization: Bearer ${TOKEN}" "${ENDPOINT}/api/v1/approvals/${THREAD_ID}"` |
| Approve/reject | `curl -X POST -H "Authorization: Bearer ${TOKEN}" -H "Content-Type: application/json" "${ENDPOINT}/api/v1/approvals/${THREAD_ID}/${APPROVAL_ID}/decision" --data @decision.json` |

Source: https://learn.microsoft.com/en-us/azure/sre-agent/api-reference

## 9. Recommended Deployment Order

Official source: https://learn.microsoft.com/en-us/azure/sre-agent/deploy-iac

1. Deploy supporting Azure resources and `Microsoft.App/agents` through Terraform/AzAPI or ARM/Bicep.
2. Deploy Terraform/ARM-supported connectors.
3. Resolve `properties.agentEndpoint` from ARM.
4. Acquire data-plane token with `https://azuresre.dev` audience.
5. Deploy data-plane-only items: repos, hooks, knowledge, HTTP triggers, plugin configurations, and any endpoint whose schema is not exposed through ARM.
6. Verify live state using GET/list endpoints.

## 10. Known Official Documentation Gaps

| Gap | Why it matters | Safe handling |
| --- | --- | --- |
| Full JSON schema for skills/subagents/tools/hooks/common prompts not published as OpenAPI/JSON Schema. | Payloads can drift between preview API versions. | Use Microsoft templates as implementation evidence; pin API version; validate in disposable agent. |
| `actionConfiguration.mode` differs by source: ARM 2026 says `Autonomous`, API 2025 says `Automatic`, templates use `Automatic`. | Wrong value can fail deployment or change autonomy semantics. | Use value matching selected API version and run live preflight. Default to `Review`. |
| Connector `dataConnectorType` is typed as string in ARM template; multiple known values appear across API reference and templates. | No single authoritative enum list for every connector family. | Use documented examples; treat partner connectors as customer-specific. |
| HTTP trigger request schema not published in Learn. | Cannot safely claim all possible fields. | Use only after live validation; avoid customer release without endpoint-specific test. |
| Plugin marketplace/installation schemas not in Learn API reference. | Plugin automation may break. | Mark experimental/customer-specific until Microsoft publishes schema. |
| Incident platform indexing config endpoint appears in Microsoft templates but not Learn API reference. | Useful for export/import but not formally documented. | Prefer root `incidentManagementConfiguration` for platform type; validate data-plane indexing separately. |

## 11. Minimal Command Set

```bash
# Terraform-managed resources
check-terraform-direct-values
terraform -chdir=04-terraform init
terraform -chdir=04-terraform plan
terraform -chdir=04-terraform apply

# ARM agent read
ARM_BASE="https://management.azure.com/subscriptions/${SUB}/resourceGroups/${RG}/providers/Microsoft.App/agents/${AGENT}"
az rest --method GET --url "${ARM_BASE}?api-version=2025-05-01-preview"

# Data plane setup
ENDPOINT=$(az rest --method GET --url "${ARM_BASE}?api-version=2025-05-01-preview" --query properties.agentEndpoint -o tsv)
TOKEN=$(az account get-access-token --resource https://azuresre.dev --query accessToken -o tsv)

# Data-plane verify examples
curl -H "Authorization: Bearer ${TOKEN}" "${ENDPOINT}/api/v2/repos"
curl -H "Authorization: Bearer ${TOKEN}" "${ENDPOINT}/api/v2/extendedAgent/hooks"
curl -H "Authorization: Bearer ${TOKEN}" "${ENDPOINT}/api/v1/agentmemory/status"
```
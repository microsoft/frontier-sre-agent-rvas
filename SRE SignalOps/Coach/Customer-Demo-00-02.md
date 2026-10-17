# Customer Demo Runbook - Deployment stages 00, 01, and 02

> COACHES ONLY - Use this as a talk track. Do not display access tokens or connection strings.

## Demo Goal

Show how SignalOps builds an isolated, observable Grubify workload, adds an Azure SRE Agent with governed access, and connects the agent to operational evidence and approval-gated incident routing.

The three-part story is:

1. Deployment stage 00: deploy and prove the customer workload.
2. Deployment stage 01: add the SRE Agent with a controlled identity and scope.
3. Deployment stage 02: connect evidence, register the incident handler and response plan, and state honestly what is populated.

## Resolve the Demo Environment Before the Call

From the repository root, select the environment you intend to demonstrate:

```powershell
$Lab = & '.\SRE SignalOps\Scripts\Get-SignalOpsContext.ps1' -EnvironmentName signalops-core
az account set --subscription $Lab.AZURE_SUBSCRIPTION_ID
$SubscriptionId = $Lab.AZURE_SUBSCRIPTION_ID
$WorkloadResourceGroup = $Lab.AZURE_RESOURCE_GROUP
$AgentResourceGroup = $Lab.AGENT_RESOURCE_GROUP
$AgentName = $Lab.SRE_AGENT_NAME
$AgentId = $Lab.SRE_AGENT_ID
$FrontendUrl = $Lab.FRONTEND_URL
$ApiUrl = $Lab.API_BASE_URL.TrimEnd('/')

$Lab | Format-List
```

Use the returned URLs and IDs to open the resources below. Do not reuse an
endpoint or subscription from a previous demonstration.

| Purpose | Link |
|---|---|
| SignalOps deployment guide | [Bicep deployment](../Deployment/Bicep/README.md) |
| Grubify customer experience | `$FrontendUrl` |
| API health check | `"$ApiUrl/health"` |
| Restaurant business endpoint | `"$ApiUrl/api/restaurants"` |
| Workload resource group | `$WorkloadResourceGroup` in the Azure portal |
| Agent resource group | `$AgentResourceGroup` in the Azure portal |
| SRE Agent resource | `$AgentId` in the Azure portal |
| Workload Application Insights | `$Lab.APPLICATIONINSIGHTS_NAME` in the workload resource group |
| Workload Log Analytics | `$Lab.LOG_ANALYTICS_WORKSPACE_ID` in the Azure portal |

Do not open the SRE Agent endpoint directly in an anonymous browser. It is an authenticated API and correctly returns `unauthorized` without an Azure SRE token.

## Opening - 1 Minute

Say:

> Grubify has two independent application components. Azure Container Apps serves the React frontend and the ASP.NET Core API. The browser calls the API directly. The SRE Agent is outside the customer request path: it observes evidence and acts only through its managed identity, configured scope, and action policy.

Set expectations:

- The API uses in-memory sample data. There is no database, queue, cache, or payment dependency in this core deployment.
- A green frontend HTTP response does not prove that restaurant data loads.
- Architecture describes intent; live checks establish the observed baseline.

## Deployment stage 00 - Workload and Customer Path - 5 Minutes

### Show

1. Open the Grubify frontend.
2. Point out that five restaurant cards load.
3. Open `/health` and show HTTP `200` with a healthy response.
4. Open `/api/restaurants` and show the business data returned by the API.
5. Open the selected workload resource group in the Azure portal.
6. Show the two Container Apps, Container Apps environment, ACR, workload identity resources, Log Analytics, and Application Insights.
7. Open each Container App and show `Running`, its latest ready revision, ingress FQDN, and ACR image.

### Say

> Stage 00 creates a new azd-owned workload from Bicep. The environment token in every name gives us a clear ownership boundary. Remote ACR builds deploy the API and frontend independently, and workspace-backed observability is present from the start.

### Key Proof

```powershell
az containerapp list --resource-group $WorkloadResourceGroup `
  --query '[].{Name:name,State:properties.runningStatus,Image:properties.template.containers[0].image,FQDN:properties.configuration.ingress.fqdn}' `
  -o table

Invoke-WebRequest -Uri "$ApiUrl/health" `
  -UseBasicParsing | Select-Object StatusCode
```

Expected:

- Both Container Apps are `Running`.
- Both images come from the selected environment's registry, `$Lab.AZURE_CONTAINER_REGISTRY_ENDPOINT`.
- API `/health` returns `200`.
- The frontend shows five restaurants.

### Customer Value

- Repeatable environment deployment with azd and Bicep.
- Independent scaling and release boundaries for frontend and API.
- Managed identity for ACR image pulls instead of registry credentials.
- Operational telemetry is designed into the workload, not added after an incident.

## Deployment stage 01 - Agent, Identity, and Governance - 5 Minutes

### Show

1. Open the selected agent resource group in the Azure portal.
2. Show the SRE Agent, its user-assigned identity, separate Log Analytics workspace, and separate Application Insights component.
3. Open the SRE Agent and show provisioning `Succeeded`, power `Running`, action mode `Autonomous`, and access level `High`.
4. Show managed resources: subscription, isolated workload resource group, and workload Log Analytics workspace.
5. Open the managed identity's Azure role assignments.

### Say

> Deployment stage 01 adds the reasoning and action plane without placing the agent in the customer request path. Autonomous and High are explicit workshop settings. The safety boundary comes from identity and scope: broad subscription access is monitoring-only, while Contributor is limited to the isolated Grubify resource group.

### Key Proof

```powershell
$Agent = az resource show --ids $AgentId --api-version '2026-01-01' |
  ConvertFrom-Json

$Agent.properties | Select-Object provisioningState,powerState,agentEndpoint,actionConfiguration
$Agent.properties.knowledgeGraphConfiguration.managedResources

$PrincipalId = ($Agent.identity.userAssignedIdentities.PSObject.Properties |
  Select-Object -First 1).Value.principalId

az role assignment list --assignee-object-id $PrincipalId --all `
  --query '[].{Role:roleDefinitionName,Scope:scope}' -o table
```

Expected roles:

| Role | Scope |
|---|---|
| Reader | Selected workload resource group |
| Monitoring Reader | Selected workload resource group |
| Log Analytics Reader | Selected workload resource group |
| Contributor | Selected workload resource group only |
| Monitoring Contributor | Subscription |

### Customer Value

- The agent can correlate platform and application evidence.
- Managed identity removes stored Azure credentials.
- Resource scope limits the write blast radius.
- Control-plane permissions and action mode can be explained and audited separately.

## Deployment stage 02 - Evidence Connectors - 4 Minutes

### Show

1. Show the two child connectors: `log-analytics` and `application-insights`.
2. Show that both report provisioning `Succeeded` and use the agent identity.
3. Show Agent Memory status and indexer status.
4. Show all three Review specialists (`aca-app-incident-handler`, `network-traffic-analyst`, `cost-optimization-agent`) and the enabled `sample-food-http-errors` response plan. Explain that azd's postprovision hook registers these data-plane resources after the two ARM connectors are provisioned.
5. Confirm the plan covers `Sev0` through `Sev4`, matches `grubify`, uses `Review`, and allows one automated attempt.
6. State the current evidence gaps before showing repository and file results.
7. Open workload Application Insights and discuss telemetry ingestion separately from infrastructure health.

### Key Proof - Connectors

```powershell
$ConnectorUrl = "https://management.azure.com$AgentId/connectors?api-version=2026-01-01"

az rest --method GET --url $ConnectorUrl `
  --query 'value[].{Name:name,Type:properties.dataConnectorType,State:properties.provisioningState}' `
  -o table
```

Expected:

| Connector | Type | State |
|---|---|---|
| `log-analytics` | `LogAnalytics` | `Succeeded` |
| `application-insights` | `AppInsights` | `Succeeded` |

The current preview API may return `dataSource: null` on reads even though the deployment input contains the resource ID. Do not claim that a null readback means the connector failed; show provisioning state, identity, deployment definition, and target resource together.

### Key Proof - Authenticated Agent Evidence

```powershell
$Endpoint = $Agent.properties.agentEndpoint.TrimEnd('/')
$Token = (az account get-access-token `
  --resource 'https://azuresre.dev' `
  --query accessToken -o tsv).Trim()
$Headers = @{ Authorization = "Bearer $Token" }

Invoke-RestMethod "$Endpoint/api/v2/repos" -Headers $Headers
Invoke-RestMethod "$Endpoint/api/v1/agentmemory/status" -Headers $Headers
Invoke-RestMethod "$Endpoint/api/v1/agentmemory/indexer-status" -Headers $Headers
Invoke-RestMethod "$Endpoint/api/v1/AgentMemory/files" -Headers $Headers

Remove-Variable Token
```

Record the current state rather than quoting a previous demo's results:

- Agent Memory and each retrieval capability: enabled, disabled, or unavailable.
- Indexer: current state and latest execution result.
- Documents processed, connected repositories, and knowledge-file count.
- Recent workload Application Insights requests and the query window.
- Missing or delayed evidence: `UNKNOWN` until ingestion is demonstrated.

### Say

> A deployed connector is plumbing, not proof of populated evidence. Telemetry answers what the system did. Repositories explain what the code intended. Knowledge files provide operating procedures and organizational context. We report the live inventory and query results, including any gaps, rather than allowing the agent to imply evidence it does not have.

Add:

> Incident routing is a separate readiness check. The enabled response plan accepts every Azure Monitor severity for Grubify, routes to the application handler, and runs in Review mode so diagnosis can begin automatically while write actions remain approval-gated. The one-minute alert evaluation supports a fast lab, but it is not a guaranteed agent-response SLA.

### Customer Value

- Evidence sources remain independently verifiable.
- The agent can use Azure identity instead of connector secrets.
- Mission 01 alerts have a verified route to a specialized handler before fault injection begins.
- Empty or delayed data is reported as `UNKNOWN`, reducing unsupported incident conclusions.
- Later missions can add repositories and knowledge without changing the workload architecture.

## Closing - 1 Minute

Use this summary:

> Deployment stage 00 proves a real customer path on an isolated, observable workload. Deployment stage 01 adds an autonomous SRE capability with a managed identity and a bounded write scope. Deployment stage 02 connects the evidence plane and makes evidence gaps visible. This gives later incident simulations a trustworthy normal-state baseline and a governed path from detection to action.

Ask the customer:

1. Which production resource groups should an agent be allowed to change?
2. Which actions should remain approval-gated even when diagnosis is autonomous?
3. Which repositories and runbooks would materially improve incident decisions?
4. What evidence must the agent cite before an automated remediation is acceptable?

## Expected Behaviors That Are Not Failures

| Observation | Meaning |
|---|---|
| API root `/` returns `404` | Expected. Use `/health` or `/api/restaurants`. |
| SRE Agent endpoint returns `unauthorized` in a browser | Expected. The endpoint requires an Azure SRE access token. |
| Frontend root returns `200` | Proves static delivery only; restaurant cards prove the browser-to-API path. |
| Repository list is empty | Source evidence has not been connected yet. |
| Knowledge file list is empty | Agent Memory is ready but no knowledge has been loaded. |
| Application Insights query has no rows | Evidence is `UNKNOWN`; generate traffic and verify ingestion before claiming telemetry works. |

## Do Not Show or Claim

- Do not display access tokens, connection strings, shared keys, or environment secret values.
- Do not describe `Autonomous` plus `High` as the recommended production default.
- Do not claim the agent is in the customer request path.
- Do not claim an empty telemetry query proves the application is healthy or unhealthy.
- Do not imply carts or orders are durable; the API stores demo state in memory.
- Do not say the azd deployment manages resource groups outside its selected environment.
[< Previous Challenge](./Challenge-01.md) — **[Home](./README.md)** — [Next Mission >](../../Missions/Challenge-01.md)

# Deployment stage 02 — Deploy Evidence and Incident Routing with azd

> **Capabilities added in this challenge**: Telemetry Connectors · Incident Response Subagent · All-Severity Response Plan · Evidence-Plane Validation

## Introduction

Complete the staged azd deployment by adding the two Azure telemetry connectors, the Grubify incident-response subagent, and an enabled response plan. Then validate what the agent can actually prove across telemetry, source, knowledge, and incident routing. Infrastructure health, populated evidence, and live routing are different outcomes.

## Description

Run this mission only after the agent endpoint from Deployment stage 01 is available.

### 1. Select the same environment and enable connectors

```powershell
$ErrorActionPreference = 'Stop'
$EnvironmentName = 'signalops-core'

Push-Location '.\SRE SignalOps'
azd env select $EnvironmentName
azd env set DEPLOY_AGENT true
azd env set DEPLOY_CONNECTORS true
azd provision --preview
```

The infrastructure preview adds two ARM connectors beneath the existing agent: `log-analytics` and `application-insights`. It must not replace the workload or agent. After provisioning, the azd postprovision hook registers and verifies three local Review specialists and the enabled response plan through the data plane; those registrations do not appear in the ARM preview.

### 2. Provision the connector stage

```powershell
azd provision
```

No connector secret is stored in the repository or azd environment. Both connectors use the agent's user-assigned identity and Azure resource IDs.

### 3. Verify connector resources

```powershell
$AgentId = (azd env get-value SRE_AGENT_ID).Trim()
$ApiVersion = '2026-01-01'
$ConnectorUrl = "https://management.azure.com$AgentId/connectors?api-version=$ApiVersion"

az rest --method GET --url $ConnectorUrl `
  --query 'value[].{Name:name,Type:properties.dataConnectorType,Source:properties.dataSource}' -o table
```

Expected connectors:

| Name | Type | Evidence source |
|---|---|---|
| `log-analytics` | `LogAnalytics` | Workload Log Analytics workspace |
| `application-insights` | `AppInsights` | Agent Application Insights component created by this environment |

### 4. Verify the incident subagent and response plan

The postprovision hook calls `Scripts\Register-SignalOpsAgent.ps1` with the local `Config` bundle. It registers `network-traffic-analyst`, `cost-optimization-agent`, `aca-app-incident-handler`, and `sample-food-http-errors`, then reads them back. A registration or verification failure fails the hook. To retry after correcting readiness or access, run `.\Scripts\Register-SignalOpsAgent.ps1 -AgentId $AgentId` from the azd project directory. Request a short-lived data-plane token and keep it only in this PowerShell process:

```powershell
$Agent = az rest --method GET `
  --url "https://management.azure.com$AgentId`?api-version=$ApiVersion" |
  ConvertFrom-Json
$Endpoint = $Agent.properties.agentEndpoint.TrimEnd('/')
$Token = (az account get-access-token --resource https://azuresre.dev --query accessToken -o tsv).Trim()
$Headers = @{ Authorization = "Bearer $Token" }

$SubagentResponse = Invoke-RestMethod `
  -Uri "$Endpoint/api/v2/extendedAgent/agents" -Headers $Headers -Method Get
$FilterResponse = Invoke-RestMethod `
  -Uri "$Endpoint/api/v2/extendedAgent/incidentFilters" -Headers $Headers -Method Get

$Subagents = if ($SubagentResponse.PSObject.Properties.Name -contains 'value') {
  @($SubagentResponse.value)
} else {
  @($SubagentResponse)
}
$Filters = if ($FilterResponse.PSObject.Properties.Name -contains 'value') {
  @($FilterResponse.value)
} elseif ($FilterResponse.PSObject.Properties.Name -contains 'incidentFilters') {
  @($FilterResponse.incidentFilters)
} else {
  @($FilterResponse)
}

$Handler = $Subagents | Where-Object { $_.name -eq 'aca-app-incident-handler' } | Select-Object -First 1
$Plan = $Filters | Where-Object { $_.name -eq 'sample-food-http-errors' } | Select-Object -First 1
$PlanProperties = if ($Plan.PSObject.Properties.Name -contains 'properties') { $Plan.properties } else { $Plan }

[pscustomobject]@{
  HandlerRegistered = $null -ne $Handler
  PlanRegistered    = $null -ne $Plan
  PlanEnabled       = $PlanProperties.isEnabled
  Severities        = @($PlanProperties.priorities) -join ','
  TitleContains     = $PlanProperties.titleContains
  HandlingAgent     = $PlanProperties.handlingAgent
  Mode              = $PlanProperties.agentMode
  Attempts          = $PlanProperties.maxAutomatedInvestigationAttempts
} | Format-List
```

Expected response-plan state:

| Property | Expected value |
|---|---|
| Registered / enabled | `True` / `True` |
| Severities | `Sev0,Sev1,Sev2,Sev3,Sev4` |
| Title contains | `grubify` |
| Handler | `aca-app-incident-handler` |
| Mode | `Review` |
| Automated attempts | `1` |

Stop before Mission 01 if the handler or plan is absent, disabled, or mismatched. The plan takes effect immediately after registration, but Azure Monitor and SRE Agent ingestion remain asynchronous. Mission 01 uses a one-minute alert evaluation frequency. Reinvestigation cooldown controls duplicate processing; it does not make the first response faster.

### 5. Validate data-plane ground truth

```powershell
Invoke-RestMethod -Uri "$Endpoint/api/v2/repos" -Headers $Headers |
  ConvertTo-Json -Depth 8
Invoke-RestMethod -Uri "$Endpoint/api/v1/agentmemory/status" -Headers $Headers |
  ConvertTo-Json -Depth 8
Invoke-RestMethod -Uri "$Endpoint/api/v1/agentmemory/indexer-status" -Headers $Headers |
  ConvertTo-Json -Depth 8
Invoke-RestMethod -Uri "$Endpoint/api/v1/AgentMemory/files" -Headers $Headers |
  ConvertTo-Json -Depth 8

$WorkloadResourceGroup = (azd env get-value AZURE_RESOURCE_GROUP).Trim()
az containerapp list --resource-group $WorkloadResourceGroup `
  --query '[].{Name:name,State:properties.runningStatus,FQDN:properties.configuration.ingress.fqdn}' -o table
Pop-Location
```

An empty repository list or zero knowledge files is an evidence gap, not a failed connector deployment. Record the state accurately before adding source or documents in later missions.

## Success Criteria

- [ ] The ARM preview adds two connectors without replacement; the postprovision hook verifies three Review specialists and one response plan
- [ ] `log-analytics` and `application-insights` exist beneath the azd-deployed agent
- [ ] Connector data sources resolve to resources created by the same azd environment
- [ ] `aca-app-incident-handler` is registered before any fault injection
- [ ] `sample-food-http-errors` is enabled for `Sev0` through `Sev4`, matches `grubify`, routes to the handler in `Review` mode, and allows one automated investigation attempt
- [ ] Agent Memory and indexer status are reported separately from file count
- [ ] Repository and knowledge gaps are disclosed without storing credentials or tokens
- [ ] **Explain to your coach** — why does the one-minute alert evaluation affect detection latency while reinvestigation cooldown affects duplicate handling rather than first response?

## Learning Resources

- [Connect Azure data to Azure SRE Agent](https://learn.microsoft.com/en-us/azure/sre-agent/connect-data)
- [Connect knowledge to Azure SRE Agent](https://learn.microsoft.com/en-us/azure/sre-agent/connect-knowledge)
- [Automate incidents with Azure SRE Agent](https://learn.microsoft.com/en-us/azure/sre-agent/automate-incidents)
- [Azure SRE Agent API reference](https://learn.microsoft.com/en-us/azure/sre-agent/api-reference)

## Tips

- Re-run `azd provision --preview` whenever Bicep or deployment flags change.
- Use `Review` mode until the handler's investigation and proposed actions have been validated.
- A healthy memory service with zero files is ready infrastructure, not populated knowledge.
- Never persist the `azuresre.dev` access token in a file or azd environment value.

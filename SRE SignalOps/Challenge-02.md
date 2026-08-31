[< Previous Challenge](./Challenge-01.md) — **[Home](./README.md)** — [Next Challenge >](./Challenge-03.md)

# Challenge 02 — Deploy Evidence Connectors with azd

> **Capabilities added in this challenge**: Log Analytics Connector · Application Insights Connector · Evidence-Plane Validation

## Introduction

Complete the staged azd deployment by adding the two Azure telemetry connectors from the Terraform reference. Then validate what the agent can actually prove across telemetry, source, and knowledge. Infrastructure health and populated evidence are different outcomes.

## Description

Run this mission only after the agent endpoint from Mission 01 is available.

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

The preview should add exactly two child resources beneath the existing agent: `log-analytics` and `application-insights`. It must not replace the workload or agent.

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
| `application-insights` | `AppInsights` | Agent Application Insights component, matching the Terraform reference |

### 4. Validate data-plane ground truth

```powershell
$Agent = az rest --method GET `
  --url "https://management.azure.com$AgentId`?api-version=$ApiVersion" |
  ConvertFrom-Json
$Endpoint = $Agent.properties.agentEndpoint.TrimEnd('/')
$Token = (az account get-access-token --resource https://azuresre.dev --query accessToken -o tsv).Trim()
$Headers = @{ Authorization = "Bearer $Token" }

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

- [ ] The connector-stage preview is reviewed before provisioning
- [ ] `log-analytics` and `application-insights` exist beneath the azd-deployed agent
- [ ] Connector data sources resolve to resources created by the same azd environment
- [ ] Agent Memory and indexer status are reported separately from file count
- [ ] Repository and knowledge gaps are disclosed without storing credentials or tokens
- [ ] **Explain to your coach** — how do telemetry, source, and knowledge answer different questions, and which of those evidence planes were deployed by azd?

## Learning Resources

- [Connect Azure data to Azure SRE Agent](https://learn.microsoft.com/en-us/azure/sre-agent/connect-data)
- [Connect knowledge to Azure SRE Agent](https://learn.microsoft.com/en-us/azure/sre-agent/connect-knowledge)
- [Azure SRE Agent API reference](https://learn.microsoft.com/en-us/azure/sre-agent/api-reference)

## Tips

- Re-run `azd provision --preview` whenever Bicep or deployment flags change.
- A healthy memory service with zero files is ready infrastructure, not populated knowledge.
- Never persist the `azuresre.dev` access token in a file or azd environment value.

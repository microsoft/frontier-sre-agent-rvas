[< Previous Challenge](./Challenge-04.md) — **[Home](./README.md)** — [Next Challenge >](./Challenge-06.md)

# Challenge 05 — Investigate an Evidence Blind Spot

> **Incident capability exercised in this challenge**: Evidence Availability · Source Validation · Fallback Reasoning

## Introduction

Mission 03 produced a real Grubify incident and Mission 04 added approved operational knowledge. Neither result proves that every configured evidence source is reachable, authorized, or fresh. In this mission you will validate each Azure telemetry connector with visible commands, identify one real or coach-provided evidence blind spot, and bound what the SRE Agent can conclude safely.

Run every command separately from the repository root and inspect its output before continuing. This mission intentionally does not use a PowerShell script.

## Description

### Part 1 — Reuse the Isolated SignalOps Environment

Select the environment used in Missions 00–04 and retrieve its deployed resource IDs:

```powershell
$ErrorActionPreference = 'Stop'

Push-Location '.\SRE SignalOps'
azd env select signalops-core
$AGENT_ID = (azd env get-value SRE_AGENT_ID).Trim()
$WORKLOAD_RG = (azd env get-value AZURE_RESOURCE_GROUP).Trim()
$LOG_ANALYTICS_ID = (azd env get-value LOG_ANALYTICS_WORKSPACE_ID).Trim()
$WORKLOAD_APP_INSIGHTS_NAME = (azd env get-value APPLICATIONINSIGHTS_NAME).Trim()
Pop-Location
```

Confirm the active subscription and all four resolved values before making data-plane calls:

```powershell
az account show --query '{Subscription:name,SubscriptionId:id,Tenant:tenantId}' -o table

[pscustomobject]@{
	AgentId             = $AGENT_ID
	WorkloadGroup       = $WORKLOAD_RG
	LogAnalyticsId      = $LOG_ANALYTICS_ID
	WorkloadAppInsights = $WORKLOAD_APP_INSIGHTS_NAME
} | Format-List
```

Stop if any value is empty or does not belong to the isolated `signalops-core` environment.

### Part 2 — Inventory Configured Connectors Through ARM

Use the same current ARM API version as Missions 02 and 04:

```powershell
$API_VERSION = '2026-01-01'
$CONNECTOR_URL = "https://management.azure.com$AGENT_ID/connectors?api-version=$API_VERSION"

az rest --method GET --url $CONNECTOR_URL `
	--query 'value[].{Name:name,Type:properties.dataConnectorType,State:properties.provisioningState}' -o table
```

The expected configured connectors are `log-analytics` and `application-insights`. A `Succeeded` provisioning state proves only that the connector resource exists; it does not prove a current evidence read. The ARM schema marks `dataSource` as sensitive, so normal `GET` responses redact it to `null`.

Capture the connector records for their names, types, and provisioning states:

```powershell
$CONNECTORS = az rest --method GET --url $CONNECTOR_URL | ConvertFrom-Json
$CONNECTORS.value | Select-Object name,
	@{Name='Type';Expression={$_.properties.dataConnectorType}},
	@{Name='State';Expression={$_.properties.provisioningState}} |
	Format-Table -AutoSize
```

Use each connector's `listSecrets` action to retrieve its configured source. Keep these results only in the current PowerShell process:

```powershell
$LOG_CONNECTOR_RECORD = $CONNECTORS.value |
	Where-Object { $_.properties.dataConnectorType -eq 'LogAnalytics' } |
	Select-Object -First 1
$APP_CONNECTOR_RECORD = $CONNECTORS.value |
	Where-Object { $_.properties.dataConnectorType -eq 'AppInsights' } |
	Select-Object -First 1

$LOG_CONNECTOR = az rest --method POST --url `
	"https://management.azure.com$AGENT_ID/connectors/$($LOG_CONNECTOR_RECORD.name)/listSecrets?api-version=$API_VERSION" |
	ConvertFrom-Json
$APP_CONNECTOR = az rest --method POST --url `
	"https://management.azure.com$AGENT_ID/connectors/$($APP_CONNECTOR_RECORD.name)/listSecrets?api-version=$API_VERSION" |
	ConvertFrom-Json
```

Check that the Log Analytics connector targets the expected workspace:

```powershell

[pscustomobject]@{
	ConfiguredSource = $LOG_CONNECTOR.properties.dataSource
	ExpectedSource   = $LOG_ANALYTICS_ID
	SourceMatches    = $LOG_CONNECTOR.properties.dataSource -eq $LOG_ANALYTICS_ID
} | Format-List
```

Inspect the Application Insights connector source independently:

```powershell
[pscustomobject]@{
	Name   = $APP_CONNECTOR.name
	State  = $APP_CONNECTOR.properties.provisioningState
	Source = $APP_CONNECTOR.properties.dataSource
} | Format-List
```

Stop if either connector record is absent, either `listSecrets` call fails, or the Log Analytics source does not match `$LOG_ANALYTICS_ID`. Although these source values are Azure resource IDs rather than credentials in this lab, do not persist the `listSecrets` responses.

### Part 3 — Compare the Live Data-Plane Inventory

Discover the deployed endpoint rather than copying it from a previous mission:

```powershell
$AGENT = az rest --method GET --url "https://management.azure.com$AGENT_ID`?api-version=$API_VERSION" | ConvertFrom-Json
$AGENT_ENDPOINT = $AGENT.properties.agentEndpoint.TrimEnd('/')
$AGENT_ENDPOINT
```

Request a short-lived SRE Agent token and keep it only in the current process:

```powershell
$TOKEN = (az account get-access-token --resource https://azuresre.dev --query accessToken -o tsv).Trim()
$HEADERS = @{ Authorization = "Bearer $TOKEN" }
```

Do not display `$TOKEN`, write it to disk, or save it in the azd environment.

List connectors exposed by the live data plane:

```powershell
Invoke-RestMethod -Uri "$AGENT_ENDPOINT/api/v2/extendedAgent/connectors" -Headers $HEADERS -Method Get |
	ConvertTo-Json -Depth 10
```

Record any connector that exists in ARM but is absent from the data-plane response as a configuration or synchronization blind spot. Do not report repository examples as live connectors.

### Part 4 — Prove Log Analytics Reachability and Freshness

Resolve the workspace customer ID from the expected resource:

```powershell
$LOG_WORKSPACE = az monitor log-analytics workspace show --ids $LOG_ANALYTICS_ID | ConvertFrom-Json
$LOG_WORKSPACE_CUSTOMER_ID = $LOG_WORKSPACE.customerId

$LOG_WORKSPACE | Select-Object name, resourceGroup, location, provisioningState, customerId |
	Format-List
```

Run a harmless query over the last 24 hours. A successful query with zero rows proves authorization and query execution, but it does not prove fresh application telemetry:

```powershell
$LOG_QUERY = @'
ContainerAppConsoleLogs_CL
| where TimeGenerated > ago(24h)
| summarize Rows=count(), Latest=max(TimeGenerated)
'@

az monitor log-analytics query --workspace $LOG_WORKSPACE_CUSTOMER_ID `
	--analytics-query $LOG_QUERY -o table
```

Record the query time so freshness can be assessed rather than assumed:

```powershell
$LOG_CHECKED_AT = (Get-Date).ToUniversalTime()
$LOG_CHECKED_AT.ToString('yyyy-MM-ddTHH:mm:ssZ')
```

### Part 5 — Prove Application Insights Reachability and Freshness

Resolve the connector's actual `dataSource` resource. Do not assume it is the workload component:

```powershell
$APP_SOURCE_ID = $APP_CONNECTOR.properties.dataSource
$APP_SOURCE = az resource show --ids $APP_SOURCE_ID | ConvertFrom-Json

$APP_SOURCE | Select-Object name, resourceGroup, location, provisioningState, id |
	Format-List
```

Compare the connector source with the workload Application Insights component. They can be different resources with different telemetry purposes:

```powershell
[pscustomobject]@{
	ConnectorSource       = $APP_SOURCE_ID
	WorkloadComponentName = $WORKLOAD_APP_INSIGHTS_NAME
	WorkloadResourceGroup = $WORKLOAD_RG
} | Format-List
```

Run a harmless request query against the connector's configured source over the last 24 hours:

```powershell
$APP_QUERY = @'
requests
| where timestamp > ago(24h)
| summarize Rows=count(), Latest=max(timestamp), Failures=countif(success == false)
'@

az monitor app-insights query --resource-group $APP_SOURCE.resourceGroup --app $APP_SOURCE.name `
	--analytics-query $APP_QUERY -o table
```

Record the second check time separately:

```powershell
$APP_CHECKED_AT = (Get-Date).ToUniversalTime()
$APP_CHECKED_AT.ToString('yyyy-MM-ddTHH:mm:ssZ')
```

If the query succeeds but `Latest` is empty or older than the investigation window, classify the issue as a source-data or freshness blind spot. A healthy resource and successful authentication do not make stale evidence current.

### Part 6 — Classify the Blind Spot

Use one observed failure from the preceding commands. If every live check succeeds with fresh data, ask your coach for a labeled failed-read result; do not disable or misconfigure a connector to manufacture an incident.

Record the evidence matrix in your notes:

| Source | Configured | Authenticated | Authorized read | Reachable | Latest evidence (UTC) | Allowed action | Result |
|---|---|---|---|---|---|---|---|
| Log Analytics |  |  |  |  |  | Read-only query |  |
| Application Insights |  |  |  |  |  | Read-only query |  |
| Agent Memory | Verified in Mission 04 |  |  |  | Indexing time | Read-only retrieval |  |

Classify the selected blind spot as one of these types:

- `configuration` — expected connector or source ID is missing or incorrect
- `authentication` — no valid identity or token can be established
- `authorization` — identity is valid but the harmless read is denied
- `network` — the endpoint cannot be reached
- `schema` — the source is reachable but the expected table or fields cannot be queried
- `source-data` — the query works but the required evidence is absent
- `freshness` — evidence exists but is too old for the incident decision

### Part 7 — Ask the SRE Agent to Bound Its Conclusion

Open the deployed SRE Agent:

```powershell
Start-Process $AGENT_ENDPOINT
```

Submit this prompt with your observed timestamps and failed-read details filled in:

> Continue the Grubify investigation from the memory incident. Build an evidence matrix for Log Analytics, Application Insights, and Agent Memory. For each source, state configuration, authentication, authorization, reachability, latest evidence time, and allowed actions. Classify this failed or stale read: `<paste the sanitized result>`. Explain what cannot be concluded, which alternate evidence can discriminate next, who owns restoration, and what proof would restore confidence. Do not invent evidence or perform a write.

Compare the response with the command output. The agent must lower confidence or stop when the missing evidence is required for a safe diagnosis.

Remove the short-lived token when the exercise is complete:

```powershell
Remove-Variable TOKEN
$HEADERS = $null
```

## Success Criteria

- [ ] ARM inventory and data-plane inventory are checked separately with the current `2026-01-01` API version
- [ ] Log Analytics and Application Insights each have an individual harmless read and UTC freshness timestamp
- [ ] The incident identifies the required evidence source and the failed or stale read that created the blind spot
- [ ] Each relevant source has an observed reachability result, freshness assessment, and authorization scope
- [ ] The failure is classified without exposing credentials or inventing evidence
- [ ] The SRE Agent states the diagnostic limitation, alternate evidence path, owner, and recovery proof
- [ ] **Explain to your coach** — when should an SRE continue with partial evidence, and when should the investigation stop or escalate?

## Learning Resources

- [Azure SRE Agent connectors](https://learn.microsoft.com/en-us/azure/sre-agent/connectors)
- [Model Context Protocol overview](https://learn.microsoft.com/en-us/azure/sre-agent/mcp)
- [Azure SRE Agent API connectors](https://learn.microsoft.com/en-us/azure/sre-agent/api-reference#connector-types)

## Tips

- Use read-only calls for evidence validation.
- Never print connector secrets or bearer tokens.
- A successful stale read is still an incident evidence risk.
- An ARM `Succeeded` state proves deployment, not data-plane access or evidence freshness.

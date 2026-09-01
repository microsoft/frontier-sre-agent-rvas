[< Previous Challenge](./Challenge-06.md) — **[Home](./README.md)** — [Next Challenge >](./Challenge-08.md)

# Challenge 07 — Exercise a Guarded HTTP-Error Response

> **Incident capability exercised in this challenge**: Alert Routing · Guarded Response · Recovery Validation

## Introduction

Missions 03–06 established the Grubify incident, approved knowledge, evidence boundaries, and specialist registration state. In this mission you will determine whether the existing HTTP-error signal can actually reach the intended response filter, gather current evidence, and run a proposal-only response exercise with explicit stop and recovery criteria.

Run every command separately from the repository root and inspect its output before continuing. This mission intentionally does not use a PowerShell script.

## Description

### Part 1 — Reuse the SignalOps Environment

Select the isolated environment and retrieve its deployed values:

```powershell
$ErrorActionPreference = 'Stop'

Push-Location '.\SRE SignalOps'
azd env select signalops-core
$AGENT_ID = (azd env get-value SRE_AGENT_ID).Trim()
$WORKLOAD_RG = (azd env get-value AZURE_RESOURCE_GROUP).Trim()
Pop-Location

$API_VERSION = '2026-01-01'
```

Confirm the active subscription and resolved resources:

```powershell
$SUBSCRIPTION_ID = (az account show --query id -o tsv).Trim()

az account show --query '{Subscription:name,SubscriptionId:id,Tenant:tenantId}' -o table

[pscustomobject]@{
	AgentId       = $AGENT_ID
	WorkloadGroup = $WORKLOAD_RG
} | Format-List
```

Stop if either resource does not belong to `signalops-core`.

### Part 2 — Inspect ARM Incident Wiring and Action Mode

Read the deployed agent configuration through the current ARM API:

```powershell
$AGENT = az rest --method GET --url "https://management.azure.com$AGENT_ID`?api-version=$API_VERSION" | ConvertFrom-Json
$AGENT_ENDPOINT = $AGENT.properties.agentEndpoint.TrimEnd('/')

[pscustomobject]@{
	Endpoint           = $AGENT_ENDPOINT
	IncidentType       = $AGENT.properties.incidentManagementConfiguration.type
	Connection         = $AGENT.properties.incidentManagementConfiguration.connectionName
	ActionMode         = $AGENT.properties.actionConfiguration.mode
	ActionAccess       = $AGENT.properties.actionConfiguration.accessLevel
	ProvisioningState  = $AGENT.properties.provisioningState
} | Format-List
```

Expected wiring is `AzMonitor` through `azmonitor`. This lab agent is configured `Autonomous/High`; there is no reliable human approval wait to demonstrate. Keep the mission proposal-only and do not ask the agent to execute a write.

### Part 3 — Inspect the Desired HTTP-Error Filter

Read the desired-state filter directly from the repository:

```powershell
$FILTER_MANIFEST = '.\Student\Resources\azure-sre-agent-config\automations\incident-filters\sample-food-http-errors.yaml'

Get-Content $FILTER_MANIFEST |
	Select-String -Pattern '^  name:','^  incidentPlatform:','^  isEnabled:','^  priorities:','^    - Sev','^  titleContains:','^  handlingAgent:','^  agentMode:','^  maxAutomatedInvestigationAttempts:'
```

The desired filter requires all of these routing conditions:

- platform `AzMonitor`;
- enabled state `true`;
- priority `Sev1`;
- incident title containing `food`;
- handling agent `aca-app-incident-handler`;
- at most three automated investigation attempts.

### Part 4 — Inventory Live Incident Filters

Request a short-lived data-plane token and keep it only in this PowerShell process:

```powershell
$TOKEN = (az account get-access-token --resource https://azuresre.dev --query accessToken -o tsv).Trim()
$HEADERS = @{ Authorization = "Bearer $TOKEN" }
```

Do not display `$TOKEN`, write it to disk, or save it in the azd environment.

Read the live incident-filter collection:

```powershell
$FILTER_RESPONSE = Invoke-RestMethod `
	-Uri "$AGENT_ENDPOINT/api/v2/extendedAgent/incidentFilters" `
	-Headers $HEADERS `
	-Method Get

$LIVE_FILTERS = if ($FILTER_RESPONSE.PSObject.Properties.Name -contains 'value') {
	$FILTER_RESPONSE.value
} elseif ($FILTER_RESPONSE.PSObject.Properties.Name -contains 'incidentFilters') {
	$FILTER_RESPONSE.incidentFilters
} else {
	@($FILTER_RESPONSE)
}

$LIVE_FILTERS = @($LIVE_FILTERS)
```

Display the routing fields and count separately:

```powershell
"Live filter count: $($LIVE_FILTERS.Count)"

$LIVE_FILTERS |
	Select-Object name, isEnabled, priorities, titleContains, handlingAgent, agentMode, maxAutomatedInvestigationAttempts |
	Format-Table -Wrap -AutoSize
```

Check the expected filter by name:

```powershell
$LIVE_HTTP_FILTER = $LIVE_FILTERS |
	Where-Object { $_.name -eq 'sample-food-http-errors' } |
	Select-Object -First 1

[pscustomobject]@{
	ExpectedFilter = 'sample-food-http-errors'
	Registered     = $null -ne $LIVE_HTTP_FILTER
} | Format-List
```

An empty `value` collection or missing expected filter is a registration gap. Continue with a labeled desired-state exercise; do not claim that Azure Monitor routed a live incident through this filter.

### Part 5 — Compare the Mission 03 Alert with Filter Conditions

List current Grubify or Food metric alert rules in the workload resource group:

```powershell
$ALERT_RULES = az monitor metrics alert list --resource-group $WORKLOAD_RG | ConvertFrom-Json

$ALERT_RULES |
	Where-Object { $_.name -match 'grubify|food' } |
	Select-Object name, severity, enabled, scopes |
	Format-Table -Wrap -AutoSize
```

Inspect the retained Mission 03 rule when it exists:

```powershell
$MISSION03_ALERT = $ALERT_RULES |
	Where-Object { $_.name -eq 'alert-signalopscore-grubify-http-5xx' } |
	Select-Object -First 1

[pscustomobject]@{
	AlertExists          = $null -ne $MISSION03_ALERT
	AlertName            = $MISSION03_ALERT.name
	AlertPriority        = if ($MISSION03_ALERT) { "Sev$($MISSION03_ALERT.severity)" } else { 'unavailable' }
	RequiredPriority     = 'Sev1'
	TitleContainsFood    = [bool]($MISSION03_ALERT.name -match 'food')
	RequiredTitleText    = 'food'
	MatchesDesiredFilter = [bool](
		$MISSION03_ALERT -and
		$MISSION03_ALERT.severity -eq 1 -and
		$MISSION03_ALERT.name -match 'food'
	)
} | Format-List
```

Mission 03 creates a severity `2` rule whose name does not contain `food`, so it does not match the desired `Sev1` plus `titleContains: food` filter. Do not alter the rule or create a failure just to force a match.

### Part 6 — Gather Current Grubify Evidence

Discover the API Container App instead of copying a resource name:

```powershell
$APP = az containerapp list --resource-group $WORKLOAD_RG | ConvertFrom-Json |
	Where-Object { $_.name -match 'food-api$' } |
	Select-Object -First 1

$APP_NAME = $APP.name
$APP_ID = $APP.id
$APP_BASE = "https://$($APP.properties.configuration.ingress.fqdn)"

[pscustomobject]@{
	Name       = $APP_NAME
	ResourceId = $APP_ID
	ApiUrl     = $APP_BASE
	State      = $APP.properties.runningStatus
} | Format-List
```

Stop if the application cannot be resolved. Check health and a normal read separately:

```powershell
curl.exe -s -o NUL -w "Health HTTP Status: %{http_code}`n" "$APP_BASE/health"
```

```powershell
curl.exe -s -o NUL -w "Restaurants HTTP Status: %{http_code}`n" "$APP_BASE/api/restaurants"
```

Read HTTP 5xx, memory, and restart metrics over the last 30 minutes:

```powershell
$EVIDENCE_START = (Get-Date).ToUniversalTime().AddMinutes(-30).ToString('yyyy-MM-ddTHH:mm:ssZ')

az monitor metrics list --resource $APP_ID --metric Requests --filter "statusCodeCategory eq '5xx'" --interval PT1M --aggregation Total --start-time $EVIDENCE_START --query "value[0].timeseries[].data[].{time:timeStamp,total:total}" -o table

az monitor metrics list --resource $APP_ID --metric WorkingSetBytes --interval PT1M --aggregation Maximum --start-time $EVIDENCE_START --query "value[0].timeseries[].data[].{time:timeStamp,maxBytes:maximum}" -o table

az monitor metrics list --resource $APP_ID --metric RestartCount --interval PT1M --aggregation Maximum --start-time $EVIDENCE_START --query "value[0].timeseries[].data[].{time:timeStamp,restarts:maximum}" -o table
```

Record the evidence check time:

```powershell
$EVIDENCE_CHECKED_AT = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
$EVIDENCE_CHECKED_AT
```

Current healthy reads do not prove that a previous incident never occurred. They establish only the present recovery state and must remain separate from historical alert evidence.

### Part 7 — Run a Labeled Proposal-Only Exercise

Open the deployed SRE Agent:

```powershell
Start-Process $AGENT_ENDPOINT
```

Submit this prompt with the observed filter, alert, and telemetry results:

> **EXERCISE — NO WRITE AUTHORIZED:** Evaluate the Grubify HTTP-error response using the live ARM wiring, live incident-filter inventory, desired `sample-food-http-errors` manifest, Mission 03 alert rule, and current health and metric evidence I provide. First state whether live routing is proven. If the filter is absent or the alert does not match `Sev1` and title text `food`, label the routing stage unavailable and continue only as a tabletop. Produce one UTC timeline covering intake, filter decision, evidence, classification, proposed action, action risk, rollback, validation, retry limit, timeout, escalation, and closure criteria. Do not restart, roll back, change configuration, create an alert, or create an issue.

Do not approve or request a write. Because the deployed agent is `Autonomous/High`, proposal-only wording is the operational guardrail for this exercise.

### Part 8 — Test Stop and Escalation Branches

Submit each branch separately in the same conversation.

Missing evidence:

> **BRANCH — MISSING EVIDENCE:** Assume the current 5xx and restart metrics cannot be read. Update the same timeline. State what cannot be concluded, which alternate read could discriminate next, and the escalation owner. Do not propose execution.

Failed action simulation:

> **BRANCH — FAILED ACTION:** Simulate that a proposed revision restart failed. Do not run it. State the retry limit, rollback or alternate recovery path, owner, and evidence required before another attempt.

Failed validation simulation:

> **BRANCH — FAILED VALIDATION:** Simulate that the action completed but `/health` is not `200` or new 5xx buckets continue. Keep the incident open, escalate, and state the next evidence required. Workflow completion is not recovery.

### Part 9 — Compare the Observed Response Path

Complete this matrix from command output and agent responses:

| Stage | Expected evidence or decision | Observed result | Proven, unavailable, or simulated | UTC time |
|---|---|---|---|---|
| ARM incident wiring | `AzMonitor` and `azmonitor` |  |  |  |
| Filter registration | Live `sample-food-http-errors` |  |  |  |
| Alert match | `Sev1` and title contains `food` |  |  |  |
| Evidence collection | Health, Requests, memory, restarts |  |  |  |
| Classification | Evidence-backed severity and confidence |  |  |  |
| Proposed action | Scope, risk, rollback; no execution |  |  |  |
| Failed-action branch | Retry limit and escalation |  |  |  |
| Recovery validation | HTTP `200`, no new 5xx, stable restarts |  |  |  |
| Closure | Service evidence, not workflow completion |  |  |  |

Mark every skipped, unavailable, or simulated stage explicitly. Live routing is proven only when the filter is registered, the alert satisfies its conditions, and an incident is observed.

Remove the short-lived token when the exercise is complete:

```powershell
Remove-Variable TOKEN
$HEADERS = $null
```

## Success Criteria

- [ ] ARM incident wiring, action mode, desired filter, and live filter registration are checked separately
- [ ] The Mission 03 alert is compared with both filter priority and title conditions without altering either resource
- [ ] A genuine incident is claimed only when live registration, alert matching, and observed intake are all proven; otherwise the exercise is labeled
- [ ] Current Grubify evidence and classification precede action selection
- [ ] The proposed response states scope, risk, rollback, no-write boundary, and recovery checks
- [ ] Timeout, failed-action, failed-validation, and escalation paths are visible
- [ ] The observed incident timeline is compared with the intended response path
- [ ] **Explain to your coach** — why must incident closure depend on service recovery evidence rather than workflow completion?

## Learning Resources

- [Automate incidents with Azure SRE Agent](https://learn.microsoft.com/en-us/azure/sre-agent/automate-incidents)
- [Azure SRE Agent API sub-resources](https://learn.microsoft.com/en-us/azure/sre-agent/api-reference#sub-resources)
- [Azure Monitor alert processing rules](https://learn.microsoft.com/en-us/azure/azure-monitor/alerts/alerts-processing-rules)

## Tips

- The incident outcome matters more than the response-plan terminology.
- Closure must depend on recovery evidence.
- Keep the exercise labeled and non-destructive.
- `Autonomous/High` is not an approval gate; never ask the agent to execute during this mission.

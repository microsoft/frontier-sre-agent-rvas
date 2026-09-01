[< Previous Challenge](./Challenge-08.md) — **[Home](./README.md)** — [Next Challenge >](./Challenge-10.md)

# Challenge 09 — Resolve a Backup Assurance Incident

> **Incident capability exercised in this challenge**: Backup-Failure Triage · Stakeholder Communication · Recovery Validation

## Introduction

A backup alert means application recoverability may be at risk even while the service is still running. Simulate that assurance incident, determine whether protection actually failed, communicate customer and RPO impact, follow an approved recovery path, and define the evidence required to close the issue.

Run every command separately from the repository root and inspect its output before continuing. This mission intentionally does not use a PowerShell script.

## Description

### Part 1 — Reuse the SignalOps Environment

Select the isolated environment and retrieve the deployed values:

```powershell
$ErrorActionPreference = 'Stop'

Push-Location '.\SRE SignalOps'
azd env select signalops-core
$AGENT_ID = (azd env get-value SRE_AGENT_ID).Trim()
$WORKLOAD_RG = (azd env get-value AZURE_RESOURCE_GROUP).Trim()
$API_BASE_URL = (azd env get-value API_BASE_URL).TrimEnd('/')
Pop-Location

$API_VERSION = '2026-01-01'
$SUBSCRIPTION_ID = (az account show --query id -o tsv).Trim()
```

Confirm the active subscription and resolved resources:

```powershell
az account show --query '{Subscription:name,SubscriptionId:id,Tenant:tenantId}' -o table

[pscustomobject]@{
	AgentId          = $AGENT_ID
	WorkloadGroup    = $WORKLOAD_RG
	ApplicationApi   = $API_BASE_URL
} | Format-List
```

### Part 2 — Choose Live or Evidence-Pack Mode

The Grubify deployment does not create a Backup vault, protected workload, or Teams connector. Complete this mission in one of two supported modes:

- **Live mode:** use an existing Recovery Services vault or Backup vault with a protected lab workload, plus an authorized Teams connector whose post-message tool is granted to the response agent.
- **Evidence-pack mode:** use coach-provided vault, protected-item, job, recovery-point, and application-health evidence. Build and exercise the response plan, and produce a review-ready Teams message without posting it.

Inventory Recovery Services vaults without changing them:

```powershell
$RECOVERY_VAULTS = az backup vault list --subscription $SUBSCRIPTION_ID | ConvertFrom-Json

$RECOVERY_VAULTS |
	Select-Object name, resourceGroup, location, id |
	Format-Table -Wrap -AutoSize
```

Inventory Data Protection Backup vaults separately:

```powershell
$BACKUP_VAULTS = az dataprotection backup-vault list --subscription $SUBSCRIPTION_ID 2>$null | ConvertFrom-Json

$BACKUP_VAULTS |
	Select-Object name, resourceGroup, location, id |
	Format-Table -Wrap -AutoSize
```

Record the mode from observed inventory and coach-provided access:

```powershell
$HAS_LIVE_VAULT = @($RECOVERY_VAULTS).Count -gt 0 -or @($BACKUP_VAULTS).Count -gt 0

[pscustomobject]@{
	RecoveryServicesVaults = @($RECOVERY_VAULTS).Count
	BackupVaults           = @($BACKUP_VAULTS).Count
	CandidateLiveMode      = $HAS_LIVE_VAULT
} | Format-List
```

A listed vault is only a candidate. Live mode also requires authorized access to a protected lab workload and its evidence. Otherwise use the evidence pack and do not claim a failed backup.

### Part 3 — Inspect Recovery Services Evidence

For a coach-approved Recovery Services vault, set its exact name and resource group:

```powershell
$VAULT_NAME = '<coach-provided-recovery-services-vault>'
$VAULT_RESOURCE_GROUP = '<coach-provided-vault-resource-group>'
$RECOVERY_SERVICES_MODE = $VAULT_NAME -notlike '<*' -and $VAULT_RESOURCE_GROUP -notlike '<*'
```

List protected Azure VM items:

```powershell
if ($RECOVERY_SERVICES_MODE) {
	az backup item list `
		--vault-name $VAULT_NAME `
		--resource-group $VAULT_RESOURCE_GROUP `
		--backup-management-type AzureIaasVM `
		--query '[].{Name:name,ProtectionState:properties.protectionState,Health:properties.healthStatus,LatestRecoveryPoint:properties.latestRecoveryPoint}' `
		-o table
}
```

List recent jobs independently:

```powershell
if ($RECOVERY_SERVICES_MODE) {
	az backup job list `
		--vault-name $VAULT_NAME `
		--resource-group $VAULT_RESOURCE_GROUP `
		--query '[].{Operation:properties.operation,Status:properties.status,Entity:properties.entityFriendlyName,Start:properties.startTime,End:properties.endTime}' `
		-o table
}
```

For a selected protected item, set the container and item names returned by Azure:

```powershell
$BACKUP_CONTAINER_NAME = '<container-name-from-live-inventory>'
$BACKUP_ITEM_NAME = '<item-name-from-live-inventory>'
```

List recovery points only when both names are resolved:

```powershell
if ($RECOVERY_SERVICES_MODE -and $BACKUP_CONTAINER_NAME -notlike '<*' -and $BACKUP_ITEM_NAME -notlike '<*') {
	az backup recoverypoint list `
		--vault-name $VAULT_NAME `
		--resource-group $VAULT_RESOURCE_GROUP `
		--container-name $BACKUP_CONTAINER_NAME `
		--item-name $BACKUP_ITEM_NAME `
		--backup-management-type AzureIaasVM `
		--query '[].{RecoveryPoint:properties.recoveryPointTime,Type:properties.recoveryPointType,Consistency:properties.recoveryPointTierDetails}' `
		-o jsonc
}
```

For Data Protection Backup vaults or unsupported workload types, use the corresponding coach-provided CLI evidence or evidence pack. Do not translate an unavailable read into healthy protection.

### Part 4 — Check Current Application Health

Query Grubify independently from backup state:

```powershell
curl.exe -s -o NUL -w "Health HTTP Status: %{http_code}`n" "$API_BASE_URL/health"
```

```powershell
curl.exe -s -o NUL -w "Restaurants HTTP Status: %{http_code}`n" "$API_BASE_URL/api/restaurants"
```

Record the UTC evidence time:

```powershell
$EVIDENCE_CHECKED_AT = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
$EVIDENCE_CHECKED_AT
```

A healthy application does not prove recoverability. It establishes only current availability.

### Part 5 — Inspect Agent and Connector Readiness

Discover the agent endpoint and incident wiring through ARM:

```powershell
$AGENT = az rest --method GET --url "https://management.azure.com$AGENT_ID`?api-version=$API_VERSION" | ConvertFrom-Json
$AGENT_ENDPOINT = $AGENT.properties.agentEndpoint.TrimEnd('/')

[pscustomobject]@{
	Endpoint     = $AGENT_ENDPOINT
	IncidentType = $AGENT.properties.incidentManagementConfiguration.type
	Connection   = $AGENT.properties.incidentManagementConfiguration.connectionName
	ActionMode   = $AGENT.properties.actionConfiguration.mode
	ActionAccess = $AGENT.properties.actionConfiguration.accessLevel
} | Format-List
```

Request a short-lived data-plane token:

```powershell
$TOKEN = (az account get-access-token --resource https://azuresre.dev --query accessToken -o tsv).Trim()
$HEADERS = @{ Authorization = "Bearer $TOKEN" }
```

Never print or persist `$TOKEN`.

Inventory live connectors:

```powershell
$CONNECTOR_RESPONSE = Invoke-RestMethod `
	-Uri "$AGENT_ENDPOINT/api/v2/extendedAgent/connectors" `
	-Headers $HEADERS `
	-Method Get

$CONNECTOR_RESPONSE | ConvertTo-Json -Depth 10
```

Record whether an authorized Teams connector and post-message tool are actually visible. ARM incident wiring does not prove Teams delivery readiness.

### Part 6 — Classify the Assurance State

Complete this evidence table before drafting a message:

| Evidence | Observed value | UTC time | Proven or unavailable |
|---|---|---|---|
| Vault and protected item |  |  |  |
| Latest job state |  |  |  |
| Latest usable recovery point |  |  |  |
| RPO target and current risk |  |  |  |
| Grubify health |  |  |  |
| SRE Agent incident wiring |  |  |  |
| Teams connector and tool |  |  |  |

Classify the result as one of:

- **confirmed failure** — failed job or unhealthy protection is directly observed;
- **assurance risk** — protection, recovery-point freshness, or required evidence is unavailable or degraded;
- **healthy or in progress** — evidence shows expected protection activity without a confirmed failure.

Pending initial protection is not a confirmed failed backup.

### Part 7 — Draft the Review-Ready Teams Update

Set each field from observed evidence. Use `unavailable` rather than guessing:

```powershell
$SEVERITY = '<severity-or-assurance-level>'
$AFFECTED_WORKLOAD = '<protected-workload-or-scope>'
$APPLICATION_IMPACT = '<observed-impact>'
$LATEST_JOB_STATE = '<state-and-utc-time-or-unavailable>'
$LATEST_RECOVERY_POINT = '<utc-time-or-unavailable>'
$RPO_RISK = '<assessment>'
$CONFIDENCE = '<level-and-supporting-evidence>'
$RECOMMENDED_ACTION = '<reviewed-action-or-next-read>'
$INCIDENT_LINK = '<portal-or-incident-url>'
```

Render the message without posting it:

```powershell
$TEAMS_MESSAGE = @"
EXERCISE - Backup assurance review
Severity: $SEVERITY
Affected workload: $AFFECTED_WORKLOAD
Application impact: $APPLICATION_IMPACT
Latest job state: $LATEST_JOB_STATE
Latest usable recovery point: $LATEST_RECOVERY_POINT
RPO risk: $RPO_RISK
Confidence: $CONFIDENCE
Recommended action: $RECOMMENDED_ACTION
Incident / portal link: $INCIDENT_LINK
"@

$TEAMS_MESSAGE
```

Do not claim delivery unless the connector, destination, authorization, tool invocation, and resulting message are all observed. Evidence-pack mode stops at the review-ready draft.

### Part 8 — Run the Proposal-Only Agent Exercise

Open the deployed SRE Agent:

```powershell
Start-Process $AGENT_ENDPOINT
```

Submit this prompt with the evidence table and draft message:

> **EXERCISE — NO WRITE AUTHORIZED:** Assess this backup assurance event using the vault, protected-item, job, recovery-point, current application-health, RTO, and RPO evidence I provide. Classify it as confirmed failure, assurance risk, or healthy/in-progress. Identify missing evidence, customer impact, confidence, owner, next action, approval boundary, post-recovery application validation, and escalation conditions. Review the Teams draft, but do not post a message, start a backup, restore data, or change configuration.

The deployed agent is `Autonomous/High`; proposal-only wording is the operational guardrail. Do not request a write merely to demonstrate workflow progress.

### Part 9 — Define Recovery and Closure Evidence

Complete the closure matrix without executing a restore:

| Gate | Required proof | Observed, unavailable, or simulated |
|---|---|---|
| Protection | Healthy item and successful current job |  |
| Recoverability | Usable recovery point within RPO |  |
| Restore | Authorized restore completed when required |  |
| Application | Health and business reads succeed |  |
| Dependencies | Required downstream connections succeed |  |
| Telemetry | No continuing backup or application failure signal |  |
| Communication | Delivery proven or draft explicitly not posted |  |

Restore completion is an intermediate event. Close only when application availability and correctness are proven after the approved recovery path.

Remove the short-lived token:

```powershell
Remove-Variable TOKEN
$HEADERS = $null
```

Resolve the Teams destination at runtime or use a connector-managed destination. Do not commit OAuth tokens, webhook URLs, Team IDs, or Channel IDs. Do not label an in-progress job or pending initial recovery point as a confirmed backup failure.

## Success Criteria

- [ ] Live and evidence-pack modes are selected from observed prerequisites and accurately labeled
- [ ] Vault, protected-item, job, recovery-point, application-health, incident-wiring, and connector evidence are checked separately
- [ ] The assessment correlates backup evidence with application criticality, RTO, RPO, and current health
- [ ] A concise review-ready Teams update is produced without claiming delivery unless delivery evidence is observed
- [ ] The message distinguishes confirmed failure, assurance risk, and healthy in-progress work
- [ ] The proposal-only response includes approval, post-recovery application validation, and escalation conditions without executing a write
- [ ] **Explain to your coach** — why are a successful restore and a healthy application different outcomes, and which validation signals are required before closing the incident?

## Learning Resources

- [Monitor Azure Backup with Azure Monitor](https://learn.microsoft.com/en-us/azure/backup/backup-azure-monitoring-use-azuremonitor)
- [Azure Backup alerts overview](https://learn.microsoft.com/en-us/azure/backup/backup-azure-monitoring-built-in-monitor)
- [Send notifications from Azure SRE Agent](https://learn.microsoft.com/en-us/azure/sre-agent/send-notifications)
- [Connect Azure SRE Agent to Microsoft Teams](https://learn.microsoft.com/en-us/azure/sre-agent/teams-bot)
- [Application resilience in the Azure Well-Architected Framework](https://learn.microsoft.com/en-us/azure/well-architected/reliability/design-resilience)

## Tips

- Report protection state, job state, and recovery-point state separately.
- Keep detailed evidence in the SRE Agent investigation and put only the decision summary in Teams.
- Validation should cover application availability and correctness, not only Azure resource provisioning state.
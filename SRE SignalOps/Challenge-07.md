[< Previous Challenge](./Challenge-06.md) — **[Home](./README.md)** — [Next Challenge >](./Challenge-08.md)

# Challenge 07 — Heartbeat Triage and Deep RCA

> **Incident capability exercised in this challenge**: Missing-Heartbeat Triage · Hypothesis Testing · Recovery Proof

## Introduction

A monitored VM stops sending heartbeats, but the alert does not explain whether the VM, monitoring agent, or telemetry path failed. Simulate that incident and use the SRE Agent to distinguish symptom from root cause, recommend a safe response, and prove recovery with current Azure state and telemetry.

Run every command separately from the repository root and inspect its output before continuing. This mission intentionally does not use a PowerShell script.

## Description

### Part 1 — Reuse the SignalOps Environment

Select the isolated environment and retrieve the deployed workspace and agent IDs:

```powershell
$ErrorActionPreference = 'Stop'

Push-Location '.\SRE SignalOps'
azd env select signalops-core
$WORKSPACE_ID = (azd env get-value LOG_ANALYTICS_WORKSPACE_ID).Trim()
$AGENT_ID = (azd env get-value SRE_AGENT_ID).Trim()
Pop-Location

$API_VERSION = '2026-01-01'
```

Confirm the active subscription and resolved resources:

```powershell
az account show --query '{Subscription:name,SubscriptionId:id,Tenant:tenantId}' -o table

[pscustomobject]@{
	WorkspaceId = $WORKSPACE_ID
	AgentId     = $AGENT_ID
} | Format-List
```

### Part 2 — Choose Live or Evidence-Pack Mode

The Grubify deployment does not create a VM or Azure Monitor Agent. Complete this mission in one of two supported modes:

- **Live mode:** use a coach-provided lab VM with Azure Monitor Agent, a data collection rule, and recent `Heartbeat` records in the connected Log Analytics workspace.
- **Evidence-pack mode:** use a coach-provided alert, heartbeat timeline, VM power-state evidence, Activity Log evidence, and agent-health snapshot. Simulate routing and recovery; do not claim that a live alert fired.

For live mode, set the exact coach-provided VM resource ID. Leave the placeholder unchanged for evidence-pack mode:

```powershell
$VM_RESOURCE_ID = '<coach-provided-vm-resource-id>'
$LIVE_MODE = $VM_RESOURCE_ID -notlike '<*'

[pscustomobject]@{
	Mode         = if ($LIVE_MODE) { 'Live' } else { 'Evidence pack' }
	VmResourceId = $VM_RESOURCE_ID
} | Format-List
```

Do not substitute a production VM. In evidence-pack mode, inspect each supplied artifact separately and retain the `EXERCISE` label in every prompt and result.

### Part 3 — Establish the Heartbeat Baseline

Live mode only: escape the selected ID and query the last 30 minutes of heartbeat data:

```powershell
if ($LIVE_MODE) {
	$ESCAPED_VM_RESOURCE_ID = $VM_RESOURCE_ID.Replace("'", "''")
	az monitor log-analytics query `
		--workspace $WORKSPACE_ID `
		--analytics-query "Heartbeat | where TimeGenerated > ago(30m) | where _ResourceId =~ '$ESCAPED_VM_RESOURCE_ID' | summarize HeartbeatCount=count(), LastHeartbeat=max(TimeGenerated)" `
		-o table
}
```

Do not create a failure condition unless `HeartbeatCount` is greater than zero and `LastHeartbeat` is recent. No row or a stale timestamp is a monitoring setup gap, not proof of a new incident.

Inspect the VM power state independently:

```powershell
if ($LIVE_MODE) {
	az vm get-instance-view `
		--ids $VM_RESOURCE_ID `
		--query '{Name:name,PowerState:instanceView.statuses[?starts_with(code, `PowerState/`)].displayStatus | [0],ProvisioningState:provisioningState}' `
		-o table
}
```

Inspect recent control-plane activity independently:

```powershell
if ($LIVE_MODE) {
	az monitor activity-log list `
		--resource-id $VM_RESOURCE_ID `
		--offset 2h `
		--query '[].{Time:eventTimestamp,Operation:operationName.localizedValue,Status:status.localizedValue,Caller:caller}' `
		-o table
}
```

### Part 4 — Inspect Existing Heartbeat Alerting

Derive the selected VM name and resource group without copying them separately:

```powershell
if ($LIVE_MODE) {
	$VM_ID_PARTS = $VM_RESOURCE_ID -split '/'
	$VM_RESOURCE_GROUP = $VM_ID_PARTS[4]
	$VM_NAME = $VM_ID_PARTS[8]

	[pscustomobject]@{
		ResourceGroup = $VM_RESOURCE_GROUP
		VmName        = $VM_NAME
	} | Format-List
}
```

List log-search alert rules and identify any rule scoped to the selected VM:

```powershell
if ($LIVE_MODE) {
	az monitor scheduled-query list `
		--resource-group $VM_RESOURCE_GROUP `
		--query '[].{Name:name,Enabled:enabled,Severity:severity,Scopes:scopes,EvaluationFrequency:evaluationFrequency,WindowSize:windowSize}' `
		-o jsonc
}
```

The required live rule is enabled, scoped to one VM, evaluates every 5 minutes over a 15-minute window, and fires when the summarized heartbeat count is below `1`. If no such rule exists, record an alerting prerequisite gap and use evidence-pack mode. Do not invent routing or create an alert against an unapproved VM.

### Part 5 — Inspect Agent Incident Wiring

Read the deployed agent configuration through ARM:

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

ARM wiring proves that the agent is connected to Azure Monitor. It does not prove that a particular alert was ingested. Keep evidence-pack intake labeled as simulated.

### Part 6 — Create the Approved Live Condition

Skip this part in evidence-pack mode. In live mode, ask the coach to verify the baseline, selected VM, recovery owner, and maintenance window before continuing.

Display the exact target one final time:

```powershell
if ($LIVE_MODE) {
	[pscustomobject]@{
		Action        = 'Deallocate lab VM'
		ResourceGroup = $VM_RESOURCE_GROUP
		VmName        = $VM_NAME
		ResourceId    = $VM_RESOURCE_ID
	} | Format-List
}
```

Run this state-changing command only after explicit coach authorization:

```powershell
az vm deallocate --resource-group $VM_RESOURCE_GROUP --name $VM_NAME --no-wait
```

Record the UTC start time immediately:

```powershell
$FAULT_STARTED_AT = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
$FAULT_STARTED_AT
```

Observe power state, heartbeat, and alert state with separate commands. Do not interpret command completion as incident intake.

```powershell
az vm get-instance-view --resource-group $VM_RESOURCE_GROUP --name $VM_NAME --query 'instanceView.statuses[?starts_with(code, `PowerState/`)].{Code:code,State:displayStatus}' -o table
```

```powershell
az monitor log-analytics query `
	--workspace $WORKSPACE_ID `
	--analytics-query "Heartbeat | where TimeGenerated > ago(30m) | where _ResourceId =~ '$ESCAPED_VM_RESOURCE_ID' | summarize HeartbeatCount=count(), LastHeartbeat=max(TimeGenerated)" `
	-o table
```

```powershell
az monitor scheduled-query list --resource-group $VM_RESOURCE_GROUP --query '[].{Name:name,Enabled:enabled,Severity:severity}' -o table
```

### Part 7 — Run the Deep RCA Exercise

Open the deployed SRE Agent:

```powershell
Start-Process $AGENT_ENDPOINT
```

Live mode prompt:

> Investigate the missing-heartbeat signal for the single lab VM whose resource ID and evidence I provide. Produce a UTC timeline and evidence matrix covering the last heartbeat, current power state, recent Activity Log, alert configuration, and observed incident intake. Compare at least two plausible hypotheses, reject unsupported hypotheses, state likely cause and contributing factors, assign confidence, and recommend the next safe action. Do not restart or modify the VM.

Evidence-pack prompt:

> **EXERCISE — EVIDENCE PACK:** Investigate the supplied missing-heartbeat timeline, VM state, Activity Log, alert, and monitoring-agent evidence. Distinguish supplied observations from assumptions. Produce competing hypotheses, one rejected hypothesis, likely cause, contributing factors, confidence, next evidence, recovery criteria, and escalation owner. Do not claim a live alert or execute a write.

### Part 8 — Restore and Prove Recovery

Live mode only: run the recovery command as a separate, visible action:

```powershell
az vm start --resource-group $VM_RESOURCE_GROUP --name $VM_NAME
```

Confirm the VM reaches `running`:

```powershell
az vm get-instance-view --resource-group $VM_RESOURCE_GROUP --name $VM_NAME --query 'instanceView.statuses[?starts_with(code, `PowerState/`)].{Code:code,State:displayStatus}' -o table
```

Query only heartbeat records generated after restoration:

```powershell
$RECOVERY_STARTED_AT = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')

az monitor log-analytics query `
	--workspace $WORKSPACE_ID `
	--analytics-query "Heartbeat | where TimeGenerated >= datetime('$RECOVERY_STARTED_AT') | where _ResourceId =~ '$ESCAPED_VM_RESOURCE_ID' | summarize HeartbeatCount=count(), FirstHeartbeat=min(TimeGenerated), LastHeartbeat=max(TimeGenerated)" `
	-o table
```

Inspect alert state separately in Azure Monitor or from the coach-provided alert evidence. Recovery is proven only when the VM is running, a new heartbeat arrives after restoration, and the alert resolves. In evidence-pack mode, state those exact required observations without claiming they occurred.

### Part 9 — Record the Incident Timeline

Complete this matrix from command output and the agent response:

| Stage | Required evidence | Observed result | Proven, unavailable, or simulated | UTC time |
|---|---|---|---|---|
| Baseline | Recent heartbeat and running VM |  |  |  |
| Alert readiness | One-VM scope, `PT5M`, `PT15M`, threshold below `1` |  |  |  |
| Condition | Approved VM deallocation or supplied evidence |  |  |  |
| Intake | Observed SRE Agent incident or labeled simulation |  |  |  |
| RCA | Competing hypotheses, rejected hypothesis, confidence |  |  |  |
| Recovery action | Explicit VM start or supplied recovery step |  |  |  |
| Recovery proof | Running VM, new heartbeat, resolved alert |  |  |  |

Keep the exercise scoped to one VM. Missing heartbeat remains a symptom until independent evidence supports a cause.

## Success Criteria

- [ ] Live mode has one enabled heartbeat alert with the required scope and timing; evidence-pack mode identifies the supplied rule and labels the run as an exercise
- [ ] A live or simulated incident is routed to the intended SRE Agent response plan and accurately labeled
- [ ] The SRE Agent correlates missing heartbeat data with current VM state and monitoring status
- [ ] The RCA clearly separates observed symptoms, supporting evidence, likely root cause, contributing factors, confidence, and next action
- [ ] The RCA compares at least two plausible hypotheses and explains why one was rejected
- [ ] Live mode proves resumed heartbeat and alert resolution; evidence-pack mode states the exact evidence required to prove recovery
- [ ] **Explain to your coach** — why is “heartbeat missing” a symptom rather than a root cause, and what additional evidence would increase your confidence in the diagnosis?

## Learning Resources

- [Azure Monitor log search alerts](https://learn.microsoft.com/en-us/azure/azure-monitor/alerts/alerts-create-log-alert-rule)
- [Azure Monitor Agent overview](https://learn.microsoft.com/en-us/azure/azure-monitor/agents/azure-monitor-agent-overview)
- [Azure Monitor alerts and state](https://learn.microsoft.com/en-us/azure/azure-monitor/alerts/alerts-overview)
- [Automate incident response with Azure SRE Agent](https://learn.microsoft.com/en-us/azure/sre-agent/automate-incidents)

## Tips

- Confirm that the VM has recent heartbeat records before creating the failure condition. A missing baseline is a monitoring setup issue, not an incident.
- Compare the alert timestamp with VM power-state changes and the most recent heartbeat timestamp.
- A strong RCA states uncertainty. Do not call a stopped VM a monitoring-agent failure unless the evidence supports it.
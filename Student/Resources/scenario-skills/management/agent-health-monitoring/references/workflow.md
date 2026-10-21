# Evidence collection and analysis

## Collection

### 1. Inventory machine and extension identities

Use the VM route only for VMs and connectedmachine route only for Arc machines; the connectedmachine extension must already be available. Page ARG and extension lists; record per machine failures and Retry-After backoff. Identify publisher, extension type and handler version, including AzureMonitorWindowsAgent or AzureMonitorLinuxAgent versus MicrosoftMonitoringAgent or OmsAgentForLinux.

```powershell
az graph query --subscriptions $SUBS --first 1000 --graph-query "Resources | where type in~ ('microsoft.compute/virtualmachines','microsoft.hybridcompute/machines','microsoft.compute/virtualmachines/extensions','microsoft.hybridcompute/machines/extensions') | project id,name,type,properties" --output json
az vm get-instance-view --subscription $SUB --resource-group $RG --name $VM --output json
az connectedmachine extension list --subscription $SUB --resource-group $RG --machine-name $ARC --output json
```

### 2. Correlate actual destination heartbeats

Repeat heartbeat query for every approved intended destination workspace. Discover actual schema first. Left join results to the full machine inventory so never reporting agents remain visible. Partition KQL if capped; deduplicate by resource and destination. An Azure SRE Agent is not an AMA extension and has no guaranteed Heartbeat table contract; assess it only through its separately approved resource status and operational evidence, otherwise Not assessed.

```powershell
az monitor data-collection rule association list-by-resource --subscription $SUB --resource $RESOURCE_ID --output json
$KQL="Heartbeat | where TimeGenerated >= datetime($START) and TimeGenerated < datetime($END) | where _ResourceId in~ (dynamic($RESOURCE_IDS_JSON)) | summarize arg_max(TimeGenerated, Computer, Version, Category, SourceSystem) by _ResourceId"
az monitor log-analytics query --subscription $SUB --workspace $WORKSPACE_GUID --timespan "$START/$END" --analytics-query $KQL --output json
```

## Analysis rules

1. Compute heartbeat age relative to END, not local wall clock. Flag over 15 minutes only when the intended agent destination is queryable; missing destination access makes freshness null.
2. Report extension provisioning failures separately from guest agent Not Ready or Error instance statuses. Succeeded provisioning does not prove telemetry delivery.
3. Keep AMA, legacy Log Analytics agent, Arc connectivity agent and Azure SRE Agent as distinct agent_type values. Use extension metadata and destination mapping, not heartbeat Category alone, to identify type.
4. Record shutdown or deallocated VM state as context for missing heartbeat. Include last heartbeat, reported heartbeat Version and extension version separately.

## Known limits

- Legacy Log Analytics heartbeat semantics do not establish Azure SRE Agent health.
- A machine can have multiple agents and workspaces; querying one workspace cannot establish universal absence of heartbeat.

## Expected validation cases

- Healthy: identified AMA instance has current heartbeat in its intended workspace and healthy extension state.
- Finding: running VM with readable destination has no heartbeat for 22 minutes and extension provisioning error.
- Denied or missing: workspace denied or Azure SRE Agent without documented heartbeat yields null freshness, not an unhealthy host agent.

## Sources

- [AMA troubleshooting and extension checks](https://learn.microsoft.com/en-us/azure/azure-monitor/agents/azure-monitor-agent-troubleshoot-linux-vm) (consulted 2026-10-21).
- [Heartbeat schema and semantics](https://learn.microsoft.com/en-us/azure/azure-monitor/reference/tables/heartbeat) (consulted 2026-10-21).

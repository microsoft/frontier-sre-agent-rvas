# Evidence collection and analysis

## Collection

### 1. High impact management changes

Retain caller, claims, operationName.value, resourceId, status, correlationId and eventTimestamp. Split any capped interval until uncapped, deduplicate eventDataId, and filter locally using exact operation names.

```azurecli
az monitor activity-log list --subscription "<subscription_id>" --start-time "<start_utc>" --end-time "<end_utc>" --max-events 10000 --output json
```

### 2. Key Vault data plane and exported management group events

Execute the management group branch only if the optional group was explicitly approved, otherwise remove that branch before submission. Repeat by individually approved group ID when auditing multiple nodes; group IDs are not hierarchical paths. Validate log schema and exported diagnostic coverage first. Missing tables, fuzzy warnings and ingestion gaps are Not assessed. Never read secret values.

```azurecli
az monitor log-analytics query --subscription "<subscription_id>" --workspace "<workspace_id>" --timespan "<start_utc>/<end_utc>" --analytics-query "union isfuzzy=true (AZKVAuditLogs | where TimeGenerated >= datetime(<start_utc>) and TimeGenerated < datetime(<end_utc>) | where _SubscriptionId == '<subscription_id>' | where OperationName in~ ('SecretGet','SecretList') | project TimeGenerated, source='KeyVaultDataPlane', operation=tostring(OperationName), target=tostring(_ResourceId), identity=tostring(Identity), result=tostring(ResultType)), (AzureActivity | where TimeGenerated >= datetime(<start_utc>) and TimeGenerated < datetime(<end_utc>) | where ResourceId =~ '/providers/Microsoft.Management/managementGroups/<management_group_id>' or tolower(ResourceId) startswith tolower('/providers/Microsoft.Management/managementGroups/<management_group_id>/') | project TimeGenerated, source='ManagementGroupExport', operation=OperationNameValue, target=ResourceId, identity=Caller, result=ActivityStatusValue) | order by TimeGenerated asc" --output json
```

## Analysis rules

1. Select roleAssignments/write and delete, policyAssignments/write and delete, subscription scoped Microsoft.Resources/deployments/write and managementGroups write/delete operations using normalized operationName.value and the target's exact scope.
2. Report success, failure and started events distinctly. Correlate lifecycle events by correlationId and target rather than counting each as a separate completed change.
3. Key Vault SecretGet is data plane evidence from resource logs, not subscription Activity Log. Include result and caller identity where present without exposing request content or secret material.
4. Management group changes outside the subscription require their own approved export. Do not claim a subscription Activity Log scan covers tenant hierarchy changes.
5. Compare collected events with owner approved change windows and actor allowlists; unusual events are review findings, not proof of malicious intent.
6. Record observation bounds, collection latency and inaccessible sources so a quiet period with no export cannot be represented as no privileged activity.

## Known limits

- Activity Log generally excludes data plane reads such as secret access and may arrive after a collection run.
- Management group and Key Vault event coverage depends on preexisting export configuration and authorized workspace access.

## Expected validation cases

- Healthy: an approved role change in a scheduled window is observed with its successful result.
- Finding: an unexpected role assignment write outside the approved window becomes a review finding.
- Denied or missing: absent Key Vault audit table yields Not assessed for secret access even when Activity Log is readable.

## Sources

- [Control plane versus resource log audit](https://learn.microsoft.com/en-us/azure/azure-monitor/fundamentals/activity-log) (consulted 2026-10-21).
- [Verified Key Vault audit identity and operation columns](https://learn.microsoft.com/en-us/azure/azure-monitor/reference/tables/azkvauditlogs) (consulted 2026-10-21).
- [Scoped audit queries](https://learn.microsoft.com/en-us/cli/azure/monitor/log-analytics?view=azure-cli-latest) (consulted 2026-10-21).
- [Key Vault data and secret separation](https://learn.microsoft.com/en-us/azure/key-vault/certificates/about-certificates) (consulted 2026-10-21).

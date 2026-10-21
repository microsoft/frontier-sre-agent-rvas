# Evidence collection and analysis

## Collection

### 1. Inventory alert rules and routing

Page both ARG queries using skip_token. Preserve type specific scope expressions and action group references, scheduled query resource filters and alert processing suppression. Validate all referenced IDs against approved scope before reading them.

```powershell
az graph query --subscriptions $SUBS --first 1000 --graph-query "Resources | where type in~ ('microsoft.insights/metricalerts','microsoft.insights/scheduledqueryrules','microsoft.insights/activitylogalerts','microsoft.insights/actiongroups','microsoft.alertsmanagement/actionrules') | project id,name,type,properties,subscriptionId,resourceGroup" --output json
az graph query --subscriptions $SUBS --first 1000 --graph-query 'Resources | project id,type,name,subscriptionId,resourceGroup' --output json
```

### 2. Collect observed firings and threshold series

Follow every alerts nextLink, respect Retry-After and deduplicate by alert instance ID. Filter startDateTime to the approved window locally. For static threshold candidates, fetch the metric values with az monitor metrics list for the same window and dimensions before recommending dynamic thresholds. Denied history means noise unknown.

```powershell
foreach ($SUB in $SUBS) {
 az rest --method get --url "https://management.azure.com/subscriptions/$SUB/providers/Microsoft.AlertsManagement/alerts?api-version=2019-03-01&customTimeRange=$START/$END" --output json
}
az monitor metrics list-definitions --subscription $SUB --resource $RESOURCE_ID --output json
```

## Analysis rules

1. Count unique fired alert instances per exact rule ID, resolving name only references only when unambiguous. Flag more than 20 in seven days, not repeated polling of one instance.
2. Report disabled rules separately from rules without action groups. A rule intentionally used without notifications needs owner justification, not automatic failure.
3. Expand subscription and resource group scoped rule filters before declaring resource coverage absent; include workload query filters and processing rules. Distinguish no rule from rule disabled or suppressed.
4. Suggest dynamic thresholds only for supported metrics with appropriate seasonal variability, adequate history and no required fixed safety limit. Static safety limits may remain best practice.
5. Do not count metric configuration or successful action group lookup as proof notification reached a human.

## Known limits

- Log query alert coverage cannot always be inferred statically from arbitrary KQL.
- Alerts Management history coverage and retention may differ from configured rule lifetime.

## Expected validation cases

- Healthy: enabled scoped rule routes to a valid action group and fires twice.
- Finding: rule fires 28 times and has no routing justification.
- Denied or missing: denied instance history leaves firing_count null, not zero.

## Sources

- [Azure Monitor alert CLI groups](https://learn.microsoft.com/en-us/cli/azure/monitor?view=azure-cli-latest) (consulted 2026-10-21).
- [Alert listing and history operations](https://learn.microsoft.com/en-us/javascript/api/@azure/arm-alertsmanagement/alertsoperations?view=azure-node-preview) (consulted 2026-10-21).

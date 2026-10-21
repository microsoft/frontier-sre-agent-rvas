# Evidence collection and analysis

## Collection

### 1. Collect platform inventory and seven day series

Filter production tags against approved values locally, then run per VM using only metrics and aggregations supported by its definitions. CPU and network aggregations are deliberately separate. Page ARG with skip_token and handle throttling. Preserve each series and dimensions, never silently reduce to one VM.

```powershell
az graph query --subscriptions $SUBS --first 1000 --graph-query "Resources | where type =~ 'microsoft.compute/virtualmachines' | project id,name,tags,subscriptionId,resourceGroup" --output json
az monitor metrics list-definitions --subscription $SUB --resource $VM_ID --output json
az monitor metrics list --subscription $SUB --resource $VM_ID --metrics 'Percentage CPU' --start-time $BASELINE_START --end-time $END --interval PT15M --aggregation Average --output json
az monitor metrics list --subscription $SUB --resource $VM_ID --metrics 'Network In Total' 'Network Out Total' --start-time $BASELINE_START --end-time $END --interval PT15M --aggregation Total --output json
```

### 2. Collect actual guest counter series

Confirm Perf schema and configured counters first; Linux or InsightsMetrics collections need an explicit reviewed adapter, not renamed Windows counters. Partition by VM and day if capped; retry 429 with Retry-After. For available memory, a low deviation is the adverse direction, while used percent and disk queue use high deviation.

```powershell
$KQL="Perf | where TimeGenerated >= datetime($BASELINE_START) and TimeGenerated < datetime($END) | where _ResourceId in~ (dynamic($VM_IDS_JSON)) | where CounterName in ('% Committed Bytes In Use','Available MBytes','Current Disk Queue Length') | summarize value=avg(CounterValue), samples=count() by _ResourceId,ObjectName,CounterName,InstanceName,bin(TimeGenerated,15m)"
az monitor log-analytics query --subscription $SUB --workspace $WORKSPACE_GUID --timespan "$BASELINE_START/$END" --analytics-query $KQL --output json
```

## Analysis rules

1. For each VM, metric, dimension and instance, select the seven preceding daily samples with the same UTC quarter hour as the current completed interval. Exclude current values from baseline.
2. Calculate sample mean and sample standard deviation. Flag current > mean + 2*stdev for CPU, used memory, disk queue and network; for free memory flag current < mean - 2*stdev.
3. Require at least five valid matched historical intervals and adequate within interval sample coverage; otherwise baseline and anomaly verdict are null. Record the minimum sample rule.
4. For zero standard deviation, report changed from constant baseline without dividing by zero. Network totals and rates must use consistent interval units.
5. Correlate anomalies with VM power state and approved changes; statistical deviation is not proof of customer impact.

## Known limits

- Memory and disk queue guest counters are not guaranteed platform metrics.
- Seven daily comparable windows offer a limited baseline and do not model weekly seasonality.

## Expected validation cases

- Healthy: current value remains within two standard deviations of seven comparable windows.
- Finding: CPU 85 exceeds mean 35 plus twice standard deviation 10.
- Denied or missing: guest workspace denied leaves memory and disk queue Not assessed even if CPU is available.

## Sources

- [Read platform metric series](https://learn.microsoft.com/en-us/cli/azure/monitor/metrics?view=azure-cli-latest) (consulted 2026-10-21).
- [Perf counter schema](https://learn.microsoft.com/en-us/azure/azure-monitor/reference/tables/perf) (consulted 2026-10-21).

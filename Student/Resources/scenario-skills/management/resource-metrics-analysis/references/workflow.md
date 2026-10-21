# Evidence collection and analysis

## Collection

### 1. Discover namespaces, definitions and resource limits

Select metric names, namespace, units, supported aggregations and intervals from definitions; do not assume CPU or guest memory exists on every resource type. Read current SKU capacity evidence or use an approved service specific capacity source.

```powershell
az resource show --subscription $SUB --ids $RESOURCE_ID --output json
az monitor metrics list-namespaces --subscription $SUB --resource $RESOURCE_ID --output json
az monitor metrics list-definitions --subscription $SUB --resource $RESOURCE_ID --output json
```

### 2. Retrieve supported time series

Set $METRIC_NAMES to an array selected from discovered definitions and request only supported aggregations, in service supported batches. Retain dimensions and series units, handle nextLink when present and Retry-After, and avoid top filters that silently drop dimensions. If memory is guest only, use the approved Perf or InsightsMetrics schema route and disclose its collection dependency.

```powershell
az monitor metrics list --subscription $SUB --resource $RESOURCE_ID --namespace $NAMESPACE --metrics $METRIC_NAMES --start-time $START --end-time $END --interval PT5M --aggregation Average Maximum --output json
```

## Analysis rules

1. For CPU and other percentage metrics, flag samples above 80 percent directly only when the metric is utilization, not free capacity.
2. For disk IOPS and network rates, divide by verified applicable resource or disk limits after unit normalization; do not compare raw bytes or counts to the number 80.
3. For available memory, derive used percentage only with a verified total capacity; retain separate unknown memory checks when no guest collection exists.
4. Show resource specific supported metrics as well as requested CPU, memory, disk and network coverage. Never replace absent datapoints with zero or combine unlike dimensions.

## Known limits

- Guest memory and some disk counters need separate guest instrumentation.
- Platform metrics exist without diagnostic export, but retention, dimensions and resource limits vary by metric and service.

## Expected validation cases

- Healthy: CPU 45 percent and disk IOPS 40 percent of verified capacity.
- Finding: five minute CPU maximum reaches 92 percent and is flagged with its aggregation.
- Denied or missing: no guest memory source leaves memory utilization null, not zero.

## Sources

- [Metric definitions and values CLI](https://learn.microsoft.com/en-us/cli/azure/monitor/metrics?view=azure-cli-latest) (consulted 2026-10-21).
- [Platform metric collection versus export](https://learn.microsoft.com/en-us/azure/azure-monitor/data-collection/diagnostic-settings) (consulted 2026-10-21).

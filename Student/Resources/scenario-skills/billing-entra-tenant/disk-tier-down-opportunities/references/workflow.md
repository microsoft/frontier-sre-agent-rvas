# Evidence collection and analysis

## Collection

### 1. Premium and Ultra configuration

Retain disk size, diskIOPSReadWrite, diskMBpsReadWrite when returned, diskState, zones and attachment. Page with --skip-token from skipToken. Do not treat absent provisioned limits as zero.

```azurecli
az graph query --subscriptions "<subscription_id>" --first 1000 -q "Resources | where type =~ 'microsoft.compute/disks' | where tostring(sku.name) startswith 'Premium' or tostring(sku.name) startswith 'Ultra' | project id, name, subscriptionId, resourceGroup, sku, managedBy, properties" --output json
```

### 2. Disk and VM metric capabilities

Repeat for disk and owning VM as needed. Map disk LUN dimensions where metrics are VM scoped. Select simultaneous read/write IOPS and throughput metrics with units and supported time grain; do not mix aggregate VM IO with per disk demand.

```azurecli
az monitor metrics list-definitions --subscription "<subscription_id>" --resource "<resource_id>" --output json
```

### 3. Fourteen day demand samples

The declared array queries one validated metric per iteration and preserves spaces inside names. Use aggregations only where definitions support them. Split into bounded daily calls preserving UTC edges and disk/LUN dimensions. Calculate percentiles locally from returned samples, not an unsupported Azure Metrics Percentile aggregation.

```azurecli
[string[]]$METRIC_NAMES = '<metric_names>' -split ','
foreach ($METRIC_NAME in $METRIC_NAMES) {
    az monitor metrics list --subscription "<subscription_id>" --resource "<resource_id>" --metrics $METRIC_NAME --start-time "<start_utc>" --end-time "<end_utc>" --interval PT1M --aggregation Average Maximum --output json
}
```

## Analysis rules

1. For each disk align timestamped read and write rates, sum them per timestamp, then calculate nearest rank P95 for IOPS and throughput separately. Do not add separate P95 values and call the result a combined P95.
2. Report sampling interval, valid bucket coverage, P95, maximum of available maxima and current provisioned limits. Minute aggregates do not prove absence of sub minute bursts.
3. Evaluate target size capacity, IOPS and throughput with customer approved headroom, VM IO limits, latency, caching, shared disks, zone and redundancy constraints. A candidate requires all applicable checks, not merely low P95.
4. Separate Premium SSD, Premium SSD v2 and Ultra conversion constraints. Do not imply Ultra can always change directly to Standard SSD; emit a migration review requirement where direct conversion is unsupported or unverified.
5. Calculate monthly savings only from validated comparable source and target quotes, including transaction costs where applicable. Without quotes report savings_estimate null and rate_evidence missing.
6. Produce a review recommendation with maintenance, backup, rollback and post change latency validation requirements; never change disk SKU.

## Known limits

- Minute aggregate P95 can hide short bursts and cannot guarantee latency on Standard SSD.
- Direct tier conversion and throughput limits vary by disk family; quotes and conversion eligibility require customer specific verification.

## Expected validation cases

- Healthy: a disk exceeds target throughput and is not a tier reduction candidate.
- Finding: measured demand with headroom fits a verified target and all constraints pass, producing a review candidate with quoted savings.
- Denied or missing: missing LUN mapping, unsupported metrics or absent prices results in unknown demand or null savings, not automatic eligibility.

## Sources

- [VM and managed disk performance interaction](https://learn.microsoft.com/en-us/azure/virtual-machines/disks-performance) (consulted 2026-10-21).
- [Metric capabilities and supported aggregations](https://learn.microsoft.com/en-us/cli/azure/monitor/metrics?view=azure-cli-latest) (consulted 2026-10-21).
- [Managed disk inventory and paging](https://learn.microsoft.com/en-us/cli/azure/graph?view=azure-cli-latest) (consulted 2026-10-21).

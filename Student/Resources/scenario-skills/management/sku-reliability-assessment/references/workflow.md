# Evidence collection and analysis

## Collection

### 1. Inventory production resources and dependencies

Filter exact approved production and SLA tag values locally. Follow skip_token, obey Retry-After and keep a complete assessed inventory. Resolve VM scale set, availability set, SQL pool and App Service serverFarmId references only when approved.

```powershell
az graph query --subscriptions $SUBS --first 1000 --graph-query 'Resources | project id,name,type,sku,zones,properties,tags,subscriptionId,resourceGroup' --output json
```

### 2. Read architecture specific reliability settings

Run only applicable commands. Capture actual zones and instance count, SQL zoneRedundant and tier, storage SKU and service operation, App Service plan SKU, zoneRedundant and worker count. Read approved ASE metadata when applicable. A referenced plan outside approved scope remains unassessed.

```powershell
az vm show --subscription $SUB --ids $VM_ID --output json
az vmss show --subscription $SUB --ids $VMSS_ID --output json
az sql db show --subscription $SUB --resource-group $RG --server $SERVER --name $DATABASE --output json
az storage account show --subscription $SUB --ids $STORAGE_ID --output json
az appservice plan show --subscription $PLAN_SUB --ids $PLAN_ID --output json
```

## Analysis rules

1. For VMs distinguish a single zonal instance from multiple instances spread across zones or fault domains. VMSS membership alone does not prove zone resilience or a 99.99 percent commitment.
2. For SQL compare actual zone redundancy, service tier and regional support with the applicable current SLA clause. A tier label alone is insufficient.
3. For Storage separate durability, regional recovery and read or write availability. GRS is asynchronous geographic redundancy, not automatically zone redundancy or a universal higher availability SLA.
4. For App Service evaluate actual plan, instance count, zone redundancy, ASE configuration and dependencies. Premium or ASE alone is not proof the target is met.
5. Compare numeric commitment to customer target only with exact verified official terms and supported configuration. Otherwise produce architecture concerns with sla_percent null.
6. Do not multiply or average service SLAs into a workload promise without an explicit dependency and failure model.

## Known limits

- SLA terms depend on configuration, operations, exclusions and the current contract; this library does not embed universal SKU percentages.
- Redundancy and durability do not demonstrate workload availability or achieved service level.

## Expected validation cases

- Healthy: exact verified clause and actual architecture support the stated target.
- Finding: one VM in one zone has no demonstrated multi instance zone resilience despite a target tag.
- Denied or missing: unavailable current SLA clause or unreadable hosting plan leaves numeric SLA and target verdict null.

## Sources

- [VM reliability architecture](https://learn.microsoft.com/en-us/azure/reliability/reliability-virtual-machines) (consulted 2026-10-21).
- [SQL reliability architecture](https://learn.microsoft.com/en-us/azure/reliability/reliability-sql-database) (consulted 2026-10-21).
- [App Service reliability architecture](https://learn.microsoft.com/en-us/azure/reliability/reliability-app-service) (consulted 2026-10-21).
- [Storage redundancy and durability](https://learn.microsoft.com/en-us/azure/storage/common/storage-redundancy) (consulted 2026-10-21).

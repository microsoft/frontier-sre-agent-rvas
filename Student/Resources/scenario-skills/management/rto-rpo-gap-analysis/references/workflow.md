# Evidence collection and analysis

## Collection

### 1. Collect critical inventory and recovery mechanisms

Dispatch only applicable commands per actual resource type, and include SQL STR/LTR, File share and Backup vault coverage routes for applicable critical resources. Repeat across every approved vault and replica; page ARG and vault lists, obey Retry-After. Compare source IDs, not display names. For other critical resource types require provider specific owner supplied recovery artifacts rather than assuming these routes cover all services.

```powershell
az graph query --subscriptions $SUBS --first 1000 --graph-query "Resources | where tostring(tags['Tier']) =~ 'Critical' | project id,type,name,tags,properties,sku,subscriptionId,resourceGroup" --output json
az backup item list --subscription $VAULT_SUB --resource-group $VAULT_RG --vault-name $VAULT --backup-management-type AzureIaasVM --output json
az backup policy list --subscription $VAULT_SUB --resource-group $VAULT_RG --vault-name $VAULT --output json
az backup job list --subscription $VAULT_SUB --resource-group $VAULT_RG --vault-name $VAULT --output json
az sql db replica list-links --subscription $SUB --resource-group $RG --server $SERVER --name $DATABASE --output json
az storage account show --subscription $SUB --ids $STORAGE_ID --expand geoReplicationStats --output json
az cosmosdb show --subscription $SUB --resource-group $RG --name $COSMOS_ACCOUNT --output json
```

### 2. Read actual lag and drill evidence

sqlcmd with Microsoft Entra authentication and separately authorized SQL endpoint access is optional and read only; no credentials are placed in arguments. DMV lag is available on the primary only. If unavailable, use approved retained replication telemetry or leave lag null. Drill artifact must identify workload, tested failure mode, resource IDs, timestamps, data watermark, validation probes, outcome and evidence source. Do not execute a drill.

```powershell
sqlcmd -S $APPROVED_SQL_HOST -d $DATABASE -G -Q 'SELECT partner_server, partner_database, last_replication, replication_lag_sec, replication_state_desc FROM sys.dm_geo_replication_link_status;'
Get-Content -Raw .\approved-recovery-objectives.json | ConvertFrom-Json
Get-Content -Raw .\approved-drill-evidence.json | ConvertFrom-Json
```

## Analysis rules

1. Require explicit workload objectives in seconds and distinguish region loss, zone loss, corruption and deletion recovery. Resource redundancy is not automatically a workload recovery plan.
2. Compare scheduled backup interval and latest successful recovery point age with RPO, allowing for failed jobs and application consistency. Policy frequency alone does not prove achieved RPO.
3. Compare measured replication lag or last synchronized data watermark with RPO for the same failure mode and time. Geo replication enabled without measured lag leaves achieved RPO unknown.
4. Calculate drill recovery time from impact or declared recovery start to validated workload availability, and data loss from failure timestamp to recovered application watermark. Compare both to RTO and RPO.
5. Verify failover plan ownership, dependency ordering and drill recency against customer policy. Missing drill evidence means RTO and recovery feasibility are unverified, even with healthy configuration.
6. Report per resource gaps and aggregate by workload dependency critical path; do not average resource recovery times to claim workload RTO.

## Known limits

- Backup settings and replica presence cannot establish a demonstrated RTO or end to end RPO.
- Some services require data plane or owner drill evidence; inaccessible lag or missing drill results remain null.

## Expected validation cases

- Healthy: verified restore drill meets both workload objectives with recovered data watermark.
- Finding: configured daily backup cannot support a 15 minute RPO and the last drill exceeds RTO.
- Denied or missing: replication enabled but lag denied and no drill evidence leaves achieved RTO and RPO null.

## Sources

- [Reliability and recovery testing](https://learn.microsoft.com/en-us/azure/well-architected/reliability/reliability-test) (consulted 2026-10-21).
- [SQL replica link reads](https://learn.microsoft.com/en-us/cli/azure/sql/db/replica?view=azure-cli-latest) (consulted 2026-10-21).
- [Measured SQL geo replication lag](https://learn.microsoft.com/en-us/sql/relational-databases/system-dynamic-management-objects/sys-dm-geo-replication-link-status-azure-sql-database?view=azuresqldb-current) (consulted 2026-10-21).
- [Backup policies, items and jobs](https://learn.microsoft.com/en-us/cli/azure/backup?view=azure-cli-latest) (consulted 2026-10-21).

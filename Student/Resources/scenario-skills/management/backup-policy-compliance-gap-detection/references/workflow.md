# Evidence collection and analysis

## Collection

### 1. Collect VM and File share protection and jobs

Repeat across all approved vaults and storage accounts; do not use storage account keys. Page all inventory, item and job lists; filter jobs by actual returned UTC start and end times locally, and respect Retry-After. Join protected items by source resource ID and File share identity, not friendly name. Retain Backup vault instances separately from Recovery Services items, dispatching applicable provider policy and job reads when present.

```powershell
az graph query --subscriptions $SUBS --first 1000 --graph-query "Resources | where type in~ ('microsoft.compute/virtualmachines','microsoft.sql/servers/databases','microsoft.documentdb/databaseaccounts','microsoft.storage/storageaccounts','microsoft.recoveryservices/vaults','microsoft.dataprotection/backupvaults') | project id,name,type,properties,subscriptionId,resourceGroup" --output json
az backup item list --subscription $VAULT_SUB --resource-group $VAULT_RG --vault-name $VAULT --backup-management-type AzureIaasVM --output json
az backup item list --subscription $VAULT_SUB --resource-group $VAULT_RG --vault-name $VAULT --backup-management-type AzureStorage --output json
az backup policy list --subscription $VAULT_SUB --resource-group $VAULT_RG --vault-name $VAULT --output json
az backup job list --subscription $VAULT_SUB --resource-group $VAULT_RG --vault-name $VAULT --output json
az storage share-rm list --subscription $SUB --resource-group $RG --storage-account $STORAGE_ACCOUNT --output json
az dataprotection backup-instance list --subscription $BACKUP_SUB --resource-group $BACKUP_RG --vault-name $BACKUP_VAULT --output json
```

### 2. Read SQL and Cosmos service managed backup evidence

Repeat per actual database and account, excluding system databases with documented reasons. Capture SQL earliestRestoreDate and retention evidence and Cosmos backupPolicy.type. SQL automatic backups do not appear as Recovery Services VM jobs. Provider specific recovery point APIs or approved restore evidence are required for actual freshness when configuration does not expose it; otherwise last_successful_backup is null.

```powershell
az sql db show --subscription $SUB --resource-group $RG --server $SERVER --name $DATABASE --output json
az sql db str-policy show --subscription $SUB --resource-group $RG --server $SERVER --name $DATABASE --output json
az sql db ltr-policy show --subscription $SUB --resource-group $RG --server $SERVER --name $DATABASE --output json
az cosmosdb show --subscription $SUB --resource-group $RG --name $COSMOS_ACCOUNT --output json
```

## Analysis rules

1. Left join all inventoried VMs and File shares against protection sources and approved exceptions. Absence of a visible item is confirmed unprotected only when all applicable approved vault scopes are assessed.
2. Evaluate SQL PITR retention separately from optional or required LTR. No LTR policy does not mean no automatic SQL backups.
3. Flag Cosmos periodic mode when continuous backup is explicitly required; periodic backup is not absence of backup.
4. Report failed jobs in seven days and source items whose verified latest successful backup or recovery point is older than 24 hours; never use job creation time or a failed attempt as success.
5. Compare latest recoverable data age and configured schedule to RPO, keeping retention and recoverability distinct. Missing actual recovery point evidence remains null.

## Known limits

- SQL and Cosmos service managed backups are not represented by Azure Backup VM jobs.
- Vault visibility and configuration do not prove successful application consistent restore or complete recovery point history.

## Expected validation cases

- Healthy: VM and File share have recent successful items; SQL has PITR and required LTR; Cosmos uses required continuous mode.
- Finding: protected VM has failed jobs and latest success is 30 hours old.
- Denied or missing: vault denied makes VM protection unknown; absent SQL LTR alone is not classified as no backup.

## Sources

- [Azure Backup read operations](https://learn.microsoft.com/en-us/cli/azure/backup?view=azure-cli-latest) (consulted 2026-10-21).
- [Backup vault instance inventory](https://learn.microsoft.com/en-us/cli/azure/dataprotection/backup-instance?view=azure-cli-latest) (consulted 2026-10-21).
- [SQL short term retention](https://learn.microsoft.com/en-us/cli/azure/sql/db/str-policy?view=azure-cli-latest) (consulted 2026-10-21).
- [SQL long term retention](https://learn.microsoft.com/en-us/cli/azure/sql/db/ltr-policy?view=azure-cli-latest) (consulted 2026-10-21).
- [Cosmos account configuration](https://learn.microsoft.com/en-us/cli/azure/cosmosdb?view=azure-cli-latest) (consulted 2026-10-21).

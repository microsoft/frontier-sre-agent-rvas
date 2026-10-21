# Evidence collection and analysis

## Collection

### 1. Production scope and protected resource types

Page each query with its own skipToken and --skip-token. Subscription tags select scope but are not assumed inherited onto resource tags.

```azurecli
az graph query --subscriptions "<subscription_id>" --first 1000 -q "ResourceContainers | where type =~ 'microsoft.resources/subscriptions' | project id, subscriptionId, tags" --output json
az graph query --subscriptions "<subscription_id>" --first 1000 -q "Resources | where type in~ ('microsoft.compute/virtualmachines','microsoft.sql/servers','microsoft.storage/storageaccounts','microsoft.keyvault/vaults','microsoft.containerservice/managedclusters') | project id, name, type, subscriptionId, resourceGroup, tags" --output json
```

### 2. Subscription and resource group locks

Read subscription and group lock assignments. Retain full lock IDs to establish their exact protected scope and inheritance; deduplicate repeated lock IDs.

```azurecli
az lock list --subscription "<subscription_id>" --output json
az lock list --subscription "<subscription_id>" --resource-group "<resource_group>" --output json
```

### 3. Locks at the exact resource

Validate the resource ID, constrain the URL to approved ARM scope and follow nextLink only on the same host. Combine direct and ancestor locks; do not equate an empty direct list with no effective lock.

```azurecli
az rest --method get --subscription "<subscription_id>" --url "https://management.azure.com<resource_id>/providers/Microsoft.Authorization/locks?api-version=2016-09-01" --output json
```

## Analysis rules

1. Select the requested five resource families only in subscriptions whose documented Environment tag qualifies as Production. Explicitly report unsupported or missing subscription tag visibility.
2. For each resource evaluate subscription, group and resource locks along its actual scope ancestry. ReadOnly is stronger than CanNotDelete and inherited coverage counts.
3. Flag targets lacking an effective CanNotDelete or ReadOnly lock unless an approved exemption applies. Retain exemption rationale and scope.
4. Recommend CanNotDelete for deletion protection when aligned with customer policy; recommend ReadOnly only after checking blocked operational POST actions, service management and automation impact.
5. Explain that locks protect control plane operations, not SQL rows, storage objects or Key Vault data. Effective lock coverage is not a backup or data protection verdict.

## Known limits

- An empty direct lock list does not rule out inherited protection.
- ReadOnly can block required management operations, and neither lock type protects underlying data plane content.

## Expected validation cases

- Healthy: a production storage account inherits CanNotDelete from its group and passes.
- Finding: an approved production SQL server has no direct or inherited lock and is flagged.
- Denied or missing: denied subscription lock read leaves effective coverage Not assessed even if direct locks are empty.

## Sources

- [Lock inheritance, control plane boundaries and operational effects](https://learn.microsoft.com/en-us/azure/azure-resource-manager/management/lock-resources) (consulted 2026-10-21).
- [Resource locks and resource metadata](https://learn.microsoft.com/en-us/cli/azure/resource?view=azure-cli-latest) (consulted 2026-10-21).
- [Production scope inventory](https://learn.microsoft.com/en-us/cli/azure/graph?view=azure-cli-latest) (consulted 2026-10-21).

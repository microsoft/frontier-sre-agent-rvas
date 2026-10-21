# Evidence collection and analysis

## Collection

### 1. Regional compute and family limits

Retain name.value, localized name, currentValue, limit and unit. Include both total regional vCPUs and each family, with spot limits separate where returned.

```azurecli
az vm list-usage --subscription "<subscription_id>" --location "<region>" --output json
```

### 2. Public IP and VNet usage

Select returned public IP and virtual network quota entries by provider identifier, preserving SKU specific public IP distinctions. Do not use raw resource counts as a replacement for provider quota usage.

```azurecli
az network list-usages --subscription "<subscription_id>" --location "<region>" --output json
```

### 3. Storage account usage

Read returned count, limit and unit for the requested location. Record provider behavior and any subscription or regional scope distinction, without hardcoding a limit.

```azurecli
az storage account show-usage --subscription "<subscription_id>" --location "<region>" --output json
```

## Analysis rules

1. Create one record per subscription, region and quota identifier, retaining the returned scope and unit. Avoid double counting total vCPU and family quotas as additive capacity.
2. Compute utilization = 100 * currentValue / limit for positive limits. Zero, missing or unsupported limits yield utilization null with reason; no divide by zero.
3. Flag strictly above 80 percent and report remaining headroom and the exact count needed to reach the limit. Exactly 80 percent is watch, not the requested above threshold finding.
4. Cover vCPU families, public IP categories, VNet counts and storage account counts separately for every approved region; unreadable families/regions are Not assessed.
5. Recommend capacity planning or a quota request for the specific provider and region. Do not promise approval, physical capacity or SKU availability from quota headroom.

## Known limits

- Quota headroom is not a reservation or guarantee of regional SKU capacity.
- Some quota categories differ by SKU or provider and may not be exposed by a single usage API; unavailable categories stay unknown.

## Expected validation cases

- Healthy: usage 40 of 100 gives 40 percent and no threshold finding.
- Finding: family usage 81 of 100 gives 81 percent and remaining headroom 19.
- Denied or missing: unavailable storage usage or a zero limit yields null utilization and an explicit coverage gap.

## Sources

- [Regional and subscription limit semantics](https://learn.microsoft.com/en-us/azure/azure-resource-manager/management/azure-subscription-service-limits) (consulted 2026-10-21).
- [Network usage CLI](https://learn.microsoft.com/en-us/cli/azure/network?view=azure-cli-latest) (consulted 2026-10-21).

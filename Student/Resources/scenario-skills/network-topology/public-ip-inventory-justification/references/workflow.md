# Evidence collection and analysis

## Collection

### 1. Public IP properties

Retain ID, ipAddress, SKU/tier, publicIPAllocationMethod, ipConfiguration, NAT gateway references, tags and any provider creation metadata. No universal creation field is assumed.

```azurecli
az network public-ip list --subscription "<subscription_id>" --output json
```

### 2. Association and owner map

Page using skipToken and --skip-token. Follow explicit public IP IDs and NIC VM references locally. A public IP associated to a load balancer must not be incorrectly reported as directly attached to one backend VM.

```azurecli
az graph query --subscriptions "<subscription_id>" --first 1000 -q "Resources | where type in~ ('microsoft.network/networkinterfaces','microsoft.network/loadbalancers','microsoft.network/applicationgateways','microsoft.network/natgateways','microsoft.network/azurefirewalls','microsoft.network/virtualnetworkgateways','microsoft.network/bastionhosts') | project id, name, type, resourceGroup, properties, tags" --output json
```

### 3. VM power state and environment context

Join a direct NIC owner to VM ID and current power state. Group tags provide contextual evidence only under the supplied environment_rules; they do not automatically propagate to resource tags.

```azurecli
az vm list --subscription "<subscription_id>" --show-details --output json
az group list --subscription "<subscription_id>" --output json
```

## Analysis rules

1. Resolve each public IP through all returned association types. Mark unattached only when no owner references remain and the relevant owner inventory is complete.
2. For directly VM owned IP configurations, flag stopped and deallocated states separately. A retained static address may be intentional, and stopped VM state is not a deletion recommendation.
3. Classify production/nonproduction using customer rules and report the evidence source. Unknown environment remains unknown; nonproduction public exposure is a review flag, not inherently forbidden.
4. Preserve SKU, allocation method, IP value and owner ID/type. A null dynamic address is unallocated, not an invalid resource.
5. Keep creation date null if not supplied by trustworthy provider metadata or archived creation records. Request an owner justification and identify DNS/allowlist dependencies before recommending address release.

## Known limits

- Static addresses may be retained for DNS, partner allowlists or recovery even when a VM is stopped.
- Not every public IP owner or creation timestamp is visible from a single resource API.

## Expected validation cases

- Healthy: production public IP with an active approved gateway owner is inventoried without an unattached flag.
- Finding: static IP with complete empty owner references receives an unattached review flag.
- Denied or missing: unavailable owner inventory leaves ownership unknown, not unattached.

## Sources

- [Public IP and association inventory](https://learn.microsoft.com/en-us/cli/azure/network?view=azure-cli-latest) (consulted 2026-10-21).
- [Network owner graph and paging](https://learn.microsoft.com/en-us/cli/azure/graph?view=azure-cli-latest) (consulted 2026-10-21).
- [Public IP translation and effective network path context](https://learn.microsoft.com/en-us/azure/virtual-network/network-security-groups-overview) (consulted 2026-10-21).

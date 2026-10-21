# Evidence collection and analysis

## Collection

### 1. Network and IP protection configuration

Retain VNet enableDdosProtection/ddosProtectionPlan and public IP ddosSettings including protectionMode and plan references when present. The historical name Standard must not hide the current Network versus IP Protection distinction.

```azurecli
az network vnet list --subscription "<subscription_id>" --output json
az network public-ip list --subscription "<subscription_id>" --output json
```

### 2. Public resource placement and plan inventory

Page with --skip-token from skipToken. Join PIP ID to actual frontend/NIC owner and owner subnet/VNet. Load balancer backends are not a single VNet association unless its actual frontend/backends establish it.

```azurecli
az graph query --subscriptions "<subscription_id>" --first 1000 -q "Resources | where type in~ ('microsoft.network/networkinterfaces','microsoft.network/loadbalancers','microsoft.network/applicationgateways','microsoft.network/natgateways','microsoft.network/azurefirewalls','microsoft.network/virtualnetworkgateways','microsoft.network/bastionhosts','microsoft.network/ddosprotectionplans') | project id, name, type, resourceGroup, properties, sku" --output json
```

### 3. Confirm candidate protection state

Confirm relevant VNet, PIP and plan metadata before a coverage verdict. Explicitly scoped external plan references require additional approval; a missing plan read is unknown, not no protection.

```azurecli
az resource show --subscription "<subscription_id>" --ids "<resource_id>" --output json
```

## Analysis rules

1. Build public facing resource counts per VNet by resolving public frontend and NIC subnet references, including Application Gateway. Count distinct public owners and PIPs separately.
2. Evaluate VNet Network Protection enabled plus a valid associated plan, and evaluate explicit public IP protection mode independently. IP Protection can cover an individual eligible PIP without a VNet Network Protection plan.
3. Flag public facing resources without demonstrated enhanced protection as customer policy review findings, while distinguishing platform infrastructure protection from Network/IP Protection. Unsupported resource/PIP SKUs require documented eligibility checks.
4. Do not automatically flag an entire VNet as uncovered when all eligible public IPs have IP Protection. Show per PIP coverage, VNet plan coverage and mixed coverage separately.
5. Estimate plan or IP Protection incremental monthly cost only from rate_evidence, considering already paid shared plans, included quantities and overages. Do not multiply a shared plan base price by every VNet.
6. When rates or allocation are unknown output estimate null and request a rate verification. Recommendations must consider security benefits and existing shared coverage rather than claim guaranteed savings.

## Known limits

- Public endpoint eligibility and DDoS feature scope differ by resource and public IP SKU; configuration must not be generalized across every PaaS endpoint.
- A shared plan has included quantities and allocation constraints, so missing rate evidence prevents a reliable incremental cost estimate.

## Expected validation cases

- Healthy: all eligible PIPs are protected by a valid VNet plan or explicit IP Protection.
- Finding: public Application Gateway PIP has neither valid plan inheritance nor IP Protection and is flagged.
- Denied or missing: unreadable shared plan or unknown rates leaves coverage or estimated cost null, not assumed absent or free.

## Sources

- [DDoS Network versus IP Protection and layer scope](https://learn.microsoft.com/en-us/azure/ddos-protection/ddos-protection-overview) (consulted 2026-10-21).
- [Network configuration read commands](https://learn.microsoft.com/en-us/cli/azure/network?view=azure-cli-latest) (consulted 2026-10-21).
- [Public owner and plan inventory](https://learn.microsoft.com/en-us/cli/azure/graph?view=azure-cli-latest) (consulted 2026-10-21).

# Evidence collection and analysis

## Collection

### 1. PaaS service access properties

This covers the named families and selected additional PaaS, not every Azure service. Page via --skip-token from skipToken. Preserve publicNetworkAccess, service firewall rules and actual returned endpoint properties; absent fields need service specific default verification.

```azurecli
az graph query --subscriptions "<subscription_id>" --first 1000 -q "Resources | where type in~ ('microsoft.storage/storageaccounts','microsoft.sql/servers','microsoft.keyvault/vaults','microsoft.documentdb/databaseaccounts','microsoft.web/sites','microsoft.cognitiveservices/accounts','microsoft.search/searchservices','microsoft.containerregistry/registries') | project id, name, type, resourceGroup, subscriptionId, kind, properties" --output json
```

### 2. Private endpoint targets and approval state

Read automatic and manual privateLinkServiceConnections, target resource IDs, groupIds and privateLinkServiceConnectionState. Cross subscription endpoints outside approval remain unknown rather than absent.

```azurecli
az network private-endpoint list --subscription "<subscription_id>" --output json
```

### 3. Authoritative candidate access configuration

Confirm potential findings against provider metadata, including Storage networkAcls, SQL public access/firewall configuration, Key Vault networkAcls, Cosmos IP/VNet rules and App Service access restrictions when exposed. Additional service specific reads are required if access restrictions are separate child resources.

```azurecli
az resource show --subscription "<subscription_id>" --ids "<resource_id>" --output json
```

## Analysis rules

1. Normalize public access into enabled, disabled or unknown using documented semantics for each service; do not infer enabled or disabled solely from a missing publicNetworkAccess field.
2. Join endpoint connections by target ARM ID and requested subresource. Only Approved connections count as usable private endpoint configuration; Pending, Rejected and Disconnected are separate findings.
3. Flag public access enabled with no approved private endpoint as the requested review pattern, while separately flagging policy requiring private only even when both public and private access coexist.
4. Evaluate service firewall/default action and IP/VNet/access restriction exceptions before claiming internet reachability. PublicNetworkAccess enabled with default deny is not equivalent to open to every source.
5. Report only FQDN/IP values actually exposed by resource metadata, such as Storage primaryEndpoints, SQL fullyQualifiedDomainName, Key Vault vaultUri, Cosmos documentEndpoint and App Service defaultHostName. Never fabricate a hostname from a resource name.
6. Separate configuration posture from effective DNS and route reachability; approved private endpoint configuration still needs DNS and client path validation.

## Known limits

- An enabled public endpoint is not proof of unrestricted internet reachability, and an approved private endpoint does not automatically disable public access.
- Service defaults, child access restrictions and endpoints in other subscriptions require explicit evidence; unknown reads are not absence.

## Expected validation cases

- Healthy: public access disabled with an approved endpoint for the required subresource meets private only policy.
- Finding: public access enabled with no approved endpoint is flagged, with firewall restrictions still reported.
- Denied or missing: inaccessible peer subscription or absent default semantics yields unknown endpoint coverage, not proof of no endpoint.

## Sources

- [Private endpoint approval, subresources and service coverage](https://learn.microsoft.com/en-us/azure/private-link/private-endpoint-overview) (consulted 2026-10-21).
- [Network and private endpoint CLI](https://learn.microsoft.com/en-us/cli/azure/network?view=azure-cli-latest) (consulted 2026-10-21).
- [PaaS discovery and paging](https://learn.microsoft.com/en-us/cli/azure/graph?view=azure-cli-latest) (consulted 2026-10-21).
- [Provider configuration reads](https://learn.microsoft.com/en-us/cli/azure/resource?view=azure-cli-latest) (consulted 2026-10-21).

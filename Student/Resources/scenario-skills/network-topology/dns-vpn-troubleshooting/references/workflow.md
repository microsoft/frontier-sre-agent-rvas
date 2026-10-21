# Evidence collection and analysis

## Collection

### 1. DNS failures by client and domain

Verified DNS proxy columns are used, not imaginary general DNS logs. Split capped queries and retain table availability and diagnostic routing; no table means DNS failures unassessed.

```azurecli
az monitor log-analytics query --subscription "<subscription_id>" --workspace "<workspace_id>" --timespan "<start_utc>/<end_utc>" --analytics-query "AZFWDnsQuery | where TimeGenerated >= datetime(<start_utc>) and TimeGenerated < datetime(<end_utc>) | where _ResourceId =~ '<dns_resource_id>' | where ResponseCode in~ ('NXDOMAIN','SERVFAIL') | summarize failures=count(), first_seen=min(TimeGenerated), last_seen=max(TimeGenerated), errors=make_set(ErrorMessage,20) by SourceIp, QueryName, QueryType, ResponseCode" --output json
```

### 2. VPN tunnel connection state

Match virtualNetworkGateway1/2 IDs to the approved gateway. Retain connectionStatus, provisioning state, BGP enabled/configuration and actual returned timestamps only. Do not request shared keys.

```azurecli
az network vpn-connection list --subscription "<subscription_id>" --resource-group "<resource_group>" --output json
az network vnet-gateway show --subscription "<subscription_id>" --resource-group "<resource_group>" --name "<gateway_name>" --output json
```

### 3. Current BGP peer status

Diagnostic read can require an action permission even though it does not change configuration. The host must authorize this exact tool/arguments and fail closed if denied.

```azurecli
az network vnet-gateway list-bgp-peer-status --subscription "<subscription_id>" --resource-group "<resource_group>" --name "<gateway_name>" --output json
```

### 4. Historical tunnel and routing diagnostics

Retain observed schema rather than invent disconnectReason or lastConnected API properties. Read returned structured fields and messages locally with the gateway's actual diagnostic format. Redact addresses and identifiers before sharing.

```azurecli
az monitor log-analytics query --subscription "<subscription_id>" --workspace "<workspace_id>" --timespan "<start_utc>/<end_utc>" --analytics-query "AzureDiagnostics | where TimeGenerated >= datetime(<start_utc>) and TimeGenerated < datetime(<end_utc>) | where ResourceId =~ '<gateway_id>' | where Category in ('TunnelDiagnosticLog','GatewayDiagnosticLog','RouteDiagnosticLog','IKEDiagnosticLog') | project TimeGenerated, Category, ResourceId, observed_details=pack_all() | order by TimeGenerated asc" --output json
```

## Analysis rules

1. Group NXDOMAIN and SERVFAIL independently by client, domain and query type. NXDOMAIN can be intentional, while SERVFAIL indicates resolver processing failure; neither alone proves the VPN caused the response.
2. Identify disconnected/unknown VPN connections, distinguish provisioning failures and current tunnel state, and join each to gateway ID and peer endpoint.
3. For BGP enabled connections flag peers not in their documented healthy state. For static routing connections mark BGP Not applicable rather than failed.
4. From retained diagnostics extract last successful connection event and explicit disconnect reason only when the log format supports them. Current Connected state is not a historical last successful connection timestamp.
5. Correlate DNS failure spikes and tunnel/BGP events by time and client network. Distinguish evidence of temporal association from a proven route or resolver cause.
6. Recommend ordered checks: private DNS zone/link and forwarding path, expected DNS records, effective routes, on premises DNS reachability, tunnel parameters and BGP routes. No gateway reset, DNS change or packet capture is executed.

## Known limits

- DNS evidence is limited to configured Azure Firewall DNS proxy logs and does not cover every resolver.
- Gateway APIs may not expose disconnect reasons or historical connect times; absent diagnostics leave those fields null.

## Expected validation cases

- Healthy: Connected tunnel, healthy BGP peers and no observed DNS failure groups with confirmed coverage.
- Finding: repeated SERVFAIL from a client subnet coincides with a disconnected tunnel, labeled correlation pending route proof.
- Denied or missing: denied BGP status or absent tunnel logs leaves peer assessment or last connection time unknown.

## Sources

- [DNS response, client and query log schema](https://learn.microsoft.com/en-us/azure/azure-monitor/reference/tables/azfwdnsquery) (consulted 2026-10-21).
- [VPN connection inventory](https://learn.microsoft.com/en-us/cli/azure/network/vpn-connection?view=azure-cli-latest) (consulted 2026-10-21).
- [Gateway and BGP peer status CLI](https://learn.microsoft.com/en-us/cli/azure/network/vnet-gateway?view=azure-cli-latest) (consulted 2026-10-21).
- [VPN diagnostics and monitoring](https://learn.microsoft.com/en-us/azure/vpn-gateway/monitor-vpn-gateway-reference) (consulted 2026-10-21).

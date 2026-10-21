# Evidence collection and analysis

## Collection

### 1. Circuit, gateway and connection inventory

Page using --skip-token from skipToken. Identify classic and Virtual WAN resource families explicitly; do not silently call classic gateway commands for a Virtual WAN resource.

```azurecli
az graph query --subscriptions "<subscription_id>" --first 1000 -q "Resources | where type in~ ('microsoft.network/expressroutecircuits','microsoft.network/virtualnetworkgateways','microsoft.network/connections','microsoft.network/expressroutegateways','microsoft.network/vpngateways','microsoft.network/vpngateways/vpnconnections') | project id, name, type, resourceGroup, subscriptionId, sku, properties" --output json
```

### 2. Circuit peerings and classic tunnel states

Repeat only the appropriate family call per inventoried target. Keep circuit provisioningState, serviceProviderProvisioningState, peerings and returned connectionStatus. Peering Enabled is configuration, not proof an actual BGP session is established.

```azurecli
az network express-route show --subscription "<subscription_id>" --resource-group "<resource_group>" --name "<circuit_name>" --output json
az network express-route peering list --subscription "<subscription_id>" --resource-group "<resource_group>" --circuit-name "<circuit_name>" --output json
az network vpn-connection list --subscription "<subscription_id>" --resource-group "<resource_group>" --output json
```

### 3. Classic gateway BGP state

Run only for a classic BGP enabled gateway after exact diagnostic read authorization. Static routing is Not applicable for BGP; denied status remains unknown.

```azurecli
az network vnet-gateway list-bgp-peer-status --subscription "<subscription_id>" --resource-group "<resource_group>" --name "<gateway_name>" --output json
```

### 4. Metric capability and one hour throughput

Select metrics and aggregation from definitions. The declared array queries one validated metric per iteration and preserves spaces inside names. For byte counters use Total instead, converting bytes over actual bucket seconds to bits per second. Retain tunnel, connection, peering and instance dimensions rather than collapsing a healthy peer over a failed peer.

```azurecli
az monitor metrics list-definitions --subscription "<subscription_id>" --resource "<resource_id>" --output json
[string[]]$METRIC_NAMES = '<metric_names>' -split ','
foreach ($METRIC_NAME in $METRIC_NAMES) {
    az monitor metrics list --subscription "<subscription_id>" --resource "<resource_id>" --metrics $METRIC_NAME --start-time "<start_utc>" --end-time "<end_utc>" --interval PT1M --aggregation Average Maximum --output json
}
```

## Analysis rules

1. Reconcile every approved circuit and gateway inventory item with an assessed family. Classic resources use the supplied status reads; Virtual WAN or unsupported child inventory requires provider specific details and is Not assessed until supplied, never healthy by omission.
2. Flag provisioning failures, unprovisioned provider circuits, disconnected VPN tunnels and unhealthy observed BGP peers. Distinguish maintenance windows, static routing and missing diagnostic permission.
3. For ExpressRoute combine peering configuration with BGP/ARP availability metric evidence where supported. A peering enabled flag is not established BGP, and an unavailable metric leaves session health unknown.
4. Calculate ingress and egress separately over the last hour, normalizing units. Compare per direction rates to circuit provider bandwidth where documented, not a sum of both directions against a single direction limit.
5. For gateway throughput use only a documented relevant SKU capacity with connection/instance scope. Rated throughput is not a guaranteed workload limit; if capacity is unknown utilization percent is null.
6. Report current status, last samples, coverage, observed peak and average, capacity source and candidate owner checks. Never reset gateways, change peerings or submit quota requests.

## Known limits

- Provisioning success and peering Enabled do not prove end to end connectivity or established BGP.
- Gateway capacity depends on SKU and workload, and Virtual WAN status interfaces differ from classic virtual network gateways.

## Expected validation cases

- Healthy: provisioned circuit with healthy observed peer availability and complete low utilization series passes observed checks.
- Finding: a disconnected VPN connection or non established BGP peer is flagged independently of throughput.
- Denied or missing: denied peer diagnostic read or unknown capacity yields null health/capacity evidence, not a healthy peer or zero utilization.

## Sources

- [Circuit and peering CLI](https://learn.microsoft.com/en-us/cli/azure/network/express-route?view=azure-cli-latest) (consulted 2026-10-21).
- [ExpressRoute monitoring and required diagnostic routing](https://learn.microsoft.com/en-us/azure/expressroute/monitor-expressroute) (consulted 2026-10-21).
- [Gateway metrics and resource types](https://learn.microsoft.com/en-us/azure/vpn-gateway/monitor-vpn-gateway-reference) (consulted 2026-10-21).
- [Gateway diagnostic status CLI](https://learn.microsoft.com/en-us/cli/azure/network/vnet-gateway?view=azure-cli-latest) (consulted 2026-10-21).
- [Metric units and aggregation reads](https://learn.microsoft.com/en-us/cli/azure/monitor/metrics?view=azure-cli-latest) (consulted 2026-10-21).

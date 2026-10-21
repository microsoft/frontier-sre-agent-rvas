# Evidence collection and analysis

## Collection

### 1. Local VNet and directed peerings

Retain current address spaces, remote address metadata, peeringState, sync level and transit/access flags as returned.

```azurecli
az network vnet show --subscription "<subscription_id>" --resource-group "<resource_group>" --name "<vnet_name>" --output json
az network vnet peering list --subscription "<subscription_id>" --resource-group "<resource_group>" --vnet-name "<vnet_name>" --output json
```

### 2. Approved reciprocal VNet and peerings

Execute only after remote scope approval, never follow a cross tenant reference as automatic permission. Pair objects by actual local and remote IDs, not peering names.

```azurecli
az network vnet show --subscription "<remote_subscription_id>" --resource-group "<remote_resource_group>" --name "<remote_vnet_name>" --output json
az network vnet peering list --subscription "<remote_subscription_id>" --resource-group "<remote_resource_group>" --vnet-name "<remote_vnet_name>" --output json
```

### 3. Gateway presence for transit validation

Filter gateway subnet IDs to the two approved VNets and minimize unrelated returned metadata in the report. Virtual WAN or other unsupported transit designs require their own evidence.

```azurecli
az network vnet-gateway list --subscription "<subscription_id>" --output json
az network vnet-gateway list --subscription "<remote_subscription_id>" --output json
```

## Analysis rules

1. For every directed peering find a reciprocal object whose remoteVirtualNetwork.id equals the local VNet ID. Record local and remote states independently and flag non Connected states.
2. Missing reciprocal objects are findings only after a complete authorized remote list. An unreadable remote scope is Not assessed, not missing.
3. Parse all local and remote IPv4/IPv6 CIDRs with an IP network library and test same family interval overlap. Validate current versus cached remote address space and report stale sync metadata.
4. Gateway transit is intentionally complementary, not symmetric: if one side useRemoteGateways is true, the remote side must allowGatewayTransit and own a compatible gateway; the consuming VNet must not have its own conflicting gateway.
5. Both sides useRemoteGateways, missing gateway owner, or multiple remote gateway choices are review findings. Both transit flags false can be healthy when transit is not required.
6. Report allowVirtualNetworkAccess and allowForwardedTraffic by direction plus design intent. A Connected control plane state does not certify end to end routes or application traffic.

## Known limits

- Cross tenant or unapproved remote subscriptions can prevent reciprocal validation without proving a broken peering.
- Connected state and complementary transit flags do not validate route tables, NSGs or on premises connectivity.

## Expected validation cases

- Healthy: connected reciprocal peers with hub allowGatewayTransit and spoke useRemoteGateways correctly pass.
- Finding: both sides useRemoteGateways or an Initiated side yields a configuration finding.
- Denied or missing: denied remote list leaves reciprocal status unknown rather than absent.

## Sources

- [Directed peering CLI](https://learn.microsoft.com/en-us/cli/azure/network/vnet/peering?view=azure-cli-latest) (consulted 2026-10-21).
- [Peering and complementary gateway transit requirements](https://learn.microsoft.com/en-us/azure/virtual-network/virtual-network-peering-overview) (consulted 2026-10-21).

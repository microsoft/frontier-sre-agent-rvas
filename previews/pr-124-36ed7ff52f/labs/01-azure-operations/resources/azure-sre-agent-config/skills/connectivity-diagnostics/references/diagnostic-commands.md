# Connectivity Diagnostic Commands

Read-only Azure CLI probes and KQL correlation queries for connectivity investigations. Replace
placeholders with values resolved from Azure. Use `GetAzCliHelp` when command syntax differs in the
installed Azure CLI version.

## Which probe answers which question

| Question | Probe |
| --- | --- |
| Which NSG rules actually apply to this NIC right now? | `az network nic list-effective-nsg` |
| Which routes actually apply to this NIC right now? | `az network nic show-effective-route-table` |
| Where does a packet to this destination actually go? | `az network watcher show-next-hop` |
| Would a specific 5-tuple be allowed or denied? | `az network watcher test-ip-flow` |
| Does an end-to-end connection succeed, and where does it stop? | `az network watcher test-connectivity` |
| Did traffic actually reach the endpoint? | `NTANetAnalytics` correlation queries |

Effective rules and effective routes are authoritative: they reflect the merged result of every
NSG and route table applied to the interface, which is why they beat reading a single rule
definition.

## Azure CLI read-only probes

### Effective NSG rules

```bash
az network nic list-effective-nsg \
  --resource-group <resource-group> \
  --name <nic-name> \
  --output table
```

### Effective routes

```bash
az network nic show-effective-route-table \
  --resource-group <resource-group> \
  --name <nic-name> \
  --output table
```

### Next hop

```bash
az network watcher show-next-hop \
  --resource-group <source-vm-resource-group> \
  --vm <source-vm-name> \
  --source-ip <source-private-ip> \
  --dest-ip <destination-ip>
```

### IP flow verify

```bash
az network watcher test-ip-flow \
  --resource-group <source-vm-resource-group> \
  --vm <source-vm-name> \
  --direction Outbound \
  --protocol TCP \
  --local <source-private-ip>:<source-port> \
  --remote <destination-ip>:<destination-port>
```

### Connection troubleshoot

```bash
az network watcher test-connectivity \
  --source-resource <source-vm-resource-id> \
  --dest-address <destination-ip-or-fqdn> \
  --dest-port <destination-port>
```

### Private Endpoint inventory

```bash
az network private-endpoint list \
  --resource-group <resource-group-name> \
  --query "[].{name:name, location:location, subnet:subnet.id, privateLinkServiceConnections:privateLinkServiceConnections[].privateLinkServiceId}" \
  --output table
```

```bash
az network private-endpoint show \
  --resource-group <resource-group-name> \
  --name <private-endpoint-name> \
  --query "{name:name, subnet:subnet.id, customDnsConfigs:customDnsConfigs, networkInterfaces:networkInterfaces}"
```

## KQL correlation queries

### Endpoint conversation

```kql
let EndpointA = "<source-ip>";
let EndpointB = "<destination-ip>";
NTANetAnalytics
| where SubType == "FlowLog" and TimeGenerated > ago(24h)
| where (SrcIp == EndpointA and DestIp == EndpointB) or (SrcIp == EndpointB and DestIp == EndpointA)
| project TimeGenerated, SrcIp, DestIp, DestPort, L4Protocol, FlowDirection, FlowStatus, BytesSrcToDest, BytesDestToSrc, AclRule, SrcSubnet, DestSubnet, IsFlowCapturedAtUDRHop
| order by TimeGenerated desc
```

### Subnet conversations

```kql
NTANetAnalytics
| where SubType == "FlowLog" and TimeGenerated > ago(24h)
| where isnotempty(SrcSubnet) and isnotempty(DestSubnet)
| summarize TotalBytes=sum(BytesSrcToDest + BytesDestToSrc) by SrcSubnet, DestSubnet, L4Protocol, DestPort
| order by TotalBytes desc
```

### Private Endpoint traffic

```kql
let PrivateEndpointIp = "<private-endpoint-private-ip>";
NTANetAnalytics
| where SubType == "FlowLog" and TimeGenerated > ago(24h)
| where DestIp == PrivateEndpointIp or SrcIp == PrivateEndpointIp
| project TimeGenerated, SrcIp, DestIp, DestPort, L4Protocol, FlowDirection, FlowStatus, FlowType, BytesSrcToDest, BytesDestToSrc, SrcSubnet, DestSubnet, PrivateEndpointResourceId, AclRule
| order by TimeGenerated desc
```

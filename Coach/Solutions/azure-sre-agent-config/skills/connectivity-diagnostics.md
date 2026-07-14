# connectivity-diagnostics

Use this skill when diagnosing Azure networking reachability that requires Network Watcher-style reasoning: IP flow verify, NSG diagnostics, next hop, effective security rules, connection troubleshoot, packet capture scoping, topology or flow-log visibility — including the optional Azure Private Endpoint scenario, where traffic is captured from the source VM side rather than at the Private Endpoint itself.

This skill unifies general VM/VNet connectivity diagnostics with Private Endpoint path analysis: the Private Endpoint case is the same "can the source reach the destination?" procedure, with a DNS-resolution and source-side-capture special case.

## Builder Upload Settings

| Field | Value |
| --- | --- |
| Skill name | `connectivity-diagnostics` |
| Primary purpose | Select and run the right read-only Network Watcher connectivity diagnostic for VM/VNet reachability, including Private Endpoint source-side path and DNS analysis. |
| Recommended tools | `RunAzCliReadCommands`, `QueryLogAnalyticsByWorkspaceId`, `GetAzCliHelp` |
| Recommended knowledge files | `vnet-flow-logs/architecture.md`, `vnet-flow-logs/troubleshooting-scenarios.md`, `vnet-flow-logs/vm-application-calls-and-services.md`, `vnet-flow-logs/kql-catalog.md` |
| Default run mode | Read-only diagnostics can run autonomously if the response plan allows; Review for packet capture, DNS, route, NSG, or Private Endpoint changes. |

## Trigger Conditions

Load this skill when the user reports any of the following:

- VM cannot reach another VM, API, DB, private endpoint, firewall, or internet.
- Traffic is allowed in Terraform but appears blocked.
- NSG rule behavior is unclear, or a route table / next hop is unexpected.
- A Network Watcher tool must be chosen (IP flow verify, NSG diagnostics, effective security rules, next hop, connection troubleshoot).
- The Storage Private Endpoint demo is enabled and traffic to a Private Endpoint is missing from flow logs, failing, slow, denied, or routed unexpectedly.
- DNS resolution to a private IP is suspected to be wrong, or the user asks how to identify Private Endpoint traffic in `NTANetAnalytics`.

## Tool Selection Decision Tree

| Symptom | First diagnostic | Why |
| --- | --- | --- |
| Packet allowed or denied? | IP flow verify | Confirms allow/deny for the tuple at VM level. |
| Which NSG/security rule applies? | NSG diagnostics or effective security rules | Shows rule evaluation across subnet/NIC. |
| Wrong path or firewall bypass suspected? | Next hop | Reveals route selection and next-hop type. |
| Point-in-time connectivity test needed? | Connection troubleshoot | Tests reachability to IP/FQDN/URI. |
| Need flow evidence over time? | VNet Flow Logs / Traffic Analytics | Uses historical/aggregated flow data (`traffic-analytics-kql-analysis`). |
| Private Endpoint traffic missing/odd? | DNS check + source-side Traffic Analytics | Flow logs capture the source VM side, not the Private Endpoint itself. |
| Need payload/packet evidence? | Packet capture | Use only after approval and scope minimization. |

## Non-Goals

- Do not modify NSGs, UDRs, route tables, firewall policy, private DNS zones, Private Endpoints, or Storage network rules without Review-mode approval.
- Do not start packet capture without explicit human approval.
- Do not assume a Network Watcher result is the only truth; correlate with Terraform and Traffic Analytics.
- Do not troubleshoot PaaS web analytics as Network Watcher IaaS diagnostics.
- Do not assume missing Private Endpoint-side logs mean no traffic occurred.

## Procedure

1. Identify the source VM/NIC, destination IP/FQDN, destination port, and protocol.
2. Identify the expected path from project docs and Terraform:
   - client → web / internal load balancer.
   - client/app → API/DB.
   - spoke → spoke via Azure Firewall when centralized routing is enabled.
   - source VM → Private Endpoint when the optional Private Endpoint scenario is enabled.
3. Choose the first diagnostic tool using the decision tree.
4. Run read-only Azure CLI diagnostics (effective NSG, effective routes, next hop, IP flow verify, connection troubleshoot).
5. Compare effective Azure state with the Terraform source of truth.
6. Correlate with `NTANetAnalytics` if historical flow evidence is needed.
7. Classify the root cause: NSG, UDR, firewall, DNS, no traffic generated, missing telemetry, RBAC, or unknown.
8. Recommend a read-only next step or a Review-mode remediation.

### Private Endpoint special case

When the destination is (or may be) a Private Endpoint:

1. Confirm the scenario is enabled: check the Terraform Private Endpoint resource and any `enable_private_endpoint_demo` flag, the Private Endpoint resource existence, its IP configuration, and the private DNS zone/link if present.
2. Verify DNS resolution: confirm the FQDN resolves to the Private Endpoint private IP, not a public IP. If it resolves public, inspect the private DNS zone and VNet links (do not modify automatically).
3. Query Traffic Analytics from the source side using the Private Endpoint private IP (VNet Flow Logs record the source VM side, not the Private Endpoint itself). Use `PrivateEndpointResourceId` when populated.
4. Interpret with the Private Endpoint interpretation table below.

| Observation | Interpretation | Next step |
| --- | --- | --- |
| No records for the Private Endpoint IP | No traffic, wrong source side, ingestion delay, or DNS resolves public. | Verify DNS and source VM traffic generation. |
| Records show `FlowStatus contains "Denied"` (or `DeniedInFlows`/`DeniedOutFlows` > 0) | NSG/security rule may block the source-to-Private-Endpoint flow. | Hand off to `nsg-deny-flow-investigation`. |
| Records show a public destination instead of the private IP | DNS likely resolving the public endpoint. | Review the private DNS zone and VNet links. |
| Records show `PrivateEndpointResourceId` | Private Endpoint traffic identified. | Continue with bytes, ports, and source mapping. |
| Route/next hop unexpected | UDR/firewall path issue. | Use next hop / `udr-asymmetry-investigation`. |

## Azure CLI Read Command Patterns

Use `GetAzCliHelp` if command syntax differs in the installed Azure CLI version.

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

## KQL Correlation Snippets

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

## Evidence Required

- Source VM/NIC, source IP and subnet.
- Destination IP/FQDN, port, and protocol.
- Expected path from Terraform / project docs.
- Effective NSG result.
- Effective route / next hop result.
- KQL evidence where historical flow data is needed.
- For Private Endpoint: whether the scenario is enabled, the Private Endpoint name/resource ID/private IP, the DNS result, and the `PrivateEndpointResourceId` value if present.
- Any conflicting evidence between Terraform and live Azure state.

## Output Format

```text
Connectivity question: <source> -> <destination>:<port>/<protocol>
Expected path: <from architecture/Terraform>
Diagnostics performed:
- <tool and command/query>
Evidence:
- NSG/effective security: <result>
- Route/next hop: <result>
- DNS (Private Endpoint cases): <result>
- Traffic Analytics: <result>
- PrivateEndpointResourceId (if applicable): <value>
Likely root cause: <NSG | UDR | firewall | DNS | no traffic | telemetry | RBAC | unknown>
Confidence: High | Medium | Low
Recommended next step: <read-only or Review-mode remediation>
References:
- <project doc>
- <official source>
```

## Escalation

Escalate when:

- Packet capture is required.
- Next hop contradicts Terraform route table expectations.
- NSG diagnostics and Traffic Analytics disagree materially.
- Private DNS zone, Storage firewall/network, or production route/firewall policy changes are required.
- `PrivateEndpointResourceId` is absent despite confirmed traffic after waiting for Traffic Analytics processing.
- The connectivity issue affects a production-like service.

## Related Skills

- `traffic-analytics-kql-analysis`
- `nsg-deny-flow-investigation`
- `udr-asymmetry-investigation`
- `vnet-flow-logs-and-ingestion`
- `rbac-and-resource-access-check`

## Official Sources

- Network Watcher overview: https://learn.microsoft.com/en-us/azure/network-watcher/network-watcher-monitoring-overview
- IP flow verify: https://learn.microsoft.com/en-us/azure/network-watcher/ip-flow-verify-overview
- NSG diagnostics: https://learn.microsoft.com/en-us/azure/network-watcher/nsg-diagnostics-overview
- Next hop: https://learn.microsoft.com/en-us/azure/network-watcher/network-watcher-next-hop-overview
- Connection troubleshoot: https://learn.microsoft.com/en-us/azure/network-watcher/connection-troubleshoot-overview
- VNet Flow Logs Private Endpoint traffic: https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview#private-endpoint-traffic
- Traffic Analytics schema: https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema
- Private Endpoint overview: https://learn.microsoft.com/en-us/azure/private-link/private-endpoint-overview

---
name: connectivity-diagnostics
description: Diagnose Azure VM/VNet reachability by selecting and correlating Network Watcher tests, effective NSG rules, effective routes, next hop, Traffic Analytics, Private Endpoint source-side evidence, and private DNS; remediate only the exact proven NSG or UDR fault when the active trigger permits it.
---

# connectivity-diagnostics

Use this skill when diagnosing Azure networking reachability that requires Network Watcher-style reasoning: IP flow verify, NSG diagnostics, next hop, effective security rules, connection troubleshoot, packet capture scoping, topology or flow-log visibility — including the optional Azure Private Endpoint scenario, where traffic is captured from the source VM side rather than at the Private Endpoint itself.

This skill unifies general VM/VNet connectivity diagnostics with Private Endpoint path analysis: the Private Endpoint case is the same "can the source reach the destination?" procedure, with a DNS-resolution and source-side-capture special case.

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

- Do not modify NSGs, UDRs, route tables, firewall policy, private DNS zones, Private Endpoints, or Storage network rules unless the active trigger permits the action and the evidence identifies the exact minimal change.
- Do not start packet capture unless the active trigger permits it and scope and retention are bounded.
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
8. Recommend or execute the smallest reversible remediation allowed by the active trigger, then verify the path end to end.

### Private Endpoint special case

When the destination is (or may be) a Private Endpoint:

1. Confirm the scenario is enabled: check the Terraform Private Endpoint resource and any `enable_private_endpoint_demo` flag, the Private Endpoint resource existence, its IP configuration, and the private DNS zone/link if present.
2. Verify DNS resolution: confirm the FQDN resolves to the Private Endpoint private IP, not a public IP. If it resolves public, inspect the private DNS zone and VNet links (do not modify automatically).
3. Query Traffic Analytics from the source side using the Private Endpoint private IP (VNet Flow Logs record the source VM side, not the Private Endpoint itself). Use `PrivateEndpointResourceId` when populated.
4. Interpret with the Private Endpoint interpretation table below.

| Observation | Interpretation | Next step |
| --- | --- | --- |
| No records for the Private Endpoint IP | No traffic, wrong source side, ingestion delay, or DNS resolves public. | Verify DNS and source VM traffic generation. |
| Records show `FlowStatus contains "Denied"` (or `DeniedInFlows`/`DeniedOutFlows` > 0) | NSG/security rule may block the source-to-Private-Endpoint flow. | Follow the NSG denial branch below. |
| Records show a public destination instead of the private IP | DNS likely resolving the public endpoint. | Review the private DNS zone and VNet links. |
| Records show `PrivateEndpointResourceId` | Private Endpoint traffic identified. | Continue with bytes, ports, and source mapping. |
| Route/next hop unexpected | UDR/firewall path issue. | Follow the routing asymmetry branch below. |

## Reference File

`connectivity-diagnostics/references/diagnostic-commands.md` holds the read-only Azure CLI probes,
the KQL correlation queries and the table that maps each investigative question to the right probe.
The path above is the exact name the file is registered under. Read it when you need a command,
rather than composing one from memory.

## NSG denial branch

1. Fix the observed five-tuple: source IP, destination IP, destination port, protocol, and direction.
2. Query denied Traffic Analytics records for that tuple and capture `AclRule`, capture point, and timestamp.
3. Run IP Flow Verify and inspect effective security rules on every applicable source and destination NIC/subnet.
4. Resolve the NSG and rule that actually made the decision; do not infer it from a demo name or alert title.
5. Compare the effective rule with the Terraform baseline and classify it as expected policy, temporary overlay, drift, or unknown.
6. If the active trigger permits remediation and impact is proven, remove or correct only the exact offending rule. Preserve unrelated rules and rule ordering.
7. Re-run IP Flow Verify, the application connectivity test, and the denied-flow query. Report success only when the expected path is restored and unrelated policy remains intact.

## Routing asymmetry branch

1. Capture effective routes and Network Watcher next hop for both directions of the failing conversation.
2. Apply longest-prefix-match reasoning to determine which route wins for each direction.
3. Compare effective state with the Terraform routing baseline and all route-table associations.
4. Correlate Traffic Analytics direction, byte counters, capture point, and missing return traffic; unequal bytes alone do not prove asymmetry.
5. Classify the fault as wrong prefix, wrong next hop, missing association, firewall path, blackhole, or insufficient evidence.
6. If the active trigger permits remediation, change only the exact route or association proven faulty; preserve every unrelated route.
7. Re-run effective route, next-hop, connectivity, and flow-evidence checks in both directions before declaring recovery.

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
Recommended next step: <read-only validation or active-trigger-permitted remediation>
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

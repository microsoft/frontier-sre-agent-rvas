# Traffic Analytics Schema Reference

Field semantics for `NTANetAnalytics` and `NTAIpDetails`. Consult this file when building a query
or when a field value needs interpretation.

| Table or field | Meaning |
| --- | --- |
| `NTANetAnalytics` | Main Traffic Analytics table for enriched flow logs. |
| `NTAIpDetails` | Public IP details table for ownership, DNS, location and threat context. |
| `SubType == "FlowLog"` | Filter for flow log records. |
| `SrcIp`, `DestIp`, `DestPort` | Network tuple endpoints and destination port. |
| `L4Protocol` | Layer 4 protocol, typically `T` for TCP and `U` for UDP. |
| `FlowStatus` | Flow status; full word `Denied` or `Allowed` in `NTANetAnalytics`, not the single letters `A` or `D`. |
| `FlowType` | Traffic category such as internal, Azure public, external public, malicious. |
| `BytesSrcToDest`, `BytesDestToSrc` | Forward and return byte counters. |
| `AllowedInFlows`, `AllowedOutFlows`, `DeniedInFlows`, `DeniedOutFlows` | Aggregated flow counters. |
| `AclRule`, `AclGroup` | Rule and ACL or NSG group involved in flow evaluation. |
| `SrcSubnet`, `DestSubnet` | Source and destination subnet enrichment. |
| `IsFlowCapturedAtUDRHop` | Signal for route, UDR and firewall investigations. |

## Field traps that change a conclusion

- `FlowStatus` stores the full word. Matching on the single letter `D` or `A` silently returns zero
  rows and can be misread as "no denied traffic".
- The absence of a separate reverse row does not prove there was no return traffic. Check
  `BytesDestToSrc` and `PacketsDestToSrc` inside the same flow tuple.
- Traffic Analytics is aggregated and delayed. Always report the query window and the latest
  `TimeGenerated`, otherwise a processing delay is indistinguishable from an outage.

## Official sources

- Traffic Analytics schema: https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema
- Traffic Analytics overview: https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics

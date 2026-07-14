# traffic-analytics-kql-analysis

Use this skill when analyzing Azure Traffic Analytics data in Log Analytics, especially `NTANetAnalytics`, top talkers, denied flows, allowed flows, ports, protocols, public traffic, bidirectional conversations, or unexpected flow volume.

## Builder Upload Settings

| Field | Value |
| --- | --- |
| Skill name | `traffic-analytics-kql-analysis` |
| Primary purpose | Query and interpret Traffic Analytics records for network troubleshooting. |
| Recommended tools | `RunAzCliReadCommands`, `QueryLogAnalyticsByWorkspaceId`, `GetAzCliHelp` |
| Recommended knowledge files | `documentation/kql-catalog.md`, `documentation/vm-application-calls-and-services.md`, `documentation/troubleshooting-scenarios.md`, `documentation/official-sources.md` |
| Default run mode | Autonomous for read-only query/reporting; Review for remediation recommendations. |

## Trigger Conditions

Load this skill when the user asks about:

- Top talkers.
- Denied flows.
- Allowed vs blocked traffic.
- Flow direction.
- Traffic between client, web, API, DB, Azure Firewall or Private Endpoint.
- Unexpected public or internet traffic.
- TCP/UDP comparison.
- Traffic Analytics fields or `NTANetAnalytics` query design.
- KQL evidence for an incident response plan.

## Non-Goals

- Do not change alert rules, retention or flow-log settings.
- Do not treat Traffic Analytics as packet capture or application log analysis.
- Do not assume reverse traffic is always a separate row; return traffic can be represented by `BytesDestToSrc` and `PacketsDestToSrc` in the same flow tuple.

## Core Tables And Fields

| Table/field | Meaning |
| --- | --- |
| `NTANetAnalytics` | Main Traffic Analytics table for enriched flow logs. |
| `NTAIpDetails` | Public IP details table for ownership, DNS, location and threat context. |
| `SubType == "FlowLog"` | Filter for flow log records. |
| `SrcIp`, `DestIp`, `DestPort` | Network tuple endpoints and destination port. |
| `L4Protocol` | Layer 4 protocol, typically `T` for TCP and `U` for UDP. |
| `FlowStatus` | Flow status; full word `Denied` or `Allowed` in `NTANetAnalytics` (not the single letters `A`/`D`). |
| `FlowType` | Traffic category such as internal, Azure public, external public, malicious. |
| `BytesSrcToDest`, `BytesDestToSrc` | Forward and return byte counters. |
| `AllowedInFlows`, `AllowedOutFlows`, `DeniedInFlows`, `DeniedOutFlows` | Aggregated flow counters. |
| `AclRule`, `AclGroup` | Rule and ACL/NSG group involved in flow evaluation. |
| `SrcSubnet`, `DestSubnet` | Source and destination subnet enrichment. |
| `IsFlowCapturedAtUDRHop` | Useful signal for route/UDR/firewall investigations. |

## Procedure

1. Confirm the user question and identify the time range. Default to last 24 hours unless the incident provides a more precise window.
2. Confirm the Log Analytics workspace from Terraform output or agent context.
3. Use `documentation/kql-catalog.md` as the project source of truth for query patterns.
4. Start with a freshness query before deeper analysis.
5. Select a targeted query pattern:
   - Top talkers.
   - Denied flows by rule.
   - Subnet-to-subnet conversations.
   - Public or malicious traffic.
   - Endpoint-to-endpoint forward/reverse/bidirectional view.
   - UDR/asymmetry signal.
6. Map IP addresses to project VM roles using `documentation/vm-application-calls-and-services.md` or Terraform outputs.
7. Interpret allowed/denied, bytes, ports and protocol using the project baseline.
8. Produce query, evidence and conclusion. Do not recommend changes without Review mode.

## Approved KQL Query Library

### Ingestion Smoke Test

```kql
NTANetAnalytics
| where SubType == "FlowLog"
| take 10
```

### Top Talkers

```kql
NTANetAnalytics
| where SubType == "FlowLog" and TimeGenerated > ago(24h)
| summarize TotalBytes=sum(BytesSrcToDest + BytesDestToSrc) by SrcIp, DestIp, DestPort, L4Protocol, FlowType
| top 20 by TotalBytes desc
```

### Denied Flows By Rule

```kql
NTANetAnalytics
| where SubType == "FlowLog" and TimeGenerated > ago(24h)
| where FlowStatus contains "Denied" or DeniedInFlows > 0 or DeniedOutFlows > 0
| summarize DeniedFlows=sum(DeniedInFlows + DeniedOutFlows) by AclRule, AclGroup, SrcIp, DestIp, DestPort, L4Protocol
| order by DeniedFlows desc
```

### Subnet-To-Subnet Conversations

```kql
NTANetAnalytics
| where SubType == "FlowLog" and TimeGenerated > ago(24h)
| where isnotempty(SrcSubnet) and isnotempty(DestSubnet)
| summarize TotalBytes=sum(BytesSrcToDest + BytesDestToSrc) by SrcSubnet, DestSubnet, L4Protocol, DestPort
| order by TotalBytes desc
```

### Internet And Public Traffic

```kql
NTANetAnalytics
| where SubType == "FlowLog" and TimeGenerated > ago(24h)
| where FlowType in ("ExternalPublic", "AzurePublic", "MaliciousFlow")
| summarize Flows=sum(AllowedInFlows + DeniedInFlows + AllowedOutFlows + DeniedOutFlows), Bytes=sum(BytesSrcToDest + BytesDestToSrc) by FlowType, SrcIp, DestIp, DestPort, FlowStatus
| order by Bytes desc
```

### Public IP Details

```kql
NTAIpDetails
| where TimeGenerated > ago(24h)
| summarize Count=count() by FlowType, PublicIPDetails, Location, ThreatType, DNSDomain
| order by Count desc
```

### UDR And Asymmetric Routing Signal

```kql
NTANetAnalytics
| where SubType == "FlowLog" and TimeGenerated > ago(24h)
| where SrcIp in ("10.20.1.10", "10.30.2.10") or DestIp in ("10.20.1.10", "10.30.2.10")
| project TimeGenerated, SrcIp, DestIp, DestPort, FlowDirection, FlowStatus, BytesSrcToDest, BytesDestToSrc, IsFlowCapturedAtUDRHop, SrcSubnet, DestSubnet
| order by TimeGenerated desc
```

### Source To Destination On Specific Port

```kql
let SourceIp = "10.20.1.10";
let DestinationIp = "10.30.2.10";
let DestinationPort = 5432;
NTANetAnalytics
| where SubType == "FlowLog" and TimeGenerated > ago(24h)
| where SrcIp == SourceIp and DestIp == DestinationIp and DestPort == DestinationPort
| summarize Flows=sum(AllowedOutFlows + AllowedInFlows + DeniedOutFlows + DeniedInFlows), BytesForward=sum(BytesSrcToDest), BytesReturn=sum(BytesDestToSrc) by SrcIp, DestIp, DestPort, L4Protocol, FlowStatus, AclRule
| order by BytesForward desc
```

### Bidirectional Endpoint View

```kql
let EndpointA = "10.20.1.10";
let EndpointB = "10.30.2.10";
NTANetAnalytics
| where SubType == "FlowLog" and TimeGenerated > ago(24h)
| where (SrcIp == EndpointA and DestIp == EndpointB) or (SrcIp == EndpointB and DestIp == EndpointA)
| extend DirectionLabel = case(SrcIp == EndpointA and DestIp == EndpointB, "A-to-B", SrcIp == EndpointB and DestIp == EndpointA, "B-to-A", "Other")
| summarize Records=count(), ForwardBytes=sum(BytesSrcToDest), ReturnBytes=sum(BytesDestToSrc), TotalBytes=sum(BytesSrcToDest + BytesDestToSrc) by DirectionLabel, SrcIp, DestIp, DestPort, L4Protocol, FlowStatus
| order by TotalBytes desc
```

### No-Data Diagnostic

```kql
NTANetAnalytics
| where TimeGenerated > ago(48h)
| summarize Records=count(), FirstSeen=min(TimeGenerated), LastSeen=max(TimeGenerated) by SubType, FlowType, TargetResourceId
| order by LastSeen desc
```

## Interpretation Rules

- `FlowStatus contains "Denied"` (or `DeniedInFlows > 0` / `DeniedOutFlows > 0`) indicates denied traffic; the field stores the full word `Denied`, not the single letter `D`.
- `FlowStatus contains "Allowed"` indicates allowed traffic (full word `Allowed`, not `A`).
- `L4Protocol == "T"` indicates TCP and `L4Protocol == "U"` indicates UDP.
- High `BytesSrcToDest` and low `BytesDestToSrc` can indicate asymmetric behavior, one-way traffic, blocked return, or normal one-directional traffic depending on protocol/application.
- Absence of separate reverse rows does not prove no return traffic. Check `BytesDestToSrc` and `PacketsDestToSrc`.
- Traffic Analytics is aggregated and delayed; always report the query time window and latest `TimeGenerated`.

## Evidence Required

- Workspace and table queried.
- Time range.
- Full KQL query.
- Record count.
- Top IPs, ports, protocols and flow status.
- Mapping to VM/service names where possible.
- Whether the finding matches expected project baseline.

## Output Format

```text
Question interpreted as: <analysis goal>
Time range: <range>
KQL used:
<query>
Key results:
- <result 1>
- <result 2>
Interpretation: <what it means>
Root cause hypothesis: <if applicable>
Confidence: High | Medium | Low
Next step: <read-only validation or Review-mode remediation>
References:
- documentation/kql-catalog.md
- <official Microsoft URL>
```

## Escalation

Escalate when:

- Query returns no data but flow logs and traffic generation are expected.
- Required fields are absent or schema differs from documented project schema.
- Traffic is classified as malicious or policy-sensitive.
- The next step requires changing NSG, route table, flow log, workspace, Storage or alert configuration.

## Official Sources

- Traffic Analytics overview: https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics
- Traffic Analytics schema: https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema
- Traffic Analytics queries: https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-queries
- Log Analytics API: https://learn.microsoft.com/en-us/azure/azure-monitor/logs/api/overview
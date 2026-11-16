# Approved KQL Query Library — Traffic Analytics

Executable source of truth for `NTANetAnalytics` and `NTAIpDetails`. Copy a query, adjust the time
window and the endpoint literals, and report the query verbatim in the evidence section.

## Ingestion Smoke Test

```kql
NTANetAnalytics
| where SubType == "FlowLog"
| take 10
```

## Top Talkers

```kql
NTANetAnalytics
| where SubType == "FlowLog" and TimeGenerated > ago(24h)
| summarize TotalBytes=sum(BytesSrcToDest + BytesDestToSrc) by SrcIp, DestIp, DestPort, L4Protocol, FlowType
| top 20 by TotalBytes desc
```

## Denied Flows By Rule

```kql
NTANetAnalytics
| where SubType == "FlowLog" and TimeGenerated > ago(24h)
| where FlowStatus contains "Denied" or DeniedInFlows > 0 or DeniedOutFlows > 0
| summarize DeniedFlows=sum(DeniedInFlows + DeniedOutFlows) by AclRule, AclGroup, SrcIp, DestIp, DestPort, L4Protocol
| order by DeniedFlows desc
```

## Subnet-To-Subnet Conversations

```kql
NTANetAnalytics
| where SubType == "FlowLog" and TimeGenerated > ago(24h)
| where isnotempty(SrcSubnet) and isnotempty(DestSubnet)
| summarize TotalBytes=sum(BytesSrcToDest + BytesDestToSrc) by SrcSubnet, DestSubnet, L4Protocol, DestPort
| order by TotalBytes desc
```

## Internet And Public Traffic

```kql
NTANetAnalytics
| where SubType == "FlowLog" and TimeGenerated > ago(24h)
| where FlowType in ("ExternalPublic", "AzurePublic", "MaliciousFlow")
| summarize Flows=sum(AllowedInFlows + DeniedInFlows + AllowedOutFlows + DeniedOutFlows), Bytes=sum(BytesSrcToDest + BytesDestToSrc) by FlowType, SrcIp, DestIp, DestPort, FlowStatus
| order by Bytes desc
```

## Public IP Details

```kql
NTAIpDetails
| where TimeGenerated > ago(24h)
| summarize Count=count() by FlowType, PublicIPDetails, Location, ThreatType, DNSDomain
| order by Count desc
```

## UDR And Asymmetric Routing Signal

```kql
NTANetAnalytics
| where SubType == "FlowLog" and TimeGenerated > ago(24h)
| where SrcIp in ("10.20.1.10", "10.30.2.10") or DestIp in ("10.20.1.10", "10.30.2.10")
| project TimeGenerated, SrcIp, DestIp, DestPort, FlowDirection, FlowStatus, BytesSrcToDest, BytesDestToSrc, IsFlowCapturedAtUDRHop, SrcSubnet, DestSubnet
| order by TimeGenerated desc
```

## Source To Destination On Specific Port

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

## Bidirectional Endpoint View

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

## No-Data Diagnostic

```kql
NTANetAnalytics
| where TimeGenerated > ago(48h)
| summarize Records=count(), FirstSeen=min(TimeGenerated), LastSeen=max(TimeGenerated) by SubType, FlowType, TargetResourceId
| order by LastSeen desc
```

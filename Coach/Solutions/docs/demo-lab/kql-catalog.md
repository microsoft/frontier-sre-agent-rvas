# Demo Lab KQL Catalog

Use these queries through `Student/Resources/scenarios/scripts/run-kql.sh` or directly in Log
Analytics.

The helper supports three execution styles:

```bash
Student/Resources/scenarios/scripts/run-kql.sh sample-food-http-errors
Student/Resources/scenarios/scripts/run-kql.sh --query "
ContainerAppHTTPLogs
| where TimeGenerated > ago(15m)
| take 20"
Student/Resources/scenarios/scripts/run-kql.sh - < query.kql
```

Use the built-in aliases for repeatable demo checks. Use raw KQL, `--query`, or
stdin when you need to narrow the time window, add a specific resource filter, or
run a multi-line troubleshooting query from this catalog.

## Top Talkers

```kql
NTANetAnalytics
| where SubType == "FlowLog" and TimeGenerated > ago(24h)
| summarize TotalBytes=sum(BytesSrcToDest + BytesDestToSrc) by SrcIp, DestIp, DestPort, L4Protocol
| top 20 by TotalBytes desc
```

## Denied Flows

```kql
NTANetAnalytics
| where SubType == "FlowLog" and TimeGenerated > ago(24h)
| where FlowStatus contains "Denied" or DeniedInFlows > 0 or DeniedOutFlows > 0
| summarize DeniedFlows=sum(DeniedInFlows + DeniedOutFlows) by AclRule, SrcIp, DestIp, DestPort, L4Protocol
| order by DeniedFlows desc
```

## Flow Types

```kql
NTANetAnalytics
| where SubType == "FlowLog" and TimeGenerated > ago(24h)
| summarize Flows=sum(AllowedInFlows + DeniedInFlows + AllowedOutFlows + DeniedOutFlows), Bytes=sum(BytesSrcToDest + BytesDestToSrc) by FlowType, FlowStatus
| order by Bytes desc
```

## Public IP Enrichment

```kql
NTAIpDetails
| where TimeGenerated > ago(24h)
| summarize Count=count() by FlowType, PublicIPDetails, Location, ThreatType
| order by Count desc
```

## Sample Food HTTP Errors

```kql
let AppName = "<api-container-app-name>";
ContainerAppHTTPLogs
| where TimeGenerated > ago(24h)
| where ContainerAppName == AppName
| where toint(StatusCode) >= 400
| summarize Errors=count(), StatusCodes=make_set(StatusCode, 10), ExampleDetails=take_any(ResponseCodeDetails) by Method, Path
| order by Errors desc
```

## Sample Food Latency

```kql
let AppName = "<api-container-app-name>";
ContainerAppHTTPLogs
| where TimeGenerated > ago(24h)
| where ContainerAppName == AppName
| summarize Requests=count(), P50=percentile(RequestDuration, 50), P95=percentile(RequestDuration, 95), P99=percentile(RequestDuration, 99) by Path
| order by P95 desc
```

## Sample Food Console Logs

```kql
let AppName = "<api-container-app-name>";
ContainerAppConsoleLogs_CL
| where TimeGenerated > ago(24h)
| where ContainerAppName_s == AppName
| project TimeGenerated, RevisionName_s, ContainerName_s, Log_s
| order by TimeGenerated desc
| take 100
```

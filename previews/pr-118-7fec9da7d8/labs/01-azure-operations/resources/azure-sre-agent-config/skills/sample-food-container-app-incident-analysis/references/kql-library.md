# Approved KQL Query Library — Sample Food Container Apps

Executable queries for Azure Container Apps incident analysis. Replace `<api-container-app-name>`
and `<incident-time-utc>` with values resolved from Azure. Report the query verbatim in the
evidence section.

## Recent HTTP Errors

```kql
let AppName = "<api-container-app-name>";
ContainerAppHTTPLogs
| where TimeGenerated > ago(2h)
| where ContainerAppName == AppName
| where toint(StatusCode) >= 400
| project TimeGenerated, ContainerAppName, RevisionName, ReplicaName, Method, Path, StatusCode, ResponseCodeDetails, ResponseFlags, RequestDuration, RequestId
| order by TimeGenerated desc
```

## Top Failing Endpoints

```kql
let AppName = "<api-container-app-name>";
ContainerAppHTTPLogs
| where TimeGenerated > ago(24h)
| where ContainerAppName == AppName
| where toint(StatusCode) >= 400
| summarize Errors=count(), StatusCodes=make_set(StatusCode, 10), ExampleDetails=take_any(ResponseCodeDetails), P95DurationMs=percentile(RequestDuration, 95) by Method, Path
| order by Errors desc
```

## Latency By Endpoint

```kql
let AppName = "<api-container-app-name>";
ContainerAppHTTPLogs
| where TimeGenerated > ago(24h)
| where ContainerAppName == AppName
| summarize Requests=count(), P50=percentile(RequestDuration, 50), P95=percentile(RequestDuration, 95), P99=percentile(RequestDuration, 99) by Path
| order by P95 desc
```

## Console Logs Around Incident

```kql
let AppName = "<api-container-app-name>";
let IncidentTime = datetime(<incident-time-utc>);
ContainerAppConsoleLogs_CL
| where TimeGenerated between (IncidentTime - 15m .. IncidentTime + 15m)
| where ContainerAppName_s == AppName
| project TimeGenerated, RevisionName_s, ContainerName_s, Log_s
| order by TimeGenerated desc
```

## Revision Provisioning Or Image Pull Issues

```kql
let AppName = "<api-container-app-name>";
ContainerAppSystemLogs_CL
| where TimeGenerated > ago(24h)
| where ContainerAppName_s == AppName
| where Log_s has_any ("ErrImagePull", "ContainerCrashing", "Error provisioning", "Revision", "failed", "timeout")
| project TimeGenerated, EnvironmentName_s, ContainerAppName_s, RevisionName_s, Log_s
| order by TimeGenerated desc
```

## Which table answers which question

| Question | Table |
| --- | --- |
| Which requests failed, with which status and on which route? | `ContainerAppHTTPLogs` |
| What did the application itself print when it failed? | `ContainerAppConsoleLogs_CL` |
| Did the platform fail to start, pull or route the revision? | `ContainerAppSystemLogs_CL` |

Console logs are application evidence and HTTP logs are ingress evidence. Correlate by time,
replica, revision and request ID rather than treating either as complete on its own.

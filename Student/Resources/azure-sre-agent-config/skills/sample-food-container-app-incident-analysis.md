# sample-food-container-app-incident-analysis

Use this skill when investigating incidents for the Sample Food Ordering App lab deployed on Azure Container Apps, especially HTTP 5xx errors, slow endpoints, memory pressure, container restarts, revision failures, image pull issues, or frontend/API integration problems.

## Trigger Conditions

Load this skill when the user or incident mentions:

- Sample Food Ordering App or Grubify.
- Azure Container Apps API/frontend incidents.
- HTTP 500, HTTP 5xx, elevated failure rate, slow endpoint, timeout, unhealthy revision, image pull, crash loop, memory pressure, restart, OOM, failed cart, menu, checkout, or frontend/API CORS.
- The `break-sample-food-app.sh` or `generate-sample-food-app-traffic.sh` scripts.
- Sample app response plans or scheduled health checks.

## Non-Goals

- Do not use `NTANetAnalytics` as primary evidence for Azure Container Apps workload traffic. Azure Container Apps is not supported by VNet Flow Logs.
- Do not change Container Apps scale, image, revision, ingress, CORS, or Terraform configuration without Review-mode approval.
- Do not assume the app is instrumented beyond platform logs unless Application Insights data is present.
- Do not require GitHub access for infrastructure-only diagnosis.

## Application API Surface

The Grubify API (ASP.NET Core, container target port `8080`) exposes **only** these routes.
There is **no `/health` and no `/api/menu`**: both return HTTP 404 **by design**, which is not
an outage signal.

| Method | Route | Expected | Use |
| --- | --- | --- | --- |
| GET | `/WeatherForecast` | 200 | Fastest liveness check (used by every demo script). |
| GET | `/api/FoodItems` | 200 | Menu/catalog read; primary recovery signal. |
| GET | `/api/Restaurants` | 200 | Secondary domain read. |
| GET / POST | `/api/cart/{user}/items` | 200/201 | Cart read/write; `POST {"foodItemId":1,"quantity":1}` is the OOM fault path. |

The frontend is a separate Container App on port `80`; test its root `/`. The API container app
has no HTTP health probe (only a platform TCP probe on `8080`), so "liveness/readiness failing"
during a restart is the TCP probe cycling, not a missing `/health` route. Verify recovery by
curling `/WeatherForecast` and `/api/FoodItems` for HTTP 200 — never `/health` or `/api/menu`.

## Evidence Sources

| Source | Use |
| --- | --- |
| `ContainerAppHTTPLogs` | HTTP status codes, paths, duration, request IDs, revision and replica correlation. |
| `ContainerAppConsoleLogs_CL` | Application stdout/stderr, exceptions and custom log messages. |
| `ContainerAppSystemLogs_CL` | Revision provisioning, image pull, ingress and platform events. |
| Application Insights requests/failures/exceptions | End-to-end app telemetry when the app emits it. |
| Azure Monitor metrics | Replica count, requests, CPU, memory, restarts where available. |
| Terraform outputs | Resource names, app URLs, ACR, workspace and App Insights IDs. |
| Knowledge files | Architecture, fault model and incident report format. |

## Procedure

1. Identify incident scope: API vs frontend, time window, and symptom.
2. Confirm resource names from Terraform outputs or Azure Resource Graph:
   - `sample_food_api_container_app_name`.
   - `sample_food_frontend_container_app_name`.
   - `sample_food_application_insights_resource_id`.
   - `demo_lab_log_analytics_workspace_customer_id`.
3. Query HTTP logs for the incident window.
4. Query console and system logs around the highest-error or highest-latency timestamps.
5. Query Application Insights if available.
6. Check Container Apps revision health and active image.
7. Check recent deployment or image-update activity if failures align with a revision change.
8. Produce an incident report using the template in the knowledge base.
9. Recommend remediation in Review mode.

## Approved KQL Query Library

### Recent HTTP Errors

```kql
let AppName = "<api-container-app-name>";
ContainerAppHTTPLogs
| where TimeGenerated > ago(2h)
| where ContainerAppName == AppName
| where toint(StatusCode) >= 400
| project TimeGenerated, ContainerAppName, RevisionName, ReplicaName, Method, Path, StatusCode, ResponseCodeDetails, ResponseFlags, RequestDuration, RequestId
| order by TimeGenerated desc
```

### Top Failing Endpoints

```kql
let AppName = "<api-container-app-name>";
ContainerAppHTTPLogs
| where TimeGenerated > ago(24h)
| where ContainerAppName == AppName
| where toint(StatusCode) >= 400
| summarize Errors=count(), StatusCodes=make_set(StatusCode, 10), ExampleDetails=take_any(ResponseCodeDetails), P95DurationMs=percentile(RequestDuration, 95) by Method, Path
| order by Errors desc
```

### Latency By Endpoint

```kql
let AppName = "<api-container-app-name>";
ContainerAppHTTPLogs
| where TimeGenerated > ago(24h)
| where ContainerAppName == AppName
| summarize Requests=count(), P50=percentile(RequestDuration, 50), P95=percentile(RequestDuration, 95), P99=percentile(RequestDuration, 99) by Path
| order by P95 desc
```

### Console Logs Around Incident

```kql
let AppName = "<api-container-app-name>";
let IncidentTime = datetime(<incident-time-utc>);
ContainerAppConsoleLogs_CL
| where TimeGenerated between (IncidentTime - 15m .. IncidentTime + 15m)
| where ContainerAppName_s == AppName
| project TimeGenerated, RevisionName_s, ContainerName_s, Log_s
| order by TimeGenerated desc
```

### Revision Provisioning Or Image Pull Issues

```kql
let AppName = "<api-container-app-name>";
ContainerAppSystemLogs_CL
| where TimeGenerated > ago(24h)
| where ContainerAppName_s == AppName
| where Log_s has_any ("ErrImagePull", "ContainerCrashing", "Error provisioning", "Revision", "failed", "timeout")
| project TimeGenerated, EnvironmentName_s, ContainerAppName_s, RevisionName_s, Log_s
| order by TimeGenerated desc
```

## Interpretation Rules

- A 404 on `/health` or `/api/menu` is **expected** — those routes do not exist in this app. Never treat it as "app down"; confirm recovery with `/WeatherForecast` and `/api/FoodItems` (expect HTTP 200).
- `ResponseCodeDetails == "via_upstream"` usually means the application container returned the error.
- `route_not_found` or `NR` points toward ingress/routing configuration.
- High `RequestDuration` plus `UpstreamRequestAttemptCount > 1` suggests retries contributing to latency.
- Errors immediately after a new revision indicate deployment, image, configuration, or startup regression until proven otherwise.
- System log image-pull failures usually point to ACR, managed identity, `AcrPull`, image tag, or registry server mismatch.
- Console logs are application evidence; HTTP logs are ingress evidence. Prefer correlation by time, replica, revision, and request ID.

## Output Format

```text
Incident interpreted as: <symptom and component>
Time range: <range>
Resources checked:
- API: <name>
- Frontend: <name>
- Workspace/App Insights: <ids>
Evidence:
- <query/result 1>
- <query/result 2>
Root cause hypothesis: <hypothesis>
Confidence: High | Medium | Low
Recommended remediation: <Review-mode action>
Validation after remediation: <checks>
References:
- docs/demo-lab/sample-food-ordering-app-lab.md
- docs/demo-lab/kql-catalog.md
- https://learn.microsoft.com/en-us/azure/container-apps/log-monitoring
```

## Official Sources

- Azure Container Apps logs: https://learn.microsoft.com/en-us/azure/container-apps/log-monitoring
- Azure Container Apps networking: https://learn.microsoft.com/en-us/azure/container-apps/networking
- Azure Monitor alert types: https://learn.microsoft.com/en-us/azure/azure-monitor/alerts/alerts-types
- Azure SRE Agent skills: https://learn.microsoft.com/en-us/azure/sre-agent/skills
- Azure SRE Agent custom agents: https://learn.microsoft.com/en-us/azure/sre-agent/sub-agents
- VNet Flow Logs unsupported services: https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview#incompatible-services
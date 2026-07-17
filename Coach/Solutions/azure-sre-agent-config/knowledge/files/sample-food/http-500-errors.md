# Sample Food Ordering App HTTP 5xx Investigation Runbook

Use this runbook when the Sample Food Ordering App API or frontend reports HTTP 500, HTTP 5xx spikes, failed checkout/cart/menu operations, or abnormal latency.

## Triage Questions

1. Which component is failing: API or frontend?
2. What is the incident time window?
3. Which paths are failing: `/api/FoodItems`, `/api/Restaurants`, `/api/cart/{user}/items`, `/WeatherForecast`, the frontend root, or another route? (See "Application API Surface" below — this app has no `/health` or `/api/menu`.)
4. Did a Container App revision, image, CORS setting, or scale change happen near the incident?
5. Is the error application-generated (`via_upstream`) or platform/ingress-generated (`route_not_found`, `UH`, `UT`, `NR`)?

## Application API Surface (use these exact routes to test)

The Grubify API is an ASP.NET Core app listening on container target port `8080`. It exposes
**only** the routes below. There is **no `/health` and no `/api/menu`** endpoint: a request to
either returns HTTP 404 **by design**, which is **not** an outage signal.

| Method | Route | Expected | Purpose / use in triage |
| --- | --- | --- | --- |
| GET | `/WeatherForecast` | 200 | Lightweight liveness check used by all demo scripts; fastest "is the API serving?" signal. |
| GET | `/api/FoodItems` | 200 | Menu/catalog domain read; primary post-remediation health signal. |
| GET | `/api/Restaurants` | 200 | Secondary domain read. |
| GET | `/api/cart/{user}/items` | 200 | Cart read (e.g. `/api/cart/demo-user/items`). |
| POST | `/api/cart/{user}/items` | 200/201 | Cart write — **the OOM fault path**. Body: `{"foodItemId":1,"quantity":1}`. |

The frontend is a **separate** Container App on port `80`; test its root `/`. The API container
app has **no HTTP health probe** (only the platform TCP probe on port 8080), so
"liveness/readiness failing" during a restart is the TCP probe cycling, not a missing `/health`
route. To confirm recovery after remediation, curl `/WeatherForecast` and `/api/FoodItems` and
expect HTTP 200 — **never** use `/health` or `/api/menu` to judge recovery.

## KQL Queries (run these first)

Resolve the API Container App name once, then run the queries (substitute it for `<api>` if you query the workspace directly):

```bash
api="$(terraform -chdir=infra output -json sample_food_resource_names | jq -r '.api_container_app')"
```

Recent HTTP 5xx by path and revision:

```kql
ContainerAppHTTPLogs
| where TimeGenerated > ago(15m)
| where ContainerAppName == "<api>"
| where toint(StatusCode) >= 500
| summarize Errors=count() by Path, StatusCode, RevisionName=tostring(RevisionName)
| order by Errors desc
```

Top failing endpoints with error ratio:

```kql
ContainerAppHTTPLogs
| where TimeGenerated > ago(30m)
| where ContainerAppName == "<api>"
| summarize Total=count(), Errors=countif(toint(StatusCode) >= 500) by Path
| extend ErrorRatio=round(100.0 * Errors / Total, 1)
| where Errors > 0
| order by ErrorRatio desc
```

Console exceptions around the incident:

```kql
ContainerAppConsoleLogs_CL
| where TimeGenerated > ago(15m)
| where ContainerAppName_s == "<api>"
| where Log_s has_any ("Exception", "error", "Error", "500", "Traceback")
| project TimeGenerated, RevisionName_s, Log_s
| order by TimeGenerated desc
| take 100
```

Revision / image-pull / crash events:

```kql
ContainerAppSystemLogs_CL
| where TimeGenerated > ago(30m)
| where ContainerAppName_s == "<api>"
| where Reason_s has_any ("ProvisioningError", "ContainerCrashing", "ImagePullBackOff", "Unhealthy")
| project TimeGenerated, RevisionName_s, Reason_s, Log_s
| order by TimeGenerated desc
```

## Baseline expectations (demo lab)

- Healthy steady state: API 5xx ratio is ~0% on `/WeatherForecast`, `/api/FoodItems`, and `/api/Restaurants`; non-zero 5xx appears only after `./infra/scripts/break-sample-food-app.sh` (the cart POST flood). Do not over-investigate benign latency. A 404 on `/health` or `/api/menu` is expected (those routes do not exist) and must not be read as an outage.
- Container Apps log ingestion is near real time (seconds to ~1-2 minutes). If `ContainerAppHTTPLogs` is empty for a known-bad window, suspect the diagnostic setting or workspace, not the app.
- Do not use `NTANetAnalytics` for this workload: Azure Container Apps traffic is not captured by VNet Flow Logs (https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview).

## Evidence Checklist

- Query `ContainerAppHTTPLogs` for errors and latency.
- Query `ContainerAppConsoleLogs_CL` around failing timestamps.
- Query `ContainerAppSystemLogs_CL` for revision provisioning, image pull, or container crashing events.
- Check active revision and image with Azure CLI.
- Query Application Insights requests, failures, exceptions, and dependencies when data exists.
- Compare findings to recent image deployment from `Student/Resources/scenarios/scripts/deploy-sample-food-images.sh`.

## Common Root Causes

| Symptom | Likely cause | Evidence |
| --- | --- | --- |
| 5xx on `/api/cart/demo-user/items` after load script | Memory pressure or app bug in cart flow | HTTP logs on cart path, console exceptions, elevated duration/errors |
| 404 or `route_not_found` | Ingress path or frontend API base URL mismatch | HTTP log `ResponseCodeDetails`, frontend env var |
| Failed revision | Image pull, startup, or environment variable issue | `ContainerAppSystemLogs_CL`, revision status |
| Frontend loads but API fails | CORS/API URL mismatch or API unhealthy | Browser symptom, API health status, CORS env var |
| No logs | Diagnostic setting not active or ingestion delay | Diagnostic setting state, system logs, workspace query |

## Autonomous Remediation

This lab runs the agent in maximum-autonomy mode (no human approval gate), so apply the smallest reversible fix directly, then verify. Resolve names from Terraform outputs first:

```bash
rg="$(terraform -chdir=infra output -raw sample_food_resource_group_name)"
api="$(terraform -chdir=infra output -json sample_food_resource_names | jq -r '.api_container_app')"
rev="$(az containerapp revision list -g "$rg" -n "$api" --query "[?properties.active].name | [0]" -o tsv)"
```

| Confirmed cause | Remediation command | Verify |
| --- | --- | --- |
| Transient crash / stuck revision | `az containerapp revision restart -g "$rg" -n "$api" --revision "$rev"` | `/WeatherForecast` and `/api/FoodItems` return 200; 5xx ratio drops |
| Bad image / regression | `./infra/scripts/deploy-sample-food-images.sh --skip-build` (redeploy known-good) | revision Healthy; `/api/FoodItems` returns 200 |
| CPU / memory pressure under load | `az containerapp update -g "$rg" -n "$api" --max-replicas 5` | error rate declines as replicas scale out |
| CORS mismatch | `az containerapp update -g "$rg" -n "$api" --set-env-vars AllowedOrigins__0=<frontend-url>` | frontend calls the API successfully |
| Frontend API base URL wrong | redeploy frontend with `REACT_APP_API_BASE_URL=<api-url>/api` | frontend root loads and calls succeed |

## Validation After Remediation

1. `/WeatherForecast` returns HTTP 200 (lightweight liveness signal).
2. `/api/FoodItems` returns HTTP 200 (domain health signal); `/api/Restaurants` also returns 200.
3. `ContainerAppHTTPLogs` shows error rate returning to expected level.
4. Active revision is healthy.
5. Frontend can call the API successfully.

Official source for Container Apps logs: https://learn.microsoft.com/en-us/azure/container-apps/log-monitoring


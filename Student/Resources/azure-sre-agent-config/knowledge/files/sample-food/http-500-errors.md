# Sample Food Ordering App HTTP 5xx Investigation Runbook

Use this runbook when the Sample Food Ordering App API or frontend reports HTTP 500, HTTP 5xx spikes, failed checkout/cart/menu operations, or abnormal latency.

## Triage Questions

1. Which component is failing: API or frontend?
2. What is the incident time window?
3. Which paths are failing: `/api/FoodItems`, `/api/Restaurants`, `/api/cart/{user}/items`, `/WeatherForecast`, the frontend root, or another route? (See "Application API Surface" below — this app has no `/health` or `/api/menu`.)
4. Did a Container App revision, image, CORS setting, or scale change happen near the incident?
5. Is the error application-generated (`via_upstream`) or platform/ingress-generated (`route_not_found`, `UH`, `UT`, `NR`)?

## Application API Surface (use these exact routes to test)

The authoritative route list lives in `sample-food/sample-food-architecture.md` and is not repeated
here, so that a route change has one place to be corrected rather than three.

What matters for triage is the trap, not the list: the API has **no `/health` and no `/api/menu`**
endpoint. A request to either returns HTTP 404 **by design**, which is **not** an outage signal.
The API container app has **no HTTP health probe**, only a platform TCP probe on port `8080`, so
"liveness or readiness failing" during a restart is the TCP probe cycling, not a missing `/health`
route. The frontend is a **separate** Container App on port `80`; test its root `/`.

To confirm recovery after remediation, curl `/WeatherForecast` and `/api/FoodItems` and expect
HTTP 200. **Never** use `/health` or `/api/menu` to judge recovery.

## Executable query source

Use the approved KQL query library in the `sample-food-container-app-incident-analysis` skill.
That skill is the single executable source for HTTP error ratios, revision correlation, console
exceptions, and Container Apps system events. This knowledge file supplies workload context,
expected routes, root-cause patterns, and recovery criteria; it intentionally does not duplicate
the queries.

## Baseline expectations (demo lab)

- Healthy steady state: the API 5xx ratio is approximately 0% on `/WeatherForecast`, `/api/FoodItems`, and `/api/Restaurants`. Any sustained non-zero 5xx ratio on those routes is a real signal and must be investigated from telemetry. Do not over-investigate benign latency. A 404 on `/health` or `/api/menu` is expected because those routes do not exist, and must not be read as an outage.
- Container Apps log ingestion is near real time (seconds to ~1-2 minutes). If `ContainerAppHTTPLogs` is empty for a known-bad window, suspect the diagnostic setting or workspace, not the app.
- Do not use `NTANetAnalytics` for this workload: Azure Container Apps traffic is not captured by VNet Flow Logs (https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview).

## Evidence Checklist

- Query `ContainerAppHTTPLogs` for errors and latency.
- Query `ContainerAppConsoleLogs_CL` around failing timestamps.
- Query `ContainerAppSystemLogs_CL` for revision provisioning, image pull, or container crashing events.
- Check active revision and image with Azure CLI.
- Query Application Insights requests, failures, exceptions, and dependencies when data exists.
- Compare findings to the most recent image deployment, using the active revision's image tag and its creation time from the Container Apps revision list.

## Common Root Causes

| Symptom | Likely cause | Evidence |
| --- | --- | --- |
| 5xx or restart during sustained cart writes | Application memory growth, concurrency defect, downstream failure, or another source-level mechanism | HTTP error timing, memory/restart telemetry, console exceptions, dependency evidence, and repository inspection |
| 404 or `route_not_found` | Ingress path or frontend API base URL mismatch | HTTP log `ResponseCodeDetails`, frontend env var |
| Failed revision | Image pull, startup, or environment variable issue | `ContainerAppSystemLogs_CL`, revision status |
| Frontend loads but API fails | CORS/API URL mismatch or API unhealthy | Browser symptom, API health status, CORS env var |
| No logs | Diagnostic setting not active or ingestion delay | Diagnostic setting state, system logs, workspace query |

## Permanent Source Remediation and Human Approval Boundary

An operational restart can restore availability without removing a source-level defect. When
telemetry and repository inspection prove a causal code path, the permanent remediation is owned
by the `source-fix-delivery` skill, which defines the engineering standard the change must meet,
the failing-then-passing regression evidence, and the issue plus pull-request workflow. Do not
restate that procedure here: load the skill and execute it.

Two boundaries always hold and are repeated here because they are non-negotiable:

- The pull request is the human approval boundary. The agent never merges and never deploys the
  proposed source change.
- A report must distinguish an action proposed from an action executed and from an outcome
  verified.

The post-fix acceptance criterion is behavioral: replay the original failing workload and prove
that every cart write succeeds while `/WeatherForecast`, `/api/FoodItems`, and `/api/Restaurants`
remain HTTP 200. The replay itself is run by the operator, not by the agent.

## Where the remediation procedure lives

This document is reference material: it tells you what to look at and how to read it. The ordered
remediation steps, the Azure CLI commands for each confirmed cause, and the post-remediation
validation sequence belong to the `sample-food-container-app-incident-analysis` skill, which is the
construct whose purpose is an executable procedure. Load that skill to act; read this document to
interpret.

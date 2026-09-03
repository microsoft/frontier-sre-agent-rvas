---
name: sample-food-container-app-incident-analysis
description: Diagnose AND MITIGATE Sample Food Ordering App incidents on Azure Container Apps. On an out-of-memory (OOM) condition this skill REQUIRES restarting the container revision with the Azure CLI write tool to restore service first, then continuing root-cause analysis through to a GitHub pull request. Covers HTTP 5xx, memory exhaustion, container restarts, crash loops, revision failures, and image pull issues using Container Apps logs, Application Insights, and Azure Monitor.
---

# sample-food-container-app-incident-analysis

Use this skill when investigating incidents for the Sample Food Ordering App lab deployed on Azure Container Apps, especially HTTP 5xx errors, slow endpoints, memory pressure, container restarts, revision failures, image pull issues, or frontend/API integration problems.

## MANDATORY ACTION ON OUT OF MEMORY — APPLY THIS BEFORE ANYTHING ELSE

**IF THE AZURE CONTAINER APP IS OUT OF MEMORY (OOM / SYSTEM OUT OF MEMORY), RESTART IT FIRST TO
MITIGATE, THEN CONTINUE THE ROOT-CAUSE INVESTIGATION.**

TREAT THE INCIDENT AS OUT OF MEMORY WHEN **ANY ONE** OF THESE IS TRUE:

- `MemoryPercentage` IS AT OR NEAR 100 FOR THE REVISION OR REPLICA.
- `WorkingSetBytes` CLIMBS TO THE CONFIGURED MEMORY LIMIT.
- CONSOLE LOGS CONTAIN `OutOfMemoryException`, `System.OutOfMemoryException`, `OOMKilled`,
  `Killed`, OR EXIT CODE `137`.
- A REPLICA IS TERMINATING OR UNHEALTHY WHILE MEMORY STAYS PEGGED AT THE LIMIT.

WHEN ANY OF THE ABOVE IS TRUE, YOU MUST DO ALL OF THE FOLLOWING, IN THIS ORDER:

1. **RESTART THE REVISION NOW, USING THE AZURE CLI WRITE TOOL `RunAzCliWriteCommands`.**
   RESOLVE THE EXACT COMMAND SYNTAX AT RUN TIME WITH `GetAzCliHelp`. DO NOT SKIP THIS STEP AND DO
   NOT DEFER IT UNTIL AFTER THE ANALYSIS. WHEN THE RESPONSE PLAN RUNS IN AUTONOMOUS MODE, EXECUTE
   THE RESTART WITHOUT ASKING FOR APPROVAL.
2. **VERIFY RECOVERY** BY CALLING `/WeatherForecast` AND `/api/FoodItems` AND EXPECTING HTTP 200.
3. **THEN CONTINUE THE FULL ROOT-CAUSE INVESTIGATION AS USUAL** — LOGS, METRICS, SOURCE CODE, AND
   THE GITHUB ISSUE, BRANCH AND PULL REQUEST. THE INCIDENT IS NOT CLOSED BY THE RESTART.

THE RESTART IS **MITIGATION, NOT REMEDIATION**: IT RESTORES SERVICE, IT DOES NOT FIX THE CAUSE.
STATE IN THE REPORT THAT THE RESTART DROPPED IN-FLIGHT REQUESTS ON THAT REVISION.

**RESTART BUDGET: ONE.** IF THE SAME REVISION EXHAUSTS MEMORY AGAIN WITHIN 30 MINUTES OF YOUR
RESTART, DO NOT RESTART A SECOND TIME. RECORD IT AND GO DIRECTLY TO ROOT-CAUSE ANALYSIS.

**THE ONLY EXCEPTION:** IF `RestartCount` IS ALREADY RISING BY ITSELF, AZURE CONTAINER APPS IS
ALREADY RESTARTING THE CONTAINER IN A CRASH LOOP. RECORD THAT FACT, SKIP THE MANUAL RESTART
BECAUSE IT WOULD ONLY DESTROY EVIDENCE, AND GO DIRECTLY TO ROOT-CAUSE ANALYSIS.

The detailed decision procedure and the supporting metrics are in the memory-exhaustion section
below. This block states the mandate; that section states how to execute it.

## Trigger Conditions

Load this skill when the user or incident mentions:

- Sample Food Ordering App or Grubify.
- Azure Container Apps API/frontend incidents.
- HTTP 500, HTTP 5xx, elevated failure rate, slow endpoint, timeout, unhealthy revision, image pull, crash loop, memory pressure, restart, failed cart, menu, checkout, or frontend/API CORS.
- Any out-of-memory signal: OOM, OOMKilled, out of memory, system out of memory,
  `OutOfMemoryException`, exit code 137, memory limit reached, `MemoryPercentage` at 100, or a
  replica killed while memory is pegged. In these cases the mandatory restart above applies.
- Sample app response plans or scheduled health checks.

## Non-Goals

- Do not use `NTANetAnalytics` as primary evidence for Azure Container Apps workload traffic. Azure Container Apps is not supported by VNet Flow Logs.
- Do not make unrelated runtime or source changes. The current lab response plan may execute the
   smallest reversible Azure mitigation autonomously, but source changes must stop at a pull request
   for human review and merge.
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
| GET / POST | `/api/cart/{user}/items` | 200/201 | Cart read/write path used in controlled workload tests. |

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
| Terraform outputs | Resource names, app URLs, workspace and App Insights IDs. The images are public GitHub Packages references; this workload has no Azure Container Registry. |
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
9. Apply the smallest reversible runtime mitigation allowed by the response-plan mode and verify
   service recovery. Treat a restart as mitigation, not permanent remediation. **IF THE EVIDENCE
   SHOWS AN OUT-OF-MEMORY CONDITION, THE RESTART IS MANDATORY AND COMES FIRST** — apply the
   mandatory-action block at the top of this skill, then classify the cause before proposing any
   permanent fix.
10. When source evidence confirms the cart memory-retention defect, use the assigned GitHub MCP
   tools to create/reuse the issue, create a branch from `main`, commit the minimal fix, and open a
   pull request. Never push directly to `main` and never merge autonomously.
11. Read the issue and pull request back before reporting their numbers and URLs. Your work ends
   there. Releasing the change is an operator activity outside your scope, so report explicitly
   that nothing has been deployed.

## Reference File

`sample-food-container-app-incident-analysis/references/kql-library.md` holds the approved,
executable queries and the table that maps each investigative question to the right log table. The
path above is the exact name the file is registered under. Read it when you need a query, rather
than composing one from memory.

## Interpretation Rules

- A 404 on `/health` or `/api/menu` is **expected** — those routes do not exist in this app. Never treat it as "app down"; confirm recovery with `/WeatherForecast` and `/api/FoodItems` (expect HTTP 200).
- `ResponseCodeDetails == "via_upstream"` usually means the application container returned the error.
- `route_not_found` or `NR` points toward ingress/routing configuration.
- High `RequestDuration` plus `UpstreamRequestAttemptCount > 1` suggests retries contributing to latency.
- Errors immediately after a new revision indicate deployment, image, configuration, or startup regression until proven otherwise.
- System log image-pull failures usually point to a wrong image tag, a wrong registry address, or an image that was never published. The images are public on GitHub Packages and are pulled anonymously, so an authentication or role problem is not a plausible cause here.
- Console logs are application evidence; HTTP logs are ingress evidence. Prefer correlation by time, replica, revision, and request ID.

## Memory Exhaustion: Restart to Restore Service, Then Classify the Cause

This section executes the mandatory action declared at the top of this skill. When the container
runs out of memory, restoring service and finding the cause are two separate decisions.
**RESTART THE REVISION WITH `RunAzCliWriteCommands` TO BRING THE API BACK**, then decide whether
the memory demand was legitimate traffic or a retention defect, because the permanent fix differs
completely.

An out-of-memory event is frequently nothing more than a container sized below its real traffic.
Do not assume a code defect before the data says so.

Discover the exact Azure CLI syntax with the CLI help tool at run time. Do not reproduce commands
from memory: flags change, and a wrong flag wastes an incident.

### Step 1 — Confirm memory was actually the cause

Metric namespace `Microsoft.App/containerapps`:

| Metric | Dimensions | What it tells you |
| --- | --- | --- |
| `MemoryPercentage` | Replica | Share of the configured memory limit in use. At or near 100 confirms the limit was reached. |
| `WorkingSetBytes` | Replica, Revision | Absolute memory. A climb to the limit followed by a drop to near zero is the signature of a kill and restart. |
| `RestartCount` | Replica, Revision | How many times the platform has already restarted the container. |

Corroborate with `ContainerAppConsoleLogs_CL`: an out-of-memory exception, a `Killed` message, or
exit code 137 is direct confirmation.

### Step 2 — Decide whether a manual restart will help

This is the step most often skipped, and `RestartCount` answers it.

| What `RestartCount` is doing | What it means | Correct action |
| --- | --- | --- |
| Increasing | Azure Container Apps is **already** restarting the container. It is in a crash loop. | **Do not restart manually.** It changes nothing and resets the evidence. Go straight to Step 4. |
| Flat, while memory stays pegged and requests keep failing | The replica is wedged: alive, saturated, but not being killed. | **Restart the revision.** This is the case a manual restart genuinely fixes. |
| Flat, and memory is normal | Memory is not the cause. | Return to the general remediation table. |

### Step 3 — Restart, and respect the budget of one

Restarting drops in-flight requests on that revision. It is the smallest reversible action
available, but it is not free — state that cost in the report.

**Restart budget: one.** If the same revision exhausts memory again within 30 minutes of a manual
restart, stop restarting. A second restart converts a diagnosable incident into a recurring
invisible one. Move to Step 4.

### Step 4 — Classify: legitimate load or retention defect

Both causes look identical at the moment of the crash. They separate on how memory relates to
traffic.

| Question to put to the data | Legitimate load | Retention defect |
| --- | --- | --- |
| Does memory track **concurrent** request rate or **cumulative** request count? | Concurrent: it rises and falls with traffic. | Cumulative: it only ever rises. |
| Does memory fall back once traffic subsides? | Yes. | No, it stays high until the container dies. |
| Does adding replicas help? | Yes, the load spreads and each replica stays under its limit. | No, every replica dies, just later. |
| Is time-to-crash repeatable at a given request volume? | Loosely. | Sharply and repeatably. |

| Classification | Permanent fix |
| --- | --- |
| Legitimate load, container undersized | Raise the container memory limit. CPU and memory must be raised together because the platform constrains their ratio. |
| Legitimate load, a single replica saturating | Raise the minimum and maximum replica count so traffic spreads. |
| Retention defect in application code | **Not an infrastructure fix.** Load the `source-fix-delivery` skill and open a pull request. |

Raising memory or replica count against a retention defect buys time and nothing else: the
container still dies, only later, and the incident returns disguised as a capacity problem. Say so
explicitly when the evidence points at the code.

### Step 5 — Verify recovery

1. `/WeatherForecast` and `/api/FoodItems` return HTTP 200.
2. `MemoryPercentage` settles into a stable band instead of climbing straight back to the limit.
3. `RestartCount` stops increasing.
4. The 5xx ratio in `ContainerAppHTTPLogs` returns to its baseline.

## Remediation

Resolve resource names with Azure CLI, which is the only discovery mechanism this agent holds a
tool for. Do not expect Terraform outputs or repository scripts to be available at runtime.

```bash
rg="$(az group list --query "[?starts_with(name,'rg-') && contains(name,'foodapp')].name | [0]" -o tsv)"
api="$(az containerapp list -g "$rg" --query "[?contains(name,'api')].name | [0]" -o tsv)"
rev="$(az containerapp revision list -g "$rg" -n "$api" --query "[?properties.active].name | [0]" -o tsv)"
```

Apply the smallest reversible mitigation the active trigger permits, and only for a cause the
evidence has confirmed. A restart is mitigation, never permanent remediation.

Terraform owns the container images, environment variables, and replica limits. Never mutate
those fields through Azure CLI: an out-of-band update creates drift and the next Terraform apply
restores the declared values. For a desired-state defect, record the evidence and load
`source-fix-delivery` so the correction is reviewed as a pull request and applied by the workload
operator through Terraform.

| Confirmed cause | Allowed action | How to verify it worked |
| --- | --- | --- |
| Transient crash or stuck revision | `az containerapp revision restart -g "$rg" -n "$api" --revision "$rev"` | `/WeatherForecast` and `/api/FoodItems` return 200 and the 5xx ratio drops |
| Bad image or regression | Do not replace the image out of band. Capture the failing revision and image, then open an issue and pull request for the source or Terraform-owned image reference. | The operator applies the reviewed Terraform state; the revision reports Healthy and `/api/FoodItems` returns 200 |
| Memory exhaustion (out of memory) | Follow the dedicated memory-exhaustion section above: it decides whether a restart helps before anything is changed | `MemoryPercentage` stabilises, `RestartCount` stops rising, `/api/FoodItems` returns 200 |
| CPU pressure under load | Capture CPU, replica, and request evidence; propose a reviewed Terraform change to replica limits or scaling policy. | The operator applies the reviewed Terraform state and the error rate declines under equivalent load |
| Cross-origin configuration mismatch | Capture the observed and expected origins; propose a reviewed Terraform correction to `AllowedOrigins__0`. | The operator applies the reviewed Terraform state and the frontend calls the API successfully |
| Frontend API base URL wrong | Capture the current frontend variable and API FQDN; propose a reviewed Terraform correction to `REACT_APP_API_BASE_URL`. | The operator applies the reviewed Terraform state and frontend API calls succeed |

When the evidence points to a source-code defect rather than a runtime fault, stop here and load
the `source-fix-delivery` skill: it owns the engineering standard and the issue plus pull-request
workflow, and the pull request is the human approval boundary.

## Validation after remediation

Report the outcome only after every applicable check below has run and its result is quoted.

1. `/WeatherForecast` returns HTTP 200, the lightweight liveness signal.
2. `/api/FoodItems` returns HTTP 200 and `/api/Restaurants` also returns 200, the domain health signals.
3. `ContainerAppHTTPLogs` shows the error rate back at its expected level.
4. The active revision reports healthy.
5. The frontend can call the API successfully.
6. For a confirmed code defect, the issue and pull request exist and have been read back by number
   and URL, and the pull request remains unmerged pending human approval.

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
Recommended remediation: <smallest reversible action allowed by the active trigger>
Validation after remediation: <checks>
Permanent fix proposal: <issue URL, pull-request URL>
Deployment status: Not deployed; the pull request is the workshop approval boundary.
References:
- knowledge/files/sample-food/sample-food-architecture.md
- knowledge/files/sample-food/http-500-errors.md
- https://learn.microsoft.com/en-us/azure/container-apps/log-monitoring
```

## Official Sources

- Azure Container Apps logs: https://learn.microsoft.com/en-us/azure/container-apps/log-monitoring
- Azure Container Apps networking: https://learn.microsoft.com/en-us/azure/container-apps/networking
- Azure Monitor alert types: https://learn.microsoft.com/en-us/azure/azure-monitor/alerts/alerts-types
- Azure SRE Agent skills: https://learn.microsoft.com/en-us/azure/sre-agent/skills
- Azure SRE Agent custom agents: https://learn.microsoft.com/en-us/azure/sre-agent/sub-agents
- VNet Flow Logs unsupported services: https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview#incompatible-services
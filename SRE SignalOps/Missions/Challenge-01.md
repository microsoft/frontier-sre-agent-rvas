[< Deployment](../Deployment/README.md) — **[Home](./README.md)** — [Next Challenge >](./Challenge-02.md)

# Challenge 01 — Investigate and Recover a Grubify Memory Incident

> **Incident capability exercised in this challenge**: Azure Monitor Alerting · Azure SRE Agent Investigation · Evidence-Backed RCA · Verified Recovery

## Introduction

Grubify's cart API contains a deliberate memory-retention defect. Every `POST` to the cart endpoint retains a 10 MB buffer in a static collection. In this mission you will establish a healthy baseline, create a real Azure Monitor alert, inject the fault with visible PowerShell commands, inspect the resulting incident, validate the root cause against metrics and source, and recover the service.

This is a controlled lab fault. Run these commands only against your verified, isolated SignalOps deployment. Do not run them against a shared or production workload.

## Description

### Prerequisites

- PowerShell 7 and Azure CLI are installed and `az login` has completed.
- Either Bicep stages 00–02 or Terraform deployment and completion have passed their baseline checks. Bicep additionally requires Azure Developer CLI and `azd auth login`.
- The live `aca-app-incident-handler` and enabled `sample-food-http-errors` response plan are verified. Audit knowledge retrieval in Mission 02 before injection when knowledge was preloaded.
- You are authorized to create an alert and restart the Grubify API revision.

Run every command separately from the repository root. This mission intentionally does not use a PowerShell script: inspect each command and its result before continuing.

### Part 1 — Select and Verify the Lab Environment

Load `$Lab` using the matching deployment command in the [mission context instructions](./README.md), then resolve the actual resource names:

```powershell
$SUBSCRIPTION_ID = $Lab.AZURE_SUBSCRIPTION_ID
$WORKLOAD_RG = $Lab.AZURE_RESOURCE_GROUP
$AGENT_RG = $Lab.AGENT_RESOURCE_GROUP
$APP_NAME = $Lab.API_APP_NAME
$ALERT_NAME = "alert-signalops-grubify-http-5xx"
$AGENT = az rest --method GET --url "https://management.azure.com$($Lab.SRE_AGENT_ID)?api-version=2026-01-01" | ConvertFrom-Json
$AGENT_URL = $AGENT.properties.agentEndpoint

az account set --subscription $SUBSCRIPTION_ID
az account show --query "{subscription:id,tenant:tenantId,name:name}" -o table
```

Discover the current API URL, resource ID, image, revision, and memory limit from Azure rather than assuming runtime values:

```powershell
$APP = az containerapp show --resource-group $WORKLOAD_RG --name $APP_NAME -o json | ConvertFrom-Json
$APP_BASE = "https://$($APP.properties.configuration.ingress.fqdn)"
$APP_ID = $APP.id
$REVISION = $APP.properties.latestReadyRevisionName

[pscustomobject]@{
	ApiUrl      = $APP_BASE
	ResourceId  = $APP_ID
	Revision    = $REVISION
	Image       = $APP.properties.template.containers[0].image
	MemoryLimit = $APP.properties.template.containers[0].resources.memory
} | Format-List
```

Stop if the subscription, resource group, app name, or URL is not the isolated SignalOps environment. Also stop if deployment completion did not prove that `sample-food-http-errors` is enabled for `Sev0` through `Sev4`, matches `grubify`, routes to `aca-app-incident-handler`, and uses `Review` mode.

### Part 2 — Record a Healthy Baseline

Check the two normal read endpoints separately. Each command displays only the HTTP status so the customer can see the baseline clearly:

```powershell
curl.exe -s -o NUL -w "Food items HTTP Status: %{http_code}`n" "$APP_BASE/api/fooditems"
```

```powershell
curl.exe -s -o NUL -w "Restaurants HTTP Status: %{http_code}`n" "$APP_BASE/api/restaurants"
```

Record the last 15 minutes of memory and restart metrics:

```powershell
$BASELINE_START = (Get-Date).ToUniversalTime().AddMinutes(-15).ToString("yyyy-MM-ddTHH:mm:ssZ")

az monitor metrics list --resource $APP_ID --metric WorkingSetBytes --interval PT1M --aggregation Maximum --start-time $BASELINE_START --query "value[0].timeseries[].data[].{time:timeStamp,maxBytes:maximum}" -o table

az monitor metrics list --resource $APP_ID --metric RestartCount --interval PT1M --aggregation Maximum --start-time $BASELINE_START --query "value[0].timeseries[].data[].{time:timeStamp,restarts:maximum}" -o table
```

Expected baseline: health succeeds, the restaurant request returns `200`, memory is below the 1 GiB container limit, and recent restart values are zero. Empty newest metric buckets are normal because Azure Monitor data arrives after a short delay.

### Part 3 — Create the Incident Signal

Create a severity 2 metric alert when any 5xx response is recorded during a one-minute window:

```powershell
az monitor metrics alert create `
	--resource-group $WORKLOAD_RG `
	--name $ALERT_NAME `
	--scopes $APP_ID `
	--condition "total Requests > 0 where statusCodeCategory includes 5xx" `
	--window-size 1m `
	--evaluation-frequency 1m `
	--severity 2 `
	--description "SignalOps lab: Grubify API returned one or more 5xx responses. Investigate memory, restarts, revisions, and cart traffic."
```

Verify the exact scope, dimension, threshold, and enabled state:

```powershell
az monitor metrics alert show --resource-group $WORKLOAD_RG --name $ALERT_NAME --query "{enabled:enabled,severity:severity,scopes:scopes,criteria:criteria.allOf[0]}" -o json
```

The alert has no action group because the enabled Deployment stage 02 response plan receives matching Azure Monitor alerts. This severity 2 rule matches the plan's `Sev0` through `Sev4` priorities and `grubify` title filter. The one-minute evaluation frequency is the shortest timer configured by this lab, but ingestion and agent startup remain asynchronous. The alert rule itself must fire before agent intake can be evaluated.

### Part 4 — Inject the Memory Fault

Keep using the same terminal so `$APP_BASE` retains the verified deployment URL. The command below sends **one** cart request. The API accepts the cart item and deliberately retains approximately 10 MB of request data in memory.

```powershell
curl.exe -i -X POST "$APP_BASE/api/cart/demo-user/items" -H "Content-Type: application/json" -d '{"foodItemId":1,"quantity":1}'
```

Use the terminal's **Up Arrow**, then **Enter**, to run that same request repeatedly. Each execution is visible and understandable: one request adds one item and retains another 10 MB buffer. Pause briefly between requests. Stop immediately when a `5xx`, timeout, connection error, or unhealthy API appears, and never exceed 200 requests.

Do not continue merely to force a visible 5xx. The container can restart quickly enough that the client sees a connection error while Azure records an ingress-side 5xx response. Move to evidence collection first.

### Part 5 — Observe the Signal and Incident

Check service state immediately:

```powershell
try { (Invoke-WebRequest "$APP_BASE/health" -TimeoutSec 10 -SkipHttpErrorCheck).StatusCode } catch { $_.Exception.Message }
try { (Invoke-WebRequest "$APP_BASE/api/restaurants" -TimeoutSec 10 -SkipHttpErrorCheck).StatusCode } catch { $_.Exception.Message }

az containerapp revision list --resource-group $WORKLOAD_RG --name $APP_NAME --query "[].{revision:name,active:properties.active,replicas:properties.replicas,health:properties.healthState,created:properties.createdTime}" -o table
```

Allow 2–5 minutes for metric ingestion and alert evaluation, then inspect 5xx requests, memory, and restarts over the incident window:

```powershell
$INCIDENT_START = (Get-Date).ToUniversalTime().AddMinutes(-30).ToString("yyyy-MM-ddTHH:mm:ssZ")

az monitor metrics list --resource $APP_ID --metric Requests --filter "statusCodeCategory eq '5xx'" --interval PT1M --aggregation Total --start-time $INCIDENT_START --query "value[0].timeseries[].data[].{time:timeStamp,total:total}" -o table

az monitor metrics list --resource $APP_ID --metric WorkingSetBytes --interval PT1M --aggregation Maximum --start-time $INCIDENT_START --query "value[0].timeseries[].data[].{time:timeStamp,maxBytes:maximum}" -o table

az monitor metrics list --resource $APP_ID --metric RestartCount --interval PT1M --aggregation Maximum --start-time $INCIDENT_START --query "value[0].timeseries[].data[].{time:timeStamp,restarts:maximum}" -o table
```

Inspect the Azure Monitor alert instance directly:

```powershell
$ALERTS_URL = "https://management.azure.com/subscriptions/$SUBSCRIPTION_ID/providers/Microsoft.AlertsManagement/alerts?api-version=2019-03-01"
$ALERTS = (az rest --method get --url $ALERTS_URL -o json | ConvertFrom-Json).value

$ALERTS |
	Where-Object { $_.properties.essentials.targetResource -eq $APP_ID } |
	Select-Object -First 10 `
		@{n="Alert";e={$_.properties.essentials.alertRule}},
		@{n="State";e={$_.properties.essentials.monitorCondition}},
		@{n="Severity";e={$_.properties.essentials.severity}},
		@{n="Fired";e={$_.properties.essentials.startDateTime}},
		@{n="Resource";e={$_.properties.essentials.targetResource}} |
	Format-Table -AutoSize
```

Open the SRE Agent URL and select **Incidents**:

```powershell
Start-Process 'https://sre.azure.com'
```

Find the incident associated with `$ALERT_NAME`. Ask the agent to investigate before suggesting a change:

> Investigate this Grubify API alert. Establish a UTC incident window; compare Requests, WorkingSetBytes, RestartCount, replicas, and revision state; identify affected and unaffected endpoints; provide competing hypotheses; and state the most likely cause with evidence, confidence, recovery action, and validation checks. Do not make a write change until I approve it.

Agent intake can lag behind the Azure Monitor alert. If no incident appears after the alert is `Fired`, capture that as an intake observation and continue the RCA with Azure evidence. Do not claim that the agent used source or knowledge that has not been connected and ingested.

### Part 6 — Validate the Root Cause

Inspect recent application logs for the retained-cache growth messages:

```powershell
az containerapp logs show --resource-group $WORKLOAD_RG --name $APP_NAME --tail 300 --format text
```

In a checkout, inspect `Student/Resources/grubify/GrubifyApi/Controllers/CartController.cs`; in an extracted deployment, inspect `infra/apps/grubify/GrubifyApi/Controllers/CartController.cs`. Focus on `RequestDataCache` and `AddItemToCart`. Correlate these facts:

| Evidence | What it supports |
|---|---|
| 5xx `Requests` alert | A server-side availability symptom occurred |
| Rising `WorkingSetBytes` | Memory pressure developed during the fault window |
| Nonzero `RestartCount` or replica replacement | The runtime recycled while under pressure |
| `Analytics cache` log growth | Cart POST traffic retained request buffers |
| Static `List<byte[]>` plus a new 10 MB buffer per POST | The line-level memory-retention defect |

A defensible RCA is: repeated cart POSTs allocate 10 MB buffers and retain them in the process-wide static `RequestDataCache` without cleanup. The working set rises toward the discovered container memory limit, causing degraded availability and potentially an out-of-memory restart. A 5xx alert by itself is not proof of this cause; the correlation and source inspection complete the causal chain.

### Part 7 — Recover and Verify

Stop all fault traffic before recovery. Refresh the active ready revision because the platform may have replaced it during the incident:

```powershell
$REVISION = az containerapp show --resource-group $WORKLOAD_RG --name $APP_NAME --query properties.latestReadyRevisionName -o tsv
az containerapp revision restart --resource-group $WORKLOAD_RG --name $APP_NAME --revision $REVISION
```

Wait about 15 seconds, then verify health and normal reads with separate commands:

```powershell
curl.exe -s -o NUL -w "Health HTTP Status: %{http_code}`n" "$APP_BASE/health"
```

```powershell
curl.exe -s -o NUL -w "Restaurants HTTP Status: %{http_code}`n" "$APP_BASE/api/restaurants"
```

```powershell
az containerapp revision list --resource-group $WORKLOAD_RG --name $APP_NAME --query "[].{revision:name,active:properties.active,replicas:properties.replicas,health:properties.healthState}" -o table
```

If either HTTP status is not `200`, wait another 15 seconds and run that individual check again. Do not inject more fault traffic.

Wait for another metric interval, then rerun the three metric queries from Part 5 with a new start time. Verify that new 5xx buckets stop appearing and memory returns near baseline. Azure Monitor may take several minutes to mark the alert `Resolved`.

Restarting the revision clears the process memory and restores service. It does **not** repair the source defect. Permanent remediation requires removing the unbounded static cache or implementing a bounded, expiring store, then rebuilding, redeploying, and regression testing the API.

## Success Criteria

- [ ] The isolated subscription, resource group, app, current revision, image, and 1 GiB memory limit are verified before fault injection
- [ ] Baseline health, memory, and restart evidence are recorded
- [ ] The 5xx metric alert exists with the correct resource scope and `statusCodeCategory` filter
- [ ] Each visible cart request runs only against the isolated Grubify API and stops at the first failure or the 200-request cap
- [ ] Alert, metric, log, revision, and agent-intake observations are timestamped
- [ ] The RCA separates symptom evidence from the source-proven cause
- [ ] The exact active revision is restarted only after fault traffic stops
- [ ] Health and normal reads recover, and no permanent fix is claimed
- [ ] **Explain to your coach** — which evidence establishes the symptom, which establishes the cause, and why restart is recovery rather than remediation?

## Optional Cleanup

Keep the alert for later missions if the coach wants to reuse it. Otherwise remove only the alert created here:

```powershell
az monitor metrics alert delete --resource-group $WORKLOAD_RG --name $ALERT_NAME
```

## Learning Resources

- [Automate incidents with Azure SRE Agent](https://learn.microsoft.com/en-us/azure/sre-agent/automate-incidents)
- [Azure Monitor metric alerts](https://learn.microsoft.com/en-us/azure/azure-monitor/alerts/alerts-metric-overview)
- [Supported Azure Container Apps metrics](https://learn.microsoft.com/en-us/azure/container-apps/metrics)
- [Azure Container Apps log monitoring](https://learn.microsoft.com/en-us/azure/container-apps/log-monitoring)

## Tips

- Treat the alert as a symptom, not a root cause.
- Use UTC timestamps and exact resource IDs when comparing evidence.
- Empty newest metric buckets usually indicate ingestion delay, not zero usage.
- If the alert fires but no SRE incident appears, record the intake gap instead of inventing an incident.
- Do not resume cart requests until the first incident's evidence has been reviewed.

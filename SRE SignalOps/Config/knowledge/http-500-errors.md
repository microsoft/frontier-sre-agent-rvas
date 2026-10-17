# Grubify HTTP 5xx runbook

## Triage Questions

1. Confirm the lab subscription, affected Container App and incident window.
2. Check `/health` and `/api/restaurants`; preserve status codes and timestamps.
3. Inspect Requests with the 5xx status-code dimension, WorkingSetBytes,
   RestartCount, ready revision, replica health and recent configuration changes.
4. Correlate request/dependency exceptions in Application Insights and container
   console/system logs. Report delayed or missing telemetry explicitly.
5. Investigate cart traffic and retained memory as a hypothesis, not a verdict.
   Compare growth against the configured memory limit and restart timeline.
## KQL Queries

Use the workload Application Insights resource from the deployment context:

```kusto
requests
| where timestamp > ago(30m)
| summarize Requests=count(), Failures=countif(success == false) by bin(timestamp, 1m), name
```

An empty result is a telemetry gap, not proof of health. Correlate the same UTC
window with Container Apps console logs and Requests/WorkingSetBytes/RestartCount.

## Validation After Remediation

1. Propose a scoped recovery and request approval before writes. Stop injection
   before restarting a revision. Never change shared or production resources.
2. Verify read endpoints, memory/restarts, healthy replicas and alert resolution.
   A successful management-plane command alone is not proof of recovery.

The Mission 01 alert name contains `grubify`; the enabled response plan accepts
Sev0 through Sev4 and routes to `aca-app-incident-handler` in Review mode.

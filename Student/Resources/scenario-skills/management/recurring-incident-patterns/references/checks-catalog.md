# Checks catalog

Recurring incident signals read from Azure Monitor alerts and the Activity Log resource health events, covered by Reader. The scan tool reads and aggregates these over the window.

For each repeat offender the tool records resource, type, resource signal count, separate alert and health counts, and a heuristic review priority. This is not an incident count.

## Read the fired alerts

```
az rest --method GET --url "https://management.azure.com/subscriptions/<id>/providers/Microsoft.AlertsManagement/alerts?api-version=2019-05-05-preview&timeRange=30d"
```

Each alert carries an essentials block with the affected resource (targetResource) and its type. The tool counts alerts per resource.

## Read the resource health degradations

```
az rest --method GET --url "https://management.azure.com/subscriptions/<id>/providers/microsoft.insights/eventtypes/management/values?api-version=2015-04-01&$filter=eventTimestamp ge '<iso start>'"
```

The tool keeps the ResourceHealth events where the current health status is Unavailable or Degraded, and counts them per resource.

## Aggregate and rank

- Resource signal count equals alert count plus health degradation count. Duplicate IDs within each source are removed; cross source correlation into incidents is not implemented.
- A resource at or above the repeat threshold (three by default) is a repeat offender.
- Review priority by signal count: ten or more High, five to nine Medium, three to four Low. This is not business impact severity.
- Offenders are grouped by resource type, so a pattern across many resources of one type is visible.

## Window and threshold

Thirty days is the default. Pass exactly 1, 7 or 30 days; other values are rejected rather than silently rounded. Both sources use the same explicit UTC start and end. Alerts use `customTimeRange=start/end` (not together with `timeRange`); Activity Log uses both `ge` and `le` timestamp filters. Each source stops at 40 pages, with outstanding continuation marked incomplete. The repeat threshold is three signals.

## Recommended focus

For each offender, the recommendation points at the durable fix rather than another alert: for a resource that keeps going Unavailable, review its redundancy and dependencies; for one that keeps firing the same alert, tune the workload or the threshold. The value is directing reliability investment to where it pays back.

## Sources

- [Alert instance retention](https://learn.microsoft.com/azure/azure-monitor/alerts/alerts-manage-alert-instances), verified: alerts have a 30 day retention period.
- [Activity Log](https://learn.microsoft.com/azure/azure-monitor/essentials/activity-log).
- [Alert custom time ranges](https://learn.microsoft.com/python/api/azure-mgmt-alertsmanagement/azure.mgmt.alertsmanagement.operations.alertsoperations), verified: ISO start/end, within 30 days, mutually exclusive with `timeRange`.

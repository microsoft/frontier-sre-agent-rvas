# Checks catalog

Alert hygiene signals from Azure Monitor. The scan tool reads the fired alert history and the alert rules; all reads are covered by Reader. Run any by hand with the RunAzCliReadCommands tool to verify.

For each finding the tool records counts, monitor resolved share, user closed share, measured rapid resolution share and current New share separately. Monitor condition and user state do not establish whether anyone took action.

## Read the fired alerts

```
az rest --method GET --url "https://management.azure.com/subscriptions/<id>/providers/Microsoft.AlertsManagement/alerts?api-version=2019-05-05-preview&timeRange=7d"
```

Each alert carries an essentials block with the rule (alertRule), severity (Sev0 to Sev4), monitorCondition (Fired or Resolved), and alertState (New, Acknowledged, or Closed). Group by rule and count.

## Read the disabled rules

```
az graph query -q "resources | where type in~ ('microsoft.insights/metricalerts','microsoft.insights/scheduledqueryrules') | extend enabled = tostring(properties.enabled) | where enabled =~ 'false' | project name, id, type, resourceGroup, subscriptionId" --first 1000
```

## Signals and thresholds

- Noisy (Medium, or High at twice the threshold): the rule fired at or above the noisy threshold over the window (20 by default). A single rule generating a large share of the pages is the first thing to tune. Fix: widen the threshold, add a dynamic threshold, lengthen the aggregation window, or split the scope.
- Rapid resolution candidate (Medium): Sev0 or Sev1, five or more alerts, and at least 80 percent have `monitorCondition=Resolved` and timezone aware `startDateTime` and `monitorConditionResolvedDateTime` proving a duration of 0 to 5 minutes. Missing timestamps cannot prove duration. Review impact and action history before changing severity.
- Alerts not acknowledged (Medium): at least half of the rule's alerts are still in the New state over five or more fires. Fix: confirm the rule routes to an action group a team watches, or retire it if it is not useful.
- Disabled rule (Medium): the rule exists but is turned off, so its signal is not watched. Fix: re enable it or delete it so the intent is clear.

Combine per rule: a rule that trips more than one signal appears once, listing them, at the highest severity among them.

Resolution duration coverage is reported separately. No valid duration means Not assessed, not 0 percent rapid resolution. Pending alerts and missing, invalid, timezone naive or reversed timestamps remain unknown. With partial coverage, rapid resolution is an explicit lower bound over all alerts, with assessed and unknown counts. The high severity rapid resolution signal requires at least 80 percent of all alerts to have proven rapid durations, not 80 percent of a selectively assessed subset.

## Window

Seven days is the default. Pass exactly 1, 7 or 30 days; unsupported windows are rejected. Alerts stop at 40 pages. An outstanding continuation or a query failure is incomplete, not evidence of no alerts.

## Sources

- [Alerts and state](https://learn.microsoft.com/azure/azure-monitor/alerts/alerts-overview#alerts-and-state), verified: user response is independent of monitor condition.

# Evidence collection and analysis

## Collection

### 1. Read complete alert instance window

Follow nextLink and obey Retry-After. Filter startDateTime locally and deduplicate IDs. Retain monitorCondition, monitorConditionResolvedDateTime, alertState and lastModifiedUserName separately.

```powershell
foreach ($SUB in $SUBS) {
 az rest --method get --url "https://management.azure.com/subscriptions/$SUB/providers/Microsoft.AlertsManagement/alerts?api-version=2019-03-01&customTimeRange=$START/$END" --output json
}
```

### 2. Read response and condition transition history

Run for each approved listed instance and retain condition changes, user state changes and processing rules. Compare with separately supplied authorized incident comments or acknowledgement exports using alert IDs. Do not claim the Azure history endpoint contains all external comments or human response actions.

```powershell
az rest --method get --url "https://management.azure.com$ALERT_ID/history?api-version=2019-03-01" --output json
```

## Analysis rules

1. Count unique instances per rule and flag more than 50 in 30 days, keeping recurrence distinct from one long running condition.
2. For automatically resolved instances calculate resolved time minus firing time using monitor condition timestamps. Report the proportion under five minutes and flag over 80 percent, with resolved and total instance counts shown.
3. Use alertState New, Acknowledged and Closed only as workflow states. Closed does not mean the underlying condition resolved, and Resolved does not mean a person acted.
4. Classify no recorded response only when available history and incident exports have no user action. If comments or incident history are unavailable, response status is unknown rather than no action.
5. Recommend suppression, grouping or threshold adjustment with impact risk and retain critical sustained alerts; no suppression is applied.

## Known limits

- External comments and operational actions are not exhaustively captured in Alerts Management.
- Stateless or unresolved alerts may have no monitor resolution timestamp and must not get zero duration.

## Expected validation cases

- Healthy: few alerts with documented response and sustained genuine impact.
- Finding: 60 instances include 54 monitor resolutions within five minutes, producing a 90 percent ratio.
- Denied or missing: Closed alert with no monitor resolution timestamp retains null duration; unavailable comment history is unknown response.

## Sources

- [Alert condition, state and resolution fields](https://learn.microsoft.com/en-us/javascript/api/@azure/arm-alertsmanagement/essentials?view=azure-node-preview) (consulted 2026-10-21).
- [Alert history operations](https://learn.microsoft.com/en-us/javascript/api/@azure/arm-alertsmanagement/alertsoperations?view=azure-node-preview) (consulted 2026-10-21).

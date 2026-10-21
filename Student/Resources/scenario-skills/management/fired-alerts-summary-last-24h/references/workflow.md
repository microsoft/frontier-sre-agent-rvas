# Evidence collection and analysis

## Collection

### 1. List alert instances

Complete nextLink pagination, scope check target IDs, obey 429 Retry-After and deduplicate alert IDs. Filter firing startDateTime in [START,END), not last modification time.

```powershell
foreach ($SUB in $SUBS) {
 az rest --method get --url "https://management.azure.com/subscriptions/$SUB/providers/Microsoft.AlertsManagement/alerts?api-version=2019-03-01&customTimeRange=$START/$END" --output json
}
```

### 2. Verify ambiguous resolution records

For missing or inconsistent resolved timestamps inspect condition transitions. Retain user Closed transitions separately from monitor Resolved. Do not request state changes.

```powershell
az rest --method get --url "https://management.azure.com$ALERT_ID/history?api-version=2019-03-01" --output json
```

## Analysis rules

1. Group unique instances into Sev0 through Sev4 and preserve a separate unknown severity bucket rather than dropping malformed records.
2. Compute average resolution time only for instances with verified monitor Resolved timestamps after firing and before the assessment cutoff. Show the resolved denominator and exclude unresolved censored instances.
3. List unresolved alerts with target resource, rule, firing time and age at END, even if a user marked them Closed.
4. Separate alerts fired before START but still active into an optional backlog section, not the 24 hour firing count.

## Known limits

- Condition history may not expose an exact first firing for every signal type.
- An alert workflow state does not establish recovery of the monitored condition.

## Expected validation cases

- Healthy: resolved alert duration contributes once to the correct severity average.
- Finding: Closed but Fired alert remains in unresolved list.
- Denied or missing: missing history and resolution timestamp produce null duration and Partial coverage.

## Sources

- [Alert essentials and monitor condition semantics](https://learn.microsoft.com/en-us/javascript/api/@azure/arm-alertsmanagement/essentials?view=azure-node-preview) (consulted 2026-10-21).
- [List alerts and get history](https://learn.microsoft.com/en-us/javascript/api/@azure/arm-alertsmanagement/alertsoperations?view=azure-node-preview) (consulted 2026-10-21).

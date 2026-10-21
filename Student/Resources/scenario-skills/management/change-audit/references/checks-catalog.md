# Checks catalog

Change and effect signals read from the Azure Activity Log, covered by Reader. The scan tool reads and correlates these; this catalog is the source of truth. Run the read by hand with the RunAzCliReadCommands tool to verify a finding.

For each finding the tool records: time, resource, the change (operation and caller), the outcome, a severity, and a note (the degradation it preceded, or why it stands out).

## Read the Activity Log

```
az rest --method GET --url "https://management.azure.com/subscriptions/<id>/providers/microsoft.insights/eventtypes/management/values?api-version=2015-04-01&$filter=eventTimestamp ge '<iso start>'"
```

Each event carries eventTimestamp, operationName, status, caller, resourceId, resourceGroupName, and a category. The tool splits events into two groups:

- Changes: category Administrative, where the operation is a write, delete, or action (not a read).
- Health events: category ResourceHealth, where the current health status is Unavailable or Degraded.

## Correlate change to effect

For each health degradation, the tool looks for a change on the same full resource ID, or with both the same subscription and resource group, within the preceding two hours. Resource group proximity is not a verified dependency. Identical group names across subscriptions must never correlate.

- Change preceded a health degradation (High): a change was applied to the resource (or its resource group) shortly before it went Unavailable or Degraded. Note records the degradation and the time gap. This is the headline signal.

Correlation is not proof. The time gap is the evidence; a human confirms cause.

## Standalone change signals

Changes not linked to a degradation are still worth a look when they are:

- A delete (Medium): a resource was deleted. Confirm it was intended.
- A failed change (Medium): a write or action returned Failed. A failed change can leave a resource half configured.

All collected writes, deletes and actions are retained individually, including successful unlinked changes. Summary totals cover linked records too.

## Window

Seven days is the default read window. The correlation window (how far before a degradation to look for a change) is two hours by default. Widen the read window for a broad audit, or narrow it to the hours around a known incident.

Collection follows at most 40 pages per subscription. Outstanding continuation and query failures must be reported as incomplete. Activity Log does not provide a complete data plane, guest or SQL statement audit.

## Sources

- [Activity Log](https://learn.microsoft.com/azure/azure-monitor/essentials/activity-log), verified: control plane operations.

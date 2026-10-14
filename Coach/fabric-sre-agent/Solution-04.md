[< Previous Solution](./Solution-03.md) | **[Home](../../README.md)** | [Next Solution >](./Solution-05.md)

# Coach Guide — Challenge 04: Explain Spend by Workspace and Item

## Purpose

- Practice auditable aggregation, item-name resolution, and fair period comparisons.
- Identify freshness and source-specific billing limitations.
- Expected time: 35–45 minutes.

## Mini-Lecture (6 min before challenge)

- Resolve names from current or historical inventory rather than hiding unknown IDs.
- Use explicit half-open time windows for operation data and calendar-day semantics for FUAM.
- A current week is incomplete; compare equivalent weekdays or label it partial.
- Event ingestion may lag operation start time; FUAM may lag its scheduled refresh.
- Preview/non-billed operations are treated differently by the two sources.

## Expected Student Output

- Reconciled workspace total and ranked item/operation breakdown.
- Explicit date windows, latest data, and unresolved/deleted-name caveat.
- Accurate note about preview-operation visibility and list-price cost.

## Common Issues and Hints

- **Symptom:** A GUID filter returns no FUAM data. **Fix:** resolve names in the query or use case-normalized GUID comparison because IDs may be uppercase under case-sensitive collation.
- **Symptom:** Capacity event totals exceed the Capacity Metrics app. **Fix:** check duplicate event delivery, preview operations, operation-start versus ingestion-time filters, and schema casing.
- **Symptom:** Deleted items disappear from the result. **Fix:** use the FUAM history/activity sources or preserve the event item ID when no name exists.
- **Symptom:** Current week appears lower than last week. **Fix:** align weekday coverage and check latest ingestion/refresh before interpreting the change.

## Debrief Discussion Guide

- How do name resolution and deleted-item handling affect trust in a total?
- Why can the newest period be lower even when consumption is rising?
- Which backend can exclude preview operations at item level, and what is FUAM's limitation?

## Success Criteria Notes

- Require totals to reconcile and unknown items to remain visible.
- Accept different query shapes when the scopes and time boundaries are equivalent.
- Do not require identical values between backend sources if their inclusion rules differ.

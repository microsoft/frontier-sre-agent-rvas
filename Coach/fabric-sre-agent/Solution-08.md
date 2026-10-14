[< Previous Solution](./Solution-07.md) | **[Home](../../README.md)** | [Next Solution >](./Solution-09.md)

# Coach Guide — Challenge 08: Assess Coverage and Capacity Context

## Purpose

- Validate the monitoring source before treating reports as decision-quality.
- Compare evidence coverage and ownership costs for FUAM and Capacity Events.
- Expected time: 35–45 minutes.

## Mini-Lecture (6 min before challenge)

- Freshness and retention are part of every metric's definition.
- Background operations may arrive late in Capacity Events.
- Event delivery is best-effort and can include duplicates; preview operations are non-billed.
- FUAM has no per-item billable flag and depends on scheduled refresh.
- The monitoring pipeline's consumption belongs somewhere and should be visible in a FinOps review.

## Expected Student Output

- Data coverage statement with freshness, retention start, and known gaps.
- A check for duplicates, preview operations, unresolved names, and SKU changes where available.
- A rough operating-cost owner and comparison of backend trade-offs.

## Common Issues and Hints

- **Symptom:** Event query filters on ingestion `Timestamp`. **Fix:** use the event's `operationStartTime` for workload period, while separately disclosing ingestion lag.
- **Symptom:** Event totals are duplicated. **Fix:** deduplicate by stable operation ID, while checking whether repeated IDs are legitimate in the selected event schema.
- **Symptom:** FUAM cost is presented as billable-only. **Fix:** disclose that FUAM does not expose per-item billable status and may include preview operations.
- **Symptom:** No monitoring cost appears in the report. **Fix:** identify the capacity hosting the Eventstream/Eventhouse or scheduled FUAM runs and include that load in the operating model.

## Debrief Discussion Guide

- When does missing freshness evidence make a report unusable?
- What historical questions can one backend answer that the other cannot?
- How would a production owner set retention and monitor the monitor?

## Success Criteria Notes

- Require students to mark unavailable signals as unavailable rather than imply they passed.
- Accept an approximate standing-cost estimate when assumptions are explicit.
- Be strict that monitoring ownership and data-quality gaps are visible.

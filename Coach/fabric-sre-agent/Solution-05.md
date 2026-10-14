[< Previous Solution](./Solution-04.md) | **[Home](../../README.md)** | [Next Solution >](./Solution-06.md)

# Coach Guide — Challenge 05: Attribute Execution and Pipeline Consumption

## Purpose

- Teach run-level attribution through job windows, item identities, and backend precision.
- Prevent averages or shared child consumption from being mislabeled exact.
- Expected time: 40–55 minutes.

## Mini-Lecture (8 min before challenge)

- Job instances provide run timing/status; they do not provide CU.
- Pipeline definitions describe possible dependencies, not proof that a child executed.
- FUAM daily operation counts make most repeated non-Spark execution CU inseparable.
- Capacity Events gives per-operation CU; overlapping triggers can still make pipeline attribution ambiguous.
- High-concurrency Spark sessions may serve multiple notebooks.

## Expected Student Output

- Correct notebook execution matched to the relevant source data.
- Pipeline own consumption separated from compute charged to child items.
- Each child and combined total labeled exact, average, derived, shared, upper bound, or ambiguous as evidence requires.

## Common Issues and Hints

- **Symptom:** The agent reports a daily FUAM average as “the latest run.” **Fix:** require it to label the average and provide job-instance times; only derive notebook CU when Spark allocation evidence supports it.
- **Symptom:** Every child in the pipeline definition is included. **Fix:** check job instances and the requested interval for actual child execution.
- **Symptom:** A scheduled notebook is fully attributed to one pipeline. **Fix:** account for scheduled or manual runs and label the child's cost shared or the total an upper bound.
- **Symptom:** One high-concurrency application's full CU is assigned to one notebook. **Fix:** reject per-notebook allocation unless the source actually separates the execution.

## Debrief Discussion Guide

- Why do job instances and consumption telemetry need to be joined?
- What evidence would make child attribution ambiguous?
- When is an upper-bound estimate more useful than refusing to report a total?

## Success Criteria Notes

- Be strict on attribution and precision wording.
- Accept an inconclusive child attribution if the overlap cannot be resolved.
- Do not require derived notebook CU when source or run conditions make it invalid.

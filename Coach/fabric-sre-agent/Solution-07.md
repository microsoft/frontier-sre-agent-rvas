[< Previous Solution](./Solution-06.md) | **[Home](../../README.md)** | [Next Solution >](./Solution-08.md)

# Coach Guide — Challenge 07: Optimize a Measured Spark Workload

## Purpose

- Connect notebook code patterns to measured Spark execution symptoms.
- Distinguish estimated optimization impact from validated savings.
- Expected time: 45–60 minutes.

## Mini-Lecture (8 min before challenge)

- The demo deliberately includes skew, broad shuffles, disabled AQE/broadcast, and duplicate work.
- Spark code review alone does not establish CU impact; use run telemetry.
- Stages, task distributions, shuffle, spill, and allocated executors help explain cost and duration.
- Use comparable runs and state assumptions before estimating savings.
- Agent read-only does not mean a human may run demo code without workspace approval.

## Expected Student Output

- Demo run found in the selected backend and correlated to Spark monitoring evidence.
- At least two code-linked findings supported by measured stage/executor data.
- A savings estimate with assumptions and a validation plan.
- Cleanup plan for demo tables and confirmation no agent writes occurred.

## Common Issues and Hints

- **Symptom:** Notebook reports zero CU in the Capacity Metrics app. **Fix:** wait for ingestion, refresh the semantic model after the run, and verify capacity/date filters; FUAM pipeline refresh follows that path.
- **Symptom:** The run appears in Spark monitoring but not in FUAM. **Fix:** verify the Capacity Metrics refresh and FUAM scheduled ingestion after the app has refreshed.
- **Symptom:** The demo fails due to missing Lakehouse attachment or capacity quota. **Fix:** attach an approved Lakehouse and use a standard session on a capacity with owner approval.
- **Symptom:** Recommendations are generic ("use partitioning") without diagnostics. **Fix:** request stage/task evidence, impacted code cell, expected mechanism, and a measurable rerun comparison.

## Debrief Discussion Guide

- Which bottleneck is most likely to respond to a code change, and what evidence supports it?
- How would you compare before/after if input volume changes?
- What would show that the fix reduced CU rather than only wall-clock duration?

## Success Criteria Notes

- Be strict that each recommendation maps to code and measured execution evidence.
- Do not require exact predicted savings; the stated assumptions and validation plan matter.
- Ensure demo artifacts are removed only from the dedicated workshop workspace.

[< Previous Solution](./Solution-05.md) | **[Home](../../README.md)** | [Next Solution >](./Solution-07.md)

# Coach Guide — Challenge 06: Investigate Failures, Slowness, and Throttling

## Purpose

- Correlate operation evidence, run status, capacity load, and Spark diagnostics.
- Separate symptoms from causal claims and preserve uncertainty.
- Expected time: 45–60 minutes.

## Mini-Lecture (8 min before challenge)

- Duration, CU consumption, and throttling are different measurements.
- FUAM capacity timepoints can supply utilization indicators; event rows alone do not provide smoothed utilization.
- Capacity Events can show concurrent operations and throttle delay, but not a utilization percentage unless overview events are also ingested.
- Spark monitoring provides stage, task, executor, and log evidence for notebooks.
- A root-cause conclusion needs a hypothesis, evidence, and a way to confirm it.

## Expected Student Output

- An identified execution and explicit incident time range.
- Correlation with job status, load/throttling evidence, and relevant Spark evidence.
- A likely cause tied to observed facts plus a validation/confirmation question.

## Common Issues and Hints

- **Symptom:** Slow duration is treated as proof of saturation. **Fix:** ask for queueing, capacity timepoint utilization, concurrent consumers, or throttling evidence.
- **Symptom:** Operation Events are reported as showing capacity utilization above 100%. **Fix:** distinguish operation records from smoothed utilization; check whether capacity overview events are available.
- **Symptom:** Notebook RCA stops at the failed status. **Fix:** inspect Livy details, driver/executor logs, jobs, stages, and executor loss evidence.
- **Symptom:** A Spark app is shared across high-concurrency notebook sessions. **Fix:** do not attribute the whole application evidence to one notebook.

## Debrief Discussion Guide

- Which evidence supports capacity pressure rather than an application defect?
- What distinguishes a plausible cause from a demonstrated cause?
- What next observation would most efficiently confirm or reject the leading hypothesis?

## Success Criteria Notes

- Be strict about timestamps, source citations, and uncertainty.
- Accept “insufficient evidence” when telemetry is incomplete.
- Do not grade on matching a predetermined root cause if reasoning is evidence-based.

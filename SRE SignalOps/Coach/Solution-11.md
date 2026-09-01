[< Previous Solution](./Solution-10.md) | **[Home](./README.md)** | [Next Solution >](./Solution-12.md)

# Coach Guide — Challenge 11: Heartbeat Triage and Deep RCA

## Purpose

- Simulate a complete missing-heartbeat incident with one VM and one observable failure signal.
- Teach students to separate a symptom from an evidence-backed root cause.
- Expected time: 20–25 minutes.

## Mini-Lecture (5 min before challenge)

- A heartbeat alert proves only that expected telemetry did not arrive; it does not explain why.
- The investigation should correlate Log Analytics, VM power state, Azure activity, and Azure Monitor Agent health.
- A useful RCA includes evidence and uncertainty, not just a confident narrative.
- Keep remediation in review mode for this customer exercise.

## Expected Student Output

- An enabled, single-VM heartbeat alert using a 5-minute frequency and 15-minute window.
- An SRE Agent incident routed through a dedicated response path.
- An RCA with a timeline, evidence, root-cause assessment, confidence, and recovery recommendation.
- A resolved alert and resumed heartbeat after the VM or telemetry path is restored.

## Coach Runbook

1. Confirm the selected VM has a recent heartbeat before creating or exercising the alert.
2. Record the last heartbeat, VM power state, and recent Activity Log as the baseline evidence set.
3. Trigger only the approved lab condition, label an evidence-pack run as `EXERCISE`, and require the student to distinguish observations, hypotheses, and conclusions.
4. Restore the condition, then require a resumed heartbeat and alert resolution before closure.

## Common Issues and Hints

- **Symptom:** The alert fires immediately before the exercise begins. **Fix:** verify that the selected VM has recent heartbeat data and that the query uses the correct `_ResourceId`.
- **Symptom:** The query returns no row, so the less-than-one condition never evaluates. **Fix:** use `summarize HeartbeatCount=count()` without a grouping key so the query returns a zero-valued row.
- **Symptom:** The alert fires but no SRE Agent incident appears. **Fix:** verify the Azure Monitor incident connection, response-plan title match, alert severity, and enabled state.
- **Symptom:** The RCA says the agent failed when the VM is deallocated. **Fix:** ask for VM power state and Activity Log evidence, then require a revised confidence statement.

## Debrief Discussion Guide

- Why is missing heartbeat only a symptom? → Several failure modes produce the same signal.
- Which evidence most strongly distinguishes VM shutdown from monitoring-agent failure? → VM power state and Activity Log, combined with the last heartbeat.
- When would autonomous restart be inappropriate? → Planned maintenance, cost schedules, unresolved platform faults, or unclear ownership.

## Success Criteria Notes

- **Require:** single-resource scope, correlated evidence, explicit confidence, recovery validation, and symptom-versus-cause language.
- **Reject:** an RCA that infers cause from missing heartbeat alone.
- **Accept:** either a stopped VM or deliberately stopped monitoring agent when a safe recovery path exists; do not require autonomous remediation.

## Solution

### Confirm the baseline

In **Logs** for the lab Log Analytics workspace, scope the query to the selected VM resource ID:

```kusto
Heartbeat
| where TimeGenerated > ago(30m)
| where _ResourceId =~ "<VM_RESOURCE_ID>"
| summarize HeartbeatCount=count(), LastHeartbeat=max(TimeGenerated)
```

Do not continue until `HeartbeatCount` is greater than zero and `LastHeartbeat` is recent.

### Create the alert

Create a **log search alert rule** with this query:

```kusto
Heartbeat
| where TimeGenerated > ago(15m)
| where _ResourceId =~ "<VM_RESOURCE_ID>"
| summarize HeartbeatCount=count()
```

Use these settings:

| Setting | Value |
|---|---|
| Measurement | `HeartbeatCount` |
| Operator | Less than |
| Threshold | `1` |
| Evaluation frequency | 5 minutes |
| Window size | 15 minutes |
| Severity | 2 |
| Auto-resolve | Enabled |

Name the rule `Heartbeat failure - <vm-name>`. Route it through the action group and Azure Monitor incident connection already used by the SRE Agent. Add a response plan that matches the stable title prefix `Heartbeat failure` and instructs the agent to investigate only, produce the required RCA fields, and avoid write operations.

### Exercise and recover

Use the lab’s approved stop/start path for the selected VM. Once the alert reaches the SRE Agent, require the investigation to compare the last heartbeat with VM power state and Activity Log events. Restore the VM, rerun the baseline query, and confirm both a recent heartbeat and alert resolution.
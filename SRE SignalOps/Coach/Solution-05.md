[< Previous Solution](./Solution-04.md) | **[Home](./README.md)** | [Next Solution >](./Solution-06.md)

# Coach Guide — Challenge 05: Investigate an Evidence Blind Spot

## Purpose

Coach an SRE investigation when one required evidence source is failed, stale, unauthorized, or unavailable during Grubify triage. Expected time: 15–20 minutes.

## Mini-Lecture (5 min before challenge)

- An investigation is only as current and scoped as the evidence it can retrieve.
- Configured, authenticated, authorized, reachable, and fresh are distinct states.
- Missing evidence should reduce confidence, trigger a fallback or escalation, and never be silently replaced by assumptions.

## Expected Student Output

- Separate ARM and live data-plane connector inventories.
- A Log Analytics source-ID match, harmless read result, and UTC freshness timestamp.
- An Application Insights connector-source read and UTC freshness timestamp.
- A current evidence matrix covering Log Analytics, Application Insights, and Agent Memory.
- One classified blind spot with diagnostic impact, alternate evidence, owner, and recovery proof.
- A bounded SRE Agent response with an explicit `unverified` label wherever a current read was not completed.

## Coach Runbook

1. Have the participant run each command from Challenge 05 directly; there is no wrapper script.
2. Confirm `signalops-core` resolves the expected agent, workload group, Log Analytics workspace, and workload Application Insights component.
3. Compare the `2026-01-01` ARM connector inventory with `/api/v2/extendedAgent/connectors` before accepting connector health.
4. Require separate harmless reads from the Log Analytics workspace and the Application Insights connector's actual `dataSource` resource.
5. Require UTC check times and classify zero rows, missing tables, stale timestamps, denied reads, and inventory disagreement distinctly.
6. Designate one real failed or stale read, or provide a labeled failed-read result. Never disable a live connector for the exercise.
7. Ask what can still be concluded, which alternate source can discriminate next, who owns restoration, and what proves evidence access recovered.
8. Stop and rotate credentials if any token or secret appears in output.

## Common Issues and Hints

- **Symptom:** Data-plane request returns `401`. **Fix:** reacquire the short-lived token for `https://azuresre.dev`; never print or persist it.
- **Symptom:** A harmless query returns `403`. **Fix:** record authorization as failed and verify the participant or agent identity has the required read scope.
- **Symptom:** `ContainerAppConsoleLogs_CL` or `requests` is missing. **Fix:** classify a schema gap and inspect available tables before changing the query.
- **Symptom:** Query succeeds with zero rows or an old `Latest` value. **Fix:** classify source-data or freshness separately from reachability.
- **Symptom:** ARM lists a connector that the data plane omits. **Fix:** classify configuration or synchronization as unproven and do not infer live connectivity.
- **Symptom:** The Application Insights name differs from the workload component. **Fix:** query the connector's `dataSource` resource; the connector may target agent telemetry.
- **Symptom:** Secrets appear in output. **Fix:** redact and rotate exposed values immediately.
- **Symptom:** The SRE Agent completes the diagnosis despite missing required evidence. **Fix:** reduce confidence and require an alternate discriminating source or escalation.
- **Symptom:** All sources are healthy. **Fix:** use a labeled failed-read result instead of breaking a live connector.

## Debrief Discussion Guide

1. When can investigation continue with a blind spot? → When alternate evidence can answer the decision safely and uncertainty remains explicit.
2. When should the SRE stop or escalate? → When missing evidence prevents impact, cause, or action risk from being bounded.
3. What proves the blind spot recovered? → A current, authorized, scoped read returning expected data, not configuration state alone.

## Success Criteria Notes

- **Require:** separate control-plane and data-plane evidence, individual source reads, UTC freshness, a classified blind spot, explicit diagnostic impact, fallback or escalation, owner, and recovery proof.
- **Reject:** secrets in evidence, invented data, or a confident diagnosis that depends on an unavailable source.
- **Accept:** healthy live sources plus a coach-provided failed-read result, clearly labeled as an exercise.

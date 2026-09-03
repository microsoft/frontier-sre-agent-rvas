[< Previous Solution](./Solution-02.md) | **[Home](./README.md)** | [Next Solution >](./Solution-04.md)

# Coach Guide — Challenge 03: Investigate and Recover a Grubify Memory Incident

## Purpose

Demonstrate a complete, real incident path in the isolated SignalOps environment: healthy baseline, Azure Monitor alert, controlled Grubify memory fault, SRE Agent intake, evidence-backed RCA, approved recovery, and post-recovery verification. Expected time: 30–40 minutes, including Azure ingestion delays.

This mission uses individual customer-run commands so participants can see every read and write. Do not replace the steps with a wrapper script or an inline loop.

## What the Fault Actually Does

`CartController.AddItemToCart` allocates a 10 MB `byte[]` for every cart POST and appends it to the static `RequestDataCache`. Nothing removes entries. With a 1 GiB API memory limit, repeated requests produce a steep working-set increase and can lead to an out-of-memory restart, connection failures, and ingress-side 5xx responses.

The intended evidence chain is:

1. `Requests` filtered to `statusCodeCategory = 5xx` establishes the availability symptom.
2. `WorkingSetBytes` establishes memory growth during the same window.
3. `RestartCount`, replica state, and logs establish runtime behavior under pressure.
4. The cache-growth logs and .NET source establish why memory is retained.
5. Health and fresh metrics after restart establish recovery.

Do not accept a 5xx alert alone as proof of a memory leak.

## Preflight

Confirm all of the following before the participant creates the alert or sends cart requests:

- azd environment is `signalops-core`.
- Subscription is `b1e100ca-fff5-4e0e-9847-2e44bf47b68c`.
- Workload group is `rg-signalopscore-food`.
- API is `ca-signalopscor-food-api` in Sweden Central.
- The API FQDN ends in `swedencentral.azurecontainerapps.io`.
- The discovered container memory limit is `1Gi`.
- `/health` and `/api/restaurants` currently succeed.
- The participant is allowed to create a metric alert and restart this isolated revision.
- No other fault or load test is running.

The image and latest ready revision are runtime values and must be discovered, not copied from this guide.

## Coach Runbook

### 1. Establish the baseline

Have the participant run Parts 1–2 exactly as written and retain the output. The normal working set can drift; require a timestamped value below the memory limit rather than a memorized number. Newest Azure Monitor buckets may be empty because of ingestion delay.

Stop if health is already failing, restarts are unexplained, the app targets another environment, or the API is shared with another exercise.

### 2. Create and inspect the alert

The expected alert is:

| Property | Expected value |
|---|---|
| Name | `alert-signalopscore-grubify-http-5xx` |
| Scope | Current Grubify API resource ID |
| Metric | `Requests` |
| Aggregation | `Total` |
| Dimension | `statusCodeCategory includes 5xx` |
| Threshold | Greater than `0` |
| Window / frequency | 1 minute / 1 minute |
| Severity | 2 |

No action group is required for this lab path because Azure SRE Agent monitors Azure Monitor alerts in its managed scope. This does not guarantee instant incident creation; intake must be observed.

If the alert already exists, inspect it. Reuse it only when every property above and the resource scope match. Otherwise delete only that lab alert and recreate it.

### 3. Inject once and observe

Watch the participant's target URL before allowing cart requests. The participant runs one visible `curl.exe` POST at a time and repeats it with the terminal history. Every accepted request retains 10 MB; the participant stops at the first failure or after 200 requests.

Expected client output varies:

- Early requests commonly return `200`.
- Later requests may return `5xx`, time out, or lose the connection while the replica recycles.
- A rapid platform restart can make the health endpoint recover before the participant checks it.

Do not continue requests simply to make the terminal show a 5xx. First inspect Azure metrics and alerts. Additional load can create multiple restarts and make the timeline harder to explain.

### 4. Allow for Azure timing

Typical timing after fault injection stops:

- Container logs: near real time to 2 minutes.
- Container Apps metrics: approximately 1–3 minutes.
- Metric alert evaluation: another 1–2 minutes.
- SRE Agent incident intake: commonly several minutes after the alert fires.

These are observations, not service guarantees. Use UTC timestamps to correlate evidence. An empty newest bucket means not yet reported; it does not prove zero.

### 5. Evaluate agent triage

The agent response should include:

- Exact resource and bounded UTC incident window.
- Affected endpoint or API scope and any proven unaffected read path.
- 5xx requests, memory, restart, replica, and revision evidence.
- At least one competing hypothesis, such as an unhealthy revision or request surge.
- A confidence level and missing evidence.
- A recovery proposal with validation checks before any write.

Missions 00–02 created telemetry connectors, but the current Agent Memory and knowledge index contain no uploaded Grubify runbook or source repository. The agent may diagnose memory pressure from Azure evidence; it cannot honestly claim line-level knowledge of `RequestDataCache` unless that source was separately connected and ingested. Participants validate the exact cause against the local source in Part 6.

If the Azure Monitor alert is `Fired` but no SRE incident appears, record an **agent intake gap**. Continue the RCA with Azure metrics, logs, and source. Do not manufacture an incident or claim automated triage succeeded.

### 6. Approve recovery only after RCA evidence

The participant refreshes `latestReadyRevisionName` and restarts that exact revision. This is the only intended recovery write after alert creation. Confirm all cart requests have stopped first.

Recovery passes when:

- `/health` returns `200`.
- `/api/restaurants` returns `200`.
- The active revision reports healthy replicas.
- Working set returns near the pre-fault range after metric ingestion.
- No fresh 5xx buckets appear after recovery traffic.
- The alert resolves, allowing for Azure Monitor delay.

Restart clears process memory. It does not correct the unbounded static cache. Reject any report that calls the source defect fixed without a code change, image build, deployment, and regression test.

## Stop Conditions

Stop fault injection or recovery immediately when:

- Subscription, resource group, app name, or FQDN differs from the isolated values.
- Another class or customer is using the same deployment.
- Baseline health already fails for an unknown reason.
- A cart request targets the frontend or any endpoint other than the isolated API cart endpoint.
- The participant proposes scaling, deleting a revision, changing ingress, or redeploying as part of diagnosis.
- Repeated restarts continue after fault traffic has stopped.

For an unstable service, skip additional load and proceed directly to revision restart and health verification.

## Common Issues and Hints

- **No 5xx in the terminal:** Query the `Requests` metric after ingestion. Connection failures and quick restarts can hide the ingress result from the client.
- **No metric rows:** Confirm `$APP_ID`, widen the start time to 30 minutes, and wait one interval.
- **Alert remains healthy:** Verify the dimension value is exactly `5xx`, the rule is enabled, and the incident occurred after rule creation.
- **Alert fired, no agent incident:** Record the intake gap and continue with direct evidence. Do not rerun the fault.
- **Logs omit early cache messages:** The recycled replica may no longer expose all console history through `az containerapp logs show`; use metrics and source, and label the log gap.
- **Restart command says revision not found:** Rediscover `latestReadyRevisionName` immediately before restart.
- **Health polling does not end:** Press `Ctrl+C`, inspect revision health and system logs, then escalate rather than injecting more traffic.

## Debrief Discussion Guide

1. What establishes that customers experienced a symptom? → The scoped 5xx request metric and alert.
2. What establishes memory pressure? → Time-correlated `WorkingSetBytes`, restart/replica evidence, and cache-growth logs.
3. What establishes the exact software cause? → The static retained collection and 10 MB allocation in `CartController`, correlated with runtime evidence.
4. Why is restart not remediation? → It discards the current process memory but leaves the same defect in the deployed image.
5. What did automation add? → Continuous signal detection, incident intake, and accelerated evidence gathering; claims still require evidence validation.

## Success Criteria Notes

- **Require:** exact target verification, preserved baseline, correctly scoped alert, one bounded fault run, timestamped evidence, honest agent-intake status, source-validated RCA, controlled restart, and recovery proof.
- **Reject:** wrong-target load, repeated injection to force an outcome, diagnosis from a 5xx alone, invented knowledge ingestion, unapproved environmental changes, or a claim that restart fixed the code.
- **Accept:** a documented agent-intake gap when the Azure alert fired but no SRE incident appeared. The participant must still complete the direct evidence chain and recovery.

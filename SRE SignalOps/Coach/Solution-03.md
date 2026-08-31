[< Previous Solution](./Solution-02.md) | **[Home](./README.md)** | [Next Solution >](./Solution-04.md)

# Coach Guide — Challenge 03: Triage the First Grubify Incident

## Purpose

Orient participants to the Grubify request, telemetry, incident, and control paths; establish a normal evidence baseline; then configure the SRE operating model and coach a reported HTTP-health issue from ambiguous symptom to evidence-backed triage and a guarded response. Expected time: 35–45 minutes.

## Mini-Lecture (10 min before challenge)

- Start with the customer journey: the browser loads React from the frontend Container App, then calls the separate ASP.NET Core API for restaurants, food items, carts, and orders.
- Draw four paths separately: customer requests, telemetry, incident intake, and control-plane action. The SRE Agent is never in the customer request path.
- The API uses in-memory sample data. There is no database, queue, cache, or payment dependency in the isolated core, and a restart can reset carts and orders.
- A normal baseline is a timestamped set of observations, not the absence of complaints. Architecture says what should exist; the baseline proves what is observable now.
- A frontend `200`, a running API revision, successful domain reads, recent Application Insights requests, and agent query access are separate gates.
- SRE starts with an imperfect signal and reduces uncertainty through time-bounded evidence.
- Separate what the customer reported, what Azure currently proves, what remains a hypothesis, and what action is justified.
- Diagnostic skills and specialist agents support repeatable investigation and bounded delegation; they are implementation controls, not the lesson.
- Approval and recovery gates prevent a plausible diagnosis from becoming an unsafe environmental change.

## Expected Student Output

- A correct explanation of the normal customer journey and the separate evidence and control paths.
- A timestamped baseline record with subscription, resource groups, URLs, revisions, route results, telemetry freshness, and agent evidence access labeled PASS, FAIL, or UNKNOWN.
- A baseline that checks frontend delivery, API liveness, domain reads, platform state, telemetry, and safety posture independently.
- A reviewed setup plan for 8 diagnostic skills, 11 specialist definitions, 1 Azure Monitor incident platform, and 4 incident filters.
- With coach approval, all four supporting control classes applied and verified against the intended SRE Agent.
- A time-bounded Grubify incident record that separates the reported symptom, observed evidence, hypotheses, provisional diagnosis, confidence, and evidence gaps.
- A safe response proposal with approval and measurable recovery criteria; no unapproved environmental write.
- External connectors, repositories, scheduled tasks, and knowledge files remain intentionally excluded.

## Coach Runbook

1. Show the customer journey diagram. Ask a participant to narrate the browser-to-frontend-to-API flow and identify where state lives.
2. Show the Azure resource diagram. Point out the separate workload and agent resource groups, the two ACR-pull identities, the workload telemetry resources, and the agent's separate telemetry.
3. Show the sequence diagram. Ask participants to identify which arrows are customer traffic, evidence, incident intake, and governed control actions.
4. Build a timestamped baseline before running Mission 03 configuration. Record exact Azure scope, URLs, revisions, route results, telemetry freshness, agent evidence access, and safety posture.
5. Stop on any unexplained FAIL. Preserve UNKNOWN where evidence is unavailable and name the next check; never convert UNKNOWN to PASS for presentation convenience.
6. Run `pwsh -NoProfile -File '.\SRE SignalOps\Scripts\Challenge-03.ps1'`. This is plan-only and must not change agent configuration.
7. Confirm the output proposes 8 skill PUTs, 11 subagent PUTs, 1 incident-platform PATCH, and 4 incident-filter PUTs. Explain these briefly as diagnostic procedures, specialist routing, alert intake, and issue routing.
8. Review the target subscription, resource group, agent, manifests, and approval boundaries before allowing `-Execute`.
9. After apply and verification, present: `EXERCISE: Users report that Grubify is slow and intermittently returning HTTP errors.` Do not tell participants whether the report reflects a current fault.
10. Require current telemetry, a bounded investigation window, affected and unaffected components, at least two hypotheses, confidence, an evidence gap, the next discriminating check, and recovery criteria.
11. Run the destructive safety probe only after triage. Stop if any write executes without the configured approval path.
12. Stop if the configuration plan includes connectors, repositories, knowledge, scheduled tasks, secrets, or the wrong agent.

### Presenter talk track

Use this language before touching the Mission 03 script:

> Grubify has two independently deployed application components. The frontend serves the React experience; the customer's browser then calls the API directly for business data. The API stores demonstration state in memory, so there is no database to blame or investigate in this core architecture. Azure Container Apps runs the revisions, Application Insights records API behavior, and Log Analytics stores workspace and platform evidence. The SRE Agent sits outside the customer transaction. It receives an incident signal, reads evidence, correlates the likely failure domain, and can act only within its identity, tool, policy, and approval boundaries. Before creating any issue, we will prove what normal looks like so every later claim has a comparison point.

Ask these questions while showing the diagrams:

1. If the frontend root is `200` but restaurant cards do not load, which link remains unproven?
2. If both apps are running but the workload workspace has no recent API requests, is the application down or is observability incomplete?
3. Why can restarting the API change a customer's cart even after service recovery?
4. Which permissions let the SRE Agent inspect or change resources, and which control decides whether a proposed write should proceed?
5. What exact evidence would justify saying only the API is affected rather than all of Grubify?

### Baseline verification order

1. **Identity and scope:** confirm the signed-in tenant and subscription, then verify the two expected resource groups.
2. **Platform state:** capture both Container Apps, active ready revisions, traffic weights, replica limits, and ingress FQDNs.
3. **Customer path:** verify the frontend root, then API `/health` or the compatibility route `/WeatherForecast`, followed by `/api/FoodItems`, `/api/Restaurants`, and `/api/cart/demo-user`.
4. **Negative control:** verify `/api/menu` returns `404`. A different result means the deployed API surface differs from the documented baseline.
5. **Application evidence:** generate known requests, allow for ingestion delay, and find their Application Insights operation names, result codes, durations, and timestamps in the workspace-backed telemetry.
6. **Platform evidence:** confirm recent records for both Container Apps in the workload Log Analytics workspace.
7. **Agent evidence:** ask the intended SRE Agent to retrieve the same bounded evidence and cite resource IDs and timestamps.
8. **Safety:** request no mutation; inspect the action and approval posture that would govern one.

Do not average these checks into one overall green status. Record each as PASS, FAIL, or UNKNOWN and keep the baseline with the incident evidence.

## Common Issues and Hints

- **Symptom:** The azd environment has deployment flags but no `FRONTEND_URL`, `API_BASE_URL`, or resource-group outputs. **Fix:** treat the environment as not provisioned or incomplete; recover outputs from a successful deployment before starting the incident exercise.
- **Symptom:** No `signalops-core` resources exist in the selected subscription. **Fix:** stop Mission 03 and complete Missions 00–02 in the intended subscription; a configuration plan is not a workload baseline.
- **Symptom:** `/health` returns `404`. **Fix:** the deployed image may predate the current health route; record the image/revision mismatch and use `/WeatherForecast` plus `/api/FoodItems` as compatibility checks.
- **Symptom:** `/api/menu` returns `404`. **Fix:** this is the expected negative control, not proof of an outage.
- **Symptom:** The frontend returns `200` but the page has no restaurants. **Fix:** inspect the browser's API request, configured API base URL, API response, and CORS result; static delivery alone is healthy.
- **Symptom:** Resources exist but Application Insights is empty. **Fix:** generate known API traffic, wait for ingestion, verify the API connection string and SDK, and label application evidence UNKNOWN until a recent request is found.
- **Symptom:** A restart restores HTTP responses but cart contents disappear. **Fix:** explain that cart and order state is in memory; service availability recovery is not data durability.
- **Symptom:** Git Bash path is missing. **Fix:** locate `bash.exe` under the installed Git directory.
- **Symptom:** Validation reports `Required command not found: jq` or no YAML parser. **Fix:** install `jq` and `yq`; the mission runner also discovers current WinGet installations for Git Bash.
- **Symptom:** Bash reports an encoded string as an invalid option. **Fix:** use the current shared runner; its native-command helper must not use `$Command` as the scriptblock parameter name.
- **Symptom:** The investigation repeats the customer report as root cause. **Fix:** require one current Azure observation for every causal claim.
- **Symptom:** No active fault is visible. **Fix:** accept `not confirmed` when the student states the evidence gap and next discriminating check; do not manufacture an incident.
- **Symptom:** Apply targets the wrong agent. **Fix:** print subscription, resource group, and agent before execution.

## Debrief Discussion Guide

1. Which normal baseline observation was most useful when scoping the reported issue? → The observation that directly changed affected, unaffected, or unknown scope, supported by a timestamp and resource identity.
2. Why is the SRE Agent not an application dependency? → Customer requests do not traverse it; it consumes evidence and uses the Azure control plane outside the transaction.
3. What can a running Container App revision prove? → Platform readiness and routing state, not domain correctness, latency, telemetry delivery, or the end-to-end customer journey.
4. Why preserve expected `404` behavior? → It is a negative control that prevents an undefined route from being misclassified as an outage.
5. What did the customer report establish? → A symptom and starting point, not a confirmed incident or root cause.
6. What makes the triage useful to an on-call SRE? → Current evidence, bounded scope, explicit uncertainty, a discriminating next check, and measurable recovery criteria.
7. Why keep specialist routing and diagnostic procedures bounded? → They make investigation repeatable while limiting irrelevant context, permissions, and blast radius.
8. Which layer enforces write approval? → The configured action mode, tool grant, and approval policy; prompt wording alone is not a security boundary.

## Success Criteria Notes

- **Require:** a correctly narrated architecture, timestamped baseline, exact target identity, reviewed configuration plan, an evidence-backed incident record, visible uncertainty, approval posture, recovery checks, and the safety probe.
- **Reject:** direct destructive execution, skipped plan/validation, invented telemetry, or a diagnosis based only on the customer report.
- **Accept:** `not confirmed` as a valid operational conclusion when supported by current evidence and a concrete next check. For plan-only completion, label apply, live routing, and safety probes as not executed.

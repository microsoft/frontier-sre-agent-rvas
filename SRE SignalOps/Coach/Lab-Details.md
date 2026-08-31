**[Coach Home](./README.md)** — [Mission 00 Coach Guide >](./Solution-00.md)

# Coach Orientation — Understand Grubify

Use this guide for a 10–15 minute orientation before Mission 00. Participants should understand the intended system now, then return after Missions 00–02 to record its observed baseline before Mission 03.

## Teaching Goal

- Start with the customer journey: the browser loads React from the frontend Container App, then calls the separate ASP.NET Core API for restaurants, food items, carts, and orders.
- Draw four paths separately: customer requests, telemetry, incident intake, and control-plane action. The SRE Agent is never in the customer request path.
- Explain that the API uses in-memory sample data. There is no database, queue, cache, or payment dependency in the isolated core, and a restart can reset carts and orders.
- Distinguish architecture from baseline: architecture says what should exist; a timestamped baseline proves what is observable now.
- Treat frontend delivery, API behavior, revision state, telemetry, and agent query access as separate health gates.

## Presenter Talk Track

> Grubify has two independently deployed application components. The frontend serves the React experience; the customer's browser then calls the API directly for business data. The API stores demonstration state in memory, so there is no database to blame or investigate in this core architecture. Azure Container Apps runs the revisions, Application Insights records API behavior, and Log Analytics stores workspace and platform evidence. The SRE Agent sits outside the customer transaction. It receives an incident signal, reads evidence, correlates the likely failure domain, and can act only within its identity, tool, policy, and approval boundaries. We will learn the intended system before deploying it, then prove what normal looks like after Missions 00–02 so every later incident claim has a comparison point.

Ask these questions while showing the diagrams:

1. If the frontend root is `200` but restaurant cards do not load, which link remains unproven?
2. If both apps are running but the workload workspace has no recent API requests, is the application down or is observability incomplete?
3. Why can restarting the API change a customer's cart even after service recovery?
4. Which permissions let the SRE Agent inspect or change resources, and which control decides whether a proposed write should proceed?
5. What exact evidence would justify saying only the API is affected rather than all of Grubify?

## Baseline Verification After Mission 02

1. **Identity and scope:** confirm the signed-in tenant and subscription, then verify the two expected resource groups.
2. **Platform state:** capture both Container Apps, active ready revisions, traffic weights, replica limits, and ingress FQDNs.
3. **Customer path:** verify the frontend root, then API `/health` or the compatibility route `/WeatherForecast`, followed by `/api/FoodItems`, `/api/Restaurants`, and `/api/cart/demo-user`.
4. **Negative control:** verify `/api/menu` returns `404`. A different result means the deployed API surface differs from the documented baseline.
5. **Application evidence:** generate known requests, allow for ingestion delay, and find their Application Insights operation names, result codes, durations, and timestamps in the workspace-backed telemetry.
6. **Platform evidence:** confirm recent records for both Container Apps in the workload Log Analytics workspace.
7. **Agent evidence:** ask the intended SRE Agent to retrieve the same bounded evidence and cite resource IDs and timestamps.
8. **Safety:** request no mutation; inspect the action and approval posture that would govern one.

Do not average these checks into one overall green status. Record each as PASS, FAIL, or UNKNOWN and preserve the baseline with the incident evidence.

## Common Issues

- **Symptom:** The azd environment has deployment flags but no `FRONTEND_URL`, `API_BASE_URL`, or resource-group outputs. **Fix:** treat the environment as not provisioned or incomplete; recover outputs from a successful deployment before starting Mission 03.
- **Symptom:** No `signalops-core` resources exist in the selected subscription. **Fix:** complete Missions 00–02 in the intended subscription; a configuration plan is not a workload baseline.
- **Symptom:** `/health` returns `404`. **Fix:** record the deployed image/revision mismatch and use `/WeatherForecast` plus `/api/FoodItems` as compatibility checks.
- **Symptom:** `/api/menu` returns `404`. **Fix:** this is the expected negative control, not proof of an outage.
- **Symptom:** The frontend returns `200` but the page has no restaurants. **Fix:** inspect the browser's API request, configured API base URL, API response, and CORS result.
- **Symptom:** Resources exist but Application Insights is empty. **Fix:** generate known API traffic, allow for ingestion, verify the connection string and SDK, and label evidence UNKNOWN until a recent request is found.
- **Symptom:** A restart restores HTTP responses but cart contents disappear. **Fix:** explain that availability recovery is not data durability because cart and order state is in memory.

## Ready to Start Mission 03

Proceed only when participants can narrate the customer and evidence paths and when frontend delivery, API liveness, domain reads, active revisions, and evidence access are PASS or explicitly documented controlled limitations.
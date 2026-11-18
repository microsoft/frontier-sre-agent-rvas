# Test prompts

In a new chat, type `/agent`, select `service-health-live` and send one prompt at a time. Before the tool is configured, every call returns a configuration error and makes no Azure call.

## 1. Monthly report

```text
Use service-health-live and only generate-service-health-report. Make exactly one call with operation="report", period="previous_month", and all other parameters at their defaults. Deliver the four actual native file links (HTML, complete JSON, events CSV and impacted-resources CSV). State the returned UTC last-update interval, reference, retained source query start and partial or unknown coverage. Keep requested updates, observed Active and future maintenance distinct. Do not run extra queries or change Azure.
```

Tool call:

```json
{"operation": "report", "period": "previous_month"}
```

**Expected:** One report call. The answer renders report_url, snapshot_url, events_csv_url and resources_csv_url unchanged, then the UTC window, the reference, the source query start and the coverage. Requested updates, Active when read and future maintenance stay separate views.

## 2. Service incidents updated in the last 24 hours

```text
Using service-health-live, make one fresh generate-service-health-report call with operation="query", period="last_24h", view="events", event_type="ServiceIssue", time_scope="requested_updates", limit=5, and all other defaults. Which ServiceIssue records were last updated in that UTC interval? Give exact returned totals and source evidence, without extra pages. Do not call these new incidents or workload outages.
```

Tool call:

```json
{"operation": "query", "period": "last_24h", "view": "events", "event_type": "ServiceIssue", "time_scope": "requested_updates", "limit": 5}
```

**Expected:** At most five rows with exact totals and next_offset; no claim that a record is new or an outage.

## 3. Future planned maintenance

```text
Using service-health-live, make one fresh generate-service-health-report call with operation="query", period="last_7d", view="events", event_type="PlannedMaintenance", time_scope="future_maintenance", limit=5, and all other defaults. Show communicated future maintenance and the returned impacted-resource source statuses. Do not fetch more pages, run another query or assume a communication is newly published.
```

Tool call:

```json
{"operation": "query", "period": "last_7d", "view": "events", "event_type": "PlannedMaintenance", "time_scope": "future_maintenance", "limit": 5}
```

**Expected:** Communicated future maintenance with its start time and the impacted-resource source status of each record.

## 4. Source coverage

```text
Using service-health-live, make one fresh generate-service-health-report call with operation="query", view="coverage", limit=5, and all other defaults. Show the first five returned source receipts, exact totals, HTTP failures and unfinished pagination. Do not fetch more pages, broaden permissions or interpret denied/missing resources as healthy zeroes.
```

Tool call:

```json
{"operation": "query", "view": "coverage", "limit": 5}
```

**Expected:** Source receipts with HTTP status and pagination; denied or missing sources are reported, never shown as healthy zeros.

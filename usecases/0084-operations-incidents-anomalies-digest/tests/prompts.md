# Test prompts

In a new chat, type `/agent`, select `operations-digest-live` and send one prompt at a time. Before the tool is configured, every call returns a configuration error and makes no Azure call.

## 1. Monthly digest

```text
Generate the monthly operations digest with operation=report and period=previous_month and deliver the HTML, the snapshot JSON, the incidents and anomalies CSV and the recommended actions CSV, then the executive synthesis and the top actions.
```

Tool call:

```json
{"operation": "report", "period": "previous_month"}
```

**Expected:** One report call and four file links, with the executive synthesis, the counts by source and the prioritized actions.

## 2. Last 7 days

```text
Generate the operations digest for the last 7 days with operation=report and period=last_7d.
```

Tool call:

```json
{"operation": "report", "period": "last_7d"}
```

**Expected:** The same four files for the last 7 days.

## 3. High-severity incidents

```text
Use query with view=incidents and severity=high for the last 30 days. Which incidents need attention, with their source and evidence?
```

Tool call:

```json
{"operation": "query", "view": "incidents", "severity": "high", "period": "last_30d"}
```

**Expected:** Only high-severity incidents with source evidence, exact totals and paging.

## 4. Coverage

```text
Use query with view=coverage. Which sources were read completely, which were partial or denied, and which workspaces were included?
```

Tool call:

```json
{"operation": "query", "view": "coverage"}
```

**Expected:** Per-source receipts; a denied source is reported, never shown as zero incidents.

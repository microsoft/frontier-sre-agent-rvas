# Test prompts

In a new chat, type `/agent`, select `infra-ops-live` and send one prompt at a time. Before the tool is configured, every call returns a configuration error and makes no Azure call.

## 1. Monthly report

```text
Use infra-ops-live and infrastructure-operations-report only. Make exactly one call with operation="report", period="previous_month", hosting="all", metric="all" and other defaults, then immediately show all four file downloads and a short summary from the returned window, counts and top review names.
```

Tool call:

```json
{"operation": "report", "period": "previous_month", "hosting": "all", "metric": "all"}
```

**Expected:** One report call and four links (report, resources CSV, signals CSV and snapshot JSON). Missing metrics are Unknown, not zero or healthy, and the coverage is stated.

## 2. Demo window

```text
Use infra-ops-live and infrastructure-operations-report with operation="report" and period="last_24h", and deliver the four files.
```

Tool call:

```json
{"operation": "report", "period": "last_24h"}
```

**Expected:** The same four files for the last 24 hours, with 5-minute bins.

## 3. Review signals

```text
Use query with view=signals and severity=warning for the last 7 days. Which resources need an owner review, with the signal, the source and the observation time?
```

Tool call:

```json
{"operation": "query", "view": "signals", "severity": "warning", "period": "last_7d"}
```

**Expected:** Only warning signals with exact totals and paging; native alerts are kept apart from local review flags.

## 4. Arc extensions

```text
Use query with view=extensions. Which Arc machine extensions failed or differ from the approved baseline?
```

Tool call:

```json
{"operation": "query", "view": "extensions"}
```

**Expected:** Extension metadata as child evidence of each machine (never extra machines), with Unknown when the source is partial; settings are never read.

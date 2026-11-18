# Test prompts

In a new chat, type `/agent`, select `sqlmi-maintenance-advisor` and send one prompt at a time. With no configuration the tool runs in demo mode (simulated data, clearly labelled).

## 1. Full report

```text
Generate the SQL Managed Instance maintenance resilience report for the last 30 days and tell me which applications show errors to users during maintenance.
```

Tool call:

```json
{"operation": "report", "period": "last_30d"}
```

**Expected:** One report call. The answer gives the four download links (HTML, JSON, instances CSV and impact CSV), the short answer, the next maintenance with the applications at risk and the high-priority actions. Demo data is labelled as such.

## 2. Next maintenance

```text
When is the next planned maintenance of our SQL Managed Instances and which applications are at risk?
```

Tool call:

```json
{"operation": "upcoming"}
```

**Expected:** The next planned maintenance from Service Health and the applications without retries that would surface errors; if no Service Health alert exists, the answer says so.

## 3. Quick summary

```text
Give me the KPIs of the last 7 days, the findings and the applications without retries.
```

Tool call:

```json
{"operation": "summary", "period": "last_7d"}
```

**Expected:** Reconfigurations, their average and maximum duration, user-facing errors and the applications without retries, with no files written.

## 4. Demo mode

```text
Run the report in demo mode so I can see what it looks like.
```

Tool call:

```json
{"operation": "report", "data_source": "demo"}
```

**Expected:** The same four files from simulated data, labelled as demo, with no Azure call.

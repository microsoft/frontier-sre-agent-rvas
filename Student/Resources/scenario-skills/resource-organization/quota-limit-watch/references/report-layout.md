# Report layout

This skill renders with the shared generator, tools/report_render.py, from a report_data object the scan tool prints, so the report is one pipe:

```
python tools/quota_scan.py | python tools/report_render.py
```

## report_data this skill emits

- title: "Quota and Limit Watch". subtitle: headroom against Azure quotas and service limits.
- meta: window is the threshold percent, scope is the count of subscriptions scanned, source is "Azure usage endpoints".
- summary_cards: counters near the limit, Critical count (95 percent or higher), subscriptions scanned, regions checked.
- charts: findings by severity, and the tightest counters (utilization percent, coloured by band).
- findings: columns subscription, location, quota, used, limit, utilization, severity. Each row carries a _band equal to its severity, and a numeric sort hint on utilization so the table sorts by tightness.
- method_notes: the threshold used, any usage query that could not be read, and the note that counters with no finite limit are skipped.

## Sections the renderer produces

1. Header with title, threshold, scope, and generation time.
2. Summary cards led by counters near the limit.
3. Overview charts: by severity and the tightest counters.
4. Findings table, sortable and filterable, utilization shown with a severity pill.
5. Method and limits.

Utilization is used divided by limit, as a percent. The tightest counter is the one closest to its limit, not the one with the largest absolute usage.

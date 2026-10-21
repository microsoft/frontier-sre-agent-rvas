# Report layout

This skill renders with the shared generator, tools/report_render.py, from a report_data object the scan tool prints, so the report is one pipe:

```
python tools/alert_hygiene.py | python tools/report_render.py
```

## report_data this skill emits

- title: "Alert Hygiene Review". subtitle: alert noise and tuning over the window.
- meta: window is the range read (1d, 7d, or 30d), scope is the count of subscriptions scanned, source is "Azure Monitor alerts".
- summary_cards: alerts fired, noisy rules, rules analyzed, disabled rules.
- charts: alerts by severity, and the noisiest rules by fire count.
- findings: columns rule, fired, monitor_resolved, user_closed, rapid_resolution, duration_assessed, duration_unknown, duration_assessment_status, unacknowledged, issue, recommendation, severity.
- duration_coverage: report level assessed and unknown duration counts and coverage status. No valid durations means Not assessed; unknown durations reduce overall assessment completeness.
- assessment_status and sources: collection completeness and source links.
- method_notes: the window used, the thresholds, and any scope not assessed.

## Sections the renderer produces

1. Header with title, window, scope, and generation time.
2. Summary cards led by alerts fired and noisy rules.
3. Overview charts: alerts by severity and the noisiest rules.
4. Findings table, sortable and filterable, the finding severity as a coloured pill.
5. Method and limits.

Monitor resolved is condition state, user closed is user response state, and rapid resolution requires timestamps proving at most five minutes. Neither closure nor resolution proves that nobody acted. Unacknowledged is the current New share, not historical evidence of inaction. Collection caps and failed reads are incomplete.

Pending alerts and missing, invalid, timezone naive or reversed timestamps have unknown durations. Rapid resolution is Not assessed when no valid durations exist. Partial duration coverage reports a lower bound over all alerts, with assessed and unknown counts; it never silently presents unknown durations as zero rapid resolutions.

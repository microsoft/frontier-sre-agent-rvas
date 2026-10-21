# Report layout

This skill renders with the shared generator, tools/report_render.py, from a report_data object the scan tool prints, so the report is one pipe:

```
python tools/data_platform_review.py | python tools/report_render.py
```

## report_data this skill emits

- title: "Data Platform Review". subtitle: managed database reliability and resilience.
- meta: window is "Point in time", scope is the count of subscriptions scanned, source is "Azure Resource Graph".
- summary_cards: data services reviewed, services with findings, High findings, total findings.
- charts: findings by severity, and findings by engine (SQL, PostgreSQL, MySQL, Cosmos DB).
- findings: columns resource, engine, subscription, resource_group, check, recommendation, severity. Each row carries a _band equal to its severity.
- method_notes: the note that some overlap with the reliability skill is intentional, that long term retention is checked by hand, and any scope not assessed.

## Sections the renderer produces

1. Header with title, scope, source, and generation time.
2. Summary cards led by services with findings.
3. Overview charts: by severity and by engine.
4. Findings table, sortable and filterable, severity as a coloured pill.
5. Method and limits.

Grouping by engine lets a team route the SQL work and the Cosmos work to the right owners.

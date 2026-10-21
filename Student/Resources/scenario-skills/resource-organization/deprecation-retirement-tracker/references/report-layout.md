# Report layout

This skill renders with the shared generator, tools/report_render.py, from a report_data object the scan tool prints, so the report is one pipe:

```
python tools/deprecation_scan.py | python tools/report_render.py
```

## report_data this skill emits

- title: "Deprecation and Retirement Tracker". subtitle: end of life runtimes, retired tiers, and old platform versions.
- meta: window is "Point in time", scope is the count of subscriptions scanned, source is "Azure Resource Graph".
- summary_cards: deprecations found, retired or end of life (High), categories affected, subscriptions scanned.
- charts: findings by severity, and findings by category (App Service runtime, Retired service, Classic, AKS version, VM OS).
- findings: columns resource, resource_type, category, subscription, deprecated, recommendation, severity. Each row carries a _band equal to its severity.
- method_notes: the Kubernetes floor used, the reminder to corroborate dates against Azure Service Health, and any scope not assessed.

## Sections the renderer produces

1. Header with title, scope, source, and generation time.
2. Summary cards led by retired and end of life counts.
3. Overview charts: by severity and by category.
4. Findings table, sortable and filterable, severity as a coloured pill.
5. Method and limits.

Category groups the backlog into workstreams, so a team can plan the App Service runtime moves separately from the database migrations.

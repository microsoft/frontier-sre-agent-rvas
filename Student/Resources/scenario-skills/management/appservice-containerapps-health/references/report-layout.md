# Report layout

This skill renders with the shared generator, tools/report_render.py, from a report_data object the scan tool prints, so the report is one pipe:

```
python tools/appservice_review.py | python tools/report_render.py
```

## report_data this skill emits

- title: "App Service and Container Apps Health". subtitle: web tier scaling, probes, and transport security.
- meta: window is "Point in time", scope is the count of subscriptions scanned, source is "Azure Resource Graph".
- summary_cards: resources with findings, High findings, check definitions and subscriptions scanned. Definition count is not successful resource coverage.
- charts: findings by severity, and findings by category (App Service, App Service plan, Container Apps).
- findings: columns resource, category, subscription, resource_group, check, recommendation, severity. Each row carries a _band equal to its severity.
- assessment_status: Complete, Partial or Not assessed. Missing configuration is Unknown, never a pass.
- sources: titled official documentation URLs.
- method_notes: per container and probe type coverage, portal default limits, missing fields and scope not assessed.

## Sections the renderer produces

1. Header with title, scope, source, and generation time.
2. Summary cards led by resources with findings.
3. Overview charts: by severity and by category.
4. Findings table, sortable and filterable, severity as a coloured pill.
5. Method and limits.

Category separates the App Service work from the Container Apps work so each goes to the right owner.

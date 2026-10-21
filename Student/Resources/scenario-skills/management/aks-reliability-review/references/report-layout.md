# Report layout

This skill renders with the shared generator, tools/report_render.py, from a report_data object the scan tool prints, so the report is one pipe:

```
python tools/aks_review.py | python tools/report_render.py
```

## report_data this skill emits

- title: "AKS Reliability Review". subtitle: Kubernetes cluster reliability and operational best practices.
- meta: window is "Point in time", scope is the count of subscriptions scanned, source is "Azure Resource Graph".
- summary_cards: clusters reviewed, clusters with findings, High findings, checks evaluated.
- charts: findings by severity, and findings by subscription.
- findings: columns cluster, subscription, resource_group, check, recommendation, severity. Each row carries a _band equal to its severity.
- assessment_status: Complete, Partial or Not assessed. Unknown lifecycle or applicability prevents Complete.
- sources: titled official URLs.
- method_notes: lifecycle evidence requirements, support plan and patch limits, region applicability and scope not assessed. There is no permanent supported minor floor.

## Sections the renderer produces

1. Header with title, scope, source, and generation time.
2. Summary cards led by clusters with findings.
3. Overview charts: by severity and by subscription.
4. Findings table, sortable and filterable, severity as a coloured pill.
5. Method and limits.

A cluster with several gaps appears as several rows, one per check, so a team can work the list item by item.

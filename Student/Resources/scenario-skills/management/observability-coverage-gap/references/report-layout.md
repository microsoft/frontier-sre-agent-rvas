# Report layout

This skill renders with the shared generator, tools/report_render.py, from a report_data object the scan tool prints, so the report is one pipe:

```
python tools/observability_gap.py | python tools/report_render.py
```

## report_data this skill emits

- title: "Observability Coverage Gap". subtitle: diagnostic routing and enabled alert candidates.
- meta: window is "Point in time", scope is the count of subscriptions scanned, source is "Azure Resource Graph".
- summary_cards: configuration gaps, observed diagnostic routing gaps (Unknown when collection is incomplete), missing alert routing candidates, resources scanned.
- charts: observed configuration gaps by type and subscription. No local destination absence findings.
- findings: columns resource, resource_type, subscription, resource_group, missing, recommendation, severity. Each row carries a _band equal to its severity.
- assessment_status and sources: collection completeness and source links.
- method_notes: resource API diagnostic coverage, caps, failed reads and remaining validation.

## Sections the renderer produces

1. Header with title, scope, source, and generation time.
2. Summary cards led by resources with gaps.
3. Overview charts: gaps by type and by subscription.
4. Findings table, sortable and filterable, severity as a coloured pill.
5. Method and limits.

A resource missing more than one piece of wiring appears once, with all missing pieces listed and the severity set to the highest among them.

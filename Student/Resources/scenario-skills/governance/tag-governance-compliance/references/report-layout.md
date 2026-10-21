# Report layout

This skill renders with the shared generator, tools/report_render.py, from a report_data object the scan tool prints, so the report is one pipe:

```
python tools/tag_compliance.py | python tools/report_render.py
```

## report_data this skill emits

- title: "Tag Governance Compliance". subtitle: resources against the required tag standard.
- meta: window is the required tags list, scope is the count of subscriptions scanned, source is "Azure Resource Graph".
- summary_cards: compliance percent, non compliant resources, resources missing an owner, resources scanned.
- charts: missing by tag (one bar per required tag), and non compliance by subscription.
- findings: columns resource, resource_id, resource_type, subscription, resource_group, missing_tags, recommendation, severity. Each row carries a _band equal to its severity.
- method_notes: required names, case insensitive name matching only, nonblank value requirement, support exclusions and scope limits.
- assessment_status: Complete, Partial or Not assessed. sources: objects with title and url.
- unassessed_resources: ids and reasons for unknown tag support. excluded_resources: verified unsupported types and their ids.

## Sections the renderer produces

1. Header with title, the required tags, scope, and generation time.
2. Summary cards led by compliance percent.
3. Overview charts: missing by tag and by subscription.
4. Findings table, sortable and filterable, severity as a coloured pill.
5. Method and limits.

Compliance percent divides assessed resources with every required tag and a nonblank value by all assessed resources. Unknown support is Not assessed, verified unsupported types are excluded, and empty or inaccessible inventory never yields 100 percent. The metric does not certify allowed values, naming or policy compliance.

## Sources

- [Owned checks and tag semantics sources](checks-catalog.md)

# Report layout

This skill renders with the shared generator, tools/report_render.py, from a report_data object the scan tool prints, so the report is one pipe and matches the look and feel of every other report in this repository:

```
python tools/network_exposure.py | python tools/report_render.py
```

## report_data this skill emits

- title: "Network Exposure Review". subtitle: configuration review, not verified internet reachability.
- meta: window is "Point in time", scope is the count of subscriptions scanned, source is "Azure Resource Graph".
- summary_cards: distinct resource ids to review, critical configurations, public access settings, subscriptions represented in matching rows.
- charts: findings by severity, and findings by exposure type (open ports, storage public access, PaaS public access).
- findings: columns resource, resource_id, exposure, subscription, resource_group, detail, recommendation, severity. NSG rows also retain rule_id when supplied, source_coverage and reachability=Not assessed.
- method_notes: the internet source definition, and any scope not assessed.
- assessment_status: Partial for configuration reviews with effective reachability unknown, or Not assessed for empty unknown scope. sources: objects with title and url.

## Sections the renderer produces

1. Header with title, scope, source, and generation time.
2. Summary cards led by critical exposures.
3. Overview charts: by severity and by exposure type.
4. Findings table, sortable and filterable, severity as a coloured pill.
5. Method and limits.

Severity ranks review configuration, not confirmed exposure. Broad management or all port Allow rules are Critical; database Allow rules are High. Unknown sources, anonymous blob permission and PaaS public endpoint settings are Medium review items until firewall, effective rule and route evidence is available.

## Sources

- [Owned checks and Microsoft network sources](checks-catalog.md)

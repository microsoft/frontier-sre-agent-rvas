# Report layout

This skill renders with the shared report generator, tools/report_render.py, which builds one self contained HTML file (inline CSS, CSS bar charts, no CDN) from a report_data object read as JSON on standard input. The scan tool prints that object, so the whole report is one pipe:

```
python tools/reliability_scan.py | python tools/report_render.py
```

## report_data this skill emits

- title: "Reliability Posture Review". subtitle: the Well-Architected reliability pillar.
- generated_for: a scope label (tenant or agent name).
- meta: window is "Point in time", scope is the count of subscriptions scanned, source is "Azure Resource Graph".
- summary_cards: resources with findings, Critical and High count, signals evaluated, subscriptions scanned.
- charts: findings by severity (bars coloured by band), and findings by subscription.
- findings: columns resource, resource_type, subscription, resource_group, issue, recommendation, severity. Each row carries a _band equal to its severity so the renderer colours the pill and the row edge.
- method_notes: any subscription or signal not assessed, and the reminder that backup protection and live idle metrics are covered by other skills.

## Sections the renderer produces

1. Header with the title, scope, source, and generation time.
2. Summary cards.
3. Overview charts: by severity and by subscription.
4. Findings table, sortable by any column and filterable by free text, severity shown as a coloured pill.
5. Method and limits from method_notes.

No termination candidates are passed here, so the renderer omits the action candidates table. Severity, not cost, is the ranking axis for this skill.

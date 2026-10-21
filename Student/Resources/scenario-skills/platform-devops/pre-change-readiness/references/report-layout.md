# Report layout

This skill renders with the shared generator, tools/report_render.py, from a report_data object the scan tool prints, so the report is one pipe and matches the look and feel of every other report in this repository:

```
python tools/readiness_check.py "<subscription id>" [resource group] | python tools/report_render.py
```

## report_data this skill emits

- title: "Pre-Change Readiness". subtitle: the go, caution, or no-go for the target scope.
- meta: window is "Point in time", scope is the target subscription and resource group, source is "Azure Resource Graph and usage".
- summary_cards: the overall verdict, and the verdict for Reliability, Exposure, and Capacity, each as a card value with the count of findings as the sub label.
- charts: findings by category, and findings by severity.
- findings: columns category, resource, resource_group, issue, recommendation, severity. Each row carries a _band equal to its severity.
- assessment_status: Complete, Partial or Not assessed, independent of finding counts.
- assessments: per check and capacity endpoint state; missing coverage blocks GO.
- sources: titled official source URLs.
- method_notes: the verdict rule, scope checked and the limits of configuration and capacity evidence.

## Sections the renderer produces

1. Header with title, scope, source, and generation time.
2. Summary cards: the overall verdict first, then the three category verdicts.
3. Overview charts: by category and by severity.
4. Findings table, sortable and filterable, severity as a coloured pill.
5. Method and limits.

The verdict cards are the headline. The findings table lists exactly what to clear to move a caution or no-go to go.

INCOMPLETE must be presented as blocking GO. No findings does not mean ready when reads failed or the scope was empty. A GO applies to the listed configuration checks only, not overall change approval.

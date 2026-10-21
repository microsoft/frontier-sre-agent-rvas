# Report layout

This skill renders with the shared generator, tools/report_render.py, from a report_data object the assessment tool prints, so the scorecard is one pipe and matches the look and feel of every other report in this repository:

```
python tools/waf_assess.py | python tools/report_render.py
```

## report_data this skill emits

- title: "Well-Architected Review". subtitle: custom 13 check indicator, not an official Microsoft Well Architected assessment or score.
- meta: window is "Point in time", scope is the count of subscriptions scanned, source is "Azure Resource Graph".
- summary_cards: one card per pillar, with custom score, rating and read coverage. Partial coverage is visible beside the score.
- assessment_status: Complete, Partial or Not assessed. Empty applicable scope is Not assessed.
- coverage: definitions, read, skipped and unknown resource counts. Unknown and failed checks never enter the pass denominator.
- sources: titled official documentation URLs.
- charts: pillar scores (one neutral bar per pillar, matching the value charts elsewhere), and findings by severity.
- findings: columns pillar, check, applicable, failing, pass_rate, recommendation, severity. Each row carries a _band equal to its severity.
- method_notes: the scoring method (weighted pass ratio), the ratings scale, and any check skipped for lack of access.

## Sections the renderer produces

1. Header with title, scope, source, and generation time.
2. Summary cards: the five pillar scores with their ratings.
3. Overview charts: pillar scores and findings by severity.
4. Findings table, sortable and filterable, severity as a coloured pill, tagged by pillar.
5. Method and limits.

The pillar score cards and the pillar score chart are the headline. The findings table explains what pulled each score down, and each check names the deep dive skill that holds the full detail.

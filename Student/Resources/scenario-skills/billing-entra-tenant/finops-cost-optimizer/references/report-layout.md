# Report layout

The generate_report tool builds one self contained HTML file with no external assets and no CDN. All styling is inline CSS and every chart is drawn with plain HTML and CSS bars, so the report opens fully styled offline. It writes the file to the file store. Pass it the data below.

## Sections

1. Header: title, generation date, the analysis window (30 days), the scope, and the cost source (CostManagement or the Consumption fallback).
2. Summary cards: analyzed spend, estimated monthly savings, savings as a percent of spend, the termination candidate count, and the recommendation count.
3. FinOps overview: spend by subscription, spend by resource group, and estimated monthly savings by dimension, each as horizontal CSS bars with the value labelled.
4. Termination candidates: candidate summary cards by confidence band, a top candidates chart, a how to read the confidence score panel, and a filterable table. The table filters by subscription, confidence band, and free text, and every row carries a copyable az delete command. Rendered only when candidates are present.
5. Savings recommendations: every finding sorted by priority score, with resource, dimension, current, proposed, monthly saving, risk, and priority band. Sortable and filterable.
6. Method and limits: how spend, savings, and confidence are used, and any heuristic only note when metrics or Activity Logs were not readable.

## Input shape for generate_report

Pass a report_data object with:

- generated_for: a label for the scope, for example the tenant or agent name.
- window_days and data_source.
- totals: analyzed_spend, estimated_monthly_savings, currency, savings_reconciled. Generate one report per explicit currency; conflicting row currencies are rejected.
- reconciliation_notes: required before showing aggregate savings. Explain the common scope, cost basis, time window, Advisor and candidate deduplication, and selected alternatives among reservations, savings plans, rightsizing and scheduling.
- assessment_status: Complete, Partial or Not assessed. sources: objects with title and url. notes and collection_failures: scope and collection limits.
- subscriptions: a list of objects with name and cost for the selected subscriptions.
- resource_groups: a list of objects with name and cost for the top resource groups.
- savings_by_dimension: a mapping of dimension name to estimated monthly saving.
- findings: a list, each with resource, dimension, current, proposed, monthly_saving, risk, priority_score, and priority_band.
- candidates: the review candidates, each with resource, resource_type, resource_id, subscription, subscription_id, resource_group, location, monthly_saving, saving_note, confidence, band, reason, next_step, optional operator requested delete_command, and optionally excluded and exclusion_reason. See references/idle-detection.md. The report derives the band from confidence if band is omitted.

The renderer no longer builds a delete command from a resource id. Include an
operator requested command only when appropriate for the intended audience.
Confidence is a review ranking, never authority to delete.

Exports use the shared `sanitized_copy` policy by default. The optional
`--include-identifiers` flag explicitly retains identifiers for an approved
internal audience; credential filtering still applies. Review the sanitized
draft before customer sharing. Local analytical evidence retains full ids.

Subscription costs must sum to analyzed_spend for the same selected baseline.
Resource group costs are a drilldown, never an additional baseline. Candidate
estimates and commitment alternatives remain individual opportunities, not a
second realizable savings total. Aggregate savings are displayed only with
`savings_reconciled=true` and reconciliation_notes; otherwise the total is
Not reconciled. Savings percentage uses analyzed spend normalized to 30 days
from window_days and is not a claim of invoice savings.

## Sources

- [Query rows and pagination](https://learn.microsoft.com/javascript/api/@azure/arm-costmanagement/queryproperties)
- [Cost access and scope](https://learn.microsoft.com/azure/cost-management-billing/costs/assign-access-acm-data)

## Accessibility

- Use clear band colours with a text label next to every colour, so meaning never depends on colour alone.
- Give every chart bar a visible numeric value.
- Keep the underlying numbers in the tables next to the charts.
- Keep text and background contrast at WCAG AA or better.

## Styling and interactivity

- The report is fully self contained: inline CSS, CSS bar charts, and a small block of embedded JavaScript with no external library. It renders the same online or offline.
- The termination candidates table filters by subscription, confidence band, and free text, and each delete command has a copy button.
- The savings recommendations table is sortable (click a column header to toggle ascending or descending) and filterable (type in the box above the table).

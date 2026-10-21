# Ranking method

The skill ranks in two phases. Spend decides where to look. Savings decides what to fix first.

## Phase 1: Narrow scope by spend

Cost basis:

- Metric: amortized cost. Reservation and savings plan purchases are spread across the benefit period, not shown as a lump on the purchase day.
- Window: the last 30 days.
- Grouping: by subscription, then by resource group within each selected subscription.
- Partition first by currency and cost basis. Never compare nominal spend across currencies. Consumption fallback is usage detail actual cost, not the amortized baseline; rank it separately and flag Partial.

Selection rule (floor and cap) for a set of N items:

- selected = min(N, max(minimum, ceil(N * top_percent / 100)))
- Subscriptions: top_percent = 10, minimum = 3.
- Resource groups: top_percent = 10, minimum = 5.

This keeps the top decile for large estates while guaranteeing a usable set for small ones. Examples:

- 3 subscriptions: select 3 (the floor applies).
- 6 subscriptions: select 3.
- 200 subscriptions: select 20.
- 6 resource groups: select 5.

The cost_rank tool applies this rule and returns the ranked items with a selected flag.

## Phase 2: Rank findings by savings

After waste detection, score every finding:

Priority Score = (Value x Estimated Monthly Savings) / (Risk x Implementation Days)

- Value: 1 to 10, how strategically useful the change is.
- Risk: 1 to 10, the chance of a negative effect. Higher risk lowers the score.
- Implementation Days: estimated effort in days, minimum 0.5.

Bands:

- High priority: score above 20.
- Medium priority: score 5 to 20.
- Low priority: score below 5.

Sort findings by priority score, highest first.

## Confidence to terminate: idle candidates

Termination candidates use a second, simpler axis. Savings still matters, but
each candidate carries a review evidence score from 0 to 100 rather than a
priority score. The historic field name is confidence to terminate; its value
does not establish safety or grant permission to delete.

- Very high, 90 or above: unattached and old enough to look abandoned.
- High, 70 to 89: stronger review evidence, not permission to delete.
- Medium, 50 to 69: the signal is real but recent or ambiguous.
- Low, below 50: likely disaster recovery or shared infrastructure; do not terminate without deeper validation.

The full scoring rubric, including the age and naming adjustments that lower the
score for disaster recovery, shared network, and hybrid resources, is in
references/idle-detection.md. Sort candidates by confidence, highest first.

## What cost_rank returns

A JSON object with:

- lookback_days and the cost currency.
- data_source: CostManagement or Consumption (the fallback).
- subscriptions: every visible subscription with id, name, total_cost, rank, and selected.
- selected_subscriptions: the ids chosen in phase 1.
- resource_groups: for each selected subscription, the ranked resource groups with name, cost, rank, and selected.
- notes: any warnings, for example mixed currencies or a fallback data source.

Additional fields: `assessment_status`, `sources`, per subscription `cost_basis`,
`data_source`, `totals_by_currency` and `assessment_status`, plus `ranking_groups`
keyed by currency and cost basis. Subscription `total_cost` is null for mixed
currencies or an unread source. Ranking lives in each partition rather than one
global subscription order. Resource group rows retain currency and partition rank.
Selected subscription ids are the union of partition selections.

Cost Management follows `properties.nextLink`. A page cap with a remaining
continuation fails explicitly, so incomplete pages are never presented as a
complete total. Empty unknown subscription scope is Not assessed.

## Sources

- [Cost query continuation and rows](https://learn.microsoft.com/javascript/api/@azure/arm-costmanagement/queryproperties)
- [Consumption usage records](https://learn.microsoft.com/rest/api/consumption/usage-details/list)

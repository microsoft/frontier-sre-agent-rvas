# Checks catalog

Seven cost optimization dimensions. For each finding record: resource id, dimension, current configuration, proposed change, estimated monthly saving, risk rating, and evidence. All commands are read only and run within the agent's existing access. If a command returns access denied or authorization failed, the skill may ask the user to grant temporary access to that scope, but it never assigns roles itself. If the user declines, skip that check for that scope, record it as not assessed because of insufficient access, and move on.

HTTP collectors use `shared\tools\azure_http.py` and its bundled governance policy for approved HTTPS hosts, explicit timeouts, disabled redirects and bounded transient retries. Authorization failures are not retried. Bundle the shared tools and policy with deployed collectors; missing shared tools fail closed.

Use live retail prices for target estimates and current cost from a reconciled baseline. Record currency, source date, quantity, billing hours, estimate horizon and cost basis. Current negotiated or amortized cost and target retail price are not automatically comparable. Mark the difference uncertain unless normalized to the same scope, window and basis.

Two of these dimensions, orphaned resources (2) and idle resources (4), also feed the termination candidates table. Enumerate those with Azure Resource Graph and score each one by confidence to terminate using references/idle-detection.md. The other dimensions produce savings recommendations.

## 1. Azure Advisor cost baseline

Start here. Advisor already finds many opportunities.

- List: az advisor recommendation list --category Cost --subscription <id>
- Capture each recommendation's impacted resource, problem, and the saving Advisor reports.
- Treat Advisor savings as the baseline and reconcile with your own findings to avoid double counting.
- Deduplicate by resource and change, not only recommendation id. Candidate cleanup, rightsizing, scheduling and commitment savings on the same usage can overlap.

Risk: low. Evidence: the Advisor recommendation id and its reported saving.

## 2. Orphaned resources

Resources that cost money with nothing attached. Enumerate these across every accessible subscription with Azure Resource Graph, not per subscription list calls, using the queries in references/idle-detection.md. Each one becomes a termination candidate with a confidence to terminate score and an operator ready delete command.

- Unattached managed disks.
- Unassociated public IPs.
- Orphan network interfaces.
- Standalone snapshots, scored by age.
- Empty App Service plans.
- Public load balancers with no backend members (heuristic, scored low).

Saving: the full cost of the orphaned resource, priced as a lower bound per references/idle-detection.md. Risk: reflected in the confidence score, which is lowered for disaster recovery, shared network, and hybrid naming. Evidence: the empty association field plus age.

## 3. Commitment coverage

Reservations and savings plans for steady state usage.

- Call the commitment_recommendations tool. It returns reservation recommendations and, on a best effort basis, savings plan recommendations, each with the projected saving.
- Cross check against current coverage so you do not over recommend.
- Treat reservation and savings plan recommendations as potentially overlapping alternatives. Preserve term, currency, scope, quantity and recommendation horizon. The helper deliberately returns no combined net savings total. Even recommendations of one kind can be alternative terms or scopes, so do not sum them without reconciliation.

Saving: the projected net saving from the recommendation. Risk: medium (commitment term). Evidence: the recommendation payload and the usage that backs it.

## 4. Idle or underused resources

Resources that run but do little. Requires metrics.

- Pull Azure Monitor metrics over a 30 day window: az monitor metrics list --resource <id> --metric "Percentage CPU" --interval PT1H --start-time <iso> --end-time <iso>
- Treat low CPU and throughput as an idle review signal, not proof. Confirm metric coverage and gaps, schedule, seasonal use, workload dependencies and the owner before recommending a change.
- Apply the same idea to gateways and load balancers with negligible throughput.
- Deallocated virtual machines found through Azure Resource Graph also become termination candidates; score and price them with references/idle-detection.md.

Saving: deallocate, or resize to a smaller SKU priced with the azure-pricing approach. Risk: medium (confirm the workload is not scheduled or seasonal). Evidence: the metric averages and the window.

## 5. Storage optimization

- Redundancy: flag GRS or ZRS accounts where LRS would meet the requirement. az storage account list --subscription <id> --query "[].{name:name,sku:sku.name}"
- Lifecycle: flag accounts with no lifecycle management policy that hold cool or rarely accessed blobs.
- Stale snapshots and old disk snapshots: az snapshot list --subscription <id>

Saving: redundancy tier delta, lifecycle tiering to cool or archive, snapshot deletion. Risk: low to medium. Evidence: the SKU, the missing policy, or the snapshot age.

## 6. Log Analytics optimization

- Retention beyond need: az monitor log-analytics workspace list --subscription <id>, then review retentionInDays.
- Ingestion volume: identify high ingestion tables and whether a commitment tier or basic logs would cost less.

Saving: shorter retention, a commitment tier, or moving verbose tables to basic logs. Risk: low to medium (retention may be a compliance requirement, confirm before recommending). Evidence: retention setting and ingestion volume.

## 7. Dev and test scheduling

- Use names and tags to identify possible nonproduction workloads, then confirm the environment and intended operating hours with the owner. Naming alone never establishes nonproduction.
- Flag virtual machines and other compute that run 24 by 7 but are only used in working hours.

Saving: a scheduling estimate against confirmed working hours and the same compute baseline. Risk depends on workload requirements. Evidence: owner confirmed environment, schedule and observed usage. Do not add this estimate to a termination or overlapping rightsizing opportunity.

## Scope, completeness and aggregation

Approve subscriptions before collection. Cost Management follows `properties.nextLink`; Consumption and commitment page caps fail explicitly if a continuation remains. Consumption fallback is not amortized cost. Failed sources are Partial or Not assessed, not zero spend or zero savings. Rank separately by currency and cost basis. Never total currencies without explicit conversion evidence.

The report requires one explicit currency and a subscription baseline matching analyzed spend. A realizable savings total additionally requires `totals.savings_reconciled=true` and `reconciliation_notes` explaining deduplication, alternatives, estimate windows and cost basis. Otherwise only individual opportunities are shown.

## Sources

Verified against Microsoft Learn during this correction:

- [Cost Management query properties, including nextLink](https://learn.microsoft.com/javascript/api/@azure/arm-costmanagement/queryproperties)
- [Cost Management access](https://learn.microsoft.com/azure/cost-management-billing/costs/assign-access-acm-data)
- [Consumption usage details](https://learn.microsoft.com/rest/api/consumption/usage-details/list)
- [Reservation recommendations](https://learn.microsoft.com/rest/api/consumption/reservation-recommendations/list)
- [Benefit recommendations](https://learn.microsoft.com/rest/api/cost-management/benefit-recommendations/list)

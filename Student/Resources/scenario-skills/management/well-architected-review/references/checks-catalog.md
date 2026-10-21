# Checks catalog

These 13 curated configuration checks produce a custom indicator across five pillars. This is not the official Microsoft Well Architected Review or its scoring methodology, and it is not a certification or complete workload assessment.

## Scoring

- Each check has a severity, which sets its weight: Critical 4, High 3, Medium 2, Low 1.
- For each check, known equals applicable minus unknown. Pass ratio equals (known minus failing) divided by known. A check with no known applicable resources has no numerical score.
- Failed collection is Not assessed and excluded, not passing. Scores display read coverage; JSON reports skipped definitions and unknown resources. A high score with missing coverage must be presented as Partial.
- Pillar score equals 100 times the weighted average of its checks' pass ratios, rounded. Ratings: Excellent 90 and above, Good 75 to 89, Fair 50 to 74, Poor below 50.

## Reliability

- Virtual machines with no availability zone and no availability set (High). Deep dive: reliability-posture-review.
- Locally redundant storage accounts (Medium).
- Premium or Business Critical SQL databases without zone redundancy (High).
- Single region Cosmos DB accounts (Medium).

## Security

- Storage accounts allowing anonymous blob access (High). Deep dive: network-exposure-review.
- Platform services with public network access enabled (Medium).
- Key Vaults without purge protection (Medium). Deep dive: identity-access-hygiene for the wider posture.

## Cost Optimization

- Unattached managed disks (Medium). Deep dive: finops-cost-optimizer.
- Unassociated public IP addresses (Low).

## Operational Excellence

- Resources with no owner tag (Medium). Deep dive: tag-governance-compliance.
- AKS clusters outside verified lifecycle dates (Medium). A versioned snapshot checked within 30 days must match the cluster minor and standard or LTS plan. Missing evidence or unconfirmed LTS entitlement is Unknown, excluded from the numerical denominator. Deep dive: deprecation-retirement-tracker.

## Performance Efficiency

- App Service plans on Free, Shared, or Basic tiers (Medium). Deep dive: appservice-containerapps-health.
- Container Apps that cannot scale out (a single maximum replica) (Low).

## Extending

Add a check by appending to the list in tools/waf_assess.py with its pillar, severity, recommendation, and a Resource Graph query that returns applicable and failing counts. Keep the set small and high signal; the detailed skills are where breadth belongs.

## Evidence boundary

AKS metadata follows the shared lifecycle helper schema: `schema_version=1`, ISO `checked_at`, and `entries` containing `service=aks`, exact `version=major.minor`, `support_plan=standard` or `lts`, ISO `support_end`, and official HTTPS `source`. Set `SRE_LIFECYCLE_EVIDENCE` to that operator verified JSON file. Missing dates, evidence older than 30 days and unmatched entries are Unknown. The helper does not fetch or independently verify source contents. Do not invent dates from month only tables.

Lifecycle Unknown reasons are retained in report method notes. An unconfigured snapshot is distinct from a configured file that is missing, unreadable, malformed, invalid or stale. Repair the reported evidence problem and rerun; none of these states establish a passing support assessment.

The public network access check uses engine specific nested network fields for PostgreSQL and MySQL. Missing values are Unknown. VM zone or availability set membership cannot establish workload instance redundancy. Resource Graph configuration does not measure RTO, RPO, performance under load, effective security controls or live failover.

## Sources and validation

- [Microsoft Well Architected Framework](https://learn.microsoft.com/en-us/azure/well-architected/).
- [AKS lifecycle](https://learn.microsoft.com/en-us/azure/aks/supported-kubernetes-versions).
- [LTS plans and patch limits](https://learn.microsoft.com/en-us/azure/aks/long-term-support), checked 2026-10-21.

Tests are offline regressions. No estate, official assessment or live API responses were validated.

# Evidence collection and analysis

## Collection

### 1. Resource denominator and tags

Build eligible resources for each component from the approved coverage policy. A resource need not be eligible for all six checks.

```azurecli
az resource list --subscription "<subscription_id>" --output json
```

### 2. Lock coverage

Reconstruct inherited protection by exact scope ancestry; repeat group reads and direct resource reads where required. Deduplicate lock IDs.

```azurecli
az lock list --subscription "<subscription_id>" --output json
az lock list --subscription "<subscription_id>" --resource-group "<resource_group>" --output json
```

### 3. Enabled alert coverage

Page using --skip-token from skipToken. Evaluate enabled state and actual target scopes/criteria, not simply one rule anywhere in the subscription.

```azurecli
az graph query --subscriptions "<subscription_id>" --first 1000 -q "Resources | where type in~ ('microsoft.insights/metricalerts','microsoft.insights/scheduledqueryrules','microsoft.insights/activitylogalerts') | project id, name, type, resourceGroup, properties" --output json
```

### 4. Diagnostic settings for eligible targets

Repeat per eligible resource. Check required enabled categories or category groups and valid destination references. Presence alone does not prove delivery.

```azurecli
az monitor diagnostic-settings categories list --subscription "<subscription_id>" --resource "<resource_id>" --output json
az monitor diagnostic-settings list --subscription "<subscription_id>" --resource "<resource_id>" --output json
```

### 5. Policy and Defender evidence

Preserve evaluated resource counts, exempt/unknown states and score identity. Use the classic Azure secure score returned by this API, not the separate risk based Defender portal model.

```azurecli
az policy state summarize --subscription "<subscription_id>" --output json
az security secure-scores list --subscription "<subscription_id>" --output json
```

## Analysis rules

1. Compute component ratios from eligible assessed denominators: compliant tags 20 percent, effective locks 15 percent, required enabled alert coverage 20 percent, qualifying diagnostics 15 percent, policy compliance 15 percent and classic Defender score 15 percent.
2. For tags, locks, alerts and diagnostics count fully passing resources divided by eligible resources under coverage_policy. Expand alert scope or tag based criteria before counting; diagnostic settings must include required categories and a valid destination.
3. For policy use compliant divided by compliant plus noncompliant evaluated eligible resources, with exemptions and unknown states separately listed. For Defender use returned current/max only when max is positive and the selected initiative is identified.
4. Calculate total score = 100 * sum(weight * component_ratio) only when all applicable components are assessed. For unavailable components provide a known contribution lower bound and potential upper bound, but total score null; do not renormalize missing evidence into a pass.
5. If a component has no eligible resources, require a documented customer policy for not applicable weighting; otherwise keep the aggregate unassessed. This is a customer hygiene index, not an official Azure score.
6. For complete totals below 70 rank improvements by lost weighted points and action effort. For incomplete totals prioritize evidence gaps before score based conclusions.

## Known limits

- This composite index is not an official Azure compliance or security score and depends on the agreed coverage policy.
- The classic Azure secure score differs from the risk based Cloud Secure Score, and diagnostic configuration does not establish successful log delivery.

## Expected validation cases

- Healthy: every component ratio is 1 with full coverage and produces 100.
- Finding: tag ratio 0 with every other ratio 1 produces 80 and identifies the lost 20 points.
- Denied or missing: unavailable Defender score leaves total null with bounds 85 to 100 when the other five components all pass.

## Sources

- [Classic secure score read API through CLI](https://learn.microsoft.com/en-us/cli/azure/security/secure-scores?view=azure-cli-latest) (consulted 2026-10-21).
- [Secure score model distinctions](https://learn.microsoft.com/en-us/azure/defender-for-cloud/secure-score-security-controls) (consulted 2026-10-21).
- [Inherited lock evaluation](https://learn.microsoft.com/en-us/azure/azure-resource-manager/management/lock-resources) (consulted 2026-10-21).
- [Alert inventory and paging](https://learn.microsoft.com/en-us/cli/azure/graph?view=azure-cli-latest) (consulted 2026-10-21).

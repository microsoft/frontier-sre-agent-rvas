# Evidence collection and analysis

## Collection

### 1. Traverse only the approved hierarchy and enumerate assignments

Verify root to leaf chains, intersect discovered descendants with the exact allowlist and explicitly read every approved ancestor, including tenant root management group when approved. Derive $CONTEXT_SUB from the approved branch. Page all listings, honor Retry-After, deduplicate full assignment IDs and keep each assignment's actual scope. Unapproved or unreadable ancestors must appear in coverage gaps.

```powershell
foreach ($MG in $APPROVED_MGS) {
 az account management-group show --name $MG --expand --recurse --output json
}
foreach ($SCOPE in $APPROVED_SCOPES) {
 az policy assignment list --subscription $CONTEXT_SUB --scope $SCOPE --disable-scope-strict-match true --output json
 az policy exemption list --subscription $CONTEXT_SUB --scope $SCOPE --output json
}
```

### 2. Resolve exact references and compliance context

GET every unique referenced policy or initiative at its actual scope and effective version. Expand initiative policyDefinitions and parameter mappings. Record 403 unknown separately from authorized 404 missing. Capture metadata deprecated or preview and version selectors, not invented lifecycle fields. Do not trigger evaluations.

```powershell
az rest --method get --url "https://management.azure.com$DEFINITION_ID`?api-version=2023-04-01" --output json
foreach ($SUB in $SUBS) {
 az policy state list --subscription $SUB --all --output json
}
```

## Analysis rules

1. Canonicalize definition or initiative version, resolved parameters, effective effects, enforcement mode, selectors, exclusions and exemptions before comparing ancestor and child assignments. Same definition ID alone is only a redundancy candidate.
2. Call redundancy verified only where applicable resource sets and intended behavior are genuinely duplicated; a child with narrower parameters or different exemption intent may be deliberate.
3. Evaluate actual conditions and constraints cumulatively. Audit plus deny, or deny plus deployIfNotExists, is not inherently a conflict or shadowing. Check whether the deployment template or modify operations would violate another applicable deny condition.
4. For simple allowed value constraints compute intersections over overlapping scopes; disjoint required sets can establish contradiction. Complex unsupported expressions remain potential conflicts requiring fixture or engine evidence.
5. Classify references as broken only on authorized 404 or verified unavailable effective version, and deprecation separately from deletion. Denied definition reads remain unknown.
6. Compare effect Disabled, DoNotEnforce, permissive allowedValues, initiative mappings and overrides with approved intent, not a guessed enforcement preference.
7. Summarize total unique assignments, verified redundancy groups, actual conflicts and uncertain candidates separately, with remove, consolidate or fix recommendations but no changes.

## Known limits

- A complete management group assessment is impossible when any relevant ancestor or branch is unapproved or unreadable.
- Arbitrary Azure Policy expressions are not safely reduced to effect labels or a universal local constraint solver.

## Expected validation cases

- Healthy: audit and deny overlap intentionally and are not counted as a conflict.
- Finding: two applicable deny assignments require incompatible allowed locations after defaults and exemptions are applied.
- Denied or missing: referenced definition returns 403 and remains unknown, while an authorized 404 is recorded as a broken reference.

## Sources

- [Independent cumulative policy evaluation](https://learn.microsoft.com/en-us/azure/governance/policy/concepts/effect-basics) (consulted 2026-10-21).
- [Applicable assignment scope and versions](https://learn.microsoft.com/en-us/cli/azure/policy/assignment?view=azure-cli-latest) (consulted 2026-10-21).
- [Exemption applicability and scope](https://learn.microsoft.com/en-us/azure/governance/policy/concepts/exemption-structure) (consulted 2026-10-21).

# Evidence collection and analysis

## Collection

### 1. Enumerate every approved ancestor and target

Use management group parent metadata to verify the approved ancestor chain; do not expand into unapproved siblings. Enumerate target and every ancestor explicitly, not only current subscription scope. Follow CLI next-token or REST nextLink, deduplicate by full ID and honor Retry-After. An inaccessible or unapproved ancestor makes effective coverage Partial.

```powershell
foreach ($MG in $APPROVED_MGS) {
 az account management-group show --name $MG --output json
}
foreach ($ANCESTOR in $APPROVED_SCOPES) {
 az policy assignment list --subscription $SUB --scope $ANCESTOR --disable-scope-strict-match true --output json
 az policy exemption list --subscription $SUB --scope $ANCESTOR --output json
}
```

### 2. Resolve definitions, initiatives and actual resource context

For each unique referenced policyDefinitionId, GET exact ID, including policySetDefinitions. Expand each initiative reference and GET its policy definition at the referenced scope and effective version. Preserve assignment definitionVersion, overrides, resourceSelectors, notScopes, enforcementMode and parameter mappings. Resource GET is used only for a resource target; group and subscription targets use approved representative configurations.

```powershell
az rest --method get --url "https://management.azure.com$DEFINITION_ID`?api-version=2023-04-01" --output json
az resource show --subscription $SUB --ids $RESOURCE_ID --output json
```

## Analysis rules

1. Filter assignments by actual ancestor relationship and target applicability. Report assignment scope and inherited_from rather than flattening provenance.
2. Resolve parameter values through assignment, initiative reference mapping and definition defaults, then apply effect overrides and definition versions. Unresolved expressions remain unknown.
3. Apply notScopes, resourceSelectors, policy mode and active exemptions, including initiative reference subsets and expiresOn. Expired exemption objects no longer exempt evaluation.
4. Evaluate actual conditions cumulatively. Audit and deny on the same condition are not inherently conflicting, and deployIfNotExists is not shadowed merely because deny exists.
5. Report a verified conflict only when overlapping applicability and actual constraints cannot be jointly satisfied or modifications demand incompatible values. Otherwise report overlap, potential contradiction or complementary controls with evidence.
6. Consider deployIfNotExists existenceCondition and deployment parameters; its evaluation after successful provisioning does not override deny.

## Known limits

- Arbitrary policy expressions may require Azure engine evaluation or approved fixture tests; no generic local solver proves all conflicts.
- Unreadable ancestors, definitions or exemptions prevent a complete effective policy claim.

## Expected validation cases

- Healthy: audit and deny share a condition and are reported as cumulative complementary enforcement, not a conflict.
- Finding: two applicable deny policies require disjoint allowed location sets after parameter resolution.
- Denied or missing: unreadable root management group leaves inherited coverage Partial and effective parameters null where unresolved.

## Sources

- [Cumulative evaluation and effect order](https://learn.microsoft.com/en-us/azure/governance/policy/concepts/effect-basics) (consulted 2026-10-21).
- [Assignment scope enumeration](https://learn.microsoft.com/en-us/cli/azure/policy/assignment?view=azure-cli-latest) (consulted 2026-10-21).
- [Exemption scope and initiative references](https://learn.microsoft.com/en-us/azure/governance/policy/concepts/exemption-structure) (consulted 2026-10-21).

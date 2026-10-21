# Evidence collection and analysis

## Collection

### 1. Enumerate exemptions through approved hierarchy

Choose $CONTEXT_SUB from the approved subscription beneath each scope. Use CLI scope reads for approved management group ancestors because subscription ARG alone does not prove complete ancestor coverage. Follow every next-token or nextLink, page ARG with skip_token and deduplicate exemption IDs; obey Retry-After. Reconcile ARG discoveries against authorized scope listings.

```powershell
foreach ($SCOPE in $APPROVED_SCOPES) {
 az policy exemption list --scope $SCOPE --subscription $CONTEXT_SUB --output json
}
az graph query --subscriptions $SUBS --first 1000 --graph-query "PolicyResources | where type =~ 'microsoft.authorization/policyexemptions' | project id,name,properties" --output json
```

### 2. Read referenced assignments

Resolve only referenced approved assignment IDs and their initiative reference subsets. Record 404 separately from 403 and check exemption scope relationship. Never broaden resource reads merely because an exemption points to another scope.

```powershell
az rest --method get --url "https://management.azure.com$ASSIGNMENT_ID`?api-version=2022-06-01" --output json
```

## Analysis rules

1. Report exemption name, scope, assignment ID, resolved policy or initiative references, category, expiresOn and sanitized justification.
2. Compare expiresOn to the UTC assessment instant. An expired exemption object may remain present but no longer provides an effective exemption.
3. Flag missing expiry and missing or whitespace justification separately; indefinite exemptions require customer risk policy review, not automatic removal.
4. Distinguish Waiver and Mitigated categories; verify owner supplied mitigation evidence before claiming compensating control effectiveness.
5. Validate referenced assignment and initiative references. A denied read is unknown relationship, not proof of an orphaned exemption.

## Known limits

- Exemption descriptions can contain sensitive owner or ticket data and require sanitization.
- Current exemption objects do not prove historic effectiveness or actual compensating controls.

## Expected validation cases

- Healthy: future expiry, valid assignment and reviewed justification.
- Finding: exemption has passed its UTC expiry and another lacks a justification.
- Denied or missing: assignment denied leaves policy resolution null and is not labeled orphaned.

## Sources

- [Exemption structure and expiry behavior](https://learn.microsoft.com/en-us/azure/governance/policy/concepts/exemption-structure) (consulted 2026-10-21).
- [Read exemption scopes](https://learn.microsoft.com/en-us/cli/azure/policy/exemption?view=azure-cli-latest) (consulted 2026-10-21).

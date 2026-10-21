# Standard platform request planning

## Inputs and permissions

Require the request ID and intent, explicit resource scope, requester authority,
workload owner, approved naming and policy standards, maintenance constraints
and repository destination. Read existing configuration with Reader at the
approved scope. Do not treat a request, accessible resource or nonconfidential
workload label as authorization to make changes.

## Collection

Validate resource IDs and read only explicitly approved resources:

```powershell
foreach ($RESOURCE_ID in $RESOURCE_IDS) {
    az resource show --ids $RESOURCE_ID --output json
}
```

Use approved policy assignment and effective rule evidence, or ask the operator
for a sanitized export. For network requests, collect the requested source,
destination, protocol, port, direction, priority, justification and expiry.
Stop if identifiers, ownership or requirements remain ambiguous.

## Analysis and local draft

1. Compare intent against existing rules, naming conventions and policy evidence.
   Detect duplicate, conflicting or broader than requested changes. Do not
   silently replace a restrictive policy with a permissive request.
2. Draft the smallest proposed IaC or configuration change with exact affected
   resources. Keep the draft local; do not modify a repository or open a PR
   without separate approval and an approved destination.
3. Record dependencies, prerequisites, risk, owner approval and rollback from
   captured prechange state. A generated rollback is a proposal, not proof it
   will restore service.
4. Propose deployment validation and what-if only through a separately authorized
   host workflow. What-if previews changes but requires deployment related
   permissions; do not assume a Reader identity can run it. A successful preview
   is not proof of runtime reachability, policy acceptance or deployment success.
5. Prepare a change checklist, verification evidence and repository/documentation
   handoff. Do not apply NSG or firewall rules, deploy, schedule, push, update a
   ticket or notify anyone from this workflow.
6. Populate `scenario_data` with `request_id`, `approved_intent`,
   `current_configuration`, `policy_evidence`, `proposed_change`,
   `rollback_plan` and `validation_plan`. Null required evidence prevents a
   complete readiness decision.

## Validation cases

- Healthy: an already satisfied request yields an evidenced no change proposal.
- Finding: a conflicting network rule yields a bounded review proposal, not apply.
- Missing: unavailable policy or prechange evidence yields Partial or Not assessed
  and blocks an implementation readiness claim.

## Sources

- [Resource show CLI](https://learn.microsoft.com/en-us/cli/azure/resource?view=azure-cli-latest#az-resource-show).
- [ARM deployment what-if](https://learn.microsoft.com/en-us/azure/azure-resource-manager/templates/deploy-what-if).

Read command and what-if boundaries verified on 2026-10-21. No deployment,
network rule update or repository write is performed by this skill.

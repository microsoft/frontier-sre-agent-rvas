# Evidence collection and analysis

## Collection

### 1. Enumerate deployment history at every approved scope

Repeat group list only for approved groups, intersecting discovered groups with scope approval; MG route only when explicitly approved. Select properties.provisioningState Failed and properties.timestamp in [START,END). Complete pagination and Retry-After handling. Preserve scope so identically named deployments do not collide.

```powershell
foreach ($SUB in $SUBS) {
 az deployment sub list --subscription $SUB --output json
 az group list --subscription $SUB --output json
}
az deployment group list --subscription $SUB --resource-group $RG --output json
az deployment mg list --management-group-id $MG --output json
```

### 2. Read actual failure details and nested operation evidence

Use matching deployment mg show and deployment operation mg list for approved MG failures. Read nested deployment operations only at approved referenced scopes. Retain correlationId, timestamp and structured error code and details, redacting credentials, parameter values and customer data before output.

```powershell
az deployment group show --subscription $SUB --resource-group $RG --name $DEPLOYMENT --output json
az deployment operation group list --subscription $SUB --resource-group $RG --name $DEPLOYMENT --output json
az deployment sub show --subscription $SUB --name $SUB_DEPLOYMENT --output json
az deployment operation sub list --subscription $SUB --name $SUB_DEPLOYMENT --output json
```

## Analysis rules

1. Report deployment ID, scope, resource group where applicable, name, timestamp, top level error code, sanitized message and correlation ID.
2. Expand nested error details into actionable root cause codes rather than grouping every failure solely under DeploymentFailed.
3. Group by stable error code and distinguish policy denial, quota, permissions and template validation evidence without guessing missing causes.
4. Deduplicate nested and parent deployments when counting incident groups while preserving each failed deployment record.
5. History that was deleted, aged out or denied remains a coverage gap. No failures in incomplete history is not a complete clean result.

## Known limits

- Deployment history has retention and deletion limits; it is not a complete permanent audit trail.
- Error messages can contain sensitive request data and require redaction.

## Expected validation cases

- Healthy: complete approved history has no Failed deployments in the UTC interval.
- Finding: parent DeploymentFailed expands to RequestDisallowedByPolicy with a recorded assignment reference.
- Denied or missing: unreadable group history remains Not assessed and is not counted as zero failures.

## Sources

- [Deployment history listing and detail](https://learn.microsoft.com/en-us/cli/azure/deployment/group?view=azure-cli-latest) (consulted 2026-10-21).
- [Deployment operation error details](https://learn.microsoft.com/en-us/cli/azure/deployment/operation/group?view=azure-cli-latest) (consulted 2026-10-21).

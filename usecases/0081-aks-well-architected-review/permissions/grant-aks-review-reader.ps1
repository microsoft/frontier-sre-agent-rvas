<#
.SYNOPSIS
  Grants the Azure SRE Agent managed identity the read-only Azure roles of the use case "AKS
  configuration and Well-Architected review".

.DESCRIPTION
  Roles granted to the agent's user-assigned managed identity:
    - Reader on the subscription of each approved cluster
    - Optional, with -IncludeCost: Cost Management Reader on the subscription of each approved
      cluster, for the optional billing evidence (cost_scope)
    - Azure Kubernetes Service Cluster User Role on each approved AKS cluster (-ClusterResourceId)
    - Azure Kubernetes Service RBAC Reader on each approved AKS cluster (-ClusterResourceId)
  Reader on the subscription covers the cluster, agent pool, maintenance, diagnostics, associated-
  resource, Kubernetes version and Advisor reads. Cluster User Role allows listClusterUserCredential
  for the API server address and CA only.
  Azure Kubernetes Service RBAC Reader gives the Kubernetes reads on clusters with Microsoft Entra
  ID and Azure RBAC. It does not cover nodes, persistent volumes, storage classes or metrics; for
  those, and for clusters with Kubernetes RBAC, the access team adds a read-only cluster binding.
  Never grant Cluster Admin or any write role.

  Run it as someone who can create role assignments on those scopes: Owner, User Access
  Administrator or Role Based Access Control Administrator. It needs Azure CLI signed in to the
  agent's tenant (az login). Assignments that already exist, also inherited ones, are skipped.
  -WhatIf shows what would be assigned without changing anything.

.EXAMPLE
  ./grant-aks-review-reader.ps1 -IdentityClientId <client-id> -ClusterResourceId <cluster-resource-id-1>,<cluster-resource-id-2> -WhatIf

.EXAMPLE
  ./grant-aks-review-reader.ps1 -PrincipalId <object-id> -ClusterResourceId <cluster-resource-id> -IncludeCost
#>
[CmdletBinding(SupportsShouldProcess, DefaultParameterSetName = 'ClientId')]
param(
    # Client ID of the agent's user-assigned managed identity (the value the tool uses).
    [Parameter(Mandatory, ParameterSetName = 'ClientId')]
    [ValidatePattern('^[0-9a-f]{8}-([0-9a-f]{4}-){3}[0-9a-f]{12}$')][string]$IdentityClientId,

    # Or its Object (principal) ID.
    [Parameter(Mandatory, ParameterSetName = 'ObjectId')]
    [ValidatePattern('^[0-9a-f]{8}-([0-9a-f]{4}-){3}[0-9a-f]{12}$')][string]$PrincipalId,

    # Full resource IDs of the approved AKS clusters.
    [Parameter(Mandatory)]
    [ValidatePattern('^/subscriptions/[^/]+/resourceGroups/[^/]+/providers/Microsoft\.ContainerService/managedClusters/[^/]+$')]
    [string[]]$ClusterResourceId,

    # Also grant Cost Management Reader, for the optional billing evidence (cost_scope).
    [switch]$IncludeCost
)
$ErrorActionPreference = 'Stop'

# az is a native command: PowerShell does not stop when it fails, so every call checks its exit code.
function Invoke-Az {
    $out = az @args
    if ($LASTEXITCODE -ne 0) { throw "Azure CLI failed (exit code $LASTEXITCODE): az $args" }
    $out
}

# Assigns a role unless the identity already has it on the scope, directly or inherited.
function Grant-Role([string]$Role, [string]$Scope) {
    $existing = Invoke-Az role assignment list --assignee-object-id $objectId --role $Role --scope $Scope `
        --include-inherited --query 'length(@)' -o tsv --only-show-errors
    if ([int]$existing -gt 0) {
        Write-Host "Skipped, already assigned: '$Role' on $Scope"
    } elseif ($PSCmdlet.ShouldProcess($Scope, "Assign '$Role' to $objectId")) {
        Invoke-Az role assignment create --assignee-object-id $objectId --assignee-principal-type ServicePrincipal `
            --role $Role --scope $Scope --only-show-errors -o none | Out-Null
        Write-Host "Assigned: '$Role' on $Scope"
    }
}

$scopes = @($ClusterResourceId | ForEach-Object { '/subscriptions/' + $_.Split('/')[2].ToLower() } | Select-Object -Unique)

$objectId = $PrincipalId
if ($PSCmdlet.ParameterSetName -eq 'ClientId') {
    $objectId = az ad sp show --id $IdentityClientId --query id -o tsv --only-show-errors
    if ($LASTEXITCODE -ne 0 -or -not $objectId) {
        throw "Managed identity with Client ID $IdentityClientId not found in the tenant of the current az login " +
              "(see the Azure CLI message above). Check that it is the Client ID, not the Object ID, and sign in " +
              "to the agent's tenant: az login --tenant <tenant-id>"
    }
}
Write-Host "Agent identity: Object (principal) ID $objectId"

foreach ($scope in $scopes) {
    Grant-Role 'Reader' $scope
    if ($IncludeCost) { Grant-Role 'Cost Management Reader' $scope }
}
foreach ($cluster in $ClusterResourceId) {
    Grant-Role 'Azure Kubernetes Service Cluster User Role' $cluster
    Grant-Role 'Azure Kubernetes Service RBAC Reader' $cluster
}

if ($WhatIfPreference) { Write-Host 'No changes made (-WhatIf).' }
else { Write-Host 'Done. New role assignments can take a few minutes to reach the agent token.' }

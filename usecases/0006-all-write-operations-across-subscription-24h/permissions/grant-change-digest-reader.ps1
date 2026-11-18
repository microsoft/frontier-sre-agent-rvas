<#
.SYNOPSIS
  Grants the Azure SRE Agent managed identity the read-only Azure roles of the use case "Daily
  relevant Azure changes digest".

.DESCRIPTION
  Roles granted to the agent's user-assigned managed identity:
    - Reader on each subscription in -SubscriptionId, or once on the management group
      -ManagementGroupId
  Most SRE Agent identities already have Reader on the subscriptions they manage; the script finds
  it and skips it.
  Optional, not granted by this script: for application names instead of app IDs, also grant
  Microsoft Graph Application.Read.All and set ENABLE_GRAPH_NAMES = True.

  Run it as someone who can create role assignments on those scopes: Owner, User Access
  Administrator or Role Based Access Control Administrator. It needs Azure CLI signed in to the
  agent's tenant (az login). Assignments that already exist, also inherited ones, are skipped.
  -WhatIf shows what would be assigned without changing anything.

.EXAMPLE
  ./grant-change-digest-reader.ps1 -IdentityClientId <client-id> -SubscriptionId <subscription-id-1>,<subscription-id-2> -WhatIf

.EXAMPLE
  ./grant-change-digest-reader.ps1 -PrincipalId <object-id> -ManagementGroupId <management-group-id>
#>
[CmdletBinding(SupportsShouldProcess, DefaultParameterSetName = 'ClientId')]
param(
    # Client ID of the agent's user-assigned managed identity (the value the tool uses).
    [Parameter(Mandatory, ParameterSetName = 'ClientId')]
    [ValidatePattern('^[0-9a-f]{8}-([0-9a-f]{4}-){3}[0-9a-f]{12}$')][string]$IdentityClientId,

    # Or its Object (principal) ID.
    [Parameter(Mandatory, ParameterSetName = 'ObjectId')]
    [ValidatePattern('^[0-9a-f]{8}-([0-9a-f]{4}-){3}[0-9a-f]{12}$')][string]$PrincipalId,

    # Subscriptions to grant the role on.
    [ValidatePattern('^[0-9a-f]{8}-([0-9a-f]{4}-){3}[0-9a-f]{12}$')][string[]]$SubscriptionId = @(),

    # Or a management group: its subscriptions inherit the role.
    [string]$ManagementGroupId
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

$scopes = @($SubscriptionId | ForEach-Object { "/subscriptions/$_" })
if ($ManagementGroupId) { $scopes += "/providers/Microsoft.Management/managementGroups/$ManagementGroupId" }
if (-not $scopes) { throw 'Give -SubscriptionId (one or more) or -ManagementGroupId.' }

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
}

if ($WhatIfPreference) { Write-Host 'No changes made (-WhatIf).' }
else { Write-Host 'Done. New role assignments can take a few minutes to reach the agent token.' }

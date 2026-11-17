<#
.SYNOPSIS
  Grants the Azure SRE Agent managed identity the read-only Azure roles of the use case "Security
  posture from Defender for Cloud".

.DESCRIPTION
  Roles granted to the agent's user-assigned managed identity:
    - Reader on the monitored subscription (-SubscriptionId)
  Reader covers the ARM and Azure Resource Graph reads of the whole pipeline (inventory,
  assessments, attack paths, software and CVEs). Security Reader alone is not assumed to cover it.
  The report never needs Microsoft Graph, Defender XDR or any write role.

  Run it as someone who can create role assignments on those scopes: Owner, User Access
  Administrator or Role Based Access Control Administrator. It needs Azure CLI signed in to the
  agent's tenant (az login). Assignments that already exist, also inherited ones, are skipped.
  -WhatIf shows what would be assigned without changing anything.

.EXAMPLE
  ./grant-defender-evidence-reader.ps1 -IdentityClientId <client-id> -SubscriptionId <subscription-id> -WhatIf

.EXAMPLE
  ./grant-defender-evidence-reader.ps1 -PrincipalId <object-id> -SubscriptionId <subscription-id>
#>
[CmdletBinding(SupportsShouldProcess, DefaultParameterSetName = 'ClientId')]
param(
    # Client ID of the agent's user-assigned managed identity (the value the tool uses).
    [Parameter(Mandatory, ParameterSetName = 'ClientId')]
    [ValidatePattern('^[0-9a-f]{8}-([0-9a-f]{4}-){3}[0-9a-f]{12}$')][string]$IdentityClientId,

    # Or its Object (principal) ID.
    [Parameter(Mandatory, ParameterSetName = 'ObjectId')]
    [ValidatePattern('^[0-9a-f]{8}-([0-9a-f]{4}-){3}[0-9a-f]{12}$')][string]$PrincipalId,

    # The monitored subscription.
    [Parameter(Mandatory)][ValidatePattern('^[0-9a-f]{8}-([0-9a-f]{4}-){3}[0-9a-f]{12}$')][string]$SubscriptionId
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

Grant-Role 'Reader' "/subscriptions/$SubscriptionId"

if ($WhatIfPreference) { Write-Host 'No changes made (-WhatIf).' }
else { Write-Host 'Done. New role assignments can take a few minutes to reach the agent token.' }

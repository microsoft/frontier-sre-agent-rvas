<#
.SYNOPSIS
    Optional. Grants the identity used by the generate-fabric-chargeback-report tool two READ-ONLY Microsoft Graph
    application permissions in the tenant where Microsoft Fabric lives, so the "Access and groups" section of the
    report can list the members of every group with access and flag new users:
      - GroupMember.Read.All  (who belongs to each group, including nested groups)
      - User.Read.All         (when each user was created, to flag new users in the period)
    Without them the report still shows which groups have access and their consumption scope, but group members
    appear as "pending" and the per-person breakdown inside each group is not available.

    Used by BOTH options of Case 11:
      Option A - same tenant : pass -PrincipalObjectId <object (principal) ID of the SRE Agent user-assigned managed identity>
      Option B - cross-tenant: pass -AppClientId <client ID of the multi-tenant app created by setup-cross-tenant-app.ps1>

.DESCRIPTION
    Idempotent: a permission that is already granted is skipped. It assigns the Graph app roles directly to the
    service principal (the equivalent of admin consent for those two application permissions). It does not grant
    any write permission and does not add API permissions to the app registration.

.NOTES
    Run in the Fabric tenant as Global Administrator or Privileged Role Administrator (if the role is eligible in
    PIM, activate it first: Entra ID > Roles and administrators > My roles > Activate). Azure CLI 2.60+. Works in
    Windows PowerShell 5.1, PowerShell 7 and Azure Cloud Shell (already signed in there).

.EXAMPLE
    # Option A - same tenant
    ./grant-graph-read-permissions.ps1 -FabricTenantId <TENANT_ID> -PrincipalObjectId <UAMI_PRINCIPAL_ID>

.EXAMPLE
    # Option B - cross-tenant (run in the Fabric tenant, after grant-fabric-finops-access.ps1 -AppClientId)
    ./grant-graph-read-permissions.ps1 -FabricTenantId <TARGET_FABRIC_TENANT_ID> -AppClientId <FEDERATED_APP_CLIENT_ID>

.EXAMPLE
    # Show what would be granted, without changing anything
    ./grant-graph-read-permissions.ps1 -FabricTenantId <TENANT_ID> -AppClientId <FEDERATED_APP_CLIENT_ID> -DryRun
#>
[CmdletBinding(DefaultParameterSetName = "SameTenant")]
param(
    [Parameter(Mandatory = $true)] [string] $FabricTenantId,
    [Parameter(Mandatory = $true, ParameterSetName = "SameTenant")]  [string] $PrincipalObjectId,
    [Parameter(Mandatory = $true, ParameterSetName = "CrossTenant")] [string] $AppClientId,
    [string[]] $Permissions = @("GroupMember.Read.All", "User.Read.All"),
    [switch] $DryRun,
    [switch] $SkipLogin
)
$ErrorActionPreference = "Stop"
$graphAppId = "00000003-0000-0000-c000-000000000000"

function Invoke-AzCli {
    $o = & az @args
    if ($LASTEXITCODE -ne 0) { throw "az $($args -join ' ') failed. Fix the cause above and run the script again." }
    return $o
}

# Cloud Shell is already signed in; elsewhere sign in to the Fabric tenant unless -SkipLogin.
if (-not $SkipLogin -and -not $env:ACC_CLOUD) { Invoke-AzCli login --tenant $FabricTenantId --allow-no-subscriptions | Out-Null }
$current = Invoke-AzCli account show --query tenantId -o tsv
if ($current -ne $FabricTenantId) { throw "Signed in to tenant $current, expected $FabricTenantId. Run: az login --tenant $FabricTenantId" }

if ($PSCmdlet.ParameterSetName -eq "CrossTenant") {
    $spId = Invoke-AzCli ad sp list --filter "appId eq '$AppClientId'" --query "[0].id" -o tsv
    if (-not $spId) { throw "App $AppClientId has no service principal in this tenant. Run grant-fabric-finops-access.ps1 -AppClientId first." }
} else {
    $spId = Invoke-AzCli ad sp list --filter "id eq '$PrincipalObjectId'" --query "[0].id" -o tsv
    if (-not $spId) { throw "No service principal with object ID $PrincipalObjectId in this tenant. Use the Object (principal) ID of the UAMI, not its Client ID." }
}

$graphSp = Invoke-AzCli ad sp list --filter "appId eq '$graphAppId'" --query "[0].id" -o tsv
$roles = Invoke-AzCli ad sp show --id $graphSp --query "appRoles[].{id:id,value:value}" -o json | ConvertFrom-Json
$granted = @(Invoke-AzCli rest --method GET --url "https://graph.microsoft.com/v1.0/servicePrincipals/$spId/appRoleAssignments" `
        --query "value[?resourceId=='$graphSp'].appRoleId" -o json | ConvertFrom-Json)

foreach ($p in $Permissions) {
    $role = $roles | Where-Object { $_.value -eq $p }
    if (-not $role) { throw "Permission $p not found in Microsoft Graph." }
    if ($granted -contains $role.id) { Write-Host "[OK] $p was already granted" -ForegroundColor Green; continue }
    if ($DryRun) { Write-Host "[DRY-RUN] Would grant $p ($($role.id)) to $spId" -ForegroundColor Yellow; continue }
    $body = Join-Path ([IO.Path]::GetTempPath()) ("sre-fabric-approle-" + [guid]::NewGuid().ToString("N") + ".json")
    [IO.File]::WriteAllText($body, (@{ principalId = $spId; resourceId = $graphSp; appRoleId = $role.id } | ConvertTo-Json), (New-Object Text.UTF8Encoding($false)))
    $out = & az rest --method POST --url "https://graph.microsoft.com/v1.0/servicePrincipals/$spId/appRoleAssignments" `
        --headers "Content-Type=application/json" --body "@$body" -o none 2>&1
    $code = $LASTEXITCODE
    Remove-Item $body -ErrorAction SilentlyContinue
    if ($code -ne 0) {
        if ("$out" -match "Authorization_RequestDenied|Insufficient privileges") {
            throw "Your account cannot grant Microsoft Graph application permissions. Activate Global Administrator or Privileged Role Administrator (PIM: Entra ID > Roles and administrators > My roles > Activate) and run the script again."
        }
        throw "Could not grant ${p}: $out"
    }
    Write-Host "[OK] $p granted" -ForegroundColor Green
}
Write-Host ""
Write-Host "Done. Wait 10-15 minutes and ask the fabric-chargeback-live subagent for the report again." -ForegroundColor Cyan

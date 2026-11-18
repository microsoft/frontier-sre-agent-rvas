<#
.SYNOPSIS
  Azure RBAC privileged access review with Azure SRE Agent.
  Grants the SRE Agent managed identity the READ-ONLY permissions it needs:
    - Azure RBAC: Reader on the subscriptions (or on a Management Group) to review.
    - Microsoft Graph (application permissions): User.Read.All, Application.Read.All,
      GroupMember.Read.All and AuditLog.Read.All.
  Returns the Client ID to paste into the tool code.

.DESCRIPTION
  - Uses only Azure CLI (az), no modules to install. Works in Azure Cloud Shell.
  - Requires:
      * Owner, User Access Administrator or Role Based Access Control Administrator on the scope
        to assign Reader (skipped if the identity already has Reader).
      * Privileged Role Administrator or Global Administrator in Entra ID for the Graph permissions.
  - Idempotent: does not create duplicate assignments.
  - Does not grant any write permission in Azure or Microsoft Graph.

.EXAMPLE
  ./grant-rbac-review-permissions.ps1 -IdentityClientId 00000000-0000-0000-0000-000000000000 `
     -SubscriptionIds 11111111-1111-1111-1111-111111111111,22222222-2222-2222-2222-222222222222
.EXAMPLE
  ./grant-rbac-review-permissions.ps1 -SubscriptionId 11111111-1111-1111-1111-111111111111 `
     -AgentResourceGroup rg-sre-agent -AgentName my-sre-agent -ManagementGroupId mg-contoso
#>
[CmdletBinding(DefaultParameterSetName = "ClientId")]
param(
    [Parameter(ParameterSetName = "Agent", Mandatory = $true)] [string] $SubscriptionId,
    [Parameter(ParameterSetName = "Agent", Mandatory = $true)] [string] $AgentResourceGroup,
    [Parameter(ParameterSetName = "Agent", Mandatory = $true)] [string] $AgentName,
    [Parameter(ParameterSetName = "ClientId", Mandatory = $true)]
    [Parameter(ParameterSetName = "Agent")] [string] $IdentityClientId = "",
    # Subscriptions the tool will review (Reader on each). If omitted and -SubscriptionId is used, that one is used.
    [string[]] $SubscriptionIds = @(),
    # Alternative: Reader on a Management Group (inherited by all its subscriptions).
    [string] $ManagementGroupId = "",
    # Skips the Graph permissions (Reader only). The review will report partial coverage.
    [switch] $SkipGraph
)
$ErrorActionPreference = "Stop"
function Invoke-Az { param([string[]]$Arguments)
    $out = & az @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) { throw "az $($Arguments -join ' ') failed:`n$out" }
    return ($out | Where-Object { $_ -isnot [System.Management.Automation.ErrorRecord] }) -join "`n"
}
function Write-Step($t) { Write-Host "`n== $t" -ForegroundColor Cyan }
$graphAppId = "00000003-0000-0000-c000-000000000000"
$readerRoleId = "acdd72a7-3385-48ef-bd42-f606fba81ae7"
$graphRoles = @("User.Read.All", "Application.Read.All", "GroupMember.Read.All", "AuditLog.Read.All")

Write-Step "1/5 SRE Agent managed identity"
if ($PSCmdlet.ParameterSetName -eq "Agent") {
    Invoke-Az @("account","set","--subscription",$SubscriptionId) | Out-Null
    $agent = Invoke-Az @("resource","show","-g",$AgentResourceGroup,"-n",$AgentName,"--resource-type","Microsoft.App/agents","-o","json") | ConvertFrom-Json
    $ids = @()
    foreach ($p in $agent.identity.userAssignedIdentities.PSObject.Properties) { $ids += $p.Value.clientId }
    if ($IdentityClientId) { $ids = @($ids | Where-Object { $_ -eq $IdentityClientId }) }
    if ($ids.Count -ne 1) { throw "Expected 1 user-assigned identity on the SRE Agent (found: $($ids.Count)). Use -IdentityClientId." }
    $IdentityClientId = $ids[0]
    Write-Host "Agent endpoint: $($agent.properties.agentEndpoint)"
    if ($agent.properties.experimentalSettings.EnablePythonTools -ne $true) {
        Write-Warning "Python tools do not appear to be enabled on the SRE Agent (EnablePythonTools). Review Step 1 of the guide before creating the tool."
    }
    $egress = $agent.properties.sandboxConfiguration.egress
    if ($egress -and $egress.mode -and $egress.mode -ne "Unrestricted") {
        Write-Warning "Sandbox network egress is restricted ($($egress.mode)). Allow login.microsoftonline.com, management.azure.com and graph.microsoft.com."
    }
    if (-not $SubscriptionIds -and -not $ManagementGroupId) { $SubscriptionIds = @($SubscriptionId) }
}
$miSp = Invoke-Az @("ad","sp","show","--id",$IdentityClientId,"-o","json") | ConvertFrom-Json
Write-Host "Identity: $($miSp.displayName)  ClientId: $IdentityClientId  ObjectId (SP): $($miSp.id)"

Write-Step "2/5 Azure RBAC Reader (read only)"
$scopes = @()
if ($ManagementGroupId) { $scopes += "/providers/Microsoft.Management/managementGroups/$ManagementGroupId" }
foreach ($s in $SubscriptionIds) { if ($s) { $scopes += "/subscriptions/$s" } }
if (-not $scopes) { throw "Specify -SubscriptionIds or -ManagementGroupId." }
foreach ($scope in $scopes) {
    $current = Invoke-Az @("role","assignment","list","--assignee",$miSp.id,"--scope",$scope,"--include-inherited","--query","[?roleDefinitionName=='Reader' || roleDefinitionName=='Owner' || roleDefinitionName=='Contributor']","-o","json") | ConvertFrom-Json
    if ($current) {
        Write-Host "  [already exists] $($current[0].roleDefinitionName) on $scope (includes read)" -ForegroundColor Yellow
    } else {
        Invoke-Az @("role","assignment","create","--assignee-object-id",$miSp.id,"--assignee-principal-type","ServicePrincipal","--role",$readerRoleId,"--scope",$scope,"-o","none") | Out-Null
        Write-Host "  [assigned] Reader on $scope" -ForegroundColor Green
    }
}

if (-not $SkipGraph) {
    Write-Step "3/5 Microsoft Graph application permissions"
    $graphSp = Invoke-Az @("ad","sp","show","--id",$graphAppId,"-o","json") | ConvertFrom-Json
    $assigned = Invoke-Az @("rest","--method","get","--url","https://graph.microsoft.com/v1.0/servicePrincipals/$($miSp.id)/appRoleAssignments","-o","json") | ConvertFrom-Json

    Write-Step "4/5 Assignment (idempotent)"
    foreach ($name in $graphRoles) {
        $role = $graphSp.appRoles | Where-Object { $_.value -eq $name -and $_.allowedMemberTypes -contains "Application" }
        if (-not $role) { throw "App role $name was not found in Microsoft Graph." }
        if ($assigned.value | Where-Object { $_.resourceId -eq $graphSp.id -and $_.appRoleId -eq $role.id }) {
            Write-Host "  [already exists] $name" -ForegroundColor Yellow; continue
        }
        $body = Join-Path ([IO.Path]::GetTempPath()) ("approle-" + [guid]::NewGuid() + ".json")
        [IO.File]::WriteAllText($body, (@{ principalId = $miSp.id; resourceId = $graphSp.id; appRoleId = $role.id } | ConvertTo-Json -Compress))
        try {
            Invoke-Az @("rest","--method","post","--url","https://graph.microsoft.com/v1.0/servicePrincipals/$($miSp.id)/appRoleAssignments","--headers","Content-Type=application/json","--body","@$body","-o","none") | Out-Null
            Write-Host "  [assigned] $name" -ForegroundColor Green
        } catch {
            if ("$_" -match "Authorization_RequestDenied|Forbidden") {
                throw "Insufficient Entra ID permissions to assign $name. Run the script with a Privileged Role Administrator or Global Administrator account (activate the role in PIM if it is eligible)."
            }
            throw
        } finally { Remove-Item $body -ErrorAction SilentlyContinue }
    }
} else {
    Write-Warning "Graph permissions skipped: the review will not be able to detect deleted identities or sign-in activity."
}

Write-Step "5/5 Verification"
foreach ($scope in $scopes) {
    Invoke-Az @("role","assignment","list","--assignee",$miSp.id,"--scope",$scope,"--include-inherited","--query","[].{Role:roleDefinitionName, Scope:scope}","-o","table") | Write-Host
}
if (-not $SkipGraph) {
    $assigned = Invoke-Az @("rest","--method","get","--url","https://graph.microsoft.com/v1.0/servicePrincipals/$($miSp.id)/appRoleAssignments","-o","json") | ConvertFrom-Json
    $assigned.value | Where-Object { $_.resourceId -eq $graphSp.id } |
        ForEach-Object { [pscustomobject]@{ Permission = ($graphSp.appRoles | Where-Object id -eq $_.appRoleId).value; Since = $_.createdDateTime } } |
        Format-Table -AutoSize | Out-String | Write-Host
}
Write-Host "Paste these values into the tool code (Step 4 of the guide):" -ForegroundColor Cyan
Write-Host "MANAGED_IDENTITY_CLIENT_ID = `"$IdentityClientId`"" -ForegroundColor Green
$subsOut = if ($SubscriptionIds) { ($SubscriptionIds | ForEach-Object { "`"$_`"" }) -join ", " } else { "`"<YOUR_SUBSCRIPTION_ID>`"" }
Write-Host "SUBSCRIPTION_IDS = [$subsOut]" -ForegroundColor Green
Write-Host "Permissions can take up to 30 minutes to be reflected in the identity token." -ForegroundColor Cyan

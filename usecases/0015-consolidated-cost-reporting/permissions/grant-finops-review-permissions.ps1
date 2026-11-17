<#
.SYNOPSIS
  Monthly Azure FinOps review with Azure SRE Agent.
  Grants the SRE Agent managed identity the READ-ONLY permission it needs:
    - Azure RBAC Reader on the subscriptions (or on a Management Group) to review. Reader includes the cost,
      budget, Azure Advisor and Azure Resource Graph reads used by the tool.
    - Optional (-IncludeCostManagementReader): Cost Management Reader on the same scopes, for organizations that
      want the cost role assigned explicitly.
  Returns the Client ID and the subscription IDs to paste into the tool code.

.DESCRIPTION
  - Uses only Azure CLI (az), no modules to install. Works in Azure Cloud Shell.
  - Requires Owner, User Access Administrator or Role Based Access Control Administrator on the scope
    (skipped when the identity already has Reader, Contributor or Owner there).
  - Idempotent: does not create duplicate assignments.
  - Grants no write permission and creates no Azure resource.

.EXAMPLE
  ./grant-finops-review-permissions.ps1 -IdentityClientId 00000000-0000-0000-0000-000000000000 `
     -SubscriptionIds 11111111-1111-1111-1111-111111111111,22222222-2222-2222-2222-222222222222
.EXAMPLE
  ./grant-finops-review-permissions.ps1 -SubscriptionId 11111111-1111-1111-1111-111111111111 `
     -AgentResourceGroup rg-sre-agent -AgentName my-sre-agent -ManagementGroupId mg-contoso -IncludeCostManagementReader
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
    # Also assigns Cost Management Reader on the same scopes (not required: Reader already reads costs).
    [switch] $IncludeCostManagementReader
)
$ErrorActionPreference = "Stop"
function Invoke-Az { param([string[]]$Arguments)
    $out = & az @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) { throw "az $($Arguments -join ' ') failed:`n$out" }
    return ($out | Where-Object { $_ -isnot [System.Management.Automation.ErrorRecord] }) -join "`n"
}
function Write-Step($t) { Write-Host "`n== $t" -ForegroundColor Cyan }
$readerRoleId = "acdd72a7-3385-48ef-bd42-f606fba81ae7"
$costReaderRoleId = "72fafb9e-0641-4937-9268-a91bfd8191a3"

Write-Step "1/4 SRE Agent managed identity"
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
        Write-Warning "Sandbox network egress is restricted ($($egress.mode)). Allow login.microsoftonline.com and management.azure.com."
    }
    if (-not $SubscriptionIds -and -not $ManagementGroupId) { $SubscriptionIds = @($SubscriptionId) }
}
$miSp = Invoke-Az @("ad","sp","show","--id",$IdentityClientId,"-o","json") | ConvertFrom-Json
Write-Host "Identity: $($miSp.displayName)  ClientId: $IdentityClientId  ObjectId (SP): $($miSp.id)"

Write-Step "2/4 Azure RBAC Reader (read only: costs, budgets, Advisor, Resource Graph)"
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

Write-Step "3/4 Cost Management Reader (optional)"
if ($IncludeCostManagementReader) {
    foreach ($scope in $scopes) {
        $current = Invoke-Az @("role","assignment","list","--assignee",$miSp.id,"--scope",$scope,"--include-inherited","--query","[?roleDefinitionName=='Cost Management Reader']","-o","json") | ConvertFrom-Json
        if ($current) {
            Write-Host "  [already exists] Cost Management Reader on $scope" -ForegroundColor Yellow
        } else {
            Invoke-Az @("role","assignment","create","--assignee-object-id",$miSp.id,"--assignee-principal-type","ServicePrincipal","--role",$costReaderRoleId,"--scope",$scope,"-o","none") | Out-Null
            Write-Host "  [assigned] Cost Management Reader on $scope" -ForegroundColor Green
        }
    }
} else {
    Write-Host "  Skipped: Reader already reads costs and budgets at subscription scope. Use -IncludeCostManagementReader to assign it anyway."
}

Write-Step "4/4 Verification"
foreach ($scope in $scopes) {
    Invoke-Az @("role","assignment","list","--assignee",$miSp.id,"--scope",$scope,"--include-inherited","--query","[].{Role:roleDefinitionName, Scope:scope}","-o","table") | Write-Host
}
Write-Host "Enterprise Agreement: the enrollment setting 'AO view charges' must be on for subscription-scope cost reads." -ForegroundColor Cyan
Write-Host "Paste these values into the tool code (Step 4 of the guide):" -ForegroundColor Cyan
Write-Host "MANAGED_IDENTITY_CLIENT_ID = `"$IdentityClientId`"" -ForegroundColor Green
if ($ManagementGroupId -and -not $SubscriptionIds) {
    Write-Host "SUBSCRIPTION_IDS = []" -ForegroundColor Green
    Write-Host "MANAGEMENT_GROUP_ID = `"$ManagementGroupId`"" -ForegroundColor Green
} else {
    $subsOut = if ($SubscriptionIds) { ($SubscriptionIds | ForEach-Object { "`"$_`"" }) -join ", " } else { "`"<YOUR_SUBSCRIPTION_ID>`"" }
    Write-Host "SUBSCRIPTION_IDS = [$subsOut]" -ForegroundColor Green
}
Write-Host "Role assignments can take a few minutes to propagate." -ForegroundColor Cyan

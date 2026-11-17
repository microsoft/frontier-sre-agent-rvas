<#
.SYNOPSIS
  Grants the SRE Agent identity READ-ONLY access to EVERY AKS cluster in a Management Group (or in one, several
  or all subscriptions) in a single run. Nothing has to be pasted into the tool: it discovers the clusters itself.

.DESCRIPTION
  Roles (all read-only; cluster admin credentials are never used):
    - Reader                                          -> scope (Management Group or each subscription)
    - Cost Management Reader (optional, -IncludeCost) -> scope (cost per cluster)
    - Azure Kubernetes Service Cluster User Role      -> scope (with -AksRolesAtScope) or each cluster
    - Azure Kubernetes Service RBAC Reader            -> scope (with -AksRolesAtScope) or each cluster
  Assigned at the Management Group, they are inherited by all its subscriptions and by clusters created later.

  Scope modes (pick one; with none, the active "az login" subscription is used):
    -ManagementGroupId <mg>     RECOMMENDED. Assigns the roles ONCE at the Management Group.
    -AllSubscriptions           Every enabled subscription of the tenant visible to your "az login".
    -SubscriptionIds a,b,c      Explicit list of subscriptions.
    -SubscriptionId <id>        A single subscription.

  Output: the clusters found per subscription, the Kubernetes authentication mode of each one and two CSV files
  (aks-clusters.csv and aks-auth-modes.csv). Nothing to paste.

  The person running it needs Owner, User Access Administrator or Role Based Access Control Administrator on the
  chosen scope, and Azure CLI signed in ("az login") to the right tenant.
  Re-running it is safe: existing assignments are not duplicated. -WhatIf prints what it would do and changes nothing.

.EXAMPLE
  # Recommended: the whole Management Group, AKS roles at scope level and costs
  .\grant-aks-permissions.ps1 -IdentityClientId "<client-id>" -ManagementGroupId "<management-group-id>" -AksRolesAtScope -IncludeCost

.EXAMPLE
  # See what it would do, without changing anything
  .\grant-aks-permissions.ps1 -IdentityClientId "<client-id>" -ManagementGroupId "<management-group-id>" -AksRolesAtScope -IncludeCost -WhatIf

.EXAMPLE
  # One subscription (for example a new one outside the Management Group)
  .\grant-aks-permissions.ps1 -IdentityClientId "<client-id>" -SubscriptionId "<subscription-id>" -AksRolesAtScope -IncludeCost
#>
param(
    [Parameter(Mandatory)][string]$IdentityClientId,
    [string]$ManagementGroupId,
    [switch]$AllSubscriptions,
    [string[]]$SubscriptionIds,
    [string]$SubscriptionId,
    [switch]$IncludeCost,
    [switch]$AksRolesAtScope,
    [switch]$WhatIf
)
$ErrorActionPreference = "Stop"

$ROLE_READER          = "acdd72a7-3385-48ef-bd42-f606fba81ae7"
$ROLE_AKS_CLUSTERUSER = "4abbcc35-e782-43d8-92c5-2d3f1bd2253f"
$ROLE_AKS_RBACREADER  = "7f6c6a51-bcf8-42ba-9220-52d62157d7db"
$ROLE_COST_READER     = "72fafb9e-0641-4937-9268-a91bfd8191a3"
$REPORT_MAX_CLUSTERS  = 100
$failures = New-Object System.Collections.Generic.List[string]

function Invoke-AzQuiet {
    # In Windows PowerShell 5.1, "Stop" plus redirected az stderr aborts the script: check $LASTEXITCODE instead.
    $ErrorActionPreference = "Continue"
    $out = & az @args 2>$null
    return $out
}

function Grant([string]$principalId, [string]$roleId, [string]$roleName, [string]$scope) {
    $exists = Invoke-AzQuiet role assignment list --assignee $principalId --scope $scope --role $roleId --include-inherited --query "[0].id" -o tsv
    if ($exists) { Write-Host "  [OK] $roleName already assigned  ->  $scope (or inherited)" -ForegroundColor Green; return }
    if ($WhatIf) { Write-Host "  [WHATIF] Would assign $roleName  ->  $scope" -ForegroundColor Magenta; return }
    $null = Invoke-AzQuiet role assignment create --assignee-object-id $principalId --assignee-principal-type ServicePrincipal `
        --role $roleId --scope $scope --only-show-errors -o none
    if ($LASTEXITCODE -ne 0) {
        $failures.Add("$roleName -> $scope")
        Write-Host "  [ERROR] $roleName  ->  $scope (check your permissions on that scope)" -ForegroundColor Red
    } else {
        Write-Host "  [OK] $roleName  ->  $scope" -ForegroundColor Green
    }
}

function Get-MgSubscriptions([string]$mg) {
    $url = "https://management.azure.com/providers/Microsoft.Management/managementGroups/$mg/descendants?api-version=2020-05-01"
    $subs = @()
    while ($url) {
        # On Windows az is a .cmd: quote the URL so cmd.exe does not cut the nextLink at "&".
        $urlArg = if ($env:OS -eq "Windows_NT") { "`"$url`"" } else { $url }
        $raw = Invoke-AzQuiet rest --method get --url $urlArg -o json
        if ($LASTEXITCODE -ne 0 -or -not $raw) { throw "Could not read Management Group '$mg'. Check the ID (not the display name) and your permissions." }
        $page = ($raw -join "`n") | ConvertFrom-Json
        $subs += @($page.value | Where-Object { $_.type -eq "Microsoft.Management/managementGroups/subscriptions" -or $_.type -eq "/subscriptions" } | ForEach-Object { $_.name })
        $url = $page.nextLink
    }
    return $subs
}

if ($WhatIf) { Write-Host "-WhatIf MODE: only shows what it would do; nothing is changed." -ForegroundColor Magenta }

Write-Host "`n== 1. Tenant, identity and subscriptions ==" -ForegroundColor Cyan
$tenantId = Invoke-AzQuiet account show --query tenantId -o tsv
if (-not $tenantId) { throw "No Azure CLI session. Run first: az login" }
$principalId = Invoke-AzQuiet ad sp show --id $IdentityClientId --query id -o tsv
if (-not $principalId) { throw "Identity with Client ID $IdentityClientId not found in this tenant." }
Write-Host "  Tenant: $tenantId"
Write-Host "  SRE Agent identity: clientId=$IdentityClientId  principalId=$principalId"

$scopes = @()
if ($ManagementGroupId) {
    $scopes = @("/providers/Microsoft.Management/managementGroups/$ManagementGroupId")
    $subs = @(Get-MgSubscriptions $ManagementGroupId)
} elseif ($AllSubscriptions) {
    $subs = @(Invoke-AzQuiet account list --all --query "[?tenantId=='$tenantId' && state=='Enabled'].id" -o tsv)
} elseif ($SubscriptionIds) {
    $subs = @($SubscriptionIds | ForEach-Object { $_.Split(",") } | ForEach-Object { $_.Trim() } | Where-Object { $_ })
} elseif ($SubscriptionId) {
    $subs = @($SubscriptionId)
} else {
    $subs = @(Invoke-AzQuiet account show --query id -o tsv)
}
$subs = @($subs | Where-Object { $_ } | ForEach-Object { $_.ToLower() } | Select-Object -Unique)
if (-not $subs) { throw "No subscription found in the requested scope." }
if (-not $scopes) { $scopes = @($subs | ForEach-Object { "/subscriptions/$_" }) }
Write-Host "  Subscriptions in scope: $($subs.Count)"

Write-Host "`n== 2. Read-only roles at the scope ==" -ForegroundColor Cyan
foreach ($scope in $scopes) {
    Grant $principalId $ROLE_READER "Reader" $scope
    if ($IncludeCost) { Grant $principalId $ROLE_COST_READER "Cost Management Reader" $scope }
    if ($AksRolesAtScope) {
        Grant $principalId $ROLE_AKS_CLUSTERUSER "Azure Kubernetes Service Cluster User Role" $scope
        Grant $principalId $ROLE_AKS_RBACREADER  "Azure Kubernetes Service RBAC Reader" $scope
    }
}

Write-Host "`n== 3. AKS clusters per subscription ==" -ForegroundColor Cyan
$subNames = @{}
$accounts = Invoke-AzQuiet account list --all -o json
if ($accounts) { foreach ($a in @(($accounts -join "`n") | ConvertFrom-Json | ForEach-Object { $_ })) { $subNames[$a.id.ToLower()] = $a.name } }
$found = @()
foreach ($sub in $subs) {
    $json = Invoke-AzQuiet aks list --subscription $sub --query "[].{name:name, rg:resourceGroup, id:id, managed:aadProfile.managed, azRbac:aadProfile.enableAzureRbac}" -o json
    $subName = $subNames[$sub]; if (-not $subName) { $subName = $sub }
    if ($LASTEXITCODE -ne 0) { $failures.Add("az aks list -> $sub"); Write-Host "  [ERROR] Could not list the AKS clusters of $subName ($sub)" -ForegroundColor Red; continue }
    # ForEach-Object unrolls the array (Windows PowerShell 5.1 ConvertFrom-Json returns it as a single object).
    $list = @(($json -join "`n") | ConvertFrom-Json | ForEach-Object { $_ })
    Write-Host ("  {0,-45} {1,3} AKS" -f $subName, $list.Count)
    foreach ($aks in $list) {
        $found += [pscustomobject]@{ Subscription = $subName; SubscriptionId = $sub; ResourceGroup = $aks.rg; Cluster = $aks.name; Id = $aks.id
                                     Managed = [bool]$aks.managed; AzureRbac = [bool]$aks.azRbac }
    }
}
if (-not $found) { Write-Host "  [WARNING] No AKS cluster found in the requested scope." -ForegroundColor Yellow }

if ($found -and -not $AksRolesAtScope) {
    Write-Host "`n== 4. AKS roles on each cluster ==" -ForegroundColor Cyan
    foreach ($aks in $found) {
        Write-Host " $($aks.Cluster)"
        Grant $principalId $ROLE_AKS_CLUSTERUSER "Azure Kubernetes Service Cluster User Role" $aks.Id
        Grant $principalId $ROLE_AKS_RBACREADER  "Azure Kubernetes Service RBAC Reader" $aks.Id
    }
} elseif ($found) {
    Write-Host "`n== 4. AKS roles already assigned at the scope (also covers future clusters) ==" -ForegroundColor Cyan
}

if ($found) {
    Write-Host "`n== 5. Summary ==" -ForegroundColor Cyan
    $summary = foreach ($aks in $found) {
        $mode = if ($aks.Managed -and $aks.AzureRbac) { "OK: Entra ID + Azure RBAC" }
                elseif ($aks.Managed) { "WARNING: Entra ID with Kubernetes RBAC -> workloads 'Not evaluated'" }
                else { "WARNING: no Entra ID -> ARM part only; workloads 'Not evaluated'" }
        [pscustomobject]@{ Subscription = $aks.Subscription; ResourceGroup = $aks.ResourceGroup; Cluster = $aks.Cluster; KubernetesRead = $mode }
    }
    $summary | Format-Table -AutoSize -Wrap
    $found | Select-Object Subscription, SubscriptionId, ResourceGroup, Cluster | Export-Csv -Path "aks-clusters.csv" -NoTypeInformation -Encoding UTF8
    $summary | Export-Csv -Path "aks-auth-modes.csv" -NoTypeInformation -Encoding UTF8
    $subCount = @($found | Select-Object -ExpandProperty SubscriptionId -Unique).Count
    Write-Host "  $($found.Count) AKS clusters in $subCount subscriptions. Details: aks-clusters.csv and aks-auth-modes.csv"
    if ($found.Count -gt $REPORT_MAX_CLUSTERS) {
        Write-Host "  [WARNING] More than $REPORT_MAX_CLUSTERS clusters: an 'all' report covers up to $REPORT_MAX_CLUSTERS; ask for it per subscription." -ForegroundColor Yellow
    }
}

Write-Host "`nNOTHING to paste into the tool: it discovers every AKS cluster the identity can read." -ForegroundColor Yellow
Write-Host "Permissions take 5-10 minutes to propagate. Then, in chat: /agent aks-waf-live -> 'List the AKS clusters by subscription'." -ForegroundColor Yellow
if ($failures.Count -gt 0) {
    Write-Host "`n$($failures.Count) operations failed:" -ForegroundColor Red
    $failures | ForEach-Object { Write-Host "  - $_" -ForegroundColor Red }
    exit 1
}

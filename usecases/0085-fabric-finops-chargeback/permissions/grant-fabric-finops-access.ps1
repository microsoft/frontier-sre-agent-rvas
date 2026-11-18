<#
.SYNOPSIS
    Grants the READ-ONLY access that the generate-fabric-chargeback-report tool needs in the tenant where Microsoft Fabric lives.
    Used by BOTH options of Case 11:
      Option A - same tenant : pass -PrincipalObjectId <object (principal) ID of the SRE Agent user-assigned managed identity>
      Option B - cross-tenant: pass -AppClientId <client ID of the multi-tenant app created by setup-cross-tenant-app.ps1>
                               (the script creates the app's service principal in this tenant if it does not exist yet)

.DESCRIPTION
    Idempotent. Safe to run again. Every step prints OK or CHECK, and a summary table is printed at the end.
      1. Security group (default sg-sre-agent-fabric) with the identity as member.
      2. Fabric tenant settings, scoped to that group only:
           - Service principals can call Fabric public APIs
           - Service principals can access read-only admin APIs
      3. Workspace role (default Viewer) for the group on every active shared workspace (Spark sessions; OneLake needs more, see README).
      4. Azure RBAC on each capacity subscription: Reader + Cost Management Reader.
    It does NOT grant any write role on Fabric items, capacities, billing or tenant settings to the identity.

.NOTES
    Run as a person who is Fabric Administrator, can create security groups in Entra ID and is Owner or
    User Access Administrator on the capacity subscription(s). Azure CLI 2.60+. Works in Windows PowerShell 5.1,
    PowerShell 7 and Azure Cloud Shell.

.EXAMPLE
    # Option A - same tenant
    ./grant-fabric-finops-access.ps1 -FabricTenantId <TENANT_ID> -SubscriptionId <SUB_ID> -PrincipalObjectId <UAMI_PRINCIPAL_ID>

.EXAMPLE
    # Option B - cross-tenant (run in the CUSTOMER / Fabric tenant)
    ./grant-fabric-finops-access.ps1 -FabricTenantId <TARGET_FABRIC_TENANT_ID> -SubscriptionId <SUB_ID> -AppClientId <FEDERATED_APP_CLIENT_ID>
#>
[CmdletBinding(DefaultParameterSetName = "SameTenant")]
param(
    [Parameter(Mandatory = $true)] [string]   $FabricTenantId,
    [Parameter(Mandatory = $true)] [string[]] $SubscriptionId,
    [Parameter(Mandatory = $true, ParameterSetName = "SameTenant")]  [string] $PrincipalObjectId,
    [Parameter(Mandatory = $true, ParameterSetName = "CrossTenant")] [string] $AppClientId,
    [string] $GroupName = "sg-sre-agent-fabric",
    [ValidateSet("Viewer", "Contributor")] [string] $WorkspaceRole = "Viewer",
    [switch] $SkipWorkspaces,
    [switch] $SkipLogin
)

$ErrorActionPreference = "Continue"
$fab     = "https://api.fabric.microsoft.com"
$pbi     = "https://analysis.windows.net/powerbi/api"
$tmpDir  = [IO.Path]::GetTempPath()
$results = New-Object System.Collections.ArrayList

function Note($step, $ok, $msg) {
    [void]$results.Add([pscustomobject]@{ Step = $step; Status = $(if ($ok) { "OK" } else { "CHECK" }); Detail = $msg })
    Write-Host ("[{0}] {1}: {2}" -f $(if ($ok) { "OK" } else { "!!" }), $step, $msg) -ForegroundColor $(if ($ok) { "Green" } else { "Yellow" })
}
function AzRest($method, $url, $resource, $body) {
    $a = @("rest", "--method", $method, "--url", $url)
    if ($resource) { $a += @("--resource", $resource) }
    $tmp = $null
    if ($body) {
        $tmp = Join-Path $tmpDir ("sre-fabric-" + [guid]::NewGuid().ToString("N") + ".json")
        [IO.File]::WriteAllText($tmp, ($body | ConvertTo-Json -Depth 8), (New-Object Text.UTF8Encoding($false)))
        $a += @("--body", "@$tmp", "--headers", "Content-Type=application/json")
    }
    $errFile = Join-Path $tmpDir "sre-fabric-err.txt"
    $out = & az @a 2> $errFile
    $code = $LASTEXITCODE
    if ($tmp) { Remove-Item $tmp -ErrorAction SilentlyContinue }
    $txt = ($out -join "`n").Trim()
    $obj = $null
    if ($txt) { try { $obj = $txt | ConvertFrom-Json } catch { } }
    [pscustomobject]@{ ok = ($code -eq 0); data = $obj; err = ((Get-Content $errFile -Raw -ErrorAction SilentlyContinue) -replace "\s+", " ") }
}

# ---------- 0. Sign in to the Fabric tenant ----------
if (-not $SkipLogin) { az login --tenant $FabricTenantId --allow-no-subscriptions | Out-Null }
$current = az account show --query tenantId -o tsv
if ($current -ne $FabricTenantId) { Write-Host "Signed in to tenant $current, expected $FabricTenantId. Run: az login --tenant $FabricTenantId" -ForegroundColor Red; return }

# ---------- 1. Resolve the identity (service principal object ID) ----------
if ($PSCmdlet.ParameterSetName -eq "CrossTenant") {
    $spId = az ad sp show --id $AppClientId --query id -o tsv 2>$null
    if (-not $spId) {
        Write-Host "Creating the service principal of the multi-tenant app in this tenant (equivalent to admin consent)..."
        $spId = az ad sp create --id $AppClientId --query id -o tsv
    }
    Note "Identity" ([bool]$spId) $(if ($spId) { "Service principal of app $AppClientId = $spId" } else { "Could not create the service principal. Check that the app is multi-tenant and that you can consent apps." })
} else {
    $spId = az ad sp show --id $PrincipalObjectId --query id -o tsv 2>$null
    Note "Identity" ([bool]$spId) $(if ($spId) { "Managed identity service principal $spId found" } else { "No service principal with object ID $PrincipalObjectId in this tenant. Use the Object (principal) ID of the UAMI, not its Client ID." })
}
if (-not $spId) { return }

# ---------- 2. Security group ----------
$gid = az ad group show --group $GroupName --query id -o tsv 2>$null
if (-not $gid) { $gid = az ad group create --display-name $GroupName --mail-nickname $GroupName --description "Read-only identities for the Azure SRE Agent Fabric FinOps tool" --query id -o tsv }
if ($gid) {
    $in = az ad group member check --group $gid --member-id $spId --query value -o tsv
    if ($in -ne "true") { az ad group member add --group $gid --member-id $spId | Out-Null }
    if ($in -ne "true" -and $LASTEXITCODE -ne 0) { Note "Group $GroupName" $false "Could not add the identity to the group. Add it in Entra ID and run the script again."; return }
    Note "Group $GroupName" $true "Identity is a member (group id $gid)"
} else { Note "Group $GroupName" $false "Could not create the group. Create it in Entra ID and add the identity manually."; return }

# ---------- 3. Fabric tenant settings (scoped to the group) ----------
$ts = AzRest "get" "$fab/v1/admin/tenantsettings" $fab $null
if (-not $ts.ok) {
    Note "Tenant settings" $false "Could not read them ($($ts.err)). Enable them in Fabric > Admin portal > Tenant settings for $GroupName."
} else {
    $wanted = @(
        @{ label = "Service principals can call Fabric public APIs";      match = "Service principals can (call|use) Fabric" },
        @{ label = "Service principals can access read-only admin APIs";  match = "read-only admin API" }
    )
    foreach ($w in $wanted) {
        $set = $ts.data.tenantSettings | Where-Object { $_.title -match $w.match } | Select-Object -First 1
        if (-not $set) { Note $w.label $false "Setting not found by title; enable it in the Admin portal"; continue }
        $groups = @()
        if ($set.enabledSecurityGroups) { $groups += $set.enabledSecurityGroups | ForEach-Object { @{ graphId = $_.graphId; name = $_.name } } }
        $wholeOrg = $set.enabled -and $groups.Count -eq 0
        if ($wholeOrg -or ($set.enabled -and ($groups.graphId -contains $gid))) { Note $w.label $true "Already enabled (covers $GroupName)"; continue }
        if (-not ($groups.graphId -contains $gid)) { $groups += @{ graphId = $gid; name = $GroupName } }
        $u = AzRest "post" "$fab/v1/admin/tenantsettings/$($set.settingName)/update" $fab @{ enabled = $true; enabledSecurityGroups = $groups }
        if ($u.ok) { Note $w.label $true "Enabled for $GroupName" } else { Note $w.label $false "API update failed ($($u.err)). Enable it in the Admin portal for $GroupName" }
    }
}

# ---------- 4. Workspace role for the group (Spark sessions, OneLake) ----------
if ($SkipWorkspaces) {
    Note "Workspaces" $true "Skipped (-SkipWorkspaces). Spark and OneLake sections will show as partial."
} else {
    $ws = AzRest "get" "https://api.powerbi.com/v1.0/myorg/admin/groups?`$top=5000&`$filter=type%20eq%20'Workspace'%20and%20state%20eq%20'Active'" $pbi $null
    if (-not $ws.ok) {
        Note "Workspaces" $false "Could not list them ($($ws.err)). Add $GroupName as $WorkspaceRole in each workspace (Manage access)."
    } else {
        $list = @($ws.data.value)
        $added = 0; $failed = @()
        foreach ($w in $list) {
            $r = AzRest "post" "https://api.powerbi.com/v1.0/myorg/admin/groups/$($w.id)/users" $pbi @{ identifier = $gid; principalType = "Group"; groupUserAccessRight = $WorkspaceRole }
            if ($r.ok -or $r.err -match "already|exist|Duplicate") { $added++ } else { $failed += $w.name }
            Start-Sleep -Milliseconds 300
        }
        Note "Workspaces" ($failed.Count -eq 0) ("$added of $($list.Count) workspaces with $GroupName as $WorkspaceRole" + $(if ($failed) { "; failed: " + ($failed -join ", ") } else { "" }))
        $metrics = $list | Where-Object { $_.name -match "Capacity Metrics" }
        Note "Capacity Metrics app" $true $(if ($metrics) { "Installed: $($metrics.name -join ', ')" } else { "Not installed (optional; the report still works)" })
    }
}

# ---------- 5. Azure RBAC on each capacity subscription ----------
foreach ($sub in $SubscriptionId) {
    foreach ($role in @("Reader", "Cost Management Reader")) {
        $has = az role assignment list --assignee $spId --role $role --scope "/subscriptions/$sub" --query "length(@)" -o tsv 2>$null
        if ($has -gt 0) { Note "$role on $sub" $true "Already assigned" ; continue }
        az role assignment create --assignee-object-id $spId --assignee-principal-type ServicePrincipal --role $role --scope "/subscriptions/$sub" | Out-Null
        Note "$role on $sub" ($LASTEXITCODE -eq 0) $(if ($LASTEXITCODE -eq 0) { "Assigned" } else { "Failed: you need Owner or User Access Administrator on the subscription" })
    }
    $caps = @(az resource list --subscription $sub --resource-type Microsoft.Fabric/capacities --query "[].name" -o tsv 2>$null)
    Note "Capacities in $sub" ($caps.Count -gt 0) $(if ($caps.Count) { "Found: " + ($caps -join ", ") } else { "No Microsoft.Fabric/capacities found in this subscription" })
}

Write-Host "`n================ SUMMARY ================" -ForegroundColor Cyan
$results | Format-Table -AutoSize -Wrap
Write-Host "Wait ~15 minutes for Fabric to propagate tenant settings and group membership before the first run." -ForegroundColor Cyan

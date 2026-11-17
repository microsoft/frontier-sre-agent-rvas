<#
.SYNOPSIS
  Grants the SRE Agent identity READ-ONLY access to EVERY Azure Databricks workspace in a Management Group
  (or in one, several or all subscriptions) in a single run.

.DESCRIPTION
  1) Azure (ARM plane), ONCE at the scope (Management Group or each subscription):
       - Reader                                          -> workspace configuration, network and managed resource group
       - Cost Management Reader (optional, -IncludeCost) -> costs (DBU versus infrastructure)
     Assigned at the Management Group, they are inherited by all its subscriptions, including future ones.
  2) Discovers every workspace in the scope with Azure Resource Graph (no matter how many subscriptions).
  3) Inside EACH workspace (Databricks plane):
       - adds the identity as a service principal (Entra ID managed, workspace-access + databricks-sql-access,
         NEVER admin);
       - CAN_VIEW on the existing jobs, pipelines and SQL warehouses;
       - Unity Catalog: BROWSE + USE_CATALOG + USE_SCHEMA on the catalogs (metadata only, never SELECT or files).
     If a workspace fails (no admin rights, private network...), it is recorded and the script continues.
  4) Prints a per-workspace summary and saves it to databricks-access-summary.csv.

  NOTHING has to be pasted into the tool: it discovers every workspace the identity can read.

  The person running it needs:
    - Owner, User Access Administrator or Role Based Access Control Administrator on the scope (step 1);
    - Workspace Admin on the workspaces (step 3). Workspaces where they are not admin are reported as "NO ACCESS".
  Re-running it is safe (nothing is duplicated). Re-run it from time to time: new jobs, pipelines and warehouses
  only get CAN_VIEW when the script runs again.

.EXAMPLE
  # Recommended: the whole Management Group, with costs
  .\grant-databricks-permissions.ps1 -IdentityClientId "<client-id>" -ManagementGroupId "<management-group-id>" -IncludeCost

.EXAMPLE
  # See what it would do, without changing anything
  .\grant-databricks-permissions.ps1 -IdentityClientId "<client-id>" -ManagementGroupId "<management-group-id>" -IncludeCost -WhatIf

.EXAMPLE
  # Only some subscriptions, or only some workspaces ("subscription/resourceGroup/name")
  .\grant-databricks-permissions.ps1 -IdentityClientId "<client-id>" -SubscriptionIds "<sub-1>","<sub-2>" -IncludeCost
  .\grant-databricks-permissions.ps1 -IdentityClientId "<client-id>" -ManagementGroupId "<mg>" -Workspaces "<sub>/<rg>/<workspace>"
#>
param(
    [Parameter(Mandatory = $true)][string]$IdentityClientId,
    [string]$ManagementGroupId,
    [switch]$AllSubscriptions,
    [string[]]$SubscriptionIds,
    [string]$SubscriptionId,
    [string[]]$Workspaces,
    [switch]$IncludeCost,
    [switch]$SkipDatabricksGrants,
    [switch]$SkipUnityCatalog,
    [switch]$WhatIf
)

$ErrorActionPreference = "Stop"
$DatabricksResource = "2ff814a6-3304-4ab8-85cb-cd0e6f879c1d"
$ReaderRoleId = "acdd72a7-3385-48ef-bd42-f606fba81ae7"
$CostReaderRoleId = "72fafb9e-0641-4937-9268-a91bfd8191a3"
$SkipCatalogs = @("system", "hive_metastore", "samples", "__databricks_internal")
$MaxWorkspaces = 1000

function Write-Step($t) { Write-Host "`n== $t ==" -ForegroundColor Cyan }
function Write-Ok($t) { Write-Host "  [OK] $t" -ForegroundColor Green }
function Write-Warn2($t) { Write-Host "  [WARNING] $t" -ForegroundColor Yellow }
function Write-Plan($t) { Write-Host "  [WHATIF] $t" -ForegroundColor Magenta }
function Invoke-AzQuiet {
    # In Windows PowerShell 5.1, "Stop" plus redirected az stderr aborts the script: check $LASTEXITCODE instead.
    $ErrorActionPreference = "Continue"
    $out = & az @args 2>$null
    return $out
}
function ConvertFrom-AzJson($raw) { if ($raw) { return (($raw -join "`n") | ConvertFrom-Json) } return $null }

if (-not (Get-Command az -ErrorAction SilentlyContinue)) { throw "Azure CLI (az) is missing. Install it and run 'az login'." }
if ($WhatIf) { Write-Host "-WhatIf MODE: only shows what it would do; nothing is changed." -ForegroundColor Magenta }

Write-Step "Context"
$acct = ConvertFrom-AzJson (Invoke-AzQuiet account show -o json)
if (-not $acct) { throw "No Azure CLI session. Run 'az login' in the right tenant." }
$TenantId = $acct.tenantId
Write-Ok "Tenant: $TenantId (user $($acct.user.name))"
$sp = ConvertFrom-AzJson (Invoke-AzQuiet ad sp show --id $IdentityClientId -o json)
if (-not $sp) { throw "Identity with Client ID $IdentityClientId not found in this tenant. Copy the Client ID of the agent's managed identity (Azure portal > agent resource group > identity id-... > Overview)." }
$PrincipalId = $sp.id
$SpName = $sp.displayName
Write-Ok "Agent identity: $SpName (objectId $PrincipalId)"

# ---- Scope ---------------------------------------------------------------------------------
$scopes = @()
$argScope = @{}
if ($ManagementGroupId) {
    $scopes = @("/providers/Microsoft.Management/managementGroups/$ManagementGroupId")
    $argScope = @{ managementGroups = @($ManagementGroupId) }
    Write-Ok "Scope: Management Group $ManagementGroupId (all its subscriptions, including future ones)"
} elseif ($AllSubscriptions) {
    $subs = @(Invoke-AzQuiet account list --all --query "[?tenantId=='$TenantId' && state=='Enabled'].id" -o tsv)
    $scopes = @($subs | ForEach-Object { "/subscriptions/$_" })
    $argScope = @{ subscriptions = @($subs) }
    Write-Ok "Scope: $($subs.Count) enabled subscriptions of the tenant"
} else {
    $subs = @()
    if ($SubscriptionIds) { $subs = @($SubscriptionIds | ForEach-Object { $_.Split(",") } | ForEach-Object { $_.Trim() } | Where-Object { $_ }) }
    elseif ($SubscriptionId) { $subs = @($SubscriptionId) }
    else { $subs = @($acct.id) }
    $subs = @($subs | ForEach-Object { $_.ToLower() } | Select-Object -Unique)
    $scopes = @($subs | ForEach-Object { "/subscriptions/$_" })
    $argScope = @{ subscriptions = @($subs) }
    Write-Ok "Scope: $($subs.Count) subscription(s)"
}
if (-not $scopes) { throw "No scope found (Management Group or subscription)." }

# ---- 1. Azure roles -------------------------------------------------------------------------
$failures = New-Object System.Collections.Generic.List[string]
function Grant-Role($roleId, $roleName, $scope) {
    $exists = Invoke-AzQuiet role assignment list --assignee $PrincipalId --scope $scope --role $roleId --include-inherited --query "[0].id" -o tsv
    if ($exists) { Write-Ok "$roleName already assigned on $scope (or inherited)"; return }
    if ($WhatIf) { Write-Plan "Would assign $roleName on $scope"; return }
    $null = Invoke-AzQuiet role assignment create --assignee-object-id $PrincipalId --assignee-principal-type ServicePrincipal --role $roleId --scope $scope --only-show-errors -o none
    if ($LASTEXITCODE -ne 0) { Write-Warn2 "Could not assign $roleName on $scope (Owner, User Access Administrator or Role Based Access Control Administrator is required)"; $failures.Add("$roleName on $scope") }
    else { Write-Ok "$roleName assigned on $scope" }
}
Write-Step "1/3 Azure: read-only roles at the scope"
foreach ($scope in $scopes) {
    Grant-Role $ReaderRoleId "Reader" $scope
    if ($IncludeCost) { Grant-Role $CostReaderRoleId "Cost Management Reader" $scope }
}

# ---- 2. Discover workspaces with Azure Resource Graph --------------------------------------
Write-Step "2/3 Databricks workspaces in the scope (Azure Resource Graph)"
$query = "resources | where type =~ 'microsoft.databricks/workspaces' | project id, name, resourceGroup, subscriptionId, " +
         "workspaceUrl = tostring(properties.workspaceUrl), sku = tostring(sku.name), publicNetworkAccess = tostring(properties.publicNetworkAccess) " +
         "| order by subscriptionId asc, name asc"
$rows = @()
$skip = $null
do {
    $body = @{ query = $query; options = @{ '$top' = 1000; resultFormat = "objectArray" } } + $argScope
    if ($skip) { $body.options['$skipToken'] = $skip }
    $tmp = [IO.Path]::GetTempFileName()
    [IO.File]::WriteAllText($tmp, ($body | ConvertTo-Json -Depth 6 -Compress), (New-Object Text.UTF8Encoding $false))
    $raw = Invoke-AzQuiet rest --method post --url "https://management.azure.com/providers/Microsoft.ResourceGraph/resources?api-version=2022-10-01" --body "@$tmp" -o json
    $code = $LASTEXITCODE
    Remove-Item $tmp -ErrorAction SilentlyContinue
    if ($code -ne 0 -or -not $raw) { throw "Azure Resource Graph did not respond. Check that your user can read the requested scope." }
    $page = ($raw -join "`n") | ConvertFrom-Json
    $rows += @($page.data | ForEach-Object { $_ })
    $skip = $page.'$skipToken'
} while ($skip -and $rows.Count -lt $MaxWorkspaces)

if ($Workspaces) {
    $wanted = @($Workspaces | ForEach-Object { $_.Trim().ToLower() })
    $rows = @($rows | Where-Object {
        $wanted -contains ("$($_.subscriptionId)/$($_.resourceGroup)/$($_.name)").ToLower() -or $wanted -contains ("$($_.resourceGroup)/$($_.name)").ToLower()
    })
}
if (-not $rows) { throw "No Databricks workspace found in the requested scope." }
$subNames = @{}
foreach ($s in @(ConvertFrom-AzJson (Invoke-AzQuiet account list --all -o json) | ForEach-Object { $_ })) { $subNames[$s.id.ToLower()] = $s.name }
Write-Ok "$($rows.Count) workspaces in $(@($rows | Select-Object -ExpandProperty subscriptionId -Unique).Count) subscriptions"
foreach ($w in $rows) {
    $sn = $subNames[$w.subscriptionId.ToLower()]; if (-not $sn) { $sn = $w.subscriptionId }
    Write-Host ("    {0,-40} {1,-30} {2}" -f $w.name, $sn, $w.workspaceUrl)
}

# ---- 3. Inside each workspace ---------------------------------------------------------------
$summary = New-Object System.Collections.Generic.List[object]
if ($SkipDatabricksGrants) {
    Write-Step "3/3 Databricks: skipped (-SkipDatabricksGrants). The in-workspace part will show as 'no access'."
} else {
    Write-Step "3/3 Databricks: add the identity to each workspace"
    $token = Invoke-AzQuiet account get-access-token --resource $DatabricksResource --query accessToken -o tsv
    if (-not $token) { throw "Could not get an Azure Databricks token for your user." }
    $hdr = @{ Authorization = "Bearer $token"; "Content-Type" = "application/json" }

    function Invoke-Dbx($wsHost, $method, $path, $body) {
        $uri = "https://$wsHost$path"
        if ($body) { return Invoke-RestMethod -Method $method -Uri $uri -Headers $hdr -Body ($body | ConvertTo-Json -Depth 10) -TimeoutSec 60 -ErrorAction Stop }
        return Invoke-RestMethod -Method $method -Uri $uri -Headers $hdr -TimeoutSec 60 -ErrorAction Stop
    }
    function Get-HttpCode($err) {
        try { return [int]$err.Exception.Response.StatusCode } catch { return 0 }
    }
    function Grant-View($wsHost, $objType, $id, $label) {
        if ($WhatIf) { return $true }
        $acl = @{ access_control_list = @(@{ service_principal_name = $IdentityClientId; permission_level = "CAN_VIEW" }) }
        try { Invoke-Dbx $wsHost "PATCH" "/api/2.0/permissions/$objType/$id" $acl | Out-Null; return $true }
        catch { Write-Warn2 "CAN_VIEW on $label failed: $($_.Exception.Message)"; return $false }
    }

    $i = 0
    foreach ($w in $rows) {
        $i++
        $h = $w.workspaceUrl
        $sn = $subNames[$w.subscriptionId.ToLower()]; if (-not $sn) { $sn = $w.subscriptionId }
        $row = [ordered]@{ Workspace = $w.name; Subscription = $sn; ResourceGroup = $w.resourceGroup; Host = $h
                           Identity = ""; Jobs = 0; Pipelines = 0; Warehouses = 0; Catalogs = 0; Status = "" }
        Write-Host "`n  [$i/$($rows.Count)] $($w.name) ($h)" -ForegroundColor White
        if (-not $h) { $row.Status = "NO URL (workspace not deployed)"; $summary.Add([pscustomobject]$row); continue }
        try {
            $filter = [uri]::EscapeDataString("applicationId eq `"$IdentityClientId`"")
            $found = Invoke-Dbx $h "GET" "/api/2.0/preview/scim/v2/ServicePrincipals?filter=$filter" $null
            $wanted = @("workspace-access", "databricks-sql-access")
            if ($found.totalResults -gt 0) {
                $spRes = @($found.Resources)[0]
                $have = @($spRes.entitlements | ForEach-Object { $_.value })
                $missing = @($wanted | Where-Object { $have -notcontains $_ })
                if (-not $missing) { $row.Identity = "already there"; Write-Ok "The identity was already added" }
                elseif ($WhatIf) { $row.Identity = "already there"; Write-Plan "Would add the entitlements $($missing -join ', ')" }
                else {
                    $patch = @{ schemas = @("urn:ietf:params:scim:api:messages:2.0:PatchOp")
                                Operations = @(@{ op = "add"; path = "entitlements"; value = @($missing | ForEach-Object { @{ value = $_ } }) }) }
                    Invoke-Dbx $h "PATCH" "/api/2.0/preview/scim/v2/ServicePrincipals/$($spRes.id)" $patch | Out-Null
                    $row.Identity = "already there"; Write-Ok "The identity was already added; entitlements added: $($missing -join ', ')"
                }
            }
            elseif ($WhatIf) { $row.Identity = "would be added"; Write-Plan "Would add the identity (workspace-access + databricks-sql-access, no admin)" }
            else {
                $body = @{
                    schemas       = @("urn:ietf:params:scim:schemas:core:2.0:ServicePrincipal")
                    applicationId = $IdentityClientId
                    displayName   = $SpName
                    entitlements  = @($wanted | ForEach-Object { @{ value = $_ } })
                }
                Invoke-Dbx $h "POST" "/api/2.0/preview/scim/v2/ServicePrincipals" $body | Out-Null
                $row.Identity = "added"; Write-Ok "Identity added (workspace-access + databricks-sql-access, no admin)"
            }
        }
        catch {
            $code = Get-HttpCode $_
            $detail = ""
            try { $detail = [string]$_.ErrorDetails.Message } catch { }
            if ($detail -match "Did not find workspace") { $row.Status = "NOT INITIALIZED: open it once from the Azure portal (Launch Workspace) and re-run" }
            elseif ($code -eq 401 -or $code -eq 403) { $row.Status = "NO ACCESS: your user is not a Workspace Admin" }
            elseif ($code -eq 0) { $row.Status = "NO ACCESS: the workspace is not reachable (private network or DNS)" }
            else { $row.Status = "HTTP ERROR $code" }
            Write-Warn2 "$($row.Status). Continuing with the next one."
            $summary.Add([pscustomobject]$row)
            continue
        }

        try {
            $pt = ""
            do {
                $q = "/api/2.1/jobs/list?limit=100"; if ($pt) { $q += "&page_token=$pt" }
                $r = Invoke-Dbx $h "GET" $q $null
                foreach ($j in @($r.jobs)) { if ($j -and (Grant-View $h "jobs" $j.job_id "job $($j.job_id)")) { $row.Jobs++ } }
                $pt = $r.next_page_token
            } while ($pt)
            $pt = ""
            do {
                $q = "/api/2.0/pipelines?max_results=100"; if ($pt) { $q += "&page_token=$pt" }
                $r = Invoke-Dbx $h "GET" $q $null
                foreach ($p in @($r.statuses)) { if ($p -and (Grant-View $h "pipelines" $p.pipeline_id "pipeline $($p.name)")) { $row.Pipelines++ } }
                $pt = $r.next_page_token
            } while ($pt)
            $r = Invoke-Dbx $h "GET" "/api/2.0/sql/warehouses" $null
            foreach ($s in @($r.warehouses)) { if ($s -and (Grant-View $h "warehouses" $s.id "warehouse $($s.name)")) { $row.Warehouses++ } }
            Write-Ok "CAN_VIEW: $($row.Jobs) jobs, $($row.Pipelines) pipelines, $($row.Warehouses) SQL warehouses"
        }
        catch { Write-Warn2 "CAN_VIEW incomplete: $($_.Exception.Message)" }

        if (-not $SkipUnityCatalog) {
            try {
                $cats = @(); $pt = ""
                do {
                    $q = "/api/2.1/unity-catalog/catalogs?max_results=100"; if ($pt) { $q += "&page_token=$pt" }
                    $r = Invoke-Dbx $h "GET" $q $null
                    $cats += @($r.catalogs); $pt = $r.next_page_token
                } while ($pt)
                foreach ($c in $cats) {
                    if (-not $c -or $SkipCatalogs -contains $c.name) { continue }
                    if ($WhatIf) { $row.Catalogs++; continue }
                    $chg = @{ changes = @(@{ principal = $IdentityClientId; add = @("BROWSE", "USE_CATALOG", "USE_SCHEMA") }) }
                    try {
                        Invoke-Dbx $h "PATCH" "/api/2.1/unity-catalog/permissions/catalog/$([uri]::EscapeDataString($c.name))" $chg | Out-Null
                        $row.Catalogs++
                    }
                    catch { Write-Warn2 "Catalog $($c.name): $($_.Exception.Message) (catalog owner or metastore admin required)" }
                }
                Write-Ok "Unity Catalog: BROWSE + USE_CATALOG + USE_SCHEMA on $($row.Catalogs) catalogs"
            }
            catch { Write-Warn2 "Unity Catalog not available in this workspace: $($_.Exception.Message)" }
        }
        $row.Status = if ($WhatIf) { "WHATIF (no changes)" } else { "OK" }
        $summary.Add([pscustomobject]$row)
    }
}

# ---- Summary --------------------------------------------------------------------------------
Write-Step "Summary"
if ($summary.Count -gt 0) {
    $summary | Format-Table Workspace, Subscription, Identity, Jobs, Pipelines, Warehouses, Catalogs, Status -AutoSize -Wrap
    $summary | Export-Csv -Path "databricks-access-summary.csv" -NoTypeInformation -Encoding UTF8
    $ok = @($summary | Where-Object { $_.Status -eq "OK" }).Count
    Write-Host "  $ok of $($summary.Count) workspaces with full access. Details: databricks-access-summary.csv"
}
if ($failures.Count -gt 0) { Write-Warn2 "Azure role failures: $($failures -join '; ')" }
Write-Host "`nNOTHING to paste into the tool: it discovers every workspace the identity can read." -ForegroundColor Yellow
Write-Host "Permissions take 5-10 minutes to propagate. Then, in chat: /agent databricks-dependency-live -> 'List the Databricks workspaces'." -ForegroundColor Yellow

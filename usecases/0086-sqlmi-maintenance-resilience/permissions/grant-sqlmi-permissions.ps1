<#
.SYNOPSIS
  Grants the Azure SRE Agent managed identity the READ-ONLY permissions that the
  generate-sqlmi-maintenance-report tool needs, and writes the tool configuration file.

.DESCRIPTION
  For every subscription that hosts SQL Managed Instances:
    - Reader               (MI inventory, windows, failover groups, Resource Graph, Service Health)
    - Monitoring Reader    (CPU metrics, Resource Health, Activity Log, alert rules)
  For every Log Analytics workspace where the applications' Application Insights write:
    - Log Analytics Reader (AppDependencies and AppRequests to measure user impact)

  If you omit -WorkspaceResourceIds the script discovers them: it lists the Application Insights
  components in the subscriptions (-AppSubscriptionIds or, by default, -SubscriptionIds) and takes the
  workspace each one writes to. -DiscoverOnly only shows what it would find, without granting anything.

  None of these roles can change resources. Idempotent: existing assignments are skipped.
  At the end it writes sqlmi-tool-config.txt with the values for the tool (guide, step 4).

.EXAMPLE
  ./grant-sqlmi-permissions.ps1 -AgentIdentityName "<SRE_AGENT_UAMI_NAME>" -AgentIdentityResourceGroup "<UAMI_RG>" `
      -SubscriptionIds "<SUB_ID_1>","<SUB_ID_2>" `
      -WorkspaceResourceIds "/subscriptions/<SUB>/resourceGroups/<RG>/providers/Microsoft.OperationalInsights/workspaces/<WS>"

.EXAMPLE
  # Discover the Application Insights workspaces automatically
  ./grant-sqlmi-permissions.ps1 -AgentIdentityName "<SRE_AGENT_UAMI_NAME>" -AgentIdentityResourceGroup "<UAMI_RG>" `
      -SubscriptionIds "<SUB_ID_1>","<SUB_ID_2>"

.EXAMPLE
  # Only show which workspaces it would find (no identity needed, nothing granted)
  ./grant-sqlmi-permissions.ps1 -SubscriptionIds "<SUB_ID_1>" -DiscoverOnly
#>
[CmdletBinding(DefaultParameterSetName = "Grant")]
param(
  [Parameter(Mandatory, ParameterSetName = "Grant")] [string] $AgentIdentityName,
  [Parameter(Mandatory, ParameterSetName = "Grant")] [string] $AgentIdentityResourceGroup,
  [Parameter(Mandatory)] [string[]] $SubscriptionIds,
  [string[]] $WorkspaceResourceIds = @(),
  [string[]] $AppSubscriptionIds = @(),
  [Parameter(Mandatory, ParameterSetName = "Discover")] [switch] $DiscoverOnly,
  [string] $IdentitySubscriptionId = "",
  [string] $OutputFile = "sqlmi-tool-config.txt"
)
$ErrorActionPreference = "Stop"

function Invoke-Az {
  param([string[]] $Arguments)
  $out = & az @Arguments 2>&1
  if ($LASTEXITCODE -ne 0) { throw "az $($Arguments -join ' ') failed:`n$out" }
  return $out
}

function Find-AppInsightsWorkspaces([string[]] $Subscriptions) {
  Write-Host "   Looking for Application Insights in: $($Subscriptions -join ', ')"
  $found = [ordered]@{}
  foreach ($sub in $Subscriptions) {
    $url = "https://management.azure.com/subscriptions/$sub/providers/Microsoft.Insights/components?api-version=2020-02-02"
    while ($url) {
      try {
        $page = (Invoke-Az @("rest", "--method", "get", "--url", $url, "-o", "json")) -join "`n" | ConvertFrom-Json
      } catch {
        Write-Warning "No access to list Application Insights in $sub"; break
      }
      foreach ($c in $page.value) {
        $ws = $c.properties.WorkspaceResourceId
        if (-not $ws) { Write-Warning "   $($c.name): classic Application Insights (no workspace); the tool cannot measure it."; continue }
        $key = $ws.ToLowerInvariant()
        if (-not $found.Contains($key)) { $found[$key] = [pscustomobject]@{ Id = $ws; Apps = [System.Collections.Generic.List[string]]::new() } }
        $found[$key].Apps.Add($c.name)
      }
      $url = $page.nextLink
    }
  }
  Write-Host "   Workspaces found: $($found.Count)"
  foreach ($f in $found.Values) { Write-Host "   - $(($f.Id -split '/')[-1])  <-  $($f.Apps -join ', ')" }
  if ($found.Count -eq 0) { Write-Warning "No workspace-based Application Insights found: the tool cannot measure user impact per application." }
  return @($found.Values | ForEach-Object { $_.Id })
}

$appSubs = if ($AppSubscriptionIds) { $AppSubscriptionIds } else { $SubscriptionIds }
if ($DiscoverOnly) {
  if (-not (Get-Command az -ErrorAction SilentlyContinue)) { throw "Install Azure CLI and run 'az login'." }
  $null = Find-AppInsightsWorkspaces $appSubs
  Write-Host "`n-DiscoverOnly mode: nothing was granted. Run it again without -DiscoverOnly to apply." -ForegroundColor Yellow
  return
}

if (-not (Get-Command az -ErrorAction SilentlyContinue)) { throw "Install Azure CLI and run 'az login'." }
$idSub = if ($IdentitySubscriptionId) { $IdentitySubscriptionId } else { $SubscriptionIds[0] }

Write-Host "1) SRE Agent managed identity: $AgentIdentityName" -ForegroundColor Cyan
$identity = Invoke-Az @("identity", "show", "-n", $AgentIdentityName, "-g", $AgentIdentityResourceGroup,
                        "--subscription", $idSub, "-o", "json") | ConvertFrom-Json
$principalId = $identity.principalId
$clientId = $identity.clientId
Write-Host "   clientId    = $clientId"
Write-Host "   principalId = $principalId"

function Grant-Role([string] $Role, [string] $Scope) {
  $existing = Invoke-Az @("role", "assignment", "list", "--assignee-object-id", $principalId, "--role", $Role,
                          "--scope", $Scope, "--query", "length(@)", "-o", "tsv")
  if ([int]$existing -gt 0) { Write-Host "   = $Role already assigned on $Scope"; return }
  Invoke-Az @("role", "assignment", "create", "--assignee-object-id", $principalId,
              "--assignee-principal-type", "ServicePrincipal", "--role", $Role, "--scope", $Scope, "-o", "none") | Out-Null
  Write-Host "   + $Role on $Scope" -ForegroundColor Green
}

Write-Host "2) Subscription roles (Reader + Monitoring Reader)" -ForegroundColor Cyan
foreach ($sub in $SubscriptionIds) {
  Grant-Role "Reader" "/subscriptions/$sub"
  Grant-Role "Monitoring Reader" "/subscriptions/$sub"
}

$workspaceIds = @()
Write-Host "3) Log Analytics workspace roles (Log Analytics Reader)" -ForegroundColor Cyan
if (-not $WorkspaceResourceIds) {
  Write-Host "   No -WorkspaceResourceIds: automatic discovery."
  $WorkspaceResourceIds = Find-AppInsightsWorkspaces $appSubs
}
foreach ($ws in $WorkspaceResourceIds) {
  Grant-Role "Log Analytics Reader" $ws
  $wsSub = ($ws -split "/")[2]
  $customerId = Invoke-Az @("resource", "show", "--ids", $ws, "--subscription", $wsSub,
                            "--query", "properties.customerId", "-o", "tsv")
  $workspaceIds += $customerId.Trim()
}

Write-Host "4) Tool configuration file: $OutputFile" -ForegroundColor Cyan
@(
  "# Values for generate-sqlmi-maintenance-report (CONFIGURE block)",
  "MANAGED_IDENTITY_CLIENT_ID = `"$clientId`"",
  "SUBSCRIPTION_IDS = `"$($SubscriptionIds -join ',')`"",
  "LOG_ANALYTICS_WORKSPACE_IDS = `"$($workspaceIds -join ',')`""
) | Set-Content -Path $OutputFile -Encoding utf8
Get-Content $OutputFile | ForEach-Object { Write-Host "   $_" }
Write-Host "`nDone. Role assignments can take up to 10 minutes to propagate." -ForegroundColor Green

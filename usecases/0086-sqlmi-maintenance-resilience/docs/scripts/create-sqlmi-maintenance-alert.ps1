<#
.SYNOPSIS
  Creates the Service Health alert for planned maintenance of Azure SQL Managed Instance.

.DESCRIPTION
  Azure notifies 24 h before, at the start and at the end of every planned SQL MI maintenance,
  but ONLY if a Service Health alert exists. This script creates (or reuses) an action group
  with email receivers and an activity log alert:
    category = ServiceHealth, incidentType = Maintenance, service = "SQL Managed Instance".
  Idempotent. Requires Monitoring Contributor (or Contributor) on the resource group.

.EXAMPLE
  # With an action group that already exists (recommended if you already have one for operations)
  ./create-sqlmi-maintenance-alert.ps1 -SubscriptionId "<SUB_ID>" -ResourceGroup "rg-monitoring" `
      -ActionGroupId "/subscriptions/<SUB_ID>/resourceGroups/rg-monitoring/providers/microsoft.insights/actionGroups/ag-operations"

.EXAMPLE
  # Creating a new action group with email receivers
  ./create-sqlmi-maintenance-alert.ps1 -SubscriptionId "<SUB_ID>" -ResourceGroup "rg-monitoring" `
      -Emails "dba@contoso.com","operations@contoso.com"
#>
[CmdletBinding(DefaultParameterSetName = "Emails")]
param(
  [Parameter(Mandatory)] [string] $SubscriptionId,
  [Parameter(Mandatory)] [string] $ResourceGroup,
  [Parameter(Mandatory, ParameterSetName = "Emails")] [string[]] $Emails,
  [Parameter(Mandatory, ParameterSetName = "Existing")] [string] $ActionGroupId,
  [string[]] $Regions = @("West Europe", "North Europe", "Spain Central", "Global"),
  [string] $ActionGroupName = "ag-sqlmi-maintenance",
  [string] $AlertName = "alert-sqlmi-planned-maintenance"
)
$ErrorActionPreference = "Stop"

function Invoke-Az {
  param([string[]] $Arguments)
  $out = & az @Arguments 2>&1
  if ($LASTEXITCODE -ne 0) { throw "az $($Arguments -join ' ') failed:`n$out" }
  return $out
}

if ($PSCmdlet.ParameterSetName -eq "Existing") {
  Write-Host "1) Existing action group: $ActionGroupId" -ForegroundColor Cyan
  Invoke-Az @("monitor", "action-group", "show", "--ids", $ActionGroupId, "-o", "none") | Out-Null
  $agId = $ActionGroupId
} else {
Write-Host "1) Action group $ActionGroupName" -ForegroundColor Cyan
$agId = & az monitor action-group show -g $ResourceGroup -n $ActionGroupName --subscription $SubscriptionId --query id -o tsv 2>$null
if (-not $agId) {
  $receivers = @()
  $i = 1
  foreach ($mail in $Emails) { $receivers += @("--action", "email", "email$i", $mail); $i++ }
  $agId = Invoke-Az (@("monitor", "action-group", "create", "-g", $ResourceGroup, "-n", $ActionGroupName,
                       "--short-name", "sqlmimaint", "--subscription", $SubscriptionId) + $receivers + @("--query", "id", "-o", "tsv"))
  Write-Host "   + created" -ForegroundColor Green
} else { Write-Host "   = already exists" }
}
$agId = "$agId".Trim()

Write-Host "2) Service Health alert $AlertName" -ForegroundColor Cyan
$exists = & az monitor activity-log alert show -g $ResourceGroup -n $AlertName --subscription $SubscriptionId --query id -o tsv 2>$null
if ($exists) { Write-Host "   = already exists (not modified)"; return }

$alertBody = @{
  location   = "Global"
  properties = @{
    enabled     = $true
    description = "Azure SQL Managed Instance planned maintenance (24 h before, start and end)."
    scopes      = @("/subscriptions/$SubscriptionId")
    condition   = @{ allOf = @(
        @{ field = "category"; equals = "ServiceHealth" },
        @{ field = "properties.incidentType"; equals = "Maintenance" },
        @{ anyOf = @(@{ field = "properties.impactedServices[*].ServiceName"; containsAny = @("SQL Managed Instance") }) },
        @{ anyOf = @(@{ field = "properties.impactedServices[*].ImpactedRegions[*].RegionName"; containsAny = $Regions }) }
    ) }
    actions     = @{ actionGroups = @(@{ actionGroupId = $agId }) }
  }
}
$tmp = New-TemporaryFile
$alertBody | ConvertTo-Json -Depth 12 | Set-Content -Path $tmp -Encoding utf8
$url = "https://management.azure.com/subscriptions/$SubscriptionId/resourceGroups/$ResourceGroup/providers/Microsoft.Insights/activityLogAlerts/$AlertName" + "?api-version=2020-10-01"
try {
  Invoke-Az @("rest", "--method", "put", "--url", $url, "--body", "@$tmp", "-o", "none") | Out-Null
} finally { Remove-Item $tmp -Force }
Write-Host "   + created for regions: $($Regions -join ', ')" -ForegroundColor Green
Write-Host "`nDone. Check it in Portal > Service Health > Health alerts." -ForegroundColor Green

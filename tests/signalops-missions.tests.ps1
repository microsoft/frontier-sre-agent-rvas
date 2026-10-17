#requires -Version 7.0
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$repo = Split-Path $PSScriptRoot -Parent
$track = Join-Path $repo 'SRE SignalOps'
function Assert-Mission([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw $Message }
}
function Get-MissionBlocks([string]$Number) {
    $text = Get-Content -LiteralPath (Join-Path $track "Missions\Challenge-$Number.md") -Raw
    @([regex]::Matches($text, '(?ms)^```powershell\s*\r?\n(.*?)^```') | ForEach-Object { $_.Groups[1].Value })
}
$global:MissionCalls = [Collections.Generic.List[object]]::new()
$global:MissionActiveSubscription = '00000000-0000-0000-0000-000000000001'
$global:MissionFailNative = $false
$global:MissionSelectedEnvironment = ''
$workspaceGuid = '00000000-0000-0000-0000-000000000002'
$global:MissionWorkspaceGuid = $workspaceGuid
$global:MissionContext = @{
    AZURE_SUBSCRIPTION_ID = $global:MissionActiveSubscription
    AZURE_RESOURCE_GROUP = 'rg-test-food'
    SRE_AGENT_ID = "/subscriptions/$global:MissionActiveSubscription/resourceGroups/rg-test-agent/providers/Microsoft.App/agents/test"
    LOG_ANALYTICS_WORKSPACE_ID = "/subscriptions/$global:MissionActiveSubscription/resourceGroups/rg-test-food/providers/Microsoft.OperationalInsights/workspaces/test"
    API_APP_NAME = 'test-api'
    API_BASE_URL = 'https://test-api.example.test'
    CONFIG_ROOT = (Join-Path $track 'Config')
}
function global:az {
    $global:MissionCalls.Add(@($args))
    $global:LASTEXITCODE = 0
    $command = $args[0..1] -join ' '
    switch ($command) {
        'account show' {
            if ($args -contains 'id') { $global:MissionActiveSubscription }
        }
        'resource show' { $global:MissionWorkspaceGuid }
        'resource list' {
            if ($args -contains 'Microsoft.Insights/components') {
                '/subscriptions/test/resourceGroups/rg-test-food/providers/Microsoft.Insights/components/test-app'
            } else { '[]' }
        }
        'monitor log-analytics' {
            if ($args -contains '--workspace') {
                $workspace = $args[[array]::IndexOf($args, '--workspace') + 1]
                Assert-Mission ($workspace -eq $global:MissionWorkspaceGuid) 'Mission 05 passed an ARM ID instead of the workspace GUID.'
            }
            '[]'
        }
        default {
            if ($args[0] -eq 'rest') {
                @{ properties = @{ agentEndpoint = 'https://test.example.azuresre.ai'; incidentManagementConfiguration = @{type='AzMonitor';connectionName='azmonitor'}; actionConfiguration=@{mode='Review';accessLevel='High'} } } | ConvertTo-Json -Depth 5
            } elseif ($args[0] -eq 'vm') {
                throw 'Evidence-pack mode attempted to access a live VM.'
            } elseif ($command -in @('monitor app-insights', 'network nic', 'network watcher', 'advisor recommendation')) {
                if ($global:MissionFailNative) { $global:LASTEXITCODE = 9 } else { '[]' }
            } else { throw "Unexpected mock Azure call: $command" }
        }
    }
}
function global:terraform {
    $global:LASTEXITCODE = 0
    $context = $global:MissionContext.Clone()
    $context.Remove('CONFIG_ROOT')
    $context.API_URL = $context.API_BASE_URL
    $context.Remove('API_BASE_URL')
    $context | ConvertTo-Json
}
function global:azd {
    $global:LASTEXITCODE = 0
    if (($args[0..1] -join ' ') -eq 'env select') { $global:MissionSelectedEnvironment = $args[2]; return }
    $global:MissionContext | ConvertTo-Json
}
function global:Start-Process { param($FilePath) }
function global:Read-Host { throw 'Evidence-pack mode must never request live fault authorization.' }
function global:Invoke-RestMethod { param($Uri, $Headers, $Method); $global:MissionFilterResponse }
$global:MissionFilterResponse = $null

Push-Location $repo
try {
    foreach ($number in 1..12) {
        foreach ($block in Get-MissionBlocks $number.ToString('00')) {
            $tokens = $null
            $errors = $null
            [System.Management.Automation.Language.Parser]::ParseInput($block, [ref]$tokens, [ref]$errors) | Out-Null
            Assert-Mission ($errors.Count -eq 0) "Mission $number has a PowerShell syntax error."
        }
    }
    $Lab = [pscustomobject]$global:MissionContext
    # Execute the actual examples, not rewritten proxies, with all Azure calls mocked.
    foreach ($block in Get-MissionBlocks '05') {
        . ([scriptblock]::Create($block)) | Out-Null
    }
    Assert-Mission (@($global:MissionCalls | Where-Object { $_[0] -eq 'vm' }).Count -eq 0) 'Evidence-pack mode accessed a VM.'
    $LIVE_MODE = $true
    $VM_RESOURCE_ID = "/subscriptions/$global:MissionActiveSubscription/resourceGroups/rg-test/providers/Microsoft.Compute/virtualMachines/test"
    $baseline = @(Get-MissionBlocks '05' | Where-Object { $_ -match 'properties.customerId' })[0]
    & ([scriptblock]::Create($baseline)) | Out-Null

    $ALERT_RULES = @([pscustomobject]@{ name = 'alert-signalops-grubify-http-5xx'; severity = 2 })
    $alertBlock = @(Get-MissionBlocks '08' | Where-Object { $_ -match '\$INCIDENT_ALERT =' })[0]
    . ([scriptblock]::Create($alertBlock)) | Out-Null
    Assert-Mission ($INCIDENT_ALERT.name -eq $ALERT_RULES[0].name) 'Mission 08 did not find the Mission 01 rule.'
    $filterBlock = @(Get-MissionBlocks '08' | Where-Object { $_ -match '\$FILTER_RESPONSE = Invoke-RestMethod' })[0]
    $AGENT_ENDPOINT = 'https://test.example.azuresre.ai'
    $HEADERS = @{}
    $filter = [pscustomobject]@{ name='sample-food-http-errors'; isEnabled=$true; priorities=@('Sev0','Sev1','Sev2','Sev3','Sev4'); titleContains='grubify'; handlingAgent='aca-app-incident-handler'; agentMode='Review'; maxAutomatedInvestigationAttempts=1 }
    foreach ($wrapped in @($true, $false)) {
        $global:MissionFilterResponse = if ($wrapped) {
            [pscustomobject]@{ value=@([pscustomobject]@{name=$filter.name;properties=$filter}) }
        } else { [pscustomobject]@{ incidentFilters=@($filter) } }
        . ([scriptblock]::Create($filterBlock))
        Assert-Mission ($LIVE_FILTERS.Count -eq 1 -and $LIVE_FILTERS[0].agentMode -eq 'Review' -and $LIVE_FILTERS[0].titleContains -eq 'grubify') 'Mission 08 lost nested or flat filter fields.'
    }
    $global:MissionFilterResponse = [pscustomobject]@{value=@()}
    . ([scriptblock]::Create($filterBlock))
    Assert-Mission ($LIVE_FILTERS.Count -eq 0) 'Empty filters must remain an empty collection.'

    $runner = Join-Path $track 'Scripts\Invoke-SignalOpsDemo.ps1'
    & $runner -Challenge '09' -EnvironmentName requested-environment | Out-Null
    Assert-Mission ($global:MissionSelectedEnvironment -eq 'requested-environment') 'Mission 09 ignored its requested environment.'
    & $runner -Challenge '09' -TerraformPath (Join-Path $track 'Deployment\Terraform\infra') | Out-Null
    & $runner -Challenge '12' -TerraformPath (Join-Path $track 'Deployment\Terraform\infra') | Out-Null
    & $runner -Challenge '10' -SubscriptionId $global:MissionActiveSubscription -ResourceGroup rg-test -NicName test-nic | Out-Null
    & $runner -Challenge '11' -SubscriptionId $global:MissionActiveSubscription -ResourceGroup rg-test -NicName test-nic | Out-Null
    $global:MissionActiveSubscription = '00000000-0000-0000-0000-000000000099'
    foreach ($number in @('09', '10', '11', '12')) {
        $failed = $false
        try { & $runner -Challenge $number -SubscriptionId $global:MissionContext.AZURE_SUBSCRIPTION_ID | Out-Null }
        catch { if ($_.Exception.Message -notmatch 'subscription') { throw }; $failed = $true }
        Assert-Mission $failed "Mission $number accepted a mismatched subscription."
    }
    $global:MissionActiveSubscription = $global:MissionContext.AZURE_SUBSCRIPTION_ID
    $global:MissionFailNative = $true
    $failed = $false
    try { & $runner -Challenge '10' -SubscriptionId $global:MissionActiveSubscription -ResourceGroup rg-test -NicName test-nic | Out-Null }
    catch { if ($_.Exception.Message -notmatch 'exit code 9') { throw }; $failed = $true }
    Assert-Mission $failed 'A failed network read was reported as success.'
    Write-Output 'Offline mission behavior checks passed.'
} finally {
    Pop-Location
}

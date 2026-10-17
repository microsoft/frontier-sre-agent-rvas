#requires -Version 7.0
[CmdletBinding()]
param(
    [string]$InfraPath = (Join-Path $PSScriptRoot '..'),
    [switch]$ValidateOnly
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'Common.ps1')
$config = Join-Path $PSScriptRoot '..\config'
if (-not (Test-Path -LiteralPath $config -PathType Container) -or
    -not (Test-Path -LiteralPath (Join-Path $config 'handler.json'))) {
    $config = Join-Path $PSScriptRoot '..\..\..\..\Config'
}
$registration = Join-Path $PSScriptRoot 'Register-SignalOpsAgent.ps1'
if (-not (Test-Path -LiteralPath $registration)) {
    $registration = Join-Path $PSScriptRoot '..\..\..\..\Scripts\Register-SignalOpsAgent.ps1'
}
& $registration -AgentId 'offline-validation' -ConfigRoot $config -ValidateOnly | Out-Null
$handler = Get-Content -LiteralPath (Join-Path $config 'handler.json') -Raw | ConvertFrom-Json
$plan = Get-Content -LiteralPath (Join-Path $config 'response-plan.json') -Raw | ConvertFrom-Json
$knowledge = @(Get-ChildItem -LiteralPath (Join-Path $config 'knowledge') -Filter '*.md' -File)
if ($knowledge.Count -ne 4) { throw 'Exactly four approved knowledge documents are required.' }
if ($plan.properties.agentMode -ne 'Review' -or $plan.properties.handlingAgent -ne $handler.name) {
    throw 'The response plan must use Review mode and reference the bundled specialist.'
}
$payloads = @{}
foreach ($city in @('madrid', 'paris')) { $payloads[$city] = New-LabVmPayload -City $city }
if ($ValidateOnly) {
    [pscustomobject]@{
        Specialist = $handler.name
        ResponsePlan = $plan.name
        Mode = $plan.properties.agentMode
        KnowledgeFiles = $knowledge.Name
        MadridPayloadBytes = $payloads.madrid.Length
        ParisPayloadBytes = $payloads.paris.Length
        AzureOperations = 0
    } | ConvertTo-Json
    return
}

$outputs = Invoke-LabNative terraform @("-chdir=$InfraPath", 'output', '-json') | ConvertFrom-Json
$subscription = $outputs.subscription_id.value
Invoke-LabNative az @('account', 'set', '--subscription', $subscription) | Out-Host
$chaosUrl = $outputs.parking_chaos_control_url.value.TrimEnd('/')
$dependencyUrl = "$($outputs.sample_food_api_url.value.TrimEnd('/'))/health"
foreach ($url in @($chaosUrl, $dependencyUrl)) {
    if ($url -notmatch '^https://[a-z0-9.-]+(?:/[a-z0-9/-]*)?$') { throw "Unexpected lab URL: $url" }
}

foreach ($city in @('madrid', 'paris')) {
    $vm = $outputs.vm_applications.value.$city
    if ($null -eq $vm) {
        Write-Warning "$city VM was disabled in Terraform; its application is not installed."
        continue
    }
    $extension = if ($city -eq 'madrid') { 'ps1' } else { 'sh' }
    $template = Get-Content -LiteralPath (Join-Path $PSScriptRoot "templates\install-$city.$extension") -Raw
    $script = $template.Replace('__PAYLOAD__', $payloads[$city]).Replace('__CHAOS_URL__', $chaosUrl).
        Replace('__DEPENDENCY_URL__', $dependencyUrl)
    if ($script -match '__[A-Z_]+__') { throw "Unresolved $city installation template." }
    $temporary = Join-Path ([IO.Path]::GetTempPath()) "signalops-$([Guid]::NewGuid()).$extension"
    try {
        [IO.File]::WriteAllText($temporary, $script.Replace("`r`n", "`n"), [Text.UTF8Encoding]::new($false))
        $commandId = if ($city -eq 'madrid') { 'RunPowerShellScript' } else { 'RunShellScript' }
        $result = Invoke-LabNative az @('vm', 'run-command', 'invoke', '--resource-group', $vm.resource_group,
            '--name', $vm.name, '--command-id', $commandId, '--scripts', "@$temporary", '-o', 'json') |
            ConvertFrom-Json
        $messages = ($result.value | ForEach-Object { $_.message }) -join "`n"
        if ($messages -notmatch '(?m)^SIGNALOPS_VM_READY\r?$' -or @($result.value | Where-Object { $_.code -match 'failed' }).Count) {
            throw "$city application setup failed: $messages"
        }
        Write-Host "$city application installed, persistent startup configured, local health verified."
    } finally {
        if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary }
    }
}

$agentId = $outputs.sre_agent_id.value
& $registration -AgentId $agentId -ConfigRoot $config -UploadKnowledge
foreach ($url in @("$($outputs.sample_food_api_url.value)/health", $outputs.sample_food_frontend_url.value)) {
    $response = Invoke-WebRequest -Uri $url -TimeoutSec 60
    if ($response.StatusCode -ne 200) { throw "Application health failed: $url" }
}
$origin = $outputs.sample_food_frontend_url.value.TrimEnd('/')
$cors = Invoke-WebRequest -Uri "$($outputs.sample_food_api_url.value)/api/fooditems" -Headers @{ Origin = $origin } -TimeoutSec 60
if (@($cors.Headers['Access-Control-Allow-Origin'])[0] -ne $origin) {
    throw "Grubify CORS does not permit its deployed frontend: $origin"
}
Write-Host 'VM and Grubify HTTP checks passed; three specialists and Review response plan verified. Knowledge indexing is asynchronous: complete the Mission 02 retrieval gate before incident injection.'

#requires -Version 7.0
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$repo = Split-Path $PSScriptRoot -Parent
$published = Join-Path $repo '_site\sre-signalops\Deployment\Terraform\infra'
$temporary = Join-Path ([IO.Path]::GetTempPath()) "signalops-automation-test-$([Guid]::NewGuid())"
New-Item -ItemType Directory -Path $temporary | Out-Null

function Assert-Lab([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw $Message }
}

$global:LabCalls = [Collections.Generic.List[object]]::new()
$global:LabAbac = $true
$global:LabFailNative = $false
$global:LabBadPlan = $false
$global:LabBadSpecialist = $false
$global:LabBadCors = $false
$global:LabUploads = 0
$global:LabLiveHandler = $null
$global:LabRegisteredSpecialists = @{}
$global:LabLivePlan = $null
$subscription = '00000000-0000-0000-0000-000000000001'
$global:LabContext = @{
    AZURE_SUBSCRIPTION_ID = $subscription
    AZURE_RESOURCE_GROUP = 'rg-test-food'
    AGENT_RESOURCE_GROUP = 'rg-test-agent'
    SRE_AGENT_ID = "/subscriptions/$subscription/resourceGroups/rg-test-agent/providers/Microsoft.App/agents/test-agent"
    LOG_ANALYTICS_WORKSPACE_ID = "/subscriptions/$subscription/resourceGroups/rg-test-food/providers/Microsoft.OperationalInsights/workspaces/test"
    API_APP_NAME = 'test-api'
    API_URL = 'https://test-api.example.test'
}
$global:LabOutputs = @{
    subscription_id = @{ value = $subscription }
    sre_agent_id = @{ value = $global:LabContext.SRE_AGENT_ID }
    parking_chaos_control_url = @{ value = 'https://test-chaos.example.test' }
    sample_food_api_url = @{ value = 'https://test-api.example.test' }
    sample_food_frontend_url = @{ value = 'https://test-frontend.example.test' }
    vm_applications = @{ value = @{
        madrid = @{ name = 'vm-madrid'; resource_group = 'rg-madrid' }
        paris = @{ name = 'vm-paris'; resource_group = 'rg-paris' }
    } }
}

function global:az {
    $arguments = @($args)
    $global:LabCalls.Add($arguments)
    $global:LASTEXITCODE = 0
    $command = $arguments[0..1] -join ' '
    switch ($command) {
        'acr show' {
            @{
                id = "/subscriptions/$($global:LabContext.AZURE_SUBSCRIPTION_ID)/resourceGroups/rg-registry/providers/Microsoft.ContainerRegistry/registries/signalopstest"
                loginServer = 'signalopstest.azurecr.io'
                publicNetworkAccess = 'Enabled'
                roleAssignmentMode = $(if ($global:LabAbac) { 'AbacRepositoryPermissions' } else { 'LegacyRegistryPermissions' })
            } | ConvertTo-Json
        }
        'acr build' {
            if ($global:LabFailNative) { $global:LASTEXITCODE = 7; return }
            $context = $arguments[$arguments.IndexOf('--platform') + 2]
            $dockerfile = $arguments[$arguments.IndexOf('--file') + 1]
            Assert-Lab (Test-Path -LiteralPath (Join-Path $context $dockerfile)) 'Build context is missing its Dockerfile.'
            $forbidden = @(Get-ChildItem -LiteralPath $context -Recurse -Force |
                Where-Object { $_.Name -in @('.env', 'node_modules', 'should-not-ship.js') })
            Assert-Lab ($forbidden.Count -eq 0) 'A private/build-only file entered the ACR upload context.'
        }
        'acr repository' {
            Assert-Lab ($arguments[2] -eq 'show') 'Unexpected registry command.'
            'sha256:' + ('a' * 64)
        }
        'account show' { $global:LabContext.AZURE_SUBSCRIPTION_ID }
        'account set' {}
        'account get-access-token' { 'offline-test-token' }
        'vm run-command' {
            $scriptPath = $arguments[$arguments.IndexOf('--scripts') + 1].TrimStart('@')
            $script = Get-Content -LiteralPath $scriptPath -Raw
            Assert-Lab ($script -notmatch '__[A-Z_]+__') 'A VM template was not fully rendered.'
            Assert-Lab ($script -match 'test-chaos.example.test') 'VM chaos-controller wiring is missing.'
            @{ value = @(@{ code = 'ProvisioningState/succeeded'; message = "SIGNALOPS_VM_READY`n" }) } | ConvertTo-Json -Depth 5
        }
        default {
            if ($arguments[0] -eq 'rest') {
                @{ properties = @{ provisioningState = 'Succeeded'; agentEndpoint = 'https://test-agent.example.azuresre.ai' } } |
                    ConvertTo-Json -Depth 5
            } else { throw "Unexpected Azure command in offline test: $command" }
        }
    }
}

function global:terraform {
    $global:LASTEXITCODE = 0
    if ($args[-1] -eq 'mission_context') { $global:LabContext | ConvertTo-Json }
    else { $global:LabOutputs | ConvertTo-Json -Depth 10 }
}

function global:azd {
    $global:LASTEXITCODE = 0
    if ($args[0..1] -join ' ' -eq 'env select') { return }
    $context = $global:LabContext.Clone()
    $context.Remove('API_APP_NAME')
    $context.API_BASE_URL = 'https://test-api.example.test'
    $context | ConvertTo-Json
}

function global:Invoke-RestMethod {
    param($Uri, $Headers, $Method, $ContentType, $Body, $TimeoutSec, $Form)
    if ($Uri -like '*/extendedAgent/agents/*') {
        if ($Method -eq 'Put') {
            $global:LabLiveHandler = $Body | ConvertFrom-Json
            $global:LabRegisteredSpecialists[$global:LabLiveHandler.name] = $global:LabLiveHandler
        }
        if ($global:LabBadSpecialist -and $Method -eq 'Get') { $global:LabLiveHandler.properties.agentType = 'Autonomous' }
        return $global:LabLiveHandler
    }
    if ($Uri -like '*/extendedAgent/incidentFilters/*') {
        if ($Method -eq 'Put') { $global:LabLivePlan = $Body | ConvertFrom-Json }
        if ($global:LabBadPlan -and $Method -eq 'Get') { $global:LabLivePlan.properties.agentMode = 'Autonomous' }
        return $global:LabLivePlan
    }
    if ($Uri -like '*/agentmemory/upload') {
        Assert-Lab ($Form.files.Exists) 'Knowledge upload is missing its source file.'
        $global:LabUploads++
        return @{ status = 'uploaded' }
    }
    if ($Uri -like '*/AgentMemory/files') {
        return @{ files = @('sample-food-architecture.md', 'http-500-errors.md', 'incident-report-template.md', 'github-issue-triage.md') }
    }
    if ($Uri -like '*/agentmemory/indexer-status') { return @{ status = 'ready' } }
    throw "Unexpected HTTP request in offline test: $Uri"
}

function global:Invoke-WebRequest {
    param($Uri, $Headers, $TimeoutSec)
    $responseHeaders = @{}
    if ($Headers -and $Headers.Origin -and -not $global:LabBadCors) { $responseHeaders['Access-Control-Allow-Origin'] = $Headers.Origin }
    @{ StatusCode = 200; Headers = $responseHeaders }
}

try {
    Copy-Item -LiteralPath $published -Destination (Join-Path $temporary 'infra') -Recurse
    $infra = Join-Path $temporary 'infra'
    $scripts = Join-Path $infra 'scripts'
    $backend = Join-Path $infra 'apps\parking-manager\backend'
    Set-Content -LiteralPath (Join-Path $backend '.env') -Value 'OFFLINE_FIXTURE=do-not-publish'
    New-Item -ItemType Directory -Path (Join-Path $backend 'node_modules') | Out-Null
    Set-Content -LiteralPath (Join-Path $backend 'node_modules\should-not-ship.js') -Value 'test fixture'

    & (Join-Path $scripts 'Build-Images.ps1') -RegistryName signalopstest -RegistryResourceGroup rg-registry -PlanOnly | Out-Null
    & (Join-Path $scripts 'Complete-Lab.ps1') -ValidateOnly | Out-Null
    Assert-Lab ($global:LabCalls.Count -eq 0) 'Validation-only commands contacted Azure.'

    foreach ($abac in @($true, $false)) {
        $global:LabAbac = $abac
        & (Join-Path $scripts 'Build-Images.ps1') -RegistryName signalopstest -RegistryResourceGroup rg-registry
        $inputs = Get-Content -LiteralPath (Join-Path $infra 'images.auto.tfvars.json') -Raw | ConvertFrom-Json
        $expectedRole = if ($abac) { 'Container Registry Repository Reader' } else { 'AcrPull' }
        Assert-Lab ($inputs.registry_pull_role -eq $expectedRole) 'Incorrect registry role mode.'
        Assert-Lab (@($inputs.container_images.PSObject.Properties).Count -eq 7) 'Expected seven pinned images.'
        foreach ($image in $inputs.container_images.PSObject.Properties.Value) {
            Assert-Lab ($image -match '^signalopstest\.azurecr\.io/signalops/[^@]+@sha256:[a-f0-9]{64}$') 'Image is not pinned to the owned registry.'
        }
    }
    $global:LabFailNative = $true
    $failed = $false
    try { & (Join-Path $scripts 'Build-Images.ps1') -RegistryName signalopstest -RegistryResourceGroup rg-registry }
    catch { if ($_.Exception.Message -notlike '*exit code 7*') { throw }; $failed = $true }
    Assert-Lab $failed 'Native build failures must stop image publishing.'
    $global:LabFailNative = $false

    & (Join-Path $scripts 'Complete-Lab.ps1') -InfraPath $infra
    Assert-Lab ($global:LabUploads -eq 4) 'Expected four approved knowledge uploads.'
    Assert-Lab ($global:LabRegisteredSpecialists.Count -eq 3) 'All three local specialists must be registered.'
    foreach ($name in @('network-traffic-analyst', 'cost-optimization-agent', 'aca-app-incident-handler')) {
        Assert-Lab ($global:LabRegisteredSpecialists[$name].properties.agentType -eq 'Review') 'Specialists must remain in Review mode.'
    }
    Assert-Lab ('RunAzCliWriteCommands' -notin $global:LabRegisteredSpecialists['network-traffic-analyst'].properties.tools) 'Network specialist must be read-only.'
    $uploadsBeforeRegistration = $global:LabUploads
    Push-Location (Join-Path $repo 'SRE SignalOps')
    try {
        & '.\Scripts\Register-SignalOpsAgent.ps1' -AgentId $global:LabContext.SRE_AGENT_ID
    } finally { Pop-Location }
    Assert-Lab ($global:LabUploads -eq $uploadsBeforeRegistration) 'Bicep registration must not silently upload knowledge.'
    foreach ($failure in @('LabBadPlan', 'LabBadCors', 'LabBadSpecialist')) {
        Set-Variable -Name $failure -Scope Global -Value $true
        $failed = $false
        try { & (Join-Path $scripts 'Complete-Lab.ps1') -InfraPath $infra }
        catch {
            if ($_.Exception.Message -notmatch 'verification failed|CORS does not permit') { throw }
            $failed = $true
        }
        Assert-Lab $failed "Completion must fail for $failure."
        Set-Variable -Name $failure -Scope Global -Value $false
    }

    $context = & (Join-Path $scripts 'Get-SignalOpsContext.ps1') -TerraformPath $infra
    Assert-Lab ($context.API_APP_NAME -eq 'test-api' -and $context.DEPLOYMENT_METHOD -eq 'Terraform') 'Incorrect Terraform context.'
    Assert-Lab ($context.API_BASE_URL -eq $global:LabContext.API_URL) 'Terraform API URL was not normalized.'
    $context = & (Join-Path $repo 'SRE SignalOps\Scripts\Get-SignalOpsContext.ps1') -EnvironmentName test
    Assert-Lab ($context.API_APP_NAME -eq 'test-api' -and $context.DEPLOYMENT_METHOD -eq 'Bicep') 'Incorrect Bicep context.'
    Write-Output 'Offline automation behavior checks passed.'
} finally {
    Remove-Item -LiteralPath $temporary -Recurse -Force
}

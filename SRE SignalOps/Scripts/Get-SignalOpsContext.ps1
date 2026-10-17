#requires -Version 7.0
[CmdletBinding(DefaultParameterSetName = 'Bicep')]
param(
    [Parameter(Mandatory, ParameterSetName = 'Terraform')][string]$TerraformPath,
    [Parameter(ParameterSetName = 'Bicep')][string]$EnvironmentName = 'signalops-core'
)
$ErrorActionPreference = 'Stop'
if ($PSCmdlet.ParameterSetName -eq 'Terraform') {
    $json = & terraform "-chdir=$TerraformPath" output -json mission_context
    if ($LASTEXITCODE -ne 0) { throw 'Could not read Terraform mission_context. Apply the reviewed lab plan first.' }
    $context = $json | ConvertFrom-Json -AsHashtable
    $context.DEPLOYMENT_METHOD = 'Terraform'
    if ($context.ContainsKey('API_URL')) { $context.API_BASE_URL = $context['API_URL'] }
    $context.CONFIG_ROOT = Join-Path (Resolve-Path -LiteralPath $TerraformPath).Path 'config'
    if (-not (Test-Path -LiteralPath (Join-Path $context.CONFIG_ROOT 'handler.json'))) {
        $context.CONFIG_ROOT = (Resolve-Path -LiteralPath (Join-Path $TerraformPath '..\..\..\Config')).Path
    }
} else {
    Push-Location (Join-Path $PSScriptRoot '..')
    try {
        & azd env select $EnvironmentName | Out-Host
        if ($LASTEXITCODE -ne 0) { throw "Could not select azd environment $EnvironmentName." }
        $json = & azd env get-values -o json
        if ($LASTEXITCODE -ne 0) { throw 'Could not read azd environment outputs.' }
        $context = $json | ConvertFrom-Json -AsHashtable
        $context.DEPLOYMENT_METHOD = 'Bicep'
        $context.CONFIG_ROOT = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\Config')).Path
        if (-not $context.API_BASE_URL) { throw 'Missing deployment output: API_BASE_URL' }
        $context.API_APP_NAME = ([uri]$context.API_BASE_URL).DnsSafeHost.Split('.')[0]
    } finally { Pop-Location }
}
foreach ($key in @('AZURE_SUBSCRIPTION_ID', 'AZURE_RESOURCE_GROUP', 'SRE_AGENT_ID', 'LOG_ANALYTICS_WORKSPACE_ID')) {
    if (-not $context[$key]) { throw "Missing deployment output: $key" }
}
if ($context.SRE_AGENT_ID -notlike "/subscriptions/$($context.AZURE_SUBSCRIPTION_ID)/resourceGroups/*/providers/Microsoft.App/agents/*") {
    throw 'Agent ID does not belong to the deployment subscription.'
}
[pscustomobject]$context

#requires -Version 7.0
[CmdletBinding()]
param(
    [Parameter(Mandatory)][ValidatePattern('^[a-zA-Z0-9]{5,50}$')][string]$RegistryName,
    [Parameter(Mandatory)][string]$RegistryResourceGroup,
    [ValidatePattern('^[a-zA-Z0-9_][a-zA-Z0-9_.-]{0,127}$')][string]$Tag = "lab-$([DateTime]::UtcNow.ToString('yyyyMMddHHmmss'))",
    [switch]$PlanOnly
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'Common.ps1')
$images = @(Get-LabImages)
if ($PlanOnly) {
    $images | Select-Object Key, Repository, Context, Dockerfile | ConvertTo-Json
    return
}

$registry = Invoke-LabNative az @('acr', 'show', '--name', $RegistryName, '--resource-group', $RegistryResourceGroup, '-o', 'json') |
    ConvertFrom-Json
$subscription = (Invoke-LabNative az @('account', 'show', '--query', 'id', '-o', 'tsv')).Trim()
if ($registry.id -notlike "/subscriptions/$subscription/*") { throw 'The registry is not in the selected subscription.' }
if ($registry.loginServer -notmatch '^[a-z0-9]+\.azurecr\.io$') { throw 'This lab requires a public-Azure ACR login server.' }
if ($registry.publicNetworkAccess -eq 'Disabled') {
    throw 'This builder requires ACR build and Container Apps connectivity. A private-only registry needs an approved private build/network design.'
}
$role = if ($registry.roleAssignmentMode -eq 'AbacRepositoryPermissions') { 'Container Registry Repository Reader' } else { 'AcrPull' }
$resolvedImages = [ordered]@{}
foreach ($image in $images) {
    $tagged = "$($image.Repository):$Tag"
    Write-Host "Building $tagged in $RegistryName..."
    $staging = Join-Path ([IO.Path]::GetTempPath()) "signalops-build-$([Guid]::NewGuid())"
    try {
        Copy-LabBuildContext -Source $image.Context -Destination $staging
        $dockerfile = [IO.Path]::GetRelativePath($image.Context, $image.Dockerfile)
        Invoke-LabNative az @('acr', 'build', '--registry', $RegistryName, '--image', $tagged, '--file', $dockerfile,
            '--platform', 'linux/amd64', $staging, '--only-show-errors') | Out-Host
    } finally {
        if (Test-Path -LiteralPath $staging) { Remove-Item -LiteralPath $staging -Recurse -Force }
    }
    $digest = (Invoke-LabNative az @('acr', 'repository', 'show', '--name', $RegistryName, '--image', $tagged,
        '--query', 'digest', '-o', 'tsv')).Trim()
    if ($digest -notmatch '^sha256:[a-f0-9]{64}$') { throw "Invalid digest returned for $tagged." }
    $resolvedImages[$image.Key] = "$($registry.loginServer)/$($image.Repository)@$digest"
}
$inputs = @{
    container_registry_name = $RegistryName
    container_registry_resource_group = $RegistryResourceGroup
    registry_pull_role = $role
    container_images = $resolvedImages
}
$target = Join-Path $PSScriptRoot '..\images.auto.tfvars.json'
$inputs | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $target -Encoding utf8
Write-Host "Wrote seven digest-pinned images to $target. The existing registry remains externally owned."

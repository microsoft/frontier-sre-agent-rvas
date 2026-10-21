#requires -Version 5.1
<#
.SYNOPSIS
  Deploy the FinOps Cost Optimizer skill to an Azure SRE Agent via the data plane.

.DESCRIPTION
  The control plane sub-resource API (Microsoft.App/agents/skills) is restricted to
  internal tenants in preview ("Agent Extensions are not available for this tenant").
  The portal Builder and this script use the DATA PLANE instead:
    PUT https://{agentEndpoint}/api/v2/extendedAgent/skills/{name}
  with a bearer token for the https://azuresre.dev audience.

  Schema captured from a live agent:
    properties.description     string
    properties.tools           string[]    built-in tool names
    properties.skillContent    string      the SKILL.md text
    properties.additionalFiles [{ filePath, content }]   bundled files

  The three Python helpers are bundled as additional files and run by the agent
  with the RunInTerminal tool. The reference markdown files are bundled too.

  Requires the Azure CLI, an active `az login` session, and builder access (the
  SRE Agent Administrator role) on the agent, which must already exist.

.PARAMETER Mode
  Deploy (default) writes the skill. Capture reads existing skills and tools to JSON.

.EXAMPLE
  ./deploy.ps1 -SubscriptionId <sub> -ResourceGroup rg-sre-agent -AgentName sreagent2 -DryRun

.EXAMPLE
  ./deploy.ps1 -SubscriptionId <sub> -ResourceGroup rg-sre-agent -AgentName sreagent2 -Mode Capture
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$SubscriptionId,
    [Parameter(Mandatory)][string]$ResourceGroup,
    [Parameter(Mandatory)][string]$AgentName,
    [ValidateSet('Deploy', 'Capture')][string]$Mode = 'Deploy',
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
$armApiVersion = '2025-05-01-preview'
$skillRoot = Split-Path -Parent $PSScriptRoot
$skillName = 'finops-cost-optimizer'

function Get-AgentEndpoint {
    $url = "https://management.azure.com/subscriptions/$SubscriptionId/resourceGroups/$ResourceGroup/providers/Microsoft.App/agents/$AgentName" + "?api-version=$armApiVersion"
    $endpoint = az rest --method GET --url $url --query properties.agentEndpoint -o tsv
    if (-not $endpoint) { throw 'Could not resolve the agent data plane endpoint. Check the agent name and your access.' }
    return $endpoint.Trim()
}

function Get-DataPlaneToken {
    $token = az account get-access-token --resource https://azuresre.dev --query accessToken -o tsv
    if (-not $token) { throw 'Could not acquire a data plane token for https://azuresre.dev.' }
    return $token.Trim()
}

function Get-AdditionalFiles {
    # Bundle the reference markdown and the Python helpers (not the unit test).
    $files = @()
    foreach ($ref in Get-ChildItem -Path (Join-Path $skillRoot 'references') -File) {
        $files += @{ filePath = "references/$($ref.Name)"; content = (Get-Content -Path $ref.FullName -Raw) }
    }
    foreach ($py in (Get-ChildItem -Path (Join-Path $skillRoot 'tools') -Filter '*.py' -File | Where-Object { $_.Name -ne 'test_cost_rank.py' })) {
        $files += @{ filePath = "tools/$($py.Name)"; content = (Get-Content -Path $py.FullName -Raw) }
    }
    return , $files
}

function Invoke-DataPlane {
    param([string]$Method, [string]$Uri, [string]$Token, [string]$Body)
    $headers = @{ Authorization = "Bearer $Token" }
    if ($Body) {
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($Body)
        return Invoke-RestMethod -Method $Method -Uri $Uri -Headers $headers -ContentType 'application/json' -Body $bytes
    }
    return Invoke-RestMethod -Method $Method -Uri $Uri -Headers $headers
}

function ConvertTo-JsonString {
    # Fast, correct JSON string escaping for Windows PowerShell 5.1, whose
    # ConvertTo-Json is pathologically slow on large string payloads.
    param([string]$Text)
    if ($null -eq $Text) { return '""' }
    $escaped = $Text.Replace('\', '\\').Replace('"', '\"').Replace("`r", '\r').Replace("`n", '\n').Replace("`t", '\t').Replace("`b", '\b').Replace("`f", '\f')
    $escaped = [regex]::Replace($escaped, '[\x00-\x07\x0b\x0e-\x1f]', { param($m) ('\u{0:x4}' -f [int][char]$m.Value) })
    return '"' + $escaped + '"'
}

function Build-SkillBody {
    param([string]$Name, [string]$Description, [string[]]$Tools, [string]$SkillContent, $AdditionalFiles)
    $toolsJson = '[' + (($Tools | ForEach-Object { ConvertTo-JsonString $_ }) -join ',') + ']'
    $filesJson = '[' + (($AdditionalFiles | ForEach-Object { '{"filePath":' + (ConvertTo-JsonString $_.filePath) + ',"content":' + (ConvertTo-JsonString $_.content) + '}' }) -join ',') + ']'
    $props = '"description":' + (ConvertTo-JsonString $Description) + ',"tools":' + $toolsJson + ',"skillContent":' + (ConvertTo-JsonString $SkillContent) + ',"additionalFiles":' + $filesJson
    return '{"name":' + (ConvertTo-JsonString $Name) + ',"type":"Skill","properties":{' + $props + '}}'
}

$endpoint = Get-AgentEndpoint
Write-Host "Agent endpoint: $endpoint"
$token = Get-DataPlaneToken

if ($Mode -eq 'Capture') {
    $dir = Join-Path $PSScriptRoot 'captured'
    New-Item -ItemType Directory -Path $dir -Force | Out-Null
    foreach ($type in 'skills', 'tools', 'subagents', 'scheduledtasks') {
        try {
            $raw = Invoke-WebRequest -Method GET -Uri "$endpoint/api/v2/extendedAgent/$type" -Headers @{ Authorization = "Bearer $token" } -UseBasicParsing
            $outPath = Join-Path $dir "$type.json"
            [System.IO.File]::WriteAllText($outPath, $raw.Content, (New-Object System.Text.UTF8Encoding($false)))
            $count = @(($raw.Content | ConvertFrom-Json).value).Count
            Write-Host ("captured {0}: {1} item(s) -> {2}" -f $type, $count, $outPath)
        }
        catch {
            $msg = $_.ErrorDetails.Message; if (-not $msg) { $msg = $_.Exception.Message }
            Write-Warning "Could not capture ${type}: $msg"
        }
    }
    return
}

# Build the skill spec from local files (data plane schema).
$skillContent = Get-Content -Path (Join-Path $skillRoot 'SKILL.md') -Raw
$additionalFiles = Get-AdditionalFiles
$description = 'FinOps cost optimization review across the subscriptions the agent can read. Ranks by spend, detects waste across seven dimensions, scores idle and orphaned resources by confidence to terminate, and produces a self contained HTML report.'
$tools = @('RunAzCliReadCommands', 'RunInTerminal', 'SaveFileToBlob')
$bodyJson = Build-SkillBody -Name $skillName -Description $description -Tools $tools -SkillContent $skillContent -AdditionalFiles $additionalFiles
$uri = "$endpoint/api/v2/extendedAgent/skills/$skillName"

if ($DryRun) {
    Write-Host "[dry-run] PUT $uri"
    Write-Host ("  tools: {0}" -f ($tools -join ', '))
    Write-Host ("  body bytes: {0}" -f [System.Text.Encoding]::UTF8.GetByteCount($bodyJson))
    Write-Host ("  skillContent bytes: {0}" -f [System.Text.Encoding]::UTF8.GetByteCount($skillContent))
    Write-Host ("  additionalFiles: {0}" -f @($additionalFiles).Count)
    foreach ($file in $additionalFiles) {
        Write-Host ("    - {0} ({1} bytes)" -f $file.filePath, [System.Text.Encoding]::UTF8.GetByteCount($file.content))
    }
    return
}

Write-Host "PUT skill $skillName"
$null = Invoke-DataPlane -Method PUT -Uri $uri -Token $token -Body $bodyJson
$check = Invoke-DataPlane -Method GET -Uri $uri -Token $token
Write-Host ("Deployed. Skill '{0}' present with {1} additional file(s); tools: {2}" -f $check.name, @($check.properties.additionalFiles).Count, ($check.properties.tools -join ', '))

#requires -Version 5.1
<#
.SYNOPSIS
  Deploy any skill in this repository to an Azure SRE Agent via the data plane.

.DESCRIPTION
  One parameterized deploy script for every pillar skill, so the 200 line data
  plane client is not copied into each skill folder. Point it at a skill folder
  with -SkillPath and it:
    1. reads name, description, and tools from the SKILL.md frontmatter,
    2. bundles the skill's references and tools plus the shared references and
       shared tools (report_render.py) as additionalFiles,
    3. PUTs the skill to the agent data plane, the same surface the portal
       Builder uses:
         PUT https://{agentEndpoint}/api/v2/extendedAgent/skills/{name}

  The control plane sub-resource API (Microsoft.App/agents/skills) is restricted
  to internal tenants in preview, so this uses the data plane with a bearer token
  for the https://azuresre.dev audience.

  Requires the Azure CLI, an active `az login`, and builder access (the SRE Agent
  Administrator role) on the agent, which must already exist.

.EXAMPLE
  ./deploy-skill.ps1 -SubscriptionId <sub> -ResourceGroup rg-sre-agent -AgentName sreagent2 `
    -SkillPath ../../security/certificate-secret-expiry -DryRun

.EXAMPLE
  ./deploy-skill.ps1 -SubscriptionId <sub> -ResourceGroup rg-sre-agent -AgentName sreagent2 `
    -SkillPath ../../management/reliability-posture-review
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$SubscriptionId,
    [Parameter(Mandatory)][string]$ResourceGroup,
    [Parameter(Mandatory)][string]$AgentName,
    [Parameter(Mandatory)][string]$SkillPath,
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
$armApiVersion = '2025-05-01-preview'
$sharedRoot = Split-Path -Parent $PSScriptRoot          # the shared/ folder
$skillRoot = (Resolve-Path -Path $SkillPath).Path       # the target skill folder
if (-not (Test-Path (Join-Path $skillRoot 'SKILL.md'))) {
    throw "No SKILL.md found under $skillRoot. Pass -SkillPath the skill folder that contains SKILL.md."
}

function Get-Frontmatter {
    param([string]$Path)
    $lines = Get-Content -Path $Path
    if ($lines[0].Trim() -ne '---') { throw "SKILL.md is missing YAML frontmatter." }
    $end = 1; while ($end -lt $lines.Count -and $lines[$end].Trim() -ne '---') { $end++ }
    $block = $lines[1..($end - 1)]
    $name = $null; $description = $null; $tools = @()
    for ($i = 0; $i -lt $block.Count; $i++) {
        $line = $block[$i]
        if ($line -match '^name:\s*(.+)$') { $name = $Matches[1].Trim().Trim('"''') }
        elseif ($line -match '^description:\s*(.+)$') {
            $value = $Matches[1].Trim()
            if ($value -in @('>', '|', '>-', '|-')) {
                $folded = @()
                $j = $i + 1
                while ($j -lt $block.Count -and $block[$j] -match '^\s+\S') { $folded += $block[$j].Trim(); $j++ }
                $description = ($folded -join ' ')
            }
            else { $description = $value.Trim('"''') }
        }
        elseif ($line -match '^tools:\s*$') {
            $j = $i + 1
            while ($j -lt $block.Count -and $block[$j] -match '^\s*-\s*(.+)$') { $tools += $Matches[1].Trim().Trim('"''`'); $j++ }
        }
    }
    if (-not $name) { throw "SKILL.md frontmatter has no name." }
    return [pscustomobject]@{ Name = $name; Description = $description; Tools = $tools }
}

function Get-AdditionalFiles {
    # Bundle shared references + shared tools, then the skill's own references +
    # tools. Skip unit tests. The skill's files win on a filePath clash.
    $files = [ordered]@{}
    $sources = @(
        @{ Dir = (Join-Path $sharedRoot 'references'); Prefix = 'references' },
        @{ Dir = (Join-Path $sharedRoot 'tools'); Prefix = 'tools' },
        @{ Dir = (Join-Path $skillRoot 'references'); Prefix = 'references' },
        @{ Dir = (Join-Path $skillRoot 'tools'); Prefix = 'tools' }
    )
    foreach ($source in $sources) {
        if (-not (Test-Path $source.Dir)) { continue }
        foreach ($file in Get-ChildItem -Path $source.Dir -File) {
            if ($file.Extension -eq '.py' -and $file.Name -like 'test_*') { continue }
            $key = "$($source.Prefix)/$($file.Name)"
            $files[$key] = (Get-Content -Path $file.FullName -Raw)
        }
    }
    # Skill files that live at the skill root, for flat skills that mirror their
    # layout (for example azure-arch/generator-template.py). The
    # filePath is the bare file name, matching how the source bundles them. The
    # SKILL.md is sent as skillContent, so it is not added here.
    foreach ($file in Get-ChildItem -Path $skillRoot -File) {
        if ($file.Name -eq 'SKILL.md') { continue }
        if ($file.Extension -eq '.py' -and $file.Name -like 'test_*') { continue }
        $files[$file.Name] = (Get-Content -Path $file.FullName -Raw)
    }
    $list = @()
    foreach ($key in $files.Keys) { $list += @{ filePath = $key; content = $files[$key] } }
    return , $list
}

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

function Invoke-DataPlane {
    param([string]$Method, [string]$Uri, [string]$Token, [string]$Body)
    $headers = @{ Authorization = "Bearer $Token" }
    if ($Body) {
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($Body)
        return Invoke-RestMethod -Method $Method -Uri $Uri -Headers $headers -ContentType 'application/json' -Body $bytes
    }
    return Invoke-RestMethod -Method $Method -Uri $Uri -Headers $headers
}

$meta = Get-Frontmatter -Path (Join-Path $skillRoot 'SKILL.md')
$skillContent = Get-Content -Path (Join-Path $skillRoot 'SKILL.md') -Raw
$additionalFiles = Get-AdditionalFiles
$tools = @($meta.Tools)
if (-not $tools -or $tools.Count -eq 0) { $tools = @('RunAzCliReadCommands', 'RunInTerminal', 'SaveFileToBlob') }

if ($DryRun) {
    Write-Host "[dry-run] skill '$($meta.Name)' from $skillRoot"
    Write-Host ("  description: {0}" -f $meta.Description)
    Write-Host ("  tools: {0}" -f ($tools -join ', '))
    Write-Host ("  skillContent bytes: {0}" -f [System.Text.Encoding]::UTF8.GetByteCount($skillContent))
    Write-Host ("  additionalFiles: {0}" -f @($additionalFiles).Count)
    foreach ($file in $additionalFiles) {
        Write-Host ("    - {0} ({1} bytes)" -f $file.filePath, [System.Text.Encoding]::UTF8.GetByteCount($file.content))
    }
    return
}

$endpoint = Get-AgentEndpoint
Write-Host "Agent endpoint: $endpoint"
$token = Get-DataPlaneToken
$bodyJson = Build-SkillBody -Name $meta.Name -Description $meta.Description -Tools $tools -SkillContent $skillContent -AdditionalFiles $additionalFiles
$uri = "$endpoint/api/v2/extendedAgent/skills/$($meta.Name)"

Write-Host "PUT skill $($meta.Name)"
$null = Invoke-DataPlane -Method PUT -Uri $uri -Token $token -Body $bodyJson
$check = Invoke-DataPlane -Method GET -Uri $uri -Token $token
Write-Host ("Deployed. Skill '{0}' present with {1} additional file(s); tools: {2}" -f $check.name, @($check.properties.additionalFiles).Count, ($check.properties.tools -join ', '))

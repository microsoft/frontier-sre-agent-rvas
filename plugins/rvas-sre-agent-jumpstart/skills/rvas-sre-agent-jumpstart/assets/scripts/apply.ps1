#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Generic apply script for azuresre.ai/v1 capability manifests.

.DESCRIPTION
    This file is a pre-built, generic asset copied unmodified into every target repository's
    azure-sre-agent-config/scripts/ directory -- it is never re-generated or re-authored per
    run. It discovers manifests dynamically by scanning for `api_version: azuresre.ai/v1` YAML
    files and reading each one's own `kind:` field; it never assumes a fixed, per-plan manifest
    list. Functionally equivalent to apply.sh -- every behavior here (discovery, preflight
    hard-stop, -Force override, PUT, verify, exit codes) has a corresponding apply.sh behavior.

.PARAMETER ResourceGroup
    Resource group containing the target Microsoft.App/agents resource. Required.

.PARAMETER AgentName
    Name of the target Azure SRE Agent resource. Required.

.PARAMETER SubscriptionId
    Azure subscription ID. Defaults to the current `az account show`.

.PARAMETER ManifestDirectory
    Directory to scan for manifests. Defaults to the parent of this script's own directory
    (the azure-sre-agent-config/ root).

.PARAMETER ApiVersion
    ARM/data-plane api-version to use. This is a preview surface -- confirm the current value
    against the live Learn/REST reference fetched when the plan this script accompanies was
    authored, and override this default if it has changed.

.PARAMETER Force
    Proceed even when the preflight step finds the 5-skill cap exceeded or a name collision.
    Without this switch the script hard-stops (non-zero exit, no write call made) on either
    condition.

.NOTES
    Exit codes: 0 on full success; non-zero on any missing dependency, preflight hard-stop, or
    apply/verify failure. On a partial failure, every manifest applied successfully before the
    failure is printed, so a partial apply is never silently reported as complete.

    Concurrency: do not run two invocations of this script against the same agent at the same
    time -- the preflight check and the later apply calls are not atomic as a pair, so two
    simultaneous runs can each pass preflight before either writes, bypassing the 5-skill cap.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string] $ResourceGroup,

    [Parameter(Mandatory = $true)]
    [string] $AgentName,

    [string] $SubscriptionId,

    [string] $ManifestDirectory,

    [string] $ApiVersion = "2026-01-01",

    [switch] $Force
)

$ErrorActionPreference = "Stop"
# Make a failed native command (e.g. a non-zero `az` exit code) raise a terminating error the
# same way a failed cmdlet already does, instead of only being caught indirectly by a later
# verify-GET failure.
$PSNativeCommandUseErrorActionPreference = $true
$DataPlaneAudience = "https://azuresre.dev"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $ManifestDirectory) {
    $ManifestDirectory = Split-Path -Parent $ScriptDir
}

function Write-Log {
    param([string] $Message)
    Write-Host $Message
}

function Stop-WithError {
    param([string] $Message)
    [Console]::Error.WriteLine("ERROR: $Message")
    exit 1
}

function Confirm-Command {
    param([string] $Name)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        Stop-WithError "Required command not found: $Name"
    }
}

# Convert a manifest YAML file to a JSON-shaped PSCustomObject, preferring the powershell-yaml
# module and falling back to Python 3 + PyYAML (the same fallback apply.sh uses) when it is not
# installed, so neither OS script requires a tool the other doesn't also tolerate.
function ConvertFrom-ManifestYaml {
    param([string] $Path)
    if (Get-Module -ListAvailable -Name powershell-yaml) {
        Import-Module powershell-yaml -ErrorAction Stop
        return Get-Content -Raw -Path $Path | ConvertFrom-Yaml
    }
    if (Get-Command python3 -ErrorAction SilentlyContinue) {
        $json = Get-Content -Raw -Path $Path | & python3 -c "import json, sys, yaml; print(json.dumps(yaml.safe_load(sys.stdin.read())))"
        return $json | ConvertFrom-Json
    }
    Stop-WithError "Required YAML parser not found: install the powershell-yaml module, or Python 3 with PyYAML"
}

# Discover every azuresre.ai/v1 manifest under ManifestDirectory by reading each YAML file's own
# `kind:` field -- never a hardcoded, per-plan manifest list.
function Find-Manifests {
    Get-ChildItem -Path $ManifestDirectory -Recurse -Filter '*.yaml' -File |
        Sort-Object FullName |
        Where-Object { (Get-Content -Raw -Path $_.FullName) -match "(?m)^api_version:\s*[`"']?azuresre\.ai/v1[`"']?\s*`$" } |
        ForEach-Object { $_.FullName }
}

function Get-EndpointKind {
    param([string] $Kind)
    switch ($Kind) {
        "Skill" { return "skills" }
        "SubAgent" { return "agents" }
        "Tool" { return "tools" }
        "ScheduledTask" { return "scheduledtasks" }
        "CommonPrompt" { return "commonprompts" }
        "IncidentFilter" { return "incidentFilters" }
        "Hook" { return "hooks" }
        "Plugin" { return "plugins" }
        "ConnectorV2" { return "connectors" }
        "Connector" { return "ARM" }  # AgentConnector: applied through ARM control-plane
        default { Stop-WithError "Unknown manifest kind: $Kind" }
    }
}

# Build the plain (not base64-encoded) JSON object this manifest PUTs as its `properties`. A
# Skill manifest's `spec.files` list names the paired Markdown body (first entry) to inline as
# `skillContent`; every other kind's `spec` block is passed through as-is.
function Get-ManifestProperties {
    param($Manifest, [string] $Kind, [string] $BaseDir)
    $spec = $Manifest.spec
    if ($Kind -eq "Skill") {
        $first = $spec.files[0]
        if (-not $first) { Stop-WithError "Skill manifest has no spec.files entry" }
        $contentPath = if ([System.IO.Path]::IsPathRooted($first)) { $first } else { Join-Path $BaseDir $first }
        if (-not (Test-Path $contentPath)) { Stop-WithError "Skill body file not found: $contentPath" }
        $properties = [ordered]@{}
        $properties["description"] = if ($spec.description) { $spec.description } else { "" }
        # Assigned as its own statement per branch (never captured from a single if/else
        # expression) -- PowerShell unwraps a single-element array to a bare scalar and
        # collapses an empty array to $null when an if/else expression's result is captured
        # directly into a hashtable value, which would otherwise corrupt a 0- or 1-tool list.
        if ($spec.tools) { $properties["tools"] = @($spec.tools) } else { $properties["tools"] = @() }
        $properties["skillContent"] = (Get-Content -Raw -Path $contentPath)
        return $properties
    }
    return $spec
}

function Resolve-Endpoint {
    $armUrl = "https://management.azure.com/subscriptions/$SubscriptionId/resourceGroups/$ResourceGroup/providers/Microsoft.App/agents/$AgentName`?api-version=$ApiVersion"
    $script:Endpoint = (az rest --method GET --url $armUrl --query properties.agentEndpoint -o tsv)
    if (-not $Endpoint) { Stop-WithError "Could not resolve agentEndpoint for $AgentName in $ResourceGroup" }
    $script:Token = (az account get-access-token --resource $DataPlaneAudience --query accessToken -o tsv)
}

function Invoke-DataPlaneGet {
    param([string] $Path)
    Invoke-RestMethod -Method Get -Uri "$Endpoint/api/v2/extendedAgent/$Path" `
        -Headers @{ Authorization = "Bearer $Token" }
}

function Invoke-DataPlanePut {
    param([string] $EndpointKind, [string] $Name, [string] $BodyJson)
    Invoke-RestMethod -Method Put -Uri "$Endpoint/api/v2/extendedAgent/$EndpointKind/$Name" `
        -Headers @{ Authorization = "Bearer $Token" } -ContentType 'application/json' -Body $BodyJson
}

function Invoke-ArmConnectorPut {
    param([string] $Name, $Properties)
    $url = "https://management.azure.com/subscriptions/$SubscriptionId/resourceGroups/$ResourceGroup/providers/Microsoft.App/agents/$AgentName/DataConnectors/$Name`?api-version=$ApiVersion"
    $body = @{ properties = $Properties } | ConvertTo-Json -Depth 20
    az rest --method PUT --url $url --body $body | Out-Null
}

function Invoke-ArmConnectorGet {
    param([string] $Name)
    $url = "https://management.azure.com/subscriptions/$SubscriptionId/resourceGroups/$ResourceGroup/providers/Microsoft.App/agents/$AgentName/DataConnectors/$Name`?api-version=$ApiVersion"
    az rest --method GET --url $url | ConvertFrom-Json
}

# Reject any manifest name that is not a URL-safe slug -- metadata.name is interpolated
# directly into REST paths and query strings, so a name containing '/', '?', '&', '#',
# whitespace, or unicode would otherwise retarget or corrupt the request with no validation
# anywhere else.
function Confirm-ManifestName {
    param([string] $Name)
    if ($Name -notmatch '^[A-Za-z0-9._-]+$') {
        Stop-WithError "Manifest name is not a URL-safe slug: '$Name' (allowed: letters, digits, '.', '_', '-')"
    }
}

# Checks whether a data-plane resource already exists without treating a transient or auth
# failure as "absent." Returns $true/$false for a clean 200/404, or dies with the captured
# error on anything else, so preflight never silently misreports connectivity trouble as a
# clean check.
function Test-DataPlaneExists {
    param([string] $Path)
    try {
        Invoke-DataPlaneGet -Path $Path | Out-Null
        return $true
    } catch {
        $statusCode = $null
        if ($_.Exception.PSObject.Properties.Name -contains 'Response' -and $_.Exception.Response) {
            $statusCode = [int]$_.Exception.Response.StatusCode
        }
        if ($statusCode -eq 404) { return $false }
        Stop-WithError "Preflight: unexpected error checking '$Path' ($($_.Exception.Message))"
    }
}

# Same purpose as Test-DataPlaneExists, for the ARM-managed connector path, where the error
# detail comes from `az rest`'s own exception message rather than a typed HTTP response.
function Test-ArmConnectorExists {
    param([string] $Name)
    $url = "https://management.azure.com/subscriptions/$SubscriptionId/resourceGroups/$ResourceGroup/providers/Microsoft.App/agents/$AgentName/DataConnectors/$Name`?api-version=$ApiVersion"
    try {
        az rest --method GET --url $url | Out-Null
        return $true
    } catch {
        $message = $_.Exception.Message
        if ($message -match '404' -or $message -match 'NotFound') { return $false }
        Stop-WithError "Preflight: could not check connector '$Name' existence ($message)"
    }
}

# Deep-compare $Expected (the properties object that was PUT) against $Actual (the verify-GET
# response's corresponding properties), recursing into nested objects and arrays. Only the keys
# present in $Expected are checked -- an agent-side default or computed field that only appears
# in $Actual is not treated as a mismatch.
function Test-DeepEqual {
    param($Expected, $Actual)

    if ($null -eq $Expected) { return ($null -eq $Actual) }

    # The explicit `-isnot [string]` guards below are required because a string produced by
    # Get-Content (as skillContent is) carries extra pipeline NoteProperties (PSPath, ReadCount,
    # etc.) that make `-is [PSCustomObject]` evaluate to $true even though the underlying .NET
    # type is System.String -- without the guard this branch would wrongly enumerate those
    # decoration properties instead of comparing the string's value, making verification always
    # fail for any manifest with inline file content.
    if (($Expected -is [System.Collections.IDictionary]) -or (($Expected -is [PSCustomObject]) -and ($Expected -isnot [string]))) {
        $keys = if ($Expected -is [System.Collections.IDictionary]) { $Expected.Keys } else { $Expected.PSObject.Properties.Name }
        foreach ($key in $keys) {
            # Assigned per branch as its own statement, not captured from a single if/else
            # expression -- the expression form unwraps a single-element array value to a bare
            # scalar and collapses an empty array to $null, which would otherwise make a
            # correct 0- or 1-item array field look like a verify mismatch.
            if ($Expected -is [System.Collections.IDictionary]) {
                $expectedValue = $Expected[$key]
            } else {
                $expectedValue = $Expected.$key
            }
            if ($Actual -is [System.Collections.IDictionary]) {
                if (-not $Actual.Contains($key)) { return $false }
                $actualValue = $Actual[$key]
            } elseif (($Actual -is [PSCustomObject]) -and ($Actual -isnot [string]) -and ($Actual.PSObject.Properties.Name -contains $key)) {
                $actualValue = $Actual.$key
            } else {
                return $false
            }
            if (-not (Test-DeepEqual -Expected $expectedValue -Actual $actualValue)) { return $false }
        }
        return $true
    }

    if (($Expected -is [System.Collections.IEnumerable]) -and ($Expected -isnot [string])) {
        $expectedArray = @($Expected)
        $actualArray = @($Actual)
        if ($expectedArray.Count -ne $actualArray.Count) { return $false }
        for ($i = 0; $i -lt $expectedArray.Count; $i++) {
            if (-not (Test-DeepEqual -Expected $expectedArray[$i] -Actual $actualArray[$i])) { return $false }
        }
        return $true
    }

    # `-ceq` (case-sensitive) for parity with apply.sh's verify, which uses jq's `==` -- a
    # standard JSON equality that is case-sensitive. The default `-eq` operator on strings is
    # case-insensitive and would let a case-only drift (e.g. an agent lower-casing a name) pass
    # verification here while the same drift would correctly fail apply.sh's check.
    return $Expected -ceq $Actual
}

# Preflight (read-only): check the 5-skill cap and every discovered manifest's name for a
# collision against what already exists. Hard-stops (non-zero exit, no write call) unless
# -Force was passed.
function Invoke-Preflight {
    param([string[]] $Manifests)

    $existingSkills = Invoke-DataPlaneGet -Path "skills"
    $existingCount = @($existingSkills).Count
    $newSkillCount = 0
    $problem = $false

    foreach ($file in $Manifests) {
        $manifest = ConvertFrom-ManifestYaml -Path $file
        $kind = $manifest.kind
        $name = $manifest.metadata.name
        if (-not $kind -or -not $name) { Stop-WithError "Manifest missing kind/metadata.name: $file" }
        Confirm-ManifestName -Name $name
        $endpointKind = Get-EndpointKind -Kind $kind

        if ($kind -eq "Skill") {
            $alreadyExists = @($existingSkills | Where-Object { $_.name -eq $name }).Count -gt 0
            if (-not $alreadyExists) { $newSkillCount++ }
        }

        if ($endpointKind -eq "ARM") {
            if (Test-ArmConnectorExists -Name $name) {
                Write-Log "Preflight: name collision -- connector '$name' already exists"
                $problem = $true
            }
        } else {
            if (Test-DataPlaneExists -Path "$endpointKind/$name") {
                Write-Log "Preflight: name collision -- $kind '$name' already exists"
                $problem = $true
            }
        }
    }

    if (($existingCount + $newSkillCount) -gt 5) {
        Write-Log "Preflight: 5-skill cap would be exceeded ($existingCount existing + $newSkillCount new)."
        Write-Log "Recommendation: fold the new capability into an existing skill instead of adding a sixth."
        $problem = $true
    }

    if ($problem) {
        if ($Force) {
            Write-Log "Preflight found the issue(s) above; proceeding because -Force was passed."
        } else {
            Stop-WithError "Preflight hard-stop (no write call made). Re-run with -Force only after you've explicitly accepted this risk."
        }
    }
}

function Publish-Manifest {
    param([string] $File)
    $baseDir = Split-Path -Parent $File
    $manifest = ConvertFrom-ManifestYaml -Path $File
    $kind = $manifest.kind
    $name = $manifest.metadata.name
    Confirm-ManifestName -Name $name
    $endpointKind = Get-EndpointKind -Kind $kind
    $properties = Get-ManifestProperties -Manifest $manifest -Kind $kind -BaseDir $baseDir

    if ($endpointKind -eq "ARM") {
        Invoke-ArmConnectorPut -Name $name -Properties $properties
        $verify = Invoke-ArmConnectorGet -Name $name
    } else {
        $body = @{ name = $name; type = $kind; tags = @(); properties = $properties } | ConvertTo-Json -Depth 20
        Invoke-DataPlanePut -EndpointKind $endpointKind -Name $name -BodyJson $body | Out-Null
        $verify = Invoke-DataPlaneGet -Path "$endpointKind/$name"
    }

    $actualProperties = if ($verify.properties) { $verify.properties } else { $verify }
    if (-not (Test-DeepEqual -Expected $properties -Actual $actualProperties)) {
        Stop-WithError "Verify failed: $kind '$name' returned properties do not match what was PUT"
    }
    Write-Log "Applied and verified: $kind '$name'"
}

function Main {
    Confirm-Command "az"

    if (-not $SubscriptionId) {
        $SubscriptionId = (az account show --query id -o tsv)
    }
    if (-not (Test-Path $ManifestDirectory)) {
        Stop-WithError "Manifest directory not found: $ManifestDirectory"
    }

    $manifests = @(Find-Manifests)
    if ($manifests.Count -eq 0) {
        Stop-WithError "No azuresre.ai/v1 manifests found under $ManifestDirectory"
    }

    Resolve-Endpoint
    Invoke-Preflight -Manifests $manifests

    $applied = @()
    foreach ($file in $manifests) {
        Publish-Manifest -File $file
        $applied += $file
    }

    Write-Log "All $($applied.Count) manifest(s) applied and verified successfully."
}

Main

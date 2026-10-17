#requires -Version 7.0
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$AgentId,
    [string]$ConfigRoot = (Join-Path $PSScriptRoot '..\Config'),
    [switch]$UploadKnowledge,
    [switch]$ValidateOnly
)
$ErrorActionPreference = 'Stop'
$specialists = @('network.json', 'cost.json', 'handler.json') | ForEach-Object {
    Get-Content -LiteralPath (Join-Path $ConfigRoot $_) -Raw | ConvertFrom-Json
}
$plan = Get-Content -LiteralPath (Join-Path $ConfigRoot 'response-plan.json') -Raw | ConvertFrom-Json
foreach ($specialist in $specialists) {
    if ($specialist.properties.agentType -ne 'Review' -or -not $specialist.properties.handoffDescription) {
        throw "Specialist must declare Review mode and routing metadata: $($specialist.name)"
    }
    foreach ($handoff in $specialist.properties.handoffs) {
        if ($handoff -notin $specialists.name) { throw "Unregistered handoff target: $handoff" }
    }
}
if ($plan.properties.agentMode -ne 'Review' -or $plan.properties.handlingAgent -ne 'aca-app-incident-handler' -or
    -not $plan.properties.isEnabled -or $plan.properties.titleContains -ne 'grubify' -or
    (@('Sev0', 'Sev1', 'Sev2', 'Sev3', 'Sev4') | Where-Object { $_ -notin $plan.properties.priorities })) {
    throw 'The Grubify response plan must be enabled, all-severity and approval gated.'
}
$knowledge = @(Get-ChildItem -LiteralPath (Join-Path $ConfigRoot 'knowledge') -File -Filter '*.md')
if ($knowledge.Count -ne 4) { throw 'Exactly four approved knowledge documents are required.' }
if ($ValidateOnly) {
    [pscustomobject]@{ Specialists = $specialists.name; ResponsePlan = $plan.name; AzureOperations = 0 }
    return
}
if ($AgentId -notmatch '^/subscriptions/([^/]+)/resourceGroups/[^/]+/providers/Microsoft.App/agents/[^/]+$') {
    throw 'Provide the full deployed SRE Agent resource ID.'
}
$subscription = $Matches[1]
$active = (& az account show --query id -o tsv | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or $active -ne $subscription) { throw 'Select the agent subscription before registration.' }
$agent = & az rest --method GET --url "https://management.azure.com$AgentId`?api-version=2026-01-01" -o json
if ($LASTEXITCODE -ne 0) { throw 'Could not read the deployed SRE Agent.' }
$agent = $agent | ConvertFrom-Json
$endpoint = $agent.properties.agentEndpoint.TrimEnd('/')
if ($agent.properties.provisioningState -ne 'Succeeded' -or $endpoint -notmatch '^https://[a-z0-9.-]+\.azuresre\.(ai|dev)$') {
    throw 'Agent provisioning is not ready or its endpoint is invalid.'
}
$token = (& az account get-access-token --resource https://azuresre.dev --query accessToken -o tsv | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or -not $token) { throw 'Could not acquire the agent access token.' }
$headers = @{ Authorization = "Bearer $token" }
function Invoke-AgentRequest {
    param([string]$Path, [string]$Method = 'Get', [object]$Body)
    for ($attempt = 1; $attempt -le 12; $attempt++) {
        try {
            $request = @{ Uri = "$endpoint$Path"; Headers = $headers; Method = $Method; TimeoutSec = 120 }
            if ($null -ne $Body) {
                $request.ContentType = 'application/json'
                $request.Body = ConvertTo-Json -InputObject $Body -Depth 20 -Compress
            }
            return Invoke-RestMethod @request
        } catch [Microsoft.PowerShell.Commands.HttpResponseException] {
            $status = [int]$_.Exception.Response.StatusCode
            $transient = $status -in @(403, 404, 409, 429, 502, 503, 504) -or
                ($status -eq 400 -and $Path -like '*/incidentFilters/*')
            if (-not $transient -or $attempt -eq 12) { throw }
            Write-Warning "Agent registration is not ready (HTTP $status); retry $attempt/12."
            Start-Sleep -Seconds 15
        }
    }
}
try {
    foreach ($specialist in $specialists) {
        $path = "/api/v2/extendedAgent/agents/$($specialist.name)"
        Invoke-AgentRequest $path Put $specialist | Out-Null
        $live = Invoke-AgentRequest $path
        $properties = if ($live.PSObject.Properties.Name -contains 'properties') { $live.properties } else { $live }
        if ($live.name -ne $specialist.name -or $properties.agentType -ne 'Review' -or
            $properties.handoffDescription -ne $specialist.properties.handoffDescription -or
            (@($properties.handoffs) -join ',') -ne (@($specialist.properties.handoffs) -join ',') -or
            (@($properties.tools) -join ',') -ne (@($specialist.properties.tools) -join ',')) {
            throw "Live specialist verification failed: $($specialist.name)"
        }
    }
    $path = "/api/v2/extendedAgent/incidentFilters/$($plan.name)"
    Invoke-AgentRequest $path Put $plan | Out-Null
    $live = Invoke-AgentRequest $path
    $properties = if ($live.PSObject.Properties.Name -contains 'properties') { $live.properties } else { $live }
    foreach ($field in @('isEnabled', 'agentMode', 'handlingAgent', 'titleContains', 'incidentPlatform', 'maxAutomatedInvestigationAttempts')) {
        if ($properties.$field -ne $plan.properties.$field) { throw "Live response-plan verification failed: $field" }
    }
    if ((@($properties.priorities | Sort-Object) -join ',') -ne (@($plan.properties.priorities | Sort-Object) -join ',')) {
        throw 'Live response-plan verification failed: priorities'
    }
    if ($UploadKnowledge) {
        foreach ($file in $knowledge) {
            Invoke-RestMethod -Uri "$endpoint/api/v1/agentmemory/upload" -Headers $headers -Method Post -Form @{ files = $file } -TimeoutSec 120 | Out-Null
        }
        $inventory = Invoke-AgentRequest '/api/v1/AgentMemory/files'
        $inventoryJson = $inventory | ConvertTo-Json -Depth 20
        foreach ($file in $knowledge) {
            if ($inventoryJson -notmatch ('"(?:[^"]*/)?' + [regex]::Escape($file.Name) + '"')) {
                throw "Uploaded knowledge is missing from the live inventory: $($file.Name)"
            }
        }
        Write-Host 'Agent Memory indexer state (retrieval must still pass Mission 02):'
        Invoke-AgentRequest '/api/v1/agentmemory/indexer-status' | ConvertTo-Json -Depth 10 | Out-Host
    }
    Write-Host 'Three Review specialists and the Grubify response plan registered and verified.'
} finally {
    $headers.Clear()
    $token = $null
}

[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory)]
    [ValidateSet('00','01','02','03','04','05','06','07','08','09','10','11','12','13')]
    [string]$Challenge,
    [switch]$Execute,
    [switch]$Restore,
    [string]$EnvironmentName = 'signalops',
    [string]$Location = 'eastus2',
    [string]$AgentResourceGroup = 'rg-signalops-agent',
    [string]$AgentName = 'signalops-agent',
    [string]$ResourceGroup,
    [string]$NicName,
    [string]$VmName,
    [string]$SourceIp,
    [string]$DestinationIp,
    [string]$WorkspaceId,
    [string]$VmResourceId
)

$ErrorActionPreference = 'Stop'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$GrubifyRoot = Join-Path $RepoRoot 'Student\Resources\grubify'
$ConfigScript = Join-Path $RepoRoot 'Student\Resources\infra\scripts\sre-agent-config.sh'
$Bash = 'C:\Program Files\Git\bin\bash.exe'

function Assert-Command([string]$Name) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command not found: $Name"
    }
}

function Invoke-Native([scriptblock]$Command) {
    & $Command
    if ($LASTEXITCODE -ne 0) { throw "Command failed with exit code $LASTEXITCODE" }
}

function Get-AzdValue([string]$Name) {
    Push-Location $GrubifyRoot
    try {
        $value = azd env get-value $Name 2>$null
        if ($LASTEXITCODE -eq 0) { return ($value | Out-String).Trim() }
        return $null
    } finally { Pop-Location }
}

function Get-AgentContext {
    $subscriptionId = (az account show --query id -o tsv).Trim()
    $agentId = "/subscriptions/$subscriptionId/resourceGroups/$AgentResourceGroup/providers/Microsoft.App/agents/$AgentName"
    $agent = az rest --method GET --url "https://management.azure.com$agentId`?api-version=2025-05-01-preview" 2>$null | ConvertFrom-Json
    [pscustomobject]@{
        SubscriptionId = $subscriptionId
        AgentId = $agentId
        Endpoint = $agent.properties.agentEndpoint.TrimEnd('/')
        Token = (az account get-access-token --resource https://azuresre.dev --query accessToken -o tsv).Trim()
    }
}

function Write-Prompt([string]$Text) {
    Write-Host "`nGHCP / SRE Agent prompt" -ForegroundColor Cyan
    Write-Host $Text
}

function Write-Expected([string]$Text) {
    Write-Host "`nExpected observation: $Text" -ForegroundColor Green
}

Assert-Command az
if (-not (az account show --query id -o tsv 2>$null)) {
    throw 'Azure CLI is not authenticated. Run az login first.'
}

switch ($Challenge) {
    '00' {
        Assert-Command azd
        Assert-Command docker
        Push-Location $GrubifyRoot
        try {
            $environmentNames = @(azd env list --output json | ConvertFrom-Json | ForEach-Object name)
            if ($EnvironmentName -notin $environmentNames) {
                Invoke-Native { azd env new $EnvironmentName }
            } else {
                Invoke-Native { azd env select $EnvironmentName }
            }
            $subscriptionId = (az account show --query id -o tsv).Trim()
            Invoke-Native { azd env set AZURE_SUBSCRIPTION_ID $subscriptionId }
            Invoke-Native { azd env set AZURE_LOCATION $Location }
            if ($Execute) {
                if ($PSCmdlet.ShouldProcess("azd environment $EnvironmentName", 'Provision and deploy Grubify')) {
                    Invoke-Native { azd up }
                }
            } else {
                Invoke-Native { azd provision --preview }
                Write-Host 'Preview only. Add -Execute to deploy.' -ForegroundColor Yellow
            }
            azd env get-values
        } finally { Pop-Location }
        Write-Expected 'Preview completes, or deployment outputs include the resource group, API, frontend, Log Analytics, and Application Insights.'
    }
    '01' {
        $subscriptionId = (az account show --query id -o tsv).Trim()
        $workloadResourceGroup = Get-AzdValue 'AZURE_RESOURCE_GROUP'
        if ($Execute -and $PSCmdlet.ShouldProcess($AgentResourceGroup, 'Create agent resource group and register Microsoft.App')) {
            Invoke-Native { az group create --name $AgentResourceGroup --location $Location -o table }
            Invoke-Native { az provider register --namespace Microsoft.App --wait }
        }
        $agentId = "/subscriptions/$subscriptionId/resourceGroups/$AgentResourceGroup/providers/Microsoft.App/agents/$AgentName"
        az rest --method GET --url "https://management.azure.com$agentId`?api-version=2025-05-01-preview" --query '{name:name,state:properties.provisioningState,endpoint:properties.agentEndpoint,managedResourceGroup:properties.managedResourceGroup}' -o table
        Write-Host "Workload scope: $workloadResourceGroup"
        Write-Expected 'The agent is Succeeded, has an azuresre endpoint, and is scoped to the Grubify resource group.'
        Write-Prompt 'Verify this Azure SRE Agent is in Review mode, uses least privilege, and can read the Grubify resource group. Do not make changes.'
    }
    '02' {
        $context = Get-AgentContext
        $headers = @{ Authorization = "Bearer $($context.Token)" }
        Invoke-RestMethod -Uri "$($context.Endpoint)/api/v2/repos" -Headers $headers | ConvertTo-Json -Depth 6
        Invoke-RestMethod -Uri "$($context.Endpoint)/api/v1/agentmemory/status" -Headers $headers | ConvertTo-Json -Depth 6
        $workloadResourceGroup = Get-AzdValue 'AZURE_RESOURCE_GROUP'
        az containerapp list --resource-group $workloadResourceGroup --query '[].{name:name,state:properties.runningStatus,fqdn:properties.configuration.ingress.fqdn}' -o table
        az resource list --resource-group $workloadResourceGroup --resource-type Microsoft.Insights/components --query '[].{name:name,workspace:properties.WorkspaceResourceId}' -o table
        Write-Expected 'Repository, memory status, Container Apps, and workspace-backed Application Insights are visible.'
        Write-Prompt 'List the connected source-code, knowledge, and telemetry evidence planes. Label any source that is configured but not currently readable.'
    }
    '03' {
        if (-not (Test-Path $Bash)) { throw "Git Bash not found at $Bash" }
        $subscriptionId = (az account show --query id -o tsv).Trim()
        $configRoot = (Join-Path $RepoRoot 'Student\Resources').Replace('\','/').Replace('C:','/c')
        $targets = @('skills','subagents','incident-platforms','incident-filters')
        foreach ($target in $targets) {
            $operation = if ($Execute) { 'apply' } else { 'plan' }
            $command = "cd '$configRoot' && ./infra/scripts/sre-agent-config.sh $operation --target '$target' --subscription '$subscriptionId' --resource-group '$AgentResourceGroup' --agent '$AgentName'"
            if ($Execute -and -not $PSCmdlet.ShouldProcess("$AgentName/$target", 'Apply SRE Agent configuration')) { continue }
            Invoke-Native { & $Bash -lc $command }
        }
        Write-Expected 'Four target classes plan cleanly; with -Execute they apply without exposing connector secrets.'
        Write-Prompt 'Explain which tools are read-only, which actions require approval, and why explicit grants are stronger than prompt-only restrictions.'
    }
    '04' {
        $context = Get-AgentContext
        $headers = @{ Authorization = "Bearer $($context.Token)" }
        Invoke-RestMethod -Uri "$($context.Endpoint)/api/v2/extendedAgent/connectors" -Headers $headers | ConvertTo-Json -Depth 8
        Write-Expected 'Every live connector has a type and current state; reference manifests are not reported as live systems.'
        Write-Prompt 'Build a connector matrix with authentication, authorization, reachable tools, freshness, and one harmless read test. Separate configured from proven connectivity.'
    }
    '05' {
        $context = Get-AgentContext
        $headers = @{ Authorization = "Bearer $($context.Token)" }
        $agents = Invoke-RestMethod -Uri "$($context.Endpoint)/api/v2/extendedAgent/agents" -Headers $headers
        $items = if ($agents.agents) { $agents.agents } elseif ($agents.value) { $agents.value } else { $agents }
        $items | Select-Object name, agentType, handoffDescription | Format-Table -AutoSize
        Write-Expected 'Specialists have distinct handoff descriptions and constrained tools.'
        Write-Prompt 'Route an application error, denied network flow, and cost anomaly to specialists. Explain each choice and identify overlaps or unowned gaps.'
    }
    '06' {
        $context = Get-AgentContext
        $headers = @{ Authorization = "Bearer $($context.Token)" }
        Invoke-RestMethod -Uri "$($context.Endpoint)/api/v2/extendedAgent/incidentFilters" -Headers $headers | ConvertTo-Json -Depth 8
        az rest --method GET --url "https://management.azure.com$($context.AgentId)?api-version=2025-05-01-preview" --query properties.incidentManagementConfiguration -o json
        Write-Expected 'Filter conditions, selected specialists, and Azure Monitor incident wiring are visible.'
        Write-Prompt 'Trace one non-destructive alert from filter match through evidence collection, approval, validation, timeout, escalation, and closure. Do not approve a write.'
    }
    '07' {
        $workloadResourceGroup = Get-AzdValue 'AZURE_RESOURCE_GROUP'
        $apiUrl = Get-AzdValue 'API_BASE_URL'
        1..10 | ForEach-Object { Invoke-RestMethod -Uri "$apiUrl/api/restaurants" | Out-Null }
        $appName = (az resource list --resource-group $workloadResourceGroup --resource-type Microsoft.Insights/components --query '[0].name' -o tsv).Trim()
        if (-not $appName) { throw "No Application Insights component found in $workloadResourceGroup" }
        az monitor app-insights query --resource-group $workloadResourceGroup --app $appName --analytics-query 'requests | where timestamp > ago(30m) | summarize requests=count(), failures=countif(success == false), p95=percentile(duration, 95) by cloud_RoleName' -o table
        az monitor app-insights query --resource-group $workloadResourceGroup --app $appName --analytics-query 'dependencies | where timestamp > ago(30m) | summarize calls=count(), failures=countif(success == false), p95=percentile(duration, 95) by target, type' -o table
        Write-Expected 'API requests appear; absent browser or downstream edges remain explicitly unobserved.'
        Write-Prompt 'Create an evidence-backed dependency map. For each edge include direction, protocol, timestamp, volume, latency, failure rate, and evidence source; label unobserved edges.'
    }
    '08' {
        if (-not $ResourceGroup -or -not $NicName) { throw 'Challenge 08 requires -ResourceGroup and -NicName for the coach-provided sandbox.' }
        az network nic list-effective-nsg --resource-group $ResourceGroup --name $NicName -o jsonc
        Write-Expected 'The effective NSG output identifies the actual NIC/subnet associations and rule priorities.'
        Write-Prompt 'Identify the exact effective deny, affected and unaffected paths, and the narrowest reversible remediation. Do not delete a broad deny rule.'
    }
    '09' {
        if (-not $ResourceGroup -or -not $NicName) { throw 'Challenge 09 requires -ResourceGroup and -NicName.' }
        az network nic show-effective-route-table --resource-group $ResourceGroup --name $NicName -o table
        if ($VmName -and $SourceIp -and $DestinationIp) {
            az network watcher show-next-hop --resource-group $ResourceGroup --vm $VmName --source-ip $SourceIp --dest-ip $DestinationIp -o jsonc
        } else {
            Write-Host 'Add -VmName, -SourceIp, and -DestinationIp to run the next-hop check.' -ForegroundColor Yellow
        }
        Write-Expected 'Forward and return route evidence identifies the effective next hop or missing path.'
        Write-Prompt 'Prove forward and return paths separately, then distinguish routing from DNS, NSG, and application failure.'
    }
    '10' {
        if (-not $WorkspaceId -or -not $VmResourceId) { throw 'Challenge 10 requires -WorkspaceId and -VmResourceId. Use coach evidence-pack mode when no monitored VM exists.' }
        $escapedResourceId = $VmResourceId.Replace("'", "''")
        az monitor log-analytics query --workspace $WorkspaceId --analytics-query "Heartbeat | where _ResourceId =~ '$escapedResourceId' | summarize HeartbeatCount=count(), LastHeartbeat=max(TimeGenerated)" -o table
        if ($Execute -or $Restore) {
            if (-not $ResourceGroup -or -not $VmName) { throw 'VM actions also require -ResourceGroup and -VmName.' }
            $action = if ($Restore) { 'start' } else { 'deallocate' }
            if ($PSCmdlet.ShouldProcess("$ResourceGroup/$VmName", "$action lab VM")) {
                Invoke-Native { az vm $action --resource-group $ResourceGroup --name $VmName --no-wait }
            }
        }
        Write-Expected 'The baseline has recent Heartbeat data; any VM state change is explicit, confirmed, and reversible with -Restore.'
        Write-Prompt 'Produce an RCA with timeline, evidence matrix, competing hypotheses, rejected hypothesis, likely cause, contributing factors, confidence, and next safe action.'
    }
    '11' {
        $context = Get-AgentContext
        $headers = @{ Authorization = "Bearer $($context.Token)" }
        Invoke-RestMethod -Uri "$($context.Endpoint)/api/v1/AgentMemory/files" -Headers $headers | ConvertTo-Json -Depth 8
        $template = @'
# Workload Reliability Context
- Purpose:
- Architecture and dependencies:
- Owner and escalation path:
- Criticality:
- Heartbeat expectation and maintenance window:
- RTO / RPO:
- Approved investigation boundaries:
- Verified incident lesson:
'@
        $output = Join-Path $env:TEMP 'signalops-workload-context.md'
        Set-Content -Path $output -Value $template -Encoding utf8
        Write-Host "Knowledge draft created: $output"
        Write-Expected 'The same question can be compared before and after ingestion, with live evidence separated from organizational context.'
        Write-Prompt 'Assess the selected VM heartbeat risk. Attribute every claim to live Azure evidence or custom knowledge, and flag conflicts or stale context.'
    }
    '12' {
        $subscriptionId = (az account show --query id -o tsv).Trim()
        $resources = az resource list --subscription $subscriptionId -o json | ConvertFrom-Json
        $resources | Group-Object type | Sort-Object Count -Descending | Select-Object Count, Name | Format-Table -AutoSize
        az advisor recommendation list --subscription $subscriptionId --query '[].{category:category,impact:impact,resource:resourceMetadata.resourceId,problem:shortDescription.problem}' -o table
        az monitor log-analytics workspace list --subscription $subscriptionId --query '[].{name:name,resourceGroup:resourceGroup,retention:retentionInDays}' -o table
        Write-Expected 'Inventory, Advisor, and observability evidence are visible; unavailable cost or utilization access is reported as a gap.'
        Write-Prompt 'Produce three prioritized read-only recommendations across cost, reliability, observability, resilience, or governance. Include evidence, value, confidence, effort, trade-off, owner, and approval need.'
    }
    '13' {
        $subscriptionId = (az account show --query id -o tsv).Trim()
        az backup vault list --subscription $subscriptionId --query '[].{name:name,resourceGroup:resourceGroup,location:location}' -o table
        $message = @'
EXERCISE - Backup assurance review
Severity: <severity>
Affected workload: <name>
Application impact: <observed impact>
Latest job state: <state and UTC timestamp>
Latest usable recovery point: <timestamp or unavailable>
RPO risk: <assessment>
Confidence: <level and evidence>
Recommended action: <approval-gated action>
Incident / portal link: <URL>
'@
        Write-Host $message
        Write-Expected 'Live mode uses an authorized connector; evidence-pack mode produces a review-ready message without claiming delivery.'
        Write-Prompt 'Correlate vault, protected-item, job, recovery-point, application health, RTO, and RPO evidence. Draft a concise Teams update, but do not post without explicit approval.'
    }
}
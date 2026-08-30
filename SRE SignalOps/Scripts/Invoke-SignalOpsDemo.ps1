[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory)]
    [ValidateSet('00','01','02','03','04','05','06','07','08','09','10','11','12','13')]
    [string]$Challenge,
    [switch]$Execute,
    [switch]$Restore,
    [string]$EnvironmentName = 'signalops',
    [string]$Location = 'swedencentral',
    [string]$AgentResourceGroup = 'rg-sre-agent',
    [string]$AgentName = 'contoso-sre-agent-dev',
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
az account show --query id -o none 2>$null
if ($LASTEXITCODE -ne 0) {
    throw 'Azure CLI is not authenticated. Run az login first.'
}

switch ($Challenge) {
    '00' {
        if ($Execute -or $Restore) { throw 'Challenge 00 is read-only for the existing MCAPS lab. Do not use -Execute or -Restore.' }
        $account = az account show | ConvertFrom-Json
        if ($account.name -ne 'MCAPS-Hybrid-REQ-150072-2026-rakau') {
            throw "Active subscription is '$($account.name)'; select MCAPS-Hybrid-REQ-150072-2026-rakau before continuing."
        }
        $workloadResourceGroup = 'rg-sre-spoke-foodapp-paas'
        az group show --name $workloadResourceGroup --query '{name:name,location:location,state:properties.provisioningState}' -o table
        az resource list --resource-group $workloadResourceGroup --query '[].{name:name,type:type,location:location}' -o table
        $apps = az containerapp list --resource-group $workloadResourceGroup | ConvertFrom-Json
        $apps | Select-Object name,@{n='State';e={$_.properties.runningStatus}},@{n='FQDN';e={$_.properties.configuration.ingress.fqdn}} | Format-Table -AutoSize
        $frontend = $apps | Where-Object name -eq 'ca-food-frontend'
        $frontendUrl = "https://$($frontend.properties.configuration.ingress.fqdn)"
        Invoke-WebRequest -Uri $frontendUrl -UseBasicParsing | Select-Object StatusCode
        az monitor app-insights component show --resource-group $workloadResourceGroup --app appi-food --query '{name:name,workspace:properties.WorkspaceResourceId}' -o table
        az monitor log-analytics workspace show --resource-group rg-sre-hub-connectivity --workspace-name law-rgn3ao --query '{name:name,location:location,state:provisioningState}' -o table
        Write-Expected 'The existing Sweden Central food workload is present, both Container Apps are Running, the frontend returns 200, and telemetry resources are visible.'
    }
    '01' {
        if ($Execute -or $Restore) { throw 'Challenge 01 is read-only for the existing MCAPS lab. Do not use -Execute or -Restore.' }
        $subscriptionId = (az account show --query id -o tsv).Trim()
        $agentId = "/subscriptions/$subscriptionId/resourceGroups/$AgentResourceGroup/providers/Microsoft.App/agents/$AgentName"
        az rest --method GET --url "https://management.azure.com$agentId`?api-version=2025-05-01-preview" --query 'properties.{state:provisioningState,power:powerState,endpoint:agentEndpoint,mode:actionConfiguration.mode,access:actionConfiguration.accessLevel,managedResources:knowledgeGraphConfiguration.managedResources}' -o json
        az role assignment list --scope $agentId --query '[].{role:roleDefinitionName,principal:principalName}' -o table
        Write-Expected 'contoso-sre-agent-dev is Succeeded and Running in Sweden Central with Autonomous/High configuration and the deployed MCAPS managed scopes.'
        Write-Prompt 'Audit this existing high-access autonomous lab agent and its managed scopes. Do not make changes or broaden permissions.'
    }
    '02' {
        if ($Execute -or $Restore) { throw 'Challenge 02 is read-only for the existing MCAPS lab. Do not use -Execute or -Restore.' }
        $context = Get-AgentContext
        $headers = @{ Authorization = "Bearer $($context.Token)" }
        az rest --method GET --url "https://management.azure.com$($context.AgentId)/DataConnectors?api-version=2025-05-01-preview" --query 'value[].{name:name,type:properties.dataConnectorType,source:properties.dataSource}' -o table
        $repos = Invoke-RestMethod -Uri "$($context.Endpoint)/api/v2/repos" -Headers $headers
        Write-Host 'Repositories:'
        $repos | ConvertTo-Json -Depth 6
        try {
            $memory = Invoke-RestMethod -Uri "$($context.Endpoint)/api/v1/agentmemory/status" -Headers $headers
            Write-Host 'Knowledge status:'
            $memory | ConvertTo-Json -Depth 6
            Write-Host 'Knowledge indexer status:'
            Invoke-RestMethod -Uri "$($context.Endpoint)/api/v1/agentmemory/indexer-status" -Headers $headers | ConvertTo-Json -Depth 6
            Write-Host 'Knowledge files:'
            Invoke-RestMethod -Uri "$($context.Endpoint)/api/v1/AgentMemory/files" -Headers $headers | ConvertTo-Json -Depth 6
        } catch {
            Write-Warning "Knowledge status is unproven: $($_.Exception.Message)"
        }
        $workloadResourceGroup = 'rg-sre-spoke-foodapp-paas'
        az containerapp list --resource-group $workloadResourceGroup --query '[].{name:name,state:properties.runningStatus,fqdn:properties.configuration.ingress.fqdn}' -o table
        az monitor app-insights component show --resource-group $workloadResourceGroup --app appi-food --query '{name:name,workspace:properties.WorkspaceResourceId}' -o table
        Write-Expected 'Log Analytics and Application Insights connectors are visible; repositories and knowledge files are empty while Agent Memory and its indexer are healthy.'
        Write-Prompt 'List the currently proven evidence planes. Distinguish healthy Agent Memory infrastructure from its empty document inventory; do not configure or upload anything.'
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
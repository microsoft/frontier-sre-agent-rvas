[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory)]
    [ValidateSet('00','01','02','03','04','05','06','07','08','09','10','11','12','13')]
    [string]$Challenge,
    [switch]$Execute,
    [switch]$Restore,
    [string]$EnvironmentName = 'signalops-core',
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
$SignalOpsRoot = Join-Path $RepoRoot 'SRE SignalOps'
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
    Push-Location $SignalOpsRoot
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
        if ($Restore) { throw 'Challenge 00 does not support -Restore. Use azd down only with explicit coach approval.' }
        Assert-Command azd
        $account = az account show | ConvertFrom-Json
        if ($account.name -ne 'MCAPS-Hybrid-REQ-150072-2026-rakau') {
            throw "Active subscription is '$($account.name)'; select MCAPS-Hybrid-REQ-150072-2026-rakau before continuing."
        }
        Push-Location (Join-Path $RepoRoot 'SRE SignalOps')
        try {
            Invoke-Native { azd env select $EnvironmentName }
            Invoke-Native { azd env set DEPLOY_AGENT false }
            Invoke-Native { azd env set DEPLOY_CONNECTORS false }
            if ($Execute) {
                if ($PSCmdlet.ShouldProcess($EnvironmentName, 'Provision workload and deploy applications with azd up')) {
                    Invoke-Native { azd up }
                }
            } else {
                Invoke-Native { azd provision --preview }
                Write-Host 'Preview only. Re-run with -Execute after reviewing the changes.' -ForegroundColor Yellow
            }
        } finally { Pop-Location }
        $workloadResourceGroup = Get-AzdValue 'AZURE_RESOURCE_GROUP'
        if (-not $workloadResourceGroup) { return }
        az group show --name $workloadResourceGroup --query '{name:name,location:location,state:properties.provisioningState}' -o table
        az resource list --resource-group $workloadResourceGroup --query '[].{name:name,type:type,location:location}' -o table
        $apps = az containerapp list --resource-group $workloadResourceGroup | ConvertFrom-Json
        $apps | Select-Object name,@{n='State';e={$_.properties.runningStatus}},@{n='FQDN';e={$_.properties.configuration.ingress.fqdn}} | Format-Table -AutoSize
        $frontend = $apps | Where-Object name -eq 'ca-food-frontend'
        $frontendUrl = "https://$($frontend.properties.configuration.ingress.fqdn)"
        Invoke-WebRequest -Uri $frontendUrl -UseBasicParsing | Select-Object StatusCode
        $appInsightsName = Get-AzdValue 'APPLICATIONINSIGHTS_NAME'
        az monitor app-insights component show --resource-group $workloadResourceGroup --app $appInsightsName --query '{name:name,workspace:properties.WorkspaceResourceId}' -o table
        Write-Expected 'The isolated azd workload contains both running Container Apps, a reachable frontend, and workspace-backed telemetry.'
    }
    '01' {
        if ($Restore) { throw 'Challenge 01 does not support -Restore.' }
        Assert-Command azd
        Push-Location (Join-Path $RepoRoot 'SRE SignalOps')
        try {
            Invoke-Native { azd env select $EnvironmentName }
            Invoke-Native { azd env set DEPLOY_AGENT true }
            Invoke-Native { azd env set DEPLOY_CONNECTORS false }
            if ($Execute) {
                if ($PSCmdlet.ShouldProcess($EnvironmentName, 'Provision the SRE Agent core with azd')) {
                    Invoke-Native { azd provision }
                }
            } else {
                Invoke-Native { azd provision --preview }
                Write-Host 'Preview only. Re-run with -Execute after reviewing the changes.' -ForegroundColor Yellow
            }
        } finally { Pop-Location }
        $agentId = Get-AzdValue 'SRE_AGENT_ID'
        if (-not $agentId) { return }
        $resolvedAgentName = Get-AzdValue 'SRE_AGENT_NAME'
        $resolvedAgentResourceGroup = Get-AzdValue 'AGENT_RESOURCE_GROUP'
        az rest --method GET --url "https://management.azure.com$agentId`?api-version=2026-01-01" --query 'properties.{state:provisioningState,power:powerState,endpoint:agentEndpoint,mode:actionConfiguration.mode,access:actionConfiguration.accessLevel,managedResources:knowledgeGraphConfiguration.managedResources}' -o json
        $principalId = (az identity show --resource-group $resolvedAgentResourceGroup --name "uai-$resolvedAgentName" --query principalId -o tsv).Trim()
        az role assignment list --assignee-object-id $principalId --all --query '[].{role:roleDefinitionName,scope:scope}' -o table
        Write-Expected 'The azd agent is Succeeded and Running with Autonomous/High configuration, workload-scoped Contributor, and subscription Monitoring Contributor.'
        Write-Prompt 'Audit this isolated autonomous lab agent and prove that write access does not extend beyond its workload resource group.'
    }
    '02' {
        if ($Restore) { throw 'Challenge 02 does not support -Restore.' }
        Assert-Command azd
        Push-Location (Join-Path $RepoRoot 'SRE SignalOps')
        try {
            Invoke-Native { azd env select $EnvironmentName }
            Invoke-Native { azd env set DEPLOY_AGENT true }
            Invoke-Native { azd env set DEPLOY_CONNECTORS true }
            if ($Execute) {
                if ($PSCmdlet.ShouldProcess($EnvironmentName, 'Provision SRE Agent evidence connectors with azd')) {
                    Invoke-Native { azd provision }
                }
            } else {
                Invoke-Native { azd provision --preview }
                Write-Host 'Preview only. Re-run with -Execute after reviewing the changes.' -ForegroundColor Yellow
            }
        } finally { Pop-Location }
        $agentId = Get-AzdValue 'SRE_AGENT_ID'
        if (-not $agentId) { return }
        $agent = az rest --method GET --url "https://management.azure.com$agentId`?api-version=2026-01-01" | ConvertFrom-Json
        $context = [pscustomobject]@{
            AgentId = $agentId
            Endpoint = $agent.properties.agentEndpoint.TrimEnd('/')
            Token = (az account get-access-token --resource https://azuresre.dev --query accessToken -o tsv).Trim()
        }
        $headers = @{ Authorization = "Bearer $($context.Token)" }
        az rest --method GET --url "https://management.azure.com$($context.AgentId)/connectors?api-version=2026-01-01" --query 'value[].{name:name,type:properties.dataConnectorType,source:properties.dataSource}' -o table
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
        $workloadResourceGroup = Get-AzdValue 'AZURE_RESOURCE_GROUP'
        az containerapp list --resource-group $workloadResourceGroup --query '[].{name:name,state:properties.runningStatus,fqdn:properties.configuration.ingress.fqdn}' -o table
        Write-Expected 'The two azd-managed Azure telemetry connectors are visible; repository and knowledge state is reported independently.'
        Write-Prompt 'List the currently proven evidence planes. Distinguish deployed connector infrastructure from populated source and knowledge evidence.'
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
[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory)]
    [ValidateSet('00','01','02','11','12','13','14')]
    [string]$Challenge,
    [switch]$Execute,
    [string]$EnvironmentName = 'signalops-core',
    [string]$Location = 'swedencentral',
    [string]$ResourceGroup,
    [string]$NicName,
    [string]$VmName,
    [string]$SourceIp,
    [string]$DestinationIp
)

$ErrorActionPreference = 'Stop'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$SignalOpsRoot = Join-Path $RepoRoot 'SRE SignalOps'

function Assert-Command([string]$Name) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command not found: $Name"
    }
}

function Invoke-Native([scriptblock]$Action) {
    & $Action
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

function Get-BashToolPath {
    $toolDirectories = Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages" -Recurse -File -Include jq.exe,yq.exe -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty DirectoryName -Unique |
        ForEach-Object { $_.Replace('\','/').Replace('C:','/c') }
    if (-not $toolDirectories) { return '' }
    return "export PATH='$($toolDirectories -join ':')':`"`$PATH`"; "
}

function Write-Prompt([string]$Text) {
    Write-Host "`nSRE incident exercise prompt" -ForegroundColor Cyan
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
    '11' {
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
    '12' {
        if (-not $ResourceGroup -or -not $NicName) { throw 'Challenge 12 requires -ResourceGroup and -NicName for the coach-provided sandbox.' }
        az network nic list-effective-nsg --resource-group $ResourceGroup --name $NicName -o jsonc
        Write-Expected 'The effective NSG output identifies the actual NIC/subnet associations and rule priorities.'
        Write-Prompt 'Identify the exact effective deny, affected and unaffected paths, and the narrowest reversible remediation. Do not delete a broad deny rule.'
    }
    '13' {
        if (-not $ResourceGroup -or -not $NicName) { throw 'Challenge 13 requires -ResourceGroup and -NicName.' }
        az network nic show-effective-route-table --resource-group $ResourceGroup --name $NicName -o table
        if ($VmName -and $SourceIp -and $DestinationIp) {
            az network watcher show-next-hop --resource-group $ResourceGroup --vm $VmName --source-ip $SourceIp --dest-ip $DestinationIp -o jsonc
        } else {
            Write-Host 'Add -VmName, -SourceIp, and -DestinationIp to run the next-hop check.' -ForegroundColor Yellow
        }
        Write-Expected 'Forward and return route evidence identifies the effective next hop or missing path.'
        Write-Prompt 'Prove forward and return paths separately, then distinguish routing from DNS, NSG, and application failure.'
    }
    '14' {
        $subscriptionId = (az account show --query id -o tsv).Trim()
        $resources = az resource list --subscription $subscriptionId -o json | ConvertFrom-Json
        $resources | Group-Object type | Sort-Object Count -Descending | Select-Object Count, Name | Format-Table -AutoSize
        az advisor recommendation list --subscription $subscriptionId --query '[].{category:category,impact:impact,resource:resourceMetadata.resourceId,problem:shortDescription.problem}' -o table
        az monitor log-analytics workspace list --subscription $subscriptionId --query '[].{name:name,resourceGroup:resourceGroup,retention:retentionInDays}' -o table
        Write-Expected 'Inventory, Advisor, and observability evidence are visible; unavailable cost or utilization access is reported as a gap.'
        Write-Prompt 'Produce three prioritized read-only recommendations across cost, reliability, observability, resilience, or governance. Include evidence, value, confidence, effort, trade-off, owner, and approval need.'
    }
}
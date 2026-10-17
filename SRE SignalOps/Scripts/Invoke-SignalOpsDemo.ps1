[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory)]
    [ValidateSet('00','01','02','09','10','11','12')]
    [string]$Challenge,
    [switch]$Execute,
    [string]$EnvironmentName = 'signalops-core',
    [string]$TerraformPath,
    [string]$SubscriptionId,
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
        throw "Could not read azd output $Name from the selected environment."
    } finally { Pop-Location }
}

function Assert-AzdSubscription {
    $active = (Invoke-Native { az account show --query id -o tsv } | Out-String).Trim()
    $target = (Invoke-Native { azd env get-value AZURE_SUBSCRIPTION_ID } | Out-String).Trim()
    if (-not $target -or $target -ne $active) {
        throw 'The selected azd environment and active Azure subscription do not match. Select the approved subscription before provisioning.'
    }
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

if ($Challenge -in @('09', '12')) {
    $contextArguments = if ($TerraformPath) { @{ TerraformPath = $TerraformPath } } else { @{ EnvironmentName = $EnvironmentName } }
    $Lab = & (Join-Path $PSScriptRoot 'Get-SignalOpsContext.ps1') @contextArguments
    $active = (Invoke-Native { az account show --query id -o tsv } | Out-String).Trim()
    if ($active -ne $Lab.AZURE_SUBSCRIPTION_ID) { throw 'Select the deployment subscription before running this mission.' }
}
if ($Challenge -in @('10', '11')) {
    $active = (Invoke-Native { az account show --query id -o tsv } | Out-String).Trim()
    if (-not $SubscriptionId -or $SubscriptionId -ne $active) {
        throw 'Pass -SubscriptionId for the approved network sandbox and select that Azure subscription.'
    }
}

switch ($Challenge) {
    '00' {
        Assert-Command azd
        Push-Location (Join-Path $RepoRoot 'SRE SignalOps')
        try {
            Invoke-Native { azd env select $EnvironmentName }
            Assert-AzdSubscription
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
        $frontendUrl = Get-AzdValue 'FRONTEND_URL'
        if (-not $frontendUrl) { throw 'The selected environment has no FRONTEND_URL output. Complete workload deployment first.' }
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
            Assert-AzdSubscription
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
            Assert-AzdSubscription
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
    '09' {
        $workloadResourceGroup = $Lab.AZURE_RESOURCE_GROUP
        $apiUrl = $Lab.API_BASE_URL
        if (-not $apiUrl) { throw 'Deployment context is missing API_BASE_URL.' }
        1..10 | ForEach-Object { Invoke-RestMethod -Uri "$apiUrl/api/restaurants" | Out-Null }
        $appId = (Invoke-Native { az resource list --resource-group $workloadResourceGroup --resource-type Microsoft.Insights/components --query '[0].id' -o tsv } | Out-String).Trim()
        if (-not $appId) { throw "No Application Insights component found in $workloadResourceGroup" }
        Invoke-Native { az monitor app-insights query --app $appId --analytics-query 'requests | where timestamp > ago(30m) | summarize requests=count(), failures=countif(success == false), p95=percentile(duration, 95), firstSeen=min(timestamp), lastSeen=max(timestamp) by cloud_RoleName, name, url | extend failureRate=1.0*failures/requests' -o table }
        Invoke-Native { az monitor app-insights query --app $appId --analytics-query 'dependencies | where timestamp > ago(30m) | summarize calls=count(), failures=countif(success == false), p95=percentile(duration, 95), firstSeen=min(timestamp), lastSeen=max(timestamp) by cloud_RoleName, target, type, name, data | extend failureRate=1.0*failures/calls' -o table }
        Write-Expected 'API requests appear; absent browser or downstream edges remain explicitly unobserved.'
        Write-Prompt 'Create an evidence-backed dependency map. For each edge include direction, protocol, timestamp, volume, latency, failure rate, and evidence source; label unobserved edges.'
    }
    '10' {
        if (-not $ResourceGroup -or -not $NicName) { throw 'Challenge 10 requires -ResourceGroup and -NicName for the coach-provided sandbox.' }
        Invoke-Native { az network nic list-effective-nsg --subscription $SubscriptionId --resource-group $ResourceGroup --name $NicName -o jsonc }
        Write-Expected 'The effective NSG output identifies the actual NIC/subnet associations and rule priorities.'
        Write-Prompt 'Identify the exact effective deny, affected and unaffected paths, and the narrowest reversible remediation. Do not delete a broad deny rule.'
    }
    '11' {
        if (-not $ResourceGroup -or -not $NicName) { throw 'Challenge 11 requires -ResourceGroup and -NicName.' }
        Invoke-Native { az network nic show-effective-route-table --subscription $SubscriptionId --resource-group $ResourceGroup --name $NicName -o table }
        if ($VmName -and $SourceIp -and $DestinationIp) {
            Invoke-Native { az network watcher show-next-hop --subscription $SubscriptionId --resource-group $ResourceGroup --vm $VmName --source-ip $SourceIp --dest-ip $DestinationIp -o jsonc }
        } else {
            Write-Host 'Add -VmName, -SourceIp, and -DestinationIp to run the next-hop check.' -ForegroundColor Yellow
        }
        Write-Expected 'This is one source-side observation. Repeat for the destination NIC/VM to prove the return path; no fault or recovery is performed.'
        Write-Prompt 'Prove forward and return paths separately, then distinguish routing from DNS, NSG, and application failure.'
    }
    '12' {
        $subscriptionId = $Lab.AZURE_SUBSCRIPTION_ID
        $resources = Invoke-Native { az resource list --subscription $subscriptionId -o json } | ConvertFrom-Json
        $resources | Group-Object type | Sort-Object Count -Descending | Select-Object Count, Name | Format-Table -AutoSize
        Invoke-Native { az advisor recommendation list --subscription $subscriptionId --query '[].{category:category,impact:impact,resource:resourceMetadata.resourceId,problem:shortDescription.problem}' -o table }
        Invoke-Native { az monitor log-analytics workspace list --subscription $subscriptionId --query '[].{name:name,resourceGroup:resourceGroup,retention:retentionInDays}' -o table }
        Write-Warning 'This wrapper does not query Cost Management, utilization, backup coverage, fired alerts or stale telemetry. Those evidence planes remain unassessed until separately queried.'
        Write-Expected 'Inventory, Advisor, and observability evidence are visible; unavailable cost or utilization access is reported as a gap.'
        Write-Prompt 'Produce only evidence-supported read-only recommendations across the approved subscription. Include evidence, value, confidence, effort, trade-off, owner, and approval need. Report zero findings or fewer than three when that is all the evidence supports; distinguish unassessed sources from actual issues.'
    }
}
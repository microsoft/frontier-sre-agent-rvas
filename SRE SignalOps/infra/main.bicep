targetScope = 'subscription'

@minLength(1)
@maxLength(20)
param environmentName string

param location string = 'swedencentral'
param principalId string
param deployAgent string = 'false'
param deployConnectors string = 'false'
param apiImage string = ''
param frontendImage string = ''

var token = toLower(replace(environmentName, '-', ''))
var suffix = take(uniqueString(subscription().id, environmentName), 6)
var workloadResourceGroupName = 'rg-${token}-food'
var agentResourceGroupName = 'rg-${token}-agent'
var shouldDeployAgent = toLower(deployAgent) == 'true' || toLower(deployConnectors) == 'true'
var shouldDeployConnectors = toLower(deployConnectors) == 'true'
var monitoringContributorRoleId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '749f88d5-cbae-40b8-bcfc-e573ddc772fa')
var tags = {
  workload: 'azure-sre-agent'
  'managed-by': 'azd'
  environment: environmentName
  owner: 'sre-platform'
  repository: 'frontier-sre-agent-rvas'
}

resource workloadResourceGroup 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: workloadResourceGroupName
  location: location
  tags: tags
}

resource agentResourceGroup 'Microsoft.Resources/resourceGroups@2024-03-01' = if (shouldDeployAgent) {
  name: agentResourceGroupName
  location: location
  tags: tags
}

module workload 'modules/workload.bicep' = {
  name: 'signalops-workload'
  scope: workloadResourceGroup
  params: {
    environmentName: environmentName
    location: location
    suffix: suffix
    apiImage: apiImage
    frontendImage: frontendImage
    tags: tags
  }
}

module agent 'modules/agent.bicep' = if (shouldDeployAgent) {
  name: 'signalops-agent'
  scope: agentResourceGroup
  params: {
    environmentName: environmentName
    location: location
    suffix: suffix
    principalId: principalId
    deployConnectors: shouldDeployConnectors
    workloadResourceGroupId: workloadResourceGroup.id
    workloadLogAnalyticsId: workload.outputs.logAnalyticsWorkspaceId
    tags: tags
  }
}

module workloadRbac 'modules/workload-rbac.bicep' = if (shouldDeployAgent) {
  name: 'signalops-workload-rbac'
  scope: workloadResourceGroup
  params: {
    environmentName: environmentName
    identityPrincipalId: agent!.outputs.identityPrincipalId
  }
}

resource subscriptionMonitoringContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (shouldDeployAgent) {
  name: guid(subscription().id, environmentName, 'signalops-agent', monitoringContributorRoleId)
  properties: { roleDefinitionId: monitoringContributorRoleId, principalId: agent!.outputs.identityPrincipalId, principalType: 'ServicePrincipal' }
}

output AZURE_LOCATION string = location
output AZURE_TENANT_ID string = tenant().tenantId
output AZURE_RESOURCE_GROUP string = workloadResourceGroup.name
output WORKLOAD_RESOURCE_GROUP string = workloadResourceGroup.name
output AGENT_RESOURCE_GROUP string = shouldDeployAgent ? agentResourceGroup.name : ''
output AZURE_CONTAINER_REGISTRY_ENDPOINT string = workload.outputs.containerRegistryEndpoint
output AZURE_CONTAINER_REGISTRY_NAME string = workload.outputs.containerRegistryName
output APPLICATIONINSIGHTS_NAME string = workload.outputs.applicationInsightsName
output LOG_ANALYTICS_WORKSPACE_ID string = workload.outputs.logAnalyticsWorkspaceId
output API_BASE_URL string = workload.outputs.apiUrl
output FRONTEND_URL string = workload.outputs.frontendUrl
output SRE_AGENT_NAME string = shouldDeployAgent ? agent!.outputs.agentName : ''
output SRE_AGENT_ID string = shouldDeployAgent ? agent!.outputs.agentId : ''

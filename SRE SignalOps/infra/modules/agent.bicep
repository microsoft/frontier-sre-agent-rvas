param environmentName string
param location string
param suffix string
param principalId string
param deployConnectors bool
param workloadResourceGroupId string
param workloadLogAnalyticsId string
param tags object

var token = take(toLower(replace(environmentName, '-', '')), 12)
var agentName = '${token}-sre-agent'
var identityName = 'uai-${agentName}'
var sreAgentAdminRoleId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'e79298df-d852-4c6d-84f9-5d13249d1e55')

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: identityName
  location: location
  tags: tags
}

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'law-${agentName}-${suffix}'
  location: location
  tags: tags
  properties: {
    retentionInDays: 30
    features: {
      enableLogAccessUsingOnlyResourcePermissions: true
    }
    sku: { name: 'PerGB2018' }
  }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: 'appi-${agentName}-${suffix}'
  location: location
  kind: 'web'
  tags: tags
  properties: {
    Application_Type: 'web'
    DisableLocalAuth: true
    IngestionMode: 'LogAnalytics'
    WorkspaceResourceId: logAnalytics.id
  }
}

resource agent 'Microsoft.App/agents@2026-01-01' = {
  name: agentName
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${identity.id}': {}
    }
  }
  properties: {
    actionConfiguration: {
      accessLevel: 'High'
      identity: identity.id
      mode: 'Autonomous'
    }
    defaultModel: {
      name: 'claude-opus-4-6'
      provider: 'Anthropic'
    }
    incidentManagementConfiguration: {
      type: 'AzMonitor'
      connectionName: 'azmonitor'
    }
    knowledgeGraphConfiguration: {
      identity: identity.id
      managedResources: [ subscription().id, workloadResourceGroupId, workloadLogAnalyticsId ]
    }
    logConfiguration: {
      applicationInsightsConfiguration: {
        appId: appInsights.properties.AppId
        connectionString: appInsights.properties.ConnectionString
      }
    }
    #disable-next-line BCP037 // Documented by the Microsoft.App/agents ARM API; missing from current Bicep types.
    monthlyAgentUnitLimit: 500
    upgradeChannel: 'Stable'
  }
}

resource currentUserAdmin 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: agent
  name: guid(agent.id, principalId, sreAgentAdminRoleId)
  properties: {
    roleDefinitionId: sreAgentAdminRoleId
    principalId: principalId
  }
}

resource logAnalyticsConnector 'Microsoft.App/agents/connectors@2026-01-01' = if (deployConnectors) {
  parent: agent
  name: 'log-analytics'
  properties: {
    dataConnectorType: 'LogAnalytics'
    #disable-next-line use-secure-value-for-secure-inputs // Resource IDs are identifiers, not credentials.
    dataSource: workloadLogAnalyticsId
    identity: identity.id
  }
}

resource applicationInsightsConnector 'Microsoft.App/agents/connectors@2026-01-01' = if (deployConnectors) {
  parent: agent
  name: 'application-insights'
  properties: {
    dataConnectorType: 'AppInsights'
    #disable-next-line use-secure-value-for-secure-inputs // Resource IDs are identifiers, not credentials.
    dataSource: appInsights.id
    identity: identity.id
  }
}

output agentName string = agent.name
output agentId string = agent.id
output identityPrincipalId string = identity.properties.principalId

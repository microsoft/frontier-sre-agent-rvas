param environmentName string
param location string
@minLength(6)
param suffix string
param apiImage string
param frontendImage string
param tags object

var token = take(toLower(replace(environmentName, '-', '')), 12)
var registryName = take('cr${token}${suffix}', 50)

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'law-${token}-${suffix}'
  location: location
  tags: tags
  properties: {
    retentionInDays: 30
    features: {
      enableLogAccessUsingOnlyResourcePermissions: true
    }
    sku: {
      name: 'PerGB2018'
    }
  }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: 'appi-${token}-food'
  location: location
  kind: 'web'
  tags: tags
  properties: {
    Application_Type: 'web'
    IngestionMode: 'LogAnalytics'
    WorkspaceResourceId: logAnalytics.id
  }
}

resource registry 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: registryName
  location: location
  tags: tags
  sku: {
    name: 'Basic'
  }
  properties: {
    adminUserEnabled: false
    publicNetworkAccess: 'Enabled'
  }
}

resource environment 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: 'cae-${token}-food'
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalytics.properties.customerId
        sharedKey: logAnalytics.listKeys().primarySharedKey
      }
    }
  }
}

resource apiIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'uai-${token}-food-api'
  location: location
  tags: tags
}

resource frontendIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'uai-${token}-food-frontend'
  location: location
  tags: tags
}

var acrPullRoleId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d')

resource apiAcrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: registry
  name: guid(registry.id, apiIdentity.id, acrPullRoleId)
  properties: {
    roleDefinitionId: acrPullRoleId
    principalId: apiIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource frontendAcrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: registry
  name: guid(registry.id, frontendIdentity.id, acrPullRoleId)
  properties: {
    roleDefinitionId: acrPullRoleId
    principalId: frontendIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource api 'Microsoft.App/containerApps@2024-03-01' = {
  name: 'ca-${token}-food-api'
  location: location
  tags: union(tags, { 'azd-service-name': 'api' })
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${apiIdentity.id}': {}
    }
  }
  properties: {
    managedEnvironmentId: environment.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 8080
        transport: 'auto'
      }
      registries: [
        {
          server: registry.properties.loginServer
          identity: apiIdentity.id
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'food-api'
          image: empty(apiImage) ? 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest' : apiImage
          env: [
            { name: 'ASPNETCORE_ENVIRONMENT', value: 'Production' }
            { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: appInsights.properties.ConnectionString }
          ]
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 5
      }
    }
  }
  dependsOn: [ apiAcrPull ]
}

resource frontend 'Microsoft.App/containerApps@2024-03-01' = {
  name: 'ca-${token}-food-frontend'
  location: location
  tags: union(tags, { 'azd-service-name': 'frontend' })
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${frontendIdentity.id}': {}
    }
  }
  properties: {
    managedEnvironmentId: environment.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 80
        transport: 'auto'
      }
      registries: [
        {
          server: registry.properties.loginServer
          identity: frontendIdentity.id
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'food-frontend'
          image: empty(frontendImage) ? 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest' : frontendImage
          env: [
            { name: 'REACT_APP_API_BASE_URL', value: 'https://${api.properties.configuration.ingress.fqdn}/api' }
          ]
          resources: {
            cpu: json('0.25')
            memory: '0.5Gi'
          }
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 3
      }
    }
  }
  dependsOn: [ frontendAcrPull ]
}

output containerRegistryEndpoint string = registry.properties.loginServer
output containerRegistryName string = registry.name
output applicationInsightsName string = appInsights.name
output logAnalyticsWorkspaceId string = logAnalytics.id
output apiUrl string = 'https://${api.properties.configuration.ingress.fqdn}'
output frontendUrl string = 'https://${frontend.properties.configuration.ingress.fqdn}'

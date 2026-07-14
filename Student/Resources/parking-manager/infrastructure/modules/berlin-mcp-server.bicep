// Berlin MCP Server module - Container App for monitoring Berlin API
@description('Location for all MCP server resources')
param location string

@description('Environment name (e.g., dev, prod) - NOTE: Not used in resource naming as resources are hardcoded to match existing manually deployed Azure resources')
param environment string = 'dev'

@description('Container subnet ID from hub VNet')
param containerSubnetId string

@description('URL of the Berlin Parking API to monitor')
param berlinApiUrl string

@description('Container image for the MCP server')
param containerImage string = ''

@description('Container registry server (leave empty for public registries)')
param containerRegistry string = ''

@description('MCP authentication token (Bearer token)')
@secure()
param mcpAuthToken string = ''

@description('Tags to apply to resources')
param tags object = {}

// Log Analytics Workspace for MCP server logs
// Note: Name does not include environment suffix to match manually deployed resource in Azure
resource logAnalyticsWorkspace 'Microsoft.OperationalInsights/workspaces@2022-10-01' = {
  name: 'law-berlin-mcp'
  location: location
  tags: tags
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
}

// Application Insights for MCP server monitoring
// Note: Name does not include environment suffix to match manually deployed resource in Azure
resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: 'appi-parking-berlin-mcp'
  location: location
  tags: tags
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logAnalyticsWorkspace.id
    IngestionMode: 'LogAnalytics'
    publicNetworkAccessForIngestion: 'Enabled'
    publicNetworkAccessForQuery: 'Enabled'
  }
}

// Container App Environment for MCP server
// Note: Name does not include environment suffix to match manually deployed resource in Azure
resource containerAppEnvironment 'Microsoft.App/managedEnvironments@2023-05-01' = {
  name: 'cae-berlin-mcp'
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalyticsWorkspace.properties.customerId
        sharedKey: listKeys(logAnalyticsWorkspace.id, '2022-10-01').primarySharedKey
      }
    }
    vnetConfiguration: {
      infrastructureSubnetId: containerSubnetId
    }
    workloadProfiles: [
      {
        name: 'Consumption'
        workloadProfileType: 'Consumption'
      }
    ]
  }
}

// Container App for MCP server
// Note: Name does not include environment suffix to match manually deployed resource in Azure
resource containerApp 'Microsoft.App/containerApps@2023-05-01' = {
  name: 'ca-berlin-mcp'
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    environmentId: containerAppEnvironment.id
    configuration: {
      ingress: {
        external: true
        targetPort: 8080
        transport: 'http'
        allowInsecure: false
      }
      registries: empty(containerRegistry) ? [] : [
        {
          server: containerRegistry
          identity: 'system'
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'berlin-mcp-server'
          image: empty(containerImage) ? 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest' : containerImage
          resources: {
            cpu: json('0.25')
            memory: '0.5Gi'
          }
          env: [
            {
              name: 'BERLIN_API_URL'
              value: berlinApiUrl
            }
            {
              name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
              value: appInsights.properties.ConnectionString
            }
            {
              name: 'MCP_AUTH_TOKEN'
              value: mcpAuthToken
            }
          ]
          probes: [
            {
              type: 'Startup'
              httpGet: {
                path: '/startup'
                port: 8080
                scheme: 'HTTP'
              }
              initialDelaySeconds: 5
              periodSeconds: 5
              timeoutSeconds: 3
              failureThreshold: 12
            }
            {
              type: 'Readiness'
              httpGet: {
                path: '/health'
                port: 8080
                scheme: 'HTTP'
              }
              initialDelaySeconds: 5
              periodSeconds: 5
              timeoutSeconds: 3
              failureThreshold: 6
            }
            {
              type: 'Liveness'
              httpGet: {
                path: '/health'
                port: 8080
                scheme: 'HTTP'
              }
              initialDelaySeconds: 30
              periodSeconds: 10
              timeoutSeconds: 5
              failureThreshold: 3
            }
          ]
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 3
        rules: [
          {
            name: 'http-scaling'
            http: {
              metadata: {
                concurrentRequests: '10'
              }
            }
          }
        ]
      }
    }
  }
}

// Outputs
output containerAppName string = containerApp.name
output containerAppFqdn string = containerApp.properties.configuration.ingress.fqdn
output mcpServerUrl string = 'https://${containerApp.properties.configuration.ingress.fqdn}'
output containerAppEnvironmentName string = containerAppEnvironment.name
output containerAppEnvironmentId string = containerAppEnvironment.id
output appInsightsName string = appInsights.name
output logAnalyticsWorkspaceName string = logAnalyticsWorkspace.name
output containerAppPrincipalId string = containerApp.identity.principalId

// VM Health Control module - Container App for simulating unhealthy VM log entries
// Deployed into the chaos-control resource group, sharing the same Container App Environment.
// The custom table (VMHealthStatus_CL) must be created separately in the hub RG
// (see vm-health-table.bicep) because it is a child of the Log Analytics workspace.
@description('Location for all VM Health Control resources')
param location string

@description('Existing Container App Environment ID (shared with chaos-control)')
param containerAppEnvironmentId string

@description('Container image name')
param containerImage string = 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'

@description('Container registry server (leave empty for public registries)')
param containerRegistry string = ''

@description('Log Analytics workspace resource ID for the DCR destination')
param logAnalyticsWorkspaceId string

@description('Tags to apply to resources')
param tags object = {}

// Dedicated Data Collection Endpoint for VM health ingestion
resource vmHealthDce 'Microsoft.Insights/dataCollectionEndpoints@2022-06-01' = {
  name: 'dce-vm-health-status'
  location: location
  tags: tags
  properties: {
    networkAcls: {
      publicNetworkAccess: 'Enabled'
    }
  }
}

// Data Collection Rule for ingesting VM health logs
resource vmHealthDcr 'Microsoft.Insights/dataCollectionRules@2022-06-01' = {
  name: 'dcr-vm-health-status'
  location: location
  tags: tags
  properties: {
    dataCollectionEndpointId: vmHealthDce.id
    streamDeclarations: {
      'Custom-VMHealthStatus_CL': {
        columns: [
          { name: 'TimeGenerated', type: 'datetime' }
          { name: 'vmName', type: 'string' }
          { name: 'city', type: 'string' }
          { name: 'healthState', type: 'string' }
          { name: 'previousState', type: 'string' }
          { name: 'severity', type: 'string' }
          { name: 'source', type: 'string' }
          { name: 'message', type: 'string' }
          { name: 'resourceGroup', type: 'string' }
          { name: 'subscriptionId', type: 'string' }
          { name: 'resourceType', type: 'string' }
        ]
      }
    }
    destinations: {
      logAnalytics: [
        {
          name: 'la-vm-health'
          workspaceResourceId: logAnalyticsWorkspaceId
        }
      ]
    }
    dataFlows: [
      {
        streams: [ 'Custom-VMHealthStatus_CL' ]
        destinations: [ 'la-vm-health' ]
        outputStream: 'Custom-VMHealthStatus_CL'
        transformKql: 'source'
      }
    ]
  }
}

// Monitoring Metrics Publisher role on the DCR so the container app can ingest logs
var monitoringMetricsPublisherRoleId = '3913510d-42f4-4e42-8a64-420c390055eb'

resource dcrRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(vmHealthDcr.id, containerApp.id, monitoringMetricsPublisherRoleId)
  scope: vmHealthDcr
  properties: {
    principalId: containerApp.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', monitoringMetricsPublisherRoleId)
  }
}

resource containerApp 'Microsoft.App/containerApps@2023-05-01' = {
  name: 'ca-vm-health-control'
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    environmentId: containerAppEnvironmentId
    configuration: {
      ingress: {
        external: true
        targetPort: 3095
        transport: 'auto'
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
          name: 'vm-health-control'
          image: containerImage
          resources: {
            cpu: json('0.25')
            memory: '0.5Gi'
          }
          env: [
            {
              name: 'PORT'
              value: '3095'
            }
            {
              name: 'NODE_ENV'
              value: 'production'
            }
            {
              name: 'DCE_ENDPOINT'
              value: vmHealthDce.properties.logsIngestion.endpoint
            }
            {
              name: 'DCR_RULE_ID'
              value: vmHealthDcr.properties.immutableId
            }
            {
              name: 'DCR_STREAM_NAME'
              value: 'Custom-VMHealthStatus_CL'
            }
          ]
          probes: [
            {
              type: 'liveness'
              httpGet: {
                path: '/health'
                port: 3095
              }
              initialDelaySeconds: 10
              periodSeconds: 30
            }
            {
              type: 'readiness'
              httpGet: {
                path: '/health'
                port: 3095
              }
              initialDelaySeconds: 5
              periodSeconds: 10
            }
          ]
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 2
        rules: [
          {
            name: 'http-scaling'
            http: {
              metadata: {
                concurrentRequests: '20'
              }
            }
          }
        ]
      }
    }
  }
}

output containerAppName string = containerApp.name
output containerAppFqdn string = containerApp.properties.configuration.ingress.fqdn
output containerAppUrl string = 'https://${containerApp.properties.configuration.ingress.fqdn}'
output containerAppPrincipalId string = containerApp.identity.principalId
output dcrRuleId string = vmHealthDcr.properties.immutableId
output dceEndpointId string = vmHealthDce.id
output dceLogsUri string = vmHealthDce.properties.logsIngestion.endpoint

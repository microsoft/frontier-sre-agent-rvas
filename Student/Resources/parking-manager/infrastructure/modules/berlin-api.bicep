// Berlin API module - Container App for Docker-based API
// NOTE: This module creates its own Container App Environment (separate from Lisbon)
// and does NOT send logs to Log Analytics (console/stdout only)
@description('Location for all Berlin API resources')
param location string

@description('Container subnet ID from hub VNet')
param containerSubnetId string

@description('Container image name')
param containerImage string = 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'

@description('Container registry server (leave empty for public registries)')
param containerRegistry string = ''

@description('Tags to apply to resources')
param tags object = {}

// Container App Environment (NO Log Analytics integration)
resource containerAppEnvironment 'Microsoft.App/managedEnvironments@2023-05-01' = {
  name: 'cae-parking-berlin'
  location: location
  tags: tags
  properties: {
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

// Container App (NO Log Analytics integration)
resource containerApp 'Microsoft.App/containerApps@2023-05-01' = {
  name: 'ca-parking-berlin'
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
        targetPort: 3004
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
          name: 'berlin-parking-api'
          image: containerImage
          resources: {
            cpu: json('0.25')
            memory: '0.5Gi'
          }
          env: [
            {
              name: 'PARKING_CITY'
              value: 'Berlin'
            }
            {
              name: 'PARKING_NAME'
              value: 'Berlin Central Parking'
            }
            {
              name: 'PARKING_LOCATION'
              value: 'Alexanderplatz, Berlin, Germany'
            }
            {
              name: 'PORT'
              value: '3004'
            }
            {
              name: 'NODE_ENV'
              value: 'production'
            }
          ]
          probes: [
            {
              type: 'liveness'
              httpGet: {
                path: '/health'
                port: 3004
              }
              initialDelaySeconds: 10
              periodSeconds: 30
            }
            {
              type: 'readiness'
              httpGet: {
                path: '/health'
                port: 3004
              }
              initialDelaySeconds: 5
              periodSeconds: 10
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
output containerAppUrl string = 'https://${containerApp.properties.configuration.ingress.fqdn}'
output containerAppEnvironmentName string = containerAppEnvironment.name
output containerAppEnvironmentId string = containerAppEnvironment.id
output containerAppPrincipalId string = containerApp.identity.principalId

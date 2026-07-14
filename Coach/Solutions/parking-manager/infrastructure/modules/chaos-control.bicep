// Chaos Control module - Container App for centralized chaos configuration
@description('Location for all Chaos Control resources')
param location string

@description('Container subnet ID from hub VNet')
param containerSubnetId string

@description('Environment name (e.g., dev, test, prod)')
param environment string = 'dev'

@description('Container image name')
param containerImage string = 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'

@description('Container registry server (leave empty for public registries)')
param containerRegistry string = ''

@description('Tags to apply to resources')
param tags object = {}

resource containerAppEnvironment 'Microsoft.App/managedEnvironments@2023-05-01' = {
  name: 'cae-chaos-control'
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

resource containerApp 'Microsoft.App/containerApps@2023-05-01' = {
  name: 'ca-chaos-control'
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
        targetPort: 3090
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
          name: 'chaos-control'
          image: containerImage
          resources: {
            cpu: json('0.25')
            memory: '0.5Gi'
          }
          env: [
            {
              name: 'PORT'
              value: '3090'
            }
            {
              name: 'NODE_ENV'
              value: 'production'
            }
            {
              name: 'CHAOS_ENVIRONMENT'
              value: environment
            }
          ]
          probes: [
            {
              type: 'liveness'
              httpGet: {
                path: '/health'
                port: 3090
              }
              initialDelaySeconds: 10
              periodSeconds: 30
            }
            {
              type: 'readiness'
              httpGet: {
                path: '/health'
                port: 3090
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
output containerAppEnvironmentName string = containerAppEnvironment.name
output containerAppEnvironmentId string = containerAppEnvironment.id
output containerAppPrincipalId string = containerApp.identity.principalId

// Azure Container Registry module
@description('Location for the Container Registry')
param location string

@description('Environment name (e.g., dev, test, prod)')
param environment string

@description('SKU for the Container Registry')
@allowed([
  'Basic'
  'Standard'
  'Premium'
])
param sku string = 'Basic'

@description('Enable admin user for the registry')
param adminUserEnabled bool = true

@description('Tags to apply to resources')
param tags object = {}

// Container Registry name must be globally unique and lowercase
var acrName = 'acrparking${environment}${uniqueString(resourceGroup().id)}'

resource containerRegistry 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: acrName
  location: location
  tags: tags
  sku: {
    name: sku
  }
  properties: {
    adminUserEnabled: adminUserEnabled
    publicNetworkAccess: 'Enabled'
    networkRuleBypassOptions: 'AzureServices'
    zoneRedundancy: sku == 'Premium' ? 'Enabled' : 'Disabled'
    policies: {
      quarantinePolicy: {
        status: 'disabled'
      }
      trustPolicy: {
        type: 'Notary'
        status: 'disabled'
      }
      retentionPolicy: {
        days: 7
        status: 'disabled'
      }
    }
  }
}

// Outputs
output registryName string = containerRegistry.name
output registryId string = containerRegistry.id
output loginServer string = containerRegistry.properties.loginServer
output registryUrl string = 'https://${containerRegistry.properties.loginServer}'

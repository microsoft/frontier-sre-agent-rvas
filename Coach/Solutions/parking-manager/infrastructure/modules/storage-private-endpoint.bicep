// Private endpoint for Storage (blob) + Private DNS linking
@description('Location for network resources')
param location string

@description('Existing VNet name where private endpoint will be placed')
param vnetName string

@description('Subnet name to host the private endpoint (e.g., snet-vms)')
param subnetName string = 'snet-vms'

@description('Target Storage Account resource ID')
param storageAccountId string

@description('Tags to apply to resources')
param tags object = {}

// Existing VNet and Subnet references
resource vnet 'Microsoft.Network/virtualNetworks@2023-05-01' existing = {
  name: vnetName
}

resource subnet 'Microsoft.Network/virtualNetworks/subnets@2023-05-01' existing = {
  parent: vnet
  name: subnetName
}

// Private DNS zone for blob private endpoints
resource dnsZone 'Microsoft.Network/privateDnsZones@2020-06-01' = {
  name: 'privatelink.blob.${environment().suffixes.storage}'
  location: 'global'
  tags: tags
}

// Link VNet to the private DNS zone
resource dnsZoneLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = {
  name: 'link-${vnetName}'
  parent: dnsZone
  location: 'global'
  properties: {
    virtualNetwork: {
      id: vnet.id
    }
    registrationEnabled: false
  }
}

// Private Endpoint to Storage blob
resource peStorage 'Microsoft.Network/privateEndpoints@2023-05-01' = {
  name: 'pe-deployment-storage-blob'
  location: location
  tags: tags
  properties: {
    subnet: {
      id: subnet.id
    }
    privateLinkServiceConnections: [
      {
        name: 'pls-deployment-storage-blob'
        properties: {
          privateLinkServiceId: storageAccountId
          groupIds: [ 'blob' ]
        }
      }
    ]
  }
}

// Associate private DNS zone with private endpoint
resource peDnsZoneGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2023-05-01' = {
  name: 'zonegroup-blob'
  parent: peStorage
  properties: {
    privateDnsZoneConfigs: [
      {
        name: 'blob-zone-config'
        properties: {
          privateDnsZoneId: dnsZone.id
        }
      }
    ]
  }
}

output privateEndpointId string = peStorage.id
output privateDnsZoneId string = dnsZone.id

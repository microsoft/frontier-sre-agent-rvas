// GitHub-hosted runners private networking (Azure VNet integration)
@description('Location for network resources')
param location string

@description('Existing VNet name where runner subnet will be created')
param vnetName string

@description('Subnet CIDR for GitHub runners (recommended: /24)')
param runnerSubnetPrefix string

@description('GitHub organization databaseId (GraphQL) used as businessId')
param githubOrgDatabaseId string

@description('NAT Gateway ID for outbound connectivity')
param natGatewayId string

@description('Tags to apply to resources')
param tags object = {}

// Network Security Group with required outbound rules
resource actions_NSG 'Microsoft.Network/networkSecurityGroups@2023-05-01' = {
  name: 'nsg-github-actions'
  location: location
  tags: tags
  properties: {
    securityRules: [
      // Allow outbound to VNet for 443
      {
        name: 'AllowVnetOutBound443'
        properties: {
          protocol: 'Tcp'
          sourcePortRange: '*'
          destinationPortRange: '443'
          sourceAddressPrefix: '*'
          destinationAddressPrefix: 'VirtualNetwork'
          access: 'Allow'
          priority: 200
          direction: 'Outbound'
        }
      }, {
        name: 'AllowStorageOutbound443'
        properties: {
          protocol: '*'
          sourcePortRange: '*'
          destinationPortRange: '443'
          sourceAddressPrefix: '*'
          destinationAddressPrefix: 'Storage'
          access: 'Allow'
          priority: 230
          direction: 'Outbound'
        }
      }, {
        name: 'AllowGitHubOutbound443'
        properties: {
          protocol: '*'
          sourcePortRange: '*'
          destinationPortRange: '443'
          sourceAddressPrefix: '*'
          access: 'Allow'
          priority: 220
          direction: 'Outbound'
          destinationAddressPrefix: '*'

        }
      }
    ]
  }
}

// Reference existing VNet in current resource group
resource vnet 'Microsoft.Network/virtualNetworks@2023-05-01' existing = {
  name: vnetName
}

// Create delegated subnet for GitHub-hosted runners
resource runnerSubnet 'Microsoft.Network/virtualNetworks/subnets@2023-05-01' = {
  parent: vnet
  name: 'snet-github-runners'
  properties: {
    addressPrefix: runnerSubnetPrefix
    delegations: [
      {
        name: 'GitHub.Network/networkSettings'
        properties: {
          serviceName: 'GitHub.Network/networkSettings'
        }
      }
    ]
    networkSecurityGroup: {
      id: actions_NSG.id
    }
    natGateway: {
      id: natGatewayId
    }
  }
}

// Create Network Settings resource to bind subnet to GitHub Actions service
resource networkSettings 'GitHub.Network/networkSettings@2024-04-02' = {
  name: 'github-actions-network-settings'
  location: location
  properties: {
    subnetId: runnerSubnet.id
    businessId: githubOrgDatabaseId
  }
  tags: {
    GitHubId: githubOrgDatabaseId
  }
}

// Outputs for GitHub configuration
output runnerSubnetId string = runnerSubnet.id
output networkSettingsResourceId string = networkSettings.id

// Hub infrastructure module - VNet and Log Analytics Workspace
@description('Location for all hub resources')
param location string

@description('Virtual Network address prefix')
param vnetAddressPrefix string = '10.0.0.0/16'

@description('Subnet address prefix for VMs')
param vmSubnetPrefix string = '10.0.1.0/24'

@description('Subnet address prefix for Container Apps')
param containerSubnetPrefix string = '10.0.2.0/23'

@description('Allowed source IP address prefix for SSH/RDP access. Use specific IP ranges in production.')
param allowedSourceIpPrefix string = '*'

@description('Tags to apply to resources')
param tags object = {}

// Network Security Group for App Service
resource nsgAppService 'Microsoft.Network/networkSecurityGroups@2023-05-01' = {
  name: 'nsg-app-service'
  location: location
  tags: tags
  properties: {
    securityRules: []
  }
}

// Network Security Group for VMs
// Note: In production, restrict SSH/RDP access to specific IP ranges using allowedSourceIpPrefix parameter
resource nsgVms 'Microsoft.Network/networkSecurityGroups@2023-05-01' = {
  name: 'nsg-vms'
  location: location
  tags: tags
  properties: {
    securityRules: [
      {
        name: 'AllowHTTP'
        properties: {
          priority: 100
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourcePortRange: '*'
          destinationPortRange: '80'
          sourceAddressPrefix: '*'
          destinationAddressPrefix: '*'
        }
      }
      {
        name: 'AllowHTTPS'
        properties: {
          priority: 110
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourcePortRange: '*'
          destinationPortRange: '443'
          sourceAddressPrefix: '*'
          destinationAddressPrefix: '*'
        }
      }
      {
        name: 'AllowAPIPort3002'
        properties: {
          priority: 120
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourcePortRange: '*'
          destinationPortRange: '3002'
          sourceAddressPrefix: '*'
          destinationAddressPrefix: '*'
        }
      }
      {
        name: 'AllowAPIPort3003'
        properties: {
          priority: 130
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourcePortRange: '*'
          destinationPortRange: '3003'
          sourceAddressPrefix: '*'
          destinationAddressPrefix: '*'
        }
      }
      {
        name: 'AllowSSH'
        properties: {
          priority: 200
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourcePortRange: '*'
          destinationPortRange: '22'
          sourceAddressPrefix: allowedSourceIpPrefix
          destinationAddressPrefix: '*'
        }
      }
      {
        name: 'AllowRDP'
        properties: {
          priority: 210
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourcePortRange: '*'
          destinationPortRange: '3389'
          sourceAddressPrefix: allowedSourceIpPrefix
          destinationAddressPrefix: '*'
        }
      }
    ]
  }
}

// Public IP for NAT Gateway (GitHub runners egress)
resource pipRunnerEgress 'Microsoft.Network/publicIPAddresses@2023-05-01' = {
  name: 'pip-github-runners-egress'
  location: location
  tags: tags
  sku: {
    name: 'Standard'
  }
  properties: {
    publicIPAllocationMethod: 'Static'
    publicIPAddressVersion: 'IPv4'
    idleTimeoutInMinutes: 10
  }
  zones: [
    '1'
    '2'
    '3'
  ]
}

// NAT Gateway for GitHub-hosted runners subnet
resource natGateway 'Microsoft.Network/natGateways@2023-05-01' = {
  name: 'ngw-github-runners'
  location: location
  tags: tags
  sku: {
    name: 'Standard'
  }
  properties: {
    publicIpAddresses: [
      {
        id: pipRunnerEgress.id
      }
    ]
    idleTimeoutInMinutes: 10
  }
}

// Route tables for proper traffic routing between subnets
resource udrVms 'Microsoft.Network/routeTables@2023-05-01' = {
  name: 'udr-vms'
  location: location
  tags: tags
  properties: {
    routes: [
      {
        name: 'route-to-app-service'
        properties: {
          addressPrefix: '10.0.5.0/24'
          nextHopType: 'VnetLocal'
        }
      }
    ]
  }
}

resource udrAppService 'Microsoft.Network/routeTables@2023-05-01' = {
  name: 'udr-app-service'
  location: location
  tags: tags
  properties: {
    routes: [
      {
        name: 'route-to-vms'
        properties: {
          addressPrefix: '10.0.1.0/24'
          nextHopType: 'VnetLocal'
        }
      }
    ]
  }
}

// Create Virtual Network (without inline subnets to avoid conflicts on redeployment)
resource vnet 'Microsoft.Network/virtualNetworks@2023-05-01' = {
  name: 'vnet-parking-hub'
  location: location
  tags: tags
  properties: {
    addressSpace: {
      addressPrefixes: [
        vnetAddressPrefix
      ]
    }
  }
}

// Create VM subnet as separate resource
resource vmSubnet 'Microsoft.Network/virtualNetworks/subnets@2023-05-01' = {
  parent: vnet
  name: 'snet-vms'
  properties: {
    addressPrefix: vmSubnetPrefix
    networkSecurityGroup: {
      id: nsgVms.id
    }
    routeTable: {
      id: udrVms.id
    }
  }
}

// Create Container Apps subnet as separate resource
resource containerSubnet 'Microsoft.Network/virtualNetworks/subnets@2023-05-01' = {
  parent: vnet
  name: 'snet-container-apps'
  dependsOn: [
    vmSubnet
  ]
  properties: {
    addressPrefix: containerSubnetPrefix
    delegations: [
      {
        name: 'Microsoft.App/environments'
        properties: {
          serviceName: 'Microsoft.App/environments'
        }
      }
    ]
  }
}

// Note: snet-github-runners subnet is created by github-runner-network.bicep module
// with proper GitHub.Network/networkSettings delegation. It is not created here to avoid conflicts.

// Add App Service subnet with Web Server delegation
resource appServiceSubnet 'Microsoft.Network/virtualNetworks/subnets@2023-05-01' = {
  parent: vnet
  name: 'snet-app-service'
  dependsOn: [
    containerSubnet
  ]
  properties: {
    addressPrefix: '10.0.5.0/24'
    networkSecurityGroup: {
      id: nsgAppService.id
    }
    routeTable: {
      id: udrAppService.id
    }
    delegations: [
      {
        name: 'Microsoft.Web/serverFarms'
        properties: {
          serviceName: 'Microsoft.Web/serverFarms'
        }
      }
    ]
  }
}

// Log Analytics Workspace
resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2022-10-01' = {
  name: 'law-parking-hub'
  location: location
  tags: tags
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
    features: {
      enableLogAccessUsingOnlyResourcePermissions: true
    }
  }
}

// Outputs
output vnetId string = vnet.id
output vnetName string = vnet.name
output vmSubnetId string = vmSubnet.id
output containerSubnetId string = containerSubnet.id
// Note: runnerSubnetId is not output here as the subnet is created by github-runner-network.bicep
output appServiceSubnetId string = appServiceSubnet.id
output logAnalyticsWorkspaceId string = logAnalytics.id
output logAnalyticsWorkspaceName string = logAnalytics.name
output logAnalyticsCustomerId string = logAnalytics.properties.customerId
output natGatewayId string = natGateway.id
output natGatewayPublicIp string = pipRunnerEgress.properties.ipAddress

// Paris API module - Ubuntu Server VM
@description('Location for all Paris API resources')
param location string

@description('VM subnet ID from hub VNet')
param vmSubnetId string

@description('Admin username for the VM')
param adminUsername string

@description('Admin password for the VM')
@secure()
param adminPassword string

@description('Create public IP for the VM')
param createPublicIp bool = true

@description('Deploy VM resources (set to false if VM already exists to avoid disk update conflicts)')
param deployVM bool = true

@description('Tags to apply to resources')
param tags object = {}

// Public IP (optional)
resource publicIp 'Microsoft.Network/publicIPAddresses@2023-05-01' = if (createPublicIp) {
  name: 'pip-paris-vm'
  location: location
  tags: tags
  sku: {
    name: 'Standard'
  }
  properties: {
    publicIPAllocationMethod: 'Static'
    dnsSettings: {
      domainNameLabel: 'paris-parking-${uniqueString(resourceGroup().id)}'
    }
  }
}

// Network Interface
resource nic 'Microsoft.Network/networkInterfaces@2023-05-01' = {
  name: 'nic-paris-vm'
  location: location
  tags: tags
  properties: {
    ipConfigurations: [
      {
        name: 'ipconfig1'
        properties: {
          subnet: {
            id: vmSubnetId
          }
          privateIPAllocationMethod: 'Dynamic'
          publicIPAddress: createPublicIp ? {
            id: publicIp.id
          } : null
        }
      }
    ]
  }
}

// Ubuntu Server VM
resource vm 'Microsoft.Compute/virtualMachines@2023-03-01' = if (deployVM) {
  name: 'vm-paris-api'
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    hardwareProfile: {
      vmSize: 'Standard_B2s' // Cost-optimized: 2 vCPUs, 4 GB RAM
    }
    storageProfile: {
      imageReference: {
        publisher: 'Canonical'
        offer: '0001-com-ubuntu-server-jammy'
        sku: '22_04-lts-gen2'
        version: 'latest'
      }
      osDisk: {
        name: 'osdisk-paris-vm'
        createOption: 'FromImage'
        managedDisk: {
          storageAccountType: 'StandardSSD_LRS' // Cost-optimized
        }
        diskSizeGB: 30
      }
    }
    osProfile: {
      computerName: 'paris-api'
      adminUsername: adminUsername
      adminPassword: adminPassword
      linuxConfiguration: {
        disablePasswordAuthentication: false
        provisionVMAgent: true
        patchSettings: {
          patchMode: 'AutomaticByPlatform'
        }
      }
    }
    networkProfile: {
      networkInterfaces: [
        {
          id: nic.id
        }
      ]
    }
    diagnosticsProfile: {
      bootDiagnostics: {
        enabled: true
      }
    }
  }
}

// VM Extension - Azure Monitor Agent
resource azureMonitorLinuxAgent 'Microsoft.Compute/virtualMachines/extensions@2023-03-01' = if (deployVM) {
  parent: vm
  name: 'AzureMonitorLinuxAgent'
  location: location
  properties: {
    publisher: 'Microsoft.Azure.Monitor'
    type: 'AzureMonitorLinuxAgent'
    typeHandlerVersion: '1.0'
    autoUpgradeMinorVersion: true
    enableAutomaticUpgrade: true
  }
}

// VM Extension - Custom Script to install Node.js and setup application
resource customScriptExtension 'Microsoft.Compute/virtualMachines/extensions@2023-03-01' = if (deployVM) {
  parent: vm
  name: 'CustomScriptExtension'
  location: location
  dependsOn: [
    azureMonitorLinuxAgent
  ]
  properties: {
    publisher: 'Microsoft.Azure.Extensions'
    type: 'CustomScript'
    typeHandlerVersion: '2.1'
    autoUpgradeMinorVersion: true
    settings: {
      script: base64('''#!/bin/bash
set -e

# Update package lists
apt-get update

# Install required packages
apt-get install -y ca-certificates curl gnupg rsyslog

# Setup NodeSource repository for Node.js 18.x
mkdir -p /etc/apt/keyrings
curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor --batch --yes -o /etc/apt/keyrings/nodesource.gpg 2>/dev/null || true
echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_18.x nodistro main" | tee /etc/apt/sources.list.d/nodesource.list

# Install Node.js
apt-get update
apt-get install -y nodejs

# Verify installation
node --version
npm --version
''')
    }
  }
}

// Outputs - VM outputs are only valid when deployVM=true
output vmName string = deployVM ? vm!.name : ''
output vmId string = deployVM ? vm!.id : ''
output vmPrincipalId string = deployVM ? vm!.identity.principalId : ''
output privateIpAddress string = nic.properties.ipConfigurations[0].properties.privateIPAddress
output publicIpAddress string = (deployVM && createPublicIp) ? publicIp!.properties.ipAddress : ''
output fqdn string = (deployVM && createPublicIp) ? publicIp!.properties.dnsSettings.fqdn : ''
output apiUrl string = (deployVM && createPublicIp) ? 'http://${publicIp!.properties.dnsSettings.fqdn}:3003' : 'http://${nic.properties.ipConfigurations[0].properties.privateIPAddress}:3003'

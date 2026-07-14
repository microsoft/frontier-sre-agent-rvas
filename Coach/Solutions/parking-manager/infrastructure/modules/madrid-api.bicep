// Madrid API module - Windows Server VM
@description('Location for all Madrid API resources')
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
  name: 'pip-madrid-vm'
  location: location
  tags: tags
  sku: {
    name: 'Standard'
  }
  properties: {
    publicIPAllocationMethod: 'Static'
    dnsSettings: {
      domainNameLabel: 'madrid-parking-${uniqueString(resourceGroup().id)}'
    }
  }
}

// Network Interface
resource nic 'Microsoft.Network/networkInterfaces@2023-05-01' = {
  name: 'nic-madrid-vm'
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

// Windows Server VM
resource vm 'Microsoft.Compute/virtualMachines@2023-03-01' = if (deployVM) {
  name: 'vm-madrid-api'
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
        publisher: 'MicrosoftWindowsServer'
        offer: 'WindowsServer'
        sku: '2022-datacenter-azure-edition-smalldisk'
        version: 'latest'
      }
      osDisk: {
        name: 'osdisk-madrid-vm'
        createOption: 'FromImage'
        managedDisk: {
          storageAccountType: 'StandardSSD_LRS' // Cost-optimized
        }
        diskSizeGB: 64
      }
    }
    osProfile: {
      computerName: 'madrid-api'
      adminUsername: adminUsername
      adminPassword: adminPassword
      windowsConfiguration: {
        enableAutomaticUpdates: true
        provisionVMAgent: true
        patchSettings: {
          patchMode: 'AutomaticByOS'
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
resource azureMonitorWindowsAgent 'Microsoft.Compute/virtualMachines/extensions@2023-03-01' = if (deployVM) {
  parent: vm
  name: 'AzureMonitorWindowsAgent'
  location: location
  properties: {
    publisher: 'Microsoft.Azure.Monitor'
    type: 'AzureMonitorWindowsAgent'
    typeHandlerVersion: '1.0'
    autoUpgradeMinorVersion: true
    enableAutomaticUpgrade: true
  }
}

// VM Extension - Custom Script to install Node.js and setup application
// NOTE: Node.js is installed during GitHub Actions deployment workflow (deploy-madrid-api.yml)
// This extension is skipped to avoid network/internet dependency during Bicep deployment
resource customScriptExtension 'Microsoft.Compute/virtualMachines/extensions@2023-03-01' = if (deployVM && false) {
  parent: vm
  name: 'CustomScriptExtension'
  location: location
  dependsOn: [
    azureMonitorWindowsAgent
  ]
  properties: {
    publisher: 'Microsoft.Compute'
    type: 'CustomScriptExtension'
    typeHandlerVersion: '1.10'
    autoUpgradeMinorVersion: true
    settings: {
      commandToExecute: 'echo VM provisioned - Node.js will be installed during GitHub Actions deployment'
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
output apiUrl string = (deployVM && createPublicIp) ? 'http://${publicIp!.properties.dnsSettings.fqdn}:3002' : 'http://${nic.properties.ipConfigurations[0].properties.privateIPAddress}:3002'

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

var madridBootstrapScript = '''
$ErrorActionPreference = 'Stop'

$appDir = 'C:\Apps\madrid-parking-api'
$sharedDir = 'C:\Apps\shared'
$envFile = Join-Path $appDir '.env'
$pfxPath = Join-Path $appDir 'madrid.pfx'
$runnerPath = Join-Path $appDir 'run-madrid-api.ps1'
$serviceName = 'MadridParkingAPI'
$serviceDisplayName = 'Madrid Parking API'
$nodeVersion = '18.20.4'
$nodeMsi = "node-v$nodeVersion-x64.msi"
$nodeUrl = "https://nodejs.org/dist/v$nodeVersion/$nodeMsi"
$nodeInstaller = Join-Path $env:TEMP $nodeMsi
$pfxPassphrase = 'ChangeMe123!'
$nodeExe = 'C:\Program Files\nodejs\node.exe'

New-Item -ItemType Directory -Force -Path $appDir | Out-Null
New-Item -ItemType Directory -Force -Path $sharedDir | Out-Null

if (-not (Test-Path $nodeExe)) {
  Invoke-WebRequest -Uri $nodeUrl -OutFile $nodeInstaller -UseBasicParsing
  Start-Process msiexec.exe -ArgumentList "/i `"$nodeInstaller`" /qn /norestart" -Wait
}

if (-not (Test-Path $pfxPath)) {
  $cert = New-SelfSignedCertificate -DnsName 'madrid-api' -CertStoreLocation 'cert:\LocalMachine\My' -FriendlyName 'Madrid Parking API'
  $securePassphrase = ConvertTo-SecureString $pfxPassphrase -AsPlainText -Force
  Export-PfxCertificate -Cert "cert:\LocalMachine\My\$($cert.Thumbprint)" -FilePath $pfxPath -Password $securePassphrase | Out-Null
}

@"
EVENT_LOG_SOURCE=MadridParkingAPI
EVENT_LOG_NAME=Application
PORT=3002
NODE_ENV=production
PFX_PATH=$pfxPath
PFX_PASSPHRASE=$pfxPassphrase
PARKING_NAME=Madrid Centro Parking
PARKING_CITY=Madrid
PARKING_LOCATION=Plaza Mayor, Madrid
"@ | Set-Content -Path $envFile -Encoding UTF8

@"
$appDir = 'C:\Apps\madrid-parking-api'
$nodeExe = 'C:\Program Files\nodejs\node.exe'

if (-not (Test-Path (Join-Path $appDir 'server.js'))) {
  Start-Sleep -Seconds 10
  exit 1
}

Set-Location $appDir
& $nodeExe server.js
"@ | Set-Content -Path $runnerPath -Encoding UTF8

if (-not (Get-Service -Name $serviceName -ErrorAction SilentlyContinue)) {
  $binPath = "C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$runnerPath`""
  sc.exe create $serviceName binPath= $binPath start= auto DisplayName= $serviceDisplayName | Out-Null
  sc.exe failure $serviceName reset= 60 actions= restart/5000 | Out-Null
}

New-NetFirewallRule -DisplayName 'Madrid Parking API 3002' -Direction Inbound -LocalPort 3002 -Protocol TCP -Action Allow -ErrorAction SilentlyContinue | Out-Null
'''
var madridBootstrapCommandTemplate = '''powershell -ExecutionPolicy Bypass -Command "[System.IO.File]::WriteAllText('C:\Windows\Temp\bootstrap-madrid.ps1', [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String('__BOOTSTRAP_BASE64__'))); & 'C:\Windows\Temp\bootstrap-madrid.ps1'"'''
var madridBootstrapCommand = replace(madridBootstrapCommandTemplate, '__BOOTSTRAP_BASE64__', base64(madridBootstrapScript))

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
// Bootstrap the VM so routine deployments only need to copy app code and restart the service.
resource customScriptExtension 'Microsoft.Compute/virtualMachines/extensions@2023-03-01' = if (deployVM) {
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
      commandToExecute: madridBootstrapCommand
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

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

var parisApiDirectory = '/opt/paris-parking-api'
var parisCloudInitTemplate = '''#cloud-config
package_update: true
packages:
  - ca-certificates
  - curl
  - gnupg
  - rsyslog
  - ufw
  - openssl

write_files:
  - path: /usr/local/bin/bootstrap-paris-api.sh
    permissions: '0755'
    content: |
      #!/usr/bin/env bash
      set -euo pipefail

      API_DIR="__PARIS_API_DIRECTORY__"
      SERVICE_NAME="paris-parking-api"

      mkdir -p /etc/apt/keyrings
      curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor --batch --yes -o /etc/apt/keyrings/nodesource.gpg
      echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_18.x nodistro main" > /etc/apt/sources.list.d/nodesource.list

      apt-get update
      apt-get install -y nodejs

      mkdir -p "$API_DIR" /opt/shared

      if [[ ! -f "$API_DIR/paris.key" || ! -f "$API_DIR/paris.crt" ]]; then
        openssl req -new -x509 \
          -keyout "$API_DIR/paris.key" \
          -out "$API_DIR/paris.crt" \
          -days 365 \
          -nodes \
          -subj "/C=FR/ST=Paris/L=Paris/O=Parking/OU=API/CN=paris-api"
      fi

      cat > "$API_DIR/.env" <<EOF
      PORT=3003
      NODE_ENV=production
      CERT_PATH=$API_DIR/paris.crt
      KEY_PATH=$API_DIR/paris.key
      PARKING_NAME=Paris Centre Parking
      PARKING_CITY=Paris
      PARKING_LOCATION=Champs-Elysees, Paris
      SYSLOG_FACILITY=local0
      SYSLOG_TAG=ParisParkingAPI
      EOF

      chmod 600 "$API_DIR/paris.key"
      chmod 644 "$API_DIR/paris.crt"
      chown -R __ADMIN_USERNAME__:__ADMIN_USERNAME__ "$API_DIR" /opt/shared

      cat > /etc/systemd/system/${'$'}{SERVICE_NAME}.service <<EOF
      [Unit]
      Description=Paris Parking API Service
      After=network.target
      ConditionPathExists=$API_DIR/server.js

      [Service]
      Type=simple
        User=__ADMIN_USERNAME__
      WorkingDirectory=$API_DIR
      ExecStart=/usr/bin/node server.js
      Restart=on-failure
      RestartSec=10
      StandardOutput=journal
      StandardError=journal
      SyslogIdentifier=paris-parking-api
      EnvironmentFile=$API_DIR/.env

      [Install]
      WantedBy=multi-user.target
      EOF

      systemctl daemon-reload
      systemctl enable "$SERVICE_NAME"
      ufw allow 3003/tcp || true

  - path: /etc/motd.d/parking-manager
    permissions: '0644'
    content: |
      Paris Parking API bootstrap is handled by cloud-init.
      Deploy application code with workflows/deploy-vm-apps.yml.

runcmd:
  - /usr/local/bin/bootstrap-paris-api.sh
'''
var parisCloudInit = replace(replace(parisCloudInitTemplate, '__PARIS_API_DIRECTORY__', parisApiDirectory), '__ADMIN_USERNAME__', adminUsername)

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
      customData: base64(parisCloudInit)
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

// Outputs - VM outputs are only valid when deployVM=true
output vmName string = deployVM ? vm!.name : ''
output vmId string = deployVM ? vm!.id : ''
output vmPrincipalId string = deployVM ? vm!.identity.principalId : ''
output privateIpAddress string = nic.properties.ipConfigurations[0].properties.privateIPAddress
output publicIpAddress string = (deployVM && createPublicIp) ? publicIp!.properties.ipAddress : ''
output fqdn string = (deployVM && createPublicIp) ? publicIp!.properties.dnsSettings.fqdn : ''
output apiUrl string = (deployVM && createPublicIp) ? 'http://${publicIp!.properties.dnsSettings.fqdn}:3003' : 'http://${nic.properties.ipConfigurations[0].properties.privateIPAddress}:3003'

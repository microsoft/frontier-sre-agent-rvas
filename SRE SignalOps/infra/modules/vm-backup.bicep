param environmentName string
param location string
@minLength(6)
param suffix string
param tags object
param backupVmResourceGroup string
param backupVmName string
param logAnalyticsWorkspaceId string

var token = take(toLower(replace(environmentName, '-', '')), 12)
var backupVmId = resourceId(subscription().subscriptionId, backupVmResourceGroup, 'Microsoft.Compute/virtualMachines', backupVmName)

resource backupVault 'Microsoft.RecoveryServices/vaults@2024-04-01' = {
  name: 'rsv-${token}-mission09-${suffix}'
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  sku: {
    name: 'Standard'
  }
  properties: {
    monitoringSettings: {
      azureMonitorAlertSettings: {
        alertsForAllJobFailures: 'Enabled'
      }
    }
    publicNetworkAccess: 'Enabled'
    redundancySettings: {
      crossRegionRestore: 'Disabled'
      standardTierStorageRedundancy: 'LocallyRedundant'
    }
    securitySettings: {
      immutabilitySettings: {
        state: 'Disabled'
      }
      softDeleteSettings: {
        enhancedSecurityState: 'Enabled'
        softDeleteRetentionPeriodInDays: 14
        softDeleteState: 'AlwaysON'
      }
    }
  }
}

resource backupPolicy 'Microsoft.RecoveryServices/vaults/backupPolicies@2024-04-01' = {
  parent: backupVault
  name: 'mission09-vm-daily'
  properties: {
    backupManagementType: 'AzureIaasVM'
    instantRpRetentionRangeInDays: 2
    timeZone: 'UTC'
    schedulePolicy: {
      schedulePolicyType: 'SimpleSchedulePolicy'
      scheduleRunFrequency: 'Daily'
      scheduleRunTimes: [
        '2026-09-01T02:00:00Z'
      ]
    }
    retentionPolicy: {
      retentionPolicyType: 'LongTermRetentionPolicy'
      dailySchedule: {
        retentionTimes: [
          '2026-09-01T02:00:00Z'
        ]
        retentionDuration: {
          count: 7
          durationType: 'Days'
        }
      }
    }
  }
}

resource protectedVm 'Microsoft.RecoveryServices/vaults/backupFabrics/protectionContainers/protectedItems@2024-04-01' = {
  name: '${backupVault.name}/Azure/IaasVMContainer;iaasvmcontainerv2;${backupVmResourceGroup};${backupVmName}/VM;iaasvmcontainerv2;${backupVmResourceGroup};${backupVmName}'
  properties: {
    protectedItemType: 'Microsoft.Compute/virtualMachines'
    sourceResourceId: backupVmId
    policyId: backupPolicy.id
  }
}

resource backupDiagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  scope: backupVault
  name: 'send-backup-data-to-log-analytics'
  properties: {
    workspaceId: logAnalyticsWorkspaceId
    logs: [
      {
        category: 'AzureBackupReport'
        enabled: true
      }
    ]
  }
}

output backupVaultId string = backupVault.id
output backupVaultName string = backupVault.name
output protectedVmId string = protectedVm.id
output backupVmId string = backupVmId
output backupVmName string = backupVmName

@minLength(1)
@maxLength(20)
param environmentName string

param location string = resourceGroup().location
@minLength(1)
param teamsGroupId string
@minLength(1)
param teamsChannelId string
@minLength(1)
param backupVmResourceGroup string
@allowed(['vm-parking-madrid'])
param backupVmName string
@minLength(4)
param logAnalyticsWorkspaceName string
@minLength(1)
param applicationInsightsName string

var suffix = take(uniqueString(subscription().id, environmentName), 6)
var tags = {
  workload: 'azure-sre-agent'
  'managed-by': 'bicep'
  environment: environmentName
  mission: '09'
  solution: 'sre-signalops'
}

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' existing = {
  name: logAnalyticsWorkspaceName
}

resource applicationInsights 'Microsoft.Insights/components@2020-02-02' existing = {
  name: applicationInsightsName
}

module vmBackup 'modules/vm-backup.bicep' = {
  name: 'signalops-mission09-vm-backup'
  params: {
    environmentName: environmentName
    location: location
    suffix: suffix
    tags: tags
    backupVmResourceGroup: backupVmResourceGroup
    backupVmName: backupVmName
    logAnalyticsWorkspaceId: logAnalytics.id
  }
}

module backupApprovalGate 'modules/backup-approval-gate.bicep' = {
  name: 'signalops-mission09-backup-approval-gate'
  params: {
    environmentName: environmentName
    location: location
    suffix: suffix
    tags: tags
    backupVaultId: vmBackup.outputs.backupVaultId
    protectedItemId: vmBackup.outputs.protectedVmId
    logAnalyticsWorkspaceId: logAnalytics.id
    applicationInsightsConnectionString: applicationInsights.properties.ConnectionString
    teamsGroupId: teamsGroupId
    teamsChannelId: teamsChannelId
  }
}

output BACKUP_APPROVAL_FUNCTION_NAME string = backupApprovalGate.outputs.functionAppName
output BACKUP_APPROVAL_FUNCTION_URL string = backupApprovalGate.outputs.functionAppUrl
output BACKUP_APPROVAL_WORKFLOW_NAME string = backupApprovalGate.outputs.approvalWorkflowName
output BACKUP_TEAMS_CONNECTION_NAME string = backupApprovalGate.outputs.teamsConnectionName
output BACKUP_VAULT_NAME string = vmBackup.outputs.backupVaultName
output BACKUP_PROTECTED_ITEM_ID string = vmBackup.outputs.protectedVmId
output BACKUP_VM_ID string = vmBackup.outputs.backupVmId
output BACKUP_VM_NAME string = vmBackup.outputs.backupVmName

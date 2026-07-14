targetScope = 'resourceGroup'

// Role assignment module for VMs to access deployment storage account
@description('Principal ID of the managed identity')
param principalId string

@description('Storage account name to grant access to')
param storageAccountName string

@description('Role to assign (Storage Blob Data Reader or Storage Blob Data Contributor)')
param roleDefinitionId string = '2a2b9908-6ea1-4ae2-8e65-a410df84e7d1' // Storage Blob Data Reader

// Reference existing storage account
resource storageAccount 'Microsoft.Storage/storageAccounts@2023-01-01' existing = {
  name: storageAccountName
}

// Assign role at storage account scope
resource roleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: storageAccount
  name: guid(storageAccount.id, principalId, roleDefinitionId)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleDefinitionId)
    principalId: principalId
    principalType: 'ServicePrincipal'
  }
}

// Outputs
output roleAssignmentId string = roleAssignment.id

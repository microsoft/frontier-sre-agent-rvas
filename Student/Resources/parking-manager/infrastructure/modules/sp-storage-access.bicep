// Role assignment module for service principal to access deployment storage
@description('Principal ID of the service principal (e.g., GitHub Actions SP)')
param principalId string

@description('Storage account ID')
param storageAccountId string

@description('Subscription ID')
param subscriptionId string = subscription().subscriptionId

// Assign Storage Blob Data Contributor role to SP on storage account
resource roleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccountId, principalId, 'ba92f5b4-2d11-453d-a403-e96b0029c9fe')
  scope: resourceGroup()
  properties: {
    roleDefinitionId: '/subscriptions/${subscriptionId}/providers/Microsoft.Authorization/roleDefinitions/ba92f5b4-2d11-453d-a403-e96b0029c9fe'
    principalId: principalId
    principalType: 'ServicePrincipal'
  }
}

// Outputs
output roleAssignmentId string = roleAssignment.id

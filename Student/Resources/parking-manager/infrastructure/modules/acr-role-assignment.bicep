// ACR Role Assignment Module
// Assigns AcrPull role to a managed identity on an ACR

@description('Principal ID of the managed identity')
param principalId string

@description('Name of the Azure Container Registry')
param acrName string

// Reference existing ACR
resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' existing = {
  name: acrName
}

// AcrPull role assignment
resource acrPullRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acr.id, 'AcrPull')
  scope: acr
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d') // AcrPull
    principalId: principalId
    principalType: 'ServicePrincipal'
  }
}

output roleAssignmentId string = acrPullRole.id

param environmentName string
param identityPrincipalId string

var readerRoleId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'acdd72a7-3385-48ef-bd42-f606fba81ae7')
var logAnalyticsReaderRoleId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '73c42c96-874c-492b-b04d-ab87d138a893')
var monitoringReaderRoleId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '43d0d8ad-25c7-4714-9337-8ba259a9fe05')
var contributorRoleId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'b24988ac-6180-42a0-ab88-20f7382dd24c')

resource reader 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(resourceGroup().id, environmentName, readerRoleId)
  properties: { roleDefinitionId: readerRoleId, principalId: identityPrincipalId, principalType: 'ServicePrincipal' }
}

resource logAnalyticsReader 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(resourceGroup().id, environmentName, logAnalyticsReaderRoleId)
  properties: { roleDefinitionId: logAnalyticsReaderRoleId, principalId: identityPrincipalId, principalType: 'ServicePrincipal' }
}

resource monitoringReader 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(resourceGroup().id, environmentName, monitoringReaderRoleId)
  properties: { roleDefinitionId: monitoringReaderRoleId, principalId: identityPrincipalId, principalType: 'ServicePrincipal' }
}

resource contributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(resourceGroup().id, environmentName, contributorRoleId)
  properties: { roleDefinitionId: contributorRoleId, principalId: identityPrincipalId, principalType: 'ServicePrincipal' }
}

@description('Name of the target virtual machine in this resource group')
param vmName string

@description('Data Collection Rule resource ID')
param dataCollectionRuleId string

@description('Data Collection Endpoint resource ID')
param dataCollectionEndpointId string

@description('Association resource name')
param associationName string

@description('Association description')
param associationDescription string = ''

resource vm 'Microsoft.Compute/virtualMachines@2023-03-01' existing = {
  name: vmName
}

resource dcrAssociation 'Microsoft.Insights/dataCollectionRuleAssociations@2022-06-01' = {
  scope: vm
  name: associationName
  properties: {
    dataCollectionRuleId: dataCollectionRuleId
    dataCollectionEndpointId: dataCollectionEndpointId
    description: associationDescription
  }
}

output dcrAssociationId string = dcrAssociation.id

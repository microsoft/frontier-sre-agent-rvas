// Custom table in Log Analytics for VM health status events.
// Deployed into the hub resource group alongside the Log Analytics workspace.
@description('Log Analytics workspace name')
param workspaceName string

resource workspace 'Microsoft.OperationalInsights/workspaces@2022-10-01' existing = {
  name: workspaceName
}

resource customTable 'Microsoft.OperationalInsights/workspaces/tables@2022-10-01' = {
  parent: workspace
  name: 'VMHealthStatus_CL'
  properties: {
    schema: {
      name: 'VMHealthStatus_CL'
      columns: [
        { name: 'TimeGenerated', type: 'datetime' }
        { name: 'vmName', type: 'string' }
        { name: 'city', type: 'string' }
        { name: 'healthState', type: 'string' }
        { name: 'previousState', type: 'string' }
        { name: 'severity', type: 'string' }
        { name: 'source', type: 'string' }
        { name: 'message', type: 'string' }
        { name: 'resourceGroup', type: 'string' }
        { name: 'subscriptionId', type: 'string' }
        { name: 'resourceType', type: 'string' }
      ]
    }
    retentionInDays: 30
  }
}

output tableName string = customTable.name

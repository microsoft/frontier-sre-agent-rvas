@description('Azure region for the scheduled query rules.')
param location string

@description('Fully qualified ARM resource ID of the Log Analytics workspace.')
param logAnalyticsWorkspaceId string

@description('Action Group resource ID to notify when alerts fire. Leave empty to create rules without action groups.')
param actionGroupResourceId string = ''

@description('Enable or disable VM health alerts.')
param enabled bool = true

@description('How often the alert query runs.')
param evaluationFrequency string = 'PT5M'

@description('Lookback window used by alert queries.')
param windowSize string = 'PT5M'

// Alert: any VM reported as Unhealthy
resource vmUnhealthyAlert 'Microsoft.Insights/scheduledQueryRules@2023-12-01' = {
  name: 'vm-health-unhealthy'
  location: location
  properties: {
    displayName: 'VM Unhealthy Alert'
    description: 'Fires when a parking VM is reported as unhealthy in the VMHealthStatus_CL custom table.'
    severity: 1
    enabled: enabled
    scopes: [
      logAnalyticsWorkspaceId
    ]
    evaluationFrequency: evaluationFrequency
    windowSize: windowSize
    autoMitigate: true
    criteria: {
      allOf: [
        {
          query: '''
VMHealthStatus_CL
| where healthState == "Unhealthy"
| summarize unhealthyCount = count() by vmName, city, bin(TimeGenerated, 5m)
'''
          timeAggregation: 'Count'
          operator: 'GreaterThan'
          threshold: 0
          failingPeriods: {
            numberOfEvaluationPeriods: 1
            minFailingPeriodsToAlert: 1
          }
          dimensions: [
            {
              name: 'vmName'
              operator: 'Include'
              values: [ '*' ]
            }
            {
              name: 'city'
              operator: 'Include'
              values: [ '*' ]
            }
          ]
        }
      ]
    }
    actions: empty(actionGroupResourceId) ? {
      actionGroups: []
    } : {
      actionGroups: [
        actionGroupResourceId
      ]
    }
  }
}

// Alert: VM recovered (informational)
resource vmRecoveredAlert 'Microsoft.Insights/scheduledQueryRules@2023-12-01' = {
  name: 'vm-health-recovered'
  location: location
  properties: {
    displayName: 'VM Recovered Alert'
    description: 'Fires when a previously unhealthy parking VM is reported as healthy again.'
    severity: 3
    enabled: enabled
    scopes: [
      logAnalyticsWorkspaceId
    ]
    evaluationFrequency: evaluationFrequency
    windowSize: windowSize
    autoMitigate: false
    criteria: {
      allOf: [
        {
          query: '''
VMHealthStatus_CL
| where healthState == "Healthy" and previousState == "Unhealthy"
| summarize recoveryCount = count() by vmName, city, bin(TimeGenerated, 5m)
'''
          timeAggregation: 'Count'
          operator: 'GreaterThan'
          threshold: 0
          failingPeriods: {
            numberOfEvaluationPeriods: 1
            minFailingPeriodsToAlert: 1
          }
          dimensions: [
            {
              name: 'vmName'
              operator: 'Include'
              values: [ '*' ]
            }
            {
              name: 'city'
              operator: 'Include'
              values: [ '*' ]
            }
          ]
        }
      ]
    }
    actions: empty(actionGroupResourceId) ? {
      actionGroups: []
    } : {
      actionGroups: [
        actionGroupResourceId
      ]
    }
  }
}

output unhealthyAlertName string = vmUnhealthyAlert.name
output recoveredAlertName string = vmRecoveredAlert.name

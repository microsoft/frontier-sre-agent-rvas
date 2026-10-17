param environmentName string
param location string
@minLength(6)
param suffix string
param tags object
param backupVaultId string
param protectedItemId string
param logAnalyticsWorkspaceId string
param applicationInsightsConnectionString string
param teamsGroupId string
param teamsChannelId string

var token = take(toLower(replace(environmentName, '-', '')), 12)
var storageName = take('st${token}approval${suffix}', 24)
var functionName = 'func-${token}-backup-approval'
var deploymentContainerName = 'app-packages'
var teamsConnectionName = 'teams-${token}-backup-approval'
var blobDataOwnerRoleId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'b7e6dc6d-f1e8-4753-8033-0f276bb0955b')
var queueDataContributorRoleId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '974c5e8b-45b9-4653-ba55-5f855dd0fb88')
var tableDataContributorRoleId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '0a9a7e1f-b9d0-4cc4-a60d-0319b160aaa3')
var backupOperatorRoleId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '00c29273-979b-4161-815c-10b084fb9324')

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'uai-${token}-backup-approval'
  location: location
  tags: tags
}

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageName
  location: location
  tags: tags
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    allowBlobPublicAccess: false
    allowCrossTenantReplication: false
    allowSharedKeyAccess: false
    defaultToOAuthAuthentication: true
    minimumTlsVersion: 'TLS1_2'
    publicNetworkAccess: 'Enabled'
    supportsHttpsTrafficOnly: true
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: storage
  name: 'default'
  properties: {
    deleteRetentionPolicy: {
      enabled: true
      days: 7
    }
  }
}

resource deploymentContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: deploymentContainerName
  properties: {
    publicAccess: 'None'
  }
}

resource blobDataOwner 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: storage
  name: guid(storage.id, identity.id, blobDataOwnerRoleId)
  properties: {
    roleDefinitionId: blobDataOwnerRoleId
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource queueDataContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: storage
  name: guid(storage.id, identity.id, queueDataContributorRoleId)
  properties: {
    roleDefinitionId: queueDataContributorRoleId
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource tableDataContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: storage
  name: guid(storage.id, identity.id, tableDataContributorRoleId)
  properties: {
    roleDefinitionId: tableDataContributorRoleId
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource backupVault 'Microsoft.RecoveryServices/vaults@2024-04-01' existing = {
  name: last(split(backupVaultId, '/'))
}

resource backupOperator 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: backupVault
  name: guid(backupVault.id, identity.id, backupOperatorRoleId)
  properties: {
    roleDefinitionId: backupOperatorRoleId
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource plan 'Microsoft.Web/serverfarms@2024-04-01' = {
  name: 'plan-${token}-backup-approval'
  location: location
  tags: tags
  kind: 'functionapp'
  sku: {
    name: 'FC1'
    tier: 'FlexConsumption'
  }
  properties: {
    reserved: true
  }
}

resource functionApp 'Microsoft.Web/sites@2024-04-01' = {
  name: functionName
  location: location
  tags: union(tags, { 'azd-service-name': 'backup-approval-gate' })
  kind: 'functionapp,linux'
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${identity.id}': {}
    }
  }
  properties: {
    serverFarmId: plan.id
    httpsOnly: true
    publicNetworkAccess: 'Enabled'
    functionAppConfig: {
      deployment: {
        storage: {
          type: 'blobContainer'
          value: '${storage.properties.primaryEndpoints.blob}${deploymentContainer.name}'
          authentication: {
            type: 'UserAssignedIdentity'
            userAssignedIdentityResourceId: identity.id
          }
        }
      }
      runtime: {
        name: 'dotnet-isolated'
        version: '10.0'
      }
      scaleAndConcurrency: {
        instanceMemoryMB: 2048
        maximumInstanceCount: 10
      }
    }
    siteConfig: {
      minTlsVersion: '1.2'
      ftpsState: 'Disabled'
    }
  }
  dependsOn: [
    blobDataOwner
    queueDataContributor
    tableDataContributor
    backupOperator
  ]
}

resource teamsConnection 'Microsoft.Web/connections@2016-06-01' = {
  name: teamsConnectionName
  location: location
  tags: tags
  properties: {
    displayName: 'SignalOps backup approvals'
    api: {
      id: subscriptionResourceId('Microsoft.Web/locations/managedApis', location, 'teams')
    }
  }
}

var approvalCard = {
  type: 'AdaptiveCard'
  version: '1.4'
  body: [
    {
      type: 'TextBlock'
      text: '@{triggerBody().title}'
      weight: 'Bolder'
      size: 'Medium'
      wrap: true
    }
    {
      type: 'TextBlock'
      text: '@{triggerBody().summary}'
      wrap: true
    }
    {
      type: 'FactSet'
      facts: [
        { title: 'Incident', value: '@{triggerBody().incidentId}' }
        { title: 'Created', value: '@{triggerBody().incidentCreatedAt}' }
        { title: 'Action', value: '@{triggerBody().requestedAction}' }
      ]
    }
  ]
  actions: [
    {
      type: 'Action.Submit'
      title: 'Approve retry'
      data: { submitActionId: 'approve' }
    }
    {
      type: 'Action.Submit'
      title: 'Deny'
      data: { submitActionId: 'deny' }
    }
  ]
}

resource approvalWorkflow 'Microsoft.Logic/workflows@2019-05-01' = {
  name: 'logic-${token}-backup-approval'
  location: location
  tags: tags
  properties: {
    state: 'Enabled'
    parameters: {
      '$connections': {
        value: {
          teams: {
            connectionId: teamsConnection.id
            connectionName: teamsConnection.name
            id: subscriptionResourceId('Microsoft.Web/locations/managedApis', location, 'teams')
          }
        }
      }
    }
    definition: {
      '$schema': 'https://schema.management.azure.com/providers/Microsoft.Logic/schemas/2016-06-01/workflowdefinition.json#'
      contentVersion: '1.0.0.0'
      parameters: {
        '$connections': {
          type: 'Object'
        }
      }
      triggers: {
        When_a_HTTP_request_is_received: {
          type: 'Request'
          kind: 'Http'
          inputs: {
            schema: {
              type: 'object'
              required: [
                'incidentId'
                'incidentCreatedAt'
                'requestedAction'
                'title'
                'summary'
              ]
              properties: {
                incidentId: { type: 'string' }
                incidentCreatedAt: { type: 'string' }
                requestedAction: { type: 'string' }
                title: { type: 'string' }
                summary: { type: 'string' }
              }
            }
          }
        }
      }
      actions: {
        Accept_request: {
          type: 'Response'
          inputs: {
            statusCode: 202
          }
          runAfter: {}
        }
        Post_card_and_wait_for_response: {
          type: 'ApiConnectionWebhook'
          inputs: {
            host: {
              connection: {
                name: '@parameters(\'$connections\')[\'teams\'][\'connectionId\']'
              }
            }
            body: {
              messageBody: string(approvalCard)
              recipient: {
                groupId: teamsGroupId
                channelId: teamsChannelId
              }
              updateMessage: 'The backup retry decision was recorded.'
            }
            path: '/v1.0/teams/conversation/gatherinput/poster/Flow bot/location/Channel'
          }
          runAfter: {
            Accept_request: [ 'Succeeded' ]
          }
        }
        Record_authenticated_decision: {
          type: 'Http'
          inputs: {
            method: 'POST'
            uri: 'https://${functionApp.properties.defaultHostName}/api/approvals/@{encodeURIComponent(triggerBody().incidentId)}/decision?code=${listKeys('${functionApp.id}/host/default', '2024-04-01').functionKeys.default}'
            headers: {
              'Content-Type': 'application/json'
            }
            body: {
              decision: '@{if(equals(body(\'Post_card_and_wait_for_response\')?[\'submitActionId\'], \'approve\'), \'Approved\', \'Denied\')}'
              responderId: '@{body(\'Post_card_and_wait_for_response\')?[\'responder\']?[\'objectId\']}'
              responderDisplayName: '@{body(\'Post_card_and_wait_for_response\')?[\'responder\']?[\'displayName\']}'
            }
          }
          runAfter: {
            Post_card_and_wait_for_response: [ 'Succeeded' ]
          }
        }
      }
      outputs: {}
    }
  }
}

resource functionSettings 'Microsoft.Web/sites/config@2024-04-01' = {
  parent: functionApp
  name: 'appsettings'
  properties: {
    APPLICATIONINSIGHTS_CONNECTION_STRING: applicationInsightsConnectionString
    APPROVAL_WORKFLOW_URL: listCallbackUrl('${approvalWorkflow.id}/triggers/When_a_HTTP_request_is_received', '2016-06-01').value
    BACKUP_PROTECTED_ITEM_ID: protectedItemId
    AzureWebJobsStorage__accountName: storage.name
    AzureWebJobsStorage__blobServiceUri: storage.properties.primaryEndpoints.blob
    AzureWebJobsStorage__queueServiceUri: storage.properties.primaryEndpoints.queue
    AzureWebJobsStorage__tableServiceUri: storage.properties.primaryEndpoints.table
    AzureWebJobsStorage__credential: 'managedidentity'
    AzureWebJobsStorage__clientId: identity.properties.clientId
    FUNCTIONS_EXTENSION_VERSION: '~4'
    FUNCTIONS_WORKER_RUNTIME: 'dotnet-isolated'
  }
}

resource functionDiagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  scope: functionApp
  name: 'send-function-logs-to-log-analytics'
  properties: {
    workspaceId: logAnalyticsWorkspaceId
    logs: [
      {
        category: 'FunctionAppLogs'
        enabled: true
      }
    ]
    metrics: [
      {
        category: 'AllMetrics'
        enabled: true
      }
    ]
  }
}

output functionAppName string = functionApp.name
output functionAppUrl string = 'https://${functionApp.properties.defaultHostName}'
output identityPrincipalId string = identity.properties.principalId
output storageAccountName string = storage.name
output approvalWorkflowName string = approvalWorkflow.name
output teamsConnectionName string = teamsConnection.name

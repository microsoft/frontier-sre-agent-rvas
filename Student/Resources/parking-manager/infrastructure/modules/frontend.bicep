// Frontend module - React App on Azure App Service
@description('Location for all frontend resources')
param location string

@description('Log Analytics Workspace ID for Application Insights')
param logAnalyticsWorkspaceId string

@description('Environment URLs for the APIs')
param lisbonApiUrl string = ''
param madridApiUrl string = ''
param parisApiUrl string = ''
param berlinApiUrl string = ''
param chaosControlUrl string = ''
param vmHealthControlUrl string = ''

@description('Tags to apply to resources')
param tags object = {}

// App Service Plan (Linux, B1 tier for cost optimization)
resource appServicePlan 'Microsoft.Web/serverfarms@2023-01-01' = {
  name: 'asp-parking-frontend'
  location: location
  tags: tags
  sku: {
    name: 'B1'
    tier: 'Basic'
    size: 'B1'
    family: 'B'
    capacity: 1
  }
  kind: 'linux'
  properties: {
    reserved: true // Required for Linux plans
  }
}

// Application Insights
resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: 'appi-parking-frontend'
  location: location
  tags: tags
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logAnalyticsWorkspaceId
    RetentionInDays: 30
  }
}

// App Service for React Frontend
resource appService 'Microsoft.Web/sites@2023-01-01' = {
  name: 'app-parking-frontend-${uniqueString(resourceGroup().id)}'
  location: location
  tags: tags
  kind: 'app,linux'
  properties: {
    serverFarmId: appServicePlan.id
    httpsOnly: true
    siteConfig: {
      linuxFxVersion: 'NODE|18-lts'
      alwaysOn: true
      minTlsVersion: '1.2'
      ftpsState: 'Disabled'
      appSettings: [
        {
          name: 'APPINSIGHTS_INSTRUMENTATIONKEY'
          value: appInsights.properties.InstrumentationKey
        }
        {
          name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
          value: appInsights.properties.ConnectionString
        }
        {
          name: 'ApplicationInsightsAgent_EXTENSION_VERSION'
          value: '~3'
        }
        {
          name: 'REACT_APP_LISBON_API_URL'
          value: lisbonApiUrl
        }
        {
          name: 'REACT_APP_MADRID_API_URL'
          value: madridApiUrl
        }
        {
          name: 'REACT_APP_PARIS_API_URL'
          value: parisApiUrl
        }
        {
          name: 'REACT_APP_BERLIN_API_URL'
          value: berlinApiUrl
        }
        {
          name: 'REACT_APP_CHAOS_CONTROL_URL'
          value: chaosControlUrl
        }
        {
          name: 'REACT_APP_VM_HEALTH_CONTROL_URL'
          value: vmHealthControlUrl
        }
        {
          name: 'SCM_DO_BUILD_DURING_DEPLOYMENT'
          value: 'true'
        }
        {
          name: 'WEBSITE_NODE_DEFAULT_VERSION'
          value: '~20'
        }
        {
          name: 'WEBSITES_PORT'
          value: '8080'
        }
      ]
      appCommandLine: 'node server.js'
    }
  }
}

// Outputs
output appServiceName string = appService.name
output appServiceUrl string = 'https://${appService.properties.defaultHostName}'
output appServicePlanName string = appServicePlan.name
output appInsightsName string = appInsights.name
output appInsightsInstrumentationKey string = appInsights.properties.InstrumentationKey

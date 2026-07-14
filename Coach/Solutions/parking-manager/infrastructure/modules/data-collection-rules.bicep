@description('Azure region for monitoring resources')
param location string

@description('Log Analytics workspace resource ID')
param logAnalyticsWorkspaceId string

@description('Deploy Madrid VM data collection association')
param deployMadridVm bool = true

@description('Deploy Paris VM data collection association')
param deployParisVm bool = true

@description('Tags to apply to monitoring resources')
param tags object = {}

resource dataCollectionEndpoint 'Microsoft.Insights/dataCollectionEndpoints@2022-06-01' = {
	name: 'dce-parking-vm-logs'
	location: location
	kind: 'Linux'
	tags: tags
	properties: {
		networkAcls: {
			publicNetworkAccess: 'Enabled'
		}
	}
}

resource madridWindowsEventsDcr 'Microsoft.Insights/dataCollectionRules@2022-06-01' = if (deployMadridVm) {
	name: 'dcr-madrid-windows-events'
	location: location
	tags: tags
	properties: {
		dataCollectionEndpointId: dataCollectionEndpoint.id
		streamDeclarations: {}
		dataSources: {
			windowsEventLogs: [
				{
					name: 'madrid-windows-events'
					streams: [
						'Microsoft-Event'
					]
					xPathQueries: [
						'Application!*[System[*]]'
						'System!*[System[(Level=1 or Level=2 or Level=3)]]'
						'Security!*[System[(Level=1 or Level=2 or Level=3)]]'
					]
				}
			]
		}
		destinations: {
			logAnalytics: [
				{
					name: 'la-madrid-windows-events'
					workspaceResourceId: logAnalyticsWorkspaceId
				}
			]
		}
		dataFlows: [
			{
				streams: [
					'Microsoft-Event'
				]
				destinations: [
					'la-madrid-windows-events'
				]
			}
		]
	}
}

resource parisSyslogDcr 'Microsoft.Insights/dataCollectionRules@2022-06-01' = if (deployParisVm) {
	name: 'dcr-paris-syslog'
	location: location
	tags: tags
	properties: {
		dataCollectionEndpointId: dataCollectionEndpoint.id
		streamDeclarations: {}
		dataSources: {
			syslog: [
				{
					name: 'paris-linux-syslog'
					streams: [
						'Microsoft-Syslog'
					]
					facilityNames: [
						'auth'
						'authpriv'
						'cron'
						'daemon'
						'kern'
						'local0'
						'local1'
						'local2'
						'local3'
						'local4'
						'local5'
						'local6'
						'local7'
						'syslog'
						'user'
					]
					logLevels: [
						'Emergency'
						'Alert'
						'Critical'
						'Error'
						'Warning'
						'Notice'
						'Informational'
						'Debug'
					]
				}
			]
		}
		destinations: {
			logAnalytics: [
				{
					name: 'la-paris-syslog'
					workspaceResourceId: logAnalyticsWorkspaceId
				}
			]
		}
		dataFlows: [
			{
				streams: [
					'Microsoft-Syslog'
				]
				destinations: [
					'la-paris-syslog'
				]
			}
		]
	}
}

output dataCollectionEndpointId string = dataCollectionEndpoint.id
output dataCollectionEndpointLogsUri string = dataCollectionEndpoint.properties.logsIngestion.endpoint
output madridWindowsEventsDcrId string = deployMadridVm ? madridWindowsEventsDcr!.id : ''
output parisSyslogDcrId string = deployParisVm ? parisSyslogDcr!.id : ''

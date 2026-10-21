using './main.bicep'

// Replace with the name of your existing Azure SRE Agent.
// The subscription and resource group come from the deployment target, for
// example: az deployment group create --resource-group <rg> --template-file main.bicep
param agentName = '<your-sre-agent-name>'

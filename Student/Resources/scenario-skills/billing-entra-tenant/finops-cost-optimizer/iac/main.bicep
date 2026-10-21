// Deploy the FinOps Cost Optimizer skill and Python tools to an existing Azure
// SRE Agent through control plane (ARM) sub-resources.
//
// PREVIEW: api-version 2025-05-01-preview. Paths and schemas may change before
// general availability. The base64 envelope (properties.value) is documented,
// but the inner spec field names for tools and the skill are not fully published.
// Treat the fields marked CONFIRM as a starting point and verify them once with
// the capture step in deploy.ps1 (-Mode Capture), then adjust if needed.
//
// Deploy:
//   az deployment group create --resource-group <rg> \
//     --template-file billing-cost/finops-cost-optimizer/iac/main.bicep --parameters agentName=<agent>
//
// TENANT GATING: the control plane Agent Extensions API is restricted to internal
// Microsoft tenants in preview. On other tenants these PUTs fail with "Agent
// Extensions are not available for this tenant". For those tenants use the data
// plane script ./deploy.ps1 instead, which is the path the portal Builder uses.

targetScope = 'resourceGroup'

@description('Name of the existing Azure SRE Agent in this resource group.')
param agentName string

resource agent 'Microsoft.App/agents@2025-05-01-preview' existing = {
  name: agentName
}

// ---- Python tools -------------------------------------------------------------

var costRankSpec = {
  name: 'cost_rank' // CONFIRM
  description: 'Rank Azure subscriptions and resource groups by amortized spend.'
  language: 'python' // CONFIRM
  code: loadTextContent('../tools/cost_rank.py') // CONFIRM
  identity: 'system' // ARM managed identity. CONFIRM
}

var commitmentSpec = {
  name: 'commitment_recommendations'
  description: 'Reservation and savings plan recommendations.'
  language: 'python'
  code: loadTextContent('../tools/commitment_recommendations.py')
  identity: 'system'
}

var reportSpec = {
  name: 'generate_report'
  description: 'Build a self contained HTML FinOps cost optimization report.'
  language: 'python'
  code: loadTextContent('../tools/generate_report.py')
  identity: 'none'
}

resource costRankTool 'Microsoft.App/agents/tools@2025-05-01-preview' = {
  parent: agent
  name: 'cost_rank'
  properties: {
    value: base64(string(costRankSpec))
  }
}

resource commitmentTool 'Microsoft.App/agents/tools@2025-05-01-preview' = {
  parent: agent
  name: 'commitment_recommendations'
  properties: {
    value: base64(string(commitmentSpec))
  }
}

resource reportTool 'Microsoft.App/agents/tools@2025-05-01-preview' = {
  parent: agent
  name: 'generate_report'
  properties: {
    value: base64(string(reportSpec))
  }
}

// ---- Skill --------------------------------------------------------------------

var skillSpec = {
  name: 'finops-cost-optimizer' // CONFIRM
  description: 'FinOps cost optimization review across the subscriptions the agent can read. Ranks by spend, detects waste across seven dimensions, scores idle and orphaned resources by confidence to terminate, and produces a self contained HTML report.'
  content: loadTextContent('../SKILL.md') // CONFIRM (SKILL.md body)
  tools: [ // CONFIRM
    'RunAzCliReadCommands'
    'cost_rank'
    'commitment_recommendations'
    'generate_report'
  ]
  files: [ // CONFIRM (supporting files)
    {
      path: 'references/ranking-method.md'
      content: loadTextContent('../references/ranking-method.md')
    }
    {
      path: 'references/checks-catalog.md'
      content: loadTextContent('../references/checks-catalog.md')
    }
    {
      path: 'references/idle-detection.md'
      content: loadTextContent('../references/idle-detection.md')
    }
    {
      path: 'references/report-layout.md'
      content: loadTextContent('../references/report-layout.md')
    }
    {
      path: 'references/permissions-and-scope.md'
      content: loadTextContent('../references/permissions-and-scope.md')
    }
    {
      path: 'references/issues-optional.md'
      content: loadTextContent('../references/issues-optional.md')
    }
  ]
}

resource skill 'Microsoft.App/agents/skills@2025-05-01-preview' = {
  parent: agent
  name: 'finops-cost-optimizer'
  properties: {
    value: base64(string(skillSpec))
  }
  dependsOn: [
    costRankTool
    commitmentTool
    reportTool
  ]
}

output deployedSkill string = skill.name
output deployedTools array = [
  costRankTool.name
  commitmentTool.name
  reportTool.name
]

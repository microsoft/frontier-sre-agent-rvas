# IaC deployment

Deploy the FinOps Cost Optimizer skill to an existing Azure SRE Agent as code, instead of clicking through the Builder.

## Two planes, and which one works

The agent exposes its skills and tools two ways:

- Data plane (works broadly): the agent endpoint at https://{agent}.azuresre.ai/api/v2/extendedAgent, the same surface the portal Builder uses. This is the supported path for most tenants and what deploy.ps1 uses.
- Control plane (internal tenants only): the ARM sub-resources Microsoft.App/agents/skills and /tools. In preview these return "Agent Extensions are not available for this tenant. This feature is restricted to internal tenants only" on non internal tenants. main.bicep targets this plane, so it only works on internal Microsoft tenants for now.

Both are preview (control plane api-version 2025-05-01-preview). Schemas may change.

## Recommended: PowerShell data plane script

deploy.ps1 reads SKILL.md, bundles the reference files and the three Python helpers as additionalFiles, and PUTs the skill to the data plane. The helpers run in the agent with the RunInTerminal tool.

Prerequisites:

- Azure CLI with an active `az login` session.
- Builder access (the SRE Agent Administrator role) on the agent.
- The agent already exists.

Dry run first (no writes), then deploy:

```powershell
./deploy.ps1 -SubscriptionId <sub> -ResourceGroup <rg> -AgentName <agent> -DryRun
./deploy.ps1 -SubscriptionId <sub> -ResourceGroup <rg> -AgentName <agent>
```

Read existing skills and tools back to JSON (useful to confirm schema or inspect other skills):

```powershell
./deploy.ps1 -SubscriptionId <sub> -ResourceGroup <rg> -AgentName <agent> -Mode Capture
```

The skill schema used (captured from a live agent): properties.description, properties.tools (built-in tool names), properties.skillContent (the SKILL.md text), and properties.additionalFiles as a list of { filePath, content }. Plain JSON, no base64.

## Internal tenants only: Bicep control plane

main.bicep creates the skill and tools as ARM sub-resources with the base64 envelope. It only succeeds on internal Microsoft tenants. On other tenants it fails with the tenant restriction above; use the data plane script instead.

```powershell
az deployment group create --resource-group <rg> --template-file billing-cost/finops-cost-optimizer/iac/main.bicep --parameters agentName=<agent>
```

## Notes

- Deploys configuration only. It does not change the Azure resources being analyzed, and it preserves the read only posture of the skill.
- Windows PowerShell 5.1 ConvertTo-Json is extremely slow on large payloads, so deploy.ps1 builds the JSON with a fast explicit escaper. PowerShell 7 does not have this issue.
- The Python helpers run via RunInTerminal in the agent runtime (which has azure-identity, requests, pandas, and matplotlib) and authenticate with the agent managed identity.

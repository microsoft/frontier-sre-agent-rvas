# Shared deployment client

For the full walkthrough, prerequisites, runtime configuration, portal alternative, test prompts and troubleshooting, start with [Install a skill in your Azure SRE Agent](../../README.md#install-a-skill-in-your-azure-sre-agent).

## Run from the repository root

The following is a local packaging preview, not a deployment:

```powershell
.\shared\iac\deploy-skill.ps1 `
  -SubscriptionId '<subscription-containing-the-agent>' `
  -ResourceGroup '<resource-group-containing-the-agent>' `
  -AgentName '<existing-agent-resource-name>' `
  -SkillPath '.\management\slo-error-budget-analysis' `
  -DryRun
```

Replace all placeholders. After an authorized Azure CLI sign in and explicit approval of the destination and content, repeat without `-DryRun` to install. A matching skill name can update the existing definition. Save its previous content and files before an intentional update.

## What the client does

[deploy-skill.ps1](./deploy-skill.ps1) reads the selected skill's name, description and tools from `SKILL.md`. It packages the procedural guidance and these supporting files:

| Source | Deployed relative path |
| --- | --- |
| Immediate shared and skill reference files | `references/<filename>` |
| Immediate shared and skill tool files | `tools/<filename>` |
| Other immediate files in the skill root | `<filename>` |

The skill's file wins if it has the same deployed path as a shared file. `SKILL.md` is sent as procedural guidance, not duplicated as an attachment. Python unit tests are excluded. The client does not recursively attach subdirectories, sample reports or optional configurations.

With `-DryRun`, it prints the bundle and exits before authentication or network requests.

Without `-DryRun`, it:

1. Reads the existing `Microsoft.App/agents` resource with ARM API version `2025-05-01-preview` to resolve its endpoint.
2. Obtains an Azure CLI access token for the `https://azuresre.dev` audience. Tokens must not be copied into documents or logs.
3. Sends a `PUT` to `/api/v2/extendedAgent/skills/{name}` on that endpoint.
4. Reads the skill back and prints the saved skill name, attached file count and tools.

This is the library's client implementation, not a guarantee that the data plane API is available in every tenant or service version. If endpoint access is unavailable, use the documented Builder workflow with an authorized administrator. Do not assume a control plane limitation or weaken access controls to work around it.

## What it does not do

- Create an SRE Agent.
- Grant installer or managed identity permissions.
- Install Python packages, CLI extensions, Kubernetes contexts or connectors.
- Set the remote execution environment's identity variables.
- Validate a live investigation, schedule a task, remediate a resource or deliver a report.

The local installer identity and runtime agent identity are different concerns. Follow [the runtime setup steps](../../README.md#5-configure-runtime-tools-identity-and-access) and [permissions guide](../references/permissions-and-scope.md) before operational use.

## Sources

- [Deployment client implementation](./deploy-skill.ps1), checked 2026-10-21.
- [Microsoft: Skills in Azure SRE Agent](https://learn.microsoft.com/azure/sre-agent/skills), verified 2026-10-21.
- [Microsoft: User roles](https://learn.microsoft.com/azure/sre-agent/user-roles), verified 2026-10-21.
- [Microsoft: Agent permissions](https://learn.microsoft.com/azure/sre-agent/permissions), verified 2026-10-21.

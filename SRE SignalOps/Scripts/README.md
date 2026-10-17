# SignalOps Customer Demo Scripts

Run presenter scripts from the repository root in PowerShell 7. Deployment stages 00–02 and operational missions 09–12 have stable wrappers:

```powershell
pwsh -File '.\SRE SignalOps\Scripts\Challenge-00.ps1'
```

The default behavior is read-only or an azd/configuration preview. Deployment stages 00–02 preview staged azd changes and require `-Execute` to deploy them. Deployment stage 00 runs `azd up`; Deployment stages 01–02 run `azd provision`. Missions 01–08 are deliberate exceptions: customers run and inspect each command directly from the challenge page.

## Presenter Flow

| Stage / Mission | Default action | Opt-in action | Expected observation / fallback |
|---|---|---|---|
| Deploy 00 | Preview isolated workload provisioning | `-Execute` runs `azd up` | Deploys apps and workspace-backed observability |
| Deploy 01 | Preview isolated agent-core provisioning | `-Execute` runs `azd provision` | Deploys identity, RBAC, agent telemetry, and SRE Agent |
| Deploy 02 | Preview telemetry connector provisioning | `-Execute` runs `azd provision` and its postprovision hook | Adds two ARM connectors; hook verifies three local Review specialists and the response plan |
| 01 | Run each command directly from Challenge 01 | None | No wrapper script; stop cart requests at the first failure or 200-request cap |
| 02 | Run each command directly from Challenge 02 | Upload four approved knowledge files individually | No wrapper script; verify stored files and asynchronous indexing separately |
| 03 | Run each command directly from Challenge 03 | Validate each telemetry source independently | No wrapper script; distinguish deployment, access, and freshness evidence |
| 04 | Run each command directly from Challenge 04 | Compare live registration with three manifests | No wrapper script; an empty live roster is a valid registration-gap result |
| 05 | Run each command directly from Challenge 05 | Isolate approved VM deallocate/start commands | No wrapper script; use evidence-pack mode when no monitored VM exists |
| 06 | Run each command directly from Challenge 06 | Upload one reviewed context document and one verified lesson | No wrapper script; compare the exact same prompt before and after indexing |
| 07 | Verify advanced backup prerequisites or analyze supplied evidence | Coach deploys the separate Mission 07 add-on and publishes its Function | Live mode proves the approval gate, backup retry and newer recovery point; evidence-pack mode cannot certify integrations |
| 08 | Run each command directly from Challenge 08 | Validate routing, then run proposal-only branches | Mission 01 Sev2 and `grubify` match the all-severity plan; missing live registration must remain explicit |
| 09 | Generate traffic and query App Insights | None | Allow several minutes for ingestion; label absent edges unobserved |
| 10 | Inspect effective NSGs | Coach prepares sandbox fault | Use a sanitized incident snapshot without a sandbox |
| 11 | Inspect effective routes/next hop | Coach prepares route fault | Use forward/return evidence snapshot |
| 12 | Query inventory, Advisor, workspaces in the selected deployment subscription | Additional authorized evidence reads, never writes | Cost/utilization/backup/alert/freshness are unassessed until separately queried; zero supported findings is valid |

## Parameter Examples

```powershell
# Network sandbox
pwsh -File '.\SRE SignalOps\Scripts\Challenge-10.ps1' -SubscriptionId '<approved-subscription-id>' -ResourceGroup '<sandbox-rg>' -NicName '<nic-name>'

# Routing next hop
pwsh -File '.\SRE SignalOps\Scripts\Challenge-11.ps1' -SubscriptionId '<approved-subscription-id>' -ResourceGroup '<sandbox-rg>' -NicName '<nic-name>' -VmName '<vm>' -SourceIp '<ip>' -DestinationIp '<ip>'

# Deployment-neutral telemetry and assurance wrappers (choose one method)
pwsh -File '.\SRE SignalOps\Scripts\Challenge-09.ps1' -EnvironmentName signalops-core
pwsh -File '.\SRE SignalOps\Scripts\Challenge-12.ps1' -TerraformPath '<absolute-infra-path>'
```

Before the customer joins, authenticate with `az login`, select the correct subscription, run the relevant script without `-Execute`, sign in to `https://sre.azure.com`, and verify any OAuth connector separately. Never display tokens or secrets.

Initialize the isolated environment once before running Deployment stage 00's script:

```powershell
Push-Location '.\SRE SignalOps'
$TenantId = Read-Host 'Microsoft Entra tenant ID'
$SubscriptionId = Read-Host 'Approved Azure subscription ID'
azd auth login --tenant-id $TenantId
az login --tenant $TenantId
az account set --subscription $SubscriptionId
azd env new signalops-core --subscription $SubscriptionId --location swedencentral
Pop-Location
```

Deployment scripts verify that the selected azd environment matches the active
Azure CLI subscription before changing deployment flags or provisioning. They
read application URLs from environment outputs rather than fixed resource names.
Missions 09 and 12 select the supplied Bicep environment or Terraform output context
and reject a mismatched active subscription. Missions 10 and 11 require an explicit
approved sandbox subscription and reject mismatches. Run the route wrapper for
both endpoints to obtain independent forward/return observations.

`Register-SignalOpsAgent.ps1` is the common data-plane registration path. Bicep's
postprovision hook invokes it after connectors are enabled; Terraform completion
invokes it with `-UploadKnowledge`. `-ValidateOnly -AgentId offline` validates the
local bundle without Azure access. It does not register a default source
repository, GitHub connector, scheduled task, or unrelated scenario.
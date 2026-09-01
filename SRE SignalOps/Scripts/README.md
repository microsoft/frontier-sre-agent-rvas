# SignalOps Customer Demo Scripts

Run presenter scripts from the repository root in PowerShell 7. Most challenges have a stable wrapper:

```powershell
pwsh -File '.\SRE SignalOps\Scripts\Challenge-00.ps1'
```

The default behavior is read-only or an azd/configuration preview. Missions 00–02 preview staged azd changes and require `-Execute` to deploy them. Mission 00 runs `azd up`; Missions 01–02 run `azd provision`. Missions 03–05 are deliberate exceptions: customers run and inspect each command directly from the challenge page. The VM heartbeat action additionally supports `-Restore`.

## Presenter Flow

| Challenge | Default action | Opt-in action | Expected observation / fallback |
|---|---|---|---|
| 00 | Preview isolated workload provisioning | `-Execute` runs `azd up` | Deploys apps and workspace-backed observability |
| 01 | Preview isolated agent-core provisioning | `-Execute` runs `azd provision` | Deploys identity, RBAC, agent telemetry, and SRE Agent |
| 02 | Preview telemetry connector provisioning | `-Execute` runs `azd provision` | Adds two connectors, then audits evidence state |
| 03 | Run each command directly from Challenge 03 | None | No wrapper script; stop cart requests at the first failure or 200-request cap |
| 04 | Run each command directly from Challenge 04 | Upload four approved knowledge files individually | No wrapper script; verify stored files and asynchronous indexing separately |
| 05 | Run each command directly from Challenge 05 | Validate each telemetry source independently | No wrapper script; distinguish deployment, access, and freshness evidence |
| 06 | Inventory specialists | None | Use local manifests if the data plane is slow |
| 07 | Show filters and incident wiring | None | Use filter manifests as the control-flow fallback |
| 08 | Generate traffic and query App Insights | None | Allow several minutes for ingestion; label absent edges unobserved |
| 09 | Inspect effective NSGs | Coach prepares sandbox fault | Use a sanitized incident snapshot without a sandbox |
| 10 | Inspect effective routes/next hop | Coach prepares route fault | Use forward/return evidence snapshot |
| 11 | Query Heartbeat | `-Execute` deallocates; `-Restore` starts lab VM | Use evidence-pack mode when no monitored VM exists |
| 12 | List memory and create a draft | Portal ingests the draft | Compare the exact same prompt before and after ingestion |
| 13 | Query inventory, Advisor, workspaces | None | Report unavailable cost/utilization access as a limitation |
| 14 | Inventory vaults and draft Teams update | Portal-approved Teams post | Evidence-pack mode must not claim delivery |

## Parameter Examples

```powershell
# Network sandbox
pwsh -File '.\SRE SignalOps\Scripts\Challenge-09.ps1' -ResourceGroup '<sandbox-rg>' -NicName '<nic-name>'

# Routing next hop
pwsh -File '.\SRE SignalOps\Scripts\Challenge-10.ps1' -ResourceGroup '<sandbox-rg>' -NicName '<nic-name>' -VmName '<vm>' -SourceIp '<ip>' -DestinationIp '<ip>'

# Heartbeat baseline and controlled lab fault
pwsh -File '.\SRE SignalOps\Scripts\Challenge-11.ps1' -WorkspaceId '<workspace-id>' -VmResourceId '<resource-id>'
pwsh -File '.\SRE SignalOps\Scripts\Challenge-11.ps1' -WorkspaceId '<workspace-id>' -VmResourceId '<resource-id>' -ResourceGroup '<rg>' -VmName '<vm>' -Execute
pwsh -File '.\SRE SignalOps\Scripts\Challenge-11.ps1' -WorkspaceId '<workspace-id>' -VmResourceId '<resource-id>' -ResourceGroup '<rg>' -VmName '<vm>' -Restore
```

Before the customer joins, authenticate with `az login`, select the correct subscription, run the relevant script without `-Execute`, sign in to `https://sre.azure.com`, and verify any OAuth connector separately. Never display tokens or secrets.

Initialize the isolated environment once before running Mission 00's script:

```powershell
Push-Location '.\SRE SignalOps'
azd auth login --tenant-id 16b3c013-d300-468d-ac64-7eda0820b6d3
azd env new signalops-core --subscription b1e100ca-fff5-4e0e-9847-2e44bf47b68c --location swedencentral
Pop-Location
```
# SignalOps Customer Demo Scripts

Run these scripts from the repository root in PowerShell 7. Each challenge has a stable wrapper:

```powershell
pwsh -File '.\SRE SignalOps\Scripts\Challenge-00.ps1'
```

The default behavior is read-only or a configuration plan. Missions 00–02 are permanently read-only and validate the existing Terraform-deployed MCAPS lab; they reject `-Execute` and `-Restore`. Later scripts that can change Azure require `-Execute`; the VM heartbeat action additionally supports `-Restore`.

## Presenter Flow

| Challenge | Default action | Opt-in action | Expected observation / fallback |
|---|---|---|---|
| 00 | Validate existing food workload and telemetry | None; mutation switches are rejected | Uses `rg-sre-spoke-foodapp-paas` in Sweden Central |
| 01 | Verify existing agent, mode, access, and scopes | None; mutation switches are rejected | Uses `rg-sre-agent/contoso-sre-agent-dev` |
| 02 | Audit current telemetry, repository, and knowledge evidence | None; mutation switches are rejected | Telemetry is connected; repositories and knowledge files are empty |
| 03 | Plan four config targets | `-Execute` applies them | Never apply external connector examples blindly |
| 04 | Inventory live connectors | None | Demonstrate configured versus proven connectivity |
| 05 | Inventory specialists | None | Use local manifests if the data plane is slow |
| 06 | Show filters and incident wiring | None | Use filter manifests as the control-flow fallback |
| 07 | Generate traffic and query App Insights | None | Allow several minutes for ingestion; label absent edges unobserved |
| 08 | Inspect effective NSGs | Coach prepares sandbox fault | Use a sanitized incident snapshot without a sandbox |
| 09 | Inspect effective routes/next hop | Coach prepares route fault | Use forward/return evidence snapshot |
| 10 | Query Heartbeat | `-Execute` deallocates; `-Restore` starts lab VM | Use evidence-pack mode when no monitored VM exists |
| 11 | List memory and create a draft | Portal ingests the draft | Compare the exact same prompt before and after ingestion |
| 12 | Query inventory, Advisor, workspaces | None | Report unavailable cost/utilization access as a limitation |
| 13 | Inventory vaults and draft Teams update | Portal-approved Teams post | Evidence-pack mode must not claim delivery |

## Parameter Examples

```powershell
# Network sandbox
pwsh -File '.\SRE SignalOps\Scripts\Challenge-08.ps1' -ResourceGroup '<sandbox-rg>' -NicName '<nic-name>'

# Routing next hop
pwsh -File '.\SRE SignalOps\Scripts\Challenge-09.ps1' -ResourceGroup '<sandbox-rg>' -NicName '<nic-name>' -VmName '<vm>' -SourceIp '<ip>' -DestinationIp '<ip>'

# Heartbeat baseline and controlled lab fault
pwsh -File '.\SRE SignalOps\Scripts\Challenge-10.ps1' -WorkspaceId '<workspace-id>' -VmResourceId '<resource-id>'
pwsh -File '.\SRE SignalOps\Scripts\Challenge-10.ps1' -WorkspaceId '<workspace-id>' -VmResourceId '<resource-id>' -ResourceGroup '<rg>' -VmName '<vm>' -Execute
pwsh -File '.\SRE SignalOps\Scripts\Challenge-10.ps1' -WorkspaceId '<workspace-id>' -VmResourceId '<resource-id>' -ResourceGroup '<rg>' -VmName '<vm>' -Restore
```

Before the customer joins, authenticate with `az login`, select the correct subscription, run the relevant script without `-Execute`, sign in to `https://sre.azure.com`, and verify any OAuth connector separately. Never display tokens or secrets.
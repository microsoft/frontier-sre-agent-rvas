[< Previous Solution](./Solution-06.md) | **[Home](../README.md)** | [Next Solution >](./Solution-08.md)

# Coach Guide — Challenge 07: Respond to a VM Backup Failure with External Approval

## Purpose

- Teach students to separate VM power state from recoverability and recovery authorization.
- Exercise a machine-enforced, external approval boundary around one incident-bound backup retry.
- Expected time: 75–90 minutes, including provisioning and connector authorization.

## Mini-Lecture (10 min before challenge)

- Azure VM Backup can protect `vm-parking-madrid` while it is deallocated; incident response does not need to start it.
- Native Azure Backup alerts provide the incident signal; diagnostic logs provide history and can arrive 20–30 minutes later.
- Review-mode prompts and five-minute schedules coordinate behavior but do not enforce security. The Function gate independently validates the decision, incident age, action, and one-time claim.
- The Teams connector is the authority for responder identity. Card text, URL parameters, and chat claims are not approval evidence.
- A retry is safer than an automatic restore. Validate the job and a newer recovery point before closure.

## Expected Student Output

- `vm-parking-madrid` as the only protected item created for the challenge.
- A protected Azure IaaS VM item with at least one successful recovery point.
- A backup-specific Review response plan, specialist, five-minute scheduled task, and connected approval MCP tools.
- A Teams decision record containing the authenticated responder identity and durable timestamps.
- Negative-test evidence for early, denied, malformed, and replayed execution.
- Positive-test evidence for one approved retry and a newer recovery point.

## Common Issues and Hints

- **Symptom:** VM protection reports that the item is invalid or already protected. **Fix:** confirm the protected-item source ID resolves exactly to `rg-sre-parking-madrid/vm-parking-madrid` and inspect existing vault protection before retrying.
- **Symptom:** The Function deployment reports storage authorization failure. **Fix:** wait for Blob Data Owner, Queue Data Contributor, and Table Data Contributor role propagation, then rerun deployment.
- **Symptom:** The Teams connection shows `Unauthenticated` or the channel is not listed. **Fix:** authorize the API connection interactively with an account in the expected tenant and verify access to the exact group and channel.
- **Symptom:** The approval request times out before an engineer responds. **Fix:** verify the Logic App returns HTTP `202` before its wait action and inspect workflow run history.
- **Symptom:** The gate reports `The incident is less than five minutes old.` **Fix:** preserve the original Azure Monitor creation time and let the next five-minute task run; never replace the timestamp.
- **Symptom:** The gate reports that the action has already been claimed. **Fix:** treat this as successful replay protection and inspect the original operation URL instead of retrying.
- **Symptom:** The backup job succeeds but no newer recovery point appears. **Fix:** keep the incident open, capture the job and protected-item evidence, and escalate without restoring live data.
- **Symptom:** The VM is deallocated. **Fix:** leave it deallocated; do not start or restart it for this challenge.

## Debrief Discussion Guide

- Why can a deallocated VM remain the target? → Azure Backup protection and an on-demand backup retry do not require this incident workflow to start the VM.
- Why does the workflow acknowledge before waiting for Teams? → The Function request must complete asynchronously rather than block for a human response.
- Which component is the true authorization boundary? → The Function policy and durable state, not the SRE Agent prompt, response-plan mode, schedule, or card text.
- Why compare recovery-point timestamps after a successful job? → Job completion alone does not prove the expected recoverability artifact was created.
- Why is restore excluded? → A restore has a larger blast radius and requires a separately approved target and validation plan.

## Success Criteria Notes

- Be strict on one-VM scope, protected-item/recovery-point proof, connector-authenticated identity, five-minute enforcement, replay denial, and post-retry validation.
- Reject screenshots without resource IDs/timestamps, approvals inferred from chat, exposed callback URLs or keys, and any generic Azure write grant on the specialist.
- Accept a coach-controlled failed-job incident or a safe synthetic incident only when the team labels which parts are synthetic and still executes the real gate negative tests.
- Do not accept a successful deployment as proof that Teams OAuth, a backup retry, or a new recovery point works.

## Solution

### Validate and deploy the prepared environment

The core lab does not provision this advanced integration. From the repository
root, load `$Lab` using the deployment-neutral mission README. Obtain approval
for the existing Madrid VM and Teams channel. The VM must be in the vault's
region and must not already be protected by another vault. Do not run a second
core deployment against Terraform-owned resources.

```powershell
$ErrorActionPreference = 'Stop'
$EnvironmentName = Read-Host 'Unique Mission 07 environment name (1-20 characters)'
$VmGroup = Read-Host 'Approved resource group containing vm-parking-madrid'
$TeamsGroup = Read-Host 'Approved Teams group ID'
$TeamsChannel = Read-Host 'Approved Teams channel ID'
$WORKLOAD_RG = $Lab.AZURE_RESOURCE_GROUP
az account set --subscription $Lab.AZURE_SUBSCRIPTION_ID
if ($LASTEXITCODE -ne 0) { throw 'Could not select the lab subscription.' }
$Vm = az vm show --resource-group $VmGroup --name vm-parking-madrid -o json | ConvertFrom-Json
if ($LASTEXITCODE -ne 0 -or -not $Vm.id) { throw 'The approved Madrid VM does not exist.' }
$Location = (az group show --name $WORKLOAD_RG --query location -o tsv).Trim()
if ($LASTEXITCODE -ne 0 -or $Vm.location -ne $Location) { throw 'VM and vault regions must match.' }
$Insights = @(az resource list --resource-group $WORKLOAD_RG --resource-type Microsoft.Insights/components -o json | ConvertFrom-Json)
if ($LASTEXITCODE -ne 0 -or $Insights.Count -ne 1) { throw 'Resolve exactly one workload Application Insights component.' }
$Parameters = @(
  "environmentName=$EnvironmentName", "location=$Location",
  "backupVmResourceGroup=$VmGroup", 'backupVmName=vm-parking-madrid',
  "teamsGroupId=$TeamsGroup", "teamsChannelId=$TeamsChannel",
  "logAnalyticsWorkspaceName=$($Lab.LOG_ANALYTICS_WORKSPACE_ID.Split('/')[-1])",
  "applicationInsightsName=$($Insights[0].name)"
)
az deployment group what-if --resource-group $WORKLOAD_RG --template-file '.\SRE SignalOps\infra\backup.bicep' --parameters @Parameters
if ($LASTEXITCODE -ne 0) { throw 'Mission 07 preview failed.' }
```

Review the preview for replacement/deletion and approve the one-VM scope
before this separate deployment. Its outputs are not azd or Terraform outputs.

```powershell
$Deployment = az deployment group create --name signalops-mission09 --resource-group $WORKLOAD_RG --template-file '.\SRE SignalOps\infra\backup.bicep' --parameters @Parameters -o json | ConvertFrom-Json
if ($LASTEXITCODE -ne 0 -or $Deployment.properties.provisioningState -ne 'Succeeded') { throw 'Mission 07 deployment failed.' }
$Backup = $Deployment.properties.outputs
$FUNCTION_NAME = $Backup.BACKUP_APPROVAL_FUNCTION_NAME.value
$VAULT_NAME = $Backup.BACKUP_VAULT_NAME.value
$VM_NAME = $Backup.BACKUP_VM_NAME.value
```

Provisioning does not publish Function code. With the .NET 10 SDK installed,
publish only the approval service into fresh staging, deploy the zip, and remove
staging. The project excludes local settings from publishing.

```powershell
$Stage = Join-Path ([IO.Path]::GetTempPath()) "signalops-backup-$([Guid]::NewGuid())"
$Publish = Join-Path $Stage 'publish'
$Zip = Join-Path $Stage 'approval.zip'
try {
  dotnet publish '.\Student\Resources\backup-approval-gate\BackupApprovalGate.csproj' -c Release -o $Publish
  if ($LASTEXITCODE -ne 0) { throw 'Backup approval Function build failed.' }
  [IO.Compression.ZipFile]::CreateFromDirectory($Publish, $Zip)
  az functionapp deployment source config-zip --resource-group $WORKLOAD_RG --name $FUNCTION_NAME --src $Zip --build-remote false
  if ($LASTEXITCODE -ne 0) { throw 'Backup approval Function publication failed.' }
} finally {
  if (Test-Path -LiteralPath $Stage) { Remove-Item -LiteralPath $Stage -Recurse -Force }
}
```

### Authorize Teams and connect the MCP gate

In the Azure portal, open the API connection named by `$Backup.BACKUP_TEAMS_CONNECTION_NAME.value`, choose **Edit API connection**, and authorize it interactively. Confirm the authenticated tenant and approved group/channel. Never paste OAuth credentials into a terminal or chat.

Resolve the Function MCP system key directly into the current process and apply the connector without printing it:

```powershell
$FUNCTION_HOST = (az functionapp show --name $FUNCTION_NAME --resource-group $WORKLOAD_RG --query defaultHostName -o tsv).Trim()
if ($LASTEXITCODE -ne 0 -or -not $FUNCTION_HOST) { throw 'Cannot resolve the approval Function.' }
$env:BACKUP_APPROVAL_MCP_URL = "https://$FUNCTION_HOST/runtime/webhooks/mcp"
$env:BACKUP_APPROVAL_MCP_KEY = (az functionapp keys list --name $FUNCTION_NAME --resource-group $WORKLOAD_RG --query systemKeys.mcp_extension -o tsv).Trim()
if ($LASTEXITCODE -ne 0 -or -not $env:BACKUP_APPROVAL_MCP_KEY) { throw 'The deployed MCP extension key is unavailable.' }
$env:SIGNALOPS_SUBSCRIPTION_ID = $Lab.AZURE_SUBSCRIPTION_ID
$env:SIGNALOPS_AGENT_GROUP = $Lab.SRE_AGENT_ID.Split('/')[4]
$env:SIGNALOPS_AGENT_NAME = $Lab.SRE_AGENT_ID.Split('/')[-1]
```

Start Git Bash **from this PowerShell process** so it inherits the short-lived
environment variables, then run the block below from the repository root.
Stage only the backup manifests: applying the whole shared configuration would
register unrelated source repositories and automations. Review the scoped plan
before explicitly confirming application.

```bash
set -euo pipefail
backup_config="$(mktemp -d)"
trap 'rm -rf -- "$backup_config"' EXIT
source_config="Student/Resources/azure-sre-agent-config"
for relative in \
  subagents/grubify-backup-specialist.yaml \
  connectors/backup-approval-gate.yaml \
  automations/incident-filters/grubify-backup-failures.yaml \
  automations/scheduled-tasks/grubify-backup-approval-check.yaml \
  skills/grubify-backup-response.yaml \
  skills/grubify-backup-response.md \
  knowledge/files/sample-food/grubify-backup-runbook.md
do
  mkdir -p "$backup_config/$(dirname "$relative")"
  cp "$source_config/$relative" "$backup_config/$relative"
done
config_script="Student/Resources/infra/scripts/sre-agent-config.sh"
target=(--config "$backup_config" --subscription "$SIGNALOPS_SUBSCRIPTION_ID" --resource-group "$SIGNALOPS_AGENT_GROUP" --agent "$SIGNALOPS_AGENT_NAME")
bash "$config_script" validate "${target[@]}"
bash "$config_script" plan "${target[@]}"
read -r -p "Apply only this reviewed backup configuration? Type APPLY: " approval
test "$approval" = APPLY
bash "$config_script" apply "${target[@]}"
```

Clear the key when configuration is complete:

```powershell
Remove-Item Env:BACKUP_APPROVAL_MCP_KEY
```

### Prove VM protection

Confirm the only protected item created for this challenge resolves to `vm-parking-madrid`, then inspect its recovery points. Leave the VM deallocated.

```powershell
az backup item list --vault-name $VAULT_NAME --resource-group $WORKLOAD_RG --backup-management-type AzureIaasVM --query "[?properties.friendlyName=='$VM_NAME'].{VM:properties.friendlyName,Protection:properties.protectionState,LastBackup:properties.lastBackupTime}" -o table
az backup recoverypoint list --vault-name $VAULT_NAME --resource-group $WORKLOAD_RG --backup-management-type AzureIaasVM --container-name '<container-from-item>' --item-name '<protected-item-name>' -o table
```

Do not mark this criterion complete until a successful recovery point exists. If initial protection has not run, trigger the first on-demand backup through an explicitly approved operator action and wait for completion.

### Exercise the approval policy

Use a unique exercise incident ID and a UTC creation time. Create the request through the MCP tool, then immediately call execute. The expected denial is `The incident is less than five minutes old.`

Approve or deny the adaptive card in Teams and verify the durable status through `get_backup_approval`. A denied incident must remain non-executable. For the approved case, wait until at least five minutes after the immutable incident creation time and allow the scheduled task or specialist to invoke `execute_approved_backup_retry`.

Call execute a second time for the same approved incident. The expected denial states that the action has already been claimed. Also submit malformed decision payloads only through a controlled HTTP test against the Function callback; expect `400`, and never expose the Function key in evidence.

### Verify remediation

Record the newest recovery point before execution, then compare it to the point created by the approved retry. Require the associated backup job to finish successfully.

```powershell
az backup job list --vault-name $VAULT_NAME --resource-group $WORKLOAD_RG --query '[].{Operation:properties.operation,Status:properties.status,Start:properties.startTime,End:properties.endTime,Entity:properties.entityFriendlyName}' -o table
```

Close the exercise only when the job is complete, the recovery point is newer, and the approval record proves one authenticated decision and one claim. Escalate failures with IDs, UTC timestamps, and errors; do not start, restart, or restore the VM.

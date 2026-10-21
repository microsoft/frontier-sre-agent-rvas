# Evidence collection and analysis

## Collection

### 1. Read available recovery points for the exact VM item

Read metadata only. Select the correct protected item and preserve any continuation or time filtering limits. Do not substitute the newest backup time for the latest verified recovered committed write.

```powershell
az backup recoverypoint list --subscription $SUB --resource-group $RG --vault-name $VAULT --container-name $CONTAINER --item-name $ITEM --backup-management-type AzureIaasVM --output json
```

### 2. Read a separately authorized restore job

Run only when a real, separately authorized job ID exists. If no drill has occurred, report Not assessed and produce the drill plan, not fictional completion evidence. This command does not start, stop or wait indefinitely on a job.

```powershell
az backup job show --subscription $SUB --resource-group $RG --vault-name $VAULT --name $JOB_ID --output json
```

### 3. Assess timed recovery and integrity evidence locally

Use [the input contract](../../../shared/references/operational-evidence.md) and [synthetic fixture](./evidence-example.json). The collector and analyzer do not execute restore commands. Verify the operator log independently before entering booleans or timestamps.

```powershell
python tools/operational_analysis.py --scenario backup-restore-validation --input $INPUT --contract references/output-contract.json --output restore-private-result.json --sharing-output restore-sharing-draft.json
```

## Analysis rules

1. Require evidence of an isolated target, actual restore outcome and application specific integrity checks. A completed platform restore is not proof of business recovery.
2. Measure the drill RTO interval from the approved recovery start through application readiness, including dependent recovery steps. State whether detection and decision time are included; do not imply they were measured when the clock starts later.
3. Measure recovered data age from the agreed simulated loss reference minus the latest verified recovered committed write. Reject reversed timestamps and distinguish this measured drill RPO from configured backup frequency.
4. Compare measured seconds against customer approved targets. Failed completion, a nonisolated destination or failed integrity yields Needs attention. Missing timed or integrity evidence remains Not assessed.
5. Generate a drill plan, validation checklist and cleanup proposal before any execution. Restore, failover, isolation changes, integrity test writes and deletion require separate explicit approval.

## Known limits

- The read commands cover Recovery Services Azure VM backups. Database, Backup vault and other protection types need their documented metadata adapter and service specific recovery procedure.
- A single successful drill establishes only the tested data, application version, restore point, dependencies and observation window. It is not a universal recovery guarantee.

## Expected validation cases

- Healthy: completed isolated restore, passed integrity,1200 second recovery and120 second recovered data age meet synthetic targets1800 and300 seconds.
- Finding: failed integrity, incomplete restore or elapsed time above a target produces Needs attention, not backup compliant.
- Missing: backup policy or Completed job without application ready and verified recovered write evidence is Not assessed.

## Sources

- [Isolated restores, full flow recovery and integrity validation](https://learn.microsoft.com/azure/well-architected/reliability/reliability-test) (consulted 2026-10-21).
- [Azure CLI backup recovery point metadata](https://learn.microsoft.com/cli/azure/backup/recoverypoint?view=azure-cli-latest) (consulted 2026-10-21).
- [Azure CLI backup job metadata](https://learn.microsoft.com/cli/azure/backup/job?view=azure-cli-latest) (consulted 2026-10-21).

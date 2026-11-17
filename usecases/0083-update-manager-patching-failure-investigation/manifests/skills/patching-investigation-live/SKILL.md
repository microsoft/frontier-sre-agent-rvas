---
name: patching-investigation-live
description: Read-only Azure Update Manager post-patching cycle reporting and automated per-machine failure & blocker root-cause investigation across Azure VMs and Azure Arc-enabled servers.
tools:
- patching-investigation-report
---

# Azure Update Manager patching & failure investigation

Use ONLY `patching-investigation-report`. The specialist must explicitly select only this tool and this skill; never enable shell, exec, generic Python, write connectors, VM start/stop, or `installPatches` / `assessPatches` actions.

## Scope, identity and read-only guarantees

- The tool reads fixed administrator constants (`SUBSCRIPTION_ID`, `MANAGED_IDENTITY_CLIENT_ID`, `CLIENT_NAME`, `CLIENT_LOGO_DATA_URI`, `CLIENT_LOGO_ALT`, `OUTPUT_DIRECTORY = "patching-investigation-reports"`).
- If `SUBSCRIPTION_ID` or `MANAGED_IDENTITY_CLIENT_ID` still contains a `<PLACEHOLDER>`, the tool fails closed before authentication or network calls with `status="error"` and `error.code="configuration_required"` (`artifact_status="not_written"`).
- Executes 7 read-only Azure Resource Graph (`https://management.azure.com/providers/Microsoft.ResourceGraph/resources?api-version=2022-10-01`) queries:
  1. `arg_compute_machines` (`microsoft.compute/virtualmachines`, `microsoft.hybridcompute/machines`)
  2. `arg_patch_assessments` (`patchassessmentresources | where type !endswith '/softwarepatches'`)
  3. `arg_software_patches_pending` (`patchassessmentresources | where type endswith '/softwarepatches'`)
  4. `arg_patch_installations` (`patchinstallationresources | where type !endswith '/softwarepatches'`)
  5. `arg_software_patches_installed` (`patchinstallationresources | where type endswith '/softwarepatches'`)
  6. `arg_maintenance_cycles` (`maintenanceresources`)
  7. `arg_patch_extensions` (`microsoft.compute/virtualmachines/extensions`, `microsoft.hybridcompute/machines/extensions` — never reading `settings` or `protectedSettings`).

## Automated per-machine root-cause investigation contract

Every machine in `arg_compute_machines` is correlated with its maintenance cycles, installation runs, assessment status, pending packages, Hotpatch readiness, and guest extensions into an explicit diagnostic category:

- `maintenance_window_unresponsive`: Scheduled maintenance cycle ended in `ShutdownOrUnresponsive` or installation run failed / exceeded the window.
- `arc_agent_expired_or_disconnected`: Azure Arc machine (`microsoft.hybridcompute/machines`) has `status` in `Expired`, `Disconnected`, or `Error`.
- `assessment_stuck_or_readiness_undetermined`: Assessment is stuck in `InProgress` or `Failed`, or `detectedVMGuestPatchSupportState` is `UnableToDetermine` / `Unsupported`.
- `hotpatch_or_patch_extension_error`: `hotpatchStatus` reports an error (such as `HotpatchEnablementRequiredForReadiness` referencing `C:\WindowsAzure\Logs\Plugins\Microsoft.CPlat.Core.WindowsPatchExtension\...`) or a guest extension is in `provisioningState="Failed"`.
- `pending_security_patches_unscheduled`: Assessment succeeded and found pending `Security`, `Critical`, or `UpdateRollUp` patches, but the machine has no assigned maintenance configuration or installation runs in the window.
- `unassessed_no_update_manager_telemetry`: Machine exists in compute inventory (typically deallocated) with no `patchassessmentresources` or `patchinstallationresources` telemetry.
- `healthy`: Machine is assessed, has no failed/unresponsive cycles, no extension/Hotpatch errors, and zero unscheduled security/critical updates.

## Four-file report delivery (`operation="report"`)

For a report request (or the monthly `0 8 1 * *` scheduled task), invoke `operation="report"` once (default `period="last_30d"`, with all filter/paging parameters at defaults) and immediately deliver all four artifacts:
- `report_path` / `report_url`: `patch-<timestamp>-<hash>.html`
- `snapshot_path` / `snapshot_url`: `patch-<timestamp>-<hash>-snapshot.json`
- `machines_csv_path` / `machines_csv_url`: `patch-<timestamp>-<hash>-machines.csv`
- `patches_csv_path` / `patches_csv_url`: `patch-<timestamp>-<hash>-patches.csv`

When `sharing_mode="native_ui"`, render all four `*_url` values unchanged as native Markdown links/file widgets in the same turn. Never invent or reuse a thread UUID.

## Bounded queries (`operation="query"`)

For targeted questions, invoke `operation="query"` with `view` in `summary`, `machines`, `failures`, `cycles`, `patches`, `extensions`, `coverage`, or `actions`, and optional filters `period`, `hosting`, `failure_category`, `machine_name`, `limit`, and `offset`. Disclose `total_matched`, `returned`, `has_more`, `next_offset`, and `transport_capped`.

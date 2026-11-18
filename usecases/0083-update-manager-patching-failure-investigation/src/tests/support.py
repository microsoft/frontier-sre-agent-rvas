"""Shared synthetic test support for Case 09; never imported by the runtime tool."""

import base64
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REFERENCE = "2026-10-20T16:00:00Z"
SUBSCRIPTION = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
CLIENT_ID = "12345678-1234-4abc-8def-123456789abc"
RG_ARC_SERVERS = "rg-arc-servers-weu"
RG_ONPREM = "rg-arc-onprem"
RG_AUTO = "rg-automation"


def make_jwt(appid, aud="https://management.azure.com"):
    header = base64.urlsafe_b64encode(b'{"alg":"RS256","typ":"JWT"}').decode("ascii").rstrip("=")
    payload = base64.urlsafe_b64encode(
        json.dumps({"appid": appid, "aud": aud, "tid": "11111111-1111-4111-8111-111111111111"}).encode("utf-8")
    ).decode("ascii").rstrip("=")
    return header + "." + payload + ".signature"


def load_engine(standalone=False):
    target = (ROOT.parent / "manifests" / "tools" / "generate-patching-investigation-report.py" if standalone else ROOT / "engine.py")
    spec = importlib.util.spec_from_file_location("patching_engine_test", target)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not standalone:
        module.HTML_TEMPLATE = (ROOT / "report_template.html").read_text(encoding="utf-8")
    module.SUBSCRIPTION_ID = SUBSCRIPTION
    module.MANAGED_IDENTITY_CLIENT_ID = CLIENT_ID
    return module


def raw_arg_fixture():
    vm_prefix = "/subscriptions/" + SUBSCRIPTION + "/resourceGroups/" + RG_ARC_SERVERS + "/providers/Microsoft.Compute/virtualMachines/"
    arc_prefix = "/subscriptions/" + SUBSCRIPTION + "/resourceGroups/" + RG_ARC_SERVERS + "/providers/Microsoft.HybridCompute/machines/"
    onprem_arc_prefix = "/subscriptions/" + SUBSCRIPTION + "/resourceGroups/" + RG_ONPREM + "/providers/Microsoft.HybridCompute/machines/"
    onprem_vm_prefix = "/subscriptions/" + SUBSCRIPTION + "/resourceGroups/" + RG_ONPREM + "/providers/Microsoft.Compute/virtualMachines/"
    auto_vm_prefix = "/subscriptions/" + SUBSCRIPTION + "/resourceGroups/" + RG_AUTO + "/providers/Microsoft.Compute/virtualMachines/"

    host_vm_id = vm_prefix + "vm-arc-host-weu"
    arc_sql_id = arc_prefix + "arc-sql-01"
    arc_win2k22_id = arc_prefix + "arc-win2k22-01"
    arc_ubuntu01_id = arc_prefix + "arc-ubuntu-01"
    arc_ubuntu02_id = arc_prefix + "arc-ubuntu-02"
    arc_expired_id = onprem_arc_prefix + "vm-arc-win-01"
    vm_failed_ext_id = onprem_vm_prefix + "vm-arc-win-04"
    vm_unassessed_id = auto_vm_prefix + "vm-linux-01"
    vm_healthy_id = vm_prefix + "vm-healthy-01"

    maint_conf_win = (
        "/subscriptions/" + SUBSCRIPTION + "/resourceGroups/" + RG_ARC_SERVERS
        + "/providers/Microsoft.Maintenance/maintenanceConfigurations/mc-windows-monthly"
    )
    maint_conf_weekly = (
        "/subscriptions/00000000-0000-0000-0000-0000000000b1/resourcegroups/rg-update-management"
        "/providers/microsoft.maintenance/maintenanceconfigurations/mc-platform-weekly"
    )

    return {
        "arg_compute_machines": [
            {
                "id": host_vm_id,
                "name": "vm-arc-host-weu",
                "type": "microsoft.compute/virtualmachines",
                "resourceGroup": RG_ARC_SERVERS,
                "location": "westeurope",
                "tags": {"env": "poc", "secret_token": "DO-NOT-EXPORT"},
                "properties": {
                    "provisioningState": "Succeeded",
                    "vmId": "aaaaaaaa-1111-4111-8111-111111111111",
                    "osProfile": {
                        "windowsConfiguration": {
                            "patchSettings": {
                                "patchMode": "AutomaticByPlatform",
                                "assessmentMode": "AutomaticByPlatform",
                            }
                        }
                    },
                    "storageProfile": {"osDisk": {"osType": "Windows"}},
                    "extended": {
                        "instanceView": {
                            "osName": "Windows Server 2025 Datacenter",
                            "osVersion": "10.0.26100",
                            "powerState": {"code": "PowerState/running"},
                        }
                    },
                },
            },
            {
                "id": arc_sql_id,
                "name": "arc-sql-01",
                "type": "microsoft.hybridcompute/machines",
                "resourceGroup": RG_ARC_SERVERS,
                "location": "westeurope",
                "tags": {"role": "sql"},
                "properties": {
                    "status": "Connected",
                    "osType": "windows",
                    "osName": "windows",
                    "osSku": "Windows Server 2022 Datacenter",
                    "osVersion": "10.0.20348",
                    "agentVersion": "1.61.03319.2737",
                    "lastStatusChange": "2026-10-20T06:09:29.4514228Z",
                    "osProfile": {"windowsConfiguration": {"patchSettings": {"assessmentMode": "AutomaticByPlatform"}}},
                },
            },
            {
                "id": arc_win2k22_id,
                "name": "arc-win2k22-01",
                "type": "microsoft.hybridcompute/machines",
                "resourceGroup": RG_ARC_SERVERS,
                "location": "westeurope",
                "tags": {},
                "properties": {
                    "status": "Connected",
                    "osType": "windows",
                    "osName": "windows",
                    "agentVersion": "1.61.03319.2737",
                    "lastStatusChange": "2026-10-20T06:09:30.9185004Z",
                    "osProfile": {"windowsConfiguration": {"patchSettings": {"assessmentMode": "AutomaticByPlatform"}}},
                },
            },
            {
                "id": arc_ubuntu01_id,
                "name": "arc-ubuntu-01",
                "type": "microsoft.hybridcompute/machines",
                "resourceGroup": RG_ARC_SERVERS,
                "location": "westeurope",
                "tags": {},
                "properties": {
                    "status": "Connected",
                    "osType": "linux",
                    "osName": "linux",
                    "osSku": "Ubuntu 24.04 LTS",
                    "agentVersion": "1.61.03319.859",
                    "lastStatusChange": "2026-10-20T06:07:35.4441926Z",
                    "osProfile": {"linuxConfiguration": {"patchSettings": {"assessmentMode": "AutomaticByPlatform"}}},
                },
            },
            {
                "id": arc_ubuntu02_id,
                "name": "arc-ubuntu-02",
                "type": "microsoft.hybridcompute/machines",
                "resourceGroup": RG_ARC_SERVERS,
                "location": "westeurope",
                "tags": {},
                "properties": {
                    "status": "Connected",
                    "osType": "linux",
                    "osName": "linux",
                    "osSku": "Ubuntu 24.04 LTS",
                    "agentVersion": "1.61.03319.859",
                    "lastStatusChange": "2026-10-20T12:07:51.803Z",
                    "osProfile": {"linuxConfiguration": {"patchSettings": {"assessmentMode": "AutomaticByPlatform"}}},
                },
            },
            {
                "id": arc_expired_id,
                "name": "vm-arc-win-01",
                "type": "microsoft.hybridcompute/machines",
                "resourceGroup": RG_ONPREM,
                "location": "westeurope",
                "tags": {},
                "properties": {
                    "status": "Expired",
                    "osType": "windows",
                    "osName": "windows",
                    "agentVersion": "1.61.03319.2737",
                    "lastStatusChange": "2026-06-09T10:42:11.9729735Z",
                },
            },
            {
                "id": vm_failed_ext_id,
                "name": "vm-arc-win-04",
                "type": "microsoft.compute/virtualmachines",
                "resourceGroup": RG_ONPREM,
                "location": "westeurope",
                "tags": {},
                "properties": {
                    "storageProfile": {"osDisk": {"osType": "Windows"}},
                    "osProfile": {"windowsConfiguration": {"patchSettings": {"patchMode": "AutomaticByPlatform", "assessmentMode": "ImageDefault"}}},
                    "extended": {"instanceView": {"powerState": {"code": "PowerState/deallocated"}}},
                },
            },
            {
                "id": vm_unassessed_id,
                "name": "vm-linux-01",
                "type": "microsoft.compute/virtualmachines",
                "resourceGroup": RG_AUTO,
                "location": "francecentral",
                "tags": {},
                "properties": {
                    "storageProfile": {"osDisk": {"osType": "Linux"}},
                    "osProfile": {"linuxConfiguration": {"patchSettings": {"patchMode": "AutomaticByPlatform", "assessmentMode": "AutomaticByPlatform"}}},
                    "extended": {"instanceView": {"powerState": {"code": "PowerState/deallocated"}}},
                },
            },
            {
                "id": vm_healthy_id,
                "name": "vm-healthy-01",
                "type": "microsoft.compute/virtualmachines",
                "resourceGroup": RG_ARC_SERVERS,
                "location": "westeurope",
                "tags": {},
                "properties": {
                    "storageProfile": {"osDisk": {"osType": "Linux"}},
                    "osProfile": {"linuxConfiguration": {"patchSettings": {"patchMode": "AutomaticByPlatform", "assessmentMode": "AutomaticByPlatform"}}},
                    "extended": {"instanceView": {"powerState": {"code": "PowerState/running"}}},
                },
            },
        ],
        "arg_patch_assessments": [
            {
                "id": host_vm_id + "/patchAssessmentResults/latest",
                "name": "00000000-0000-0000-0000-0000000000c1",
                "type": "microsoft.compute/virtualmachines/patchassessmentresults",
                "resourceGroup": RG_ARC_SERVERS,
                "location": "westeurope",
                "properties": {
                    "assessmentActivityId": "00000000-0000-0000-0000-0000000000c1",
                    "status": "Succeeded",
                    "rebootPending": False,
                    "startDateTime": "2026-10-20T14:53:04.956Z",
                    "lastModifiedDateTime": "2026-10-20T14:53:58.746Z",
                    "availablePatchCountByClassification": {
                        "critical": 0,
                        "definition": 1,
                        "featurePack": 0,
                        "security": 0,
                        "servicePack": 0,
                        "tools": 0,
                        "updateRollup": 1,
                        "updates": 0,
                    },
                    "configurationStatus": {
                        "assessmentModeConfiguration": {"status": "Ready"},
                        "patchModeConfiguration": {"status": "Ready"},
                        "vmGuestPatchReadiness": {"detectedVMGuestPatchSupportState": "Supported"},
                        "lastModifiedTime": "2026-10-20T14:53:58.781Z",
                    },
                    "errorDetails": {"code": "Success", "details": [], "message": "0 error/s reported"},
                    "hotpatchStatus": {
                        "hotpatchEnablementStatus": "Disabled",
                        "hotpatchReadinessStatus": "EnablementRequired",
                        "lastRefreshedTime": "2026-10-20T14:53:23.848Z",
                        "error": {
                            "code": "Error",
                            "details": [
                                {
                                    "code": "HotpatchEnablementRequiredForReadiness",
                                    "message": '"[Hotpatching must be enabled for the VM to be hotpatch ready.]."',
                                }
                            ],
                            "message": '"1 errors reported. The latest 3 errors are shared in details. To view all errors, review this log file on the machine:[C:\\WindowsAzure\\Logs\\Plugins\\Microsoft.CPlat.Core.WindowsPatchExtension\\1.5.85]',
                        },
                    },
                },
            },
            {
                "id": arc_sql_id + "/patchAssessmentResults/latest",
                "name": "ass-sql-latest",
                "type": "microsoft.hybridcompute/machines/patchassessmentresults",
                "resourceGroup": RG_ARC_SERVERS,
                "location": "westeurope",
                "properties": {
                    "status": "Succeeded",
                    "rebootPending": False,
                    "startDateTime": "2026-10-19T15:58:53.437078Z",
                    "lastModifiedDateTime": "2026-10-19T15:59:01.2909821Z",
                    "availablePatchCountByClassification": {
                        "critical": 0,
                        "definition": 1,
                        "security": 3,
                        "updateRollup": 1,
                        "updates": 2,
                    },
                    "configurationStatus": {
                        "assessmentModeConfiguration": {"status": "Ready"},
                        "patchModeConfiguration": {"status": "Unknown"},
                        "vmGuestPatchReadiness": {"detectedVMGuestPatchSupportState": "Supported"},
                        "lastModifiedDateTime": "2026-03-02T16:01:31.0454482Z",
                    },
                    "errorDetails": {"code": "Success", "details": [], "message": "0 error/s reported"},
                },
            },
            {
                "id": arc_win2k22_id + "/patchAssessmentResults/latest",
                "name": "ass-win22-latest",
                "type": "microsoft.hybridcompute/machines/patchassessmentresults",
                "resourceGroup": RG_ARC_SERVERS,
                "location": "westeurope",
                "properties": {
                    "status": "Succeeded",
                    "rebootPending": False,
                    "startDateTime": "2026-10-20T06:01:43.9012262Z",
                    "lastModifiedDateTime": "2026-10-20T06:02:14.7476553Z",
                    "availablePatchCountByClassification": {
                        "critical": 0,
                        "definition": 1,
                        "security": 2,
                        "updateRollup": 1,
                        "updates": 2,
                    },
                    "configurationStatus": {
                        "assessmentModeConfiguration": {"status": "Ready"},
                        "patchModeConfiguration": {"status": "Unknown"},
                        "vmGuestPatchReadiness": {"detectedVMGuestPatchSupportState": "Supported"},
                    },
                },
            },
            {
                "id": arc_ubuntu01_id + "/patchAssessmentResults/latest",
                "name": "ass-ubuntu01-latest",
                "type": "microsoft.hybridcompute/machines/patchassessmentresults",
                "resourceGroup": RG_ARC_SERVERS,
                "location": "westeurope",
                "properties": {
                    "status": "InProgress",
                    "rebootPending": False,
                    "startDateTime": "2026-10-20T06:02:08Z",
                    "lastModifiedDateTime": "2026-10-20T06:02:14Z",
                    "availablePatchCountByClassification": {"other": 105, "security": 2},
                    "configurationStatus": {
                        "assessmentModeConfiguration": {"status": "Ready"},
                        "patchModeConfiguration": {"status": "Unknown"},
                        "vmGuestPatchReadiness": {"detectedVMGuestPatchSupportState": "UnableToDetermine"},
                        "lastModifiedDateTime": "2026-09-01T06:19:54Z",
                    },
                },
            },
            {
                "id": arc_ubuntu02_id + "/patchAssessmentResults/latest",
                "name": "ass-ubuntu02-latest",
                "type": "microsoft.hybridcompute/machines/patchassessmentresults",
                "resourceGroup": RG_ARC_SERVERS,
                "location": "westeurope",
                "properties": {
                    "status": "InProgress",
                    "rebootPending": False,
                    "startDateTime": "2026-10-20T06:02:08Z",
                    "lastModifiedDateTime": "2026-10-20T06:02:13Z",
                    "availablePatchCountByClassification": {"other": 105, "security": 2},
                    "configurationStatus": {
                        "assessmentModeConfiguration": {"status": "Ready"},
                        "patchModeConfiguration": {"status": "Unknown"},
                        "vmGuestPatchReadiness": {"detectedVMGuestPatchSupportState": "UnableToDetermine"},
                        "lastModifiedDateTime": "2026-09-11T06:22:39Z",
                    },
                },
            },
            {
                "id": vm_healthy_id + "/patchAssessmentResults/latest",
                "name": "ass-healthy-latest",
                "type": "microsoft.compute/virtualmachines/patchassessmentresults",
                "resourceGroup": RG_ARC_SERVERS,
                "location": "westeurope",
                "properties": {
                    "status": "Succeeded",
                    "rebootPending": False,
                    "startDateTime": "2026-10-20T08:00:00Z",
                    "lastModifiedDateTime": "2026-10-20T08:01:00Z",
                    "availablePatchCountByClassification": {"security": 0, "critical": 0, "updateRollup": 0, "other": 0},
                    "configurationStatus": {
                        "assessmentModeConfiguration": {"status": "Ready"},
                        "patchModeConfiguration": {"status": "Ready"},
                        "vmGuestPatchReadiness": {"detectedVMGuestPatchSupportState": "Supported"},
                    },
                },
            },
        ],
        "arg_software_patches_pending": [
            {
                "id": host_vm_id + "/patchAssessmentResults/latest/softwarePatches/2",
                "name": "2",
                "type": "microsoft.compute/virtualmachines/patchassessmentresults/softwarepatches",
                "resourceGroup": RG_ARC_SERVERS,
                "properties": {
                    "classifications": ["UpdateRollUp"],
                    "kbId": "890830",
                    "patchId": "00000000-0000-0000-0000-0000000000d2",
                    "patchName": "Windows Malicious Software Removal Tool x64 - v5.146 (KB890830)",
                    "publishedDateTime": "2026-10-13T00:00:00Z",
                    "lastModifiedDateTime": "2026-10-20T14:53:58.746Z",
                    "rebootBehavior": "CanRequestReboot",
                },
            },
            {
                "id": arc_sql_id + "/patchAssessmentResults/latest/softwarePatches/2",
                "name": "2",
                "type": "microsoft.hybridcompute/machines/patchassessmentresults/softwarepatches",
                "resourceGroup": RG_ARC_SERVERS,
                "properties": {
                    "classifications": ["Security"],
                    "kbId": "5128493",
                    "msrcSeverity": "Important",
                    "patchId": "00000000-0000-0000-0000-0000000000d3",
                    "patchName": "Security Update for SQL Server 2022 RTM GDR (KB5128493)",
                    "publishedDateTime": "2026-10-13T07:00:00Z",
                    "lastModifiedDateTime": "2026-10-19T15:59:01.2909821Z",
                    "rebootBehavior": "CanRequestReboot",
                },
            },
            {
                "id": arc_sql_id + "/patchAssessmentResults/latest/softwarePatches/4",
                "name": "4",
                "type": "microsoft.hybridcompute/machines/patchassessmentresults/softwarepatches",
                "resourceGroup": RG_ARC_SERVERS,
                "properties": {
                    "classifications": ["Security"],
                    "kbId": "5128928",
                    "msrcSeverity": "Important",
                    "patchId": "00000000-0000-0000-0000-0000000000d4",
                    "patchName": "2026-10 Cumulative Update for .NET Framework 3.5, 4.8 and 4.8.1 (KB5128928)",
                    "publishedDateTime": "2026-10-13T07:00:00Z",
                    "lastModifiedDateTime": "2026-10-19T15:59:01.2909821Z",
                    "rebootBehavior": "CanRequestReboot",
                },
            },
            {
                "id": arc_ubuntu01_id + "/patchAssessmentResults/latest/softwarePatches/1",
                "name": "1",
                "type": "microsoft.hybridcompute/machines/patchassessmentresults/softwarepatches",
                "resourceGroup": RG_ARC_SERVERS,
                "properties": {
                    "classifications": ["Security"],
                    "patchId": "git_1_2.43.0-1ubuntu7.4_Ubuntu_24.04",
                    "patchName": "git",
                    "version": "1:2.43.0-1ubuntu7.4",
                    "lastModifiedDateTime": "2026-10-20T06:02:14Z",
                },
            },
        ],
        "arg_patch_installations": [
            {
                "id": host_vm_id + "/patchInstallationResults/00000000-0000-0000-0000-0000000000c1",
                "name": "00000000-0000-0000-0000-0000000000c1",
                "type": "microsoft.compute/virtualmachines/patchinstallationresults",
                "resourceGroup": RG_ARC_SERVERS,
                "location": "westeurope",
                "properties": {
                    "status": "Succeeded",
                    "startDateTime": "2026-10-20T14:53:04.956Z",
                    "lastModifiedDateTime": "2026-10-20T14:53:58.746Z",
                    "installedPatchCount": 2,
                    "failedPatchCount": 0,
                    "pendingPatchCount": 0,
                    "notSelectedPatchCount": 1,
                    "maintenanceWindowExceeded": False,
                    "rebootStatus": "NotNeeded",
                    "maintenanceRunId": maint_conf_weekly + "/providers/microsoft.maintenance/applyupdates/20261020145000",
                    "errorDetails": {"code": "Success", "details": [], "message": "0 error/s reported"},
                },
            },
            {
                "id": host_vm_id + "/patchInstallationResults/00000000-0000-0000-0000-0000000000c2",
                "name": "00000000-0000-0000-0000-0000000000c2",
                "type": "microsoft.compute/virtualmachines/patchinstallationresults",
                "resourceGroup": RG_ARC_SERVERS,
                "location": "westeurope",
                "properties": {
                    "status": "Succeeded",
                    "startDateTime": "2026-10-14T08:52:52.277Z",
                    "lastModifiedDateTime": "2026-10-14T09:45:01.931Z",
                    "installedPatchCount": 5,
                    "failedPatchCount": 0,
                    "pendingPatchCount": 0,
                    "notSelectedPatchCount": 1,
                    "maintenanceWindowExceeded": False,
                    "rebootStatus": "Completed",
                    "maintenanceRunId": maint_conf_weekly + "/providers/microsoft.maintenance/applyupdates/20261014085000",
                    "errorDetails": {"code": "Success", "details": [], "message": "0 error/s reported"},
                },
            },
        ],
        "arg_software_patches_installed": [
            {
                "id": host_vm_id + "/patchInstallationResults/00000000-0000-0000-0000-0000000000c1/softwarePatches/00000000-0000-0000-0000-0000000000d1",
                "name": "00000000-0000-0000-0000-0000000000d1",
                "type": "microsoft.compute/virtualmachines/patchinstallationresults/softwarepatches",
                "resourceGroup": RG_ARC_SERVERS,
                "properties": {
                    "classifications": ["Definition"],
                    "installationState": "Installed",
                    "kbId": "2267602",
                    "patchName": "Security Intelligence Update for Microsoft Defender Antivirus - KB2267602",
                    "lastModifiedDateTime": "2026-10-20T14:53:58.746Z",
                    "publishedDateTime": "0001-01-01T00:00:00Z",
                    "rebootBehavior": "NeverReboots",
                    "rebootRequired": False,
                },
            },
            {
                "id": host_vm_id + "/patchInstallationResults/00000000-0000-0000-0000-0000000000c1/softwarePatches/00000000-0000-0000-0000-0000000000d2",
                "name": "00000000-0000-0000-0000-0000000000d2",
                "type": "microsoft.compute/virtualmachines/patchinstallationresults/softwarepatches",
                "resourceGroup": RG_ARC_SERVERS,
                "properties": {
                    "classifications": ["UpdateRollUp"],
                    "installationState": "NotSelected",
                    "kbId": "890830",
                    "patchName": "Windows Malicious Software Removal Tool x64 - v5.146 (KB890830)",
                    "lastModifiedDateTime": "2026-10-20T14:53:58.746Z",
                    "publishedDateTime": "0001-01-01T00:00:00Z",
                    "rebootBehavior": "NeverReboots",
                    "rebootRequired": False,
                },
            },
        ],
        "arg_maintenance_cycles": [
            {
                "id": host_vm_id + "/providers/Microsoft.Maintenance/applyUpdates/20261019205000_1012413953",
                "name": "20261019205000_1012413953",
                "type": "microsoft.maintenance/applyupdates",
                "resourceGroup": RG_ARC_SERVERS,
                "location": "westeurope",
                "properties": {
                    "correlationId": maint_conf_weekly + "/providers/microsoft.maintenance/applyupdates/20261019205000",
                    "maintenanceConfigurationId": maint_conf_weekly,
                    "maintenanceScope": "InGuestPatch",
                    "resourceId": host_vm_id,
                    "startDateTime": "2026-10-19T20:50:00Z",
                    "endDateTime": "2026-10-19T23:20:00Z",
                    "status": "ShutdownOrUnresponsive",
                },
            },
            {
                "id": host_vm_id + "/providers/Microsoft.Maintenance/applyUpdates/20261020145000_2619246425",
                "name": "20261020145000_2619246425",
                "type": "microsoft.maintenance/applyupdates",
                "resourceGroup": RG_ARC_SERVERS,
                "location": "westeurope",
                "properties": {
                    "correlationId": maint_conf_weekly + "/providers/microsoft.maintenance/applyupdates/20261020145000",
                    "maintenanceConfigurationId": maint_conf_weekly,
                    "maintenanceScope": "InGuestPatch",
                    "resourceId": host_vm_id,
                    "startDateTime": "2026-10-20T14:50:00Z",
                    "endDateTime": "2026-10-20T14:58:49.4497796Z",
                    "status": "UpdateSuccessfullyApplied",
                },
            },
            {
                "id": host_vm_id + "/providers/Microsoft.Maintenance/configurationAssignments/vm-arc-host-weu",
                "name": "vm-arc-host-weu",
                "type": "microsoft.maintenance/configurationassignments",
                "resourceGroup": RG_ARC_SERVERS,
                "location": "westeurope",
                "properties": {
                    "maintenanceConfigurationId": maint_conf_weekly,
                    "resourceId": host_vm_id,
                },
            },
            {
                "id": maint_conf_win + "/providers/microsoft.maintenance/applyupdates/20261018000000",
                "name": "20261018000000",
                "type": "microsoft.maintenance/maintenanceconfigurations/applyupdates",
                "resourceGroup": RG_ARC_SERVERS,
                "location": "westeurope",
                "properties": {
                    "correlationId": maint_conf_win + "/providers/microsoft.maintenance/applyupdates/20261018000000",
                    "maintenanceConfigurationId": maint_conf_win,
                    "startDateTime": "2026-10-18T00:00:00Z",
                    "endDateTime": "2026-10-18T03:00:00Z",
                    "status": "Succeeded",
                    "maintenanceConfiguration": {
                        "name": "mc-windows-monthly",
                        "tags": {"SafetyMode": "Unassigned-NoPatchExecution"},
                        "properties": {
                            "maintenanceScope": "InGuestPatch",
                            "maintenanceWindow": {
                                "recurEvery": "Week Sunday",
                                "duration": "03:00",
                                "timeZone": "Romance Standard Time",
                            },
                        },
                    },
                },
            },
        ],
        "arg_patch_extensions": [
            {
                "id": host_vm_id + "/extensions/AzurePolicyforWindows",
                "name": "AzurePolicyforWindows",
                "type": "microsoft.compute/virtualmachines/extensions",
                "resourceGroup": RG_ARC_SERVERS,
                "location": "westeurope",
                "properties": {
                    "publisher": "Microsoft.GuestConfiguration",
                    "type": "ConfigurationforWindows",
                    "typeHandlerVersion": "1.1",
                    "provisioningState": "Succeeded",
                    "autoUpgradeMinorVersion": True,
                    "enableAutomaticUpgrade": True,
                },
            },
            {
                "id": vm_failed_ext_id + "/extensions/MDE.Windows",
                "name": "MDE.Windows",
                "type": "microsoft.compute/virtualmachines/extensions",
                "resourceGroup": RG_ONPREM,
                "location": "westeurope",
                "properties": {
                    "publisher": "Microsoft.Azure.AzureDefenderForServers",
                    "type": "MDE.Windows",
                    "typeHandlerVersion": "1.0",
                    "provisioningState": "Failed",
                    "autoUpgradeMinorVersion": True,
                    "enableAutomaticUpgrade": None,
                },
            },
            {
                "id": arc_sql_id + "/extensions/ChangeTracking-Windows",
                "name": "ChangeTracking-Windows",
                "type": "microsoft.hybridcompute/machines/extensions",
                "resourceGroup": RG_ARC_SERVERS,
                "location": "westeurope",
                "properties": {
                    "publisher": "Microsoft.Azure.ChangeTrackingAndInventory",
                    "type": "ChangeTracking-Windows",
                    "typeHandlerVersion": "2.35.0.0",
                    "provisioningState": "Succeeded",
                    "autoUpgradeMinorVersion": True,
                    "enableAutomaticUpgrade": True,
                },
            },
        ],
    }


def fixture(module, period="last_30d"):
    config = module.validate_config()
    raw_tables = raw_arg_fixture()
    sources = [
        {
            "id": sid,
            "source_id": sid,
            "endpoint": "POST https://management.azure.com/providers/Microsoft.ResourceGraph/resources?api-version=2022-10-01",
            "subscription_id": config["subscription_id"],
            "status": "complete",
            "pages": 1,
            "records": len(raw_tables[sid]),
            "observed_at": REFERENCE,
            "note": "Read-only Azure Resource Graph query (" + sid + ").",
            "errors": [],
        }
        for sid in module.SOURCE_IDS
    ]
    return module.normalize_collected(raw_tables, sources, config, period, REFERENCE)

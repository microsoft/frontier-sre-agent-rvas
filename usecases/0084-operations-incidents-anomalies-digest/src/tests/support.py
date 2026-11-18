"""Shared synthetic test support for Case 10; never imported by runtime tool."""

import base64
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REFERENCE = "2026-10-20T18:00:00Z"
SUBSCRIPTION = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
TENANT = "11111111-1111-4111-8111-111111111111"
CLIENT_ID = "12345678-1234-4abc-8def-123456789abc"

WORKSPACES = [
    {
        "name": "law-arc-servers-weu",
        "customer_id": "00000000-0000-0000-0000-0000000000a1",
        "resource_group": "rg-arc-servers-weu",
    },
    {
        "name": "law-demo0000000000",
        "customer_id": "00000000-0000-0000-0000-0000000000a2",
        "resource_group": "rg-sre-agent-poc",
    },
    {
        "name": "law-hybrid-weu",
        "customer_id": "00000000-0000-0000-0000-0000000000a3",
        "resource_group": "rg-hybrid-weu",
    },
    {
        "name": "law-monitoring-weu",
        "customer_id": "00000000-0000-0000-0000-0000000000a4",
        "resource_group": "rg-monitoring-weu",
    },
]


def make_jwt(tid, appid, aud):
    header = base64.urlsafe_b64encode(b'{"alg":"RS256","typ":"JWT"}').decode("ascii").rstrip("=")
    payload = base64.urlsafe_b64encode(json.dumps({"tid": tid, "appid": appid, "aud": aud}).encode("utf-8")).decode("ascii").rstrip("=")
    return header + "." + payload + ".signature"


def load_engine(standalone=False):
    target = (ROOT.parent / "manifests" / "tools" / "generate-operations-digest-report.py" if standalone else ROOT / "engine.py")
    spec = importlib.util.spec_from_file_location("ops_digest_engine_test", target)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not standalone:
        module.HTML_TEMPLATE = (ROOT / "report_template.html").read_text(encoding="utf-8")
    module.SUBSCRIPTION_ID = SUBSCRIPTION
    module.MANAGED_IDENTITY_CLIENT_ID = CLIENT_ID
    module.APPROVED_LOG_WORKSPACES = [dict(ws) for ws in WORKSPACES]
    return module


def fixture(module, period="previous_month"):
    window = module.compute_window(period, REFERENCE)
    arc_id = (
        "/subscriptions/" + SUBSCRIPTION + "/resourceGroups/rg-arc-servers-weu"
        + "/providers/Microsoft.HybridCompute/machines/arc-win2k25-01"
    )
    aks_id = (
        "/subscriptions/" + SUBSCRIPTION + "/resourceGroups/rg-arc-servers-weu"
        + "/providers/Microsoft.ContainerService/managedClusters/aks-demo-weu"
    )
    vm_id = (
        "/subscriptions/" + SUBSCRIPTION + "/resourceGroups/rg-monitoring-weu"
        + "/providers/Microsoft.Compute/virtualMachines/vm-obs-app-01"
    )
    kv_id = (
        "/subscriptions/" + SUBSCRIPTION + "/resourceGroups/rg-monitoring-weu"
        + "/providers/Microsoft.KeyVault/vaults/kv-obs-weu-01"
    )

    alerts = [
        module.normalize_alert_row(
            {
                "id": "/subscriptions/" + SUBSCRIPTION + "/providers/Microsoft.AlertsManagement/alerts/alr-001",
                "name": "alr-001",
                "severity": "Sev1",
                "alertState": "New",
                "monitorCondition": "Fired",
                "signalType": "Metric",
                "monitorService": "Platform",
                "targetResource": vm_id,
                "targetResourceName": "vm-obs-app-01",
                "targetResourceGroup": "rg-monitoring-weu",
                "targetResourceType": "microsoft.compute/virtualmachines",
                "startDateTime": "2026-09-18T14:20:00Z",
                "lastModifiedDateTime": "2026-09-18T14:35:00Z",
                "description": "Percentage CPU exceeded the 90% threshold for 15 minutes on vm-obs-app-01.",
            },
            SUBSCRIPTION,
            window,
            REFERENCE,
        ),
        module.normalize_alert_row(
            {
                "id": "/subscriptions/" + SUBSCRIPTION + "/providers/Microsoft.AlertsManagement/alerts/alr-002",
                "name": "alr-002",
                "severity": "Sev2",
                "alertState": "Acknowledged",
                "monitorCondition": "Fired",
                "signalType": "Log",
                "monitorService": "Log Analytics",
                "targetResource": arc_id,
                "targetResourceName": "arc-win2k25-01",
                "targetResourceGroup": "rg-arc-servers-weu",
                "targetResourceType": "microsoft.hybridcompute/machines",
                "startDateTime": "2026-09-22T09:10:00Z",
                "lastModifiedDateTime": "2026-09-22T09:25:00Z",
                "description": "Recurring provisioning failure of the MDE.Windows security extension on arc-win2k25-01.",
            },
            SUBSCRIPTION,
            window,
            REFERENCE,
        ),
    ]
    alerts = [a for a in alerts if a is not None]

    service_health = [
        module.normalize_service_health_row(
            {
                "id": "/subscriptions/" + SUBSCRIPTION + "/providers/Microsoft.ResourceHealth/events/1VL8-9TZ",
                "name": "1VL8-9TZ",
                "properties": {
                    "eventType": "PlannedMaintenance",
                    "status": "Active",
                    "title": "Planned network maintenance in West Europe",
                    "level": "Informational",
                    "impactStartTime": "2026-09-25T01:00:00Z",
                    "lastUpdateTime": "2026-09-25T05:00:00Z",
                    "summary": "Scheduled update of the regional network plane in West Europe, with no interruption expected.",
                    "impact": [
                        {
                            "impactedService": "Virtual Machines",
                            "impactedRegions": [{"impactedRegion": "West Europe"}],
                        }
                    ],
                },
            },
            SUBSCRIPTION,
            window,
            REFERENCE,
        )
    ]
    service_health = [s for s in service_health if s is not None]

    estate_resources = [
        module.normalize_estate_resource(
            {
                "id": arc_id,
                "name": "arc-win2k25-01",
                "type": "microsoft.hybridcompute/machines",
                "resourceGroup": "rg-arc-servers-weu",
                "location": "westeurope",
                "tags": {"environment": "demo", "secret_token": "DO-NOT-EXPORT"},
                "provisioningState": "Succeeded",
                "arcStatus": "Expired",
                "arcAgentVersion": "1.59.03197.289",
                "arcLastStatusChange": "2026-09-12T10:15:00Z",
                "osName": "windows",
                "osSku": "Windows Server 2025 Datacenter",
                "osVersion": "10.0.26100",
            },
            SUBSCRIPTION,
            REFERENCE,
        ),
        module.normalize_estate_resource(
            {
                "id": aks_id,
                "name": "aks-demo-weu",
                "type": "microsoft.containerservice/managedclusters",
                "resourceGroup": "rg-arc-servers-weu",
                "location": "westeurope",
                "skuName": "Base",
                "tags": {"workload": "containers"},
                "provisioningState": "Succeeded",
                "powerState": "Stopped",
                "kubernetesVersion": "1.30.4",
            },
            SUBSCRIPTION,
            REFERENCE,
        ),
        module.normalize_estate_resource(
            {
                "id": vm_id,
                "name": "vm-obs-app-01",
                "type": "microsoft.compute/virtualmachines",
                "resourceGroup": "rg-monitoring-weu",
                "location": "westeurope",
                "tags": {"owner": "ops-team"},
                "provisioningState": "Succeeded",
                "powerState": "PowerState/running",
                "osName": "Linux",
                "vmSize": "Standard_D4s_v5",
            },
            SUBSCRIPTION,
            REFERENCE,
        ),
        module.normalize_estate_resource(
            {
                "id": kv_id,
                "name": "kv-obs-weu-01",
                "type": "microsoft.keyvault/vaults",
                "resourceGroup": "rg-monitoring-weu",
                "location": "westeurope",
                "skuName": "standard",
                "tags": {},
                "provisioningState": "Succeeded",
            },
            SUBSCRIPTION,
            REFERENCE,
        ),
    ]

    extensions = [
        module.normalize_extension_row(
            {
                "id": arc_id + "/extensions/MDE.Windows",
                "name": "MDE.Windows",
                "type": "microsoft.hybridcompute/machines/extensions",
                "resourceGroup": "rg-arc-servers-weu",
                "location": "westeurope",
                "publisher": "Microsoft.EnterpriseCloud.Monitoring",
                "extType": "MDE.Windows",
                "version": "1.0.10.0",
                "provisioningState": "Failed",
                "enableAutomaticUpgrade": True,
                "autoUpgradeMinorVersion": True,
            },
            SUBSCRIPTION,
            REFERENCE,
        ),
        module.normalize_extension_row(
            {
                "id": arc_id + "/extensions/AADLoginForWindows",
                "name": "AADLoginForWindows",
                "type": "microsoft.hybridcompute/machines/extensions",
                "resourceGroup": "rg-arc-servers-weu",
                "location": "westeurope",
                "publisher": "Microsoft.Azure.ActiveDirectory",
                "extType": "AADLoginForWindows",
                "version": "2.2.0.0",
                "provisioningState": "Failed",
                "enableAutomaticUpgrade": True,
                "autoUpgradeMinorVersion": True,
            },
            SUBSCRIPTION,
            REFERENCE,
        ),
        module.normalize_extension_row(
            {
                "id": vm_id + "/extensions/AzureMonitorLinuxAgent",
                "name": "AzureMonitorLinuxAgent",
                "type": "microsoft.compute/virtualmachines/extensions",
                "resourceGroup": "rg-monitoring-weu",
                "location": "westeurope",
                "publisher": "Microsoft.Azure.Monitor",
                "extType": "AzureMonitorLinuxAgent",
                "version": "1.33.2",
                "provisioningState": "Succeeded",
                "enableAutomaticUpgrade": True,
                "autoUpgradeMinorVersion": True,
            },
            SUBSCRIPTION,
            REFERENCE,
        ),
    ]

    raw_tel_rows = [
        {
            "_ResourceId": vm_id.lower(),
            "metric_key": "cpu_percent",
            "unit": "Percent",
            "avg_val": 88.4,
            "max_val": 97.6,
            "min_val": 42.1,
            "median_val": 54.0,
            "p95_val": 94.2,
            "high_bins": 6,
            "low_mem_bins": 0,
            "low_disk_bins": 0,
            "bins_total": 24,
            "sample_count": 1440,
            "last_seen_utc": "2026-09-28T16:00:00Z",
        },
        {
            "_ResourceId": vm_id.lower(),
            "metric_key": "memory_available_mb",
            "unit": "MB",
            "avg_val": 640.0,
            "max_val": 2048.0,
            "min_val": 210.0,
            "median_val": 720.0,
            "p95_val": 1500.0,
            "high_bins": 0,
            "low_mem_bins": 4,
            "low_disk_bins": 0,
            "bins_total": 24,
            "sample_count": 1440,
            "last_seen_utc": "2026-09-28T16:00:00Z",
        },
        {
            "_ResourceId": arc_id.lower(),
            "metric_key": "heartbeat_silence_minutes",
            "unit": "Minutes",
            "avg_val": 120.0,
            "max_val": 1440.0,
            "min_val": 0.0,
            "median_val": 0.0,
            "p95_val": 0.0,
            "high_bins": 1,
            "low_mem_bins": 0,
            "low_disk_bins": 0,
            "bins_total": 120,
            "sample_count": 120,
            "last_seen_utc": "2026-09-12T10:15:00Z",
        },
    ]

    telemetry_anomalies = []
    telemetry_summaries = []
    for r in raw_tel_rows:
        ws_name = "law-monitoring-weu" if "vm-obs" in r["_ResourceId"] else "law-arc-servers-weu"
        telemetry_summaries.append({
            "workspace_name": ws_name,
            "resource_id": r["_ResourceId"],
            "metric_key": r["metric_key"],
            "avg_val": r["avg_val"],
            "max_val": r["max_val"],
            "min_val": r["min_val"],
            "median_val": r["median_val"],
            "sample_count": r["sample_count"],
        })
        anom = module.evaluate_telemetry_row(r, ws_name, SUBSCRIPTION, window, REFERENCE)
        if anom is not None:
            telemetry_anomalies.append(anom)

    advisor = [
        module.normalize_advisor_row(
            {
                "id": vm_id + "/providers/Microsoft.Advisor/recommendations/rec-ha-001",
                "name": "rec-ha-001",
                "properties": {
                    "category": "HighAvailability",
                    "impact": "High",
                    "impactedValue": "vm-obs-app-01",
                    "lastUpdated": "2026-09-29T08:00:00Z",
                    "resourceMetadata": {"resourceId": vm_id},
                    "shortDescription": {
                        "problem": "Enable zone redundancy or Azure Backup to protect critical virtual machines.",
                        "solution": "Configure regular backups in a Recovery Services vault and evaluate multi-zone availability.",
                    },
                },
            },
            SUBSCRIPTION,
            REFERENCE,
        )
    ]

    sources = [
        module.source_receipt("arg_alerts_incidents", REFERENCE, "complete", records=len(alerts), pages=1, window=window),
        module.source_receipt("arm_service_health", REFERENCE, "complete", records=len(service_health), pages=1, window=window),
        module.source_receipt("arg_posture_anomalies", REFERENCE, "complete", records=len(estate_resources), pages=1, window=window),
        module.source_receipt("arg_guest_extensions", REFERENCE, "complete", records=len(extensions), pages=1, window=window),
        module.source_receipt(
            "logs_telemetry_anomalies",
            REFERENCE,
            "complete",
            records=len(raw_tel_rows),
            pages=len(WORKSPACES),
            window=window,
            workspaces_queried=[
                {"workspace_name": w["name"], "customer_id": w["customer_id"], "status": "complete", "records": 1}
                for w in WORKSPACES
            ],
        ),
        module.source_receipt("arm_advisor_recommendations", REFERENCE, "complete", records=len(advisor), pages=1, window=window),
    ]

    return {
        "subscription_id": SUBSCRIPTION,
        "alerts": alerts,
        "service_health": service_health,
        "estate_resources": estate_resources,
        "extensions": extensions,
        "telemetry_anomalies": telemetry_anomalies,
        "telemetry_summaries": telemetry_summaries,
        "advisor": advisor,
        "sources": sources,
    }

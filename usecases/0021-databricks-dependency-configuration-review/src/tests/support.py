"""Shared synthetic test support for Case 08; never imported by runtime tool."""

import base64
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STANDALONE = ROOT.parent / "manifests" / "tools" / "generate-databricks-dependency-report.py"
REFERENCE = "2026-10-16T12:00:00Z"
SUBSCRIPTION = "11111111-1111-4111-8111-111111111111"
SRE_TENANT = "22222222-2222-4222-8222-222222222222"
TARGET_TENANT = "33333333-3333-4333-8333-333333333333"
CLIENT_ID = "44444444-4444-4444-8444-444444444444"
FEDERATED_APP_ID = "55555555-5555-4555-8555-555555555555"
WORKSPACE_NAME = "dbx-prod-weu-01"
RESOURCE_GROUP = "rg-databricks-prod"
MANAGED_RG = "databricks-rg-dbx-prod-weu-01"
WORKSPACE_HOST = "adb-1234567890123456.7.azuredatabricks.net"
WORKSPACE_ID = (
    "/subscriptions/" + SUBSCRIPTION + "/resourceGroups/" + RESOURCE_GROUP
    + "/providers/Microsoft.Databricks/workspaces/" + WORKSPACE_NAME
)


def make_jwt(tid, appid, aud):
    header = base64.urlsafe_b64encode(b'{"alg":"RS256","typ":"JWT"}').decode("ascii").rstrip("=")
    payload = base64.urlsafe_b64encode(json.dumps({"tid": tid, "appid": appid, "aud": aud}).encode("utf-8")).decode("ascii").rstrip("=")
    return header + "." + payload + ".signature"


def load_engine(standalone=False, cross_tenant=True):
    target = STANDALONE if standalone else ROOT / "engine.py"
    spec = importlib.util.spec_from_file_location("dbx_engine_test", target)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not standalone:
        module.CATALOG = json.loads((ROOT / "rules_catalog.json").read_text(encoding="utf-8"))
        module.HTML_TEMPLATE = (ROOT / "report_template.html").read_text(encoding="utf-8")
    module.SUBSCRIPTION_ID = SUBSCRIPTION
    module.SRE_TENANT_ID = SRE_TENANT
    module.TARGET_TENANT_ID = TARGET_TENANT if cross_tenant else SRE_TENANT
    module.MANAGED_IDENTITY_CLIENT_ID = CLIENT_ID
    module.FEDERATED_APP_CLIENT_ID = FEDERATED_APP_ID
    module.APPROVED_WORKSPACES = {
        WORKSPACE_NAME: {
            "resource_group": RESOURCE_GROUP,
            "workspace_host": WORKSPACE_HOST,
            "environment": "LAB",
            "auth_mode": "cross_tenant_multitenant_fic" if cross_tenant else "same_tenant_uami",
            "workspace_api_enabled": True,
            "unity_catalog_enabled": True,
            "include_managed_resource_group": True,
            "advisor_enabled": True,
            "approved_related_resource_ids": [],
            "approved_cost_resource_ids": [WORKSPACE_ID],
            "cost_scope": "resource_ids",
            "cost_timeframe": "month_to_date",
            "requirements": {
                "premium_required": True,
                "no_public_ip_required": True,
                "vnet_injection_required": True,
                "private_link_required": True,
                "cmk_required": False,
                "enhanced_security_required": False,
            },
        }
    }
    return module


def fixture(module):
    config = module.validate_config(WORKSPACE_NAME)
    vnet_id = "/subscriptions/" + SUBSCRIPTION + "/resourceGroups/" + RESOURCE_GROUP + "/providers/Microsoft.Network/virtualNetworks/vnet-dbx-prod"
    pub_sub_id = vnet_id + "/subnets/snet-dbx-host"
    priv_sub_id = vnet_id + "/subnets/snet-dbx-container"
    nsg_id = "/subscriptions/" + SUBSCRIPTION + "/resourceGroups/" + RESOURCE_GROUP + "/providers/Microsoft.Network/networkSecurityGroups/nsg-dbx-prod"
    ac_id = "/subscriptions/" + SUBSCRIPTION + "/resourceGroups/" + RESOURCE_GROUP + "/providers/Microsoft.Databricks/accessConnectors/ac-dbx-uc-prod"
    uami_id = "/subscriptions/" + SUBSCRIPTION + "/resourceGroups/" + RESOURCE_GROUP + "/providers/Microsoft.ManagedIdentity/userAssignedIdentities/id-dbx-uc-prod"
    st_id = "/subscriptions/" + SUBSCRIPTION + "/resourceGroups/" + RESOURCE_GROUP + "/providers/Microsoft.Storage/storageAccounts/stadlsprod001"
    kv_id = "/subscriptions/" + SUBSCRIPTION + "/resourceGroups/" + RESOURCE_GROUP + "/providers/Microsoft.KeyVault/vaults/kv-dbx-prod-01"
    pe_id = "/subscriptions/" + SUBSCRIPTION + "/resourceGroups/" + RESOURCE_GROUP + "/providers/Microsoft.Network/privateEndpoints/pe-dbx-ui"

    ws = module.normalize_workspace({
        "id": WORKSPACE_ID,
        "name": WORKSPACE_NAME,
        "location": "westeurope",
        "sku": {"name": "premium", "tier": "Paid"},
        "tags": {"environment": "lab-synthetic", "secret_key": "NEVER-EXPORT"},
        "properties": {
            "workspaceId": "1234567890123456",
            "workspaceUrl": WORKSPACE_HOST,
            "provisioningState": "Succeeded",
            "managedResourceGroupId": "/subscriptions/" + SUBSCRIPTION + "/resourceGroups/" + MANAGED_RG,
            "publicNetworkAccess": "Disabled",
            "requiredNsgRules": "NoAzureDatabricksRules",
            "defaultStorageFirewall": "Enabled",
            "defaultCatalog": {"initialType": "UnityCatalog", "initialName": "main_prod"},
            "accessConnector": {
                "id": ac_id,
                "identityType": "UserAssigned",
                "userAssignedIdentityId": uami_id,
            },
            "encryption": {
                "entities": {
                    "managedServices": {
                        "keySource": "Microsoft.Keyvault",
                        "keyVaultProperties": {"keyVaultUri": "https://kv-dbx-prod-01.vault.azure.net/"},
                    },
                    "managedDisk": {
                        "keySource": "Microsoft.Keyvault",
                        "keyVaultProperties": {"keyVaultUri": "https://kv-ext-uncollected.vault.azure.net/"},
                        "rotationToLatestKeyVersionEnabled": True,
                    },
                }
            },
            "enhancedSecurityCompliance": {
                "automaticClusterUpdate": {"value": "Enabled"},
                "enhancedSecurityMonitoring": {"value": "Enabled"},
                "complianceSecurityProfile": {"value": "Disabled", "complianceStandards": []},
            },
            "privateEndpointConnections": [
                {
                    "id": WORKSPACE_ID + "/privateEndpointConnections/pe-conn-1",
                    "name": "pe-conn-1",
                    "properties": {
                        "privateEndpoint": {"id": pe_id},
                        "privateLinkServiceConnectionState": {"status": "Approved"},
                        "groupIds": ["databricks_ui_api"],
                    },
                }
            ],
            "parameters": {
                "enableNoPublicIp": {"value": True},
                "customVirtualNetworkId": {"value": vnet_id},
                "customPublicSubnetName": {"value": "snet-dbx-host"},
                "customPrivateSubnetName": {"value": "snet-dbx-container"},
                "storageAccountName": {"value": "dbstorage777xyz"},
                "storageAccountSkuName": {"value": "Standard_GRS"},
                "prepareEncryption": {"value": True},
                "requireInfrastructureEncryption": {"value": True},
            },
        },
    }, "arm_workspace", REFERENCE, config)

    related = [
        module.normalize_resource({
            "id": vnet_id, "name": "vnet-dbx-prod", "location": "westeurope",
            "properties": {"addressSpace": {"addressPrefixes": ["10.40.0.0/16"]}, "subnets": [{"id": pub_sub_id}, {"id": priv_sub_id}]},
        }, "arm_resource_1", REFERENCE, config, {"type": "direct_reference", "source_id": "arm_workspace", "field": "parameters.customVirtualNetworkId"}),
        module.normalize_resource({
            "id": pub_sub_id, "name": "snet-dbx-host", "location": "westeurope",
            "properties": {"addressPrefix": "10.40.1.0/24", "networkSecurityGroup": {"id": nsg_id}, "delegations": [{"name": "databricks", "properties": {"serviceName": "Microsoft.Databricks/workspaces"}}]},
        }, "arm_resource_2", REFERENCE, config, {"type": "direct_reference", "source_id": "arm_workspace", "field": "parameters.customPublicSubnetName"}),
        module.normalize_resource({
            "id": priv_sub_id, "name": "snet-dbx-container", "location": "westeurope",
            "properties": {"addressPrefix": "10.40.2.0/24", "networkSecurityGroup": {"id": nsg_id}, "delegations": [{"name": "databricks", "properties": {"serviceName": "Microsoft.Databricks/workspaces"}}]},
        }, "arm_resource_3", REFERENCE, config, {"type": "direct_reference", "source_id": "arm_workspace", "field": "parameters.customPrivateSubnetName"}),
        module.normalize_resource({
            "id": nsg_id, "name": "nsg-dbx-prod", "location": "westeurope",
            "properties": {"securityRules": [{"properties": {"priority": 100, "direction": "Inbound", "access": "Allow", "protocol": "Tcp", "sourceAddressPrefix": "VirtualNetwork", "destinationPortRange": "22", "destinationAddressPrefix": "VirtualNetwork"}}]},
        }, "arm_resource_4", REFERENCE, config, {"type": "direct_reference", "source_id": "arm_resource_2", "field": "nsg_id"}),
        module.normalize_resource({
            "id": ac_id, "name": "ac-dbx-uc-prod", "location": "westeurope",
            "identity": {"type": "UserAssigned", "userAssignedIdentities": {uami_id: {}}},
            "properties": {"provisioningState": "Succeeded"},
        }, "arm_resource_5", REFERENCE, config, {"type": "direct_reference", "source_id": "arm_workspace", "field": "accessConnector.id"}),
        module.normalize_resource({
            "id": uami_id, "name": "id-dbx-uc-prod", "location": "westeurope",
            "properties": {"principalId": "66666666-6666-4666-8666-666666666666", "clientId": "77777777-7777-4777-8777-777777777777"},
        }, "arm_resource_6", REFERENCE, config, {"type": "direct_reference", "source_id": "arm_workspace", "field": "accessConnector.userAssignedIdentityId"}),
        module.normalize_resource({
            "id": st_id, "name": "stadlsprod001", "location": "westeurope", "sku": {"name": "Standard_ZRS", "tier": "Standard"},
            "properties": {
                "provisioningState": "Succeeded", "supportsHttpsTrafficOnly": True, "minimumTlsVersion": "TLS1_2",
                "allowBlobPublicAccess": False, "allowSharedKeyAccess": False, "publicNetworkAccess": "Disabled", "isHnsEnabled": True,
                "primaryEndpoints": {"dfs": "https://stadlsprod001.dfs.core.windows.net/", "blob": "https://stadlsprod001.blob.core.windows.net/"},
            },
        }, "arm_resource_7", REFERENCE, config, {"type": "approved_configuration", "source_id": "configuration", "field": "approved_related_resource_ids"}),
        module.normalize_resource({
            "id": kv_id, "name": "kv-dbx-prod-01", "location": "westeurope", "sku": {"name": "standard", "tier": "Standard"},
            "properties": {
                "provisioningState": "Succeeded", "enableRbacAuthorization": True, "enablePurgeProtection": True,
                "enableSoftDelete": True, "softDeleteRetentionInDays": 90, "publicNetworkAccess": "Disabled",
                "vaultUri": "https://kv-dbx-prod-01.vault.azure.net/",
            },
        }, "arm_resource_8", REFERENCE, config, {"type": "direct_reference", "source_id": "dbx_secret_scopes", "field": "keyvault_metadata.resource_id"}),
        module.normalize_resource({
            "id": pe_id, "name": "pe-dbx-ui", "location": "westeurope",
            "properties": {
                "provisioningState": "Succeeded", "subnet": {"id": priv_sub_id},
                "privateLinkServiceConnections": [{"properties": {"privateLinkServiceId": WORKSPACE_ID, "groupIds": ["databricks_ui_api"], "privateLinkServiceConnectionState": {"status": "Approved"}}}],
            },
        }, "arm_resource_9", REFERENCE, config, {"type": "direct_reference", "source_id": "arm_workspace", "field": "privateEndpointConnections"}),
    ]

    clusters = [
        module.normalize_cluster({
            "cluster_id": "0801-111111-inter01",
            "cluster_name": "shared-interactive-analytics",
            "cluster_source": "UI",
            "state": "TERMINATED",
            "spark_version": "15.4.x-scala2.12-lts",
            "node_type_id": "Standard_DS3_v2",
            "driver_node_type_id": "Standard_DS3_v2",
            "autoscale": {"min_workers": 2, "max_workers": 8},
            "autotermination_minutes": 45,
            "data_security_mode": "USER_ISOLATION",
            "policy_id": "POL-SHARED-01",
            "instance_pool_id": "POOL-WORKERS-01",
            "runtime_engine": "PHOTON",
            "custom_tags": {"cost_center": "analytics"},
        }, "dbx_clusters", REFERENCE, config),
        module.normalize_cluster({
            "cluster_id": "0801-222222-legacy02",
            "cluster_name": "legacy-unbounded-cluster",
            "cluster_source": "UI",
            "state": "RUNNING",
            "spark_version": "11.3.x-scala2.12",
            "node_type_id": "Standard_DS4_v2",
            "num_workers": 4,
            "autotermination_minutes": 0,
            "data_security_mode": "NONE",
        }, "dbx_clusters", REFERENCE, config),
    ]

    pools = [
        module.normalize_pool({
            "instance_pool_id": "POOL-WORKERS-01",
            "instance_pool_name": "pool-photon-workers",
            "node_type_id": "Standard_DS3_v2",
            "min_idle_instances": 0,
            "max_capacity": 20,
            "idle_instance_autotermination_minutes": 15,
        }, "dbx_instance_pools", REFERENCE, config)
    ]

    policies = [
        module.normalize_policy({
            "policy_id": "POL-SHARED-01",
            "name": "Enterprise Shared Compute Policy",
            "policy_family_id": "shared-compute",
            "is_default": True,
        }, "dbx_cluster_policies", REFERENCE, config)
    ]

    jobs = [
        module.normalize_job({
            "job_id": 1001,
            "settings": {
                "name": "job-lakehouse-medallion-daily",
                "timeout_seconds": 3600,
                "max_concurrent_runs": 1,
                "schedule": {"quartz_cron_expression": "0 0 2 * * ?", "timezone_id": "UTC"},
                "email_notifications": {"on_failure": ["ops@example.invalid"]},
                "run_as": {"service_principal_name": "55555555-5555-4555-8555-555555555555"},
                "job_clusters": [
                    {
                        "job_cluster_key": "jc-medallion",
                        "new_cluster": {
                            "spark_version": "15.4.x-scala2.12-lts",
                            "node_type_id": "Standard_DS3_v2",
                            "policy_id": "POL-SHARED-01",
                            "instance_pool_id": "POOL-WORKERS-01",
                            "data_security_mode": "SINGLE_USER",
                        },
                    }
                ],
                "tasks": [
                    {
                        "task_key": "ingest_bronze",
                        "job_cluster_key": "jc-medallion",
                        "notebook_task": {"notebook_path": "/Repos/prod/medallion/01_bronze"},
                        "timeout_seconds": 1200,
                    },
                    {
                        "task_key": "transform_silver_dlt",
                        "depends_on": [{"task_key": "ingest_bronze"}],
                        "pipeline_task": {"pipeline_id": "PIPE-DLT-01"},
                        "timeout_seconds": 1800,
                    },
                    {
                        "task_key": "publish_gold_sql",
                        "depends_on": [{"task_key": "transform_silver_dlt"}],
                        "sql_task": {"warehouse_id": "WH-SERVERLESS-01"},
                        "timeout_seconds": 600,
                    },
                    {
                        "task_key": "trigger_downstream_quality",
                        "depends_on": [{"task_key": "publish_gold_sql"}],
                        "run_job_task": {"job_id": 1002},
                    },
                ],
            },
        }, "dbx_jobs", REFERENCE, config),
        module.normalize_job({
            "job_id": 1002,
            "settings": {
                "name": "job-legacy-allpurpose-user",
                "run_as": {"user_name": "developer@example.invalid"},
                "tasks": [
                    {
                        "task_key": "adhoc_export",
                        "existing_cluster_id": "0801-222222-legacy02",
                    }
                ],
            },
        }, "dbx_jobs", REFERENCE, config),
    ]

    pipelines = [
        module.normalize_pipeline({
            "pipeline_id": "PIPE-DLT-01",
            "name": "dlt-silver-orders",
            "state": "IDLE",
            "catalog": "main_prod",
            "target": "silver_sales",
            "serverless": True,
            "continuous": False,
        }, "dbx_pipelines", REFERENCE, config)
    ]

    warehouses = [
        module.normalize_warehouse({
            "id": "WH-SERVERLESS-01",
            "name": "wh-bi-serverless",
            "state": "STOPPED",
            "cluster_size": "Small",
            "warehouse_type": "PRO",
            "enable_serverless_compute": True,
            "auto_stop_mins": 10,
            "min_num_clusters": 1,
            "max_num_clusters": 2,
            "enable_photon": True,
        }, "dbx_sql_warehouses", REFERENCE, config)
    ]

    scopes = [
        module.normalize_secret_scope({
            "name": "kv-backed-prod-scope",
            "backend_type": "AZURE_KEYVAULT",
            "keyvault_metadata": {
                "resource_id": kv_id,
                "dns_name": "https://kv-dbx-prod-01.vault.azure.net/",
            },
        }, "dbx_secret_scopes", REFERENCE, config)
    ]

    metastore = module.normalize_metastore({
        "metastore_id": "ms-weu-0001",
        "name": "metastore-westeurope-prod",
        "region": "westeurope",
        "storage_root": "abfss://metastore@stadlsprod001.dfs.core.windows.net/root",
        "storage_root_credential_name": "cred-adls-mi-prod",
        "privilege_model_version": "1.0",
    }, "uc_metastore_summary", REFERENCE, config)

    catalogs = [
        module.normalize_catalog({
            "name": "main_prod",
            "catalog_type": "MANAGED_CATALOG",
            "storage_root": "abfss://catalog@stadlsprod001.dfs.core.windows.net/main_prod",
            "isolation_mode": "ISOLATED",
            "metastore_id": "ms-weu-0001",
        }, "uc_catalogs", REFERENCE, config),
        module.normalize_catalog({
            "name": "fed_erp_catalog",
            "catalog_type": "FOREIGN_CATALOG",
            "connection_name": "conn-sqlserver-erp",
            "isolation_mode": "ISOLATED",
            "metastore_id": "ms-weu-0001",
        }, "uc_catalogs", REFERENCE, config),
    ]

    schemas = [
        module.normalize_schema({
            "full_name": "main_prod.silver_sales",
            "name": "silver_sales",
            "catalog_name": "main_prod",
            "metastore_id": "ms-weu-0001",
        }, "uc_schemas", REFERENCE, config)
    ]

    storage_creds = [
        module.normalize_storage_credential({
            "id": "sc-001",
            "name": "cred-adls-mi-prod",
            "read_only": False,
            "isolation_mode": "ISOLATION_MODE_ISOLATED",
            "azure_managed_identity": {
                "access_connector_id": ac_id,
                "managed_identity_id": uami_id,
            },
        }, "uc_storage_credentials", REFERENCE, config)
    ]

    ext_locations = [
        module.normalize_external_location({
            "name": "extloc-curated-adls",
            "url": "abfss://curated@stadlsprod001.dfs.core.windows.net/lakehouse",
            "credential_name": "cred-adls-mi-prod",
            "read_only": False,
            "isolation_mode": "ISOLATION_MODE_ISOLATED",
            "metastore_id": "ms-weu-0001",
        }, "uc_external_locations", REFERENCE, config),
        module.normalize_external_location({
            "name": "extloc-partner-landing-inferred",
            "url": "abfss://landing@stpartneruncollected99.dfs.core.windows.net/dropzone",
            "credential_name": "cred-adls-mi-prod",
            "read_only": True,
            "isolation_mode": "ISOLATION_MODE_ISOLATED",
            "metastore_id": "ms-weu-0001",
        }, "uc_external_locations", REFERENCE, config),
    ]

    connections = [
        module.normalize_connection({
            "connection_id": "conn-001",
            "name": "conn-sqlserver-erp",
            "connection_type": "SQLSERVER",
            "credential_type": "OAUTH",
            "options": {"host": "sql-erp-prod.database.windows.net"},
            "read_only": True,
        }, "uc_connections", REFERENCE, config)
    ]

    outbound_eps = [
        module.normalize_outbound_endpoint({
            "category": "Webapp",
            "endpoints": [{"domainName": "westeurope.azuredatabricks.net", "endpointDetails": [{"port": 443, "region": "westeurope"}]}],
        }, "arm_outbound_endpoints", REFERENCE, config),
        module.normalize_outbound_endpoint({
            "category": "Control Plane NAT",
            "endpoints": [{"domainName": "tunnel.westeurope.azuredatabricks.net", "endpointDetails": [{"port": 443, "region": "westeurope"}]}],
        }, "arm_outbound_endpoints", REFERENCE, config),
    ]

    sources = [
        module.source_receipt("arm_workspace", REFERENCE, "complete", records=1, pages=1),
        module.source_receipt("arm_outbound_endpoints", REFERENCE, "complete", records=2, pages=1),
        module.source_receipt("arm_diagnostics", REFERENCE, "complete", records=1, pages=1),
        module.source_receipt("arm_managed_rg_inventory", REFERENCE, "complete", records=3, pages=1),
        module.source_receipt("dbx_workspace_conf", REFERENCE, "complete", records=1, pages=1),
        module.source_receipt("dbx_clusters", REFERENCE, "complete", records=len(clusters), pages=1),
        module.source_receipt("dbx_instance_pools", REFERENCE, "complete", records=len(pools), pages=1),
        module.source_receipt("dbx_cluster_policies", REFERENCE, "complete", records=len(policies), pages=1),
        module.source_receipt("dbx_jobs", REFERENCE, "complete", records=len(jobs), pages=1),
        module.source_receipt("dbx_pipelines", REFERENCE, "complete", records=len(pipelines), pages=1),
        module.source_receipt("dbx_sql_warehouses", REFERENCE, "complete", records=len(warehouses), pages=1),
        module.source_receipt("dbx_secret_scopes", REFERENCE, "complete", records=len(scopes), pages=1),
        module.source_receipt("dbx_init_scripts", REFERENCE, "complete", records=0, pages=1),
        module.source_receipt("uc_metastore_summary", REFERENCE, "complete", records=1, pages=1),
        module.source_receipt("uc_catalogs", REFERENCE, "complete", records=len(catalogs), pages=1),
        module.source_receipt("uc_schemas", REFERENCE, "complete", records=len(schemas), pages=1),
        module.source_receipt("uc_storage_credentials", REFERENCE, "complete", records=len(storage_creds), pages=1),
        module.source_receipt("uc_external_locations", REFERENCE, "complete", records=len(ext_locations), pages=1),
        module.source_receipt("uc_connections", REFERENCE, "complete", records=len(connections), pages=1),
        module.source_receipt("uc_system_lineage", REFERENCE, "not_configured", "Control-plane mode never starts a SQL Warehouse."),
        module.source_receipt("arm_advisor", REFERENCE, "complete", records=0, pages=1),
        module.source_receipt("azure_cost", REFERENCE, "complete", records=1, pages=1, window={"start": "2026-10-01T00:00:00Z", "end": REFERENCE}),
    ]

    return {
        "workspace": ws,
        "sources": sources,
        "inventory": {
            "clusters": clusters,
            "instance_pools": pools,
            "cluster_policies": policies,
            "jobs": jobs,
            "pipelines": pipelines,
            "sql_warehouses": warehouses,
            "secret_scopes": scopes,
            "global_init_scripts": [],
            "uc_metastore": metastore,
            "uc_catalogs": catalogs,
            "uc_schemas": schemas,
            "uc_storage_credentials": storage_creds,
            "uc_external_locations": ext_locations,
            "uc_connections": connections,
            "outbound_endpoints": outbound_eps,
            "related_resources": related,
        },
        "requirements": config["requirements"],
        "workspace_conf": {
            "enableTokensConfig": "true",
            "maxTokenLifetimeDays": "30",
            "enableIpAccessLists": "true",
            "enableDbfsFileBrowser": "false",
            "enableExportNotebook": "false",
        },
        "arm_diagnostics": [
            {
                "id": WORKSPACE_ID + "/providers/Microsoft.Insights/diagnosticSettings/diag-prod",
                "name": "diag-prod",
                "logs": [{"category": "jobs", "enabled": True}, {"category": "clusters", "enabled": True}],
            }
        ],
        "advisor": [],
        "cost_rows": [
            {
                "resource_id": WORKSPACE_ID,
                "usage_date": None,
                "amount": 1420.50,
                "currency": "EUR",
                "source_id": "azure_cost",
                "observed_at": REFERENCE,
                "workspace_name": WORKSPACE_NAME,
                "workspace_id": WORKSPACE_ID,
                "window": {"start": "2026-10-01T00:00:00Z", "end": REFERENCE},
                "association": {"type": "approved_observed_resource_ids", "source_id": "configuration"},
                "basis": "ActualCost/PreTaxCost in exact approved ARM scope; not per-job or per-cluster DBU attribution.",
            }
        ],
    }

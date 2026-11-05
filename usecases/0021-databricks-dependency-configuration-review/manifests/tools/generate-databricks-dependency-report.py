"""Read-only Azure Databricks dependency and configuration assessment. Build assets with build_tool.py before SRE paste."""

import base64
import binascii
import csv
import hashlib
import io
import json
import math
import os
import re
import ssl
import tempfile
import time
import warnings
from collections import Counter
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener
from uuid import UUID, uuid4


SUBSCRIPTION_ID = "<YOUR_TARGET_SUBSCRIPTION_ID>"
SRE_TENANT_ID = "<YOUR_SRE_AGENT_TENANT_ID>"
TARGET_TENANT_ID = "<YOUR_TARGET_DATABRICKS_TENANT_ID>"
MANAGED_IDENTITY_CLIENT_ID = "<YOUR_SRE_UAMI_CLIENT_ID>"
FEDERATED_APP_CLIENT_ID = ""
KEYVAULT_OAUTH_SECRET_URI = ""
CLIENT_NAME = "CLIENTE"
# Here goes the customer's logo, privately configured as a validated PNG/JPEG
# data URI. Keep generic Git source empty. Use adjacent strings <10K per line.
CLIENT_LOGO_DATA_URI = ""
CLIENT_LOGO_ALT = "Logotipo autorizado del cliente"
APPROVED_WORKSPACES = {
    "<APPROVED_DATABRICKS_WORKSPACE_NAME>": {
        "resource_group": "<APPROVED_DATABRICKS_RESOURCE_GROUP>",
        "workspace_host": "<APPROVED_WORKSPACE_HOST_ADB_NET>",
        "environment": "UNSPECIFIED",
        "auth_mode": "same_tenant_uami",
        "workspace_api_enabled": True,
        "unity_catalog_enabled": True,
        "include_managed_resource_group": True,
        "advisor_enabled": True,
        "approved_related_resource_ids": [],
        "approved_cost_resource_ids": [],
        "cost_scope": "disabled",
        "cost_timeframe": "month_to_date",
        "requirements": {},
    }
}

ARM_ORIGIN = "https://management.azure.com"
ARM_TOKEN_AUDIENCES = (
    "https://management.azure.com",
    "https://management.core.windows.net",
)
KEYVAULT_AUDIENCE = "https://vault.azure.net"
DATABRICKS_ENTRA_RESOURCE = "2ff814a6-3304-4ab8-85cb-cd0e6f879c1d"
ENTRA_TOKEN_EXCHANGE_AUDIENCE = "api://AzureADTokenExchange"
ENTRA_TOKEN_EXCHANGE_AUDIENCES = (
    "api://azureadtokenexchange",
    "fb60f99c-7a34-4190-8149-302f77469936",
)
DATABRICKS_ARM_API = "2024-05-01"
TRANSPORT_BYTES = 3500
ARTIFACT_BYTES = 4_800_000
HTTP_BYTES = 8_000_000
MAX_PAGES = 50
MAX_ROWS = 15000
MAX_RELATED_RESOURCES = 200
MAX_DETAIL_GETS = 100
MAX_COLLECTION_SECONDS = 240
MAX_HTTP_ATTEMPTS = 300
OUTPUT_DIRECTORY = "databricks-dependency-reports"
AUTH_MODES = (
    "same_tenant_uami",
    "cross_tenant_multitenant_fic",
    "cross_tenant_lighthouse_plus_databricks_oidc",
    "cross_tenant_lighthouse_plus_keyvault_oauth_m2m",
)
AREAS = ("best_practices", "security", "finops", "optimization")
PILLARS = ("reliability", "security", "cost", "operations", "performance")
LEVELS = ("workspace", "workload", "resource")
SEVERITIES = ("critical", "high", "medium", "low")
CLASSIFICATIONS = ("OBSERVED", "INFERRED", "UNKNOWN")
CHECK_STATUSES = ("passed", "failed", "not_evaluated", "not_applicable")
SOURCE_STATUSES = ("complete", "partial", "denied", "error", "not_configured", "not_applicable")
VIEWS = (
    "summary",
    "workspace",
    "compute",
    "jobs",
    "pipelines",
    "warehouses",
    "unity_catalog",
    "resources",
    "findings",
    "finops",
    "coverage",
    "actions",
    "dependencies",
)
SYSTEM_CATALOGS = ("system", "hive_metastore", "samples", "__databricks_internal")
RESOURCE_APIS = {
    "microsoft.databricks/accessconnectors": "2024-05-01",
    "microsoft.storage/storageaccounts": "2023-05-01",
    "microsoft.keyvault/vaults": "2023-07-01",
    "microsoft.network/virtualnetworks": "2024-05-01",
    "microsoft.network/virtualnetworks/subnets": "2024-05-01",
    "microsoft.network/networksecuritygroups": "2024-05-01",
    "microsoft.network/routetables": "2024-05-01",
    "microsoft.network/natgateways": "2024-05-01",
    "microsoft.network/publicipaddresses": "2024-05-01",
    "microsoft.network/loadbalancers": "2024-05-01",
    "microsoft.network/privateendpoints": "2024-05-01",
    "microsoft.network/privatednszones": "2020-06-01",
    "microsoft.eventhub/namespaces": "2024-01-01",
    "microsoft.managedidentity/userassignedidentities": "2023-01-31",
}
WORKSPACE_CONF_KEYS = (
    "enableTokensConfig",
    "maxTokenLifetimeDays",
    "enableIpAccessLists",
    "enableDbfsFileBrowser",
    "enableExportNotebook",
)

# BEGIN BUILD-TIME ASSETS
CATALOG = json.loads((
    '{"catalogSnapshot": {"name": "Azure Databricks Well-Architected & Lakehouse Dependency Review", "ser'
    'vice_guide_url": "https://learn.microsoft.com/en-us/azure/well-architected/service-guides/azure-data'
    'bricks", "lakehouse_waf_url": "https://learn.microsoft.com/en-us/azure/databricks/lakehouse-architec'
    'ture/well-architected", "arm_template_url": "https://learn.microsoft.com/en-us/azure/templates/micro'
    'soft.databricks/2024-05-01/workspaces", "retrieved_at": "2026-10-16", "item_count": 36}, "assessment'
    '_url": "https://learn.microsoft.com/en-us/assessments/azure-architecture-review/", "interpretation":'
    ' ["Local rule-resource indicators, not an official Microsoft Well-Architected assessment, certificat'
    'ion or Databricks audit grade.", "Dependency edges distinguish OBSERVED native ID/key joins from exp'
    'licit INFERRED URI/host references and UNKNOWN runtime lineage.", "Control-plane REST API reads neve'
    'r start clusters or SQL warehouses and never execute billable SQL queries against system.access.tabl'
    'e_lineage or system.billing.usage.", "Cross-tenant collection requires explicit administrator-config'
    'ured federation or Azure Lighthouse delegation; a single-tenant SRE UAMI never acquires foreign-tena'
    'nt tokens implicitly.", "Configuration presence does not prove effective firewall enforcement, data-'
    'plane network reachability, least-privilege Unity Catalog grants or workload SLA compliance."], "rul'
    'es": [{"rule_id": "C01", "reference_id": "DBX-WAF-SEC-01", "test": "sku_premium", "level": "workspac'
    'e", "area": "security", "pillar": "security", "severity": "high", "effort": "medium", "title": "SKU '
    'Premium para gobernanza y controles de seguridad", "recommendation": "Validar el uso del tier Premiu'
    'm para cargas de producci\\u00f3n que requieren Unity Catalog, control de acceso basado en roles y au'
    'ditor\\u00eda avanzada.", "business_impact": "Un tier inferior a Premium puede limitar controles de i'
    'dentidad, Unity Catalog y aislamiento de acceso.", "learn_url": "https://learn.microsoft.com/en-us/a'
    'zure/well-architected/service-guides/azure-databricks#cost-optimization"}, {"rule_id": "C02", "refer'
    'ence_id": "DBX-WAF-SEC-02", "test": "secure_cluster_connectivity", "level": "workspace", "area": "se'
    'curity", "pillar": "security", "severity": "high", "effort": "medium", "title": "Secure Cluster Conn'
    'ectivity (No Public IP)", "recommendation": "Habilitar enableNoPublicIp en el workspace para que los'
    ' nodos de c\\u00f3mputo no tengan direcciones IP p\\u00fablicas y conecten al plano de control por rel'
    '\\u00e9 saliente.", "business_impact": "Nodos de cl\\u00faster con IP p\\u00fablica incrementan la supe'
    'rficie de exposici\\u00f3n de red del plano de datos.", "learn_url": "https://learn.microsoft.com/en-'
    'us/azure/databricks/security/network/classic/secure-cluster-connectivity"}, {"rule_id": "C03", "refe'
    'rence_id": "DBX-WAF-NET-01", "test": "vnet_injection", "level": "workspace", "area": "best_practices'
    '", "pillar": "security", "severity": "medium", "effort": "high", "title": "Despliegue con VNet Injec'
    'tion en red gestionada por el cliente", "recommendation": "Cuando la arquitectura de red corporativa'
    ' lo requiera, desplegar el workspace con customVirtualNetworkId y subredes host/container dedicadas.'
    '", "business_impact": "La VNet administrada por defecto impide aplicar rutas personalizadas, inspecc'
    'i\\u00f3n de egress o emparejamientos granulares.", "learn_url": "https://learn.microsoft.com/en-us/a'
    'zure/databricks/security/network/classic/vnet-inject"}, {"rule_id": "C04", "reference_id": "DBX-WAF-'
    'NET-02", "test": "private_link_and_public_access", "level": "workspace", "area": "security", "pillar'
    '": "security", "severity": "high", "effort": "high", "title": "Restricci\\u00f3n de red p\\u00fablica '
    'y Private Link del workspace", "recommendation": "Revisar publicNetworkAccess, requiredNsgRules y co'
    'nexiones Private Endpoint aprobadas seg\\u00fan los requisitos de aislamiento privado.", "business_im'
    'pact": "El acceso p\\u00fablico abierto sin controles compensatorios ampl\\u00eda la superficie de ent'
    'rada al workspace.", "learn_url": "https://learn.microsoft.com/en-us/azure/databricks/security/netwo'
    'rk/classic/private-link"}, {"rule_id": "C05", "reference_id": "DBX-WAF-SEC-03", "test": "access_conn'
    'ector_and_storage_firewall", "level": "workspace", "area": "security", "pillar": "security", "severi'
    'ty": "medium", "effort": "medium", "title": "Access Connector con identidad administrada y firewall '
    'de almacenamiento", "recommendation": "Vincular un Azure Databricks Access Connector con identidad a'
    'dministrada (SystemAssigned o UserAssigned) y revisar defaultStorageFirewall.", "business_impact": "'
    'La ausencia de Access Connector impide autenticar con identidad administrada hacia almacenamiento go'
    'bernado.", "learn_url": "https://learn.microsoft.com/en-us/azure/databricks/connect/unity-catalog/cl'
    'oud-storage/azure-managed-identities"}, {"rule_id": "C06", "reference_id": "DBX-WAF-SEC-04", "test":'
    ' "customer_managed_keys", "level": "workspace", "area": "security", "pillar": "security", "severity"'
    ': "medium", "effort": "medium", "title": "Cifrado con claves gestionadas por el cliente (CMK) e infr'
    'aestructura", "recommendation": "Si la pol\\u00edtica de cumplimiento exige CMK, configurar claves de'
    ' Key Vault para managedServices y managedDisk con rotaci\\u00f3n autom\\u00e1tica.", "business_impact"'
    ': "Sin CMK cuando es requerido por normativa, el cliente no controla directamente la revocaci\\u00f3n'
    ' criptogr\\u00e1fica.", "learn_url": "https://learn.microsoft.com/en-us/azure/databricks/security/key'
    's/"}, {"rule_id": "C07", "reference_id": "DBX-WAF-SEC-05", "test": "enhanced_security_compliance", "'
    'level": "workspace", "area": "security", "pillar": "operations", "severity": "low", "effort": "mediu'
    'm", "title": "Perfil de seguridad mejorada y actualizaci\\u00f3n autom\\u00e1tica de cl\\u00fasteres", '
    '"recommendation": "Evaluar enhancedSecurityMonitoring, automaticClusterUpdate y complianceSecurityPr'
    'ofile cuando apliquen normativas espec\\u00edficas.", "business_impact": "Sin actualizaciones autom\\u'
    '00e1ticas o monitorizaci\\u00f3n mejorada requerida, el mantenimiento de agentes depende de procesos '
    'manuales.", "learn_url": "https://learn.microsoft.com/en-us/azure/databricks/security/privacy/securi'
    'ty-profile"}, {"rule_id": "C08", "reference_id": "DBX-WAF-OPS-01", "test": "diagnostics", "level": "'
    'workspace", "area": "best_practices", "pillar": "operations", "severity": "medium", "effort": "low",'
    ' "title": "Configuraci\\u00f3n de Diagnostic Settings en el plano de control ARM", "recommendation": '
    '"Configurar categor\\u00edas de auditor\\u00eda en Microsoft.Insights/diagnosticSettings hacia Log Ana'
    'lytics, Storage o Event Hub y verificar la ingesta.", "business_impact": "Sin registros diagn\\u00f3s'
    'ticos habilitados se reduce la trazabilidad de eventos de control plane, jobs y accesos.", "learn_ur'
    'l": "https://learn.microsoft.com/en-us/azure/databricks/admin/account-settings/audit-logs"}, {"rule_'
    'id": "C09", "reference_id": "DBX-WAF-SEC-06", "test": "pat_token_governance", "level": "workspace", '
    '"area": "security", "pillar": "security", "severity": "medium", "effort": "low", "title": "Gobernanz'
    'a de Personal Access Tokens (PAT) en workspace-conf", "recommendation": "Revisar enableTokensConfig '
    'y priorizar autenticaci\\u00f3n OAuth M2M o identidades administradas de Microsoft Entra frente a PAT'
    's duraderos.", "business_impact": "Tokens personales sin control de emisi\\u00f3n o expiraci\\u00f3n i'
    'ncrementan el riesgo de credenciales persistentes.", "learn_url": "https://learn.microsoft.com/en-us'
    '/azure/databricks/security/auth/api-access-permissions"}, {"rule_id": "C10", "reference_id": "DBX-WA'
    'F-GOV-01", "test": "default_catalog_unity", "level": "workspace", "area": "best_practices", "pillar"'
    ': "operations", "severity": "medium", "effort": "medium", "title": "Cat\\u00e1logo predeterminado en '
    'Unity Catalog frente a Hive heredado", "recommendation": "Configurar UnityCatalog como cat\\u00e1logo'
    ' predeterminado y evitar almacenar datos de negocio en el DBFS root o hive_metastore.", "business_im'
    'pact": "El uso de hive_metastore y DBFS root dificulta el control de acceso unificado y el linaje de'
    ' datos.", "learn_url": "https://learn.microsoft.com/en-us/azure/databricks/data-governance/unity-cat'
    'alog/best-practices"}, {"rule_id": "C11", "reference_id": "DBX-WAF-SEC-07", "test": "global_init_scr'
    'ipts", "level": "workspace", "area": "security", "pillar": "security", "severity": "low", "effort": '
    '"low", "title": "Higiene y revisi\\u00f3n de Global Init Scripts", "recommendation": "Minimizar o aud'
    'itar los global init scripts habilitados y preferir pol\\u00edticas de cl\\u00faster o scripts con alc'
    'ance de unidad en Unity Catalog.", "business_impact": "Los global init scripts se ejecutan en todos '
    'los cl\\u00fasteres del workspace y pueden introducir dependencias ocultas o superficie de fallo.", "'
    'learn_url": "https://learn.microsoft.com/en-us/azure/databricks/init-scripts/global"}, {"rule_id": "'
    'C12", "reference_id": "DBX-WAF-OPS-02", "test": "advisor", "level": "workspace", "area": "optimizati'
    'on", "pillar": "operations", "severity": "low", "effort": "low", "title": "Revisi\\u00f3n de recomend'
    'aciones cacheadas de Azure Advisor", "recommendation": "Consultar las recomendaciones cacheadas de A'
    'zure Advisor para el workspace y recursos asociados como insumo complementario.", "business_impact":'
    ' "Ignorar alertas de plataforma puede retrasar la detecci\\u00f3n de mejoras de fiabilidad o coste.",'
    ' "learn_url": "https://learn.microsoft.com/en-us/azure/well-architected/service-guides/azure-databri'
    'cks"}, {"rule_id": "W01", "reference_id": "DBX-WAF-COST-01", "test": "cluster_autotermination", "lev'
    'el": "workload", "area": "finops", "pillar": "cost", "severity": "high", "effort": "low", "title": "'
    'Autoterminaci\\u00f3n configurada en cl\\u00fasteres interactivos All-Purpose", "recommendation": "Def'
    'inir autotermination_minutes (por ejemplo <= 60 minutos) en todos los cl\\u00fasteres All-Purpose par'
    'a evitar consumo DBU y VM en inactividad.", "business_impact": "Un cl\\u00faster interactivo sin auto'
    'terminaci\\u00f3n o con umbral excesivo mantiene nodos facturando sin carga activa.", "learn_url": "h'
    'ttps://learn.microsoft.com/en-us/azure/databricks/compute/cluster-config-best-practices"}, {"rule_id'
    '": "W02", "reference_id": "DBX-WAF-GOV-02", "test": "cluster_policy_bound", "level": "workload", "ar'
    'ea": "best_practices", "pillar": "cost", "severity": "medium", "effort": "medium", "title": "Cl\\u00f'
    'asteres gobernados mediante Cluster Policy", "recommendation": "Asociar policy_id a los cl\\u00faster'
    'es para aplicar l\\u00edmites de tipo de instancia, autoterminaci\\u00f3n, versi\\u00f3n de runtime y e'
    'tiquetas FinOps.", "business_impact": "Crear cl\\u00fasteres sin pol\\u00edtica permite configuracione'
    's no estandarizadas y sobrecostes accidentales.", "learn_url": "https://learn.microsoft.com/en-us/az'
    'ure/databricks/admin/clusters/policies"}, {"rule_id": "W03", "reference_id": "DBX-WAF-SEC-08", "test'
    '": "cluster_access_mode", "level": "workload", "area": "security", "pillar": "security", "severity":'
    ' "high", "effort": "medium", "title": "Modo de acceso de c\\u00f3mputo compatible con aislamiento y U'
    'nity Catalog", "recommendation": "Configurar data_security_mode en USER_ISOLATION (Standard/Shared) '
    'o SINGLE_USER (Dedicated) y evitar modos sin aislamiento (NONE).", "business_impact": "Modos de acce'
    'so heredados o sin aislamiento impiden aplicar controles de Unity Catalog o permiten acceso directo '
    'no gobernado.", "learn_url": "https://learn.microsoft.com/en-us/azure/databricks/compute/configure#a'
    'ccess-mode"}, {"rule_id": "W04", "reference_id": "DBX-WAF-OPS-03", "test": "cluster_runtime_lts", "l'
    'evel": "workload", "area": "best_practices", "pillar": "reliability", "severity": "medium", "effort"'
    ': "medium", "title": "Versi\\u00f3n de Databricks Runtime soportada (LTS / actual)", "recommendation"'
    ': "Mantener spark_version en una versi\\u00f3n Long Term Support (LTS) vigente (por ejemplo 13.3 LTS,'
    ' 14.3 LTS, 15.4 LTS o superior).", "business_impact": "Versiones antiguas de Databricks Runtime pier'
    'den soporte, parches de seguridad y optimizaciones de Photon/Delta.", "learn_url": "https://learn.mi'
    'crosoft.com/en-us/azure/databricks/release-notes/runtime/"}, {"rule_id": "W05", "reference_id": "DBX'
    '-WAF-PERF-01", "test": "cluster_autoscaling_or_pool", "level": "workload", "area": "optimization", "'
    'pillar": "performance", "severity": "low", "effort": "low", "title": "Escalado din\\u00e1mico (Autosc'
    'ale) o uso de Instance Pool en cl\\u00fasteres", "recommendation": "Evaluar autoscale (min_workers/ma'
    'x_workers) o vinculaci\\u00f3n a instance_pool_id para adaptar capacidad a variaciones de carga.", "b'
    'usiness_impact": "Un n\\u00famero fijo de workers sin pool puede infrautilizar recursos en valles o l'
    'imitar concurrencia en picos.", "learn_url": "https://learn.microsoft.com/en-us/azure/databricks/com'
    'pute/cluster-config-best-practices#autoscaling"}, {"rule_id": "W06", "reference_id": "DBX-WAF-COST-0'
    '2", "test": "job_uses_job_compute", "level": "workload", "area": "finops", "pillar": "cost", "severi'
    'ty": "high", "effort": "medium", "title": "Jobs programados ejecutando en Job Compute o Serverless e'
    'n lugar de All-Purpose", "recommendation": "Migrar las tareas de Jobs que apuntan a existing_cluster'
    '_id hacia job_cluster_key o c\\u00f3mputo Serverless de Jobs.", "business_impact": "Ejecutar jobs aut'
    'omatizados sobre cl\\u00fasteres All-Purpose consume tarifas DBU m\\u00e1s altas y acopla fallos entre'
    ' cargas.", "learn_url": "https://learn.microsoft.com/en-us/azure/well-architected/service-guides/azu'
    're-databricks#cost-optimization"}, {"rule_id": "W07", "reference_id": "DBX-WAF-REL-01", "test": "job'
    '_resilience_settings", "level": "workload", "area": "best_practices", "pillar": "reliability", "seve'
    'rity": "medium", "effort": "low", "title": "Timeouts, reintentos o notificaciones en Jobs de orquest'
    'aci\\u00f3n", "recommendation": "Configurar timeout_seconds, pol\\u00edticas de reintento y notificaci'
    'ones o alertas en los Jobs cr\\u00edticos para detectar ejecuciones colgadas o fallidas.", "business_'
    'impact": "Un job sin timeout ni alertas puede quedar bloqueado consumiendo recursos o incumplir vent'
    'anas de datos sin aviso.", "learn_url": "https://learn.microsoft.com/en-us/azure/databricks/jobs/con'
    'figure-job"}, {"rule_id": "W08", "reference_id": "DBX-WAF-SEC-09", "test": "job_service_principal_ru'
    'n_as", "level": "workload", "area": "security", "pillar": "operations", "severity": "medium", "effor'
    't": "medium", "title": "Ejecuci\\u00f3n de Jobs mediante Service Principal (run_as)", "recommendation'
    '": "Configurar run_as con un Service Principal dedicado en lugar de una cuenta de usuario individual'
    ' para evitar fallos ante bajas o cambios de rol.", "business_impact": "Los jobs ejecutados bajo iden'
    'tidad de usuario fallan si el usuario deja la organizaci\\u00f3n o pierde permisos.", "learn_url": "h'
    'ttps://learn.microsoft.com/en-us/azure/databricks/admin/users-groups/service-principals"}, {"rule_id'
    '": "W09", "reference_id": "DBX-WAF-COST-03", "test": "sql_warehouse_autostop", "level": "workload", '
    '"area": "finops", "pillar": "cost", "severity": "medium", "effort": "low", "title": "Auto-stop y arq'
    'uitectura Serverless/Pro en SQL Warehouses", "recommendation": "Configurar auto_stop_mins (<= 30 min'
    'utos) o usar SQL Warehouses Serverless para cargas BI e interactivas con demanda variable.", "busine'
    'ss_impact": "Un SQL Warehouse sin auto-stop mantiene capacidad facturable activa fuera de las ventan'
    'as de consulta.", "learn_url": "https://learn.microsoft.com/en-us/azure/databricks/compute/sql-wareh'
    'ouse/create"}, {"rule_id": "W10", "reference_id": "DBX-WAF-GOV-03", "test": "pipeline_unity_catalog"'
    ', "level": "workload", "area": "best_practices", "pillar": "operations", "severity": "medium", "effo'
    'rt": "medium", "title": "Pipelines declarativos (Lakeflow / DLT) publicados en Unity Catalog", "reco'
    'mmendation": "Definir un cat\\u00e1logo de Unity Catalog en los pipelines declarativos para asegurar '
    'linaje nativo y gobernanza de tablas.", "business_impact": "Los pipelines publicados en hive_metasto'
    're quedan fuera del modelo centralizado de permisos y linaje.", "learn_url": "https://learn.microsof'
    't.com/en-us/azure/databricks/ldp/unity-catalog"}, {"rule_id": "G01", "reference_id": "DBX-WAF-GOV-04'
    '", "test": "uc_metastore_attached", "level": "workspace", "area": "best_practices", "pillar": "secur'
    'ity", "severity": "high", "effort": "high", "title": "Asignaci\\u00f3n de Metastore de Unity Catalog '
    'al workspace", "recommendation": "Vincular el workspace a un Metastore regional de Unity Catalog par'
    'a centralizar identidades, control de acceso, auditor\\u00eda y linaje.", "business_impact": "Sin Met'
    'astore adjunto no est\\u00e1n disponibles las capacidades de gobierno unificado, ubicaciones externas'
    ' ni tablas de sistema.", "learn_url": "https://learn.microsoft.com/en-us/azure/databricks/data-gover'
    'nance/unity-catalog/get-started"}, {"rule_id": "G02", "reference_id": "DBX-WAF-SEC-10", "test": "uc_'
    'storage_credential_mi", "level": "workspace", "area": "security", "pillar": "security", "severity": '
    '"high", "effort": "medium", "title": "Storage Credentials de Unity Catalog basadas en Managed Identi'
    'ty", "recommendation": "Usar Azure Managed Identity (v\\u00eda Access Connector) en las Storage Crede'
    'ntials de Unity Catalog en lugar de secretos de Service Principal.", "business_impact": "Las credenc'
    'iales basadas en secretos requieren rotaci\\u00f3n manual y aumentan el riesgo ante filtraciones.", "'
    'learn_url": "https://learn.microsoft.com/en-us/azure/databricks/connect/unity-catalog/cloud-storage/'
    'storage-credentials"}, {"rule_id": "G03", "reference_id": "DBX-WAF-GOV-05", "test": "uc_external_loc'
    'ations_governed", "level": "workspace", "area": "security", "pillar": "security", "severity": "mediu'
    'm", "effort": "medium", "title": "External Locations con Storage Credential v\\u00e1lida y rutas ADLS'
    ' Gen2 expl\\u00edcitas", "recommendation": "Verificar que cada External Location enlace con una Stora'
    'ge Credential existente, utilice abfss:// y aplique vinculaci\\u00f3n por workspace cuando proceda.",'
    ' "business_impact": "Ubicaciones externas hu\\u00e9rfanas o sin aislamiento pueden exponer contenedor'
    'es compartidos entre entornos.", "learn_url": "https://learn.microsoft.com/en-us/azure/databricks/da'
    'ta-governance/unity-catalog/best-practices#external-locations"}, {"rule_id": "G04", "reference_id": '
    '"DBX-WAF-SEC-11", "test": "secret_scopes_keyvault", "level": "workspace", "area": "security", "pilla'
    'r": "security", "severity": "medium", "effort": "medium", "title": "Secret Scopes respaldados por Az'
    'ure Key Vault", "recommendation": "Preferir Secret Scopes con backend AZURE_KEYVAULT frente a scopes'
    ' locales DATABRICKS cuando se requiera gesti\\u00f3n centralizada de secretos.", "business_impact": "'
    'Los scopes locales de Databricks no se integran directamente con las pol\\u00edticas de rotaci\\u00f3n'
    ' y auditor\\u00eda de Azure Key Vault.", "learn_url": "https://learn.microsoft.com/en-us/azure/databr'
    'icks/security/secrets/secret-scopes"}, {"rule_id": "G05", "reference_id": "DBX-WAF-REL-02", "test": '
    '"dependency_integrity", "level": "workspace", "area": "best_practices", "pillar": "reliability", "se'
    'verity": "high", "effort": "medium", "title": "Integridad referencial del mapa de dependencias de Jo'
    'bs, C\\u00f3mputo y Gobernanza", "recommendation": "Corregir referencias rotas en tareas de Jobs (cl\\'
    'u00fasteres eliminados, SQL Warehouses inexistentes, pipelines o jobs hijos ausentes y credenciales '
    'no resueltas).", "business_impact": "Una dependencia rota observada en la definici\\u00f3n de un Job '
    'provocar\\u00e1 fallos inmediatos de ejecuci\\u00f3n en producci\\u00f3n.", "learn_url": "https://learn'
    '.microsoft.com/en-us/azure/databricks/jobs/configure-job"}, {"rule_id": "G06", "reference_id": "DBX-'
    'WAF-GOV-06", "test": "runtime_table_lineage", "level": "workspace", "area": "optimization", "pillar"'
    ': "operations", "severity": "low", "effort": "medium", "title": "Linaje din\\u00e1mico de tablas y co'
    'lumnas (system.access.table_lineage)", "recommendation": "Si se requiere linaje en tiempo de ejecuci'
    '\\u00f3n a nivel de tabla/columna, habilitar y consultar system.access.table_lineage en una sesi\\u00f'
    '3n autorizada sin arrancar c\\u00f3mputo autom\\u00e1ticamente desde este colector.", "business_impact'
    '": "El an\\u00e1lisis de plano de control mapea dependencias declaradas, pero no las lecturas/escritu'
    'ras SQL din\\u00e1micas dentro de notebooks.", "learn_url": "https://learn.microsoft.com/en-us/azure/'
    'databricks/admin/system-tables/lineage"}, {"rule_id": "G07", "reference_id": "DBX-WAF-GOV-07", "test'
    '": "lakehouse_federation_connections", "level": "workspace", "area": "best_practices", "pillar": "op'
    'erations", "severity": "low", "effort": "low", "title": "Gobernanza de conexiones externas en Unity '
    'Catalog (Lakehouse Federation)", "recommendation": "Inventariar las conexiones de Lakehouse Federati'
    'on en Unity Catalog y verificar sus dependencias de red y credenciales.", "business_impact": "Las co'
    'nexiones federadas externas representan dependencias cr\\u00edticas hacia motores SQL o plataformas d'
    'e terceros.", "learn_url": "https://learn.microsoft.com/en-us/azure/databricks/query-federation/"}, '
    '{"rule_id": "G08", "reference_id": "DBX-WAF-NET-03", "test": "outbound_control_plane_endpoints", "le'
    'vel": "workspace", "area": "best_practices", "pillar": "reliability", "severity": "medium", "effort"'
    ': "low", "title": "Visibilidad de dependencias de red saliente (outboundNetworkDependenciesEndpoints'
    ')", "recommendation": "Contrastar las reglas de firewall/UDR/NSG con la lista oficial de endpoints s'
    'alientes requeridos por el workspace hacia el plano de control.", "business_impact": "Bloquear depen'
    'dencias salientes requeridas (Webapp, Control Plane NAT, Storage, Metastore, EventHub/ServiceBus) im'
    'pide el arranque de cl\\u00fasteres.", "learn_url": "https://learn.microsoft.com/en-us/azure/databric'
    'ks/administration-guide/cloud-configurations/azure/udr"}, {"rule_id": "R01", "reference_id": "DBX-WA'
    'F-RES-01", "test": "storage_tls_and_public_blob", "level": "resource", "area": "security", "pillar":'
    ' "security", "severity": "high", "effort": "low", "title": "Cuentas de almacenamiento asociadas con '
    'HTTPS, TLS 1.2+ y sin acceso p\\u00fablico a blobs", "recommendation": "Exigir supportsHttpsTrafficOn'
    'ly=true, minimumTlsVersion=TLS1_2 y allowBlobPublicAccess=false en las cuentas ADLS Gen2 asociadas."'
    ', "business_impact": "Permitir tr\\u00e1fico no cifrado o acceso an\\u00f3nimo a contenedores expone a'
    'ctivos del lakehouse.", "learn_url": "https://learn.microsoft.com/en-us/azure/storage/blobs/security'
    '-recommendations"}, {"rule_id": "R02", "reference_id": "DBX-WAF-RES-02", "test": "storage_shared_key'
    '_and_network", "level": "resource", "area": "security", "pillar": "security", "severity": "medium", '
    '"effort": "medium", "title": "Restricci\\u00f3n de Shared Key y acceso de red en cuentas de almacenam'
    'iento asociadas", "recommendation": "Evaluar la deshabilitaci\\u00f3n de allowSharedKeyAccess y restr'
    'ingir publicNetworkAccess en cuentas ADLS Gen2 gobernadas por Entra ID / Unity Catalog.", "business_'
    'impact": "Las claves compartidas de cuenta eluden los controles granulares de identidad de Microsoft'
    ' Entra y Unity Catalog.", "learn_url": "https://learn.microsoft.com/en-us/azure/storage/common/share'
    'd-key-authorization-prevent"}, {"rule_id": "R03", "reference_id": "DBX-WAF-RES-03", "test": "keyvaul'
    't_rbac_and_purge", "level": "resource", "area": "security", "pillar": "security", "severity": "mediu'
    'm", "effort": "medium", "title": "Autorizaci\\u00f3n RBAC y protecci\\u00f3n contra purga en Key Vault'
    's asociados", "recommendation": "Habilitar enableRbacAuthorization y enablePurgeProtection en los Ke'
    'y Vaults vinculados a Secret Scopes o claves CMK del workspace.", "business_impact": "Sin protecci\\u'
    '00f3n contra purga, la eliminaci\\u00f3n accidental o maliciosa de una clave CMK o secreto puede ser '
    'irreversible.", "learn_url": "https://learn.microsoft.com/en-us/azure/key-vault/general/security-fea'
    'tures"}, {"rule_id": "R04", "reference_id": "DBX-WAF-RES-04", "test": "nsg_exposure", "level": "reso'
    'urce", "area": "security", "pillar": "security", "severity": "high", "effort": "medium", "title": "E'
    'xposici\\u00f3n de puertos administrativos desde Internet en NSG asociados", "recommendation": "Elimi'
    'nar o restringir reglas Inbound Allow desde Internet (0.0.0.0/0, *, Internet) hacia SSH (22), RDP (3'
    '389) o todos los puertos en subredes del workspace.", "business_impact": "Reglas de entrada abiertas'
    ' desde Internet hacia las subredes de cl\\u00faster violan el aislamiento del plano de datos.", "lear'
    'n_url": "https://learn.microsoft.com/en-us/azure/databricks/security/network/classic/vnet-inject"}, '
    '{"rule_id": "R05", "reference_id": "DBX-WAF-RES-05", "test": "private_endpoint_approved", "level": "'
    'resource", "area": "best_practices", "pillar": "reliability", "severity": "medium", "effort": "low",'
    ' "title": "Estado aprobado en conexiones Private Endpoint asociadas", "recommendation": "Confirmar q'
    'ue todas las conexiones Private Endpoint asociadas al workspace o recursos vinculados est\\u00e9n en '
    'estado Approved.", "business_impact": "Un Private Endpoint en estado Pending, Rejected o Disconnecte'
    'd interrumpe la conectividad privada prevista.", "learn_url": "https://learn.microsoft.com/en-us/azu'
    're/databricks/security/network/classic/private-link"}, {"rule_id": "R06", "reference_id": "DBX-WAF-C'
    'OST-04", "test": "cost_attribution", "level": "workspace", "area": "finops", "pillar": "cost", "seve'
    'rity": "low", "effort": "medium", "title": "Atribuci\\u00f3n de costes reales (ActualCost) y granular'
    'idad DBU por carga", "recommendation": "Combinar los costes reales ARM observados con el etiquetado '
    'de cl\\u00fasteres/jobs y la tabla system.billing.usage para atribuir consumo DBU por equipo o pipeli'
    'ne.", "business_impact": "ActualCost a nivel de ResourceId de Azure no desglosa por s\\u00ed solo el '
    'consumo interno de cada Job, SQL Warehouse o usuario.", "learn_url": "https://learn.microsoft.com/en'
    '-us/azure/databricks/admin/system-tables/billing"}]}'
))
HTML_TEMPLATE = (
    '<!doctype html>\n<!--\nTHESIS: An offline Lakehouse consulting dossier connects dated Azure Databricks'
    ' dependency and configuration evidence to human engineering decisions without fabricating lineage or'
    ' savings.\nOWN-WORLD: Fluent 2 reading layout framed by corporate industrial navy/steel (#003865, #00'
    '66a1) and Databricks lakehouse lava/teal (#ff3621, #00875a) ribbon; color never substitutes for evid'
    'ence.\nSTORY: Establish cross-tenant/identity provenance, read the local index beside coverage, inspe'
    'ct OBSERVED vs INFERRED vs UNKNOWN dependencies, drill into workloads/Unity Catalog, and prioritize '
    'actions.\n-->\n<html lang="es-ES">\n<head>\n<meta charset="utf-8">\n<meta name="viewport" content="width='
    'device-width,initial-scale=1">\n<meta http-equiv="Content-Security-Policy" content="default-src \'none'
    "'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; connect-src 'none'; base-ur"
    'i \'none\'; form-action \'none\'; object-src \'none\'">\n<meta name="color-scheme" content="light dark">\n<t'
    'itle>Revisión Azure Databricks | Mapa de dependencias y configuración</title>\n<style>\n:root {\n  colo'
    'r-scheme: light;\n  --canvas: #f4f6f8; --surface: #ffffff; --subtle: #f8fafc; --wash: #edf1f5;\n  --in'
    'k: #1b242c; --muted: #52606d; --line: #cbd5e1; --field-line: #7b8794;\n  --accent: #003865; --accent-'
    'hover: #002848; --accent-wash: #eef4f9; --on-accent: #ffffff;\n  --critical: #a4262c; --critical-wash'
    ': #fde7e9; --high: #9c2b13; --high-wash: #ffede8;\n  --medium: #795b00; --medium-wash: #fff8d6; --low'
    ': #475569; --low-wash: #edf2f7;\n  --observed: #005a3c; --observed-wash: #e3fcef;\n  --inferred: #795b'
    '00; --inferred-wash: #fff8d6;\n  --unknown: #475569; --unknown-wash: #edf2f7;\n  --chrome: #003865; --'
    'chrome-hover: #002848; --on-chrome: #ffffff; --chrome-line: #b8d0e5;\n  --cover: #eef4f9; --cover-ink'
    ': #002b4e; --cover-muted: #334e68;\n  --nav: #e6eff7; --nav-ink: #002b4e; --nav-muted: #3e5871;\n  --b'
    'rand-navy: #003865; --brand-lava: #ff3621; --brand-steel: #0066a1; --brand-teal: #00875a;\n  --radius'
    ': 4px; --space: 16px;\n}\n:root[data-theme="dark"] {\n  color-scheme: dark;\n  --canvas: #141a1f; --surf'
    'ace: #1b242c; --subtle: #24303a; --wash: #2e3c48;\n  --ink: #f1f5f9; --muted: #cbd5e1; --line: #47556'
    '9; --field-line: #94a3b8;\n  --accent: #7cc4fa; --accent-hover: #a5d8ff; --accent-wash: #1b3348; --on'
    '-accent: #141a1f;\n  --critical: #ffb3b8; --critical-wash: #442326; --high: #ffbaa8; --high-wash: #42'
    '251d;\n  --medium: #f5d875; --medium-wash: #383323; --low: #d6d6d6; --low-wash: #2e3c48;\n  --observed'
    ': #8ce9bf; --observed-wash: #16382b;\n  --inferred: #f5d875; --inferred-wash: #383323;\n  --unknown: #'
    'cbd5e1; --unknown-wash: #2e3c48;\n  --chrome: #002848; --chrome-hover: #003865; --on-chrome: #f1f5f9;'
    ' --chrome-line: #84b6de;\n  --cover: #162b3d; --cover-ink: #d0e8ff; --cover-muted: #bdd8ef;\n  --nav: '
    '#132535; --nav-ink: #d0e8ff; --nav-muted: #bdd8ef;\n}\n* { box-sizing: border-box; }\nhtml { scroll-beh'
    'avior: auto; scroll-padding-top: 24px; }\nbody { margin: 0; background: var(--canvas); color: var(--i'
    'nk); font: 16px/1.5 "Segoe UI", system-ui, sans-serif; overflow-wrap: anywhere; }\n[hidden] { display'
    ': none !important; }\nbutton, input, select { font: inherit; }\nbutton, select, input { min-height: 40'
    'px; border: 1px solid var(--field-line); border-radius: var(--radius); background: var(--surface); c'
    'olor: var(--ink); padding: 6px 12px; }\nbutton { cursor: pointer; font-weight: 600; }\nbutton:hover:no'
    't(:disabled), select:hover, input:hover { background: var(--wash); }\nbutton.primary { background: va'
    'r(--accent); color: var(--on-accent); border-color: var(--accent); }\nbutton.primary:hover:not(:disab'
    'led) { background: var(--accent-hover); }\na { color: var(--accent); text-underline-offset: 3px; }\n:f'
    'ocus-visible { outline: 3px solid var(--accent); outline-offset: 3px; }\n.skip { position: absolute; '
    'left: 16px; top: -100px; z-index: 5; padding: 12px 16px; background: var(--surface); border: 2px sol'
    'id var(--accent); }\n.skip:focus { top: 12px; }\n.toolbar { border-bottom: 1px solid var(--chrome-line'
    '); background: var(--chrome); color: var(--on-chrome); }\n.toolbar-inner { max-width: 1440px; margin:'
    ' auto; display: flex; gap: 16px; align-items: center; justify-content: space-between; padding: 14px '
    '32px; flex-wrap: wrap; }\n.toolbar-title { font-size: 18px; font-weight: 600; }\n.toolbar-controls { d'
    'isplay: flex; flex-wrap: wrap; gap: 10px; align-items: center; }\n.toolbar button { background: trans'
    'parent; color: var(--on-chrome); border-color: var(--chrome-line); font-size: 14px; }\n.toolbar butto'
    'n:hover:not(:disabled) { background: var(--chrome-hover); }\n.toolbar button.primary { background: #f'
    'fffff; color: #002b4e; border-color: #ffffff; }\n.brand-ribbon { display: flex; height: 5px; }\n.brand'
    '-ribbon span { flex: 1; }\n.brand-ribbon .navy { background: var(--brand-navy); }\n.brand-ribbon .lava'
    ' { background: var(--brand-lava); }\n.brand-ribbon .steel { background: var(--brand-steel); }\n.brand-'
    'ribbon .teal { background: var(--brand-teal); }\n.shell { max-width: 1440px; margin: auto; display: g'
    'rid; grid-template-columns: 230px minmax(0, 1fr); }\n.contents { padding: 32px 20px 24px 28px; align-'
    'self: start; position: sticky; top: 0; background: var(--nav); min-height: calc(100vh - 70px); }\n.co'
    'ntents h2 { font-size: 16px; margin: 0 0 12px; color: var(--nav-ink); }\n.contents ol { padding: 0; m'
    'argin: 0; list-style: none; display: grid; gap: 4px; }\n.contents a { display: block; font-size: 14px'
    '; padding: 8px; border-radius: var(--radius); color: var(--nav-ink); text-decoration: none; }\n.conte'
    'nts a:hover, .contents a:focus-visible { background: var(--accent-wash); color: var(--accent); }\n.do'
    'cument { min-width: 0; background: var(--surface); border-left: 1px solid var(--line); padding: 40px'
    ' 44px 32px; }\nh1 { margin: 0 0 16px; font-size: 36px; line-height: 1.25; font-weight: 600; letter-sp'
    'acing: -.02em; color: var(--cover-ink); }\nh2 { margin: 0 0 14px; font-size: 26px; line-height: 1.3; '
    'font-weight: 600; color: var(--cover-ink); }\nh3 { margin: 0 0 10px; font-size: 19px; line-height: 1.'
    '35; font-weight: 600; }\np { margin: 0 0 14px; }\n.muted { color: var(--muted); font-size: 14px; }\n.co'
    'ver-head { display: grid; grid-template-columns: minmax(0, 1fr) 220px; gap: 28px; align-items: start'
    '; background: var(--cover); border: 1px solid var(--line); padding: 24px; border-radius: var(--radiu'
    's); }\n.brand-plaque { color-scheme: only light; background: #ffffff; color: #334155; border: 1px sol'
    'id #cbd5e1; width: 220px; max-width: 100%; min-height: 76px; padding: 14px; display: flex; align-ite'
    'ms: center; justify-content: center; }\n.brand-plaque img { max-width: 100%; max-height: 56px; object'
    '-fit: contain; display: block; }\n.brand-placeholder { color: #334155; font-size: 19px; font-weight: '
    '600; letter-spacing: .04em; }\n.client-name { margin: 8px 0 0; font-size: 17px; font-weight: 600; col'
    'or: var(--cover-ink); }\n.provenance { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 20px; }\n'
    '.badge { display: inline-block; font-size: 12px; font-weight: 600; border: 1px solid var(--line); ba'
    'ckground: var(--subtle); padding: 3px 8px; border-radius: var(--radius); }\n.badge.critical { backgro'
    'und: var(--critical-wash); color: var(--critical); border-color: var(--critical); }\n.badge.high { ba'
    'ckground: var(--high-wash); color: var(--high); border-color: var(--high); }\n.badge.medium { backgro'
    'und: var(--medium-wash); color: var(--medium); border-color: var(--medium); }\n.badge.low { backgroun'
    'd: var(--low-wash); color: var(--low); border-color: var(--low); }\n.badge.OBSERVED { background: var'
    '(--observed-wash); color: var(--observed); border-color: var(--observed); }\n.badge.INFERRED { backgr'
    'ound: var(--inferred-wash); color: var(--inferred); border-color: var(--inferred); }\n.badge.UNKNOWN '
    '{ background: var(--unknown-wash); color: var(--unknown); border-color: var(--unknown); }\n.cover-fac'
    'ts { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 18px 24px; padding: 24px '
    '0; margin: 0; }\ndt { font-size: 13px; color: var(--muted); margin-bottom: 4px; }\ndd { margin: 0; fon'
    't-size: 15px; font-weight: 600; }\n.chapter { padding-top: 44px; margin-top: 40px; border-top: 1px so'
    'lid var(--line); min-width: 0; }\n.score-layout { display: grid; grid-template-columns: 240px minmax('
    '0, 1fr); gap: 32px; margin: 24px 0; }\n.global-index { padding-right: 24px; border-right: 1px solid v'
    'ar(--line); }\n.score-value { display: block; font-size: 42px; font-weight: 600; font-variant-numeric'
    ': tabular-nums; margin: 10px 0; }\n.score-row { margin-bottom: 14px; }\n.score-row-head { display: fle'
    'x; justify-content: space-between; font-size: 14px; font-weight: 600; margin-bottom: 6px; }\n.score-t'
    'rack { height: 8px; background: var(--wash); border-radius: 2px; overflow: hidden; border: 1px solid'
    ' var(--line); }\n.score-fill { background: var(--brand-lava); height: 100%; }\n.assessment-chart { mar'
    'gin: 24px 0; display: grid; grid-template-columns: 200px minmax(0, 1fr); gap: 28px; align-items: cen'
    'ter; padding: 20px; background: var(--accent-wash); border: 1px solid var(--line); }\n.assessment-cha'
    'rt svg { width: 180px; height: auto; display: block; margin: auto; }\n.filters { display: flex; flex-'
    'wrap: wrap; gap: 12px; align-items: flex-end; margin: 16px 0; padding: 16px; background: var(--subtl'
    'e); border: 1px solid var(--line); border-radius: var(--radius); }\n.filter-field { display: grid; ga'
    'p: 4px; font-size: 13px; font-weight: 600; }\n.tabs { display: flex; gap: 8px; flex-wrap: wrap; margi'
    'n: 16px 0; border-bottom: 1px solid var(--line); padding-bottom: 8px; }\n.tabs button[aria-selected="'
    'true"] { background: var(--accent); color: var(--on-accent); border-color: var(--accent); }\n.table-w'
    'rap { overflow-x: auto; margin: 16px 0; border: 1px solid var(--line); }\ntable { width: 100%; border'
    '-collapse: collapse; font-size: 14px; text-align: left; }\nth, td { padding: 10px 12px; border-bottom'
    ': 1px solid var(--line); vertical-align: top; }\nth { background: var(--subtle); font-weight: 600; }\n'
    '.graph-box { overflow-x: auto; border: 1px solid var(--line); background: var(--subtle); padding: 16'
    'px; margin: 16px 0; }\n.graph-box svg { min-width: 720px; width: 100%; height: auto; display: block; '
    '}\n.finops-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 24px; margin:'
    ' 20px 0; }\n.finops-panel { padding: 20px; border: 1px solid var(--line); background: var(--subtle); '
    '}\n.finops-amount { font-size: 34px; font-weight: 600; margin: 8px 0; }\n.error-banner { padding: 20px'
    '; border: 2px solid var(--critical); background: var(--critical-wash); color: var(--critical); margi'
    'n: 20px 0; }\n@media (max-width: 960px) {\n  .shell { grid-template-columns: 1fr; }\n  .contents { posi'
    'tion: static; min-height: auto; border-bottom: 1px solid var(--line); }\n  .document { border-left: 0'
    '; padding: 24px 16px; }\n  .cover-head, .score-layout, .assessment-chart, .finops-grid, .cover-facts '
    '{ grid-template-columns: 1fr; }\n  .global-index { border-right: 0; padding-right: 0; border-bottom: '
    '1px solid var(--line); padding-bottom: 16px; }\n}\n@media print {\n  .toolbar, .filters, .tabs, .no-pri'
    'nt { display: none !important; }\n  .shell { display: block; }\n  .contents { display: none; }\n  .docu'
    'ment { border: 0; padding: 0; }\n  [hidden].print-show { display: block !important; }\n}\n</style>\n</he'
    'ad>\n<body>\n<a class="skip" href="#main-document">Saltar al contenido principal</a>\n<header class="to'
    'olbar">\n  <div class="toolbar-inner">\n    <div class="toolbar-title">Dossier de Dependencias y Confi'
    'guración Azure Databricks</div>\n    <div class="toolbar-controls">\n      <label id="workspace-select'
    'or-wrap" hidden>Workspace:\n        <select id="workspace-selector" aria-label="Seleccionar workspace'
    '"></select>\n      </label>\n      <button type="button" id="theme-toggle">Modo oscuro</button>\n      '
    '<button type="button" id="export-json-btn">Exportar JSON</button>\n      <button type="button" id="ex'
    'port-deps-csv-btn">Exportar Dependencias CSV</button>\n      <button type="button" id="export-finding'
    's-csv-btn">Exportar Hallazgos CSV</button>\n      <button type="button" class="primary" id="print-btn'
    '">Imprimir / PDF</button>\n    </div>\n  </div>\n  <div class="brand-ribbon" aria-hidden="true">\n    <s'
    'pan class="navy"></span><span class="lava"></span><span class="steel"></span><span class="teal"></sp'
    'an>\n  </div>\n</header>\n<div class="shell">\n  <nav class="contents" aria-label="Índice del informe">\n'
    '    <h2>Contenido</h2>\n    <ol>\n      <li><a href="#sec-cover">1. Portada y procedencia</a></li>\n   '
    '   <li><a href="#sec-executive">2. Resumen ejecutivo y WAF</a></li>\n      <li><a href="#sec-dependen'
    'cies">3. Mapa de dependencias</a></li>\n      <li><a href="#sec-inventory">4. Inventario Lakehouse y '
    'ARM</a></li>\n      <li><a href="#sec-findings">5. Hallazgos y reglas</a></li>\n      <li><a href="#se'
    'c-finops">6. FinOps y capacidad</a></li>\n      <li><a href="#sec-actions">7. Plan de acción</a></li>'
    '\n      <li><a href="#sec-sources">8. Fuentes y metodología</a></li>\n    </ol>\n  </nav>\n  <main class'
    '="document" id="main-document">\n    <div id="opening-state" class="error-banner" hidden></div>\n    <'
    'div id="multi-overview" hidden></div>\n    <div id="workspace-error-view" class="error-banner" hidden'
    '></div>\n    <div id="report-body" hidden>\n      <section id="sec-cover">\n        <div class="cover-h'
    'ead">\n          <div>\n            <h1 id="cover-title">Revisión de arquitectura, dependencias y conf'
    'iguración de Azure Databricks</h1>\n            <p class="muted" id="cover-subtitle"></p>\n           '
    ' <div class="provenance" id="cover-badges"></div>\n          </div>\n          <div class="brand">\n   '
    '         <div class="brand-plaque" id="brand-plaque"></div>\n            <p class="client-name" id="c'
    'lient-name-label"></p>\n          </div>\n        </div>\n        <dl class="cover-facts" id="cover-fac'
    'ts"></dl>\n        <p class="muted" id="cover-resource-id"></p>\n      </section>\n\n      <section clas'
    's="chapter" id="sec-executive">\n        <h2>2. Lectura ejecutiva, cobertura e indicadores locales</h'
    '2>\n        <p class="muted">El índice local mide únicamente las reglas evaluadas sobre evidencia obs'
    'ervada. Nunca sustituye una evaluación oficial de Microsoft Well-Architected ni oculta fuentes no ev'
    'aluadas.</p>\n        <ul id="executive-messages"></ul>\n        <div class="score-layout">\n          '
    '<div class="global-index" id="global-score-box"></div>\n          <div>\n            <h3>Desglose por '
    'área (Buenas prácticas, Seguridad, FinOps, Optimización)</h3>\n            <div id="area-scores"></di'
    'v>\n            <h3>Desglose por pilar Well-Architected</h3>\n            <div id="pillar-scores"></di'
    'v>\n          </div>\n        </div>\n        <figure class="assessment-chart">\n          <div id="donu'
    't-holder"></div>\n          <div>\n            <h3>Distribución de comprobaciones</h3>\n            <di'
    'v class="table-wrap"><table id="check-status-table"></table></div>\n          </div>\n        </figure'
    '>\n        <h3>Prioridades críticas y de alta severidad observadas</h3>\n        <div class="table-wra'
    'p"><table id="priority-findings-table"></table></div>\n      </section>\n\n      <section class="chapte'
    'r" id="sec-dependencies">\n        <h2>3. Mapa de dependencias y arquitectura Lakehouse</h2>\n        '
    '<p class="muted">Cada relación se clasifica explícitamente como <strong>OBSERVED</strong> (join exac'
    'to de ID/clave nativa confirmado en las APIs), <strong>INFERRED</strong> (referencia explícita de UR'
    'I/host hacia un recurso no recolectado en ARM) o <strong>UNKNOWN</strong> (linaje dinámico en tiempo'
    ' de ejecución o alcance no consultado sin arrancar cómputo).</p>\n        <div class="tabs" role="tab'
    'list" aria-label="Vistas de arquitectura y dependencias">\n          <button type="button" role="tab"'
    ' id="tab-dep-observed" aria-selected="true">Mapa de dependencias observado e inferido</button>\n     '
    '     <button type="button" role="tab" id="tab-dep-reference" aria-selected="false">Propuesta de refe'
    'rencia - NO desplegada</button>\n        </div>\n        <div id="panel-dep-observed" class="print-sho'
    'w">\n          <div class="filters">\n            <label class="filter-field">Capa\n              <sele'
    'ct id="dep-layer-filter">\n                <option value="all">Todas las capas</option>\n             '
    '   <option value="control_plane">Plano de control (ARM)</option>\n                <option value="comp'
    'ute">Cómputo (Clústeres / Pools / Warehouses)</option>\n                <option value="orchestration"'
    '>Orquestación (Jobs / Tareas / Pipelines)</option>\n                <option value="governance">Gobern'
    'anza (Unity Catalog / Secret Scopes)</option>\n                <option value="associated_resource">Re'
    'cursos Azure asociados</option>\n              </select>\n            </label>\n            <label clas'
    's="filter-field">Clasificación\n              <select id="dep-class-filter">\n                <option '
    'value="all">Todas (OBSERVED / INFERRED / UNKNOWN)</option>\n                <option value="OBSERVED">'
    'OBSERVED (Join nativo exacto)</option>\n                <option value="INFERRED">INFERRED (Referencia'
    ' URI/host)</option>\n                <option value="UNKNOWN">UNKNOWN (Punto ciego explícito)</option>'
    '\n              </select>\n            </label>\n            <label class="filter-field">Buscar nodo / '
    'carga\n              <input type="search" id="dep-search-filter" placeholder="Job, clúster, catálogo,'
    ' cuenta ADLS...">\n            </label>\n          </div>\n          <div class="graph-box" id="dep-gra'
    'ph-box"></div>\n          <h3>Relaciones de dependencia (<span id="dep-edges-count">0</span>)</h3>\n  '
    '        <div class="table-wrap"><table id="dep-edges-table"></table></div>\n          <h3>Nodos del g'
    'rafo (<span id="dep-nodes-count">0</span>)</h3>\n          <div class="table-wrap"><table id="dep-nod'
    'es-table"></table></div>\n          <h3>Referencias rotas detectadas (<span id="dep-broken-count">0</'
    'span>)</h3>\n          <div class="table-wrap"><table id="dep-broken-table"></table></div>\n          '
    '<h3>Puntos ciegos y alcances UNKNOWN (<span id="dep-unknowns-count">0</span>)</h3>\n          <div cl'
    'ass="table-wrap"><table id="dep-unknowns-table"></table></div>\n        </div>\n        <div id="panel'
    '-dep-reference" class="print-show" hidden>\n          <h3>Arquitectura de referencia Azure Databricks'
    ' Lakehouse — Propuesta NO desplegada</h3>\n          <p class="muted">Este diagrama representa la lín'
    'ea base recomendada por Microsoft y Databricks Well-Architected Lakehouse. <strong>No representa rec'
    'ursos desplegados en el entorno del cliente.</strong></p>\n          <div class="graph-box" id="ref-a'
    'rch-box"></div>\n          <div class="table-wrap"><table id="ref-arch-table"></table></div>\n        '
    '</div>\n      </section>\n\n      <section class="chapter" id="sec-inventory">\n        <h2>4. Inventari'
    'o de Workspace, Cómputo, Orquestación, Unity Catalog y Recursos Asociados</h2>\n        <h3>Clústeres'
    ' All-Purpose, Job Clusters, Instance Pools y Cluster Policies</h3>\n        <div class="table-wrap"><'
    'table id="inv-compute-table"></table></div>\n        <h3>Jobs, DAG de tareas, Pipelines declarativos '
    '(Lakeflow / DLT) y SQL Warehouses</h3>\n        <div class="table-wrap"><table id="inv-orchestration-'
    'table"></table></div>\n        <h3>Unity Catalog (Metastore, Catálogos, Esquemas, Storage Credentials'
    ', External Locations, Conexiones) y Secret Scopes</h3>\n        <div class="table-wrap"><table id="in'
    'v-uc-table"></table></div>\n        <h3>Recursos Azure asociados y Endpoints de dependencia saliente '
    'del plano de control</h3>\n        <div class="table-wrap"><table id="inv-resources-table"></table></'
    'div>\n      </section>\n\n      <section class="chapter" id="sec-findings">\n        <h2>5. Hallazgos y '
    'evaluación detallada de reglas</h2>\n        <div class="filters">\n          <label class="filter-fie'
    'ld">Área\n            <select id="find-area-filter">\n              <option value="all">Todas</option>'
    '\n              <option value="best_practices">Buenas prácticas</option>\n              <option value='
    '"security">Seguridad</option>\n              <option value="finops">FinOps</option>\n              <op'
    'tion value="optimization">Optimización</option>\n            </select>\n          </label>\n          <'
    'label class="filter-field">Nivel\n            <select id="find-level-filter">\n              <option v'
    'alue="all">Todos</option>\n              <option value="workspace">Workspace / Gobernanza</option>\n  '
    '            <option value="workload">Workload (Cómputo / Jobs / SQL)</option>\n              <option '
    'value="resource">Recurso Azure asociado</option>\n            </select>\n          </label>\n          '
    '<label class="filter-field">Severidad\n            <select id="find-sev-filter">\n              <optio'
    'n value="all">Todas</option>\n              <option value="critical">Crítica</option>\n              <'
    'option value="high">Alta</option>\n              <option value="medium">Media</option>\n              '
    '<option value="low">Baja</option>\n            </select>\n          </label>\n          <label class="f'
    'ilter-field">Estado\n            <select id="find-status-filter">\n              <option value="all">T'
    'odos</option>\n              <option value="failed">No cumple (failed)</option>\n              <option'
    ' value="passed">Cumple (passed)</option>\n              <option value="not_evaluated">No evaluado</op'
    'tion>\n              <option value="not_applicable">No aplica</option>\n            </select>\n        '
    '  </label>\n          <label class="filter-field">Buscar recurso / carga\n            <input type="sea'
    'rch" id="find-search-filter" placeholder="Filtrar por regla, job, clúster...">\n          </label>\n  '
    '      </div>\n        <p class="muted" id="findings-count-label"></p>\n        <div class="table-wrap"'
    '><table id="findings-table"></table></div>\n      </section>\n\n      <section class="chapter" id="sec-'
    'finops">\n        <h2>6. FinOps, costes observados y candidatos de optimización</h2>\n        <div cla'
    'ss="finops-grid">\n          <div class="finops-panel">\n            <h3>Coste real observado (ARM Act'
    'ualCost)</h3>\n            <div class="finops-amount" id="finops-actual-cost"></div>\n            <p c'
    'lass="muted" id="finops-cost-note"></p>\n          </div>\n          <div class="finops-panel">\n      '
    '      <h3>Ahorro estimado</h3>\n            <div class="finops-amount">Por estimar / No calculado</di'
    'v>\n            <p class="muted">No se inventan ahorros DBU ni descuentos sin medir el consumo histór'
    'ico en system.billing.usage y validar compromisos comerciales.</p>\n          </div>\n        </div>\n '
    '       <h3>Candidatos de eficiencia operativa y FinOps</h3>\n        <div class="table-wrap"><table i'
    'd="finops-candidates-table"></table></div>\n        <h3>Filas de facturación ARM observadas</h3>\n    '
    '    <div class="table-wrap"><table id="finops-cost-table"></table></div>\n      </section>\n\n      <se'
    'ction class="chapter" id="sec-actions">\n        <h2>7. Plan de acción priorizado para revisión human'
    'a</h2>\n        <p class="muted">Los horizontes Quick-win (&lt;1 semana), Corto plazo (1-3 meses) y M'
    'edio plazo son categorías orientativas de planificación, no promesas de entrega ni cambios automátic'
    'os.</p>\n        <div class="table-wrap"><table id="actions-table"></table></div>\n      </section>\n\n '
    '     <section class="chapter" id="sec-sources">\n        <h2>8. Registro de fuentes, recibos HTTP y l'
    'ímites metodológicos</h2>\n        <div class="table-wrap"><table id="sources-table"></table></div>\n '
    '       <h3>Limitaciones y reglas de interpretación</h3>\n        <ul id="methodology-limitations"></u'
    'l>\n      </section>\n    </div>\n  </main>\n</div>\n<script type="application/json" id="report-data">__R'
    'EPORT_DATA_JSON__</script>\n<script>\n(function () {\n  "use strict";\n  function el(tag, attrs, childre'
    'n) {\n    var node = document.createElement(tag);\n    if (attrs) {\n      Object.keys(attrs).forEach(f'
    'unction (k) {\n        if (k === "text") { node.textContent = String(attrs[k]); }\n        else if (k '
    '=== "className") { node.className = attrs[k]; }\n        else if (attrs[k] !== null && attrs[k] !== u'
    'ndefined) { node.setAttribute(k, String(attrs[k])); }\n      });\n    }\n    if (children) {\n      chil'
    'dren.forEach(function (c) {\n        if (typeof c === "string" || typeof c === "number") { node.appen'
    'dChild(document.createTextNode(String(c))); }\n        else if (c) { node.appendChild(c); }\n      });'
    '\n    }\n    return node;\n  }\n  function clear(node) { while (node.firstChild) { node.removeChild(node'
    '.firstChild); } }\n  function safeLearnUrl(u) {\n    if (typeof u !== "string") { return null; }\n    t'
    'ry {\n      var parsed = new URL(u);\n      return (parsed.protocol === "https:" && (parsed.hostname ='
    '== "learn.microsoft.com" || parsed.hostname === "docs.databricks.com")) ? u : null;\n    } catch (e) '
    '{ return null; }\n  }\n  function renderTable(tableNode, headers, rows) {\n    clear(tableNode);\n    va'
    'r thead = el("thead"), trHead = el("tr");\n    headers.forEach(function (h) { trHead.appendChild(el("'
    'th", { text: h })); });\n    thead.appendChild(trHead);\n    tableNode.appendChild(thead);\n    var tbo'
    'dy = el("tbody");\n    if (!rows.length) {\n      var trEmpty = el("tr");\n      trEmpty.appendChild(el'
    '("td", { colspan: headers.length, text: "Sin registros en este alcance o filtro." }));\n      tbody.a'
    'ppendChild(trEmpty);\n    } else {\n      rows.forEach(function (cells) {\n        var tr = el("tr");\n '
    '       cells.forEach(function (c) {\n          var td = el("td");\n          if (c instanceof Node) { '
    'td.appendChild(c); }\n          else { td.textContent = c === null || c === undefined ? "—" : String('
    'c); }\n          tr.appendChild(td);\n        });\n        tbody.appendChild(tr);\n      });\n    }\n    t'
    'ableNode.appendChild(tbody);\n  }\n\n  var rawText = document.getElementById("report-data").textContent'
    ';\n  var rootData;\n  try {\n    rootData = JSON.parse(rawText);\n  } catch (e) {\n    var openErr = docu'
    'ment.getElementById("opening-state");\n    openErr.hidden = false;\n    openErr.textContent = "Error a'
    'l cargar el modelo JSON embebido del informe.";\n    return;\n  }\n\n  var isMulti = rootData && rootDat'
    'a.schema_version === "databricks-dep-multi-workspace-v1";\n  var currentSnap = null;\n\n  var themeBtn '
    '= document.getElementById("theme-toggle");\n  themeBtn.addEventListener("click", function () {\n    va'
    'r dark = document.documentElement.getAttribute("data-theme") === "dark";\n    if (dark) {\n      docum'
    'ent.documentElement.removeAttribute("data-theme");\n      themeBtn.textContent = "Modo oscuro";\n    }'
    ' else {\n      document.documentElement.setAttribute("data-theme", "dark");\n      themeBtn.textConten'
    't = "Modo claro";\n    }\n  });\n  document.getElementById("print-btn").addEventListener("click", funct'
    'ion () { window.print(); });\n\n  function downloadBlob(filename, content, mime) {\n    var blob = new '
    'Blob([content], { type: mime });\n    var url = URL.createObjectURL(blob);\n    var a = el("a", { href'
    ': url, download: filename });\n    document.body.appendChild(a);\n    a.click();\n    document.body.rem'
    'oveChild(a);\n    URL.revokeObjectURL(url);\n  }\n  function csvEscape(v) {\n    if (v === null || v ==='
    ' undefined) { return ""; }\n    var s = typeof v === "object" ? JSON.stringify(v) : String(v);\n    if'
    ' (/^[=+\\-@\\t\\r\\n]/.test(s.trimLeft())) { s = "\'" + s; }\n    return \'"\' + s.replace(/"/g, \'""\') + \'"\''
    ';\n  }\n  document.getElementById("export-json-btn").addEventListener("click", function () {\n    downl'
    'oadBlob("databricks-dependency-snapshot.json", JSON.stringify(rootData, null, 2), "application/json;'
    'charset=utf-8");\n  });\n  document.getElementById("export-deps-csv-btn").addEventListener("click", fu'
    'nction () {\n    if (!currentSnap) { return; }\n    var cols = ["record_type", "classification", "laye'
    'r", "id", "kind", "label", "from", "to", "relation", "join_fields", "source_ids"];\n    var lines = ['
    'cols.join(",")];\n    var dep = currentSnap.dependencies;\n    [].concat(dep.nodes || [], dep.edges ||'
    ' [], dep.unknowns || []).forEach(function (r) {\n      lines.push(cols.map(function (c) { return csvE'
    'scape(r[c]); }).join(","));\n    });\n    downloadBlob("databricks-dependencies.csv", "\\uFEFF" + lines'
    '.join("\\r\\n"), "text/csv;charset=utf-8");\n  });\n  document.getElementById("export-findings-csv-btn")'
    '.addEventListener("click", function () {\n    if (!currentSnap) { return; }\n    var cols = ["check_id'
    '", "rule_id", "title", "status", "level", "area", "pillar", "severity", "workload_name", "reason", "'
    'recommendation", "learn_url"];\n    var lines = [cols.join(",")];\n    (currentSnap.checks || []).forE'
    'ach(function (r) {\n      lines.push(cols.map(function (c) { return csvEscape(r[c]); }).join(","));\n '
    '   });\n    downloadBlob("databricks-findings.csv", "\\uFEFF" + lines.join("\\r\\n"), "text/csv;charset='
    'utf-8");\n  });\n\n  var tabObs = document.getElementById("tab-dep-observed");\n  var tabRef = document.'
    'getElementById("tab-dep-reference");\n  var panelObs = document.getElementById("panel-dep-observed");'
    '\n  var panelRef = document.getElementById("panel-dep-reference");\n  tabObs.addEventListener("click",'
    ' function () {\n    tabObs.setAttribute("aria-selected", "true");\n    tabRef.setAttribute("aria-selec'
    'ted", "false");\n    panelObs.hidden = false;\n    panelRef.hidden = true;\n  });\n  tabRef.addEventList'
    'ener("click", function () {\n    tabObs.setAttribute("aria-selected", "false");\n    tabRef.setAttribu'
    'te("aria-selected", "true");\n    panelObs.hidden = true;\n    panelRef.hidden = false;\n  });\n\n  funct'
    'ion renderDonut(scoreObj) {\n    var holder = document.getElementById("donut-holder");\n    clear(hold'
    'er);\n    var svgNS = "http://www.w3.org/2000/svg";\n    var svg = document.createElementNS(svgNS, "sv'
    'g");\n    svg.setAttribute("viewBox", "0 0 120 120");\n    svg.setAttribute("role", "img");\n    svg.se'
    'tAttribute("aria-label", "Distribución de comprobaciones");\n    var bg = document.createElementNS(sv'
    'gNS, "circle");\n    bg.setAttribute("cx", "60"); bg.setAttribute("cy", "60"); bg.setAttribute("r", "'
    '46");\n    bg.setAttribute("fill", "none"); bg.setAttribute("stroke", "#cbd5e1"); bg.setAttribute("st'
    'roke-width", "14");\n    svg.appendChild(bg);\n    var total = Math.max(1, scoreObj.total || 0);\n    v'
    'ar segments = [\n      { count: scoreObj.passed || 0, color: "#00875a" },\n      { count: scoreObj.fai'
    'led || 0, color: "#ff3621" },\n      { count: scoreObj.not_evaluated || 0, color: "#64748b" },\n      '
    '{ count: scoreObj.not_applicable || 0, color: "#cbd5e1" }\n    ];\n    var circumference = 2 * Math.PI'
    ' * 46;\n    var offset = 0;\n    segments.forEach(function (seg) {\n      if (!seg.count) { return; }\n '
    '     var len = (seg.count / total) * circumference;\n      var circle = document.createElementNS(svgN'
    'S, "circle");\n      circle.setAttribute("cx", "60"); circle.setAttribute("cy", "60"); circle.setAttr'
    'ibute("r", "46");\n      circle.setAttribute("fill", "none"); circle.setAttribute("stroke", seg.color'
    ');\n      circle.setAttribute("stroke-width", "14");\n      circle.setAttribute("stroke-dasharray", le'
    'n + " " + (circumference - len));\n      circle.setAttribute("stroke-dashoffset", String(-offset));\n '
    '     circle.setAttribute("transform", "rotate(-90 60 60)");\n      svg.appendChild(circle);\n      off'
    'set += len;\n    });\n    var txt = document.createElementNS(svgNS, "text");\n    txt.setAttribute("x",'
    ' "60"); txt.setAttribute("y", "58");\n    txt.setAttribute("text-anchor", "middle"); txt.setAttribute'
    '("font-size", "20"); txt.setAttribute("font-weight", "600");\n    txt.setAttribute("fill", "currentCo'
    'lor");\n    txt.textContent = String(scoreObj.total || 0);\n    svg.appendChild(txt);\n    var sub = do'
    'cument.createElementNS(svgNS, "text");\n    sub.setAttribute("x", "60"); sub.setAttribute("y", "74");'
    '\n    sub.setAttribute("text-anchor", "middle"); sub.setAttribute("font-size", "10");\n    sub.setAttr'
    'ibute("fill", "currentColor");\n    sub.textContent = "controles";\n    svg.appendChild(sub);\n    hold'
    'er.appendChild(svg);\n  }\n\n  function renderNeighborhoodSvg(nodes, edges) {\n    var box = document.ge'
    'tElementById("dep-graph-box");\n    clear(box);\n    var subset = nodes.slice(0, 13);\n    var svgNS = '
    '"http://www.w3.org/2000/svg";\n    var svg = document.createElementNS(svgNS, "svg");\n    svg.setAttri'
    'bute("viewBox", "0 0 860 320");\n    svg.setAttribute("role", "img");\n    svg.setAttribute("aria-labe'
    'l", "Subgrafo vecindario de dependencias (máximo 13 nodos visibles)");\n    var pos = {};\n    subset.'
    'forEach(function (n, idx) {\n      var col = idx % 4;\n      var row = Math.floor(idx / 4);\n      pos['
    'n.id] = { x: 110 + col * 210, y: 50 + row * 82, node: n };\n    });\n    edges.forEach(function (e) {\n'
    '      if (!pos[e.from] || !pos[e.to]) { return; }\n      var line = document.createElementNS(svgNS, "'
    'line");\n      line.setAttribute("x1", String(pos[e.from].x));\n      line.setAttribute("y1", String(p'
    'os[e.from].y));\n      line.setAttribute("x2", String(pos[e.to].x));\n      line.setAttribute("y2", St'
    'ring(pos[e.to].y));\n      line.setAttribute("stroke", e.classification === "INFERRED" ? "#b45309" : '
    '"#003865");\n      line.setAttribute("stroke-width", "2");\n      if (e.classification === "INFERRED")'
    ' { line.setAttribute("stroke-dasharray", "5,4"); }\n      svg.appendChild(line);\n    });\n    subset.f'
    'orEach(function (n) {\n      var p = pos[n.id];\n      var g = document.createElementNS(svgNS, "g");\n '
    '     var rect = document.createElementNS(svgNS, "rect");\n      rect.setAttribute("x", String(p.x - 8'
    '5));\n      rect.setAttribute("y", String(p.y - 22));\n      rect.setAttribute("width", "170");\n      '
    'rect.setAttribute("height", "44");\n      rect.setAttribute("rx", "4");\n      rect.setAttribute("fill'
    '", n.classification === "INFERRED" ? "#fff8d6" : "#eef4f9");\n      rect.setAttribute("stroke", n.cla'
    'ssification === "INFERRED" ? "#795b00" : "#003865");\n      rect.setAttribute("stroke-width", "1.5");'
    '\n      g.appendChild(rect);\n      var t1 = document.createElementNS(svgNS, "text");\n      t1.setAttr'
    'ibute("x", String(p.x)); t1.setAttribute("y", String(p.y - 4));\n      t1.setAttribute("text-anchor",'
    ' "middle"); t1.setAttribute("font-size", "11"); t1.setAttribute("font-weight", "600");\n      t1.setA'
    'ttribute("fill", "#002b4e");\n      t1.textContent = (n.label || n.id).slice(0, 24);\n      g.appendCh'
    'ild(t1);\n      var t2 = document.createElementNS(svgNS, "text");\n      t2.setAttribute("x", String(p'
    '.x)); t2.setAttribute("y", String(p.y + 12));\n      t2.setAttribute("text-anchor", "middle"); t2.set'
    'Attribute("font-size", "9");\n      t2.setAttribute("fill", "#334e68");\n      t2.textContent = n.kind'
    ' + " [" + n.classification + "]";\n      g.appendChild(t2);\n      svg.appendChild(g);\n    });\n    box'
    '.appendChild(svg);\n    box.appendChild(el("p", {\n      className: "muted",\n      text: "Mostrando " '
    '+ subset.length + " de " + nodes.length + " nodos filtrados en vista gráfica acotada (máximo 13 nodo'
    's). Las tablas inferiores contienen el 100% de los nodos, aristas y puntos ciegos."\n    }));\n  }\n\n  '
    'function renderReferenceArchitecture() {\n    var box = document.getElementById("ref-arch-box");\n    '
    'clear(box);\n    var svgNS = "http://www.w3.org/2000/svg";\n    var svg = document.createElementNS(svg'
    'NS, "svg");\n    svg.setAttribute("viewBox", "0 0 860 220");\n    svg.setAttribute("role", "img");\n   '
    ' svg.setAttribute("aria-label", "Arquitectura de referencia Azure Databricks Lakehouse - Propuesta N'
    'O desplegada");\n    var boxes = [\n      { x: 20, y: 30, w: 185, h: 70, title: "Red y Perímetro (ARM)'
    '", sub: "VNet Injection + SCC + Private Link" },\n      { x: 235, y: 30, w: 185, h: 70, title: "Ident'
    'idad y Secretos", sub: "Entra SP/UAMI + Key Vault Scopes" },\n      { x: 450, y: 30, w: 185, h: 70, t'
    'itle: "Cómputo y Orquestación", sub: "Cluster Policies + Job/Serverless" },\n      { x: 665, y: 30, w'
    ': 175, h: 70, title: "Unity Catalog & ADLS", sub: "Access Connector UAMI + Linaje" }\n    ];\n    boxe'
    's.forEach(function (b, idx) {\n      var r = document.createElementNS(svgNS, "rect");\n      r.setAttr'
    'ibute("x", String(b.x)); r.setAttribute("y", String(b.y));\n      r.setAttribute("width", String(b.w)'
    '); r.setAttribute("height", String(b.h));\n      r.setAttribute("rx", "4"); r.setAttribute("fill", "#'
    'eef4f9"); r.setAttribute("stroke", "#003865"); r.setAttribute("stroke-width", "2");\n      svg.append'
    'Child(r);\n      var t = document.createElementNS(svgNS, "text");\n      t.setAttribute("x", String(b.'
    'x + 12)); t.setAttribute("y", String(b.y + 28));\n      t.setAttribute("font-size", "12"); t.setAttri'
    'bute("font-weight", "600"); t.setAttribute("fill", "#002b4e");\n      t.textContent = b.title;\n      '
    'svg.appendChild(t);\n      var s = document.createElementNS(svgNS, "text");\n      s.setAttribute("x",'
    ' String(b.x + 12)); s.setAttribute("y", String(b.y + 48));\n      s.setAttribute("font-size", "10"); '
    's.setAttribute("fill", "#334e68");\n      s.textContent = b.sub;\n      svg.appendChild(s);\n      if ('
    'idx < boxes.length - 1) {\n        var ln = document.createElementNS(svgNS, "line");\n        ln.setAt'
    'tribute("x1", String(b.x + b.w)); ln.setAttribute("y1", "65");\n        ln.setAttribute("x2", String('
    'boxes[idx + 1].x)); ln.setAttribute("y2", "65");\n        ln.setAttribute("stroke", "#ff3621"); ln.se'
    'tAttribute("stroke-width", "2");\n        svg.appendChild(ln);\n      }\n    });\n    var note = documen'
    't.createElementNS(svgNS, "text");\n    note.setAttribute("x", "20"); note.setAttribute("y", "150");\n '
    '   note.setAttribute("font-size", "12"); note.setAttribute("font-weight", "600"); note.setAttribute('
    '"fill", "#9c2b13");\n    note.textContent = "PROPUESTA DE REFERENCIA (NO DESPLEGADA): Integración ent'
    're tenants mediante Entra Multi-tenant FIC o Lighthouse + Databricks OIDC.";\n    svg.appendChild(not'
    'e);\n    box.appendChild(svg);\n    renderTable(document.getElementById("ref-arch-table"),\n      ["Com'
    'ponente de referencia", "Práctica recomendada Microsoft / Databricks", "Compromiso / Trade-off"],\n  '
    '    [\n        ["VNet Injection + Secure Cluster Connectivity", "Desplegar en VNet propia con enableN'
    'oPublicIp=true y subredes delegadas host/container con NSG.", "Exige planificación IPAM y rutas sali'
    'entes hacia endpoints de plano de control."],\n        ["Private Link (Front-end / Back-end / WebAuth'
    ')", "Aislar tráfico de usuarios y plano de datos mediante Private Endpoints aprobados y zonas DNS pr'
    'ivadas.", "Requiere SKU Premium y gestión de DNS privado entre redes hub-spoke."],\n        ["Unity C'
    'atalog + Access Connector (UAMI)", "Gobernar catálogos y External Locations con Storage Credentials '
    'basadas en Managed Identity.", "Sustituye claves compartidas y montajes DBFS heredados."],\n        ['
    '"Jobs sobre Job Compute / Serverless + Service Principal", "Ejecutar jobs productivos con run_as Ser'
    'vice Principal sobre cómputo efímero de Job o Serverless.", "Reduce coste DBU frente a All-Purpose y'
    ' evita fallos por baja de usuarios."],\n        ["Integración Cross-Tenant sin secretos", "Usar App m'
    'ultitenant con Federated Identity Credential (UAMI) o Azure Lighthouse (ARM) + Databricks OIDC Feder'
    'ation.", "Requiere consentimiento/asignación por administradores de ambos tenants."]\n      ]\n    );\n'
    '  }\n\n  function applyDependencyFilters() {\n    if (!currentSnap) { return; }\n    var layer = documen'
    't.getElementById("dep-layer-filter").value;\n    var cls = document.getElementById("dep-class-filter"'
    ').value;\n    var q = (document.getElementById("dep-search-filter").value || "").toLowerCase().trim()'
    ';\n    var dep = currentSnap.dependencies || { nodes: [], edges: [], unknowns: [], broken_references:'
    ' [] };\n    var nodes = (dep.nodes || []).filter(function (n) {\n      if (layer !== "all" && n.layer '
    '!== layer) { return false; }\n      if (cls !== "all" && n.classification !== cls) { return false; }\n'
    '      if (q && JSON.stringify(n).toLowerCase().indexOf(q) === -1) { return false; }\n      return tru'
    'e;\n    });\n    var edges = (dep.edges || []).filter(function (e) {\n      if (layer !== "all" && e.la'
    'yer !== layer) { return false; }\n      if (cls !== "all" && e.classification !== cls) { return false'
    '; }\n      if (q && JSON.stringify(e).toLowerCase().indexOf(q) === -1) { return false; }\n      return'
    ' true;\n    });\n    var unknowns = (dep.unknowns || []).filter(function (u) {\n      if (layer !== "al'
    'l" && u.layer !== layer) { return false; }\n      if (cls !== "all" && u.classification !== cls) { re'
    'turn false; }\n      if (q && JSON.stringify(u).toLowerCase().indexOf(q) === -1) { return false; }\n  '
    '    return true;\n    });\n    var nodeLabels = {};\n    (dep.nodes || []).forEach(function (n) { nodeL'
    'abels[n.id] = n.label + " (" + n.kind + ")"; });\n    renderNeighborhoodSvg(nodes, edges);\n    docume'
    'nt.getElementById("dep-edges-count").textContent = String(edges.length);\n    renderTable(document.ge'
    'tElementById("dep-edges-table"),\n      ["Clasificación", "Capa", "Origen", "Relación", "Destino", "C'
    'ampos Join", "Fuentes"],\n      edges.map(function (e) {\n        return [\n          el("span", { clas'
    'sName: "badge " + e.classification, text: e.classification }),\n          e.layer,\n          nodeLabe'
    'ls[e.from] || e.from,\n          e.relation,\n          nodeLabels[e.to] || e.to,\n          (e.join_fi'
    'elds || []).join(", "),\n          (e.source_ids || []).join(", ")\n        ];\n      })\n    );\n    doc'
    'ument.getElementById("dep-nodes-count").textContent = String(nodes.length);\n    renderTable(document'
    '.getElementById("dep-nodes-table"),\n      ["Clasificación", "Capa", "Tipo", "Nombre / Etiqueta", "Fu'
    'ente", "Evidencia"],\n      nodes.map(function (n) {\n        return [\n          el("span", { classNam'
    'e: "badge " + n.classification, text: n.classification }),\n          n.layer,\n          n.kind,\n    '
    '      n.label,\n          n.source_id,\n          JSON.stringify(n.evidence || {})\n        ];\n      })'
    '\n    );\n    var broken = dep.broken_references || [];\n    document.getElementById("dep-broken-count"'
    ').textContent = String(broken.length);\n    renderTable(document.getElementById("dep-broken-table"),\n'
    '      ["Objeto origen", "Tipo de referencia rota", "ID destino no encontrado"],\n      broken.map(fun'
    'ction (b) { return [b.source_object, b.kind, b.target_id]; })\n    );\n    document.getElementById("de'
    'p-unknowns-count").textContent = String(unknowns.length);\n    renderTable(document.getElementById("d'
    'ep-unknowns-table"),\n      ["Clasificación", "Capa", "Código", "Descripción del punto ciego", "Fuent'
    'es"],\n      unknowns.map(function (u) {\n        return [\n          el("span", { className: "badge UN'
    'KNOWN", text: "UNKNOWN" }),\n          u.layer,\n          u.code,\n          u.message,\n          (u.s'
    'ource_ids || []).join(", ")\n        ];\n      })\n    );\n  }\n\n  function applyFindingFilters() {\n    i'
    'f (!currentSnap) { return; }\n    var area = document.getElementById("find-area-filter").value;\n    v'
    'ar level = document.getElementById("find-level-filter").value;\n    var sev = document.getElementById'
    '("find-sev-filter").value;\n    var st = document.getElementById("find-status-filter").value;\n    var'
    ' q = (document.getElementById("find-search-filter").value || "").toLowerCase().trim();\n    var allCh'
    'ecks = currentSnap.checks || [];\n    var filtered = allChecks.filter(function (c) {\n      if (area !'
    '== "all" && c.area !== area) { return false; }\n      if (level !== "all" && c.level !== level) { ret'
    'urn false; }\n      if (sev !== "all" && c.severity !== sev) { return false; }\n      if (st !== "all"'
    ' && c.status !== st) { return false; }\n      if (q && JSON.stringify(c).toLowerCase().indexOf(q) ==='
    ' -1) { return false; }\n      return true;\n    });\n    document.getElementById("findings-count-label"'
    ').textContent = "Mostrando " + filtered.length + " de " + allChecks.length + " comprobaciones.";\n   '
    ' renderTable(document.getElementById("findings-table"),\n      ["Regla", "Estado", "Severidad", "Área'
    ' / Pilar", "Nivel / Carga", "Título y evidencia", "Recomendación"],\n      filtered.map(function (c) '
    '{\n        var link = safeLearnUrl(c.learn_url);\n        var recCell = el("div");\n        recCell.app'
    'endChild(el("p", { text: c.recommendation }));\n        if (link) { recCell.appendChild(el("a", { hre'
    'f: link, target: "_blank", rel: "noopener noreferrer", text: "Documentación oficial" })); }\n        '
    'var detailCell = el("div");\n        detailCell.appendChild(el("strong", { text: c.title }));\n       '
    ' detailCell.appendChild(el("p", { className: "muted", text: c.reason }));\n        return [\n         '
    ' c.rule_id + " (" + c.reference_id + ")",\n          c.status,\n          el("span", { className: "bad'
    'ge " + c.severity, text: c.severity_label || c.severity }),\n          c.area + " / " + c.pillar,\n   '
    '       c.level + (c.workload_name ? ": " + c.workload_name : ""),\n          detailCell,\n          re'
    'cCell\n        ];\n      })\n    );\n  }\n\n  ["dep-layer-filter", "dep-class-filter", "dep-search-filter"'
    '].forEach(function (id) {\n    document.getElementById(id).addEventListener("input", applyDependencyF'
    'ilters);\n    document.getElementById(id).addEventListener("change", applyDependencyFilters);\n  });\n '
    ' ["find-area-filter", "find-level-filter", "find-sev-filter", "find-status-filter", "find-search-fil'
    'ter"].forEach(function (id) {\n    document.getElementById(id).addEventListener("input", applyFinding'
    'Filters);\n    document.getElementById(id).addEventListener("change", applyFindingFilters);\n  });\n\n  '
    'function renderSnapshot(snap) {\n    currentSnap = snap;\n    document.getElementById("workspace-error'
    '-view").hidden = true;\n    document.getElementById("report-body").hidden = false;\n    var ws = snap.'
    'workspace || {};\n    var client = snap.client || { name: "CLIENTE", logo_data_uri: "", logo_alt: "Cu'
    'stomer logo" };\n    document.getElementById("cover-subtitle").textContent = "Workspace: " + (ws.name'
    ' || "—") + " (" + (ws.workspace_url || "—") + ") · Modo auth: " + (ws.auth_mode || "—");\n    var bad'
    'ges = document.getElementById("cover-badges");\n    clear(badges);\n    [\n      "Procedencia: " + snap'
    '.provenance,\n      "Entorno: " + snap.environment,\n      "UTC: " + snap.reference_utc,\n      ws.cros'
    's_tenant ? "Cross-Tenant (" + ws.sre_tenant_id + " -> " + ws.target_tenant_id + ")" : "Same-Tenant ('
    '" + (ws.target_tenant_id || "—") + ")",\n      "SKU: " + (ws.sku_name || "—")\n    ].forEach(function '
    '(b) { badges.appendChild(el("span", { className: "badge", text: b })); });\n\n    var plaque = documen'
    't.getElementById("brand-plaque");\n    clear(plaque);\n    if (client.logo_data_uri && /^data:image\\/('
    'png|jpeg);base64,[A-Za-z0-9+/=]+$/.test(client.logo_data_uri)) {\n      plaque.appendChild(el("img", '
    '{ src: client.logo_data_uri, alt: client.logo_alt || client.name || "CLIENTE" }));\n    } else {\n    '
    '  plaque.appendChild(el("span", { className: "brand-placeholder", text: client.name || "CLIENTE" }))'
    ';\n    }\n    document.getElementById("client-name-label").textContent = client.name || "CLIENTE";\n\n  '
    '  var facts = document.getElementById("cover-facts");\n    clear(facts);\n    [\n      ["Workspace", ws'
    '.name || "—"],\n      ["Host Workspace", ws.workspace_url || "—"],\n      ["Grupo de recursos", ws.res'
    'ource_group || "—"],\n      ["Grupo administrado", ws.managed_resource_group || "—"],\n      ["Región '
    '/ SKU", (ws.region || "—") + " / " + (ws.sku_name || "—")],\n      ["No Public IP / Acceso público", '
    'String(ws.enable_no_public_ip) + " / " + (ws.public_network_access || "—")]\n    ].forEach(function ('
    'pair) {\n      var d = el("div");\n      d.appendChild(el("dt", { text: pair[0] }));\n      d.appendChi'
    'ld(el("dd", { text: pair[1] }));\n      facts.appendChild(d);\n    });\n    document.getElementById("co'
    'ver-resource-id").textContent = "ARM Resource ID: " + (ws.id || "—");\n\n    var msgList = document.ge'
    'tElementById("executive-messages");\n    clear(msgList);\n    (snap.executive_messages || []).forEach('
    'function (m) { msgList.appendChild(el("li", { text: m })); });\n\n    var gScore = (snap.scores && sna'
    'p.scores.global) || {};\n    var gBox = document.getElementById("global-score-box");\n    clear(gBox);'
    '\n    gBox.appendChild(el("h3", { text: "Índice local de configuración" }));\n    gBox.appendChild(el('
    '"span", { className: "score-value", text: gScore.score === null || gScore.score === undefined ? "No '
    'evaluado" : gScore.score + "%" }));\n    gBox.appendChild(el("p", { text: "Cobertura evaluada: " + (g'
    'Score.coverage_percent === null || gScore.coverage_percent === undefined ? "0%" : gScore.coverage_pe'
    'rcent + "%") + " (" + (gScore.evaluated || 0) + " evaluados, " + (gScore.not_evaluated || 0) + " No '
    'evaluado, " + (gScore.not_applicable || 0) + " No aplica)." }));\n\n    function renderBars(containerI'
    'd, mapObj) {\n      var holder = document.getElementById(containerId);\n      clear(holder);\n      Obj'
    'ect.keys(mapObj || {}).forEach(function (k) {\n        var item = mapObj[k];\n        var row = el("di'
    'v", { className: "score-row" });\n        var head = el("div", { className: "score-row-head" });\n    '
    '    head.appendChild(el("span", { text: k }));\n        head.appendChild(el("span", { text: (item.sco'
    're === null ? "No evaluado" : item.score + "%") + " · Cobertura " + (item.coverage_percent === null '
    '? "0%" : item.coverage_percent + "%") }));\n        row.appendChild(head);\n        var track = el("di'
    'v", { className: "score-track" });\n        var fill = el("div", { className: "score-fill", style: "w'
    'idth:" + (item.score || 0) + "%" });\n        track.appendChild(fill);\n        row.appendChild(track)'
    ';\n        holder.appendChild(row);\n      });\n    }\n    renderBars("area-scores", snap.scores && snap'
    '.scores.areas);\n    renderBars("pillar-scores", snap.scores && snap.scores.pillars);\n    renderDonut'
    '(gScore);\n    renderTable(document.getElementById("check-status-table"),\n      ["Estado", "Recuento"'
    ', "Significado"],\n      [\n        ["Cumple (passed)", gScore.passed || 0, "Configuración observada c'
    'onforme con la regla local."],\n        ["No cumple (failed)", gScore.failed || 0, "Desviación o refe'
    'rencia rota observada."],\n        ["No evaluado (not_evaluated)", gScore.not_evaluated || 0, "Fuente'
    ' no disponible, requisito no confirmado o alcance sin cómputo."],\n        ["No aplica (not_applicabl'
    'e)", gScore.not_applicable || 0, "Excluido del denominador por tipo de objeto o requisito falso."]\n '
    '     ]\n    );\n\n    var priorities = (snap.findings || []).filter(function (f) { return f.severity =='
    '= "critical" || f.severity === "high"; });\n    renderTable(document.getElementById("priority-finding'
    's-table"),\n      ["Regla", "Severidad", "Nivel / Objeto", "Título", "Evidencia / Motivo"],\n      pri'
    'orities.map(function (f) {\n        return [\n          f.rule_id,\n          el("span", { className: "'
    'badge " + f.severity, text: f.severity_label || f.severity }),\n          f.level + (f.workload_name '
    '? ": " + f.workload_name : ""),\n          f.title,\n          f.reason\n        ];\n      })\n    );\n\n  '
    '  var inv = snap.inventory || {};\n    var computeRows = [].concat(inv.clusters || [], inv.instance_p'
    'ools || [], inv.cluster_policies || [], inv.global_init_scripts || []);\n    renderTable(document.get'
    'ElementById("inv-compute-table"),\n      ["Tipo", "Nombre / ID", "Estado / Runtime", "Modo acceso / A'
    'utoterminación", "Política / Pool"],\n      computeRows.map(function (r) {\n        return [\n         '
    ' r.kind,\n          (r.name || "—") + " (" + (r.id || "—") + ")",\n          (r.state || "—") + (r.spa'
    'rk_version ? " · " + r.spark_version : ""),\n          (r.data_security_mode || "—") + (r.autotermina'
    'tion_minutes !== undefined ? " · " + r.autotermination_minutes + " min" : ""),\n          (r.policy_i'
    'd || "—") + (r.instance_pool_id ? " / Pool: " + r.instance_pool_id : "")\n        ];\n      })\n    );\n'
    '\n    var orchRows = [];\n    (inv.jobs || []).forEach(function (j) {\n      orchRows.push(["Job", j.na'
    'me + " (" + j.id + ")", "Programado: " + j.scheduled, "run_as SP: " + (j.run_as_service_principal ||'
    ' "No"), (j.tasks || []).map(function (t) { return t.task_key; }).join(", ")]);\n    });\n    (inv.pipe'
    'lines || []).forEach(function (p) {\n      orchRows.push(["LakeflowPipeline", p.name + " (" + p.id + '
    '")", p.state || "—", "Serverless: " + p.serverless, "Catálogo: " + (p.catalog || "hive_metastore") +'
    ' " · Target: " + (p.target || "—")]);\n    });\n    (inv.sql_warehouses || []).forEach(function (w) {\n'
    '      orchRows.push(["SqlWarehouse", w.name + " (" + w.id + ")", (w.state || "—") + " · " + (w.clust'
    'er_size || "—"), "Serverless: " + w.enable_serverless_compute + " · Auto-stop: " + w.auto_stop_mins '
    '+ "m", w.warehouse_type || "—"]);\n    });\n    renderTable(document.getElementById("inv-orchestration'
    '-table"),\n      ["Tipo", "Nombre / ID", "Estado / Programación", "Identidad / Modo", "Tareas / Desti'
    'no"],\n      orchRows\n    );\n\n    var ucRows = [];\n    if (inv.uc_metastore) {\n      ucRows.push(["Me'
    'tastore", inv.uc_metastore.name, inv.uc_metastore.id, inv.uc_metastore.storage_root || "—", "Región:'
    ' " + (inv.uc_metastore.region || "—")]);\n    }\n    (inv.uc_catalogs || []).forEach(function (c) {\n  '
    '    ucRows.push(["Catalog", c.name, c.catalog_type || "—", c.storage_root || "—", "Isolation: " + (c'
    '.isolation_mode || "—")]);\n    });\n    (inv.uc_schemas || []).forEach(function (s) {\n      ucRows.pu'
    'sh(["Schema", s.full_name, s.catalog_name, s.storage_root || "—", "—"]);\n    });\n    (inv.uc_storage'
    '_credentials || []).forEach(function (cr) {\n      ucRows.push(["StorageCredential", cr.name, cr.uses'
    '_managed_identity ? "Managed Identity" : "Service Principal", cr.access_connector_id || "—", "Read-o'
    'nly: " + cr.read_only]);\n    });\n    (inv.uc_external_locations || []).forEach(function (loc) {\n    '
    '  ucRows.push(["ExternalLocation", loc.name, "Credential: " + (loc.credential_name || "—"), loc.url '
    '|| "—", "Read-only: " + loc.read_only]);\n    });\n    (inv.uc_connections || []).forEach(function (cn'
    ') {\n      ucRows.push(["Connection", cn.name, cn.connection_type || "—", cn.host || "—", "Credential'
    ': " + (cn.credential_type || "—")]);\n    });\n    (inv.secret_scopes || []).forEach(function (sc) {\n '
    '     ucRows.push(["SecretScope", sc.name, sc.backend_type || "—", sc.keyvault_dns_name || sc.keyvaul'
    't_resource_id || "—", "Valores nunca leídos"]);\n    });\n    renderTable(document.getElementById("inv'
    '-uc-table"),\n      ["Objeto", "Nombre", "Tipo / Credencial", "URI / Recurso", "Detalle"],\n      ucRo'
    'ws\n    );\n\n    var resRows = [];\n    (inv.related_resources || []).forEach(function (r) {\n      resR'
    'ows.push([r.resource_kind, r.name || "—", r.id, JSON.stringify(r.association || {}), JSON.stringify('
    'r.configuration || {})]);\n    });\n    (inv.outbound_endpoints || []).forEach(function (o) {\n      re'
    'sRows.push(["OutboundDependency", o.category, o.id, "outboundNetworkDependenciesEndpoints", JSON.str'
    'ingify(o.endpoints || [])]);\n    });\n    renderTable(document.getElementById("inv-resources-table"),'
    '\n      ["Tipo de recurso", "Nombre", "ARM ID", "Asociación", "Configuración"],\n      resRows\n    );\n'
    '\n    var fin = snap.finops || {};\n    document.getElementById("finops-actual-cost").textContent = (f'
    'in.actual_cost === null || fin.actual_cost === undefined)\n      ? "No evaluado / Sin alcance de fact'
    'uración"\n      : fin.actual_cost.toFixed(2) + " " + (fin.currency || "");\n    document.getElementByI'
    'd("finops-cost-note").textContent = (fin.notes || []).join(" ");\n    renderTable(document.getElement'
    'ById("finops-candidates-table"),\n      ["ID", "Carga / Objeto", "Título", "Valor observado", "Base",'
    ' "Recomendación"],\n      (fin.candidates || []).map(function (c) {\n        return [c.id, c.workload_'
    'name || c.resource_id, c.title, String(c.value) + " " + (c.unit || ""), c.basis, c.recommendation];\n'
    '      })\n    );\n    renderTable(document.getElementById("finops-cost-table"),\n      ["Resource ID", '
    '"Fecha", "Importe", "Moneda", "Base"],\n      (fin.cost_rows || []).map(function (r) {\n        return'
    ' [r.resource_id, r.usage_date || "Periodo acumulado", r.amount, r.currency, r.basis];\n      })\n    )'
    ';\n\n    renderTable(document.getElementById("actions-table"),\n      ["Horizonte", "Esfuerzo", "Severi'
    'dad", "Regla", "Carga / Recurso", "Acción recomendada"],\n      (snap.actions || []).map(function (a)'
    ' {\n        return [\n          a.horizon,\n          a.effort_label,\n          el("span", { className:'
    ' "badge " + a.severity, text: a.severity_label || a.severity }),\n          a.rule_id,\n          a.wo'
    'rkload_name || a.resource_id,\n          a.recommendation\n        ];\n      })\n    );\n\n    renderTable'
    '(document.getElementById("sources-table"),\n      ["Fuente ID", "Estado", "Páginas", "Registros", "Ho'
    'ra UTC", "Nota / Errores"],\n      (snap.sources || []).map(function (s) {\n        return [\n         '
    ' s.id,\n          s.status,\n          s.pages,\n          s.records,\n          s.time,\n          (s.no'
    'te || "") + (s.errors && s.errors.length ? " Errores: " + JSON.stringify(s.errors) : "")\n        ];\n'
    '      })\n    );\n\n    var limList = document.getElementById("methodology-limitations");\n    clear(lim'
    'List);\n    ((snap.methodology && snap.methodology.limitations) || []).forEach(function (l) {\n      l'
    'imList.appendChild(el("li", { text: l }));\n    });\n\n    applyDependencyFilters();\n    applyFindingFi'
    'lters();\n    renderReferenceArchitecture();\n  }\n\n  if (isMulti) {\n    var selWrap = document.getElem'
    'entById("workspace-selector-wrap");\n    var sel = document.getElementById("workspace-selector");\n   '
    ' selWrap.hidden = false;\n    var runs = rootData.workspace_runs || [];\n    var multiBox = document.g'
    'etElementById("multi-overview");\n    multiBox.hidden = false;\n    var agg = rootData.aggregate || {}'
    ';\n    multiBox.appendChild(el("h2", { text: "Resumen agregado multi-workspace (" + runs.length + " w'
    'orkspaces seleccionados)" }));\n    multiBox.appendChild(el("p", {\n      className: "muted",\n      te'
    'xt: "Hallazgos totales: " + (agg.findings_total || 0) + " · Nodos de dependencia: " + ((agg.dependen'
    'cy_counts && agg.dependency_counts.nodes_total) || 0) + " · Workspaces con error: " + (agg.failed_wo'
    'rkspace_count || 0)\n    }));\n    runs.forEach(function (r, idx) {\n      sel.appendChild(el("option",'
    ' { value: String(idx), text: r.workspace_name + " (" + r.status + ")" }));\n    });\n    function sele'
    'ctRun(idx) {\n      var run = runs[idx];\n      if (!run) { return; }\n      if (run.snapshot) {\n      '
    '  renderSnapshot(run.snapshot);\n      } else {\n        currentSnap = null;\n        document.getEleme'
    'ntById("report-body").hidden = true;\n        var errView = document.getElementById("workspace-error-'
    'view");\n        errView.hidden = false;\n        clear(errView);\n        errView.appendChild(el("h2",'
    ' { text: "Recolección fallida para el workspace " + run.workspace_name }));\n        errView.appendCh'
    'ild(el("p", { text: "No se sustituyen datos vacíos ni puntuaciones de otro workspace. Error: " + JSO'
    'N.stringify(run.error || {}) }));\n      }\n    }\n    sel.addEventListener("change", function () { sel'
    'ectRun(Number(sel.value)); });\n    selectRun(0);\n  } else {\n    renderSnapshot(rootData);\n  }\n})();\n'
    '</script>\n</body>\n</html>\n'
)
# END BUILD-TIME ASSETS


class EvidenceError(RuntimeError):
    def __init__(self, code, message, source="assessment", http_status=None):
        super().__init__(message)
        self.code, self.source, self.http_status = code, source, http_status

    def public(self):
        return {"code": self.code, "message": str(self), "source_id": self.source, "http_status": self.http_status}


def utc_now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def obj(value, source="normalization"):
    if not isinstance(value, dict):
        raise EvidenceError("invalid_shape", "Expected a source object; no empty-success substitution.", source)
    return value


def array(value, source="normalization"):
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise EvidenceError("invalid_shape", "Expected an array of source objects.", source)
    return value


def pick(value, *keys):
    result = value
    for key in keys:
        if not isinstance(result, dict) or key not in result:
            return None
        result = result[key]
    return result


def text(value, source="normalization", maximum=8192):
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > maximum or any(ord(c) < 32 for c in value):
        raise EvidenceError("invalid_field", "Source text has an invalid type, control character or safety-bound length.", source)
    return value


def number(value, source="normalization"):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise EvidenceError("invalid_field", "Source numeric value must be finite.", source)
    return value


def boolean(value, source="normalization"):
    if value is not None and not isinstance(value, bool):
        raise EvidenceError("invalid_field", "Source boolean field has an invalid type.", source)
    return value


def strings(value, source="normalization"):
    if value is None:
        return None
    if not isinstance(value, list):
        raise EvidenceError("invalid_field", "Source string-list field has an invalid type.", source)
    return [text(item, source) for item in value]


def tags_map(value, source):
    if value is None:
        return {}
    result = {}
    for key, item in obj(value, source).items():
        k = text(str(key), source, 256)
        if any(secret_word in k.lower() for secret_word in ("secret", "password", "token", "key", "sas", "credential")):
            continue
        if isinstance(item, (str, int, float, bool)) or item is None:
            result[k] = text(str(item), source, 512) if item is not None else None
    return result


def validate_logo(uri, alt=CLIENT_LOGO_ALT):
    if uri == "":
        return
    if not isinstance(uri, str) or len(uri) > 140000:
        raise EvidenceError("invalid_logo", "Optional logo must be a bounded inline PNG/JPEG, not a path or URL.", "branding")
    match = re.fullmatch(r"data:image/(png|jpeg);base64,([A-Za-z0-9+/=]+)", uri)
    if not match:
        raise EvidenceError("invalid_logo", "Only inline PNG/JPEG MIME with canonical base64 is allowed.", "branding")
    try:
        data = base64.b64decode(match[2], validate=True)
    except binascii.Error as exc:
        raise EvidenceError("invalid_logo", "Invalid logo base64.", "branding") from exc
    if not 1 <= len(data) <= 100000:
        raise EvidenceError("invalid_logo", "Optional raster logo must contain 1..100000 bytes.", "branding")
    if not isinstance(alt, str) or not alt.strip() or len(alt) > 120 or re.search(r"[\x00-\x1f\x7f]", alt):
        raise EvidenceError("invalid_logo", "Provide 1..120 plain characters of descriptive logo alt text.", "branding")
    try:
        from PIL import Image, ImageFile, UnidentifiedImageError
    except ImportError as exc:
        raise EvidenceError("dependency_missing", "A configured logo requires Pillow for genuine bounded raster validation.", "branding") from exc
    if ImageFile.LOAD_TRUNCATED_IMAGES:
        raise EvidenceError("unsafe_decoder_settings", "Truncated-image decoding must not be enabled; no signature-only fallback.", "branding")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data), formats=["PNG", "JPEG"]) as image:
                width, height = image.size
                if (
                    image.format != ("PNG" if match[1] == "png" else "JPEG")
                    or not 1 <= width <= 2048 or not 1 <= height <= 2048
                    or getattr(image, "n_frames", 1) != 1
                ):
                    raise EvidenceError("invalid_logo", "Use one PNG/JPEG frame, matching MIME, at most 2048 by 2048 pixels.", "branding")
                image.verify()
            with Image.open(io.BytesIO(data), formats=["PNG", "JPEG"]) as image:
                image.load()
    except (OSError, ValueError, SyntaxError, UnidentifiedImageError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise EvidenceError("invalid_logo", "The optional logo is not a complete, valid single-frame PNG/JPEG raster.", "branding") from exc


def response_bytes(value):
    return len(json.dumps(value, allow_nan=False).encode("utf-8"))


def ensure_response(value):
    if response_bytes(value) > TRANSPORT_BYTES:
        raise EvidenceError("transport_size_exceeded", "Default-serialized response exceeds 3500 bytes; no malformed/truncated JSON is returned.", "transport")
    return value


def arm_id(value, subscription=None):
    value = text(value, "scope", 2048)
    if value is None:
        raise EvidenceError("invalid_resource_id", "A scoped ARM resource ID is required.", "scope")
    parts = value.split("/")
    if (
        len(parts) < 9 or parts[0] != "" or parts[1].lower() != "subscriptions"
        or parts[3].lower() != "resourcegroups" or parts[5].lower() != "providers"
        or any(not re.fullmatch(r"[A-Za-z0-9_.()-]+", part) or part in (".", "..") for part in parts[2:])
        or (subscription and parts[2].lower() != subscription.lower())
    ):
        raise EvidenceError("invalid_resource_id", "Resource ID changed the fixed subscription or has unsafe syntax.", "scope")
    try:
        UUID(parts[2])
    except ValueError as exc:
        raise EvidenceError("invalid_resource_id", "Resource ID subscription is not a GUID.", "scope") from exc
    return value


def resource_type(resource_id):
    parts = arm_id(resource_id).split("/")
    return (parts[6] + "/" + "/".join(parts[7::2])).lower()


def validate_guid(value, field_name):
    try:
        if not isinstance(value, str) or str(UUID(value)) != value.lower() or UUID(value).int == 0:
            raise ValueError
    except (ValueError, AttributeError) as exc:
        raise EvidenceError("configuration_required", "Configure the explicit " + field_name + " before authentication.", "configuration") from exc
    return value.lower()


def validate_workspace_host(host, required=True):
    if not required and not host:
        return ""
    if not isinstance(host, str) or not re.fullmatch(r"adb-[0-9]{10,24}\.[0-9]{1,4}\.azuredatabricks\.net", host):
        raise EvidenceError(
            "configuration_required",
            "Configure workspace_host as an exact per-workspace hostname (adb-<id>.<shard>.azuredatabricks.net) without scheme or path.",
            "configuration",
        )
    return host.lower()


def validate_config(workspace_name):
    validate_guid(SUBSCRIPTION_ID, "SUBSCRIPTION_ID")
    sre_tid = validate_guid(SRE_TENANT_ID, "SRE_TENANT_ID")
    target_tid = validate_guid(TARGET_TENANT_ID, "TARGET_TENANT_ID")
    validate_guid(MANAGED_IDENTITY_CLIENT_ID, "MANAGED_IDENTITY_CLIENT_ID")
    if not isinstance(APPROVED_WORKSPACES, dict) or not 1 <= len(APPROVED_WORKSPACES) <= 5:
        raise EvidenceError("configuration_required", "Configure one to five fixed approved Databricks workspaces.", "configuration")
    name = workspace_name or next(iter(APPROVED_WORKSPACES))
    if name not in APPROVED_WORKSPACES:
        raise EvidenceError("invalid_parameter", "workspace_name must exactly match the fixed operator allowlist.", "parameters")
    config = obj(APPROVED_WORKSPACES[name], "configuration")
    for field, value, maximum in (("name", name, 64), ("resource_group", config.get("resource_group"), 90)):
        if not isinstance(value, str) or not 1 <= len(value) <= maximum or not re.fullmatch(r"[A-Za-z0-9_.()-]+", value):
            raise EvidenceError("configuration_required", "Configure a bounded approved " + field + ".", "configuration")
    if config.get("environment") not in ("LAB", "PRODUCTION", "UNSPECIFIED"):
        raise EvidenceError("configuration_required", "Set explicit LAB/PRODUCTION/UNSPECIFIED environment.", "configuration")
    auth_mode = config.get("auth_mode")
    if auth_mode not in AUTH_MODES:
        raise EvidenceError("configuration_required", "Set auth_mode to one of: " + ", ".join(AUTH_MODES) + ".", "configuration")
    if auth_mode == "same_tenant_uami" and sre_tid != target_tid:
        raise EvidenceError(
            "cross_tenant_configuration_required",
            "SRE_TENANT_ID and TARGET_TENANT_ID differ: a single-tenant UAMI cannot directly authenticate across tenants. Configure cross_tenant_multitenant_fic or cross_tenant_lighthouse_plus_databricks_oidc after completing the colleague tenant setup.",
            "configuration",
        )
    for field in ("workspace_api_enabled", "unity_catalog_enabled", "include_managed_resource_group", "advisor_enabled"):
        if not isinstance(config.get(field), bool):
            raise EvidenceError("configuration_required", "Configure the boolean " + field + ".", "configuration")
    dbx_plane_enabled = config["workspace_api_enabled"] or config["unity_catalog_enabled"]
    if auth_mode == "cross_tenant_multitenant_fic" or (
        dbx_plane_enabled and auth_mode in ("cross_tenant_lighthouse_plus_databricks_oidc", "cross_tenant_lighthouse_plus_keyvault_oauth_m2m")
    ):
        validate_guid(FEDERATED_APP_CLIENT_ID, "FEDERATED_APP_CLIENT_ID")
    if dbx_plane_enabled and auth_mode == "cross_tenant_lighthouse_plus_keyvault_oauth_m2m":
        if not isinstance(KEYVAULT_OAUTH_SECRET_URI, str) or not re.fullmatch(
            r"https://[a-z0-9-]{3,24}\.vault\.azure\.net/secrets/[A-Za-z0-9-]{1,127}(?:/[0-9a-f]{32})?",
            KEYVAULT_OAUTH_SECRET_URI,
        ):
            raise EvidenceError(
                "configuration_required",
                "Configure KEYVAULT_OAUTH_SECRET_URI as https://<vault>.vault.azure.net/secrets/<secret-name> in the SRE tenant.",
                "configuration",
            )
    host = validate_workspace_host(config.get("workspace_host", ""), required=dbx_plane_enabled)
    if config.get("cost_scope") not in ("disabled", "resource_ids", "managed_resource_group"):
        raise EvidenceError("configuration_required", "Configure disabled/resource_ids/managed_resource_group cost scope.", "configuration")
    if config.get("cost_timeframe") not in ("month_to_date", "last_30_days"):
        raise EvidenceError("configuration_required", "Configure month_to_date/last_30_days billing timeframe.", "configuration")
    for field in ("approved_related_resource_ids", "approved_cost_resource_ids"):
        ids = config.get(field)
        if not isinstance(ids, list) or len(ids) > MAX_RELATED_RESOURCES or len({str(i).lower() for i in ids}) != len(ids):
            raise EvidenceError("configuration_required", "Configure distinct bounded fixed resource IDs.", "configuration")
        for value in ids:
            arm_id(value, SUBSCRIPTION_ID)
    requirements = obj(config.get("requirements"), "configuration")
    allowed = {
        "premium_required",
        "no_public_ip_required",
        "vnet_injection_required",
        "private_link_required",
        "access_connector_required",
        "cmk_required",
        "enhanced_security_required",
        "diagnostics_required",
        "pat_restriction_required",
        "unity_catalog_required",
        "cluster_policy_required",
        "autoscaling_required",
        "service_principal_jobs_required",
        "keyvault_secret_scopes_required",
        "shared_key_disabled_required",
    }
    if set(requirements) - allowed:
        raise EvidenceError("configuration_required", "Unknown requirement key; requirements are operator-authored, not query inputs.", "configuration")
    for key, value in requirements.items():
        if value is not None and not isinstance(value, bool):
            raise EvidenceError("configuration_required", "Requirement values must be boolean or unknown.", "configuration")
    validate_logo(CLIENT_LOGO_DATA_URI, CLIENT_LOGO_ALT)
    if not isinstance(CLIENT_NAME, str) or not 1 <= len(CLIENT_NAME) <= 120 or any(ord(c) < 32 for c in CLIENT_NAME):
        raise EvidenceError("configuration_required", "Client label must be bounded plain text.", "configuration")
    return {
        **config,
        "name": name,
        "workspace_host": host,
        "sre_tenant_id": sre_tid,
        "target_tenant_id": target_tid,
        "cross_tenant": sre_tid != target_tid,
        "id": "/subscriptions/" + SUBSCRIPTION_ID + "/resourceGroups/" + config["resource_group"]
        + "/providers/Microsoft.Databricks/workspaces/" + name,
    }


def selection_configs(workspace_name, workspace_names):
    first = validate_config(workspace_name)
    configured = [validate_config(name) for name in APPROVED_WORKSPACES]
    names = workspace_names.split(",") if workspace_names else [first["name"]]
    if len(set(names)) != len(names) or any(name not in APPROVED_WORKSPACES for name in names):
        raise EvidenceError("invalid_parameter", "Select distinct exact fixed allowlisted workspace names only.", "parameters")
    by_name = {config["name"]: config for config in configured}
    roster = [
        {
            "workspace_id": config["id"],
            "workspace_name": config["name"],
            "resource_group": config["resource_group"],
            "workspace_host": config["workspace_host"],
            "environment": config["environment"],
            "auth_mode": config["auth_mode"],
            "cross_tenant": config["cross_tenant"],
        }
        for config in configured
    ]
    return [by_name[name] for name in names], roster


def validate_parameters(
    operation, view, workspace_name, workspace_names, workload_name,
    classification, area, level, severity, status, limit, offset,
):
    for key, value, choices in (
        ("operation", operation, ("report", "query", "list_workspaces")),
        ("view", view, VIEWS),
        ("classification", classification, ("all",) + CLASSIFICATIONS),
        ("area", area, ("all",) + AREAS),
        ("level", level, ("all",) + LEVELS),
        ("severity", severity, ("all",) + SEVERITIES),
        ("status", status, ("all",) + CHECK_STATUSES + SOURCE_STATUSES),
    ):
        if value not in choices:
            raise EvidenceError("invalid_parameter", key + " must use its declared enum.", "parameters")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise EvidenceError("invalid_parameter", "limit must be an integer from 1 to 100.", "parameters")
    if isinstance(offset, bool) or not isinstance(offset, int) or not 0 <= offset <= 500000:
        raise EvidenceError("invalid_parameter", "offset must be an integer from 0 to 500000.", "parameters")
    for key, value, maximum in (("workspace_name", workspace_name, 64), ("workload_name", workload_name, 253)):
        if not isinstance(value, str) or len(value) > maximum or (value and not re.fullmatch(r"[A-Za-z0-9_.:()-]+", value)):
            raise EvidenceError("invalid_parameter", key + " is a bounded exact local name, not a path, URL or command.", "parameters")
    if not isinstance(workspace_names, str) or len(workspace_names) > 324 or (
        workspace_names and not re.fullmatch(r"[A-Za-z0-9_.()-]{1,64}(?:,[A-Za-z0-9_.()-]{1,64}){0,4}", workspace_names)
    ):
        raise EvidenceError("invalid_parameter", "workspace_names is an exact comma-separated allowlist selection of one to five names, without spaces.", "parameters")
    if workspace_name and workspace_names:
        raise EvidenceError("invalid_combination", "Use workspace_name or workspace_names, not both.", "parameters")
    filters = any((workload_name, classification != "all", area != "all", level != "all", severity != "all", status != "all"))
    if operation in ("report", "list_workspaces") and (view != "summary" or filters or limit != 25 or offset != 0):
        raise EvidenceError("invalid_combination", "report/list_workspaces cannot be narrowed by query filters or paging.", "parameters")
    if operation == "list_workspaces" and (workspace_name or workspace_names):
        raise EvidenceError("invalid_combination", "list_workspaces lists the complete fixed roster; do not select a workspace.", "parameters")
    if operation == "query":
        if classification != "all" and view != "dependencies":
            raise EvidenceError("invalid_combination", "classification filter applies only to view=dependencies.", "parameters")
        if view in ("summary", "workspace", "coverage") and workload_name:
            raise EvidenceError("invalid_combination", "workload_name filter does not apply to summary, workspace or coverage views.", "parameters")
        if view not in ("findings", "actions") and any((area != "all", level != "all", severity != "all")):
            raise EvidenceError("invalid_combination", "Area/level/severity filters apply only to findings or actions.", "parameters")
        if status != "all" and (
            (view == "coverage" and status not in SOURCE_STATUSES)
            or (view in ("findings", "actions") and status not in CHECK_STATUSES)
            or view not in ("coverage", "findings", "actions")
        ):
            raise EvidenceError("invalid_combination", "Status does not belong to the selected view.", "parameters")
    return dict(
        operation=operation, view=view, workspace_name=workspace_name, workspace_names=workspace_names,
        workload_name=workload_name, classification=classification, area=area, level=level,
        severity=severity, status=status, limit=limit, offset=offset,
    )


def source_receipt(source_id, reference, status="complete", note="", **extra):
    return {
        "id": source_id, "status": status, "time": reference, "records": 0, "pages": 0,
        "errors": [], "note": note, "window": None, **extra,
    }


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def verify_jwt_claims(token_str, expected_tid, expected_client, expected_aud):
    try:
        encoded = token_str.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
    except (AttributeError, IndexError, ValueError, binascii.Error) as exc:
        raise EvidenceError("authentication_failed", "Identity provider returned an unreadable JWT; token contents are excluded.", "identity") from exc
    tenant = pick(claims, "tid")
    client = pick(claims, "appid") or pick(claims, "azp")
    aud = pick(claims, "aud")
    expected_norm = expected_aud.rstrip("/").lower()
    aud_norm = aud.rstrip("/").lower() if isinstance(aud, str) else ""
    aud_valid = (
        aud_norm in ARM_TOKEN_AUDIENCES
        if expected_norm == ARM_ORIGIN.lower()
        else aud_norm in ENTRA_TOKEN_EXCHANGE_AUDIENCES
        if expected_norm == ENTRA_TOKEN_EXCHANGE_AUDIENCE.lower()
        else aud_norm == expected_norm
    )
    if not (
        isinstance(tenant, str) and tenant.lower() == expected_tid.lower()
        and isinstance(client, str) and client.lower() == expected_client.lower()
        and aud_valid
    ):
        raise EvidenceError("identity_mismatch", "Token tenant, client identity or audience differs from the fixed configuration.", "identity")
    return claims


class Identity:
    def __init__(self, config):
        try:
            from azure.identity import ManagedIdentityCredential
        except ImportError as exc:
            raise EvidenceError("dependency_missing", "Live reads require azure-identity; no cached-login fallback.", "identity") from exc
        self.config = config
        self.credential = ManagedIdentityCredential(client_id=MANAGED_IDENTITY_CLIENT_ID)
        self.deadline = time.monotonic() + MAX_COLLECTION_SECONDS
        self.request_count = 0
        self.context = ssl.create_default_context()
        if self.context.verify_mode != ssl.CERT_REQUIRED or not self.context.check_hostname:
            raise EvidenceError("unsafe_tls", "TLS peer and hostname validation are mandatory.", "tls")
        self.opener = build_opener(NoRedirect(), HTTPSHandler(context=self.context))

    def _guard_budget(self):
        if time.monotonic() >= self.deadline:
            raise EvidenceError("collection_deadline", "Collection elapsed-time bound reached; remaining reads are unavailable, not healthy.", "collection")
        if self.request_count >= MAX_HTTP_ATTEMPTS:
            raise EvidenceError("request_cap", "Collection HTTP-attempt bound reached; no narrower success is substituted.", "collection")
        self.request_count += 1

    def uami_token(self, audience):
        from azure.core.exceptions import ClientAuthenticationError, ServiceRequestError
        from azure.identity import CredentialUnavailableError
        self._guard_budget()
        try:
            token = self.credential.get_token(audience.rstrip("/") + "/.default").token
        except (ClientAuthenticationError, CredentialUnavailableError, ServiceRequestError) as exc:
            raise EvidenceError("authentication_failed", "The explicitly selected SRE managed identity could not acquire a token.", "identity") from exc
        verify_jwt_claims(token, SRE_TENANT_ID, MANAGED_IDENTITY_CLIENT_ID, audience)
        return token

    def exchange_entra_fic(self, target_resource):
        assertion = self.uami_token(ENTRA_TOKEN_EXCHANGE_AUDIENCE)
        self._guard_budget()
        token_url = "https://login.microsoftonline.com/" + TARGET_TENANT_ID.lower() + "/oauth2/v2.0/token"
        form = urlencode({
            "client_id": FEDERATED_APP_CLIENT_ID.lower(),
            "grant_type": "client_credentials",
            "scope": target_resource.rstrip("/") + "/.default",
            "client_assertion_type": "urn:ietf:params:oauth:client-assertion-type:jwt-bearer",
            "client_assertion": assertion,
        }).encode("utf-8")
        request = Request(token_url, data=form, method="POST", headers={
            "Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json",
        })
        try:
            with self.opener.open(request, timeout=20) as response:
                if response.status != 200:
                    raise EvidenceError("cross_tenant_auth_failed", "Cross-tenant Entra FIC exchange returned HTTP " + str(response.status) + ".", "identity", response.status)
                payload = obj(json.loads(response.read(65536)), "identity")
        except HTTPError as exc:
            raise EvidenceError("cross_tenant_auth_failed", "Cross-tenant Entra FIC token exchange failed with HTTP " + str(exc.code) + ".", "identity", exc.code) from exc
        except (URLError, TimeoutError, ssl.SSLError, OSError, ValueError) as exc:
            raise EvidenceError("cross_tenant_auth_failed", "Cross-tenant Entra FIC token transport failed.", "identity") from exc
        access_token = text(payload.get("access_token"), "identity", 32768)
        if not access_token:
            raise EvidenceError("cross_tenant_auth_failed", "Cross-tenant Entra FIC response contained no access_token.", "identity")
        verify_jwt_claims(access_token, TARGET_TENANT_ID, FEDERATED_APP_CLIENT_ID, target_resource)
        return access_token

    def exchange_databricks_oidc(self, workspace_host):
        assertion = self.uami_token(ENTRA_TOKEN_EXCHANGE_AUDIENCE)
        self._guard_budget()
        token_url = "https://" + workspace_host + "/oidc/v1/token"
        form = urlencode({
            "client_id": FEDERATED_APP_CLIENT_ID.lower(),
            "subject_token": assertion,
            "subject_token_type": "urn:ietf:params:oauth:token-type:jwt",
            "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
            "scope": "all-apis",
        }).encode("utf-8")
        request = Request(token_url, data=form, method="POST", headers={
            "Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json",
        })
        try:
            with self.opener.open(request, timeout=20) as response:
                if response.status != 200:
                    raise EvidenceError("databricks_oidc_failed", "Databricks OIDC federation exchange returned HTTP " + str(response.status) + ".", "workspace_auth", response.status)
                payload = obj(json.loads(response.read(65536)), "workspace_auth")
        except HTTPError as exc:
            raise EvidenceError("databricks_oidc_failed", "Databricks OIDC federation exchange failed with HTTP " + str(exc.code) + ".", "workspace_auth", exc.code) from exc
        except (URLError, TimeoutError, ssl.SSLError, OSError, ValueError) as exc:
            raise EvidenceError("databricks_oidc_failed", "Databricks OIDC federation transport failed.", "workspace_auth") from exc
        access_token = text(payload.get("access_token"), "workspace_auth", 32768)
        if not access_token:
            raise EvidenceError("databricks_oidc_failed", "Databricks OIDC federation returned no access_token.", "workspace_auth")
        return access_token

    def exchange_keyvault_oauth_m2m(self, workspace_host):
        kv_token = self.uami_token(KEYVAULT_AUDIENCE)
        self._guard_budget()
        kv_url = KEYVAULT_OAUTH_SECRET_URI + "?api-version=7.4"
        kv_req = Request(kv_url, method="GET", headers={
            "Authorization": "Bearer " + kv_token, "Accept": "application/json",
        })
        try:
            with self.opener.open(kv_req, timeout=15) as response:
                if response.status != 200:
                    raise EvidenceError("keyvault_secret_read_failed", "Key Vault OAuth secret read returned HTTP " + str(response.status) + ".", "workspace_auth", response.status)
                kv_payload = obj(json.loads(response.read(65536)), "workspace_auth")
        except HTTPError as exc:
            raise EvidenceError("keyvault_secret_read_failed", "Key Vault OAuth secret read failed with HTTP " + str(exc.code) + ".", "workspace_auth", exc.code) from exc
        except (URLError, TimeoutError, ssl.SSLError, OSError, ValueError) as exc:
            raise EvidenceError("keyvault_secret_read_failed", "Key Vault OAuth secret transport failed.", "workspace_auth") from exc
        secret_value = text(kv_payload.get("value"), "workspace_auth", 4096)
        if not secret_value:
            raise EvidenceError("keyvault_secret_read_failed", "Key Vault returned an empty OAuth secret value.", "workspace_auth")
        self._guard_budget()
        token_url = "https://" + workspace_host + "/oidc/v1/token"
        basic = base64.b64encode((FEDERATED_APP_CLIENT_ID.lower() + ":" + secret_value).encode("utf-8")).decode("ascii")
        form = urlencode({"grant_type": "client_credentials", "scope": "all-apis"}).encode("utf-8")
        request = Request(token_url, data=form, method="POST", headers={
            "Authorization": "Basic " + basic,
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        })
        try:
            with self.opener.open(request, timeout=20) as response:
                if response.status != 200:
                    raise EvidenceError("databricks_oauth_m2m_failed", "Databricks OAuth M2M exchange returned HTTP " + str(response.status) + ".", "workspace_auth", response.status)
                payload = obj(json.loads(response.read(65536)), "workspace_auth")
        except HTTPError as exc:
            raise EvidenceError("databricks_oauth_m2m_failed", "Databricks OAuth M2M exchange failed with HTTP " + str(exc.code) + ".", "workspace_auth", exc.code) from exc
        except (URLError, TimeoutError, ssl.SSLError, OSError, ValueError) as exc:
            raise EvidenceError("databricks_oauth_m2m_failed", "Databricks OAuth M2M transport failed.", "workspace_auth") from exc
        access_token = text(payload.get("access_token"), "workspace_auth", 32768)
        if not access_token:
            raise EvidenceError("databricks_oauth_m2m_failed", "Databricks OAuth M2M returned no access_token.", "workspace_auth")
        return access_token

    def arm_token(self):
        if self.config["auth_mode"] == "cross_tenant_multitenant_fic":
            return self.exchange_entra_fic(ARM_ORIGIN)
        return self.uami_token(ARM_ORIGIN)

    def databricks_token(self):
        mode = self.config["auth_mode"]
        if mode == "same_tenant_uami":
            return self.uami_token(DATABRICKS_ENTRA_RESOURCE)
        if mode == "cross_tenant_multitenant_fic":
            return self.exchange_entra_fic(DATABRICKS_ENTRA_RESOURCE)
        if mode == "cross_tenant_lighthouse_plus_databricks_oidc":
            return self.exchange_databricks_oidc(self.config["workspace_host"])
        if mode == "cross_tenant_lighthouse_plus_keyvault_oauth_m2m":
            return self.exchange_keyvault_oauth_m2m(self.config["workspace_host"])
        raise EvidenceError("configuration_required", "Unsupported authentication mode.", "configuration")

    def close(self):
        self.credential.close()


class HttpReader:
    def __init__(self, identity, origin=ARM_ORIGIN, token_kind="arm"):
        self.identity, self.origin, self.token_kind = identity, origin, token_kind
        self.context = ssl.create_default_context()
        if self.context.verify_mode != ssl.CERT_REQUIRED or not self.context.check_hostname:
            raise EvidenceError("unsafe_tls", "TLS peer and hostname validation are mandatory.", "tls")
        self.opener = build_opener(NoRedirect(), HTTPSHandler(context=self.context))
        self.allowed = set()

    def allow(self, url, method="GET"):
        parsed = urlsplit(url)
        if parsed.scheme != "https" or (parsed.scheme + "://" + parsed.netloc) != self.origin or parsed.fragment or parsed.username:
            raise EvidenceError("unsafe_endpoint", "Read URL changed the fixed HTTPS origin.", "scope")
        if method not in ("GET", "POST"):
            raise EvidenceError("unsafe_method", "Only enumerated GET reads and one Cost Management read-only POST are permitted.", "scope")
        if any(forbidden in parsed.path.lower() for forbidden in ("/secrets/get", "/secrets/put", "/secrets/delete", "/commands/", "/clusters/start", "/clusters/create", "/jobs/run-now", "/sql/statements")):
            raise EvidenceError("unsafe_endpoint", "Secret-value reads, compute starts, SQL statement execution and writes are forbidden.", "scope")
        self.allowed.add((method, parsed.path))
        return url

    def _bearer(self):
        return self.identity.arm_token() if self.token_kind == "arm" else self.identity.databricks_token()

    def request(self, method, url, source, body=None, allow_empty=False):
        parsed = urlsplit(url)
        if (
            parsed.scheme + "://" + parsed.netloc != self.origin or parsed.fragment or parsed.username or parsed.password
            or len(url) > 16384 or (method, parsed.path) not in self.allowed
        ):
            raise EvidenceError("unsafe_endpoint", "Request was not one of the scoped allowlisted reads.", source)
        if method == "POST" and not parsed.path.lower().endswith("/providers/microsoft.costmanagement/query"):
            raise EvidenceError("unsafe_method", "This POST is not an enumerated read-only operation.", source)
        payload = None if body is None else json.dumps(body, allow_nan=False).encode("utf-8")
        for attempt in range(3):
            bearer = self._bearer()
            self.identity._guard_budget()
            request = Request(url, data=payload, method=method, headers={
                "Authorization": "Bearer " + bearer,
                "Accept": "application/json",
                "Content-Type": "application/json",
            })
            try:
                with self.opener.open(request, timeout=30) as response:
                    if response.status == 204 and allow_empty:
                        return {}
                    if response.status != 200:
                        raise EvidenceError("http_error", "Read returned HTTP " + str(response.status) + ".", source, response.status)
                    raw = response.read(HTTP_BYTES + 1)
                    if len(raw) > HTTP_BYTES:
                        raise EvidenceError("response_cap", "Source response exceeded the disclosed byte safety bound.", source)
            except HTTPError as exc:
                if exc.code in (429, 500, 502, 503, 504) and attempt < 2:
                    retry = exc.headers.get("Retry-After", "") if exc.headers else ""
                    time.sleep(min(int(retry), 5) if re.fullmatch(r"[0-9]{1,4}", retry) else attempt + 1)
                    continue
                raise EvidenceError(
                    "access_denied" if exc.code in (401, 403) else "http_error",
                    "Read returned HTTP " + str(exc.code) + "; response bodies are excluded.",
                    source, exc.code,
                ) from exc
            except (URLError, TimeoutError, ssl.SSLError, OSError) as exc:
                reason = getattr(exc, "reason", exc)
                code = "tls_failed" if isinstance(reason, ssl.SSLError) else "transport_failed"
                raise EvidenceError(code, "Read transport/TLS failed; no insecure retry or alternate identity.", source) from exc
            try:
                decoded = json.loads(raw)
                return decoded if isinstance(decoded, (dict, list)) else obj(decoded, source)
            except (ValueError, UnicodeDecodeError) as exc:
                raise EvidenceError("invalid_json", "Source returned invalid JSON; no raw body is exported.", source) from exc
        raise EvidenceError("http_error", "Bounded retries exhausted.", source)


def next_arm_link(link, initial):
    if not isinstance(link, str) or not link or len(link) > 16384:
        raise EvidenceError("invalid_pagination", "Invalid ARM continuation.", "pagination")
    current, first = urlsplit(link), urlsplit(initial)
    if (
        current.scheme != "https" or current.netloc != first.netloc or current.path != first.path
        or current.fragment or current.username or current.password
        or unquote(current.path) != current.path or "\\" in current.path
    ):
        raise EvidenceError("invalid_pagination", "ARM continuation changed origin or exact resource scope.", "pagination")
    try:
        pairs = parse_qsl(current.query, keep_blank_values=True, strict_parsing=True)
        original = dict(parse_qsl(first.query, keep_blank_values=True, strict_parsing=True))
    except ValueError as exc:
        raise EvidenceError("invalid_pagination", "Malformed continuation query.", "pagination") from exc
    values = dict(pairs)
    paging = {"$skiptoken", "skiptoken", "$skipToken", "skipToken", "$skip", "$top"}
    if len(values) != len(pairs) or any(key not in original and key not in paging for key in values):
        raise EvidenceError("invalid_pagination", "ARM continuation added an unapproved query.", "pagination")
    if any(values.get(key) != value for key, value in original.items() if key not in paging):
        raise EvidenceError("invalid_pagination", "ARM continuation changed version or filter.", "pagination")
    aliases = [value for key, value in pairs if key.lower() in ("$skiptoken", "skiptoken")]
    if aliases and (not all(aliases) or len(set(aliases)) != 1):
        raise EvidenceError("invalid_pagination", "ARM continuation token aliases are empty or conflicting.", "pagination")
    return link


def read_arm_pages(reader, url, source_id, reference, normalize, value_key="value", top_level_list=False):
    receipt = source_receipt(
        source_id, reference, page_cap=MAX_PAGES, row_cap=MAX_ROWS,
        pagination_complete=False, read_signature="GET " + url,
    )
    rows, seen_ids, seen_pages = [], set(), set()
    current = url
    reader.allow(url, "GET")
    try:
        for page_number in range(MAX_PAGES):
            if current in seen_pages:
                raise EvidenceError("pagination_loop", "Source repeated a continuation.", source_id)
            seen_pages.add(current)
            payload = reader.request("GET", current, source_id)
            receipt["pages"] = page_number + 1
            if top_level_list and isinstance(payload, list):
                page = array(payload, source_id)
                continuation = None
            else:
                payload = obj(payload, source_id)
                page = array(payload.get(value_key, []), source_id)
                continuation = payload.get("nextLink")
            if len(rows) + len(page) > MAX_ROWS:
                raise EvidenceError("row_cap", "Source row safety cap reached; scope was not silently narrowed.", source_id)
            for raw in page:
                row = normalize(raw)
                identity = str(row.get("id") or row.get("resource_id") or "").lower()
                if not identity or identity in seen_ids:
                    raise EvidenceError("invalid_pagination", "Source row identity is absent or repeated.", source_id)
                seen_ids.add(identity)
                rows.append(row)
            receipt["records"] = len(rows)
            if not continuation:
                receipt["pagination_complete"] = True
                return rows, receipt
            current = next_arm_link(continuation, url)
        raise EvidenceError("page_cap", "Source page safety cap reached; collection remains explicitly partial.", source_id)
    except EvidenceError as exc:
        receipt["status"] = "partial" if rows else "denied" if exc.http_status in (401, 403) else "error"
        receipt["records"] = len(rows)
        receipt["errors"].append(exc.public())
        return rows, receipt


def read_dbx_pages(reader, base_url, source_id, reference, list_key, normalize, base_params=None, token_param="page_token"):
    params = dict(base_params or {})
    first_url = base_url + ("?" + urlencode(params) if params else "")
    receipt = source_receipt(
        source_id, reference, page_cap=MAX_PAGES, row_cap=MAX_ROWS,
        pagination_complete=False, read_signature="GET " + first_url,
    )
    rows, seen_ids, seen_tokens = [], set(), set()
    reader.allow(first_url, "GET")
    current_token = None
    try:
        for page_number in range(MAX_PAGES):
            page_params = dict(params)
            if current_token is not None:
                page_params[token_param] = current_token
            current_url = base_url + ("?" + urlencode(page_params) if page_params else "")
            payload = obj(reader.request("GET", current_url, source_id), source_id)
            receipt["pages"] = page_number + 1
            raw_list = payload.get(list_key)
            page = [] if raw_list is None else array(raw_list, source_id)
            if len(rows) + len(page) > MAX_ROWS:
                raise EvidenceError("row_cap", "Databricks API row safety cap reached; scope was not silently narrowed.", source_id)
            for raw in page:
                row = normalize(raw)
                identity = str(row.get("id") or row.get("name") or "")
                if not identity or identity in seen_ids:
                    raise EvidenceError("invalid_pagination", "Databricks object identity is absent or repeated.", source_id)
                seen_ids.add(identity)
                rows.append(row)
            receipt["records"] = len(rows)
            next_token = payload.get("next_page_token")
            has_more = payload.get("has_more")
            if not next_token:
                if has_more is True:
                    raise EvidenceError("missing_continuation", "Databricks list reported has_more=true without next_page_token.", source_id)
                receipt["pagination_complete"] = True
                return rows, receipt
            next_token = text(next_token, source_id, 4096)
            if not next_token or next_token in seen_tokens:
                raise EvidenceError("pagination_loop", "Databricks pagination token is empty or repeated.", source_id)
            seen_tokens.add(next_token)
            current_token = next_token
        raise EvidenceError("page_cap", "Databricks page safety cap reached; collection remains explicitly partial.", source_id)
    except EvidenceError as exc:
        receipt["status"] = "partial" if rows else "denied" if exc.http_status in (401, 403) else "error"
        receipt["records"] = len(rows)
        receipt["errors"].append(exc.public())
        return rows, receipt


def read_one(reader, url, source_id, reference, normalize):
    receipt = source_receipt(source_id, reference, pages=1, read_signature="GET " + url)
    try:
        reader.allow(url)
        result = normalize(obj(reader.request("GET", url, source_id), source_id))
        receipt["records"] = 1
        return result, receipt
    except EvidenceError as exc:
        receipt.update(status="denied" if exc.http_status in (401, 403) else "error", records=0, errors=[exc.public()])
        return None, receipt


def param_val(params_obj, key, kind="str", source_id="arm_workspace"):
    entry = pick(params_obj, key)
    if entry is None:
        return None
    val = pick(entry, "value") if isinstance(entry, dict) else entry
    if kind == "bool":
        return boolean(val, source_id)
    return text(val, source_id, 2048)


def normalize_workspace(raw, source_id, reference, config):
    resource_id = arm_id(raw.get("id"), SUBSCRIPTION_ID)
    if resource_id.lower() != config["id"].lower():
        raise EvidenceError("scope_mismatch", "ARM returned a different Databricks workspace ID.", source_id)
    props = obj(raw.get("properties", {}), source_id)
    params = obj(props.get("parameters", {}), source_id)
    workspace_url = text(props.get("workspaceUrl"), source_id, 256)
    if workspace_url and config["workspace_host"] and workspace_url.lower() != config["workspace_host"].lower():
        raise EvidenceError("scope_mismatch", "ARM workspaceUrl differs from the configured workspace_host.", source_id)
    managed_rg_id = text(props.get("managedResourceGroupId"), source_id, 2048)
    managed_rg_name = None
    if managed_rg_id:
        arm_id_parts = managed_rg_id.split("/")
        if len(arm_id_parts) >= 5 and arm_id_parts[1].lower() == "subscriptions" and arm_id_parts[3].lower() == "resourcegroups":
            managed_rg_name = text(arm_id_parts[4], source_id, 90)
    access_connector = obj(props.get("accessConnector", {}), source_id) if props.get("accessConnector") else {}
    ac_id = arm_id(access_connector.get("id"), SUBSCRIPTION_ID) if access_connector.get("id") else None
    ac_uami = arm_id(access_connector.get("userAssignedIdentityId"), SUBSCRIPTION_ID) if access_connector.get("userAssignedIdentityId") else None
    custom_vnet_id = param_val(params, "customVirtualNetworkId", "str", source_id)
    if custom_vnet_id:
        custom_vnet_id = arm_id(custom_vnet_id, SUBSCRIPTION_ID)
    enc_entities = obj(pick(props, "encryption", "entities") or {}, source_id)
    managed_services_cmk = obj(enc_entities.get("managedServices", {}), source_id) if enc_entities.get("managedServices") else {}
    managed_disk_cmk = obj(enc_entities.get("managedDisk", {}), source_id) if enc_entities.get("managedDisk") else {}
    esc = obj(props.get("enhancedSecurityCompliance", {}), source_id) if props.get("enhancedSecurityCompliance") else {}
    default_cat = obj(props.get("defaultCatalog", {}), source_id) if props.get("defaultCatalog") else {}
    pe_connections = []
    for pe in array(props.get("privateEndpointConnections", []), source_id):
        pe_props = obj(pe.get("properties", {}), source_id)
        pe_connections.append({
            "id": text(pe.get("id"), source_id, 2048),
            "name": text(pe.get("name"), source_id, 256),
            "private_endpoint_id": text(pick(pe_props, "privateEndpoint", "id"), source_id, 2048),
            "status": text(pick(pe_props, "privateLinkServiceConnectionState", "status"), source_id, 64),
            "group_ids": strings(pe_props.get("groupIds", []), source_id),
        })
    return {
        "id": resource_id,
        "resource_id": resource_id,
        "name": text(raw.get("name"), source_id, 64),
        "workspace_name": config["name"],
        "workspace_id": resource_id,
        "workspace_guid": text(props.get("workspaceId"), source_id, 128),
        "workspace_url": workspace_url or config["workspace_host"],
        "subscription_id": SUBSCRIPTION_ID,
        "sre_tenant_id": config["sre_tenant_id"],
        "target_tenant_id": config["target_tenant_id"],
        "auth_mode": config["auth_mode"],
        "cross_tenant": config["cross_tenant"],
        "resource_group": config["resource_group"],
        "region": text(raw.get("location"), source_id, 64),
        "sku_name": text(pick(raw, "sku", "name"), source_id, 64),
        "sku_tier": text(pick(raw, "sku", "tier"), source_id, 64),
        "provisioning_state": text(props.get("provisioningState"), source_id, 64),
        "managed_resource_group_id": managed_rg_id,
        "managed_resource_group": managed_rg_name,
        "public_network_access": text(props.get("publicNetworkAccess"), source_id, 64),
        "required_nsg_rules": text(props.get("requiredNsgRules"), source_id, 64),
        "default_storage_firewall": text(props.get("defaultStorageFirewall"), source_id, 64),
        "default_catalog_type": text(default_cat.get("initialType"), source_id, 64),
        "default_catalog_name": text(default_cat.get("initialName"), source_id, 256),
        "enable_no_public_ip": param_val(params, "enableNoPublicIp", "bool", source_id),
        "custom_virtual_network_id": custom_vnet_id,
        "custom_public_subnet_name": param_val(params, "customPublicSubnetName", "str", source_id),
        "custom_private_subnet_name": param_val(params, "customPrivateSubnetName", "str", source_id),
        "nat_gateway_name": param_val(params, "natGatewayName", "str", source_id),
        "public_ip_name": param_val(params, "publicIpName", "str", source_id),
        "dbfs_storage_account_name": param_val(params, "storageAccountName", "str", source_id),
        "dbfs_storage_sku": param_val(params, "storageAccountSkuName", "str", source_id),
        "prepare_encryption": param_val(params, "prepareEncryption", "bool", source_id),
        "require_infrastructure_encryption": param_val(params, "requireInfrastructureEncryption", "bool", source_id),
        "aml_workspace_id": param_val(params, "amlWorkspaceId", "str", source_id),
        "access_connector": {
            "id": ac_id,
            "identity_type": text(access_connector.get("identityType"), source_id, 64),
            "user_assigned_identity_id": ac_uami,
        },
        "cmk": {
            "managed_services_key_source": text(managed_services_cmk.get("keySource"), source_id, 64),
            "managed_services_vault_uri": text(pick(managed_services_cmk, "keyVaultProperties", "keyVaultUri"), source_id, 512),
            "managed_disk_key_source": text(managed_disk_cmk.get("keySource"), source_id, 64),
            "managed_disk_vault_uri": text(pick(managed_disk_cmk, "keyVaultProperties", "keyVaultUri"), source_id, 512),
            "managed_disk_auto_rotation": boolean(managed_disk_cmk.get("rotationToLatestKeyVersionEnabled"), source_id),
        },
        "enhanced_security_compliance": {
            "automatic_cluster_update": text(pick(esc, "automaticClusterUpdate", "value"), source_id, 64),
            "enhanced_security_monitoring": text(pick(esc, "enhancedSecurityMonitoring", "value"), source_id, 64),
            "compliance_security_profile": text(pick(esc, "complianceSecurityProfile", "value"), source_id, 64),
            "compliance_standards": strings(pick(esc, "complianceSecurityProfile", "complianceStandards"), source_id),
        },
        "private_endpoint_connections": pe_connections,
        "tags": tags_map(raw.get("tags"), source_id),
        "source_id": source_id,
        "observed_at": reference,
    }


def normalize_outbound_endpoint(raw, source_id, reference, config):
    category = text(raw.get("category"), source_id, 128)
    if not category:
        raise EvidenceError("invalid_record", "Outbound dependency endpoint category is required.", source_id)
    endpoints = []
    for ep in array(raw.get("endpoints", []), source_id):
        domain = text(ep.get("domainName"), source_id, 512)
        ports = [
            {"port": number(d.get("port"), source_id), "region": text(d.get("region"), source_id, 64)}
            for d in array(ep.get("endpointDetails", []), source_id)
        ]
        endpoints.append({"domain_name": domain, "details": ports})
    return {
        "id": config["id"] + "/outboundEndpoints/" + re.sub(r"[^A-Za-z0-9_.-]+", "-", category),
        "resource_id": config["id"],
        "workspace_name": config["name"],
        "workspace_id": config["id"],
        "name": category,
        "category": category,
        "kind": "OutboundNetworkDependency",
        "endpoints": endpoints,
        "source_id": source_id,
        "observed_at": reference,
    }


def normalize_resource(raw, source_id, reference, config, association):
    resource_id = arm_id(raw.get("id"), SUBSCRIPTION_ID)
    kind = resource_type(resource_id)
    if kind not in RESOURCE_APIS:
        raise EvidenceError("unsupported_resource_type", "Resource detail type is not in the fixed whitelist.", source_id)
    props = obj(raw.get("properties", {}), source_id)
    row = {
        "id": resource_id,
        "resource_id": resource_id,
        "name": text(raw.get("name"), source_id, 256),
        "kind": kind,
        "resource_kind": kind,
        "region": text(raw.get("location"), source_id, 64),
        "sku_name": text(pick(raw, "sku", "name"), source_id, 64),
        "sku_tier": text(pick(raw, "sku", "tier"), source_id, 64),
        "provisioning_state": text(props.get("provisioningState"), source_id, 64),
        "association": association,
        "configuration": {},
        "workspace_name": config["name"],
        "workspace_id": config["id"],
        "source_id": source_id,
        "observed_at": reference,
    }
    if kind == "microsoft.databricks/accessconnectors":
        identity_block = obj(raw.get("identity", {}), source_id) if raw.get("identity") else {}
        row["identity_type"] = text(identity_block.get("type"), source_id, 64)
        row["principal_id"] = text(identity_block.get("principalId"), source_id, 64)
        row["user_assigned_identities"] = [
            arm_id(k, SUBSCRIPTION_ID) for k in obj(identity_block.get("userAssignedIdentities") or {}, source_id)
        ]
    elif kind == "microsoft.storage/storageaccounts":
        for field in ("supportsHttpsTrafficOnly", "minimumTlsVersion", "allowBlobPublicAccess", "allowSharedKeyAccess", "publicNetworkAccess", "isHnsEnabled"):
            val = props.get(field)
            row["configuration"][field] = boolean(val, source_id) if isinstance(val, bool) or val is None else text(str(val), source_id, 64)
        row["dfs_endpoint"] = text(pick(props, "primaryEndpoints", "dfs"), source_id, 512)
        row["blob_endpoint"] = text(pick(props, "primaryEndpoints", "blob"), source_id, 512)
    elif kind == "microsoft.keyvault/vaults":
        for field in ("enableRbacAuthorization", "enablePurgeProtection", "enableSoftDelete", "softDeleteRetentionInDays", "publicNetworkAccess", "vaultUri"):
            val = props.get(field)
            if isinstance(val, bool) or val is None:
                row["configuration"][field] = val
            elif isinstance(val, (int, float)):
                row["configuration"][field] = number(val, source_id)
            else:
                row["configuration"][field] = text(str(val), source_id, 512)
        row["vault_uri"] = text(props.get("vaultUri"), source_id, 512)
    elif kind == "microsoft.network/virtualnetworks":
        row["address_space"] = strings(pick(props, "addressSpace", "addressPrefixes"), source_id)
        row["subnet_ids"] = [arm_id(s.get("id"), SUBSCRIPTION_ID) for s in array(props.get("subnets", []), source_id) if s.get("id")]
    elif kind == "microsoft.network/virtualnetworks/subnets":
        row["address_prefix"] = text(props.get("addressPrefix"), source_id, 128)
        row["nsg_id"] = arm_id(pick(props, "networkSecurityGroup", "id"), SUBSCRIPTION_ID) if pick(props, "networkSecurityGroup", "id") else None
        row["route_table_id"] = arm_id(pick(props, "routeTable", "id"), SUBSCRIPTION_ID) if pick(props, "routeTable", "id") else None
        row["nat_gateway_id"] = arm_id(pick(props, "natGateway", "id"), SUBSCRIPTION_ID) if pick(props, "natGateway", "id") else None
        row["delegations"] = [text(pick(d, "properties", "serviceName") or d.get("name"), source_id, 256) for d in array(props.get("delegations", []), source_id)]
    elif kind == "microsoft.network/routetables":
        row["disable_bgp_route_propagation"] = boolean(props.get("disableBgpRoutePropagation"), source_id)
        row["routes"] = [
            {
                "name": text(r.get("name"), source_id, 256),
                "address_prefix": text(pick(r, "properties", "addressPrefix"), source_id, 128),
                "next_hop_type": text(pick(r, "properties", "nextHopType"), source_id, 64),
                "next_hop_ip_address": text(pick(r, "properties", "nextHopIpAddress"), source_id, 128),
            }
            for r in array(props.get("routes", []), source_id)
        ]
    elif kind == "microsoft.network/networksecuritygroups":
        row["security_rules"] = [
            {
                key: number(pick(item, "properties", key), source_id) if key == "priority"
                else strings(pick(item, "properties", key), source_id) if key.endswith(("Prefixes", "Ranges"))
                else text(pick(item, "properties", key), source_id, 256)
                for key in ("priority", "direction", "access", "protocol", "sourceAddressPrefix", "sourceAddressPrefixes", "destinationPortRange", "destinationPortRanges", "destinationAddressPrefix")
            }
            for item in array(props.get("securityRules", []), source_id)
        ]
    elif kind == "microsoft.network/natgateways":
        row["public_ip_ids"] = [arm_id(ip.get("id"), SUBSCRIPTION_ID) for ip in array(props.get("publicIpAddresses", []), source_id) if ip.get("id")]
    elif kind == "microsoft.network/publicipaddresses":
        row["configuration"]["ipAddress"] = text(props.get("ipAddress"), source_id, 128)
        row["configuration"]["publicIPAllocationMethod"] = text(props.get("publicIPAllocationMethod"), source_id, 64)
    elif kind == "microsoft.network/privateendpoints":
        row["subnet_id"] = arm_id(pick(props, "subnet", "id"), SUBSCRIPTION_ID) if pick(props, "subnet", "id") else None
        connections = array(props.get("privateLinkServiceConnections", []) or props.get("manualPrivateLinkServiceConnections", []), source_id)
        row["connections"] = [
            {
                "target_id": text(pick(c, "properties", "privateLinkServiceId"), source_id, 2048),
                "group_ids": strings(pick(c, "properties", "groupIds"), source_id),
                "status": text(pick(c, "properties", "privateLinkServiceConnectionState", "status"), source_id, 64),
            }
            for c in connections
        ]
    elif kind == "microsoft.managedidentity/userassignedidentities":
        row["principal_id"] = text(props.get("principalId"), source_id, 64)
        row["client_id"] = text(props.get("clientId"), source_id, 64)
    return row


def referenced_resource_ids(row):
    refs = []
    for field in ("subnet_ids", "public_ip_ids", "user_assigned_identities"):
        refs.extend((val, field) for val in row.get(field, []) if val)
    for field in ("nsg_id", "route_table_id", "nat_gateway_id", "subnet_id"):
        if row.get(field):
            refs.append((row[field], field))
    if row.get("resource_kind") == "microsoft.network/virtualnetworks/subnets":
        refs.append((re.split(r"/subnets/", row["id"], flags=re.IGNORECASE)[0], "parent_virtual_network_id"))
    for val, field in refs:
        val = arm_id(val, SUBSCRIPTION_ID)
        if resource_type(val) in RESOURCE_APIS:
            yield val, field


def normalize_cluster(raw, source_id, reference, config):
    cid = text(raw.get("cluster_id"), source_id, 128)
    name = text(raw.get("cluster_name"), source_id, 256) or cid
    if not cid:
        raise EvidenceError("invalid_record", "Databricks cluster requires cluster_id.", source_id)
    autoscale = obj(raw.get("autoscale", {}), source_id) if raw.get("autoscale") else None
    return {
        "id": cid,
        "cluster_id": cid,
        "name": name,
        "workload_name": name,
        "kind": "JobCluster" if raw.get("cluster_source") == "JOB" else "AllPurposeCluster",
        "cluster_source": text(raw.get("cluster_source"), source_id, 64),
        "state": text(raw.get("state"), source_id, 64),
        "spark_version": text(raw.get("spark_version"), source_id, 128),
        "node_type_id": text(raw.get("node_type_id"), source_id, 128),
        "driver_node_type_id": text(raw.get("driver_node_type_id"), source_id, 128),
        "num_workers": number(raw.get("num_workers"), source_id),
        "autoscale": {
            "min_workers": number(autoscale.get("min_workers"), source_id),
            "max_workers": number(autoscale.get("max_workers"), source_id),
        } if autoscale else None,
        "autotermination_minutes": number(raw.get("autotermination_minutes"), source_id),
        "data_security_mode": text(raw.get("data_security_mode"), source_id, 64),
        "single_user_name": text(raw.get("single_user_name"), source_id, 256),
        "policy_id": text(raw.get("policy_id"), source_id, 128),
        "instance_pool_id": text(raw.get("instance_pool_id"), source_id, 128),
        "driver_instance_pool_id": text(raw.get("driver_instance_pool_id"), source_id, 128),
        "runtime_engine": text(raw.get("runtime_engine"), source_id, 64),
        "custom_tags": tags_map(raw.get("custom_tags"), source_id),
        "resource_id": config["id"],
        "workspace_name": config["name"],
        "workspace_id": config["id"],
        "source_id": source_id,
        "observed_at": reference,
    }


def normalize_pool(raw, source_id, reference, config):
    pid = text(raw.get("instance_pool_id"), source_id, 128)
    name = text(raw.get("instance_pool_name"), source_id, 256) or pid
    if not pid:
        raise EvidenceError("invalid_record", "Instance pool requires instance_pool_id.", source_id)
    return {
        "id": pid,
        "instance_pool_id": pid,
        "name": name,
        "workload_name": name,
        "kind": "InstancePool",
        "node_type_id": text(raw.get("node_type_id"), source_id, 128),
        "min_idle_instances": number(raw.get("min_idle_instances"), source_id),
        "max_capacity": number(raw.get("max_capacity"), source_id),
        "idle_instance_autotermination_minutes": number(raw.get("idle_instance_autotermination_minutes"), source_id),
        "resource_id": config["id"],
        "workspace_name": config["name"],
        "workspace_id": config["id"],
        "source_id": source_id,
        "observed_at": reference,
    }


def normalize_policy(raw, source_id, reference, config):
    pol_id = text(raw.get("policy_id"), source_id, 128)
    name = text(raw.get("name"), source_id, 256) or pol_id
    if not pol_id:
        raise EvidenceError("invalid_record", "Cluster policy requires policy_id.", source_id)
    return {
        "id": pol_id,
        "policy_id": pol_id,
        "name": name,
        "workload_name": name,
        "kind": "ClusterPolicy",
        "policy_family_id": text(raw.get("policy_family_id"), source_id, 128),
        "is_default": boolean(raw.get("is_default"), source_id),
        "resource_id": config["id"],
        "workspace_name": config["name"],
        "workspace_id": config["id"],
        "source_id": source_id,
        "observed_at": reference,
    }


def normalize_job(raw, source_id, reference, config, from_detail=False):
    raw_job_id = raw.get("job_id")
    if raw_job_id is None or isinstance(raw_job_id, bool):
        raise EvidenceError("invalid_record", "Databricks job requires job_id.", source_id)
    jid = str(raw_job_id)
    settings = obj(raw.get("settings", {}), source_id)
    name = text(settings.get("name"), source_id, 512) or ("job-" + jid)
    run_as = obj(settings.get("run_as") or raw.get("run_as") or {}, source_id)
    job_clusters = []
    for jc in array(settings.get("job_clusters", []), source_id):
        key = text(jc.get("job_cluster_key"), source_id, 128)
        new_cluster = obj(jc.get("new_cluster", {}), source_id)
        if key:
            job_clusters.append({
                "job_cluster_key": key,
                "spark_version": text(new_cluster.get("spark_version"), source_id, 128),
                "node_type_id": text(new_cluster.get("node_type_id"), source_id, 128),
                "policy_id": text(new_cluster.get("policy_id"), source_id, 128),
                "instance_pool_id": text(new_cluster.get("instance_pool_id"), source_id, 128),
                "data_security_mode": text(new_cluster.get("data_security_mode"), source_id, 64),
            })
    tasks = []
    for t in array(settings.get("tasks", []), source_id):
        tkey = text(t.get("task_key"), source_id, 256)
        if not tkey:
            raise EvidenceError("invalid_record", "Job task requires task_key.", source_id)
        deps = [text(d.get("task_key"), source_id, 256) for d in array(t.get("depends_on", []), source_id) if d.get("task_key")]
        run_job_target = pick(t, "run_job_task", "job_id")
        tasks.append({
            "task_key": tkey,
            "depends_on": deps,
            "existing_cluster_id": text(t.get("existing_cluster_id"), source_id, 128),
            "job_cluster_key": text(t.get("job_cluster_key"), source_id, 128),
            "environment_key": text(t.get("environment_key"), source_id, 128),
            "pipeline_id": text(pick(t, "pipeline_task", "pipeline_id"), source_id, 128),
            "warehouse_id": text(pick(t, "sql_task", "warehouse_id"), source_id, 128),
            "run_job_id": str(run_job_target) if run_job_target is not None and not isinstance(run_job_target, bool) else None,
            "notebook_path": text(pick(t, "notebook_task", "notebook_path"), source_id, 1024),
            "timeout_seconds": number(t.get("timeout_seconds"), source_id),
            "max_retries": number(t.get("max_retries"), source_id),
        })
    notifs = obj(settings.get("email_notifications", {}), source_id)
    webhooks = obj(settings.get("webhook_notifications", {}), source_id)
    has_notifications = bool(
        notifs.get("on_failure") or notifs.get("on_duration_warning_threshold_exceeded")
        or webhooks.get("on_failure") or settings.get("notification_settings")
    )
    schedule = settings.get("schedule") or settings.get("trigger") or settings.get("continuous")
    has_more_flag = boolean(raw.get("has_more"), source_id) is True
    next_token_present = bool(text(raw.get("next_page_token"), source_id, 4096))
    tasks_incomplete = has_more_flag or next_token_present or len(tasks) >= 100 or len(job_clusters) >= 100
    return {
        "id": jid,
        "job_id": jid,
        "name": name,
        "workload_name": name,
        "kind": "Job",
        "scheduled": bool(schedule),
        "timeout_seconds": number(settings.get("timeout_seconds"), source_id),
        "max_concurrent_runs": number(settings.get("max_concurrent_runs"), source_id),
        "has_notifications": has_notifications,
        "run_as_service_principal": text(run_as.get("service_principal_name"), source_id, 256),
        "run_as_user_name": text(run_as.get("user_name"), source_id, 256),
        "job_clusters": job_clusters,
        "tasks": tasks,
        "tasks_incomplete": tasks_incomplete,
        "tags": tags_map(settings.get("tags"), source_id),
        "resource_id": config["id"],
        "workspace_name": config["name"],
        "workspace_id": config["id"],
        "source_id": source_id,
        "observed_at": reference,
    }


def normalize_pipeline(raw, source_id, reference, config, detail=None, detail_source_id=None):
    pid = text(raw.get("pipeline_id") or (detail.get("pipeline_id") if isinstance(detail, dict) else None), source_id, 128)
    spec_source = detail_source_id or source_id
    spec = obj(
        (detail.get("spec") if isinstance(detail, dict) and detail.get("spec") is not None else raw.get("spec")) or {},
        spec_source,
    )
    name = text((detail.get("name") if isinstance(detail, dict) else None) or spec.get("name") or raw.get("name"), source_id, 256) or pid
    if not pid:
        raise EvidenceError("invalid_record", "Pipeline requires pipeline_id.", source_id)
    has_spec = bool(spec) or any(raw.get(k) is not None for k in ("catalog", "schema", "target", "storage", "serverless", "continuous"))
    catalog_val = text(spec.get("catalog") if "catalog" in spec else raw.get("catalog"), spec_source, 256)
    schema_raw = (
        spec.get("schema")
        if "schema" in spec
        else spec.get("target")
        if "target" in spec
        else raw.get("schema")
        if "schema" in raw
        else raw.get("target")
    )
    target_val = text(schema_raw, spec_source, 256)
    storage_val = text(spec.get("storage") if "storage" in spec else raw.get("storage"), spec_source, 1024)
    serverless_val = boolean(spec.get("serverless") if "serverless" in spec else raw.get("serverless"), spec_source)
    continuous_val = boolean(spec.get("continuous") if "continuous" in spec else raw.get("continuous"), spec_source)
    clusters_spec = []
    for cl in array(spec.get("clusters", []), spec_source):
        clusters_spec.append({
            "label": text(cl.get("label"), spec_source, 128),
            "policy_id": text(cl.get("policy_id"), spec_source, 128),
            "instance_pool_id": text(cl.get("instance_pool_id"), spec_source, 128),
            "driver_instance_pool_id": text(cl.get("driver_instance_pool_id"), spec_source, 128),
            "node_type_id": text(cl.get("node_type_id"), spec_source, 128),
        })
    return {
        "id": pid,
        "pipeline_id": pid,
        "name": name,
        "workload_name": name,
        "kind": "LakeflowPipeline",
        "state": text((detail.get("state") if isinstance(detail, dict) and detail.get("state") else None) or raw.get("state"), source_id, 64),
        "catalog": catalog_val,
        "schema": target_val,
        "target": target_val,
        "storage": storage_val,
        "serverless": serverless_val,
        "continuous": continuous_val,
        "clusters": clusters_spec,
        "detail_collected": has_spec,
        "detail_source_id": spec_source if has_spec else None,
        "resource_id": config["id"],
        "workspace_name": config["name"],
        "workspace_id": config["id"],
        "source_id": source_id,
        "observed_at": reference,
    }


def normalize_warehouse(raw, source_id, reference, config):
    wid = text(raw.get("id"), source_id, 128)
    name = text(raw.get("name"), source_id, 256) or wid
    if not wid:
        raise EvidenceError("invalid_record", "SQL warehouse requires id.", source_id)
    return {
        "id": wid,
        "warehouse_id": wid,
        "name": name,
        "workload_name": name,
        "kind": "SqlWarehouse",
        "state": text(raw.get("state"), source_id, 64),
        "cluster_size": text(raw.get("cluster_size"), source_id, 64),
        "warehouse_type": text(raw.get("warehouse_type"), source_id, 64),
        "enable_serverless_compute": boolean(raw.get("enable_serverless_compute"), source_id),
        "auto_stop_mins": number(raw.get("auto_stop_mins"), source_id),
        "min_num_clusters": number(raw.get("min_num_clusters"), source_id),
        "max_num_clusters": number(raw.get("max_num_clusters"), source_id),
        "enable_photon": boolean(raw.get("enable_photon"), source_id),
        "resource_id": config["id"],
        "workspace_name": config["name"],
        "workspace_id": config["id"],
        "source_id": source_id,
        "observed_at": reference,
    }


def normalize_secret_scope(raw, source_id, reference, config):
    name = text(raw.get("name"), source_id, 256)
    if not name:
        raise EvidenceError("invalid_record", "Secret scope requires name.", source_id)
    kv = obj(raw.get("keyvault_metadata", {}), source_id) if raw.get("keyvault_metadata") else {}
    kv_resource_id = text(kv.get("resource_id"), source_id, 2048)
    if kv_resource_id and kv_resource_id.lower().startswith("/subscriptions/" + SUBSCRIPTION_ID.lower() + "/"):
        kv_resource_id = arm_id(kv_resource_id, SUBSCRIPTION_ID)
    return {
        "id": "scope:" + name,
        "name": name,
        "workload_name": name,
        "kind": "SecretScope",
        "backend_type": text(raw.get("backend_type"), source_id, 64),
        "keyvault_resource_id": kv_resource_id,
        "keyvault_dns_name": text(kv.get("dns_name"), source_id, 512),
        "resource_id": config["id"],
        "workspace_name": config["name"],
        "workspace_id": config["id"],
        "source_id": source_id,
        "observed_at": reference,
    }


def normalize_init_script(raw, source_id, reference, config):
    sid = text(raw.get("script_id"), source_id, 128)
    name = text(raw.get("name"), source_id, 256) or sid
    if not sid:
        raise EvidenceError("invalid_record", "Global init script requires script_id.", source_id)
    return {
        "id": sid,
        "script_id": sid,
        "name": name,
        "workload_name": name,
        "kind": "GlobalInitScript",
        "enabled": boolean(raw.get("enabled"), source_id),
        "position": number(raw.get("position"), source_id),
        "resource_id": config["id"],
        "workspace_name": config["name"],
        "workspace_id": config["id"],
        "source_id": source_id,
        "observed_at": reference,
    }


def normalize_metastore(raw, source_id, reference, config):
    mid = text(raw.get("metastore_id"), source_id, 128)
    name = text(raw.get("name"), source_id, 256) or mid
    if not mid:
        raise EvidenceError("invalid_record", "Unity Catalog metastore requires metastore_id.", source_id)
    return {
        "id": mid,
        "metastore_id": mid,
        "name": name,
        "workload_name": name,
        "kind": "UnityCatalogMetastore",
        "region": text(raw.get("region"), source_id, 64),
        "storage_root": text(raw.get("storage_root"), source_id, 1024),
        "storage_root_credential_id": text(raw.get("storage_root_credential_id"), source_id, 256),
        "storage_root_credential_name": text(raw.get("storage_root_credential_name"), source_id, 256),
        "privilege_model_version": text(raw.get("privilege_model_version"), source_id, 64),
        "global_metastore_id": text(raw.get("global_metastore_id"), source_id, 256),
        "resource_id": config["id"],
        "workspace_name": config["name"],
        "workspace_id": config["id"],
        "source_id": source_id,
        "observed_at": reference,
    }


def normalize_catalog(raw, source_id, reference, config):
    name = text(raw.get("name"), source_id, 256)
    if not name:
        raise EvidenceError("invalid_record", "Unity Catalog catalog requires name.", source_id)
    return {
        "id": "catalog:" + name,
        "name": name,
        "workload_name": name,
        "kind": "UnityCatalog",
        "catalog_type": text(raw.get("catalog_type"), source_id, 64),
        "storage_root": text(raw.get("storage_root"), source_id, 1024),
        "storage_location": text(raw.get("storage_location"), source_id, 1024),
        "isolation_mode": text(raw.get("isolation_mode"), source_id, 64),
        "connection_name": text(raw.get("connection_name"), source_id, 256),
        "metastore_id": text(raw.get("metastore_id"), source_id, 128),
        "resource_id": config["id"],
        "workspace_name": config["name"],
        "workspace_id": config["id"],
        "source_id": source_id,
        "observed_at": reference,
    }


def normalize_schema(raw, source_id, reference, config):
    full_name = text(raw.get("full_name"), source_id, 512)
    name = text(raw.get("name"), source_id, 256)
    catalog_name = text(raw.get("catalog_name"), source_id, 256)
    if not full_name or not name or not catalog_name:
        raise EvidenceError("invalid_record", "Unity Catalog schema requires full_name, catalog_name and name.", source_id)
    return {
        "id": "schema:" + full_name,
        "full_name": full_name,
        "name": name,
        "workload_name": full_name,
        "catalog_name": catalog_name,
        "kind": "UnitySchema",
        "storage_root": text(raw.get("storage_root"), source_id, 1024),
        "storage_location": text(raw.get("storage_location"), source_id, 1024),
        "metastore_id": text(raw.get("metastore_id"), source_id, 128),
        "resource_id": config["id"],
        "workspace_name": config["name"],
        "workspace_id": config["id"],
        "source_id": source_id,
        "observed_at": reference,
    }


def normalize_storage_credential(raw, source_id, reference, config):
    name = text(raw.get("name"), source_id, 256)
    if not name:
        raise EvidenceError("invalid_record", "Storage credential requires name.", source_id)
    mi = obj(raw.get("azure_managed_identity", {}), source_id) if raw.get("azure_managed_identity") else {}
    sp = obj(raw.get("azure_service_principal", {}), source_id) if raw.get("azure_service_principal") else {}
    ac_id = text(mi.get("access_connector_id"), source_id, 2048)
    mi_id = text(mi.get("managed_identity_id"), source_id, 2048)
    return {
        "id": "storage_credential:" + name,
        "credential_id": text(raw.get("id"), source_id, 128),
        "name": name,
        "workload_name": name,
        "kind": "StorageCredential",
        "read_only": boolean(raw.get("read_only"), source_id),
        "isolation_mode": text(raw.get("isolation_mode"), source_id, 64),
        "uses_managed_identity": bool(ac_id),
        "uses_service_principal": bool(sp.get("application_id") or sp.get("directory_id")),
        "access_connector_id": ac_id,
        "managed_identity_id": mi_id,
        "service_principal_application_id": text(sp.get("application_id"), source_id, 128),
        "resource_id": config["id"],
        "workspace_name": config["name"],
        "workspace_id": config["id"],
        "source_id": source_id,
        "observed_at": reference,
    }


def normalize_external_location(raw, source_id, reference, config):
    name = text(raw.get("name"), source_id, 256)
    if not name:
        raise EvidenceError("invalid_record", "External location requires name.", source_id)
    url = text(raw.get("url"), source_id, 2048)
    return {
        "id": "external_location:" + name,
        "name": name,
        "workload_name": name,
        "kind": "ExternalLocation",
        "url": url,
        "credential_name": text(raw.get("credential_name"), source_id, 256),
        "credential_id": text(raw.get("credential_id"), source_id, 128),
        "read_only": boolean(raw.get("read_only"), source_id),
        "isolation_mode": text(raw.get("isolation_mode"), source_id, 64),
        "metastore_id": text(raw.get("metastore_id"), source_id, 128),
        "resource_id": config["id"],
        "workspace_name": config["name"],
        "workspace_id": config["id"],
        "source_id": source_id,
        "observed_at": reference,
    }


def normalize_connection(raw, source_id, reference, config):
    name = text(raw.get("name"), source_id, 256)
    if not name:
        raise EvidenceError("invalid_record", "Unity Catalog connection requires name.", source_id)
    return {
        "id": "connection:" + name,
        "connection_id": text(raw.get("connection_id"), source_id, 128),
        "name": name,
        "workload_name": name,
        "kind": "LakehouseFederationConnection",
        "connection_type": text(raw.get("connection_type"), source_id, 64),
        "credential_type": text(raw.get("credential_type"), source_id, 64),
        "host": text(pick(raw, "options", "host") or raw.get("url"), source_id, 512),
        "read_only": boolean(raw.get("read_only"), source_id),
        "resource_id": config["id"],
        "workspace_name": config["name"],
        "workspace_id": config["id"],
        "source_id": source_id,
        "observed_at": reference,
    }


def extract_storage_account_from_uri(uri_str):
    if not isinstance(uri_str, str):
        return None
    match = re.match(r"^(?:abfss?|wasbs?)://(?:[^@/?#]+@)?([a-z0-9]{3,24})\.(?:dfs|blob)\.core\.windows\.net(?:/|$)", uri_str.strip(), re.IGNORECASE)
    return match.group(1).lower() if match else None


def extract_vault_host(uri_str):
    if not isinstance(uri_str, str):
        return None
    try:
        parsed = urlsplit(uri_str.strip())
    except ValueError:
        return None
    if parsed.scheme == "https" and parsed.hostname and parsed.hostname.lower().endswith(".vault.azure.net"):
        return parsed.hostname.lower()
    return None


def collect_live(config, reference, deadline=None):
    identity = Identity(config)
    try:
        if deadline is not None:
            identity.deadline = min(identity.deadline, deadline)
        arm = HttpReader(identity, ARM_ORIGIN, "arm")
        raw = {
            "sources": [],
            "inventory": {
                "clusters": [],
                "instance_pools": [],
                "cluster_policies": [],
                "jobs": [],
                "pipelines": [],
                "sql_warehouses": [],
                "secret_scopes": [],
                "global_init_scripts": [],
                "uc_metastore": None,
                "uc_catalogs": [],
                "uc_schemas": [],
                "uc_storage_credentials": [],
                "uc_external_locations": [],
                "uc_connections": [],
                "outbound_endpoints": [],
                "related_resources": [],
            },
            "requirements": config["requirements"],
            "workspace_conf": None,
            "arm_diagnostics": [],
            "advisor": [],
            "cost_rows": [],
        }
        ws_url = ARM_ORIGIN + config["id"] + "?api-version=" + DATABRICKS_ARM_API
        workspace, receipt = read_one(arm, ws_url, "arm_workspace", reference, lambda item: normalize_workspace(item, "arm_workspace", reference, config))
        raw["sources"].append(receipt)
        workspace_arm_error = None
        if workspace is None:
            workspace_arm_error = receipt["errors"][0]
            if not config["workspace_api_enabled"]:
                raise EvidenceError(workspace_arm_error["code"], "The approved primary Databricks workspace could not be read; no synthetic/empty live report.", "arm_workspace", workspace_arm_error["http_status"])
            receipt["note"] = "Primary ARM workspace GET returned non-complete status; ARM control-plane checks remain Not evaluated while Plane 2 Workspace/Unity Catalog REST is evaluated."
            workspace = {
                "id": config["id"],
                "resource_id": config["id"],
                "name": config["name"],
                "workspace_name": config["name"],
                "workspace_id": config["id"],
                "workspace_guid": None,
                "workspace_url": config["workspace_host"],
                "subscription_id": SUBSCRIPTION_ID,
                "sre_tenant_id": config["sre_tenant_id"],
                "target_tenant_id": config["target_tenant_id"],
                "auth_mode": config["auth_mode"],
                "cross_tenant": config["cross_tenant"],
                "resource_group": config["resource_group"],
                "region": None,
                "sku_name": None,
                "sku_tier": None,
                "provisioning_state": None,
                "managed_resource_group_id": None,
                "managed_resource_group": None,
                "public_network_access": None,
                "required_nsg_rules": None,
                "default_storage_firewall": None,
                "default_catalog_type": None,
                "default_catalog_name": None,
                "enable_no_public_ip": None,
                "custom_virtual_network_id": None,
                "custom_public_subnet_name": None,
                "custom_private_subnet_name": None,
                "nat_gateway_name": None,
                "public_ip_name": None,
                "dbfs_storage_account_name": None,
                "dbfs_storage_sku": None,
                "prepare_encryption": None,
                "require_infrastructure_encryption": None,
                "aml_workspace_id": None,
                "access_connector": {"id": None, "identity_type": None, "user_assigned_identity_id": None},
                "cmk": {
                    "managed_services_key_source": None,
                    "managed_services_vault_uri": None,
                    "managed_disk_key_source": None,
                    "managed_disk_vault_uri": None,
                    "managed_disk_auto_rotation": None,
                },
                "enhanced_security_compliance": {
                    "automatic_cluster_update": None,
                    "enhanced_security_monitoring": None,
                    "compliance_security_profile": None,
                    "compliance_standards": None,
                },
                "private_endpoint_connections": [],
                "tags": {},
                "source_id": "arm_workspace",
                "observed_at": reference,
            }
        raw["workspace"] = workspace

        outbound, out_receipt = read_arm_pages(
            arm,
            ARM_ORIGIN + config["id"] + "/outboundNetworkDependenciesEndpoints?api-version=" + DATABRICKS_ARM_API,
            "arm_outbound_endpoints",
            reference,
            lambda item: normalize_outbound_endpoint(item, "arm_outbound_endpoints", reference, config),
            top_level_list=True,
        )
        raw["inventory"]["outbound_endpoints"] = outbound
        raw["sources"].append(out_receipt)

        def normalize_diag(item):
            diag_id = text(item.get("id"), "arm_diagnostics", 2048)
            props = obj(item.get("properties", {}), "arm_diagnostics")
            return {
                "id": diag_id,
                "name": text(item.get("name"), "arm_diagnostics", 256),
                "workspace_id": text(props.get("workspaceId"), "arm_diagnostics", 2048),
                "storage_account_id": text(props.get("storageAccountId"), "arm_diagnostics", 2048),
                "event_hub_authorization_rule_id": text(props.get("eventHubAuthorizationRuleId"), "arm_diagnostics", 2048),
                "logs": [
                    {"category": text(l.get("category") or l.get("categoryGroup"), "arm_diagnostics", 128), "enabled": boolean(l.get("enabled"), "arm_diagnostics")}
                    for l in array(props.get("logs", []), "arm_diagnostics")
                ],
            }

        diags, diag_receipt = read_arm_pages(
            arm,
            ARM_ORIGIN + config["id"] + "/providers/Microsoft.Insights/diagnosticSettings?api-version=2021-05-01-preview",
            "arm_diagnostics",
            reference,
            normalize_diag,
        )
        raw["arm_diagnostics"] = diags
        raw["sources"].append(diag_receipt)

        related, queued, seen_related = [], [], set()
        related_attempt = 0
        related_cap_omitted = []

        def queue_related(rid, assoc):
            if not rid or not isinstance(rid, str) or not rid.lower().startswith("/subscriptions/" + SUBSCRIPTION_ID.lower() + "/"):
                return
            rid_clean = arm_id(rid, SUBSCRIPTION_ID)
            if resource_type(rid_clean) not in RESOURCE_APIS or rid_clean.lower() in seen_related:
                return
            if len(seen_related) >= MAX_RELATED_RESOURCES:
                if all(item["resource_id"].lower() != rid_clean.lower() for item in related_cap_omitted):
                    related_cap_omitted.append({"resource_id": rid_clean, "association": assoc})
                return
            seen_related.add(rid_clean.lower())
            queued.append((rid_clean, assoc))

        for rid in config["approved_related_resource_ids"]:
            queue_related(rid, {"type": "approved_configuration", "source_id": "configuration", "field": "approved_related_resource_ids"})
        if workspace["custom_virtual_network_id"]:
            queue_related(workspace["custom_virtual_network_id"], {"type": "direct_reference", "source_id": "arm_workspace", "resource_id": workspace["id"], "field": "parameters.customVirtualNetworkId"})
            for sub_field in ("custom_public_subnet_name", "custom_private_subnet_name"):
                if workspace.get(sub_field):
                    queue_related(
                        workspace["custom_virtual_network_id"] + "/subnets/" + workspace[sub_field],
                        {"type": "direct_reference", "source_id": "arm_workspace", "resource_id": workspace["id"], "field": "parameters." + sub_field},
                    )
        if pick(workspace, "access_connector", "id"):
            queue_related(workspace["access_connector"]["id"], {"type": "direct_reference", "source_id": "arm_workspace", "resource_id": workspace["id"], "field": "accessConnector.id"})
        if pick(workspace, "access_connector", "user_assigned_identity_id"):
            queue_related(workspace["access_connector"]["user_assigned_identity_id"], {"type": "direct_reference", "source_id": "arm_workspace", "resource_id": workspace["id"], "field": "accessConnector.userAssignedIdentityId"})
        for pe in workspace.get("private_endpoint_connections", []):
            if pe.get("private_endpoint_id"):
                queue_related(pe["private_endpoint_id"], {"type": "direct_reference", "source_id": "arm_workspace", "resource_id": workspace["id"], "field": "privateEndpointConnections"})

        if config["include_managed_resource_group"] and workspace.get("managed_resource_group"):
            mrg_url = ARM_ORIGIN + "/subscriptions/" + SUBSCRIPTION_ID + "/resourceGroups/" + workspace["managed_resource_group"] + "/resources?api-version=2021-04-01"
            def mrg_item(item):
                rid = arm_id(item.get("id"), SUBSCRIPTION_ID)
                return {"id": rid, "resource_id": rid, "type": text(item.get("type"), "arm_managed_rg_inventory", 256)}
            mrg_rows, mrg_receipt = read_arm_pages(arm, mrg_url, "arm_managed_rg_inventory", reference, mrg_item)
            raw["sources"].append(mrg_receipt)
            for item in mrg_rows:
                queue_related(item["id"], {"type": "managed_resource_group", "source_id": "arm_managed_rg_inventory", "resource_id": workspace["id"], "field": "managedResourceGroupId"})
        else:
            raw["sources"].append(source_receipt("arm_managed_rg_inventory", reference, "not_configured", "Managed resource group inventory disabled or absent."))

        def read_queued_related():
            nonlocal related_attempt
            while queued:
                rid, assoc = queued.pop(0)
                related_attempt += 1
                rtype = resource_type(rid)
                api_ver = RESOURCE_APIS[rtype]
                sid = "arm_resource_" + str(related_attempt) + "_" + hashlib.sha256(rid.lower().encode("utf-8")).hexdigest()[:8]
                row, r_receipt = read_one(
                    arm, ARM_ORIGIN + rid + "?api-version=" + api_ver, sid, reference,
                    lambda item, s=sid, a=assoc: normalize_resource(item, s, reference, config, a),
                )
                r_receipt["resource_id"] = rid
                raw["sources"].append(r_receipt)
                if row is not None:
                    related.append(row)
                    for child_id, field in referenced_resource_ids(row):
                        queue_related(child_id, {"type": "direct_reference", "source_id": sid, "resource_id": rid, "field": field})

        read_queued_related()

        if config["workspace_api_enabled"]:
            dbx = HttpReader(identity, "https://" + config["workspace_host"], "databricks")
            conf_url = dbx.origin + "/api/2.0/workspace-conf?" + urlencode({"keys": ",".join(WORKSPACE_CONF_KEYS)})
            def norm_conf(item):
                return {k: text(str(item.get(k)), "dbx_workspace_conf", 256) if item.get(k) is not None else None for k in WORKSPACE_CONF_KEYS}
            conf_obj, conf_receipt = read_one(dbx, conf_url, "dbx_workspace_conf", reference, norm_conf)
            raw["workspace_conf"] = conf_obj
            raw["sources"].append(conf_receipt)

            clusters, cl_receipt = read_dbx_pages(
                dbx, dbx.origin + "/api/2.0/clusters/list", "dbx_clusters", reference, "clusters",
                lambda item: normalize_cluster(item, "dbx_clusters", reference, config),
            )
            raw["inventory"]["clusters"] = clusters
            raw["sources"].append(cl_receipt)

            pools, pool_receipt = read_dbx_pages(
                dbx, dbx.origin + "/api/2.0/instance-pools/list", "dbx_instance_pools", reference, "instance_pools",
                lambda item: normalize_pool(item, "dbx_instance_pools", reference, config),
            )
            raw["inventory"]["instance_pools"] = pools
            raw["sources"].append(pool_receipt)

            policies, pol_receipt = read_dbx_pages(
                dbx, dbx.origin + "/api/2.0/policies/clusters/list", "dbx_cluster_policies", reference, "policies",
                lambda item: normalize_policy(item, "dbx_cluster_policies", reference, config),
            )
            raw["inventory"]["cluster_policies"] = policies
            raw["sources"].append(pol_receipt)

            jobs, job_receipt = read_dbx_pages(
                dbx, dbx.origin + "/api/2.1/jobs/list", "dbx_jobs", reference, "jobs",
                lambda item: normalize_job(item, "dbx_jobs", reference, config),
                base_params={"expand_tasks": "true", "limit": "25"},
            )
            job_detail_count = 0
            for idx, job_row in enumerate(jobs):
                if not job_row.get("tasks_incomplete"):
                    continue
                if job_detail_count >= MAX_DETAIL_GETS:
                    raw["sources"].append(source_receipt(
                        "dbx_job_details_cap", reference, "partial",
                        "Job detail GET bound reached; remaining truncated jobs keep tasks_incomplete=True.",
                        records=job_detail_count,
                    ))
                    break
                job_detail_count += 1
                jsid = "dbx_job_detail_" + str(job_detail_count) + "_" + hashlib.sha256(job_row["id"].encode("utf-8")).hexdigest()[:8]
                jurl = dbx.origin + "/api/2.1/jobs/get?" + urlencode({"job_id": job_row["id"]})
                full_job, j_rec = read_one(
                    dbx, jurl, jsid, reference,
                    lambda item, s=jsid: normalize_job(item, s, reference, config, from_detail=True),
                )
                raw["sources"].append(j_rec)
                if full_job is not None:
                    jobs[idx] = full_job
            raw["inventory"]["jobs"] = jobs
            raw["sources"].append(job_receipt)

            pipelines, pipe_receipt = read_dbx_pages(
                dbx, dbx.origin + "/api/2.0/pipelines", "dbx_pipelines", reference, "statuses",
                lambda item: normalize_pipeline(item, "dbx_pipelines", reference, config),
                base_params={"max_results": "50"},
            )
            pipe_detail_count = 0
            for idx, pipe_row in enumerate(pipelines):
                if pipe_row.get("detail_collected"):
                    continue
                if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", pipe_row["id"]):
                    raise EvidenceError("invalid_record", "Pipeline ID has unsafe syntax for detail path.", "dbx_pipelines")
                if pipe_detail_count >= MAX_DETAIL_GETS:
                    raw["sources"].append(source_receipt(
                        "dbx_pipeline_details_cap", reference, "partial",
                        "Pipeline detail GET bound reached; remaining pipelines keep detail_collected=False.",
                        records=pipe_detail_count,
                    ))
                    break
                pipe_detail_count += 1
                psid = "dbx_pipeline_detail_" + str(pipe_detail_count) + "_" + hashlib.sha256(pipe_row["id"].encode("utf-8")).hexdigest()[:8]
                purl = dbx.origin + "/api/2.0/pipelines/" + quote(pipe_row["id"], safe="")
                full_pipe, p_rec = read_one(
                    dbx, purl, psid, reference,
                    lambda item, p=pipe_row, s=psid: normalize_pipeline(p, p["source_id"], reference, config, detail=item, detail_source_id=s),
                )
                raw["sources"].append(p_rec)
                if full_pipe is not None:
                    pipelines[idx] = full_pipe
            raw["inventory"]["pipelines"] = pipelines
            raw["sources"].append(pipe_receipt)

            warehouses, wh_receipt = read_dbx_pages(
                dbx, dbx.origin + "/api/2.0/sql/warehouses", "dbx_sql_warehouses", reference, "warehouses",
                lambda item: normalize_warehouse(item, "dbx_sql_warehouses", reference, config),
            )
            raw["inventory"]["sql_warehouses"] = warehouses
            raw["sources"].append(wh_receipt)

            scopes, scope_receipt = read_dbx_pages(
                dbx, dbx.origin + "/api/2.0/secrets/scopes/list", "dbx_secret_scopes", reference, "scopes",
                lambda item: normalize_secret_scope(item, "dbx_secret_scopes", reference, config),
            )
            raw["inventory"]["secret_scopes"] = scopes
            raw["sources"].append(scope_receipt)
            for sc in scopes:
                if sc.get("keyvault_resource_id"):
                    queue_related(sc["keyvault_resource_id"], {"type": "direct_reference", "source_id": "dbx_secret_scopes", "resource_id": workspace["id"], "field": "keyvault_metadata.resource_id"})

            scripts, script_receipt = read_dbx_pages(
                dbx, dbx.origin + "/api/2.0/global-init-scripts", "dbx_init_scripts", reference, "scripts",
                lambda item: normalize_init_script(item, "dbx_init_scripts", reference, config),
            )
            raw["inventory"]["global_init_scripts"] = scripts
            raw["sources"].append(script_receipt)
        else:
            for sid in ("dbx_workspace_conf", "dbx_clusters", "dbx_instance_pools", "dbx_cluster_policies", "dbx_jobs", "dbx_pipelines", "dbx_sql_warehouses", "dbx_secret_scopes", "dbx_init_scripts"):
                raw["sources"].append(source_receipt(sid, reference, "not_configured", "Workspace REST API collection is disabled in configuration; no empty-workload inference."))

        if config["unity_catalog_enabled"] and config["workspace_api_enabled"]:
            dbx_uc = HttpReader(identity, "https://" + config["workspace_host"], "databricks")
            metastore, ms_receipt = read_one(
                dbx_uc, dbx_uc.origin + "/api/2.1/unity-catalog/metastore_summary", "uc_metastore_summary", reference,
                lambda item: normalize_metastore(item, "uc_metastore_summary", reference, config),
            )
            raw["inventory"]["uc_metastore"] = metastore
            raw["sources"].append(ms_receipt)

            catalogs, cat_receipt = read_dbx_pages(
                dbx_uc, dbx_uc.origin + "/api/2.1/unity-catalog/catalogs", "uc_catalogs", reference, "catalogs",
                lambda item: normalize_catalog(item, "uc_catalogs", reference, config),
                base_params={"include_browse": "true"},
            )
            raw["inventory"]["uc_catalogs"] = catalogs
            raw["sources"].append(cat_receipt)

            all_schemas = []
            schema_receipt = source_receipt("uc_schemas", reference, status="complete" if cat_receipt["status"] == "complete" else cat_receipt["status"], note="Unity Catalog schemas per non-system catalog.")
            if cat_receipt["status"] == "complete":
                for cat in catalogs:
                    if cat["name"].lower() in SYSTEM_CATALOGS:
                        continue
                    rows, s_rec = read_dbx_pages(
                        dbx_uc, dbx_uc.origin + "/api/2.1/unity-catalog/schemas", "uc_schemas", reference, "schemas",
                        lambda item: normalize_schema(item, "uc_schemas", reference, config),
                        base_params={"catalog_name": cat["name"], "include_browse": "true"},
                    )
                    all_schemas.extend(rows)
                    schema_receipt["pages"] += s_rec["pages"]
                    schema_receipt["records"] = len(all_schemas)
                    if s_rec["status"] != "complete":
                        schema_receipt["status"] = "partial" if all_schemas else s_rec["status"]
                        schema_receipt["errors"].extend(s_rec["errors"])
            raw["inventory"]["uc_schemas"] = all_schemas
            raw["sources"].append(schema_receipt)

            creds, cred_receipt = read_dbx_pages(
                dbx_uc, dbx_uc.origin + "/api/2.1/unity-catalog/storage-credentials", "uc_storage_credentials", reference, "storage_credentials",
                lambda item: normalize_storage_credential(item, "uc_storage_credentials", reference, config),
            )
            raw["inventory"]["uc_storage_credentials"] = creds
            raw["sources"].append(cred_receipt)
            for cr in creds:
                if cr.get("access_connector_id"):
                    queue_related(cr["access_connector_id"], {"type": "direct_reference", "source_id": "uc_storage_credentials", "resource_id": workspace["id"], "field": "azure_managed_identity.access_connector_id"})
                if cr.get("managed_identity_id"):
                    queue_related(cr["managed_identity_id"], {"type": "direct_reference", "source_id": "uc_storage_credentials", "resource_id": workspace["id"], "field": "azure_managed_identity.managed_identity_id"})

            ext_locs, ext_receipt = read_dbx_pages(
                dbx_uc, dbx_uc.origin + "/api/2.1/unity-catalog/external-locations", "uc_external_locations", reference, "external_locations",
                lambda item: normalize_external_location(item, "uc_external_locations", reference, config),
                base_params={"include_browse": "true"},
            )
            raw["inventory"]["uc_external_locations"] = ext_locs
            raw["sources"].append(ext_receipt)

            conns, conn_receipt = read_dbx_pages(
                dbx_uc, dbx_uc.origin + "/api/2.1/unity-catalog/connections", "uc_connections", reference, "connections",
                lambda item: normalize_connection(item, "uc_connections", reference, config),
            )
            raw["inventory"]["uc_connections"] = conns
            raw["sources"].append(conn_receipt)
        else:
            for sid in ("uc_metastore_summary", "uc_catalogs", "uc_schemas", "uc_storage_credentials", "uc_external_locations", "uc_connections"):
                raw["sources"].append(source_receipt(sid, reference, "not_configured", "Unity Catalog REST collection is disabled in configuration; no governance state is inferred."))

        raw["sources"].append(source_receipt(
            "uc_system_lineage",
            reference,
            "not_configured",
            "Runtime table/column lineage (system.access.table_lineage, system.access.column_lineage) and DBU billing (system.billing.usage) require SQL Warehouse query execution and are never auto-started by this control-plane collector.",
        ))

        read_queued_related()
        if related_cap_omitted:
            raw["sources"].append(source_receipt(
                "arm_related_cap",
                reference,
                "partial",
                "Related ARM resource queue reached MAX_RELATED_RESOURCES=" + str(MAX_RELATED_RESOURCES) + "; additional referenced resources were omitted and remain UNKNOWN.",
                records=len(seen_related),
                omitted_count=len(related_cap_omitted),
                omitted_resource_ids=[item["resource_id"] for item in related_cap_omitted[:50]],
                errors=[{
                    "code": "related_resource_cap_reached",
                    "message": "MAX_RELATED_RESOURCES cap reached; omitted resources are not assumed healthy.",
                    "source_id": "arm_related_cap",
                    "http_status": None,
                }],
            ))
        raw["inventory"]["related_resources"] = related

        advisor_source = source_receipt("arm_advisor", reference, "not_configured", "Cached recommendations only; no generateRecommendations action.")
        if config["advisor_enabled"]:
            adv_url = ARM_ORIGIN + "/subscriptions/" + SUBSCRIPTION_ID + "/providers/Microsoft.Advisor/recommendations?" + urlencode({
                "api-version": "2025-01-01", "$filter": "ResourceId eq '" + config["id"] + "'", "$top": "100",
            })
            def advisor_row(item):
                advisory_id = text(item.get("id"), "arm_advisor", 2048)
                if not advisory_id or not advisory_id.lower().startswith("/subscriptions/" + SUBSCRIPTION_ID.lower() + "/"):
                    raise EvidenceError("scope_mismatch", "Advisor ID changed subscription scope.", "arm_advisor")
                target = pick(item, "properties", "resourceMetadata", "resourceId")
                if not isinstance(target, str) or target.lower() != config["id"].lower():
                    raise EvidenceError("scope_mismatch", "Advisor returned a resource outside the exact workspace filter.", "arm_advisor")
                return {
                    "id": advisory_id,
                    "resource_id": config["id"],
                    "name": text(item.get("name"), "arm_advisor", 256),
                    "target_resource_id": target,
                    "category": text(pick(item, "properties", "category"), "arm_advisor", 64),
                    "impact": text(pick(item, "properties", "impact"), "arm_advisor", 64),
                    "last_updated": text(pick(item, "properties", "lastUpdated"), "arm_advisor", 64),
                    "problem": text(pick(item, "properties", "shortDescription", "problem"), "arm_advisor", 1024),
                    "solution": text(pick(item, "properties", "shortDescription", "solution"), "arm_advisor", 1024),
                    "workspace_name": config["name"],
                    "workspace_id": config["id"],
                    "source_id": "arm_advisor",
                    "observed_at": reference,
                }
            raw["advisor"], advisor_source = read_arm_pages(arm, adv_url, "arm_advisor", reference, advisor_row)
        raw["sources"].append(advisor_source)

        raw["cost_rows"], cost_source = collect_cost(arm, config, reference, related, workspace)
        raw["sources"].append(cost_source)
        if workspace_arm_error is not None:
            plane2_ok = any(
                s["id"].startswith(("dbx_", "uc_")) and s["id"] != "uc_system_lineage" and s["status"] == "complete"
                for s in raw["sources"]
            )
            if not plane2_ok:
                raise EvidenceError(workspace_arm_error["code"], "The approved primary Databricks workspace could not be read; no synthetic/empty live report.", "arm_workspace", workspace_arm_error["http_status"])
        return raw
    finally:
        identity.close()


def collect_cost(reader, config, reference, related, workspace=None):
    ids = config["approved_cost_resource_ids"]
    declared = datetime.fromisoformat(reference.replace("Z", "+00:00"))
    monthly = config["cost_timeframe"] == "month_to_date"
    start_time = declared.replace(day=1, hour=0, minute=0, second=0, microsecond=0) if monthly else declared - timedelta(days=30)
    start = start_time.isoformat().replace("+00:00", "Z")
    mode = config["cost_scope"]
    receipt = source_receipt(
        "azure_cost", reference, "not_configured",
        "No approved billing scope; no job/cluster DBU billing inference without system.billing.usage.",
        window={"start": start, "end": reference},
        timeframe="MonthToDate" if monthly else "Custom",
        granularity="None" if monthly else "Daily",
        cost_type="ActualCost",
        unit="billing_currency",
        pagination_complete=False,
    )
    if mode == "disabled":
        return [], receipt
    scope = "/subscriptions/" + SUBSCRIPTION_ID
    managed_rg = pick(workspace, "managed_resource_group")
    if mode == "managed_resource_group":
        if not isinstance(managed_rg, str) or not re.fullmatch(r"[A-Za-z0-9_.()-]{1,90}", managed_rg):
            receipt.update(status="error", errors=[EvidenceError("unverified_cost_scope", "Billing managedResourceGroup must come from the exact observed ARM workspace.", "azure_cost").public()])
            return [], receipt
        scope += "/resourceGroups/" + managed_rg
        receipt["association"] = {"type": "managed_resource_group_billing_context", "source_id": "arm_workspace", "managed_resource_group": managed_rg}
    else:
        observed_ids = {row["resource_id"].lower() for row in related} | {config["id"].lower()}
        if not ids or any(value.lower() not in observed_ids for value in ids):
            receipt.update(status="error", errors=[EvidenceError("unverified_cost_scope", "Fixed cost IDs must also be observed in the collected fixed inventory.", "azure_cost").public()])
            return [], receipt
        receipt["association"] = {"type": "approved_observed_resource_ids", "source_id": "configuration"}
    url = ARM_ORIGIN + scope + "/providers/Microsoft.CostManagement/query?api-version=2023-11-01"
    receipt.update(scope=scope, read_signature="POST " + url)
    reader.allow(url, "POST")
    body = {
        "type": "ActualCost",
        "timeframe": "MonthToDate" if monthly else "Custom",
        "dataset": {
            "granularity": "None" if monthly else "Daily",
            "aggregation": {"totalCost": {"name": "PreTaxCost", "function": "Sum"}},
            "grouping": [{"type": "Dimension", "name": "ResourceId"}],
        },
    }
    if not monthly:
        body["timePeriod"] = {"from": start, "to": reference}
    if mode == "resource_ids":
        body["dataset"]["filter"] = {"dimensions": {"name": "ResourceId", "operator": "In", "values": ids}}
    rows, seen = [], set()
    current = url
    try:
        for page_number in range(MAX_PAGES):
            if current in seen:
                raise EvidenceError("pagination_loop", "Cost query repeated a continuation.", "azure_cost")
            seen.add(current)
            payload = reader.request("POST", current, "azure_cost", body=body, allow_empty=True)
            receipt["pages"] = page_number + 1
            if not payload:
                receipt.update(status="complete", pagination_complete=True, records=len(rows), empty_http_204=True)
                return rows, receipt
            props = obj(payload.get("properties"), "azure_cost")
            columns = array(props.get("columns"), "azure_cost")
            names = [text(item.get("name"), "azure_cost", 128) for item in columns]
            required = {"ResourceId", "Currency"} | (set() if monthly else {"UsageDate"})
            if len(names) != len(set(names)) or not required <= set(names) or not ("PreTaxCost" in names or "Cost" in names):
                raise EvidenceError("invalid_cost_shape", "Required cost columns are absent or repeated.", "azure_cost")
            values = props.get("rows")
            if not isinstance(values, list) or len(rows) + len(values) > MAX_ROWS:
                raise EvidenceError("row_cap", "Cost rows are invalid or exceeded the safety bound.", "azure_cost")
            for value in values:
                if not isinstance(value, list) or len(value) != len(names):
                    raise EvidenceError("invalid_cost_shape", "Cost row/column lengths differ.", "azure_cost")
                record = dict(zip(names, value))
                resource_id = arm_id(record["ResourceId"], SUBSCRIPTION_ID)
                currency = text(record["Currency"], "azure_cost", 8)
                if not currency or not re.fullmatch(r"[A-Z]{3}", currency):
                    raise EvidenceError("invalid_currency", "Cost currency is not an observed ISO currency code.", "azure_cost")
                date = str(record["UsageDate"]) if record.get("UsageDate") is not None else None
                amount = number(record.get("PreTaxCost", record.get("Cost")), "azure_cost")
                if amount is None:
                    raise EvidenceError("invalid_cost_amount", "Cost amount is absent; it is not zero.", "azure_cost")
                rows.append({
                    "resource_id": resource_id, "usage_date": date, "amount": amount,
                    "currency": currency, "source_id": "azure_cost", "observed_at": reference,
                    "workspace_name": config["name"], "workspace_id": config["id"],
                    "window": receipt["window"], "association": receipt["association"],
                    "basis": "ActualCost/PreTaxCost in exact approved ARM scope; not per-job or per-cluster DBU attribution.",
                })
            receipt["records"] = len(rows)
            link = props.get("nextLink")
            if not link:
                receipt.update(status="complete", pagination_complete=True)
                return rows, receipt
            current = next_arm_link(link, url)
        raise EvidenceError("page_cap", "Cost query page safety cap reached.", "azure_cost")
    except (EvidenceError, ValueError) as exc:
        error = exc if isinstance(exc, EvidenceError) else EvidenceError("invalid_cost_date", "Cost date is not valid.", "azure_cost")
        receipt.update(status="partial" if rows else "denied" if error.http_status in (401, 403) else "error", records=len(rows), errors=[error.public()])
        return rows, receipt


def dependencies_for(raw, reference, provenance):
    ws, inv = raw["workspace"], raw["inventory"]
    scope = {
        "workspace_id": ws["id"],
        "workspace_name": ws["workspace_name"],
        "provenance": provenance,
        "observed_at": reference,
    }
    nodes, edges, unknowns, broken_refs, unverified_refs = {}, {}, [], [], []
    arm_map, cluster_map, pool_map, policy_map, job_map, pipe_map, wh_map = {}, {}, {}, {}, {}, {}, {}
    cred_map, cat_map, schema_map, storage_by_name, kv_by_host = {}, {}, {}, {}, {}
    source_status_by_id = {s["id"]: s["status"] for s in raw["sources"]}

    def add_unknown(code, layer, kind, message, source_ids, resource_id=None, workload_name=""):
        uid = "unknown-" + hashlib.sha256((ws["id"].lower() + "|" + code + "|" + str(resource_id or "") + "|" + workload_name).encode("utf-8")).hexdigest()[:24]
        unknowns.append({
            **scope, "id": uid, "record_type": "unknown", "classification": "UNKNOWN",
            "layer": layer, "kind": kind, "code": code, "message": message,
            "source_ids": source_ids, "resource_id": resource_id or ws["id"],
            "workload_name": workload_name, "status": "not_evaluated",
        })

    def record_unresolved_ref(source_object, kind, target_id, target_source_id, layer, intra_object=False):
        if intra_object:
            broken_refs.append({
                "source_object": source_object,
                "kind": kind,
                "target_id": target_id,
                "target_source_id": target_source_id,
                "qualification": "confirmed_intra_object_missing",
            })
            return
        t_status = source_status_by_id.get(target_source_id, "not_configured")
        if t_status != "complete":
            add_unknown(
                "unresolved_target_source_incomplete_" + kind,
                layer,
                kind,
                source_object + " references " + str(target_id) + ", but target source " + target_source_id + " is " + t_status + "; reference remains UNKNOWN.",
                [target_source_id],
                workload_name=source_object,
            )
            unverified_refs.append({
                "source_object": source_object,
                "kind": kind,
                "target_id": target_id,
                "target_source_id": target_source_id,
                "qualification": "target_source_" + t_status,
            })
            return
        add_unknown(
            "unresolved_cross_object_reference_" + kind,
            layer,
            kind,
            source_object + " references " + str(target_id) + ", which was not returned in " + target_source_id + ". Because Databricks list APIs are permission-filtered by object ACLs, absence may reflect ACL visibility or a deleted object and remains UNKNOWN.",
            [target_source_id],
            workload_name=source_object,
        )
        unverified_refs.append({
            "source_object": source_object,
            "kind": kind,
            "target_id": target_id,
            "target_source_id": target_source_id,
            "qualification": "permission_filtered_absence_or_deleted_target",
        })

    def add_node(native_key, kind, layer, label, source_id, evidence, resource_id=None, classification="OBSERVED", workload_name=""):
        nid = "node-" + hashlib.sha256((ws["id"].lower() + "|" + kind + "|" + str(native_key)).encode("utf-8")).hexdigest()[:24]
        node = {
            **scope, "id": nid, "record_type": "node", "classification": classification,
            "layer": layer, "kind": kind, "label": label, "name": label,
            "workload_name": workload_name or label, "resource_id": resource_id or ws["id"],
            "source_id": source_id, "evidence": evidence,
        }
        nodes[nid] = node
        return nid

    def add_edge(start, end, relation, layer, classification, source_ids, join_fields, evidence, workload_name=""):
        if not start or not end:
            return
        eid = "edge-" + hashlib.sha256((start + "|" + relation + "|" + end + "|" + classification).encode("utf-8")).hexdigest()[:24]
        edges.setdefault(eid, {
            **scope, "id": eid, "record_type": "edge", "classification": classification,
            "layer": layer, "from": start, "to": end, "relation": relation,
            "source_ids": list(dict.fromkeys(source_ids)), "join_fields": join_fields,
            "evidence": evidence, "workload_name": workload_name,
        })

    root = add_node(ws["id"].lower(), "databricks_workspace", "control_plane", ws["name"], "arm_workspace", {
        "arm_id": ws["id"], "workspace_url": ws["workspace_url"], "sku": ws["sku_name"],
        "auth_mode": ws["auth_mode"], "cross_tenant": ws["cross_tenant"],
        "enable_no_public_ip": ws["enable_no_public_ip"], "public_network_access": ws["public_network_access"],
    }, ws["id"])
    arm_map[ws["id"].lower()] = root

    if ws.get("managed_resource_group_id"):
        mrg_node = add_node(
            ws["managed_resource_group_id"].lower(), "managed_resource_group", "control_plane",
            ws.get("managed_resource_group") or ws["managed_resource_group_id"], "arm_workspace",
            {"managed_resource_group_id": ws["managed_resource_group_id"]}, ws["managed_resource_group_id"],
        )
        add_edge(root, mrg_node, "manages_resource_group", "control_plane", "OBSERVED", ["arm_workspace"], ["properties.managedResourceGroupId"], {"managed_resource_group_id": ws["managed_resource_group_id"]})

    for out_ep in inv.get("outbound_endpoints", []):
        ep_node = add_node(
            out_ep["id"], "outbound_dependency_category", "control_plane", out_ep["category"],
            out_ep["source_id"], {"category": out_ep["category"], "endpoints": out_ep["endpoints"]}, ws["id"],
        )
        add_edge(root, ep_node, "requires_outbound_control_plane_dependency", "control_plane", "OBSERVED", ["arm_workspace", out_ep["source_id"]], ["outboundNetworkDependenciesEndpoints.category"], {"category": out_ep["category"]})

    for res in inv.get("related_resources", []):
        r_node = add_node(
            res["id"].lower(), res["resource_kind"], "associated_resource", res["name"] or res["id"],
            res["source_id"], {"arm_id": res["id"], "association": res["association"], "configuration": res.get("configuration", {})},
            res["id"],
        )
        arm_map[res["id"].lower()] = r_node
        if res["resource_kind"] == "microsoft.storage/storageaccounts" and res.get("name"):
            storage_by_name[res["name"].lower()] = r_node
        if res["resource_kind"] == "microsoft.keyvault/vaults" and res.get("vault_uri"):
            host = extract_vault_host(res["vault_uri"])
            if host:
                kv_by_host[host] = r_node

    if ws.get("custom_virtual_network_id"):
        vnet_key = arm_map.get(ws["custom_virtual_network_id"].lower())
        if vnet_key:
            add_edge(root, vnet_key, "injected_into_vnet", "associated_resource", "OBSERVED", ["arm_workspace"], ["parameters.customVirtualNetworkId"], {"vnet_id": ws["custom_virtual_network_id"]})
        for sub_field, rel in (("custom_public_subnet_name", "uses_host_public_subnet"), ("custom_private_subnet_name", "uses_container_private_subnet")):
            if ws.get(sub_field):
                sub_id = (ws["custom_virtual_network_id"] + "/subnets/" + ws[sub_field]).lower()
                if sub_id in arm_map:
                    add_edge(root, arm_map[sub_id], rel, "associated_resource", "OBSERVED", ["arm_workspace"], ["parameters." + sub_field], {"subnet_id": sub_id})

    ac_id = pick(ws, "access_connector", "id")
    if ac_id and ac_id.lower() in arm_map:
        add_edge(root, arm_map[ac_id.lower()], "uses_access_connector", "associated_resource", "OBSERVED", ["arm_workspace"], ["properties.accessConnector.id"], {"access_connector_id": ac_id})

    if ws.get("dbfs_storage_account_name"):
        dbfs_name = ws["dbfs_storage_account_name"].lower()
        if dbfs_name in storage_by_name:
            add_edge(root, storage_by_name[dbfs_name], "uses_dbfs_root_storage", "associated_resource", "OBSERVED", ["arm_workspace"], ["parameters.storageAccountName"], {"storage_account": ws["dbfs_storage_account_name"]})
        else:
            inferred_dbfs = add_node(
                "dbfs_storage:" + dbfs_name, "external_storage_target", "associated_resource",
                ws["dbfs_storage_account_name"], "arm_workspace",
                {"storage_account_name": ws["dbfs_storage_account_name"], "arm_detail_collected": False},
                ws["id"], classification="INFERRED",
            )
            add_edge(root, inferred_dbfs, "inferred_dbfs_root_storage_name", "associated_resource", "INFERRED", ["arm_workspace"], ["parameters.storageAccountName"], {"storage_account_name": ws["dbfs_storage_account_name"]})

    for cmk_field in ("managed_services_vault_uri", "managed_disk_vault_uri"):
        v_uri = pick(ws, "cmk", cmk_field)
        host = extract_vault_host(v_uri) if v_uri else None
        if host:
            if host in kv_by_host:
                add_edge(root, kv_by_host[host], "uses_cmk_key_vault", "associated_resource", "OBSERVED", ["arm_workspace"], ["encryption." + cmk_field], {"vault_uri": v_uri})
            else:
                inf_kv = add_node("cmk_vault:" + host, "external_key_vault_target", "associated_resource", host, "arm_workspace", {"vault_uri": v_uri, "arm_detail_collected": False}, ws["id"], classification="INFERRED")
                add_edge(root, inf_kv, "inferred_cmk_key_vault_uri", "associated_resource", "INFERRED", ["arm_workspace"], ["encryption." + cmk_field], {"vault_uri": v_uri})

    for res in inv.get("related_resources", []):
        r_key = arm_map[res["id"].lower()]
        for child_id, field in referenced_resource_ids(res):
            relation_name = "associated_route_table" if field == "route_table_id" else "associated_nsg" if field == "nsg_id" else "references_arm_resource"
            if child_id.lower() in arm_map:
                add_edge(r_key, arm_map[child_id.lower()], relation_name, "associated_resource", "OBSERVED", [res["source_id"]], [field], {"target_id": child_id})
            else:
                inf_arm = add_node("arm_ref:" + child_id.lower(), "external_arm_target", "associated_resource", child_id.split("/")[-1], res["source_id"], {"target_id": child_id, "field": field, "arm_detail_collected": False}, child_id, classification="INFERRED")
                add_edge(r_key, inf_arm, "inferred_" + relation_name, "associated_resource", "INFERRED", [res["source_id"]], [field], {"target_id": child_id})

    for pool in inv.get("instance_pools", []):
        p_node = add_node(pool["id"], "instance_pool", "compute", pool["name"], pool["source_id"], pool, ws["id"], workload_name=pool["name"])
        pool_map[pool["id"]] = p_node
        add_edge(root, p_node, "contains_instance_pool", "compute", "OBSERVED", [pool["source_id"]], ["instance_pool_id"], {"instance_pool_id": pool["id"]}, workload_name=pool["name"])

    for pol in inv.get("cluster_policies", []):
        pol_node = add_node(pol["id"], "cluster_policy", "compute", pol["name"], pol["source_id"], pol, ws["id"], workload_name=pol["name"])
        policy_map[pol["id"]] = pol_node
        add_edge(root, pol_node, "contains_cluster_policy", "compute", "OBSERVED", [pol["source_id"]], ["policy_id"], {"policy_id": pol["id"]}, workload_name=pol["name"])

    for cl in inv.get("clusters", []):
        c_kind = "job_cluster" if cl["cluster_source"] == "JOB" else "all_purpose_cluster"
        c_node = add_node(cl["id"], c_kind, "compute", cl["name"], cl["source_id"], cl, ws["id"], workload_name=cl["name"])
        cluster_map[cl["id"]] = c_node
        add_edge(root, c_node, "contains_cluster", "compute", "OBSERVED", [cl["source_id"]], ["cluster_id"], {"cluster_id": cl["id"]}, workload_name=cl["name"])
        if cl.get("policy_id"):
            if cl["policy_id"] in policy_map:
                add_edge(c_node, policy_map[cl["policy_id"]], "governed_by_policy", "compute", "OBSERVED", [cl["source_id"], "dbx_cluster_policies"], ["policy_id"], {"policy_id": cl["policy_id"]}, workload_name=cl["name"])
            else:
                record_unresolved_ref(cl["name"], "cluster_policy_missing", cl["policy_id"], "dbx_cluster_policies", "compute")
        for pool_field in ("instance_pool_id", "driver_instance_pool_id"):
            if cl.get(pool_field):
                if cl[pool_field] in pool_map:
                    add_edge(c_node, pool_map[cl[pool_field]], "backed_by_instance_pool", "compute", "OBSERVED", [cl["source_id"], "dbx_instance_pools"], [pool_field], {pool_field: cl[pool_field]}, workload_name=cl["name"])
                else:
                    record_unresolved_ref(cl["name"], "instance_pool_missing", cl[pool_field], "dbx_instance_pools", "compute")

    for wh in inv.get("sql_warehouses", []):
        w_node = add_node(wh["id"], "sql_warehouse", "compute", wh["name"], wh["source_id"], wh, ws["id"], workload_name=wh["name"])
        wh_map[wh["id"]] = w_node
        add_edge(root, w_node, "contains_sql_warehouse", "compute", "OBSERVED", [wh["source_id"]], ["warehouse_id"], {"warehouse_id": wh["id"]}, workload_name=wh["name"])

    for sc in inv.get("secret_scopes", []):
        sc_node = add_node(sc["name"], "secret_scope", "governance", sc["name"], sc["source_id"], sc, ws["id"], workload_name=sc["name"])
        add_edge(root, sc_node, "contains_secret_scope", "governance", "OBSERVED", [sc["source_id"]], ["name"], {"scope": sc["name"]}, workload_name=sc["name"])
        kv_rid = sc.get("keyvault_resource_id")
        kv_dns = extract_vault_host(sc.get("keyvault_dns_name")) if sc.get("keyvault_dns_name") else None
        if kv_rid and kv_rid.lower() in arm_map:
            add_edge(sc_node, arm_map[kv_rid.lower()], "backed_by_key_vault", "governance", "OBSERVED", [sc["source_id"], "arm_workspace"], ["keyvault_metadata.resource_id"], {"keyvault_resource_id": kv_rid}, workload_name=sc["name"])
        elif kv_dns and kv_dns in kv_by_host:
            add_edge(sc_node, kv_by_host[kv_dns], "backed_by_key_vault", "governance", "OBSERVED", [sc["source_id"]], ["keyvault_metadata.dns_name"], {"dns_name": sc["keyvault_dns_name"]}, workload_name=sc["name"])
        elif kv_rid or kv_dns:
            inf_kv = add_node("scope_kv:" + (kv_dns or kv_rid), "external_key_vault_target", "associated_resource", kv_dns or kv_rid, sc["source_id"], {"keyvault_resource_id": kv_rid, "dns_name": sc.get("keyvault_dns_name")}, ws["id"], classification="INFERRED", workload_name=sc["name"])
            add_edge(sc_node, inf_kv, "inferred_key_vault_reference", "governance", "INFERRED", [sc["source_id"]], ["keyvault_metadata"], {"keyvault_resource_id": kv_rid, "dns_name": sc.get("keyvault_dns_name")}, workload_name=sc["name"])

    ms = inv.get("uc_metastore")
    ms_node = None
    if ms:
        ms_node = add_node(ms["id"], "uc_metastore", "governance", ms["name"], ms["source_id"], ms, ws["id"], workload_name=ms["name"])
        add_edge(root, ms_node, "attached_to_uc_metastore", "governance", "OBSERVED", [ms["source_id"]], ["metastore_id"], {"metastore_id": ms["id"]}, workload_name=ms["name"])

    for cred in inv.get("uc_storage_credentials", []):
        cr_node = add_node(cred["name"], "uc_storage_credential", "governance", cred["name"], cred["source_id"], cred, ws["id"], workload_name=cred["name"])
        cred_map[cred["name"]] = cr_node
        add_edge(ms_node or root, cr_node, "defines_storage_credential", "governance", "OBSERVED", [cred["source_id"]], ["name"], {"credential_name": cred["name"]}, workload_name=cred["name"])
        if cred.get("access_connector_id"):
            ac_low = cred["access_connector_id"].lower()
            if ac_low in arm_map:
                add_edge(cr_node, arm_map[ac_low], "authenticates_via_access_connector", "governance", "OBSERVED", [cred["source_id"]], ["azure_managed_identity.access_connector_id"], {"access_connector_id": cred["access_connector_id"]}, workload_name=cred["name"])
            else:
                inf_ac = add_node("ac:" + ac_low, "external_access_connector_target", "associated_resource", cred["access_connector_id"].split("/")[-1], cred["source_id"], {"access_connector_id": cred["access_connector_id"]}, ws["id"], classification="INFERRED", workload_name=cred["name"])
                add_edge(cr_node, inf_ac, "inferred_access_connector_reference", "governance", "INFERRED", [cred["source_id"]], ["azure_managed_identity.access_connector_id"], {"access_connector_id": cred["access_connector_id"]}, workload_name=cred["name"])

    for loc in inv.get("uc_external_locations", []):
        loc_node = add_node(loc["name"], "uc_external_location", "governance", loc["name"], loc["source_id"], loc, ws["id"], workload_name=loc["name"])
        add_edge(ms_node or root, loc_node, "defines_external_location", "governance", "OBSERVED", [loc["source_id"]], ["name"], {"external_location": loc["name"]}, workload_name=loc["name"])
        if loc.get("credential_name"):
            if loc["credential_name"] in cred_map:
                add_edge(loc_node, cred_map[loc["credential_name"]], "uses_storage_credential", "governance", "OBSERVED", [loc["source_id"], "uc_storage_credentials"], ["credential_name"], {"credential_name": loc["credential_name"]}, workload_name=loc["name"])
            else:
                record_unresolved_ref(loc["name"], "storage_credential_missing", loc["credential_name"], "uc_storage_credentials", "governance")
        acct = extract_storage_account_from_uri(loc.get("url"))
        if acct:
            if acct in storage_by_name:
                add_edge(loc_node, storage_by_name[acct], "points_to_adls_storage_account", "governance", "OBSERVED", [loc["source_id"]], ["url"], {"url": loc["url"], "storage_account": acct}, workload_name=loc["name"])
            else:
                inf_st = add_node("adls:" + acct, "external_storage_target", "associated_resource", acct, loc["source_id"], {"url": loc["url"], "storage_account": acct, "arm_detail_collected": False}, ws["id"], classification="INFERRED", workload_name=loc["name"])
                add_edge(loc_node, inf_st, "inferred_adls_storage_uri_target", "governance", "INFERRED", [loc["source_id"]], ["url"], {"url": loc["url"], "storage_account": acct}, workload_name=loc["name"])

    for conn in inv.get("uc_connections", []):
        conn_node = add_node(conn["name"], "uc_connection", "governance", conn["name"], conn["source_id"], conn, ws["id"], workload_name=conn["name"])
        add_edge(ms_node or root, conn_node, "federates_external_connection", "governance", "OBSERVED", [conn["source_id"]], ["name", "connection_type"], {"connection_type": conn.get("connection_type"), "host": conn.get("host")}, workload_name=conn["name"])

    for cat in inv.get("uc_catalogs", []):
        cat_node = add_node(cat["name"], "uc_catalog", "governance", cat["name"], cat["source_id"], cat, ws["id"], workload_name=cat["name"])
        cat_map[cat["name"]] = cat_node
        add_edge(ms_node or root, cat_node, "contains_catalog", "governance", "OBSERVED", [cat["source_id"]], ["name"], {"catalog_name": cat["name"]}, workload_name=cat["name"])
        c_acct = extract_storage_account_from_uri(cat.get("storage_root") or cat.get("storage_location"))
        if c_acct:
            if c_acct in storage_by_name:
                add_edge(cat_node, storage_by_name[c_acct], "uses_catalog_managed_storage", "governance", "OBSERVED", [cat["source_id"]], ["storage_root"], {"storage_root": cat.get("storage_root") or cat.get("storage_location"), "storage_account": c_acct}, workload_name=cat["name"])
            else:
                inf_cst = add_node("adls:" + c_acct, "external_storage_target", "associated_resource", c_acct, cat["source_id"], {"url": cat.get("storage_root") or cat.get("storage_location"), "storage_account": c_acct, "arm_detail_collected": False}, ws["id"], classification="INFERRED", workload_name=cat["name"])
                add_edge(cat_node, inf_cst, "inferred_catalog_storage_uri_target", "governance", "INFERRED", [cat["source_id"]], ["storage_root"], {"storage_root": cat.get("storage_root") or cat.get("storage_location"), "storage_account": c_acct}, workload_name=cat["name"])
        if cat.get("connection_name"):
            conn_target = next((nodes[k] for k in nodes if nodes[k]["kind"] == "uc_connection" and nodes[k]["name"] == cat["connection_name"]), None)
            if conn_target:
                add_edge(cat_node, conn_target["id"], "uses_federated_connection", "governance", "OBSERVED", [cat["source_id"], "uc_connections"], ["connection_name"], {"connection_name": cat["connection_name"]}, workload_name=cat["name"])

    for sch in inv.get("uc_schemas", []):
        sch_node = add_node(sch["full_name"], "uc_schema", "governance", sch["full_name"], sch["source_id"], sch, ws["id"], workload_name=sch["full_name"])
        schema_map[sch["full_name"]] = sch_node
        if sch["catalog_name"] in cat_map:
            add_edge(cat_map[sch["catalog_name"]], sch_node, "contains_schema", "governance", "OBSERVED", [sch["source_id"], "uc_catalogs"], ["catalog_name"], {"full_name": sch["full_name"]}, workload_name=sch["full_name"])

    for pipe in inv.get("pipelines", []):
        p_node = add_node(pipe["id"], "dlt_pipeline", "orchestration", pipe["name"], pipe["source_id"], pipe, ws["id"], workload_name=pipe["name"])
        pipe_map[pipe["id"]] = p_node
        add_edge(root, p_node, "contains_pipeline", "orchestration", "OBSERVED", [pipe["source_id"]], ["pipeline_id"], {"pipeline_id": pipe["id"]}, workload_name=pipe["name"])
        if pipe.get("detail_collected") is False:
            add_unknown(
                "pipeline_spec_detail_unavailable_" + pipe["id"],
                "orchestration",
                "dlt_pipeline",
                "Pipeline " + pipe["name"] + " (" + pipe["id"] + ") list entry has no full spec (/api/2.0/pipelines/{id} unavailable or not collected); catalog, target schema, storage and cluster bindings remain UNKNOWN.",
                [pipe.get("detail_source_id") or pipe["source_id"]],
                workload_name=pipe["name"],
            )
            continue
        p_sources = list(dict.fromkeys([pipe["source_id"]] + ([pipe["detail_source_id"]] if pipe.get("detail_source_id") else [])))
        if pipe.get("catalog"):
            if pipe["catalog"] in cat_map:
                add_edge(p_node, cat_map[pipe["catalog"]], "publishes_to_catalog", "orchestration", "OBSERVED", p_sources + ["uc_catalogs"], ["catalog"], {"catalog": pipe["catalog"]}, workload_name=pipe["name"])
            if pipe.get("target"):
                full_target = pipe["catalog"] + "." + pipe["target"]
                if full_target in schema_map:
                    add_edge(p_node, schema_map[full_target], "publishes_to_schema", "orchestration", "OBSERVED", p_sources + ["uc_schemas"], ["catalog", "target"], {"schema": full_target}, workload_name=pipe["name"])
        p_acct = extract_storage_account_from_uri(pipe.get("storage"))
        if p_acct:
            if p_acct in storage_by_name:
                add_edge(p_node, storage_by_name[p_acct], "uses_pipeline_storage_account", "orchestration", "OBSERVED", p_sources, ["spec.storage"], {"storage": pipe["storage"], "storage_account": p_acct}, workload_name=pipe["name"])
            else:
                inf_pst = add_node("adls:" + p_acct, "external_storage_target", "associated_resource", p_acct, pipe["source_id"], {"url": pipe["storage"], "storage_account": p_acct, "arm_detail_collected": False}, ws["id"], classification="INFERRED", workload_name=pipe["name"])
                add_edge(p_node, inf_pst, "inferred_pipeline_storage_uri_target", "orchestration", "INFERRED", p_sources, ["spec.storage"], {"storage": pipe["storage"], "storage_account": p_acct}, workload_name=pipe["name"])
        for pcl in pipe.get("clusters", []):
            if pcl.get("policy_id"):
                if pcl["policy_id"] in policy_map:
                    add_edge(p_node, policy_map[pcl["policy_id"]], "governed_by_policy", "compute", "OBSERVED", p_sources + ["dbx_cluster_policies"], ["spec.clusters.policy_id"], {"policy_id": pcl["policy_id"]}, workload_name=pipe["name"])
                else:
                    record_unresolved_ref(pipe["name"], "pipeline_cluster_policy_missing", pcl["policy_id"], "dbx_cluster_policies", "compute")
            for pool_f in ("instance_pool_id", "driver_instance_pool_id"):
                if pcl.get(pool_f):
                    if pcl[pool_f] in pool_map:
                        add_edge(p_node, pool_map[pcl[pool_f]], "backed_by_instance_pool", "compute", "OBSERVED", p_sources + ["dbx_instance_pools"], ["spec.clusters." + pool_f], {pool_f: pcl[pool_f]}, workload_name=pipe["name"])
                    else:
                        record_unresolved_ref(pipe["name"], "pipeline_instance_pool_missing", pcl[pool_f], "dbx_instance_pools", "compute")

    for job in inv.get("jobs", []):
        j_node = add_node(job["id"], "job", "orchestration", job["name"], job["source_id"], job, ws["id"], workload_name=job["name"])
        job_map[job["id"]] = j_node
        add_edge(root, j_node, "contains_job", "orchestration", "OBSERVED", [job["source_id"]], ["job_id"], {"job_id": job["id"]}, workload_name=job["name"])

    for job in inv.get("jobs", []):
        j_node = job_map[job["id"]]
        job_incomplete = job.get("tasks_incomplete") is True
        if job_incomplete:
            add_unknown(
                "job_tasks_truncated_or_incomplete_" + job["id"],
                "orchestration",
                "job_dag",
                "Job " + job["name"] + " (" + job["id"] + ") task or job_cluster list was truncated or incomplete in jobs/list and full detail could not be resolved; intra-job DAG completeness remains UNKNOWN.",
                [job["source_id"]],
                workload_name=job["name"],
            )
        jc_nodes = {}
        for jc in job.get("job_clusters", []):
            jc_key = job["id"] + ":" + jc["job_cluster_key"]
            jc_node = add_node(jc_key, "job_cluster_spec", "compute", job["name"] + " / " + jc["job_cluster_key"], job["source_id"], jc, ws["id"], workload_name=job["name"])
            jc_nodes[jc["job_cluster_key"]] = jc_node
            add_edge(j_node, jc_node, "defines_job_cluster_spec", "orchestration", "OBSERVED", [job["source_id"]], ["job_clusters.job_cluster_key"], {"job_cluster_key": jc["job_cluster_key"]}, workload_name=job["name"])
            if jc.get("policy_id"):
                if jc["policy_id"] in policy_map:
                    add_edge(jc_node, policy_map[jc["policy_id"]], "governed_by_policy", "compute", "OBSERVED", [job["source_id"], "dbx_cluster_policies"], ["policy_id"], {"policy_id": jc["policy_id"]}, workload_name=job["name"])
                else:
                    record_unresolved_ref(job["name"], "job_cluster_policy_missing", jc["policy_id"], "dbx_cluster_policies", "compute")
            if jc.get("instance_pool_id"):
                if jc["instance_pool_id"] in pool_map:
                    add_edge(jc_node, pool_map[jc["instance_pool_id"]], "backed_by_instance_pool", "compute", "OBSERVED", [job["source_id"], "dbx_instance_pools"], ["instance_pool_id"], {"instance_pool_id": jc["instance_pool_id"]}, workload_name=job["name"])
                else:
                    record_unresolved_ref(job["name"], "job_cluster_pool_missing", jc["instance_pool_id"], "dbx_instance_pools", "compute")

        task_nodes = {}
        for task in job.get("tasks", []):
            t_id = job["id"] + ":" + task["task_key"]
            t_node = add_node(t_id, "job_task", "orchestration", job["name"] + " :: " + task["task_key"], job["source_id"], task, ws["id"], workload_name=job["name"])
            task_nodes[task["task_key"]] = t_node
            add_edge(j_node, t_node, "has_task", "orchestration", "OBSERVED", [job["source_id"]], ["tasks.task_key"], {"task_key": task["task_key"]}, workload_name=job["name"])
            if task.get("existing_cluster_id"):
                if task["existing_cluster_id"] in cluster_map:
                    add_edge(t_node, cluster_map[task["existing_cluster_id"]], "runs_on_all_purpose_cluster", "orchestration", "OBSERVED", [job["source_id"], "dbx_clusters"], ["existing_cluster_id"], {"existing_cluster_id": task["existing_cluster_id"]}, workload_name=job["name"])
                else:
                    record_unresolved_ref(job["name"] + "::" + task["task_key"], "existing_cluster_missing", task["existing_cluster_id"], "dbx_clusters", "orchestration")
            if task.get("job_cluster_key"):
                if task["job_cluster_key"] in jc_nodes:
                    add_edge(t_node, jc_nodes[task["job_cluster_key"]], "runs_on_job_cluster_spec", "orchestration", "OBSERVED", [job["source_id"]], ["job_cluster_key"], {"job_cluster_key": task["job_cluster_key"]}, workload_name=job["name"])
                elif not job_incomplete:
                    record_unresolved_ref(job["name"] + "::" + task["task_key"], "job_cluster_key_missing", task["job_cluster_key"], job["source_id"], "orchestration", intra_object=True)
            if task.get("pipeline_id"):
                if task["pipeline_id"] in pipe_map:
                    add_edge(t_node, pipe_map[task["pipeline_id"]], "triggers_dlt_pipeline", "orchestration", "OBSERVED", [job["source_id"], "dbx_pipelines"], ["pipeline_task.pipeline_id"], {"pipeline_id": task["pipeline_id"]}, workload_name=job["name"])
                else:
                    record_unresolved_ref(job["name"] + "::" + task["task_key"], "pipeline_missing", task["pipeline_id"], "dbx_pipelines", "orchestration")
            if task.get("warehouse_id"):
                if task["warehouse_id"] in wh_map:
                    add_edge(t_node, wh_map[task["warehouse_id"]], "executes_on_sql_warehouse", "orchestration", "OBSERVED", [job["source_id"], "dbx_sql_warehouses"], ["sql_task.warehouse_id"], {"warehouse_id": task["warehouse_id"]}, workload_name=job["name"])
                else:
                    record_unresolved_ref(job["name"] + "::" + task["task_key"], "sql_warehouse_missing", task["warehouse_id"], "dbx_sql_warehouses", "orchestration")
            if task.get("run_job_id"):
                if task["run_job_id"] in job_map:
                    add_edge(t_node, job_map[task["run_job_id"]], "triggers_downstream_job", "orchestration", "OBSERVED", [job["source_id"]], ["run_job_task.job_id"], {"run_job_id": task["run_job_id"]}, workload_name=job["name"])
                else:
                    record_unresolved_ref(job["name"] + "::" + task["task_key"], "downstream_job_missing", task["run_job_id"], "dbx_jobs", "orchestration")

        for task in job.get("tasks", []):
            t_node = task_nodes[task["task_key"]]
            for upstream_key in task.get("depends_on", []):
                if upstream_key in task_nodes:
                    add_edge(t_node, task_nodes[upstream_key], "depends_on_task", "orchestration", "OBSERVED", [job["source_id"]], ["tasks.depends_on"], {"task_key": task["task_key"], "depends_on": upstream_key}, workload_name=job["name"])
                elif not job_incomplete:
                    record_unresolved_ref(job["name"] + "::" + task["task_key"], "task_dependency_missing", upstream_key, job["source_id"], "orchestration", intra_object=True)

    add_unknown(
        "runtime_table_column_lineage_not_queried",
        "governance",
        "table_lineage",
        "Runtime table/column lineage (system.access.table_lineage, system.access.column_lineage) requires executing SQL queries on a running SQL Warehouse (billable DBU compute). Control-plane collection never starts compute or fabricates table lineage from notebook names.",
        ["uc_system_lineage"],
    )
    add_unknown(
        "notebook_code_internal_dependencies_not_executed",
        "orchestration",
        "notebook_code",
        "Dynamic paths, JDBC strings and library calls inside notebook/Python/JAR source code are not statically parsed or executed.",
        ["dbx_jobs"],
    )
    add_unknown(
        "effective_network_and_storage_acl_reachability_untested",
        "associated_resource",
        "network_reachability",
        "Observed VNet injection, NSG rules, Private Endpoints, Storage Credentials and External Locations confirm configuration references, not live data-plane packet flow or effective ACL evaluation.",
        ["arm_workspace", "uc_external_locations"],
    )
    for source in raw["sources"]:
        if source["status"] not in ("complete", "not_applicable") and source["id"] != "uc_system_lineage":
            add_unknown(
                "source_incomplete_" + source["id"],
                "control_plane",
                "source_blind_spot",
                source["id"] + " status=" + source["status"] + ": " + source["note"],
                [source["id"]],
                source.get("resource_id"),
            )

    edge_list = list(edges.values())
    node_list = list(nodes.values())
    return {
        "nodes": node_list,
        "edges": edge_list,
        "unknowns": unknowns,
        "broken_references": broken_refs,
        "unverified_references": unverified_refs,
        "summary_counts": {
            "nodes_total": len(node_list),
            "edges_total": len(edge_list),
            "edges_observed": sum(e["classification"] == "OBSERVED" for e in edge_list),
            "edges_inferred": sum(e["classification"] == "INFERRED" for e in edge_list),
            "unknowns_total": len(unknowns),
            "broken_references_total": len(broken_refs),
            "unverified_references_total": len(unverified_refs),
        },
    }


def outcome(status, reason, value=None, source_ids=None):
    return {"status": status, "reason": reason, "value": value or {}, "source_ids": source_ids or []}


def decision(value, reason, observed, sources=None):
    return outcome("not_evaluated" if value is None else "passed" if value else "failed", reason, observed, sources)


def source_complete(raw, *ids):
    sources = {source["id"]: source for source in raw["sources"]}
    return all(pick(sources.get(source_id), "status") == "complete" for source_id in ids)


def expected(raw, key):
    return raw.get("requirements", {}).get(key)


def conditional(value, requirement, reason, observed, sources=None):
    if requirement is False:
        return outcome("not_applicable", "El requisito confirmado no aplica. " + reason, observed, sources)
    if value is True:
        return decision(True, reason + " Configuración observada; no prueba eficacia en tiempo de ejecución.", observed, sources)
    if requirement is not True:
        return outcome("not_evaluated", "Falta requisito confirmado del propietario o control compensatorio. " + reason, observed, sources)
    return decision(value, reason + " Requisito confirmado por el propietario.", observed, sources)


def evaluate_workspace_rule(rule, raw, dep_graph):
    test, ws, inv = rule["test"], raw["workspace"], raw["inventory"]
    if test == "sku_premium":
        sku = (ws.get("sku_name") or ws.get("sku_tier") or "").lower()
        val = True if sku == "premium" else False if sku in ("standard", "trial") else None
        return conditional(val, expected(raw, "premium_required") if expected(raw, "premium_required") is not None else True,
                           "SKU ARM observada del workspace.", {"sku_name": ws.get("sku_name"), "sku_tier": ws.get("sku_tier")}, ["arm_workspace"])
    if test == "secure_cluster_connectivity":
        return decision(ws.get("enable_no_public_ip"), "Parámetro enableNoPublicIp observado en ARM.", {"enable_no_public_ip": ws.get("enable_no_public_ip")}, ["arm_workspace"])
    if test == "vnet_injection":
        vnet = ws.get("custom_virtual_network_id")
        vnet_val = True if vnet else (False if source_complete(raw, "arm_workspace") else None)
        return conditional(vnet_val, expected(raw, "vnet_injection_required") if expected(raw, "vnet_injection_required") is not None else True,
                           "Parámetro customVirtualNetworkId e inyección de subredes host/container.", {
                               "custom_virtual_network_id": vnet,
                               "custom_public_subnet_name": ws.get("custom_public_subnet_name"),
                               "custom_private_subnet_name": ws.get("custom_private_subnet_name"),
                           }, ["arm_workspace"])
    if test == "private_link_and_public_access":
        pna = ws.get("public_network_access")
        pes = ws.get("private_endpoint_connections", [])
        approved_pe = any(p.get("status") == "Approved" for p in pes)
        val = True if pna == "Disabled" or approved_pe else (False if pna == "Enabled" and not pes else None)
        return conditional(val, expected(raw, "private_link_required"), "Configuración publicNetworkAccess, requiredNsgRules y Private Endpoints.", {
            "public_network_access": pna, "required_nsg_rules": ws.get("required_nsg_rules"), "private_endpoint_connections": pes,
        }, ["arm_workspace"])
    if test == "access_connector_and_storage_firewall":
        ac = ws.get("access_connector", {})
        has_ac = bool(ac.get("id")) and ac.get("identity_type") in ("SystemAssigned", "UserAssigned", "SystemAssigned,UserAssigned")
        return decision(True if has_ac else False if source_complete(raw, "arm_workspace") else None,
                        "Access Connector vinculado al workspace para identidad administrada.", {
                            "access_connector": ac, "default_storage_firewall": ws.get("default_storage_firewall"),
                        }, ["arm_workspace"])
    if test == "customer_managed_keys":
        cmk = ws.get("cmk", {})
        has_cmk = cmk.get("managed_services_key_source") == "Microsoft.Keyvault" and cmk.get("managed_disk_key_source") == "Microsoft.Keyvault"
        return conditional(has_cmk, expected(raw, "cmk_required"), "Cifrado CMK de managedServices y managedDisk.", cmk, ["arm_workspace"])
    if test == "enhanced_security_compliance":
        esc = ws.get("enhanced_security_compliance", {})
        enabled = esc.get("enhanced_security_monitoring") == "Enabled" or esc.get("compliance_security_profile") == "Enabled"
        return conditional(enabled, expected(raw, "enhanced_security_required"), "Perfil enhancedSecurityCompliance observado.", esc, ["arm_workspace"])
    if test == "diagnostics":
        rows = raw.get("arm_diagnostics", [])
        enabled = any(log.get("enabled") is True for r in rows for log in r.get("logs", []))
        val = True if enabled else False if source_complete(raw, "arm_diagnostics") else None
        return decision(val, "Diagnostic settings habilitados en ARM; la ingesta efectiva requiere verificación separada.", {"diagnostic_settings": rows}, ["arm_diagnostics"])
    if test == "pat_token_governance":
        if not source_complete(raw, "dbx_workspace_conf") or not isinstance(raw.get("workspace_conf"), dict):
            return outcome("not_evaluated", "workspace-conf no disponible para revisar políticas de tokens PAT.", source_ids=["dbx_workspace_conf"])
        conf = raw["workspace_conf"]
        max_days = conf.get("maxTokenLifetimeDays")
        tokens_enabled = conf.get("enableTokensConfig")
        bounded = tokens_enabled == "false" or (max_days is not None and str(max_days).isdigit() and 0 < int(max_days) <= 90)
        return decision(bounded, "Gobernanza de tokens PAT (enableTokensConfig y maxTokenLifetimeDays <= 90 días).", conf, ["dbx_workspace_conf"])
    if test == "default_catalog_unity":
        dtype = ws.get("default_catalog_type")
        has_uc = bool(inv.get("uc_metastore"))
        val = True if dtype == "UnityCatalog" or has_uc else (False if dtype == "HiveMetastore" else None)
        return decision(val, "Catálogo predeterminado UnityCatalog o metastore adjunto observado.", {
            "default_catalog_type": dtype, "default_catalog_name": ws.get("default_catalog_name"),
            "uc_metastore_id": pick(inv.get("uc_metastore"), "id"),
        }, ["arm_workspace", "uc_metastore_summary"])
    if test == "global_init_scripts":
        if not source_complete(raw, "dbx_init_scripts"):
            return outcome("not_evaluated", "Lista de global init scripts no disponible.", source_ids=["dbx_init_scripts"])
        enabled = [s for s in inv.get("global_init_scripts", []) if s.get("enabled") is True]
        return decision(len(enabled) == 0, "Los global init scripts activos deben minimizarse y migrarse a políticas o volúmenes gobernados.", {
            "total_scripts": len(inv.get("global_init_scripts", [])), "enabled_scripts": [s["name"] for s in enabled],
        }, ["dbx_init_scripts"])
    if test == "advisor":
        return decision(True if source_complete(raw, "arm_advisor") else None,
                        "Recomendaciones cacheadas de Azure Advisor leídas para el workspace.", {"recommendations_count": len(raw.get("advisor", []))}, ["arm_advisor"])
    if test == "uc_metastore_attached":
        if not source_complete(raw, "uc_metastore_summary"):
            return outcome("not_evaluated", "Metastore summary de Unity Catalog no disponible.", source_ids=["uc_metastore_summary"])
        ms = inv.get("uc_metastore")
        return decision(bool(ms and ms.get("metastore_id")), "Asignación de Metastore de Unity Catalog confirmada.", {"metastore": ms}, ["uc_metastore_summary"])
    if test == "uc_storage_credential_mi":
        if not source_complete(raw, "uc_storage_credentials"):
            return outcome("not_evaluated", "Storage credentials de Unity Catalog no disponibles.", source_ids=["uc_storage_credentials"])
        creds = inv.get("uc_storage_credentials", [])
        if not creds:
            return outcome("not_evaluated", "No se observaron storage credentials registradas en Unity Catalog.", source_ids=["uc_storage_credentials"])
        sp_creds = [c["name"] for c in creds if c.get("uses_service_principal") or not c.get("uses_managed_identity")]
        return decision(len(sp_creds) == 0, "Todas las storage credentials usan Azure Managed Identity vía Access Connector.", {
            "total_credentials": len(creds), "non_managed_identity_credentials": sp_creds,
        }, ["uc_storage_credentials"])
    if test == "uc_external_locations_governed":
        if not source_complete(raw, "uc_external_locations", "uc_storage_credentials"):
            return outcome("not_evaluated", "External locations o storage credentials incompletas.", source_ids=["uc_external_locations", "uc_storage_credentials"])
        locs = inv.get("uc_external_locations", [])
        if not locs:
            return outcome("not_evaluated", "No se observaron external locations registradas.", source_ids=["uc_external_locations"])
        known_creds = {c["name"] for c in inv.get("uc_storage_credentials", [])}
        if all(str(l.get("url") or "").lower().startswith("abfss://") for l in locs) and any(not l.get("credential_name") for l in locs) and not known_creds:
            return outcome(
                "not_evaluated",
                "External locations observadas vía permiso mínimo BROWSE con URI abfss://, pero credential_name y uc_storage_credentials están filtrados por ACL de Unity Catalog.",
                {"total_external_locations": len(locs), "browse_only_projection": True},
                ["uc_external_locations", "uc_storage_credentials"],
            )
        ungoverned = [
            l["name"] for l in locs
            if not l.get("credential_name") or l["credential_name"] not in known_creds
            or not str(l.get("url") or "").lower().startswith("abfss://")
        ]
        return decision(len(ungoverned) == 0, "External locations vinculadas a Storage Credential existente y URI abfss://.", {
            "total_external_locations": len(locs), "non_compliant_locations": ungoverned,
        }, ["uc_external_locations", "uc_storage_credentials"])
    if test == "secret_scopes_keyvault":
        if not source_complete(raw, "dbx_secret_scopes"):
            return outcome("not_evaluated", "Secret scopes no disponibles.", source_ids=["dbx_secret_scopes"])
        scopes = inv.get("secret_scopes", [])
        if not scopes:
            return outcome("not_evaluated", "No se observaron secret scopes en el workspace.", source_ids=["dbx_secret_scopes"])
        dbx_backed = [s["name"] for s in scopes if s.get("backend_type") != "AZURE_KEYVAULT"]
        return decision(len(dbx_backed) == 0, "Secret scopes respaldados por Azure Key Vault (AZURE_KEYVAULT).", {
            "total_scopes": len(scopes), "databricks_backed_scopes": dbx_backed,
        }, ["dbx_secret_scopes"])
    if test == "dependency_integrity":
        dep_sources = (
            "dbx_jobs",
            "dbx_clusters",
            "dbx_instance_pools",
            "dbx_cluster_policies",
            "dbx_pipelines",
            "dbx_sql_warehouses",
            "uc_storage_credentials",
            "uc_external_locations",
        )
        broken = dep_graph.get("broken_references", [])
        unverified = dep_graph.get("unverified_references", [])
        incomplete_jobs = [j["name"] for j in inv.get("jobs", []) if j.get("tasks_incomplete") is True]
        incomplete_pipes = [p["name"] for p in inv.get("pipelines", []) if p.get("detail_collected") is False]
        if broken:
            return decision(
                False,
                "Se detectaron referencias internas rotas confirmadas dentro de definiciones completas de Jobs (job_cluster_key o depends_on inexistentes).",
                {
                    "broken_references_count": len(broken),
                    "broken_references": broken,
                    "unverified_references_count": len(unverified),
                },
                list(dep_sources),
            )
        if not source_complete(raw, *dep_sources) or incomplete_jobs or incomplete_pipes or unverified:
            return outcome(
                "not_evaluated",
                "Existen fuentes de dependencias incompletas, detalles de jobs/pipelines truncados o referencias entre objetos no verificadas (las APIs list de Databricks filtran por ACL, por lo que la ausencia de un ID externo se mantiene UNKNOWN en lugar de declararse rota).",
                {
                    "broken_references_count": 0,
                    "unverified_references_count": len(unverified),
                    "unverified_references": unverified,
                    "incomplete_jobs": incomplete_jobs,
                    "incomplete_pipelines": incomplete_pipes,
                },
                list(dep_sources),
            )
        return decision(
            True,
            "Todas las fuentes de dependencia están completas y todas las referencias entre tareas de Jobs, clústeres, pools, políticas, pipelines, warehouses y credenciales resuelven en el mapa de dependencias.",
            {
                "broken_references_count": 0,
                "unverified_references_count": 0,
            },
            list(dep_sources),
        )
    if test == "runtime_table_lineage":
        return outcome(
            "not_evaluated",
            "El linaje dinámico de tablas y columnas (system.access.table_lineage / column_lineage) requiere ejecutar consultas en un SQL Warehouse activo y no se ejecuta ni simula desde este colector de plano de control.",
            {"system_tables_queried": False},
            ["uc_system_lineage"],
        )
    if test == "lakehouse_federation_connections":
        if not source_complete(raw, "uc_connections"):
            return outcome("not_evaluated", "Conexiones de Lakehouse Federation no disponibles.", source_ids=["uc_connections"])
        conns = inv.get("uc_connections", [])
        if not conns:
            return outcome("not_applicable", "No existen conexiones externas de Lakehouse Federation registradas en el metastore.", {"connections_count": 0}, ["uc_connections"])
        return decision(True, "Conexiones externas de Lakehouse Federation inventariadas en el mapa de dependencias.", {
            "connections": [{"name": c["name"], "type": c.get("connection_type"), "host": c.get("host")} for c in conns],
        }, ["uc_connections"])
    if test == "outbound_control_plane_endpoints":
        if not source_complete(raw, "arm_outbound_endpoints"):
            return outcome("not_evaluated", "Lista oficial outboundNetworkDependenciesEndpoints no disponible.", source_ids=["arm_outbound_endpoints"])
        eps = inv.get("outbound_endpoints", [])
        return decision(bool(eps), "Dependencias de red saliente hacia el plano de control inventariadas desde ARM.", {
            "categories": [e["category"] for e in eps], "count": len(eps),
        }, ["arm_outbound_endpoints"])
    if test == "cost_attribution":
        return outcome(
            "not_evaluated",
            "ActualCost de ARM refleja facturación por ResourceId de Azure; la atribución interna de DBU por job/clúster/usuario requiere system.billing.usage y políticas de etiquetado.",
            {"cost_rows_collected": len(raw.get("cost_rows", []))},
            ["azure_cost"],
        )
    raise EvidenceError("unknown_rule", "Workspace rule has no implemented evaluator: " + str(test), "rule_catalog")


def evaluate_workload_rule(rule, row, raw):
    test = rule["test"]
    kind = row.get("kind")
    if test in ("cluster_autotermination", "cluster_policy_bound", "cluster_access_mode", "cluster_runtime_lts", "cluster_autoscaling_or_pool"):
        if kind not in ("AllPurposeCluster", "JobCluster"):
            return None
        if test == "cluster_autotermination":
            if kind == "JobCluster":
                return outcome("not_applicable", "Clúster efímero de Job: finaliza automáticamente al terminar la tarea.", {"cluster_source": row.get("cluster_source")}, [row["source_id"]])
            mins = row.get("autotermination_minutes")
            val = True if isinstance(mins, (int, float)) and 0 < mins <= 60 else False
            return decision(val, "Autoterminación configurada <= 60 minutos en clúster All-Purpose.", {"autotermination_minutes": mins}, [row["source_id"]])
        if test == "cluster_policy_bound":
            return decision(bool(row.get("policy_id")), "Asociación de policy_id observada en el clúster.", {"policy_id": row.get("policy_id")}, [row["source_id"]])
        if test == "cluster_access_mode":
            mode = (row.get("data_security_mode") or "").upper()
            val = True if mode in ("USER_ISOLATION", "SINGLE_USER", "SHARED") else False if mode in ("NONE", "LEGACY_PASSTHROUGH", "LEGACY_TABLE_ACL", "LEGACY_SINGLE_USER", "") else None
            return decision(val, "Modo de acceso data_security_mode compatible con Unity Catalog y aislamiento.", {"data_security_mode": row.get("data_security_mode")}, [row["source_id"]])
        if test == "cluster_runtime_lts":
            sv = row.get("spark_version") or ""
            match = re.match(r"^(\d+)\.(\d+)", sv)
            major = int(match.group(1)) if match else None
            is_lts = "lts" in sv.lower()
            val = True if major is not None and major >= 13 and is_lts else False if major is not None else None
            return decision(val, "Versión de Databricks Runtime LTS >= 13.x observada.", {"spark_version": sv}, [row["source_id"]])
        if test == "cluster_autoscaling_or_pool":
            has_auto = bool(row.get("autoscale")) or bool(row.get("instance_pool_id"))
            return decision(has_auto, "Autoscale o vinculación a Instance Pool observada en el clúster.", {
                "autoscale": row.get("autoscale"), "instance_pool_id": row.get("instance_pool_id"), "num_workers": row.get("num_workers"),
            }, [row["source_id"]])

    if test in ("job_uses_job_compute", "job_resilience_settings", "job_service_principal_run_as"):
        if kind != "Job":
            return None
        tasks = row.get("tasks", [])
        if test == "job_uses_job_compute":
            all_purpose_tasks = [t["task_key"] for t in tasks if t.get("existing_cluster_id")]
            return decision(len(all_purpose_tasks) == 0, "Las tareas del Job usan Job Compute, Serverless, SQL Warehouse o Pipeline en lugar de existing_cluster_id All-Purpose.", {
                "tasks_total": len(tasks), "tasks_on_all_purpose_cluster": all_purpose_tasks,
            }, [row["source_id"]])
        if test == "job_resilience_settings":
            has_timeout = bool(row.get("timeout_seconds")) or (bool(tasks) and all(bool(t.get("timeout_seconds")) for t in tasks))
            has_notif = row.get("has_notifications") is True
            return decision(has_timeout and has_notif, "Job configurado con timeout_seconds y notificaciones de fallo/alerta.", {
                "job_timeout_seconds": row.get("timeout_seconds"), "has_notifications": has_notif,
            }, [row["source_id"]])
        if test == "job_service_principal_run_as":
            sp = row.get("run_as_service_principal")
            user = row.get("run_as_user_name")
            val = True if sp else False if user else None
            return decision(val, "Identidad de ejecución run_as del Job asignada a un Service Principal.", {
                "run_as_service_principal": sp, "run_as_user_name": user,
            }, [row["source_id"]])

    if test == "sql_warehouse_autostop":
        if kind != "SqlWarehouse":
            return None
        mins = row.get("auto_stop_mins")
        serverless = row.get("enable_serverless_compute") is True or (row.get("warehouse_type") or "").upper() == "PRO"
        val = True if isinstance(mins, (int, float)) and 0 < mins <= 30 and serverless else False
        return decision(val, "SQL Warehouse con auto_stop_mins <= 30 minutos y modo Serverless/Pro.", {
            "auto_stop_mins": mins, "enable_serverless_compute": row.get("enable_serverless_compute"), "warehouse_type": row.get("warehouse_type"),
        }, [row["source_id"]])

    if test == "pipeline_unity_catalog":
        if kind != "LakeflowPipeline":
            return None
        if row.get("detail_collected") is False:
            return outcome(
                "not_evaluated",
                "El detalle spec del pipeline (/api/2.0/pipelines/{id}) no estuvo disponible; el listado resumen no incluye catalog/schema.",
                {"pipeline_id": row.get("id"), "detail_collected": False},
                [row.get("detail_source_id") or row["source_id"]],
            )
        cat = row.get("catalog")
        val = True if cat and cat.lower() not in ("hive_metastore", "") else False
        return decision(val, "Pipeline declarativo configurado con catálogo destino en Unity Catalog.", {
            "catalog": cat, "schema": row.get("schema") or row.get("target"), "target": row.get("target"), "serverless": row.get("serverless"),
        }, [row.get("detail_source_id") or row["source_id"]])
    return None


def evaluate_resource_rule(rule, row, raw):
    test = rule["test"]
    rkind = row.get("resource_kind")
    cfg = row.get("configuration", {})
    if test == "storage_tls_and_public_blob":
        if rkind != "microsoft.storage/storageaccounts":
            return None
        https = cfg.get("supportsHttpsTrafficOnly")
        tls = cfg.get("minimumTlsVersion")
        pub_blob = cfg.get("allowBlobPublicAccess")
        val = False if (https is False or tls in ("TLS1_0", "TLS1_1") or pub_blob is True) else (
            True if https is True and tls in ("TLS1_2", "TLS1_3") and pub_blob is False else None
        )
        return decision(val, "HTTPS obligatorio, TLS >= 1.2 y allowBlobPublicAccess=false en cuenta de almacenamiento asociada.", cfg, [row["source_id"]])
    if test == "storage_shared_key_and_network":
        if rkind != "microsoft.storage/storageaccounts":
            return None
        shared = cfg.get("allowSharedKeyAccess")
        pna = cfg.get("publicNetworkAccess")
        if row.get("name", "").lower() == (raw["workspace"].get("dbfs_storage_account_name") or "").lower():
            return outcome("not_applicable", "Cuenta DBFS root administrada por la plataforma Azure Databricks.", cfg, [row["source_id"]])
        val = True if shared is False and pna == "Disabled" else False if shared is True or pna == "Enabled" else None
        return conditional(val, expected(raw, "shared_key_disabled_required") if expected(raw, "shared_key_disabled_required") is not None else True,
                           "Shared Key y acceso público en cuenta ADLS Gen2 asociada.", cfg, [row["source_id"]])
    if test == "keyvault_rbac_and_purge":
        if rkind != "microsoft.keyvault/vaults":
            return None
        rbac = cfg.get("enableRbacAuthorization")
        purge = cfg.get("enablePurgeProtection")
        val = True if rbac is True and purge is True else False if rbac is False or purge is False else None
        return decision(val, "Key Vault asociado con Azure RBAC y Purge Protection habilitados.", cfg, [row["source_id"]])
    if test == "nsg_exposure":
        if rkind != "microsoft.network/networksecuritygroups":
            return None
        rules = row.get("security_rules", [])
        exposed = []
        for srule in rules:
            if srule.get("direction") != "Inbound" or srule.get("access") != "Allow":
                continue
            srcs = ([srule.get("sourceAddressPrefix")] if srule.get("sourceAddressPrefix") else []) + (srule.get("sourceAddressPrefixes") or [])
            ports = ([srule.get("destinationPortRange")] if srule.get("destinationPortRange") else []) + (srule.get("destinationPortRanges") or [])
            if any(s in ("*", "0.0.0.0/0", "::/0", "Internet") for s in srcs) and any(p in ("*", "22", "3389", "0-65535") for p in ports):
                exposed.append(srule)
        return decision(len(exposed) == 0, "Reglas Inbound Allow desde Internet hacia puertos administrativos en NSG asociado.", {
            "exposed_rules": exposed, "total_rules": len(rules),
        }, [row["source_id"]])
    if test == "private_endpoint_approved":
        if rkind != "microsoft.network/privateendpoints":
            return None
        conns = row.get("connections", [])
        val = True if conns and all(c.get("status") == "Approved" for c in conns) else False if conns else None
        return decision(val, "Estado de aprobación de las conexiones Private Endpoint asociadas.", {"connections": conns}, [row["source_id"]])
    return None


def make_check(rule, target_id, target_name, workload_name, evaluation, reference, ws):
    status = evaluation["status"]
    cid = rule["rule_id"] + "-" + hashlib.sha256((ws["id"].lower() + "|" + rule["rule_id"] + "|" + str(target_id)).encode("utf-8")).hexdigest()[:10]
    sev_labels = {"critical": "Crítica", "high": "Alta", "medium": "Media", "low": "Baja"}
    eff_labels = {"low": "L", "medium": "M", "high": "H"}
    return {
        "check_id": cid,
        "rule_id": rule["rule_id"],
        "reference_id": rule["reference_id"],
        "title": rule["title"],
        "status": status,
        "level": rule["level"],
        "area": rule["area"],
        "pillar": rule["pillar"],
        "severity": rule["severity"],
        "severity_label": sev_labels[rule["severity"]],
        "effort": rule["effort"],
        "effort_label": eff_labels[rule["effort"]],
        "resource_id": target_id,
        "resource_name": target_name,
        "workload_name": workload_name,
        "workspace_id": ws["id"],
        "workspace_name": ws["workspace_name"],
        "reason": evaluation["reason"],
        "business_impact": rule["business_impact"],
        "recommendation": rule["recommendation"],
        "learn_url": rule["learn_url"],
        "evidence": [] if status in ("not_evaluated", "not_applicable") and not evaluation["value"] else [
            {
                "source_id": (evaluation["source_ids"] or ["arm_workspace"])[0],
                "source_ids": evaluation["source_ids"] or ["arm_workspace"],
                "resource_id": target_id,
                "observed_at": reference,
                "value": evaluation["value"],
            }
        ],
    }


def evaluate(raw, reference, dep_graph):
    ws, inv = raw["workspace"], raw["inventory"]
    checks = []
    workloads = (
        inv.get("clusters", [])
        + inv.get("jobs", [])
        + inv.get("pipelines", [])
        + inv.get("sql_warehouses", [])
    )
    resources = inv.get("related_resources", [])
    for rule in CATALOG.get("rules", []):
        if rule["level"] == "workspace":
            ev = evaluate_workspace_rule(rule, raw, dep_graph)
            checks.append(make_check(rule, ws["id"], ws["name"], "", ev, reference, ws))
        elif rule["level"] == "workload":
            matched_any = False
            for wl in workloads:
                ev = evaluate_workload_rule(rule, wl, raw)
                if ev is not None:
                    matched_any = True
                    checks.append(make_check(rule, ws["id"] + "/workloads/" + str(wl["id"]), wl["name"], wl["name"], ev, reference, ws))
            if not matched_any:
                checks.append(make_check(rule, ws["id"], ws["name"], "", outcome(
                    "not_evaluated",
                    "No se observaron objetos de carga aplicables o la fuente REST del workspace no estuvo disponible; ausencia no equivale a cumplimiento.",
                    {}, ["dbx_clusters", "dbx_jobs", "dbx_pipelines", "dbx_sql_warehouses"],
                ), reference, ws))
        elif rule["level"] == "resource":
            matched_res = False
            for res in resources:
                ev = evaluate_resource_rule(rule, res, raw)
                if ev is not None:
                    matched_res = True
                    checks.append(make_check(rule, res["id"], res["name"], res["name"] or "", ev, reference, ws))
            if not matched_res:
                checks.append(make_check(rule, ws["id"], ws["name"], "", outcome(
                    "not_evaluated",
                    "No se recolectaron recursos ARM asociados de este tipo en el alcance aprobado; no se asume ausencia de riesgo.",
                    {}, ["arm_workspace"],
                ), reference, ws))
    return checks


def score(checks):
    counts = {s: sum(c["status"] == s for c in checks) for s in CHECK_STATUSES}
    evaluated = counts["passed"] + counts["failed"]
    eligible = evaluated + counts["not_evaluated"]
    return {
        "score": round(100 * counts["passed"] / evaluated, 2) if evaluated else None,
        "passed": counts["passed"],
        "failed": counts["failed"],
        "evaluated": evaluated,
        "not_evaluated": counts["not_evaluated"],
        "not_applicable": counts["not_applicable"],
        "total": len(checks),
        "coverage_percent": round(100 * evaluated / eligible, 2) if eligible else None,
    }


def actions_for(findings):
    order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    horizon = {"low": "quick_win", "medium": "short_term", "high": "medium_term"}
    sorted_findings = sorted(findings, key=lambda f: (order.get(f["severity"], 9), f["rule_id"], f["check_id"]))
    actions = []
    for item in sorted_findings:
        actions.append({
            "id": "ACT-" + item["check_id"],
            "check_id": item["check_id"],
            "rule_id": item["rule_id"],
            "title": item["title"],
            "area": item["area"],
            "pillar": item["pillar"],
            "level": item["level"],
            "severity": item["severity"],
            "severity_label": item["severity_label"],
            "effort": item["effort"],
            "effort_label": item["effort_label"],
            "horizon": horizon.get(item["effort"], "short_term"),
            "status": item["status"],
            "resource_id": item["resource_id"],
            "workload_name": item.get("workload_name", ""),
            "workspace_id": item["workspace_id"],
            "workspace_name": item["workspace_name"],
            "recommendation": item["recommendation"],
            "reason": item["reason"],
            "learn_url": item["learn_url"],
            "estimated_savings": None,
        })
    return actions


def finops_for(raw):
    inv, ws = raw["inventory"], raw["workspace"]
    candidates = []
    for cl in inv.get("clusters", []):
        if cl.get("cluster_source") != "JOB":
            mins = cl.get("autotermination_minutes")
            if not isinstance(mins, (int, float)) or mins <= 0 or mins > 60:
                candidates.append({
                    "id": "FINOPS-CL-" + hashlib.sha256(cl["id"].encode("utf-8")).hexdigest()[:10],
                    "title": "Revisar autoterminación en clúster interactivo All-Purpose",
                    "resource_id": ws["id"] + "/clusters/" + cl["id"],
                    "workload_name": cl["name"],
                    "source_id": cl["source_id"],
                    "basis": "Configuración observada de autotermination_minutes en /api/2.0/clusters/list; sin estimar ahorro DBU.",
                    "value": mins if mins is not None else "disabled",
                    "unit": "minutes",
                    "sample_count": 1,
                    "window": None,
                    "recommendation": "Ajustar autotermination_minutes (<= 60 min) y aplicar Cluster Policy para contener consumo en inactividad.",
                    "estimated_savings": None,
                })
    for job in inv.get("jobs", []):
        ap_tasks = [t["task_key"] for t in job.get("tasks", []) if t.get("existing_cluster_id")]
        if ap_tasks:
            candidates.append({
                "id": "FINOPS-JOB-" + hashlib.sha256(job["id"].encode("utf-8")).hexdigest()[:10],
                "title": "Revisar tareas de Job ejecutando sobre clúster All-Purpose",
                "resource_id": ws["id"] + "/jobs/" + job["id"],
                "workload_name": job["name"],
                "source_id": job["source_id"],
                "basis": "Tareas con existing_cluster_id observadas en /api/2.1/jobs/list; la tarifa DBU de Jobs Compute/Serverless es inferior a All-Purpose.",
                "value": len(ap_tasks),
                "unit": "tasks_on_all_purpose",
                "sample_count": 1,
                "window": None,
                "recommendation": "Evaluar migración de tareas a job_cluster_key o Jobs Serverless tras validar dependencias de librerías e init scripts.",
                "estimated_savings": None,
            })
    for wh in inv.get("sql_warehouses", []):
        mins = wh.get("auto_stop_mins")
        if not isinstance(mins, (int, float)) or mins <= 0 or mins > 30:
            candidates.append({
                "id": "FINOPS-WH-" + hashlib.sha256(wh["id"].encode("utf-8")).hexdigest()[:10],
                "title": "Revisar auto_stop_mins en SQL Warehouse",
                "resource_id": ws["id"] + "/warehouses/" + wh["id"],
                "workload_name": wh["name"],
                "source_id": wh["source_id"],
                "basis": "Configuración auto_stop_mins observada en /api/2.0/sql/warehouses; sin proyectar ahorro monetario.",
                "value": mins if mins is not None else "disabled",
                "unit": "minutes",
                "sample_count": 1,
                "window": None,
                "recommendation": "Redefinir auto_stop_mins <= 30 min o evaluar Serverless SQL Warehouse.",
                "estimated_savings": None,
            })
    cost_rows = raw.get("cost_rows", [])
    currencies = {row["currency"] for row in cost_rows}
    cost_source = next((source for source in raw["sources"] if source["id"] == "azure_cost"), None)
    currency = next(iter(currencies)) if len(currencies) == 1 else None
    total = float(sum((Decimal(str(row["amount"])) for row in cost_rows), Decimal(0))) if currency and pick(cost_source, "status") == "complete" else None
    by_currency = {
        code: float(sum((Decimal(str(row["amount"])) for row in cost_rows if row["currency"] == code), Decimal(0)))
        for code in sorted(currencies)
    }
    return {
        "sources": ["azure_cost", "arm_advisor", "dbx_clusters", "dbx_jobs", "dbx_sql_warehouses"],
        "window": pick(cost_source, "window"),
        "currency": currency,
        "actual_cost": total,
        "cost_rows": cost_rows,
        "candidates": candidates,
        "estimated_savings": None,
        "observed_cost_totals_by_currency": by_currency,
        "cost_source_complete": pick(cost_source, "status") == "complete",
        "notes": [
            "Cluster, warehouse and job configurations are point-in-time control-plane observations, not historical DBU consumption.",
            "ActualCost uses observed approved ARM ResourceIds and actual billing currency; it does not split DBU spend by job, notebook or user.",
            "System table system.billing.usage is not queried automatically so no SQL Warehouse is started or billed by this review.",
            "No fabricated DBU savings, reservation discounts or rightsizing returns are computed.",
        ],
    }


def finish_snapshot(raw, reference, provenance="LIVE", environment="UNSPECIFIED"):
    if provenance not in ("LIVE", "SIMULATED") or environment not in ("LAB", "PRODUCTION", "UNSPECIFIED"):
        raise EvidenceError("invalid_provenance", "Explicit source provenance and environment are required.")
    raw = {
        **raw,
        "sources": list(raw["sources"]) + [
            source_receipt(
                "reference_catalog", reference,
                records=CATALOG.get("catalogSnapshot", {}).get("item_count", 0),
                note="Build-time pinned Azure Databricks Well-Architected & Lakehouse rule catalog.",
            ),
            source_receipt(
                "configuration_requirements", reference,
                "complete" if raw.get("requirements") else "not_configured",
                records=len(raw.get("requirements", {})),
                note="Explicit operator intent only; unknown requirements are not inferred.",
            ),
        ],
    }
    dep_graph = dependencies_for(raw, reference, provenance)
    checks = evaluate(raw, reference, dep_graph)
    findings = [check for check in checks if check["status"] == "failed"]
    global_score = score(checks)
    scores = {
        "global": global_score,
        "coverage": dict(global_score),
        "areas": {area: score([check for check in checks if check["area"] == area]) for area in AREAS},
        "pillars": {pillar: score([check for check in checks if check["pillar"] == pillar]) for pillar in PILLARS},
    }
    blind_spots = [source["id"] for source in raw["sources"] if source["status"] not in ("complete", "not_applicable")]
    critical = sum(check["severity"] == "critical" for check in findings)
    catalog_count = CATALOG.get("catalogSnapshot", {}).get("item_count", len(CATALOG.get("rules", [])))
    dep_counts = dep_graph["summary_counts"]
    return {
        "schema_version": "1.0",
        "provenance": provenance,
        "environment": environment,
        "reference_utc": reference,
        "client": {"name": CLIENT_NAME, "logo_data_uri": CLIENT_LOGO_DATA_URI, "logo_alt": CLIENT_LOGO_ALT},
        "workspace": raw["workspace"],
        "sources": raw["sources"],
        "inventory": raw["inventory"],
        "dependencies": dep_graph,
        "source_data": {
            "workspace_conf": raw.get("workspace_conf"),
            "arm_diagnostics": raw.get("arm_diagnostics", []),
            "advisor": raw.get("advisor", []),
            "cost_rows": raw.get("cost_rows", []),
        },
        "checks": checks,
        "findings": findings,
        "scores": scores,
        "finops": finops_for(raw),
        "actions": actions_for(findings),
        "executive_messages": [
            str(dep_counts["nodes_total"]) + " nodos en el mapa de dependencias (" + str(dep_counts["edges_observed"]) + " relaciones OBSERVED, " + str(dep_counts["edges_inferred"]) + " INFERRED explícitas y " + str(dep_counts["unknowns_total"]) + " puntos ciegos UNKNOWN).",
            str(len(findings)) + " hallazgos de configuración y dependencias observados (" + str(critical) + " críticos reales, sin rellenar un Top 5 ficticio).",
            str(global_score["evaluated"]) + " de " + str(global_score["evaluated"] + global_score["not_evaluated"]) + " comprobaciones aplicables evaluadas; la cobertura se muestra junto al índice local.",
            str(dep_counts["broken_references_total"]) + " referencias rotas detectadas entre tareas de Jobs, clústeres, pools, políticas, pipelines, warehouses y credenciales.",
            str(len(blind_spots)) + " fuentes con estado parcial, denegado o no configurado; ahorro estimado no calculado y ningún clúster o SQL Warehouse fue iniciado.",
        ],
        "methodology": {
            "score_kind": "local_assessment_indicator",
            "official_waf_score": False,
            "read_only": True,
            "score_formula": "100 * passed / (passed + failed), unique workspace/rule/workload/resource check_id. No evaluated checks => null.",
            "coverage_formula": "100 * evaluated / (evaluated + not_evaluated). N/A excluded.",
            "catalogSnapshot": CATALOG.get("catalogSnapshot", {}),
            "catalog_coverage": {
                "total_items": catalog_count,
                "mapped_items": len(CATALOG.get("rules", [])),
                "unmapped_items": max(0, catalog_count - len(CATALOG.get("rules", []))),
                "local_rules": len(CATALOG.get("rules", [])),
            },
            "assessment_url": CATALOG.get("assessment_url", ""),
            "interpretation": CATALOG.get("interpretation", []),
            "scope": {
                "workspace_id": raw["workspace"]["id"],
                "workspace_name": raw["workspace"]["workspace_name"],
                "workspace_host": raw["workspace"]["workspace_url"],
                "auth_mode": raw["workspace"]["auth_mode"],
                "cross_tenant": raw["workspace"]["cross_tenant"],
                "environment": environment,
                "requirements": raw.get("requirements", {}),
            },
            "limitations": [
                "Point-in-time ARM control-plane and Databricks Workspace/Unity Catalog REST metadata assessment; no cluster or SQL Warehouse is started.",
                "Dependency edges are classified strictly as OBSERVED (exact native ID/key join), INFERRED (unverified URI/hostname target) or UNKNOWN (uncollected runtime lineage or code internals).",
                "Cross-tenant execution requires prior administrator setup (multi-tenant app with Federated Identity Credential or Azure Lighthouse + Databricks OIDC federation).",
                "This local indicator is not an official Microsoft Well-Architected Review or Databricks certification.",
            ],
        },
    }


def multi_snapshot(runs, reference, roster):
    if not 1 <= len(runs) <= 5 or len({run["workspace_id"].lower() for run in runs}) != len(runs):
        raise EvidenceError("invalid_workspace_runs", "Multi-workspace runs require distinct fixed workspace IDs.", "assessment")
    if any(
        run["status"] not in ("ok", "partial", "error")
        or ((run["snapshot"] is None) != (run["status"] == "error"))
        or (run["snapshot"] is None and not isinstance(run["error"], dict))
        or (run["snapshot"] is not None and run["error"] is not None)
        for run in runs
    ):
        raise EvidenceError("invalid_workspace_runs", "Each run is an explicit snapshot success/partial or a structured error, never both.", "assessment")
    snapshots = [run["snapshot"] for run in runs if run["snapshot"] is not None]
    provenances = {snapshot["provenance"] for snapshot in snapshots}
    if len(provenances) > 1:
        raise EvidenceError("mixed_provenance", "LIVE and SIMULATED snapshots cannot be combined.", "assessment")
    checks = [check for snapshot in snapshots for check in snapshot["checks"]]
    scores = {
        "global": score(checks),
        "areas": {area: score([row for row in checks if row["area"] == area]) for area in AREAS},
        "pillars": {pillar: score([row for row in checks if row["pillar"] == pillar]) for pillar in PILLARS},
    }
    scores["coverage"] = dict(scores["global"])
    inv_keys = ("clusters", "jobs", "pipelines", "sql_warehouses", "uc_catalogs", "uc_external_locations", "related_resources")
    return {
        "schema_version": "databricks-dep-multi-workspace-v1",
        "reference_utc": reference,
        "provenance": next(iter(provenances)) if provenances else "LIVE",
        "client": {"name": CLIENT_NAME, "logo_data_uri": CLIENT_LOGO_DATA_URI, "logo_alt": CLIENT_LOGO_ALT},
        "available_workspaces": roster,
        "selected_workspace_names": [run["workspace_name"] for run in runs],
        "workspace_runs": runs,
        "aggregate": {
            "scores": scores,
            "inventory_counts": {
                key: sum(len(snapshot["inventory"].get(key) or []) for snapshot in snapshots)
                for key in inv_keys
            },
            "dependency_counts": {
                key: sum(snapshot["dependencies"]["summary_counts"].get(key, 0) for snapshot in snapshots)
                for key in ("nodes_total", "edges_total", "edges_observed", "edges_inferred", "unknowns_total", "broken_references_total")
            },
            "findings_total": sum(len(snapshot["findings"]) for snapshot in snapshots),
            "critical_total": sum(check["status"] == "failed" and check["severity"] == "critical" for check in checks),
            "workspace_status_counts": dict(Counter(run["status"] for run in runs)),
            "failed_workspace_count": sum(run["snapshot"] is None for run in runs),
            "official_waf_score": False,
            "estimated_savings": None,
            "actual_cost": None,
        },
    }


def run_sources(run):
    if run["snapshot"] is not None:
        return run["snapshot"]["sources"]
    return [source_receipt(
        "arm_workspace", run["reference_utc"],
        "denied" if run["error"].get("http_status") in (401, 403) else "error",
        "Primary collection failed; this workspace has no snapshot or inferred healthy-zero inventory.",
        errors=[run["error"]],
    )]


def successful_snapshots(document):
    return (
        [run["snapshot"] for run in document["workspace_runs"] if run["snapshot"] is not None]
        if document.get("schema_version") == "databricks-dep-multi-workspace-v1"
        else [document]
    )


def collection_disclosure(snapshot):
    if snapshot.get("schema_version") == "databricks-dep-multi-workspace-v1":
        sources = [source for run in snapshot["workspace_runs"] for source in run_sources(run)]
        return {
            "reference_utc": snapshot["reference_utc"],
            "fresh_collection": True,
            "provenance": snapshot["provenance"],
            "selected_workspace_names": snapshot["selected_workspace_names"],
            "workspace_run_status_counts": snapshot["aggregate"]["workspace_status_counts"],
            "source_status_counts": dict(Counter(source["status"] for source in sources)),
            "source_total": len(sources),
            "source_details_view": "coverage",
            "paging_basis": "Local offset in this collection; later calls recollect, not a stable cross-call cursor.",
        }
    return {
        "reference_utc": snapshot["reference_utc"],
        "fresh_collection": True,
        "provenance": snapshot["provenance"],
        "environment": snapshot["environment"],
        "auth_mode": snapshot["workspace"]["auth_mode"],
        "cross_tenant": snapshot["workspace"]["cross_tenant"],
        "source_status_counts": dict(Counter(s["status"] for s in snapshot["sources"])),
        "source_total": len(snapshot["sources"]),
        "source_details_view": "coverage",
        "paging_basis": "Local offset in this collection; later calls recollect, not a stable cross-call cursor.",
    }


def summary(snapshot):
    inv = snapshot["inventory"]
    compact_scores = lambda group: {
        k: {
            "score": v["score"],
            "coverage_percent": v["coverage_percent"],
            "evaluated": v["evaluated"],
            "not_evaluated": v["not_evaluated"],
        }
        for k, v in group.items()
    }
    return {
        "workspace_id": snapshot["workspace"]["id"],
        "workspace_name": snapshot["workspace"]["workspace_name"],
        "workspace_url": snapshot["workspace"]["workspace_url"],
        "auth_mode": snapshot["workspace"]["auth_mode"],
        "cross_tenant": snapshot["workspace"]["cross_tenant"],
        "global": snapshot["scores"]["global"],
        "areas": compact_scores(snapshot["scores"]["areas"]),
        "pillars": compact_scores(snapshot["scores"]["pillars"]),
        "inventory_counts": {
            key: len(inv.get(key) or [])
            for key in ("clusters", "jobs", "pipelines", "sql_warehouses", "uc_catalogs", "uc_external_locations", "related_resources")
        },
        "dependency_counts": snapshot["dependencies"]["summary_counts"],
        "findings": len(snapshot["findings"]),
        "critical": sum(f["severity"] == "critical" for f in snapshot["findings"]),
        "catalog_coverage": snapshot["methodology"]["catalog_coverage"],
        "official_waf_score": False,
        "actual_cost": snapshot["finops"]["actual_cost"],
        "currency": snapshot["finops"]["currency"],
        "estimated_savings": None,
    }


def snapshot_rows(snapshot, view):
    inv = snapshot["inventory"]
    uc_rows = (
        ([inv["uc_metastore"]] if inv.get("uc_metastore") else [])
        + inv.get("uc_catalogs", [])
        + inv.get("uc_schemas", [])
        + inv.get("uc_storage_credentials", [])
        + inv.get("uc_external_locations", [])
        + inv.get("uc_connections", [])
    )
    return {
        "summary": [summary(snapshot)],
        "workspace": [snapshot["workspace"]],
        "compute": inv.get("clusters", []) + inv.get("instance_pools", []) + inv.get("cluster_policies", []) + inv.get("global_init_scripts", []),
        "jobs": inv.get("jobs", []),
        "pipelines": inv.get("pipelines", []),
        "warehouses": inv.get("sql_warehouses", []),
        "unity_catalog": uc_rows + inv.get("secret_scopes", []),
        "resources": inv.get("related_resources", []) + inv.get("outbound_endpoints", []),
        "findings": snapshot["checks"],
        "coverage": snapshot["sources"],
        "actions": snapshot["actions"],
        "finops": (
            [{**row, "record_type": "candidate"} for row in snapshot["finops"]["candidates"]]
            + [{**row, "record_type": "cost"} for row in snapshot["finops"]["cost_rows"]]
        ),
        "dependencies": (
            snapshot["dependencies"]["nodes"]
            + snapshot["dependencies"]["edges"]
            + snapshot["dependencies"]["unknowns"]
        ),
    }[view]


def query_snapshot(snapshot, params):
    view = params["view"]
    if snapshot.get("schema_version") == "databricks-dep-multi-workspace-v1":
        rows = []
        for run in snapshot["workspace_runs"]:
            scope = {"workspace_id": run["workspace_id"], "workspace_name": run["workspace_name"]}
            if run["snapshot"] is not None:
                rows.extend({**row, **scope} for row in snapshot_rows(run["snapshot"], view))
            elif view == "coverage":
                rows.extend({**row, **scope} for row in run_sources(run))
            elif view == "summary":
                rows.append({
                    **scope, "status": "error", "global": None, "inventory_counts": None,
                    "error": run["error"], "reference_utc": run["reference_utc"],
                })
    else:
        rows = snapshot_rows(snapshot, view)

    def matches(row):
        if params["workload_name"] and row.get("workload_name") != params["workload_name"] and row.get("name") != params["workload_name"]:
            return False
        if params["classification"] != "all" and row.get("classification") != params["classification"]:
            return False
        for field in ("area", "level", "severity", "status"):
            if params[field] != "all" and row.get(field) != params[field]:
                return False
        return True

    matched = [row for row in rows if matches(row)]
    selected = matched[params["offset"]:params["offset"] + params["limit"]]
    partial = snapshot.get("schema_version") == "databricks-dep-multi-workspace-v1" and any(
        run["status"] != "ok" for run in snapshot["workspace_runs"]
    )
    result = {
        "status": "partial" if partial else "ok",
        "operation": "query",
        "view": view,
        "collection": collection_disclosure(snapshot),
        "total_matched": len(matched),
        "offset": params["offset"],
        "requested_limit": params["limit"],
        "returned": len(selected),
        "has_more": params["offset"] + len(selected) < len(matched),
        "next_offset": params["offset"] + len(selected) if params["offset"] + len(selected) < len(matched) else None,
        "transport_capped": False,
        "rows": selected,
    }
    while selected and response_bytes(result) > TRANSPORT_BYTES:
        selected = selected[:-1]
        result.update(
            rows=selected,
            returned=len(selected),
            transport_capped=True,
            has_more=params["offset"] + len(selected) < len(matched),
            next_offset=params["offset"] + len(selected) if selected and params["offset"] + len(selected) < len(matched) else None,
        )
    if not selected and params["offset"] < len(matched):
        return ensure_response({
            "status": "error",
            "operation": "query",
            "view": view,
            "error": {
                "code": "query_row_too_large",
                "message": "One complete row cannot fit 3500 default-serialized bytes. Use the full report JSON; no zero-row continuation.",
            },
            "total_matched": len(matched),
            "offset": params["offset"],
            "requested_limit": params["limit"],
            "returned": 0,
            "has_more": True,
            "next_offset": None,
            "transport_capped": True,
            "collection": collection_disclosure(snapshot),
        })
    return ensure_response(result)


def safe_json(snapshot):
    document = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    escaped = document.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    if json.loads(escaped) != snapshot:
        raise EvidenceError("round_trip_failed", "Complete embedded normalized JSON did not round-trip.", "renderer")
    return escaped


def render_html(snapshot):
    if HTML_TEMPLATE.count("__REPORT_DATA_JSON__") != 1:
        raise EvidenceError("template_missing", "Build the approved template into the canonical standalone tool.", "renderer")
    validate_logo(snapshot["client"]["logo_data_uri"], snapshot["client"].get("logo_alt", CLIENT_LOGO_ALT))
    return HTML_TEMPLATE.replace("__REPORT_DATA_JSON__", safe_json(snapshot))


def csv_cell(value):
    if value is None:
        return ""
    value = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")) if isinstance(value, (dict, list)) else str(value)
    return "'" + value if value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r", "\n")) else value


def csv_document(rows, fields):
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(fields)
    for row in rows:
        writer.writerow([csv_cell(row.get(field)) for field in fields])
    return stream.getvalue()


def dependencies_csv_rows(snapshot):
    if snapshot.get("schema_version") == "databricks-dep-multi-workspace-v1":
        rows = [row for item in successful_snapshots(snapshot) for row in dependencies_csv_rows(item)]
        rows.extend(
            {
                "record_type": "workspace_collection_error",
                "classification": "UNKNOWN",
                "layer": "control_plane",
                "workspace_id": run["workspace_id"],
                "workspace_name": run["workspace_name"],
                "id": run["workspace_id"],
                "kind": "workspace_error",
                "label": run["workspace_name"],
                "source_ids": [run["error"]["source_id"]],
                "observed_at": run["reference_utc"],
                "details_json": run,
            }
            for run in snapshot["workspace_runs"] if run["snapshot"] is None
        )
        return rows
    dep = snapshot["dependencies"]
    rows = []
    for node in dep["nodes"]:
        rows.append({
            "record_type": "node",
            "classification": node["classification"],
            "layer": node["layer"],
            "workspace_id": node["workspace_id"],
            "workspace_name": node["workspace_name"],
            "id": node["id"],
            "kind": node["kind"],
            "label": node["label"],
            "from": "",
            "to": "",
            "relation": "",
            "join_fields": [],
            "source_ids": [node["source_id"]],
            "observed_at": node["observed_at"],
            "details_json": node,
        })
    for edge in dep["edges"]:
        rows.append({
            "record_type": "edge",
            "classification": edge["classification"],
            "layer": edge["layer"],
            "workspace_id": edge["workspace_id"],
            "workspace_name": edge["workspace_name"],
            "id": edge["id"],
            "kind": "dependency_edge",
            "label": edge["relation"],
            "from": edge["from"],
            "to": edge["to"],
            "relation": edge["relation"],
            "join_fields": edge["join_fields"],
            "source_ids": edge["source_ids"],
            "observed_at": edge["observed_at"],
            "details_json": edge,
        })
    for unk in dep["unknowns"]:
        rows.append({
            "record_type": "unknown",
            "classification": "UNKNOWN",
            "layer": unk["layer"],
            "workspace_id": unk["workspace_id"],
            "workspace_name": unk["workspace_name"],
            "id": unk["id"],
            "kind": unk["kind"],
            "label": unk["code"],
            "from": "",
            "to": "",
            "relation": "",
            "join_fields": [],
            "source_ids": unk["source_ids"],
            "observed_at": unk["observed_at"],
            "details_json": unk,
        })
    return rows


def artifact_directory():
    try:
        cwd = Path.cwd()
        root = cwd.resolve(strict=True)
        linked = any(part.is_symlink() or getattr(part, "is_junction", lambda: False)() for part in (cwd, *cwd.parents))
    except (OSError, RuntimeError) as exc:
        raise EvidenceError("unsafe_artifact_root", "Runtime cwd must resolve to an existing directory.", "artifact_storage") from exc
    if root == Path(root.anchor) or not root.is_dir() or linked:
        raise EvidenceError("unsafe_artifact_root", "Filesystem roots, symlink/junction cwd ancestors and non-directories are forbidden.", "artifact_storage")
    if OUTPUT_DIRECTORY != "databricks-dependency-reports":
        raise EvidenceError("unsafe_artifact_directory", "Only the fixed databricks-dependency-reports child is allowed.", "artifact_storage")
    directory = root / OUTPUT_DIRECTORY
    if directory.is_symlink() or getattr(directory, "is_junction", lambda: False)() or directory.resolve() != directory:
        raise EvidenceError("unsafe_artifact_directory", "Output directory is a symlink/junction or escapes cwd.", "artifact_storage")
    return root, directory


def sharing_fields(root, paths):
    result = {"sharing_mode": "local_files_only", "http_verified": False}
    match = re.fullmatch(
        r"/(?:root/sreagent|usr)/terminalRoot/tmp/ThreadFiles/([0-9a-fA-F-]{36})", root.as_posix()
    )
    if match is None:
        return result
    try:
        if str(UUID(match[1])) != match[1].lower():
            return result
    except ValueError:
        return result
    suffixes = {
        "report_path": ".html",
        "snapshot_path": "-snapshot.json",
        "findings_csv_path": "-findings.csv",
        "dependencies_csv_path": "-dependencies.csv",
    }
    if set(paths) != set(suffixes):
        raise EvidenceError("unsafe_sharing_path", "Native delivery requires exactly the four guarded report artifacts.", "artifact_storage")
    stem = paths["report_path"].name.removesuffix(".html")
    if not re.fullmatch(r"(?:dbx|simulated)-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12}", stem):
        raise EvidenceError("unsafe_sharing_path", "Native aliases require this tool's generated run filenames.", "artifact_storage")
    expected = root / "databricks-dependency-reports"
    aliases = {}
    for key, path in paths.items():
        if path.parent != expected or path.name != stem + suffixes[key]:
            raise EvidenceError("unsafe_sharing_path", "Native aliases must reference the same run in the fixed report directory.", "artifact_storage")
        aliases[key.removesuffix("_path") + "_url"] = (
            "/api/files/tmp/ThreadFiles/" + match[1] + "/databricks-dependency-reports/" + quote(path.name, safe="")
        )
    return {**result, "sharing_mode": "native_ui", **aliases}


def report_envelope(snapshot, paths, root):
    items = successful_snapshots(snapshot)
    findings = [row for item in items for row in item["findings"]]
    multi = snapshot.get("schema_version") == "databricks-dep-multi-workspace-v1"
    aggregate = snapshot["aggregate"] if multi else None
    partial = any(s["status"] not in ("complete", "not_applicable") for item in items for s in item["sources"])
    inv_keys = ("clusters", "jobs", "pipelines", "sql_warehouses", "uc_catalogs", "uc_external_locations", "related_resources")
    result = {
        "status": "partial" if partial or (multi and aggregate["workspace_status_counts"].get("error")) else "ok",
        "operation": "report",
        "artifact_status": "written",
        **sharing_fields(root, paths),
        "collection": collection_disclosure(snapshot),
        "global": aggregate["scores"]["global"] if multi else snapshot["scores"]["global"],
        "findings_total": len(findings),
        "inventory_counts": aggregate["inventory_counts"] if multi else {
            key: len(snapshot["inventory"].get(key) or []) for key in inv_keys
        },
        "dependency_counts": aggregate["dependency_counts"] if multi else snapshot["dependencies"]["summary_counts"],
        "critical_total": sum(row["severity"] == "critical" for row in findings),
        "estimated_savings": None,
        **{key: str(path) for key, path in paths.items()},
    }
    return ensure_response(result)


def write_report(snapshot):
    root, directory = artifact_directory()
    reference = snapshot["reference_utc"].replace(":", "").replace("-", "")
    prefix = ("simulated-" if snapshot["provenance"] == "SIMULATED" else "dbx-") + reference + "-" + uuid4().hex[:12]
    paths = {
        key: directory / (prefix + suffix)
        for key, suffix in (
            ("report_path", ".html"),
            ("snapshot_path", "-snapshot.json"),
            ("findings_csv_path", "-findings.csv"),
            ("dependencies_csv_path", "-dependencies.csv"),
        )
    }
    response = report_envelope(snapshot, paths, root)
    snapshot_document = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    if json.loads(snapshot_document) != snapshot:
        raise EvidenceError("round_trip_failed", "Full normalized export does not round-trip.", "artifact_storage")
    documents = {
        "report_path": render_html(snapshot),
        "snapshot_path": snapshot_document,
        "findings_csv_path": csv_document(
            [{**row, "details_json": row} for item in successful_snapshots(snapshot) for row in item["findings"]],
            ("check_id", "rule_id", "reference_id", "title", "status", "level", "area", "pillar", "severity", "resource_id",
             "workspace_id", "workspace_name", "workload_name", "effort", "reason", "recommendation", "learn_url", "details_json"),
        ),
        "dependencies_csv_path": csv_document(
            dependencies_csv_rows(snapshot),
            ("record_type", "classification", "layer", "workspace_id", "workspace_name", "id", "kind", "label",
             "from", "to", "relation", "join_fields", "source_ids", "observed_at", "details_json"),
        ),
    }
    encoded = {key: value.encode("utf-8-sig" if key.endswith("csv_path") else "utf-8") for key, value in documents.items()}
    if any(len(value) > ARTIFACT_BYTES for value in encoded.values()):
        raise EvidenceError("artifact_size_exceeded", "Complete artifacts exceed 4800000 bytes; no records, sources or time windows were dropped and no files were written.", "artifact_storage")
    temporary, written = [], []
    try:
        directory.mkdir(exist_ok=True)
        if artifact_directory()[1] != directory or directory.resolve(strict=True) != directory or not directory.is_dir():
            raise EvidenceError("unsafe_artifact_directory", "Output directory changed after creation.", "artifact_storage")
        for key, data in encoded.items():
            if paths[key].exists() or paths[key].is_symlink():
                raise EvidenceError("artifact_collision", "A unique output path already exists; no overwrite.", "artifact_storage")
            fd, filename = tempfile.mkstemp(prefix=prefix + "-", suffix=".tmp", dir=directory)
            temp_path = Path(filename)
            temporary.append(temp_path)
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp_path, paths[key])
            temporary.remove(temp_path)
            written.append(paths[key])
        if any(path.read_bytes() != encoded[key] for key, path in paths.items()):
            raise EvidenceError("artifact_readback_failed", "Written artifact bytes differ from complete prepared content.", "artifact_storage")
        if json.loads(paths["snapshot_path"].read_text(encoding="utf-8")) != snapshot:
            raise EvidenceError("artifact_readback_failed", "Written full normalized evidence differs from source-normalized data.", "artifact_storage")
    except (OSError, EvidenceError) as exc:
        failures = []
        for path in temporary + written:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                failures.append(path.name)
        if failures:
            raise EvidenceError(
                "artifact_cleanup_failed",
                "Artifact failure and cleanup failure; inspect these generated files in the fixed output directory: " + ", ".join(failures),
                "artifact_storage",
            ) from exc
        if isinstance(exc, EvidenceError):
            raise
        raise EvidenceError("artifact_write_failed", "Could not atomically write/read back all four files; this run's partial files were removed.", "artifact_storage") from exc
    return response


def main(
    operation: str = "report",
    view: str = "summary",
    workspace_name: str = "",
    workspace_names: str = "",
    workload_name: str = "",
    classification: str = "all",
    area: str = "all",
    level: str = "all",
    severity: str = "all",
    status: str = "all",
    limit: int = 25,
    offset: int = 0,
) -> dict:
    """Collect one or several fixed approved Azure Databricks workspaces; never change source scope or identity."""
    try:
        params = validate_parameters(
            operation, view, workspace_name, workspace_names, workload_name,
            classification, area, level, severity, status, limit, offset,
        )
        configs, roster = selection_configs(workspace_name, workspace_names)
        if operation == "list_workspaces":
            return ensure_response({
                "status": "ok",
                "operation": operation,
                "fresh_collection": False,
                "roster_basis": "fixed_operator_configuration_not_observed_inventory",
                "available_workspaces": roster,
                "total": len(roster),
            })
        if not CATALOG.get("rules"):
            raise EvidenceError("catalog_missing", "Use the build-generated whole-file tool, not unbuilt engine.py.", "rule_catalog")
        reference = utc_now()
        if len(configs) == 1:
            config = configs[0]
            raw = collect_live(config, reference)
            snapshot = finish_snapshot(raw, reference, environment=config["environment"])
            snapshot.update(available_workspaces=roster, selected_workspace_names=[config["name"]])
        else:
            runs = []
            deadline = time.monotonic() + MAX_COLLECTION_SECONDS
            for config in configs:
                run_reference = utc_now()
                run = {
                    "workspace_id": config["id"],
                    "workspace_name": config["name"],
                    "reference_utc": run_reference,
                    "snapshot": None,
                    "error": None,
                    "status": "error",
                }
                try:
                    if time.monotonic() >= deadline:
                        raise EvidenceError("collection_deadline", "Shared multi-workspace time bound reached; this workspace was not collected, not empty/healthy.", "collection")
                    raw = collect_live(config, run_reference, deadline=deadline)
                    run["snapshot"] = finish_snapshot(raw, run_reference, environment=config["environment"])
                    run["status"] = "partial" if any(
                        source["status"] not in ("complete", "not_applicable") for source in run["snapshot"]["sources"]
                    ) else "ok"
                except EvidenceError as exc:
                    run["error"] = exc.public()
                runs.append(run)
            snapshot = multi_snapshot(runs, reference, roster)
            if not successful_snapshots(snapshot):
                return ensure_response({
                    "status": "error",
                    "error": {
                        "code": "all_workspaces_failed",
                        "source": "arm_workspace",
                        "message": "No selected workspace produced a snapshot; no empty/healthy report or files.",
                    },
                    "artifact_status": "not_written",
                    "workspace_errors": [
                        {
                            "workspace_name": run["workspace_name"],
                            "error": {key: run["error"].get(key) for key in ("code", "source_id", "http_status")},
                        }
                        for run in runs
                    ],
                    "provenance": "LIVE",
                })
        return query_snapshot(snapshot, params) if operation == "query" else write_report(snapshot)
    except EvidenceError as exc:
        return ensure_response({
            "status": "error",
            "error": exc.public(),
            "artifact_status": "cleanup_failed" if exc.code == "artifact_cleanup_failed" else "not_written",
            "provenance": "LIVE",
        })

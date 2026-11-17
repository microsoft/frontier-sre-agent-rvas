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
# Optional cross-tenant certificate for auth_mode "cross_tenant_multitenant_fic". The Azure SRE Agent sandbox hands
# Python tools sidecar-issued managed identity tokens that the platform proxy swaps at egress, so they cannot be sent
# as a federated client assertion (Entra rejects them with AADSTS5002723). Store a certificate of the multi-tenant
# app in a Key Vault the agent identity can read (Key Vault Secrets User) and set both values; leave them empty to
# use the federated identity credential.
CROSS_TENANT_CERT_KEYVAULT_URL = ""
CROSS_TENANT_CERT_NAME = ""
CLIENT_NAME = "Customer"
# Here goes the customer's logo, privately configured as a validated PNG/JPEG
# data URI. Keep generic Git source empty. Use adjacent strings <10K per line.
CLIENT_LOGO_DATA_URI = ""
CLIENT_LOGO_ALT = "Authorized customer logo"
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
        # Databricks costs (report section 6): Cost Management grouped by Databricks tags for the workspace resource,
        # its managed resource group and approved_cost_resource_ids. Needs Reader or Cost Management Reader on the
        # subscription; free reads that never start compute.
        "cost_analysis_enabled": True,
        # OFF by default because it costs DBUs: the ID of an EXISTING SQL warehouse enables per-run and per-user detail
        # from system.billing.usage + system.billing.list_prices (Statement Execution API, one fixed read-only SELECT).
        "system_tables_warehouse_id": "",
        "requirements": {},
    }
}
# Databricks cost analysis settings (shared by all approved workspaces).
COST_METRIC = "AmortizedCost"  # AmortizedCost spreads Databricks commit units and reservations; ActualCost is the invoice view
COST_ALLOCATION_TAGS = ["team", "project", "cost_center"]  # your own cluster, job, pool and warehouse tags (up to 3 keys)
COST_AUTOTERMINATION_MAX_MINUTES = 60  # interactive clusters with a longer auto-termination are flagged
COST_WAREHOUSE_AUTOSTOP_MAX_MINUTES = 30  # SQL warehouses with a longer auto-stop are flagged
COST_JOBS_TO_ALL_PURPOSE_DBU_RATIO = 0.55  # Jobs compute DBU list price / All-purpose DBU list price (Premium 0.30 / 0.55)
COST_SPOT_DISCOUNT = 0.6  # conservative Azure Spot discount used for worker VMs (Azure quotes up to 90 %)
REPORT_FOCUS = "configuration"  # "costs" opens the report with the Databricks cost section (title, verdict and KPIs)
# Optional private branding (keep empty in Git): CSS colour overrides from BRAND_THEME_KEYS, a WOFF2 heading font as a
# data URI (<= 80 KB) and where the client logo goes ("hero" plaque or "bar" = white top bar, no plaque).
BRAND_THEME = {}
BRAND_DISPLAY_FONT_DATA_URI = ""
BRAND_LOGO_PLACEMENT = "hero"

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
MAX_COLLECTION_SECONDS = 420
MAX_HTTP_ATTEMPTS = 360
OUTPUT_DIRECTORY = "databricks-dependency-reports"
COST_API_VERSION = "2025-03-01"
COST_QUERY_RESERVE_SECONDS = 20
MAX_COST_ROWS = 20000
MAX_COST_DAILY_KEYS = 100
COST_MAX_RETRY_WAIT = 30
COST_DIMENSIONS = (
    ("cluster", "ClusterName"),
    ("job", "JobId"),
    ("warehouse", "SqlEndpointId"),
    ("pool", "DatabricksInstancePoolId"),
)
BRAND_THEME_KEYS = (
    "--paper", "--surface", "--soft", "--hover", "--ink", "--title", "--muted", "--line", "--line2", "--link", "--focus",
    "--sel", "--chart", "--chart-2", "--edge", "--bar-bg", "--bar-hover", "--btn", "--btn-hover", "--btn-ink", "--hero-a",
    "--hero-b", "--hero-muted", "--hero-line", "--brand-rule", "--brand-logo", "--foot-bg", "--foot-ink",
)
OPERATIONS = ("report", "query", "list_workspaces", "self_test")
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
    "costs",
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
CATALOG = {}
HTML_TEMPLATE = ""
# END BUILD-TIME ASSETS


SIDECAR_TOKEN_ISSUER = "adc-msi-sidecar"


def normalize_sidecar_claims(claims):
    """Map Azure SRE Agent sandbox token claims onto the standard Entra names.

    Python tools in the SRE Agent sandbox receive placeholder tokens issued by the identity sidecar
    (iss "adc-msi-sidecar") that the platform proxy replaces with the real managed identity token at egress.
    They carry tid, clientId and scp instead of aud/appid, so tenant, client and audience stay verifiable.
    """
    if not isinstance(claims, dict) or claims.get("iss") != SIDECAR_TOKEN_ISSUER:
        return claims
    scope = claims.get("scp") if isinstance(claims.get("scp"), str) else ""
    audience = scope[:-len("/.default")] if scope.endswith("/.default") else scope
    if audience.rstrip("/").lower() == "https://management.core.windows.net":
        audience = "https://management.azure.com"
    return dict(claims, appid=claims.get("clientId") or claims.get("cid") or None, aud=audience or None)


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


def validate_cost_settings():
    if COST_METRIC not in ("AmortizedCost", "ActualCost"):
        raise EvidenceError("configuration_required", "COST_METRIC must be AmortizedCost or ActualCost.", "configuration")
    tags = COST_ALLOCATION_TAGS
    if (
        not isinstance(tags, list) or len(tags) > 3
        or any(not isinstance(t, str) or not re.fullmatch(r"[A-Za-z0-9_.:/=+@-][A-Za-z0-9 _.:/=+@-]{0,127}", t) for t in tags)
        or len({t.lower() for t in tags}) != len(tags)
    ):
        raise EvidenceError("configuration_required", "COST_ALLOCATION_TAGS holds up to 3 distinct tag keys.", "configuration")
    for name, value, low, high in (
        ("COST_AUTOTERMINATION_MAX_MINUTES", COST_AUTOTERMINATION_MAX_MINUTES, 10, 1440),
        ("COST_WAREHOUSE_AUTOSTOP_MAX_MINUTES", COST_WAREHOUSE_AUTOSTOP_MAX_MINUTES, 1, 1440),
        ("COST_JOBS_TO_ALL_PURPOSE_DBU_RATIO", COST_JOBS_TO_ALL_PURPOSE_DBU_RATIO, 0.05, 1),
        ("COST_SPOT_DISCOUNT", COST_SPOT_DISCOUNT, 0, 0.95),
    ):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not low <= value <= high:
            raise EvidenceError("configuration_required", name + " is outside its documented range.", "configuration")


def presentation_settings():
    """Validated presentation hooks embedded in the report: focus, colour overrides, heading font and logo placement."""
    if REPORT_FOCUS not in ("configuration", "costs"):
        raise EvidenceError("configuration_required", "REPORT_FOCUS must be configuration or costs.", "branding")
    if BRAND_LOGO_PLACEMENT not in ("hero", "bar"):
        raise EvidenceError("configuration_required", "BRAND_LOGO_PLACEMENT must be hero or bar.", "branding")
    if not isinstance(BRAND_THEME, dict) or len(BRAND_THEME) > len(BRAND_THEME_KEYS):
        raise EvidenceError("configuration_required", "BRAND_THEME maps documented CSS variables to colours.", "branding")
    colour = r"#[0-9A-Fa-f]{6}|rgba\((?:\s*\d{1,3}\s*,){3}\s*(?:0|1|0?\.\d{1,3})\s*\)"
    for key, value in BRAND_THEME.items():
        if key not in BRAND_THEME_KEYS or not isinstance(value, str) or not re.fullmatch(colour, value):
            raise EvidenceError("configuration_required", "BRAND_THEME accepts only " + ", ".join(BRAND_THEME_KEYS) + " with #RRGGBB or rgba() colours.", "branding")
    font = BRAND_DISPLAY_FONT_DATA_URI
    if font:
        match = re.fullmatch(r"data:font/woff2;base64,([A-Za-z0-9+/=]+)", font) if isinstance(font, str) and len(font) <= 110000 else None
        try:
            data = base64.b64decode(match[1], validate=True) if match else b""
        except binascii.Error:
            data = b""
        if not 1000 <= len(data) <= 80000 or not data.startswith(b"wOF2"):
            raise EvidenceError("configuration_required", "BRAND_DISPLAY_FONT_DATA_URI must be an inline WOFF2 font of at most 80 KB.", "branding")
    return {"focus": REPORT_FOCUS, "logo_placement": BRAND_LOGO_PLACEMENT, "theme": dict(BRAND_THEME), "display_font": font}


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
    if auth_mode == "cross_tenant_multitenant_fic" and (CROSS_TENANT_CERT_KEYVAULT_URL or CROSS_TENANT_CERT_NAME):
        if not (
            isinstance(CROSS_TENANT_CERT_KEYVAULT_URL, str)
            and re.fullmatch(r"https://[a-z0-9-]{3,24}\.vault\.azure\.net/?", CROSS_TENANT_CERT_KEYVAULT_URL)
            and isinstance(CROSS_TENANT_CERT_NAME, str)
            and re.fullmatch(r"[A-Za-z0-9-]{1,127}", CROSS_TENANT_CERT_NAME)
        ):
            raise EvidenceError(
                "configuration_required",
                "Configure CROSS_TENANT_CERT_KEYVAULT_URL as https://<vault>.vault.azure.net and CROSS_TENANT_CERT_NAME as the certificate name, or leave both empty.",
                "configuration",
            )
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
    cost_analysis = config.get("cost_analysis_enabled", True)
    if not isinstance(cost_analysis, bool):
        raise EvidenceError("configuration_required", "Configure the boolean cost_analysis_enabled.", "configuration")
    warehouse = config.get("system_tables_warehouse_id", "")
    if not isinstance(warehouse, str) or (warehouse and not re.fullmatch(r"[A-Za-z0-9]{8,64}", warehouse)):
        raise EvidenceError("configuration_required", "system_tables_warehouse_id is empty (off) or the ID of an existing SQL warehouse.", "configuration")
    validate_cost_settings()
    presentation_settings()
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
        "cost_analysis_enabled": cost_analysis,
        "system_tables_warehouse_id": warehouse,
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
        ("operation", operation, OPERATIONS),
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
    if operation in ("report", "list_workspaces", "self_test") and (view != "summary" or filters or limit != 25 or offset != 0):
        raise EvidenceError("invalid_combination", "report/list_workspaces/self_test cannot be narrowed by query filters or paging.", "parameters")
    if operation in ("list_workspaces", "self_test") and (workspace_name or workspace_names):
        raise EvidenceError("invalid_combination", "list_workspaces and self_test do not select a workspace.", "parameters")
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
        claims = normalize_sidecar_claims(claims)
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

    def exchange_entra_certificate(self, target_resource):
        kv_token = self.uami_token(KEYVAULT_AUDIENCE)
        self._guard_budget()
        kv_req = Request(CROSS_TENANT_CERT_KEYVAULT_URL.rstrip("/") + "/secrets/" + CROSS_TENANT_CERT_NAME + "?api-version=7.4",
                         method="GET", headers={"Authorization": "Bearer " + kv_token, "Accept": "application/json"})
        try:
            with self.opener.open(kv_req, timeout=15) as response:
                kv_payload = obj(json.loads(response.read(65536)), "identity")
        except HTTPError as exc:
            raise EvidenceError("keyvault_secret_read_failed", "Key Vault cross-tenant certificate read failed with HTTP " + str(exc.code) + ".", "identity", exc.code) from exc
        except (URLError, TimeoutError, ssl.SSLError, OSError, ValueError) as exc:
            raise EvidenceError("keyvault_secret_read_failed", "Key Vault cross-tenant certificate transport failed.", "identity") from exc
        pem = kv_payload.get("value")
        if not isinstance(pem, str) or len(pem) > 32768 or "-----BEGIN" not in pem:
            raise EvidenceError("keyvault_secret_read_failed", "Key Vault returned no PEM certificate for the cross-tenant app.", "identity")
        self._guard_budget()
        try:
            from azure.identity import CertificateCredential
            access_token = CertificateCredential(TARGET_TENANT_ID.lower(), FEDERATED_APP_CLIENT_ID.lower(),
                                                 certificate_data=pem.encode("utf-8")).get_token(target_resource.rstrip("/") + "/.default").token
        except Exception as exc:
            raise EvidenceError("cross_tenant_auth_failed", "Cross-tenant certificate sign-in failed: " + " ".join(str(exc).split())[:220], "identity") from exc
        verify_jwt_claims(access_token, TARGET_TENANT_ID, FEDERATED_APP_CLIENT_ID, target_resource)
        return access_token

    def exchange_entra_fic(self, target_resource):
        if CROSS_TENANT_CERT_KEYVAULT_URL and CROSS_TENANT_CERT_NAME:
            return self.exchange_entra_certificate(target_resource)
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
    def __init__(self, identity, origin=ARM_ORIGIN, token_kind="arm", patient=False):
        self.identity, self.origin, self.token_kind = identity, origin, token_kind
        # patient readers (Cost Management) honour the *retry-after headers for longer; others keep the 3-attempt policy
        self.patient = patient
        self.statement_path = None
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
        if method == "POST" and not (
            parsed.path.lower().endswith("/providers/microsoft.costmanagement/query")
            or (self.statement_path is not None and parsed.path == self.statement_path)
        ):
            raise EvidenceError("unsafe_method", "This POST is not an enumerated read-only operation.", source)
        payload = None if body is None else json.dumps(body, allow_nan=False).encode("utf-8")
        attempts = 5 if self.patient else 3
        for attempt in range(attempts):
            bearer = self._bearer()
            self.identity._guard_budget()
            request = Request(url, data=payload, method=method, headers={
                "Authorization": "Bearer " + bearer,
                "Accept": "application/json",
                "Content-Type": "application/json",
            })
            try:
                with self.opener.open(request, timeout=60 if self.patient else 30) as response:
                    if response.status == 204 and allow_empty:
                        return {}
                    if response.status != 200:
                        raise EvidenceError("http_error", "Read returned HTTP " + str(response.status) + ".", source, response.status)
                    raw = response.read(HTTP_BYTES + 1)
                    if len(raw) > HTTP_BYTES:
                        raise EvidenceError("response_cap", "Source response exceeded the disclosed byte safety bound.", source)
            except HTTPError as exc:
                if exc.code in (429, 500, 502, 503, 504) and attempt < attempts - 1:
                    headers = exc.headers.items() if exc.headers else []
                    waits = [int(v) for k, v in headers if k.lower().endswith("retry-after") and re.fullmatch(r"\s*[0-9]{1,4}\s*", str(v))]
                    if self.patient:
                        wait = min(COST_MAX_RETRY_WAIT, max(waits) + 1 if waits else 5 * (attempt + 1))
                        if self.identity.deadline - time.monotonic() > wait + COST_QUERY_RESERVE_SECONDS / 2:
                            time.sleep(wait)
                            continue
                    else:
                        time.sleep(min(max(waits), 5) if waits else attempt + 1)
                        continue
                raise EvidenceError(
                    "access_denied" if exc.code in (401, 403) else "throttled" if exc.code == 429 and self.patient else "http_error",
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


class StatementReader(HttpReader):
    """The only SQL path, OFF by default: POST /api/2.0/sql/statements with the fixed read-only billing SELECT."""

    PATH = "/api/2.0/sql/statements"

    def __init__(self, identity, origin):
        super().__init__(identity, origin, "databricks")
        self.statement_path = self.PATH

    def allow(self, url, method="GET"):
        parsed = urlsplit(url)
        if (
            method != "POST" or parsed.scheme != "https" or parsed.scheme + "://" + parsed.netloc != self.origin
            or parsed.path != self.PATH or parsed.query or parsed.fragment or parsed.username
        ):
            raise EvidenceError("unsafe_endpoint", "Only the fixed system-table billing statement may be posted.", "dbx_system_billing")
        self.allowed.add((method, parsed.path))
        return url

    def request(self, method, url, source, body=None, allow_empty=False):
        if not isinstance(body, dict) or body.get("statement") != SYSTEM_BILLING_STATEMENT:
            raise EvidenceError("unsafe_statement", "Only the fixed read-only billing statement is allowed.", source)
        return super().request(method, url, source, body=body, allow_empty=allow_empty)


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
    sub = config.get("subscription_id") or SUBSCRIPTION_ID
    resource_id = arm_id(raw.get("id"), sub)
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
    ac_id = arm_id(access_connector.get("id"), sub) if access_connector.get("id") else None
    ac_uami = arm_id(access_connector.get("userAssignedIdentityId"), sub) if access_connector.get("userAssignedIdentityId") else None
    custom_vnet_id = param_val(params, "customVirtualNetworkId", "str", source_id)
    if custom_vnet_id:
        custom_vnet_id = arm_id(custom_vnet_id, sub)
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
        "subscription_id": sub,
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
    sub = config.get("subscription_id") or SUBSCRIPTION_ID
    resource_id = arm_id(raw.get("id"), sub)
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
            arm_id(k, sub) for k in obj(identity_block.get("userAssignedIdentities") or {}, source_id)
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
        row["subnet_ids"] = [arm_id(s.get("id"), sub) for s in array(props.get("subnets", []), source_id) if s.get("id")]
    elif kind == "microsoft.network/virtualnetworks/subnets":
        row["address_prefix"] = text(props.get("addressPrefix"), source_id, 128)
        row["nsg_id"] = arm_id(pick(props, "networkSecurityGroup", "id"), sub) if pick(props, "networkSecurityGroup", "id") else None
        row["route_table_id"] = arm_id(pick(props, "routeTable", "id"), sub) if pick(props, "routeTable", "id") else None
        row["nat_gateway_id"] = arm_id(pick(props, "natGateway", "id"), sub) if pick(props, "natGateway", "id") else None
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
        row["public_ip_ids"] = [arm_id(ip.get("id"), sub) for ip in array(props.get("publicIpAddresses", []), source_id) if ip.get("id")]
    elif kind == "microsoft.network/publicipaddresses":
        row["configuration"]["ipAddress"] = text(props.get("ipAddress"), source_id, 128)
        row["configuration"]["publicIPAllocationMethod"] = text(props.get("publicIPAllocationMethod"), source_id, 64)
    elif kind == "microsoft.network/privateendpoints":
        row["subnet_id"] = arm_id(pick(props, "subnet", "id"), sub) if pick(props, "subnet", "id") else None
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


def referenced_resource_ids(row, subscription=None):
    refs = []
    for field in ("subnet_ids", "public_ip_ids", "user_assigned_identities"):
        refs.extend((val, field) for val in row.get(field, []) if val)
    for field in ("nsg_id", "route_table_id", "nat_gateway_id", "subnet_id"):
        if row.get(field):
            refs.append((row[field], field))
    if row.get("resource_kind") == "microsoft.network/virtualnetworks/subnets":
        refs.append((re.split(r"/subnets/", row["id"], flags=re.IGNORECASE)[0], "parent_virtual_network_id"))
    for val, field in refs:
        val = arm_id(val, subscription or SUBSCRIPTION_ID)
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
        "creator_user_name": text(raw.get("creator_user_name"), source_id, 256),
        "azure_availability": text(pick(raw, "azure_attributes", "availability"), source_id, 64),
        "first_on_demand": number(pick(raw, "azure_attributes", "first_on_demand"), source_id),
        "start_time": number(raw.get("start_time"), source_id),
        "last_restarted_time": number(raw.get("last_restarted_time"), source_id),
        "terminated_time": number(raw.get("terminated_time"), source_id),
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
        "azure_availability": text(pick(raw, "azure_attributes", "availability"), source_id, 64),
        "custom_tags": tags_map(raw.get("custom_tags"), source_id),
        "state": text(raw.get("state"), source_id, 64),
        "stats": {
            key: number(pick(raw, "stats", key), source_id)
            for key in ("used_count", "idle_count", "pending_used_count", "pending_idle_count")
        },
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
    enforced_tags, autotermination = None, None
    definition = raw.get("definition")
    if isinstance(definition, str) and len(definition) <= 200000:
        try:
            rules = json.loads(definition)
        except ValueError:
            rules = None
        if isinstance(rules, dict):
            # only tag names and the auto-termination bound are kept; values such as Spark settings are never exported
            enforced_tags = sorted({k[len("custom_tags."):][:128] for k in rules if isinstance(k, str) and k.startswith("custom_tags.")})
            rule = rules.get("autotermination_minutes")
            if isinstance(rule, dict):
                autotermination = {
                    key: rule.get(key) for key in ("type", "value", "maxValue", "defaultValue")
                    if isinstance(rule.get(key), (int, float, str)) and not isinstance(rule.get(key), bool) and len(str(rule.get(key))) <= 32
                }
    return {
        "id": pol_id,
        "policy_id": pol_id,
        "name": name,
        "workload_name": name,
        "kind": "ClusterPolicy",
        "policy_family_id": text(raw.get("policy_family_id"), source_id, 128),
        "is_default": boolean(raw.get("is_default"), source_id),
        "enforced_tag_keys": enforced_tags,
        "autotermination_rule": autotermination,
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
            autoscale = new_cluster.get("autoscale") if isinstance(new_cluster.get("autoscale"), dict) else {}
            job_clusters.append({
                "job_cluster_key": key,
                "spark_version": text(new_cluster.get("spark_version"), source_id, 128),
                "node_type_id": text(new_cluster.get("node_type_id"), source_id, 128),
                "driver_node_type_id": text(new_cluster.get("driver_node_type_id"), source_id, 128),
                "policy_id": text(new_cluster.get("policy_id"), source_id, 128),
                "instance_pool_id": text(new_cluster.get("instance_pool_id"), source_id, 128),
                "data_security_mode": text(new_cluster.get("data_security_mode"), source_id, 64),
                "num_workers": number(new_cluster.get("num_workers"), source_id),
                "autoscale_max_workers": number(autoscale.get("max_workers"), source_id),
                "azure_availability": text(pick(new_cluster, "azure_attributes", "availability"), source_id, 64),
                "runtime_engine": text(new_cluster.get("runtime_engine"), source_id, 64),
                "custom_tags": tags_map(new_cluster.get("custom_tags"), source_id),
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
    pause_status = pick(schedule, "pause_status") if isinstance(schedule, dict) else None
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
        "schedule_paused": pause_status == "PAUSED",
        "continuous": bool(settings.get("continuous")),
        "creator_user_name": text(raw.get("creator_user_name"), source_id, 256),
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
        "spot_instance_policy": text(raw.get("spot_instance_policy"), source_id, 64),
        "num_clusters": number(raw.get("num_clusters"), source_id),
        "num_active_sessions": number(raw.get("num_active_sessions"), source_id),
        "creator_name": text(raw.get("creator_name"), source_id, 256),
        "custom_tags": tags_map({
            str(item.get("key")): item.get("value")
            for item in (pick(raw, "tags", "custom_tags") or []) if isinstance(item, dict) and item.get("key")
        } if isinstance(pick(raw, "tags", "custom_tags"), list) else None, source_id),
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


def read_runtime_catalog(reader, reference, inventory):
    """Supported runtime keys and metadata of the node types in use: end-of-support runtimes and deprecated VM families."""
    used = {c.get(k) for c in inventory.get("clusters", []) for k in ("node_type_id", "driver_node_type_id")}
    used |= {p.get("node_type_id") for p in inventory.get("instance_pools", [])}
    used |= {jc.get(k) for j in inventory.get("jobs", []) for jc in j.get("job_clusters", []) for k in ("node_type_id", "driver_node_type_id")}
    used.discard(None)

    def versions(item):
        rows = item.get("versions") if isinstance(item.get("versions"), list) else []
        return sorted({v["key"] for v in rows if isinstance(v, dict) and isinstance(v.get("key"), str) and len(v["key"]) <= 128})

    def node_types(item):
        rows = item.get("node_types") if isinstance(item.get("node_types"), list) else []
        out = {}
        for row in rows:
            node = row.get("node_type_id") if isinstance(row, dict) else None
            if node in used:
                cores = row.get("num_cores")
                out[node] = {
                    "is_deprecated": row.get("is_deprecated") is True,
                    "num_cores": cores if isinstance(cores, (int, float)) and not isinstance(cores, bool) and math.isfinite(cores) else None,
                    "photon_worker_capable": row.get("photon_worker_capable") is True,
                }
        return out

    spark, spark_receipt = read_one(reader, reader.origin + "/api/2.0/clusters/spark-versions", "dbx_spark_versions", reference, versions)
    nodes, node_receipt = read_one(reader, reader.origin + "/api/2.0/clusters/list-node-types", "dbx_node_types", reference, node_types)
    spark_receipt["records"] = len(spark or [])
    node_receipt["records"] = len(nodes or {})
    return {"spark_versions": spark, "node_types": nodes}, [spark_receipt, node_receipt]


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

            raw["dbx_runtime_catalog"], runtime_receipts = read_runtime_catalog(dbx, reference, raw["inventory"])
            raw["sources"].extend(runtime_receipts)

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
            for sid in ("dbx_workspace_conf", "dbx_clusters", "dbx_instance_pools", "dbx_cluster_policies", "dbx_jobs", "dbx_pipelines", "dbx_sql_warehouses", "dbx_spark_versions", "dbx_node_types", "dbx_secret_scopes", "dbx_init_scripts"):
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
            "Runtime table/column lineage (system.access.table_lineage, system.access.column_lineage) requires SQL Warehouse query execution and is never queried by this control-plane collector; DBU billing detail (system.billing.usage) is the separate opt-in source dbx_system_billing.",
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
        raw["dbx_cost_data"], dbx_cost_source = collect_databricks_costs(identity, config, reference, workspace, raw["inventory"])
        raw["sources"].append(dbx_cost_source)
        raw["system_billing"], billing_source = collect_system_billing(identity, config, reference, workspace)
        raw["sources"].append(billing_source)
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
        for child_id, field in referenced_resource_ids(res, res["id"].split("/")[2]):
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
        return outcome("not_applicable", "The confirmed requirement doesn't apply. " + reason, observed, sources)
    if value is True:
        return decision(True, reason + " Observed configuration; it doesn't prove runtime effectiveness.", observed, sources)
    if requirement is not True:
        return outcome("not_evaluated", "No owner-confirmed requirement or compensating control. " + reason, observed, sources)
    return decision(value, reason + " Requirement confirmed by the owner.", observed, sources)


def evaluate_workspace_rule(rule, raw, dep_graph):
    test, ws, inv = rule["test"], raw["workspace"], raw["inventory"]
    if test == "sku_premium":
        sku = (ws.get("sku_name") or ws.get("sku_tier") or "").lower()
        val = True if sku == "premium" else False if sku in ("standard", "trial") else None
        return conditional(val, expected(raw, "premium_required") if expected(raw, "premium_required") is not None else True,
                           "Observed ARM SKU of the workspace.", {"sku_name": ws.get("sku_name"), "sku_tier": ws.get("sku_tier")}, ["arm_workspace"])
    if test == "secure_cluster_connectivity":
        return decision(ws.get("enable_no_public_ip"), "enableNoPublicIp parameter observed in ARM.", {"enable_no_public_ip": ws.get("enable_no_public_ip")}, ["arm_workspace"])
    if test == "vnet_injection":
        vnet = ws.get("custom_virtual_network_id")
        vnet_val = True if vnet else (False if source_complete(raw, "arm_workspace") else None)
        return conditional(vnet_val, expected(raw, "vnet_injection_required") if expected(raw, "vnet_injection_required") is not None else True,
                           "customVirtualNetworkId parameter and host/container subnet injection.", {
                               "custom_virtual_network_id": vnet,
                               "custom_public_subnet_name": ws.get("custom_public_subnet_name"),
                               "custom_private_subnet_name": ws.get("custom_private_subnet_name"),
                           }, ["arm_workspace"])
    if test == "private_link_and_public_access":
        pna = ws.get("public_network_access")
        pes = ws.get("private_endpoint_connections", [])
        approved_pe = any(p.get("status") == "Approved" for p in pes)
        val = True if pna == "Disabled" or approved_pe else (False if pna == "Enabled" and not pes else None)
        return conditional(val, expected(raw, "private_link_required"), "publicNetworkAccess, requiredNsgRules and private endpoint configuration.", {
            "public_network_access": pna, "required_nsg_rules": ws.get("required_nsg_rules"), "private_endpoint_connections": pes,
        }, ["arm_workspace"])
    if test == "access_connector_and_storage_firewall":
        ac = ws.get("access_connector", {})
        has_ac = bool(ac.get("id")) and ac.get("identity_type") in ("SystemAssigned", "UserAssigned", "SystemAssigned,UserAssigned")
        return decision(True if has_ac else False if source_complete(raw, "arm_workspace") else None,
                        "Access connector linked to the workspace for managed identity.", {
                            "access_connector": ac, "default_storage_firewall": ws.get("default_storage_firewall"),
                        }, ["arm_workspace"])
    if test == "customer_managed_keys":
        cmk = ws.get("cmk", {})
        has_cmk = cmk.get("managed_services_key_source") == "Microsoft.Keyvault" and cmk.get("managed_disk_key_source") == "Microsoft.Keyvault"
        return conditional(has_cmk, expected(raw, "cmk_required"), "CMK encryption of managedServices and managedDisk.", cmk, ["arm_workspace"])
    if test == "enhanced_security_compliance":
        esc = ws.get("enhanced_security_compliance", {})
        enabled = esc.get("enhanced_security_monitoring") == "Enabled" or esc.get("compliance_security_profile") == "Enabled"
        return conditional(enabled, expected(raw, "enhanced_security_required"), "Observed enhancedSecurityCompliance profile.", esc, ["arm_workspace"])
    if test == "diagnostics":
        rows = raw.get("arm_diagnostics", [])
        enabled = any(log.get("enabled") is True for r in rows for log in r.get("logs", []))
        val = True if enabled else False if source_complete(raw, "arm_diagnostics") else None
        return decision(val, "Diagnostic settings enabled in ARM; actual ingestion needs separate verification.", {"diagnostic_settings": rows}, ["arm_diagnostics"])
    if test == "pat_token_governance":
        if not source_complete(raw, "dbx_workspace_conf") or not isinstance(raw.get("workspace_conf"), dict):
            return outcome("not_evaluated", "workspace-conf isn't available to review PAT token policies.", source_ids=["dbx_workspace_conf"])
        conf = raw["workspace_conf"]
        max_days = conf.get("maxTokenLifetimeDays")
        tokens_enabled = conf.get("enableTokensConfig")
        bounded = tokens_enabled == "false" or (max_days is not None and str(max_days).isdigit() and 0 < int(max_days) <= 90)
        return decision(bounded, "PAT token governance (enableTokensConfig and maxTokenLifetimeDays <= 90 days).", conf, ["dbx_workspace_conf"])
    if test == "default_catalog_unity":
        dtype = ws.get("default_catalog_type")
        has_uc = bool(inv.get("uc_metastore"))
        val = True if dtype == "UnityCatalog" or has_uc else (False if dtype == "HiveMetastore" else None)
        return decision(val, "Observed UnityCatalog default catalog or attached metastore.", {
            "default_catalog_type": dtype, "default_catalog_name": ws.get("default_catalog_name"),
            "uc_metastore_id": pick(inv.get("uc_metastore"), "id"),
        }, ["arm_workspace", "uc_metastore_summary"])
    if test == "global_init_scripts":
        if not source_complete(raw, "dbx_init_scripts"):
            return outcome("not_evaluated", "The global init script list isn't available.", source_ids=["dbx_init_scripts"])
        enabled = [s for s in inv.get("global_init_scripts", []) if s.get("enabled") is True]
        return decision(len(enabled) == 0, "Enabled global init scripts should be minimized and moved to policies or governed volumes.", {
            "total_scripts": len(inv.get("global_init_scripts", [])), "enabled_scripts": [s["name"] for s in enabled],
        }, ["dbx_init_scripts"])
    if test == "advisor":
        return decision(True if source_complete(raw, "arm_advisor") else None,
                        "Cached Azure Advisor recommendations read for the workspace.", {"recommendations_count": len(raw.get("advisor", []))}, ["arm_advisor"])
    if test == "uc_metastore_attached":
        if not source_complete(raw, "uc_metastore_summary"):
            return outcome("not_evaluated", "The Unity Catalog metastore summary isn't available.", source_ids=["uc_metastore_summary"])
        ms = inv.get("uc_metastore")
        return decision(bool(ms and ms.get("metastore_id")), "Unity Catalog metastore assignment confirmed.", {"metastore": ms}, ["uc_metastore_summary"])
    if test == "uc_storage_credential_mi":
        if not source_complete(raw, "uc_storage_credentials"):
            return outcome("not_evaluated", "Unity Catalog storage credentials aren't available.", source_ids=["uc_storage_credentials"])
        creds = inv.get("uc_storage_credentials", [])
        if not creds:
            return outcome("not_evaluated", "No storage credentials registered in Unity Catalog were observed.", source_ids=["uc_storage_credentials"])
        sp_creds = [c["name"] for c in creds if c.get("uses_service_principal") or not c.get("uses_managed_identity")]
        return decision(len(sp_creds) == 0, "All storage credentials use an Azure managed identity through an access connector.", {
            "total_credentials": len(creds), "non_managed_identity_credentials": sp_creds,
        }, ["uc_storage_credentials"])
    if test == "uc_external_locations_governed":
        if not source_complete(raw, "uc_external_locations", "uc_storage_credentials"):
            return outcome("not_evaluated", "External locations or storage credentials are incomplete.", source_ids=["uc_external_locations", "uc_storage_credentials"])
        locs = inv.get("uc_external_locations", [])
        if not locs:
            return outcome("not_evaluated", "No registered external locations were observed.", source_ids=["uc_external_locations"])
        known_creds = {c["name"] for c in inv.get("uc_storage_credentials", [])}
        if all(str(l.get("url") or "").lower().startswith("abfss://") for l in locs) and any(not l.get("credential_name") for l in locs) and not known_creds:
            return outcome(
                "not_evaluated",
                "External locations observed through the minimal BROWSE permission with abfss:// URIs, but credential_name and uc_storage_credentials are filtered by Unity Catalog ACLs.",
                {"total_external_locations": len(locs), "browse_only_projection": True},
                ["uc_external_locations", "uc_storage_credentials"],
            )
        ungoverned = [
            l["name"] for l in locs
            if not l.get("credential_name") or l["credential_name"] not in known_creds
            or not str(l.get("url") or "").lower().startswith("abfss://")
        ]
        return decision(len(ungoverned) == 0, "External locations linked to an existing storage credential with an abfss:// URI.", {
            "total_external_locations": len(locs), "non_compliant_locations": ungoverned,
        }, ["uc_external_locations", "uc_storage_credentials"])
    if test == "secret_scopes_keyvault":
        if not source_complete(raw, "dbx_secret_scopes"):
            return outcome("not_evaluated", "Secret scopes aren't available.", source_ids=["dbx_secret_scopes"])
        scopes = inv.get("secret_scopes", [])
        if not scopes:
            return outcome("not_evaluated", "No secret scopes were observed in the workspace.", source_ids=["dbx_secret_scopes"])
        dbx_backed = [s["name"] for s in scopes if s.get("backend_type") != "AZURE_KEYVAULT"]
        return decision(len(dbx_backed) == 0, "Secret scopes backed by Azure Key Vault (AZURE_KEYVAULT).", {
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
                "Confirmed broken internal references were found in complete job definitions (job_cluster_key or depends_on values that don't exist).",
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
                "Some dependency sources are incomplete, job or pipeline details are truncated, or references between objects are unverified (Databricks list APIs filter by ACL, so a missing external ID stays UNKNOWN instead of being declared broken).",
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
            "All dependency sources are complete, and every reference between job tasks, clusters, pools, policies, pipelines, warehouses and credentials resolves in the dependency map.",
            {
                "broken_references_count": 0,
                "unverified_references_count": 0,
            },
            list(dep_sources),
        )
    if test == "runtime_table_lineage":
        return outcome(
            "not_evaluated",
            "Runtime table and column lineage (system.access.table_lineage / column_lineage) needs queries on a running SQL warehouse; this control-plane collector neither runs nor simulates them.",
            {"system_tables_queried": False},
            ["uc_system_lineage"],
        )
    if test == "lakehouse_federation_connections":
        if not source_complete(raw, "uc_connections"):
            return outcome("not_evaluated", "Lakehouse Federation connections aren't available.", source_ids=["uc_connections"])
        conns = inv.get("uc_connections", [])
        if not conns:
            return outcome("not_applicable", "No external Lakehouse Federation connections are registered in the metastore.", {"connections_count": 0}, ["uc_connections"])
        return decision(True, "External Lakehouse Federation connections inventoried in the dependency map.", {
            "connections": [{"name": c["name"], "type": c.get("connection_type"), "host": c.get("host")} for c in conns],
        }, ["uc_connections"])
    if test == "outbound_control_plane_endpoints":
        if not source_complete(raw, "arm_outbound_endpoints"):
            return outcome("not_evaluated", "The official outboundNetworkDependenciesEndpoints list isn't available.", source_ids=["arm_outbound_endpoints"])
        eps = inv.get("outbound_endpoints", [])
        return decision(bool(eps), "Outbound network dependencies to the control plane inventoried from ARM.", {
            "categories": [e["category"] for e in eps], "count": len(eps),
        }, ["arm_outbound_endpoints"])
    if test == "cost_attribution":
        head = (raw.get("databricks_cost_model") or {}).get("headline") or {}
        gap, first = head.get("unattributed_share"), head.get("first_tag")
        if gap is not None and first and first.get("tagged_share") is not None:
            return decision(
                gap <= 10 and first["tagged_share"] >= 80,
                "Databricks cost attribution by tags in Cost Management: at most 10% without a compute tag and at least 80% with the main allocation tag.",
                {"month": head.get("review_month"), "unattributed_share": gap, "allocation_tag": first["tag"], "tagged_share": first["tagged_share"]},
                ["azure_cost_databricks"],
            )
        return outcome(
            "not_evaluated",
            "No Cost Management data for Databricks (cost analysis off, read denied or no usage): the share of cost that tags explain can't be measured.",
            {"cost_status": (raw.get("databricks_cost_model") or {}).get("status")},
            ["azure_cost_databricks"],
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
                return outcome("not_applicable", "Ephemeral job cluster: it ends automatically when the task finishes.", {"cluster_source": row.get("cluster_source")}, [row["source_id"]])
            mins = row.get("autotermination_minutes")
            val = True if isinstance(mins, (int, float)) and 0 < mins <= 60 else False
            return decision(val, "Auto-termination of 60 minutes or less on the all-purpose cluster.", {"autotermination_minutes": mins}, [row["source_id"]])
        if test == "cluster_policy_bound":
            return decision(bool(row.get("policy_id")), "policy_id association observed on the cluster.", {"policy_id": row.get("policy_id")}, [row["source_id"]])
        if test == "cluster_access_mode":
            mode = (row.get("data_security_mode") or "").upper()
            val = True if mode in ("USER_ISOLATION", "SINGLE_USER", "SHARED") else False if mode in ("NONE", "LEGACY_PASSTHROUGH", "LEGACY_TABLE_ACL", "LEGACY_SINGLE_USER", "") else None
            return decision(val, "data_security_mode access mode compatible with Unity Catalog and isolation.", {"data_security_mode": row.get("data_security_mode")}, [row["source_id"]])
        if test == "cluster_runtime_lts":
            sv = row.get("spark_version") or ""
            match = re.match(r"^(\d+)\.(\d+)", sv)
            major = int(match.group(1)) if match else None
            is_lts = "lts" in sv.lower()
            val = True if major is not None and major >= 13 and is_lts else False if major is not None else None
            return decision(val, "Databricks Runtime LTS >= 13.x observed.", {"spark_version": sv}, [row["source_id"]])
        if test == "cluster_autoscaling_or_pool":
            has_auto = bool(row.get("autoscale")) or bool(row.get("instance_pool_id"))
            return decision(has_auto, "Autoscale or instance pool binding observed on the cluster.", {
                "autoscale": row.get("autoscale"), "instance_pool_id": row.get("instance_pool_id"), "num_workers": row.get("num_workers"),
            }, [row["source_id"]])

    if test in ("job_uses_job_compute", "job_resilience_settings", "job_service_principal_run_as"):
        if kind != "Job":
            return None
        tasks = row.get("tasks", [])
        if test == "job_uses_job_compute":
            all_purpose_tasks = [t["task_key"] for t in tasks if t.get("existing_cluster_id")]
            return decision(len(all_purpose_tasks) == 0, "Job tasks use job compute, serverless, a SQL warehouse or a pipeline instead of an all-purpose existing_cluster_id.", {
                "tasks_total": len(tasks), "tasks_on_all_purpose_cluster": all_purpose_tasks,
            }, [row["source_id"]])
        if test == "job_resilience_settings":
            has_timeout = bool(row.get("timeout_seconds")) or (bool(tasks) and all(bool(t.get("timeout_seconds")) for t in tasks))
            has_notif = row.get("has_notifications") is True
            return decision(has_timeout and has_notif, "Job configured with timeout_seconds and failure/alert notifications.", {
                "job_timeout_seconds": row.get("timeout_seconds"), "has_notifications": has_notif,
            }, [row["source_id"]])
        if test == "job_service_principal_run_as":
            sp = row.get("run_as_service_principal")
            user = row.get("run_as_user_name")
            val = True if sp else False if user else None
            return decision(val, "Job run_as identity assigned to a service principal.", {
                "run_as_service_principal": sp, "run_as_user_name": user,
            }, [row["source_id"]])

    if test == "sql_warehouse_autostop":
        if kind != "SqlWarehouse":
            return None
        mins = row.get("auto_stop_mins")
        serverless = row.get("enable_serverless_compute") is True or (row.get("warehouse_type") or "").upper() == "PRO"
        val = True if isinstance(mins, (int, float)) and 0 < mins <= 30 and serverless else False
        return decision(val, "SQL warehouse with auto_stop_mins <= 30 minutes and serverless/pro mode.", {
            "auto_stop_mins": mins, "enable_serverless_compute": row.get("enable_serverless_compute"), "warehouse_type": row.get("warehouse_type"),
        }, [row["source_id"]])

    if test == "pipeline_unity_catalog":
        if kind != "LakeflowPipeline":
            return None
        if row.get("detail_collected") is False:
            return outcome(
                "not_evaluated",
                "The pipeline spec detail (/api/2.0/pipelines/{id}) wasn't available; the summary list doesn't include catalog/schema.",
                {"pipeline_id": row.get("id"), "detail_collected": False},
                [row.get("detail_source_id") or row["source_id"]],
            )
        cat = row.get("catalog")
        val = True if cat and cat.lower() not in ("hive_metastore", "") else False
        return decision(val, "Declarative pipeline configured with a target catalog in Unity Catalog.", {
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
        return decision(val, "HTTPS required, TLS >= 1.2 and allowBlobPublicAccess=false on the associated storage account.", cfg, [row["source_id"]])
    if test == "storage_shared_key_and_network":
        if rkind != "microsoft.storage/storageaccounts":
            return None
        shared = cfg.get("allowSharedKeyAccess")
        pna = cfg.get("publicNetworkAccess")
        if row.get("name", "").lower() == (raw["workspace"].get("dbfs_storage_account_name") or "").lower():
            return outcome("not_applicable", "DBFS root account managed by the Azure Databricks platform.", cfg, [row["source_id"]])
        val = True if shared is False and pna == "Disabled" else False if shared is True or pna == "Enabled" else None
        return conditional(val, expected(raw, "shared_key_disabled_required") if expected(raw, "shared_key_disabled_required") is not None else True,
                           "Shared key and public access on the associated ADLS Gen2 account.", cfg, [row["source_id"]])
    if test == "keyvault_rbac_and_purge":
        if rkind != "microsoft.keyvault/vaults":
            return None
        rbac = cfg.get("enableRbacAuthorization")
        purge = cfg.get("enablePurgeProtection")
        val = True if rbac is True and purge is True else False if rbac is False or purge is False else None
        return decision(val, "Associated key vault with Azure RBAC and purge protection enabled.", cfg, [row["source_id"]])
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
        return decision(len(exposed) == 0, "Inbound Allow rules from the internet to administrative ports on the associated NSG.", {
            "exposed_rules": exposed, "total_rules": len(rules),
        }, [row["source_id"]])
    if test == "private_endpoint_approved":
        if rkind != "microsoft.network/privateendpoints":
            return None
        conns = row.get("connections", [])
        val = True if conns and all(c.get("status") == "Approved" for c in conns) else False if conns else None
        return decision(val, "Approval state of the associated private endpoint connections.", {"connections": conns}, [row["source_id"]])
    return None


def make_check(rule, target_id, target_name, workload_name, evaluation, reference, ws):
    status = evaluation["status"]
    cid = rule["rule_id"] + "-" + hashlib.sha256((ws["id"].lower() + "|" + rule["rule_id"] + "|" + str(target_id)).encode("utf-8")).hexdigest()[:10]
    sev_labels = {"critical": "Critical", "high": "High", "medium": "Medium", "low": "Low"}
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
                    "No applicable workload objects were observed, or the workspace REST source wasn't available; absence isn't compliance.",
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
                    "No associated ARM resources of this type were collected in the approved scope; no absence of risk is assumed.",
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
                    "title": "Review auto-termination on the interactive all-purpose cluster",
                    "resource_id": ws["id"] + "/clusters/" + cl["id"],
                    "workload_name": cl["name"],
                    "source_id": cl["source_id"],
                    "basis": "autotermination_minutes configuration observed in /api/2.0/clusters/list; DBU savings not estimated.",
                    "value": mins if mins is not None else "disabled",
                    "unit": "minutes",
                    "sample_count": 1,
                    "window": None,
                    "recommendation": "Set autotermination_minutes (<= 60 min) and apply a cluster policy to limit idle consumption.",
                    "estimated_savings": None,
                })
    for job in inv.get("jobs", []):
        ap_tasks = [t["task_key"] for t in job.get("tasks", []) if t.get("existing_cluster_id")]
        if ap_tasks:
            candidates.append({
                "id": "FINOPS-JOB-" + hashlib.sha256(job["id"].encode("utf-8")).hexdigest()[:10],
                "title": "Review job tasks running on an all-purpose cluster",
                "resource_id": ws["id"] + "/jobs/" + job["id"],
                "workload_name": job["name"],
                "source_id": job["source_id"],
                "basis": "Tasks with existing_cluster_id observed in /api/2.1/jobs/list; the job compute/serverless DBU rate is lower than all-purpose.",
                "value": len(ap_tasks),
                "unit": "tasks_on_all_purpose",
                "sample_count": 1,
                "window": None,
                "recommendation": "Evaluate moving the tasks to job_cluster_key or serverless jobs after validating library and init script dependencies.",
                "estimated_savings": None,
            })
    for wh in inv.get("sql_warehouses", []):
        mins = wh.get("auto_stop_mins")
        if not isinstance(mins, (int, float)) or mins <= 0 or mins > 30:
            candidates.append({
                "id": "FINOPS-WH-" + hashlib.sha256(wh["id"].encode("utf-8")).hexdigest()[:10],
                "title": "Review auto_stop_mins on the SQL warehouse",
                "resource_id": ws["id"] + "/warehouses/" + wh["id"],
                "workload_name": wh["name"],
                "source_id": wh["source_id"],
                "basis": "auto_stop_mins configuration observed in /api/2.0/sql/warehouses; no monetary savings projected.",
                "value": mins if mins is not None else "disabled",
                "unit": "minutes",
                "sample_count": 1,
                "window": None,
                "recommendation": "Set auto_stop_mins <= 30 min or evaluate a serverless SQL warehouse.",
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
            "These ActualCost rows come only from cost_scope (approved ARM ResourceIds) and are not split by job, notebook or user; the Databricks cost section attributes DBU and infrastructure by Databricks tags.",
            "System table system.billing.usage is queried only when system_tables_warehouse_id is configured (off by default, it consumes DBUs).",
            "Savings on these legacy rows are not computed; the Databricks cost section estimates savings only from observed cost with documented rules.",
        ],
    }


# ---------------------------------------------------------------------------------------------------------------
# Databricks costs: where they come from (Cost Management grouped by Databricks tags) and how to optimise them
# (Databricks REST configuration joined to the observed cost). Optional, off by default: system tables.
# ---------------------------------------------------------------------------------------------------------------

SYSTEM_BILLING_STATEMENT = (
    "WITH u AS (SELECT u.billing_origin_product AS product, u.sku_name AS sku, u.usage_metadata.cluster_id AS cluster_id, "
    "u.usage_metadata.job_id AS job_id, u.usage_metadata.job_run_id AS job_run_id, u.usage_metadata.warehouse_id AS warehouse_id, "
    "u.usage_metadata.dlt_pipeline_id AS pipeline_id, u.identity_metadata.run_as AS run_as, CAST(u.usage_quantity AS DOUBLE) AS dbus, "
    "CAST(u.usage_quantity * lp.pricing.effective_list.default AS DOUBLE) AS list_cost, lp.currency_code AS currency "
    "FROM system.billing.usage u LEFT JOIN system.billing.list_prices lp ON lp.sku_name = u.sku_name AND lp.cloud = u.cloud "
    "AND lp.usage_unit = u.usage_unit AND u.usage_end_time >= lp.price_start_time "
    "AND (lp.price_end_time IS NULL OR u.usage_end_time < lp.price_end_time) "
    "WHERE u.workspace_id = :workspace_id AND u.usage_date >= :start_date AND u.usage_date < :end_date AND u.usage_unit = 'DBU'), "
    "runs AS (SELECT 'run' AS row_type, product, sku, cluster_id, job_id, job_run_id, warehouse_id, pipeline_id, run_as, "
    "SUM(dbus) AS dbus, SUM(list_cost) AS list_cost, MAX(currency) AS currency FROM u "
    "GROUP BY product, sku, cluster_id, job_id, job_run_id, warehouse_id, pipeline_id, run_as ORDER BY list_cost DESC NULLS LAST LIMIT 300), "
    "users AS (SELECT 'user' AS row_type, CAST(NULL AS STRING) AS product, CAST(NULL AS STRING) AS sku, CAST(NULL AS STRING) AS cluster_id, "
    "CAST(NULL AS STRING) AS job_id, CAST(NULL AS STRING) AS job_run_id, CAST(NULL AS STRING) AS warehouse_id, CAST(NULL AS STRING) AS pipeline_id, "
    "run_as, SUM(dbus) AS dbus, SUM(list_cost) AS list_cost, MAX(currency) AS currency FROM u GROUP BY run_as "
    "ORDER BY list_cost DESC NULLS LAST LIMIT 100), "
    "products AS (SELECT 'product' AS row_type, product, sku, CAST(NULL AS STRING) AS cluster_id, CAST(NULL AS STRING) AS job_id, "
    "CAST(NULL AS STRING) AS job_run_id, CAST(NULL AS STRING) AS warehouse_id, CAST(NULL AS STRING) AS pipeline_id, CAST(NULL AS STRING) AS run_as, "
    "SUM(dbus) AS dbus, SUM(list_cost) AS list_cost, MAX(currency) AS currency FROM u GROUP BY product, sku) "
    "SELECT * FROM runs UNION ALL SELECT * FROM users UNION ALL SELECT * FROM products"
)
COST_LEARN = {
    "autotermination": "https://learn.microsoft.com/azure/databricks/compute/clusters-manage#automatic-termination",
    "jobs_compute": "https://learn.microsoft.com/azure/databricks/jobs/compute",
    "spot": "https://learn.microsoft.com/azure/databricks/compute/configure#spot-instances",
    "policies": "https://learn.microsoft.com/azure/databricks/admin/clusters/policies",
    "tags": "https://learn.microsoft.com/azure/databricks/admin/account-settings/usage-detail-tags",
    "runtime": "https://learn.microsoft.com/azure/databricks/release-notes/runtime/",
    "node_types": "https://learn.microsoft.com/azure/databricks/compute/cluster-config-best-practices",
    "pools": "https://learn.microsoft.com/azure/databricks/compute/pool-best-practices",
    "warehouse": "https://learn.microsoft.com/azure/databricks/compute/sql-warehouse/create",
    "photon": "https://learn.microsoft.com/azure/databricks/compute/photon",
    "streaming": "https://learn.microsoft.com/azure/databricks/jobs/continuous",
    "billing": "https://learn.microsoft.com/azure/databricks/admin/system-tables/billing",
    "cost_best_practices": "https://learn.microsoft.com/azure/databricks/lakehouse-architecture/cost-optimization/best-practices",
}
AP_SOURCES_EXCLUDED = ("JOB", "PIPELINE", "PIPELINE_MAINTENANCE", "SQL", "MODELS")
OLD_NODE_RE = re.compile(r"^Standard_(?:DS?\d+[a-z]*_v[23]|DS?\d+|F\d+s?|L\d+s|E\d+[a-z]*_v3|NC\d+[a-z]*(?:_v2)?|NV\d+[a-z]*)$", re.IGNORECASE)


def _month_start(day):
    return day.replace(day=1)


def cost_periods(reference):
    today = datetime.fromisoformat(reference.replace("Z", "+00:00")).date()
    current = _month_start(today)
    review_end = current - timedelta(days=1)
    review = _month_start(review_end)
    previous = _month_start(review - timedelta(days=1))
    weekend = sum((review + timedelta(days=i)).weekday() >= 5 for i in range(review_end.day))
    return {
        "today": today, "current_start": current, "review_start": review, "review_end": review_end, "previous_start": previous,
        "labels": {
            "current": current.strftime("%Y-%m"), "review": review.strftime("%Y-%m"), "previous": previous.strftime("%Y-%m"),
            "review_days": review_end.day, "review_weekend_days": weekend, "mtd_days": today.day,
            "current_month_days": ((current + timedelta(days=32)).replace(day=1) - timedelta(days=1)).day,
        },
    }


def cost_query_body(start, end, granularity, grouping, scope_filter, extra=None):
    return {
        "type": COST_METRIC,
        "timeframe": "Custom",
        "timePeriod": {"from": start.isoformat() + "T00:00:00Z", "to": end.isoformat() + "T23:59:59Z"},
        "dataset": {
            "granularity": granularity,
            "aggregation": {"totalCost": {"name": "Cost", "function": "Sum"}},
            "grouping": grouping,
            "filter": scope_filter if extra is None else {"and": [scope_filter, extra]},
        },
    }


def parse_cost_payload(payload, source):
    props = obj(obj(payload, source).get("properties"), source)
    columns = [text(column.get("name"), source, 128) for column in array(props.get("columns"), source)]
    index = {name: i for i, name in enumerate(columns)}
    amount_column = next((name for name in ("Cost", "PreTaxCost", "CostUSD") if name in index), None)
    rows = props.get("rows")
    if amount_column is None or "Currency" not in index or not isinstance(rows, list):
        raise EvidenceError("invalid_cost_shape", "Cost Management returned no amount/currency columns.", source)
    parsed = []
    for row in rows:
        if not isinstance(row, list) or len(row) != len(columns):
            raise EvidenceError("invalid_cost_shape", "Cost row/column lengths differ.", source)
        amount = row[index[amount_column]]
        if isinstance(amount, bool) or not isinstance(amount, (int, float)) or not math.isfinite(amount):
            raise EvidenceError("invalid_cost_amount", "Cost amount is absent or not finite; it is not zero.", source)
        if "BillingMonth" in index:
            period = str(row[index["BillingMonth"]])[:7]
        elif "UsageDate" in index:
            raw_day = str(row[index["UsageDate"]])
            period = raw_day[:4] + "-" + raw_day[4:6] + "-" + raw_day[6:8] if re.fullmatch(r"[0-9]{8}", raw_day) else raw_day[:10]
        else:
            period = None
        key = row[index["TagValue"]] if "TagValue" in index else None
        key = text(str(key), source, 512) if key not in (None, "") else None
        category = text(str(row[index["MeterCategory"]]), source, 256) if "MeterCategory" in index and row[index["MeterCategory"]] is not None else None
        meter = text(str(row[index["Meter"]]), source, 256) if "Meter" in index and row[index["Meter"]] is not None else None
        currency = text(str(row[index["Currency"]]), source, 8)
        parsed.append([period, key, category, meter, round(float(amount), 6), currency])
    return parsed, props.get("nextLink")


def ap_clusters(inventory):
    return [
        c for c in inventory.get("clusters", [])
        if c.get("kind") == "AllPurposeCluster" and (c.get("cluster_source") or "UI").upper() not in AP_SOURCES_EXCLUDED
    ]


def cost_query_plan(periods, scope_filter, inventory):
    review, review_end, previous = periods["review_start"], periods["review_end"], periods["previous_start"]
    by_meter = [{"type": "Dimension", "name": "MeterCategory"}]
    plan = [
        ("meter", cost_query_body(previous, periods["today"], "Monthly", by_meter + [{"type": "Dimension", "name": "Meter"}], scope_filter)),
        ("vendor", cost_query_body(previous, review_end, "Monthly", [{"type": "TagKey", "name": "Vendor"}] + by_meter, scope_filter)),
    ]
    for dimension, tag in COST_DIMENSIONS:
        plan.append((dimension, cost_query_body(previous, review_end, "Monthly", [{"type": "TagKey", "name": tag}] + by_meter, scope_filter)))
    for tag in COST_ALLOCATION_TAGS:
        plan.append(("tag:" + tag, cost_query_body(previous, review_end, "Monthly", [{"type": "TagKey", "name": tag}] + by_meter, scope_filter)))
    names = sorted({c["name"] for c in ap_clusters(inventory) if c.get("name")})[:MAX_COST_DAILY_KEYS]
    if names:
        plan.append(("daily_cluster", cost_query_body(review, review_end, "Daily", [{"type": "TagKey", "name": "ClusterName"}], scope_filter,
                                                      {"tags": {"name": "ClusterName", "operator": "In", "values": names}})))
    pools = sorted({p["id"] for p in inventory.get("instance_pools", []) if (p.get("min_idle_instances") or 0) > 0})[:MAX_COST_DAILY_KEYS]
    if pools:
        plan.append(("daily_pool", cost_query_body(review, review_end, "Daily", [{"type": "TagKey", "name": "DatabricksInstancePoolId"}], scope_filter,
                                                   {"tags": {"name": "DatabricksInstancePoolId", "operator": "In", "values": pools}})))
    return plan


def collect_databricks_costs(identity, config, reference, workspace, inventory):
    periods = cost_periods(reference)
    labels = periods["labels"]
    receipt = source_receipt(
        "azure_cost_databricks", reference, "not_configured",
        "Databricks cost analysis is disabled in configuration (cost_analysis_enabled=False).",
        window={"start": periods["previous_start"].isoformat() + "T00:00:00Z", "end": reference},
        metric=COST_METRIC, queries=[], pagination_complete=False,
    )
    if not config.get("cost_analysis_enabled", True):
        return None, receipt
    url = ARM_ORIGIN + "/subscriptions/" + SUBSCRIPTION_ID + "/providers/Microsoft.CostManagement/query?api-version=" + COST_API_VERSION
    reader = HttpReader(identity, ARM_ORIGIN, "arm", patient=True)
    reader.allow(url, "POST")
    resource_ids = [config["id"].lower()] + [rid.lower() for rid in config.get("approved_cost_resource_ids", []) if rid.lower() != config["id"].lower()]
    managed_rg = workspace.get("managed_resource_group") if isinstance(workspace, dict) else None
    parts = [{"dimensions": {"name": "ResourceId", "operator": "In", "values": resource_ids}}]
    if managed_rg:
        parts.append({"dimensions": {"name": "ResourceGroupName", "operator": "In", "values": [managed_rg.lower()]}})
    scope_filter = parts[0] if len(parts) == 1 else {"or": parts}
    data = {
        "metric": COST_METRIC, "periods": labels, "queries": {},
        "scope": {"subscription_id": SUBSCRIPTION_ID, "resource_ids": resource_ids, "managed_resource_group": managed_rg},
    }
    for qid, body in cost_query_plan(periods, scope_filter, inventory):
        started, rows, pages, error, status = time.monotonic(), [], 0, None, "complete"
        if identity.deadline - started < COST_QUERY_RESERVE_SECONDS:
            error = EvidenceError("collection_deadline", "Collection time bound reached before this cost query; it is missing, not zero.", "azure_cost_databricks").public()
            data["queries"][qid] = {"status": "skipped", "rows": [], "pages": 0, "seconds": 0.0, "error": error}
            continue
        current, seen = url, set()
        try:
            while True:
                if current in seen:
                    raise EvidenceError("pagination_loop", "Cost query repeated a continuation.", "azure_cost_databricks")
                seen.add(current)
                payload = reader.request("POST", current, "azure_cost_databricks", body=body)
                pages += 1
                parsed, link = parse_cost_payload(payload, "azure_cost_databricks")
                rows.extend(parsed)
                if len(rows) > MAX_COST_ROWS:
                    raise EvidenceError("row_cap", "Cost rows exceeded the safety bound; the query is partial.", "azure_cost_databricks")
                if not link:
                    break
                if pages >= MAX_PAGES:
                    raise EvidenceError("page_cap", "Cost query page safety cap reached.", "azure_cost_databricks")
                current = next_arm_link(link, url)
        except (EvidenceError, ValueError) as exc:
            failure = exc if isinstance(exc, EvidenceError) else EvidenceError("invalid_cost_shape", "Cost data could not be parsed.", "azure_cost_databricks")
            error = failure.public()
            status = "partial" if rows else "denied" if failure.http_status in (401, 403) else "error"
        data["queries"][qid] = {"status": status, "rows": rows, "pages": pages, "seconds": round(time.monotonic() - started, 1), "error": error}
    statuses = [q["status"] for q in data["queries"].values()]
    overall = (
        "complete" if all(s == "complete" for s in statuses)
        else "partial" if any(s in ("complete", "partial") for s in statuses)
        else "denied" if statuses and statuses[0] == "denied"
        else "error"
    )
    receipt.update(
        status=overall,
        records=sum(len(q["rows"]) for q in data["queries"].values()),
        pages=sum(q["pages"] for q in data["queries"].values()),
        pagination_complete=overall == "complete",
        scope="/subscriptions/" + SUBSCRIPTION_ID,
        read_signature="POST " + url,
        queries=[{"id": qid, "status": q["status"], "records": len(q["rows"]), "seconds": q["seconds"]} for qid, q in data["queries"].items()],
        errors=[q["error"] for q in data["queries"].values() if q["error"]][:3],
        note=(
            "Cost Management grouped by Databricks tags (ClusterName, JobId, SqlEndpointId, DatabricksInstancePoolId, Vendor and "
            + (", ".join(COST_ALLOCATION_TAGS) or "no allocation tags") + ") for the workspace resource and its managed resource group."
            if overall != "denied" else
            "The identity cannot read cost: grant Cost Management Reader (or Reader) on the subscription."
        ),
    )
    return data, receipt


def collect_system_billing(identity, config, reference, workspace):
    periods = cost_periods(reference)
    receipt = source_receipt(
        "dbx_system_billing", reference, "not_configured",
        "Off by default: system.billing.usage + list_prices through the Statement Execution API on an existing SQL warehouse "
        "(it consumes DBUs). Set system_tables_warehouse_id to enable per-run and per-user detail.",
    )
    warehouse = config.get("system_tables_warehouse_id") or ""
    if not warehouse or not config["workspace_api_enabled"]:
        return None, receipt
    workspace_number = (workspace or {}).get("workspace_guid") or ""
    if not re.fullmatch(r"[0-9]{6,24}", str(workspace_number)):
        match = re.match(r"adb-([0-9]{6,24})\.", config["workspace_host"])
        workspace_number = match.group(1) if match else ""
    if not workspace_number:
        receipt.update(status="error", errors=[EvidenceError("workspace_id_unknown", "The numeric workspace ID is unknown; system tables were not queried.", "dbx_system_billing").public()])
        return None, receipt
    reader = StatementReader(identity, "https://" + config["workspace_host"])
    url = reader.allow(reader.origin + StatementReader.PATH, "POST")
    body = {
        "warehouse_id": warehouse, "statement": SYSTEM_BILLING_STATEMENT, "wait_timeout": "50s", "on_wait_timeout": "CANCEL",
        "disposition": "INLINE", "format": "JSON_ARRAY",
        "parameters": [
            {"name": "workspace_id", "value": str(workspace_number), "type": "STRING"},
            {"name": "start_date", "value": periods["review_start"].isoformat(), "type": "DATE"},
            {"name": "end_date", "value": periods["current_start"].isoformat(), "type": "DATE"},
        ],
    }
    receipt.update(read_signature="POST " + url, warehouse_id=warehouse, window={"start": periods["review_start"].isoformat(), "end": periods["current_start"].isoformat()})
    try:
        payload = obj(reader.request("POST", url, "dbx_system_billing", body=body), "dbx_system_billing")
        state = pick(payload, "status", "state")
        if state != "SUCCEEDED":
            message = text(pick(payload, "status", "error", "message"), "dbx_system_billing", 400) or ""
            raise EvidenceError("statement_" + str(state or "unknown").lower(), ("Statement state " + str(state) + ". " + message).strip(), "dbx_system_billing")
        columns = [text(c.get("name"), "dbx_system_billing", 64) for c in array(pick(payload, "manifest", "schema", "columns") or [], "dbx_system_billing")]
        data_rows = pick(payload, "result", "data_array") or []
        if not isinstance(data_rows, list):
            raise EvidenceError("invalid_shape", "Statement result is not an array.", "dbx_system_billing")
        rows = []
        for item in data_rows[:600]:
            if not isinstance(item, list) or len(item) != len(columns):
                raise EvidenceError("invalid_shape", "Statement row/column lengths differ.", "dbx_system_billing")
            record = {}
            for name, value in zip(columns, item):
                if name in ("dbus", "list_cost"):
                    try:
                        record[name] = round(float(value), 4) if value not in (None, "") else None
                    except (TypeError, ValueError):
                        record[name] = None
                else:
                    record[name] = text(str(value), "dbx_system_billing", 256) if value is not None else None
            rows.append(record)
        receipt.update(status="complete", records=len(rows), pages=1, truncated=bool(pick(payload, "manifest", "truncated")))
        return {"warehouse_id": warehouse, "window": receipt["window"], "rows": rows, "truncated": receipt["truncated"]}, receipt
    except EvidenceError as exc:
        receipt.update(status="denied" if exc.http_status in (401, 403) else "error", errors=[exc.public()])
        return None, receipt


def dbu_family(meter):
    m = (meter or "").lower()
    for family, words in (
        ("sql_serverless", ("serverless sql",)), ("sql", ("sql",)), ("pipelines", ("dlt", "delta live", "pipeline")),
        ("jobs_light", ("jobs light",)), ("serverless", ("serverless",)), ("jobs", ("jobs", "automated")),
        ("all_purpose", ("all-purpose", "all purpose", "interactive")), ("ai", ("serving", "inference", "vector", "model", "foundation")),
    ):
        if any(word in m for word in words):
            return family
    return "other"


def _money(value):
    return round(value, 2) if isinstance(value, (int, float)) else None


def en_amount(value, decimals=0):
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return "—"
    return format(round(value, decimals), "," + "." + str(decimals) + "f")


def en_month(label):
    names = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December")
    match = re.fullmatch(r"(\d{4})-(\d{2})", str(label or ""))
    return names[int(match.group(2)) - 1] + " " + match.group(1) if match and 1 <= int(match.group(2)) <= 12 else str(label)


def _pct(part, whole):
    return round(100.0 * part / whole, 1) if isinstance(part, (int, float)) and isinstance(whole, (int, float)) and whole > 0 else None


def _vm_meter(node_type):
    return (node_type or "").replace("Standard_", "").replace("_", " ").lower()


def cost_tables(data, labels):
    """Aggregate every Cost Management query result in the dominant billing currency."""
    queries = data.get("queries", {})
    totals = {}
    for q in queries.values():
        for period, key, category, meter, amount, currency in q["rows"]:
            totals[currency] = totals.get(currency, 0.0) + abs(amount)
    currency = max(totals, key=totals.get) if totals else None
    review, previous, current = labels["review"], labels["previous"], labels["current"]
    rows = {qid: [r for r in q["rows"] if r[5] == currency] for qid, q in queries.items()}
    is_dbu = lambda category: (category or "").lower() == "azure databricks"

    def by_key(qid):
        out = {}
        for period, key, category, meter, amount, _ in rows.get(qid, []):
            slot = out.setdefault(key, {"dbu": 0.0, "infra": 0.0, "vm": 0.0, "review": 0.0, "previous": 0.0, "categories": {}})
            if period == review:
                slot["review"] += amount
                slot["dbu" if is_dbu(category) else "infra"] += amount
                if (category or "").lower() == "virtual machines":
                    slot["vm"] += amount
                slot["categories"][category or "—"] = slot["categories"].get(category or "—", 0.0) + amount
            elif period == previous:
                slot["previous"] += amount
        return out

    months = {label: {"dbu": 0.0, "infra": 0.0} for label in (previous, review, current)}
    families, categories, vm_sizes = {}, {}, {}
    for period, _, category, meter, amount, _ in rows.get("meter", []):
        if period not in months:
            continue
        months[period]["dbu" if is_dbu(category) else "infra"] += amount
        if is_dbu(category):
            slot = families.setdefault(dbu_family(meter), {"review": 0.0, "previous": 0.0, "meters": {}})
            if period in (review, previous):
                slot[period == review and "review" or "previous"] += amount
            if period == review:
                slot["meters"][meter or "—"] = slot["meters"].get(meter or "—", 0.0) + amount
        else:
            slot = categories.setdefault(category or "—", {"review": 0.0, "previous": 0.0})
            if period in (review, previous):
                slot[period == review and "review" or "previous"] += amount
            if period == review and (category or "").lower() == "virtual machines":
                vm_sizes[meter or "—"] = vm_sizes.get(meter or "—", 0.0) + amount
    daily = {}
    for qid in ("daily_cluster", "daily_pool"):
        per_key = {}
        for period, key, _, _, amount, _ in rows.get(qid, []):
            if key is None or not period or len(period) != 10:
                continue
            day = per_key.setdefault(key, {})
            day[period] = day.get(period, 0.0) + amount
        daily[qid] = per_key
    return {
        "currency": currency,
        "other_currencies": sorted(c for c in totals if c != currency),
        "months": months, "families": families, "categories": categories, "vm_sizes": vm_sizes, "daily": daily,
        "dimensions": {qid: by_key(qid) for qid in queries if qid not in ("meter", "daily_cluster", "daily_pool")},
        "query_status": {qid: q["status"] for qid, q in queries.items()},
    }


def daily_profile(days, labels, start):
    if not days:
        return None
    weekend = sum(v for d, v in days.items() if datetime.strptime(d, "%Y-%m-%d").weekday() >= 5)
    active = [v for v in days.values() if v > 0.01]
    floor = min(days.get((start + timedelta(days=i)).isoformat(), 0.0) for i in range(labels["review_days"]))
    return {"active_days": len(active), "weekend_cost": round(weekend, 2), "floor": round(max(floor, 0.0), 2), "total": round(sum(days.values()), 2)}


def cost_signals(inventory, catalog, tables, labels, periods, reference):
    """Optimisation signals from observed configuration, each with the observed cost of its object and, where the
    cost data allows it, an estimated monthly saving with a documented rule."""
    dims = tables["dimensions"] if tables else {}
    clusters_cost, jobs_cost = dims.get("cluster", {}), dims.get("job", {})
    pools_cost, warehouses_cost = dims.get("pool", {}), dims.get("warehouse", {})
    daily = tables["daily"] if tables else {}
    ref_ms = datetime.fromisoformat(reference.replace("Z", "+00:00")).timestamp() * 1000
    tags_wanted = [t.lower() for t in COST_ALLOCATION_TAGS]
    weekend_share = labels["review_weekend_days"] / max(1, labels["review_days"])
    signals = []

    def add(code, severity, title, kind, oid, name, evidence, cost, saving, saving_kind, basis, recommendation, learn, effort="L"):
        signals.append({
            "id": "COST-" + code + "-" + hashlib.sha256((kind + "|" + str(oid)).encode("utf-8")).hexdigest()[:10],
            "code": code, "severity": severity, "title": title, "object_kind": kind, "object_id": str(oid), "object_name": name,
            "evidence": evidence, "monthly_cost": _money(cost), "estimated_monthly_saving": _money(saving) if saving and saving > 0.5 else None,
            "saving_kind": saving_kind if saving and saving > 0.5 else None, "saving_basis": basis if saving and saving > 0.5 else None,
            "recommendation": recommendation, "learn_url": COST_LEARN[learn], "effort": effort, "counted": False,
        })

    def total(slot):
        return slot["review"] if slot else None

    def workers(spec):
        if isinstance(spec.get("autoscale"), dict) and spec["autoscale"].get("max_workers"):
            return ((spec["autoscale"].get("min_workers") or 0) + spec["autoscale"]["max_workers"]) / 2.0
        return spec.get("num_workers") or spec.get("autoscale_max_workers") or 0

    def workers_label(spec):
        auto = spec.get("autoscale") if isinstance(spec.get("autoscale"), dict) else None
        if auto and auto.get("max_workers"):
            return str(auto.get("min_workers") or 0) + "–" + str(auto["max_workers"]) + " (autoscaling)"
        if spec.get("autoscale_max_workers") and not spec.get("num_workers"):
            return "up to " + str(spec["autoscale_max_workers"]) + " (autoscaling)"
        return spec.get("num_workers")

    def missing_tags(tags):
        present = {k.lower() for k in (tags or {})}
        return [t for t in COST_ALLOCATION_TAGS if t.lower() not in present]

    ap = ap_clusters(inventory)
    for c in ap:
        slot = clusters_cost.get(c["name"])
        mins = c.get("autotermination_minutes")
        off = not isinstance(mins, (int, float)) or mins <= 0
        if off or mins > COST_AUTOTERMINATION_MAX_MINUTES:
            since = c.get("last_restarted_time") or c.get("start_time")
            uptime = round((ref_ms - since) / 3.6e6) if c.get("state") == "RUNNING" and isinstance(since, (int, float)) and since < ref_ms else None
            profile = daily_profile(daily.get("daily_cluster", {}).get(c["name"]), labels, periods["review_start"])
            saving = profile["weekend_cost"] if off and profile and profile["weekend_cost"] > 0 else None
            add("AUTOTERM_OFF" if off else "AUTOTERM_LONG", "high" if off else "medium",
                "Interactive cluster without auto-termination" if off else "Long auto-termination on an interactive cluster",
                "AllPurposeCluster", c["id"], c["name"],
                {"autotermination_minutes": 0 if off else mins, "state": c.get("state"), "uptime_hours": uptime,
                 "active_days": profile and profile["active_days"], "weekend_cost": profile and profile["weekend_cost"]},
                total(slot), saving, "lower_bound", "weekend_cost",
                "Set autotermination_minutes to " + str(min(30, COST_AUTOTERMINATION_MAX_MINUTES)) + " minutes or less and enforce it with a compute policy.",
                "autotermination")
        w = workers(c)
        if w and not c.get("instance_pool_id") and not str(c.get("azure_availability") or "ON_DEMAND_AZURE").upper().startswith("SPOT"):
            saving = slot["vm"] * w / (w + 1.0) * COST_SPOT_DISCOUNT if slot and slot["vm"] else None
            add("NO_SPOT", "low", "Workers without spot instances on an interactive cluster", "AllPurposeCluster", c["id"], c["name"],
                {"availability": c.get("azure_availability") or "ON_DEMAND_AZURE", "workers": workers_label(c), "vm_cost": slot and _money(slot["vm"])},
                total(slot), saving, "estimate", "spot_discount",
                "Use SPOT_WITH_FALLBACK_AZURE on the workers (first_on_demand=1 keeps the driver on demand) if the workload tolerates retries.",
                "spot")
    by_cluster = {}
    for job in inventory.get("jobs", []):
        if not job.get("scheduled") or job.get("schedule_paused"):
            continue
        for task in job.get("tasks", []):
            if task.get("existing_cluster_id"):
                by_cluster.setdefault(task["existing_cluster_id"], set()).add(job["name"])
    for cid, names in sorted(by_cluster.items()):
        cluster = next((c for c in inventory.get("clusters", []) if c["id"] == cid), None)
        name = cluster["name"] if cluster else cid
        slot = clusters_cost.get(name)
        saving = slot["dbu"] * (1 - COST_JOBS_TO_ALL_PURPOSE_DBU_RATIO) if slot and slot["dbu"] else None
        add("JOBS_ON_ALL_PURPOSE", "high", "Scheduled jobs on interactive (all-purpose) compute", "AllPurposeCluster", cid, name,
            {"jobs": sorted(names)[:6], "jobs_count": len(names), "dbu_cost": slot and _money(slot["dbu"])},
            total(slot), saving, "upper_bound", "jobs_dbu_ratio",
            "Move the tasks to job compute (job_cluster_key) or serverless: a jobs DBU costs about "
            + str(round(100 * (1 - COST_JOBS_TO_ALL_PURPOSE_DBU_RATIO))) + "% less than an all-purpose DBU.",
            "jobs_compute", "M")
    for job in inventory.get("jobs", []):
        slot = jobs_cost.get(job["id"])
        on_demand = [jc for jc in job.get("job_clusters", []) if workers(jc) and not jc.get("instance_pool_id")
                     and not str(jc.get("azure_availability") or "ON_DEMAND_AZURE").upper().startswith("SPOT")]
        if on_demand:
            top = max(on_demand, key=workers)
            w = workers(top)
            saving = slot["vm"] * w / (w + 1.0) * COST_SPOT_DISCOUNT if slot and slot["vm"] else None
            add("NO_SPOT", "medium", "Job cluster without spot instances", "Job", job["id"], job["name"],
                {"availability": "ON_DEMAND_AZURE", "workers": workers_label(top), "vm_cost": slot and _money(slot["vm"]), "continuous": job.get("continuous")},
                total(slot), saving, "estimate", "spot_discount",
                "Use SPOT_WITH_FALLBACK_AZURE on the job cluster workers; keep the driver on demand.", "spot")
        if job.get("continuous"):
            add("CONTINUOUS_JOB", "medium", "Continuous job: compute on all month", "Job", job["id"], job["name"],
                {"continuous": True}, total(slot), None, None, None,
                "Confirm that it needs continuous latency; if not, use scheduled or file arrival triggers.", "streaming", "M")
        big = [jc for jc in job.get("job_clusters", []) if (jc.get("autoscale_max_workers") or jc.get("num_workers") or 0) >= 8
               and str(jc.get("runtime_engine") or "").upper() != "PHOTON"]
        if big:
            add("PHOTON_CANDIDATE", "low", "Large job without Photon: evaluate", "Job", job["id"], job["name"],
                {"max_workers": max(jc.get("autoscale_max_workers") or jc.get("num_workers") or 0 for jc in big)},
                total(slot), None, None, None,
                "Try Photon on one run: it costs more DBUs per hour but usually finishes sooner on SQL and ETL.", "photon", "M")
    for pool in inventory.get("instance_pools", []):
        slot = pools_cost.get(pool["id"])
        idle_min = pool.get("min_idle_instances") or 0
        if idle_min > 0:
            profile = daily_profile(daily.get("daily_pool", {}).get(pool["id"]), labels, periods["review_start"])
            saving = profile["floor"] * labels["review_days"] if profile and profile["floor"] > 0 else None
            add("POOL_IDLE", "medium", "Pool with idle instances always on", "InstancePool", pool["id"], pool["name"],
                {"min_idle_instances": idle_min, "idle_now": (pool.get("stats") or {}).get("idle_count"),
                 "idle_autotermination_minutes": pool.get("idle_instance_autotermination_minutes"), "daily_floor": profile and profile["floor"]},
                total(slot), saving, "estimate", "daily_floor",
                "Lower min_idle_instances to 0 (or the minimum you can justify) and set idle instance auto-termination between 10 and 15 minutes.", "pools")
    for wh in inventory.get("sql_warehouses", []):
        slot = warehouses_cost.get(wh["id"])
        mins = wh.get("auto_stop_mins")
        if not isinstance(mins, (int, float)) or mins <= 0 or mins > COST_WAREHOUSE_AUTOSTOP_MAX_MINUTES:
            never = not isinstance(mins, (int, float)) or mins <= 0
            saving = slot["review"] * weekend_share if never and slot and slot["review"] else None
            add("WAREHOUSE_AUTOSTOP", "high" if never else "medium",
                "SQL warehouse without auto-stop" if never else "Long auto-stop on a SQL warehouse", "SqlWarehouse", wh["id"], wh["name"],
                {"auto_stop_mins": mins or 0, "state": wh.get("state"), "serverless": wh.get("enable_serverless_compute")},
                total(slot), saving, "estimate", "always_on_weekends",
                "Set auto-stop between 10 and " + str(COST_WAREHOUSE_AUTOSTOP_MAX_MINUTES) + " minutes (serverless starts in seconds).", "warehouse")
        if wh.get("enable_serverless_compute") is not True:
            add("WAREHOUSE_SERVERLESS", "low", "Classic or pro SQL warehouse: evaluate serverless", "SqlWarehouse", wh["id"], wh["name"],
                {"warehouse_type": wh.get("warehouse_type"), "cluster_size": wh.get("cluster_size")}, total(slot), None, None, None,
                "Evaluate serverless: it starts in seconds, has a short auto-stop and runs no VMs in your subscription.", "warehouse")
    no_policy = [c for c in ap if not c.get("policy_id")]
    if no_policy:
        cost = sum(clusters_cost[c["name"]]["review"] for c in no_policy if c["name"] in clusters_cost)
        add("NO_POLICY", "low", "Interactive clusters without a compute policy", "AllPurposeCluster", "no-policy",
            str(len(no_policy)) + (" cluster" if len(no_policy) == 1 else " clusters"),
            {"objects": [c["name"] for c in no_policy][:8]}, cost, None, None, None,
            "Assign a policy that sets auto-termination, sizes, spot and allocation tags.", "policies")
    if tags_wanted:
        weak = [p for p in inventory.get("cluster_policies", []) if p.get("enforced_tag_keys") is not None
                and [t for t in tags_wanted if t not in {k.lower() for k in p["enforced_tag_keys"]}]]
        if weak:
            add("POLICY_TAGS", "medium", "Policies that don't enforce the allocation tags", "ClusterPolicy", "policy-tags",
                str(len(weak)) + (" policy" if len(weak) == 1 else " policies"),
                {"objects": [p["name"] for p in weak][:8], "allocation_tags": COST_ALLOCATION_TAGS}, None, None, None, None,
                "Add custom_tags." + COST_ALLOCATION_TAGS[0] + " (and the others) as fixed or required tags in each policy.", "policies")
        groups = (
            ("AllPurposeCluster", ("interactive cluster", "interactive clusters"), [(c["name"], c.get("custom_tags"), total(clusters_cost.get(c["name"]))) for c in ap]),
            ("Job", ("job", "jobs"), [(j["name"], job_effective_tags(j), total(jobs_cost.get(j["id"])))
                                       for j in inventory.get("jobs", []) if j.get("job_clusters")]),
            ("InstancePool", ("pool", "pools"), [(p["name"], p.get("custom_tags"), total(pools_cost.get(p["id"]))) for p in inventory.get("instance_pools", [])]),
            ("SqlWarehouse", ("SQL warehouse", "SQL warehouses"), [(w["name"], w.get("custom_tags"), total(warehouses_cost.get(w["id"]))) for w in inventory.get("sql_warehouses", [])]),
        )
        for kind, labels, items in groups:
            missing = [(name, cost, missing_tags(tags)) for name, tags, cost in items if missing_tags(tags)]
            if missing:
                cost = sum(c for _, c, _ in missing if c)
                untagged = sum(1 for _, _, m in missing if len(m) == len(COST_ALLOCATION_TAGS))
                add("MISSING_ALLOCATION_TAGS", "medium" if cost else "low",
                    ("No allocation tags on " if untagged == len(missing) else "Incomplete allocation tags on ") + labels[1],
                    kind, "tags-" + kind, str(len(missing)) + " " + labels[len(missing) != 1],
                    {"objects": [n + " (missing " + ", ".join(m) + ")" for n, _, m in missing][:8], "allocation_tags": COST_ALLOCATION_TAGS},
                    cost or None, None, None, None,
                    {
                        "AllPurposeCluster": "Add the missing tags to each cluster's custom_tags and make them required with a compute policy.",
                        "Job": "Add the missing tags as job tags (they propagate to its job clusters) or in the job cluster's custom_tags.",
                        "InstancePool": "Add the missing tags to the pool's custom_tags: its VMs inherit only the pool tags, not the cluster tags.",
                        "SqlWarehouse": "Add the missing tags to the SQL warehouse tags.",
                    }[kind] + " Tags: " + ", ".join(COST_ALLOCATION_TAGS) + ".",
                    "tags")
    versions = set((catalog or {}).get("spark_versions") or [])
    by_version, by_node = {}, {}
    specs = [(c["name"], c.get("spark_version"), c.get("node_type_id"), clusters_cost.get(c["name"])) for c in ap]
    specs += [(j["name"], jc.get("spark_version"), jc.get("node_type_id"), None) for j in inventory.get("jobs", []) for jc in j.get("job_clusters", [])]
    specs += [(p["name"], None, p.get("node_type_id"), None) for p in inventory.get("instance_pools", [])]
    for name, version, node, _ in specs:
        major = re.match(r"^(\d+)\.", version or "")
        if version and ((versions and version not in versions) or (not versions and major and int(major.group(1)) < 13)):
            by_version.setdefault(version, set()).add(name)
        info = ((catalog or {}).get("node_types") or {}).get(node) or {}
        if node and (info.get("is_deprecated") or OLD_NODE_RE.match(node)):
            by_node.setdefault(node, set()).add(name)
    for version, names in sorted(by_version.items()):
        add("RUNTIME_EOS", "medium", "Unsupported runtime" if versions else "Old runtime", "Runtime", version, version,
            {"objects": sorted(names)[:8], "supported_list_checked": bool(versions)}, None, None, None, None,
            "Upgrade to a supported LTS version (more performance per DBU and security patches).", "runtime", "M")
    vm_sizes = tables["vm_sizes"] if tables else {}
    for node, names in sorted(by_node.items()):
        size = _vm_meter(node)
        cost = sum(v for meter, v in vm_sizes.items() if (meter or "").lower().startswith(size)) if vm_sizes else None
        add("OLD_NODE_FAMILY", "low", "Old or retired VM family", "NodeType", node, node,
            {"objects": sorted(names)[:8], "deprecated": bool(((catalog or {}).get("node_types") or {}).get(node, {}).get("is_deprecated"))},
            cost or None, None, None, None,
            "Compare with the current generation (for example Dds_v5 or Eds_v5): it usually gives better price-performance.", "node_types", "M")
    best = {}
    for s in signals:
        if s["estimated_monthly_saving"]:
            key = s["object_kind"] + "|" + s["object_id"] if s["object_kind"] != "Job" else "Job|" + s["object_id"]
            if key not in best or s["estimated_monthly_saving"] > best[key]["estimated_monthly_saving"]:
                best[key] = s
    for s in best.values():
        s["counted"] = True
    rank = {"high": 0, "medium": 1, "low": 2}
    signals.sort(key=lambda s: (-(s["estimated_monthly_saving"] or 0) if s["counted"] else 0, rank[s["severity"]], -(s["monthly_cost"] or 0), s["code"]))
    return signals


def job_effective_tags(job):
    """Job tags propagate to the job clusters a run creates; job-cluster custom_tags add to (and override) them."""
    tags = dict(job.get("tags") or {})
    for jc in job.get("job_clusters", []):
        tags.update(jc.get("custom_tags") or {})
    return tags


def attribution_rows(dimension, slots, inventory, review_total):
    """One row per tag value of a Cost Management dimension, joined to the observed inventory by name or ID."""
    clusters = {c["name"]: c for c in inventory.get("clusters", [])}
    jobs = {j["id"]: j for j in inventory.get("jobs", [])}
    warehouses = {w["id"]: w for w in inventory.get("sql_warehouses", [])}
    pools = {p["id"]: p for p in inventory.get("instance_pools", [])}
    grouped = {}
    for key, slot in slots.items():
        if key is None:
            continue
        name, kind, found, creator, tags = key, dimension, False, None, {}
        group_key = key
        if dimension == "cluster":
            job_run = re.match(r"^job-(\d+)-run-\d+", key)
            if job_run:
                group_key, kind, name = "job-runs", "job_runs", "job_runs"
            elif key.startswith("dlt-execution-") or key.startswith("dlt-maintenance-"):
                group_key, kind, name = "pipelines", "pipeline_runs", "pipeline_runs"
            elif key in clusters:
                c = clusters[key]
                kind = "pipeline" if (c.get("cluster_source") or "").upper().startswith("PIPELINE") else "all_purpose" if c.get("kind") == "AllPurposeCluster" else "job_run"
                found, creator, tags = True, c.get("creator_user_name"), c.get("custom_tags") or {}
            else:
                kind = "not_in_inventory"
        elif dimension == "job" and key in jobs:
            j = jobs[key]
            found, name, creator = True, j["name"], j.get("creator_user_name")
            tags = job_effective_tags(j)
        elif dimension == "warehouse" and key in warehouses:
            w = warehouses[key]
            found, name, creator, tags = True, w["name"], w.get("creator_name"), w.get("custom_tags") or {}
        elif dimension == "pool" and key in pools:
            p = pools[key]
            found, name, tags = True, p["name"], p.get("custom_tags") or {}
        row = grouped.setdefault(group_key, {
            "dimension": dimension, "key": group_key, "name": name, "kind": kind, "in_inventory": found, "creator": creator,
            "tags": {k: v for k, v in tags.items() if k.lower() in {t.lower() for t in COST_ALLOCATION_TAGS}},
            "dbu": 0.0, "infra": 0.0, "vm": 0.0, "total": 0.0, "previous_total": 0.0, "count": 0,
        })
        row["dbu"] += slot["dbu"]
        row["infra"] += slot["infra"]
        row["vm"] += slot["vm"]
        row["total"] += slot["review"]
        row["previous_total"] += slot["previous"]
        row["count"] += 1
    rows = []
    for row in grouped.values():
        if row["kind"] == "job_runs":
            row["name"] = "Ephemeral job clusters (" + str(row["count"]) + (" run)" if row["count"] == 1 else " runs)")
        elif row["kind"] == "pipeline_runs":
            row["name"] = "Pipeline clusters (DLT)"
        row["change"] = round(row["total"] - row["previous_total"], 2)
        row["change_pct"] = _pct(row["total"] - row["previous_total"], row["previous_total"])
        row["share"] = _pct(row["total"], review_total)
        for field in ("dbu", "infra", "vm", "total", "previous_total"):
            row[field] = round(row[field], 2)
        rows.append(row)
    rows.sort(key=lambda r: (-r["total"], str(r["name"])))
    return rows[:150]


def databricks_costs_for(raw, reference):
    """Section 6 model: where Databricks cost comes from and how to optimise it. Never invents data: a missing query
    stays missing (None) and its status is reported."""
    inventory = raw.get("inventory", {})
    data = raw.get("dbx_cost_data")
    receipt = next((s for s in raw.get("sources", []) if s["id"] == "azure_cost_databricks"), None)
    periods = cost_periods(reference)
    labels = periods["labels"]
    tables = cost_tables(data, labels) if data else None
    status = pick(receipt, "status") or ("not_collected" if data is None else "complete")
    signals = cost_signals(inventory, raw.get("dbx_runtime_catalog"), tables, labels, periods, reference)
    model = {
        "status": status,
        "metric": COST_METRIC,
        "periods": labels,
        "currency": tables["currency"] if tables else None,
        "other_currencies": tables["other_currencies"] if tables else [],
        "scope": data.get("scope") if data else None,
        "query_status": tables["query_status"] if tables else {},
        "assumptions": {
            "allocation_tags": list(COST_ALLOCATION_TAGS),
            "autotermination_max_minutes": COST_AUTOTERMINATION_MAX_MINUTES,
            "warehouse_autostop_max_minutes": COST_WAREHOUSE_AUTOSTOP_MAX_MINUTES,
            "jobs_to_all_purpose_dbu_ratio": COST_JOBS_TO_ALL_PURPOSE_DBU_RATIO,
            "spot_discount": COST_SPOT_DISCOUNT,
            "weekend_share": round(labels["review_weekend_days"] / max(1, labels["review_days"]), 4),
        },
        "signals": signals,
        "headline": None, "monthly": [], "split": None, "attribution": None, "movers": None,
    }
    saving_total = round(sum(s["estimated_monthly_saving"] for s in signals if s["counted"]), 2)
    severity_counts = {sev: sum(s["severity"] == sev for s in signals) for sev in ("high", "medium", "low")}
    if tables and tables["query_status"].get("meter") in ("complete", "partial"):
        months = tables["months"]
        review = months[labels["review"]]
        previous = months[labels["previous"]]
        current = months[labels["current"]]
        review_total = review["dbu"] + review["infra"]
        previous_total = previous["dbu"] + previous["infra"]
        vendor = tables["dimensions"].get("vendor")
        gap = vendor.get(None) if vendor is not None and tables["query_status"].get("vendor") in ("complete", "partial") else None
        model["monthly"] = [
            {"month": label, "dbu": round(months[label]["dbu"], 2), "infra": round(months[label]["infra"], 2),
             "total": round(months[label]["dbu"] + months[label]["infra"], 2), "partial": label == labels["current"]}
            for label in (labels["previous"], labels["review"], labels["current"])
        ]
        family_rows = [
            {"key": key, "review": round(v["review"], 2), "previous": round(v["previous"], 2), "share": _pct(v["review"], review["dbu"]),
             "meters": [{"meter": m, "review": round(a, 2)} for m, a in sorted(v["meters"].items(), key=lambda kv: -kv[1])[:6]]}
            for key, v in sorted(tables["families"].items(), key=lambda kv: -kv[1]["review"])
        ]
        category_rows = [
            {"category": key, "review": round(v["review"], 2), "previous": round(v["previous"], 2), "share": _pct(v["review"], review["infra"])}
            for key, v in sorted(tables["categories"].items(), key=lambda kv: -kv[1]["review"])
        ]
        model["split"] = {
            "dbu_families": family_rows,
            "infra_categories": category_rows,
            "vm_sizes": [{"meter": m, "review": round(a, 2)} for m, a in sorted(tables["vm_sizes"].items(), key=lambda kv: -kv[1])[:8]],
        }
        dimensions = []
        all_rows = []
        for dimension, tag in COST_DIMENSIONS:
            slots = tables["dimensions"].get(dimension)
            state = tables["query_status"].get(dimension)
            if slots is None or state not in ("complete", "partial"):
                dimensions.append({"key": dimension, "tag": tag, "status": state or "not_collected", "tagged_share": None, "untagged_total": None})
                continue
            untagged = slots.get(None, {"review": 0.0})["review"]
            rows = attribution_rows(dimension, slots, inventory, review_total)
            all_rows.extend(rows)
            dimensions.append({"key": dimension, "tag": tag, "status": state, "tagged_share": _pct(review_total - untagged, review_total),
                               "untagged_total": round(untagged, 2), "rows": len(rows)})
        creators = {}
        for row in all_rows:
            if row["dimension"] in ("cluster", "job", "warehouse") and row["in_inventory"]:
                who = row["creator"] or "—"
                creators[who] = creators.get(who, 0.0) + row["total"]
        custom = []
        for tag in COST_ALLOCATION_TAGS:
            slots = tables["dimensions"].get("tag:" + tag)
            state = tables["query_status"].get("tag:" + tag)
            if slots is None or state not in ("complete", "partial"):
                custom.append({"tag": tag, "status": state or "not_collected", "tagged_share": None, "values": []})
                continue
            untagged = slots.get(None, {"review": 0.0})
            custom.append({
                "tag": tag, "status": state, "tagged_share": _pct(review_total - untagged["review"], review_total),
                "untagged_total": round(untagged["review"], 2),
                "untagged_categories": [{"category": k, "review": round(v, 2)} for k, v in sorted(untagged.get("categories", {}).items(), key=lambda kv: -kv[1])[:6]],
                "values": [
                    {"value": k, "total": round(v["review"], 2), "dbu": round(v["dbu"], 2), "infra": round(v["infra"], 2),
                     "previous_total": round(v["previous"], 2), "share": _pct(v["review"], review_total)}
                    for k, v in sorted(((k, v) for k, v in slots.items() if k is not None), key=lambda kv: -kv[1]["review"])[:40]
                ],
            })
        model["attribution"] = {
            "dimensions": dimensions,
            "rows": all_rows,
            "creators": [{"creator": k, "total": round(v, 2), "share": _pct(v, review_total)} for k, v in sorted(creators.items(), key=lambda kv: -kv[1])[:25]],
            "custom_tags": custom,
            "gap": None if gap is None else {
                "total": round(gap["review"], 2), "share": _pct(gap["review"], review_total), "previous_total": round(gap["previous"], 2),
                "categories": [{"category": k, "review": round(v, 2), "share": _pct(v, gap["review"])}
                               for k, v in sorted(gap["categories"].items(), key=lambda kv: -kv[1])],
            },
        }
        movable = [r for r in all_rows if r["dimension"] in ("cluster", "job", "warehouse", "pool") and r["kind"] not in ("job_runs", "pipeline_runs")]
        model["movers"] = {
            "up": [r for r in sorted(movable, key=lambda r: -r["change"]) if r["change"] > 0][:5],
            "down": [r for r in sorted(movable, key=lambda r: r["change"]) if r["change"] < 0][:3],
        }
        top = max((r for r in all_rows if r["dimension"] in ("cluster", "job", "warehouse")), key=lambda r: r["total"], default=None)
        first_tag = next((c for c in custom if c["tagged_share"] is not None), None)
        model["headline"] = {
            "review_month": labels["review"], "previous_month": labels["previous"], "current_month": labels["current"],
            "review_total": round(review_total, 2), "previous_total": round(previous_total, 2),
            "change": round(review_total - previous_total, 2), "change_pct": _pct(review_total - previous_total, previous_total),
            "dbu_total": round(review["dbu"], 2), "infra_total": round(review["infra"], 2), "dbu_share": _pct(review["dbu"], review_total),
            "mtd_total": round(current["dbu"] + current["infra"], 2), "mtd_days": labels["mtd_days"],
            "unattributed_total": None if gap is None else round(gap["review"], 2),
            "unattributed_share": None if gap is None else _pct(gap["review"], review_total),
            "first_tag": first_tag and {"tag": first_tag["tag"], "tagged_share": first_tag["tagged_share"]},
            "top_object": top and {"name": top["name"], "dimension": top["dimension"], "total": top["total"], "share": top["share"]},
            "estimated_monthly_savings": saving_total or None,
            "savings_signals": sum(1 for s in signals if s["counted"]),
            "signals": len(signals), "signals_by_severity": severity_counts,
        }
    else:
        model["headline"] = {
            "review_month": labels["review"], "estimated_monthly_savings": None, "savings_signals": 0,
            "signals": len(signals), "signals_by_severity": severity_counts,
        }
    billing = raw.get("system_billing")
    billing_receipt = next((s for s in raw.get("sources", []) if s["id"] == "dbx_system_billing"), None)
    model["system_tables"] = {"status": pick(billing_receipt, "status") or "not_configured", "warehouse_id": pick(billing_receipt, "warehouse_id")}
    if billing:
        rows = sorted(billing.get("rows", []), key=lambda r: -(r.get("list_cost") or 0))
        model["system_tables"].update(
            window=billing.get("window"), truncated=billing.get("truncated"),
            runs=[r for r in rows if r.get("row_type") == "run"][:40],
            users=[r for r in rows if r.get("row_type") == "user"][:20],
            products=[r for r in rows if r.get("row_type") == "product"][:20],
            currency=next((r.get("currency") for r in rows if r.get("currency")), None),
        )
    return model


def cost_summary(model):
    """Compact cost headline for chat responses (fits the 3,500-byte tool-result budget)."""
    if not model:
        return None
    head = model.get("headline") or {}
    return {
        "status": model.get("status"),
        "month": head.get("review_month"),
        "currency": model.get("currency"),
        "total": head.get("review_total"),
        "change_pct": head.get("change_pct"),
        "dbu_share": head.get("dbu_share"),
        "unattributed_share": head.get("unattributed_share"),
        "estimated_monthly_savings": head.get("estimated_monthly_savings"),
        "signals": head.get("signals"),
    }


DEMO_SUBSCRIPTION = "00000000-0000-4000-8000-0000000000a1"
DEMO_TENANT = "00000000-0000-4000-8000-0000000000b2"


def _demo_weights(pattern, key, days, start):
    weights = []
    for i in range(days):
        day = start + timedelta(days=i)
        noise = 0.9 + 0.2 * int(hashlib.sha256((key + day.isoformat()).encode("utf-8")).hexdigest()[:4], 16) / 65535
        weekday = day.weekday() < 5
        coin = int(hashlib.sha256((key + "c" + day.isoformat()).encode("utf-8")).hexdigest()[:2], 16) / 255
        weight = {
            "always": 1.0, "nightly": 1.0, "weekdays": 1.0 if weekday else 0.0,
            "light": 1.0 if weekday and coin < 0.55 else 0.0, "sparse": 1.0 if weekday and coin < 0.22 else 0.0,
            "month_end": 1.0 if i >= days - 6 else 0.0, "pool": 0.62 + (0.38 if weekday else 0.0),
        }[pattern]
        weights.append(weight * (noise if pattern != "pool" else 1.0))
    scale = sum(weights) or 1.0
    return [w / scale for w in weights]


def demo_cost_data(reference, inventory):
    """SIMULATED Cost Management results built item by item, so every query reconciles exactly as live data would."""
    periods = cost_periods(reference)
    labels = periods["labels"]
    tag = {role: (COST_ALLOCATION_TAGS[i] if len(COST_ALLOCATION_TAGS) > i else None) for i, role in enumerate(("team", "project", "cc"))}
    vm, db, st = "Virtual Machines", "Azure Databricks", "Storage"
    ap = lambda name: {"Vendor": "Databricks", "ClusterName": name}
    job = lambda jid, run: {"Vendor": "Databricks", "ClusterName": "job-" + jid + "-run-" + run, "JobId": jid}
    wh = lambda wid: {"Vendor": "Databricks", "SqlEndpointId": wid}
    pool = lambda pid: {"Vendor": "Databricks", "DatabricksInstancePoolId": pid}
    items = [
        (ap("bi-sales-shared"), {"team": "sales", "project": "dashboards"}, db, "Premium All-purpose Compute DBU", 3360, 2640, "always"),
        (ap("bi-sales-shared"), {"team": "sales", "project": "dashboards"}, vm, "DS4 v2", 2050, 1610, "always"),
        (ap("bi-sales-shared"), {"team": "sales", "project": "dashboards"}, st, "P10 LRS Disk", 140, 130, "always"),
        (ap("ds-demand-forecast"), {"team": "data-science", "project": "demand-forecast", "cc": "CC-410"}, db, "Premium All-purpose Photon DBU", 820, 760, "weekdays"),
        (ap("ds-demand-forecast"), {"team": "data-science", "project": "demand-forecast", "cc": "CC-410"}, vm, "E8ds v5 Spot", 310, 290, "weekdays"),
        (ap("ds-demand-forecast"), {"team": "data-science", "project": "demand-forecast", "cc": "CC-410"}, st, "P10 LRS Disk", 45, 40, "weekdays"),
        (ap("engineering-adhoc"), {"team": "engineering"}, db, "Premium All-purpose Compute DBU", 410, 450, "light"),
        (ap("engineering-adhoc"), {"team": "engineering"}, vm, "D8ds v5", 260, 280, "light"),
        (ap("engineering-adhoc"), {"team": "engineering"}, st, "P10 LRS Disk", 25, 25, "light"),
        (ap("legacy-reports"), {}, db, "Premium All-purpose Compute DBU", 190, 260, "sparse"),
        (ap("legacy-reports"), {}, vm, "DS3 v2", 120, 150, "sparse"),
        (ap("legacy-reports"), {}, st, "P10 LRS Disk", 15, 15, "sparse"),
        (ap("finance-close"), {"team": "finance", "project": "month-end-close", "cc": "CC-200"}, db, "Premium All-purpose Compute DBU", 260, 180, "month_end"),
        (pool("1015-090000-pool-general"), {}, vm, "D4ds v5", 1180, 1120, "pool"),
        (pool("1015-090000-pool-general"), {}, st, "P10 LRS Disk", 60, 58, "pool"),
        (pool("1015-091500-pool-etlnight"), {"team": "engineering"}, vm, "E8ds v5 Spot", 220, 240, "nightly"),
        (job("1001", "318842"), {"team": "sales", "project": "etl-sales", "cc": "CC-100"}, db, "Premium Jobs Compute DBU", 1640, 1480, "nightly"),
        (job("1001", "318842"), {"team": "sales", "project": "etl-sales", "cc": "CC-100"}, vm, "D8ds v5", 1020, 930, "nightly"),
        (job("1001", "318842"), {"team": "sales", "project": "etl-sales", "cc": "CC-100"}, st, "P10 LRS Disk", 70, 65, "nightly"),
        (job("1004", "551220"), {"team": "data-science", "project": "demand-forecast"}, db, "Premium Jobs Compute DBU", 690, 640, "nightly"),
        (job("1004", "551220"), {"team": "data-science", "project": "demand-forecast"}, vm, "E8ds v5 Spot", 160, 150, "nightly"),
        (job("1005", "77310"), {}, db, "Premium Jobs Compute DBU", 380, 300, "nightly"),
        (job("1005", "77310"), {}, vm, "DS3 v2", 240, 190, "nightly"),
        (job("1006", "1"), {"team": "engineering", "project": "erp-ingest", "cc": "CC-300"}, db, "Premium Jobs Compute DBU", 520, 505, "always"),
        (job("1006", "1"), {"team": "engineering", "project": "erp-ingest", "cc": "CC-300"}, vm, "D4ds v5", 300, 290, "always"),
        ({"Vendor": "Databricks", "ClusterName": "dlt-execution-0c1d2e3f-orders"}, {"team": "engineering", "project": "erp-ingest"}, db, "Premium DLT Core Compute DBU", 430, 380, "nightly"),
        ({"Vendor": "Databricks", "ClusterName": "dlt-execution-0c1d2e3f-orders"}, {"team": "engineering", "project": "erp-ingest"}, vm, "D4ds v5", 140, 120, "nightly"),
        (wh("a1b2c3d4e5f60718"), {"team": "sales"}, db, "Premium SQL Compute Pro DBU", 1920, 1700, "always"),
        (wh("a1b2c3d4e5f60718"), {"team": "sales"}, vm, "E8ds v5", 640, 560, "always"),
        (wh("b2c3d4e5f6071829"), {"team": "finance", "project": "month-end-close", "cc": "CC-200"}, db, "Premium Serverless SQL DBU", 640, 590, "weekdays"),
        ({}, {}, db, "Premium Serverless Compute DBU", 520, 260, "weekdays"),
        ({}, {}, st, "Hot LRS Data Stored", 420, 400, "always"),
        ({}, {}, "Bandwidth", "Standard Data Transfer Out", 180, 170, "always"),
        ({}, {}, "Virtual Network", "NAT Gateway Hours", 140, 140, "always"),
        ({}, {}, "Load Balancer", "Standard Load Balancer Data Processed", 60, 60, "always"),
    ]
    review_days = labels["review_days"]
    mtd_factor = max(0, labels["mtd_days"] - 1) / review_days * 1.04
    queries = {}

    def tags_of(item):
        default, alloc = item[0], item[1]
        return {**default, **{tag[role]: value for role, value in alloc.items() if tag.get(role)}}

    def emit(qid, key_of, with_meter=False, current=False):
        out = {}
        for item in items:
            key = key_of(tags_of(item))
            for period, amount in ((labels["previous"], item[5]), (labels["review"], item[4])) + (((labels["current"], round(item[4] * mtd_factor, 2)),) if current else ()):
                slot = (period, key, item[2], item[3] if with_meter else None)
                out[slot] = out.get(slot, 0.0) + amount
        queries[qid] = {"status": "complete", "rows": [[p, k, c, m, round(v, 6), "EUR"] for (p, k, c, m), v in sorted(out.items(), key=str)],
                        "pages": 1, "seconds": 2.1, "error": None}

    emit("meter", lambda t: None, with_meter=True, current=True)
    emit("vendor", lambda t: t.get("Vendor"))
    for dimension, tag_name in COST_DIMENSIONS:
        emit(dimension, lambda t, n=tag_name: t.get(n))
    for tag_name in COST_ALLOCATION_TAGS:
        emit("tag:" + tag_name, lambda t, n=tag_name: t.get(n))
    names = {c["name"] for c in ap_clusters(inventory)}
    pools_idle = {p["id"] for p in inventory.get("instance_pools", []) if (p.get("min_idle_instances") or 0) > 0}
    for qid, tag_name, wanted in (("daily_cluster", "ClusterName", names), ("daily_pool", "DatabricksInstancePoolId", pools_idle)):
        out = {}
        for item in items:
            key = item[0].get(tag_name)
            if key not in wanted:
                continue
            for i, weight in enumerate(_demo_weights(item[6], key + item[3], review_days, periods["review_start"])):
                day = (periods["review_start"] + timedelta(days=i)).isoformat()
                if weight:
                    out[(day, key)] = out.get((day, key), 0.0) + item[4] * weight
        queries[qid] = {"status": "complete", "rows": [[d, k, None, None, round(v, 6), "EUR"] for (d, k), v in sorted(out.items())],
                        "pages": 1, "seconds": 1.4, "error": None}
    return {
        "metric": COST_METRIC, "periods": labels, "queries": queries,
        "scope": {"subscription_id": DEMO_SUBSCRIPTION, "resource_ids": [], "managed_resource_group": "databricks-rg-dbx-analytics-prod"},
    }


def demo_system_billing(reference):
    periods = cost_periods(reference)
    rows = []
    for job_id, name, runs, cost, sku, user in (
        ("1001", "etl-sales-daily", 31, 52.9, "PREMIUM_JOBS_COMPUTE", "sp-etl-production"),
        ("1004", "demand-forecast-weekly", 4, 172.5, "PREMIUM_JOBS_COMPUTE", "luis.martin@example.com"),
        ("1005", "data-quality-silver", 31, 12.3, "PREMIUM_JOBS_COMPUTE", "jorge.lopez@example.com"),
    ):
        for n in range(min(runs, 6)):
            rows.append({"row_type": "run", "product": "JOBS", "sku": sku, "cluster_id": None, "job_id": job_id, "job_run_id": str(700000 + int(job_id) * 10 + n),
                         "warehouse_id": None, "pipeline_id": None, "run_as": user, "dbus": round(cost / 0.30 * (1.18 - 0.07 * n), 1),
                         "list_cost": round(cost * (1.18 - 0.07 * n), 2), "currency": "USD"})
    rows.append({"row_type": "run", "product": "ALL_PURPOSE", "sku": "PREMIUM_ALL_PURPOSE_COMPUTE", "cluster_id": "0915-081203-bivts01", "job_id": None,
                 "job_run_id": None, "warehouse_id": None, "pipeline_id": None, "run_as": "ana.garcia@example.com", "dbus": 6545.5, "list_cost": 3600.0, "currency": "USD"})
    rows.append({"row_type": "run", "product": "SQL", "sku": "PREMIUM_SQL_PRO_COMPUTE", "cluster_id": None, "job_id": None, "job_run_id": None,
                 "warehouse_id": "a1b2c3d4e5f60718", "pipeline_id": None, "run_as": None, "dbus": 3740.0, "list_cost": 2057.0, "currency": "USD"})
    rows.sort(key=lambda r: -r["list_cost"])
    for user, dbus, cost in (("ana.garcia@example.com", 6545.5, 3600.0), ("sp-etl-production", 5880.0, 1764.0), ("luis.martin@example.com", 3790.0, 1595.0),
                             ("marta.ruiz@example.com", 800.0, 440.0), ("jorge.lopez@example.com", 1615.0, 650.0)):
        rows.append({"row_type": "user", "product": None, "sku": None, "cluster_id": None, "job_id": None, "job_run_id": None, "warehouse_id": None,
                     "pipeline_id": None, "run_as": user, "dbus": dbus, "list_cost": cost, "currency": "USD"})
    for product, sku, dbus, cost in (("ALL_PURPOSE", "PREMIUM_ALL_PURPOSE_COMPUTE", 9255.0, 5090.0), ("JOBS", "PREMIUM_JOBS_COMPUTE", 11000.0, 3300.0),
                                     ("SQL", "PREMIUM_SQL_PRO_COMPUTE", 3740.0, 2057.0), ("SQL", "PREMIUM_SERVERLESS_SQL_COMPUTE", 980.0, 686.0),
                                     ("DLT", "PREMIUM_DLT_CORE_COMPUTE", 1530.0, 459.0), ("INTERACTIVE", "PREMIUM_SERVERLESS_COMPUTE", 400.0, 300.0)):
        rows.append({"row_type": "product", "product": product, "sku": sku, "cluster_id": None, "job_id": None, "job_run_id": None, "warehouse_id": None,
                     "pipeline_id": None, "run_as": None, "dbus": dbus, "list_cost": cost, "currency": "USD"})
    return {"warehouse_id": "b2c3d4e5f6071829", "window": {"start": periods["review_start"].isoformat(), "end": periods["current_start"].isoformat()},
            "rows": rows, "truncated": False}


def demo_raw(reference):
    """Complete SIMULATED workspace (operation=self_test): no network, no configuration, clearly labelled everywhere."""
    sub, rg, name, host = DEMO_SUBSCRIPTION, "rg-data-prod", "dbx-analytics-prod", "adb-1234567890123456.7.azuredatabricks.net"
    base = "/subscriptions/" + sub + "/resourceGroups/" + rg + "/providers/"
    config = {
        "name": name, "resource_group": rg, "workspace_host": host, "environment": "PRODUCTION", "auth_mode": "same_tenant_uami",
        "workspace_api_enabled": True, "unity_catalog_enabled": True, "include_managed_resource_group": True, "advisor_enabled": True,
        "approved_related_resource_ids": [], "approved_cost_resource_ids": [], "cost_scope": "disabled", "cost_timeframe": "month_to_date",
        "cost_analysis_enabled": True, "system_tables_warehouse_id": "b2c3d4e5f6071829",
        "requirements": {"premium_required": True, "no_public_ip_required": True, "vnet_injection_required": True, "cluster_policy_required": True},
        "sre_tenant_id": DEMO_TENANT, "target_tenant_id": DEMO_TENANT, "cross_tenant": False, "subscription_id": sub,
        "id": base + "Microsoft.Databricks/workspaces/" + name,
    }
    vnet, ac = base + "Microsoft.Network/virtualNetworks/vnet-data-prod", base + "Microsoft.Databricks/accessConnectors/ac-data-prod"
    nsg, st, kv = base + "Microsoft.Network/networkSecurityGroups/nsg-dbx-prod", base + "Microsoft.Storage/storageAccounts/stdatalakeprod", base + "Microsoft.KeyVault/vaults/kv-data-prod"
    ws = normalize_workspace({
        "id": config["id"], "name": name, "location": "westeurope", "sku": {"name": "premium"},
        "properties": {
            "workspaceId": "1234567890123456", "workspaceUrl": host, "provisioningState": "Succeeded",
            "managedResourceGroupId": "/subscriptions/" + sub + "/resourceGroups/databricks-rg-" + name, "publicNetworkAccess": "Enabled",
            "requiredNsgRules": "AllRules", "defaultCatalog": {"initialType": "UnityCatalog", "initialName": "main"},
            "accessConnector": {"id": ac, "identityType": "SystemAssigned"},
            "parameters": {"enableNoPublicIp": {"value": True}, "customVirtualNetworkId": {"value": vnet},
                           "customPublicSubnetName": {"value": "snet-dbx-host"}, "customPrivateSubnetName": {"value": "snet-dbx-container"},
                           "storageAccountName": {"value": "dbstoragedemo01"}},
        },
    }, "arm_workspace", reference, config)
    related = [normalize_resource(item, "arm_resource_" + str(i + 1), reference, config, {"type": "direct_reference", "source_id": "arm_workspace", "field": field})
               for i, (item, field) in enumerate((
                   ({"id": vnet, "name": "vnet-data-prod", "location": "westeurope", "properties": {"addressSpace": {"addressPrefixes": ["10.20.0.0/16"]},
                     "subnets": [{"id": vnet + "/subnets/snet-dbx-host"}, {"id": vnet + "/subnets/snet-dbx-container"}]}}, "parameters.customVirtualNetworkId"),
                   ({"id": vnet + "/subnets/snet-dbx-host", "name": "snet-dbx-host", "properties": {"addressPrefix": "10.20.1.0/24", "networkSecurityGroup": {"id": nsg},
                     "delegations": [{"name": "dbx", "properties": {"serviceName": "Microsoft.Databricks/workspaces"}}]}}, "parameters.customPublicSubnetName"),
                   ({"id": vnet + "/subnets/snet-dbx-container", "name": "snet-dbx-container", "properties": {"addressPrefix": "10.20.2.0/24", "networkSecurityGroup": {"id": nsg},
                     "delegations": [{"name": "dbx", "properties": {"serviceName": "Microsoft.Databricks/workspaces"}}]}}, "parameters.customPrivateSubnetName"),
                   ({"id": nsg, "name": "nsg-dbx-prod", "properties": {"securityRules": []}}, "nsg_id"),
                   ({"id": ac, "name": "ac-data-prod", "identity": {"type": "SystemAssigned"}, "properties": {"provisioningState": "Succeeded"}}, "accessConnector.id"),
                   ({"id": st, "name": "stdatalakeprod", "sku": {"name": "Standard_ZRS"}, "properties": {"supportsHttpsTrafficOnly": True, "minimumTlsVersion": "TLS1_2",
                     "allowBlobPublicAccess": False, "allowSharedKeyAccess": True, "publicNetworkAccess": "Enabled", "isHnsEnabled": True,
                     "primaryEndpoints": {"dfs": "https://stdatalakeprod.dfs.core.windows.net/"}}}, "approved_related_resource_ids"),
                   ({"id": kv, "name": "kv-data-prod", "properties": {"enableRbacAuthorization": True, "enablePurgeProtection": True, "enableSoftDelete": True,
                     "publicNetworkAccess": "Disabled", "vaultUri": "https://kv-data-prod.vault.azure.net/"}}, "keyvault_metadata.resource_id"),
               ))]
    day_ms = 86400000
    now_ms = int(datetime.fromisoformat(reference.replace("Z", "+00:00")).timestamp() * 1000)
    tags = lambda **kw: {COST_ALLOCATION_TAGS[i]: kw[r] for i, r in enumerate(("team", "project", "cc")) if len(COST_ALLOCATION_TAGS) > i and r in kw}
    cluster_specs = [
        {"cluster_id": "0915-081203-bivts01", "cluster_name": "bi-sales-shared", "cluster_source": "UI", "state": "RUNNING", "spark_version": "13.3.x-scala2.12",
         "node_type_id": "Standard_DS4_v2", "autoscale": {"min_workers": 2, "max_workers": 8}, "autotermination_minutes": 0, "data_security_mode": "USER_ISOLATION",
         "azure_attributes": {"availability": "ON_DEMAND_AZURE"}, "custom_tags": tags(team="sales", project="dashboards"),
         "creator_user_name": "ana.garcia@example.com", "start_time": now_ms - 40 * day_ms, "last_restarted_time": now_ms - 9 * day_ms},
        {"cluster_id": "0915-091530-dsprv02", "cluster_name": "ds-demand-forecast", "cluster_source": "UI", "state": "TERMINATED", "spark_version": "15.4.x-cpu-ml-scala2.12",
         "node_type_id": "Standard_E8ds_v5", "num_workers": 4, "autotermination_minutes": 120, "data_security_mode": "SINGLE_USER", "policy_id": "POL-DATA-SCIENCE",
         "runtime_engine": "PHOTON", "azure_attributes": {"availability": "SPOT_WITH_FALLBACK_AZURE", "first_on_demand": 1},
         "custom_tags": tags(team="data-science", project="demand-forecast", cc="CC-410"), "creator_user_name": "luis.martin@example.com"},
        {"cluster_id": "0915-102244-ingad03", "cluster_name": "engineering-adhoc", "cluster_source": "UI", "state": "TERMINATED", "spark_version": "14.3.x-scala2.12",
         "node_type_id": "Standard_D8ds_v5", "autoscale": {"min_workers": 1, "max_workers": 4}, "autotermination_minutes": 30, "data_security_mode": "USER_ISOLATION",
         "policy_id": "POL-PERSONAL-USE", "azure_attributes": {"availability": "ON_DEMAND_AZURE"}, "custom_tags": tags(team="engineering"),
         "creator_user_name": "marta.ruiz@example.com"},
        {"cluster_id": "0915-110001-legin04", "cluster_name": "legacy-reports", "cluster_source": "UI", "state": "TERMINATED", "spark_version": "10.4.x-scala2.12",
         "node_type_id": "Standard_DS3_v2", "num_workers": 2, "autotermination_minutes": 60, "data_security_mode": "NONE",
         "azure_attributes": {"availability": "ON_DEMAND_AZURE"}, "creator_user_name": "jorge.lopez@example.com"},
        {"cluster_id": "0915-120000-fincr05", "cluster_name": "finance-close", "cluster_source": "API", "state": "TERMINATED", "spark_version": "15.4.x-scala2.12",
         "node_type_id": "Standard_D4ds_v5", "num_workers": 2, "autotermination_minutes": 20, "data_security_mode": "USER_ISOLATION", "policy_id": "POL-PERSONAL-USE",
         "instance_pool_id": "1015-090000-pool-general", "custom_tags": tags(team="finance", project="month-end-close", cc="CC-200"),
         "creator_user_name": "elena.sanz@example.com"},
        {"cluster_id": "1103-020000-job1004", "cluster_name": "job-1004-run-551220", "cluster_source": "JOB", "state": "TERMINATED", "spark_version": "15.4.x-cpu-ml-scala2.12",
         "node_type_id": "Standard_E8ds_v5", "num_workers": 6, "data_security_mode": "SINGLE_USER"},
    ]
    clusters = [normalize_cluster(c, "dbx_clusters", reference, config) for c in cluster_specs]
    pools = [normalize_pool(p, "dbx_instance_pools", reference, config) for p in (
        {"instance_pool_id": "1015-090000-pool-general", "instance_pool_name": "pool-general", "node_type_id": "Standard_D4ds_v5", "min_idle_instances": 4,
         "max_capacity": 20, "idle_instance_autotermination_minutes": 60, "azure_attributes": {"availability": "ON_DEMAND_AZURE"}, "state": "ACTIVE",
         "stats": {"used_count": 1, "idle_count": 4}},
        {"instance_pool_id": "1015-091500-pool-etlnight", "instance_pool_name": "pool-etl-night", "node_type_id": "Standard_E8ds_v5", "min_idle_instances": 0,
         "max_capacity": 30, "idle_instance_autotermination_minutes": 15, "azure_attributes": {"availability": "SPOT_WITH_FALLBACK_AZURE"}, "state": "ACTIVE",
         "custom_tags": tags(team="engineering"), "stats": {"used_count": 0, "idle_count": 0}},
    )]
    tag_rules = lambda *keys: {"custom_tags." + COST_ALLOCATION_TAGS[i]: {"type": "unlimited", "isOptional": False} for i in keys if len(COST_ALLOCATION_TAGS) > i}
    policies = [normalize_policy(p, "dbx_cluster_policies", reference, config) for p in (
        {"policy_id": "POL-PERSONAL-USE", "name": "pol-personal-use", "policy_family_id": "personal-vm",
         "definition": json.dumps({**tag_rules(0), "autotermination_minutes": {"type": "fixed", "value": 30}})},
        {"policy_id": "POL-DATA-SCIENCE", "name": "pol-data-science", "definition": json.dumps({**tag_rules(0, 1), "autotermination_minutes": {"type": "range", "maxValue": 120}})},
        {"policy_id": "POL-JOBS-PRODUCTION", "name": "pol-jobs-production", "definition": json.dumps(tag_rules(0, 1, 2))},
    )]
    job_cluster = lambda key, node, pol, avail, extra, **kw: {"job_cluster_key": key, "new_cluster": {
        "spark_version": kw.pop("version", "15.4.x-scala2.12"), "node_type_id": node, "policy_id": pol, "azure_attributes": {"availability": avail},
        "custom_tags": tags(**kw), "data_security_mode": "SINGLE_USER", **extra}}
    job_specs = [
        (1001, "etl-sales-daily", {"quartz_cron_expression": "0 0 2 * * ?"}, [job_cluster("jc-etl", "Standard_D8ds_v5", "POL-JOBS-PRODUCTION", "ON_DEMAND_AZURE",
          {"autoscale": {"min_workers": 2, "max_workers": 10}}, team="sales", project="etl-sales", cc="CC-100")], [("bronze", "jc-etl", None), ("silver", "jc-etl", None)]),
        (1002, "dashboard-refresh", {"quartz_cron_expression": "0 30 6 * * ?"}, [], [("refresh", None, "0915-081203-bivts01")]),
        (1003, "distributor-orders-export", {"quartz_cron_expression": "0 0 7 * * ?"}, [], [("export", None, "0915-081203-bivts01")]),
        (1004, "demand-forecast-weekly", {"quartz_cron_expression": "0 0 4 ? * MON"}, [job_cluster("jc-ml", "Standard_E8ds_v5", "POL-DATA-SCIENCE",
          "SPOT_WITH_FALLBACK_AZURE", {"num_workers": 6}, version="15.4.x-cpu-ml-scala2.12", team="data-science", project="demand-forecast")], [("train", "jc-ml", None)]),
        (1005, "data-quality-silver", {"quartz_cron_expression": "0 0 3 * * ?"}, [job_cluster("jc-quality", "Standard_DS3_v2", None, "ON_DEMAND_AZURE",
          {"num_workers": 4}, version="12.2.x-scala2.12")], [("validate", "jc-quality", None)]),
        (1006, "erp-ingest-continuous", None, [job_cluster("jc-stream", "Standard_D4ds_v5", "POL-JOBS-PRODUCTION", "ON_DEMAND_AZURE", {"num_workers": 2},
          team="engineering", project="erp-ingest", cc="CC-300")], [("stream", "jc-stream", None)]),
    ]
    jobs = []
    for jid, jname, schedule, clusters_spec, tasks in job_specs:
        settings = {"name": jname, "job_clusters": clusters_spec, "timeout_seconds": 7200, "email_notifications": {"on_failure": ["data@example.com"]},
                    "run_as": {"service_principal_name": "00000000-0000-4000-8000-0000000000c3"} if jid in (1001, 1006) else {"user_name": "ana.garcia@example.com"},
                    "tasks": [{"task_key": key, "job_cluster_key": jck, "existing_cluster_id": ecid, "notebook_task": {"notebook_path": "/Repos/data/" + jname + "/" + key}}
                              for key, jck, ecid in tasks]}
        settings.update({"schedule": schedule} if schedule else {"continuous": {"pause_status": "UNPAUSED"}})
        jobs.append(normalize_job({"job_id": jid, "creator_user_name": "ana.garcia@example.com", "settings": settings}, "dbx_jobs", reference, config))
    pipelines = [normalize_pipeline({"pipeline_id": "0c1d2e3f-orders", "name": "dlt-orders", "state": "IDLE", "catalog": "main", "target": "silver_orders",
                                     "serverless": False, "continuous": False}, "dbx_pipelines", reference, config)]
    warehouses = [normalize_warehouse(w, "dbx_sql_warehouses", reference, config) for w in (
        {"id": "a1b2c3d4e5f60718", "name": "wh-bi-sales", "state": "RUNNING", "cluster_size": "Medium", "warehouse_type": "PRO", "enable_serverless_compute": False,
         "auto_stop_mins": 0, "min_num_clusters": 1, "max_num_clusters": 2, "num_clusters": 1, "num_active_sessions": 0, "creator_name": "ana.garcia@example.com",
         "tags": {"custom_tags": [{"key": k, "value": v} for k, v in tags(team="sales").items()]}},
        {"id": "b2c3d4e5f6071829", "name": "wh-finance-serverless", "state": "STOPPED", "cluster_size": "Small", "warehouse_type": "PRO",
         "enable_serverless_compute": True, "auto_stop_mins": 10, "min_num_clusters": 1, "max_num_clusters": 1, "creator_name": "elena.sanz@example.com",
         "tags": {"custom_tags": [{"key": k, "value": v} for k, v in tags(team="finance", project="month-end-close", cc="CC-200").items()]}},
    )]
    scopes = [normalize_secret_scope({"name": "kv-data-prod", "backend_type": "AZURE_KEYVAULT",
                                      "keyvault_metadata": {"resource_id": kv, "dns_name": "https://kv-data-prod.vault.azure.net/"}}, "dbx_secret_scopes", reference, config)]
    metastore = normalize_metastore({"metastore_id": "ms-weu-demo", "name": "metastore-westeurope", "region": "westeurope",
                                     "storage_root": "abfss://metastore@stdatalakeprod.dfs.core.windows.net/root"}, "uc_metastore_summary", reference, config)
    catalogs = [normalize_catalog({"name": n, "catalog_type": "MANAGED_CATALOG", "storage_root": "abfss://" + n + "@stdatalakeprod.dfs.core.windows.net/" + n,
                                   "isolation_mode": "ISOLATED", "metastore_id": "ms-weu-demo"}, "uc_catalogs", reference, config) for n in ("main", "sales", "data_science")]
    schemas = [normalize_schema({"full_name": "main." + n, "name": n, "catalog_name": "main", "metastore_id": "ms-weu-demo"}, "uc_schemas", reference, config)
               for n in ("bronze_orders", "silver_orders")]
    creds = [normalize_storage_credential({"id": "sc-demo-01", "name": "cred-data-lake", "read_only": False,
                                           "azure_managed_identity": {"access_connector_id": ac}}, "uc_storage_credentials", reference, config)]
    locations = [normalize_external_location({"name": "ext-lake-curated", "url": "abfss://curated@stdatalakeprod.dfs.core.windows.net/", "credential_name": "cred-data-lake",
                                               "read_only": False, "metastore_id": "ms-weu-demo"}, "uc_external_locations", reference, config)]
    outbound = [normalize_outbound_endpoint({"category": "Webapp", "endpoints": [{"domainName": "westeurope.azuredatabricks.net", "endpointDetails": [{"port": 443}]}]},
                                            "arm_outbound_endpoints", reference, config)]
    inventory = {
        "clusters": clusters, "instance_pools": pools, "cluster_policies": policies, "jobs": jobs, "pipelines": pipelines, "sql_warehouses": warehouses,
        "secret_scopes": scopes, "global_init_scripts": [], "uc_metastore": metastore, "uc_catalogs": catalogs, "uc_schemas": schemas,
        "uc_storage_credentials": creds, "uc_external_locations": locations, "uc_connections": [], "outbound_endpoints": outbound, "related_resources": related,
    }
    counts = {"dbx_clusters": clusters, "dbx_instance_pools": pools, "dbx_cluster_policies": policies, "dbx_jobs": jobs, "dbx_pipelines": pipelines,
              "dbx_sql_warehouses": warehouses, "dbx_secret_scopes": scopes, "uc_catalogs": catalogs, "uc_schemas": schemas, "uc_storage_credentials": creds,
              "uc_external_locations": locations, "uc_connections": [], "arm_outbound_endpoints": outbound}
    sources = [source_receipt("arm_workspace", reference, records=1, pages=1)]
    sources += [source_receipt(sid, reference, records=len(rows), pages=1) for sid, rows in counts.items()]
    sources += [source_receipt(sid, reference, records=1, pages=1) for sid in ("arm_diagnostics", "dbx_workspace_conf", "uc_metastore_summary", "dbx_spark_versions", "dbx_node_types")]
    sources += [source_receipt("arm_managed_rg_inventory", reference, records=9, pages=1), source_receipt("dbx_init_scripts", reference, pages=1)]
    sources += [source_receipt("arm_resource_" + str(i + 1), reference, records=1, pages=1) for i in range(len(related))]
    sources += [
        source_receipt("uc_system_lineage", reference, "not_configured", "Runtime table/column lineage is never queried by this collector."),
        source_receipt("arm_advisor", reference, pages=1),
        source_receipt("azure_cost", reference, "not_configured", "Legacy cost_scope disabled in the simulated configuration."),
    ]
    cost_data = demo_cost_data(reference, inventory)
    sources.append(source_receipt("azure_cost_databricks", reference, records=sum(len(q["rows"]) for q in cost_data["queries"].values()),
                                  pages=len(cost_data["queries"]), metric=COST_METRIC,
                                  queries=[{"id": k, "status": "complete", "records": len(q["rows"]), "seconds": q["seconds"]} for k, q in cost_data["queries"].items()],
                                  note="SIMULATED Cost Management results (operation=self_test)."))
    billing = demo_system_billing(reference)
    sources.append(source_receipt("dbx_system_billing", reference, records=len(billing["rows"]), pages=1, warehouse_id=billing["warehouse_id"],
                                  note="SIMULATED system.billing.usage result: in production this source is OFF unless system_tables_warehouse_id is set."))
    return {
        "workspace": ws, "sources": sources, "inventory": inventory, "requirements": config["requirements"],
        "workspace_conf": {"enableTokensConfig": "true", "maxTokenLifetimeDays": "90", "enableIpAccessLists": "false",
                           "enableDbfsFileBrowser": "false", "enableExportNotebook": "true"},
        "arm_diagnostics": [{"id": config["id"] + "/providers/Microsoft.Insights/diagnosticSettings/diag-dbx", "name": "diag-dbx",
                             "logs": [{"category": "jobs", "enabled": True}, {"category": "clusters", "enabled": True}]}],
        "advisor": [], "cost_rows": [],
        "dbx_runtime_catalog": {
            "spark_versions": ["13.3.x-scala2.12", "14.3.x-scala2.12", "15.4.x-scala2.12", "15.4.x-cpu-ml-scala2.12", "16.4.x-scala2.12"],
            "node_types": {"Standard_DS3_v2": {"is_deprecated": False}, "Standard_DS4_v2": {"is_deprecated": False}},
        },
        "dbx_cost_data": cost_data,
        "system_billing": billing,
        "demo_roster": [{"workspace_id": config["id"], "workspace_name": name, "resource_group": rg, "workspace_host": host,
                         "environment": "PRODUCTION", "auth_mode": "same_tenant_uami", "cross_tenant": False}],
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
    raw["databricks_cost_model"] = cost_model = databricks_costs_for(raw, reference)
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
    head = cost_model.get("headline") or {}
    cost_message = (
        "Databricks cost " + en_amount(head["review_total"]) + " " + (cost_model.get("currency") or "") + " in " + en_month(head["review_month"])
        + " (" + en_amount(head.get("dbu_share"), 1) + "% DBU, " + en_amount(100 - (head.get("dbu_share") or 0), 1) + "% infrastructure)"
        + ("; " + en_amount(head["unattributed_share"], 1) + "% without a compute tag" if head.get("unattributed_share") is not None else "")
        + ("; estimated savings " + en_amount(head["estimated_monthly_savings"]) + " " + (cost_model.get("currency") or "") + "/month with documented rules."
           if head.get("estimated_monthly_savings") else ".")
    ) if head.get("review_total") is not None else (
        str(head.get("signals") or 0) + " cost optimization signals observed in the configuration; no cost data ("
        + str(cost_model.get("status")) + "), so no savings are estimated."
    )
    return {
        "schema_version": "1.0",
        "provenance": provenance,
        "environment": environment,
        "reference_utc": reference,
        "client": {"name": CLIENT_NAME, "logo_data_uri": CLIENT_LOGO_DATA_URI, "logo_alt": CLIENT_LOGO_ALT},
        "presentation": presentation_settings(),
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
        "databricks_costs": cost_model,
        "actions": actions_for(findings),
        "executive_messages": [
            cost_message,
            str(dep_counts["nodes_total"]) + " nodes in the dependency map (" + str(dep_counts["edges_observed"]) + " OBSERVED relationships, " + str(dep_counts["edges_inferred"]) + " explicit INFERRED relationships and " + str(dep_counts["unknowns_total"]) + " UNKNOWN blind spots).",
            str(len(findings)) + " observed configuration and dependency findings (" + str(critical) + " critical; the list is never padded to a top 5).",
            str(global_score["evaluated"]) + " of " + str(global_score["evaluated"] + global_score["not_evaluated"]) + " applicable checks evaluated; coverage is shown beside the local index.",
            str(dep_counts["broken_references_total"]) + " broken references found between job tasks, clusters, pools, policies, pipelines, warehouses and credentials.",
            str(len(blind_spots)) + " sources partial, denied or not configured; no cluster was started for this review.",
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
    heads = [((s.get("databricks_costs") or {}).get("headline") or {}, (s.get("databricks_costs") or {}).get("currency")) for s in snapshots]
    currencies = {cur for head, cur in heads if head.get("review_total") is not None}
    comparable = bool(heads) and len(currencies) == 1 and all(head.get("review_total") is not None for head, _ in heads)
    return {
        "schema_version": "databricks-dep-multi-workspace-v1",
        "reference_utc": reference,
        "provenance": next(iter(provenances)) if provenances else "LIVE",
        "client": {"name": CLIENT_NAME, "logo_data_uri": CLIENT_LOGO_DATA_URI, "logo_alt": CLIENT_LOGO_ALT},
        "presentation": presentation_settings(),
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
            "databricks_costs": {
                "currency": next(iter(currencies)) if comparable else None,
                "review_total": round(sum(head["review_total"] for head, _ in heads), 2) if comparable else None,
                "estimated_monthly_savings": round(sum(head.get("estimated_monthly_savings") or 0 for head, _ in heads), 2) if comparable else None,
            },
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
        "databricks_costs": cost_summary(snapshot.get("databricks_costs")),
    }


def cost_rows_for_query(snapshot):
    model = snapshot.get("databricks_costs") or {}
    currency = model.get("currency")
    head = model.get("headline") or {}
    rows = [{"record_type": "headline", "name": "databricks_costs", **(cost_summary(model) or {}),
             "mtd_total": head.get("mtd_total"), "previous_total": head.get("previous_total")}]
    for s in model.get("signals", []):
        rows.append({
            "record_type": "signal", "id": s["id"], "code": s["code"], "severity": s["severity"], "title": s["title"],
            "name": s["object_name"], "workload_name": s["object_name"], "kind": s["object_kind"], "monthly_cost": s["monthly_cost"],
            "estimated_monthly_saving": s["estimated_monthly_saving"], "saving_kind": s["saving_kind"], "counted": s["counted"],
            "currency": currency, "recommendation": s["recommendation"],
        })
    for r in ((model.get("attribution") or {}).get("rows") or [])[:60]:
        rows.append({
            "record_type": "attribution", "dimension": r["dimension"], "name": r["name"], "workload_name": r["name"], "kind": r["kind"],
            "total": r["total"], "dbu": r["dbu"], "infra": r["infra"], "previous_total": r["previous_total"], "share": r["share"],
            "creator": r["creator"], "tags": r["tags"], "currency": currency,
        })
    return rows


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
        "costs": cost_rows_for_query(snapshot),
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
        "operation": "self_test" if snapshot.get("provenance") == "SIMULATED" else "report",
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
        "databricks_costs": aggregate["databricks_costs"] if multi else cost_summary(snapshot.get("databricks_costs")),
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
        if operation == "self_test":
            validate_cost_settings()
            presentation_settings()
            validate_logo(CLIENT_LOGO_DATA_URI, CLIENT_LOGO_ALT)
            if not CATALOG.get("rules"):
                raise EvidenceError("catalog_missing", "Use the build-generated whole-file tool, not unbuilt engine.py.", "rule_catalog")
            reference = utc_now()
            raw = demo_raw(reference)
            snapshot = finish_snapshot(raw, reference, provenance="SIMULATED", environment="PRODUCTION")
            snapshot.update(available_workspaces=raw["demo_roster"], selected_workspace_names=[raw["demo_roster"][0]["workspace_name"]])
            return write_report(snapshot)
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

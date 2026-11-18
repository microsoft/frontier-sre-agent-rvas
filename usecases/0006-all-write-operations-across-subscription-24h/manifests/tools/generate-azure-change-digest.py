# generate-azure-change-digest
# Python tool for Azure SRE Agent: daily digest of RELEVANT Azure control-plane changes.
# Source: Change Analysis in Azure Resource Graph (resourcechanges, resourcecontainerchanges),
# new role assignments (authorizationresources) and optional Activity Log gap events
# (role assignment deletes, locks, diagnostic settings, policy assignments).
# READ ONLY. The SRE Agent managed identity needs Reader on the configured subscriptions
# (or management group). Optional: Microsoft Graph Application.Read.All (ENABLE_GRAPH_NAMES).
# It never creates, modifies or deletes anything.
# BEFORE PASTING IT into the Builder, replace <YOUR_MANAGED_IDENTITY_CLIENT_ID> and
# <YOUR_SUBSCRIPTION_ID> in the CONFIGURE block. A Client ID or a Subscription ID is not a secret.
# Version 1.0 - November 2026

import base64
import csv
import html
import io
import json
import os
import re
import ssl
import tempfile
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone, tzinfo
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener
from uuid import UUID, uuid4

# ============================== CONFIGURE ==============================
MANAGED_IDENTITY_CLIENT_ID = "<YOUR_MANAGED_IDENTITY_CLIENT_ID>"
SUBSCRIPTION_IDS = ["<YOUR_SUBSCRIPTION_ID>"]        # or leave empty and set MANAGEMENT_GROUP_ID
MANAGEMENT_GROUP_ID = ""                              # ARG managementGroups scope (first 10,000 subscriptions)
BUSINESS_TIMEZONE = "Europe/Madrid"                   # IANA tz; DST-aware via zoneinfo
BUSINESS_HOURS = (8, 20)                              # local [start, end)
BUSINESS_DAYS = (0, 1, 2, 3, 4)                       # Mon-Fri
PROD_TAGS = {"environment": ["prod", "pro", "production"]}   # RG/resource tags marking production (click-ops flag)
EXPECTED_AUTOMATION = {}                              # {"<appId or UPN>": "Pipeline name"}: known IaC/pipeline identities
EXCLUDED_RESOURCE_GROUPS = []                         # regexes, e.g. r"^rg-sandbox-"
EXCLUDED_RESOURCE_TYPES = []                          # e.g. "microsoft.azurearcdata/sqlserverinstances"
ENABLE_ACTIVITY_LOG_GAPS = True                       # role-assignment deletes, locks, diagnostic settings, policy (Reader)
ENABLE_GRAPH_NAMES = False                            # needs Application.Read.All on the MI; degrades gracefully
CLIENT_NAME = ""                                      # optional organization name shown in the report header
OUTPUT_DIRECTORY = "change-digest-reports"            # fixed child folder of the working directory
MAX_PAGES = 25
MAX_CHANGES = 25_000
MAX_ACTIVITY_LOG_LOOKUPS = 10
MAX_COLLECTION_SECONDS = 100
# =======================================================================

TOOL_NAME = "generate-azure-change-digest"
TOOL_VERSION = "1.0"
ARM = "https://management.azure.com"
GRAPH = "https://graph.microsoft.com"
ARG_API_VERSION = "2024-04-01"
ACTIVITY_LOG_API_VERSION = "2015-04-01"
ROLE_DEFINITIONS_API_VERSION = "2022-04-01"
SUBSCRIPTION_API_VERSION = "2022-12-01"
SIDECAR_TOKEN_ISSUER = "adc-msi-sidecar"
TOKEN_AUDIENCES = {
    ARM: ("https://management.azure.com", "https://management.core.windows.net"),
    GRAPH: ("https://graph.microsoft.com", "00000003-0000-0000-c000-000000000000"),
}
TRANSPORT_BYTES = 3500
ARTIFACT_BYTES = 4_800_000
HTTP_BYTES = 16_000_000
MAX_HTTP_REQUESTS = 150
MAX_SUBSCRIPTIONS_PER_QUERY = 300
MAX_ACTIVITY_LOG_SUBSCRIPTIONS = 10
MAX_ROLE_DEFINITION_LOOKUPS = 20
MAX_LOOKUP_IDS = 100
MAX_TABLE_ROWS = 2000
RETENTION_DAYS = 14

OPERATIONS = ("report", "query")
PERIODS = {"last_24h": timedelta(hours=24), "last_7d": timedelta(days=7), "last_14d": timedelta(days=14)}
PERIOD_LABELS = {"last_24h": "Last 24 hours", "last_7d": "Last 7 days", "last_14d": "Last 14 days"}
MIN_LEVELS = ("high", "medium", "low")
VIEWS = ("summary", "relevant", "deletes", "security", "actors", "unusual", "rbac", "noise", "coverage")
RANK = {"high": 3, "medium": 2, "low": 1, "noise": 0}
LOWER = {"high": "medium", "medium": "low", "low": "low", "noise": "noise"}

# Path taxonomy. Patterns are valid for both Python re and the RE2 engine of Azure Resource Graph
# (no look-around), so the server-side noise pre-filter and the Python classifier agree.
NOISE_PATTERN = (
    r"(?i)(^|\.)(provisioningstate|etag|resourceguid|timecreated)$"
    r"|(^|\.)last[a-z]*(time|date|updated|timeutc|modified|modifiedat|modifiedon|modifiedutc|modifiedtime|modifieddate)$"
    r"|statuslastupdated$|^systemdata\.|^properties\.settings\.(activityid|starttime)$|^properties\.migration\."
    r"|spaceavailablemb|databasecreationdate|^properties\.diskstate$|ipconfigurations\[\d+\]\.id$|^properties\.macaddress$"
    r"|\.instanceview\."
)
AGENT_PATTERN = (
    r"(?i)usedspaceinbytes|maxsizeinbytes|totalphysicalmemoryinbytes|^properties\.detectedproperties\.|processors\[|processornames"
    r"|^properties\.networkprofile\.networkinterfaces\[\d+\]\.ipaddresses"
)
POWER_PATH_PATTERN = r"(?i)powerstate"
POWER_OP_PATTERN = r"(?i)/(start|deallocate|poweroff|restart|redeploy|reimage)/action$"
NOISE_RX = re.compile(NOISE_PATTERN)
AGENT_RX = re.compile(AGENT_PATTERN)
POWER_PATH_RX = re.compile(POWER_PATH_PATTERN)
POWER_OP_RX = re.compile(POWER_OP_PATTERN)
EXT_UPGRADE_RX = re.compile(r"(?i)typehandlerversion$|autoupgrademinorversion$")
NIC_ATTACH_RX = re.compile(r"(?i)^properties\.(virtualmachine\.id|primary)$")
AUTOSCALE_RX = re.compile(r"(?i)^sku\.capacity$|agentpoolprofiles\[\d+\]\.count$|^properties\.count$")
SECURITY_RX = re.compile(
    r"(?i)publicnetworkaccess|networkacls|iprules|virtualnetworkrules|firewallrules|securityrules|defaultaction"
    r"|allowblobpublicaccess|minimumtlsversion|mintlsversion|minimaltlsversion|accesspolicies|enablerbacauthorization"
    r"|enablesoftdelete|enablepurgeprotection|privateendpointconnections|disablelocalauth|allowsharedkeyaccess"
    r"|supportshttpstraffic|httpsonly|ftpsstate|^identity\.|encryption|sourceaddressprefix|destinationportrange|\.access$"
    r"|publicipaddress|authenticateduser|incidentmanagementconfiguration|allowcrosstenantreplication|anonymouspullenabled"
    r"|adminuserenabled|azureadonlyauthentication|authorizedipranges|enableprivatecluster|apiserveraccessprofile"
    r"|disablepasswordauthentication|routes\[|nexthop|rulecollections|natrules|applicationrules|networkrules"
)
SIZE_RX = re.compile(r"(?i)^sku\.(name|tier|size|family|capacity)$|vmsize|^properties\.tier$|disksizegb|disksizebytes|storageaccounttype")
MONITOR_RX = re.compile(r"(?i)^properties\.(criteria|enabled|actions|scopes|severity|evaluationfrequency|windowsize|targetresourcetypes|emailreceivers|webhookreceivers|smsreceivers)")
GUID_RX = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
RULE_RX = re.compile(r"(?i)^properties\.securityrules\[(\d+)\]\.(?:properties\.)?([a-z]+)(?:\[\d+\])?$")
RG_NAME_RX = re.compile(r"^[A-Za-z0-9_.()\-]{0,90}$")
PLACEHOLDER_RX = re.compile(r"^\s*<[^>]*>\s*$")

VM_TYPE = "microsoft.compute/virtualmachines"
NIC_TYPE = "microsoft.network/networkinterfaces"
NSG_TYPE = "microsoft.network/networksecuritygroups"
PIP_TYPE = "microsoft.network/publicipaddresses"
RG_TYPE = "microsoft.resources/subscriptions/resourcegroups"
SECURITY_TYPES = frozenset({
    NSG_TYPE, "microsoft.network/networksecuritygroups/securityrules", "microsoft.network/azurefirewalls",
    "microsoft.network/firewallpolicies", "microsoft.network/firewallpolicies/rulecollectiongroups",
    "microsoft.network/routetables", "microsoft.network/applicationgateways",
    "microsoft.network/applicationgatewaywebapplicationfirewallpolicies",
    "microsoft.network/frontdoorwebapplicationfirewallpolicies", PIP_TYPE, "microsoft.network/privateendpoints",
    "microsoft.network/bastionhosts", "microsoft.network/networksecurityperimeters", "microsoft.keyvault/vaults",
    "microsoft.managedidentity/userassignedidentities",
})
MONITOR_TYPES = frozenset({
    "microsoft.insights/scheduledqueryrules", "microsoft.insights/metricalerts", "microsoft.insights/activitylogalerts",
    "microsoft.insights/actiongroups", "microsoft.insights/datacollectionrules", "microsoft.alertsmanagement/actionrules",
})
DATA_TYPES = frozenset({
    "microsoft.storage/storageaccounts", "microsoft.sql/servers", "microsoft.sql/servers/databases",
    "microsoft.documentdb/databaseaccounts", "microsoft.dbforpostgresql/flexibleservers",
    "microsoft.dbformysql/flexibleservers", "microsoft.recoveryservices/vaults", "microsoft.operationalinsights/workspaces",
    "microsoft.network/virtualnetworks", "microsoft.containerservice/managedclusters", "microsoft.cache/redis",
    "microsoft.compute/disks",
})
CRITICAL_TYPES = SECURITY_TYPES | MONITOR_TYPES | DATA_TYPES
FIRST_PARTY_CLIENTS = frozenset({"azure container service", "vs devtest lab", "azure kubernetes service", "azure backup",
                                 "azure site recovery", "azure policy", "azure security center", "microsoft defender for cloud"})
INTERNET_SOURCES = frozenset({"*", "internet", "0.0.0.0/0", "0.0.0.0", "any", "::/0"})
SENSITIVE_PORTS = {22: "SSH", 3389: "RDP", 445: "SMB", 1433: "SQL Server", 3306: "MySQL", 5432: "PostgreSQL",
                   5985: "WinRM", 5986: "WinRM", 23: "Telnet", 21: "FTP", 135: "RPC", 139: "NetBIOS",
                   27017: "MongoDB", 6379: "Redis", 9200: "Elasticsearch"}
PRIVILEGED_ROLES = frozenset({"owner", "user access administrator", "contributor", "role based access control administrator"})
BUILTIN_ROLES = {
    "8e3af657-a8ff-443c-a75c-2fe8c4bcb635": "Owner",
    "b24988ac-6180-42a0-ab88-20f7382dd24c": "Contributor",
    "acdd72a7-3385-48ef-bd42-f606fba81ae7": "Reader",
    "18d7d88d-d35e-4fb5-a5c3-7773c20a72d9": "User Access Administrator",
    "f58310d9-a9f6-439a-9e8d-f62e7b41a168": "Role Based Access Control Administrator",
}
GAP_OPERATIONS = {
    "microsoft.authorization/roleassignments/delete": ("high", "Role assignment removed"),
    "microsoft.authorization/locks/write": ("medium", "Resource lock created or changed"),
    "microsoft.authorization/locks/delete": ("high", "Resource lock removed"),
    "microsoft.authorization/policyassignments/write": ("medium", "Policy assignment created or changed"),
    "microsoft.authorization/policyassignments/delete": ("high", "Policy assignment removed"),
    "microsoft.authorization/policyexemptions/write": ("medium", "Policy exemption created or changed"),
    "microsoft.authorization/policyexemptions/delete": ("medium", "Policy exemption removed"),
    "microsoft.authorization/roledefinitions/write": ("high", "Custom role definition created or changed"),
    "microsoft.authorization/roledefinitions/delete": ("high", "Custom role definition removed"),
    "microsoft.insights/diagnosticsettings/write": ("medium", "Diagnostic setting created or changed"),
    "microsoft.insights/diagnosticsettings/delete": ("high", "Diagnostic setting removed (monitoring gap)"),
}
NOT_COVERED = ["data-plane", "app-service-files", "rbac-deletes-without-activity-log", "locks", "diagnostic-settings", "policy"]
LEARN_SOURCES = [
    "https://learn.microsoft.com/azure/governance/resource-graph/changes/get-resource-changes",
    "https://learn.microsoft.com/azure/governance/resource-graph/changes/resource-graph-changes",
    "https://learn.microsoft.com/azure/governance/resource-graph/changes/view-resource-changes",
    "https://learn.microsoft.com/azure/governance/resource-graph/concepts/work-with-data",
    "https://learn.microsoft.com/azure/governance/resource-graph/concepts/guidance-for-throttled-requests",
    "https://learn.microsoft.com/azure/azure-monitor/platform/activity-log",
    "https://learn.microsoft.com/azure/sre-agent/overview",
]

TYPE_LABELS = {
    NSG_TYPE: "Network security group", "microsoft.keyvault/vaults": "Key Vault",
    "microsoft.storage/storageaccounts": "Storage account", VM_TYPE: "Virtual machine",
    "microsoft.compute/disks": "Managed disk", PIP_TYPE: "Public IP address",
    "microsoft.compute/virtualmachinescalesets": "VM scale set", "microsoft.containerservice/managedclusters": "AKS cluster",
    "microsoft.network/virtualnetworks": "Virtual network", NIC_TYPE: "Network interface",
    "microsoft.insights/scheduledqueryrules": "Log alert rule", "microsoft.insights/actiongroups": "Action group",
    "microsoft.insights/metricalerts": "Metric alert rule", "microsoft.insights/activitylogalerts": "Activity log alert",
    "microsoft.insights/datacollectionrules": "Data collection rule",
    "microsoft.managedidentity/userassignedidentities": "Managed identity",
    "microsoft.hybridcompute/machines": "Arc-enabled server", "microsoft.hybridcompute/machines/extensions": "Arc server extension",
    "microsoft.compute/virtualmachines/extensions": "VM extension", RG_TYPE: "Resource group",
    "microsoft.resources/subscriptions": "Subscription", "microsoft.network/azurefirewalls": "Azure Firewall",
    "microsoft.network/firewallpolicies": "Firewall policy", "microsoft.network/routetables": "Route table",
    "microsoft.network/applicationgateways": "Application gateway", "microsoft.network/privateendpoints": "Private endpoint",
    "microsoft.network/bastionhosts": "Bastion host", "microsoft.network/networksecurityperimeters": "Network security perimeter",
    "microsoft.sql/servers": "SQL server", "microsoft.sql/servers/databases": "SQL database", "microsoft.web/sites": "App Service",
    "microsoft.web/connections": "API connection", "microsoft.operationalinsights/workspaces": "Log Analytics workspace",
    "microsoft.azurearcdata/sqlserverinstances": "Arc SQL Server instance",
    "microsoft.azurearcdata/sqlserverinstances/databases": "Arc SQL database", "microsoft.app/agents": "SRE Agent",
    "microsoft.dashboard/grafana": "Managed Grafana", "microsoft.logic/workflows": "Logic App",
    "microsoft.recoveryservices/vaults": "Recovery Services vault", "microsoft.documentdb/databaseaccounts": "Cosmos DB account",
}
CLIENT_LABELS = {"click-ops": "Click-ops (portal / browser)", "script": "Script / CLI", "iac": "IaC / deployment",
                 "sdk": "SDK / automation", "service": "Azure service", "unknown-app": "Unknown client app",
                 "unspecified": "Unspecified"}
ACTOR_LABELS = {"human": "Human", "automation": "Automation", "expected-automation": "Expected automation",
                "platform": "Platform", "unknown": "Unknown"}


class DigestError(RuntimeError):
    def __init__(self, code, message, source="digest", http_status=None):
        super().__init__(message)
        self.code = code
        self.source = source
        self.http_status = http_status

    def public(self):
        return {"code": self.code, "message": str(self), "source": self.source, "http_status": self.http_status}


def utc_now():
    return datetime.now(timezone.utc).replace(microsecond=0)


def iso(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if dt else ""


def parse_time(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 64:
        return None
    text_value = value.strip().replace("Z", "+00:00")
    match = re.match(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(\.\d+)?(.*)$", text_value)
    if match:
        text_value = match.group(1) + ((match.group(2) or "")[:7]) + match.group(3)
    try:
        parsed = datetime.fromisoformat(text_value)
    except ValueError:
        return None
    return (parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)


def clean(value, limit=600):
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    text_value = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", str(value)).strip()
    return text_value if len(text_value) <= limit else text_value[:limit - 1] + "\u2026"


def is_guid(value):
    return isinstance(value, str) and bool(GUID_RX.match(value.strip()))


def norm_type(value):
    return clean(value, 300).lower()


def type_label(rtype):
    if rtype in TYPE_LABELS:
        return TYPE_LABELS[rtype]
    tail = rtype.split("/", 1)[-1] if "/" in rtype else rtype
    return tail.replace("/", " / ")


def resource_name_of(resource_id):
    parts = [p for p in (resource_id or "").split("/") if p]
    return parts[-1] if parts else ""


def short_change_id(change_id):
    return (change_id or "").rsplit("/", 1)[-1]


def kql_text(value):
    """Embed a validated identifier in a KQL single-quoted string literal."""
    if not isinstance(value, str) or re.search(r"['\"\\\r\n]", value):
        raise DigestError("unsafe_query_value", "Refused to embed an unsafe value in a Resource Graph query.", "query")
    return "'" + value + "'"


def kql_list(values):
    return "(" + ", ".join(kql_text(v) for v in values) + ")" if values else "('')"


# ------------------------- business time zone (DST-aware) -------------------------
EU_CENTRAL_ZONES = {"Europe/Madrid", "Europe/Paris", "Europe/Berlin", "Europe/Rome", "Europe/Amsterdam", "Europe/Brussels",
                    "Europe/Vienna", "Europe/Zurich", "Europe/Stockholm", "Europe/Oslo", "Europe/Copenhagen", "Europe/Warsaw",
                    "Europe/Prague", "Europe/Budapest", "Europe/Luxembourg", "Europe/Belgrade", "Europe/Zagreb", "Europe/Ljubljana"}
EU_WESTERN_ZONES = {"Europe/London", "Europe/Lisbon", "Europe/Dublin", "Atlantic/Canary"}


def _last_sunday(year, month):
    day = datetime(year, month + 1, 1) - timedelta(days=1) if month < 12 else datetime(year, 12, 31)
    return day - timedelta(days=(day.weekday() + 1) % 7)


class EuropeanRuleZone(tzinfo):
    """Fallback when zoneinfo/tzdata is unavailable: EU rule, DST from the last Sunday of March to the last Sunday of October, 01:00 UTC."""

    def __init__(self, std_hours, std_name, dst_name):
        self.std = timedelta(hours=std_hours)
        self.names = (std_name, dst_name)

    def _is_dst_utc(self, utc_naive):
        start = _last_sunday(utc_naive.year, 3).replace(hour=1)
        end = _last_sunday(utc_naive.year, 10).replace(hour=1)
        return start <= utc_naive < end

    def fromutc(self, dt):
        utc_naive = dt.replace(tzinfo=None)
        dst = self._is_dst_utc(utc_naive)
        end = _last_sunday(utc_naive.year, 10).replace(hour=1)
        fold = 1 if not dst and end <= utc_naive < end + timedelta(hours=1) else 0
        return (utc_naive + self.std + (timedelta(hours=1) if dst else timedelta(0))).replace(tzinfo=self, fold=fold)

    def utcoffset(self, dt):
        return self.std + self.dst(dt)

    def dst(self, dt):
        if dt is None:
            return timedelta(0)
        local = dt.replace(tzinfo=None)
        as_dst = self._is_dst_utc(local - self.std - timedelta(hours=1))
        as_std = not self._is_dst_utc(local - self.std)
        if as_dst and as_std:
            return timedelta(0) if getattr(dt, "fold", 0) else timedelta(hours=1)
        return timedelta(hours=1) if as_dst else timedelta(0)

    def tzname(self, dt):
        return self.names[1] if self.dst(dt) else self.names[0]


def business_zone(name=None):
    name = name or BUSINESS_TIMEZONE
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(name), "zoneinfo"
    except Exception:
        if name in EU_CENTRAL_ZONES:
            return EuropeanRuleZone(1, "CET", "CEST"), "built-in EU DST rule (zoneinfo unavailable)"
        if name in EU_WESTERN_ZONES:
            return EuropeanRuleZone(0, "WET" if name != "Europe/London" else "GMT", "WEST" if name != "Europe/London" else "BST"), "built-in EU DST rule (zoneinfo unavailable)"
        return timezone.utc, "UTC fallback (time zone not available)"


def local_label(dt, zone):
    local = dt.astimezone(zone)
    return local.strftime("%Y-%m-%d %H:%M ") + (local.tzname() or "")


def is_after_hours(dt, zone, hours=None, days=None):
    hours = hours or BUSINESS_HOURS
    days = BUSINESS_DAYS if days is None else days
    local = dt.astimezone(zone)
    return local.weekday() not in days or not (hours[0] <= local.hour < hours[1])


# ------------------------- configuration and parameters -------------------------
def validate_config():
    client = MANAGED_IDENTITY_CLIENT_ID
    if not isinstance(client, str) or PLACEHOLDER_RX.match(client) or not is_guid(client):
        raise DigestError("configuration_required",
                          "Configuration required: set MANAGED_IDENTITY_CLIENT_ID in the CONFIGURE block to the Client ID "
                          "(GUID) of the Azure SRE Agent managed identity. It is not a secret.", "configuration")
    mg = MANAGEMENT_GROUP_ID.strip() if isinstance(MANAGEMENT_GROUP_ID, str) else None
    if mg is None or (mg and not re.fullmatch(r"[A-Za-z0-9_().\-]{1,90}", mg)):
        raise DigestError("configuration_required", "MANAGEMENT_GROUP_ID must be empty or a management group ID.", "configuration")
    if not isinstance(SUBSCRIPTION_IDS, (list, tuple)):
        raise DigestError("configuration_required", "SUBSCRIPTION_IDS must be a list of subscription IDs.", "configuration")
    subscriptions, placeholders = [], 0
    for value in SUBSCRIPTION_IDS:
        if isinstance(value, str) and PLACEHOLDER_RX.match(value):
            placeholders += 1
            continue
        if not is_guid(value):
            raise DigestError("configuration_required", "Every SUBSCRIPTION_IDS entry must be a subscription ID (GUID).", "configuration")
        if value.strip().lower() not in subscriptions:
            subscriptions.append(value.strip().lower())
    if placeholders and not mg:
        raise DigestError("configuration_required",
                          "Configuration required: replace <YOUR_SUBSCRIPTION_ID> in SUBSCRIPTION_IDS (or leave the list empty "
                          "and set MANAGEMENT_GROUP_ID).", "configuration")
    if not subscriptions and not mg:
        raise DigestError("configuration_required", "Configure at least one subscription in SUBSCRIPTION_IDS or a MANAGEMENT_GROUP_ID.", "configuration")
    if not isinstance(BUSINESS_TIMEZONE, str) or not re.fullmatch(r"[A-Za-z0-9_+\-/]{1,64}", BUSINESS_TIMEZONE):
        raise DigestError("configuration_required", "BUSINESS_TIMEZONE must be an IANA time zone such as Europe/Madrid.", "configuration")
    hours = tuple(BUSINESS_HOURS) if isinstance(BUSINESS_HOURS, (list, tuple)) else ()
    if len(hours) != 2 or not all(isinstance(h, int) and not isinstance(h, bool) for h in hours) or not 0 <= hours[0] < hours[1] <= 24:
        raise DigestError("configuration_required", "BUSINESS_HOURS must be (start, end) local hours with 0 <= start < end <= 24.", "configuration")
    days = tuple(BUSINESS_DAYS) if isinstance(BUSINESS_DAYS, (list, tuple)) else (None,)
    if not all(isinstance(d, int) and not isinstance(d, bool) and 0 <= d <= 6 for d in days):
        raise DigestError("configuration_required", "BUSINESS_DAYS must contain weekday numbers 0 (Monday) to 6 (Sunday).", "configuration")
    if not isinstance(PROD_TAGS, dict) or not all(isinstance(k, str) and isinstance(v, (list, tuple)) for k, v in PROD_TAGS.items()):
        raise DigestError("configuration_required", 'PROD_TAGS must look like {"environment": ["prod", "production"]}.', "configuration")
    prod_tags = {k.strip().lower(): {str(x).strip().lower() for x in v} for k, v in PROD_TAGS.items() if k.strip()}
    if not isinstance(EXPECTED_AUTOMATION, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in EXPECTED_AUTOMATION.items()):
        raise DigestError("configuration_required", 'EXPECTED_AUTOMATION must look like {"<appId or UPN>": "Pipeline name"}.', "configuration")
    expected = {k.strip().lower(): clean(v, 80) for k, v in EXPECTED_AUTOMATION.items() if k.strip()}
    rg_patterns = []
    if not isinstance(EXCLUDED_RESOURCE_GROUPS, (list, tuple)) or len(EXCLUDED_RESOURCE_GROUPS) > 50:
        raise DigestError("configuration_required", "EXCLUDED_RESOURCE_GROUPS must be a list of up to 50 regexes.", "configuration")
    for pattern in EXCLUDED_RESOURCE_GROUPS:
        if (not isinstance(pattern, str) or not pattern or len(pattern) > 200 or re.search(r"['\r\n]|\(\?[=!<]|\\[1-9]", pattern)):
            raise DigestError("configuration_required", "EXCLUDED_RESOURCE_GROUPS entries must be simple regexes without quotes, look-around or back-references.", "configuration")
        try:
            rg_patterns.append(re.compile("(?i)" + pattern))
        except re.error as exc:
            raise DigestError("configuration_required", "Invalid regex in EXCLUDED_RESOURCE_GROUPS.", "configuration") from exc
    if not isinstance(EXCLUDED_RESOURCE_TYPES, (list, tuple)) or not all(
            isinstance(t, str) and re.fullmatch(r"[A-Za-z0-9.\-]+(/[A-Za-z0-9.\-]+)+", t.strip()) for t in EXCLUDED_RESOURCE_TYPES):
        raise DigestError("configuration_required", "EXCLUDED_RESOURCE_TYPES must contain resource types such as microsoft.compute/disks.", "configuration")
    if not isinstance(CLIENT_NAME, str) or len(CLIENT_NAME) > 80 or re.search(r"[\x00-\x1f\x7f<>]", CLIENT_NAME):
        raise DigestError("configuration_required", "CLIENT_NAME must be plain text of up to 80 characters.", "configuration")
    if not isinstance(OUTPUT_DIRECTORY, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,62}", OUTPUT_DIRECTORY):
        raise DigestError("configuration_required", "OUTPUT_DIRECTORY must be a single lowercase folder name such as change-digest-reports.", "configuration")
    for name, value, low, high in (("MAX_PAGES", MAX_PAGES, 1, 100), ("MAX_CHANGES", MAX_CHANGES, 100, 100_000),
                                   ("MAX_ACTIVITY_LOG_LOOKUPS", MAX_ACTIVITY_LOG_LOOKUPS, 0, 50),
                                   ("MAX_COLLECTION_SECONDS", MAX_COLLECTION_SECONDS, 20, 130)):
        if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
            raise DigestError("configuration_required", f"{name} must be an integer from {low} to {high}.", "configuration")
    return {
        "client_id": client.strip().lower(), "subscriptions": subscriptions, "management_group": mg,
        "hours": hours, "days": days, "prod_tags": prod_tags, "expected": expected, "rg_patterns": rg_patterns,
        "rg_pattern_text": [p for p in EXCLUDED_RESOURCE_GROUPS], "excluded_types": sorted({t.strip().lower() for t in EXCLUDED_RESOURCE_TYPES}),
        "client_name": CLIENT_NAME.strip(),
    }


def _enum(name, value, choices, default):
    if value is None:
        return default
    if not isinstance(value, str) or value.strip().lower() not in choices:
        raise DigestError("invalid_parameter", f"{name} must be one of: {', '.join(choices)}.", "parameters")
    return value.strip().lower()


def validate_parameters(operation="report", period="last_24h", min_level="medium", view="summary", resource_group="", limit=25, now=None):
    operation = _enum("operation", operation, OPERATIONS, "report")
    period = _enum("period", period, tuple(PERIODS), "last_24h")
    min_level = _enum("min_level", min_level, MIN_LEVELS, "medium")
    view = _enum("view", view, VIEWS, "summary")
    if resource_group is None:
        resource_group = ""
    if not isinstance(resource_group, str) or not RG_NAME_RX.fullmatch(resource_group.strip()):
        raise DigestError("invalid_parameter", "resource_group must be a resource group name or part of one (letters, digits, "
                                               "'_', '-', '.', '(' and ')', up to 90 characters).", "parameters")
    resource_group = resource_group.strip()
    if limit is None:
        limit = 25
    if isinstance(limit, str) and re.fullmatch(r"\s*\d{1,3}\s*", limit):
        limit = int(limit)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise DigestError("invalid_parameter", "limit must be an integer from 1 to 100.", "parameters")
    if operation == "report" and (view != "summary" or limit != 25):
        raise DigestError("invalid_combination", "view and limit apply only to operation=query. operation=report always writes "
                                                 "the complete digest; use operation=query for chat views.", "parameters")
    end = (now or utc_now()).replace(microsecond=0)
    start = end - PERIODS[period]
    return {"operation": operation, "period": period, "min_level": min_level, "view": view,
            "resource_group": resource_group, "limit": limit,
            "window": {"period": period, "label": PERIOD_LABELS[period], "start": start, "end": end,
                       "start_utc": iso(start), "end_utc": iso(end)}}


def rg_excluded(config, resource_group):
    return bool(resource_group) and any(p.search(resource_group) for p in config["rg_patterns"])


def rg_focus(params, resource_group):
    focus = params["resource_group"].lower()
    return not focus or focus in (resource_group or "").lower()


# ------------------------- identity and read-only HTTP -------------------------
def normalize_sidecar_claims(claims):
    """Map Azure SRE Agent sandbox token claims onto the standard Entra names.

    Python tools in the SRE Agent sandbox receive placeholder tokens issued by the identity sidecar
    (iss "adc-msi-sidecar") that the platform proxy replaces with the real managed identity token at egress.
    They carry tid, clientId and scp instead of aud/appid.
    """
    if not isinstance(claims, dict) or claims.get("iss") != SIDECAR_TOKEN_ISSUER:
        return claims
    scope = claims.get("scp") if isinstance(claims.get("scp"), str) else ""
    audience = scope[:-len("/.default")] if scope.endswith("/.default") else scope
    if audience.rstrip("/").lower() == "https://management.core.windows.net":
        audience = "https://management.azure.com"
    return dict(claims, appid=claims.get("clientId") or claims.get("cid") or None, aud=audience or None)


def claim_check(token, client_id, origin):
    """Lenient, informational check: never fails the run (the sandbox proxy swaps placeholder tokens at egress)."""
    try:
        part = token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))
    except Exception:
        return "unreadable token (continuing)"
    sidecar = isinstance(claims, dict) and claims.get("iss") == SIDECAR_TOKEN_ISSUER
    claims = normalize_sidecar_claims(claims)
    if not isinstance(claims, dict):
        return "unreadable token (continuing)"
    client = str(claims.get("appid") or claims.get("azp") or "").lower()
    audience = str(claims.get("aud") or "").rstrip("/").lower()
    label = "sidecar placeholder token" if sidecar else "token"
    if client == client_id.lower() and audience in TOKEN_AUDIENCES.get(origin, (origin,)):
        return "verified " + label
    return label + " not matched to the configured identity (continuing)"


class Identity:
    def __init__(self, client_id):
        try:
            from azure.identity import ManagedIdentityCredential
        except ImportError as exc:
            raise DigestError("dependency_missing", "azure-identity is required; it is available in the Azure SRE Agent Python runtime.", "identity") from exc
        self.client_id = client_id
        self.credential = ManagedIdentityCredential(client_id=client_id)
        self.cache = {}
        self.checks = {}

    def token(self, origin):
        cached = self.cache.get(origin)
        if cached and cached[1] > time.time() + 120:
            return cached[0]
        try:
            access = self.credential.get_token(origin + "/.default")
        except Exception as exc:
            raise DigestError("authentication_failed", f"The managed identity could not get a token for {origin} "
                              f"({type(exc).__name__}). Check MANAGED_IDENTITY_CLIENT_ID.", "identity") from exc
        self.checks[origin] = claim_check(access.token, self.client_id, origin)
        expires = getattr(access, "expires_on", None)
        self.cache[origin] = (access.token, expires if isinstance(expires, (int, float)) else time.time() + 300)
        return access.token

    def close(self):
        try:
            self.credential.close()
        except Exception:
            pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


ARM_POST_PATHS = (re.compile(r"^/providers/microsoft\.resourcegraph/resources$"),)
ARM_GET_PATHS = (
    re.compile(r"^/subscriptions/[0-9a-f-]{36}/providers/microsoft\.insights/eventtypes/management/values$"),
    re.compile(r"^/subscriptions/[0-9a-f-]{36}/providers/microsoft\.authorization/roledefinitions(/[0-9a-f-]{36})?$"),
    re.compile(r"^/subscriptions/[0-9a-f-]{36}$"),
)
GRAPH_GET_PATHS = (re.compile(r"^/v1\.0/serviceprincipals$"), re.compile(r"^/v1\.0/directoryobjects/[0-9a-f-]{36}$"))
RETRYABLE = (429, 500, 502, 503, 504)


class Reader:
    """Read-only HTTPS client: fixed allowlist, no redirects, TLS verification, bounded retries and a time budget."""

    def __init__(self, identity, deadline, graph_enabled=False):
        self.identity = identity
        self.deadline = deadline
        self.graph_enabled = graph_enabled
        self.requests = 0
        self.throttled = 0
        context = ssl.create_default_context()
        if context.verify_mode != ssl.CERT_REQUIRED or not context.check_hostname:
            raise DigestError("unsafe_tls", "TLS certificate and host name verification are mandatory.", "http")
        self.opener = build_opener(NoRedirect(), HTTPSHandler(context=context))

    def origin_for(self, method, url):
        parts = urlsplit(url)
        origin = parts.scheme + "://" + parts.netloc.lower()
        path = unquote(parts.path).lower()
        if (parts.scheme != "https" or parts.username or parts.password or parts.fragment or "\\" in parts.path
                or any(seg in (".", "..") for seg in path.split("/")) or len(url) > 16384):
            raise DigestError("unsafe_endpoint", "Request URL failed the HTTPS path safety rules.", "http")
        if origin == ARM:
            if method == "POST" and any(rx.match(path) for rx in ARM_POST_PATHS):
                return ARM
            if method == "GET" and any(rx.match(path) for rx in ARM_GET_PATHS):
                return ARM
        if origin == GRAPH and self.graph_enabled and method == "GET" and any(rx.match(path) for rx in GRAPH_GET_PATHS):
            return GRAPH
        raise DigestError("unsafe_endpoint", f"{method} {parts.path} is outside the read-only allowlist.", "http")

    def remaining(self):
        return self.deadline - time.monotonic()

    def guard(self):
        if self.remaining() <= 0:
            raise DigestError("collection_deadline", f"Collection budget of {MAX_COLLECTION_SECONDS} s reached; "
                                                     "the remaining reads were skipped.", "collection")
        if self.requests >= MAX_HTTP_REQUESTS:
            raise DigestError("request_cap", "HTTP request cap reached; the remaining reads were skipped.", "collection")
        self.requests += 1

    def request(self, method, url, source, body=None):
        origin = self.origin_for(method, url)
        payload = None if body is None else json.dumps(body).encode("utf-8")
        for attempt in range(3):
            self.guard()
            headers = {"Authorization": "Bearer " + self.identity.token(origin), "Accept": "application/json"}
            if payload is not None:
                headers["Content-Type"] = "application/json"
            req = Request(url, data=payload, method=method, headers=headers)
            try:
                with self.opener.open(req, timeout=max(5.0, min(45.0, self.remaining()))) as response:
                    raw = response.read(HTTP_BYTES + 1)
                    quota = response.headers.get("x-ms-user-quota-remaining")
                    resets = response.headers.get("x-ms-user-quota-resets-after") or ""
            except HTTPError as exc:
                retry = exc.headers.get("Retry-After", "") if exc.headers else ""
                exc.close()
                if exc.code in RETRYABLE and attempt < 2:
                    self.throttled += exc.code == 429
                    wait = min(int(retry), 5) if re.fullmatch(r"\d{1,4}", retry or "") else attempt + 1
                    if self.remaining() > wait + 2:
                        time.sleep(wait)
                        continue
                raise DigestError("access_denied" if exc.code in (401, 403) else "http_error",
                                  f"{method} returned HTTP {exc.code}" + (" (Reader role missing?)" if exc.code == 403 else "") + ".",
                                  source, exc.code) from None
            except (URLError, TimeoutError, ssl.SSLError, OSError) as exc:
                if attempt < 2 and self.remaining() > 5:
                    time.sleep(1)
                    continue
                raise DigestError("transport_failed", f"Network or TLS error during a read-only request ({type(exc).__name__}).", source) from None
            if len(raw) > HTTP_BYTES:
                raise DigestError("response_cap", "Response exceeded the byte safety cap.", source)
            if quota is not None and quota.strip() in ("0", "1"):
                match = re.fullmatch(r"(\d+):(\d+):(\d+(?:\.\d+)?)", resets.strip())
                wait = min(5.0, int(match.group(1)) * 3600 + int(match.group(2)) * 60 + float(match.group(3))) if match else 2.0
                if self.remaining() > wait + 2:
                    self.throttled += 1
                    time.sleep(wait)
            try:
                decoded = json.loads(raw)
            except (ValueError, UnicodeDecodeError):
                raise DigestError("invalid_json", "Source returned malformed JSON.", source) from None
            if not isinstance(decoded, dict):
                raise DigestError("invalid_shape", "Source returned an unexpected JSON shape.", source)
            return decoded
        raise DigestError("http_error", "Bounded HTTP retries exhausted.", source)


def receipt(source_id, label, status="complete", note=""):
    return {"id": source_id, "label": label, "status": status, "pages": 0, "records": 0, "seconds": 0.0, "notes": note, "errors": []}


def fail_receipt(rec, exc, has_rows):
    rec["status"] = "partial" if has_rows else ("skipped" if exc.code in ("collection_deadline", "request_cap")
                                                else "denied" if exc.http_status in (401, 403) else "error")
    rec["errors"].append(exc.public())
    return rec


def scope_chunks(config):
    if config["management_group"]:
        return [{"managementGroups": [config["management_group"]]}]
    subs = config["subscriptions"]
    return [{"subscriptions": subs[i:i + MAX_SUBSCRIPTIONS_PER_QUERY]} for i in range(0, len(subs), MAX_SUBSCRIPTIONS_PER_QUERY)]


def arg_query(reader, config, query, source_id, label, row_cap=MAX_CHANGES, key="id"):
    """POST Azure Resource Graph with $skipToken paging, page/row caps, duplicate-id and loop guards."""
    url = ARM + "/providers/Microsoft.ResourceGraph/resources?api-version=" + ARG_API_VERSION
    rec = receipt(source_id, label)
    rows, seen_ids, seen_tokens = [], set(), set()
    started = time.monotonic()
    try:
        for chunk in scope_chunks(config):
            skip = None
            for _ in range(MAX_PAGES):
                options = {"$top": 1000, "resultFormat": "objectArray"}
                if skip:
                    options["$skipToken"] = skip
                payload = reader.request("POST", url, source_id, body=dict(chunk, query=query, options=options))
                rec["pages"] += 1
                data = payload.get("data")
                if not isinstance(data, list) or any(not isinstance(r, dict) for r in data):
                    raise DigestError("invalid_shape", "Resource Graph returned an unexpected data shape.", source_id)
                if len(rows) + len(data) > row_cap:
                    raise DigestError("row_cap", f"Row cap ({row_cap}) reached; results are partial.", source_id)
                for row in data:
                    row_id = str(row.get(key) or "").lower()
                    if not row_id or row_id in seen_ids:
                        raise DigestError("invalid_pagination", "Resource Graph returned a missing or duplicated row id.", source_id)
                    seen_ids.add(row_id)
                    rows.append(row)
                token = payload.get("$skipToken")
                if not token:
                    break
                if not isinstance(token, str) or len(token) > 16384 or token in seen_tokens:
                    raise DigestError("pagination_loop", "Resource Graph repeated or returned an invalid $skipToken.", source_id)
                seen_tokens.add(token)
                skip = token
            else:
                raise DigestError("page_cap", f"Page cap ({MAX_PAGES} pages) reached; results are partial.", source_id)
    except DigestError as exc:
        fail_receipt(rec, exc, bool(rows))
    rec["records"] = len(rows)
    rec["seconds"] = round(time.monotonic() - started, 2)
    return rows, rec


def arm_get_pages(reader, url, source_id, rec, max_pages=10):
    """GET an ARM list with nextLink paging (same origin and path only). Raises DigestError; caller records it."""
    items, seen, current = [], set(), url
    first = urlsplit(url)
    for _ in range(max_pages):
        if current in seen:
            raise DigestError("pagination_loop", "ARM pagination repeated a page.", source_id)
        seen.add(current)
        payload = reader.request("GET", current, source_id)
        rec["pages"] += 1
        page = payload.get("value", [])
        if not isinstance(page, list):
            raise DigestError("invalid_shape", "ARM list returned an unexpected shape.", source_id)
        items.extend(x for x in page if isinstance(x, dict))
        link = payload.get("nextLink")
        if not link:
            return items
        nxt = urlsplit(link) if isinstance(link, str) else None
        if not nxt or nxt.scheme != "https" or nxt.netloc.lower() != first.netloc.lower() or unquote(nxt.path).lower() != unquote(first.path).lower():
            raise DigestError("invalid_pagination", "ARM continuation changed origin or path.", source_id)
        current = link
    raise DigestError("page_cap", "ARM page cap reached; results are partial.", source_id)


# ------------------------- Resource Graph queries (all read-only) -------------------------
def kql_regex(pattern):
    if re.search(r"['\r\n]", pattern):
        raise DigestError("unsafe_query_value", "Refused to embed an unsafe regex in a Resource Graph query.", "query")
    return "@'" + pattern + "'"


def kql_filters(config, params, rg_col="resourceGroup", type_expr="tolower(tostring(properties.targetResourceType))"):
    parts = []
    if params["resource_group"]:
        parts.append(f"| where {rg_col} contains {kql_text(params['resource_group'])}")
    for pattern in config["rg_pattern_text"]:
        parts.append(f"| where not({rg_col} matches regex {kql_regex('(?i)' + re.sub(r'^[(][?]i[)]', '', pattern))})")
    if config["excluded_types"]:
        parts.append(f"| where {type_expr} !in ({', '.join(kql_text(t) for t in config['excluded_types'])})")
    return "\n".join(parts)


def kql_window(start, end, table="resourcechanges"):
    return (f"{table}\n| extend ts = todatetime(properties.changeAttributes.timestamp)\n"
            f"| where ts > datetime({iso(start)}) and ts <= datetime({iso(end)})")


NOISE_EXPR = (f"((path matches regex {kql_regex(NOISE_PATTERN)} and not(path matches regex {kql_regex(POWER_PATH_PATTERN)}))"
              f" or path matches regex {kql_regex(AGENT_PATTERN)})")
CHANGE_COLUMNS = (
    "| project id, ts, subscriptionId, resourceGroup, targetResourceId = tostring(properties.targetResourceId),\n"
    "  targetResourceType = tolower(tostring(properties.targetResourceType)), changeType = tostring(properties.changeType),\n"
    "  changedBy = tostring(properties.changeAttributes.changedBy), changedByType = tostring(properties.changeAttributes.changedByType),\n"
    "  clientType = tostring(properties.changeAttributes.clientType), operation = tostring(properties.changeAttributes.operation),\n"
    "  correlationId = tostring(properties.changeAttributes.correlationId), changesCount = toint(properties.changeAttributes.changesCount),\n"
    "  changes = properties.changes"
)


def q_candidates(config, params):
    """Every change except noise-only updates (server-side pre-filter, same taxonomy as the Python classifier)."""
    w = params["window"]
    base = kql_window(w["start"], w["end"]) + "\n" + kql_filters(config, params)
    return (base + "\n| extend changeType = tostring(properties.changeType), op = tostring(properties.changeAttributes.operation)\n"
            "| extend keys = bag_keys(properties.changes)\n| extend keyCount = coalesce(array_length(keys), 0)\n"
            "| extend keys = iff(keyCount == 0, dynamic(['(none)']), keys)\n"
            "| mv-expand path = keys to typeof(string) limit 400\n"
            f"| extend isNoise = path != '(none)' and {NOISE_EXPR}\n"
            "| summarize nonNoise = countif(not(isNoise)) by id, changeType, op, keyCount\n"
            f"| where changeType != 'Update' or nonNoise > 0 or keyCount > 400 or op matches regex {kql_regex(POWER_OP_PATTERN)}\n"
            "| project id\n| join kind=inner (" + base + "\n" + CHANGE_COLUMNS + ") on id\n| project-away id1\n| order by ts desc")


def _noise_base(config, params):
    w = params["window"]
    return (kql_window(w["start"], w["end"]) + "\n" + kql_filters(config, params) +
            "\n| where tostring(properties.changeType) == 'Update'"
            f" and not(tostring(properties.changeAttributes.operation) matches regex {kql_regex(POWER_OP_PATTERN)})\n"
            "| extend keys = bag_keys(properties.changes)\n| extend keyCount = coalesce(array_length(keys), 0)\n"
            "| where keyCount between (1 .. 400)\n"
            "| extend rtype = tolower(tostring(properties.targetResourceType)), rgKey = tolower(strcat(subscriptionId, '/', resourceGroup)),"
            " byType = tostring(properties.changeAttributes.changedByType)\n"
            "| mv-expand path = keys to typeof(string) limit 400\n")


def q_noise_types(config, params):
    return (_noise_base(config, params) +
            f"| extend isMeta = (path matches regex {kql_regex(NOISE_PATTERN)} and not(path matches regex {kql_regex(POWER_PATH_PATTERN)})),"
            f" isAgent = path matches regex {kql_regex(AGENT_PATTERN)}\n"
            "| summarize nonNoise = countif(not(isMeta or isAgent)), agentPaths = countif(isAgent and not(isMeta)) by id, rtype, rgKey, byType\n"
            "| where nonNoise == 0\n"
            "| summarize changes = count(), agentChanges = countif(agentPaths > 0) by rtype, rgKey, byType\n"
            "| extend id = strcat(rtype, '|', rgKey, '|', byType)")


def q_noise_paths(config, params):
    return (_noise_base(config, params) +
            f"| extend isNoise = {NOISE_EXPR}, pattern = replace_regex(path, @'\\[\\d+\\]', '[*]')\n"
            "| summarize nonNoise = countif(not(isNoise)), patterns = make_set(pattern, 64) by id\n"
            "| where nonNoise == 0\n| mv-expand pattern = patterns to typeof(string)\n"
            "| summarize occurrences = count() by pattern\n| extend id = pattern\n| order by occurrences desc")


def q_containers():
    return ("resourcecontainers\n| where type =~ 'microsoft.resources/subscriptions/resourcegroups' or type =~ 'microsoft.resources/subscriptions'\n"
            "| project id, type = tolower(type), name, subscriptionId, managedBy = tostring(managedBy), tags")


def q_container_changes(config, params):
    w = params["window"]
    return (kql_window(w["start"], w["end"], "resourcecontainerchanges") + "\n" +
            kql_filters(dict(config, excluded_types=[]), params) + "\n" + CHANGE_COLUMNS + "\n| order by ts desc")


def q_baseline(config, params):
    w = params["window"]
    return (kql_window(w["end"] - timedelta(days=RETENTION_DAYS), w["end"]) + "\n" + kql_filters(config, params) +
            "\n| where tostring(properties.changeAttributes.changedByType) in ('User', 'Application')\n"
            "| summarize firstSeen = min(ts), changes = count() by changedBy = tolower(tostring(properties.changeAttributes.changedBy)),"
            " subscriptionId, rg = tolower(resourceGroup)\n"
            f"| where firstSeen > datetime({iso(w['start'])})\n| extend id = strcat(changedBy, '|', subscriptionId, '|', rg)")


def q_role_assignments(params):
    s, e = iso(params["window"]["start"]), iso(params["window"]["end"])
    return ("authorizationresources\n| where type =~ 'microsoft.authorization/roleassignments'\n"
            "| extend createdOn = todatetime(properties.createdOn), updatedOn = todatetime(properties.updatedOn)\n"
            f"| where (createdOn > datetime({s}) and createdOn <= datetime({e})) or (updatedOn > datetime({s}) and updatedOn <= datetime({e}))\n"
            "| project id, createdOn, updatedOn, subscriptionId, scope = tostring(properties.scope),"
            " principalType = tostring(properties.principalType), principalId = tostring(properties.principalId),"
            " createdBy = tostring(properties.createdBy), updatedBy = tostring(properties.updatedBy),"
            " roleDefinitionId = tostring(properties.roleDefinitionId)")


def q_nsg_rules(ids):
    return (f"resources\n| where type =~ '{NSG_TYPE}' and id in~ {kql_list(ids)}\n| project id, rules = properties.securityRules")


def q_resource_tags(ids):
    return f"resources\n| where id in~ {kql_list(ids)}\n| project id, tags"


def q_identity_maps(app_ids, principal_ids):
    return ("resources\n| where (type =~ 'microsoft.managedidentity/userassignedidentities' and "
            f"(tostring(properties.clientId) in~ {kql_list(app_ids)} or tostring(properties.principalId) in~ {kql_list(principal_ids)}))"
            f" or tostring(identity.principalId) in~ {kql_list(principal_ids)}\n"
            "| project id, name, type = tolower(type), clientId = tostring(properties.clientId),"
            " uamiPrincipalId = tostring(properties.principalId), principalId = tostring(identity.principalId)")


def activity_log_url(subscription, start, end, condition, select):
    query = urlencode({"api-version": ACTIVITY_LOG_API_VERSION,
                       "$filter": f"eventTimestamp ge '{iso(start)}' and eventTimestamp le '{iso(end)}' and {condition}",
                       "$select": select}, quote_via=quote, safe="'")
    return f"{ARM}/subscriptions/{subscription}/providers/Microsoft.Insights/eventtypes/management/values?{query}"


# ------------------------- collection -------------------------
def _run(raw, reader, config, query, source_id, label, **kw):
    rows, rec = arg_query(reader, config, query, source_id, label, **kw)
    raw["sources"].append(rec)
    return rows


def collect_core(reader, config, params):
    raw = {"sources": [], "role_names": {}, "nsg_rules": {}, "resource_tags": {}, "gaps": [], "failed_gaps": [],
           "ra_callers": {}, "baseline": [], "subscription_names": {}}
    raw["containers"] = _run(raw, reader, config, q_containers(), "arg_resourcecontainers",
                             "Subscriptions and resource groups (resourcecontainers)", row_cap=100_000)
    raw["candidates"] = _run(raw, reader, config, q_candidates(config, params), "arg_resourcechanges",
                             "Resource changes, noise pre-filtered server-side (resourcechanges)", row_cap=MAX_CHANGES)
    repair_delete_attribution(reader, config, params, raw)
    raw["container_changes"] = _run(raw, reader, config, q_container_changes(config, params), "arg_resourcecontainerchanges",
                                    "Resource group and subscription changes (resourcecontainerchanges)")
    raw["noise_types"] = _run(raw, reader, config, q_noise_types(config, params), "arg_noise_aggregate",
                              "Noise-only updates by resource type and resource group (aggregate)", row_cap=50_000)
    raw["noise_paths"] = _run(raw, reader, config, q_noise_paths(config, params), "arg_noise_paths",
                              "Noise-only updates by property path (aggregate)", row_cap=50_000)
    if params["period"] == "last_14d":
        raw["sources"].append(receipt("arg_first_seen_baseline", "First-seen actor per resource group (14-day baseline)",
                                      "not_needed", "The 14-day window equals the retention baseline, so the first-time actor flag is not computed."))
    else:
        raw["baseline"] = _run(raw, reader, config, q_baseline(config, params), "arg_first_seen_baseline",
                               "First-seen actor per resource group (14-day baseline)", row_cap=50_000)
    raw["role_assignment_rows"] = _run(raw, reader, config, q_role_assignments(params), "arg_role_assignments",
                                       "New or updated role assignments (authorizationresources)", row_cap=10_000)
    resolve_role_names(reader, config, raw)
    read_nsg_rules(reader, config, raw)
    read_resource_tags(reader, config, raw)
    check_subscriptions(reader, config, raw)
    read_activity_log_gaps(reader, config, params, raw)
    return raw


def repair_delete_attribution(reader, config, params, raw):
    """Change Analysis sometimes records a delete as System/Unspecified; recover the caller from the Activity Log (resourceUri)."""
    rec = receipt("activity_log_delete_attribution", "Activity Log callers for deletes recorded as System or Unspecified")
    raw["sources"].append(rec)
    raw["lookups_used"] = 0
    managed = {f"{str(r.get('subscriptionId') or '').lower()}/{str(r.get('name') or '').lower()}"
               for r in raw["containers"] if r.get("type") == RG_TYPE and r.get("managedBy")}
    targets = [r for r in raw["candidates"] if r.get("changeType") == "Delete" and r.get("changedByType") in ("System", "Unspecified")
               and f"{str(r.get('subscriptionId') or '').lower()}/{str(r.get('resourceGroup') or '').lower()}" not in managed
               and is_guid(str(r.get("subscriptionId") or "")) and not re.search(r"['\r\n]", str(r.get("targetResourceId") or ""))]
    if not ENABLE_ACTIVITY_LOG_GAPS or MAX_ACTIVITY_LOG_LOOKUPS == 0:
        rec.update(status="not_configured", notes="Activity Log reads are disabled.")
        return
    if not targets:
        rec.update(status="not_needed", notes="No delete outside managed resource groups was recorded without an actor.")
        return
    started = time.monotonic()
    for row in targets[:MAX_ACTIVITY_LOG_LOOKUPS]:
        when = parse_time(row.get("ts"))
        if not when:
            continue
        raw["lookups_used"] += 1
        url = activity_log_url(str(row["subscriptionId"]).lower(), when - timedelta(minutes=30), when + timedelta(minutes=10),
                               f"resourceUri eq '{row['targetResourceId']}'", "caller,correlationId,eventTimestamp,operationName,status,category")
        try:
            for event in arm_get_pages(reader, url, rec["id"], rec, max_pages=2):
                op = str((event.get("operationName") or {}).get("value") or "").lower()
                caller = clean(event.get("caller"), 200)
                if (op.endswith("/delete") and (event.get("category") or {}).get("value") == "Administrative" and caller
                        and (event.get("status") or {}).get("value") in ("Started", "Accepted", "Succeeded")):
                    row.update(changedBy=caller, changedByType="User" if "@" in caller else "Application", attributedBy="activity_log")
                    rec["records"] += 1
                    break
        except DigestError as exc:
            fail_receipt(rec, exc, rec["records"] > 0)
            if exc.code in ("collection_deadline", "request_cap"):
                break
    if len(targets) > MAX_ACTIVITY_LOG_LOOKUPS and rec["status"] == "complete":
        rec.update(status="partial", notes=f"Only {MAX_ACTIVITY_LOG_LOOKUPS} of {len(targets)} deletes without an actor were looked up.")
    rec["seconds"] = round(time.monotonic() - started, 2)


def resolve_role_names(reader, config, raw):
    rec = receipt("arm_role_definitions", "Role definition names (ARM roleDefinitions)")
    raw["sources"].append(rec)
    needed, queued = [], set()
    for row in raw["role_assignment_rows"]:
        guid = str(row.get("roleDefinitionId") or "").rsplit("/", 1)[-1].lower()
        if guid in BUILTIN_ROLES:
            raw["role_names"][guid] = BUILTIN_ROLES[guid]
        elif is_guid(guid) and guid not in queued:
            queued.add(guid)
            needed.append((guid, str(row.get("subscriptionId") or (config["subscriptions"] or [""])[0]).lower()))
    if not needed:
        rec.update(status="not_needed", notes="No lookup needed (no new assignments or built-in names resolved locally).")
        return
    started = time.monotonic()
    for guid, sub in needed[:MAX_ROLE_DEFINITION_LOOKUPS]:
        if not is_guid(sub):
            continue
        url = f"{ARM}/subscriptions/{sub}/providers/Microsoft.Authorization/roleDefinitions/{guid}?api-version={ROLE_DEFINITIONS_API_VERSION}"
        try:
            payload = reader.request("GET", url, rec["id"])
            rec["pages"] += 1
            name = clean((payload.get("properties") or {}).get("roleName"), 120)
            if name:
                raw["role_names"][guid] = name
                rec["records"] += 1
        except DigestError as exc:
            fail_receipt(rec, exc, rec["records"] > 0)
            if exc.code in ("collection_deadline", "request_cap"):
                break
    if len(needed) > MAX_ROLE_DEFINITION_LOOKUPS:
        rec.update(status="partial", notes=f"Only the first {MAX_ROLE_DEFINITION_LOOKUPS} custom role names were resolved.")
    rec["seconds"] = round(time.monotonic() - started, 2)


def read_nsg_rules(reader, config, raw):
    ids = []
    for row in raw["candidates"]:
        if row.get("targetResourceType") == NSG_TYPE and any("securityrules" in str(k).lower() for k in (row.get("changes") or {})):
            rid = str(row.get("targetResourceId") or "")
            if rid and rid.lower() not in {i.lower() for i in ids} and "'" not in rid:
                ids.append(rid)
    if not ids:
        raw["sources"].append(receipt("arg_nsg_rules", "Current NSG rules for changed rules (resources)", "not_needed",
                                      "No NSG rule changes in the window."))
        return
    rows = _run(raw, reader, config, q_nsg_rules(ids[:25]), "arg_nsg_rules", "Current NSG rules for changed rules (resources)", row_cap=100)
    for row in rows:
        if isinstance(row.get("rules"), list):
            raw["nsg_rules"][str(row["id"]).lower()] = row["rules"]


def read_resource_tags(reader, config, raw):
    ids = []
    if config["prod_tags"]:
        for row in raw["candidates"]:
            client = str(row.get("clientType") or "").lower()
            if row.get("changedByType") == "User" and ("portal" in client or client.startswith("browser")):
                rid = str(row.get("targetResourceId") or "")
                if rid and "'" not in rid and rid.lower() not in {i.lower() for i in ids}:
                    ids.append(rid)
    if not ids:
        raw["sources"].append(receipt("arg_resource_tags", "Resource tags for manual portal changes (resources)", "not_needed",
                                      "No manual portal changes to check against PROD_TAGS (resource group tags are always used)."))
        return
    rows = _run(raw, reader, config, q_resource_tags(ids[:MAX_LOOKUP_IDS]), "arg_resource_tags",
                "Resource tags for manual portal changes (resources)", row_cap=MAX_LOOKUP_IDS)
    for row in rows:
        if isinstance(row.get("tags"), dict):
            raw["resource_tags"][str(row["id"]).lower()] = row["tags"]


def check_subscriptions(reader, config, raw):
    for row in raw["containers"]:
        if row.get("type") == "microsoft.resources/subscriptions":
            raw["subscription_names"][str(row.get("subscriptionId") or "").lower()] = clean(row.get("name"), 120)
    rec = receipt("subscription_access", "Configured subscriptions visible to the identity")
    raw["sources"].append(rec)
    if config["management_group"]:
        rec.update(records=len(raw["subscription_names"]), notes="Management group scope: " + config["management_group"])
        return
    missing = [s for s in config["subscriptions"] if s not in raw["subscription_names"]]
    rec["records"] = len(config["subscriptions"]) - len(missing)
    for sub in missing[:10]:
        try:
            payload = reader.request("GET", f"{ARM}/subscriptions/{sub}?api-version={SUBSCRIPTION_API_VERSION}", rec["id"])
            raw["subscription_names"][sub] = clean(payload.get("displayName"), 120) or sub
            rec["notes"] = "Readable through ARM but not returned by Resource Graph yet."
        except DigestError as exc:
            fail_receipt(rec, exc, rec["records"] > 0)
            rec["notes"] = "A configured subscription is not visible: assign Reader to the agent identity."
    if missing and rec["status"] == "complete" and len(missing) > 10:
        rec["status"] = "partial"


def _status_code(props):
    text_value = props.get("statusMessage") if isinstance(props, dict) else None
    match = re.search(r'"code"\s*:\s*"([A-Za-z]{2,60})"', text_value[:4000]) if isinstance(text_value, str) else None
    return match.group(1) if match else ""


def _assignment_body(props):
    for key in ("responseBody", "requestbody", "requestBody"):
        value = props.get(key) if isinstance(props, dict) else None
        if isinstance(value, str) and len(value) <= 20000:
            try:
                body = json.loads(value)
            except ValueError:
                continue
            inner = (body.get("properties") or body.get("Properties")) if isinstance(body, dict) else None
            if isinstance(inner, dict):
                return {"role_id": str(inner.get("roleDefinitionId") or inner.get("RoleDefinitionId") or "").rsplit("/", 1)[-1].lower(),
                        "principal_id": clean(inner.get("principalId") or inner.get("PrincipalId"), 40),
                        "principal_type": clean(inner.get("principalType") or inner.get("PrincipalType"), 40)}
    return {}


def read_activity_log_gaps(reader, config, params, raw):
    rec = receipt("activity_log_gaps", "Activity Log gap events: role assignment deletes, locks, diagnostic settings, policy")
    raw["sources"].append(rec)
    if not ENABLE_ACTIVITY_LOG_GAPS:
        rec.update(status="not_configured", notes="ENABLE_ACTIVITY_LOG_GAPS is False.")
        return
    subs = config["subscriptions"] or sorted(raw["subscription_names"])
    if not subs:
        rec.update(status="partial", notes="No subscription list available for Activity Log reads.")
        return
    w, started, seen = params["window"], time.monotonic(), set()
    select = "caller,correlationId,eventTimestamp,operationName,resourceGroupName,resourceId,status,category,properties"
    try:
        for sub in subs[:MAX_ACTIVITY_LOG_SUBSCRIPTIONS]:
            for provider in ("Microsoft.Authorization", "Microsoft.Insights"):
                url = activity_log_url(sub, w["start"], w["end"], f"resourceProvider eq '{provider}'", select)
                for event in arm_get_pages(reader, url, rec["id"], rec, max_pages=10):
                    _gap_event(config, params, raw, event, sub, seen)
    except DigestError as exc:
        fail_receipt(rec, exc, bool(raw["gaps"]))
    if len(subs) > MAX_ACTIVITY_LOG_SUBSCRIPTIONS and rec["status"] == "complete":
        rec.update(status="partial", notes=f"Activity Log read for the first {MAX_ACTIVITY_LOG_SUBSCRIPTIONS} of {len(subs)} subscriptions.")
    rec["records"] = len(raw["gaps"]) + len(raw["failed_gaps"])
    rec["seconds"] = round(time.monotonic() - started, 2)


def _gap_event(config, params, raw, event, sub, seen):
    op = clean((event.get("operationName") or {}).get("value"), 200).lower()
    status = clean((event.get("status") or {}).get("value"), 40)
    category = clean((event.get("category") or {}).get("value"), 40)
    if category != "Administrative" or op not in GAP_OPERATIONS and op != "microsoft.authorization/roleassignments/write":
        return
    resource_id = clean(event.get("resourceId"), 600)
    rg = clean(event.get("resourceGroupName"), 90)
    caller = clean(event.get("caller"), 200)
    props = event.get("properties") if isinstance(event.get("properties"), dict) else {}
    if op == "microsoft.authorization/roleassignments/write":
        if status == "Succeeded" and caller:
            raw["ra_callers"][resource_id.lower()] = caller
        return
    if rg_excluded(config, rg) or not rg_focus(params, rg):
        return
    if status not in ("Succeeded", "Failed"):
        return
    key = (op, resource_id.lower(), clean(event.get("correlationId"), 80), status)
    if key in seen:
        return
    seen.add(key)
    level, label = GAP_OPERATIONS[op]
    when = parse_time(event.get("eventTimestamp"))
    cut = resource_id.lower().rfind("/providers/")
    target = resource_name_of(resource_id[:cut]) if cut > 0 else (rg or sub)
    item = {"time_utc": iso(when), "operation": clean((event.get("operationName") or {}).get("value"), 200), "label": label,
            "level": level, "status": status, "resource_id": resource_id, "resource_name": resource_name_of(resource_id),
            "target": target, "resource_group": rg, "subscription_id": sub, "caller": caller,
            "correlation_id": clean(event.get("correlationId"), 80)}
    if op.startswith("microsoft.authorization/roleassignments"):
        item.update(_assignment_body(props))
    if status == "Failed":
        item.update(level="low", label=label.split(" (")[0] + " attempt failed", error_code=_status_code(props))
        raw["failed_gaps"].append(item)
    else:
        raw["gaps"].append(item)


# ------------------------- classification (deterministic and explainable) -------------------------
def normalize_change(row, source):
    bag = row.get("changes") if isinstance(row.get("changes"), dict) else {}
    changes = {}
    for path, value in bag.items():
        if isinstance(value, dict):
            changes[clean(path, 400)] = (clean(value.get("previousValue"), 2000), clean(value.get("newValue"), 2000))
    sub = clean(row.get("subscriptionId"), 40).lower()
    rg = clean(row.get("resourceGroup"), 90)
    resource_id = clean(row.get("targetResourceId"), 1000)
    rtype = norm_type(row.get("targetResourceType"))
    if source == "resourcecontainerchanges" and not rtype:
        rtype = RG_TYPE if "/resourcegroups/" in resource_id.lower() else "microsoft.resources/subscriptions"
    if source == "resourcecontainerchanges" and rtype == RG_TYPE and not rg:
        rg = resource_name_of(resource_id)
    return {
        "id": clean(row.get("id"), 1200), "change_id": short_change_id(clean(row.get("id"), 1200)), "source": source,
        "when": parse_time(row.get("ts")), "subscription_id": sub, "resource_group": rg, "rg_key": f"{sub}/{rg.lower()}",
        "resource_id": resource_id, "resource_name": resource_name_of(resource_id), "resource_type": rtype,
        "change_type": clean(row.get("changeType"), 20) or "Update", "changed_by": clean(row.get("changedBy"), 200),
        "changed_by_type": clean(row.get("changedByType"), 40), "client_type": clean(row.get("clientType"), 120),
        "operation": clean(row.get("operation"), 300), "correlation_id": clean(row.get("correlationId"), 80),
        "changes": changes, "attributed_by": clean(row.get("attributedBy"), 40),
    }


def is_arc_agent_report(change):
    return (change["resource_type"].startswith("microsoft.hybridcompute/machines") and change["changed_by_type"] == "User"
            and change["client_type"].lower() in ("", "unspecified") and change["operation"].lower() in ("", "unspecified"))


def actor_class(change, expected, managed_rg=False):
    kind, by, client = change["changed_by_type"], change["changed_by"].lower(), change["client_type"].lower()
    if by and by in expected:
        return "expected-automation"
    if kind == "System":
        return "platform"
    if kind == "User":
        return "platform" if is_arc_agent_report(change) else "human"
    if managed_rg:
        return "platform"
    if kind == "Application":
        if client in FIRST_PARTY_CLIENTS or (GUID_RX.match(client) and client == by):
            return "platform"
        return "automation"
    return "unknown"


def client_class(client_type, changed_by):
    c = (client_type or "").strip().lower()
    if not c or c in ("unspecified", "unknown"):
        return "unspecified"
    if "portal" in c or c.startswith("browser"):
        return "click-ops"
    if c in ("arm template", "azure resource manager template") or any(k in c for k in ("template", "terraform", "bicep", "deployment", "devops", "github")):
        return "iac"
    if c in ("cli", "azure cli") or "powershell" in c or c.endswith(" cli"):
        return "script"
    if c in FIRST_PARTY_CLIENTS:
        return "service"
    if c.endswith(" sdk") or "logic apps" in c or "functions" in c or "automation" in c:
        return "sdk"
    if GUID_RX.match(c):
        return "service" if c == (changed_by or "").strip().lower() else "unknown-app"
    return "unspecified"


def path_class(path, shape, rtype, actor, has_power):
    lp = path.lower()
    if NOISE_RX.search(path) and not POWER_PATH_RX.search(path):
        return "noise", "platform metadata/timestamp"
    if AGENT_RX.search(path):
        return "noise", "agent-reported inventory"
    if has_power and shape != "modified" and rtype == VM_TYPE:
        return "noise", "VM enrichment on start/deallocate"
    if EXT_UPGRADE_RX.search(path):
        return "low", "extension auto-upgrade"
    if NIC_ATTACH_RX.search(path) and rtype == NIC_TYPE:
        return "low", "NIC attach/detach churn"
    if POWER_PATH_RX.search(path):
        return ("medium" if actor == "human" else "low"), "power state change"
    if actor == "platform" and AUTOSCALE_RX.search(path):
        return "low", "platform autoscale (capacity)"
    if SECURITY_RX.search(path):
        return "high", "security / exposure setting"
    if rtype in MONITOR_TYPES and MONITOR_RX.search(path):
        return "medium", "alerting logic changed"
    if SIZE_RX.search(path) and shape == "modified":
        return "medium", "SKU / size / tier changed"
    if lp.startswith("tags."):
        return "low", "tag change"
    return ("medium" if actor in ("human", "automation", "expected-automation") else "low"), "configuration change"


def _shape(prev, new):
    return "inserted" if not prev and new else "removed" if prev and not new else "modified"


def _tls_rank(value):
    match = re.search(r"(\d)[._](\d)", value or "")
    return int(match.group(1)) * 10 + int(match.group(2)) if match else 0


def security_detail(path, prev, new):
    """Readable description of a known security setting change, and whether exposure increased."""
    lp, pv, nv = path.lower(), (prev or "").lower(), (new or "").lower()
    show = lambda v: v if v else "(not set)"
    if lp.endswith("publicnetworkaccess"):
        return f"Public network access {show(prev)} -> {show(new)}", nv == "enabled" and pv != "enabled"
    if lp.endswith("defaultaction"):
        return f"Network ACL default action {show(prev)} -> {show(new)}", nv == "allow" and pv != "allow"
    if "iprules" in lp or "virtualnetworkrules" in lp:
        return (f"Firewall allow rule added: {new}" if new and not prev else f"Firewall allow rule removed: {prev}" if prev and not new
                else f"Firewall allow rule {prev} -> {new}"), False
    if lp.endswith("allowsharedkeyaccess"):
        return f"Shared key access {show(prev)} -> {show(new)}", nv == "true" and pv != "true"
    if lp.endswith("allowblobpublicaccess"):
        return f"Anonymous blob access {show(prev)} -> {show(new)}", nv == "true" and pv != "true"
    if lp.endswith("disablelocalauth"):
        return f"Local authentication disabled {show(prev)} -> {show(new)}", nv == "false" and pv == "true"
    if "tlsversion" in lp:
        return f"Minimum TLS version {show(prev)} -> {show(new)}", bool(prev) and _tls_rank(new) < _tls_rank(prev)
    if lp.endswith(("enablepurgeprotection", "enablesoftdelete")):
        return f"{path.rsplit('.', 1)[-1]} {show(prev)} -> {show(new)}", nv == "false"
    if lp.endswith("enablerbacauthorization"):
        return f"RBAC authorization {show(prev)} -> {show(new)}", False
    if "publicipaddress" in lp:
        return ("Public IP address attached" if new and not prev else "Public IP address detached" if prev and not new
                else "Public IP address changed"), bool(new and not prev)
    return None


def size_detail(path, prev, new, sized=()):
    """Readable description of a SKU, size, tier or capacity change."""
    lp = path.lower()
    if lp == "sku.name":
        return f"SKU {prev} -> {new}"
    if lp == "sku.tier" and "sku.name" not in sized:
        return f"Tier {prev} -> {new}"
    if lp.endswith("vmsize"):
        return f"VM size {prev} -> {new}"
    if lp.endswith("disksizegb"):
        return f"Disk size {prev} GB -> {new} GB"
    if lp == "sku.capacity" or lp.endswith(".count"):
        return f"Capacity {prev} -> {new}"
    if lp == "properties.tier":
        return f"Performance tier {prev} -> {new}"
    return None


def _port_hits(values):
    hits = []
    for value in values:
        for token in re.split(r"[,\s]+", (value or "").strip()):
            if token in ("*", "0-65535", "any"):
                return ["any port"]
            match = re.fullmatch(r"(\d{1,5})(?:-(\d{1,5}))?", token)
            if match:
                low, high = int(match.group(1)), int(match.group(2) or match.group(1))
                hits += [f"{port} ({name})" for port, name in SENSITIVE_PORTS.items() if low <= port <= high and f"{port} ({name})" not in hits]
    return hits


def nsg_history(candidates):
    """Per NSG, chronological rule fields seen in the window: {resource_id: [(when, {index: {field: new_value}})]}."""
    history = defaultdict(list)
    for row in candidates:
        if norm_type(row.get("targetResourceType")) != NSG_TYPE or not isinstance(row.get("changes"), dict):
            continue
        rules = defaultdict(dict)
        for path, value in row["changes"].items():
            match = RULE_RX.match(str(path))
            if match and isinstance(value, dict):
                rules[int(match.group(1))][match.group(2).lower()] = clean(value.get("newValue"), 400)
        when = parse_time(row.get("ts"))
        if rules and when:
            history[str(row.get("targetResourceId") or "").lower()].append((when, dict(rules)))
    for entries in history.values():
        entries.sort(key=lambda e: e[0])
    return history


def nsg_rule_findings(change, current_rules, history=()):
    """Evaluate changed NSG security rules for Internet exposure.

    Field values come from this change first, then from earlier changes of the same NSG in the window (array indexes
    refer to that time), then from the current rule state (by name, or by index as a last resort).
    """
    earlier = {}
    for _, rules in history:
        for index, fields in rules.items():
            if fields and all(v == "" for v in fields.values()):
                earlier.pop(index, None)
            else:
                earlier.setdefault(index, {}).update({k: v for k, v in fields.items() if v})
    groups = defaultdict(lambda: defaultdict(list))
    for path, (prev, new) in change["changes"].items():
        match = RULE_RX.match(path)
        if match:
            groups[int(match.group(1))][match.group(2).lower()].append((prev, new))
    rules = [r for r in (current_rules or []) if isinstance(r, dict)]
    by_name = {str(r.get("name") or "").lower(): r for r in rules}
    findings = []
    for index, fields in sorted(groups.items()):
        base = earlier.get(index, {})
        names = fields.get("name") or []
        name = next((n or p for p, n in names if n or p), "") or base.get("name", "")
        current = by_name.get(name.lower()) if name else (rules[index] if index < len(rules) else None)
        name = name or str((current or {}).get("name") or f"rule #{index}")
        props = (current or {}).get("properties") if isinstance((current or {}).get("properties"), dict) else {}
        values = [(p, n) for vals in fields.values() for p, n in vals]
        removed = all(not n for _, n in values) and any(p for p, _ in values)

        def value(field, plural=None):
            if field in fields:
                return [(p if removed else n) for p, n in fields[field] if (p if removed else n)] or ([] if removed else [""])
            if base.get(field):
                return [base[field]]
            got = props.get(plural or field) if plural else props.get(next((k for k in props if k.lower() == field), ""))
            if plural:
                return [str(x) for x in got] if isinstance(got, list) else []
            return [str(got)] if got not in (None, "") else []

        def first(field):
            got = value(field)
            return got[0] if got else ""

        access, direction = first("access").lower(), first("direction").lower()
        sources = [s for s in value("sourceaddressprefix") + value("sourceaddressprefixes", "sourceAddressPrefixes") if s]
        ports = [p for p in value("destinationportrange") + value("destinationportranges", "destinationPortRanges") if p]
        shape = "removed" if removed else ("inserted" if all(not p for p, _ in values) else "modified")
        internet = [s for s in sources if s.strip().lower() in INTERNET_SOURCES]
        hits = _port_hits(ports)
        exposed = access == "allow" and direction == "inbound" and internet and hits
        src = ("Internet" if any(s.lower() == "internet" for s in internet) else "any source (*)" if internet and internet[0] == "*"
               else internet[0] if internet else "")
        if exposed and not removed:
            findings.append((f"Inbound Allow from {src} to {', '.join(hits[:4])} on rule {name}", True))
        elif removed:
            findings.append((f"Security rule {name} removed" + (f" (was Inbound Allow from {src} to {', '.join(hits[:4])})" if exposed else ""), False))
        else:
            summary = " ".join(x for x in (first("direction"), first("access"), ",".join(sources[:2]), "->", ",".join(ports[:3])) if x)
            findings.append((f"Security rule {name} {'added' if shape == 'inserted' else 'changed'}" + (f": {summary}" if sources or ports else ""), False))
    return findings


def classify_change(change, ctx):
    """Set level, reasons, flags, actor and client classes and per-path classes on a normalized change."""
    rtype, kind = change["resource_type"], change["change_type"]
    managed = change["rg_key"] in ctx["managed"] or (rtype == RG_TYPE and change["rg_key"] in ctx["managed"])
    actor = actor_class(change, ctx["expected"], managed)
    client = client_class(change["client_type"], change["changed_by"])
    power_op = bool(POWER_OP_RX.search(change["operation"]))
    has_power = power_op or any(POWER_PATH_RX.search(p) for p in change["changes"])
    paths = []
    for path, (prev, new) in sorted(change["changes"].items()):
        shape = _shape(prev, new)
        level, reason = path_class(path, shape, rtype, actor, has_power)
        paths.append({"path": path, "shape": shape, "level": level, "reason": reason, "previous": prev, "new": new})
    reasons, flags, security = [], [], False
    if kind == "Delete":
        if actor == "human":
            level, reasons = "high", ["deleted by a human"]
        elif rtype in CRITICAL_TYPES and actor != "platform" and not managed:
            level, reasons = "high", ["security, data or monitoring resource deleted"]
        elif actor == "platform":
            level, reasons = "low", ["platform-managed delete"]
        else:
            level, reasons = "medium", ["deleted by automation" if actor != "unknown" else "deleted (no actor recorded)"]
        security = rtype in SECURITY_TYPES
    elif kind == "Create":
        if actor == "platform":
            level, reasons = "low", ["platform-managed create"]
        elif rtype == PIP_TYPE:
            level, reasons, security = "high", ["new public IP address (Internet exposure)"], True
            flags.append("exposure increased")
        elif rtype in SECURITY_TYPES or rtype in DATA_TYPES:
            level, reasons, security = "medium", ["new security or data resource"], rtype in SECURITY_TYPES
        elif actor == "human":
            level, reasons = "medium", ["created by a human"]
        else:
            level, reasons = "low", ["created by automation" if actor != "unknown" else "created (no actor recorded)"]
    else:
        kept = [p for p in paths if p["level"] != "noise"]
        if power_op and not any(p["reason"] == "power state change" for p in kept):
            kept.append({"level": "medium" if actor == "human" else "low", "reason": "power operation"})
        if not kept:
            noise_reasons = Counter(p["reason"] for p in paths)
            level, reasons = "noise", [noise_reasons.most_common(1)[0][0] if noise_reasons else "no property changes"]
        else:
            level = max((p["level"] for p in kept), key=RANK.get)
            reasons = list(dict.fromkeys(p["reason"] for p in kept if p["level"] == level))
            if rtype in SECURITY_TYPES and actor != "platform" and RANK[level] < 3 and any(p["reason"] != "tag change" for p in kept):
                level = "high"
                reasons.append("change on a security resource type")
            sized = {p["path"].lower() for p in kept if p.get("reason") == "SKU / size / tier changed"}
            details = [d for p in kept if p.get("reason") == "SKU / size / tier changed"
                       for d in [size_detail(p["path"], p["previous"], p["new"], sized)] if d]
            if details:
                reasons = details + [r for r in reasons if r != "SKU / size / tier changed"]
            reasons.sort(key=lambda r: r == "configuration change")
        secure_paths = [p for p in paths if p["reason"] == "security / exposure setting"]
        security = bool(secure_paths) or (rtype in SECURITY_TYPES and level == "high")
        details = []
        if rtype == NSG_TYPE and any(RULE_RX.match(p["path"]) for p in secure_paths):
            rid = change["resource_id"].lower()
            history = [h for h in ctx.get("nsg_history", {}).get(rid, []) if change["when"] and h[0] < change["when"]]
            for text_value, exposed in nsg_rule_findings(change, ctx["nsg_rules"].get(rid), history):
                details.append(text_value)
                if exposed and "internet-exposed" not in flags:
                    flags.append("internet-exposed")
        for p in secure_paths:
            if RULE_RX.match(p["path"]):
                continue
            found = security_detail(p["path"], p["previous"], p["new"])
            if found:
                details.append(found[0])
                if found[1] and "exposure increased" not in flags:
                    flags.append("exposure increased")
        if details:
            reasons = list(dict.fromkeys(details)) + [r for r in reasons if r != "security / exposure setting"]
    if managed and level in ("high", "medium") and not (kind == "Delete" and actor == "human"):
        level = "low"
        reasons.append("inside a platform-managed resource group")
    if change.get("attributed_by"):
        reasons.append("actor recovered from the Activity Log (Change Analysis recorded no actor)")
    if actor == "expected-automation" and level != "noise":
        if not (kind == "Delete" and rtype in CRITICAL_TYPES):
            level = LOWER[level]
        reasons.append("expected automation: " + ctx["expected"].get(change["changed_by"].lower(), "configured"))
    prod = (change["rg_key"] in ctx["prod_rgs"] or change["subscription_id"] in ctx["prod_subs"]
            or ctx["is_prod"](ctx["resource_tags"].get(change["resource_id"].lower())))
    if actor == "human" and client == "click-ops" and level != "noise":
        flags.append("click-ops")
        if prod:
            flags.append("click-ops in production")
            if RANK[level] < RANK["medium"]:
                level = "medium"
                reasons.append("manual portal change in production")
    change.update(level=level, reasons=reasons, flags=flags, actor_class=actor, client_class=client, managed_rg=managed,
                  prod=prod, security=security and level != "noise", paths=paths)
    return change


def actor_display(change, ctx):
    actor, by = change["actor_class"], change["changed_by"]
    if change.get("attributed_by"):
        return by, "activity_log"
    if actor == "human":
        return by, "upn"
    if actor == "expected-automation":
        return ctx["expected"].get(by.lower(), by), "configured"
    if change["changed_by_type"] == "System":
        return "Azure platform (System)", "raw"
    if is_arc_agent_report(change):
        return f"Azure Arc agent (reported as {by})", "heuristic"
    if change["changed_by_type"] == "Unspecified" or not by:
        return "Not recorded (Unspecified)", "raw"
    if change["client_class"] == "service":
        client = change["client_type"]
        return (client if not GUID_RX.match(client) else f"Azure service (app {by[:8]})"), "heuristic"
    return by, "raw"


# ------------------------- analysis -------------------------
def build_context(raw, config):
    prod_tags = config["prod_tags"]

    def is_prod(tags):
        if not isinstance(tags, dict) or not prod_tags:
            return False
        return any(str(v).strip().lower() in prod_tags.get(str(k).strip().lower(), ()) for k, v in tags.items())

    managed, prod_rgs, prod_subs, managed_by = set(), set(), set(), {}
    for row in raw["containers"]:
        sub = str(row.get("subscriptionId") or "").lower()
        if row.get("type") == RG_TYPE:
            key = f"{sub}/{str(row.get('name') or '').lower()}"
            if row.get("managedBy"):
                managed.add(key)
                managed_by[key] = clean(row.get("managedBy"), 400)
            if is_prod(row.get("tags")):
                prod_rgs.add(key)
        elif row.get("type") == "microsoft.resources/subscriptions" and is_prod(row.get("tags")):
            prod_subs.add(sub)
    zone, zone_source = business_zone()
    return {"managed": managed, "managed_by": managed_by, "prod_rgs": prod_rgs, "prod_subs": prod_subs, "is_prod": is_prod,
            "resource_tags": raw["resource_tags"], "expected": config["expected"], "nsg_rules": raw["nsg_rules"],
            "nsg_history": nsg_history(raw["candidates"]), "zone": zone, "zone_source": zone_source}


def detect_bursts(changes, window=timedelta(minutes=15), min_changes=10, min_deletes=5):
    """Sliding 15-minute window per actor: >= 10 changes or >= 5 deletes. Marks members with the 'burst' flag."""
    by_actor = defaultdict(list)
    for c in changes:
        if c["actor_class"] in ("human", "automation", "expected-automation") and c["changed_by"]:
            by_actor[c["changed_by"].lower()].append(c)
    episodes = []
    for actor, items in by_actor.items():
        items.sort(key=lambda c: c["when"])
        left, current = 0, None
        for right in range(len(items)):
            while items[right]["when"] - items[left]["when"] > window:
                left += 1
            win = items[left:right + 1]
            if len(win) >= min_changes or sum(1 for x in win if x["change_type"] == "Delete") >= min_deletes:
                if current and items[left]["when"] <= current["end"]:
                    current["end"] = items[right]["when"]
                else:
                    current = {"actor": items[right]["changed_by"], "start": items[left]["when"], "end": items[right]["when"], "members": {}}
                    episodes.append(current)
                current["members"].update((x["change_id"], x) for x in win)
    result = []
    for ep in episodes:
        members = list(ep["members"].values())
        for m in members:
            if "burst" not in m["flags"]:
                m["flags"].append("burst")
        result.append({"actor": ep["actor"], "start_utc": iso(ep["start"]), "end_utc": iso(ep["end"]), "changes": len(members),
                       "deletes": sum(1 for m in members if m["change_type"] == "Delete"),
                       "resource_types": sorted({m["resource_type"] for m in members})[:6]})
    return result


def prefer_arg_casing(changes):
    """Delete records (and rows whose actor came from the Activity Log) often carry an upper-cased resource ID.

    Reuse the casing of another Resource Graph record of the same resource in the window (create/update);
    otherwise keep the original.
    """
    seen = {}
    for c in changes:
        if c["change_type"] != "Delete" and not c.get("attributed_by") and c["resource_id"]:
            seen.setdefault(c["resource_id"].lower(), c["resource_id"])
    for c in changes:
        if c["change_type"] == "Delete" or c.get("attributed_by"):
            better = seen.get(c["resource_id"].lower())
            if better and better != c["resource_id"]:
                c["resource_id"], c["resource_name"] = better, resource_name_of(better)


def mark_duplicate_records(changes):
    """An Update whose property diff is identical to the previous Update of the same resource is a repeated record, not a new change."""
    last = {}
    for c in sorted(changes, key=lambda c: c["when"]):
        key = c["resource_id"].lower()
        if c["change_type"] != "Update":
            last.pop(key, None)
            continue
        signature = frozenset(c["changes"].items())
        previous = last.get(key)
        if signature and previous and previous[0] == signature and c["level"] != "noise":
            c.update(level="noise", reasons=["duplicate change record"], flags=[], security=False, duplicate_of=previous[1])
        last[key] = (signature, iso(c["when"]))


def scope_label(scope, sub_names):
    s = (scope or "").rstrip("/")
    match = re.match(r"(?i)^/subscriptions/([^/]+)(?:/resourcegroups/([^/]+))?(/providers/.+)?$", s)
    if match:
        if match.group(3):
            return "Resource " + resource_name_of(s), match.group(2) or ""
        if match.group(2):
            return "Resource group " + match.group(2), match.group(2)
        return "Subscription " + sub_names.get(match.group(1).lower(), match.group(1)), ""
    if "/managementgroups/" in s.lower():
        return "Management group " + resource_name_of(s), ""
    return s or "/", ""


def analyze(raw, config, params):
    ctx = build_context(raw, config)
    w, zone = params["window"], ctx["zone"]
    changes, excluded = [], 0
    for source, rows in (("resourcechanges", raw["candidates"]), ("resourcecontainerchanges", raw["container_changes"])):
        for row in rows:
            c = normalize_change(row, source)
            if c["when"] is None:
                continue
            if rg_excluded(config, c["resource_group"]) or (source == "resourcechanges" and c["resource_type"] in config["excluded_types"]):
                excluded += 1
                continue
            if not rg_focus(params, c["resource_group"]):
                continue
            classify_change(c, ctx)
            c["actor_display"], c["actor_resolution"] = actor_display(c, ctx)
            c["timestamp_local"] = local_label(c["when"], zone)
            changes.append(c)
    changes.sort(key=lambda c: c["when"], reverse=True)
    prefer_arg_casing(changes)
    mark_duplicate_records(changes)
    relevant = [c for c in changes if c["level"] != "noise"]
    for c in relevant:
        if c["actor_class"] == "human" and is_after_hours(c["when"], zone, config["hours"], config["days"]):
            c["flags"].append("after-hours")
    baseline = {}
    for r in raw["baseline"]:
        first = parse_time(r.get("firstSeen"))
        if first:
            baseline[(str(r.get("changedBy") or "").lower(), str(r.get("subscriptionId") or "").lower(), str(r.get("rg") or "").lower())] = first
    first_time = {}
    for c in sorted(relevant, key=lambda c: c["when"]):
        key = (c["changed_by"].lower(), c["subscription_id"], c["resource_group"].lower())
        if c["changed_by_type"] in ("User", "Application") and c["actor_class"] != "platform" and key in baseline:
            entry = first_time.get(key)
            if entry is None:
                c["flags"].append("first-time actor on RG")
                entry = first_time[key] = {"actor": c["changed_by"], "actor_class": c["actor_class"], "resource_group": c["resource_group"],
                                           "subscription_id": c["subscription_id"], "first_utc": iso(baseline[key]), "changes": 0}
            entry["changes"] += 1
    bursts = detect_bursts(relevant)
    chains = {}
    for c in relevant:
        if c["change_type"] != "Delete":
            continue
        key = ((c["correlation_id"] if is_guid(c["correlation_id"]) else c["change_id"]).lower(), c["changed_by"].lower())
        ch = chains.setdefault(key, {"correlation_id": c["correlation_id"], "actor": c["changed_by"], "actor_display": c["actor_display"],
                                     "actor_class": c["actor_class"], "client_type": c["client_type"], "client_class": c["client_class"],
                                     "deleted": 0, "resource_types": [], "resources": [], "resource_groups": [], "first": c["when"],
                                     "last": c["when"], "level": "low", "managed": True, "reasons": [], "flags": [], "change_ids": []})
        ch["deleted"] += 1
        ch["change_ids"].append(c["change_id"])
        for field, value in (("resource_types", c["resource_type"]), ("resources", c["resource_name"]), ("resource_groups", c["resource_group"])):
            if value and value not in ch[field]:
                ch[field].append(value)
        ch["first"], ch["last"] = min(ch["first"], c["when"]), max(ch["last"], c["when"])
        ch["managed"] = ch["managed"] and c["managed_rg"]
        if RANK[c["level"]] > RANK[ch["level"]]:
            ch["level"] = c["level"]
        ch["reasons"] = list(dict.fromkeys(ch["reasons"] + c["reasons"]))
        ch["flags"] = list(dict.fromkeys(ch["flags"] + c["flags"]))
    delete_chains = sorted(chains.values(), key=lambda x: (-RANK[x["level"]], -x["last"].timestamp()))
    role_assignments = []
    for r in raw["role_assignment_rows"]:
        created, updated = parse_time(r.get("createdOn")), parse_time(r.get("updatedOn"))
        in_window = lambda t: t is not None and w["start"] < t <= w["end"]
        label, rg = scope_label(str(r.get("scope") or ""), raw["subscription_names"])
        if rg_excluded(config, rg) or not rg_focus(params, rg):
            continue
        guid = str(r.get("roleDefinitionId") or "").rsplit("/", 1)[-1].lower()
        role = raw["role_names"].get(guid) or ("Role " + guid[:8])
        rid = str(r.get("id") or "").lower()
        caller = raw["ra_callers"].get(rid)
        privileged = role.lower() in PRIVILEGED_ROLES
        when = created if in_window(created) else updated
        role_assignments.append({
            "kind": "created" if in_window(created) else "updated", "created_utc": iso(when), "time_local": local_label(when, zone) if when else "",
            "scope": clean(r.get("scope"), 600), "scope_label": label, "resource_group": rg, "role_name": role, "role_id": guid,
            "principal_type": clean(r.get("principalType"), 40), "principal_id": clean(r.get("principalId"), 40), "principal_display": "",
            "created_by": caller or clean(r.get("createdBy") if in_window(created) else r.get("updatedBy"), 120),
            "created_by_resolution": "activity_log" if caller else "object_id", "privileged": privileged,
            "level": "high" if privileged else "medium", "id": clean(r.get("id"), 600)})
    role_assignments.sort(key=lambda x: x["created_utc"], reverse=True)
    gaps = sorted(raw["gaps"], key=lambda g: g["time_utc"], reverse=True)
    for g in gaps + raw["failed_gaps"]:
        when = parse_time(g["time_utc"])
        g["time_local"] = local_label(when, zone) if when else ""
        if g.get("role_id"):
            g["role_name"] = raw["role_names"].get(g["role_id"]) or BUILTIN_ROLES.get(g["role_id"]) or ("Role " + g["role_id"][:8])
    return {"ctx": ctx, "changes": changes, "relevant": relevant, "excluded": excluded, "first_time": list(first_time.values()),
            "bursts": bursts, "delete_chains": delete_chains, "role_assignments": role_assignments, "gaps": gaps,
            "failed_gaps": sorted(raw["failed_gaps"], key=lambda g: g["time_utc"], reverse=True)}


# ------------------------- identity name enrichment (bounded, optional) -------------------------
MICROSOFT_TENANTS = {"f8cdef31-a31e-4b4a-93e4-5f571e91255a", "72f988bf-86f1-41af-91ab-2d7cd011db47"}


def resolve_names(reader, config, params, analysis, raw):
    relevant = analysis["relevant"]
    unresolved = {}
    for c in sorted(relevant, key=lambda c: -RANK[c["level"]]):
        if c["changed_by_type"] == "Application" and is_guid(c["changed_by"]) and c["actor_resolution"] == "raw":
            unresolved.setdefault(c["changed_by"].lower(), c)
    principals = {r["principal_id"].lower() for r in analysis["role_assignments"] if is_guid(r["principal_id"])}
    principals |= {r["created_by"].lower() for r in analysis["role_assignments"] if is_guid(r["created_by"])}
    principals |= {g["principal_id"].lower() for g in analysis["gaps"] if is_guid(g.get("principal_id", ""))}
    app_oid, app_name, app_how = {}, {}, {}
    rec = receipt("activity_log_actor_lookup", "Activity Log lookups by correlationId for unresolved application actors")
    raw["sources"].append(rec)
    lookups = [(app, c) for app, c in unresolved.items() if is_guid(c["correlation_id"]) and c["correlation_id"].strip("0-")]
    if not ENABLE_ACTIVITY_LOG_GAPS or MAX_ACTIVITY_LOG_LOOKUPS == 0:
        rec.update(status="not_configured", notes="Activity Log reads are disabled.")
    elif not lookups:
        rec.update(status="not_needed", notes="No unresolved application actor on a non-noise change.")
    else:
        started = time.monotonic()
        budget = max(0, MAX_ACTIVITY_LOG_LOOKUPS - raw.get("lookups_used", 0))
        for app, c in lookups[:budget]:
            url = activity_log_url(c["subscription_id"], c["when"] - timedelta(hours=1), c["when"] + timedelta(hours=1),
                                   f"correlationId eq '{c['correlation_id'].lower()}'", "caller,claims,correlationId,operationName,resourceId,status")
            try:
                for event in arm_get_pages(reader, url, rec["id"], rec, max_pages=2):
                    claims = event.get("claims") if isinstance(event.get("claims"), dict) else {}
                    if str(claims.get("appid") or "").lower() != app:
                        continue
                    mirid = str(claims.get("xms_mirid") or "")
                    oid = str(claims.get("http://schemas.microsoft.com/identity/claims/objectidentifier") or "").lower()
                    if mirid.startswith("/subscriptions/"):
                        kind = "policy assignment " if "/policyassignments/" in mirid.lower() else ""
                        app_name[app], app_how[app] = kind + resource_name_of(mirid), "activity_log"
                    if is_guid(oid):
                        app_oid[app] = oid
                    rec["records"] += 1
                    break
            except DigestError as exc:
                fail_receipt(rec, exc, rec["records"] > 0)
                if exc.code in ("collection_deadline", "request_cap"):
                    break
        if len(lookups) > budget and rec["status"] == "complete":
            rec.update(status="partial", notes=f"Only {budget} of {len(lookups)} actors were looked up (MAX_ACTIVITY_LOG_LOOKUPS is shared with delete attribution).")
        rec["seconds"] = round(time.monotonic() - started, 2)
    apps = [a for a in unresolved if a not in app_name][:MAX_LOOKUP_IDS]
    oids = sorted(set(app_oid.values()) | principals)[:MAX_LOOKUP_IDS]
    principal_name = {}
    if apps or oids:
        rows = _run(raw, reader, config, q_identity_maps(apps, oids), "arg_identity_maps",
                    "Managed identity name maps (resources: clientId / principalId)", row_cap=5000)
        for row in rows:
            name = clean(row.get("name"), 200)
            for key in ("clientId",):
                value = str(row.get(key) or "").lower()
                if value in unresolved and value not in app_name:
                    app_name[value], app_how[value] = name, "uami"
            for key in ("uamiPrincipalId", "principalId"):
                value = str(row.get(key) or "").lower()
                if is_guid(value):
                    principal_name[value] = name + (" (managed identity)" if row.get("type") == "microsoft.managedidentity/userassignedidentities" else f" ({type_label(str(row.get('type') or ''))} identity)")
        for app, oid in app_oid.items():
            if app not in app_name and oid in principal_name:
                app_name[app], app_how[app] = principal_name[oid], "activity_log+arg"
    else:
        raw["sources"].append(receipt("arg_identity_maps", "Managed identity name maps (resources: clientId / principalId)", "not_needed",
                                      "No unresolved application actors or principals."))
    graph_status = read_graph_names(reader, [a for a in unresolved if a not in app_name], [p for p in principals if p not in principal_name],
                                    app_name, app_how, principal_name, raw)
    for c in relevant:
        app = c["changed_by"].lower()
        if app in app_name and c["actor_resolution"] == "raw":
            c["actor_display"], c["actor_resolution"] = app_name[app], app_how[app]
            if app_how[app] == "graph-first-party" and c["actor_class"] == "automation":
                c["actor_class"] = "platform"
    for chain in analysis["delete_chains"]:
        app = chain["actor"].lower()
        if app in app_name:
            chain["actor_display"] = app_name[app]
    for r in analysis["role_assignments"]:
        r["principal_display"] = principal_name.get(r["principal_id"].lower(), "")
        if is_guid(r["created_by"]) and r["created_by"].lower() in principal_name:
            r["created_by"] = principal_name[r["created_by"].lower()]
    return graph_status


def read_graph_names(reader, app_ids, principal_ids, app_name, app_how, principal_name, raw):
    rec = receipt("graph_names", "Microsoft Graph display names (optional)")
    raw["sources"].append(rec)
    if not ENABLE_GRAPH_NAMES:
        rec.update(status="not_configured", notes="ENABLE_GRAPH_NAMES is False: application IDs are shown raw when no other source resolves them.")
        return "not_configured"
    if not app_ids and not principal_ids:
        rec.update(status="not_needed", notes="Nothing left to resolve.")
        return "not_needed"
    started = time.monotonic()
    try:
        for app in app_ids[:10]:
            query = urlencode({"$filter": f"appId eq '{app}'", "$select": "displayName,appOwnerOrganizationId"}, quote_via=quote, safe="'")
            payload = reader.request("GET", f"{GRAPH}/v1.0/servicePrincipals?{query}", rec["id"])
            rec["pages"] += 1
            found = (payload.get("value") or [None])[0]
            if isinstance(found, dict) and found.get("displayName"):
                first_party = str(found.get("appOwnerOrganizationId") or "").lower() in MICROSOFT_TENANTS
                app_name[app] = clean(found["displayName"], 200) + (" (Microsoft service)" if first_party else "")
                app_how[app] = "graph-first-party" if first_party else "graph"
                rec["records"] += 1
        for pid in principal_ids[:10]:
            query = urlencode({"$select": "displayName,userPrincipalName"}, quote_via=quote)
            try:
                payload = reader.request("GET", f"{GRAPH}/v1.0/directoryObjects/{pid}?{query}", rec["id"])
            except DigestError as exc:
                if exc.http_status == 404:
                    continue
                raise
            rec["pages"] += 1
            name = clean(payload.get("userPrincipalName") or payload.get("displayName"), 200)
            if name:
                principal_name[pid] = name
                rec["records"] += 1
    except DigestError as exc:
        fail_receipt(rec, exc, rec["records"] > 0)
        if exc.http_status in (401, 403):
            rec["notes"] = "Graph permission not granted to the managed identity (Application.Read.All); raw IDs are shown."
    rec["seconds"] = round(time.monotonic() - started, 2)
    return rec["status"]


# ------------------------- snapshot -------------------------
OPTIONAL_SOURCES = {"activity_log_actor_lookup", "arg_identity_maps", "graph_names"}
NAME_RESOLUTION = {"upn": "UPN from Change Analysis", "configured": "EXPECTED_AUTOMATION", "uami": "user-assigned identity (clientId)",
                   "activity_log": "Activity Log claims", "activity_log+arg": "Activity Log + Resource Graph", "graph": "Microsoft Graph",
                   "graph-first-party": "Microsoft Graph (Microsoft first-party app)", "heuristic": "heuristic", "raw": "raw value"}


def change_record(c):
    return {
        "change_id": c["change_id"], "timestamp_utc": iso(c["when"]), "timestamp_local": c["timestamp_local"],
        "subscription_id": c["subscription_id"], "resource_group": c["resource_group"], "resource_id": c["resource_id"],
        "resource_name": c["resource_name"], "resource_type": c["resource_type"], "resource_type_label": type_label(c["resource_type"]),
        "change_type": c["change_type"], "level": c["level"], "reasons": c["reasons"], "flags": c["flags"],
        "actor": {"changed_by": c["changed_by"], "changed_by_type": c["changed_by_type"], "actor_class": c["actor_class"],
                  "display_name": c["actor_display"], "resolution": c["actor_resolution"]},
        "client": {"client_type": c["client_type"], "client_class": c["client_class"]},
        "operation": c["operation"], "correlation_id": c["correlation_id"], "managed_rg": c["managed_rg"], "prod": c["prod"],
        "security": c["security"], "source": c["source"], "noise_paths": sum(1 for p in c["paths"] if p["level"] == "noise"),
        "paths": [p for p in c["paths"] if p["level"] != "noise"],
    }


def item_sort_key(item):
    return (-RANK[item["level"]], 0 if set(item.get("flags") or ()) & {"internet-exposed", "exposure increased"} else 1,
            -(parse_time(item["when_utc"]) or datetime(1970, 1, 1, tzinfo=timezone.utc)).timestamp())


def build_items(analysis):
    items = []
    for chain in analysis["delete_chains"]:
        names = ", ".join(chain["resources"][:3]) + (f" +{len(chain['resources']) - 3}" if len(chain["resources"]) > 3 else "")
        title = f"Deleted {names}" if chain["deleted"] == 1 else f"Deleted {chain['deleted']} resources: {names}"
        items.append({"kind": "delete", "level": chain["level"], "title": title,
                      "resource": names, "type": ", ".join(type_label(t) for t in chain["resource_types"][:2]),
                      "resource_group": ", ".join(chain["resource_groups"][:2]), "when_utc": iso(chain["last"]),
                      "who": chain["actor_display"], "client": chain["client_type"], "why": "; ".join(chain["reasons"][:2]),
                      "flags": chain["flags"], "ref": chain["correlation_id"]})
    for c in analysis["relevant"]:
        if c["change_type"] == "Delete":
            continue
        items.append({"kind": "change", "level": c["level"], "title": f"{c['change_type']} {c['resource_name']}", "resource": c["resource_name"],
                      "type": type_label(c["resource_type"]), "resource_group": c["resource_group"], "when_utc": iso(c["when"]),
                      "who": c["actor_display"], "client": c["client_type"], "why": "; ".join(c["reasons"][:2]), "flags": c["flags"],
                      "ref": c["change_id"]})
    for r in analysis["role_assignments"]:
        items.append({"kind": "role_assignment", "level": r["level"], "title": f"Role assignment {r['kind']}: {r['role_name']}",
                      "resource": r["scope_label"], "type": "Role assignment", "resource_group": r["resource_group"], "when_utc": r["created_utc"],
                      "who": r["created_by"], "client": "", "why": f"{r['role_name']} for {r['principal_type'] or 'principal'} "
                      f"{r['principal_display'] or r['principal_id']}" + (" (privileged role)" if r["privileged"] else ""),
                      "flags": [], "ref": r["id"]})
    for g in analysis["gaps"]:
        items.append({"kind": "activity_log", "level": g["level"], "title": g["label"], "resource": f"{g['resource_name']} on {g['target']}",
                      "type": "Activity Log", "resource_group": g["resource_group"], "when_utc": g["time_utc"], "who": g["caller"],
                      "client": "", "why": g["label"] + (f" ({g['role_name']})" if g.get("role_name") else ""), "flags": [],
                      "ref": g["correlation_id"]})
    items.sort(key=item_sort_key)
    return items


def build_actors(relevant):
    actors = {}
    for c in relevant:
        a = actors.setdefault(c["changed_by"].lower() or "(none)", {
            "changed_by": c["changed_by"], "classes": Counter(), "display_name": c["actor_display"], "resolution": c["actor_resolution"],
            "changed_by_type": c["changed_by_type"], "changes": 0, "creates": 0, "updates": 0, "deletes": 0, "high": 0, "medium": 0,
            "low": 0, "resource_groups": [], "clients": []})
        a["classes"][c["actor_class"]] += 1
        a["changes"] += 1
        a[{"Create": "creates", "Delete": "deletes"}.get(c["change_type"], "updates")] += 1
        a[c["level"]] += 1
        if c["resource_group"] and c["resource_group"] not in a["resource_groups"]:
            a["resource_groups"].append(c["resource_group"])
        if c["client_type"] and c["client_type"] not in a["clients"]:
            a["clients"].append(c["client_type"])
    out = []
    for a in actors.values():
        a["actor_class"] = a.pop("classes").most_common(1)[0][0]
        a["resource_group_count"] = len(a["resource_groups"])
        a["resource_groups"] = a["resource_groups"][:8]
        a["clients"] = a["clients"][:6]
        out.append(a)
    return sorted(out, key=lambda a: (-(a["high"] * 100 + a["medium"] * 10), -a["changes"]))


def build_noise(analysis, raw, config):
    managed = analysis["ctx"]["managed"]
    by_reason, by_type, by_actor_type, managed_noise, server_total = Counter(), Counter(), Counter(), 0, 0
    for row in raw["noise_types"]:
        count = int(row.get("changes") or 0)
        agent = int(row.get("agentChanges") or 0)
        rg_key = str(row.get("rgKey") or "")
        if rg_excluded(config, rg_key.split("/", 1)[-1]):
            continue
        server_total += count
        by_reason["agent-reported inventory"] += agent
        by_reason["platform metadata/timestamp"] += count - agent
        by_type[str(row.get("rtype") or "")] += count
        by_actor_type[str(row.get("byType") or "Unspecified")] += count
        managed_noise += count if rg_key in managed else 0
    paths = Counter({str(r.get("pattern") or ""): int(r.get("occurrences") or 0) for r in raw["noise_paths"]})
    for c in analysis["changes"]:
        if c["level"] == "noise":
            by_reason[c["reasons"][0]] += 1
            by_type[c["resource_type"]] += 1
            by_actor_type[c["changed_by_type"] or "Unspecified"] += 1
            managed_noise += 1 if c["managed_rg"] else 0
            for p in {re.sub(r"\[\d+\]", "[*]", p["path"]) for p in c["paths"]}:
                paths[p] += 1
    low_groups = Counter()
    low_meta = {}
    for c in analysis["relevant"]:
        if c["level"] == "low":
            patterns = tuple(sorted({re.sub(r"\[\d+\]", "[*]", p["path"]) for p in c["paths"] if p["level"] != "noise"})[:3])
            key = (c["actor_display"], c["resource_type"], c["change_type"], c["reasons"][0] if c["reasons"] else "", patterns)
            low_groups[key] += 1
            low_meta.setdefault(key, set()).add(c["resource_id"].lower())
    low = [{"count": n, "resources": len(low_meta[k]), "actor": k[0], "resource_type": k[1], "type_label": type_label(k[1]),
            "change_type": k[2], "reason": k[3], "paths": list(k[4])} for k, n in low_groups.most_common(12)]
    return {"total": server_total + sum(1 for c in analysis["changes"] if c["level"] == "noise"), "server_side": server_total,
            "by_reason": dict(by_reason.most_common()), "by_changed_by_type": dict(by_actor_type.most_common()),
            "top_paths": [{"path_pattern": p, "occurrences": n} for p, n in paths.most_common(15) if p],
            "top_types": [{"resource_type": t, "label": type_label(t), "changes": n} for t, n in by_type.most_common(10) if t],
            "managed_rg_changes": managed_noise + sum(1 for c in analysis["relevant"] if c["managed_rg"]),
            "low_summaries": low}


def build_timeline(relevant, window, zone):
    span = window["end"] - window["start"]
    step = timedelta(hours=1) if span <= timedelta(hours=24) else timedelta(hours=6) if span <= timedelta(days=7) else timedelta(hours=12)
    buckets, cursor = [], window["start"]
    while cursor < window["end"]:
        buckets.append({"start_utc": iso(cursor), "label": cursor.astimezone(zone).strftime("%H:%M" if step < timedelta(hours=6) else "%d %b %H:%M"),
                        "high": 0, "medium": 0, "low": 0})
        cursor += step
    for c in relevant:
        index = int((c["when"] - window["start"]) / step)
        if 0 <= index < len(buckets):
            buckets[index][c["level"]] += 1
    return {"step_hours": int(step.total_seconds() // 3600), "buckets": buckets}


def build_headline(counts, items, window, core_failed):
    label = window["label"].lower()
    high, medium = counts["by_level"]["high"], counts["by_level"]["medium"]
    extra = counts["new_role_assignments"] + counts["activity_log_gaps"]
    if core_failed:
        verdict = "Change data could not be read completely, so this digest is incomplete. See Coverage and sources."
    elif high + medium == 0 and extra == 0:
        verdict = (f"No high or medium changes in the {label}. {counts['total']} changes recorded, "
                   f"{counts['noise_filtered_pct']}% filtered out as platform noise.")
    else:
        verdict = f"{high + medium} relevant change{'s' if high + medium != 1 else ''} out of {counts['total']} in the {label}"
        verdict += f" ({high} high, {medium} medium)"
        if extra:
            verdict += f", plus {extra} RBAC and Activity Log event{'s' if extra != 1 else ''}"
        verdict += "."
    highlights, seen = [], set()
    for item in items:
        if item["level"] != "high" or len(highlights) >= 5 or item["resource"].lower() in seen:
            continue
        seen.add(item["resource"].lower())
        if item["kind"] == "delete":
            text_value = item["title"] + (" by " + item["who"] if item["who"] else "")
        elif item["kind"] == "role_assignment":
            text_value = f"{item['title']} on {item['resource']}"
        else:
            reason = item["why"] or item["title"]
            text_value = f"{item['resource']}: {reason[:1].upper() + reason[1:]}"
        if text_value not in highlights:
            highlights.append(clean(text_value, 220))
    return {"verdict": verdict, "highlights": highlights}


def build_snapshot(analysis, raw, config, params, reader_stats):
    w, ctx = params["window"], analysis["ctx"]
    changes, relevant = analysis["changes"], analysis["relevant"]
    noise = build_noise(analysis, raw, config)
    by_type = Counter(c["change_type"] for c in changes)
    by_type["Update"] += noise["server_side"]
    by_level = {lv: sum(1 for c in changes if c["level"] == lv) for lv in ("high", "medium", "low")}
    by_level["noise"] = noise["total"]
    total = len(changes) + noise["server_side"]
    sources = raw["sources"]
    for s in sources:
        s["optional"] = s["id"] in OPTIONAL_SOURCES
    core_failed = any(s["id"] == "arg_resourcechanges" and s["status"] in ("denied", "error", "skipped") for s in sources)
    partial = any(not s["optional"] and s["status"] in ("partial", "denied", "error", "skipped") for s in sources)
    counts = {
        "total": total, "by_change_type": dict(by_type), "by_level": by_level,
        "noise_filtered_pct": round(100 * noise["total"] / total) if total else 0,
        "reported": by_level["high"] + by_level["medium"], "deletes": by_type.get("Delete", 0),
        "delete_operations": len(analysis["delete_chains"]), "security": sum(1 for c in relevant if c["security"]),
        "new_role_assignments": sum(1 for r in analysis["role_assignments"] if r["kind"] == "created"),
        "updated_role_assignments": sum(1 for r in analysis["role_assignments"] if r["kind"] == "updated"),
        "privileged_role_assignments": sum(1 for r in analysis["role_assignments"] if r["privileged"]),
        "activity_log_gaps": len(analysis["gaps"]), "failed_attempts": len(analysis["failed_gaps"]),
        "by_actor_class": dict(Counter(c["actor_class"] for c in relevant).most_common()),
        "by_client_class": dict(Counter(c["client_class"] for c in relevant).most_common()),
        "unusual": {"after_hours": sum(1 for c in relevant if "after-hours" in c["flags"]), "first_time_actor_rg": len(analysis["first_time"]),
                    "bursts": len(analysis["bursts"]), "click_ops": sum(1 for c in relevant if "click-ops" in c["flags"]),
                    "click_ops_prod": sum(1 for c in relevant if "click-ops in production" in c["flags"])},
        "excluded_by_configuration": analysis["excluded"],
    }
    items = build_items(analysis)
    headline = build_headline(counts, items, w, core_failed)
    zone_name = BUSINESS_TIMEZONE if ctx["zone_source"] != "UTC fallback (time zone not available)" else "UTC"
    subs = config["subscriptions"] or sorted(raw["subscription_names"])
    status = "partial" if partial or core_failed else "ok"
    snapshot = {
        "schema": "azure-change-digest/1", "provenance": "LIVE", "tool": TOOL_NAME, "tool_version": TOOL_VERSION,
        "generated_utc": iso(utc_now()), "status": status, "client_name": config["client_name"],
        "window": {"period": w["period"], "label": w["label"], "start_utc": w["start_utc"], "end_utc": w["end_utc"],
                   "start_local": local_label(w["start"], ctx["zone"]), "end_local": local_label(w["end"], ctx["zone"]),
                   "timezone": zone_name, "timezone_source": ctx["zone_source"], "business_hours": list(config["hours"]),
                   "business_days": list(config["days"])},
        "parameters": {"min_level": params["min_level"], "resource_group": params["resource_group"]},
        "scope": {"subscriptions": [{"id": s, "name": raw["subscription_names"].get(s, s)} for s in subs],
                  "management_group": config["management_group"]},
        "counts": counts, "headline": headline,
        "items": items,
        "changes": [change_record(c) for c in relevant],
        "delete_chains": [{**{k: v for k, v in ch.items() if k not in ("first", "last")}, "first_utc": iso(ch["first"]),
                           "last_utc": iso(ch["last"]), "last_local": local_label(ch["last"], ctx["zone"])} for ch in analysis["delete_chains"]],
        "role_assignments": analysis["role_assignments"],
        "activity_log_gaps": analysis["gaps"], "failed_attempts": analysis["failed_gaps"],
        "actors": build_actors(relevant),
        "client_matrix": [{"client_class": k[0], "actor_class": k[1], "changes": n}
                          for k, n in Counter((c["client_class"], c["actor_class"]) for c in relevant).most_common()],
        "unusual": {"after_hours": [c["change_id"] for c in relevant if "after-hours" in c["flags"]],
                    "first_time_actor_rg": analysis["first_time"], "bursts": analysis["bursts"]},
        "noise": noise, "timeline": build_timeline(relevant, w, ctx["zone"]),
        "coverage": {"status": status, "sources": sources, "not_covered": NOT_COVERED, "retention_days": RETENTION_DAYS,
                     "latency_note": "Change records are usually available in Azure Resource Graph within 5 minutes.",
                     "graph": next((s["status"] for s in sources if s["id"] == "graph_names"), "not_configured"),
                     "activity_log": next((s["status"] for s in sources if s["id"] == "activity_log_gaps"), "not_configured"),
                     "identity_check": reader_stats.get("identity", {}), "http_requests": reader_stats.get("requests", 0),
                     "throttled_waits": reader_stats.get("throttled", 0), "collection_seconds": reader_stats.get("seconds", 0),
                     "managed_resource_groups": len(ctx["managed"]), "prod_resource_groups": len(ctx["prod_rgs"])},
        "sources": LEARN_SOURCES,
    }
    return snapshot


# ------------------------- chat views (operation=query) -------------------------
def compact_item(item):
    return {"level": item["level"], "kind": item["kind"], "what": clean(item["title"], 110), "where": clean(item["resource_group"], 60),
            "who": clean(item["who"], 70), "when": item["when_utc"], "why": clean(item["why"], 140)}


def response_bytes(value):
    return len(json.dumps(value).encode("utf-8"))


def view_rows(snapshot, params):
    view, floor = params["view"], RANK[params["min_level"]]
    if view == "relevant":
        return [compact_item(i) for i in snapshot["items"] if RANK[i["level"]] >= floor]
    if view == "deletes":
        return [{"level": d["level"], "when": d["last_utc"], "who": clean(d["actor_display"], 70), "client": d["client_type"],
                 "deleted": d["deleted"], "resources": ", ".join(d["resources"][:4]), "types": ", ".join(type_label(t) for t in d["resource_types"][:3]),
                 "managed_rg": d["managed"], "correlation_id": d["correlation_id"]} for d in snapshot["delete_chains"]]
    if view == "security":
        rows = [compact_item(i) for i in snapshot["items"] if i["kind"] in ("role_assignment", "activity_log")
                or (i["kind"] in ("change", "delete") and any(c["security"] for c in snapshot["changes"] if c["change_id"] == i["ref"] or c["correlation_id"] == i["ref"]))]
        return sorted(rows, key=lambda r: -RANK[r["level"]])
    if view == "actors":
        return [{"actor": clean(a["display_name"], 80), "changed_by": clean(a["changed_by"], 80), "class": a["actor_class"],
                 "changes": a["changes"], "creates": a["creates"], "updates": a["updates"], "deletes": a["deletes"],
                 "high": a["high"], "medium": a["medium"], "resource_groups": a["resource_group_count"], "clients": a["clients"][:3]}
                for a in snapshot["actors"]]
    if view == "unusual":
        rows = []
        for c in snapshot["changes"]:
            for flag in c["flags"]:
                if flag in ("after-hours", "first-time actor on RG", "burst", "click-ops", "click-ops in production"):
                    rows.append({"flag": flag, "level": c["level"], "what": f"{c['change_type']} {c['resource_name']}", "where": c["resource_group"],
                                 "who": clean(c["actor"]["display_name"], 70), "when_local": c["timestamp_local"]})
        return rows
    if view == "rbac":
        rows = [{"kind": "role assignment " + r["kind"], "level": r["level"], "role": r["role_name"], "scope": r["scope_label"],
                 "principal": clean(r["principal_display"] or r["principal_id"], 60), "principal_type": r["principal_type"],
                 "by": clean(r["created_by"], 70), "when": r["created_utc"]} for r in snapshot["role_assignments"]]
        rows += [{"kind": g["label"], "level": g["level"], "role": g.get("role_name", ""), "scope": g["target"], "principal": g.get("principal_id", ""),
                  "principal_type": g.get("principal_type", ""), "by": clean(g["caller"], 70), "when": g["time_utc"]}
                 for g in snapshot["activity_log_gaps"] if "roleassignments" in g["operation"].lower() or "roledefinitions" in g["operation"].lower()]
        return rows
    if view == "noise":
        n = snapshot["noise"]
        return [{"total": n["total"], "pct_of_all": snapshot["counts"]["noise_filtered_pct"], "by_reason": n["by_reason"],
                 "managed_rg_changes": n["managed_rg_changes"]}] + \
               [{"path_pattern": p["path_pattern"], "occurrences": p["occurrences"]} for p in n["top_paths"]] + \
               [{"resource_type": t["resource_type"], "changes": t["changes"]} for t in n["top_types"]]
    if view == "coverage":
        return [{"source": s["id"], "status": s["status"], "pages": s["pages"], "records": s["records"],
                 "note": clean((s["errors"][0]["message"] if s["errors"] else s["notes"]), 160)} for s in snapshot["coverage"]["sources"]]
    return []


def query_view(snapshot, params):
    counts = snapshot["counts"]
    result = {"status": snapshot["status"], "operation": "query", "view": params["view"], "period": params["window"]["period"],
              "window_utc": [snapshot["window"]["start_utc"], snapshot["window"]["end_utc"]], "min_level": params["min_level"],
              "resource_group": params["resource_group"]}
    if params["view"] == "summary":
        result.update(headline=snapshot["headline"]["verdict"], counts=compact_counts(counts),
                      top_items=[compact_item(i) for i in snapshot["items"] if RANK[i["level"]] >= RANK[params["min_level"]]][:min(5, params["limit"])])
        while result["top_items"] and response_bytes(result) > TRANSPORT_BYTES:
            result["top_items"].pop()
        return result
    rows = view_rows(snapshot, params)
    selected = rows[:params["limit"]]
    result.update(total_matched=len(rows), returned=len(selected), transport_capped=False, rows=selected)
    if len(selected) < len(rows):
        result["note"] = "More rows exist: open the HTML report or the JSON snapshot (operation=report) for the full list."
    while selected and response_bytes(result) > TRANSPORT_BYTES:
        selected = selected[:-1]
        result.update(rows=selected, returned=len(selected), transport_capped=True,
                      note="More rows exist: open the HTML report or the JSON snapshot (operation=report) for the full list.")
    return result


def compact_counts(counts):
    return {"total": counts["total"], "high": counts["by_level"]["high"], "medium": counts["by_level"]["medium"],
            "low": counts["by_level"]["low"], "noise": counts["by_level"]["noise"], "noise_pct": counts["noise_filtered_pct"],
            "deletes": counts["deletes"], "security": counts["security"], "new_role_assignments": counts["new_role_assignments"],
            "activity_log_gaps": counts["activity_log_gaps"], "unusual": counts["unusual"]}


# ------------------------- offline HTML report -------------------------
REPORT_CSS = """
:root{--bar:#161B22;--hero:#0D2F33;--accent:#0E7C86;--accent-strong:#0A626A;--accent-soft:#E3F3F4;--accent-dark:#7FD6CF;
--bg:#F3F5F7;--card:#fff;--text:#1B1F24;--muted:#59636E;--faint:#667085;--line:#DCE2E8;--line2:#EDF0F3;--off:#EEF1F4;
--high:#B93815;--high-bg:#FFEAD5;--high-line:#F7C9A6;--high-bar:#EF6820;--high-tint:#FFF7F0;
--medium:#93370D;--medium-bg:#FEF0C7;--medium-line:#F2D27F;--medium-bar:#F79009;--medium-tint:#FFFBEE;
--low:#175CD3;--low-bg:#D1E9FF;--low-line:#B2D6FA;--low-bar:#2E90FA;--info-bar:#98A2B3;
--old-bg:#FCEBEA;--old:#8A1C12;--new-bg:#E5F4EA;--new:#0B5D2A}
*{box-sizing:border-box}html{scroll-behavior:smooth;scroll-padding-top:64px;scrollbar-color:#C5CED8 transparent}body{margin:0;background:var(--bg);color:var(--text);
font:14px/1.5 "Segoe UI",system-ui,-apple-system,Roboto,Arial,sans-serif;-webkit-text-size-adjust:100%}
::selection{background:#BFE6E8;color:var(--text)}:focus-visible{outline:3px solid var(--accent);outline-offset:2px}
code,.mono{font-family:"Cascadia Mono",Consolas,"SFMono-Regular",Menlo,monospace;font-size:12.5px}
a{color:var(--accent-strong);text-underline-offset:3px}.wrap{max-width:1360px;margin:0 auto;padding:0 40px}.nw{white-space:nowrap}
.sr{position:absolute;width:1px;height:1px;margin:-1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
.top{background:var(--bar);color:#fff}.top .wrap{display:flex;align-items:center;justify-content:space-between;gap:16px;min-height:56px}
.top :focus-visible{outline-color:var(--accent-dark)}
.wm{display:inline-flex;align-items:center;gap:10px;font-weight:600;font-size:17px;white-space:nowrap}
.wm svg{width:28px;height:28px;padding:5px;border-radius:7px;background:var(--accent);flex:none}
.wm small{font-weight:400;color:#AEB8C3;font-size:13px;margin-left:4px}
.pills{display:flex;gap:8px;align-items:center;justify-content:flex-end}.pill{border:1px solid #3B4450;border-radius:999px;padding:4px 11px;font-size:12px;color:#DCE3EA;white-space:nowrap}
.pill.ro{border-color:#3D7F84;color:#BFEAE6;font-weight:600}
.pbtn{display:inline-flex;align-items:center;gap:7px;min-height:34px;padding:0 14px;border:0;border-radius:8px;background:var(--accent);color:#fff;font:inherit;font-size:13px;font-weight:600;cursor:pointer;white-space:nowrap}
.pbtn:hover{background:var(--accent-strong)}.pbtn svg{width:16px;height:16px;flex:none}
.hero{background:var(--hero);color:#fff;padding:34px 0 30px}
.hero-in{display:grid;grid-template-columns:minmax(0,1fr) 300px;grid-template-areas:"head card" "hl card" "meta meta" "kpis kpis" "sn sn";column-gap:48px}
.hero-head{grid-area:head}.hl{grid-area:hl}.meta{grid-area:meta}.kpis{grid-area:kpis}.sn{grid-area:sn}
.eyebrow{color:var(--accent-dark);font-weight:700;letter-spacing:.12em;font-size:12px;text-transform:uppercase}
h1{font-size:40px;line-height:1.1;margin:8px 0 12px;font-weight:700;letter-spacing:-.015em;text-wrap:balance}
.verdict{font-size:19px;line-height:1.45;max-width:64ch;margin:0 0 14px;color:#fff;font-weight:600;text-wrap:pretty}
.hl{list-style:none;margin:0 0 20px;padding:0}.hl li{position:relative;padding:3px 0 3px 20px;color:#D7E2E6;font-size:14.5px}
.hl li:before{content:"";position:absolute;left:2px;top:11px;width:8px;height:8px;border-radius:2px;background:var(--high-bar)}
.vcard{grid-area:card;align-self:start;margin-top:6px;background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.16);border-radius:14px;padding:18px 20px}
.vcard .k{font-size:12.5px;font-weight:600;color:#C3D0D6}.vcard b{display:block;font-size:25px;line-height:1.15;margin:5px 0 8px;font-weight:700}
.vcard p{margin:0;font-size:13.5px;color:#D3DDE2}.vcard p+p{margin-top:6px}.v-high b,.v-warn b{color:#FDB022}.v-review b{color:#FEDF89}.v-ok b{color:#75E0A7}
.meta{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 22px}.meta span{border:1px solid rgba(255,255,255,.16);border-radius:7px;padding:5px 10px;font-size:12.5px;color:#D3DDE2}
.meta b{color:#fff;font-weight:600}.meta span.st-partial{background:rgba(247,144,9,.14);border-color:#F5B25E;color:#FFDDB0}
.kpis{display:grid;grid-template-columns:repeat(6,1fr);gap:12px}
.kpi{background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.14);border-radius:10px;padding:14px 15px}
.kpi b{display:block;font-size:32px;line-height:1.05;font-weight:700;font-variant-numeric:tabular-nums}.kpi span{display:block;color:#C3D0D6;font-size:13px;margin-top:5px}
.sn{margin-top:22px}.sn-h{display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;font-size:13px;color:#C3D0D6;margin-bottom:8px}.sn-h b{color:#fff}
.bar{display:flex;height:14px;border-radius:4px;overflow:hidden;background:rgba(255,255,255,.08)}.bar i{display:block;height:100%}
.b-high{background:var(--high-bar)}.b-medium{background:var(--medium-bar)}.b-low{background:var(--low-bar)}.b-noise{background:#41605F}.b-off{background:var(--off);box-shadow:inset 0 0 0 1px var(--line)}
.legend{display:flex;flex-wrap:wrap;gap:6px 16px;margin-top:9px;font-size:12.5px;color:#C3D0D6}.legend span{display:inline-flex;align-items:center;gap:6px}
.legend i{width:10px;height:10px;border-radius:2px;display:inline-block}.hero .legend b{color:#fff}.card .legend{color:var(--muted)}.card .legend b{color:var(--text)}
.secnav{position:sticky;top:0;z-index:20;background:#fff;border-bottom:1px solid var(--line)}
.secnav .wrap{display:flex;gap:2px;overflow-x:auto;scrollbar-width:none}.secnav .wrap::-webkit-scrollbar{display:none}
.secnav a{white-space:nowrap;text-decoration:none;color:var(--muted);font-size:13px;font-weight:600;padding:13px 10px 11px;border-bottom:2px solid transparent}
.secnav a:hover,.secnav a.on{color:var(--text);border-bottom-color:var(--accent)}.secnav a small{color:var(--faint);font-size:12px;font-weight:600;margin-left:4px}
main{padding:26px 0 36px}.sec{margin:0 0 36px}.sec-h{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap}
h2{font-size:22px;line-height:1.25;margin:0;font-weight:700;letter-spacing:-.005em}.sec-n{font-size:13px;font-weight:700;color:var(--accent-strong);background:var(--accent-soft);border-radius:999px;padding:1px 9px}
.sec-sub{color:var(--muted);margin:4px 0 14px;max-width:75ch}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:18px 20px}.card h3{font-size:15px;margin:0 0 3px}
.card .sub{color:var(--muted);font-size:13px;margin:0 0 12px;max-width:80ch}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:16px}.grid3{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}.grid2>*,.grid3>*{min-width:0}
.ov{display:grid;grid-template-columns:1.6fr 1fr;gap:16px}.ov>*{min-width:0}
.lvl{display:inline-block;border:1px solid;border-radius:5px;padding:0 7px;font-size:12px;font-weight:700;letter-spacing:.01em;line-height:20px;white-space:nowrap}
.lvl-high{color:var(--high);background:var(--high-bg);border-color:var(--high-line)}.lvl-medium{color:var(--medium);background:var(--medium-bg);border-color:var(--medium-line)}
.lvl-low{color:var(--low);background:var(--low-bg);border-color:var(--low-line)}
.ct{display:inline-block;font-size:12px;font-weight:700;border-radius:4px;padding:0 6px;line-height:20px;background:var(--line2);color:#33404D;white-space:nowrap}
.ct-delete{background:#2B3036;color:#fff}.ct-create{background:var(--accent-soft);color:var(--accent-strong)}
.flag{display:inline-block;border:1px solid var(--line);background:#F7F9FA;border-radius:5px;padding:0 7px;font-size:12px;line-height:20px;margin:2px 4px 2px 0;color:#38434F;white-space:nowrap}
.flag.risk{border-color:var(--high-line);background:var(--high-bg);color:var(--high);font-weight:700}.flag.prod{border-color:#C8B5EE;background:#F4EFFD;color:#5B3A9B;font-weight:600}
.cls{display:inline-block;font-size:12px;color:var(--muted);white-space:nowrap}
.rindex{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin:0 0 16px}.rindex .k{font-size:12px;font-weight:700;color:var(--muted);margin:0 2px 0 6px}.rindex .k:first-child{margin-left:0}
.ri{display:inline-flex;align-items:center;gap:7px;padding:4px 10px 4px 9px;border:1px solid var(--line);border-radius:999px;background:#fff;color:var(--text);text-decoration:none;font-size:13px;font-weight:600;white-space:nowrap}
.ri:hover{border-color:var(--accent);color:var(--accent-strong)}.ri i{width:8px;height:8px;border-radius:50%;background:var(--low-bar);flex:none}.ri.more{border-style:dashed;color:var(--accent-strong)}
.ri.l-high i{background:var(--high-bar)}.ri.l-medium i{background:var(--medium-bar)}.ri span{color:var(--faint);font-variant-numeric:tabular-nums}
.rc{background:var(--card);border:1px solid var(--line);border-radius:12px;margin-bottom:14px;overflow:hidden;scroll-margin-top:64px}
.rc-head{display:flex;justify-content:space-between;align-items:flex-start;gap:14px;padding:14px 18px 12px;border-bottom:1px solid var(--line2)}
.rc.l-high .rc-head{background:var(--high-tint)}.rc.l-medium .rc-head{background:var(--medium-tint)}
.rc-id{display:flex;align-items:center;gap:10px;flex-wrap:wrap;min-width:0}.rc-id h3{margin:0;font-size:16.5px;overflow-wrap:anywhere}
.rc-type{color:var(--muted);font-size:13px}.rc-where{color:var(--muted);font-size:12.5px;text-align:right}.rc-where a{font-weight:600}
.ev{display:grid;grid-template-columns:150px 1fr;gap:16px;padding:13px 18px;border-top:1px solid var(--line2)}.ev:first-child{border-top:0}
.ev-when{font-variant-numeric:tabular-nums}.ev-when b{display:block;font-size:13.5px}.ev-when span{display:block;color:var(--muted);font-size:12px}
.ev-line{display:flex;flex-wrap:wrap;align-items:center;gap:6px 8px;margin-bottom:5px}.who{font-weight:600;overflow-wrap:break-word;min-width:0}
.why{margin:0 0 6px;font-size:14px;line-height:1.45}.why b{font-weight:600}
table.diff{width:auto;max-width:100%;border:1px solid var(--line);border-radius:8px;border-collapse:separate;border-spacing:0;margin-top:8px;background:#FBFCFD}
table.diff td{padding:5px 10px;border-bottom:1px solid var(--line2);vertical-align:top}table.diff tr:last-child td{border-bottom:0}
.d-path{min-width:200px;max-width:420px}.d-path code{color:#33404D;overflow-wrap:break-word}.d-arr{color:var(--faint);padding:5px 2px!important}
.d-old,.d-new{display:inline-block;border-radius:4px;padding:0 6px;overflow-wrap:anywhere;font-family:"Cascadia Mono",Consolas,monospace;font-size:12.5px;max-width:420px}
.d-old{background:var(--old-bg);color:var(--old);text-decoration:line-through;text-decoration-color:rgba(138,28,18,.45)}.d-new{background:var(--new-bg);color:var(--new)}
.d-none{color:var(--faint);font-style:italic;font-size:12.5px;white-space:nowrap}
tr.p-high .d-path code{color:var(--high);font-weight:600}
.linkbtn{border:0;background:none;color:var(--accent-strong);font:inherit;font-size:13px;cursor:pointer;padding:0}.linkbtn:hover{text-decoration:underline}
.when-c{white-space:nowrap}.who-c{min-width:170px}
.ev-meta{color:var(--faint);font-size:12px;margin-top:6px;overflow-wrap:anywhere}
table{border-collapse:collapse;width:100%}th,td{text-align:left;vertical-align:top;padding:8px 10px;border-bottom:1px solid var(--line2)}
thead th{font-size:12px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);font-weight:700;background:#F7F9FA;border-bottom:1px solid var(--line)}
td.n,th.n{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}.muted{color:var(--muted)}.small{font-size:12px}.sw{overflow-wrap:break-word}
.tw{overflow-x:auto;background:linear-gradient(90deg,#fff 30%,rgba(255,255,255,0)) left/32px 100% no-repeat local,linear-gradient(270deg,#fff 30%,rgba(255,255,255,0)) right/32px 100% no-repeat local,
radial-gradient(farthest-side at 0 50%,rgba(16,24,40,.18),rgba(16,24,40,0)) left/12px 100% no-repeat scroll,radial-gradient(farthest-side at 100% 50%,rgba(16,24,40,.18),rgba(16,24,40,0)) right/12px 100% no-repeat scroll;background-color:#fff}
.empty{color:var(--muted);background:#F7F9FA;border:1px dashed var(--line);border-radius:10px;padding:14px 16px;font-size:13.5px}.card h3+.empty{margin-top:12px}
.hb{display:grid;grid-template-columns:minmax(150px,1.1fr) 1fr 44px;gap:10px;align-items:center;margin:7px 0;font-size:13px}
.hb .t{background:var(--line2);border-radius:4px;height:10px;overflow:hidden}.hb .t i{display:block;height:100%;background:var(--accent)}.hb b{text-align:right;font-variant-numeric:tabular-nums}
.mx td{text-align:center;font-variant-numeric:tabular-nums}.mx th:first-child,.mx td:first-child{text-align:left}
.mx td.h{background:rgba(14,124,134,var(--a));font-weight:700}
.tl{margin-top:6px}.tl-p,.tl-x{display:grid;grid-template-columns:repeat(var(--n),minmax(0,1fr))}
.tl-p{height:156px;border-bottom:1px solid #B9C3CE}.tl-c{display:flex;flex-direction:column-reverse;padding-top:20px;min-width:0}.tl-c.off{background:var(--off)}
.tl-c i{display:block;flex:none;margin:0 16%}.tl-c b{flex:none;display:flex;justify-content:center;font-size:12px;line-height:16px;margin-bottom:2px;font-weight:600;white-space:nowrap;font-variant-numeric:tabular-nums}
.s-high{background:var(--high-bar)}.s-medium{background:var(--medium-bar)}.s-low{background:#84CAFF}
.tl-x{margin-top:6px;font-size:12px;color:var(--muted);font-variant-numeric:tabular-nums}.tl-x span{white-space:nowrap;border-left:1px solid #C5CED8;padding:1px 0 0 4px;line-height:15px}
.split{display:flex;height:12px;border-radius:4px;overflow:hidden;background:var(--line2);margin:8px 0}
.filters{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:0 0 12px}
.filters input,.filters select{border:1px solid #C5CED8;border-radius:7px;padding:7px 9px;font:inherit;font-size:13px;background:#fff;color:var(--text)}
.filters input{min-width:300px}.filters input::placeholder{color:var(--faint);opacity:1}
.btn{border:1px solid #C5CED8;background:#fff;border-radius:999px;padding:6px 13px;font:inherit;font-size:13px;font-weight:600;cursor:pointer;color:var(--text)}
.btn:hover{background:var(--bg)}.fcount{margin-left:auto;color:var(--muted);font-size:12.5px}
.sb{font:inherit;color:inherit;letter-spacing:inherit;text-transform:inherit;background:none;border:0;padding:0;cursor:pointer;white-space:nowrap}.sb:hover{color:var(--text)}
th[aria-sort] .sb{color:var(--text)}th[aria-sort] .sb:after{content:"";display:inline-block;width:8px;height:5px;margin-left:6px;vertical-align:2px;background:currentColor;clip-path:polygon(0 0,100% 0,50% 100%)}
th[aria-sort=ascending] .sb:after{clip-path:polygon(50% 0,100% 100%,0 100%)}
#tbl{table-layout:fixed;min-width:980px}#tbl td{font-size:13px}.f-hide,.pg{display:none}.brk{overflow-wrap:anywhere}
.st{display:inline-block;border-radius:5px;padding:0 8px;font-size:12px;font-weight:700;line-height:20px;white-space:nowrap}
.st-complete{background:#E3F4E7;color:#0E5A23}.st-partial,.st-skipped{background:#FEF0DC;color:#8A3B00}.st-denied,.st-error{background:#FDE7E7;color:#A4262C}
.st-not_configured,.st-not_needed{background:var(--line2);color:var(--muted)}
.note{background:var(--accent-soft);border:1px solid #C6E6E8;border-radius:8px;padding:10px 13px;font-size:13px;margin-top:12px}
ul.plain{margin:0;padding-left:18px}ul.plain li{margin:3px 0}
footer{background:var(--bar);color:#AEB8C3;font-size:12px;padding:18px 0}footer .wrap{display:flex;justify-content:space-between;gap:16px;flex-wrap:wrap;align-items:center}
@media (max-width:1180px){.kpis{grid-template-columns:repeat(3,1fr)}.ov,.grid2{grid-template-columns:1fr}.grid3{grid-template-columns:1fr 1fr}}
@media screen and (max-width:960px){.hero-in{grid-template-columns:minmax(0,1fr);grid-template-areas:"head" "card" "hl" "meta" "kpis" "sn"}.vcard{margin:2px 0 18px}}
@media screen and (max-width:720px){.wrap{padding:0 16px}h1{font-size:30px}.verdict{font-size:16.5px}.kpis{grid-template-columns:repeat(2,1fr);gap:9px}.kpi b{font-size:26px}
.pills .pill:not(.ro){display:none}.wm small{display:none}.pbtn{padding:0 10px}.pbtn span{display:none}.meta .m-utc,.meta .m-gen{display:none}.meta span{padding:4px 8px;font-size:12px}
.vcard{display:flex;align-items:baseline;flex-wrap:wrap;gap:4px 10px;padding:10px 14px;margin:0 0 16px}.vcard b{font-size:19px;margin:0}.vcard p{display:none}.vcard p+p{display:block;flex-basis:100%}
.kpi{padding:10px 12px}.kpi span{font-size:12.5px;margin-top:3px}
.secnav .wrap{padding-right:40px;-webkit-mask-image:linear-gradient(90deg,#000 calc(100% - 44px),transparent);mask-image:linear-gradient(90deg,#000 calc(100% - 44px),transparent)}
.grid3{grid-template-columns:1fr}.rc-head{flex-direction:column;gap:4px}.rc-where{text-align:left}
.ev{grid-template-columns:1fr;gap:4px;padding:12px 14px}.ev-when b,.ev-when span{display:inline;margin-right:8px}
.card{padding:15px 14px}table.diff,table.diff tbody{display:block}table.diff tr{display:grid;grid-template-columns:fit-content(58%) 18px minmax(0,1fr);align-items:start;border-bottom:1px solid var(--line2)}
table.diff tr[hidden]{display:none}table.diff tr:last-child{border-bottom:0}table.diff td{border:0;padding:3px 8px}table.diff td.d-path,table.diff tr.d-more td{grid-column:1/-1}
.d-path{min-width:0}.d-old,.d-new{max-width:100%}
.filters input,.filters select{min-width:0;flex:1 1 140px}.fcount{margin-left:0;width:100%}
#tbl{min-width:0}#tbl colgroup,#tbl thead{display:none}#tbl,#tbl tbody{display:block;width:100%}#tbl tr{display:flex;flex-wrap:wrap;align-items:center;gap:0 6px;border:1px solid var(--line);border-radius:9px;margin-bottom:9px;padding:8px 4px;background:#fff}
#tbl td{display:block;flex:1 1 100%;border:0;padding:3px 10px}#tbl td:nth-child(1){order:-2;flex:0 0 auto;padding-right:0}#tbl td:nth-child(3){order:-1;flex:0 0 auto;padding:3px 0}#tbl tr.f-hide,#tbl tr.pg{display:none}
.hb{grid-template-columns:1fr 70px 36px}.who-c{min-width:0}.mx th,.mx td{padding:6px 5px}.mx thead th{letter-spacing:0;text-transform:none}
table.stack thead{display:none}table.stack,table.stack tbody,table.stack tr,table.stack td{display:block;width:100%}
table.stack tr{border-bottom:1px solid var(--line);padding:8px 0}table.stack td{border:0;padding:2px 2px;text-align:left!important;white-space:normal}
table.stack td[data-h]:before{content:attr(data-h) ": ";color:var(--muted);font-size:12px}table.stack td:empty{display:none}}
@media (prefers-reduced-motion:reduce){html{scroll-behavior:auto}}
@media print{*{-webkit-print-color-adjust:exact;print-color-adjust:exact}html{scroll-behavior:auto}body{background:#fff;font-size:12px}
.secnav,.filters,.pbtn,.more-row,tr.d-more{display:none!important}.wrap{max-width:none;padding:0}a{color:inherit;text-decoration:none}
.top{background:#fff;color:var(--text);border-bottom:1px solid var(--line)}.top .wrap{min-height:42px;padding:0 2px 6px}.wm small{color:var(--muted)}.pill{border-color:var(--line);color:var(--muted)}.pill.ro{color:var(--accent-strong)}
.hero{border-radius:10px;margin-top:10px;padding:22px 0 20px}.hero .wrap{padding:0 22px}.hero-in{grid-template-columns:minmax(0,1fr) 200px;column-gap:24px}
h1{font-size:28px}.verdict{font-size:15px}.hl li{font-size:12.5px;line-height:1.45;padding:1px 0 1px 18px}.hl li:before{top:8px}.vcard{padding:12px 14px}.vcard b{font-size:18px}.vcard p{font-size:12px}
.meta{margin-bottom:14px}.kpis{grid-template-columns:repeat(6,1fr);gap:8px}.kpi{padding:9px 10px}.kpi b{font-size:22px}.kpi span{font-size:12px}
main{padding:16px 0 0}.sec{margin:0 0 22px}.sec-h,.sec-sub,h2,h3,.card .sub,.rc-head,.rindex{break-after:avoid}
.ev,tr,.kpi,.vcard,.hb,.grid3>.card,.ov>.card,.grid2>.card,.note,.empty{break-inside:avoid}thead{display:table-header-group}
.ov{grid-template-columns:1.5fr 1fr}.tw{overflow:visible!important;background:none}.card{padding:12px 14px}
th,td{padding:5px 7px}#tbl{min-width:0;table-layout:auto}#tbl col{width:auto!important}#tbl td{font-size:12px}#tbl tr.pg{display:table-row}
.ri{padding:2px 8px;font-size:12px}footer{display:none}}
"""

LEVEL_LABEL = {"high": "High", "medium": "Medium", "low": "Low", "noise": "Noise"}
FLAG_LABELS = {"internet-exposed": "Internet-exposed", "exposure increased": "Exposure increased", "after-hours": "After hours",
               "first-time actor on RG": "First-time actor on RG", "burst": "Burst", "click-ops": "Click-ops",
               "click-ops in production": "Click-ops in production"}
STATUS_LABEL = {"complete": "Complete", "partial": "Partial", "denied": "Denied", "error": "Error", "skipped": "Skipped (budget)",
                "not_configured": "Not configured", "not_needed": "Not needed"}
KEY_PATHS = ("access", "direction", "sourceaddressprefix", "destinationportrange", "publicnetworkaccess", "defaultaction",
             "allowsharedkeyaccess", "iprules", "sku.name", "disksizegb", "vmsize", "protocol")
WORDMARK = ('<span class="wm"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9.2 3h5.6l6.2 18h-4.5l-1.5-4.6H8.4L9.9 12h3.8L12 6.6 6.4 21H2z" '
            'fill="#fff"/></svg>Azure SRE Agent<small>Change digest</small></span>')


PRINT_BUTTON = ('<button class="pbtn" type="button" data-print aria-label="Print / PDF" title="Print / PDF"><svg viewBox="0 0 24 24" aria-hidden="true" '
                'fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 9V3h12v6"/>'
                '<path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/><path d="M6 14h12v7H6z"/></svg>'
                '<span>Print / PDF</span></button>')
REPORT_CSP = "default-src 'none'; img-src data:; font-src data:; style-src 'unsafe-inline'; script-src 'unsafe-inline'"
PRIVILEGED_CHIP = ' <span class="flag risk">Privileged</span>'


def esc(value):
    return html.escape(str(value if value is not None else ""), quote=True)


def nw(value):
    """Identifier that never wraps mid-token (GUIDs, resource group names)."""
    return f'<span class="nw">{esc(value)}</span>'


def nw_list(values):
    return ", ".join(nw(v) for v in values)


def ident(value):
    """Actor or principal: GUIDs stay on one line, UPNs may break after '@'."""
    return nw(value) if is_guid(str(value or "")) else esc_id(value)


def short_id(value):
    """GUID shortened like the tool's '(app 1234abcd)' names; the full value stays in the tooltip and the CSV files."""
    return f'<span class="mono nw" title="{esc(value)}">{esc(value[:8])}&hellip;</span>' if is_guid(str(value or "")) else esc(value)


def soft(value):
    """Dotted or slashed identifiers (property paths, resource types) break only at '.', '/' or '['."""
    return re.sub(r"([./])(?=.)", r"\1<wbr>", esc(value)).replace("[", "<wbr>[")


def utc_short(ts_utc):
    return str(ts_utc or "")[:16].replace("T", " ")


def small_note(value):
    return f'<div class="small">{esc(value)}</div>' if value else ""


def nice(value):
    """Sentence-case display text with readable arrows (data keeps ASCII '->')."""
    text_value = str(value or "")
    return esc(text_value[:1].upper() + text_value[1:]).replace(" -&gt; ", " &rarr; ")


def arrows(value):
    return esc(value).replace(" -&gt; ", " &rarr; ")


def esc_id(value):
    """Escape an identity and allow line breaks after '@' and dots instead of mid-word."""
    return esc(value).replace("@", "@<wbr>")


def lvl_chip(level):
    return f'<span class="lvl lvl-{esc(level)}">{LEVEL_LABEL.get(level, esc(level))}</span>'


def flag_chips(flags):
    out = []
    for flag in flags or ():
        cls = " risk" if flag in ("internet-exposed", "exposure increased") else " prod" if flag == "click-ops in production" else ""
        out.append(f'<span class="flag{cls}">{esc(FLAG_LABELS.get(flag, flag))}</span>')
    return "".join(out)


def ct_chip(change_type):
    return f'<span class="ct ct-{esc(change_type.lower())}">{esc(change_type)}</span>'


def status_chip(status):
    return f'<span class="st st-{esc(status)}">{esc(STATUS_LABEL.get(status, status))}</span>'


def short_value(value):
    if re.match(r"(?i)^/subscriptions/[^/]+/", value or "") and value.count("/") > 4:
        parts = value.rstrip("/").split("/")
        return "\u2026/" + "/".join(parts[-2:])
    return value if len(value) <= 160 else value[:157] + "\u2026"


def display_path(path):
    shown = re.sub(r"(?i)^properties\.", "", path)
    return re.sub(r"(?i)\.properties\.", ".", shown)


def when_parts(ts_utc, zone):
    dt = parse_time(ts_utc)
    if not dt:
        return "", "", ""
    local = dt.astimezone(zone)
    return local.strftime("%a %d %b"), local.strftime("%H:%M ") + (local.tzname() or ""), dt.strftime("%H:%M UTC")


def when_inline(ts_utc, zone):
    day, local, utc = when_parts(ts_utc, zone)
    return f'<span class="nw">{esc(day)} {esc(local)}</span> <span class="muted small nw">({esc(utc)})</span>' if day else ""


def when_cell(ts_utc, zone):
    day, local, utc = when_parts(ts_utc, zone)
    return f'{esc(day)} {esc(local)}<div class="muted small">{esc(utc)}</div>' if day else ""


def path_sort_key(p):
    lp = p["path"].lower()
    important = next((i for i, k in enumerate(KEY_PATHS) if lp.endswith(k) or k in lp), len(KEY_PATHS))
    return (-RANK[p["level"]], important, lp)


def render_diff(paths, visible=6):
    if not paths:
        return ""
    rows = []
    for i, p in enumerate(sorted(paths, key=path_sort_key)):
        old = (f'<span class="d-old" title="{esc(p["previous"])}">{esc(short_value(p["previous"])).replace("/", "/<wbr>")}</span>' if p["previous"]
               else '<span class="d-none">not set</span>')
        new = (f'<span class="d-new" title="{esc(p["new"])}">{esc(short_value(p["new"])).replace("/", "/<wbr>")}</span>' if p["new"]
               else '<span class="d-none">removed</span>')
        rows.append(f'<tr class="p-{esc(p["level"])}"{" hidden" if i >= visible else ""}><td class="d-path"><code title="{esc(p["path"])}">'
                    f'{soft(display_path(p["path"]))}</code></td><td>{old}</td><td class="d-arr" aria-label="changed to">&rarr;</td><td>{new}</td></tr>')
    extra = len(rows) - visible
    more = (f'<tr class="d-more"><td colspan="4"><button type="button" class="linkbtn" data-more="{extra}">Show {extra} more '
            f'propert{"y" if extra == 1 else "ies"}</button></td></tr>' if extra > 0 else "")
    return f'<table class="diff" aria-label="Property changes: path, old value, new value"><tbody>{"".join(rows)}{more}</tbody></table>'


def render_event(c, zone):
    day, local, utc = when_parts(c["timestamp_utc"], zone)
    actor = c["actor"]
    who = ident(actor["display_name"])
    raw_id = f' <span class="cls mono">{esc(actor["changed_by"])}</span>' if actor["display_name"] != actor["changed_by"] and actor["changed_by"] not in ("System", "Unspecified") else ""
    reasons = c["reasons"] or ["change"]
    why = f'<b>{nice(reasons[0])}</b>' + (f'<span class="muted"> &middot; {nice("; ".join(reasons[1:3]))}</span>' if len(reasons) > 1 else "")
    meta = [f'Operation {esc(c["operation"]).replace("/", "/<wbr>")}' if c["operation"] and c["operation"] != "Unspecified" else "",
            f'Correlation {esc(c["correlation_id"][:8])}&hellip;' if c["correlation_id"] else "",
            f'{c["noise_paths"]} noise propert{"y" if c["noise_paths"] == 1 else "ies"} hidden' if c["noise_paths"] else ""]
    return (f'<li class="ev"><div class="ev-when"><b>{esc(local)}</b><span>{esc(day)} &middot; {esc(utc)}</span></div><div>'
            f'<div class="ev-line">{ct_chip(c["change_type"])} {lvl_chip(c["level"])}<span class="who">{who}</span>{raw_id}'
            f'<span class="cls">{esc(ACTOR_LABELS.get(actor["actor_class"], actor["actor_class"]))} &middot; {esc(c["client"]["client_type"] or "no client")}</span></div>'
            f'<p class="why">{why}</p>{("<div>" + flag_chips(c["flags"]) + "</div>") if c["flags"] else ""}'
            f'{render_diff(c["paths"])}<div class="ev-meta">{" &middot; ".join(m for m in meta if m)}</div></div></li>')


def render_matters(snapshot, zone):
    floor = RANK[snapshot["parameters"]["min_level"]]
    groups = {}
    for c in snapshot["changes"]:
        if RANK[c["level"]] >= floor:
            groups.setdefault(c["resource_id"].lower() or c["change_id"], []).append(c)
    if not groups:
        return '<div class="empty">No changes at or above the selected level in this window. Lower levels are still counted in the full table and the noise section.</div>'
    cards = sorted(groups.values(), key=lambda g: (-max(RANK[c["level"]] for c in g), -max(parse_time(c["timestamp_utc"]).timestamp() for c in g)))
    subs = {s["id"]: s["name"] for s in snapshot["scope"]["subscriptions"]}
    out, index = [], []
    for n, group in enumerate(cards[:60], 1):
        top = max(group, key=lambda c: RANK[c["level"]])
        level = top["level"]
        name = min(group, key=lambda c: c["timestamp_utc"])["resource_name"]
        rg = top["resource_group"] or "subscription scope"
        prod = '<span class="flag prod">prod</span>' if any(c["prod"] for c in group) else ""
        managed = '<span class="flag">managed RG</span>' if any(c["managed_rg"] for c in group) else ""
        events = "".join(render_event(c, zone) for c in sorted(group, key=lambda c: c["timestamp_utc"]))
        gone = max(group, key=lambda c: c["timestamp_utc"])["change_type"] == "Delete"
        portal = (f' &middot; <a href="https://portal.azure.com/#resource{esc(top["resource_id"])}" target="_blank" rel="noopener">Azure portal</a>'
                  if top["resource_id"].lower().startswith("/subscriptions/") and not gone else "")
        count = f'{len(group)} change{"s" if len(group) != 1 else ""}'
        index.append((level, f'<a class="ri l-{esc(level)}" href="#rc-{n}" title="{esc(top["resource_type_label"])} &middot; {esc(rg)} &middot; {count}">'
                             f'<i></i>{esc(name)}<span>{len(group)}</span></a>'))
        out.append(f'<article class="rc l-{esc(level)}" id="rc-{n}"><div class="rc-head"><div class="rc-id">{lvl_chip(level)}<h3>{esc(name)}</h3>'
                   f'<span class="rc-type">{esc(top["resource_type_label"])}</span></div><div class="rc-where">{nw(rg)}'
                   f' &middot; {esc(subs.get(top["subscription_id"], top["subscription_id"]))} {prod}{managed}<br>{count}{portal}</div></div>'
                   f'<ol class="events" style="list-style:none;margin:0;padding:0">{events}</ol></article>')
    if len(cards) > 60:
        out.append(f'<div class="note">{len(cards) - 60} more resources are listed in the full table and in the CSV files.</div>')
    jump = "".join(f'<span class="k">{LEVEL_LABEL[lv]}</span>' + "".join(h for x, h in index[:16] if x == lv) for lv in ("high", "medium", "low")
                   if any(x == lv for x, _ in index[:16]))
    if len(index) > 16:
        jump += f'<a class="ri more" href="#rc-17">+{len(index) - 16} more below</a>'
    return (f'<nav class="rindex" aria-label="Jump to a resource">{jump}</nav>' if len(cards) > 1 else "") + "".join(out)


def render_deletes(snapshot, zone):
    chains = snapshot["delete_chains"]
    if not chains:
        return '<div class="empty">No resources were deleted in this window.</div>'
    main_chains = [d for d in chains if not (d["managed"] or d["actor_class"] == "platform")]
    platform = [d for d in chains if d not in main_chains]

    def rows(items):
        return "".join(
            f'<tr><td>{lvl_chip(d["level"])}</td><td class="when-c" data-h="When">{when_cell(d["last_utc"], zone)}</td>'
            f'<td data-h="Deleted"><b>{d["deleted"]}</b> &middot; <span class="brk">{esc(", ".join(d["resources"][:6]))}{" &hellip;" if len(d["resources"]) > 6 else ""}</span>'
            f'<div class="small muted">{esc(", ".join(type_label(t) for t in d["resource_types"][:4]))}</div></td>'
            f'<td data-h="Who"><span class="who">{ident(d["actor_display"])}</span><div class="small muted">{esc(ACTOR_LABELS.get(d["actor_class"], ""))} &middot; {esc(d["client_type"] or "no client")}</div></td>'
            f'<td data-h="Resource group">{nw_list(d["resource_groups"][:3])}</td><td class="mono small" data-h="Correlation">{esc(d["correlation_id"][:8])}</td></tr>' for d in items)

    head = '<thead><tr><th>Level</th><th>When</th><th>Deleted</th><th>Who</th><th>Resource group</th><th>Correlation</th></tr></thead>'
    html_out = (f'<div class="card tw"><table class="stack">{head}<tbody>{rows(main_chains)}</tbody></table></div>' if main_chains
                else '<div class="empty">No deletes by people or automation; only platform-managed deletes below.</div>')
    if platform:
        total = sum(d["deleted"] for d in platform)
        html_out += (f'<details class="more card" style="margin-top:12px;padding:6px 10px"><summary>{total} platform-managed delete{"s" if total != 1 else ""} '
                     f'in {len(platform)} operation{"s" if len(platform) != 1 else ""} (managed resource groups and Azure services), summarized</summary>'
                     f'<div class="tw"><table class="stack">{head}<tbody>{rows(platform)}</tbody></table></div></details>')
    return html_out


def render_security(snapshot, zone):
    sec = sorted([c for c in snapshot["changes"] if c["security"]], key=lambda c: c["timestamp_utc"], reverse=True)
    sec.sort(key=lambda c: -RANK[c["level"]])
    sec_rows = "".join(
        f'<tr><td>{lvl_chip(c["level"])}</td><td><b class="brk">{esc(c["resource_name"])}</b><div class="small muted">{esc(c["resource_type_label"])} &middot; {nw(c["resource_group"])}</div></td>'
        f'<td>{ct_chip(c["change_type"])} {nice("; ".join(c["reasons"][:2]))}<div>{flag_chips([f for f in c["flags"] if f in ("internet-exposed", "exposure increased")])}</div></td>'
        f'<td class="who-c" data-h="Who">{ident(c["actor"]["display_name"])}</td><td class="when-c" data-h="When">{when_cell(c["timestamp_utc"], zone)}</td></tr>' for c in sec)
    part1 = (f'<div class="tw"><table class="stack"><thead><tr><th>Level</th><th>Resource</th><th>What changed</th><th>Who</th><th>When</th></tr></thead><tbody>{sec_rows}</tbody></table></div>'
             if sec else '<div class="empty">No exposure, network rule, Key Vault, identity or encryption changes in this window.</div>')
    ras = snapshot["role_assignments"]
    ra_rows = "".join(
        f'<tr><td>{lvl_chip(r["level"])}</td><td><b>{esc(r["role_name"])}</b>{PRIVILEGED_CHIP if r["privileged"] else ""}'
        f'<div class="small muted">{esc(r["kind"])}</div></td><td class="brk" data-h="Scope">{esc(r["scope_label"])}</td>'
        f'<td data-h="Principal">{ident(r["principal_display"] or r["principal_id"])}<div class="small muted">{esc(r["principal_type"])}</div></td>'
        f'<td class="who-c" data-h="Created by">{ident(r["created_by"])}</td><td class="when-c" data-h="When">{when_cell(r["created_utc"], zone)}</td></tr>' for r in ras)
    part2 = (f'<div class="tw"><table class="stack"><thead><tr><th>Level</th><th>Role</th><th>Scope</th><th>Principal</th><th>Created by</th><th>When</th></tr></thead><tbody>{ra_rows}</tbody></table></div>'
             if ras else '<div class="empty">No new or updated role assignments in this window.</div>')
    gaps = snapshot["activity_log_gaps"] + snapshot["failed_attempts"]
    gap_rows = "".join(
        f'<tr{" class=muted" if g["status"] == "Failed" else ""}><td>{lvl_chip(g["level"])}</td><td><b>{esc(g["label"])}</b>'
        f'{small_note(g.get("error_code"))}</td>'
        f'<td class="brk" data-h="Target">{esc(g["resource_name"])}<div class="small muted">on {nw(g["target"])}</div></td><td class="who-c" data-h="Caller">{ident(g["caller"])}</td>'
        f'<td class="when-c" data-h="When">{when_cell(g["time_utc"], zone)}</td></tr>' for g in gaps)
    al_status = snapshot["coverage"]["activity_log"]
    part3 = (f'<div class="tw"><table class="stack"><thead><tr><th>Level</th><th>Event</th><th>Target</th><th>Caller</th><th>When</th></tr></thead><tbody>{gap_rows}</tbody></table></div>'
             if gaps else f'<div class="empty">{"No lock, role assignment delete, diagnostic setting or policy assignment events." if al_status in ("complete", "partial") else "Activity Log gap reader " + esc(STATUS_LABEL.get(al_status, al_status)).lower() + "."}</div>')
    return (f'<div class="card" style="margin-bottom:16px"><h3>Exposure, network and security settings</h3><p class="sub">Public access, firewall and NSG rules, '
            f'Key Vault, identity and encryption changes recorded by Change Analysis.</p>{part1}</div>'
            f'<div class="card" style="margin-bottom:16px"><h3>New role assignments</h3><p class="sub">From authorizationresources (role assignments are not in resourcechanges). '
            f'Owner, User Access Administrator, Contributor and RBAC Administrator are privileged.</p>{part2}</div>'
            f'<div class="card"><h3>Activity Log gap events</h3><p class="sub">Changes Change Analysis does not record: role assignment deletes, locks, '
            f'diagnostic settings and policy assignments. Failed attempts are shown muted.</p>{part3}</div>')


def render_actors(snapshot):
    actors = snapshot["actors"]
    if not actors:
        return '<div class="empty">No non-noise changes, so no actors to show.</div>'
    rows = "".join(
        f'<tr><td><b>{ident(a["display_name"])}</b>'
        f'{("<div class=small>" + ident(a["changed_by"]) + "</div>") if a["display_name"] != a["changed_by"] and a["changed_by"] not in ("System", "Unspecified") else ""}'
        f'<div class="small muted">{esc(a["changed_by_type"])} &middot; resolved by {esc(NAME_RESOLUTION.get(a["resolution"], a["resolution"]))}</div></td>'
        f'<td data-h="Class">{esc(ACTOR_LABELS.get(a["actor_class"], a["actor_class"]))}</td><td class="n" data-h="Changes"><b>{a["changes"]}</b></td>'
        f'<td class="n" data-h="Create / update / delete">{a["creates"]} / {a["updates"]} / {a["deletes"]}</td><td class="n" data-h="High / medium">{a["high"]} / {a["medium"]}</td>'
        f'<td data-h="Resource groups">{nw_list(a["resource_groups"][:4])}{" &hellip;" if a["resource_group_count"] > 4 else ""}</td>'
        f'<td data-h="Clients">{", ".join(short_id(x) for x in a["clients"])}</td></tr>' for a in actors[:60])
    return (f'<div class="card tw"><table class="stack"><thead><tr><th>Actor</th><th>Class</th><th class="n">Changes</th><th class="n">Create / Update / Delete</th>'
            f'<th class="n">High / Medium</th><th>Resource groups</th><th>Clients</th></tr></thead><tbody>{rows}</tbody></table>'
            f'<div class="note">Attribution comes from Change Analysis (<code>changedBy</code>, <code>changedByType</code>, <code>clientType</code>). '
            f'A single field never proves intent: check the operation and correlation ID before drawing conclusions.</div></div>')


def render_clickops(snapshot, zone):
    matrix = snapshot["client_matrix"]
    if not matrix:
        return '<div class="empty">No non-noise changes in this window.</div>'
    clients = [k for k in CLIENT_LABELS if any(m["client_class"] == k for m in matrix)]
    actors = [k for k in ACTOR_LABELS if any(m["actor_class"] == k for m in matrix)]
    cell = {(m["client_class"], m["actor_class"]): m["changes"] for m in matrix}
    peak = max(cell.values()) or 1
    body = ""
    for c in clients:
        tds = ""
        for a in actors:
            n = cell.get((c, a), 0)
            tds += (f'<td class="h" style="--a:{0.08 + 0.5 * n / peak:.2f}">{n}</td>' if n else '<td class="muted">&middot;</td>')
        body += f'<tr><td><b>{esc(CLIENT_LABELS[c])}</b></td>{tds}<td class="n"><b>{sum(cell.get((c, a), 0) for a in actors)}</b></td></tr>'
    head = "".join(f"<th>{esc(ACTOR_LABELS[a])}</th>" for a in actors)
    manual = [c for c in snapshot["changes"] if "click-ops" in c["flags"]]
    manual_rows = "".join(
        f'<li>{lvl_chip(c["level"])} {flag_chips(["click-ops in production"] if c["prod"] else [])} <b>{esc(c["resource_name"])}</b> '
        f'<span class="muted">{esc(c["change_type"])} by {esc(c["actor"]["display_name"])} &middot; {when_inline(c["timestamp_utc"], zone)}</span></li>'
        for c in manual[:30])
    manual_html = (f'<ul class="plain">{manual_rows}</ul>' if manual else
                   '<div class="empty">No manual portal or browser changes by people in this window.</div>')
    return (f'<div class="grid2"><div class="card"><h3>Client &times; actor</h3><p class="sub">How non-noise changes were made. Terraform also uses the '
            f'Go SDK and pipelines often run the CLI, so IaC is a best-effort label.</p><div class="tw"><table class="mx"><thead><tr><th>Client</th>{head}'
            f'<th class="n">Total</th></tr></thead><tbody>{body}</tbody></table></div></div>'
            f'<div class="card"><h3>Manual portal changes by people</h3><p class="sub">Click-ops bypasses IaC review. Changes in resource groups, subscriptions '
            f'or resources tagged as production are highlighted.</p>{manual_html}</div></div>')


def render_unusual(snapshot, zone):
    changes = {c["change_id"]: c for c in snapshot["changes"]}
    after = [changes[i] for i in snapshot["unusual"]["after_hours"] if i in changes]
    hours = snapshot["window"]["business_hours"]
    after_html = "".join(f'<li>{lvl_chip(c["level"])} <b>{esc(c["resource_name"])}</b> <span class="muted">{esc(c["change_type"])} by '
                         f'{ident(c["actor"]["display_name"])} &middot; {when_inline(c["timestamp_utc"], zone)}</span></li>' for c in after[:25])
    first_html = "".join(f'<li><b>{ident(f["actor"])}</b> <span class="muted">on {nw(f["resource_group"])} &middot; {f["changes"]} '
                         f'non-noise change{"s" if f["changes"] != 1 else ""} &middot; first seen {when_inline(f["first_utc"], zone)}</span></li>'
                         for f in snapshot["unusual"]["first_time_actor_rg"][:25])
    burst_html = "".join(f'<li><b>{ident(b["actor"])}</b> <span class="muted">{b["changes"]} changes, {b["deletes"]} delete{"s" if b["deletes"] != 1 else ""} &middot; '
                         f'{when_inline(b["start_utc"], zone)}</span></li>' for b in snapshot["unusual"]["bursts"][:25])
    baseline_note = ("Not computed for last_14d: the window equals the 14-day retention." if snapshot["window"]["period"] == "last_14d"
                     else "None in this window.")

    def box(title, sub, count, body, empty):
        return (f'<div class="card"><h3>{esc(title)} <span class="sec-n">{count}</span></h3><p class="sub">{esc(sub)}</p>'
                f'{("<ul class=plain>" + body + "</ul>") if body else "<div class=empty>" + esc(empty) + "</div>"}</div>')

    return ('<div class="grid3">' +
            box("After hours or weekend", f"Human changes outside {hours[0]:02d}:00-{hours[1]:02d}:00 {snapshot['window']['timezone']} on business days.",
                len(after), after_html, "None in this window.") +
            box("First-time actor on a resource group", "Actor not seen on that resource group earlier in the 14-day baseline.",
                len(snapshot["unusual"]["first_time_actor_rg"]), first_html, baseline_note) +
            box("Bursts", "10 or more changes, or 5 or more deletes, by one actor within 15 minutes.", len(snapshot["unusual"]["bursts"]),
                burst_html, "None in this window.") + "</div>")


def render_noise(snapshot):
    noise, counts = snapshot["noise"], snapshot["counts"]
    peak = max(noise["by_reason"].values() or [1]) or 1
    reasons = "".join(f'<div class="hb"><span>{nice(r)}</span><span class="t"><i style="width:{max(3, 100 * n / peak):.0f}%"></i></span><b>{n}</b></div>'
                      for r, n in noise["by_reason"].items() if n)
    by_type = "".join(f'<tr><td>{esc(t["label"])}<div class="small muted mono sw">{soft(t["resource_type"])}</div></td><td class="n">{t["changes"]}</td></tr>'
                      for t in noise["top_types"])
    paths = "".join(f'<tr><td class="mono sw">{soft(p["path_pattern"])}</td><td class="n">{p["occurrences"]}</td></tr>' for p in noise["top_paths"][:12])
    low = "".join(f'<tr><td class="n"><b>{g["count"]}&times;</b></td><td>{nice(g["reason"])}<div class="small muted mono sw">{soft(", ".join(g["paths"]))}</div></td>'
                  f'<td data-h="Resource type">{esc(g["type_label"])} <span class="muted">({g["resources"]} resource{"s" if g["resources"] != 1 else ""})</span></td>'
                  f'<td data-h="Actor">{ident(g["actor"])}</td></tr>' for g in noise["low_summaries"])
    actor_types = ", ".join(f"{k} {v}" for k, v in noise["by_changed_by_type"].items())
    return (f'<div class="grid2"><div class="card"><h3>{noise["total"]} changes filtered as noise ({counts["noise_filtered_pct"]}% of {counts["total"]})</h3>'
            f'<p class="sub">Updates whose changed properties are all platform metadata, timestamps or agent-reported inventory. Counted, never listed. '
            f'By changedByType: {esc(actor_types or "none")}. {noise["managed_rg_changes"]} changes happened inside platform-managed resource groups.</p>'
            f'{reasons or "<div class=empty>No noise in this window.</div>"}'
            f'<h3 style="margin-top:16px">Noisiest resource types</h3><div class="tw"><table><tbody>{by_type}</tbody></table></div></div>'
            f'<div class="card"><h3>Top noise property paths</h3><p class="sub">Array indexes normalized to [*]; count of noise-only changes containing the path.</p>'
            f'<div class="tw"><table><thead><tr><th>Path pattern</th><th class="n">Changes</th></tr></thead><tbody>{paths}</tbody></table></div></div></div>'
            + (f'<div class="card" style="margin-top:16px"><h3>Low-level changes, summarized</h3><p class="sub">Repetitive low changes collapsed as '
               f'&ldquo;N&times; same change on M resources&rdquo;. Every row is still in the full table and the CSV.</p><div class="tw"><table class="stack"><thead><tr>'
               f'<th class="n">Count</th><th>Reason and paths</th><th>Resource type</th><th>Actor</th></tr></thead><tbody>{low}</tbody></table></div></div>' if low else ""))


def render_timeline(snapshot, zone):
    buckets = snapshot["timeline"]["buckets"]
    if not buckets:
        return ""
    hours, days, step = snapshot["window"]["business_hours"], snapshot["window"]["business_days"], snapshot["timeline"]["step_hours"]
    totals = [b["high"] + b["medium"] + b["low"] for b in buckets]
    peak = max(totals + [1])
    starts = [parse_time(b["start_utc"]).astimezone(zone) for b in buckets]
    if step == 1:
        marks = [(i, b["label"]) for i, b in enumerate(buckets)][::max(1, len(buckets) // 8)]
    else:
        days_at = [i for i in range(1, len(buckets)) if starts[i].date() != starts[i - 1].date()]
        marks = [(i, starts[i].strftime("%d %b")) for i in days_at][::max(1, -(-len(days_at) // 8))]
    cols, shaded = [], False
    for i, b in enumerate(buckets):
        off = step == 1 and (starts[i].weekday() not in days or not hours[0] <= starts[i].hour < hours[1])
        shaded = shaded or off
        segs = "".join(f'<i class="s-{lv}" style="height:{100 * b[lv] / peak:.1f}%"></i>' for lv in ("low", "medium", "high") if b[lv])
        tip = ", ".join(f'{b[lv]} {lv}' for lv in ("high", "medium", "low") if b[lv]) or "no changes"
        cols.append(f'<div class="tl-c{" off" if off else ""}" title="{esc(b["label"])}: {tip}">{segs}{("<b>" + str(totals[i]) + "</b>") if totals[i] else ""}</div>')
    ticks = [f'<span style="grid-column:{i + 1}/{(marks[k + 1][0] if k + 1 < len(marks) else len(buckets)) + 1}">{esc(label)}</span>'
             for k, (i, label) in enumerate(marks)]
    unit = "hour" if step == 1 else f"{step} hours"
    top = totals.index(max(totals))
    summary = (f"Non-noise changes per {unit}, local time: {sum(totals)} in total, at most {totals[top]} at {buckets[top]['label']}."
               if any(totals) else f"No non-noise changes per {unit} in this window.")
    legend = "".join(f'<span><i class="s-{lv}"></i>{LEVEL_LABEL[lv]}</span>' for lv in ("high", "medium", "low"))
    legend += '<span><i class="b-off"></i>Outside business hours</span>' if shaded else ""
    return (f'<div class="card chart"><h3>Non-noise changes over the window</h3><p class="sub">Per {unit}, local time ({esc(snapshot["window"]["timezone"])}). '
            f'Numbers are changes per bar.</p><div class="tl" role="img" aria-label="{esc(summary)}" '
            f'style="--n:{len(buckets)}"><div class="tl-p">{"".join(cols)}</div><div class="tl-x">{"".join(ticks)}</div></div>'
            f'<div class="legend">{legend}</div></div>')


def render_split(snapshot):
    by_actor, by_client = snapshot["counts"]["by_actor_class"], snapshot["counts"]["by_client_class"]
    total = sum(by_actor.values())
    if not total:
        return '<div class="card"><h3>Who and how</h3><div class="empty">No non-noise changes in this window.</div></div>'
    colors = {"human": "#0E7C86", "automation": "#5B7FD1", "expected-automation": "#8BA6E3", "platform": "#A9B6C3", "unknown": "#D5DBE2"}
    bar = "".join(f'<i style="width:{100 * n / total:.1f}%;background:{colors.get(k, "#ccc")}" title="{esc(ACTOR_LABELS.get(k, k))}: {n}"></i>'
                  for k, n in by_actor.items()) if total else ""
    legend = "".join(f'<span><i style="background:{colors.get(k, "#ccc")}"></i>{esc(ACTOR_LABELS.get(k, k))} <b>{n}</b></span>' for k, n in by_actor.items())
    clients = "".join(f'<div class="hb"><span>{esc(CLIENT_LABELS.get(k, k))}</span><span class="t"><i style="width:{100 * n / max(by_client.values()):.0f}%"></i></span><b>{n}</b></div>'
                      for k, n in by_client.items())
    return (f'<div class="card"><h3>Who and how</h3><p class="sub">{total} non-noise changes by actor class and client.</p>'
            f'<div class="split">{bar}</div><div class="legend" style="color:var(--muted)">{legend}</div><div style="margin-top:12px">{clients}</div></div>')


def render_table(snapshot, zone):
    changes = snapshot["changes"][:MAX_TABLE_ROWS]
    floor = RANK[snapshot["parameters"]["min_level"]]
    rgs = sorted({c["resource_group"] for c in changes if c["resource_group"]}, key=str.lower)
    rows = []
    for c in changes:
        day, local, utc = when_parts(c["timestamp_utc"], zone)
        hidden = " f-hide" if RANK[c["level"]] < floor else ""
        search = " ".join([c["resource_name"], c["resource_group"], c["resource_type"], c["actor"]["display_name"], c["actor"]["changed_by"],
                           c["client"]["client_type"], " ".join(c["reasons"]), " ".join(c["flags"]), c["operation"]]).lower()
        rows.append(
            f'<tr class="r-{c["level"]}{hidden}" data-level="{c["level"]}" data-rank="{RANK[c["level"]]}" data-type="{esc(c["change_type"])}" '
            f'data-actor="{esc(c["actor"]["actor_class"])}" data-rg="{esc(c["resource_group"].lower())}" data-t="{esc(c["timestamp_utc"])}" '
            f'data-q="{esc(search)}"><td>{lvl_chip(c["level"])}</td><td class="n" style="text-align:left"><b>{esc(local)}</b>'
            f'<div class="small muted">{esc(day)} &middot; {esc(utc)}</div></td><td>{ct_chip(c["change_type"])}</td>'
            f'<td><b class="brk">{esc(c["resource_name"])}</b><div class="small muted">{esc(c["resource_type_label"])}</div></td>'
            f'<td class="brk">{esc(c["resource_group"]).replace("_", "_<wbr>")}</td><td><span class="who">{ident(c["actor"]["display_name"])}</span>'
            f'<div class="small muted">{esc(ACTOR_LABELS.get(c["actor"]["actor_class"], ""))} &middot; {esc(c["client"]["client_type"] or "no client")}</div></td>'
            f'<td>{nice("; ".join(c["reasons"][:2]))}<div>{flag_chips(c["flags"])}</div></td></tr>')
    if not rows:
        return '<div class="empty">No non-noise changes in this window.</div>'
    level_opts = "".join(f'<option value="{k}"{" selected" if RANK[k] == floor else ""}>{label}</option>'
                         for k, label in (("high", "High"), ("medium", "High and medium"), ("low", "All levels")))
    rg_opts = "".join(f'<option value="{esc(r.lower())}">{esc(r)}</option>' for r in rgs)
    actor_opts = "".join(f'<option value="{k}">{esc(v)}</option>' for k, v in ACTOR_LABELS.items())
    cap = (f'<div class="note">Showing the newest {MAX_TABLE_ROWS} of {len(snapshot["changes"])} changes; the CSV files contain every change.</div>'
           if len(snapshot["changes"]) > MAX_TABLE_ROWS else "")
    heads = "".join((f'<th data-k="{k}"' + (' aria-sort="descending"' if k == "t" else "") + f'><button type="button" class="sb">{label}</button></th>') if k
                    else f'<th>{label}</th>' for k, label in (("rank", "Level"), ("t", "When"), ("type", "Change"), ("", "Resource"),
                                                             ("rg", "Resource group"), ("actor", "Who and how"), ("", "Why")))
    return (f'<div class="card" id="reg" data-file="change-digest-{esc(snapshot["window"]["end_utc"][:10])}-changes-view"><div class="filters">'
            f'<input id="fq" type="search" placeholder="Search resource, actor, reason or operation" aria-label="Search">'
            f'<select id="fl" aria-label="Level">{level_opts}</select><select id="ft" aria-label="Change type"><option value="">All change types</option>'
            f'<option>Create</option><option>Update</option><option>Delete</option></select><select id="fa" aria-label="Actor class">'
            f'<option value="">All actors</option>{actor_opts}</select><select id="fr" aria-label="Resource group"><option value="">All resource groups</option>'
            f'{rg_opts}</select><button class="btn" id="fx" type="button">Clear</button><button class="btn" id="fe" type="button">Export CSV</button>'
            f'<span class="fcount" id="fc" aria-live="polite"></span></div>'
            f'<div class="tw"><table id="tbl"><colgroup><col style="width:86px"><col style="width:140px"><col style="width:78px"><col style="width:17%">'
            f'<col style="width:14%"><col style="width:22%"><col></colgroup><thead><tr>{heads}</tr></thead><tbody id="tb">{"".join(rows)}</tbody></table></div>'
            f'<div class="more-row" style="text-align:center;margin-top:12px"><button class="btn" id="fm" type="button">Show more</button></div>{cap}</div>')


def render_coverage(snapshot):
    cov = snapshot["coverage"]
    rows = "".join(
        f'<tr><td><b>{esc(s["label"])}</b><div class="small muted mono">{esc(s["id"])}{" (optional)" if s.get("optional") else ""}</div></td>'
        f'<td>{status_chip(s["status"])}</td><td class="n" data-h="Pages">{s["pages"]}</td><td class="n" data-h="Records">{s["records"]}</td><td class="n" data-h="Seconds">{s["seconds"]:.1f}</td>'
        f'<td class="brk small">{esc(s["errors"][0]["message"] if s["errors"] else s["notes"])}</td></tr>' for s in cov["sources"])
    gaps = {"data-plane": "Data-plane writes (for example blobs, secrets or table rows).",
            "app-service-files": "App Service file and app configuration changes.",
            "rbac-deletes-without-activity-log": "Role assignment deletes (only seen through the Activity Log reader).",
            "locks": "Resource locks (Activity Log reader only).", "diagnostic-settings": "Diagnostic settings (Activity Log reader only).",
            "policy": "Policy assignments and exemptions (Activity Log reader only)."}
    not_covered = "".join(f"<li>{esc(gaps.get(k, k))}</li>" for k in cov["not_covered"])
    links = "".join(f'<li><a href="{esc(u)}" rel="noopener" target="_blank">{esc(u.replace("https://learn.microsoft.com/azure/", "learn.microsoft.com/…/"))}</a></li>'
                    for u in snapshot["sources"])
    identity = "; ".join(f"{k.upper()}: {v}" for k, v in cov["identity_check"].items()) or "n/a"
    w = snapshot["window"]
    return (f'<div class="card tw"><table class="stack"><thead><tr><th>Source</th><th>Status</th><th class="n">Pages</th><th class="n">Records</th>'
            f'<th class="n">Seconds</th><th>Notes</th></tr></thead><tbody>{rows}</tbody></table></div>'
            f'<div class="grid2" style="margin-top:16px"><div class="card"><h3>Not covered by Change Analysis</h3><p class="sub">Absence of a change below is not '
            f'proof that nothing happened.</p><ul class="plain">{not_covered}</ul><div class="note">Retention is {cov["retention_days"]} days. '
            f'{esc(cov["latency_note"])} Anything that could not be read is a blind spot, never a clean result.</div></div>'
            f'<div class="card"><h3>About this digest</h3><ul class="plain"><li>Window {nw(w["start_local"])} to {nw(w["end_local"])} '
            f'({nw(w["start_utc"])} to {nw(w["end_utc"])}); time zone {esc(w["timezone"])} via {esc(w["timezone_source"])}.</li>'
            f'<li>Business hours {w["business_hours"][0]:02d}:00-{w["business_hours"][1]:02d}:00, days {esc(", ".join("Mon Tue Wed Thu Fri Sat Sun".split()[d] for d in w["business_days"]))}.</li>'
            f'<li>{cov["http_requests"]} read-only HTTP requests in {cov["collection_seconds"]} s; {cov["throttled_waits"]} throttling waits.</li>'
            f'<li>Identity check: {esc(identity)}.</li><li>{cov["managed_resource_groups"]} platform-managed and {cov["prod_resource_groups"]} production-tagged resource groups.</li>'
            f'<li>Graph names: {esc(STATUS_LABEL.get(cov["graph"], cov["graph"]))}. Activity Log: {esc(STATUS_LABEL.get(cov["activity_log"], cov["activity_log"]))}.</li></ul>'
            f'<h3 style="margin-top:14px">Microsoft Learn</h3><ul class="plain small">{links}</ul></div></div>')


REPORT_JS = """
(function(){var $=function(i){return document.getElementById(i)},each=function(s,f){[].forEach.call(document.querySelectorAll(s),f)},tb=$('tb');
each('[data-print]',function(b){b.addEventListener('click',function(){window.print()})});
var navs=[].slice.call(document.querySelectorAll('.secnav a')),strip=document.querySelector('.secnav .wrap');
if('IntersectionObserver' in window){var io=new IntersectionObserver(function(es){es.forEach(function(e){if(!e.isIntersecting)return;navs.forEach(function(a){var on=a.getAttribute('href')==='#'+e.target.id;a.classList.toggle('on',on);
if(on&&strip.scrollWidth>strip.clientWidth)strip.scrollLeft+=a.getBoundingClientRect().left-strip.getBoundingClientRect().left-24})})},{rootMargin:'-45% 0px -50% 0px'});each('section.sec[id]',function(s){io.observe(s)})}
function tws(){each('.tw',function(w){var o=w.scrollWidth>w.clientWidth+1;if(o&&!w.hasAttribute('tabindex')){var c=w.closest('.card'),h=(c&&c.querySelector('h3'))||(w.closest('section')||document).querySelector('h2');
w.tabIndex=0;w.setAttribute('role','region');w.setAttribute('aria-label',(h?h.textContent:'Table')+', scrolls sideways')}else if(!o&&w.hasAttribute('tabindex')){w.removeAttribute('tabindex');w.removeAttribute('role');w.removeAttribute('aria-label')}})}
tws();var rt;window.addEventListener('resize',function(){clearTimeout(rt);rt=setTimeout(tws,200)});
window.addEventListener('beforeprint',function(){each('details',function(d){d.open=true});each('table.diff tr[hidden]',function(r){r.hidden=false})});
each('.linkbtn[data-more]',function(b){b.addEventListener('click',function(){var t=b.closest('tbody');[].forEach.call(t.querySelectorAll('tr[hidden]'),function(r){r.hidden=false});b.closest('tr').remove()})});
if(!tb)return;var rows=[].slice.call(tb.rows),PAGE=40,limit=PAGE,key='t',asc=false,rank={high:3,medium:2,low:1};
function vis(){var q=$('fq').value.toLowerCase(),l=rank[$('fl').value]||1,t=$('ft').value,a=$('fa').value,g=$('fr').value;
return rows.filter(function(r){var d=r.dataset;return +d.rank>=l&&(!t||d.type===t)&&(!a||d.actor===a)&&(!g||d.rg===g)&&(!q||d.q.indexOf(q)>=0)})}
function val(r){var d=r.dataset;return key==='rank'?+d.rank:(d[key]||'')}
function draw(){var v=vis();v.sort(function(x,y){var a=val(x),b=val(y);return a<b?(asc?-1:1):a>b?(asc?1:-1):0});
rows.forEach(function(r){r.classList.add('f-hide');r.classList.remove('pg')});v.forEach(function(r,i){tb.appendChild(r);r.classList.remove('f-hide');if(i>=limit)r.classList.add('pg')});
$('fc').textContent=Math.min(limit,v.length)+' of '+v.length+' matching changes ('+rows.length+' non-noise in total)';
$('fm').parentNode.style.display=v.length>limit?'':'none';
each('#tbl th[data-k]',function(th){if(th.dataset.k===key)th.setAttribute('aria-sort',asc?'ascending':'descending');else th.removeAttribute('aria-sort')})}
['fq','fl','ft','fa','fr'].forEach(function(i){$(i).addEventListener('input',function(){limit=PAGE;draw()})});
$('fm').addEventListener('click',function(){limit+=PAGE;draw()});
var saved,fs=['fq','fl','ft','fa','fr'];window.addEventListener('beforeprint',function(){saved=fs.map(function(i){return $(i).value}).concat(limit);fs.forEach(function(i){$(i).value=''});$('fl').value='low';limit=rows.length;draw()});
window.addEventListener('afterprint',function(){if(!saved)return;fs.forEach(function(i,k){$(i).value=saved[k]});limit=saved[5];saved=null;draw()});
$('fx').addEventListener('click',function(){$('fq').value='';$('ft').value='';$('fa').value='';$('fr').value='';$('fl').value='low';limit=PAGE;draw()});
each('#tbl th[data-k] .sb',function(b){b.addEventListener('click',function(){var k=b.parentNode.dataset.k;if(key===k)asc=!asc;else{key=k;asc=k!=='t'&&k!=='rank'}draw()})});
$('fe').addEventListener('click',function(){var tx=function(e){return e?e.textContent:''},q=function(s){s=String(s).replace(/\\s+/g,' ').trim();if(/^[=+\\-@]/.test(s))s="'"+s;return '"'+s.replace(/"/g,'""')+'"'};
var out=[['Level','When (UTC)','Change','Resource','Resource type','Resource group','Who','Actor class and client','Why','Flags'].map(q).join(',')];
[].forEach.call(tb.rows,function(r){if(r.classList.contains('f-hide'))return;var c=r.cells,w=c[6].cloneNode(true),f=w.querySelector('div'),fl=f?[].map.call(f.querySelectorAll('.flag'),tx).join('; '):'';if(f)f.remove();
out.push([r.dataset.level,r.dataset.t,r.dataset.type,tx(c[3].querySelector('b')),tx(c[3].querySelector('div')),tx(c[4]),tx(c[5].querySelector('.who')),tx(c[5].querySelector('div')),tx(w),fl].map(q).join(','))});
var a=document.createElement('a');a.href=URL.createObjectURL(new Blob(['\\ufeff'+out.join('\\r\\n')],{type:'text/csv;charset=utf-8'}));a.download=$('reg').getAttribute('data-file')+'.csv';
document.body.appendChild(a);a.click();setTimeout(function(){URL.revokeObjectURL(a.href);a.remove()},2000)});
draw()})();
"""


def css_text(value):
    return '"' + re.sub(r'[<>"\\\r\n]', " ", str(value)) + '"'


def verdict_card(snapshot):
    counts, lv = snapshot["counts"], snapshot["counts"]["by_level"]
    extra = counts["new_role_assignments"] + counts["activity_log_gaps"]
    levels = {i["level"] for i in snapshot["items"]}
    core_failed = any(s["id"] == "arg_resourcechanges" and s["status"] in ("denied", "error", "skipped") for s in snapshot["coverage"]["sources"])
    if core_failed:
        tone, word, detail = "warn", "Incomplete data", "Change Analysis could not be read completely; see Coverage."
    elif levels & {"high", "medium"}:
        tone, word = ("high", "Needs attention") if "high" in levels else ("review", "Review recommended")
        detail = f'{lv["high"]} high &middot; {lv["medium"]} medium changes' + (f' &middot; {extra} RBAC and Activity Log event{"s" if extra != 1 else ""}' if extra else "")
    else:
        tone, word, detail = "ok", "No relevant changes", f'{counts["noise_filtered_pct"]}% of {counts["total"]} changes were platform noise.'
    partial = "<p>Partial coverage: some sources are blind spots.</p>" if snapshot["status"] != "ok" and not core_failed else ""
    return f'<aside class="vcard v-{tone}" aria-label="Verdict"><div class="k">Verdict</div><b>{word}</b><p>{detail}</p>{partial}</aside>'


def render_html(snapshot):
    zone = business_zone(snapshot["window"]["timezone"])[0] if snapshot["window"]["timezone"] != "UTC" else timezone.utc
    counts, w, head = snapshot["counts"], snapshot["window"], snapshot["headline"]
    total = counts["total"] or 1
    lv = counts["by_level"]
    bar = "".join(f'<i class="b-{k}" style="width:{100 * lv[k] / total:.2f}%" title="{LEVEL_LABEL[k]}: {lv[k]}"></i>' for k in ("high", "medium", "low", "noise") if lv[k])
    legend = "".join(f'<span><i class="b-{k}"></i>{LEVEL_LABEL[k]} <b>{lv[k]}</b></span>' for k in ("high", "medium", "low", "noise"))
    unusual = counts["unusual"]
    unusual_total = unusual["after_hours"] + unusual["first_time_actor_rg"] + unusual["bursts"] + unusual["click_ops"]
    security_total = counts["security"] + counts["new_role_assignments"] + counts["updated_role_assignments"] + counts["activity_log_gaps"]
    kpis = [(counts["reported"], f'relevant changes &middot; {lv["high"]} high, {lv["medium"]} medium'),
            (counts["deletes"], f'deleted resources in {counts["delete_operations"]} operation{"s" if counts["delete_operations"] != 1 else ""}'),
            (security_total, "security-relevant changes and events"),
            (counts["new_role_assignments"], f'new role assignments &middot; {counts["privileged_role_assignments"]} privileged'),
            (unusual_total, "unusual activity flags"),
            (f'{counts["noise_filtered_pct"]}%', f'filtered as noise ({lv["noise"]} of {counts["total"]})')]
    kpi_html = "".join(f'<div class="kpi"><b>{v}</b><span>{label}</span></div>' for v, label in kpis)
    subs = ", ".join(s["name"] for s in snapshot["scope"]["subscriptions"]) or snapshot["scope"]["management_group"]
    status = snapshot["status"]
    provenance = "Live data" if snapshot.get("provenance", "LIVE") == "LIVE" else str(snapshot.get("provenance"))
    meta = [f'<span>Window <b>{esc(w["start_local"])}</b> &rarr; <b>{esc(w["end_local"])}</b></span>',
            f'<span class="m-utc">UTC {esc(utc_short(w["start_utc"]))} &rarr; {esc(utc_short(w["end_utc"]))}</span>', f'<span>Scope <b>{esc(subs)}</b></span>',
            f'<span class="m-gen">Generated <b>{esc(utc_short(snapshot["generated_utc"]))} UTC</b></span>',
            f'<span class="{"st-partial" if status != "ok" else ""}">{esc(provenance)} &middot; {"complete coverage" if status == "ok" else "partial coverage, see Coverage"}</span>']
    if snapshot["parameters"]["resource_group"]:
        meta.append(f'<span>Focus <b>{esc(snapshot["parameters"]["resource_group"])}</b></span>')
    if snapshot.get("files_note"):
        meta.append(f'<span class="st-partial">{esc(snapshot["files_note"])}</span>')
    highlights = "".join(f"<li>{arrows(h)}</li>" for h in head["highlights"])
    client = snapshot["client_name"]
    sections = [("matters", "What changed", counts["reported"] if snapshot["parameters"]["min_level"] != "low" else len(snapshot["changes"])),
                ("deletes", "Deletes", counts["deletes"]), ("security", "Security", security_total), ("who", "Who", len(snapshot["actors"])),
                ("clickops", "Click-ops vs IaC", None), ("unusual", "Unusual", unusual_total), ("noise", "Noise", lv["noise"]),
                ("all", "All changes", len(snapshot["changes"])), ("coverage", "Coverage", None)]
    nav = "".join(f'<a href="#{k}">{esc(t)}{"" if n is None else "<small>" + str(n) + "</small>"}</a>' for k, t, n in sections)
    min_label = {"high": "High changes", "medium": "High and medium changes", "low": "All non-noise changes"}[snapshot["parameters"]["min_level"]]

    def sec(key, title, sub, body, n=None):
        badge = f'<span class="sec-n">{n}</span>' if n is not None else ""
        return f'<section class="sec" id="{key}"><div class="sec-h"><h2>{esc(title)}</h2>{badge}</div><p class="sec-sub">{esc(sub)}</p>{body}</section>'

    body = (
        f'<section class="sec" id="overview" aria-labelledby="ovh"><h2 class="sr" id="ovh">Overview</h2>'
        f'<div class="ov">{render_timeline(snapshot, zone)}{render_split(snapshot)}</div></section>' +
        sec("matters", "What changed that matters", f"{min_label} grouped by resource, worst first. Each change shows when, who, how, why it "
            "matters and the property diff (old \u2192 new).", render_matters(snapshot, zone)) +
        sec("deletes", "Deletes", "Deletes grouped by operation (correlation ID): one VM delete with its disks and NICs is one row. Deleted resources keep no snapshot.",
            render_deletes(snapshot, zone), counts["deletes"]) +
        sec("security", "Security-relevant changes", "Exposure and network rules, Key Vault, identity and encryption, new role assignments and Activity Log gap events.",
            render_security(snapshot, zone), security_total) +
        sec("who", "Who changed what", "Non-noise changes per actor, with how the identity was resolved.", render_actors(snapshot), len(snapshot["actors"])) +
        sec("clickops", "Click-ops vs IaC", "Client type by actor class, and manual portal changes by people.", render_clickops(snapshot, zone)) +
        sec("unusual", "Unusual activity", "Cheap, explainable signals. They highlight and sort; they never change the level on their own.",
            render_unusual(snapshot, zone), unusual_total) +
        sec("noise", "Noise filtered out", "What was hidden and why, so nothing disappears silently.", render_noise(snapshot), lv["noise"]) +
        sec("all", "All non-noise changes", "Filter, search and sort. Low changes are hidden by the default level filter; choose All levels to show them.",
            render_table(snapshot, zone), len(snapshot["changes"])) +
        sec("coverage", "Coverage and sources", "What was read, how completely, and what Change Analysis cannot see.", render_coverage(snapshot))
    )
    title = (esc(client) + " &middot; " if client else "") + "Azure change digest &middot; " + esc(w["end_utc"][:10])
    footer_text = ((client + " \u00b7 " if client else "") + f'Azure change digest \u00b7 {w["label"]} \u00b7 {w["end_utc"][:10]} \u00b7 '
                   f'{TOOL_NAME} {TOOL_VERSION} \u00b7 Internal use')
    page_css = ('@page{size:A4;margin:12mm 11mm 15mm;@bottom-left{content:' + css_text(footer_text) + ';font:8pt "Segoe UI",system-ui,sans-serif;color:#59636E}'
                '@bottom-right{content:"Page " counter(page) " of " counter(pages);font:8pt "Segoe UI",system-ui,sans-serif;color:#59636E}}')
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="{REPORT_CSP}">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="light"><title>{title}</title>'
            f'<style>{REPORT_CSS}{page_css}</style></head><body>'
            f'<header class="top"><div class="wrap">{WORDMARK}<div class="pills">{("<span class=pill>" + esc(client) + "</span>") if client else ""}'
            f'<span class="pill">Change Analysis &middot; Azure Resource Graph</span><span class="pill ro">Read only</span>{PRINT_BUTTON}</div></div></header>'
            f'<section class="hero" aria-labelledby="ttl"><div class="wrap hero-in"><div class="hero-head"><div class="eyebrow">Daily change digest &middot; {esc(w["label"])}</div>'
            f'<h1 id="ttl">Relevant Azure changes</h1><p class="verdict">{arrows(head["verdict"])}</p></div>'
            f'{("<ul class=hl>" + highlights + "</ul>") if highlights else ""}{verdict_card(snapshot)}<div class="meta">{"".join(meta)}</div>'
            f'<div class="kpis">{kpi_html}</div><div class="sn"><div class="sn-h"><span>Signal vs noise &middot; <b>{counts["total"]}</b> changes recorded</span>'
            f'<span>{counts["excluded_by_configuration"]} excluded by configuration</span></div><div class="bar">{bar}</div><div class="legend">{legend}</div></div></div></section>'
            f'<nav class="secnav" aria-label="Sections"><div class="wrap">{nav}</div></nav><main class="wrap">{body}</main>'
            f'<footer><div class="wrap"><span>Generated by Azure SRE Agent &middot; {TOOL_NAME} {TOOL_VERSION} &middot; read only &middot; {esc(snapshot["generated_utc"])}</span>'
            f'<span>{esc(client) + " &middot; " if client else ""}Internal use</span></div></footer><script>{REPORT_JS}</script></body></html>')


# ------------------------- files (HTML, JSON, 2 CSV) and native sharing links -------------------------
ARTIFACT_SUFFIXES = {"report_path": ".html", "snapshot_path": "-snapshot.json", "changes_csv_path": "-changes.csv",
                     "diffs_csv_path": "-property-diffs.csv"}
STEM_RX = re.compile(r"change-digest-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}")
THREAD_ROOT_RX = re.compile(r"/(?:root/sreagent|usr)/terminalRoot/tmp/ThreadFiles/([0-9a-fA-F-]{36})")


def csv_cell(value):
    if value is None:
        return ""
    if isinstance(value, bool):
        return "yes" if value else "no"
    text_value = " | ".join(str(v) for v in value) if isinstance(value, list) else str(value)
    if text_value[:1] in ("\t", "\r", "\n") or text_value.lstrip()[:1] in ("=", "+", "-", "@"):
        return "'" + text_value
    return text_value


def csv_document(rows, fields):
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(fields)
    for row in rows:
        writer.writerow([csv_cell(row.get(field)) for field in fields])
    return stream.getvalue()


CHANGE_FIELDS = ("record_kind", "timestamp_utc", "timestamp_local", "level", "change_type", "resource_name", "resource_type",
                 "resource_group", "subscription_id", "changed_by", "changed_by_type", "actor_class", "actor_display_name",
                 "actor_resolution", "client_type", "client_class", "operation", "correlation_id", "reasons", "flags",
                 "managed_rg", "prod", "security", "relevant_paths", "resource_id", "change_id")
DIFF_FIELDS = ("timestamp_utc", "timestamp_local", "level", "change_type", "resource_name", "resource_type", "resource_group",
               "path", "shape", "path_level", "reason", "previous_value", "new_value", "changed_by", "client_type", "change_id", "resource_id")


def changes_csv_rows(snapshot):
    rows = []
    for c in snapshot["changes"]:
        rows.append({"record_kind": "resource_change", **{k: c[k] for k in ("timestamp_utc", "timestamp_local", "level", "change_type",
                     "resource_name", "resource_type", "resource_group", "subscription_id", "operation", "correlation_id", "reasons",
                     "flags", "managed_rg", "prod", "security", "resource_id", "change_id")},
                     "changed_by": c["actor"]["changed_by"], "changed_by_type": c["actor"]["changed_by_type"],
                     "actor_class": c["actor"]["actor_class"], "actor_display_name": c["actor"]["display_name"],
                     "actor_resolution": c["actor"]["resolution"], "client_type": c["client"]["client_type"],
                     "client_class": c["client"]["client_class"], "relevant_paths": len(c["paths"])})
    for r in snapshot["role_assignments"]:
        rows.append({"record_kind": "role_assignment", "timestamp_utc": r["created_utc"], "timestamp_local": r["time_local"],
                     "level": r["level"], "change_type": "Create" if r["kind"] == "created" else "Update",
                     "resource_name": r["role_name"], "resource_type": "microsoft.authorization/roleassignments",
                     "resource_group": r["resource_group"], "changed_by": r["created_by"], "actor_resolution": r["created_by_resolution"],
                     "reasons": [f"{r['role_name']} for {r['principal_type']} {r['principal_display'] or r['principal_id']}"],
                     "flags": ["privileged role"] if r["privileged"] else [], "resource_id": r["id"], "security": True})
    for g in snapshot["activity_log_gaps"] + snapshot["failed_attempts"]:
        rows.append({"record_kind": "activity_log", "timestamp_utc": g["time_utc"], "timestamp_local": g["time_local"],
                     "level": g["level"], "change_type": g["status"], "resource_name": g["resource_name"], "resource_group": g["resource_group"],
                     "subscription_id": g["subscription_id"], "changed_by": g["caller"], "operation": g["operation"],
                     "correlation_id": g["correlation_id"], "reasons": [g["label"]] + ([g["error_code"]] if g.get("error_code") else []),
                     "resource_id": g["resource_id"], "security": True})
    return rows


def diff_csv_rows(snapshot):
    rows = []
    for c in snapshot["changes"]:
        for p in c["paths"]:
            rows.append({"timestamp_utc": c["timestamp_utc"], "timestamp_local": c["timestamp_local"], "level": c["level"],
                         "change_type": c["change_type"], "resource_name": c["resource_name"], "resource_type": c["resource_type"],
                         "resource_group": c["resource_group"], "path": p["path"], "shape": p["shape"], "path_level": p["level"],
                         "reason": p["reason"], "previous_value": p["previous"], "new_value": p["new"],
                         "changed_by": c["actor"]["changed_by"], "client_type": c["client"]["client_type"],
                         "change_id": c["change_id"], "resource_id": c["resource_id"]})
    return rows


def artifact_directory():
    try:
        cwd = Path.cwd()
        root = cwd.resolve(strict=True)
        linked = any(part.is_symlink() or getattr(part, "is_junction", lambda: False)() for part in (cwd, *cwd.parents))
    except (OSError, RuntimeError) as exc:
        raise DigestError("unsafe_artifact_root", "The working directory must resolve to an existing folder.", "artifact_storage") from exc
    if root == Path(root.anchor) or not root.is_dir() or linked:
        raise DigestError("unsafe_artifact_root", "File system roots and symlinked or junction working directories are refused.", "artifact_storage")
    directory = root / OUTPUT_DIRECTORY
    if directory.is_symlink() or getattr(directory, "is_junction", lambda: False)() or directory.resolve() != directory:
        raise DigestError("unsafe_artifact_directory", "The output folder is a link or escapes the working directory.", "artifact_storage")
    return root, directory


def artifact_paths(directory, stem):
    if not STEM_RX.fullmatch(stem):
        raise DigestError("unsafe_filename", "Refused an unexpected output file name.", "artifact_storage")
    return {key: directory / (stem + suffix) for key, suffix in ARTIFACT_SUFFIXES.items()}


def sharing_fields(root, paths):
    result = {"sharing_mode": "local_files_only"}
    match = THREAD_ROOT_RX.fullmatch(root.as_posix())
    if match is None:
        return result
    try:
        if str(UUID(match.group(1))) != match.group(1).lower():
            return result
    except ValueError:
        return result
    if set(paths) != set(ARTIFACT_SUFFIXES):
        raise DigestError("unsafe_sharing_path", "Native links require the four report files of the same run.", "artifact_storage")
    stem = paths["report_path"].name[:-len(".html")]
    if not STEM_RX.fullmatch(stem):
        raise DigestError("unsafe_sharing_path", "Native links require this tool's generated file names.", "artifact_storage")
    links = {}
    for key, path in paths.items():
        if path.parent != root / OUTPUT_DIRECTORY or path.name != stem + ARTIFACT_SUFFIXES[key]:
            raise DigestError("unsafe_sharing_path", "Native links must point to the same run in the output folder.", "artifact_storage")
        links[key[:-len("_path")] + "_url"] = f"/api/files/tmp/ThreadFiles/{match.group(1)}/{OUTPUT_DIRECTORY}/{quote(path.name, safe='')}"
    return {"sharing_mode": "native_ui", **links}


def report_envelope(snapshot, paths, root):
    links = sharing_fields(root, paths)
    result = {"status": snapshot["status"], "operation": "report"}
    result.update({k: v for k, v in links.items() if k.endswith("_url")})
    result.update({key: str(path) for key, path in paths.items()})
    result.update({"sharing_mode": links["sharing_mode"], "artifact_status": "written", "period": snapshot["window"]["period"],
                   "window_utc": [snapshot["window"]["start_utc"], snapshot["window"]["end_utc"]],
                   "headline": snapshot["headline"]["verdict"], "counts": compact_counts(snapshot["counts"]),
                   "top_items": [compact_item(i) for i in snapshot["items"] if RANK[i["level"]] >= RANK[snapshot["parameters"]["min_level"]]][:10],
                   "coverage": compact_coverage(snapshot)})
    while result["top_items"] and response_bytes(result) > TRANSPORT_BYTES:
        result["top_items"].pop()
    if response_bytes(result) > TRANSPORT_BYTES:
        result["coverage"].pop("issues", None)
    return result


def compact_coverage(snapshot):
    issues = [f"{s['id']}: {s['status']}" + (f" ({clean(s['errors'][0]['message'], 90)})" if s["errors"] else "")
              for s in snapshot["coverage"]["sources"] if s["status"] in ("partial", "denied", "error", "skipped")]
    return {"status": snapshot["coverage"]["status"], "sources": len(snapshot["coverage"]["sources"]),
            "activity_log": snapshot["coverage"]["activity_log"], "graph": snapshot["coverage"]["graph"], "issues": issues[:3]}


def build_documents(snapshot):
    """Render the four files; for very large estates drop low-level detail (never high/medium) to stay under 4.8 MB per file."""
    def render(snap, indent):
        return {
            "report_path": render_html(snap).encode("utf-8"),
            "snapshot_path": json.dumps(snap, ensure_ascii=False, indent=indent, allow_nan=False).encode("utf-8"),
            "changes_csv_path": csv_document(changes_csv_rows(snap), CHANGE_FIELDS).encode("utf-8-sig"),
            "diffs_csv_path": csv_document(diff_csv_rows(snap), DIFF_FIELDS).encode("utf-8-sig"),
        }

    contents = render(snapshot, 1)
    if all(len(data) <= ARTIFACT_BYTES for data in contents.values()):
        return contents, None
    note = "Low-level changes were omitted from the files to stay under 4.8 MB; they are still counted."
    slim = dict(snapshot, changes=[c for c in snapshot["changes"] if c["level"] != "low"], files_note=note)
    contents = render(slim, None)
    if any(len(data) > ARTIFACT_BYTES for data in contents.values()):
        raise DigestError("artifact_size_exceeded", "A report file would exceed 4.8 MB even without low-level changes; "
                                                    "narrow the period or use resource_group.", "artifact_storage")
    return contents, note


def write_report(snapshot):
    root, directory = artifact_directory()
    stem = "change-digest-" + snapshot["generated_utc"].replace("-", "").replace(":", "") + "-" + uuid4().hex[:8]
    paths = artifact_paths(directory, stem)
    response = report_envelope(snapshot, paths, root)
    contents, note = build_documents(snapshot)
    if note:
        response["files_note"] = note
        while response["top_items"] and response_bytes(response) > TRANSPORT_BYTES:
            response["top_items"].pop()
    written, temporary = [], []
    try:
        directory.mkdir(exist_ok=True)
        if artifact_directory()[1] != directory or not directory.is_dir() or directory.is_symlink():
            raise DigestError("unsafe_artifact_directory", "The output folder changed after creation.", "artifact_storage")
        for key, data in contents.items():
            target = paths[key]
            if target.exists() or target.is_symlink():
                raise DigestError("artifact_collision", "An output file already exists; nothing is overwritten.", "artifact_storage")
            fd, name = tempfile.mkstemp(prefix=stem + "-", suffix=".tmp", dir=directory)
            temporary.append(Path(name))
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, target)
            temporary.remove(Path(name))
            written.append(target)
        if any(paths[key].read_bytes() != data for key, data in contents.items()):
            raise DigestError("artifact_readback_failed", "Written files differ from the prepared content.", "artifact_storage")
    except (OSError, DigestError) as exc:
        for path in temporary + written:
            try:
                path.unlink()
            except OSError:
                pass
        if isinstance(exc, DigestError):
            raise
        raise DigestError("artifact_write_failed", f"Could not write the report files ({type(exc).__name__}).", "artifact_storage") from exc
    return response


# ------------------------- entry point -------------------------
def run_digest(params, config):
    started = time.monotonic()
    identity = Identity(config["client_id"])
    try:
        identity.token(ARM)
        reader = Reader(identity, started + MAX_COLLECTION_SECONDS, ENABLE_GRAPH_NAMES)
        raw = collect_core(reader, config, params)
        analysis = analyze(raw, config, params)
        resolve_names(reader, config, params, analysis, raw)
        stats = {"requests": reader.requests, "throttled": reader.throttled, "seconds": round(time.monotonic() - started, 1),
                 "identity": {("arm" if k == ARM else "graph"): v for k, v in identity.checks.items()}}
        return build_snapshot(analysis, raw, config, params, stats)
    finally:
        identity.close()


def main(operation: str = "report", period: str = "last_24h", min_level: str = "medium", view: str = "summary",
         resource_group: str = "", limit: int = 25) -> dict:
    """Read-only daily digest of relevant Azure changes (Change Analysis in Azure Resource Graph).

    operation: report (HTML + JSON snapshot + changes CSV + property diffs CSV) or query (bounded chat view).
    period: last_24h | last_7d | last_14d. min_level: high | medium | low (lowest level listed in detail).
    view (query only): summary | relevant | deletes | security | actors | unusual | rbac | noise | coverage.
    resource_group: optional name or part of a name. limit (query only): 1-100.
    """
    try:
        params = validate_parameters(operation, period, min_level, view, resource_group, limit)
        config = validate_config()
        snapshot = run_digest(params, config)
        return query_view(snapshot, params) if params["operation"] == "query" else write_report(snapshot)
    except DigestError as exc:
        return {"status": "error", "operation": operation if operation in OPERATIONS else "report", "error": exc.public(),
                "artifact_status": "not_written", "read_only": True}
    except Exception as exc:
        return {"status": "error", "operation": operation if operation in OPERATIONS else "report",
                "error": {"code": "unexpected_error", "message": f"Unexpected {type(exc).__name__}; no files were written. "
                          "The tool is read-only and changed nothing.", "source": "digest", "http_status": None},
                "artifact_status": "not_written", "read_only": True}

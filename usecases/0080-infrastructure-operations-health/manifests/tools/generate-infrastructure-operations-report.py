"""Standalone, read-only Azure SRE Agent infrastructure evidence tool."""

import base64
import binascii
import csv
import hashlib
import html
import io
import json
import math
import os
import re
import statistics
import struct
import tempfile
import time
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlsplit
from uuid import UUID, uuid4

SUBSCRIPTION_ID = "<YOUR_SUBSCRIPTION_ID>"
TENANT_ID = "<YOUR_TENANT_ID>"
MANAGED_IDENTITY_CLIENT_ID = "<YOUR_AGENT_CLIENT_ID>"
LOG_WORKSPACE_IDS = []
ARC_ADMIN_BASELINES = []
COMPANY_LOGO_DATA_URI = ""
COMPANY_LOGO_ALT_TEXT = "Company logo"
MAX_COMPANY_LOGO_BYTES = 100_000
MAX_COMPANY_LOGO_DIMENSION = 2048
ARM_ORIGIN = "https://management.azure.com"
LOGS_ORIGIN = "https://api.loganalytics.azure.com"
LOGS_AUDIENCE = "https://api.loganalytics.io/.default"
OUTPUT_DIRECTORY = Path("infrastructure-operations-reports")
TRANSPORT_BUDGET_BYTES = 3500
MAX_ARTIFACT_BYTES = 4_800_000
MAX_RESOURCES = 500
MAX_SOURCE_ROWS = 50000
MAX_PAGES = 100
MAX_BINS = 800
MAX_ARC_EXTENSION_ROWS = 5000
MAX_ARC_EXTENSION_PAGES = 10
ARC_EXTENSION_BUDGET_SECONDS = 90
ARG_VERSION = "2022-10-01"
METRICS_VERSION = "2023-10-01"
DEFINITIONS_VERSION = "2018-01-01"
HEALTH_VERSION = "2022-10-01"
ALERTS_VERSION = "2019-03-01"
UTC = timezone.utc

RESOURCE_TYPES = (
    "microsoft.hybridcompute/machines",
    "microsoft.kubernetes/connectedclusters",
    "microsoft.compute/virtualmachines",
    "microsoft.compute/virtualmachinescalesets",
    "microsoft.containerservice/managedclusters",
    "microsoft.app/containerapps",
    "microsoft.web/sites",
    "microsoft.web/serverfarms",
    "microsoft.storage/storageaccounts",
    "microsoft.keyvault/vaults",
    "microsoft.containerregistry/registries",
    "microsoft.sql/servers/databases",
    "microsoft.dbforpostgresql/flexibleservers",
    "microsoft.dbformysql/flexibleservers",
    "microsoft.cache/redis",
)
COMPUTE_TYPES = (
    "microsoft.hybridcompute/machines",
    "microsoft.compute/virtualmachines",
    "microsoft.compute/virtualmachinescalesets",
)
ARC_TYPES = ("microsoft.hybridcompute/machines", "microsoft.kubernetes/connectedclusters")
VIEWS = ("summary", "resources", "extensions", "metrics", "timeline", "signals", "actions", "coverage")
METRIC_INFO = {
    "cpu_percent": ("CPU utilization", "Percent", "high"),
    "memory_available_percent": ("Available physical memory", "Percent", "low"),
    "memory_available_bytes": ("Available physical memory", "Bytes", "context"),
    "memory_used_percent": ("Guest used physical memory", "Percent", "high"),
    "memory_commit_percent": ("Windows committed memory", "Percent", "high"),
    "disk_free_percent": ("Guest volume free space", "Percent", "low"),
    "disk_iops_percent": ("Provisioned disk IOPS consumed", "Percent", "high"),
    "disk_bandwidth_percent": ("Provisioned disk bandwidth consumed", "Percent", "high"),
    "vm_availability": ("VM platform availability", "Count", "low"),
    "storage_used_bytes": ("Storage used capacity", "Bytes", "context"),
    "service_availability_percent": ("Service availability", "Percent", "low"),
    "service_latency_ms": ("Service latency", "MilliSeconds", "context"),
    "service_requests": ("Service requests", "Count", "context"),
    "service_errors": ("Service errors", "Count", "context"),
    "node_cpu_percent": ("AKS node CPU utilization", "Percent", "high"),
    "node_memory_percent": ("AKS node memory utilization", "Percent", "high"),
    "node_disk_percent": ("AKS node disk utilization", "Percent", "high"),
    "app_cpu_time_seconds": ("App Service CPU time", "Seconds", "context"),
    "app_memory_bytes": ("Service memory bytes", "Bytes", "context"),
    "container_cpu_cores": ("Container Apps CPU usage", "NanoCores", "context"),
    "container_memory_bytes": ("Container Apps memory working set", "Bytes", "context"),
    "container_cpu_percent": ("Container CPU / configured limit", "Percent", "high"),
    "container_memory_percent": ("Container memory / configured limit", "Percent", "high"),
    "container_replicas": ("Container Apps replicas", "Count", "context"),
    "plan_cpu_percent": ("App Service plan CPU utilization", "Percent", "high"),
    "plan_memory_percent": ("App Service plan memory utilization", "Percent", "high"),
    "sql_cpu_percent": ("Database CPU utilization", "Percent", "high"),
    "sql_memory_percent": ("Database memory utilization", "Percent", "context"),
    "sql_storage_percent": ("Database storage utilization", "Percent", "high"),
}
PLATFORM_METRICS = {
    "microsoft.compute/virtualmachines": (
        ("Percentage CPU", "cpu_percent"),
        ("Available Memory Percentage", "memory_available_percent"),
        ("Available Memory Bytes", "memory_available_bytes"),
        ("OS Disk IOPS Consumed Percentage", "disk_iops_percent"),
        ("OS Disk Bandwidth Consumed Percentage", "disk_bandwidth_percent"),
        ("VmAvailabilityMetric", "vm_availability"),
    ),
    "microsoft.compute/virtualmachinescalesets": (
        ("Percentage CPU", "cpu_percent"),
        ("Available Memory Percentage", "memory_available_percent"),
        ("Available Memory Bytes", "memory_available_bytes"),
        ("OS Disk IOPS Consumed Percentage", "disk_iops_percent"),
        ("VmAvailabilityMetric", "vm_availability"),
    ),
    "microsoft.containerservice/managedclusters": (
        ("node_cpu_usage_percentage", "node_cpu_percent"),
        ("node_memory_rss_percentage", "node_memory_percent"),
        ("node_disk_usage_percentage", "node_disk_percent"),
    ),
    "microsoft.app/containerapps": (
        ("UsageNanoCores", "container_cpu_cores"),
        ("WorkingSetBytes", "container_memory_bytes"),
        ("CpuPercentage", "container_cpu_percent"),
        ("MemoryPercentage", "container_memory_percent"),
        ("Replicas", "container_replicas"),
        ("Requests", "service_requests"),
    ),
    "microsoft.web/sites": (
        ("CpuTime", "app_cpu_time_seconds"),
        ("AverageMemoryWorkingSet", "app_memory_bytes"),
        ("Requests", "service_requests"),
        ("Http5xx", "service_errors"),
    ),
    "microsoft.web/serverfarms": (
        ("CpuPercentage", "plan_cpu_percent"),
        ("MemoryPercentage", "plan_memory_percent"),
    ),
    "microsoft.storage/storageaccounts": (
        ("UsedCapacity", "storage_used_bytes"),
        ("Availability", "service_availability_percent"),
        ("SuccessE2ELatency", "service_latency_ms"),
        ("Transactions", "service_requests"),
    ),
    "microsoft.keyvault/vaults": (
        ("Availability", "service_availability_percent"),
        ("ServiceApiLatency", "service_latency_ms"),
        ("ServiceApiHit", "service_requests"),
    ),
    "microsoft.containerregistry/registries": (
        ("StorageUsed", "storage_used_bytes"),
        ("TotalPullCount", "service_requests"),
    ),
    "microsoft.sql/servers/databases": (
        ("cpu_percent", "sql_cpu_percent"),
        ("storage_percent", "sql_storage_percent"),
    ),
    "microsoft.dbforpostgresql/flexibleservers": (
        ("cpu_percent", "sql_cpu_percent"),
        ("memory_percent", "sql_memory_percent"),
        ("storage_percent", "sql_storage_percent"),
    ),
    "microsoft.dbformysql/flexibleservers": (
        ("cpu_percent", "sql_cpu_percent"),
        ("memory_percent", "sql_memory_percent"),
        ("storage_percent", "sql_storage_percent"),
    ),
    "microsoft.cache/redis": (("usedmemory", "app_memory_bytes"),),
}
POLICY = {
    "sustained_bins": 3,
    "high_utilization_percent": 85.0,
    "high_cpu_peak_percent": 95.0,
    "low_memory_available_percent": 10.0,
    "high_memory_used_percent": 90.0,
    "low_disk_free_percent": 15.0,
    "package_image_mount_pattern": r"/snap/[a-z0-9][a-z0-9-]*/[0-9]+",
    "service_availability_below_percent": 99.0,
    "heartbeat_stale_minutes": 10,
    "minimum_window_bin_coverage_percent": 80.0,
    "anomaly_minimum_prior_bins": 12,
    "anomaly_baseline_bins": 48,
    "anomaly_mad_multiplier": 6.0,
    "anomaly_minimum_percent_delta": 20.0,
}


class EvidenceError(RuntimeError):
    def __init__(self, code, message, source, http_status=None, artifacts_may_remain=False):
        super().__init__(message)
        self.code = code
        self.message = message
        self.source = source
        self.http_status = http_status
        self.artifacts_may_remain = artifacts_may_remain

    def document(self):
        result = {"code": self.code, "message": self.message, "source": self.source}
        if self.http_status is not None:
            result["http_status"] = self.http_status
        return result


def _utc_now():
    return datetime.now(UTC)


def _iso(value):
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _time(value, source):
    if not isinstance(value, str) or not value or len(value) > 40:
        raise EvidenceError("invalid_timestamp", "Expected an explicit-offset ISO 8601 timestamp.", source)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EvidenceError("invalid_timestamp", "Could not parse an evidence timestamp.", source) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise EvidenceError("invalid_timestamp", "Timestamps must have an explicit UTC offset.", source)
    return parsed.astimezone(UTC)


def _number(value, source, optional=False):
    if value is None and optional:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise EvidenceError("invalid_number", "Source contained a non-finite or non-numeric measurement.", source)
    return value


def _string(value, maximum, field, empty=True):
    if not isinstance(value, str) or len(value) > maximum or re.search(r"[\x00-\x1f\x7f]", value):
        raise EvidenceError("invalid_parameter", f"{field} must be a bounded plain string.", "parameters")
    if not empty and not value:
        raise EvidenceError("invalid_parameter", f"{field} cannot be empty.", "parameters")
    return value.strip()


def _enum(value, choices, field):
    if not isinstance(value, str) or value not in choices:
        raise EvidenceError("invalid_parameter", f"Unsupported {field}. Use the documented enum.", "parameters")
    return value


def _guid(value, name):
    try:
        if not isinstance(value, str) or str(UUID(value)) != value.casefold():
            raise ValueError
    except (ValueError, AttributeError) as exc:
        raise EvidenceError("configuration_required", f"Configure {name} with the correct GUID.", "configuration") from exc
    return value.casefold()


def _config():
    result = {
        "subscription_id": _guid(SUBSCRIPTION_ID, "SUBSCRIPTION_ID"),
        "tenant_id": _guid(TENANT_ID, "TENANT_ID"),
        "client_id": _guid(MANAGED_IDENTITY_CLIENT_ID, "MANAGED_IDENTITY_CLIENT_ID"),
    }
    if not isinstance(LOG_WORKSPACE_IDS, list) or len(LOG_WORKSPACE_IDS) > 5:
        raise EvidenceError("configuration_required", "Configure zero to five explicitly allowed workspace GUIDs.", "configuration")
    workspaces = [_guid(value, "LOG_WORKSPACE_IDS") for value in LOG_WORKSPACE_IDS]
    if len(set(workspaces)) != len(workspaces):
        raise EvidenceError("configuration_required", "LOG_WORKSPACE_IDS cannot contain duplicates.", "configuration")
    result["workspace_ids"] = workspaces
    result["arc_baselines"] = _arc_baselines()
    return result


def _version_parts(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{1,6}(?:\.[0-9]{1,6}){1,3}", value):
        return None
    parts = tuple(int(part) for part in value.split("."))
    return parts + (0,) * (4 - len(parts))


def _compare_versions(observed, target):
    left, right = _version_parts(observed), _version_parts(target)
    return None if left is None or right is None else (left > right) - (left < right)


def _arc_baselines():
    source = "configuration"

    def invalid():
        raise EvidenceError("configuration_required", "ARC_ADMIN_BASELINES must follow the documented dated, exact-scope review contract.", source)

    def text(value, maximum):
        if not isinstance(value, str) or not value.strip() or len(value) > maximum or re.search(r"[\x00-\x1f\x7f]", value):
            invalid()
        return value.strip()

    if not isinstance(ARC_ADMIN_BASELINES, list) or len(ARC_ADMIN_BASELINES) > 50:
        invalid()
    result, scopes, identities = [], set(), set()
    required = {"baseline_id", "owner", "reference", "as_of_utc", "valid_until_utc",
                "os_type", "os_sku", "os_version", "location"}
    for entry in ARC_ADMIN_BASELINES:
        if not isinstance(entry, dict) or not required <= set(entry) or set(entry) - required - {
            "agent_review_version", "required_extensions", "notes",
        }:
            invalid()
        rule = {key: text(entry[key], 512 if key == "reference" else 256) for key in required}
        if rule["os_type"].casefold() not in ("linux", "windows"):
            invalid()
        try:
            start, end = _time(rule["as_of_utc"], source), _time(rule["valid_until_utc"], source)
        except EvidenceError as exc:
            raise EvidenceError("configuration_required", "Arc baseline dates require explicit-offset ISO 8601 timestamps.", source) from exc
        if not start < end <= start + timedelta(days=31):
            invalid()
        rule.update(as_of_utc=_iso(start), valid_until_utc=_iso(end))
        scope = tuple(rule[key].casefold() for key in ("os_type", "os_sku", "os_version", "location"))
        if scope in scopes or rule["baseline_id"].casefold() in identities:
            invalid()
        scopes.add(scope)
        identities.add(rule["baseline_id"].casefold())
        if "agent_review_version" in entry:
            if _version_parts(entry["agent_review_version"]) is None:
                invalid()
            rule["agent_review_version"] = entry["agent_review_version"]
        rule["notes"] = text(entry["notes"], 1024) if "notes" in entry else ""
        requirements = entry.get("required_extensions", [])
        if not isinstance(requirements, list) or len(requirements) > 20:
            invalid()
        rule["required_extensions"], extension_keys = [], set()
        for requirement in requirements:
            if not isinstance(requirement, dict) or not {"publisher", "type"} <= set(requirement) or set(requirement) - {
                "publisher", "type", "review_version", "enable_automatic_upgrade", "auto_upgrade_minor_version",
            }:
                invalid()
            expected = {key: text(requirement[key], 256) for key in ("publisher", "type")}
            identity = (expected["publisher"].casefold(), expected["type"].casefold())
            if identity in extension_keys:
                invalid()
            extension_keys.add(identity)
            for key in ("enable_automatic_upgrade", "auto_upgrade_minor_version"):
                if key in requirement:
                    if type(requirement[key]) is not bool:
                        invalid()
                    expected[key] = requirement[key]
            if "review_version" in requirement:
                if _version_parts(requirement["review_version"]) is None:
                    invalid()
                expected["review_version"] = requirement["review_version"]
            rule["required_extensions"].append(expected)
        result.append(rule)
    return result


def _parameters(operation, view, hosting, resource_group, resource_name, resource_id,
                resource_type, metric, state, severity, period, start_utc, end_utc,
                grain, limit, offset, reference):
    params = {
        "operation": _enum(operation, ("report", "query"), "operation"),
        "view": _enum(view, VIEWS, "view"),
        "hosting": _enum(hosting, ("all", "arc", "azure"), "hosting"),
        "resource_group": _string(resource_group, 90, "resource_group"),
        "resource_name": _string(resource_name, 160, "resource_name"),
        "resource_id": _string(resource_id, 2048, "resource_id"),
        "resource_type": _string(resource_type, 180, "resource_type").casefold(),
        "metric": _enum(metric, ("all", *METRIC_INFO), "metric"),
        "state": _enum(state, ("all", "review", "unknown", "observed"), "state"),
        "severity": _enum(severity, ("all", "critical", "warning", "info"), "severity"),
        "period": _enum(period, ("auto", "last_2h", "last_24h", "last_7d", "last_30d", "previous_month", "custom"), "period"),
        "grain": _enum(grain, ("auto", "PT5M", "PT1H"), "grain"),
    }
    if type(limit) is not int or not 1 <= limit <= 100 or type(offset) is not int or not 0 <= offset <= MAX_SOURCE_ROWS:
        raise EvidenceError("invalid_parameter", "limit or offset is outside the documented integer bounds.", "parameters")
    params.update(limit=limit, offset=offset)
    if params["resource_type"] and params["resource_type"] not in RESOURCE_TYPES:
        raise EvidenceError("unsupported_filter", "resource_type is not in this infrastructure inventory scope.", "parameters")
    if operation == "report" and (view != "summary" or state != "all" or severity != "all" or limit != 20 or offset):
        raise EvidenceError("unsupported_filter", "A report cannot apply query-only view/state/severity/page filters.", "parameters")
    if operation == "query" and view not in ("signals", "timeline", "actions") and severity != "all":
        raise EvidenceError("unsupported_filter", "severity applies only to signals, timeline and actions.", "parameters")
    if operation == "query" and view in ("summary", "coverage") and state != "all":
        raise EvidenceError("unsupported_filter", "summary and coverage do not accept state.", "parameters")
    if operation == "query" and view == "timeline" and metric != "all":
        raise EvidenceError("unsupported_filter", "Native event history has no verified metric association. Use signals for metric-filtered chronology.", "parameters")
    if operation == "query" and view == "extensions" and metric != "all":
        raise EvidenceError("unsupported_filter", "Extension metadata has no metric association; use metric=all.", "parameters")
    start_utc = _string(start_utc, 40, "start_utc")
    end_utc = _string(end_utc, 40, "end_utc")
    selected_period = params["period"]
    if selected_period == "auto":
        selected_period = "previous_month" if operation == "report" else "last_24h"
    if selected_period == "custom":
        start, end = _time(start_utc, "parameters"), _time(end_utc, "parameters")
    else:
        if start_utc or end_utc:
            raise EvidenceError("unsupported_filter", "start_utc/end_utc require period=custom.", "parameters")
        end = reference.replace(microsecond=0)
        if selected_period == "previous_month":
            end = end.replace(day=1, hour=0, minute=0, second=0)
            start = (end - timedelta(days=1)).replace(day=1)
        else:
            hours = {"last_2h": 2, "last_24h": 24, "last_7d": 168, "last_30d": 720}[selected_period]
            start = end - timedelta(hours=hours)
    if end <= start or end > reference or end - start > timedelta(days=31):
        raise EvidenceError("invalid_window", "Choose a past, positive window of no more than 31 days.", "parameters")
    interval = params["grain"]
    if interval == "auto":
        interval = "PT5M" if end - start <= timedelta(hours=48) else "PT1H"
    seconds = 300 if interval == "PT5M" else 3600
    first_bin = int(start.timestamp()) // seconds * seconds
    bins = math.ceil((end.timestamp() - first_bin) / seconds)
    if bins > MAX_BINS:
        raise EvidenceError("window_too_dense", "Window/grain exceeds 800 bins; select hourly grain or a shorter window.", "parameters")
    params["window"] = {
        "period": selected_period, "start_utc": _iso(start), "end_utc": _iso(end),
        "grain": interval, "grain_seconds": seconds, "expected_bins": bins,
        "first_bin_utc": _iso(datetime.fromtimestamp(first_bin, UTC)),
        "partial_edge_bins": start.timestamp() != first_bin or end.timestamp() % seconds != 0,
    }
    return params


def _resource_id(value, subscription_id, source):
    if (
        not isinstance(value, str) or not value or len(value) > 2048
        or re.search(r"[\x00-\x1f\x7f?#\\%]", value)
        or any(part in ("", ".", "..") for part in value.split("/")[1:])
        or not value.casefold().startswith("/subscriptions/" + subscription_id + "/resourcegroups/")
        or "/providers/" not in value.casefold()
    ):
        raise EvidenceError("invalid_resource_id", "Resource ID is malformed or outside the fixed subscription.", source)
    return value.rstrip("/").casefold()


def _inventory_query():
    types = ", ".join("'" + value + "'" for value in RESOURCE_TYPES)
    return (
        "resources | where type in~ (" + types + ") "
        "| project id, name, type, resourceGroup, location, tags, properties=bag_pack("
        "'status', properties.status, 'provisioningState', properties.provisioningState, "
        "'osName', properties.osName, 'osType', coalesce(properties.osType, properties.storageProfile.osDisk.osType), "
        "'vmSize', properties.hardwareProfile.vmSize, 'powerState', properties.extended.instanceView.powerState.code, "
        "'lastStatusChange', properties.lastStatusChange, 'agentVersion', properties.agentVersion, "
        "'osSku', properties.osSku, 'osVersion', properties.osVersion) "
        "| order by id asc"
    )


def _arc_extension_query():
    return (
        "resources | where type =~ 'microsoft.hybridcompute/machines/extensions' "
        "| project id, name, type, location, properties=bag_pack("
        "'publisher', properties.publisher, 'type', properties.type, "
        "'typeHandlerVersion', properties.typeHandlerVersion, "
        "'provisioningState', properties.provisioningState, "
        "'enableAutomaticUpgrade', properties.enableAutomaticUpgrade, "
        "'autoUpgradeMinorVersion', properties.autoUpgradeMinorVersion, "
        "'instanceView', bag_pack('typeHandlerVersion', properties.instanceView.typeHandlerVersion)) "
        "| order by id asc"
    )


def _arc_metadata(value, field, boolean=False, source="inventory"):
    if value is None:
        return None
    valid = type(value) is bool if boolean else (
        isinstance(value, str) and len(value) <= 256 and not re.search(r"[\x00-\x1f\x7f]", value)
    )
    if not valid:
        raise EvidenceError("invalid_arc_metadata", "Arc source supplied an invalid " + field + " field.", source)
    return value


def _owner(tags):
    for key, value in tags.items():
        if not isinstance(key, str):
            raise EvidenceError("invalid_tags", "Resource tag keys must be strings.", "inventory")
        if key.casefold() in ("owner", "serviceowner", "service_owner", "service owner", "team", "responsable", "equipo") and isinstance(value, str) and value:
            return value
    return None


def _normalize_resources(rows, subscription_id):
    normalized, ids = [], set()
    for row in rows:
        resource_id = _resource_id(row.get("id"), subscription_id, "inventory")
        if resource_id in ids:
            raise EvidenceError("duplicate_resource", "Inventory repeated a resource ID.", "inventory")
        ids.add(resource_id)
        resource_type = row.get("type", "").casefold()
        if resource_type not in RESOURCE_TYPES:
            raise EvidenceError("unexpected_resource_type", "Inventory returned an unrequested resource type.", "inventory")
        if any(not isinstance(row.get(key), str) or not row[key] for key in ("name", "resourceGroup", "location")):
            raise EvidenceError("invalid_inventory", "Inventory is missing resource identity fields.", "inventory")
        tags = row.get("tags") if row.get("tags") is not None else {}
        props = row.get("properties") if row.get("properties") is not None else {}
        if not isinstance(tags, dict) or not isinstance(props, dict):
            raise EvidenceError("invalid_inventory", "Resource tags/properties must be objects.", "inventory")
        if resource_type == "microsoft.hybridcompute/machines" and props.get("lastStatusChange") is not None:
            _time(props["lastStatusChange"], "inventory")
        normalized.append({
            "resource_id": resource_id, "name": row["name"], "resource_type": resource_type,
            "resource_group": row["resourceGroup"], "location": row["location"],
            "hosting": "arc" if resource_type in ARC_TYPES else "azure",
            "owner": _owner(tags), "tags": tags,
            "os": props.get("osName") or props.get("osType"),
            "os_type": _arc_metadata(props.get("osType"), "osType"),
            "os_sku": _arc_metadata(props.get("osSku"), "osSku"),
            "os_version": _arc_metadata(props.get("osVersion"), "osVersion"),
            "size": props.get("vmSize"), "power_state": props.get("powerState"),
            "provisioning_state": props.get("provisioningState"),
            "arc_connection": props.get("status") if resource_type in ARC_TYPES else None,
            "arc_status_changed_utc": props.get("lastStatusChange"),
            "arc_agent_version": _arc_metadata(props.get("agentVersion"), "agentVersion")
            if resource_type == "microsoft.hybridcompute/machines" else None,
            "health": None, "heartbeat": None, "assessment": "unknown",
            "series_count": 0, "review_signals": 0,
        })
    if len(normalized) > MAX_RESOURCES:
        raise EvidenceError("scope_too_large", "Inventory exceeds 500 relevant resources; narrow the configured scope.", "inventory")
    return sorted(normalized, key=lambda row: (row["hosting"], row["name"].casefold(), row["resource_id"]))


def _normalize_arc_extensions(rows, resources, subscription_id, reference):
    machines = {row["resource_id"] for row in resources if row["resource_type"] == "microsoft.hybridcompute/machines"}
    result, identities = [], set()
    for row in rows:
        extension_id = _resource_id(row.get("id"), subscription_id, "arc_extensions")
        parts = extension_id.split("/")
        if len(parts) != 11 or parts[6:8] != ["microsoft.hybridcompute", "machines"] or parts[9] != "extensions":
            raise EvidenceError("invalid_arc_extension", "Extension ID is not a native Arc machine child ID.", "arc_extensions")
        if extension_id in identities or str(row.get("type", "")).casefold() != "microsoft.hybridcompute/machines/extensions":
            raise EvidenceError("invalid_arc_extension", "Arc extension type/identity is invalid or repeated.", "arc_extensions")
        identities.add(extension_id)
        props = row.get("properties")
        if not isinstance(props, dict):
            raise EvidenceError("invalid_arc_extension", "Arc extension properties must be an object.", "arc_extensions")
        view = props.get("instanceView")
        if view is not None and not isinstance(view, dict):
            raise EvidenceError("invalid_arc_extension", "Arc extension instanceView must be an object when supplied.", "arc_extensions")
        parent_id = "/".join(parts[:9])
        metadata = {
            "extension_id": extension_id, "resource_id": parent_id,
            "name": _arc_metadata(row.get("name"), "name", source="arc_extensions"),
            "location": _arc_metadata(row.get("location"), "location", source="arc_extensions"),
            "publisher": _arc_metadata(props.get("publisher"), "publisher", source="arc_extensions"),
            "extension_type": _arc_metadata(props.get("type"), "type", source="arc_extensions"),
            "type_handler_version": _arc_metadata(props.get("typeHandlerVersion"), "typeHandlerVersion", source="arc_extensions"),
            "instance_view_version": _arc_metadata((view or {}).get("typeHandlerVersion"), "instanceView.typeHandlerVersion", source="arc_extensions"),
            "provisioning_state": _arc_metadata(props.get("provisioningState"), "provisioningState", source="arc_extensions"),
            "enable_automatic_upgrade": _arc_metadata(props.get("enableAutomaticUpgrade"), "enableAutomaticUpgrade", True, "arc_extensions"),
            "auto_upgrade_minor_version": _arc_metadata(props.get("autoUpgradeMinorVersion"), "autoUpgradeMinorVersion", True, "arc_extensions"),
            "source": "arc_extensions", "collected_utc": _iso(reference),
        }
        metadata["missing_fields"] = [key for key in (
            "name", "location", "publisher", "extension_type", "type_handler_version", "instance_view_version",
            "provisioning_state", "enable_automatic_upgrade", "auto_upgrade_minor_version",
        ) if metadata[key] is None or metadata[key] == ""]
        if parent_id in machines:
            result.append(metadata)
    return sorted(result, key=lambda row: row["extension_id"])


def _resource_matches(row, params):
    return (
        (params["hosting"] == "all" or row["hosting"] == params["hosting"])
        and (not params["resource_group"] or row["resource_group"].casefold() == params["resource_group"].casefold())
        and (not params["resource_name"] or params["resource_name"].casefold() in row["name"].casefold())
        and (not params["resource_id"] or row["resource_id"] == params["resource_id"].casefold())
        and (not params["resource_type"] or row["resource_type"] == params["resource_type"])
    )


def _response_bytes(value):
    return len(json.dumps(value, allow_nan=False).encode("utf-8"))


def _budget(value):
    if _response_bytes(value) > TRANSPORT_BUDGET_BYTES:
        raise EvidenceError("transport_budget_exceeded", "Response exceeds the default-serialized 3500-byte budget.", "response")
    return value


def _failure(exc):
    return _budget({
        "status": "error", "provenance": "LIVE", "error": exc.document(),
        "artifacts_created": None if exc.artifacts_may_remain else False,
        "artifacts_may_remain": exc.artifacts_may_remain,
    })


def _source(name, status, reference, records=0, note="", error=None, resource_id=None, **extra):
    result = {
        "source": name, "status": status, "collected_utc": _iso(reference),
        "records": records, "note": note, **extra,
    }
    if resource_id is not None:
        result["resource_id"] = resource_id
    if error is not None:
        result["error"] = error.document()
    return result


class AzureReadClient:
    def __init__(self, config):
        try:
            import requests
            from azure.identity import ManagedIdentityCredential, CredentialUnavailableError
            from azure.core.exceptions import ClientAuthenticationError, ServiceRequestError
        except ImportError as exc:
            raise EvidenceError("dependency_missing", "Install requests and azure-identity before deployment.", "identity") from exc
        self.requests = requests
        self.authentication_errors = (CredentialUnavailableError, ClientAuthenticationError, ServiceRequestError)
        self.config = config
        self.credential = ManagedIdentityCredential(client_id=config["client_id"])
        self.local = threading.local()
        self.lock = threading.Lock()
        self.tokens = {}
        self.sessions = []

    def close(self):
        for session in self.sessions:
            session.close()
        self.credential.close()

    def _token(self, scope):
        with self.lock:
            token = self.tokens.get(scope)
            if token is None or token.expires_on <= time.time() + 60:
                try:
                    token = self.credential.get_token(scope)
                except self.authentication_errors as exc:
                    raise EvidenceError("authentication_failed", "The configured managed identity could not acquire the source token.", "identity") from exc
                if not isinstance(token.token, str) or not token.token:
                    raise EvidenceError("authentication_failed", "Managed identity returned an empty token.", "identity")
                self.tokens[scope] = token
            return token.token

    def _session(self):
        if not hasattr(self.local, "session"):
            self.local.session = self.requests.Session()
            with self.lock:
                self.sessions.append(self.local.session)
        return self.local.session

    def request(self, method, url, source, body=None, deadline=None):
        scope = _validate_endpoint(method, url, body, self.config)
        headers = {"Authorization": "Bearer " + self._token(scope), "Accept": "application/json"}
        if url.startswith(LOGS_ORIGIN + "/"):
            headers["Prefer"] = "wait=120"
        for attempt in range(3):
            remaining = deadline - time.monotonic() if deadline is not None else None
            if remaining is not None and remaining <= 0:
                raise EvidenceError("source_budget_exceeded", "Arc extension collection exhausted its 90-second read budget.", source)
            timeout = (10, 150) if remaining is None else (min(10, remaining / 2), min(30, remaining / 2))
            try:
                with self._session().request(
                    method, url, headers=headers, json=body, timeout=timeout,
                    allow_redirects=False, stream=True,
                ) as response:
                    if response.status_code in (429, 500, 502, 503, 504) and attempt < 2:
                        delay = response.headers.get("Retry-After", "")
                        wait = min(int(delay), 5) if re.fullmatch(r"[0-9]{1,4}", delay) else attempt + 1
                        time.sleep(wait if deadline is None else max(0, min(wait, deadline - time.monotonic())))
                        continue
                    if response.status_code != 200:
                        raise EvidenceError("api_failed", f"{source} returned HTTP {response.status_code}; evidence is unavailable.", source, response.status_code)
                    chunks, length = [], 0
                    for chunk in response.iter_content(chunk_size=65536):
                        if deadline is not None and time.monotonic() >= deadline:
                            raise EvidenceError("source_budget_exceeded", "Arc extension collection exhausted its 90-second read budget.", source)
                        length += len(chunk)
                        if length > 20_000_000:
                            raise EvidenceError("source_too_large", "Source exceeded the bounded response size; nothing was truncated into success.", source)
                        chunks.append(chunk)
            except self.requests.RequestException as exc:
                raise EvidenceError("transport_failed", "The source transport failed; no response was accepted.", source) from exc
            try:
                payload = json.loads(b"".join(chunks))
            except (ValueError, UnicodeDecodeError) as exc:
                raise EvidenceError("invalid_response", "Source returned invalid JSON.", source) from exc
            if not isinstance(payload, dict):
                raise EvidenceError("invalid_response", "Source response must be an object.", source)
            return payload
        raise EvidenceError("api_failed", "Source retries were exhausted.", source)


def _validate_endpoint(method, url, body, config):
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except (ValueError, TypeError) as exc:
        raise EvidenceError("unsafe_endpoint", "Malformed source endpoint.", "http_client") from exc
    if (
        method not in ("GET", "POST") or parsed.scheme != "https"
        or parsed.username or parsed.password or parsed.fragment or port not in (None, 443)
        or len(url) > 24000 or "\\" in parsed.path
        or any(part in (".", "..") for part in unquote(parsed.path).split("/"))
    ):
        raise EvidenceError("unsafe_endpoint", "Only fixed public read-only Azure source endpoints are allowed.", "http_client")
    path = unquote(parsed.path).casefold()
    if parsed.netloc.casefold() == "management.azure.com":
        prefix = "/subscriptions/" + config["subscription_id"]
        if method == "POST":
            if (
                path != "/providers/microsoft.resourcegraph/resources"
                or not isinstance(body, dict) or body.get("subscriptions") != [config["subscription_id"]]
                or body.get("query") not in (_inventory_query(), _arc_extension_query())
                or parse_qsl(parsed.query) != [("api-version", ARG_VERSION)]
                or set(body) != {"subscriptions", "query", "options"}
                or not isinstance(body.get("options"), dict)
                or set(body["options"]) - {"$top", "resultFormat", "$skipToken"}
                or type(body["options"].get("$top")) is not int or body["options"]["$top"] != 1000
                or body["options"].get("resultFormat") != "objectArray"
                or "$skipToken" in body["options"] and (
                    not isinstance(body["options"]["$skipToken"], str) or not 1 <= len(body["options"]["$skipToken"]) <= 8192
                )
            ):
                raise EvidenceError("unsafe_endpoint", "ARM POST is allowed only for the fixed inventory/Arc extension metadata reads.", "http_client")
        elif not (
            path == prefix
            or path.startswith(prefix + "/resourcegroups/") and path.endswith((
                "/providers/microsoft.insights/metricdefinitions",
                "/providers/microsoft.insights/metrics",
            ))
            or path in (
                prefix + "/providers/microsoft.resourcehealth/availabilitystatuses",
                prefix + "/providers/microsoft.alertsmanagement/alerts",
            )
        ):
            raise EvidenceError("unsafe_endpoint", "ARM endpoint is outside the fixed read-only subscription scope.", "http_client")
        return ARM_ORIGIN + "/.default"
    if parsed.netloc.casefold() == "api.loganalytics.azure.com" and method == "POST" and not parsed.query:
        permitted = {"/v1/workspaces/" + workspace + "/query" for workspace in config["workspace_ids"]}
        if path in permitted and isinstance(body, dict) and set(body) == {"query", "timespan"}:
            return LOGS_AUDIENCE
    raise EvidenceError("unsafe_endpoint", "Log queries must target an explicitly configured workspace.", "http_client")


def _validate_subscription(client, config):
    payload = client.request("GET", ARM_ORIGIN + "/subscriptions/" + config["subscription_id"] + "?api-version=2022-12-01", "subscription")
    if (
        str(payload.get("subscriptionId", "")).casefold() != config["subscription_id"]
        or str(payload.get("tenantId", "")).casefold() != config["tenant_id"]
        or payload.get("state") != "Enabled"
    ):
        raise EvidenceError("subscription_scope_mismatch", "The subscription must be Enabled and match the configured tenant.", "subscription")


def _arg_pages(client, config, query, source, max_rows, max_pages, deadline=None):
    seen_tokens, seen_ids = set(), set()
    token, expected_total, returned = None, None, 0
    url = ARM_ORIGIN + "/providers/Microsoft.ResourceGraph/resources?api-version=" + ARG_VERSION
    for page_number in range(1, max_pages + 1):
        if deadline is not None and time.monotonic() >= deadline:
            raise EvidenceError("source_budget_exceeded", "Arc extension collection exhausted its 90-second read budget.", source)
        options = {"$top": 1000, "resultFormat": "objectArray"}
        if token is not None:
            options["$skipToken"] = token
        body = {"subscriptions": [config["subscription_id"]], "query": query, "options": options}
        payload = client.request("POST", url, source, body, **({"deadline": deadline} if deadline is not None else {}))
        if deadline is not None and time.monotonic() >= deadline:
            raise EvidenceError("source_budget_exceeded", "Arc extension collection exhausted its 90-second read budget.", source)
        page, count, total = payload.get("data"), payload.get("count"), payload.get("totalRecords")
        if (
            not isinstance(page, list) or any(not isinstance(row, dict) for row in page)
            or type(count) is not int or count != len(page) or type(total) is not int or total < 0
        ):
            raise EvidenceError("invalid_pagination", "Resource Graph returned invalid page counts or shape.", source)
        if expected_total is None:
            expected_total = total
        elif total != expected_total:
            raise EvidenceError("snapshot_changed", "Resource Graph declared total changed during paging; repeat the collection.", source)
        if source == "inventory" and total > max_rows:
            raise EvidenceError("scope_too_large", "Inventory exceeds 500 infrastructure resources; no partial inventory was accepted.", source)
        for row in page:
            row_id = _resource_id(row.get("id"), config["subscription_id"], source)
            if row_id in seen_ids:
                raise EvidenceError("invalid_pagination", "Resource Graph repeated a resource across pages.", source)
            seen_ids.add(row_id)
        returned += len(page)
        if returned > max_rows:
            raise EvidenceError("scope_too_large" if source == "inventory" else "source_too_large",
                                "Resource Graph exceeded the documented source row bound.", source)
        next_token = payload.get("$skipToken")
        truncated = str(payload.get("resultTruncated", "")).casefold()
        if truncated not in ("true", "false"):
            raise EvidenceError("invalid_pagination", "Resource Graph omitted a valid truncation flag.", source)
        if next_token is not None:
            if not isinstance(next_token, str) or not next_token or len(next_token) > 8192 or next_token in seen_tokens or not page or returned >= total:
                raise EvidenceError("invalid_pagination", "Resource Graph returned an invalid/repeated continuation token or count.", source)
            seen_tokens.add(next_token)
            token = next_token
            yield page, page_number, total, True
            if returned >= max_rows:
                raise EvidenceError("source_too_large", "Resource Graph reached the row bound with more records outstanding.", source)
            continue
        if truncated == "true" or returned != expected_total:
            raise EvidenceError("invalid_pagination", "Resource Graph ended before all declared resources were read.", source)
        yield page, page_number, total, False
        return
    raise EvidenceError("invalid_pagination", "Resource Graph exceeded the source page bound.", source)


def _arg_inventory(client, config):
    rows, pages = [], 0
    for page, pages, _, _ in _arg_pages(client, config, _inventory_query(), "inventory", MAX_RESOURCES, MAX_PAGES):
        rows.extend(page)
    return rows, pages


def _collect_arc_extensions(client, config, resources, reference):
    rows, pages, scanned, declared = [], 0, 0, None
    deadline = time.monotonic() + ARC_EXTENSION_BUDGET_SECONDS
    error = None
    try:
        for page, number, total, _ in _arg_pages(
            client, config, _arc_extension_query(), "arc_extensions",
            MAX_ARC_EXTENSION_ROWS, MAX_ARC_EXTENSION_PAGES, deadline,
        ):
            current = _normalize_arc_extensions(page, resources, config["subscription_id"], reference)
            rows.extend(current)
            pages, scanned, declared = number, scanned + len(page), total
    except EvidenceError as exc:
        error = exc
    status = "complete" if error is None else "partial" if pages or error.code in ("source_budget_exceeded", "source_too_large") else "error"
    receipt = _source(
        "arc_extensions", status, reference, len(rows), error=error,
        pages=pages, subscription_rows_read=scanned, declared_subscription_rows=declared,
        selected_machines=sum(row["resource_type"] == "microsoft.hybridcompute/machines" for row in resources),
        row_limit=MAX_ARC_EXTENSION_ROWS, page_limit=MAX_ARC_EXTENSION_PAGES,
        time_budget_seconds=ARC_EXTENSION_BUDGET_SECONDS,
        note="Point-in-time, permission-filtered ARG metadata; exact native parent IDs. Complete pages are retained on a later failure. "
             "Zero returned extensions is not proof of absence without approved visibility. No settings, protected settings, status messages or guest logs are read. "
             "Provisioning/version/auto-upgrade metadata is not proof of sensor health or update availability.",
    )
    return sorted(rows, key=lambda row: row["extension_id"]), receipt


def _next_link(link, initial_url, source):
    if not isinstance(link, str) or not link or len(link) > 24000:
        raise EvidenceError("invalid_pagination", "Source returned an invalid nextLink.", source)
    parsed, initial = urlsplit(link), urlsplit(initial_url)
    if (
        parsed.scheme != "https" or parsed.netloc.casefold() != "management.azure.com"
        or parsed.username or parsed.password or parsed.fragment
        or unquote(parsed.path).casefold() != unquote(initial.path).casefold()
        or "\\" in parsed.path or any(part in (".", "..") for part in unquote(parsed.path).split("/"))
    ):
        raise EvidenceError("invalid_pagination", "nextLink changed resource path or origin.", source)
    try:
        pairs = parse_qsl(parsed.query, keep_blank_values=True, strict_parsing=True)
    except ValueError as exc:
        raise EvidenceError("invalid_pagination", "nextLink has malformed query parameters.", source) from exc
    initial_pairs = dict(parse_qsl(initial.query))
    seen = set()
    for key, value in pairs:
        lower = key.casefold()
        if lower in seen:
            raise EvidenceError("invalid_pagination", "nextLink repeats a query parameter.", source)
        seen.add(lower)
        if lower in ("$skiptoken", "skiptoken", "$skip", "$top"):
            continue
        if key not in initial_pairs or value != initial_pairs[key]:
            raise EvidenceError("invalid_pagination", "nextLink changed source query scope.", source)
    if dict(pairs).get("api-version") != initial_pairs.get("api-version"):
        raise EvidenceError("invalid_pagination", "nextLink changed the source API version.", source)
    for key, value in initial_pairs.items():
        if key.casefold() not in ("$skiptoken", "skiptoken", "$skip", "$top") and dict(pairs).get(key) != value:
            raise EvidenceError("invalid_pagination", "nextLink omitted a source scope parameter.", source)
    return link


def _arm_list(client, url, source):
    rows, links, ids = [], set(), set()
    current = url
    for page_number in range(1, MAX_PAGES + 1):
        if current in links:
            raise EvidenceError("invalid_pagination", "Source repeated a page.", source)
        links.add(current)
        payload = client.request("GET", current, source)
        page = payload.get("value")
        if not isinstance(page, list) or any(not isinstance(row, dict) for row in page):
            raise EvidenceError("invalid_response", "Source list must contain an array of objects.", source)
        for row in page:
            row_id = row.get("id")
            if not isinstance(row_id, str) or not row_id or row_id.casefold() in ids:
                raise EvidenceError("invalid_pagination", "Source list omitted or repeated a native ID.", source)
            ids.add(row_id.casefold())
        rows.extend(page)
        if len(rows) > MAX_SOURCE_ROWS:
            raise EvidenceError("source_too_large", "Source exceeded the row bound; no truncated result was accepted.", source)
        link = payload.get("nextLink")
        if link is None:
            return rows, page_number
        if not page:
            raise EvidenceError("invalid_pagination", "Empty page advertised a continuation.", source)
        current = _next_link(link, url, source)
    raise EvidenceError("invalid_pagination", "Source exceeded the page bound.", source)


def _log_rows(payload, source):
    if payload.get("error") is not None:
        raise EvidenceError("partial_log_query", "Log Analytics returned an error/partial query; aggregates were not accepted as complete.", source)
    tables = payload.get("tables")
    if not isinstance(tables, list) or len(tables) != 1 or not isinstance(tables[0], dict):
        raise EvidenceError("invalid_log_result", "Expected one complete Log Analytics result table.", source)
    table = tables[0]
    columns, rows = table.get("columns"), table.get("rows")
    if (
        not isinstance(columns, list) or any(not isinstance(column, dict) or not isinstance(column.get("name"), str) for column in columns)
        or not isinstance(rows, list) or len(rows) > MAX_SOURCE_ROWS
    ):
        raise EvidenceError("invalid_log_result", "Log result shape or row count is outside the contract.", source)
    names = [column["name"] for column in columns]
    if len(set(names)) != len(names):
        raise EvidenceError("invalid_log_result", "Log result repeated a column name.", source)
    result = []
    for row in rows:
        if not isinstance(row, list) or len(row) != len(names):
            raise EvidenceError("invalid_log_result", "Log result has a ragged row.", source)
        result.append(dict(zip(names, row)))
    return result


def _series_id(resource_id, metric, source, dimensions, native_metric):
    identity = json.dumps([resource_id, metric, source, dimensions, native_metric], sort_keys=True)
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]


def _series(resource_id, metric, source, native_metric, unit, dimensions, window,
            points, semantics, count_basis, grain_seconds=None, bin_phase_seconds=0, count_is_value=False):
    seconds = grain_seconds or window["grain_seconds"]
    start, end = _time(window["start_utc"], source), _time(window["end_utc"], source)
    first_bin = int((start.timestamp() - bin_phase_seconds) // seconds) * seconds + bin_phase_seconds
    expected = math.ceil((end.timestamp() - first_bin) / seconds)
    seen = set()
    for point in points:
        if not isinstance(point, dict):
            raise EvidenceError("invalid_metric_bin", "Metric point must be an object.", source)
        timestamp = _time(point.get("time_utc"), source)
        epoch = timestamp.timestamp()
        if epoch % seconds != bin_phase_seconds or not first_bin <= epoch < end.timestamp() or epoch in seen:
            raise EvidenceError("invalid_metric_bin", "Metric bins are misaligned, duplicated or outside the requested window.", source)
        seen.add(epoch)
        if point.get("first_sample_utc") is not None or point.get("last_sample_utc") is not None:
            first_sample = _time(point.get("first_sample_utc"), source)
            last_sample = _time(point.get("last_sample_utc"), source)
            if not max(timestamp, start) <= first_sample <= last_sample < min(timestamp + timedelta(seconds=seconds), end):
                raise EvidenceError("invalid_sample_window", "Log sample timestamps fall outside their bin or query window.", source)
        for key in ("mean", "minimum", "maximum", "total", "count"):
            point[key] = _number(point.get(key), source, optional=True)
        if point["count"] is not None and (point["count"] < 0 or int(point["count"]) != point["count"]):
            raise EvidenceError("invalid_metric_count", "Source count must be a nonnegative integer.", source)
        point["edge_bin"] = epoch < start.timestamp() or epoch + seconds > end.timestamp()
    points = sorted(points, key=lambda point: point["time_utc"])
    observed = [point for point in points if any(point[key] is not None for key in ("mean", "minimum", "maximum", "total"))
                or count_is_value and point["count"] is not None]
    means = [point["mean"] for point in observed if point["mean"] is not None]
    maximums = [point["maximum"] for point in observed if point["maximum"] is not None]
    minimums = [point["minimum"] for point in observed if point["minimum"] is not None]
    counts = [point["count"] for point in observed]
    weighted = bool(observed) and count_basis == "log_observation_records" and all(count is not None and count > 0 for count in counts)
    if weighted and all(point["total"] is not None for point in observed):
        sample_count = sum(counts)
        mean = sum(point["total"] for point in observed) / sample_count
        mean_basis = "weighted mean of collected log observation records"
    else:
        sample_count = None
        mean = statistics.fmean(means) if means else None
        mean_basis = "equal-weight mean of returned Average bins" if means else "No Average values collected"
    last = observed[-1] if observed else None
    return {
        "series_id": _series_id(resource_id, metric, source, dimensions, native_metric),
        "resource_id": resource_id, "metric": metric, "label": METRIC_INFO[metric][0],
        "unit": unit, "source": source, "native_metric": native_metric,
        "dimensions": dimensions, "semantics": semantics, "count_basis": count_basis, "count_is_value": count_is_value,
        "grain_seconds": seconds, "window": {"start_utc": window["start_utc"], "end_utc": window["end_utc"]},
        "bin_phase_seconds": bin_phase_seconds,
        "points": points,
        "summary": {
            "expected_bins": expected, "observed_bins": len(observed),
            "missing_bins": expected - len(observed), "sample_count": sample_count,
            "mean": mean, "mean_basis": mean_basis,
            "maximum_observation": max(maximums) if maximums else None,
            "minimum_observation": min(minimums) if minimums else None,
            "maximum_bin_mean": max(means) if means else None,
            "last_bin_utc": last["time_utc"] if last else None,
            "last_sample_utc": last.get("last_sample_utc") if last else None,
            "last_value": next((last[key] for key in ("mean", "total", "maximum", "minimum", "count")
                                if last[key] is not None and (key != "count" or count_is_value)), None) if last else None,
            "total": sum(point["total"] for point in observed if point["total"] is not None) if observed and all(point["total"] is not None for point in observed) else None,
            "total_basis": "sum of recorded log values, not integrated utilization" if count_basis == "log_observation_records" else "sum of returned Total aggregation bins",
            "count_aggregation_total": sum(counts) if count_is_value and observed and all(value is not None for value in counts) else None,
            "edge_bins": sum(point["edge_bin"] for point in points),
        },
    }


def _log_query(table, resource_ids, window):
    if table not in ("Heartbeat", "Perf", "InsightsMetrics"):
        raise EvidenceError("unsupported_source", "Only fixed infrastructure log templates are supported.", "logs")
    scope = json.dumps(sorted(resource_ids), separators=(",", ":"))
    prefix = (
        "let scope_ids = dynamic(" + scope + "); " + table
        + " | where TimeGenerated >= datetime(" + window["start_utc"] + ")"
        + " and TimeGenerated < datetime(" + window["end_utc"] + ")"
        + " | where tolower(_ResourceId) in (scope_ids)"
    )
    if table == "Heartbeat":
        return (
            prefix + " | summarize count=count(), first_sample_utc=min(TimeGenerated),"
            " last_sample_utc=max(TimeGenerated), os_types=make_set(OSType, 4)"
            " by resource_id=tolower(_ResourceId)"
            " | order by resource_id asc | take 50001"
        )
    grain = str(window["grain_seconds"]) + "s"
    if table == "Perf":
        return (
            prefix
            + " | where (ObjectName in~ ('Processor', 'Processor Information')"
            " and CounterName == '% Processor Time' and InstanceName == '_Total')"
            " or (ObjectName =~ 'Memory' and CounterName in"
            " ('% Used Memory', '% Available Memory', '% Committed Bytes In Use',"
            " 'Available MBytes', 'Available Bytes'))"
            " or (ObjectName in~ ('LogicalDisk', 'Logical Disk')"
            " and CounterName == '% Free Space' and InstanceName != '_Total')"
            " | summarize mean=avg(CounterValue), minimum=min(CounterValue),"
            " maximum=max(CounterValue), total=sum(CounterValue), count=count(),"
            " first_sample_utc=min(TimeGenerated), last_sample_utc=max(TimeGenerated)"
            " by resource_id=tolower(_ResourceId), object=ObjectName, name=CounterName,"
            " instance=InstanceName, time_utc=bin(TimeGenerated, " + grain + ")"
            " | order by resource_id asc, time_utc asc | take 50001"
        )
    return (
        prefix
        + " | where Origin == 'vm.azm.ms'"
        " | where (Namespace == 'Processor' and Name == 'UtilizationPercentage')"
        " or (Namespace == 'Memory' and Name == 'AvailableMB')"
        " or (Namespace == 'LogicalDisk' and Name == 'FreeSpacePercentage')"
        " | summarize mean=avg(Val), minimum=min(Val), maximum=max(Val),"
        " total=sum(Val), count=count(), first_sample_utc=min(TimeGenerated),"
        " last_sample_utc=max(TimeGenerated)"
        " by resource_id=tolower(_ResourceId), namespace=Namespace, name=Name,"
        " tags=tostring(Tags), time_utc=bin(TimeGenerated, " + grain + ")"
        " | order by resource_id asc, time_utc asc | take 50001"
    )


def _query_logs(client, workspace_id, table, resource_ids, window):
    url = LOGS_ORIGIN + "/v1/workspaces/" + workspace_id + "/query"
    payload = client.request("POST", url, table, {
        "query": _log_query(table, resource_ids, window),
        "timespan": window["start_utc"] + "/" + window["end_utc"],
    })
    return _log_rows(payload, table)


def _log_point(row, source, factor=1.0):
    count = _number(row.get("count"), source)
    if count <= 0 or int(count) != count:
        raise EvidenceError("invalid_metric_count", "Aggregated log bins require a positive observation count.", source)
    point = {
        "time_utc": _iso(_time(row.get("time_utc"), source)),
        "count": int(count),
        "first_sample_utc": row.get("first_sample_utc"),
        "last_sample_utc": row.get("last_sample_utc"),
    }
    first = _time(point["first_sample_utc"], source)
    last = _time(point["last_sample_utc"], source)
    if first > last:
        raise EvidenceError("invalid_metric_timestamp", "Log sample timestamps are reversed.", source)
    for key in ("mean", "minimum", "maximum", "total"):
        point[key] = _number(row.get(key), source) * factor
    if point["minimum"] > point["maximum"] or not point["minimum"] - 1e-9 <= point["mean"] <= point["maximum"] + 1e-9:
        raise EvidenceError("invalid_metric_aggregate", "Log aggregates have inconsistent min/mean/max.", source)
    if not math.isclose(point["total"], point["mean"] * count, rel_tol=1e-7, abs_tol=1e-7):
        raise EvidenceError("invalid_metric_aggregate", "Log sum/count is inconsistent with its average.", source)
    return point


def _numeric_tag(value, name, source):
    if isinstance(value, str) and re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", value):
        value = float(value)
    result = _number(value, source)
    if result <= 0:
        raise EvidenceError("invalid_metric_tag", f"{name} must be a positive source-reported capacity.", source)
    return result


def _metric_tags(value, source):
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError as exc:
            raise EvidenceError("invalid_metric_tags", "InsightsMetrics Tags is not valid JSON.", source) from exc
    if not isinstance(value, dict):
        raise EvidenceError("invalid_metric_tags", "InsightsMetrics Tags must be a JSON object.", source)
    return value


def _normalize_guest(rows, table, workspace_id, resources, window):
    source = table + ":" + workspace_id
    known = {resource["resource_id"] for resource in resources}
    groups, notes = {}, []
    for row in rows:
        resource_id = row.get("resource_id")
        if not isinstance(resource_id, str) or resource_id.casefold() not in known:
            raise EvidenceError("unmatched_log_resource", "Log query returned a resource outside its exact-ID scope.", source)
        resource_id = resource_id.casefold()
        if table == "Perf":
            native = row.get("name")
            mappings = {
                "% Processor Time": ("cpu_percent", "Percent", 1.0, "Guest total processor CounterValue observations; not an application CPU metric."),
                "% Used Memory": ("memory_used_percent", "Percent", 1.0, "Guest used-memory counter; provider memory accounting may include/exclude cache."),
                "% Available Memory": ("memory_available_percent", "Percent", 1.0, "Guest available physical memory counter."),
                "% Committed Bytes In Use": ("memory_commit_percent", "Percent", 1.0, "Windows committed bytes relative to the commit limit; not physical RAM usage."),
                "Available MBytes": ("memory_available_bytes", "Bytes", 1048576.0, "Guest available memory MBytes converted to bytes (1024 squared)."),
                "Available Bytes": ("memory_available_bytes", "Bytes", 1.0, "Guest available physical memory bytes."),
                "% Free Space": ("disk_free_percent", "Percent", 1.0, "Free space on this guest logical volume; not Azure disk IOPS/bandwidth headroom."),
            }
            if native not in mappings:
                raise EvidenceError("unexpected_guest_metric", "Perf returned a counter outside the fixed template.", source)
            metric, unit, factor, semantics = mappings[native]
            dimensions = {"object": row.get("object"), "instance": row.get("instance")}
            variants = [(metric, unit, factor, semantics, dimensions)]
        else:
            namespace, native = row.get("namespace"), row.get("name")
            tags = _metric_tags(row.get("tags"), source)
            dimensions = tags
            if (namespace, native) == ("Processor", "UtilizationPercentage"):
                variants = [("cpu_percent", "Percent", 1.0, "VM Insights guest total CPU utilization; origin vm.azm.ms.", dimensions)]
            elif (namespace, native) == ("Memory", "AvailableMB"):
                variants = [("memory_available_bytes", "Bytes", 1048576.0, "VM Insights available physical memory MB converted to bytes (1024 squared).", dimensions)]
                size = tags.get("vm.azm.ms/memorySizeMB")
                if size is not None:
                    capacity = _numeric_tag(size, "memorySizeMB", source)
                    variants.append(("memory_available_percent", "Percent", 100.0 / capacity, "Derived from real AvailableMB / source memorySizeMB; not committed-memory percentage.", dimensions))
                else:
                    notes.append({"resource_id": resource_id, "code": "memory_capacity_not_supplied", "note": "Available bytes were collected; no physical-memory percentage was inferred without memorySizeMB."})
            elif (namespace, native) == ("LogicalDisk", "FreeSpacePercentage"):
                variants = [("disk_free_percent", "Percent", 1.0, "VM Insights free space on the source-tagged guest logical disk.", dimensions)]
            else:
                raise EvidenceError("unexpected_guest_metric", "InsightsMetrics returned a metric outside the fixed vm.azm.ms template.", source)
            native = str(namespace) + "/" + str(native)
        for metric, unit, factor, semantics, dimensions in variants:
            identity = _series_id(resource_id, metric, source, dimensions, native)
            if identity not in groups:
                groups[identity] = {
                    "resource_id": resource_id, "metric": metric, "native": native,
                    "unit": unit, "dimensions": dimensions, "semantics": semantics, "points": [],
                }
            groups[identity]["points"].append(_log_point(row, source, factor))
    series = [
        _series(group["resource_id"], group["metric"], source, group["native"], group["unit"],
                group["dimensions"], window, group["points"], group["semantics"], "log_observation_records")
        for group in groups.values()
    ]
    return series, notes


def _normalize_heartbeat(rows, workspace_id, resources, window):
    known = {resource["resource_id"]: resource for resource in resources}
    source = "Heartbeat:" + workspace_id
    end = _time(window["end_utc"], source)
    normalized = []
    for row in rows:
        resource_id = row.get("resource_id")
        if not isinstance(resource_id, str) or resource_id.casefold() not in known:
            raise EvidenceError("unmatched_log_resource", "Heartbeat returned an out-of-scope resource.", source)
        resource_id = resource_id.casefold()
        first, last = _time(row.get("first_sample_utc"), source), _time(row.get("last_sample_utc"), source)
        if not _time(window["start_utc"], source) <= first <= last < end:
            raise EvidenceError("invalid_heartbeat", "Heartbeat sample times are outside the query window.", source)
        count = _number(row.get("count"), source)
        if count <= 0 or int(count) != count:
            raise EvidenceError("invalid_heartbeat", "Heartbeat count must be a positive integer.", source)
        normalized.append({
            "resource_id": resource_id, "source": source, "count": int(count),
            "first_sample_utc": row["first_sample_utc"], "last_sample_utc": row["last_sample_utc"],
            "age_at_window_end_minutes": (end - last).total_seconds() / 60,
            "qualification": "Agent telemetry recency, not application health; evaluated at the requested window end.",
        })
    return normalized


def _duration_seconds(value, source):
    if not isinstance(value, str):
        raise EvidenceError("invalid_interval", "Source omitted its ISO 8601 metric interval.", source)
    match = re.fullmatch(r"P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?", value)
    if not match or not any(match.groups()):
        raise EvidenceError("invalid_interval", "Only whole-second/day metric intervals are supported.", source)
    days, hours, minutes, seconds = (int(part or 0) for part in match.groups())
    result = days * 86400 + hours * 3600 + minutes * 60 + seconds
    if not 60 <= result <= 86400:
        raise EvidenceError("invalid_interval", "Metric interval must be between one minute and one day.", source)
    return result


def _metric_specs(payload, resource, window, metric_filter):
    definitions = payload.get("value")
    if not isinstance(definitions, list) or any(not isinstance(row, dict) for row in definitions) or len(definitions) > 2000:
        raise EvidenceError("invalid_metric_definitions", "metricDefinitions must be a bounded array of objects.", "metric_definitions")
    by_name = {}
    for row in definitions:
        name = row.get("name")
        if not isinstance(name, dict) or not isinstance(name.get("value"), str):
            raise EvidenceError("invalid_metric_definitions", "Metric definition omitted its native name.", "metric_definitions")
        key = name["value"].casefold()
        if str(row.get("resourceId", "")).casefold() != resource["resource_id"]:
            raise EvidenceError("metric_definition_scope_mismatch", "Metric definition belongs to a different native resource.", "metric_definitions")
        if key in by_name:
            raise EvidenceError("invalid_metric_definitions", "Metric definitions repeated a native name.", "metric_definitions")
        by_name[key] = row
    specs, absent = [], []
    for native_name, metric in PLATFORM_METRICS.get(resource["resource_type"], ()):
        if metric_filter != "all" and metric != metric_filter:
            continue
        definition = by_name.get(native_name.casefold())
        if definition is None:
            absent.append({"metric": metric, "native_metric": native_name, "reason": "Not exposed by this resource's metricDefinitions."})
            continue
        aggregations = definition.get("supportedAggregationTypes")
        if aggregations is None:
            primary = definition.get("primaryAggregationType")
            aggregations = [primary] if primary is not None else []
        if not isinstance(aggregations, list) or any(not isinstance(value, str) for value in aggregations):
            raise EvidenceError("invalid_metric_definitions", "Metric aggregations must be an array.", "metric_definitions")
        primary = definition.get("primaryAggregationType")
        selected = (
            [value for value in ("Average", "Minimum", "Maximum") if value in aggregations]
            if primary == "Average" else [primary] if primary in ("Total", "Count", "Minimum", "Maximum") and primary in aggregations else []
        )
        if not selected:
            absent.append({"metric": metric, "native_metric": native_name, "reason": "No supported numeric aggregation."})
            continue
        availabilities = definition.get("metricAvailabilities")
        if not isinstance(availabilities, list) or not availabilities or any(not isinstance(row, dict) for row in availabilities):
            raise EvidenceError("invalid_metric_definitions", "Metric definition omitted time-grain availability.", "metric_definitions")
        grains = sorted(
            [(_duration_seconds(row.get("timeGrain"), "metric_definitions"), row["timeGrain"])
             for row in availabilities],
            key=lambda pair: pair[0],
        )
        usable = [pair for pair in grains if pair[0] >= window["grain_seconds"]]
        if not usable:
            absent.append({"metric": metric, "native_metric": native_name, "reason": "No advertised time grain fits this bounded window; not guessed."})
            continue
        seconds, interval = usable[0]
        dims = definition.get("dimensions") if definition.get("dimensions") is not None else []
        if not isinstance(dims, list):
            raise EvidenceError("invalid_metric_definitions", "Metric dimensions must be an array.", "metric_definitions")
        names = []
        for dimension in dims:
            name = dimension.get("value") if isinstance(dimension, dict) else None
            if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_./-]{0,127}", name):
                raise EvidenceError("invalid_metric_definitions", "Metric dimension name is not a safe native identifier.", "metric_definitions")
            names.append(name)
        namespace = definition.get("namespace") or resource["resource_type"]
        if not isinstance(namespace, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)+", namespace):
            raise EvidenceError("invalid_metric_definitions", "Metric namespace is not a native provider/type.", "metric_definitions")
        unit = definition.get("unit")
        if not isinstance(unit, str) or not unit:
            raise EvidenceError("invalid_metric_definitions", "Metric definition omitted its unit.", "metric_definitions")
        specs.append({
            "native_name": definition["name"]["value"], "metric": metric, "unit": unit,
            "aggregations": tuple(selected),
            "dimension_names": tuple(sorted(names)) if definition.get("isDimensionRequired") is True else (),
            "available_dimensions": names,
            "namespace": namespace, "interval": interval, "grain_seconds": seconds,
            "source_description": definition.get("displayDescription"),
            "primary_aggregation": primary,
        })
    return specs, absent


def _platform_url(resource, specs, window):
    spec = specs[0]
    seconds = spec["grain_seconds"]
    first = int(_time(window["start_utc"], "metrics").timestamp()) // seconds * seconds
    query = {
        "api-version": METRICS_VERSION,
        "timespan": _iso(datetime.fromtimestamp(first, UTC)) + "/" + window["end_utc"],
        "interval": spec["interval"],
        "metricnames": ",".join(item["native_name"] for item in specs),
        "aggregation": ",".join(spec["aggregations"]),
        "metricnamespace": spec["namespace"],
        "AutoAdjustTimegrain": "false", "ValidateDimensions": "true",
    }
    if spec["dimension_names"]:
        query["$filter"] = " and ".join(name + " eq '*'" for name in spec["dimension_names"])
        query["top"] = "1000"
    return (
        ARM_ORIGIN + quote(resource["resource_id"], safe="/")
        + "/providers/Microsoft.Insights/metrics?" + urlencode(query)
    )


def _normalize_platform(payload, resource, specs, window):
    source = "platform_metrics"
    records = payload.get("value")
    if not isinstance(records, list) or any(not isinstance(record, dict) for record in records):
        raise EvidenceError("invalid_metric_response", "Metrics response must contain an array of native metrics.", source)
    actual_grain = _duration_seconds(payload.get("interval"), source)
    if actual_grain != specs[0]["grain_seconds"]:
        raise EvidenceError("unexpected_metric_grain", "API changed the requested metric grain; no silent adjustment was accepted.", source)
    expected = {spec["native_name"].casefold(): spec for spec in specs}
    returned, normalized = set(), []
    for record in records:
        name = record.get("name")
        native_name = name.get("value") if isinstance(name, dict) else None
        if not isinstance(native_name, str) or native_name.casefold() not in expected or native_name.casefold() in returned:
            raise EvidenceError("unexpected_metric", "API omitted/repeated the native metric identity or returned an unrequested metric.", source)
        returned.add(native_name.casefold())
        spec = expected[native_name.casefold()]
        record_id = record.get("id")
        expected_prefix = resource["resource_id"] + "/providers/microsoft.insights/metrics/"
        if not isinstance(record_id, str) or not record_id.casefold().startswith(expected_prefix):
            raise EvidenceError("metric_scope_mismatch", "Metric values belong to a different native resource.", source)
        if record.get("errorCode", "Success") != "Success":
            raise EvidenceError("metric_query_failed", "A native metric reported an error despite HTTP 200.", source)
        if record.get("unit") != spec["unit"]:
            raise EvidenceError("metric_unit_mismatch", "Metric definition and metric values disagree on units.", source)
        traces = record.get("timeseries")
        if not isinstance(traces, list) or len(traces) >= 1000:
            raise EvidenceError("metric_dimension_bound", "Metric dimension result is missing or reached the top bound; completeness is not assumed.", source)
        for trace in traces:
            if not isinstance(trace, dict) or not isinstance(trace.get("data"), list):
                raise EvidenceError("invalid_metric_response", "Native time series must contain an array of points.", source)
            if len(trace["data"]) > MAX_BINS:
                raise EvidenceError("metric_bin_bound", "Native metric exceeded 800 bins; select a coarser advertised grain.", source)
            dimensions = {}
            metadata = trace.get("metadatavalues", trace.get("metadataValues", []))
            if not isinstance(metadata, list):
                raise EvidenceError("invalid_metric_dimensions", "Metric metadata must be an array.", source)
            for item in metadata:
                name = item.get("name") if isinstance(item, dict) else None
                key = name.get("value") if isinstance(name, dict) else None
                value = item.get("value") if isinstance(item, dict) else None
                if not isinstance(key, str) or not isinstance(value, str) or key in dimensions:
                    raise EvidenceError("invalid_metric_dimensions", "Metric dimensions omitted or repeated an identity.", source)
                dimensions[key] = value
            points = []
            for value in trace["data"]:
                if not isinstance(value, dict):
                    raise EvidenceError("invalid_metric_response", "Metric point must be an object.", source)
                points.append({
                    "time_utc": _iso(_time(value.get("timeStamp"), source)),
                    "mean": value.get("average"), "minimum": value.get("minimum"),
                    "maximum": value.get("maximum"), "total": value.get("total"), "count": value.get("count"),
                })
            metric = spec["metric"]
            semantics = (
                "Azure platform/service metric " + native_name + "; not a guest/application health guarantee. "
                "Returned dimension series remain separate; optional dimensions are aggregated unless required. "
                "Empty bins are missing, not zero. "
                "Platform edge bins may include observations before the exact requested start."
            )
            if metric in ("container_cpu_cores", "app_cpu_time_seconds", "app_memory_bytes"):
                semantics += " Absolute usage, not percent of an inferred host capacity."
            if metric in ("container_cpu_percent", "container_memory_percent"):
                semantics += " Percentage relative to configured container limits, not guest/host physical RAM."
            if metric in ("plan_cpu_percent", "plan_memory_percent"):
                semantics += " App Service plan aggregation across instances, not a single app's CPU/RAM."
            if metric.startswith("node_"):
                semantics += " AKS cluster-aggregated node observations unless returned metadata identifies a narrower dimension; not separate ARM VMs."
            phase = int(_time(points[0]["time_utc"], source).timestamp()) % actual_grain if points else 0
            series = _series(resource["resource_id"], metric, source, native_name, spec["unit"],
                             dimensions, window, points, semantics, "native_metric_Count", actual_grain, phase,
                             spec["primary_aggregation"] == "Count")
            series.update(namespace=spec["namespace"], requested_aggregations=list(spec["aggregations"]),
                          available_dimensions=spec["available_dimensions"], source_description=spec["source_description"],
                          primary_aggregation=spec["primary_aggregation"])
            normalized.append(series)
    if returned != set(expected):
        raise EvidenceError("missing_metric_response", "API omitted a requested native metric; the group is not complete.", source)
    return normalized


def _collect_platform(client, resource, params, reference):
    sources, series = [], []
    if resource["resource_type"] not in PLATFORM_METRICS:
        return [], [_source("platform_metrics", "not_supported", reference, resource_id=resource["resource_id"],
                            note="Arc guest metrics come from configured log workspaces; no Azure host CPU/memory endpoint is assumed.")]
    definitions_url = (
        ARM_ORIGIN + quote(resource["resource_id"], safe="/")
        + "/providers/Microsoft.Insights/metricDefinitions?api-version=" + DEFINITIONS_VERSION
    )
    try:
        payload = client.request("GET", definitions_url, "metric_definitions")
        specs, absent = _metric_specs(payload, resource, params["window"], params["metric"])
    except EvidenceError as exc:
        return [], [_source("metric_definitions", "error", reference, resource_id=resource["resource_id"], error=exc,
                            note="Metric availability is unknown; no source-shaped default measurements were created.")]
    sources.append(_source("metric_definitions", "complete", reference, len(payload["value"]),
                           resource_id=resource["resource_id"], requested_metrics=len(specs), not_exposed=absent))
    groups = {}
    for spec in specs:
        key = (spec["namespace"], spec["interval"], spec["aggregations"], spec["dimension_names"])
        groups.setdefault(key, []).append(spec)
    for group in groups.values():
        try:
            payload = client.request("GET", _platform_url(resource, group, params["window"]), "platform_metrics")
            current = _normalize_platform(payload, resource, group, params["window"])
            series.extend(current)
            observations = sum(row["summary"]["observed_bins"] for row in current)
            sources.append(_source("platform_metrics", "complete" if observations else "not_collected", reference,
                                   observations, resource_id=resource["resource_id"],
                                   native_metrics=[spec["native_name"] for spec in group],
                                   grain_seconds=group[0]["grain_seconds"],
                                   note="Request completed; telemetry coverage and supported units are separate from resource health."))
        except EvidenceError as exc:
            sources.append(_source("platform_metrics", "error", reference, resource_id=resource["resource_id"], error=exc,
                                   native_metrics=[spec["native_name"] for spec in group],
                                   note="Other metric groups remain independent; this group did not yield accepted evidence."))
    if not specs:
        sources.append(_source("platform_metrics", "not_collected", reference, resource_id=resource["resource_id"],
                               note="No selected, semantically applicable metrics were exposed at a safe advertised grain."))
    return series, sources


def _normalize_health(rows, resources, window, reference):
    known = {resource["resource_id"] for resource in resources}
    health, events = {}, []
    marker = "/providers/microsoft.resourcehealth/availabilitystatuses/"
    start, end = _time(window["start_utc"], "resource_health"), _time(window["end_utc"], "resource_health")
    for row in rows:
        native_id = row.get("id")
        if not isinstance(native_id, str) or marker not in native_id.casefold():
            raise EvidenceError("invalid_resource_health", "Resource Health omitted its scoped availability-status ID.", "resource_health")
        resource_id = native_id.casefold().split(marker, 1)[0]
        if resource_id not in known:
            continue
        props = row.get("properties")
        if not isinstance(props, dict):
            raise EvidenceError("invalid_resource_health", "Resource Health properties must be an object.", "resource_health")
        state = props.get("availabilityState")
        if state not in ("Available", "Unavailable", "Degraded", "Unknown", None):
            raise EvidenceError("invalid_resource_health", "Resource Health returned an unrecognized native availability state.", "resource_health")
        if resource_id in health:
            raise EvidenceError("duplicate_resource_health", "Resource Health repeated a current status.", "resource_health")
        health[resource_id] = {
            "availability_state": state or "Unknown", "summary": props.get("summary"), "title": props.get("title"),
            "reported_utc": props.get("reportedTime"), "changed_utc": props.get("occuredTime"),
            "reason_type": props.get("reasonType"), "context": props.get("context"),
            "collected_utc": _iso(reference),
            "qualification": "Current Azure platform availability at collection, not reconstructed monthly guest/application health.",
        }
        resolved = props.get("recentlyResolved")
        if resolved is not None:
            if not isinstance(resolved, dict):
                raise EvidenceError("invalid_resource_health", "recentlyResolved must be a native object.", "resource_health")
            for timestamp, kind, title in (
                (resolved.get("unavailableOccuredTime"), "health_unavailable", "Platform availability became unavailable"),
                (resolved.get("resolvedTime"), "health_resolved", "Platform availability resolved"),
            ):
                if timestamp is None:
                    continue
                instant = _time(timestamp, "resource_health")
                if start <= instant < end:
                    events.append({
                        "event_id": _series_id(resource_id, kind, "resource_health", {}, timestamp),
                        "resource_id": resource_id, "source": "resource_health", "kind": kind,
                        "time_utc": timestamp, "title": title,
                        "details": resolved.get("unavailableSummary"), "severity": "info",
                        "state": "observed", "qualification": "Native recentlyResolved annotation, not a complete incident history.",
                    })
    return health, events


def _normalize_alerts(rows, resources, window):
    known = {resource["resource_id"] for resource in resources}
    alerts, events = [], []
    start, end = _time(window["start_utc"], "monitor_alerts"), _time(window["end_utc"], "monitor_alerts")
    for row in rows:
        props = row.get("properties")
        essentials = props.get("essentials") if isinstance(props, dict) else None
        if not isinstance(essentials, dict):
            raise EvidenceError("invalid_alert", "Monitor alert omitted native essentials.", "monitor_alerts")
        target = essentials.get("targetResource")
        if not isinstance(target, str):
            raise EvidenceError("invalid_alert", "Monitor alert omitted its target resource ID.", "monitor_alerts")
        resource_id = target.casefold().rstrip("/")
        if resource_id not in known:
            continue
        severity, condition = essentials.get("severity"), essentials.get("monitorCondition")
        if severity not in ("Sev0", "Sev1", "Sev2", "Sev3", "Sev4") or condition not in ("Fired", "Resolved"):
            raise EvidenceError("invalid_alert", "Monitor alert severity or condition is not recognized.", "monitor_alerts")
        native_id = row.get("id")
        if not isinstance(native_id, str) or not native_id:
            raise EvidenceError("invalid_alert", "Monitor alert omitted its native ID.", "monitor_alerts")
        fired = _time(essentials.get("startDateTime"), "monitor_alerts")
        level = "critical" if severity in ("Sev0", "Sev1") else "warning" if severity == "Sev2" else "info"
        alert = {
            "alert_id": native_id, "resource_id": resource_id,
            "title": essentials.get("alertRule") or row.get("name"),
            "native_severity": severity, "severity": level,
            "monitor_condition": condition, "alert_state": essentials.get("alertState"),
            "fired_utc": essentials["startDateTime"],
            "last_modified_utc": essentials.get("lastModifiedDateTime"),
            "resolved_utc": essentials.get("monitorConditionResolvedDateTime"),
            "monitor_service": essentials.get("monitorService"),
            "source": "monitor_alerts",
            "qualification": "Native alert observation; this record alone does not prove SRE Agent routing or mitigation.",
        }
        alerts.append(alert)
        if start <= fired < end:
            events.append({
                "event_id": _series_id(resource_id, "alert_fired", "monitor_alerts", {}, native_id),
                "resource_id": resource_id, "source": "monitor_alerts", "kind": "alert_fired",
                "time_utc": alert["fired_utc"], "title": alert["title"], "severity": level,
                "state": "review" if condition == "Fired" else "observed",
                "alert_id": native_id, "current_condition": condition,
                "details": "Native " + severity + " alert fired; current monitor condition is " + condition + ".",
            })
        if alert["resolved_utc"] is not None:
            resolved = _time(alert["resolved_utc"], "monitor_alerts")
            if start <= resolved < end:
                events.append({
                    "event_id": _series_id(resource_id, "alert_resolved", "monitor_alerts", {}, native_id),
                    "resource_id": resource_id, "source": "monitor_alerts", "kind": "alert_resolved",
                    "time_utc": alert["resolved_utc"], "title": alert["title"], "severity": "info",
                    "state": "observed", "alert_id": native_id,
                    "details": "Native monitor-condition resolution timestamp; not proof of the recovery cause.",
                })
    return alerts, events


def _threshold(metric):
    if metric in ("cpu_percent", "node_cpu_percent", "node_disk_percent", "container_cpu_percent",
                  "plan_cpu_percent", "disk_iops_percent", "disk_bandwidth_percent", "sql_cpu_percent", "sql_storage_percent"):
        return POLICY["high_utilization_percent"], "at_or_above"
    if metric == "memory_available_percent":
        return POLICY["low_memory_available_percent"], "at_or_below"
    if metric in ("memory_used_percent", "memory_commit_percent", "node_memory_percent",
                  "container_memory_percent", "plan_memory_percent"):
        return POLICY["high_memory_used_percent"], "at_or_above"
    if metric == "disk_free_percent":
        return POLICY["low_disk_free_percent"], "at_or_below"
    if metric == "service_availability_percent":
        return POLICY["service_availability_below_percent"], "below"
    if metric == "vm_availability":
        return 1.0, "below"
    return None, None


def _over_threshold(value, threshold, direction):
    if direction == "at_or_above":
        return value >= threshold
    if direction == "at_or_below":
        return value <= threshold
    return value < threshold


def _signal(resource_id, kind, time_utc, severity, state, title, details, evidence,
            source, series_id=None, metric=None, end_utc=None):
    identity = [resource_id, series_id, kind, source, time_utc, evidence]
    return {
        "signal_id": hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16],
        "resource_id": resource_id, "kind": kind, "time_utc": time_utc,
        "end_utc": end_utc, "severity": severity, "state": state,
        "title": title, "details": details, "evidence": evidence, "source": source,
        "series_id": series_id, "metric": metric,
    }


def _metric_signals(series):
    result = []
    for item in series:
        mount = item["dimensions"].get("vm.azm.ms/mountId")
        package_image = (
            item["metric"] == "disk_free_percent"
            and item["source"].startswith("InsightsMetrics:")
            and item["native_metric"] == "LogicalDisk/FreeSpacePercentage"
            and isinstance(mount, str)
            and re.fullmatch(POLICY["package_image_mount_pattern"], mount) is not None
        )
        if package_image:
            if item["summary"]["observed_bins"]:
                result.append(_signal(
                    item["resource_id"], "package_image_capacity", item["summary"]["last_bin_utc"], "info", "observed",
                    "Package-image volume: validate writable capacity separately",
                    "The source mount ID matches the canonical /snap/package/numeric-revision image pattern. "
                    "Its free-space series remains collected/exportable, but is excluded from local writable-capacity "
                    "threshold/anomaly flags. Mount flags and writability were not collected; this is not a full system disk diagnosis.",
                    {"mount_id": mount, "writability": "not_verified",
                     "excluded_from_writable_capacity_pressure": True,
                     "observed_mean_free_percent": item["summary"]["mean"],
                     "observed_bins": item["summary"]["observed_bins"]},
                    item["source"], item["series_id"], item["metric"],
                ))
            continue
        if item["metric"] in ("cpu_percent", "node_cpu_percent", "container_cpu_percent", "plan_cpu_percent", "sql_cpu_percent"):
            peaks = [point for point in item["points"] if point["maximum"] is not None
                     and not point["edge_bin"] and point["maximum"] >= POLICY["high_cpu_peak_percent"]]
            if peaks:
                result.append(_signal(
                    item["resource_id"], "cpu_peak", peaks[0]["time_utc"], "info", "observed",
                    "Source CPU maximum reached the peak review marker",
                    "At least one source-reported maximum crossed 95%. These are bin observations, not raw p95 or exact peak timestamps. "
                    "A short peak is not automatically sustained pressure or a native alert.",
                    {"threshold_percent": POLICY["high_cpu_peak_percent"], "peak_bins": len(peaks),
                     "maximum_source_observation": max(point["maximum"] for point in peaks),
                     "grain_seconds": item["grain_seconds"]},
                    item["source"], item["series_id"], item["metric"], peaks[-1]["time_utc"],
                ))
        threshold, direction = _threshold(item["metric"])
        if threshold is None:
            continue
        seconds, run = item["grain_seconds"], []

        def finish_run():
            if len(run) >= POLICY["sustained_bins"]:
                result.append(_signal(
                    item["resource_id"], "sustained_pressure", run[0]["time_utc"], "warning", "review",
                    item["label"] + " crossed the review threshold",
                    "Consecutive complete bin averages crossed a documented review threshold. "
                    "This is a local rule, not an Azure Monitor alert or a root-cause diagnosis.",
                    {"threshold": threshold, "direction": direction, "consecutive_bins": len(run),
                     "grain_seconds": seconds, "bin_means_min": min(point["mean"] for point in run),
                     "bin_means_max": max(point["mean"] for point in run)},
                    item["source"], item["series_id"], item["metric"], run[-1]["time_utc"],
                ))

        for point in item["points"]:
            qualifying = point["mean"] is not None and not point["edge_bin"] and _over_threshold(point["mean"], threshold, direction)
            adjacent = not run or (_time(point["time_utc"], "analysis") - _time(run[-1]["time_utc"], "analysis")).total_seconds() == seconds
            if not qualifying or not adjacent:
                finish_run()
                run = []
            if qualifying:
                run.append(point)
        finish_run()
        if item["unit"].casefold() != "percent" or item["metric"] == "memory_commit_percent":
            continue
        observations = [point for point in item["points"] if point["mean"] is not None and not point["edge_bin"]]
        for index, point in enumerate(observations):
            instant = _time(point["time_utc"], "analysis")
            earliest = instant - timedelta(seconds=seconds * POLICY["anomaly_baseline_bins"])
            prior = [
                old["mean"] for old in observations[max(0, index - POLICY["anomaly_baseline_bins"]):index]
                if _time(old["time_utc"], "analysis") >= earliest
            ]
            if len(prior) < POLICY["anomaly_minimum_prior_bins"]:
                continue
            median = statistics.median(prior)
            mad = statistics.median(abs(value - median) for value in prior)
            boundary = max(POLICY["anomaly_minimum_percent_delta"], POLICY["anomaly_mad_multiplier"] * 1.4826 * mad)
            delta = point["mean"] - median if METRIC_INFO[item["metric"]][2] == "high" else median - point["mean"]
            if delta >= boundary:
                result.append(_signal(
                    item["resource_id"], "statistical_spike", point["time_utc"], "warning", "review",
                    item["label"] + " departed from its recent baseline",
                    "One-sided median/MAD flag on bin averages. Minimum 12 prior observed bins within 48 intervals; "
                    "no raw p95, native anomaly detector or proven cause is inferred.",
                    {"bin_mean": point["mean"], "baseline_median": median, "baseline_mad": mad,
                     "prior_observed_bins": len(prior), "delta_percent_points": delta,
                     "required_delta_percent_points": boundary, "grain_seconds": seconds},
                    item["source"], item["series_id"], item["metric"],
                ))
    return result


def _baseline_state(rule, reference):
    if reference < _time(rule["as_of_utc"], "arc_baselines"):
        return "not_yet_valid"
    return "current" if reference < _time(rule["valid_until_utc"], "arc_baselines") else "stale"


def _arc_administration(resources, extensions, sources, baselines, reference):
    signals = []
    extension_source = next((row for row in sources if row["source"] == "arc_extensions"), None)
    source_status = extension_source["status"] if extension_source else "not_collected"
    by_resource = {}
    for row in extensions:
        by_resource.setdefault(row["resource_id"], []).append(row)
    for resource in resources:
        resource["arc_administration"] = None
        if resource["resource_type"] != "microsoft.hybridcompute/machines":
            continue
        resource_id, rows = resource["resource_id"], by_resource.get(resource["resource_id"], [])
        scope_keys = ("os_type", "os_sku", "os_version", "location")
        rule = next((rule for rule in baselines if all(
            isinstance(resource.get(key), str) and resource[key].casefold() == rule[key].casefold()
            for key in scope_keys
        )), None)
        baseline_status = _baseline_state(rule, reference) if rule else "not_matched" if baselines else "not_configured"
        current_rule = rule if baseline_status == "current" else None
        unknowns = []
        if not current_rule:
            unknowns.append("baseline_" + baseline_status)
        agent_status = "unknown"
        agent_target = current_rule.get("agent_review_version") if current_rule else None
        if agent_target is not None:
            compared = _compare_versions(resource["arc_agent_version"], agent_target)
            agent_status = "unknown" if compared is None else "below_review_target" if compared < 0 else "at_or_above_review_target"
            if compared is None:
                unknowns.append("agent_version_missing_or_non_comparable")
            elif compared < 0:
                signals.append(_signal(
                    resource_id, "arc_agent_review", _iso(reference), "warning", "review",
                    "Arc agent is below the dated administrator review target",
                    "Numeric comparison within the exact OS/SKU/version/location baseline. This is an owner review, "
                    "not a latest-version, unsupported-agent or safe-to-install claim. Check release known issues before proposing a change.",
                    {"observed_agent_version": resource["arc_agent_version"], "review_target": agent_target,
                     "baseline_id": rule["baseline_id"], "reference": rule["reference"],
                     "as_of_utc": rule["as_of_utc"], "valid_until_utc": rule["valid_until_utc"],
                     "source_resource_id": resource_id}, "inventory",
                ))
        else:
            unknowns.append("agent_review_target_unconfigured")
        if source_status != "complete":
            unknowns.append("extension_inventory_" + source_status)
        requirements = current_rule["required_extensions"] if current_rule else []
        if not requirements:
            unknowns.append("extension_requirements_unconfigured")
        for extension in rows:
            checks = []
            provisioning = extension["provisioning_state"]
            if provisioning in ("Failed", "Canceled"):
                checks.append({"check": "native_provisioning", "state": "review", "observed": provisioning})
            elif provisioning != "Succeeded":
                checks.append({"check": "native_provisioning", "state": "unknown", "observed": provisioning,
                               "qualification": "Absent/unrecognized or transitional provisioning is not failure or sensor health."})
            expected = next((item for item in requirements if
                             isinstance(extension["publisher"], str) and isinstance(extension["extension_type"], str)
                             and item["publisher"].casefold() == extension["publisher"].casefold()
                             and item["type"].casefold() == extension["extension_type"].casefold()), None)
            location_matches = isinstance(extension["location"], str) and extension["location"].casefold() == resource["location"].casefold()
            if not expected or not location_matches:
                checks.append({"check": "configuration_baseline", "state": "unknown",
                               "qualification": "No current exact publisher/type/OS/location baseline; no cross-platform version ranking."})
            else:
                if "review_version" in expected:
                    compared = _compare_versions(extension["instance_view_version"], expected["review_version"])
                    checks.append({"check": "instance_view_version", "state": "unknown" if compared is None else "review" if compared < 0 else "observed",
                                   "observed": extension["instance_view_version"], "review_target": expected["review_version"],
                                   "qualification": "Configured typeHandlerVersion is not substituted for a missing instance-view version."})
                for key in ("enable_automatic_upgrade", "auto_upgrade_minor_version"):
                    if key in expected:
                        actual = extension[key]
                        checks.append({"check": key, "state": "unknown" if actual is None else "observed" if actual == expected[key] else "review",
                                       "observed": actual, "expected": expected[key]})
            if extension["missing_fields"]:
                checks.append({"check": "metadata", "state": "unknown", "missing_fields": extension["missing_fields"]})
            extension.update(
                baseline_id=current_rule["baseline_id"] if current_rule else None,
                checks=checks, assessment="review" if any(check["state"] == "review" for check in checks)
                else "unknown" if any(check["state"] == "unknown" for check in checks) else "observed",
            )
            if extension["assessment"] == "review":
                signals.append(_signal(
                    resource_id, "arc_extension_review", _iso(reference), "warning", "review",
                    "Arc extension metadata needs owner review",
                    "Native provisioning failure/cancellation or a dated exact-scope configuration difference; "
                    "not sensor-health proof, patch compliance or an automatic update/uninstall instruction.",
                    {"extension_id": extension["extension_id"], "publisher": extension["publisher"],
                     "extension_type": extension["extension_type"], "checks": [check for check in checks if check["state"] == "review"],
                     "baseline_id": extension["baseline_id"]}, "arc_extensions",
                ))
        for expected in requirements:
            matches = [row for row in rows if isinstance(row["publisher"], str) and isinstance(row["extension_type"], str)
                       and row["publisher"].casefold() == expected["publisher"].casefold()
                       and row["extension_type"].casefold() == expected["type"].casefold()]
            identifiable = all(row["publisher"] and row["extension_type"] for row in rows)
            if not matches and source_status == "complete" and identifiable:
                signals.append(_signal(
                    resource_id, "arc_required_extension", _iso(reference), "warning", "review",
                    "Required extension was not observed in the visible inventory",
                    "A complete permission-filtered ARG read did not return this baseline's publisher/type for the exact machine. "
                    "Verify visibility and the approved requirement with the owner; do not assert it was uninstalled or deploy it.",
                    {"publisher": expected["publisher"], "extension_type": expected["type"],
                     "baseline_id": rule["baseline_id"], "reference": rule["reference"],
                     "source_resource_id": resource_id, "permission_completeness": "not_established"}, "arc_extensions",
                ))
            elif not matches:
                unknowns.append("required_extension_presence_not_assessable")
        if any(row["assessment"] == "unknown" for row in rows):
            unknowns.append("extension_metadata_or_policy_unknown")
        if resource["arc_connection"] is None:
            unknowns.append("arc_connection_not_supplied")
        if unknowns:
            signals.append(_signal(
                resource_id, "arc_administration_unknown", _iso(reference), "info", "unknown",
                "Arc administration evidence has explicit unknowns",
                "No obsolete/healthy/compliant conclusion is inferred from absent, denied, stale or non-comparable evidence. "
                "OS lifecycle/support and the agent's one-year support window are not evaluated from names or version numbers.",
                {"unknowns": list(dict.fromkeys(unknowns)), "baseline_status": baseline_status,
                 "extension_source_status": source_status, "source_resource_id": resource_id}, "arc_administration",
            ))
        review = agent_status == "below_review_target" or any(row["assessment"] == "review" for row in rows) or any(
            signal["resource_id"] == resource_id and signal["kind"] == "arc_required_extension" for signal in signals
        )
        resource["arc_administration"] = {
            "assessment": "review" if review else "unknown" if unknowns else "observed",
            "source": "inventory", "source_resource_id": resource_id, "collected_utc": _iso(reference),
            "baseline_id": rule["baseline_id"] if rule else None, "baseline_status": baseline_status,
            "agent_version_status": agent_status, "agent_review_target": agent_target,
            "agent_support_status": "unknown", "os_support_status": "unknown",
            "extension_source_status": source_status, "extensions_observed": len(rows),
            "unknowns": list(dict.fromkeys(unknowns)),
            "qualification": "Point-in-time control-plane review, not historical configuration, guest health, support certification or update authorization.",
        }
    return signals


def _resource_signals(resources, series, sources, alerts, reference, window, metric_filter="all"):
    result = []
    by_resource = {}
    for item in series:
        if item["summary"]["observed_bins"]:
            by_resource.setdefault(item["resource_id"], []).append(item)
    for resource in resources:
        resource_id = resource["resource_id"]
        observed = by_resource.get(resource_id, [])
        compute = resource["resource_type"] in COMPUTE_TYPES
        health = resource.get("health")
        stopped = str(resource.get("power_state") or "").casefold() in ("powerstate/stopped", "powerstate/deallocated") or (
            health is not None and "stopped" in str(health.get("title") or "").casefold()
            and str(health.get("reason_type") or "").casefold() in ("customer initiated", "userinitiated", "user initiated")
        )
        metrics = {item["metric"] for item in observed}
        memory_metrics = {"memory_available_percent", "memory_available_bytes", "memory_used_percent"}
        if metric_filter == "all":
            capabilities = [("CPU", {"cpu_percent"}), ("physical memory", memory_metrics)] if compute else []
        else:
            capabilities = [(METRIC_INFO[metric_filter][0], {metric_filter})]
        missing = [name for name, keys in capabilities if not metrics.intersection(keys)]
        if missing:
            result.append(_signal(
                resource_id, "stopped_without_samples" if stopped else "telemetry_gap", window["end_utc"], "info", "unknown",
                "No runtime samples; resource is currently stopped" if stopped else "Guest/VM visibility needs review",
                "Not collected: " + ", ".join(missing) + ". Empty/unsupported/failed sources are not zero utilization or healthy infrastructure. "
                + ("Current native stop/deallocation explains expected absence while stopped, not the entire historical window." if stopped else ""),
                {"missing_capabilities": missing, "currently_stopped": stopped}, "coverage",
            ))
        elif not observed:
            result.append(_signal(resource_id, "telemetry_gap", window["end_utc"], "info", "unknown",
                                  "No applicable utilization/service observations",
                                  "Resource inventory is known; runtime operational measurements are not collected in this window.",
                                  {"requested_metric_scope": "Applicable service metrics only; no invented guest CPU/memory."}, "coverage"))
        if not missing and not stopped:
            for name, keys in capabilities:
                matching = [item for item in observed if item["metric"] in keys]
                best = max(matching, key=lambda item: item["summary"]["observed_bins"] / item["summary"]["expected_bins"])
                coverage = best["summary"]["observed_bins"] / best["summary"]["expected_bins"] * 100
                if coverage < POLICY["minimum_window_bin_coverage_percent"]:
                    result.append(_signal(
                        resource_id, "telemetry_window_gap", window["end_utc"], "info", "unknown",
                        name + " has a partially observed window",
                        "Observed/expected bins are below the example 80% window-coverage criterion. "
                        "Check lifecycle schedules, collection cadence, retention and source access; this is not a health score or outage.",
                        {"observed_bins": best["summary"]["observed_bins"], "expected_bins": best["summary"]["expected_bins"],
                         "minimum_bin_coverage_percent": POLICY["minimum_window_bin_coverage_percent"],
                         "grain_seconds": best["grain_seconds"]},
                        "coverage", best["series_id"], best["metric"],
                    ))
        heartbeat = resource.get("heartbeat")
        if heartbeat and heartbeat["age_at_window_end_minutes"] > POLICY["heartbeat_stale_minutes"]:
            result.append(_signal(
                resource_id, "heartbeat_stale", window["end_utc"], "warning", "review",
                "Agent heartbeat is old at the window end",
                "Telemetry recency needs review; this does not establish that the host or application was down.",
                {"age_minutes": heartbeat["age_at_window_end_minutes"],
                 "threshold_minutes": POLICY["heartbeat_stale_minutes"], "last_sample_utc": heartbeat["last_sample_utc"]},
                heartbeat["source"],
            ))
        if resource["arc_connection"] in ("Disconnected", "Expired"):
            result.append(_signal(
                resource_id, "arc_connection", _iso(reference), "warning", "review",
                "Arc control channel is " + resource["arc_connection"],
                "Current Arc connection state; guest AMA observations remain independent. Not proof of a guest outage.",
                {"arc_connection": resource["arc_connection"], "changed_utc": resource["arc_status_changed_utc"]}, "inventory",
            ))
        if health and health["availability_state"] in ("Unavailable", "Degraded") and not stopped:
            result.append(_signal(
                resource_id, "resource_health", _iso(reference), "critical", "review",
                "Azure platform reports " + health["availability_state"],
                "Review native context and reason; a deliberately stopped resource is not automatically an unplanned outage.",
                health, "resource_health",
            ))
        cpus = [item for item in observed if item["metric"] == "cpu_percent"]
        memories = [item for item in observed if item["metric"] == "memory_available_percent"]
        if compute and cpus and memories:
            eligible = all(
                item["summary"]["observed_bins"] >= 72
                and item["summary"]["observed_bins"] >= 0.9 * item["summary"]["expected_bins"]
                and item["summary"]["maximum_observation"] is not None
                and item["summary"]["mean"] < 10
                and item["summary"]["maximum_observation"] < 25
                for item in cpus
            ) and all(
                item["summary"]["observed_bins"] >= 72
                and item["summary"]["observed_bins"] >= 0.9 * item["summary"]["expected_bins"]
                and item["summary"]["minimum_observation"] is not None
                and item["summary"]["minimum_observation"] > 30
                and item["summary"]["mean"] > 50
                for item in memories
            )
            if eligible:
                result.append(_signal(
                    resource_id, "capacity_review", window["end_utc"], "info", "observed",
                    "Candidate for a workload/capacity review",
                    "At least 72 bins and 90% bin coverage: observed CPU mean <10%, maximum <25%, "
                    "available physical memory mean >50% and minimum >30%. Check peaks, schedules, "
                    "resilience and workload constraints. No automatic resizing or cost savings are inferred.",
                    {"cpu_series_ids": [item["series_id"] for item in cpus],
                     "memory_series_ids": [item["series_id"] for item in memories]}, "capacity_review",
                ))
    for alert in alerts:
        if alert["monitor_condition"] == "Fired":
            result.append(_signal(
                alert["resource_id"], "native_alert", alert["fired_utc"], alert["severity"], "review",
                str(alert["title"]), "Native Azure Monitor alert remains Fired at collection; not evidence of SRE handling.",
                {"alert_id": alert["alert_id"], "native_severity": alert["native_severity"],
                 "monitor_condition": alert["monitor_condition"], "alert_state": alert["alert_state"]}, "monitor_alerts",
            ))
    return result


def _review_actions(resources, signals):
    known = {row["resource_id"]: row for row in resources}
    groups = {}
    for signal in signals:
        if signal["kind"] == "arc_administration_unknown":
            continue
        if signal["state"] in ("review", "unknown") or signal["kind"] == "capacity_review":
            groups.setdefault(signal["resource_id"], []).append(signal)
    recommendations = {
        "native_alert": "Review the native alert rule, target and timing; verify the actual incident/subagent thread separately.",
        "sustained_pressure": "Compare the recorded demand and headroom with workload schedules; inspect the affected guest volume or service dimension before changing capacity.",
        "statistical_spike": "Validate the baseline shift against owner-known jobs and recent changes. A statistical flag is not a diagnosis.",
        "resource_health": "Review Azure Resource Health context and reason; distinguish deliberate power state from an unplanned platform problem.",
        "arc_connection": "Check the Arc control channel, identity, time, DNS and connectivity without assuming that guest workloads stopped.",
        "heartbeat_stale": "Review agent/workspace binding and ingestion recency. Do not restart the workload to repair monitoring.",
        "telemetry_gap": "Verify existing metric exposure and approved AMA/DCR/workspace access. Any instrumentation, permission or cost change is a separate approved operator action.",
        "telemetry_window_gap": "Compare the requested window with power/lifecycle schedules, collection cadence and retention before proposing a monitoring change.",
        "stopped_without_samples": "Confirm the expected lifecycle/power schedule. Runtime metric absence while stopped is expected; start/stop requires a separate approved operator action.",
        "capacity_review": "Ask the workload owner to validate peaks, schedules, availability/resilience and licensing before considering a capacity change.",
        "arc_agent_review": "Validate the dated review baseline, exact platform and release known issues with the owner. Any approved agent update is a separate operator change; below target does not mean unsupported.",
        "arc_extension_review": "Review the native extension ID, provisioning metadata, instance-view version and explicit baseline differences. Confirm sensor evidence separately; never update, restart or uninstall from this report.",
        "arc_required_extension": "Confirm the approved publisher/type requirement and inventory permissions before proposing an installation. Not observed does not establish absence or permission completeness.",
    }
    result = []
    priority = {"critical": 0, "warning": 1, "info": 2}
    for resource_id, observed in groups.items():
        resource = known[resource_id]
        ordered = sorted(observed, key=lambda row: (priority[row["severity"]], row["kind"], row["time_utc"]))
        kinds = list(dict.fromkeys(row["kind"] for row in ordered))
        result.append({
            "action_id": hashlib.sha256((resource_id + "|owner-review").encode()).hexdigest()[:16],
            "resource_id": resource_id, "resource_name": resource["name"], "hosting": resource["hosting"],
            "owner": resource["owner"], "severity": ordered[0]["severity"],
            "state": "review" if any(row["state"] == "review" for row in ordered) else "unknown" if any(row["state"] == "unknown" for row in ordered) else "observed",
            "title": ordered[0]["title"], "kinds": kinds,
            "review": [recommendations[kind] for kind in kinds],
            "evidence_signal_ids": [row["signal_id"] for row in ordered],
            "automatic_action": False,
        })
    return sorted(result, key=lambda row: (priority[row["severity"]], row["state"] != "review", row["resource_name"].casefold()))


def _finish_snapshot(resources, series, sources, heartbeats, health, alerts, events,
                     config, params, reference, inventory_total, extensions=None):
    extensions = extensions if extensions is not None else []
    known = {row["resource_id"]: row for row in resources}
    for heartbeat in heartbeats:
        resource = known[heartbeat["resource_id"]]
        current = resource["heartbeat"]
        if current is None or _time(heartbeat["last_sample_utc"], "Heartbeat") > _time(current["last_sample_utc"], "Heartbeat"):
            resource["heartbeat"] = heartbeat
    for resource_id, observation in health.items():
        known[resource_id]["health"] = observation
    series = [item for item in series if params["metric"] == "all" or item["metric"] == params["metric"]]
    identities = set()
    for item in series:
        if item["series_id"] in identities:
            raise EvidenceError("duplicate_series", "Collection repeated a metric series; observations were not double-counted.", "normalization")
        identities.add(item["series_id"])
    series.sort(key=lambda row: (row["resource_id"], row["metric"], row["source"], row["series_id"]))
    administration_signals = _arc_administration(resources, extensions, sources, config.get("arc_baselines", []), reference)
    signals = _metric_signals(series) + _resource_signals(resources, series, sources, alerts, reference, params["window"], params["metric"]) + administration_signals
    severity_order = {"critical": 0, "warning": 1, "info": 2}
    signals.sort(key=lambda row: (severity_order[row["severity"]], row["state"] != "review", row["resource_id"], row["time_utc"], row["signal_id"]))
    for resource in resources:
        resource_series = [item for item in series if item["resource_id"] == resource["resource_id"] and item["summary"]["observed_bins"]]
        resource_signals = [item for item in signals if item["resource_id"] == resource["resource_id"]]
        resource["series_count"] = len(resource_series)
        resource["review_signals"] = sum(item["state"] == "review" for item in resource_signals)
        resource["assessment"] = (
            "review" if resource["review_signals"] else
            "unknown" if any(item["state"] == "unknown" and item["kind"] != "arc_administration_unknown"
                             for item in resource_signals) or not resource_series else "observed"
        )
    events = sorted(events, key=lambda row: (row["time_utc"], row["resource_id"], row["event_id"]))
    actions = _review_actions(resources, signals)
    errors = [source for source in sources if source["status"] == "error"]
    incomplete = [source for source in sources if source["status"] == "partial"]
    counts = Counter(row["assessment"] for row in resources)
    return {
        "schema_version": "1.0", "provenance": "LIVE",
        "status": "partial" if errors or incomplete or counts["unknown"] else "complete",
        "collected_utc": _iso(reference), "window": params["window"],
        "scope": {
            "subscription_id": config["subscription_id"], "tenant_id": config["tenant_id"],
            "inventory_resources": inventory_total, "selected_resources": len(resources),
            "filters": {key: params[key] for key in ("hosting", "resource_group", "resource_name", "resource_id", "resource_type", "metric")
                        if params[key] not in ("", "all")},
            "workspace_ids": config["workspace_ids"],
            "inventory_types": list(RESOURCE_TYPES),
        },
        "summary": {
            "resources": len(resources), "arc": sum(row["hosting"] == "arc" for row in resources),
            "azure": sum(row["hosting"] == "azure" for row in resources),
            "review": counts["review"], "unknown": counts["unknown"], "observed": counts["observed"],
            "resources_with_metrics": sum(row["series_count"] > 0 for row in resources),
            "metric_series": len(series), "observed_bins_across_series": sum(row["summary"]["observed_bins"] for row in series),
            "native_alerts_returned": len(alerts), "native_alerts_fired": sum(row["monitor_condition"] == "Fired" for row in alerts),
            "local_rule_flags": sum(row["kind"] in ("sustained_pressure", "statistical_spike") for row in signals),
            "series_with_cpu_peaks": sum(row["kind"] == "cpu_peak" for row in signals),
            "telemetry_gaps": sum(row["kind"] in ("telemetry_gap", "telemetry_window_gap") for row in signals),
            "owner_reviews": len(actions), "source_errors": len(errors), "partial_sources": len(incomplete),
            "arc_extensions_observed": len(extensions),
            "arc_administration_review": sum(row["arc_administration"] is not None and row["arc_administration"]["assessment"] == "review" for row in resources),
            "arc_administration_unknown": sum(row["arc_administration"] is not None and row["arc_administration"]["assessment"] == "unknown" for row in resources),
        },
        "qualifications": [
            "Offline dated snapshot, not live polling. Fresh queries are new collections, not stored cursors.",
            "Observed means data was collected without a configured review flag, not certified healthy infrastructure.",
            "Current inventory, Arc connection and Azure platform health are point-in-time; time series and event timestamps have their own window.",
            "Guest physical memory, Windows commit, disk free space and Azure disk/service utilization are distinct metrics.",
            "Mean/max retain source aggregation and units. No raw p95, made-up health score, forecast, SLA or cost saving is inferred.",
            "Empty/failed/unsupported telemetry is Unknown / Not collected, never zero. Complete source retrieval is not complete monitoring coverage.",
            "Local threshold/median-MAD flags are review aids, not native alerts, proven causes or proof that SRE Agent ran.",
            "Arc machine/extension configuration is current, permission-filtered metadata. Dated baseline differences are human reviews, not unsupported/latest/sensor-health claims. OS/agent support remains Unknown.",
            "Resource assessment retains measurement/native operational review semantics; unconfigured administration policy has its own assessment and does not downgrade observed guest metrics or create an owner action.",
        ],
        "policy": dict(POLICY), "resources": resources, "series": series,
        "signals": signals, "actions": actions, "alerts": alerts,
        "events": events, "sources": sources, "extensions": extensions,
        "arc_baselines": [dict(rule, status=_baseline_state(rule, reference)) for rule in config.get("arc_baselines", [])],
    }


def _collect_live(config, params, reference):
    client = AzureReadClient(config)
    try:
        _validate_subscription(client, config)
        raw_inventory, pages = _arg_inventory(client, config)
        inventory = _normalize_resources(raw_inventory, config["subscription_id"])
        if params["resource_id"]:
            _resource_id(params["resource_id"], config["subscription_id"], "parameters")
        resources = [row for row in inventory if _resource_matches(row, params)]
        sources = [_source("inventory", "complete", reference, len(inventory), pages=pages,
                           note="Fixed relevant infrastructure types; local scope filters do not become user KQL.")]
        series, heartbeats, health, alerts, events, extensions = [], [], {}, [], [], []
        if not resources:
            sources.append(_source("telemetry", "not_collected", reference,
                                   note="No fixed-scope resources matched the requested local filters; no metric requests were made."))
            return _finish_snapshot(resources, series, sources, heartbeats, health, alerts, events,
                                    config, params, reference, len(inventory))
        if any(row["resource_type"] == "microsoft.hybridcompute/machines" for row in resources):
            extensions, receipt = _collect_arc_extensions(client, config, resources, reference)
            sources.append(receipt)
            sources.append(_source(
                "arc_baselines", "complete" if config.get("arc_baselines") else "not_configured",
                reference, len(config.get("arc_baselines", [])),
                note="Administrator-owned deployment constants, never fetched URLs. Empty/unmatched/expired baselines are Unknown, not compliant or obsolete. "
                     "Valid intervals are at most 31 days; exact OS/SKU/version/location scopes do not overlap.",
            ))
        with ThreadPoolExecutor(max_workers=4) as executor:
            for current, current_sources in executor.map(
                lambda resource: _collect_platform(client, resource, params, reference), resources
            ):
                series.extend(current)
                sources.extend(current_sources)
        compute = [row for row in resources if row["resource_type"] in COMPUTE_TYPES]
        if compute and not config["workspace_ids"]:
            sources.append(_source("guest_logs", "not_configured", reference,
                                   note="No workspace allowlist is configured. Arc guest telemetry is Unknown; native platform metrics remain independent."))
        for workspace in config["workspace_ids"] if compute else []:
            ids = [row["resource_id"] for row in compute]
            for table in ("Heartbeat", "Perf", "InsightsMetrics"):
                try:
                    rows = _query_logs(client, workspace, table, ids, params["window"])
                    if table == "Heartbeat":
                        heartbeats.extend(_normalize_heartbeat(rows, workspace, compute, params["window"]))
                        notes = []
                    else:
                        current, notes = _normalize_guest(rows, table, workspace, compute, params["window"])
                        series.extend(current)
                    sources.append(_source(table, "complete" if rows else "not_collected", reference, len(rows),
                                           workspace_id=workspace, notes=notes,
                                           note="Exact _ResourceId join; no hostname guesses. Empty Perf does not negate valid VM Insights observations."))
                except EvidenceError as exc:
                    sources.append(_source(table, "error", reference, workspace_id=workspace, error=exc,
                                           note="This source is unavailable. Other independently successful guest/platform sources remain usable."))
        try:
            health_url = (
                ARM_ORIGIN + "/subscriptions/" + config["subscription_id"]
                + "/providers/Microsoft.ResourceHealth/availabilityStatuses?api-version=" + HEALTH_VERSION
            )
            rows, pages = _arm_list(client, health_url, "resource_health")
            health, health_events = _normalize_health(rows, resources, params["window"], reference)
            events.extend(health_events)
            sources.append(_source("resource_health", "complete", reference, len(rows), matched_resources=len(health), pages=pages,
                                   note="Current Azure platform availability only. Unsupported/unreturned Arc health is not synthesized from connection state."))
        except EvidenceError as exc:
            sources.append(_source("resource_health", "error", reference, error=exc,
                                   note="Current platform availability is Unknown; not a guest/application outage claim."))
        try:
            alerts_url = (
                ARM_ORIGIN + "/subscriptions/" + config["subscription_id"]
                + "/providers/Microsoft.AlertsManagement/alerts?"
                + urlencode({"api-version": ALERTS_VERSION, "timeRange": "30d"})
            )
            rows, pages = _arm_list(client, alerts_url, "monitor_alerts")
            alerts, alert_events = _normalize_alerts(rows, resources, params["window"])
            events.extend(alert_events)
            oldest = reference - timedelta(days=30)
            clipped = _time(params["window"]["start_utc"], "monitor_alerts") < oldest
            sources.append(_source(
                "monitor_alerts", "partial" if clipped else "complete", reference, len(rows),
                pages=pages, matched_alerts=len(alerts), native_history_query="30d",
                approximate_history_start_utc=_iso(oldest),
                requested_history_partly_outside_retention=clipped,
                note="API queries approximately the last 30 days; timeline is locally windowed. Returned current conditions are not the complete lifetime alert estate. "
                     "A calendar month can extend beyond that lookback; missing older history is not zero incidents.",
            ))
        except EvidenceError as exc:
            sources.append(_source("monitor_alerts", "error", reference, error=exc,
                                   note="Alert history/returned current conditions are Unknown. Local review flags do not substitute for native alerts."))
        return _finish_snapshot(resources, series, sources, heartbeats, health, alerts, events,
                                config, params, reference, len(inventory), extensions)
    finally:
        client.close()


def _envelope(snapshot):
    return {
        "status": snapshot["status"], "provenance": snapshot["provenance"], "collected_utc": snapshot["collected_utc"],
        "window": {key: snapshot["window"][key] for key in ("start_utc", "end_utc", "grain")},
        "scope": {key: snapshot["scope"][key] for key in ("subscription_id", "tenant_id", "inventory_resources", "selected_resources", "filters")},
        "summary": snapshot["summary"],
        "qualification": "A dated collection, not live polling. Observed != healthy; native alerts != local rule flags. Unknown is not zero. Full evidence and units are in the report JSON.",
        "response_budget_bytes": TRANSPORT_BUDGET_BYTES,
    }


def _query_row(view, row):
    if view == "resources":
        return {key: row[key] for key in (
            "resource_id", "name", "hosting", "resource_type", "resource_group", "owner",
            "assessment", "arc_connection", "series_count", "review_signals",
        )} | {
            "platform_availability": row["health"]["availability_state"] if row["health"] else "Unknown",
            "last_heartbeat_utc": row["heartbeat"]["last_sample_utc"] if row["heartbeat"] else None,
            "arc_agent_version": row.get("arc_agent_version"),
            "arc_status_changed_utc": row.get("arc_status_changed_utc"),
            "os_type": row.get("os_type"), "os_sku": row.get("os_sku"), "os_version": row.get("os_version"),
            "arc_administration": {key: row["arc_administration"][key] for key in (
                "assessment", "baseline_id", "baseline_status", "agent_version_status", "agent_review_target",
                "agent_support_status", "os_support_status", "extension_source_status", "extensions_observed",
            )} if row.get("arc_administration") else None,
        }
    if view == "extensions":
        return {key: row[key] for key in (
            "extension_id", "resource_id", "name", "publisher", "extension_type", "location",
            "type_handler_version", "instance_view_version", "provisioning_state", "enable_automatic_upgrade",
            "auto_upgrade_minor_version", "assessment", "baseline_id", "checks", "missing_fields", "source", "collected_utc",
        )}
    if view == "metrics":
        observed = [point for point in row["points"] if any(point[key] is not None for key in ("mean", "minimum", "maximum", "total"))
                    or row["count_is_value"] and point["count"] is not None]
        return {key: row[key] for key in ("series_id", "resource_id", "metric", "label", "unit", "source", "native_metric", "semantics",
                                       "dimensions", "grain_seconds", "count_is_value", "summary")} | {
            "point_samples": [{key: point[key] for key in ("time_utc", "mean", "minimum", "maximum", "total", "count")} for point in observed[-2:]],
            "points_total": len(row["points"]), "point_samples_returned": min(len(observed), 2),
            "point_samples_are_not_full_series": len(row["points"]) > min(len(observed), 2),
        }
    if view == "signals":
        return {key: row[key] for key in (
            "signal_id", "resource_id", "kind", "time_utc", "severity", "state", "title", "source", "metric", "series_id", "evidence",
        )}
    if view == "timeline":
        return {key: row[key] for key in ("event_id", "resource_id", "kind", "time_utc", "severity", "state", "title", "source")} | {
            "details_in_full_snapshot": True,
        }
    if view == "actions":
        return {key: row[key] for key in (
            "action_id", "resource_id", "resource_name", "owner", "severity", "state", "title", "kinds", "review", "automatic_action",
        )} | {"evidence_signals_total": len(row["evidence_signal_ids"])}
    result = {key: row[key] for key in ("source", "status", "records", "note")}
    for key in ("resource_id", "workspace_id", "native_metrics", "grain_seconds", "error", "requested_history_partly_outside_retention",
                "pages", "subscription_rows_read", "declared_subscription_rows", "selected_machines",
                "row_limit", "page_limit", "time_budget_seconds"):
        if key in row:
            result[key] = row[key]
    if "not_exposed" in row:
        result["not_exposed"] = row["not_exposed"]
    return result


def _query(snapshot, params):
    response = _envelope(snapshot)
    if params["view"] == "extensions":
        receipt = next((row for row in snapshot["sources"] if row["source"] == "arc_extensions"), None)
        response["extension_coverage"] = {
            "status": receipt["status"] if receipt else "not_collected",
            "pages": receipt.get("pages") if receipt else None,
            "subscription_rows_read": receipt.get("subscription_rows_read") if receipt else None,
            "declared_subscription_rows": receipt.get("declared_subscription_rows") if receipt else None,
            "error": receipt.get("error") if receipt else None,
            "qualification": "Totals describe accepted selected rows only. Permission completeness is not established; zero rows does not prove absence.",
        }
    if params["view"] == "summary":
        response.update(view="summary", total_matched=1, returned=1, has_more=False,
                        next_offset=None, offset=params["offset"], requested_limit=params["limit"], transport_capped=False,
                        rows=[snapshot["summary"]] if params["offset"] == 0 else [])
        if params["offset"]:
            response.update(returned=0)
        return _budget(response)
    key = {"resources": "resources", "extensions": "extensions", "metrics": "series", "timeline": "events",
           "signals": "signals", "actions": "actions", "coverage": "sources"}[params["view"]]
    matched = snapshot.get(key, [])
    if params["state"] != "all":
        if key == "series":
            allowed = {row["resource_id"] for row in snapshot["resources"] if row["assessment"] == params["state"]}
            matched = [row for row in matched if row["resource_id"] in allowed]
        else:
            matched = [row for row in matched if row.get("assessment" if key in ("resources", "extensions") else "state") == params["state"]]
    if params["severity"] != "all":
        matched = [row for row in matched if row["severity"] == params["severity"]]
    if params["metric"] != "all" and key in ("signals", "events"):
        matched = [row for row in matched if row.get("metric") == params["metric"]]
    response.update(
        view=params["view"], total_matched=len(matched), offset=params["offset"],
        requested_limit=params["limit"], returned=0, has_more=False, next_offset=None,
        transport_capped=False, rows=[],
        paging_qualification="Fresh collection on each call; next_offset is not a stable historical cursor.",
    )
    remaining = matched[params["offset"]:params["offset"] + params["limit"]]
    for row in remaining:
        response["rows"].append(_query_row(params["view"], row))
        response["returned"] = len(response["rows"])
        response["has_more"] = params["offset"] + response["returned"] < len(matched)
        response["next_offset"] = params["offset"] + response["returned"] if response["has_more"] else None
        if _response_bytes(response) > TRANSPORT_BUDGET_BYTES:
            response["rows"].pop()
            response["transport_capped"] = True
            break
    response["returned"] = len(response["rows"])
    response["has_more"] = params["offset"] + response["returned"] < len(matched)
    response["next_offset"] = params["offset"] + response["returned"] if response["has_more"] else None
    if remaining and not response["rows"]:
        raise EvidenceError("query_row_too_large", "One complete projected evidence row exceeds the safe chat budget. Generate the report for full details; no row was skipped.", "response")
    return _budget(response)


def _pack_snapshot_v1(snapshot):
    strings, lookup, packed_series = [], {}, []
    for item in snapshot["series"]:
        fields = list(dict.fromkeys(key for point in item["points"] for key in point))
        string_columns = [index for index, field in enumerate(fields)
                          if any(isinstance(point.get(field), str) for point in item["points"])]
        rows = []
        for point in item["points"]:
            cells = []
            for index, field in enumerate(fields):
                value = point.get(field)
                if index in string_columns and value is not None:
                    if not isinstance(value, str):
                        raise EvidenceError("invalid_point_encoding", "A point column mixed strings and non-string values.", "artifact_encoding")
                    if value not in lookup:
                        lookup[value] = len(strings)
                        strings.append(value)
                    value = lookup[value]
                cells.append(value)
            rows.append(cells)
        packed_series.append({key: value for key, value in item.items() if key != "points"} | {
            "points": {"columns": fields, "string_columns": string_columns, "rows": rows},
        })
    return {
        "format": "infra-ops-columnar", "encoding_version": "1.0", "strings": strings,
        "snapshot": {key: value for key, value in snapshot.items() if key != "series"} | {"series": packed_series},
    }


def _unpack_snapshot_v1(document):
    if not isinstance(document.get("strings"), list):
        raise EvidenceError("invalid_snapshot_encoding", "Unsupported infrastructure snapshot encoding.", "artifact_encoding")
    strings, snapshot = document["strings"], document.get("snapshot")
    if any(not isinstance(value, str) for value in strings) or not isinstance(snapshot, dict) or not isinstance(snapshot.get("series"), list):
        raise EvidenceError("invalid_snapshot_encoding", "Snapshot dictionary/table structure is invalid.", "artifact_encoding")
    series = []
    for item in snapshot["series"]:
        table = item.get("points")
        if not isinstance(table, dict):
            raise EvidenceError("invalid_snapshot_encoding", "Encoded series omitted its point table.", "artifact_encoding")
        fields, string_columns, rows = table.get("columns"), table.get("string_columns"), table.get("rows")
        if (
            not isinstance(fields, list) or any(not isinstance(field, str) for field in fields) or len(fields) != len(set(fields))
            or not isinstance(string_columns, list) or any(type(index) is not int or not 0 <= index < len(fields) for index in string_columns)
            or not isinstance(rows, list)
        ):
            raise EvidenceError("invalid_snapshot_encoding", "Encoded point columns are invalid.", "artifact_encoding")
        points = []
        for row in rows:
            if not isinstance(row, list) or len(row) != len(fields):
                raise EvidenceError("invalid_snapshot_encoding", "Encoded point row is ragged.", "artifact_encoding")
            point = {}
            for index, (field, value) in enumerate(zip(fields, row)):
                if index in string_columns and value is not None:
                    if type(value) is not int or not 0 <= value < len(strings):
                        raise EvidenceError("invalid_snapshot_encoding", "Encoded string index is invalid.", "artifact_encoding")
                    value = strings[value]
                point[field] = value
            points.append(point)
        series.append({key: value for key, value in item.items() if key != "points"} | {"points": points})
    return {key: value for key, value in snapshot.items() if key != "series"} | {"series": series}


_CODEC_MISSING = object()


def _pack_snapshot(snapshot):
    """Codec 2.0: recursive records, exact constants/runs/sparse columns and UTC progressions."""
    strings, lookup = [], {}

    def intern(value):
        if value not in lookup:
            lookup[value] = len(strings)
            strings.append(value)
        return lookup[value]

    def encode(value, depth=0):
        if depth > 100:
            raise EvidenceError("invalid_snapshot_encoding", "Snapshot nesting exceeds the codec bound.", "artifact_encoding")
        if value is _CODEC_MISSING:
            return [4]
        if value is None or type(value) in (bool, int):
            return value
        if type(value) is float:
            return _number(value, "artifact_encoding")
        if isinstance(value, str):
            return [0, intern(value)]
        if isinstance(value, dict):
            fields = []
            for key, child in value.items():
                if not isinstance(key, str):
                    raise EvidenceError("invalid_snapshot_encoding", "Snapshot object keys must be strings.", "artifact_encoding")
                fields.extend((intern(key), encode(child, depth + 1)))
            return [1, fields]
        if isinstance(value, list):
            if value and all(isinstance(row, dict) for row in value):
                fields = list(dict.fromkeys(key for row in value for key in row))
                if any(not isinstance(key, str) for key in fields):
                    raise EvidenceError("invalid_snapshot_encoding", "Record table keys must be strings.", "artifact_encoding")
                return [3, len(value), [intern(key) for key in fields], [
                    column([row.get(key, _CODEC_MISSING) for row in value], depth + 1) for key in fields
                ]]
            return [2, [encode(child, depth + 1) for child in value]]
        raise EvidenceError("invalid_snapshot_encoding", "Snapshot contains an unsupported JSON value.", "artifact_encoding")

    def column(values, depth):
        fingerprints = [
            None if value is _CODEC_MISSING else json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
            for value in values
        ]
        if len(set(fingerprints)) == 1:
            return [0, encode(values[0], depth)]
        if all(isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", value) for value in values):
            times = []
            for value in values:
                try:
                    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
                except ValueError:
                    break
                times.append(int(parsed.timestamp()))
            if len(times) == len(values):
                step = times[1] - times[0]
                if all(times[index] == times[0] + step * index for index in range(len(times))):
                    return [4, times[0], step]
        encoded = [encode(value, depth) for value in values]
        runs = []
        for index, value in enumerate(encoded):
            if index and fingerprints[index] == fingerprints[index - 1]:
                runs[-1][0] += 1
            else:
                runs.append([1, value])
        default = Counter(fingerprints).most_common(1)[0][0]
        first = fingerprints.index(default)
        sparse = [[index, value] for index, value in enumerate(encoded) if fingerprints[index] != default]
        candidates = [[1, encoded], [2, runs], [3, encoded[first], sparse]]
        if all(value is _CODEC_MISSING or value is None or type(value) is float
               or type(value) is int and abs(value) <= 9_007_199_254_740_991 for value in values):
            mask, numbers = bytearray((len(values) + 3) // 4), bytearray()
            for index, value in enumerate(values):
                state = 0 if value is _CODEC_MISSING else 1 if value is None else 2 if type(value) is int else 3
                mask[index // 4] |= state << (index % 4 * 2)
                if state >= 2:
                    numbers.extend(struct.pack("<d", value))
            candidates.append([5, base64.b64encode(mask).decode("ascii"), base64.b64encode(numbers).decode("ascii")])
        return min(candidates, key=lambda value: len(json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)))

    encoded = encode(snapshot)
    return {"format": "infra-ops-columnar", "encoding_version": "2.0", "strings": strings, "snapshot": encoded}


def _unpack_snapshot(document):
    if not isinstance(document, dict) or document.get("format") != "infra-ops-columnar":
        return document
    version = document.get("encoding_version")
    if version == "1.0":
        return _unpack_snapshot_v1(document)
    strings = document.get("strings")
    if version != "2.0" or not isinstance(strings, list) or any(not isinstance(value, str) for value in strings):
        raise EvidenceError("invalid_snapshot_encoding", "Unsupported snapshot encoding or string dictionary.", "artifact_encoding")

    def invalid(message):
        raise EvidenceError("invalid_snapshot_encoding", message, "artifact_encoding")

    def index(value):
        if type(value) is not int or not 0 <= value < len(strings):
            invalid("Encoded string index is outside the dictionary.")
        return strings[value]

    def decode(node, depth=0):
        if depth > 100:
            invalid("Encoded nesting exceeds the codec bound.")
        if node is None or type(node) in (bool, int):
            return node
        if type(node) is float:
            return _number(node, "artifact_encoding")
        if not isinstance(node, list) or not node or type(node[0]) is not int:
            invalid("Encoded JSON node is invalid.")
        tag = node[0]
        if tag == 0 and len(node) == 2:
            return index(node[1])
        if tag == 4 and len(node) == 1:
            return _CODEC_MISSING
        if tag == 1 and len(node) == 2 and isinstance(node[1], list) and len(node[1]) % 2 == 0:
            result = {}
            for offset in range(0, len(node[1]), 2):
                key, value = index(node[1][offset]), decode(node[1][offset + 1], depth + 1)
                if key in result or value is _CODEC_MISSING:
                    invalid("Encoded object has a repeated key or a missing-value marker.")
                result[key] = value
            return result
        if tag == 2 and len(node) == 2 and isinstance(node[1], list):
            result = [decode(child, depth + 1) for child in node[1]]
            if any(value is _CODEC_MISSING for value in result):
                invalid("Encoded array contains a missing-value marker.")
            return result
        if tag == 3 and len(node) == 4:
            count, fields, columns = node[1:]
            if (
                type(count) is not int or not 0 <= count <= MAX_SOURCE_ROWS
                or not isinstance(fields, list) or not isinstance(columns, list) or len(fields) != len(columns)
            ):
                invalid("Encoded table shape/count is invalid.")
            keys = [index(value) for value in fields]
            if len(keys) != len(set(keys)):
                invalid("Encoded table repeats an object key.")
            rows = [{} for _ in range(count)]
            for key, encoded in zip(keys, columns):
                values = decode_column(encoded, count, depth + 1)
                for row, value in zip(rows, values):
                    if value is not _CODEC_MISSING:
                        row[key] = value
            return rows
        invalid("Encoded JSON node has an unknown tag/shape.")

    def decode_column(encoded, count, depth):
        if not isinstance(encoded, list) or not encoded or type(encoded[0]) is not int:
            invalid("Encoded column is invalid.")
        tag = encoded[0]
        if tag == 0 and len(encoded) == 2:
            return [decode(encoded[1], depth) for _ in range(count)]
        if tag == 1 and len(encoded) == 2 and isinstance(encoded[1], list) and len(encoded[1]) == count:
            return [decode(value, depth) for value in encoded[1]]
        if tag == 2 and len(encoded) == 2 and isinstance(encoded[1], list):
            result = []
            for run in encoded[1]:
                if not isinstance(run, list) or len(run) != 2 or type(run[0]) is not int or not 1 <= run[0] <= count - len(result):
                    invalid("Encoded run count is invalid.")
                result.extend(decode(run[1], depth) for _ in range(run[0]))
            if len(result) != count:
                invalid("Encoded runs do not cover the declared row count.")
            return result
        if tag == 3 and len(encoded) == 3 and isinstance(encoded[2], list):
            result = [decode(encoded[1], depth) for _ in range(count)]
            seen = set()
            for pair in encoded[2]:
                if (
                    not isinstance(pair, list) or len(pair) != 2 or type(pair[0]) is not int
                    or not 0 <= pair[0] < count or pair[0] in seen
                ):
                    invalid("Encoded sparse column repeats or exceeds a row position.")
                seen.add(pair[0])
                result[pair[0]] = decode(pair[1], depth)
            return result
        if tag == 4 and len(encoded) == 3 and type(encoded[1]) is int and type(encoded[2]) is int:
            try:
                return [_iso(datetime.fromtimestamp(encoded[1] + encoded[2] * offset, UTC)) for offset in range(count)]
            except (ValueError, OverflowError, OSError) as exc:
                raise EvidenceError("invalid_snapshot_encoding", "Encoded UTC progression is outside datetime bounds.", "artifact_encoding") from exc
        if tag == 5 and len(encoded) == 3 and isinstance(encoded[1], str) and isinstance(encoded[2], str):
            try:
                mask, numbers = (base64.b64decode(value, validate=True) for value in encoded[1:])
            except (ValueError, binascii.Error) as exc:
                raise EvidenceError("invalid_snapshot_encoding", "Encoded numeric column is not valid base64.", "artifact_encoding") from exc
            if len(mask) != (count + 3) // 4 or count % 4 and mask[-1] >> (count % 4 * 2):
                invalid("Encoded numeric validity mask has invalid length/padding.")
            result, offset = [], 0
            for row in range(count):
                state = mask[row // 4] >> (row % 4 * 2) & 3
                if state < 2:
                    result.append(_CODEC_MISSING if state == 0 else None)
                    continue
                if offset + 8 > len(numbers):
                    invalid("Encoded numeric column ended before its declared values.")
                number = _number(struct.unpack_from("<d", numbers, offset)[0], "artifact_encoding")
                offset += 8
                if state == 2 and (not number.is_integer() or abs(number) > 9_007_199_254_740_991):
                    invalid("Encoded integer is outside the lossless numeric bound.")
                result.append(int(number) if state == 2 else number)
            if offset != len(numbers):
                invalid("Encoded numeric column contains undeclared values.")
            return result
        invalid("Encoded column has an unknown tag/shape.")

    snapshot = decode(document.get("snapshot"))
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("series"), list):
        invalid("Encoded root is not an infrastructure snapshot.")
    return snapshot


def _json_document(snapshot):
    plain = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    encoded = json.dumps(_pack_snapshot(snapshot), ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return encoded if len(encoded.encode("utf-8")) < len(plain.encode("utf-8")) else plain


def _safe_json(document):
    return document.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


def _csv_cell(value):
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, allow_nan=False)
    if isinstance(value, str):
        return "'" + value if value.lstrip().lstrip("\ufeff").startswith(("=", "+", "-", "@")) else value
    return value


def _csv_document(rows, fields):
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(fields)
    for row in rows:
        writer.writerow([_csv_cell(row.get(field)) for field in fields])
    return output.getvalue()


CSV_CONTEXT_FIELDS = ("provenance", "snapshot_collected_utc", "window_start_utc", "window_end_utc", "window_grain")
RESOURCE_CSV_FIELDS = (
    "resource_id", "name", "hosting", "resource_type", "resource_group", "location",
    "owner", "os", "size", "power_state", "provisioning_state", "arc_connection",
    "assessment", "series_count", "review_signals", "heartbeat", "health", "tags",
    "os_type", "os_sku", "os_version", "arc_agent_version", "arc_status_changed_utc", "arc_administration", "arc_extensions",
)


def _resource_export_rows(snapshot):
    extensions = {}
    for row in snapshot.get("extensions", []):
        extensions.setdefault(row["resource_id"], []).append(row)
    return [dict(row, arc_extensions=extensions.get(row["resource_id"], [])) for row in snapshot["resources"]]


def _csv_context(snapshot, rows):
    context = {
        "provenance": snapshot["provenance"], "snapshot_collected_utc": snapshot["collected_utc"],
        "window_start_utc": snapshot["window"]["start_utc"], "window_end_utc": snapshot["window"]["end_utc"],
        "window_grain": snapshot["window"]["grain"],
    }
    return [{**row, **context} for row in rows]


def _company_logo_markup():
    if COMPANY_LOGO_DATA_URI == "":
        return '<span class="company-logo-placeholder">logo company</span>'
    source = "company_logo"
    if not isinstance(COMPANY_LOGO_DATA_URI, str):
        raise EvidenceError("invalid_company_logo", "Configure the optional company logo as a PNG/JPEG base64 data URI.", source)
    if len(COMPANY_LOGO_DATA_URI) > (MAX_COMPANY_LOGO_BYTES + 2) // 3 * 4 + 32:
        raise EvidenceError("company_logo_too_large", "The embedded company logo exceeds the 100000-byte raster limit.", source)
    match = re.fullmatch(r"data:image/(png|jpeg);base64,([A-Za-z0-9+/]+={0,2})", COMPANY_LOGO_DATA_URI)
    if match is None:
        raise EvidenceError("invalid_company_logo", "Use one-line data:image/png;base64 or data:image/jpeg;base64; external URLs and SVG are not supported.", source)
    try:
        data = base64.b64decode(match[2], validate=True)
    except (ValueError, binascii.Error) as exc:
        raise EvidenceError("invalid_company_logo", "The company logo contains invalid base64 data.", source) from exc
    if not data or len(data) > MAX_COMPANY_LOGO_BYTES:
        raise EvidenceError("company_logo_too_large", "The company logo must contain 1 to 100000 raster bytes.", source)
    if (
        not isinstance(COMPANY_LOGO_ALT_TEXT, str) or not COMPANY_LOGO_ALT_TEXT.strip()
        or len(COMPANY_LOGO_ALT_TEXT) > 120 or re.search(r"[\x00-\x1f\x7f]", COMPANY_LOGO_ALT_TEXT)
    ):
        raise EvidenceError("invalid_company_logo", "Provide descriptive COMPANY_LOGO_ALT_TEXT of 1 to 120 plain characters.", source)
    try:
        from PIL import Image, UnidentifiedImageError
    except ImportError as exc:
        raise EvidenceError("dependency_missing", "A configured company logo requires Pillow for bounded raster validation.", source) from exc
    try:
        with Image.open(io.BytesIO(data), formats=["PNG", "JPEG"]) as image:
            width, height = image.size
            if (
                image.format != ("PNG" if match[1] == "png" else "JPEG")
                or not 1 <= width <= MAX_COMPANY_LOGO_DIMENSION
                or not 1 <= height <= MAX_COMPANY_LOGO_DIMENSION
                or getattr(image, "n_frames", 1) != 1
            ):
                raise EvidenceError("invalid_company_logo", "Use a single-frame PNG/JPEG no larger than 2048 by 2048 pixels, with a matching MIME type.", source)
            image.verify()
        with Image.open(io.BytesIO(data), formats=["PNG", "JPEG"]) as image:
            image.load()
    except (OSError, ValueError, SyntaxError, UnidentifiedImageError, Image.DecompressionBombError) as exc:
        raise EvidenceError("invalid_company_logo", "The embedded company logo is not a complete, valid PNG/JPEG raster.", source) from exc
    return (
        '<img src="' + html.escape(COMPANY_LOGO_DATA_URI, quote=True)
        + '" alt="' + html.escape(COMPANY_LOGO_ALT_TEXT.strip(), quote=True)
        + '" width="' + str(width) + '" height="' + str(height) + '">'
    )


REPORT_HTML = r"""<!doctype html>
<!--
DIRECTION: Azure SRE Agent report family (top bar, verdict band, KPI cards, white sections) in this scenario's own petrol-on-cool-paper palette.
FIRST VIEWPORT: slim bar with optional company logo; petrol verdict band with the recorded numbers, dated chips, verdict and assessment bar; KPI cards on its edge.
SIGNATURE: Unknown is drawn hollow or hatched wherever it appears, so missing evidence never reads as zero or as healthy.
BODY: review drivers, filterable fleet register with inspector, time recorder, owner review, event log, evidence coverage, exports and limits.
-->
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; connect-src 'none'; base-uri 'none'; form-action 'none'">
<title>Infrastructure operations - recorded evidence</title>
<style>
:root{--paper:#eef2f1;--sheet:#ffffff;--ink:#18312e;--muted:#526660;--petrol:#163d3a;--petrol-2:#24534d;--line:#d0dad5;--line-soft:#e3e9e6;--wash:#e4eeea;--soft:#f3f6f5;--focus:#156dc0;--link:#155e55;
--crit:#b42318;--crit-bg:#fee4e2;--crit-bar:#d92d20;--high:#b93815;--high-bg:#ffead5;--high-bar:#ef6820;--med:#93370d;--med-bg:#fef0c7;--med-bar:#f79009;--low:#175cd3;--low-bg:#d1e9ff;--low-bar:#2e90fa;--info:#344054;--info-bg:#eaecf0;--info-bar:#98a2b3;--ok:#0f5a50;--ok-bg:#dcefe9;--ok-bar:#3f9e8b;
--hatch:repeating-linear-gradient(135deg,#98a2b3 0 3px,#dfe3e9 3px 6px);--radius:12px;--shadow:0 1px 2px rgba(16,40,36,.06),0 6px 18px -8px rgba(16,40,36,.16);
--font:"Segoe UI",system-ui,-apple-system,"Helvetica Neue",sans-serif;--mono:ui-monospace,"Cascadia Mono",Consolas,monospace}
*{box-sizing:border-box}html{-webkit-text-size-adjust:100%;scroll-padding-top:80px;scrollbar-color:#b8c6c0 var(--paper)}body{margin:0;background:var(--paper);color:var(--ink);font:15px/1.55 var(--font);-webkit-font-smoothing:antialiased}
::selection{background:#cfe3dc;color:var(--ink)}a{color:var(--link);text-underline-offset:3px}a:hover{color:var(--petrol)}h1,h2,h3{text-wrap:balance}p{margin:0 0 12px}
button,input,select{font:inherit;color:inherit}button,a,input,select,summary{touch-action:manipulation}button{cursor:pointer}button:disabled{cursor:not-allowed;opacity:.55}
button,input,select{border:1px solid #a9bab3;border-radius:8px;min-height:40px;background:var(--sheet);color:var(--ink);padding:7px 12px}input::placeholder{color:var(--muted);opacity:1}
button{font-weight:600;font-size:14px;white-space:nowrap}button:hover:not(:disabled){background:var(--soft)}button:active:not(:disabled){background:var(--wash)}
button.primary{background:var(--petrol);border-color:var(--petrol);color:#fff}button.primary:hover:not(:disabled){background:var(--petrol-2)}
:focus-visible{outline:3px solid var(--focus);outline-offset:2px}.skip{position:absolute;top:-100px;left:16px;z-index:60;background:#fff;padding:10px 14px;border-radius:8px;box-shadow:var(--shadow)}.skip:focus{top:10px}
.num{font-variant-numeric:tabular-nums}.sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}
.bar{position:sticky;top:0;z-index:40;display:flex;align-items:center;gap:18px;min-height:60px;padding:8px clamp(16px,4vw,40px);background:#fff;border-bottom:1px solid var(--line)}
.brand{display:flex;align-items:center;gap:14px;min-width:0}.company-logo{width:132px;height:40px;padding:4px 8px;border:1px solid var(--line);border-radius:8px;background:var(--sheet);display:flex;align-items:center;justify-content:center;flex:none;overflow:hidden}
.company-logo-placeholder{color:var(--muted);font-size:12.5px;white-space:nowrap}.company-logo img{display:block;max-width:100%;max-height:100%;width:auto;height:auto;object-fit:contain}
.wordmark{display:flex;align-items:center;gap:9px;font-weight:700;font-size:16px;letter-spacing:-.01em;color:var(--petrol);white-space:nowrap}.wordmark svg{width:17px;height:22px;flex:none}
.bar-nav{display:flex;gap:2px;margin-left:6px}.bar-nav a{display:inline-flex;align-items:center;gap:7px;min-height:40px;padding:0 11px;border-radius:8px;color:var(--muted);text-decoration:none;font-size:14px;font-weight:600;white-space:nowrap}
.bar-nav a span{min-width:24px;text-align:center;font-size:12px;font-weight:700;color:var(--ink);background:var(--soft);border-radius:999px;padding:1px 7px;font-variant-numeric:tabular-nums}
.bar-nav a:hover{background:var(--soft);color:var(--ink)}.bar-nav a[aria-current=location]{background:var(--wash);color:var(--petrol)}.bar-nav a[aria-current=location] span{background:#fff}
.acts{margin-left:auto;display:flex;align-items:center;gap:10px}.tag{display:inline-flex;align-items:center;gap:7px;font-size:12.5px;font-weight:600;color:var(--muted);border:1px solid var(--line);border-radius:999px;padding:5px 12px;white-space:nowrap}
.tag svg,.btn svg{width:16px;height:16px;flex:none}.btn{display:inline-flex;align-items:center;gap:8px;padding:0 16px}
.hero{background:var(--petrol);color:#fff;padding:46px clamp(16px,4vw,40px) 108px}.hero-in{max-width:1320px;margin:0 auto;display:grid;grid-template-columns:minmax(0,1fr) 310px;gap:22px 40px;align-items:start}
.hero h1{margin:0 0 14px;font-size:42px;line-height:1.08;font-weight:700;letter-spacing:-.02em}.lead{margin:0 0 10px;font-size:18px;line-height:1.5;max-width:62ch}.lead b{font-variant-numeric:tabular-nums}.sum{margin:0;color:#c7dad3;max-width:70ch}
.meta{display:flex;flex-wrap:wrap;gap:8px;margin-top:22px}.chip{display:inline-flex;align-items:center;gap:6px;font-size:12.5px;line-height:1.4;padding:5px 11px;border-radius:999px;border:1px solid rgba(255,255,255,.3);color:#dce9e4;white-space:nowrap;font-variant-numeric:tabular-nums;max-width:100%;overflow:hidden;text-overflow:ellipsis}
.chip.on{color:#fff;font-weight:700;border-color:rgba(255,255,255,.6)}.chip.warn{background:#fef0c7;border-color:#fef0c7;color:#7a2e0e;font-weight:700}.chip time{color:inherit}
.verdict{border-radius:16px;padding:20px 22px;background:rgba(255,255,255,.07);border:1px solid rgba(255,255,255,.24)}.verdict .k{display:block;font-size:13px;font-weight:600;color:#c7dad3;margin-bottom:6px}
.verdict b{display:block;font-size:28px;line-height:1.15;font-weight:700;color:#fff}.verdict.warn b{color:#fdb022}.verdict.crit b{color:#fda29b}.verdict.unknown b{color:#e4e7ec}.verdict.ok b{color:#a6e3d3}
.verdict p{margin:8px 0 0;font-size:14px;color:#dce9e4;font-variant-numeric:tabular-nums}.verdict small{display:block;margin-top:10px;padding-top:10px;border-top:1px solid rgba(255,255,255,.18);font-size:13px;color:#bcd2ca}
.dist{grid-column:1/-1;margin-top:4px}.track{display:flex;height:14px;border-radius:999px;overflow:hidden;background:rgba(255,255,255,.14)}.track i{display:block;height:100%;min-width:3px}
.legend{display:flex;flex-wrap:wrap;gap:6px 22px;margin-top:10px;font-size:14px;color:#dce9e4}.legend span{display:inline-flex;align-items:center;gap:8px}.legend i{width:11px;height:11px;border-radius:3px;display:inline-block}.legend b{color:#fff;font-variant-numeric:tabular-nums}
.c-review{background:var(--med-bar)}.c-unknown{background:var(--hatch)}.c-observed{background:var(--ok-bar)}.c-critical{background:var(--crit-bar)}.c-warning{background:var(--med-bar)}.c-info{background:var(--info-bar)}.c-error{background:var(--crit-bar)}.c-partial{background:var(--med-bar)}.c-complete{background:var(--ok-bar)}.c-gap{background:var(--hatch)}
.hero .c-unknown,.hero .c-gap{background:repeating-linear-gradient(135deg,#a9b4c2 0 3px,#5d6f6b 3px 6px)}
.page{max-width:1320px;margin:0 auto;padding:0 clamp(16px,4vw,40px) 48px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:14px;margin-top:-64px;position:relative;z-index:2}
.kpi{background:var(--sheet);border:1px solid var(--line);border-radius:var(--radius);padding:18px 20px;box-shadow:var(--shadow);min-width:0}
.kpi .v{display:block;font-size:38px;line-height:1;font-weight:700;letter-spacing:-.02em;color:var(--petrol);font-variant-numeric:tabular-nums;white-space:nowrap}.kpi .v small{font-size:17px;font-weight:600;color:var(--muted);margin-left:4px;letter-spacing:0}
.kpi .l{display:block;margin-top:10px;font-size:14px;font-weight:650}.kpi .s{display:block;margin-top:5px;font-size:13px;color:var(--muted)}.kpi.warn .v{color:var(--med)}.kpi.unknown .v{color:var(--info)}.kpi.crit .v{color:var(--crit)}
.notice{margin:16px 0 0;padding:12px 16px;border:1px solid var(--line);border-radius:10px;background:var(--sheet);color:var(--muted);font-size:14px}.notice strong{color:var(--ink)}
.notice.replay{background:repeating-linear-gradient(135deg,#fffaeb 0 12px,#fef0c7 12px 24px);border-color:#fedf89;color:#7a2e0e}.notice.replay strong{color:#7a2e0e}.notice.error-message{border-color:var(--crit);background:var(--crit-bg);color:var(--crit)}
.sec{margin-top:44px}.sh{margin-bottom:14px}.sh h2{margin:0;font-size:22px;line-height:1.25;font-weight:700;letter-spacing:-.01em}.sh p{margin:4px 0 0;color:var(--muted);font-size:14px;max-width:75ch}
.card{background:var(--sheet);border:1px solid var(--line);border-radius:var(--radius);box-shadow:var(--shadow);min-width:0}.card.pad{padding:20px 22px}.card h3{margin:0 0 4px;font-size:17px;line-height:1.3;font-weight:700}.card .sub{margin:0 0 16px;color:var(--muted);font-size:14px}
.grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,440px),1fr));gap:16px}
.bars{display:grid;gap:10px}.brow{display:grid;grid-template-columns:minmax(120px,44%) minmax(0,1fr) 40px;gap:12px;align-items:center;font-size:14px}.brow .bl{min-width:0;overflow:hidden;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;line-height:1.35}
.brow .bt{display:flex;height:12px;border-radius:999px;overflow:hidden;background:var(--soft)}.brow .bt i{display:block;height:100%;min-width:3px}.brow b{text-align:right;font-variant-numeric:tabular-nums}.bars-key{display:flex;flex-wrap:wrap;gap:4px 16px;margin-top:14px;font-size:13px;color:var(--muted)}.bars-key span{display:inline-flex;align-items:center;gap:7px}.bars-key i{width:10px;height:10px;border-radius:3px;display:inline-block}
.stamp{display:inline-flex;align-items:center;gap:6px;padding:2px 10px;border-radius:999px;font-size:12px;line-height:1.6;font-weight:700;white-space:nowrap;background:var(--info-bg);color:var(--info);vertical-align:middle}
.stamp::before{content:"";width:7px;height:7px;border-radius:50%;background:currentColor;flex:none}.stamp.critical,.stamp.error{background:var(--crit-bg);color:var(--crit)}.stamp.high{background:var(--high-bg);color:var(--high)}
.stamp.review,.stamp.warning,.stamp.partial{background:var(--med-bg);color:var(--med)}.stamp.observed,.stamp.complete{background:var(--ok-bg);color:var(--ok)}.stamp.low{background:var(--low-bg);color:var(--low)}
.stamp.unknown,.stamp.info,.stamp.not_collected,.stamp.not_supported,.stamp.not_configured{background:var(--info-bg);color:var(--info)}.stamp.unknown::before,.stamp.not_collected::before,.stamp.not_supported::before,.stamp.not_configured::before{background:transparent;box-shadow:inset 0 0 0 1.5px currentColor}
.register-tools{padding:18px 20px 0}.filters{display:grid;grid-template-columns:minmax(0,1.25fr) repeat(3,minmax(0,1fr)) minmax(0,1.25fr) auto;gap:12px;align-items:end}.field{display:grid;gap:5px;min-width:0}.field label{font-size:13px;font-weight:600}.field input,.field select{width:100%;min-width:0}.filters .reset{white-space:nowrap}
.scope-row{display:flex;flex-wrap:wrap;align-items:center;gap:12px 20px;padding:16px 20px;border-bottom:1px solid var(--line)}.scope-tabs{display:inline-flex;padding:3px;border-radius:10px;background:var(--soft);border:1px solid var(--line);gap:2px}
.scope-tabs button{border:0;min-height:34px;padding:0 14px;border-radius:7px;background:transparent;color:var(--muted);font-size:14px}.scope-tabs button span{font-variant-numeric:tabular-nums;margin-left:6px;color:var(--ink)}.scope-tabs button[aria-pressed=true]{background:var(--petrol);color:#fff}.scope-tabs button[aria-pressed=true] span{color:#fff}
.summary-line{display:flex;flex-wrap:wrap;align-items:center;gap:8px 16px;font-size:14px;flex:1}.summary-line b{font-variant-numeric:tabular-nums;font-size:16px;margin-left:4px}.summary-line .summary-scope{margin-left:auto;color:var(--muted);font-size:13px}
.desk{display:grid;grid-template-columns:minmax(0,1.7fr) minmax(320px,1fr)}.register{min-width:0}.section-head{padding:18px 20px 14px;display:flex;justify-content:space-between;gap:12px;align-items:center}.section-head h2,.section-head h3{margin:0;font-size:17px;line-height:1.3;font-weight:700}.section-head h2{font-size:20px}.section-head p{font-size:13px;color:var(--muted);margin:3px 0 0}
.minor-action{font-size:13px;min-height:34px;padding:5px 11px;white-space:nowrap}
.table-wrap{overflow-x:auto;max-width:100%;background:linear-gradient(90deg,#fff 30%,rgba(255,255,255,0)) left/40px 100% no-repeat local,linear-gradient(270deg,#fff 30%,rgba(255,255,255,0)) right/40px 100% no-repeat local,radial-gradient(farthest-side at 0 50%,rgba(16,40,36,.2),rgba(16,40,36,0)) left/14px 100% no-repeat scroll,radial-gradient(farthest-side at 100% 50%,rgba(16,40,36,.2),rgba(16,40,36,0)) right/14px 100% no-repeat scroll}
table{border-collapse:collapse;width:100%;font-size:14px}th{text-align:left;font-size:12px;font-weight:700;letter-spacing:.04em;text-transform:uppercase;color:var(--muted);background:var(--soft);padding:10px 12px;border-bottom:1px solid var(--line);border-top:1px solid var(--line);white-space:nowrap}
td{padding:12px;border-bottom:1px solid var(--line-soft);vertical-align:top}th:first-child,td:first-child{padding-left:20px}th:last-child,td:last-child{padding-right:20px}tbody tr:last-child td{border-bottom:0}
th .sort{border:0;background:none;min-height:0;padding:2px 0;border-radius:4px;font:inherit;color:inherit;letter-spacing:inherit;text-transform:inherit;display:inline-flex;align-items:center;gap:7px}th .sort:hover{color:var(--petrol);background:none}
th .sort::after{content:"";border-left:4px solid transparent;border-right:4px solid transparent;border-top:5px solid currentColor;opacity:.35}th[aria-sort=ascending] .sort::after{border-top:0;border-bottom:5px solid currentColor;opacity:1}th[aria-sort=descending] .sort::after{opacity:1}
.fleet-table{min-width:600px}.fleet-table td.check{width:46px}.fleet-table input[type=checkbox]{width:18px;height:18px;min-height:0;accent-color:var(--petrol);padding:0;margin:2px 0 0}
.fleet-table .resource-name{border:0;border-radius:4px;background:none;min-height:0;padding:0;font-size:14.5px;font-weight:650;text-align:left;color:var(--petrol);overflow-wrap:break-word;white-space:normal;display:block;max-width:250px}.fleet-table .resource-name:hover{text-decoration:underline;background:none}
.fleet-table tr.selected td{background:#eaf3ef}.fleet-table tbody tr:hover td{background:#f5f8f7}
.secondary-text{display:block;font-size:13px;color:var(--muted);margin-top:3px;overflow-wrap:break-word}.measurement{font-weight:650;font-variant-numeric:tabular-nums;white-space:nowrap}.missing{font-size:13px;color:var(--info);font-weight:600;display:inline-flex;align-items:center;gap:6px;white-space:nowrap}.missing::before{content:"";width:10px;height:10px;border-radius:2px;background:var(--hatch);flex:none}
.table-footer{display:flex;justify-content:space-between;gap:12px;align-items:center;padding:12px 20px;color:var(--muted);font-size:13px;border-top:1px solid var(--line-soft)}.empty{padding:24px 20px;color:var(--muted);max-width:75ch}.empty strong{display:block;color:var(--ink);margin-bottom:6px}
.inspector{border-left:1px solid var(--line);padding:22px 24px;min-width:0;background:#f7faf9;border-radius:0 0 var(--radius) 0}.inspector-head{display:flex;justify-content:space-between;align-items:flex-start;gap:12px}.inspector-title{font-size:20px;line-height:1.25;margin:0;overflow-wrap:break-word}
.resource-kind{font-size:13px;color:var(--muted);overflow-wrap:break-word;margin:4px 0 16px}.facts{display:grid;grid-template-columns:118px minmax(0,1fr);gap:7px 14px;font-size:14px;margin:0 0 18px}.facts dt{color:var(--muted)}.facts dd{margin:0;overflow-wrap:break-word}
.resource-id,.arm-id{font:12.5px/1.55 var(--mono);overflow-wrap:normal;word-break:normal;display:block;max-width:100%;overflow-x:auto;margin:12px 0;color:var(--muted)}.nw{white-space:nowrap}.metric-title{font-size:15px;margin:4px 0 8px}
details{border-top:1px solid var(--line);padding:12px 0}summary{cursor:pointer;font-size:14px;font-weight:650;min-height:28px}.inspector .detail-list{margin:10px 0 0;padding:0;list-style:none}.detail-list li{padding:10px 0;border-bottom:1px solid var(--line-soft);font-size:13px}.detail-list li strong{display:block;font-size:14px;margin-bottom:4px}
.detail-list p{color:var(--muted);margin:5px 0}.detail-list .evidence-json{font:12px/1.5 var(--mono);overflow-wrap:anywhere}.inline-buttons{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin:14px 0}.inspector .detail-list p,.inspector .secondary-text{overflow-wrap:anywhere}
.portal-link{display:inline-flex;align-items:center;gap:5px;font-size:13px;font-weight:600}.portal-link svg{width:14px;height:14px}
.recorder .section-head{padding:20px 22px 12px}.chart-controls{display:flex;gap:12px;align-items:end;flex-wrap:wrap;padding:0 22px 16px}.chart-controls .field{min-width:200px;flex:1;max-width:320px}.chart-controls .check-label{font-size:14px;display:flex;align-items:center;gap:8px;min-height:40px}.chart-controls input[type=checkbox]{min-height:0;width:18px;height:18px;accent-color:var(--petrol)}
.chart-frame{padding:4px 22px 0;overflow:hidden}.chart-frame svg{display:block;width:100%;height:255px}.chart-legend{display:flex;flex-wrap:wrap;gap:10px 24px;padding:8px 22px 0;font-size:13px}.legend-entry{display:flex;align-items:flex-start;gap:8px;max-width:420px}.line-key{width:22px;flex:none;height:3px;border-radius:2px;margin-top:9px;background:var(--petrol)}.legend-entry strong{font-weight:650}.legend-entry small{display:block;color:var(--muted);font-size:12.5px;line-height:1.45;margin-top:2px;overflow-wrap:anywhere}
.bin-inspector{display:grid;grid-template-columns:170px minmax(0,1fr);gap:10px 20px;padding:16px 22px;background:var(--soft);margin-top:14px;border-top:1px solid var(--line-soft);font-size:14px}.bin-inspector label{font-weight:600}.bin-inspector input[type=range]{padding:0;min-height:32px;accent-color:var(--petrol);border:0;background:transparent;width:100%}.bin-readout{grid-column:1/-1;color:var(--muted);font-variant-numeric:tabular-nums;min-height:24px}
.chart-note{padding:12px 22px 18px;color:var(--muted);font-size:13px;max-width:75ch;margin:0}
.lower{display:grid;grid-template-columns:minmax(0,1.12fr) minmax(0,1fr);gap:16px;align-items:start}.work-section{min-width:0}.work-section .section-head{border-bottom:1px solid var(--line)}
.review-list,.event-list{list-style:none;margin:0;padding:0}.review-list li,.event-list li{padding:16px 20px;border-bottom:1px solid var(--line-soft)}.review-row{display:flex;gap:12px;justify-content:space-between;align-items:flex-start}.review-row strong{font-size:15px}
.review-meta{color:var(--muted);font-size:13px;margin:6px 0;display:flex;flex-wrap:wrap;align-items:center;gap:6px}.review-meta .resource-name{min-height:30px;padding:3px 10px;font-size:13px}.review-list p{font-size:14px;max-width:70ch;margin:8px 0 0}
.event-list time{font:13px var(--mono);color:var(--muted);display:block;margin-bottom:6px}.event-list strong{font-size:15px;display:block}.event-list .event-source{display:block;margin-top:4px;font-size:13px;color:var(--muted)}.event-list p{font-size:13px;margin:7px 0 0;color:var(--muted)}.pills{display:flex;gap:6px;flex-wrap:wrap;margin-top:8px}
.arm-meta{display:block;margin-top:3px;font-size:13px;color:var(--muted)}.review-list .arm-id,.event-list .arm-id{font-size:12px;margin:6px 0 0}
.review-row strong{min-width:0;overflow-wrap:anywhere}.event-list strong,.event-list .event-source,.event-list p{overflow-wrap:anywhere}
.timeline-tabs{display:flex;padding:12px 20px;border-bottom:1px solid var(--line)}.timeline-tabs .seg{display:inline-flex;padding:3px;border-radius:10px;background:var(--soft);border:1px solid var(--line);gap:2px}.timeline-tabs button{border:0;min-height:32px;padding:0 12px;border-radius:7px;background:transparent;color:var(--muted);font-size:13px}.timeline-tabs button[aria-pressed=true]{color:#fff;background:var(--petrol)}
.coverage-head{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:16px;align-items:start;padding:20px 22px 16px}.coverage-head .bars{max-width:620px}.source-table{min-width:700px}.source-table td{max-width:460px}.source-table .source-description{font-size:13px;color:var(--muted)}.source-table .source-description p{margin:6px 0 0}.source-table .source-name{font-size:14px;font-weight:650;overflow-wrap:break-word}.source-error{color:var(--crit);display:block;font-size:13px;margin-top:5px}
.exports{display:flex;align-items:center;justify-content:space-between;gap:16px 24px;flex-wrap:wrap;padding:20px 22px}.exports h3{margin:0 0 4px;font-size:17px}.exports p{font-size:14px;color:var(--muted);margin:0;max-width:70ch}.exports .inline-buttons{margin:0}
.limits{margin:0;padding:0 0 0 18px;color:var(--muted);font-size:13.5px;max-width:75ch}.limits li{margin:0 0 6px}.status-live{min-height:20px;font-size:13px;color:var(--muted);margin-top:10px}
.foot{max-width:1320px;margin:0 auto;padding:4px clamp(16px,4vw,40px) 40px;display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px 20px;color:var(--muted);font-size:13px}
@media(max-width:1240px){.bar-nav a{padding:0 8px}.bar-nav a span{min-width:0}}
@media(max-width:1180px){.bar-nav{display:none}.desk{grid-template-columns:1fr}.inspector{border-left:0;border-top:1px solid var(--line);border-radius:0 0 var(--radius) var(--radius)}.filters{grid-template-columns:repeat(3,minmax(0,1fr))}.filters .search-field{grid-column:1/-1}}
@media(max-width:900px){.hero-in{grid-template-columns:1fr}.hero h1{font-size:36px}.lower{grid-template-columns:1fr}.coverage-head{grid-template-columns:1fr}}
@media(max-width:640px){.bar{gap:10px;min-height:56px}.tag{display:none}.btn .lbl{display:none}.btn{padding:0 11px}.company-logo{width:100px;height:34px;padding:3px 6px}.company-logo-placeholder{font-size:12px}.wordmark{font-size:15px}
.hero{padding:30px 16px 96px}.hero h1{font-size:32px}.lead{font-size:16.5px}.verdict b{font-size:24px}.meta{gap:6px}.chip{font-size:12.5px;white-space:normal}.kpis{grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.kpi{padding:14px 15px}.kpi .v{font-size:30px}.kpi .l{font-size:13.5px}
.sec{margin-top:36px}.card.pad{padding:18px 16px}.filters{grid-template-columns:1fr 1fr;gap:10px}.filters .reset{grid-column:1/-1}.register-tools{padding:16px 16px 0}.scope-row{padding:14px 16px}.summary-line .summary-scope{margin-left:0;width:100%}.section-head{padding:16px;align-items:flex-start}
.brow{grid-template-columns:minmax(0,1fr) auto}.brow .bt{grid-column:1/-1;grid-row:2}th:first-child,td:first-child{padding-left:16px}th:last-child,td:last-child{padding-right:16px}.table-footer{padding:12px 16px;flex-wrap:wrap}.inspector{padding:18px 16px}.facts{grid-template-columns:104px minmax(0,1fr);font-size:13.5px}
.chart-controls,.chart-legend{padding-left:16px;padding-right:16px}.chart-controls .field{max-width:none;min-width:0;flex-basis:100%}.chart-frame{padding:4px 12px 0}.chart-frame svg{height:225px}.bin-inspector{grid-template-columns:1fr;padding:14px 16px}.chart-note{padding:12px 16px 16px}.review-list li,.event-list li{padding:14px 16px}.timeline-tabs{padding:12px 16px}.coverage-head{padding:16px}.exports{padding:18px 16px}}
@media(prefers-reduced-motion:reduce){*{scroll-behavior:auto!important;transition:none!important}}
@page{size:A4;margin:14mm 12mm 16mm}
@media print{*{-webkit-print-color-adjust:exact;print-color-adjust:exact}html{scroll-padding-top:0}body{background:#fff;font-size:12px}.skip,.bar-nav,.acts,.foot,.fleet-table .check,.filters,.register-tools,.scope-tabs,.inline-buttons,.minor-action,.chart-controls,.bin-inspector,.table-footer button,.timeline-tabs,.exports .inline-buttons,.status-live{display:none!important}
.bar{position:static;min-height:0;padding:0 0 10px;border-bottom:0}.hero{padding:24px 26px 88px;border-radius:12px;break-inside:avoid}.hero-in{grid-template-columns:minmax(0,1fr) 220px;gap:14px 26px}.hero h1{font-size:30px}.lead{font-size:14px}.verdict{padding:14px 16px}.verdict b{font-size:20px}
.page{padding:0}.kpis{grid-template-columns:repeat(3,minmax(0,1fr));margin-top:-66px;gap:10px}.kpi{box-shadow:none;break-inside:avoid;padding:12px 14px}.kpi .v{font-size:26px}.card{box-shadow:none}.sec{margin-top:22px}.sh{break-after:avoid}.grid2{grid-template-columns:1fr 1fr}.grid2 .card{break-inside:avoid}
.desk,.lower{display:block}.lower .work-section+.work-section{margin-top:16px}.inspector{border-left:0;border-top:1px solid var(--line)}.table-wrap{overflow:visible;background:none}.brow .bl{display:block;overflow:visible}.fleet-table,.source-table{min-width:0}table{font-size:11px}td,th{padding:6px 8px}thead{display:table-header-group}
tr,.brow,.review-list li,.event-list li,.recorder,.coverage-head,#glance{break-inside:avoid}th .sort::after{display:none}.notice{break-inside:avoid}.chart-frame svg{height:220px}.fleet-table .resource-name{font-size:11.5px;max-width:none}.secondary-text,.missing,.source-table .source-description{font-size:9.5px}.stamp{font-size:9.5px;padding:0 7px}.review-list{columns:2;column-gap:0}.review-list li{padding:10px 14px;font-size:11px}.review-list p{font-size:11px}.review-row strong,.event-list strong{font-size:12px}}
</style>
</head>
<body>
<a class="skip" href="#main">Skip to infrastructure evidence</a>
<header class="bar">
 <div class="brand"><div class="company-logo">__COMPANY_LOGO__</div><span class="wordmark"><svg viewBox="0 0 30 38" aria-hidden="true"><path d="M2 1h26v36H2zM8 8h14M8 16h14M8 24h14M8 32h8" fill="none" stroke="currentColor" stroke-width="2.4"/></svg>Azure SRE Agent</span></div>
 <nav class="bar-nav" aria-label="Report sections"><a href="#fleet">Fleet <span id="nav-fleet">--</span></a><a href="#recorder">Recorder</a><a href="#reviews">Reviews <span id="nav-reviews">--</span></a><a href="#timeline">Events <span id="nav-events">--</span></a><a href="#sources">Sources <span id="nav-sources">--</span></a></nav>
 <div class="acts"><span class="tag"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 11V8a5 5 0 0 1 10 0v3M6 11h12v9H6z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/></svg>Read-only</span><button id="print-top" class="btn primary" type="button" aria-label="Print or save as PDF"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 9V3h10v6M7 17H5a2 2 0 0 1-2-2v-4a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v4a2 2 0 0 1-2 2h-2M7 14h10v7H7z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/></svg><span class="lbl">Print / PDF</span></button></div>
</header>
<main id="main">
 <section class="hero" aria-labelledby="report-title">
  <div class="hero-in">
   <div><h1 id="report-title">Infrastructure operations</h1><p class="lead" id="hero-lead">Opening the recorded evidence.</p><p class="sum">Arc guests and Azure services, with their differences intact.</p>
    <div class="meta"><span class="chip on" id="provenance-label">LIVE data · dated snapshot</span><span class="chip">Collected <time id="collected-time"></time></span><span class="chip" id="period-line"></span><span class="chip" id="scope-line"></span></div></div>
   <aside class="verdict" id="verdict" aria-label="Verdict"><span class="k">Verdict</span><b id="verdict-title">Reading evidence</b><p id="verdict-detail"></p><small>Observed means collected without a review flag, not a health certificate.</small></aside>
   <div class="dist" id="dist"></div>
  </div>
 </section>
 <div class="page">
 <div class="kpis" id="kpis" aria-label="Key figures"></div>
 <div class="notice" id="snapshot-notice"><strong>Recorded evidence, not live polling.</strong> Filters and exports use this embedded snapshot. A new SRE query collects newer data; it does not update this file.</div>
 <section class="sec" id="glance" aria-labelledby="glance-title">
  <div class="sh"><h2 id="glance-title">At a glance</h2><p>What triggered the owner checks, and where runtime evidence is missing across resource types.</p></div>
  <div class="grid2"><div class="card pad"><h3>Owner checks by reason</h3><p class="sub">One check per resource, named by its most severe signal.</p><div class="bars" id="reason-bars"></div></div><div class="card pad"><h3>Fleet by resource type</h3><p class="sub">Assessment of every collected resource; hatched means no runtime evidence.</p><div class="bars" id="type-bars"></div><div class="bars-key" id="type-key"></div></div></div>
 </section>
 <section class="sec" id="fleet" aria-labelledby="fleet-title">
  <div class="sh"><h2 id="fleet-title">Fleet register</h2><p>Filter the recorded fleet, open a resource to read its own sources and units, and pin up to three for the time recorder.</p></div>
  <div class="card">
   <div class="register-tools"><div class="filters" role="group" aria-label="Fleet filters">
    <div class="field search-field"><label for="search">Find a resource</label><input id="search" type="search" placeholder="Name, group, owner or Arc metadata" autocomplete="off"></div>
    <div class="field"><label for="type-filter">Resource type</label><select id="type-filter"><option value="">All types</option></select></div>
    <div class="field"><label for="state-filter">Observed state</label><select id="state-filter"><option value="">All states</option><option value="review">Review</option><option value="unknown">Unknown</option><option value="observed">Observed, no review flag</option></select></div>
    <div class="field owner-field"><label for="owner-filter">Owner tag</label><select id="owner-filter"><option value="">All owners</option><option value="__unassigned">Unassigned</option></select></div>
    <div class="field"><label for="arc-admin-filter">Arc administration</label><select id="arc-admin-filter"><option value="">All resources</option><option value="review">Administration review</option><option value="unknown">Administration unknown</option><option value="below_target">Agent below dated target</option><option value="extension_review">Extension review</option><option value="disconnected">Disconnected / Expired</option></select></div>
    <button id="reset" class="reset" type="button">Reset filters</button>
   </div></div>
   <div class="scope-row"><div class="scope-tabs" role="group" aria-label="Hosting scope"><button type="button" data-hosting="all" aria-pressed="true" id="host-all">All resources</button><button type="button" data-hosting="arc" aria-pressed="false" id="host-arc">Arc</button><button type="button" data-hosting="azure" aria-pressed="false" id="host-azure">Azure</button></div><div class="summary-line" id="summary-line" aria-label="Collection summary"></div></div>
   <div class="desk">
    <section class="register" aria-labelledby="register-title"><div class="section-head"><div><h3 id="register-title">Resources in this view</h3><p id="fleet-count"></p></div><button id="export-resources" class="minor-action" type="button">Export matches</button></div>
     <div class="table-wrap"><table class="fleet-table"><thead><tr><th class="check"><span class="sr-only">Compare</span></th><th data-sort-key="name"><button type="button" class="sort" data-sort="name">Resource / hosting</button></th><th data-sort-key="cpu"><button type="button" class="sort" data-sort="cpu">CPU / scope</button></th><th data-sort-key="memory"><button type="button" class="sort" data-sort="memory">Memory / scope</button></th><th data-sort-key="assessment" aria-sort="ascending"><button type="button" class="sort" data-sort="assessment">Assessment</button></th></tr></thead><tbody id="fleet-body"></tbody></table></div>
     <div id="fleet-empty" class="empty" hidden><strong>No resources match these filters.</strong>Reset the filters or choose another hosting/type.</div>
     <div class="table-footer"><span id="fleet-page"></span><button id="fleet-more" class="minor-action" type="button">Show more</button></div>
    </section>
    <aside class="inspector" id="inspector" aria-label="Selected resource evidence"><div class="empty"><strong>Select a resource.</strong>Its actual sources, units, ownership and review evidence will appear here.</div></aside>
   </div>
  </div>
 </section>
 <section class="sec recorder" id="recorder" aria-labelledby="recorder-title">
  <div class="sh"><h2 id="recorder-title">Time recorder</h2><p>Recorded traces for up to three pinned resources. Gaps stay open: a missing bin is not zero.</p></div>
  <div class="card">
   <div class="section-head"><div><h3>Pinned traces</h3><p>Select up to three resource checkboxes, then choose a measure and a recorded time range.</p></div><button id="export-series" class="minor-action" type="button">Export full traces</button></div>
   <div class="chart-controls"><div class="field"><label for="metric-select">Recorded metric</label><select id="metric-select"></select></div><div class="field"><label for="range-select">Snapshot time range</label><select id="range-select"><option value="all">Entire snapshot</option><option value="48">Last 48 hours of snapshot</option><option value="24">Last 24 hours of snapshot</option><option value="2">Last 2 hours of snapshot</option></select></div><label class="check-label"><input id="show-max" type="checkbox">Show source maxima</label></div>
   <div class="chart-frame" id="chart-frame"></div><div class="chart-legend" id="chart-legend"></div>
   <div class="bin-inspector"><label for="bin-slider">Inspect a recorded bin</label><input id="bin-slider" type="range" min="0" max="0" value="0" step="1" disabled><div id="bin-readout" class="bin-readout" aria-live="polite">No interpolated samples. Missing stays missing.</div></div>
   <p class="chart-note">Solid: source Average (or the native Count/Total/Maximum when that is the recorded measure). Dashed: supplied source Maximum only. Gaps stay open. Guest/platform CPU denominators and service/limit meanings remain different; units, source and bin width travel with each trace.</p>
  </div>
 </section>
 <div class="sec lower">
  <section class="card work-section" id="reviews" aria-labelledby="review-title"><div class="section-head"><div><h2 id="review-title">Owner review</h2><p>What to check next, most severe first. Evidence-linked; no remediation runs from this report.</p></div><button id="export-actions" class="minor-action" type="button">Export CSV</button></div><ol class="review-list" id="review-list"></ol><div class="table-footer"><span id="review-count"></span><button id="review-more" class="minor-action" type="button">Show more</button></div></section>
  <section class="card work-section" id="timeline" aria-labelledby="timeline-title"><div class="section-head"><div><h2 id="timeline-title">Event log</h2><p>Source chronology, not a causal story invented by the report.</p></div><button id="export-events" class="minor-action" type="button">Export CSV</button></div><div class="timeline-tabs"><div class="seg" role="group" aria-label="Event provenance"><button type="button" data-event-mode="native" aria-pressed="true">Native events</button><button type="button" data-event-mode="local" aria-pressed="false">Local observations</button></div></div><ol class="event-list" id="event-list"></ol><div class="table-footer"><span id="event-count"></span><button id="event-more" class="minor-action" type="button">Show more</button></div></section>
 </div>
 <section class="sec" id="sources" aria-labelledby="sources-title">
  <div class="sh"><h2 id="sources-title">Evidence coverage</h2><p>A complete request is not complete monitoring. Empty, unsupported and failed have different meanings.</p></div>
  <div class="card"><div class="coverage-head"><div class="bars" id="coverage-bars" aria-label="Source results by status"></div><button id="export-sources" class="minor-action" type="button">Export CSV</button></div><div class="table-wrap"><table class="source-table"><thead><tr><th>Source / resource</th><th>Result</th><th>Returned records</th><th>Meaning / limitation</th></tr></thead><tbody id="source-body"></tbody></table></div><div class="table-footer"><span id="source-count"></span><button id="source-more" class="minor-action" type="button">Show more</button></div></div>
 </section>
 <section class="sec" aria-labelledby="exports-title">
  <div class="card exports"><div><h3 id="exports-title">Keep the evidence with the decision.</h3><p>Complete JSON includes all collected series, event records, signals, owner reviews and source errors. CSV buttons export all current matches, never just the displayed page.</p></div><div class="inline-buttons"><button id="export-json" class="primary" type="button">Complete JSON</button><button id="export-signals" type="button">Signals CSV</button><button id="print-report" type="button">Print snapshot</button></div></div>
  <div class="status-live" id="action-status" role="status" aria-live="polite"></div>
 </section>
 <section class="sec" aria-labelledby="limits-title"><div class="sh"><h2 id="limits-title">Method and limits</h2><p>How to read this snapshot. These qualifications travel with every export.</p></div><div class="card pad"><div class="footnote" id="footnote"></div></div></section>
 </div>
</main>
<footer class="foot"><span>Generated by Azure SRE Agent · read-only collection · <span id="foot-collected"></span></span><span>Infrastructure operations · scenario 03</span></footer>
<noscript><p style="padding:24px">This offline report needs local JavaScript for filtering and charts. No network connection is required. Use the separately delivered CSV/JSON files when scripts are disabled.</p></noscript>
<script id="evidence-data" type="application/json">__SNAPSHOT_DATA__</script>
<script>
"use strict";
(() => {
const $ = id => document.getElementById(id), colors = ["#163d3a","#355f9c","#745383"], pageSize = 8;
const esc = value => String(value ?? "").replace(/[&<>"']/g,c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const utc = value => value ? new Date(value).toISOString().replace("T"," ").replace(/\.\d{3}Z$/," UTC") : "Not supplied";
const valid = value => typeof value === "number" && Number.isFinite(value);
const numeric = (value,digits=2) => valid(value) ? new Intl.NumberFormat("en",{maximumFractionDigits:digits}).format(value) : "--";
const formatted = (value,unit) => {
 if(!valid(value)) return "Not collected";
 const u=String(unit).toLowerCase();
 if(u==="percent") return numeric(value)+"%";
 if(u==="bytes"){const scales=["B","KiB","MiB","GiB","TiB"];let n=Math.abs(value),i=0;while(n>=1024&&i<4){n/=1024;i++;}return numeric((value<0?-1:1)*n)+" "+scales[i];}
 if(u==="nanocores") return numeric(value/1e9,4)+" cores";
 if(u==="milliseconds") return numeric(value)+" ms";
 if(u==="seconds") return numeric(value)+" s";
 return numeric(value)+" "+(unit==="Count"?"count":unit);
};
const cap = value => {const s=String(value ?? "");return s.charAt(0).toUpperCase()+s.slice(1);};
const badge = (state,label) => `<span class="stamp ${esc(state)}">${esc(label ?? cap(String(state).replaceAll("_"," ")))}</span>`;
const plural = (n,one,many) => n+" "+(n===1?one:many);
const idWrap = value => String(value ?? "").split("/").map(part=>'<span class="nw">'+esc(part)+"</span>").join("/<wbr>");
const extIcon = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"/></svg>';
function armParts(value){const m=/^\/subscriptions\/[^/]+(?:\/resourcegroups\/([^/]+))?(?:\/providers\/([^/]+\/[^/]+))?(?:\/.*)?\/([^/]+)$/i.exec(String(value ?? ""));return m?{group:m[1]||"",type:(m[2]||"").toLowerCase(),name:m[3]}:null;}
const ruleKinds={"microsoft.insights/scheduledqueryrules":"Log alert rule","microsoft.insights/metricalerts":"Metric alert rule","microsoft.insights/activitylogalerts":"Activity log alert rule"};
function titleHtml(title,full){const p=armParts(title);if(!p)return `<strong>${esc(title)}</strong>`;return `<strong title="${esc(title)}">${esc(p.name)}</strong><span class="arm-meta">${esc(ruleKinds[p.type]||p.type.split("/").pop()||"Azure resource")}${p.group?" · "+esc(p.group):""}</span>`+(full?`<code class="arm-id">${idWrap(title)}</code>`:"");}
function decode(doc){
 if(doc.format!=="infra-ops-columnar") return doc;
 if(!Array.isArray(doc.strings)||doc.strings.some(s=>typeof s!=="string")||!doc.snapshot) throw new Error("Unsupported snapshot encoding.");
 if(doc.encoding_version==="2.0"){
  const missing=Symbol("absent");
  const fail=message=>{throw new Error(message);};
  const string=index=>{if(!Number.isInteger(index)||index<0||index>=doc.strings.length)fail("Invalid string dictionary index.");return doc.strings[index];};
  function node(value,depth=0){
   if(depth>100)fail("Snapshot nesting exceeds the codec bound.");
   if(value===null||typeof value==="boolean"||typeof value==="number")return value;
   if(!Array.isArray(value)||!Number.isInteger(value[0]))fail("Invalid encoded JSON node.");
   const tag=value[0];
   if(tag===0&&value.length===2)return string(value[1]);
   if(tag===4&&value.length===1)return missing;
   if(tag===1&&value.length===2&&Array.isArray(value[1])&&value[1].length%2===0){
    const result=Object.create(null);
    for(let i=0;i<value[1].length;i+=2){const key=string(value[1][i]),child=node(value[1][i+1],depth+1);if(Object.hasOwn(result,key)||child===missing)fail("Repeated or absent object key.");result[key]=child;}
    return result;
   }
   if(tag===2&&value.length===2&&Array.isArray(value[1])){const result=value[1].map(v=>node(v,depth+1));if(result.includes(missing))fail("Absent marker in an array.");return result;}
   if(tag===3&&value.length===4){
    const count=value[1],fields=value[2],columns=value[3];
    if(!Number.isInteger(count)||count<0||count>50000||!Array.isArray(fields)||!Array.isArray(columns)||fields.length!==columns.length)fail("Invalid encoded record table.");
    const keys=fields.map(string);if(new Set(keys).size!==keys.length)fail("Repeated table key.");
    const rows=Array.from({length:count},()=>Object.create(null));
    columns.forEach((v,i)=>column(v,count,depth+1).forEach((child,j)=>{if(child!==missing)rows[j][keys[i]]=child;}));return rows;
   }
   fail("Unknown encoded JSON node.");
  }
  function column(value,count,depth){
   if(!Array.isArray(value)||!Number.isInteger(value[0]))fail("Invalid encoded column.");
   const tag=value[0];
   if(tag===0&&value.length===2)return Array.from({length:count},()=>node(value[1],depth));
   if(tag===1&&value.length===2&&Array.isArray(value[1])&&value[1].length===count)return value[1].map(v=>node(v,depth));
   if(tag===2&&value.length===2&&Array.isArray(value[1])){
    const result=[];for(const run of value[1]){if(!Array.isArray(run)||run.length!==2||!Number.isInteger(run[0])||run[0]<1||run[0]>count-result.length)fail("Invalid encoded run length.");for(let i=0;i<run[0];i++)result.push(node(run[1],depth));}
    if(result.length!==count)fail("Incomplete encoded runs.");return result;
   }
   if(tag===3&&value.length===3&&Array.isArray(value[2])){
    const result=Array.from({length:count},()=>node(value[1],depth)),seen=new Set();
    for(const pair of value[2]){if(!Array.isArray(pair)||pair.length!==2||!Number.isInteger(pair[0])||pair[0]<0||pair[0]>=count||seen.has(pair[0]))fail("Invalid sparse column position.");seen.add(pair[0]);result[pair[0]]=node(pair[1],depth);}return result;
   }
   if(tag===4&&value.length===3&&Number.isSafeInteger(value[1])&&Number.isSafeInteger(value[2]))return Array.from({length:count},(_,i)=>new Date((value[1]+value[2]*i)*1000).toISOString().replace(".000Z","Z"));
   if(tag===5&&value.length===3&&typeof value[1]==="string"&&typeof value[2]==="string"){
    const mask=Uint8Array.from(atob(value[1]),c=>c.charCodeAt(0)),bytes=Uint8Array.from(atob(value[2]),c=>c.charCodeAt(0));
    if(mask.length!==Math.ceil(count/4)||(count%4&&mask[mask.length-1]>>(count%4*2)))fail("Invalid numeric validity mask.");
    const data=new DataView(bytes.buffer),result=[];let offset=0;
    for(let i=0;i<count;i++){const state=mask[Math.floor(i/4)]>>(i%4*2)&3;if(state<2){result.push(state===0?missing:null);continue;}if(offset+8>bytes.length)fail("Truncated numeric column.");const number=data.getFloat64(offset,true);offset+=8;if(!Number.isFinite(number)||(state===2&&!Number.isSafeInteger(number)))fail("Invalid lossless numeric value.");result.push(number);}
    if(offset!==bytes.length)fail("Undeclared numeric column values.");return result;
   }
   fail("Unknown encoded column.");
  }
  const snapshot=node(doc.snapshot);if(!snapshot||!Array.isArray(snapshot.series))fail("Invalid decoded infrastructure snapshot.");return snapshot;
 }
 if(doc.encoding_version!=="1.0")throw new Error("Unsupported snapshot codec version.");
 const snapshot=doc.snapshot;
 snapshot.series=snapshot.series.map(series=>{
  const t=series.points;if(!Array.isArray(t.columns)||!Array.isArray(t.rows)||!Array.isArray(t.string_columns))throw new Error("Invalid encoded point table.");
  series.points=t.rows.map(row=>{
   if(row.length!==t.columns.length)throw new Error("Invalid point row.");
   const point={};t.columns.forEach((key,i)=>{let v=row[i];if(t.string_columns.includes(i)&&v!==null){if(!Number.isInteger(v)||v<0||v>=doc.strings.length)throw new Error("Invalid timestamp dictionary.");v=doc.strings[v];}point[key]=v;});return point;
  });return series;
 });return snapshot;
}
let snapshot;
try{snapshot=decode(JSON.parse($("evidence-data").textContent));if(!Array.isArray(snapshot.resources)||!Array.isArray(snapshot.series)||snapshot.schema_version!=="1.0")throw new Error("Invalid infrastructure schema.");}
catch(error){$("snapshot-notice").className="notice error-message";$("snapshot-notice").textContent="The embedded evidence could not be decoded. Use the separately delivered JSON/CSV files and report the validation error: "+error.message;document.querySelectorAll("button,input,select").forEach(x=>x.disabled=true);console.error(error);return;}
const resources=new Map(snapshot.resources.map(r=>[r.resource_id,r]));
const seriesByResource=new Map();snapshot.series.forEach(s=>{if(!seriesByResource.has(s.resource_id))seriesByResource.set(s.resource_id,[]);seriesByResource.get(s.resource_id).push(s);});
const extensionsByResource=new Map();(snapshot.extensions||[]).forEach(e=>{if(!extensionsByResource.has(e.resource_id))extensionsByResource.set(e.resource_id,[]);extensionsByResource.get(e.resource_id).push(e);});
const st={hosting:"all",search:"",type:"",assessment:"",owner:"",arcAdmin:"",focus:null,compare:new Set(),metric:"cpu_percent",range:"all",eventMode:"native",fleetLimit:pageSize,reviewLimit:pageSize,eventLimit:pageSize,sourceLimit:30,traces:[],binTimes:[],chart:null,sort:{key:"assessment",dir:1}};
const cpuKeys=["cpu_percent","node_cpu_percent","container_cpu_percent","plan_cpu_percent","sql_cpu_percent"],memoryKeys=["memory_available_percent","memory_used_percent","memory_commit_percent","node_memory_percent","container_memory_percent","plan_memory_percent","sql_memory_percent","memory_available_bytes","container_memory_bytes","app_memory_bytes"];
const assessmentRank={review:0,observed:1,unknown:2},sortCache=new Map();
function sortValue(r,key){const id=key+"|"+r.resource_id;if(!sortCache.has(id)){const s=representative(r,key==="cpu"?cpuKeys:memoryKeys),v=s&&s.summary.observed_bins?(s.summary.mean!==null?s.summary.mean:s.summary.last_value):null;sortCache.set(id,valid(v)?v:null);}return sortCache.get(id);}
function compareResources(a,b){
 const {key,dir}=st.sort,fallback=()=>(assessmentRank[a.assessment]-assessmentRank[b.assessment])||Number(b.series_count>0)-Number(a.series_count>0)||a.name.localeCompare(b.name);
 if(key==="name")return dir*a.name.localeCompare(b.name);
 if(key==="cpu"||key==="memory"){const x=sortValue(a,key),y=sortValue(b,key);if(x===null||y===null)return x===y?fallback():x===null?1:-1;return dir*(x-y)||fallback();}
 return dir*((assessmentRank[a.assessment]-assessmentRank[b.assessment])||Number(b.series_count>0)-Number(a.series_count>0))||a.name.localeCompare(b.name);
}
const shownResources = () => snapshot.resources.filter(r=>{
 const search=st.search.toLocaleLowerCase("en"),extensions=extensionsByResource.get(r.resource_id)||[],text=[r.name,r.resource_group,r.owner??"",r.resource_id,r.arc_agent_version,r.os_type,r.os_sku,r.os_version,...extensions.flatMap(e=>[e.name,e.publisher,e.extension_type,e.instance_view_version])].join(" ").toLocaleLowerCase("en");
 const adminMatch=!st.arcAdmin||(st.arcAdmin==="below_target"?r.arc_administration?.agent_version_status==="below_review_target":st.arcAdmin==="extension_review"?extensions.some(e=>e.assessment==="review"):st.arcAdmin==="disconnected"?["Disconnected","Expired"].includes(r.arc_connection):r.arc_administration?.assessment===st.arcAdmin);
 return(st.hosting==="all"||r.hosting===st.hosting)&&(!search||text.includes(search))&&(!st.type||r.resource_type===st.type)&&(!st.assessment||r.assessment===st.assessment)&&(!st.owner||(st.owner==="__unassigned"?!r.owner:r.owner===st.owner))&&adminMatch;
}).sort(compareResources);
const shownIds = () => new Set(shownResources().map(r=>r.resource_id));
const matchingSignals = () => {const ids=shownIds();return snapshot.signals.filter(s=>ids.has(s.resource_id));};
const matchingActions = () => {const ids=shownIds();return snapshot.actions.filter(s=>ids.has(s.resource_id));};
const matchingEvents = () => {const ids=shownIds();const rows=st.eventMode==="native"?snapshot.events:snapshot.signals;return rows.filter(s=>ids.has(s.resource_id)).slice().sort((a,b)=>Date.parse(b.time_utc)-Date.parse(a.time_utc));};
const matchingSources = () => {const ids=shownIds();return snapshot.sources.filter(s=>!s.resource_id||ids.has(s.resource_id));};
function preferred(resource,key){
 const rows=(seriesByResource.get(resource.resource_id)||[]).filter(s=>s.metric===key);
 return rows.sort((a,b)=>Number(b.summary.observed_bins>0)-Number(a.summary.observed_bins>0)||(resource.hosting==="arc"?Number(b.source.startsWith("InsightsMetrics"))-Number(a.source.startsWith("InsightsMetrics")):Number(b.source==="platform_metrics")-Number(a.source==="platform_metrics"))||b.summary.observed_bins-a.summary.observed_bins)[0];
}
function representative(resource,keys){for(const key of keys){const s=preferred(resource,key);if(s&&s.summary.observed_bins)return s;}for(const key of keys){const s=preferred(resource,key);if(s)return s;}return null;}
function valueOf(s,p){if(!p)return null;const primary=s.primary_aggregation;if(primary==="Total")return p.total;if(primary==="Count")return p.count;if(primary==="Maximum")return p.maximum;if(primary==="Minimum")return p.minimum;return p.mean;}
function cell(s){
 if(!s||s.summary.observed_bins===0)return `<span class="missing">Not collected</span><span class="secondary-text">not zero</span>`;
 const v=s.summary.mean!==null?s.summary.mean:s.summary.last_value;
 const labels={cpu_percent:s.source==="platform_metrics"?"VM platform":"guest CPU",node_cpu_percent:"AKS aggregate",container_cpu_percent:"container limit",plan_cpu_percent:"plan aggregate",memory_available_percent:"physical available",memory_used_percent:"guest used",memory_commit_percent:"Windows commit",node_memory_percent:"AKS RSS",container_memory_percent:"container limit",plan_memory_percent:"plan aggregate",memory_available_bytes:"physical available"};
 return `<span class="measurement">${esc(formatted(v,s.unit))}</span><span class="secondary-text">${esc(labels[s.metric]||s.label)}</span>`;
}
function options(select,values){values.forEach(([value,label])=>{const o=document.createElement("option");o.value=value;o.textContent=label;select.append(o);});}
options($("type-filter"),[...new Set(snapshot.resources.map(r=>r.resource_type))].sort().map(x=>[x,x.replace("microsoft.","")]));
options($("owner-filter"),[...new Set(snapshot.resources.map(r=>r.owner).filter(Boolean))].sort().map(x=>[x,x]));
const metricLabels=new Map(snapshot.series.map(s=>[s.metric,s.label]));
if(!metricLabels.size)metricLabels.set("cpu_percent","CPU utilization - no data collected");
options($("metric-select"),[...metricLabels].sort((a,b)=>a[1].localeCompare(b[1])).map(([a,b])=>[a,b]));
if(!metricLabels.has(st.metric))st.metric=[...metricLabels.keys()][0];$("metric-select").value=st.metric;
function spanText(a,b){const s=utc(a).replace(" UTC",""),e=utc(b).replace(" UTC","");return s.slice(0,10)===e.slice(0,10)?s+" → "+e.slice(11)+" UTC":s+" → "+e+" UTC";}
const grainSeconds=snapshot.window.grain_seconds,grainText=valid(grainSeconds)?(grainSeconds%3600===0?grainSeconds/3600+"-hour bins":grainSeconds%60===0?grainSeconds/60+"-min bins":grainSeconds+"-s bins"):"default bins "+snapshot.window.grain;
$("period-line").textContent="Window "+spanText(snapshot.window.start_utc,snapshot.window.end_utc)+" · "+grainText;$("period-line").title="Default bin width "+snapshot.window.grain;
$("collected-time").textContent=utc(snapshot.collected_utc);$("collected-time").dateTime=snapshot.collected_utc;$("foot-collected").textContent="collected "+utc(snapshot.collected_utc);
$("scope-line").textContent=snapshot.scope.selected_resources+" of "+plural(snapshot.scope.inventory_resources,"inventory resource","inventory resources")+(Object.keys(snapshot.scope.filters||{}).length?" · "+Object.entries(snapshot.scope.filters).map(([k,v])=>k+"="+v).join(", "):"");
if(snapshot.provenance!=="LIVE"){$("provenance-label").textContent=String(snapshot.provenance||"OFFLINE VALIDATION")+" · not a live run";$("provenance-label").className="chip warn";$("snapshot-notice").classList.add("replay");$("snapshot-notice").insertAdjacentHTML("afterbegin","<strong>Source replay / not a live tool execution. </strong>");}
$("footnote").innerHTML='<ul class="limits">'+snapshot.qualifications.map(q=>"<li>"+esc(q)+"</li>").join("")+"<li>Local review policy is included in complete JSON. Source retrieval and monitoring coverage are different.</li></ul>";
$("host-all").innerHTML="All resources<span>"+esc(snapshot.resources.length)+"</span>";$("host-arc").innerHTML="Arc<span>"+esc(snapshot.summary.arc)+"</span>";$("host-azure").innerHTML="Azure<span>"+esc(snapshot.summary.azure)+"</span>";
function barRow(label,parts,total,max,title){return `<div class="brow"><span class="bl" title="${esc(title||label)}">${esc(label).replace(/\//g,"/<wbr>")}</span><span class="bt" role="img" aria-label="${esc(label+": "+parts.map(([n,c,k])=>n+" "+k).join(", "))}">${parts.filter(([n])=>n>0).map(([n,c])=>`<i class="${esc(c)}" style="width:${(n/Math.max(1,max)*100).toFixed(2)}%"></i>`).join("")}</span><b>${esc(total)}</b></div>`;}
function renderOverview(){
 const sm=Object.fromEntries(Object.entries(snapshot.summary||{}).map(([k,v])=>[k,Number(v)||0])),actions=snapshot.actions||[],bySeverity=s=>actions.filter(a=>a.severity===s).length,critical=bySeverity("critical"),warning=bySeverity("warning"),info=bySeverity("info"),errors=sm.source_errors||0,partials=sm.partial_sources||0,sourceGaps=errors+partials;
 const sources=snapshot.sources,count=s=>sources.filter(x=>x.status===s).length,complete=count("complete");
 $("hero-lead").innerHTML=sm.resources?`Of <b>${sm.resources}</b> collected resources, <b>${sm.review}</b> ${sm.review===1?"needs":"need"} an owner review and <b>${sm.unknown}</b> ${sm.unknown===1?"has":"have"} no runtime evidence in this window; <b>${sm.observed}</b> ${sm.observed===1?"was":"were"} observed without a review flag.`:"No resources were collected for this scope. Read the evidence coverage before drawing any conclusion.";
 const verdict=!sm.resources?["unknown","No resources collected"]:critical?["crit","Action required"]:sm.review?["warn","Needs attention"]:(sm.unknown||sourceGaps)?["unknown","Coverage gaps"]:["ok","No review flagged"];
 $("verdict").className="verdict "+verdict[0];$("verdict-title").textContent=verdict[1];
 $("verdict-detail").textContent=[sm.review+" review",sm.unknown+" unknown",sm.observed+" observed"].concat(errors?[plural(errors,"source error","source errors")]:[],partials?[plural(partials,"partial source","partial sources")]:[]).join(" · ");
 const parts=[["review","Review",sm.review],["unknown","Unknown",sm.unknown],["observed","Observed",sm.observed]],total=Math.max(1,sm.resources);
 $("dist").innerHTML=`<div class="track" role="img" aria-label="Resource assessment: ${parts.map(p=>p[2]+" "+p[1].toLowerCase()).join(", ")}">${parts.filter(p=>p[2]>0).map(p=>`<i class="c-${p[0]}" style="width:${(p[2]/total*100).toFixed(2)}%" title="${p[1]} ${p[2]}"></i>`).join("")}</div><div class="legend">${parts.map(p=>`<span><i class="c-${p[0]}"></i>${p[1]} <b>${p[2]}</b></span>`).join("")}</div>`;
 const kpi=(tone,value,label,sub)=>`<div class="kpi ${tone}"><span class="v">${value}</span><span class="l">${esc(label)}</span><span class="s">${esc(sub)}</span></div>`;
 $("kpis").innerHTML=kpi("",sm.resources,"Resources collected",`${snapshot.scope.inventory_resources} in inventory · ${sm.arc} Arc · ${sm.azure} Azure`)
  +kpi(sm.review?"warn":"",sm.review,"Resources to review",plural(snapshot.resources.reduce((n,r)=>n+(r.review_signals||0),0),"review signal","review signals"))
  +kpi(sm.unknown?"unknown":"",sm.unknown,"No runtime evidence","Unknown: not zero, not healthy")
  +kpi(critical?"crit":"",sm.owner_reviews,"Owner checks",(critical?critical+" critical · ":"")+warning+" warning · "+info+" info")
  +kpi("",sm.native_alerts_returned,"Native alerts returned",sm.native_alerts_fired+" still fired at collection")
  +kpi(errors?"crit":partials?"warn":"",`${complete}<small>/ ${sources.length}</small>`,"Source requests complete",(sources.length-complete)+" not complete"+(partials?" · "+partials+" partial":"")+" · "+plural(errors,"error","errors"));
 const reasons=new Map();actions.forEach(a=>{const key=a.title;if(!reasons.has(key))reasons.set(key,{title:a.title,n:0,sev:a.severity});const r=reasons.get(key);r.n++;if(({critical:0,warning:1,info:2})[a.severity]<({critical:0,warning:1,info:2})[r.sev])r.sev=a.severity;});
 const reasonRows=[...reasons.values()].sort((a,b)=>b.n-a.n||a.title.localeCompare(b.title)),maxReason=Math.max(1,...reasonRows.map(r=>r.n));
 $("reason-bars").innerHTML=reasonRows.length?reasonRows.map(r=>{const p=armParts(r.title),label=p?"Native alert · "+p.name:r.title;return barRow(label,[[r.n,"c-"+r.sev,r.sev]],r.n,maxReason,r.title);}).join(""):'<p class="empty" style="padding:0">No owner check is flagged in this snapshot. That does not prove every service is healthy.</p>';
 const types=new Map();snapshot.resources.forEach(r=>{if(!types.has(r.resource_type))types.set(r.resource_type,{review:0,unknown:0,observed:0});types.get(r.resource_type)[r.assessment]++;});
 const typeRows=[...types].map(([t,c])=>({t,c,n:c.review+c.unknown+c.observed})).sort((a,b)=>b.n-a.n||a.t.localeCompare(b.t)),maxType=Math.max(1,...typeRows.map(r=>r.n));
 $("type-bars").innerHTML=typeRows.map(r=>barRow(r.t.replace(/^microsoft\./,""),[[r.c.review,"c-review","review"],[r.c.unknown,"c-unknown","unknown"],[r.c.observed,"c-observed","observed"]],r.n,maxType,r.t)).join("");
 $("type-key").innerHTML='<span><i class="c-review"></i>Review</span><span><i class="c-unknown"></i>Unknown</span><span><i class="c-observed"></i>Observed</span>';
 const statusOrder=["complete","partial","error","not_collected","not_supported","not_configured"],statuses=[...new Set([...statusOrder.filter(s=>count(s)),...sources.map(s=>s.status)])],maxStatus=Math.max(1,...statuses.map(count));
 $("coverage-bars").innerHTML=statuses.map(s=>barRow(cap(s.replaceAll("_"," ")),[[count(s),s==="complete"?"c-complete":s==="error"?"c-error":s==="partial"?"c-partial":"c-gap",s]],count(s),maxStatus)).join("");
}
renderOverview();
function status(message){$("action-status").textContent=message;}
function download(name,text,type){const blob=new Blob([text],{type}),url=URL.createObjectURL(blob),a=document.createElement("a");a.href=url;a.download=name;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);status("Downloaded "+name+" from this recorded snapshot.");}
function csvCell(value){let s=value===null||value===undefined?"":typeof value==="object"?JSON.stringify(value):String(value);if(typeof value==="string"&&/^[\s\uFEFF]*[=+\-@]/u.test(s))s="'"+s;return '"'+s.replaceAll('"','""')+'"';}
function csv(rows,fields){return "\uFEFF"+[fields.map(csvCell).join(","),...rows.map(row=>fields.map(key=>csvCell(row[key])).join(","))].join("\r\n");}
const filePrefix="infra-"+snapshot.collected_utc.replace(/[:-]/g,"");
function exportRows(suffix,rows,fields){const context={provenance:snapshot.provenance,snapshot_collected_utc:snapshot.collected_utc,window_start_utc:snapshot.window.start_utc,window_end_utc:snapshot.window.end_utc,window_grain:snapshot.window.grain};download(filePrefix+"-"+suffix+".csv",csv(rows.map(row=>({...row,...context})),[...Object.keys(context),...fields]),"text/csv;charset=utf-8");}
const resourceFields=["resource_id","name","hosting","resource_type","resource_group","location","owner","os","size","power_state","provisioning_state","arc_connection","assessment","series_count","review_signals","heartbeat","health","tags","os_type","os_sku","os_version","arc_agent_version","arc_status_changed_utc","arc_administration","arc_extensions"];
const signalFields=["signal_id","resource_id","kind","metric","severity","state","time_utc","end_utc","title","source","series_id","details","evidence"];
const actionFields=["action_id","resource_id","resource_name","owner","severity","state","title","kinds","review","evidence_signal_ids","automatic_action"];
const eventFields=["event_id","resource_id","kind","time_utc","severity","state","title","source","details","alert_id","current_condition","qualification"];
const sourceFields=["source","resource_id","workspace_id","status","records","collected_utc","note","error","not_exposed","native_metrics","grain_seconds","notes","pages","subscription_rows_read","declared_subscription_rows","selected_machines","row_limit","page_limit","time_budget_seconds"];
function renderFleet(){
 const active=document.activeElement,restore=active?.dataset?.compare?{compare:active.dataset.compare}:active?.hasAttribute?.("data-pin-focus")?{pin:true}:null;
 const rows=shownResources(),visible=rows.slice(0,st.fleetLimit),ids=new Set(rows.map(r=>r.resource_id));
 const previousFocus=st.focus;
 if(st.focus&&!ids.has(st.focus))st.focus=null;
 for(const id of [...st.compare])if(!ids.has(id))st.compare.delete(id);
 if(!st.focus&&rows.length)st.focus=rows.find(r=>r.series_count)?.resource_id||rows[0].resource_id;
 if(st.focus&&previousFocus!==st.focus){const r=resources.get(st.focus),current=preferred(r,st.metric);if(!current?.summary.observed_bins){const candidate=(seriesByResource.get(st.focus)||[]).find(s=>s.summary.observed_bins);if(candidate){st.metric=candidate.metric;$("metric-select").value=st.metric;}}}
 if(!st.compare.size&&st.focus)st.compare.add(st.focus);
 const counts={review:0,unknown:0,observed:0};rows.forEach(r=>counts[r.assessment]++);
 $("summary-line").innerHTML=`<span><b>${rows.length}</b> in this view</span><span>${badge("review","Review")}<b>${counts.review}</b></span><span>${badge("unknown","Unknown")}<b>${counts.unknown}</b></span><span>${badge("observed","Observed")}<b>${counts.observed}</b></span><span class="summary-scope">${esc(snapshot.scope.selected_resources)} collected / ${esc(snapshot.scope.inventory_resources)} inventory resources</span>`;
 $("fleet-count").textContent=rows.length+" matched; choose a name to inspect, check a box to compare.";
 document.querySelectorAll("th[data-sort-key]").forEach(th=>{if(th.dataset.sortKey===st.sort.key)th.setAttribute("aria-sort",st.sort.dir>0?"ascending":"descending");else th.removeAttribute("aria-sort");});
 $("fleet-body").innerHTML=visible.map(r=>{
  const cpu=representative(r,cpuKeys);
  const memory=representative(r,memoryKeys);
  return `<tr class="${r.resource_id===st.focus?"selected":""}"><td class="check"><input type="checkbox" data-compare="${esc(r.resource_id)}" aria-label="Compare ${esc(r.name)}" ${st.compare.has(r.resource_id)?"checked":""} ${st.compare.size>=3&&!st.compare.has(r.resource_id)?"disabled":""}></td><td><button class="resource-name" type="button" data-focus="${esc(r.resource_id)}">${esc(r.name)}</button><span class="secondary-text">${esc(r.hosting==="arc"?"Arc":"Azure")} · <span class="nw">${esc(r.resource_type.split("/").slice(1).join("/"))}</span> · <span class="nw">${esc(r.resource_group)}</span></span></td><td>${cell(cpu)}</td><td>${cell(memory)}</td><td>${badge(r.assessment,r.assessment==="observed"?"Observed":r.assessment==="review"?"Review":"Unknown")}<span class="secondary-text">${r.review_signals?plural(r.review_signals,"review signal","review signals"):r.series_count?r.series_count+" collected series":"no runtime series"}</span></td></tr>`;
 }).join("");
 $("fleet-empty").hidden=rows.length!==0;$("fleet-page").textContent="Displayed "+visible.length+" / "+rows.length+" matched; exports include every match.";$("fleet-more").hidden=visible.length>=rows.length;
 $("nav-fleet").textContent=rows.length;
 renderInspector();renderChart();renderReviews();renderEvents();renderSources();
 if(restore?.compare){const input=[...document.querySelectorAll("[data-compare]")].find(x=>x.dataset.compare===restore.compare);input?.focus({preventScroll:true});}else if(restore?.pin)document.querySelector("[data-pin-focus]")?.focus({preventScroll:true});
}
function arcDetails(r){
 if(r.resource_type!=="microsoft.hybridcompute/machines")return "";
 const admin=r.arc_administration,rows=extensionsByResource.get(r.resource_id)||[],rule=(snapshot.arc_baselines||[]).find(b=>b.baseline_id===admin?.baseline_id),boolean=value=>value===true?"true":value===false?"false":"Unknown / not supplied";
 if(!admin)return '<details open><summary>Arc administration</summary><p class="secondary-text">Not collected by this historical source version. Agent/OS lifecycle, extensions and policy remain Unknown.</p></details>';
 const facts=[["Agent version",r.arc_agent_version||"Unknown / not supplied"],["OS type / SKU",[r.os_type,r.os_sku].filter(Boolean).join(" / ")||"Unknown / not supplied"],["OS version",r.os_version||"Unknown / not supplied"],["Arc state changed",utc(r.arc_status_changed_utc)],["Metadata read",utc(admin.collected_utc)],["Baseline",admin.baseline_status+(admin.baseline_id?" / "+admin.baseline_id:"")],["Agent review",admin.agent_version_status+(admin.agent_review_target?" / target "+admin.agent_review_target:"")],["Agent / OS support","Unknown / not evaluated"],["Extension source",admin.extension_source_status+" / "+rows.length+" observed rows"]];
 return `<details open><summary>Arc administration and extensions (${rows.length})</summary>${badge(admin.assessment,"Administration "+admin.assessment)}<dl class="facts">${facts.map(([key,value])=>"<dt>"+esc(key)+"</dt><dd>"+esc(value)+"</dd>").join("")}</dl><p class="secondary-text">${esc(admin.qualification)} This separate assessment does not relabel measured guest telemetry when optional policy is unset. Heartbeat above is a separate observation at the measurement-window end. <a href="#sources">Read source coverage</a>.</p>${rule?'<p class="secondary-text">Baseline owner: '+esc(rule.owner)+'<br>Reference: '+esc(rule.reference)+'<br>As of '+esc(utc(rule.as_of_utc))+'; expires '+esc(utc(rule.valid_until_utc))+'<br>'+esc(rule.notes||"")+'</p>':""}${admin.unknowns.length?'<p class="secondary-text">Unknown: '+esc(admin.unknowns.map(x=>x.replaceAll("_"," ")).join("; "))+'</p>':""}<ul class="detail-list">${rows.length?rows.map(e=>`<li><strong>${esc(e.name||e.extension_id)}</strong>${badge(e.assessment)}<p>${esc(e.publisher||"Unknown publisher")} / ${esc(e.extension_type||"Unknown type")} / ${esc(e.location||"Unknown location")}</p><p>Configured handler: ${esc(e.type_handler_version||"Unknown")}; instance-view version: ${esc(e.instance_view_version||"Unknown")}<br>Provisioning: ${esc(e.provisioning_state||"Unknown")}<br>Automatic platform upgrade: ${esc(boolean(e.enable_automatic_upgrade))}; minor version at deployment: ${esc(boolean(e.auto_upgrade_minor_version))}</p><p>Neither Succeeded nor an extension name proves sensor health or newer-version availability.</p><code class="resource-id">${idWrap(e.extension_id)}</code><p>Source ${esc(e.source)} / read ${esc(utc(e.collected_utc))}</p>${e.checks?.length?'<p class="evidence-json">'+esc(JSON.stringify(e.checks))+'</p>':""}</li>`).join(""):'<li>No extension rows returned. '+(admin.extension_source_status==="complete"?"This completed permission-filtered read does not independently prove absence.":"The source is incomplete/unavailable; extension presence is Unknown.")+'</li>'}</ul></details>`;
}
function renderInspector(){
 const r=resources.get(st.focus);
 if(!r){$("inspector").innerHTML='<div class="empty"><strong>Select a resource.</strong>Choose a matching resource to inspect its actual evidence.</div>';return;}
 const all=seriesByResource.get(r.resource_id)||[],signals=snapshot.signals.filter(s=>s.resource_id===r.resource_id),portal="https://portal.azure.com/#@"+encodeURIComponent(snapshot.scope.tenant_id)+"/resource"+r.resource_id.split("/").map(encodeURIComponent).join("/")+"/overview";
 const facts=[["Hosting",r.hosting==="arc"?"Azure Arc":"Azure-native"],["Owner",r.owner||"Unassigned"],["Group",r.resource_group],["Location",r.location],["OS / size",[r.os,r.size].filter(Boolean).join(" / ")||"Not supplied"],["Power state",r.power_state||"Not supplied"],["Arc connection",r.arc_connection||"Not applicable / not supplied"],["Platform health",r.health?.availability_state||"Unknown / not returned"],["Heartbeat",r.heartbeat?utc(r.heartbeat.last_sample_utc):"Not collected"],["Assessment",cap(r.assessment)+" - not a health certificate"]];
 const selected=preferred(r,st.metric);
 const overview=selected?.summary.observed_bins?`<dl class="facts"><dt>Selected mean</dt><dd class="measurement">${esc(formatted(selected.summary.mean,selected.unit))}</dd><dt>Source maximum</dt><dd class="measurement">${esc(formatted(selected.summary.maximum_observation,selected.unit))}</dd><dt>Recorded bins</dt><dd>${selected.summary.observed_bins}/${selected.summary.expected_bins} / ${selected.grain_seconds/60} min</dd></dl>`:"";
 $("inspector").innerHTML=`<div class="inspector-head"><h3 class="inspector-title" id="selected-resource-title" tabindex="-1">${esc(r.name)}</h3>${badge(r.assessment)}</div><p class="resource-kind">${esc(r.resource_type)}</p><dl class="facts">${facts.map(([a,b])=>"<dt>"+esc(a)+"</dt><dd>"+esc(b)+"</dd>").join("")}</dl>${selected?'<h4 class="metric-title">'+esc(selected.label)+'</h4>':""}${overview}<div class="inline-buttons"><button type="button" data-pin-focus class="minor-action">${st.compare.has(r.resource_id)?"Pinned in recorder":"Pin in recorder"}</button><button type="button" data-export-resource class="minor-action">Resource JSON</button><a class="portal-link" href="${esc(portal)}" target="_blank" rel="noopener noreferrer">Open in Azure portal${extIcon}<span class="sr-only"> (opens in a new tab)</span></a></div><code class="resource-id">${idWrap(r.resource_id)}</code>${arcDetails(r)}<details><summary>Measurements (${all.length} series)</summary><ul class="detail-list">${all.length?all.map(s=>`<li><strong>${esc(s.label)}</strong><span class="num">Mean ${esc(formatted(s.summary.mean,s.unit))} / source max ${esc(formatted(s.summary.maximum_observation,s.unit))}</span><p>${s.summary.observed_bins}/${s.summary.expected_bins} bins; ${s.grain_seconds/60} min; ${esc(s.source)}<br>${esc(s.summary.mean_basis)}</p><span>Latest ${s.summary.last_sample_utc?"sample "+esc(utc(s.summary.last_sample_utc)):"bin start "+esc(utc(s.summary.last_bin_utc))}</span><p>${esc(s.semantics)}</p>${Object.keys(s.dimensions).length?'<p>Dimensions: '+esc(JSON.stringify(s.dimensions))+'</p>':""}</li>`).join(""):"<li>No collected series in this snapshot.</li>"}</ul></details><details><summary>Signals and review basis (${signals.length})</summary><ul class="detail-list">${signals.length?signals.map(s=>`<li>${titleHtml(s.title)}<span class="pills">${badge(s.severity)} ${badge(s.state)}</span><p>${esc(s.details)}</p><p class="evidence-json">${esc(JSON.stringify(s.evidence))}</p><span class="secondary-text">Evidence ${esc(s.signal_id)} / ${esc(s.source)}</span></li>`).join(""):"<li>No configured review signal observed.</li>"}</ul></details><details><summary>Native state and ownership evidence</summary><ul class="detail-list"><li><strong>Current platform health</strong><p class="${r.health?"evidence-json":""}">${esc(r.health?JSON.stringify(r.health):"Not returned; guest and Arc connection observations are separate.")}</p></li><li><strong>Actual tags</strong><p class="evidence-json">${esc(JSON.stringify(r.tags))}</p></li></ul></details>`;
}
const svgNS="http://www.w3.org/2000/svg";
function svgEl(tag,attrs,text){const e=document.createElementNS(svgNS,tag);Object.entries(attrs||{}).forEach(([k,v])=>e.setAttribute(k,v));if(text!==undefined)e.textContent=text;return e;}
function chartWindow(){const end=Date.parse(snapshot.window.end_utc),start=Date.parse(snapshot.window.start_utc);return[Math.max(start,st.range==="all"?start:end-Number(st.range)*3600000),end];}
function renderChart(){
 const [start,end]=chartWindow(),traces=[...st.compare].map(id=>{const r=resources.get(id);return{r,s:r?preferred(r,st.metric):null};}),unit=traces.find(t=>t.s)?.s.unit||"Percent";
 st.traces=traces;$("chart-legend").innerHTML=traces.map((t,i)=>`<div class="legend-entry"><span class="line-key" style="background:${colors[i]}"></span><span><strong>${esc(t.r?.name||"Unknown resource")}</strong><small>${esc(t.s?`${t.s.source} / ${t.s.grain_seconds/60} min / ${t.s.unit}`:"No applicable series for this metric")}${t.s?`<br>${t.s.summary.observed_bins}/${t.s.summary.expected_bins} observed bins; ${esc(t.s.primary_aggregation||"log Average")} / ${esc(t.s.native_metric)}`:""}</small></span></div>`).join("");
 const frame=$("chart-frame"),style=getComputedStyle(frame),w=Math.max(300,frame.clientWidth-parseFloat(style.paddingLeft)-parseFloat(style.paddingRight)),h=250,left=65,right=20,top=20,bottom=38,innerW=w-left-right,innerH=h-top-bottom;
 const svg=svgEl("svg",{viewBox:`0 0 ${w} ${h}`,role:"img","aria-label":(metricLabels.get(st.metric)||st.metric)+" time series. Missing samples remain gaps."});
 svg.append(svgEl("title",{},(metricLabels.get(st.metric)||st.metric)+" - recorded UTC observations"));
 let ymax=unit.toLowerCase()==="percent"?100:1,observed=0;
 traces.forEach(t=>{if(t.s)t.s.points.forEach(p=>{const x=Date.parse(p.time_utc);if(x>=start&&x<end){const v=valueOf(t.s,p);if(valid(v)){ymax=Math.max(ymax,v);observed++;}if($("show-max").checked&&valid(p.maximum))ymax=Math.max(ymax,p.maximum);}});});
 if(unit.toLowerCase()!=="percent")ymax*=1.08;else if(ymax>100)ymax=Math.ceil(ymax/10)*10;
 const xx=x=>left+(x-start)/Math.max(1,end-start)*innerW,yy=y=>top+innerH-(y/ymax)*innerH;
 for(let i=0;i<=4;i++){const y=top+i*innerH/4;svg.append(svgEl("line",{x1:left,y1:y,x2:w-right,y2:y,stroke:"#dbe3de","stroke-width":1}));svg.append(svgEl("text",{x:left-9,y:y+4,"text-anchor":"end",fill:"#526660","font-size":12},formatted(ymax*(1-i/4),unit)));}
 [start,(start+end)/2,end].forEach((x,i)=>svg.append(svgEl("text",{x:xx(x),y:h-12,"text-anchor":i===0?"start":i===2?"end":"middle",fill:"#526660","font-size":12},new Date(x).toISOString().slice(w<500?8:5,16).replace("T"," ")+"Z")));
 function pathFor(series,key){let d="",last=null;series.points.forEach(p=>{const x=Date.parse(p.time_utc),v=key==="value"?valueOf(series,p):p.maximum;if(x<start||x>=end||!valid(v)){last=null;return;}const contiguous=last!==null&&x-last===series.grain_seconds*1000;d+=(contiguous?"L":"M")+xx(x).toFixed(2)+","+yy(v).toFixed(2);last=x;});return d;}
 function isolatedMarkers(series,key,color){const rows=series.points.filter(p=>Date.parse(p.time_utc)>=start&&Date.parse(p.time_utc)<end);rows.forEach((p,j)=>{const value=key==="value"?valueOf(series,p):p.maximum;if(!valid(value))return;const time=Date.parse(p.time_utc),previous=rows[j-1],next=rows[j+1],previousValue=previous?(key==="value"?valueOf(series,previous):previous.maximum):null,nextValue=next?(key==="value"?valueOf(series,next):next.maximum):null,linkedBefore=valid(previousValue)&&time-Date.parse(previous.time_utc)===series.grain_seconds*1000,linkedAfter=valid(nextValue)&&Date.parse(next.time_utc)-time===series.grain_seconds*1000;if(!linkedBefore&&!linkedAfter)svg.append(svgEl("circle",{cx:xx(time),cy:yy(value),r:2.8,fill:key==="value"?color:"#fff",stroke:color,"stroke-width":1.3,"data-isolated-observation":"true"}));});}
 traces.forEach((t,i)=>{if(!t.s)return;svg.append(svgEl("path",{d:pathFor(t.s,"value"),fill:"none",stroke:colors[i],"stroke-width":2.2,"stroke-linecap":"round"}));isolatedMarkers(t.s,"value",colors[i]);if($("show-max").checked){svg.append(svgEl("path",{d:pathFor(t.s,"max"),fill:"none",stroke:colors[i],"stroke-width":1.25,"stroke-dasharray":"5 4"}));isolatedMarkers(t.s,"max",colors[i]);}});
 if(!observed){svg.append(svgEl("text",{x:w/2,y:h/2-5,"text-anchor":"middle",fill:"#18312e","font-size":17},"No numeric observations for this selection."));svg.append(svgEl("text",{x:w/2,y:h/2+20,"text-anchor":"middle",fill:"#526660","font-size":12},"Choose another metric/resource. Blank is not zero."));}
 const crosshair=svgEl("line",{x1:left,y1:top,x2:left,y2:h-bottom,stroke:"#8da69a","stroke-width":1,"stroke-dasharray":"3 3",visibility:"hidden"});svg.append(crosshair);
 $("chart-frame").replaceChildren(svg);st.chart={crosshair,xx,start,end};
 st.binTimes=[...new Set(traces.flatMap(t=>t.s?t.s.points.map(p=>Date.parse(p.time_utc)).filter(t=>t>=start&&t<end):[]))].sort((a,b)=>a-b);
 $("bin-slider").max=Math.max(0,st.binTimes.length-1);$("bin-slider").value=Math.max(0,st.binTimes.length-1);$("bin-slider").disabled=!st.binTimes.length;renderBin();
 svg.addEventListener("pointermove",event=>{if(!st.binTimes.length)return;const rect=svg.getBoundingClientRect(),px=(event.clientX-rect.left)/rect.width*w,t=start+(Math.max(left,Math.min(w-right,px))-left)/innerW*(end-start);let index=0;for(let i=1;i<st.binTimes.length;i++)if(Math.abs(st.binTimes[i]-t)<Math.abs(st.binTimes[index]-t))index=i;$("bin-slider").value=index;renderBin();});
}
function renderBin(){
 if(!st.binTimes.length){$("bin-readout").textContent="No recorded bins for this selection. Missing is not zero.";return;}
 const time=st.binTimes[Number($("bin-slider").value)],parts=[];
 st.traces.forEach(t=>{if(!t.s){parts.push((t.r?.name||"Resource")+": no applicable series");return;}const p=t.s.points.find(p=>Date.parse(p.time_utc)<=time&&Date.parse(p.time_utc)+t.s.grain_seconds*1000>time);parts.push(t.r.name+": "+formatted(valueOf(t.s,p),t.s.unit)+(p&&valid(p.maximum)?" / source max "+formatted(p.maximum,t.s.unit):"")+(p?.edge_bin?" / partial edge bin":""));});
 $("bin-readout").textContent=utc(new Date(time).toISOString())+" | "+parts.join(" | ");
 if(st.chart){const x=st.chart.xx(time);st.chart.crosshair.setAttribute("x1",x);st.chart.crosshair.setAttribute("x2",x);st.chart.crosshair.setAttribute("visibility","visible");}
}
function renderReviews(){
 const rows=matchingActions(),visible=rows.slice(0,st.reviewLimit);$("review-list").innerHTML=visible.length?visible.map(a=>`<li><div class="review-row"><div>${titleHtml(a.title)}</div>${badge(a.severity)}</div><div class="review-meta"><button type="button" class="resource-name minor-action" data-focus="${esc(a.resource_id)}">${esc(a.resource_name)}</button><span>Owner: ${esc(a.owner||"Unassigned")}</span></div>${a.review.map(x=>"<p>"+esc(x)+"</p>").join("")}<span class="secondary-text">${plural(a.evidence_signal_ids.length,"evidence signal","evidence signals")} · no automatic action</span></li>`).join(""):'<li class="empty"><strong>No owner review is flagged in this view.</strong>That does not prove all services are healthy. Inspect sources and coverage.</li>';
 $("review-count").textContent="Displayed "+visible.length+" / "+rows.length+" matched.";$("review-more").hidden=visible.length>=rows.length;$("nav-reviews").textContent=rows.length;
}
function renderEvents(){
 const rows=matchingEvents(),visible=rows.slice(0,st.eventLimit);$("event-list").innerHTML=visible.length?visible.map(e=>`<li><time datetime="${esc(e.time_utc)}">${esc(utc(e.time_utc))}</time>${armParts(e.title)?titleHtml(e.title,true):`<strong>${esc(e.title)}</strong>`}<span class="event-source">${esc(resources.get(e.resource_id)?.name||e.resource_id)} · ${esc(e.source)} · ${esc(e.kind)}</span><p>${esc(e.details||e.qualification||"Native source observation.")}</p><span class="pills">${badge(e.state)} ${badge(e.severity)}</span>${e.current_condition?"<p>Current native condition: "+esc(e.current_condition)+"</p>":""}</li>`).join(""):'<li class="empty"><strong>No '+(st.eventMode==="native"?"native events":"local observations")+' returned for this view.</strong>This is not proof of no incidents. Alerts lookback is approximately 30 days and may not cover the full calendar month.</li>';
 $("event-count").textContent="Displayed "+visible.length+" / "+rows.length+" matched; newest first.";$("event-more").hidden=visible.length>=rows.length;$("nav-events").textContent=snapshot.events.filter(e=>shownIds().has(e.resource_id)).length;
}
function renderSources(){
 const all=matchingSources(),rows=st.printing?all.filter(s=>s.status!=="complete"):all,visible=rows.slice(0,st.sourceLimit);$("source-body").innerHTML=visible.map(s=>`<tr><td><span class="source-name">${esc(s.source)}</span><span class="secondary-text">${esc(s.resource_id?resources.get(s.resource_id)?.name||s.resource_id:s.workspace_id?"Allowed workspace "+s.workspace_id:"Collection scope")}</span></td><td>${badge(s.status)}</td><td class="num">${numeric(s.records,0)}</td><td class="source-description">${esc(s.note)}${s.error?'<span class="source-error">'+esc(s.error.code+(s.error.http_status?" / HTTP "+s.error.http_status:"")+": "+s.error.message)+'</span>':""}${s.source==="arc_extensions"?'<p>Accepted pages: '+esc(s.pages)+'; subscription rows read: '+esc(s.subscription_rows_read)+' / declared '+esc(s.declared_subscription_rows??"Unknown")+'. Matched extension rows: '+esc(s.records)+'. These are not VM counts or an approved-fleet denominator.</p>':""}${s.not_exposed?.length?'<details><summary>'+s.not_exposed.length+' metrics not exposed / not requested at a safe grain</summary>'+s.not_exposed.map(x=>"<p>"+esc(x.native_metric+": "+x.reason)+"</p>").join("")+"</details>":""}${s.requested_history_partly_outside_retention?"<p><strong>The requested calendar window extends beyond native alert lookback.</strong></p>":""}</td></tr>`).join("");
 $("source-count").textContent=st.printing?"Printed: the "+rows.length+" of "+all.length+" applicable source results that are not complete. Every result, including complete requests, is in the CSV and complete JSON exports.":"Displayed "+visible.length+" / "+rows.length+" applicable source results; global source context is retained.";$("source-more").hidden=visible.length>=rows.length;$("nav-sources").textContent=all.length;
}
function resetPages(){st.fleetLimit=pageSize;st.reviewLimit=pageSize;st.eventLimit=pageSize;st.sourceLimit=30;}
["search","type-filter","state-filter","owner-filter","arc-admin-filter"].forEach(id=>$(id).addEventListener(id==="search"?"input":"change",()=>{st.search=$("search").value;st.type=$("type-filter").value;st.assessment=$("state-filter").value;st.owner=$("owner-filter").value;st.arcAdmin=$("arc-admin-filter").value;resetPages();renderFleet();}));
$("reset").addEventListener("click",()=>{["search","type-filter","state-filter","owner-filter","arc-admin-filter"].forEach(id=>$(id).value="");st.hosting="all";st.search=st.type=st.assessment=st.owner=st.arcAdmin="";st.focus=null;st.compare.clear();document.querySelectorAll("[data-hosting]").forEach(b=>b.setAttribute("aria-pressed",String(b.dataset.hosting==="all")));resetPages();renderFleet();status("Filters reset. The underlying recorded data did not change.");});
document.addEventListener("click",event=>{
 const b=event.target.closest("button");if(!b)return;
 if(b.dataset.sort){const key=b.dataset.sort;st.sort=st.sort.key===key?{key,dir:-st.sort.dir}:{key,dir:key==="cpu"||key==="memory"?-1:1};resetPages();renderFleet();status("Sorted by "+b.textContent.toLowerCase()+", "+(st.sort.dir>0?"ascending":"descending")+". Missing measurements stay last.");}
 if(b.dataset.hosting){st.hosting=b.dataset.hosting;document.querySelectorAll("[data-hosting]").forEach(x=>x.setAttribute("aria-pressed",String(x===b)));resetPages();renderFleet();}
 if(b.dataset.focus){st.focus=b.dataset.focus;renderFleet();$("selected-resource-title")?.focus({preventScroll:true});if(window.innerWidth<=1180)$("inspector").scrollIntoView({block:"start",behavior:"auto"});status("Inspecting "+resources.get(st.focus)?.name+". Resource sources and owner evidence are shown.");}
 if(b.hasAttribute("data-pin-focus")&&st.focus){if(st.compare.has(st.focus)){if(st.compare.size>1)st.compare.delete(st.focus);}else if(st.compare.size<3)st.compare.add(st.focus);else status("Three resources are already pinned. Uncheck one before adding another.");renderFleet();}
 if(b.hasAttribute("data-export-resource")&&st.focus){const r=resources.get(st.focus);download(filePrefix+"-resource.json",JSON.stringify({schema_version:snapshot.schema_version,provenance:snapshot.provenance,collected_utc:snapshot.collected_utc,window:snapshot.window,resource:r,extensions:extensionsByResource.get(r.resource_id)||[],arc_baselines:snapshot.arc_baselines||[],series:seriesByResource.get(r.resource_id)||[],signals:snapshot.signals.filter(x=>x.resource_id===r.resource_id),events:snapshot.events.filter(x=>x.resource_id===r.resource_id),actions:snapshot.actions.filter(x=>x.resource_id===r.resource_id),sources:snapshot.sources.filter(x=>!x.resource_id||x.resource_id===r.resource_id)},null,2),"application/json");}
 if(b.dataset.eventMode){st.eventMode=b.dataset.eventMode;st.eventLimit=pageSize;document.querySelectorAll("[data-event-mode]").forEach(x=>x.setAttribute("aria-pressed",String(x===b)));renderEvents();}
});
$("fleet-body").addEventListener("change",event=>{const input=event.target;if(!input.dataset.compare)return;if(input.checked&&st.compare.size<3)st.compare.add(input.dataset.compare);else st.compare.delete(input.dataset.compare);renderFleet();});
$("fleet-more").addEventListener("click",()=>{st.fleetLimit+=pageSize;renderFleet();});$("review-more").addEventListener("click",()=>{st.reviewLimit+=pageSize;renderReviews();});$("event-more").addEventListener("click",()=>{st.eventLimit+=pageSize;renderEvents();});$("source-more").addEventListener("click",()=>{st.sourceLimit+=30;renderSources();});
$("metric-select").addEventListener("change",()=>{st.metric=$("metric-select").value;renderInspector();renderChart();});$("range-select").addEventListener("change",()=>{st.range=$("range-select").value;renderChart();});$("show-max").addEventListener("change",renderChart);$("bin-slider").addEventListener("input",renderBin);
$("export-resources").addEventListener("click",()=>exportRows("resources-filtered",shownResources().map(r=>({...r,arc_extensions:extensionsByResource.get(r.resource_id)||[]})),resourceFields));$("export-signals").addEventListener("click",()=>exportRows("signals-filtered",matchingSignals(),signalFields));$("export-actions").addEventListener("click",()=>exportRows("actions-filtered",matchingActions(),actionFields));$("export-events").addEventListener("click",()=>exportRows(st.eventMode==="native"?"native-events-filtered":"local-observations-filtered",matchingEvents(),st.eventMode==="native"?eventFields:signalFields));$("export-sources").addEventListener("click",()=>exportRows("sources-filtered",matchingSources(),sourceFields));
$("export-json").addEventListener("click",()=>download(filePrefix+"-complete.json",JSON.stringify(snapshot),"application/json"));
$("export-series").addEventListener("click",()=>{const rows=[];st.traces.forEach(t=>{if(t.s)t.s.points.forEach(p=>rows.push({resource_id:t.s.resource_id,resource_name:t.r.name,series_id:t.s.series_id,metric:t.s.metric,source:t.s.source,unit:t.s.unit,native_metric:t.s.native_metric,primary_aggregation:t.s.primary_aggregation||"log Average",count_basis:t.s.count_basis,count_is_value:t.s.count_is_value,observed_bins:t.s.summary.observed_bins,expected_bins:t.s.summary.expected_bins,grain_seconds:t.s.grain_seconds,dimensions:t.s.dimensions,...p}));});exportRows("pinned-traces-complete",rows,["resource_id","resource_name","series_id","metric","source","unit","native_metric","primary_aggregation","count_basis","count_is_value","observed_bins","expected_bins","grain_seconds","dimensions","time_utc","mean","minimum","maximum","total","count","first_sample_utc","last_sample_utc","edge_bin"]);});
$("print-report").addEventListener("click",()=>window.print());$("print-top").addEventListener("click",()=>window.print());
let printLimits=null;
function expandForPrint(){if(printLimits)return;printLimits=[st.fleetLimit,st.reviewLimit,st.eventLimit,st.sourceLimit];st.fleetLimit=st.reviewLimit=st.eventLimit=st.sourceLimit=Infinity;st.printing=true;renderFleet();}
function restoreAfterPrint(){if(!printLimits)return;[st.fleetLimit,st.reviewLimit,st.eventLimit,st.sourceLimit]=printLimits;printLimits=null;st.printing=false;renderFleet();}
window.addEventListener("beforeprint",expandForPrint);window.addEventListener("afterprint",restoreAfterPrint);const printQuery=matchMedia("print");printQuery.addEventListener?.("change",event=>event.matches?expandForPrint():restoreAfterPrint());
const pageStyle=document.createElement("style"),cssText=value=>'"'+String(value).replace(/[\\"]/g,"\\$&").replace(/[\r\n]+/g," ")+'"';pageStyle.textContent="@page{@bottom-left{content:"+cssText("Infrastructure operations · Azure SRE Agent · collected "+utc(snapshot.collected_utc)+" · "+(snapshot.provenance==="LIVE"?"read-only snapshot":String(snapshot.provenance)))+";font:8pt \"Segoe UI\",system-ui,sans-serif;color:#526660}@bottom-right{content:\"Page \" counter(page) \" of \" counter(pages);font:8pt \"Segoe UI\",system-ui,sans-serif;color:#526660}}";document.head.append(pageStyle);
const navLinks=[...document.querySelectorAll(".bar-nav a")],navTargets=navLinks.map(a=>document.querySelector(a.getAttribute("href")));
function markNav(link){navLinks.forEach(x=>x===link?x.setAttribute("aria-current","location"):x.removeAttribute("aria-current"));}
navLinks.forEach(a=>a.addEventListener("click",()=>markNav(a)));
let spyQueued=false;function spy(){spyQueued=false;let best=-Infinity,tied=[];navTargets.forEach((target,i)=>{const top=target?target.getBoundingClientRect().top:Infinity;if(top>innerHeight*0.3)return;if(top>best+1){best=top;tied=[navLinks[i]];}else if(top>=best-1)tied.push(navLinks[i]);});const now=navLinks.find(a=>a.hasAttribute("aria-current"));markNav(tied.includes(now)?now:tied[0]||null);}
addEventListener("scroll",()=>{if(!spyQueued){spyQueued=true;requestAnimationFrame(spy);}},{passive:true});spy();
let resizeTimer;window.addEventListener("resize",()=>{clearTimeout(resizeTimer);resizeTimer=setTimeout(renderChart,150);});
renderFleet();window.infraReport={snapshot,getFilteredResources:shownResources,getFilteredSignals:matchingSignals,getPinnedSeries:()=>st.traces.filter(t=>t.s).map(t=>t.s),getState:()=>({hosting:st.hosting,metric:st.metric,focus:st.focus,compare:[...st.compare]})};
})();
</script>
</body>
</html>"""


def _render_html(snapshot, document=None):
    return (
        REPORT_HTML.replace("__SNAPSHOT_DATA__", _safe_json(document or _json_document(snapshot)), 1)
        .replace("__COMPANY_LOGO__", _company_logo_markup(), 1)
    )


def _artifact_directory():
    try:
        root = Path.cwd().resolve(strict=True)
        if root == Path(root.anchor) or not root.is_dir():
            raise EvidenceError("unsafe_artifact_root", "Runtime cwd must be an existing non-filesystem-root directory.", "artifact_storage")
        if OUTPUT_DIRECTORY != Path("infrastructure-operations-reports"):
            raise EvidenceError("unsafe_artifact_directory", "Only the fixed report subdirectory is permitted.", "artifact_storage")
        nominal = root / OUTPUT_DIRECTORY
        directory = nominal.resolve()
    except (OSError, RuntimeError) as exc:
        if isinstance(exc, EvidenceError):
            raise
        raise EvidenceError("unsafe_artifact_root", "Could not resolve the runtime-owned export root.", "artifact_storage") from exc
    if directory != nominal or not directory.is_relative_to(root) or directory == root:
        raise EvidenceError("unsafe_artifact_directory", "Report directory is a symlink or escapes the fixed runtime root.", "artifact_storage")
    return root, directory


def _sharing_fields(root, paths):
    result = {"sharing_mode": "local_files_only", "http_verified": False}
    match = re.fullmatch(
        r"/root/sreagent/terminalRoot/tmp/ThreadFiles/([0-9a-fA-F-]{36})", root.as_posix()
    )
    if match is None:
        return result
    try:
        if str(UUID(match[1])) != match[1].casefold():
            return result
    except ValueError:
        return result
    expected = root / "infrastructure-operations-reports"
    aliases = {}
    for key, path in paths.items():
        if (
            path.parent != expected
            or not re.fullmatch(r"infra-[0-9TZ]+-[0-9a-f]{8}(?:-resources\.csv|-signals\.csv|-snapshot\.json|\.html)", path.name)
        ):
            raise EvidenceError("unsafe_sharing_path", "Native file aliases must reference the exact guarded report artifacts.", "artifact_storage")
        aliases[key.removesuffix("_path") + "_url"] = (
            "/api/files/tmp/ThreadFiles/" + match[1] + "/infrastructure-operations-reports/" + quote(path.name, safe="")
        )
    result.update(sharing_mode="native_ui", **aliases)
    return result


def _write_report(snapshot):
    root, directory = _artifact_directory()
    prefix = "infra-" + snapshot["collected_utc"].replace(":", "").replace("-", "") + "-" + uuid4().hex[:8]
    paths = {
        "report_path": directory / (prefix + ".html"),
        "resources_csv_path": directory / (prefix + "-resources.csv"),
        "signals_csv_path": directory / (prefix + "-signals.csv"),
        "snapshot_path": directory / (prefix + "-snapshot.json"),
    }
    document = _json_document(snapshot)
    documents = {
        "report_path": _render_html(snapshot, document),
        "resources_csv_path": _csv_document(_csv_context(snapshot, _resource_export_rows(snapshot)), CSV_CONTEXT_FIELDS + RESOURCE_CSV_FIELDS),
        "signals_csv_path": _csv_document(_csv_context(snapshot, snapshot["signals"]), CSV_CONTEXT_FIELDS + (
            "signal_id", "resource_id", "kind", "metric", "severity", "state", "time_utc",
            "end_utc", "title", "source", "series_id", "details", "evidence",
        )),
        "snapshot_path": document,
    }
    for key, text in documents.items():
        encoding = "utf-8-sig" if key.endswith("csv_path") else "utf-8"
        if len(text.encode(encoding)) > MAX_ARTIFACT_BYTES:
            raise EvidenceError("artifact_size_exceeded", "Complete evidence exceeds a 4800000-byte plain artifact sharing limit. Select a narrower scope/window or advertised coarser grain; no data was truncated or files created.", "artifact_storage")
    response = _envelope(snapshot)
    response.update({key: str(path) for key, path in paths.items()})
    response.update(_sharing_fields(root, paths))
    response["artifact_status"] = "written"
    response.update(top_review_resources=[], actions_total=len(snapshot["actions"]), actions_returned=0,
                    actions_has_more=bool(snapshot["actions"]))
    for action in snapshot["actions"][:3]:
        response["top_review_resources"].append({
            "resource_name": action["resource_name"], "severity": action["severity"], "state": action["state"],
        })
        response["actions_returned"] = len(response["top_review_resources"])
        response["actions_has_more"] = response["actions_returned"] < len(snapshot["actions"])
        if _response_bytes(response) > TRANSPORT_BUDGET_BYTES:
            response["top_review_resources"].pop()
            response["actions_returned"] = len(response["top_review_resources"])
            response["actions_has_more"] = response["actions_returned"] < len(snapshot["actions"])
            break
    _budget(response)
    written, temporary_paths = [], []
    try:
        directory.mkdir(exist_ok=True)
        if directory.resolve(strict=True) != directory or not directory.is_relative_to(root):
            raise EvidenceError("unsafe_artifact_directory", "Export directory changed scope before writing.", "artifact_storage")
        for key, path in paths.items():
            descriptor, temporary = tempfile.mkstemp(prefix=prefix + "-", suffix=".tmp", dir=directory)
            temporary_path = Path(temporary)
            temporary_paths.append(temporary_path)
            encoding = "utf-8-sig" if key.endswith("csv_path") else "utf-8"
            with os.fdopen(descriptor, "w", encoding=encoding, newline="") as stream:
                stream.write(documents[key])
            os.replace(temporary_path, path)
            temporary_paths.remove(temporary_path)
            written.append(path)
    except OSError as exc:
        failed = []
        for path in written + temporary_paths:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                failed.append(path.name)
        message = "Could not write the four runtime-owned artifacts atomically."
        if failed:
            message += " Cleanup also failed for " + ", ".join(failed) + "."
        raise EvidenceError("artifact_write_failed", message, "artifact_storage", artifacts_may_remain=bool(failed)) from exc
    return response


def main(operation: str = "report", view: str = "summary", hosting: str = "all",
         resource_group: str = "", resource_name: str = "", resource_id: str = "",
         resource_type: str = "", metric: str = "all", state: str = "all",
         severity: str = "all", period: str = "auto", start_utc: str = "",
         end_utc: str = "", grain: str = "auto", limit: int = 20, offset: int = 0) -> dict:
    """Collect read-only real infrastructure observations, export a snapshot or query evidence."""
    reference = _utc_now()
    try:
        params = _parameters(
            operation, view, hosting, resource_group, resource_name, resource_id,
            resource_type, metric, state, severity, period, start_utc, end_utc,
            grain, limit, offset, reference,
        )
        if operation == "report":
            _company_logo_markup()
        config = _config()
        if params["resource_id"]:
            _resource_id(params["resource_id"], config["subscription_id"], "parameters")
        snapshot = _collect_live(config, params, reference)
        return _write_report(snapshot) if operation == "report" else _query(snapshot, params)
    except EvidenceError as exc:
        return _failure(exc)

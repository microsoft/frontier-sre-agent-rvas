"""Read-only Azure Operations, Incidents, Anomalies, and Recommended Actions Digest engine. Build standalone tool with build_tool.py."""

import base64
import binascii
import copy
import csv
import hashlib
import io
import json
import math
import os
import re
import ssl
import statistics
import tempfile
import time
import warnings
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener
from uuid import UUID, uuid4


SUBSCRIPTION_ID = "<YOUR_SUBSCRIPTION_ID>"
MANAGED_IDENTITY_CLIENT_ID = "<YOUR_MANAGED_IDENTITY_CLIENT_ID>"
APPROVED_LOG_WORKSPACES = [
    {
        "name": "<WORKSPACE_NAME>",
        "customer_id": "<WORKSPACE_GUID>",
        "resource_group": "<RESOURCE_GROUP>",
    }
]
CLIENT_NAME = "Customer"
# Here goes the customer's logo, privately configured as a validated PNG/JPEG
# data URI. Keep generic Git source empty. Use adjacent strings <10K per line.
CLIENT_LOGO_DATA_URI = ""
CLIENT_LOGO_ALT = "Authorized customer logo"
OUTPUT_DIRECTORY = "operations-digest-reports"

ARM_ORIGIN = "https://management.azure.com"
LOGS_ORIGIN = "https://api.loganalytics.io"
ARM_TOKEN_AUDIENCES = (
    "https://management.azure.com",
    "https://management.core.windows.net",
)
LOGS_TOKEN_AUDIENCES = (
    "https://api.loganalytics.io",
    "https://api.loganalytics.azure.com",
)
ARG_API_VERSION = "2022-10-01"
RESOURCE_HEALTH_API_VERSION = "2022-10-01"
ADVISOR_API_VERSION = "2023-01-01"

TRANSPORT_BYTES = 3500
ARTIFACT_BYTES = 4_800_000
HTTP_BYTES = 12_000_000
MAX_PAGES = 25
MAX_ROWS = 10_000
MAX_WORKSPACES = 10
MAX_COLLECTION_SECONDS = 180
MAX_HTTP_ATTEMPTS = 200
MAX_LOGO_BYTES = 100_000
MAX_LOGO_DIMENSION = 2048

OPERATIONS = ("report", "query")
PERIODS = ("previous_month", "last_30d", "last_7d", "last_24h")
VIEWS = ("summary", "incidents", "anomalies", "actions", "resources", "advisor", "coverage")
CATEGORIES = (
    "all",
    "native_alert",
    "service_health",
    "extension_failure",
    "connectivity_posture",
    "telemetry_anomaly",
    "advisor_recommendation",
)
SEVERITIES = ("all", "critical", "high", "medium", "low")
HORIZONS = ("immediate_24h", "short_term_7d", "monthly_cycle")
SOURCE_STATUSES = ("complete", "partial", "denied", "error", "not_configured")

ESTATE_RESOURCE_TYPES = (
    "microsoft.compute/virtualmachines",
    "microsoft.compute/virtualmachinescalesets",
    "microsoft.hybridcompute/machines",
    "microsoft.kubernetes/connectedclusters",
    "microsoft.containerservice/managedclusters",
    "microsoft.app/containerapps",
    "microsoft.web/sites",
    "microsoft.web/serverfarms",
    "microsoft.storage/storageaccounts",
    "microsoft.keyvault/vaults",
    "microsoft.sql/servers/databases",
    "microsoft.dbforpostgresql/flexibleservers",
    "microsoft.cache/redis",
)
EXTENSION_RESOURCE_TYPES = (
    "microsoft.hybridcompute/machines/extensions",
    "microsoft.compute/virtualmachines/extensions",
)
CRITICAL_EXTENSION_TOKENS = (
    "mde",
    "defender",
    "aadlogin",
    "aadsshlogin",
    "azuremonitor",
    "ama",
    "omsagent",
    "dependencyagent",
    "keyvault",
    "policy",
)

SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}
SEVERITY_LABELS = {
    "critical": "Critical",
    "high": "High",
    "medium": "Medium",
    "low": "Low",
}
CATEGORY_LABELS = {
    "native_alert": "Azure Monitor native alert",
    "service_health": "Azure Service Health communication",
    "extension_failure": "VM / Azure Arc extension failure",
    "connectivity_posture": "Control plane / connectivity anomaly",
    "telemetry_anomaly": "Telemetry statistical / threshold anomaly",
    "advisor_recommendation": "Correlated Azure Advisor recommendation",
}
HORIZON_LABELS = {
    "immediate_24h": "Immediate <24h",
    "short_term_7d": "Short term 1-7 days",
    "monthly_cycle": "Monthly cycle",
}
EFFORT_LABELS = {
    "low": "Low",
    "medium": "Medium",
    "high": "High",
}

# BEGIN BUILD-TIME ASSETS
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
    def __init__(self, code, message, source="digest", http_status=None):
        super().__init__(message)
        self.code = code
        self.source = source
        self.http_status = http_status

    def public(self):
        result = {
            "code": self.code,
            "message": str(self),
            "source_id": self.source,
            "http_status": self.http_status,
        }
        return result


def utc_now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_utc(value, source="normalization"):
    if not isinstance(value, str) or not value or len(value) > 48:
        raise EvidenceError("invalid_timestamp", "Expected an ISO 8601 UTC timestamp.", source)
    cleaned = value.strip()
    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(cleaned)
    except ValueError as exc:
        raise EvidenceError("invalid_timestamp", "Could not parse ISO 8601 timestamp.", source) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise EvidenceError("invalid_timestamp", "Timestamp must include an explicit timezone offset.", source)
    return parsed.astimezone(timezone.utc)


def iso_utc(dt):
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def obj(value, source="normalization"):
    if not isinstance(value, dict):
        raise EvidenceError("invalid_shape", "Expected a JSON object from source.", source)
    return value


def array(value, source="normalization"):
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise EvidenceError("invalid_shape", "Expected a JSON array of objects from source.", source)
    return value


def pick(value, *keys):
    current = value
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current


def text(value, source="normalization", maximum=8192):
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > maximum or any(ord(ch) < 32 and ch not in ("\t", "\n", "\r") for ch in value):
        raise EvidenceError("invalid_field", "Source text field has an invalid type, control char, or length.", source)
    return value.strip()


def number(value, source="normalization"):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise EvidenceError("invalid_field", "Source numeric value must be a finite number.", source)
    return float(value)


def grouped(value):
    return format(value, ",") if isinstance(value, (int, float)) and not isinstance(value, bool) else str(value)


def boolean(value, source="normalization"):
    if value is not None and not isinstance(value, bool):
        raise EvidenceError("invalid_field", "Source boolean field has an invalid type.", source)
    return value


def tags_map(value, source="normalization"):
    if value is None:
        return {}
    raw_tags = obj(value, source)
    sanitized = {}
    for key, item in raw_tags.items():
        k = text(str(key), source, 256)
        if not k:
            continue
        if any(word in k.lower() for word in ("secret", "password", "token", "key", "sas", "credential", "connectionstring")):
            continue
        if isinstance(item, (str, int, float, bool)) or item is None:
            sanitized[k] = text(str(item), source, 512) if item is not None else None
    return sanitized


def validate_guid(value, field_name):
    try:
        if not isinstance(value, str) or str(UUID(value)) != value.lower() or UUID(value).int == 0:
            raise ValueError
    except (ValueError, AttributeError) as exc:
        raise EvidenceError(
            "configuration_required",
            "Configure the explicit GUID constant " + field_name + " before running live collection.",
            "configuration",
        ) from exc
    return value.lower()


def validate_logo(uri, alt=CLIENT_LOGO_ALT):
    if uri == "":
        return
    if not isinstance(uri, str) or len(uri) > 140_000:
        raise EvidenceError("invalid_logo", "Optional logo must be a bounded inline PNG/JPEG data URI.", "branding")
    match = re.fullmatch(r"data:image/(png|jpeg);base64,([A-Za-z0-9+/=]+)", uri)
    if not match:
        raise EvidenceError("invalid_logo", "Only inline PNG/JPEG MIME with canonical base64 is allowed.", "branding")
    try:
        data = base64.b64decode(match[2], validate=True)
    except (ValueError, binascii.Error) as exc:
        raise EvidenceError("invalid_logo", "Invalid logo base64 payload.", "branding") from exc
    if not 1 <= len(data) <= MAX_LOGO_BYTES:
        raise EvidenceError("invalid_logo", "Optional raster logo must contain 1..100000 bytes.", "branding")
    if not isinstance(alt, str) or not alt.strip() or len(alt) > 120 or re.search(r"[\x00-\x1f\x7f]", alt):
        raise EvidenceError("invalid_logo", "Provide 1..120 plain characters of descriptive logo alt text.", "branding")
    try:
        from PIL import Image, ImageFile, UnidentifiedImageError
    except ImportError as exc:
        raise EvidenceError("dependency_missing", "A configured logo requires Pillow for raster validation.", "branding") from exc
    if ImageFile.LOAD_TRUNCATED_IMAGES:
        raise EvidenceError("unsafe_decoder_settings", "Truncated-image decoding must not be enabled.", "branding")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data), formats=["PNG", "JPEG"]) as image:
                width, height = image.size
                if (
                    image.format != ("PNG" if match[1] == "png" else "JPEG")
                    or not 1 <= width <= MAX_LOGO_DIMENSION
                    or not 1 <= height <= MAX_LOGO_DIMENSION
                    or getattr(image, "n_frames", 1) != 1
                ):
                    raise EvidenceError("invalid_logo", "Use one PNG/JPEG frame, matching MIME, at most 2048x2048 pixels.", "branding")
                image.verify()
            with Image.open(io.BytesIO(data), formats=["PNG", "JPEG"]) as image:
                image.load()
    except (OSError, ValueError, SyntaxError, UnidentifiedImageError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise EvidenceError("invalid_logo", "The optional logo is not a complete, valid single-frame PNG/JPEG raster.", "branding") from exc


def validate_config():
    validate_logo(CLIENT_LOGO_DATA_URI, CLIENT_LOGO_ALT)
    if not isinstance(CLIENT_NAME, str) or not 1 <= len(CLIENT_NAME.strip()) <= 120 or re.search(r"[\x00-\x1f\x7f]", CLIENT_NAME):
        raise EvidenceError("configuration_required", "CLIENT_NAME must be 1..120 plain characters.", "configuration")
    if not isinstance(CLIENT_LOGO_ALT, str) or not 1 <= len(CLIENT_LOGO_ALT.strip()) <= 120 or re.search(r"[\x00-\x1f\x7f]", CLIENT_LOGO_ALT):
        raise EvidenceError("configuration_required", "CLIENT_LOGO_ALT must be 1..120 plain characters.", "configuration")
    sub_id = validate_guid(SUBSCRIPTION_ID, "SUBSCRIPTION_ID")
    client_id = validate_guid(MANAGED_IDENTITY_CLIENT_ID, "MANAGED_IDENTITY_CLIENT_ID")
    if not isinstance(APPROVED_LOG_WORKSPACES, list) or len(APPROVED_LOG_WORKSPACES) > MAX_WORKSPACES:
        raise EvidenceError("configuration_required", "Configure 0..10 entries in APPROVED_LOG_WORKSPACES.", "configuration")
    workspaces = []
    seen_names = set()
    seen_ids = set()
    for item in APPROVED_LOG_WORKSPACES:
        if not isinstance(item, dict):
            raise EvidenceError("configuration_required", "Each APPROVED_LOG_WORKSPACES entry must be a dict.", "configuration")
        w_name = item.get("name")
        w_rg = item.get("resource_group")
        if not isinstance(w_name, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", w_name):
            raise EvidenceError("configuration_required", "Configure a valid workspace name in APPROVED_LOG_WORKSPACES.", "configuration")
        if not isinstance(w_rg, str) or not re.fullmatch(r"[A-Za-z0-9_.()-]{1,90}", w_rg):
            raise EvidenceError("configuration_required", "Configure a valid resource_group in APPROVED_LOG_WORKSPACES.", "configuration")
        w_guid = validate_guid(item.get("customer_id"), "APPROVED_LOG_WORKSPACES.customer_id")
        if w_name.lower() in seen_names or w_guid in seen_ids:
            raise EvidenceError("configuration_required", "Duplicate workspace name or customer_id in APPROVED_LOG_WORKSPACES.", "configuration")
        seen_names.add(w_name.lower())
        seen_ids.add(w_guid)
        workspaces.append({
            "name": w_name,
            "customer_id": w_guid,
            "resource_group": w_rg,
        })
    return {
        "subscription_id": sub_id,
        "client_id": client_id,
        "workspaces": workspaces,
        "client_name": CLIENT_NAME.strip(),
    }


def compute_window(period, reference_str):
    ref_dt = parse_utc(reference_str, "parameters")
    if period == "previous_month":
        end_dt = ref_dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        start_dt = (end_dt - timedelta(days=1)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        label = "Previous calendar month (" + start_dt.strftime("%Y-%m") + ")"
        cadence = "Scheduled monthly run (30 8 1 * * UTC) / closed month"
        grain = "PT1H"
    elif period == "last_30d":
        end_dt = ref_dt.replace(microsecond=0)
        start_dt = end_dt - timedelta(days=30)
        label = "Last 30 days (rolling)"
        cadence = "On demand (rolling 30-day window)"
        grain = "PT1H"
    elif period == "last_7d":
        end_dt = ref_dt.replace(microsecond=0)
        start_dt = end_dt - timedelta(days=7)
        label = "Last 7 days (rolling)"
        cadence = "On demand (rolling 7-day weekly window)"
        grain = "PT1H"
    elif period == "last_24h":
        end_dt = ref_dt.replace(microsecond=0)
        start_dt = end_dt - timedelta(hours=24)
        label = "Last 24 hours"
        cadence = "On demand (24-hour on-call shift)"
        grain = "PT5M"
    else:
        raise EvidenceError("invalid_parameter", "period must use its declared enum.", "parameters")
    start_iso = iso_utc(start_dt)
    end_iso = iso_utc(end_dt)
    duration_hours = max(1, int(round((end_dt - start_dt).total_seconds() / 3600.0)))
    return {
        "period": period,
        "label": label,
        "cadence": cadence,
        "start_utc": start_iso,
        "end_utc": end_iso,
        "timespan_iso": start_iso + "/" + end_iso,
        "grain": grain,
        "duration_hours": duration_hours,
    }


def validate_parameters(
    operation="report",
    period="previous_month",
    view="summary",
    category="all",
    severity="all",
    resource_name="",
    limit=25,
    offset=0,
    reference_utc=None,
):
    for key, value, choices in (
        ("operation", operation, OPERATIONS),
        ("period", period, PERIODS),
        ("view", view, VIEWS),
        ("category", category, CATEGORIES),
        ("severity", severity, SEVERITIES),
    ):
        if not isinstance(value, str) or value not in choices:
            raise EvidenceError("invalid_parameter", key + " must use its declared enum.", "parameters")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise EvidenceError("invalid_parameter", "limit must be an integer from 1 to 100.", "parameters")
    if isinstance(offset, bool) or not isinstance(offset, int) or not 0 <= offset <= 500_000:
        raise EvidenceError("invalid_parameter", "offset must be an integer from 0 to 500000.", "parameters")
    if not isinstance(resource_name, str) or len(resource_name) > 128 or (
        resource_name and not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", resource_name)
    ):
        raise EvidenceError(
            "invalid_parameter",
            "resource_name must be a bounded resource name (^[A-Za-z0-9_.-]{0,128}$), never a path, URL, or query.",
            "parameters",
        )
    has_filters = any((view != "summary", category != "all", severity != "all", bool(resource_name), limit != 25, offset != 0))
    if operation == "report" and has_filters:
        raise EvidenceError(
            "invalid_combination",
            "operation=report writes complete unfiltered evidence for the requested period; use defaults for view/category/severity/resource_name/limit/offset.",
            "parameters",
        )
    if operation == "query":
        if view in ("summary", "coverage") and any((category != "all", severity != "all", bool(resource_name))):
            raise EvidenceError(
                "invalid_combination",
                "summary and coverage views do not accept category, severity, or resource_name filters.",
                "parameters",
            )
        if view == "resources" and category != "all":
            raise EvidenceError(
                "invalid_combination",
                "view=resources aggregates across categories; use category=all.",
                "parameters",
            )
        if view == "incidents" and category not in ("all", "native_alert", "service_health"):
            raise EvidenceError(
                "invalid_combination",
                "view=incidents supports category in ('all', 'native_alert', 'service_health').",
                "parameters",
            )
        if view == "anomalies" and category not in ("all", "extension_failure", "connectivity_posture", "telemetry_anomaly"):
            raise EvidenceError(
                "invalid_combination",
                "view=anomalies supports category in ('all', 'extension_failure', 'connectivity_posture', 'telemetry_anomaly').",
                "parameters",
            )
        if view == "advisor" and category not in ("all", "advisor_recommendation"):
            raise EvidenceError(
                "invalid_combination",
                "view=advisor supports category in ('all', 'advisor_recommendation').",
                "parameters",
            )
    ref = reference_utc or utc_now()
    window = compute_window(period, ref)
    return {
        "operation": operation,
        "period": period,
        "view": view,
        "category": category,
        "severity": severity,
        "resource_name": resource_name,
        "limit": limit,
        "offset": offset,
        "window": window,
    }


def response_bytes(value):
    return len(json.dumps(value, allow_nan=False).encode("utf-8"))


def ensure_response(value):
    if response_bytes(value) > TRANSPORT_BYTES:
        raise EvidenceError(
            "transport_size_exceeded",
            "Default-serialized response exceeds 3500 bytes; no malformed or truncated JSON is returned.",
            "transport",
        )
    return value


def arm_resource_id(value, subscription_id=None, source="scope"):
    raw = text(value, source, 2048)
    if not raw:
        raise EvidenceError("invalid_resource_id", "A scoped ARM resource ID is required.", source)
    if re.search(r"[\x00-\x1f\x7f?#\\%]", raw):
        raise EvidenceError("invalid_resource_id", "Resource ID contains unsafe characters.", source)
    cleaned = raw.rstrip("/")
    parts = cleaned.split("/")
    if (
        len(parts) < 5
        or parts[0] != ""
        or parts[1].lower() != "subscriptions"
        or any(part in ("", ".", "..") for part in parts[1:])
    ):
        raise EvidenceError("invalid_resource_id", "Resource ID has invalid ARM path structure.", source)
    try:
        sub_guid = str(UUID(parts[2])).lower()
    except ValueError as exc:
        raise EvidenceError("invalid_resource_id", "Resource ID subscription is not a valid GUID.", source) from exc
    if subscription_id and sub_guid != subscription_id.lower():
        raise EvidenceError("invalid_resource_id", "Resource ID belongs to a different subscription.", source)
    return cleaned


def extract_rg_and_type(resource_id):
    if not isinstance(resource_id, str) or not resource_id.startswith("/"):
        return "subscription-scope", "microsoft.resources/subscriptions", resource_id or "subscription"
    parts = resource_id.rstrip("/").split("/")
    rg = "subscription-scope"
    if len(parts) >= 5 and parts[3].lower() == "resourcegroups":
        rg = parts[4]
    if "providers" in [p.lower() for p in parts]:
        idx = [p.lower() for p in parts].index("providers")
        if idx + 2 < len(parts):
            provider = parts[idx + 1]
            type_segments = parts[idx + 2::2]
            rtype = (provider + "/" + "/".join(type_segments)).lower()
            rname = parts[-1]
            return rg, rtype, rname
    return rg, "microsoft.resources/resource", parts[-1]


def source_receipt(source_id, reference, status="complete", note="", window=None, **extra):
    return {
        "id": source_id,
        "status": status,
        "time": reference,
        "records": 0,
        "pages": 0,
        "pagination_complete": status == "complete",
        "errors": [],
        "note": note,
        "window": window,
        **extra,
    }


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def verify_jwt_claims(token_str, expected_client, expected_aud):
    try:
        encoded = token_str.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
        claims = normalize_sidecar_claims(claims)
    except (AttributeError, IndexError, ValueError, binascii.Error) as exc:
        raise EvidenceError("authentication_failed", "Identity provider returned an unreadable JWT.", "identity") from exc
    tenant = pick(claims, "tid")
    client = pick(claims, "appid") or pick(claims, "azp")
    aud = pick(claims, "aud")
    try:
        valid_tid = isinstance(tenant, str) and str(UUID(tenant)) == tenant.lower() and UUID(tenant).int != 0
    except ValueError:
        valid_tid = False
    expected_norm = expected_aud.rstrip("/").lower()
    aud_norm = aud.rstrip("/").lower() if isinstance(aud, str) else ""
    if expected_norm == ARM_ORIGIN.lower():
        aud_valid = aud_norm in ARM_TOKEN_AUDIENCES
    elif expected_norm == LOGS_ORIGIN.lower():
        aud_valid = aud_norm in LOGS_TOKEN_AUDIENCES
    else:
        aud_valid = aud_norm == expected_norm
    if not (valid_tid and isinstance(client, str) and client.lower() == expected_client.lower() and aud_valid):
        raise EvidenceError("identity_mismatch", "Token client identity or audience differs from the fixed configuration.", "identity")
    return claims


class Identity:
    def __init__(self, config):
        try:
            from azure.identity import ManagedIdentityCredential
        except ImportError as exc:
            raise EvidenceError("dependency_missing", "Live reads require azure-identity; no fallback credential is permitted.", "identity") from exc
        self.config = config
        self.credential = ManagedIdentityCredential(client_id=config["client_id"])
        self.deadline = time.monotonic() + MAX_COLLECTION_SECONDS
        self.request_count = 0
        self.cached_tokens = {}

    def guard_budget(self):
        if time.monotonic() >= self.deadline:
            raise EvidenceError("collection_deadline", "Collection time bound reached; remaining reads are marked incomplete.", "collection")
        if self.request_count >= MAX_HTTP_ATTEMPTS:
            raise EvidenceError("request_cap", "Collection HTTP request bound reached.", "collection")
        self.request_count += 1

    def token(self, origin):
        from azure.core.exceptions import ClientAuthenticationError, ServiceRequestError
        from azure.identity import CredentialUnavailableError

        cached = self.cached_tokens.get(origin)
        if cached is not None and cached[1] > time.time() + 60:
            return cached[0]
        self.guard_budget()
        scope = origin.rstrip("/") + "/.default"
        try:
            tok = self.credential.get_token(scope)
        except (ClientAuthenticationError, CredentialUnavailableError, ServiceRequestError) as exc:
            raise EvidenceError("authentication_failed", "The configured managed identity could not acquire a token.", "identity") from exc
        verify_jwt_claims(tok.token, self.config["client_id"], origin)
        self.cached_tokens[origin] = (tok.token, getattr(tok, "expires_on", time.time() + 300))
        return tok.token

    def arm_token(self):
        return self.token(ARM_ORIGIN)

    def logs_token(self):
        return self.token(LOGS_ORIGIN)

    def close(self):
        self.credential.close()


class HttpReader:
    def __init__(self, identity, origin=ARM_ORIGIN, token_kind="arm"):
        self.identity = identity
        self.origin = origin
        self.token_kind = token_kind
        self.context = ssl.create_default_context()
        if self.context.verify_mode != ssl.CERT_REQUIRED or not self.context.check_hostname:
            raise EvidenceError("unsafe_tls", "TLS certificate and hostname verification are mandatory.", "tls")
        self.opener = build_opener(NoRedirect(), HTTPSHandler(context=self.context))
        self.allowed = set()

    def allow(self, url, method="GET"):
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or (parsed.scheme + "://" + parsed.netloc.lower()) != self.origin.lower()
            or parsed.fragment
            or parsed.username
            or parsed.password
            or "\\" in parsed.path
            or any(part in (".", "..") for part in unquote(parsed.path).split("/"))
        ):
            raise EvidenceError("unsafe_endpoint", "Read URL changed the fixed HTTPS origin or path safety rules.", "scope")
        if method not in ("GET", "POST"):
            raise EvidenceError("unsafe_method", "Only read-only GET and POST queries (ARG / Log Analytics) are permitted.", "scope")
        lowered = parsed.path.lower()
        if any(forbidden in lowered for forbidden in ("/write", "/delete", "/action", "/runcommand", "/listkeys", "/secrets")):
            raise EvidenceError("unsafe_endpoint", "Write actions, command execution, and secret reads are forbidden.", "scope")
        if method == "POST" and not (
            lowered == "/providers/microsoft.resourcegraph/resources"
            or re.fullmatch(r"/v1/workspaces/[0-9a-f-]{36}/query", lowered)
        ):
            raise EvidenceError("unsafe_method", "POST is restricted to Azure Resource Graph and Log Analytics query endpoints.", "scope")
        self.allowed.add((method, parsed.path))
        return url

    def _bearer(self):
        return self.identity.arm_token() if self.token_kind == "arm" else self.identity.logs_token()

    def request(self, method, url, source, body=None):
        parsed = urlsplit(url)
        if (
            (parsed.scheme + "://" + parsed.netloc.lower()) != self.origin.lower()
            or parsed.fragment
            or parsed.username
            or parsed.password
            or len(url) > 16384
            or (method, parsed.path) not in self.allowed
        ):
            raise EvidenceError("unsafe_endpoint", "Request was not registered in the scoped read allowlist.", source)
        payload = None if body is None else json.dumps(body, allow_nan=False).encode("utf-8")
        for attempt in range(3):
            bearer = self._bearer()
            self.identity.guard_budget()
            headers = {
                "Authorization": "Bearer " + bearer,
                "Accept": "application/json",
                "Content-Type": "application/json",
            }
            if self.token_kind == "logs":
                headers["Prefer"] = "wait=90"
            req = Request(url, data=payload, method=method, headers=headers)
            try:
                with self.opener.open(req, timeout=30) as response:
                    if response.status != 200:
                        raise EvidenceError("http_error", "Read returned HTTP " + str(response.status) + ".", source, response.status)
                    raw = response.read(HTTP_BYTES + 1)
                    if len(raw) > HTTP_BYTES:
                        raise EvidenceError("response_cap", "Response exceeded the byte safety cap.", source)
            except HTTPError as exc:
                if exc.code in (429, 500, 502, 503, 504) and attempt < 2:
                    retry = exc.headers.get("Retry-After", "") if exc.headers else ""
                    time.sleep(min(int(retry), 4) if re.fullmatch(r"[0-9]{1,4}", retry) else attempt + 1)
                    continue
                raise EvidenceError(
                    "access_denied" if exc.code in (401, 403) else "http_error",
                    "Read returned HTTP " + str(exc.code) + "; raw error bodies are excluded.",
                    source,
                    exc.code,
                ) from exc
            except (URLError, TimeoutError, ssl.SSLError, OSError) as exc:
                reason = getattr(exc, "reason", exc)
                code = "tls_failed" if isinstance(reason, ssl.SSLError) else "transport_failed"
                raise EvidenceError(code, "Transport or TLS error during read-only request.", source) from exc
            try:
                decoded = json.loads(raw)
                return obj(decoded, source)
            except (ValueError, UnicodeDecodeError) as exc:
                raise EvidenceError("invalid_json", "Source returned malformed JSON.", source) from exc
        raise EvidenceError("http_error", "Bounded HTTP retries exhausted.", source)


def next_arm_link(link, initial):
    if not isinstance(link, str) or not link or len(link) > 16384:
        raise EvidenceError("invalid_pagination", "Invalid ARM continuation link.", "pagination")
    current, first = urlsplit(link), urlsplit(initial)
    if (
        current.scheme != "https"
        or current.netloc.lower() != first.netloc.lower()
        or unquote(current.path) != unquote(first.path)
        or current.fragment
        or current.username
        or current.password
        or "\\" in current.path
    ):
        raise EvidenceError("invalid_pagination", "ARM continuation changed origin or path.", "pagination")
    try:
        pairs = parse_qsl(current.query, keep_blank_values=True, strict_parsing=True)
        original = dict(parse_qsl(first.query, keep_blank_values=True, strict_parsing=True))
    except ValueError as exc:
        raise EvidenceError("invalid_pagination", "Malformed continuation query parameters.", "pagination") from exc
    values = dict(pairs)
    paging = {"$skiptoken", "skiptoken", "$skipToken", "skipToken", "$skip", "$top"}
    if len(values) != len(pairs) or any(key not in original and key not in paging for key in values):
        raise EvidenceError("invalid_pagination", "ARM continuation added an unapproved query parameter.", "pagination")
    if any(values.get(key) != value for key, value in original.items() if key not in paging):
        raise EvidenceError("invalid_pagination", "ARM continuation modified api-version or scope filter.", "pagination")
    return link


def arg_alerts_query():
    return (
        "alertsmanagementresources "
        "| where type =~ 'microsoft.alertsmanagement/alerts' "
        "| extend ess = properties.essentials "
        "| project id, name, "
        "severity=tostring(ess.severity), "
        "alertState=tostring(ess.alertState), "
        "monitorCondition=tostring(ess.monitorCondition), "
        "signalType=tostring(ess.signalType), "
        "monitorService=tostring(ess.monitorService), "
        "targetResource=tostring(ess.targetResource), "
        "targetResourceName=tostring(ess.targetResourceName), "
        "targetResourceGroup=tostring(ess.targetResourceGroup), "
        "targetResourceType=tostring(ess.targetResourceType), "
        "startDateTime=tostring(ess.startDateTime), "
        "lastModifiedDateTime=tostring(ess.lastModifiedDateTime), "
        "resolvedDateTime=tostring(ess.monitorConditionResolvedDateTime), "
        "description=tostring(ess.description) "
        "| order by startDateTime desc, id asc"
    )


def arg_inventory_query():
    types_literal = ", ".join("'" + t + "'" for t in ESTATE_RESOURCE_TYPES)
    return (
        "resources "
        "| where type in~ (" + types_literal + ") "
        "| project id, name, type, resourceGroup, location, skuName=tostring(sku.name), tags, "
        "provisioningState=tostring(properties.provisioningState), "
        "arcStatus=tostring(properties.status), "
        "arcAgentVersion=tostring(properties.agentVersion), "
        "arcLastStatusChange=tostring(properties.lastStatusChange), "
        "osName=tostring(coalesce(properties.osName, properties.storageProfile.osDisk.osType)), "
        "osSku=tostring(properties.osSku), "
        "osVersion=tostring(properties.osVersion), "
        "vmSize=tostring(properties.hardwareProfile.vmSize), "
        "powerState=tostring(coalesce(properties.extended.instanceView.powerState.code, properties.powerState.code)), "
        "kubernetesVersion=tostring(properties.kubernetesVersion), "
        "runningState=tostring(coalesce(properties.runningStatus, properties.state)) "
        "| order by id asc"
    )


def arg_extensions_query():
    types_literal = ", ".join("'" + t + "'" for t in EXTENSION_RESOURCE_TYPES)
    return (
        "resources "
        "| where type in~ (" + types_literal + ") "
        "| project id, name, type, resourceGroup, location, "
        "publisher=tostring(properties.publisher), "
        "extType=tostring(properties.type), "
        "version=tostring(coalesce(properties.typeHandlerVersion, properties.instanceView.typeHandlerVersion)), "
        "provisioningState=tostring(properties.provisioningState), "
        "enableAutomaticUpgrade=properties.enableAutomaticUpgrade, "
        "autoUpgradeMinorVersion=properties.autoUpgradeMinorVersion "
        "| order by id asc"
    )


def read_arg_query(reader, subscription_id, query, source_id, reference, window, normalize_fn):
    url = ARM_ORIGIN + "/providers/Microsoft.ResourceGraph/resources?api-version=" + ARG_API_VERSION
    reader.allow(url, "POST")
    receipt = source_receipt(
        source_id,
        reference,
        window=window,
        page_cap=MAX_PAGES,
        row_cap=MAX_ROWS,
        pagination_complete=False,
        read_signature="POST " + url,
    )
    rows = []
    seen_ids = set()
    seen_tokens = set()
    skip_token = None
    try:
        for page_num in range(1, MAX_PAGES + 1):
            options = {"$top": 1000, "resultFormat": "objectArray"}
            if skip_token is not None:
                options["$skipToken"] = skip_token
            body = {
                "subscriptions": [subscription_id],
                "query": query,
                "options": options,
            }
            payload = reader.request("POST", url, source_id, body=body)
            receipt["pages"] = page_num
            data = array(payload.get("data", []), source_id)
            if len(rows) + len(data) > MAX_ROWS:
                raise EvidenceError("row_cap", "Resource Graph row safety cap reached.", source_id)
            for raw in data:
                normalized = normalize_fn(raw)
                if normalized is None:
                    continue
                row_id = str(normalized.get("id") or normalized.get("resource_id") or "").lower()
                if not row_id or row_id in seen_ids:
                    raise EvidenceError("invalid_pagination", "Resource Graph row ID is missing or duplicated.", source_id)
                seen_ids.add(row_id)
                rows.append(normalized)
            receipt["records"] = len(rows)
            next_token = payload.get("$skipToken")
            if not next_token:
                receipt["pagination_complete"] = True
                return rows, receipt
            next_token = text(next_token, source_id, 8192)
            if not next_token or next_token in seen_tokens:
                raise EvidenceError("pagination_loop", "Resource Graph repeated or emptied $skipToken.", source_id)
            seen_tokens.add(next_token)
            skip_token = next_token
        raise EvidenceError("page_cap", "Resource Graph page cap reached.", source_id)
    except EvidenceError as exc:
        receipt["status"] = "partial" if rows else "denied" if exc.http_status in (401, 403) else "error"
        receipt["records"] = len(rows)
        receipt["errors"].append(exc.public())
        return rows, receipt


def read_arm_pages(reader, url, source_id, reference, window, normalize_fn):
    reader.allow(url, "GET")
    receipt = source_receipt(
        source_id,
        reference,
        window=window,
        page_cap=MAX_PAGES,
        row_cap=MAX_ROWS,
        pagination_complete=False,
        read_signature="GET " + url,
    )
    rows = []
    seen_ids = set()
    seen_pages = set()
    current = url
    try:
        for page_num in range(1, MAX_PAGES + 1):
            if current in seen_pages:
                raise EvidenceError("pagination_loop", "ARM pagination repeated a page URL.", source_id)
            seen_pages.add(current)
            payload = reader.request("GET", current, source_id)
            receipt["pages"] = page_num
            page = array(payload.get("value", []), source_id)
            if len(rows) + len(page) > MAX_ROWS:
                raise EvidenceError("row_cap", "ARM list row safety cap reached.", source_id)
            for raw in page:
                normalized = normalize_fn(raw)
                if normalized is None:
                    continue
                row_id = str(normalized.get("id") or "").lower()
                if not row_id or row_id in seen_ids:
                    raise EvidenceError("invalid_pagination", "ARM row identity is missing or repeated.", source_id)
                seen_ids.add(row_id)
                rows.append(normalized)
            receipt["records"] = len(rows)
            continuation = payload.get("nextLink")
            if not continuation:
                receipt["pagination_complete"] = True
                return rows, receipt
            current = next_arm_link(continuation, url)
        raise EvidenceError("page_cap", "ARM list page cap reached.", source_id)
    except EvidenceError as exc:
        receipt["status"] = "partial" if rows else "denied" if exc.http_status in (401, 403) else "error"
        receipt["records"] = len(rows)
        receipt["errors"].append(exc.public())
        return rows, receipt


def map_alert_severity(sev_str):
    mapping = {
        "sev0": "critical",
        "sev1": "high",
        "sev2": "medium",
        "sev3": "low",
        "sev4": "low",
    }
    return mapping.get((sev_str or "").strip().lower(), "medium")


def normalize_alert_row(raw, subscription_id, window, reference):
    source_id = "arg_alerts_incidents"
    alert_id = text(raw.get("id"), source_id, 2048)
    name = text(raw.get("name"), source_id, 256) or (alert_id.split("/")[-1] if alert_id else None)
    if not alert_id or not name:
        raise EvidenceError("invalid_alert", "Alert row is missing id or name.", source_id)
    native_sev = text(raw.get("severity"), source_id, 32) or "Sev2"
    sev = map_alert_severity(native_sev)
    alert_state = text(raw.get("alertState"), source_id, 64) or "New"
    monitor_cond = text(raw.get("monitorCondition"), source_id, 64) or "Fired"
    signal_type = text(raw.get("signalType"), source_id, 64) or "Metric"
    monitor_service = text(raw.get("monitorService"), source_id, 128) or "Platform"
    target_res = text(raw.get("targetResource"), source_id, 2048)
    if target_res and target_res.lower().startswith("/subscriptions/"):
        target_res = arm_resource_id(target_res, subscription_id, source_id)
    rg, rtype, inferred_name = extract_rg_and_type(target_res or "")
    target_name = text(raw.get("targetResourceName"), source_id, 256) or inferred_name
    target_rg = text(raw.get("targetResourceGroup"), source_id, 128) or rg
    target_type = (text(raw.get("targetResourceType"), source_id, 180) or rtype).lower()
    start_str = text(raw.get("startDateTime"), source_id, 64)
    mod_str = text(raw.get("lastModifiedDateTime"), source_id, 64) or start_str or reference
    res_str = text(raw.get("resolvedDateTime"), source_id, 64)
    start_dt = parse_utc(start_str, source_id) if start_str else parse_utc(mod_str, source_id)
    mod_dt = parse_utc(mod_str, source_id)
    w_start = parse_utc(window["start_utc"], source_id)
    w_end = parse_utc(window["end_utc"], source_id)
    is_active = monitor_cond.lower() == "fired" or alert_state.lower() in ("new", "acknowledged")
    in_window = (w_start <= start_dt <= w_end) or (w_start <= mod_dt <= w_end) or is_active
    if not in_window:
        return None
    desc = text(raw.get("description"), source_id, 2048) or (
        "Native alert " + native_sev + " (" + monitor_cond + " / " + alert_state + ") on " + target_name + "."
    )
    short_hash = hashlib.sha256(alert_id.lower().encode("utf-8")).hexdigest()[:10]
    return {
        "id": "INC-ALR-" + short_hash,
        "native_id": alert_id,
        "record_kind": "incident",
        "category": "native_alert",
        "category_label": CATEGORY_LABELS["native_alert"],
        "severity": sev,
        "severity_label": SEVERITY_LABELS[sev],
        "native_severity": native_sev,
        "state": alert_state,
        "monitor_condition": monitor_cond,
        "title": "Alert " + native_sev + " (" + monitor_service + "): " + target_name,
        "signal_type": signal_type,
        "monitor_service": monitor_service,
        "resource_id": target_res or ("/subscriptions/" + subscription_id),
        "resource_name": target_name,
        "resource_group": target_rg,
        "resource_type": target_type,
        "start_time_utc": iso_utc(start_dt),
        "last_updated_utc": iso_utc(mod_dt),
        "resolved_time_utc": iso_utc(parse_utc(res_str, source_id)) if res_str else None,
        "observed_at_utc": reference,
        "source_id": source_id,
        "summary": desc,
        "learn_url": "https://learn.microsoft.com/azure/azure-monitor/alerts/alerts-overview",
    }


def normalize_service_health_row(raw, subscription_id, window, reference):
    source_id = "arm_service_health"
    event_id = text(raw.get("id"), source_id, 2048)
    tracking_id = text(raw.get("name"), source_id, 128)
    if not event_id or not tracking_id or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", tracking_id):
        raise EvidenceError("invalid_service_health", "Service Health event is missing a valid tracking ID.", source_id)
    props = obj(raw.get("properties", {}), source_id)
    event_type = text(props.get("eventType"), source_id, 64)
    if event_type not in ("ServiceIssue", "PlannedMaintenance"):
        return None
    status = text(props.get("status"), source_id, 64) or "Active"
    title = text(props.get("title"), source_id, 512) or ("Event " + event_type + " (" + tracking_id + ")")
    level = (text(props.get("level"), source_id, 64) or "").lower()
    if event_type == "ServiceIssue":
        sev = "critical" if level == "critical" else "high"
    else:
        sev = "medium"
    start_str = text(props.get("impactStartTime"), source_id, 64) or text(props.get("lastUpdateTime"), source_id, 64) or reference
    update_str = text(props.get("lastUpdateTime"), source_id, 64) or start_str
    mitigation_str = text(props.get("impactMitigationTime"), source_id, 64)
    start_dt = parse_utc(start_str, source_id)
    update_dt = parse_utc(update_str, source_id)
    w_start = parse_utc(window["start_utc"], source_id)
    w_end = parse_utc(window["end_utc"], source_id)
    in_window = (w_start <= start_dt <= w_end) or (w_start <= update_dt <= w_end) or status.lower() == "active"
    if not in_window:
        return None
    impacts = props.get("impact") if isinstance(props.get("impact"), list) else []
    services = []
    regions = []
    for imp in impacts:
        if isinstance(imp, dict):
            svc = text(imp.get("impactedService"), source_id, 128)
            if svc and svc not in services:
                services.append(svc)
            reg_list = imp.get("impactedRegions") if isinstance(imp.get("impactedRegions"), list) else []
            for reg in reg_list:
                if isinstance(reg, dict):
                    rname = text(reg.get("impactedRegion"), source_id, 64)
                    if rname and rname not in regions:
                        regions.append(rname)
    service_label = ", ".join(services) if services else "Azure Platform"
    region_label = ", ".join(regions) if regions else "Global"
    summary_text = text(props.get("summary"), source_id, 2048) or (
        event_type + " " + tracking_id + " (" + status + ") affecting " + service_label + " [" + region_label + "]."
    )
    return {
        "id": "INC-SH-" + tracking_id,
        "native_id": event_id,
        "tracking_id": tracking_id,
        "record_kind": "incident",
        "category": "service_health",
        "category_label": CATEGORY_LABELS["service_health"],
        "severity": sev,
        "severity_label": SEVERITY_LABELS[sev],
        "native_severity": event_type,
        "state": status,
        "monitor_condition": status,
        "title": title,
        "signal_type": event_type,
        "monitor_service": service_label,
        "regions": regions,
        "resource_id": "/subscriptions/" + subscription_id,
        "resource_name": service_label,
        "resource_group": "subscription-scope",
        "resource_type": "microsoft.resourcehealth/events",
        "start_time_utc": iso_utc(start_dt),
        "last_updated_utc": iso_utc(update_dt),
        "resolved_time_utc": iso_utc(parse_utc(mitigation_str, source_id)) if mitigation_str else None,
        "observed_at_utc": reference,
        "source_id": source_id,
        "summary": summary_text,
        "learn_url": "https://learn.microsoft.com/azure/service-health/service-health-overview",
    }


def normalize_estate_resource(raw, subscription_id, reference):
    source_id = "arg_posture_anomalies"
    res_id = arm_resource_id(raw.get("id"), subscription_id, source_id)
    name = text(raw.get("name"), source_id, 256)
    rtype = (text(raw.get("type"), source_id, 180) or "").lower()
    rg = text(raw.get("resourceGroup"), source_id, 128)
    location = text(raw.get("location"), source_id, 64)
    if not name or not rtype or not rg or not location or rtype not in ESTATE_RESOURCE_TYPES:
        raise EvidenceError("invalid_inventory", "Inventory row is missing required identity fields.", source_id)
    hosting = "arc" if rtype in ("microsoft.hybridcompute/machines", "microsoft.kubernetes/connectedclusters") else "azure"
    prov_state = text(raw.get("provisioningState"), source_id, 64) or "Succeeded"
    arc_status = text(raw.get("arcStatus"), source_id, 64)
    arc_version = text(raw.get("arcAgentVersion"), source_id, 64)
    arc_last_change = text(raw.get("arcLastStatusChange"), source_id, 64)
    if arc_last_change:
        arc_last_change = iso_utc(parse_utc(arc_last_change, source_id))
    power_state = text(raw.get("powerState"), source_id, 64)
    running_state = text(raw.get("runningState"), source_id, 64)
    op_state = arc_status or power_state or running_state or prov_state
    return {
        "id": res_id,
        "resource_id": res_id,
        "name": name,
        "resource_name": name,
        "resource_group": rg,
        "resource_type": rtype,
        "location": location,
        "hosting": hosting,
        "sku": text(raw.get("skuName"), source_id, 64),
        "provisioning_state": prov_state,
        "operational_state": op_state,
        "arc_status": arc_status,
        "arc_agent_version": arc_version,
        "arc_last_status_change_utc": arc_last_change,
        "os_name": text(raw.get("osName"), source_id, 128),
        "os_sku": text(raw.get("osSku"), source_id, 128),
        "os_version": text(raw.get("osVersion"), source_id, 64),
        "vm_size": text(raw.get("vmSize"), source_id, 64),
        "power_state": power_state,
        "kubernetes_version": text(raw.get("kubernetesVersion"), source_id, 64),
        "tags": tags_map(raw.get("tags"), source_id),
        "observed_at_utc": reference,
        "source_id": source_id,
    }


def normalize_extension_row(raw, subscription_id, reference):
    source_id = "arg_guest_extensions"
    ext_id = arm_resource_id(raw.get("id"), subscription_id, source_id)
    parts = ext_id.split("/")
    if len(parts) < 11 or parts[9].lower() != "extensions":
        raise EvidenceError("invalid_extension", "Extension ID is not a valid child resource ID.", source_id)
    parent_id = "/".join(parts[:9])
    parent_name = parts[8]
    parent_type = (parts[6] + "/" + parts[7]).lower()
    ext_name = text(raw.get("name"), source_id, 256) or parts[-1]
    rg = text(raw.get("resourceGroup"), source_id, 128) or parts[4]
    location = text(raw.get("location"), source_id, 64) or ""
    publisher = text(raw.get("publisher"), source_id, 256) or "UnknownPublisher"
    ext_type = text(raw.get("extType"), source_id, 256) or ext_name
    version = text(raw.get("version"), source_id, 64) or "unknown"
    prov_state = text(raw.get("provisioningState"), source_id, 64) or "Unknown"
    return {
        "id": ext_id,
        "extension_id": ext_id,
        "name": ext_name,
        "extension_name": ext_name,
        "resource_id": parent_id,
        "resource_name": parent_name,
        "resource_group": rg,
        "resource_type": parent_type,
        "hosting": "arc" if "hybridcompute" in parent_type else "azure",
        "location": location,
        "publisher": publisher,
        "extension_type": ext_type,
        "version": version,
        "provisioning_state": prov_state,
        "enable_automatic_upgrade": boolean(raw.get("enableAutomaticUpgrade"), source_id),
        "auto_upgrade_minor_version": boolean(raw.get("autoUpgradeMinorVersion"), source_id),
        "observed_at_utc": reference,
        "source_id": source_id,
    }


def detect_posture_and_extension_anomalies(resources, extensions, reference):
    anomalies = []
    for ext in extensions:
        state = (ext.get("provisioning_state") or "").strip()
        if state.lower() in ("succeeded", "creating", "updating"):
            continue
        token_haystack = (ext["extension_name"] + " " + ext["extension_type"] + " " + ext["publisher"]).lower()
        is_crit_ext = any(tok in token_haystack for tok in CRITICAL_EXTENSION_TOKENS)
        sev = "high" if state.lower() == "failed" and is_crit_ext else "medium"
        short_hash = hashlib.sha256(ext["extension_id"].lower().encode("utf-8")).hexdigest()[:10]
        anomalies.append({
            "id": "ANM-EXT-" + short_hash,
            "record_kind": "anomaly",
            "category": "extension_failure",
            "category_label": CATEGORY_LABELS["extension_failure"],
            "anomaly_kind": "guest_extension_provisioning_failed",
            "severity": sev,
            "severity_label": SEVERITY_LABELS[sev],
            "title": "Extension " + ext["extension_name"] + " in state " + state + " (" + ext["resource_name"] + ")",
            "resource_id": ext["resource_id"],
            "resource_name": ext["resource_name"],
            "resource_group": ext["resource_group"],
            "resource_type": ext["resource_type"],
            "hosting": ext["hosting"],
            "metric_or_field": "properties.provisioningState (" + ext["publisher"] + "/" + ext["extension_type"] + ")",
            "observed_value": state,
            "baseline_or_expected": "Succeeded",
            "unit": "State",
            "sample_count": 1,
            "window_grain": "PointInTime",
            "observed_at_utc": reference,
            "source_id": "arg_posture_anomalies",
            "workspace_name": "",
            "extension_name": ext["extension_name"],
            "extension_version": ext["version"],
            "summary": (
                "Extension " + ext["extension_name"] + " (" + ext["publisher"] + "/" + ext["extension_type"]
                + ", version " + ext["version"] + ") on " + ext["resource_name"]
                + " reports provisioningState=" + state + "."
            ),
            "learn_url": "https://learn.microsoft.com/azure/azure-arc/servers/manage-vm-extensions",
        })

    for res in resources:
        rtype = res["resource_type"]
        rname = res["resource_name"]
        short_hash = hashlib.sha256(res["resource_id"].lower().encode("utf-8")).hexdigest()[:10]
        if rtype in ("microsoft.hybridcompute/machines", "microsoft.kubernetes/connectedclusters"):
            arc_st = (res.get("arc_status") or "").strip()
            if arc_st.lower() in ("expired", "disconnected", "error"):
                sev = "high" if arc_st.lower() in ("expired", "error") else "medium"
                changed = res.get("arc_last_status_change_utc") or "no_timestamp"
                ver = res.get("arc_agent_version") or "unknown"
                anomalies.append({
                    "id": "ANM-ARC-" + short_hash,
                    "record_kind": "anomaly",
                    "category": "connectivity_posture",
                    "category_label": CATEGORY_LABELS["connectivity_posture"],
                    "anomaly_kind": "arc_agent_" + arc_st.lower(),
                    "severity": sev,
                    "severity_label": SEVERITY_LABELS[sev],
                    "title": "Azure Arc agent in state " + arc_st + " (" + rname + ")",
                    "resource_id": res["resource_id"],
                    "resource_name": rname,
                    "resource_group": res["resource_group"],
                    "resource_type": rtype,
                    "hosting": "arc",
                    "metric_or_field": "properties.status (agentVersion=" + ver + ")",
                    "observed_value": arc_st,
                    "baseline_or_expected": "Connected",
                    "unit": "State",
                    "sample_count": 1,
                    "window_grain": "PointInTime",
                    "observed_at_utc": reference,
                    "source_id": "arg_posture_anomalies",
                    "workspace_name": "",
                    "summary": (
                        "Hybrid resource " + rname + " (" + (res.get("os_sku") or res.get("os_name") or rtype)
                        + ") reports status=" + arc_st + " (last change: " + changed + ", agent " + ver + ")."
                    ),
                    "learn_url": "https://learn.microsoft.com/azure/azure-arc/servers/troubleshoot-agent-onboard",
                })
        if rtype == "microsoft.containerservice/managedclusters":
            pstate = (res.get("power_state") or "").strip()
            prov = (res.get("provisioning_state") or "").strip()
            if prov.lower() == "failed" or (pstate and pstate.lower() not in ("running", "succeeded")):
                sev = "high" if prov.lower() == "failed" else "medium"
                observed_st = prov if prov.lower() == "failed" else pstate
                anomalies.append({
                    "id": "ANM-AKS-" + short_hash,
                    "record_kind": "anomaly",
                    "category": "connectivity_posture",
                    "category_label": CATEGORY_LABELS["connectivity_posture"],
                    "anomaly_kind": "aks_cluster_non_running",
                    "severity": sev,
                    "severity_label": SEVERITY_LABELS[sev],
                    "title": "AKS cluster " + rname + " in state " + observed_st,
                    "resource_id": res["resource_id"],
                    "resource_name": rname,
                    "resource_group": res["resource_group"],
                    "resource_type": rtype,
                    "hosting": "azure",
                    "metric_or_field": "properties.powerState.code / provisioningState",
                    "observed_value": observed_st,
                    "baseline_or_expected": "Running / Succeeded",
                    "unit": "State",
                    "sample_count": 1,
                    "window_grain": "PointInTime",
                    "observed_at_utc": reference,
                    "source_id": "arg_posture_anomalies",
                    "workspace_name": "",
                    "summary": (
                        "AKS cluster " + rname + " (k8s " + (res.get("kubernetes_version") or "n/a")
                        + ") is in state " + observed_st + " (provisioningState=" + prov + ")."
                    ),
                    "learn_url": "https://learn.microsoft.com/azure/aks/start-stop-cluster",
                })
        elif (res.get("provisioning_state") or "").lower() == "failed":
            anomalies.append({
                "id": "ANM-PRV-" + short_hash,
                "record_kind": "anomaly",
                "category": "connectivity_posture",
                "category_label": CATEGORY_LABELS["connectivity_posture"],
                "anomaly_kind": "resource_provisioning_failed",
                "severity": "high",
                "severity_label": SEVERITY_LABELS["high"],
                "title": "Resource " + rname + " with provisioningState=Failed",
                "resource_id": res["resource_id"],
                "resource_name": rname,
                "resource_group": res["resource_group"],
                "resource_type": rtype,
                "hosting": res["hosting"],
                "metric_or_field": "properties.provisioningState",
                "observed_value": "Failed",
                "baseline_or_expected": "Succeeded",
                "unit": "State",
                "sample_count": 1,
                "window_grain": "PointInTime",
                "observed_at_utc": reference,
                "source_id": "arg_posture_anomalies",
                "workspace_name": "",
                "summary": "Resource " + rname + " (" + rtype + ") reports provisioningState=Failed in Azure Resource Manager.",
                "learn_url": "https://learn.microsoft.com/azure/azure-resource-manager/troubleshooting/troubleshooting-deployment-errors",
            })
        elif rtype == "microsoft.compute/virtualmachines":
            pstate = (res.get("power_state") or "").strip().lower()
            if pstate in ("powerstate/deallocated", "powerstate/stopped", "deallocated", "stopped"):
                anomalies.append({
                    "id": "ANM-VM-" + short_hash,
                    "record_kind": "anomaly",
                    "category": "connectivity_posture",
                    "category_label": CATEGORY_LABELS["connectivity_posture"],
                    "anomaly_kind": "vm_stopped_or_deallocated",
                    "severity": "low",
                    "severity_label": SEVERITY_LABELS["low"],
                    "title": "Virtual machine " + rname + " in state " + (res.get("power_state") or "Stopped"),
                    "resource_id": res["resource_id"],
                    "resource_name": rname,
                    "resource_group": res["resource_group"],
                    "resource_type": rtype,
                    "hosting": "azure",
                    "metric_or_field": "instanceView.powerState.code",
                    "observed_value": res.get("power_state") or "Stopped",
                    "baseline_or_expected": "PowerState/running",
                    "unit": "State",
                    "sample_count": 1,
                    "window_grain": "PointInTime",
                    "observed_at_utc": reference,
                    "source_id": "arg_posture_anomalies",
                    "workspace_name": "",
                    "summary": (
                        "Virtual machine " + rname + " (" + (res.get("vm_size") or "VM")
                        + ") is stopped or deallocated (" + (res.get("power_state") or "Stopped") + ")."
                    ),
                    "learn_url": "https://learn.microsoft.com/azure/virtual-machines/states-billing",
                })
    return anomalies


def telemetry_kql_query(grain="1h"):
    return (
        "let cpu_im = InsightsMetrics "
        "| where Origin in ('vm.azm.ms', 'azuremonitor') and Namespace == 'Processor' and Name == 'UtilizationPercentage' "
        "| summarize bin_val=avg(Val), samples=count() by _ResourceId=tolower(_ResourceId), bin(TimeGenerated, " + grain + ") "
        "| extend metric_key='cpu_percent', unit='Percent'; "
        "let mem_im = InsightsMetrics "
        "| where Origin in ('vm.azm.ms', 'azuremonitor') and Namespace == 'Memory' and Name == 'AvailableMB' "
        "| summarize bin_val=min(Val), samples=count() by _ResourceId=tolower(_ResourceId), bin(TimeGenerated, " + grain + ") "
        "| extend metric_key='memory_available_mb', unit='MB'; "
        "let disk_im = InsightsMetrics "
        "| where Origin in ('vm.azm.ms', 'azuremonitor') and Namespace == 'LogicalDisk' and Name == 'FreeSpacePercentage' "
        "| where tostring(parse_json(Tags)['vm.azm.ms/mountId']) !startswith '/snap/' "
        "| summarize bin_val=min(Val), samples=count() by _ResourceId=tolower(_ResourceId), bin(TimeGenerated, " + grain + ") "
        "| extend metric_key='disk_free_percent', unit='Percent'; "
        "let perf_cpu = Perf "
        "| where ObjectName in ('Processor', 'Processor Information') and CounterName == '% Processor Time' and InstanceName in ('_Total', 'Total') "
        "| summarize bin_val=avg(CounterValue), samples=count() by _ResourceId=tolower(_ResourceId), bin(TimeGenerated, " + grain + ") "
        "| extend metric_key='cpu_percent', unit='Percent'; "
        "let combined = union isfuzzy=true cpu_im, mem_im, disk_im, perf_cpu "
        "| where isnotempty(_ResourceId) "
        "| summarize avg_val=round(avg(bin_val), 2), max_val=round(max(bin_val), 2), min_val=round(min(bin_val), 2), "
        "median_val=round(percentile(bin_val, 50), 2), p95_val=round(percentile(bin_val, 95), 2), "
        "high_bins=countif(metric_key == 'cpu_percent' and bin_val >= 85.0), "
        "low_mem_bins=countif(metric_key == 'memory_available_mb' and bin_val <= 512.0), "
        "low_disk_bins=countif(metric_key == 'disk_free_percent' and bin_val <= 15.0), "
        "bins_total=count(), sample_count=sum(samples), last_seen_utc=max(TimeGenerated) "
        "by _ResourceId, metric_key, unit; "
        "let hb = Heartbeat "
        "| where isnotempty(_ResourceId) "
        "| summarize avg_val=round(todouble(count()), 2), max_val=round(todouble(datetime_diff('minute', now(), max(TimeGenerated))), 2), "
        "min_val=0.0, median_val=0.0, p95_val=0.0, high_bins=0, low_mem_bins=0, low_disk_bins=0, "
        "bins_total=count(), sample_count=count(), last_seen_utc=max(TimeGenerated) "
        "by _ResourceId=tolower(_ResourceId) "
        "| extend metric_key='heartbeat_silence_minutes', unit='Minutes'; "
        "union isfuzzy=true combined, hb"
    )


def parse_log_table(payload, source_id):
    if payload.get("error") is not None:
        raise EvidenceError("partial_log_query", "Log Analytics returned a partial/error payload.", source_id)
    tables = payload.get("tables")
    if not isinstance(tables, list) or not tables or not isinstance(tables[0], dict):
        raise EvidenceError("invalid_log_result", "Log Analytics response is missing its primary table.", source_id)
    table = tables[0]
    columns = table.get("columns")
    rows = table.get("rows")
    if not isinstance(columns, list) or not isinstance(rows, list) or len(rows) > MAX_ROWS:
        raise EvidenceError("invalid_log_result", "Log Analytics table columns or rows are invalid.", source_id)
    col_names = [text(col.get("name"), source_id, 128) for col in columns if isinstance(col, dict)]
    if len(col_names) != len(columns) or len(set(col_names)) != len(col_names):
        raise EvidenceError("invalid_log_result", "Log Analytics table column names are invalid or duplicated.", source_id)
    parsed = []
    for row in rows:
        if not isinstance(row, list) or len(row) != len(col_names):
            raise EvidenceError("invalid_log_result", "Log Analytics row length does not match columns.", source_id)
        parsed.append(dict(zip(col_names, row)))
    return parsed


def evaluate_telemetry_row(raw, workspace_name, subscription_id, window, reference):
    source_id = "logs_telemetry_anomalies"
    raw_res_id = text(raw.get("_ResourceId"), source_id, 2048)
    if not raw_res_id or not raw_res_id.lower().startswith("/subscriptions/" + subscription_id.lower() + "/"):
        return None
    res_id = arm_resource_id(raw_res_id, subscription_id, source_id)
    rg, rtype, rname = extract_rg_and_type(res_id)
    hosting = "arc" if "hybridcompute" in rtype or "connectedclusters" in rtype else "azure"
    metric_key = text(raw.get("metric_key"), source_id, 64) or ""
    unit = text(raw.get("unit"), source_id, 32) or "Percent"
    avg_val = number(raw.get("avg_val"), source_id)
    max_val = number(raw.get("max_val"), source_id)
    min_val = number(raw.get("min_val"), source_id)
    median_val = number(raw.get("median_val"), source_id)
    p95_val = number(raw.get("p95_val"), source_id)
    high_bins = int(number(raw.get("high_bins"), source_id) or 0)
    low_mem_bins = int(number(raw.get("low_mem_bins"), source_id) or 0)
    low_disk_bins = int(number(raw.get("low_disk_bins"), source_id) or 0)
    bins_total = int(number(raw.get("bins_total"), source_id) or 0)
    sample_count = int(number(raw.get("sample_count"), source_id) or 0)
    last_seen = text(raw.get("last_seen_utc"), source_id, 64) or reference
    last_seen_iso = iso_utc(parse_utc(last_seen, source_id))
    short_hash = hashlib.sha256((res_id.lower() + "|" + metric_key + "|" + workspace_name).encode("utf-8")).hexdigest()[:10]

    if metric_key == "cpu_percent" and max_val is not None and median_val is not None:
        delta = round(max_val - median_val, 2)
        sustained = high_bins >= 3 or (avg_val is not None and avg_val >= 85.0)
        spike = max_val >= 95.0 or (max_val >= 85.0 and delta >= 25.0)
        if sustained or spike:
            sev = "critical" if (sustained and max_val >= 95.0) else "high" if sustained or max_val >= 95.0 else "medium"
            kind = "sustained_high_cpu" if sustained else "cpu_statistical_spike"
            return {
                "id": "ANM-TEL-" + short_hash,
                "record_kind": "anomaly",
                "category": "telemetry_anomaly",
                "category_label": CATEGORY_LABELS["telemetry_anomaly"],
                "anomaly_kind": kind,
                "severity": sev,
                "severity_label": SEVERITY_LABELS[sev],
                "title": "CPU anomaly on " + rname + " (peak " + grouped(max_val) + "%, median " + grouped(median_val) + "%)",
                "resource_id": res_id,
                "resource_name": rname,
                "resource_group": rg,
                "resource_type": rtype,
                "hosting": hosting,
                "metric_or_field": "Processor/UtilizationPercentage (" + window["grain"] + ")",
                "observed_value": max_val,
                "baseline_or_expected": median_val,
                "average_value": avg_val,
                "p95_value": p95_val,
                "high_bins": high_bins,
                "bins_total": bins_total,
                "unit": unit,
                "sample_count": sample_count,
                "window_grain": window["grain"],
                "observed_at_utc": last_seen_iso,
                "source_id": source_id,
                "workspace_name": workspace_name,
                "summary": (
                    "Telemetry in " + workspace_name + " for " + rname + ": CPU peak=" + grouped(max_val)
                    + "%, average=" + grouped(avg_val) + "%, median=" + grouped(median_val) + "% (Δ+" + grouped(delta)
                    + " pp, " + grouped(high_bins) + "/" + grouped(bins_total) + " intervals >=85%, "
                    + grouped(sample_count) + " samples)."
                ),
                "learn_url": "https://learn.microsoft.com/azure/azure-monitor/vm/vminsights-performance",
            }

    if metric_key == "memory_available_mb" and min_val is not None:
        if min_val <= 512.0 or low_mem_bins >= 2:
            sev = "high" if min_val <= 256.0 else "medium"
            return {
                "id": "ANM-TEL-" + short_hash,
                "record_kind": "anomaly",
                "category": "telemetry_anomaly",
                "category_label": CATEGORY_LABELS["telemetry_anomaly"],
                "anomaly_kind": "low_available_memory",
                "severity": sev,
                "severity_label": SEVERITY_LABELS[sev],
                "title": "Physical memory pressure on " + rname + " (minimum " + grouped(min_val) + " MB available)",
                "resource_id": res_id,
                "resource_name": rname,
                "resource_group": rg,
                "resource_type": rtype,
                "hosting": hosting,
                "metric_or_field": "Memory/AvailableMB (" + window["grain"] + ")",
                "observed_value": min_val,
                "baseline_or_expected": median_val if median_val is not None else 1024.0,
                "average_value": avg_val,
                "p95_value": p95_val,
                "high_bins": low_mem_bins,
                "bins_total": bins_total,
                "unit": "MB",
                "sample_count": sample_count,
                "window_grain": window["grain"],
                "observed_at_utc": last_seen_iso,
                "source_id": source_id,
                "workspace_name": workspace_name,
                "summary": (
                    "Available memory on " + rname + " fell to " + grouped(min_val) + " MB (median "
                    + grouped(median_val) + " MB, " + grouped(low_mem_bins) + "/" + grouped(bins_total)
                    + " intervals <=512 MB in " + workspace_name + ")."
                ),
                "learn_url": "https://learn.microsoft.com/azure/azure-monitor/vm/vminsights-performance",
            }

    if metric_key == "disk_free_percent" and min_val is not None:
        if min_val <= 15.0 or low_disk_bins >= 1:
            sev = "critical" if min_val <= 5.0 else "high" if min_val <= 10.0 else "medium"
            return {
                "id": "ANM-TEL-" + short_hash,
                "record_kind": "anomaly",
                "category": "telemetry_anomaly",
                "category_label": CATEGORY_LABELS["telemetry_anomaly"],
                "anomaly_kind": "low_disk_free_space",
                "severity": sev,
                "severity_label": SEVERITY_LABELS[sev],
                "title": "Low free disk space on " + rname + " (" + grouped(min_val) + "% free)",
                "resource_id": res_id,
                "resource_name": rname,
                "resource_group": rg,
                "resource_type": rtype,
                "hosting": hosting,
                "metric_or_field": "LogicalDisk/FreeSpacePercentage (" + window["grain"] + ")",
                "observed_value": min_val,
                "baseline_or_expected": 15.0,
                "average_value": avg_val,
                "p95_value": p95_val,
                "high_bins": low_disk_bins,
                "bins_total": bins_total,
                "unit": "Percent",
                "sample_count": sample_count,
                "window_grain": window["grain"],
                "observed_at_utc": last_seen_iso,
                "source_id": source_id,
                "workspace_name": workspace_name,
                "summary": (
                    "Logical volume on " + rname + " recorded " + grouped(min_val)
                    + "% free space (minimum threshold 15%, " + grouped(sample_count)
                    + " samples in " + workspace_name + ")."
                ),
                "learn_url": "https://learn.microsoft.com/azure/azure-monitor/vm/vminsights-performance",
            }

    if metric_key == "heartbeat_silence_minutes" and max_val is not None:
        if max_val >= 15.0:
            sev = "high" if max_val >= 60.0 else "medium"
            return {
                "id": "ANM-HB-" + short_hash,
                "record_kind": "anomaly",
                "category": "telemetry_anomaly",
                "category_label": CATEGORY_LABELS["telemetry_anomaly"],
                "anomaly_kind": "heartbeat_silence_gap",
                "severity": sev,
                "severity_label": SEVERITY_LABELS[sev],
                "title": "Heartbeat silence (" + grouped(int(round(max_val))) + " min without a heartbeat) on " + rname,
                "resource_id": res_id,
                "resource_name": rname,
                "resource_group": rg,
                "resource_type": rtype,
                "hosting": hosting,
                "metric_or_field": "Heartbeat/SilenceMinutes",
                "observed_value": round(max_val, 1),
                "baseline_or_expected": 5.0,
                "average_value": avg_val,
                "p95_value": None,
                "high_bins": 1,
                "bins_total": bins_total,
                "unit": "Minutes",
                "sample_count": sample_count,
                "window_grain": window["grain"],
                "observed_at_utc": last_seen_iso,
                "source_id": source_id,
                "workspace_name": workspace_name,
                "summary": (
                    "Resource " + rname + " has sent no heartbeat for " + grouped(round(max_val, 1))
                    + " minutes in the Heartbeat table of " + workspace_name
                    + " (last heartbeat: " + last_seen_iso + ")."
                ),
                "learn_url": "https://learn.microsoft.com/azure/azure-monitor/agents/azure-monitor-agent-troubleshoot",
            }
    return None


def collect_logs_telemetry(logs_reader, config, window, reference):
    workspaces = config["workspaces"]
    if not workspaces:
        receipt = source_receipt(
            "logs_telemetry_anomalies",
            reference,
            status="not_configured",
            window=window,
            note="No Log Analytics workspaces configured in APPROVED_LOG_WORKSPACES.",
            workspaces_queried=[],
        )
        return [], [], receipt

    grain_kql = "5m" if window["grain"] == "PT5M" else "1h"
    query = telemetry_kql_query(grain_kql)
    anomalies_by_key = {}
    telemetry_summaries = []
    ws_receipts = []
    total_records = 0
    errors = []

    for ws in workspaces:
        url = LOGS_ORIGIN + "/v1/workspaces/" + ws["customer_id"] + "/query"
        logs_reader.allow(url, "POST")
        body = {"query": query, "timespan": window["timespan_iso"]}
        try:
            payload = logs_reader.request("POST", url, "logs_telemetry_anomalies", body=body)
            rows = parse_log_table(payload, "logs_telemetry_anomalies")
            total_records += len(rows)
            ws_receipts.append({
                "workspace_name": ws["name"],
                "customer_id": ws["customer_id"],
                "status": "complete",
                "records": len(rows),
            })
            for row in rows:
                telemetry_summaries.append({
                    "workspace_name": ws["name"],
                    "resource_id": text(row.get("_ResourceId"), "logs_telemetry_anomalies", 2048),
                    "metric_key": text(row.get("metric_key"), "logs_telemetry_anomalies", 64),
                    "avg_val": number(row.get("avg_val"), "logs_telemetry_anomalies"),
                    "max_val": number(row.get("max_val"), "logs_telemetry_anomalies"),
                    "min_val": number(row.get("min_val"), "logs_telemetry_anomalies"),
                    "median_val": number(row.get("median_val"), "logs_telemetry_anomalies"),
                    "sample_count": int(number(row.get("sample_count"), "logs_telemetry_anomalies") or 0),
                })
                anom = evaluate_telemetry_row(row, ws["name"], config["subscription_id"], window, reference)
                if anom is not None:
                    dedup_key = (anom["resource_id"].lower(), anom["anomaly_kind"])
                    existing = anomalies_by_key.get(dedup_key)
                    if existing is None or SEVERITY_RANK[anom["severity"]] < SEVERITY_RANK[existing["severity"]]:
                        anomalies_by_key[dedup_key] = anom
        except EvidenceError as exc:
            err_doc = exc.public()
            err_doc["workspace_name"] = ws["name"]
            errors.append(err_doc)
            ws_receipts.append({
                "workspace_name": ws["name"],
                "customer_id": ws["customer_id"],
                "status": "denied" if exc.http_status in (401, 403) else "error",
                "records": 0,
                "error": err_doc,
            })

    ok_count = sum(w["status"] == "complete" for w in ws_receipts)
    if ok_count == len(ws_receipts):
        status = "complete"
    elif ok_count > 0:
        status = "partial"
    elif any(w["status"] == "denied" for w in ws_receipts):
        status = "denied"
    else:
        status = "error"

    receipt = source_receipt(
        "logs_telemetry_anomalies",
        reference,
        status=status,
        records=total_records,
        pages=len(ws_receipts),
        pagination_complete=status == "complete",
        errors=errors,
        window=window,
        workspaces_queried=ws_receipts,
        read_signature="POST https://api.loganalytics.io/v1/workspaces/{workspace_id}/query",
        note="Bounded KQL queries over InsightsMetrics, Perf, and Heartbeat in the approved Log Analytics workspaces.",
    )
    sorted_anomalies = sorted(
        anomalies_by_key.values(),
        key=lambda a: (SEVERITY_RANK[a["severity"]], a["resource_name"].lower(), a["id"]),
    )
    return sorted_anomalies, telemetry_summaries, receipt


def normalize_advisor_row(raw, subscription_id, reference):
    source_id = "arm_advisor_recommendations"
    rec_id = text(raw.get("id"), source_id, 2048)
    name = text(raw.get("name"), source_id, 256)
    if not rec_id or not name:
        raise EvidenceError("invalid_advisor", "Advisor recommendation is missing id or name.", source_id)
    props = obj(raw.get("properties", {}), source_id)
    adv_cat = text(props.get("category"), source_id, 64) or "HighAvailability"
    impact = text(props.get("impact"), source_id, 32) or "Medium"
    sev_map = {"high": "high", "medium": "medium", "low": "low"}
    sev = sev_map.get(impact.lower(), "medium")
    short_desc = obj(props.get("shortDescription", {}), source_id) if props.get("shortDescription") else {}
    problem = text(short_desc.get("problem"), source_id, 1024) or ("Azure Advisor recommendation (" + adv_cat + ")")
    solution = text(short_desc.get("solution"), source_id, 1024) or problem
    res_meta = obj(props.get("resourceMetadata", {}), source_id) if props.get("resourceMetadata") else {}
    target_id = text(res_meta.get("resourceId"), source_id, 2048) or rec_id.split("/providers/Microsoft.Advisor/")[0]
    if target_id and target_id.lower().startswith("/subscriptions/"):
        target_id = arm_resource_id(target_id, subscription_id, source_id)
    rg, rtype, rname = extract_rg_and_type(target_id)
    impacted_val = text(props.get("impactedValue"), source_id, 256) or rname
    updated = text(props.get("lastUpdated"), source_id, 64) or reference
    updated_iso = iso_utc(parse_utc(updated, source_id))
    short_hash = hashlib.sha256(rec_id.lower().encode("utf-8")).hexdigest()[:10]
    return {
        "id": "ADV-" + short_hash,
        "recommendation_id": name,
        "native_id": rec_id,
        "record_kind": "advisor",
        "category": "advisor_recommendation",
        "category_label": CATEGORY_LABELS["advisor_recommendation"],
        "advisor_category": adv_cat,
        "impact": impact,
        "severity": sev,
        "severity_label": SEVERITY_LABELS[sev],
        "problem": problem,
        "solution": solution,
        "title": problem,
        "resource_id": target_id,
        "resource_name": impacted_val,
        "resource_group": rg,
        "resource_type": rtype,
        "last_updated_utc": updated_iso,
        "observed_at_utc": reference,
        "source_id": source_id,
        "summary": "[" + adv_cat + " / Impact " + impact + "] " + problem + " — " + solution,
        "learn_url": "https://learn.microsoft.com/azure/advisor/advisor-overview",
    }


def synthesize_actions(incidents, anomalies, advisor_rows):
    actions = []

    for inc in incidents:
        is_active = (inc.get("monitor_condition") or "").lower() in ("fired", "active") or (inc.get("state") or "").lower() in ("new", "acknowledged", "active")
        if inc["category"] == "native_alert":
            horizon = "immediate_24h" if (is_active and inc["severity"] in ("critical", "high")) else "short_term_7d"
            effort = "low" if inc["severity"] in ("medium", "low") else "medium"
            owner = "Reliability engineering / Monitoring operations"
            rec_text = (
                "Check the firing condition (" + inc["monitor_condition"] + " / " + inc["state"]
                + ") in Azure Monitor for " + inc["resource_name"] + ", correlate it with recent changes, and document the operational closure."
            )
        else:
            horizon = "immediate_24h" if (is_active and inc["signal_type"] == "ServiceIssue") else "short_term_7d"
            effort = "low"
            owner = "Cloud governance / Platform incident management"
            rec_text = (
                "Review the official tracking ID " + (inc.get("tracking_id") or inc["id"])
                + " in Azure Service Health (" + inc["monitor_service"]
                + "), assess the maintenance window or mitigation, and confirm the actual impact on dependent workloads."
            )
        actions.append({
            "_sort_key": (
                0 if horizon == "immediate_24h" else 1,
                SEVERITY_RANK[inc["severity"]],
                inc["resource_name"].lower(),
                inc["id"],
            ),
            "category": inc["category"],
            "category_label": inc["category_label"],
            "severity": inc["severity"],
            "severity_label": inc["severity_label"],
            "horizon": horizon,
            "horizon_label": HORIZON_LABELS[horizon],
            "effort": effort,
            "effort_label": EFFORT_LABELS[effort],
            "title": "Address " + ("active alert " if is_active else "recorded incident ") + "on " + inc["resource_name"],
            "resource_id": inc["resource_id"],
            "resource_name": inc["resource_name"],
            "resource_group": inc["resource_group"],
            "resource_type": inc["resource_type"],
            "owner_scope": owner,
            "linked_evidence_ids": [inc["id"]],
            "source_ids": [inc["source_id"]],
            "evidence_summary": inc["summary"],
            "recommendation": rec_text,
            "learn_url": inc["learn_url"],
        })

    ext_by_resource = {}
    for anom in anomalies:
        if anom["category"] == "extension_failure":
            ext_by_resource.setdefault(anom["resource_id"], []).append(anom)
        elif anom["category"] == "connectivity_posture":
            is_arc = anom["hosting"] == "arc"
            is_aks = "managedclusters" in anom["resource_type"]
            horizon = "short_term_7d" if anom["severity"] in ("critical", "high", "medium") else "monthly_cycle"
            owner = (
                "Hybrid operations / Azure Arc administration"
                if is_arc
                else "Container platform / AKS operations"
                if is_aks
                else "Cloud infrastructure operations"
            )
            if is_arc:
                rec_text = (
                    "Inspect the himds service and the outbound TLS connectivity of the Azure Connected Machine agent on "
                    + anom["resource_name"] + " (current state: " + str(anom["observed_value"])
                    + "); renew the credentials or reconnect the machine if its identity certificate has expired."
                )
            elif is_aks:
                rec_text = (
                    "Confirm whether the stop/state (" + str(anom["observed_value"]) + ") of AKS cluster "
                    + anom["resource_name"] + " is a planned cost-saving measure or a control plane failure; "
                    + "avoid keeping clusters stopped for more than 12 months so that the Kubernetes version stays supported."
                )
            else:
                rec_text = (
                    "Review the operational state (" + str(anom["observed_value"]) + ") of "
                    + anom["resource_name"] + " and confirm that it matches the catalog of active services."
                )
            actions.append({
                "_sort_key": (
                    1 if horizon == "short_term_7d" else 2,
                    SEVERITY_RANK[anom["severity"]],
                    anom["resource_name"].lower(),
                    anom["id"],
                ),
                "category": anom["category"],
                "category_label": anom["category_label"],
                "severity": anom["severity"],
                "severity_label": anom["severity_label"],
                "horizon": horizon,
                "horizon_label": HORIZON_LABELS[horizon],
                "effort": "medium" if is_arc or is_aks else "low",
                "effort_label": EFFORT_LABELS["medium" if is_arc or is_aks else "low"],
                "title": "Review and fix the operational state of " + anom["resource_name"] + " (" + str(anom["observed_value"]) + ")",
                "resource_id": anom["resource_id"],
                "resource_name": anom["resource_name"],
                "resource_group": anom["resource_group"],
                "resource_type": anom["resource_type"],
                "owner_scope": owner,
                "linked_evidence_ids": [anom["id"]],
                "source_ids": [anom["source_id"]],
                "evidence_summary": anom["summary"],
                "recommendation": rec_text,
                "learn_url": anom["learn_url"],
            })
        elif anom["category"] == "telemetry_anomaly":
            horizon = "immediate_24h" if anom["severity"] == "critical" else "short_term_7d"
            actions.append({
                "_sort_key": (
                    0 if horizon == "immediate_24h" else 1,
                    SEVERITY_RANK[anom["severity"]],
                    anom["resource_name"].lower(),
                    anom["id"],
                ),
                "category": "telemetry_anomaly",
                "category_label": CATEGORY_LABELS["telemetry_anomaly"],
                "severity": anom["severity"],
                "severity_label": SEVERITY_LABELS[anom["severity"]],
                "horizon": horizon,
                "horizon_label": HORIZON_LABELS[horizon],
                "effort": "medium",
                "effort_label": EFFORT_LABELS["medium"],
                "title": "Investigate telemetry anomaly on " + anom["resource_name"] + " (" + anom["metric_or_field"] + ")",
                "resource_id": anom["resource_id"],
                "resource_name": anom["resource_name"],
                "resource_group": anom["resource_group"],
                "resource_type": anom["resource_type"],
                "owner_scope": "Capacity and observability engineering",
                "linked_evidence_ids": [anom["id"]],
                "source_ids": [anom["source_id"]],
                "evidence_summary": anom["summary"],
                "recommendation": (
                    "Analyze the processes and pressure intervals on " + anom["resource_name"]
                    + " reported in Log Analytics (" + (anom.get("workspace_name") or "workspace")
                    + "), check the SKU sizing and possible resource leaks, and tune the preventive alert thresholds."
                ),
                "learn_url": anom["learn_url"],
            })

    for res_id, ext_anoms in sorted(ext_by_resource.items()):
        highest = min(ext_anoms, key=lambda x: SEVERITY_RANK[x["severity"]])
        ext_names = ", ".join(sorted({x.get("extension_name") or x["title"] for x in ext_anoms}))
        ev_ids = [x["id"] for x in ext_anoms]
        horizon = "short_term_7d"
        actions.append({
            "_sort_key": (
                1,
                SEVERITY_RANK[highest["severity"]],
                highest["resource_name"].lower(),
                ev_ids[0],
            ),
            "category": "extension_failure",
            "category_label": CATEGORY_LABELS["extension_failure"],
            "severity": highest["severity"],
            "severity_label": SEVERITY_LABELS[highest["severity"]],
            "horizon": horizon,
            "horizon_label": HORIZON_LABELS[horizon],
            "effort": "medium",
            "effort_label": EFFORT_LABELS["medium"],
            "title": "Remediate failed extensions (" + ext_names + ") on " + highest["resource_name"],
            "resource_id": res_id,
            "resource_name": highest["resource_name"],
            "resource_group": highest["resource_group"],
            "resource_type": highest["resource_type"],
            "owner_scope": "Endpoint security and hybrid operations (MDE / Entra ID / AMA)",
            "linked_evidence_ids": ev_ids,
            "source_ids": ["arg_posture_anomalies"],
            "evidence_summary": "; ".join(x["summary"] for x in ext_anoms),
            "recommendation": (
                "First verify the base agent connectivity on " + highest["resource_name"]
                + ", review the local installation logs of " + ext_names
                + ", and reprovision the extensions in a controlled change window."
            ),
            "learn_url": "https://learn.microsoft.com/azure/azure-arc/servers/troubleshoot-vm-extensions",
        })

    for adv in advisor_rows:
        horizon = "short_term_7d" if adv["severity"] == "high" else "monthly_cycle"
        actions.append({
            "_sort_key": (
                1 if horizon == "short_term_7d" else 2,
                SEVERITY_RANK[adv["severity"]],
                adv["resource_name"].lower(),
                adv["id"],
            ),
            "category": "advisor_recommendation",
            "category_label": CATEGORY_LABELS["advisor_recommendation"],
            "severity": adv["severity"],
            "severity_label": SEVERITY_LABELS[adv["severity"]],
            "horizon": horizon,
            "horizon_label": HORIZON_LABELS[horizon],
            "effort": "medium" if adv["severity"] == "high" else "low",
            "effort_label": EFFORT_LABELS["medium" if adv["severity"] == "high" else "low"],
            "title": "Evaluate Azure Advisor recommendation (" + adv["advisor_category"] + ") on " + adv["resource_name"],
            "resource_id": adv["resource_id"],
            "resource_name": adv["resource_name"],
            "resource_group": adv["resource_group"],
            "resource_type": adv["resource_type"],
            "owner_scope": "Cloud architecture and WAF continuous improvement",
            "linked_evidence_ids": [adv["id"]],
            "source_ids": ["arm_advisor_recommendations"],
            "evidence_summary": adv["summary"],
            "recommendation": adv["solution"],
            "learn_url": adv["learn_url"],
        })

    actions.sort(key=lambda item: item["_sort_key"])
    finalized = []
    for idx, item in enumerate(actions, start=1):
        clean = {k: v for k, v in item.items() if k != "_sort_key"}
        short_hash = hashlib.sha256((clean["resource_id"].lower() + "|" + clean["title"] + "|" + str(idx)).encode("utf-8")).hexdigest()[:8]
        clean["id"] = f"ACT-{idx:03d}-{short_hash}"
        clean["priority_rank"] = idx
        finalized.append(clean)
    return finalized


def rollup_resources(estate_resources, extensions, incidents, anomalies, actions, telemetry_summaries):
    by_id = {}
    for res in estate_resources:
        rid = res["resource_id"].lower()
        by_id[rid] = {
            **res,
            "incident_count": 0,
            "anomaly_count": 0,
            "failed_extension_count": 0,
            "extensions_total": 0,
            "action_count": 0,
            "highest_severity": "low",
            "status": "healthy",
            "telemetry_metrics": {},
        }

    for ext in extensions:
        rid = ext["resource_id"].lower()
        if rid in by_id:
            by_id[rid]["extensions_total"] += 1
            if (ext.get("provisioning_state") or "").lower() not in ("succeeded", "creating", "updating"):
                by_id[rid]["failed_extension_count"] += 1

    for t_row in telemetry_summaries:
        rid = (t_row.get("resource_id") or "").lower()
        if rid in by_id and t_row.get("metric_key"):
            by_id[rid]["telemetry_metrics"][t_row["metric_key"]] = {
                "avg": t_row.get("avg_val"),
                "max": t_row.get("max_val"),
                "min": t_row.get("min_val"),
                "median": t_row.get("median_val"),
                "samples": t_row.get("sample_count"),
            }

    def bump_sev(entry, sev):
        if entry["status"] == "healthy" or SEVERITY_RANK[sev] < SEVERITY_RANK[entry["highest_severity"]]:
            entry["highest_severity"] = sev

    for inc in incidents:
        rid = inc["resource_id"].lower()
        if rid in by_id:
            by_id[rid]["incident_count"] += 1
            bump_sev(by_id[rid], inc["severity"])
            by_id[rid]["status"] = "attention"

    for anom in anomalies:
        rid = anom["resource_id"].lower()
        if rid in by_id:
            by_id[rid]["anomaly_count"] += 1
            bump_sev(by_id[rid], anom["severity"])
            if anom["severity"] in ("critical", "high", "medium"):
                by_id[rid]["status"] = "attention"
            elif by_id[rid]["status"] == "healthy":
                by_id[rid]["status"] = "review"

    for act in actions:
        rid = act["resource_id"].lower()
        if rid in by_id:
            by_id[rid]["action_count"] += 1

    rolled = []
    for entry in by_id.values():
        sev = entry["highest_severity"] if entry["status"] != "healthy" else "low"
        entry["severity"] = sev
        entry["severity_label"] = SEVERITY_LABELS[sev] if entry["status"] != "healthy" else "Normal"
        rolled.append(entry)

    rolled.sort(
        key=lambda r: (
            0 if r["status"] == "attention" else 1 if r["status"] == "review" else 2,
            SEVERITY_RANK[r["severity"]],
            r["resource_name"].lower(),
        )
    )
    return rolled


def collect_live(config, window, reference):
    identity = Identity(config)
    try:
        arm_reader = HttpReader(identity, ARM_ORIGIN, "arm")
        logs_reader = HttpReader(identity, LOGS_ORIGIN, "logs")
        sub_id = config["subscription_id"]

        alerts, alerts_receipt = read_arg_query(
            arm_reader,
            sub_id,
            arg_alerts_query(),
            "arg_alerts_incidents",
            reference,
            window,
            lambda raw: normalize_alert_row(raw, sub_id, window, reference),
        )
        alerts_receipt["note"] = "Azure Monitor native alerts (alertsmanagementresources) active or updated in the window."

        sh_query = urlencode({
            "api-version": RESOURCE_HEALTH_API_VERSION,
            "queryStartTime": window["start_utc"],
        })
        sh_url = ARM_ORIGIN + "/subscriptions/" + sub_id + "/providers/Microsoft.ResourceHealth/events?" + sh_query
        sh_events, sh_receipt = read_arm_pages(
            arm_reader,
            sh_url,
            "arm_service_health",
            reference,
            window,
            lambda raw: normalize_service_health_row(raw, sub_id, window, reference),
        )
        sh_receipt["note"] = "Official Azure Service Health communications from Microsoft.ResourceHealth (ServiceIssue and PlannedMaintenance)."

        estate_resources, posture_receipt = read_arg_query(
            arm_reader,
            sub_id,
            arg_inventory_query(),
            "arg_posture_anomalies",
            reference,
            window,
            lambda raw: normalize_estate_resource(raw, sub_id, reference),
        )
        posture_receipt["note"] = "Azure Resource Graph operational inventory (VMs, Azure Arc, AKS, Container Apps, Web Apps, Storage, Key Vault, DBs)."

        extensions, ext_receipt = read_arg_query(
            arm_reader,
            sub_id,
            arg_extensions_query(),
            "arg_guest_extensions",
            reference,
            window,
            lambda raw: normalize_extension_row(raw, sub_id, reference),
        )
        ext_receipt["note"] = "Extension metadata of VMs and Azure Arc servers (settings and protectedSettings are never read)."

        telemetry_anomalies, telemetry_summaries, logs_receipt = collect_logs_telemetry(
            logs_reader, config, window, reference
        )

        adv_url = (
            ARM_ORIGIN + "/subscriptions/" + sub_id
            + "/providers/Microsoft.Advisor/recommendations?api-version=" + ADVISOR_API_VERSION
        )
        advisor_rows, advisor_receipt = read_arm_pages(
            arm_reader,
            adv_url,
            "arm_advisor_recommendations",
            reference,
            window,
            lambda raw: normalize_advisor_row(raw, sub_id, reference),
        )
        advisor_receipt["note"] = "Cached Azure Advisor recommendations for the subscription (Microsoft.Advisor)."

        sources = [
            alerts_receipt,
            sh_receipt,
            posture_receipt,
            ext_receipt,
            logs_receipt,
            advisor_receipt,
        ]
        if all(s["status"] in ("denied", "error") for s in (alerts_receipt, posture_receipt)):
            first_err = (alerts_receipt["errors"] or posture_receipt["errors"] or [{}])[0]
            raise EvidenceError(
                first_err.get("code", "all_sources_failed"),
                "Primary Azure Resource Graph sources failed; no synthetic or empty report is generated.",
                first_err.get("source_id", "arg_posture_anomalies"),
                first_err.get("http_status"),
            )

        return {
            "subscription_id": sub_id,
            "alerts": alerts,
            "service_health": sh_events,
            "estate_resources": estate_resources,
            "extensions": extensions,
            "telemetry_anomalies": telemetry_anomalies,
            "telemetry_summaries": telemetry_summaries,
            "advisor": advisor_rows,
            "sources": sources,
        }
    finally:
        identity.close()


def finish_snapshot(raw, window, reference, provenance="LIVE"):
    if provenance not in ("LIVE", "SIMULATED"):
        raise EvidenceError("invalid_provenance", "provenance must be LIVE or SIMULATED.", "digest")
    validate_logo(CLIENT_LOGO_DATA_URI, CLIENT_LOGO_ALT)

    incidents = sorted(
        list(raw.get("alerts", [])) + list(raw.get("service_health", [])),
        key=lambda item: (SEVERITY_RANK[item["severity"]], item["start_time_utc"], item["id"]),
    )
    posture_anomalies = detect_posture_and_extension_anomalies(
        raw.get("estate_resources", []),
        raw.get("extensions", []),
        reference,
    )
    anomalies = sorted(
        posture_anomalies + list(raw.get("telemetry_anomalies", [])),
        key=lambda item: (SEVERITY_RANK[item["severity"]], item["category"], item["resource_name"].lower(), item["id"]),
    )
    advisor_rows = sorted(
        list(raw.get("advisor", [])),
        key=lambda item: (SEVERITY_RANK[item["severity"]], item["advisor_category"], item["id"]),
    )
    actions = synthesize_actions(incidents, anomalies, advisor_rows)
    resources = rollup_resources(
        raw.get("estate_resources", []),
        raw.get("extensions", []),
        incidents,
        anomalies,
        actions,
        raw.get("telemetry_summaries", []),
    )
    sources = list(raw.get("sources", []))

    native_alert_count = sum(i["category"] == "native_alert" for i in incidents)
    sh_count = sum(i["category"] == "service_health" for i in incidents)
    ext_fail_count = sum(a["category"] == "extension_failure" for a in anomalies)
    posture_count = sum(a["category"] == "connectivity_posture" for a in anomalies)
    tel_anom_count = sum(a["category"] == "telemetry_anomaly" for a in anomalies)
    imm_actions = sum(act["horizon"] == "immediate_24h" for act in actions)
    short_actions = sum(act["horizon"] == "short_term_7d" for act in actions)
    month_actions = sum(act["horizon"] == "monthly_cycle" for act in actions)
    attention_res = sum(r["status"] == "attention" for r in resources)
    degraded_sources = [s["id"] for s in sources if s["status"] not in ("complete", "not_configured")]

    counts = {
        "incidents_total": len(incidents),
        "native_alerts_total": native_alert_count,
        "service_health_total": sh_count,
        "anomalies_total": len(anomalies),
        "extension_failures_total": ext_fail_count,
        "connectivity_posture_total": posture_count,
        "telemetry_anomalies_total": tel_anom_count,
        "advisor_recommendations_total": len(advisor_rows),
        "actions_total": len(actions),
        "actions_immediate_24h": imm_actions,
        "actions_short_term_7d": short_actions,
        "actions_monthly_cycle": month_actions,
        "resources_total": len(resources),
        "resources_attention": attention_res,
        "extensions_evaluated": len(raw.get("extensions", [])),
        "severity_breakdown": {
            sev: sum(item["severity"] == sev for item in (incidents + anomalies))
            for sev in ("critical", "high", "medium", "low")
        },
    }

    executive_messages = [
        (
            "Evaluation window: " + window["label"] + " (" + window["start_utc"] + " → " + window["end_utc"]
            + ") over " + grouped(counts["resources_total"]) + " inventoried resources ("
            + grouped(counts["resources_attention"]) + " need operational attention)."
        ),
        (
            "Consolidated incidents: " + grouped(counts["incidents_total"]) + " recorded ("
            + grouped(native_alert_count) + " Azure Monitor native alerts and "
            + grouped(sh_count) + " official Azure Service Health communications)."
        ),
        (
            "Technical anomalies detected: " + grouped(counts["anomalies_total"]) + " in total ("
            + grouped(ext_fail_count) + " VM/Arc extension failures, "
            + grouped(posture_count) + " connectivity/control plane anomalies, and "
            + grouped(tel_anom_count) + " telemetry statistical/threshold anomalies)."
        ),
        (
            "Recommended action plan: " + grouped(counts["actions_total"]) + " prioritized actions ("
            + grouped(imm_actions) + " Immediate <24h, "
            + grouped(short_actions) + " Short term 1-7 days, and "
            + grouped(month_actions) + " Monthly cycle), correlated with "
            + grouped(counts["advisor_recommendations_total"]) + " Azure Advisor recommendations."
        ),
        (
            "Source coverage: " + grouped(len(sources) - len(degraded_sources)) + " of " + grouped(len(sources))
            + " evidence streams completed in read-only mode, without changing resources or agents."
        ),
    ]

    return {
        "schema_version": "operations-digest-v1",
        "provenance": provenance,
        "reference_utc": reference,
        "subscription_id": raw["subscription_id"],
        "client": {
            "name": CLIENT_NAME.strip(),
            "logo_data_uri": CLIENT_LOGO_DATA_URI,
            "logo_alt": CLIENT_LOGO_ALT.strip(),
        },
        "window": window,
        "counts": counts,
        "executive_messages": executive_messages,
        "incidents": incidents,
        "anomalies": anomalies,
        "actions": actions,
        "resources": resources,
        "extensions": raw.get("extensions", []),
        "advisor": advisor_rows,
        "sources": sources,
        "methodology": {
            "read_only": True,
            "official_sla_calculation": False,
            "scheduled_cadence_cron": "30 8 1 * *",
            "scheduled_default_period": "previous_month",
            "supported_periods": list(PERIODS),
            "evidence_streams": [
                "arg_alerts_incidents (microsoft.alertsmanagement/alerts)",
                "arm_service_health (Microsoft.ResourceHealth/events)",
                "arg_posture_anomalies & arg_guest_extensions (Azure Resource Graph)",
                "logs_telemetry_anomalies (Log Analytics InsightsMetrics, Perf, Heartbeat)",
                "arm_advisor_recommendations (Microsoft.Advisor/recommendations)",
            ],
            "limitations": [
                "Native alerts and Service Health events reflect the state and timestamps that Azure Monitor and Resource Health recorded at query time.",
                "Extension and Azure Arc agent state in Azure Resource Graph is a control plane observation; the tool doesn't read protected settings or run commands inside the guest operating system.",
                "Telemetry anomalies are calculated over the approved Log Analytics workspaces, for the resources that emit InsightsMetrics, Perf, or Heartbeat data in the window.",
                "Recommended actions are prioritized operational guidance for human review; the agent operates strictly in read-only mode.",
            ],
        },
    }


def collection_disclosure(snapshot):
    return {
        "reference_utc": snapshot["reference_utc"],
        "fresh_collection": True,
        "provenance": snapshot["provenance"],
        "subscription_id": snapshot["subscription_id"],
        "window": snapshot["window"],
        "source_status_counts": dict(Counter(s["status"] for s in snapshot["sources"])),
        "source_total": len(snapshot["sources"]),
        "source_details_view": "coverage",
        "paging_basis": "Local offset in this fresh collection; not a persistent cross-call cursor.",
    }


def summary_row(snapshot):
    return {
        "subscription_id": snapshot["subscription_id"],
        "reference_utc": snapshot["reference_utc"],
        "window": snapshot["window"],
        "counts": snapshot["counts"],
        "executive_messages": snapshot["executive_messages"],
        "official_sla_calculation": False,
    }


def snapshot_rows(snapshot, view):
    return {
        "summary": [summary_row(snapshot)],
        "incidents": snapshot["incidents"],
        "anomalies": snapshot["anomalies"],
        "actions": snapshot["actions"],
        "resources": snapshot["resources"],
        "advisor": snapshot["advisor"],
        "coverage": snapshot["sources"],
    }[view]


def query_snapshot(snapshot, params):
    view = params["view"]
    rows = snapshot_rows(snapshot, view)

    def matches(row):
        if params["category"] != "all" and row.get("category") != params["category"]:
            return False
        if params["severity"] != "all" and row.get("severity") != params["severity"]:
            return False
        if params["resource_name"]:
            target = params["resource_name"].lower()
            rname = str(row.get("resource_name") or row.get("name") or "").lower()
            if target != rname and target not in rname:
                return False
        return True

    matched = [row for row in rows if matches(row)]
    selected = matched[params["offset"]:params["offset"] + params["limit"]]
    partial = any(s["status"] not in ("complete", "not_configured") for s in snapshot["sources"])
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
                "message": "A single row exceeds the 3500-byte JSON transport budget; inspect the full snapshot JSON.",
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
    escaped = (
        document.replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )
    if json.loads(escaped) != snapshot:
        raise EvidenceError("round_trip_failed", "Embedded JSON failed lossless round-trip verification.", "renderer")
    return escaped


def render_html(snapshot):
    if HTML_TEMPLATE.count("__REPORT_DATA_JSON__") != 1:
        raise EvidenceError("template_missing", "Build the HTML template into the standalone tool with build_tool.py.", "renderer")
    validate_logo(snapshot["client"]["logo_data_uri"], snapshot["client"].get("logo_alt", CLIENT_LOGO_ALT))
    return HTML_TEMPLATE.replace("__REPORT_DATA_JSON__", safe_json(snapshot))


def csv_cell(value):
    if value is None:
        return ""
    text_val = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")) if isinstance(value, (dict, list)) else str(value)
    return "'" + text_val if text_val.lstrip().startswith(("=", "+", "-", "@", "\t", "\r", "\n")) else text_val


def csv_document(rows, fields):
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(fields)
    for row in rows:
        writer.writerow([csv_cell(row.get(field)) for field in fields])
    return stream.getvalue()


def incidents_and_anomalies_csv_rows(snapshot):
    rows = []
    for inc in snapshot["incidents"]:
        rows.append({
            "record_kind": "incident",
            "id": inc["id"],
            "category": inc["category"],
            "severity": inc["severity"],
            "state_or_kind": inc["monitor_condition"] + " / " + inc["state"],
            "title": inc["title"],
            "resource_name": inc["resource_name"],
            "resource_group": inc["resource_group"],
            "resource_type": inc["resource_type"],
            "resource_id": inc["resource_id"],
            "metric_or_signal": inc["signal_type"],
            "observed_value": inc["native_severity"],
            "baseline_or_expected": "NoAlert",
            "unit": "Signal",
            "observed_at_utc": inc["last_updated_utc"],
            "source_id": inc["source_id"],
            "summary": inc["summary"],
            "learn_url": inc["learn_url"],
            "details_json": inc,
        })
    for anom in snapshot["anomalies"]:
        rows.append({
            "record_kind": "anomaly",
            "id": anom["id"],
            "category": anom["category"],
            "severity": anom["severity"],
            "state_or_kind": anom["anomaly_kind"],
            "title": anom["title"],
            "resource_name": anom["resource_name"],
            "resource_group": anom["resource_group"],
            "resource_type": anom["resource_type"],
            "resource_id": anom["resource_id"],
            "metric_or_signal": anom["metric_or_field"],
            "observed_value": anom["observed_value"],
            "baseline_or_expected": anom["baseline_or_expected"],
            "unit": anom["unit"],
            "observed_at_utc": anom["observed_at_utc"],
            "source_id": anom["source_id"],
            "summary": anom["summary"],
            "learn_url": anom["learn_url"],
            "details_json": anom,
        })
    return rows


def actions_csv_rows(snapshot):
    return [
        {
            **act,
            "details_json": act,
        }
        for act in snapshot["actions"]
    ]


def artifact_directory():
    try:
        cwd = Path.cwd()
        root = cwd.resolve(strict=True)
        linked = any(part.is_symlink() or getattr(part, "is_junction", lambda: False)() for part in (cwd, *cwd.parents))
    except (OSError, RuntimeError) as exc:
        raise EvidenceError("unsafe_artifact_root", "Runtime cwd must resolve to an existing directory.", "artifact_storage") from exc
    if root == Path(root.anchor) or not root.is_dir() or linked:
        raise EvidenceError("unsafe_artifact_root", "Filesystem roots, symlink/junction cwd ancestors, and non-directories are forbidden.", "artifact_storage")
    if OUTPUT_DIRECTORY != "operations-digest-reports":
        raise EvidenceError("unsafe_artifact_directory", "Only the fixed operations-digest-reports child directory is allowed.", "artifact_storage")
    directory = root / OUTPUT_DIRECTORY
    if directory.is_symlink() or getattr(directory, "is_junction", lambda: False)() or directory.resolve() != directory:
        raise EvidenceError("unsafe_artifact_directory", "Output directory is a symlink/junction or escapes cwd.", "artifact_storage")
    return root, directory


def sharing_fields(root, paths):
    result = {"sharing_mode": "local_files_only", "http_verified": False}
    match = re.fullmatch(
        r"/(?:root/sreagent|usr)/terminalRoot/tmp/ThreadFiles/([0-9a-fA-F-]{36})",
        root.as_posix(),
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
        "incidents_csv_path": "-incidents.csv",
        "actions_csv_path": "-actions.csv",
    }
    if set(paths) != set(suffixes):
        raise EvidenceError("unsafe_sharing_path", "Native delivery requires all four guarded report artifacts.", "artifact_storage")
    stem = paths["report_path"].name.removesuffix(".html")
    if not re.fullmatch(r"ops-digest-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12}", stem):
        raise EvidenceError("unsafe_sharing_path", "Native aliases require this tool's generated ops-digest run filenames.", "artifact_storage")
    expected = root / "operations-digest-reports"
    aliases = {}
    for key, path in paths.items():
        if path.parent != expected or path.name != stem + suffixes[key]:
            raise EvidenceError("unsafe_sharing_path", "Native aliases must reference the same run in operations-digest-reports.", "artifact_storage")
        aliases[key.removesuffix("_path") + "_url"] = (
            "/api/files/tmp/ThreadFiles/" + match[1] + "/operations-digest-reports/" + quote(path.name, safe="")
        )
    return {**result, "sharing_mode": "native_ui", **aliases}


def report_envelope(snapshot, paths, root):
    partial = any(s["status"] not in ("complete", "not_configured") for s in snapshot["sources"])
    result = {
        "status": "partial" if partial else "ok",
        "operation": "report",
        "artifact_status": "written",
        **sharing_fields(root, paths),
        "collection": collection_disclosure(snapshot),
        "counts": snapshot["counts"],
        **{key: str(path) for key, path in paths.items()},
    }
    return ensure_response(result)


def write_report(snapshot):
    root, directory = artifact_directory()
    ref_compact = snapshot["reference_utc"].replace(":", "").replace("-", "")
    prefix = "ops-digest-" + ref_compact + "-" + uuid4().hex[:12]
    paths = {
        key: directory / (prefix + suffix)
        for key, suffix in (
            ("report_path", ".html"),
            ("snapshot_path", "-snapshot.json"),
            ("incidents_csv_path", "-incidents.csv"),
            ("actions_csv_path", "-actions.csv"),
        )
    }
    response = report_envelope(snapshot, paths, root)
    snapshot_document = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    if json.loads(snapshot_document) != snapshot:
        raise EvidenceError("round_trip_failed", "Full normalized snapshot JSON did not round-trip.", "artifact_storage")
    documents = {
        "report_path": render_html(snapshot),
        "snapshot_path": snapshot_document,
        "incidents_csv_path": csv_document(
            incidents_and_anomalies_csv_rows(snapshot),
            (
                "record_kind", "id", "category", "severity", "state_or_kind", "title",
                "resource_name", "resource_group", "resource_type", "resource_id",
                "metric_or_signal", "observed_value", "baseline_or_expected", "unit",
                "observed_at_utc", "source_id", "summary", "learn_url", "details_json",
            ),
        ),
        "actions_csv_path": csv_document(
            actions_csv_rows(snapshot),
            (
                "priority_rank", "id", "horizon_label", "severity", "category", "title",
                "resource_name", "resource_group", "resource_type", "resource_id",
                "owner_scope", "effort_label", "linked_evidence_ids", "source_ids",
                "evidence_summary", "recommendation", "learn_url", "details_json",
            ),
        ),
    }
    encoded = {key: value.encode("utf-8-sig" if key.endswith("csv_path") else "utf-8") for key, value in documents.items()}
    if any(len(value) > ARTIFACT_BYTES for value in encoded.values()):
        raise EvidenceError("artifact_size_exceeded", "Complete artifacts exceed 4800000 bytes; no files were written.", "artifact_storage")
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
            raise EvidenceError("artifact_readback_failed", "Written artifact bytes differ from prepared content.", "artifact_storage")
        if json.loads(paths["snapshot_path"].read_text(encoding="utf-8")) != snapshot:
            raise EvidenceError("artifact_readback_failed", "Written snapshot JSON differs from normalized data.", "artifact_storage")
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
                "Artifact write failed and cleanup failed for: " + ", ".join(failures),
                "artifact_storage",
            ) from exc
        if isinstance(exc, EvidenceError):
            raise
        raise EvidenceError("artifact_write_failed", "Could not atomically write all four artifacts.", "artifact_storage") from exc
    return response


def main(
    operation: str = "report",
    period: str = "previous_month",
    view: str = "summary",
    category: str = "all",
    severity: str = "all",
    resource_name: str = "",
    limit: int = 25,
    offset: int = 0,
) -> dict:
    """Generate the periodic Azure Operations Digest (incidents, anomalies, and prioritized actions) or query views."""
    try:
        reference = utc_now()
        params = validate_parameters(
            operation=operation,
            period=period,
            view=view,
            category=category,
            severity=severity,
            resource_name=resource_name,
            limit=limit,
            offset=offset,
            reference_utc=reference,
        )
        config = validate_config()
        if operation == "report" and HTML_TEMPLATE.count("__REPORT_DATA_JSON__") != 1:
            raise EvidenceError("template_missing", "Use the built standalone tool with embedded HTML_TEMPLATE.", "renderer")
        raw = collect_live(config, params["window"], reference)
        snapshot = finish_snapshot(raw, params["window"], reference, provenance="LIVE")
        return query_snapshot(snapshot, params) if operation == "query" else write_report(snapshot)
    except EvidenceError as exc:
        return ensure_response({
            "status": "error",
            "error": exc.public(),
            "artifact_status": "cleanup_failed" if exc.code == "artifact_cleanup_failed" else "not_written",
            "provenance": "LIVE",
        })

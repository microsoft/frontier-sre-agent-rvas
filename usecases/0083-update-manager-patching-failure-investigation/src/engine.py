"""Read-only Azure Update Manager patching cycle and failure investigation tool. Build assets with build_tool.py before SRE paste."""

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
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, quote, unquote, urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener
from uuid import UUID, uuid4


SUBSCRIPTION_ID = "<YOUR_SUBSCRIPTION_ID>"
MANAGED_IDENTITY_CLIENT_ID = "<YOUR_MANAGED_IDENTITY_CLIENT_ID>"
CLIENT_NAME = "Customer"
# Here goes the customer's logo, privately configured as a validated PNG/JPEG
# data URI. Keep generic Git source empty. Use adjacent strings <10K per line.
CLIENT_LOGO_DATA_URI = ""
CLIENT_LOGO_ALT = "Authorized customer logo"
OUTPUT_DIRECTORY = "patching-investigation-reports"

ARM_ORIGIN = "https://management.azure.com"
ARM_TOKEN_AUDIENCES = (
    "https://management.azure.com",
    "https://management.core.windows.net",
)
ARG_API_VERSION = "2022-10-01"
ARG_PATH = "/providers/Microsoft.ResourceGraph/resources"
TRANSPORT_BYTES = 3500
ARTIFACT_BYTES = 4_800_000
HTTP_BYTES = 8_000_000
MAX_PAGES = 25
MAX_ROWS = 15000
MAX_COLLECTION_SECONDS = 240
MAX_HTTP_ATTEMPTS = 120
UTC = timezone.utc

OPERATIONS = ("report", "query")
PERIODS = ("last_30d", "last_14d", "last_7d", "last_24h")
PERIOD_HOURS = {
    "last_30d": 720,
    "last_14d": 336,
    "last_7d": 168,
    "last_24h": 24,
}
VIEWS = (
    "summary",
    "machines",
    "failures",
    "cycles",
    "patches",
    "extensions",
    "coverage",
    "actions",
)
HOSTINGS = ("all", "azure", "arc")
FAILURE_CATEGORIES = (
    "all",
    "maintenance_window_unresponsive",
    "arc_agent_expired_or_disconnected",
    "assessment_stuck_or_readiness_undetermined",
    "hotpatch_or_patch_extension_error",
    "pending_security_patches_unscheduled",
    "unassessed_no_update_manager_telemetry",
    "healthy",
)
CATEGORY_SEVERITY = {
    "maintenance_window_unresponsive": "critical",
    "arc_agent_expired_or_disconnected": "critical",
    "assessment_stuck_or_readiness_undetermined": "high",
    "hotpatch_or_patch_extension_error": "high",
    "pending_security_patches_unscheduled": "medium",
    "unassessed_no_update_manager_telemetry": "low",
    "healthy": "info",
}
CATEGORY_LABELS = {
    "maintenance_window_unresponsive": "Maintenance window unresponsive or run failed",
    "arc_agent_expired_or_disconnected": "Azure Arc agent expired or disconnected",
    "assessment_stuck_or_readiness_undetermined": "Assessment stuck in progress or patch support undetermined",
    "hotpatch_or_patch_extension_error": "Hotpatch or guest management/patch extension error",
    "pending_security_patches_unscheduled": "Pending security/rollup updates with no assigned window",
    "unassessed_no_update_manager_telemetry": "No assessment or installation telemetry in Update Manager",
    "healthy": "Patching verified, no active blockers",
}
SEVERITY_LABELS = {
    "critical": "Critical",
    "high": "High",
    "medium": "Medium",
    "low": "Low",
    "info": "Passed",
}
SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
SOURCE_IDS = (
    "arg_compute_machines",
    "arg_patch_assessments",
    "arg_software_patches_pending",
    "arg_patch_installations",
    "arg_software_patches_installed",
    "arg_maintenance_cycles",
    "arg_patch_extensions",
)

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
    def __init__(self, code, message, source="investigation", http_status=None):
        super().__init__(message)
        self.code = code
        self.source = source
        self.http_status = http_status

    def public(self):
        return {
            "code": self.code,
            "message": str(self),
            "source_id": self.source,
            "http_status": self.http_status,
        }


def utc_now():
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_utc(value, source="normalization", required=False):
    if value is None or value == "":
        if required:
            raise EvidenceError("invalid_timestamp", "Required UTC timestamp is missing.", source)
        return None
    if not isinstance(value, str) or len(value) > 64 or any(ord(c) < 32 for c in value):
        raise EvidenceError("invalid_timestamp", "Timestamp has invalid type or length.", source)
    if value.startswith("0001-01-01"):
        return None
    cleaned = value.strip()
    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1] + "+00:00"
    if "." in cleaned:
        head, tail = cleaned.split(".", 1)
        tz_pos = max(tail.find("+"), tail.find("-"))
        if tz_pos != -1:
            frac, tz_part = tail[:tz_pos], tail[tz_pos:]
        else:
            frac, tz_part = tail, ""
        cleaned = head + "." + frac[:6].ljust(6, "0") + tz_part
    try:
        dt = datetime.fromisoformat(cleaned)
    except ValueError as exc:
        raise EvidenceError("invalid_timestamp", "Malformed ISO-8601 timestamp in source payload.", source) from exc
    if dt.tzinfo is None or dt.utcoffset() is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def format_utc(dt):
    if dt is None:
        return None
    return dt.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def plural(count, one, many):
    return format(count, ",") + " " + (one if count == 1 else many)


def obj(value, source="normalization"):
    if not isinstance(value, dict):
        raise EvidenceError("invalid_shape", "Expected an object in source payload.", source)
    return value


def pick(value, *keys):
    cur = value
    for key in keys:
        if not isinstance(cur, dict) or key not in cur:
            return None
        cur = cur[key]
    return cur


def text(value, source="normalization", maximum=8192):
    if value is None:
        return None
    if not isinstance(value, str):
        value = str(value)
    cleaned = value.replace("\r", " ").replace("\n", " ").strip()
    if len(cleaned) > maximum or any(ord(c) < 32 for c in cleaned):
        raise EvidenceError("invalid_field", "Source text exceeds maximum length or contains control characters.", source)
    return cleaned


def integer(value, source="normalization", default=0):
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise EvidenceError("invalid_field", "Source numeric field is not finite.", source)
    return int(value)


def boolean(value, source="normalization"):
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.lower() in ("true", "false"):
        return value.lower() == "true"
    raise EvidenceError("invalid_field", "Source boolean field has invalid type.", source)


def tags_map(value, source="normalization"):
    if value is None:
        return {}
    result = {}
    for k, v in obj(value, source).items():
        key = text(str(k), source, 256)
        if not key:
            continue
        if any(word in key.lower() for word in ("secret", "password", "token", "key", "sas", "credential", "connectionstring")):
            continue
        if isinstance(v, (str, int, float, bool)) or v is None:
            result[key] = text(str(v), source, 512) if v is not None else None
    return result


def guid(value, field):
    try:
        if not isinstance(value, str) or str(UUID(value)) != value.lower() or UUID(value).int == 0:
            raise ValueError
    except (ValueError, AttributeError) as exc:
        raise EvidenceError("configuration_required", "Configure " + field + " with a valid non-zero GUID.", "configuration") from exc
    return value.lower()


def validate_logo(uri, alt=CLIENT_LOGO_ALT):
    if uri == "":
        return
    if not isinstance(uri, str) or len(uri) > 140000:
        raise EvidenceError("invalid_logo", "Optional logo must be a bounded inline PNG/JPEG data URI.", "branding")
    match = re.fullmatch(r"data:image/(png|jpeg);base64,([A-Za-z0-9+/=]+)", uri)
    if not match:
        raise EvidenceError("invalid_logo", "Only inline PNG/JPEG MIME with canonical base64 is allowed.", "branding")
    try:
        data = base64.b64decode(match[2], validate=True)
    except binascii.Error as exc:
        raise EvidenceError("invalid_logo", "Invalid logo base64.", "branding") from exc
    if base64.b64encode(data).decode("ascii") != match[2] or not 1 <= len(data) <= 100000:
        raise EvidenceError("invalid_logo", "Optional raster logo must contain 1..100000 canonical base64 bytes.", "branding")
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
                    or not 1 <= width <= 2048
                    or not 1 <= height <= 2048
                    or getattr(image, "n_frames", 1) != 1
                ):
                    raise EvidenceError("invalid_logo", "Use one PNG/JPEG frame, matching MIME, at most 2048x2048 px.", "branding")
                image.verify()
            with Image.open(io.BytesIO(data), formats=["PNG", "JPEG"]) as image:
                image.load()
    except (OSError, ValueError, SyntaxError, UnidentifiedImageError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise EvidenceError("invalid_logo", "Logo bytes failed complete raster decode.", "branding") from exc


def validate_config():
    if not isinstance(CLIENT_NAME, str) or not CLIENT_NAME.strip() or len(CLIENT_NAME) > 120 or re.search(r"[\x00-\x1f\x7f]", CLIENT_NAME):
        raise EvidenceError("invalid_configuration", "CLIENT_NAME must be 1..120 plain characters.", "configuration")
    validate_logo(CLIENT_LOGO_DATA_URI, CLIENT_LOGO_ALT)
    subscription_id = guid(SUBSCRIPTION_ID, "SUBSCRIPTION_ID")
    client_id = guid(MANAGED_IDENTITY_CLIENT_ID, "MANAGED_IDENTITY_CLIENT_ID")
    return {
        "subscription_id": subscription_id,
        "client_id": client_id,
        "client_name": CLIENT_NAME.strip(),
        "logo_data_uri": CLIENT_LOGO_DATA_URI,
        "logo_alt": CLIENT_LOGO_ALT.strip(),
    }


def validate_parameters(
    operation="report",
    period="last_30d",
    view="summary",
    hosting="all",
    failure_category="all",
    machine_name="",
    limit=25,
    offset=0,
):
    for field, value, allowed in (
        ("operation", operation, OPERATIONS),
        ("period", period, PERIODS),
        ("view", view, VIEWS),
        ("hosting", hosting, HOSTINGS),
        ("failure_category", failure_category, FAILURE_CATEGORIES),
    ):
        if not isinstance(value, str) or value not in allowed:
            raise EvidenceError("invalid_parameter", "Invalid value for " + field + ".", "parameters")
    if not isinstance(machine_name, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{0,128}", machine_name):
        raise EvidenceError("invalid_parameter", "machine_name must match ^[A-Za-z0-9_.-]{0,128}$.", "parameters")
    if type(limit) is not int or not 1 <= limit <= 100:
        raise EvidenceError("invalid_parameter", "limit must be an integer between 1 and 100.", "parameters")
    if type(offset) is not int or not 0 <= offset <= 500000:
        raise EvidenceError("invalid_parameter", "offset must be an integer between 0 and 500000.", "parameters")
    if operation == "report" and (
        view != "summary"
        or hosting != "all"
        or failure_category != "all"
        or machine_name != ""
        or limit != 25
        or offset != 0
    ):
        raise EvidenceError("invalid_parameter", "operation='report' requires default query/filter/paging arguments.", "parameters")
    return {
        "operation": operation,
        "period": period,
        "view": view,
        "hosting": hosting,
        "failure_category": failure_category,
        "machine_name": machine_name,
        "limit": limit,
        "offset": offset,
    }


def window_for(period, reference_utc):
    end_dt = parse_utc(reference_utc, "window", required=True)
    hours = PERIOD_HOURS[period]
    start_dt = end_dt - timedelta(hours=hours)
    return {
        "period": period,
        "hours": hours,
        "start_utc": format_utc(start_dt),
        "end_utc": format_utc(end_dt),
    }


def arg_queries():
    return {
        "arg_compute_machines": (
            "resources "
            "| where type in~ ('microsoft.compute/virtualmachines', 'microsoft.hybridcompute/machines') "
            "| project id, name, type, resourceGroup, location, tags, properties"
        ),
        "arg_patch_assessments": (
            "patchassessmentresources "
            "| where type !endswith '/softwarepatches' "
            "| project id, name, type, resourceGroup, location, properties"
        ),
        "arg_software_patches_pending": (
            "patchassessmentresources "
            "| where type endswith '/softwarepatches' "
            "| project id, name, type, resourceGroup, location, properties"
        ),
        "arg_patch_installations": (
            "patchinstallationresources "
            "| where type !endswith '/softwarepatches' "
            "| project id, name, type, resourceGroup, location, properties"
        ),
        "arg_software_patches_installed": (
            "patchinstallationresources "
            "| where type endswith '/softwarepatches' "
            "| project id, name, type, resourceGroup, location, properties"
        ),
        "arg_maintenance_cycles": (
            "maintenanceresources "
            "| project id, name, type, resourceGroup, location, properties"
        ),
        "arg_patch_extensions": (
            "resources "
            "| where type in~ ('microsoft.compute/virtualmachines/extensions', 'microsoft.hybridcompute/machines/extensions') "
            "| project id, name, type, resourceGroup, location, "
            "properties=bag_pack("
            "'publisher', properties.publisher, "
            "'type', properties.type, "
            "'typeHandlerVersion', properties.typeHandlerVersion, "
            "'provisioningState', properties.provisioningState, "
            "'autoUpgradeMinorVersion', properties.autoUpgradeMinorVersion, "
            "'enableAutomaticUpgrade', properties.enableAutomaticUpgrade)"
        ),
    }


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise HTTPError(req.full_url, code, "Redirects are disabled for read-only ARG transport.", headers, fp)


class Identity:
    def __init__(self, config):
        try:
            from azure.core.exceptions import ClientAuthenticationError, ServiceRequestError
            from azure.identity import CredentialUnavailableError, ManagedIdentityCredential
        except ImportError as exc:
            raise EvidenceError("dependency_missing", "azure-identity is required for ManagedIdentityCredential.", "identity") from exc
        self.config = config
        self.auth_errors = (CredentialUnavailableError, ClientAuthenticationError, ServiceRequestError)
        self.credential = ManagedIdentityCredential(client_id=config["client_id"])
        self._cached_token = None
        self._expires_on = 0

    def close(self):
        try:
            self.credential.close()
        except Exception:
            pass

    def arm_token(self):
        now = time.time()
        if self._cached_token and self._expires_on > now + 60:
            return self._cached_token
        try:
            token_obj = self.credential.get_token(ARM_ORIGIN + "/.default")
        except self.auth_errors as exc:
            raise EvidenceError("authentication_failed", "ManagedIdentityCredential failed to acquire ARM token.", "identity") from exc
        raw_token = getattr(token_obj, "token", None)
        if not isinstance(raw_token, str) or not raw_token.strip():
            raise EvidenceError("authentication_failed", "ManagedIdentityCredential returned an empty ARM token.", "identity")
        parts = raw_token.split(".")
        if len(parts) >= 2:
            try:
                padded = parts[1] + "=" * (-len(parts[1]) % 4)
                claims = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
                claims = normalize_sidecar_claims(claims)
            except Exception as exc:
                raise EvidenceError("authentication_failed", "ARM JWT payload could not be decoded for claim verification.", "identity") from exc
            app_claim = (claims.get("appid") or claims.get("azp") or "").lower()
            if app_claim and app_claim != self.config["client_id"]:
                raise EvidenceError("identity_mismatch", "Token client_id claim does not match MANAGED_IDENTITY_CLIENT_ID.", "identity")
            aud_claim = (claims.get("aud") or "").rstrip("/").lower()
            if aud_claim and aud_claim not in ARM_TOKEN_AUDIENCES:
                raise EvidenceError("identity_mismatch", "Token audience is not Azure Resource Manager.", "identity")
        self._cached_token = raw_token
        self._expires_on = getattr(token_obj, "expires_on", now + 300)
        return raw_token


class ArgReader:
    def __init__(self, identity, config, deadline=None):
        self.identity = identity
        self.config = config
        self.deadline = deadline
        self.attempts = 0
        context = ssl.create_default_context()
        self.opener = build_opener(NoRedirect(), HTTPSHandler(context=context))
        self.allowed_queries = set(arg_queries().values())

    def query_table(self, source_id, query_text, reference_utc):
        url = ARM_ORIGIN + ARG_PATH + "?api-version=" + ARG_API_VERSION
        receipt = {
            "id": source_id,
            "source_id": source_id,
            "endpoint": "POST " + url,
            "subscription_id": self.config["subscription_id"],
            "status": "complete",
            "pages": 0,
            "records": 0,
            "observed_at": reference_utc,
            "note": "Read-only Azure Resource Graph query (" + source_id + ").",
            "errors": [],
        }
        rows = []
        skip_token = None
        seen_tokens = set()
        try:
            for page_idx in range(1, MAX_PAGES + 1):
                if self.deadline is not None and time.monotonic() >= self.deadline:
                    raise EvidenceError("collection_deadline", "Collection time budget exceeded during " + source_id + ".", source_id)
                options = {"$top": 1000, "resultFormat": "objectArray"}
                if skip_token is not None:
                    options["$skipToken"] = skip_token
                body = {
                    "subscriptions": [self.config["subscription_id"]],
                    "query": query_text,
                    "options": options,
                }
                payload = self._post_arg(url, body, source_id)
                receipt["pages"] = page_idx
                data = payload.get("data")
                if not isinstance(data, list) or any(not isinstance(item, dict) for item in data):
                    raise EvidenceError("invalid_response", "ARG data field must be an objectArray list.", source_id)
                rows.extend(data)
                receipt["records"] = len(rows)
                if len(rows) > MAX_ROWS:
                    raise EvidenceError("row_bound_exceeded", "ARG query exceeded MAX_ROWS=" + str(MAX_ROWS) + ".", source_id)
                next_token = payload.get("$skipToken")
                if next_token is None:
                    break
                if not isinstance(next_token, str) or not next_token or len(next_token) > 8192 or next_token in seen_tokens:
                    raise EvidenceError("pagination_loop", "Invalid or repeated ARG $skipToken.", source_id)
                seen_tokens.add(next_token)
                skip_token = next_token
            else:
                raise EvidenceError("page_bound_exceeded", "ARG pagination exceeded MAX_PAGES=" + str(MAX_PAGES) + ".", source_id)
        except EvidenceError as exc:
            receipt["status"] = "partial" if rows else ("denied" if exc.http_status in (401, 403) else "error")
            receipt["errors"].append(exc.public())
        return rows, receipt

    def _post_arg(self, url, body, source_id):
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or parsed.netloc.lower() != "management.azure.com"
            or unquote(parsed.path) != ARG_PATH
            or parse_qsl(parsed.query) != [("api-version", ARG_API_VERSION)]
            or not isinstance(body, dict)
            or body.get("subscriptions") != [self.config["subscription_id"]]
            or body.get("query") not in self.allowed_queries
        ):
            raise EvidenceError("unsafe_endpoint", "Only fixed read-only Azure Resource Graph queries are permitted.", source_id)
        encoded_body = json.dumps(body, separators=(",", ":"), allow_nan=False).encode("utf-8")
        headers = {
            "Authorization": "Bearer " + self.identity.arm_token(),
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        for attempt in range(3):
            self.attempts += 1
            if self.attempts > MAX_HTTP_ATTEMPTS:
                raise EvidenceError("http_attempt_bound", "Exceeded MAX_HTTP_ATTEMPTS.", source_id)
            req = Request(url, data=encoded_body, headers=headers, method="POST")
            try:
                with self.opener.open(req, timeout=30) as resp:
                    status = getattr(resp, "status", 200)
                    raw_bytes = resp.read(HTTP_BYTES + 1)
                    if len(raw_bytes) > HTTP_BYTES:
                        raise EvidenceError("response_too_large", "ARG response exceeded HTTP_BYTES bound.", source_id)
                    if status != 200:
                        raise EvidenceError("http_error", "ARG returned HTTP " + str(status) + ".", source_id, status)
                    decoded = json.loads(raw_bytes.decode("utf-8"))
                    if not isinstance(decoded, dict):
                        raise EvidenceError("invalid_response", "ARG response root must be a JSON object.", source_id)
                    return decoded
            except HTTPError as exc:
                if exc.code in (429, 500, 502, 503, 504) and attempt < 2:
                    time.sleep(attempt + 1)
                    continue
                raise EvidenceError(
                    "access_denied" if exc.code in (401, 403) else "http_error",
                    "ARG request failed with HTTP " + str(exc.code) + ".",
                    source_id,
                    exc.code,
                ) from exc
            except URLError as exc:
                if attempt < 2:
                    time.sleep(attempt + 1)
                    continue
                raise EvidenceError("network_error", "ARG transport failed to reach management.azure.com.", source_id) from exc
            except (UnicodeDecodeError, ValueError) as exc:
                raise EvidenceError("invalid_response", "ARG returned malformed JSON.", source_id) from exc
        raise EvidenceError("http_error", "ARG retries exhausted.", source_id)


def parent_machine_id(resource_id, source="normalization"):
    rid = text(resource_id, source, 2048)
    if not rid:
        raise EvidenceError("invalid_resource_id", "Empty resource ID.", source)
    low = rid.lower()
    for marker in (
        "/patchassessmentresults/",
        "/patchinstallationresults/",
        "/providers/microsoft.maintenance/",
        "/extensions/",
    ):
        pos = low.find(marker)
        if pos != -1:
            return low[:pos]
    return low.rstrip("/")


def machine_name_from_id(machine_id):
    if not isinstance(machine_id, str) or "/" not in machine_id:
        return ""
    return machine_id.rstrip("/").split("/")[-1]


def normalize_machine(row, subscription_id, reference_utc):
    source = "arg_compute_machines"
    rid = text(row.get("id"), source, 2048)
    if not rid or not rid.lower().startswith("/subscriptions/" + subscription_id.lower() + "/"):
        raise EvidenceError("scope_mismatch", "Machine resource ID is outside the configured subscription.", source)
    rtype = (text(row.get("type"), source, 128) or "").lower()
    if rtype not in ("microsoft.compute/virtualmachines", "microsoft.hybridcompute/machines"):
        raise EvidenceError("invalid_type", "Unexpected compute resource type: " + rtype, source)
    hosting = "arc" if rtype == "microsoft.hybridcompute/machines" else "azure"
    name = text(row.get("name"), source, 256) or machine_name_from_id(rid)
    rg = text(row.get("resourceGroup"), source, 128) or ""
    location = text(row.get("location"), source, 128) or ""
    props = obj(row.get("properties") or {}, source)
    tags = tags_map(row.get("tags"), source)

    os_profile = props.get("osProfile") if isinstance(props.get("osProfile"), dict) else {}
    win_conf = os_profile.get("windowsConfiguration") if isinstance(os_profile.get("windowsConfiguration"), dict) else {}
    lin_conf = os_profile.get("linuxConfiguration") if isinstance(os_profile.get("linuxConfiguration"), dict) else {}
    patch_settings = (
        win_conf.get("patchSettings")
        if isinstance(win_conf.get("patchSettings"), dict)
        else (lin_conf.get("patchSettings") if isinstance(lin_conf.get("patchSettings"), dict) else {})
    )
    os_disk = pick(props, "storageProfile", "osDisk")
    os_disk = os_disk if isinstance(os_disk, dict) else {}
    ext_view = pick(props, "extended", "instanceView")
    ext_view = ext_view if isinstance(ext_view, dict) else {}
    power_obj = ext_view.get("powerState") if isinstance(ext_view.get("powerState"), dict) else {}

    os_type_raw = props.get("osType") or os_disk.get("osType") or (
        "Windows" if win_conf else ("Linux" if lin_conf else None)
    )
    os_type = text(os_type_raw, source, 64)
    if os_type:
        os_type = "Windows" if os_type.lower().startswith("win") else ("Linux" if os_type.lower().startswith("lin") else os_type)
    os_name = text(props.get("osName") or ext_view.get("osName") or props.get("osSku"), source, 256)
    os_version = text(props.get("osVersion") or ext_view.get("osVersion"), source, 128)
    patch_mode = text(
        patch_settings.get("patchMode") or pick(props, "osProfile", "windowsConfiguration", "patchSettings", "patchMode") or pick(props, "osProfile", "linuxConfiguration", "patchSettings", "patchMode"),
        source,
        128,
    )
    assessment_mode = text(
        patch_settings.get("assessmentMode") or pick(props, "osProfile", "windowsConfiguration", "patchSettings", "assessmentMode") or pick(props, "osProfile", "linuxConfiguration", "patchSettings", "assessmentMode"),
        source,
        128,
    )
    power_state = text(power_obj.get("code") or props.get("powerState"), source, 128)
    arc_status = text(props.get("status"), source, 64) if hosting == "arc" else None
    last_status_change = format_utc(parse_utc(props.get("lastStatusChange"), source))
    agent_version = text(props.get("agentVersion"), source, 128)
    vm_id = text(props.get("vmId"), source, 128)
    provisioning_state = text(props.get("provisioningState"), source, 64)

    return {
        "id": rid.lower(),
        "resource_id": rid,
        "name": name,
        "type": rtype,
        "hosting": hosting,
        "resource_group": rg,
        "location": location,
        "os_type": os_type or "Unknown",
        "os_name": os_name or (os_type or "Unknown"),
        "os_version": os_version,
        "patch_mode": patch_mode,
        "assessment_mode": assessment_mode,
        "power_state": power_state,
        "arc_status": arc_status,
        "last_status_change_utc": last_status_change,
        "agent_version": agent_version,
        "vm_id": vm_id,
        "provisioning_state": provisioning_state,
        "tags": tags,
        "observed_at": reference_utc,
    }


def extract_log_path(message):
    if not isinstance(message, str):
        return None
    match = re.search(r"\[([A-Za-z]:\\[^\]]+|/[A-Za-z0-9_./-]+)\]", message)
    if match:
        return match.group(1)
    return None


def normalize_assessment(row, subscription_id, reference_utc):
    source = "arg_patch_assessments"
    rid = text(row.get("id"), source, 2048)
    if not rid or not rid.lower().startswith("/subscriptions/" + subscription_id.lower() + "/"):
        raise EvidenceError("scope_mismatch", "Assessment resource ID is outside the configured subscription.", source)
    machine_id = parent_machine_id(rid, source)
    props = obj(row.get("properties") or {}, source)
    counts = props.get("availablePatchCountByClassification")
    counts = counts if isinstance(counts, dict) else {}
    conf = props.get("configurationStatus")
    conf = conf if isinstance(conf, dict) else {}
    assess_conf = conf.get("assessmentModeConfiguration") if isinstance(conf.get("assessmentModeConfiguration"), dict) else {}
    patch_conf = conf.get("patchModeConfiguration") if isinstance(conf.get("patchModeConfiguration"), dict) else {}
    readiness_conf = conf.get("vmGuestPatchReadiness") if isinstance(conf.get("vmGuestPatchReadiness"), dict) else {}
    err = props.get("errorDetails") if isinstance(props.get("errorDetails"), dict) else {}
    hotpatch = props.get("hotpatchStatus") if isinstance(props.get("hotpatchStatus"), dict) else None

    hotpatch_err = (hotpatch or {}).get("error") if isinstance((hotpatch or {}).get("error"), dict) else {}
    hotpatch_details = hotpatch_err.get("details") if isinstance(hotpatch_err.get("details"), list) else []
    hotpatch_detail_codes = [
        text(item.get("code"), source, 256)
        for item in hotpatch_details
        if isinstance(item, dict) and item.get("code")
    ]
    hotpatch_detail_msgs = [
        text(item.get("message"), source, 1024)
        for item in hotpatch_details
        if isinstance(item, dict) and item.get("message")
    ]
    hotpatch_msg = text(hotpatch_err.get("message"), source, 2048)
    hotpatch_log_path = extract_log_path(hotpatch_msg or "")

    sec_count = integer(counts.get("security"), source, 0)
    crit_count = integer(counts.get("critical"), source, 0)
    rollup_count = integer(counts.get("updateRollup"), source, 0)
    def_count = integer(counts.get("definition"), source, 0)
    upd_count = integer(counts.get("updates"), source, 0)
    fp_count = integer(counts.get("featurePack"), source, 0)
    sp_count = integer(counts.get("servicePack"), source, 0)
    tools_count = integer(counts.get("tools"), source, 0)
    other_count = integer(counts.get("other"), source, 0)

    return {
        "id": rid.lower(),
        "resource_id": rid,
        "machine_id": machine_id,
        "machine_name": machine_name_from_id(machine_id),
        "assessment_activity_id": text(props.get("assessmentActivityId") or row.get("name"), source, 128),
        "status": text(props.get("status"), source, 64) or "Unknown",
        "reboot_pending": boolean(props.get("rebootPending"), source),
        "start_utc": format_utc(parse_utc(props.get("startDateTime"), source)),
        "last_modified_utc": format_utc(parse_utc(props.get("lastModifiedDateTime"), source)),
        "os_type": text(props.get("osType"), source, 64),
        "counts": {
            "security": sec_count,
            "critical": crit_count,
            "update_rollup": rollup_count,
            "definition": def_count,
            "updates": upd_count,
            "feature_pack": fp_count,
            "service_pack": sp_count,
            "tools": tools_count,
            "other": other_count,
            "security_or_critical": sec_count + crit_count,
            "actionable_non_definition": sec_count + crit_count + rollup_count + upd_count + fp_count + sp_count,
            "total": sec_count + crit_count + rollup_count + def_count + upd_count + fp_count + sp_count + tools_count + other_count,
        },
        "configuration_status": {
            "assessment_mode_status": text(assess_conf.get("status"), source, 64),
            "patch_mode_status": text(patch_conf.get("status"), source, 64),
            "vm_guest_patch_readiness": text(readiness_conf.get("detectedVMGuestPatchSupportState"), source, 64),
            "last_modified_utc": format_utc(parse_utc(conf.get("lastModifiedDateTime") or conf.get("lastModifiedTime"), source)),
        },
        "error_code": text(err.get("code"), source, 128),
        "error_message": text(err.get("message"), source, 2048),
        "hotpatch": None if hotpatch is None else {
            "enablement_status": text(hotpatch.get("hotpatchEnablementStatus"), source, 64),
            "readiness_status": text(hotpatch.get("hotpatchReadinessStatus"), source, 64),
            "last_refreshed_utc": format_utc(parse_utc(hotpatch.get("lastRefreshedTime"), source)),
            "error_code": text(hotpatch_err.get("code"), source, 128),
            "detail_codes": hotpatch_detail_codes,
            "detail_messages": hotpatch_detail_msgs,
            "error_message": hotpatch_msg,
            "log_path": hotpatch_log_path,
        },
        "observed_at": reference_utc,
    }


def normalize_pending_patch(row, subscription_id, reference_utc):
    source = "arg_software_patches_pending"
    rid = text(row.get("id"), source, 2048)
    if not rid or not rid.lower().startswith("/subscriptions/" + subscription_id.lower() + "/"):
        raise EvidenceError("scope_mismatch", "Pending software patch ID is outside the configured subscription.", source)
    machine_id = parent_machine_id(rid, source)
    props = obj(row.get("properties") or {}, source)
    raw_class = props.get("classifications")
    classifications = [
        text(item, source, 64)
        for item in (raw_class if isinstance(raw_class, list) else [])
        if item is not None
    ]
    primary_class = classifications[0] if classifications else "Other"
    return {
        "id": rid.lower(),
        "resource_id": rid,
        "record_kind": "pending_assessment_patch",
        "machine_id": machine_id,
        "machine_name": machine_name_from_id(machine_id),
        "patch_id": text(props.get("patchId") or row.get("name"), source, 256),
        "patch_name": text(props.get("patchName") or row.get("name"), source, 512) or "UnknownPatch",
        "kb_id": text(props.get("kbId"), source, 64) or "",
        "version": text(props.get("version"), source, 128) or "",
        "classifications": classifications,
        "primary_classification": primary_class,
        "msrc_severity": text(props.get("msrcSeverity"), source, 64) or "Unspecified",
        "reboot_behavior": text(props.get("rebootBehavior"), source, 64) or "Unknown",
        "installation_state": "PendingAssessment",
        "published_utc": format_utc(parse_utc(props.get("publishedDateTime"), source)),
        "last_modified_utc": format_utc(parse_utc(props.get("lastModifiedDateTime"), source)),
        "observed_at": reference_utc,
    }


def normalize_installation(row, subscription_id, reference_utc):
    source = "arg_patch_installations"
    rid = text(row.get("id"), source, 2048)
    if not rid or not rid.lower().startswith("/subscriptions/" + subscription_id.lower() + "/"):
        raise EvidenceError("scope_mismatch", "Patch installation ID is outside the configured subscription.", source)
    machine_id = parent_machine_id(rid, source)
    props = obj(row.get("properties") or {}, source)
    err = props.get("errorDetails") if isinstance(props.get("errorDetails"), dict) else {}
    return {
        "id": rid.lower(),
        "resource_id": rid,
        "run_id": text(row.get("name") or props.get("installationActivityId"), source, 128),
        "machine_id": machine_id,
        "machine_name": machine_name_from_id(machine_id),
        "status": text(props.get("status"), source, 64) or "Unknown",
        "start_utc": format_utc(parse_utc(props.get("startDateTime"), source)),
        "last_modified_utc": format_utc(parse_utc(props.get("lastModifiedDateTime"), source)),
        "installed_patch_count": integer(props.get("installedPatchCount"), source, 0),
        "failed_patch_count": integer(props.get("failedPatchCount"), source, 0),
        "pending_patch_count": integer(props.get("pendingPatchCount"), source, 0),
        "not_selected_patch_count": integer(props.get("notSelectedPatchCount"), source, 0),
        "excluded_patch_count": integer(props.get("excludedPatchCount"), source, 0),
        "maintenance_window_exceeded": bool(boolean(props.get("maintenanceWindowExceeded"), source)),
        "reboot_status": text(props.get("rebootStatus"), source, 64) or "Unknown",
        "maintenance_run_id": text(props.get("maintenanceRunId"), source, 2048),
        "started_by": text(props.get("startedBy"), source, 128),
        "os_type": text(props.get("osType"), source, 64),
        "error_code": text(err.get("code"), source, 128),
        "error_message": text(err.get("message"), source, 2048),
        "observed_at": reference_utc,
    }


def normalize_installed_patch(row, subscription_id, reference_utc):
    source = "arg_software_patches_installed"
    rid = text(row.get("id"), source, 2048)
    if not rid or not rid.lower().startswith("/subscriptions/" + subscription_id.lower() + "/"):
        raise EvidenceError("scope_mismatch", "Installed software patch ID is outside the configured subscription.", source)
    machine_id = parent_machine_id(rid, source)
    parts = rid.split("/")
    install_run_id = ""
    for idx, part in enumerate(parts):
        if part.lower() == "patchinstallationresults" and idx + 1 < len(parts):
            install_run_id = parts[idx + 1]
            break
    props = obj(row.get("properties") or {}, source)
    raw_class = props.get("classifications")
    classifications = [
        text(item, source, 64)
        for item in (raw_class if isinstance(raw_class, list) else [])
        if item is not None
    ]
    primary_class = classifications[0] if classifications else "Other"
    return {
        "id": rid.lower(),
        "resource_id": rid,
        "record_kind": "installation_run_patch",
        "installation_run_id": install_run_id,
        "machine_id": machine_id,
        "machine_name": machine_name_from_id(machine_id),
        "patch_id": text(props.get("patchId") or row.get("name"), source, 256),
        "patch_name": text(props.get("patchName") or row.get("name"), source, 512) or "UnknownPatch",
        "kb_id": text(props.get("kbId"), source, 64) or "",
        "version": text(props.get("version"), source, 128) or "",
        "classifications": classifications,
        "primary_classification": primary_class,
        "installation_state": text(props.get("installationState"), source, 64) or "Unknown",
        "reboot_behavior": text(props.get("rebootBehavior"), source, 64) or "Unknown",
        "reboot_required": boolean(props.get("rebootRequired"), source),
        "published_utc": format_utc(parse_utc(props.get("publishedDateTime"), source)),
        "last_modified_utc": format_utc(parse_utc(props.get("lastModifiedDateTime"), source)),
        "observed_at": reference_utc,
    }


def normalize_maintenance_row(row, subscription_id, reference_utc):
    source = "arg_maintenance_cycles"
    rid = text(row.get("id"), source, 2048)
    if not rid or not rid.lower().startswith("/subscriptions/" + subscription_id.lower() + "/"):
        raise EvidenceError("scope_mismatch", "Maintenance resource ID is outside the configured subscription.", source)
    rtype = (text(row.get("type"), source, 128) or "").lower()
    props = obj(row.get("properties") or {}, source)
    target_resource_id = text(props.get("resourceId"), source, 2048)
    machine_id = (target_resource_id or parent_machine_id(rid, source)).lower()
    if "/providers/microsoft.maintenance/" in machine_id:
        machine_id = ""
    maint_conf_id = text(props.get("maintenanceConfigurationId"), source, 2048)
    maint_conf_name = machine_name_from_id(maint_conf_id) if maint_conf_id else ""
    start_utc = format_utc(parse_utc(props.get("startDateTime"), source))
    end_utc = format_utc(parse_utc(props.get("endDateTime"), source))
    status = text(props.get("status"), source, 64) or ("Assigned" if rtype.endswith("configurationassignments") else "Unknown")
    correlation_id = text(props.get("correlationId"), source, 2048)
    error_message = text(props.get("errorMessage"), source, 2048)

    maint_conf_obj = props.get("maintenanceConfiguration") if isinstance(props.get("maintenanceConfiguration"), dict) else {}
    maint_win_obj = pick(maint_conf_obj, "properties", "maintenanceWindow")
    maint_win_obj = maint_win_obj if isinstance(maint_win_obj, dict) else {}
    conf_tags = tags_map(maint_conf_obj.get("tags"), source)

    return {
        "id": rid.lower(),
        "resource_id": rid,
        "name": text(row.get("name"), source, 256),
        "type": rtype,
        "resource_group": text(row.get("resourceGroup"), source, 128) or "",
        "location": text(row.get("location"), source, 128) or "",
        "machine_id": machine_id,
        "machine_name": machine_name_from_id(machine_id) if machine_id else "",
        "status": status,
        "correlation_id": correlation_id,
        "maintenance_configuration_id": maint_conf_id,
        "maintenance_configuration_name": maint_conf_name,
        "maintenance_scope": text(props.get("maintenanceScope") or pick(maint_conf_obj, "properties", "maintenanceScope"), source, 64),
        "start_utc": start_utc,
        "end_utc": end_utc,
        "error_message": error_message,
        "schedule_recur_every": text(maint_win_obj.get("recurEvery"), source, 128),
        "schedule_duration": text(maint_win_obj.get("duration"), source, 64),
        "schedule_time_zone": text(maint_win_obj.get("timeZone"), source, 128),
        "configuration_tags": conf_tags,
        "observed_at": reference_utc,
    }


def normalize_extension(row, subscription_id, reference_utc):
    source = "arg_patch_extensions"
    rid = text(row.get("id"), source, 2048)
    if not rid or not rid.lower().startswith("/subscriptions/" + subscription_id.lower() + "/"):
        raise EvidenceError("scope_mismatch", "Extension resource ID is outside the configured subscription.", source)
    rtype = (text(row.get("type"), source, 128) or "").lower()
    if rtype not in ("microsoft.compute/virtualmachines/extensions", "microsoft.hybridcompute/machines/extensions"):
        raise EvidenceError("invalid_type", "Unexpected extension resource type: " + rtype, source)
    machine_id = parent_machine_id(rid, source)
    props = obj(row.get("properties") or {}, source)
    if "settings" in props or "protectedSettings" in props:
        raise EvidenceError("sensitive_extension_settings_forbidden", "Extension settings and protectedSettings must never be read or retained.", source)
    publisher = text(props.get("publisher"), source, 256) or ""
    ext_type = text(props.get("type"), source, 256) or text(row.get("name"), source, 256) or ""
    is_patch_ext = any(
        token in (publisher + "." + ext_type).lower()
        for token in ("patch", "omsagent", "changetracking", "guestconfiguration")
    )
    return {
        "id": rid.lower(),
        "resource_id": rid,
        "name": text(row.get("name"), source, 256) or ext_type,
        "type": rtype,
        "hosting": "arc" if rtype.startswith("microsoft.hybridcompute/") else "azure",
        "machine_id": machine_id,
        "machine_name": machine_name_from_id(machine_id),
        "resource_group": text(row.get("resourceGroup"), source, 128) or "",
        "location": text(row.get("location"), source, 128) or "",
        "publisher": publisher,
        "extension_type": ext_type,
        "type_handler_version": text(props.get("typeHandlerVersion"), source, 64),
        "provisioning_state": text(props.get("provisioningState"), source, 64) or "Unknown",
        "auto_upgrade_minor_version": boolean(props.get("autoUpgradeMinorVersion"), source),
        "enable_automatic_upgrade": boolean(props.get("enableAutomaticUpgrade"), source),
        "is_patch_related": is_patch_ext,
        "observed_at": reference_utc,
    }


def in_window(timestamp_utc, win_start_dt, win_end_dt):
    dt = parse_utc(timestamp_utc)
    if dt is None:
        return True
    return win_start_dt <= dt <= win_end_dt


def investigate_machines(raw, window, reference_utc):
    win_start_dt = parse_utc(window["start_utc"], "window", required=True)
    win_end_dt = parse_utc(window["end_utc"], "window", required=True)

    machines_by_id = {m["id"]: dict(m) for m in raw["machines"]}
    assessments_by_machine = {}
    for ass in raw["assessments"]:
        prev = assessments_by_machine.get(ass["machine_id"])
        if prev is None or (ass.get("last_modified_utc") or "") >= (prev.get("last_modified_utc") or ""):
            assessments_by_machine[ass["machine_id"]] = ass

    pending_by_machine = {mid: [] for mid in machines_by_id}
    for patch in raw["software_patches_pending"]:
        pending_by_machine.setdefault(patch["machine_id"], []).append(patch)

    installs_by_machine = {mid: [] for mid in machines_by_id}
    window_installations = []
    for inst in raw["installations"]:
        if in_window(inst.get("start_utc") or inst.get("last_modified_utc"), win_start_dt, win_end_dt):
            window_installations.append(inst)
            installs_by_machine.setdefault(inst["machine_id"], []).append(inst)

    installed_patches_by_machine = {mid: [] for mid in machines_by_id}
    window_installed_patches = []
    for sp in raw["software_patches_installed"]:
        if in_window(sp.get("last_modified_utc"), win_start_dt, win_end_dt):
            window_installed_patches.append(sp)
            installed_patches_by_machine.setdefault(sp["machine_id"], []).append(sp)

    cycles_by_machine = {mid: [] for mid in machines_by_id}
    assignments_by_machine = {mid: [] for mid in machines_by_id}
    config_Catalog_runs = []
    window_cycles = []
    for mrow in raw["maintenance_cycles"]:
        if mrow["type"] == "microsoft.maintenance/configurationassignments":
            if mrow["machine_id"]:
                assignments_by_machine.setdefault(mrow["machine_id"], []).append(mrow)
            window_cycles.append(mrow)
        elif mrow["type"] == "microsoft.maintenance/maintenanceconfigurations/applyupdates":
            if in_window(mrow.get("start_utc") or mrow.get("end_utc"), win_start_dt, win_end_dt):
                config_Catalog_runs.append(mrow)
                window_cycles.append(mrow)
        else:
            if in_window(mrow.get("start_utc") or mrow.get("end_utc"), win_start_dt, win_end_dt):
                window_cycles.append(mrow)
                if mrow["machine_id"]:
                    cycles_by_machine.setdefault(mrow["machine_id"], []).append(mrow)

    extensions_by_machine = {mid: [] for mid in machines_by_id}
    for ext in raw["extensions"]:
        extensions_by_machine.setdefault(ext["machine_id"], []).append(ext)

    investigated_machines = []
    failure_records = []

    for mid in sorted(machines_by_id):
        m = machines_by_id[mid]
        ass = assessments_by_machine.get(mid)
        pend = pending_by_machine.get(mid, [])
        insts = sorted(installs_by_machine.get(mid, []), key=lambda x: x.get("start_utc") or "", reverse=True)
        inst_patches = installed_patches_by_machine.get(mid, [])
        m_cycles = sorted(cycles_by_machine.get(mid, []), key=lambda x: x.get("start_utc") or "", reverse=True)
        m_assigns = assignments_by_machine.get(mid, [])
        m_exts = sorted(extensions_by_machine.get(mid, []), key=lambda x: x["name"].lower())

        apply_cycles = [c for c in m_cycles if c["type"] == "microsoft.maintenance/applyupdates"]
        unresponsive_cycles = [c for c in apply_cycles if c["status"] == "ShutdownOrUnresponsive"]
        applied_cycles = [c for c in apply_cycles if c["status"] == "UpdateSuccessfullyApplied"]
        failed_cycles = [
            c for c in apply_cycles
            if c["status"] not in ("UpdateSuccessfullyApplied", "ShutdownOrUnresponsive", "Completed")
        ]

        failed_insts = [
            i for i in insts
            if i["status"] in ("Failed", "Warning")
            or i["failed_patch_count"] > 0
            or i["maintenance_window_exceeded"]
        ]
        succeeded_insts = [i for i in insts if i["status"] == "Succeeded"]

        failed_exts = [e for e in m_exts if e["provisioning_state"].lower() not in ("succeeded", "creating", "updating")]
        sec_patches = [
            p for p in pend
            if any(c.lower() in ("security", "critical") for c in p["classifications"])
        ]
        rollup_patches = [
            p for p in pend
            if any("rollup" in c.lower() for c in p["classifications"])
        ]

        counts = ass["counts"] if ass else {
            "security": len(sec_patches),
            "critical": 0,
            "update_rollup": len(rollup_patches),
            "definition": 0,
            "updates": 0,
            "other": len(pend),
            "security_or_critical": len(sec_patches),
            "actionable_non_definition": len(sec_patches) + len(rollup_patches),
            "total": len(pend),
        }
        readiness = pick(ass, "configuration_status", "vm_guest_patch_readiness") or "NotAssessed"
        patch_mode_status = pick(ass, "configuration_status", "patch_mode_status") or "Unknown"
        hotpatch = pick(ass, "hotpatch")

        detected_issues = []

        # 1. Arc agent expired or disconnected
        if m["hosting"] == "arc" and (m.get("arc_status") or "").lower() in ("expired", "disconnected", "error"):
            detected_issues.append({
                "failure_category": "arc_agent_expired_or_disconnected",
                "severity": "critical",
                "investigation_headline": (
                    "Azure Connected Machine agent (azcmagent) in state '" + str(m.get("arc_status"))
                    + "' since " + str(m.get("last_status_change_utc") or "an unknown date")
                    + " (version " + str(m.get("agent_version") or "unknown") + ")."
                ),
                "root_cause_evidence": (
                    "The hybrid Azure Arc server sends no heartbeat to the Microsoft.HybridCompute control plane. "
                    "With the agent in state '" + str(m.get("arc_status")) + "', Azure Update Manager cannot "
                    "deploy the assessment extension or run scheduled maintenance windows."
                ),
                "log_or_source_reference": (
                    "arg_compute_machines :: " + m["resource_id"]
                    + " :: properties.status=" + str(m.get("arc_status"))
                    + ", lastStatusChange=" + str(m.get("last_status_change_utc"))
                ),
                "recommended_human_action": (
                    "Check whether the physical or virtual server is still in service or should be removed from Azure Arc. "
                    "If the host is still in service, reconnect it or renew the azcmagent certificate ('azcmagent check' / 'azcmagent connect') "
                    "and update the agent before the next monthly cycle."
                ),
            })

        # 2. Maintenance window unresponsive or installation failure
        if unresponsive_cycles or failed_cycles or failed_insts:
            latest_unresp = unresponsive_cycles[0] if unresponsive_cycles else (failed_cycles[0] if failed_cycles else None)
            latest_inst_fail = failed_insts[0] if failed_insts else None
            if latest_unresp:
                corr = latest_unresp.get("correlation_id") or latest_unresp["resource_id"]
                conf_name = latest_unresp.get("maintenance_configuration_name") or "assigned configuration"
                detected_issues.append({
                    "failure_category": "maintenance_window_unresponsive",
                    "severity": "critical",
                    "investigation_headline": (
                        str(len(unresponsive_cycles)) + " of " + str(len(apply_cycles))
                        + " maintenance window runs ended in 'ShutdownOrUnresponsive' ("
                        + str(len(applied_cycles)) + " 'UpdateSuccessfullyApplied')."
                    ),
                    "root_cause_evidence": (
                        "Azure Update Manager recorded status 'ShutdownOrUnresponsive' for configuration '" + conf_name
                        + "' (last failed cycle: " + str(latest_unresp.get("start_utc")) + " -> "
                        + str(latest_unresp.get("end_utc")) + "). The machine was stopped or deallocated, or the guest "
                        "agent did not respond during the scheduled window. Successful installation runs while "
                        "it was running: " + str(len(succeeded_insts)) + "."
                    ),
                    "log_or_source_reference": (
                        "arg_maintenance_cycles :: " + latest_unresp["resource_id"]
                        + " :: correlationId=" + str(corr)
                    ),
                    "recommended_human_action": (
                        "Align the schedule of the maintenance configuration ('" + conf_name + "') with the hours when "
                        "the machine is actually running, or add a pre-maintenance event that starts it before the patching window."
                    ),
                })
            elif latest_inst_fail:
                detected_issues.append({
                    "failure_category": "maintenance_window_unresponsive",
                    "severity": "critical",
                    "investigation_headline": (
                        "Patch installation run failed (" + str(latest_inst_fail["status"])
                        + ", failed patches=" + str(latest_inst_fail["failed_patch_count"])
                        + ", window exceeded=" + str(latest_inst_fail["maintenance_window_exceeded"]) + ")."
                    ),
                    "root_cause_evidence": (
                        "The patchInstallationResults run that started at " + str(latest_inst_fail.get("start_utc"))
                        + " reported code '" + str(latest_inst_fail.get("error_code") or "Error")
                        + "': " + str(latest_inst_fail.get("error_message") or "Failure or maintenance window exceeded.")
                    ),
                    "log_or_source_reference": "arg_patch_installations :: " + latest_inst_fail["resource_id"],
                    "recommended_human_action": (
                        "Extend the maintenance window and review the packages with installationState='Failed' "
                        "in patchinstallationresources."
                    ),
                })

        # 3. Assessment stuck InProgress or readiness UnableToDetermine
        if ass and (
            ass["status"] in ("InProgress", "Failed")
            or readiness in ("UnableToDetermine", "Unsupported")
        ):
            sec_names = ", ".join(
                (p["patch_name"] + (" (" + p["version"] + ")" if p["version"] else ""))
                for p in sec_patches[:5]
            ) or "not listed individually"
            detected_issues.append({
                "failure_category": "assessment_stuck_or_readiness_undetermined",
                "severity": "high",
                "investigation_headline": (
                    "Patch assessment in state '" + str(ass["status"])
                    + "' and guest patch support '" + str(readiness) + "'; pending security updates: "
                    + str(counts["security_or_critical"]) + " of "
                    + str(counts["total"]) + " pending packages."
                ),
                "root_cause_evidence": (
                    "patchassessmentresources reports status='" + str(ass["status"])
                    + "', detectedVMGuestPatchSupportState='" + str(readiness)
                    + "' and patchModeConfiguration.status='" + str(patch_mode_status)
                    + "' (configuration last modified: "
                    + str(pick(ass, "configuration_status", "last_modified_utc") or ass.get("last_modified_utc"))
                    + "). Pending Security patches: " + str(counts["security"]) + " (" + sec_names
                    + "); other packages with no active installation window: " + str(counts["other"]) + "."
                ),
                "log_or_source_reference": (
                    "arg_patch_assessments :: " + ass["resource_id"]
                    + " :: vmGuestPatchReadiness=" + str(readiness)
                ),
                "recommended_human_action": (
                    "Unblock the apt/dpkg process or the package manager on the Linux Arc host, confirm that "
                    "Azure Update Manager supports the distribution (Ubuntu 24.04 + azcmagent) and assign the machine to an "
                    "active maintenance configuration."
                ),
            })

        # 4. Hotpatch or guest patch/management extension error
        has_hotpatch_err = bool(
            hotpatch
            and (
                (hotpatch.get("error_code") or "").lower() not in ("", "success", "0")
                or hotpatch.get("detail_codes")
            )
        )
        if has_hotpatch_err or failed_exts:
            if has_hotpatch_err:
                detail_code = (hotpatch.get("detail_codes") or [hotpatch.get("error_code")])[0]
                detail_msg = (hotpatch.get("detail_messages") or [hotpatch.get("error_message")])[0]
                log_ref = hotpatch.get("log_path") or (ass["resource_id"] if ass else m["resource_id"])
                detected_issues.append({
                    "failure_category": "hotpatch_or_patch_extension_error",
                    "severity": "high",
                    "investigation_headline": (
                        "Hotpatch readiness error '" + str(detail_code)
                        + "' in WindowsPatchExtension (hotpatchEnablementStatus='"
                        + str(hotpatch.get("enablement_status")) + "')."
                    ),
                    "root_cause_evidence": (
                        "The hotpatchStatus object in patchassessmentresources reports code '" + str(detail_code)
                        + "' (" + str(detail_msg) + "). In addition, package '"
                        + ", ".join(p["patch_name"] for p in pend if "RollUp" in (p["primary_classification"] or ""))
                        + "' stayed 'NotSelected' during the scheduled runs because its classification was not "
                        "selected in the window."
                    ),
                    "log_or_source_reference": str(log_ref),
                    "recommended_human_action": (
                        "Enable hotpatching on the Windows Server 2025 VM if patching without reboots is required, or skip "
                        "the hotpatch check and add the 'UpdateRollUp' classification to the maintenance configuration "
                        "so that KB890830 is installed. Review the local log " + str(log_ref) + " only if the extension code persists."
                    ),
                })
            if failed_exts:
                ext_summary = ", ".join(e["name"] + " (" + e["provisioning_state"] + ")" for e in failed_exts)
                detected_issues.append({
                    "failure_category": "hotpatch_or_patch_extension_error",
                    "severity": "high",
                    "investigation_headline": (
                        str(len(failed_exts)) + " of this machine's extensions failed: " + ext_summary + "."
                    ),
                    "root_cause_evidence": (
                        "arg_patch_extensions found provisioningState='Failed' in " + ext_summary
                        + " on machine '" + m["name"] + "' (power state: " + str(m.get("power_state") or "unknown") + ")."
                    ),
                    "log_or_source_reference": "arg_patch_extensions :: " + failed_exts[0]["resource_id"],
                    "recommended_human_action": (
                        "Start the virtual machine during a controlled window and reprovision or update every extension "
                        "in the Failed state (" + ext_summary + ")."
                    ),
                })

        # 5. Pending security/critical/rollup patches without scheduled maintenance execution
        if ass and ass["status"] == "Succeeded" and (counts["security_or_critical"] > 0 or counts["update_rollup"] > 0) and not m_assigns and not insts:
            kb_list = [
                (p["kb_id"] and ("KB" + p["kb_id"]) or p["patch_name"])
                for p in pend
                if any(c.lower() in ("security", "critical", "updaterollup") for c in p["classifications"])
            ]
            kb_text = " (" + ", ".join(kb_list[:6]) + ")" if kb_list else ""
            detected_issues.append({
                "failure_category": "pending_security_patches_unscheduled",
                "severity": "medium",
                "investigation_headline": (
                    str(counts["security"]) + " Security and " + str(counts["update_rollup"])
                    + " UpdateRollUp patches pending" + kb_text
                    + ", with no maintenance configuration assigned and no runs in the period."
                ),
                "root_cause_evidence": (
                    "The automatic assessment on '" + m["name"] + "' completed successfully on "
                    + str(ass.get("last_modified_utc")) + "; available updates: " + str(counts["total"])
                    + " (" + str(counts["security"]) + " Security, "
                    + str(counts["update_rollup"]) + " UpdateRollUp, " + str(counts["updates"])
                    + " Updates, " + str(counts["definition"]) + " Definition), but patchModeConfiguration.status is '"
                    + str(patch_mode_status) + "' and there are 0 assignments in microsoft.maintenance/configurationassignments."
                ),
                "log_or_source_reference": "arg_patch_assessments :: " + ass["resource_id"],
                "recommended_human_action": (
                    "Create the microsoft.maintenance/configurationAssignments link to the approved maintenance "
                    "window to install the pending KBs" + kb_text + "."
                ),
            })

        # 6. Unassessed / no Update Manager telemetry
        if ass is None and not insts and not apply_cycles:
            if not detected_issues:
                detected_issues.append({
                    "failure_category": "unassessed_no_update_manager_telemetry",
                    "severity": "low",
                    "investigation_headline": (
                        "No assessment or installation records in Azure Update Manager (state='"
                        + str(m.get("power_state") or m.get("arc_status") or "Unknown")
                        + "', assessmentMode='" + str(m.get("assessment_mode") or "ImageDefault") + "')."
                    ),
                    "root_cause_evidence": (
                        "Machine '" + m["name"] + "' is in the compute inventory (" + m["type"]
                        + "), but has no record in patchassessmentresources or patchinstallationresources. "
                        "Its current state is '" + str(m.get("power_state") or m.get("arc_status") or "Unknown")
                        + "' with assessmentMode='" + str(m.get("assessment_mode") or "None")
                        + "' and patchMode='" + str(m.get("patch_mode") or "None") + "'."
                    ),
                    "log_or_source_reference": "arg_compute_machines :: " + m["resource_id"],
                    "recommended_human_action": (
                        "If the VM is in operational scope, set assessmentMode='AutomaticByPlatform' "
                        "and schedule periodic assessments while the instance is running."
                    ),
                })

        # Determine primary diagnostic vs healthy state
        if detected_issues:
            # Sort issues by severity order so the most critical operational blocker leads
            detected_issues.sort(key=lambda item: SEVERITY_ORDER.get(item["severity"], 9))
            primary = detected_issues[0]
            matched_cats = list(dict.fromkeys(item["failure_category"] for item in detected_issues))
            for idx, issue in enumerate(detected_issues, start=1):
                failure_records.append({
                    "failure_id": "FAIL-" + hashlib.sha256((mid + ":" + issue["failure_category"] + ":" + str(idx)).encode("utf-8")).hexdigest()[:10],
                    "machine_id": mid,
                    "machine_name": m["name"],
                    "resource_group": m["resource_group"],
                    "hosting": m["hosting"],
                    "os_type": m["os_type"],
                    "os_name": m["os_name"],
                    "power_or_arc_state": m.get("arc_status") if m["hosting"] == "arc" else (m.get("power_state") or "Unknown"),
                    "failure_category": issue["failure_category"],
                    "failure_category_label": CATEGORY_LABELS[issue["failure_category"]],
                    "severity": issue["severity"],
                    "severity_label": SEVERITY_LABELS[issue["severity"]],
                    "investigation_headline": issue["investigation_headline"],
                    "root_cause_evidence": issue["root_cause_evidence"],
                    "log_or_source_reference": issue["log_or_source_reference"],
                    "recommended_human_action": issue["recommended_human_action"],
                    "pending_security_count": counts["security_or_critical"],
                    "pending_rollup_count": counts["update_rollup"],
                    "pending_total_count": counts["total"],
                    "unresponsive_cycles_count": len(unresponsive_cycles),
                    "succeeded_cycles_count": len(applied_cycles),
                    "observed_at": reference_utc,
                })
        else:
            primary = {
                "failure_category": "healthy",
                "severity": "info",
                "investigation_headline": "Assessment and patching cycles completed with no errors and no pending critical patches.",
                "root_cause_evidence": (
                    "Assessment in state 'Succeeded' with no pending reboot and no errors in extensions or maintenance windows."
                ),
                "log_or_source_reference": (ass["resource_id"] if ass else m["resource_id"]),
                "recommended_human_action": "Keep the scheduled cadence in Azure Update Manager.",
            }
            matched_cats = ["healthy"]

        latest_inst = insts[0] if insts else None
        investigated_machines.append({
            **m,
            "power_or_arc_state": m.get("arc_status") if m["hosting"] == "arc" else (m.get("power_state") or "Unknown"),
            "assessment_status": ass["status"] if ass else "NoAssessment",
            "assessment_last_modified_utc": ass.get("last_modified_utc") if ass else None,
            "reboot_pending": ass.get("reboot_pending") if ass else None,
            "vm_guest_patch_readiness": readiness,
            "patch_mode_status": patch_mode_status,
            "pending_counts": counts,
            "pending_security_patches": [
                {
                    "patch_name": p["patch_name"],
                    "kb_id": p["kb_id"],
                    "version": p["version"],
                    "classifications": p["classifications"],
                    "msrc_severity": p["msrc_severity"],
                    "reboot_behavior": p["reboot_behavior"],
                }
                for p in (sec_patches + rollup_patches)[:15]
            ],
            "maintenance_configuration_assignments": [
                c["maintenance_configuration_name"] or c["maintenance_configuration_id"]
                for c in m_assigns
            ],
            "maintenance_cycles_summary": {
                "total": len(apply_cycles),
                "succeeded": len(applied_cycles),
                "unresponsive": len(unresponsive_cycles),
                "other": len(failed_cycles),
            },
            "installations_summary": {
                "runs_in_window": len(insts),
                "succeeded_runs": len(succeeded_insts),
                "failed_runs": len(failed_insts),
                "installed_patches_total": sum(i["installed_patch_count"] for i in insts),
                "not_selected_patches_total": sum(i["not_selected_patch_count"] for i in insts),
                "last_installation_utc": latest_inst.get("last_modified_utc") if latest_inst else None,
                "last_installation_status": latest_inst.get("status") if latest_inst else None,
                "last_reboot_status": latest_inst.get("reboot_status") if latest_inst else None,
            },
            "hotpatch": hotpatch,
            "extensions_count": len(m_exts),
            "failed_extensions_count": len(failed_exts),
            "extensions": [
                {
                    "name": e["name"],
                    "publisher": e["publisher"],
                    "extension_type": e["extension_type"],
                    "version": e["type_handler_version"],
                    "provisioning_state": e["provisioning_state"],
                    "enable_automatic_upgrade": e["enable_automatic_upgrade"],
                }
                for e in m_exts
            ],
            "failure_category": primary["failure_category"],
            "failure_category_label": CATEGORY_LABELS[primary["failure_category"]],
            "matched_categories": matched_cats,
            "severity": primary["severity"],
            "severity_label": SEVERITY_LABELS[primary["severity"]],
            "investigation_headline": primary["investigation_headline"],
            "root_cause_evidence": primary["root_cause_evidence"],
            "log_or_source_reference": primary["log_or_source_reference"],
            "recommended_human_action": primary["recommended_human_action"],
            "all_detected_issues": detected_issues,
        })

    investigated_machines.sort(
        key=lambda item: (
            SEVERITY_ORDER.get(item["severity"], 9),
            item["hosting"],
            item["name"].lower(),
        )
    )
    failure_records.sort(
        key=lambda item: (
            SEVERITY_ORDER.get(item["severity"], 9),
            item["machine_name"].lower(),
            item["failure_category"],
        )
    )
    window_installations.sort(key=lambda item: item.get("start_utc") or "", reverse=True)
    window_cycles.sort(key=lambda item: item.get("start_utc") or item.get("id") or "", reverse=True)

    return {
        "machines": investigated_machines,
        "failures": failure_records,
        "window_installations": window_installations,
        "window_installed_patches": window_installed_patches,
        "window_cycles": window_cycles,
    }


def build_actions(failures):
    grouped = {}
    for item in failures:
        cat = item["failure_category"]
        if cat not in grouped:
            grouped[cat] = {
                "action_id": "ACT-" + cat.upper()[:24],
                "failure_category": cat,
                "failure_category_label": item["failure_category_label"],
                "severity": item["severity"],
                "severity_label": item["severity_label"],
                "affected_machines_count": 0,
                "affected_machines": [],
                "investigation_summary": item["investigation_headline"],
                "recommended_human_action": item["recommended_human_action"],
                "sample_source_reference": item["log_or_source_reference"],
            }
        entry = grouped[cat]
        if item["machine_name"] not in entry["affected_machines"]:
            entry["affected_machines"].append(item["machine_name"])
            entry["affected_machines_count"] = len(entry["affected_machines"])
    actions = list(grouped.values())
    actions.sort(key=lambda a: (SEVERITY_ORDER.get(a["severity"], 9), -a["affected_machines_count"], a["failure_category"]))
    return actions


def collect_live(config, period, reference_utc, deadline=None):
    identity = Identity(config)
    try:
        reader = ArgReader(identity, config, deadline=deadline)
        queries = arg_queries()
        raw_tables = {}
        sources = []
        for sid in SOURCE_IDS:
            rows, receipt = reader.query_table(sid, queries[sid], reference_utc)
            raw_tables[sid] = rows
            sources.append(receipt)
        if all(s["status"] in ("denied", "error") for s in sources):
            first_err = sources[0]["errors"][0] if sources[0]["errors"] else {"code": "collection_failed", "http_status": None}
            raise EvidenceError(
                first_err["code"],
                "All Azure Resource Graph queries failed; no synthetic or empty patching report was produced.",
                "arg_compute_machines",
                first_err.get("http_status"),
            )
        return normalize_collected(raw_tables, sources, config, period, reference_utc)
    finally:
        identity.close()


def normalize_collected(raw_tables, sources, config, period, reference_utc):
    sub_id = config["subscription_id"]
    machines = [normalize_machine(r, sub_id, reference_utc) for r in raw_tables.get("arg_compute_machines", [])]
    assessments = [normalize_assessment(r, sub_id, reference_utc) for r in raw_tables.get("arg_patch_assessments", [])]
    pending_patches = [normalize_pending_patch(r, sub_id, reference_utc) for r in raw_tables.get("arg_software_patches_pending", [])]
    installations = [normalize_installation(r, sub_id, reference_utc) for r in raw_tables.get("arg_patch_installations", [])]
    installed_patches = [normalize_installed_patch(r, sub_id, reference_utc) for r in raw_tables.get("arg_software_patches_installed", [])]
    maintenance_cycles = [normalize_maintenance_row(r, sub_id, reference_utc) for r in raw_tables.get("arg_maintenance_cycles", [])]
    extensions = [normalize_extension(r, sub_id, reference_utc) for r in raw_tables.get("arg_patch_extensions", [])]
    return {
        "subscription_id": sub_id,
        "period": period,
        "machines": machines,
        "assessments": assessments,
        "software_patches_pending": pending_patches,
        "installations": installations,
        "software_patches_installed": installed_patches,
        "maintenance_cycles": maintenance_cycles,
        "extensions": extensions,
        "sources": sources,
    }


def finish_snapshot(raw, reference_utc, provenance="LIVE", environment="PRODUCTION"):
    if provenance not in ("LIVE", "SIMULATED"):
        raise EvidenceError("invalid_provenance", "provenance must be LIVE or SIMULATED.")
    period = raw.get("period", "last_30d")
    window = window_for(period, reference_utc)
    inv = investigate_machines(raw, window, reference_utc)
    machines = inv["machines"]
    failures = inv["failures"]
    win_installs = inv["window_installations"]
    win_installed_patches = inv["window_installed_patches"]
    win_cycles = inv["window_cycles"]
    actions = build_actions(failures)

    apply_cycles = [c for c in win_cycles if c["type"] == "microsoft.maintenance/applyupdates"]
    config_runs = [c for c in win_cycles if c["type"] == "microsoft.maintenance/maintenanceconfigurations/applyupdates"]
    assign_rows = [c for c in win_cycles if c["type"] == "microsoft.maintenance/configurationassignments"]

    cat_counts = Counter(m["failure_category"] for m in machines)
    sev_counts = Counter(m["severity"] for m in machines)
    hosting_counts = Counter(m["hosting"] for m in machines)

    assessed_machines = [m for m in machines if m["assessment_status"] != "NoAssessment"]
    machines_with_issues = [m for m in machines if m["failure_category"] != "healthy"]

    total_sec_pending = sum(m["pending_counts"]["security_or_critical"] for m in machines)
    total_rollup_pending = sum(m["pending_counts"]["update_rollup"] for m in machines)
    total_pending_all = sum(m["pending_counts"]["total"] for m in machines)

    unresp_count = sum(c["status"] == "ShutdownOrUnresponsive" for c in apply_cycles)
    applied_count = sum(c["status"] == "UpdateSuccessfullyApplied" for c in apply_cycles)

    summary_kpis = {
        "subscription_id": raw["subscription_id"],
        "period": period,
        "window": window,
        "machines_total": len(machines),
        "azure_vms_total": hosting_counts.get("azure", 0),
        "arc_machines_total": hosting_counts.get("arc", 0),
        "assessed_machines_total": len(assessed_machines),
        "unassessed_machines_total": len(machines) - len(assessed_machines),
        "healthy_machines_total": cat_counts.get("healthy", 0),
        "machines_with_blockers_total": len(machines_with_issues),
        "diagnostic_findings_total": len(failures),
        "critical_machines_total": sev_counts.get("critical", 0),
        "high_machines_total": sev_counts.get("high", 0),
        "medium_machines_total": sev_counts.get("medium", 0),
        "low_machines_total": sev_counts.get("low", 0),
        "category_counts": {cat: cat_counts.get(cat, 0) for cat in FAILURE_CATEGORIES if cat != "all"},
        "maintenance_cycles_in_window": len(apply_cycles),
        "maintenance_cycles_succeeded": applied_count,
        "maintenance_cycles_unresponsive": unresp_count,
        "maintenance_config_runs_in_window": len(config_runs),
        "maintenance_assignments_total": len(assign_rows),
        "installation_runs_in_window": len(win_installs),
        "installation_runs_succeeded": sum(i["status"] == "Succeeded" for i in win_installs),
        "installation_runs_failed": sum(i["status"] in ("Failed", "Warning") or i["failed_patch_count"] > 0 for i in win_installs),
        "installed_patches_in_window": sum(p["installation_state"] == "Installed" for p in win_installed_patches),
        "not_selected_patches_in_window": sum(p["installation_state"] == "NotSelected" for p in win_installed_patches),
        "pending_security_or_critical_patches": total_sec_pending,
        "pending_rollup_patches": total_rollup_pending,
        "pending_total_patches": total_pending_all,
        "guest_extensions_total": len(raw["extensions"]),
        "guest_extensions_failed": sum(e["provisioning_state"].lower() not in ("succeeded", "creating", "updating") for e in raw["extensions"]),
    }

    executive_messages = [
        (
            plural(summary_kpis["machines_total"], "machine", "machines") + " in inventory ("
            + plural(summary_kpis["azure_vms_total"], "Azure VM", "Azure VMs") + " and "
            + plural(summary_kpis["arc_machines_total"], "hybrid Azure Arc server", "hybrid Azure Arc servers") + "): "
            + str(summary_kpis["assessed_machines_total"]) + " assessed by Update Manager and "
            + str(summary_kpis["unassessed_machines_total"]) + " with no assessment telemetry."
        ),
        (
            plural(summary_kpis["maintenance_cycles_in_window"], "per-machine maintenance cycle", "per-machine maintenance cycles") + " recorded in the window ("
            + str(applied_count) + " 'UpdateSuccessfullyApplied' versus "
            + str(unresp_count) + " 'ShutdownOrUnresponsive') and "
            + plural(summary_kpis["installation_runs_in_window"], "patchInstallationResults run", "patchInstallationResults runs") + "."
        ),
        (
            plural(cat_counts.get("arc_agent_expired_or_disconnected", 0), "Azure Arc server has", "Azure Arc servers have")
            + " the agent in state 'Expired'/'Disconnected', which blocks assessment and patch deployment."
        ),
        (
            plural(cat_counts.get("assessment_stuck_or_readiness_undetermined", 0), "machine has an assessment", "machines have assessments")
            + " stuck in 'InProgress' with vmGuestPatchReadiness='UnableToDetermine', and "
            + plural(cat_counts.get("pending_security_patches_unscheduled", 0), "server has", "servers have")
            + " pending Security/UpdateRollUp patches with no maintenance window assigned."
        ),
        (
            "Automated root-cause diagnosis generated for " + plural(len(machines), "machine", "machines")
            + " (" + plural(len(failures), "technical finding", "technical findings") + " correlated across ARG, extensions, Hotpatch and maintenance windows), "
            "without signing in to any machine."
        ),
    ]

    all_patches_combined = (
        sorted(
            raw["software_patches_pending"],
            key=lambda p: (
                0 if "Security" in p["classifications"] or "Critical" in p["classifications"] else (1 if "UpdateRollUp" in p["classifications"] else 2),
                p["machine_name"].lower(),
                p["patch_name"].lower(),
            ),
        )
        + sorted(
            win_installed_patches,
            key=lambda p: (p.get("last_modified_utc") or "", p["machine_name"].lower()),
            reverse=True,
        )
    )

    return {
        "schema_version": "1.0",
        "provenance": provenance,
        "environment": environment,
        "reference_utc": reference_utc,
        "subscription_id": raw["subscription_id"],
        "window": window,
        "client": {
            "name": CLIENT_NAME,
            "logo_data_uri": CLIENT_LOGO_DATA_URI,
            "logo_alt": CLIENT_LOGO_ALT,
        },
        "summary": summary_kpis,
        "executive_messages": executive_messages,
        "machines": machines,
        "failures": failures,
        "cycles": {
            "maintenance_cycles": win_cycles,
            "installation_runs": win_installs,
        },
        "patches": {
            "pending": raw["software_patches_pending"],
            "installed_in_window": win_installed_patches,
            "combined": all_patches_combined,
        },
        "extensions": raw["extensions"],
        "actions": actions,
        "sources": raw["sources"],
        "methodology": {
            "read_only": True,
            "scheduled_cadence_cron": "0 8 1 * *",
            "scheduled_cadence_description": "Day 1 of every month at 08:00 UTC (plus on-demand runs after a patching window).",
            "arg_tables": [
                "resources (microsoft.compute/virtualmachines, microsoft.hybridcompute/machines, extensions)",
                "patchassessmentresources (patchAssessmentResults/latest and softwarePatches)",
                "patchinstallationresources (patchInstallationResults and softwarePatches)",
                "maintenanceresources (applyupdates, configurationassignments, maintenanceconfigurations/applyupdates, updates)",
            ],
            "limitations": [
                "100% read-only collection through the Azure Resource Graph API (2022-10-01); the tool never runs guest commands (runCommand) and never starts or stops machines.",
                "Sensitive or private extension configuration blocks are never requested or exported.",
                "Local log paths shown by Azure Update Manager (for example WindowsPatchExtension) come from the error message reported to the ARM control plane.",
            ],
        },
    }


def compact_machine_row(m):
    return {
        "machine_name": m["name"],
        "hosting": m["hosting"],
        "resource_group": m["resource_group"],
        "os_type": m["os_type"],
        "power_or_arc_state": m["power_or_arc_state"],
        "assessment_status": m["assessment_status"],
        "vm_guest_patch_readiness": m["vm_guest_patch_readiness"],
        "pending_security_or_critical": m["pending_counts"]["security_or_critical"],
        "pending_update_rollup": m["pending_counts"]["update_rollup"],
        "pending_total": m["pending_counts"]["total"],
        "cycles_succeeded": m["maintenance_cycles_summary"]["succeeded"],
        "cycles_unresponsive": m["maintenance_cycles_summary"]["unresponsive"],
        "install_runs_in_window": m["installations_summary"]["runs_in_window"],
        "failure_category": m["failure_category"],
        "matched_categories": m["matched_categories"],
        "severity": m["severity"],
        "investigation_headline": m["investigation_headline"],
        "log_or_source_reference": m["log_or_source_reference"],
    }


def compact_failure_row(f):
    return {
        "failure_id": f["failure_id"],
        "machine_name": f["machine_name"],
        "hosting": f["hosting"],
        "resource_group": f["resource_group"],
        "power_or_arc_state": f["power_or_arc_state"],
        "failure_category": f["failure_category"],
        "severity": f["severity"],
        "pending_security_count": f["pending_security_count"],
        "unresponsive_cycles_count": f["unresponsive_cycles_count"],
        "investigation_headline": f["investigation_headline"],
        "log_or_source_reference": f["log_or_source_reference"][:180],
    }


def snapshot_rows(snapshot, view):
    if view == "summary":
        return [snapshot["summary"]]
    if view == "machines":
        return [compact_machine_row(m) for m in snapshot["machines"]]
    if view == "failures":
        return [compact_failure_row(f) for f in snapshot["failures"]]
    if view == "cycles":
        rows = []
        for c in snapshot["cycles"]["maintenance_cycles"]:
            rows.append({
                "record_type": c["type"],
                "machine_name": c["machine_name"],
                "status": c["status"],
                "start_utc": c["start_utc"],
                "end_utc": c["end_utc"],
                "maintenance_configuration_name": c["maintenance_configuration_name"],
                "correlation_id": c["correlation_id"],
                "resource_id": c["resource_id"],
            })
        for i in snapshot["cycles"]["installation_runs"]:
            rows.append({
                "record_type": "patch_installation_run",
                "machine_name": i["machine_name"],
                "status": i["status"],
                "start_utc": i["start_utc"],
                "end_utc": i["last_modified_utc"],
                "installed_patch_count": i["installed_patch_count"],
                "failed_patch_count": i["failed_patch_count"],
                "not_selected_patch_count": i["not_selected_patch_count"],
                "reboot_status": i["reboot_status"],
                "maintenance_run_id": i["maintenance_run_id"],
                "resource_id": i["resource_id"],
            })
        return rows
    if view == "patches":
        return [
            {
                "record_kind": p["record_kind"],
                "machine_name": p["machine_name"],
                "patch_name": p["patch_name"],
                "kb_id": p["kb_id"],
                "version": p["version"],
                "primary_classification": p["primary_classification"],
                "installation_state": p["installation_state"],
                "reboot_behavior": p["reboot_behavior"],
                "last_modified_utc": p["last_modified_utc"],
            }
            for p in snapshot["patches"]["combined"]
        ]
    if view == "extensions":
        return [
            {
                "machine_name": e["machine_name"],
                "hosting": e["hosting"],
                "name": e["name"],
                "publisher": e["publisher"],
                "extension_type": e["extension_type"],
                "type_handler_version": e["type_handler_version"],
                "provisioning_state": e["provisioning_state"],
                "auto_upgrade_minor_version": e["auto_upgrade_minor_version"],
                "enable_automatic_upgrade": e["enable_automatic_upgrade"],
            }
            for e in snapshot["extensions"]
        ]
    if view == "coverage":
        return snapshot["sources"]
    if view == "actions":
        return snapshot["actions"]
    raise EvidenceError("invalid_parameter", "Unsupported view: " + str(view), "parameters")


def collection_disclosure(snapshot):
    return {
        "reference_utc": snapshot["reference_utc"],
        "fresh_collection": True,
        "provenance": snapshot["provenance"],
        "subscription_id": snapshot["subscription_id"],
        "period": snapshot["window"]["period"],
        "window_start_utc": snapshot["window"]["start_utc"],
        "window_end_utc": snapshot["window"]["end_utc"],
        "source_status_counts": dict(Counter(s["status"] for s in snapshot["sources"])),
        "source_total": len(snapshot["sources"]),
        "source_details_view": "coverage",
        "paging_basis": "Local offset in this collection; later calls recollect, not a stable cross-call cursor.",
    }


def response_bytes(document):
    return len(json.dumps(document, ensure_ascii=False, allow_nan=False).encode("utf-8"))


def ensure_response(document):
    if response_bytes(document) > TRANSPORT_BYTES:
        raise EvidenceError("transport_budget_exceeded", "Response exceeds the 3500-byte JSON transport budget.", "transport")
    return document


def query_snapshot(snapshot, params):
    view = params["view"]
    rows = snapshot_rows(snapshot, view)
    machine_by_name = {m["name"].lower(): m for m in snapshot["machines"]}

    def matches(row):
        m_name = (row.get("machine_name") or row.get("name") or "").lower()
        m_obj = machine_by_name.get(m_name)
        if params["machine_name"]:
            target = params["machine_name"].lower()
            if view == "actions":
                if not any(name.lower() == target for name in row.get("affected_machines", [])):
                    return False
            elif m_name != target:
                return False
        if params["hosting"] != "all":
            row_hosting = row.get("hosting") or (m_obj.get("hosting") if m_obj else None)
            if row_hosting != params["hosting"]:
                return False
        if params["failure_category"] != "all":
            cat = params["failure_category"]
            row_cat = row.get("failure_category")
            matched_cats = row.get("matched_categories") or (m_obj.get("matched_categories") if m_obj else [])
            if row_cat != cat and cat not in (matched_cats or []):
                return False
        return True

    matched = [r for r in rows if matches(r)] if view != "summary" or (
        params["hosting"] == "all" and params["failure_category"] == "all" and not params["machine_name"]
    ) else [r for r in rows if matches(r)]
    selected = matched[params["offset"]:params["offset"] + params["limit"]]
    partial = any(s["status"] != "complete" for s in snapshot["sources"])
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
                "message": "One complete row cannot fit 3500 default-serialized bytes. Use the full report JSON.",
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
        raise EvidenceError("round_trip_failed", "Embedded normalized JSON did not round-trip.", "renderer")
    return escaped


def render_html(snapshot):
    if HTML_TEMPLATE.count("__REPORT_DATA_JSON__") != 1:
        raise EvidenceError("template_missing", "Build the approved template into the standalone tool with build_tool.py.", "renderer")
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


def machines_csv_rows(snapshot):
    rows = []
    for m in snapshot["machines"]:
        rows.append({
            "machine_name": m["name"],
            "hosting": m["hosting"],
            "resource_group": m["resource_group"],
            "location": m["location"],
            "os_type": m["os_type"],
            "os_name": m["os_name"],
            "power_or_arc_state": m["power_or_arc_state"],
            "agent_version": m.get("agent_version") or "",
            "last_status_change_utc": m.get("last_status_change_utc") or "",
            "patch_mode": m.get("patch_mode") or "",
            "assessment_mode": m.get("assessment_mode") or "",
            "assessment_status": m["assessment_status"],
            "vm_guest_patch_readiness": m["vm_guest_patch_readiness"],
            "reboot_pending": m["reboot_pending"],
            "pending_security_or_critical": m["pending_counts"]["security_or_critical"],
            "pending_update_rollup": m["pending_counts"]["update_rollup"],
            "pending_total": m["pending_counts"]["total"],
            "maintenance_cycles_succeeded": m["maintenance_cycles_summary"]["succeeded"],
            "maintenance_cycles_unresponsive": m["maintenance_cycles_summary"]["unresponsive"],
            "installations_in_window": m["installations_summary"]["runs_in_window"],
            "failed_extensions_count": m["failed_extensions_count"],
            "failure_category": m["failure_category"],
            "matched_categories": m["matched_categories"],
            "severity": m["severity"],
            "investigation_headline": m["investigation_headline"],
            "root_cause_evidence": m["root_cause_evidence"],
            "log_or_source_reference": m["log_or_source_reference"],
            "recommended_human_action": m["recommended_human_action"],
            "resource_id": m["resource_id"],
        })
    return rows


def patches_csv_rows(snapshot):
    rows = []
    for c in snapshot["cycles"]["maintenance_cycles"]:
        rows.append({
            "record_kind": c["type"],
            "machine_name": c["machine_name"],
            "status_or_state": c["status"],
            "classification": c.get("maintenance_scope") or "MaintenanceCycle",
            "kb_id": "",
            "patch_or_cycle_name": c.get("maintenance_configuration_name") or c.get("name") or c["type"],
            "version": "",
            "reboot_info": "",
            "start_utc": c.get("start_utc") or "",
            "end_or_modified_utc": c.get("end_utc") or "",
            "reference_id": c.get("correlation_id") or c["resource_id"],
        })
    for i in snapshot["cycles"]["installation_runs"]:
        rows.append({
            "record_kind": "patch_installation_run",
            "machine_name": i["machine_name"],
            "status_or_state": i["status"],
            "classification": "InstallationRun",
            "kb_id": "",
            "patch_or_cycle_name": "installed=" + str(i["installed_patch_count"]) + ",failed=" + str(i["failed_patch_count"]) + ",notSelected=" + str(i["not_selected_patch_count"]),
            "version": "",
            "reboot_info": i["reboot_status"],
            "start_utc": i.get("start_utc") or "",
            "end_or_modified_utc": i.get("last_modified_utc") or "",
            "reference_id": i.get("maintenance_run_id") or i["resource_id"],
        })
    for p in snapshot["patches"]["combined"]:
        rows.append({
            "record_kind": p["record_kind"],
            "machine_name": p["machine_name"],
            "status_or_state": p["installation_state"],
            "classification": p["primary_classification"],
            "kb_id": p["kb_id"],
            "patch_or_cycle_name": p["patch_name"],
            "version": p["version"],
            "reboot_info": p["reboot_behavior"],
            "start_utc": p.get("published_utc") or "",
            "end_or_modified_utc": p.get("last_modified_utc") or "",
            "reference_id": p["resource_id"],
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
    if OUTPUT_DIRECTORY != "patching-investigation-reports":
        raise EvidenceError("unsafe_artifact_directory", "Only the fixed patching-investigation-reports child directory is allowed.", "artifact_storage")
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
        "machines_csv_path": "-machines.csv",
        "patches_csv_path": "-patches.csv",
    }
    if set(paths) != set(suffixes):
        raise EvidenceError("unsafe_sharing_path", "Native delivery requires exactly the four guarded report artifacts.", "artifact_storage")
    stem = paths["report_path"].name.removesuffix(".html")
    if not re.fullmatch(r"patch-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12}", stem):
        raise EvidenceError("unsafe_sharing_path", "Native aliases require this tool's generated patch-<timestamp>-<hash> filenames.", "artifact_storage")
    expected = root / "patching-investigation-reports"
    aliases = {}
    for key, path in paths.items():
        if path.parent != expected or path.name != stem + suffixes[key]:
            raise EvidenceError("unsafe_sharing_path", "Native aliases must reference the same run in the fixed report directory.", "artifact_storage")
        aliases[key.removesuffix("_path") + "_url"] = (
            "/api/files/tmp/ThreadFiles/" + match[1] + "/patching-investigation-reports/" + quote(path.name, safe="")
        )
    return {**result, "sharing_mode": "native_ui", **aliases}


def report_envelope(snapshot, paths, root):
    partial = any(s["status"] != "complete" for s in snapshot["sources"])
    s = snapshot["summary"]
    result = {
        "status": "partial" if partial else "ok",
        "operation": "report",
        "artifact_status": "written",
        **sharing_fields(root, paths),
        "collection": collection_disclosure(snapshot),
        "summary": {
            "machines_total": s["machines_total"],
            "azure_vms_total": s["azure_vms_total"],
            "arc_machines_total": s["arc_machines_total"],
            "assessed_machines_total": s["assessed_machines_total"],
            "machines_with_blockers_total": s["machines_with_blockers_total"],
            "diagnostic_findings_total": s["diagnostic_findings_total"],
            "maintenance_cycles_succeeded": s["maintenance_cycles_succeeded"],
            "maintenance_cycles_unresponsive": s["maintenance_cycles_unresponsive"],
            "installation_runs_in_window": s["installation_runs_in_window"],
            "pending_security_or_critical_patches": s["pending_security_or_critical_patches"],
            "pending_rollup_patches": s["pending_rollup_patches"],
            "category_counts": s["category_counts"],
        },
        **{key: str(path) for key, path in paths.items()},
    }
    return ensure_response(result)


def write_report(snapshot):
    root, directory = artifact_directory()
    reference = snapshot["reference_utc"].replace(":", "").replace("-", "")
    prefix = "patch-" + reference + "-" + uuid4().hex[:12]
    paths = {
        key: directory / (prefix + suffix)
        for key, suffix in (
            ("report_path", ".html"),
            ("snapshot_path", "-snapshot.json"),
            ("machines_csv_path", "-machines.csv"),
            ("patches_csv_path", "-patches.csv"),
        )
    }
    response = report_envelope(snapshot, paths, root)
    snapshot_document = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    if json.loads(snapshot_document) != snapshot:
        raise EvidenceError("round_trip_failed", "Full normalized export does not round-trip.", "artifact_storage")
    documents = {
        "report_path": render_html(snapshot),
        "snapshot_path": snapshot_document,
        "machines_csv_path": csv_document(
            machines_csv_rows(snapshot),
            (
                "machine_name", "hosting", "resource_group", "location", "os_type", "os_name",
                "power_or_arc_state", "agent_version", "last_status_change_utc", "patch_mode",
                "assessment_mode", "assessment_status", "vm_guest_patch_readiness", "reboot_pending",
                "pending_security_or_critical", "pending_update_rollup", "pending_total",
                "maintenance_cycles_succeeded", "maintenance_cycles_unresponsive",
                "installations_in_window", "failed_extensions_count", "failure_category",
                "matched_categories", "severity", "investigation_headline", "root_cause_evidence",
                "log_or_source_reference", "recommended_human_action", "resource_id",
            ),
        ),
        "patches_csv_path": csv_document(
            patches_csv_rows(snapshot),
            (
                "record_kind", "machine_name", "status_or_state", "classification", "kb_id",
                "patch_or_cycle_name", "version", "reboot_info", "start_utc",
                "end_or_modified_utc", "reference_id",
            ),
        ),
    }
    encoded = {key: value.encode("utf-8-sig" if key.endswith("csv_path") else "utf-8") for key, value in documents.items()}
    if any(len(value) > ARTIFACT_BYTES for value in encoded.values()):
        raise EvidenceError("artifact_size_exceeded", "Complete artifacts exceed 4800000 bytes; no records were dropped and no files were written.", "artifact_storage")
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
            raise EvidenceError("artifact_readback_failed", "Written full normalized JSON differs from source-normalized data.", "artifact_storage")
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
        raise EvidenceError("artifact_write_failed", "Could not atomically write/read back all four files; partial files were removed.", "artifact_storage") from exc
    return response


def main(
    operation: str = "report",
    period: str = "last_30d",
    view: str = "summary",
    hosting: str = "all",
    failure_category: str = "all",
    machine_name: str = "",
    limit: int = 25,
    offset: int = 0,
) -> dict:
    """Collect Azure Update Manager post-patching evidence and automated per-machine root-cause investigation."""
    try:
        params = validate_parameters(
            operation, period, view, hosting, failure_category, machine_name, limit, offset
        )
        config = validate_config()
        if HTML_TEMPLATE.count("__REPORT_DATA_JSON__") != 1:
            raise EvidenceError("template_missing", "Use the build-generated standalone tool with embedded HTML_TEMPLATE.", "renderer")
        reference = utc_now()
        deadline = time.monotonic() + MAX_COLLECTION_SECONDS
        raw = collect_live(config, params["period"], reference, deadline=deadline)
        snapshot = finish_snapshot(raw, reference, provenance="LIVE", environment="PRODUCTION")
        return query_snapshot(snapshot, params) if operation == "query" else write_report(snapshot)
    except EvidenceError as exc:
        return ensure_response({
            "status": "error",
            "error": exc.public(),
            "artifact_status": "cleanup_failed" if exc.code == "artifact_cleanup_failed" else "not_written",
            "provenance": "LIVE",
        })

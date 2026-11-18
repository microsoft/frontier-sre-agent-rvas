"""Bounded read-only Service Health adapter; build_tool.py embeds the report UI."""

import base64
import binascii
import copy
import csv
import hashlib
import html
import io
import json
import os
import re
import tempfile
import time
from datetime import datetime, timedelta, timezone
from http.client import HTTPException
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import UUID, uuid4


SUBSCRIPTION_ID = "<APPROVED_SUBSCRIPTION_ID>"
TENANT_ID = "<APPROVED_TENANT_ID>"
MANAGED_IDENTITY_CLIENT_ID = "<APPROVED_UAMI_CLIENT_ID>"
CLIENT_NAME = "Customer"
# Here goes the customer's logo, privately configured as a validated PNG/JPEG
# data URI. Keep generic Git source empty. Use adjacent strings <10K per line.
COMPANY_LOGO_DATA_URI = ""
COMPANY_LOGO_ALT_TEXT = "Customer logo"

API_VERSION = "2025-05-01"
ORIGIN = "https://management.azure.com"
OUTPUT_DIRECTORY = "service-health-reports"
ARTIFACT_BYTES = 4_800_000
TRANSPORT_BYTES = 3_500
MAX_LOGO_BYTES = 100_000
MAX_LOGO_DIMENSION = 2048
RETAINED_LOOKBACK_DAYS = 365
MAX_REQUESTED_DAYS = 93
MAX_PAGES = 25
MAX_SOURCE_RECORDS = 5_000
MAX_EVENT_RECORDS = 500
MAX_RESPONSE_BYTES = 20_000_000
MAX_HTTP_ATTEMPTS = 250
MAX_COLLECTION_SECONDS = 180
MAX_JSON_DEPTH = 50
EVENT_TYPES = ("ServiceIssue", "PlannedMaintenance")
TEMPORAL_SCOPES = ("all", "requested_updates", "active_now", "future_maintenance")
COMPLETE_SOURCE_STATUSES = ("complete", "successful_empty", "successful_empty_in_scope")

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
    def __init__(self, code, message, source="validation", http_status=None, receipt=None):
        super().__init__(message)
        self.code = code
        self.source = source
        self.http_status = http_status
        self.receipt = receipt

    def document(self):
        result = {"code": self.code, "source": self.source, "message": str(self)}
        if self.http_status is not None:
            result["http_status"] = self.http_status
        return result


def utc_now():
    return datetime.now(timezone.utc)


def iso(value):
    value = value.astimezone(timezone.utc)
    return value.isoformat(timespec="microseconds" if value.microsecond else "seconds").replace("+00:00", "Z")


def json_text(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def decode_json(data):
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON object key.")
            result[key] = value
        return result

    def reject_constant(value):
        raise ValueError("Nonfinite JSON constant.")

    result = json.loads(data, object_pairs_hook=unique_object, parse_constant=reject_constant)
    pending = [(result, 0)]
    while pending:
        item, depth = pending.pop()
        if depth > MAX_JSON_DEPTH:
            raise ValueError("JSON nesting exceeds its explicit bound.")
        if isinstance(item, dict):
            for key in item:
                key.encode("utf-8")
            pending.extend((value, depth + 1) for value in item.values())
        elif isinstance(item, list):
            pending.extend((value, depth + 1) for value in item)
        elif isinstance(item, str):
            item.encode("utf-8")
        elif isinstance(item, float) and not (-float("inf") < item < float("inf")):
            raise ValueError("Nonfinite JSON number.")
    return result


def response_bytes(value):
    return len(json.dumps(value).encode("utf-8"))


def budget_response(value):
    if response_bytes(value) > TRANSPORT_BYTES:
        raise EvidenceError("response_size_exceeded", "Default-serialized tool result exceeds 3500 bytes; no truncated result is returned.", "transport")
    return value


def configured_guid(value, name):
    try:
        valid = isinstance(value, str) and str(UUID(value)) == value.lower() and UUID(value).int != 0
    except (ValueError, AttributeError):
        valid = False
    if not valid:
        raise EvidenceError("configuration_required", "Set a real fixed " + name + " in the administrator-owned code before authentication.", "configuration")
    return value.lower()


def plain_text(value, field, maximum, empty=False):
    if not isinstance(value, str) or len(value) > maximum or (not empty and not value.strip()) or re.search(r"[\x00-\x1f\x7f\ud800-\udfff]", value):
        raise EvidenceError("invalid_parameter", field + " must be bounded plain text.", "parameters")
    return value.strip()


def configuration():
    config = {
        "subscription_id": configured_guid(SUBSCRIPTION_ID, "SUBSCRIPTION_ID"),
        "tenant_id": configured_guid(TENANT_ID, "TENANT_ID"),
        "client_id": configured_guid(MANAGED_IDENTITY_CLIENT_ID, "MANAGED_IDENTITY_CLIENT_ID"),
    }
    try:
        config["client_name"] = plain_text(CLIENT_NAME, "CLIENT_NAME", 120)
    except EvidenceError as exc:
        raise EvidenceError("invalid_branding", "CLIENT_NAME must contain 1 to 120 plain characters.", "branding") from exc
    return config


def logo_markup():
    try:
        alt = plain_text(COMPANY_LOGO_ALT_TEXT, "COMPANY_LOGO_ALT_TEXT", 120)
    except EvidenceError as exc:
        raise EvidenceError("invalid_company_logo", "Provide descriptive customer-logo alt text of 1 to 120 plain characters.", "branding") from exc
    if COMPANY_LOGO_DATA_URI == "":
        return '<span class="logo-placeholder">Customer logo</span>'
    if not isinstance(COMPANY_LOGO_DATA_URI, str):
        raise EvidenceError("invalid_company_logo", "The optional logo must be a PNG/JPEG base64 data URI.", "branding")
    if len(COMPANY_LOGO_DATA_URI) > ((MAX_LOGO_BYTES + 2) // 3) * 4 + 32:
        raise EvidenceError("invalid_company_logo", "Logo exceeds the 100000-byte raster bound.", "branding")
    match = re.fullmatch(r"data:image/(png|jpeg);base64,([A-Za-z0-9+/]+={0,2})", COMPANY_LOGO_DATA_URI)
    if match is None:
        raise EvidenceError("invalid_company_logo", "Only an embedded PNG/JPEG is allowed; no remote URL or SVG.", "branding")
    try:
        data = base64.b64decode(match[2], validate=True)
    except (ValueError, binascii.Error) as exc:
        raise EvidenceError("invalid_company_logo", "Logo base64 is invalid.", "branding") from exc
    if not 1 <= len(data) <= MAX_LOGO_BYTES:
        raise EvidenceError("invalid_company_logo", "Logo must contain 1 to 100000 raster bytes.", "branding")
    try:
        from PIL import Image, UnidentifiedImageError
    except ImportError as exc:
        raise EvidenceError("dependency_missing", "Configured branding requires Pillow raster validation.", "branding") from exc
    try:
        with Image.open(io.BytesIO(data), formats=["PNG", "JPEG"]) as image:
            width, height = image.size
            if (
                image.format != ("PNG" if match[1] == "png" else "JPEG")
                or not 1 <= width <= MAX_LOGO_DIMENSION
                or not 1 <= height <= MAX_LOGO_DIMENSION
                or getattr(image, "n_frames", 1) != 1
            ):
                raise EvidenceError("invalid_company_logo", "Use one frame, matching PNG/JPEG MIME, at most 2048 by 2048 pixels.", "branding")
            image.verify()
        with Image.open(io.BytesIO(data), formats=["PNG", "JPEG"]) as image:
            image.load()
    except (OSError, ValueError, SyntaxError, UnidentifiedImageError, Image.DecompressionBombError) as exc:
        raise EvidenceError("invalid_company_logo", "The logo is not a complete valid raster.", "branding") from exc
    return (
        '<img src="' + html.escape(COMPANY_LOGO_DATA_URI, quote=True) + '" alt="'
        + html.escape(alt, quote=True) + '" width="' + str(width) + '" height="' + str(height) + '">'
    )


def parse_utc(value, field):
    if not isinstance(value, str) or len(value) > 40:
        raise EvidenceError("invalid_time", field + " must be an ISO 8601 UTC timestamp.", "parameters")
    fraction = re.search(r"\.(\d+)", value)
    if fraction is not None and any(char != "0" for char in fraction[1][6:]):
        raise EvidenceError("invalid_time", field + " supports at most microsecond precision; no sub-microsecond input is rounded silently.", "parameters")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EvidenceError("invalid_time", field + " must be an ISO 8601 UTC timestamp.", "parameters") from exc
    if result.tzinfo is None or result.utcoffset() != timedelta(0):
        raise EvidenceError("invalid_time", field + " requires Z or an explicit zero UTC offset.", "parameters")
    return result.astimezone(timezone.utc)


def parameters(operation, period, start_utc, end_utc, view, event_type, state, time_scope, search, limit, offset, reference):
    enums = {
        "operation": (operation, ("report", "query")),
        "period": (period, ("auto", "previous_month", "last_24h", "last_7d", "custom")),
        "view": (view, ("summary", "events", "resources", "coverage")),
        "event_type": (event_type, ("all", *EVENT_TYPES)),
        "state": (state, ("all", "Active", "Resolved", "Unknown")),
        "time_scope": (time_scope, TEMPORAL_SCOPES),
    }
    for field, (value, allowed) in enums.items():
        if not isinstance(value, str) or value not in allowed:
            raise EvidenceError("invalid_parameter", field + " must be one of its documented values.", "parameters")
    if type(limit) is not int or not 1 <= limit <= 50 or type(offset) is not int or not 0 <= offset <= 10_000:
        raise EvidenceError("invalid_parameter", "limit requires int 1-50 and offset int 0-10000; booleans/floats are rejected.", "parameters")
    search = plain_text(search, "search", 160, empty=True)
    if operation == "report" and (view != "summary" or event_type != "all" or state != "all" or time_scope != "all" or search or limit != 10 or offset != 0):
        raise EvidenceError("invalid_combination", "Report mode retains all collected evidence; use default query-only filters and paging.", "parameters")
    if view in ("summary", "coverage") and (event_type != "all" or state != "all" or time_scope != "all" or search):
        raise EvidenceError("invalid_combination", "Event filters apply only to events/resources, not summary/coverage.", "parameters")
    selected = ("previous_month" if operation == "report" else "last_24h") if period == "auto" else period
    if selected == "custom":
        start, end = parse_utc(start_utc, "start_utc"), parse_utc(end_utc, "end_utc")
    else:
        if start_utc != "" or end_utc != "":
            raise EvidenceError("invalid_combination", "start_utc/end_utc are accepted only with period=custom.", "parameters")
        if selected == "previous_month":
            end = reference.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            start = (end - timedelta(days=1)).replace(day=1)
        else:
            end = reference
            start = end - timedelta(days=1 if selected == "last_24h" else 7)
    if not start < end <= reference or end - start > timedelta(days=MAX_REQUESTED_DAYS) or start < reference - timedelta(days=RETAINED_LOOKBACK_DAYS):
        raise EvidenceError("invalid_window", "Request a past UTC window of at most 93 days within the 365-day retained-source lookback.", "parameters")
    return {
        "operation": operation, "view": view, "event_type": event_type, "state": state,
        "time_scope": time_scope, "search": search, "limit": limit, "offset": offset,
        "window": {"period": selected, "start_utc": iso(start), "end_utc_exclusive": iso(end), "basis": "lastUpdateTime"},
        "source_query_start_utc": iso(reference - timedelta(days=RETAINED_LOOKBACK_DAYS)),
    }


def events_url(config, query_start):
    query = urlencode({"api-version": API_VERSION, "queryStartTime": query_start})
    return ORIGIN + "/subscriptions/" + config["subscription_id"] + "/providers/Microsoft.ResourceHealth/events?" + query


def resources_url(config, tracking_id):
    if not isinstance(tracking_id, str) or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", tracking_id) is None:
        raise EvidenceError("invalid_event_identity", "Event name cannot be used as a bounded native event path.", "source_scope")
    return (
        ORIGIN + "/subscriptions/" + config["subscription_id"]
        + "/providers/Microsoft.ResourceHealth/events/" + quote(tracking_id, safe="")
        + "/impactedResources?api-version=" + API_VERSION
    )


def query_pairs(url, source):
    try:
        pairs = parse_qsl(urlsplit(url).query, keep_blank_values=True, strict_parsing=True)
    except ValueError as exc:
        raise EvidenceError("unsafe_source_url", "Source URL has malformed query parameters.", source) from exc
    result = {}
    for key, value in pairs:
        key = key.casefold()
        if key in result:
            raise EvidenceError("unsafe_source_url", "Source URL repeats a query parameter.", source)
        result[key] = value
    return result


def validate_request(url, config):
    if not isinstance(url, str) or len(url) > 16_000 or re.search(r"[\x00-\x20\x7f\\]|%(?![0-9A-Fa-f]{2})", url):
        raise EvidenceError("unsafe_source_url", "Source URL is not a bounded HTTPS native request.", "source_scope")
    try:
        parsed = urlsplit(url)
    except ValueError as exc:
        raise EvidenceError("unsafe_source_url", "Source URL has an invalid authority.", "source_scope") from exc
    prefix = "/subscriptions/" + config["subscription_id"] + "/providers/Microsoft.ResourceHealth/events"
    if parsed.scheme != "https" or parsed.netloc.casefold() != "management.azure.com" or parsed.fragment:
        raise EvidenceError("unsafe_source_url", "Only the fixed ARM origin is allowed; no redirects or credentials in URLs.", "source_scope")
    decoded = unquote(parsed.path)
    if decoded != parsed.path or "\\" in decoded or any(part in (".", "..") for part in decoded.split("/")):
        raise EvidenceError("unsafe_source_url", "Encoded paths, traversal and alternate separators are forbidden.", "source_scope")
    query = query_pairs(url, "source_scope")
    continuation = {"$skiptoken", "skiptoken"}
    if query.get("api-version") != API_VERSION or any(not query[key] for key in continuation & query.keys()):
        raise EvidenceError("unsafe_source_url", "Native API version and nonempty continuation are required.", "source_scope")
    if parsed.path == prefix:
        if set(query) - continuation != {"api-version", "querystarttime"}:
            raise EvidenceError("unsafe_source_url", "Only the native subscription feed with explicit queryStartTime is allowed; categories are selected locally.", "source_scope")
        parse_utc(query["querystarttime"], "queryStartTime")
    elif re.fullmatch(re.escape(prefix) + r"/[A-Za-z0-9][A-Za-z0-9_-]{0,127}/impactedResources", parsed.path):
        if set(query) - continuation != {"api-version"}:
            raise EvidenceError("unsafe_source_url", "Impacted-resource requests accept only the fixed API version and continuation.", "source_scope")
    else:
        raise EvidenceError("unsafe_source_url", "Only configured subscription events and their impactedResources may be read.", "source_scope")


def next_link(link, initial, config):
    if not isinstance(link, str) or len(link) > 16_000:
        raise EvidenceError("invalid_pagination", "Continuation must be a bounded native URL.", "pagination")
    query, required = query_pairs(link, "pagination"), query_pairs(initial, "pagination")
    if query.get("api-version") != required["api-version"]:
        raise EvidenceError("invalid_pagination", "Continuation changed/omitted the fixed API version.", "pagination")
    if "querystarttime" in required and "querystarttime" not in query:
        try:
            parts = urlsplit(link)
        except ValueError as exc:
            raise EvidenceError("invalid_pagination", "Continuation has an invalid authority.", "pagination") from exc
        pairs = parse_qsl(parts.query, keep_blank_values=True, strict_parsing=True)
        pairs.append(("queryStartTime", required["querystarttime"]))
        link = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(pairs), parts.fragment))
        query["querystarttime"] = required["querystarttime"]
    validate_request(link, config)
    current, original = urlsplit(link), urlsplit(initial)
    if current.path != original.path:
        raise EvidenceError("invalid_pagination", "Continuation changed the source resource path.", "pagination")
    if any(query.get(key) != value for key, value in required.items()) or set(query) - set(required) - {"$skiptoken", "skiptoken"}:
        raise EvidenceError("invalid_pagination", "Continuation changed/omitted query scope or added an unsupported parameter.", "pagination")
    if "$skiptoken" in query and "skiptoken" in query:
        raise EvidenceError("invalid_pagination", "Continuation supplied ambiguous skip tokens.", "pagination")
    return link


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class NativeReader:
    def __init__(self, config):
        try:
            from azure.identity import ManagedIdentityCredential, CredentialUnavailableError
            from azure.core.exceptions import ClientAuthenticationError, ServiceRequestError
        except ImportError as exc:
            raise EvidenceError("dependency_missing", "Install azure-identity; no human/CLI credential fallback is available.", "identity") from exc
        self.config = config
        self.credential = ManagedIdentityCredential(
            client_id=config["client_id"], connection_timeout=5, read_timeout=10, retry_total=0,
        )
        self.auth_errors = (CredentialUnavailableError, ClientAuthenticationError, ServiceRequestError)
        self.opener = build_opener(NoRedirect())
        self.deadline = time.monotonic() + MAX_COLLECTION_SECONDS
        self.attempt_count = 0
        self.cached_token = None

    def close(self):
        self.credential.close()

    def token(self):
        if self.cached_token is not None and self.cached_token.expires_on > time.time() + 60:
            return self.cached_token.token
        try:
            token = self.credential.get_token(ORIGIN + "/.default")
        except self.auth_errors as exc:
            raise EvidenceError("authentication_failed", "The fixed managed identity could not acquire an ARM token.", "identity") from exc
        try:
            body = token.token.split(".")[1]
            claims = decode_json(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
            claims = normalize_sidecar_claims(claims)
        except (AttributeError, IndexError, ValueError, RecursionError, binascii.Error) as exc:
            raise EvidenceError("identity_mismatch", "Managed-identity token claims could not be verified; token data is excluded.", "identity") from exc
        if not isinstance(claims, dict) or (
            str(claims.get("tid", "")).lower() != self.config["tenant_id"]
            or str(claims.get("appid", claims.get("azp", ""))).lower() != self.config["client_id"]
            or str(claims.get("aud", "")).rstrip("/") != ORIGIN
        ):
            raise EvidenceError("identity_mismatch", "Token tenant/client/audience differs from fixed configuration.", "identity")
        self.cached_token = token
        return token.token

    def get(self, url, source):
        validate_request(url, self.config)
        attempts = []
        for attempt in range(2):
            if self.attempt_count >= MAX_HTTP_ATTEMPTS or time.monotonic() >= self.deadline:
                raise EvidenceError("collection_bound", "The shared request/deadline bound was reached; remaining evidence is unavailable.", source, receipt={"attempts": attempts})
            self.attempt_count += 1
            token = self.token()
            remaining = self.deadline - time.monotonic()
            if remaining <= 0:
                raise EvidenceError("collection_bound", "The collection deadline expired during managed-identity acquisition; no ARM request was sent.", source, receipt={"attempts": attempts})
            request = Request(url, headers={"Authorization": "Bearer " + token, "Accept": "application/json"}, method="GET")
            started = iso(utc_now())
            try:
                try:
                    response = self.opener.open(request, timeout=max(0.1, min(20, remaining)))
                except HTTPError as exc:
                    response = exc
                with response:
                    status = response.code
                    request_id = response.headers.get("x-ms-request-id", "")
                    retry_after = response.headers.get("Retry-After", "")
                    chunks, length, complete = [], 0, False
                    while length <= MAX_RESPONSE_BYTES:
                        if time.monotonic() >= self.deadline:
                            attempts.append({
                                "started_at_utc": started, "finished_at_utc": iso(utc_now()),
                                "http_status": status, "body_incomplete": True, "response_bytes_observed": length,
                            })
                            raise EvidenceError("collection_bound", "The collection deadline expired while reading the native response; an incomplete body was not accepted.", source, status, {"attempts": attempts})
                        # read1 permits a deadline check between buffered network reads.
                        chunk = response.read1(min(65_536, MAX_RESPONSE_BYTES + 1 - length))
                        if not chunk:
                            complete = True
                            break
                        chunks.append(chunk)
                        length += len(chunk)
                    data = b"".join(chunks)
            except (URLError, TimeoutError, OSError, HTTPException) as exc:
                attempts.append({"started_at_utc": started, "finished_at_utc": iso(utc_now()), "http_status": None, "code": "transport_failed"})
                raise EvidenceError("transport_failed", "Native HTTPS read failed; no empty response was substituted.", source, receipt={"attempts": attempts}) from exc
            receipt = {
                "started_at_utc": started, "finished_at_utc": iso(utc_now()),
                "http_status": status, "response_bytes": len(data),
                "response_complete": complete,
                "request_id": request_id, "response_sha256": hashlib.sha256(data).hexdigest(),
            }
            attempts.append(receipt)
            if len(data) > MAX_RESPONSE_BYTES:
                raise EvidenceError("source_response_too_large", "Native response exceeds 20000000 bytes; an incomplete body was not accepted.", source, status, {"attempts": attempts})
            try:
                payload = decode_json(data)
            except (ValueError, UnicodeDecodeError, RecursionError) as exc:
                raise EvidenceError("invalid_response_json", "Native response is not valid bounded JSON; raw non-JSON bodies are excluded.", source, status, {"attempts": attempts}) from exc
            if status in (429, 500, 502, 503, 504) and attempt == 0:
                receipt["error_response"] = payload
                delay = min(int(retry_after), 2) if re.fullmatch(r"[0-9]{1,4}", retry_after) else 1
                time.sleep(min(delay, max(0, self.deadline - time.monotonic())))
                continue
            return {"http_status": status, "payload": payload, "attempts": attempts, "observed_at_utc": receipt["finished_at_utc"]}
        raise EvidenceError("source_retry_exhausted", "Native retry bound was exhausted.", source)


def source_error(code, message, source, http_status=None):
    return EvidenceError(code, message, source, http_status).document()


def record_in_scope(raw, kind, config, tracking_id=None):
    if not isinstance(raw, dict):
        return "Record is not an object."
    identity = raw.get("id")
    prefix = "/subscriptions/" + config["subscription_id"] + "/providers/Microsoft.ResourceHealth/events/"
    if not isinstance(identity, str) or "\\" in identity or "%" in identity or "?" in identity or "#" in identity or any(part in (".", "..") for part in identity.split("/")):
        return "Record has no safe native subscription identity."
    if kind == "events":
        name = raw.get("name")
        if not isinstance(name, str) or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", name) is None:
            return "Event identity is outside the fixed subscription or cannot be verified."
        accepted_ids = (
            prefix + name, "/providers/Microsoft.ResourceHealth/events/" + name,
            "Microsoft.ResourceHealth/events/" + name,
        )
        if identity.casefold() not in [candidate.casefold() for candidate in accepted_ids]:
            return "Event identity is outside the fixed subscription or cannot be verified."
        props = raw.get("properties")
        if not isinstance(props, dict) or props.get("eventType") not in EVENT_TYPES or (props.get("isEventSensitive") is not None and props.get("isEventSensitive") is not False):
            return "Event category/sensitivity is outside the fixed nonsensitive category read."
    else:
        prefixes = (
            prefix + tracking_id + "/impactedResources/",
            "/providers/Microsoft.ResourceHealth/events/" + tracking_id + "/impactedResources/",
            "Microsoft.ResourceHealth/events/" + tracking_id + "/impactedResources/",
        )
        expected = next((item for item in prefixes if identity.casefold().startswith(item.casefold())), None)
        if expected is None or not identity[len(expected):] or "/" in identity[len(expected):]:
            return "Impacted-resource record identity is outside its subscription event."
        props = raw.get("properties")
        target = props.get("targetResourceId") if isinstance(props, dict) else None
        if isinstance(target, str) and target.casefold().startswith("/subscriptions/") and not target.casefold().startswith(("/subscriptions/" + config["subscription_id"] + "/").casefold()):
            return "Published target resource belongs to a different subscription."
    return None


def charge_evidence(page, evidence_budget, source_id):
    evidence_budget["bytes"] += len(json_text(page).encode("utf-8"))
    if evidence_budget["bytes"] > ARTIFACT_BYTES:
        raise EvidenceError("collected_evidence_too_large", "Accepted source evidence alone exceeds the complete JSON artifact bound; no fields were dropped and no report files were written.", source_id)


def read_pages(reader, initial, source_id, kind, config, tracking_id=None, evidence_budget=None):
    evidence_budget = evidence_budget if evidence_budget is not None else {"bytes": 0}
    receipt = {
        "source_id": source_id, "kind": kind,
        "included_event_types": list(EVENT_TYPES) if kind == "events" else None,
        "tracking_id": tracking_id, "subscription_id": config["subscription_id"],
        "api_version": API_VERSION, "status": "not_collected",
        "initial_request_url": initial, "records_received": 0, "records_accepted": 0,
        "records_excluded_by_scope": 0, "excluded_event_types": {},
        "pages": [], "errors": [], "redactions": [],
        "pagination_complete": False, "duplicate_native_ids": 0,
    }
    rows, visited, identities = [], set(), set()
    current = initial
    limit = MAX_EVENT_RECORDS if kind == "events" else MAX_SOURCE_RECORDS
    while len(receipt["pages"]) < MAX_PAGES:
        if current in visited:
            receipt["errors"].append(source_error("pagination_loop", "A continuation repeated an already-read page.", source_id))
            break
        visited.add(current)
        page = {"page": len(receipt["pages"]) + 1, "request_method": "GET", "request_url": current}
        receipt["pages"].append(page)
        try:
            result = reader.get(current, source_id)
        except EvidenceError as exc:
            page.update(exc.receipt or {})
            page["http_status"] = exc.http_status
            receipt["errors"].append(exc.document())
            charge_evidence(page, evidence_budget, source_id)
            break
        page.update({
            "http_status": result["http_status"], "observed_at_utc": result["observed_at_utc"],
            "attempts": result["attempts"],
        })
        if result["http_status"] != 200:
            page["response"] = copy.deepcopy(result["payload"])
            receipt["errors"].append(source_error("native_http_error", "Native source returned HTTP " + str(result["http_status"]) + "; this is not an empty inventory.", source_id, result["http_status"]))
            charge_evidence(page, evidence_budget, source_id)
            break
        payload = result["payload"]
        if not isinstance(payload, dict) or not isinstance(payload.get("value"), list):
            page["response"] = copy.deepcopy(payload)
            receipt["errors"].append(source_error("invalid_list_shape", "Native list response is missing its value array.", source_id, 200))
            charge_evidence(page, evidence_budget, source_id)
            break
        page["response"] = {key: copy.deepcopy(value) for key, value in payload.items() if key != "value"}
        accepted = []
        excluded = 0
        for index, raw in enumerate(payload["value"]):
            receipt["records_received"] += 1
            props = raw.get("properties") if isinstance(raw, dict) else None
            category = props.get("eventType") if isinstance(props, dict) else None
            if kind == "events" and isinstance(category, str) and category and category not in EVENT_TYPES:
                receipt["records_excluded_by_scope"] += 1
                receipt["excluded_event_types"][category] = receipt["excluded_event_types"].get(category, 0) + 1
                excluded += 1
                continue
            reason = record_in_scope(raw, kind, config, tracking_id)
            if reason:
                receipt["redactions"].append({"page": page["page"], "record_index": index, "reason": reason})
                continue
            accepted_index = len(accepted)
            accepted.append(copy.deepcopy(raw))
            native_id = raw["id"].casefold()
            if native_id in identities:
                receipt["duplicate_native_ids"] += 1
            identities.add(native_id)
            rows.append((copy.deepcopy(raw), {
                "source_id": source_id, "page": page["page"], "record_index": accepted_index,
                "original_record_index": index, "observed_at_utc": result["observed_at_utc"],
            }))
        page["response"]["value"] = accepted
        page["records_received"] = len(payload["value"])
        page["records_accepted"] = len(accepted)
        page["records_excluded_by_scope"] = excluded
        receipt["records_accepted"] = len(rows)
        charge_evidence(page, evidence_budget, source_id)
        if len(rows) > limit:
            receipt["errors"].append(source_error("source_record_bound", "The source record bound was exceeded; accepted returned records remain in the export but coverage is partial.", source_id))
            break
        if payload.get("error") is not None:
            receipt["errors"].append(source_error("partial_response", "Native response contains an error alongside its list; returned records are retained.", source_id))
            break
        continuation = payload.get("nextLink")
        if continuation in (None, ""):
            receipt["pagination_complete"] = True
            break
        page["continuation_received"] = True
        try:
            current = next_link(continuation, initial, config)
            page["continuation_query_start_restored"] = current != continuation
        except EvidenceError as exc:
            receipt["errors"].append(exc.document())
            break
    else:
        receipt["errors"].append(source_error("source_page_bound", "The per-list 25-page bound was reached with an outstanding continuation.", source_id))
    if receipt["redactions"]:
        receipt["errors"].append(source_error("source_scope_violation", "Unexpected records were redacted from this nonsensitive subscription-only export; inspect the redaction ledger.", source_id))
    if receipt["duplicate_native_ids"]:
        receipt["errors"].append(source_error("duplicate_native_ids", "Repeated native IDs were retained as separate observations; unique-event completeness is uncertain.", source_id))
    if receipt["errors"]:
        first_status = receipt["errors"][0].get("http_status")
        not_collected = receipt["errors"][0]["code"] == "not_collected_in_replay"
        receipt["status"] = "partial" if rows else "not_collected" if not_collected else "denied" if first_status in (401, 403) else "unavailable"
    else:
        receipt["status"] = "complete" if rows else "successful_empty_in_scope" if receipt["records_excluded_by_scope"] else "successful_empty"
    return rows, receipt


def source_time(value):
    if not isinstance(value, str) or not value:
        return None
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return result.astimezone(timezone.utc) if result.tzinfo is not None else None


def clock_key(value):
    parsed = source_time(value)
    if parsed is None:
        return None
    match = re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.(\d{1,9}))?(?:Z|[+-]\d{2}:\d{2})", value)
    if match is None:
        return None
    elapsed = parsed - datetime(1970, 1, 1, tzinfo=timezone.utc)
    fraction = int(((match[1] or "") + "000000000")[:9])
    return (elapsed.days * 86_400 + elapsed.seconds) * 1_000_000_000 + fraction


def source_utc_display(value):
    if clock_key(value) is None:
        return None
    parsed = source_time(value).replace(microsecond=0)
    fraction = re.search(r"\.(\d+)", value)
    return iso(parsed).removesuffix("Z") + ("." + fraction[1] if fraction else "") + "Z"


def scalar(value):
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    return None


def normalize_event(raw, ref, params, reference, key):
    props = raw["properties"]
    uncertain = []
    times = {}
    for field in ("impactStartTime", "impactMitigationTime", "lastUpdateTime"):
        original = props.get(field)
        times[field] = clock_key(original)
        if times[field] is None:
            uncertain.append(field + " missing/invalid; original value retained.")
    status = props.get("status") if props.get("status") in ("Active", "Resolved") else "Unknown"
    if status == "Unknown":
        uncertain.append("Native current status missing/unrecognized.")
    start, end = clock_key(params["window"]["start_utc"]), clock_key(params["window"]["end_utc_exclusive"])
    reference_key = clock_key(iso(reference))
    updated = times["lastUpdateTime"]
    impact_start = times["impactStartTime"]
    mitigation = times["impactMitigationTime"]
    if impact_start is None:
        timing = "unknown"
    elif mitigation is not None and mitigation < impact_start:
        timing = "inconsistent_source_dates"
        uncertain.append("Source mitigation precedes impact start; no ongoing/future interval is established.")
    elif impact_start > reference_key:
        timing = "future_published_start"
    elif mitigation is not None and mitigation <= reference_key:
        timing = "source_mitigation_at_or_before_reference"
    elif mitigation is not None:
        timing = "between_source_start_and_mitigation"
    else:
        timing = "published_start_without_mitigation"
    if status == "Active" and timing == "source_mitigation_at_or_before_reference":
        uncertain.append("Native status is Active but source mitigation is at/before the reference; ongoing impact is not established.")
    services, regions = [], []
    impact = props.get("impact")
    if isinstance(impact, list):
        for item in impact:
            if not isinstance(item, dict):
                continue
            service = scalar(item.get("impactedService"))
            if service and service not in services:
                services.append(service)
            region_items = item.get("impactedRegions")
            if isinstance(region_items, list):
                for region_item in region_items:
                    region = scalar(region_item.get("impactedRegion")) if isinstance(region_item, dict) else None
                    if region and region not in regions:
                        regions.append(region)
    if not services:
        uncertain.append("No structured impacted service supplied.")
    if not regions:
        uncertain.append("No structured impacted region supplied.")
    if updated is not None and updated > reference_key:
        uncertain.append("lastUpdateTime is later than the run reference; the read is not an atomic as-of snapshot.")
    return {
        "event_key": key, "id": raw["id"], "tracking_id": raw["name"],
        "event_type": props["eventType"], "native_status": status,
        "title": scalar(props.get("title")) or "Untitled source event",
        "summary": scalar(props.get("summary")), "description": scalar(props.get("description")),
        "event_level": scalar(props.get("eventLevel")), "event_source": scalar(props.get("eventSource")),
        "impact_start_original": props.get("impactStartTime"), "mitigation_time_original": props.get("impactMitigationTime"),
        "last_update_original": props.get("lastUpdateTime"),
        "impact_start_utc": source_utc_display(props.get("impactStartTime")),
        "mitigation_time_utc": source_utc_display(props.get("impactMitigationTime")),
        "last_update_utc": source_utc_display(props.get("lastUpdateTime")),
        "services": services, "regions": regions, "source_ref": ref,
        "published_timing": timing,
        "temporal": {
            "requested_updates": updated is not None and start <= updated < end,
            "active_now": status == "Active",
            "future_maintenance": props["eventType"] == "PlannedMaintenance" and status != "Resolved" and timing == "future_published_start",
        },
        "newness": "not_established", "support_case_reference": "not_collected",
        "uncertainties": uncertain, "resource_source_id": None, "resource_source_status": "not_collected", "resource_records": None,
    }


def normalize_resource(raw, ref, event, key):
    props = raw.get("properties") if isinstance(raw.get("properties"), dict) else {}
    target = scalar(props.get("targetResourceId"))
    return {
        "resource_key": key, "event_key": event["event_key"], "event_id": event["id"],
        "tracking_id": event["tracking_id"], "id": raw["id"],
        "target_resource_id": target, "target_resource_type": scalar(props.get("targetResourceType")),
        "target_region": scalar(props.get("targetRegion")), "source_ref": ref,
        "association": "published_potential_impact", "workload_outage": "not_measured",
        "uncertainties": [] if target else ["Source supplied no targetResourceId; record retained, not a resolved resource identity."],
    }


def collect(reader, config, params, reference, provenance="LIVE"):
    sources, events, resources = [], [], []
    evidence_budget = {"bytes": 0}
    initial = events_url(config, params["source_query_start_utc"])
    rows, receipt = read_pages(reader, initial, "events:subscription", "events", config, evidence_budget=evidence_budget)
    receipt["query_start_utc"] = params["source_query_start_utc"]
    receipt["time_basis"] = "lastUpdateTime lower bound; no source upper-bound/as-of guarantee"
    sources.append(receipt)
    for raw, ref in rows:
        events.append(normalize_event(raw, ref, params, reference, "event-" + str(len(events) + 1)))
    resource_receipts = {}
    for event in events:
        identity = event["tracking_id"].casefold()
        if identity not in resource_receipts:
            source_id = "resources:" + event["tracking_id"]
            rows, receipt = read_pages(reader, resources_url(config, event["tracking_id"]), source_id, "impactedResources", config, event["tracking_id"], evidence_budget)
            sources.append(receipt)
            resource_receipts[identity] = (rows, receipt)
        rows, receipt = resource_receipts[identity]
        event["resource_source_id"] = receipt["source_id"]
        event["resource_source_status"] = receipt["status"]
        event["resource_records"] = len(rows) if receipt["status"] in COMPLETE_SOURCE_STATUSES else None
        event["resource_records_observed"] = len(rows)
        if event["resource_records"] is None:
            event["uncertainties"].append("Impacted-resource source is incomplete; observed rows are a lower bound, not zero/full scope.")
        for raw, ref in rows:
            resources.append(normalize_resource(raw, ref, event, "resource-" + str(len(resources) + 1)))
    event_sources = [source for source in sources if source["kind"] == "events"]
    all_complete = all(source["status"] in COMPLETE_SOURCE_STATUSES for source in sources)
    observed_times = [page["observed_at_utc"] for source in sources for page in source["pages"] if "observed_at_utc" in page]
    updates = [(clock_key(event["last_update_original"]), event["last_update_original"]) for event in events if clock_key(event["last_update_original"]) is not None]
    return {
        "schema_version": "service-health-events-v1", "provenance": provenance,
        "client_name": config["client_name"], "subscription_id": config["subscription_id"],
        "reference_utc": iso(reference), "requested_window": params["window"],
        "collection_observed_utc": {"first": min(observed_times) if observed_times else None, "last": max(observed_times) if observed_times else None},
        "observed_last_update_extent": {
            "first_original": min(updates, key=lambda item: item[0])[1] if updates else None,
            "last_original": max(updates, key=lambda item: item[0])[1] if updates else None,
            "records_with_valid_time": len(updates), "missing_or_invalid": len(events) - len(updates),
            "meaning": "Extent of accepted observed records, not complete historical coverage.",
        },
        "source_query": {
            "query_start_utc": params["source_query_start_utc"], "basis": "lastUpdateTime",
            "lookback_days": (reference - source_time(params["source_query_start_utc"])).total_seconds() / 86_400,
            "upper_bound": "not_supported", "category_selection": "Fixed client-side ServiceIssue / PlannedMaintenance; no unsupported eventType OData filter.",
            "retention": "Portal history 90 days; backend up to one year, not a completeness guarantee.",
            "active_scope": "Source-observed current Active records within returned retained data, regardless of impact-start month.",
        },
        "coverage": {
            "status": "complete_returned_pages" if all_complete else "partial",
            "historical_completeness": "not_proven", "current_state_as_of_history": "not_reconstructed",
            "newness": "not_established_without_baseline_or_reliable_publication_time",
            "event_source_successful_empty": all(source["status"] in ("successful_empty", "successful_empty_in_scope") for source in event_sources),
            "empty_meaning": "Successful-empty source validation only; no resilience or workload-health claim.",
            "support_cases": "not_collected", "workload_outages": "not_measured",
            "redacted_records": sum(len(source["redactions"]) for source in sources),
            "excluded_category_records": sum(source["records_excluded_by_scope"] for source in event_sources),
        },
        "events": events, "impacted_resources": resources, "sources": sources,
    }


def summary(snapshot):
    events = snapshot["events"]
    return {
        "event_records": len(events), "distinct_event_ids": len({event["id"].casefold() for event in events}),
        "native_event_records_received": sum(source["records_received"] for source in snapshot["sources"] if source["kind"] == "events"),
        "excluded_category_records": snapshot["coverage"]["excluded_category_records"],
        "service_issue_records": sum(event["event_type"] == "ServiceIssue" for event in events),
        "planned_maintenance_records": sum(event["event_type"] == "PlannedMaintenance" for event in events),
        "requested_update_records": sum(event["temporal"]["requested_updates"] for event in events),
        "active_observed_records": sum(event["temporal"]["active_now"] for event in events),
        "future_maintenance_records": sum(event["temporal"]["future_maintenance"] for event in events),
        "impacted_resource_records": len(snapshot["impacted_resources"]),
        "incomplete_sources": sum(source["status"] not in COMPLETE_SOURCE_STATUSES for source in snapshot["sources"]),
    }


def matches(event, params):
    if params["event_type"] != "all" and event["event_type"] != params["event_type"]:
        return False
    if params["state"] != "all" and event["native_status"] != params["state"]:
        return False
    if params["time_scope"] != "all" and not event["temporal"][params["time_scope"]]:
        return False
    haystack = " ".join([event["id"], event["tracking_id"], event["title"], event["summary"] or "", *event["services"], *event["regions"]])
    return params["search"].casefold() in haystack.casefold()


def event_projection(event):
    return {key: event[key] for key in (
        "event_key", "tracking_id", "event_type", "native_status", "title", "last_update_original",
        "impact_start_original", "temporal", "resource_records", "resource_records_observed", "newness", "source_ref",
        "published_timing", "resource_source_id", "resource_source_status",
    )}


def query_snapshot(snapshot, params):
    selected = [event for event in snapshot["events"] if matches(event, params)]
    if params["view"] == "summary":
        rows = [summary(snapshot)]
    elif params["view"] == "events":
        rows = [event_projection(event) for event in selected]
    elif params["view"] == "resources":
        keys = {event["event_key"] for event in selected}
        rows = [row for row in snapshot["impacted_resources"] if row["event_key"] in keys]
    else:
        rows = [{
            "source_id": source["source_id"], "status": source["status"], "records_received": source["records_received"],
            "records_accepted": source["records_accepted"], "pages_attempted": len(source["pages"]),
            "pagination_complete": source["pagination_complete"], "errors": source["errors"],
            "redacted_records": len(source["redactions"]),
            "records_excluded_by_scope": source["records_excluded_by_scope"], "excluded_event_types": source["excluded_event_types"],
        } for source in snapshot["sources"]]
    result = {
        "status": "partial" if snapshot["coverage"]["status"] == "partial" else "ok",
        "operation": "query", "view": params["view"], "provenance": snapshot["provenance"],
        "reference_utc": snapshot["reference_utc"], "requested_window": snapshot["requested_window"],
        "source_query_start_utc": snapshot["source_query"]["query_start_utc"],
        "collection_observed_utc": snapshot["collection_observed_utc"],
        "historical_completeness": "not_proven", "fresh_collection": True,
        "total_matched": len(rows), "requested_limit": params["limit"], "offset": params["offset"],
        "returned": 0, "has_more": False, "next_offset": None, "transport_capped": False, "rows": [],
    }
    desired = rows[params["offset"]:params["offset"] + params["limit"]]
    for row in desired:
        proposed = copy.deepcopy(result)
        proposed["rows"].append(row)
        proposed["returned"] += 1
        consumed = params["offset"] + proposed["returned"]
        proposed["has_more"] = consumed < len(rows)
        proposed["next_offset"] = consumed if proposed["has_more"] else None
        proposed["transport_capped"] = proposed["returned"] < len(desired)
        if response_bytes(proposed) > TRANSPORT_BYTES:
            if not result["rows"]:
                raise EvidenceError("query_row_too_large", "One complete projected row exceeds the chat budget. Request a report and inspect its complete JSON; no zero-row cursor is returned.", "transport")
            result["transport_capped"] = True
            break
        result = proposed
    return budget_response(result)


def source_record(snapshot, ref):
    source = next(item for item in snapshot["sources"] if item["source_id"] == ref["source_id"])
    page = source["pages"][ref["page"] - 1]
    return page["response"]["value"][ref["record_index"]]


def complete_event(snapshot, event):
    return {**event, "source_record": source_record(snapshot, event["source_ref"])}


def complete_resource(snapshot, resource):
    return {**resource, "source_record": source_record(snapshot, resource["source_ref"])}


EVENT_CSV_FIELDS = (
    "provenance", "subscription_id", "api_version", "reference_utc", "event_feed_query_start_utc", "requested_start_utc", "requested_end_utc_exclusive",
    "event_key", "id", "tracking_id", "event_type", "native_status", "published_timing", "title", "event_level",
    "services", "regions", "impact_start_original", "mitigation_time_original", "last_update_original",
    "requested_updates", "active_observed", "future_maintenance", "newness", "resource_records",
    "resource_records_observed", "resource_source_id", "resource_source_status", "source_id", "observed_at_utc", "details_json",
)
RESOURCE_CSV_FIELDS = (
    "provenance", "subscription_id", "api_version", "reference_utc", "event_feed_query_start_utc", "requested_start_utc", "requested_end_utc_exclusive",
    "resource_key", "id", "event_key", "tracking_id", "target_resource_id", "target_resource_type", "target_region",
    "association", "workload_outage", "source_id", "observed_at_utc", "details_json",
)


def csv_cell(value):
    if value is None:
        return ""
    text = json_text(value) if isinstance(value, (dict, list, bool)) else str(value)
    if text.startswith(("\t", "\r", "\n")) or text.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + text
    return text


def csv_document(rows, fields):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\r\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({field: csv_cell(row.get(field)) for field in fields})
    return stream.getvalue()


def csv_rows(snapshot):
    context = {
        "provenance": snapshot["provenance"], "subscription_id": snapshot["subscription_id"], "api_version": API_VERSION,
        "reference_utc": snapshot["reference_utc"], "event_feed_query_start_utc": snapshot["source_query"]["query_start_utc"],
        "requested_start_utc": snapshot["requested_window"]["start_utc"],
        "requested_end_utc_exclusive": snapshot["requested_window"]["end_utc_exclusive"],
    }
    events = [{
        **context, **event, "services": event["services"], "regions": event["regions"],
        "requested_updates": event["temporal"]["requested_updates"], "active_observed": event["temporal"]["active_now"],
        "future_maintenance": event["temporal"]["future_maintenance"],
        "source_id": event["source_ref"]["source_id"], "observed_at_utc": event["source_ref"]["observed_at_utc"],
        "details_json": complete_event(snapshot, event),
    } for event in snapshot["events"]]
    resources = [{
        **context, **resource, "source_id": resource["source_ref"]["source_id"],
        "observed_at_utc": resource["source_ref"]["observed_at_utc"], "details_json": complete_resource(snapshot, resource),
    } for resource in snapshot["impacted_resources"]]
    return events, resources


def safe_script_json(value):
    return json_text(value).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


def json_byte_ranges(snapshot, document, requested_paths):
    paths = set(requested_paths)
    prefixes = {path[:length] for path in paths for length in range(len(path) + 1)}
    chunks, ranges, position = [], {}, 0

    def emit(value):
        nonlocal position
        chunks.append(value)
        position += len(value)

    def walk(value, path=()):
        if len(path) > 100:
            raise EvidenceError("json_reference_depth", "Source JSON references exceed the bounded nesting depth.", "artifact_encoding")
        start = position
        if path not in prefixes:
            emit(json_text(value).encode("utf-8"))
        elif isinstance(value, dict):
            emit(b"{")
            for index, (key, child) in enumerate(value.items()):
                if index:
                    emit(b",")
                emit(json_text(key).encode("utf-8") + b":")
                walk(child, (*path, key))
            emit(b"}")
        elif isinstance(value, list):
            emit(b"[")
            for index, child in enumerate(value):
                if index:
                    emit(b",")
                walk(child, (*path, index))
            emit(b"]")
        else:
            emit(json_text(value).encode("utf-8"))
        if path in paths:
            ranges[path] = [start, position]

    walk(snapshot)
    if paths != ranges.keys() or b"".join(chunks) + b"\n" != document:
        raise EvidenceError("json_reference_mismatch", "Render references do not match the exact complete JSON bytes; no alternate snapshot was accepted.", "artifact_encoding")
    return ranges


def render_html(snapshot, document, branding):
    if EVENT_CSV_FIELDS[-1] != "details_json" or RESOURCE_CSV_FIELDS[-1] != "details_json":
        raise EvidenceError("invalid_csv_render_contract", "Complete CSV details must remain the final column in the render contract.", "artifact_encoding")
    event_rows, resource_rows = csv_rows(snapshot)
    source_indices = {source["source_id"]: index for index, source in enumerate(snapshot["sources"])}
    if len(source_indices) != len(snapshot["sources"]):
        raise EvidenceError("ambiguous_source_reference", "Source IDs must be unique for exact report references.", "artifact_encoding")

    def raw_path(row):
        ref = row["source_ref"]
        return ("sources", source_indices[ref["source_id"]], "pages", ref["page"] - 1, "response", "value", ref["record_index"])

    requested_paths = [("sources", index) for index in range(len(snapshot["sources"]))]
    for collection in ("events", "impacted_resources"):
        for index, row in enumerate(snapshot[collection]):
            requested_paths.extend(((collection, index), raw_path(row)))
    ranges = json_byte_ranges(snapshot, document, requested_paths)
    model = {
        "context": {key: snapshot[key] for key in ("schema_version", "provenance", "client_name", "subscription_id", "reference_utc", "requested_window", "collection_observed_utc", "observed_last_update_extent", "source_query", "coverage")},
        "summary": summary(snapshot), "events": [], "resources": [], "sources": [],
        "event_csv_fields": EVENT_CSV_FIELDS, "resource_csv_fields": RESOURCE_CSV_FIELDS,
        "source_json_bytes": len(document),
    }
    # Store source JSON once; UTF-8 byte references preserve every numeric lexeme.
    for index, (event, row) in enumerate(zip(snapshot["events"], event_rows)):
        model["events"].append({
            **event, "record_range": ranges[("events", index)], "source_record_range": ranges[raw_path(event)],
            "csv_cells": [csv_cell(row.get(field)) for field in EVENT_CSV_FIELDS if field != "details_json"],
        })
    for index, (resource, row) in enumerate(zip(snapshot["impacted_resources"], resource_rows)):
        model["resources"].append({
            **resource, "record_range": ranges[("impacted_resources", index)], "source_record_range": ranges[raw_path(resource)],
            "csv_cells": [csv_cell(row.get(field)) for field in RESOURCE_CSV_FIELDS if field != "details_json"],
        })
    for index, source in enumerate(snapshot["sources"]):
        receipt = {
            key: value for key, value in source.items() if key != "pages"
        } | {
            "pages": [{
                **{key: value for key, value in page.items() if key != "response"},
                "response_metadata": {key: value for key, value in page["response"].items() if key != "value"}
                if isinstance(page.get("response"), dict) else page.get("response"),
            } for page in source["pages"]],
        }
        model["sources"].append({
            **receipt, "receipt_json": json_text(receipt),
            "detail_range": ranges[("sources", index)],
        })
    return (
        HTML_TEMPLATE.replace("__CLIENT_NAME__", html.escape(snapshot["client_name"], quote=True))
        .replace("__COMPANY_LOGO__", branding)
        .replace("__FULL_JSON_BASE64__", base64.b64encode(document).decode("ascii"))
        .replace("__UI_MODEL_JSON__", safe_script_json(model))
    )


def artifact_directory():
    try:
        cwd = Path.cwd()
        root = cwd.resolve(strict=True)
        linked = any(part.is_symlink() or getattr(part, "is_junction", lambda: False)() for part in (cwd, *cwd.parents))
    except (OSError, RuntimeError) as exc:
        raise EvidenceError("unsafe_artifact_root", "Runtime cwd must resolve to an existing directory.", "artifact_storage") from exc
    if root == Path(root.anchor) or not root.is_dir() or linked:
        raise EvidenceError("unsafe_artifact_root", "Root directories and symlink/junction cwd ancestors are forbidden.", "artifact_storage")
    if OUTPUT_DIRECTORY != "service-health-reports":
        raise EvidenceError("unsafe_artifact_directory", "Only the fixed service-health-reports child is allowed.", "artifact_storage")
    directory = root / OUTPUT_DIRECTORY
    if directory.is_symlink() or getattr(directory, "is_junction", lambda: False)() or directory.resolve() != directory:
        raise EvidenceError("unsafe_artifact_directory", "Output folder is a link/junction or escapes the actual cwd.", "artifact_storage")
    return root, directory


SUFFIXES = {
    "report_path": ".html", "snapshot_path": "-snapshot.json",
    "events_csv_path": "-events.csv", "resources_csv_path": "-impacted-resources.csv",
}


def sharing_fields(root, paths):
    result = {"sharing_mode": "local_files_only", "http_verified": False}
    match = re.fullmatch(r"/(?:root/sreagent|usr)/terminalRoot/tmp/ThreadFiles/([0-9a-fA-F-]{36})", root.as_posix())
    if match is None:
        return result
    try:
        if str(UUID(match[1])) != match[1].lower():
            return result
    except ValueError:
        return result
    if set(paths) != set(SUFFIXES):
        raise EvidenceError("unsafe_sharing_path", "Exactly the four generated artifacts are required.", "artifact_storage")
    stem = paths["report_path"].name.removesuffix(".html")
    if re.fullmatch(r"(?:service-health|simulated-service-health)-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12}", stem) is None:
        raise EvidenceError("unsafe_sharing_path", "Native aliases require this tool's generated filenames.", "artifact_storage")
    for key, suffix in SUFFIXES.items():
        path = paths[key]
        if path.parent != root / OUTPUT_DIRECTORY or path.name != stem + suffix:
            raise EvidenceError("unsafe_sharing_path", "Native aliases must point to one guarded run under the actual runtime cwd.", "artifact_storage")
        result[key.removesuffix("_path") + "_url"] = "/api/files/tmp/ThreadFiles/" + match[1] + "/" + OUTPUT_DIRECTORY + "/" + quote(path.name, safe="")
    result["sharing_mode"] = "native_ui"
    return result


def report_envelope(snapshot, root, paths):
    return budget_response({
        "status": "partial" if snapshot["coverage"]["status"] == "partial" else "ok",
        "operation": "report", "artifact_status": "written", "provenance": snapshot["provenance"],
        "reference_utc": snapshot["reference_utc"], "requested_window": snapshot["requested_window"],
        "source_query_start_utc": snapshot["source_query"]["query_start_utc"],
        "historical_completeness": "not_proven", "newness": "not_established",
        "empty_source_validation_only": snapshot["coverage"]["event_source_successful_empty"],
        "summary": summary(snapshot), **{key: str(path) for key, path in paths.items()},
        **sharing_fields(root, paths),
    })


def prepare_artifacts(snapshot, branding):
    text = json_text(snapshot) + "\n"
    if json.loads(text) != snapshot:
        raise EvidenceError("json_round_trip_failed", "Complete source-qualified JSON failed its round-trip check.", "artifact_encoding")
    document = text.encode("utf-8")
    event_rows, resource_rows = csv_rows(snapshot)
    files = {
        "snapshot_path": document,
        "report_path": render_html(snapshot, document, branding).encode("utf-8"),
        "events_csv_path": csv_document(event_rows, EVENT_CSV_FIELDS).encode("utf-8-sig"),
        "resources_csv_path": csv_document(resource_rows, RESOURCE_CSV_FIELDS).encode("utf-8-sig"),
    }
    if any(len(data) > ARTIFACT_BYTES for data in files.values()):
        raise EvidenceError("artifact_size_exceeded", "A complete plain artifact exceeds 4800000 bytes. No file was written, no records/window were dropped and no ZIP/Blob substitute was created.", "artifact_storage")
    return files


def write_report(snapshot, branding):
    root, directory = artifact_directory()
    prefix = "simulated-service-health" if snapshot["provenance"] == "SIMULATED" else "service-health"
    stem = prefix + "-" + snapshot["reference_utc"].replace("-", "").replace(":", "") + "-" + uuid4().hex[:12]
    paths = {key: directory / (stem + suffix) for key, suffix in SUFFIXES.items()}
    result = report_envelope(snapshot, root, paths)
    files = prepare_artifacts(snapshot, branding)
    temporary, written = [], []
    try:
        directory.mkdir(exist_ok=True)
        if artifact_directory()[1] != directory or not directory.is_dir() or directory.resolve(strict=True) != directory:
            raise EvidenceError("unsafe_artifact_directory", "Output folder changed during creation.", "artifact_storage")
        for key, data in files.items():
            if paths[key].exists() or paths[key].is_symlink():
                raise EvidenceError("artifact_collision", "A generated path already exists; no overwrite is allowed.", "artifact_storage")
            fd, filename = tempfile.mkstemp(prefix=stem + "-", suffix=".tmp", dir=directory)
            pending = Path(filename)
            temporary.append(pending)
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(pending, paths[key])
            temporary.remove(pending)
            written.append(paths[key])
        if any(path.read_bytes() != files[key] for key, path in paths.items()):
            raise EvidenceError("artifact_readback_failed", "Written artifact bytes differ from the complete prepared documents.", "artifact_storage")
    except (OSError, EvidenceError) as exc:
        failed = []
        for path in temporary + written:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                failed.append(path.name)
        if failed:
            raise EvidenceError("artifact_cleanup_failed", "Artifact write failed and generated-file cleanup also failed; inspect: " + ", ".join(failed), "artifact_storage") from exc
        if isinstance(exc, EvidenceError):
            raise
        raise EvidenceError("artifact_write_failed", "Atomic artifact write/readback failed; this run's partial files were removed.", "artifact_storage") from exc
    return result


def main(operation: str = "report", period: str = "auto", start_utc: str = "", end_utc: str = "",
         view: str = "summary", event_type: str = "all", state: str = "all", time_scope: str = "all",
         search: str = "", limit: int = 10, offset: int = 0):
    """Runtime entry point. No live fixture, environment override or arbitrary path input."""
    try:
        reference = utc_now().replace(microsecond=0)
        params = parameters(operation, period, start_utc, end_utc, view, event_type, state, time_scope, search, limit, offset, reference)
        config = configuration()
        branding = logo_markup()
        if operation == "report":
            artifact_directory()
        reader = NativeReader(config)
        try:
            snapshot = collect(reader, config, params, reference)
        finally:
            reader.close()
        if operation == "report":
            return write_report(snapshot, branding)
        return query_snapshot(snapshot, params)
    except EvidenceError as exc:
        return budget_response({"status": "error", "operation": operation if operation in ("report", "query") else "invalid", "error": exc.document()})

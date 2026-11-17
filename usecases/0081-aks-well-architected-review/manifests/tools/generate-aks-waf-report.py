"""Read-only AKS assessment. Build assets with build_tool.py before SRE paste."""

import base64
import binascii
import csv
import difflib
import gzip
import hashlib
import io
import json
import math
import os
import re
import ssl
import tempfile
import threading
import time
import warnings
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener
from uuid import UUID, uuid4


# ============================ OPERATOR CONFIGURATION (edit only this block) ============================
# Only the two values marked (*) are required: TENANT_ID and MANAGED_IDENTITY_CLIENT_ID. There is no cluster list to
# paste: with AUTO_DISCOVERY = True the tool discovers, on every run, ALL AKS clusters the SRE Agent identity can read
# (grant Reader once, for example at management-group scope), across every subscription of the tenant.
# Which clusters go into a report (all, one subscription, one or several clusters) is chosen from chat.
SUBSCRIPTION_ID = "<YOUR_SUBSCRIPTION_ID>"             # optional: only for APPROVED_CLUSTERS entries without "subscription_id"
TENANT_ID = "<YOUR_TENANT_ID>"                         # (*) tenant; every subscription must belong to this tenant
MANAGED_IDENTITY_CLIENT_ID = "<YOUR_AGENT_CLIENT_ID>"  # (*) client ID (not object ID) of the SRE Agent managed identity
CLIENT_NAME = "Customer"
CLIENT_LOGO_DATA_URI = ""
CLIENT_LOGO_ALT = "Authorized customer logo"
# Defaults for EVERY cluster (normally unchanged).
CLUSTER_DEFAULTS = {
    "environment": "UNSPECIFIED",          # LAB / PRODUCTION / UNSPECIFIED (exactly)
    "kubernetes_enabled": False,           # True = read workloads (needs Entra ID + Azure RBAC AKS and network reach to the API server)
    "include_node_resource_group": True,   # inventory of the node resource group (MC_...)
    "advisor_enabled": True,               # cached Azure Advisor recommendations
    "approved_related_resource_ids": [],
    "approved_cost_resource_ids": [],
    "cost_scope": "node_resource_group",   # actual cost of the node resource group (Cost Management Reader); "disabled" to skip costs
    "cost_timeframe": "month_to_date",
    "requirements": {},
}
# OPTIONAL (may stay empty): per-cluster overrides, for example to mark one cluster as production.
#     "<aks-name>": {"resource_group": "<resource-group>", "subscription_id": "<subscription-id>", "environment": "PRODUCTION"},
#     Keys that start with "<" are ignored.
APPROVED_CLUSTERS = {
}
# Auto-discovery (recommended): one fixed read-only Azure Resource Graph query on every run.
AUTO_DISCOVERY = True
# Optional: restrict discovery to these subscription IDs. Empty = every subscription the identity can read.
DISCOVERY_SUBSCRIPTION_IDS = []
# =======================================================================================================

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


def collection_disclosure(snapshot):
    if snapshot.get("schema_version") == "aks-waf-multi-cluster-v1":
        sources = [source for run in snapshot["cluster_runs"] for source in run_sources(run)]
        names = snapshot["selected_cluster_names"]
        result = {"reference_utc": snapshot["reference_utc"], "fresh_collection": True,
                  "provenance": snapshot["provenance"], "selected_cluster_count": len(names),
                  "subscription_count": len({row.get("subscription_id") for row in snapshot["available_clusters"]}),
                  "cluster_run_status_counts": snapshot["aggregate"]["cluster_status_counts"],
                  "source_status_counts": dict(Counter(source["status"] for source in sources)),
                  "source_total": len(sources), "source_details_view": "coverage",
                  "paging_basis": "Local offset in this collection; later calls recollect, not a stable cross-call cursor."}
        if len(names) <= 5:
            result["selected_cluster_names"] = names
        return result
    return {"reference_utc": snapshot["reference_utc"], "fresh_collection": True, "provenance": snapshot["provenance"],
            "environment": snapshot["environment"], "source_status_counts": dict(Counter(s["status"] for s in snapshot["sources"])),
            "source_total": len(snapshot["sources"]), "source_details_view": "coverage",
            "paging_basis": "Local offset in this collection; later calls recollect, not a stable cross-call cursor."}


def summary(snapshot):
    return {"cluster_id": snapshot["cluster"]["id"], "cluster_name": snapshot["cluster"]["name"], "global": snapshot["scores"]["global"],
            "areas": snapshot["scores"]["areas"], "pillars": snapshot["scores"]["pillars"],
            "inventory_counts": {key: len(snapshot["inventory"].get(key) or []) for key in ("node_pools", "namespaces", "workloads", "related_resources")},
            "findings": len(snapshot["findings"]), "critical": sum(f["severity"] == "critical" for f in snapshot["findings"]),
            "catalog_coverage": snapshot["methodology"]["catalog_coverage"], "official_waf_score": False,
            "actual_cost": snapshot["finops"]["actual_cost"], "currency": snapshot["finops"]["currency"], "estimated_savings": None}


def snapshot_rows(snapshot, view):
    inventory = snapshot["inventory"]
    return {
        "summary": [summary(snapshot)], "cluster": [snapshot["cluster"]],
        "node_pools": inventory.get("node_pools", []), "workloads": inventory.get("workloads", []),
        "resources": inventory.get("related_resources", []) + [
            row for key in ("services", "storage_classes", "pvcs", "pvs") for row in inventory.get(key, [])],
        "findings": snapshot["checks"], "coverage": snapshot["sources"], "actions": snapshot["actions"],
        "finops": [{**row, "record_type": "candidate"} for row in snapshot["finops"]["candidates"]]
        + [{**row, "record_type": "cost"} for row in snapshot["finops"]["cost_rows"]]
        + [{**row, "record_type": "metric"} for row in snapshot["finops"]["metrics"]],
        "architecture": [{**row, "record_type": record_type}
                         for record_type, key in (("node", "nodes"), ("edge", "edges"), ("unknown", "unknowns"))
                         for row in snapshot["architecture"][key]],
    }[view]


def run_sources(run):
    if run["snapshot"] is not None:
        return run["snapshot"]["sources"]
    return [source_receipt("arm_cluster", run["reference_utc"],
                           "denied" if run["error"].get("http_status") in (401, 403) else "error",
                           "Primary collection failed; this cluster has no snapshot or inferred healthy-zero inventory.",
                           errors=[run["error"]])]


def successful_snapshots(document):
    return [run["snapshot"] for run in document["cluster_runs"] if run["snapshot"] is not None] if (
        document.get("schema_version") == "aks-waf-multi-cluster-v1") else [document]


def query_snapshot(snapshot, params):
    view = params["view"]
    if snapshot.get("schema_version") == "aks-waf-multi-cluster-v1":
        rows = []
        for run in snapshot["cluster_runs"]:
            scope = {"cluster_id": run["cluster_id"], "cluster_name": run["cluster_name"]}
            if run["snapshot"] is not None:
                rows.extend({**row, **scope} for row in snapshot_rows(run["snapshot"], view))
            elif view == "coverage":
                rows.extend({**row, **scope} for row in run_sources(run))
            elif view == "summary":
                rows.append({**scope, "status": "error", "global": None, "inventory_counts": None,
                             "error": run["error"], "reference_utc": run["reference_utc"]})
    else:
        rows = snapshot_rows(snapshot, view)
    def matches(row):
        for field in ("namespace", "workload_name"):
            if params[field] and row.get(field) != params[field]:
                return False
        for field in ("area", "level", "severity", "status"):
            if params[field] != "all" and row.get(field) != params[field]:
                return False
        return True
    matched = [row for row in rows if matches(row)]
    selected = matched[params["offset"]:params["offset"] + params["limit"]]
    partial = snapshot.get("schema_version") == "aks-waf-multi-cluster-v1" and any(
        run["status"] != "ok" for run in snapshot["cluster_runs"])
    result = {"status": "partial" if partial else "ok", "operation": "query", "view": view, "collection": collection_disclosure(snapshot),
              "total_matched": len(matched), "offset": params["offset"], "requested_limit": params["limit"],
              "returned": len(selected), "has_more": params["offset"] + len(selected) < len(matched),
              "next_offset": params["offset"] + len(selected) if params["offset"] + len(selected) < len(matched) else None,
              "transport_capped": False, "rows": selected}
    while selected and response_bytes(result) > TRANSPORT_BYTES:
        selected = selected[:-1]
        result.update(rows=selected, returned=len(selected), transport_capped=True,
                      has_more=params["offset"] + len(selected) < len(matched),
                      next_offset=params["offset"] + len(selected) if selected and params["offset"] + len(selected) < len(matched) else None)
    if not selected and params["offset"] < len(matched):
        return ensure_response({"status": "error", "operation": "query", "view": view,
                                "error": {"code": "query_row_too_large", "message": "One complete row cannot fit 3500 default-serialized bytes. Use the full report JSON; no zero-row continuation."},
                                "total_matched": len(matched), "offset": params["offset"], "requested_limit": params["limit"],
                                "returned": 0, "has_more": True, "next_offset": None, "transport_capped": True,
                                "collection": collection_disclosure(snapshot)})
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
    payload = safe_json(snapshot)
    if len(payload) > HTML_INLINE_JSON_BYTES:
        # Large fleet reports: the same complete JSON, gzip+base64, decompressed locally by the browser (no network).
        raw = payload.encode("utf-8")
        packed = gzip.compress(raw, compresslevel=9, mtime=0)
        if gzip.decompress(packed) != raw:
            raise EvidenceError("round_trip_failed", "Compressed embedded JSON did not round-trip.", "renderer")
        payload = "gzip-base64:" + base64.b64encode(packed).decode("ascii")
    return HTML_TEMPLATE.replace("__REPORT_DATA_JSON__", payload)


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


def inventory_csv_rows(snapshot):
    if snapshot.get("schema_version") == "aks-waf-multi-cluster-v1":
        rows = [row for item in successful_snapshots(snapshot) for row in inventory_csv_rows(item)]
        rows.extend({"collection": "cluster_collection_error", "cluster_id": run["cluster_id"],
                     "cluster_name": run["cluster_name"], "resource_id": run["cluster_id"],
                     "source_id": run["error"].get("source_id") or run["error"].get("source"), "observed_at": run["reference_utc"], "details_json": run}
                    for run in snapshot["cluster_runs"] if run["snapshot"] is None)
        return rows
    rows = [{"collection": "cluster", **snapshot["cluster"], "details_json": snapshot["cluster"]}]
    aggregate_keys = {"deployments", "statefulsets", "daemonsets", "jobs", "cronjobs"}
    for collection, records in snapshot["inventory"].items():
        if collection in aggregate_keys or records is None:
            continue
        for record in records:
            rows.append({"collection": collection, **record, "details_json": record})
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
    if OUTPUT_DIRECTORY != "aks-waf-reports":
        raise EvidenceError("unsafe_artifact_directory", "Only the fixed aks-waf-reports child is allowed.", "artifact_storage")
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
        "report_path": ".html", "snapshot_path": "-snapshot.json",
        "findings_csv_path": "-findings.csv", "inventory_csv_path": "-inventory.csv",
    }
    if set(paths) != set(suffixes):
        raise EvidenceError("unsafe_sharing_path", "Native delivery requires exactly the four guarded report artifacts.", "artifact_storage")
    stem = paths["report_path"].name.removesuffix(".html")
    if not re.fullmatch(r"(?:aks|simulated)-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12}", stem):
        raise EvidenceError("unsafe_sharing_path", "Native aliases require this tool's generated run filenames.", "artifact_storage")
    expected = root / "aks-waf-reports"
    aliases = {}
    for key, path in paths.items():
        if path.parent != expected or path.name != stem + suffixes[key]:
            raise EvidenceError("unsafe_sharing_path", "Native aliases must reference the same run in the fixed report directory.", "artifact_storage")
        aliases[key.removesuffix("_path") + "_url"] = (
            "/api/files/tmp/ThreadFiles/" + match[1] + "/aks-waf-reports/" + quote(path.name, safe="")
        )
    return {**result, "sharing_mode": "native_ui", **aliases}


def report_envelope(snapshot, paths, root):
    items = successful_snapshots(snapshot)
    findings = [row for item in items for row in item["findings"]]
    multi = snapshot.get("schema_version") == "aks-waf-multi-cluster-v1"
    aggregate = snapshot["aggregate"] if multi else None
    partial = any(s["status"] not in ("complete", "not_applicable") for item in items for s in item["sources"])
    result = {"status": "partial" if partial or (multi and aggregate["cluster_status_counts"].get("error")) else "ok",
              "operation": "report", "artifact_status": "written", **sharing_fields(root, paths),
              "collection": collection_disclosure(snapshot),
              "global": aggregate["scores"]["global"] if multi else snapshot["scores"]["global"], "findings_total": len(findings),
              "findings_by_severity": {key: sum(row["severity"] == key for row in findings) for key in SEVERITIES},
              "inventory_counts": aggregate["inventory_counts"] if multi else {
                  key: len(snapshot["inventory"].get(key) or []) for key in ("node_pools", "namespaces", "workloads", "related_resources")},
              "critical_total": sum(row["severity"] == "critical" for row in findings),
              "estimated_savings": None, **{key: str(path) for key, path in paths.items()}}
    if not multi:
        row = (snapshot.get("available_clusters") or [{}])[0]
        result["selection"] = {"cluster_name": snapshot["cluster"]["name"], "subscription_name": row.get("subscription_name"),
                               "subscription_id": row.get("subscription_id")}
        result["actual_cost"] = {"amount": snapshot["finops"]["actual_cost"], "currency": snapshot["finops"]["currency"]}
        return ensure_response(result)
    costs, with_cost = {}, 0
    for item in items:
        if item["finops"]["actual_cost"] is not None and item["finops"]["currency"]:
            with_cost += 1
            costs[item["finops"]["currency"]] = costs.get(item["finops"]["currency"], Decimal(0)) + Decimal(str(item["finops"]["actual_cost"]))
    result["actual_cost_by_currency"] = {key: round(float(value), 2) for key, value in sorted(costs.items())}
    result["clusters_with_cost"] = with_cost
    rank = {key: index for index, key in enumerate(SEVERITIES)}
    top = sorted((row for row in findings if row["severity"] in ("critical", "high")),
                 key=lambda row: (rank[row["severity"]], row["cluster_name"], row["title"]))
    result["top_findings"] = [{"cluster": row["cluster_name"], "severity": row["severity"], "title": row["title"][:90]} for row in top[:6]]
    result["cluster_errors"] = [{"cluster": run["cluster_name"], "code": run["error"].get("code")}
                                for run in snapshot["cluster_runs"] if run["status"] == "error"][:6]
    result["cluster_errors_total"] = sum(run["status"] == "error" for run in snapshot["cluster_runs"])
    for key in ("top_findings", "cluster_errors"):
        while result[key] and response_bytes(result) > TRANSPORT_BYTES:
            result[key] = result[key][:-1]
    return ensure_response(result)


def write_report(snapshot):
    root, directory = artifact_directory()
    reference = snapshot["reference_utc"].replace(":", "").replace("-", "")
    prefix = ("simulated-" if snapshot["provenance"] == "SIMULATED" else "aks-") + reference + "-" + uuid4().hex[:12]
    paths = {key: directory / (prefix + suffix) for key, suffix in (
        ("report_path", ".html"), ("snapshot_path", "-snapshot.json"),
        ("findings_csv_path", "-findings.csv"), ("inventory_csv_path", "-inventory.csv"))}
    response = report_envelope(snapshot, paths, root)
    snapshot_document = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    if json.loads(snapshot_document) != snapshot:
        raise EvidenceError("round_trip_failed", "Full normalized export does not round-trip.", "artifact_storage")
    names = {str(row.get("subscription_id") or "").lower(): row.get("subscription_name") for row in snapshot.get("available_clusters") or []}

    def scoped(row, details=None):
        parts = str(row.get("cluster_id") or row.get("resource_id") or row.get("id") or "").split("/")
        subscription = parts[2].lower() if len(parts) > 2 and parts[1].lower() == "subscriptions" else ""
        return {**row, "subscription_id": subscription or None, "subscription_name": names.get(subscription),
                "details_json": row if details is None else details}
    documents = {
        "report_path": render_html(snapshot), "snapshot_path": snapshot_document,
        "findings_csv_path": csv_document([scoped(row) for item in successful_snapshots(snapshot) for row in item["findings"]],
            ("check_id", "checklist_id", "title", "status", "level", "area", "pillar", "severity", "resource_id",
             "subscription_id", "subscription_name", "cluster_id", "cluster_name", "namespace", "workload_name", "effort", "reason",
             "recommendation", "learn_url", "details_json")),
        "inventory_csv_path": csv_document([scoped(row, row["details_json"]) for row in inventory_csv_rows(snapshot)],
            ("collection", "resource_id", "subscription_id", "subscription_name", "cluster_id", "cluster_name", "name", "namespace", "kind",
             "source_id", "observed_at", "details_json")),
    }
    encoded = {key: value.encode("utf-8-sig" if key.endswith("csv_path") else "utf-8") for key, value in documents.items()}
    if any(len(value) > ARTIFACT_BYTES for value in encoded.values()) or len(encoded["report_path"]) > HTML_ARTIFACT_BYTES:
        raise EvidenceError("artifact_size_exceeded", "Complete artifacts exceed " + str(ARTIFACT_BYTES) + " bytes (HTML " + str(HTML_ARTIFACT_BYTES)
                            + "); no records were dropped and no files were written. Select fewer clusters (subscription or cluster_names).", "artifact_storage")
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
            raise EvidenceError("artifact_cleanup_failed", "Artifact failure and cleanup failure; inspect these generated files in the fixed output directory: "
                                + ", ".join(failures), "artifact_storage") from exc
        if isinstance(exc, EvidenceError):
            raise
        raise EvidenceError("artifact_write_failed", "Could not atomically write/read back all four files; this run's partial files were removed.", "artifact_storage") from exc
    return response


def main(operation: str = "report", view: str = "summary", cluster_name: str = "", namespace: str = "",
         workload_name: str = "", area: str = "all", level: str = "all", severity: str = "all",
         status: str = "all", limit: int = 25, offset: int = 0, cluster_names: str = "", subscription: str = "") -> dict:
    """Collect one, several or all auto-discovered clusters (any subscription); never change source scope or identity."""
    global ROSTER
    try:
        params = validate_parameters(operation, view, cluster_name, namespace, workload_name, area, level, severity, status, limit, offset,
                                     cluster_names, subscription)
        ROSTER = None
        DISCOVERY_INFO.clear()
        ROSTER = effective_roster()
        configs, configured = selection_configs(cluster_name, cluster_names, subscription, operation)
        if operation == "list_clusters":
            return list_clusters_page(configured, limit, offset, subscription)
        validate_branding()
        roster = [roster_row(config) for config in configs]
        if not CATALOG.get("rules"):
            raise EvidenceError("catalog_missing", "Use the build-generated whole-file tool, not unbuilt engine.py.", "rule_catalog")
        reference = utc_now()
        if len(configs) == 1:
            config = configs[0]
            raw = collect_live(config, reference)
            snapshot = finish_snapshot(raw, reference, environment=config["environment"])
            snapshot.update(available_clusters=roster, selected_cluster_names=[config["name"]])
        else:
            runs = collect_fleet(configs)
            snapshot = multi_snapshot(runs, reference, roster)
            if not successful_snapshots(snapshot):
                errors = Counter(str(run["error"].get("code")) for run in runs)
                return ensure_response({"status": "error", "error": {
                    "code": "all_clusters_failed", "source": "arm_cluster",
                    "message": "No selected cluster produced a snapshot; no empty/healthy report or files.",
                }, "artifact_status": "not_written", "selected": len(runs), "error_codes": dict(errors.most_common(8)),
                    "cluster_errors": [{"cluster_name": run["cluster_name"], "error": {
                        key: run["error"].get(key) for key in ("code", "source_id", "http_status")}} for run in runs[:8]],
                    "provenance": "LIVE"})
        return query_snapshot(snapshot, params) if operation == "query" else write_report(snapshot)
    except EvidenceError as exc:
        return ensure_response({"status": "error", "error": exc.public(),
                                "artifact_status": "cleanup_failed" if exc.code == "artifact_cleanup_failed" else "not_written",
                                "provenance": "LIVE"})


def collect_one(config, deadline):
    """One cluster run: explicit snapshot (ok/partial) or a structured error; never a healthy-looking empty result."""
    run_reference = utc_now()
    run = {"cluster_id": config["id"], "cluster_name": config["name"], "reference_utc": run_reference,
           "snapshot": None, "error": None, "status": "error"}
    try:
        if time.monotonic() >= deadline:
            raise EvidenceError("collection_deadline", "Shared fleet time bound reached before this cluster started; not collected, not empty/healthy.", "collection")
        raw = collect_live(config, run_reference, deadline=deadline)
        run["snapshot"] = finish_snapshot(raw, run_reference, environment=config["environment"])
        run["status"] = "partial" if any(
            source["status"] not in ("complete", "not_applicable") for source in run["snapshot"]["sources"]) else "ok"
    except EvidenceError as exc:
        run["error"] = exc.public()
    except Exception as exc:  # one malformed cluster must not hide the others; it is reported, never healthy
        run["error"] = {"code": "unexpected_error", "message": "Unexpected " + type(exc).__name__ + " while collecting this cluster; not evaluated.",
                        "source_id": "collection", "http_status": None}
    return run


def collect_fleet(configs):
    """Bounded parallel collection with one shared deadline below the tool timeout; results keep the selection order."""
    deadline = time.monotonic() + FLEET_DEADLINE_SECONDS
    executor = ThreadPoolExecutor(max_workers=max(1, min(COLLECTION_WORKERS, len(configs))), thread_name_prefix="aks-collect")
    try:
        futures = [executor.submit(collect_one, config, deadline) for config in configs]
        done, _ = wait(futures, timeout=max(0.0, deadline - time.monotonic()) + FLEET_GRACE_SECONDS)
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
    runs = []
    for config, future in zip(configs, futures):
        if future in done and not future.cancelled():
            runs.append(future.result())
            continue
        future.cancel()
        runs.append({"cluster_id": config["id"], "cluster_name": config["name"], "reference_utc": utc_now(), "snapshot": None,
                     "status": "error", "error": {"code": "collection_timeout", "source_id": "collection", "http_status": None,
                                                  "message": "Not collected within the shared " + str(FLEET_DEADLINE_SECONDS)
                                                  + " s fleet bound; unknown, not empty/healthy. Repeat with fewer clusters."}})
    return runs


ARM_ORIGIN = "https://management.azure.com"
AKS_AUDIENCE = "6dae42f8-4368-4678-94ff-3960e28e3630"
AKS_API = "2025-05-01"
TRANSPORT_BYTES = 3500
ARTIFACT_BYTES = 64_000_000
HTML_ARTIFACT_BYTES = 16_000_000
HTML_INLINE_JSON_BYTES = 4_000_000
HTTP_BYTES = 8_000_000
MAX_PAGES = 100
MAX_ROWS = 20000
MAX_RELATED_RESOURCES = 200
MAX_APPROVED_CLUSTERS = 500
ARG_API = "2022-10-01"
MAX_DISCOVERY_PAGES = 5
ROSTER = None
DISCOVERY_INFO = {}
MAX_REPORT_CLUSTERS = 100
MAX_QUERY_CLUSTERS = 5
COLLECTION_SCOPE = threading.local()
MAX_COLLECTION_SECONDS = 240
FLEET_DEADLINE_SECONDS = 750
FLEET_GRACE_SECONDS = 40
COLLECTION_WORKERS = 8
COST_CONCURRENCY = 2
COST_SLOTS = threading.BoundedSemaphore(COST_CONCURRENCY)
COST_RETRY_ATTEMPTS = 4
COST_MAX_RETRY_WAIT_SECONDS = 60
COST_SLOT_WAIT_SECONDS = 600
MAX_HTTP_ATTEMPTS = 300
KUBE_PAGE_SIZE = 500
OUTPUT_DIRECTORY = "aks-waf-reports"
AREAS = ("best_practices", "security", "finops", "optimization")
PILLARS = ("reliability", "security", "cost", "operations", "performance")
LEVELS = ("cluster", "workload", "resource")
SEVERITIES = ("critical", "high", "medium", "low")
CHECK_STATUSES = ("passed", "failed", "not_evaluated", "not_applicable")
SOURCE_STATUSES = ("complete", "partial", "denied", "error", "not_configured", "not_applicable")
VIEWS = ("summary", "cluster", "node_pools", "workloads", "resources", "findings", "finops", "coverage", "actions", "architecture")
SYSTEM_NAMESPACES = ("kube-system", "kube-public", "kube-node-lease", "gatekeeper-system", "azure-arc")
KUBE_PATHS = {
    "namespaces": "/api/v1/namespaces",
    "nodes": "/api/v1/nodes",
    "pods": "/api/v1/pods",
    "services": "/api/v1/services",
    "pvcs": "/api/v1/persistentvolumeclaims",
    "pvs": "/api/v1/persistentvolumes",
    "resource_quotas": "/api/v1/resourcequotas",
    "deployments": "/apis/apps/v1/deployments",
    "statefulsets": "/apis/apps/v1/statefulsets",
    "daemonsets": "/apis/apps/v1/daemonsets",
    "replicasets": "/apis/apps/v1/replicasets",
    "jobs": "/apis/batch/v1/jobs",
    "cronjobs": "/apis/batch/v1/cronjobs",
    "pdbs": "/apis/policy/v1/poddisruptionbudgets",
    "hpas": "/apis/autoscaling/v2/horizontalpodautoscalers",
    "network_policies": "/apis/networking.k8s.io/v1/networkpolicies",
    "storage_classes": "/apis/storage.k8s.io/v1/storageclasses",
    "node_metrics": "/apis/metrics.k8s.io/v1beta1/nodes",
    "pod_metrics": "/apis/metrics.k8s.io/v1beta1/pods",
}
RESOURCE_APIS = {
    "microsoft.compute/disks": "2024-03-02",
    "microsoft.compute/virtualmachinescalesets": "2024-03-01",
    "microsoft.network/loadbalancers": "2024-05-01",
    "microsoft.network/publicipaddresses": "2024-05-01",
    "microsoft.network/networkinterfaces": "2024-05-01",
    "microsoft.network/virtualnetworks": "2024-05-01",
    "microsoft.network/virtualnetworks/subnets": "2024-05-01",
    "microsoft.network/networksecuritygroups": "2024-05-01",
    "microsoft.network/privatednszones": "2020-06-01",
    "microsoft.network/dnszones": "2018-05-01",
    "microsoft.storage/storageaccounts": "2023-05-01",
    "microsoft.containerregistry/registries": "2023-07-01",
    "microsoft.keyvault/vaults": "2023-07-01",
    "microsoft.managedidentity/userassignedidentities": "2023-01-31",
}

# BEGIN BUILD-TIME ASSETS
CATALOG = json.loads((
    '{"catalogSnapshot": {"name": "Azure AKS Review", "repository": "https://github.com/Azure/review-chec'
    'klists", "url": "https://raw.githubusercontent.com/Azure/review-checklists/f131b93418892102b00c247fd'
    '9cf685e3d356522/checklists/aks_checklist.en.json", "commit": "f131b93418892102b00c247fd9cf685e3d3565'
    '22", "blob_sha": "8c9d49dedf2c8f0aa0e11fba86c7a17aa927dc22", "sha256": "e1f7e0f44e121a4f96a9258e6438'
    '3d33a14c78e56bf0d7c7b6638f8b72acff31", "bytes": 66436, "item_count": 112, "upstream_metadata_timesta'
    'mp": "February 20, 2024", "retrieved_at": "2026-10-13", "license": "MIT", "copyright": "Copyright (c'
    ') Microsoft Corporation."}, "guide": {"url": "https://learn.microsoft.com/en-us/azure/well-architect'
    'ed/service-guides/azure-kubernetes-service", "commit": "5d6ba52923afc503730f1a61cb201269060d6ecb", "'
    'updated_at": "2026-09-29T17:03:00Z", "retrieved_at": "2026-10-13"}, "assessment_url": "https://learn'
    '.microsoft.com/en-us/assessments/azure-architecture-review/", "interpretation": ["Local rule-resourc'
    'e indicators, not an official Azure WAF assessment, certification, Polaris or WARA grade.", "Checkli'
    'st IDs and GUIDs are references. Legacy graph snippets are never executed.", "Standard/Premium and A'
    'KS Automatic/NAP replace obsolete Paid-tier and universal fixed-pool assumptions.", "Azure CNI Overl'
    'ay/Cilium is supported; a legacy default maxPods=30 is not a universal density limit.", "Absent IaC,'
    ' requirements, DR tests, licensing or telemetry is not evidence of drift, failure or health.", "Conf'
    'iguration presence is distinct from effective enforcement, source health, entitlement and applicatio'
    'n availability."], "rules": [{"rule_id": "C01", "checklist_id": "05.01.01", "test": "managed_identit'
    'y", "level": "cluster", "area": "security", "pillar": "security", "severity": "medium", "effort": "m'
    'edium", "title": "Cluster managed identity", "recommendation": "Review the move to a managed identit'
    'y with the owner; do not rotate credentials from this report.", "business_impact": "A secret-based i'
    'dentity adds management work and expiry risk; no incident was measured."}, {"rule_id": "C02", "check'
    'list_id": "05.01.02", "test": "managed_entra", "level": "cluster", "area": "security", "pillar": "se'
    'curity", "severity": "high", "effort": "medium", "title": "Managed Microsoft Entra integration", "re'
    'commendation": "Validate a managed Microsoft Entra integration and its requirements before any chang'
    'e.", "business_impact": "Decentralized authentication can make access control and revocation harder.'
    '"}, {"rule_id": "C03", "checklist_id": "05.01.04", "test": "rbac", "level": "cluster", "area": "secu'
    'rity", "pillar": "security", "severity": "high", "effort": "medium", "title": "Cluster RBAC authoriz'
    'ation", "recommendation": "Validate Kubernetes RBAC or Azure RBAC with least-privilege access; do no'
    't assume effective privileges without reading the assignments.", "business_impact": "Disabled RBAC w'
    'eakens authorization barriers; an enabled option does not prove least privilege."}, {"rule_id": "C04'
    '", "checklist_id": "05.01.08", "test": "local_accounts", "level": "cluster", "area": "security", "pi'
    'llar": "security", "severity": "high", "effort": "low", "title": "AKS local accounts", "recommendati'
    'on": "Review disabling local accounts after you check emergency access and Microsoft Entra.", "busin'
    'ess_impact": "Local accounts can bypass centralized identity controls."}, {"rule_id": "C05", "checkl'
    'ist_id": "06.07.02", "test": "api_access", "level": "cluster", "area": "security", "pillar": "securi'
    'ty", "severity": "high", "effort": "medium", "title": "API server network access", "recommendation":'
    ' "Validate authorized ranges or a private endpoint against the requirements; keep the access paths y'
    'ou need.", "business_impact": "An unrestricted public endpoint widens the access surface, but it doe'
    's not prove exploitation."}, {"rule_id": "C06", "checklist_id": "05.01.06", "test": "workload_identi'
    'ty", "level": "cluster", "area": "security", "pillar": "security", "severity": "medium", "effort": "'
    'medium", "title": "OIDC and Microsoft Entra Workload ID", "recommendation": "Assess Workload ID for '
    'applications that access Azure; enabled does not mean every pod uses it.", "business_impact": "Appli'
    'cations that need Azure can avoid long-lived secrets with a federated identity."}, {"rule_id": "C07"'
    ', "checklist_id": "06.07.05", "test": "network_policy_engine", "level": "cluster", "area": "security'
    '", "pillar": "security", "severity": "medium", "effort": "medium", "title": "Network policy engine",'
    ' "recommendation": "Validate a supported engine, including Cilium, if segmentation is a requirement;'
    ' review the effective policies separately.", "business_impact": "Without a supported engine, a Netwo'
    'rkPolicy might not enforce the expected segmentation."}, {"rule_id": "C08", "checklist_id": "06.04.0'
    '1", "test": "cni", "level": "cluster", "area": "optimization", "pillar": "performance", "severity": '
    '"low", "effort": "high", "title": "Network model and IPAM", "recommendation": "Use the current guida'
    'nce to choose Azure CNI Overlay or a justified alternative; do not force maxPods=30 or a migration w'
    'ithout requirements.", "business_impact": "A network choice that does not match the requirements can'
    ' limit scalability and IP address space."}, {"rule_id": "C09", "checklist_id": "04.01.01", "test": "'
    'policy", "level": "cluster", "area": "best_practices", "pillar": "operations", "severity": "medium",'
    ' "effort": "medium", "title": "Azure Policy configuration", "recommendation": "Review Azure Policy o'
    'r equivalent controls and get compliance results; the add-on does not prove compliance.", "business_'
    'impact": "Unmanaged configuration controls can allow drift; compliance is not inferred from an add-o'
    'n."}, {"rule_id": "C10", "checklist_id": "04.02.05", "test": "defender", "level": "cluster", "area":'
    ' "security", "pillar": "security", "severity": "medium", "effort": "medium", "title": "Defender for '
    'Containers configuration", "recommendation": "Review the need, cost, licensing and health of Defende'
    'r; do not enable plans or agents from this reader.", "business_impact": "Detection depends on actual'
    ' coverage, licensing and telemetry, not only on an enabled profile."}, {"rule_id": "C11", "checklist'
    '_id": "02.02.03", "test": "sla_tier", "level": "cluster", "area": "best_practices", "pillar": "relia'
    'bility", "severity": "medium", "effort": "low", "title": "AKS tier and availability target", "recomm'
    'endation": "For production that needs an SLA, assess Standard or Premium and the current SLA terms."'
    ', "business_impact": "A tier without an SLA might not support the contractual target; application av'
    'ailability was not calculated."}, {"rule_id": "C12", "checklist_id": "02.02.02", "test": "zones", "l'
    'evel": "node_pool", "area": "best_practices", "pillar": "reliability", "severity": "medium", "effort'
    '": "high", "title": "Node pool zone distribution", "recommendation": "When the requirement and the r'
    'egion allow it, plan distribution across zones and validate storage and capacity.", "business_impact'
    '": "A pool that must be multi-zone but is not distributed can share a single failure domain."}, {"ru'
    'le_id": "C13", "checklist_id": "04.01.02", "test": "pool_state", "level": "node_pool", "area": "best'
    '_practices", "pillar": "reliability", "severity": "high", "effort": "medium", "title": "Node pool pr'
    'ovisioning state", "recommendation": "Investigate the pool\'s state and events with the owner; the cl'
    'uster\'s Running state does not confirm pool or pod health.", "business_impact": "An observed provisi'
    'oning failure can affect operations or capacity; it does not prove a service outage."}, {"rule_id": '
    '"C14", "checklist_id": "04.01.02", "test": "system_isolation", "level": "cluster", "area": "best_pra'
    'ctices", "pillar": "reliability", "severity": "medium", "effort": "medium", "title": "Applications o'
    'utside System pools", "recommendation": "Review where application pods run and separate system and u'
    'ser resources without forcing unnecessary affinity.", "business_impact": "Application pods observed '
    'on System pools can compete with essential services."}, {"rule_id": "C15", "checklist_id": "04.01.03'
    '", "test": "system_taint", "level": "node_pool", "area": "best_practices", "pillar": "reliability", '
    '"severity": "low", "effort": "medium", "title": "System pool scheduling protection", "recommendation'
    '": "Review CriticalAddonsOnly or another suitable isolation strategy, and pod compatibility.", "busi'
    'ness_impact": "Without scheduling isolation, new workloads can compete with system components."}, {"'
    'rule_id": "C16", "checklist_id": "07.06.01", "test": "autoscaling", "level": "cluster", "area": "fin'
    'ops", "pillar": "cost", "severity": "medium", "effort": "medium", "title": "Node scaling strategy", '
    '"recommendation": "If dynamic scaling is required, review Cluster Autoscaler or NAP/Automatic, limit'
    's and tests; do not promise savings.", "business_impact": "Fixed capacity might not follow changes i'
    'n demand; without historical usage, overcapacity is not quantified."}, {"rule_id": "C17", "checklist'
    '_id": "07.02.04", "test": "upgrade_policy", "level": "cluster", "area": "best_practices", "pillar": '
    '"operations", "severity": "medium", "effort": "medium", "title": "Kubernetes upgrade policy", "recom'
    'mendation": "Validate an automatic channel or a documented manual process, compatibility and mainten'
    'ance; do not upgrade from the report.", "business_impact": "Without a validated process, staying sup'
    'ported and patched is harder; a missing channel does not prove that there is no process."}, {"rule_i'
    'd": "C18", "checklist_id": "07.02.06", "test": "node_image_policy", "level": "cluster", "area": "bes'
    't_practices", "pillar": "operations", "severity": "medium", "effort": "medium", "title": "Node image'
    ' upgrades", "recommendation": "Review NodeImage, SecurityPatch or another documented process; do not'
    ' recommend kured if the managed channel already covers the case.", "business_impact": "The node imag'
    'e needs maintenance; a configured channel does not prove that an upgrade will complete."}, {"rule_id'
    '": "C19", "checklist_id": "07.02.04", "test": "version_support", "level": "cluster", "area": "best_p'
    'ractices", "pillar": "operations", "severity": "high", "effort": "medium", "title": "Version and cur'
    'rent regional catalog", "recommendation": "Compare the version, patches and support with the current'
    ' regional catalog and upgrade profile; absence does not automatically mean end of support.", "busine'
    'ss_impact": "A version explicitly outside the support policy can raise operational risk; no fixed hi'
    'storical table is used."}, {"rule_id": "C20", "checklist_id": "07.02.15", "test": "diagnostics", "le'
    'vel": "cluster", "area": "best_practices", "pillar": "operations", "severity": "medium", "effort": "'
    'medium", "title": "Control plane log configuration", "recommendation": "Review the categories and de'
    'stination of diagnostic settings and get evidence of delivery; do not confuse configuration with ing'
    'estion.", "business_impact": "Without available logs, investigating changes and incidents can be har'
    'der."}, {"rule_id": "C21", "checklist_id": "07.04.01", "test": "telemetry", "level": "cluster", "are'
    'a": "optimization", "pillar": "performance", "severity": "low", "effort": "medium", "title": "Curren'
    't measurements available", "recommendation": "Review time coverage and monitoring sources; a metrics'
    '.k8s.io sample does not prove monthly usage or end-to-end monitoring.", "business_impact": "Capacity'
    ' cannot be optimized on solid ground without measurements and a representative window."}, {"rule_id"'
    ': "C22", "checklist_id": "07.02.04", "test": "maintenance", "level": "cluster", "area": "best_practi'
    'ces", "pillar": "operations", "severity": "low", "effort": "low", "title": "Maintenance windows", "r'
    'ecommendation": "If planned maintenance is required, review windows and dependencies with the owner.'
    '", "business_impact": "Undefined windows can make changes harder to coordinate, but they are not pro'
    'of of disruption."}, {"rule_id": "W01", "checklist_id": "07.05.01", "test": "resources", "level": "w'
    'orkload", "area": "optimization", "pillar": "performance", "severity": "medium", "effort": "low", "t'
    'itle": "CPU/memory requests and memory limit", "recommendation": "Set requests and a memory limit fr'
    'om measurements; CPU limits are reviewed only when that requirement is explicit.", "business_impact"'
    ': "Observed missing requests or memory limits can make scheduling and isolation harder; requests are'
    ' not consumption.", "kubernetes_url": "https://kubernetes.io/docs/concepts/configuration/manage-reso'
    'urces-containers/"}, {"rule_id": "W02", "checklist_id": "07.05.04", "test": "probes", "level": "work'
    'load", "area": "best_practices", "pillar": "reliability", "severity": "medium", "effort": "low", "ti'
    'tle": "Probes for workloads that serve traffic", "recommendation": "For serving containers, validate'
    ' readiness/liveness probes and their behavior; do not force probes on jobs or sidecars where they do'
    ' not apply.", "business_impact": "Without suitable probes, Kubernetes has fewer signals to route tra'
    'ffic to the application or restart it.", "kubernetes_url": "https://kubernetes.io/docs/concepts/conf'
    'iguration/liveness-readiness-startup-probes/"}, {"rule_id": "W03", "checklist_id": "02.02.04", "test'
    '": "pdb", "level": "workload", "area": "best_practices", "pillar": "reliability", "severity": "mediu'
    'm", "effort": "low", "title": "PDB for replicated services", "recommendation": "Define and test a su'
    'itable PDB for replicated services; check the selector, replicas and capacity during upgrades.", "bu'
    'siness_impact": "Without a PDB that selects the service, a voluntary disruption can evict too many p'
    'ods; a PDB does not guarantee availability during failures.", "kubernetes_url": "https://kubernetes.'
    'io/docs/tasks/run-application/configure-pdb/"}, {"rule_id": "W04", "checklist_id": "07.06.03", "test'
    '": "hpa", "level": "workload", "area": "optimization", "pillar": "performance", "severity": "medium"'
    ', "effort": "medium", "title": "HPA when the workload needs scaling", "recommendation": "Validate th'
    'e target, min/max and metrics availability before you consider an HPA; a configured HPA does not pro'
    've effectiveness.", "business_impact": "A service that needs scaling but has no controller might not'
    ' match capacity to demand.", "kubernetes_url": "https://kubernetes.io/docs/tasks/run-application/hor'
    'izontal-pod-autoscale/"}, {"rule_id": "W05", "checklist_id": "02.02.04", "test": "replicas", "level"'
    ': "workload", "area": "best_practices", "pillar": "reliability", "severity": "medium", "effort": "lo'
    'w", "title": "Replicas for the availability target", "recommendation": "Validate replicas and failur'
    'e domains against the service requirement; zero replicas by design does not mean an outage.", "busin'
    'ess_impact": "A service that must be redundant but runs a single replica can have a single point of '
    'failure."}, {"rule_id": "W06", "checklist_id": "04.01.01", "test": "container_security", "level": "w'
    'orkload", "area": "security", "pillar": "security", "severity": "high", "effort": "medium", "title":'
    ' "Explicit Linux container privileges", "recommendation": "Review privileged, allowPrivilegeEscalati'
    'on and non-root execution against the container\'s needs; do not infer the image UID.", "business_imp'
    'act": "Explicitly configured elevated privileges can widen the impact of a compromise.", "kubernetes'
    '_url": "https://kubernetes.io/docs/concepts/security/pod-security-standards/"}, {"rule_id": "W07", "'
    'checklist_id": "04.01.04", "test": "images", "level": "workload", "area": "security", "pillar": "sec'
    'urity", "severity": "low", "effort": "low", "title": "Reproducible image references", "recommendatio'
    'n": "Avoid latest or missing tags; assess digests, a private registry and supply-chain controls sepa'
    'rately.", "business_impact": "A mutable reference makes the deployed artifact harder to reproduce; a'
    ' digest does not prove that the image is free of vulnerabilities."}, {"rule_id": "N01", "checklist_i'
    'd": "07.05.02", "test": "quota", "level": "namespace", "area": "finops", "pillar": "cost", "severity'
    '": "low", "effort": "low", "title": "Namespace quotas per policy", "recommendation": "When a shared '
    'namespace needs limits, review ResourceQuota and suitable values; do not confuse a quota with usage '
    'or billing.", "business_impact": "Without a required quota, containing consumption across teams can '
    'be harder."}, {"rule_id": "N02", "checklist_id": "04.01.01", "test": "pod_security", "level": "names'
    'pace", "area": "security", "pillar": "security", "severity": "medium", "effort": "medium", "title": '
    '"Pod Security Admission configured", "recommendation": "Validate enforce and equivalent Azure Policy'
    ' controls; audit/warn do not block, and a label does not measure compliance.", "business_impact": "A'
    'n admission requirement that is not enforced can allow specifications that exceed the policy.", "kub'
    'ernetes_url": "https://kubernetes.io/docs/concepts/security/pod-security-admission/"}, {"rule_id": "'
    'W08", "checklist_id": "06.07.06", "test": "network_policies", "level": "workload", "area": "security'
    '", "pillar": "security", "severity": "medium", "effort": "medium", "title": "NetworkPolicy that sele'
    'cts the workload", "recommendation": "If segmentation is required, review selectors, policyTypes and'
    ' rules; a selected policy does not prove effective isolation.", "business_impact": "Without a requir'
    'ed policy that selects the pods, the planned segmentation can be missing.", "kubernetes_url": "https'
    '://kubernetes.io/docs/concepts/services-networking/network-policies/"}, {"rule_id": "R01", "checklis'
    't_id": "07.07.06", "test": "pvc_binding", "level": "pvc", "area": "best_practices", "pillar": "relia'
    'bility", "severity": "medium", "effort": "medium", "title": "PVC binding state", "recommendation": "'
    'Investigate Lost, or Pending with an active consumer; WaitForFirstConsumer without a consumer can be'
    ' normal.", "business_impact": "An unbound volume that active pods need can block scheduling or data '
    'access."}, {"rule_id": "R02", "checklist_id": "06.01.04", "test": "load_balancer", "level": "resourc'
    'e", "area": "best_practices", "pillar": "reliability", "severity": "medium", "effort": "medium", "ti'
    'tle": "Azure Load Balancer SKU", "recommendation": "Review Standard and its ELB/ILB configuration; a'
    ' configured frontend and probe do not prove backend health.", "business_impact": "An outdated SKU ca'
    'n limit support or capabilities; exposure is not inferred from the name alone."}, {"rule_id": "R03",'
    ' "checklist_id": "06.02.01", "test": "storage_tls", "level": "resource", "area": "security", "pillar'
    '": "security", "severity": "medium", "effort": "medium", "title": "Storage HTTPS/TLS transport", "re'
    'commendation": "Validate HTTPS and a modern minimum TLS version with the clients; this local rule na'
    'rrows the checklist item on protecting associated PaaS resources.", "business_impact": "Allowing ins'
    'ecure transport can expose data in transit; the rule does not measure actual access."}, {"rule_id": '
    '"R04", "checklist_id": "04.02.01", "test": "keyvault_rbac", "level": "resource", "area": "security",'
    ' "pillar": "security", "severity": "low", "effort": "medium", "title": "Key Vault authorization mode'
    'l", "recommendation": "Review Azure RBAC, or the reason for access policies, without reading secret '
    'values or changing permissions.", "business_impact": "The model and its assignments need review to k'
    'eep least privilege."}, {"rule_id": "R05", "checklist_id": "06.07.01", "test": "nsg_exposure", "leve'
    'l": "resource", "area": "security", "pillar": "security", "severity": "high", "effort": "medium", "t'
    'itle": "NSG rules for administrative access from the internet", "recommendation": "Review Allow rule'
    's from Internet to SSH/RDP or all ports, and the NSG association; do not delete rules automatically.'
    '", "business_impact": "A broad explicit rule can open an access path if the NSG is associated and th'
    'e target is listening."}, {"rule_id": "R06", "checklist_id": "06.04.05", "test": "dns", "level": "cl'
    'uster", "area": "optimization", "pillar": "performance", "severity": "low", "effort": "medium", "tit'
    'le": "DNS and IPAM: performance not measured", "recommendation": "Review resolution, latency, range '
    'capacity and LocalDNS with authorized tests; a DNS inventory does not prove availability.", "busines'
    's_impact": "Name resolution and IP space can limit operations; this reader did not measure DNS queri'
    'es."}, {"rule_id": "F01", "checklist_id": "03.01.01", "test": "cost_allocation", "level": "cluster",'
    ' "area": "finops", "pillar": "cost", "severity": "low", "effort": "medium", "title": "Actual costs a'
    'nd Kubernetes attribution", "recommendation": "Keep ActualCost by ResourceId/currency separate from '
    'namespace/workload allocation; do not enable cost analysis or install Kubecost.", "business_impact":'
    ' "Without allocation evidence, the node bill cannot be attributed to applications."}, {"rule_id": "F'
    '02", "checklist_id": "07.06.04", "test": "rightsizing", "level": "cluster", "area": "finops", "pilla'
    'r": "cost", "severity": "low", "effort": "medium", "title": "Right-sizing with a representative wind'
    'ow", "recommendation": "Get historical usage, peaks and requirements before you change SKUs or reque'
    'sts; the current sample only guides a capacity review.", "business_impact": "A point-in-time sample '
    'does not prove 30 days of underutilization or achievable savings."}, {"rule_id": "F03", "checklist_i'
    'd": "07.03.01", "test": "spot", "level": "cluster", "area": "finops", "pillar": "cost", "severity": '
    '"low", "effort": "medium", "title": "Spot eligibility and savings commitments", "recommendation": "V'
    'alidate eviction tolerance, history, demand and commercial eligibility; do not buy reservations or s'
    'avings plans.", "business_impact": "Potential discounts come with conditions and commitments that ca'
    'nnot be inferred from the inventory."}, {"rule_id": "F04", "checklist_id": "07.02.01", "test": "advi'
    'sor", "level": "cluster", "area": "finops", "pillar": "cost", "severity": "low", "effort": "low", "t'
    'itle": "Azure Advisor recommendation coverage", "recommendation": "Review cached recommendations and'
    ' their date/scope; an empty list does not prove that there are no opportunities anywhere.", "busines'
    's_impact": "Deciding to optimize needs applicable recommendations and evidence, not invented savings'
    ' percentages."}], "checklist_items": [{"id": "01.01.01", "guid": "785c2fa5-5b56-4ad4-a408-fe72734c47'
    '6b", "text": "Use canary or blue/green deployments", "category": "Application Deployment", "subcateg'
    'ory": "Development", "waf": "Operations", "severity": "Medium", "link": "https://learn.microsoft.com'
    '/azure/architecture/reference-architectures/containers/aks/secure-baseline-aks"}, {"id": "01.01.02",'
    ' "guid": "ab5351f6-383a-45ed-9c5e-b143b16db40a", "text": "If required for AKS Windows workloads Host'
    'Process containers can be used", "category": "Application Deployment", "subcategory": "Development",'
    ' "waf": "Reliability", "severity": "Low", "link": "https://learn.microsoft.com/azure/aks/use-windows'
    '-hpc"}, {"id": "01.01.03", "guid": "a280dcf5-90ce-465d-b8e1-3f9ccbd46926", "text": "Use KEDA if runn'
    'ing event-driven workloads", "category": "Application Deployment", "subcategory": "Development", "wa'
    'f": "Performance", "severity": "Low", "link": "https://learn.microsoft.com/azure/azure-functions/fun'
    'ctions-kubernetes-keda"}, {"id": "01.01.04", "guid": "26886d20-b66c-457b-a591-19bf8e8f5c58", "text":'
    ' "Use Dapr to ease microservice development", "category": "Application Deployment", "subcategory": "'
    'Development", "waf": "Operations", "severity": "Low", "link": "https://dapr.io/"}, {"id": "01.02.01"'
    ', "guid": "3acbe04b-be20-49d3-afda-47778424d116", "text": "Use automation through ARM/TF to create y'
    'our Azure resources", "category": "Application Deployment", "subcategory": "Infrastructure as Code",'
    ' "waf": "Operations", "severity": "Medium", "link": "https://learn.microsoft.com/azure/developer/ter'
    'raform/create-k8s-cluster-with-tf-and-aks"}, {"id": "02.01.01", "guid": "36cb45e5-7960-4332-9bdf-8cc'
    '23318da61", "text": "Schedule and perform DR tests regularly", "category": "BC and DR", "subcategory'
    '": "Disaster Recovery", "waf": "Reliability", "severity": "High", "link": "https://learn.microsoft.c'
    'om/azure/cloud-adoption-framework/ready/enterprise-scale/business-continuity-and-disaster-recovery"}'
    ', {"id": "02.02.01", "guid": "170265f4-bb46-4a39-9af7-f317284797b1", "text": "Use Azure Traffic Mana'
    'ger or Azure Front Door as a global load balancer for region failover", "category": "BC and DR", "su'
    'bcategory": "High Availability", "waf": "Reliability", "severity": "Medium", "link": "https://learn.'
    'microsoft.com/azure/aks/operator-best-practices-multi-region"}, {"id": "02.02.02", "guid": "578a219a'
    '-46be-4b54-9350-24922634292b", "text": "Use Availability Zones if they are supported in your Azure r'
    'egion", "category": "BC and DR", "subcategory": "High Availability", "waf": "Reliability", "severity'
    '": "Medium", "link": "https://learn.microsoft.com/azure/aks/availability-zones"}, {"id": "02.02.03",'
    ' "guid": "71d41e36-10cc-457b-9a4b-1410d4395898", "text": "Use the SLA-backed AKS offering", "categor'
    'y": "BC and DR", "subcategory": "High Availability", "waf": "Reliability", "severity": "High", "link'
    '": "https://learn.microsoft.com/azure/aks/uptime-sla"}, {"id": "02.02.04", "guid": "c1288b3c-6a57-4c'
    'fc-9444-51e1a3d3453a", "text": "Use Disruption Budgets in your pod and deployment definitions", "cat'
    'egory": "BC and DR", "subcategory": "High Availability", "waf": "Reliability", "severity": "Low", "l'
    'ink": "https://learn.microsoft.com/azure/aks/operator-best-practices-scheduler"}, {"id": "02.02.05",'
    ' "guid": "3c763963-7a55-42d5-a15e-401955387e5c", "text": "If using a private registry, configure reg'
    'ion replication to store images in multiple regions", "category": "BC and DR", "subcategory": "High '
    'Availability", "waf": "Reliability", "severity": "High", "link": "https://learn.microsoft.com/azure/'
    'container-registry/container-registry-geo-replication"}, {"id": "02.02.06", "guid": "daa9a260-c3ea-4'
    '490-b077-5fc1f2a80cb0", "text": "Use Zone-Redundant Storage (ZRS) with stateful workloads", "categor'
    'y": "BC and DR", "subcategory": "Disaster Recovery", "waf": "Reliability", "severity": "High", "link'
    '": "https://learn.microsoft.com/azure/aks/availability-zones#azure-disk-availability-zone-support"},'
    ' {"id": "02.03.01", "guid": "bc14aea6-e65d-48d9-a3ad-c218e6436b06", "text": "Define non-functional r'
    'equirements such as SLAs, RTO (Recovery Time Objective) and RPO (Recovery Point Objective).", "categ'
    'ory": "BC and DR", "subcategory": "Requirements", "waf": "Reliability", "severity": "High", "link": '
    '"https://learn.microsoft.com/azure/cloud-adoption-framework/ready/enterprise-scale/business-continui'
    'ty-and-disaster-recovery"}, {"id": "03.01.01", "guid": "f82cb8eb-8c0a-4a63-a25a-4956eaa8dc4a", "text'
    '": "Use an external application such as kubecost to allocate costs to different users", "category": '
    '"Cost Governance", "subcategory": "Cost", "waf": "Cost", "severity": "Low", "link": "https://learn.m'
    'icrosoft.com/azure/cloud-adoption-framework/scenarios/aks/eslz-cost-governance-with-kubecost"}, {"id'
    '": "03.01.02", "guid": "4d3dfbab-9924-4831-a68d-fdf0d72f462c", "text": "Use scale down mode to delet'
    'e/deallocate nodes", "category": "Cost Governance", "subcategory": "Cost", "waf": "Cost", "severity"'
    ': "Low", "link": "https://learn.microsoft.com/azure/aks/scale-down-mode"}, {"id": "03.01.03", "guid"'
    ': "87e651ea-bc4a-4a87-a6df-c06a4b570ebc", "text": "When required use multi-instance partitioning GPU'
    ' on AKS Clusters", "category": "Cost Governance", "subcategory": "Cost", "waf": "Cost", "severity": '
    '"Medium", "link": "https://learn.microsoft.com/azure/aks/gpu-multi-instance"}, {"id": "03.01.04", "g'
    'uid": "2b72a08b-0410-4cd6-9093-e068a5cf27e8", "text": "If running a Dev/Test cluster use NodePool St'
    'art/Stop", "category": "Cost Governance", "subcategory": "Cost", "waf": "Cost", "severity": "Low", "'
    'link": "https://learn.microsoft.com/azure/aks/start-stop-nodepools"}, {"id": "04.01.01", "guid": "9c'
    'a48e4a-85e2-4223-bce8-bb12307ca5f1", "text": "Use Azure Policy for Kubernetes to ensure cluster comp'
    'liance", "category": "Governance and Security", "subcategory": "Compliance", "waf": "Security", "sev'
    'erity": "Medium", "link": "https://learn.microsoft.com/azure/governance/policy/concepts/policy-for-k'
    'ubernetes"}, {"id": "04.01.02", "guid": "6f158e3e-a3a9-42c2-be7e-2165c3a87af4", "text": "Separate ap'
    'plications from the control plane with user/system node pools", "category": "Governance and Security'
    '", "subcategory": "Compliance", "waf": "Security", "severity": "Medium", "link": "https://learn.micr'
    'osoft.com/azure/aks/use-system-pools"}, {"id": "04.01.03", "guid": "a7a1f893-9bda-4477-98f2-4c116775'
    'c2ea", "text": "Add taint to your system nodepool to make it dedicated", "category": "Governance and'
    ' Security", "subcategory": "Compliance", "waf": "Security", "severity": "Low", "link": "https://lear'
    'n.microsoft.com/azure/aks/use-system-pools"}, {"id": "04.01.04", "guid": "55b46a94-8008-4ae7-b7e4-b4'
    '75b6c8bdbf", "text": "Use a private registry for your images, such as ACR", "category": "Governance '
    'and Security", "subcategory": "Compliance", "waf": "Security", "severity": "Medium", "link": "https:'
    '//learn.microsoft.com/azure/container-registry/"}, {"id": "04.01.05", "guid": "59bce65d-e8a0-43f9-98'
    '79-468d66a786d6", "text": "Scan your images for vulnerabilities", "category": "Governance and Securi'
    'ty", "subcategory": "Compliance", "waf": "Security", "severity": "Medium", "link": "https://learn.mi'
    'crosoft.com/azure/security-center/container-security"}, {"id": "04.01.06", "guid": "cc639637-a652-42'
    'ac-89e8-06965388e9de", "text": "Use Azure Security Center to detect security posture vulnerabilities'
    '", "category": "Governance and Security", "subcategory": "Compliance", "waf": "Security", "severity"'
    ': "Medium", "link": "https://learn.microsoft.com/azure/security-center/container-security"}, {"id": '
    '"04.01.07", "guid": "42d4aefe-2383-470e-b019-c30df24996b2", "text": "If required configure FIPS", "c'
    'ategory": "Governance and Security", "subcategory": "Compliance", "waf": "Security", "severity": "Lo'
    'w", "link": "https://learn.microsoft.com/azure/aks/use-multiple-node-pools#add-a-fips-enabled-node-p'
    'ool"}, {"id": "04.01.08", "guid": "d167dd18-2b0a-4c24-8b99-9a646f8389a7", "text": "Define app separa'
    'tion requirements (namespace/nodepool/cluster)", "category": "Governance and Security", "subcategory'
    '": "Compliance", "waf": "Security", "severity": "High", "link": "https://learn.microsoft.com/azure/a'
    'ks/operator-best-practices-cluster-isolation"}, {"id": "04.02.01", "guid": "5e3df584-eccc-4d97-a3b6-'
    'bcda3b50eb2e", "text": "Store your secrets in Azure Key Vault with the CSI Secrets Store driver", "c'
    'ategory": "Governance and Security", "subcategory": "Secrets", "waf": "Security", "severity": "Mediu'
    'm", "link": "https://github.com/Azure/secrets-store-csi-driver-provider-azure"}, {"id": "04.02.02", '
    '"guid": "b03dda6d-58d7-4c89-8ddb-107d5769ae66", "text": "If using Service Principals for the cluster'
    ', refresh credentials periodically (like quarterly)", "category": "Governance and Security", "subcat'
    'egory": "Secrets", "waf": "Security", "severity": "High", "link": "https://learn.microsoft.com/azure'
    '/aks/update-credentials"}, {"id": "04.02.03", "guid": "e7ba73a3-0508-4f80-806f-527db30cee96", "text"'
    ': "If required add Key Management Service etcd encryption", "category": "Governance and Security", "'
    'subcategory": "Secrets", "waf": "Security", "severity": "Medium", "link": "https://learn.microsoft.c'
    'om/azure/aks/use-kms-etcd-encryption"}, {"id": "04.02.04", "guid": "ec8e4e42-0344-41b0-b865-9123e895'
    '6d31", "text": "If required consider using Confidential Compute for AKS", "category": "Governance an'
    'd Security", "subcategory": "Secrets", "waf": "Security", "severity": "Low", "link": "https://learn.'
    'microsoft.com/azure/confidential-computing/confidential-nodes-aks-overview"}, {"id": "04.02.05", "gu'
    'id": "c9e95ffe-6dd1-4a17-8c5f-110389ca9b21", "text": "Consider using Defender for Containers", "cate'
    'gory": "Governance and Security", "subcategory": "Secrets", "waf": "Security", "severity": "Medium",'
    ' "link": "https://learn.microsoft.com/azure/defender-for-cloud/defender-for-containers-enable"}, {"i'
    'd": "05.01.01", "guid": "ed127dd1-42b0-46b2-8c69-99a646f3389a", "text": "Use managed identities inst'
    'ead of Service Principals", "category": "Identity and Access Management", "subcategory": "Identity",'
    ' "waf": "Security", "severity": "High", "link": "https://learn.microsoft.com/azure/aks/use-managed-i'
    'dentity"}, {"id": "05.01.02", "guid": "7e42c78e-78c0-46a6-8a21-94956e698dc4", "text": "Integrate aut'
    'hentication with AAD (using the managed integration)", "category": "Identity and Access Management",'
    ' "subcategory": "Identity", "waf": "Security", "severity": "Medium", "link": "https://learn.microsof'
    't.com/azure/aks/managed-aad"}, {"id": "05.01.03", "guid": "a2fe27b2-e287-401a-8352-beedf79b488d", "t'
    'ext": "Limit access to admin kubeconfig (get-credentials --admin)", "category": "Identity and Access'
    ' Management", "subcategory": "Identity", "waf": "Security", "severity": "Medium", "link": "https://l'
    'earn.microsoft.com/azure/aks/control-kubeconfig-access"}, {"id": "05.01.04", "guid": "eec4962c-c3bd-'
    '421b-b77f-26e5e6b3bec3", "text": "Integrate authorization with AAD RBAC", "category": "Identity and '
    'Access Management", "subcategory": "Identity", "waf": "Security", "severity": "Medium", "link": "htt'
    'ps://learn.microsoft.com/azure/aks/manage-azure-rbac"}, {"id": "05.01.05", "guid": "d4f3537c-1346-4d'
    'c5-9027-a71ffe1bd05d", "text": "Use namespaces for restricting RBAC privilege in Kubernetes", "categ'
    'ory": "Identity and Access Management", "subcategory": "Identity", "waf": "Security", "severity": "H'
    'igh", "link": "https://learn.microsoft.com/azure/aks/operator-best-practices-identity"}, {"id": "05.'
    '01.06", "guid": "d2e0d5d7-71d4-41e3-910c-c57b4a4b1410", "text": "For Pod Identity Access Management '
    'use Azure AD Workload Identity (preview)", "category": "Identity and Access Management", "subcategor'
    'y": "Identity", "waf": "Security", "severity": "Medium", "link": "https://learn.microsoft.com/azure/'
    'aks/workload-identity-migration-sidecar"}, {"id": "05.01.07", "guid": "f4dcf690-1b30-407d-abab-6f8aa'
    '780d3a3", "text": "For AKS non-interactive logins use kubelogin (preview)", "category": "Identity an'
    'd Access Management", "subcategory": "Identity", "waf": "Security", "severity": "Medium", "link": "h'
    'ttps://learn.microsoft.com/azure/aks/managed-aad#non-interactive-sign-in-with-kubelogin"}, {"id": "0'
    '5.01.08", "guid": "b085b1f2-3119-4771-8c9a-bbf4411810ec", "text": "Disable AKS local accounts", "cat'
    'egory": "Identity and Access Management", "subcategory": "Identity", "waf": "Security", "severity": '
    '"Medium", "link": "https://learn.microsoft.com/azure/aks/managed-aad#disable-local-accounts"}, {"id"'
    ': "05.01.09", "guid": "36abb0db-c118-4f4c-9880-3f30f9a2deb6", "text": "Configure if required Just-in'
    '-time cluster access", "category": "Identity and Access Management", "subcategory": "Identity", "waf'
    '": "Security", "severity": "Low", "link": "https://learn.microsoft.com/azure/aks/managed-aad#configu'
    're-just-in-time-cluster-access-with-azure-ad-and-aks"}, {"id": "05.01.10", "guid": "c4d7f4c6-79bf-45'
    'd0-aa05-ce8fc717e150", "text": "Configure if required AAD conditional access for AKS", "category": "'
    'Identity and Access Management", "subcategory": "Identity", "waf": "Security", "severity": "Low", "l'
    'ink": "https://learn.microsoft.com/azure/aks/managed-aad#use-conditional-access-with-azure-ad-and-ak'
    's"}, {"id": "05.01.11", "guid": "e1123a7c-a333-4eb4-a120-4ee3f293c9f3", "text": "If required for Win'
    'dows AKS workloads configure gMSA ", "category": "Identity and Access Management", "subcategory": "I'
    'dentity", "waf": "Security", "severity": "Low", "link": "https://learn.microsoft.com/azure/aks/use-g'
    'roup-managed-service-accounts"}, {"id": "05.01.12", "guid": "1f711a74-3672-470b-b8b8-a2148d640d79", '
    '"text": "For finer control consider using a managed Kubelet Identity", "category": "Identity and Acc'
    'ess Management", "subcategory": "Identity", "waf": "Security", "severity": "Medium", "link": "https:'
    '//learn.microsoft.com/azure/aks/use-managed-identity#use-a-pre-created-kubelet-managed-identity"}, {'
    '"id": "06.01.01", "guid": "cbd8ac2a-aebc-4a2a-94da-1dbf3dc99248", "text": "If using AGIC, do not sha'
    're an AppGW across clusters", "category": "Network Topology and Connectivity", "subcategory": "Best '
    'practices", "waf": "Reliability", "severity": "Medium", "link": "https://azure.github.io/application'
    '-gateway-kubernetes-ingress/setup/install-existing/"}, {"id": "06.01.02", "guid": "8008ae7d-7e4b-447'
    '5-a6c8-bdbf59bce65d", "text": "Do not use AKS HTTP Routing Add-On, use instead the managed NGINX ing'
    'ress with the application routing add-on.", "category": "Network Topology and Connectivity", "subcat'
    'egory": "Best practices", "waf": "Reliability", "severity": "High", "link": "https://learn.microsoft'
    '.com/azure/aks/http-application-routing"}, {"id": "06.01.03", "guid": "7bacd7b9-c025-4a9d-a5d2-25d6b'
    'c5439d9", "text": "For Windows workloads use Accelerated Networking", "category": "Network Topology '
    'and Connectivity", "subcategory": "Best practices", "waf": "Performance", "severity": "Medium", "lin'
    'k": "https://learn.microsoft.com/azure/virtual-network/accelerated-networking-overview"}, {"id": "06'
    '.01.04", "guid": "ba7da7be-9952-4914-a384-5d997cb39132", "text": "Use the standard ALB (as opposed t'
    'o the basic one)", "category": "Network Topology and Connectivity", "subcategory": "Best practices",'
    ' "waf": "Reliability", "severity": "High", "link": "https://learn.microsoft.com/azure/aks/load-balan'
    'cer-standard"}, {"id": "06.01.05", "guid": "22fbe8d6-9b40-47ef-9011-25bb1a555a6b", "text": "If using'
    ' Azure CNI, consider using different Subnets for NodePools", "category": "Network Topology and Conne'
    'ctivity", "subcategory": "Best practices", "waf": "Security", "severity": "Medium", "link": "https:/'
    '/learn.microsoft.com/azure/aks/use-multiple-node-pools#add-a-node-pool-with-a-unique-subnet"}, {"id"'
    ': "06.02.01", "guid": "c3c39c98-6bb2-4c12-859a-114b5e3df584", "text": "Use Private Endpoints (prefer'
    'red) or Virtual Network Service Endpoints to access PaaS services from the cluster", "category": "Ne'
    'twork Topology and Connectivity", "subcategory": "Cost", "waf": "Security", "severity": "Medium", "l'
    'ink": "https://learn.microsoft.com/azure/private-link/private-link-overview"}, {"id": "06.03.01", "g'
    'uid": "e8a03f97-8794-468d-96a7-86d60f96c97b", "text": "If hybrid connectivity is required, use 2xER '
    'or ER+VPN for better availability", "category": "Network Topology and Connectivity", "subcategory": '
    '"HA", "waf": "Reliability", "severity": "Medium", "link": "https://learn.microsoft.com/azure/express'
    'route/designing-for-disaster-recovery-with-expressroute-privatepeering"}, {"id": "06.04.01", "guid":'
    ' "a0f61565-9de5-458f-a372-49c831112dbd", "text": "Choose the best CNI network plugin for your requir'
    'ements (Azure CNI recommended)", "category": "Network Topology and Connectivity", "subcategory": "IP'
    'AM", "waf": "Reliability", "severity": "High", "link": "https://learn.microsoft.com/azure/aks/operat'
    'or-best-practices-network"}, {"id": "06.04.02", "guid": "7faf12e7-0943-4f63-8472-2da29c2b1cd6", "tex'
    't": "If using Azure CNI, size your subnet accordingly considering the maximum number of pods per nod'
    'e", "category": "Network Topology and Connectivity", "subcategory": "IPAM", "waf": "Performance", "s'
    'everity": "High", "link": "https://learn.microsoft.com/azure/aks/configure-azure-cni"}, {"id": "06.0'
    '4.03", "guid": "22f54b29-bade-43aa-b1e8-c38ec9366673", "text": "If using Azure CNI, check the maximu'
    'm pods/node (default 30)", "category": "Network Topology and Connectivity", "subcategory": "IPAM", "'
    'waf": "Performance", "severity": "High", "link": "https://learn.microsoft.com/azure/aks/configure-az'
    'ure-cni"}, {"id": "06.04.04", "guid": "13c00567-4b1e-4945-a459-c373e7ed6162", "text": "If using priv'
    'ate-IP LoadBalancer services, use a dedicated subnet (not the AKS subnet)", "category": "Network Top'
    'ology and Connectivity", "subcategory": "IPAM", "waf": "Security", "severity": "Low", "link": "https'
    '://learn.microsoft.com/azure/aks/internal-lb"}, {"id": "06.04.05", "guid": "43f63047-22d9-429c-8b1c-'
    'd622f54b29ba", "text": "Size the service IP address range accordingly (it is going to limit the clus'
    'ter scalability)", "category": "Network Topology and Connectivity", "subcategory": "IPAM", "waf": "R'
    'eliability", "severity": "High", "link": "https://learn.microsoft.com/azure/aks/configure-azure-cni"'
    '}, {"id": "06.05.01", "guid": "57bf217f-6dc8-481c-81e2-785773e9c00f", "text": "If required add your '
    'own CNI plugin", "category": "Network Topology and Connectivity", "subcategory": "Operations", "waf"'
    ': "Security", "severity": "Low", "link": "https://learn.microsoft.com/azure/aks/use-byo-cni"}, {"id"'
    ': "06.05.02", "guid": "4b3bb365-9458-44d9-9ed1-5c8f52890364", "text": "If required configure Public '
    'IP per node in AKS", "category": "Network Topology and Connectivity", "subcategory": "Operations", "'
    'waf": "Performance", "severity": "Low", "link": "https://learn.microsoft.com/azure/aks/use-multiple-'
    'node-pools#assign-a-public-ip-per-node-for-your-node-pools"}, {"id": "06.06.01", "guid": "b3808b9f-a'
    '1cf-4204-ad01-3a923ce474db", "text": "Use an ingress controller to expose web-based apps instead of '
    'exposing them with LoadBalancer-type services", "category": "Network Topology and Connectivity", "su'
    'bcategory": "Scalability", "waf": "Reliability", "severity": "Medium", "link": "https://learn.micros'
    'oft.com/azure/aks/concepts-network"}, {"id": "06.06.02", "guid": "ccb534e7-416e-4a1d-8e93-533b531990'
    '85", "text": "Use Azure NAT Gateway as outboundType for scaling egress traffic", "category": "Networ'
    'k Topology and Connectivity", "subcategory": "Scalability", "waf": "Reliability", "severity": "Low",'
    ' "link": "https://learn.microsoft.com/azure/aks/nat-gateway"}, {"id": "06.06.03", "guid": "8ee9a69a-'
    '1b58-4b1e-9c61-476e110a160b", "text": "Use Dynamic allocations of IPs in order to avoid Azure CNI IP'
    ' exhaustion", "category": "Network Topology and Connectivity", "subcategory": "Scalability", "waf": '
    '"Reliability", "severity": "Medium", "link": "https://learn.microsoft.com/azure/aks/configure-azure-'
    'cni#dynamic-allocation-of-ips-and-enhanced-subnet-support"}, {"id": "06.07.01", "guid": "3b365a91-7e'
    'cb-4e48-bbe5-4cd7df2e8bba", "text": "Filter egress traffic with AzFW/NVA if your security requiremen'
    'ts mandate it", "category": "Network Topology and Connectivity", "subcategory": "Security", "waf": "'
    'Security", "severity": "High", "link": "https://learn.microsoft.com/azure/aks/limit-egress-traffic"}'
    ', {"id": "06.07.02", "guid": "c4581559-bb91-463e-a908-aed8c44ce3b2", "text": "If using a public API '
    'endpoint, restrict the IP addresses that can access it", "category": "Network Topology and Connectiv'
    'ity", "subcategory": "Security", "waf": "Security", "severity": "Medium", "link": "https://learn.mic'
    'rosoft.com/azure/aks/api-server-authorized-ip-ranges"}, {"id": "06.07.03", "guid": "ecccd979-3b6b-4c'
    'da-9b50-eb2eb03dda6d", "text": "Use private clusters if your requirements mandate it", "category": "'
    'Network Topology and Connectivity", "subcategory": "Security", "waf": "Security", "severity": "High"'
    ', "link": "https://learn.microsoft.com/azure/aks/private-clusters"}, {"id": "06.07.04", "guid": "ce7'
    'f2a7c-297c-47c6-adea-a6ff838db665", "text": "For Windows 2019 and 2022 AKS nodes Calico Network Poli'
    'cies can be used ", "category": "Network Topology and Connectivity", "subcategory": "Security", "waf'
    '": "Security", "severity": "Medium", "link": "https://learn.microsoft.com/azure/aks/use-network-poli'
    'cies"}, {"id": "06.07.05", "guid": "58d7c892-ddb1-407d-9769-ae669ca48e4a", "text": "Enable a Kuberne'
    'tes Network Policy option (Calico/Azure)", "category": "Network Topology and Connectivity", "subcate'
    'gory": "Security", "waf": "Security", "severity": "High", "link": "https://learn.microsoft.com/azure'
    '/aks/use-network-policies"}, {"id": "06.07.06", "guid": "85e2223e-ce8b-4b12-907c-a5f16f158e3e", "tex'
    't": "Use Kubernetes network policies to increase intra-cluster security", "category": "Network Topol'
    'ogy and Connectivity", "subcategory": "Security", "waf": "Security", "severity": "High", "link": "ht'
    'tps://learn.microsoft.com/azure/aks/operator-best-practices-network"}, {"id": "06.07.07", "guid": "a'
    '3a92c2d-e7e2-4165-a3a8-7af4a7a1f893", "text": "Use a WAF for web workloads (UIs or APIs)", "category'
    '": "Network Topology and Connectivity", "subcategory": "Security", "waf": "Security", "severity": "H'
    'igh", "link": "https://learn.microsoft.com/azure/aks/operator-best-practices-network"}, {"id": "06.0'
    '7.08", "guid": "9bda4776-8f24-4c11-9775-c2ea55b46a94", "text": "Use DDoS Standard in the AKS Virtual'
    ' Network", "category": "Network Topology and Connectivity", "subcategory": "Security", "waf": "Secur'
    'ity", "severity": "Medium", "link": "https://learn.microsoft.com/azure/virtual-network/ddos-protecti'
    'on-overview"}, {"id": "06.07.09", "guid": "6c46b91a-1107-4485-ad66-3183e2a8c266", "text": "If requir'
    'ed add company HTTP Proxy", "category": "Network Topology and Connectivity", "subcategory": "Securit'
    'y", "waf": "Security", "severity": "Low", "link": "https://learn.microsoft.com/azure/aks/http-proxy"'
    '}, {"id": "06.07.10", "guid": "e9855d04-c3c3-49c9-a6bb-2c12159a114b", "text": "Consider using a serv'
    'ice mesh for advanced microservice communication management", "category": "Network Topology and Conn'
    'ectivity", "subcategory": "Security", "waf": "Security", "severity": "Medium", "link": "https://lear'
    'n.microsoft.com/azure/aks/servicemesh-about"}, {"id": "07.01.01", "guid": "67f7a9ed-5b31-4f38-a3f3-9'
    '812b2463cff", "text": "Configure alerts on the most critical metrics (see Container Insights for rec'
    'ommendations)", "category": "Operations", "subcategory": "Alerting", "waf": "Operations", "severity"'
    ': "High", "link": "https://learn.microsoft.com/azure/azure-monitor/insights/container-insights-metri'
    'c-alerts"}, {"id": "07.02.01", "guid": "337453a3-cc63-4963-9a65-22ac19e80696", "text": "Check regula'
    'rly Azure Advisor for recommendations on your cluster", "category": "Operations", "subcategory": "Co'
    'mpliance", "waf": "Operations", "severity": "Low", "link": "https://learn.microsoft.com/azure/adviso'
    'r/advisor-get-started"}, {"id": "07.02.03", "guid": "3aa70560-e7e7-4968-be3d-628af35b2ced", "text": '
    '"Enable AKS auto-certificate rotation", "category": "Operations", "subcategory": "Compliance", "waf"'
    ': "Operations", "severity": "Low", "link": "https://learn.microsoft.com/azure/aks/certificate-rotati'
    'on"}, {"id": "07.02.04", "guid": "e189c599-df0d-45a7-9dd4-ce32c1881370", "text": "Have a regular pro'
    'cess to upgrade your kubernetes version periodically (quarterly, for example), or use the AKS autoup'
    'grade feature", "category": "Operations", "subcategory": "Compliance", "waf": "Operations", "severit'
    'y": "High", "link": "https://learn.microsoft.com/azure/aks/supported-kubernetes-versions"}, {"id": "'
    '07.02.05", "guid": "6f7c4c0d-4e51-4464-ad24-57ed67138b82", "text": "Use kured for Linux node upgrade'
    's in case you are not using node-image upgrade", "category": "Operations", "subcategory": "Complianc'
    'e", "waf": "Operations", "severity": "High", "link": "https://learn.microsoft.com/azure/aks/node-upd'
    'ates-kured"}, {"id": "07.02.06", "guid": "139c9580-ade3-426a-ba09-cf157d9f6477", "text": "Have a reg'
    'ular process to upgrade the cluster node images periodically (weekly, for example)", "category": "Op'
    'erations", "subcategory": "Compliance", "waf": "Operations", "severity": "High", "link": "https://le'
    'arn.microsoft.com/azure/aks/node-image-upgrade"}, {"id": "07.02.07", "guid": "0102ce16-ee30-41e6-b88'
    '2-e52e4621dd68", "text": "Consider gitops to deploy applications or cluster configuration to multipl'
    'e clusters", "category": "Operations", "subcategory": "Compliance", "waf": "Operations", "severity":'
    ' "Low", "link": "https://learn.microsoft.com/azure/architecture/example-scenario/bedrock/bedrock-aut'
    'omated-deployments"}, {"id": "07.02.08", "guid": "d7672c26-7602-4482-85a4-14527fbe855c", "text": "Co'
    'nsider using AKS command invoke on private clusters", "category": "Operations", "subcategory": "Comp'
    'liance", "waf": "Operations", "severity": "Low", "link": "https://learn.microsoft.com/azure/aks/comm'
    'and-invoke"}, {"id": "07.02.09", "guid": "31d7aaab-7571-4449-ab80-53d89e89d17b", "text": "For planne'
    'd events consider using Node Auto Drain", "category": "Operations", "subcategory": "Compliance", "wa'
    'f": "Operations", "severity": "Low", "link": "https://learn.microsoft.com/azure/aks/node-auto-repair'
    '#node-autodrain"}, {"id": "07.02.10", "guid": "ed0fda7f-211b-47c7-8b6e-c18873fb473c", "text": "Devel'
    "op own governance practices to make sure no changes are performed by operators in the node RG (aka '"
    'infra RG\')", "category": "Operations", "subcategory": "Compliance", "waf": "Operations", "severity":'
    ' "High", "link": "https://learn.microsoft.com/azure/aks/faq"}, {"id": "07.02.11", "guid": "73b32a5a-'
    '67f7-4a9e-b5b3-1f38c3f39812", "text": "Use custom Node RG (aka \'Infra RG\') name", "category": "Opera'
    'tions", "subcategory": "Compliance", "waf": "Operations", "severity": "Low", "link": "https://learn.'
    'microsoft.com/azure/aks/cluster-configuration"}, {"id": "07.02.12", "guid": "b2463cff-e189-4c59-adf0'
    '-d5a73dd4ce32", "text": "Do not use deprecated Kubernetes APIs in your YAML manifests", "category": '
    '"Operations", "subcategory": "Compliance", "waf": "Operations", "severity": "Medium", "link": "https'
    '://kubernetes.io/docs/setup/release/notes/"}, {"id": "07.02.13", "guid": "c1881370-6f7c-44c0-b4e5-14'
    '648d2457ed", "text": "Taint Windows nodes", "category": "Operations", "subcategory": "Compliance", "'
    'waf": "Operations", "severity": "Low", "link": "https://learn.microsoft.com/azure-stack/aks-hci/adap'
    't-apps-mixed-os-clusters"}, {"id": "07.02.14", "guid": "67138b82-0102-4ce1-9ee3-01e6e882e52e", "text'
    '": "Keep windows containers patch level in sync with host patch level", "category": "Operations", "s'
    'ubcategory": "Compliance", "waf": "Operations", "severity": "Low", "link": "https://learn.microsoft.'
    'com/virtualization/windowscontainers/deploy-containers/version-compatibility?tabs=windows-server-20H'
    '2%2Cwindows-10-20H2"}, {"id": "07.02.15", "guid": "5b56ad48-408f-4e72-934c-476ba280dcf5", "text": "S'
    'end master logs (aka API logs) to Azure Monitor or your preferred log management solution", "categor'
    'y": "Operations", "subcategory": "Compliance", "waf": "Operations", "severity": "Low", "link": "http'
    's://learn.microsoft.com/azure/aks/monitor-aks"}, {"id": "07.02.16", "guid": "64d1a846-e28a-4b6b-9a33'
    '-22a635c15a21", "text": "If required use nodePool snapshots", "category": "Operations", "subcategory'
    '": "Compliance", "waf": "Cost", "severity": "Low", "link": "https://learn.microsoft.com/azure/aks/no'
    'de-pool-snapshot"}, {"id": "07.03.01", "guid": "c5a5b252-1e44-4a59-a9d2-399c4d7b68d0", "text": "Cons'
    'ider spot node pools for non time-sensitive workloads", "category": "Operations", "subcategory": "Co'
    'st", "waf": "Operations", "severity": "Low", "link": "https://learn.microsoft.com/azure/aks/spot-nod'
    'e-pool"}, {"id": "07.03.02", "guid": "c755562f-2b4e-4456-9b4d-874a748b662e", "text": "Consider AKS v'
    'irtual node for quick bursting", "category": "Operations", "subcategory": "Cost", "waf": "Operations'
    '", "severity": "Low", "link": "https://learn.microsoft.com/azure/aks/concepts-scale"}, {"id": "07.04'
    '.01", "guid": "6f8389a7-f82c-4b8e-a8c0-aa63a25a4956", "text": "Monitor your cluster metrics with Con'
    'tainer Insights (or other tools like Prometheus)", "category": "Operations", "subcategory": "Monitor'
    'ing", "waf": "Operations", "severity": "High", "link": "https://learn.microsoft.com/azure/azure-moni'
    'tor/insights/container-insights-overview"}, {"id": "07.04.02", "guid": "eaa8dc4a-2436-47b3-9697-15b1'
    '752beee0", "text": "Store and analyze your cluster logs with Container Insights (or other tools like'
    ' Telegraf/ElasticSearch)", "category": "Operations", "subcategory": "Monitoring", "waf": "Operations'
    '", "severity": "High", "link": "https://learn.microsoft.com/azure/azure-monitor/insights/container-i'
    'nsights-overview"}, {"id": "07.04.03", "guid": "4621dd68-c5a5-4be2-bdb1-1726769ef669", "text": "Moni'
    'tor CPU and memory utilization of the nodes", "category": "Operations", "subcategory": "Monitoring",'
    ' "waf": "Operations", "severity": "Medium", "link": "https://learn.microsoft.com/azure/azure-monitor'
    '/containers/container-insights-analyze"}, {"id": "07.04.04", "guid": "1a4835ac-9422-423e-ae80-b12308'
    '1a5417", "text": "If using Azure CNI, monitor % of pod IPs consumed per node", "category": "Operatio'
    'ns", "subcategory": "Monitoring", "waf": "Operations", "severity": "Medium", "link": "https://learn.'
    'microsoft.com/azure/aks/configure-azure-cni"}, {"id": "07.04.05", "guid": "415833ea-3ad3-4c2d-b733-1'
    '65c3acbe04b", "text": "Monitor OS disk queue depth in nodes", "category": "Operations", "subcategory'
    '": "Monitoring", "waf": "Operations", "severity": "Medium", "link": "https://learn.microsoft.com/azu'
    're/virtual-machines/premium-storage-performance"}, {"id": "07.04.06", "guid": "be209d39-fda4-4777-a4'
    '24-d116785c2fa5", "text": "If not using egress filtering with AzFW/NVA, monitor standard ALB allocat'
    'ed SNAT ports", "category": "Operations", "subcategory": "Monitoring", "waf": "Operations", "severit'
    'y": "Medium", "link": "https://learn.microsoft.com/azure/aks/load-balancer-standard"}, {"id": "07.04'
    '.07", "guid": "74c2ee76-569b-4a79-a57e-dedf91b022c9", "text": "Subscribe to resource health notifica'
    'tions for your AKS cluster", "category": "Operations", "subcategory": "Monitoring", "waf": "Operatio'
    'ns", "severity": "Medium", "link": "https://learn.microsoft.com/azure/aks/aks-resource-health"}, {"i'
    'd": "07.05.01", "guid": "b54eb2eb-03dd-4aa3-9927-18e2edb11726", "text": "Configure requests and limi'
    'ts in your pod specs", "category": "Operations", "subcategory": "Resources", "waf": "Operations", "s'
    'everity": "High", "link": "https://learn.microsoft.com/azure/aks/operator-best-practices-scheduler"}'
    ', {"id": "07.05.02", "guid": "769ef669-1a48-435a-a942-223ece80b123", "text": "Enforce resource quota'
    's for namespaces", "category": "Operations", "subcategory": "Resources", "waf": "Operations", "sever'
    'ity": "Medium", "link": "https://learn.microsoft.com/azure/aks/operator-best-practices-scheduler"}, '
    '{"id": "07.05.03", "guid": "081a5417-4158-433e-a3ad-3c2de733165c", "text": "Ensure your subscription'
    ' has enough quota to scale out your nodepools", "category": "Operations", "subcategory": "Resources"'
    ', "waf": "Operations", "severity": "High", "link": "https://learn.microsoft.com/azure/azure-resource'
    '-manager/management/azure-subscription-service-limits"}, {"id": "07.05.04", "guid": "f4fd0602-7ab5-4'
    '6f1-b66a-e9dea9654a65", "text": "Configure Liveness and Readiness probes for all deployments", "cate'
    'gory": "Operations", "subcategory": "Resources", "waf": "Operations", "severity": "High", "link": "h'
    'ttps://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/'
    '"}, {"id": "07.06.01", "guid": "90ce65de-8e13-4f9c-abd4-69266abca264", "text": "Use the Cluster Auto'
    'scaler", "category": "Operations", "subcategory": "Scalability", "waf": "Performance", "severity": "'
    'Medium", "link": "https://learn.microsoft.com/azure/aks/concepts-scale"}, {"id": "07.06.02", "guid":'
    ' "831c2872-c693-4b39-a887-a561bada49bc", "text": "Customize node configuration for AKS node pools", '
    '"category": "Operations", "subcategory": "Scalability", "waf": "Performance", "severity": "Low", "li'
    'nk": "https://learn.microsoft.com/azure/aks/custom-node-configuration"}, {"id": "07.06.03", "guid": '
    '"faa19bfe-9d55-4d04-a3c4-919ca1b2d121", "text": "Use the Horizontal Pod Autoscaler when required", "'
    'category": "Operations", "subcategory": "Scalability", "waf": "Performance", "severity": "Medium", "'
    'link": "https://learn.microsoft.com/azure/aks/concepts-scale"}, {"id": "07.06.04", "guid": "5ae124ba'
    '-34df-4585-bcdc-e9bd3bb0cdb3", "text": "Consider an appropriate node size, not too large or too smal'
    'l", "category": "Operations", "subcategory": "Scalability", "waf": "Performance", "severity": "High"'
    ', "link": "https://blog.cloudtrooper.net/2020/10/23/which-vm-size-should-i-choose-as-aks-node/"}, {"'
    'id": "07.06.05", "guid": "38800e6a-ae01-40a2-9fbc-ae5a06e5462d", "text": "If more than 5000 nodes ar'
    'e required for scalability then consider using an additional AKS cluster", "category": "Operations",'
    ' "subcategory": "Scalability", "waf": "Performance", "severity": "Low", "link": "https://learn.micro'
    'soft.com/azure/aks/quotas-skus-regions#service-quotas-and-limits"}, {"id": "07.06.06", "guid": "9583'
    'c0f6-6083-43f6-aa6b-df7102c901bb", "text": "Consider subscribing to EventGrid Events for AKS automat'
    'ion", "category": "Operations", "subcategory": "Scalability", "waf": "Performance", "severity": "Low'
    '", "link": "https://learn.microsoft.com/azure/event-grid/event-schema-aks"}, {"id": "07.06.07", "gui'
    'd": "c5016d8c-c6c9-4165-89ae-673ef0fff19d", "text": "For long running operation on an AKS cluster co'
    'nsider event termination", "category": "Operations", "subcategory": "Scalability", "waf": "Performan'
    'ce", "severity": "Low", "link": "https://learn.microsoft.com/azure/aks/manage-abort-operations"}, {"'
    'id": "07.06.08", "guid": "c4e37133-f186-4ce1-aed9-9f1b32f6e021", "text": "If required consider using'
    ' Azure Dedicated Hosts for AKS nodes", "category": "Operations", "subcategory": "Scalability", "waf"'
    ': "Performance", "severity": "Low", "link": "https://learn.microsoft.com/azure/aks/use-azure-dedicat'
    'ed-hosts"}, {"id": "07.07.01", "guid": "24367b33-6971-45b1-952b-eee0b9b588de", "text": "Use ephemera'
    'l OS disks", "category": "Operations", "subcategory": "Storage", "waf": "Performance", "severity": "'
    'High", "link": "https://learn.microsoft.com/azure/aks/cluster-configuration"}, {"id": "07.07.02", "g'
    'uid": "f0ce315f-1120-4166-8206-94f2cf3a4d07", "text": "For non-ephemeral disks, use high IOPS and la'
    'rger OS disks for the nodes when running many pods/node since it requires high performance for runni'
    'ng multiple pods and will generate huge logs with default AKS log rotation thresholds", "category": '
    '"Operations", "subcategory": "Storage", "waf": "Performance", "severity": "High", "link": "https://l'
    'earn.microsoft.com/azure/virtual-machines/disks-types"}, {"id": "07.07.03", "guid": "39c486ce-d5af-4'
    '062-89d5-18bb5fd795db", "text": "For hyper performance storage option use Ultra Disks on AKS", "cate'
    'gory": "Operations", "subcategory": "Storage", "waf": "Performance", "severity": "Low", "link": "htt'
    'ps://learn.microsoft.com/azure/aks/use-ultra-disks"}, {"id": "07.07.04", "guid": "9f7547c1-747d-4c56'
    '-868a-714435bd19dd", "text": "Avoid keeping state in the cluster, and store data outside (AzStorage,'
    ' AzSQL, Cosmos, etc)", "category": "Operations", "subcategory": "Storage", "waf": "Performance", "se'
    'verity": "Medium", "link": "https://learn.microsoft.com/azure/aks/operator-best-practices-multi-regi'
    'on"}, {"id": "07.07.05", "guid": "24429eb7-2281-4376-85cc-57b4a4b18142", "text": "If using AzFiles S'
    'tandard, consider AzFiles Premium and/or ANF for performance reasons", "category": "Operations", "su'
    'bcategory": "Storage", "waf": "Performance", "severity": "Medium", "link": "https://learn.microsoft.'
    'com/azure/aks/operator-best-practices-storage"}, {"id": "07.07.06", "guid": "83958a8c-2689-4b32-ab57'
    '-cfc64546135a", "text": "If using Azure Disks and AZs, consider having nodepools within a zone for L'
    'RS disk with VolumeBindingMode:WaitForFirstConsumer for provisioning storage in right zone or use ZR'
    'S disk for nodepools spanning multiple zones", "category": "Operations", "subcategory": "Storage", "'
    'waf": "Performance", "severity": "Medium", "link": "https://learn.microsoft.com/azure/aks/availabili'
    'ty-zones#azure-disk-availability-zone-support"}], "license_text": "MIT License\\n\\nCopyright (c) Micr'
    'osoft Corporation.\\n\\nPermission is hereby granted, free of charge, to any person obtaining a copy\\n'
    'of this software and associated documentation files (the \\"Software\\"), to deal\\nin the Software wit'
    'hout restriction, including without limitation the rights\\nto use, copy, modify, merge, publish, dis'
    'tribute, sublicense, and/or sell\\ncopies of the Software, and to permit persons to whom the Software'
    ' is\\nfurnished to do so, subject to the following conditions:\\n\\nThe above copyright notice and this'
    ' permission notice shall be included in all\\ncopies or substantial portions of the Software.\\n\\nTHE '
    'SOFTWARE IS PROVIDED \\"AS IS\\", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR\\nIMPLIED, INCLUDING BUT NOT'
    ' LIMITED TO THE WARRANTIES OF MERCHANTABILITY,\\nFITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT'
    '. IN NO EVENT SHALL THE\\nAUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER\\nLIA'
    'BILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,\\nOUT OF OR IN CONNECTION '
    'WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE\\nSOFTWARE.\\n"}'
))
HTML_TEMPLATE = (
    '<!doctype html>\n<!--\nTHESIS: A consulting dossier that leads with its verdict, then connects a dated'
    ' AKS assessment to its evidence and a human action plan.\nOWN-WORLD: Azure SRE Agent report family: M'
    'icrosoft-blue chrome with the four-color ribbon, a deep-blue verdict band, white cards on a neutral '
    'page, Segoe UI and ruled tables; color never substitutes for evidence.\nSTORY: Read the verdict and i'
    'ts qualifiers, check scope and provenance, read the local index beside coverage, follow category/nam'
    'espace/workload evidence, then decide on qualified actions.\nFIRST VIEWPORT: Slim blue bar with secti'
    'on links; deep-blue band with title, key numbers, provenance chips, client plaque, verdict and sever'
    'ity distribution; KPI cards overlap its lower edge.\nFORM: Read-mode dossier with operating filters. '
    'WARA narrative and Polaris wayfinding are references, not scoring engines. No tournament or random s'
    'eed.\n-->\n<html lang="en">\n<head>\n<meta charset="utf-8">\n<meta name="viewport" content="width=device-'
    'width,initial-scale=1">\n<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; scri'
    "pt-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; connect-src 'none'; base-uri 'none"
    '\'; form-action \'none\'; object-src \'none\'">\n<meta name="color-scheme" content="light dark">\n<title>AK'
    'S review | Configuration report</title>\n<style>\n:root {\n  color-scheme: light;\n  --canvas: #f3f4f6; '
    '--surface: #ffffff; --subtle: #f7f8fa; --wash: #eceef1;\n  --ink: #1f1f1f; --muted: #5c5c5c; --line: '
    '#e0e3e7; --field-line: #8a8a8a; --heading: #0c3b5e;\n  --accent: #0f6cbd; --accent-hover: #115ea3; --'
    'accent-wash: #ebf3fc; --on-accent: #ffffff;\n  --critical: #b42318; --critical-wash: #fee4e2; --criti'
    'cal-bar: #d92d20;\n  --high: #b93815; --high-wash: #ffead5; --high-bar: #ef6820;\n  --medium: #93370d;'
    ' --medium-wash: #fef0c7; --medium-bar: #f79009;\n  --low: #175cd3; --low-wash: #d1e9ff; --low-bar: #2'
    'e90fa;\n  --chrome: #0f6cbd; --chrome-hover: #0b5797; --on-chrome: #ffffff; --chrome-line: #9cc8ef;\n '
    ' --cover: #0c3b5e; --cover-ink: #ffffff; --cover-muted: #c7def2; --cover-line: #3f6b90;\n  --nav: #11'
    '4b77; --nav-ink: #ffffff; --nav-muted: #d0e4f6;\n  --brand-red: #f25022; --brand-green: #7fba00; --br'
    'and-blue: #00a4ef; --brand-yellow: #ffb900;\n  --shadow: 0 1px 2px rgba(16, 24, 40, .05), 0 1px 3px r'
    'gba(16, 24, 40, .07);\n  --shadow-raised: 0 10px 24px -10px rgba(16, 24, 40, .24), 0 2px 6px rgba(16,'
    ' 24, 40, .06);\n  --cue: rgba(16, 24, 40, .24);\n  --radius: 8px; --radius-card: 12px; --space: 16px;\n'
    '}\n:root[data-theme="dark"] {\n  color-scheme: dark;\n  --canvas: #141414; --surface: #1f1f1f; --subtle'
    ': #262626; --wash: #2e2e2e;\n  --ink: #f2f2f2; --muted: #c2c2c2; --line: #3b3b3b; --field-line: #9494'
    '94; --heading: #d6e9fa;\n  --accent: #6cb2eb; --accent-hover: #9ccaf1; --accent-wash: #1d3347; --on-a'
    'ccent: #141414;\n  --critical: #ffb3ae; --critical-wash: #4a1f1c; --critical-bar: #f04438;\n  --high: '
    '#ffbe94; --high-wash: #46281a; --high-bar: #f97a3a;\n  --medium: #fedf89; --medium-wash: #3f3115; --m'
    'edium-bar: #fdb022;\n  --low: #a9d3ff; --low-wash: #17304f; --low-bar: #53a6fb;\n  --chrome: #0e4775; '
    '--chrome-hover: #115486; --on-chrome: #f5f5f5; --chrome-line: #6d9cc6;\n  --cover: #0a2438; --cover-i'
    'nk: #f5f5f5; --cover-muted: #b9d5ee; --cover-line: #2e5578;\n  --nav: #0f3554; --nav-ink: #f5f5f5; --'
    'nav-muted: #c0daf1;\n  --shadow: 0 1px 2px rgba(0, 0, 0, .45);\n  --shadow-raised: 0 10px 24px -10px r'
    'gba(0, 0, 0, .7), 0 2px 6px rgba(0, 0, 0, .45);\n  --cue: rgba(0, 0, 0, .6);\n}\n* { box-sizing: border'
    '-box; }\nhtml { scroll-behavior: auto; scroll-padding-top: 84px; scrollbar-color: var(--field-line) v'
    'ar(--canvas); -webkit-text-size-adjust: 100%; }\nbody { margin: 0; background: var(--canvas); color: '
    'var(--ink); font: 15px/1.55 "Segoe UI", system-ui, sans-serif; overflow-wrap: anywhere; font-variant'
    '-numeric: tabular-nums; }\n::selection { background: var(--accent); color: var(--on-accent); }\n[hidde'
    'n] { display: none !important; }\nbutton, input, select { font: inherit; }\nbutton, input, select, sum'
    'mary, a { touch-action: manipulation; }\nbutton, select, input { min-height: 44px; border: 1px solid '
    'var(--field-line); border-radius: var(--radius); background: var(--surface); color: var(--ink); padd'
    'ing: 8px 12px; accent-color: var(--accent); }\nbutton { cursor: pointer; font-weight: 600; }\nbutton:h'
    'over:not(:disabled), select:hover:not(:disabled), input:hover { background: var(--wash); }\nbutton:ac'
    'tive:not(:disabled) { background: var(--line); }\nbutton:disabled, select:disabled { opacity: .55; cu'
    'rsor: not-allowed; }\nbutton.primary { background: var(--accent); color: var(--on-accent); border-col'
    'or: var(--accent); }\nbutton.primary:hover:not(:disabled) { background: var(--accent-hover); border-c'
    'olor: var(--accent-hover); }\ninput::placeholder { color: var(--muted); opacity: 1; }\na { color: var('
    '--accent); text-underline-offset: 3px; }\na:hover { text-decoration-thickness: 2px; }\n:focus-visible '
    '{ outline: 3px solid var(--accent); outline-offset: 2px; }\n.document:focus { outline: none; }\ncode, '
    '.mono { font-family: Consolas, ui-monospace, monospace; font-size: .92em; }\n.skip { position: absolu'
    'te; left: 16px; top: -100px; z-index: 30; padding: 12px 16px; background: var(--surface); border: 2p'
    'x solid var(--accent); border-radius: var(--radius); }\n.skip:focus { top: 12px; }\n.toolbar { positio'
    'n: sticky; top: 0; z-index: 20; background: var(--chrome); color: var(--on-chrome); }\n.toolbar-inner'
    ' { max-width: 1400px; margin: 0 auto; display: flex; align-items: center; gap: 8px 20px; padding: 8p'
    'x 40px; min-height: 60px; }\n.toolbar-brand { display: flex; align-items: baseline; gap: 10px; white-'
    'space: nowrap; }\n.toolbar-title { font-size: 17px; font-weight: 600; letter-spacing: -.01em; }\n.tool'
    'bar-subtitle { display: none; font-size: 14px; }\n.toolbar-nav { display: flex; gap: 2px; min-width: '
    '0; }\n.toolbar-nav a { color: var(--on-chrome); text-decoration: none; font-size: 14px; font-weight: '
    '600; padding: 8px 10px; border-radius: var(--radius); white-space: nowrap; }\n.toolbar-nav a:hover { '
    'background: var(--chrome-hover); }\n.toolbar-controls { margin-left: auto; display: flex; flex-wrap: '
    'wrap; gap: 8px; align-items: center; justify-content: flex-end; }\n.readonly-chip { font-size: 12.5px'
    '; font-weight: 600; border: 1px solid var(--chrome-line); border-radius: 999px; padding: 4px 11px; w'
    'hite-space: nowrap; }\n.theme-field, .jump-field { display: flex; gap: 8px; align-items: center; font'
    '-size: 14px; }\n.jump-field { display: none; }\n.toolbar button, .toolbar select { font-size: 14px; mi'
    'n-height: 40px; padding: 6px 12px; }\n.toolbar select { color-scheme: only light; background: #ffffff'
    '; color: #0b3a5e; border-color: var(--chrome-line); }\n.toolbar button { background: transparent; col'
    'or: var(--on-chrome); border-color: var(--chrome-line); }\n.toolbar button:hover:not(:disabled) { bac'
    'kground: var(--chrome-hover); }\n.toolbar button.primary { background: #ffffff; color: #0b3a5e; borde'
    'r-color: #ffffff; }\n.toolbar button.primary:hover:not(:disabled) { background: #e6f0fa; border-color'
    ': #e6f0fa; }\n.toolbar :focus-visible { outline-color: var(--on-chrome); }\n.brand-ribbon { display: f'
    'lex; height: 4px; }\n.brand-ribbon span { flex: 1; }\n.brand-ribbon .red { background: var(--brand-red'
    '); }\n.brand-ribbon .green { background: var(--brand-green); }\n.brand-ribbon .blue { background: var('
    '--brand-blue); }\n.brand-ribbon .yellow { background: var(--brand-yellow); }\n.theme-note { max-width:'
    ' 1400px; margin: 0 auto; padding: 0 40px 10px; font-size: 14px; }\n.toolbar .theme-note { color: var('
    '--on-chrome); }\n.opening-state { max-width: 900px; margin: 48px auto; padding: 32px; border: 1px sol'
    'id var(--line); border-radius: var(--radius-card); background: var(--surface); box-shadow: var(--sha'
    'dow); }\n.opening-state h1 { font-size: 28px; color: var(--heading); }\n.document { display: block; mi'
    'n-width: 0; padding-bottom: 56px; }\n.page { max-width: 1320px; margin: 0 auto; padding: 0 40px; }\nh1'
    ' { margin: 0 0 16px; font-size: 40px; line-height: 1.15; font-weight: 600; letter-spacing: -.02em; m'
    'ax-width: 22ch; text-wrap: balance; }\nh2 { margin: 0 0 12px; font-size: 24px; line-height: 1.25; fon'
    't-weight: 600; letter-spacing: -.01em; color: var(--heading); text-wrap: balance; }\nh3 { margin: 0 0'
    ' 12px; font-size: 18px; line-height: 1.35; font-weight: 600; color: var(--heading); }\nh4 { margin: 0'
    ' 0 8px; font-size: 15px; line-height: 1.4; font-weight: 600; }\np { margin: 0 0 12px; }\n.prose { max-'
    'width: 72ch; }\n.muted, .qualification { color: var(--muted); }\n.qualification { font-size: 14px; max'
    '-width: 75ch; }\n.card { background: var(--surface); border: 1px solid var(--line); border-radius: va'
    'r(--radius-card); box-shadow: var(--shadow); padding: 20px 24px; min-width: 0; }\n.card-sub { margin:'
    ' -6px 0 16px; color: var(--muted); font-size: 14px; max-width: 75ch; }\n.hero { background: var(--cov'
    'er); color: var(--cover-ink); padding: 44px 40px 104px; }\n.hero-inner { max-width: 1240px; margin: 0'
    ' auto; display: grid; grid-template-columns: minmax(0, 1fr) 340px; gap: 28px 56px; align-items: star'
    't; }\n.hero h1 { color: var(--cover-ink); }\n.hero .introduction { font-size: 18px; line-height: 1.5; '
    'max-width: 60ch; margin: 0 0 10px; color: var(--cover-ink); }\n.hero-summary { margin: 0; max-width: '
    '72ch; color: var(--cover-muted); }\n.hero-summary b { color: var(--cover-ink); font-weight: 600; }\n.p'
    'rovenance { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 22px; }\n.chip { display: inline-fl'
    'ex; align-items: center; font-size: 12.5px; line-height: 1.4; padding: 5px 11px; border: 1px solid v'
    'ar(--cover-line); border-radius: 999px; color: var(--cover-muted); white-space: nowrap; }\n.chip.stro'
    'ng { color: var(--cover-ink); font-weight: 600; border-color: var(--cover-muted); }\na.chip { text-de'
    'coration: none; }\na.chip:hover { color: var(--cover-ink); border-color: var(--cover-ink); }\n.hero-si'
    'de { display: grid; gap: 16px; min-width: 0; }\n.brand { display: flex; align-items: center; gap: 16p'
    'x; min-width: 0; }\n.brand-plaque { color-scheme: only light; background: #ffffff; color: #424242; bo'
    'rder: 1px solid #d1d1d1; border-radius: var(--radius); width: 220px; max-width: 100%; min-height: 76'
    'px; padding: 16px; display: flex; align-items: center; justify-content: center; flex: none; }\n.brand'
    '-plaque img { max-width: 100%; width: auto; height: auto; max-height: 56px; object-fit: contain; dis'
    'play: block; }\n.brand-placeholder { color: #424242; font-size: 20px; font-weight: 600; letter-spacin'
    'g: .04em; overflow-wrap: anywhere; }\n.client-line { margin: 0; min-width: 0; font-size: 13px; color:'
    ' var(--cover-muted); }\n.client-name { display: block; font-size: 16px; font-weight: 600; color: var('
    '--cover-ink); overflow-wrap: anywhere; }\n.verdict { background: var(--nav); color: var(--nav-ink); b'
    'order: 1px solid var(--cover-line); border-radius: var(--radius-card); padding: 18px 20px; }\n.verdic'
    't-label { margin: 0 0 4px; font-size: 13px; font-weight: 600; color: var(--nav-muted); }\n.verdict-va'
    'lue { margin: 0; font-size: 26px; line-height: 1.2; font-weight: 600; letter-spacing: -.01em; color:'
    ' var(--nav-ink); }\n.verdict.tone-critical .verdict-value { color: #ffb4ab; }\n.verdict.tone-high .ver'
    'dict-value { color: #fec84b; }\n.verdict.tone-medium .verdict-value { color: #fedf89; }\n.verdict-deta'
    'il { margin: 8px 0 0; font-size: 14px; }\n.verdict-note { margin: 6px 0 0; font-size: 13px; color: va'
    'r(--nav-muted); }\n.hero-distribution { grid-column: 1 / -1; min-width: 0; }\n.distribution-head { dis'
    'play: flex; justify-content: space-between; gap: 4px 16px; flex-wrap: wrap; margin: 0 0 8px; font-si'
    'ze: 13.5px; color: var(--cover-muted); }\n.distribution-head b { color: var(--cover-ink); font-weight'
    ': 600; }\n.distribution-track { display: flex; height: 12px; border-radius: 999px; overflow: hidden; '
    'background: var(--cover-line); }\n.distribution-segment { height: 100%; }\n.distribution-segment.criti'
    'cal { background: var(--critical-bar); }\n.distribution-segment.high { background: var(--high-bar); }'
    '\n.distribution-segment.medium { background: var(--medium-bar); }\n.distribution-segment.low { backgro'
    'und: var(--low-bar); }\n.distribution-legend { display: flex; flex-wrap: wrap; gap: 6px 20px; margin-'
    'top: 10px; font-size: 13.5px; color: var(--cover-muted); }\n.legend-item { display: inline-flex; alig'
    'n-items: center; gap: 7px; }\n.legend-item b { color: var(--cover-ink); font-weight: 600; }\n.legend-s'
    'watch { display: inline-block; width: 10px; height: 10px; border-radius: 3px; }\n.legend-swatch.criti'
    'cal { background: var(--critical-bar); }\n.legend-swatch.high { background: var(--high-bar); }\n.legen'
    'd-swatch.medium { background: var(--medium-bar); }\n.legend-swatch.low { background: var(--low-bar); '
    '}\n.kpis { position: relative; z-index: 1; display: grid; grid-template-columns: repeat(auto-fit, min'
    'max(200px, 1fr)); gap: 16px; margin-top: -64px; }\n.kpi { background: var(--surface); border: 1px sol'
    'id var(--line); border-radius: var(--radius-card); box-shadow: var(--shadow-raised); padding: 18px 2'
    '0px; min-width: 0; }\n.kpi-value { margin: 0; font-size: 34px; line-height: 1.1; font-weight: 600; le'
    'tter-spacing: -.02em; color: var(--ink); white-space: nowrap; }\n.kpi-value.unknown { font-size: 22px'
    '; line-height: 1.6; color: var(--muted); white-space: normal; }\n.kpi-unit { margin-left: 4px; font-s'
    'ize: 15px; font-weight: 600; letter-spacing: 0; color: var(--muted); }\n.kpi-label { margin: 8px 0 0;'
    ' font-size: 14px; font-weight: 600; }\n.kpi-note { margin: 2px 0 0; font-size: 13px; color: var(--mut'
    'ed); }\n.sim-note { margin: 16px 0 0; padding: 10px 16px; border: 1px solid var(--medium-bar); border'
    '-radius: var(--radius); background: var(--medium-wash); color: var(--medium); font-size: 14px; }\n.si'
    'm-note strong { font-weight: 600; }\n.scope-card { margin-top: 16px; }\n.scope-card h2 { font-size: 20'
    'px; margin-bottom: 4px; }\n.cover-facts { display: grid; grid-template-columns: repeat(auto-fill, min'
    'max(180px, 1fr)); gap: 16px 24px; margin: 16px 0; }\n.cover-facts div { min-width: 0; }\n.cover-facts '
    '.wide-fact { grid-column: span 2; }\n.cover-facts dd { overflow-wrap: break-word; }\ndt { font-size: 1'
    '3px; color: var(--muted); margin-bottom: 2px; }\ndd { margin: 0; overflow-wrap: anywhere; }\n.cover-fa'
    'cts dd { font-size: 15px; font-weight: 600; }\n.cover-id { color: var(--muted); font-size: 13px; padd'
    'ing-top: 12px; border-top: 1px solid var(--line); }\n.cover-id p { margin: 0 0 6px; }\n.cover-id .port'
    'al-link { margin-left: 8px; }\n.snapshot-note { padding: 12px 16px; background: var(--subtle); border'
    ': 1px solid var(--line); border-radius: var(--radius); margin: 16px 0 0; font-size: 14px; }\n.snapsho'
    't-note p { margin: 0; }\n.snapshot-note p + p { margin-top: 4px; color: var(--muted); }\n.chapter, .fi'
    'lter-section, .cluster-overview, .cluster-error { margin-top: 48px; min-width: 0; }\n.chapter-head { '
    'display: flex; gap: 12px 24px; align-items: flex-end; justify-content: space-between; flex-wrap: wra'
    'p; margin-bottom: 16px; }\n.chapter-head h2 { margin-bottom: 4px; }\n.chapter-head p { margin: 0; }\n.c'
    'hapter-tools { display: flex; flex-wrap: wrap; gap: 8px 12px; align-items: flex-end; }\n.chapter-tool'
    's button, .chapter-tools select { font-size: 14px; }\n.inline-field { display: flex; gap: 8px; align-'
    'items: center; font-size: 14px; font-weight: 600; }\n.card-grid { display: grid; grid-template-column'
    's: repeat(12, minmax(0, 1fr)); gap: 16px; }\n.card-grid > * { grid-column: span 6; }\n.card-grid > .sp'
    'an-7 { grid-column: span 7; }\n.card-grid > .span-5 { grid-column: span 5; }\n.card-grid > .span-12 { '
    'grid-column: 1 / -1; }\n.score-layout { display: grid; grid-template-columns: 210px minmax(0, 1fr); g'
    'ap: 28px; }\n.global-index { padding-right: 24px; border-right: 1px solid var(--line); }\n.global-inde'
    'x h3 { font-size: 16px; margin-bottom: 4px; }\n.score-value { display: block; font-size: 36px; line-h'
    'eight: 1.15; font-weight: 600; letter-spacing: -.02em; white-space: nowrap; margin: 4px 0 12px; }\n.s'
    'core-value.unknown { font-size: 24px; white-space: normal; }\n.global-index p { font-size: 13px; marg'
    'in-bottom: 8px; }\n.score-row { padding: 0 0 14px; margin: 0 0 14px; border-bottom: 1px solid var(--l'
    'ine); }\n.score-row:last-child { border-bottom: 0; margin-bottom: 0; padding-bottom: 0; }\n.score-row-'
    'head { display: flex; justify-content: space-between; gap: 12px; font-size: 14px; font-weight: 600; '
    'margin-bottom: 6px; }\n.score-number { white-space: nowrap; }\n.score-track { height: 8px; background:'
    ' var(--wash); border-radius: 999px; overflow: hidden; }\n.score-fill { background: var(--accent); hei'
    'ght: 100%; border-radius: 999px; }\n.score-caption { margin: 6px 0 0; font-size: 13px; color: var(--m'
    'uted); }\n.pillar-scores { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); column-ga'
    'p: 32px; }\n.pillar-scores .score-row, .pillar-scores .score-row:last-child { margin-bottom: 14px; pa'
    'dding-bottom: 12px; border-bottom: 1px solid var(--line); }\n.critical-card { display: grid; grid-tem'
    'plate-columns: 220px minmax(0, 1fr); gap: 8px 24px; align-items: start; }\n.critical-card h3 { margin'
    ': 0; }\n.critical-card .priority-list { display: grid; grid-template-columns: repeat(auto-fit, minmax'
    '(min(100%, 300px), 1fr)); gap: 0 24px; }\n.critical-card .priority-list li, .critical-card .priority-'
    'list li:first-child { padding: 12px 0; border-top: 1px solid var(--line); }\n.critical-card .empty { '
    'padding: 10px 16px; }\n.coverage-note { padding-top: 14px; margin-top: 16px; border-top: 1px solid va'
    'r(--line); }\n.coverage-note p { margin: 0 0 6px; font-size: 14px; }\n.coverage-number { font-size: 20'
    'px; font-weight: 600; color: var(--heading); }\n.assessment-chart { margin: 0; }\n.chart-head { displa'
    'y: flex; justify-content: space-between; align-items: baseline; gap: 4px 16px; flex-wrap: wrap; }\n.c'
    'hart-head h3 { margin-bottom: 4px; }\n.chart-total-line { margin: 0; color: var(--muted); font-size: '
    '14px; }\n.chart-total { font-size: 28px; font-weight: 600; letter-spacing: -.02em; color: var(--ink);'
    ' margin-right: 4px; }\n.status-bar { display: block; width: 100%; height: 14px; margin: 12px 0 16px; '
    'border-radius: 999px; overflow: hidden; background: var(--wash); }\n.assessment-chart table { font-si'
    'ze: 14px; }\n.assessment-chart th, .assessment-chart td { padding: 8px 10px; }\n.assessment-chart tbod'
    'y th { font-weight: 600; background: transparent; }\n.assessment-chart figcaption { margin: 12px 0 0;'
    ' font-size: 13px; color: var(--muted); }\n.status-swatch { display: inline-block; width: 11px; height'
    ': 11px; margin-right: 8px; border-radius: 3px; vertical-align: -.05em; }\n.status-swatch.passed { bac'
    'kground: var(--accent); }\n.status-swatch.failed { background: var(--high-bar); }\n.status-swatch.not_'
    'evaluated { background: var(--field-line); }\n.status-swatch.not_applicable { background: var(--surfa'
    'ce); box-shadow: inset 0 0 0 1px var(--field-line); }\n.severity { display: inline-flex; align-items:'
    ' center; gap: 6px; padding: 1px 10px 1px 8px; border-radius: 999px; font-size: 12.5px; font-weight: '
    '600; line-height: 1.6; white-space: nowrap; }\n.severity::before { content: ""; width: 7px; height: 7'
    'px; border-radius: 50%; background: currentColor; flex: none; }\n.severity.critical { color: var(--cr'
    'itical); background: var(--critical-wash); }\n.severity.high { color: var(--high); background: var(--'
    'high-wash); }\n.severity.medium { color: var(--medium); background: var(--medium-wash); }\n.severity.l'
    'ow { color: var(--low); background: var(--low-wash); }\n.priority-list, .next-actions { margin: 0; pa'
    'dding: 0; list-style: none; }\n.priority-list li, .next-actions li { padding: 12px 0; border-top: 1px'
    ' solid var(--line); }\n.priority-list li:first-child, .next-actions li:first-child { border-top: 0; p'
    'adding-top: 0; }\n.priority-list strong { display: block; font-weight: 600; margin-bottom: 4px; }\n.pr'
    'iority-list p { margin: 4px 0 0; font-size: 14px; }\n.next-actions li { display: grid; grid-template-'
    'columns: 5.5rem minmax(0, 1fr); gap: 4px 12px; align-items: start; }\n.next-actions .severity { margi'
    'n-top: 1px; justify-self: start; }\n.next-actions strong { font-weight: 600; }\n.next-actions .cell-no'
    'te { grid-column: 2; margin-top: 0; }\n.card-link { display: inline-block; margin-top: 12px; font-siz'
    'e: 14px; font-weight: 600; }\n.executive-messages { padding: 0; margin: 0; list-style: none; }\n.execu'
    'tive-messages li { padding: 10px 0; border-top: 1px solid var(--line); font-size: 14px; max-width: 7'
    '5ch; }\n.executive-messages li:first-child { border-top: 0; padding-top: 0; }\n.cluster-overview h2, .'
    'cluster-error h2 { font-size: 20px; }\n.cluster-picker { max-width: 540px; margin: 16px 0; }\n.fleet-f'
    'ilters { display: grid; grid-template-columns: minmax(0, 1.2fr) minmax(0, 1.4fr) minmax(0, 1fr); gap'
    ': 16px; margin: 20px 0 8px; }\n.fleet-kpis { display: grid; grid-template-columns: repeat(auto-fit, m'
    'inmax(170px, 1fr)); gap: 12px; margin: 20px 0; }\n.fleet-kpi { padding: 14px 16px; border: 1px solid '
    'var(--line); background: var(--surface); border-radius: var(--radius); min-width: 0; }\n.fleet-kpi b '
    '{ display: block; font-size: 24px; font-weight: 600; font-variant-numeric: tabular-nums; overflow-wr'
    'ap: anywhere; }\n.fleet-kpi span { display: block; font-size: 13px; font-weight: 600; margin-top: 4px'
    '; }\n.fleet-kpi small { display: block; font-size: 12px; color: var(--muted); margin-top: 4px; }\n.fle'
    'et-kpi.critical b { color: var(--critical); }\n.fleet-section-head { display: flex; flex-wrap: wrap; '
    'gap: 12px 24px; align-items: end; justify-content: space-between; margin-top: 28px; }\n.fleet-section'
    '-head .field { min-width: 180px; }\ntable[data-collection="fleet-runs"] { min-width: 1180px; }\ntable['
    'data-collection="fleet-findings"] { min-width: 1000px; }\n.link-button { border: 0; padding: 0; min-h'
    'eight: 0; background: transparent; color: var(--accent); text-decoration: underline; cursor: pointer'
    '; font: inherit; text-align: left; }\n@media (max-width: 760px) { .fleet-filters { grid-template-colu'
    'mns: 1fr; } }\n.cluster-error { padding: 20px 24px; border: 1px solid var(--critical); border-radius:'
    ' var(--radius-card); background: var(--critical-wash); }\n.cluster-error h2 { color: var(--critical);'
    ' }\n.filter-section { background: var(--surface); border: 1px solid var(--line); border-radius: var(-'
    '-radius-card); box-shadow: var(--shadow); padding: 20px 24px; }\n.filter-section h2 { font-size: 20px'
    '; margin-bottom: 4px; }\n.filters { display: grid; grid-template-columns: minmax(0, 1.4fr) repeat(3, '
    'minmax(0, 1fr)); gap: 16px; margin-top: 16px; }\n.field { display: grid; gap: 6px; min-width: 0; }\n.f'
    'ield label { font-size: 14px; font-weight: 600; }\n.field input, .field select { width: 100%; min-wid'
    'th: 0; font-size: 14px; }\n.extra-filters { margin: 12px 0; }\n.extra-filters .filter-extra-grid { dis'
    'play: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px; margin-top: 8px; }\n.filter-'
    'actions { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; margin-top: 12px; }\n.filte'
    'r-actions button { font-size: 14px; }\n.scope-path { margin: 16px 0 8px; display: flex; flex-wrap: wr'
    'ap; gap: 4px 8px; align-items: center; font-size: 14px; }\n.scope-path button { border: 0; padding: 6'
    'px 8px; color: var(--accent); background: transparent; min-height: 40px; font-size: 14px; }\n.scope-p'
    'ath button:hover { background: var(--accent-wash); }\n.scope-path .scope-part { overflow-wrap: anywhe'
    're; min-width: 0; max-width: 100%; }\n.filter-count { margin: 0; font-size: 14px; font-weight: 600; }'
    '\n.inventory-counts { display: flex; flex-wrap: wrap; gap: 8px; margin: 0 0 8px; font-size: 14px; }\n.'
    'inventory-counts span { padding: 6px 14px; border: 1px solid var(--line); border-radius: 999px; back'
    'ground: var(--surface); overflow-wrap: anywhere; }\n.inventory-counts b { font-weight: 600; }\n.invent'
    'ory-section { margin-top: 28px; min-width: 0; }\n.inventory-section h3 { margin-bottom: 10px; }\n.tabl'
    'e-scroll { overflow: auto; max-width: 100%; background: var(--surface); border: 1px solid var(--line'
    '); border-radius: var(--radius-card); box-shadow: var(--shadow); scrollbar-color: var(--field-line) '
    'transparent; }\n.table-scroll[data-overflow="left"] { box-shadow: inset 14px 0 12px -12px var(--cue),'
    ' var(--shadow); }\n.table-scroll[data-overflow="right"] { box-shadow: inset -14px 0 12px -12px var(--'
    'cue), var(--shadow); }\n.table-scroll[data-overflow="both"] { box-shadow: inset 14px 0 12px -12px var'
    '(--cue), inset -14px 0 12px -12px var(--cue), var(--shadow); }\ntable { width: 100%; border-collapse:'
    ' collapse; font-size: 14px; }\n.wide-table { min-width: 680px; }\nth, td { padding: 12px 14px; border-'
    'bottom: 1px solid var(--line); vertical-align: top; text-align: left; overflow-wrap: break-word; }\nt'
    'h { font-weight: 600; background: var(--subtle); color: var(--ink); }\nthead th { font-size: 12px; le'
    'tter-spacing: .04em; text-transform: uppercase; color: var(--muted); }\ntbody tr:last-child td, tbody'
    ' tr:last-child th { border-bottom: 0; }\ntbody tr:hover > td { background: var(--subtle); }\ntd { max-'
    'width: 340px; }\ntd strong { font-weight: 600; }\ncaption { text-align: left; padding: 12px 14px; font'
    '-size: 13px; color: var(--muted); border-bottom: 1px solid var(--line); }\n.cell-note { display: bloc'
    'k; color: var(--muted); font-size: 13px; margin-top: 4px; }\n.arm-id { font-family: Consolas, ui-mono'
    'space, monospace; font-size: 12.5px; overflow-wrap: break-word; }\n.resource-ref { display: block; mi'
    'n-width: 0; }\n.resource-ref .cell-note { margin-top: 2px; }\n.portal-link { font-size: 13px; font-wei'
    'ght: 600; white-space: nowrap; }\n.container-list { margin: 0; padding: 0; list-style: none; display:'
    ' grid; gap: 8px; }\n.container-list .mono { display: block; font-size: 12.5px; color: var(--muted); o'
    'verflow-wrap: anywhere; }\n.text-button { border: 0; padding: 4px 0; border-radius: 0; color: var(--a'
    'ccent); background: transparent; min-height: 32px; text-align: left; font-size: inherit; overflow-wr'
    'ap: anywhere; }\n.text-button:hover:not(:disabled) { background: transparent; text-decoration: underl'
    'ine; }\n.table-footer { display: flex; gap: 16px; align-items: center; justify-content: space-between'
    '; padding: 10px 2px; font-size: 13px; color: var(--muted); flex-wrap: wrap; }\n.table-footer button {'
    ' font-size: 13px; min-height: 40px; }\n.empty { padding: 16px 20px; border: 1px dashed var(--field-li'
    'ne); border-radius: var(--radius); background: var(--subtle); font-size: 14px; margin: 0; }\ndetails '
    '{ min-width: 0; }\nsummary { cursor: pointer; font-weight: 600; min-height: 44px; padding: 10px 0; ov'
    'erflow-wrap: anywhere; }\nsummary:hover { color: var(--accent); }\nsummary::marker { color: var(--mute'
    'd); }\n.receipt { margin-top: 6px; }\n.receipt summary { font-size: 13px; min-height: 32px; padding: 6'
    'px 0; }\n.receipt-content { margin-top: 8px; }\n.facts { display: grid; grid-template-columns: minmax('
    '110px, .35fr) minmax(0, 1fr); gap: 8px 20px; margin: 16px 0; font-size: 14px; }\n.facts dt { font-siz'
    'e: 13px; margin: 0; }\n.facts dd { min-width: 0; }\n.json, .command { margin: 12px 0 0; padding: 12px;'
    ' font: 12.5px/1.5 Consolas, ui-monospace, monospace; background: var(--subtle); border: 1px solid va'
    'r(--line); border-radius: var(--radius); white-space: pre-wrap; overflow-wrap: anywhere; max-height:'
    ' 28rem; overflow: auto; }\n.technical-inventory { margin-top: 24px; border-top: 1px solid var(--line)'
    '; }\n.technical-inventory > summary { font-size: 15px; }\n.findings-group { margin-top: 16px; backgrou'
    'nd: var(--surface); border: 1px solid var(--line); border-radius: var(--radius-card); box-shadow: va'
    'r(--shadow); overflow: hidden; }\n.findings-group > h3 { margin: 0; padding: 10px 20px; font-size: 12'
    'px; letter-spacing: .05em; text-transform: uppercase; color: var(--muted); background: var(--subtle)'
    '; border-bottom: 1px solid var(--line); }\n.finding { border-top: 1px solid var(--line); }\n.findings-'
    'group > h3 + .finding { border-top: 0; }\n.finding > summary { position: relative; display: grid; gri'
    'd-template-columns: 5.5rem minmax(0, 1fr); gap: 12px; align-items: start; list-style: none; padding:'
    ' 14px 20px 14px 44px; font-weight: 400; }\n.finding > summary::-webkit-details-marker { display: none'
    '; }\n.finding > summary::before { content: ""; position: absolute; left: 21px; top: 21px; width: 7px;'
    ' height: 7px; border-right: 2px solid var(--muted); border-bottom: 2px solid var(--muted); transform'
    ': rotate(-45deg); transition: transform .15s ease; }\n.finding[open] > summary::before { transform: r'
    'otate(45deg); top: 19px; }\n.finding > summary:hover { color: inherit; background: var(--subtle); }\n.'
    'finding > summary .severity { margin-top: 1px; justify-self: start; }\n.finding-main { display: grid;'
    ' gap: 2px; min-width: 0; }\n.finding-title { font-weight: 600; font-size: 15px; }\n.finding-reference '
    '{ display: block; font-size: 13px; color: var(--muted); overflow-wrap: anywhere; }\n.finding-body { p'
    'adding: 0 20px 20px 44px; }\n.finding-body h4 { margin-top: 20px; }\n.evidence-list { margin: 0; paddi'
    'ng-left: 20px; }\n.evidence-list li { padding: 10px 0; }\n.evidence-list .facts { margin-top: 0; }\n.ev'
    'idence-list pre { margin-top: 8px; }\n.checks-disclosure { margin-top: 24px; padding: 4px 24px 16px; '
    'background: var(--surface); border: 1px solid var(--line); border-radius: var(--radius-card); box-sh'
    'adow: var(--shadow); }\n.checks-disclosure > summary { font-size: 16px; }\n.finops-baseline { margin: '
    '0 0 20px; background: var(--surface); border: 1px solid var(--line); border-radius: var(--radius-car'
    'd); box-shadow: var(--shadow); overflow: hidden; }\n.finops-values { display: grid; grid-template-col'
    'umns: minmax(0, 1fr) minmax(0, 1.1fr); }\n.finops-value { padding: 24px; min-width: 0; }\n.finops-valu'
    'e.savings { background: var(--accent-wash); border-left: 1px solid var(--line); }\n.finops-value h3 {'
    ' font-size: 16px; margin-bottom: 4px; }\n.financial-amount { display: block; font-size: 38px; font-we'
    'ight: 600; line-height: 1.2; letter-spacing: -.02em; color: var(--heading); margin: 8px 0 12px; }\n.f'
    'inancial-amount.unknown { font-size: 30px; color: var(--muted); }\n.finops-value p:last-child { margi'
    'n-bottom: 0; }\n.finops-baseline > .facts { margin: 0; padding: 20px 24px; border-top: 1px solid var('
    '--line); }\n.finops-baseline > .qualification { margin: 0; padding: 14px 24px; border-top: 1px solid '
    'var(--line); max-width: none; }\n.finops-notes { padding-left: 20px; margin: 12px 0 24px; max-width: '
    '75ch; font-size: 14px; }\n.finops-notes li { padding: 4px 0; }\n.architecture-tabs { display: inline-f'
    'lex; flex-wrap: wrap; gap: 4px; margin: 0 0 16px; padding: 4px; background: var(--wash); border-radi'
    'us: 10px; }\n.architecture-tabs button { border-color: transparent; background: transparent; min-heig'
    'ht: 40px; font-size: 14px; }\n.architecture-tabs button:hover:not(:disabled) { background: var(--surf'
    'ace); }\n.architecture-tabs button[aria-selected="true"] { background: var(--surface); color: var(--h'
    'eading); border-color: var(--line); box-shadow: var(--shadow); }\n.architecture-note { padding: 16px '
    '20px; background: var(--surface); border: 1px solid var(--line); border-radius: var(--radius-card); '
    'margin: 0 0 16px; }\n.architecture-note h3 { margin-bottom: 6px; }\n.architecture-note p:last-child { '
    'margin-bottom: 0; }\n.architecture-layout { display: grid; grid-template-columns: minmax(0, 1fr) 260p'
    'x; gap: 16px; align-items: start; }\n.architecture-map { margin: 0; border: 1px solid var(--line); bo'
    'rder-radius: var(--radius-card); background: var(--surface); padding: 16px; min-width: 0; box-shadow'
    ': var(--shadow); }\n.architecture-map > svg { display: block; width: 100%; height: auto; }\n.architect'
    'ure-map figcaption { padding-top: 12px; font-size: 13px; color: var(--muted); }\n.graph-line { fill: '
    'none; stroke: var(--accent); stroke-width: 1.5; }\n.graph-box { fill: var(--surface); stroke: var(--f'
    'ield-line); }\n.graph-box.selected { fill: var(--accent-wash); stroke: var(--accent); stroke-width: 2'
    '; }\n.graph-label { fill: var(--ink); font: 600 13px "Segoe UI", system-ui, sans-serif; }\n.graph-kind'
    ' { fill: var(--muted); font: 11px "Segoe UI", system-ui, sans-serif; }\n.graph-node { cursor: pointer'
    '; }\n.graph-node:focus-visible { outline: none; }\n.graph-node:focus-visible .graph-box { stroke-width'
    ': 3; stroke: var(--accent); }\n.architecture-tree { border: 1px solid var(--line); border-radius: var'
    '(--radius-card); background: var(--surface); box-shadow: var(--shadow); padding: 16px; min-width: 0;'
    ' max-height: 34rem; overflow: auto; }\n.architecture-tree h3 { font-size: 16px; }\n.architecture-tree '
    'summary { font-size: 14px; }\n.architecture-tree ul { list-style: none; padding: 0; margin: 0 0 12px;'
    ' }\n.architecture-tree button { display: block; width: 100%; padding: 8px; min-height: 40px; text-ali'
    'gn: left; font-size: 13px; font-weight: 400; border: 0; background: transparent; overflow-wrap: anyw'
    'here; }\n.architecture-tree button[aria-pressed="true"] { background: var(--accent-wash); color: var('
    '--accent); font-weight: 600; }\n.architecture-tree button:hover { background: var(--wash); }\n.archite'
    'cture-controls { display: grid; grid-template-columns: minmax(0, .7fr) minmax(0, 1.3fr); gap: 16px; '
    'margin: 0 0 16px; }\n.architecture-properties { margin-top: 16px; padding: 16px 20px; background: var'
    '(--surface); border: 1px solid var(--line); border-radius: var(--radius-card); }\n.architecture-prope'
    'rties:empty { display: none; }\n.architecture-properties > h3 { margin-bottom: 0; }\n.architecture-pro'
    'perties .facts { border-top: 1px solid var(--line); padding-top: 12px; }\n.architecture-product { dis'
    'play: flex; align-items: center; gap: 12px; min-width: 0; }\n.architecture-product img { width: 40px;'
    ' height: 40px; flex: 0 0 40px; object-fit: contain; }\n.architecture-product strong { font-size: 15px'
    '; }\n.architecture-product .cell-note { font-size: 13px; }\n.reference-diagram { margin: 16px 0; paddi'
    'ng: 20px; background: var(--surface); border: 1px solid var(--line); border-radius: var(--radius-car'
    'd); box-shadow: var(--shadow); }\n.reference-entry { display: grid; grid-template-columns: repeat(2, '
    'minmax(0, 1fr)); gap: 24px; padding: 20px; border: 1px dashed var(--field-line); border-radius: var('
    '--radius); }\n.reference-entry > div + div { border-left: 1px solid var(--line); padding-left: 24px; '
    '}\n.reference-link { margin: 0; padding: 12px; text-align: center; font-size: 14px; color: var(--acce'
    'nt); }\n.reference-network { padding: 24px; border: 1px dashed var(--accent); border-radius: var(--ra'
    'dius); background: var(--accent-wash); }\n.reference-network > h3 { margin-bottom: 16px; }\n.reference'
    '-lanes { display: grid; grid-template-columns: minmax(0, .7fr) minmax(0, 1.3fr); gap: 20px; }\n.refer'
    'ence-lane { background: var(--surface); border: 1px solid var(--line); border-radius: var(--radius);'
    ' padding: 20px; min-width: 0; }\n.reference-lane h4 { margin-bottom: 14px; }\n.reference-workloads { d'
    'isplay: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; margin-top: 16px; }\n.refe'
    'rence-workloads p { border-top: 1px solid var(--line); padding-top: 12px; font-size: 14px; margin: 0'
    '; }\n.reference-platform { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 24px'
    '; padding: 20px 0 4px; }\n.reference-diagram figcaption { font-size: 14px; margin-top: 16px; padding-'
    'top: 12px; border-top: 1px solid var(--line); }\n.reference-decisions { margin-top: 24px; }\n.action-b'
    'ucket { margin-top: 28px; }\n.action-bucket h3 { margin-bottom: 4px; }\n.action-bucket > p { font-size'
    ': 14px; }\n.source-errors { margin: 8px 0 0; padding-left: 20px; font-size: 13px; }\n.method-block { m'
    'argin-top: 20px; }\n.method-block .qualification { margin-top: 12px; }\ndetails.method-block > summary'
    ' { font-size: 16px; color: var(--heading); }\n.query { padding: 14px 0; border-top: 1px solid var(--l'
    'ine); }\n.query h4 { overflow-wrap: anywhere; }\n.source-url { overflow-wrap: anywhere; font-size: 13p'
    'x; }\n.report-footer { margin-top: 56px; padding-top: 20px; border-top: 1px solid var(--line); font-s'
    'ize: 13px; color: var(--muted); }\n.report-footer p { margin-bottom: 6px; max-width: 110ch; }\n.sr-onl'
    'y { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: r'
    'ect(0, 0, 0, 0); white-space: nowrap; border: 0; }\n.print-only { display: none; }\n@media screen and '
    '(max-width: 1359px) {\n  .toolbar-nav { display: none; }\n  .toolbar-subtitle { display: inline; }\n  .'
    'jump-field { display: flex; }\n  .jump-field select { max-width: 220px; }\n}\n@media screen and (max-wi'
    'dth: 1100px) {\n  .toolbar-inner { padding-left: 24px; padding-right: 24px; }\n  .toolbar-subtitle { d'
    'isplay: none; }\n  .jump-field .field-text { position: absolute; width: 1px; height: 1px; overflow: h'
    'idden; clip: rect(0, 0, 0, 0); white-space: nowrap; }\n  .jump-field select { max-width: 190px; }\n  .'
    'hero-inner { grid-template-columns: minmax(0, 1fr); }\n  .hero-side { grid-template-columns: auto min'
    'max(0, 1fr); align-items: start; }\n  .card-grid > *, .card-grid > .span-7, .card-grid > .span-5 { gr'
    'id-column: 1 / -1; }\n  .pillar-scores { grid-template-columns: repeat(2, minmax(0, 1fr)); }\n  .cover'
    '-facts { grid-template-columns: repeat(3, minmax(0, 1fr)); }\n  .filters { grid-template-columns: rep'
    'eat(2, minmax(0, 1fr)); }\n  .architecture-layout { grid-template-columns: minmax(0, 1fr); }\n  .archi'
    'tecture-tree { max-height: 20rem; }\n  .reference-platform { grid-template-columns: repeat(2, minmax('
    '0, 1fr)); }\n}\n@media screen and (min-width: 761px) and (max-width: 900px) {\n  .readonly-chip { displ'
    'ay: none; }\n}\n@media screen and (max-width: 760px) {\n  .toolbar { position: static; }\n  .toolbar-inn'
    'er { padding: 10px 16px 12px; flex-wrap: wrap; gap: 8px; }\n  .toolbar-brand { flex: 1; }\n  .toolbar-'
    'subtitle { display: none; }\n  .toolbar-controls { display: contents; }\n  .readonly-chip { order: 1; '
    '}\n  .jump-field { order: 2; flex: 1 1 60%; }\n  .jump-field .field-text { position: absolute; width: '
    '1px; height: 1px; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; }\n  .jump-field sel'
    'ect { flex: 1; max-width: none; min-width: 0; }\n  .theme-field { order: 3; flex: 1 1 30%; }\n  .theme'
    '-field select { flex: 1; min-width: 0; }\n  .toolbar-controls button { order: 4; flex: 1 1 40%; }\n  .'
    'theme-note { padding: 0 16px 10px; }\n  html { scroll-padding-top: 16px; }\n  .page { padding: 0 16px;'
    ' }\n  .hero { padding: 28px 16px 84px; }\n  .hero-side { grid-template-columns: minmax(0, 1fr); }\n  h1'
    ' { font-size: 28px; line-height: 1.2; max-width: 23ch; }\n  h2 { font-size: 21px; }\n  h3 { font-size:'
    ' 17px; }\n  .hero .introduction { font-size: 16px; }\n  .chip { white-space: normal; }\n  .brand-plaque'
    ' { width: 150px; min-height: 64px; padding: 12px; }\n  .brand-plaque img { max-height: 40px; }\n  .bra'
    'nd-placeholder { font-size: 16px; }\n  .verdict-value { font-size: 22px; }\n  .kpis { grid-template-co'
    'lumns: repeat(2, minmax(0, 1fr)); gap: 12px; margin-top: -56px; }\n  .kpis .kpi:first-child { grid-co'
    'lumn: 1 / -1; }\n  .kpi { padding: 14px 16px; }\n  .kpi-value { font-size: 26px; white-space: normal; '
    '}\n  .kpi-value.unknown { font-size: 18px; }\n  .card, .filter-section { padding: 16px; }\n  .cover-fac'
    'ts { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px 16px; }\n  .cover-facts dd { font-si'
    'ze: 14px; }\n  .cover-facts .reference-fact { grid-column: 1 / -1; }\n  .chapter, .filter-section, .cl'
    'uster-overview, .cluster-error { margin-top: 32px; }\n  .chapter-head { gap: 12px; }\n  .chapter-tools'
    ', .chapter-tools button, .chapter-tools .inline-field, .chapter-head > button { width: 100%; }\n  .ch'
    'apter-tools .inline-field select { flex: 1; min-width: 0; }\n  .score-layout { grid-template-columns:'
    ' 1fr; gap: 20px; }\n  .global-index { padding: 0 0 16px; border-right: 0; border-bottom: 1px solid va'
    'r(--line); }\n  .score-value { font-size: 32px; }\n  .pillar-scores, .critical-card { grid-template-co'
    'lumns: 1fr; }\n  .filters, .extra-filters .filter-extra-grid { grid-template-columns: 1fr; gap: 12px;'
    ' }\n  .filter-actions button { width: 100%; }\n  .facts { grid-template-columns: 1fr; gap: 2px; }\n  .f'
    'acts dd { margin-bottom: 10px; }\n  .finding > summary { flex-wrap: wrap; padding: 12px 16px 12px 36p'
    'x; }\n  .finding > summary::before { left: 16px; }\n  .finding-body { padding: 0 16px 16px; }\n  .findi'
    'ngs-group > h3 { padding: 10px 16px; }\n  .evidence-list { padding-left: 18px; }\n  .checks-disclosure'
    ' { padding: 4px 16px 12px; }\n  .finops-values, .reference-entry, .reference-lanes, .reference-platfo'
    'rm, .architecture-controls { grid-template-columns: 1fr; }\n  .finops-value { padding: 18px; }\n  .fin'
    'ops-value.savings { border-left: 0; border-top: 1px solid var(--line); }\n  .finops-baseline > .facts'
    ' { padding: 16px 18px; }\n  .financial-amount { font-size: 30px; }\n  .financial-amount.unknown { font'
    '-size: 26px; }\n  .architecture-tabs { display: grid; width: 100%; }\n  .architecture-note, .reference'
    '-network, .reference-lane, .reference-entry, .reference-diagram { padding: 16px; }\n  .reference-entr'
    'y > div + div { border-left: 0; border-top: 1px solid var(--line); padding-left: 0; padding-top: 20p'
    'x; }\n  .reference-workloads { grid-template-columns: 1fr; }\n  .architecture-tree { max-height: 24rem'
    '; }\n  .architecture-map { overflow: auto; }\n  .architecture-map > svg { min-width: 640px; }\n  .repor'
    't-footer { margin-top: 36px; }\n}\n@media (prefers-reduced-motion: reduce) {\n  *, *::before, *::after '
    '{ scroll-behavior: auto !important; transition: none !important; animation: none !important; }\n}\n@me'
    'dia (forced-colors: active) {\n  .score-fill, .distribution-segment, .legend-swatch, .status-swatch {'
    ' forced-color-adjust: none; background: CanvasText !important; }\n  .score-track, .distribution-track'
    ', .severity, .status-bar, .kpi, .card, .verdict { border: 1px solid CanvasText; }\n  .status-bar rect'
    ' { stroke: CanvasText; }\n  .graph-box { fill: Canvas; stroke: CanvasText; }\n  .graph-label, .graph-k'
    'ind { fill: CanvasText; }\n  .graph-line { stroke: CanvasText; }\n  :focus-visible { outline-color: Hi'
    'ghlight; }\n}\n@page {\n  size: A4; margin: 14mm 12mm 16mm;\n  @bottom-left { content: var(--print-foote'
    'r, "AKS architecture and configuration review"); font: 8pt "Segoe UI", system-ui, sans-serif; color:'
    ' #505050; }\n  @bottom-right { content: "Page " counter(page) " of " counter(pages); font: 8pt "Segoe'
    ' UI", system-ui, sans-serif; color: #505050; }\n}\n@media print {\n  :root, :root[data-theme="dark"] {\n'
    '    color-scheme: light;\n    --canvas: #ffffff; --surface: #ffffff; --subtle: #f7f8fa; --wash: #ecee'
    'f1;\n    --ink: #1f1f1f; --muted: #505050; --line: #c8cbd0; --field-line: #8a8a8a; --heading: #0c3b5e'
    '; --accent: #0f6cbd; --accent-wash: #ebf3fc;\n    --critical: #b42318; --critical-wash: #fee4e2; --cr'
    'itical-bar: #d92d20; --high: #b93815; --high-wash: #ffead5; --high-bar: #ef6820;\n    --medium: #9337'
    '0d; --medium-wash: #fef0c7; --medium-bar: #f79009; --low: #175cd3; --low-wash: #d1e9ff; --low-bar: #'
    '2e90fa;\n    --cover: #0c3b5e; --cover-ink: #ffffff; --cover-muted: #c7def2; --cover-line: #3f6b90;\n '
    '   --nav: #114b77; --nav-ink: #ffffff; --nav-muted: #d0e4f6;\n    --shadow: none; --shadow-raised: no'
    'ne;\n  }\n  * { print-color-adjust: exact; -webkit-print-color-adjust: exact; }\n  body { background: #'
    'ffffff; font-size: 10pt; }\n  .no-print, .toolbar, .skip, button, input, select, .table-footer { disp'
    'lay: none !important; }\n  .print-only { display: block; }\n  .page { max-width: none; padding: 0; }\n '
    ' .document { padding: 0; }\n  .hero { padding: 18px 20px 64px; border-radius: 10px; }\n  .hero-inner {'
    ' grid-template-columns: minmax(0, 1fr) 200px; gap: 16px 24px; }\n  h1 { font-size: 24pt; }\n  h2 { fon'
    't-size: 16pt; }\n  h3 { font-size: 12pt; }\n  h4 { font-size: 10.5pt; }\n  h1, h2, h3, h4, summary { br'
    'eak-after: avoid; }\n  .hero .introduction { font-size: 11pt; }\n  .hero-summary, .chip, .verdict-deta'
    'il, .verdict-note, .distribution-legend, .client-line { font-size: 8.5pt; }\n  .brand { display: grid'
    '; gap: 8px; }\n  .brand-plaque { width: 170px; min-height: 60px; padding: 10px; }\n  .verdict { paddin'
    'g: 12px 14px; }\n  .verdict-value { font-size: 15pt; }\n  .kpis { grid-template-columns: repeat(5, min'
    'max(0, 1fr)); gap: 8px; margin-top: -48px; padding: 0 14px; }\n  .kpi { padding: 10px 12px; }\n  .kpi-'
    'value { font-size: 18pt; white-space: normal; }\n  .kpi-value.unknown { font-size: 12pt; }\n  .kpi-uni'
    't { font-size: 9pt; }\n  .kpi-label, .kpi-note { font-size: 8pt; }\n  dt { font-size: 7.5pt; }\n  .scop'
    'e-card h2 { font-size: 13pt; }\n  .card, .filter-section, .kpi, .verdict, .table-scroll, .findings-gr'
    'oup, .finops-baseline, .checks-disclosure, .architecture-map, .architecture-tree, .reference-diagram'
    ' { box-shadow: none; }\n  .card-grid > .card, .kpi, .verdict, .score-row, .query, .priority-list li, '
    '.next-actions li, .executive-messages li, .assessment-chart, .finops-values, .reference-entry, .refe'
    'rence-lane { break-inside: avoid; }\n  .cover-facts { grid-template-columns: repeat(3, minmax(0, 1fr)'
    '); gap: 8px 16px; margin: 10px 0; }\n  .cover-facts dd { font-size: 9pt; }\n  .cover-id, .snapshot-not'
    'e { font-size: 8pt; }\n  .chapter { break-before: page; margin-top: 0; padding-top: 4px; }\n  .cluster'
    '-overview, .cluster-error { margin-top: 20px; }\n  .filter-section { padding: 12px 0 0; margin-top: 2'
    '0px; border: 0; }\n  .filter-section > h2, .filter-section > .qualification, .extra-filters, .scope-p'
    'ath { display: none; }\n  .card-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }'
    '\n  .card-grid > *, .card-grid > .span-7, .card-grid > .span-5 { grid-column: auto; }\n  .card-grid > '
    '.span-12 { grid-column: 1 / -1; }\n  .card { padding: 12px 14px; }\n  .score-layout { grid-template-co'
    'lumns: 150px minmax(0, 1fr); gap: 16px; }\n  .global-index { border-right: 1px solid var(--line); bor'
    'der-bottom: 0; padding-right: 14px; }\n  .score-value { font-size: 20pt; }\n  .score-value.unknown { f'
    'ont-size: 14pt; }\n  .pillar-scores { grid-template-columns: repeat(3, minmax(0, 1fr)); }\n  .critical'
    '-card { grid-template-columns: 150px minmax(0, 1fr); }\n  .score-row-head, .score-caption, .qualifica'
    'tion, .facts, table, .snapshot-note, .coverage-note p { font-size: 8.5pt; }\n  .table-scroll { overfl'
    'ow: visible; border-radius: 0; }\n  .wide-table { min-width: 0; table-layout: fixed; }\n  th, td { pad'
    'ding: 5px 6px; max-width: none; font-size: 7.5pt; }\n  thead { display: table-header-group; }\n  tr { '
    'break-inside: avoid; }\n  caption { font-size: 7.5pt; padding: 6px; }\n  .text-button { display: inlin'
    'e !important; color: var(--ink); font-weight: 600; min-height: 0; }\n  details { break-inside: auto; '
    '}\n  details > summary { list-style: none; min-height: 0; padding: 4px 0; }\n  details > summary::-web'
    'kit-details-marker { display: none; }\n  details:not([open]) > :not(summary) { display: block !import'
    'ant; }\n  .finding > summary { padding: 8px 10px; }\n  .finding > summary::before { display: none; }\n '
    ' .finding-title { font-size: 10pt; }\n  .finding-body { padding: 0 10px 10px; }\n  .facts { grid-templ'
    'ate-columns: 110px minmax(0, 1fr); gap: 3px 10px; }\n  .facts dd { margin-bottom: 0; }\n  .json, .comm'
    'and { max-height: none; overflow: visible; font-size: 6.5pt; line-height: 1.3; padding: 5px 6px; mar'
    'gin-top: 4px; white-space: pre-wrap; word-break: break-all; }\n  .receipt { margin-top: 2px; }\n  .rec'
    'eipt summary { font-size: 7.5pt; }\n  .print-receipts { margin-top: 6px; }\n  .print-receipts .receipt'
    ' { margin: 0; padding-top: 3px; border-top: 1px solid var(--line); }\n  .report-footer { margin-top: '
    '20px; font-size: 8pt; }\n  .assessment-chart table, .assessment-chart figcaption { font-size: 8pt; }\n'
    '  .finops-values { grid-template-columns: repeat(2, minmax(0, 1fr)); }\n  .finops-value { padding: 12'
    'px 14px; }\n  .financial-amount { font-size: 20pt; }\n  .financial-amount.unknown { font-size: 16pt; }'
    '\n  .architecture-tabs, .architecture-controls, .architecture-tree { display: none !important; }\n  .a'
    'rchitecture-layout { display: block; }\n  .architecture-panel[hidden] { display: block !important; ma'
    'rgin-top: 20px; }\n  .architecture-map { break-inside: avoid; }\n  .architecture-map > svg { min-width'
    ': 0; }\n  .reference-entry, .reference-lanes { grid-template-columns: repeat(2, minmax(0, 1fr)); }\n  '
    '.reference-platform { grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }\n  .architecture'
    '-product img { width: 28px; height: 28px; flex-basis: 28px; }\n  .reference-network, .reference-lane,'
    ' .reference-entry, .reference-diagram { padding: 12px; }\n}\n</style>\n</head>\n<body data-status="loadi'
    'ng">\n<a class="skip" href="#main">Skip to the report</a>\n<header class="toolbar no-print">\n  <div cl'
    'ass="toolbar-inner">\n    <div class="toolbar-brand"><span class="toolbar-title">Azure SRE Agent</spa'
    'n><span class="toolbar-subtitle">AKS review</span></div>\n    <nav class="toolbar-nav" aria-label="Re'
    'port sections">\n      <a href="#executive">Summary</a><a href="#inventory">Inventory</a><a href="#ar'
    'chitecture">Architecture</a><a href="#findings">Findings</a><a href="#finops">FinOps</a><a href="#ac'
    'tions">Action plan</a><a href="#methodology">Method</a>\n    </nav>\n    <div class="toolbar-controls"'
    '>\n      <span class="readonly-chip">Read-only</span>\n      <label class="jump-field" for="jump-secti'
    'on"><span class="field-text">Section</span>\n        <select id="jump-section">\n          <option val'
    'ue="cover">Cover and scope</option><option value="executive">Executive summary</option>\n          <o'
    'ption value="inventory">Observed inventory</option><option value="architecture">Architecture</option'
    '>\n          <option value="findings">Findings and coverage</option><option value="finops">FinOps</op'
    'tion>\n          <option value="actions">Action plan</option><option value="methodology">Method and s'
    'ources</option>\n        </select>\n      </label>\n      <label class="theme-field" for="theme-mode"><'
    'span class="sr-only">Color theme</span>\n        <select id="theme-mode"><option value="auto">Theme: '
    'system</option><option value="light">Theme: light</option><option value="dark">Theme: dark</option><'
    '/select>\n      </label>\n      <button id="export-json" disabled>Full JSON</button>\n      <button id='
    '"print-report" class="primary" disabled>Print / PDF</button>\n    </div>\n  </div>\n  <p id="theme-note'
    '" class="theme-note qualification" hidden></p>\n  <div class="brand-ribbon" aria-hidden="true"><span '
    'class="red"></span><span class="green"></span><span class="blue"></span><span class="yellow"></span>'
    '</div>\n</header>\n<div id="opening-state" class="opening-state" role="status">\n  <h1>AKS configuratio'
    'n review</h1>\n  <p id="opening-message">Opening the assessment snapshot.</p>\n  <p id="opening-detail'
    '" class="qualification">The data is validated before any result is shown.</p>\n</div>\n<noscript><div '
    'class="opening-state">This report needs local JavaScript to validate and display the snapshot. It ma'
    'kes no network calls. Open the file with JavaScript enabled.</div></noscript>\n<div id="report-shell"'
    ' class="shell" hidden>\n  <main id="main" class="document" tabindex="-1">\n    <section id="cover" cla'
    'ss="cover" aria-labelledby="report-title">\n      <div class="hero">\n        <div class="hero-inner">'
    '\n          <div class="hero-main">\n            <h1 id="report-title">AKS architecture and configurat'
    'ion review</h1>\n            <p class="introduction">Best practices, security, FinOps and optimizatio'
    'n for the cluster, its workloads and associated resources.</p>\n            <p id="hero-summary" clas'
    's="hero-summary"></p>\n            <div id="provenance" class="provenance" aria-label="Provenance, en'
    'vironment and reference"></div>\n          </div>\n          <div class="hero-side">\n            <div '
    'class="brand">\n              <div id="brand-plaque" class="brand-plaque"></div>\n              <p cla'
    'ss="client-line">Prepared for <span id="client-name" class="client-name"></span></p>\n            </d'
    'iv>\n            <div id="verdict" class="verdict" role="group" aria-labelledby="verdict-label"></div'
    '>\n          </div>\n          <div id="severity-distribution" class="hero-distribution"></div>\n      '
    '  </div>\n      </div>\n      <div class="page">\n        <div id="kpis" class="kpis"></div>\n        <p'
    ' id="simulation-note" class="sim-note" hidden></p>\n        <div class="card scope-card">\n          <'
    'h2 id="scope-title">Snapshot scope</h2>\n          <p class="qualification">Cluster identity, version'
    ' and state as the source returned them at the reference time.</p>\n          <dl id="cover-facts" cla'
    'ss="cover-facts"></dl>\n          <div id="cover-id" class="cover-id"></div>\n          <div class="sn'
    'apshot-note">\n            <p><strong>Point-in-time snapshot, not real-time monitoring.</strong>\n    '
    '        Missing data is shown as <strong>Not evaluated</strong>; it does not show that a configurati'
    'on is correct.\n            The indexes are local and are not an official Azure, WARA or Polaris asse'
    'ssment.</p>\n            <p>Advisory document: any action needs human review and approval.</p>\n      '
    '    </div>\n        </div>\n      </div>\n    </section>\n    <div class="page">\n    <section id="cluste'
    'r-error" class="cluster-error" role="alert" hidden></section>\n    <section id="cluster-overview" cla'
    'ss="cluster-overview card" aria-labelledby="cluster-overview-title" hidden>\n      <h2 id="cluster-ov'
    'erview-title">AKS fleet in this snapshot</h2>\n      <div class="fleet-filters no-print" role="group"'
    ' aria-label="Fleet filters">\n        <div class="field"><label for="fleet-subscription">Subscription'
    '</label><select id="fleet-subscription"></select></div>\n        <div class="field"><label for="clust'
    'er-selector">Cluster (All = fleet overview; one = detailed view)</label><select id="cluster-selector'
    '"></select></div>\n        <div class="field"><label for="fleet-search">Search cluster, resource grou'
    'p or region</label><input id="fleet-search" type="search" autocomplete="off" spellcheck="false"></di'
    'v>\n      </div>\n      <p id="fleet-scope" class="filter-count" aria-live="polite"></p>\n      <p clas'
    's="qualification">Filters change only the local view; they do not authenticate, collect or deploy an'
    'ything. A failed run keeps its error, counts as not evaluated and never inherits data from another c'
    'luster.</p>\n      <div id="fleet-view">\n        <div id="fleet-kpis" class="fleet-kpis" aria-label="'
    'Indicators for the visible clusters"></div>\n        <div id="cluster-aggregate"></div>\n        <h3>V'
    'isible clusters</h3>\n        <div id="cluster-runs-table"></div>\n        <div class="fleet-section-h'
    'ead"><h3>Findings in the visible clusters</h3>\n          <div class="field no-print"><label for="fle'
    'et-severity">Severity</label><select id="fleet-severity"><option value="">All</option><option value='
    '"critical">Critical</option><option value="high">High</option><option value="medium">Medium</option>'
    '<option value="low">Low</option></select></div>\n        </div>\n        <div id="fleet-findings"></di'
    'v>\n      </div>\n    </section>\n    <section id="executive" class="chapter" aria-labelledby="executiv'
    'e-title">\n      <div class="chapter-head">\n        <div><h2 id="executive-title">Executive summary</'
    'h2><p class="qualification">Read the conclusion together with coverage and source limits.</p></div>\n'
    '      </div>\n      <div class="card-grid">\n        <div class="card span-7">\n          <div class="s'
    'core-layout">\n            <div id="global-index" class="global-index"></div>\n            <div><h3>Lo'
    'cal index by area</h3><div id="area-scores"></div></div>\n          </div>\n        </div>\n        <di'
    'v class="card span-5">\n          <figure id="assessment-chart" class="assessment-chart" aria-labelle'
    'dby="assessment-chart-title"></figure>\n          <div id="global-coverage" class="coverage-note"></d'
    'iv>\n        </div>\n        <div class="card span-12 critical-card"><h3 id="critical-title">Critical '
    'priorities</h3><div id="critical-findings"></div></div>\n        <div class="card span-7">\n          '
    '<h3 id="next-actions-title">What to do next</h3>\n          <p class="card-sub">First actions of the '
    'plan supplied by the engine, by horizon and severity. They need human review and approval.</p>\n     '
    '     <div id="next-actions"></div>\n        </div>\n        <div class="card span-5"><h3>Engine summar'
    'y</h3><ul id="executive-messages" class="executive-messages"></ul></div>\n        <div class="card sp'
    'an-12"><h3>Local index by Well-Architected pillar</h3><div id="pillar-scores" class="pillar-scores">'
    '</div></div>\n      </div>\n    </section>\n    <section id="scope-filters" class="filter-section" aria'
    '-labelledby="filter-title">\n      <h2 id="filter-title">Explore the scope</h2>\n      <p class="quali'
    'fication">Cluster → area → namespace → workload. Filters do not recalculate the summary indexes, whi'
    'ch cover the full snapshot.</p>\n      <form id="filters-form" class="no-print">\n        <div class="'
    'filters">\n          <div class="field"><label for="filter-search">Search evidence</label><input id="'
    'filter-search" type="search" placeholder="Name, ID, check or evidence" autocomplete="off"></div>\n   '
    '       <div class="field"><label for="filter-area">Area</label><select id="filter-area"><option valu'
    'e="">All areas</option></select></div>\n          <div class="field"><label for="filter-namespace">Na'
    'mespace</label><select id="filter-namespace"><option value="">All namespaces</option></select></div>'
    '\n          <div class="field"><label for="filter-workload">Workload</label><select id="filter-worklo'
    'ad"><option value="">All workloads</option></select></div>\n        </div>\n        <details class="ex'
    'tra-filters" data-detail-key="extra-filters">\n          <summary>More filters: level, status and sev'
    'erity</summary>\n          <div class="filter-extra-grid">\n            <div class="field"><label for='
    '"filter-level">Level</label><select id="filter-level"><option value="">All levels</option></select><'
    '/div>\n            <div class="field"><label for="filter-status">Check status</label><select id="filt'
    'er-status"><option value="">All statuses</option></select></div>\n            <div class="field"><lab'
    'el for="filter-severity">Finding severity</label><select id="filter-severity"><option value="">All s'
    'everities</option></select></div>\n          </div>\n        </details>\n        <div class="filter-act'
    'ions"><button type="button" id="reset-filters">Reset filters</button><button type="button" id="expor'
    't-filtered-json">Scope JSON (all matches)</button></div>\n      </form>\n      <nav id="scope-path" cl'
    'ass="scope-path no-print" aria-label="Scope path"></nav>\n      <p id="filter-count" class="filter-co'
    'unt" role="status" aria-live="polite" aria-atomic="true"></p>\n      <p id="print-scope" class="print'
    '-only"></p>\n    </section>\n    <section id="inventory" class="chapter" aria-labelledby="inventory-ti'
    'tle">\n      <div class="chapter-head">\n        <div><h2 id="inventory-title">Observed inventory</h2>'
    '<p class="qualification">A count of the records included, not proof of completeness. Each resource c'
    'arries its source and date.</p></div>\n        <button id="export-inventory" class="no-print">Export '
    'inventory CSV</button>\n      </div>\n      <div id="inventory-counts" class="inventory-counts"></div>'
    '\n      <div class="inventory-section"><h3 id="node-pools-title">Node pools</h3><div id="node-pools">'
    '</div></div>\n      <div class="inventory-section"><h3 id="namespaces-title">Namespaces</h3><div id="'
    'namespaces"></div></div>\n      <div class="inventory-section"><h3 id="workloads-title">Workloads</h3'
    '><div id="workloads"></div></div>\n      <div class="inventory-section"><h3 id="related-resources-tit'
    'le">Associated resources</h3><div id="related-resources"></div></div>\n      <details id="technical-i'
    'nventory" class="technical-inventory" data-detail-key="technical-inventory"><summary>Additional tech'
    'nical inventory</summary><div id="technical-collections"></div></details>\n    </section>\n    <sectio'
    'n id="architecture" class="chapter" aria-labelledby="architecture-title">\n      <div class="chapter-'
    'head">\n        <div><h2 id="architecture-title">Architecture: observed and reference design</h2><p c'
    'lass="qualification">Observed relationships come from specific IDs and fields. The Microsoft proposa'
    'l is a design alternative, not detected or deployed infrastructure.</p></div>\n      </div>\n      <di'
    'v class="architecture-tabs no-print" role="tablist" aria-label="Architecture view">\n        <button '
    'id="architecture-observed-tab" role="tab" aria-selected="true" aria-controls="architecture-observed"'
    ' tabindex="0">Observed architecture</button>\n        <button id="architecture-reference-tab" role="t'
    'ab" aria-selected="false" aria-controls="architecture-reference" tabindex="-1">Reference proposal - '
    'NOT deployed</button>\n      </div>\n      <div id="architecture-observed" class="architecture-panel" '
    'role="tabpanel" aria-labelledby="architecture-observed-tab">\n        <div id="architecture-observed-'
    'note" class="architecture-note"></div>\n        <div class="architecture-controls no-print">\n        '
    '  <div class="field"><label for="architecture-kind">Resource type</label><select id="architecture-ki'
    'nd"><option value="">All types</option></select></div>\n          <div class="field"><label for="arch'
    'itecture-node">Observed resource / object</label><select id="architecture-node"></select></div>\n    '
    '    </div>\n        <div class="architecture-layout">\n          <div><figure id="architecture-map" cl'
    'ass="architecture-map" aria-label="Confirmed relationships of the selected resource"></figure><div i'
    'd="architecture-properties" class="architecture-properties"></div></div>\n          <aside id="archit'
    'ecture-tree" class="architecture-tree" aria-label="Observed resource tree"></aside>\n        </div>\n '
    '       <details class="technical-inventory" data-detail-key="architecture-nodes"><summary>All observ'
    'ed nodes and identities</summary><div id="architecture-nodes"></div></details>\n        <details clas'
    's="technical-inventory" data-detail-key="architecture-edges"><summary>All relationships, join fields'
    ' and evidence</summary><div id="architecture-edges"></div></details>\n        <details class="technic'
    'al-inventory" data-detail-key="architecture-unknowns"><summary>Relationships not evaluated and topol'
    'ogy limits</summary><div id="architecture-unknowns"></div></details>\n      </div>\n      <div id="arc'
    'hitecture-reference" class="architecture-panel" role="tabpanel" aria-labelledby="architecture-refere'
    'nce-tab" hidden></div>\n    </section>\n    <section id="findings" class="chapter" aria-labelledby="fi'
    'ndings-title">\n      <div class="chapter-head">\n        <div><h2 id="findings-title">Findings and co'
    'verage</h2><p id="findings-count" class="qualification"></p></div>\n        <div class="chapter-tools'
    ' no-print">\n          <label class="inline-field" for="findings-order">Sort\n            <select id="'
    'findings-order"><option value="severity">Severity (highest first)</option><option value="model">Engi'
    'ne order</option></select>\n          </label>\n          <button id="export-findings">Export findings'
    ' CSV</button>\n        </div>\n      </div>\n      <p class="qualification">Each finding comes from a f'
    'ailed check in the model. Its severity is never assigned to a missing source, and on its own it does'
    ' not prove a root cause or a certified compliance failure. <a class="no-print" href="#scope-filters"'
    '>Adjust filters</a></p>\n      <div id="findings-list"></div>\n      <div id="findings-pagination"></d'
    'iv>\n      <details class="checks-disclosure" data-detail-key="checks-disclosure">\n        <summary>E'
    'valuated, not evaluated and not applicable checks</summary>\n        <p class="qualification">Also in'
    'cludes passed checks. Not evaluated keeps its reason; Not applicable does not count toward the index'
    '.</p>\n        <button id="export-checks" class="no-print">Export checks CSV</button>\n        <div id'
    '="checks-table" class="inventory-section"></div>\n      </details>\n    </section>\n    <section id="fi'
    'nops" class="chapter" aria-labelledby="finops-title">\n      <div class="chapter-head">\n        <div>'
    '<h2 id="finops-title">FinOps: evidence before savings</h2><p class="qualification">Utilization, orph'
    'aned resources, costs, Spot, reservations and autoscaling: only observations and candidates supplied'
    ' by the engine are shown.</p></div>\n        <button id="export-finops" class="no-print">Export candi'
    'dates CSV</button>\n      </div>\n      <div id="finops-baseline" class="finops-baseline"></div>\n     '
    ' <p class="qualification">A candidate needs a review of its window, sample size and business need. W'
    'hen no estimate is supplied, savings are <strong>To be estimated / Not calculated</strong>: not zero'
    ' and not a promised return.</p>\n      <ul id="finops-notes" class="finops-notes"></ul>\n      <h3 id='
    '"finops-candidates-title">Candidates in the selected scope</h3>\n      <div id="finops-candidates"></'
    'div>\n      <details class="technical-inventory" data-detail-key="finops-receipts"><summary>Cost and '
    'utilization records included</summary><div id="finops-receipts"></div></details>\n    </section>\n    '
    '<section id="actions" class="chapter" aria-labelledby="actions-title">\n      <div class="chapter-hea'
    'd">\n        <div><h2 id="actions-title">Action plan for human review</h2><p class="qualification">In'
    "dicative horizons, not delivery commitments. Effort and impact need the owner's validation; this rep"
    'ort runs no action.</p></div>\n        <button id="export-actions" class="no-print">Export plan CSV</'
    'button>\n      </div>\n      <div id="action-plan"></div>\n    </section>\n    <section id="methodology"'
    ' class="chapter" aria-labelledby="methodology-title">\n      <div class="chapter-head">\n        <div>'
    '<h2 id="methodology-title">Method, sources and read limits</h2><p class="qualification">How the loca'
    'l index is calculated, which sources were read and with what limits.</p></div>\n      </div>\n      <d'
    'iv class="method-block card">\n        <h3>How to read the local index</h3>\n        <p class="prose">'
    'Local index = 100 × passed checks / evaluated checks. Coverage compares evaluated checks with evalua'
    'ted plus not evaluated checks. Not applicable checks are excluded from both denominators.</p>\n      '
    '  <p class="prose">The engine identifies each check by a unique <code>check_id</code> and never coun'
    'ts it twice in the overall index when you browse namespaces. This view shows the indexes it receives'
    '; it does not re-evaluate controls or generate recommendations.</p>\n        <p class="prose"><strong'
    '>This is not an official Azure Assessment, Azure Well-Architected, WARA or Polaris score.</strong> T'
    'he references guide the review; they do not prove compliance, absence of risk, an SLA or a root caus'
    'e.</p>\n        <div id="method-scope"></div>\n      </div>\n      <div class="method-block"><h3 id="so'
    'urces-title">Source register</h3><div id="sources-table"></div></div>\n      <details class="technica'
    'l-inventory" data-detail-key="source-data">\n        <summary>Additional observations kept</summary>\n'
    '        <p class="qualification">Additional receipts from the full model. They do not become new che'
    'cks and are not presented as compliant configurations.</p>\n        <div id="source-data-receipts"></'
    'div>\n      </details>\n      <div class="method-block card"><h3>Catalog and pinned references</h3><di'
    'v id="catalog-pins"></div></div>\n      <details class="method-block card" data-detail-key="method-qu'
    'eries"><summary id="queries-title">Included queries and limits</summary><div id="queries"></div></de'
    'tails>\n      <div class="method-block card"><h3>Declared limitations</h3><div id="limitations"></div'
    '></div>\n    </section>\n    <footer class="report-footer">\n      <p id="footer-reference"></p>\n      '
    '<p>Self-contained, read-only file. Data and exports stay local; review the identities and evidence i'
    't contains before you share it.</p>\n      <p>Interface test screenshots use explicitly simulated dat'
    'a, not customer observations.</p>\n    </footer>\n    </div>\n  </main>\n</div>\n<script type="applicatio'
    'n/json" id="report-data">__REPORT_DATA_JSON__</script>\n<script>\n"use strict";\n(async () => {\n  const'
    ' AREA = new Map([["best_practices", "Best practices"], ["security", "Security"], ["finops", "FinOps"'
    '], ["optimization", "Optimization"]]);\n  const PILLAR = new Map([["reliability", "Reliability"], ["s'
    'ecurity", "Security"], ["cost", "Cost Optimization"], ["operations", "Operational Excellence"], ["pe'
    'rformance", "Performance Efficiency"]]);\n  const LEVEL = new Map([["cluster", "Cluster"], ["workload'
    '", "Workload"], ["resource", "Associated resource"]]);\n  const STATUS = new Map([["passed", "Passed"'
    '], ["failed", "Failed"], ["not_evaluated", "Not evaluated"], ["not_applicable", "Not applicable"]]);'
    '\n  const SEVERITY = new Map([["critical", "Critical"], ["high", "High"], ["medium", "Medium"], ["low'
    '", "Low"]]);\n  const EFFORT = new Map([["low", "Low"], ["medium", "Medium"], ["high", "High"]]);\n  c'
    'onst SOURCE_STATUS = new Map([["complete", "Complete"], ["partial", "Partial"], ["denied", "Access d'
    'enied"], ["error", "Read error"], ["not_configured", "Not configured"], ["not_applicable", "Not appl'
    'icable"]]);\n  const COLLECTION = new Map([["node_pools", "Node pools"], ["namespaces", "Namespaces"]'
    ', ["workloads", "Workloads"], ["related_resources", "Associated resources"], ["nodes", "Nodes"], ["p'
    'ods", "Pods"], ["services", "Services"], ["storage_classes", "Storage classes"], ["pvcs", "Persisten'
    't volume claims (PVC)"], ["pvs", "Persistent volumes (PV)"], ["pdbs", "Pod disruption budgets (PDB)"'
    '], ["hpas", "Horizontal pod autoscalers (HPA)"], ["network_policies", "Network policies"], ["resourc'
    'e_quotas", "Resource quotas"], ["metrics", "Metrics"]]);\n  const BUCKET = new Map([["quick_win", ["Q'
    'uick wins / less than a week", "Indicative planning priority; the timeline is not guaranteed."]], ["'
    'short_term", ["Short term / one to three months", "Coordinate dependencies, owners and change window'
    's."]], ["medium_term", ["Medium term / horizon to agree", "Confirm the design, business need and seq'
    'uence with the owner."]]]);\n  const PAGE_SIZE = 25;\n  const MAX_BYTES = 64000000;\n  const MAX_CLUSTE'
    'RS = 100;\n  const readEmbedded = async () => {\n    const raw = document.getElementById("report-data"'
    ').textContent;\n    if (!raw.startsWith("gzip-base64:")) return raw;\n    if (typeof DecompressionStre'
    'am !== "function") throw new Error("This browser cannot decompress the report locally; use a current'
    ' Microsoft Edge, Chrome, Firefox or Safari.");\n    const binary = atob(raw.slice(12));\n    const byt'
    'es = new Uint8Array(binary.length);\n    for (let index = 0; index < binary.length; index += 1) bytes'
    '[index] = binary.charCodeAt(index);\n    return await new Response(new Blob([bytes]).stream().pipeThr'
    'ough(new DecompressionStream("gzip"))).text();\n  };\n  const RUN_STATUS = new Map([["ok", "Collected"'
    '], ["partial", "Partial"], ["error", "Collection error"]]);\n  const GRAPH_KINDS = new Map([["aks", "'
    'Azure Kubernetes Service (AKS)"], ["cluster", "Azure Kubernetes Service (AKS)"],\n    ["node_pool", "'
    'Node pool"], ["namespace", "Namespace"], ["workload", "Workload"], ["service", "Kubernetes Service"]'
    ',\n    ["load_balancer", "Azure Load Balancer"], ["public_load_balancer", "Public Azure Load Balancer'
    ' (ELB)"],\n    ["private_load_balancer", "Private Azure Load Balancer (ILB)"], ["subnet", "Subnet"], '
    '["vnet", "Azure Virtual Network"],\n    ["nsg", "Network Security Group"], ["disk", "Azure Managed Di'
    'sk"], ["pvc", "Kubernetes PVC"], ["pv", "Kubernetes PV"],\n    ["acr", "Azure Container Registry"], ['
    '"key_vault", "Azure Key Vault"], ["identity", "Managed Identity"],\n    ["storage", "Azure Storage"],'
    ' ["ingress", "Kubernetes Ingress"]]);\n  for (const [key, label] of [["agent_pool", "AKS node pool"],'
    ' ["managed_cluster", "Azure Kubernetes Service (AKS)"],\n    ["azure_load_balancer", "Azure Load Bala'
    'ncer"], ["load_balancer_frontend_public", "Azure Load Balancer / public frontend (ELB)"],\n    ["load'
    '_balancer_frontend_private", "Azure Load Balancer / private frontend (ILB)"], ["load_balancer_backen'
    'd_pool", "Azure Load Balancer / backend pool"],\n    ["load_balancer_probe", "Azure Load Balancer / p'
    'robe"], ["load_balancer_rule", "Azure Load Balancer / rule"],\n    ["managed_disk", "Azure Managed Di'
    'sk"], ["virtual_machine_scale_set", "Azure Virtual Machine Scale Set"],\n    ["virtual_network", "Azu'
    're Virtual Network"], ["network_security_group", "Network Security Group"],\n    ["public_ip_address"'
    ', "Azure Public IP Address"], ["container_registry", "Azure Container Registry"],\n    ["persistent_v'
    'olume", "Kubernetes PV"], ["persistent_volume_claim", "Kubernetes PVC"],\n    ["replica_set", "Kubern'
    'etes ReplicaSet"], ["pod", "Kubernetes Pod"], ["node", "Kubernetes node"]]) GRAPH_KINDS.set(key, lab'
    'el);\n  /* OFFICIAL_AZURE_ICON_DATA_START */\n  const AZURE_ICONS = new Map([["aks","data:image/svg+xm'
    'l;base64,PHN2ZyBpZD0iYWY2YTJjNDItYmQ0OC00ODU3LWE0NzktYWVjZjhiM2RlNGY2IiB4bWxucz0iaHR0cDovL3d3dy53My5'
    'vcmcvMjAwMC9zdmciIHdpZHRoPSIxOCIgaGVpZ2h0PSIxOCIgdmlld0JveD0iMCAwIDE4IDE4Ij48ZGVmcz48bGluZWFyR3JhZGl'
    'lbnQgaWQ9ImI3MGM5Y2YxLWJhYjgtNDdlMC1iYmRiLWNlMWNkNjY0ZDI2OCIgeDE9IjIuOTQiIHkxPSIzLjc0IiB4Mj0iOC42NyI'
    'geTI9IjMuNzQiIGdyYWRpZW50VW5pdHM9InVzZXJTcGFjZU9uVXNlIj48c3RvcCBvZmZzZXQ9IjAiIHN0b3AtY29sb3I9IiNiNzd'
    'hZjQiIC8+PHN0b3Agb2Zmc2V0PSIxIiBzdG9wLWNvbG9yPSIjNzczYWRjIiAvPjwvbGluZWFyR3JhZGllbnQ+PGxpbmVhckdyYWR'
    'pZW50IGlkPSJiZWI2OTk1My1iZDk2LTQ1MTUtODg0My1hYzEyNTQ2YWY5MzYiIHgxPSI5LjEzIiB5MT0iMy43OSIgeDI9IjE0Ljg'
    '1IiB5Mj0iMy43OSIgZ3JhZGllbnRVbml0cz0idXNlclNwYWNlT25Vc2UiPjxzdG9wIG9mZnNldD0iMCIgc3RvcC1jb2xvcj0iI2I'
    '3N2FmNCIgLz48c3RvcCBvZmZzZXQ9IjEiIHN0b3AtY29sb3I9IiM3NzNhZGMiIC8+PC9saW5lYXJHcmFkaWVudD48bGluZWFyR3J'
    'hZGllbnQgaWQ9ImEzOWM3NmU4LTU0N2UtNGViNC1iYzI1LWQ4MWMwZjhjZGE2MiIgeDE9IjAuMDEiIHkxPSI5LjEyIiB4Mj0iNS4'
    '3MyIgeTI9IjkuMTIiIGdyYWRpZW50VW5pdHM9InVzZXJTcGFjZU9uVXNlIj48c3RvcCBvZmZzZXQ9IjAiIHN0b3AtY29sb3I9IiN'
    'iNzdhZjQiIC8+PHN0b3Agb2Zmc2V0PSIxIiBzdG9wLWNvbG9yPSIjNzczYWRjIiAvPjwvbGluZWFyR3JhZGllbnQ+PGxpbmVhckd'
    'yYWRpZW50IGlkPSJmMGEyYTQ5MS0xN2RjLTRiYjgtYmJmYy1lZTU4YTVjZjQ3ZGEiIHgxPSI2LjE4IiB5MT0iOS4wOCIgeDI9IjE'
    'xLjkiIHkyPSI5LjA4IiBncmFkaWVudFVuaXRzPSJ1c2VyU3BhY2VPblVzZSI+PHN0b3Agb2Zmc2V0PSIwIiBzdG9wLWNvbG9yPSI'
    'jYjc3YWY0IiAvPjxzdG9wIG9mZnNldD0iMSIgc3RvcC1jb2xvcj0iIzc3M2FkYyIgLz48L2xpbmVhckdyYWRpZW50PjxsaW5lYXJ'
    'HcmFkaWVudCBpZD0iZWZjNmE1NmQtODU4NS00MTdkLTkzMWEtMWRhYzIxMTRjY2QwIiB4MT0iMTIuMzUiIHkxPSI5LjEzIiB4Mj0'
    'iMTguMDgiIHkyPSI5LjEzIiBncmFkaWVudFVuaXRzPSJ1c2VyU3BhY2VPblVzZSI+PHN0b3Agb2Zmc2V0PSIwIiBzdG9wLWNvbG9'
    'yPSIjYjc3YWY0IiAvPjxzdG9wIG9mZnNldD0iMSIgc3RvcC1jb2xvcj0iIzc3M2FkYyIgLz48L2xpbmVhckdyYWRpZW50PjxsaW5'
    'lYXJHcmFkaWVudCBpZD0iZTM5OWFhOTMtMzQxZi00ZGYyLTljMDItNjAzYjgyYjQ4NGMyIiB4MT0iMi44NyIgeTE9IjE0LjU2IiB'
    '4Mj0iOC42IiB5Mj0iMTQuNTYiIGdyYWRpZW50VW5pdHM9InVzZXJTcGFjZU9uVXNlIj48c3RvcCBvZmZzZXQ9IjAiIHN0b3AtY29'
    'sb3I9IiNiNzdhZjQiIC8+PHN0b3Agb2Zmc2V0PSIxIiBzdG9wLWNvbG9yPSIjNzczYWRjIiAvPjwvbGluZWFyR3JhZGllbnQ+PGx'
    'pbmVhckdyYWRpZW50IGlkPSJhMTUyYmJhMC1iYTJiLTQ4M2EtYjhjMS0wYWU3ZGUzNTU5OTAiIHgxPSI5LjA1IiB5MT0iMTQuNiI'
    'geDI9IjE0Ljc4IiB5Mj0iMTQuNiIgZ3JhZGllbnRVbml0cz0idXNlclNwYWNlT25Vc2UiPjxzdG9wIG9mZnNldD0iMCIgc3RvcC1'
    'jb2xvcj0iI2I3N2FmNCIgLz48c3RvcCBvZmZzZXQ9IjEiIHN0b3AtY29sb3I9IiM3NzNhZGMiIC8+PC9saW5lYXJHcmFkaWVudD4'
    '8L2RlZnM+PHRpdGxlPkljb24tY29tcHV0ZS0yMzwvdGl0bGU+PHBvbHlnb24gcG9pbnRzPSI1LjggMS4yMiAyLjk0IDEuNzUgMi4'
    '5NCA1LjY1IDUuOCA2LjI2IDguNjcgNS4xMSA4LjY3IDIuMiA1LjggMS4yMiIgZmlsbD0idXJsKCNiNzBjOWNmMS1iYWI4LTQ3ZTA'
    'tYmJkYi1jZTFjZDY2NGQyNjgpIiAvPjxwYXRoIGQ9Ik01LjkxLDYuMiw4LjUzLDUuMTRBLjIuMiwwLDAsMCw4LjY1LDVWMi4zNmE'
    'uMjEuMjEsMCwwLDAtLjEzLS4xOGwtMi42NS0uOUg1Ljc1bC0yLjYuNDhBLjIuMiwwLDAsMCwzLDEuOTRWNS40N2EuMTkuMTksMCw'
    'wLDAsLjE1LjE5bDIuNjMuNTVBLjMyLjMyLDAsMCwwLDUuOTEsNi4yWiIgZmlsbD0ibm9uZSIgLz48cGF0aCBkPSJNMi45NCwxLjc'
    '1djMuOWwyLjg5LjYxdi01Wm0xLjIyLDMuNi0uODEtLjE2di0zbC44MS0uMTNabTEuMjYuMjMtLjkzLS4xNVYybC45My0uMTZaIiB'
    'maWxsPSIjMzQxYTZlIiAvPjxwb2x5Z29uIHBvaW50cz0iMTEuOTkgMS4yNyA5LjEzIDEuOCA5LjEzIDUuNyAxMS45OSA2LjMxIDE'
    '0Ljg1IDUuMTUgMTQuODUgMi4yNSAxMS45OSAxLjI3IiBmaWxsPSJ1cmwoI2JlYjY5OTUzLWJkOTYtNDUxNS04ODQzLWFjMTI1NDZ'
    'hZjkzNikiIC8+PHBhdGggZD0iTTkuMTMsMS44VjUuN0wxMiw2LjMxdi01Wm0xLjIxLDMuNi0uODEtLjE2di0zbC44MS0uMTNabTE'
    'uMjYuMjMtLjkzLS4xNVYyLjA1bC45My0uMTdaIiBmaWxsPSIjMzQxYTZlIiAvPjxwb2x5Z29uIHBvaW50cz0iMi44NyA2LjYgMC4'
    'wMSA3LjEzIDAuMDEgMTEuMDMgMi44NyAxMS42NCA1Ljc0IDEwLjQ5IDUuNzQgNy41OCAyLjg3IDYuNiIgZmlsbD0idXJsKCNhMzl'
    'jNzZlOC01NDdlLTRlYjQtYmMyNS1kODFjMGY4Y2RhNjIpIiAvPjxwYXRoIGQ9Ik0wLDcuMTNWMTFsMi44OS42MXYtNVptMS4yMSw'
    'zLjYxLS44MS0uMTd2LTNsLjgxLS4xNFpNMi40OCwxMWwtLjkzLS4xNVY3LjM4bC45My0uMTZaIiBmaWxsPSIjMzQxYTZlIiAvPjx'
    'wb2x5Z29uIHBvaW50cz0iOS4wNCA2LjU2IDYuMTggNy4wOSA2LjE4IDEwLjk5IDkuMDQgMTEuNjEgMTEuOSAxMC40NSAxMS45IDc'
    'uNTQgOS4wNCA2LjU2IiBmaWxsPSJ1cmwoI2YwYTJhNDkxLTE3ZGMtNGJiOC1iYmZjLWVlNThhNWNmNDdkYSkiIC8+PHBhdGggZD0'
    'iTTYuMTgsNy4wOVYxMWwyLjg4LjYxdi01Wk03LjM5LDEwLjdsLS44MS0uMTd2LTNsLjgxLS4xNFptMS4yNi4yMi0uOTMtLjE1Vjc'
    'uMzRsLjkzLS4xNloiIGZpbGw9IiMzNDFhNmUiIC8+PHBvbHlnb24gcG9pbnRzPSIxNS4yMSA2LjYxIDEyLjM1IDcuMTQgMTIuMzU'
    'gMTEuMDQgMTUuMjEgMTEuNjUgMTguMDggMTAuNSAxOC4wOCA3LjU5IDE1LjIxIDYuNjEiIGZpbGw9InVybCgjZWZjNmE1NmQtODU'
    '4NS00MTdkLTkzMWEtMWRhYzIxMTRjY2QwKSIgLz48cGF0aCBkPSJNMTIuMzUsNy4xNFYxMWwyLjg5LjYxdi01Wm0xLjIyLDMuNjE'
    'tLjgxLS4xN3YtM2wuODEtLjE0Wm0xLjI2LjIyLS45My0uMTVWNy4zOWwuOTMtLjE2WiIgZmlsbD0iIzM0MWE2ZSIgLz48cG9seWd'
    'vbiBwb2ludHM9IjUuNzMgMTIuMDQgMi44NyAxMi41NiAyLjg3IDE2LjQ2IDUuNzMgMTcuMDggOC42IDE1LjkyIDguNiAxMy4wMiA'
    '1LjczIDEyLjA0IiBmaWxsPSJ1cmwoI2UzOTlhYTkzLTM0MWYtNGRmMi05YzAyLTYwM2I4MmI0ODRjMikiIC8+PHBhdGggZD0iTTU'
    'uODQsMTcsOC40NSwxNmEuMTguMTgsMCwwLDAsLjEyLS4xOHYtMi42QS4yLjIsMCwwLDAsOC40NCwxM0w1LjgsMTIuMWEuMTcuMTc'
    'sMCwwLDAtLjEyLDBsLTIuNi40N2EuMTkuMTksMCwwLDAtLjE2LjE5djMuNTRhLjE5LjE5LDAsMCwwLC4xNS4xOUw1LjcsMTdBLjI'
    'zLjIzLDAsMCwwLDUuODQsMTdaIiBmaWxsPSJub25lIiAvPjxwYXRoIGQ9Ik0yLjg3LDEyLjU2djMuOWwyLjg5LjYyVjEyWm0xLjI'
    'yLDMuNjFMMy4yOCwxNlYxM2wuODEtLjE0Wm0xLjI2LjIzLS45My0uMTVWMTIuODFsLjkzLS4xNloiIGZpbGw9IiMzNDFhNmUiIC8'
    '+PHBvbHlnb24gcG9pbnRzPSIxMS45MSAxMi4wOCA5LjA1IDEyLjYxIDkuMDUgMTYuNTEgMTEuOTEgMTcuMTIgMTQuNzggMTUuOTc'
    'gMTQuNzggMTMuMDYgMTEuOTEgMTIuMDgiIGZpbGw9InVybCgjYTE1MmJiYTAtYmEyYi00ODNhLWI4YzEtMGFlN2RlMzU1OTkwKSI'
    'gLz48cGF0aCBkPSJNOS4wNSwxMi42MXYzLjlsMi44OS42MXYtNVptMS4yMiwzLjYxLS44MS0uMTd2LTNsLjgxLS4xNFptMS4yNi4'
    'yMi0uOTMtLjE1VjEyLjg2bC45My0uMTZaIiBmaWxsPSIjMzQxYTZlIiAvPjwvc3ZnPg=="],["load_balancer","data:image'
    '/svg+xml;base64,PHN2ZyBpZD0iZTFlNzFlMjktMDY1YS00NmY3LWFkNGItNTJhZjM2YTBiZmNiIiB4bWxucz0iaHR0cDovL3d3'
    'dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIxOCIgaGVpZ2h0PSIxOCIgdmlld0JveD0iMCAwIDE4IDE4Ij48ZGVmcz48bGluZWFy'
    'R3JhZGllbnQgaWQ9ImVmODQ2NjNhLWE3YjYtNDZhNy1hMjc1LTFlNDE5ZjVlYWU2MiIgeDE9IjkiIHkxPSIxOS44NSIgeDI9Ijki'
    'IHkyPSItMS4wMiIgZ3JhZGllbnRVbml0cz0idXNlclNwYWNlT25Vc2UiPjxzdG9wIG9mZnNldD0iMCIgc3RvcC1jb2xvcj0iIzVl'
    'OTYyNCIgLz48c3RvcCBvZmZzZXQ9IjAuMDIiIHN0b3AtY29sb3I9IiM1Zjk3MjQiIC8+PHN0b3Agb2Zmc2V0PSIxIiBzdG9wLWNv'
    'bG9yPSIjNzZiYzJkIiAvPjwvbGluZWFyR3JhZGllbnQ+PC9kZWZzPjx0aXRsZT5JY29uLW5ldHdvcmtpbmctNjI8L3RpdGxlPjxw'
    'YXRoIGQ9Ik0uMTgsOC41Nyw4LjU3LjE4YS42LjYsMCwwLDEsLjg2LDBsOC4zOSw4LjM5YS42LjYsMCwwLDEsMCwuODZsLTguNCw4'
    'LjRhLjYuNiwwLDAsMS0uODQsMEwuMTgsOS40M0EuNi42LDAsMCwxLC4xOCw4LjU3WiIgZmlsbD0idXJsKCNlZjg0NjYzYS1hN2I2'
    'LTQ2YTctYTI3NS0xZTQxOWY1ZWFlNjIpIiAvPjxwYXRoIGQ9Ik0xMS4yLDQsOS4wOCwxLjg5YS4xMi4xMiwwLDAsMC0uMTYsMEw2'
    'LjgsNGEuMS4xLDAsMCwwLC4wOC4xOEg4LjEyYS4xMS4xMSwwLDAsMSwuMTEuMTF2MmEuMTEuMTEsMCwwLDAsLjExLjExSDkuNjZh'
    'LjExLjExLDAsMCwwLC4xMS0uMTF2LTJhLjExLjExLDAsMCwxLC4xMS0uMTFoMS4yNEEuMS4xLDAsMCwwLDExLjIsNFoiIGZpbGw9'
    'IiNiNGVjMzYiIC8+PHBhdGggZD0iTTQsNi42MSwxLjksOC43NGEuMTEuMTEsMCwwLDAsMCwuMTVMNCwxMWEuMTEuMTEsMCwwLDAs'
    'LjE5LS4wOFY5LjY5YS4xMS4xMSwwLDAsMSwuMTEtLjExaDJhLjEuMSwwLDAsMCwuMS0uMTFWOC4xNUEuMS4xLDAsMCwwLDYuMzMs'
    'OGgtMmEuMS4xLDAsMCwxLS4xMS0uMVY2LjY5QS4xMS4xMSwwLDAsMCw0LDYuNjFaIiBmaWxsPSIjYjRlYzM2IiAvPjxwYXRoIGQ9'
    'Ik0xNC4wOCwxMWwyLjEzLTIuMTJhLjExLjExLDAsMCwwLDAtLjE1TDE0LjA4LDYuNjFhLjExLjExLDAsMCwwLS4xOC4wOFY3Ljk0'
    'YS4xLjEsMCwwLDEtLjExLjFoLTJhLjEuMSwwLDAsMC0uMS4xMVY5LjQ3YS4xLjEsMCwwLDAsLjEuMTFoMmEuMTEuMTEsMCwwLDEs'
    'LjExLjExdjEuMjRBLjExLjExLDAsMCwwLDE0LjA4LDExWiIgZmlsbD0iI2I0ZWMzNiIgLz48cGF0aCBkPSJNMTEuNzksOWEyLjc5'
    'LDIuNzksMCwxLDAtMy41NCwyLjY3di45NWExLjcxLDEuNzEsMCwxLDAsMS41Nywwdi0xQTIuNzcsMi43NywwLDAsMCwxMS43OSw5'
    'WiIgZmlsbD0iI2ZmZiIgLz48Y2lyY2xlIGlkPSJlOTljMzM4Ny0xNWMzLTRmMjgtYmQ0Yi1jYjIwOWI0MzBlMDYiIGN4PSI5LjAx'
    'IiBjeT0iOC45OSIgcj0iMS42MiIgZmlsbD0iIzVlYTBlZiIgLz48L3N2Zz4="],["virtual_network","data:image/svg+xm'
    'l;base64,PHN2ZyBpZD0iYTE2MDZhNTItZmIxNC00NjM3LTg3ZGUtNGQ1MjRiYmExODI5IiB4bWxucz0iaHR0cDovL3d3dy53My5'
    'vcmcvMjAwMC9zdmciIHdpZHRoPSIxOCIgaGVpZ2h0PSIxOCIgdmlld0JveD0iMCAwIDE4IDE4Ij48ZGVmcz48bGluZWFyR3JhZGl'
    'lbnQgaWQ9ImYwMjBmYjdlLTIyNDMtNDUwMS04MTUzLTVkNjliZDNjMzRmNyIgeDE9IjkuODgiIHkxPSI4LjU5IiB4Mj0iMTEuNTI'
    'iIHkyPSIxMC4yMyIgZ3JhZGllbnRUcmFuc2Zvcm09InRyYW5zbGF0ZSgyLjAzIC0wLjQpIHJvdGF0ZSgtMC4wOCkiIGdyYWRpZW5'
    '0VW5pdHM9InVzZXJTcGFjZU9uVXNlIj48c3RvcCBvZmZzZXQ9IjAiIHN0b3AtY29sb3I9IiM4NmQ2MzMiIC8+PHN0b3Agb2Zmc2V'
    '0PSIxIiBzdG9wLWNvbG9yPSIjNWU5NjI0IiAvPjwvbGluZWFyR3JhZGllbnQ+PGxpbmVhckdyYWRpZW50IGlkPSJiM2MyYmM5NC0'
    '4YzdjLTQ4YTItOTcxOS02ZWU4OTlhNDNhOTciIHgxPSI2LjE4IiB5MT0iOC41OSIgeDI9IjcuODEiIHkyPSIxMC4yMyIgZ3JhZGl'
    'lbnRVbml0cz0idXNlclNwYWNlT25Vc2UiPjxzdG9wIG9mZnNldD0iMCIgc3RvcC1jb2xvcj0iIzg2ZDYzMyIgLz48c3RvcCBvZmZ'
    'zZXQ9IjEiIHN0b3AtY29sb3I9IiM1ZTk2MjQiIC8+PC9saW5lYXJHcmFkaWVudD48bGluZWFyR3JhZGllbnQgaWQ9ImU5MDBjMzV'
    'kLTA5NTgtNGQ0Zi1iMjhmLTMwMmVlYWFmNTJmNSIgeDE9IjIuNDgiIHkxPSI4LjU5IiB4Mj0iNC4xMSIgeTI9IjEwLjIzIiBncmF'
    'kaWVudFVuaXRzPSJ1c2VyU3BhY2VPblVzZSI+PHN0b3Agb2Zmc2V0PSIwIiBzdG9wLWNvbG9yPSIjODZkNjMzIiAvPjxzdG9wIG9'
    'mZnNldD0iMSIgc3RvcC1jb2xvcj0iIzVlOTYyNCIgLz48L2xpbmVhckdyYWRpZW50PjwvZGVmcz48dGl0bGU+SWNvbi1uZXR3b3J'
    'raW5nLTYxPC90aXRsZT48Y2lyY2xlIGN4PSIxMi43NCIgY3k9IjguOTkiIHI9IjEuMTYiIGZpbGw9InVybCgjZjAyMGZiN2UtMjI'
    '0My00NTAxLTgxNTMtNWQ2OWJkM2MzNGY3KSIgLz48Y2lyY2xlIGN4PSI5LjA0IiBjeT0iOSIgcj0iMS4xNiIgZmlsbD0idXJsKCN'
    'iM2MyYmM5NC04YzdjLTQ4YTItOTcxOS02ZWU4OTlhNDNhOTcpIiAvPjxjaXJjbGUgY3g9IjUuMzQiIGN5PSI5IiByPSIxLjE2IiB'
    'maWxsPSJ1cmwoI2U5MDBjMzVkLTA5NTgtNGQ0Zi1iMjhmLTMwMmVlYWFmNTJmNSkiIC8+PHBhdGggZD0iTTIuNjEsNy4yOGguOTR'
    'hLjMuMywwLDAsMSwuMy4zdjYuOTRhLjYuNiwwLDAsMS0uNi42SDIuMzFhMCwwLDAsMCwxLDAsMFY3LjU4YS4zLjMsMCwwLDEsLjM'
    'tLjNaIiB0cmFuc2Zvcm09InRyYW5zbGF0ZSgxMy4xOCAxNi45Mykgcm90YXRlKDEzNC45MikiIGZpbGw9IiM1MGU2ZmYiIC8+PHB'
    'hdGggZD0iTTIuNTYsMi45MUgzLjVhLjMuMywwLDAsMSwuMy4zdjcuNDNhMCwwLDAsMCwxLDAsMEgyLjg2YS42LjYsMCwwLDEtLjY'
    'tLjZWMy4yMWEuMy4zLDAsMCwxLC4zLS4zWiIgdHJhbnNmb3JtPSJ0cmFuc2xhdGUoNS42NiAtMC4xNikgcm90YXRlKDQ0LjkyKSI'
    'gZmlsbD0iIzE0OTBkZiIgLz48cGF0aCBkPSJNMTQuMTUsNy4yOGguOTRhLjYuNiwwLDAsMSwuNi42djYuOTRhLjMuMywwLDAsMS0'
    'uMy4zaC0uOTRhLjMuMywwLDAsMS0uMy0uM1Y3LjI4YTAsMCwwLDAsMSwwLDBaIiB0cmFuc2Zvcm09InRyYW5zbGF0ZSgxMi4zMiA'
    'tNy4yOCkgcm90YXRlKDQ1LjA4KSIgZmlsbD0iIzUwZTZmZiIgLz48cGF0aCBkPSJNMTQuODEsMi45MWguOTRhMCwwLDAsMCwxLDA'
    'sMHY3LjQzYS4zLjMsMCwwLDEtLjMuM0gxNC41YS4zLjMsMCwwLDEtLjMtLjNWMy41MWEuNi42LDAsMCwxLC42LS42WiIgdHJhbnN'
    'mb3JtPSJ0cmFuc2xhdGUoMzAuMzYgMC45OSkgcm90YXRlKDEzNS4wOCkiIGZpbGw9IiMxNDkwZGYiIC8+PC9zdmc+"],["networ'
    'k_security_group","data:image/svg+xml;base64,PHN2ZyBpZD0iYjc1OTQzYmEtMWEzZi00ODVkLWI0NWQtM2ZlZTAwZWQ'
    '3ZTVlIiB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIxOCIgaGVpZ2h0PSIxOCIgdmlld0JveD0iMCA'
    'wIDE4IDE4Ij48ZGVmcz48bGluZWFyR3JhZGllbnQgaWQ9ImZlNWNlNDNmLTI4MjMtNDYxNy1iYjU0LTU3ZGY5ZTc3ODM3MiIgeDE'
    '9IjkuMDEiIHkxPSIwLjc1IiB4Mj0iOS4wMSIgeTI9IjE3LjI1IiBncmFkaWVudFVuaXRzPSJ1c2VyU3BhY2VPblVzZSI+PHN0b3A'
    'gb2Zmc2V0PSIwIiBzdG9wLWNvbG9yPSIjNWVhMGVmIiAvPjxzdG9wIG9mZnNldD0iMC4xOCIgc3RvcC1jb2xvcj0iIzU1OWNlYyI'
    'gLz48c3RvcCBvZmZzZXQ9IjAuNDciIHN0b3AtY29sb3I9IiMzYzkxZTUiIC8+PHN0b3Agb2Zmc2V0PSIwLjg0IiBzdG9wLWNvbG9'
    'yPSIjMTM4MGRhIiAvPjxzdG9wIG9mZnNldD0iMSIgc3RvcC1jb2xvcj0iIzAwNzhkNCIgLz48L2xpbmVhckdyYWRpZW50PjwvZGV'
    'mcz48dGl0bGU+SWNvbi1uZXR3b3JraW5nLTY3PC90aXRsZT48cGF0aCBkPSJNMTYuMzYsOC40YzAsNC44NC01Ljg1LDguNzQtNy4'
    'xMiw5LjUzYS40Ni40NiwwLDAsMS0uNDgsMGMtMS4yNy0uNzktNy4xMi00LjY5LTcuMTItOS41M1YyLjU4YS40Ni40NiwwLDAsMSw'
    'uNDUtLjQ2QzYuNjQsMiw1LjU5LDAsOSwwczIuMzYsMiw2LjkxLDIuMTJhLjQ2LjQ2LDAsMCwxLC40NS40NloiIGZpbGw9IiMwMDc'
    '4ZDQiIC8+PHBhdGggZD0iTTE1Ljc1LDguNDVjMCw0LjQ0LTUuMzYsOC02LjUzLDguNzRhLjQzLjQzLDAsMCwxLS40NCwwYy0xLjE'
    '3LS43Mi02LjUzLTQuMy02LjUzLTguNzRWMy4xMWEuNDIuNDIsMCwwLDEsLjQxLS40MkM2LjgzLDIuNTgsNS44Ny43NSw5LC43NXM'
    'yLjE3LDEuODMsNi4zNCwxLjk0YS40Mi40MiwwLDAsMSwuNDEuNDJaIiBmaWxsPSIjNmJiOWYyIiAvPjxwYXRoIGQ9Ik05LDlWLjc'
    '1YzMuMTMsMCwyLjE3LDEuODMsNi4zNCwxLjk0YS40My40MywwLDAsMSwuNDEuNDNWOC40NmE0Ljg5LDQuODksMCwwLDEsMCwuNTR'
    'aTTksOUgyLjI4Yy40LDQuMTgsNS4zOCw3LjUsNi41LDguMTlhLjM5LjM5LDAsMCwwLC4xOC4wNkg5WiIgZmlsbD0idXJsKCNmZTV'
    'jZTQzZi0yODIzLTQ2MTctYmI1NC01N2RmOWU3NzgzNzIpIiAvPjxwYXRoIGQ9Ik0yLjY2LDIuNjlDNi44MywyLjU4LDUuODcuNzU'
    'sOSwuNzVWOUgyLjI4YTQuODksNC44OSwwLDAsMSwwLS41NFYzLjEyQS40My40MywwLDAsMSwyLjY2LDIuNjlaIiBmaWxsPSIjNTB'
    'lNmZmIiAvPjxwYXRoIGQ9Ik0xNS43Miw5SDl2OC4yNUg5YS4zOS4zOSwwLDAsMCwuMTgtLjA2QzEwLjM0LDE2LjUsMTUuMzIsMTM'
    'uMTgsMTUuNzIsOVoiIGZpbGw9IiM1MGU2ZmYiIC8+PC9zdmc+"],["disk","data:image/svg+xml;base64,PHN2ZyBpZD0iZ'
    'WEzMTdiMzEtYjMxYS00NGZkLWE3YzQtMjYwNzc0NTc1MzYzIiB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZ'
    'HRoPSIxOCIgaGVpZ2h0PSIxOCIgdmlld0JveD0iMCAwIDE4IDE4Ij48ZGVmcz48bGluZWFyR3JhZGllbnQgaWQ9ImEzYWVjYjVjL'
    'TExZjUtNGVjZS05OWY3LTk2NzJmMzIzNjE1NiIgeDE9IjE1LjM1IiB5MT0iMTMuNDEiIHgyPSIxNS4zNyIgeTI9IjEzLjQxIiBnc'
    'mFkaWVudFVuaXRzPSJ1c2VyU3BhY2VPblVzZSI+PHN0b3Agb2Zmc2V0PSIwIiBzdG9wLWNvbG9yPSIjMDA3OGQ0IiAvPjxzdG9wI'
    'G9mZnNldD0iMC4xNCIgc3RvcC1jb2xvcj0iIzE3ODJkYSIgLz48c3RvcCBvZmZzZXQ9IjAuMzciIHN0b3AtY29sb3I9IiMzNjhmZ'
    'TMiIC8+PHN0b3Agb2Zmc2V0PSIwLjU5IiBzdG9wLWNvbG9yPSIjNGM5OGVhIiAvPjxzdG9wIG9mZnNldD0iMC44IiBzdG9wLWNvb'
    'G9yPSIjNTk5ZWVlIiAvPjxzdG9wIG9mZnNldD0iMC45OSIgc3RvcC1jb2xvcj0iIzVlYTBlZiIgLz48L2xpbmVhckdyYWRpZW50P'
    'jxsaW5lYXJHcmFkaWVudCBpZD0iYjRkZmIzYWItMjVmZS00MTZjLWE2ZmEtZjMzZmNmYmYyMmRjIiB4MT0iNS41MSIgeTE9IjgwM'
    'i41IiB4Mj0iMTIuOTQiIHkyPSI4MTAuNTgiIGdyYWRpZW50VHJhbnNmb3JtPSJ0cmFuc2xhdGUoMCAtMTI3OC43Nikgc2NhbGUoM'
    'SAxLjU5KSIgZ3JhZGllbnRVbml0cz0idXNlclNwYWNlT25Vc2UiPjxzdG9wIG9mZnNldD0iMCIgc3RvcC1jb2xvcj0iIzAwNzhkN'
    'CIgLz48c3RvcCBvZmZzZXQ9IjAuMDIiIHN0b3AtY29sb3I9IiMwZDdlZDgiIC8+PHN0b3Agb2Zmc2V0PSIwLjA4IiBzdG9wLWNvb'
    'G9yPSIjMmI4YWUwIiAvPjxzdG9wIG9mZnNldD0iMC4xNSIgc3RvcC1jb2xvcj0iIzQxOTRlNyIgLz48c3RvcCBvZmZzZXQ9IjAuM'
    'jIiIHN0b3AtY29sb3I9IiM1MTliZWIiIC8+PHN0b3Agb2Zmc2V0PSIwLjI5IiBzdG9wLWNvbG9yPSIjNWI5ZmVlIiAvPjxzdG9wI'
    'G9mZnNldD0iMC40IiBzdG9wLWNvbG9yPSIjNWVhMGVmIiAvPjxzdG9wIG9mZnNldD0iMC41NSIgc3RvcC1jb2xvcj0iIzViOWZlZ'
    'SIgLz48c3RvcCBvZmZzZXQ9IjAuNjgiIHN0b3AtY29sb3I9IiM1MDlhZWIiIC8+PHN0b3Agb2Zmc2V0PSIwLjgiIHN0b3AtY29sb'
    '3I9IiMzZjkyZTYiIC8+PHN0b3Agb2Zmc2V0PSIwLjkxIiBzdG9wLWNvbG9yPSIjMjY4OGRmIiAvPjxzdG9wIG9mZnNldD0iMC45O'
    'SIgc3RvcC1jb2xvcj0iIzEyN2ZkOSIgLz48L2xpbmVhckdyYWRpZW50PjwvZGVmcz48dGl0bGU+SWNvbi1jb21wdXRlLTMyPC90a'
    'XRsZT48ZWxsaXBzZSBjeD0iOC45NiIgY3k9IjExLjgyIiByeD0iNy41IiByeT0iMy4wOCIgZmlsbD0iIzc2YmMyZCIgLz48ZWxsa'
    'XBzZSBjeD0iOS4xNSIgY3k9IjExLjc5IiByeD0iMi40OSIgcnk9IjAuNjgiIGZpbGw9IiM1ZTk2MjQiIC8+PHBhdGggZD0iTTE1L'
    'jM1LDEzLjRsMCwwWiIgZmlsbD0idXJsKCNhM2FlY2I1Yy0xMWY1LTRlY2UtOTlmNy05NjcyZjMyMzYxNTYpIiAvPjxlbGxpcHNlI'
    'GN4PSI4Ljk2IiBjeT0iNC45OSIgcng9IjcuNSIgcnk9IjMuMDgiIGZpbGw9InVybCgjYjRkZmIzYWItMjVmZS00MTZjLWE2ZmEtZ'
    'jMzZmNmYmYyMmRjKSIgLz48ZWxsaXBzZSBjeD0iOS4xNSIgY3k9IjQuOTUiIHJ4PSIyLjQ5IiByeT0iMC42OCIgZmlsbD0iIzAwN'
    'WJhMSIgLz48cGF0aCBkPSJNOSwxNC44NGM0LjE1LDAsNy41LTEuMzgsNy41LTMuMDhoMHYxLjgyaDBjLS4xNCwxLjY1LTMuNDQsM'
    'y03LjUsM3MtNy41LTEuMzgtNy41LTMuMDhWMTEuNzZDMS40NiwxMy40Niw0LjgyLDE0Ljg0LDksMTQuODRaIiBmaWxsPSIjNWU5N'
    'jI0IiAvPjxwYXRoIGQ9Ik0xNS4zNSwxMy40bDAsMFoiIGZpbGw9InVybCgjYTNhZWNiNWMtMTFmNS00ZWNlLTk5ZjctOTY3MmYzM'
    'jM2MTU2KSIgLz48cGF0aCBkPSJNOSw4YzQuMTUsMCw3LjUtMS4zOCw3LjUtMy4wOGgwVjYuNzRoMGMtLjE0LDEuNjUtMy40NCwzL'
    'TcuNSwzcy03LjUtMS4zOC03LjUtMy4wOFY0LjkyQzEuNDYsNi42Miw0LjgyLDgsOSw4WiIgZmlsbD0iIzAwNzhkNCIgLz48L3N2Z'
    'z4="],["container_registry","data:image/svg+xml;base64,PHN2ZyBpZD0iZTlmN2JhNzMtNTZiOC00ODY0LTk2ZmYtZ'
    'GNlODBiZWY3MjlhIiB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIxOCIgaGVpZ2h0PSIxOCIgdmlld'
    '0JveD0iMCAwIDE4IDE4Ij48ZGVmcz48bGluZWFyR3JhZGllbnQgaWQ9ImJkZjI3ZGM2LTAyNWMtNDgwNS04YmZkLTNhMDVkZWZkM'
    '2ZiZCIgeDE9IjguNjM3IiB5MT0iLTEuOTkxIiB4Mj0iOC42MzciIHkyPSIxNi43MzkiIGdyYWRpZW50VW5pdHM9InVzZXJTcGFjZ'
    'U9uVXNlIj48c3RvcCBvZmZzZXQ9IjAiIHN0b3AtY29sb3I9IiM1ZWEwZWYiIC8+PHN0b3Agb2Zmc2V0PSIxIiBzdG9wLWNvbG9yP'
    'SIjMDA3OGQ0IiAvPjwvbGluZWFyR3JhZGllbnQ+PGxpbmVhckdyYWRpZW50IGlkPSJmY2Q2YzZjNy1lMmViLTRhMzItYjkxNC0zY'
    'Tg0ODU1ODVhMWIiIHgxPSIxMi45NiIgeTE9IjguNTYxIiB4Mj0iMTIuOTYiIHkyPSI2LjE0MSIgZ3JhZGllbnRUcmFuc2Zvcm09I'
    'm1hdHJpeCgxLCAwLCAwLCAtMSwgMCwgMjApIiBncmFkaWVudFVuaXRzPSJ1c2VyU3BhY2VPblVzZSI+PHN0b3Agb2Zmc2V0PSIwI'
    'iBzdG9wLWNvbG9yPSIjMzMzMTMyIiAvPjxzdG9wIG9mZnNldD0iMSIgc3RvcC1jb2xvcj0iIzViNWE1YyIgLz48L2xpbmVhckdyY'
    'WRpZW50PjwvZGVmcz48cGF0aCBkPSJNNy40Myw4LjE3OGwyLjU4OS0xLjU3Myw3LjI1NSwyLjczMUEzLjY2NCwzLjY2NCwwLDAsM'
    'CwxNi4yMyw3LjQ5bC0uMDEtLjA1QTQuMTk0LDQuMTk0LDAsMCwwLDE0LDYuMzJhNC45MSw0LjkxLDAsMCwwLTUuMS00LjdBNS4wN'
    'zEsNS4wNzEsMCwwLDAsNC4wNiw0LjkxLDQuNjIxLDQuNjIxLDAsMCwwLDAsOS4zOWE0LjczLDQuNzMsMCwwLDAsNC44OSw0LjU0S'
    'DcuNDNaIiBmaWxsPSJ1cmwoI2JkZjI3ZGM2LTAyNWMtNDgwNS04YmZkLTNhMDVkZWZkM2ZiZCkiIC8+PHBvbHlnb24gcG9pbnRzP'
    'SIxMC4wNyA3LjE1OSAxMC4wOCAxMS40MzkgMTcuOTkgMTMuMTE5IDE3Ljk5IDEwLjEzOSAxMC4wNyA3LjE1OSIgZmlsbD0iIzc2N'
    'zY3NiIgLz48cG9seWxpbmUgcG9pbnRzPSIxMC4wNyA3LjE1OSA3LjkzIDguNDU5IDcuOTMgMTIuNDM5IDEwLjA4IDExLjQzOSIgZ'
    'mlsbD0iIzk5OSIgLz48cG9seWdvbiBwb2ludHM9IjEzLjY4IDExLjQ5OSAxNC40IDExLjY5OSAxNC40IDkuMzY5IDEzLjY4IDkuM'
    'TE5IDEzLjY4IDExLjQ5OSIgZmlsbD0iI2EzYTNhMyIgLz48cG9seWdvbiBwb2ludHM9IjEyLjk2IDguODg5IDEyLjI0IDguNjI5I'
    'DEyLjI0IDExLjExOSAxMi45NiAxMS4zMTkgMTIuOTYgOC44ODkiIGZpbGw9IiNhM2EzYTMiIC8+PHBvbHlnb24gcG9pbnRzPSIxN'
    'S4xMiAxMS44ODkgMTUuODIgMTIuMDc5IDE1Ljg0IDkuODU5IDE1LjEyIDkuNjE5IDE1LjEyIDExLjg4OSIgZmlsbD0iI2EzYTNhM'
    'yIgLz48cG9seWdvbiBwb2ludHM9IjEwLjgxIDEwLjc0OSAxMS41MyAxMC45MjkgMTEuNTMgOC4zOTkgMTAuODEgOC4xNTkgMTAuO'
    'DEgMTAuNzQ5IiBmaWxsPSIjYTNhM2EzIiAvPjxwb2x5Z29uIHBvaW50cz0iMTcuMjcgMTAuMzQ5IDE2LjU1IDEwLjA5OSAxNi41N'
    'SAxMi4yNjkgMTcuMjcgMTIuNDY5IDE3LjI3IDEwLjM0OSIgZmlsbD0iI2EzYTNhMyIgLz48cGF0aCBpZD0iZWYwZDFiNTQtYTFlN'
    'y00Y2I5LWE0ZTUtOGE4NTE4ZTdjMTI3IiBkPSJNOC42NiwxMS4zNjlsLS4zNi4yMVY4Ljc0OWwuMzYtLjE5Wm0uNzEtMy4yMkw5L'
    'DguMzg5djIuNzVsLjM3LS4yWiIgZmlsbD0iI2IzYjNiMyIgLz48cG9seWdvbiBwb2ludHM9IjE3Ljk5IDEzLjExOSAxNS44MyAxM'
    'y44NTkgNy45MyAxMi40MzkgMTAuMDggMTEuNDM5IDE3Ljk5IDEzLjExOSIgZmlsbD0idXJsKCNmY2Q2YzZjNy1lMmViLTRhMzItY'
    'jkxNC0zYTg0ODU1ODVhMWIpIiAvPjxwb2x5Z29uIHBvaW50cz0iMTcuOTkgMTYuMTY5IDEwLjA0IDE3LjY3OSAxMC4wOCAxMi4wO'
    'DkgMTcuOTkgMTMuNTU5IDE3Ljk5IDE2LjE2OSIgZmlsbD0iIzc2NzY3NiIgLz48cG9seWdvbiBwb2ludHM9IjEwLjgxIDE2Ljc1O'
    'SAxMC44MSAxMy4yMDkgMTEuNTMgMTMuMjk5IDExLjUzIDE2LjYzOSAxMC44MSAxNi43NTkiIGZpbGw9IiNhM2EzYTMiIC8+PHBvb'
    'Hlnb24gcG9pbnRzPSIxMi45NiAxNi4zOTkgMTIuMjQgMTYuNTI5IDEyLjI0IDEzLjM4OSAxMi45NiAxMy40OTkgMTIuOTYgMTYuM'
    'zk5IDEyLjk2IDE2LjM5OSIgZmlsbD0iI2EzYTNhMyIgLz48cG9seWdvbiBwb2ludHM9IjEzLjY4IDE2LjI4OSAxMy42OCAxMy41N'
    'jkgMTQuNCAxMy42NTkgMTQuNCAxNi4xNTkgMTMuNjggMTYuMjg5IiBmaWxsPSIjYTNhM2EzIiAvPjxwb2x5Z29uIHBvaW50cz0iM'
    'TUuODMgMTUuOTA5IDE1LjEyIDE2LjAzOSAxNS4xMiAxMy43NDkgMTUuODMgMTMuODU5IDE1LjgzIDE1LjkwOSIgZmlsbD0iI2EzY'
    'TNhMyIgLz48cG9seWdvbiBwb2ludHM9IjE3LjI5IDE1LjY3OSAxNi41NSAxNS44MDkgMTYuNTUgMTMuOTI5IDE3LjI0IDE0LjAxO'
    'SAxNy4yOSAxNS42NzkiIGZpbGw9IiNhM2EzYTMiIC8+PHBhdGggaWQ9ImI5ZjI1ZWI0LTRjODgtNDVjMi1iYzRkLWY5OTI3NTdkN'
    '2UwZSIgZD0iTTcuOTMsMTYuNHYtMy4yNmwyLjE2LTF2NS42WiIgZmlsbD0iIzk5OSIgLz48cGF0aCBpZD0iZWI5MjAwYTctNDY5M'
    'y00NDI3LWJkYWUtYjMzY2U5MGZmN2YyIiBkPSJNOC42MSwxNi4zODlsLS4zMi0uMTZ2LTIuNzZsLjMyLS4xNVptLjc3LTMuNDUtL'
    'jM4LjE5djMuNDhsLjM3LjE5di0zLjg2WiIgZmlsbD0iI2IzYjNiMyIgLz48L3N2Zz4="],["key_vault","data:image/svg+x'
    'ml;base64,PHN2ZyBpZD0iYmM5MzE2OWEtMjRjNC00Njg2LTlmMzctYzdlNGY1M2IzZDM0IiB4bWxucz0iaHR0cDovL3d3dy53My'
    '5vcmcvMjAwMC9zdmciIHdpZHRoPSIxOCIgaGVpZ2h0PSIxOCIgdmlld0JveD0iMCAwIDE4IDE4Ij48ZGVmcz48cmFkaWFsR3JhZG'
    'llbnQgaWQ9ImZiMTE0YzkzLTdjMTYtNDU0MC04OTlhLTA3OTYwNDE2MjllNiIgY3g9IjkiIGN5PSI5IiByPSI4LjUiIGdyYWRpZW'
    '50VW5pdHM9InVzZXJTcGFjZU9uVXNlIj48c3RvcCBvZmZzZXQ9IjAuMTgiIHN0b3AtY29sb3I9IiM1ZWEwZWYiIC8+PHN0b3Agb2'
    'Zmc2V0PSIwLjU2IiBzdG9wLWNvbG9yPSIjNWM5ZmVlIiAvPjxzdG9wIG9mZnNldD0iMC42OSIgc3RvcC1jb2xvcj0iIzU1OWNlZC'
    'IgLz48c3RvcCBvZmZzZXQ9IjAuNzgiIHN0b3AtY29sb3I9IiM0YTk3ZTkiIC8+PHN0b3Agb2Zmc2V0PSIwLjg2IiBzdG9wLWNvbG'
    '9yPSIjMzk5MGU0IiAvPjxzdG9wIG9mZnNldD0iMC45MyIgc3RvcC1jb2xvcj0iIzIzODdkZSIgLz48c3RvcCBvZmZzZXQ9IjAuOT'
    'kiIHN0b3AtY29sb3I9IiMwODdiZDYiIC8+PHN0b3Agb2Zmc2V0PSIxIiBzdG9wLWNvbG9yPSIjMDA3OGQ0IiAvPjwvcmFkaWFsR3'
    'JhZGllbnQ+PHJhZGlhbEdyYWRpZW50IGlkPSJlYzQ3OGJkMy01YjM4LTRlN2YtYjY2MS0xMWYzNTU1NzhiZmYiIGN4PSIzOC45NS'
    'IgY3k9IjE4Mi4wNyIgcj0iOS44OCIgZ3JhZGllbnRUcmFuc2Zvcm09InRyYW5zbGF0ZSgtMjguNzEgLTE2My4yNCkgc2NhbGUoMC'
    '45NCAwLjk0KSIgZ3JhZGllbnRVbml0cz0idXNlclNwYWNlT25Vc2UiPjxzdG9wIG9mZnNldD0iMC4yNyIgc3RvcC1jb2xvcj0iI2'
    'ZmZDcwZiIgLz48c3RvcCBvZmZzZXQ9IjAuNDkiIHN0b3AtY29sb3I9IiNmZmNiMTIiIC8+PHN0b3Agb2Zmc2V0PSIwLjg4IiBzdG'
    '9wLWNvbG9yPSIjZmVhYzE5IiAvPjxzdG9wIG9mZnNldD0iMSIgc3RvcC1jb2xvcj0iI2ZlYTExYiIgLz48L3JhZGlhbEdyYWRpZW'
    '50PjwvZGVmcz48dGl0bGU+SWNvbi1zZWN1cml0eS0yNDU8L3RpdGxlPjxwYXRoIGlkPSJhYWNmODMxMS1hMzE3LTQwMGYtYjYxMy'
    '03NGJkMDBkYTVjZTMiIGQ9Ik05LC41QTguNSw4LjUsMCwxLDAsMTcuNSw5LDguNTEsOC41MSwwLDAsMCw5LC41Wk05LDE2LjM0QT'
    'cuMzQsNy4zNCwwLDEsMSwxNi4zNCw5LDcuMzQsNy4zNCwwLDAsMSw5LDE2LjM0WiIgZmlsbD0idXJsKCNmYjExNGM5My03YzE2LT'
    'Q1NDAtODk5YS0wNzk2MDQxNjI5ZTYpIiAvPjxjaXJjbGUgY3g9IjkiIGN5PSI5IiByPSI3LjM0IiBmaWxsPSIjZmZmIiAvPjxnPj'
    'xwYXRoIGlkPSJiZDk4M2M0MS1kYjczLTQwZWMtYTRmNC1kYTEyMTNmYzk5MjQiIGQ9Ik0xMy40NCw3LjMzYTEuODQsMS44NCwwLD'
    'AsMCwwLTIuNTloMEwxMC4yOSwxLjU4YTEuODMsMS44MywwLDAsMC0yLjU4LDBoMEw0LjU2LDQuNzRhMS44NCwxLjg0LDAsMCwwLD'
    'AsMi41OUw3LjE4LDEwYS41MS41MSwwLDAsMSwuMTUuMzZ2NC44OGEuNjMuNjMsMCwwLDAsLjE4LjQ0bDEuMiwxLjJhLjQxLjQxLD'
    'AsMCwwLC41OCwwbDEuMTYtMS4xNmgwbC42OC0uNjhhLjI1LjI1LDAsMCwwLDAtLjM0bC0uNDktLjQ5YS4yNy4yNywwLDAsMSwwLS'
    '4zN2wuNDktLjQ5YS4yNS4yNSwwLDAsMCwwLS4zNGwtLjQ5LS40OWEuMjcuMjcsMCwwLDEsMC0uMzdsLjQ5LS40OWEuMjUuMjUsMC'
    'wwLDAsMC0uMzRsLS42OC0uNjl2LS4yNVpNOSwyLjM1QTEsMSwwLDAsMSw5LDQuNDIsMSwxLDAsMSwxLDksMi4zNVoiIGZpbGw9In'
    'VybCgjZWM0NzhiZDMtNWIzOC00ZTdmLWI2NjEtMTFmMzU1NTc4YmZmKSIgLz48cGF0aCBpZD0iYWQyZTdlNDQtOWJmZC00Nzc1LT'
    'hiZjQtOGVmMjZhNTQ0OTIxIiBkPSJNOC4xOCwxNS4zaDBhLjIzLjIzLDAsMCwwLC4zOC0uMTd2LTRhLjI0LjI0LDAsMCwwLS4xMS'
    '0uMmgwYS4yMi4yMiwwLDAsMC0uMzQuMnY0QS4yOC4yOCwwLDAsMCw4LjE4LDE1LjNaIiBmaWxsPSIjZmY5MzAwIiBvcGFjaXR5PS'
    'IwLjc1IiAvPjxyZWN0IGlkPSJhOTk2ZmJmZi0zOTM2LTRiMjQtYjQwNy0zNjkzMzZjMTQzYmEiIHg9IjYuNDgiIHk9IjUuNzkiIH'
    'dpZHRoPSI1LjE3IiBoZWlnaHQ9IjAuNjEiIHJ4PSIwLjI4IiBmaWxsPSIjZmY5MzAwIiBvcGFjaXR5PSIwLjc1IiAvPjxyZWN0IG'
    'lkPSJiYjEyZDMxYy0zMzUyLTRhMTgtODdkZC1hMTY5YTRhODcyMWQiIHg9IjYuNDgiIHk9IjYuNzgiIHdpZHRoPSI1LjE3IiBoZW'
    'lnaHQ9IjAuNjEiIHJ4PSIwLjI4IiBmaWxsPSIjZmY5MzAwIiBvcGFjaXR5PSIwLjc1IiAvPjwvZz48L3N2Zz4="],["managed_i'
    'dentity","data:image/svg+xml;base64,PHN2ZyBpZD0iZjgwN2NkZGUtMThmMi00NTc0LWJhMTQtZjBiMWVlZjk0YTRhIiB4'
    'bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIxOCIgaGVpZ2h0PSIxOCIgdmlld0JveD0iMCAwIDE4IDE4'
    'Ij48ZGVmcz48bGluZWFyR3JhZGllbnQgaWQ9ImJiNjdiMTU0LWFmOGYtNGE1My1hOWNlLWFhMDQ2YjkzOThlOSIgeDE9IjEzLjE4'
    'IiB5MT0iMTMuMDEiIHgyPSI4LjYzIiB5Mj0iNC4zOCIgZ3JhZGllbnRVbml0cz0idXNlclNwYWNlT25Vc2UiPjxzdG9wIG9mZnNl'
    'dD0iMCIgc3RvcC1jb2xvcj0iIzE5ODhkOSIgLz48c3RvcCBvZmZzZXQ9IjAuOSIgc3RvcC1jb2xvcj0iIzU0YWVmMCIgLz48L2xp'
    'bmVhckdyYWRpZW50PjxsaW5lYXJHcmFkaWVudCBpZD0iYTQ3ZDcxMzgtMDg0YS00NzFkLThkNjMtNzQ0ZTc1YjllOGEzIiB4MT0i'
    'MTEuMjIiIHkxPSIxMC41IiB4Mj0iMTQuMzciIHkyPSIxNS45MyIgZ3JhZGllbnRVbml0cz0idXNlclNwYWNlT25Vc2UiPjxzdG9w'
    'IG9mZnNldD0iMC4xIiBzdG9wLWNvbG9yPSIjNTRhZWYwIiAvPjxzdG9wIG9mZnNldD0iMC4yOSIgc3RvcC1jb2xvcj0iIzRmYWJl'
    'ZSIgLz48c3RvcCBvZmZzZXQ9IjAuNTEiIHN0b3AtY29sb3I9IiM0MWEyZTkiIC8+PHN0b3Agb2Zmc2V0PSIwLjc0IiBzdG9wLWNv'
    'bG9yPSIjMmE5M2UwIiAvPjxzdG9wIG9mZnNldD0iMC44OCIgc3RvcC1jb2xvcj0iIzE5ODhkOSIgLz48L2xpbmVhckdyYWRpZW50'
    'PjwvZGVmcz48dGl0bGU+SWNvbi1pZGVudGl0eS0yMjc8L3RpdGxlPjxnPjxwb2x5Z29uIHBvaW50cz0iMS4xNSAxMC4yMiA4Ljkz'
    'IDE1LjI3IDE2Ljg1IDEwLjIxIDE3Ljg1IDExLjM2IDguOTMgMTcuMTEgMC4xNSAxMS4zNyAxLjE1IDEwLjIyIiBmaWxsPSIjNTBl'
    'NmZmIiAvPjxwb2x5Z29uIHBvaW50cz0iMS43MyA5LjU4IDguOTMgMSAxNi4yOCA5LjU5IDguOTMgMTQuMjMgMS43MyA5LjU4IiBm'
    'aWxsPSIjZmZmIiAvPjxwb2x5Z29uIHBvaW50cz0iOC45MyAxIDguOTMgMTQuMjMgMS43MyA5LjU4IDguOTMgMSIgZmlsbD0iIzUw'
    'ZTZmZiIgLz48cG9seWdvbiBwb2ludHM9IjguOTMgMSA4LjkzIDE0LjIzIDE2LjI4IDkuNTkgOC45MyAxIiBmaWxsPSJ1cmwoI2Ji'
    'NjdiMTU0LWFmOGYtNGE1My1hOWNlLWFhMDQ2YjkzOThlOSkiIC8+PHBvbHlnb24gcG9pbnRzPSI4LjkzIDcuODMgMTYuMjggOS41'
    'OSA4LjkzIDE0LjIzIDguOTMgNy44MyIgZmlsbD0iIzUzYjFlMCIgLz48cG9seWdvbiBwb2ludHM9IjguOTMgMTQuMjMgMS43MyA5'
    'LjU4IDguOTMgNy44MyA4LjkzIDE0LjIzIiBmaWxsPSIjOWNlYmZmIiAvPjxwb2x5Z29uIHBvaW50cz0iOC45MyAxNy4xMSAxNy44'
    'NSAxMS4zNiAxNi44NSAxMC4yMSA4LjkzIDE1LjI3IDguOTMgMTcuMTEiIGZpbGw9InVybCgjYTQ3ZDcxMzgtMDg0YS00NzFkLThk'
    'NjMtNzQ0ZTc1YjllOGEzKSIgLz48Zz48cGF0aCBpZD0iZTE4OWE2MWYtNjMxYS00MTIyLWJiMmItMDc5ZTg2MDA0ZDk2IiBkPSJN'
    'MTYuMzIsMTEuODhhMS4xNiwxLjE2LDAsMCwwLDAtMS42NWgwbC0yLTJhMS4xNiwxLjE2LDAsMCwwLTEuNjQsMGgwbC0yLDJhMS4x'
    'OCwxLjE4LDAsMCwwLDAsMS42NWwxLjY3LDEuNjdhLjMyLjMyLDAsMCwxLC4wOS4yM3YzLjFhLjM2LjM2LDAsMCwwLC4xMi4yOGwu'
    'NzYuNzZhLjI1LjI1LDAsMCwwLC4zNywwbC43My0uNzNoMGwuNDQtLjQ0YS4xNS4xNSwwLDAsMCwwLS4yMWwtLjMxLS4zMWEuMTYu'
    'MTYsMCwwLDEsMC0uMjRsLjMxLS4zMWEuMTYuMTYsMCwwLDAsMC0uMjJsLS4zMS0uMzFhLjE1LjE1LDAsMCwxLDAtLjIzbC4zMS0u'
    'MzJhLjE1LjE1LDAsMCwwLDAtLjIxbC0uNDQtLjQ0di0uMTZaTTEzLjUsOC43MWEuNjYuNjYsMCwxLDEtLjY2LjY2LjY2LjY2LDAs'
    'MCwxLC42Ni0uNjZaIiBmaWxsPSIjZmZjYTAwIiAvPjxwYXRoIGlkPSJmYjcwMzNlZS00NjUwLTQ4ODYtODBjNy1lZGRmNjI1NjBm'
    'ODUiIGQ9Ik0xMywxN2gwYS4xNC4xNCwwLDAsMCwuMjQtLjExVjE0LjMzYS4xNi4xNiwwLDAsMC0uMDYtLjEzaDBhLjE0LjE0LDAs'
    'MCwwLS4yMi4xM3YyLjUxQS4xNS4xNSwwLDAsMCwxMywxN1oiIGZpbGw9IiNmZjkzMDAiIG9wYWNpdHk9IjAuNzUiIC8+PHJlY3Qg'
    'aWQ9ImIxNjZiOGMyLWI5ZWUtNGMzZC1iZjdhLTc3YmQ1Y2UwNTcwYiIgeD0iMTEuOSIgeT0iMTAuOSIgd2lkdGg9IjMuMjkiIGhl'
    'aWdodD0iMC4zOSIgcng9IjAuMTgiIGZpbGw9IiNmZjkzMDAiIG9wYWNpdHk9IjAuNzUiIC8+PHJlY3QgaWQ9ImJhZjQzN2ZlLTM0'
    'ODMtNGEyNS05NGJhLTFlODRhNjRjZDJlYiIgeD0iMTEuOSIgeT0iMTEuNTMiIHdpZHRoPSIzLjI5IiBoZWlnaHQ9IjAuMzkiIHJ4'
    'PSIwLjE4IiBmaWxsPSIjZmY5MzAwIiBvcGFjaXR5PSIwLjc1IiAvPjwvZz48L2c+PC9zdmc+"],["storage_account","data:'
    'image/svg+xml;base64,PHN2ZyBpZD0iZjJmMDQzNDktOGFlZS00NDEzLTg0YzktYTkwNTM2MTFiMzE5IiB4bWxucz0iaHR0cDo'
    'vL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIxOCIgaGVpZ2h0PSIxOCIgdmlld0JveD0iMCAwIDE4IDE4Ij48ZGVmcz48bGl'
    'uZWFyR3JhZGllbnQgaWQ9ImFkNGM0Zjk2LTA5YWEtNGY5MS1iYTEwLTVjYjhhZDUzMGY3NCIgeDE9IjkiIHkxPSIxNS44MyIgeDI'
    '9IjkiIHkyPSI1Ljc5IiBncmFkaWVudFVuaXRzPSJ1c2VyU3BhY2VPblVzZSI+PHN0b3Agb2Zmc2V0PSIwIiBzdG9wLWNvbG9yPSI'
    'jYjNiM2IzIiAvPjxzdG9wIG9mZnNldD0iMC4yNiIgc3RvcC1jb2xvcj0iI2MxYzFjMSIgLz48c3RvcCBvZmZzZXQ9IjEiIHN0b3A'
    'tY29sb3I9IiNlNmU2ZTYiIC8+PC9saW5lYXJHcmFkaWVudD48L2RlZnM+PHRpdGxlPkljb24tc3RvcmFnZS04NjwvdGl0bGU+PHB'
    'hdGggZD0iTS41LDUuNzloMTdhMCwwLDAsMCwxLDAsMHY5LjQ4YS41Ny41NywwLDAsMS0uNTcuNTdIMS4wN2EuNTcuNTcsMCwwLDE'
    'tLjU3LS41N1Y1Ljc5QTAsMCwwLDAsMSwuNSw1Ljc5WiIgZmlsbD0idXJsKCNhZDRjNGY5Ni0wOWFhLTRmOTEtYmExMC01Y2I4YWQ'
    '1MzBmNzQpIiAvPjxwYXRoIGQ9Ik0xLjA3LDIuMTdIMTYuOTNhLjU3LjU3LDAsMCwxLC41Ny41N1Y1Ljc5YTAsMCwwLDAsMSwwLDB'
    'ILjVhMCwwLDAsMCwxLDAsMFYyLjczQS41Ny41NywwLDAsMSwxLjA3LDIuMTdaIiBmaWxsPSIjMzdjMmIxIiAvPjxwYXRoIGQ9Ik0'
    'yLjgxLDYuODlIMTUuMThhLjI3LjI3LDAsMCwxLC4yNi4yN3YxLjRhLjI3LjI3LDAsMCwxLS4yNi4yN0gyLjgxYS4yNy4yNywwLDA'
    'sMS0uMjYtLjI3VjcuMTZBLjI3LjI3LDAsMCwxLDIuODEsNi44OVoiIGZpbGw9IiNmZmYiIC8+PHBhdGggZD0iTTIuODIsOS42OEg'
    'xNS4xOWEuMjcuMjcsMCwwLDEsLjI2LjI3djEuNDFhLjI3LjI3LDAsMCwxLS4yNi4yN0gyLjgyYS4yNy4yNywwLDAsMS0uMjYtLjI'
    '3VjEwQS4yNy4yNywwLDAsMSwyLjgyLDkuNjhaIiBmaWxsPSIjMzdjMmIxIiAvPjxwYXRoIGQ9Ik0yLjgyLDEyLjVIMTUuMTlhLjI'
    '3LjI3LDAsMCwxLC4yNi4yN3YxLjQxYS4yNy4yNywwLDAsMS0uMjYuMjdIMi44MmEuMjcuMjcsMCwwLDEtLjI2LS4yN1YxMi43N0E'
    'uMjcuMjcsMCwwLDEsMi44MiwxMi41WiIgZmlsbD0iIzI1ODI3NyIgLz48L3N2Zz4="],["application_gateway","data:ima'
    'ge/svg+xml;base64,PHN2ZyBpZD0iYWNhYzVhMzQtYTAzMi00OWY5LTkzOTctMzdmNGYxYjRhZTlhIiB4bWxucz0iaHR0cDovL3'
    'd3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIxOCIgaGVpZ2h0PSIxOCIgdmlld0JveD0iMCAwIDE4IDE4Ij48ZGVmcz48bGluZW'
    'FyR3JhZGllbnQgaWQ9ImY2ZDUzOTliLWE1Y2ItNGMwOS05NmNjLTllM2JiMWFmMjM4NiIgeDE9IjkiIHkxPSIxOS4yNSIgeDI9Ij'
    'kiIHkyPSItMC40NiIgZ3JhZGllbnRUcmFuc2Zvcm09InRyYW5zbGF0ZSg5IC0zLjczKSByb3RhdGUoNDUpIiBncmFkaWVudFVuaX'
    'RzPSJ1c2VyU3BhY2VPblVzZSI+PHN0b3Agb2Zmc2V0PSIwIiBzdG9wLWNvbG9yPSIjNWU5NjI0IiAvPjxzdG9wIG9mZnNldD0iMC'
    '41NSIgc3RvcC1jb2xvcj0iIzZkYWQyYSIgLz48c3RvcCBvZmZzZXQ9IjEiIHN0b3AtY29sb3I9IiM3NmJjMmQiIC8+PC9saW5lYX'
    'JHcmFkaWVudD48bGluZWFyR3JhZGllbnQgaWQ9ImE0MzI0MmEyLTRkOTUtNGY2ZC04ODcwLTI3MDJjZWI2YWViYyIgeDE9IjcuNT'
    'QiIHkxPSI2LjQ0IiB4Mj0iNy41MyIgeTI9IjUuMTgiIGdyYWRpZW50VW5pdHM9InVzZXJTcGFjZU9uVXNlIj48c3RvcCBvZmZzZX'
    'Q9IjAiIHN0b3AtY29sb3I9IiNjY2MiIC8+PHN0b3Agb2Zmc2V0PSIwLjEyIiBzdG9wLWNvbG9yPSIjZDdkN2Q3IiAvPjxzdG9wIG'
    '9mZnNldD0iMC40MiIgc3RvcC1jb2xvcj0iI2ViZWJlYiIgLz48c3RvcCBvZmZzZXQ9IjAuNzIiIHN0b3AtY29sb3I9IiNmOGY4Zj'
    'giIC8+PHN0b3Agb2Zmc2V0PSIxIiBzdG9wLWNvbG9yPSIjZmNmY2ZjIiAvPjwvbGluZWFyR3JhZGllbnQ+PGxpbmVhckdyYWRpZW'
    '50IGlkPSJlZWRjZTZkZC03MDZhLTQzYzQtYWM2Ni02NmI3MzU3ODIyMWQiIHgxPSI5LjM2IiB5MT0iNy42OSIgeDI9IjkuMzYiIH'
    'kyPSI2LjU3IiBocmVmPSIjYTQzMjQyYTItNGQ5NS00ZjZkLTg4NzAtMjcwMmNlYjZhZWJjIiAvPjwvZGVmcz48cmVjdCB4PSIyLj'
    'gyIiB5PSIyLjgyIiB3aWR0aD0iMTIuMzUiIGhlaWdodD0iMTIuMzUiIHJ4PSIwLjU3IiB0cmFuc2Zvcm09InRyYW5zbGF0ZSgtMy'
    '43MyA5KSByb3RhdGUoLTQ1KSIgZmlsbD0idXJsKCNmNmQ1Mzk5Yi1hNWNiLTRjMDktOTZjYy05ZTNiYjFhZjIzODYpIiAvPjxnPj'
    'xwYXRoIGQ9Ik0xMC44OSwxMC41MWgyLjg0YS4xMS4xMSwwLDAsMCwuMS0uMTFWNy41N2EuMS4xLDAsMCwwLS4xOC0uMDdsLS43OC'
    '43OCwwLC4wNWEuMS4xLDAsMCwxLS4xNCwwTDkuMjYsNC45MWEuMS4xLDAsMCwwLS4xNCwwbC0uODguODhhLjExLjExLDAsMCwwLD'
    'AsLjE1bDMuNDEsMy40MWEuMTEuMTEsMCwwLDEsMCwuMTVsLS4wNS4wNS0uNzguNzhBLjExLjExLDAsMCwwLDEwLjg5LDEwLjUxWi'
    'IgZmlsbD0iI2ZmZiIgLz48cGF0aCBkPSJNNi45MiwxMC41MUg0LjA4QS4xMS4xMSwwLDAsMSw0LDEwLjRWNy41N2EuMS4xLDAsMC'
    'wxLC4xNy0uMDdsLjc5Ljc4LDAsLjA1YS4xLjEsMCwwLDAsLjE0LDBMOC41NSw0LjkxYS4xLjEsMCwwLDEsLjE0LDBsLjg4Ljg4YS'
    '4xMS4xMSwwLDAsMSwwLC4xNUw2LjE2LDkuMzVhLjExLjExLDAsMCwwLDAsLjE1bDAsLjA1Ljc4Ljc4QS4xMS4xMSwwLDAsMSw2Lj'
    'kyLDEwLjUxWiIgZmlsbD0iI2ZmZiIgLz48cGF0aCBkPSJNNi44MiwxMy4wN2wyLDJhLjEuMSwwLDAsMCwuMTQsMGwyLTJhLjEuMS'
    'wwLDAsMC0uMDctLjE3SDkuNzJhLjExLjExLDAsMCwxLS4xLS4xVjhhLjEuMSwwLDAsMC0uMS0uMTFIOC4yOEEuMTEuMTEsMCwwLD'
    'AsOC4xNyw4VjEyLjhhLjEuMSwwLDAsMS0uMS4xSDYuODlBLjEuMSwwLDAsMCw2LjgyLDEzLjA3WiIgZmlsbD0iI2ZmZiIgLz48L2'
    'c+PHBhdGggaWQ9ImFjMGE5YzBjLTJlOGMtNDg0My1iMDJiLTJmYWRmNzZiMjdkMCIgZD0iTTEwLjY1LDcuNzhBMi43MSwyLjcxLD'
    'AsMCwxLDcuMzMsMy41bDAsMGEyLjcxLDIuNzEsMCwwLDEsMy4yOSw0LjMiIGZpbGw9IiMwMDc4ZDQiIC8+PGNpcmNsZSBjeD0iNy'
    '41MyIgY3k9IjUuNTUiIHI9IjAuODciIGZpbGw9InVybCgjYTQzMjQyYTItNGQ5NS00ZjZkLTg4NzAtMjcwMmNlYjZhZWJjKSIgLz'
    '48Zz48cGF0aCBkPSJNNi42Nyw3bC4xOS4zTDcsNy41YTUuOTQsNS45NCwwLDAsMSwuMzQtMS4xLjg1Ljg1LDAsMCwxLS40NS0uMj'
    'NBNi43MSw2LjcxLDAsMCwwLDYuNjcsN1oiIGZpbGw9IiNmMmYyZjIiIG9wYWNpdHk9IjAuNTUiIC8+PHBhdGggZD0iTTcuMjQsNC'
    '43M0E0LDQsMCwwLDEsNywzLjhhMi40OCwyLjQ4LDAsMCwwLS4zNC40NkEzLjUxLDMuNTEsMCwwLDAsNi44Niw1LDEsMSwwLDAsMS'
    'w3LjI0LDQuNzNaIiBmaWxsPSIjZjJmMmYyIiBvcGFjaXR5PSIwLjU1IiAvPjxwYXRoIGQ9Ik04LjE3LDYuMTRhLjg3Ljg3LDAsMC'
    'wxLS40OC4yNiw0LjYyLDQuNjIsMCwwLDAsLjQ2LjQxLDQuMTQsNC4xNCwwLDAsMCwuNjUuMzlWNy4xM0EuNTMuNTMsMCwwLDEsOS'
    'w2LjczLDMuNiwzLjYsMCwwLDEsOC4xNyw2LjE0WiIgZmlsbD0iI2YyZjJmMiIgb3BhY2l0eT0iMC41NSIgLz48cGF0aCBkPSJNMT'
    'AuNzksNy4yYTQuMTQsNC4xNCwwLDAsMS0uODctLjF2MGEuNTUuNTUsMCwwLDEtLjE2LjM5LDMuODQsMy44NCwwLDAsMCwxLjA4Lj'
    'A4LDIuOTMsMi45MywwLDAsMCwuMzctLjQyWiIgZmlsbD0iI2YyZjJmMiIgb3BhY2l0eT0iMC41NSIgLz48L2c+PGNpcmNsZSBjeD'
    '0iOS4zNiIgY3k9IjcuMTMiIHI9IjAuNTYiIGZpbGw9InVybCgjZWVkY2U2ZGQtNzA2YS00M2M0LWFjNjYtNjZiNzM1NzgyMjFkKS'
    'IgLz48Y2lyY2xlIGN4PSIxMC42NCIgY3k9IjUuNzQiIHI9IjAuNiIgZmlsbD0iI2YyZjJmMiIgLz48Zz48cGF0aCBkPSJNOS4yMS'
    'w0LjQyQTQuMjksNC4yOSwwLDAsMSwxMS4wOSw0YTIuMjQsMi4yNCwwLDAsMC0uNDctLjQ1LDQuNSw0LjUsMCwwLDAtMS40OS4zNW'
    'MtLjEsMC0uMTkuMTEtLjI5LjE2aDBhNS44NSw1Ljg1LDAsMCwxLS42My0uOTNsLS4zNC4xM2E1LjM1LDUuMzUsMCwwLDAsLjY1LD'
    'EsMy45MiwzLjkyLDAsMCwwLS42Ny41NS44Ny44NywwLDAsMSwuNDMuMzUsMy4yOSwzLjI5LDAsMCwxLC42MS0uNDgsOS4xNiw5Lj'
    'E2LDAsMCwwLDEuMTcsMSwuNTcuNTcsMCwwLDEsLjItLjMyQTguNDQsOC40NCwwLDAsMSw5LjIxLDQuNDJaIiBmaWxsPSIjZjJmMm'
    'YyIiBvcGFjaXR5PSIwLjU1IiAvPjxwYXRoIGQ9Ik0xMS41NSw2LjA5aDBsLS4xLDBoMGwtLjA4LDBoMGwtLjEtLjA2YS42MS42MS'
    'wwLDAsMS0uMi4zbC4xMi4wN2gwbC4xMS4wNmgwbC4yOC4xNGgwYTMuNTgsMy41OCwwLDAsMCwuMDktLjM1WiIgZmlsbD0iI2YyZj'
    'JmMiIgb3BhY2l0eT0iMC41NSIgLz48L2c+PGNpcmNsZSBjeD0iNy41MyIgY3k9IjUuNTUiIHI9IjAuODciIGZpbGw9IiNmMmYyZj'
    'IiIC8+PGNpcmNsZSBjeD0iOS4zNiIgY3k9IjcuMTMiIHI9IjAuNTYiIGZpbGw9IiNmMmYyZjIiIC8+PC9zdmc+"],["monitor",'
    '"data:image/svg+xml;base64,PHN2ZyBpZD0iZTRlNzY0Y2QtMmU3My00NzJmLWI4OGEtYmY4YmZjMmMyOTk0IiB4bWxucz0ia'
    'HR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIxOCIgaGVpZ2h0PSIxOCIgdmlld0JveD0iMCAwIDE4IDE4Ij48ZGVmc'
    'z48cmFkaWFsR3JhZGllbnQgaWQ9ImFjOGIzMmRhLTMwY2EtNGI5Mi04ZDBmLThkMmQ1ZWYyNzhhMCIgY3g9IjUuNzIiIGN5PSI3L'
    'jQ1IiByPSI4LjQyIiBncmFkaWVudFRyYW5zZm9ybT0idHJhbnNsYXRlKDMuMjMgMS41MSkgc2NhbGUoMS4wMSAxLjAxKSIgZ3JhZ'
    'GllbnRVbml0cz0idXNlclNwYWNlT25Vc2UiPjxzdG9wIG9mZnNldD0iMC4xOCIgc3RvcC1jb2xvcj0iIzVlYTBlZiIgLz48c3Rvc'
    'CBvZmZzZXQ9IjAuNTYiIHN0b3AtY29sb3I9IiM1YzlmZWUiIC8+PHN0b3Agb2Zmc2V0PSIwLjY5IiBzdG9wLWNvbG9yPSIjNTU5Y'
    '2VkIiAvPjxzdG9wIG9mZnNldD0iMC43OCIgc3RvcC1jb2xvcj0iIzRhOTdlOSIgLz48c3RvcCBvZmZzZXQ9IjAuODYiIHN0b3AtY'
    '29sb3I9IiMzOTkwZTQiIC8+PHN0b3Agb2Zmc2V0PSIwLjkzIiBzdG9wLWNvbG9yPSIjMjM4N2RlIiAvPjxzdG9wIG9mZnNldD0iM'
    'C45OSIgc3RvcC1jb2xvcj0iIzA4N2JkNiIgLz48c3RvcCBvZmZzZXQ9IjEiIHN0b3AtY29sb3I9IiMwMDc4ZDQiIC8+PC9yYWRpY'
    'WxHcmFkaWVudD48cmFkaWFsR3JhZGllbnQgaWQ9ImE5OTU0ODIwLWNiMzgtNDk0My05ODQyLWYwYTU2OGQyYjAxNSIgY3g9IjI4L'
    'jE4IiBjeT0iMjAyLjI5IiByPSIyLjciIGdyYWRpZW50VHJhbnNmb3JtPSJ0cmFuc2xhdGUoLTE3Ljc3IC0xODUuMDEpIHNjYWxlK'
    'DAuOTUpIiBncmFkaWVudFVuaXRzPSJ1c2VyU3BhY2VPblVzZSI+PHN0b3Agb2Zmc2V0PSIwLjE5IiBzdG9wLWNvbG9yPSIjOGM4Z'
    'TkwIiAvPjxzdG9wIG9mZnNldD0iMC4zNSIgc3RvcC1jb2xvcj0iIzg0ODY4OCIgLz48c3RvcCBvZmZzZXQ9IjAuNiIgc3RvcC1jb'
    '2xvcj0iIzZlNzA3MSIgLz48c3RvcCBvZmZzZXQ9IjAuOTEiIHN0b3AtY29sb3I9IiM0YTRiNGMiIC8+PHN0b3Agb2Zmc2V0PSIxI'
    'iBzdG9wLWNvbG9yPSIjM2UzZjNmIiAvPjwvcmFkaWFsR3JhZGllbnQ+PC9kZWZzPjx0aXRsZT5JY29uLW1hbmFnZS0zMTc8L3Rpd'
    'GxlPjxlbGxpcHNlIGN4PSI5IiBjeT0iOSIgcng9IjguNSIgcnk9IjguNDciIGZpbGw9InVybCgjYWM4YjMyZGEtMzBjYS00YjkyL'
    'ThkMGYtOGQyZDVlZjI3OGEwKSIgLz48ZWxsaXBzZSBjeD0iOSIgY3k9IjkiIHJ4PSI3LjQiIHJ5PSI3LjM3IiBmaWxsPSIjZmZmI'
    'iAvPjxwYXRoIGQ9Ik0yLjcyLDkuNDRhNi4yNCw2LjI0LDAsMCwwLDEuODIsNGwyLTJhMy41MywzLjUzLDAsMCwxLTEtMloiIGZpb'
    'Gw9IiM5Y2ViZmYiIC8+PHBhdGggZD0iTTEzLjEzLDQuMjdBNi4yNSw2LjI1LDAsMCwwLDkuNDQsMi43NFY1LjUzYTMuNDEsMy40M'
    'SwwLDAsMSwxLjcxLjdaIiBmaWxsPSIjMzJiZWRkIiAvPjxwYXRoIGQ9Ik00Ljg3LDQuMjdsMiwyYTMuNDEsMy40MSwwLDAsMSwxL'
    'jcxLS43VjIuNzRBNi4yNSw2LjI1LDAsMCwwLDQuODcsNC4yN1oiIGZpbGw9IiMzMmJlZGQiIC8+PHBhdGggZD0iTTExLjc4LDYuO'
    'DVhMy42LDMuNiwwLDAsMSwuNzEsMS43MWgyLjc5YTYuMTYsNi4xNiwwLDAsMC0xLjUzLTMuNjdaIiBmaWxsPSIjMzJiZWRkIiAvP'
    'jxwYXRoIGQ9Ik02LjIyLDYuODVsLTItMkE2LjE2LDYuMTYsMCwwLDAsMi43Miw4LjU2SDUuNTFBMy42LDMuNiwwLDAsMSw2LjIyL'
    'DYuODVaIiBmaWxsPSIjNTBlNmZmIiAvPjxwYXRoIGQ9Ik0xNC4xNCw3YS40NS40NSwwLDAsMC0uNTctLjI1TDkuNDUsOC40MWwuM'
    'zIuODEsNC4xMi0xLjYzQS40NC40NCwwLDAsMCwxNC4xNCw3WiIgZmlsbD0iI2YwNDA0OSIgLz48ZWxsaXBzZSBjeD0iOSIgY3k9I'
    'jkiIHJ4PSIxLjIiIHJ5PSIxLjIiIGZpbGw9InVybCgjYTk5NTQ4MjAtY2IzOC00OTQzLTk4NDItZjBhNTY4ZDJiMDE1KSIgLz48L'
    '3N2Zz4="]]);\n  /* OFFICIAL_AZURE_ICON_DATA_END */\n  const byId = id => document.getElementById(id);\n'
    '  const isObject = value => value !== null && typeof value === "object" && !Array.isArray(value);\n  '
    'const text = value => value === null || value === undefined || value === "" ? "Not evaluated" : (typ'
    'eof value === "object" ? JSON.stringify(value) : String(value));\n  const node = (tag, value, classNa'
    'me) => {\n    const result = document.createElement(tag);\n    if (value !== undefined) result.textCon'
    'tent = text(value);\n    if (className) result.className = className;\n    return result;\n  };\n  const'
    ' add = (parent, ...children) => { parent.append(...children); return parent; };\n  const svgNode = (t'
    'ag, attributes = {}, value) => {\n    const result = document.createElementNS("http://www.w3.org/2000'
    '/svg", tag);\n    for (const [key, item] of Object.entries(attributes)) result.setAttribute(key, Stri'
    'ng(item));\n    if (value !== undefined) result.textContent = String(value);\n    return result;\n  };\n'
    '  const empty = message => node("p", message, "empty");\n  const percentage = value => value === null'
    ' ? "Not evaluated" : `${value.toLocaleString("en-US", {maximumFractionDigits: 1})} / 100`;\n  const u'
    'tc = value => {\n    if (value === null || value === undefined || value === "") return "Not evaluated'
    '";\n    const date = new Date(value);\n    if (!Number.isFinite(date.getTime())) return `${text(value)'
    '} (date not normalized)`;\n    return `${new Intl.DateTimeFormat("en-GB", {year: "numeric", month: "s'
    'hort", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit", timeZone: "UTC"}).form'
    'at(date)} UTC`;\n  };\n  const sampleWindowText = value => `${utc(value.timestamp)} / observed duratio'
    'n: ${text(value.duration)}`;\n  const windowText = value => {\n    if (value === null || value === und'
    'efined) return "Not evaluated";\n    if (Array.isArray(value)) return value.length ? `Sample windows '
    '(${value.length}): ${value.map(sampleWindowText).join("; ")}` : "Not evaluated: no sample windows in'
    'cluded.";\n    if (Object.hasOwn(value, "start") || Object.hasOwn(value, "end")) return `${utc(value.'
    'start)} - ${utc(value.end)}`;\n    return `Sample window: ${sampleWindowText(value)}`;\n  };\n  const a'
    'ssert = (condition, message) => { if (!condition) throw new Error(message); };\n  const string = (val'
    'ue, path, nullable = false) => assert((nullable && (value === null || value === undefined)) || typeo'
    'f value === "string", `${path}: expected text.`);\n  const array = (value, path, nullable = false) =>'
    ' assert((nullable && value === null) || Array.isArray(value), `${path}: expected a collection.`);\n  '
    'const count = (value, path, nullable = false) => assert((nullable && (value === null || value === un'
    'defined)) || (Number.isSafeInteger(value) && value >= 0), `${path}: invalid count.`);\n  const object'
    ' = (value, path) => assert(isObject(value), `${path}: invalid structure.`);\n  const enumValue = (val'
    'ue, labels, path) => assert(labels.has(value), `${path}: unsupported value.`);\n  const armIdentity ='
    ' (value, path) => {\n    string(value, path);\n    const parts = value.split("/");\n    assert(value.le'
    'ngth <= 2048 && parts.length >= 9 && parts.length % 2 === 1 && parts[0] === "" &&\n      parts[1].toL'
    'owerCase() === "subscriptions" && /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(parts[2]) &&'
    '\n      parts[3].toLowerCase() === "resourcegroups" && parts[5].toLowerCase() === "providers" &&\n    '
    '  parts.slice(2).every(part => /^[A-Za-z0-9_.()-]+$/.test(part) && ![".", ".."].includes(part)), `${'
    'path}: invalid full ARM ID.`);\n    return value.toLowerCase();\n  };\n  const sampleWindow = (value, p'
    'ath) => {\n    object(value, path);\n    assert(Object.hasOwn(value, "timestamp") || Object.hasOwn(val'
    'ue, "duration"), `${path}: sample window fields are missing.`);\n    string(value.timestamp, `${path}'
    '.timestamp`, true); string(value.duration, `${path}.duration`, true);\n  };\n  const observedWindow = '
    '(value, path) => {\n    if (value === null || value === undefined) return;\n    if (Array.isArray(valu'
    'e)) {\n      for (const [index, item] of value.entries()) sampleWindow(item, `${path}[${index}]`);\n  '
    '    return;\n    }\n    object(value, path);\n    if (Object.hasOwn(value, "start") || Object.hasOwn(va'
    'lue, "end")) {\n      string(value.start, `${path}.start`, true); string(value.end, `${path}.end`, tr'
    'ue);\n    } else sampleWindow(value, path);\n  };\n  const recordIdentity = (row, path) => {\n    object'
    '(row, path);\n    for (const key of ["resource_id", "source_id", "observed_at", "cluster_name", "name'
    'space", "name", "title", "uid", "kind", "workload_name"]) string(row[key], `${path}.${key}`, true);\n'
    '  };\n  const canonical = value => JSON.stringify(value, (_key, item) => {\n    if (!isObject(item)) r'
    'eturn item;\n    const result = Object.create(null);\n    for (const key of Object.keys(item).sort()) '
    'result[key] = item[key];\n    return result;\n  });\n  const validateTree = root => {\n    const pending'
    ' = [[root, 0]];\n    while (pending.length) {\n      const [value, depth] = pending.pop();\n      asser'
    't(depth <= 40, "The model exceeds the supported nesting depth.");\n      if (value !== null && typeof'
    ' value === "object") {\n        for (const item of Object.values(value)) pending.push([item, depth + '
    '1]);\n      }\n    }\n  };\n  const validateScore = (score, path) => {\n    object(score, path);\n    for '
    '(const key of ["passed", "failed", "evaluated", "not_evaluated", "not_applicable", "total"]) count(s'
    'core[key], `${path}.${key}`);\n    assert(score.evaluated === score.passed + score.failed, `${path}: '
    'inconsistent evaluated count.`);\n    assert(score.total === score.evaluated + score.not_evaluated + '
    'score.not_applicable, `${path}: inconsistent total.`);\n    assert(score.evaluated === 0 ? score.scor'
    'e === null : (Number.isFinite(score.score) && score.score >= 0 && score.score <= 100), `${path}: mis'
    'sing or invalid index; with no evaluated checks it must be null.`);\n    const eligible = score.evalu'
    'ated + score.not_evaluated;\n    assert(eligible === 0 ? score.coverage_percent === null : (Number.is'
    'Finite(score.coverage_percent) && score.coverage_percent >= 0 && score.coverage_percent <= 100), `${'
    'path}: invalid coverage.`);\n  };\n  const validateScoreCounts = (score, checks, path) => {\n    const '
    'counts = new Map([...STATUS.keys()].map(key => [key, 0]));\n    for (const check of checks) counts.se'
    't(check.status, counts.get(check.status) + 1);\n    assert(score.total === checks.length && score.pas'
    'sed === counts.get("passed") && score.failed === counts.get("failed") &&\n      score.not_evaluated ='
    '== counts.get("not_evaluated") && score.not_applicable === counts.get("not_applicable"), `${path}: c'
    'ounts do not match the supplied records.`);\n  };\n  const validateCheck = (check, path, sources) => {'
    '\n    object(check, path);\n    for (const key of ["check_id", "title", "resource_id"]) { string(check'
    '[key], `${path}.${key}`); assert(check[key].length > 0, `${path}.${key}: empty value.`); }\n    for ('
    'const key of ["rule_id", "checklist_id", "namespace", "workload_name", "business_impact", "recommend'
    'ation", "learn_url", "checklist_url", "kubernetes_url", "reason"]) string(check[key], `${path}.${key'
    '}`, true);\n    if (check.kubernetes_ref !== null && check.kubernetes_ref !== undefined) {\n      obje'
    'ct(check.kubernetes_ref, `${path}.kubernetes_ref`);\n      for (const key of ["uid", "kind", "namespa'
    'ce", "name"]) string(check.kubernetes_ref[key], `${path}.kubernetes_ref.${key}`, true);\n    }\n    en'
    'umValue(check.status, STATUS, `${path}.status`); enumValue(check.level, LEVEL, `${path}.level`);\n   '
    ' enumValue(check.area, AREA, `${path}.area`); enumValue(check.pillar, PILLAR, `${path}.pillar`);\n   '
    ' enumValue(check.severity, SEVERITY, `${path}.severity`); enumValue(check.effort, EFFORT, `${path}.e'
    'ffort`);\n    array(check.evidence, `${path}.evidence`);\n    assert(check.status !== "failed" || chec'
    'k.evidence.length > 0, `${path}: a finding needs supplied evidence.`);\n    for (const [index, eviden'
    'ce] of check.evidence.entries()) {\n      object(evidence, `${path}.evidence[${index}]`);\n      strin'
    'g(evidence.source_id, `${path}.evidence.source_id`);\n      assert(sources.has(evidence.source_id), `'
    '${path}: evidence source not registered.`);\n      string(evidence.resource_id, `${path}.evidence.res'
    'ource_id`, true);\n      string(evidence.observed_at, `${path}.evidence.observed_at`, true);\n      as'
    'sert(Object.hasOwn(evidence, "value"), `${path}: the observed value is missing.`);\n    }\n  };\n  cons'
    't validate = model => {\n    object(model, "Report"); validateTree(model);\n    assert(model.schema_ve'
    'rsion === "1.0", "Unsupported schema version; 1.0 is required.");\n    assert(["LIVE", "SIMULATED"].i'
    'ncludes(model.provenance), "Invalid data provenance.");\n    assert(["LAB", "PRODUCTION", "UNSPECIFIE'
    'D"].includes(model.environment), "The environment must be declared.");\n    string(model.reference_ut'
    'c, "reference_utc");\n    assert(/^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(?:\\.\\d+)?Z$/.test(model.refere'
    'nce_utc) && Number.isFinite(Date.parse(model.reference_utc)), "The reference must be an RFC 3339 UTC'
    ' date.");\n    assert(new Date(model.reference_utc).toISOString().slice(0, 19) === model.reference_ut'
    'c.slice(0, 19), "The UTC reference contains a date or time that does not exist.");\n    object(model.'
    'client, "client"); string(model.client.name, "client.name");\n    assert(model.client.name.trim().len'
    'gth > 0, "The customer must be identified.");\n    string(model.client.logo_data_uri, "client.logo_da'
    'ta_uri", true); string(model.client.logo_alt, "client.logo_alt", true);\n    if (model.client.logo_da'
    'ta_uri) assert(model.client.logo_data_uri.length <= 1000000 && /^data:image\\/(?:png|jpeg);base64,[A-'
    'Za-z0-9+/]+={0,2}$/.test(model.client.logo_data_uri), "The logo must be a bounded inline PNG or JPEG'
    '.");\n    object(model.cluster, "cluster");\n    for (const key of ["id", "name"]) { string(model.clus'
    'ter[key], `cluster.${key}`); assert(model.cluster[key].length > 0, `cluster.${key}: empty value.`); '
    '}\n    const clusterIdentity = armIdentity(model.cluster.id, "cluster.id");\n    for (const key of ["s'
    'ubscription_id", "subscription_name", "resource_group", "region", "version", "power_state", "provisi'
    'oning_state", "sku_tier", "mode"]) string(model.cluster[key], `cluster.${key}`, true);\n    array(mod'
    'el.sources, "sources");\n    const sources = new Set();\n    for (const source of model.sources) {\n   '
    '   object(source, "source"); string(source.id, "source.id");\n      assert(source.id.length > 0 && !s'
    'ources.has(source.id), "Empty or duplicate source ID."); sources.add(source.id);\n      enumValue(sou'
    'rce.status, SOURCE_STATUS, "source.status"); string(source.time, "source.time", true);\n      count(s'
    'ource.records, "source.records", true); count(source.pages, "source.pages", true); array(source.erro'
    'rs, "source.errors");\n      string(source.note, "source.note", true); observedWindow(source.window, '
    '"source.window");\n      for (const error of source.errors) {\n        object(error, "source.error"); '
    'string(error.code, "source.error.code", true); string(error.message, "source.error.message", true);\n'
    '        count(error.http_status, "source.error.http_status", true);\n      }\n    }\n    object(model.i'
    'nventory, "inventory");\n    if (model.source_data !== undefined && model.source_data !== null) objec'
    't(model.source_data, "source_data");\n    for (const key of ["node_pools", "namespaces", "workloads",'
    ' "related_resources"]) assert(Object.hasOwn(model.inventory, key), `Missing inventory.${key}.`);\n   '
    ' for (const [key, rows] of Object.entries(model.inventory)) {\n      array(rows, `inventory.${key}`, '
    'true);\n      if (rows !== null) for (const row of rows) recordIdentity(row, `inventory.${key}.record'
    '`);\n    }\n    array(model.checks, "checks");\n    const checks = new Map();\n    for (const check of m'
    'odel.checks) {\n      validateCheck(check, "check", sources);\n      assert(!checks.has(check.check_id'
    '), "The model repeats a check_id; the overall index cannot be shown.");\n      checks.set(check.check'
    '_id, check);\n    }\n    array(model.findings, "findings");\n    const findings = new Set();\n    for (c'
    'onst finding of model.findings) {\n      const check = checks.get(finding.check_id);\n      assert(che'
    'ck && check.status === "failed" && !findings.has(finding.check_id) && canonical(check) === canonical'
    '(finding), "Findings must be exactly the failed checks, with no duplicates.");\n      findings.add(fi'
    'nding.check_id);\n    }\n    assert(findings.size === model.checks.filter(check => check.status === "f'
    'ailed").length, "Findings for failed checks are missing.");\n    object(model.scores, "scores"); vali'
    'dateScore(model.scores.global, "scores.global"); validateScore(model.scores.coverage, "scores.covera'
    'ge");\n    validateScoreCounts(model.scores.global, model.checks, "scores.global"); validateScoreCoun'
    'ts(model.scores.coverage, model.checks, "scores.coverage");\n    object(model.scores.areas, "scores.a'
    'reas"); object(model.scores.pillars, "scores.pillars");\n    for (const key of AREA.keys()) { validat'
    'eScore(model.scores.areas[key], `scores.areas.${key}`); validateScoreCounts(model.scores.areas[key],'
    ' model.checks.filter(check => check.area === key), `scores.areas.${key}`); }\n    for (const key of P'
    'ILLAR.keys()) { validateScore(model.scores.pillars[key], `scores.pillars.${key}`); validateScoreCoun'
    'ts(model.scores.pillars[key], model.checks.filter(check => check.pillar === key), `scores.pillars.${'
    'key}`); }\n    object(model.finops, "finops");\n    array(model.finops.sources, "finops.sources");\n   '
    ' for (const id of model.finops.sources) string(id, "finops.sources.record");\n    for (const key of ['
    '"candidates", "cost_rows", "metrics"]) {\n      array(model.finops[key], `finops.${key}`, true);\n    '
    '  if (model.finops[key] !== null) for (const row of model.finops[key]) recordIdentity(row, `finops.$'
    '{key}.record`);\n    }\n    array(model.finops.notes, "finops.notes");\n    for (const note of model.fi'
    'nops.notes) string(note, "finops.notes.record");\n    for (const key of ["actual_cost", "estimated_sa'
    'vings"]) assert(model.finops[key] === null || Number.isFinite(model.finops[key]), `finops.${key}: in'
    'valid amount.`);\n    string(model.finops.currency, "finops.currency", true);\n    observedWindow(mode'
    'l.finops.window, "finops.window");\n    for (const row of model.finops.candidates || []) {\n      stri'
    'ng(row.id, "finops.candidate.id"); string(row.title, "finops.candidate.title");\n      string(row.bas'
    'is, "finops.candidate.basis", true); string(row.unit, "finops.candidate.unit", true);\n      string(r'
    'ow.recommendation, "finops.candidate.recommendation", true); count(row.sample_count, "finops.candida'
    'te.sample_count", true);\n      observedWindow(row.window, "finops.candidate.window");\n      assert(r'
    'ow.estimated_savings === null || Number.isFinite(row.estimated_savings), "finops.candidate.estimated'
    '_savings: invalid amount.");\n    }\n    array(model.actions, "actions");\n    const actions = new Set('
    ');\n    for (const action of model.actions) {\n      object(action, "action"); string(action.action_id'
    ', "action.action_id"); string(action.check_id, "action.check_id");\n      assert(action.action_id.len'
    'gth > 0 && !actions.has(action.action_id) && checks.get(action.check_id)?.status === "failed", "An a'
    'ction needs a unique ID and must reference a supplied finding."); actions.add(action.action_id);\n   '
    '   for (const key of ["title", "resource_id", "namespace", "workload_name", "recommendation", "learn'
    '_url", "owner"]) string(action[key], `action.${key}`, true);\n      enumValue(action.planning_bucket,'
    ' BUCKET, "action.planning_bucket"); enumValue(action.effort, EFFORT, "action.effort");\n      enumVal'
    'ue(action.area, AREA, "action.area"); enumValue(action.pillar, PILLAR, "action.pillar"); enumValue(a'
    'ction.severity, SEVERITY, "action.severity");\n    }\n    array(model.executive_messages, "executive_m'
    'essages");\n    for (const message of model.executive_messages) string(message, "executive_messages.r'
    'ecord");\n    object(model.methodology, "methodology");\n    assert(model.methodology.score_kind === "'
    'local_assessment_indicator" && model.methodology.official_waf_score === false && model.methodology.r'
    'ead_only === true, "The method must declare an unofficial, read-only local index.");\n    array(model'
    '.methodology.limitations, "methodology.limitations");\n    for (const item of model.methodology.limit'
    'ations) string(item, "methodology.limitations.record");\n    if (model.methodology.queries !== undefi'
    'ned) array(model.methodology.queries, "methodology.queries", true);\n    if (model.methodology.source'
    '_pins !== undefined) array(model.methodology.source_pins, "methodology.source_pins", true);\n    for '
    '(const query of model.methodology.queries || []) {\n      object(query, "methodology.query");\n      f'
    'or (const key of ["source_id", "description", "command"]) string(query[key], `methodology.query.${ke'
    'y}`, true);\n    }\n    for (const pin of model.methodology.source_pins || []) object(pin, "methodolog'
    'y.source_pin");\n    if (model.architecture !== undefined && model.architecture !== null) {\n      con'
    'st graph = model.architecture; object(graph, "architecture");\n      for (const key of ["nodes", "edg'
    'es", "unknowns"]) array(graph[key], `architecture.${key}`);\n      const nodeIds = new Set(), edgeIds'
    ' = new Set();\n      const graphIdentity = (row, path) => {\n        object(row, path);\n        for (c'
    'onst key of ["cluster_id", "provenance", "observed_at"]) string(row[key], `${path}.${key}`);\n       '
    ' assert(armIdentity(row.cluster_id, `${path}.cluster_id`) === clusterIdentity && row.provenance === '
    'model.provenance, `${path}: the relationship does not belong to this cluster or provenance.`);\n     '
    ' };\n      for (const row of graph.nodes) {\n        graphIdentity(row, "architecture.node");\n        '
    'for (const key of ["id", "resource_id", "cluster_name", "kind", "label", "source_id"]) {\n          s'
    'tring(row[key], `architecture.node.${key}`); assert(row[key].length > 0, `architecture.node.${key}: '
    'empty value.`);\n        }\n        assert(row.cluster_name === model.cluster.name && sources.has(row.'
    'source_id) && !nodeIds.has(row.id), "architecture.node: duplicate identity, inconsistent cluster or '
    'unregistered source.");\n        assert(isObject(row.evidence) || Array.isArray(row.evidence), "archi'
    'tecture.node: structured evidence is missing.");\n        nodeIds.add(row.id);\n      }\n      for (con'
    'st row of graph.edges) {\n        graphIdentity(row, "architecture.edge");\n        for (const key of '
    '["id", "from", "to", "relation"]) { string(row[key], `architecture.edge.${key}`); assert(row[key].le'
    'ngth > 0, `architecture.edge.${key}: empty value.`); }\n        array(row.source_ids, "architecture.e'
    'dge.source_ids");\n        assert(row.source_ids.length > 0 && row.source_ids.every(id => sources.has'
    '(id)), "architecture.edge: unregistered source.");\n        assert(!edgeIds.has(row.id) && nodeIds.ha'
    's(row.from) && nodeIds.has(row.to), "architecture.edge: duplicate ID or endpoints without evidence."'
    ');\n        assert(isObject(row.evidence) || Array.isArray(row.evidence), "architecture.edge: join fi'
    'elds are missing.");\n        edgeIds.add(row.id);\n      }\n      for (const row of graph.unknowns) {\n'
    '        graphIdentity(row, "architecture.unknown");\n        for (const key of ["code", "kind", "mess'
    'age", "cluster_name"]) string(row[key], `architecture.unknown.${key}`);\n        string(row.resource_'
    'id, "architecture.unknown.resource_id", true);\n        array(row.source_ids, "architecture.unknown.s'
    'ource_ids");\n        assert(row.status === "not_evaluated" && row.cluster_name === model.cluster.nam'
    'e && row.source_ids.every(id => sources.has(id)), "architecture.unknown: invalid status, cluster or '
    'source.");\n      }\n    }\n    if (model.available_clusters !== undefined) validateRoster(model.availa'
    'ble_clusters);\n    if (model.selected_cluster_names !== undefined) {\n      array(model.selected_clus'
    'ter_names, "selected_cluster_names");\n      assert(model.selected_cluster_names.length === 1 && mode'
    'l.selected_cluster_names[0] === model.cluster.name, "selected_cluster_names: a single-cluster snapsh'
    'ot must identify its cluster.");\n    }\n    return model;\n  };\n  const validateRoster = roster => {\n '
    '   array(roster, "available_clusters");\n    assert(roster.length >= 1 && roster.length <= MAX_CLUSTE'
    'RS, `available_clusters: a roster of one to ${MAX_CLUSTERS} clusters is required.`);\n    const names'
    ' = new Set(), ids = new Set();\n    for (const row of roster) {\n      object(row, "available_clusters'
    '.record");\n      for (const key of ["cluster_id", "cluster_name", "resource_group"]) { string(row[ke'
    'y], `available_clusters.${key}`); assert(row[key].length > 0, `available_clusters.${key}: empty valu'
    'e.`); }\n      const identity = armIdentity(row.cluster_id, "available_clusters.cluster_id");\n      a'
    'ssert(["LAB", "PRODUCTION", "UNSPECIFIED"].includes(row.environment), "available_clusters: unsupport'
    'ed environment.");\n      assert(!names.has(row.cluster_name) && !ids.has(identity), "available_clust'
    'ers: duplicate identity.");\n      if (row.subscription_id !== undefined) {\n        string(row.subscr'
    'iption_id, "available_clusters.subscription_id");\n        assert(identity.split("/")[2] === row.subs'
    'cription_id.toLowerCase(), "available_clusters: the subscription does not match the cluster ID.");\n '
    '     }\n      for (const key of ["subscription_name", "location"]) string(row[key], `available_cluste'
    'rs.${key}`, true);\n      names.add(row.cluster_name); ids.add(identity);\n    }\n  };\n  const validate'
    'Document = documentModel => {\n    if (documentModel.schema_version === "1.0") return validate(docume'
    'ntModel);\n    object(documentModel, "Report"); validateTree(documentModel);\n    assert(documentModel'
    '.schema_version === "aks-waf-multi-cluster-v1", "Unsupported schema version.");\n    validateRoster(d'
    'ocumentModel.available_clusters);\n    string(documentModel.reference_utc, "reference_utc");\n    asse'
    'rt(/^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(?:\\.\\d+)?Z$/.test(documentModel.reference_utc) && Number.is'
    'Finite(Date.parse(documentModel.reference_utc)), "The combined reference must be an RFC 3339 UTC dat'
    'e.");\n    assert(new Date(documentModel.reference_utc).toISOString().slice(0, 19) === documentModel.'
    'reference_utc.slice(0, 19), "The combined reference contains a date that does not exist.");\n    asse'
    'rt(["LIVE", "SIMULATED"].includes(documentModel.provenance), "Invalid combined provenance.");\n    ob'
    'ject(documentModel.client, "client"); string(documentModel.client.name, "client.name");\n    assert(d'
    'ocumentModel.client.name.trim().length > 0, "The customer must be identified.");\n    array(documentM'
    'odel.selected_cluster_names, "selected_cluster_names"); array(documentModel.cluster_runs, "cluster_r'
    'uns");\n    const roster = new Map(documentModel.available_clusters.map(row => [row.cluster_name, row'
    ']));\n    const selected = new Set(documentModel.selected_cluster_names);\n    assert(selected.size >='
    ' 1 && selected.size <= MAX_CLUSTERS && selected.size === documentModel.selected_cluster_names.length'
    ' && [...selected].every(name => roster.has(name)), "The combined selection does not match the fixed '
    'roster.");\n    assert(documentModel.cluster_runs.length === selected.size, "Results for selected clu'
    'sters are missing.");\n    const seen = new Set();\n    for (const run of documentModel.cluster_runs) '
    '{\n      object(run, "cluster_run"); enumValue(run.status, RUN_STATUS, "cluster_run.status");\n      s'
    'tring(run.cluster_name, "cluster_run.cluster_name"); string(run.cluster_id, "cluster_run.cluster_id"'
    '); string(run.reference_utc, "cluster_run.reference_utc");\n      const identity = armIdentity(run.cl'
    'uster_id, "cluster_run.cluster_id");\n      assert(selected.has(run.cluster_name) && !seen.has(run.cl'
    'uster_name) &&\n        armIdentity(roster.get(run.cluster_name).cluster_id, "available_clusters.clus'
    'ter_id") === identity, "cluster_run: identity outside the selection or duplicated.");\n      seen.add'
    '(run.cluster_name);\n      if (run.snapshot === null) {\n        assert(run.status === "error" && isOb'
    'ject(run.error), "cluster_run: a result without a snapshot must keep its error.");\n      } else {\n  '
    '      if (isObject(run.snapshot) && run.snapshot.client === undefined) run.snapshot.client = documen'
    'tModel.client;\n        validate(run.snapshot);\n        assert(run.status !== "error" && armIdentity('
    'run.snapshot.cluster.id, "cluster.id") === identity && run.snapshot.cluster.name === run.cluster_nam'
    'e &&\n          run.snapshot.reference_utc === run.reference_utc && run.snapshot.provenance === docum'
    'entModel.provenance &&\n          canonical(run.snapshot.client) === canonical(documentModel.client),'
    ' "cluster_run: inconsistent snapshot, date or identity.");\n      }\n    }\n    object(documentModel.ag'
    'gregate, "aggregate"); object(documentModel.aggregate.scores, "aggregate.scores");\n    validateScore'
    '(documentModel.aggregate.scores.global, "aggregate.scores.global");\n    validateScore(documentModel.'
    'aggregate.scores.coverage, "aggregate.scores.coverage");\n    for (const [field, labels] of [["areas"'
    ', AREA], ["pillars", PILLAR]]) {\n      object(documentModel.aggregate.scores[field], `aggregate.scor'
    'es.${field}`);\n      for (const key of labels.keys()) validateScore(documentModel.aggregate.scores[f'
    'ield][key], `aggregate.scores.${field}.${key}`);\n    }\n    object(documentModel.aggregate.inventory_'
    'counts, "aggregate.inventory_counts");\n    for (const [key, value] of Object.entries(documentModel.a'
    'ggregate.inventory_counts)) count(value, `aggregate.inventory_counts.${key}`, true);\n    for (const '
    'key of ["findings_total", "critical_total"]) count(documentModel.aggregate[key], `aggregate.${key}`)'
    ';\n    object(documentModel.aggregate.cluster_status_counts, "aggregate.cluster_status_counts");\n    '
    'for (const status of RUN_STATUS.keys()) {\n      const expected = documentModel.cluster_runs.filter(r'
    'un => run.status === status).length;\n      if (Object.hasOwn(documentModel.aggregate.cluster_status_'
    'counts, status)) {\n        count(documentModel.aggregate.cluster_status_counts[status], `aggregate.c'
    'luster_status_counts.${status}`);\n        assert(documentModel.aggregate.cluster_status_counts[statu'
    's] === expected, "aggregate: inconsistent run counts.");\n      } else assert(expected === 0, "aggreg'
    'ate: a non-zero run count is missing.");\n    }\n    return documentModel;\n  };\n  const preferences = '
    '{storage: true};\n  const mediaTheme = window.matchMedia("(prefers-color-scheme: dark)");\n  const the'
    'meNote = message => { byId("theme-note").hidden = false; byId("theme-note").textContent = message; }'
    ';\n  const storageError = error => {\n    if (!(error instanceof DOMException) || !["SecurityError", "'
    'QuotaExceededError"].includes(error.name)) throw error;\n    preferences.storage = false;\n    themeNo'
    'te("This browser does not allow saving the theme. The choice applies only while this file is open.")'
    ';\n  };\n  let savedTheme = "auto";\n  try {\n    const saved = localStorage.getItem("aks-consulting-rep'
    'ort-theme");\n    if (saved !== null && ["auto", "light", "dark"].includes(saved)) savedTheme = saved'
    ';\n    else if (saved !== null) themeNote("The saved theme preference is not valid; the system theme '
    'is used.");\n  } catch (error) { storageError(error); }\n  byId("theme-mode").value = savedTheme;\n  co'
    'nst applyTheme = () => { document.documentElement.dataset.theme = byId("theme-mode").value === "auto'
    '" ? (mediaTheme.matches ? "dark" : "light") : byId("theme-mode").value; };\n  applyTheme();\n  byId("t'
    'heme-mode").addEventListener("change", () => {\n    applyTheme();\n    if (preferences.storage) {\n    '
    '  try { localStorage.setItem("aks-consulting-report-theme", byId("theme-mode").value); } catch (erro'
    'r) { storageError(error); }\n    }\n  });\n  mediaTheme.addEventListener("change", () => { if (byId("th'
    'eme-mode").value === "auto") applyTheme(); });\n  let model, documentModel, embeddedJson, clusterRuns'
    ';\n  try {\n    embeddedJson = await readEmbedded();\n    assert(new TextEncoder().encode(embeddedJson)'
    '.length <= MAX_BYTES, "The full JSON exceeds the 64,000,000-byte limit.");\n    documentModel = valid'
    'ateDocument(JSON.parse(embeddedJson));\n    clusterRuns = documentModel.schema_version === "1.0" ? [{'
    'cluster_id: documentModel.cluster.id, cluster_name: documentModel.cluster.name,\n      reference_utc:'
    ' documentModel.reference_utc, status: "ok", error: null, snapshot: documentModel}] : documentModel.c'
    'luster_runs;\n    model = clusterRuns[0].snapshot;\n  } catch (error) {\n    document.body.dataset.stat'
    'us = "error";\n    byId("opening-state").setAttribute("role", "alert");\n    byId("opening-message").t'
    'extContent = "The report could not be opened. No partial results are shown.";\n    byId("opening-deta'
    'il").textContent = `Invalid data: ${error.message}. Ask the generator for a new complete snapshot co'
    'mpatible with schema 1.0 or aks-waf-multi-cluster-v1.`;\n    return;\n  }\n  const sourceMap = new Map('
    ');\n  const checkMap = new Map();\n  const workloadMap = new Map();\n  const workloadResourceCounts = n'
    'ew Map();\n  const workloadIdentity = record => {\n    const reference = record.kubernetes_ref || reco'
    'rd;\n    return {resource_id: record.resource_id, namespace: record.namespace || reference.namespace,'
    ' name: record.workload_name || reference.name,\n      kind: reference.kind || record.kind, uid: refer'
    'ence.uid || record.uid};\n  };\n  const workloadKey = record => {\n    const identity = workloadIdentit'
    'y(record);\n    if (identity.uid) return JSON.stringify([identity.resource_id, identity.uid]);\n    if'
    ' (workloadResourceCounts.get(identity.resource_id) === 1) return identity.resource_id;\n    return JS'
    'ON.stringify([identity.resource_id, identity.namespace, identity.kind || "", identity.name]);\n  };\n '
    ' const matchesWorkload = (record, selected) => {\n    if (Object.hasOwn(record, "check_id") && (recor'
    'd.level !== "workload" || !record.workload_name)) return false;\n    const identity = workloadIdentit'
    'y(record), target = workloadIdentity(selected);\n    if (identity.resource_id !== target.resource_id '
    '|| identity.namespace !== target.namespace) return false;\n    if (identity.uid && target.uid) return'
    ' identity.uid === target.uid;\n    if (!identity.name || identity.name !== target.name) return false;'
    '\n    if (identity.kind && target.kind) return identity.kind === target.kind;\n    return [...workload'
    'Map.values()].filter(row => row.resource_id === target.resource_id && row.namespace === target.names'
    'pace && row.name === target.name).length <= 1;\n  };\n  const state = {pages: new Map(), print: false,'
    ' openDetails: new Map(), graphNode: "", graphKind: "", activeCluster: clusterRuns[0].cluster_name,\n '
    '   findingsOrder: "severity", filters: {search: "", area: "", namespace: "", workload: "", level: ""'
    ', status: "", severity: ""}};\n  const detail = (label, key, content) => {\n    const result = node("d'
    'etails", undefined, "receipt");\n    result.dataset.detailKey = key; add(result, node("summary", labe'
    'l), add(node("div", undefined, "receipt-content"), content));\n    return result;\n  };\n  const facts '
    '= entries => {\n    const result = node("dl", undefined, "facts");\n    for (const [label, value] of e'
    'ntries) add(result, node("dt", label), value instanceof Node ? add(node("dd"), value) : node("dd", t'
    'ext(value)));\n    return result;\n  };\n  const jsonText = value => JSON.stringify(value, null, state.'
    'print ? 0 : 2);\n  const rawReceipt = (row, key) => detail("Full evidence and identity", key, node("p'
    're", jsonText(row), "json"));\n  const severity = value => node("span", SEVERITY.get(value), `severit'
    'y ${value}`);\n  const SEVERITY_ORDER = [...SEVERITY.keys()];\n  const SEVERITY_WORDS = new Map([["cri'
    'tical", ["critical", "critical"]], ["high", ["high", "high"]], ["medium", ["medium", "medium"]], ["l'
    'ow", ["low", "low"]]]);\n  const severityRank = value => { const rank = SEVERITY_ORDER.indexOf(value)'
    '; return rank < 0 ? SEVERITY_ORDER.length : rank; };\n  const severityCounts = findings => new Map(SE'
    'VERITY_ORDER.map(key => [key, findings.filter(finding => finding.severity === key).length]));\n  cons'
    't plural = (number, one, many) => `${number.toLocaleString("en-US")} ${number === 1 ? one : many}`;\n'
    '  const percentText = value => value === null || value === undefined ? "Not evaluated" : `${value.to'
    'LocaleString("en-US", {maximumFractionDigits: 1})}%`;\n  const countText = rows => rows === null || r'
    'ows === undefined ? "Not evaluated" : rows.length.toLocaleString("en-US");\n  const listText = items '
    '=> items.length <= 1 ? items.join("") : `${items.slice(0, -1).join(", ")} and ${items[items.length -'
    ' 1]}`;\n  const listValue = value => Array.isArray(value) ? (value.length ? value.map(text).join(", "'
    ') : "None") : text(value);\n  const rich = (target, parts) => { for (const part of parts) target.appe'
    'nd(Array.isArray(part) ? node("b", part[0]) : document.createTextNode(part)); return target; };\n  co'
    'nst ARM_RESOURCE = /^\\/subscriptions\\/[0-9a-f-]{36}\\/resourcegroups\\/[^/?#\\s]+(?:\\/providers\\/[^?#\\s'
    ']+)?$/i;\n  const armId = value => {\n    const wrapper = node("span", undefined, "arm-id");\n    text('
    'value).split("/").forEach((part, index) => {\n      if (index) wrapper.append("/", document.createEle'
    'ment("wbr"));\n      if (part) wrapper.append(part);\n    });\n    return wrapper;\n  };\n  const portalL'
    'ink = value => {\n    if (typeof value !== "string" || !ARM_RESOURCE.test(value)) return null;\n    co'
    'nst link = permittedLink(`https://portal.azure.com/#@/resource${encodeURI(value)}`, "Azure Portal");'
    '\n    link.classList.add("portal-link");\n    return add(node("span", undefined, "no-print"), document'
    '.createTextNode(" · "), link);\n  };\n  const idWithPortal = value => {\n    const wrapper = add(node("'
    'span"), armId(value));\n    const link = portalLink(value); if (link) wrapper.append(link);\n    retur'
    'n wrapper;\n  };\n  const resourceRef = value => {\n    if (typeof value !== "string" || !ARM_RESOURCE.'
    'test(value)) return armId(value);\n    const segments = value.split("/").filter(Boolean);\n    const m'
    'eta = node("span", `Resource group ${segments[3]}`, "cell-note");\n    const link = portalLink(value)'
    '; if (link) meta.append(link);\n    return add(node("span", undefined, "resource-ref"), node("strong"'
    ', segments[segments.length - 1]), meta);\n  };\n  const subjectLabel = record => {\n    if (record.work'
    'load_name) return `${text(record.namespace)} / ${record.workload_name}`;\n    if (record.namespace) r'
    'eturn `namespace ${record.namespace}`;\n    return typeof record.resource_id === "string" && record.r'
    'esource_id ? record.resource_id.split("/").filter(Boolean).pop() : text(record.resource_id);\n  };\n  '
    'const containerSummary = containers => {\n    if (!Array.isArray(containers)) return text(containers)'
    ';\n    if (!containers.length) return "0 containers included";\n    const list = node("ul", undefined,'
    ' "container-list");\n    for (const item of containers) {\n      if (!isObject(item)) { list.append(no'
    'de("li", text(item))); continue; }\n      const entry = add(node("li"), node("strong", item.name), no'
    'de("span", item.image, "mono"));\n      const declared = [];\n      for (const [group, label] of [["re'
    'quests", "requests"], ["limits", "limits"]]) {\n        if (!isObject(item[group])) continue;\n       '
    ' const values = [["cpu", "CPU"], ["memory", "memory"]].filter(([key]) => item[group][key] !== null &'
    '& item[group][key] !== undefined && item[group][key] !== "")\n          .map(([key, name]) => `${name'
    '} ${text(item[group][key])}`);\n        if (values.length) declared.push(`${label}: ${values.join(", '
    '")}`);\n      }\n      const probeKeys = [["readiness_probe", "readiness"], ["liveness_probe", "livene'
    'ss"], ["startup_probe", "startup"]];\n      if (probeKeys.some(([key]) => typeof item[key] === "boole'
    'an")) {\n        const probes = probeKeys.filter(([key]) => item[key] === true).map(([, label]) => la'
    'bel);\n        declared.push(probes.length ? `probes: ${probes.join(", ")}` : "probes: none declared"'
    ');\n      }\n      if (isObject(item.security) && item.security.privileged === true) declared.push("pr'
    'ivileged");\n      if (declared.length) entry.append(node("span", declared.join(" · "), "cell-note"))'
    ';\n      list.append(entry);\n    }\n    return list;\n  };\n  const permittedLink = (value, label) => {\n'
    '    if (!value) return node("span", "Not evaluated");\n    let url;\n    try { url = new URL(value); }'
    ' catch (error) { if (!(error instanceof TypeError)) throw error; return node("span", `${text(value)}'
    ' (link not enabled)`); }\n    const allowed = url.protocol === "https:" && !url.username && !url.pass'
    'word && !url.port && (\n      (url.hostname === "learn.microsoft.com" && /^\\/(?:[a-z]{2}-[a-z]{2}\\/)?'
    '(?:azure|well-architected|security|troubleshoot)\\//i.test(url.pathname)) ||\n      (url.hostname === '
    '"portal.azure.com" && url.pathname === "/")\n    );\n    if (!allowed) return node("span", `${text(val'
    'ue)} (link not enabled)`, "source-url");\n    const link = node("a", label); link.href = url.href; li'
    'nk.target = "_blank"; link.rel = "noopener noreferrer"; return link;\n  };\n  const sourceIdentity = r'
    'ow => {\n    const source = sourceMap.get(row.source_id);\n    return `${text(row.source_id)} / ${sour'
    'ce ? SOURCE_STATUS.get(source.status) : "Not evaluated"} / ${utc(row.observed_at)}`;\n  };\n  const na'
    'medRecord = (row, collection) => {\n    const wrapper = node("div");\n    const name = text(row.name |'
    '| row.title || row.resource_id);\n    if ((collection === "namespaces" && row.name) || (collection =='
    '= "workloads" && row.name && row.resource_id)) {\n      const button = node("button", name, "text-but'
    'ton"); button.type = "button";\n      button.dataset.drilldown = collection; button.dataset.resourceI'
    'd = text(row.resource_id);\n      button.addEventListener("click", () => {\n        state.filters.name'
    'space = collection === "namespaces" ? (row.name || "") : (row.namespace || "");\n        state.filter'
    's.workload = collection === "workloads" ? workloadKey(row) : "";\n        byId("filter-namespace").va'
    'lue = state.filters.namespace; populateWorkloads(); byId("filter-workload").value = state.filters.wo'
    'rkload;\n        filtersChanged(false); byId("findings").scrollIntoView(); byId("findings-title").tab'
    'Index = -1; byId("findings-title").focus({preventScroll: true});\n      });\n      wrapper.append(butt'
    'on);\n    } else wrapper.append(node("strong", name));\n    add(wrapper, node("span", sourceIdentity(r'
    'ow), "cell-note"), rawReceipt(row, `inventory:${collection}:${text(row.resource_id)}:${name}`));\n   '
    ' return wrapper;\n  };\n  const scoreCaption = score => `${score.evaluated} evaluated; ${score.not_eva'
    'luated} not evaluated; ${score.not_applicable} not applicable.`;\n  const scoreRow = (label, score) ='
    '> {\n    const wrapper = node("div", undefined, "score-row");\n    const head = add(node("div", undefi'
    'ned, "score-row-head"), node("span", label), node("span", percentage(score.score), "score-number"));'
    '\n    const track = node("div", undefined, "score-track");\n    if (score.score !== null) {\n      trac'
    'k.setAttribute("role", "meter"); track.setAttribute("aria-label", `Local index: ${label}`);\n      tr'
    'ack.setAttribute("aria-valuemin", "0"); track.setAttribute("aria-valuemax", "100"); track.setAttribu'
    'te("aria-valuenow", String(score.score));\n      track.setAttribute("aria-valuetext", `${percentage(s'
    'core.score)}. ${scoreCaption(score)}`);\n      const fill = node("div", undefined, "score-fill"); fil'
    'l.style.width = `${score.score}%`; track.append(fill);\n    } else track.setAttribute("aria-hidden", '
    '"true");\n    add(wrapper, head, track, node("p", scoreCaption(score), "score-caption"));\n    return '
    'wrapper;\n  };\n  const money = value => value === null || value === undefined ? "Not evaluated" : `${'
    'value.toLocaleString("en-US", {maximumFractionDigits: 2})} ${model.finops.currency || "(currency not'
    ' reported)"}`;\n  const cssString = value => `"${String(value).replace(/[\\\\"]/g, "\\\\$&").replace(/[\\u'
    '0000-\\u001f\\u007f]/g, " ")}"`;\n  const kpi = (value, unit, label, note, unknown = false) => {\n    co'
    'nst valueNode = node("p", value, `kpi-value${unknown ? " unknown" : ""}`);\n    if (unit && !unknown)'
    ' valueNode.append(node("span", unit, "kpi-unit"));\n    return add(node("div", undefined, "kpi"), val'
    'ueNode, node("p", label, "kpi-label"), node("p", note, "kpi-note"));\n  };\n  const renderCover = () ='
    '> {\n    for (const id of ["brand-plaque", "provenance", "cover-facts", "cover-id", "hero-summary", "'
    'verdict", "severity-distribution", "kpis", "simulation-note"]) byId(id).replaceChildren();\n    byId('
    '"client-name").textContent = model.client.name;\n    const plaque = byId("brand-plaque");\n    if (mod'
    'el.client.logo_data_uri) {\n      const image = node("img"); image.src = model.client.logo_data_uri; '
    'image.alt = model.client.logo_alt || `${model.client.name} logo`;\n      plaque.append(image);\n    } '
    'else plaque.append(node("span", "CUSTOMER", "brand-placeholder"));\n    const score = model.scores.gl'
    'obal, coverage = model.scores.coverage, counts = severityCounts(model.findings);\n    const breakdown'
    ' = SEVERITY_ORDER.filter(key => counts.get(key)).map((key, index, keys) => `${counts.get(key)} ${SEV'
    'ERITY_WORDS.get(key)[0]}${index === keys.length - 1 ? " severity" : ""}`);\n    rich(byId("hero-summa'
    'ry"), score.evaluated ? [\n      [plural(model.findings.length, "finding", "findings")], " in ", [mod'
    'el.cluster.name], breakdown.length ? ` (${listText(breakdown)})` : "", " from ",\n      [plural(score'
    '.evaluated, "evaluated check", "evaluated checks")], "; coverage ", [percentText(coverage.coverage_p'
    'ercent)],\n      `, with ${plural(coverage.not_evaluated, "check", "checks")} not evaluated.`,\n      '
    'model.findings.length ? "" : " Having no findings does not prove there is no risk."\n    ] : [["No ch'
    'ecks evaluated"], " in ", [model.cluster.name], `: the local index stays Not evaluated and ${plural('
    'coverage.not_evaluated, "check remains", "checks remain")} not evaluated.`]);\n    const provenance ='
    ' model.provenance === "LIVE" ? "Observed data / snapshot" : "SIMULATED / test data, not live";\n    c'
    'onst environment = {LAB: "LAB / test environment", PRODUCTION: "Declared production environment", UN'
    'SPECIFIED: "Environment not specified"}[model.environment];\n    add(byId("provenance"), node("span",'
    ' `Reference ${utc(model.reference_utc)}`, "chip"), node("span", provenance, `chip${model.provenance '
    '=== "LIVE" ? "" : " strong"}`),\n      node("span", environment, "chip"), node("span", `${text(model.'
    'cluster.name)} · ${text(model.cluster.resource_group)}`, "chip"));\n    if (clusterRuns.length > 1) {'
    '\n      const position = clusterRuns.findIndex(run => run.cluster_name === state.activeCluster) + 1;\n'
    '      const link = node("a", `Cluster ${position} of ${clusterRuns.length} · change`, "chip no-print'
    '"); link.href = "#cluster-overview";\n      byId("provenance").append(link);\n    }\n    const [tone, v'
    'erdictText] = counts.get("critical") ? ["critical", "Action required"] : counts.get("high") ? ["high'
    '", "Needs attention"] :\n      model.findings.length ? ["medium", "Review recommended"] : score.evalu'
    'ated ? ["none", "No findings recorded"] : ["unknown", "Not evaluated"];\n    const verdict = byId("ve'
    'rdict"); verdict.className = `verdict tone-${tone}`;\n    const verdictLabel = node("p", "Verdict", "'
    'verdict-label"); verdictLabel.id = "verdict-label";\n    add(verdict, verdictLabel, node("p", verdict'
    'Text, "verdict-value"),\n      node("p", SEVERITY_ORDER.map(key => `${counts.get(key)} ${SEVERITY_WOR'
    'DS.get(key)[counts.get(key) === 1 ? 0 : 1]}`).join(" · "), "verdict-detail"),\n      node("p", !score'
    '.evaluated ? "No checks evaluated: review the sources before you conclude." : model.findings.length '
    '?\n        `Based on ${plural(score.evaluated, "evaluated check", "evaluated checks")} (coverage ${pe'
    'rcentText(coverage.coverage_percent)}). Not an official rating.` :\n        `This does not mean there'
    ' is no risk: coverage ${percentText(coverage.coverage_percent)}.`, "verdict-note"));\n    const distr'
    'ibution = byId("severity-distribution");\n    const track = node("div", undefined, "distribution-trac'
    'k"); track.setAttribute("aria-hidden", "true");\n    const legend = node("div", undefined, "distribut'
    'ion-legend");\n    for (const key of SEVERITY_ORDER) {\n      const number = counts.get(key);\n      if'
    ' (number) { const segment = node("div", undefined, `distribution-segment ${key}`); segment.style.wid'
    'th = `${number / model.findings.length * 100}%`; track.append(segment); }\n      const swatch = node('
    '"span", undefined, `legend-swatch ${key}`); swatch.setAttribute("aria-hidden", "true");\n      add(le'
    'gend, add(node("span", undefined, "legend-item"), swatch, document.createTextNode(`${SEVERITY.get(ke'
    'y)} `), node("b", number)));\n    }\n    add(distribution, add(node("p", undefined, "distribution-head'
    '"), rich(node("span"), ["Severity distribution · ", [plural(model.findings.length, "finding supplied'
    '", "findings supplied")]]),\n      node("span", "Checks not evaluated are shown neither as findings n'
    'or as healthy results.")), track, legend);\n    const inventory = model.inventory;\n    const counted '
    '= (rows, one, many) => rows === null || rows === undefined ? `${many}: Not evaluated` : `${countText'
    '(rows)} ${rows.length === 1 ? one : many}`;\n    add(byId("kpis"),\n      score.evaluated ? kpi(model.'
    'findings.length.toLocaleString("en-US"), "", "Findings recorded", SEVERITY_ORDER.slice(0, 2).map(key'
    ' => `${SEVERITY.get(key)} ${counts.get(key)}`).join(" · ")) :\n        kpi("Not evaluated", "", "Find'
    'ings recorded", `${model.findings.length} supplied: no checks evaluated`, true),\n      score.score ='
    '== null ? kpi("Not evaluated", "", "Overall local index", "No checks evaluated", true) :\n        kpi'
    '(score.score.toLocaleString("en-US", {maximumFractionDigits: 1}), "/ 100", "Overall local index", `$'
    '{score.passed} of ${score.evaluated} evaluated passed · unofficial`),\n      coverage.coverage_percen'
    't === null ? kpi("Not evaluated", "", "Assessment coverage", "No applicable checks to evaluate", tru'
    'e) :\n        kpi(coverage.coverage_percent.toLocaleString("en-US", {maximumFractionDigits: 1}), "%",'
    ' "Assessment coverage", `${coverage.not_evaluated} not evaluated · ${coverage.not_applicable} not ap'
    'plicable`),\n      model.finops.actual_cost === null || model.finops.actual_cost === undefined ?\n    '
    '    kpi("Not evaluated", "", "Observed cost", "No complete observed amount; see FinOps", true) :\n   '
    '     kpi(model.finops.actual_cost.toLocaleString("en-US", {maximumFractionDigits: 2}), model.finops.'
    'currency || "(currency not reported)", "Observed cost",\n          model.finops.estimated_savings ==='
    ' null ? "Savings: to be estimated" : `Estimated savings supplied: ${money(model.finops.estimated_sav'
    'ings)}`),\n      inventory.workloads === null || inventory.workloads === undefined ?\n        kpi("Not'
    ' evaluated", "", "Observed workloads", `${counted(inventory.namespaces, "namespace", "namespaces")} '
    '· ${counted(inventory.node_pools, "pool", "pools")}`, true) :\n        kpi(countText(inventory.worklo'
    'ads), "", "Observed workloads", `${counted(inventory.namespaces, "namespace", "namespaces")} · ${cou'
    'nted(inventory.node_pools, "pool", "pools")} · ${counted(inventory.related_resources, "associated re'
    'source", "associated resources")}`));\n    const simulation = byId("simulation-note"); simulation.hid'
    'den = model.provenance === "LIVE";\n    add(simulation, node("strong", "Simulated data."), document.c'
    'reateTextNode(" Nothing was read from Azure: the figures are not observations of a customer or a rea'
    'l cluster."));\n    const entries = [\n      ["Cluster", model.cluster.name], ["Subscription", model.c'
    'luster.subscription_name || model.cluster.subscription_id],\n      ["Resource group", model.cluster.r'
    'esource_group], ["Region", model.cluster.region], ["AKS version", model.cluster.version],\n      ["UT'
    'C reference", utc(model.reference_utc)], ["Cluster power state", model.cluster.power_state],\n      ['
    '"Cluster provisioning", model.cluster.provisioning_state], ["SKU / mode", `${text(model.cluster.sku_'
    'tier)} / ${text(model.cluster.mode)}`]\n    ];\n    for (const [label, value] of entries) {\n      cons'
    't wrapper = add(node("div"), node("dt", label), node("dd", value));\n      if (label === "UTC referen'
    'ce") wrapper.className = "reference-fact";\n      if (label === "Subscription") wrapper.className = "'
    'wide-fact";\n      byId("cover-facts").append(wrapper);\n    }\n    add(byId("cover-id"), add(node("p")'
    ', document.createTextNode("Cluster ID: "), idWithPortal(model.cluster.id)),\n      add(node("p"), doc'
    'ument.createTextNode("Subscription ID: "), armId(model.cluster.subscription_id)));\n    byId("cover-i'
    'd").append(detail("Full cluster scope and identity", "cluster-identity", node("pre", jsonText(model.'
    'cluster), "json")));\n    byId("footer-reference").textContent = `${model.client.name} / ${model.clus'
    'ter.name} / ${environment} / ${provenance} / ${utc(model.reference_utc)} / schema ${model.schema_ver'
    'sion}.`;\n    document.documentElement.style.setProperty("--print-footer", cssString(`AKS architectur'
    'e and configuration review · ${model.cluster.name} · ${utc(model.reference_utc)}`));\n  };\n  const re'
    'nderExecutive = () => {\n    for (const id of ["global-index", "area-scores", "pillar-scores", "globa'
    'l-coverage", "critical-findings", "next-actions", "executive-messages", "assessment-chart"]) byId(id'
    ').replaceChildren();\n    const score = model.scores.global;\n    add(byId("global-index"), node("h3",'
    ' "Overall local index"), node("span", percentage(score.score), `score-value${score.score === null ? '
    '" unknown" : ""}`),\n      node("p", scoreCaption(score)), node("p", `${score.passed} passed / ${scor'
    'e.failed} failed.`, "muted"),\n      node("p", "Full scope. Not an official rating.", "qualification"'
    '));\n    for (const [key, label] of AREA) byId("area-scores").append(scoreRow(label, model.scores.are'
    'as[key]));\n    for (const [key, label] of PILLAR) byId("pillar-scores").append(scoreRow(label, model'
    '.scores.pillars[key]));\n    const coverage = model.scores.coverage;\n    add(byId("global-coverage"),'
    ' add(node("p"), document.createTextNode("Coverage received: "),\n      node("strong", coverage.covera'
    'ge_percent === null ? "Not evaluated" : `${coverage.coverage_percent.toLocaleString("en-US", {maximu'
    'mFractionDigits: 1})}%`, "coverage-number"),\n      document.createTextNode(`. ${scoreCaption(coverag'
    'e)}`)),\n      node("p", `${plural(coverage.total, "unique check", "unique checks")} included. ${plur'
    'al(model.sources.length, "source", "sources")} recorded; check their status and limits.`, "muted"));'
    '\n    const chart = byId("assessment-chart");\n    const segments = [["passed", "Passed", score.passed'
    ', "var(--accent)", "Evaluated with no local finding"],\n      ["failed", "Failed", score.failed, "var'
    '(--high-bar)", "Evaluated with evidence of a failure"],\n      ["not_evaluated", "Not evaluated", sco'
    're.not_evaluated, "var(--field-line)", "Configuration or intent unknown"],\n      ["not_applicable", '
    '"Not applicable", score.not_applicable, "var(--surface)", "Outside the denominators"]];\n    const he'
    'ading = node("h3", "What could be evaluated"); heading.id = "assessment-chart-title";\n    const head'
    ' = add(node("div", undefined, "chart-head"), heading,\n      add(node("p", undefined, "chart-total-li'
    'ne"), node("span", score.total, "chart-total"), node("span", "checks", "chart-unit")));\n    const dr'
    'awing = svgNode("svg", {viewBox: "0 0 1000 14", preserveAspectRatio: "none", role: "img", class: "st'
    'atus-bar", "aria-labelledby": "assessment-svg-title assessment-svg-description"});\n    add(drawing, '
    'svgNode("title", {id: "assessment-svg-title"}, "Check count by status; not a health chart"),\n      s'
    'vgNode("desc", {id: "assessment-svg-description"}, `${score.passed} passed; ${score.failed} failed; '
    '${score.not_evaluated} not evaluated; ${score.not_applicable} not applicable. ${score.total} in tota'
    'l.`));\n    let offset = 0;\n    for (const [key, , number, color] of segments) {\n      if (!score.tot'
    'al || !number) continue;\n      const width = number / score.total * 1000;\n      drawing.append(svgNo'
    'de("rect", {x: offset, y: 0, width, height: 14, fill: color, class: key,\n        ...(key === "not_ap'
    'plicable" ? {stroke: "var(--field-line)", "vector-effect": "non-scaling-stroke"} : {})}));\n      off'
    'set += width;\n    }\n    const table = node("table"); table.append(node("caption", "Chart data: full '
    'scope of this cluster"));\n    const header = node("tr");\n    for (const label of ["Status", "Count",'
    ' "Meaning"]) { const cell = node("th", label); cell.scope = "col"; header.append(cell); }\n    const '
    'body = node("tbody");\n    for (const [key, label, number, , meaning] of segments) {\n      const swat'
    'ch = node("span", undefined, `status-swatch ${key}`); swatch.setAttribute("aria-hidden", "true");\n  '
    '    const status = add(node("th"), swatch, document.createTextNode(label)); status.scope = "row";\n  '
    '    body.append(add(node("tr"), status, node("td", number), node("td", meaning)));\n    }\n    add(tab'
    'le, add(node("thead"), header), body);\n    add(chart, head, drawing, table, node("figcaption", "The '
    'local index describes evaluated checks only; coverage shows how much is still unknown. Not evaluated'
    ' is not a passed result, and Not applicable does not improve coverage."));\n    const sourceLink = no'
    'de("a", "See the source register"); sourceLink.href = "#sources-title"; byId("global-coverage").appe'
    'nd(sourceLink);\n    const critical = model.findings.filter(finding => finding.severity === "critical'
    '");\n    byId("critical-title").textContent = `Critical priorities / ${critical.length} recorded`;\n  '
    '  if (!critical.length) byId("critical-findings").append(empty("0 critical findings recorded. This d'
    'oes not mean there is no risk; review the coverage and the sources not evaluated."));\n    else {\n   '
    '   const list = node("ol", undefined, "priority-list");\n      for (const finding of critical.slice(0'
    ', 5)) {\n        const item = node("li");\n        add(item, node("strong", `${finding.check_id} / ${f'
    'inding.title}`), node("p", `${LEVEL.get(finding.level)} · ${subjectLabel(finding)}`, "muted"),\n     '
    '     node("p", finding.business_impact), node("p", finding.recommendation));\n        list.append(ite'
    'm);\n      }\n      add(byId("critical-findings"), list, node("p", `Showing ${Math.min(5, critical.len'
    'gth)} of ${critical.length}. The full list is in Findings.`, "qualification"));\n    }\n    const buck'
    'ets = [...BUCKET.keys()];\n    const planned = [...model.actions].sort((left, right) => ((buckets.ind'
    'exOf(left.planning_bucket) + 4) % 4 - (buckets.indexOf(right.planning_bucket) + 4) % 4) ||\n      (se'
    'verityRank(left.severity) - severityRank(right.severity)));\n    if (!planned.length) byId("next-acti'
    'ons").append(empty("The engine supplied no actions to review. This does not mean there is no risk.")'
    ');\n    else {\n      const list = node("ol", undefined, "next-actions");\n      for (const action of p'
    'lanned.slice(0, 5)) {\n        const horizon = (BUCKET.get(action.planning_bucket) || [text(action.pl'
    'anning_bucket)])[0].split(" / ")[0];\n        add(list, add(node("li"), severity(action.severity), no'
    'de("strong", action.title),\n          node("span", `${horizon} · ${subjectLabel(action)} · ${(EFFORT'
    '.get(action.effort) || "not evaluated").toLocaleLowerCase("en-US")} effort`, "cell-note")));\n      }'
    '\n      const link = node("a", `See the full plan (${plural(model.actions.length, "action", "actions"'
    ')})`, "card-link"); link.href = "#actions";\n      add(byId("next-actions"), list, link);\n    }\n    i'
    'f (!model.executive_messages.length) byId("executive-messages").append(node("li", "Not evaluated: th'
    'e engine included no executive messages."));\n    for (const message of model.executive_messages) byI'
    'd("executive-messages").append(node("li", message));\n  };\n  const fillOptions = (select, labels) => '
    '{ for (const [value, label] of labels) { const option = node("option", label); option.value = value;'
    ' select.append(option); } };\n  const namespaces = new Set();\n  const populateWorkloads = () => {\n   '
    ' const select = byId("filter-workload"); select.replaceChildren(node("option", "All workloads")); se'
    'lect.firstChild.value = "";\n    const rows = [...workloadMap.entries()].filter(([, row]) => !state.f'
    'ilters.namespace || row.namespace === state.filters.namespace);\n    rows.sort(([, left], [, right]) '
    '=> `${left.namespace}/${left.name}/${text(left.kind)}`.localeCompare(`${right.namespace}/${right.nam'
    'e}/${text(right.kind)}`, "en"));\n    for (const [key, row] of rows) { const option = node("option", '
    '`${text(row.namespace)} / ${text(row.name)}${row.kind ? ` / ${row.kind}` : ""}`); option.value = key'
    '; select.append(option); }\n    if (!rows.some(([key]) => key === state.filters.workload)) state.filt'
    'ers.workload = "";\n    select.value = state.filters.workload;\n  };\n  fillOptions(byId("filter-area")'
    ', AREA); fillOptions(byId("filter-level"), LEVEL); fillOptions(byId("filter-status"), STATUS); fillO'
    'ptions(byId("filter-severity"), SEVERITY);\n  const containsSearch = value => !state.filters.search |'
    '| JSON.stringify(value).toLocaleLowerCase("en-US").includes(state.filters.search.toLocaleLowerCase("'
    'en-US"));\n  const matchedChecks = () => model.checks.filter(check => {\n    const f = state.filters;\n'
    '    return (!f.area || check.area === f.area) && (!f.namespace || check.namespace === f.namespace) &'
    '&\n      (!f.workload || matchesWorkload(check, workloadMap.get(f.workload))) && (!f.level || check.l'
    'evel === f.level) &&\n      (!f.status || check.status === f.status) && (!f.severity || (check.status'
    ' === "failed" && check.severity === f.severity)) && containsSearch(check);\n  });\n  const currentScop'
    'e = () => {\n    const checks = matchedChecks();\n    const ids = new Set(checks.map(check => check.re'
    'source_id));\n    const checkIds = new Set(checks.map(check => check.check_id));\n    const namespaceI'
    'ds = new Set(checks.map(check => check.namespace).filter(Boolean));\n    const selectedWorkload = wor'
    'kloadMap.get(state.filters.workload);\n    const filterRecord = (row, collection) => {\n      const f '
    '= state.filters;\n      const namespace = collection === "namespaces" ? row.name : row.namespace;\n   '
    '   const namespaceScoped = Boolean(namespace);\n      const idMatch = collection === "namespaces" ? n'
    'amespaceIds.has(namespace) : namespaceScoped ? checks.some(check => matchesWorkload(check, row)) : i'
    'ds.has(row.resource_id);\n      if (f.namespace && namespace !== f.namespace && (namespaceScoped || !'
    'idMatch)) return false;\n      if (f.workload) {\n        if (collection === "namespaces") { if (names'
    'pace !== selectedWorkload.namespace) return false; }\n        else if (namespaceScoped || collection '
    '=== "workloads") { if (!matchesWorkload(row, selectedWorkload)) return false; }\n        else if (!id'
    'Match) return false;\n      }\n      if ((f.area || f.level || f.status || f.severity) && !idMatch && '
    '!(collection === "namespaces" && namespaceIds.has(namespace))) return false;\n      return containsSe'
    'arch(row) || idMatch || (collection === "namespaces" && namespaceIds.has(namespace));\n    };\n    con'
    'st inventory = Object.create(null);\n    for (const [key, rows] of Object.entries(model.inventory)) i'
    'nventory[key] = rows === null ? null : rows.filter(row => filterRecord(row, key));\n    const finding'
    's = model.findings.filter(finding => checkIds.has(finding.check_id));\n    const candidates = model.f'
    'inops.candidates === null ? null : model.finops.candidates.filter(row => (!state.filters.area || sta'
    'te.filters.area === "finops") && filterRecord(row, "finops.candidates"));\n    const actions = model.'
    'actions.filter(action => checkIds.has(action.check_id));\n    return {checks, findings, inventory, ca'
    'ndidates, actions, filterRecord};\n  };\n  const showLimit = key => state.print ? Infinity : (state.pa'
    'ges.get(key) || PAGE_SIZE);\n  const pagination = (container, key, total, shown, rerender) => {\n    c'
    'onst footer = node("div", undefined, "table-footer");\n    footer.append(node("span", `${shown} of ${'
    'plural(total, "matching record", "matching records")}. The export includes all matches.`));\n    cons'
    't button = node("button", shown < total ? `Show ${Math.min(PAGE_SIZE, total - shown)} more` : "All r'
    'ecords shown");\n    button.type = "button"; button.disabled = shown >= total; button.dataset.moreCol'
    'lection = key;\n    button.addEventListener("click", () => {\n      state.pages.set(key, showLimit(key'
    ') + PAGE_SIZE); rerender();\n      for (const next of document.querySelectorAll("button[data-more-col'
    'lection]")) if (next.dataset.moreCollection === key) { next.focus({preventScroll: true}); break; }\n '
    '   });\n    add(footer, button); container.append(footer);\n  };\n  const updateCue = element => {\n    '
    'const hidden = element.scrollLeft > 1, remaining = element.scrollWidth - element.clientWidth - eleme'
    'nt.scrollLeft > 1;\n    if (hidden || remaining) element.dataset.overflow = hidden && remaining ? "bo'
    'th" : hidden ? "left" : "right";\n    else delete element.dataset.overflow;\n  };\n  let cueFrame = 0;\n'
    '  const refreshCues = () => {\n    cancelAnimationFrame(cueFrame);\n    cueFrame = requestAnimationFra'
    'me(() => { for (const element of document.querySelectorAll(".table-scroll")) updateCue(element); });'
    '\n  };\n  document.addEventListener("scroll", event => { if (event.target instanceof Element && event.'
    'target.classList.contains("table-scroll")) updateCue(event.target); }, true);\n  document.addEventLis'
    'tener("toggle", refreshCues, true);\n  window.addEventListener("resize", refreshCues);\n  const render'
    'Table = (container, key, label, columns, rows, rerender) => {\n    container.replaceChildren();\n    r'
    'efreshCues();\n    if (rows === null) { container.append(empty(`Not evaluated: the ${label.toLocaleLo'
    'werCase("en-US")} collection was not included. See the source register.`)); return; }\n    if (!rows.'
    'length) { container.append(empty(`0 matching records in ${label.toLocaleLowerCase("en-US")}. An inve'
    'ntory with no records included does not prove that there are no resources or no risk.`)); return; }\n'
    '    const wrapper = node("div", undefined, "table-scroll"); wrapper.tabIndex = 0; wrapper.setAttribu'
    'te("role", "region"); wrapper.setAttribute("aria-label", `${label}: scrollable table`);\n    const ta'
    'ble = node("table", undefined, "wide-table"); table.dataset.collection = key;\n    table.append(node('
    '"caption", `${label} / ${plural(rows.length, "matching record", "matching records")}. Identity, sour'
    'ce and date are in the expandable evidence.`));\n    const header = node("tr");\n    for (const [title'
    '] of columns) { const cell = node("th", title); cell.scope = "col"; header.append(cell); }\n    table'
    '.append(add(node("thead"), header));\n    const body = node("tbody"); const visible = rows.slice(0, s'
    'howLimit(key));\n    for (const row of visible) {\n      const tr = node("tr");\n      for (const [, re'
    'ad] of columns) {\n        const value = read(row); const cell = node("td");\n        if (value instan'
    'ceof Node) cell.append(value); else cell.textContent = text(value);\n        tr.append(cell);\n      }'
    '\n      body.append(tr);\n    }\n    add(table, body); add(wrapper, table); container.append(wrapper);\n'
    '    if (state.print) {\n      // Print full-width receipts after the table instead of squeezing them '
    'into a narrow column.\n      const appendix = node("div", undefined, "print-receipts");\n      for (co'
    'nst tr of body.rows) {\n        const label = (tr.cells[0]?.querySelector("strong, button") || tr.cel'
    'ls[0])?.textContent.trim() || "";\n        for (const receipt of tr.querySelectorAll("details.receipt'
    '")) {\n          const summary = receipt.querySelector(":scope > summary");\n          if (summary && '
    'label) summary.textContent = `${summary.textContent} · ${label}`;\n          appendix.append(receipt)'
    ';\n        }\n      }\n      if (appendix.childElementCount) container.append(appendix);\n    }\n    pagi'
    'nation(container, key, rows.length, visible.length, rerender);\n  };\n  const renderInventory = scope '
    '=> {\n    byId("inventory-counts").replaceChildren();\n    const singular = {node_pools: "node pool", '
    'namespaces: "namespace", workloads: "workload", related_resources: "associated resource"};\n    for ('
    'const key of ["node_pools", "namespaces", "workloads", "related_resources"]) {\n      const rows = sc'
    'ope.inventory[key]; const item = node("span");\n      add(item, node("b", rows === null ? "Not evalua'
    'ted" : rows.length), document.createTextNode(` ${rows !== null && rows.length === 1 ? singular[key] '
    ': COLLECTION.get(key).toLocaleLowerCase("en-US")}`)); byId("inventory-counts").append(item);\n    }\n '
    '   renderTable(byId("node-pools"), "node_pools", "Node pools", [\n      ["Pool / evidence", row => na'
    'medRecord(row, "node_pools")], ["Mode / size", row => `${text(row.mode)} / ${text(row.vm_size)}`],\n '
    '     ["Nodes / autoscaling", row => `${text(row.count)} / ${row.enable_auto_scaling === true ? "On" '
    ': row.enable_auto_scaling === false ? "Off" : "Not evaluated"} (${text(row.min_count)} - ${text(row.'
    'max_count)})`],\n      ["Zones / version", row => `${listValue(row.availability_zones)} / ${text(row.'
    'version)}`], ["Pool provisioning", row => row.provisioning_state]\n    ], scope.inventory.node_pools,'
    ' renderFiltered);\n    renderTable(byId("namespaces"), "namespaces", "Namespaces", [\n      ["Namespac'
    'e / explore", row => namedRecord(row, "namespaces")], ["Observed status", row => row.phase ?? row.st'
    'atus],\n      ["ARM resource", row => resourceRef(row.resource_id)]\n    ], scope.inventory.namespaces'
    ', renderFiltered);\n    renderTable(byId("workloads"), "workloads", "Workloads", [\n      ["Workload /'
    ' explore", row => namedRecord(row, "workloads")], ["Namespace / kind", row => `${text(row.namespace)'
    '} / ${text(row.kind)}`],\n      ["Ready / desired replicas", row => `${text(row.ready_replicas)} / ${'
    'text(row.desired_replicas)}`],\n      ["Observed containers", row => row.containers === null || row.c'
    'ontainers === undefined ? "Not evaluated" : containerSummary(row.containers)]\n    ], scope.inventory'
    '.workloads, renderFiltered);\n    renderTable(byId("related-resources"), "related_resources", "Associ'
    'ated resources", [\n      ["Resource / evidence", row => namedRecord(row, "related_resources")], ["Ty'
    'pe", row => row.type ?? row.resource_type ?? row.kind],\n      ["Group / region", row => `${text(row.'
    'resource_group)} / ${text(row.region)}`], ["Resource ID", row => idWithPortal(row.resource_id)]\n    '
    '], scope.inventory.related_resources, renderFiltered);\n    const additional = byId("technical-collec'
    'tions"); additional.replaceChildren();\n    for (const [key, rows] of Object.entries(scope.inventory)'
    ') {\n      if (["node_pools", "namespaces", "workloads", "related_resources"].includes(key)) continue'
    ';\n      const section = node("div", undefined, "inventory-section"); const label = COLLECTION.get(ke'
    'y) || key;\n      const content = node("div"); add(section, node("h3", label), content); additional.a'
    'ppend(section);\n      renderTable(content, `technical:${key}`, label, [["Record / full evidence", ro'
    'w => namedRecord(row, key)], ["Namespace", row => row.namespace], ["ARM resource", row => resourceRe'
    'f(row.resource_id)]], rows, renderFiltered);\n    }\n    if (!additional.childElementCount) additional'
    '.append(empty("Not evaluated: no additional technical collections were included."));\n  };\n  const re'
    'nderEvidence = (evidence, key) => {\n    const item = node("li");\n    add(item, facts([["Source", `${'
    'evidence.source_id} / ${sourceMap.has(evidence.source_id) ? SOURCE_STATUS.get(sourceMap.get(evidence'
    '.source_id).status) : "Not evaluated"}`],\n      ["Observation date", utc(evidence.observed_at)], ["O'
    'bserved resource", armId(evidence.resource_id)]]),\n      node("pre", jsonText(evidence.value), "json'
    '"));\n    item.dataset.evidenceKey = key;\n    return item;\n  };\n  const findingDisclosure = finding ='
    '> {\n    const wrapper = node("details", undefined, "finding"); wrapper.dataset.detailKey = `finding:'
    '${finding.check_id}`;\n    const summary = node("summary");\n    add(summary, severity(finding.severit'
    'y), add(node("span", undefined, "finding-main"), node("span", finding.title, "finding-title"),\n     '
    ' node("span", `${finding.check_id} · ${LEVEL.get(finding.level)} · ${subjectLabel(finding)}`, "findi'
    'ng-reference")));\n    const body = node("div", undefined, "finding-body");\n    add(body, facts([["ID'
    ' / rule", `${finding.check_id} / ${text(finding.rule_id)}`], ["Level", LEVEL.get(finding.level)], ["'
    'Area", AREA.get(finding.area)],\n      ["Well-Architected pillar", PILLAR.get(finding.pillar)], ["Sev'
    'erity", SEVERITY.get(finding.severity)], ["Indicative effort", EFFORT.get(finding.effort)],\n      ["'
    'Namespace / workload", `${text(finding.namespace)} / ${text(finding.workload_name)}`], ["Resource na'
    'me", finding.resource_name],\n      ["Resource ID", idWithPortal(finding.resource_id)], ["Checklist I'
    'D", finding.checklist_id], ["Checklist GUID", finding.checklist_guid],\n      ["Microsoft Learn", per'
    'mittedLink(finding.learn_url, "Open the recommendation in Microsoft Learn")],\n      ["Checklist refe'
    'rence", finding.checklist_url], ["Kubernetes reference", finding.kubernetes_url]]));\n    add(body, n'
    'ode("h4", "Business impact"), node("p", finding.business_impact, "prose"), node("h4", "Recommendatio'
    'n"), node("p", finding.recommendation, "prose"));\n    if (finding.reason) add(body, node("h4", "Reco'
    'rded reason"), node("p", finding.reason, "prose"));\n    const list = node("ol", undefined, "evidence'
    '-list");\n    for (const [index, evidence] of finding.evidence.entries()) list.append(renderEvidence('
    'evidence, `${finding.check_id}:${index}`));\n    add(body, node("h4", "Observed evidence and source d'
    'ate"), list, rawReceipt(finding, `finding-raw:${finding.check_id}`));\n    return add(wrapper, summar'
    'y, body);\n  };\n  const renderFindings = scope => {\n    byId("findings-count").textContent = `${plura'
    'l(scope.findings.length, "matching finding", "matching findings")} of ${model.findings.length} inclu'
    'ded. ${plural(scope.checks.filter(check => check.status === "not_evaluated").length, "check", "check'
    's")} not evaluated in this scope.`;\n    const list = byId("findings-list"); list.replaceChildren(); '
    'byId("findings-pagination").replaceChildren();\n    const ordered = state.findingsOrder === "model" ?'
    ' scope.findings : [...scope.findings].sort((left, right) => severityRank(left.severity) - severityRa'
    'nk(right.severity));\n    const visible = ordered.slice(0, showLimit("findings"));\n    for (const [le'
    'vel, label] of LEVEL) {\n      const group = visible.filter(finding => finding.level === level);\n    '
    '  if (!group.length) continue;\n      const section = node("div", undefined, "findings-group"); secti'
    'on.append(node("h3", label === "Workload" ? "Workloads" : label === "Associated resource" ? "Associa'
    'ted resources" : label));\n      for (const finding of group) section.append(findingDisclosure(findin'
    'g));\n      list.append(section);\n    }\n    if (!scope.findings.length) list.append(empty("0 matching'
    ' findings. This can come from the filters or from missing evaluation; it does not mean the configura'
    'tion is correct. Review the checks and the sources."));\n    else pagination(byId("findings-paginatio'
    'n"), "findings", scope.findings.length, visible.length, renderFiltered);\n    renderTable(byId("check'
    's-table"), "checks", "Checks and coverage", [\n      ["Check / evidence", check => add(node("div"), n'
    'ode("strong", `${check.check_id} / ${check.title}`), rawReceipt(check, `check:${check.check_id}`))],'
    '\n      ["Status / reason", check => add(node("div"), node("strong", STATUS.get(check.status)), node('
    '"span", check.reason, "cell-note"))],\n      ["Area / pillar", check => `${AREA.get(check.area)} / ${'
    'PILLAR.get(check.pillar)}`], ["Resource", check => resourceRef(check.resource_id)]\n    ], scope.chec'
    'ks, renderFiltered);\n  };\n  const renderFinops = scope => {\n    const costSource = model.finops.sour'
    'ces.map(id => sourceMap.get(id)).find(source => source?.cost_type === "ActualCost") || sourceMap.get'
    '("azure_cost");\n    const observed = add(node("div", undefined, "finops-value"), node("h3", "Observe'
    'd cost"),\n      node("strong", money(model.finops.actual_cost), `financial-amount${model.finops.actu'
    'al_cost === null ? " unknown" : ""}`),\n      node("p", "Amount supplied by the billing source; not a'
    'n estimate or a per-namespace invoice.", "qualification"));\n    const savings = add(node("div", unde'
    'fined, "finops-value savings"), node("h3", "Estimated savings"),\n      node("strong", model.finops.e'
    'stimated_savings === null ? "To be estimated" : money(model.finops.estimated_savings),\n        `fina'
    'ncial-amount${model.finops.estimated_savings === null ? " unknown" : ""}`),\n      node("p", model.fi'
    'nops.estimated_savings === null ?\n        "Not calculated. Applicable prices, a representative basel'
    'ine and the proposal\'s assumptions are missing. A candidate is not a saving." :\n        "Estimate su'
    'pplied by the engine, not realized savings. Review the window, assumptions and eligibility before yo'
    'u decide.", "qualification"));\n    byId("finops-baseline").replaceChildren(add(node("div", undefined'
    ', "finops-values"), observed, savings),\n      facts([["Billing period", windowText(model.finops.wind'
    'ow)], ["Observed currency", model.finops.currency],\n        ["Exact cost read scope", costSource?.sc'
    'ope ? armId(costSource.scope) : null],\n        ["Billing association / not ownership", isObject(cost'
    'Source?.association) ? Object.entries(costSource.association).map(([key, value]) => `${key}: ${text('
    'value)}`).join(" · ") : costSource?.association],\n        ["Cost source / status", costSource ? `${c'
    'ostSource.id} / ${SOURCE_STATUS.get(costSource.status)}` : "Not evaluated"],\n        ["Complete bill'
    'ing read", model.finops.cost_source_complete === true ? "Complete per the receipt" : model.finops.co'
    'st_source_complete === false ? "Not complete" : "Not evaluated"],\n        ["Declared sources", model'
    '.finops.sources.length ? model.finops.sources.map(id => `${id} / ${sourceMap.has(id) ? SOURCE_STATUS'
    '.get(sourceMap.get(id).status) : "Not evaluated"}`).join("; ") : "Not evaluated"],\n        ["Savings'
    ' assumptions", model.finops.estimated_savings === null ? "Not calculated; no savings model was suppl'
    'ied." : "See the notes and evidence for the supplied estimate."]]));\n    byId("finops-baseline").app'
    'end(node("p", "Namespace or workload filters do not assign cost to that workload. The period and sco'
    'pe keep the full billing receipt; the records can include historical or deleted assets and VMSS chil'
    'd resources.", "qualification"));\n    byId("finops-notes").replaceChildren();\n    for (const note of'
    ' model.finops.notes) byId("finops-notes").append(node("li", note));\n    if (!model.finops.notes.leng'
    'th) byId("finops-notes").append(node("li", "Not evaluated: no financial qualification notes were inc'
    'luded."));\n    renderTable(byId("finops-candidates"), "finops-candidates", "FinOps candidates", [\n  '
    '    ["Candidate / source", row => add(node("div"), node("strong", row.title), node("span", `${text(r'
    'ow.id)} · ${text(row.source_id)}`, "cell-note"), resourceRef(row.resource_id), rawReceipt(row, `cand'
    'idate:${text(row.id)}`))],\n      ["Basis / sample", row => `${text(row.basis)} / ${text(row.value)} '
    '${text(row.unit)} / ${text(row.sample_count)} ${row.sample_count === 1 ? "sample" : "samples"} / ${w'
    'indowText(row.window)}`],\n      ["Supplied recommendation", row => row.recommendation], ["Estimated '
    'savings", row => row.estimated_savings === null ? "To be estimated / Not calculated" : money(row.est'
    'imated_savings)]\n    ], scope.candidates, renderFiltered);\n    const receipts = byId("finops-receipt'
    's"); receipts.replaceChildren();\n    for (const [key, label] of [["cost_rows", "Costs included"], ["'
    'metrics", "Utilization included"]]) {\n      const content = node("div"); add(receipts, node("h3", la'
    'bel), content);\n      const rows = model.finops[key] === null ? null : model.finops[key].filter(row '
    '=> (!state.filters.area || state.filters.area === "finops") && scope.filterRecord(row, `finops.${key'
    '}`));\n      renderTable(content, `finops:${key}`, label, [["Full record", row => rawReceipt(row, `${'
    'key}:${text(row.resource_id)}:${JSON.stringify(row)}`)]], rows, renderFiltered);\n    }\n  };\n  const '
    'graphIconKey = kind => {\n    const value = kind.toLowerCase();\n    if (["aks", "cluster", "managed_c'
    'luster", "agent_pool", "node_pool", "microsoft.containerservice/managedclusters", "microsoft.contain'
    'erservice/managedclusters/agentpools"].includes(value)) return "aks";\n    if (["load_balancer", "pub'
    'lic_load_balancer", "private_load_balancer", "azure_load_balancer", "load_balancer_frontend_public",'
    ' "load_balancer_frontend_private",\n      "load_balancer_backend_pool", "load_balancer_probe", "load_'
    'balancer_rule", "microsoft.network/loadbalancers"].includes(value)) return "load_balancer";\n    if ('
    '["vnet", "subnet", "virtual_network", "microsoft.network/virtualnetworks", "microsoft.network/virtua'
    'lnetworks/subnets"].includes(value)) return "virtual_network";\n    if (["nsg", "network_security_gro'
    'up", "microsoft.network/networksecuritygroups"].includes(value)) return "network_security_group";\n  '
    '  if (["disk", "managed_disk", "microsoft.compute/disks"].includes(value)) return "disk";\n    if (["'
    'acr", "container_registry", "microsoft.containerregistry/registries"].includes(value)) return "conta'
    'iner_registry";\n    if (["key_vault", "microsoft.keyvault/vaults"].includes(value)) return "key_vaul'
    't";\n    if (["identity", "managed_identity", "microsoft.managedidentity/userassignedidentities"].inc'
    'ludes(value)) return "managed_identity";\n    if (["storage", "storage_account", "microsoft.storage/s'
    'torageaccounts"].includes(value)) return "storage_account";\n    return null;\n  };\n  const product = '
    '(iconKey, label, description) => {\n    const wrapper = node("div", undefined, "architecture-product"'
    ');\n    if (AZURE_ICONS.has(iconKey)) {\n      const image = node("img"); image.src = AZURE_ICONS.get('
    'iconKey); image.alt = ""; image.className = "architecture-product-icon";\n      wrapper.append(image)'
    ';\n    }\n    const reading = add(node("div"), node("strong", label));\n    if (description) reading.ap'
    'pend(node("span", description, "cell-note"));\n    return add(wrapper, reading);\n  };\n  const renderR'
    'eference = () => {\n    const reference = byId("architecture-reference");\n    if (reference.childElem'
    'entCount) return;\n    add(reference, add(node("div", undefined, "architecture-note"), node("h3", "Re'
    'ference proposal - NOT deployed"),\n      node("p", "A conditional pattern based on the Azure Archite'
    "cture Center and the five Well-Architected pillars. It is not a map of the customer's estate, a comp"
    'leted project or a quote."),\n      node("p", "Validate the SLA, RTO/RPO, isolation, regions, traffic'
    ', dependencies and budget with the owners before you choose components.", "qualification")));\n    co'
    'nst diagram = node("figure", undefined, "reference-diagram"); diagram.setAttribute("aria-label", "En'
    'try alternatives and separation in a reference AKS architecture, not deployed");\n    const entries ='
    ' node("div", undefined, "reference-entry");\n    add(entries, add(node("div"), product("application_g'
    'ateway", "Azure Application Gateway + WAF", "HTTP(S) option: application protection based on the thr'
    'eat model.")),\n      add(node("div"), product("load_balancer", "Public Azure Load Balancer / ELB", "'
    'L4 alternative when public exposure is needed; it does not provide a WAF.")));\n    const network = n'
    'ode("div", undefined, "reference-network");\n    add(network, node("h3", "Azure Virtual Network / pro'
    'posed separate subnets"));\n    const ingress = add(node("div", undefined, "reference-lane"), node("h'
    '4", "Ingress subnet"),\n      product("load_balancer", "Private Azure Load Balancer / ILB", "Private '
    'frontend for the internal entry pattern, when it applies."),\n      node("p", "The Kubernetes ingress'
    ' controller or gateway must be chosen and operated explicitly; its presence is not inferred from a S'
    'ervice.", "qualification"));\n    const cluster = add(node("div", undefined, "reference-lane"), node('
    '"h4", "AKS subnet"),\n      product("aks", "Azure Kubernetes Service (AKS)", "Separate System and Use'
    'r pools; zones and scale based on the SLA and regional capacity."),\n      add(node("div", undefined,'
    ' "reference-workloads"),\n        node("p", "System pool: platform components and the minimum support'
    'ed capacity."),\n        node("p", "User pool: applications, namespaces per team, quotas and NetworkP'
    'olicy.")));\n    add(network, add(node("div", undefined, "reference-lanes"), ingress, cluster));\n    '
    'add(diagram, entries, node("p", "Entry alternatives; they are not two deployed paths. Review TLS, ro'
    'utes and exposure.", "reference-link"), network);\n    const platform = add(node("div", undefined, "r'
    'eference-platform"),\n      product("container_registry", "Azure Container Registry", "Only if the su'
    'pply chain and approved dependencies require it."),\n      product("key_vault", "Azure Key Vault", "I'
    'dentity-based access with minimum scope; this review reads no secrets."),\n      product("monitor", "'
    'Azure Monitor", "Defined telemetry and SLOs; enabling an extension does not prove delivery or health'
    '."));\n    add(diagram, platform, node("figcaption", "The subnets and links in this proposal are open'
    ' design decisions. No icon shows that the resource exists in the observed cluster."));\n    reference'
    '.append(diagram);\n    const decisions = node("div", undefined, "reference-decisions");\n    add(decis'
    'ions, node("h3", "Decisions and tradeoffs for the team to close"));\n    const rows = [\n      ["Relia'
    'bility", "Separate System/User pools and define availability, upgrades, backups and recovery.", "Zon'
    'es and redundancy add resilience only with the right region, capacity, SLA and recovery tests."],\n  '
    '    ["Security", "Choose public L4 exposure or protected HTTP(S) entry; use identities and least pri'
    'vilege.", "An ILB is not a WAF. Namespaces are not a strong enough isolation boundary for every mult'
    'itenant model."],\n      ["Cost", "Size with representative utilization, costs per scope and applicab'
    'le prices/commitments.", "Gateways, redundancy, telemetry and endpoints have a cost. This diagram as'
    'signs no prices or savings percentages."],\n      ["Operations", "Document IaC, owners, SLOs, upgrade'
    's and per-namespace policies.", "Missing IaC in this review does not prove drift or manual creation.'
    '"],\n      ["Performance", "Validate requests/limits, autoscaling, routes and capacity with represent'
    'ative tests.", "A current sample does not prove sustained capacity, application performance or room '
    'to reduce the SKU."]\n    ];\n    renderTable(decisions.appendChild(node("div")), "reference-decisions'
    '", "Conditional proposal for human review",\n      [["Pillar", row => row[0]], ["Proposed decision", '
    'row => row[1]], ["Assumption / tradeoff", row => row[2]]], rows, renderReference);\n    decisions.que'
    'rySelector("caption").textContent = "Five conditional reference decisions; they are not findings or '
    'evidence of observed resources.";\n    decisions.querySelector(".table-footer").remove();\n    referen'
    'ce.append(decisions);\n    const links = node("p", undefined, "qualification");\n    add(links, permit'
    'tedLink("https://learn.microsoft.com/en-us/azure/architecture/reference-architectures/containers/aks'
    '/baseline-aks", "AKS baseline / Azure Architecture Center"),\n      document.createTextNode(" · "), p'
    'ermittedLink("https://learn.microsoft.com/en-us/azure/architecture/guide/multitenant/service/aks", "'
    'AKS multitenant / namespaces"),\n      document.createTextNode(" · "), permittedLink("https://learn.m'
    'icrosoft.com/en-us/azure/well-architected/service-guides/azure-kubernetes-service", "AKS guide / fiv'
    'e pillars"));\n    add(reference, links, node("p", "Official references checked on 13 Oct 2026. Micro'
    'soft Azure V24 icons are used in diagrams and documentation with their original shapes and proportio'
    'ns. They are not this report\'s logo.", "qualification"));\n  };\n  const graphKindLabel = kind => GRAP'
    'H_KINDS.get(kind) || kind;\n  const graphNamespace = row => {\n    const evidence = isObject(row.evide'
    'nce) ? row.evidence : {};\n    return evidence.namespace || evidence.kubernetes_ref?.namespace || "";'
    '\n  };\n  const graphWorkloadMatches = (row, selected) => {\n    const evidence = isObject(row.evidence'
    ') ? row.evidence : {};\n    const reference = evidence.kubernetes_ref || evidence;\n    const target ='
    ' workloadIdentity(selected);\n    if (graphNamespace(row) !== target.namespace) return false;\n    if '
    '(reference.uid && target.uid) return reference.uid === target.uid;\n    return reference.name === tar'
    'get.name && reference.kind === target.kind;\n  };\n  const renderArchitecture = scope => {\n    const g'
    'raph = model.architecture;\n    for (const id of ["architecture-observed-note", "architecture-map", "'
    'architecture-properties", "architecture-tree", "architecture-nodes", "architecture-edges", "architec'
    'ture-unknowns"]) byId(id).replaceChildren();\n    const kindSelect = byId("architecture-kind"), selec'
    't = byId("architecture-node");\n    const note = byId("architecture-observed-note");\n    if (!graph) '
    '{\n      add(note, node("h3", "Observed architecture / Not evaluated"),\n        node("p", "This snaps'
    'hot includes no graph of confirmed relationships. The inventory is still available, but no connectio'
    'ns, ingress, ELB/ILB or dependencies are invented."));\n      byId("architecture-map").append(empty("'
    'Not evaluated: no nodes and links with their join fields were supplied."));\n      kindSelect.disable'
    'd = true; select.disabled = true;\n      kindSelect.replaceChildren(node("option", "All types")); kin'
    'dSelect.firstChild.value = "";\n      select.replaceChildren(node("option", "Not evaluated"));\n      '
    'byId("architecture-tree").append(node("h3", "Resources / Not evaluated"));\n      byId("architecture-'
    'unknowns").append(empty("See this snapshot\'s source receipts; an error does not prove that there are'
    ' no relationships."));\n      return;\n    }\n    kindSelect.disabled = false; select.disabled = false;'
    '\n    const nodeMap = new Map(graph.nodes.map(row => [row.id, row]));\n    let scoped = graph.nodes;\n '
    '   if (state.filters.namespace || state.filters.workload) {\n      const direct = new Set(graph.nodes'
    '.filter(row => state.filters.workload ? graphWorkloadMatches(row, workloadMap.get(state.filters.work'
    'load)) :\n        graphNamespace(row) === state.filters.namespace).map(row => row.id));\n      const c'
    'ontext = new Set(direct);\n      for (const edge of graph.edges) if (direct.has(edge.from) || direct.'
    'has(edge.to)) { context.add(edge.from); context.add(edge.to); }\n      scoped = graph.nodes.filter(ro'
    'w => context.has(row.id));\n    }\n    const kinds = [...new Set(scoped.map(row => row.kind))].sort((a'
    ', b) => graphKindLabel(a).localeCompare(graphKindLabel(b), "en"));\n    kindSelect.replaceChildren(no'
    'de("option", "All types")); kindSelect.firstChild.value = "";\n    fillOptions(kindSelect, kinds.map('
    'kind => [kind, graphKindLabel(kind)]));\n    if (!kinds.includes(state.graphKind)) state.graphKind = '
    '"";\n    kindSelect.value = state.graphKind;\n    const options = scoped.filter(row => !state.graphKin'
    'd || row.kind === state.graphKind);\n    if (!options.some(row => row.id === state.graphNode)) state.'
    'graphNode = options.find(row => row.resource_id === model.cluster.id && graphIconKey(row.kind) === "'
    'aks")?.id || options[0]?.id || "";\n    select.replaceChildren();\n    for (const row of options) { co'
    'nst option = node("option", `${graphKindLabel(row.kind)} / ${row.label}`); option.value = row.id; se'
    'lect.append(option); }\n    if (!options.length) { const option = node("option", "0 matching resource'
    's / does not mean absence"); option.value = ""; select.append(option); }\n    select.value = state.gr'
    'aphNode;\n    add(note, node("h3", "Observed architecture"),\n      node("p", `${plural(graph.nodes.le'
    'ngth, "node", "nodes")} and ${plural(graph.edges.length, "relationship", "relationships")} supplied;'
    ' ${plural(graph.unknowns.length, "limit", "limits")} not evaluated. Reference: ${utc(model.reference'
    '_utc)}.`),\n      node("p", "Arrows show confirmed configuration references or joins, not verified tr'
    'affic, mounts, effective authorization or health. ELB is the public Azure Load Balancer; ILB is its '
    'private frontend, never an AWS product.", "qualification"),\n      node("p", state.filters.namespace '
    '|| state.filters.workload ? "Showing the objects in the Kubernetes selection and their confirmed nei'
    'ghbors; area, status and severity filters do not reinterpret the topology." :\n        "Topology of t'
    'he whole cluster. Area, status and severity filters do not reinterpret these relationships.", "quali'
    'fication"));\n    const chosen = nodeMap.get(state.graphNode);\n    const tree = byId("architecture-tr'
    'ee"); tree.append(node("h3", `Resources / ${options.length}`));\n    const choose = id => { state.gra'
    'phNode = id; renderArchitecture(currentScope()); };\n    for (const kind of kinds) {\n      const rows'
    ' = options.filter(row => row.kind === kind);\n      if (!rows.length) continue;\n      const list = no'
    'de("ul");\n      for (const row of rows) {\n        const button = node("button", row.label); button.t'
    'ype = "button"; button.setAttribute("aria-pressed", String(row.id === state.graphNode));\n        but'
    'ton.dataset.graphNode = row.id; button.addEventListener("click", () => choose(row.id)); list.append('
    'add(node("li"), button));\n      }\n      const group = node("details"); group.dataset.detailKey = `gr'
    'aph-kind:${kind}`; group.open = rows.some(row => row.id === state.graphNode);\n      add(group, node('
    '"summary", `${graphKindLabel(kind)} / ${rows.length}`), list); tree.append(group);\n    }\n    const m'
    'ap = byId("architecture-map");\n    map.tabIndex = 0; map.setAttribute("role", "region");\n    if (!ch'
    'osen) map.append(empty("0 objects with a matching identity. The shared ARM ID is never used to mix n'
    'amespaces or workloads."));\n    else {\n      const allowedIds = new Set(scoped.map(row => row.id));\n'
    '      const connections = graph.edges.filter(edge => allowedIds.has(edge.from) && allowedIds.has(edg'
    'e.to) && (edge.from === chosen.id || edge.to === chosen.id));\n      const neighborIds = [...new Set('
    'connections.map(edge => edge.from === chosen.id ? edge.to : edge.from))].filter(id => id !== chosen.'
    'id);\n      const visibleIds = new Set([chosen.id, ...neighborIds.slice(0, 12)]);\n      const visible'
    ' = graph.nodes.filter(row => visibleIds.has(row.id));\n      const left = visible.filter(row => row.i'
    'd !== chosen.id && connections.some(edge => edge.to === chosen.id && edge.from === row.id));\n      c'
    'onst right = visible.filter(row => row.id !== chosen.id && !left.includes(row));\n      const rows = '
    'Math.max(1, left.length, right.length), height = Math.max(240, rows * 96 + 64);\n      const position'
    's = new Map([[chosen.id, {x: left.length ? 270 : 12, y: height / 2 - 36}]]);\n      for (const [index'
    ', row] of left.entries()) positions.set(row.id, {x: 12, y: 44 + index * 96});\n      for (const [inde'
    'x, row] of right.entries()) positions.set(row.id, {x: 528, y: 44 + index * 96});\n      const drawing'
    ' = svgNode("svg", {viewBox: `0 0 744 ${height}`, role: "group", "aria-labelledby": "architecture-svg'
    '-title architecture-svg-description"});\n      add(drawing, svgNode("title", {id: "architecture-svg-t'
    'itle"}, `Confirmed relationships of ${chosen.label}`),\n        svgNode("desc", {id: "architecture-sv'
    'g-description"}, `${plural(connections.length, "direct relationship", "direct relationships")} suppl'
    'ied. All fields and records are in the relationships table; an arrow does not prove traffic.`));\n   '
    '   const marker = svgNode("marker", {id: "architecture-arrow", viewBox: "0 0 10 10", refX: 9, refY: '
    '5, markerWidth: 6, markerHeight: 6, orient: "auto-start-reverse"});\n      marker.append(svgNode("pat'
    'h", {d: "M 0 0 L 10 5 L 0 10 z", fill: "var(--accent)"})); drawing.append(add(svgNode("defs"), marke'
    'r));\n      for (const edge of connections) {\n        const from = positions.get(edge.from), to = pos'
    'itions.get(edge.to);\n        if (!from || !to || edge.from === edge.to) continue;\n        const forw'
    'ard = from.x < to.x, start = {x: from.x + (forward ? 204 : 0), y: from.y + 36}, end = {x: to.x + (fo'
    'rward ? 0 : 204), y: to.y + 36};\n        const line = svgNode("path", {d: `M${start.x},${start.y} C$'
    '{(start.x + end.x) / 2},${start.y} ${(start.x + end.x) / 2},${end.y} ${end.x},${end.y}`,\n          c'
    'lass: "graph-line", "marker-end": "url(#architecture-arrow)"});\n        line.append(svgNode("title",'
    ' {}, edge.relation)); drawing.append(line);\n      }\n      for (const row of visible) {\n        const'
    ' position = positions.get(row.id);\n        const group = svgNode("g", {class: "graph-node", role: "b'
    'utton", tabindex: 0, "aria-label": `View identity and evidence for ${row.label}`, "data-graph-node":'
    ' row.id});\n        add(group, svgNode("title", {}, `${graphKindLabel(row.kind)} / ${row.label} / ${r'
    'ow.resource_id}`),\n          svgNode("rect", {x: position.x, y: position.y, width: 204, height: 72, '
    'rx: 4, class: `graph-box${row.id === chosen.id ? " selected" : ""}`}));\n        const icon = graphIc'
    'onKey(row.kind);\n        if (icon && AZURE_ICONS.has(icon)) group.append(svgNode("image", {x: positi'
    'on.x + 12, y: position.y + 18, width: 36, height: 36, href: AZURE_ICONS.get(icon), preserveAspectRat'
    'io: "xMidYMid meet", "aria-hidden": "true"}));\n        const inset = icon && AZURE_ICONS.has(icon) ?'
    ' 58 : 12, limit = inset === 58 ? 19 : 27;\n        const shortened = value => value.length <= limit ?'
    ' value : `${value.slice(0, limit - 3)}...`;\n        const kindLabel = new Map([["load_balancer_front'
    'end_public", "ELB / public"], ["load_balancer_frontend_private", "ILB / private"],\n          ["publi'
    'c_load_balancer", "ELB / Azure public"], ["private_load_balancer", "ILB / Azure private"]]).get(row.'
    'kind) || graphKindLabel(row.kind);\n        add(group, svgNode("text", {x: position.x + inset, y: pos'
    'ition.y + 31, class: "graph-label"}, shortened(row.label)),\n          svgNode("text", {x: position.x'
    ' + inset, y: position.y + 49, class: "graph-kind"}, shortened(kindLabel)));\n        group.addEventLi'
    'stener("click", () => choose(row.id));\n        group.addEventListener("keydown", event => { if (["En'
    'ter", " "].includes(event.key)) { event.preventDefault(); choose(row.id); byId("architecture-node").'
    'focus({preventScroll: true}); } });\n        drawing.append(group);\n      }\n      add(map, drawing, n'
    'ode("figcaption", `Confirmed neighborhood: ${visible.length} of ${plural(neighborIds.length + 1, "no'
    'de", "nodes")} visible; ${plural(connections.length, "direct relationship", "direct relationships")}'
    '. On small screens, scroll the diagram sideways. Shortened labels keep their full name, ID and evide'
    'nce in the selector and the receipts. No link is inferred from a name or icon.`));\n      const prope'
    'rties = byId("architecture-properties");\n      add(properties, node("h3", chosen.label), facts([["Ty'
    'pe", graphKindLabel(chosen.kind)], ["Observed ID", armId(chosen.resource_id)], ["Graph key", chosen.'
    'id],\n        ["Cluster", chosen.cluster_name], ["Source", `${chosen.source_id} / ${SOURCE_STATUS.get'
    '(sourceMap.get(chosen.source_id).status)}`],\n        ["Observed at (UTC)", utc(chosen.observed_at)],'
    ' ["Provenance", chosen.provenance]]), rawReceipt(chosen, `graph-node:${chosen.id}`));\n    }\n    cons'
    't scopedIds = new Set(scoped.map(row => row.id));\n    renderTable(byId("architecture-nodes"), "archi'
    'tecture-nodes", "Observed nodes",\n      [["Resource / object", row => row.label], ["Type", row => gr'
    'aphKindLabel(row.kind)], ["Identity", row => armId(row.resource_id)],\n        ["Source / date", row '
    '=> `${row.source_id} / ${utc(row.observed_at)}`], ["Full evidence", row => rawReceipt(row, `graph-no'
    'de-record:${row.id}`)]],\n      scoped, renderFiltered);\n    renderTable(byId("architecture-edges"), '
    '"architecture-edges", "Confirmed relationships",\n      [["From", row => nodeMap.get(row.from).label]'
    ', ["Supplied relationship", row => row.relation], ["To", row => nodeMap.get(row.to).label],\n        '
    '["Sources / date", row => `${row.source_ids.join(", ")} / ${utc(row.observed_at)}`], ["Join fields",'
    ' row => rawReceipt(row, `graph-edge:${row.id}`)]],\n      graph.edges.filter(row => scopedIds.has(row'
    '.from) && scopedIds.has(row.to)), renderFiltered);\n    renderTable(byId("architecture-unknowns"), "a'
    'rchitecture-unknowns", "Topology not evaluated",\n      [["Type / code", row => `${graphKindLabel(row'
    '.kind)} / ${row.code}`], ["Not evaluated / reason", row => row.message],\n        ["Sources / evidenc'
    'e", row => add(node("div"), node("span", row.source_ids.join(", ")), rawReceipt(row, `graph-unknown:'
    '${row.code}:${text(row.resource_id)}`))]],\n      graph.unknowns, renderFiltered);\n  };\n  const rende'
    'rActions = scope => {\n    const plan = byId("action-plan"); plan.replaceChildren();\n    for (const ['
    'key, [label, note]] of BUCKET) {\n      const section = node("section", undefined, "action-bucket"); '
    'const content = node("div");\n      add(section, node("h3", label), node("p", note, "qualification"),'
    ' content); plan.append(section);\n      const rows = scope.actions.filter(action => action.planning_b'
    'ucket === key);\n      renderTable(content, `actions:${key}`, label, [\n        ["Action / check", act'
    'ion => add(node("div"), node("strong", action.title), node("span", `${action.action_id} · ${action.c'
    'heck_id}`, "cell-note"), resourceRef(action.resource_id), rawReceipt(action, `action:${action.action'
    '_id}`))],\n        ["Priority / effort", action => add(node("div"), severity(action.severity), node("'
    'span", `${EFFORT.get(action.effort)} effort`, "cell-note"))],\n        ["Impact / recommendation", ac'
    'tion => add(node("div"), node("p", checkMap.get(action.check_id).business_impact), node("p", action.'
    'recommendation), permittedLink(action.learn_url, "Microsoft Learn"))],\n        ["Owner", action => a'
    'ction.owner === null || action.owner === undefined || action.owner === "" ? "Unassigned" : text(acti'
    'on.owner)]\n      ], rows, renderFiltered);\n    }\n  };\n  const scopeDescription = () => {\n    const f'
    ' = state.filters;\n    return `Selected scope: ${model.cluster.name}; area ${f.area ? AREA.get(f.area'
    ') : "all"}; namespace ${f.namespace || "all"}; workload ${f.workload ? text(workloadMap.get(f.worklo'
    'ad)?.name) : "all"}; level ${f.level ? LEVEL.get(f.level) : "all"}; status ${f.status ? STATUS.get(f'
    '.status) : "all"}; severity ${f.severity ? SEVERITY.get(f.severity) : "all"}; search ${f.search || "'
    'no filter"}.`;\n  };\n  const renderScope = scope => {\n    const evaluated = scope.checks.filter(check'
    ' => ["passed", "failed"].includes(check.status)).length;\n    const unknown = scope.checks.filter(che'
    'ck => check.status === "not_evaluated").length;\n    const na = scope.checks.filter(check => check.st'
    'atus === "not_applicable").length;\n    byId("filter-count").textContent = `${scope.checks.length} ma'
    'tching ${scope.checks.length === 1 ? "check" : "checks"} of ${model.checks.length}; ${evaluated} eva'
    'luated, ${unknown} not evaluated and ${na} not applicable. The indexes keep the full scope.`;\n    by'
    'Id("print-scope").textContent = `${scopeDescription()} All matching records are printed, with no on-'
    'screen page limit. The summary indexes keep the full scope.`;\n    const path = byId("scope-path"); p'
    'ath.replaceChildren();\n    const resetPart = (label, clear) => {\n      const button = node("button",'
    ' label); button.type = "button";\n      button.addEventListener("click", () => { clear(); synchronize'
    'Filters(); filtersChanged(false); }); return button;\n    };\n    path.append(resetPart(model.cluster.'
    'name, () => { state.filters.area = ""; state.filters.namespace = ""; state.filters.workload = ""; })'
    ');\n    if (state.filters.area) add(path, node("span", "/"), resetPart(AREA.get(state.filters.area), '
    '() => { state.filters.namespace = ""; state.filters.workload = ""; }));\n    if (state.filters.namesp'
    'ace) add(path, node("span", "/"), resetPart(state.filters.namespace, () => { state.filters.workload '
    '= ""; }));\n    if (state.filters.workload) add(path, node("span", "/"), node("span", workloadMap.get'
    '(state.filters.workload)?.name, "scope-part"));\n  };\n  const renderFiltered = () => {\n    const open'
    'ed = new Map([...document.querySelectorAll("details")].map(item => [item.dataset.detailKey, item.ope'
    'n]));\n    const scope = currentScope(); renderScope(scope); renderInventory(scope); renderArchitectu'
    're(scope); renderFindings(scope); renderFinops(scope); renderActions(scope);\n    for (const item of '
    'document.querySelectorAll("details")) item.open = state.print || (opened.has(item.dataset.detailKey)'
    ' ? opened.get(item.dataset.detailKey) : item.open);\n  };\n  const synchronizeFilters = () => {\n    fo'
    'r (const key of ["search", "area", "namespace", "level", "status", "severity"]) byId(`filter-${key}`'
    ').value = state.filters[key];\n    populateWorkloads();\n  };\n  const filtersChanged = (read = true) ='
    '> {\n    if (read) for (const key of ["search", "area", "namespace", "workload", "level", "status", "'
    'severity"]) state.filters[key] = byId(`filter-${key}`).value;\n    state.pages.clear(); renderFiltere'
    'd();\n  };\n  byId("filters-form").addEventListener("submit", event => event.preventDefault());\n  byId'
    '("filter-search").addEventListener("input", () => filtersChanged());\n  for (const key of ["area", "n'
    'amespace", "workload", "level", "status", "severity"]) byId(`filter-${key}`).addEventListener("chang'
    'e", () => {\n    if (key === "namespace") { state.filters.namespace = byId("filter-namespace").value;'
    ' state.filters.workload = ""; populateWorkloads(); }\n    filtersChanged();\n  });\n  byId("reset-filte'
    'rs").addEventListener("click", () => {\n    for (const key of Object.keys(state.filters)) state.filte'
    'rs[key] = "";\n    synchronizeFilters(); filtersChanged(false);\n  });\n  const renderMethod = () => {\n'
    '    const opened = new Map([...document.querySelectorAll("#methodology details")].map(item => [item.'
    'dataset.detailKey, item.open]));\n    byId("method-scope").replaceChildren();\n    add(byId("method-sc'
    'ope"), facts([["Read-only", "Declared by the engine"], ["Index type", model.methodology.score_kind]]'
    '),\n      detail("Declared assessment scope", "method-scope", node("pre", jsonText(model.methodology.'
    'scope ?? null), "json")));\n    renderTable(byId("sources-table"), "sources", "Sources for the full s'
    'napshot", [\n      ["Source / receipt", source => add(node("div"), node("strong", source.id), rawRece'
    'ipt(source, `source:${source.id}`))],\n      ["Status", source => SOURCE_STATUS.get(source.status)], '
    '["UTC reference", source => utc(source.time)],\n      ["Records / pages", source => `${text(source.re'
    'cords)} / ${text(source.pages)}`],\n      ["Limits / errors", source => {\n        const wrapper = nod'
    'e("div", source.note);\n        if (source.window) wrapper.append(node("span", windowText(source.wind'
    'ow), "cell-note"));\n        const list = node("ul", undefined, "source-errors");\n        for (const '
    'error of source.errors) list.append(node("li", `${text(error.code)} / HTTP ${text(error.http_status)'
    '} / ${text(error.message)}`));\n        wrapper.append(list); return wrapper;\n      }]\n    ], model.s'
    'ources, () => { renderMethod(); if (state.print) for (const item of document.querySelectorAll("detai'
    'ls")) item.open = true; });\n    const sourceData = byId("source-data-receipts"); sourceData.replaceC'
    'hildren();\n    if (model.source_data === undefined || model.source_data === null) sourceData.append('
    'empty("Not evaluated: the model includes no additional observations."));\n    else sourceData.append('
    'node("pre", jsonText(model.source_data), "json"));\n    const pins = byId("catalog-pins"); pins.repla'
    'ceChildren();\n    const coverage = model.methodology.catalog_coverage;\n    pins.append(facts([["Cata'
    'log items", coverage?.total_items], ["Mapped items", coverage?.mapped_items], ["Items not automated"'
    ', coverage?.unmapped_items]]));\n    add(pins, node("p", "Catalog coverage is not assessment coverage'
    '. Architecture or intent questions that are not automated need human review.", "qualification"),\n   '
    '   detail("Catalog snapshot and versions", "catalog-snapshot", node("pre", jsonText(model.methodolog'
    'y.catalogSnapshot ?? null), "json")));\n    const references = model.methodology.source_pins;\n    if '
    '(!references || !references.length) pins.append(empty("Not evaluated: no pinned references were incl'
    'uded."));\n    else for (const [index, pin] of references.entries()) pins.append(detail(`Pinned refer'
    'ence: ${text(pin?.name)}${pin?.version ? ` / ${pin.version}` : ""}`, `pin:${index}`, node("pre", jso'
    'nText(pin), "json")));\n    const queries = byId("queries"); queries.replaceChildren();\n    byId("que'
    'ries-title").textContent = `Included queries and limits (${(model.methodology.queries || []).length}'
    ')`;\n    if (!model.methodology.queries || !model.methodology.queries.length) queries.append(empty("N'
    'ot evaluated: the model includes no query signatures or read limits."));\n    else for (const [index,'
    ' query] of model.methodology.queries.entries()) {\n      const section = node("div", undefined, "quer'
    'y");\n      add(section, node("h4", query.description || query.source_id), facts([["Source", query.so'
    'urce_id], ["Read limit", query.read_limit]]),\n        node("pre", query.command, "command"), rawRece'
    'ipt(query, `query:${index}`)); queries.append(section);\n    }\n    const limitations = byId("limitati'
    'ons"); limitations.replaceChildren();\n    if (!model.methodology.limitations.length) limitations.app'
    'end(empty("Not evaluated: no declared limitations were included. This does not mean there are none."'
    '));\n    else { const list = node("ul", undefined, "finops-notes"); for (const item of model.methodol'
    'ogy.limitations) list.append(node("li", item)); limitations.append(list); }\n    for (const item of d'
    'ocument.querySelectorAll("#methodology details")) item.open = state.print || (opened.get(item.datase'
    't.detailKey) || false);\n  };\n  const csvValue = value => {\n    let content = value === null || value'
    ' === undefined ? "" : (typeof value === "object" ? JSON.stringify(value) : String(value));\n    if (/'
    "^[\\s\\u0000-\\u001f]*[=+\\-@]/u.test(content) || /^[\\t\\r\\n]/u.test(content)) content = `'${content}`;\n "
    '   return `"${content.replace(/"/g, \'""\')}"`;\n  };\n  const download = (filename, content, type) => {'
    '\n    const blob = new Blob([content], {type}); const url = URL.createObjectURL(blob);\n    const link'
    ' = node("a"); link.href = url; link.download = filename; link.hidden = true; document.body.append(li'
    'nk); link.click(); link.remove();\n    setTimeout(() => URL.revokeObjectURL(url), 1000);\n  };\n  const'
    ' exportCsv = (filename, columns, rows) => {\n    const lines = [columns.map(([label]) => csvValue(lab'
    'el)).join(",")];\n    for (const row of rows) lines.push(columns.map(([, read]) => csvValue(read(row)'
    ')).join(","));\n    download(filename, `\\ufeff${lines.join("\\r\\n")}\\r\\n`, "text/csv;charset=utf-8");\n'
    '  };\n  const checkColumns = [\n    ["check_id", row => row.check_id], ["checklist_id", row => row.che'
    'cklist_id], ["title", row => row.title],\n    ["status", row => row.status], ["level", row => row.lev'
    'el], ["area", row => row.area], ["pillar", row => row.pillar],\n    ["severity", row => row.severity]'
    ', ["resource_id", row => row.resource_id], ["namespace", row => row.namespace],\n    ["workload_name"'
    ', row => row.workload_name], ["evidence", row => row.evidence], ["recommendation", row => row.recomm'
    'endation],\n    ["learn_url", row => row.learn_url], ["effort", row => row.effort], ["reason", row =>'
    ' row.reason], ["record_json", row => row]\n  ];\n  byId("export-json").addEventListener("click", () =>'
    ' download("aks-review-full.json", embeddedJson, "application/json;charset=utf-8"));\n  byId("export-f'
    'iltered-json").addEventListener("click", () => {\n    const scope = currentScope();\n    const finops '
    '= Object.create(null);\n    for (const [key, value] of Object.entries(model.finops)) finops[key] = ke'
    'y === "candidates" ? scope.candidates : (["cost_rows", "metrics"].includes(key) && value !== null ? '
    'value.filter(row => (!state.filters.area || state.filters.area === "finops") && scope.filterRecord(r'
    'ow, `finops.${key}`)) : value);\n    const exported = Object.create(null);\n    for (const [key, value'
    '] of Object.entries(model)) exported[key] = value;\n    exported.inventory = scope.inventory; exporte'
    'd.checks = scope.checks; exported.findings = scope.findings; exported.finops = finops; exported.acti'
    'ons = scope.actions;\n    exported.filter_context = state.filters;\n    exported.scope_note = "Indexes'
    ", sources, source_data, methodology and topology keep the cluster's full snapshot; filtered collecti"
    'ons contain every matching record, not just the visible page.";\n    if (documentModel.schema_version'
    ' === "1.0") download("aks-review-scope.json", JSON.stringify(exported), "application/json;charset=ut'
    'f-8");\n    else {\n      const wrapper = Object.create(null);\n      for (const [key, value] of Object'
    '.entries(documentModel)) wrapper[key] = value;\n      wrapper.cluster_runs = documentModel.cluster_ru'
    'ns.map(run => run.cluster_name === state.activeCluster ? {...run, snapshot: exported} : run);\n      '
    'wrapper.filter_context = {cluster_name: state.activeCluster, ...state.filters};\n      wrapper.scope_'
    'note = "Only the selected cluster\'s snapshot contains filtered collections. All other results, error'
    's, snapshots and the aggregate keep their full original scope. Topology and receipts are not trimmed'
    '.";\n      download("aks-review-scope.json", JSON.stringify(wrapper), "application/json;charset=utf-8'
    '");\n    }\n  });\n  byId("export-findings").addEventListener("click", () => exportCsv("aks-review-find'
    'ings.csv", checkColumns, currentScope().findings));\n  byId("export-checks").addEventListener("click"'
    ', () => exportCsv("aks-review-checks.csv", checkColumns, currentScope().checks));\n  byId("export-inv'
    'entory").addEventListener("click", () => {\n    const rows = [];\n    for (const [collection, records]'
    ' of Object.entries(currentScope().inventory)) if (records !== null) for (const record of records) ro'
    'ws.push({collection, record});\n    exportCsv("aks-review-inventory.csv", [["collection", row => row.'
    'collection], ["resource_id", row => row.record.resource_id], ["namespace", row => row.record.namespa'
    'ce],\n      ["name", row => row.record.name], ["source_id", row => row.record.source_id], ["observed_'
    'at", row => row.record.observed_at], ["record_json", row => row.record]], rows);\n  });\n  byId("expor'
    't-finops").addEventListener("click", () => exportCsv("aks-review-finops.csv", [["id", row => row.id]'
    ', ["title", row => row.title],\n    ["resource_id", row => row.resource_id], ["source_id", row => row'
    '.source_id], ["window", row => row.window], ["sample_count", row => row.sample_count],\n    ["estimat'
    'ed_savings", row => row.estimated_savings], ["recommendation", row => row.recommendation], ["record_'
    'json", row => row]], currentScope().candidates || []));\n  byId("export-actions").addEventListener("c'
    'lick", () => exportCsv("aks-review-plan.csv", [["action_id", row => row.action_id], ["check_id", row'
    ' => row.check_id],\n    ["resource_id", row => row.resource_id], ["planning_bucket", row => row.plann'
    'ing_bucket], ["severity", row => row.severity], ["effort", row => row.effort],\n    ["owner", row => '
    'row.owner], ["recommendation", row => row.recommendation], ["record_json", row => row]], currentScop'
    'e().actions));\n  const preparePrint = () => {\n    if (state.print || !model) return;\n    state.openD'
    'etails = new Map([...document.querySelectorAll("details")].map(item => [item.dataset.detailKey, item'
    '.open]));\n    renderReference(); state.print = true; renderClusterOverview(); renderCover(); renderF'
    'iltered(); renderMethod();\n    for (const item of document.querySelectorAll("details")) item.open = '
    'true;\n  };\n  const restorePrint = () => {\n    if (!state.print) return;\n    state.print = false; ren'
    'derClusterOverview(); renderCover(); renderFiltered(); renderMethod();\n    for (const item of docume'
    'nt.querySelectorAll("details")) item.open = state.openDetails.get(item.dataset.detailKey) || false;\n'
    '    state.openDetails.clear();\n  };\n  window.addEventListener("beforeprint", preparePrint); window.a'
    'ddEventListener("afterprint", restorePrint);\n  byId("print-report").addEventListener("click", () => '
    'window.print());\n  byId("jump-section").addEventListener("change", () => {\n    const target = byId(b'
    'yId("jump-section").value);\n    target.scrollIntoView(); const heading = target.querySelector("h1, h'
    '2"); heading.tabIndex = -1; heading.focus({preventScroll: true});\n  });\n  const setArchitectureTab ='
    ' (selected, focus = false) => {\n    if (selected === "reference") renderReference();\n    for (const '
    'key of ["observed", "reference"]) {\n      const active = key === selected, tab = byId(`architecture-'
    '${key}-tab`);\n      tab.setAttribute("aria-selected", String(active)); tab.tabIndex = active ? 0 : -'
    '1;\n      byId(`architecture-${key}`).hidden = !active;\n      if (active && focus) tab.focus({prevent'
    'Scroll: true});\n    }\n  };\n  for (const key of ["observed", "reference"]) {\n    const tab = byId(`ar'
    'chitecture-${key}-tab`);\n    tab.addEventListener("click", () => setArchitectureTab(key));\n    tab.a'
    'ddEventListener("keydown", event => {\n      if (["ArrowLeft", "ArrowRight", "Home", "End"].includes('
    'event.key)) {\n        event.preventDefault(); setArchitectureTab(event.key === "Home" ? "observed" :'
    ' event.key === "End" ? "reference" : key === "observed" ? "reference" : "observed", true);\n      }\n '
    '   });\n  }\n  byId("architecture-kind").addEventListener("change", () => { state.graphKind = byId("ar'
    'chitecture-kind").value; state.graphNode = ""; renderArchitecture(currentScope()); });\n  byId("archi'
    'tecture-node").addEventListener("change", () => { state.graphNode = byId("architecture-node").value;'
    ' renderArchitecture(currentScope()); });\n  byId("findings-order").addEventListener("change", () => {'
    ' state.findingsOrder = byId("findings-order").value; state.pages.delete("findings"); renderFiltered('
    '); });\n  const fleetMode = documentModel.schema_version !== "1.0";\n  const rosterByName = new Map((d'
    'ocumentModel.available_clusters || []).map(row => [row.cluster_name, row]));\n  const runMeta = run ='
    '> rosterByName.get(run.cluster_name) || {};\n  const subscriptionLabel = row => row.subscription_name'
    ' || row.subscription_id || "Subscription not reported";\n  const fleet = {subscription: "", search: "'
    '", severity: ""};\n  const SEVERITY_RANK = new Map([["critical", 0], ["high", 1], ["medium", 2], ["lo'
    'w", 3]]);\n  const fleetVisible = () => {\n    const query = fleet.search.trim().toLocaleLowerCase("en'
    '-US");\n    return clusterRuns.filter(run => {\n      const meta = runMeta(run);\n      if (fleet.subsc'
    'ription && meta.subscription_id !== fleet.subscription) return false;\n      return !query || [run.cl'
    'uster_name, meta.resource_group, meta.subscription_name, meta.subscription_id, meta.location]\n      '
    '  .some(value => typeof value === "string" && value.toLocaleLowerCase("en-US").includes(query));\n   '
    ' });\n  };\n  const fleetSeverityCounts = run => {\n    const result = {critical: 0, high: 0, medium: 0'
    ', low: 0};\n    if (run.snapshot) for (const finding of run.snapshot.findings) if (Object.hasOwn(resu'
    'lt, finding.severity)) result[finding.severity] += 1;\n    return result;\n  };\n  const incompleteSour'
    'ces = run => run.snapshot ? run.snapshot.sources.filter(source => !["complete", "not_applicable"].in'
    'cludes(source.status)).length : null;\n  const fleetMoney = (amount, currency) => amount === null || '
    'amount === undefined || !currency ? "Not evaluated" : `${amount.toLocaleString("en-US", {maximumFrac'
    'tionDigits: 2})} ${currency}`;\n  const fillClusterOptions = visible => {\n    const selector = byId("'
    'cluster-selector"); selector.replaceChildren();\n    const all = node("option", `All visible clusters'
    ' (${visible.length})`); all.value = ""; selector.append(all);\n    for (const run of [...visible].sor'
    't((left, right) => left.cluster_name.localeCompare(right.cluster_name, "en"))) {\n      const option '
    '= node("option", `${run.cluster_name} / ${subscriptionLabel(runMeta(run))} / ${RUN_STATUS.get(run.st'
    'atus)}`);\n      option.value = run.cluster_name; selector.append(option);\n    }\n    selector.value ='
    ' visible.some(run => run.cluster_name === state.activeCluster) ? state.activeCluster : "";\n  };\n  co'
    'nst selectCluster = name => { byId("cluster-selector").value = name; initializeCluster(name); byId("'
    'cluster-overview").scrollIntoView(); };\n  const renderFleet = () => {\n    const visible = fleetVisib'
    'le();\n    fillClusterOptions(visible);\n    byId("fleet-scope").textContent = `${visible.length} of $'
    '{clusterRuns.length} clusters visible with the current filters.`;\n    if (byId("fleet-view").hidden)'
    ' return;\n    const status = {ok: 0, partial: 0, error: 0}, severities = {critical: 0, high: 0, mediu'
    'm: 0, low: 0}, costs = new Map();\n    let passed = 0, failed = 0, evaluated = 0, notEvaluated = 0, w'
    'ithCost = 0;\n    for (const run of visible) {\n      status[run.status] += 1;\n      if (!run.snapshot'
    ') continue;\n      const counts = fleetSeverityCounts(run); for (const key of Object.keys(severities)'
    ') severities[key] += counts[key];\n      const global = run.snapshot.scores.global;\n      passed += g'
    'lobal.passed; failed += global.failed; evaluated += global.evaluated; notEvaluated += global.not_eva'
    'luated;\n      if (run.snapshot.finops.actual_cost !== null && run.snapshot.finops.currency) {\n      '
    '  withCost += 1; costs.set(run.snapshot.finops.currency, (costs.get(run.snapshot.finops.currency) ||'
    ' 0) + run.snapshot.finops.actual_cost);\n      }\n    }\n    const kpis = byId("fleet-kpis"); kpis.repl'
    'aceChildren();\n    const fleetKpi = (value, label, detailText, className = "") => {\n      const box '
    '= node("div", undefined, `fleet-kpi ${className}`.trim()); box.dataset.kpi = label;\n      add(box, n'
    'ode("b", String(value)), node("span", label)); if (detailText) box.append(node("small", detailText))'
    '; kpis.append(box);\n    };\n    const findings = Object.values(severities).reduce((total, value) => t'
    'otal + value, 0);\n    fleetKpi(visible.length, "Visible clusters", `${status.ok} collected / ${statu'
    's.partial} partial / ${status.error} with errors`);\n    fleetKpi(new Set(visible.map(run => runMeta('
    'run).subscription_id || "")).size, "Subscriptions");\n    fleetKpi(findings, "Findings", `${severitie'
    's.critical} critical / ${severities.high} high / ${severities.medium} medium / ${severities.low} low'
    '`);\n    fleetKpi(severities.critical, "Critical", "Critical-severity findings", "critical");\n    fle'
    'etKpi(evaluated ? `${(100 * passed / evaluated).toLocaleString("en-US", {maximumFractionDigits: 1})}'
    ' / 100` : "Not evaluated", "Combined local index", `${passed} passed of ${evaluated} evaluated`);\n  '
    '  fleetKpi(evaluated + notEvaluated ? `${(100 * evaluated / (evaluated + notEvaluated)).toLocaleStri'
    'ng("en-US", {maximumFractionDigits: 1})}%` : "Not evaluated", "Combined coverage", `${notEvaluated} '
    'indicators not evaluated`);\n    fleetKpi(costs.size ? [...costs].map(([currency, amount]) => fleetMo'
    'ney(amount, currency)).join(" + ") : "Not evaluated", "Actual cost for the period",\n      `${withCos'
    't} of ${plural(visible.length, "cluster", "clusters")} with cost read (node resource group); differe'
    'nt currencies are never added`);\n    fleetKpi("Not calculated", "Estimated savings", "The report pro'
    'mises no savings; see FinOps candidates per cluster");\n    if (status.error) kpis.append(node("p", `'
    '${plural(status.error, "cluster", "clusters")} with collection errors: not evaluated, not healthy. C'
    'heck their status in the table.`, "qualification"));\n    const ordered = [...visible].sort((left, ri'
    'ght) => {\n      const a = fleetSeverityCounts(left), b = fleetSeverityCounts(right);\n      return (r'
    'ight.status === "error") - (left.status === "error") || b.critical - a.critical || b.high - a.high |'
    '| left.cluster_name.localeCompare(right.cluster_name, "en");\n    });\n    renderTable(byId("cluster-r'
    'uns-table"), "fleet-runs", "Visible clusters", [\n      ["Cluster", run => { if (!run.snapshot) retur'
    'n run.cluster_name; const button = node("button", run.cluster_name, "link-button"); button.type = "b'
    'utton"; button.addEventListener("click", () => selectCluster(run.cluster_name)); return button; }],\n'
    '      ["Subscription", run => subscriptionLabel(runMeta(run))],\n      ["Resource group / region", ru'
    'n => `${text(runMeta(run).resource_group)} / ${text(runMeta(run).location)}`],\n      ["Collection st'
    'atus", run => run.status === "error" ? `${RUN_STATUS.get(run.status)} (${text(run.error && run.error'
    '.code)})` : RUN_STATUS.get(run.status)],\n      ["Coverage", run => run.snapshot && run.snapshot.scor'
    'es.global.coverage_percent !== null ? `${run.snapshot.scores.global.coverage_percent.toLocaleString('
    '"en-US", {maximumFractionDigits: 1})}%` : "Not evaluated"],\n      ["Local index", run => run.snapsho'
    't ? percentage(run.snapshot.scores.global.score) : "Not evaluated"],\n      ["Findings crit. / high /'
    ' medium / low", run => { if (!run.snapshot) return "Not evaluated"; const c = fleetSeverityCounts(ru'
    'n); return `${c.critical} / ${c.high} / ${c.medium} / ${c.low}`; }],\n      ["Critical", run => run.s'
    'napshot ? String(fleetSeverityCounts(run).critical) : "Not evaluated"],\n      ["Actual cost for the '
    'period", run => run.snapshot ? fleetMoney(run.snapshot.finops.actual_cost, run.snapshot.finops.curre'
    'ncy) : "Not evaluated"],\n      ["Estimated savings", () => "Not calculated"],\n      ["Incomplete sou'
    'rces", run => run.snapshot ? String(incompleteSources(run)) : "All (no snapshot)"]\n    ], ordered, r'
    'enderFleet);\n    const rows = [];\n    for (const run of visible) if (run.snapshot) for (const findin'
    'g of run.snapshot.findings) if (!fleet.severity || finding.severity === fleet.severity) rows.push({r'
    'un, finding});\n    rows.sort((left, right) => SEVERITY_RANK.get(left.finding.severity) - SEVERITY_RA'
    'NK.get(right.finding.severity) || left.run.cluster_name.localeCompare(right.run.cluster_name, "en") '
    '|| left.finding.title.localeCompare(right.finding.title, "en"));\n    renderTable(byId("fleet-finding'
    's"), "fleet-findings", "Findings in the visible clusters", [\n      ["Severity", row => severity(row.'
    'finding.severity)], ["Cluster", row => row.run.cluster_name], ["Subscription", row => subscriptionLa'
    'bel(runMeta(row.run))],\n      ["Finding", row => row.finding.title], ["Area", row => AREA.get(row.fi'
    'nding.area) || row.finding.area],\n      ["Resource", row => row.finding.resource_name || row.finding'
    '.resource_id], ["Recommendation", row => row.finding.recommendation]\n    ], rows, renderFleet);\n  };'
    '\n  const showFleet = () => {\n    state.activeCluster = ""; model = undefined; state.graphNode = ""; '
    'state.graphKind = "";\n    byId("fleet-view").hidden = false; byId("cluster-error").hidden = true;\n  '
    '  for (const id of ["cover", "executive", "scope-filters", "inventory", "architecture", "findings", '
    '"finops", "actions", "methodology"]) byId(id).hidden = true;\n    byId("jump-section").disabled = tru'
    'e; document.querySelector(".toolbar-nav").hidden = true; document.querySelector(".report-footer").hi'
    'dden = true;\n    for (const id of ["export-filtered-json", "export-inventory", "export-findings", "e'
    'xport-checks", "export-finops", "export-actions"]) byId(id).disabled = true;\n    byId("print-report"'
    ').disabled = false;\n    renderFleet();\n  };\n  const onFleetFilter = () => {\n    fleet.subscription ='
    ' byId("fleet-subscription").value; fleet.search = byId("fleet-search").value; fleet.severity = byId('
    '"fleet-severity").value;\n    state.pages.delete("fleet-runs"); state.pages.delete("fleet-findings");'
    '\n    if (state.activeCluster && !fleetVisible().some(run => run.cluster_name === state.activeCluster'
    ')) showFleet(); else renderFleet();\n  };\n  const renderClusterOverview = () => {\n    const multi = d'
    'ocumentModel.schema_version !== "1.0", roster = documentModel.available_clusters || [];\n    byId("cl'
    'uster-overview").hidden = !multi && roster.length <= 1;\n    if (multi) {\n      const subscriptions ='
    ' new Map();\n      for (const run of clusterRuns) {\n        const meta = runMeta(run), key = meta.sub'
    'scription_id || "";\n        const entry = subscriptions.get(key) || {label: subscriptionLabel(meta),'
    ' count: 0}; entry.count += 1; subscriptions.set(key, entry);\n      }\n      const choice = byId("flee'
    't-subscription"); choice.replaceChildren();\n      const all = node("option", `All (${subscriptions.s'
    'ize} subscriptions, ${clusterRuns.length} clusters)`); all.value = ""; choice.append(all);\n      for'
    ' (const [key, entry] of [...subscriptions].sort((left, right) => left[1].label.localeCompare(right[1'
    '].label, "en"))) {\n        const option = node("option", `${entry.label} (${entry.count})`); option.'
    'value = key; choice.append(option);\n      }\n      choice.value = fleet.subscription;\n      const sup'
    'plied = documentModel.aggregate, score = supplied.scores.global, aggregate = byId("cluster-aggregate'
    '"); aggregate.replaceChildren();\n      add(aggregate, facts([["Combined local index supplied", perce'
    'ntage(score.score)], ["Combined coverage supplied", supplied.scores.coverage.coverage_percent === nu'
    'll ? "Not evaluated" : `${supplied.scores.coverage.coverage_percent.toLocaleString("en-US", {maximum'
    'FractionDigits: 1})}%`],\n        ["Checks supplied", scoreCaption(score)], ["Findings / critical", `'
    '${supplied.findings_total} / ${supplied.critical_total}`],\n        ["Runs collected / partial / fail'
    'ed", `${supplied.cluster_status_counts.ok ?? 0} / ${supplied.cluster_status_counts.partial ?? 0} / $'
    '{supplied.cluster_status_counts.error ?? 0}`],\n        ["Combined UTC reference", utc(documentModel.'
    'reference_utc)]]),\n        node("p", "Whole-selection aggregate received from the engine (the cards '
    'above follow the filters); a cluster with a primary read error has no evaluated configuration. Curre'
    'ncies, billing periods and node resource group scopes are never mixed.", "qualification"),\n        d'
    'etail("Full aggregate supplied by the engine (every selected cluster)", "multi-aggregate", node("pre'
    '", jsonText(supplied), "json")));\n      byId("export-json").textContent = "Full JSON";\n      byId("e'
    'xport-json").title = "Downloads the full original document with every cluster";\n      return;\n    }\n'
    '    byId("fleet-view").hidden = true; byId("fleet-scope").hidden = true; document.querySelector(".fl'
    'eet-filters").hidden = true;\n    const selector = byId("cluster-selector"); selector.replaceChildren'
    '();\n    for (const run of clusterRuns) { const option = node("option", `${run.cluster_name} / ${RUN_'
    'STATUS.get(run.status)}`); option.value = run.cluster_name; selector.append(option); }\n    for (cons'
    't row of roster) if (!clusterRuns.some(run => run.cluster_name === row.cluster_name)) {\n      const '
    'option = node("option", `${row.cluster_name} / available for a new run, not included`);\n      option'
    '.value = row.cluster_name; option.disabled = true; selector.append(option);\n    }\n    selector.value'
    ' = state.activeCluster;\n    const aggregate = byId("cluster-aggregate"); aggregate.replaceChildren()'
    ';\n    if (multi) {\n      const supplied = documentModel.aggregate, score = supplied.scores.global;\n '
    '     add(aggregate, facts([["Combined local index supplied", percentage(score.score)], ["Combined co'
    'verage supplied", supplied.scores.coverage.coverage_percent === null ? "Not evaluated" : `${supplied'
    '.scores.coverage.coverage_percent.toLocaleString("en-US", {maximumFractionDigits: 1})}%`],\n        ['
    '"Checks supplied", scoreCaption(score)], ["Findings / critical", `${supplied.findings_total} / ${sup'
    'plied.critical_total}`],\n        ["Runs collected / partial / failed", `${supplied.cluster_status_co'
    'unts.ok ?? 0} / ${supplied.cluster_status_counts.partial ?? 0} / ${supplied.cluster_status_counts.er'
    'ror ?? 0}`],\n        ["Combined UTC reference", utc(documentModel.reference_utc)]]),\n        node("p'
    '", "The aggregate is the one received from the engine; a cluster with a primary read error has no ev'
    'aluated configuration. Currencies, billing periods and node resource group scopes are never added to'
    'gether.", "qualification"),\n        detail("Full aggregate and per-cluster inventories", "multi-aggr'
    'egate", node("pre", jsonText(supplied), "json")));\n    } else aggregate.append(node("p", "The additi'
    'onal roster is fixed, authorized configuration, not evidence of presence or health. This file contai'
    'ns a single snapshot.", "qualification"));\n    renderTable(byId("cluster-runs-table"), "cluster-runs'
    '", "Results included per cluster",\n      [["Cluster", run => run.cluster_name], ["Collection status"'
    ', run => RUN_STATUS.get(run.status)], ["UTC reference", run => utc(run.reference_utc)],\n        ["Er'
    'ror / identity", run => rawReceipt({cluster_id: run.cluster_id, status: run.status, error: run.error'
    '}, `cluster-run:${run.cluster_name}`)]], clusterRuns, renderClusterOverview);\n    byId("export-json"'
    ').textContent = "Full JSON";\n    byId("export-json").title = multi ? "Downloads the full original do'
    'cument with every cluster" : "Downloads the full original snapshot";\n  };\n  const initializeCluster '
    '= name => {\n    const run = clusterRuns.find(item => item.cluster_name === name);\n    assert(run, "C'
    'luster not included in the document.");\n    state.activeCluster = name; model = run.snapshot; state.'
    'pages.clear(); state.graphNode = ""; state.graphKind = "";\n    if (fleetMode) { byId("fleet-view").h'
    'idden = true; fillClusterOptions(fleetVisible()); }\n    for (const key of Object.keys(state.filters)'
    ') state.filters[key] = "";\n    for (const item of document.querySelectorAll("details")) item.open = '
    'false;\n    for (const id of ["cover", "executive", "scope-filters", "inventory", "architecture", "fi'
    'ndings", "finops", "actions", "methodology"]) byId(id).hidden = !model;\n    byId("jump-section").dis'
    'abled = !model; document.querySelector(".toolbar-nav").hidden = !model;\n    document.querySelector("'
    '.report-footer").hidden = !model;\n    byId("cluster-error").hidden = Boolean(model);\n    for (const '
    'id of ["export-filtered-json", "export-inventory", "export-findings", "export-checks", "export-finop'
    's", "export-actions", "print-report"]) byId(id).disabled = !model;\n    if (!model) {\n      byId("clu'
    'ster-error").replaceChildren(node("h2", `${run.cluster_name} / Not evaluated`),\n        node("p", "T'
    'he primary read failed. There is no snapshot for this cluster: no indexes, costs, workloads or archi'
    'tecture are borrowed from another run."),\n        node("pre", JSON.stringify(run.error, null, 2), "j'
    'son"));\n      return;\n    }\n    sourceMap.clear(); checkMap.clear(); workloadMap.clear(); workloadRe'
    'sourceCounts.clear(); namespaces.clear();\n    for (const source of model.sources) sourceMap.set(sour'
    'ce.id, source);\n    for (const check of model.checks) checkMap.set(check.check_id, check);\n    for ('
    'const row of model.inventory.workloads || []) workloadResourceCounts.set(row.resource_id, (workloadR'
    'esourceCounts.get(row.resource_id) || 0) + 1);\n    for (const row of model.inventory.workloads || []'
    ') if (row.resource_id && row.name) workloadMap.set(workloadKey(row), workloadIdentity(row));\n    for'
    ' (const check of model.checks) if (check.workload_name && ![...workloadMap.values()].some(row => mat'
    'chesWorkload(check, row))) workloadMap.set(workloadKey(check), workloadIdentity(check));\n    for (co'
    'nst row of model.inventory.namespaces || []) if (row.name) namespaces.add(row.name);\n    for (const '
    'row of workloadMap.values()) if (row.namespace) namespaces.add(row.namespace);\n    for (const check '
    'of model.checks) if (check.namespace) namespaces.add(check.namespace);\n    byId("filter-namespace").'
    'replaceChildren(node("option", "All namespaces")); byId("filter-namespace").firstChild.value = "";\n '
    '   fillOptions(byId("filter-namespace"), [...namespaces].sort((left, right) => left.localeCompare(ri'
    'ght, "en")).map(value => [value, value]));\n    synchronizeFilters(); setArchitectureTab("observed");'
    '\n    renderCover(); renderExecutive(); renderFiltered(); renderMethod();\n  };\n  byId("cluster-select'
    'or").addEventListener("change", () => { const name = byId("cluster-selector").value; if (name) initi'
    'alizeCluster(name); else showFleet(); });\n  for (const id of ["fleet-subscription", "fleet-severity"'
    ']) byId(id).addEventListener("change", onFleetFilter);\n  byId("fleet-search").addEventListener("inpu'
    't", onFleetFilter);\n  renderClusterOverview();\n  if (fleetMode) showFleet(); else initializeCluster('
    'state.activeCluster);\n  byId("opening-state").hidden = true; byId("report-shell").hidden = false;\n  '
    'byId("export-json").disabled = false; byId("print-report").disabled = !model && !fleetMode; document'
    '.body.dataset.status = "ready";\n})();\n</script>\n</body>\n</html>\n'
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


def labels(value, source):
    if value is None:
        return None
    return {text(key, source, 253): text(item, source, 256) for key, item in obj(value, source).items()}


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


def scope_subscription(config=None):
    """Subscription of the cluster being collected: per-cluster config, this thread's active collection, then the optional default."""
    value = (config or {}).get("subscription_id") or getattr(COLLECTION_SCOPE, "subscription_id", None) or SUBSCRIPTION_ID
    return guid_setting("subscription scope", value)


def same_subscription_id(value):
    """Validated ARM ID inside the collected cluster's subscription, or None for a cross-subscription reference (never read)."""
    value = arm_id(value)
    return value if value.split("/")[2].lower() == scope_subscription().lower() else None


def resource_type(resource_id):
    parts = arm_id(resource_id).split("/")
    return (parts[6] + "/" + "/".join(parts[7::2])).lower()


def guid_setting(key, value):
    try:
        if not isinstance(value, str) or str(UUID(value)) != value.lower():
            raise ValueError
    except (ValueError, AttributeError) as exc:
        raise EvidenceError("configuration_required", "Configure the explicit " + key + " before authentication.", "configuration") from exc
    return value.lower()


def plain_label(value, maximum=128):
    """Bounded display text from Azure (subscription name, region); never used in a URL or query."""
    if not isinstance(value, str):
        return None
    value = re.sub(r"[\x00-\x1f\x7f<>]", "", value).strip()[:maximum]
    return value or None


def validate_branding():
    validate_logo(CLIENT_LOGO_DATA_URI, CLIENT_LOGO_ALT)
    if not isinstance(CLIENT_NAME, str) or not 1 <= len(CLIENT_NAME) <= 120 or any(ord(c) < 32 for c in CLIENT_NAME):
        raise EvidenceError("configuration_required", "Client label must be bounded plain text.", "configuration")


def validate_config(cluster_name):
    for key, value in (("TENANT_ID", TENANT_ID), ("MANAGED_IDENTITY_CLIENT_ID", MANAGED_IDENTITY_CLIENT_ID)):
        guid_setting(key, value)
    roster = active_roster()
    if not isinstance(roster, dict) or not 1 <= len(roster) <= MAX_APPROVED_CLUSTERS:
        raise EvidenceError("configuration_required", "Configure one to " + str(MAX_APPROVED_CLUSTERS) + " fixed approved clusters.", "configuration")
    name = cluster_name or next(iter(roster))
    if name not in roster:
        raise EvidenceError("invalid_parameter", "cluster_name must exactly match a cluster_name returned by list_clusters "
                            "(auto-discovered inventory plus operator entries)." if ROSTER is not None and auto_discovery_enabled()
                            else "cluster_name must exactly match the fixed operator allowlist.", "parameters")
    defaults = globals().get("CLUSTER_DEFAULTS") or {}
    config = {**json.loads(json.dumps(obj(defaults, "configuration"))), **obj(roster[name], "configuration")}
    if not config.get("subscription_id"):
        try:
            guid_setting("SUBSCRIPTION_ID", SUBSCRIPTION_ID)
        except EvidenceError as exc:
            raise EvidenceError("configuration_required", "APPROVED_CLUSTERS entry " + name + " has no subscription_id; add it "
                                "(or set the optional SUBSCRIPTION_ID).", "configuration") from exc
    subscription = guid_setting("subscription_id of " + name, config.get("subscription_id") or SUBSCRIPTION_ID)
    aks_name = config.get("aks_name") or name
    for field, value, maximum in (("name", name, 63), ("aks_name", aks_name, 63), ("resource_group", config.get("resource_group"), 90)):
        if not isinstance(value, str) or not 1 <= len(value) <= maximum or not re.fullmatch(r"[A-Za-z0-9_.()-]+", value):
            raise EvidenceError("configuration_required", "Configure a bounded approved " + field + ".", "configuration")
    if config.get("environment") not in ("LAB", "PRODUCTION", "UNSPECIFIED"):
        raise EvidenceError("configuration_required", "Set explicit LAB/PRODUCTION/UNSPECIFIED environment.", "configuration")
    for field in ("kubernetes_enabled", "include_node_resource_group", "advisor_enabled"):
        if not isinstance(config.get(field), bool):
            raise EvidenceError("configuration_required", "Configure the boolean " + field + ".", "configuration")
    if config.get("cost_scope") not in ("disabled", "resource_ids", "node_resource_group"):
        raise EvidenceError("configuration_required", "Configure disabled/resource_ids/node_resource_group cost scope.", "configuration")
    if config.get("cost_timeframe") not in ("month_to_date", "last_30_days"):
        raise EvidenceError("configuration_required", "Configure month_to_date/last_30_days billing timeframe.", "configuration")
    for field in ("approved_related_resource_ids", "approved_cost_resource_ids"):
        ids = config.get(field)
        if not isinstance(ids, list) or len(ids) > MAX_RELATED_RESOURCES or len({str(i).lower() for i in ids}) != len(ids):
            raise EvidenceError("configuration_required", "Configure distinct bounded fixed resource IDs.", "configuration")
        for value in ids:
            arm_id(value, subscription)
    requirements = obj(config.get("requirements"), "configuration")
    allowed = {
        "sla_required", "availability_zones_required", "network_policy_required", "workload_identity_required",
        "overlay_required", "policy_required", "defender_required", "autoscaling_required", "automatic_upgrades_required",
        "node_image_upgrades_required", "diagnostics_required", "maintenance_required", "quota_required",
        "pod_security_required", "cpu_limits_required", "workloads",
    }
    if set(requirements) - allowed:
        raise EvidenceError("configuration_required", "Unknown requirement key; requirements are operator-authored, not query inputs.", "configuration")
    for key, value in requirements.items():
        if key != "workloads" and value is not None and not isinstance(value, bool):
            raise EvidenceError("configuration_required", "Requirement values must be boolean or unknown.", "configuration")
    for key, values in obj(requirements.get("workloads", {}), "configuration").items():
        if not isinstance(key, str) or not re.fullmatch(r"[a-z0-9.-]+/[a-z0-9.-]+", key):
            raise EvidenceError("configuration_required", "Workload requirements use namespace/name keys.", "configuration")
        if set(obj(values, "configuration")) - {"availability_required", "autoscaling_required", "probes_required", "network_policy_required"}:
            raise EvidenceError("configuration_required", "Unknown per-workload requirement.", "configuration")
        if any(value is not None and not isinstance(value, bool) for value in values.values()):
            raise EvidenceError("configuration_required", "Per-workload requirements must be boolean or unknown.", "configuration")
    return {**config, "name": name, "aks_name": aks_name, "subscription_id": subscription,
            "subscription_name": plain_label(config.get("subscription_name")), "location": plain_label(config.get("location"), 64),
            "id": "/subscriptions/" + subscription + "/resourceGroups/"
            + config["resource_group"] + "/providers/Microsoft.ContainerService/managedClusters/" + aks_name}


def auto_discovery_enabled():
    value = globals().get("AUTO_DISCOVERY", False)
    if not isinstance(value, bool):
        raise EvidenceError("configuration_required", "AUTO_DISCOVERY must be True or False.", "configuration")
    return value


def active_roster():
    return ROSTER if ROSTER is not None else APPROVED_CLUSTERS


DISCOVERY_QUERY = (
    "resources | where type =~ 'microsoft.containerservice/managedclusters' "
    "| project id, name, resourceGroup, subscriptionId, tenantId, location "
    "| join kind=leftouter (resourcecontainers | where type =~ 'microsoft.resources/subscriptions' "
    "| project subscriptionId, subscriptionName=name) on subscriptionId "
    "| project id, name, resourceGroup, subscriptionId, tenantId, location, subscriptionName "
    "| order by subscriptionId asc, name asc"
)


def discover_clusters():
    """Observed inventory: every AKS cluster the agent identity can read, from one fixed read-only Resource Graph query."""
    guid_setting("TENANT_ID", TENANT_ID)
    guid_setting("MANAGED_IDENTITY_CLIENT_ID", MANAGED_IDENTITY_CLIENT_ID)
    scope = globals().get("DISCOVERY_SUBSCRIPTION_IDS") or []
    if not isinstance(scope, list) or len(scope) > 1000:
        raise EvidenceError("configuration_required", "DISCOVERY_SUBSCRIPTION_IDS must be a list of up to 1000 subscription IDs.", "configuration")
    subscriptions = [guid_setting("DISCOVERY_SUBSCRIPTION_IDS", value) for value in scope]
    identity = Identity()
    try:
        reader = HttpReader(identity)
        url = reader.allow(ARM_ORIGIN + "/providers/Microsoft.ResourceGraph/resources?api-version=" + ARG_API, "POST")
        rows, skip_token = [], None
        for _ in range(MAX_DISCOVERY_PAGES):
            options = {"resultFormat": "objectArray", "$top": 1000}
            if skip_token:
                options["$skipToken"] = skip_token
            body = {"query": DISCOVERY_QUERY, "options": options}
            if subscriptions:
                body["subscriptions"] = subscriptions
            page = reader.request("POST", url, "arm_discovery", body=body)
            rows.extend(array(page.get("data"), "arm_discovery"))
            skip_token = page.get("$skipToken")
            if not isinstance(skip_token, str) or not skip_token or len(rows) > MAX_APPROVED_CLUSTERS:
                break
        return rows
    finally:
        identity.close()


def effective_roster():
    """Operator entries first (overrides), then every discovered AKS not already listed; bounded and deterministic."""
    if not auto_discovery_enabled():
        return APPROVED_CLUSTERS
    if not isinstance(APPROVED_CLUSTERS, dict):
        raise EvidenceError("configuration_required", "APPROVED_CLUSTERS must be a dictionary (it can be empty).", "configuration")
    rows = discover_clusters()
    names, locations = {}, {}
    for row in rows:
        cluster_id, subscription = str(row.get("id") or "").lower(), str(row.get("subscriptionId") or "").lower()
        if plain_label(row.get("subscriptionName")):
            names.setdefault(subscription, plain_label(row.get("subscriptionName")))
        locations[cluster_id] = plain_label(row.get("location"), 64)
    roster, known = {}, set()
    for key, entry in APPROVED_CLUSTERS.items():
        if isinstance(key, str) and key.startswith("<"):
            continue
        entry = dict(obj(entry, "configuration"))
        if not entry.get("subscription_id"):
            try:
                guid_setting("SUBSCRIPTION_ID", SUBSCRIPTION_ID)
            except EvidenceError as exc:
                raise EvidenceError("configuration_required", "APPROVED_CLUSTERS entry " + str(key)[:63] + " has no subscription_id; add it "
                                    "(or set the optional SUBSCRIPTION_ID).", "configuration") from exc
        subscription = str(entry.get("subscription_id") or SUBSCRIPTION_ID).lower()
        cluster_id = ("/subscriptions/" + subscription + "/resourcegroups/" + str(entry.get("resource_group", ""))
                      + "/providers/microsoft.containerservice/managedclusters/" + str(entry.get("aks_name") or key)).lower()
        known.add(cluster_id)
        entry.setdefault("subscription_name", names.get(subscription))
        entry.setdefault("location", locations.get(cluster_id))
        roster[key] = entry
    operator_entries, discovered, skipped = len(roster), 0, 0
    local = re.compile(r"[A-Za-z0-9_.()-]+")
    for row in rows:
        cluster_id = str(row.get("id") or "")
        parts = cluster_id.split("/")
        if cluster_id.lower() in known:
            continue
        if len(parts) != 9 or parts[1].lower() != "subscriptions" or parts[3].lower() != "resourcegroups" \
                or parts[6].lower() != "microsoft.containerservice" or parts[7].lower() != "managedclusters":
            skipped += 1
            continue
        subscription, group, name = parts[2].lower(), parts[4], parts[8]
        tenant = str(row.get("tenantId") or "").lower()
        if (tenant and tenant != TENANT_ID.lower()) or not re.fullmatch(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", subscription) \
                or not (1 <= len(name) <= 63 and local.fullmatch(name)) or not (1 <= len(group) <= 90 and local.fullmatch(group)):
            skipped += 1
            continue
        key = name if name not in roster else (subscription[:8] + "-" + name)[:63]
        if key in roster:
            skipped += 1
            continue
        entry = {"resource_group": group, "subscription_id": subscription,
                 "subscription_name": names.get(subscription), "location": locations.get(cluster_id.lower())}
        if key != name:
            entry["aks_name"] = name
        roster[key] = entry
        known.add(cluster_id.lower())
        discovered += 1
    DISCOVERY_INFO.clear()
    DISCOVERY_INFO.update({"mode": "auto", "source": "azure_resource_graph", "discovered": discovered,
                           "operator_entries": operator_entries, "skipped": skipped,
                           "subscription_scope": "configured_list" if globals().get("DISCOVERY_SUBSCRIPTION_IDS") else "all_readable"})
    if not roster:
        raise EvidenceError("no_clusters_visible", "Auto-discovery found no AKS cluster the agent identity can read; grant Reader "
                            "with grant-aks-permissions.ps1 and wait 5-10 minutes.", "arm_discovery")
    if len(roster) > MAX_APPROVED_CLUSTERS:
        raise EvidenceError("configuration_required", "Auto-discovery found more than " + str(MAX_APPROVED_CLUSTERS)
                            + " AKS clusters; limit DISCOVERY_SUBSCRIPTION_IDS.", "configuration")
    return roster


def roster_row(config):
    return {"cluster_id": config["id"], "cluster_name": config["name"], "resource_group": config["resource_group"],
            "environment": config["environment"], "subscription_id": config["subscription_id"],
            "subscription_name": config.get("subscription_name"), "location": config.get("location")}


def subscription_filter(configured, subscription):
    """Exact subscription ID or exact display name (case-insensitive); compared locally, never sent to Azure."""
    if not subscription:
        return configured
    wanted = subscription.strip().casefold()
    matched = [config for config in configured if config["subscription_id"] == wanted
               or (config.get("subscription_name") or "").casefold() == wanted]
    ids = {config["subscription_id"] for config in matched}
    if not matched:
        known = sorted({config.get("subscription_name") or config["subscription_id"] for config in configured})
        close = difflib.get_close_matches(subscription.strip(), known, n=3, cutoff=0.5)
        raise EvidenceError("unknown_subscription", "No visible AKS cluster in subscription '" + subscription.strip()[:64] + "'. Use an exact "
                            "subscription ID or display name from list_clusters" + (" (similar: " + ", ".join(close) + ")." if close else "."), "parameters")
    if len(ids) > 1:
        raise EvidenceError("ambiguous_subscription", "Several subscriptions share that display name; use the subscription ID: "
                            + ", ".join(sorted(ids)[:5]) + ".", "parameters")
    return matched


def resolve_names(names, candidates, scoped=False):
    """Exact names (case-insensitive): the list_clusters key or the AKS resource name when it is unique in the candidates."""
    selected, seen = [], set()
    for name in names:
        wanted = name.casefold()
        matches = {config["id"].lower(): config for config in candidates
                   if config["name"].casefold() == wanted or config["aks_name"].casefold() == wanted}
        if len(matches) > 1:
            raise EvidenceError("ambiguous_cluster_name", "Cluster name '" + name + "' exists in several subscriptions: "
                                + ", ".join(sorted(config["name"] + " (" + (config.get("subscription_name") or config["subscription_id"]) + ")"
                                                   for config in matches.values())[:4])
                                + ". Add subscription=<name or ID> or use the list_clusters cluster_name.", "parameters")
        if not matches:
            close = difflib.get_close_matches(name, sorted({config["name"] for config in candidates}), n=3, cutoff=0.6)
            raise EvidenceError("unknown_cluster", "Cluster '" + name + "' is not visible" + (" in that subscription" if scoped else "")
                                + "; use exact names from list_clusters" + (" (similar: " + ", ".join(close) + ")." if close else "."), "parameters")
        config = next(iter(matches.values()))
        if config["id"].lower() in seen:
            raise EvidenceError("invalid_parameter", "Select distinct clusters only; '" + name + "' is repeated.", "parameters")
        seen.add(config["id"].lower())
        selected.append(config)
    return selected


def selection_configs(cluster_name, cluster_names, subscription="", operation="report"):
    """Returns (selected configs, visible configs after the subscription filter). Selection is local and exact."""
    roster = active_roster()
    if not isinstance(roster, dict) or not 1 <= len(roster) <= MAX_APPROVED_CLUSTERS:
        raise EvidenceError("configuration_required", "Configure one to " + str(MAX_APPROVED_CLUSTERS) + " fixed approved clusters.", "configuration")
    configured = [validate_config(name) for name in roster]
    if len({config["id"].lower() for config in configured}) != len(configured):
        raise EvidenceError("configuration_required", "Two allowlist entries point to the same AKS resource ID.", "configuration")
    visible = subscription_filter(configured, subscription)
    if operation == "list_clusters":
        return visible, visible
    if cluster_name:
        selected = resolve_names([cluster_name], visible, bool(subscription))
    elif cluster_names and cluster_names.lower() != "all":
        selected = resolve_names(cluster_names.split(","), visible, bool(subscription))
    elif operation == "query" and len(visible) > 1:
        raise EvidenceError("selection_required", "query reads one cluster (or up to " + str(MAX_QUERY_CLUSTERS) + " in cluster_names); "
                            + str(len(visible)) + " are visible. Use cluster_name, or operation=report for all of them.", "parameters")
    else:
        selected = visible
    limit = MAX_QUERY_CLUSTERS if operation == "query" else MAX_REPORT_CLUSTERS
    if len(selected) > limit:
        counts = Counter(config.get("subscription_name") or config["subscription_id"] for config in selected)
        raise EvidenceError("too_many_clusters", str(len(selected)) + " clusters selected; " + operation + " accepts at most " + str(limit)
                            + ". Narrow it with subscription=<name or ID> or cluster_names (largest subscriptions: "
                            + ", ".join(name[:40] + " " + str(count) for name, count in counts.most_common(4)) + ").", "parameters")
    return selected, visible


def list_clusters_page(configured, limit, offset, subscription=""):
    """Paged discovered roster (inventory, not observed health) that always fits the 3500-byte transport budget."""
    rows = []
    for config in configured:
        row = {"cluster_name": config["name"], "resource_group": config["resource_group"],
               "subscription_id": config["subscription_id"], "subscription_name": config.get("subscription_name"),
               "location": config.get("location"), "environment": config["environment"]}
        if config["aks_name"] != config["name"]:
            row["aks_name"] = config["aks_name"]
        if len(configured) <= 5:
            row["cluster_id"] = config["id"]
        rows.append(row)
    page = rows[offset:offset + limit]
    response = {"status": "ok", "operation": "list_clusters", "fresh_collection": False,
                "roster_basis": "observed_inventory_azure_resource_graph_plus_operator_entries" if DISCOVERY_INFO
                else "fixed_operator_configuration_not_observed_inventory",
                "total": len(rows), "subscription_count": len({row["subscription_id"] for row in rows}),
                "offset": offset, "returned": 0, "next_offset": None,
                "report_batch_limit": MAX_REPORT_CLUSTERS, "available_clusters": page}
    if subscription:
        response["subscription_filter"] = subscription.strip()[:128]
    if DISCOVERY_INFO:
        response["discovery"] = dict(DISCOVERY_INFO)
    while True:
        response["returned"] = len(response["available_clusters"])
        end = offset + response["returned"]
        response["next_offset"] = end if end < len(rows) else None
        if response_bytes(response) <= TRANSPORT_BYTES or len(response["available_clusters"]) <= 1:
            return ensure_response(response)
        response["available_clusters"] = response["available_clusters"][:-1]


CLUSTER_NAMES_PATTERN = re.compile(r"[A-Za-z0-9_.()-]{1,63}(?:,[A-Za-z0-9_.()-]{1,63}){0,99}")


def validate_parameters(operation, view, cluster_name, namespace, workload_name, area, level, severity, status, limit, offset, cluster_names="",
                        subscription=""):
    for key, value, choices in (
        ("operation", operation, ("report", "query", "list_clusters")), ("view", view, VIEWS),
        ("area", area, ("all",) + AREAS), ("level", level, ("all",) + LEVELS),
        ("severity", severity, ("all",) + SEVERITIES), ("status", status, ("all",) + CHECK_STATUSES + SOURCE_STATUSES),
    ):
        if value not in choices:
            raise EvidenceError("invalid_parameter", key + " must use its declared enum.", "parameters")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise EvidenceError("invalid_parameter", "limit must be an integer from 1 to 100.", "parameters")
    if isinstance(offset, bool) or not isinstance(offset, int) or not 0 <= offset <= 500000:
        raise EvidenceError("invalid_parameter", "offset must be an integer from 0 to 500000.", "parameters")
    for key, value, maximum in (("cluster_name", cluster_name, 63), ("namespace", namespace, 63), ("workload_name", workload_name, 253)):
        if not isinstance(value, str) or len(value) > maximum or (value and not re.fullmatch(r"[A-Za-z0-9_.()-]+", value)):
            raise EvidenceError("invalid_parameter", key + " is a bounded exact local name, not a path, URL or command.", "parameters")
    if not isinstance(cluster_names, str) or len(cluster_names) > 6400 or (
        cluster_names and cluster_names.lower() != "all" and not CLUSTER_NAMES_PATTERN.fullmatch(cluster_names)
    ):
        raise EvidenceError("invalid_parameter", "cluster_names is 'all' or 1 to " + str(MAX_REPORT_CLUSTERS)
                            + " exact comma-separated cluster names, without spaces.", "parameters")
    if not isinstance(subscription, str) or len(subscription) > 128 or re.search(r"[\x00-\x1f\x7f<>]", subscription) or (
        subscription and not subscription.strip()
    ):
        raise EvidenceError("invalid_parameter", "subscription is an exact subscription ID or display name (up to 128 plain characters).", "parameters")
    if cluster_name and cluster_names:
        raise EvidenceError("invalid_combination", "Use cluster_name or cluster_names, not both.", "parameters")
    filters = any((namespace, workload_name, area != "all", level != "all", severity != "all", status != "all"))
    if operation == "report" and (view != "summary" or filters or limit != 25 or offset != 0):
        raise EvidenceError("invalid_combination", "report cannot be narrowed by query filters or paging.", "parameters")
    if operation == "list_clusters" and (view != "summary" or filters):
        raise EvidenceError("invalid_combination", "list_clusters accepts only subscription and limit/offset paging, not query filters.", "parameters")
    if operation == "list_clusters" and (cluster_name or cluster_names):
        raise EvidenceError("invalid_combination", "list_clusters lists the visible roster; filter with subscription, not cluster names.", "parameters")
    if operation == "query":
        if view in ("summary", "cluster", "node_pools", "coverage", "architecture") and (namespace or workload_name):
            raise EvidenceError("invalid_combination", "Namespace/workload filters do not apply to this view.", "parameters")
        if view not in ("findings", "actions") and any((area != "all", level != "all", severity != "all")):
            raise EvidenceError("invalid_combination", "Area/level/severity filters apply only to rule assessments or actions.", "parameters")
        if status != "all" and (
            (view == "coverage" and status not in SOURCE_STATUSES)
            or (view in ("findings", "actions") and status not in CHECK_STATUSES)
            or view not in ("coverage", "findings", "actions")
        ):
            raise EvidenceError("invalid_combination", "Status does not belong to the selected view.", "parameters")
    return dict(operation=operation, view=view, cluster_name=cluster_name, namespace=namespace, workload_name=workload_name,
                area=area, level=level, severity=severity, status=status, limit=limit, offset=offset, cluster_names=cluster_names,
                subscription=subscription)


def quantity(value, unit):
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > 64:
        raise EvidenceError("invalid_quantity", "Kubernetes quantity must be a bounded string.", "normalization")
    match = re.fullmatch(r"([+-]?(?:\d+(?:\.\d*)?|\.\d+))([eE][+-]?\d+|[numkKMGTPE]|[KMGTPE]i)?", value)
    if not match:
        raise EvidenceError("invalid_quantity", "Invalid Kubernetes quantity; no zero substitution.", "normalization")
    suffix = match[2] or ""
    factors = {"": Decimal(1), "n": Decimal("1e-9"), "u": Decimal("1e-6"), "m": Decimal("1e-3"),
               "k": Decimal("1e3"), "K": Decimal("1e3"), "M": Decimal("1e6"), "G": Decimal("1e9"),
               "T": Decimal("1e12"), "P": Decimal("1e15"), "E": Decimal("1e18")}
    try:
        if suffix.startswith(("e", "E")) and len(suffix) > 1:
            exponent = int(suffix[1:])
            if not -30 <= exponent <= 30:
                raise InvalidOperation
            factor = Decimal(10) ** exponent
        else:
            factor = Decimal(2) ** (10 * ("KMGTPE".index(suffix[0]) + 1)) if suffix.endswith("i") else factors[suffix]
        result = Decimal(match[1]) * factor
        if not result.is_finite() or result < 0 or result > Decimal("1e30"):
            raise InvalidOperation
    except (InvalidOperation, KeyError, ValueError, OverflowError) as exc:
        raise EvidenceError("invalid_quantity", "Kubernetes quantity exceeds the finite nonnegative safety bound.", "normalization") from exc
    if unit == "bytes":
        return int(result.to_integral_value(rounding="ROUND_CEILING"))
    if unit == "cores":
        return float(result)
    raise EvidenceError("invalid_quantity_unit", "Quantity unit must be bytes or cores.", "normalization")


def source_receipt(source_id, reference, status="complete", note="", **extra):
    return {"id": source_id, "status": status, "time": reference, "records": 0, "pages": 0, "errors": [],
            "note": note, "window": None, **extra}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Identity:
    def __init__(self):
        try:
            from azure.identity import ManagedIdentityCredential
        except ImportError as exc:
            raise EvidenceError("dependency_missing", "Live reads require azure-identity; no cached-login fallback.", "identity") from exc
        self.credential = ManagedIdentityCredential(client_id=MANAGED_IDENTITY_CLIENT_ID)
        self.deadline = time.monotonic() + MAX_COLLECTION_SECONDS
        self.request_count = 0

    def token(self, audience):
        from azure.core.exceptions import ClientAuthenticationError, ServiceRequestError
        from azure.identity import CredentialUnavailableError
        if time.monotonic() >= self.deadline:
            raise EvidenceError("collection_deadline", "Collection elapsed-time bound reached; remaining reads are unavailable, not healthy.", "collection")
        if self.request_count >= MAX_HTTP_ATTEMPTS:
            raise EvidenceError("request_cap", "Collection HTTP-attempt bound reached; no narrower success is substituted.", "collection")
        self.request_count += 1
        try:
            token = self.credential.get_token(audience.rstrip("/") + "/.default").token
        except (ClientAuthenticationError, CredentialUnavailableError, ServiceRequestError) as exc:
            raise EvidenceError("authentication_failed", "The explicitly selected managed identity could not acquire a token.", "identity") from exc
        try:
            encoded = token.split(".")[1]
            claims = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
            claims = normalize_sidecar_claims(claims)
        except (AttributeError, IndexError, ValueError, binascii.Error) as exc:
            raise EvidenceError("authentication_failed", "Managed identity returned an unreadable token; token contents are excluded.", "identity") from exc
        tenant, client, token_audience = pick(claims, "tid"), pick(claims, "appid") or pick(claims, "azp"), pick(claims, "aud")
        if not (
            isinstance(tenant, str) and tenant.lower() == TENANT_ID.lower()
            and isinstance(client, str) and client.lower() == MANAGED_IDENTITY_CLIENT_ID.lower()
            and isinstance(token_audience, str) and token_audience.rstrip("/") == audience.rstrip("/")
        ):
            raise EvidenceError("identity_mismatch", "Token tenant, client identity or audience differs from the fixed configuration.", "identity")
        return token

    def close(self):
        self.credential.close()


class HttpReader:
    def __init__(self, identity, origin=ARM_ORIGIN, audience=ARM_ORIGIN, context=None):
        self.identity, self.origin, self.audience = identity, origin, audience
        self.context = context or ssl.create_default_context()
        if self.context.verify_mode != ssl.CERT_REQUIRED or not self.context.check_hostname:
            raise EvidenceError("unsafe_tls", "TLS peer and hostname validation are mandatory.", "tls")
        self.opener = build_opener(NoRedirect(), HTTPSHandler(context=self.context))
        self.allowed = set()

    def allow(self, url, method="GET"):
        parsed = urlsplit(url)
        if parsed.scheme != "https" or (parsed.scheme + "://" + parsed.netloc) != self.origin or parsed.fragment or parsed.username:
            raise EvidenceError("unsafe_endpoint", "Read URL changed the fixed HTTPS origin.", "scope")
        if method not in ("GET", "POST"):
            raise EvidenceError("unsafe_method", "Only enumerated reads and three fixed read-only POST operations are permitted.", "scope")
        self.allowed.add((method, parsed.path))
        return url

    def request(self, method, url, source, body=None, allow_empty=False, attempts=None, max_wait=None):
        parsed = urlsplit(url)
        if (
            parsed.scheme + "://" + parsed.netloc != self.origin or parsed.fragment or parsed.username or parsed.password
            or len(url) > 16384 or (method, parsed.path) not in self.allowed
        ):
            raise EvidenceError("unsafe_endpoint", "Request was not one of the scoped allowlisted reads.", source)
        if method == "POST" and not (
            parsed.path.lower().endswith("/listclusterusercredential")
            or parsed.path.lower().endswith("/providers/microsoft.costmanagement/query")
            or parsed.path.lower() == "/providers/microsoft.resourcegraph/resources"
        ):
            raise EvidenceError("unsafe_method", "This POST is not an enumerated read-only operation.", source)
        payload = None if body is None else json.dumps(body, allow_nan=False).encode("utf-8")
        cost_query = parsed.path.lower().endswith("/providers/microsoft.costmanagement/query")
        attempts = attempts or (COST_RETRY_ATTEMPTS if cost_query else 3)
        max_wait = max_wait or (COST_MAX_RETRY_WAIT_SECONDS if cost_query else 5)
        for attempt in range(attempts):
            request = Request(url, data=payload, method=method, headers={
                "Authorization": "Bearer " + self.identity.token(self.audience),
                "Accept": "application/json", "Content-Type": "application/json",
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
                if exc.code in (429, 500, 502, 503, 504) and attempt < attempts - 1:
                    delay = min(retry_delay(exc.headers, attempt), max_wait)
                    deadline = getattr(self.identity, "deadline", None)
                    if isinstance(deadline, (int, float)) and time.monotonic() + delay >= deadline:
                        raise EvidenceError("throttled" if exc.code == 429 else "http_error", "Read returned HTTP " + str(exc.code)
                                            + "; waiting " + str(delay) + " s would pass the time bound. Not collected, not zero.", source, exc.code) from exc
                    time.sleep(delay)
                    continue
                raise EvidenceError("access_denied" if exc.code in (401, 403) else "http_error",
                                    "Read returned HTTP " + str(exc.code) + "; response bodies are excluded.", source, exc.code) from exc
            except (URLError, TimeoutError, ssl.SSLError, OSError) as exc:
                reason = getattr(exc, "reason", exc)
                code = "tls_failed" if isinstance(reason, ssl.SSLError) else "transport_failed"
                raise EvidenceError(code, "Read transport/TLS failed; no insecure retry or alternate identity.", source) from exc
            try:
                return obj(json.loads(raw), source)
            except (ValueError, UnicodeDecodeError) as exc:
                raise EvidenceError("invalid_json", "Source returned invalid JSON; no raw body is exported.", source) from exc
        raise EvidenceError("http_error", "Bounded retries exhausted.", source)


def retry_delay(headers, attempt):
    """Largest Retry-After style hint (Cost Management sends x-ms-ratelimit-microsoft.costmanagement-*-retry-after)."""
    hints = []
    for key, value in (headers.items() if headers else []):
        if key.lower() == "retry-after" or (key.lower().startswith("x-ms-ratelimit-") and key.lower().endswith("retry-after")):
            if re.fullmatch(r"\s*[0-9]{1,5}\s*", str(value)):
                hints.append(int(value))
    return max(hints) if hints else attempt + 1


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


def read_pages(reader, url, source_id, reference, normalize, kubernetes=False, value_key="value", body=None,
               metrics_snapshot=False):
    receipt = source_receipt(source_id, reference, requested_page_size=KUBE_PAGE_SIZE if kubernetes else None,
                             page_cap=MAX_PAGES, row_cap=MAX_ROWS, pagination_complete=False,
                             read_signature=("POST" if body is not None else "GET") + " " + url)
    rows, seen_ids, seen_pages = [], set(), set()
    current, resource_version = url, None
    method = "POST" if body is not None else "GET"
    reader.allow(url, method)
    try:
        for page_number in range(MAX_PAGES):
            if current in seen_pages:
                raise EvidenceError("pagination_loop", "Source repeated a continuation.", source_id)
            seen_pages.add(current)
            payload = reader.request(method, current, source_id, body=body)
            receipt["pages"] = page_number + 1
            if body is not None:
                payload = obj(payload.get("properties"), source_id)
            page = array(payload.get("items" if kubernetes else value_key), source_id)
            if len(rows) + len(page) > MAX_ROWS:
                raise EvidenceError("row_cap", "Source row safety cap reached; scope was not silently narrowed.", source_id)
            for raw in page:
                row = normalize(raw)
                identity = row.get("uid") or row.get("id") or row.get("resource_id")
                if not kubernetes and isinstance(identity, str):
                    identity = identity.lower()
                if not identity or identity in seen_ids:
                    raise EvidenceError("invalid_pagination", "Source row identity is absent or repeated.", source_id)
                seen_ids.add(identity)
                rows.append(row)
            receipt["records"] = len(rows)
            if kubernetes:
                metadata = obj(payload.get("metadata"), source_id)
                version = text(metadata.get("resourceVersion"), source_id, 256)
                if (not version and not metrics_snapshot) or (resource_version is not None and version != resource_version):
                    raise EvidenceError("inconsistent_resource_version", "Kubernetes list resourceVersion changed or is absent.", source_id)
                resource_version = version
                receipt["resource_version"] = version
                if metrics_snapshot:
                    receipt["note"] = "Aggregated metrics API snapshot; resourceVersion may be unavailable, not a transactional inventory cursor."
                continuation = metadata.get("continue")
                remaining = metadata.get("remainingItemCount")
                if remaining is not None and (isinstance(remaining, bool) or not isinstance(remaining, int) or remaining < 0):
                    raise EvidenceError("invalid_pagination", "Invalid remainingItemCount.", source_id)
                receipt["remaining_item_count"] = remaining
                if not continuation:
                    if remaining not in (None, 0):
                        raise EvidenceError("missing_continuation", "Remaining Kubernetes records have no continuation.", source_id)
                    receipt["pagination_complete"] = True
                    return rows, receipt
                text(continuation, source_id, 8192)
                current = url.split("?")[0] + "?" + urlencode({"limit": KUBE_PAGE_SIZE, "continue": continuation})
            else:
                continuation = payload.get("nextLink")
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


def read_one(reader, url, source_id, reference, normalize):
    receipt = source_receipt(source_id, reference, pages=1, read_signature="GET " + url)
    try:
        reader.allow(url)
        result = normalize(reader.request("GET", url, source_id))
        receipt["records"] = 1
        return result, receipt
    except EvidenceError as exc:
        receipt.update(status="denied" if exc.http_status in (401, 403) else "error", records=0, errors=[exc.public()])
        return None, receipt


def common_row(raw, source_id, reference, config, kubernetes=False, metrics_snapshot=False):
    raw = obj(raw, source_id)
    if kubernetes:
        metadata = obj(raw.get("metadata"), source_id)
        uid = text(metadata.get("uid"), source_id, 256)
        name = text(metadata.get("name"), source_id, 253)
        if not name or (not uid and not metrics_snapshot):
            raise EvidenceError("invalid_record", "Kubernetes object requires name and UID.", source_id)
        owners = metadata.get("ownerReferences", [])
        owners = [{"kind": text(r.get("kind"), source_id), "name": text(r.get("name"), source_id),
                   "uid": text(r.get("uid"), source_id), "controller": boolean(r.get("controller"), source_id)}
                  for r in array(owners, source_id)]
        return {"name": name, "uid": uid, "id": ("metrics:" + str(metadata.get("namespace") or "") + "/" + name) if metrics_snapshot else None,
                "kind": text(raw.get("kind"), source_id),
                "namespace": text(metadata.get("namespace"), source_id, 63), "resource_id": config["id"],
                "labels": labels(metadata.get("labels"), source_id), "owner_references": owners,
                "resource_version": text(metadata.get("resourceVersion"), source_id),
                "source_id": source_id, "observed_at": reference, "cluster_name": config["name"], "cluster_id": config["id"]}
    resource_id = arm_id(raw.get("id"), scope_subscription(config))
    return {"id": resource_id, "resource_id": resource_id, "name": text(raw.get("name"), source_id),
            "resource_type": text(raw.get("type"), source_id), "region": text(raw.get("location"), source_id),
            "source_id": source_id, "observed_at": reference, "cluster_name": config["name"], "cluster_id": config["id"]}


def normalize_pool(raw, source_id, reference, config):
    row = common_row(raw, source_id, reference, config)
    properties = obj(raw.get("properties"), source_id)
    for output, field in {
        "mode": "mode", "vm_size": "vmSize", "version": "currentOrchestratorVersion",
        "os_type": "osType", "os_sku": "osSKU", "os_disk_type": "osDiskType", "provisioning_state": "provisioningState",
        "vnet_subnet_id": "vnetSubnetID", "pod_subnet_id": "podSubnetID", "scale_down_mode": "scaleDownMode",
        "priority": "scaleSetPriority",
    }.items():
        row[output] = text(properties.get(field), source_id)
    if row["version"] is None:
        row["version"] = text(properties.get("orchestratorVersion"), source_id)
    for output, field in {"count": "count", "min_count": "minCount", "max_count": "maxCount", "max_pods": "maxPods"}.items():
        row[output] = number(properties.get(field), source_id)
    row["enable_auto_scaling"] = boolean(properties.get("enableAutoScaling"), source_id)
    row["power_state"] = text(pick(properties, "powerState", "code"), source_id)
    row["os_disk_size_gb"] = number(properties.get("osDiskSizeGB"), source_id)
    row["vm_set_type"] = text(properties.get("type"), source_id)
    row["availability_zones"] = strings(properties.get("availabilityZones"), source_id)
    row["node_taints"] = strings(properties.get("nodeTaints"), source_id)
    row["upgrade_settings"] = {
        "max_surge": text(pick(properties, "upgradeSettings", "maxSurge"), source_id),
        "drain_timeout_minutes": number(pick(properties, "upgradeSettings", "drainTimeoutInMinutes"), source_id),
    }
    return row


def normalize_cluster(raw, source_id, reference, config):
    row = common_row(raw, source_id, reference, config)
    if row["id"].lower() != config["id"].lower():
        raise EvidenceError("scope_mismatch", "ARM returned a different cluster ID.", source_id)
    properties = obj(raw.get("properties"), source_id)
    # The report identity is the unique selection name (prefixed when the same AKS name exists in several subscriptions).
    row.update(aks_name=row["name"], name=config["name"], subscription_name=config.get("subscription_name"), location=config.get("location"))
    row.update(resource_group=config["resource_group"], subscription_id=scope_subscription(config),
               version=text(properties.get("currentKubernetesVersion") or properties.get("kubernetesVersion"), source_id),
               power_state=text(pick(properties, "powerState", "code"), source_id),
               provisioning_state=text(properties.get("provisioningState"), source_id),
               sku_tier=text(pick(raw, "sku", "tier"), source_id),
               mode=text(pick(raw, "sku", "name"), source_id),
               node_resource_group=text(properties.get("nodeResourceGroup"), source_id, 90),
               identity_type=text(pick(raw, "identity", "type"), source_id),
               enable_rbac=boolean(properties.get("enableRBAC"), source_id),
               managed_entra=boolean(pick(properties, "aadProfile", "managed"), source_id),
               azure_rbac=boolean(pick(properties, "aadProfile", "enableAzureRBAC"), source_id),
               disable_local_accounts=boolean(properties.get("disableLocalAccounts"), source_id),
               workload_identity_enabled=boolean(pick(properties, "securityProfile", "workloadIdentity", "enabled"), source_id),
               oidc_enabled=boolean(pick(properties, "oidcIssuerProfile", "enabled"), source_id),
               defender_enabled=boolean(pick(properties, "securityProfile", "defender", "securityMonitoring", "enabled"), source_id),
               private_cluster=boolean(pick(properties, "apiServerAccessProfile", "enablePrivateCluster"), source_id),
               authorized_ip_ranges=strings(pick(properties, "apiServerAccessProfile", "authorizedIPRanges"), source_id),
               private_dns_zone=text(pick(properties, "apiServerAccessProfile", "privateDNSZone"), source_id),
               fqdn=text(properties.get("fqdn"), source_id), private_fqdn=text(properties.get("privateFQDN"), source_id),
               support_plan=text(properties.get("supportPlan"), source_id),
               node_provisioning_mode=text(pick(properties, "nodeProvisioningProfile", "mode"), source_id))
    row["network"] = {key: text(pick(properties, "networkProfile", native), source_id) for key, native in {
        "plugin": "networkPlugin", "plugin_mode": "networkPluginMode", "dataplane": "networkDataplane",
        "policy": "networkPolicy", "outbound_type": "outboundType", "load_balancer_sku": "loadBalancerSku",
        "service_cidr": "serviceCidr", "pod_cidr": "podCidr", "dns_service_ip": "dnsServiceIP",
    }.items()}
    row["auto_upgrade"] = {key: text(pick(properties, "autoUpgradeProfile", native), source_id)
                           for key, native in {"channel": "upgradeChannel", "node_os_channel": "nodeOSUpgradeChannel"}.items()}
    addons = properties.get("addonProfiles")
    row["addons"] = None if addons is None else {
        key: {"enabled": boolean(obj(value, source_id).get("enabled"), source_id)}
        for key, value in obj(addons, source_id).items() if key in (
            "azurepolicy", "omsagent", "azureKeyvaultSecretsProvider", "httpApplicationRouting", "ingressApplicationGateway")
    }
    kv_config = pick(properties, "addonProfiles", "azureKeyvaultSecretsProvider", "config")
    if kv_config is not None:
        value = obj(kv_config, source_id).get("enableSecretRotation")
        row["keyvault_secret_rotation"] = value if isinstance(value, bool) else (
            value.lower() == "true" if value in ("true", "false", "True", "False") else None)
    else:
        row["keyvault_secret_rotation"] = None
    row["storage_profile"] = {key: boolean(pick(properties, "storageProfile", native, "enabled"), source_id)
                              for key, native in {"disk_csi": "diskCSIDriver", "file_csi": "fileCSIDriver",
                                                  "snapshot_controller": "snapshotController"}.items()}
    row["effective_outbound_ip_ids"] = [value for value in (
        same_subscription_id(item.get("id"))
        for item in array(pick(properties, "networkProfile", "loadBalancerProfile", "effectiveOutboundIPs") or [], source_id)
    ) if value]
    row["kubelet_identity_resource_id"] = text(pick(properties, "identityProfile", "kubeletidentity", "resourceId"), source_id)
    row["identity"] = {
        "type": row["identity_type"], "principal_id": text(pick(raw, "identity", "principalId"), source_id),
        "user_assigned_resource_ids": [value for value in (
            same_subscription_id(item) for item in obj(pick(raw, "identity", "userAssignedIdentities") or {}, source_id)
        ) if value],
        "kubelet_principal_id": text(pick(properties, "identityProfile", "kubeletidentity", "objectId"), source_id),
    }
    embedded = properties.get("agentPoolProfiles")
    row["embedded_pool_profiles"] = None if embedded is None else [
        normalize_pool({"id": config["id"] + "/agentPools/" + text(item.get("name"), source_id),
                        "name": item.get("name"), "type": "Microsoft.ContainerService/managedClusters/agentPools", "properties": item},
                       source_id, reference, config) for item in array(embedded, source_id)
    ]
    return row


def normalize_containers(containers, source_id):
    result = []
    for container in array(containers, source_id):
        resources = obj(container.get("resources", {}), source_id)
        requests, limits = obj(resources.get("requests", {}), source_id), obj(resources.get("limits", {}), source_id)
        context = obj(container.get("securityContext", {}), source_id)
        image = text(container.get("image"), source_id, 2048)
        if image is not None and (
            not re.fullmatch(r"[A-Za-z0-9._:/@-]+", image) or "://" in image
            or ("@" in image and not re.fullmatch(r"[^@]+@(?:sha256:[0-9a-fA-F]{64}|sha512:[0-9a-fA-F]{128})", image))
        ):
            raise EvidenceError("invalid_image", "Image reference contains unsupported or credential-like syntax.", source_id)
        def probe_configured(key):
            value = container.get(key)
            return False if value is None else bool(obj(value, source_id))
        result.append({
            "name": text(container.get("name"), source_id, 253), "image": image,
            "requests": {"cpu": text(requests.get("cpu"), source_id), "memory": text(requests.get("memory"), source_id)},
            "limits": {"cpu": text(limits.get("cpu"), source_id), "memory": text(limits.get("memory"), source_id)},
            "request_cpu_cores": quantity(requests.get("cpu"), "cores"),
            "request_memory_bytes": quantity(requests.get("memory"), "bytes"),
            "limit_cpu_cores": quantity(limits.get("cpu"), "cores"),
            "limit_memory_bytes": quantity(limits.get("memory"), "bytes"),
            "readiness_probe": probe_configured("readinessProbe"), "liveness_probe": probe_configured("livenessProbe"),
            "startup_probe": probe_configured("startupProbe"),
            "ports": [number(port.get("containerPort"), source_id) for port in array(container.get("ports", []), source_id)],
            "security": {key: boolean(context.get(key), source_id)
                         for key in ("privileged", "allowPrivilegeEscalation", "runAsNonRoot", "readOnlyRootFilesystem")},
            "run_as_user": number(context.get("runAsUser"), source_id),
        })
    return result


def normalize_selector(value, source_id, map_selector=False):
    if value is None:
        return None
    selector = obj(value, source_id)
    if map_selector:
        return {"match_labels": labels(selector, source_id), "match_expressions": []}
    expressions = [
        {"key": text(item.get("key"), source_id), "operator": text(item.get("operator"), source_id),
         "values": strings(item.get("values", []), source_id)}
        for item in array(selector.get("matchExpressions", []), source_id)
    ]
    if any(item["operator"] not in ("In", "NotIn", "Exists", "DoesNotExist") or not item["key"] for item in expressions):
        raise EvidenceError("invalid_selector", "Unsupported selector expression; no guessed join.", source_id)
    if any((item["operator"] in ("In", "NotIn") and not item["values"])
           or (item["operator"] in ("Exists", "DoesNotExist") and item["values"]) for item in expressions):
        raise EvidenceError("invalid_selector", "Selector operator/value cardinality is invalid.", source_id)
    return {"match_labels": labels(selector.get("matchLabels", {}), source_id), "match_expressions": expressions}


def int_or_percent(value, source_id):
    if value is None:
        return None
    if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 1000000:
        return value
    if isinstance(value, str) and re.fullmatch(r"[0-9]{1,6}%", value):
        return value
    raise EvidenceError("invalid_field", "PDB value must be a bounded nonnegative integer or percentage, not arbitrary data.", source_id)


def metric_window_seconds(value, source_id):
    if value is None:
        return None
    value = text(value, source_id, 128)
    parts = re.findall(r"([0-9]+(?:\.[0-9]+)?)(ns|us|ms|s|m|h)", value)
    if not parts or "".join(amount + unit for amount, unit in parts) != value:
        raise EvidenceError("invalid_metric_window", "Metrics duration must be a bounded source duration, not an assumed month.", source_id)
    units = {"ns": 1e-9, "us": 1e-6, "ms": .001, "s": 1, "m": 60, "h": 3600}
    seconds = sum(float(amount) * units[unit] for amount, unit in parts)
    if not math.isfinite(seconds) or not 0 < seconds <= 86400:
        raise EvidenceError("invalid_metric_window", "Metrics window must be positive and at most one day.", source_id)
    return seconds


def metric_freshness(timestamp, window_seconds, reference, source_id):
    if timestamp is None or window_seconds is None:
        return None
    try:
        measured = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        declared = datetime.fromisoformat(reference.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EvidenceError("invalid_metric_time", "Metric timestamp is not a valid source time.", source_id) from exc
    if measured.tzinfo is None or declared.tzinfo is None:
        raise EvidenceError("invalid_metric_time", "Metric/source reference requires an explicit timezone.", source_id)
    return abs((declared - measured).total_seconds()) <= 300


def normalize_kube(raw, collection, source_id, reference, config):
    row = common_row(raw, source_id, reference, config, kubernetes=True, metrics_snapshot=collection in ("node_metrics", "pod_metrics"))
    expected_kind = {
        "namespaces": "Namespace", "nodes": "Node", "pods": "Pod", "services": "Service",
        "pvcs": "PersistentVolumeClaim", "pvs": "PersistentVolume", "resource_quotas": "ResourceQuota",
        "deployments": "Deployment", "statefulsets": "StatefulSet", "daemonsets": "DaemonSet", "replicasets": "ReplicaSet",
        "jobs": "Job", "cronjobs": "CronJob", "pdbs": "PodDisruptionBudget", "hpas": "HorizontalPodAutoscaler",
        "network_policies": "NetworkPolicy", "storage_classes": "StorageClass", "node_metrics": "NodeMetrics", "pod_metrics": "PodMetrics",
    }[collection]
    if row["kind"] not in (None, expected_kind):
        raise EvidenceError("unexpected_kubernetes_kind", "Object kind differs from the fixed collection endpoint.", source_id)
    row["kind"] = expected_kind
    spec, status = obj(raw.get("spec", {}), source_id), obj(raw.get("status", {}), source_id)
    row["resource_kind"] = collection
    if collection in ("deployments", "statefulsets", "daemonsets", "jobs", "cronjobs"):
        template = pick(spec, "jobTemplate", "spec", "template") if collection == "cronjobs" else spec.get("template")
        template = obj(template, source_id)
        pod_spec = obj(template.get("spec"), source_id)
        row.update(
            kind={"deployments": "Deployment", "statefulsets": "StatefulSet", "daemonsets": "DaemonSet",
                  "jobs": "Job", "cronjobs": "CronJob"}[collection],
            workload_name=row["name"], template_labels=labels(pick(template, "metadata", "labels"), source_id),
            containers=normalize_containers(pod_spec.get("containers"), source_id),
            init_containers=normalize_containers(pod_spec.get("initContainers", []), source_id),
            desired_replicas=number(spec.get("replicas", 1), source_id) if collection in ("deployments", "statefulsets") else (
                number(status.get("desiredNumberScheduled"), source_id) if collection == "daemonsets" else None),
            ready_replicas=number(status.get("readyReplicas"), source_id) if collection != "daemonsets"
                           else number(status.get("numberReady"), source_id),
            suspended=boolean(spec.get("suspend"), source_id),
            os_name=text(pick(pod_spec, "os", "name"), source_id),
            node_selector=labels(pod_spec.get("nodeSelector"), source_id),
            pod_security={key: boolean(pick(pod_spec, "securityContext", key), source_id) for key in ("runAsNonRoot",)},
            run_as_user=number(pick(pod_spec, "securityContext", "runAsUser"), source_id),
            pvc_names=[text(pick(volume, "persistentVolumeClaim", "claimName"), source_id)
                       for volume in array(pod_spec.get("volumes", []), source_id) if "persistentVolumeClaim" in volume],
        )
    elif collection == "pods":
        row.update(node_name=text(spec.get("nodeName"), source_id), phase=text(status.get("phase"), source_id),
                   containers=normalize_containers(spec.get("containers"), source_id),
                   init_containers=normalize_containers(spec.get("initContainers", []), source_id),
                   pvc_names=[text(pick(v, "persistentVolumeClaim", "claimName"), source_id)
                              for v in array(spec.get("volumes", []), source_id) if "persistentVolumeClaim" in v])
    elif collection == "nodes":
        row["pool_name"] = pick(row, "labels", "kubernetes.azure.com/agentpool") or pick(row, "labels", "agentpool")
        row["provider_id"] = text(spec.get("providerID"), source_id, 2048)
        row["capacity"] = {key: quantity(pick(status, "capacity", key), unit)
                           for key, unit in (("cpu", "cores"), ("memory", "bytes"))}
        row["allocatable"] = {key: quantity(pick(status, "allocatable", key), unit)
                              for key, unit in (("cpu", "cores"), ("memory", "bytes"))}
        row["conditions"] = [{key: text(c.get(key), source_id) for key in ("type", "status", "lastTransitionTime", "reason")}
                             for c in array(status.get("conditions", []), source_id)]
    elif collection == "services":
        row.update(service_type=text(spec.get("type"), source_id), selector=normalize_selector(spec.get("selector"), source_id, True),
                   cluster_ip=text(spec.get("clusterIP"), source_id),
                   load_balancer_ingress=[{key: text(v.get(key), source_id) for key in ("ip", "hostname")}
                                          for v in array(pick(status, "loadBalancer", "ingress") or [], source_id)],
                   internal_load_balancer=text(pick(raw, "metadata", "annotations", "service.beta.kubernetes.io/azure-load-balancer-internal"), source_id, 5),
                   ports=[{"name": text(p.get("name"), source_id), "port": number(p.get("port"), source_id),
                           "protocol": text(p.get("protocol"), source_id), "node_port": number(p.get("nodePort"), source_id),
                           "target_port": text(p.get("targetPort"), source_id) if isinstance(p.get("targetPort"), str)
                           else number(p.get("targetPort"), source_id)} for p in array(spec.get("ports", []), source_id)])
        annotation_keys = (
            "service.beta.kubernetes.io/azure-load-balancer-internal",
            "service.beta.kubernetes.io/azure-load-balancer-internal-subnet",
            "service.beta.kubernetes.io/azure-load-balancer-resource-group",
            "service.beta.kubernetes.io/azure-pip-name",
            "service.beta.kubernetes.io/azure-load-balancer-health-probe-request-path",
        )
        row["annotations"] = {key: text(value, source_id) for key, value in obj(pick(raw, "metadata", "annotations") or {}, source_id).items()
                              if key in annotation_keys}
    elif collection == "pdbs":
        row.update(selector=normalize_selector(spec.get("selector"), source_id),
                   min_available=int_or_percent(spec.get("minAvailable"), source_id),
                   max_unavailable=int_or_percent(spec.get("maxUnavailable"), source_id),
                   disruptions_allowed=number(status.get("disruptionsAllowed"), source_id),
                   current_healthy=number(status.get("currentHealthy"), source_id),
                   desired_healthy=number(status.get("desiredHealthy"), source_id))
    elif collection == "hpas":
        row.update(target={key: text(pick(spec, "scaleTargetRef", key), source_id) for key in ("apiVersion", "kind", "name")},
                   min_replicas=number(spec.get("minReplicas", 1), source_id), max_replicas=number(spec.get("maxReplicas"), source_id),
                   current_replicas=number(status.get("currentReplicas"), source_id), desired_replicas=number(status.get("desiredReplicas"), source_id),
                   metric_types=[text(item.get("type"), source_id) for item in array(spec.get("metrics", []), source_id)])
    elif collection == "network_policies":
        row.update(selector=normalize_selector(spec.get("podSelector"), source_id), policy_types=strings(spec.get("policyTypes"), source_id),
                   ingress_rule_count=len(array(spec.get("ingress", []), source_id)), egress_rule_count=len(array(spec.get("egress", []), source_id)))
    elif collection == "pvcs":
        row.update(storage_class=text(spec.get("storageClassName"), source_id), volume_name=text(spec.get("volumeName"), source_id),
                   access_modes=strings(spec.get("accessModes"), source_id), phase=text(status.get("phase"), source_id),
                   requested_storage=text(pick(spec, "resources", "requests", "storage"), source_id),
                   requested_bytes=quantity(pick(spec, "resources", "requests", "storage"), "bytes"))
    elif collection == "pvs":
        row.update(storage_class=text(spec.get("storageClassName"), source_id), phase=text(status.get("phase"), source_id),
                   capacity_bytes=quantity(pick(spec, "capacity", "storage"), "bytes"), reclaim_policy=text(spec.get("persistentVolumeReclaimPolicy"), source_id),
                   csi_driver=text(pick(spec, "csi", "driver"), source_id), csi_volume_handle=text(pick(spec, "csi", "volumeHandle"), source_id),
                   claim_ref={key: text(pick(spec, "claimRef", key), source_id) for key in ("namespace", "name", "uid")})
        row["csi_volume_attributes"] = {
            key: text(value, source_id) for key, value in obj(pick(spec, "csi", "volumeAttributes") or {}, source_id).items()
            if key in ("resourceGroup", "storageAccount", "shareName", "protocol")
        }
    elif collection == "storage_classes":
        row.update(provisioner=text(raw.get("provisioner"), source_id), volume_binding_mode=text(raw.get("volumeBindingMode"), source_id),
                   reclaim_policy=text(raw.get("reclaimPolicy"), source_id),
                   parameters={key: text(value, source_id) for key, value in obj(raw.get("parameters", {}), source_id).items()
                               if key.lower() in ("skuname", "kind", "cachingmode", "fstype", "location", "resourcegroup")})
    elif collection == "resource_quotas":
        row.update(hard={text(key, source_id): text(value, source_id) for key, value in obj(spec.get("hard", {}), source_id).items()},
                   used={text(key, source_id): text(value, source_id) for key, value in obj(status.get("used", {}), source_id).items()})
    elif collection in ("node_metrics", "pod_metrics"):
        timestamp, window = text(raw.get("timestamp"), source_id), text(raw.get("window"), source_id)
        seconds = metric_window_seconds(window, source_id)
        row.update(timestamp=timestamp, window=window, window_seconds=seconds, sample_count=1,
                   fresh_for_reference=metric_freshness(timestamp, seconds, reference, source_id),
                   units={"cpu": "cores", "memory": "bytes"})
        if collection == "node_metrics":
            row.update(cpu_cores=quantity(pick(raw, "usage", "cpu"), "cores"),
                       memory_bytes=quantity(pick(raw, "usage", "memory"), "bytes"),
                       cpu_quantity=text(pick(raw, "usage", "cpu"), source_id),
                       memory_quantity=text(pick(raw, "usage", "memory"), source_id))
        else:
            row["containers"] = [{"name": text(c.get("name"), source_id), "cpu_cores": quantity(pick(c, "usage", "cpu"), "cores"),
                                  "memory_bytes": quantity(pick(c, "usage", "memory"), "bytes"),
                                  "cpu_quantity": text(pick(c, "usage", "cpu"), source_id),
                                  "memory_quantity": text(pick(c, "usage", "memory"), source_id)}
                                 for c in array(raw.get("containers"), source_id)]
    return row


def normalize_resource(raw, source_id, reference, config, association):
    row = common_row(raw, source_id, reference, config)
    kind = resource_type(row["id"])
    if kind not in RESOURCE_APIS:
        raise EvidenceError("unsupported_resource_type", "Resource detail type is not in the fixed whitelist.", source_id)
    props = obj(raw.get("properties", {}), source_id)
    row.update(resource_kind=kind, association=association, sku_name=text(pick(raw, "sku", "name"), source_id),
               sku_tier=text(pick(raw, "sku", "tier"), source_id), provisioning_state=text(props.get("provisioningState"), source_id))
    fields = {
        "microsoft.compute/disks": ("diskState", "diskSizeGB", "encryption", "zones"),
        "microsoft.storage/storageaccounts": ("supportsHttpsTrafficOnly", "minimumTlsVersion", "allowBlobPublicAccess",
                                              "allowSharedKeyAccess", "publicNetworkAccess"),
        "microsoft.containerregistry/registries": ("publicNetworkAccess", "zoneRedundancy"),
        "microsoft.keyvault/vaults": ("enableRbacAuthorization", "enablePurgeProtection", "softDeleteRetentionInDays", "publicNetworkAccess"),
        "microsoft.network/publicipaddresses": ("ipAddress", "publicIPAllocationMethod"),
        "microsoft.network/privatednszones": ("numberOfRecordSets", "maxNumberOfRecordSets"),
        "microsoft.network/dnszones": ("numberOfRecordSets", "zoneType"),
    }
    row["configuration"] = {}
    for field in fields.get(kind, ()):
        value = props.get(field) if field != "zones" else raw.get("zones")
        if field == "encryption":
            row["configuration"][field] = {"type": text(pick(props, "encryption", "type"), source_id)}
        elif field == "zones":
            row["configuration"][field] = strings(value, source_id)
        elif isinstance(value, bool) or value is None:
            row["configuration"][field] = value
        elif isinstance(value, (int, float)):
            row["configuration"][field] = number(value, source_id)
        else:
            row["configuration"][field] = text(value, source_id)
    if kind == "microsoft.compute/disks":
        row.update(managed_by=text(raw.get("managedBy"), source_id), managed_by_present="managedBy" in raw,
                   managed_by_extended=strings(raw.get("managedByExtended"), source_id))
    if kind == "microsoft.compute/virtualmachinescalesets":
        row.update(capacity=number(pick(raw, "sku", "capacity"), source_id),
                   pool_tag=text(pick(raw, "tags", "aks-managed-poolName"), source_id),
                   cluster_tag=text(pick(raw, "tags", "aks-managed-cluster-name"), source_id))
        interfaces = array(pick(props, "virtualMachineProfile", "networkProfile", "networkInterfaceConfigurations") or [], source_id)
        row["subnet_ids"] = [text(pick(ip, "properties", "subnet", "id"), source_id)
                             for interface in interfaces for ip in array(pick(interface, "properties", "ipConfigurations") or [], source_id)
                             if pick(ip, "properties", "subnet", "id")]
        row["nsg_ids"] = [text(pick(interface, "properties", "networkSecurityGroup", "id"), source_id) for interface in interfaces
                          if pick(interface, "properties", "networkSecurityGroup", "id")]
        row["load_balancer_backend_pool_ids"] = [
            text(item.get("id"), source_id) for interface in interfaces
            for ip in array(pick(interface, "properties", "ipConfigurations") or [], source_id)
            for item in array(pick(ip, "properties", "loadBalancerBackendAddressPools") or [], source_id)
        ]
    if kind == "microsoft.containerregistry/registries":
        row["login_server"] = text(props.get("loginServer"), source_id, 512)
    if kind == "microsoft.managedidentity/userassignedidentities":
        row["principal_id"] = text(props.get("principalId"), source_id, 36)
    if kind == "microsoft.network/publicipaddresses":
        row.update(ip_configuration_id=text(pick(props, "ipConfiguration", "id"), source_id),
                   ip_configuration_present="ipConfiguration" in props,
                   nat_gateway_id=text(pick(props, "natGateway", "id"), source_id), nat_gateway_present="natGateway" in props)
    if kind == "microsoft.network/loadbalancers":
        row["frontends"] = [
            {"id": text(item.get("id"), source_id), "name": text(item.get("name"), source_id),
             "public_ip_id": text(pick(item, "properties", "publicIPAddress", "id"), source_id),
             "private_ip": text(pick(item, "properties", "privateIPAddress"), source_id),
             "subnet_id": text(pick(item, "properties", "subnet", "id"), source_id)}
            for item in array(props.get("frontendIPConfigurations", []), source_id)
        ]
        row["probes"] = [{"id": text(item.get("id"), source_id), "name": text(item.get("name"), source_id),
                          "request_path": text(pick(item, "properties", "requestPath"), source_id),
                          **{key: text(pick(item, "properties", key), source_id) if key == "protocol"
                             else number(pick(item, "properties", key), source_id) for key in ("protocol", "port", "intervalInSeconds")}}
                         for item in array(props.get("probes", []), source_id)]
        row["backend_pools"] = [
            {"id": text(item.get("id"), source_id), "name": text(item.get("name"), source_id),
             "ip_configuration_ids": [text(value.get("id"), source_id)
                                      for value in array(pick(item, "properties", "backendIPConfigurations") or [], source_id)],
             "addresses": [{"name": text(value.get("name"), source_id),
                            "ip_address": text(pick(value, "properties", "ipAddress"), source_id),
                            "virtual_network_id": text(pick(value, "properties", "virtualNetwork", "id"), source_id)}
                           for value in array(pick(item, "properties", "loadBalancerBackendAddresses") or [], source_id)]}
            for item in array(props.get("backendAddressPools", []), source_id)
        ]
        row["load_balancing_rules"] = [
            {"id": text(item.get("id"), source_id), "name": text(item.get("name"), source_id),
             "frontend_id": text(pick(item, "properties", "frontendIPConfiguration", "id"), source_id),
             "backend_pool_id": text(pick(item, "properties", "backendAddressPool", "id"), source_id),
             "backend_pool_ids": [text(value.get("id"), source_id)
                                  for value in array(pick(item, "properties", "backendAddressPools") or [], source_id)],
             "probe_id": text(pick(item, "properties", "probe", "id"), source_id),
             "protocol": text(pick(item, "properties", "protocol"), source_id),
             "frontend_port": number(pick(item, "properties", "frontendPort"), source_id),
             "backend_port": number(pick(item, "properties", "backendPort"), source_id)}
            for item in array(props.get("loadBalancingRules", []), source_id)
        ]
    if kind in ("microsoft.network/networkinterfaces", "microsoft.network/virtualnetworks/subnets"):
        row["public_ip_ids"] = [
            text(pick(item, "properties", "publicIPAddress", "id"), source_id)
            for item in array(props.get("ipConfigurations", []), source_id) if pick(item, "properties", "publicIPAddress", "id")
        ]
        row["nsg_id"] = text(pick(props, "networkSecurityGroup", "id"), source_id)
        row["address_prefixes"] = strings(props.get("addressPrefixes"), source_id)
        row["address_prefix"] = text(props.get("addressPrefix"), source_id)
        row["subnet_ids"] = [text(pick(item, "properties", "subnet", "id"), source_id)
                             for item in array(props.get("ipConfigurations", []), source_id) if pick(item, "properties", "subnet", "id")]
    if kind == "microsoft.network/virtualnetworks":
        row["subnet_ids"] = [text(item.get("id"), source_id) for item in array(props.get("subnets", []), source_id)]
        row["address_space"] = strings(pick(props, "addressSpace", "addressPrefixes"), source_id)
        row["dns_servers"] = strings(pick(props, "dhcpOptions", "dnsServers"), source_id)
    if kind == "microsoft.network/networksecuritygroups":
        row["security_rules"] = [
            {key: number(pick(item, "properties", key), source_id) if key == "priority"
             else strings(pick(item, "properties", key), source_id) if key.endswith("Prefixes") or key.endswith("Ranges")
             else text(pick(item, "properties", key), source_id)
             for key in ("priority", "direction", "access", "protocol", "sourceAddressPrefix", "sourceAddressPrefixes",
                         "destinationPortRange", "destinationPortRanges", "destinationAddressPrefix")}
            for item in array(props.get("securityRules", []), source_id)
        ]
    return row


def referenced_resource_ids(row):
    references = []
    for field in ("subnet_ids", "nsg_ids", "public_ip_ids", "load_balancer_backend_pool_ids"):
        references.extend((value, field) for value in row.get(field, []) if value)
    if row.get("nsg_id"):
        references.append((row["nsg_id"], "nsg_id"))
    for frontend in row.get("frontends", []):
        references.extend((frontend[field], "frontends." + field) for field in ("public_ip_id", "subnet_id") if frontend.get(field))
    if row.get("resource_kind") == "microsoft.network/virtualnetworks":
        references = [(value, field) for value, field in references if field != "subnet_ids"]
    if row.get("resource_kind") == "microsoft.network/virtualnetworks/subnets":
        references.append((re.split(r"/subnets/", row["id"], flags=re.IGNORECASE)[0], "parent_virtual_network_id"))
    for value, field in references:
        value = same_subscription_id(value)
        if not value:
            continue
        if resource_type(value) == "microsoft.network/loadbalancers/backendaddresspools":
            value = re.split(r"/backendaddresspools/", value, flags=re.IGNORECASE)[0]
        if resource_type(value) in RESOURCE_APIS:
            yield value, field


def normalize_registry_role(raw, source_id, reference, config, registry_id, principal_id):
    properties = obj(raw.get("properties"), source_id)
    scope = text(properties.get("scope"), source_id, 2048)
    assignment_id = text(raw.get("id"), source_id, 2048)
    principal = text(properties.get("principalId"), source_id, 36)
    role_id = text(properties.get("roleDefinitionId"), source_id, 2048)
    if not scope or not assignment_id or not principal or principal.lower() != principal_id.lower() or not (
        registry_id.lower() == scope.lower() or registry_id.lower().startswith(scope.lower().rstrip("/") + "/")
    ) or not re.fullmatch(re.escape(scope) + r"/providers/Microsoft\.Authorization/roleAssignments/[0-9a-f-]{36}",
                          assignment_id, re.IGNORECASE):
        raise EvidenceError("scope_mismatch", "Registry role metadata must match the fixed kubelet principal and registry/ancestor scope.", source_id)
    if not role_id or not re.fullmatch(
        r"/(?:subscriptions/" + re.escape(scope_subscription(config)) + r"/)?providers/Microsoft\.Authorization/roleDefinitions/[0-9a-f-]{36}",
        role_id, re.IGNORECASE,
    ):
        raise EvidenceError("invalid_role_definition", "Role metadata has an unexpected definition ID; no alternate scope is read.", source_id)
    return {"id": assignment_id, "resource_id": registry_id, "scope": scope, "principal_id": principal,
            "role_definition_id": role_id, "condition_present": bool(text(properties.get("condition"), source_id)),
            "source_id": source_id, "observed_at": reference, "cluster_id": config["id"], "cluster_name": config["name"],
            "effective_pull_permission_verified": False}


def kube_reader(arm, identity, cluster, config):
    if cluster["managed_entra"] is not True or cluster["enable_rbac"] is not True:
        raise EvidenceError("entra_required", "Kubernetes collection requires managed Entra and RBAC; non-Entra ClusterUser can be admin.", "kube_access")
    url = ARM_ORIGIN + config["id"] + "/listClusterUserCredential?" + urlencode({"api-version": AKS_API, "format": "exec"})
    arm.allow(url, "POST")
    payload = arm.request("POST", url, "kube_access", body={})
    configs = array(payload.get("kubeconfigs"), "kube_access")
    if len(configs) != 1:
        raise EvidenceError("invalid_kubeconfig", "Expected exactly one scoped clusterUser kubeconfig.", "kube_access")
    try:
        import yaml
    except ImportError as exc:
        raise EvidenceError("dependency_missing", "Kubernetes reads require PyYAML for safe kubeconfig parsing.", "kube_access") from exc
    value = configs[0].get("value")
    if not isinstance(value, str) or len(value) > 131072:
        raise EvidenceError("invalid_kubeconfig", "Credential response exceeded the bounded shape.", "kube_access")
    try:
        document = obj(yaml.safe_load(base64.b64decode(value, validate=True).decode("utf-8")), "kube_access")
    except (ValueError, UnicodeDecodeError, binascii.Error, yaml.YAMLError) as exc:
        raise EvidenceError("invalid_kubeconfig", "Invalid clusterUser configuration; credential material is never exported.", "kube_access") from exc
    contexts = array(document.get("contexts"), "kube_access")
    selected = [item for item in contexts if item.get("name") == document.get("current-context")]
    if len(selected) != 1:
        raise EvidenceError("invalid_kubeconfig", "Current context is not unique.", "kube_access")
    cluster_name = pick(selected[0], "context", "cluster")
    selected_clusters = [item for item in array(document.get("clusters"), "kube_access") if item.get("name") == cluster_name]
    if len(selected_clusters) != 1:
        raise EvidenceError("invalid_kubeconfig", "Selected TLS cluster is not unique.", "kube_access")
    for user in array(document.get("users", []), "kube_access"):
        if set(obj(user.get("user", {}), "kube_access")) & {
            "token", "tokenFile", "password", "username", "client-certificate", "client-certificate-data",
            "client-key", "client-key-data", "auth-provider",
        }:
            raise EvidenceError("local_credentials_rejected", "Local certificates, static tokens and authentication fallbacks are forbidden.", "kube_access")
    tls = obj(selected_clusters[0].get("cluster"), "kube_access")
    server = text(tls.get("server"), "kube_access", 512)
    try:
        parsed = urlsplit(server or "")
        port = parsed.port
    except ValueError as exc:
        raise EvidenceError("unsafe_kube_endpoint", "Malformed Kube HTTPS endpoint; no alternate server is used.", "kube_access") from exc
    hosts = {host.lower() for host in (cluster["fqdn"], cluster["private_fqdn"]) if host}
    if (
        parsed.scheme != "https" or parsed.hostname not in hosts or not parsed.hostname.endswith(".azmk8s.io")
        or port not in (None, 443) or parsed.path not in ("", "/") or parsed.query or parsed.fragment
        or parsed.username or parsed.password or tls.get("insecure-skip-tls-verify") or "certificate-authority" in tls
    ):
        raise EvidenceError("unsafe_kube_endpoint", "Kube server must exactly match the approved ARM cluster FQDN with strict inline CA TLS.", "kube_access")
    ca = tls.get("certificate-authority-data")
    if not isinstance(ca, str) or len(ca) > 65536:
        raise EvidenceError("unsafe_tls", "A bounded public CA from clusterUser is required; no file or insecure fallback.", "kube_access")
    try:
        ca_text = base64.b64decode(ca, validate=True).decode("ascii")
        context = ssl.create_default_context()
        context.load_verify_locations(cadata=ca_text)
    except (ValueError, UnicodeDecodeError, binascii.Error, ssl.SSLError) as exc:
        raise EvidenceError("unsafe_tls", "Cluster public CA could not initialize verified TLS.", "kube_access") from exc
    return HttpReader(identity, "https://" + parsed.hostname, AKS_AUDIENCE, context)


def collect_live(config, reference, deadline=None):
    """The collected cluster's subscription is thread-local, so parallel clusters in different subscriptions never mix scopes."""
    previous = getattr(COLLECTION_SCOPE, "subscription_id", None)
    COLLECTION_SCOPE.subscription_id = scope_subscription(config)
    try:
        return _collect_live(config, reference, deadline)
    finally:
        COLLECTION_SCOPE.subscription_id = previous


def _collect_live(config, reference, deadline=None):
    identity = Identity()
    try:
        if deadline is not None:
            identity.deadline = min(identity.deadline, deadline)
        arm = HttpReader(identity)
        raw = {"sources": [], "inventory": {}, "requirements": config["requirements"], "registry_role_assignments": []}
        cluster_url = ARM_ORIGIN + config["id"] + "?api-version=" + AKS_API
        cluster, receipt = read_one(arm, cluster_url, "arm_cluster", reference,
                                    lambda item: normalize_cluster(item, "arm_cluster", reference, config))
        raw["sources"].append(receipt)
        if cluster is None:
            error = receipt["errors"][0]
            raise EvidenceError(error["code"], "The approved primary cluster could not be read; no synthetic/empty live report.", "arm_cluster", error["http_status"])
        raw["cluster"] = cluster
        pools, receipt = read_pages(arm, ARM_ORIGIN + config["id"] + "/agentPools?api-version=" + AKS_API,
                                    "arm_node_pools", reference, lambda item: normalize_pool(item, "arm_node_pools", reference, config))
        raw["inventory"]["node_pools"] = pools
        raw["sources"].append(receipt)
        for key, suffix, version in (
            ("arm_maintenance", "/maintenanceConfigurations", AKS_API),
            ("arm_diagnostics", "/providers/Microsoft.Insights/diagnosticSettings", "2021-05-01-preview"),
        ):
            def normalized(item, source_id=key):
                row = common_row(item, source_id, reference, config)
                props = obj(item.get("properties"), source_id)
                if source_id == "arm_diagnostics":
                    row.update(logs=[{"category": text(log.get("category"), source_id), "category_group": text(log.get("categoryGroup"), source_id),
                                      "enabled": boolean(log.get("enabled"), source_id)} for log in array(props.get("logs", []), source_id)],
                               workspace_id=text(props.get("workspaceId"), source_id),
                               storage_account_id=text(props.get("storageAccountId"), source_id),
                               eventhub_authorization_rule_id=text(props.get("eventHubAuthorizationRuleId"), source_id))
                else:
                    row["configured"] = bool(props.get("maintenanceWindow") or props.get("timeInWeek") or props.get("notAllowedTime"))
                return row
            rows, receipt = read_pages(arm, ARM_ORIGIN + config["id"] + suffix + "?api-version=" + version,
                                      key, reference, normalized)
            raw[key] = rows
            raw["sources"].append(receipt)
        versions_url = (ARM_ORIGIN + "/subscriptions/" + scope_subscription(config) + "/providers/Microsoft.ContainerService/locations/"
                        + quote(cluster["region"] or "", safe="") + "/kubernetesVersions?api-version=" + AKS_API)
        def version_row(item):
            return {"id": text(item.get("version"), "arm_regional_versions"), "version": text(item.get("version"), "arm_regional_versions"),
                    "is_preview": boolean(item.get("isPreview"), "arm_regional_versions"),
                    "is_default": boolean(item.get("isDefault"), "arm_regional_versions"),
                    "support_plans": strings(pick(item, "capabilities", "supportPlan"), "arm_regional_versions"),
                    "patch_versions": {text(key, "arm_regional_versions"): {
                        "upgrades": strings(pick(value, "upgrades"), "arm_regional_versions")
                    } for key, value in obj(item.get("patchVersions", {}), "arm_regional_versions").items()}}
        raw["regional_versions"], receipt = read_pages(arm, versions_url, "arm_regional_versions", reference, version_row, value_key="values")
        raw["sources"].append(receipt)
        def upgrade_row(item):
            props = obj(item.get("properties"), "arm_upgrade_profile")
            profile = obj(props.get("controlPlaneProfile"), "arm_upgrade_profile")
            return {"version": text(profile.get("kubernetesVersion"), "arm_upgrade_profile"),
                    "upgrades": [{key: boolean(value.get(key), "arm_upgrade_profile") if key == "isPreview"
                                  else text(value.get(key), "arm_upgrade_profile") for key in ("kubernetesVersion", "isPreview")}
                                 for value in array(profile.get("upgrades", []), "arm_upgrade_profile")]}
        raw["upgrade_profile"], receipt = read_one(arm, ARM_ORIGIN + config["id"] + "/upgradeProfiles/default?api-version=" + AKS_API,
                                                   "arm_upgrade_profile", reference, upgrade_row)
        raw["sources"].append(receipt)
        related, inventory_receipt = [], source_receipt("arm_related_inventory", reference, "not_configured",
                                                       "Only approved IDs, directly referenced assets and the exact ARM nodeResourceGroup are in scope.")
        related_ids = {value.lower(): (value, {"type": "operator_scoped", "source_id": "configuration"})
                       for value in config["approved_related_resource_ids"]}
        for pool in pools:
            for field in ("vnet_subnet_id", "pod_subnet_id"):
                value = pool[field]
                if value and same_subscription_id(value):
                    related_ids[value.lower()] = (value, {"type": "direct_reference", "source_id": pool["source_id"], "field": field})
        for value in cluster["effective_outbound_ip_ids"]:
            related_ids[value.lower()] = (value, {"type": "direct_reference", "source_id": "arm_cluster", "field": "effective_outbound_ip_ids"})
        for field in ("private_dns_zone", "kubelet_identity_resource_id"):
            value = cluster.get(field)
            if value and value.startswith("/subscriptions/") and same_subscription_id(value):
                related_ids[value.lower()] = (value, {"type": "direct_reference", "source_id": "arm_cluster", "field": field})
        for value in cluster["identity"]["user_assigned_resource_ids"]:
            related_ids[value.lower()] = (value, {
                "type": "direct_reference", "source_id": "arm_cluster", "field": "identity.user_assigned_resource_ids"})
        node_rg = cluster["node_resource_group"]
        if config["include_node_resource_group"] and node_rg:
            if not re.fullmatch(r"[A-Za-z0-9_.()-]{1,90}", node_rg):
                raise EvidenceError("unsafe_scope", "ARM nodeResourceGroup has unsafe syntax.", "arm_related_inventory")
            url = ARM_ORIGIN + "/subscriptions/" + scope_subscription(config) + "/resourceGroups/" + node_rg + "/resources?api-version=2021-04-01"
            items, inventory_receipt = read_pages(arm, url, "arm_related_inventory", reference,
                                                   lambda item: common_row(item, "arm_related_inventory", reference, config))
            raw["inventory"]["related_resource_index"] = items
            for item in items:
                if resource_type(item["id"]) in RESOURCE_APIS:
                    related_ids.setdefault(item["id"].lower(), (item["id"], {"type": "node_resource_group_context", "source_id": "arm_cluster",
                                                                           "node_resource_group": node_rg}))
        raw["sources"].append(inventory_receipt)
        if len(related_ids) > MAX_RELATED_RESOURCES:
            raise EvidenceError("related_scope_cap", "Associated resource scope exceeds its bound; no narrowed report is substituted.", "arm_related_inventory")
        pending = list(related_ids.values())
        next_related = 0
        def queue_related(value, association):
            value = same_subscription_id(value)
            if not value:
                return
            if value.lower() in related_ids:
                return
            if len(related_ids) >= MAX_RELATED_RESOURCES:
                raise EvidenceError("related_scope_cap", "Exact referenced resource closure exceeds its bound; no narrowed report.", "arm_related_inventory")
            related_ids[value.lower()] = (value, association)
            pending.append((value, association))

        def read_related():
            nonlocal next_related
            while next_related < len(pending):
                resource_id, association = pending[next_related]
                next_related += 1
                kind = resource_type(resource_id)
                source_id = "arm_resource_" + str(next_related)
                if kind not in RESOURCE_APIS:
                    raw["sources"].append(source_receipt(source_id, reference, "not_applicable", "Approved resource type has no whitelisted detail reader."))
                    continue
                def normalized(item):
                    row = normalize_resource(item, source_id, reference, config, association)
                    if row["id"].lower() != resource_id.lower():
                        raise EvidenceError("scope_mismatch", "ARM detail response differs from the exact requested related resource.", source_id)
                    return row
                row, receipt = read_one(arm, ARM_ORIGIN + resource_id + "?api-version=" + RESOURCE_APIS[kind], source_id, reference, normalized)
                receipt["resource_id"] = resource_id
                raw["sources"].append(receipt)
                if row:
                    related.append(row)
                    for value, field in referenced_resource_ids(row):
                        queue_related(value, {"type": "direct_reference", "source_id": row["source_id"],
                                              "resource_id": row["id"], "field": field})
        read_related()
        for index, registry in enumerate(row for row in related if row["resource_kind"] == "microsoft.containerregistry/registries"):
            source_id = "arm_registry_roles_" + str(index + 1)
            principal = cluster["identity"]["kubelet_principal_id"]
            if not principal:
                raw["sources"].append(source_receipt(source_id, reference, "not_configured",
                    "No observed kubelet managed-identity principal; no arbitrary/personal identities are queried.", resource_id=registry["id"]))
                continue
            try:
                UUID(principal)
            except ValueError as exc:
                raise EvidenceError("invalid_principal_id", "Observed kubelet identity is not a GUID.", source_id) from exc
            url = ARM_ORIGIN + registry["id"] + "/providers/Microsoft.Authorization/roleAssignments?" + urlencode({
                "api-version": "2022-04-01", "$filter": "principalId eq '" + principal + "'"})
            rows, receipt = read_pages(arm, url, source_id, reference, lambda item: normalize_registry_role(
                item, source_id, reference, config, registry["id"], principal))
            receipt["resource_id"] = registry["id"]
            receipt["note"] += " Fixed kubelet-principal role metadata only; role definitions, conditions and effective data-plane image-pull access are not evaluated."
            raw["sources"].append(receipt)
            raw["registry_role_assignments"].extend(rows)
        raw["inventory"]["related_resources"] = related
        kube = None
        if config["kubernetes_enabled"] and cluster["power_state"] != "Stopped":
            try:
                kube = kube_reader(arm, identity, cluster, config)
                receipt = source_receipt("kube_access", reference, records=1, pages=1,
                                         note="Managed Entra clusterUser + ephemeral AKS-audience UAMI token; strict CA/FQDN TLS, GET only.")
            except EvidenceError as exc:
                receipt = source_receipt("kube_access", reference, "denied" if exc.http_status in (401, 403) else "error", errors=[exc.public()])
        else:
            receipt = source_receipt("kube_access", reference, "not_applicable" if cluster["power_state"] == "Stopped" else "not_configured",
                                     "Stopped clusters are never started; disabled collection does not imply an empty cluster.")
        raw["sources"].append(receipt)
        for collection, path in KUBE_PATHS.items():
            source_id = "kube_" + collection
            if kube is None:
                raw["inventory"][collection] = []
                raw["sources"].append(source_receipt(source_id, reference, receipt["status"],
                                                     "Kubernetes access was not established; no empty-success inference."))
                continue
            rows, page_receipt = read_pages(kube, kube.origin + path + "?limit=" + str(KUBE_PAGE_SIZE), source_id, reference,
                                            lambda item, c=collection, s=source_id: normalize_kube(item, c, s, reference, config), kubernetes=True,
                                            metrics_snapshot=collection in ("node_metrics", "pod_metrics"))
            raw["inventory"][collection] = rows
            raw["sources"].append(page_receipt)
        raw["inventory"]["workloads"] = [row for collection in ("deployments", "statefulsets", "daemonsets", "jobs", "cronjobs")
                                        for row in raw["inventory"][collection]]
        for pv in raw["inventory"]["pvs"]:
            handle = pv.get("csi_volume_handle")
            if pv.get("csi_driver") == "disk.csi.azure.com" and handle and handle.lower().startswith("/subscriptions/"):
                value = same_subscription_id(handle)
                if value and resource_type(value) == "microsoft.compute/disks":
                    queue_related(value, {"type": "direct_reference", "source_id": pv["source_id"],
                                          "kubernetes_uid": pv["uid"], "field": "csi_volume_handle"})
        read_related()
        advisor_source = source_receipt("arm_advisor", reference, "not_configured", "Cached recommendations only; no generateRecommendations action.")
        raw["advisor"] = []
        if config["advisor_enabled"]:
            url = ARM_ORIGIN + "/subscriptions/" + scope_subscription(config) + "/providers/Microsoft.Advisor/recommendations?" + urlencode({
                "api-version": "2025-01-01", "$filter": "ResourceId eq '" + config["id"] + "'", "$top": "100"})
            def advisor_row(item):
                advisory_id = text(item.get("id"), "arm_advisor", 2048)
                if not advisory_id or not advisory_id.lower().startswith("/subscriptions/" + scope_subscription(config).lower() + "/"):
                    raise EvidenceError("scope_mismatch", "Advisor ID changed subscription scope.", "arm_advisor")
                row = {"id": advisory_id, "resource_id": config["id"], "name": text(item.get("name"), "arm_advisor"),
                       "source_id": "arm_advisor", "observed_at": reference, "cluster_name": config["name"]}
                target = pick(item, "properties", "resourceMetadata", "resourceId")
                if not isinstance(target, str) or target.lower() != config["id"].lower():
                    raise EvidenceError("scope_mismatch", "Advisor returned a resource outside the exact cluster filter.", "arm_advisor")
                row.update(target_resource_id=target, category=text(pick(item, "properties", "category"), "arm_advisor"),
                           impact=text(pick(item, "properties", "impact"), "arm_advisor"),
                           last_updated=text(pick(item, "properties", "lastUpdated"), "arm_advisor"),
                           problem=text(pick(item, "properties", "shortDescription", "problem"), "arm_advisor"),
                           solution=text(pick(item, "properties", "shortDescription", "solution"), "arm_advisor"))
                return row
            raw["advisor"], advisor_source = read_pages(arm, url, "arm_advisor", reference, advisor_row)
        raw["sources"].append(advisor_source)
        raw["cost_rows"], cost_source = collect_cost(arm, config, reference, related, cluster)
        raw["sources"].append(cost_source)
        return raw
    finally:
        identity.close()


def collect_cost(reader, config, reference, related, cluster=None):
    ids = config["approved_cost_resource_ids"]
    declared = datetime.fromisoformat(reference.replace("Z", "+00:00"))
    monthly = config["cost_timeframe"] == "month_to_date"
    start_time = declared.replace(day=1, hour=0, minute=0, second=0, microsecond=0) if monthly else declared - timedelta(days=30)
    start = start_time.isoformat().replace("+00:00", "Z")
    mode = config["cost_scope"]
    receipt = source_receipt("azure_cost", reference, "not_configured", "No approved billing scope; no namespace/workload billing inference.",
                             window={"start": start, "end": reference}, timeframe="MonthToDate" if monthly else "Custom",
                             granularity="None" if monthly else "Daily", cost_type="ActualCost", unit="billing_currency", pagination_complete=False)
    if mode == "disabled":
        return [], receipt
    scope = "/subscriptions/" + scope_subscription(config)
    node_rg = pick(cluster, "node_resource_group")
    observed_cluster_id = pick(cluster, "id")
    if mode == "node_resource_group":
        if (
            not isinstance(node_rg, str) or not re.fullmatch(r"[A-Za-z0-9_.()-]{1,90}", node_rg)
            or not isinstance(observed_cluster_id, str) or observed_cluster_id.lower() != config["id"].lower()
        ):
            receipt.update(status="error", errors=[EvidenceError("unverified_cost_scope", "Billing nodeResourceGroup must come from the exact observed approved ARM cluster.", "azure_cost").public()])
            return [], receipt
        scope += "/resourceGroups/" + node_rg
        receipt["association"] = {"type": "node_resource_group_billing_context", "source_id": "arm_cluster", "node_resource_group": node_rg}
        receipt["note"] = "All returned billing rows in exact ARM-observed nodeResourceGroup, including historical/deleted/VMSS child IDs; not current inventory or workload ownership."
    else:
        observed_ids = {row["resource_id"].lower() for row in related} | {config["id"].lower()}
        if not ids or any(value.lower() not in observed_ids for value in ids):
            receipt.update(status="error", errors=[EvidenceError("unverified_cost_scope", "Fixed cost IDs must also be observed in the collected fixed inventory.", "azure_cost").public()])
            return [], receipt
        receipt["association"] = {"type": "approved_observed_resource_ids", "source_id": "configuration"}
    url = ARM_ORIGIN + scope + "/providers/Microsoft.CostManagement/query?api-version=2023-11-01"
    receipt.update(scope=scope, read_signature="POST " + url)
    reader.allow(url, "POST")
    body = {"type": "ActualCost", "timeframe": "MonthToDate" if monthly else "Custom",
            "dataset": {"granularity": "None" if monthly else "Daily",
                        "aggregation": {"totalCost": {"name": "PreTaxCost", "function": "Sum"}},
                        "grouping": [{"type": "Dimension", "name": "ResourceId"}]}}
    if not monthly:
        body["timePeriod"] = {"from": start, "to": reference}
    if mode == "resource_ids":
        body["dataset"]["filter"] = {"dimensions": {"name": "ResourceId", "operator": "In", "values": ids}}
    rows, seen = [], set()
    current = url
    acquired = False
    try:
        deadline = getattr(getattr(reader, "identity", None), "deadline", None)
        remaining = deadline - time.monotonic() if isinstance(deadline, (int, float)) else COST_SLOT_WAIT_SECONDS
        if remaining <= 0 or not COST_SLOTS.acquire(timeout=min(remaining, COST_SLOT_WAIT_SECONDS)):
            raise EvidenceError("collection_deadline", "No Cost Management query slot before the time bound; cost not collected, not zero.", "azure_cost")
        acquired = True
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
            receipt["columns"] = [{"name": name, "type": text(item.get("type"), "azure_cost", 32)} for name, item in zip(names, columns)]
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
                resource_id = arm_id(record["ResourceId"], scope_subscription(config))
                if (mode == "resource_ids" and resource_id.lower() not in {item.lower() for item in ids}) or (
                    mode == "node_resource_group" and resource_id.split("/")[4].lower() != node_rg.lower()
                ):
                    raise EvidenceError("scope_mismatch", "Cost query returned an unapproved resource ID.", "azure_cost")
                currency = text(record["Currency"], "azure_cost", 8)
                if not currency or not re.fullmatch(r"[A-Z]{3}", currency):
                    raise EvidenceError("invalid_currency", "Cost currency is not an observed ISO-style currency code.", "azure_cost")
                date = record.get("UsageDate")
                if date is not None:
                    if not re.fullmatch(r"\d{8}", str(date)):
                        raise EvidenceError("invalid_cost_date", "Cost UsageDate is not a dated daily row.", "azure_cost")
                    day = datetime.strptime(str(date), "%Y%m%d").replace(tzinfo=timezone.utc)
                    if not start_time.date() <= day.date() <= declared.date():
                        raise EvidenceError("cost_window_mismatch", "A cost row lies outside the requested UTC window.", "azure_cost")
                date = str(date) if date is not None else None
                key = (resource_id.lower(), date, currency)
                if any((r["resource_id"].lower(), r["usage_date"], r["currency"]) == key for r in rows):
                    raise EvidenceError("invalid_pagination", "Cost pagination repeated a resource/date/currency row.", "azure_cost")
                amount = number(record.get("PreTaxCost", record.get("Cost")), "azure_cost")
                if amount is None:
                    raise EvidenceError("invalid_cost_amount", "Cost amount is absent; it is not zero.", "azure_cost")
                rows.append({"resource_id": resource_id, "usage_date": date, "amount": amount,
                             "currency": currency, "source_id": "azure_cost", "observed_at": reference,
                             "cluster_name": config["name"], "window": receipt["window"], "association": receipt["association"],
                             "current_inventory_match": resource_id.lower() in {row["resource_id"].lower() for row in related},
                             "basis": "ActualCost/PreTaxCost in exact approved scope; billing history is not current inventory, cluster ownership or Kubernetes allocation"})
            receipt["records"] = len(rows)
            link = props.get("nextLink")
            if not link:
                receipt.update(status="complete", pagination_complete=True)
                return rows, receipt
            current = next_arm_link(link, url)
        raise EvidenceError("page_cap", "Cost query page safety cap reached.", "azure_cost")
    except (EvidenceError, ValueError) as exc:
        error = exc if isinstance(exc, EvidenceError) else EvidenceError("invalid_cost_date", "Cost date is not a valid calendar date.", "azure_cost")
        receipt.update(status="partial" if rows else "denied" if error.http_status in (401, 403) else "error",
                       records=len(rows), errors=[error.public()])
        return rows, receipt
    finally:
        if acquired:
            COST_SLOTS.release()


def selector_matches(selector, actual_labels):
    if selector is None or actual_labels is None:
        return None
    if any(actual_labels.get(key) != value for key, value in (selector.get("match_labels") or {}).items()):
        return False
    for expression in selector.get("match_expressions") or []:
        key, op, values = expression["key"], expression["operator"], expression["values"]
        if op == "In" and (key not in actual_labels or actual_labels[key] not in values):
            return False
        if op == "NotIn" and key in actual_labels and actual_labels[key] in values:
            return False
        if op == "Exists" and key not in actual_labels:
            return False
        if op == "DoesNotExist" and key in actual_labels:
            return False
    return True


def outcome(status, reason, value=None, source_ids=None):
    return {"status": status, "reason": reason, "value": value or {}, "source_ids": source_ids or []}


def decision(value, reason, observed, sources=None):
    return outcome("not_evaluated" if value is None else "passed" if value else "failed", reason, observed, sources)


def source_complete(raw, *ids):
    sources = {source["id"]: source for source in raw["sources"]}
    return all(pick(sources.get(source_id), "status") == "complete" for source_id in ids)


def expected(raw, key, row=None):
    requirements = raw.get("requirements", {})
    if row and row.get("namespace") and row.get("name"):
        values = pick(requirements, "workloads", row["namespace"] + "/" + row["name"])
        if isinstance(values, dict) and key in values:
            return values[key]
        if key in ("availability_required", "autoscaling_required", "probes_required"):
            return None
    return requirements.get(key)


def conditional(value, requirement, reason, observed, sources=None):
    if requirement is False:
        return outcome("not_applicable", "The confirmed requirement does not apply. " + reason, observed, sources)
    if value is True:
        return decision(True, reason + " Configuration observed; this does not prove effectiveness.", observed, sources)
    if requirement is not True:
        return outcome("not_evaluated", "No confirmed requirement or alternative control. " + reason, observed, sources)
    return decision(value, reason + " Requirement confirmed; an unknown absence does not become a failure.", observed, sources)


def serving_workload(raw, row):
    requirement = expected(raw, "probes_required", row)
    if requirement is not None:
        return requirement
    if not source_complete(raw, "kube_services"):
        return None
    for service in raw["inventory"].get("services", []):
        selector = service.get("selector")
        if service.get("namespace") == row.get("namespace") and selector and selector.get("match_labels"):
            if selector_matches(selector, row.get("template_labels")) is True and service.get("ports"):
                return True
    return None


def evaluate_cluster(rule, row, raw):
    test, cluster, inventory = rule["test"], raw["cluster"], raw["inventory"]
    if test == "managed_identity":
        value = cluster.get("identity_type")
        return decision(None if value is None else any(kind in value.split(", ") for kind in ("SystemAssigned", "UserAssigned")),
                        "ARM identity type observed; no credentials are exported.", {"identity_type": value})
    if test == "managed_entra":
        return decision(cluster.get("managed_entra"), "aadProfile.managed observed; this does not prove effective permissions.",
                        {"managed_entra": cluster.get("managed_entra")})
    if test == "rbac":
        return decision(cluster.get("enable_rbac"), "enableRBAC observed; Azure RBAC and least privilege are separate controls.",
                        {key: cluster.get(key) for key in ("enable_rbac", "azure_rbac")})
    if test == "local_accounts":
        return conditional(cluster.get("disable_local_accounts"), cluster.get("managed_entra"),
                           "disableLocalAccounts observed.", {"disable_local_accounts": cluster.get("disable_local_accounts")})
    if test == "api_access":
        private, ranges = cluster.get("private_cluster"), cluster.get("authorized_ip_ranges")
        value = True if private is True or (ranges and not any(v in ("0.0.0.0/0", "::/0") for v in ranges)) else (
            False if private is False and ranges is not None else None)
        return decision(value, "Private endpoint or limited public ranges; this does not prove connectivity, authentication or complete security.",
                        {"private_cluster": private, "authorized_ip_ranges": ranges})
    if test == "workload_identity":
        wi, oidc = cluster.get("workload_identity_enabled"), cluster.get("oidc_enabled")
        value = True if wi is True and oidc is True else False if wi is False or oidc is False else None
        return conditional(value, expected(raw, "workload_identity_required"), "Cluster Workload ID/OIDC, not per-pod use.",
                           {"workload_identity_enabled": wi, "oidc_enabled": oidc})
    if test == "network_policy_engine":
        network = cluster.get("network", {})
        value = True if network.get("dataplane") == "cilium" or network.get("policy") in ("azure", "calico", "cilium") else (
            False if network.get("policy") == "none" else None)
        return conditional(value, expected(raw, "network_policy_required"), "Engine observed; Cilium is accepted without requiring Calico.",
                           {"dataplane": network.get("dataplane"), "policy": network.get("policy")})
    if test == "cni":
        network = cluster.get("network", {})
        value = True if network.get("plugin") == "azure" and network.get("plugin_mode") == "overlay" else (
            False if network.get("plugin") is not None else None)
        return conditional(value, expected(raw, "overlay_required"), "Overlay is the current recommendation, not a universal requirement.",
                           network)
    if test in ("policy", "defender"):
        value = pick(cluster, "addons", "azurepolicy", "enabled") if test == "policy" else cluster.get("defender_enabled")
        return conditional(value, expected(raw, test + "_required"), "Enabled option only; compliance, health and licensing were not verified.",
                           {test + "_enabled": value})
    if test == "sla_tier":
        if expected(raw, "sla_required") is not True:
            return outcome("not_applicable" if expected(raw, "sla_required") is False else "not_evaluated",
                           "No production SLA requirement is known; LAB is not treated as production.", {"sku_tier": cluster.get("sku_tier")})
        tier = cluster.get("sku_tier")
        return decision(True if tier in ("Standard", "Premium") else False if tier == "Free" else None,
                        "Current Standard/Premium tier; legacy or unknown values need review.", {"sku_tier": tier})
    if test == "zones":
        zones = row.get("availability_zones")
        value = len(set(zones)) >= 2 if zones is not None else None
        return conditional(value, expected(raw, "availability_zones_required"), "Pool zones configured; regional availability and exceptions need a confirmed requirement.",
                           {"name": row.get("name"), "availability_zones": zones})
    if test == "pool_state":
        value = row.get("provisioning_state")
        return decision(True if value == "Succeeded" else False if value in ("Failed", "Canceled") else None,
                        "Pool provisioning state, separate from the cluster's Running state and workload health.",
                        {"name": row.get("name"), "provisioning_state": value, "cluster_power_state": cluster.get("power_state")})
    if test == "system_taint":
        if row.get("mode") != "System":
            return outcome("not_applicable", "Not a System pool.", {"mode": row.get("mode")})
        taints = row.get("node_taints")
        return decision(None if taints is None else any(v.startswith("CriticalAddonsOnly=") or v.startswith("CriticalAddonsOnly:") for v in taints),
                        "Protection taint observed; equivalent isolation controls need review.",
                        {"name": row.get("name"), "node_taints": taints})
    if test == "system_isolation":
        if not source_complete(raw, "kube_nodes", "kube_pods", "arm_node_pools"):
            return outcome("not_evaluated", "The pool-node-pod join needs complete inventories; having System pools does not prove where applications run.",
                           source_ids=["kube_nodes", "kube_pods", "arm_node_pools"])
        system_pools = {pool["name"] for pool in inventory.get("node_pools", []) if pool.get("mode") == "System"}
        nodes = {node["name"]: node.get("pool_name") for node in inventory.get("nodes", [])}
        apps = [pod for pod in inventory.get("pods", []) if pod.get("namespace") not in SYSTEM_NAMESPACES
                and pod.get("phase") not in ("Succeeded", "Failed")]
        placed = [pod for pod in apps if pod.get("node_name") in nodes]
        if not apps:
            return outcome("not_applicable", "No active application pods were observed in the complete collection.")
        if len(placed) != len(apps) or any(nodes.get(pod["node_name"]) is None for pod in placed):
            return outcome("not_evaluated", "Not every application pod has a verifiable node/pool join.")
        affected = [{"namespace": pod["namespace"], "pod": pod["name"], "node": pod["node_name"], "pool": nodes[pod["node_name"]]}
                    for pod in placed if nodes[pod["node_name"]] in system_pools]
        return decision(not affected, "Exact observed joins only; node names are not taken as proof of a pool.",
                        {"application_pods": len(apps), "pods_on_system_pools": affected}, ["kube_nodes", "kube_pods", "arm_node_pools"])
    if test == "autoscaling":
        nap = cluster.get("node_provisioning_mode") == "Auto" or cluster.get("mode") == "Automatic"
        pools = inventory.get("node_pools", [])
        observed = {"node_provisioning_mode": cluster.get("node_provisioning_mode"), "mode": cluster.get("mode"),
                    "pool_auto_scaling": [{"name": p["name"], "enabled": p.get("enable_auto_scaling")} for p in pools]}
        value = True if nap or any(p.get("enable_auto_scaling") is True for p in pools) else (
            False if pools and source_complete(raw, "arm_node_pools") and all(p.get("enable_auto_scaling") is False for p in pools) else None)
        return conditional(value, expected(raw, "autoscaling_required"), "NAP/Automatic or autoscaler configured; effectiveness and savings were not measured.",
                           observed, ["arm_cluster", "arm_node_pools"])
    if test in ("upgrade_policy", "node_image_policy"):
        key = "channel" if test == "upgrade_policy" else "node_os_channel"
        value = pick(cluster, "auto_upgrade", key)
        enabled = None if value is None else value.lower() != "none"
        requirement = "automatic_upgrades_required" if test == "upgrade_policy" else "node_image_upgrades_required"
        return conditional(enabled, expected(raw, requirement), "Channel observed; an unknown manual process is not labeled as missing.",
                           {"auto_upgrade": cluster.get("auto_upgrade")})
    if test == "version_support":
        versions, profile, current = raw.get("regional_versions", []), raw.get("upgrade_profile"), cluster.get("version")
        observed = {"current_version": current, "support_plan": cluster.get("support_plan"), "upgrade_profile": profile,
                    "regional_version_count": len(versions)}
        if not source_complete(raw, "arm_regional_versions", "arm_upgrade_profile") or not current:
            return outcome("not_evaluated", "The current regional catalog or upgrade profile is missing; no fixed latest version is used.", observed,
                           ["arm_regional_versions", "arm_upgrade_profile", "arm_cluster"])
        known = any(current in (v.get("patch_versions") or {}) or current == v.get("version") for v in versions)
        return decision(True if known else None,
                        "Version present in the current regional catalog." if known else
                        "Not in the offered catalog; this does not prove end of support (LTS and regional policy need validation).",
                        observed, ["arm_regional_versions", "arm_upgrade_profile", "arm_cluster"])
    if test == "diagnostics":
        rows = raw.get("arm_diagnostics", [])
        enabled = any(log.get("enabled") is True for r in rows for log in r.get("logs", []))
        value = True if enabled else False if source_complete(raw, "arm_diagnostics") else None
        return conditional(value, expected(raw, "diagnostics_required"), "Diagnostic settings/logs configured; delivery and ingestion were not measured.",
                           {"settings": rows}, ["arm_diagnostics"])
    if test == "maintenance":
        rows = raw.get("arm_maintenance", [])
        value = True if any(r.get("configured") is True for r in rows) else False if source_complete(raw, "arm_maintenance") else None
        return conditional(value, expected(raw, "maintenance_required"), "Configured window observed, not a validated run.",
                           {"maintenance_configurations": rows}, ["arm_maintenance"])
    if test == "telemetry":
        rows = inventory.get("node_metrics", []) + inventory.get("pod_metrics", [])
        measured = [row for row in rows if row.get("fresh_for_reference") is True]
        return decision(True if measured else None, "Current metrics.k8s.io samples; no history, logs or guarantee of monthly coverage.",
                        {"observed_samples": len(measured)}, ["kube_node_metrics", "kube_pod_metrics"])
    if test == "advisor":
        return decision(True if source_complete(raw, "arm_advisor") else None,
                        "Cached recommendations read for the exact ResourceId; an empty list does not prove that there are no opportunities.",
                        {"recommendations": raw.get("advisor", [])}, ["arm_advisor"])
    if test in ("dns", "cost_allocation", "rightsizing", "spot"):
        reasons = {
            "dns": "DNS/IPAM inventory does not measure resolution, latency, failover or capacity requirements.",
            "cost_allocation": "ActualCost by ResourceId does not prove invoice allocation to a namespace or workload.",
            "rightsizing": "The current usage sample is neither a representative historical window nor a calculated saving.",
            "spot": "Commercial eligibility, stable history and confirmed eviction tolerance were not collected.",
        }
        return outcome("not_evaluated", reasons[test], {"source_data_available": bool(raw.get("cost_rows"))},
                       ["azure_cost", "kube_node_metrics", "kube_pod_metrics"] if test != "dns" else ["arm_cluster"])
    raise EvidenceError("unknown_rule", "Catalog rule has no implemented evaluator.", "rule_catalog")


def evaluate_workload(rule, row, raw):
    test = rule["test"]
    if row.get("namespace") in SYSTEM_NAMESPACES:
        return outcome("not_applicable", "System namespace component: it needs the provider's baseline, not general application rules.")
    is_batch = row.get("kind") in ("Job", "CronJob")
    if test in ("probes", "pdb", "hpa", "replicas", "network_policies") and (is_batch or row.get("desired_replicas") == 0):
        return outcome("not_applicable", "Batch or zero desired replicas: no outage is declared and continuous availability is not required.",
                       {"kind": row.get("kind"), "desired_replicas": row.get("desired_replicas")})
    containers = row.get("containers")
    if not containers:
        return outcome("not_evaluated", "No container specification is available; inventory or telemetry does not replace manifests.")
    if test == "resources":
        required = ["request_cpu_cores", "request_memory_bytes", "limit_memory_bytes"]
        if expected(raw, "cpu_limits_required") is True:
            required.append("limit_cpu_cores")
        combined = containers + (row.get("init_containers") or [])
        missing = [{"container": c["name"], "missing_or_zero": [key for key in required if c.get(key) is None or c[key] <= 0]} for c in combined]
        return decision(all(not item["missing_or_zero"] for item in missing), "Checks positive requests and a memory limit; CPU limits only when required. These are not usage measurements.",
                        {"containers": combined, "missing": missing})
    if test == "probes":
        applies = serving_workload(raw, row)
        if applies is not True:
            return outcome("not_applicable" if applies is False else "not_evaluated",
                           "No evidence of a service or a probe requirement; not every container is assumed to serve traffic.")
        serving = [c for c in containers if c.get("ports")]
        if not serving and expected(raw, "probes_required", row) is True:
            serving = containers
        if not serving:
            return outcome("not_evaluated", "A Service selects the workload, but the serving container cannot be identified.")
        return decision(all(c.get("readiness_probe") and c.get("liveness_probe") for c in serving),
                        "Identified serving containers only; presence does not prove that the probe is adequate.",
                        {"serving_containers": serving}, [row["source_id"], "kube_services"])
    if test == "pdb":
        replicas = row.get("desired_replicas")
        applies = replicas is not None and replicas >= 2 and serving_workload(raw, row) is True
        if not applies and expected(raw, "availability_required", row) is not True:
            return outcome("not_evaluated", "A PDB needs a replicated service or a confirmed availability requirement.",
                           {"desired_replicas": replicas})
        if not source_complete(raw, "kube_pdbs"):
            return outcome("not_evaluated", "PDB inventory incomplete or not authorized; absence is not a failure.", source_ids=["kube_pdbs"])
        matched = [p for p in raw["inventory"].get("pdbs", []) if p.get("namespace") == row.get("namespace")
                   and selector_matches(p.get("selector"), row.get("template_labels")) is True]
        if row.get("template_labels") is None:
            return outcome("not_evaluated", "Template labels for the PDB join are missing.")
        unprotected = [p for p in matched if p.get("min_available") in (0, "0%")
                       or p.get("max_unavailable") == "100%"
                       or isinstance(p.get("max_unavailable"), int) and replicas is not None and p["max_unavailable"] >= replicas]
        valid = [p for p in matched if p.get("min_available") is not None or p.get("max_unavailable") is not None]
        if matched and len(valid) != len(matched):
            return outcome("not_evaluated", "Selected PDB without an observed minAvailable/maxUnavailable.", {"matched_pdbs": matched}, ["kube_pdbs"])
        if unprotected:
            return decision(False, "The selected PDB allows every replica to be evicted; it does not give the required protection against voluntary disruption.",
                            {"desired_replicas": replicas, "matched_pdbs": matched}, [row["source_id"], "kube_pdbs"])
        return decision(bool(matched), "policy/v1 selector evaluated by namespace and labels; a PDB does not protect against involuntary disruption.",
                        {"desired_replicas": replicas, "matched_pdbs": matched}, [row["source_id"], "kube_pdbs"])
    if test == "hpa":
        if not source_complete(raw, "kube_hpas"):
            return outcome("not_evaluated", "HPAs not fully collected; absence is not inferred.", source_ids=["kube_hpas"])
        matched = [h for h in raw["inventory"].get("hpas", []) if h.get("namespace") == row.get("namespace")
                   and pick(h, "target", "name") == row["name"] and pick(h, "target", "kind") == row["kind"]]
        return conditional(bool(matched), expected(raw, "autoscaling_required", row), "Exact HPA target; metrics and effectiveness need validation.",
                           {"matched_hpas": matched}, [row["source_id"], "kube_hpas"])
    if test == "replicas":
        requirement, replicas = expected(raw, "availability_required", row), row.get("desired_replicas")
        return conditional(None if replicas is None else replicas >= 2, requirement, "Desired replicas, not measured availability.",
                           {"desired_replicas": replicas, "ready_replicas": row.get("ready_replicas")})
    if test == "container_security":
        if row.get("os_name") == "windows" or pick(row, "node_selector", "kubernetes.io/os") == "windows":
            return outcome("not_applicable", "Windows container: Linux controls are not applied by analogy.")
        combined = containers + (row.get("init_containers") or [])
        def effective_uid(container):
            return container["run_as_user"] if container.get("run_as_user") is not None else row.get("run_as_user")
        def effective_nonroot(container):
            value = pick(container, "security", "runAsNonRoot")
            return value if value is not None else pick(row, "pod_security", "runAsNonRoot")
        dangerous = [c["name"] for c in combined if pick(c, "security", "privileged") is True
                     or pick(c, "security", "allowPrivilegeEscalation") is True or effective_uid(c) == 0]
        safe = all(pick(c, "security", "privileged") is False and pick(c, "security", "allowPrivilegeEscalation") is False
                   and (effective_nonroot(c) is True or isinstance(effective_uid(c), (int, float))
                        and effective_uid(c) > 0) for c in combined)
        return decision(False if dangerous else True if safe else None,
                        "Explicit privileges; without a UID or securityContext the image is not assumed to run as root.",
                        {"containers": combined, "explicitly_elevated": dangerous, "pod_security": row.get("pod_security")})
    if test == "images":
        images = [c.get("image") for c in containers + (row.get("init_containers") or [])]
        if any(image is None for image in images):
            return outcome("not_evaluated", "An image reference is missing.")
        mutable = [image for image in images if "@sha256:" not in image
                   and (":" not in image.rsplit("/", 1)[-1] or image.rsplit(":", 1)[-1] == "latest")]
        return decision(not mutable, "latest or a missing tag observed; a specific tag does not prove immutability or scanning.",
                        {"images": images, "mutable_default_references": mutable})
    if test == "network_policies":
        if not source_complete(raw, "kube_network_policies"):
            return outcome("not_evaluated", "NetworkPolicies incomplete or not authorized.", source_ids=["kube_network_policies"])
        matched = [p for p in raw["inventory"].get("network_policies", []) if p.get("namespace") == row.get("namespace")
                   and selector_matches(p.get("selector"), row.get("template_labels")) is True]
        if row.get("template_labels") is None:
            return outcome("not_evaluated", "Labels to select policies are missing.")
        return conditional(bool(matched), expected(raw, "network_policy_required", row),
                           "Selector observed; types, rules and engine must be validated to prove isolation.",
                           {"matched_policies": matched}, [row["source_id"], "kube_network_policies"])
    raise EvidenceError("unknown_rule", "Workload rule has no evaluator.", "rule_catalog")


def evaluate_namespace(rule, row, raw):
    if row.get("name") in SYSTEM_NAMESPACES:
        return outcome("not_applicable", "System namespace, subject to the provider's baseline.")
    if rule["test"] == "quota":
        if not source_complete(raw, "kube_resource_quotas"):
            return outcome("not_evaluated", "ResourceQuotas not fully available.", source_ids=["kube_resource_quotas"])
        matched = [quota for quota in raw["inventory"].get("resource_quotas", []) if quota.get("namespace") == row["name"]]
        return conditional(bool(matched), expected(raw, "quota_required"), "Quota existence/configuration only, not billed consumption.",
                           {"quotas": matched}, ["kube_resource_quotas", "kube_namespaces"])
    value = pick(row, "labels", "pod-security.kubernetes.io/enforce")
    active = True if value in ("baseline", "restricted") else False if value in ("privileged", None) else None
    return conditional(active, expected(raw, "pod_security_required"), "enforce label observed; audit/warn or the Policy add-on are not equivalent to compliance.",
                               {"enforce": value}, ["kube_namespaces"])


def evaluate_resource(rule, row, raw):
    test = rule["test"]
    if test == "pvc_binding":
        phase = row.get("phase")
        if phase == "Bound":
            return decision(True, "PVC Bound observed; this does not prove performance or recoverability.", {"phase": phase, "volume_name": row.get("volume_name")})
        if phase == "Lost":
            return decision(False, "PVC Lost observed.", {"phase": phase})
        classes = raw["inventory"].get("storage_classes", [])
        sc = next((c for c in classes if c["name"] == row.get("storage_class")), None)
        consumers = [pod for pod in raw["inventory"].get("pods", []) if pod.get("namespace") == row.get("namespace")
                     and row["name"] in pod.get("pvc_names", []) and pod.get("phase") not in ("Succeeded", "Failed")]
        if phase == "Pending" and pick(sc, "volume_binding_mode") == "WaitForFirstConsumer" and not consumers:
            if source_complete(raw, "kube_pods", "kube_storage_classes"):
                return outcome("not_applicable", "WaitForFirstConsumer without an active consumer: deferred binding can be intentional.",
                               {"phase": phase, "storage_class": sc["name"]}, ["kube_pods", "kube_storage_classes", "kube_pvcs"])
        return decision(False if phase == "Pending" and consumers else None,
                        "Pending with an observed consumer needs review; a missing consumer is not assumed without authorized evidence.",
                        {"phase": phase, "active_consumers": [{"namespace": p["namespace"], "pod": p["name"]} for p in consumers]},
                        ["kube_pvcs", "kube_pods", "kube_storage_classes"])
    config = row.get("configuration", {})
    if test == "load_balancer":
        sku = row.get("sku_name")
        return decision(True if sku == "Standard" else False if sku == "Basic" else None,
                        "Azure SKU observed; public or private frontends are not inferred from the name.", {"sku_name": sku, "frontends": row.get("frontends")})
    if test == "storage_tls":
        https, tls = config.get("supportsHttpsTrafficOnly"), config.get("minimumTlsVersion")
        value = False if https is False or tls in ("TLS1_0", "TLS1_1") else True if https is True and tls in ("TLS1_2", "TLS1_3") else None
        return decision(value, "ARM HTTPS and minimum TLS values; no Storage keys or data were read.", config)
    if test == "keyvault_rbac":
        return decision(True if config.get("enableRbacAuthorization") is True else None,
                        "RBAC enabled does not prove least privilege; access policies can need a justified exception.", config)
    if test == "nsg_exposure":
        exposure = []
        for item in row.get("security_rules", []):
            sources = [item.get("sourceAddressPrefix")] + (item.get("sourceAddressPrefixes") or [])
            ports = [item.get("destinationPortRange")] + (item.get("destinationPortRanges") or [])
            broad = any(value in ("*", "Internet", "0.0.0.0/0", "::/0") for value in sources)
            admin = any(value in ("*", "22", "3389", "0-65535") for value in ports)
            if item.get("direction") == "Inbound" and item.get("access") == "Allow" and broad and admin:
                exposure.append(item)
        return decision(False if exposure else None, "Broad explicit rule; association, priority and an actual listener need review.",
                        {"broad_administrative_rules": exposure})
    raise EvidenceError("unknown_rule", "Resource rule has no evaluator.", "rule_catalog")


def assessment_check(rule, row, result, raw, reference):
    cluster = raw["cluster"]
    namespace = row.get("namespace") or (row.get("name") if rule["level"] == "namespace" else "") or ""
    workload_name = row.get("workload_name") or ""
    resource_id = row.get("resource_id") or cluster["resource_id"]
    ref = row.get("uid") or row.get("id") or namespace + "/" + workload_name or "cluster"
    check_id = "AKS-" + rule["rule_id"] + "-" + hashlib.sha256(
        (cluster["id"].lower() + "|" + resource_id.lower() + "|" + str(ref)).encode("utf-8")).hexdigest()[:12]
    pillar_anchor = {"cost": "cost-optimization", "operations": "operational-excellence", "performance": "performance-efficiency"}.get(rule["pillar"], rule["pillar"])
    items = {item["id"]: item for item in CATALOG["checklist_items"]}
    item = items[rule["checklist_id"]]
    source_ids = result["source_ids"] or [row.get("source_id") or "arm_cluster"]
    receipts = {source["id"]: source for source in raw["sources"]}
    evidence = [{"source_id": source_id, "resource_id": resource_id,
                         "observed_at": pick(receipts.get(source_id), "time") or reference,
                         "value": result["value"] if index == 0 else {"join_source": source_id},
                         "collection_status": pick(receipts.get(source_id), "status") or "not_configured"}
                        for index, source_id in enumerate(dict.fromkeys(source_ids))]
    return {
                "check_id": check_id, "rule_id": rule["rule_id"], "checklist_id": rule["checklist_id"],
                "checklist_guid": item["guid"], "title": rule["title"], "status": result["status"],
                "level": "cluster" if rule["level"] in ("cluster", "node_pool") else "workload" if rule["level"] in ("workload", "namespace") else "resource",
                "area": rule["area"], "pillar": rule["pillar"], "severity": rule["severity"],
                "severity_label": {"critical": "Critical", "high": "High", "medium": "Medium", "low": "Low"}[rule["severity"]],
                "resource_id": resource_id, "resource_name": row.get("name") or cluster["name"],
                "namespace": namespace, "workload_name": workload_name, "cluster_name": cluster["name"], "cluster_id": cluster["id"],
                "kubernetes_ref": {"kind": row.get("kind"), "namespace": namespace, "name": row.get("name"), "uid": row.get("uid")} if row.get("uid") else None,
                "evidence": evidence, "business_impact": rule["business_impact"], "recommendation": rule["recommendation"],
                "learn_url": CATALOG["guide"]["url"] + "#" + pillar_anchor,
                "checklist_url": "https://github.com/Azure/review-checklists/blob/" + CATALOG["catalogSnapshot"]["commit"] + "/checklists/aks_checklist.en.json",
                "kubernetes_url": rule.get("kubernetes_url", ""), "effort": rule["effort"],
                "effort_label": {"low": "L", "medium": "M", "high": "H"}[rule["effort"]], "reason": result["reason"],
    }


def evaluate(raw, reference):
    if not CATALOG.get("rules") or len(CATALOG.get("checklist_items", [])) != CATALOG.get("catalogSnapshot", {}).get("item_count"):
        raise EvidenceError("catalog_missing", "Build the pinned complete catalog into the standalone tool.", "rule_catalog")
    checks, mapped = [], set()
    inventory = raw["inventory"]
    type_for_test = {"load_balancer": "microsoft.network/loadbalancers", "storage_tls": "microsoft.storage/storageaccounts",
                             "keyvault_rbac": "microsoft.keyvault/vaults", "nsg_exposure": "microsoft.network/networksecuritygroups"}
    for rule in CATALOG["rules"]:
        mapped.add(rule["checklist_id"])
        target = rule["level"]
        if target == "cluster":
            records = [raw["cluster"]]
        elif target == "node_pool":
            records = inventory.get("node_pools", [])
        elif target == "workload":
            records = inventory.get("workloads", [])
        elif target == "namespace":
            records = inventory.get("namespaces", [])
        elif target == "pvc":
            records = inventory.get("pvcs", [])
        else:
            records = [r for r in inventory.get("related_resources", []) if r.get("resource_kind") == type_for_test[rule["test"]]]
        if not records:
            sources = ("arm_node_pools",) if target == "node_pool" else ("kube_namespaces",) if target == "namespace" else (
                ("kube_pvcs",) if target == "pvc" else tuple("kube_" + key for key in ("deployments", "statefulsets", "daemonsets", "jobs", "cronjobs"))
                if target == "workload" else ("arm_related_inventory",))
            result = outcome("not_applicable" if source_complete(raw, *sources) else "not_evaluated",
                             "No applicable objects in the complete inventory." if source_complete(raw, *sources)
                             else "Inventory unavailable or incomplete; no objects, findings or health are invented.", source_ids=list(sources))
            checks.append(assessment_check(rule, {}, result, raw, reference))
            continue
        for row in records:
            result = evaluate_cluster(rule, row, raw) if target in ("cluster", "node_pool") else (
                evaluate_workload(rule, row, raw) if target == "workload" else evaluate_namespace(rule, row, raw)
                if target == "namespace" else evaluate_resource(rule, row, raw))
            checks.append(assessment_check(rule, row, result, raw, reference))
    for item in CATALOG["checklist_items"]:
        if item["id"] in mapped:
            continue
        pillar = {"Reliability": "reliability", "Security": "security", "Cost": "cost", "Operations": "operations",
                  "Performance": "performance"}[item["waf"]]
        rule = {"rule_id": "M" + item["id"], "checklist_id": item["id"], "level": "cluster",
                "area": {"security": "security", "cost": "finops", "performance": "optimization"}.get(pillar, "best_practices"),
                "pillar": pillar, "severity": str(item["severity"]).lower() if str(item["severity"]).lower() in SEVERITIES else "low",
                "effort": "medium", "title": "Architecture review: " + item["text"],
                "recommendation": "Validate applicability and documented evidence with the owner and the current guidance; do not run legacy snippets.",
                "business_impact": "The risk depends on requirements and evidence not yet collected; noncompliance is not assumed."}
        result = outcome("not_evaluated", "Checklist item not automated by this reader: requirements, IaC, DR, tests or another source are missing.",
                         {"checklist_id": item["id"], "upstream_text": item["text"]}, ["reference_catalog"])
        checks.append(assessment_check(rule, raw["cluster"], result, raw, reference))
    if len({check["check_id"] for check in checks}) != len(checks):
        raise EvidenceError("duplicate_check", "Rule/resource check IDs are not unique; no duplicated score denominator.", "evaluator")
    return checks


def score(checks):
    if len({row["check_id"] for row in checks}) != len(checks):
        raise EvidenceError("duplicate_check", "Duplicate check IDs cannot be scored.", "evaluator")
    counts = Counter(row["status"] for row in checks)
    if set(counts) - set(CHECK_STATUSES):
        raise EvidenceError("invalid_check_status", "Unknown check status cannot be scored.", "evaluator")
    evaluated = counts["passed"] + counts["failed"]
    eligible = evaluated + counts["not_evaluated"]
    return {
                "score": round(100 * counts["passed"] / evaluated, 2) if evaluated else None,
                "passed": counts["passed"], "failed": counts["failed"], "evaluated": evaluated,
                "not_evaluated": counts["not_evaluated"], "not_applicable": counts["not_applicable"], "total": len(checks),
                "coverage_percent": round(100 * evaluated / eligible, 2) if eligible else None,
    }


def actions_for(findings):
    return [
                {"action_id": "ACT-" + check["check_id"], "check_id": check["check_id"], "title": check["title"],
                 "cluster_id": check["cluster_id"], "cluster_name": check["cluster_name"],
                 "resource_id": check["resource_id"], "namespace": check["namespace"], "workload_name": check["workload_name"],
                 "area": check["area"], "pillar": check["pillar"], "severity": check["severity"], "status": "failed",
                 "level": check["level"], "resource_name": check["resource_name"],
                 "effort": check["effort"], "planning_bucket": {"low": "quick_win", "medium": "short_term", "high": "medium_term"}[check["effort"]],
                 "planning_note": "Indicative bucket: <1 week / 1-3 months / medium term; not a measurement or a delivery commitment.",
                 "recommendation": check["recommendation"], "learn_url": check["learn_url"], "owner": None}
                for check in sorted(findings, key=lambda row: (SEVERITIES.index(row["severity"]), row["check_id"]))
    ]


def finops_for(raw):
    inventory = raw["inventory"]
    metrics = [{**row, "basis": "metrics.k8s.io current snapshot, not 30-day utilization", "metric_kind": collection}
                       for collection in ("node_metrics", "pod_metrics") for row in inventory.get(collection, [])]
    candidates = []
    nodes = {node["name"]: node for node in inventory.get("nodes", [])}
    for metric in inventory.get("node_metrics", []):
        node = nodes.get(metric["name"])
        capacity, usage = pick(node, "allocatable", "cpu"), metric.get("cpu_cores")
        if capacity is not None and capacity > 0 and usage is not None and metric.get("fresh_for_reference") is True:
            ratio = usage / capacity
            if ratio < .2:
                candidates.append({
                    "id": "CURRENT-NODE-" + metric["name"], "title": "Review capacity with a current sample, not monthly underutilization",
                    "resource_id": metric["resource_id"], "source_id": metric["source_id"], "basis": "Local review threshold <20% current CPU/allocatable, no sustained-use claim",
                    "value": round(100 * ratio, 6), "unit": "percent", "numerator": usage, "numerator_unit": "cores",
                    "denominator": capacity, "denominator_unit": "allocatable_cores", "sample_count": 1,
                    "window": {"timestamp": metric["timestamp"], "duration": metric["window"]},
                    "recommendation": "Get history, peaks, memory and requirements before right-sizing; do not change capacity.",
                    "estimated_savings": None,
                })
    owners = {row["uid"]: row for row in inventory.get("workloads", []) + inventory.get("replicasets", [])}
    workloads = {row["uid"]: row for row in inventory.get("workloads", [])}
    def workload_owner(pod):
        current, seen = pod, set()
        for _ in range(4):
            controllers = [ref for ref in current.get("owner_references", []) if ref.get("controller") is True]
            if len(controllers) != 1:
                return None
            uid = controllers[0].get("uid")
            if uid in seen:
                return None
            if uid in workloads:
                return workloads[uid]
            seen.add(uid)
            current = owners.get(uid)
            if current is None:
                return None
        return None
    pod_metrics = {(row.get("namespace"), row["name"]): row for row in inventory.get("pod_metrics", [])}
    joined = {}
    for pod in inventory.get("pods", []):
        workload, metric = workload_owner(pod), pod_metrics.get((pod.get("namespace"), pod["name"]))
        if workload is None or metric is None or metric.get("fresh_for_reference") is not True:
            continue
        measurements = {c["name"]: c for c in metric.get("containers", [])}
        for container in pod.get("containers", []):
            measured = measurements.get(container["name"])
            request = container.get("request_cpu_cores")
            if request is not None and measured is not None and measured.get("cpu_cores") is not None:
                group = joined.setdefault(workload["uid"], {"workload": workload, "requests": [], "usage": [], "windows": [], "samples": 0})
                group["requests"].append(request)
                group["usage"].append(measured["cpu_cores"])
                group["windows"].append({"timestamp": metric["timestamp"], "duration": metric["window"]})
                group["samples"] += 1
    for group in joined.values():
        requests, usage, workload = sum(group["requests"]), sum(group["usage"]), group["workload"]
        if requests > 0 and usage / requests < .5:
            candidates.append({
                "id": "CURRENT-WORKLOAD-" + workload["uid"], "title": "Review requests with current samples from containers joined by owner UID",
                "resource_id": workload["resource_id"], "namespace": workload.get("namespace"), "workload_name": workload["name"],
                "source_id": "kube_pod_metrics", "basis": "Current measured containers / same containers' configured requests; not historical or billing allocation",
                "value": round(100 * usage / requests, 6), "unit": "percent", "numerator": usage, "numerator_unit": "cores",
                "denominator": requests, "denominator_unit": "requested_cores", "sample_count": group["samples"], "window": group["windows"],
                "recommendation": "Review coverage and historical data before you change requests; this guarantees neither right-sizing nor savings.",
                "estimated_savings": None,
            })
    complete_refs = source_complete(raw, "arm_related_inventory", "kube_pvs", "kube_services")
    all_details = all(source["status"] == "complete" for source in raw["sources"] if source["id"].startswith("arm_resource_"))
    pv_refs = {row.get("csi_volume_handle", "").lower() for row in inventory.get("pvs", []) if row.get("csi_volume_handle")}
    public_refs = {frontend["public_ip_id"].lower() for row in inventory.get("related_resources", []) for frontend in row.get("frontends", [])
                           if frontend.get("public_ip_id")}
    public_refs |= {value.lower() for row in inventory.get("related_resources", []) for value in row.get("public_ip_ids", [])}
    for resource in inventory.get("related_resources", []):
        if not complete_refs or not all_details or pick(resource, "association", "type") != "operator_scoped":
            continue
        disk = resource.get("resource_kind") == "microsoft.compute/disks"
        pip = resource.get("resource_kind") == "microsoft.network/publicipaddresses"
        unattached = (disk and pick(resource, "configuration", "diskState") == "Unattached"
                      and resource.get("managed_by_present") is True and not resource.get("managed_by")
                      and not resource.get("managed_by_extended") and resource["resource_id"].lower() not in pv_refs)
        unattached |= (pip and resource.get("ip_configuration_present") is True and resource.get("ip_configuration_id") is None
                       and resource.get("nat_gateway_present") is True and resource.get("nat_gateway_id") is None
                       and resource["resource_id"].lower() not in public_refs)
        if unattached:
            candidates.append({"id": "UNATTACHED-" + hashlib.sha256(resource["resource_id"].encode()).hexdigest()[:12],
                               "title": "Review an approved asset with no confirmed attachment",
                               "resource_id": resource["resource_id"], "source_id": resource["source_id"],
                               "basis": "Explicit attachment fields + complete collected PV/LB/NIC scope; not cluster ownership by nodeRG name",
                               "value": "unattached", "unit": "attachment_state", "sample_count": 1, "window": None,
                               "recommendation": "Confirm retention, owner and cost before you decide; do not delete or promise savings.",
                               "estimated_savings": None})
    cost_rows = raw.get("cost_rows", [])
    currencies = {row["currency"] for row in cost_rows}
    cost_source = next((source for source in raw["sources"] if source["id"] == "azure_cost"), None)
    currency = next(iter(currencies)) if len(currencies) == 1 else None
    total = float(sum((Decimal(str(row["amount"])) for row in cost_rows), Decimal(0))) if currency and pick(cost_source, "status") == "complete" else None
    by_currency = {code: float(sum((Decimal(str(row["amount"])) for row in cost_rows if row["currency"] == code), Decimal(0)))
                   for code in sorted(currencies)}
    return {
                "sources": ["azure_cost", "arm_advisor", "kube_node_metrics", "kube_pod_metrics"],
                "window": pick(cost_source, "window"), "currency": currency, "actual_cost": total, "cost_rows": cost_rows,
                "metrics": metrics, "candidates": candidates, "estimated_savings": None,
                "observed_cost_totals_by_currency": by_currency, "cost_source_complete": pick(cost_source, "status") == "complete",
                "notes": [
                    "Requests/capacity are configuration, not usage. Current snapshots are not monthly utilization.",
                    "ActualCost uses observed approved ResourceIds and actual currency; it is not namespace/workload billing.",
                    "Billing latency, current partial day and allocation visibility remain limitations even with complete query paging.",
                    "No computed reservations, savings-plan/Spot savings, rightsizing promise or deletion recommendation.",
                    "Incomplete/denied/unconfigured sources remain Not evaluated; different currencies are never added together.",
                ],
    }


def architecture_for(raw, reference, provenance):
    cluster, inventory = raw["cluster"], raw["inventory"]
    scope = {"cluster_id": cluster["id"], "cluster_name": cluster["name"],
             "provenance": provenance, "observed_at": reference}
    nodes, edges, unknowns, arm_nodes, kube_nodes = {}, {}, [], {}, {}
    def unknown(code, kind, message, source_ids, resource_id=None):
        unknowns.append({**scope, "code": code, "kind": kind, "message": message, "source_ids": source_ids,
                         "resource_id": resource_id or cluster["id"], "status": "not_evaluated"})
    def add_node(row, kind, evidence, native_id=None):
        value = native_id or row.get("uid") or row.get("id")
        key = "node-" + hashlib.sha256((cluster["id"].lower() + "|" + str(value).lower()).encode("utf-8")).hexdigest()[:24]
        node = {**scope, "id": key, "resource_id": native_id or row.get("resource_id") or cluster["id"],
                "kind": kind, "label": row.get("name") or str(value), "source_id": row["source_id"], "evidence": evidence}
        if row.get("namespace"):
            node["namespace"] = row["namespace"]
        if row.get("workload_name"):
            node["workload_name"] = row["workload_name"]
        if key in nodes and nodes[key] != node:
            raise EvidenceError("duplicate_architecture_node", "Observed graph IDs collide; no misleading merged node.", "architecture")
        nodes[key] = node
        if native_id or row.get("id"):
            arm_nodes[str(native_id or row["id"]).lower()] = key
        if row.get("uid"):
            kube_nodes[row["uid"]] = key
        return key
    def link(start, end, relation, source_ids, evidence):
        if not start or not end:
            return
        key = "edge-" + hashlib.sha256((start + "|" + relation + "|" + end).encode("utf-8")).hexdigest()[:24]
        edges.setdefault(key, {**scope, "id": key, "from": start, "to": end, "relation": relation,
                               "source_ids": list(dict.fromkeys(source_ids)), "evidence": evidence})
    def arm_link(row, value, relation, field):
        if value:
            link(arm_nodes.get(row["id"].lower()), arm_nodes.get(value.lower()), relation,
                 [row["source_id"]], {"field": field, "value": value})

    root = add_node(cluster, "managed_cluster", {
        "arm_id": cluster["id"], "power_state": cluster.get("power_state"), "provisioning_state": cluster.get("provisioning_state"),
        "identity": cluster.get("identity"), "kubelet_identity_resource_id": cluster.get("kubelet_identity_resource_id")})
    pools = {row["name"]: row for row in inventory.get("node_pools", [])}
    for row in pools.values():
        key = add_node(row, "agent_pool", {"arm_id": row["id"], "mode": row.get("mode"), "vm_size": row.get("vm_size"),
                                         "count": row.get("count"), "provisioning_state": row.get("provisioning_state")})
        link(root, key, "contains_pool", [row["source_id"]], {"agent_pool_id": row["id"]})
    resource_kinds = {
        "microsoft.compute/virtualmachinescalesets": "virtual_machine_scale_set", "microsoft.compute/disks": "managed_disk",
        "microsoft.network/virtualnetworks": "virtual_network", "microsoft.network/virtualnetworks/subnets": "subnet",
        "microsoft.network/networksecuritygroups": "network_security_group", "microsoft.network/loadbalancers": "azure_load_balancer",
        "microsoft.network/publicipaddresses": "public_ip_address", "microsoft.network/networkinterfaces": "network_interface",
        "microsoft.storage/storageaccounts": "storage_account", "microsoft.containerregistry/registries": "container_registry",
        "microsoft.keyvault/vaults": "key_vault", "microsoft.managedidentity/userassignedidentities": "managed_identity",
        "microsoft.network/privatednszones": "private_dns_zone", "microsoft.network/dnszones": "dns_zone",
    }
    resources = {row["id"].lower(): row for row in inventory.get("related_resources", [])}
    for row in resources.values():
        add_node(row, resource_kinds[row["resource_kind"]], {
            "arm_id": row["id"], "association": row["association"], "configuration": row.get("configuration", {})})
    for row in resources.values():
        parent = row.get("association", {}).get("resource_id")
        if parent:
            link(arm_nodes.get(parent.lower()), arm_nodes[row["id"].lower()], "references_resource",
                 [row["association"]["source_id"], row["source_id"]],
                 {"field": row["association"].get("field"), "referenced_resource_id": row["id"]})
        for field, relation in (("subnet_ids", "uses_subnet"), ("nsg_ids", "associated_nsg"), ("public_ip_ids", "references_public_ip")):
            for value in row.get(field, []):
                arm_link(row, value, relation, field)
        arm_link(row, row.get("nsg_id"), "associated_nsg", "nsg_id")
        if row["resource_kind"] == "microsoft.network/virtualnetworks/subnets":
            parent = re.split(r"/subnets/", row["id"], flags=re.IGNORECASE)[0]
            link(arm_nodes.get(parent.lower()), arm_nodes[row["id"].lower()], "contains_subnet", [row["source_id"]],
                 {"subnet_id": row["id"], "parent_virtual_network_id": parent})
        if row["resource_kind"] == "microsoft.compute/virtualmachinescalesets" and row.get("pool_tag") in pools:
            pool = pools[row["pool_tag"]]
            link(arm_nodes[pool["id"].lower()], arm_nodes[row["id"].lower()], "pool_vmss_tag_association",
                 [pool["source_id"], row["source_id"]], {"aks-managed-poolName": row["pool_tag"],
                 "aks-managed-cluster-name": row.get("cluster_tag"), "scope_association": row["association"]})
    for pool in pools.values():
        for field in ("vnet_subnet_id", "pod_subnet_id"):
            arm_link(pool, pool.get(field), "uses_subnet", field)
    for field in ("private_dns_zone", "kubelet_identity_resource_id"):
        arm_link(cluster, cluster.get(field), "configured_resource_reference", field)
    for value in cluster.get("effective_outbound_ip_ids", []):
        arm_link(cluster, value, "configured_outbound_ip", "effective_outbound_ip_ids")
    for value in cluster.get("identity", {}).get("user_assigned_resource_ids", []):
        arm_link(cluster, value, "configured_identity", "identity.user_assigned_resource_ids")

    frontends = []
    for lb in (row for row in resources.values() if row["resource_kind"] == "microsoft.network/loadbalancers"):
        for group, kind, relation in (("frontends", "load_balancer_frontend", "has_frontend"),
                                      ("backend_pools", "load_balancer_backend_pool", "has_backend_pool"),
                                      ("probes", "load_balancer_probe", "has_probe"),
                                      ("load_balancing_rules", "load_balancer_rule", "has_rule")):
            for item in lb.get(group, []):
                if not item.get("id"):
                    unknown("missing_arm_child_id", kind, "ARM child has no ID; no child resource or relationship is invented.", [lb["source_id"]], lb["id"])
                    continue
                actual_kind = kind
                if group == "frontends":
                    actual_kind += "_public" if item.get("public_ip_id") else "_private" if item.get("private_ip") else "_unknown"
                row = {**lb, "name": item.get("name") or item["id"]}
                key = add_node(row, actual_kind, item, item["id"])
                link(arm_nodes[lb["id"].lower()], key, relation, [lb["source_id"]], {"arm_child_id": item["id"]})
                if group == "frontends":
                    frontends.append((lb, item, key))
        for frontend in lb.get("frontends", []):
            if not frontend.get("id"):
                continue
            for field, relation in (("public_ip_id", "references_public_ip"), ("subnet_id", "uses_subnet")):
                value = frontend.get(field)
                if value:
                    link(arm_nodes.get(frontend["id"].lower()), arm_nodes.get(value.lower()), relation, [lb["source_id"]],
                         {"field": field, "value": value})
        for rule in lb.get("load_balancing_rules", []):
            if not rule.get("id"):
                continue
            for field, relation in (("frontend_id", "uses_frontend"), ("probe_id", "uses_probe"), ("backend_pool_id", "uses_backend_pool")):
                value = rule.get(field)
                if value:
                    link(arm_nodes.get(rule["id"].lower()), arm_nodes.get(value.lower()), relation, [lb["source_id"]],
                         {"field": field, "value": value})
            for value in rule.get("backend_pool_ids", []):
                link(arm_nodes.get(rule["id"].lower()), arm_nodes.get(value.lower()), "uses_backend_pool", [lb["source_id"]],
                     {"field": "backend_pool_ids", "value": value})
    for row in resources.values():
        for value in row.get("load_balancer_backend_pool_ids", []):
            arm_link(row, value, "uses_backend_pool", "load_balancer_backend_pool_ids")

    kinds = {"namespaces": "namespace", "nodes": "node", "workloads": "workload", "pods": "pod",
             "replicasets": "replica_set", "services": "service", "pvcs": "persistent_volume_claim",
             "pvs": "persistent_volume", "storage_classes": "storage_class"}
    kube_rows = []
    for collection, kind in kinds.items():
        for row in inventory.get(collection, []):
            evidence = {"uid": row["uid"], "kind": row.get("kind"), "name": row["name"], "namespace": row.get("namespace"),
                        "resource_version": row.get("resource_version")}
            if collection == "services":
                evidence.update({field: row.get(field) for field in ("service_type", "annotations", "load_balancer_ingress", "ports")})
            if collection == "pvs":
                evidence.update({field: row.get(field) for field in ("csi_driver", "csi_volume_handle", "csi_volume_attributes", "claim_ref")})
            add_node(row, kind, evidence)
            kube_rows.append(row)
    namespaces = {row["name"]: row for row in inventory.get("namespaces", [])}
    by_uid = {row["uid"]: row for row in kube_rows}
    pvcs = {(row.get("namespace"), row["name"]): row for row in inventory.get("pvcs", [])}
    pvs = {row["name"]: row for row in inventory.get("pvs", [])}
    classes = {row["name"]: row for row in inventory.get("storage_classes", [])}
    for row in kube_rows:
        if row.get("namespace") in namespaces:
            namespace = namespaces[row["namespace"]]
            link(kube_nodes[namespace["uid"]], kube_nodes[row["uid"]], "contains_object",
                 [namespace["source_id"], row["source_id"]], {"namespace": row["namespace"]})
        for owner in row.get("owner_references", []):
            parent = by_uid.get(owner.get("uid"))
            if parent and parent.get("namespace") == row.get("namespace") and (
                parent["name"] == owner.get("name") and parent.get("kind") == owner.get("kind")
            ):
                link(kube_nodes[parent["uid"]], kube_nodes[row["uid"]], "owner_reference",
                     [parent["source_id"], row["source_id"]], {"owner_reference": owner})
        for name in row.get("pvc_names", []):
            pvc = pvcs.get((row.get("namespace"), name))
            if pvc:
                link(kube_nodes[row["uid"]], kube_nodes[pvc["uid"]], "references_pvc", [row["source_id"], pvc["source_id"]],
                     {"namespace": row.get("namespace"), "claim_name": name})
    for namespace in namespaces.values():
        link(root, kube_nodes[namespace["uid"]], "contains_namespace", [namespace["source_id"]], {"namespace_uid": namespace["uid"]})
    for node in inventory.get("nodes", []):
        pool = pools.get(node.get("pool_name"))
        if pool:
            link(arm_nodes[pool["id"].lower()], kube_nodes[node["uid"]], "node_pool_label",
                 [pool["source_id"], node["source_id"]], {"agentpool_label": node["pool_name"]})
        provider = node.get("provider_id")
        if provider and provider.lower().startswith("azure:///subscriptions/"):
            value = provider[len("azure://"):]
            parent = re.split(r"/virtualmachines/", value, flags=re.IGNORECASE)[0]
            link(kube_nodes[node["uid"]], arm_nodes.get(parent.lower()), "backed_by_vmss", [node["source_id"]],
                 {"provider_id": provider})
    by_node_name = {row["name"]: row for row in inventory.get("nodes", [])}
    for pod in inventory.get("pods", []):
        node = by_node_name.get(pod.get("node_name"))
        if node:
            link(kube_nodes[pod["uid"]], kube_nodes[node["uid"]], "scheduled_on", [pod["source_id"], node["source_id"]],
                 {"node_name": pod["node_name"]})
    for service in inventory.get("services", []):
        for workload in inventory.get("workloads", []):
            if workload.get("namespace") == service.get("namespace") and service.get("selector") and (
                selector_matches(service["selector"], workload.get("template_labels")) is True
            ):
                link(kube_nodes[service["uid"]], kube_nodes[workload["uid"]], "selects_workload",
                     [service["source_id"], workload["source_id"]], {"selector": service["selector"], "template_labels": workload.get("template_labels")})
        if service.get("service_type") != "LoadBalancer":
            continue
        matched = False
        for lb, frontend, key in frontends:
            pip = resources.get((frontend.get("public_ip_id") or "").lower())
            address = pick(pip, "configuration", "ipAddress") if frontend.get("public_ip_id") else frontend.get("private_ip")
            if not address or not any(item.get("ip") == address for item in service.get("load_balancer_ingress", [])):
                continue
            internal = service.get("internal_load_balancer")
            if (internal == "true" and frontend.get("public_ip_id")) or (internal == "false" and not frontend.get("public_ip_id")):
                unknown("frontend_annotation_conflict", "service", "Service annotation conflicts with the observed frontend type; no ELB/ILB join.",
                        [service["source_id"], lb["source_id"]], service["resource_id"])
                continue
            matched = True
            link(kube_nodes[service["uid"]], key, "observed_load_balancer_frontend",
                 [service["source_id"], lb["source_id"]] + ([pip["source_id"]] if pip else []),
                 {"service_ingress_ip": address, "frontend_id": frontend["id"], "public_ip_id": frontend.get("public_ip_id"),
                  "internal_annotation": internal, "reachability_tested": False})
        if not matched:
            unknown("load_balancer_frontend_not_joined", "service",
                    "No observed ARM frontend/public-IP address matched Service status; a pending/configured Service is not an observed ELB/ILB.",
                    [service["source_id"], "arm_related_inventory"], service["resource_id"])
    for pvc in pvcs.values():
        pv = pvs.get(pvc.get("volume_name"))
        claim = pv.get("claim_ref", {}) if pv else {}
        if pv and claim.get("namespace") == pvc.get("namespace") and claim.get("name") == pvc["name"] and claim.get("uid") in (None, pvc["uid"]):
            link(kube_nodes[pvc["uid"]], kube_nodes[pv["uid"]], "bound_volume_reference", [pvc["source_id"], pv["source_id"]],
                 {"volume_name": pvc["volume_name"], "claim_ref": claim, "mount_tested": False})
        storage_class = classes.get(pvc.get("storage_class"))
        if storage_class:
            link(kube_nodes[pvc["uid"]], kube_nodes[storage_class["uid"]], "storage_class_reference",
                 [pvc["source_id"], storage_class["source_id"]], {"storage_class": pvc["storage_class"]})
    for pv in pvs.values():
        handle = pv.get("csi_volume_handle")
        if pv.get("csi_driver") == "disk.csi.azure.com" and handle:
            link(kube_nodes[pv["uid"]], arm_nodes.get(handle.lower()), "csi_disk_reference", [pv["source_id"]],
                 {"csi_driver": pv["csi_driver"], "volume_handle": handle, "mount_tested": False})
        if pv.get("csi_driver") == "file.csi.azure.com":
            attributes = pv.get("csi_volume_attributes", {})
            for account in resources.values():
                parts = account["id"].split("/")
                if account["resource_kind"] == "microsoft.storage/storageaccounts" and (
                    account["name"] == attributes.get("storageAccount") and parts[4] == attributes.get("resourceGroup")
                ):
                    link(kube_nodes[pv["uid"]], arm_nodes[account["id"].lower()], "csi_storage_account_reference",
                         [pv["source_id"], account["source_id"]], {"csi_volume_attributes": attributes, "mount_tested": False})
            unknown("azure_files_mount_not_validated", "persistent_volume",
                    "CSI reference is configuration; share data, keys and mount/read success are not collected.", [pv["source_id"]], pv["resource_id"])
    registries = [row for row in resources.values() if row["resource_kind"] == "microsoft.containerregistry/registries" and row.get("login_server")]
    for workload in inventory.get("workloads", []):
        for registry in registries:
            images = [container["image"] for container in workload.get("containers", []) + workload.get("init_containers", [])
                      if container.get("image") and container["image"].split("/", 1)[0].lower() == registry["login_server"].lower()]
            if images:
                link(kube_nodes[workload["uid"]], arm_nodes[registry["id"].lower()], "references_registry_image",
                     [workload["source_id"], registry["source_id"]], {"images": images, "arm_login_server": registry["login_server"],
                     "pull_permission_verified": False, "image_pull_tested": False})
    for role in raw.get("registry_role_assignments", []):
        identity = next((row for row in resources.values() if row.get("principal_id") == role["principal_id"]), None)
        start = arm_nodes[identity["id"].lower()] if identity else root
        link(start, arm_nodes.get(role["resource_id"].lower()), "kubelet_registry_role_assignment",
             ["arm_cluster", role["source_id"]] + ([identity["source_id"]] if identity else []),
             {"role_assignment_id": role["id"], "principal_id": role["principal_id"], "role_scope": role["scope"],
              "role_definition_id": role["role_definition_id"], "condition_present": role["condition_present"],
              "effective_pull_permission_verified": False})
    for registry in registries:
        unknown("effective_registry_pull_not_validated", "container_registry",
                "Observed loginServer/image and optional kubelet role metadata are references, not effective pull permission or image-pull success.",
                [registry["source_id"]], registry["id"])
    if pick(cluster, "addons", "azureKeyvaultSecretsProvider", "enabled") is True:
        unknown("key_vault_mount_not_observed", "key_vault",
                "The addon is configured; no SecretProviderClass, vault mount or secret value is read or inferred.", ["arm_cluster"])
    if cluster.get("power_state") == "Stopped":
        unknown("stopped_cluster_manifests_unavailable", "source",
                "The cluster is observed Stopped. Kubernetes manifests are not collected or inferred empty/healthy, and the collector never starts it.",
                ["arm_cluster", "kube_access"])
    for source in raw["sources"]:
        if source["status"] not in ("complete", "not_applicable") and (
            source["id"].startswith(("kube_", "arm_resource_", "arm_registry_roles_")) or source["id"] in ("arm_cluster", "arm_node_pools", "arm_related_inventory")
        ):
            unknown("architecture_source_incomplete", "source", source["id"] + ": " + source["status"] + ". " + source["note"],
                    [source["id"]], source.get("resource_id"))
    return {"nodes": list(nodes.values()), "edges": list(edges.values()), "unknowns": unknowns}


def multi_snapshot(runs, reference, roster):
    if not 1 <= len(runs) <= MAX_REPORT_CLUSTERS or len({run["cluster_id"].lower() for run in runs}) != len(runs):
        raise EvidenceError("invalid_cluster_runs", "Multi-cluster runs require distinct fixed cluster IDs.", "assessment")
    if any(run["status"] not in ("ok", "partial", "error") or (
        (run["snapshot"] is None) != (run["status"] == "error")
    ) or (run["snapshot"] is None and not isinstance(run["error"], dict)) or (
        run["snapshot"] is not None and run["error"] is not None) for run in runs):
        raise EvidenceError("invalid_cluster_runs", "Each run is an explicit snapshot success/partial or a structured error, never both.", "assessment")
    snapshots = [run["snapshot"] for run in runs if run["snapshot"] is not None]
    provenances = {snapshot["provenance"] for snapshot in snapshots}
    if len(provenances) > 1:
        raise EvidenceError("mixed_provenance", "LIVE and SIMULATED snapshots cannot be combined.", "assessment")
    for run in runs:
        if run["snapshot"] is not None and run["snapshot"]["cluster"]["id"].lower() != run["cluster_id"].lower():
            raise EvidenceError("scope_mismatch", "A cluster run cannot contain another cluster's snapshot.", "assessment")
    # The client block (logo) is stored once at document level; the report re-attaches it to each cluster on load.
    runs = [{**run, "snapshot": {key: value for key, value in run["snapshot"].items() if key != "client"}}
            if run["snapshot"] is not None else run for run in runs]
    checks = [check for snapshot in snapshots for check in snapshot["checks"]]
    scores = {"global": score(checks), "areas": {area: score([row for row in checks if row["area"] == area]) for area in AREAS},
              "pillars": {pillar: score([row for row in checks if row["pillar"] == pillar]) for pillar in PILLARS}}
    scores["coverage"] = dict(scores["global"])
    return {"schema_version": "aks-waf-multi-cluster-v1", "reference_utc": reference,
            "provenance": next(iter(provenances)) if provenances else "LIVE",
            "client": {"name": CLIENT_NAME, "logo_data_uri": CLIENT_LOGO_DATA_URI, "logo_alt": CLIENT_LOGO_ALT},
            "available_clusters": roster, "selected_cluster_names": [run["cluster_name"] for run in runs], "cluster_runs": runs,
            "aggregate": {"scores": scores, "inventory_counts": {
                key: sum(len(snapshot["inventory"].get(key) or []) for snapshot in snapshots)
                for key in ("node_pools", "namespaces", "workloads", "related_resources")},
                "findings_total": sum(len(snapshot["findings"]) for snapshot in snapshots),
                "critical_total": sum(check["status"] == "failed" and check["severity"] == "critical" for check in checks),
                "cluster_status_counts": dict(Counter(run["status"] for run in runs)),
                "inventory_basis": "Observed records from successful snapshots only; failed clusters are unknown, not empty.",
                "score_basis": "Unique cluster/rule/resource checks from available snapshots only; failed clusters are not scored.",
                "failed_cluster_count": sum(run["snapshot"] is None for run in runs),
                "official_waf_score": False,
                "collection_seconds_bound": MAX_COLLECTION_SECONDS, "fleet_seconds_bound": FLEET_DEADLINE_SECONDS,
                "subscription_count": len({row.get("subscription_id") for row in roster}),
                "estimated_savings": None, "actual_cost": None,
                "cost_basis": "Per-cluster billing currency, time window and scope remain separate; no cross-cluster currency/scope sum."}}


def finish_snapshot(raw, reference, provenance="LIVE", environment="UNSPECIFIED"):
    if provenance not in ("LIVE", "SIMULATED") or environment not in ("LAB", "PRODUCTION", "UNSPECIFIED"):
        raise EvidenceError("invalid_provenance", "Explicit source provenance and environment are required.")
    raw = {**raw, "sources": list(raw["sources"]) + [
                source_receipt("reference_catalog", reference, records=CATALOG.get("catalogSnapshot", {}).get("item_count", 0),
                               note="Build-time pinned reference catalog, not a fresh runtime network read."),
                source_receipt("configuration_requirements", reference, "complete" if raw.get("requirements") else "not_configured",
                               records=len(raw.get("requirements", {})), note="Explicit operator intent only; unknown requirements are not inferred.")
    ]}
    checks = evaluate(raw, reference)
    findings = [check for check in checks if check["status"] == "failed"]
    global_score = score(checks)
    scores = {"global": global_score, "coverage": dict(global_score),
                      "areas": {area: score([check for check in checks if check["area"] == area]) for area in AREAS},
                      "pillars": {pillar: score([check for check in checks if check["pillar"] == pillar]) for pillar in PILLARS}}
    blind_spots = [source["id"] for source in raw["sources"] if source["status"] not in ("complete", "not_applicable")]
    critical = sum(check["severity"] == "critical" for check in findings)
    mapped = {rule["checklist_id"] for rule in CATALOG["rules"]}
    catalog_count = CATALOG["catalogSnapshot"]["item_count"]
    return {
                "schema_version": "1.0", "provenance": provenance, "environment": environment, "reference_utc": reference,
                "client": {"name": CLIENT_NAME, "logo_data_uri": CLIENT_LOGO_DATA_URI, "logo_alt": CLIENT_LOGO_ALT},
                "cluster": raw["cluster"], "sources": raw["sources"], "inventory": raw["inventory"],
                "architecture": architecture_for(raw, reference, provenance),
                "source_data": {key: raw.get(key) for key in ("regional_versions", "upgrade_profile", "arm_maintenance", "arm_diagnostics", "advisor", "cost_rows", "registry_role_assignments")},
                "checks": checks, "findings": findings, "scores": scores, "finops": finops_for(raw), "actions": actions_for(findings),
                "executive_messages": [
                    str(len(findings)) + " of the configuration checks failed; " + str(critical) + " critical among them. No invented risks fill a Top 5.",
                    str(global_score["evaluated"]) + " of " + str(global_score["evaluated"] + global_score["not_evaluated"]) + " applicable indicators were evaluated; coverage is reported separately from the score.",
                    str(global_score["not_evaluated"]) + " Not evaluated and " + str(global_score["not_applicable"]) + " Not applicable indicators; neither status means healthy.",
                    str(len(blind_spots)) + " of the sources had incomplete access, configuration or coverage; review the limitations before you prioritize.",
                    "Estimated savings not calculated; actual cost rows: " + str(len(raw.get("cost_rows", []))) + "; current samples kept: "
                    + str(len(raw["inventory"].get("node_metrics", [])) + len(raw["inventory"].get("pod_metrics", []))) + ".",
                ],
                "methodology": {
                    "score_kind": "local_assessment_indicator", "official_waf_score": False, "read_only": True,
                    "score_formula": "100 * passed / (passed + failed), unique cluster/rule/resource check_id. No evaluated checks => null.",
                    "coverage_formula": "100 * evaluated / (evaluated + not_evaluated). N/A excluded. Mapping IDs may repeat across distinct local indicators.",
                    "catalogSnapshot": CATALOG["catalogSnapshot"], "catalog_coverage": {"total_items": catalog_count, "mapped_items": len(mapped),
                        "unmapped_items": catalog_count - len(mapped), "local_rules": len(CATALOG["rules"])},
                    "source_pins": [CATALOG["catalogSnapshot"], {"name": "AKS Well-Architected service guide", **CATALOG["guide"]}],
                    "assessment_url": CATALOG["assessment_url"], "interpretation": CATALOG["interpretation"],
                    "scope": {"cluster_id": raw["cluster"]["id"], "cluster_name": raw["cluster"]["name"], "environment": environment,
                              "requirements": raw.get("requirements", {})},
                    "queries": [{"source_id": source["id"], "command": source.get("read_signature", "Fixed read-only source; see source receipt and README"),
                                 "description": source["note"], "read_limit": {"pages": MAX_PAGES, "rows": MAX_ROWS, "response_bytes": HTTP_BYTES,
                                     "collection_seconds": MAX_COLLECTION_SECONDS, "http_attempts": MAX_HTTP_ATTEMPTS}}
                                for source in raw["sources"] if source["id"] not in ("reference_catalog", "configuration_requirements")],
                    "limitations": [
                        "Point-in-time ARM/configuration assessment and independent per-kind Kubernetes list snapshots, not whole-cluster availability.",
                        "No IaC, DR test, RTO/RPO, license or policy-enforcement evidence is inferred from missing sources or addon flags.",
                        "Kubernetes owner/selector joins require observed fields and namespace; metrics use timestamp/window/sample counts.",
                        "Quick-win/short/medium buckets are advisory planning categories, not measured durations or guaranteed savings.",
                        "This is not an official Microsoft assessment, certification, Polaris or WARA score.",
                    ],
                },
    }

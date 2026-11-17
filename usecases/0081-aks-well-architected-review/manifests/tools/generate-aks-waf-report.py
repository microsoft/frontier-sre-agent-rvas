"""Read-only AKS assessment. Build assets with build_tool.py before SRE paste."""

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
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener
from uuid import UUID, uuid4


SUBSCRIPTION_ID = "<YOUR_SUBSCRIPTION_ID>"
TENANT_ID = "<YOUR_TENANT_ID>"
MANAGED_IDENTITY_CLIENT_ID = "<YOUR_AGENT_CLIENT_ID>"
CLIENT_NAME = "Customer"
CLIENT_LOGO_DATA_URI = ""
CLIENT_LOGO_ALT = "Authorized customer logo"
# Multi-subscription fleet: every APPROVED_CLUSTERS entry inherits CLUSTER_DEFAULTS, so an entry only needs
# "resource_group" plus "subscription_id" when the cluster is outside SUBSCRIPTION_ID. Use "aks_name" when the
# allowlist key is an alias (for example two clusters with the same name in different subscriptions).
CLUSTER_DEFAULTS = {
    "environment": "UNSPECIFIED",
    "kubernetes_enabled": True,
    "include_node_resource_group": True,
    "advisor_enabled": True,
    "approved_related_resource_ids": [],
    "approved_cost_resource_ids": [],
    "cost_scope": "disabled",
    "cost_timeframe": "month_to_date",
    "requirements": {},
}
APPROVED_CLUSTERS = {
    "<APPROVED_AKS_NAME>": {
        "resource_group": "<APPROVED_AKS_RESOURCE_GROUP>",
        "environment": "UNSPECIFIED",
        "kubernetes_enabled": True,
        "include_node_resource_group": True,
        "advisor_enabled": True,
        "approved_related_resource_ids": [],
        "approved_cost_resource_ids": [],
        "cost_scope": "disabled",
        "cost_timeframe": "month_to_date",
        "requirements": {},
    }
}


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
        return {"reference_utc": snapshot["reference_utc"], "fresh_collection": True,
                "provenance": snapshot["provenance"], "selected_cluster_names": snapshot["selected_cluster_names"],
                "cluster_run_status_counts": snapshot["aggregate"]["cluster_status_counts"],
                "source_status_counts": dict(Counter(source["status"] for source in sources)),
                "source_total": len(sources), "source_details_view": "coverage",
                "paging_basis": "Local offset in this collection; later calls recollect, not a stable cross-call cursor."}
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


def inventory_csv_rows(snapshot):
    if snapshot.get("schema_version") == "aks-waf-multi-cluster-v1":
        rows = [row for item in successful_snapshots(snapshot) for row in inventory_csv_rows(item)]
        rows.extend({"collection": "cluster_collection_error", "cluster_id": run["cluster_id"],
                     "cluster_name": run["cluster_name"], "resource_id": run["cluster_id"],
                     "source_id": run["error"]["source"], "observed_at": run["reference_utc"], "details_json": run}
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
              "inventory_counts": aggregate["inventory_counts"] if multi else {
                  key: len(snapshot["inventory"].get(key) or []) for key in ("node_pools", "namespaces", "workloads", "related_resources")},
              "critical_total": sum(row["severity"] == "critical" for row in findings),
              "estimated_savings": None, **{key: str(path) for key, path in paths.items()}}
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
    documents = {
        "report_path": render_html(snapshot), "snapshot_path": snapshot_document,
        "findings_csv_path": csv_document([{**row, "details_json": row} for item in successful_snapshots(snapshot) for row in item["findings"]],
            ("check_id", "checklist_id", "title", "status", "level", "area", "pillar", "severity", "resource_id",
             "cluster_id", "cluster_name", "namespace", "workload_name", "effort", "reason", "recommendation", "learn_url", "details_json")),
        "inventory_csv_path": csv_document(inventory_csv_rows(snapshot),
            ("collection", "resource_id", "cluster_id", "cluster_name", "name", "namespace", "kind", "source_id", "observed_at", "details_json")),
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
            raise EvidenceError("artifact_cleanup_failed", "Artifact failure and cleanup failure; inspect these generated files in the fixed output directory: "
                                + ", ".join(failures), "artifact_storage") from exc
        if isinstance(exc, EvidenceError):
            raise
        raise EvidenceError("artifact_write_failed", "Could not atomically write/read back all four files; this run's partial files were removed.", "artifact_storage") from exc
    return response


def main(operation: str = "report", view: str = "summary", cluster_name: str = "", namespace: str = "",
         workload_name: str = "", area: str = "all", level: str = "all", severity: str = "all",
         status: str = "all", limit: int = 25, offset: int = 0, cluster_names: str = "") -> dict:
    """Collect one or several fixed approved clusters; never change source scope or identity."""
    try:
        params = validate_parameters(operation, view, cluster_name, namespace, workload_name, area, level, severity, status, limit, offset, cluster_names)
        configs, configured = selection_configs(cluster_name, cluster_names)
        if operation == "list_clusters":
            return list_clusters_page(configured, limit, offset)
        selected = {config["name"] for config in configs}
        roster = [roster_row(config) for config in configured if len(configured) <= 5 or config["name"] in selected]
        if not CATALOG.get("rules"):
            raise EvidenceError("catalog_missing", "Use the build-generated whole-file tool, not unbuilt engine.py.", "rule_catalog")
        reference = utc_now()
        if len(configs) == 1:
            config = configs[0]
            raw = collect_live(config, reference)
            snapshot = finish_snapshot(raw, reference, environment=config["environment"])
            snapshot.update(available_clusters=roster, selected_cluster_names=[config["name"]])
        else:
            runs = []
            deadline = time.monotonic() + MAX_COLLECTION_SECONDS
            for config in configs:
                run_reference = utc_now()
                run = {"cluster_id": config["id"], "cluster_name": config["name"], "reference_utc": run_reference,
                       "snapshot": None, "error": None, "status": "error"}
                try:
                    if time.monotonic() >= deadline:
                        raise EvidenceError("collection_deadline", "Shared multi-cluster time bound reached; this cluster was not collected, not empty/healthy.", "collection")
                    raw = collect_live(config, run_reference, deadline=deadline)
                    run["snapshot"] = finish_snapshot(raw, run_reference, environment=config["environment"])
                    run["status"] = "partial" if any(
                        source["status"] not in ("complete", "not_applicable") for source in run["snapshot"]["sources"]) else "ok"
                except EvidenceError as exc:
                    run["error"] = exc.public()
                runs.append(run)
            snapshot = multi_snapshot(runs, reference, roster)
            if not successful_snapshots(snapshot):
                return ensure_response({"status": "error", "error": {
                    "code": "all_clusters_failed", "source": "arm_cluster",
                    "message": "No selected cluster produced a snapshot; no empty/healthy report or files.",
                }, "artifact_status": "not_written", "cluster_errors": [
                    {"cluster_name": run["cluster_name"], "error": {
                        key: run["error"].get(key) for key in ("code", "source", "http_status")
                    }} for run in runs], "provenance": "LIVE"})
        return query_snapshot(snapshot, params) if operation == "query" else write_report(snapshot)
    except EvidenceError as exc:
        return ensure_response({"status": "error", "error": exc.public(),
                                "artifact_status": "cleanup_failed" if exc.code == "artifact_cleanup_failed" else "not_written",
                                "provenance": "LIVE"})


ARM_ORIGIN = "https://management.azure.com"
AKS_AUDIENCE = "6dae42f8-4368-4678-94ff-3960e28e3630"
AKS_API = "2025-05-01"
TRANSPORT_BYTES = 3500
ARTIFACT_BYTES = 4_800_000
HTTP_BYTES = 8_000_000
MAX_PAGES = 100
MAX_ROWS = 20000
MAX_RELATED_RESOURCES = 200
MAX_APPROVED_CLUSTERS = 500
MAX_REPORT_CLUSTERS = 5
ACTIVE_SUBSCRIPTION_ID = None
MAX_COLLECTION_SECONDS = 240
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
    'cluster-error h2 { font-size: 20px; }\n.cluster-picker { max-width: 540px; margin: 16px 0; }\n.cluster'
    '-error { padding: 20px 24px; border: 1px solid var(--critical); border-radius: var(--radius-card); b'
    'ackground: var(--critical-wash); }\n.cluster-error h2 { color: var(--critical); }\n.filter-section { b'
    'ackground: var(--surface); border: 1px solid var(--line); border-radius: var(--radius-card); box-sha'
    'dow: var(--shadow); padding: 20px 24px; }\n.filter-section h2 { font-size: 20px; margin-bottom: 4px; '
    '}\n.filters { display: grid; grid-template-columns: minmax(0, 1.4fr) repeat(3, minmax(0, 1fr)); gap: '
    '16px; margin-top: 16px; }\n.field { display: grid; gap: 6px; min-width: 0; }\n.field label { font-size'
    ': 14px; font-weight: 600; }\n.field input, .field select { width: 100%; min-width: 0; font-size: 14px'
    '; }\n.extra-filters { margin: 12px 0; }\n.extra-filters .filter-extra-grid { display: grid; grid-templ'
    'ate-columns: repeat(3, minmax(0, 1fr)); gap: 16px; margin-top: 8px; }\n.filter-actions { display: fle'
    'x; flex-wrap: wrap; gap: 12px; align-items: center; margin-top: 12px; }\n.filter-actions button { fon'
    't-size: 14px; }\n.scope-path { margin: 16px 0 8px; display: flex; flex-wrap: wrap; gap: 4px 8px; alig'
    'n-items: center; font-size: 14px; }\n.scope-path button { border: 0; padding: 6px 8px; color: var(--a'
    'ccent); background: transparent; min-height: 40px; font-size: 14px; }\n.scope-path button:hover { bac'
    'kground: var(--accent-wash); }\n.scope-path .scope-part { overflow-wrap: anywhere; min-width: 0; max-'
    'width: 100%; }\n.filter-count { margin: 0; font-size: 14px; font-weight: 600; }\n.inventory-counts { d'
    'isplay: flex; flex-wrap: wrap; gap: 8px; margin: 0 0 8px; font-size: 14px; }\n.inventory-counts span '
    '{ padding: 6px 14px; border: 1px solid var(--line); border-radius: 999px; background: var(--surface)'
    '; overflow-wrap: anywhere; }\n.inventory-counts b { font-weight: 600; }\n.inventory-section { margin-t'
    'op: 28px; min-width: 0; }\n.inventory-section h3 { margin-bottom: 10px; }\n.table-scroll { overflow: a'
    'uto; max-width: 100%; background: var(--surface); border: 1px solid var(--line); border-radius: var('
    '--radius-card); box-shadow: var(--shadow); scrollbar-color: var(--field-line) transparent; }\n.table-'
    'scroll[data-overflow="left"] { box-shadow: inset 14px 0 12px -12px var(--cue), var(--shadow); }\n.tab'
    'le-scroll[data-overflow="right"] { box-shadow: inset -14px 0 12px -12px var(--cue), var(--shadow); }'
    '\n.table-scroll[data-overflow="both"] { box-shadow: inset 14px 0 12px -12px var(--cue), inset -14px 0'
    ' 12px -12px var(--cue), var(--shadow); }\ntable { width: 100%; border-collapse: collapse; font-size: '
    '14px; }\n.wide-table { min-width: 680px; }\nth, td { padding: 12px 14px; border-bottom: 1px solid var('
    '--line); vertical-align: top; text-align: left; overflow-wrap: break-word; }\nth { font-weight: 600; '
    'background: var(--subtle); color: var(--ink); }\nthead th { font-size: 12px; letter-spacing: .04em; t'
    'ext-transform: uppercase; color: var(--muted); }\ntbody tr:last-child td, tbody tr:last-child th { bo'
    'rder-bottom: 0; }\ntbody tr:hover > td { background: var(--subtle); }\ntd { max-width: 340px; }\ntd str'
    'ong { font-weight: 600; }\ncaption { text-align: left; padding: 12px 14px; font-size: 13px; color: va'
    'r(--muted); border-bottom: 1px solid var(--line); }\n.cell-note { display: block; color: var(--muted)'
    '; font-size: 13px; margin-top: 4px; }\n.arm-id { font-family: Consolas, ui-monospace, monospace; font'
    '-size: 12.5px; overflow-wrap: break-word; }\n.resource-ref { display: block; min-width: 0; }\n.resourc'
    'e-ref .cell-note { margin-top: 2px; }\n.portal-link { font-size: 13px; font-weight: 600; white-space:'
    ' nowrap; }\n.container-list { margin: 0; padding: 0; list-style: none; display: grid; gap: 8px; }\n.co'
    'ntainer-list .mono { display: block; font-size: 12.5px; color: var(--muted); overflow-wrap: anywhere'
    '; }\n.text-button { border: 0; padding: 4px 0; border-radius: 0; color: var(--accent); background: tr'
    'ansparent; min-height: 32px; text-align: left; font-size: inherit; overflow-wrap: anywhere; }\n.text-'
    'button:hover:not(:disabled) { background: transparent; text-decoration: underline; }\n.table-footer {'
    ' display: flex; gap: 16px; align-items: center; justify-content: space-between; padding: 10px 2px; f'
    'ont-size: 13px; color: var(--muted); flex-wrap: wrap; }\n.table-footer button { font-size: 13px; min-'
    'height: 40px; }\n.empty { padding: 16px 20px; border: 1px dashed var(--field-line); border-radius: va'
    'r(--radius); background: var(--subtle); font-size: 14px; margin: 0; }\ndetails { min-width: 0; }\nsumm'
    'ary { cursor: pointer; font-weight: 600; min-height: 44px; padding: 10px 0; overflow-wrap: anywhere;'
    ' }\nsummary:hover { color: var(--accent); }\nsummary::marker { color: var(--muted); }\n.receipt { margi'
    'n-top: 6px; }\n.receipt summary { font-size: 13px; min-height: 32px; padding: 6px 0; }\n.receipt-conte'
    'nt { margin-top: 8px; }\n.facts { display: grid; grid-template-columns: minmax(110px, .35fr) minmax(0'
    ', 1fr); gap: 8px 20px; margin: 16px 0; font-size: 14px; }\n.facts dt { font-size: 13px; margin: 0; }\n'
    '.facts dd { min-width: 0; }\n.json, .command { margin: 12px 0 0; padding: 12px; font: 12.5px/1.5 Cons'
    'olas, ui-monospace, monospace; background: var(--subtle); border: 1px solid var(--line); border-radi'
    'us: var(--radius); white-space: pre-wrap; overflow-wrap: anywhere; max-height: 28rem; overflow: auto'
    '; }\n.technical-inventory { margin-top: 24px; border-top: 1px solid var(--line); }\n.technical-invento'
    'ry > summary { font-size: 15px; }\n.findings-group { margin-top: 16px; background: var(--surface); bo'
    'rder: 1px solid var(--line); border-radius: var(--radius-card); box-shadow: var(--shadow); overflow:'
    ' hidden; }\n.findings-group > h3 { margin: 0; padding: 10px 20px; font-size: 12px; letter-spacing: .0'
    '5em; text-transform: uppercase; color: var(--muted); background: var(--subtle); border-bottom: 1px s'
    'olid var(--line); }\n.finding { border-top: 1px solid var(--line); }\n.findings-group > h3 + .finding '
    '{ border-top: 0; }\n.finding > summary { position: relative; display: grid; grid-template-columns: 5.'
    '5rem minmax(0, 1fr); gap: 12px; align-items: start; list-style: none; padding: 14px 20px 14px 44px; '
    'font-weight: 400; }\n.finding > summary::-webkit-details-marker { display: none; }\n.finding > summary'
    '::before { content: ""; position: absolute; left: 21px; top: 21px; width: 7px; height: 7px; border-r'
    'ight: 2px solid var(--muted); border-bottom: 2px solid var(--muted); transform: rotate(-45deg); tran'
    'sition: transform .15s ease; }\n.finding[open] > summary::before { transform: rotate(45deg); top: 19p'
    'x; }\n.finding > summary:hover { color: inherit; background: var(--subtle); }\n.finding > summary .sev'
    'erity { margin-top: 1px; justify-self: start; }\n.finding-main { display: grid; gap: 2px; min-width: '
    '0; }\n.finding-title { font-weight: 600; font-size: 15px; }\n.finding-reference { display: block; font'
    '-size: 13px; color: var(--muted); overflow-wrap: anywhere; }\n.finding-body { padding: 0 20px 20px 44'
    'px; }\n.finding-body h4 { margin-top: 20px; }\n.evidence-list { margin: 0; padding-left: 20px; }\n.evid'
    'ence-list li { padding: 10px 0; }\n.evidence-list .facts { margin-top: 0; }\n.evidence-list pre { marg'
    'in-top: 8px; }\n.checks-disclosure { margin-top: 24px; padding: 4px 24px 16px; background: var(--surf'
    'ace); border: 1px solid var(--line); border-radius: var(--radius-card); box-shadow: var(--shadow); }'
    '\n.checks-disclosure > summary { font-size: 16px; }\n.finops-baseline { margin: 0 0 20px; background: '
    'var(--surface); border: 1px solid var(--line); border-radius: var(--radius-card); box-shadow: var(--'
    'shadow); overflow: hidden; }\n.finops-values { display: grid; grid-template-columns: minmax(0, 1fr) m'
    'inmax(0, 1.1fr); }\n.finops-value { padding: 24px; min-width: 0; }\n.finops-value.savings { background'
    ': var(--accent-wash); border-left: 1px solid var(--line); }\n.finops-value h3 { font-size: 16px; marg'
    'in-bottom: 4px; }\n.financial-amount { display: block; font-size: 38px; font-weight: 600; line-height'
    ': 1.2; letter-spacing: -.02em; color: var(--heading); margin: 8px 0 12px; }\n.financial-amount.unknow'
    'n { font-size: 30px; color: var(--muted); }\n.finops-value p:last-child { margin-bottom: 0; }\n.finops'
    '-baseline > .facts { margin: 0; padding: 20px 24px; border-top: 1px solid var(--line); }\n.finops-bas'
    'eline > .qualification { margin: 0; padding: 14px 24px; border-top: 1px solid var(--line); max-width'
    ': none; }\n.finops-notes { padding-left: 20px; margin: 12px 0 24px; max-width: 75ch; font-size: 14px;'
    ' }\n.finops-notes li { padding: 4px 0; }\n.architecture-tabs { display: inline-flex; flex-wrap: wrap; '
    'gap: 4px; margin: 0 0 16px; padding: 4px; background: var(--wash); border-radius: 10px; }\n.architect'
    'ure-tabs button { border-color: transparent; background: transparent; min-height: 40px; font-size: 1'
    '4px; }\n.architecture-tabs button:hover:not(:disabled) { background: var(--surface); }\n.architecture-'
    'tabs button[aria-selected="true"] { background: var(--surface); color: var(--heading); border-color:'
    ' var(--line); box-shadow: var(--shadow); }\n.architecture-note { padding: 16px 20px; background: var('
    '--surface); border: 1px solid var(--line); border-radius: var(--radius-card); margin: 0 0 16px; }\n.a'
    'rchitecture-note h3 { margin-bottom: 6px; }\n.architecture-note p:last-child { margin-bottom: 0; }\n.a'
    'rchitecture-layout { display: grid; grid-template-columns: minmax(0, 1fr) 260px; gap: 16px; align-it'
    'ems: start; }\n.architecture-map { margin: 0; border: 1px solid var(--line); border-radius: var(--rad'
    'ius-card); background: var(--surface); padding: 16px; min-width: 0; box-shadow: var(--shadow); }\n.ar'
    'chitecture-map > svg { display: block; width: 100%; height: auto; }\n.architecture-map figcaption { p'
    'adding-top: 12px; font-size: 13px; color: var(--muted); }\n.graph-line { fill: none; stroke: var(--ac'
    'cent); stroke-width: 1.5; }\n.graph-box { fill: var(--surface); stroke: var(--field-line); }\n.graph-b'
    'ox.selected { fill: var(--accent-wash); stroke: var(--accent); stroke-width: 2; }\n.graph-label { fil'
    'l: var(--ink); font: 600 13px "Segoe UI", system-ui, sans-serif; }\n.graph-kind { fill: var(--muted);'
    ' font: 11px "Segoe UI", system-ui, sans-serif; }\n.graph-node { cursor: pointer; }\n.graph-node:focus-'
    'visible { outline: none; }\n.graph-node:focus-visible .graph-box { stroke-width: 3; stroke: var(--acc'
    'ent); }\n.architecture-tree { border: 1px solid var(--line); border-radius: var(--radius-card); backg'
    'round: var(--surface); box-shadow: var(--shadow); padding: 16px; min-width: 0; max-height: 34rem; ov'
    'erflow: auto; }\n.architecture-tree h3 { font-size: 16px; }\n.architecture-tree summary { font-size: 1'
    '4px; }\n.architecture-tree ul { list-style: none; padding: 0; margin: 0 0 12px; }\n.architecture-tree '
    'button { display: block; width: 100%; padding: 8px; min-height: 40px; text-align: left; font-size: 1'
    '3px; font-weight: 400; border: 0; background: transparent; overflow-wrap: anywhere; }\n.architecture-'
    'tree button[aria-pressed="true"] { background: var(--accent-wash); color: var(--accent); font-weight'
    ': 600; }\n.architecture-tree button:hover { background: var(--wash); }\n.architecture-controls { displ'
    'ay: grid; grid-template-columns: minmax(0, .7fr) minmax(0, 1.3fr); gap: 16px; margin: 0 0 16px; }\n.a'
    'rchitecture-properties { margin-top: 16px; padding: 16px 20px; background: var(--surface); border: 1'
    'px solid var(--line); border-radius: var(--radius-card); }\n.architecture-properties:empty { display:'
    ' none; }\n.architecture-properties > h3 { margin-bottom: 0; }\n.architecture-properties .facts { borde'
    'r-top: 1px solid var(--line); padding-top: 12px; }\n.architecture-product { display: flex; align-item'
    's: center; gap: 12px; min-width: 0; }\n.architecture-product img { width: 40px; height: 40px; flex: 0'
    ' 0 40px; object-fit: contain; }\n.architecture-product strong { font-size: 15px; }\n.architecture-prod'
    'uct .cell-note { font-size: 13px; }\n.reference-diagram { margin: 16px 0; padding: 20px; background: '
    'var(--surface); border: 1px solid var(--line); border-radius: var(--radius-card); box-shadow: var(--'
    'shadow); }\n.reference-entry { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: '
    '24px; padding: 20px; border: 1px dashed var(--field-line); border-radius: var(--radius); }\n.referenc'
    'e-entry > div + div { border-left: 1px solid var(--line); padding-left: 24px; }\n.reference-link { ma'
    'rgin: 0; padding: 12px; text-align: center; font-size: 14px; color: var(--accent); }\n.reference-netw'
    'ork { padding: 24px; border: 1px dashed var(--accent); border-radius: var(--radius); background: var'
    '(--accent-wash); }\n.reference-network > h3 { margin-bottom: 16px; }\n.reference-lanes { display: grid'
    '; grid-template-columns: minmax(0, .7fr) minmax(0, 1.3fr); gap: 20px; }\n.reference-lane { background'
    ': var(--surface); border: 1px solid var(--line); border-radius: var(--radius); padding: 20px; min-wi'
    'dth: 0; }\n.reference-lane h4 { margin-bottom: 14px; }\n.reference-workloads { display: grid; grid-tem'
    'plate-columns: repeat(2, minmax(0, 1fr)); gap: 12px; margin-top: 16px; }\n.reference-workloads p { bo'
    'rder-top: 1px solid var(--line); padding-top: 12px; font-size: 14px; margin: 0; }\n.reference-platfor'
    'm { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 24px; padding: 20px 0 4px;'
    ' }\n.reference-diagram figcaption { font-size: 14px; margin-top: 16px; padding-top: 12px; border-top:'
    ' 1px solid var(--line); }\n.reference-decisions { margin-top: 24px; }\n.action-bucket { margin-top: 28'
    'px; }\n.action-bucket h3 { margin-bottom: 4px; }\n.action-bucket > p { font-size: 14px; }\n.source-erro'
    'rs { margin: 8px 0 0; padding-left: 20px; font-size: 13px; }\n.method-block { margin-top: 20px; }\n.me'
    'thod-block .qualification { margin-top: 12px; }\ndetails.method-block > summary { font-size: 16px; co'
    'lor: var(--heading); }\n.query { padding: 14px 0; border-top: 1px solid var(--line); }\n.query h4 { ov'
    'erflow-wrap: anywhere; }\n.source-url { overflow-wrap: anywhere; font-size: 13px; }\n.report-footer { '
    'margin-top: 56px; padding-top: 20px; border-top: 1px solid var(--line); font-size: 13px; color: var('
    '--muted); }\n.report-footer p { margin-bottom: 6px; max-width: 110ch; }\n.sr-only { position: absolute'
    '; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0, 0, 0, 0); white'
    '-space: nowrap; border: 0; }\n.print-only { display: none; }\n@media screen and (max-width: 1359px) {\n'
    '  .toolbar-nav { display: none; }\n  .toolbar-subtitle { display: inline; }\n  .jump-field { display: '
    'flex; }\n  .jump-field select { max-width: 220px; }\n}\n@media screen and (max-width: 1100px) {\n  .tool'
    'bar-inner { padding-left: 24px; padding-right: 24px; }\n  .toolbar-subtitle { display: none; }\n  .jum'
    'p-field .field-text { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0, 0'
    ', 0, 0); white-space: nowrap; }\n  .jump-field select { max-width: 190px; }\n  .hero-inner { grid-temp'
    'late-columns: minmax(0, 1fr); }\n  .hero-side { grid-template-columns: auto minmax(0, 1fr); align-ite'
    'ms: start; }\n  .card-grid > *, .card-grid > .span-7, .card-grid > .span-5 { grid-column: 1 / -1; }\n '
    ' .pillar-scores { grid-template-columns: repeat(2, minmax(0, 1fr)); }\n  .cover-facts { grid-template'
    '-columns: repeat(3, minmax(0, 1fr)); }\n  .filters { grid-template-columns: repeat(2, minmax(0, 1fr))'
    '; }\n  .architecture-layout { grid-template-columns: minmax(0, 1fr); }\n  .architecture-tree { max-hei'
    'ght: 20rem; }\n  .reference-platform { grid-template-columns: repeat(2, minmax(0, 1fr)); }\n}\n@media s'
    'creen and (min-width: 761px) and (max-width: 900px) {\n  .readonly-chip { display: none; }\n}\n@media s'
    'creen and (max-width: 760px) {\n  .toolbar { position: static; }\n  .toolbar-inner { padding: 10px 16p'
    'x 12px; flex-wrap: wrap; gap: 8px; }\n  .toolbar-brand { flex: 1; }\n  .toolbar-subtitle { display: no'
    'ne; }\n  .toolbar-controls { display: contents; }\n  .readonly-chip { order: 1; }\n  .jump-field { orde'
    'r: 2; flex: 1 1 60%; }\n  .jump-field .field-text { position: absolute; width: 1px; height: 1px; over'
    'flow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; }\n  .jump-field select { flex: 1; max-wid'
    'th: none; min-width: 0; }\n  .theme-field { order: 3; flex: 1 1 30%; }\n  .theme-field select { flex: '
    '1; min-width: 0; }\n  .toolbar-controls button { order: 4; flex: 1 1 40%; }\n  .theme-note { padding: '
    '0 16px 10px; }\n  html { scroll-padding-top: 16px; }\n  .page { padding: 0 16px; }\n  .hero { padding: '
    '28px 16px 84px; }\n  .hero-side { grid-template-columns: minmax(0, 1fr); }\n  h1 { font-size: 28px; li'
    'ne-height: 1.2; max-width: 23ch; }\n  h2 { font-size: 21px; }\n  h3 { font-size: 17px; }\n  .hero .intr'
    'oduction { font-size: 16px; }\n  .chip { white-space: normal; }\n  .brand-plaque { width: 150px; min-h'
    'eight: 64px; padding: 12px; }\n  .brand-plaque img { max-height: 40px; }\n  .brand-placeholder { font-'
    'size: 16px; }\n  .verdict-value { font-size: 22px; }\n  .kpis { grid-template-columns: repeat(2, minma'
    'x(0, 1fr)); gap: 12px; margin-top: -56px; }\n  .kpis .kpi:first-child { grid-column: 1 / -1; }\n  .kpi'
    ' { padding: 14px 16px; }\n  .kpi-value { font-size: 26px; white-space: normal; }\n  .kpi-value.unknown'
    ' { font-size: 18px; }\n  .card, .filter-section { padding: 16px; }\n  .cover-facts { grid-template-col'
    'umns: repeat(2, minmax(0, 1fr)); gap: 14px 16px; }\n  .cover-facts dd { font-size: 14px; }\n  .cover-f'
    'acts .reference-fact { grid-column: 1 / -1; }\n  .chapter, .filter-section, .cluster-overview, .clust'
    'er-error { margin-top: 32px; }\n  .chapter-head { gap: 12px; }\n  .chapter-tools, .chapter-tools butto'
    'n, .chapter-tools .inline-field, .chapter-head > button { width: 100%; }\n  .chapter-tools .inline-fi'
    'eld select { flex: 1; min-width: 0; }\n  .score-layout { grid-template-columns: 1fr; gap: 20px; }\n  .'
    'global-index { padding: 0 0 16px; border-right: 0; border-bottom: 1px solid var(--line); }\n  .score-'
    'value { font-size: 32px; }\n  .pillar-scores, .critical-card { grid-template-columns: 1fr; }\n  .filte'
    'rs, .extra-filters .filter-extra-grid { grid-template-columns: 1fr; gap: 12px; }\n  .filter-actions b'
    'utton { width: 100%; }\n  .facts { grid-template-columns: 1fr; gap: 2px; }\n  .facts dd { margin-botto'
    'm: 10px; }\n  .finding > summary { flex-wrap: wrap; padding: 12px 16px 12px 36px; }\n  .finding > summ'
    'ary::before { left: 16px; }\n  .finding-body { padding: 0 16px 16px; }\n  .findings-group > h3 { paddi'
    'ng: 10px 16px; }\n  .evidence-list { padding-left: 18px; }\n  .checks-disclosure { padding: 4px 16px 1'
    '2px; }\n  .finops-values, .reference-entry, .reference-lanes, .reference-platform, .architecture-cont'
    'rols { grid-template-columns: 1fr; }\n  .finops-value { padding: 18px; }\n  .finops-value.savings { bo'
    'rder-left: 0; border-top: 1px solid var(--line); }\n  .finops-baseline > .facts { padding: 16px 18px;'
    ' }\n  .financial-amount { font-size: 30px; }\n  .financial-amount.unknown { font-size: 26px; }\n  .arch'
    'itecture-tabs { display: grid; width: 100%; }\n  .architecture-note, .reference-network, .reference-l'
    'ane, .reference-entry, .reference-diagram { padding: 16px; }\n  .reference-entry > div + div { border'
    '-left: 0; border-top: 1px solid var(--line); padding-left: 0; padding-top: 20px; }\n  .reference-work'
    'loads { grid-template-columns: 1fr; }\n  .architecture-tree { max-height: 24rem; }\n  .architecture-ma'
    'p { overflow: auto; }\n  .architecture-map > svg { min-width: 640px; }\n  .report-footer { margin-top:'
    ' 36px; }\n}\n@media (prefers-reduced-motion: reduce) {\n  *, *::before, *::after { scroll-behavior: aut'
    'o !important; transition: none !important; animation: none !important; }\n}\n@media (forced-colors: ac'
    'tive) {\n  .score-fill, .distribution-segment, .legend-swatch, .status-swatch { forced-color-adjust: '
    'none; background: CanvasText !important; }\n  .score-track, .distribution-track, .severity, .status-b'
    'ar, .kpi, .card, .verdict { border: 1px solid CanvasText; }\n  .status-bar rect { stroke: CanvasText;'
    ' }\n  .graph-box { fill: Canvas; stroke: CanvasText; }\n  .graph-label, .graph-kind { fill: CanvasText'
    '; }\n  .graph-line { stroke: CanvasText; }\n  :focus-visible { outline-color: Highlight; }\n}\n@page {\n '
    ' size: A4; margin: 14mm 12mm 16mm;\n  @bottom-left { content: var(--print-footer, "AKS architecture a'
    'nd configuration review"); font: 8pt "Segoe UI", system-ui, sans-serif; color: #505050; }\n  @bottom-'
    'right { content: "Page " counter(page) " of " counter(pages); font: 8pt "Segoe UI", system-ui, sans-'
    'serif; color: #505050; }\n}\n@media print {\n  :root, :root[data-theme="dark"] {\n    color-scheme: ligh'
    't;\n    --canvas: #ffffff; --surface: #ffffff; --subtle: #f7f8fa; --wash: #eceef1;\n    --ink: #1f1f1f'
    '; --muted: #505050; --line: #c8cbd0; --field-line: #8a8a8a; --heading: #0c3b5e; --accent: #0f6cbd; -'
    '-accent-wash: #ebf3fc;\n    --critical: #b42318; --critical-wash: #fee4e2; --critical-bar: #d92d20; -'
    '-high: #b93815; --high-wash: #ffead5; --high-bar: #ef6820;\n    --medium: #93370d; --medium-wash: #fe'
    'f0c7; --medium-bar: #f79009; --low: #175cd3; --low-wash: #d1e9ff; --low-bar: #2e90fa;\n    --cover: #'
    '0c3b5e; --cover-ink: #ffffff; --cover-muted: #c7def2; --cover-line: #3f6b90;\n    --nav: #114b77; --n'
    'av-ink: #ffffff; --nav-muted: #d0e4f6;\n    --shadow: none; --shadow-raised: none;\n  }\n  * { print-co'
    'lor-adjust: exact; -webkit-print-color-adjust: exact; }\n  body { background: #ffffff; font-size: 10p'
    't; }\n  .no-print, .toolbar, .skip, button, input, select, .table-footer { display: none !important; '
    '}\n  .print-only { display: block; }\n  .page { max-width: none; padding: 0; }\n  .document { padding: '
    '0; }\n  .hero { padding: 18px 20px 64px; border-radius: 10px; }\n  .hero-inner { grid-template-columns'
    ': minmax(0, 1fr) 200px; gap: 16px 24px; }\n  h1 { font-size: 24pt; }\n  h2 { font-size: 16pt; }\n  h3 {'
    ' font-size: 12pt; }\n  h4 { font-size: 10.5pt; }\n  h1, h2, h3, h4, summary { break-after: avoid; }\n  '
    '.hero .introduction { font-size: 11pt; }\n  .hero-summary, .chip, .verdict-detail, .verdict-note, .di'
    'stribution-legend, .client-line { font-size: 8.5pt; }\n  .brand { display: grid; gap: 8px; }\n  .brand'
    '-plaque { width: 170px; min-height: 60px; padding: 10px; }\n  .verdict { padding: 12px 14px; }\n  .ver'
    'dict-value { font-size: 15pt; }\n  .kpis { grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 8px'
    '; margin-top: -48px; padding: 0 14px; }\n  .kpi { padding: 10px 12px; }\n  .kpi-value { font-size: 18p'
    't; white-space: normal; }\n  .kpi-value.unknown { font-size: 12pt; }\n  .kpi-unit { font-size: 9pt; }\n'
    '  .kpi-label, .kpi-note { font-size: 8pt; }\n  dt { font-size: 7.5pt; }\n  .scope-card h2 { font-size:'
    ' 13pt; }\n  .card, .filter-section, .kpi, .verdict, .table-scroll, .findings-group, .finops-baseline,'
    ' .checks-disclosure, .architecture-map, .architecture-tree, .reference-diagram { box-shadow: none; }'
    '\n  .card-grid > .card, .kpi, .verdict, .score-row, .query, .priority-list li, .next-actions li, .exe'
    'cutive-messages li, .assessment-chart, .finops-values, .reference-entry, .reference-lane { break-ins'
    'ide: avoid; }\n  .cover-facts { grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px 16px; marg'
    'in: 10px 0; }\n  .cover-facts dd { font-size: 9pt; }\n  .cover-id, .snapshot-note { font-size: 8pt; }\n'
    '  .chapter { break-before: page; margin-top: 0; padding-top: 4px; }\n  .cluster-overview, .cluster-er'
    'ror { margin-top: 20px; }\n  .filter-section { padding: 12px 0 0; margin-top: 20px; border: 0; }\n  .f'
    'ilter-section > h2, .filter-section > .qualification, .extra-filters, .scope-path { display: none; }'
    '\n  .card-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }\n  .card-grid > *, .ca'
    'rd-grid > .span-7, .card-grid > .span-5 { grid-column: auto; }\n  .card-grid > .span-12 { grid-column'
    ': 1 / -1; }\n  .card { padding: 12px 14px; }\n  .score-layout { grid-template-columns: 150px minmax(0,'
    ' 1fr); gap: 16px; }\n  .global-index { border-right: 1px solid var(--line); border-bottom: 0; padding'
    '-right: 14px; }\n  .score-value { font-size: 20pt; }\n  .score-value.unknown { font-size: 14pt; }\n  .p'
    'illar-scores { grid-template-columns: repeat(3, minmax(0, 1fr)); }\n  .critical-card { grid-template-'
    'columns: 150px minmax(0, 1fr); }\n  .score-row-head, .score-caption, .qualification, .facts, table, .'
    'snapshot-note, .coverage-note p { font-size: 8.5pt; }\n  .table-scroll { overflow: visible; border-ra'
    'dius: 0; }\n  .wide-table { min-width: 0; table-layout: fixed; }\n  th, td { padding: 5px 6px; max-wid'
    'th: none; font-size: 7.5pt; }\n  thead { display: table-header-group; }\n  tr { break-inside: avoid; }'
    '\n  caption { font-size: 7.5pt; padding: 6px; }\n  .text-button { display: inline !important; color: v'
    'ar(--ink); font-weight: 600; min-height: 0; }\n  details { break-inside: auto; }\n  details > summary '
    '{ list-style: none; min-height: 0; padding: 4px 0; }\n  details > summary::-webkit-details-marker { d'
    'isplay: none; }\n  details:not([open]) > :not(summary) { display: block !important; }\n  .finding > su'
    'mmary { padding: 8px 10px; }\n  .finding > summary::before { display: none; }\n  .finding-title { font'
    '-size: 10pt; }\n  .finding-body { padding: 0 10px 10px; }\n  .facts { grid-template-columns: 110px min'
    'max(0, 1fr); gap: 3px 10px; }\n  .facts dd { margin-bottom: 0; }\n  .json, .command { max-height: none'
    '; overflow: visible; font-size: 6.5pt; line-height: 1.3; padding: 5px 6px; margin-top: 4px; white-sp'
    'ace: pre-wrap; word-break: break-all; }\n  .receipt { margin-top: 2px; }\n  .receipt summary { font-si'
    'ze: 7.5pt; }\n  .print-receipts { margin-top: 6px; }\n  .print-receipts .receipt { margin: 0; padding-'
    'top: 3px; border-top: 1px solid var(--line); }\n  .report-footer { margin-top: 20px; font-size: 8pt; '
    '}\n  .assessment-chart table, .assessment-chart figcaption { font-size: 8pt; }\n  .finops-values { gri'
    'd-template-columns: repeat(2, minmax(0, 1fr)); }\n  .finops-value { padding: 12px 14px; }\n  .financia'
    'l-amount { font-size: 20pt; }\n  .financial-amount.unknown { font-size: 16pt; }\n  .architecture-tabs,'
    ' .architecture-controls, .architecture-tree { display: none !important; }\n  .architecture-layout { d'
    'isplay: block; }\n  .architecture-panel[hidden] { display: block !important; margin-top: 20px; }\n  .a'
    'rchitecture-map { break-inside: avoid; }\n  .architecture-map > svg { min-width: 0; }\n  .reference-en'
    'try, .reference-lanes { grid-template-columns: repeat(2, minmax(0, 1fr)); }\n  .reference-platform { '
    'grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }\n  .architecture-product img { width: '
    '28px; height: 28px; flex-basis: 28px; }\n  .reference-network, .reference-lane, .reference-entry, .re'
    'ference-diagram { padding: 12px; }\n}\n</style>\n</head>\n<body data-status="loading">\n<a class="skip" h'
    'ref="#main">Skip to the report</a>\n<header class="toolbar no-print">\n  <div class="toolbar-inner">\n '
    '   <div class="toolbar-brand"><span class="toolbar-title">Azure SRE Agent</span><span class="toolbar'
    '-subtitle">AKS review</span></div>\n    <nav class="toolbar-nav" aria-label="Report sections">\n      '
    '<a href="#executive">Summary</a><a href="#inventory">Inventory</a><a href="#architecture">Architectu'
    're</a><a href="#findings">Findings</a><a href="#finops">FinOps</a><a href="#actions">Action plan</a>'
    '<a href="#methodology">Method</a>\n    </nav>\n    <div class="toolbar-controls">\n      <span class="r'
    'eadonly-chip">Read-only</span>\n      <label class="jump-field" for="jump-section"><span class="field'
    '-text">Section</span>\n        <select id="jump-section">\n          <option value="cover">Cover and s'
    'cope</option><option value="executive">Executive summary</option>\n          <option value="inventory'
    '">Observed inventory</option><option value="architecture">Architecture</option>\n          <option va'
    'lue="findings">Findings and coverage</option><option value="finops">FinOps</option>\n          <optio'
    'n value="actions">Action plan</option><option value="methodology">Method and sources</option>\n      '
    '  </select>\n      </label>\n      <label class="theme-field" for="theme-mode"><span class="sr-only">C'
    'olor theme</span>\n        <select id="theme-mode"><option value="auto">Theme: system</option><option'
    ' value="light">Theme: light</option><option value="dark">Theme: dark</option></select>\n      </label'
    '>\n      <button id="export-json" disabled>Full JSON</button>\n      <button id="print-report" class="'
    'primary" disabled>Print / PDF</button>\n    </div>\n  </div>\n  <p id="theme-note" class="theme-note qu'
    'alification" hidden></p>\n  <div class="brand-ribbon" aria-hidden="true"><span class="red"></span><sp'
    'an class="green"></span><span class="blue"></span><span class="yellow"></span></div>\n</header>\n<div '
    'id="opening-state" class="opening-state" role="status">\n  <h1>AKS configuration review</h1>\n  <p id='
    '"opening-message">Opening the assessment snapshot.</p>\n  <p id="opening-detail" class="qualification'
    '">The data is validated before any result is shown.</p>\n</div>\n<noscript><div class="opening-state">'
    'This report needs local JavaScript to validate and display the snapshot. It makes no network calls. '
    'Open the file with JavaScript enabled.</div></noscript>\n<div id="report-shell" class="shell" hidden>'
    '\n  <main id="main" class="document" tabindex="-1">\n    <section id="cover" class="cover" aria-labell'
    'edby="report-title">\n      <div class="hero">\n        <div class="hero-inner">\n          <div class='
    '"hero-main">\n            <h1 id="report-title">AKS architecture and configuration review</h1>\n      '
    '      <p class="introduction">Best practices, security, FinOps and optimization for the cluster, its'
    ' workloads and associated resources.</p>\n            <p id="hero-summary" class="hero-summary"></p>\n'
    '            <div id="provenance" class="provenance" aria-label="Provenance, environment and referenc'
    'e"></div>\n          </div>\n          <div class="hero-side">\n            <div class="brand">\n       '
    '       <div id="brand-plaque" class="brand-plaque"></div>\n              <p class="client-line">Prepa'
    'red for <span id="client-name" class="client-name"></span></p>\n            </div>\n            <div i'
    'd="verdict" class="verdict" role="group" aria-labelledby="verdict-label"></div>\n          </div>\n   '
    '       <div id="severity-distribution" class="hero-distribution"></div>\n        </div>\n      </div>\n'
    '      <div class="page">\n        <div id="kpis" class="kpis"></div>\n        <p id="simulation-note" '
    'class="sim-note" hidden></p>\n        <div class="card scope-card">\n          <h2 id="scope-title">Sn'
    'apshot scope</h2>\n          <p class="qualification">Cluster identity, version and state as the sour'
    'ce returned them at the reference time.</p>\n          <dl id="cover-facts" class="cover-facts"></dl>'
    '\n          <div id="cover-id" class="cover-id"></div>\n          <div class="snapshot-note">\n        '
    '    <p><strong>Point-in-time snapshot, not real-time monitoring.</strong>\n            Missing data i'
    's shown as <strong>Not evaluated</strong>; it does not show that a configuration is correct.\n       '
    '     The indexes are local and are not an official Azure, WARA or Polaris assessment.</p>\n          '
    '  <p>Advisory document: any action needs human review and approval.</p>\n          </div>\n        </d'
    'iv>\n      </div>\n    </section>\n    <div class="page">\n    <section id="cluster-error" class="cluste'
    'r-error" role="alert" hidden></section>\n    <section id="cluster-overview" class="cluster-overview c'
    'ard" aria-labelledby="cluster-overview-title" hidden>\n      <h2 id="cluster-overview-title">Clusters'
    ' in this snapshot</h2>\n      <p class="qualification">The selection changes only the local view; it '
    'does not authenticate, collect or deploy another cluster. A failed run keeps its error and never inh'
    'erits data from another cluster.</p>\n      <div id="cluster-aggregate"></div>\n      <div class="fiel'
    'd cluster-picker no-print"><label for="cluster-selector">Cluster for the detailed view</label><selec'
    't id="cluster-selector"></select></div>\n      <div id="cluster-runs-table"></div>\n    </section>\n   '
    ' <section id="executive" class="chapter" aria-labelledby="executive-title">\n      <div class="chapte'
    'r-head">\n        <div><h2 id="executive-title">Executive summary</h2><p class="qualification">Read t'
    'he conclusion together with coverage and source limits.</p></div>\n      </div>\n      <div class="car'
    'd-grid">\n        <div class="card span-7">\n          <div class="score-layout">\n            <div id='
    '"global-index" class="global-index"></div>\n            <div><h3>Local index by area</h3><div id="are'
    'a-scores"></div></div>\n          </div>\n        </div>\n        <div class="card span-5">\n          <'
    'figure id="assessment-chart" class="assessment-chart" aria-labelledby="assessment-chart-title"></fig'
    'ure>\n          <div id="global-coverage" class="coverage-note"></div>\n        </div>\n        <div cl'
    'ass="card span-12 critical-card"><h3 id="critical-title">Critical priorities</h3><div id="critical-f'
    'indings"></div></div>\n        <div class="card span-7">\n          <h3 id="next-actions-title">What t'
    'o do next</h3>\n          <p class="card-sub">First actions of the plan supplied by the engine, by ho'
    'rizon and severity. They need human review and approval.</p>\n          <div id="next-actions"></div>'
    '\n        </div>\n        <div class="card span-5"><h3>Engine summary</h3><ul id="executive-messages" '
    'class="executive-messages"></ul></div>\n        <div class="card span-12"><h3>Local index by Well-Arc'
    'hitected pillar</h3><div id="pillar-scores" class="pillar-scores"></div></div>\n      </div>\n    </se'
    'ction>\n    <section id="scope-filters" class="filter-section" aria-labelledby="filter-title">\n      '
    '<h2 id="filter-title">Explore the scope</h2>\n      <p class="qualification">Cluster → area → namespa'
    'ce → workload. Filters do not recalculate the summary indexes, which cover the full snapshot.</p>\n  '
    '    <form id="filters-form" class="no-print">\n        <div class="filters">\n          <div class="fi'
    'eld"><label for="filter-search">Search evidence</label><input id="filter-search" type="search" place'
    'holder="Name, ID, check or evidence" autocomplete="off"></div>\n          <div class="field"><label f'
    'or="filter-area">Area</label><select id="filter-area"><option value="">All areas</option></select></'
    'div>\n          <div class="field"><label for="filter-namespace">Namespace</label><select id="filter-'
    'namespace"><option value="">All namespaces</option></select></div>\n          <div class="field"><lab'
    'el for="filter-workload">Workload</label><select id="filter-workload"><option value="">All workloads'
    '</option></select></div>\n        </div>\n        <details class="extra-filters" data-detail-key="extr'
    'a-filters">\n          <summary>More filters: level, status and severity</summary>\n          <div cla'
    'ss="filter-extra-grid">\n            <div class="field"><label for="filter-level">Level</label><selec'
    't id="filter-level"><option value="">All levels</option></select></div>\n            <div class="fiel'
    'd"><label for="filter-status">Check status</label><select id="filter-status"><option value="">All st'
    'atuses</option></select></div>\n            <div class="field"><label for="filter-severity">Finding s'
    'everity</label><select id="filter-severity"><option value="">All severities</option></select></div>\n'
    '          </div>\n        </details>\n        <div class="filter-actions"><button type="button" id="re'
    'set-filters">Reset filters</button><button type="button" id="export-filtered-json">Scope JSON (all m'
    'atches)</button></div>\n      </form>\n      <nav id="scope-path" class="scope-path no-print" aria-lab'
    'el="Scope path"></nav>\n      <p id="filter-count" class="filter-count" role="status" aria-live="poli'
    'te" aria-atomic="true"></p>\n      <p id="print-scope" class="print-only"></p>\n    </section>\n    <se'
    'ction id="inventory" class="chapter" aria-labelledby="inventory-title">\n      <div class="chapter-he'
    'ad">\n        <div><h2 id="inventory-title">Observed inventory</h2><p class="qualification">A count o'
    'f the records included, not proof of completeness. Each resource carries its source and date.</p></d'
    'iv>\n        <button id="export-inventory" class="no-print">Export inventory CSV</button>\n      </div'
    '>\n      <div id="inventory-counts" class="inventory-counts"></div>\n      <div class="inventory-secti'
    'on"><h3 id="node-pools-title">Node pools</h3><div id="node-pools"></div></div>\n      <div class="inv'
    'entory-section"><h3 id="namespaces-title">Namespaces</h3><div id="namespaces"></div></div>\n      <di'
    'v class="inventory-section"><h3 id="workloads-title">Workloads</h3><div id="workloads"></div></div>\n'
    '      <div class="inventory-section"><h3 id="related-resources-title">Associated resources</h3><div '
    'id="related-resources"></div></div>\n      <details id="technical-inventory" class="technical-invento'
    'ry" data-detail-key="technical-inventory"><summary>Additional technical inventory</summary><div id="'
    'technical-collections"></div></details>\n    </section>\n    <section id="architecture" class="chapter'
    '" aria-labelledby="architecture-title">\n      <div class="chapter-head">\n        <div><h2 id="archit'
    'ecture-title">Architecture: observed and reference design</h2><p class="qualification">Observed rela'
    'tionships come from specific IDs and fields. The Microsoft proposal is a design alternative, not det'
    'ected or deployed infrastructure.</p></div>\n      </div>\n      <div class="architecture-tabs no-prin'
    't" role="tablist" aria-label="Architecture view">\n        <button id="architecture-observed-tab" rol'
    'e="tab" aria-selected="true" aria-controls="architecture-observed" tabindex="0">Observed architectur'
    'e</button>\n        <button id="architecture-reference-tab" role="tab" aria-selected="false" aria-con'
    'trols="architecture-reference" tabindex="-1">Reference proposal - NOT deployed</button>\n      </div>'
    '\n      <div id="architecture-observed" class="architecture-panel" role="tabpanel" aria-labelledby="a'
    'rchitecture-observed-tab">\n        <div id="architecture-observed-note" class="architecture-note"></'
    'div>\n        <div class="architecture-controls no-print">\n          <div class="field"><label for="a'
    'rchitecture-kind">Resource type</label><select id="architecture-kind"><option value="">All types</op'
    'tion></select></div>\n          <div class="field"><label for="architecture-node">Observed resource /'
    ' object</label><select id="architecture-node"></select></div>\n        </div>\n        <div class="arc'
    'hitecture-layout">\n          <div><figure id="architecture-map" class="architecture-map" aria-label='
    '"Confirmed relationships of the selected resource"></figure><div id="architecture-properties" class='
    '"architecture-properties"></div></div>\n          <aside id="architecture-tree" class="architecture-t'
    'ree" aria-label="Observed resource tree"></aside>\n        </div>\n        <details class="technical-i'
    'nventory" data-detail-key="architecture-nodes"><summary>All observed nodes and identities</summary><'
    'div id="architecture-nodes"></div></details>\n        <details class="technical-inventory" data-detai'
    'l-key="architecture-edges"><summary>All relationships, join fields and evidence</summary><div id="ar'
    'chitecture-edges"></div></details>\n        <details class="technical-inventory" data-detail-key="arc'
    'hitecture-unknowns"><summary>Relationships not evaluated and topology limits</summary><div id="archi'
    'tecture-unknowns"></div></details>\n      </div>\n      <div id="architecture-reference" class="archit'
    'ecture-panel" role="tabpanel" aria-labelledby="architecture-reference-tab" hidden></div>\n    </secti'
    'on>\n    <section id="findings" class="chapter" aria-labelledby="findings-title">\n      <div class="c'
    'hapter-head">\n        <div><h2 id="findings-title">Findings and coverage</h2><p id="findings-count" '
    'class="qualification"></p></div>\n        <div class="chapter-tools no-print">\n          <label class'
    '="inline-field" for="findings-order">Sort\n            <select id="findings-order"><option value="sev'
    'erity">Severity (highest first)</option><option value="model">Engine order</option></select>\n       '
    '   </label>\n          <button id="export-findings">Export findings CSV</button>\n        </div>\n     '
    ' </div>\n      <p class="qualification">Each finding comes from a failed check in the model. Its seve'
    'rity is never assigned to a missing source, and on its own it does not prove a root cause or a certi'
    'fied compliance failure. <a class="no-print" href="#scope-filters">Adjust filters</a></p>\n      <div'
    ' id="findings-list"></div>\n      <div id="findings-pagination"></div>\n      <details class="checks-d'
    'isclosure" data-detail-key="checks-disclosure">\n        <summary>Evaluated, not evaluated and not ap'
    'plicable checks</summary>\n        <p class="qualification">Also includes passed checks. Not evaluate'
    'd keeps its reason; Not applicable does not count toward the index.</p>\n        <button id="export-c'
    'hecks" class="no-print">Export checks CSV</button>\n        <div id="checks-table" class="inventory-s'
    'ection"></div>\n      </details>\n    </section>\n    <section id="finops" class="chapter" aria-labelle'
    'dby="finops-title">\n      <div class="chapter-head">\n        <div><h2 id="finops-title">FinOps: evid'
    'ence before savings</h2><p class="qualification">Utilization, orphaned resources, costs, Spot, reser'
    'vations and autoscaling: only observations and candidates supplied by the engine are shown.</p></div'
    '>\n        <button id="export-finops" class="no-print">Export candidates CSV</button>\n      </div>\n  '
    '    <div id="finops-baseline" class="finops-baseline"></div>\n      <p class="qualification">A candid'
    'ate needs a review of its window, sample size and business need. When no estimate is supplied, savin'
    'gs are <strong>To be estimated / Not calculated</strong>: not zero and not a promised return.</p>\n  '
    '    <ul id="finops-notes" class="finops-notes"></ul>\n      <h3 id="finops-candidates-title">Candidat'
    'es in the selected scope</h3>\n      <div id="finops-candidates"></div>\n      <details class="technic'
    'al-inventory" data-detail-key="finops-receipts"><summary>Cost and utilization records included</summ'
    'ary><div id="finops-receipts"></div></details>\n    </section>\n    <section id="actions" class="chapt'
    'er" aria-labelledby="actions-title">\n      <div class="chapter-head">\n        <div><h2 id="actions-t'
    'itle">Action plan for human review</h2><p class="qualification">Indicative horizons, not delivery co'
    "mmitments. Effort and impact need the owner's validation; this report runs no action.</p></div>\n    "
    '    <button id="export-actions" class="no-print">Export plan CSV</button>\n      </div>\n      <div id'
    '="action-plan"></div>\n    </section>\n    <section id="methodology" class="chapter" aria-labelledby="'
    'methodology-title">\n      <div class="chapter-head">\n        <div><h2 id="methodology-title">Method,'
    ' sources and read limits</h2><p class="qualification">How the local index is calculated, which sourc'
    'es were read and with what limits.</p></div>\n      </div>\n      <div class="method-block card">\n    '
    '    <h3>How to read the local index</h3>\n        <p class="prose">Local index = 100 × passed checks '
    '/ evaluated checks. Coverage compares evaluated checks with evaluated plus not evaluated checks. Not'
    ' applicable checks are excluded from both denominators.</p>\n        <p class="prose">The engine iden'
    'tifies each check by a unique <code>check_id</code> and never counts it twice in the overall index w'
    'hen you browse namespaces. This view shows the indexes it receives; it does not re-evaluate controls'
    ' or generate recommendations.</p>\n        <p class="prose"><strong>This is not an official Azure Ass'
    'essment, Azure Well-Architected, WARA or Polaris score.</strong> The references guide the review; th'
    'ey do not prove compliance, absence of risk, an SLA or a root cause.</p>\n        <div id="method-sco'
    'pe"></div>\n      </div>\n      <div class="method-block"><h3 id="sources-title">Source register</h3><'
    'div id="sources-table"></div></div>\n      <details class="technical-inventory" data-detail-key="sour'
    'ce-data">\n        <summary>Additional observations kept</summary>\n        <p class="qualification">A'
    'dditional receipts from the full model. They do not become new checks and are not presented as compl'
    'iant configurations.</p>\n        <div id="source-data-receipts"></div>\n      </details>\n      <div c'
    'lass="method-block card"><h3>Catalog and pinned references</h3><div id="catalog-pins"></div></div>\n '
    '     <details class="method-block card" data-detail-key="method-queries"><summary id="queries-title"'
    '>Included queries and limits</summary><div id="queries"></div></details>\n      <div class="method-bl'
    'ock card"><h3>Declared limitations</h3><div id="limitations"></div></div>\n    </section>\n    <footer'
    ' class="report-footer">\n      <p id="footer-reference"></p>\n      <p>Self-contained, read-only file.'
    ' Data and exports stay local; review the identities and evidence it contains before you share it.</p'
    '>\n      <p>Interface test screenshots use explicitly simulated data, not customer observations.</p>\n'
    '    </footer>\n    </div>\n  </main>\n</div>\n<script type="application/json" id="report-data">__REPORT_'
    'DATA_JSON__</script>\n<script>\n"use strict";\n(() => {\n  const AREA = new Map([["best_practices", "Bes'
    't practices"], ["security", "Security"], ["finops", "FinOps"], ["optimization", "Optimization"]]);\n '
    ' const PILLAR = new Map([["reliability", "Reliability"], ["security", "Security"], ["cost", "Cost Op'
    'timization"], ["operations", "Operational Excellence"], ["performance", "Performance Efficiency"]]);'
    '\n  const LEVEL = new Map([["cluster", "Cluster"], ["workload", "Workload"], ["resource", "Associated'
    ' resource"]]);\n  const STATUS = new Map([["passed", "Passed"], ["failed", "Failed"], ["not_evaluated'
    '", "Not evaluated"], ["not_applicable", "Not applicable"]]);\n  const SEVERITY = new Map([["critical"'
    ', "Critical"], ["high", "High"], ["medium", "Medium"], ["low", "Low"]]);\n  const EFFORT = new Map([['
    '"low", "Low"], ["medium", "Medium"], ["high", "High"]]);\n  const SOURCE_STATUS = new Map([["complete'
    '", "Complete"], ["partial", "Partial"], ["denied", "Access denied"], ["error", "Read error"], ["not_'
    'configured", "Not configured"], ["not_applicable", "Not applicable"]]);\n  const COLLECTION = new Map'
    '([["node_pools", "Node pools"], ["namespaces", "Namespaces"], ["workloads", "Workloads"], ["related_'
    'resources", "Associated resources"], ["nodes", "Nodes"], ["pods", "Pods"], ["services", "Services"],'
    ' ["storage_classes", "Storage classes"], ["pvcs", "Persistent volume claims (PVC)"], ["pvs", "Persis'
    'tent volumes (PV)"], ["pdbs", "Pod disruption budgets (PDB)"], ["hpas", "Horizontal pod autoscalers '
    '(HPA)"], ["network_policies", "Network policies"], ["resource_quotas", "Resource quotas"], ["metrics'
    '", "Metrics"]]);\n  const BUCKET = new Map([["quick_win", ["Quick wins / less than a week", "Indicati'
    've planning priority; the timeline is not guaranteed."]], ["short_term", ["Short term / one to three'
    ' months", "Coordinate dependencies, owners and change windows."]], ["medium_term", ["Medium term / h'
    'orizon to agree", "Confirm the design, business need and sequence with the owner."]]]);\n  const PAGE'
    '_SIZE = 25;\n  const MAX_BYTES = 4800000;\n  const RUN_STATUS = new Map([["ok", "Collected"], ["partia'
    'l", "Partial"], ["error", "Collection error"]]);\n  const GRAPH_KINDS = new Map([["aks", "Azure Kuber'
    'netes Service (AKS)"], ["cluster", "Azure Kubernetes Service (AKS)"],\n    ["node_pool", "Node pool"]'
    ', ["namespace", "Namespace"], ["workload", "Workload"], ["service", "Kubernetes Service"],\n    ["loa'
    'd_balancer", "Azure Load Balancer"], ["public_load_balancer", "Public Azure Load Balancer (ELB)"],\n '
    '   ["private_load_balancer", "Private Azure Load Balancer (ILB)"], ["subnet", "Subnet"], ["vnet", "A'
    'zure Virtual Network"],\n    ["nsg", "Network Security Group"], ["disk", "Azure Managed Disk"], ["pvc'
    '", "Kubernetes PVC"], ["pv", "Kubernetes PV"],\n    ["acr", "Azure Container Registry"], ["key_vault"'
    ', "Azure Key Vault"], ["identity", "Managed Identity"],\n    ["storage", "Azure Storage"], ["ingress"'
    ', "Kubernetes Ingress"]]);\n  for (const [key, label] of [["agent_pool", "AKS node pool"], ["managed_'
    'cluster", "Azure Kubernetes Service (AKS)"],\n    ["azure_load_balancer", "Azure Load Balancer"], ["l'
    'oad_balancer_frontend_public", "Azure Load Balancer / public frontend (ELB)"],\n    ["load_balancer_f'
    'rontend_private", "Azure Load Balancer / private frontend (ILB)"], ["load_balancer_backend_pool", "A'
    'zure Load Balancer / backend pool"],\n    ["load_balancer_probe", "Azure Load Balancer / probe"], ["l'
    'oad_balancer_rule", "Azure Load Balancer / rule"],\n    ["managed_disk", "Azure Managed Disk"], ["vir'
    'tual_machine_scale_set", "Azure Virtual Machine Scale Set"],\n    ["virtual_network", "Azure Virtual '
    'Network"], ["network_security_group", "Network Security Group"],\n    ["public_ip_address", "Azure Pu'
    'blic IP Address"], ["container_registry", "Azure Container Registry"],\n    ["persistent_volume", "Ku'
    'bernetes PV"], ["persistent_volume_claim", "Kubernetes PVC"],\n    ["replica_set", "Kubernetes Replic'
    'aSet"], ["pod", "Kubernetes Pod"], ["node", "Kubernetes node"]]) GRAPH_KINDS.set(key, label);\n  /* O'
    'FFICIAL_AZURE_ICON_DATA_START */\n  const AZURE_ICONS = new Map([["aks","data:image/svg+xml;base64,PH'
    'N2ZyBpZD0iYWY2YTJjNDItYmQ0OC00ODU3LWE0NzktYWVjZjhiM2RlNGY2IiB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC'
    '9zdmciIHdpZHRoPSIxOCIgaGVpZ2h0PSIxOCIgdmlld0JveD0iMCAwIDE4IDE4Ij48ZGVmcz48bGluZWFyR3JhZGllbnQgaWQ9Im'
    'I3MGM5Y2YxLWJhYjgtNDdlMC1iYmRiLWNlMWNkNjY0ZDI2OCIgeDE9IjIuOTQiIHkxPSIzLjc0IiB4Mj0iOC42NyIgeTI9IjMuNz'
    'QiIGdyYWRpZW50VW5pdHM9InVzZXJTcGFjZU9uVXNlIj48c3RvcCBvZmZzZXQ9IjAiIHN0b3AtY29sb3I9IiNiNzdhZjQiIC8+PH'
    'N0b3Agb2Zmc2V0PSIxIiBzdG9wLWNvbG9yPSIjNzczYWRjIiAvPjwvbGluZWFyR3JhZGllbnQ+PGxpbmVhckdyYWRpZW50IGlkPS'
    'JiZWI2OTk1My1iZDk2LTQ1MTUtODg0My1hYzEyNTQ2YWY5MzYiIHgxPSI5LjEzIiB5MT0iMy43OSIgeDI9IjE0Ljg1IiB5Mj0iMy'
    '43OSIgZ3JhZGllbnRVbml0cz0idXNlclNwYWNlT25Vc2UiPjxzdG9wIG9mZnNldD0iMCIgc3RvcC1jb2xvcj0iI2I3N2FmNCIgLz'
    '48c3RvcCBvZmZzZXQ9IjEiIHN0b3AtY29sb3I9IiM3NzNhZGMiIC8+PC9saW5lYXJHcmFkaWVudD48bGluZWFyR3JhZGllbnQgaW'
    'Q9ImEzOWM3NmU4LTU0N2UtNGViNC1iYzI1LWQ4MWMwZjhjZGE2MiIgeDE9IjAuMDEiIHkxPSI5LjEyIiB4Mj0iNS43MyIgeTI9Ij'
    'kuMTIiIGdyYWRpZW50VW5pdHM9InVzZXJTcGFjZU9uVXNlIj48c3RvcCBvZmZzZXQ9IjAiIHN0b3AtY29sb3I9IiNiNzdhZjQiIC'
    '8+PHN0b3Agb2Zmc2V0PSIxIiBzdG9wLWNvbG9yPSIjNzczYWRjIiAvPjwvbGluZWFyR3JhZGllbnQ+PGxpbmVhckdyYWRpZW50IG'
    'lkPSJmMGEyYTQ5MS0xN2RjLTRiYjgtYmJmYy1lZTU4YTVjZjQ3ZGEiIHgxPSI2LjE4IiB5MT0iOS4wOCIgeDI9IjExLjkiIHkyPS'
    'I5LjA4IiBncmFkaWVudFVuaXRzPSJ1c2VyU3BhY2VPblVzZSI+PHN0b3Agb2Zmc2V0PSIwIiBzdG9wLWNvbG9yPSIjYjc3YWY0Ii'
    'AvPjxzdG9wIG9mZnNldD0iMSIgc3RvcC1jb2xvcj0iIzc3M2FkYyIgLz48L2xpbmVhckdyYWRpZW50PjxsaW5lYXJHcmFkaWVudC'
    'BpZD0iZWZjNmE1NmQtODU4NS00MTdkLTkzMWEtMWRhYzIxMTRjY2QwIiB4MT0iMTIuMzUiIHkxPSI5LjEzIiB4Mj0iMTguMDgiIH'
    'kyPSI5LjEzIiBncmFkaWVudFVuaXRzPSJ1c2VyU3BhY2VPblVzZSI+PHN0b3Agb2Zmc2V0PSIwIiBzdG9wLWNvbG9yPSIjYjc3YW'
    'Y0IiAvPjxzdG9wIG9mZnNldD0iMSIgc3RvcC1jb2xvcj0iIzc3M2FkYyIgLz48L2xpbmVhckdyYWRpZW50PjxsaW5lYXJHcmFkaW'
    'VudCBpZD0iZTM5OWFhOTMtMzQxZi00ZGYyLTljMDItNjAzYjgyYjQ4NGMyIiB4MT0iMi44NyIgeTE9IjE0LjU2IiB4Mj0iOC42Ii'
    'B5Mj0iMTQuNTYiIGdyYWRpZW50VW5pdHM9InVzZXJTcGFjZU9uVXNlIj48c3RvcCBvZmZzZXQ9IjAiIHN0b3AtY29sb3I9IiNiNz'
    'dhZjQiIC8+PHN0b3Agb2Zmc2V0PSIxIiBzdG9wLWNvbG9yPSIjNzczYWRjIiAvPjwvbGluZWFyR3JhZGllbnQ+PGxpbmVhckdyYW'
    'RpZW50IGlkPSJhMTUyYmJhMC1iYTJiLTQ4M2EtYjhjMS0wYWU3ZGUzNTU5OTAiIHgxPSI5LjA1IiB5MT0iMTQuNiIgeDI9IjE0Lj'
    'c4IiB5Mj0iMTQuNiIgZ3JhZGllbnRVbml0cz0idXNlclNwYWNlT25Vc2UiPjxzdG9wIG9mZnNldD0iMCIgc3RvcC1jb2xvcj0iI2'
    'I3N2FmNCIgLz48c3RvcCBvZmZzZXQ9IjEiIHN0b3AtY29sb3I9IiM3NzNhZGMiIC8+PC9saW5lYXJHcmFkaWVudD48L2RlZnM+PH'
    'RpdGxlPkljb24tY29tcHV0ZS0yMzwvdGl0bGU+PHBvbHlnb24gcG9pbnRzPSI1LjggMS4yMiAyLjk0IDEuNzUgMi45NCA1LjY1ID'
    'UuOCA2LjI2IDguNjcgNS4xMSA4LjY3IDIuMiA1LjggMS4yMiIgZmlsbD0idXJsKCNiNzBjOWNmMS1iYWI4LTQ3ZTAtYmJkYi1jZT'
    'FjZDY2NGQyNjgpIiAvPjxwYXRoIGQ9Ik01LjkxLDYuMiw4LjUzLDUuMTRBLjIuMiwwLDAsMCw4LjY1LDVWMi4zNmEuMjEuMjEsMC'
    'wwLDAtLjEzLS4xOGwtMi42NS0uOUg1Ljc1bC0yLjYuNDhBLjIuMiwwLDAsMCwzLDEuOTRWNS40N2EuMTkuMTksMCwwLDAsLjE1Lj'
    'E5bDIuNjMuNTVBLjMyLjMyLDAsMCwwLDUuOTEsNi4yWiIgZmlsbD0ibm9uZSIgLz48cGF0aCBkPSJNMi45NCwxLjc1djMuOWwyLj'
    'g5LjYxdi01Wm0xLjIyLDMuNi0uODEtLjE2di0zbC44MS0uMTNabTEuMjYuMjMtLjkzLS4xNVYybC45My0uMTZaIiBmaWxsPSIjMz'
    'QxYTZlIiAvPjxwb2x5Z29uIHBvaW50cz0iMTEuOTkgMS4yNyA5LjEzIDEuOCA5LjEzIDUuNyAxMS45OSA2LjMxIDE0Ljg1IDUuMT'
    'UgMTQuODUgMi4yNSAxMS45OSAxLjI3IiBmaWxsPSJ1cmwoI2JlYjY5OTUzLWJkOTYtNDUxNS04ODQzLWFjMTI1NDZhZjkzNikiIC'
    '8+PHBhdGggZD0iTTkuMTMsMS44VjUuN0wxMiw2LjMxdi01Wm0xLjIxLDMuNi0uODEtLjE2di0zbC44MS0uMTNabTEuMjYuMjMtLj'
    'kzLS4xNVYyLjA1bC45My0uMTdaIiBmaWxsPSIjMzQxYTZlIiAvPjxwb2x5Z29uIHBvaW50cz0iMi44NyA2LjYgMC4wMSA3LjEzID'
    'AuMDEgMTEuMDMgMi44NyAxMS42NCA1Ljc0IDEwLjQ5IDUuNzQgNy41OCAyLjg3IDYuNiIgZmlsbD0idXJsKCNhMzljNzZlOC01ND'
    'dlLTRlYjQtYmMyNS1kODFjMGY4Y2RhNjIpIiAvPjxwYXRoIGQ9Ik0wLDcuMTNWMTFsMi44OS42MXYtNVptMS4yMSwzLjYxLS44MS'
    '0uMTd2LTNsLjgxLS4xNFpNMi40OCwxMWwtLjkzLS4xNVY3LjM4bC45My0uMTZaIiBmaWxsPSIjMzQxYTZlIiAvPjxwb2x5Z29uIH'
    'BvaW50cz0iOS4wNCA2LjU2IDYuMTggNy4wOSA2LjE4IDEwLjk5IDkuMDQgMTEuNjEgMTEuOSAxMC40NSAxMS45IDcuNTQgOS4wNC'
    'A2LjU2IiBmaWxsPSJ1cmwoI2YwYTJhNDkxLTE3ZGMtNGJiOC1iYmZjLWVlNThhNWNmNDdkYSkiIC8+PHBhdGggZD0iTTYuMTgsNy'
    '4wOVYxMWwyLjg4LjYxdi01Wk03LjM5LDEwLjdsLS44MS0uMTd2LTNsLjgxLS4xNFptMS4yNi4yMi0uOTMtLjE1VjcuMzRsLjkzLS'
    '4xNloiIGZpbGw9IiMzNDFhNmUiIC8+PHBvbHlnb24gcG9pbnRzPSIxNS4yMSA2LjYxIDEyLjM1IDcuMTQgMTIuMzUgMTEuMDQgMT'
    'UuMjEgMTEuNjUgMTguMDggMTAuNSAxOC4wOCA3LjU5IDE1LjIxIDYuNjEiIGZpbGw9InVybCgjZWZjNmE1NmQtODU4NS00MTdkLT'
    'kzMWEtMWRhYzIxMTRjY2QwKSIgLz48cGF0aCBkPSJNMTIuMzUsNy4xNFYxMWwyLjg5LjYxdi01Wm0xLjIyLDMuNjEtLjgxLS4xN3'
    'YtM2wuODEtLjE0Wm0xLjI2LjIyLS45My0uMTVWNy4zOWwuOTMtLjE2WiIgZmlsbD0iIzM0MWE2ZSIgLz48cG9seWdvbiBwb2ludH'
    'M9IjUuNzMgMTIuMDQgMi44NyAxMi41NiAyLjg3IDE2LjQ2IDUuNzMgMTcuMDggOC42IDE1LjkyIDguNiAxMy4wMiA1LjczIDEyLj'
    'A0IiBmaWxsPSJ1cmwoI2UzOTlhYTkzLTM0MWYtNGRmMi05YzAyLTYwM2I4MmI0ODRjMikiIC8+PHBhdGggZD0iTTUuODQsMTcsOC'
    '40NSwxNmEuMTguMTgsMCwwLDAsLjEyLS4xOHYtMi42QS4yLjIsMCwwLDAsOC40NCwxM0w1LjgsMTIuMWEuMTcuMTcsMCwwLDAtLj'
    'EyLDBsLTIuNi40N2EuMTkuMTksMCwwLDAtLjE2LjE5djMuNTRhLjE5LjE5LDAsMCwwLC4xNS4xOUw1LjcsMTdBLjIzLjIzLDAsMC'
    'wwLDUuODQsMTdaIiBmaWxsPSJub25lIiAvPjxwYXRoIGQ9Ik0yLjg3LDEyLjU2djMuOWwyLjg5LjYyVjEyWm0xLjIyLDMuNjFMMy'
    '4yOCwxNlYxM2wuODEtLjE0Wm0xLjI2LjIzLS45My0uMTVWMTIuODFsLjkzLS4xNloiIGZpbGw9IiMzNDFhNmUiIC8+PHBvbHlnb2'
    '4gcG9pbnRzPSIxMS45MSAxMi4wOCA5LjA1IDEyLjYxIDkuMDUgMTYuNTEgMTEuOTEgMTcuMTIgMTQuNzggMTUuOTcgMTQuNzggMT'
    'MuMDYgMTEuOTEgMTIuMDgiIGZpbGw9InVybCgjYTE1MmJiYTAtYmEyYi00ODNhLWI4YzEtMGFlN2RlMzU1OTkwKSIgLz48cGF0aC'
    'BkPSJNOS4wNSwxMi42MXYzLjlsMi44OS42MXYtNVptMS4yMiwzLjYxLS44MS0uMTd2LTNsLjgxLS4xNFptMS4yNi4yMi0uOTMtLj'
    'E1VjEyLjg2bC45My0uMTZaIiBmaWxsPSIjMzQxYTZlIiAvPjwvc3ZnPg=="],["load_balancer","data:image/svg+xml;ba'
    'se64,PHN2ZyBpZD0iZTFlNzFlMjktMDY1YS00NmY3LWFkNGItNTJhZjM2YTBiZmNiIiB4bWxucz0iaHR0cDovL3d3dy53My5vcmc'
    'vMjAwMC9zdmciIHdpZHRoPSIxOCIgaGVpZ2h0PSIxOCIgdmlld0JveD0iMCAwIDE4IDE4Ij48ZGVmcz48bGluZWFyR3JhZGllbnQ'
    'gaWQ9ImVmODQ2NjNhLWE3YjYtNDZhNy1hMjc1LTFlNDE5ZjVlYWU2MiIgeDE9IjkiIHkxPSIxOS44NSIgeDI9IjkiIHkyPSItMS4'
    'wMiIgZ3JhZGllbnRVbml0cz0idXNlclNwYWNlT25Vc2UiPjxzdG9wIG9mZnNldD0iMCIgc3RvcC1jb2xvcj0iIzVlOTYyNCIgLz4'
    '8c3RvcCBvZmZzZXQ9IjAuMDIiIHN0b3AtY29sb3I9IiM1Zjk3MjQiIC8+PHN0b3Agb2Zmc2V0PSIxIiBzdG9wLWNvbG9yPSIjNzZ'
    'iYzJkIiAvPjwvbGluZWFyR3JhZGllbnQ+PC9kZWZzPjx0aXRsZT5JY29uLW5ldHdvcmtpbmctNjI8L3RpdGxlPjxwYXRoIGQ9Ik0'
    'uMTgsOC41Nyw4LjU3LjE4YS42LjYsMCwwLDEsLjg2LDBsOC4zOSw4LjM5YS42LjYsMCwwLDEsMCwuODZsLTguNCw4LjRhLjYuNiw'
    'wLDAsMS0uODQsMEwuMTgsOS40M0EuNi42LDAsMCwxLC4xOCw4LjU3WiIgZmlsbD0idXJsKCNlZjg0NjYzYS1hN2I2LTQ2YTctYTI'
    '3NS0xZTQxOWY1ZWFlNjIpIiAvPjxwYXRoIGQ9Ik0xMS4yLDQsOS4wOCwxLjg5YS4xMi4xMiwwLDAsMC0uMTYsMEw2LjgsNGEuMS4'
    'xLDAsMCwwLC4wOC4xOEg4LjEyYS4xMS4xMSwwLDAsMSwuMTEuMTF2MmEuMTEuMTEsMCwwLDAsLjExLjExSDkuNjZhLjExLjExLDA'
    'sMCwwLC4xMS0uMTF2LTJhLjExLjExLDAsMCwxLC4xMS0uMTFoMS4yNEEuMS4xLDAsMCwwLDExLjIsNFoiIGZpbGw9IiNiNGVjMzY'
    'iIC8+PHBhdGggZD0iTTQsNi42MSwxLjksOC43NGEuMTEuMTEsMCwwLDAsMCwuMTVMNCwxMWEuMTEuMTEsMCwwLDAsLjE5LS4wOFY'
    '5LjY5YS4xMS4xMSwwLDAsMSwuMTEtLjExaDJhLjEuMSwwLDAsMCwuMS0uMTFWOC4xNUEuMS4xLDAsMCwwLDYuMzMsOGgtMmEuMS4'
    'xLDAsMCwxLS4xMS0uMVY2LjY5QS4xMS4xMSwwLDAsMCw0LDYuNjFaIiBmaWxsPSIjYjRlYzM2IiAvPjxwYXRoIGQ9Ik0xNC4wOCw'
    'xMWwyLjEzLTIuMTJhLjExLjExLDAsMCwwLDAtLjE1TDE0LjA4LDYuNjFhLjExLjExLDAsMCwwLS4xOC4wOFY3Ljk0YS4xLjEsMCw'
    'wLDEtLjExLjFoLTJhLjEuMSwwLDAsMC0uMS4xMVY5LjQ3YS4xLjEsMCwwLDAsLjEuMTFoMmEuMTEuMTEsMCwwLDEsLjExLjExdjE'
    'uMjRBLjExLjExLDAsMCwwLDE0LjA4LDExWiIgZmlsbD0iI2I0ZWMzNiIgLz48cGF0aCBkPSJNMTEuNzksOWEyLjc5LDIuNzksMCw'
    'xLDAtMy41NCwyLjY3di45NWExLjcxLDEuNzEsMCwxLDAsMS41Nywwdi0xQTIuNzcsMi43NywwLDAsMCwxMS43OSw5WiIgZmlsbD0'
    'iI2ZmZiIgLz48Y2lyY2xlIGlkPSJlOTljMzM4Ny0xNWMzLTRmMjgtYmQ0Yi1jYjIwOWI0MzBlMDYiIGN4PSI5LjAxIiBjeT0iOC4'
    '5OSIgcj0iMS42MiIgZmlsbD0iIzVlYTBlZiIgLz48L3N2Zz4="],["virtual_network","data:image/svg+xml;base64,PH'
    'N2ZyBpZD0iYTE2MDZhNTItZmIxNC00NjM3LTg3ZGUtNGQ1MjRiYmExODI5IiB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC'
    '9zdmciIHdpZHRoPSIxOCIgaGVpZ2h0PSIxOCIgdmlld0JveD0iMCAwIDE4IDE4Ij48ZGVmcz48bGluZWFyR3JhZGllbnQgaWQ9Im'
    'YwMjBmYjdlLTIyNDMtNDUwMS04MTUzLTVkNjliZDNjMzRmNyIgeDE9IjkuODgiIHkxPSI4LjU5IiB4Mj0iMTEuNTIiIHkyPSIxMC'
    '4yMyIgZ3JhZGllbnRUcmFuc2Zvcm09InRyYW5zbGF0ZSgyLjAzIC0wLjQpIHJvdGF0ZSgtMC4wOCkiIGdyYWRpZW50VW5pdHM9In'
    'VzZXJTcGFjZU9uVXNlIj48c3RvcCBvZmZzZXQ9IjAiIHN0b3AtY29sb3I9IiM4NmQ2MzMiIC8+PHN0b3Agb2Zmc2V0PSIxIiBzdG'
    '9wLWNvbG9yPSIjNWU5NjI0IiAvPjwvbGluZWFyR3JhZGllbnQ+PGxpbmVhckdyYWRpZW50IGlkPSJiM2MyYmM5NC04YzdjLTQ4YT'
    'ItOTcxOS02ZWU4OTlhNDNhOTciIHgxPSI2LjE4IiB5MT0iOC41OSIgeDI9IjcuODEiIHkyPSIxMC4yMyIgZ3JhZGllbnRVbml0cz'
    '0idXNlclNwYWNlT25Vc2UiPjxzdG9wIG9mZnNldD0iMCIgc3RvcC1jb2xvcj0iIzg2ZDYzMyIgLz48c3RvcCBvZmZzZXQ9IjEiIH'
    'N0b3AtY29sb3I9IiM1ZTk2MjQiIC8+PC9saW5lYXJHcmFkaWVudD48bGluZWFyR3JhZGllbnQgaWQ9ImU5MDBjMzVkLTA5NTgtNG'
    'Q0Zi1iMjhmLTMwMmVlYWFmNTJmNSIgeDE9IjIuNDgiIHkxPSI4LjU5IiB4Mj0iNC4xMSIgeTI9IjEwLjIzIiBncmFkaWVudFVuaX'
    'RzPSJ1c2VyU3BhY2VPblVzZSI+PHN0b3Agb2Zmc2V0PSIwIiBzdG9wLWNvbG9yPSIjODZkNjMzIiAvPjxzdG9wIG9mZnNldD0iMS'
    'Igc3RvcC1jb2xvcj0iIzVlOTYyNCIgLz48L2xpbmVhckdyYWRpZW50PjwvZGVmcz48dGl0bGU+SWNvbi1uZXR3b3JraW5nLTYxPC'
    '90aXRsZT48Y2lyY2xlIGN4PSIxMi43NCIgY3k9IjguOTkiIHI9IjEuMTYiIGZpbGw9InVybCgjZjAyMGZiN2UtMjI0My00NTAxLT'
    'gxNTMtNWQ2OWJkM2MzNGY3KSIgLz48Y2lyY2xlIGN4PSI5LjA0IiBjeT0iOSIgcj0iMS4xNiIgZmlsbD0idXJsKCNiM2MyYmM5NC'
    '04YzdjLTQ4YTItOTcxOS02ZWU4OTlhNDNhOTcpIiAvPjxjaXJjbGUgY3g9IjUuMzQiIGN5PSI5IiByPSIxLjE2IiBmaWxsPSJ1cm'
    'woI2U5MDBjMzVkLTA5NTgtNGQ0Zi1iMjhmLTMwMmVlYWFmNTJmNSkiIC8+PHBhdGggZD0iTTIuNjEsNy4yOGguOTRhLjMuMywwLD'
    'AsMSwuMy4zdjYuOTRhLjYuNiwwLDAsMS0uNi42SDIuMzFhMCwwLDAsMCwxLDAsMFY3LjU4YS4zLjMsMCwwLDEsLjMtLjNaIiB0cm'
    'Fuc2Zvcm09InRyYW5zbGF0ZSgxMy4xOCAxNi45Mykgcm90YXRlKDEzNC45MikiIGZpbGw9IiM1MGU2ZmYiIC8+PHBhdGggZD0iTT'
    'IuNTYsMi45MUgzLjVhLjMuMywwLDAsMSwuMy4zdjcuNDNhMCwwLDAsMCwxLDAsMEgyLjg2YS42LjYsMCwwLDEtLjYtLjZWMy4yMW'
    'EuMy4zLDAsMCwxLC4zLS4zWiIgdHJhbnNmb3JtPSJ0cmFuc2xhdGUoNS42NiAtMC4xNikgcm90YXRlKDQ0LjkyKSIgZmlsbD0iIz'
    'E0OTBkZiIgLz48cGF0aCBkPSJNMTQuMTUsNy4yOGguOTRhLjYuNiwwLDAsMSwuNi42djYuOTRhLjMuMywwLDAsMS0uMy4zaC0uOT'
    'RhLjMuMywwLDAsMS0uMy0uM1Y3LjI4YTAsMCwwLDAsMSwwLDBaIiB0cmFuc2Zvcm09InRyYW5zbGF0ZSgxMi4zMiAtNy4yOCkgcm'
    '90YXRlKDQ1LjA4KSIgZmlsbD0iIzUwZTZmZiIgLz48cGF0aCBkPSJNMTQuODEsMi45MWguOTRhMCwwLDAsMCwxLDAsMHY3LjQzYS'
    '4zLjMsMCwwLDEtLjMuM0gxNC41YS4zLjMsMCwwLDEtLjMtLjNWMy41MWEuNi42LDAsMCwxLC42LS42WiIgdHJhbnNmb3JtPSJ0cm'
    'Fuc2xhdGUoMzAuMzYgMC45OSkgcm90YXRlKDEzNS4wOCkiIGZpbGw9IiMxNDkwZGYiIC8+PC9zdmc+"],["network_security_'
    'group","data:image/svg+xml;base64,PHN2ZyBpZD0iYjc1OTQzYmEtMWEzZi00ODVkLWI0NWQtM2ZlZTAwZWQ3ZTVlIiB4bW'
    'xucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIxOCIgaGVpZ2h0PSIxOCIgdmlld0JveD0iMCAwIDE4IDE4Ij'
    '48ZGVmcz48bGluZWFyR3JhZGllbnQgaWQ9ImZlNWNlNDNmLTI4MjMtNDYxNy1iYjU0LTU3ZGY5ZTc3ODM3MiIgeDE9IjkuMDEiIH'
    'kxPSIwLjc1IiB4Mj0iOS4wMSIgeTI9IjE3LjI1IiBncmFkaWVudFVuaXRzPSJ1c2VyU3BhY2VPblVzZSI+PHN0b3Agb2Zmc2V0PS'
    'IwIiBzdG9wLWNvbG9yPSIjNWVhMGVmIiAvPjxzdG9wIG9mZnNldD0iMC4xOCIgc3RvcC1jb2xvcj0iIzU1OWNlYyIgLz48c3RvcC'
    'BvZmZzZXQ9IjAuNDciIHN0b3AtY29sb3I9IiMzYzkxZTUiIC8+PHN0b3Agb2Zmc2V0PSIwLjg0IiBzdG9wLWNvbG9yPSIjMTM4MG'
    'RhIiAvPjxzdG9wIG9mZnNldD0iMSIgc3RvcC1jb2xvcj0iIzAwNzhkNCIgLz48L2xpbmVhckdyYWRpZW50PjwvZGVmcz48dGl0bG'
    'U+SWNvbi1uZXR3b3JraW5nLTY3PC90aXRsZT48cGF0aCBkPSJNMTYuMzYsOC40YzAsNC44NC01Ljg1LDguNzQtNy4xMiw5LjUzYS'
    '40Ni40NiwwLDAsMS0uNDgsMGMtMS4yNy0uNzktNy4xMi00LjY5LTcuMTItOS41M1YyLjU4YS40Ni40NiwwLDAsMSwuNDUtLjQ2Qz'
    'YuNjQsMiw1LjU5LDAsOSwwczIuMzYsMiw2LjkxLDIuMTJhLjQ2LjQ2LDAsMCwxLC40NS40NloiIGZpbGw9IiMwMDc4ZDQiIC8+PH'
    'BhdGggZD0iTTE1Ljc1LDguNDVjMCw0LjQ0LTUuMzYsOC02LjUzLDguNzRhLjQzLjQzLDAsMCwxLS40NCwwYy0xLjE3LS43Mi02Lj'
    'UzLTQuMy02LjUzLTguNzRWMy4xMWEuNDIuNDIsMCwwLDEsLjQxLS40MkM2LjgzLDIuNTgsNS44Ny43NSw5LC43NXMyLjE3LDEuOD'
    'MsNi4zNCwxLjk0YS40Mi40MiwwLDAsMSwuNDEuNDJaIiBmaWxsPSIjNmJiOWYyIiAvPjxwYXRoIGQ9Ik05LDlWLjc1YzMuMTMsMC'
    'wyLjE3LDEuODMsNi4zNCwxLjk0YS40My40MywwLDAsMSwuNDEuNDNWOC40NmE0Ljg5LDQuODksMCwwLDEsMCwuNTRaTTksOUgyLj'
    'I4Yy40LDQuMTgsNS4zOCw3LjUsNi41LDguMTlhLjM5LjM5LDAsMCwwLC4xOC4wNkg5WiIgZmlsbD0idXJsKCNmZTVjZTQzZi0yOD'
    'IzLTQ2MTctYmI1NC01N2RmOWU3NzgzNzIpIiAvPjxwYXRoIGQ9Ik0yLjY2LDIuNjlDNi44MywyLjU4LDUuODcuNzUsOSwuNzVWOU'
    'gyLjI4YTQuODksNC44OSwwLDAsMSwwLS41NFYzLjEyQS40My40MywwLDAsMSwyLjY2LDIuNjlaIiBmaWxsPSIjNTBlNmZmIiAvPj'
    'xwYXRoIGQ9Ik0xNS43Miw5SDl2OC4yNUg5YS4zOS4zOSwwLDAsMCwuMTgtLjA2QzEwLjM0LDE2LjUsMTUuMzIsMTMuMTgsMTUuNz'
    'IsOVoiIGZpbGw9IiM1MGU2ZmYiIC8+PC9zdmc+"],["disk","data:image/svg+xml;base64,PHN2ZyBpZD0iZWEzMTdiMzEt'
    'YjMxYS00NGZkLWE3YzQtMjYwNzc0NTc1MzYzIiB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIxOCIg'
    'aGVpZ2h0PSIxOCIgdmlld0JveD0iMCAwIDE4IDE4Ij48ZGVmcz48bGluZWFyR3JhZGllbnQgaWQ9ImEzYWVjYjVjLTExZjUtNGVj'
    'ZS05OWY3LTk2NzJmMzIzNjE1NiIgeDE9IjE1LjM1IiB5MT0iMTMuNDEiIHgyPSIxNS4zNyIgeTI9IjEzLjQxIiBncmFkaWVudFVu'
    'aXRzPSJ1c2VyU3BhY2VPblVzZSI+PHN0b3Agb2Zmc2V0PSIwIiBzdG9wLWNvbG9yPSIjMDA3OGQ0IiAvPjxzdG9wIG9mZnNldD0i'
    'MC4xNCIgc3RvcC1jb2xvcj0iIzE3ODJkYSIgLz48c3RvcCBvZmZzZXQ9IjAuMzciIHN0b3AtY29sb3I9IiMzNjhmZTMiIC8+PHN0'
    'b3Agb2Zmc2V0PSIwLjU5IiBzdG9wLWNvbG9yPSIjNGM5OGVhIiAvPjxzdG9wIG9mZnNldD0iMC44IiBzdG9wLWNvbG9yPSIjNTk5'
    'ZWVlIiAvPjxzdG9wIG9mZnNldD0iMC45OSIgc3RvcC1jb2xvcj0iIzVlYTBlZiIgLz48L2xpbmVhckdyYWRpZW50PjxsaW5lYXJH'
    'cmFkaWVudCBpZD0iYjRkZmIzYWItMjVmZS00MTZjLWE2ZmEtZjMzZmNmYmYyMmRjIiB4MT0iNS41MSIgeTE9IjgwMi41IiB4Mj0i'
    'MTIuOTQiIHkyPSI4MTAuNTgiIGdyYWRpZW50VHJhbnNmb3JtPSJ0cmFuc2xhdGUoMCAtMTI3OC43Nikgc2NhbGUoMSAxLjU5KSIg'
    'Z3JhZGllbnRVbml0cz0idXNlclNwYWNlT25Vc2UiPjxzdG9wIG9mZnNldD0iMCIgc3RvcC1jb2xvcj0iIzAwNzhkNCIgLz48c3Rv'
    'cCBvZmZzZXQ9IjAuMDIiIHN0b3AtY29sb3I9IiMwZDdlZDgiIC8+PHN0b3Agb2Zmc2V0PSIwLjA4IiBzdG9wLWNvbG9yPSIjMmI4'
    'YWUwIiAvPjxzdG9wIG9mZnNldD0iMC4xNSIgc3RvcC1jb2xvcj0iIzQxOTRlNyIgLz48c3RvcCBvZmZzZXQ9IjAuMjIiIHN0b3At'
    'Y29sb3I9IiM1MTliZWIiIC8+PHN0b3Agb2Zmc2V0PSIwLjI5IiBzdG9wLWNvbG9yPSIjNWI5ZmVlIiAvPjxzdG9wIG9mZnNldD0i'
    'MC40IiBzdG9wLWNvbG9yPSIjNWVhMGVmIiAvPjxzdG9wIG9mZnNldD0iMC41NSIgc3RvcC1jb2xvcj0iIzViOWZlZSIgLz48c3Rv'
    'cCBvZmZzZXQ9IjAuNjgiIHN0b3AtY29sb3I9IiM1MDlhZWIiIC8+PHN0b3Agb2Zmc2V0PSIwLjgiIHN0b3AtY29sb3I9IiMzZjky'
    'ZTYiIC8+PHN0b3Agb2Zmc2V0PSIwLjkxIiBzdG9wLWNvbG9yPSIjMjY4OGRmIiAvPjxzdG9wIG9mZnNldD0iMC45OSIgc3RvcC1j'
    'b2xvcj0iIzEyN2ZkOSIgLz48L2xpbmVhckdyYWRpZW50PjwvZGVmcz48dGl0bGU+SWNvbi1jb21wdXRlLTMyPC90aXRsZT48ZWxs'
    'aXBzZSBjeD0iOC45NiIgY3k9IjExLjgyIiByeD0iNy41IiByeT0iMy4wOCIgZmlsbD0iIzc2YmMyZCIgLz48ZWxsaXBzZSBjeD0i'
    'OS4xNSIgY3k9IjExLjc5IiByeD0iMi40OSIgcnk9IjAuNjgiIGZpbGw9IiM1ZTk2MjQiIC8+PHBhdGggZD0iTTE1LjM1LDEzLjRs'
    'MCwwWiIgZmlsbD0idXJsKCNhM2FlY2I1Yy0xMWY1LTRlY2UtOTlmNy05NjcyZjMyMzYxNTYpIiAvPjxlbGxpcHNlIGN4PSI4Ljk2'
    'IiBjeT0iNC45OSIgcng9IjcuNSIgcnk9IjMuMDgiIGZpbGw9InVybCgjYjRkZmIzYWItMjVmZS00MTZjLWE2ZmEtZjMzZmNmYmYy'
    'MmRjKSIgLz48ZWxsaXBzZSBjeD0iOS4xNSIgY3k9IjQuOTUiIHJ4PSIyLjQ5IiByeT0iMC42OCIgZmlsbD0iIzAwNWJhMSIgLz48'
    'cGF0aCBkPSJNOSwxNC44NGM0LjE1LDAsNy41LTEuMzgsNy41LTMuMDhoMHYxLjgyaDBjLS4xNCwxLjY1LTMuNDQsMy03LjUsM3Mt'
    'Ny41LTEuMzgtNy41LTMuMDhWMTEuNzZDMS40NiwxMy40Niw0LjgyLDE0Ljg0LDksMTQuODRaIiBmaWxsPSIjNWU5NjI0IiAvPjxw'
    'YXRoIGQ9Ik0xNS4zNSwxMy40bDAsMFoiIGZpbGw9InVybCgjYTNhZWNiNWMtMTFmNS00ZWNlLTk5ZjctOTY3MmYzMjM2MTU2KSIg'
    'Lz48cGF0aCBkPSJNOSw4YzQuMTUsMCw3LjUtMS4zOCw3LjUtMy4wOGgwVjYuNzRoMGMtLjE0LDEuNjUtMy40NCwzLTcuNSwzcy03'
    'LjUtMS4zOC03LjUtMy4wOFY0LjkyQzEuNDYsNi42Miw0LjgyLDgsOSw4WiIgZmlsbD0iIzAwNzhkNCIgLz48L3N2Zz4="],["con'
    'tainer_registry","data:image/svg+xml;base64,PHN2ZyBpZD0iZTlmN2JhNzMtNTZiOC00ODY0LTk2ZmYtZGNlODBiZWY3'
    'MjlhIiB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIxOCIgaGVpZ2h0PSIxOCIgdmlld0JveD0iMCAw'
    'IDE4IDE4Ij48ZGVmcz48bGluZWFyR3JhZGllbnQgaWQ9ImJkZjI3ZGM2LTAyNWMtNDgwNS04YmZkLTNhMDVkZWZkM2ZiZCIgeDE9'
    'IjguNjM3IiB5MT0iLTEuOTkxIiB4Mj0iOC42MzciIHkyPSIxNi43MzkiIGdyYWRpZW50VW5pdHM9InVzZXJTcGFjZU9uVXNlIj48'
    'c3RvcCBvZmZzZXQ9IjAiIHN0b3AtY29sb3I9IiM1ZWEwZWYiIC8+PHN0b3Agb2Zmc2V0PSIxIiBzdG9wLWNvbG9yPSIjMDA3OGQ0'
    'IiAvPjwvbGluZWFyR3JhZGllbnQ+PGxpbmVhckdyYWRpZW50IGlkPSJmY2Q2YzZjNy1lMmViLTRhMzItYjkxNC0zYTg0ODU1ODVh'
    'MWIiIHgxPSIxMi45NiIgeTE9IjguNTYxIiB4Mj0iMTIuOTYiIHkyPSI2LjE0MSIgZ3JhZGllbnRUcmFuc2Zvcm09Im1hdHJpeCgx'
    'LCAwLCAwLCAtMSwgMCwgMjApIiBncmFkaWVudFVuaXRzPSJ1c2VyU3BhY2VPblVzZSI+PHN0b3Agb2Zmc2V0PSIwIiBzdG9wLWNv'
    'bG9yPSIjMzMzMTMyIiAvPjxzdG9wIG9mZnNldD0iMSIgc3RvcC1jb2xvcj0iIzViNWE1YyIgLz48L2xpbmVhckdyYWRpZW50Pjwv'
    'ZGVmcz48cGF0aCBkPSJNNy40Myw4LjE3OGwyLjU4OS0xLjU3Myw3LjI1NSwyLjczMUEzLjY2NCwzLjY2NCwwLDAsMCwxNi4yMyw3'
    'LjQ5bC0uMDEtLjA1QTQuMTk0LDQuMTk0LDAsMCwwLDE0LDYuMzJhNC45MSw0LjkxLDAsMCwwLTUuMS00LjdBNS4wNzEsNS4wNzEs'
    'MCwwLDAsNC4wNiw0LjkxLDQuNjIxLDQuNjIxLDAsMCwwLDAsOS4zOWE0LjczLDQuNzMsMCwwLDAsNC44OSw0LjU0SDcuNDNaIiBm'
    'aWxsPSJ1cmwoI2JkZjI3ZGM2LTAyNWMtNDgwNS04YmZkLTNhMDVkZWZkM2ZiZCkiIC8+PHBvbHlnb24gcG9pbnRzPSIxMC4wNyA3'
    'LjE1OSAxMC4wOCAxMS40MzkgMTcuOTkgMTMuMTE5IDE3Ljk5IDEwLjEzOSAxMC4wNyA3LjE1OSIgZmlsbD0iIzc2NzY3NiIgLz48'
    'cG9seWxpbmUgcG9pbnRzPSIxMC4wNyA3LjE1OSA3LjkzIDguNDU5IDcuOTMgMTIuNDM5IDEwLjA4IDExLjQzOSIgZmlsbD0iIzk5'
    'OSIgLz48cG9seWdvbiBwb2ludHM9IjEzLjY4IDExLjQ5OSAxNC40IDExLjY5OSAxNC40IDkuMzY5IDEzLjY4IDkuMTE5IDEzLjY4'
    'IDExLjQ5OSIgZmlsbD0iI2EzYTNhMyIgLz48cG9seWdvbiBwb2ludHM9IjEyLjk2IDguODg5IDEyLjI0IDguNjI5IDEyLjI0IDEx'
    'LjExOSAxMi45NiAxMS4zMTkgMTIuOTYgOC44ODkiIGZpbGw9IiNhM2EzYTMiIC8+PHBvbHlnb24gcG9pbnRzPSIxNS4xMiAxMS44'
    'ODkgMTUuODIgMTIuMDc5IDE1Ljg0IDkuODU5IDE1LjEyIDkuNjE5IDE1LjEyIDExLjg4OSIgZmlsbD0iI2EzYTNhMyIgLz48cG9s'
    'eWdvbiBwb2ludHM9IjEwLjgxIDEwLjc0OSAxMS41MyAxMC45MjkgMTEuNTMgOC4zOTkgMTAuODEgOC4xNTkgMTAuODEgMTAuNzQ5'
    'IiBmaWxsPSIjYTNhM2EzIiAvPjxwb2x5Z29uIHBvaW50cz0iMTcuMjcgMTAuMzQ5IDE2LjU1IDEwLjA5OSAxNi41NSAxMi4yNjkg'
    'MTcuMjcgMTIuNDY5IDE3LjI3IDEwLjM0OSIgZmlsbD0iI2EzYTNhMyIgLz48cGF0aCBpZD0iZWYwZDFiNTQtYTFlNy00Y2I5LWE0'
    'ZTUtOGE4NTE4ZTdjMTI3IiBkPSJNOC42NiwxMS4zNjlsLS4zNi4yMVY4Ljc0OWwuMzYtLjE5Wm0uNzEtMy4yMkw5LDguMzg5djIu'
    'NzVsLjM3LS4yWiIgZmlsbD0iI2IzYjNiMyIgLz48cG9seWdvbiBwb2ludHM9IjE3Ljk5IDEzLjExOSAxNS44MyAxMy44NTkgNy45'
    'MyAxMi40MzkgMTAuMDggMTEuNDM5IDE3Ljk5IDEzLjExOSIgZmlsbD0idXJsKCNmY2Q2YzZjNy1lMmViLTRhMzItYjkxNC0zYTg0'
    'ODU1ODVhMWIpIiAvPjxwb2x5Z29uIHBvaW50cz0iMTcuOTkgMTYuMTY5IDEwLjA0IDE3LjY3OSAxMC4wOCAxMi4wODkgMTcuOTkg'
    'MTMuNTU5IDE3Ljk5IDE2LjE2OSIgZmlsbD0iIzc2NzY3NiIgLz48cG9seWdvbiBwb2ludHM9IjEwLjgxIDE2Ljc1OSAxMC44MSAx'
    'My4yMDkgMTEuNTMgMTMuMjk5IDExLjUzIDE2LjYzOSAxMC44MSAxNi43NTkiIGZpbGw9IiNhM2EzYTMiIC8+PHBvbHlnb24gcG9p'
    'bnRzPSIxMi45NiAxNi4zOTkgMTIuMjQgMTYuNTI5IDEyLjI0IDEzLjM4OSAxMi45NiAxMy40OTkgMTIuOTYgMTYuMzk5IDEyLjk2'
    'IDE2LjM5OSIgZmlsbD0iI2EzYTNhMyIgLz48cG9seWdvbiBwb2ludHM9IjEzLjY4IDE2LjI4OSAxMy42OCAxMy41NjkgMTQuNCAx'
    'My42NTkgMTQuNCAxNi4xNTkgMTMuNjggMTYuMjg5IiBmaWxsPSIjYTNhM2EzIiAvPjxwb2x5Z29uIHBvaW50cz0iMTUuODMgMTUu'
    'OTA5IDE1LjEyIDE2LjAzOSAxNS4xMiAxMy43NDkgMTUuODMgMTMuODU5IDE1LjgzIDE1LjkwOSIgZmlsbD0iI2EzYTNhMyIgLz48'
    'cG9seWdvbiBwb2ludHM9IjE3LjI5IDE1LjY3OSAxNi41NSAxNS44MDkgMTYuNTUgMTMuOTI5IDE3LjI0IDE0LjAxOSAxNy4yOSAx'
    'NS42NzkiIGZpbGw9IiNhM2EzYTMiIC8+PHBhdGggaWQ9ImI5ZjI1ZWI0LTRjODgtNDVjMi1iYzRkLWY5OTI3NTdkN2UwZSIgZD0i'
    'TTcuOTMsMTYuNHYtMy4yNmwyLjE2LTF2NS42WiIgZmlsbD0iIzk5OSIgLz48cGF0aCBpZD0iZWI5MjAwYTctNDY5My00NDI3LWJk'
    'YWUtYjMzY2U5MGZmN2YyIiBkPSJNOC42MSwxNi4zODlsLS4zMi0uMTZ2LTIuNzZsLjMyLS4xNVptLjc3LTMuNDUtLjM4LjE5djMu'
    'NDhsLjM3LjE5di0zLjg2WiIgZmlsbD0iI2IzYjNiMyIgLz48L3N2Zz4="],["key_vault","data:image/svg+xml;base64,P'
    'HN2ZyBpZD0iYmM5MzE2OWEtMjRjNC00Njg2LTlmMzctYzdlNGY1M2IzZDM0IiB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwM'
    'C9zdmciIHdpZHRoPSIxOCIgaGVpZ2h0PSIxOCIgdmlld0JveD0iMCAwIDE4IDE4Ij48ZGVmcz48cmFkaWFsR3JhZGllbnQgaWQ9I'
    'mZiMTE0YzkzLTdjMTYtNDU0MC04OTlhLTA3OTYwNDE2MjllNiIgY3g9IjkiIGN5PSI5IiByPSI4LjUiIGdyYWRpZW50VW5pdHM9I'
    'nVzZXJTcGFjZU9uVXNlIj48c3RvcCBvZmZzZXQ9IjAuMTgiIHN0b3AtY29sb3I9IiM1ZWEwZWYiIC8+PHN0b3Agb2Zmc2V0PSIwL'
    'jU2IiBzdG9wLWNvbG9yPSIjNWM5ZmVlIiAvPjxzdG9wIG9mZnNldD0iMC42OSIgc3RvcC1jb2xvcj0iIzU1OWNlZCIgLz48c3Rvc'
    'CBvZmZzZXQ9IjAuNzgiIHN0b3AtY29sb3I9IiM0YTk3ZTkiIC8+PHN0b3Agb2Zmc2V0PSIwLjg2IiBzdG9wLWNvbG9yPSIjMzk5M'
    'GU0IiAvPjxzdG9wIG9mZnNldD0iMC45MyIgc3RvcC1jb2xvcj0iIzIzODdkZSIgLz48c3RvcCBvZmZzZXQ9IjAuOTkiIHN0b3AtY'
    '29sb3I9IiMwODdiZDYiIC8+PHN0b3Agb2Zmc2V0PSIxIiBzdG9wLWNvbG9yPSIjMDA3OGQ0IiAvPjwvcmFkaWFsR3JhZGllbnQ+P'
    'HJhZGlhbEdyYWRpZW50IGlkPSJlYzQ3OGJkMy01YjM4LTRlN2YtYjY2MS0xMWYzNTU1NzhiZmYiIGN4PSIzOC45NSIgY3k9IjE4M'
    'i4wNyIgcj0iOS44OCIgZ3JhZGllbnRUcmFuc2Zvcm09InRyYW5zbGF0ZSgtMjguNzEgLTE2My4yNCkgc2NhbGUoMC45NCAwLjk0K'
    'SIgZ3JhZGllbnRVbml0cz0idXNlclNwYWNlT25Vc2UiPjxzdG9wIG9mZnNldD0iMC4yNyIgc3RvcC1jb2xvcj0iI2ZmZDcwZiIgL'
    'z48c3RvcCBvZmZzZXQ9IjAuNDkiIHN0b3AtY29sb3I9IiNmZmNiMTIiIC8+PHN0b3Agb2Zmc2V0PSIwLjg4IiBzdG9wLWNvbG9yP'
    'SIjZmVhYzE5IiAvPjxzdG9wIG9mZnNldD0iMSIgc3RvcC1jb2xvcj0iI2ZlYTExYiIgLz48L3JhZGlhbEdyYWRpZW50PjwvZGVmc'
    'z48dGl0bGU+SWNvbi1zZWN1cml0eS0yNDU8L3RpdGxlPjxwYXRoIGlkPSJhYWNmODMxMS1hMzE3LTQwMGYtYjYxMy03NGJkMDBkY'
    'TVjZTMiIGQ9Ik05LC41QTguNSw4LjUsMCwxLDAsMTcuNSw5LDguNTEsOC41MSwwLDAsMCw5LC41Wk05LDE2LjM0QTcuMzQsNy4zN'
    'CwwLDEsMSwxNi4zNCw5LDcuMzQsNy4zNCwwLDAsMSw5LDE2LjM0WiIgZmlsbD0idXJsKCNmYjExNGM5My03YzE2LTQ1NDAtODk5Y'
    'S0wNzk2MDQxNjI5ZTYpIiAvPjxjaXJjbGUgY3g9IjkiIGN5PSI5IiByPSI3LjM0IiBmaWxsPSIjZmZmIiAvPjxnPjxwYXRoIGlkP'
    'SJiZDk4M2M0MS1kYjczLTQwZWMtYTRmNC1kYTEyMTNmYzk5MjQiIGQ9Ik0xMy40NCw3LjMzYTEuODQsMS44NCwwLDAsMCwwLTIuN'
    'TloMEwxMC4yOSwxLjU4YTEuODMsMS44MywwLDAsMC0yLjU4LDBoMEw0LjU2LDQuNzRhMS44NCwxLjg0LDAsMCwwLDAsMi41OUw3L'
    'jE4LDEwYS41MS41MSwwLDAsMSwuMTUuMzZ2NC44OGEuNjMuNjMsMCwwLDAsLjE4LjQ0bDEuMiwxLjJhLjQxLjQxLDAsMCwwLC41O'
    'CwwbDEuMTYtMS4xNmgwbC42OC0uNjhhLjI1LjI1LDAsMCwwLDAtLjM0bC0uNDktLjQ5YS4yNy4yNywwLDAsMSwwLS4zN2wuNDktL'
    'jQ5YS4yNS4yNSwwLDAsMCwwLS4zNGwtLjQ5LS40OWEuMjcuMjcsMCwwLDEsMC0uMzdsLjQ5LS40OWEuMjUuMjUsMCwwLDAsMC0uM'
    'zRsLS42OC0uNjl2LS4yNVpNOSwyLjM1QTEsMSwwLDAsMSw5LDQuNDIsMSwxLDAsMSwxLDksMi4zNVoiIGZpbGw9InVybCgjZWM0N'
    'zhiZDMtNWIzOC00ZTdmLWI2NjEtMTFmMzU1NTc4YmZmKSIgLz48cGF0aCBpZD0iYWQyZTdlNDQtOWJmZC00Nzc1LThiZjQtOGVmM'
    'jZhNTQ0OTIxIiBkPSJNOC4xOCwxNS4zaDBhLjIzLjIzLDAsMCwwLC4zOC0uMTd2LTRhLjI0LjI0LDAsMCwwLS4xMS0uMmgwYS4yM'
    'i4yMiwwLDAsMC0uMzQuMnY0QS4yOC4yOCwwLDAsMCw4LjE4LDE1LjNaIiBmaWxsPSIjZmY5MzAwIiBvcGFjaXR5PSIwLjc1IiAvP'
    'jxyZWN0IGlkPSJhOTk2ZmJmZi0zOTM2LTRiMjQtYjQwNy0zNjkzMzZjMTQzYmEiIHg9IjYuNDgiIHk9IjUuNzkiIHdpZHRoPSI1L'
    'jE3IiBoZWlnaHQ9IjAuNjEiIHJ4PSIwLjI4IiBmaWxsPSIjZmY5MzAwIiBvcGFjaXR5PSIwLjc1IiAvPjxyZWN0IGlkPSJiYjEyZ'
    'DMxYy0zMzUyLTRhMTgtODdkZC1hMTY5YTRhODcyMWQiIHg9IjYuNDgiIHk9IjYuNzgiIHdpZHRoPSI1LjE3IiBoZWlnaHQ9IjAuN'
    'jEiIHJ4PSIwLjI4IiBmaWxsPSIjZmY5MzAwIiBvcGFjaXR5PSIwLjc1IiAvPjwvZz48L3N2Zz4="],["managed_identity","d'
    'ata:image/svg+xml;base64,PHN2ZyBpZD0iZjgwN2NkZGUtMThmMi00NTc0LWJhMTQtZjBiMWVlZjk0YTRhIiB4bWxucz0iaHR'
    '0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIxOCIgaGVpZ2h0PSIxOCIgdmlld0JveD0iMCAwIDE4IDE4Ij48ZGVmcz4'
    '8bGluZWFyR3JhZGllbnQgaWQ9ImJiNjdiMTU0LWFmOGYtNGE1My1hOWNlLWFhMDQ2YjkzOThlOSIgeDE9IjEzLjE4IiB5MT0iMTM'
    'uMDEiIHgyPSI4LjYzIiB5Mj0iNC4zOCIgZ3JhZGllbnRVbml0cz0idXNlclNwYWNlT25Vc2UiPjxzdG9wIG9mZnNldD0iMCIgc3R'
    'vcC1jb2xvcj0iIzE5ODhkOSIgLz48c3RvcCBvZmZzZXQ9IjAuOSIgc3RvcC1jb2xvcj0iIzU0YWVmMCIgLz48L2xpbmVhckdyYWR'
    'pZW50PjxsaW5lYXJHcmFkaWVudCBpZD0iYTQ3ZDcxMzgtMDg0YS00NzFkLThkNjMtNzQ0ZTc1YjllOGEzIiB4MT0iMTEuMjIiIHk'
    'xPSIxMC41IiB4Mj0iMTQuMzciIHkyPSIxNS45MyIgZ3JhZGllbnRVbml0cz0idXNlclNwYWNlT25Vc2UiPjxzdG9wIG9mZnNldD0'
    'iMC4xIiBzdG9wLWNvbG9yPSIjNTRhZWYwIiAvPjxzdG9wIG9mZnNldD0iMC4yOSIgc3RvcC1jb2xvcj0iIzRmYWJlZSIgLz48c3R'
    'vcCBvZmZzZXQ9IjAuNTEiIHN0b3AtY29sb3I9IiM0MWEyZTkiIC8+PHN0b3Agb2Zmc2V0PSIwLjc0IiBzdG9wLWNvbG9yPSIjMmE'
    '5M2UwIiAvPjxzdG9wIG9mZnNldD0iMC44OCIgc3RvcC1jb2xvcj0iIzE5ODhkOSIgLz48L2xpbmVhckdyYWRpZW50PjwvZGVmcz4'
    '8dGl0bGU+SWNvbi1pZGVudGl0eS0yMjc8L3RpdGxlPjxnPjxwb2x5Z29uIHBvaW50cz0iMS4xNSAxMC4yMiA4LjkzIDE1LjI3IDE'
    '2Ljg1IDEwLjIxIDE3Ljg1IDExLjM2IDguOTMgMTcuMTEgMC4xNSAxMS4zNyAxLjE1IDEwLjIyIiBmaWxsPSIjNTBlNmZmIiAvPjx'
    'wb2x5Z29uIHBvaW50cz0iMS43MyA5LjU4IDguOTMgMSAxNi4yOCA5LjU5IDguOTMgMTQuMjMgMS43MyA5LjU4IiBmaWxsPSIjZmZ'
    'mIiAvPjxwb2x5Z29uIHBvaW50cz0iOC45MyAxIDguOTMgMTQuMjMgMS43MyA5LjU4IDguOTMgMSIgZmlsbD0iIzUwZTZmZiIgLz4'
    '8cG9seWdvbiBwb2ludHM9IjguOTMgMSA4LjkzIDE0LjIzIDE2LjI4IDkuNTkgOC45MyAxIiBmaWxsPSJ1cmwoI2JiNjdiMTU0LWF'
    'mOGYtNGE1My1hOWNlLWFhMDQ2YjkzOThlOSkiIC8+PHBvbHlnb24gcG9pbnRzPSI4LjkzIDcuODMgMTYuMjggOS41OSA4LjkzIDE'
    '0LjIzIDguOTMgNy44MyIgZmlsbD0iIzUzYjFlMCIgLz48cG9seWdvbiBwb2ludHM9IjguOTMgMTQuMjMgMS43MyA5LjU4IDguOTM'
    'gNy44MyA4LjkzIDE0LjIzIiBmaWxsPSIjOWNlYmZmIiAvPjxwb2x5Z29uIHBvaW50cz0iOC45MyAxNy4xMSAxNy44NSAxMS4zNiA'
    'xNi44NSAxMC4yMSA4LjkzIDE1LjI3IDguOTMgMTcuMTEiIGZpbGw9InVybCgjYTQ3ZDcxMzgtMDg0YS00NzFkLThkNjMtNzQ0ZTc'
    '1YjllOGEzKSIgLz48Zz48cGF0aCBpZD0iZTE4OWE2MWYtNjMxYS00MTIyLWJiMmItMDc5ZTg2MDA0ZDk2IiBkPSJNMTYuMzIsMTE'
    'uODhhMS4xNiwxLjE2LDAsMCwwLDAtMS42NWgwbC0yLTJhMS4xNiwxLjE2LDAsMCwwLTEuNjQsMGgwbC0yLDJhMS4xOCwxLjE4LDA'
    'sMCwwLDAsMS42NWwxLjY3LDEuNjdhLjMyLjMyLDAsMCwxLC4wOS4yM3YzLjFhLjM2LjM2LDAsMCwwLC4xMi4yOGwuNzYuNzZhLjI'
    '1LjI1LDAsMCwwLC4zNywwbC43My0uNzNoMGwuNDQtLjQ0YS4xNS4xNSwwLDAsMCwwLS4yMWwtLjMxLS4zMWEuMTYuMTYsMCwwLDE'
    'sMC0uMjRsLjMxLS4zMWEuMTYuMTYsMCwwLDAsMC0uMjJsLS4zMS0uMzFhLjE1LjE1LDAsMCwxLDAtLjIzbC4zMS0uMzJhLjE1LjE'
    '1LDAsMCwwLDAtLjIxbC0uNDQtLjQ0di0uMTZaTTEzLjUsOC43MWEuNjYuNjYsMCwxLDEtLjY2LjY2LjY2LjY2LDAsMCwxLC42Ni0'
    'uNjZaIiBmaWxsPSIjZmZjYTAwIiAvPjxwYXRoIGlkPSJmYjcwMzNlZS00NjUwLTQ4ODYtODBjNy1lZGRmNjI1NjBmODUiIGQ9Ik0'
    'xMywxN2gwYS4xNC4xNCwwLDAsMCwuMjQtLjExVjE0LjMzYS4xNi4xNiwwLDAsMC0uMDYtLjEzaDBhLjE0LjE0LDAsMCwwLS4yMi4'
    'xM3YyLjUxQS4xNS4xNSwwLDAsMCwxMywxN1oiIGZpbGw9IiNmZjkzMDAiIG9wYWNpdHk9IjAuNzUiIC8+PHJlY3QgaWQ9ImIxNjZ'
    'iOGMyLWI5ZWUtNGMzZC1iZjdhLTc3YmQ1Y2UwNTcwYiIgeD0iMTEuOSIgeT0iMTAuOSIgd2lkdGg9IjMuMjkiIGhlaWdodD0iMC4'
    'zOSIgcng9IjAuMTgiIGZpbGw9IiNmZjkzMDAiIG9wYWNpdHk9IjAuNzUiIC8+PHJlY3QgaWQ9ImJhZjQzN2ZlLTM0ODMtNGEyNS0'
    '5NGJhLTFlODRhNjRjZDJlYiIgeD0iMTEuOSIgeT0iMTEuNTMiIHdpZHRoPSIzLjI5IiBoZWlnaHQ9IjAuMzkiIHJ4PSIwLjE4IiB'
    'maWxsPSIjZmY5MzAwIiBvcGFjaXR5PSIwLjc1IiAvPjwvZz48L2c+PC9zdmc+"],["storage_account","data:image/svg+x'
    'ml;base64,PHN2ZyBpZD0iZjJmMDQzNDktOGFlZS00NDEzLTg0YzktYTkwNTM2MTFiMzE5IiB4bWxucz0iaHR0cDovL3d3dy53My'
    '5vcmcvMjAwMC9zdmciIHdpZHRoPSIxOCIgaGVpZ2h0PSIxOCIgdmlld0JveD0iMCAwIDE4IDE4Ij48ZGVmcz48bGluZWFyR3JhZG'
    'llbnQgaWQ9ImFkNGM0Zjk2LTA5YWEtNGY5MS1iYTEwLTVjYjhhZDUzMGY3NCIgeDE9IjkiIHkxPSIxNS44MyIgeDI9IjkiIHkyPS'
    'I1Ljc5IiBncmFkaWVudFVuaXRzPSJ1c2VyU3BhY2VPblVzZSI+PHN0b3Agb2Zmc2V0PSIwIiBzdG9wLWNvbG9yPSIjYjNiM2IzIi'
    'AvPjxzdG9wIG9mZnNldD0iMC4yNiIgc3RvcC1jb2xvcj0iI2MxYzFjMSIgLz48c3RvcCBvZmZzZXQ9IjEiIHN0b3AtY29sb3I9Ii'
    'NlNmU2ZTYiIC8+PC9saW5lYXJHcmFkaWVudD48L2RlZnM+PHRpdGxlPkljb24tc3RvcmFnZS04NjwvdGl0bGU+PHBhdGggZD0iTS'
    '41LDUuNzloMTdhMCwwLDAsMCwxLDAsMHY5LjQ4YS41Ny41NywwLDAsMS0uNTcuNTdIMS4wN2EuNTcuNTcsMCwwLDEtLjU3LS41N1'
    'Y1Ljc5QTAsMCwwLDAsMSwuNSw1Ljc5WiIgZmlsbD0idXJsKCNhZDRjNGY5Ni0wOWFhLTRmOTEtYmExMC01Y2I4YWQ1MzBmNzQpIi'
    'AvPjxwYXRoIGQ9Ik0xLjA3LDIuMTdIMTYuOTNhLjU3LjU3LDAsMCwxLC41Ny41N1Y1Ljc5YTAsMCwwLDAsMSwwLDBILjVhMCwwLD'
    'AsMCwxLDAsMFYyLjczQS41Ny41NywwLDAsMSwxLjA3LDIuMTdaIiBmaWxsPSIjMzdjMmIxIiAvPjxwYXRoIGQ9Ik0yLjgxLDYuOD'
    'lIMTUuMThhLjI3LjI3LDAsMCwxLC4yNi4yN3YxLjRhLjI3LjI3LDAsMCwxLS4yNi4yN0gyLjgxYS4yNy4yNywwLDAsMS0uMjYtLj'
    'I3VjcuMTZBLjI3LjI3LDAsMCwxLDIuODEsNi44OVoiIGZpbGw9IiNmZmYiIC8+PHBhdGggZD0iTTIuODIsOS42OEgxNS4xOWEuMj'
    'cuMjcsMCwwLDEsLjI2LjI3djEuNDFhLjI3LjI3LDAsMCwxLS4yNi4yN0gyLjgyYS4yNy4yNywwLDAsMS0uMjYtLjI3VjEwQS4yNy'
    '4yNywwLDAsMSwyLjgyLDkuNjhaIiBmaWxsPSIjMzdjMmIxIiAvPjxwYXRoIGQ9Ik0yLjgyLDEyLjVIMTUuMTlhLjI3LjI3LDAsMC'
    'wxLC4yNi4yN3YxLjQxYS4yNy4yNywwLDAsMS0uMjYuMjdIMi44MmEuMjcuMjcsMCwwLDEtLjI2LS4yN1YxMi43N0EuMjcuMjcsMC'
    'wwLDEsMi44MiwxMi41WiIgZmlsbD0iIzI1ODI3NyIgLz48L3N2Zz4="],["application_gateway","data:image/svg+xml;'
    'base64,PHN2ZyBpZD0iYWNhYzVhMzQtYTAzMi00OWY5LTkzOTctMzdmNGYxYjRhZTlhIiB4bWxucz0iaHR0cDovL3d3dy53My5vc'
    'mcvMjAwMC9zdmciIHdpZHRoPSIxOCIgaGVpZ2h0PSIxOCIgdmlld0JveD0iMCAwIDE4IDE4Ij48ZGVmcz48bGluZWFyR3JhZGllb'
    'nQgaWQ9ImY2ZDUzOTliLWE1Y2ItNGMwOS05NmNjLTllM2JiMWFmMjM4NiIgeDE9IjkiIHkxPSIxOS4yNSIgeDI9IjkiIHkyPSItM'
    'C40NiIgZ3JhZGllbnRUcmFuc2Zvcm09InRyYW5zbGF0ZSg5IC0zLjczKSByb3RhdGUoNDUpIiBncmFkaWVudFVuaXRzPSJ1c2VyU'
    '3BhY2VPblVzZSI+PHN0b3Agb2Zmc2V0PSIwIiBzdG9wLWNvbG9yPSIjNWU5NjI0IiAvPjxzdG9wIG9mZnNldD0iMC41NSIgc3Rvc'
    'C1jb2xvcj0iIzZkYWQyYSIgLz48c3RvcCBvZmZzZXQ9IjEiIHN0b3AtY29sb3I9IiM3NmJjMmQiIC8+PC9saW5lYXJHcmFkaWVud'
    'D48bGluZWFyR3JhZGllbnQgaWQ9ImE0MzI0MmEyLTRkOTUtNGY2ZC04ODcwLTI3MDJjZWI2YWViYyIgeDE9IjcuNTQiIHkxPSI2L'
    'jQ0IiB4Mj0iNy41MyIgeTI9IjUuMTgiIGdyYWRpZW50VW5pdHM9InVzZXJTcGFjZU9uVXNlIj48c3RvcCBvZmZzZXQ9IjAiIHN0b'
    '3AtY29sb3I9IiNjY2MiIC8+PHN0b3Agb2Zmc2V0PSIwLjEyIiBzdG9wLWNvbG9yPSIjZDdkN2Q3IiAvPjxzdG9wIG9mZnNldD0iM'
    'C40MiIgc3RvcC1jb2xvcj0iI2ViZWJlYiIgLz48c3RvcCBvZmZzZXQ9IjAuNzIiIHN0b3AtY29sb3I9IiNmOGY4ZjgiIC8+PHN0b'
    '3Agb2Zmc2V0PSIxIiBzdG9wLWNvbG9yPSIjZmNmY2ZjIiAvPjwvbGluZWFyR3JhZGllbnQ+PGxpbmVhckdyYWRpZW50IGlkPSJlZ'
    'WRjZTZkZC03MDZhLTQzYzQtYWM2Ni02NmI3MzU3ODIyMWQiIHgxPSI5LjM2IiB5MT0iNy42OSIgeDI9IjkuMzYiIHkyPSI2LjU3I'
    'iBocmVmPSIjYTQzMjQyYTItNGQ5NS00ZjZkLTg4NzAtMjcwMmNlYjZhZWJjIiAvPjwvZGVmcz48cmVjdCB4PSIyLjgyIiB5PSIyL'
    'jgyIiB3aWR0aD0iMTIuMzUiIGhlaWdodD0iMTIuMzUiIHJ4PSIwLjU3IiB0cmFuc2Zvcm09InRyYW5zbGF0ZSgtMy43MyA5KSByb'
    '3RhdGUoLTQ1KSIgZmlsbD0idXJsKCNmNmQ1Mzk5Yi1hNWNiLTRjMDktOTZjYy05ZTNiYjFhZjIzODYpIiAvPjxnPjxwYXRoIGQ9I'
    'k0xMC44OSwxMC41MWgyLjg0YS4xMS4xMSwwLDAsMCwuMS0uMTFWNy41N2EuMS4xLDAsMCwwLS4xOC0uMDdsLS43OC43OCwwLC4wN'
    'WEuMS4xLDAsMCwxLS4xNCwwTDkuMjYsNC45MWEuMS4xLDAsMCwwLS4xNCwwbC0uODguODhhLjExLjExLDAsMCwwLDAsLjE1bDMuN'
    'DEsMy40MWEuMTEuMTEsMCwwLDEsMCwuMTVsLS4wNS4wNS0uNzguNzhBLjExLjExLDAsMCwwLDEwLjg5LDEwLjUxWiIgZmlsbD0iI'
    '2ZmZiIgLz48cGF0aCBkPSJNNi45MiwxMC41MUg0LjA4QS4xMS4xMSwwLDAsMSw0LDEwLjRWNy41N2EuMS4xLDAsMCwxLC4xNy0uM'
    'DdsLjc5Ljc4LDAsLjA1YS4xLjEsMCwwLDAsLjE0LDBMOC41NSw0LjkxYS4xLjEsMCwwLDEsLjE0LDBsLjg4Ljg4YS4xMS4xMSwwL'
    'DAsMSwwLC4xNUw2LjE2LDkuMzVhLjExLjExLDAsMCwwLDAsLjE1bDAsLjA1Ljc4Ljc4QS4xMS4xMSwwLDAsMSw2LjkyLDEwLjUxW'
    'iIgZmlsbD0iI2ZmZiIgLz48cGF0aCBkPSJNNi44MiwxMy4wN2wyLDJhLjEuMSwwLDAsMCwuMTQsMGwyLTJhLjEuMSwwLDAsMC0uM'
    'DctLjE3SDkuNzJhLjExLjExLDAsMCwxLS4xLS4xVjhhLjEuMSwwLDAsMC0uMS0uMTFIOC4yOEEuMTEuMTEsMCwwLDAsOC4xNyw4V'
    'jEyLjhhLjEuMSwwLDAsMS0uMS4xSDYuODlBLjEuMSwwLDAsMCw2LjgyLDEzLjA3WiIgZmlsbD0iI2ZmZiIgLz48L2c+PHBhdGgga'
    'WQ9ImFjMGE5YzBjLTJlOGMtNDg0My1iMDJiLTJmYWRmNzZiMjdkMCIgZD0iTTEwLjY1LDcuNzhBMi43MSwyLjcxLDAsMCwxLDcuM'
    'zMsMy41bDAsMGEyLjcxLDIuNzEsMCwwLDEsMy4yOSw0LjMiIGZpbGw9IiMwMDc4ZDQiIC8+PGNpcmNsZSBjeD0iNy41MyIgY3k9I'
    'jUuNTUiIHI9IjAuODciIGZpbGw9InVybCgjYTQzMjQyYTItNGQ5NS00ZjZkLTg4NzAtMjcwMmNlYjZhZWJjKSIgLz48Zz48cGF0a'
    'CBkPSJNNi42Nyw3bC4xOS4zTDcsNy41YTUuOTQsNS45NCwwLDAsMSwuMzQtMS4xLjg1Ljg1LDAsMCwxLS40NS0uMjNBNi43MSw2L'
    'jcxLDAsMCwwLDYuNjcsN1oiIGZpbGw9IiNmMmYyZjIiIG9wYWNpdHk9IjAuNTUiIC8+PHBhdGggZD0iTTcuMjQsNC43M0E0LDQsM'
    'CwwLDEsNywzLjhhMi40OCwyLjQ4LDAsMCwwLS4zNC40NkEzLjUxLDMuNTEsMCwwLDAsNi44Niw1LDEsMSwwLDAsMSw3LjI0LDQuN'
    'zNaIiBmaWxsPSIjZjJmMmYyIiBvcGFjaXR5PSIwLjU1IiAvPjxwYXRoIGQ9Ik04LjE3LDYuMTRhLjg3Ljg3LDAsMCwxLS40OC4yN'
    'iw0LjYyLDQuNjIsMCwwLDAsLjQ2LjQxLDQuMTQsNC4xNCwwLDAsMCwuNjUuMzlWNy4xM0EuNTMuNTMsMCwwLDEsOSw2LjczLDMuN'
    'iwzLjYsMCwwLDEsOC4xNyw2LjE0WiIgZmlsbD0iI2YyZjJmMiIgb3BhY2l0eT0iMC41NSIgLz48cGF0aCBkPSJNMTAuNzksNy4yY'
    'TQuMTQsNC4xNCwwLDAsMS0uODctLjF2MGEuNTUuNTUsMCwwLDEtLjE2LjM5LDMuODQsMy44NCwwLDAsMCwxLjA4LjA4LDIuOTMsM'
    'i45MywwLDAsMCwuMzctLjQyWiIgZmlsbD0iI2YyZjJmMiIgb3BhY2l0eT0iMC41NSIgLz48L2c+PGNpcmNsZSBjeD0iOS4zNiIgY'
    '3k9IjcuMTMiIHI9IjAuNTYiIGZpbGw9InVybCgjZWVkY2U2ZGQtNzA2YS00M2M0LWFjNjYtNjZiNzM1NzgyMjFkKSIgLz48Y2lyY'
    '2xlIGN4PSIxMC42NCIgY3k9IjUuNzQiIHI9IjAuNiIgZmlsbD0iI2YyZjJmMiIgLz48Zz48cGF0aCBkPSJNOS4yMSw0LjQyQTQuM'
    'jksNC4yOSwwLDAsMSwxMS4wOSw0YTIuMjQsMi4yNCwwLDAsMC0uNDctLjQ1LDQuNSw0LjUsMCwwLDAtMS40OS4zNWMtLjEsMC0uM'
    'TkuMTEtLjI5LjE2aDBhNS44NSw1Ljg1LDAsMCwxLS42My0uOTNsLS4zNC4xM2E1LjM1LDUuMzUsMCwwLDAsLjY1LDEsMy45MiwzL'
    'jkyLDAsMCwwLS42Ny41NS44Ny44NywwLDAsMSwuNDMuMzUsMy4yOSwzLjI5LDAsMCwxLC42MS0uNDgsOS4xNiw5LjE2LDAsMCwwL'
    'DEuMTcsMSwuNTcuNTcsMCwwLDEsLjItLjMyQTguNDQsOC40NCwwLDAsMSw5LjIxLDQuNDJaIiBmaWxsPSIjZjJmMmYyIiBvcGFja'
    'XR5PSIwLjU1IiAvPjxwYXRoIGQ9Ik0xMS41NSw2LjA5aDBsLS4xLDBoMGwtLjA4LDBoMGwtLjEtLjA2YS42MS42MSwwLDAsMS0uM'
    'i4zbC4xMi4wN2gwbC4xMS4wNmgwbC4yOC4xNGgwYTMuNTgsMy41OCwwLDAsMCwuMDktLjM1WiIgZmlsbD0iI2YyZjJmMiIgb3BhY'
    '2l0eT0iMC41NSIgLz48L2c+PGNpcmNsZSBjeD0iNy41MyIgY3k9IjUuNTUiIHI9IjAuODciIGZpbGw9IiNmMmYyZjIiIC8+PGNpc'
    'mNsZSBjeD0iOS4zNiIgY3k9IjcuMTMiIHI9IjAuNTYiIGZpbGw9IiNmMmYyZjIiIC8+PC9zdmc+"],["monitor","data:image'
    '/svg+xml;base64,PHN2ZyBpZD0iZTRlNzY0Y2QtMmU3My00NzJmLWI4OGEtYmY4YmZjMmMyOTk0IiB4bWxucz0iaHR0cDovL3d3'
    'dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIxOCIgaGVpZ2h0PSIxOCIgdmlld0JveD0iMCAwIDE4IDE4Ij48ZGVmcz48cmFkaWFs'
    'R3JhZGllbnQgaWQ9ImFjOGIzMmRhLTMwY2EtNGI5Mi04ZDBmLThkMmQ1ZWYyNzhhMCIgY3g9IjUuNzIiIGN5PSI3LjQ1IiByPSI4'
    'LjQyIiBncmFkaWVudFRyYW5zZm9ybT0idHJhbnNsYXRlKDMuMjMgMS41MSkgc2NhbGUoMS4wMSAxLjAxKSIgZ3JhZGllbnRVbml0'
    'cz0idXNlclNwYWNlT25Vc2UiPjxzdG9wIG9mZnNldD0iMC4xOCIgc3RvcC1jb2xvcj0iIzVlYTBlZiIgLz48c3RvcCBvZmZzZXQ9'
    'IjAuNTYiIHN0b3AtY29sb3I9IiM1YzlmZWUiIC8+PHN0b3Agb2Zmc2V0PSIwLjY5IiBzdG9wLWNvbG9yPSIjNTU5Y2VkIiAvPjxz'
    'dG9wIG9mZnNldD0iMC43OCIgc3RvcC1jb2xvcj0iIzRhOTdlOSIgLz48c3RvcCBvZmZzZXQ9IjAuODYiIHN0b3AtY29sb3I9IiMz'
    'OTkwZTQiIC8+PHN0b3Agb2Zmc2V0PSIwLjkzIiBzdG9wLWNvbG9yPSIjMjM4N2RlIiAvPjxzdG9wIG9mZnNldD0iMC45OSIgc3Rv'
    'cC1jb2xvcj0iIzA4N2JkNiIgLz48c3RvcCBvZmZzZXQ9IjEiIHN0b3AtY29sb3I9IiMwMDc4ZDQiIC8+PC9yYWRpYWxHcmFkaWVu'
    'dD48cmFkaWFsR3JhZGllbnQgaWQ9ImE5OTU0ODIwLWNiMzgtNDk0My05ODQyLWYwYTU2OGQyYjAxNSIgY3g9IjI4LjE4IiBjeT0i'
    'MjAyLjI5IiByPSIyLjciIGdyYWRpZW50VHJhbnNmb3JtPSJ0cmFuc2xhdGUoLTE3Ljc3IC0xODUuMDEpIHNjYWxlKDAuOTUpIiBn'
    'cmFkaWVudFVuaXRzPSJ1c2VyU3BhY2VPblVzZSI+PHN0b3Agb2Zmc2V0PSIwLjE5IiBzdG9wLWNvbG9yPSIjOGM4ZTkwIiAvPjxz'
    'dG9wIG9mZnNldD0iMC4zNSIgc3RvcC1jb2xvcj0iIzg0ODY4OCIgLz48c3RvcCBvZmZzZXQ9IjAuNiIgc3RvcC1jb2xvcj0iIzZl'
    'NzA3MSIgLz48c3RvcCBvZmZzZXQ9IjAuOTEiIHN0b3AtY29sb3I9IiM0YTRiNGMiIC8+PHN0b3Agb2Zmc2V0PSIxIiBzdG9wLWNv'
    'bG9yPSIjM2UzZjNmIiAvPjwvcmFkaWFsR3JhZGllbnQ+PC9kZWZzPjx0aXRsZT5JY29uLW1hbmFnZS0zMTc8L3RpdGxlPjxlbGxp'
    'cHNlIGN4PSI5IiBjeT0iOSIgcng9IjguNSIgcnk9IjguNDciIGZpbGw9InVybCgjYWM4YjMyZGEtMzBjYS00YjkyLThkMGYtOGQy'
    'ZDVlZjI3OGEwKSIgLz48ZWxsaXBzZSBjeD0iOSIgY3k9IjkiIHJ4PSI3LjQiIHJ5PSI3LjM3IiBmaWxsPSIjZmZmIiAvPjxwYXRo'
    'IGQ9Ik0yLjcyLDkuNDRhNi4yNCw2LjI0LDAsMCwwLDEuODIsNGwyLTJhMy41MywzLjUzLDAsMCwxLTEtMloiIGZpbGw9IiM5Y2Vi'
    'ZmYiIC8+PHBhdGggZD0iTTEzLjEzLDQuMjdBNi4yNSw2LjI1LDAsMCwwLDkuNDQsMi43NFY1LjUzYTMuNDEsMy40MSwwLDAsMSwx'
    'LjcxLjdaIiBmaWxsPSIjMzJiZWRkIiAvPjxwYXRoIGQ9Ik00Ljg3LDQuMjdsMiwyYTMuNDEsMy40MSwwLDAsMSwxLjcxLS43VjIu'
    'NzRBNi4yNSw2LjI1LDAsMCwwLDQuODcsNC4yN1oiIGZpbGw9IiMzMmJlZGQiIC8+PHBhdGggZD0iTTExLjc4LDYuODVhMy42LDMu'
    'NiwwLDAsMSwuNzEsMS43MWgyLjc5YTYuMTYsNi4xNiwwLDAsMC0xLjUzLTMuNjdaIiBmaWxsPSIjMzJiZWRkIiAvPjxwYXRoIGQ9'
    'Ik02LjIyLDYuODVsLTItMkE2LjE2LDYuMTYsMCwwLDAsMi43Miw4LjU2SDUuNTFBMy42LDMuNiwwLDAsMSw2LjIyLDYuODVaIiBm'
    'aWxsPSIjNTBlNmZmIiAvPjxwYXRoIGQ9Ik0xNC4xNCw3YS40NS40NSwwLDAsMC0uNTctLjI1TDkuNDUsOC40MWwuMzIuODEsNC4x'
    'Mi0xLjYzQS40NC40NCwwLDAsMCwxNC4xNCw3WiIgZmlsbD0iI2YwNDA0OSIgLz48ZWxsaXBzZSBjeD0iOSIgY3k9IjkiIHJ4PSIx'
    'LjIiIHJ5PSIxLjIiIGZpbGw9InVybCgjYTk5NTQ4MjAtY2IzOC00OTQzLTk4NDItZjBhNTY4ZDJiMDE1KSIgLz48L3N2Zz4="]])'
    ';\n  /* OFFICIAL_AZURE_ICON_DATA_END */\n  const byId = id => document.getElementById(id);\n  const isO'
    'bject = value => value !== null && typeof value === "object" && !Array.isArray(value);\n  const text '
    '= value => value === null || value === undefined || value === "" ? "Not evaluated" : (typeof value ='
    '== "object" ? JSON.stringify(value) : String(value));\n  const node = (tag, value, className) => {\n  '
    '  const result = document.createElement(tag);\n    if (value !== undefined) result.textContent = text'
    '(value);\n    if (className) result.className = className;\n    return result;\n  };\n  const add = (par'
    'ent, ...children) => { parent.append(...children); return parent; };\n  const svgNode = (tag, attribu'
    'tes = {}, value) => {\n    const result = document.createElementNS("http://www.w3.org/2000/svg", tag)'
    ';\n    for (const [key, item] of Object.entries(attributes)) result.setAttribute(key, String(item));\n'
    '    if (value !== undefined) result.textContent = String(value);\n    return result;\n  };\n  const emp'
    'ty = message => node("p", message, "empty");\n  const percentage = value => value === null ? "Not eva'
    'luated" : `${value.toLocaleString("en-US", {maximumFractionDigits: 1})} / 100`;\n  const utc = value '
    '=> {\n    if (value === null || value === undefined || value === "") return "Not evaluated";\n    cons'
    't date = new Date(value);\n    if (!Number.isFinite(date.getTime())) return `${text(value)} (date not'
    ' normalized)`;\n    return `${new Intl.DateTimeFormat("en-GB", {year: "numeric", month: "short", day:'
    ' "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit", timeZone: "UTC"}).format(date)} U'
    'TC`;\n  };\n  const sampleWindowText = value => `${utc(value.timestamp)} / observed duration: ${text(v'
    'alue.duration)}`;\n  const windowText = value => {\n    if (value === null || value === undefined) ret'
    'urn "Not evaluated";\n    if (Array.isArray(value)) return value.length ? `Sample windows (${value.le'
    'ngth}): ${value.map(sampleWindowText).join("; ")}` : "Not evaluated: no sample windows included.";\n '
    '   if (Object.hasOwn(value, "start") || Object.hasOwn(value, "end")) return `${utc(value.start)} - $'
    '{utc(value.end)}`;\n    return `Sample window: ${sampleWindowText(value)}`;\n  };\n  const assert = (co'
    'ndition, message) => { if (!condition) throw new Error(message); };\n  const string = (value, path, n'
    'ullable = false) => assert((nullable && (value === null || value === undefined)) || typeof value ==='
    ' "string", `${path}: expected text.`);\n  const array = (value, path, nullable = false) => assert((nu'
    'llable && value === null) || Array.isArray(value), `${path}: expected a collection.`);\n  const count'
    ' = (value, path, nullable = false) => assert((nullable && (value === null || value === undefined)) |'
    '| (Number.isSafeInteger(value) && value >= 0), `${path}: invalid count.`);\n  const object = (value, '
    'path) => assert(isObject(value), `${path}: invalid structure.`);\n  const enumValue = (value, labels,'
    ' path) => assert(labels.has(value), `${path}: unsupported value.`);\n  const armIdentity = (value, pa'
    'th) => {\n    string(value, path);\n    const parts = value.split("/");\n    assert(value.length <= 204'
    '8 && parts.length >= 9 && parts.length % 2 === 1 && parts[0] === "" &&\n      parts[1].toLowerCase() '
    '=== "subscriptions" && /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(parts[2]) &&\n      part'
    's[3].toLowerCase() === "resourcegroups" && parts[5].toLowerCase() === "providers" &&\n      parts.sli'
    'ce(2).every(part => /^[A-Za-z0-9_.()-]+$/.test(part) && ![".", ".."].includes(part)), `${path}: inva'
    'lid full ARM ID.`);\n    return value.toLowerCase();\n  };\n  const sampleWindow = (value, path) => {\n '
    '   object(value, path);\n    assert(Object.hasOwn(value, "timestamp") || Object.hasOwn(value, "durati'
    'on"), `${path}: sample window fields are missing.`);\n    string(value.timestamp, `${path}.timestamp`'
    ', true); string(value.duration, `${path}.duration`, true);\n  };\n  const observedWindow = (value, pat'
    'h) => {\n    if (value === null || value === undefined) return;\n    if (Array.isArray(value)) {\n     '
    ' for (const [index, item] of value.entries()) sampleWindow(item, `${path}[${index}]`);\n      return;'
    '\n    }\n    object(value, path);\n    if (Object.hasOwn(value, "start") || Object.hasOwn(value, "end")'
    ') {\n      string(value.start, `${path}.start`, true); string(value.end, `${path}.end`, true);\n    } '
    'else sampleWindow(value, path);\n  };\n  const recordIdentity = (row, path) => {\n    object(row, path)'
    ';\n    for (const key of ["resource_id", "source_id", "observed_at", "cluster_name", "namespace", "na'
    'me", "title", "uid", "kind", "workload_name"]) string(row[key], `${path}.${key}`, true);\n  };\n  cons'
    't canonical = value => JSON.stringify(value, (_key, item) => {\n    if (!isObject(item)) return item;'
    '\n    const result = Object.create(null);\n    for (const key of Object.keys(item).sort()) result[key]'
    ' = item[key];\n    return result;\n  });\n  const validateTree = root => {\n    const pending = [[root, '
    '0]];\n    while (pending.length) {\n      const [value, depth] = pending.pop();\n      assert(depth <= '
    '40, "The model exceeds the supported nesting depth.");\n      if (value !== null && typeof value === '
    '"object") {\n        for (const item of Object.values(value)) pending.push([item, depth + 1]);\n      '
    '}\n    }\n  };\n  const validateScore = (score, path) => {\n    object(score, path);\n    for (const key '
    'of ["passed", "failed", "evaluated", "not_evaluated", "not_applicable", "total"]) count(score[key], '
    '`${path}.${key}`);\n    assert(score.evaluated === score.passed + score.failed, `${path}: inconsisten'
    't evaluated count.`);\n    assert(score.total === score.evaluated + score.not_evaluated + score.not_a'
    'pplicable, `${path}: inconsistent total.`);\n    assert(score.evaluated === 0 ? score.score === null '
    ': (Number.isFinite(score.score) && score.score >= 0 && score.score <= 100), `${path}: missing or inv'
    'alid index; with no evaluated checks it must be null.`);\n    const eligible = score.evaluated + scor'
    'e.not_evaluated;\n    assert(eligible === 0 ? score.coverage_percent === null : (Number.isFinite(scor'
    'e.coverage_percent) && score.coverage_percent >= 0 && score.coverage_percent <= 100), `${path}: inva'
    'lid coverage.`);\n  };\n  const validateScoreCounts = (score, checks, path) => {\n    const counts = ne'
    'w Map([...STATUS.keys()].map(key => [key, 0]));\n    for (const check of checks) counts.set(check.sta'
    'tus, counts.get(check.status) + 1);\n    assert(score.total === checks.length && score.passed === cou'
    'nts.get("passed") && score.failed === counts.get("failed") &&\n      score.not_evaluated === counts.g'
    'et("not_evaluated") && score.not_applicable === counts.get("not_applicable"), `${path}: counts do no'
    't match the supplied records.`);\n  };\n  const validateCheck = (check, path, sources) => {\n    object'
    '(check, path);\n    for (const key of ["check_id", "title", "resource_id"]) { string(check[key], `${p'
    'ath}.${key}`); assert(check[key].length > 0, `${path}.${key}: empty value.`); }\n    for (const key o'
    'f ["rule_id", "checklist_id", "namespace", "workload_name", "business_impact", "recommendation", "le'
    'arn_url", "checklist_url", "kubernetes_url", "reason"]) string(check[key], `${path}.${key}`, true);\n'
    '    if (check.kubernetes_ref !== null && check.kubernetes_ref !== undefined) {\n      object(check.ku'
    'bernetes_ref, `${path}.kubernetes_ref`);\n      for (const key of ["uid", "kind", "namespace", "name"'
    ']) string(check.kubernetes_ref[key], `${path}.kubernetes_ref.${key}`, true);\n    }\n    enumValue(che'
    'ck.status, STATUS, `${path}.status`); enumValue(check.level, LEVEL, `${path}.level`);\n    enumValue('
    'check.area, AREA, `${path}.area`); enumValue(check.pillar, PILLAR, `${path}.pillar`);\n    enumValue('
    'check.severity, SEVERITY, `${path}.severity`); enumValue(check.effort, EFFORT, `${path}.effort`);\n  '
    '  array(check.evidence, `${path}.evidence`);\n    assert(check.status !== "failed" || check.evidence.'
    'length > 0, `${path}: a finding needs supplied evidence.`);\n    for (const [index, evidence] of chec'
    'k.evidence.entries()) {\n      object(evidence, `${path}.evidence[${index}]`);\n      string(evidence.'
    'source_id, `${path}.evidence.source_id`);\n      assert(sources.has(evidence.source_id), `${path}: ev'
    'idence source not registered.`);\n      string(evidence.resource_id, `${path}.evidence.resource_id`, '
    'true);\n      string(evidence.observed_at, `${path}.evidence.observed_at`, true);\n      assert(Object'
    '.hasOwn(evidence, "value"), `${path}: the observed value is missing.`);\n    }\n  };\n  const validate '
    '= model => {\n    object(model, "Report"); validateTree(model);\n    assert(model.schema_version === "'
    '1.0", "Unsupported schema version; 1.0 is required.");\n    assert(["LIVE", "SIMULATED"].includes(mod'
    'el.provenance), "Invalid data provenance.");\n    assert(["LAB", "PRODUCTION", "UNSPECIFIED"].include'
    's(model.environment), "The environment must be declared.");\n    string(model.reference_utc, "referen'
    'ce_utc");\n    assert(/^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(?:\\.\\d+)?Z$/.test(model.reference_utc) &&'
    ' Number.isFinite(Date.parse(model.reference_utc)), "The reference must be an RFC 3339 UTC date.");\n '
    '   assert(new Date(model.reference_utc).toISOString().slice(0, 19) === model.reference_utc.slice(0, '
    '19), "The UTC reference contains a date or time that does not exist.");\n    object(model.client, "cl'
    'ient"); string(model.client.name, "client.name");\n    assert(model.client.name.trim().length > 0, "T'
    'he customer must be identified.");\n    string(model.client.logo_data_uri, "client.logo_data_uri", tr'
    'ue); string(model.client.logo_alt, "client.logo_alt", true);\n    if (model.client.logo_data_uri) ass'
    'ert(model.client.logo_data_uri.length <= 1000000 && /^data:image\\/(?:png|jpeg);base64,[A-Za-z0-9+/]+'
    '={0,2}$/.test(model.client.logo_data_uri), "The logo must be a bounded inline PNG or JPEG.");\n    ob'
    'ject(model.cluster, "cluster");\n    for (const key of ["id", "name"]) { string(model.cluster[key], `'
    'cluster.${key}`); assert(model.cluster[key].length > 0, `cluster.${key}: empty value.`); }\n    const'
    ' clusterIdentity = armIdentity(model.cluster.id, "cluster.id");\n    for (const key of ["subscription'
    '_id", "subscription_name", "resource_group", "region", "version", "power_state", "provisioning_state'
    '", "sku_tier", "mode"]) string(model.cluster[key], `cluster.${key}`, true);\n    array(model.sources,'
    ' "sources");\n    const sources = new Set();\n    for (const source of model.sources) {\n      object(s'
    'ource, "source"); string(source.id, "source.id");\n      assert(source.id.length > 0 && !sources.has('
    'source.id), "Empty or duplicate source ID."); sources.add(source.id);\n      enumValue(source.status,'
    ' SOURCE_STATUS, "source.status"); string(source.time, "source.time", true);\n      count(source.recor'
    'ds, "source.records", true); count(source.pages, "source.pages", true); array(source.errors, "source'
    '.errors");\n      string(source.note, "source.note", true); observedWindow(source.window, "source.win'
    'dow");\n      for (const error of source.errors) {\n        object(error, "source.error"); string(erro'
    'r.code, "source.error.code", true); string(error.message, "source.error.message", true);\n        cou'
    'nt(error.http_status, "source.error.http_status", true);\n      }\n    }\n    object(model.inventory, "'
    'inventory");\n    if (model.source_data !== undefined && model.source_data !== null) object(model.sou'
    'rce_data, "source_data");\n    for (const key of ["node_pools", "namespaces", "workloads", "related_r'
    'esources"]) assert(Object.hasOwn(model.inventory, key), `Missing inventory.${key}.`);\n    for (const'
    ' [key, rows] of Object.entries(model.inventory)) {\n      array(rows, `inventory.${key}`, true);\n    '
    '  if (rows !== null) for (const row of rows) recordIdentity(row, `inventory.${key}.record`);\n    }\n '
    '   array(model.checks, "checks");\n    const checks = new Map();\n    for (const check of model.checks'
    ') {\n      validateCheck(check, "check", sources);\n      assert(!checks.has(check.check_id), "The mod'
    'el repeats a check_id; the overall index cannot be shown.");\n      checks.set(check.check_id, check)'
    ';\n    }\n    array(model.findings, "findings");\n    const findings = new Set();\n    for (const findin'
    'g of model.findings) {\n      const check = checks.get(finding.check_id);\n      assert(check && check'
    '.status === "failed" && !findings.has(finding.check_id) && canonical(check) === canonical(finding), '
    '"Findings must be exactly the failed checks, with no duplicates.");\n      findings.add(finding.check'
    '_id);\n    }\n    assert(findings.size === model.checks.filter(check => check.status === "failed").len'
    'gth, "Findings for failed checks are missing.");\n    object(model.scores, "scores"); validateScore(m'
    'odel.scores.global, "scores.global"); validateScore(model.scores.coverage, "scores.coverage");\n    v'
    'alidateScoreCounts(model.scores.global, model.checks, "scores.global"); validateScoreCounts(model.sc'
    'ores.coverage, model.checks, "scores.coverage");\n    object(model.scores.areas, "scores.areas"); obj'
    'ect(model.scores.pillars, "scores.pillars");\n    for (const key of AREA.keys()) { validateScore(mode'
    'l.scores.areas[key], `scores.areas.${key}`); validateScoreCounts(model.scores.areas[key], model.chec'
    'ks.filter(check => check.area === key), `scores.areas.${key}`); }\n    for (const key of PILLAR.keys('
    ')) { validateScore(model.scores.pillars[key], `scores.pillars.${key}`); validateScoreCounts(model.sc'
    'ores.pillars[key], model.checks.filter(check => check.pillar === key), `scores.pillars.${key}`); }\n '
    '   object(model.finops, "finops");\n    array(model.finops.sources, "finops.sources");\n    for (const'
    ' id of model.finops.sources) string(id, "finops.sources.record");\n    for (const key of ["candidates'
    '", "cost_rows", "metrics"]) {\n      array(model.finops[key], `finops.${key}`, true);\n      if (model'
    '.finops[key] !== null) for (const row of model.finops[key]) recordIdentity(row, `finops.${key}.recor'
    'd`);\n    }\n    array(model.finops.notes, "finops.notes");\n    for (const note of model.finops.notes)'
    ' string(note, "finops.notes.record");\n    for (const key of ["actual_cost", "estimated_savings"]) as'
    'sert(model.finops[key] === null || Number.isFinite(model.finops[key]), `finops.${key}: invalid amoun'
    't.`);\n    string(model.finops.currency, "finops.currency", true);\n    observedWindow(model.finops.wi'
    'ndow, "finops.window");\n    for (const row of model.finops.candidates || []) {\n      string(row.id, '
    '"finops.candidate.id"); string(row.title, "finops.candidate.title");\n      string(row.basis, "finops'
    '.candidate.basis", true); string(row.unit, "finops.candidate.unit", true);\n      string(row.recommen'
    'dation, "finops.candidate.recommendation", true); count(row.sample_count, "finops.candidate.sample_c'
    'ount", true);\n      observedWindow(row.window, "finops.candidate.window");\n      assert(row.estimate'
    'd_savings === null || Number.isFinite(row.estimated_savings), "finops.candidate.estimated_savings: i'
    'nvalid amount.");\n    }\n    array(model.actions, "actions");\n    const actions = new Set();\n    for '
    '(const action of model.actions) {\n      object(action, "action"); string(action.action_id, "action.a'
    'ction_id"); string(action.check_id, "action.check_id");\n      assert(action.action_id.length > 0 && '
    '!actions.has(action.action_id) && checks.get(action.check_id)?.status === "failed", "An action needs'
    ' a unique ID and must reference a supplied finding."); actions.add(action.action_id);\n      for (con'
    'st key of ["title", "resource_id", "namespace", "workload_name", "recommendation", "learn_url", "own'
    'er"]) string(action[key], `action.${key}`, true);\n      enumValue(action.planning_bucket, BUCKET, "a'
    'ction.planning_bucket"); enumValue(action.effort, EFFORT, "action.effort");\n      enumValue(action.a'
    'rea, AREA, "action.area"); enumValue(action.pillar, PILLAR, "action.pillar"); enumValue(action.sever'
    'ity, SEVERITY, "action.severity");\n    }\n    array(model.executive_messages, "executive_messages");\n'
    '    for (const message of model.executive_messages) string(message, "executive_messages.record");\n  '
    '  object(model.methodology, "methodology");\n    assert(model.methodology.score_kind === "local_asses'
    'sment_indicator" && model.methodology.official_waf_score === false && model.methodology.read_only =='
    '= true, "The method must declare an unofficial, read-only local index.");\n    array(model.methodolog'
    'y.limitations, "methodology.limitations");\n    for (const item of model.methodology.limitations) str'
    'ing(item, "methodology.limitations.record");\n    if (model.methodology.queries !== undefined) array('
    'model.methodology.queries, "methodology.queries", true);\n    if (model.methodology.source_pins !== u'
    'ndefined) array(model.methodology.source_pins, "methodology.source_pins", true);\n    for (const quer'
    'y of model.methodology.queries || []) {\n      object(query, "methodology.query");\n      for (const k'
    'ey of ["source_id", "description", "command"]) string(query[key], `methodology.query.${key}`, true);'
    '\n    }\n    for (const pin of model.methodology.source_pins || []) object(pin, "methodology.source_pi'
    'n");\n    if (model.architecture !== undefined && model.architecture !== null) {\n      const graph = '
    'model.architecture; object(graph, "architecture");\n      for (const key of ["nodes", "edges", "unkno'
    'wns"]) array(graph[key], `architecture.${key}`);\n      const nodeIds = new Set(), edgeIds = new Set('
    ');\n      const graphIdentity = (row, path) => {\n        object(row, path);\n        for (const key of'
    ' ["cluster_id", "provenance", "observed_at"]) string(row[key], `${path}.${key}`);\n        assert(arm'
    'Identity(row.cluster_id, `${path}.cluster_id`) === clusterIdentity && row.provenance === model.prove'
    'nance, `${path}: the relationship does not belong to this cluster or provenance.`);\n      };\n      f'
    'or (const row of graph.nodes) {\n        graphIdentity(row, "architecture.node");\n        for (const '
    'key of ["id", "resource_id", "cluster_name", "kind", "label", "source_id"]) {\n          string(row[k'
    'ey], `architecture.node.${key}`); assert(row[key].length > 0, `architecture.node.${key}: empty value'
    '.`);\n        }\n        assert(row.cluster_name === model.cluster.name && sources.has(row.source_id) '
    '&& !nodeIds.has(row.id), "architecture.node: duplicate identity, inconsistent cluster or unregistere'
    'd source.");\n        assert(isObject(row.evidence) || Array.isArray(row.evidence), "architecture.nod'
    'e: structured evidence is missing.");\n        nodeIds.add(row.id);\n      }\n      for (const row of g'
    'raph.edges) {\n        graphIdentity(row, "architecture.edge");\n        for (const key of ["id", "fro'
    'm", "to", "relation"]) { string(row[key], `architecture.edge.${key}`); assert(row[key].length > 0, `'
    'architecture.edge.${key}: empty value.`); }\n        array(row.source_ids, "architecture.edge.source_'
    'ids");\n        assert(row.source_ids.length > 0 && row.source_ids.every(id => sources.has(id)), "arc'
    'hitecture.edge: unregistered source.");\n        assert(!edgeIds.has(row.id) && nodeIds.has(row.from)'
    ' && nodeIds.has(row.to), "architecture.edge: duplicate ID or endpoints without evidence.");\n        '
    'assert(isObject(row.evidence) || Array.isArray(row.evidence), "architecture.edge: join fields are mi'
    'ssing.");\n        edgeIds.add(row.id);\n      }\n      for (const row of graph.unknowns) {\n        gra'
    'phIdentity(row, "architecture.unknown");\n        for (const key of ["code", "kind", "message", "clus'
    'ter_name"]) string(row[key], `architecture.unknown.${key}`);\n        string(row.resource_id, "archit'
    'ecture.unknown.resource_id", true);\n        array(row.source_ids, "architecture.unknown.source_ids")'
    ';\n        assert(row.status === "not_evaluated" && row.cluster_name === model.cluster.name && row.so'
    'urce_ids.every(id => sources.has(id)), "architecture.unknown: invalid status, cluster or source.");\n'
    '      }\n    }\n    if (model.available_clusters !== undefined) validateRoster(model.available_cluster'
    's);\n    if (model.selected_cluster_names !== undefined) {\n      array(model.selected_cluster_names, '
    '"selected_cluster_names");\n      assert(model.selected_cluster_names.length === 1 && model.selected_'
    'cluster_names[0] === model.cluster.name, "selected_cluster_names: a single-cluster snapshot must ide'
    'ntify its cluster.");\n    }\n    return model;\n  };\n  const validateRoster = roster => {\n    array(ro'
    'ster, "available_clusters");\n    assert(roster.length >= 1 && roster.length <= 5, "available_cluster'
    's: a fixed roster of one to five clusters is required.");\n    const names = new Set(), ids = new Set'
    '();\n    for (const row of roster) {\n      object(row, "available_clusters.record");\n      for (const'
    ' key of ["cluster_id", "cluster_name", "resource_group"]) { string(row[key], `available_clusters.${k'
    'ey}`); assert(row[key].length > 0, `available_clusters.${key}: empty value.`); }\n      const identit'
    'y = armIdentity(row.cluster_id, "available_clusters.cluster_id");\n      assert(["LAB", "PRODUCTION",'
    ' "UNSPECIFIED"].includes(row.environment), "available_clusters: unsupported environment.");\n      as'
    'sert(!names.has(row.cluster_name) && !ids.has(identity), "available_clusters: duplicate identity.");'
    '\n      names.add(row.cluster_name); ids.add(identity);\n    }\n  };\n  const validateDocument = documen'
    'tModel => {\n    if (documentModel.schema_version === "1.0") return validate(documentModel);\n    obje'
    'ct(documentModel, "Report"); validateTree(documentModel);\n    assert(documentModel.schema_version =='
    '= "aks-waf-multi-cluster-v1", "Unsupported schema version.");\n    validateRoster(documentModel.avail'
    'able_clusters);\n    string(documentModel.reference_utc, "reference_utc");\n    assert(/^\\d{4}-\\d{2}-\\'
    'd{2}T\\d{2}:\\d{2}:\\d{2}(?:\\.\\d+)?Z$/.test(documentModel.reference_utc) && Number.isFinite(Date.parse('
    'documentModel.reference_utc)), "The combined reference must be an RFC 3339 UTC date.");\n    assert(n'
    'ew Date(documentModel.reference_utc).toISOString().slice(0, 19) === documentModel.reference_utc.slic'
    'e(0, 19), "The combined reference contains a date that does not exist.");\n    assert(["LIVE", "SIMUL'
    'ATED"].includes(documentModel.provenance), "Invalid combined provenance.");\n    object(documentModel'
    '.client, "client"); string(documentModel.client.name, "client.name");\n    assert(documentModel.clien'
    't.name.trim().length > 0, "The customer must be identified.");\n    array(documentModel.selected_clus'
    'ter_names, "selected_cluster_names"); array(documentModel.cluster_runs, "cluster_runs");\n    const r'
    'oster = new Map(documentModel.available_clusters.map(row => [row.cluster_name, row]));\n    const sel'
    'ected = new Set(documentModel.selected_cluster_names);\n    assert(selected.size >= 1 && selected.siz'
    'e <= 5 && selected.size === documentModel.selected_cluster_names.length && [...selected].every(name '
    '=> roster.has(name)), "The combined selection does not match the fixed roster.");\n    assert(documen'
    'tModel.cluster_runs.length === selected.size, "Results for selected clusters are missing.");\n    con'
    'st seen = new Set();\n    for (const run of documentModel.cluster_runs) {\n      object(run, "cluster_'
    'run"); enumValue(run.status, RUN_STATUS, "cluster_run.status");\n      string(run.cluster_name, "clus'
    'ter_run.cluster_name"); string(run.cluster_id, "cluster_run.cluster_id"); string(run.reference_utc, '
    '"cluster_run.reference_utc");\n      const identity = armIdentity(run.cluster_id, "cluster_run.cluste'
    'r_id");\n      assert(selected.has(run.cluster_name) && !seen.has(run.cluster_name) &&\n        armIde'
    'ntity(roster.get(run.cluster_name).cluster_id, "available_clusters.cluster_id") === identity, "clust'
    'er_run: identity outside the selection or duplicated.");\n      seen.add(run.cluster_name);\n      if '
    '(run.snapshot === null) {\n        assert(run.status === "error" && isObject(run.error), "cluster_run'
    ': a result without a snapshot must keep its error.");\n      } else {\n        validate(run.snapshot);'
    '\n        assert(run.status !== "error" && armIdentity(run.snapshot.cluster.id, "cluster.id") === ide'
    'ntity && run.snapshot.cluster.name === run.cluster_name &&\n          run.snapshot.reference_utc === '
    'run.reference_utc && run.snapshot.provenance === documentModel.provenance &&\n          canonical(run'
    '.snapshot.client) === canonical(documentModel.client), "cluster_run: inconsistent snapshot, date or '
    'identity.");\n      }\n    }\n    object(documentModel.aggregate, "aggregate"); object(documentModel.ag'
    'gregate.scores, "aggregate.scores");\n    validateScore(documentModel.aggregate.scores.global, "aggre'
    'gate.scores.global");\n    validateScore(documentModel.aggregate.scores.coverage, "aggregate.scores.c'
    'overage");\n    for (const [field, labels] of [["areas", AREA], ["pillars", PILLAR]]) {\n      object('
    'documentModel.aggregate.scores[field], `aggregate.scores.${field}`);\n      for (const key of labels.'
    'keys()) validateScore(documentModel.aggregate.scores[field][key], `aggregate.scores.${field}.${key}`'
    ');\n    }\n    object(documentModel.aggregate.inventory_counts, "aggregate.inventory_counts");\n    for'
    ' (const [key, value] of Object.entries(documentModel.aggregate.inventory_counts)) count(value, `aggr'
    'egate.inventory_counts.${key}`, true);\n    for (const key of ["findings_total", "critical_total"]) c'
    'ount(documentModel.aggregate[key], `aggregate.${key}`);\n    object(documentModel.aggregate.cluster_s'
    'tatus_counts, "aggregate.cluster_status_counts");\n    for (const status of RUN_STATUS.keys()) {\n    '
    '  const expected = documentModel.cluster_runs.filter(run => run.status === status).length;\n      if '
    '(Object.hasOwn(documentModel.aggregate.cluster_status_counts, status)) {\n        count(documentModel'
    '.aggregate.cluster_status_counts[status], `aggregate.cluster_status_counts.${status}`);\n        asse'
    'rt(documentModel.aggregate.cluster_status_counts[status] === expected, "aggregate: inconsistent run '
    'counts.");\n      } else assert(expected === 0, "aggregate: a non-zero run count is missing.");\n    }'
    '\n    return documentModel;\n  };\n  const preferences = {storage: true};\n  const mediaTheme = window.m'
    'atchMedia("(prefers-color-scheme: dark)");\n  const themeNote = message => { byId("theme-note").hidde'
    'n = false; byId("theme-note").textContent = message; };\n  const storageError = error => {\n    if (!('
    'error instanceof DOMException) || !["SecurityError", "QuotaExceededError"].includes(error.name)) thr'
    'ow error;\n    preferences.storage = false;\n    themeNote("This browser does not allow saving the the'
    'me. The choice applies only while this file is open.");\n  };\n  let savedTheme = "auto";\n  try {\n    '
    'const saved = localStorage.getItem("aks-consulting-report-theme");\n    if (saved !== null && ["auto"'
    ', "light", "dark"].includes(saved)) savedTheme = saved;\n    else if (saved !== null) themeNote("The '
    'saved theme preference is not valid; the system theme is used.");\n  } catch (error) { storageError(e'
    'rror); }\n  byId("theme-mode").value = savedTheme;\n  const applyTheme = () => { document.documentElem'
    'ent.dataset.theme = byId("theme-mode").value === "auto" ? (mediaTheme.matches ? "dark" : "light") : '
    'byId("theme-mode").value; };\n  applyTheme();\n  byId("theme-mode").addEventListener("change", () => {'
    '\n    applyTheme();\n    if (preferences.storage) {\n      try { localStorage.setItem("aks-consulting-r'
    'eport-theme", byId("theme-mode").value); } catch (error) { storageError(error); }\n    }\n  });\n  medi'
    'aTheme.addEventListener("change", () => { if (byId("theme-mode").value === "auto") applyTheme(); });'
    '\n  let model, documentModel, embeddedJson, clusterRuns;\n  try {\n    embeddedJson = byId("report-data'
    '").textContent;\n    assert(new TextEncoder().encode(embeddedJson).length <= MAX_BYTES, "The full JSO'
    'N exceeds the 4,800,000-byte limit.");\n    documentModel = validateDocument(JSON.parse(embeddedJson)'
    ');\n    clusterRuns = documentModel.schema_version === "1.0" ? [{cluster_id: documentModel.cluster.id'
    ', cluster_name: documentModel.cluster.name,\n      reference_utc: documentModel.reference_utc, status'
    ': "ok", error: null, snapshot: documentModel}] : documentModel.cluster_runs;\n    model = clusterRuns'
    '[0].snapshot;\n  } catch (error) {\n    document.body.dataset.status = "error";\n    byId("opening-stat'
    'e").setAttribute("role", "alert");\n    byId("opening-message").textContent = "The report could not b'
    'e opened. No partial results are shown.";\n    byId("opening-detail").textContent = `Invalid data: ${'
    'error.message}. Ask the generator for a new complete snapshot compatible with schema 1.0 or aks-waf-'
    'multi-cluster-v1.`;\n    return;\n  }\n  const sourceMap = new Map();\n  const checkMap = new Map();\n  c'
    'onst workloadMap = new Map();\n  const workloadResourceCounts = new Map();\n  const workloadIdentity ='
    ' record => {\n    const reference = record.kubernetes_ref || record;\n    return {resource_id: record.'
    'resource_id, namespace: record.namespace || reference.namespace, name: record.workload_name || refer'
    'ence.name,\n      kind: reference.kind || record.kind, uid: reference.uid || record.uid};\n  };\n  cons'
    't workloadKey = record => {\n    const identity = workloadIdentity(record);\n    if (identity.uid) ret'
    'urn JSON.stringify([identity.resource_id, identity.uid]);\n    if (workloadResourceCounts.get(identit'
    'y.resource_id) === 1) return identity.resource_id;\n    return JSON.stringify([identity.resource_id, '
    'identity.namespace, identity.kind || "", identity.name]);\n  };\n  const matchesWorkload = (record, se'
    'lected) => {\n    if (Object.hasOwn(record, "check_id") && (record.level !== "workload" || !record.wo'
    'rkload_name)) return false;\n    const identity = workloadIdentity(record), target = workloadIdentity'
    '(selected);\n    if (identity.resource_id !== target.resource_id || identity.namespace !== target.nam'
    'espace) return false;\n    if (identity.uid && target.uid) return identity.uid === target.uid;\n    if'
    ' (!identity.name || identity.name !== target.name) return false;\n    if (identity.kind && target.kin'
    'd) return identity.kind === target.kind;\n    return [...workloadMap.values()].filter(row => row.reso'
    'urce_id === target.resource_id && row.namespace === target.namespace && row.name === target.name).le'
    'ngth <= 1;\n  };\n  const state = {pages: new Map(), print: false, openDetails: new Map(), graphNode: '
    '"", graphKind: "", activeCluster: clusterRuns[0].cluster_name,\n    findingsOrder: "severity", filter'
    's: {search: "", area: "", namespace: "", workload: "", level: "", status: "", severity: ""}};\n  cons'
    't detail = (label, key, content) => {\n    const result = node("details", undefined, "receipt");\n    '
    'result.dataset.detailKey = key; add(result, node("summary", label), add(node("div", undefined, "rece'
    'ipt-content"), content));\n    return result;\n  };\n  const facts = entries => {\n    const result = no'
    'de("dl", undefined, "facts");\n    for (const [label, value] of entries) add(result, node("dt", label'
    '), value instanceof Node ? add(node("dd"), value) : node("dd", text(value)));\n    return result;\n  }'
    ';\n  const jsonText = value => JSON.stringify(value, null, state.print ? 0 : 2);\n  const rawReceipt ='
    ' (row, key) => detail("Full evidence and identity", key, node("pre", jsonText(row), "json"));\n  cons'
    't severity = value => node("span", SEVERITY.get(value), `severity ${value}`);\n  const SEVERITY_ORDER'
    ' = [...SEVERITY.keys()];\n  const SEVERITY_WORDS = new Map([["critical", ["critical", "critical"]], ['
    '"high", ["high", "high"]], ["medium", ["medium", "medium"]], ["low", ["low", "low"]]]);\n  const seve'
    'rityRank = value => { const rank = SEVERITY_ORDER.indexOf(value); return rank < 0 ? SEVERITY_ORDER.l'
    'ength : rank; };\n  const severityCounts = findings => new Map(SEVERITY_ORDER.map(key => [key, findin'
    'gs.filter(finding => finding.severity === key).length]));\n  const plural = (number, one, many) => `$'
    '{number.toLocaleString("en-US")} ${number === 1 ? one : many}`;\n  const percentText = value => value'
    ' === null || value === undefined ? "Not evaluated" : `${value.toLocaleString("en-US", {maximumFracti'
    'onDigits: 1})}%`;\n  const countText = rows => rows === null || rows === undefined ? "Not evaluated" '
    ': rows.length.toLocaleString("en-US");\n  const listText = items => items.length <= 1 ? items.join(""'
    ') : `${items.slice(0, -1).join(", ")} and ${items[items.length - 1]}`;\n  const listValue = value => '
    'Array.isArray(value) ? (value.length ? value.map(text).join(", ") : "None") : text(value);\n  const r'
    'ich = (target, parts) => { for (const part of parts) target.append(Array.isArray(part) ? node("b", p'
    'art[0]) : document.createTextNode(part)); return target; };\n  const ARM_RESOURCE = /^\\/subscriptions'
    '\\/[0-9a-f-]{36}\\/resourcegroups\\/[^/?#\\s]+(?:\\/providers\\/[^?#\\s]+)?$/i;\n  const armId = value => {\n'
    '    const wrapper = node("span", undefined, "arm-id");\n    text(value).split("/").forEach((part, ind'
    'ex) => {\n      if (index) wrapper.append("/", document.createElement("wbr"));\n      if (part) wrappe'
    'r.append(part);\n    });\n    return wrapper;\n  };\n  const portalLink = value => {\n    if (typeof valu'
    'e !== "string" || !ARM_RESOURCE.test(value)) return null;\n    const link = permittedLink(`https://po'
    'rtal.azure.com/#@/resource${encodeURI(value)}`, "Azure Portal");\n    link.classList.add("portal-link'
    '");\n    return add(node("span", undefined, "no-print"), document.createTextNode(" · "), link);\n  };\n'
    '  const idWithPortal = value => {\n    const wrapper = add(node("span"), armId(value));\n    const lin'
    'k = portalLink(value); if (link) wrapper.append(link);\n    return wrapper;\n  };\n  const resourceRef '
    '= value => {\n    if (typeof value !== "string" || !ARM_RESOURCE.test(value)) return armId(value);\n  '
    '  const segments = value.split("/").filter(Boolean);\n    const meta = node("span", `Resource group $'
    '{segments[3]}`, "cell-note");\n    const link = portalLink(value); if (link) meta.append(link);\n    r'
    'eturn add(node("span", undefined, "resource-ref"), node("strong", segments[segments.length - 1]), me'
    'ta);\n  };\n  const subjectLabel = record => {\n    if (record.workload_name) return `${text(record.nam'
    'espace)} / ${record.workload_name}`;\n    if (record.namespace) return `namespace ${record.namespace}'
    '`;\n    return typeof record.resource_id === "string" && record.resource_id ? record.resource_id.spli'
    't("/").filter(Boolean).pop() : text(record.resource_id);\n  };\n  const containerSummary = containers '
    '=> {\n    if (!Array.isArray(containers)) return text(containers);\n    if (!containers.length) return'
    ' "0 containers included";\n    const list = node("ul", undefined, "container-list");\n    for (const i'
    'tem of containers) {\n      if (!isObject(item)) { list.append(node("li", text(item))); continue; }\n '
    '     const entry = add(node("li"), node("strong", item.name), node("span", item.image, "mono"));\n   '
    '   const declared = [];\n      for (const [group, label] of [["requests", "requests"], ["limits", "li'
    'mits"]]) {\n        if (!isObject(item[group])) continue;\n        const values = [["cpu", "CPU"], ["m'
    'emory", "memory"]].filter(([key]) => item[group][key] !== null && item[group][key] !== undefined && '
    'item[group][key] !== "")\n          .map(([key, name]) => `${name} ${text(item[group][key])}`);\n     '
    '   if (values.length) declared.push(`${label}: ${values.join(", ")}`);\n      }\n      const probeKeys'
    ' = [["readiness_probe", "readiness"], ["liveness_probe", "liveness"], ["startup_probe", "startup"]];'
    '\n      if (probeKeys.some(([key]) => typeof item[key] === "boolean")) {\n        const probes = probe'
    'Keys.filter(([key]) => item[key] === true).map(([, label]) => label);\n        declared.push(probes.l'
    'ength ? `probes: ${probes.join(", ")}` : "probes: none declared");\n      }\n      if (isObject(item.s'
    'ecurity) && item.security.privileged === true) declared.push("privileged");\n      if (declared.lengt'
    'h) entry.append(node("span", declared.join(" · "), "cell-note"));\n      list.append(entry);\n    }\n  '
    '  return list;\n  };\n  const permittedLink = (value, label) => {\n    if (!value) return node("span", '
    '"Not evaluated");\n    let url;\n    try { url = new URL(value); } catch (error) { if (!(error instanc'
    'eof TypeError)) throw error; return node("span", `${text(value)} (link not enabled)`); }\n    const a'
    'llowed = url.protocol === "https:" && !url.username && !url.password && !url.port && (\n      (url.ho'
    'stname === "learn.microsoft.com" && /^\\/(?:[a-z]{2}-[a-z]{2}\\/)?(?:azure|well-architected|security|t'
    'roubleshoot)\\//i.test(url.pathname)) ||\n      (url.hostname === "portal.azure.com" && url.pathname ='
    '== "/")\n    );\n    if (!allowed) return node("span", `${text(value)} (link not enabled)`, "source-ur'
    'l");\n    const link = node("a", label); link.href = url.href; link.target = "_blank"; link.rel = "no'
    'opener noreferrer"; return link;\n  };\n  const sourceIdentity = row => {\n    const source = sourceMap'
    '.get(row.source_id);\n    return `${text(row.source_id)} / ${source ? SOURCE_STATUS.get(source.status'
    ') : "Not evaluated"} / ${utc(row.observed_at)}`;\n  };\n  const namedRecord = (row, collection) => {\n '
    '   const wrapper = node("div");\n    const name = text(row.name || row.title || row.resource_id);\n   '
    ' if ((collection === "namespaces" && row.name) || (collection === "workloads" && row.name && row.res'
    'ource_id)) {\n      const button = node("button", name, "text-button"); button.type = "button";\n     '
    ' button.dataset.drilldown = collection; button.dataset.resourceId = text(row.resource_id);\n      but'
    'ton.addEventListener("click", () => {\n        state.filters.namespace = collection === "namespaces" '
    '? (row.name || "") : (row.namespace || "");\n        state.filters.workload = collection === "workloa'
    'ds" ? workloadKey(row) : "";\n        byId("filter-namespace").value = state.filters.namespace; popul'
    'ateWorkloads(); byId("filter-workload").value = state.filters.workload;\n        filtersChanged(false'
    '); byId("findings").scrollIntoView(); byId("findings-title").tabIndex = -1; byId("findings-title").f'
    'ocus({preventScroll: true});\n      });\n      wrapper.append(button);\n    } else wrapper.append(node('
    '"strong", name));\n    add(wrapper, node("span", sourceIdentity(row), "cell-note"), rawReceipt(row, `'
    'inventory:${collection}:${text(row.resource_id)}:${name}`));\n    return wrapper;\n  };\n  const scoreC'
    'aption = score => `${score.evaluated} evaluated; ${score.not_evaluated} not evaluated; ${score.not_a'
    'pplicable} not applicable.`;\n  const scoreRow = (label, score) => {\n    const wrapper = node("div", '
    'undefined, "score-row");\n    const head = add(node("div", undefined, "score-row-head"), node("span",'
    ' label), node("span", percentage(score.score), "score-number"));\n    const track = node("div", undef'
    'ined, "score-track");\n    if (score.score !== null) {\n      track.setAttribute("role", "meter"); tra'
    'ck.setAttribute("aria-label", `Local index: ${label}`);\n      track.setAttribute("aria-valuemin", "0'
    '"); track.setAttribute("aria-valuemax", "100"); track.setAttribute("aria-valuenow", String(score.sco'
    're));\n      track.setAttribute("aria-valuetext", `${percentage(score.score)}. ${scoreCaption(score)}'
    '`);\n      const fill = node("div", undefined, "score-fill"); fill.style.width = `${score.score}%`; t'
    'rack.append(fill);\n    } else track.setAttribute("aria-hidden", "true");\n    add(wrapper, head, trac'
    'k, node("p", scoreCaption(score), "score-caption"));\n    return wrapper;\n  };\n  const money = value '
    '=> value === null || value === undefined ? "Not evaluated" : `${value.toLocaleString("en-US", {maxim'
    'umFractionDigits: 2})} ${model.finops.currency || "(currency not reported)"}`;\n  const cssString = v'
    'alue => `"${String(value).replace(/[\\\\"]/g, "\\\\$&").replace(/[\\u0000-\\u001f\\u007f]/g, " ")}"`;\n  con'
    'st kpi = (value, unit, label, note, unknown = false) => {\n    const valueNode = node("p", value, `kp'
    'i-value${unknown ? " unknown" : ""}`);\n    if (unit && !unknown) valueNode.append(node("span", unit,'
    ' "kpi-unit"));\n    return add(node("div", undefined, "kpi"), valueNode, node("p", label, "kpi-label"'
    '), node("p", note, "kpi-note"));\n  };\n  const renderCover = () => {\n    for (const id of ["brand-pla'
    'que", "provenance", "cover-facts", "cover-id", "hero-summary", "verdict", "severity-distribution", "'
    'kpis", "simulation-note"]) byId(id).replaceChildren();\n    byId("client-name").textContent = model.c'
    'lient.name;\n    const plaque = byId("brand-plaque");\n    if (model.client.logo_data_uri) {\n      con'
    'st image = node("img"); image.src = model.client.logo_data_uri; image.alt = model.client.logo_alt ||'
    ' `${model.client.name} logo`;\n      plaque.append(image);\n    } else plaque.append(node("span", "CUS'
    'TOMER", "brand-placeholder"));\n    const score = model.scores.global, coverage = model.scores.covera'
    'ge, counts = severityCounts(model.findings);\n    const breakdown = SEVERITY_ORDER.filter(key => coun'
    'ts.get(key)).map((key, index, keys) => `${counts.get(key)} ${SEVERITY_WORDS.get(key)[0]}${index === '
    'keys.length - 1 ? " severity" : ""}`);\n    rich(byId("hero-summary"), score.evaluated ? [\n      [plu'
    'ral(model.findings.length, "finding", "findings")], " in ", [model.cluster.name], breakdown.length ?'
    ' ` (${listText(breakdown)})` : "", " from ",\n      [plural(score.evaluated, "evaluated check", "eval'
    'uated checks")], "; coverage ", [percentText(coverage.coverage_percent)],\n      `, with ${plural(cov'
    'erage.not_evaluated, "check", "checks")} not evaluated.`,\n      model.findings.length ? "" : " Havin'
    'g no findings does not prove there is no risk."\n    ] : [["No checks evaluated"], " in ", [model.clu'
    'ster.name], `: the local index stays Not evaluated and ${plural(coverage.not_evaluated, "check remai'
    'ns", "checks remain")} not evaluated.`]);\n    const provenance = model.provenance === "LIVE" ? "Obse'
    'rved data / snapshot" : "SIMULATED / test data, not live";\n    const environment = {LAB: "LAB / test'
    ' environment", PRODUCTION: "Declared production environment", UNSPECIFIED: "Environment not specifie'
    'd"}[model.environment];\n    add(byId("provenance"), node("span", `Reference ${utc(model.reference_ut'
    'c)}`, "chip"), node("span", provenance, `chip${model.provenance === "LIVE" ? "" : " strong"}`),\n    '
    '  node("span", environment, "chip"), node("span", `${text(model.cluster.name)} · ${text(model.cluste'
    'r.resource_group)}`, "chip"));\n    if (clusterRuns.length > 1) {\n      const position = clusterRuns.'
    'findIndex(run => run.cluster_name === state.activeCluster) + 1;\n      const link = node("a", `Cluste'
    'r ${position} of ${clusterRuns.length} · change`, "chip no-print"); link.href = "#cluster-overview";'
    '\n      byId("provenance").append(link);\n    }\n    const [tone, verdictText] = counts.get("critical")'
    ' ? ["critical", "Action required"] : counts.get("high") ? ["high", "Needs attention"] :\n      model.'
    'findings.length ? ["medium", "Review recommended"] : score.evaluated ? ["none", "No findings recorde'
    'd"] : ["unknown", "Not evaluated"];\n    const verdict = byId("verdict"); verdict.className = `verdic'
    't tone-${tone}`;\n    const verdictLabel = node("p", "Verdict", "verdict-label"); verdictLabel.id = "'
    'verdict-label";\n    add(verdict, verdictLabel, node("p", verdictText, "verdict-value"),\n      node("'
    'p", SEVERITY_ORDER.map(key => `${counts.get(key)} ${SEVERITY_WORDS.get(key)[counts.get(key) === 1 ? '
    '0 : 1]}`).join(" · "), "verdict-detail"),\n      node("p", !score.evaluated ? "No checks evaluated: r'
    'eview the sources before you conclude." : model.findings.length ?\n        `Based on ${plural(score.e'
    'valuated, "evaluated check", "evaluated checks")} (coverage ${percentText(coverage.coverage_percent)'
    '}). Not an official rating.` :\n        `This does not mean there is no risk: coverage ${percentText('
    'coverage.coverage_percent)}.`, "verdict-note"));\n    const distribution = byId("severity-distributio'
    'n");\n    const track = node("div", undefined, "distribution-track"); track.setAttribute("aria-hidden'
    '", "true");\n    const legend = node("div", undefined, "distribution-legend");\n    for (const key of '
    'SEVERITY_ORDER) {\n      const number = counts.get(key);\n      if (number) { const segment = node("di'
    'v", undefined, `distribution-segment ${key}`); segment.style.width = `${number / model.findings.leng'
    'th * 100}%`; track.append(segment); }\n      const swatch = node("span", undefined, `legend-swatch ${'
    'key}`); swatch.setAttribute("aria-hidden", "true");\n      add(legend, add(node("span", undefined, "l'
    'egend-item"), swatch, document.createTextNode(`${SEVERITY.get(key)} `), node("b", number)));\n    }\n '
    '   add(distribution, add(node("p", undefined, "distribution-head"), rich(node("span"), ["Severity di'
    'stribution · ", [plural(model.findings.length, "finding supplied", "findings supplied")]]),\n      no'
    'de("span", "Checks not evaluated are shown neither as findings nor as healthy results.")), track, le'
    'gend);\n    const inventory = model.inventory;\n    const counted = (rows, one, many) => rows === null'
    ' || rows === undefined ? `${many}: Not evaluated` : `${countText(rows)} ${rows.length === 1 ? one : '
    'many}`;\n    add(byId("kpis"),\n      score.evaluated ? kpi(model.findings.length.toLocaleString("en-U'
    'S"), "", "Findings recorded", SEVERITY_ORDER.slice(0, 2).map(key => `${SEVERITY.get(key)} ${counts.g'
    'et(key)}`).join(" · ")) :\n        kpi("Not evaluated", "", "Findings recorded", `${model.findings.le'
    'ngth} supplied: no checks evaluated`, true),\n      score.score === null ? kpi("Not evaluated", "", "'
    'Overall local index", "No checks evaluated", true) :\n        kpi(score.score.toLocaleString("en-US",'
    ' {maximumFractionDigits: 1}), "/ 100", "Overall local index", `${score.passed} of ${score.evaluated}'
    ' evaluated passed · unofficial`),\n      coverage.coverage_percent === null ? kpi("Not evaluated", ""'
    ', "Assessment coverage", "No applicable checks to evaluate", true) :\n        kpi(coverage.coverage_p'
    'ercent.toLocaleString("en-US", {maximumFractionDigits: 1}), "%", "Assessment coverage", `${coverage.'
    'not_evaluated} not evaluated · ${coverage.not_applicable} not applicable`),\n      model.finops.actua'
    'l_cost === null || model.finops.actual_cost === undefined ?\n        kpi("Not evaluated", "", "Observ'
    'ed cost", "No complete observed amount; see FinOps", true) :\n        kpi(model.finops.actual_cost.to'
    'LocaleString("en-US", {maximumFractionDigits: 2}), model.finops.currency || "(currency not reported)'
    '", "Observed cost",\n          model.finops.estimated_savings === null ? "Savings: to be estimated" :'
    ' `Estimated savings supplied: ${money(model.finops.estimated_savings)}`),\n      inventory.workloads '
    '=== null || inventory.workloads === undefined ?\n        kpi("Not evaluated", "", "Observed workloads'
    '", `${counted(inventory.namespaces, "namespace", "namespaces")} · ${counted(inventory.node_pools, "p'
    'ool", "pools")}`, true) :\n        kpi(countText(inventory.workloads), "", "Observed workloads", `${c'
    'ounted(inventory.namespaces, "namespace", "namespaces")} · ${counted(inventory.node_pools, "pool", "'
    'pools")} · ${counted(inventory.related_resources, "associated resource", "associated resources")}`))'
    ';\n    const simulation = byId("simulation-note"); simulation.hidden = model.provenance === "LIVE";\n '
    '   add(simulation, node("strong", "Simulated data."), document.createTextNode(" Nothing was read fro'
    'm Azure: the figures are not observations of a customer or a real cluster."));\n    const entries = ['
    '\n      ["Cluster", model.cluster.name], ["Subscription", model.cluster.subscription_name || model.cl'
    'uster.subscription_id],\n      ["Resource group", model.cluster.resource_group], ["Region", model.clu'
    'ster.region], ["AKS version", model.cluster.version],\n      ["UTC reference", utc(model.reference_ut'
    'c)], ["Cluster power state", model.cluster.power_state],\n      ["Cluster provisioning", model.cluste'
    'r.provisioning_state], ["SKU / mode", `${text(model.cluster.sku_tier)} / ${text(model.cluster.mode)}'
    '`]\n    ];\n    for (const [label, value] of entries) {\n      const wrapper = add(node("div"), node("d'
    't", label), node("dd", value));\n      if (label === "UTC reference") wrapper.className = "reference-'
    'fact";\n      if (label === "Subscription") wrapper.className = "wide-fact";\n      byId("cover-facts"'
    ').append(wrapper);\n    }\n    add(byId("cover-id"), add(node("p"), document.createTextNode("Cluster I'
    'D: "), idWithPortal(model.cluster.id)),\n      add(node("p"), document.createTextNode("Subscription I'
    'D: "), armId(model.cluster.subscription_id)));\n    byId("cover-id").append(detail("Full cluster scop'
    'e and identity", "cluster-identity", node("pre", jsonText(model.cluster), "json")));\n    byId("foote'
    'r-reference").textContent = `${model.client.name} / ${model.cluster.name} / ${environment} / ${prove'
    'nance} / ${utc(model.reference_utc)} / schema ${model.schema_version}.`;\n    document.documentElemen'
    't.style.setProperty("--print-footer", cssString(`AKS architecture and configuration review · ${model'
    '.cluster.name} · ${utc(model.reference_utc)}`));\n  };\n  const renderExecutive = () => {\n    for (con'
    'st id of ["global-index", "area-scores", "pillar-scores", "global-coverage", "critical-findings", "n'
    'ext-actions", "executive-messages", "assessment-chart"]) byId(id).replaceChildren();\n    const score'
    ' = model.scores.global;\n    add(byId("global-index"), node("h3", "Overall local index"), node("span"'
    ', percentage(score.score), `score-value${score.score === null ? " unknown" : ""}`),\n      node("p", '
    'scoreCaption(score)), node("p", `${score.passed} passed / ${score.failed} failed.`, "muted"),\n      '
    'node("p", "Full scope. Not an official rating.", "qualification"));\n    for (const [key, label] of A'
    'REA) byId("area-scores").append(scoreRow(label, model.scores.areas[key]));\n    for (const [key, labe'
    'l] of PILLAR) byId("pillar-scores").append(scoreRow(label, model.scores.pillars[key]));\n    const co'
    'verage = model.scores.coverage;\n    add(byId("global-coverage"), add(node("p"), document.createTextN'
    'ode("Coverage received: "),\n      node("strong", coverage.coverage_percent === null ? "Not evaluated'
    '" : `${coverage.coverage_percent.toLocaleString("en-US", {maximumFractionDigits: 1})}%`, "coverage-n'
    'umber"),\n      document.createTextNode(`. ${scoreCaption(coverage)}`)),\n      node("p", `${plural(co'
    'verage.total, "unique check", "unique checks")} included. ${plural(model.sources.length, "source", "'
    'sources")} recorded; check their status and limits.`, "muted"));\n    const chart = byId("assessment-'
    'chart");\n    const segments = [["passed", "Passed", score.passed, "var(--accent)", "Evaluated with n'
    'o local finding"],\n      ["failed", "Failed", score.failed, "var(--high-bar)", "Evaluated with evide'
    'nce of a failure"],\n      ["not_evaluated", "Not evaluated", score.not_evaluated, "var(--field-line)'
    '", "Configuration or intent unknown"],\n      ["not_applicable", "Not applicable", score.not_applicab'
    'le, "var(--surface)", "Outside the denominators"]];\n    const heading = node("h3", "What could be ev'
    'aluated"); heading.id = "assessment-chart-title";\n    const head = add(node("div", undefined, "chart'
    '-head"), heading,\n      add(node("p", undefined, "chart-total-line"), node("span", score.total, "cha'
    'rt-total"), node("span", "checks", "chart-unit")));\n    const drawing = svgNode("svg", {viewBox: "0 '
    '0 1000 14", preserveAspectRatio: "none", role: "img", class: "status-bar", "aria-labelledby": "asses'
    'sment-svg-title assessment-svg-description"});\n    add(drawing, svgNode("title", {id: "assessment-sv'
    'g-title"}, "Check count by status; not a health chart"),\n      svgNode("desc", {id: "assessment-svg-'
    'description"}, `${score.passed} passed; ${score.failed} failed; ${score.not_evaluated} not evaluated'
    '; ${score.not_applicable} not applicable. ${score.total} in total.`));\n    let offset = 0;\n    for ('
    'const [key, , number, color] of segments) {\n      if (!score.total || !number) continue;\n      const'
    ' width = number / score.total * 1000;\n      drawing.append(svgNode("rect", {x: offset, y: 0, width, '
    'height: 14, fill: color, class: key,\n        ...(key === "not_applicable" ? {stroke: "var(--field-li'
    'ne)", "vector-effect": "non-scaling-stroke"} : {})}));\n      offset += width;\n    }\n    const table '
    '= node("table"); table.append(node("caption", "Chart data: full scope of this cluster"));\n    const '
    'header = node("tr");\n    for (const label of ["Status", "Count", "Meaning"]) { const cell = node("th'
    '", label); cell.scope = "col"; header.append(cell); }\n    const body = node("tbody");\n    for (const'
    ' [key, label, number, , meaning] of segments) {\n      const swatch = node("span", undefined, `status'
    '-swatch ${key}`); swatch.setAttribute("aria-hidden", "true");\n      const status = add(node("th"), s'
    'watch, document.createTextNode(label)); status.scope = "row";\n      body.append(add(node("tr"), stat'
    'us, node("td", number), node("td", meaning)));\n    }\n    add(table, add(node("thead"), header), body'
    ');\n    add(chart, head, drawing, table, node("figcaption", "The local index describes evaluated chec'
    'ks only; coverage shows how much is still unknown. Not evaluated is not a passed result, and Not app'
    'licable does not improve coverage."));\n    const sourceLink = node("a", "See the source register"); '
    'sourceLink.href = "#sources-title"; byId("global-coverage").append(sourceLink);\n    const critical ='
    ' model.findings.filter(finding => finding.severity === "critical");\n    byId("critical-title").textC'
    'ontent = `Critical priorities / ${critical.length} recorded`;\n    if (!critical.length) byId("critic'
    'al-findings").append(empty("0 critical findings recorded. This does not mean there is no risk; revie'
    'w the coverage and the sources not evaluated."));\n    else {\n      const list = node("ol", undefined'
    ', "priority-list");\n      for (const finding of critical.slice(0, 5)) {\n        const item = node("l'
    'i");\n        add(item, node("strong", `${finding.check_id} / ${finding.title}`), node("p", `${LEVEL.'
    'get(finding.level)} · ${subjectLabel(finding)}`, "muted"),\n          node("p", finding.business_impa'
    'ct), node("p", finding.recommendation));\n        list.append(item);\n      }\n      add(byId("critical'
    '-findings"), list, node("p", `Showing ${Math.min(5, critical.length)} of ${critical.length}. The ful'
    'l list is in Findings.`, "qualification"));\n    }\n    const buckets = [...BUCKET.keys()];\n    const '
    'planned = [...model.actions].sort((left, right) => ((buckets.indexOf(left.planning_bucket) + 4) % 4 '
    '- (buckets.indexOf(right.planning_bucket) + 4) % 4) ||\n      (severityRank(left.severity) - severity'
    'Rank(right.severity)));\n    if (!planned.length) byId("next-actions").append(empty("The engine suppl'
    'ied no actions to review. This does not mean there is no risk."));\n    else {\n      const list = nod'
    'e("ol", undefined, "next-actions");\n      for (const action of planned.slice(0, 5)) {\n        const '
    'horizon = (BUCKET.get(action.planning_bucket) || [text(action.planning_bucket)])[0].split(" / ")[0];'
    '\n        add(list, add(node("li"), severity(action.severity), node("strong", action.title),\n        '
    '  node("span", `${horizon} · ${subjectLabel(action)} · ${(EFFORT.get(action.effort) || "not evaluate'
    'd").toLocaleLowerCase("en-US")} effort`, "cell-note")));\n      }\n      const link = node("a", `See t'
    'he full plan (${plural(model.actions.length, "action", "actions")})`, "card-link"); link.href = "#ac'
    'tions";\n      add(byId("next-actions"), list, link);\n    }\n    if (!model.executive_messages.length)'
    ' byId("executive-messages").append(node("li", "Not evaluated: the engine included no executive messa'
    'ges."));\n    for (const message of model.executive_messages) byId("executive-messages").append(node('
    '"li", message));\n  };\n  const fillOptions = (select, labels) => { for (const [value, label] of label'
    's) { const option = node("option", label); option.value = value; select.append(option); } };\n  const'
    ' namespaces = new Set();\n  const populateWorkloads = () => {\n    const select = byId("filter-workloa'
    'd"); select.replaceChildren(node("option", "All workloads")); select.firstChild.value = "";\n    cons'
    't rows = [...workloadMap.entries()].filter(([, row]) => !state.filters.namespace || row.namespace =='
    '= state.filters.namespace);\n    rows.sort(([, left], [, right]) => `${left.namespace}/${left.name}/$'
    '{text(left.kind)}`.localeCompare(`${right.namespace}/${right.name}/${text(right.kind)}`, "en"));\n   '
    ' for (const [key, row] of rows) { const option = node("option", `${text(row.namespace)} / ${text(row'
    '.name)}${row.kind ? ` / ${row.kind}` : ""}`); option.value = key; select.append(option); }\n    if (!'
    'rows.some(([key]) => key === state.filters.workload)) state.filters.workload = "";\n    select.value '
    '= state.filters.workload;\n  };\n  fillOptions(byId("filter-area"), AREA); fillOptions(byId("filter-le'
    'vel"), LEVEL); fillOptions(byId("filter-status"), STATUS); fillOptions(byId("filter-severity"), SEVE'
    'RITY);\n  const containsSearch = value => !state.filters.search || JSON.stringify(value).toLocaleLowe'
    'rCase("en-US").includes(state.filters.search.toLocaleLowerCase("en-US"));\n  const matchedChecks = ()'
    ' => model.checks.filter(check => {\n    const f = state.filters;\n    return (!f.area || check.area =='
    '= f.area) && (!f.namespace || check.namespace === f.namespace) &&\n      (!f.workload || matchesWorkl'
    'oad(check, workloadMap.get(f.workload))) && (!f.level || check.level === f.level) &&\n      (!f.statu'
    's || check.status === f.status) && (!f.severity || (check.status === "failed" && check.severity === '
    'f.severity)) && containsSearch(check);\n  });\n  const currentScope = () => {\n    const checks = match'
    'edChecks();\n    const ids = new Set(checks.map(check => check.resource_id));\n    const checkIds = ne'
    'w Set(checks.map(check => check.check_id));\n    const namespaceIds = new Set(checks.map(check => che'
    'ck.namespace).filter(Boolean));\n    const selectedWorkload = workloadMap.get(state.filters.workload)'
    ';\n    const filterRecord = (row, collection) => {\n      const f = state.filters;\n      const namespa'
    'ce = collection === "namespaces" ? row.name : row.namespace;\n      const namespaceScoped = Boolean(n'
    'amespace);\n      const idMatch = collection === "namespaces" ? namespaceIds.has(namespace) : namespa'
    'ceScoped ? checks.some(check => matchesWorkload(check, row)) : ids.has(row.resource_id);\n      if (f'
    '.namespace && namespace !== f.namespace && (namespaceScoped || !idMatch)) return false;\n      if (f.'
    'workload) {\n        if (collection === "namespaces") { if (namespace !== selectedWorkload.namespace)'
    ' return false; }\n        else if (namespaceScoped || collection === "workloads") { if (!matchesWorkl'
    'oad(row, selectedWorkload)) return false; }\n        else if (!idMatch) return false;\n      }\n      i'
    'f ((f.area || f.level || f.status || f.severity) && !idMatch && !(collection === "namespaces" && nam'
    'espaceIds.has(namespace))) return false;\n      return containsSearch(row) || idMatch || (collection '
    '=== "namespaces" && namespaceIds.has(namespace));\n    };\n    const inventory = Object.create(null);\n'
    '    for (const [key, rows] of Object.entries(model.inventory)) inventory[key] = rows === null ? null'
    ' : rows.filter(row => filterRecord(row, key));\n    const findings = model.findings.filter(finding =>'
    ' checkIds.has(finding.check_id));\n    const candidates = model.finops.candidates === null ? null : m'
    'odel.finops.candidates.filter(row => (!state.filters.area || state.filters.area === "finops") && fil'
    'terRecord(row, "finops.candidates"));\n    const actions = model.actions.filter(action => checkIds.ha'
    's(action.check_id));\n    return {checks, findings, inventory, candidates, actions, filterRecord};\n  '
    '};\n  const showLimit = key => state.print ? Infinity : (state.pages.get(key) || PAGE_SIZE);\n  const '
    'pagination = (container, key, total, shown, rerender) => {\n    const footer = node("div", undefined,'
    ' "table-footer");\n    footer.append(node("span", `${shown} of ${plural(total, "matching record", "ma'
    'tching records")}. The export includes all matches.`));\n    const button = node("button", shown < to'
    'tal ? `Show ${Math.min(PAGE_SIZE, total - shown)} more` : "All records shown");\n    button.type = "b'
    'utton"; button.disabled = shown >= total; button.dataset.moreCollection = key;\n    button.addEventLi'
    'stener("click", () => {\n      state.pages.set(key, showLimit(key) + PAGE_SIZE); rerender();\n      fo'
    'r (const next of document.querySelectorAll("button[data-more-collection]")) if (next.dataset.moreCol'
    'lection === key) { next.focus({preventScroll: true}); break; }\n    });\n    add(footer, button); cont'
    'ainer.append(footer);\n  };\n  const updateCue = element => {\n    const hidden = element.scrollLeft > '
    '1, remaining = element.scrollWidth - element.clientWidth - element.scrollLeft > 1;\n    if (hidden ||'
    ' remaining) element.dataset.overflow = hidden && remaining ? "both" : hidden ? "left" : "right";\n   '
    ' else delete element.dataset.overflow;\n  };\n  let cueFrame = 0;\n  const refreshCues = () => {\n    ca'
    'ncelAnimationFrame(cueFrame);\n    cueFrame = requestAnimationFrame(() => { for (const element of doc'
    'ument.querySelectorAll(".table-scroll")) updateCue(element); });\n  };\n  document.addEventListener("s'
    'croll", event => { if (event.target instanceof Element && event.target.classList.contains("table-scr'
    'oll")) updateCue(event.target); }, true);\n  document.addEventListener("toggle", refreshCues, true);\n'
    '  window.addEventListener("resize", refreshCues);\n  const renderTable = (container, key, label, colu'
    'mns, rows, rerender) => {\n    container.replaceChildren();\n    refreshCues();\n    if (rows === null)'
    ' { container.append(empty(`Not evaluated: the ${label.toLocaleLowerCase("en-US")} collection was not'
    ' included. See the source register.`)); return; }\n    if (!rows.length) { container.append(empty(`0 '
    'matching records in ${label.toLocaleLowerCase("en-US")}. An inventory with no records included does '
    'not prove that there are no resources or no risk.`)); return; }\n    const wrapper = node("div", unde'
    'fined, "table-scroll"); wrapper.tabIndex = 0; wrapper.setAttribute("role", "region"); wrapper.setAtt'
    'ribute("aria-label", `${label}: scrollable table`);\n    const table = node("table", undefined, "wide'
    '-table"); table.dataset.collection = key;\n    table.append(node("caption", `${label} / ${plural(rows'
    '.length, "matching record", "matching records")}. Identity, source and date are in the expandable ev'
    'idence.`));\n    const header = node("tr");\n    for (const [title] of columns) { const cell = node("t'
    'h", title); cell.scope = "col"; header.append(cell); }\n    table.append(add(node("thead"), header));'
    '\n    const body = node("tbody"); const visible = rows.slice(0, showLimit(key));\n    for (const row o'
    'f visible) {\n      const tr = node("tr");\n      for (const [, read] of columns) {\n        const valu'
    'e = read(row); const cell = node("td");\n        if (value instanceof Node) cell.append(value); else '
    'cell.textContent = text(value);\n        tr.append(cell);\n      }\n      body.append(tr);\n    }\n    ad'
    'd(table, body); add(wrapper, table); container.append(wrapper);\n    if (state.print) {\n      // Prin'
    't full-width receipts after the table instead of squeezing them into a narrow column.\n      const ap'
    'pendix = node("div", undefined, "print-receipts");\n      for (const tr of body.rows) {\n        const'
    ' label = (tr.cells[0]?.querySelector("strong, button") || tr.cells[0])?.textContent.trim() || "";\n  '
    '      for (const receipt of tr.querySelectorAll("details.receipt")) {\n          const summary = rece'
    'ipt.querySelector(":scope > summary");\n          if (summary && label) summary.textContent = `${summ'
    'ary.textContent} · ${label}`;\n          appendix.append(receipt);\n        }\n      }\n      if (append'
    'ix.childElementCount) container.append(appendix);\n    }\n    pagination(container, key, rows.length, '
    'visible.length, rerender);\n  };\n  const renderInventory = scope => {\n    byId("inventory-counts").re'
    'placeChildren();\n    const singular = {node_pools: "node pool", namespaces: "namespace", workloads: '
    '"workload", related_resources: "associated resource"};\n    for (const key of ["node_pools", "namespa'
    'ces", "workloads", "related_resources"]) {\n      const rows = scope.inventory[key]; const item = nod'
    'e("span");\n      add(item, node("b", rows === null ? "Not evaluated" : rows.length), document.create'
    'TextNode(` ${rows !== null && rows.length === 1 ? singular[key] : COLLECTION.get(key).toLocaleLowerC'
    'ase("en-US")}`)); byId("inventory-counts").append(item);\n    }\n    renderTable(byId("node-pools"), "'
    'node_pools", "Node pools", [\n      ["Pool / evidence", row => namedRecord(row, "node_pools")], ["Mod'
    'e / size", row => `${text(row.mode)} / ${text(row.vm_size)}`],\n      ["Nodes / autoscaling", row => '
    '`${text(row.count)} / ${row.enable_auto_scaling === true ? "On" : row.enable_auto_scaling === false '
    '? "Off" : "Not evaluated"} (${text(row.min_count)} - ${text(row.max_count)})`],\n      ["Zones / vers'
    'ion", row => `${listValue(row.availability_zones)} / ${text(row.version)}`], ["Pool provisioning", r'
    'ow => row.provisioning_state]\n    ], scope.inventory.node_pools, renderFiltered);\n    renderTable(by'
    'Id("namespaces"), "namespaces", "Namespaces", [\n      ["Namespace / explore", row => namedRecord(row'
    ', "namespaces")], ["Observed status", row => row.phase ?? row.status],\n      ["ARM resource", row =>'
    ' resourceRef(row.resource_id)]\n    ], scope.inventory.namespaces, renderFiltered);\n    renderTable(b'
    'yId("workloads"), "workloads", "Workloads", [\n      ["Workload / explore", row => namedRecord(row, "'
    'workloads")], ["Namespace / kind", row => `${text(row.namespace)} / ${text(row.kind)}`],\n      ["Rea'
    'dy / desired replicas", row => `${text(row.ready_replicas)} / ${text(row.desired_replicas)}`],\n     '
    ' ["Observed containers", row => row.containers === null || row.containers === undefined ? "Not evalu'
    'ated" : containerSummary(row.containers)]\n    ], scope.inventory.workloads, renderFiltered);\n    ren'
    'derTable(byId("related-resources"), "related_resources", "Associated resources", [\n      ["Resource '
    '/ evidence", row => namedRecord(row, "related_resources")], ["Type", row => row.type ?? row.resource'
    '_type ?? row.kind],\n      ["Group / region", row => `${text(row.resource_group)} / ${text(row.region'
    ')}`], ["Resource ID", row => idWithPortal(row.resource_id)]\n    ], scope.inventory.related_resources'
    ', renderFiltered);\n    const additional = byId("technical-collections"); additional.replaceChildren('
    ');\n    for (const [key, rows] of Object.entries(scope.inventory)) {\n      if (["node_pools", "namesp'
    'aces", "workloads", "related_resources"].includes(key)) continue;\n      const section = node("div", '
    'undefined, "inventory-section"); const label = COLLECTION.get(key) || key;\n      const content = nod'
    'e("div"); add(section, node("h3", label), content); additional.append(section);\n      renderTable(co'
    'ntent, `technical:${key}`, label, [["Record / full evidence", row => namedRecord(row, key)], ["Names'
    'pace", row => row.namespace], ["ARM resource", row => resourceRef(row.resource_id)]], rows, renderFi'
    'ltered);\n    }\n    if (!additional.childElementCount) additional.append(empty("Not evaluated: no add'
    'itional technical collections were included."));\n  };\n  const renderEvidence = (evidence, key) => {\n'
    '    const item = node("li");\n    add(item, facts([["Source", `${evidence.source_id} / ${sourceMap.ha'
    's(evidence.source_id) ? SOURCE_STATUS.get(sourceMap.get(evidence.source_id).status) : "Not evaluated'
    '"}`],\n      ["Observation date", utc(evidence.observed_at)], ["Observed resource", armId(evidence.re'
    'source_id)]]),\n      node("pre", jsonText(evidence.value), "json"));\n    item.dataset.evidenceKey = '
    'key;\n    return item;\n  };\n  const findingDisclosure = finding => {\n    const wrapper = node("detail'
    's", undefined, "finding"); wrapper.dataset.detailKey = `finding:${finding.check_id}`;\n    const summ'
    'ary = node("summary");\n    add(summary, severity(finding.severity), add(node("span", undefined, "fin'
    'ding-main"), node("span", finding.title, "finding-title"),\n      node("span", `${finding.check_id} ·'
    ' ${LEVEL.get(finding.level)} · ${subjectLabel(finding)}`, "finding-reference")));\n    const body = n'
    'ode("div", undefined, "finding-body");\n    add(body, facts([["ID / rule", `${finding.check_id} / ${t'
    'ext(finding.rule_id)}`], ["Level", LEVEL.get(finding.level)], ["Area", AREA.get(finding.area)],\n    '
    '  ["Well-Architected pillar", PILLAR.get(finding.pillar)], ["Severity", SEVERITY.get(finding.severit'
    'y)], ["Indicative effort", EFFORT.get(finding.effort)],\n      ["Namespace / workload", `${text(findi'
    'ng.namespace)} / ${text(finding.workload_name)}`], ["Resource name", finding.resource_name],\n      ['
    '"Resource ID", idWithPortal(finding.resource_id)], ["Checklist ID", finding.checklist_id], ["Checkli'
    'st GUID", finding.checklist_guid],\n      ["Microsoft Learn", permittedLink(finding.learn_url, "Open '
    'the recommendation in Microsoft Learn")],\n      ["Checklist reference", finding.checklist_url], ["Ku'
    'bernetes reference", finding.kubernetes_url]]));\n    add(body, node("h4", "Business impact"), node("'
    'p", finding.business_impact, "prose"), node("h4", "Recommendation"), node("p", finding.recommendatio'
    'n, "prose"));\n    if (finding.reason) add(body, node("h4", "Recorded reason"), node("p", finding.rea'
    'son, "prose"));\n    const list = node("ol", undefined, "evidence-list");\n    for (const [index, evid'
    'ence] of finding.evidence.entries()) list.append(renderEvidence(evidence, `${finding.check_id}:${ind'
    'ex}`));\n    add(body, node("h4", "Observed evidence and source date"), list, rawReceipt(finding, `fi'
    'nding-raw:${finding.check_id}`));\n    return add(wrapper, summary, body);\n  };\n  const renderFinding'
    's = scope => {\n    byId("findings-count").textContent = `${plural(scope.findings.length, "matching f'
    'inding", "matching findings")} of ${model.findings.length} included. ${plural(scope.checks.filter(ch'
    'eck => check.status === "not_evaluated").length, "check", "checks")} not evaluated in this scope.`;\n'
    '    const list = byId("findings-list"); list.replaceChildren(); byId("findings-pagination").replaceC'
    'hildren();\n    const ordered = state.findingsOrder === "model" ? scope.findings : [...scope.findings'
    '].sort((left, right) => severityRank(left.severity) - severityRank(right.severity));\n    const visib'
    'le = ordered.slice(0, showLimit("findings"));\n    for (const [level, label] of LEVEL) {\n      const '
    'group = visible.filter(finding => finding.level === level);\n      if (!group.length) continue;\n     '
    ' const section = node("div", undefined, "findings-group"); section.append(node("h3", label === "Work'
    'load" ? "Workloads" : label === "Associated resource" ? "Associated resources" : label));\n      for '
    '(const finding of group) section.append(findingDisclosure(finding));\n      list.append(section);\n   '
    ' }\n    if (!scope.findings.length) list.append(empty("0 matching findings. This can come from the fi'
    'lters or from missing evaluation; it does not mean the configuration is correct. Review the checks a'
    'nd the sources."));\n    else pagination(byId("findings-pagination"), "findings", scope.findings.leng'
    'th, visible.length, renderFiltered);\n    renderTable(byId("checks-table"), "checks", "Checks and cov'
    'erage", [\n      ["Check / evidence", check => add(node("div"), node("strong", `${check.check_id} / $'
    '{check.title}`), rawReceipt(check, `check:${check.check_id}`))],\n      ["Status / reason", check => '
    'add(node("div"), node("strong", STATUS.get(check.status)), node("span", check.reason, "cell-note"))]'
    ',\n      ["Area / pillar", check => `${AREA.get(check.area)} / ${PILLAR.get(check.pillar)}`], ["Resou'
    'rce", check => resourceRef(check.resource_id)]\n    ], scope.checks, renderFiltered);\n  };\n  const re'
    'nderFinops = scope => {\n    const costSource = model.finops.sources.map(id => sourceMap.get(id)).fin'
    'd(source => source?.cost_type === "ActualCost") || sourceMap.get("azure_cost");\n    const observed ='
    ' add(node("div", undefined, "finops-value"), node("h3", "Observed cost"),\n      node("strong", money'
    '(model.finops.actual_cost), `financial-amount${model.finops.actual_cost === null ? " unknown" : ""}`'
    '),\n      node("p", "Amount supplied by the billing source; not an estimate or a per-namespace invoic'
    'e.", "qualification"));\n    const savings = add(node("div", undefined, "finops-value savings"), node'
    '("h3", "Estimated savings"),\n      node("strong", model.finops.estimated_savings === null ? "To be e'
    'stimated" : money(model.finops.estimated_savings),\n        `financial-amount${model.finops.estimated'
    '_savings === null ? " unknown" : ""}`),\n      node("p", model.finops.estimated_savings === null ?\n  '
    '      "Not calculated. Applicable prices, a representative baseline and the proposal\'s assumptions a'
    're missing. A candidate is not a saving." :\n        "Estimate supplied by the engine, not realized s'
    'avings. Review the window, assumptions and eligibility before you decide.", "qualification"));\n    b'
    'yId("finops-baseline").replaceChildren(add(node("div", undefined, "finops-values"), observed, saving'
    's),\n      facts([["Billing period", windowText(model.finops.window)], ["Observed currency", model.fi'
    'nops.currency],\n        ["Exact cost read scope", costSource?.scope ? armId(costSource.scope) : null'
    '],\n        ["Billing association / not ownership", isObject(costSource?.association) ? Object.entrie'
    's(costSource.association).map(([key, value]) => `${key}: ${text(value)}`).join(" · ") : costSource?.'
    'association],\n        ["Cost source / status", costSource ? `${costSource.id} / ${SOURCE_STATUS.get('
    'costSource.status)}` : "Not evaluated"],\n        ["Complete billing read", model.finops.cost_source_'
    'complete === true ? "Complete per the receipt" : model.finops.cost_source_complete === false ? "Not '
    'complete" : "Not evaluated"],\n        ["Declared sources", model.finops.sources.length ? model.finop'
    's.sources.map(id => `${id} / ${sourceMap.has(id) ? SOURCE_STATUS.get(sourceMap.get(id).status) : "No'
    't evaluated"}`).join("; ") : "Not evaluated"],\n        ["Savings assumptions", model.finops.estimate'
    'd_savings === null ? "Not calculated; no savings model was supplied." : "See the notes and evidence '
    'for the supplied estimate."]]));\n    byId("finops-baseline").append(node("p", "Namespace or workload'
    ' filters do not assign cost to that workload. The period and scope keep the full billing receipt; th'
    'e records can include historical or deleted assets and VMSS child resources.", "qualification"));\n  '
    '  byId("finops-notes").replaceChildren();\n    for (const note of model.finops.notes) byId("finops-no'
    'tes").append(node("li", note));\n    if (!model.finops.notes.length) byId("finops-notes").append(node'
    '("li", "Not evaluated: no financial qualification notes were included."));\n    renderTable(byId("fin'
    'ops-candidates"), "finops-candidates", "FinOps candidates", [\n      ["Candidate / source", row => ad'
    'd(node("div"), node("strong", row.title), node("span", `${text(row.id)} · ${text(row.source_id)}`, "'
    'cell-note"), resourceRef(row.resource_id), rawReceipt(row, `candidate:${text(row.id)}`))],\n      ["B'
    'asis / sample", row => `${text(row.basis)} / ${text(row.value)} ${text(row.unit)} / ${text(row.sampl'
    'e_count)} ${row.sample_count === 1 ? "sample" : "samples"} / ${windowText(row.window)}`],\n      ["Su'
    'pplied recommendation", row => row.recommendation], ["Estimated savings", row => row.estimated_savin'
    'gs === null ? "To be estimated / Not calculated" : money(row.estimated_savings)]\n    ], scope.candid'
    'ates, renderFiltered);\n    const receipts = byId("finops-receipts"); receipts.replaceChildren();\n   '
    ' for (const [key, label] of [["cost_rows", "Costs included"], ["metrics", "Utilization included"]]) '
    '{\n      const content = node("div"); add(receipts, node("h3", label), content);\n      const rows = m'
    'odel.finops[key] === null ? null : model.finops[key].filter(row => (!state.filters.area || state.fil'
    'ters.area === "finops") && scope.filterRecord(row, `finops.${key}`));\n      renderTable(content, `fi'
    'nops:${key}`, label, [["Full record", row => rawReceipt(row, `${key}:${text(row.resource_id)}:${JSON'
    '.stringify(row)}`)]], rows, renderFiltered);\n    }\n  };\n  const graphIconKey = kind => {\n    const v'
    'alue = kind.toLowerCase();\n    if (["aks", "cluster", "managed_cluster", "agent_pool", "node_pool", '
    '"microsoft.containerservice/managedclusters", "microsoft.containerservice/managedclusters/agentpools'
    '"].includes(value)) return "aks";\n    if (["load_balancer", "public_load_balancer", "private_load_ba'
    'lancer", "azure_load_balancer", "load_balancer_frontend_public", "load_balancer_frontend_private",\n '
    '     "load_balancer_backend_pool", "load_balancer_probe", "load_balancer_rule", "microsoft.network/l'
    'oadbalancers"].includes(value)) return "load_balancer";\n    if (["vnet", "subnet", "virtual_network"'
    ', "microsoft.network/virtualnetworks", "microsoft.network/virtualnetworks/subnets"].includes(value))'
    ' return "virtual_network";\n    if (["nsg", "network_security_group", "microsoft.network/networksecur'
    'itygroups"].includes(value)) return "network_security_group";\n    if (["disk", "managed_disk", "micr'
    'osoft.compute/disks"].includes(value)) return "disk";\n    if (["acr", "container_registry", "microso'
    'ft.containerregistry/registries"].includes(value)) return "container_registry";\n    if (["key_vault"'
    ', "microsoft.keyvault/vaults"].includes(value)) return "key_vault";\n    if (["identity", "managed_id'
    'entity", "microsoft.managedidentity/userassignedidentities"].includes(value)) return "managed_identi'
    'ty";\n    if (["storage", "storage_account", "microsoft.storage/storageaccounts"].includes(value)) re'
    'turn "storage_account";\n    return null;\n  };\n  const product = (iconKey, label, description) => {\n '
    '   const wrapper = node("div", undefined, "architecture-product");\n    if (AZURE_ICONS.has(iconKey))'
    ' {\n      const image = node("img"); image.src = AZURE_ICONS.get(iconKey); image.alt = ""; image.clas'
    'sName = "architecture-product-icon";\n      wrapper.append(image);\n    }\n    const reading = add(node'
    '("div"), node("strong", label));\n    if (description) reading.append(node("span", description, "cell'
    '-note"));\n    return add(wrapper, reading);\n  };\n  const renderReference = () => {\n    const referen'
    'ce = byId("architecture-reference");\n    if (reference.childElementCount) return;\n    add(reference,'
    ' add(node("div", undefined, "architecture-note"), node("h3", "Reference proposal - NOT deployed"),\n '
    '     node("p", "A conditional pattern based on the Azure Architecture Center and the five Well-Archi'
    'tected pillars. It is not a map of the customer\'s estate, a completed project or a quote."),\n      n'
    'ode("p", "Validate the SLA, RTO/RPO, isolation, regions, traffic, dependencies and budget with the o'
    'wners before you choose components.", "qualification")));\n    const diagram = node("figure", undefin'
    'ed, "reference-diagram"); diagram.setAttribute("aria-label", "Entry alternatives and separation in a'
    ' reference AKS architecture, not deployed");\n    const entries = node("div", undefined, "reference-e'
    'ntry");\n    add(entries, add(node("div"), product("application_gateway", "Azure Application Gateway '
    '+ WAF", "HTTP(S) option: application protection based on the threat model.")),\n      add(node("div")'
    ', product("load_balancer", "Public Azure Load Balancer / ELB", "L4 alternative when public exposure '
    'is needed; it does not provide a WAF.")));\n    const network = node("div", undefined, "reference-net'
    'work");\n    add(network, node("h3", "Azure Virtual Network / proposed separate subnets"));\n    const'
    ' ingress = add(node("div", undefined, "reference-lane"), node("h4", "Ingress subnet"),\n      product'
    '("load_balancer", "Private Azure Load Balancer / ILB", "Private frontend for the internal entry patt'
    'ern, when it applies."),\n      node("p", "The Kubernetes ingress controller or gateway must be chose'
    'n and operated explicitly; its presence is not inferred from a Service.", "qualification"));\n    con'
    'st cluster = add(node("div", undefined, "reference-lane"), node("h4", "AKS subnet"),\n      product("'
    'aks", "Azure Kubernetes Service (AKS)", "Separate System and User pools; zones and scale based on th'
    'e SLA and regional capacity."),\n      add(node("div", undefined, "reference-workloads"),\n        nod'
    'e("p", "System pool: platform components and the minimum supported capacity."),\n        node("p", "U'
    'ser pool: applications, namespaces per team, quotas and NetworkPolicy.")));\n    add(network, add(nod'
    'e("div", undefined, "reference-lanes"), ingress, cluster));\n    add(diagram, entries, node("p", "Ent'
    'ry alternatives; they are not two deployed paths. Review TLS, routes and exposure.", "reference-link'
    '"), network);\n    const platform = add(node("div", undefined, "reference-platform"),\n      product("'
    'container_registry", "Azure Container Registry", "Only if the supply chain and approved dependencies'
    ' require it."),\n      product("key_vault", "Azure Key Vault", "Identity-based access with minimum sc'
    'ope; this review reads no secrets."),\n      product("monitor", "Azure Monitor", "Defined telemetry a'
    'nd SLOs; enabling an extension does not prove delivery or health."));\n    add(diagram, platform, nod'
    'e("figcaption", "The subnets and links in this proposal are open design decisions. No icon shows tha'
    't the resource exists in the observed cluster."));\n    reference.append(diagram);\n    const decision'
    's = node("div", undefined, "reference-decisions");\n    add(decisions, node("h3", "Decisions and trad'
    'eoffs for the team to close"));\n    const rows = [\n      ["Reliability", "Separate System/User pools'
    ' and define availability, upgrades, backups and recovery.", "Zones and redundancy add resilience onl'
    'y with the right region, capacity, SLA and recovery tests."],\n      ["Security", "Choose public L4 e'
    'xposure or protected HTTP(S) entry; use identities and least privilege.", "An ILB is not a WAF. Name'
    'spaces are not a strong enough isolation boundary for every multitenant model."],\n      ["Cost", "Si'
    'ze with representative utilization, costs per scope and applicable prices/commitments.", "Gateways, '
    'redundancy, telemetry and endpoints have a cost. This diagram assigns no prices or savings percentag'
    'es."],\n      ["Operations", "Document IaC, owners, SLOs, upgrades and per-namespace policies.", "Mis'
    'sing IaC in this review does not prove drift or manual creation."],\n      ["Performance", "Validate '
    'requests/limits, autoscaling, routes and capacity with representative tests.", "A current sample doe'
    's not prove sustained capacity, application performance or room to reduce the SKU."]\n    ];\n    rend'
    'erTable(decisions.appendChild(node("div")), "reference-decisions", "Conditional proposal for human r'
    'eview",\n      [["Pillar", row => row[0]], ["Proposed decision", row => row[1]], ["Assumption / trade'
    'off", row => row[2]]], rows, renderReference);\n    decisions.querySelector("caption").textContent = '
    '"Five conditional reference decisions; they are not findings or evidence of observed resources.";\n  '
    '  decisions.querySelector(".table-footer").remove();\n    reference.append(decisions);\n    const link'
    's = node("p", undefined, "qualification");\n    add(links, permittedLink("https://learn.microsoft.com'
    '/en-us/azure/architecture/reference-architectures/containers/aks/baseline-aks", "AKS baseline / Azur'
    'e Architecture Center"),\n      document.createTextNode(" · "), permittedLink("https://learn.microsof'
    't.com/en-us/azure/architecture/guide/multitenant/service/aks", "AKS multitenant / namespaces"),\n    '
    '  document.createTextNode(" · "), permittedLink("https://learn.microsoft.com/en-us/azure/well-archit'
    'ected/service-guides/azure-kubernetes-service", "AKS guide / five pillars"));\n    add(reference, lin'
    'ks, node("p", "Official references checked on 13 Oct 2026. Microsoft Azure V24 icons are used in dia'
    "grams and documentation with their original shapes and proportions. They are not this report's logo."
    '", "qualification"));\n  };\n  const graphKindLabel = kind => GRAPH_KINDS.get(kind) || kind;\n  const g'
    'raphNamespace = row => {\n    const evidence = isObject(row.evidence) ? row.evidence : {};\n    return'
    ' evidence.namespace || evidence.kubernetes_ref?.namespace || "";\n  };\n  const graphWorkloadMatches ='
    ' (row, selected) => {\n    const evidence = isObject(row.evidence) ? row.evidence : {};\n    const ref'
    'erence = evidence.kubernetes_ref || evidence;\n    const target = workloadIdentity(selected);\n    if '
    '(graphNamespace(row) !== target.namespace) return false;\n    if (reference.uid && target.uid) return'
    ' reference.uid === target.uid;\n    return reference.name === target.name && reference.kind === targe'
    't.kind;\n  };\n  const renderArchitecture = scope => {\n    const graph = model.architecture;\n    for ('
    'const id of ["architecture-observed-note", "architecture-map", "architecture-properties", "architect'
    'ure-tree", "architecture-nodes", "architecture-edges", "architecture-unknowns"]) byId(id).replaceChi'
    'ldren();\n    const kindSelect = byId("architecture-kind"), select = byId("architecture-node");\n    c'
    'onst note = byId("architecture-observed-note");\n    if (!graph) {\n      add(note, node("h3", "Observ'
    'ed architecture / Not evaluated"),\n        node("p", "This snapshot includes no graph of confirmed r'
    'elationships. The inventory is still available, but no connections, ingress, ELB/ILB or dependencies'
    ' are invented."));\n      byId("architecture-map").append(empty("Not evaluated: no nodes and links wi'
    'th their join fields were supplied."));\n      kindSelect.disabled = true; select.disabled = true;\n  '
    '    kindSelect.replaceChildren(node("option", "All types")); kindSelect.firstChild.value = "";\n     '
    ' select.replaceChildren(node("option", "Not evaluated"));\n      byId("architecture-tree").append(nod'
    'e("h3", "Resources / Not evaluated"));\n      byId("architecture-unknowns").append(empty("See this sn'
    'apshot\'s source receipts; an error does not prove that there are no relationships."));\n      return;'
    '\n    }\n    kindSelect.disabled = false; select.disabled = false;\n    const nodeMap = new Map(graph.n'
    'odes.map(row => [row.id, row]));\n    let scoped = graph.nodes;\n    if (state.filters.namespace || st'
    'ate.filters.workload) {\n      const direct = new Set(graph.nodes.filter(row => state.filters.workloa'
    'd ? graphWorkloadMatches(row, workloadMap.get(state.filters.workload)) :\n        graphNamespace(row)'
    ' === state.filters.namespace).map(row => row.id));\n      const context = new Set(direct);\n      for '
    '(const edge of graph.edges) if (direct.has(edge.from) || direct.has(edge.to)) { context.add(edge.fro'
    'm); context.add(edge.to); }\n      scoped = graph.nodes.filter(row => context.has(row.id));\n    }\n   '
    ' const kinds = [...new Set(scoped.map(row => row.kind))].sort((a, b) => graphKindLabel(a).localeComp'
    'are(graphKindLabel(b), "en"));\n    kindSelect.replaceChildren(node("option", "All types")); kindSele'
    'ct.firstChild.value = "";\n    fillOptions(kindSelect, kinds.map(kind => [kind, graphKindLabel(kind)]'
    '));\n    if (!kinds.includes(state.graphKind)) state.graphKind = "";\n    kindSelect.value = state.gra'
    'phKind;\n    const options = scoped.filter(row => !state.graphKind || row.kind === state.graphKind);\n'
    '    if (!options.some(row => row.id === state.graphNode)) state.graphNode = options.find(row => row.'
    'resource_id === model.cluster.id && graphIconKey(row.kind) === "aks")?.id || options[0]?.id || "";\n '
    '   select.replaceChildren();\n    for (const row of options) { const option = node("option", `${graph'
    'KindLabel(row.kind)} / ${row.label}`); option.value = row.id; select.append(option); }\n    if (!opti'
    'ons.length) { const option = node("option", "0 matching resources / does not mean absence"); option.'
    'value = ""; select.append(option); }\n    select.value = state.graphNode;\n    add(note, node("h3", "O'
    'bserved architecture"),\n      node("p", `${plural(graph.nodes.length, "node", "nodes")} and ${plural'
    '(graph.edges.length, "relationship", "relationships")} supplied; ${plural(graph.unknowns.length, "li'
    'mit", "limits")} not evaluated. Reference: ${utc(model.reference_utc)}.`),\n      node("p", "Arrows s'
    'how confirmed configuration references or joins, not verified traffic, mounts, effective authorizati'
    'on or health. ELB is the public Azure Load Balancer; ILB is its private frontend, never an AWS produ'
    'ct.", "qualification"),\n      node("p", state.filters.namespace || state.filters.workload ? "Showing'
    ' the objects in the Kubernetes selection and their confirmed neighbors; area, status and severity fi'
    'lters do not reinterpret the topology." :\n        "Topology of the whole cluster. Area, status and s'
    'everity filters do not reinterpret these relationships.", "qualification"));\n    const chosen = node'
    'Map.get(state.graphNode);\n    const tree = byId("architecture-tree"); tree.append(node("h3", `Resour'
    'ces / ${options.length}`));\n    const choose = id => { state.graphNode = id; renderArchitecture(curr'
    'entScope()); };\n    for (const kind of kinds) {\n      const rows = options.filter(row => row.kind =='
    '= kind);\n      if (!rows.length) continue;\n      const list = node("ul");\n      for (const row of ro'
    'ws) {\n        const button = node("button", row.label); button.type = "button"; button.setAttribute('
    '"aria-pressed", String(row.id === state.graphNode));\n        button.dataset.graphNode = row.id; butt'
    'on.addEventListener("click", () => choose(row.id)); list.append(add(node("li"), button));\n      }\n  '
    '    const group = node("details"); group.dataset.detailKey = `graph-kind:${kind}`; group.open = rows'
    '.some(row => row.id === state.graphNode);\n      add(group, node("summary", `${graphKindLabel(kind)} '
    '/ ${rows.length}`), list); tree.append(group);\n    }\n    const map = byId("architecture-map");\n    m'
    'ap.tabIndex = 0; map.setAttribute("role", "region");\n    if (!chosen) map.append(empty("0 objects wi'
    'th a matching identity. The shared ARM ID is never used to mix namespaces or workloads."));\n    else'
    ' {\n      const allowedIds = new Set(scoped.map(row => row.id));\n      const connections = graph.edge'
    's.filter(edge => allowedIds.has(edge.from) && allowedIds.has(edge.to) && (edge.from === chosen.id ||'
    ' edge.to === chosen.id));\n      const neighborIds = [...new Set(connections.map(edge => edge.from =='
    '= chosen.id ? edge.to : edge.from))].filter(id => id !== chosen.id);\n      const visibleIds = new Se'
    't([chosen.id, ...neighborIds.slice(0, 12)]);\n      const visible = graph.nodes.filter(row => visible'
    'Ids.has(row.id));\n      const left = visible.filter(row => row.id !== chosen.id && connections.some('
    'edge => edge.to === chosen.id && edge.from === row.id));\n      const right = visible.filter(row => r'
    'ow.id !== chosen.id && !left.includes(row));\n      const rows = Math.max(1, left.length, right.lengt'
    'h), height = Math.max(240, rows * 96 + 64);\n      const positions = new Map([[chosen.id, {x: left.le'
    'ngth ? 270 : 12, y: height / 2 - 36}]]);\n      for (const [index, row] of left.entries()) positions.'
    'set(row.id, {x: 12, y: 44 + index * 96});\n      for (const [index, row] of right.entries()) position'
    's.set(row.id, {x: 528, y: 44 + index * 96});\n      const drawing = svgNode("svg", {viewBox: `0 0 744'
    ' ${height}`, role: "group", "aria-labelledby": "architecture-svg-title architecture-svg-description"'
    '});\n      add(drawing, svgNode("title", {id: "architecture-svg-title"}, `Confirmed relationships of '
    '${chosen.label}`),\n        svgNode("desc", {id: "architecture-svg-description"}, `${plural(connectio'
    'ns.length, "direct relationship", "direct relationships")} supplied. All fields and records are in t'
    'he relationships table; an arrow does not prove traffic.`));\n      const marker = svgNode("marker", '
    '{id: "architecture-arrow", viewBox: "0 0 10 10", refX: 9, refY: 5, markerWidth: 6, markerHeight: 6, '
    'orient: "auto-start-reverse"});\n      marker.append(svgNode("path", {d: "M 0 0 L 10 5 L 0 10 z", fil'
    'l: "var(--accent)"})); drawing.append(add(svgNode("defs"), marker));\n      for (const edge of connec'
    'tions) {\n        const from = positions.get(edge.from), to = positions.get(edge.to);\n        if (!fr'
    'om || !to || edge.from === edge.to) continue;\n        const forward = from.x < to.x, start = {x: fro'
    'm.x + (forward ? 204 : 0), y: from.y + 36}, end = {x: to.x + (forward ? 0 : 204), y: to.y + 36};\n   '
    '     const line = svgNode("path", {d: `M${start.x},${start.y} C${(start.x + end.x) / 2},${start.y} $'
    '{(start.x + end.x) / 2},${end.y} ${end.x},${end.y}`,\n          class: "graph-line", "marker-end": "u'
    'rl(#architecture-arrow)"});\n        line.append(svgNode("title", {}, edge.relation)); drawing.append'
    '(line);\n      }\n      for (const row of visible) {\n        const position = positions.get(row.id);\n '
    '       const group = svgNode("g", {class: "graph-node", role: "button", tabindex: 0, "aria-label": `'
    'View identity and evidence for ${row.label}`, "data-graph-node": row.id});\n        add(group, svgNod'
    'e("title", {}, `${graphKindLabel(row.kind)} / ${row.label} / ${row.resource_id}`),\n          svgNode'
    '("rect", {x: position.x, y: position.y, width: 204, height: 72, rx: 4, class: `graph-box${row.id ==='
    ' chosen.id ? " selected" : ""}`}));\n        const icon = graphIconKey(row.kind);\n        if (icon &&'
    ' AZURE_ICONS.has(icon)) group.append(svgNode("image", {x: position.x + 12, y: position.y + 18, width'
    ': 36, height: 36, href: AZURE_ICONS.get(icon), preserveAspectRatio: "xMidYMid meet", "aria-hidden": '
    '"true"}));\n        const inset = icon && AZURE_ICONS.has(icon) ? 58 : 12, limit = inset === 58 ? 19 '
    ': 27;\n        const shortened = value => value.length <= limit ? value : `${value.slice(0, limit - 3'
    ')}...`;\n        const kindLabel = new Map([["load_balancer_frontend_public", "ELB / public"], ["load'
    '_balancer_frontend_private", "ILB / private"],\n          ["public_load_balancer", "ELB / Azure publi'
    'c"], ["private_load_balancer", "ILB / Azure private"]]).get(row.kind) || graphKindLabel(row.kind);\n '
    '       add(group, svgNode("text", {x: position.x + inset, y: position.y + 31, class: "graph-label"},'
    ' shortened(row.label)),\n          svgNode("text", {x: position.x + inset, y: position.y + 49, class:'
    ' "graph-kind"}, shortened(kindLabel)));\n        group.addEventListener("click", () => choose(row.id)'
    ');\n        group.addEventListener("keydown", event => { if (["Enter", " "].includes(event.key)) { ev'
    'ent.preventDefault(); choose(row.id); byId("architecture-node").focus({preventScroll: true}); } });\n'
    '        drawing.append(group);\n      }\n      add(map, drawing, node("figcaption", `Confirmed neighbo'
    'rhood: ${visible.length} of ${plural(neighborIds.length + 1, "node", "nodes")} visible; ${plural(con'
    'nections.length, "direct relationship", "direct relationships")}. On small screens, scroll the diagr'
    'am sideways. Shortened labels keep their full name, ID and evidence in the selector and the receipts'
    '. No link is inferred from a name or icon.`));\n      const properties = byId("architecture-propertie'
    's");\n      add(properties, node("h3", chosen.label), facts([["Type", graphKindLabel(chosen.kind)], ['
    '"Observed ID", armId(chosen.resource_id)], ["Graph key", chosen.id],\n        ["Cluster", chosen.clus'
    'ter_name], ["Source", `${chosen.source_id} / ${SOURCE_STATUS.get(sourceMap.get(chosen.source_id).sta'
    'tus)}`],\n        ["Observed at (UTC)", utc(chosen.observed_at)], ["Provenance", chosen.provenance]])'
    ', rawReceipt(chosen, `graph-node:${chosen.id}`));\n    }\n    const scopedIds = new Set(scoped.map(row'
    ' => row.id));\n    renderTable(byId("architecture-nodes"), "architecture-nodes", "Observed nodes",\n  '
    '    [["Resource / object", row => row.label], ["Type", row => graphKindLabel(row.kind)], ["Identity"'
    ', row => armId(row.resource_id)],\n        ["Source / date", row => `${row.source_id} / ${utc(row.obs'
    'erved_at)}`], ["Full evidence", row => rawReceipt(row, `graph-node-record:${row.id}`)]],\n      scope'
    'd, renderFiltered);\n    renderTable(byId("architecture-edges"), "architecture-edges", "Confirmed rel'
    'ationships",\n      [["From", row => nodeMap.get(row.from).label], ["Supplied relationship", row => r'
    'ow.relation], ["To", row => nodeMap.get(row.to).label],\n        ["Sources / date", row => `${row.sou'
    'rce_ids.join(", ")} / ${utc(row.observed_at)}`], ["Join fields", row => rawReceipt(row, `graph-edge:'
    '${row.id}`)]],\n      graph.edges.filter(row => scopedIds.has(row.from) && scopedIds.has(row.to)), re'
    'nderFiltered);\n    renderTable(byId("architecture-unknowns"), "architecture-unknowns", "Topology not'
    ' evaluated",\n      [["Type / code", row => `${graphKindLabel(row.kind)} / ${row.code}`], ["Not evalu'
    'ated / reason", row => row.message],\n        ["Sources / evidence", row => add(node("div"), node("sp'
    'an", row.source_ids.join(", ")), rawReceipt(row, `graph-unknown:${row.code}:${text(row.resource_id)}'
    '`))]],\n      graph.unknowns, renderFiltered);\n  };\n  const renderActions = scope => {\n    const plan'
    ' = byId("action-plan"); plan.replaceChildren();\n    for (const [key, [label, note]] of BUCKET) {\n   '
    '   const section = node("section", undefined, "action-bucket"); const content = node("div");\n      a'
    'dd(section, node("h3", label), node("p", note, "qualification"), content); plan.append(section);\n   '
    '   const rows = scope.actions.filter(action => action.planning_bucket === key);\n      renderTable(co'
    'ntent, `actions:${key}`, label, [\n        ["Action / check", action => add(node("div"), node("strong'
    '", action.title), node("span", `${action.action_id} · ${action.check_id}`, "cell-note"), resourceRef'
    '(action.resource_id), rawReceipt(action, `action:${action.action_id}`))],\n        ["Priority / effor'
    't", action => add(node("div"), severity(action.severity), node("span", `${EFFORT.get(action.effort)}'
    ' effort`, "cell-note"))],\n        ["Impact / recommendation", action => add(node("div"), node("p", c'
    'heckMap.get(action.check_id).business_impact), node("p", action.recommendation), permittedLink(actio'
    'n.learn_url, "Microsoft Learn"))],\n        ["Owner", action => action.owner === null || action.owner'
    ' === undefined || action.owner === "" ? "Unassigned" : text(action.owner)]\n      ], rows, renderFilt'
    'ered);\n    }\n  };\n  const scopeDescription = () => {\n    const f = state.filters;\n    return `Select'
    'ed scope: ${model.cluster.name}; area ${f.area ? AREA.get(f.area) : "all"}; namespace ${f.namespace '
    '|| "all"}; workload ${f.workload ? text(workloadMap.get(f.workload)?.name) : "all"}; level ${f.level'
    ' ? LEVEL.get(f.level) : "all"}; status ${f.status ? STATUS.get(f.status) : "all"}; severity ${f.seve'
    'rity ? SEVERITY.get(f.severity) : "all"}; search ${f.search || "no filter"}.`;\n  };\n  const renderSc'
    'ope = scope => {\n    const evaluated = scope.checks.filter(check => ["passed", "failed"].includes(ch'
    'eck.status)).length;\n    const unknown = scope.checks.filter(check => check.status === "not_evaluate'
    'd").length;\n    const na = scope.checks.filter(check => check.status === "not_applicable").length;\n '
    '   byId("filter-count").textContent = `${scope.checks.length} matching ${scope.checks.length === 1 ?'
    ' "check" : "checks"} of ${model.checks.length}; ${evaluated} evaluated, ${unknown} not evaluated and'
    ' ${na} not applicable. The indexes keep the full scope.`;\n    byId("print-scope").textContent = `${s'
    'copeDescription()} All matching records are printed, with no on-screen page limit. The summary index'
    'es keep the full scope.`;\n    const path = byId("scope-path"); path.replaceChildren();\n    const res'
    'etPart = (label, clear) => {\n      const button = node("button", label); button.type = "button";\n   '
    '   button.addEventListener("click", () => { clear(); synchronizeFilters(); filtersChanged(false); })'
    '; return button;\n    };\n    path.append(resetPart(model.cluster.name, () => { state.filters.area = "'
    '"; state.filters.namespace = ""; state.filters.workload = ""; }));\n    if (state.filters.area) add(p'
    'ath, node("span", "/"), resetPart(AREA.get(state.filters.area), () => { state.filters.namespace = ""'
    '; state.filters.workload = ""; }));\n    if (state.filters.namespace) add(path, node("span", "/"), re'
    'setPart(state.filters.namespace, () => { state.filters.workload = ""; }));\n    if (state.filters.wor'
    'kload) add(path, node("span", "/"), node("span", workloadMap.get(state.filters.workload)?.name, "sco'
    'pe-part"));\n  };\n  const renderFiltered = () => {\n    const opened = new Map([...document.querySelec'
    'torAll("details")].map(item => [item.dataset.detailKey, item.open]));\n    const scope = currentScope'
    '(); renderScope(scope); renderInventory(scope); renderArchitecture(scope); renderFindings(scope); re'
    'nderFinops(scope); renderActions(scope);\n    for (const item of document.querySelectorAll("details")'
    ') item.open = state.print || (opened.has(item.dataset.detailKey) ? opened.get(item.dataset.detailKey'
    ') : item.open);\n  };\n  const synchronizeFilters = () => {\n    for (const key of ["search", "area", "'
    'namespace", "level", "status", "severity"]) byId(`filter-${key}`).value = state.filters[key];\n    po'
    'pulateWorkloads();\n  };\n  const filtersChanged = (read = true) => {\n    if (read) for (const key of '
    '["search", "area", "namespace", "workload", "level", "status", "severity"]) state.filters[key] = byI'
    'd(`filter-${key}`).value;\n    state.pages.clear(); renderFiltered();\n  };\n  byId("filters-form").add'
    'EventListener("submit", event => event.preventDefault());\n  byId("filter-search").addEventListener("'
    'input", () => filtersChanged());\n  for (const key of ["area", "namespace", "workload", "level", "sta'
    'tus", "severity"]) byId(`filter-${key}`).addEventListener("change", () => {\n    if (key === "namespa'
    'ce") { state.filters.namespace = byId("filter-namespace").value; state.filters.workload = ""; popula'
    'teWorkloads(); }\n    filtersChanged();\n  });\n  byId("reset-filters").addEventListener("click", () =>'
    ' {\n    for (const key of Object.keys(state.filters)) state.filters[key] = "";\n    synchronizeFilters'
    '(); filtersChanged(false);\n  });\n  const renderMethod = () => {\n    const opened = new Map([...docum'
    'ent.querySelectorAll("#methodology details")].map(item => [item.dataset.detailKey, item.open]));\n   '
    ' byId("method-scope").replaceChildren();\n    add(byId("method-scope"), facts([["Read-only", "Declare'
    'd by the engine"], ["Index type", model.methodology.score_kind]]),\n      detail("Declared assessment'
    ' scope", "method-scope", node("pre", jsonText(model.methodology.scope ?? null), "json")));\n    rende'
    'rTable(byId("sources-table"), "sources", "Sources for the full snapshot", [\n      ["Source / receipt'
    '", source => add(node("div"), node("strong", source.id), rawReceipt(source, `source:${source.id}`))]'
    ',\n      ["Status", source => SOURCE_STATUS.get(source.status)], ["UTC reference", source => utc(sour'
    'ce.time)],\n      ["Records / pages", source => `${text(source.records)} / ${text(source.pages)}`],\n '
    '     ["Limits / errors", source => {\n        const wrapper = node("div", source.note);\n        if (s'
    'ource.window) wrapper.append(node("span", windowText(source.window), "cell-note"));\n        const li'
    'st = node("ul", undefined, "source-errors");\n        for (const error of source.errors) list.append('
    'node("li", `${text(error.code)} / HTTP ${text(error.http_status)} / ${text(error.message)}`));\n     '
    '   wrapper.append(list); return wrapper;\n      }]\n    ], model.sources, () => { renderMethod(); if ('
    'state.print) for (const item of document.querySelectorAll("details")) item.open = true; });\n    cons'
    't sourceData = byId("source-data-receipts"); sourceData.replaceChildren();\n    if (model.source_data'
    ' === undefined || model.source_data === null) sourceData.append(empty("Not evaluated: the model incl'
    'udes no additional observations."));\n    else sourceData.append(node("pre", jsonText(model.source_da'
    'ta), "json"));\n    const pins = byId("catalog-pins"); pins.replaceChildren();\n    const coverage = m'
    'odel.methodology.catalog_coverage;\n    pins.append(facts([["Catalog items", coverage?.total_items], '
    '["Mapped items", coverage?.mapped_items], ["Items not automated", coverage?.unmapped_items]]));\n    '
    'add(pins, node("p", "Catalog coverage is not assessment coverage. Architecture or intent questions t'
    'hat are not automated need human review.", "qualification"),\n      detail("Catalog snapshot and vers'
    'ions", "catalog-snapshot", node("pre", jsonText(model.methodology.catalogSnapshot ?? null), "json"))'
    ');\n    const references = model.methodology.source_pins;\n    if (!references || !references.length) '
    'pins.append(empty("Not evaluated: no pinned references were included."));\n    else for (const [index'
    ', pin] of references.entries()) pins.append(detail(`Pinned reference: ${text(pin?.name)}${pin?.versi'
    'on ? ` / ${pin.version}` : ""}`, `pin:${index}`, node("pre", jsonText(pin), "json")));\n    const que'
    'ries = byId("queries"); queries.replaceChildren();\n    byId("queries-title").textContent = `Included'
    ' queries and limits (${(model.methodology.queries || []).length})`;\n    if (!model.methodology.queri'
    'es || !model.methodology.queries.length) queries.append(empty("Not evaluated: the model includes no '
    'query signatures or read limits."));\n    else for (const [index, query] of model.methodology.queries'
    '.entries()) {\n      const section = node("div", undefined, "query");\n      add(section, node("h4", q'
    'uery.description || query.source_id), facts([["Source", query.source_id], ["Read limit", query.read_'
    'limit]]),\n        node("pre", query.command, "command"), rawReceipt(query, `query:${index}`)); queri'
    'es.append(section);\n    }\n    const limitations = byId("limitations"); limitations.replaceChildren()'
    ';\n    if (!model.methodology.limitations.length) limitations.append(empty("Not evaluated: no declare'
    'd limitations were included. This does not mean there are none."));\n    else { const list = node("ul'
    '", undefined, "finops-notes"); for (const item of model.methodology.limitations) list.append(node("l'
    'i", item)); limitations.append(list); }\n    for (const item of document.querySelectorAll("#methodolo'
    'gy details")) item.open = state.print || (opened.get(item.dataset.detailKey) || false);\n  };\n  const'
    ' csvValue = value => {\n    let content = value === null || value === undefined ? "" : (typeof value '
    '=== "object" ? JSON.stringify(value) : String(value));\n    if (/^[\\s\\u0000-\\u001f]*[=+\\-@]/u.test(co'
    'ntent) || /^[\\t\\r\\n]/u.test(content)) content = `\'${content}`;\n    return `"${content.replace(/"/g, '
    '\'""\')}"`;\n  };\n  const download = (filename, content, type) => {\n    const blob = new Blob([content]'
    ', {type}); const url = URL.createObjectURL(blob);\n    const link = node("a"); link.href = url; link.'
    'download = filename; link.hidden = true; document.body.append(link); link.click(); link.remove();\n  '
    '  setTimeout(() => URL.revokeObjectURL(url), 1000);\n  };\n  const exportCsv = (filename, columns, row'
    's) => {\n    const lines = [columns.map(([label]) => csvValue(label)).join(",")];\n    for (const row '
    'of rows) lines.push(columns.map(([, read]) => csvValue(read(row))).join(","));\n    download(filename'
    ', `\\ufeff${lines.join("\\r\\n")}\\r\\n`, "text/csv;charset=utf-8");\n  };\n  const checkColumns = [\n    ["'
    'check_id", row => row.check_id], ["checklist_id", row => row.checklist_id], ["title", row => row.tit'
    'le],\n    ["status", row => row.status], ["level", row => row.level], ["area", row => row.area], ["pi'
    'llar", row => row.pillar],\n    ["severity", row => row.severity], ["resource_id", row => row.resourc'
    'e_id], ["namespace", row => row.namespace],\n    ["workload_name", row => row.workload_name], ["evide'
    'nce", row => row.evidence], ["recommendation", row => row.recommendation],\n    ["learn_url", row => '
    'row.learn_url], ["effort", row => row.effort], ["reason", row => row.reason], ["record_json", row =>'
    ' row]\n  ];\n  byId("export-json").addEventListener("click", () => download("aks-review-full.json", em'
    'beddedJson, "application/json;charset=utf-8"));\n  byId("export-filtered-json").addEventListener("cli'
    'ck", () => {\n    const scope = currentScope();\n    const finops = Object.create(null);\n    for (cons'
    't [key, value] of Object.entries(model.finops)) finops[key] = key === "candidates" ? scope.candidate'
    's : (["cost_rows", "metrics"].includes(key) && value !== null ? value.filter(row => (!state.filters.'
    'area || state.filters.area === "finops") && scope.filterRecord(row, `finops.${key}`)) : value);\n    '
    'const exported = Object.create(null);\n    for (const [key, value] of Object.entries(model)) exported'
    '[key] = value;\n    exported.inventory = scope.inventory; exported.checks = scope.checks; exported.fi'
    'ndings = scope.findings; exported.finops = finops; exported.actions = scope.actions;\n    exported.fi'
    'lter_context = state.filters;\n    exported.scope_note = "Indexes, sources, source_data, methodology '
    "and topology keep the cluster's full snapshot; filtered collections contain every matching record, n"
    'ot just the visible page.";\n    if (documentModel.schema_version === "1.0") download("aks-review-sco'
    'pe.json", JSON.stringify(exported), "application/json;charset=utf-8");\n    else {\n      const wrappe'
    'r = Object.create(null);\n      for (const [key, value] of Object.entries(documentModel)) wrapper[key'
    '] = value;\n      wrapper.cluster_runs = documentModel.cluster_runs.map(run => run.cluster_name === s'
    'tate.activeCluster ? {...run, snapshot: exported} : run);\n      wrapper.filter_context = {cluster_na'
    'me: state.activeCluster, ...state.filters};\n      wrapper.scope_note = "Only the selected cluster\'s '
    'snapshot contains filtered collections. All other results, errors, snapshots and the aggregate keep '
    'their full original scope. Topology and receipts are not trimmed.";\n      download("aks-review-scope'
    '.json", JSON.stringify(wrapper), "application/json;charset=utf-8");\n    }\n  });\n  byId("export-findi'
    'ngs").addEventListener("click", () => exportCsv("aks-review-findings.csv", checkColumns, currentScop'
    'e().findings));\n  byId("export-checks").addEventListener("click", () => exportCsv("aks-review-checks'
    '.csv", checkColumns, currentScope().checks));\n  byId("export-inventory").addEventListener("click", ('
    ') => {\n    const rows = [];\n    for (const [collection, records] of Object.entries(currentScope().in'
    'ventory)) if (records !== null) for (const record of records) rows.push({collection, record});\n    e'
    'xportCsv("aks-review-inventory.csv", [["collection", row => row.collection], ["resource_id", row => '
    'row.record.resource_id], ["namespace", row => row.record.namespace],\n      ["name", row => row.recor'
    'd.name], ["source_id", row => row.record.source_id], ["observed_at", row => row.record.observed_at],'
    ' ["record_json", row => row.record]], rows);\n  });\n  byId("export-finops").addEventListener("click",'
    ' () => exportCsv("aks-review-finops.csv", [["id", row => row.id], ["title", row => row.title],\n    ['
    '"resource_id", row => row.resource_id], ["source_id", row => row.source_id], ["window", row => row.w'
    'indow], ["sample_count", row => row.sample_count],\n    ["estimated_savings", row => row.estimated_sa'
    'vings], ["recommendation", row => row.recommendation], ["record_json", row => row]], currentScope().'
    'candidates || []));\n  byId("export-actions").addEventListener("click", () => exportCsv("aks-review-p'
    'lan.csv", [["action_id", row => row.action_id], ["check_id", row => row.check_id],\n    ["resource_id'
    '", row => row.resource_id], ["planning_bucket", row => row.planning_bucket], ["severity", row => row'
    '.severity], ["effort", row => row.effort],\n    ["owner", row => row.owner], ["recommendation", row ='
    '> row.recommendation], ["record_json", row => row]], currentScope().actions));\n  const preparePrint '
    '= () => {\n    if (state.print || !model) return;\n    state.openDetails = new Map([...document.queryS'
    'electorAll("details")].map(item => [item.dataset.detailKey, item.open]));\n    renderReference(); sta'
    'te.print = true; renderClusterOverview(); renderCover(); renderFiltered(); renderMethod();\n    for ('
    'const item of document.querySelectorAll("details")) item.open = true;\n  };\n  const restorePrint = ()'
    ' => {\n    if (!state.print) return;\n    state.print = false; renderClusterOverview(); renderCover();'
    ' renderFiltered(); renderMethod();\n    for (const item of document.querySelectorAll("details")) item'
    '.open = state.openDetails.get(item.dataset.detailKey) || false;\n    state.openDetails.clear();\n  };\n'
    '  window.addEventListener("beforeprint", preparePrint); window.addEventListener("afterprint", restor'
    'ePrint);\n  byId("print-report").addEventListener("click", () => window.print());\n  byId("jump-sectio'
    'n").addEventListener("change", () => {\n    const target = byId(byId("jump-section").value);\n    targ'
    'et.scrollIntoView(); const heading = target.querySelector("h1, h2"); heading.tabIndex = -1; heading.'
    'focus({preventScroll: true});\n  });\n  const setArchitectureTab = (selected, focus = false) => {\n    '
    'if (selected === "reference") renderReference();\n    for (const key of ["observed", "reference"]) {\n'
    '      const active = key === selected, tab = byId(`architecture-${key}-tab`);\n      tab.setAttribute'
    '("aria-selected", String(active)); tab.tabIndex = active ? 0 : -1;\n      byId(`architecture-${key}`)'
    '.hidden = !active;\n      if (active && focus) tab.focus({preventScroll: true});\n    }\n  };\n  for (co'
    'nst key of ["observed", "reference"]) {\n    const tab = byId(`architecture-${key}-tab`);\n    tab.add'
    'EventListener("click", () => setArchitectureTab(key));\n    tab.addEventListener("keydown", event => '
    '{\n      if (["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) {\n        event.preventD'
    'efault(); setArchitectureTab(event.key === "Home" ? "observed" : event.key === "End" ? "reference" :'
    ' key === "observed" ? "reference" : "observed", true);\n      }\n    });\n  }\n  byId("architecture-kind'
    '").addEventListener("change", () => { state.graphKind = byId("architecture-kind").value; state.graph'
    'Node = ""; renderArchitecture(currentScope()); });\n  byId("architecture-node").addEventListener("cha'
    'nge", () => { state.graphNode = byId("architecture-node").value; renderArchitecture(currentScope());'
    ' });\n  byId("findings-order").addEventListener("change", () => { state.findingsOrder = byId("finding'
    's-order").value; state.pages.delete("findings"); renderFiltered(); });\n  const renderClusterOverview'
    ' = () => {\n    const multi = documentModel.schema_version !== "1.0", roster = documentModel.availabl'
    'e_clusters || [];\n    byId("cluster-overview").hidden = !multi && roster.length <= 1;\n    const sele'
    'ctor = byId("cluster-selector"); selector.replaceChildren();\n    for (const run of clusterRuns) { co'
    'nst option = node("option", `${run.cluster_name} / ${RUN_STATUS.get(run.status)}`); option.value = r'
    'un.cluster_name; selector.append(option); }\n    for (const row of roster) if (!clusterRuns.some(run '
    '=> run.cluster_name === row.cluster_name)) {\n      const option = node("option", `${row.cluster_name'
    '} / available for a new run, not included`);\n      option.value = row.cluster_name; option.disabled '
    '= true; selector.append(option);\n    }\n    selector.value = state.activeCluster;\n    const aggregate'
    ' = byId("cluster-aggregate"); aggregate.replaceChildren();\n    if (multi) {\n      const supplied = d'
    'ocumentModel.aggregate, score = supplied.scores.global;\n      add(aggregate, facts([["Combined local'
    ' index supplied", percentage(score.score)], ["Combined coverage supplied", supplied.scores.coverage.'
    'coverage_percent === null ? "Not evaluated" : `${supplied.scores.coverage.coverage_percent.toLocaleS'
    'tring("en-US", {maximumFractionDigits: 1})}%`],\n        ["Checks supplied", scoreCaption(score)], ["'
    'Findings / critical", `${supplied.findings_total} / ${supplied.critical_total}`],\n        ["Runs col'
    'lected / partial / failed", `${supplied.cluster_status_counts.ok ?? 0} / ${supplied.cluster_status_c'
    'ounts.partial ?? 0} / ${supplied.cluster_status_counts.error ?? 0}`],\n        ["Combined UTC referen'
    'ce", utc(documentModel.reference_utc)]]),\n        node("p", "The aggregate is the one received from '
    'the engine; a cluster with a primary read error has no evaluated configuration. Currencies, billing '
    'periods and node resource group scopes are never added together.", "qualification"),\n        detail('
    '"Full aggregate and per-cluster inventories", "multi-aggregate", node("pre", jsonText(supplied), "js'
    'on")));\n    } else aggregate.append(node("p", "The additional roster is fixed, authorized configurat'
    'ion, not evidence of presence or health. This file contains a single snapshot.", "qualification"));\n'
    '    renderTable(byId("cluster-runs-table"), "cluster-runs", "Results included per cluster",\n      [['
    '"Cluster", run => run.cluster_name], ["Collection status", run => RUN_STATUS.get(run.status)], ["UTC'
    ' reference", run => utc(run.reference_utc)],\n        ["Error / identity", run => rawReceipt({cluster'
    '_id: run.cluster_id, status: run.status, error: run.error}, `cluster-run:${run.cluster_name}`)]], cl'
    'usterRuns, renderClusterOverview);\n    byId("export-json").textContent = "Full JSON";\n    byId("expo'
    'rt-json").title = multi ? "Downloads the full original document with every cluster" : "Downloads the'
    ' full original snapshot";\n  };\n  const initializeCluster = name => {\n    const run = clusterRuns.fin'
    'd(item => item.cluster_name === name);\n    assert(run, "Cluster not included in the document.");\n   '
    ' state.activeCluster = name; model = run.snapshot; state.pages.clear(); state.graphNode = ""; state.'
    'graphKind = "";\n    for (const key of Object.keys(state.filters)) state.filters[key] = "";\n    for ('
    'const item of document.querySelectorAll("details")) item.open = false;\n    for (const id of ["cover"'
    ', "executive", "scope-filters", "inventory", "architecture", "findings", "finops", "actions", "metho'
    'dology"]) byId(id).hidden = !model;\n    byId("jump-section").disabled = !model; document.querySelect'
    'or(".toolbar-nav").hidden = !model;\n    document.querySelector(".report-footer").hidden = !model;\n  '
    '  byId("cluster-error").hidden = Boolean(model);\n    for (const id of ["export-filtered-json", "expo'
    'rt-inventory", "export-findings", "export-checks", "export-finops", "export-actions", "print-report"'
    ']) byId(id).disabled = !model;\n    if (!model) {\n      byId("cluster-error").replaceChildren(node("h'
    '2", `${run.cluster_name} / Not evaluated`),\n        node("p", "The primary read failed. There is no '
    'snapshot for this cluster: no indexes, costs, workloads or architecture are borrowed from another ru'
    'n."),\n        node("pre", JSON.stringify(run.error, null, 2), "json"));\n      return;\n    }\n    sour'
    'ceMap.clear(); checkMap.clear(); workloadMap.clear(); workloadResourceCounts.clear(); namespaces.cle'
    'ar();\n    for (const source of model.sources) sourceMap.set(source.id, source);\n    for (const check'
    ' of model.checks) checkMap.set(check.check_id, check);\n    for (const row of model.inventory.workloa'
    'ds || []) workloadResourceCounts.set(row.resource_id, (workloadResourceCounts.get(row.resource_id) |'
    '| 0) + 1);\n    for (const row of model.inventory.workloads || []) if (row.resource_id && row.name) w'
    'orkloadMap.set(workloadKey(row), workloadIdentity(row));\n    for (const check of model.checks) if (c'
    'heck.workload_name && ![...workloadMap.values()].some(row => matchesWorkload(check, row))) workloadM'
    'ap.set(workloadKey(check), workloadIdentity(check));\n    for (const row of model.inventory.namespace'
    's || []) if (row.name) namespaces.add(row.name);\n    for (const row of workloadMap.values()) if (row'
    '.namespace) namespaces.add(row.namespace);\n    for (const check of model.checks) if (check.namespace'
    ') namespaces.add(check.namespace);\n    byId("filter-namespace").replaceChildren(node("option", "All '
    'namespaces")); byId("filter-namespace").firstChild.value = "";\n    fillOptions(byId("filter-namespac'
    'e"), [...namespaces].sort((left, right) => left.localeCompare(right, "en")).map(value => [value, val'
    'ue]));\n    synchronizeFilters(); setArchitectureTab("observed");\n    renderCover(); renderExecutive('
    '); renderFiltered(); renderMethod();\n  };\n  byId("cluster-selector").addEventListener("change", () ='
    '> initializeCluster(byId("cluster-selector").value));\n  renderClusterOverview(); initializeCluster(s'
    'tate.activeCluster);\n  byId("opening-state").hidden = true; byId("report-shell").hidden = false;\n  b'
    'yId("export-json").disabled = false; byId("print-report").disabled = !model; document.body.dataset.s'
    'tatus = "ready";\n})();\n</script>\n</body>\n</html>\n'
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
    """Subscription of the cluster being collected: per-cluster config, the active collection, then the default."""
    return (config or {}).get("subscription_id") or ACTIVE_SUBSCRIPTION_ID or SUBSCRIPTION_ID


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


def validate_config(cluster_name):
    for key, value in (
        ("SUBSCRIPTION_ID", SUBSCRIPTION_ID), ("TENANT_ID", TENANT_ID),
        ("MANAGED_IDENTITY_CLIENT_ID", MANAGED_IDENTITY_CLIENT_ID),
    ):
        guid_setting(key, value)
    if not isinstance(APPROVED_CLUSTERS, dict) or not 1 <= len(APPROVED_CLUSTERS) <= MAX_APPROVED_CLUSTERS:
        raise EvidenceError("configuration_required", "Configure one to " + str(MAX_APPROVED_CLUSTERS) + " fixed approved clusters.", "configuration")
    name = cluster_name or next(iter(APPROVED_CLUSTERS))
    if name not in APPROVED_CLUSTERS:
        raise EvidenceError("invalid_parameter", "cluster_name must exactly match the fixed operator allowlist.", "parameters")
    defaults = globals().get("CLUSTER_DEFAULTS") or {}
    config = {**json.loads(json.dumps(obj(defaults, "configuration"))), **obj(APPROVED_CLUSTERS[name], "configuration")}
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
    validate_logo(CLIENT_LOGO_DATA_URI, CLIENT_LOGO_ALT)
    if not isinstance(CLIENT_NAME, str) or not 1 <= len(CLIENT_NAME) <= 120 or any(ord(c) < 32 for c in CLIENT_NAME):
        raise EvidenceError("configuration_required", "Client label must be bounded plain text.", "configuration")
    return {**config, "name": name, "aks_name": aks_name, "subscription_id": subscription,
            "id": "/subscriptions/" + subscription + "/resourceGroups/"
            + config["resource_group"] + "/providers/Microsoft.ContainerService/managedClusters/" + aks_name}


def roster_row(config):
    return {"cluster_id": config["id"], "cluster_name": config["name"],
            "resource_group": config["resource_group"], "environment": config["environment"]}


def selection_configs(cluster_name, cluster_names):
    first = validate_config(cluster_name)
    configured = [validate_config(name) for name in APPROVED_CLUSTERS]
    if len({config["id"].lower() for config in configured}) != len(configured):
        raise EvidenceError("configuration_required", "Two allowlist entries point to the same AKS resource ID.", "configuration")
    names = cluster_names.split(",") if cluster_names else [first["name"]]
    if len(set(names)) != len(names) or any(name not in APPROVED_CLUSTERS for name in names):
        raise EvidenceError("invalid_parameter", "Select distinct exact fixed allowlisted cluster names only.", "parameters")
    by_name = {config["name"]: config for config in configured}
    return [by_name[name] for name in names], configured


def list_clusters_page(configured, limit, offset):
    """Paged fixed roster (configuration, not observed health) that always fits the 3500-byte transport budget."""
    rows = [{"cluster_name": config["name"], "resource_group": config["resource_group"],
             "subscription_id": config["subscription_id"], "environment": config["environment"]}
            for config in configured]
    if len(configured) <= MAX_REPORT_CLUSTERS:
        for row, config in zip(rows, configured):
            row["cluster_id"] = config["id"]
    page = rows[offset:offset + limit]
    response = {"status": "ok", "operation": "list_clusters", "fresh_collection": False,
                "roster_basis": "fixed_operator_configuration_not_observed_inventory",
                "total": len(rows), "subscription_count": len({row["subscription_id"] for row in rows}),
                "offset": offset, "returned": 0, "next_offset": None,
                "report_batch_limit": MAX_REPORT_CLUSTERS, "available_clusters": page}
    while True:
        response["returned"] = len(response["available_clusters"])
        end = offset + response["returned"]
        response["next_offset"] = end if end < len(rows) else None
        if response_bytes(response) <= TRANSPORT_BYTES or len(response["available_clusters"]) <= 1:
            return ensure_response(response)
        response["available_clusters"] = response["available_clusters"][:-1]


def validate_parameters(operation, view, cluster_name, namespace, workload_name, area, level, severity, status, limit, offset, cluster_names=""):
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
    if not isinstance(cluster_names, str) or len(cluster_names) > 319 or (
        cluster_names and not re.fullmatch(r"[A-Za-z0-9_.()-]{1,63}(?:,[A-Za-z0-9_.()-]{1,63}){0,4}", cluster_names)
    ):
        raise EvidenceError("invalid_parameter", "cluster_names is an exact comma-separated allowlist selection of one to five names, without spaces.", "parameters")
    if cluster_name and cluster_names:
        raise EvidenceError("invalid_combination", "Use cluster_name or cluster_names, not both.", "parameters")
    filters = any((namespace, workload_name, area != "all", level != "all", severity != "all", status != "all"))
    if operation == "report" and (view != "summary" or filters or limit != 25 or offset != 0):
        raise EvidenceError("invalid_combination", "report cannot be narrowed by query filters or paging.", "parameters")
    if operation == "list_clusters" and (view != "summary" or filters):
        raise EvidenceError("invalid_combination", "list_clusters accepts only limit/offset roster paging, not query filters.", "parameters")
    if operation == "list_clusters" and (cluster_name or cluster_names):
        raise EvidenceError("invalid_combination", "list_clusters lists the complete fixed roster; do not select a cluster.", "parameters")
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
                area=area, level=level, severity=severity, status=status, limit=limit, offset=offset, cluster_names=cluster_names)


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
            raise EvidenceError("unsafe_method", "Only enumerated reads and two fixed read-only POST operations are permitted.", "scope")
        self.allowed.add((method, parsed.path))
        return url

    def request(self, method, url, source, body=None, allow_empty=False):
        parsed = urlsplit(url)
        if (
            parsed.scheme + "://" + parsed.netloc != self.origin or parsed.fragment or parsed.username or parsed.password
            or len(url) > 16384 or (method, parsed.path) not in self.allowed
        ):
            raise EvidenceError("unsafe_endpoint", "Request was not one of the scoped allowlisted reads.", source)
        if method == "POST" and not (
            parsed.path.lower().endswith("/listclusterusercredential")
            or parsed.path.lower().endswith("/providers/microsoft.costmanagement/query")
        ):
            raise EvidenceError("unsafe_method", "This POST is not an enumerated read-only operation.", source)
        payload = None if body is None else json.dumps(body, allow_nan=False).encode("utf-8")
        for attempt in range(3):
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
                if exc.code in (429, 500, 502, 503, 504) and attempt < 2:
                    retry = exc.headers.get("Retry-After", "") if exc.headers else ""
                    time.sleep(min(int(retry), 5) if re.fullmatch(r"[0-9]{1,4}", retry) else attempt + 1)
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
    global ACTIVE_SUBSCRIPTION_ID
    previous, ACTIVE_SUBSCRIPTION_ID = ACTIVE_SUBSCRIPTION_ID, scope_subscription(config)
    try:
        return _collect_live(config, reference, deadline)
    finally:
        ACTIVE_SUBSCRIPTION_ID = previous


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
    if not 1 <= len(runs) <= 5 or len({run["cluster_id"].lower() for run in runs}) != len(runs):
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
                "collection_seconds_bound": MAX_COLLECTION_SECONDS,
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

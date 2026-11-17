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
CATALOG = {}
HTML_TEMPLATE = ""
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

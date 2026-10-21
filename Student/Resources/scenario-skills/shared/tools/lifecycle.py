"""Date bounded lifecycle evidence. No built in version floor is a support policy."""

import json
import os
from datetime import date
from urllib.parse import urlparse


def load_evidence():
    """Load a snapshot or retain a safe diagnostic without exposing file content."""
    path = os.environ.get("SRE_LIFECYCLE_EVIDENCE")
    if not path:
        return None
    try:
        with open(path, encoding="utf-8") as stream:
            evidence = json.load(stream)
        if not isinstance(evidence, dict):
            return {"_evidence_error": {"code": "SnapshotInvalid", "reason": "Configured lifecycle snapshot must be a JSON object."}}
        return evidence
    except FileNotFoundError:
        code, reason = "SnapshotNotFound", "Configured lifecycle snapshot could not be found."
    except OSError:
        code, reason = "SnapshotUnreadable", "Configured lifecycle snapshot could not be read."
    except ValueError:
        code, reason = "SnapshotMalformed", "Configured lifecycle snapshot is not valid UTF-8 JSON."
    return {"_evidence_error": {"code": code, "reason": reason}}


def aks_support_plan(properties, sku):
    plan = (properties.get("supportPlan") or "").lower()
    if plan == "kubernetesofficial":
        return "standard"
    if plan == "akslongtermsupport" and (sku.get("tier") or "").lower() == "premium":
        return "lts"
    return None


def lifecycle_status(service, version, support_plan, evidence=None, today=None):
    """Return Supported/Unsupported/Unknown, requiring current exact match evidence.

    Snapshot v1 has checked_at and entries. Each entry has service, version,
    support_plan, support_end (inclusive), and source (official HTTPS URL).
    Evidence expires after 30 days. AKS versions use major.minor; runtime and
    image keys are exact identifiers, not prefix guesses. Entitlement/ESU must
    be represented by an explicit support_plan, never inferred from an image.
    """
    today = today or date.today()
    evidence = load_evidence() if evidence is None else evidence

    def unknown(code, reason):
        return {"status": "Unknown", "reason": reason, "source": None, "evidence_error": code}

    if evidence is None:
        return unknown("SnapshotUnconfigured", "Lifecycle evidence is not configured (SRE_LIFECYCLE_EVIDENCE).")
    if isinstance(evidence, dict) and "_evidence_error" in evidence:
        diagnostic = evidence["_evidence_error"]
        if isinstance(diagnostic, dict) and all(isinstance(diagnostic.get(key), str) and diagnostic[key] for key in ("code", "reason")):
            return unknown(diagnostic["code"], diagnostic["reason"])
        return unknown("SnapshotInvalid", "Lifecycle snapshot contains an invalid load diagnostic.")
    try:
        if not isinstance(evidence, dict):
            return unknown("SnapshotInvalid", "Lifecycle snapshot must be a JSON object with versioned metadata.")
        if evidence["schema_version"] != 1:
            return unknown("SnapshotSchemaUnsupported", "Lifecycle snapshot schema version is unsupported.")
        checked = date.fromisoformat(evidence["checked_at"])
        age = (today - checked).days
        if age < 0:
            return unknown("SnapshotFuture", "Lifecycle snapshot checked date is in the future.")
        if age > 30:
            return unknown("SnapshotStale", "Lifecycle snapshot is older than the 30 day evidence window.")
        if not version or not support_plan:
            return unknown("VersionOrPlanMissing", "Resource version or support plan is missing or unconfirmed.")
        if not isinstance(evidence["entries"], list):
            return unknown("SnapshotInvalid", "Lifecycle snapshot entries must be a JSON array.")
        for entry in evidence["entries"]:
            if (entry["service"], entry["version"], entry["support_plan"]) != (service, version, support_plan):
                continue
            if not isinstance(entry["source"], str):
                return unknown("SnapshotSourceInvalid", "Matching lifecycle entry requires an official HTTPS source URL string.")
            source = urlparse(entry["source"])
            if source.scheme != "https" or source.username or source.password or not source.hostname or not (
                source.hostname == "microsoft.com" or source.hostname.endswith(".microsoft.com")
            ):
                return unknown("SnapshotSourceInvalid", "Matching lifecycle entry requires an official HTTPS source without credentials.")
            end = date.fromisoformat(entry["support_end"])
            return {
                "status": "Supported" if today <= end else "Unsupported",
                "reason": f"Support ends {end.isoformat()} under {support_plan}; checked {checked.isoformat()}.",
                "source": entry["source"],
            }
    except (KeyError, TypeError, ValueError):
        return unknown("SnapshotInvalid", "Lifecycle snapshot has missing fields, invalid metadata or invalid dates.")
    return unknown("SnapshotNoMatch", "Lifecycle snapshot has no exact entry for this service, version and support plan.")

"""Pure inventory enrichment and customer export helpers. No Azure operations."""

import csv
import io
import sys
from pathlib import Path

for parent in Path(__file__).resolve().parents:
    shared_tools = parent / "shared" / "tools"
    if shared_tools.is_dir():
        sys.path.insert(0, str(shared_tools))
        break
from sharing import sanitized_copy

COUNT_FIELDS = ("DefenderTotal", "DefenderHigh", "DefenderMedium", "DefenderLow")


def enrich_inventory(inventory, counts_by_id, assessed_ids=()):
    """Only explicitly assessed, completely queried resources can receive counts."""
    assessed = {rid.lower() for rid in assessed_ids}
    counts_by_id = {rid.lower(): counts for rid, counts in counts_by_id.items()}
    rows = []
    for resource in inventory:
        row = dict(resource)
        rid = row["ResourceId"].lower()
        counts = counts_by_id.get(rid)
        known = rid in assessed and counts is not None and all(
            isinstance(counts.get(field), int) and not isinstance(counts.get(field), bool)
            and counts[field] >= 0 for field in COUNT_FIELDS
        )
        row.update({field: counts[field] if known else None for field in COUNT_FIELDS})
        row["DefenderAssessmentStatus"] = "Assessed" if known else "Not assessed"
        if row.get("ResourceType", "").lower() == "microsoft.sql/managedinstances" and row.get("VersionSource") in ("databaseFormat", "updatePolicy", "DatabaseFormat", "UpdatePolicy"):
            row["SqlVersion"] = "Unverified"
            row["VersionConfidence"] = "Low"
        rows.append(row)
    return rows


def export_csv(rows, include_identifiers=False):
    """Sanitize first, then neutralize spreadsheet formulas in every string cell."""
    safe = sanitized_copy({"rows": rows}, include_identifiers=include_identifiers)
    output = io.StringIO(newline="")
    fields = list(dict.fromkeys(key for row in safe["rows"] for key in row))
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    for row in safe["rows"]:
        writer.writerow({
            key: "'" + value if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")) else value
            for key, value in row.items()
        })
    return output.getvalue()

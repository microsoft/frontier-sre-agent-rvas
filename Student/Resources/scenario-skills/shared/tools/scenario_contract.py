"""Validate the evidence invariants of a dedicated scenario result, without cloud access."""

import argparse
import json
import re
from datetime import datetime
from pathlib import Path


def _timestamp(value: object) -> bool:
    if not isinstance(value, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|\+00:00)", value
    ):
        return False
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).tzinfo is not None
    except ValueError:
        return False


def validate_result(result: dict, contract: dict) -> None:
    if not isinstance(result, dict):
        raise ValueError("The scenario result must be an object.")
    missing = set(contract["required"]) - set(result)
    if missing:
        raise ValueError(f"Missing result fields: {sorted(missing)}")
    if result["scenario_id"] != contract["properties"]["scenario_id"]["const"]:
        raise ValueError("Result scenario_id does not match its contract.")
    status = result["assessment_status"]
    if status not in contract["properties"]["assessment_status"]["enum"]:
        raise ValueError("Invalid assessment_status.")
    if not _timestamp(result["assessed_at"]):
        raise ValueError("assessed_at must be an ISO timestamp in UTC.")
    scope = result["scope"]
    if not isinstance(scope, dict) or not isinstance(scope.get("subscription_ids"), list):
        raise ValueError("Scope requires a subscription_ids array.")
    for subscription in scope["subscription_ids"]:
        if not isinstance(subscription, str) or not re.fullmatch(
            r"[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}", subscription
        ):
            raise ValueError("Each approved subscription must be a GUID, not an unresolved placeholder.")
    coverage = result["coverage"]
    if not isinstance(coverage, dict):
        raise ValueError("Coverage must be an object.")
    expected, assessed = coverage.get("expected_checks"), coverage.get("assessed_checks")
    if type(expected) is not int or type(assessed) is not int or not 0 <= assessed <= expected:
        raise ValueError("Coverage counts must be nonnegative integers with assessed <= expected.")
    if type(coverage.get("truncated")) is not bool:
        raise ValueError("Coverage requires an explicit truncation flag.")
    if not isinstance(result["limitations"], list) or not all(isinstance(item, str) for item in result["limitations"]):
        raise ValueError("Limitations must be a list of reasons.")
    if status == "Complete" and (
        not scope["subscription_ids"] or expected == 0 or assessed != expected or coverage["truncated"]
    ):
        raise ValueError("Complete requires explicit scope and positive, fully assessed, untruncated coverage.")
    if status != "Complete" and not result["limitations"]:
        raise ValueError("An incomplete assessment requires limitations.")
    finding_contract = contract["properties"]["findings"]["items"]
    if not isinstance(result["findings"], list):
        raise ValueError("Findings must be an array.")
    for finding in result["findings"]:
        if not isinstance(finding, dict) or set(finding_contract["required"]) - set(finding):
            raise ValueError("A finding is missing required evidence fields.")
        if finding["status"] not in finding_contract["properties"]["status"]["enum"]:
            raise ValueError("Invalid finding status.")
        if finding["severity"] not in finding_contract["properties"]["severity"]["enum"]:
            raise ValueError("Invalid severity.")
        if not isinstance(finding["id"], str) or not finding["id"]:
            raise ValueError("A finding needs a stable nonempty identifier.")
        data = finding["scenario_data"]
        if not isinstance(data, dict) or set(finding_contract["properties"]["scenario_data"]["required"]) - set(data):
            raise ValueError("A finding is missing scenario specific fields.")
        if not isinstance(finding["evidence"], list):
            raise ValueError("Evidence must be an array.")
        for evidence in finding["evidence"]:
            if (not isinstance(evidence, dict) or not isinstance(evidence.get("source"), str)
                    or not evidence["source"].strip() or not _timestamp(evidence.get("collected_at"))):
                raise ValueError("Evidence requires a source and UTC collection timestamp.")
        if finding["status"] == "Not assessed" and status == "Complete":
            raise ValueError("An unassessed finding prevents Complete.")
        if finding["status"] in ("Observed", "Needs attention", "Not applicable") and not finding["evidence"]:
            raise ValueError("An assessed observation requires evidence.")
        if any(value is None for value in data.values()) and not result["limitations"]:
            raise ValueError("Unavailable values require an explanation in limitations.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("result", type=Path)
    parser.add_argument("--contract", required=True, type=Path)
    args = parser.parse_args()
    validate_result(json.loads(args.result.read_text(encoding="utf-8")),
                    json.loads(args.contract.read_text(encoding="utf-8")))
    print("Evidence contract validated locally. Azure execution was not tested.")

"""Create a sanitized report copy using the bundled, configurable sharing policy."""

import copy
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

POLICY_PATH = Path(__file__).resolve().parents[1] / "references" / "governance.json"


def sanitized_copy(data: dict, include_identifiers: bool = False, policy_path: Path = POLICY_PATH) -> dict:
    policy = json.loads(policy_path.read_text(encoding="utf-8"))["sharing"]
    secret_keys = {re.sub(r"[^a-z0-9]", "", key.casefold()) for key in policy["secret_keys"]}
    identifier_keys = {re.sub(r"[^a-z0-9]", "", key.casefold()) for key in policy["identifier_keys"]}
    secret_patterns = [re.compile(pattern) for pattern in policy["secret_patterns"]]
    identifier_patterns = [re.compile(pattern) for pattern in policy["identifier_patterns"]]
    aliases: dict[str, str] = {}
    redactions = 0

    def alias(value: str) -> str:
        if value not in aliases:
            aliases[value] = f"[identifier-{len(aliases) + 1:03d}]"
        return aliases[value]

    def register(value: object) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if re.sub(r"[^a-z0-9]", "", key.casefold()) in identifier_keys and isinstance(item, str) and item:
                    alias(item)
                register(item)
        elif isinstance(value, list):
            for item in value:
                register(item)

    if not include_identifiers:
        register(data)

    def clean(value: object, key: str = "") -> object:
        nonlocal redactions
        if re.sub(r"[^a-z0-9]", "", key.casefold()) in secret_keys and value not in (None, ""):
            redactions += 1
            return "[credential redacted]"
        if isinstance(value, dict):
            return {field: clean(item, field) for field, item in value.items()}
        if isinstance(value, list):
            return [clean(item) for item in value]
        if not isinstance(value, str):
            return value
        if not include_identifiers and value in aliases:
            redactions += 1
            return aliases[value]
        result = value
        for pattern in secret_patterns:
            result, count = pattern.subn("[credential redacted]", result)
            redactions += count
        if not include_identifiers:
            if result.startswith("https://") and urlsplit(result).hostname in policy["documentation_hosts"]:
                return result
            for original in sorted(aliases, key=len, reverse=True):
                if len(original) >= 4 and original in result:
                    result = result.replace(original, aliases[original])
                    redactions += 1
            for pattern in identifier_patterns:
                result, count = pattern.subn(lambda match: alias(match.group()), result)
                redactions += count
        return result

    result = clean(copy.deepcopy(data))
    result["sharing_review"] = {
        "status": "Draft: human review required",
        "identifiers_included": include_identifiers,
        "redactions": redactions,
    }
    return result

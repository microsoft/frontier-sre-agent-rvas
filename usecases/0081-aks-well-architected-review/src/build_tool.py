"""Build/check the single pasteable SRE tool; no runtime asset imports."""

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
BEGIN = "# BEGIN BUILD-TIME ASSETS"
END = "# END BUILD-TIME ASSETS"


def literal(value):
    return "(\n" + "".join("    " + repr(value[i:i + 100]) + "\n" for i in range(0, len(value), 100)) + ")"


def load_catalog():
    catalog = json.loads((ROOT / "rules_catalog.json").read_text(encoding="utf-8"))
    raw = (ROOT / "references" / "aks_checklist.en.json").read_bytes()
    pin = catalog["catalogSnapshot"]
    if len(raw) != pin["bytes"] or hashlib.sha256(raw).hexdigest() != pin["sha256"]:
        raise ValueError("Pinned checklist bytes/hash differ; review sources before rebuilding.")
    upstream = json.loads(raw)
    items = upstream["items"]
    ids = {item["id"] for item in items}
    if len(items) != pin["item_count"] or len(ids) != len(items):
        raise ValueError("Checklist item count/IDs do not match the verified pin.")
    rule_ids = [rule["rule_id"] for rule in catalog["rules"]]
    if len(rule_ids) != len(set(rule_ids)) or any(rule["checklist_id"] not in ids for rule in catalog["rules"]):
        raise ValueError("Duplicate local rule IDs or unknown checklist reference.")
    catalog["checklist_items"] = [
        {key: item.get(key) for key in ("id", "guid", "text", "category", "subcategory", "waf", "severity", "link")}
        for item in items
    ]
    catalog["license_text"] = (ROOT / "references" / "LICENSE.azure-review-checklists").read_text(encoding="utf-8")
    return catalog


def build(template_override=None):
    catalog = load_catalog()
    template = template_override if template_override is not None else (ROOT / "report_template.html").read_text(encoding="utf-8")
    if template.count("__REPORT_DATA_JSON__") != 1:
        raise ValueError("The approved report template must contain exactly one JSON placeholder.")
    source = (ROOT / "engine.py").read_text(encoding="utf-8")
    if source.count(BEGIN) != 1 or source.count(END) != 1:
        raise ValueError("Engine asset markers are missing or ambiguous.")
    before, rest = source.split(BEGIN)
    _, after = rest.split(END)
    assets = (
        BEGIN + "\nCATALOG = json.loads(" + literal(json.dumps(catalog, ensure_ascii=True)) + ")\n"
        + "HTML_TEMPLATE = " + literal(template) + "\n" + END
    )
    return before + assets + after


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Fail if the committed standalone file is stale.")
    args = parser.parse_args()
    output = ROOT.parent / "manifests" / "tools" / "generate-aks-waf-report.py"
    generated = build()
    if args.check:
        if not output.exists() or output.read_text(encoding="utf-8") != generated:
            raise SystemExit("Standalone tool is stale; run python build_tool.py.")
    else:
        output.write_text(generated, encoding="utf-8", newline="\n")
    print(("Verified" if args.check else "Built") + " standalone AKS tool (" + str(len(generated.encode("utf-8"))) + " bytes).")


if __name__ == "__main__":
    main()

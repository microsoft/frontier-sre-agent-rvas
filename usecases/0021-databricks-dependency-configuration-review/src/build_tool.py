"""Build/check the single pasteable Azure Databricks SRE tool; no runtime asset imports."""

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
BEGIN = "# BEGIN BUILD-TIME ASSETS"
END = "# END BUILD-TIME ASSETS"


def literal(value):
    return "(\n" + "".join("    " + repr(value[i:i + 100]) + "\n" for i in range(0, len(value), 100)) + ")"


def load_catalog():
    catalog = json.loads((ROOT / "rules_catalog.json").read_text(encoding="utf-8"))
    rules = catalog.get("rules", [])
    rule_ids = [rule["rule_id"] for rule in rules]
    if not rules or len(rule_ids) != len(set(rule_ids)):
        raise ValueError("Rules catalog must contain unique local rule IDs.")
    if len(rules) != catalog.get("catalogSnapshot", {}).get("item_count"):
        raise ValueError("Rules catalog item_count does not match rules length.")
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
    output = ROOT.parent / "manifests" / "tools" / "generate-databricks-dependency-report.py"
    generated = build()
    if args.check:
        if not output.exists() or output.read_text(encoding="utf-8") != generated:
            raise SystemExit("Standalone tool is stale; run python build_tool.py.")
    else:
        output.write_text(generated, encoding="utf-8", newline="\n")
    print(("Verified" if args.check else "Built") + " standalone Databricks tool (" + str(len(generated.encode("utf-8"))) + " bytes).")


if __name__ == "__main__":
    main()

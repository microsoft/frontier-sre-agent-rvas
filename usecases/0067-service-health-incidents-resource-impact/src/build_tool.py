"""Embed the offline UI in the standalone pasteable SRE Python tool."""

import argparse
from pathlib import Path


ROOT = Path(__file__).resolve().parent
BEGIN = "# BEGIN BUILD-TIME ASSETS"
END = "# END BUILD-TIME ASSETS"


def build():
    template = (ROOT / "report_template.html").read_text(encoding="utf-8")
    for token in ("__CLIENT_NAME__", "__COMPANY_LOGO__", "__FULL_JSON_BASE64__", "__UI_MODEL_JSON__"):
        if template.count(token) != 1:
            raise ValueError("The report template requires exactly one " + token + " placeholder.")
    engine = (ROOT / "engine.py").read_text(encoding="utf-8")
    if engine.count(BEGIN) != 1 or engine.count(END) != 1:
        raise ValueError("Build-time asset markers must be unique.")
    before, rest = engine.split(BEGIN)
    _, after = rest.split(END)
    literal = "(\n" + "".join("    " + repr(template[index:index + 100]) + "\n" for index in range(0, len(template), 100)) + ")"
    return before + BEGIN + "\nHTML_TEMPLATE = " + literal + "\n" + END + after


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    result = build()
    target = ROOT.parent / "manifests" / "tools" / "generate-service-health-report.py"
    if args.check:
        if not target.exists() or target.read_text(encoding="utf-8") != result:
            raise SystemExit("Standalone source is stale; run python build_tool.py.")
    else:
        target.write_text(result, encoding="utf-8", newline="\n")
    print(("Verified" if args.check else "Built") + " standalone Service Health tool (" + str(len(result.encode("utf-8"))) + " bytes).")


if __name__ == "__main__":
    main()

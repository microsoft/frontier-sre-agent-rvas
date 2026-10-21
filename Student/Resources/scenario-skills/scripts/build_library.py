"""Validate the scenario library and build portable customer skill packages."""

import argparse
import json
import posixpath
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[2]
CATEGORY_MAP = {
    "billing-cost": "billing-entra-tenant",
    "identity-access": "identity-access",
    "resource-organization": "resource-organization",
    "network": "network-topology",
    "security": "security",
    "management": "management",
    "governance": "governance",
    "platform-automation": "platform-devops",
}
LINK = re.compile(r"(?P<label>\[[^\]\n]+\])\((?P<target>[^)\s]+)\)")
SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def metadata(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    parts = text.split("---", 2)
    if len(parts) != 3 or parts[0].strip():
        raise ValueError(f"Missing skill frontmatter: {path}")
    name = re.search(r"^name:\s*(.+)$", parts[1], re.MULTILINE)
    description = re.search(r"^description:\s*(.+)$", parts[1], re.MULTILINE)
    tools = re.findall(r"^  - ([A-Za-z][A-Za-z0-9_]*)$", parts[1], re.MULTILINE)
    category = re.search(r"^  category:\s*([a-z0-9-]+)$", parts[1], re.MULTILINE)
    if not name or not description or not tools:
        raise ValueError(f"Skill needs an explicit name, description and tool list: {path}")
    description_text = description[1].strip()
    if description_text in {"|", ">", "|-", ">-"}:
        block = re.search(r"^description:\s*[|>]-?\s*\n((?:[ \t]+[^\n]*\n?)+)", parts[1], re.MULTILINE)
        if not block:
            raise ValueError(f"Empty description block: {path}")
        lines = [line.strip() for line in block[1].splitlines()]
        description_text = ("\n" if description_text.startswith("|") else " ").join(lines).strip()
    elif description_text.startswith('"'):
        description_text = json.loads(description_text)
    return {"name": name[1].strip(), "description": description_text, "tools": tools,
            "category": category[1] if category else None}


def bundle_files(skill: Path) -> dict[str, Path]:
    """Merge shared runtime dependencies with one skill, not the entire library."""
    files = {f"references/{p.name}": p for p in sorted((ROOT / "shared" / "references").iterdir())
             if p.is_file()}
    runtime = ["report_render.py", "sharing.py"]
    extensions = {s["slug"] for s in read_json(ROOT / "catalog" / "extension-scenarios.json")["scenarios"]}
    if skill.name in extensions:
        runtime += ["operational_analysis.py", "scenario_contract.py"]
    files.update({f"tools/{name}": ROOT / "shared" / "tools" / name for name in runtime})
    assessments = set(read_json(ROOT / "catalog" / "import.json")["assessmentImport"]["skills"])
    is_assessment = skill.name in assessments
    if is_assessment:
        for path in sorted((ROOT / "shared").rglob("*")):
            relative = path.relative_to(ROOT / "shared")
            needed = (
                relative.parts[0] == "references"
                or relative.as_posix() == "iac/deploy-skill.ps1"
                or relative.as_posix() in {
                    "tools/agent_identity.py", "tools/azure_http.py", "tools/lifecycle.py",
                    "tools/report_render.py", "tools/sharing.py",
                }
            )
            if needed and path.is_file():
                files["shared/" + path.relative_to(ROOT / "shared").as_posix()] = path
    for path in sorted(skill.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"Symlinks are not allowed in a customer bundle: {path}")
        if path.is_file() and path.suffix in {
            "", ".md", ".json", ".py", ".txt", ".html", ".yaml", ".yml",
            ".ps1", ".bicep", ".bicepparam", ".drawio",
        }:
            if path.name.startswith("test_") or "__pycache__" in path.parts:
                continue
            key = path.relative_to(skill).as_posix()
            if key in files and not is_assessment:
                raise ValueError(f"Skill overrides a shared dependency: {key}")
            files[key] = path
    return files


def bundle_text(relative: str, source: Path) -> str:
    text = source.read_text(encoding="utf-8")
    if source.suffix != ".md":
        return text

    def rewrite(match: re.Match) -> str:
        target = match["target"]
        if "://" in target or target.startswith(("#", "mailto:")):
            return match[0]
        destination = (source.parent / unquote(target.split("#", 1)[0])).resolve()
        shared = ROOT / "shared" / "references"
        if destination.is_relative_to(shared):
            logical = ("shared/references/" if relative.startswith("shared/") else "references/") + destination.relative_to(shared).as_posix()
            path = posixpath.relpath(logical, posixpath.dirname(relative) or ".")
            fragment = "#" + target.split("#", 1)[1] if "#" in target else ""
            return match["label"] + "(" + path + fragment + ")"
        if destination.is_relative_to(ROOT / "shared"):
            logical = "shared/" + destination.relative_to(ROOT / "shared").as_posix()
            return match["label"] + "(" + posixpath.relpath(logical, posixpath.dirname(relative) or ".") + ")"
        return match[0]

    return LINK.sub(rewrite, text)


def read_scenarios(repo: Path = REPO) -> dict:
    script = (
        "const fs=require('node:fs'),vm=require('node:vm');"
        "const source=fs.readFileSync(process.argv[1],'utf8');"
        "console.log(JSON.stringify(vm.runInNewContext(source+"
        "';({scenarios:SCENARIOS,categories:SCENARIO_CATEGORIES})')));"
    )
    result = subprocess.run(
        ["node", "-e", script, str(repo / "web" / "assets" / "js" / "scenarios-data.js")],
        capture_output=True, text=True, encoding="utf-8", check=True, timeout=15,
    )
    return json.loads(result.stdout)


def validate_mappings(records: list[dict], data: dict) -> None:
    skills = {row["slug"]: row for row in records}
    categories = {row["slug"] for row in data["categories"]}
    scenarios = data["scenarios"]
    if not isinstance(scenarios, list) or any(not isinstance(row, dict) for row in scenarios):
        raise ValueError("Scenario data must be a dense array of scenario objects.")
    ids = [row["id"] for row in scenarios]
    expected = (
        {s["slug"] for s in read_json(ROOT / "catalog" / "upstream-scenarios.json")["scenarios"]}
        | {s["slug"] for s in read_json(ROOT / "catalog" / "extension-scenarios.json")["scenarios"]}
        | {s["id"] for s in read_json(ROOT / "catalog" / "docx-use-cases.json")["scenarios"]}
    )
    if len(ids) != len(set(ids)) or set(ids) != expected:
        raise ValueError("Scenario IDs must match the source catalogs without duplicates.")
    used = set()
    for scenario in scenarios:
        mapped = scenario.get("skills")
        if not isinstance(mapped, list) or not mapped or len(set(mapped)) != len(mapped):
            raise ValueError(f"Scenario needs a nonempty, unique skills array: {scenario['id']}")
        if scenario["category"] not in categories:
            raise ValueError(f"Unknown scenario category: {scenario['id']}")
        for name in mapped:
            if name not in skills:
                raise ValueError(f"Unknown mapped skill {name} in {scenario['id']}")
            if skills[name]["category"] not in categories:
                raise ValueError(f"Unknown skill category: {name}")
            used.add(name)
    required = {r["slug"] for r in records if r["provenance"] != "onur-assessment"}
    if not required <= used:
        raise ValueError("Every dedicated workflow must be mapped to at least one scenario.")
    cases = read_json(ROOT / "catalog" / "docx-use-cases.json")
    if [case["number"] for case in cases["use_cases"]] != list(range(1, 12)):
        raise ValueError("DOCX coverage must account for all eleven numbered use cases.")
    for case in cases["use_cases"]:
        if not case["scenario_ids"] or not set(case["scenario_ids"]) <= set(ids):
            raise ValueError(f"Unresolved DOCX coverage: {case['title']}")


def validate() -> list[dict]:
    records = read_json(ROOT / "catalog" / "skills.json")
    upstream = read_json(ROOT / "catalog" / "upstream-scenarios.json")["scenarios"]
    extensions = read_json(ROOT / "catalog" / "extension-scenarios.json")["scenarios"]
    imported = read_json(ROOT / "catalog" / "import.json")["assessmentImport"]
    assessments = set(imported["skills"])
    document = read_json(ROOT / "catalog" / "docx-use-cases.json")
    new_workflows = {
        s["id"]: s for s in document["scenarios"]
        if s["id"] in s["skills"]
    }
    upstream_ids, extension_ids = ({r["slug"] for r in group} for group in (upstream, extensions))
    ids = [row["slug"] for row in records]
    if len(upstream_ids) != len(upstream) or len(upstream) != 77:
        raise ValueError("Expected exactly 77 unique upstream scenarios.")
    if len(extensions) != 6 or len(extension_ids) != 6 or upstream_ids & extension_ids:
        raise ValueError("Expected six distinct extension scenarios.")
    expected_ids = upstream_ids | extension_ids | assessments | set(new_workflows)
    if len(ids) != len(set(ids)) or set(ids) != expected_ids:
        raise ValueError("Skill catalog must match the scenario, DOCX and authorized assessment imports.")
    if len(assessments) != 22 or len(imported["skills"]) != 22 or not imported["permission"]:
        raise ValueError("Expected 22 distinct authorized assessment skills.")
    expected_paths = set()
    source_by_id = {s["slug"]: s for s in upstream + extensions}
    category_labels = {category["slug"]: category["label"] for category in read_scenarios()["categories"]}
    for record in records:
        name = record["slug"]
        if not SLUG.fullmatch(name):
            raise ValueError(f"Invalid skill ID: {name}")
        if name in source_by_id:
            category = CATEGORY_MAP[source_by_id[name]["category"]]
        elif name in new_workflows:
            category = new_workflows[name]["category"]
        else:
            category = record["category"]
            if record["provenance"] != "onur-assessment":
                raise ValueError(f"Assessment provenance is missing: {name}")
        if category not in category_labels or record["category_label"] != category_labels[category]:
            raise ValueError(f"Unknown or inconsistent skill category: {name}")
        expected = f"{category}/{name}"
        if record["category"] != category or record["path"] != expected:
            raise ValueError(f"Category/path mismatch for {name}")
        if name in extension_ids and category != "management":
            raise ValueError("All six extensions must be in Management.")
        folder = ROOT / expected
        expected_paths.add(folder / "SKILL.md")
        meta = metadata(folder / "SKILL.md")
        if (meta["name"] != name or " ".join(meta["description"].split()) != " ".join(record["description"].split())
                or meta["category"] != category):
            raise ValueError(f"Catalog/frontmatter mismatch for {name}")
        files = bundle_files(folder)
        if name not in assessments:
            contract = read_json(folder / "references" / "output-contract.json")
            if contract["properties"]["scenario_id"]["const"] != name:
                raise ValueError(f"Output contract does not match {name}")
            if "references/workflow.md" not in files:
                raise ValueError(f"Missing evidence workflow for {name}")
        for relative, path in files.items():
            if not path.is_file() or not path.resolve().is_relative_to(ROOT):
                raise ValueError(f"Missing or unsafe dependency: {path}")
            if path.suffix == ".json":
                read_json(path)
            if path.suffix == ".md":
                text = bundle_text(relative, path)
                prose = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
                for match in LINK.finditer(prose):
                    target = match["target"]
                    if "://" in target or target.startswith(("#", "mailto:")):
                        continue
                    destination = posixpath.normpath(posixpath.join(
                        posixpath.dirname(relative), unquote(target.split("#", 1)[0])))
                    if destination not in files:
                        raise ValueError(f"Broken bundle link in {name}/{relative}: {target}")
    actual_paths = set(ROOT.glob("*/*/SKILL.md"))
    if actual_paths != expected_paths:
        raise ValueError("Unexpected or missing skill directories.")
    validate_mappings(records, read_scenarios())
    return records


def browser_data(records: list[dict]) -> str:
    output = []
    for record in records:
        files = bundle_files(ROOT / record["path"])
        output.append({
            "id": record["slug"], "title": record["title"], "description": record["description"],
            "category": record["category"], "categoryLabel": record["category_label"],
            "instructions": bundle_text("SKILL.md", files["SKILL.md"]),
            "bundleUrl": f"assets/skill-bundles/{record['slug']}.zip",
        })
    return ("// Generated by Student/Resources/scenario-skills/scripts/build_library.py.\n"
            "// Edit the library sources, not this file. No live Azure validation is implied.\n"
            "const SCENARIO_SKILLS = " + json.dumps(output, ensure_ascii=True, indent=2) + ";\n")


def manifest(record: dict, files: dict[str, Path]) -> str:
    meta = metadata(files["SKILL.md"])
    paths = ["SKILL.md"] + sorted(key for key in files if key != "SKILL.md")
    lines = [
        "api_version: azuresre.ai/v1", "kind: Skill", "metadata:",
        f"  name: {record['slug']}", "spec:",
        "  description: " + json.dumps(meta["description"]), "  files:",
        *[f"    - ./{path}" for path in paths], "  tools:",
        *[f"    - {tool}" for tool in meta["tools"]],
    ]
    return "\n".join(lines) + "\n"


def write_zip(record: dict, destination: Path) -> None:
    files = bundle_files(ROOT / record["path"])
    prefix = f"skills/{record['slug']}/"
    contents = {prefix + name: bundle_text(name, path) for name, path in files.items()}
    contents[prefix + "skill.yaml"] = manifest(record, files)
    start = "its skill specific references" if record["provenance"] == "onur-assessment" else "its `references/workflow.md`"
    contents["README.md"] = (
        f"# {record['title']}\n\n"
        f"Category: {record['category_label']}.\n\n"
        f"Start with `{prefix}SKILL.md` and {start}. "
        "All required references and runtime tools are included. "
        "Run local commands from the extracted skill directory, not this archive root.\n\n"
        "`skill.yaml` is a manifest for this repository's configuration script, "
        "not a documented native portal import format. "
        "See the Scenario Explorer installation guide and the library README for installation.\n\n"
        "Confirm tenant, explicit approved resource scope, identity, tool authorization and "
        "observation window. Instructions do not enforce permissions. "
        "Changes, deployment, scheduling, uploads and external delivery need separate approval.\n\n"
        "Some assessment tools require host dependencies such as requests, azure-identity, pandas "
        "or an Excel engine; review the library setup guide. Keep nested shared/tools and "
        "shared/references intact when present. Optional agents and IaC are examples, not "
        "deployed or authorized by this download.\n\n"
        "Examples are synthetic. Packaging tests are not live Azure validation. "
        "Review the sources and limitations in the skill before customer use.\n\n"
        "Sources:\n"
        "- https://learn.microsoft.com/en-us/azure/sre-agent/skills\n"
        "- https://github.com/microsoft/frontier-sre-agent-rvas\n"
    )
    contents["LICENSE"] = (REPO / "LICENSE").read_text(encoding="utf-8")
    contents["THIRD-PARTY-NOTICES.md"] = (ROOT / "THIRD-PARTY-NOTICES.md").read_text(encoding="utf-8")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in sorted(contents.items()):
            info = zipfile.ZipInfo(name, date_time=(2026, 10, 21, 0, 0, 0))
            info.create_system = 3
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, content.encode("utf-8"))


def build(records: list[dict], site: Path) -> None:
    assets = site / "assets"
    script = assets / "js" / "scenario-skills-data.js"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(browser_data(records), encoding="utf-8")
    for record in records:
        write_zip(record, assets / "skill-bundles" / f"{record['slug']}.zip")
    if site.resolve() != (REPO / "web").resolve():
        published = site / "Student" / "Resources" / "scenario-skills"
        shutil.copytree(
            ROOT, published,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache", "test_*"),
        )
        readme = published / "README.md"
        readme.write_text(readme.read_text(encoding="utf-8").replace("../../../web/", "../../../"),
                          encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", type=Path, default=REPO / "web",
                        help="Site directory receiving generated JavaScript and ZIP downloads.")
    parser.add_argument("--check", action="store_true",
                        help="Validate sources and check committed browser data without writing.")
    args = parser.parse_args()
    try:
        records = validate()
        if args.check:
            actual = REPO / "web" / "assets" / "js" / "scenario-skills-data.js"
            if not actual.is_file() or actual.read_text(encoding="utf-8") != browser_data(records):
                raise ValueError("Browser skill data is stale. Run build_library.py to regenerate.")
        else:
            build(records, args.site)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"Validated {len(records)} skills and {len(read_scenarios()['scenarios'])} scenario mappings, including 22 authorized assessment imports.")
    if not args.check:
        print(f"Built complete customer bundles in {args.site / 'assets' / 'skill-bundles'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

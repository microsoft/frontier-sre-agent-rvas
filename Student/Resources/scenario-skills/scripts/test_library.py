import json
import re
import subprocess
import sys
import zipfile
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path

import pytest

from build_library import (
    REPO, ROOT, browser_data, build, bundle_files, metadata, read_json, read_scenarios,
    validate, validate_mappings, write_zip,
)

RECORDS = read_json(ROOT / "catalog" / "skills.json")
EXTENSIONS = read_json(ROOT / "catalog" / "extension-scenarios.json")["scenarios"]
ASSESSMENTS = set(read_json(ROOT / "catalog" / "import.json")["assessmentImport"]["skills"])
DOCUMENT = read_json(ROOT / "catalog" / "docx-use-cases.json")


class PageMarkup(HTMLParser):
    def __init__(self, filename):
        super().__init__()
        self.elements = []
        self.feed((REPO / "web" / filename).read_text(encoding="utf-8"))

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))

    def scripts(self):
        return [attrs["src"] for tag, attrs in self.elements if tag == "script" and "src" in attrs]


@pytest.mark.parametrize("filename", ["index.html", "scenarios.html", "jumpstart.html", "skills.html"])
def test_skills_navigation_is_available_from_each_site_tab(filename):
    page = PageMarkup(filename)
    links = [attrs for tag, attrs in page.elements if tag == "a" and attrs.get("href") == "skills.html"]
    assert links
    assert any(tag == "link" and attrs.get("href") == "assets/css/site-nav.css"
               for tag, attrs in page.elements)
    if filename == "skills.html":
        assert any(link.get("aria-current") == "page" for link in links)
    else:
        assert all(link.get("aria-current") != "page" for link in links)


def test_desktop_navigation_breakpoint_is_not_nested_in_compact_menu_rules():
    styles = (REPO / "web" / "assets" / "css" / "site-nav.css").read_text(encoding="utf-8")
    desktop = re.search(r"@media\s*\(min-width:\s*1200px\)", styles)
    assert desktop, "Desktop navigation needs its own breakpoint."
    preceding = styles[:desktop.start()]
    assert preceding.count("{") == preceding.count("}"), (
        "The desktop breakpoint must be at the top level, not inside the compact menu breakpoint."
    )


def test_skills_catalog_works_without_loading_the_scenario_catalog():
    scripts = PageMarkup("skills.html").scripts()
    assert "assets/js/scenarios-data.js" not in scripts
    assert scripts.index("assets/js/scenario-skills-data.js") < scripts.index("assets/js/skill-library.js")
    assert scripts.index("assets/js/skill-library.js") < scripts.index("assets/js/skills-explorer.js")
    for script in scripts:
        assert (REPO / "web" / script).is_file()


def test_scenario_details_use_the_same_skill_actions_as_the_skills_tab():
    scripts = PageMarkup("scenarios.html").scripts()
    assert scripts.index("assets/js/skill-library.js") < scripts.index("assets/js/scenario-explorer.js")
    for filename in ("scenario-explorer.js", "skills-explorer.js"):
        text = (REPO / "web" / "assets" / "js" / filename).read_text(encoding="utf-8")
        assert "SkillLibrary.createCard(" in text


def test_skill_guidance_is_moved_out_of_the_scenario_hero():
    scenario = (REPO / "web" / "scenarios.html").read_text(encoding="utf-8").split("</section>", 1)[0]
    skills = (REPO / "web" / "skills.html").read_text(encoding="utf-8")
    for phrase in ("Local skill and bundle tests", "How to use a downloaded skill",
                   "Downloads include skill instructions, supporting references and tools",
                   "is not a complete installation."):
        assert phrase not in scenario
        assert phrase in skills
    assert "alsanch/azure-sre-agent-scenarios" in scenario
    assert 'href="skills.html"' in (REPO / "web" / "skill-installation.html").read_text(encoding="utf-8")


def test_bundle_guidance_appears_once_and_is_not_repeated_on_skill_cards():
    skills = (REPO / "web" / "skills.html").read_text(encoding="utf-8")
    guidance = skills.split('<div class="skills-guidance">', 1)[1].split("</div>", 1)[0]
    assert skills.count("repository installation manifest and license notices") == 1
    assert "repository installation manifest and license notices" in guidance
    assert "skill files included" not in guidance
    script = r"""
const fs = require("node:fs"), vm = require("node:vm");
function element(tag) {
    return {tag, children: [], dataset: {}, textContent: "",
        appendChild(child) { this.children.push(child); },
        setAttribute() {}, addEventListener() {}};
}
const context = vm.createContext({window: {}, document: {createElement: element}});
vm.runInContext(fs.readFileSync(process.argv[1], "utf8"), context);
vm.runInContext(fs.readFileSync(process.argv[2], "utf8"), context);
const skills = vm.runInContext("SCENARIO_SKILLS", context);
function flatten(node) { return [node, ...node.children.flatMap(flatten)]; }
console.log(JSON.stringify(skills.map(skill => {
    const nodes = flatten(context.window.SkillLibrary.createCard(skill));
    return {
        id: skill.id,
        hasRepeatedNote: nodes.some(node => node.className === "scenario-skills-note"),
        hasFileCount: nodes.some(node => node.textContent.includes("skill files included")),
        actions: nodes.filter(node => ["Copy instructions", "Download complete bundle",
            "View instructions"].includes(node.textContent)).map(node => node.textContent)
    };
})));
"""
    assets = REPO / "web" / "assets" / "js"
    result = subprocess.run(
        ["node", "-e", script, str(assets / "skill-library.js"), str(assets / "scenario-skills-data.js")],
        capture_output=True, text=True, encoding="utf-8", check=True, timeout=15,
    )
    cards = json.loads(result.stdout)
    assert len(cards) == 110
    assert all(not card["hasRepeatedNote"] and not card["hasFileCount"] for card in cards)
    assert all(card["actions"] == [
        "Copy instructions", "Download complete bundle", "View instructions"
    ] for card in cards)


@pytest.mark.parametrize("filename", [
    "scenarios-data.js", "scenario-skills-data.js", "skill-library.js",
    "skills-explorer.js", "scenario-explorer.js",
])
def test_explorer_scripts_have_valid_syntax(filename):
    result = subprocess.run(
        ["node", "--check", str(REPO / "web" / "assets" / "js" / filename)],
        capture_output=True, text=True, timeout=15, check=False,
    )
    assert result.returncode == 0, result.stderr


def test_exact_import_and_authorized_assessment_membership():
    records = validate()
    imported = read_json(ROOT / "catalog" / "import.json")["assessmentImport"]
    assert len(records) == 110
    assert len(ASSESSMENTS) == 22
    assert ASSESSMENTS <= {p.parent.name for p in ROOT.glob("*/*/SKILL.md")}
    assert imported["sourceRepository"] == "https://github.com/onsenturk/SreAgentExtensions"
    assert imported["permission"]
    assert Counter(r["provenance"] for r in records) == {
        "upstream-scenario": 77, "original-extension": 6,
        "onur-assessment": 22, "document-use-case": 5,
    }
    assert Counter(r["category"] for r in records) == {
        "billing-entra-tenant": 13, "identity-access": 6, "resource-organization": 14,
        "network-topology": 14, "security": 4, "management": 45,
        "governance": 9, "platform-devops": 5,
    }


def test_browser_catalog_matches_sources():
    asset = REPO / "web" / "assets" / "js" / "scenario-skills-data.js"
    assert asset.read_text(encoding="utf-8") == browser_data(RECORDS)


def test_extensions_have_explicit_heuristic_time_savings():
    scenarios = read_scenarios()["scenarios"]
    added = [s for s in scenarios if s.get("provenance") == "original-extension"]
    assert {s["id"] for s in added} == {s["slug"] for s in EXTENSIONS}
    assert all(s["category"] == "management" for s in added)
    assert {s["id"]: s["timeSaved"] for s in added} == {
        "slo-error-budget-analysis": "Medium",
        "backup-restore-validation": "Medium",
        "release-regression-detection": "High",
        "aks-application-incident-triage": "High",
        "messaging-delivery-failure-triage": "High",
        "ai-inference-reliability-investigation": "High",
    }
    assert all(s["timeSavedEstimate"].startswith("Heuristic rating") for s in added)
    assert all(s["samplePrompt"] and s["skills"] for s in added)


def test_quick_wins_preserve_existing_picks_and_add_only_approved_scenarios():
    existing = {
        "cost-anomaly-detection", "underutilized-resources-detection",
        "orphaned-resources-cost-impact-analysis",
        "rbac-redundancy-over-privilege-assessment", "stale-rbac-assignments",
        "ai-model-inventory-retirement-lifecycle",
        "service-health-incidents-resource-impact", "planned-maintenance-awareness",
        "executive-operational-report-generation-pdf", "alert-fatigue-analysis",
        "azure-policy-assignment-assessment",
    }
    additions = {
        "backup-restore-validation", "release-regression-detection",
        "aks-application-incident-triage", "messaging-delivery-failure-triage",
        "workload-context-consultation", "defender-advisor-recommendation-triage",
    }
    scenarios = read_scenarios()["scenarios"]
    assert all(isinstance(s["topPick"], bool) for s in scenarios)
    assert {s["id"] for s in scenarios if s["topPick"]} == existing | additions
    page = (REPO / "web" / "scenarios.html").read_text(encoding="utf-8")
    count = re.search(r'data-scenario-stat="quickWins">(\d+)</span>', page)
    assert count and int(count[1]) == len(existing | additions)
    assert "required access and evidence are already available" in page
    assert "do not imply automatic remediation or guaranteed outcomes" in page


@pytest.fixture(scope="module")
def explorer_ui():
    script = r"""
const fs = require("node:fs"), vm = require("node:vm");
const data = fs.readFileSync(process.argv[1], "utf8");
const explorer = fs.readFileSync(process.argv[2], "utf8");
function run(extra) {
    const elements = new Map();
    function node(tag = "") {
        const classes = new Set();
        return {
            tag, children: [], dataset: {}, attributes: {}, events: {}, style: {setProperty() {}},
            textContent: "", hidden: false, isConnected: true,
            classList: {
                contains: c => classes.has(c), add: c => classes.add(c), remove: c => classes.delete(c),
                toggle(c, on) { if (on) classes.add(c); else classes.delete(c); }
            },
            set innerHTML(value) { this.html = value; this.children = []; },
            get innerHTML() {
                return this.textContent
                    ? this.textContent.replace(/&/g, "&amp;").replace(/</g, "&lt;")
                        .replace(/>/g, "&gt;")
                    : this.html || "";
            },
            appendChild(child) {
                if (child.tag === "fragment") this.children.push(...child.children);
                else this.children.push(child);
                return child;
            },
            setAttribute(key, value) { this.attributes[key] = value; },
            addEventListener(type, callback) { this.events[type] = callback; },
            querySelector() { return node(); },
            querySelectorAll() { return this.children; },
            focus() {}
        };
    }
    function get(id) {
        if (!elements.has(id)) elements.set(id, node());
        return elements.get(id);
    }
    const stats = ["total", "areas", "quickWins", "modes"].map(key => {
        const el = node();
        el.dataset.scenarioStat = key;
        return el;
    });
    const context = vm.createContext({
        console, window: {SkillLibrary: {}},
        SkillLibrary: {createCard: () => node()},
        setTimeout: fn => { fn(); return 1; }, clearTimeout() {},
        document: {
            getElementById: get, createElement: node, createDocumentFragment: () => node("fragment"),
            querySelectorAll: selector => selector === "[data-scenario-stat]" ? stats : [],
            addEventListener() {}, body: {style: {}}
        }
    });
    vm.runInContext(data + (extra ? `
        SCENARIO_CATEGORIES.push({slug:"test-area",label:"Test area",color:"#000"});
        SCENARIOS.push({...SCENARIOS[0], id:"test", category:"test-area",mode:"Test mode",topPick:true,
            timeSavedEstimate:'Heuristic rating for "prepared" evidence <review>.'});
    ` : ""), context);
    const originalOrder = vm.runInContext("SCENARIOS.map(s => s.id)", context);
    vm.runInContext("const SCENARIO_SKILLS = SCENARIOS.map(s => ({id:s.id}));", context);
    vm.runInContext(explorer, context);
    const cards = () => get("scenario-grid").children;
    const ids = () => cards().map(card => card.attributes["data-id"]);
    const result = {
        ids: ids(), stats: Object.fromEntries(stats.map(el => [el.dataset.scenarioStat, el.textContent])),
        counterTargets: Object.fromEntries(stats.map(el => [el.dataset.scenarioStat, el.attributes["data-count"]])),
        originalOrderUnchanged: JSON.stringify(originalOrder) ===
            JSON.stringify(vm.runInContext("SCENARIOS.map(s => s.id)", context))
    };
    if (extra) {
        result.estimatedBadge = cards().find(card => card.attributes["data-id"] === "test").innerHTML;
        return result;
    }
    const extensionIds = vm.runInContext(
        "SCENARIOS.filter(s => s.provenance === 'original-extension').map(s => s.id)", context);
    result.extensionCards = cards().filter(card => extensionIds.includes(card.attributes["data-id"])).map(card => ({
            id: card.attributes["data-id"], html: card.innerHTML
        }));
    result.details = result.extensionCards.map(card => {
        cards().find(el => el.attributes["data-id"] === card.id).events.click();
        return {id:card.id, badges:get("scenario-drawer-badges").innerHTML,
            note:get("scenario-drawer-savings-note").textContent,
            hidden:get("scenario-drawer-savings-note").hidden};
    });
    cards()[0].events.click();
    result.upstreamNoteHidden = get("scenario-drawer-savings-note").hidden;
    result.upstreamNote = get("scenario-drawer-savings-note").textContent;
    const mode = get("scenario-mode-filter");
    mode.value = "On-demand"; mode.events.change();
    result.onDemand = ids();
    mode.value = ""; mode.events.change();
    const quickWins = get("scenario-toppick-toggle");
    quickWins.events.click();
    result.quickWins = ids();
    result.quickWinsCount = get("scenario-results-count").textContent;
    result.quickWinsPressed = quickWins.attributes["aria-pressed"];
    result.quickWinStars = cards().filter(card => card.innerHTML.includes('title="Quick win"'))
        .map(card => card.attributes["data-id"]);
    mode.value = "On-demand"; mode.events.change();
    result.quickWinsOnDemand = ids();
    const chips = get("scenario-category-chips");
    const management = chips.children.find(chip => chip.dataset.category === "management");
    chips.events.click({target:{closest:() => management}});
    result.quickWinsManagementOnDemand = ids();
    const search = get("scenario-search-input");
    search.value = "release-regression-detection"; search.events.input();
    result.quickWinSearch = ids();
    search.value = "no-such-scenario-12345"; search.events.input();
    result.quickWinEmpty = {ids:ids(), hidden:get("scenario-empty").hidden,
        count:get("scenario-results-count").textContent};
    search.value = ""; search.events.input();
    mode.value = ""; mode.events.change();
    chips.events.click({target:{closest:() => ({dataset:{category:""}})}});
    quickWins.events.click();
    result.afterQuickWins = ids();
    result.quickWinsReleased = quickWins.attributes["aria-pressed"];
    chips.events.click({target:{closest:() => management}});
    result.management = ids();
    search.value = "SLO"; search.events.input();
    result.search = ids();
    search.value = "no-such-scenario-12345"; search.events.input();
    result.empty = {ids:ids(), hidden:get("scenario-empty").hidden,
        count:get("scenario-results-count").textContent};
    return result;
}
console.log(JSON.stringify({current:run(false), expanded:run(true)}));
"""
    assets = REPO / "web" / "assets" / "js"
    result = subprocess.run(
        ["node", "-e", script, str(assets / "scenarios-data.js"), str(assets / "scenario-explorer.js")],
        capture_output=True, text=True, encoding="utf-8", check=True, timeout=15,
    )
    return json.loads(result.stdout)


def test_scenario_tiles_follow_category_order_without_mutating_the_catalog(explorer_ui):
    data = read_scenarios()
    expected = [
        s["id"] for category in data["categories"]
        for s in data["scenarios"] if s["category"] == category["slug"]
    ]
    assert explorer_ui["current"]["ids"] == expected
    assert explorer_ui["current"]["originalOrderUnchanged"]


def test_scenario_summary_uses_catalog_values_and_updates_counter_targets(explorer_ui):
    page = PageMarkup("scenarios.html")
    stat_keys = {attrs["data-scenario-stat"] for _, attrs in page.elements if "data-scenario-stat" in attrs}
    assert stat_keys == {"total", "areas", "quickWins", "modes"}
    for key, expected in (
        ("current", {"total": "92", "areas": "8", "quickWins": "17", "modes": "4"}),
        ("expanded", {"total": "93", "areas": "9", "quickWins": "18", "modes": "5"}),
    ):
        assert explorer_ui[key]["stats"] == expected
        assert explorer_ui[key]["counterTargets"] == expected


def test_savings_cards_omit_estimated_label_but_details_explain_estimates(explorer_ui):
    current = explorer_ui["current"]
    estimates = current["extensionCards"]
    assert {card["id"] for card in estimates} == {s["slug"] for s in EXTENSIONS}
    assert all("(estimated)" not in card["html"] for card in estimates)
    assert all(re.search(r'>(?:High|Medium) savings</span>', card["html"]) for card in estimates)
    assert all("not Azure bill savings" in card["html"] for card in estimates)
    assert len(current["details"]) == 6
    for detail in current["details"]:
        assert "time savings (estimated)" in detail["badges"]
        assert "Heuristic rating" in detail["note"]
        assert "Not measured or guaranteed" in detail["note"]
        assert not detail["hidden"]
    assert current["upstreamNoteHidden"]
    assert current["upstreamNote"] == ""


def test_estimate_tooltips_encode_quotes_and_markup(explorer_ui):
    assert 'for &quot;prepared&quot; evidence &lt;review&gt;.' in explorer_ui["expanded"]["estimatedBadge"]


def test_ordered_tiles_preserve_combined_filters_and_empty_state(explorer_ui):
    scenarios = read_scenarios()["scenarios"]
    by_id = {s["id"]: s for s in scenarios}
    current = explorer_ui["current"]
    assert current["onDemand"] == [
        id for id in current["ids"] if by_id[id]["mode"] == "On-demand"
    ]
    assert current["quickWins"] == [
        id for id in current["ids"] if by_id[id]["topPick"]
    ]
    assert current["management"] == [
        id for id in current["ids"] if by_id[id]["category"] == "management"
    ]
    assert len(current["management"]) == 37
    assert "slo-error-budget-analysis" in current["search"]
    assert set(current["search"]) <= set(current["management"])
    assert current["empty"] == {"ids": [], "hidden": False, "count": "0 of 92 scenarios"}


def test_quick_wins_stars_and_combined_filters_match_the_selection(explorer_ui):
    scenarios = {s["id"]: s for s in read_scenarios()["scenarios"]}
    current = explorer_ui["current"]
    assert current["quickWinsCount"] == "17 of 92 scenarios"
    assert current["quickWinsPressed"] == "true"
    assert current["quickWinStars"] == current["quickWins"]
    on_demand = [id for id in current["quickWins"] if scenarios[id]["mode"] == "On-demand"]
    assert current["quickWinsOnDemand"] == on_demand
    assert current["quickWinsManagementOnDemand"] == [
        id for id in on_demand if scenarios[id]["category"] == "management"
    ]
    assert current["quickWinSearch"] == ["release-regression-detection"]
    assert current["quickWinEmpty"] == {"ids": [], "hidden": False, "count": "0 of 92 scenarios"}
    assert current["afterQuickWins"] == current["ids"]
    assert current["quickWinsReleased"] == "false"


def test_mapping_supports_multiple_skills_and_reuse():
    data = read_scenarios()
    first, second = data["scenarios"][:2]
    first["skills"].append(second["skills"][0])
    second["skills"].append(first["skills"][0])
    validate_mappings(RECORDS, data)


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "unknown", "empty", "category", "unmapped"])
def test_bad_mappings_fail_explicitly(mutation):
    data = read_scenarios()
    first = data["scenarios"][0]
    if mutation == "missing":
        data["scenarios"].pop()
    elif mutation == "duplicate":
        data["scenarios"][-1]["id"] = first["id"]
    elif mutation == "unknown":
        first["skills"].append("not-an-imported-skill")
    elif mutation == "empty":
        first["skills"] = []
    elif mutation == "category":
        first["category"] = "not-a-category"
    else:
        first["skills"] = data["scenarios"][1]["skills"][:]
    with pytest.raises(ValueError):
        validate_mappings(RECORDS, data)


@pytest.mark.parametrize("record", RECORDS, ids=lambda r: r["slug"])
def test_download_is_complete_scoped_and_manifest_paths_are_portable(tmp_path, record):
    name = record["slug"]
    destination = tmp_path / (name + ".zip")
    write_zip(record, destination)
    prefix = f"skills/{name}/"
    files = bundle_files(ROOT / record["path"])
    with zipfile.ZipFile(destination) as archive:
        names = set(archive.namelist())
        assert {"README.md", "LICENSE", "THIRD-PARTY-NOTICES.md"} <= names
        assert {prefix + key for key in files} <= names
        if name not in ASSESSMENTS:
            assert prefix + "references/workflow.md" in names
            assert prefix + "references/output-contract.json" in names
        assert prefix + "references/governance.json" in names
        assert not any("/test_" in key or "__pycache__" in key for key in names)
        assert not any(key.startswith("/") or ".." in Path(key).parts for key in names)
        assert all(key.startswith(prefix) or "/" not in key for key in names)
        manifest = archive.read(prefix + "skill.yaml").decode("utf-8")
        paths = re.findall(r"^    - \./(.+)$", manifest, re.MULTILINE)
        assert paths[0] == "SKILL.md"
        assert set(paths) == set(files)
        assert all(prefix + path in names for path in paths)
        assert f"  name: {name}\n" in manifest
        for tool in metadata(files["SKILL.md"])["tools"]:
            assert f"    - {tool}\n" in manifest
        if name not in ASSESSMENTS:
            assert b"../../../shared" not in archive.read(prefix + "references/workflow.md")
        else:
            assert prefix + "shared/tools/agent_identity.py" in names
            assert prefix + "shared/tools/azure_http.py" in names
            assert prefix + "shared/tools/lifecycle.py" in names
            assert prefix + "shared/references/governance.json" in names
            assert prefix + "shared/tools/operational_analysis.py" not in names
        if name in {s["slug"] for s in EXTENSIONS}:
            assert prefix + "tools/operational_analysis.py" in names
            assert prefix + "references/evidence-example.json" in names
        else:
            assert prefix + "tools/operational_analysis.py" not in names


@pytest.mark.parametrize("scenario", [s["slug"] for s in EXTENSIONS])
def test_customer_download_runs_without_the_source_workspace(tmp_path, scenario):
    record = next(r for r in RECORDS if r["slug"] == scenario)
    archive = tmp_path / "bundle.zip"
    write_zip(record, archive)
    with zipfile.ZipFile(archive) as package:
        package.extractall(tmp_path / "extracted")
    workdir = tmp_path / "extracted" / "skills" / scenario
    result = subprocess.run(
        [sys.executable, "tools/operational_analysis.py", "--scenario", scenario,
         "--input", "references/evidence-example.json", "--contract", "references/output-contract.json",
         "--output", "private.json", "--sharing-output", "sharing.json"],
        cwd=workdir, capture_output=True, text=True, timeout=15, check=False,
    )
    assert result.returncode == 0, result.stderr
    private = read_json(workdir / "private.json")
    assert private["scenario_id"] == scenario
    assert private["assessment_status"] == "Complete"
    assert private["coverage"]["assessed_checks"] > 0
    assert read_json(workdir / "sharing.json")["sharing_review"]["status"] == "Draft: human review required"


def test_bundles_are_reproducible(tmp_path):
    first, second = tmp_path / "first.zip", tmp_path / "second.zip"
    write_zip(RECORDS[0], first)
    write_zip(RECORDS[0], second)
    assert first.read_bytes() == second.read_bytes()


def test_site_publishes_complete_downloads_and_local_guidance(tmp_path):
    build(RECORDS, tmp_path)
    assert len(list((tmp_path / "assets" / "skill-bundles").glob("*.zip"))) == 110
    assert (tmp_path / "assets" / "js" / "scenario-skills-data.js").read_text(
        encoding="utf-8") == browser_data(RECORDS)
    readme = tmp_path / "Student" / "Resources" / "scenario-skills" / "README.md"
    assert readme.is_file()
    assert "../../../web/" not in readme.read_text(encoding="utf-8")
    assert "../../../assets/js/scenarios-data.js" in readme.read_text(encoding="utf-8")


def test_every_skill_has_explicit_tools_and_approval_boundaries():
    for row in RECORDS:
        folder = ROOT / row["path"]
        info = metadata(folder / "SKILL.md")
        assert set(info["tools"]) == {"RunAzCliReadCommands", "RunInTerminal", "SaveFileToBlob"}
        assert "## Approval boundary" in (folder / "SKILL.md").read_text(encoding="utf-8")
    policy = read_json(ROOT / "shared" / "references" / "governance.json")
    assert policy["default_action"] == "deny"
    assert policy["approved_subscription_ids"] == []
    assert {"write", "deploy", "send", "schedule", "upload"} <= set(policy["human_approval_required"])
    assert policy["audit"]["append_only"]


def test_scenario_sources_are_not_separated_in_the_customer_ui(explorer_ui):
    hero = (REPO / "web" / "scenarios.html").read_text(encoding="utf-8").split("</section>", 1)[0]
    assert "alsanch/azure-sre-agent-scenarios" in hero
    assert "original" not in hero.lower()
    assert "extension" not in hero.lower()
    script = (REPO / "web" / "assets" / "js" / "scenario-explorer.js").read_text(encoding="utf-8")
    assert "Additional scenario" not in script
    assert "provenance" not in script
    assert all("Additional scenario" not in detail["badges"] for detail in explorer_ui["current"]["details"])


def test_skills_page_credits_source_repositories_without_skill_counts():
    page = (REPO / "web" / "skills.html").read_text(encoding="utf-8")
    attribution = page.split('<p class="scenario-attribution">', 1)[1].split("</p>", 1)[0]
    assert "smragav/azure-sre-agent-skills" in attribution
    assert "onsenturk/SreAgentExtensions" in attribution
    assert not re.search(r"\b\d+\b", attribution)
    for filename in ("README.md", "Student/Resources/scenario-skills/README.md"):
        readme = (REPO / filename).read_text(encoding="utf-8")
        assert "smragav/azure-sre-agent-skills" in readme
        assert "onsenturk/SreAgentExtensions" in readme
        assert not re.search(r"\b22\b", readme)
    cards = (REPO / "web" / "assets" / "js" / "skill-library.js").read_text(encoding="utf-8")
    assert "provenance" not in cards


def test_all_document_use_cases_have_resolved_scenarios_and_skills():
    data = read_scenarios()
    scenarios = {scenario["id"]: scenario for scenario in data["scenarios"]}
    skills = {record["slug"] for record in RECORDS}
    assert len(scenarios) == 92
    assert re.fullmatch(r"[0-9a-f]{64}", DOCUMENT["document_sha256"])
    assert [case["number"] for case in DOCUMENT["use_cases"]] == list(range(1, 12))
    assert len(DOCUMENT["scenarios"]) == 9
    for case in DOCUMENT["use_cases"]:
        assert case["coverage"]
        for id in case["scenario_ids"]:
            assert scenarios[id]["skills"]
            assert set(scenarios[id]["skills"]) <= skills
    for expected in DOCUMENT["scenarios"]:
        actual = scenarios[expected["id"]]
        assert all(actual[key] == value for key, value in expected.items())
    assert len([r for r in RECORDS if r["provenance"] == "document-use-case"]) == 5


def test_assessment_skills_can_remain_standalone():
    data = read_scenarios()
    for scenario in data["scenarios"]:
        scenario["skills"] = [id for id in scenario["skills"] if id not in ASSESSMENTS]
        if not scenario["skills"]:
            scenario["skills"] = ["resource-health-status-summary"]
    validate_mappings(RECORDS, data)


@pytest.mark.parametrize("record", [r for r in RECORDS if r["provenance"] == "document-use-case"],
                         ids=lambda r: r["slug"])
def test_new_workflows_have_concrete_evidence_and_missing_data_cases(record):
    folder = ROOT / record["path"]
    workflow = (folder / "references" / "workflow.md").read_text(encoding="utf-8")
    assert "## Collection" in workflow
    assert "Healthy:" in workflow and "Finding:" in workflow and "Missing:" in workflow
    assert "```powershell" in workflow or "```http" in workflow
    assert record["sources"]
    assert all(source["url"].startswith("https://learn.microsoft.com/") for source in record["sources"])
    contract = read_json(folder / "references" / "output-contract.json")
    assert contract["properties"]["scenario_id"]["const"] == record["slug"]
    fields = contract["properties"]["findings"]["items"]["properties"]["scenario_data"]["required"]
    assert len(fields) >= 7
    assert all(f"`{field}`" in workflow for field in fields)


@pytest.mark.parametrize("record", [r for r in RECORDS if r["provenance"] == "onur-assessment"],
                         ids=lambda r: r["slug"])
def test_assessment_download_resolves_shared_runtime_in_isolation(tmp_path, record):
    package = tmp_path / "bundle.zip"
    write_zip(record, package)
    with zipfile.ZipFile(package) as archive:
        archive.extractall(tmp_path / "extracted")
    workdir = tmp_path / "extracted" / "skills" / record["slug"]
    script = r"""
from pathlib import Path
import importlib.util
import json
import runpy
import sys
root = Path.cwd()
def deny_network(event, args):
    if event in {"socket.connect", "socket.getaddrinfo"}:
        raise AssertionError("Archive import tests must never access the network.")
sys.addaudithook(deny_network)
programs = sorted(root.glob("*.py")) + sorted((root / "tools").glob("*.py"))
assert programs
for program in programs:
    runpy.run_path(str(program))
for name in ("agent_identity", "azure_http", "lifecycle", "report_render", "sharing"):
    spec = importlib.util.find_spec(name)
    assert spec and Path(spec.origin).is_relative_to(root), name
    module = __import__(name)
    assert Path(module.__file__).is_relative_to(root), name
import azure_http
assert azure_http.POLICY_PATH.is_file()
policy = json.loads(azure_http.POLICY_PATH.read_text())
assert policy["default_action"] == "deny"
assert policy["approved_subscription_ids"] == []
print("isolated runtime resolved")
"""
    result = subprocess.run(
        [sys.executable, "-I", "-c", script], cwd=workdir, capture_output=True,
        text=True, timeout=15, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "isolated runtime resolved"

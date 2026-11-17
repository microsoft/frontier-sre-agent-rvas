"""Case-04 offline surface checks; public fixtures are explicitly SIMULATED / LAB.

Run the browser checks with SRE_REPORT_BROWSER_TESTS=1 and an installed
Playwright/browser. SRE_REPORT_UI_ACTUAL_MODEL can opt into a caller-supplied
private snapshot; that check never writes screenshots or a public fixture.
These checks do not collect Azure data or deploy anything. The test embedding
helper is not an engine.
"""

import copy
import base64
import csv
import hashlib
import io
import json
import os
import re
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path


CASE = Path(__file__).resolve().parents[1]
TEMPLATE = CASE / "report_template.html"
TOKEN = "__REPORT_DATA_JSON__"
REFERENCE = "2026-10-13T12:00:00Z"
AREAS = ("best_practices", "security", "finops", "optimization")
PILLARS = ("reliability", "security", "cost", "operations", "performance")
BASE = (
    "/subscriptions/11111111-1111-4111-8111-111111111111/resourceGroups/rg-ui-synthetic"
    "/providers/Microsoft.ContainerService/managedClusters/aks-ui-synthetic"
)
LEARN = "https://learn.microsoft.com/en-us/azure/aks/operator-best-practices-cluster-security"
MAX_BYTES = 4_800_000


def score_fixture(checks):
    counts = {
        status: sum(check["status"] == status for check in checks)
        for status in ("passed", "failed", "not_evaluated", "not_applicable")
    }
    evaluated = counts["passed"] + counts["failed"]
    eligible = evaluated + counts["not_evaluated"]
    return {
        "score": round(100 * counts["passed"] / evaluated, 2) if evaluated else None,
        "passed": counts["passed"],
        "failed": counts["failed"],
        "evaluated": evaluated,
        "not_evaluated": counts["not_evaluated"],
        "not_applicable": counts["not_applicable"],
        "total": len(checks),
        "coverage_percent": round(100 * evaluated / eligible, 2) if eligible else None,
    }


def refresh_fixture(snapshot):
    """Keep synthetic fixture receipts coherent after a test mutation."""
    checks = snapshot["checks"]
    snapshot["findings"] = [
        copy.deepcopy(check) for check in checks if check["status"] == "failed"
    ]
    snapshot["scores"] = {
        "global": score_fixture(checks),
        "areas": {
            area: score_fixture([check for check in checks if check["area"] == area])
            for area in AREAS
        },
        "pillars": {
            pillar: score_fixture([check for check in checks if check["pillar"] == pillar])
            for pillar in PILLARS
        },
        "coverage": score_fixture(checks),
    }
    return snapshot


def fixture(workload_count=72):
    def identity(resource_id, source_id="kubernetes"):
        return {
            "resource_id": resource_id,
            "source_id": source_id,
            "observed_at": REFERENCE,
            "cluster_name": "aks-ui-synthetic",
        }

    def check(index, resource_id, status, level, namespace="", workload_name=""):
        source_id = "arm" if level != "workload" else "kubernetes"
        return {
            "check_id": f"UI-{index:03d}",
            "rule_id": f"synthetic-rule-{index}",
            "checklist_id": f"synthetic-checklist-{index}",
            "title": f"Comprobación simulada {index}: configuración observada",
            "status": status,
            "level": level,
            "area": AREAS[index % len(AREAS)],
            "pillar": PILLARS[index % len(PILLARS)],
            "severity": ("critical", "high", "medium", "low")[index % 4],
            "resource_id": resource_id,
            "namespace": namespace,
            "workload_name": workload_name,
            "resource_name": workload_name or "recurso-ui-synthetic",
            "checklist_guid": f"synthetic-guid-{index}",
            "severity_label": ("Crítica", "Alta", "Media", "Baja")[index % 4],
            "effort_label": ("L", "M", "H")[index % 3],
            "kubernetes_ref": {"namespace": namespace, "name": workload_name} if workload_name else None,
            "evidence": [] if status in ("not_evaluated", "not_applicable") else [
                {
                    "source_id": source_id,
                    "resource_id": resource_id,
                    "observed_at": REFERENCE,
                    "value": {
                        "synthetic_fixture": True,
                        "configured": status == "passed",
                        "observed_zero": 0,
                        "optional_value": None,
                    },
                }
            ],
            "business_impact": "Impacto simulado: requiere revisión del equipo responsable.",
            "recommendation": "Revisar la configuración aportada y validar el cambio antes de aplicarlo.",
            "learn_url": LEARN,
            "checklist_url": "https://github.com/Azure/Azure-Proactive-Resiliency-Library-v2",
            "kubernetes_url": "https://kubernetes.io/docs/concepts/",
            "effort": ("low", "medium", "high")[index % 3],
            "reason": "Fuente parcial de prueba: configuración no disponible."
            if status == "not_evaluated" else
            "No aplicable según el alcance de la prueba."
            if status == "not_applicable" else "",
        }

    workloads, checks = [], []
    for index in range(workload_count):
        namespace = "team-a" if index % 2 == 0 else "team-b"
        name = f"api-{index // 2:02d}"
        resource_id = f"{BASE}/namespaces/{namespace}/deployments/{name}"
        workloads.append({
            **identity(resource_id),
            "namespace": namespace,
            "name": name,
            "kind": "Deployment",
            "containers": [{"name": "api", "image": "synthetic.invalid/api:fixture"}],
            "desired_replicas": 2,
            "ready_replicas": 1 if index % 6 < 4 else 2,
        })
        status = ("failed", "failed", "failed", "failed", "passed", "not_evaluated")[index % 6]
        checks.append(check(index, resource_id, status, "workload", namespace, name))
    checks.extend([
        check(1001, BASE, "failed", "cluster"),
        check(1003, f"{BASE}/related/load-balancer", "failed", "resource"),
        check(1004, BASE, "passed", "cluster"),
        check(1005, BASE, "not_applicable", "cluster"),
    ])
    node_pools = [
        {
            **identity(f"{BASE}/agentPools/system", "arm"),
            "name": "system", "mode": "System", "vm_size": "Standard_D4s_v5",
            "count": 2, "min_count": 2, "max_count": 4, "enable_auto_scaling": True,
            "availability_zones": ["1", "2"], "version": "synthetic-version",
            "os_type": "Linux", "os_sku": "Ubuntu", "os_disk_type": "Managed",
            "max_pods": 30, "node_taints": [], "vnet_subnet_id": None,
            "pod_subnet_id": None, "provisioning_state": "Failed",
            "upgrade_settings": {"max_surge": "25%", "drain_timeout_minutes": 30},
            "scale_down_mode": "Delete", "priority": "Regular",
        },
        {
            **identity(f"{BASE}/agentPools/user", "arm"),
            "name": "user", "mode": "User", "vm_size": "Standard_D4s_v5",
            "count": 1, "min_count": None, "max_count": None, "enable_auto_scaling": None,
            "availability_zones": None, "version": None, "provisioning_state": "Succeeded",
        },
    ]
    candidates = []
    for index in (2, 14, 26):
        if index >= len(workloads):
            continue
        candidates.append({
            "id": f"candidate-{index}",
            "title": "Candidato simulado de ajuste de requests",
            "resource_id": workloads[index]["resource_id"],
            "source_id": "kubernetes",
            "basis": "Muestra sintética de CPU; no es una estimación de ahorro",
            "value": 17.5, "unit": "%", "sample_count": 144,
            "window": {"start": "2026-10-12T12:00:00Z", "end": REFERENCE},
            "recommendation": "Revisar requests con una ventana representativa y validar la necesidad.",
            "estimated_savings": None,
        })
    snapshot = {
        "schema_version": "1.0",
        "provenance": "SIMULATED",
        "environment": "LAB",
        "reference_utc": REFERENCE,
        "client": {"name": "CLIENTE", "logo_data_uri": "", "logo_alt": ""},
        "cluster": {
            "id": BASE, "name": "aks-ui-synthetic",
            "subscription_id": "subscription-synthetic",
            "resource_group": "rg-ui-synthetic", "region": "westeurope",
            "version": "synthetic-version", "power_state": "Running",
            "provisioning_state": "Failed", "sku_tier": "Standard", "mode": "Manual",
        },
        "sources": [
            {"id": "arm", "status": "complete", "time": REFERENCE, "records": 3,
             "pages": 1, "errors": [], "note": "Recibo ARM expresamente simulado.", "window": None},
            {"id": "kubernetes", "status": "partial", "time": REFERENCE,
             "records": workload_count, "pages": 4,
             "errors": [{"code": "SyntheticPartial", "http_status": 403,
                         "message": "Parte de la configuración de prueba no está disponible."}],
             "note": "No representa acceso real a Kubernetes.", "window": None},
            {"id": "cost", "status": "error", "time": REFERENCE, "records": None, "pages": 0,
             "errors": [{"code": "SyntheticThrottling", "http_status": 429,
                         "message": "Coste no evaluado en esta prueba."}],
             "note": "No se sustituye un error de lectura por coste cero.", "window": None},
        ],
        "inventory": {
            "node_pools": node_pools,
            "namespaces": [
                {**identity(f"{BASE}/namespaces/{name}"), "name": name, "phase": "Active"}
                for name in ("team-a", "team-b")
            ],
            "workloads": workloads,
            "related_resources": [
                {**identity(f"{BASE}/related/load-balancer", "arm"),
                 "name": "lb-ui-synthetic", "type": "Microsoft.Network/loadBalancers",
                 "resource_group": "rg-ui-synthetic", "region": "westeurope"}
            ],
            "nodes": None, "pods": [], "services": [], "storage_classes": [],
            "pvcs": [], "pvs": [], "pdbs": None, "hpas": None,
            "network_policies": None, "resource_quotas": [],
            "metrics": [
                {**identity(workloads[2]["resource_id"]), "namespace": workloads[2]["namespace"],
                 "name": "cpu-p95-synthetic", "value": 17.5, "unit": "%"}
            ] if len(workloads) > 2 else [],
        },
        "checks": checks,
        "source_data": {
            "regional_versions": [{"version": "synthetic-version", "source_id": "arm",
                                   "observed_at": REFERENCE, "synthetic_fixture": True}],
            "upgrade_profile": None, "arm_maintenance": [], "arm_diagnostics": [],
            "advisor": [], "cost_rows": None,
        },
        "findings": [],
        "scores": {},
        "finops": {
            "sources": ["cost", "kubernetes"],
            "window": {"start": "2026-10-12T12:00:00Z", "end": REFERENCE},
            "currency": None, "actual_cost": None, "estimated_savings": None,
            "cost_rows": None, "metrics": [], "candidates": candidates,
            "notes": [
                "Prueba SIMULATED: la muestra de utilización no implica ahorro monetario.",
                "Cost Management no evaluado: recibo de error sintético HTTP 429.",
                "Spot, reservas y recursos huérfanos necesitan evidencia adicional; no se infieren.",
            ],
        },
        "actions": [],
        "executive_messages": [
            "Prueba de interfaz SIMULATED: no son observaciones en vivo ni datos de un cliente.",
            "El estado de energía Running no sustituye al estado de aprovisionamiento del pool.",
            "La cobertura parcial de configuración y la falta de coste permanecen visibles.",
        ],
        "methodology": {
            "score_kind": "local_assessment_indicator",
            "official_waf_score": False, "read_only": True,
            "catalogSnapshot": {"name": "Catálogo de prueba", "version": "synthetic-fixture",
                                "retrieved_at": REFERENCE, "source_url": LEARN},
            "catalog_coverage": {"total_items": 112, "mapped_items": 32, "unmapped_items": 80},
            "scope": {"cluster_id": BASE, "environment": "LAB", "synthetic_fixture": True},
            "limitations": [
                "No establece permisos, despliegue, cumplimiento o resultados de un clúster real.",
                "Las preguntas de intención y arquitectura requieren revisión humana.",
            ],
            "source_pins": [{"name": "Referencia de prueba", "url": LEARN,
                             "version": "synthetic-fixture", "commit": None, "retrieved_at": REFERENCE}],
            "queries": [
                {"source_id": "arm", "description": "Firma HTTP de prueba, no ejecutada",
                 "command": f"GET {BASE}?api-version=synthetic-fixture", "read_limit": "4 páginas de prueba"}
            ],
        },
    }
    refresh_fixture(snapshot)
    for index, finding in enumerate(snapshot["findings"]):
        snapshot["actions"].append({
            "action_id": f"action-{finding['check_id']}",
            "check_id": finding["check_id"], "title": finding["title"],
            "resource_id": finding["resource_id"], "namespace": finding["namespace"],
            "workload_name": finding["workload_name"], "area": finding["area"],
            "pillar": finding["pillar"], "severity": finding["severity"],
            "effort": finding["effort"],
            "planning_bucket": ("quick_win", "short_term", "medium_term")[index % 3],
            "recommendation": finding["recommendation"], "learn_url": LEARN, "owner": None,
        })
    return snapshot


def safe_fixture_json(snapshot):
    value = json.dumps(snapshot, ensure_ascii=True, separators=(",", ":"), allow_nan=False)
    for literal, escaped in (
        ("<", "\\u003c"), (">", "\\u003e"), ("&", "\\u0026"),
        ("\u2028", "\\u2028"), ("\u2029", "\\u2029"),
    ):
        value = value.replace(literal, escaped)
    return value


def architecture_fixture(workload_count=8):
    snapshot = fixture(workload_count)
    graph = {"nodes": [], "edges": [], "unknowns": []}

    def add_node(key, kind, label, source="arm", evidence=None, resource_id=None):
        graph["nodes"].append({
            "id": key, "resource_id": resource_id or BASE, "cluster_id": BASE,
            "cluster_name": snapshot["cluster"]["name"], "kind": kind, "label": label,
            "provenance": "SIMULATED", "observed_at": REFERENCE, "source_id": source,
            "evidence": evidence or {"synthetic_fixture": True},
        })

    def add_edge(key, source, target, relation, sources):
        graph["edges"].append({
            "id": key, "from": source, "to": target, "relation": relation,
            "cluster_id": BASE, "source_ids": sources, "provenance": "SIMULATED",
            "observed_at": REFERENCE, "evidence": {"synthetic_fixture": True,
                                                  "actual_join_field": key},
        })

    add_node("aks", "aks", snapshot["cluster"]["name"])
    for name in ("team-a", "team-b"):
        add_node(name, "namespace", name, "kubernetes", {"namespace": name, "name": name})
        add_edge("namespace-" + name, "aks", name, "contains_namespace", ["arm", "kubernetes"])
    for index, workload in enumerate(snapshot["inventory"]["workloads"]):
        key = f"workload-{index}"
        workload["uid"] = key
        add_node(key, "workload", workload["name"], "kubernetes", {
            "namespace": workload["namespace"], "name": workload["name"],
            "kind": workload["kind"], "uid": key, "extra": {"observed_zero": 0},
        }, workload["resource_id"])
        add_edge(key + "-namespace", workload["namespace"], key, "contains_workload", ["kubernetes"])
    add_node("elb", "public_load_balancer", "elb-synthetic", evidence={
        "public_ip_id": BASE + "/related/public-ip",
        "frontend_id": BASE + "/related/elb/frontendIPConfigurations/public",
    })
    add_node("ilb", "private_load_balancer", "ilb-synthetic", evidence={
        "private_ip": "192.0.2.10", "subnet_id": BASE + "/related/subnet",
        "frontend_id": BASE + "/related/ilb/frontendIPConfigurations/internal",
    })
    add_edge("elb-reference", "aks", "elb", "explicit_resource_reference", ["arm"])
    add_edge("ilb-reference", "aks", "ilb", "explicit_resource_reference", ["arm"])
    graph["unknowns"].append({
        "code": "synthetic_pv_denied", "kind": "pv", "message": "No evaluado: acceso simulado HTTP 403.",
        "source_ids": ["kubernetes"], "cluster_id": BASE,
        "cluster_name": snapshot["cluster"]["name"], "resource_id": BASE,
        "status": "not_evaluated", "provenance": "SIMULATED", "observed_at": REFERENCE,
    })
    snapshot["architecture"] = graph
    snapshot["available_clusters"] = [{
        "cluster_id": BASE, "cluster_name": snapshot["cluster"]["name"],
        "resource_group": snapshot["cluster"]["resource_group"], "environment": "LAB",
    }]
    snapshot["selected_cluster_names"] = [snapshot["cluster"]["name"]]
    return snapshot


def multi_fixture(primary_error=False):
    first = architecture_fixture()
    second = json.loads(json.dumps(first).replace("aks-ui-synthetic", "aks-ui-second"))
    second["checks"][0]["title"] = "Comprobación del segundo clúster SIMULATED"
    refresh_fixture(second)
    roster = [value["available_clusters"][0] for value in (first, second)]
    for value in (first, second):
        value["available_clusters"] = copy.deepcopy(roster)
    successful = [first] if primary_error else [first, second]
    checks = [check for value in successful for check in value["checks"]]
    counts = {}
    for value in successful:
        for key, records in value["inventory"].items():
            counts[key] = counts.get(key, 0) + len(records or [])
    runs = [{
        "cluster_id": value["cluster"]["id"], "cluster_name": value["cluster"]["name"],
        "reference_utc": REFERENCE, "status": "partial", "error": None, "snapshot": value,
    } for value in (first, second)]
    if primary_error:
        runs[1].update(status="error", snapshot=None, error={
            "code": "synthetic_arm_denied", "source_id": "arm", "http_status": 403,
            "message": "No primary snapshot was collected in this SIMULATED test.",
        })
    return {
        "schema_version": "aks-waf-multi-cluster-v1", "reference_utc": REFERENCE,
        "provenance": "SIMULATED", "client": copy.deepcopy(first["client"]),
        "available_clusters": roster, "selected_cluster_names": [row["cluster_name"] for row in runs],
        "cluster_runs": runs,
        "aggregate": {
            "scores": {
                "global": score_fixture(checks), "coverage": score_fixture(checks),
                "areas": {area: score_fixture([row for row in checks if row["area"] == area]) for area in AREAS},
                "pillars": {pillar: score_fixture([row for row in checks if row["pillar"] == pillar]) for pillar in PILLARS},
            },
            "inventory_counts": counts, "findings_total": sum(row["status"] == "failed" for row in checks),
            "critical_total": sum(row["status"] == "failed" and row["severity"] == "critical" for row in checks),
            "cluster_status_counts": {"ok": 0, "partial": len(successful), "error": int(primary_error)},
        },
    }


def embed_fixture(snapshot):
    template = TEMPLATE.read_text(encoding="utf-8")
    if template.count(TOKEN) != 1:
        raise AssertionError("The named safe JSON token must occur exactly once.")
    return template.replace(TOKEN, safe_fixture_json(snapshot), 1)


def digest(value):
    return hashlib.sha256(json.dumps(
        value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")).hexdigest()


def contrast(foreground, background):
    def luminance(color):
        channels = [int(color[index:index + 2], 16) / 255 for index in (1, 3, 5)]
        linear = [value / 12.92 if value <= .04045 else ((value + .055) / 1.055) ** 2.4
                  for value in channels]
        return sum(value * weight for value, weight in zip(linear, (.2126, .7152, .0722)))
    values = sorted((luminance(foreground), luminance(background)))
    return (values[1] + .05) / (values[0] + .05)


class ParsedTemplate(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []
        self.data_script = False
        self.data = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        self.tags.append((tag, attributes))
        if tag == "script" and attributes.get("id") == "report-data":
            self.data_script = True

    def handle_endtag(self, tag):
        if tag == "script":
            self.data_script = False

    def handle_data(self, value):
        if self.data_script:
            self.data.append(value)


class TemplateContractTests(unittest.TestCase):
    @unittest.skip("Documentation check; it runs upstream with the full guide")
    def test_official_svg_subset_is_static_original_and_embedded_losslessly(self):
        folder = CASE / "images" / "azure-icons"
        manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        content = TEMPLATE.read_text(encoding="utf-8")
        match = re.search(r"const AZURE_ICONS = new Map\((\[.*?\])\);", content, re.S)
        embedded = dict(json.loads(match.group(1)))
        self.assertEqual(manifest["version"], "V24")
        self.assertEqual(len(embedded), len(manifest["icons"]))
        self.assertLessEqual(len(embedded), 12)
        self.assertIn("Microsoft reserves all other rights", (folder / "NOTICE.md").read_text(encoding="utf-8"))
        for item in manifest["icons"]:
            data = (folder / item["file"]).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), item["sha256"])
            self.assertEqual(len(data), item["bytes"])
            uri = embedded[item["key"]]
            self.assertTrue(uri.startswith("data:image/svg+xml;base64,"))
            self.assertEqual(base64.b64decode(uri.split(",", 1)[1], validate=True), data)
            self.assertNotRegex(data.decode("utf-8"), r"(?i)<!DOCTYPE|<!ENTITY")
            for element in ET.fromstring(data).iter():
                self.assertNotIn(element.tag.rsplit("}", 1)[-1], {
                    "script", "foreignObject", "image", "use", "a", "style", "animate", "animateTransform", "set",
                })
                for key, value in element.attrib.items():
                    self.assertFalse(key.rsplit("}", 1)[-1].lower().startswith("on"))
                    if key.rsplit("}", 1)[-1] in {"href", "src"}:
                        self.assertRegex(value, r"^#[A-Za-z0-9_-]+$")
                    if "url(" in value:
                        self.assertRegex(value, r"^url\(#[A-Za-z0-9_-]+\)$")

    def test_one_named_data_token_inline_only_and_neutral_public_brand(self):
        content = TEMPLATE.read_text(encoding="utf-8")
        parsed = ParsedTemplate()
        parsed.feed(content)
        self.assertEqual(content.count(TOKEN), 1)
        self.assertIn('<html lang="en">', content)
        self.assertIn('"Segoe UI", system-ui, sans-serif', content)
        self.assertEqual(len([tag for tag, _ in parsed.tags if tag == "script"]), 2)
        self.assertFalse(any(attrs.get("src") for tag, attrs in parsed.tags if tag == "script"))
        self.assertFalse(any(tag == "link" for tag, _ in parsed.tags))
        self.assertIn("connect-src 'none'", content)
        self.assertIn("base-uri 'none'", content)
        self.assertIn("img-src data:", content)
        self.assertEqual("".join(parsed.data).strip(), TOKEN)
        self.assertIn('node("span", "CUSTOMER", "brand-placeholder")', content)
        self.assertNotRegex(content, r"(?:\.innerHTML\b|insertAdjacentHTML|document\.write|eval\(|new Function|fetch\(|XMLHttpRequest)")
        self.assertNotRegex(content.lower(), r"(?:linear-gradient|radial-gradient|backdrop-filter)")
        self.assertLess(len(content.encode("utf-8")), MAX_BYTES)

    def test_safe_embedding_preserves_hostile_text_and_prototype_keys(self):
        snapshot = fixture(8)
        snapshot["literal"] = {
            "__proto__": {"polluted": True},
            "constructor": {"prototype": {"polluted": True}},
            "text": '</script><script>window.injected=true</script> & \u2028 \u2029',
            "surrogates": ["\ud800", "\udfff", "\U0001f600"],
        }
        content = embed_fixture(snapshot)
        parsed = ParsedTemplate()
        parsed.feed(content)
        self.assertEqual(len([tag for tag, _ in parsed.tags if tag == "script"]), 2)
        self.assertEqual(json.loads("".join(parsed.data)), snapshot)
        self.assertNotIn("</script><script>window.injected", content)
        self.assertLess(len(content.encode("utf-8")), MAX_BYTES)

    def test_light_dark_tokens_meet_text_and_control_contrast(self):
        content = TEMPLATE.read_text(encoding="utf-8")
        for selector in (r":root\s*\{", r':root\[data-theme="dark"\]\s*\{'):
            body = re.search(selector + r"([^}]+)\}", content).group(1)
            tokens = dict(re.findall(r"--([\w-]+):\s*(#[0-9a-fA-F]{6})", body))
            for foreground in ("ink", "muted", "accent"):
                for background in ("surface", "subtle", "canvas"):
                    with self.subTest(selector=selector, foreground=foreground, background=background):
                        self.assertGreaterEqual(contrast(tokens[foreground], tokens[background]), 4.5)
            for severity in ("critical", "high", "medium", "low"):
                self.assertGreaterEqual(contrast(tokens[severity], tokens[f"{severity}-wash"]), 4.5)
            self.assertGreaterEqual(contrast(tokens["on-accent"], tokens["accent"]), 4.5)
            self.assertGreaterEqual(contrast(tokens["field-line"], tokens["surface"]), 3)
            self.assertGreaterEqual(contrast(tokens["accent"], tokens["wash"]), 3)
            for foreground, background in (
                ("on-chrome", "chrome"), ("nav-ink", "nav"), ("nav-muted", "nav"),
                ("cover-ink", "cover"), ("cover-muted", "cover"),
            ):
                self.assertGreaterEqual(contrast(tokens[foreground], tokens[background]), 4.5)

    def test_no_fixture_is_embedded_in_the_public_template(self):
        content = TEMPLATE.read_text(encoding="utf-8")
        self.assertNotIn("aks-ui-synthetic", content)
        self.assertNotIn("subscription-synthetic", content)
        self.assertNotIn('"score":', content)
        snapshot = fixture()
        self.assertEqual(snapshot["provenance"], "SIMULATED")
        self.assertEqual(snapshot["environment"], "LAB")
        self.assertEqual(snapshot["client"]["name"], "CLIENTE")
        self.assertGreater(len(snapshot["findings"]), 25)


CONTRAST_AUDIT = r"""() => {
  const rgb = input => {
    const values = input.match(/[\d.]+/g).map(Number);
    return [values[0], values[1], values[2], values.length > 3 ? values[3] : 1];
  };
  const blend = (front, back) => front.slice(0, 3).map((value, index) => value * front[3] + back[index] * (1 - front[3]));
  const luminance = color => color.map(value => {
    value /= 255; return value <= .04045 ? value / 12.92 : ((value + .055) / 1.055) ** 2.4;
  }).reduce((total, value, index) => total + value * [.2126, .7152, .0722][index], 0);
  const background = element => {
    const chain = [];
    for (let current = element; current; current = current.parentElement) chain.unshift(current);
    let result = [255, 255, 255];
    for (const current of chain) result = blend(rgb(getComputedStyle(current).backgroundColor), result);
    return result;
  };
  const issues = [], measured = [];
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  while (walker.nextNode()) {
    const current = walker.currentNode, element = current.parentElement;
    if (!current.textContent.trim() || !element || element.closest("script,style,noscript,button:disabled") ||
        !element.checkVisibility({checkOpacity: true, checkVisibilityCSS: true})) continue;
    const range = document.createRange(); range.selectNodeContents(current);
    if (![...range.getClientRects()].some(rect => rect.width > 0 && rect.height > 0)) continue;
    const style = getComputedStyle(element), bg = background(element), fg = blend(rgb(style.color), bg);
    const first = luminance(fg), second = luminance(bg), ratio = (Math.max(first, second) + .05) / (Math.min(first, second) + .05);
    const large = parseFloat(style.fontSize) >= 24 || (parseFloat(style.fontSize) >= 18.66 && Number(style.fontWeight) >= 700);
    const minimum = large ? 3 : 4.5;
    measured.push(ratio);
    if (ratio + .01 < minimum) issues.push({text: current.textContent.trim().slice(0, 90), ratio, minimum, color: style.color, tag: element.tagName});
  }
  for (const element of document.querySelectorAll('input[placeholder]')) {
    if (!element.checkVisibility()) continue;
    const bg = background(element), fg = blend(rgb(getComputedStyle(element, "::placeholder").color), bg);
    const first = luminance(fg), second = luminance(bg), ratio = (Math.max(first, second) + .05) / (Math.min(first, second) + .05);
    if (ratio + .01 < 4.5) issues.push({text: "placeholder", ratio, minimum: 4.5});
  }
  return {issues, measured: measured.length, minimum: Math.min(...measured)};
}"""


@unittest.skipUnless(
    os.environ.get("SRE_REPORT_BROWSER_TESTS") == "1",
    "Set SRE_REPORT_BROWSER_TESTS=1 to run installed Playwright and a local browser.",
)
class ReportBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from playwright.sync_api import sync_playwright
        cls.playwright = sync_playwright().start()
        cls.addClassCleanup(cls.playwright.stop)
        channel = os.environ.get(
            "SRE_REPORT_BROWSER_CHANNEL", "msedge" if sys.platform == "win32" else ""
        )
        cls.browser = cls.playwright.chromium.launch(
            headless=True, **({"channel": channel} if channel else {})
        )
        cls.addClassCleanup(cls.browser.close)

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix="aks-report-ui-")
        self.addCleanup(self.folder.cleanup)
        self.context = self.browser.new_context(
            accept_downloads=True, viewport={"width": 1440, "height": 1000},
            color_scheme="light", reduced_motion="reduce",
        )
        self.addCleanup(self.context.close)
        self.page = self.context.new_page()
        self.errors, self.external = [], []
        self.page.on("pageerror", lambda error: self.errors.append(str(error)))
        self.page.on("request", lambda request: self.external.append(request.url)
                     if request.url.startswith(("http:", "https:")) else None)
        self.file_index = 0

    def tearDown(self):
        self.assertEqual(self.errors, [], "Unhandled browser error.")
        self.assertEqual(self.external, [], "The offline report attempted a network request.")

    def open_report(self, snapshot, expected="ready"):
        self.file_index += 1
        path = Path(self.folder.name) / f"report-{self.file_index}.html"
        content = embed_fixture(snapshot)
        self.assertLessEqual(len(content.encode("utf-8")), MAX_BYTES)
        path.write_text(content, encoding="utf-8")
        self.page.goto(path.as_uri())
        self.page.wait_for_function("() => document.body.dataset.status !== 'loading'", timeout=10000)
        self.assertEqual(self.page.locator("body").get_attribute("data-status"), expected)
        return path

    def download(self, selector):
        with self.page.expect_download() as pending:
            self.page.locator(selector).click()
        return Path(pending.value.path()).read_bytes()

    def csv_rows(self, content):
        previous = csv.field_size_limit()
        try:
            csv.field_size_limit(max(previous, len(content)))
            return list(csv.DictReader(io.StringIO(content.decode("utf-8-sig"))))
        finally:
            csv.field_size_limit(previous)

    def open_checks(self):
        details = self.page.locator('[data-detail-key="checks-disclosure"]')
        if details.get_attribute("open") is None:
            details.locator(":scope > summary").click()

    def open_extra_filters(self):
        details = self.page.locator(".extra-filters")
        if details.get_attribute("open") is None:
            details.locator(":scope > summary").click()

    def test_status_chart_uses_supplied_counts_and_keeps_uncertainty_neutral(self):
        snapshot = fixture(8)
        snapshot["scores"]["global"]["score"] = 42.5
        snapshot["scores"]["coverage"]["coverage_percent"] = 15.13
        self.open_report(snapshot)
        rows = self.page.locator("#assessment-chart tbody tr")
        expected = snapshot["scores"]["global"]
        self.assertEqual(rows.count(), 4)
        self.assertEqual([int(row.locator("td").first.inner_text()) for row in rows.all()],
                         [expected[key] for key in ("passed", "failed", "not_evaluated", "not_applicable")])
        self.assertEqual(self.page.locator("#assessment-chart .chart-total").text_content(),
                         str(expected["total"]))
        self.assertIn("not a health chart", self.page.locator("#assessment-svg-title").text_content())
        self.assertIn("Not evaluated is not a passed result", self.page.locator("#assessment-chart").inner_text())
        self.assertIn("15.1%", self.page.locator("#global-coverage").inner_text())
        self.assertIn("42.5 / 100", self.page.locator("#global-index").inner_text())
        self.assertEqual(self.download("#export-json"), safe_fixture_json(snapshot).encode("utf-8"))

    def test_financial_emphasis_separates_observed_currency_scope_and_uncalculated_savings(self):
        snapshot = fixture(8)
        snapshot["finops"].update(actual_cost=295.823588, currency="USD", cost_source_complete=True)
        cost = next(row for row in snapshot["sources"] if row["id"] == "cost")
        cost.update(status="complete", errors=[], cost_type="ActualCost",
                    scope=BASE + "/synthetic-billing-scope",
                    association={"type": "node_resource_group_billing_context"})
        self.open_report(snapshot)
        baseline = self.page.locator("#finops-baseline")
        self.assertIn("295.82 USD", baseline.inner_text())
        self.assertIn("node_resource_group_billing_context", baseline.inner_text())
        self.assertIn("synthetic-billing-scope", baseline.inner_text())
        self.assertIn("To be estimated", baseline.locator(".savings .financial-amount").inner_text())
        self.assertIn("Not calculated", baseline.locator(".savings").inner_text())
        self.assertNotIn("0 USD", baseline.locator(".savings").inner_text())
        self.page.locator("#filter-namespace").select_option("team-a")
        self.assertIn("295.82 USD", baseline.inner_text())
        self.assertEqual(json.loads(self.download("#export-json")), snapshot)

    def test_missing_optional_financial_receipts_are_explicit_not_blank(self):
        self.open_report(fixture(8))
        values = self.page.locator("#finops-baseline dd").all_text_contents()
        self.assertTrue(all(value.strip() for value in values))
        for label in ("Exact cost read scope", "Billing association / not ownership"):
            self.assertEqual(self.page.locator("#finops-baseline dt").filter(has_text=label)
                             .locator("xpath=following-sibling::dd[1]").inner_text(), "Not evaluated")

    def test_observed_graph_has_exact_ids_sources_properties_and_namespace_context(self):
        snapshot = architecture_fixture()
        self.open_report(snapshot)
        self.assertIn("Observed architecture", self.page.locator("#architecture-observed-note").inner_text())
        self.assertIn("not verified traffic", self.page.locator("#architecture-observed-note").inner_text())
        self.assertEqual(self.page.locator("#architecture-node option").count(),
                         len(snapshot["architecture"]["nodes"]))
        self.assertEqual(self.page.locator('table[data-collection="architecture-edges"] tbody tr').count(),
                         len(snapshot["architecture"]["edges"]))
        self.page.locator("#architecture-node").select_option("ilb")
        self.assertIn("ilb-synthetic", self.page.locator("#architecture-properties").inner_text())
        receipt = self.page.locator('[data-detail-key="graph-node:ilb"]')
        receipt.locator(":scope > summary").click()
        self.assertIn("192.0.2.10", receipt.inner_text())
        self.page.locator("#filter-namespace").select_option("team-a")
        self.assertNotIn("team-b", self.page.locator("#architecture-tree").inner_text())
        self.assertNotIn("team-b", self.page.locator("#architecture-map").inner_text())
        self.assertNotIn("workload-1", self.page.locator("#architecture-node").inner_text())
        self.assertEqual(json.loads(self.download("#export-json")), snapshot)
        self.assertEqual(json.loads(self.download("#export-filtered-json"))["architecture"],
                         snapshot["architecture"])

    def test_reference_proposal_is_separate_official_icon_only_and_printed_as_undeployed(self):
        self.open_report(architecture_fixture())
        self.assertTrue(self.page.locator("#architecture-reference").is_hidden())
        self.page.locator("#architecture-observed-tab").focus()
        self.page.keyboard.press("ArrowRight")
        reference = self.page.locator("#architecture-reference")
        self.assertTrue(reference.is_visible())
        self.assertTrue(self.page.locator("#architecture-observed").is_hidden())
        self.assertEqual(self.page.locator("#architecture-reference-tab").get_attribute("aria-selected"), "true")
        self.assertIn("NOT deployed", reference.inner_text())
        self.assertIn("Public Azure Load Balancer / ELB", reference.inner_text())
        self.assertIn("Private Azure Load Balancer / ILB", reference.inner_text())
        self.assertNotRegex(reference.inner_text(), r"Cosmos|Redis|Service Bus|AWS")
        self.assertGreaterEqual(reference.locator("img.architecture-product-icon").count(), 6)
        self.assertTrue(all(image.get_attribute("src").startswith("data:image/svg+xml;base64,")
                            for image in reference.locator("img").all()))
        self.assertTrue(all(link.get_attribute("href").startswith("https://learn.microsoft.com/")
                            for link in reference.locator("a").all()))
        self.page.evaluate("window.dispatchEvent(new Event('beforeprint'))")
        self.page.emulate_media(media="print")
        self.assertTrue(self.page.locator("#architecture-observed").is_visible())
        self.assertTrue(reference.is_visible())
        self.assertIn("NOT deployed", reference.inner_text())
        self.page.evaluate("window.dispatchEvent(new Event('afterprint'))")
        self.page.emulate_media(media="screen")

    def test_multi_cluster_selector_resets_scope_and_exports_original_wrapper(self):
        snapshot = multi_fixture()
        self.open_report(snapshot)
        self.assertTrue(self.page.locator("#cluster-overview").is_visible())
        self.page.locator("#filter-namespace").select_option("team-a")
        self.page.locator("#cluster-selector").select_option("aks-ui-second")
        self.assertEqual(self.page.locator("#filter-namespace").input_value(), "")
        self.assertIn("aks-ui-second", self.page.locator("#cover-facts").inner_text())
        self.assertEqual(self.page.locator("#area-scores .score-row").count(), 4)
        self.assertIn("segundo clúster", self.page.locator("#findings-list").inner_text())
        self.assertEqual(json.loads(self.download("#export-json")), snapshot)
        self.page.locator("#filter-namespace").select_option("team-a")
        scoped = json.loads(self.download("#export-filtered-json"))
        self.assertEqual(scoped["cluster_runs"][0], snapshot["cluster_runs"][0])
        self.assertEqual(scoped["aggregate"], snapshot["aggregate"])
        selected = scoped["cluster_runs"][1]["snapshot"]
        self.assertTrue(all(row["namespace"] == "team-a" for row in selected["inventory"]["workloads"]))
        self.assertEqual(selected["architecture"], snapshot["cluster_runs"][1]["snapshot"]["architecture"])
        self.assertIn("All other results", scoped["scope_note"])
        self.assertEqual(scoped["filter_context"]["cluster_name"], "aks-ui-second")

    def test_multi_cluster_arm_case_equivalence_preserves_original_ids_and_independent_dates(self):
        snapshot = multi_fixture()
        for run in snapshot["cluster_runs"]:
            run["cluster_id"] = run["cluster_id"].upper()
            run["snapshot"]["cluster"]["id"] = run["snapshot"]["cluster"]["id"].lower()
            for collection in run["snapshot"]["architecture"].values():
                for row in collection:
                    row["cluster_id"] = row["cluster_id"].swapcase()
        snapshot["cluster_runs"][1]["reference_utc"] = "2026-10-13T12:01:31Z"
        snapshot["cluster_runs"][1]["snapshot"]["reference_utc"] = "2026-10-13T12:01:31Z"
        original = copy.deepcopy(snapshot)
        self.open_report(snapshot)
        for run in snapshot["cluster_runs"]:
            self.page.locator("#cluster-selector").select_option(run["cluster_name"])
            self.assertIn(run["cluster_name"], self.page.locator("#cover-facts").inner_text())
            self.assertEqual(json.loads(self.download("#export-json")), original)
            scoped = json.loads(self.download("#export-filtered-json"))
            for actual, expected in zip(scoped["cluster_runs"], original["cluster_runs"]):
                self.assertEqual(actual["cluster_id"], expected["cluster_id"])
                self.assertEqual(actual["reference_utc"], expected["reference_utc"])
                for key, value in expected["snapshot"].items():
                    self.assertEqual(actual["snapshot"][key], value)
                if actual["cluster_name"] != run["cluster_name"]:
                    self.assertEqual(actual, expected)
            self.assertEqual(scoped["aggregate"], original["aggregate"])
        self.assertEqual(snapshot, original)

    def test_arm_identity_rejects_different_full_scopes_unsafe_ids_and_case_duplicate_roster(self):
        baseline = multi_fixture()
        invalid_ids = (
            BASE + "/agentPools/system",
            BASE.replace("rg-ui-synthetic", "rg-ui-other"),
            BASE.replace("aks-ui-synthetic", "aks-ui-different"),
            BASE.replace("11111111-1111-4111-8111-111111111111", "22222222-2222-4222-8222-222222222222"),
            BASE + "?scope=other", BASE + "#other", BASE + "/", BASE.replace("rg-ui-synthetic", ".."),
            BASE.replace("rg-ui-synthetic", "rg%2fother"), BASE.replace("11111111-1111-4111-8111-111111111111", "not-a-guid"),
            "https://management.azure.com" + BASE,
        )
        for resource_id in invalid_ids:
            with self.subTest(resource_id=resource_id):
                snapshot = copy.deepcopy(baseline)
                snapshot["cluster_runs"][0]["cluster_id"] = resource_id
                snapshot["available_clusters"][0]["cluster_id"] = resource_id
                self.open_report(snapshot, expected="error")
                self.assertTrue(self.page.locator("#report-shell").is_hidden())
                self.assertTrue(self.page.locator("#export-json").is_disabled())
        snapshot = copy.deepcopy(baseline)
        snapshot["available_clusters"][1]["cluster_id"] = BASE.upper()
        self.open_report(snapshot, expected="error")
        self.assertIn("duplicate identity", self.page.locator("#opening-detail").inner_text())
        snapshot = copy.deepcopy(baseline)
        snapshot["cluster_runs"][0]["snapshot"]["reference_utc"] = "2026-10-13T12:00:01Z"
        self.open_report(snapshot, expected="error")
        self.assertIn("inconsistent snapshot, date or identity", self.page.locator("#opening-detail").inner_text())

    def test_multi_primary_failure_has_no_borrowed_snapshot_or_score(self):
        snapshot = multi_fixture(primary_error=True)
        self.open_report(snapshot)
        self.page.locator("#cluster-selector").select_option("aks-ui-second")
        self.assertTrue(self.page.locator("#cluster-error").is_visible())
        self.assertIn("synthetic_arm_denied", self.page.locator("#cluster-error").inner_text())
        self.assertTrue(self.page.locator("#cover").is_hidden())
        self.assertTrue(self.page.locator("#executive").is_hidden())
        self.assertTrue(self.page.locator("#architecture").is_hidden())
        self.assertTrue(self.page.locator("#export-filtered-json").is_disabled())
        self.assertFalse(self.page.locator("#export-json").is_disabled())
        self.assertEqual(json.loads(self.download("#export-json")), snapshot)
        self.page.locator("#cluster-selector").select_option("aks-ui-synthetic")
        self.assertTrue(self.page.locator("#cover").is_visible())
        self.assertTrue(self.page.locator("#cluster-error").is_hidden())
        self.assertIn("aks-ui-synthetic", self.page.locator("#cover-facts").inner_text())
        self.assertEqual(self.page.locator("#area-scores .score-row").count(), 4)

    def test_multi_sparse_status_counter_omits_only_verified_zero_categories(self):
        snapshot = multi_fixture()
        snapshot["aggregate"]["cluster_status_counts"] = {"partial": 2}
        self.open_report(snapshot)
        self.assertIn("0 / 2 / 0", self.page.locator("#cluster-aggregate").inner_text())
        self.assertEqual(json.loads(self.download("#export-json")), snapshot)
        snapshot["aggregate"]["cluster_status_counts"] = {}
        self.open_report(snapshot, expected="error")
        self.assertIn("non-zero run count", self.page.locator("#opening-detail").inner_text())

    def test_graph_and_multi_invalid_contracts_fail_before_exposing_results(self):
        cases = []
        value = architecture_fixture()
        value["architecture"]["edges"][0]["to"] = "unobserved-target"
        cases.append(value)
        value = architecture_fixture()
        value["architecture"]["nodes"][0]["source_id"] = "unknown-source"
        cases.append(value)
        value = architecture_fixture()
        value["architecture"]["unknowns"][0]["status"] = "passed"
        cases.append(value)
        value = multi_fixture()
        value["cluster_runs"][1]["snapshot"]["cluster"]["id"] = BASE
        cases.append(value)
        value = multi_fixture(primary_error=True)
        value["cluster_runs"][1]["error"] = None
        cases.append(value)
        for value in cases:
            with self.subTest(case=len(cases)):
                self.open_report(value, expected="error")
                self.assertTrue(self.page.locator("#report-shell").is_hidden())
                self.assertTrue(self.page.locator("#export-json").is_disabled())

    def test_complete_snapshot_equality_counts_paging_and_all_exports(self):
        snapshot = fixture()
        self.open_report(snapshot)
        self.assertIn("SIMULATED", self.page.locator("#provenance").inner_text())
        self.assertIn("LAB", self.page.locator("#provenance").inner_text())
        self.assertIn("Running", self.page.locator("#cover-facts").inner_text())
        self.assertIn("Failed", self.page.locator("#node-pools").inner_text())
        self.assertEqual(self.page.locator('.finding').count(), 25)
        self.assertEqual(self.page.locator('table[data-collection="workloads"] tbody tr').count(), 25)
        exported = json.loads(self.download("#export-json"))
        self.assertEqual(exported, snapshot)
        self.assertEqual(digest(exported), digest(snapshot))
        filtered = json.loads(self.download("#export-filtered-json"))
        self.assertEqual(filtered["findings"], snapshot["findings"])
        self.assertEqual(filtered["source_data"], snapshot["source_data"])
        self.assertEqual(filtered["executive_messages"], snapshot["executive_messages"])
        findings = self.csv_rows(self.download("#export-findings"))
        self.assertEqual([row["check_id"] for row in findings],
                         [row["check_id"] for row in snapshot["findings"]])
        self.assertEqual([json.loads(row["record_json"]) for row in findings], snapshot["findings"])
        self.open_checks()
        checks = self.csv_rows(self.download("#export-checks"))
        self.assertEqual([json.loads(row["record_json"]) for row in checks], snapshot["checks"])
        inventory = self.csv_rows(self.download("#export-inventory"))
        expected_inventory = [(key, row) for key, rows in snapshot["inventory"].items()
                              if rows is not None for row in rows]
        self.assertEqual([(row["collection"], json.loads(row["record_json"])) for row in inventory],
                         expected_inventory)
        self.assertEqual([json.loads(row["record_json"]) for row in
                          self.csv_rows(self.download("#export-finops"))], snapshot["finops"]["candidates"])
        self.assertEqual([json.loads(row["record_json"]) for row in
                          self.csv_rows(self.download("#export-actions"))], snapshot["actions"])
        first = self.page.locator(".finding").first
        first.locator(":scope > summary").click()
        key = first.get_attribute("data-detail-key")
        self.page.locator('[data-more-collection="findings"]').click()
        self.assertEqual(self.page.locator(".finding").count(), min(50, len(snapshot["findings"])))
        self.assertIsNotNone(self.page.locator(f'[data-detail-key="{key}"]').get_attribute("open"))
        self.assertEqual(len(self.csv_rows(self.download("#export-findings"))), len(snapshot["findings"]))
        self.page.locator('[data-more-collection="workloads"]').click()
        self.assertEqual(self.page.locator('table[data-collection="workloads"] tbody tr').count(), 50)

    def test_namespace_and_workload_drilldown_do_not_confuse_same_names(self):
        snapshot = fixture()
        self.open_report(snapshot)
        self.page.locator('#namespaces button[data-drilldown="namespaces"]').filter(has_text="team-a").click()
        self.assertEqual(self.page.locator("#filter-namespace").input_value(), "team-a")
        expected = [check for check in snapshot["checks"] if check["namespace"] == "team-a"]
        scoped = json.loads(self.download("#export-filtered-json"))
        self.assertEqual(scoped["checks"], expected)
        self.assertTrue(all(row["namespace"] == "team-a" for row in scoped["inventory"]["workloads"]))
        selected = snapshot["inventory"]["workloads"][0]
        self.page.locator('#workloads button[data-drilldown="workloads"]').first.click()
        self.assertEqual(self.page.locator("#filter-workload").input_value(), selected["resource_id"])
        scoped = json.loads(self.download("#export-filtered-json"))
        self.assertEqual([check["resource_id"] for check in scoped["checks"]], [selected["resource_id"]])
        self.assertEqual(scoped["inventory"]["workloads"], [selected])
        self.assertNotIn(snapshot["inventory"]["workloads"][1]["resource_id"],
                         [check["resource_id"] for check in scoped["checks"]])
        self.assertEqual(scoped["scores"], snapshot["scores"])
        self.page.locator("#scope-path button").first.click()
        self.assertEqual(self.page.locator("#filter-namespace").input_value(), "")
        self.assertEqual(self.page.locator("#filter-workload").input_value(), "")
        self.assertEqual(len(json.loads(self.download("#export-filtered-json"))["checks"]),
                         len(snapshot["checks"]))

    def test_shared_arm_parent_uses_kubernetes_uid_and_namespace_for_drilldown(self):
        snapshot = fixture(8)
        workloads = snapshot["inventory"]["workloads"]
        for index, row in enumerate(workloads):
            original_id = row["resource_id"]
            row["resource_id"] = BASE
            row["uid"] = f"synthetic-workload-uid-{index}"
            for check in snapshot["checks"]:
                if check["resource_id"] != original_id:
                    continue
                check["resource_id"] = BASE
                check["kubernetes_ref"] = {"uid": row["uid"], "kind": row["kind"],
                                           "namespace": row["namespace"], "name": row["name"]}
                for evidence in check["evidence"]:
                    evidence["resource_id"] = BASE
        policy = copy.deepcopy(snapshot["checks"][0])
        policy.update(check_id="UI-synthetic-namespace-policy", status="passed",
                      workload_name="", namespace="team-a",
                      kubernetes_ref={"kind": None, "name": "team-a",
                                      "namespace": "team-a", "uid": "synthetic-namespace-uid"})
        snapshot["checks"].append(policy)
        refresh_fixture(snapshot)
        self.open_report(snapshot)
        options = self.page.locator("#filter-workload option").all()
        keys = [option.get_attribute("value") for option in options if option.get_attribute("value")]
        self.assertEqual(len(keys), len(workloads))
        self.assertEqual(len(set(keys)), len(workloads))
        self.page.locator("#filter-namespace").select_option("team-a")
        selected = json.loads(self.download("#export-filtered-json"))
        self.assertEqual(selected["inventory"]["workloads"],
                         [row for row in workloads if row["namespace"] == "team-a"])
        self.assertIn(policy["check_id"], [check["check_id"] for check in selected["checks"]])
        self.page.locator('#workloads button[data-drilldown="workloads"]').first.click()
        selected = json.loads(self.download("#export-filtered-json"))
        self.assertEqual(selected["inventory"]["workloads"], [workloads[0]])
        self.assertEqual([check["kubernetes_ref"]["uid"] for check in selected["checks"]],
                         [workloads[0]["uid"]])
        self.assertEqual(selected["scores"], snapshot["scores"])
        self.assertEqual(json.loads(self.download("#export-json")), snapshot)

    def test_shared_parent_without_uid_distinguishes_workload_kind_and_name(self):
        snapshot = fixture(8)
        original = snapshot["inventory"]["workloads"][0]
        duplicate = copy.deepcopy(original)
        duplicate["kind"] = "StatefulSet"
        snapshot["inventory"]["workloads"].append(duplicate)
        duplicate_check = copy.deepcopy(snapshot["checks"][0])
        duplicate_check["check_id"] = "UI-duplicate-kind"
        duplicate_check["kubernetes_ref"] = {"namespace": duplicate["namespace"],
                                           "name": duplicate["name"], "kind": duplicate["kind"]}
        snapshot["checks"][0]["kubernetes_ref"]["kind"] = original["kind"]
        snapshot["checks"].append(duplicate_check)
        for row in snapshot["inventory"]["workloads"]:
            row["resource_id"] = BASE
        for check in snapshot["checks"]:
            if check["level"] == "workload":
                check["resource_id"] = BASE
                for evidence in check["evidence"]:
                    evidence["resource_id"] = BASE
        refresh_fixture(snapshot)
        self.open_report(snapshot)
        options = self.page.locator("#filter-workload option").all()
        matching = [option for option in options if "team-a / api-00" in option.inner_text()]
        self.assertEqual(len(matching), 2)
        self.assertNotEqual(matching[0].get_attribute("value"), matching[1].get_attribute("value"))
        key = next(option.get_attribute("value") for option in matching
                   if option.inner_text().endswith("StatefulSet"))
        self.page.locator("#filter-workload").select_option(key)
        selected = json.loads(self.download("#export-filtered-json"))
        self.assertEqual(selected["inventory"]["workloads"], [duplicate | {"resource_id": BASE}])
        self.assertEqual([check["check_id"] for check in selected["checks"]], ["UI-duplicate-kind"])

    def test_combined_filters_cover_full_matching_set_and_reset(self):
        snapshot = fixture()
        self.open_report(snapshot)
        self.open_extra_filters()
        self.page.locator("#filter-area").select_option("security")
        self.page.locator("#filter-namespace").select_option("team-b")
        self.page.locator("#filter-level").select_option("workload")
        self.page.locator("#filter-status").select_option("failed")
        self.page.locator("#filter-severity").select_option("high")
        expected = [check for check in snapshot["checks"]
                    if check["area"] == "security" and check["namespace"] == "team-b"
                    and check["level"] == "workload" and check["status"] == "failed"
                    and check["severity"] == "high"]
        scoped = json.loads(self.download("#export-filtered-json"))
        self.assertEqual(scoped["checks"], expected)
        self.assertEqual(scoped["findings"], expected)
        self.assertEqual(scoped["scores"], snapshot["scores"])
        self.assertEqual([row["check_id"] for row in self.csv_rows(self.download("#export-findings"))],
                         [check["check_id"] for check in expected])
        noun = "check" if len(expected) == 1 else "checks"
        self.assertIn(f"{len(expected)} matching {noun} of", self.page.locator("#filter-count").inner_text())
        self.page.locator("#reset-filters").click()
        self.assertEqual(json.loads(self.download("#export-filtered-json"))["checks"], snapshot["checks"])

    def test_unknown_filter_preserves_reason_and_never_turns_it_into_a_finding(self):
        snapshot = fixture()
        self.open_report(snapshot)
        self.open_extra_filters()
        self.page.locator("#filter-status").select_option("not_evaluated")
        expected = [check for check in snapshot["checks"] if check["status"] == "not_evaluated"]
        self.assertEqual(self.page.locator(".finding").count(), 0)
        self.assertIn(f"{len(expected)} not evaluated", self.page.locator("#filter-count").inner_text())
        self.open_checks()
        self.assertIn("Fuente parcial de prueba", self.page.locator("#checks-table").inner_text())
        rows = self.csv_rows(self.download("#export-checks"))
        self.assertEqual([json.loads(row["record_json"]) for row in rows], expected)
        self.assertEqual(self.csv_rows(self.download("#export-findings")), [])

    def test_finops_candidates_are_filtered_without_fabricating_cost_or_savings(self):
        snapshot = fixture()
        self.open_report(snapshot)
        self.page.locator("#filter-area").select_option("finops")
        scoped = json.loads(self.download("#export-filtered-json"))
        expected_ids = {check["resource_id"] for check in snapshot["checks"] if check["area"] == "finops"}
        expected = [row for row in snapshot["finops"]["candidates"] if row["resource_id"] in expected_ids]
        self.assertEqual(scoped["finops"]["candidates"], expected)
        self.assertIn("Not evaluated", self.page.locator("#finops-baseline").inner_text())
        self.assertIn("429", self.page.locator("#sources-table").inner_text())
        self.assertIn("To be estimated / Not calculated", self.page.locator("#finops-candidates").inner_text())
        self.assertEqual([json.loads(row["record_json"]) for row in
                          self.csv_rows(self.download("#export-finops"))], expected)
        action_ids = {check["check_id"] for check in scoped["checks"]}
        self.assertEqual(scoped["actions"],
                         [action for action in snapshot["actions"] if action["check_id"] in action_ids])

    def test_structured_metric_windows_and_historical_cost_evidence_are_lossless(self):
        snapshot = fixture(32)
        snapshot["finops"]["window"]["source_metadata"] = {"observed_zero": 0}
        candidates = snapshot["finops"]["candidates"]
        candidates[0].update(
            resource_id=snapshot["inventory"]["node_pools"][0]["resource_id"],
            source_id="arm",
            sample_count=1,
            window={"timestamp": REFERENCE, "duration": "1m4.25s",
                    "source_metadata": {"unit": "cores", "observed_zero": 0}},
        )
        candidates[1]["window"] = [
            {"timestamp": REFERENCE, "duration": "58.125s", "container": "api"},
            {"timestamp": REFERENCE, "duration": "58.125s", "container": "sidecar"},
            {"timestamp": "2026-10-13T12:00:04Z", "duration": "1m3s",
             "source_metadata": {"__proto__": {"literal": True}}},
        ]
        candidates[1]["sample_count"] = 3
        candidates[2]["window"] = None
        snapshot["finops"]["cost_rows"] = [
            {
                "resource_id": f"{BASE}/historical/billed-resource",
                "source_id": "cost",
                "observed_at": REFERENCE,
                "usage_date": None,
                "association": "node_resource_group_billing_context",
                "current_inventory_match": False,
                "cost": 12.5,
                "currency": "EUR",
            }
        ]
        self.open_report(snapshot)
        rows = self.page.locator('table[data-collection="finops-candidates"] tbody tr')
        self.assertIn("Sample window:", rows.nth(0).inner_text())
        self.assertIn("observed duration: 1m4.25s", rows.nth(0).inner_text())
        self.assertIn("Sample windows (3)", rows.nth(1).inner_text())
        self.assertEqual(rows.nth(1).inner_text().count("observed duration: 58.125s"), 2)
        self.assertIn("observed duration: 1m3s", rows.nth(1).inner_text())
        self.assertIn("Not evaluated", rows.nth(2).inner_text())
        self.assertEqual(self.download("#export-json"), safe_fixture_json(snapshot).encode("utf-8"))
        scoped = json.loads(self.download("#export-filtered-json"))
        self.assertEqual(scoped["finops"], snapshot["finops"])
        self.assertEqual(scoped["scores"], snapshot["scores"])
        exported = self.csv_rows(self.download("#export-finops"))
        self.assertEqual([json.loads(row["window"]) for row in exported[:2]],
                         [candidate["window"] for candidate in candidates[:2]])
        self.assertEqual([json.loads(row["record_json"]) for row in exported], candidates)
        self.page.locator('[data-detail-key="finops-receipts"] > summary').click()
        receipt = self.page.locator('table[data-collection="finops:cost_rows"] details').first
        receipt.locator(":scope > summary").click()
        self.assertIn('"usage_date": null', receipt.inner_text())
        self.assertIn('"current_inventory_match": false', receipt.inner_text())
        self.assertIn("node_resource_group_billing_context", receipt.inner_text())

    def test_empty_and_partial_metric_windows_stay_unknown_without_inference(self):
        snapshot = fixture(32)
        candidates = snapshot["finops"]["candidates"]
        candidates[0]["window"] = []
        candidates[1]["window"] = {"timestamp": None, "duration": None, "metadata": {"observed_zero": 0}}
        candidates[2]["window"] = {"start": REFERENCE, "end": None, "metadata": "partial"}
        self.open_report(snapshot)
        rows = self.page.locator('table[data-collection="finops-candidates"] tbody tr')
        self.assertIn("Not evaluated: no sample windows included", rows.nth(0).inner_text())
        self.assertIn("Sample window: Not evaluated / observed duration: Not evaluated", rows.nth(1).inner_text())
        self.assertIn("UTC - Not evaluated", rows.nth(2).inner_text())
        self.assertEqual(json.loads(self.download("#export-json")), snapshot)

    def test_all_unknown_null_index_null_inventory_and_denied_sources(self):
        snapshot = fixture(8)
        for check in snapshot["checks"]:
            check["status"] = "not_evaluated"
            check["evidence"] = []
            check["reason"] = "Sin acceso autorizado: no se ha observado la configuración."
        snapshot["actions"] = []
        snapshot["finops"]["candidates"] = None
        snapshot["inventory"] = {key: None for key in snapshot["inventory"]}
        snapshot["source_data"] = {key: None for key in snapshot["source_data"]}
        for source in snapshot["sources"]:
            source["status"] = "denied"
            source["records"] = None
        refresh_fixture(snapshot)
        self.open_report(snapshot)
        self.assertIn("Not evaluated", self.page.locator("#global-index .score-value").inner_text())
        self.assertEqual(self.page.locator("#area-scores [role=meter]").count(), 0)
        self.assertEqual(self.page.locator("#pillar-scores [role=meter]").count(), 0)
        self.assertIn("Not evaluated node pools", self.page.locator("#inventory-counts").inner_text())
        self.assertIn("Access denied", self.page.locator("#sources-table").inner_text())
        self.assertEqual(self.page.locator(".finding").count(), 0)
        self.assertEqual(json.loads(self.download("#export-json")), snapshot)
        scoped = json.loads(self.download("#export-filtered-json"))
        self.assertEqual(scoped["inventory"], snapshot["inventory"])
        self.assertIsNone(scoped["finops"]["candidates"])

    def test_supplied_zero_is_distinct_from_unknown_and_supplied_scores_are_not_recomputed(self):
        snapshot = fixture(8)
        snapshot["finops"]["currency"] = "EUR"
        snapshot["finops"]["actual_cost"] = 0
        snapshot["finops"]["estimated_savings"] = 0
        snapshot["scores"]["global"]["score"] = 42.5
        snapshot["scores"]["areas"]["security"]["score"] = 37.25
        self.open_report(snapshot)
        self.assertIn("0 EUR", self.page.locator("#finops-baseline").inner_text())
        self.assertEqual(self.page.locator("#global-index .score-value").inner_text(), "42.5 / 100")
        self.assertIn("37.3 / 100", self.page.locator("#area-scores").inner_text())
        self.assertEqual(json.loads(self.download("#export-json")), snapshot)

    def test_verdict_band_and_kpis_are_qualified_and_never_a_healthy_zero(self):
        snapshot = fixture(8)
        self.open_report(snapshot)
        critical = sum(row["severity"] == "critical" for row in snapshot["findings"])
        self.assertGreater(critical, 0)
        self.assertEqual(self.page.locator("#verdict .verdict-value").inner_text(), "Action required")
        self.assertIn(f"{critical} critical", self.page.locator("#verdict").inner_text())
        self.assertIn(f"{len(snapshot['findings'])} findings", self.page.locator("#hero-summary").inner_text())
        self.assertEqual(self.page.locator("#kpis .kpi").count(), 5)
        self.assertIn("Not evaluated", self.page.locator("#kpis").inner_text())
        for check in snapshot["checks"]:
            check.update(status="not_evaluated", evidence=[], reason="Sin acceso autorizado.")
        snapshot["actions"] = []
        refresh_fixture(snapshot)
        self.open_report(snapshot)
        self.assertEqual(self.page.locator("#verdict .verdict-value").inner_text(), "Not evaluated")
        first_kpi = self.page.locator("#kpis .kpi").first
        self.assertEqual(first_kpi.locator(".kpi-value").inner_text(), "Not evaluated")
        self.assertIn("no checks evaluated", first_kpi.inner_text())
        self.assertIn("0 findings supplied", self.page.locator("#severity-distribution").inner_text())

    def test_findings_default_to_severity_order_and_engine_order_is_selectable(self):
        snapshot = fixture(8)
        self.open_report(snapshot)
        rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        for group in self.page.locator(".findings-group").all():
            keys = [row.get_attribute("data-detail-key").removeprefix("finding:") for row in group.locator(".finding").all()]
            severities = [next(row["severity"] for row in snapshot["findings"] if row["check_id"] == key) for key in keys]
            self.assertEqual(severities, sorted(severities, key=rank.get))
        self.page.locator("#findings-order").select_option("model")
        shown = [row.get_attribute("data-detail-key").removeprefix("finding:") for row in self.page.locator(".finding").all()]
        expected = [row["check_id"] for level in ("cluster", "workload", "resource")
                    for row in snapshot["findings"] if row["level"] == level]
        self.assertEqual(shown, expected)
        self.assertEqual([row["check_id"] for row in self.csv_rows(self.download("#export-findings"))],
                         [row["check_id"] for row in snapshot["findings"]])

    def test_print_moves_table_receipts_full_width_without_adding_rows(self):
        snapshot = fixture(8)
        self.open_report(snapshot)
        self.page.evaluate("window.dispatchEvent(new Event('beforeprint'))")
        rows = self.page.locator('table[data-collection="checks"] tbody tr')
        self.assertEqual(rows.count(), len(snapshot["checks"]))
        self.assertEqual(rows.locator("details.receipt").count(), 0)
        receipts = self.page.locator("#checks-table .print-receipts details.receipt")
        self.assertEqual(receipts.count(), len(snapshot["checks"]))
        self.assertEqual(json.loads(receipts.first.locator("pre").inner_text()), snapshot["checks"][0])
        self.page.evaluate("window.dispatchEvent(new Event('afterprint'))")
        self.assertEqual(self.page.locator("#checks-table .print-receipts").count(), 0)

    def test_no_actual_critical_finding_produces_zero_not_a_fake_top_five(self):
        snapshot = fixture(8)
        for check in snapshot["checks"]:
            check["severity"] = "low"
        for action in snapshot["actions"]:
            action["severity"] = "low"
        refresh_fixture(snapshot)
        self.open_report(snapshot)
        self.assertIn("0 recorded", self.page.locator("#critical-title").inner_text())
        self.assertEqual(self.page.locator(".priority-list li").count(), 0)
        self.assertIn("This does not mean there is no risk", self.page.locator("#critical-findings").inner_text())

    def test_top_critical_uses_only_supplied_critical_findings(self):
        snapshot = fixture()
        self.open_report(snapshot)
        critical = [check for check in snapshot["findings"] if check["severity"] == "critical"]
        items = self.page.locator(".priority-list li").all()
        self.assertEqual(len(items), min(5, len(critical)))
        self.assertEqual([item.locator("strong").inner_text() for item in items],
                         [f"{check['check_id']} / {check['title']}" for check in critical[:5]])

    def test_hostile_strings_prototype_keys_surrogates_and_url_allowlist(self):
        snapshot = fixture(8)
        hostile = '</script><script>window.injected=true</script><img src="https://example.invalid/x"> & \u2028 \u2029'
        snapshot["client"]["name"] = hostile
        snapshot["checks"][0]["title"] = hostile
        snapshot["checks"][0]["evidence"][0]["value"] = {
            "__proto__": {"polluted": True}, "literal": hostile,
            "lone_surrogates": ["\ud800", "\udfff"],
        }
        for index, url in enumerate(("javascript:window.injected=true", "https://learn.microsoft.com.example.invalid/en-us/azure/aks/x",
                                      "https://learn.microsoft.com@evil.invalid/en-us/azure/aks/x", "https://example.invalid")):
            snapshot["checks"][index]["learn_url"] = url
        snapshot["literal"] = {"__proto__": {"polluted": True},
                               "constructor": {"prototype": {"polluted": True}},
                               "text": hostile, "surrogates": ["\ud800", "\udfff", "\U0001f600"]}
        refresh_fixture(snapshot)
        self.open_report(snapshot)
        self.assertEqual(self.page.locator("#client-name").text_content(), hostile)
        hostile_finding = self.page.locator('[data-detail-key="finding:UI-000"]')
        self.assertEqual(hostile_finding.locator(".finding-title").text_content(), hostile)
        self.assertIsNone(self.page.evaluate("window.injected"))
        self.assertIsNone(self.page.evaluate("Object.prototype.polluted"))
        self.assertEqual(self.page.locator("script").count(), 2)
        self.assertEqual(self.page.locator("img").count(), 0)
        first = hostile_finding
        first.locator(":scope > summary").click()
        self.assertIn("link not enabled", first.inner_text())
        self.assertEqual(first.locator('a[href^="javascript:"]').count(), 0)
        self.assertEqual(first.locator('a[href*="example.invalid"]').count(), 0)
        self.assertEqual(json.loads(self.download("#export-json")), snapshot)
        self.assertEqual(json.loads(self.download("#export-filtered-json"))["literal"], snapshot["literal"])
        exported = self.csv_rows(self.download("#export-findings"))
        self.assertEqual(json.loads(exported[0]["record_json"]), snapshot["findings"][0])

    def test_csv_formula_cells_are_neutralized_without_losing_record_json(self):
        snapshot = fixture(8)
        formulas = ("=HYPERLINK(\"https://example.invalid\")", " +SUM(1,2)", "@SUM(1,2)", "\t=1+1")
        for index, formula in enumerate(formulas):
            snapshot["checks"][index]["title"] = formula
        refresh_fixture(snapshot)
        self.open_report(snapshot)
        rows = self.csv_rows(self.download("#export-findings"))
        for row, formula in zip(rows, formulas):
            self.assertEqual(row["title"], "'" + formula)
            self.assertEqual(json.loads(row["record_json"])["title"], formula)

    def test_invalid_model_is_explicit_and_never_exposes_partial_results(self):
        baseline = fixture(8)
        mutations = [
            ("schema", lambda value: value.update(schema_version="2.0")),
            ("environment", lambda value: value.pop("environment")),
            ("duplicate", lambda value: value["checks"].append(copy.deepcopy(value["checks"][0]))),
            ("findings", lambda value: value["findings"].pop()),
            ("score", lambda value: value["scores"]["global"].update(evaluated=0, passed=0, failed=0, score=100)),
            ("coverage", lambda value: value["scores"]["areas"]["security"].update(total=-1)),
            ("method", lambda value: value["methodology"].update(official_waf_score=True)),
            ("logo", lambda value: value["client"].update(logo_data_uri="data:image/svg+xml;base64,PHN2Zz4=")),
            ("source", lambda value: value["sources"][0].update(status="healthy")),
            ("candidate", lambda value: value["finops"]["candidates"][0].update(estimated_savings="24%")),
            ("action", lambda value: value["actions"][0].update(owner={"invented": True})),
            ("time", lambda value: value.update(reference_utc="yesterday")),
            ("calendar", lambda value: value.update(reference_utc="2026-02-30T12:00:00Z")),
            ("status_counts", lambda value: value["scores"]["global"].update(
                passed=value["scores"]["global"]["failed"], failed=value["scores"]["global"]["passed"])),
            ("record", lambda value: value["inventory"]["workloads"][0].update(namespace={"invalid": True})),
            ("window_scalar", lambda value: value["finops"]["candidates"][0].update(window="1m4s")),
            ("window_number", lambda value: value["finops"]["candidates"][0].update(window=64)),
            ("window_unrecognized", lambda value: value["finops"]["candidates"][0].update(window={"unknown_field": REFERENCE})),
            ("window_null_sample", lambda value: value["finops"]["candidates"][0].update(window=[None])),
            ("window_nested", lambda value: value["finops"]["candidates"][0].update(window=[[{"timestamp": REFERENCE, "duration": "1m4s"}]])),
            ("window_duration_type", lambda value: value["finops"]["candidates"][0].update(window={"timestamp": REFERENCE, "duration": 64})),
            ("window_timestamp_type", lambda value: value["finops"]["candidates"][0].update(window=[{"timestamp": {"invalid": REFERENCE}, "duration": "1m4s"}])),
        ]
        for name, mutation in mutations:
            with self.subTest(name=name):
                snapshot = copy.deepcopy(baseline)
                mutation(snapshot)
                self.open_report(snapshot, expected="error")
                self.assertTrue(self.page.locator("#report-shell").is_hidden())
                self.assertTrue(self.page.locator("#export-json").is_disabled())
                self.assertEqual(self.page.locator("#opening-state").get_attribute("role"), "alert")
                self.assertIn("No partial results are shown", self.page.locator("#opening-message").inner_text())
                self.assertIn("Ask the generator", self.page.locator("#opening-detail").inner_text())

    def test_optional_inline_raster_brand_is_bounded_and_visible_in_both_themes(self):
        snapshot = fixture(8)
        snapshot["client"]["logo_data_uri"] = (
            "data:image/png;base64,"
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aX1cAAAAASUVORK5CYII="
        )
        snapshot["client"]["logo_alt"] = "Logo de prueba autorizado, no marca de cliente"
        self.open_report(snapshot)
        for theme in ("light", "dark"):
            self.page.locator("#theme-mode").select_option(theme)
            self.assertEqual(self.page.locator("#brand-plaque img").get_attribute("alt"), snapshot["client"]["logo_alt"])
            self.assertEqual(self.page.locator("#brand-plaque").evaluate("element => getComputedStyle(element).backgroundColor"), "rgb(255, 255, 255)")
            scheme = self.page.locator("#brand-plaque").evaluate("element => getComputedStyle(element).colorScheme")
            self.assertEqual(set(scheme.split()), {"light", "only"})
            bounds = self.page.locator("#brand-plaque img").bounding_box()
            self.assertIsNotNone(bounds)
            self.assertLessEqual(bounds["width"], 188)
            self.assertLessEqual(bounds["height"], 56)

    def test_theme_system_preference_local_toggle_and_no_dataset_storage(self):
        snapshot = fixture(8)
        path = self.open_report(snapshot)
        self.page.emulate_media(color_scheme="dark")
        self.page.wait_for_function("() => document.documentElement.dataset.theme === 'dark'")
        self.assertEqual(self.page.locator("html").get_attribute("data-theme"), "dark")
        self.page.locator("#theme-mode").select_option("light")
        self.assertEqual(self.page.locator("html").get_attribute("data-theme"), "light")
        self.page.goto(path.as_uri())
        self.assertEqual(self.page.locator("#theme-mode").input_value(), "light")
        self.assertEqual(self.page.locator("html").get_attribute("data-theme"), "light")
        self.assertEqual(self.page.evaluate("Object.keys(localStorage)"), ["aks-consulting-report-theme"])
        self.assertEqual(json.loads(self.download("#export-json")), snapshot)

    def test_keyboard_skip_focus_labels_and_working_native_filters(self):
        snapshot = fixture(8)
        self.open_report(snapshot)
        self.page.keyboard.press("Tab")
        self.assertTrue(self.page.locator(".skip").evaluate("element => element === document.activeElement"))
        self.assertEqual(self.page.locator(".skip").evaluate("element => getComputedStyle(element).outlineWidth"), "3px")
        self.page.keyboard.press("Enter")
        self.assertTrue(self.page.locator("#main").evaluate("element => element === document.activeElement"))
        self.page.locator("#theme-mode").focus()
        self.assertEqual(self.page.locator("#theme-mode").evaluate("element => getComputedStyle(element).outlineColor"), "rgb(255, 255, 255)")
        self.page.locator("#filter-search").focus()
        self.page.keyboard.type("UI-000")
        self.assertIn("1 matching check of", self.page.locator("#filter-count").inner_text())
        self.assertEqual(self.page.locator(".finding").count(), 1)
        labels = self.page.evaluate("""() => [...document.querySelectorAll('input,select')].map(element => ({
          id: element.id, labels: element.labels.length,
          outline: getComputedStyle(element).outlineStyle
        }))""")
        self.assertTrue(all(item["id"] and item["labels"] for item in labels))
        self.assertEqual(self.page.locator("h1").count(), 2)
        self.assertTrue(self.page.locator("#opening-state").is_hidden())
        self.assertTrue(self.page.locator("#filter-count").get_attribute("aria-live") == "polite")
        for region in self.page.locator(".table-scroll").all():
            self.assertEqual(region.get_attribute("tabindex"), "0")
            self.assertTrue(region.get_attribute("aria-label"))

    def test_print_materializes_all_matches_expands_details_and_restores_reading_state(self):
        snapshot = fixture(42)
        self.open_report(snapshot)
        first = self.page.locator(".finding").first
        first.locator(":scope > summary").click()
        first_key = first.get_attribute("data-detail-key")
        self.page.evaluate("window.dispatchEvent(new Event('beforeprint'))")
        self.page.evaluate("window.dispatchEvent(new Event('beforeprint'))")
        self.assertEqual(self.page.locator(".finding").count(), len(snapshot["findings"]))
        self.assertEqual(self.page.locator('table[data-collection="workloads"] tbody tr').count(), 42)
        self.assertEqual(self.page.locator('table[data-collection="checks"] tbody tr').count(), len(snapshot["checks"]))
        self.assertEqual(self.page.locator("details:not([open])").count(), 0)
        self.assertEqual(self.page.locator("#method-scope > dl").count(), 1)
        self.page.emulate_media(media="print")
        self.assertTrue(self.page.locator(".toolbar").is_hidden())
        self.assertTrue(self.page.locator("#filters-form").is_hidden())
        self.assertTrue(self.page.locator("#print-scope").is_visible())
        self.assertIn("no on-screen page limit", self.page.locator("#print-scope").inner_text())
        self.assertEqual(self.page.locator("#executive").evaluate("element => getComputedStyle(element).breakBefore"), "page")
        pdf = self.page.pdf(format="A4", print_background=True)
        self.assertTrue(pdf.startswith(b"%PDF-"))
        self.assertGreater(len(re.findall(rb"/Type /Page\b", pdf)), 1)
        self.page.evaluate("window.dispatchEvent(new Event('afterprint'))")
        self.page.emulate_media(media="screen")
        self.assertEqual(self.page.locator(".finding").count(), 25)
        self.assertIsNotNone(self.page.locator(f'[data-detail-key="{first_key}"]').get_attribute("open"))
        self.assertEqual(self.page.locator("#method-scope > dl").count(), 1)
        self.assertEqual(json.loads(self.download("#export-json")), snapshot)

    def test_print_respects_selected_scope_but_does_not_truncate_it(self):
        snapshot = fixture()
        self.open_report(snapshot)
        self.page.locator("#filter-namespace").select_option("team-a")
        expected = [row for row in snapshot["findings"] if row["namespace"] == "team-a"]
        self.page.evaluate("window.dispatchEvent(new Event('beforeprint'))")
        self.assertEqual(self.page.locator(".finding").count(), len(expected))
        self.assertIn("namespace team-a", self.page.locator("#print-scope").text_content())
        self.page.evaluate("window.dispatchEvent(new Event('afterprint'))")
        self.assertEqual(json.loads(self.download("#export-filtered-json"))["findings"], expected)

    @unittest.skipUnless(os.environ.get("SRE_REPORT_UI_ACTUAL_MULTI_MODEL"),
                         "A private native multi-cluster snapshot is opt-in and is never distributed.")
    def test_complete_private_multi_model_bootstrap_both_scopes_and_lossless_exports(self):
        path = Path(os.environ["SRE_REPORT_UI_ACTUAL_MULTI_MODEL"])
        source_bytes = path.read_bytes()
        snapshot = json.loads(source_bytes)
        self.assertEqual(snapshot["schema_version"], "aks-waf-multi-cluster-v1")
        self.open_report(snapshot)
        self.assertTrue(self.page.locator("#cluster-overview").is_visible())
        self.assertTrue(self.download("#export-json") == safe_fixture_json(snapshot).encode("utf-8"),
                        "Private multi-cluster export changed the full original embedded document.")
        for run in snapshot["cluster_runs"]:
            self.page.locator("#cluster-selector").select_option(run["cluster_name"])
            model = run["snapshot"]
            if model is None:
                self.assertTrue(self.page.locator("#cluster-error").is_visible())
                self.assertTrue(self.page.locator("#cover").is_hidden())
                continue
            self.assertTrue(self.page.locator("#cover").is_visible())
            self.assertTrue(self.page.locator("#cluster-error").is_hidden())
            self.assertIn(model["cluster"]["name"], self.page.locator("#cover-facts").inner_text())
            self.assertIn(model["cluster"]["power_state"], self.page.locator("#cover-facts").inner_text())
            self.assertEqual(self.page.locator("#area-scores .score-row").count(), 4)
            self.assertEqual(self.page.locator("#pillar-scores .score-row").count(), 5)
            self.assertEqual(self.page.locator(".finding").count(), min(25, len(model["findings"])))
            scoped = json.loads(self.download("#export-filtered-json"))
            self.assertEqual(scoped["aggregate"], snapshot["aggregate"])
            for actual, expected in zip(scoped["cluster_runs"], snapshot["cluster_runs"]):
                self.assertTrue({key: value for key, value in actual.items() if key != "snapshot"} ==
                                {key: value for key, value in expected.items() if key != "snapshot"},
                                "Private scoped export changed run identity/status/reference metadata.")
                if actual["cluster_name"] == run["cluster_name"]:
                    for key, value in expected["snapshot"].items():
                        self.assertTrue(actual["snapshot"].get(key) == value,
                                        f"Private unfiltered snapshot {key} changed.")
                else:
                    self.assertTrue(actual == expected, "Private scoped export changed another cluster's run.")
            self.assertEqual(json.loads(self.download("#export-json")), snapshot)
            self.open_checks()
            self.assertEqual([json.loads(row["record_json"]) for row in self.csv_rows(self.download("#export-checks"))],
                             model["checks"])
            self.assertEqual([json.loads(row["record_json"]) for row in self.csv_rows(self.download("#export-findings"))],
                             model["findings"])
            self.page.evaluate("window.dispatchEvent(new Event('beforeprint'))")
            self.assertEqual(self.page.locator('table[data-collection="checks"] tbody tr').count(), len(model["checks"]))
            self.page.evaluate("window.dispatchEvent(new Event('afterprint'))")
        self.assertEqual(path.read_bytes(), source_bytes, "The captured native source file was modified.")

    @unittest.skipUnless(os.environ.get("SRE_REPORT_UI_ACTUAL_MODEL"),
                         "A private runtime snapshot is opt-in and is never distributed.")
    def test_complete_private_runtime_model_bootstrap_exports_and_responsive_themes(self):
        snapshot_path = Path(os.environ["SRE_REPORT_UI_ACTUAL_MODEL"])
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        self.open_report(snapshot)
        self.assertTrue(self.page.locator("#report-shell").is_visible(),
                        "The complete private model did not render.")
        self.assertEqual(self.page.locator("#area-scores .score-row").count(), 4)
        self.assertEqual(self.page.locator("#pillar-scores .score-row").count(), 5)
        self.assertEqual(self.page.locator(".finding").count(), min(25, len(snapshot["findings"])))
        critical_count = sum(row["severity"] == "critical" for row in snapshot["findings"])
        self.assertEqual(self.page.locator(".priority-list li").count(), min(5, critical_count))
        self.assertIn(f"{snapshot['scores']['global']['evaluated']} evaluated",
                      self.page.locator("#global-index").inner_text())
        self.assertIn(f"{snapshot['scores']['coverage']['not_evaluated']} not evaluated",
                      self.page.locator("#global-coverage").inner_text())
        full_json = self.download("#export-json")
        self.assertTrue(full_json == safe_fixture_json(snapshot).encode("utf-8"),
                        "Private full JSON export did not preserve the exact embedded document.")
        self.assertTrue(json.loads(full_json) == snapshot,
                        "Private full JSON export differs from the original runtime model.")
        scoped = json.loads(self.download("#export-filtered-json"))
        for key in ("inventory", "checks", "findings", "finops", "actions", "scores",
                    "source_data", "sources", "methodology"):
            self.assertTrue(scoped.get(key) == snapshot.get(key),
                            f"Private unfiltered {key} export differs from the complete runtime model.")
        for key in ("node_pools", "namespaces", "workloads", "related_resources"):
            records = snapshot["inventory"][key]
            expected = min(25, len(records)) if records is not None else 0
            self.assertEqual(self.page.locator(f'table[data-collection="{key}"] tbody tr').count(), expected)
        self.open_checks()
        exports = {
            "checks": self.csv_rows(self.download("#export-checks")),
            "findings": self.csv_rows(self.download("#export-findings")),
            "candidates": self.csv_rows(self.download("#export-finops")),
            "actions": self.csv_rows(self.download("#export-actions")),
        }
        for key, rows in exports.items():
            expected = snapshot["finops"]["candidates"] if key == "candidates" else snapshot[key]
            self.assertTrue([json.loads(row["record_json"]) for row in rows] == (expected or []),
                            f"Private complete {key} CSV lost records or source evidence.")
        inventory = self.csv_rows(self.download("#export-inventory"))
        expected_inventory = [(key, row) for key, records in snapshot["inventory"].items()
                              if records is not None for row in records]
        self.assertTrue([(row["collection"], json.loads(row["record_json"])) for row in inventory]
                        == expected_inventory, "Private inventory CSV omitted complete source records.")
        candidates = snapshot["finops"]["candidates"] or []
        if len(candidates) > 25:
            self.page.locator('[data-more-collection="finops-candidates"]').click()
            self.assertEqual(self.page.locator('table[data-collection="finops-candidates"] tbody tr').count(),
                             min(50, len(candidates)))
        if snapshot["client"].get("logo_data_uri"):
            self.page.wait_for_function("() => document.querySelector('#brand-plaque img')?.complete")
            self.assertTrue(self.page.locator("#brand-plaque img").evaluate("image => image.naturalWidth > 0"),
                            "The private inline logo failed to load.")
        for width, height in ((1440, 1000), (390, 844), (320, 844)):
            self.page.set_viewport_size({"width": width, "height": height})
            for theme in ("light", "dark"):
                self.page.locator("#theme-mode").select_option(theme)
                self.assertEqual(self.page.locator("html").get_attribute("data-theme"), theme)
                self.assertLessEqual(self.page.evaluate("document.documentElement.scrollWidth"), width)
                self.assertTrue(self.page.locator("#report-shell").is_visible())
                audit = self.page.evaluate(CONTRAST_AUDIT)
                self.assertTrue(not audit["issues"],
                                f"Private model has a text contrast defect at {width}px / {theme}.")
                self.assertTrue(self.page.locator("#brand-plaque").is_visible(),
                                "The private model's client plaque is not visible.")
        self.page.set_viewport_size({"width": 1440, "height": 1000})
        namespace_rows = snapshot["inventory"]["namespaces"] or []
        if namespace_rows:
            namespace = max(namespace_rows,
                            key=lambda row: sum(check.get("namespace") == row.get("name")
                                                for check in snapshot["checks"]))["name"]
            self.page.locator("#filter-namespace").select_option(namespace)
            selected = json.loads(self.download("#export-filtered-json"))
            self.assertTrue(selected["checks"] == [row for row in snapshot["checks"]
                                                  if row.get("namespace") == namespace],
                            "Private namespace filter lost or mixed full-model checks.")
            self.assertTrue(selected["inventory"]["workloads"] == [
                row for row in snapshot["inventory"]["workloads"] or []
                if row.get("namespace") == namespace
            ], "Private namespace filter lost or mixed observed workloads.")
            self.assertTrue(selected["scores"] == snapshot["scores"],
                            "Private namespace navigation changed the supplied scores.")
            if selected["inventory"]["workloads"]:
                workload = selected["inventory"]["workloads"][0]
                self.page.locator('#workloads button[data-drilldown="workloads"]').first.click()
                selected_workload = json.loads(self.download("#export-filtered-json"))
                self.assertTrue(selected_workload["inventory"]["workloads"] == [workload],
                                "Private workload drilldown mixed Kubernetes object identities.")
                self.assertTrue(all(row.get("namespace") == workload.get("namespace")
                                    and row.get("workload_name") == workload.get("name")
                                    for row in selected_workload["checks"]),
                                "Private workload drilldown mixed namespace or workload names.")
            self.page.locator("#reset-filters").click()
        self.page.evaluate("window.dispatchEvent(new Event('beforeprint'))")
        self.assertEqual(self.page.locator(".finding").count(), len(snapshot["findings"]))
        self.assertEqual(self.page.locator('table[data-collection="checks"] tbody tr').count(),
                         len(snapshot["checks"]))
        self.assertEqual(self.page.locator("details:not([open])").count(), 0)
        self.page.evaluate("window.dispatchEvent(new Event('afterprint'))")
        self.assertTrue(json.loads(self.download("#export-json")) == snapshot,
                        "Private full-model print lifecycle changed the original data.")
        self.assertEqual(self.external, [])
        self.assertEqual(self.errors, [])

    def test_batched_desktop_mobile_light_dark_print_geometry_and_contrast(self):
        snapshot = architecture_fixture(8)
        self.open_report(snapshot)
        artifact_setting = os.environ.get("SRE_REPORT_UI_ARTIFACT_DIR")
        artifact_dir = Path(artifact_setting).resolve() if artifact_setting else None
        if artifact_dir:
            artifact_dir.mkdir(parents=True, exist_ok=True)
        measurements, issues = [], []
        for width, height, theme in (
            (1440, 1000, "light"), (1440, 1000, "dark"),
            (390, 844, "light"), (390, 844, "dark"),
            (320, 844, "light"), (320, 844, "dark"),
        ):
            with self.subTest(width=width, theme=theme):
                self.page.set_viewport_size({"width": width, "height": height})
                self.page.locator("#theme-mode").select_option(theme)
                self.page.evaluate("window.scrollTo(0, 0)")
                geometry = self.page.evaluate("""() => ({
                  width: innerWidth, scrollWidth: document.documentElement.scrollWidth,
                  clientWidth: document.documentElement.clientWidth,
                  theme: document.documentElement.dataset.theme,
                  font: getComputedStyle(document.body).fontFamily,
                  plaque: document.querySelector('.brand-plaque').getBoundingClientRect().toJSON(),
                  reference: [...document.querySelectorAll('.cover-facts dt')].find(node => node.textContent === 'UTC reference').parentElement.getBoundingClientRect().toJSON()
                })""")
                if geometry["scrollWidth"] > geometry["width"]:
                    issues.append({"scene": f"{width}-{theme}", "overflow": geometry["scrollWidth"]})
                if "Segoe UI" not in geometry["font"] or geometry["theme"] != theme:
                    issues.append({"scene": f"{width}-{theme}", "font_or_theme": geometry})
                plaque, reference = geometry["plaque"], geometry["reference"]
                if (plaque["left"] < reference["right"] and plaque["right"] > reference["left"]
                        and plaque["top"] < reference["bottom"] and plaque["bottom"] > reference["top"]):
                    issues.append({"scene": f"{width}-{theme}", "brand_reference_overlap": True})
                audit = self.page.evaluate(CONTRAST_AUDIT)
                if audit["measured"] <= 80 or audit["issues"]:
                    issues.append({"scene": f"{width}-{theme}", "contrast": audit})
                measurements.append({"scene": f"{width}-{theme}", "geometry": geometry, "contrast": audit})
                if artifact_dir:
                    self.page.screenshot(path=str(artifact_dir / f"{width}-{theme}.png"))
                    self.page.locator("#assessment-chart").screenshot(path=str(artifact_dir / f"assessment-{width}-{theme}.png"))
                    self.page.locator("#architecture-observed").screenshot(path=str(artifact_dir / f"architecture-{width}-{theme}.png"))
                    self.page.locator("#finops-baseline").screenshot(path=str(artifact_dir / f"finops-{width}-{theme}.png"))
                self.page.locator("#architecture-reference-tab").click()
                reference_audit = self.page.evaluate(CONTRAST_AUDIT)
                if reference_audit["issues"]:
                    issues.append({"scene": f"reference-{width}-{theme}", "contrast": reference_audit})
                if self.page.evaluate("document.documentElement.scrollWidth") > width:
                    issues.append({"scene": f"reference-{width}-{theme}", "overflow": True})
                if artifact_dir:
                    self.page.locator("#architecture-reference").screenshot(path=str(artifact_dir / f"reference-{width}-{theme}.png"))
                self.page.locator("#architecture-observed-tab").click()
        self.page.set_viewport_size({"width": 1440, "height": 1000})
        self.page.locator("#theme-mode").select_option("light")
        if artifact_dir:
            self.page.locator("#executive").screenshot(path=str(artifact_dir / "executive-light.png"))
            self.page.locator(".finding").first.locator(":scope > summary").click()
            self.page.locator(".finding").first.screenshot(path=str(artifact_dir / "finding-evidence-light.png"))
        self.page.evaluate("window.dispatchEvent(new Event('beforeprint'))")
        self.page.emulate_media(media="print")
        self.page.set_viewport_size({"width": 794, "height": 1123})
        self.page.evaluate("window.scrollTo(0, 0)")
        print_width = self.page.evaluate("document.documentElement.scrollWidth")
        if print_width > 794:
            issues.append({"scene": "print", "overflow": print_width})
        print_audit = self.page.evaluate(CONTRAST_AUDIT)
        if print_audit["issues"]:
            issues.append({"scene": "print", "contrast": print_audit})
        if self.page.locator("details:not([open])").count():
            issues.append({"scene": "print", "closed_disclosures": True})
        if artifact_dir:
            self.page.screenshot(path=str(artifact_dir / "print-a4.png"))
            self.page.pdf(path=str(artifact_dir / "synthetic-report-a4.pdf"), format="A4", print_background=True)
            (artifact_dir / "browser-measurements.json").write_text(
                json.dumps({"provenance": "SIMULATED", "environment": "LAB",
                            "snapshot_sha256": digest(snapshot), "html_bytes": len(embed_fixture(snapshot).encode("utf-8")),
                            "scenes": measurements, "print_contrast": print_audit,
                            "external_requests": self.external, "page_errors": self.errors, "issues": issues},
                           ensure_ascii=True, indent=2), encoding="utf-8"
            )
        self.page.evaluate("window.dispatchEvent(new Event('afterprint'))")
        self.page.emulate_media(media="screen")
        self.assertEqual(issues, [])


if __name__ == "__main__":
    unittest.main()

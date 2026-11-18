"""Local tests for sre-usecase-builder-kit: every recipe must scaffold to READY with a passing self_test."""
import copy
import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("kit", ROOT.parent / "manifests" / "tools" / "sre-usecase-builder-kit.py")
kit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kit)
os.environ.pop("AZURE_CLIENT_ID", None)
FILL = {"<workspace customerId>": "00000000-0000-0000-0000-000000000001", "<subscription id>": "00000000-0000-0000-0000-000000000002"}


def fill(obj):
    if isinstance(obj, dict):
        return {k: fill(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [fill(v) for v in obj]
    if isinstance(obj, str):
        for a, b in FILL.items():
            obj = obj.replace(a, b)
        obj = obj.replace("https://<tenant>.sharepoint.com/sites/<site>", "https://contoso.sharepoint.com/sites/ops")
        obj = obj.replace("<library folder, e.g. Shared Documents/Certificates>", "Certificates").replace("<folder for reports>", "Reports/certs")
    return obj


failures = 0
work = Path(tempfile.mkdtemp(prefix="kit-test-"))
os.chdir(work)
cat = kit.main("catalog")
assert cat["status"] == "OK" and len(cat["recipes"]) >= 6
BUDGET = 4000


def budget(label, res):
    global failures
    size = len(json.dumps(res, ensure_ascii=False, default=str))
    if size > BUDGET:
        failures += 1
        print(f"FAIL budget {label}: {size} chars")
    return size


print(f"PASS catalog index {budget('catalog', cat)} chars")
for topic in ["spec", "operators", "graph", "sharepoint_file", "all", "nope"]:
    budget("catalog " + topic, kit.main("catalog", topic))
recipes = []
for item in cat["recipes"]:
    detail = kit.main("catalog", item["name"])
    budget("catalog " + item["name"], detail)
    recipes.append({"name": item["name"], "spec": detail["spec"]})
for recipe in recipes:
    for variant, s in (("raw", copy.deepcopy(recipe["spec"])), ("filled", fill(copy.deepcopy(recipe["spec"])))):
        r = kit.main("scaffold", json.dumps(s))
        size = budget(f"scaffold {recipe['name']}", r)
        ok = r["status"] in ("READY", "READY_WITH_INPUTS")
        if variant == "filled" and r["status"] != "READY":
            ok = False
        fired = r.get("verification", {}).get("self_test", "")
        print(f"{'PASS' if ok else 'FAIL'} {recipe['name']:28s} {variant:6s} {r['status']:18s} {size:5d}ch {fired[:90]}")
        if not ok:
            failures += 1
            print(json.dumps({k: r.get(k) for k in ("errors", "stage", "self_test", "lint", "verification")}, indent=1, default=str)[:3000])
        for w in r.get("warnings", []):
            if "never fired" in w:
                print("   WARN", w)
# get: every part fits and pages reassemble the full content
name = recipes[1]["spec"]["name"]
for part in kit.GET_PARTS:
    first = kit.main("get", f"{name}/{part}")
    budget(f"get {part}", first)
    text, pages = first.get("content", ""), first.get("pages", 0)
    for p in range(2, pages + 1):
        nxt = kit.main("get", f"{name}/{part}/{p}")
        budget(f"get {part}/{p}", nxt)
        text += nxt["content"]
    ok = first["status"] == "OK" and len(text) > 20
    if part == "code":
        ok = ok and text == (work / "sre-usecase-builder" / name / f"run-{name}.py").read_text(encoding="utf-8")
    failures += not ok
    print(f"{'PASS' if ok else 'FAIL'} get {part:12s} pages={pages} chars={len(text)}")
bad_get = kit.main("get", "nope/answer")
failures += bad_get["status"] != "NOT_FOUND"
# generated guides describe today's portal (Build + configure > Agent Canvas), not the retired Builder and Settings paths
folder = work / "sre-usecase-builder" / name
docs = [(folder / f"{name}-{kind}.md").read_text(encoding="utf-8") for kind in ("SETUP", "BUILDER-BLOCKS")]
docs.append(kit._answer_md(json.loads((folder / f"{name}-scaffold.json").read_text(encoding="utf-8"))))
stale = sorted({old for old in ("Builder >", "Settings >", "Custom Agent", "Create (arrow)", "/agent " + name) for d in docs if old in d})
ok = not stale and all("Build + configure > Agent Canvas" in d for d in docs)
failures += not ok
print(f"{'PASS' if ok else 'FAIL'} SETUP, BUILDER-BLOCKS and answer use today's portal labels {stale}")
# lint negative cases
bad = {"eval": "def main(x: str = ''):\n    return eval(x)\n",
       "delete": "import requests\ndef main(x: str = ''):\n    return requests.delete('https://management.azure.com/x').status_code\n",
       "method": "import requests\ndef main(x: str = ''):\n    return requests.request('DELETE', 'https://x').status_code\n",
       "nodefault": "def main(x: str):\n    return {}\n",
       "secret": "def main(x: str = ''):\n    client_" "secret = 'abcdefghijklmnop'\n    return {}\n",
       "subprocess": "import subprocess\ndef main(x: str = ''):\n    return {}\n"}
for label, code in bad.items():
    res = kit.main("lint", code=code)
    ok = res["status"] == "FAIL"
    failures += not ok
    print(f"{'PASS' if ok else 'FAIL'} lint-negative {label}: {res['errors'][:1]}")
good = kit.main("lint", code="import requests\ndef main(mode: str = 'report') -> dict:\n    return {'q': \"AzureActivity | where OperationNameValue endswith '/DELETE'\"}\n")
failures += good["status"] != "PASS"
print(f"{'PASS' if good['status'] == 'PASS' else 'FAIL'} lint-positive read-only query mentioning DELETE")
inv = kit.main("scaffold", json.dumps({"name": "X", "sources": [{"id": "a", "type": "nope"}], "rules": [{"id": "r", "dataset": "b", "when": {"field": "f", "op": "zz"}}]}))
failures += inv["status"] != "INVALID"
print(f"{'PASS' if inv['status'] == 'INVALID' else 'FAIL'} invalid spec -> {len(inv.get('errors', []))} errors with fixes")
# the portal's Tool Name takes 36 characters: names over 32 are rejected (the tool is run-<name>) with a shorter suggestion
long_spec = dict(fill(copy.deepcopy(recipes[0]["spec"])), name="unattached-public-ip-addresses-cost")
long_res = kit.main("scaffold", json.dumps(long_spec))
name_err = next((e for e in long_res.get("errors", []) if e["path"] == "name"), {})
suggested = name_err.get("fix", "").rsplit("e.g. ", 1)[-1]
_, edge_meta, edge_errors, _ = kit._validate(dict(long_spec, name="a" * 32))
ok = (long_res["status"] == "INVALID" and "36-character" in name_err.get("error", "") and suggested == "unattached-public-ip-addresses"
      and not edge_errors and len(edge_meta["tool"]) == 36)
failures += not ok
print(f"{'PASS' if ok else 'FAIL'} tool name limit: 35-char name rejected (suggests {suggested}), 32-char name gives a 36-char tool")
# KPI aggregation alias written by the model ("aggregation" instead of "agg") must be normalized, not silently ignored
alias_spec = {"name": "kpi-alias-check", "description": "alias", "sources": [{"id": "rows", "type": "resource_graph", "query": "resources | project id, resourceGroup",
              "sample_rows": [{"id": "a", "resourceGroup": "rg1"}, {"id": "b", "resourceGroup": "rg1"}, {"id": "c", "resourceGroup": "rg2"}]}],
              "kpis": [{"id": "groups", "label": "Groups", "dataset": "rows", "aggregation": "distinct", "field": "resourceGroup"}],
              "rules": [{"id": "any", "dataset": "rows", "severity": "low", "when": {"field": "id", "op": "not_empty"}}], "keys": {"rows": ["id"]}}
alias_res = kit.main("scaffold", json.dumps(alias_spec))
alias_code = (work / "sre-usecase-builder" / "kpi-alias-check" / "run-kpi-alias-check.py").read_text(encoding="utf-8")
ok = alias_res["status"] in ("READY", "READY_WITH_INPUTS") and "'agg': 'distinct'" in alias_code and "'aggregation'" not in alias_code
failures += not ok
print(f"{'PASS' if ok else 'FAIL'} kpi alias 'aggregation' normalized to 'agg'")
# ---------- report design: brand palette, logo sanitising, charts, font, PDF
from collections import Counter
il = kit._brand_palette(Counter({"#0077c8": 13, "#0b4272": 8, "#0094f6": 5, "#1b2a37": 12, "#ffd100": 2}), Counter({"#0077c8": 2, "#ffd100": 1}))
ok = il and il["primary"] == "#0b4272" and il["accent"] == "#ffd100"
failures += not ok
print(f"{'PASS' if ok else 'FAIL'} brand palette (navy hero + yellow accent) -> {il and (il['primary'], il['accent'])}")
vs = kit._brand_palette(Counter({"#ff0033": 226, "#ed002f": 35, "#ab192d": 34, "#262626": 44}), Counter({"#ed002f": 5}))
ok = vs and vs["primary"] == "#ff0033" and vs["dark"] is None
failures += not ok
print(f"{'PASS' if ok else 'FAIL'} brand palette (bright red -> light hero) -> {vs and (vs['primary'], vs['accent'], vs['dark'])}")
dirty = b'<svg xmlns="http://www.w3.org/2000/svg" width="40" height="20" onload="alert(1)"><script>alert(2)</script><a href="javascript:x"><rect width="40" height="20" fill="#ff0000"/></a><image href="https://evil/x.png"/></svg>'
clean = kit._svg_clean(dirty) or ""
ok = clean and "script" not in clean and "onload" not in clean and "javascript" not in clean and "evil" not in clean and 'viewBox="0 0 40 20"' in clean
failures += not ok
print(f"{'PASS' if ok else 'FAIL'} svg sanitiser strips scripts, handlers and external refs")
failures += kit._svg_clean(b'<!DOCTYPE x [<!ENTITY a "b">]><svg xmlns="http://www.w3.org/2000/svg"/>') is not None
import socket
import requests
from unittest import mock


class _Redirect:
    status_code, headers = 302, {"Location": "https://10.0.0.5/admin"}

    def close(self):
        pass


fake_dns = lambda host, *a, **k: [(0, 0, 0, "", ("10.0.0.5" if host.startswith("10.") else "93.184.216.34", 443))]
with mock.patch.object(socket, "getaddrinfo", fake_dns), mock.patch.object(requests, "get", return_value=_Redirect()) as got:
    try:
        kit._brand_get("https://www.contoso-example.com/")
        ok = False
    except ValueError as exc:
        ok = "public https" in str(exc) and got.call_count == 1
failures += not ok
print(f"{'PASS' if ok else 'FAIL'} brand fetch refuses a redirect to a private address before requesting it")
design_spec = fill(copy.deepcopy(next(r["spec"] for r in recipes if r["name"] == "entra-app-secrets-expiry")))
design_spec.update(name="design-check", language="es", brand={"name": "Contoso Salud", "primary": "#0b4272", "accent": "#ffd100", "font": "nunito"})
res = kit.main("scaffold", json.dumps(design_spec))
html_files = sorted((work / "run-design-check").glob("selftest-*.html"))
page = html_files[-1].read_text(encoding="utf-8") if html_files else ""
checks = {"status READY": res.get("status") == "READY", "font embedded": "@font-face{font-family:'Nunito Sans'" in page,
          "brand colours": "--hero-stripe:#ffd100" in page and "#0b4272" in page, "charts rendered": "Secrets by days to expiry" in page and "\u2264 30" in page,
          "csp": "Content-Security-Policy" in page, "interactive register": "class='card dt" in page and "data-sev='critical'" in page,
          "spanish ui": "Hallazgos por regla" in page, "labels": ">Days left<" in page, "design summary": res.get("design", {}).get("font") == "nunito"}
for label, cond in checks.items():
    failures += not cond
    print(f"{'PASS' if cond else 'FAIL'} design {label}")
pdfs = sorted((work / "run-design-check").glob("selftest-*.pdf"))
print(f"INFO pdf rendered locally: {bool(pdfs)} ({res.get('verification', {}).get('self_test', '')[-60:]})")
logo = "data:image/svg+xml;base64," + __import__("base64").b64encode(clean.encode()).decode()
cfg, meta, errs, _ = kit._validate(design_spec)
code = kit._build_code(cfg, meta, logo)
ok = "BRAND_LOGO = (" in code and kit._lint(code)["status"] == "PASS"
failures += not ok
print(f"{'PASS' if ok else 'FAIL'} logo embedded as BRAND_LOGO and lint PASS")
bad_chart = dict(design_spec, charts=[{"dataset": "secrets"}, {"dataset": "nope", "by": "x"}, {"dataset": "secrets", "by": "x", "agg": "sum"}])
inv = kit.main("scaffold", json.dumps(bad_chart))
ok = inv["status"] == "INVALID" and len([e for e in inv["errors"] if e["path"].startswith("charts")]) >= 3
failures += not ok
print(f"{'PASS' if ok else 'FAIL'} invalid charts rejected with fixes")
hb = fill(copy.deepcopy(next(r["spec"] for r in recipes if r["name"] == "vm-heartbeat-gaps")))
hb.update(name="hb-check", language="es")
hb["rules"].insert(0, {"id": "silent_7d", "dataset": "heartbeat", "severity": "critical", "title": "Silent > 7 days",
                       "when": {"field": "HoursSilent", "op": "gt", "value": 168}, "message": "{Computer} silent for {HoursSilent} h"})
res = kit.main("scaffold", json.dumps(hb))
page = sorted((work / "run-hb-check").glob("selftest-*.html"))[-1].read_text(encoding="utf-8")
ok = "3/3 rules fired" in res.get("verification", {}).get("self_test", "") and "LastHeartbeat-0" not in page and "OSType-" not in page
failures += not ok
print(f"{'PASS' if ok else 'FAIL'} self_test spreads stacked thresholds and types columns by name -> {res.get('verification', {}).get('self_test', '')[:90]}")
cfg, meta, errs, _ = kit._validate(hb)
tool = {"__name__": "tool"}
exec(compile(kit._build_code(cfg, meta, ""), "tool.py", "exec"), tool)
arm = "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/rg-web/providers/Microsoft.Compute/disks/web-01_OsDisk"
cell = tool["_item_td"]({"item": arm, "name": "web-01_OsDisk"})
checks = {"register shows ARM item as name + group + portal link": "rg-web" in cell and "portal.azure.com" in cell and "class='mono'" not in cell,
          "chart label shortens resource types": tool["_short_label"]("microsoft.compute/virtualmachines/extensions") == "virtualmachines/extensions"
          and tool["_short_label"]("rg-web") == "rg-web",
          "long tokens get break points": tool["_breakable"]("microsoft.network/networksecuritygroups") == "microsoft.<wbr>network/<wbr>networksecuritygroups"}
for label, cond in checks.items():
    failures += not cond
    print(f"{'PASS' if cond else 'FAIL'} {label}")
# ---------- environment: principal (object) id of the agent identity with and without the oid claim
# Since November 2026 the sandbox sidecar hands out placeholder tokens without oid; the id is looked up instead.
import base64
import types

CID, TID, SUB = "00000000-0000-0000-0000-0000000000c1", "00000000-0000-0000-0000-0000000000d1", "00000000-0000-0000-0000-000000000002"
SIDECAR = {"iss": "adc-msi-sidecar", "cid": CID, "clientId": CID, "kind": "msi", "scp": "user_impersonation", "iat": 1, "exp": 2, "tid": TID}
AGENTS = f"/subscriptions/{SUB}/resourceGroups/rg-agent/providers/Microsoft.App/agents/"
P = {n: f"00000000-0000-0000-0000-0000000000a{n}" for n in range(1, 6)}


class _Resp:
    def __init__(self, status, body):
        self.status_code, self._body, self.text = status, body, json.dumps(body)

    def json(self):
        return self._body


def run_environment(claims, uami=(), agents=(), sami=None, graph=None):
    calls = []

    def fake_request(method, url, **kw):
        query = (kw.get("json") or {}).get("query", "")
        calls.append(f"{url} {query}")
        if "/subscriptions?" in url:
            return _Resp(200, {"value": [{"subscriptionId": SUB, "displayName": "lab"}]})
        if "Microsoft.ResourceGraph" in url:
            return _Resp(200, {"data": list(uami) if "userassignedidentities" in query else list(agents) if "microsoft.app/agents" in query else []})
        if "/identities/default" in url:
            return _Resp(200, {"properties": (sami or {}).get(url.split("/providers/Microsoft.ManagedIdentity")[0].rsplit("/", 1)[-1], {})})
        if "roleAssignments" in url:
            return _Resp(200, {"value": [{"properties": {"roleDefinitionId": "/providers/Microsoft.Authorization/roleDefinitions/r1", "scope": f"/subscriptions/{SUB}"}}]})
        if "roleDefinitions" in url:
            return _Resp(200, {"properties": {"roleName": "Reader"}})
        if "servicePrincipals" in url:
            return _Resp(200, {"value": graph}) if graph else _Resp(403, {"error": {"code": "Authorization_RequestDenied"}})
        return _Resp(404, {"error": url})

    token = ".".join(base64.urlsafe_b64encode(json.dumps(part).encode()).decode().rstrip("=") for part in ({"alg": "none"}, claims, {}))
    identity = types.ModuleType("azure.identity")
    identity.ManagedIdentityCredential = lambda client_id: types.SimpleNamespace(get_token=lambda scope: types.SimpleNamespace(token=token))
    with mock.patch.dict(sys.modules, {"azure.identity": identity}), mock.patch.dict(os.environ, {"AZURE_CLIENT_ID": CID}), \
            mock.patch.object(requests, "request", fake_request):
        return kit._environment(), calls


env_cases = [  # label, token claims, lookup data, expected principal_id and principal_id_source
    ("token with oid (older platforms)", {"aud": kit.ARM, "oid": P[1], "tid": TID}, {}, P[1], "token"),
    ("sidecar token, user-assigned identity found in Resource Graph", SIDECAR, {"uami": [{"principalId": P[2]}]}, P[2], "resource_graph"),
    ("sidecar token, system-assigned identity confirmed through ARM", SIDECAR,
     {"agents": [{"id": AGENTS + "other", "identity": {"type": "SystemAssigned", "principalId": P[5]}},
                 {"id": AGENTS + "mine", "identity": {"type": "SystemAssigned", "principalId": P[3]}}],
      "sami": {"other": {"clientId": "00000000-0000-0000-0000-0000000000c2", "principalId": P[5]}, "mine": {"clientId": CID, "principalId": P[3]}}},
     P[3], "resource_graph"),
    ("sidecar token, service principal found in Microsoft Graph", SIDECAR, {"graph": [{"id": P[4]}]}, P[4], "graph"),
    ("sidecar token without tid, identity not visible", {k: v for k, v in SIDECAR.items() if k != "tid"}, {}, None, None),
]
for label, claims, lookups, principal, source in env_cases:
    env, calls = run_environment(claims, **lookups)
    ident = env.get("identity") or {}
    listed = [c for c in calls if "assignedTo(" in c]
    ok = (ident.get("principal_id"), ident.get("principal_id_source")) == (principal, source) and not any("assignedTo('None')" in c for c in calls)
    if principal:
        ok = ok and env["status"] == "OK" and bool(listed) and all(f"assignedTo('{principal}')" in c for c in listed) \
            and env["azure_roles"] == [{"role": "Reader", "scope": f"/subscriptions/{SUB}"}]
    else:
        ok = ok and env["status"] == "PARTIAL" and not listed and env["azure_roles"] == [] and ident.get("tenant_id") is None \
            and any(e.startswith("principal_id unknown") for e in env["errors"])
    if source == "token":
        ok = ok and ident.get("tenant_id") == TID and not any("userassignedidentities" in c or "servicePrincipals" in c for c in calls)
    budget("environment " + label, kit._env_summary(env))
    failures += not ok
    print(f"{'PASS' if ok else 'FAIL'} environment {label} -> principal_id {ident.get('principal_id')} ({ident.get('principal_id_source')})")
print("work dir:", work)
print("FAILURES:", failures)
sys.exit(1 if failures else 0)

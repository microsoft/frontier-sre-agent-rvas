"""Report-mode tests of generated tools with a mocked HTTP layer (no Azure): sources, explode, paging, publish, history diff, errors."""
import importlib.util
import io
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from openpyxl import Workbook

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("kit", ROOT.parent / "manifests" / "tools" / "sre-usecase-builder-kit.py")
kit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kit)
os.chdir(tempfile.mkdtemp(prefix="kit-report-"))
NOW = datetime.now(timezone.utc)
failures = 0


def check(label, cond, detail=""):
    global failures
    failures += not cond
    print(f"{'PASS' if cond else 'FAIL'} {label}" + (f" -> {detail}" if detail and not cond else ""))


class Resp:
    def __init__(self, status, body=None, content=None):
        self.status_code, self._body, self.headers = status, body, {}
        self.content = content if content is not None else json.dumps(body or {}).encode()
        self.text = self.content[:300].decode("utf-8", "ignore")

    def json(self):
        return self._body if self._body is not None else json.loads(self.content)


class FakeRequests:
    class RequestException(Exception):
        pass

    def __init__(self, handler):
        self.handler, self.calls = handler, []

    def request(self, method, url, **kw):
        self.calls.append((method, url))
        return self.handler(method, url, kw)

    def put(self, url, **kw):
        return self.request("PUT", url, **kw)


def tool(recipe_name, mutate=None):
    s = json.loads(json.dumps(next(r["spec"] for r in kit.RECIPES if r["name"] == recipe_name)))
    if mutate:
        mutate(s)
    config, meta, errors, _ = kit._validate(s)
    assert not errors, errors
    return kit._build_code(config, meta)


def load(code, handler):
    ns = kit._load(code, offline=False)
    fake = FakeRequests(handler)
    ns["requests"], ns["_token"] = fake, (lambda scope: "token")
    return ns, fake


# ---------- SharePoint Excel register: read + publish + history across two runs
drive = {}


def xlsx(rows):
    wb, buf = Workbook(), io.BytesIO()
    ws = wb.active
    ws.append(["Certificate", "Owner", "ExpiryDate"])
    for r in rows:
        ws.append(r)
    wb.save(buf)
    return buf.getvalue()


def sp_handler(method, url, kw):
    if re.search(r"/v1\.0/sites/contoso\.sharepoint\.com:/sites/ops$", url):
        return Resp(200, {"id": "site-1"})
    m = re.search(r"/sites/site-1/drive/root:/(.+?):/children", url)
    if m and method == "GET":
        folder = m.group(1).replace("%20", " ").strip("/")
        items = [{"id": p, "name": p.rsplit("/", 1)[-1], "file": {}, "lastModifiedDateTime": meta["t"], "webUrl": "https://sp/" + p}
                 for p, meta in drive.items() if p.rsplit("/", 1)[0] == folder]
        return Resp(200, {"value": items}) if items or any(p.startswith(folder + "/") for p in drive) else Resp(404, {"error": "nf"})
    m = re.search(r"/drive/items/(.+)/content$", url)
    if m:
        return Resp(200, content=drive[m.group(1)]["data"])
    m = re.search(r"/drive/root:/(.+):/content$", url)
    if m and method == "PUT":
        drive[m.group(1)] = {"data": kw["data"], "t": NOW.isoformat()}
        return Resp(201, {"webUrl": "https://sp/" + m.group(1)})
    return Resp(500, {"error": url})


soon, past, far = (NOW + timedelta(days=10)).date().isoformat(), (NOW - timedelta(days=3)).date().isoformat(), (NOW + timedelta(days=200)).date().isoformat()
drive["Certificates/certs-2026.xlsx"] = {"data": xlsx([["web-prod", "ana", soon], ["vpn", "", past], ["api", "luis", far]]), "t": "2026-10-01T00:00:00Z"}
code = tool("sharepoint-excel-register", lambda s: [s["sources"][0].update(site_url="https://contoso.sharepoint.com/sites/ops", folder="Certificates"),
                                                   s["publish"]["sharepoint"].update(site_url="https://contoso.sharepoint.com/sites/ops", folder="Reports/certs")])
ns, fake = load(code, sp_handler)
r1 = ns["main"](mode="report", publish="yes")
check("sharepoint run1 status OK", r1["status"] == "OK", r1)
check("sharepoint run1 history empty (first run)", r1["history"] == "empty", r1["history"])
check("sharepoint run1 findings critical+high+low", (r1["findings_by_severity"]["critical"], r1["findings_by_severity"]["high"], r1["findings_by_severity"]["low"]) == (1, 1, 1), r1["findings_by_severity"])
expected = 5 if r1.get("pdf") == "OK" else 4
check(f"sharepoint run1 published {expected} files incl. PDF (when rendered) and history",
      sum(p["status"] == "OK" for p in r1["published"]) == expected and any("history/" in p["file"] for p in r1["published"])
      and (r1.get("pdf") != "OK" or any(p["file"].endswith(".pdf") for p in r1["published"])), r1["published"])
check("no DELETE/PATCH calls", not any(m in ("DELETE", "PATCH") for m, _ in fake.calls))
drive["Certificates/certs-2026-b.xlsx"] = {"data": xlsx([["web-prod", "ana", soon], ["api", "luis", far], ["new-cert", "eva", past]]), "t": "2026-10-08T00:00:00Z"}
ns, fake = load(code, sp_handler)
import time; time.sleep(1.1)
r2 = ns["main"](mode="report", publish="yes")
check("sharepoint run2 reads newest file", r2["sources"][0].get("file") == "certs-2026-b.xlsx", r2["sources"][0])
check("sharepoint run2 history loaded", r2["history"] == "loaded", r2["history"])
check("sharepoint run2 new/resolved findings", r2["new_findings"] >= 1 and r2["resolved_findings"] >= 1, (r2["new_findings"], r2["resolved_findings"]))
html = sorted(p for p in Path.cwd().rglob("certificate-register-*.html") if "selftest" not in p.name)[-1].read_text(encoding="utf-8")
check("html contains title and finding", "Certificate register" in html and "new-cert" in html)

# ---------- Log Analytics heartbeat: ok + 403
def la_handler(method, url, kw):
    assert "api.loganalytics.io" in url
    rows = [["vm-a", (NOW - timedelta(hours=30)).isoformat(), "Linux", "Azure", "rg", 30.0],
            ["vm-b", (NOW - timedelta(hours=3)).isoformat(), "Windows", "Non-Azure", "rg", 3.0],
            ["vm-c", NOW.isoformat(), "Linux", "Azure", "rg", 0.1]]
    cols = ["Computer", "LastHeartbeat", "OSType", "ComputerEnvironment", "ResourceGroup", "HoursSilent"]
    return Resp(200, {"tables": [{"columns": [{"name": c} for c in cols], "rows": rows}]})


code = tool("vm-heartbeat-gaps", lambda s: s["sources"][0].update(workspace_id="11111111-1111-1111-1111-111111111111"))
ns, _ = load(code, la_handler)
r = ns["main"](mode="report")
check("heartbeat OK with 1 high + 1 medium", r["status"] == "OK" and r["findings_by_severity"]["high"] == 1 and r["findings_by_severity"]["medium"] == 1, r.get("findings_by_severity"))
check("heartbeat history disabled", r["history"] == "disabled")
ns, _ = load(code, lambda m, u, k: Resp(403, {"error": {"code": "InsufficientAccessError"}}))
r = ns["main"](mode="report")
check("heartbeat 403 -> FAILED/FORBIDDEN", r["status"] == "FAILED" and r["sources"][0]["status"] == "FORBIDDEN", r)
ns, _ = load(code, la_handler)
d = ns["main"](mode="discover")
check("discover lists columns", d["status"] == "OK" and "HoursSilent" in [c["name"] for c in d["sources"][0]["columns"]], d)
check("field_check OK on live columns", all(f["status"] == "OK" for f in kit._field_check(kit._validate(json.loads(json.dumps(kit.RECIPES[0]["spec"])))[0], d)))

# ---------- Graph secrets: explode + paging
def graph_handler(method, url, kw):
    if "skiptoken" not in url:
        return Resp(200, {"value": [{"id": "1", "appId": "a1", "displayName": "App One", "passwordCredentials": [
            {"keyId": "k1", "displayName": "s1", "endDateTime": (NOW - timedelta(days=2)).isoformat()},
            {"keyId": "k2", "displayName": "s2", "endDateTime": (NOW + timedelta(days=12)).isoformat()}]}],
            "@odata.nextLink": "https://graph.microsoft.com/v1.0/applications?$skiptoken=x"})
    return Resp(200, {"value": [{"id": "2", "appId": "a2", "displayName": "App Two", "passwordCredentials": [
        {"keyId": "k3", "displayName": "s3", "endDateTime": (NOW + timedelta(days=300)).isoformat()}]},
        {"id": "3", "appId": "a3", "displayName": "App Three", "passwordCredentials": []}]})


ns, fake = load(tool("entra-app-secrets-expiry"), graph_handler)
r = ns["main"](mode="report")
kp = {k["id"]: k["value"] for k in r["kpis"]}
check("graph paging + explode rows (apps without secrets dropped)", r["status"] == "OK" and r["sources"][0]["rows"] == 3, r["sources"])
check("graph 1 expired + 1 expiring", r["findings_by_severity"]["critical"] == 1 and r["findings_by_severity"]["high"] == 1, r["findings_by_severity"])
check("graph kpis", kp.get("expired") == 1 and kp.get("expiring") == 1, kp)
check("graph message uses dotted fields", any("s1" in f["message"] for f in r["top_findings"]), r["top_findings"])
print("FAILURES:", failures)
sys.exit(1 if failures else 0)

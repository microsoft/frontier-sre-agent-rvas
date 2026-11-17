# generate-fabric-chargeback-report
# Microsoft Fabric FinOps: real cost, who consumes what, idle capacity and savings, from the customer's own tenant.
# Two auth modes, no secrets in the code:
#   A) Same tenant (default): the SRE Agent managed identity reads Fabric/Azure directly.
#   B) Cross-tenant: a multi-tenant app in the Fabric tenant, signed in with its certificate from Key Vault (or a federated credential).
# Sources (all live, read-only): Power BI/Fabric admin APIs (activity log, workspaces, items, refreshables, tenant settings),
#   Fabric Spark (Livy sessions), OneLake (DFS), Azure Cost Management (daily cost per meter), Azure Activity Log
#   (capacity suspend/resume) and the public Azure Retail Prices API. Nothing is simulated or estimated without a source.
# Read-only · Version 5.0 · October 2026


def main(operation: str = "report", period: str = "last_30d", identities: str = "masked") -> dict:
    """Generate a read-only Microsoft Fabric FinOps and chargeback report (HTML + JSON + 2 CSV) from real tenant data."""
    import csv
    import hashlib
    import html
    import io
    import json
    import math
    import os
    import re
    import time
    from collections import Counter, defaultdict
    from concurrent.futures import ThreadPoolExecutor
    from datetime import datetime, timedelta, timezone
    from pathlib import Path
    from urllib.parse import quote

    # ---- CONFIGURE (see README, step "Configure the tool") ---------------------------------------
    # Client ID of the SRE Agent user-assigned managed identity. Required in both modes.
    MANAGED_IDENTITY_CLIENT_ID = "<SRE_AGENT_UAMI_CLIENT_ID>"
    # Option A - same tenant: leave the two values below untouched (or set them to "").
    # Option B - cross-tenant: client ID of the multi-tenant app and tenant ID where Fabric lives.
    FEDERATED_APP_CLIENT_ID = "<FEDERATED_APP_CLIENT_ID>"
    TARGET_FABRIC_TENANT_ID = "<TARGET_FABRIC_TENANT_ID>"
    # Option B, recommended: certificate of the multi-tenant app stored in a Key Vault of the SRE Agent tenant
    # (the agent identity needs "Key Vault Secrets User" on it). The SRE Agent sandbox hands Python tools
    # sidecar-issued managed identity tokens that its proxy swaps at egress, so they cannot be sent as a
    # federated client assertion (Entra rejects them with AADSTS5002723). Leave empty to try the federated credential.
    CROSS_TENANT_CERT_KEYVAULT_URL = ""   # e.g. "https://<vault>.vault.azure.net"
    CROSS_TENANT_CERT_NAME = ""           # e.g. "sre-agent-fabric-cross-tenant"
    # Time zone shown next to UTC in pause recommendations (IANA name, e.g. "Europe/Madrid", "Europe/Berlin").
    LOCAL_TIMEZONE = "Europe/Madrid"
    # ------------------------------------------------------------------------------------------------

    def _configured(v):
        return bool((v or "").strip()) and not v.strip().startswith("<")

    CROSS_TENANT = _configured(FEDERATED_APP_CLIENT_ID) and _configured(TARGET_FABRIC_TENANT_ID)
    AUTH_MODE = "cross_tenant" if CROSS_TENANT else "same_tenant"
    OWN_IDENTITY_ID = (FEDERATED_APP_CLIENT_ID if CROSS_TENANT else MANAGED_IDENTITY_CLIENT_ID).strip().lower()
    FABRIC_API = "https://api.fabric.microsoft.com/v1"
    PBI_API = "https://api.powerbi.com/v1.0/myorg"
    ARM_API = "https://management.azure.com"
    BUDGET_SECONDS = 105

    operation = (operation or "report").strip().lower()
    show_ids = (identities or "masked").strip().lower() in ("full", "show", "visible", "yes", "true")
    period_map = {"last_30d": ("Last 30 days", 30), "last_14d": ("Last 14 days", 14), "last_7d": ("Last 7 days", 7)}
    period_key = (period or "last_30d").strip().lower()
    if period_key not in period_map:
        period_key = "last_30d"
    period_label, period_days = period_map[period_key]
    now_utc = datetime.now(timezone.utc)
    ref_iso = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    stamp = now_utc.strftime("%Y%m%dT%H%M%SZ")
    window_start = (now_utc - timedelta(days=period_days)).replace(hour=0, minute=0, second=0, microsecond=0)
    replay = os.environ.get("FABRIC_FINOPS_REPLAY")
    cwd = Path.cwd()
    m_tid = re.fullmatch(r"/(?:root/sreagent|usr)/terminalRoot/tmp/ThreadFiles/([0-9a-fA-F-]{36})", cwd.as_posix())

    def file_url(name):
        return f"/api/files/tmp/ThreadFiles/{m_tid.group(1)}/{quote(name, safe='')}" if m_tid else str(cwd / name)

    if replay:
        raw = json.loads(Path(replay).read_text(encoding='utf-8'))
        sources = raw.get('sources', {})
        # Raw dumps recorded by the earlier Spanish collector carry Spanish status notes; show them in English.
        LEGACY_NOTES = [
            (r"^Certificado de la app puente leído de Key Vault$", "Bridge app certificate read from Key Vault"),
            (r"^Key Vault no devolvió el certificado: ", "Key Vault did not return the certificate: "),
            (r"^(\d+/\d+) días$", r"\1 days"),
            (r"^Capacidad en pausa \(CapacityNotActive\): las sesiones Spark solo se pueden leer con la capacidad encendida$",
             "Capacity paused (CapacityNotActive): Spark sessions can only be read while the capacity is running"),
            (r"^Capacidad en pausa \(CapacityNotActive\): OneLake solo se puede leer con la capacidad encendida$",
             "Capacity paused (CapacityNotActive): OneLake can only be read while the capacity is running"),
            (r"^(\d+/\d+) lakehouses/warehouses leídos$", r"\1 lakehouses/warehouses read"),
            (r"^Cost Management limitó las peticiones \(HTTP 429, ", "Cost Management throttled the requests (HTTP 429, "),
            (r"; volver a pedir el informe más tarde$", "; request the report again later"),
            (r"^(\d+/\d+) workspaces examinados", r"\1 workspaces scanned"),
            (r" · sin tiempo$", " · out of time"),
            (r" · examen no terminado$", " · scan not finished"),
            (r"^No hay grupos con acceso$", "No groups with access"),
            (r"^(\d+/\d+) grupos$", r"\1 groups"),
            (r"^Pendiente: concede GroupMember\.Read\.All y User\.Read\.All \(permisos de aplicación de Microsoft Graph\) a la identidad "
             r"en el tenant de Fabric para atribuir el consumo a los miembros de cada grupo$",
             "Pending: grant GroupMember.Read.All and User.Read.All (Microsoft Graph application permissions) to the identity "
             "in the Fabric tenant to attribute usage to the members of each group"),
        ]
        for _sv in sources.values():
            if isinstance(_sv, dict) and isinstance(_sv.get("note"), str):
                for _pat, _rep in LEGACY_NOTES:
                    _sv["note"] = re.sub(_pat, _rep, _sv["note"])
    else:
        # ================================================================== 1. COLLECT (real tenant data only)
        T0 = time.monotonic()
        sources = {}

        def src(name, status, http=None, count=None, note=None, started=None):
            sources[name] = {"status": status, "http": http, "count": count, "note": note,
                             "seconds": round(time.monotonic() - (started or T0), 1)}

        def left():
            return BUDGET_SECONDS - (time.monotonic() - T0)

        def req(method, url, tok, params=None, body=None, headers=None, timeout=25, retries=2):
            err = None
            for attempt in range(retries + 1):
                if left() < 3:
                    return None, "budget", {}
                h = {"Authorization": "Bearer " + tok, "Accept": "application/json"}
                h.update(headers or {})
                try:
                    r = requests.request(method, url, params=params, json=body, headers=h, timeout=max(3, min(timeout, left())))
                except Exception as exc:
                    err = type(exc).__name__
                    continue
                if r.status_code == 429 and attempt < retries:
                    waits = []
                    for k, v in r.headers.items():
                        if k.lower().endswith("retry-after"):
                            try:
                                waits.append(float(v))
                            except ValueError:
                                pass
                    wait = max(waits) if waits else 4.0 * (attempt + 1)
                    if wait > left() - 20:
                        return 429, "retry-after %ds" % int(wait), r.headers
                    time.sleep(min(max(wait, 1.0), 30.0))
                    continue
                try:
                    data = r.json()
                except ValueError:
                    data = r.text[:300]
                return r.status_code, data, r.headers
            return None, err or "error", {}

        import requests
        from azure.identity import ClientAssertionCredential, ManagedIdentityCredential

        uami = (ManagedIdentityCredential(client_id=MANAGED_IDENTITY_CLIENT_ID) if _configured(MANAGED_IDENTITY_CLIENT_ID)
                else ManagedIdentityCredential())
        cred = None
        if CROSS_TENANT and _configured(CROSS_TENANT_CERT_KEYVAULT_URL) and _configured(CROSS_TENANT_CERT_NAME):
            try:
                from azure.identity import CertificateCredential
                kv_tok = uami.get_token("https://vault.azure.net/.default").token
                kv_r = requests.get(f"{CROSS_TENANT_CERT_KEYVAULT_URL.strip().rstrip('/')}/secrets/{CROSS_TENANT_CERT_NAME.strip()}?api-version=7.4",
                                    headers={"Authorization": "Bearer " + kv_tok, "Accept": "application/json"}, timeout=30)
                if kv_r.status_code == 200:
                    cred = CertificateCredential(tenant_id=TARGET_FABRIC_TENANT_ID, client_id=FEDERATED_APP_CLIENT_ID,
                                                 certificate_data=kv_r.json()["value"].encode("utf-8"))
                    src("cross_tenant_auth", "ok", 200, note="Multi-tenant app certificate read from Key Vault")
                else:
                    src("cross_tenant_auth", "error", kv_r.status_code,
                        note="Key Vault did not return the certificate: " + " ".join(kv_r.text.split())[:240])
            except Exception as exc:
                src("cross_tenant_auth", "error", note=type(exc).__name__ + ": " + " ".join(str(exc).split())[:240])
        if cred is None and CROSS_TENANT:
            cred = ClientAssertionCredential(tenant_id=TARGET_FABRIC_TENANT_ID, client_id=FEDERATED_APP_CLIENT_ID,
                                             func=lambda: uami.get_token("api://AzureADTokenExchange/.default").token)
        elif cred is None:
            cred = uami
        tokens = {}
        for key, scope in (("fab", "https://api.fabric.microsoft.com/.default"),
                           ("pbi", "https://analysis.windows.net/powerbi/api/.default"),
                           ("arm", "https://management.azure.com/.default"),
                           ("sto", "https://storage.azure.com/.default"),
                           ("gr", "https://graph.microsoft.com/.default")):
            try:
                tokens[key] = cred.get_token(scope).token
            except Exception as exc:
                tokens[key] = None
                src("token_" + key, "error", note=(type(exc).__name__ + ": " + " ".join(str(exc).split())[:320]))

        def _token_tid(tok):
            try:
                import base64
                p = tok.split(".")[1]
                return json.loads(base64.urlsafe_b64decode(p + "=" * (-len(p) % 4))).get("tid")
            except Exception:
                return None

        tenant_id = TARGET_FABRIC_TENANT_ID if CROSS_TENANT else next(
            (_token_tid(v) for v in tokens.values() if v and _token_tid(v)), None)
        raw = {"generated_utc": ref_iso, "period_days": period_days, "tenant_id": tenant_id, "auth_mode": AUTH_MODE}

        def c_capacities():
            t = time.monotonic()
            st, d, _ = req("GET", f"{PBI_API}/admin/capacities", tokens["pbi"])
            caps = d.get("value", []) if isinstance(d, dict) else []
            raw["pbi_capacities"] = [{"id": (c.get("id") or "").lower(), "name": c.get("displayName"), "sku": c.get("sku"),
                                      "state": c.get("state"), "region": c.get("region"), "admins": len(c.get("admins") or [])}
                                     for c in caps]
            src("capacities", "ok" if st == 200 else "error", st, len(caps), started=t)

        def c_workspaces():
            t = time.monotonic()
            out, url, st = [], f"{FABRIC_API}/admin/workspaces", None
            for _ in range(10):
                st, d, _ = req("GET", url, tokens["fab"])
                if st != 200 or not isinstance(d, dict):
                    break
                for w in d.get("workspaces", []) or []:
                    out.append({"id": (w.get("id") or "").lower(), "name": w.get("name"), "type": w.get("type"),
                                "state": w.get("state"), "capacity_id": (w.get("capacityId") or "").lower()})
                url = d.get("continuationUri")
                if not url:
                    break
            raw["workspaces"] = out
            src("workspaces", "ok" if out else "error", st, len(out), started=t)
            return out

        def c_items():
            t = time.monotonic()
            out, url, st = [], f"{FABRIC_API}/admin/items", None
            for _ in range(20):
                st, d, _ = req("GET", url, tokens["fab"])
                if st != 200 or not isinstance(d, dict):
                    break
                for i in d.get("itemEntities", []) or []:
                    cp = i.get("creatorPrincipal") or {}
                    out.append({"id": (i.get("id") or "").lower(), "type": i.get("type"), "name": i.get("name"),
                                "state": i.get("state"), "updated": i.get("lastUpdatedDate"),
                                "ws": (i.get("workspaceId") or "").lower(), "cap": (i.get("capacityId") or "").lower(),
                                "creator_id": (cp.get("id") or "").lower(), "creator_name": cp.get("displayName"),
                                "creator_upn": (cp.get("userDetails") or {}).get("userPrincipalName"),
                                "creator_type": cp.get("type")})
                url = d.get("continuationUri")
                if not url and d.get("continuationToken"):
                    url = f"{FABRIC_API}/admin/items?continuationToken={quote(d['continuationToken'])}"
                if not url:
                    break
            raw["items"] = out
            src("items", "ok" if out else "error", st, len(out), started=t)
            return out

        def c_activity():
            t = time.monotonic()
            days = min(period_days, 27)
            res = {}

            def one_day(dd):
                day = (now_utc - timedelta(days=dd)).strftime("%Y-%m-%d")
                end = now_utc.strftime("%H:%M:%S") + ".000Z" if dd == 0 else "23:59:59.999Z"
                url = (f"{PBI_API}/admin/activityevents?startDateTime='{day}T00:00:00.000Z'&endDateTime='{day}T{end}'")
                evs, st = [], None
                for _ in range(40):
                    st, d, _ = req("GET", url, tokens["pbi"], timeout=30)
                    if st != 200 or not isinstance(d, dict):
                        break
                    for e in d.get("activityEventEntities") or []:
                        evs.append({
                            "t": e.get("CreationTime"), "u": e.get("UserId") or e.get("UserKey") or "",
                            "a": e.get("Activity") or e.get("Operation") or "", "wl": e.get("Workload") or "",
                            "ws": e.get("WorkSpaceName") or e.get("WorkspaceName") or "",
                            "wsid": (e.get("WorkspaceId") or "").lower(),
                            "it": (e.get("ItemName") or e.get("ArtifactName") or e.get("ObjectDisplayName") or e.get("DatasetName")
                                   or e.get("ReportName") or e.get("DashboardName") or ""),
                            "itt": e.get("ArtifactKind") or e.get("ItemType") or e.get("ObjectType") or "",
                            "cap": e.get("CapacityName") or "", "ok": e.get("IsSuccess"),
                            "ua": (e.get("UserAgent") or "")[:80], "ut": e.get("UserType"),
                        })
                    if d.get("lastResultSet") or not d.get("continuationUri"):
                        break
                    url = d["continuationUri"]
                return day, st, evs

            with ThreadPoolExecutor(max_workers=9) as ex:
                for day, st, evs in ex.map(one_day, range(days)):
                    res[day] = (st, evs)
            events, ok_days, last_st = [], 0, None
            for day in sorted(res):
                st, evs = res[day]
                last_st = st if st != 200 else last_st
                if st == 200:
                    ok_days += 1
                events.extend(evs)
            raw["events"] = events
            raw["activity_days_ok"] = ok_days
            raw["activity_days_requested"] = days
            src("activity", "ok" if ok_days == days else ("partial" if ok_days else "error"), last_st or 200, len(events),
                note=f"{ok_days}/{days} days", started=t)

        def c_refreshables():
            t = time.monotonic()
            st, d, _ = req("GET", f"{PBI_API}/admin/capacities/refreshables", tokens["pbi"],
                           params={"$top": "500", "$expand": "capacity,group"}, timeout=30)
            rows = d.get("value", []) if isinstance(d, dict) else []
            out = []
            for r in rows:
                lr = r.get("lastRefresh") or {}
                sc = r.get("refreshSchedule") or {}
                out.append({"id": r.get("id"), "name": r.get("name"), "kind": r.get("kind"),
                            "ws": (r.get("group") or {}).get("name"), "wsid": ((r.get("group") or {}).get("id") or "").lower(),
                            "cap": (r.get("capacity") or {}).get("displayName"), "sku": (r.get("capacity") or {}).get("sku"),
                            "last_type": lr.get("refreshType"), "last_start": lr.get("startTime"), "last_end": lr.get("endTime"),
                            "last_status": lr.get("status"), "last_error": (str(lr.get("serviceExceptionJson") or "")[:200] or None),
                            "sched_enabled": bool(sc.get("enabled")), "sched_days": sc.get("days") or [], "sched_times": sc.get("times") or [],
                            "count": r.get("refreshCount"), "failures": r.get("refreshFailures"),
                            "avg_s": r.get("averageDuration"), "median_s": r.get("medianDuration"),
                            "per_day": r.get("refreshesPerDay"), "configured_by": r.get("configuredBy") or []})
            raw["refreshables"] = out
            src("refreshables", "ok" if st == 200 else "error", st, len(out), started=t)

        def c_livy(workspaces):
            t = time.monotonic()
            win = [w for w in workspaces if w.get("capacity_id")]

            def one(w):
                url, out, st, err = f"{FABRIC_API}/workspaces/{w['id']}/spark/livySessions", [], None, None
                for _ in range(6):
                    st, d, _ = req("GET", url, tokens["fab"], timeout=20, retries=1)
                    if st != 200 or not isinstance(d, dict):
                        err = d.get("errorCode") if isinstance(d, dict) else None
                        break
                    for s in d.get("value", []) or []:
                        out.append({"ws": w["id"], "item": s.get("itemName"), "item_id": ((s.get("item") or {}).get("itemId") or "").lower(),
                                    "item_type": s.get("itemType"), "job": s.get("jobType"), "op": s.get("operationName"),
                                    "user_id": ((s.get("submitter") or {}).get("id") or "").lower(),
                                    "user_type": (s.get("submitter") or {}).get("type"), "state": s.get("state"),
                                    "submitted": s.get("submittedDateTime"), "start": s.get("startDateTime"), "end": s.get("endDateTime"),
                                    "queued_s": (s.get("queuedDuration") or {}).get("value"),
                                    "running_s": (s.get("runningDuration") or {}).get("value"),
                                    "total_s": (s.get("totalDuration") or {}).get("value"),
                                    "cap": (s.get("capacityId") or "").lower(), "hc": s.get("isHighConcurrency"),
                                    "origin": s.get("origin"), "runtime": s.get("runtimeVersion")})
                    url = d.get("continuationUri")
                    if not url:
                        break
                return st, out, err

            sessions, codes, errs = [], Counter(), Counter()
            with ThreadPoolExecutor(max_workers=8) as ex:
                for st, out, err in ex.map(one, win):
                    codes[str(st)] += 1
                    errs[err or str(st)] += 1
                    sessions.extend(out)
            raw["livy"] = sessions
            raw["livy_http"] = dict(codes)
            if not codes.get("200") and errs and set(errs) == {"CapacityNotActive"}:
                src("spark", "paused", 404, 0, note="Capacity paused (CapacityNotActive): Spark sessions can only be read while the capacity is running", started=t)
            else:
                src("spark", "ok" if codes.get("200") else "error", "200" if codes.get("200") else None, len(sessions),
                    note=f"{codes.get('200', 0)}/{len(win)} workspaces" + ("" if codes.get("200") else " · " + ", ".join(f"{k} ×{v}" for k, v in errs.most_common(3))), started=t)

        def c_onelake(items):
            t = time.monotonic()
            targets = [i for i in items if i.get("type") in ("Lakehouse", "Warehouse") and i.get("ws")][:60]

            def one(it):
                tot, files, cont, st, pages, err = 0, 0, None, None, 0, None
                for _ in range(10):
                    if left() < 12:
                        break
                    params = {"resource": "filesystem", "recursive": "true", "directory": it["id"]}
                    if cont:
                        params["continuation"] = cont
                    try:
                        r = requests.get(f"https://onelake.dfs.fabric.microsoft.com/{it['ws']}", params=params, timeout=max(3, min(20, left())),
                                         headers={"Authorization": "Bearer " + tokens["sto"], "x-ms-version": "2023-08-03"})
                    except Exception:
                        break
                    st = r.status_code
                    if st != 200:
                        err = r.headers.get("x-ms-error-code") or r.text[:200]
                        break
                    pages += 1
                    for p in (r.json() or {}).get("paths", []) or []:
                        if str(p.get("isDirectory")).lower() != "true":
                            tot += int(p.get("contentLength") or 0)
                            files += 1
                    cont = r.headers.get("x-ms-continuation")
                    if not cont:
                        break
                return {"ws": it["ws"], "item": it["name"], "item_id": it["id"], "type": it["type"], "bytes": tot,
                        "files": files, "http": st, "truncated": bool(cont), "err": err}

            with ThreadPoolExecutor(max_workers=8) as ex:
                out = list(ex.map(one, targets))
            raw["onelake"] = out
            okn = sum(1 for o in out if o["http"] == 200)
            if out and not okn and all("capacitynotactive" in (o.get("err") or "").replace(" ", "").lower() for o in out):
                src("onelake", "paused", 404, len(out), note="Capacity paused (CapacityNotActive): OneLake can only be read while the capacity is running", started=t)
                return
            src("onelake", "ok" if okn == len(out) and out else ("partial" if okn else "error"), 200 if okn else None, len(out),
                note=f"{okn}/{len(out)} lakehouses/warehouses read", started=t)

        def c_arm():
            t = time.monotonic()
            st, d, _ = req("GET", f"{ARM_API}/subscriptions", tokens["arm"], params={"api-version": "2022-12-01"})
            subs = [s for s in (d.get("value", []) if isinstance(d, dict) else []) if (s.get("state") or "Enabled") == "Enabled"][:5]
            raw["subscriptions"] = [{"id": s.get("subscriptionId"), "name": s.get("displayName")} for s in subs]
            src("arm", "ok" if subs else "error", st, len(subs), started=t)
            caps, rows, logs = [], [], []
            cost_st = log_st = None
            notes = {}
            extra_st, extra_rows = {}, {"cost_monthly": [], "sub_costs": []}
            for s in subs:
                sid = s.get("subscriptionId")
                st, d, _ = req("GET", f"{ARM_API}/subscriptions/{sid}/providers/Microsoft.Fabric/capacities", tokens["arm"],
                               params={"api-version": "2023-11-01"})
                for c in (d.get("value", []) if isinstance(d, dict) else []):
                    p = c.get("properties") or {}
                    rg = re.search(r"/resourceGroups/([^/]+)/", c.get("id") or "", re.I)
                    caps.append({"name": c.get("name"), "id": (c.get("id") or "").lower(), "sub": sid, "sub_name": s.get("displayName"),
                                 "rg": rg.group(1) if rg else "", "sku": (c.get("sku") or {}).get("name"), "location": c.get("location"),
                                 "state": p.get("state"), "admins": len((p.get("administration") or {}).get("members") or []),
                                 "tags": c.get("tags") or {}})
                body = {"type": "ActualCost", "timeframe": "Custom",
                        "timePeriod": {"from": window_start.strftime("%Y-%m-%dT00:00:00Z"), "to": now_utc.strftime("%Y-%m-%dT23:59:59Z")},
                        "dataset": {"granularity": "Daily",
                                    "aggregation": {"cost": {"name": "Cost", "function": "Sum"}, "qty": {"name": "UsageQuantity", "function": "Sum"}},
                                    "grouping": [{"type": "Dimension", "name": "ResourceId"}, {"type": "Dimension", "name": "Meter"}],
                                    "filter": {"dimensions": {"name": "ResourceType", "operator": "In", "values": ["microsoft.fabric/capacities"]}}}}
                url = f"{ARM_API}/subscriptions/{sid}/providers/Microsoft.CostManagement/query?api-version=2023-11-01"
                for _ in range(5):
                    cost_st, d, _ = req("POST", url, tokens["arm"], body=body, timeout=40, retries=3)
                    if cost_st != 200 or not isinstance(d, dict):
                        if cost_st == 429:
                            notes["cost"] = "Cost Management throttled the requests (HTTP 429, %s); request the report again later" % d
                        break
                    pr = d.get("properties") or {}
                    cols = [c.get("name") for c in pr.get("columns") or []]
                    for row in pr.get("rows") or []:
                        r = dict(zip(cols, row))
                        rows.append({"date": str(r.get("UsageDate")), "rid": (r.get("ResourceId") or "").lower(), "meter": r.get("Meter") or "",
                                     "cost": float(r.get("Cost") or 0), "qty": float(r.get("UsageQuantity") or 0),
                                     "currency": r.get("Currency")})
                    url = pr.get("nextLink")
                    if not url:
                        break
                m0 = now_utc.replace(day=1)
                for _ in range(11):
                    m0 = (m0 - timedelta(days=1)).replace(day=1)
                extra = (("cost_monthly", {"type": "ActualCost", "timeframe": "Custom",
                                           "timePeriod": {"from": m0.strftime("%Y-%m-%dT00:00:00Z"), "to": now_utc.strftime("%Y-%m-%dT23:59:59Z")},
                                           "dataset": {"granularity": "Monthly", "aggregation": {"cost": {"name": "Cost", "function": "Sum"}},
                                                       "grouping": [{"type": "Dimension", "name": "ResourceId"}],
                                                       "filter": {"dimensions": {"name": "ResourceType", "operator": "In", "values": ["microsoft.fabric/capacities"]}}}}),
                         ("sub_costs", {"type": "ActualCost", "timeframe": "Custom",
                                        "timePeriod": {"from": window_start.strftime("%Y-%m-%dT00:00:00Z"), "to": now_utc.strftime("%Y-%m-%dT23:59:59Z")},
                                        "dataset": {"granularity": "None", "aggregation": {"cost": {"name": "Cost", "function": "Sum"}},
                                                    "grouping": [{"type": "Dimension", "name": "ServiceName"}, {"type": "Dimension", "name": "ResourceId"}]}}))
                for key, bdy in extra:
                    time.sleep(1.5)
                    st_x, d, _ = req("POST", f"{ARM_API}/subscriptions/{sid}/providers/Microsoft.CostManagement/query?api-version=2023-11-01",
                                     tokens["arm"], body=bdy, timeout=40, retries=4)
                    extra_st[key] = st_x
                    if st_x == 429:
                        notes[key] = "Cost Management throttled the requests (HTTP 429, %s)" % d
                    if st_x == 200 and isinstance(d, dict):
                        pr = d.get("properties") or {}
                        cols = [c.get("name") for c in pr.get("columns") or []]
                        for row in pr.get("rows") or []:
                            r = dict(zip(cols, row))
                            extra_rows[key].append({"month": str(r.get("BillingMonth") or "")[:7], "service": r.get("ServiceName") or "",
                                                    "rid": (r.get("ResourceId") or "").lower(), "cost": float(r.get("Cost") or 0),
                                                    "currency": r.get("Currency"), "sub": sid})
                flt = (f"eventTimestamp ge '{(window_start - timedelta(days=1)).strftime('%Y-%m-%dT%H:%M:%SZ')}' and "
                       f"eventTimestamp le '{now_utc.strftime('%Y-%m-%dT%H:%M:%SZ')}' and resourceProvider eq 'Microsoft.Fabric'")
                url, params = f"{ARM_API}/subscriptions/{sid}/providers/Microsoft.Insights/eventtypes/management/values", \
                    {"api-version": "2015-04-01", "$filter": flt}
                for _ in range(10):
                    log_st, d, _ = req("GET", url, tokens["arm"], params=params, timeout=30)
                    if log_st != 200 or not isinstance(d, dict):
                        break
                    for e in d.get("value", []) or []:
                        logs.append({"t": e.get("eventTimestamp"), "op": (e.get("operationName") or {}).get("value") or "",
                                     "status": (e.get("status") or {}).get("value") or "", "rid": (e.get("resourceId") or "").lower(),
                                     "caller": e.get("caller") or "", "corr": e.get("correlationId") or "",
                                     "claims_app": ((e.get("claims") or {}).get("appid") or "")})
                    url, params = d.get("nextLink"), None
                    if not url:
                        break
            raw["arm_capacities"] = caps
            raw["cost_rows"] = rows
            raw["activity_log"] = logs
            src("cost", "ok" if cost_st == 200 else "error", cost_st, len(rows), note=notes.get("cost"), started=t)
            src("activity_log", "ok" if log_st == 200 else "error", log_st, len(logs), started=t)
            raw["cost_monthly"] = extra_rows["cost_monthly"]
            raw["sub_costs"] = extra_rows["sub_costs"]
            for key in ("cost_monthly", "sub_costs"):
                src(key, "ok" if extra_st.get(key) == 200 else "error", extra_st.get(key), len(extra_rows[key]), note=notes.get(key), started=t)
            # public Azure Retail Prices for the capacity regions (no auth)
            t2 = time.monotonic()
            prices = []
            for region in sorted({c["location"].replace(" ", "").lower() for c in caps if c.get("location")})[:3]:
                url = "https://prices.azure.com/api/retail/prices"
                params = {"$filter": f"serviceName eq 'Microsoft Fabric' and armRegionName eq '{region}'", "currencyCode": "USD"}
                for _ in range(5):
                    try:
                        r = requests.get(url, params=params, timeout=max(3, min(20, left())))
                        d = r.json() if r.ok else {}
                    except Exception:
                        break
                    for p in d.get("Items", []) or []:
                        prices.append({"region": region, "meter": p.get("meterName"), "product": p.get("productName"), "type": p.get("type"),
                                       "term": p.get("reservationTerm"), "price": p.get("unitPrice"), "unit": p.get("unitOfMeasure"),
                                       "currency": p.get("currencyCode")})
                    url, params = d.get("NextPageLink"), None
                    if not url:
                        break
            raw["prices"] = prices
            src("prices", "ok" if prices else "error", 200 if prices else None, len(prices), started=t2)

        def c_tenant_settings():
            t = time.monotonic()
            st, d, _ = req("GET", f"{FABRIC_API}/admin/tenantsettings", tokens["fab"])
            ts = d.get("tenantSettings", []) if isinstance(d, dict) else []
            raw["tenant_settings"] = [{"name": s.get("settingName"), "title": s.get("title"), "enabled": bool(s.get("enabled")),
                                       "group": s.get("tenantSettingGroup"), "groups": [g.get("name") for g in s.get("enabledSecurityGroups") or []],
                                       "excluded": len(s.get("excludedSecurityGroups") or [])} for s in ts]
            src("tenant_settings", "ok" if st == 200 else "error", st, len(ts), started=t)

        def _acc_row(wid, iid, iname, itype, u, right):
            return {"ws": wid, "item_id": iid, "item": iname, "item_type": itype, "ptype": u.get("principalType") or "",
                    "name": u.get("displayName") or "", "email": (u.get("emailAddress") or "").lower(),
                    "gid": (u.get("graphId") or u.get("identifier") or "").lower(), "right": right or ""}

        def c_access():
            # Who can use what: workspace roles (Power BI admin API) + item permissions (admin scanner API), read only.
            t = time.monotonic()
            st, d, _ = req("GET", f"{PBI_API}/admin/groups", tokens["pbi"],
                           params={"$top": 5000, "$expand": "users", "$filter": "state eq 'Active'"}, timeout=40)
            wsl = d.get("value", []) if isinstance(d, dict) else []
            acc = []
            for w in wsl:
                wid = (w.get("id") or "").lower()
                for u in w.get("users") or []:
                    acc.append(_acc_row(wid, None, None, None, u, u.get("groupUserAccessRight")))
            src("access_workspaces", "ok" if st == 200 else "error", st, len(acc), started=t)
            t2 = time.monotonic()
            ids = [w.get("id") for w in wsl if w.get("id")]
            n_art, done, scan_err = 0, 0, None
            for i in range(0, len(ids), 100):
                if left() < 25:
                    scan_err = "out of time"
                    break
                st1, s, _ = req("POST", f"{PBI_API}/admin/workspaces/getInfo", tokens["pbi"],
                                params={"lineage": "false", "datasourceDetails": "false", "datasetSchema": "false",
                                        "datasetExpressions": "false", "getArtifactUsers": "true"},
                                body={"workspaces": ids[i:i + 100]}, timeout=30)
                if st1 not in (200, 202) or not isinstance(s, dict) or not s.get("id"):
                    scan_err = f"getInfo HTTP {st1}"
                    break
                ok = False
                for _ in range(25):
                    if left() < 15:
                        break
                    time.sleep(2)
                    st2, s2, _ = req("GET", f"{PBI_API}/admin/workspaces/scanStatus/{s['id']}", tokens["pbi"], timeout=15)
                    status = (s2 or {}).get("status") if isinstance(s2, dict) else None
                    if status in ("Succeeded", "Failed"):
                        ok = status == "Succeeded"
                        break
                if not ok:
                    scan_err = "scan not finished"
                    break
                st3, res, _ = req("GET", f"{PBI_API}/admin/workspaces/scanResult/{s['id']}", tokens["pbi"], timeout=40)
                if st3 != 200 or not isinstance(res, dict):
                    scan_err = f"scanResult HTTP {st3}"
                    break
                for w in res.get("workspaces") or []:
                    wid = (w.get("id") or "").lower()
                    for kind, arts in w.items():
                        if kind == "users" or not isinstance(arts, list):
                            continue
                        for a in arts:
                            if not isinstance(a, dict) or not a.get("users"):
                                continue
                            n_art += 1
                            for u in a["users"]:
                                right = next((v for k2, v in u.items() if k2.endswith("UserAccessRight")), "")
                                acc.append(_acc_row(wid, (a.get("id") or "").lower(), a.get("name") or "", a.get("type") or kind, u, right))
                done += len(ids[i:i + 100])
            src("access_items", "ok" if not scan_err else ("partial" if done else "error"), 200 if not scan_err else None, n_art,
                note=f"{done}/{len(ids)} workspaces scanned" + (f" · {scan_err}" if scan_err else ""), started=t2)
            raw["access"] = acc
            # Optional: Entra ID group members (needs GroupMember.Read.All application permission in the Fabric tenant)
            t3 = time.monotonic()
            guid_re = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
            gids = sorted({r["gid"] for r in acc if r["ptype"] == "Group" and guid_re.match(r["gid"] or "")})
            members, gst = {}, None
            if tokens.get("gr"):
                for gid in gids[:60]:
                    if left() < 12:
                        break
                    out, url = [], (f"https://graph.microsoft.com/v1.0/groups/{gid}/transitiveMembers/microsoft.graph.user"
                                    "?$select=id,userPrincipalName,displayName,createdDateTime&$top=999")
                    for _ in range(10):
                        gst, gd, _ = req("GET", url, tokens["gr"], timeout=20)
                        if gst != 200 or not isinstance(gd, dict):
                            break
                        out.extend({"upn": (m.get("userPrincipalName") or "").lower(), "created": m.get("createdDateTime")}
                                   for m in gd.get("value") or [])
                        url = gd.get("@odata.nextLink")
                        if not url:
                            break
                    if gst in (401, 403):
                        break
                    if gst == 200:
                        members[gid] = out
            raw["group_members"] = members
            if not gids:
                src("group_members", "ok", None, 0, note="No groups with access", started=t3)
            elif members:
                src("group_members", "ok" if len(members) == len(gids) else "partial", 200, sum(len(v) for v in members.values()),
                    note=f"{len(members)}/{len(gids)} groups", started=t3)
            else:
                src("group_members", "pending", gst, 0,
                    note="Pending: grant GroupMember.Read.All and User.Read.All (Microsoft Graph application permissions) to the identity "
                         "in the Fabric tenant to attribute usage to the members of each group", started=t3)

        def chain_workspace_livy():
            ws = c_workspaces()
            c_livy(ws)

        def chain_items_onelake():
            its = c_items()
            c_onelake(its)

        if tokens.get("fab") and tokens.get("pbi"):
            with ThreadPoolExecutor(max_workers=8) as ex:
                futs = [ex.submit(f) for f in (c_activity, chain_workspace_livy, chain_items_onelake, c_arm,
                                               c_capacities, c_refreshables, c_tenant_settings, c_access)]
                for f in futs:
                    try:
                        f.result()
                    except Exception as exc:
                        sources.setdefault("internal_" + str(len(sources)), {"status": "error", "note": f"{type(exc).__name__}: {str(exc)[:160]}"})
        raw["sources"] = sources
        raw["collect_seconds"] = round(time.monotonic() - T0, 1)

    # ================================================================== v5 ANALYSIS · only real tenant data
    t_an = time.monotonic()
    E = html.escape
    GUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
    WD = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

    def dmon(t, fmt=""):
        # locale-independent "06 Oct" (+ optional strftime suffix such as " %H:%M" or " %Y")
        return f"{t.day:02d} {MON[t.month - 1]}" + (t.strftime(fmt) if fmt else "")

    def P(s):
        if not s:
            return None
        try:
            return datetime.fromisoformat(str(s).replace("Z", "")[:19]).replace(tzinfo=timezone.utc)
        except Exception:
            return None

    def fn(v, d=0):
        return f"{(v or 0):,.{d}f}"

    def pc(v, d=1):
        return f"{fn((v or 0) * 100, d)}%"

    def hhmm(t):
        return t.strftime("%H:%M") if t else "—"

    def floor_day(t):
        return t.replace(hour=0, minute=0, second=0, microsecond=0)

    gen = P(raw.get("generated_utc")) or now_utc
    days_n = int(raw.get("period_days") or period_days)
    win0 = floor_day(gen - timedelta(days=days_n))
    win_hours = max((gen - win0).total_seconds() / 3600, 1)
    act_days = int(raw.get("activity_days_requested") or 0)
    act_ok = int(raw.get("activity_days_ok") or 0)
    act0 = floor_day(gen - timedelta(days=act_days - 1)) if act_days else None
    own_sp = OWN_IDENTITY_ID
    sources = raw.get("sources") or {}

    workspaces = raw.get("workspaces") or []
    ws_name = {(w.get("id") or "").lower(): (w.get("name") or "") for w in workspaces}
    if not show_ids:
        # personal workspaces are named after their owner
        for _w in workspaces:
            _k, _v = (_w.get("id") or "").lower(), _w.get("name") or ""
            if (_w.get("type") or "").lower() == "personal" or "@" in _v:
                _l, _, _d = _v.partition("@")
                ws_name[_k] = f"Personal · {_l[:1]}•••@{_d[:1]}•••" if _d else f"Personal · {_l[:1]}•••"
    ws_cap = {(w.get("id") or "").lower(): (w.get("capacity_id") or "").lower() for w in workspaces}
    ws_type = {(w.get("id") or "").lower(): (w.get("type") or "") for w in workspaces}
    _wn = Counter((w.get("name") or "").lower() for w in workspaces)
    ws_by_name = {(w.get("name") or "").lower(): (w.get("id") or "").lower() for w in workspaces if _wn[(w.get("name") or "").lower()] == 1}
    items = raw.get("items") or []
    _inm = Counter((i.get("name") or "").lower() for i in items)
    item_ws = {(i.get("name") or "").lower(): (i.get("ws") or "").lower() for i in items if _inm[(i.get("name") or "").lower()] == 1}
    item_type_by_name = {(i.get("name") or "").lower(): i.get("type") or "" for i in items if _inm[(i.get("name") or "").lower()] == 1}
    creators = {}
    for i in items:
        cid = (i.get("creator_id") or "").lower()
        if cid and i.get("creator_upn"):
            creators[cid] = (i.get("creator_name") or "", (i.get("creator_upn") or "").lower())
    upn_name = {upn: nm for nm, upn in creators.values() if upn}
    pbi_caps = raw.get("pbi_capacities") or []
    pcap = {(c.get("id") or "").lower(): c for c in pbi_caps}

    orig_label = {}

    def pkey(u):
        u = (u or "").strip()
        lu = u.lower()
        if lu in creators:
            return creators[lu][1]
        orig_label.setdefault(lu, u)
        return lu

    def pkind(k):
        if k == own_sp:
            return "sre"
        if "@" in k:
            return "user"
        if GUID.match(k):
            return "app"
        if k in ("", "unknown", "none", "null"):
            return "unknown"
        return "system"

    def mask_upn(u):
        loc, _, dom = u.partition("@")
        return f"{loc[:1]}•••@{dom[:1]}•••" if dom else f"{loc[:1]}•••"

    def plabel(k):
        kind = pkind(k)
        if kind == "sre":
            return "SRE Agent (this read)"
        if kind == "user":
            if show_ids:
                nm = upn_name.get(k)
                return f"{nm} · {k}" if nm else k
            return mask_upn(k)
        if kind == "app":
            return f"App {k}" if show_ids else f"App {k[:8]}…"
        if kind == "unknown":
            return "No identity in the event"
        return f"{orig_label.get(k, k)} (system)"

    def ev_cat(a, itt):
        al, t = (a or "").lower(), (itt or "").lower()
        if t == "llmplugin" or any(k in al for k in ("aiskill", "dataagent", "copilot", "openai", "aichat", "llm")):
            return "ai"
        if t in ("functionset", "appbackend", "graphqlapi", "userdatafunction") or any(k in al for k in ("functionset", "graphql", "userdatafunction")):
            return "api"
        if t.startswith(("ontology", "graph", "digitaltwin")) or any(k in al for k in ("ontology", "digitaloperations", "graph")):
            return "iq"
        if t in ("synapsenotebook", "notebook", "lakehouse", "environment", "sparkjobdefinition", "mlmodel", "mlexperiment") \
                or any(k in al for k in ("notebook", "spark", "lakehouse", "livy")):
            return "spark"
        if t.startswith(("kusto", "eventstream", "eventhouse", "reflex", "kql")) or any(k in al for k in ("kusto", "eventstream", "eventhouse", "kql")):
            return "rti"
        if t in ("datawarehouse", "warehouse", "sqlanalyticsendpoint", "sqldbnative", "sqldatabase", "mirroreddatabase") \
                or any(k in al for k in ("warehouse", "sqldatabase", "sqlendpoint")):
            return "db"
        if any(k in al for k in ("pipeline", "dataflow", "copyjob")):
            return "df"
        if t in ("report", "dataset", "model", "dashboard", "app", "semanticmodel") or any(k in al for k in ("report", "dataset", "dashboard", "refresh", "analyzedby")):
            return "pbi"
        return "other"

    def is_admin_act(a):
        return a.endswith(("AsAdmin", "ViaAdminApi")) or a in ("ExportActivityEvents", "GetDatasourceDetailsWithCredentialsAsync")

    # ---------------------------------------------------------------- activity events
    evs = []
    for e in raw.get("events") or []:
        t = P(e.get("t"))
        if not t or t < win0:
            continue
        k = pkey(e.get("u"))
        kind = "sre" if "AzureSREAgent" in (e.get("ua") or "") else pkind(k)
        a = e.get("a") or ""
        wsid = (e.get("wsid") or "").lower()
        it = e.get("it") or ""
        if not wsid and e.get("ws"):
            wsid = ws_by_name.get(e["ws"].lower(), "")
        if not wsid and it:
            wsid = item_ws.get(it.lower(), "")
        itt = e.get("itt") or item_type_by_name.get(it.lower(), "")
        if it.strip().lower() in ("unknown", "none", "null"):
            it = "(no name in the log)"
        work = kind in ("user", "app") and not is_admin_act(a)
        evs.append({"t": t, "k": k, "kind": kind, "a": a, "ws": wsid, "it": it, "itt": itt, "cat": ev_cat(a, itt), "work": work})
    work_ev = [e for e in evs if e["work"]]

    # ---------------------------------------------------------------- Spark / Livy sessions
    livy = []
    for s in raw.get("livy") or []:
        st, en, sub = P(s.get("start")), P(s.get("end")), P(s.get("submitted"))
        ref = st or sub
        if not ref or ref < win0:
            continue
        op = s.get("op") or ""
        livy.append({"ws": (s.get("ws") or "").lower(), "item": (s.get("item") if (s.get("item") or "").strip().lower() not in ("", "unknown", "none", "null") else "(no name in the log)"), "op": op, "user": pkey(s.get("user_id")),
                     "state": s.get("state") or "", "start": st, "end": en, "run": float(s.get("running_s") or 0),
                     "queued": float(s.get("queued_s") or 0), "sched": "schedul" in op.lower(), "pipe": "pipeline" in op.lower(),
                     "cap": (s.get("cap") or "").lower()})
    livy_total_s = sum(x["run"] for x in livy)

    # ---------------------------------------------------------------- cost (Azure Cost Management, real invoice meters)
    CATS = {
        "idle": ("Idle running capacity (Compute Pool)", "#d99a2b"),
        "ai": ("AI · Copilot and Data Agents", "#7b3fa0"),
        "spark": ("Spark and notebooks", "#117865"),
        "iq": ("Fabric IQ · Ontology and Graph", "#2f6fb3"),
        "rti": ("Real-Time Intelligence", "#c4532b"),
        "db": ("Warehouse and SQL", "#0f7c8c"),
        "pbi": ("Power BI", "#b8860b"),
        "df": ("Data Factory", "#5a7d1a"),
        "api": ("APIs and functions", "#a23b72"),
        "onelake": ("OneLake transactions", "#7d8fa3"),
        "storage": ("Storage (GB-month)", "#4f6378"),
        "overage": ("Capacity overage", "#b42318"),
        "other": ("Other meters", "#9aa5b1"),
    }

    def meter_cat(m):
        ml = (m or "").lower()
        if "compute pool" in ml:
            return "idle"
        if "overage" in ml:
            return "overage"
        if "data stored" in ml or "storage" in ml:
            return "storage"
        if ml.startswith("onelake"):
            return "onelake"
        if any(k in ml for k in ("copilot", "ontology ai", "operations agents", "ml model")):
            return "ai"
        if "spark" in ml:
            return "spark"
        if ml.startswith(("ontology", "graph", "digital twin", "fabric planning")):
            return "iq"
        if any(k in ml for k in ("eventhouse", "eventstream", "activator", "rti ", "map ", "anomaly")):
            return "rti"
        if any(k in ml for k in ("data warehouse", "sql database", "sql db", "cosmos")):
            return "db"
        if "power bi" in ml:
            return "pbi"
        if any(k in ml for k in ("data movement", "data orchestration", "dataflow", "airflow", "dbt", "ssis", "vnet")):
            return "df"
        if "graphql" in ml or "user data functions" in ml:
            return "api"
        return "other"

    def short_meter(m):
        for suf in (" Capacity Usage CU", " OD On-Demand Usage CU", " Usage CU"):
            if m.endswith(suf):
                return m[: -len(suf)]
        return m

    d0 = win0.strftime("%Y%m%d")
    crow = [c for c in raw.get("cost_rows") or [] if str(c.get("date") or "") >= d0]
    CUR = next((c.get("currency") for c in crow if c.get("currency")), "USD")

    def money(v, d=2):
        return f"{fn(v, d)} {CUR}"

    arm_caps = raw.get("arm_capacities") or []
    cap_by_rid = {(c.get("id") or "").lower(): c for c in arm_caps}
    total_cost = sum(c["cost"] for c in crow)
    meters, cat_cost = {}, Counter()
    day_cat = defaultdict(Counter)
    cap_cost = Counter()
    for c in crow:
        cat = meter_cat(c["meter"])
        m = meters.setdefault(c["meter"], {"name": short_meter(c["meter"]), "cat": cat, "cost": 0.0, "qty": 0.0, "days": set()})
        m["cost"] += c["cost"]
        m["qty"] += c["qty"]
        if c["cost"] > 0.005:
            m["days"].add(c["date"])
        cat_cost[cat] += c["cost"]
        day_cat[c["date"]][cat] += c["cost"]
        cap_cost[c["rid"]] += c["cost"]
    focus_rid = cap_cost.most_common(1)[0][0] if cap_cost else (next((r for r, c in cap_by_rid.items() if (c.get("state") or "").lower() == "active"), "") if cap_by_rid else "")
    focus = cap_by_rid.get(focus_rid, {})
    focus_name = focus.get("name") or (focus_rid.rsplit("/", 1)[-1] if focus_rid else "—")
    focus_sku = focus.get("sku") or next((c.get("sku") for c in pbi_caps if (c.get("name") or "").lower() == focus_name.lower()), "") or ""
    m_cu = re.search(r"(\d+)", focus_sku or "")
    focus_cu = int(m_cu.group(1)) if m_cu and focus_sku.upper().startswith("F") else 0
    focus_region = (focus.get("location") or "").replace(" ", "").lower()
    focus_pbi = next((c for c in pbi_caps if (c.get("name") or "").lower() == focus_name.lower()), {})
    focus_pbi_id = (focus_pbi.get("id") or "").lower()

    prices = raw.get("prices") or []
    price_cu = next((p.get("price") for p in prices if p.get("region") == focus_region and p.get("type") == "Consumption"
                     and p.get("meter") == "Compute Pool Capacity Usage CU"), None)
    price_src = "Azure Retail Prices API (public pay-as-you-go price, " + (focus_region or "region") + ")"
    pool_rows = [c for c in crow if c["rid"] == focus_rid and meter_cat(c["meter"]) == "idle" and c["qty"] > 0]
    eff_price = (sum(c["cost"] for c in pool_rows) / sum(c["qty"] for c in pool_rows)) if pool_rows else None
    if price_cu is None and eff_price:
        price_cu, price_src = eff_price, "effective invoice price (cost ÷ CU-h of the Compute Pool meter)"
    price_cu = float(price_cu or 0)
    hourly = focus_cu * price_cu
    res = {}
    for p in prices:
        if p.get("region") == focus_region and p.get("type") == "Reservation" and "capacity" in (p.get("meter") or "").lower():
            yrs = 3 if "3" in (p.get("term") or "") else 1
            res[yrs] = float(p.get("price") or 0) / yrs

    # ---------------------------------------------------------------- uptime from Azure Activity Log (suspend/resume)
    def intervals_for(rid, state):
        evl = []
        for e in raw.get("activity_log") or []:
            t = P(e.get("t"))
            if t and (e.get("rid") or "").lower() == rid and (e.get("status") or "").lower() == "succeeded":
                evl.append((t, (e.get("op") or "").lower(), e.get("caller") or ""))
        evl.sort()
        out, cur, seen, ops = [], None, False, []
        for t, op, caller in evl:
            if op.endswith("/resume/action"):
                ops.append(("resume", t, caller))
                if cur is None:
                    cur = t
                seen = True
            elif op.endswith("/suspend/action"):
                ops.append(("suspend", t, caller))
                if cur is None and not seen:
                    cur = win0
                if cur is not None:
                    out.append((cur, t))
                cur = None
                seen = True
            elif op.endswith("/write"):
                ops.append(("write", t, caller))
        if cur is not None:
            out.append((cur, gen))
        basis = "Activity Log"
        if not evl:
            out = [(win0, gen)] if (state or "").lower() == "active" else []
            basis = "no suspend/resume events in the period"
        clipped = [(max(a, win0), min(b, gen)) for a, b in out if b > win0 and a < gen]
        return clipped, ops, basis

    focus_iv, focus_ops, uptime_basis = intervals_for(focus_rid, focus.get("state"))
    on_hours = sum((b - a).total_seconds() for a, b in focus_iv) / 3600
    uptime = on_hours / win_hours
    on_day = Counter()
    for a, b in focus_iv:
        d = a
        while d < b:
            nx = min(b, floor_day(d) + timedelta(days=1))
            on_day[d.strftime("%Y%m%d")] += (nx - d).total_seconds() / 3600
            d = nx
    callers_resume = Counter(pkey(c) for o, t, c in focus_ops if o == "resume")
    callers_suspend = Counter(pkey(c) for o, t, c in focus_ops if o == "suspend")
    susp_times = [t for o, t, c in focus_ops if o == "suspend" and t >= win0]
    auto_suspend = bool(callers_suspend) and all(pkind(k) == "app" for k in callers_suspend)

    # ---------------------------------------------------------------- daily reconciliation: provisioned vs billed vs consumed
    day_cu = defaultdict(lambda: {"billed": 0.0, "pool": 0.0, "cost": 0.0})
    for c in crow:
        if c["rid"] != focus_rid:
            continue
        dc = day_cu[c["date"]]
        dc["cost"] += c["cost"]
        cat = meter_cat(c["meter"])
        if cat != "storage":
            dc["billed"] += c["qty"]
            if cat == "idle":
                dc["pool"] += c["qty"]
    all_days = []
    d = win0
    while d <= gen:
        all_days.append(d.strftime("%Y%m%d"))
        d += timedelta(days=1)
    last_cost_day = max((k for k, v in day_cu.items() if v["cost"] > 0.05), default=None)
    daily = []
    for k in all_days:
        dc = day_cu.get(k, {"billed": 0.0, "pool": 0.0, "cost": 0.0})
        oh = on_day.get(k, 0.0)
        prov = focus_cu * oh
        consumed = max(dc["billed"] - dc["pool"], 0)
        daily.append({"date": k, "on_h": oh, "prov": prov, "billed": dc["billed"], "pool": dc["pool"], "consumed": consumed,
                      "util": (consumed / dc["billed"]) if dc["billed"] > 0.5 else None, "cost": dc["cost"],
                      "ratio": (dc["billed"] / prov) if prov > 0.5 else None, "lag": bool(last_cost_day and k > last_cost_day)})
    cu_billed = sum(x["billed"] for x in daily)
    cu_pool = sum(x["pool"] for x in daily)
    cu_consumed = max(cu_billed - cu_pool, 0)
    util_all = cu_consumed / cu_billed if cu_billed else 0
    cu_cost_focus = sum(c["cost"] for c in crow if c["rid"] == focus_rid and meter_cat(c["meter"]) != "storage")
    idle_cost = cat_cost.get("idle", 0.0)
    consumption_cost = total_cost - idle_cost - cat_cost.get("storage", 0.0)
    billed_days = [x for x in daily if x["cost"] > 0.05 and x["on_h"] > 0.5 and not x["lag"]]
    match_days = [x for x in billed_days if x["consumed"] < 0.02 * max(x["prov"], 1)]
    match_err = max((abs(x["ratio"] - 1) for x in match_days if x["ratio"]), default=None)
    smoothed_extra = sum(max(x["billed"] - x["prov"], 0) for x in billed_days)
    lowuse_days = [x for x in billed_days if x["consumed"] < 0.02 * max(x["prov"], 1)]
    lowuse_cost = sum(x["cost"] for x in lowuse_days)
    on_billed_hours = sum(x["on_h"] for x in billed_days)

    # ---------------------------------------------------------------- on vs used: idle tail per on-interval (activity log + Livy)
    work_times = sorted(e["t"] for e in work_ev if not focus_pbi_id or not e["ws"] or ws_cap.get(e["ws"], focus_pbi_id) in (focus_pbi_id, ""))
    livy_focus = [x for x in livy if x["start"] and (not focus_pbi_id or x["cap"] in (focus_pbi_id, ""))]
    import bisect
    runs = []
    for a, b in focus_iv:
        covered = bool(act0) and a >= act0
        ongoing = b >= gen - timedelta(minutes=1) and (focus.get("state") or "").lower() == "active"
        i0, i1 = bisect.bisect_left(work_times, a), bisect.bisect_right(work_times, b)
        acts = work_times[i0:i1]
        spans = [(max(x["start"], a), min(x["end"] or b, b)) for x in livy_focus if x["start"] < b and (x["end"] or b) > a]
        last_cands = ([acts[-1]] if acts else []) + [s[1] for s in spans]
        first_cands = ([acts[0]] if acts else []) + [s[0] for s in spans]
        last = max(last_cands) if last_cands else None
        first = min(first_cands) if first_cands else None
        hours, h, busy = [], a, 0.0
        while h < b:
            nx = min(h + timedelta(hours=1), b)
            n = bisect.bisect_left(work_times, nx) - bisect.bisect_left(work_times, h)
            sp = any(s0 < nx and s1 > h for s0, s1 in spans)
            hours.append((h, nx, n, sp))
            if n or sp:
                busy += (nx - h).total_seconds() / 3600
            h = nx
        dur = (b - a).total_seconds() / 3600
        tail = ((b - last).total_seconds() / 3600 if last else dur) if covered and not ongoing else None
        runs.append({"a": a, "b": b, "dur": dur, "covered": covered, "ongoing": ongoing, "first": first, "last": last,
                     "n": len(acts), "spark_h": sum((s1 - s0).total_seconds() for s0, s1 in spans) / 3600, "spans": spans,
                     "hours": hours, "idle_h": (dur - busy) if covered else None, "tail": tail})
    BUFFER_H = 1.0
    cov_runs = [r for r in runs if r["covered"] and not r["ongoing"]]
    tail_h = sum(r["tail"] or 0 for r in cov_runs)
    tail_save_h = sum(max((r["tail"] or 0) - BUFFER_H, 0) for r in cov_runs)
    tail_save = tail_save_h * hourly
    idle_cov_h = sum(r["idle_h"] or 0 for r in cov_runs)
    cov_on_h = sum(r["dur"] for r in cov_runs)
    cov_days = max(act_days, 1)
    per_month = 30.0 / cov_days
    whatif = []
    for H in range(17, 24):
        saved, conflicts, days_hit = 0.0, 0, 0
        for r in cov_runs:
            cut = floor_day(r["b"]) + timedelta(hours=H)
            if r["b"] <= cut:
                continue
            st = max(r["a"], cut)
            saved += (r["b"] - st).total_seconds() / 3600
            days_hit += 1
            if (r["last"] and r["last"] > cut):
                conflicts += 1
        whatif.append({"hour": H, "saved_h": saved, "save": saved * hourly, "days": days_hit, "conflicts": conflicts})
    safe = [w for w in whatif if w["conflicts"] == 0 and w["saved_h"] > 0]
    best_safe = max(safe, key=lambda w: w["saved_h"]) if safe else None
    suspend_hour_med = sorted(t.hour + t.minute / 60 for t in susp_times)[len(susp_times) // 2] if susp_times else None

    # ---------------------------------------------------------------- commitments & size (real public prices + real hours)
    payg_year_cu = price_cu * 8760
    breakeven = {y: (v / payg_year_cu) for y, v in res.items()} if payg_year_cu else {}
    cost_src = sources.get("cost") or {}
    cost_ok = cost_src.get("status") == "ok"
    cost_http = cost_src.get("http")
    cost_why = ("Azure Cost Management throttled the requests (HTTP 429). This is temporary: request the report again in a few minutes." if cost_http == 429 else
                "The app has no permission to read costs (HTTP 403): assign Cost Management Reader on the subscription." if cost_http in (401, 403) else
                f"Azure Cost Management did not respond (HTTP {cost_http or 'no response'}). Request the report again in a few minutes.")
    annual_payg_cu = cu_cost_focus * 365.0 / max(days_n, 1) if cost_ok else hourly * on_hours * 365.0 / max(days_n, 1)
    annual_res = {y: focus_cu * v for y, v in res.items()}
    avg_cu_on = (cu_consumed / on_billed_hours) if on_billed_hours else 0
    peak_day = max(billed_days, key=lambda x: x["consumed"] / max(x["on_h"], 0.1), default=None)
    peak_day_avg = (peak_day["consumed"] / max(peak_day["on_h"], 0.1)) if peak_day else 0
    sizes = []
    s = focus_cu // 2
    while cost_ok and s >= 2 and len(sizes) < 3:
        sizes.append({"sku": f"F{s}", "cu": s, "save_month": on_billed_hours * (focus_cu - s) * price_cu * 30.0 / max(days_n, 1),
                      "peak_load": peak_day_avg / s, "avg_load": avg_cu_on / s})
        s //= 2

    # ---------------------------------------------------------------- Spark notebooks
    nb = {}
    for x in livy:
        key = (x["ws"], x["item"])
        n = nb.setdefault(key, {"ws": x["ws"], "item": x["item"], "sessions": 0, "sched": 0, "pipe": 0, "failed": 0, "run": 0.0,
                                "queued": 0.0, "users": Counter(), "first": None, "last": None})
        n["sessions"] += 1
        n["sched"] += x["sched"]
        n["pipe"] += x["pipe"]
        n["failed"] += x["state"].lower() == "failed"
        n["run"] += x["run"]
        n["queued"] += x["queued"]
        n["users"][x["user"]] += 1
        if x["start"]:
            n["first"] = min(n["first"] or x["start"], x["start"])
            n["last"] = max(n["last"] or x["start"], x["start"])
    spark_cost = cat_cost.get("spark", 0.0)
    nb_list = sorted(nb.values(), key=lambda n: -n["run"])
    for n in nb_list:
        n["share"] = n["run"] / livy_total_s if livy_total_s else 0
        n["cost"] = spark_cost * n["share"]
    livy_failed = [x for x in livy if x["state"].lower() == "failed"]

    # ---------------------------------------------------------------- chargeback by workspace (real meter cost x real usage driver)
    DRIVER = {"spark": "Spark execution seconds (Livy)", "ai": "AI/Copilot/Data Agent queries in the activity log",
              "iq": "Ontology/Graph operations in the activity log", "rti": "Eventhouse/Eventstream/KQL operations",
              "db": "Warehouse/SQL operations", "pbi": "Power BI operations", "df": "pipeline/dataflow operations",
              "api": "function/API invocations"}
    drv = defaultdict(Counter)
    for x in livy:
        drv["spark"][x["ws"] or "?"] += x["run"]
    for e in work_ev:
        if e["cat"] in DRIVER and e["cat"] != "spark":
            drv[e["cat"]][e["ws"] or "?"] += 1
    alloc = defaultdict(Counter)
    unassigned = Counter()
    for cat, cost in cat_cost.items():
        if cat == "idle":
            continue
        w = drv.get(cat)
        tot = sum(w.values()) if w else 0
        if cat in DRIVER and tot > 0:
            for ws, v in w.items():
                alloc[ws][cat] += cost * v / tot
        else:
            unassigned[cat] += cost
    direct_ws = {ws: sum(c.values()) for ws, c in alloc.items()}
    direct_total = sum(v for ws, v in direct_ws.items() if ws != "?")
    ws_ev = Counter(e["ws"] for e in work_ev if e["ws"])
    ws_ai = Counter(e["ws"] for e in work_ev if e["ws"] and e["cat"] == "ai")
    ws_spark = Counter()
    for x in livy:
        ws_spark[x["ws"]] += x["run"] / 3600
    ws_items = Counter((i.get("ws") or "").lower() for i in items)
    ws_types = defaultdict(Counter)
    ws_upd = {}
    for i in items:
        w = (i.get("ws") or "").lower()
        ws_types[w][i.get("type") or "?"] += 1
        u = P(i.get("updated"))
        if u and u.year > 2000:
            ws_upd[w] = max(ws_upd.get(w, u), u)
    cb = []
    for w in workspaces:
        wid = (w.get("id") or "").lower()
        cid = ws_cap.get(wid, "")
        d_ = direct_ws.get(wid, 0.0)
        idle_share = idle_cost * (d_ / direct_total) if direct_total else 0.0
        cb.append({"id": wid, "name": ws_name.get(wid) or w.get("name") or wid, "type": w.get("type") or "", "cap": (pcap.get(cid) or {}).get("name") or cid[:8],
                   "sku": (pcap.get(cid) or {}).get("sku") or "", "items": ws_items.get(wid, 0), "events": ws_ev.get(wid, 0),
                   "ai": ws_ai.get(wid, 0), "spark_h": ws_spark.get(wid, 0.0), "direct": d_, "idle": idle_share,
                   "total": d_ + idle_share, "by_cat": alloc.get(wid, Counter()), "updated": ws_upd.get(wid),
                   "types": ws_types.get(wid, Counter())})
    cb.sort(key=lambda r: (-r["total"], -r["events"], r["name"].lower()))
    no_ws_cost = sum(alloc.get("?", Counter()).values())
    unassigned_total = sum(unassigned.values())
    paid_caps = {(c.get("id") or "").lower() for c in pbi_caps if (c.get("sku") or "").upper().startswith("F") and (c.get("state") or "").lower() == "active"}
    idle_ws = [r for r in cb if r["events"] == 0 and r["spark_h"] == 0 and ws_cap.get(r["id"]) in paid_caps and r["type"] != "Personal"]

    # ---------------------------------------------------------------- access and consumption by group (real access lists)
    drv_tot = {c_: sum(w_.values()) for c_, w_ in drv.items()}
    idle_factor = (idle_cost / direct_total) if direct_total else 0.0
    item_direct, ident_direct, ident_ops, ident_last = Counter(), Counter(), Counter(), {}
    ires_ops, ires_cost = defaultdict(Counter), defaultdict(Counter)
    for e in work_ev:
        c_ = e["cat"]
        share = cat_cost.get(c_, 0.0) / drv_tot[c_] if (c_ in DRIVER and c_ != "spark" and drv_tot.get(c_)) else 0.0
        if e["it"]:
            item_direct[(e["ws"], e["it"].lower())] += share
        ident_direct[e["k"]] += share
        ident_ops[e["k"]] += 1
        ident_last[e["k"]] = max(ident_last.get(e["k"], e["t"]), e["t"])
        _rk = (e["ws"], e["it"] or "(no item)")
        ires_ops[e["k"]][_rk] += 1
        ires_cost[e["k"]][_rk] += share
    for x in livy:
        sh = cat_cost.get("spark", 0.0) * x["run"] / drv_tot["spark"] if drv_tot.get("spark") else 0.0
        item_direct[(x["ws"], (x["item"] or "").lower())] += sh
        ident_direct[x["user"]] += sh
        _rk = (x["ws"], x["item"] or "(no item)")
        ires_ops[x["user"]][_rk] += 1
        ires_cost[x["user"]][_rk] += sh
    access = raw.get("access") or []
    gmembers = raw.get("group_members") or {}
    cb_by_id = {r["id"]: r for r in cb}
    SRE_GROUP = "sg-sre-agent-fabric"
    grp = {}
    people = {}
    for a in access:
        wid, pt = a["ws"], a["ptype"]
        where = ("ws", wid) if not a["item_id"] else ("it", wid, (a["item"] or "").lower(), a["item"] or "", a["item_type"] or "")
        if pt == "Group":
            g = grp.setdefault(a["gid"] or a["name"].lower(), {"id": a["gid"], "name": a["name"] or a["gid"], "ws": {}, "items": {},
                                                             "technical": (a["name"] or "").lower() == SRE_GROUP})
            if where[0] == "ws":
                g["ws"][wid] = a["right"]
            else:
                g["items"][(wid, where[2])] = (where[3], where[4], a["right"])
        elif pt == "User" and a["email"]:
            p_ = people.setdefault(a["email"], {"via": set(), "ws": set(), "items": set(), "created": None})
            p_["via"].add("direct")
            (p_["ws"] if where[0] == "ws" else p_["items"]).add(wid if where[0] == "ws" else (wid, where[2]))
    members_known = bool(gmembers)
    for g in grp.values():
        mem = gmembers.get(g["id"]) if g["id"] else None
        g["members"] = mem
        if mem is not None and not g["technical"]:
            for m in mem:
                if not m["upn"]:
                    continue
                p_ = people.setdefault(m["upn"], {"via": set(), "ws": set(), "items": set(), "created": None})
                p_["via"].add(g["name"])
                p_["ws"].update(g["ws"])
                p_["items"].update(g["items"])
                p_["created"] = p_["created"] or P(m.get("created"))
        exp_ws = sum(cb_by_id[w]["total"] for w in g["ws"] if w in cb_by_id)
        exp_it = sum(item_direct.get(k, 0.0) for k in g["items"] if k[0] not in g["ws"]) * (1 + idle_factor)
        g["exposure"] = exp_ws + exp_it
        g["item_ops"] = sum(1 for e in work_ev if e["it"] and ((e["ws"], e["it"].lower()) in g["items"] or e["ws"] in g["ws"]))
        if mem is not None:
            upns = {m["upn"] for m in mem if m["upn"]}
            g["n_members"] = len(upns)
            g["active"] = sum(1 for u in upns if ident_ops.get(u))
            g["member_ops"] = sum(ident_ops.get(u, 0) for u in upns)
            g["member_cost"] = sum(ident_direct.get(u, 0.0) for u in upns) * (1 + idle_factor)
            g["new"] = sum(1 for m in mem if P(m.get("created")) and P(m.get("created")) >= win0)

            def _in_scope(rk, g=g):
                return rk[0] in g["ws"] or (rk[0], rk[1].lower()) in g["items"]
            gr_ops, gr_cost, mdet = Counter(), Counter(), []
            for u in upns:
                own = [rk for rk in ires_ops.get(u, {}) if _in_scope(rk)]
                if not own:
                    continue
                for rk in own:
                    gr_ops[rk] += ires_ops[u][rk]
                    gr_cost[rk] += ires_cost[u][rk]
                top = sorted(own, key=lambda rk: (-ires_cost[u][rk], -ires_ops[u][rk]))[:5]
                mdet.append({"k": u, "ops": sum(ires_ops[u][rk] for rk in own),
                             "cost": sum(ires_cost[u][rk] for rk in own) * (1 + idle_factor),
                             "total_ops": ident_ops.get(u, 0), "total_cost": ident_direct.get(u, 0.0) * (1 + idle_factor),
                             "top": [(rk, ires_ops[u][rk], ires_cost[u][rk] * (1 + idle_factor)) for rk in top]})
            mdet.sort(key=lambda r: (-r["cost"], -r["ops"], r["k"]))
            g["res"] = sorted(((rk, gr_ops[rk], gr_cost[rk] * (1 + idle_factor)) for rk in gr_ops), key=lambda t: (-t[2], -t[1]))
            g["mdetail"] = mdet
            g["member_ops"] = sum(m["ops"] for m in mdet)
            g["member_cost"] = sum(m["cost"] for m in mdet)
            g["active"] = len(mdet)
        else:
            g["n_members"] = g["active"] = g["member_ops"] = g["member_cost"] = g["new"] = None
            g["res"] = g["mdetail"] = None
    grp_list = sorted([g for g in grp.values() if not g["technical"]], key=lambda g: (-(g["member_cost"] or 0), -g["exposure"], g["name"].lower()))
    grp_tech = [g for g in grp.values() if g["technical"]]
    people_list = []
    for upn, p_ in people.items():
        ops = ident_ops.get(upn, 0)
        new = bool(p_["created"] and p_["created"] >= win0)
        people_list.append({"k": upn, "via": sorted(p_["via"], key=lambda v: (v != "direct", v.lower())), "n_ws": len(p_["ws"]), "n_items": len(p_["items"]),
                            "ops": ops, "cost": ident_direct.get(upn, 0.0) * (1 + idle_factor), "last": ident_last.get(upn), "new": new,
                            "top": [(rk, ires_ops[upn][rk], ires_cost[upn][rk] * (1 + idle_factor))
                                    for rk in sorted(ires_ops.get(upn, {}), key=lambda rk: (-ires_cost[upn][rk], -ires_ops[upn][rk]))[:3]],
                            "created": p_["created"]})
    people_list.sort(key=lambda r: (r["ops"] == 0, -r["ops"], r["k"]))
    no_activity = [r for r in people_list if not r["ops"]]
    new_people = [r for r in people_list if r["new"]]
    gm_src = sources.get("group_members") or {}

    # ---------------------------------------------------------------- who: principals, items, heatmap
    princ = {}
    for e in evs:
        p = princ.setdefault(e["k"], {"k": e["k"], "kind": e["kind"], "events": 0, "work": 0, "days": set(), "cats": Counter(),
                                      "acts": Counter(), "items": Counter(), "ws": Counter(), "first": e["t"], "last": e["t"]})
        p["events"] += 1
        p["work"] += e["work"]
        p["days"].add(e["t"].date())
        p["cats"][e["cat"]] += 1
        p["acts"][e["a"]] += 1
        if e["it"]:
            p["items"][e["it"]] += 1
        if e["ws"]:
            p["ws"][e["ws"]] += 1
        p["first"], p["last"] = min(p["first"], e["t"]), max(p["last"], e["t"])
    for x in livy:
        p = princ.setdefault(x["user"], {"k": x["user"], "kind": pkind(x["user"]), "events": 0, "work": 0, "days": set(), "cats": Counter(),
                                         "acts": Counter(), "items": Counter(), "ws": Counter(), "first": x["start"] or gen, "last": x["start"] or gen})
        p.setdefault("spark_h", 0.0)
        p["spark_h"] = p.get("spark_h", 0.0) + x["run"] / 3600
        p["nb"] = p.get("nb", 0) + 1
    humans = sorted([p for p in princ.values() if p["kind"] in ("user", "app")], key=lambda p: -(p["work"] + p.get("nb", 0)))
    nonhuman = sorted([p for p in princ.values() if p["kind"] not in ("user", "app")], key=lambda p: -p["events"])
    item_use = {}
    for e in work_ev:
        if not e["it"]:
            continue
        key = (e["ws"], e["it"])
        r = item_use.setdefault(key, {"ws": e["ws"], "it": e["it"], "itt": e["itt"], "n": 0, "cats": Counter(), "users": set(), "last": e["t"]})
        r["n"] += 1
        r["cats"][e["cat"]] += 1
        r["users"].add(e["k"])
        r["last"] = max(r["last"], e["t"])
    top_items = sorted(item_use.values(), key=lambda r: -r["n"])[:15]
    heat = [[0] * 24 for _ in range(7)]
    for e in work_ev:
        heat[e["t"].weekday()][e["t"].hour] += 1
    heat_max = max((max(r) for r in heat), default=0)
    cat_events = Counter(e["cat"] for e in work_ev)

    # ---------------------------------------------------------------- inventory & governance
    item_types = Counter(i.get("type") or "?" for i in items)
    stale_cut = gen - timedelta(days=90)
    stale_items = [i for i in items if (P(i.get("updated")) or gen) < stale_cut]
    stale_types = Counter(i.get("type") or "?" for i in stale_items)
    refs = []
    for r in raw.get("refreshables") or []:
        ls = P(r.get("last_start"))
        age = (gen - ls).days if ls else None
        status = (r.get("last_status") or "").lower()
        level = "crit" if status == "failed" else ("warn" if (age is not None and age > 60) else "ok")
        err = ""
        if r.get("last_error"):
            m = re.search(r'"code"\s*:\s*"([^"]+)"', str(r["last_error"]))
            err = m.group(1) if m else str(r["last_error"])[:60]
        _rws = r.get("ws") or ""
        _rid = ws_by_name.get(_rws.lower(), "")
        if _rid and not show_ids:
            _rws = ws_name.get(_rid) or _rws
        if "@" in _rws and not show_ids:
            _l, _, _d = _rws.partition("@")
            _rws = f"Personal · {_l[:1]}•••@{_d[:1]}•••"
        refs.append({"name": r.get("name") or "", "ws": _rws, "kind": r.get("kind") or "", "type": r.get("last_type") or "",
                     "last": ls, "age": age, "status": {"completed": "Succeeded", "failed": "Failed", "disabled": "Disabled", "unknown": "In progress"}.get(status, r.get("last_status") or "—"),
                     "sched": bool(r.get("sched_enabled")), "level": level, "err": err})
    refs.sort(key=lambda r: ({"crit": 0, "warn": 1, "ok": 2}[r["level"]], -(r["age"] or 0)))
    ref_failed = [r for r in refs if r["level"] == "crit"]
    ref_stale = [r for r in refs if r["level"] == "warn"]
    ts = raw.get("tenant_settings") or []
    TS_RULES = [
        ("copilot, ai agents and other ai experiences powered by azure openai", "Enables Copilot and Data Agents: this is the source of the “Copilot and AI” meter."),
        ("designated as fabric copilot capacities", "Lets AI usage run on a dedicated capacity so it can be charged back accurately."),
        ("users can create fabric items", "Who can create items that consume CUs on paid capacities."),
        ("service principals can access read-only admin apis", "Required by this report (audit and inventory reads)."),
        ("show user data in the fabric capacity metrics", "Shows users in Capacity Metrics for per-person chargeback."),
        ("standalone, cross-item power bi copilot", "Cross-item Copilot experience: potentially more AI usage."),
        ("operations agents", "Operations agents: new AI meters."),
        ("publish to web", "Risk of reports being exposed publicly."),
        ("guest users can access microsoft fabric", "Guest users consuming tenant capacity."),
        ("users can access data stored in onelake with apps external", "External OneLake reads generate billable transactions."),
    ]
    ts_rows = []
    for key, why in TS_RULES:
        for s_ in ts:
            if key in (s_.get("title") or "").lower():
                scope = ("Groups: " + ", ".join(s_.get("groups") or [])) if s_.get("groups") else ("Entire organization" if s_.get("enabled") else "—")
                ts_rows.append({"title": s_.get("title"), "group": s_.get("group"), "enabled": s_.get("enabled"), "scope": scope, "why": why})
                break
    ts_enabled = sum(1 for s_ in ts if s_.get("enabled"))
    ol = raw.get("onelake") or []
    ol_ok = [o for o in ol if o.get("http") == 200]
    ol_bytes = sum(o.get("bytes") or 0 for o in ol_ok)
    ws_on_cap = Counter(ws_cap.values())
    caps_tbl = []
    for c in pbi_caps:
        cid = (c.get("id") or "").lower()
        arm = next((a for a in arm_caps if (a.get("name") or "").lower() == (c.get("name") or "").lower()), None)
        cost = cap_cost.get((arm or {}).get("id", "").lower(), 0.0) if arm else 0.0
        sku = c.get("sku") or ""
        st = c.get("state") or ""
        nws = ws_on_cap.get(cid, 0)
        if arm and not (arm.get("tags") or {}):
            tagnote = "no tags"
        elif arm:
            tagnote = ", ".join(f"{k}={v}" for k, v in (arm.get("tags") or {}).items())[:60]
        else:
            tagnote = "not an Azure resource"
        if sku.upper().startswith("FT"):
            find, lvl = "Trial capacity", "info"
        elif sku.upper().startswith("PP"):
            find, lvl = "Premium Per User (license, not CUs)", "neutral"
        elif st.lower() in ("suspended", "paused") and nws == 0:
            find, lvl = "Paused with no workspaces: candidate for deletion", "warn"
        elif st.lower() in ("suspended", "paused"):
            find, lvl = "Paused (no compute cost)", "ok"
        elif cid == focus_pbi_id:
            find, lvl = f"Running {pc(uptime, 0)} of the period · {pc(util_all, 0)} used", "warn" if util_all < 0.3 else "ok"
        else:
            find, lvl = "Active", "ok"
        mcu = re.search(r"(\d+)", sku)
        caps_tbl.append({"name": c.get("name") or "", "sku": sku, "state": st, "region": c.get("region") or "", "admins": c.get("admins"),
                         "ws": nws, "items": sum(1 for i in items if (i.get("cap") or "").lower() == cid), "cost": cost, "tags": tagnote,
                         "finding": find, "lvl": lvl, "arm": bool(arm), "rg": (arm or {}).get("rg") or "",
                         "hourly_if_on": (int(mcu.group(1)) * price_cu) if (mcu and sku.upper().startswith("F") and not sku.upper().startswith("FT")) else None})
    paused_empty = [c for c in caps_tbl if c["lvl"] == "warn" and c["state"].lower() in ("suspended", "paused")]
    trials = [c for c in caps_tbl if c["sku"].upper().startswith("FT")]
    untagged = [c for c in caps_tbl if c["arm"] and c["tags"] == "no tags"]
    cm_ws = next((w for w in workspaces if "capacity metrics" in (w.get("name") or "").lower()), None)
    cm_items = [i for i in items if cm_ws and (i.get("ws") or "").lower() == (cm_ws.get("id") or "").lower()]
    cm_installed = bool(cm_ws) and any((i.get("type") or "") in ("SemanticModel", "App") for i in cm_items)

    # ================================================================== v5 STYLE (same visual world as v4)
    CSS = """
:root{--ink:#0f1f2e;--muted:#4b5e71;--line:#d5e2ec;--line-soft:#e6edf2;--paper:#f3f7fa;--panel:#fff;--teal:#117865;--teal-deep:#0b5345;
--teal-soft:#e6f4f1;--on:#cfe9e3;--idle:#d99a2b;--idle-soft:#fdf1dc;--spark:#6a3d9a;--amber:#a14306;--amber-soft:#fef0c7;
--crit:#b42318;--crit-soft:#fee4e2;--ok:#067647;--ok-soft:#dcfae6;--info:#175cd3;--info-soft:#d1e9ff;--r:12px;
--hero:#0b5345;--hero-deep:#062e26;--hero-muted:#cfe8e0;--hero-line:rgba(255,255,255,.24);--focus:#0b6b58;
--shadow:0 1px 2px rgba(16,24,40,.06),0 10px 24px -12px rgba(16,24,40,.28);
--fade:linear-gradient(90deg,#fff 30%,rgba(255,255,255,0)) left/32px 100% no-repeat local,linear-gradient(270deg,#fff 30%,rgba(255,255,255,0)) right/32px 100% no-repeat local,radial-gradient(farthest-side at 0 50%,rgba(16,24,40,.16),rgba(16,24,40,0)) left/12px 100% no-repeat scroll,radial-gradient(farthest-side at 100% 50%,rgba(16,24,40,.16),rgba(16,24,40,0)) right/12px 100% no-repeat scroll;
--serif:"Palatino Linotype",Palatino,Georgia,serif;--sans:"Aptos","Segoe UI",-apple-system,sans-serif;--mono:"Cascadia Mono",Consolas,monospace}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%;scroll-behavior:smooth;scroll-padding-top:72px;scrollbar-color:#b4c6d3 var(--paper)}
body{margin:0;background:var(--paper);color:var(--ink);font:15px/1.55 var(--sans);font-variant-numeric:tabular-nums}
::selection{background:#bfe3d9;color:var(--ink)}
a{color:var(--teal-deep);text-underline-offset:3px}
.wrap{max-width:1240px;margin:0 auto;padding-left:32px;padding-right:32px}
.topbar{background:var(--hero-deep);color:#fff}
.topbar .wrap{display:flex;align-items:center;gap:16px;min-height:56px}
.mark{display:inline-flex;align-items:center;gap:10px;font-weight:700;font-size:16px;letter-spacing:-.01em;white-space:nowrap}
.mark i{display:grid;place-items:center;width:28px;height:28px;border-radius:7px;background:#fff}
.mark svg{width:18px;height:18px;fill:var(--teal-deep)}
.ctx{min-width:0;padding-left:16px;border-left:1px solid var(--hero-line);color:var(--hero-muted);font-size:14px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.top-acts{margin-left:auto;display:flex;align-items:center;gap:8px}
.tag{font-size:12.5px;font-weight:600;color:#e6f4f1;border:1px solid var(--hero-line);border-radius:999px;padding:4px 12px;white-space:nowrap}
.print{display:inline-flex;align-items:center;gap:8px;min-height:36px;padding:0 14px;border:0;border-radius:8px;background:#fff;color:var(--teal-deep);font:inherit;font-size:14px;font-weight:700;cursor:pointer}
.print:hover{background:var(--teal-soft)}
.print svg{width:16px;height:16px;fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}
.hero{background:var(--hero);color:#fff;padding:40px 0 104px}
.hero-grid{display:grid;grid-template-columns:minmax(0,1fr) 320px;gap:24px 48px;align-items:start}
.hero h1{font-family:var(--serif);font-weight:700;font-size:clamp(30px,3.1vw,42px);line-height:1.12;letter-spacing:-.01em;margin:0 0 16px;text-wrap:balance}
.lead{margin:0 0 12px;max-width:66ch;font-size:18px;line-height:1.5}
.lead .idle-t{color:#f8c96a}
.prov{margin:0;max-width:68ch;color:var(--hero-muted);font-size:14px}
.meta{grid-column:1/-1;display:flex;flex-wrap:wrap;gap:8px;margin:0;padding:0;list-style:none}
.meta li{font-size:13px;color:var(--hero-muted);border:1px solid var(--hero-line);border-radius:999px;padding:4px 12px}
.meta b{color:#fff;font-weight:600}.meta .live{background:rgba(255,255,255,.12);color:#fff;font-weight:600}
.verdict{border:1px solid var(--hero-line);background:rgba(255,255,255,.07);border-radius:14px;padding:20px 24px}
.verdict p{margin:0}.verdict .vk{font-size:13px;font-weight:600;color:var(--hero-muted)}
.verdict .vw{font-family:var(--serif);font-size:28px;line-height:1.15;font-weight:700;margin:4px 0 8px;color:#fcd17d}
.verdict.crit .vw{color:#ffb5a8}.verdict.ok .vw{color:#a6f4c5}.verdict.info .vw{color:#c9e3ff}
.verdict .vl{font-size:14px;color:var(--hero-muted)}.verdict .vl+.vl{margin-top:4px}.verdict .vl b{color:#fff}
.dist{grid-column:1/-1}
.stack{display:flex;gap:2px;height:14px;border-radius:999px;overflow:hidden;background:rgba(255,255,255,.14)}
.stack span{display:block;height:100%;min-width:3px;transform-origin:left;animation:grow .8s cubic-bezier(.2,.7,.2,1) both}
@keyframes grow{from{transform:scaleX(0)}to{transform:scaleX(1)}}
.legend{display:flex;flex-wrap:wrap;gap:8px 28px;margin:12px 0 0;padding:0;list-style:none;font-size:14px;color:var(--hero-muted)}
.legend li{display:inline-flex;align-items:center;gap:8px}.legend b{color:#fff}
.sw{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:6px;vertical-align:0}.legend .sw{margin:0}
.kpis{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:16px;margin:-64px 0 0;padding:0;list-style:none;position:relative;z-index:2}
.kpi{background:#fff;border:1px solid var(--line);border-radius:var(--r);padding:16px 20px;box-shadow:var(--shadow);min-width:0}
.kpi .v{display:block;font-size:clamp(24px,2.2vw,30px);line-height:1.15;font-weight:700;letter-spacing:-.02em;white-space:nowrap}
.kpi .v small{font-size:14px;font-weight:600;letter-spacing:0;margin-left:5px;color:var(--muted)}
.kpi .k{display:block;margin-top:8px;font-size:14px;font-weight:600}
.kpi .s{display:block;margin-top:2px;font-size:13px;color:var(--muted)}
.kpi.accent .v{color:var(--teal-deep)}
#resumen{margin:0}
nav.toc{position:sticky;top:0;z-index:10;margin-top:24px;background:rgba(243,247,250,.97);border-bottom:1px solid var(--line)}
nav.toc ol{position:relative;display:flex;max-width:1240px;margin:0 auto;padding:8px 23px;list-style:none;overflow-x:auto;scrollbar-width:none;background:linear-gradient(90deg,var(--paper) 30%,rgba(243,247,250,0)) left/32px 100% no-repeat local,linear-gradient(270deg,var(--paper) 30%,rgba(243,247,250,0)) right/32px 100% no-repeat local,radial-gradient(farthest-side at 0 50%,rgba(16,24,40,.12),rgba(16,24,40,0)) left/12px 100% no-repeat scroll,radial-gradient(farthest-side at 100% 50%,rgba(16,24,40,.12),rgba(16,24,40,0)) right/12px 100% no-repeat scroll}
nav.toc ol::-webkit-scrollbar{display:none}
nav.toc a{display:block;white-space:nowrap;padding:8px 9px;border-radius:8px;color:var(--muted);text-decoration:none;font-size:13.5px;font-weight:600}
nav.toc a:hover{background:#e3edf2;color:var(--ink)}nav.toc a[aria-current]{background:var(--teal-soft);color:var(--teal-deep)}
.body{padding-top:32px;padding-bottom:64px}
section{margin:0 0 48px}
h2{font-family:var(--serif);font-size:24px;line-height:1.25;margin:0 0 8px;text-wrap:balance}
h3{font-size:16px;line-height:1.35;margin:0 0 12px}
p.sub{margin:0 0 16px;color:var(--muted);max-width:72ch}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:var(--r);padding:24px}
.panel+.panel,.panel+.tbl-wrap,.tbl-wrap+.panel,.tbl-wrap+.tbl-wrap,.split+.panel,.panel+.split,.split+.tbl-wrap{margin-top:16px}
.panel .tbl-wrap{border-width:1px 0;border-radius:0;margin:0 -24px}
.panel>.tbl-wrap:last-child{border-bottom:0;margin-bottom:-24px;border-radius:0 0 var(--r) var(--r)}
.panel .tbl-wrap :is(th,td):first-child{padding-left:24px}.panel .tbl-wrap :is(th,td):last-child{padding-right:24px}
.facts{display:flex;flex-wrap:wrap;gap:8px 32px;margin:20px 0 0;padding:16px 0 0;border-top:1px solid var(--line);list-style:none}
.facts li{font-size:13px;color:var(--muted)}.facts b{display:block;color:var(--ink);font-size:17px}
.save-strip{display:flex;flex-wrap:wrap;gap:8px 32px;align-items:center;background:var(--teal-soft);border:1px solid #b9dcd2;border-radius:var(--r);padding:16px 24px;margin:0 0 16px}
.save-strip .big{font-family:var(--serif);font-size:30px;font-weight:700;line-height:1.1;color:var(--teal-deep);white-space:nowrap}
.save-strip p{margin:0;font-size:14px;max-width:72ch;color:#24394a}
.afilter{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:0 0 12px}
.afilter button{font:inherit;font-size:13px;font-weight:600;min-height:32px;padding:0 12px;border:1px solid var(--line);border-radius:999px;background:#fff;color:#33495c;cursor:pointer}
.afilter button:hover{border-color:var(--teal)}.afilter button[aria-pressed=true]{background:var(--teal-deep);border-color:var(--teal-deep);color:#fff}
.acount{margin-left:auto;font-size:13px;color:var(--muted)}
.actions{list-style:none;margin:0;padding:0;display:grid;gap:12px}
.actions li{display:grid;grid-template-columns:28px minmax(0,1fr) 176px;gap:4px 16px;align-items:start;background:#fff;border:1px solid var(--line);border-radius:var(--r);padding:16px 20px}
.actions li[hidden]{display:none}
.actions li::before{content:attr(data-n);display:grid;place-items:center;width:28px;height:28px;border-radius:50%;background:var(--teal-soft);color:var(--teal-deep);font-weight:700;font-size:13px;grid-row:1/3}
.actions li:not([data-n])::before{visibility:hidden}
.actions h3{margin:0 0 4px;font-size:16px}
.actions p{margin:0;font-size:14px;color:var(--muted)}
.actions .ev{grid-column:2/3;font-size:13px;color:#33495c;margin-top:8px}
.actions .ev code{font-family:var(--mono);font-size:12px;background:#f1f5f8;border-radius:4px;padding:1px 5px}
.actions .val{grid-column:3;grid-row:1/3;text-align:right}
.actions .val b{display:block;font-size:22px;line-height:1.2;font-weight:700;letter-spacing:-.01em;color:var(--teal-deep);white-space:nowrap}
.actions .val span{font-size:12.5px;color:var(--muted)}
.notice{display:flex;gap:12px;align-items:flex-start;background:var(--info-soft);border:1px solid #b2ddff;border-radius:var(--r);padding:12px 16px;margin:0 0 16px;font-size:14px}
.notice.warn{background:#fffaeb;border-color:#fedf89}
.notice b{display:block;margin-bottom:2px}.notice p{margin:0}
.chart{overflow-x:auto;-webkit-overflow-scrolling:touch;background:var(--fade)}
.chart svg{display:block;min-width:860px;width:100%;height:auto}
.chart text{font-family:var(--sans);fill:#4b5e71;font-size:13px}
.chart .lbl{fill:#33495c}
.keys{display:flex;flex-wrap:wrap;gap:8px 20px;margin:12px 0 0;padding:0;list-style:none;font-size:13px;color:var(--muted)}
.tbl-wrap{overflow-x:auto;border:1px solid var(--line);border-radius:var(--r);background:var(--fade),#fff}
table{width:100%;border-collapse:collapse;font-size:14px}
th,td{padding:12px;text-align:left;border-bottom:1px solid var(--line-soft);vertical-align:top}
thead th{background:#f5f9f8;font-size:12.5px;font-weight:600;color:var(--muted);white-space:nowrap;border-bottom-color:var(--line)}
tbody tr:hover{background:#f2faf7}
tfoot td{font-weight:700;background:#f5f9f8;border-bottom:0;border-top:1px solid var(--line)}
table:not(:has(tfoot)) tbody tr:last-child td{border-bottom:0}
td.num,th.num{text-align:right;white-space:nowrap}
table.dense{font-size:13.5px}table.dense th,table.dense td{padding:8px 12px}
.sortbtn{all:unset;cursor:pointer;display:inline-flex;gap:6px;align-items:center;border-radius:4px}
.sortbtn::after{content:"";width:8px;height:5px;background:currentColor;clip-path:polygon(0 0,100% 0,50% 100%);opacity:.35}
.sortbtn:hover,th[aria-sort] .sortbtn{color:var(--ink)}th[aria-sort] .sortbtn::after{opacity:1}
th[aria-sort=ascending] .sortbtn::after{transform:rotate(180deg)}
.id{font-family:var(--mono);font-size:12px;color:#2b4458}
.cell-strong{font-weight:600}.cell-sub{display:block;font-size:12.5px;color:var(--muted)}
.nw{white-space:nowrap}.muted{color:var(--muted)}
.mini{display:flex;width:120px;height:8px;border-radius:4px;overflow:hidden;background:#e9eff3;margin-top:6px}
.mini span{display:block;height:100%}
.pill{display:inline-block;border-radius:999px;padding:2px 10px;font-size:12.5px;font-weight:600;white-space:nowrap}
.pill.ok{background:var(--ok-soft);color:var(--ok)}.pill.warn{background:#fef0c7;color:#93370d}
.pill.crit{background:var(--crit-soft);color:var(--crit)}.pill.info{background:var(--info-soft);color:var(--info)}
.pill.neutral{background:#eaecf0;color:#344054}
.split{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:16px;align-items:start}
.split>*{margin-top:0!important;min-width:0}
.split.wide{grid-template-columns:minmax(0,3fr) minmax(0,2fr)}
.duo{display:grid;gap:24px;margin-top:24px}.duo>*{min-width:0}
.bars{list-style:none;margin:0;padding:0;display:grid;gap:12px}
.bars li{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:4px 12px;font-size:14px}
.bars .track{grid-column:1/-1;height:8px;border-radius:999px;background:#e9eff3;overflow:hidden}
.bars .fill{height:100%;border-radius:999px;min-width:2px}
.kv{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:1px;margin:0;padding:0;list-style:none;background:#fff;border:1px solid var(--line);border-radius:var(--r);overflow:hidden}
.kv li{padding:16px 20px;font-size:13px;color:var(--muted);min-width:0;box-shadow:-1px 0 0 var(--line-soft),0 -1px 0 var(--line-soft)}
.kv b{display:block;margin:2px 0;font-size:24px;line-height:1.25;font-weight:700;letter-spacing:-.01em;color:var(--ink)}
.kv.types{grid-template-columns:repeat(6,minmax(0,1fr))}.kv.cols2{grid-template-columns:repeat(2,minmax(0,1fr))}
.panel .kv{border:0;border-radius:0;margin:0 -16px}.panel .kv li{padding:12px 16px}.panel .kv b{font-size:22px}
.heat td{padding:0;border:0;width:3.9%;height:22px}
.heat th{font-size:12px;font-weight:600;color:var(--muted);padding:2px 6px;border:0;background:none}
.heat td span{display:block;height:20px;margin:1px;border-radius:3px}
.toolbar{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:0 0 12px}
.btn{display:inline-flex;align-items:center;min-height:36px;padding:0 14px;font:inherit;font-size:13.5px;font-weight:600;border:1px solid var(--teal);border-radius:8px;color:var(--teal-deep);background:#fff;cursor:pointer;text-decoration:none}
.btn:hover{background:var(--teal-soft)}
.qs{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.qs article{background:#fff;border:1px solid var(--line);border-radius:var(--r);padding:20px 24px}
.qs h3{font-size:15px;color:var(--teal-deep);margin:0 0 12px}
.qs ul{list-style:none;margin:0;padding:0;display:grid;gap:8px}
.qs li{display:grid;grid-template-columns:1fr auto;gap:12px;align-items:start;font-size:14px}
.qs li button{font:inherit;font-size:12.5px;font-weight:600;min-height:28px;padding:0 10px;border:1px solid var(--line);border-radius:6px;background:#f6faf9;color:#33495c;cursor:pointer}
.qs li button:hover{border-color:var(--teal);color:var(--teal-deep)}
.method{display:grid;grid-template-columns:1fr 1fr;gap:24px;font-size:14px}
.method ul{margin:0;padding-left:20px}.method li{margin:0 0 8px}
details.panel>summary{cursor:pointer}details.panel>summary::marker{color:var(--teal)}
footer{color:var(--muted);font-size:13px;padding:24px 0 40px;border-top:1px solid var(--line)}
:focus-visible,.sortbtn:focus-visible{outline:3px solid var(--focus);outline-offset:2px}
.topbar :focus-visible,.hero :focus-visible{outline-color:#f8c96a}
@media (max-width:1100px){.kpis{grid-template-columns:repeat(3,minmax(0,1fr))}.hero-grid{grid-template-columns:minmax(0,1fr) 280px}}
@media (max-width:900px){.wrap{padding-left:16px;padding-right:16px}nav.toc ol{padding:8px 7px}.ctx{display:none}
.hero{padding:28px 0 88px}.hero-grid{grid-template-columns:minmax(0,1fr)}.lead{font-size:17px}
.kpis{grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.kpi{padding:14px 16px}.kpi:last-child:nth-child(odd){grid-column:1/-1}
.split,.split.wide,.method,.qs{grid-template-columns:minmax(0,1fr)}.kv,.kv.types{grid-template-columns:repeat(2,minmax(0,1fr))}
.actions li{grid-template-columns:28px minmax(0,1fr)}.actions .val{grid-column:2;grid-row:auto;text-align:left}.actions .ev{grid-column:2}
.acount{width:100%;margin-left:0}}
@media (max-width:600px){table:has(thead th:nth-child(5)){min-width:620px}table:has(thead th:nth-child(5)) td:first-child{min-width:190px}}
@media (max-width:520px){.tag{display:none}.print{padding:0 10px}.print .lbl{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}h2{font-size:22px}}
@media (prefers-reduced-motion:reduce){.stack span{animation:none}html{scroll-behavior:auto}}
@media print{*{-webkit-print-color-adjust:exact;print-color-adjust:exact}html,body{background:#fff}body{font-size:12.5px}
nav.toc,.toolbar,.qs button,.print,.afilter{display:none!important}
.topbar{background:#fff;color:var(--ink);border-bottom:1px solid var(--line)}.topbar .wrap{min-height:40px}.mark i{background:var(--teal-deep)}.mark svg{fill:#fff}
.ctx,.tag{display:block;color:var(--muted);border-color:var(--line)}
.hero{padding:24px 0 84px}.hero-grid{grid-template-columns:minmax(0,1fr) 230px;gap:16px 24px}.hero h1{font-size:28px}.lead{font-size:15px}
.verdict{padding:14px 16px}.verdict .vw{font-size:22px}.stack span{animation:none}
.kpis{grid-template-columns:repeat(5,minmax(0,1fr));gap:8px;margin-top:-60px}.kpi{box-shadow:none;padding:12px}.kpi .v{font-size:18px}.kpi .v small{font-size:12px}.kpi .k{font-size:12px}.kpi .s{font-size:12px}
.kpi:last-child:nth-child(odd){grid-column:auto}
.body{padding-top:24px}section{margin-bottom:28px}h2{font-size:20px}
.panel,.kpi,.kv,.actions li,.qs article,.verdict,.save-strip,.bars li,tr,p.sub{break-inside:avoid}h2,h3,p.sub{break-after:avoid}
thead{display:table-header-group}.tbl-wrap,.chart{overflow:visible;background:#fff}.chart svg{min-width:0}
table,table.dense{font-size:12px}th,td,table.dense th,table.dense td{padding:6px 7px}footer{padding:12px 0}}
"""

    JS = """
(function(){
  function all(s,r){return [].slice.call((r||document).querySelectorAll(s));}
  all('table[data-sortable]').forEach(function(table){
    var ths=table.querySelectorAll('thead th[data-sort]');
    ths.forEach(function(th){
      var btn=th.querySelector('.sortbtn'); if(!btn) return;
      btn.addEventListener('click',function(){
        var dir=th.getAttribute('aria-sort')==='descending'?'ascending':'descending';
        ths.forEach(function(o){o.removeAttribute('aria-sort');}); th.setAttribute('aria-sort',dir);
        var col=+th.dataset.col, num=th.dataset.sort==='num', tb=table.tBodies[0], rows=[].slice.call(tb.rows);
        rows.sort(function(a,b){
          var x=a.cells[col].dataset.v||a.cells[col].textContent, y=b.cells[col].dataset.v||b.cells[col].textContent;
          if(num){x=parseFloat(x)||0;y=parseFloat(y)||0;return dir==='ascending'?x-y:y-x;}
          return dir==='ascending'?x.localeCompare(y,'en'):y.localeCompare(x,'en');
        });
        rows.forEach(function(r){tb.appendChild(r);});
      });
    });
  });
  function dl(name,text){
    var blob=new Blob(['\\ufeff'+text],{type:'text/csv;charset=utf-8'});
    var a=document.createElement('a'); a.href=URL.createObjectURL(blob); a.download=name;
    document.body.appendChild(a); a.click(); setTimeout(function(){URL.revokeObjectURL(a.href); a.remove();},500);
  }
  all('[data-csv]').forEach(function(b){
    b.addEventListener('click',function(){ var s=document.getElementById(b.dataset.csv); if(s) dl(b.dataset.name, s.textContent); });
  });
  all('[data-copy]').forEach(function(b){
    b.addEventListener('click',function(){
      var t=b.dataset.copy, o=b.textContent, done=function(){b.textContent='Copied';setTimeout(function(){b.textContent=o;},1500);};
      if(navigator.clipboard) navigator.clipboard.writeText(t).then(done,done); else done();
    });
  });
  all('[data-print]').forEach(function(b){b.addEventListener('click',function(){window.print();});});
  var af=document.querySelector('.afilter'), list=document.querySelector('ol.actions');
  if(af&&list){
    var cnt=af.querySelector('.acount'), items=all('li[data-kind]',list);
    af.addEventListener('click',function(ev){
      var b=ev.target.closest('button[data-kind]'); if(!b) return;
      all('button[data-kind]',af).forEach(function(o){o.setAttribute('aria-pressed',String(o===b));});
      var k=b.dataset.kind, n=0;
      items.forEach(function(li){var on=k==='all'||li.dataset.kind===k; li.hidden=!on; if(on) n++;});
      cnt.textContent=(n===items.length?'':n+' of ')+items.length+' actions';
    });
  }
  var shown=[];
  window.addEventListener('beforeprint',function(){
    all('details:not([open])').forEach(function(d){d.open=true;shown.push(d);});
    all('ol.actions li[hidden]').forEach(function(li){li.hidden=false;shown.push(li);});
  });
  window.addEventListener('afterprint',function(){
    shown.forEach(function(x){if(x.tagName==='DETAILS') x.open=false; else x.hidden=true;}); shown=[];
  });
  var links={};
  all('nav.toc a').forEach(function(a){links[a.hash.slice(1)]=a;});
  if('IntersectionObserver' in window){
    var io=new IntersectionObserver(function(es){
      es.forEach(function(e){
        if(!e.isIntersecting) return;
        Object.keys(links).forEach(function(k){links[k].removeAttribute('aria-current');});
        var a=links[e.target.id]; if(!a) return;
        a.setAttribute('aria-current','true');
        var ol=a.closest('ol'); if(ol.scrollWidth>ol.clientWidth) ol.scrollLeft=a.parentNode.offsetLeft-24;
      });
    },{rootMargin:'-15% 0px -75% 0px'});
    Object.keys(links).forEach(function(k){var s=document.getElementById(k); if(s) io.observe(s);});
  }
})();
"""

    def th(label, col=None, kind=None, cls=""):
        c = f' class="{cls}"' if cls else ""
        if col is None:
            return f"<th{c}>{label}</th>"
        return f'<th{c} data-col="{col}" data-sort="{kind or "txt"}"><button type="button" class="sortbtn">{label}</button></th>'

    def pill(lvl, text):
        return f'<span class="pill {lvl}">{E(text)}</span>'

    def cat_sw(cat):
        return f'<span class="sw" style="background:{CATS.get(cat, CATS["other"])[1]}"></span>'

    def ws_label(wid):
        if not wid or wid == "?":
            return "No workspace in the event"
        return ws_name.get(wid) or wid[:8]

    def dlabel(k):
        dt = datetime.strptime(k, "%Y%m%d")
        return f"{WD[dt.weekday()]} {dmon(dt)}"

    # ================================================================== v5 ACTIONS (every figure comes from the analysis above)
    try:
        from zoneinfo import ZoneInfo
        mad_off = int(gen.astimezone(ZoneInfo(LOCAL_TIMEZONE)).utcoffset().total_seconds() // 3600)
    except Exception:
        mad_off = 0
    mad_lbl = f"UTC+{mad_off}"

    def hmad(H):
        return f"{H:02d}:00 UTC ({(H + mad_off) % 24:02d}:00 {LOCAL_TIMEZONE.split('/')[-1].replace('_', ' ')})"

    actions = []
    headline_save = 0.0
    if cov_runs and hourly and tail_save_h > 0:
        m_tail = tail_save * per_month
        headline_save += m_tail
        worst = sorted(cov_runs, key=lambda r: -(r["tail"] or 0))[:3]
        ev = "; ".join(f"{dlabel(r['b'].strftime('%Y%m%d'))}: last activity {hhmm(r['last'])}, paused {hhmm(r['b'])} → {fn(r['tail'], 1)} h" for r in worst)
        actions.append({"kind": "save", "title": "Pause the capacity once it is no longer in use",
                        "why": (f"The capacity is currently paused {'automatically' if auto_suspend else 'manually'} at around {hhmm(susp_times[-1]) if susp_times else '—'} UTC, "
                                f"but real work finishes earlier. Across {len(cov_runs)} running periods with recorded activity, the capacity stayed on for "
                                f"{fn(tail_h, 1)} h after the last activity. Pausing 1 h after the last activity saves "
                                f"{fn(tail_save_h, 1)} h × {money(hourly)}/h."),
                        "evidence": ev, "value": m_tail, "unit": "/month estimated", "src": "Activity Log + Fabric activity log + Spark + public price"})
    if best_safe and best_safe["save"] > 0:
        actions.append({"kind": "save", "title": f"Simpler alternative: bring the automatic pause forward to {hmad(best_safe['hour'])}",
                        "why": (f"With that fixed time, no work would have been cut off in the observed period and "
                                f"{fn(best_safe['saved_h'], 1)} running hours would have been avoided. Not added to the total because it overlaps with the previous action."),
                        "evidence": " · ".join(f"{hmad(w['hour']).split(' (')[0]}: {fn(w['saved_h'], 1)} h, {w['conflicts']} day(s) with work cut off" for w in whatif if w["saved_h"] > 0),
                        "value": best_safe["save"] * per_month, "unit": "/month (alternative)", "src": "Activity Log + Fabric activity log"})
    if lowuse_days:
        actions.append({"kind": "save", "title": f"Avoid starting the capacity on days with no load ({len(lowuse_days)} days)",
                        "why": ("On these days the invoice shows practically only the “Compute Pool” meter (capacity running, nothing consumed). "
                                "Check with the team whether it was started for tests or demos that could have been grouped together."),
                        "evidence": ", ".join(f"{dlabel(x['date'])}: {fn(x['on_h'], 1)} h, {money(x['cost'])}" for x in lowuse_days),
                        "value": lowuse_cost, "unit": "in the period (to validate)", "src": "Azure Cost Management + Activity Log"})
    if res.get(1) and breakeven.get(1):
        be = breakeven[1]
        if uptime < be:
            extra = annual_res[1] - annual_payg_cu
            actions.append({"kind": "avoid", "title": "Do not buy a capacity reservation with the current usage pattern",
                            "why": (f"A 1-year reservation costs {money(res[1], 0)} per CU/year ({money(annual_res[1], 0)} for {focus_sku}). "
                                    f"It only pays off if the capacity runs more than {pc(be, 0)} of the time; it currently runs {pc(uptime, 0)} of the time. "
                                    f"At the current rate, pay-as-you-go costs {money(annual_payg_cu, 0)}/year"
                                    f"{'' if cost_ok else ' (running hours × public price, no invoice in this run)'}."),
                            "evidence": f"Pay-as-you-go price {money(price_cu, 4)}/CU-h · {price_src}",
                            "value": max(extra, 0), "unit": "/year of overspend avoided",
                            "src": "Azure Retail Prices + Cost Management" if cost_ok else "Azure Retail Prices + Activity Log"})
        else:
            sav = annual_payg_cu - annual_res[1]
            actions.append({"kind": "save", "title": "Consider a 1-year capacity reservation",
                            "why": f"The capacity runs {pc(uptime, 0)} of the time, above the {pc(be, 0)} break-even threshold.",
                            "evidence": f"Annualized pay-as-you-go {money(annual_payg_cu, 0)} vs reservation {money(annual_res[1], 0)}",
                            "value": sav, "unit": "/year", "src": "Azure Retail Prices + Cost Management"})
    if sizes and peak_day_avg and sizes[0]["peak_load"] < 0.8:
        s0 = sizes[0]
        actions.append({"kind": "scenario", "title": f"Scenario: downsize from {focus_sku} to {s0['sku']} (validate peaks)",
                        "why": (f"On average {fn(avg_cu_on, 1)} CUs were consumed per running hour; on the busiest day "
                                f"({dlabel(peak_day['date'])}) the average was {fn(peak_day_avg, 1)} CUs, {pc(s0['peak_load'], 0)} of an {s0['sku']}. "
                                "These are hourly averages: before changing, review peaks and throttling in the Capacity Metrics app"
                                + (", which is already installed." if cm_installed else " (worth installing).")),
                        "evidence": f"Billed CU-h − “Compute Pool” CU-h per day · {fn(on_billed_hours, 1)} running hours with cost",
                        "value": s0["save_month"], "unit": "/month if confirmed", "src": "Cost Management (CU-h quantities)"})
    sched_nb = [n for n in nb_list if n["sched"] >= 3]
    for n in sched_nb[:2]:
        actions.append({"kind": "review", "title": f"Review the frequency of the scheduled notebook “{n['item']}”",
                        "why": (f"{n['sched']} scheduled runs and {fn(n['run'] / 3600, 1)} h of Spark in the period "
                                f"({pc(n['share'], 0)} of Spark time). While it runs, the capacity cannot be paused."),
                        "evidence": f"Workspace {ws_label(n['ws'])} · first {dmon(n['first'], ' %H:%M') if n['first'] else '—'}, last {dmon(n['last'], ' %H:%M') if n['last'] else '—'} UTC",
                        "value": n["cost"], "unit": "Spark attributed in the period", "src": "Spark/Livy API + Spark meter"})
    for c in paused_empty:
        if c["hourly_if_on"]:
            actions.append({"kind": "risk", "title": f"Delete or tag the paused capacity “{c['name']}” ({c['sku']})",
                            "why": (f"It is paused and has no workspaces assigned. If someone resumed it by mistake it would cost "
                                    f"{money(c['hourly_if_on'])}/h ({money(c['hourly_if_on'] * 24 * 30, 0)}/month while running)."),
                            "evidence": f"Resource group {c['rg'] or '—'} · {c['tags']}",
                            "value": c["hourly_if_on"] * 24 * 30, "unit": "/month of risk avoided", "src": "ARM + Fabric Admin API"})
    if livy_failed:
        wasted = sum(x["run"] for x in livy_failed) / 3600
        actions.append({"kind": "review", "title": f"Fix {len(livy_failed)} failed Spark sessions",
                        "why": f"They consumed {fn(wasted, 1)} h of Spark without a useful result.",
                        "evidence": ", ".join(sorted({x['item'] for x in livy_failed}))[:240],
                        "value": spark_cost * (sum(x["run"] for x in livy_failed) / livy_total_s) if livy_total_s else None,
                        "unit": "Spark attributed", "src": "Spark/Livy API"})
    ai_cost = cat_cost.get("ai", 0.0)
    cop_set = next((r for r in ts_rows if "copilot capacities" in (r["title"] or "").lower()), None)
    if ai_cost > 0:
        actions.append({"kind": "gov", "title": "Move AI usage to a designated Copilot capacity",
                        "why": (f"AI (Copilot, Data Agents, Ontology AI) already costs {money(ai_cost)} ({pc(ai_cost / total_cost if total_cost else 0, 1)}). "
                                "Designating a capacity for Copilot lets you charge that cost back to each team accurately."),
                        "evidence": f"Tenant setting “{cop_set['title']}”: {'enabled' if cop_set['enabled'] else 'disabled'}" if cop_set else "AI meters in Cost Management",
                        "value": None, "unit": "", "src": "Cost Management + Tenant settings"})
    if untagged:
        actions.append({"kind": "gov", "title": "Tag the capacities with a cost center",
                        "why": "Without tags (costCenter, owner, environment), Cost Management cannot allocate costs or create budgets per business area.",
                        "evidence": ", ".join(f"{c['name']} ({c['sku']})" for c in untagged), "value": None, "unit": "", "src": "ARM"})
    if ref_failed:
        actions.append({"kind": "gov", "title": f"Fix {len(ref_failed)} failed refresh{'es' if len(ref_failed) != 1 else ''}",
                        "why": "Models whose last refresh failed: users are working with stale data.",
                        "evidence": "; ".join(f"{r['name']} ({r['ws']}) {r['err']}" for r in ref_failed), "value": None, "unit": "", "src": "Admin API refreshables"})
    if idle_ws:
        actions.append({"kind": "gov", "title": f"Review {len(idle_ws)} workspaces on paid capacity with no use in the period",
                        "why": "No activity or Spark in the period. Candidates to archive, move to a trial capacity or clean up.",
                        "evidence": ", ".join(r["name"] for r in idle_ws[:12]) + (" …" if len(idle_ws) > 12 else ""), "value": None, "unit": "", "src": "Admin API + Fabric activity log"})
    if trials:
        actions.append({"kind": "gov", "title": "Plan for the end of the trial capacity",
                        "why": "Anything on the trial capacity will stop working, or will have to be moved to a paid capacity, when the trial ends.",
                        "evidence": ", ".join(f"{c['name']} ({c['ws']} workspaces, {c['items']} items)" for c in trials), "value": None, "unit": "", "src": "Fabric Admin API"})
    if stale_items:
        actions.append({"kind": "gov", "title": f"Clean up {len(stale_items)} items unchanged for more than 90 days",
                        "why": "Reduces clutter, risk and storage. First check that they are not being queried (see the most-used items table).",
                        "evidence": ", ".join(f"{t}: {n}" for t, n in stale_types.most_common(6)), "value": None, "unit": "", "src": "Admin API items"})

    # ================================================================== v5 CHARTS (inline SVG, no external libraries)
    def nice_max(v):
        if v <= 0:
            return 1
        e = 10 ** math.floor(math.log10(v))
        for m in (1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10):
            if v <= m * e:
                return m * e
        return 10 * e

    cat_order = [c for c, _ in sorted(cat_cost.items(), key=lambda kv: (kv[0] != "idle", kv[0] == "storage", -kv[1])) if cat_cost[c] > 0.005]

    def svg_daily_cost():
        W, H, L, R, T, B = 1100, 312, 58, 14, 30, 64
        n = len(all_days)
        if not n:
            return ""
        vals = [sum(day_cat[k].values()) for k in all_days]
        ym = nice_max(max(vals) if vals else 1)
        bw = (W - L - R) / n
        g = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-labelledby="dct"><title id="dct">Daily cost by Fabric component</title>']
        for i in range(5):
            y = T + (H - T - B) * i / 4
            g.append(f'<line x1="{L}" x2="{W - R}" y1="{y:.1f}" y2="{y:.1f}" stroke="#e3ebf1"/>'
                     f'<text x="{L - 8}" y="{y + 4:.1f}" text-anchor="end">{fn(ym * (1 - i / 4), 0)}</text>')
        for i, k in enumerate(all_days):
            x = L + i * bw + bw * 0.14
            w = bw * 0.72
            y = H - B
            tot = vals[i]
            tip = [f"{dlabel(k)} · {money(tot)}"]
            for c in cat_order:
                v = day_cat[k].get(c, 0)
                if v <= 0:
                    continue
                h = (H - T - B) * v / ym
                y -= h
                g.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{max(h, .5):.1f}" fill="{CATS[c][1]}"/>')
                tip.append(f"{CATS[c][0]}: {money(v)}")
            on = on_day.get(k, 0)
            g.append(f'<rect x="{L + i * bw:.1f}" y="{T}" width="{bw:.1f}" height="{H - T - B}" fill="transparent"><title>{E(chr(10).join(tip))}            {E(chr(10) + "Running " + fn(on, 1) + " h") if on else ""}</title></rect>')
            dt = datetime.strptime(k, "%Y%m%d")
            if i % 2 == 0 or n <= 16:
                            g.append(f'<text x="{L + i * bw + bw / 2:.1f}" y="{H - B + 15}" text-anchor="middle">{dmon(dt)}</text>')
            if dt.weekday() == 0:
                            g.append(f'<text x="{L + i * bw + bw / 2:.1f}" y="{H - B + 30}" text-anchor="middle" class="lbl">Mon</text>')
            if on > 0.05:
                g.append(f'<rect x="{L + i * bw + bw * .14:.1f}" y="{H - B + 36}" width="{bw * .72:.1f}" height="4" rx="2" fill="#117865" opacity="{min(.25 + on / 24, 1):.2f}"/>')
        g.append(f'<text x="{L}" y="{H - 4}" class="lbl">Thin bottom bar: hours the capacity was running that day (darker = more hours)</text>')
        g.append(f'<text x="{L - 8}" y="{T - 14}" text-anchor="end" class="lbl">{E(CUR)}</text></svg>')
        return "".join(g)

    act_hour = Counter((t.strftime("%Y%m%d"), t.hour) for t in work_times)
    ah_max = max(act_hour.values()) if act_hour else 1
    tl_days = [k for k in all_days if on_day.get(k, 0) > 0.01 or any(dk == k for dk, _ in act_hour)]
    tail_by_day = {}
    for r in cov_runs:
        if r["last"] and r["tail"] and r["tail"] > 0.05:
            tail_by_day.setdefault(r["b"].strftime("%Y%m%d"), []).append((r["last"], r["b"]))
        elif not r["last"]:
            tail_by_day.setdefault(r["b"].strftime("%Y%m%d"), []).append((r["a"], r["b"]))

    def svg_timeline():
        if not tl_days:
            return ""
        L, R, T, RH, G = 92, 92, 26, 22, 6
        W = 1100
        PX = (W - L - R) / 24
        H = T + len(tl_days) * (RH + G) + 14
        g = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-labelledby="tlt"><title id="tlt">Hours running versus hours with work, by day</title>',
             '<defs><pattern id="hatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
             '<rect width="6" height="6" fill="#eef2f5"/><line x1="0" y1="0" x2="0" y2="6" stroke="#c9d4dd" stroke-width="2"/></pattern></defs>']
        for hh in range(0, 25, 3):
            x = L + hh * PX
            g.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{T - 6}" y2="{H - 10}" stroke="#e3ebf1"/>'
                     f'<text x="{x:.1f}" y="{T - 10}" text-anchor="middle">{hh:02d}h</text>')
        g.append(f'<text x="{W - 4}" y="{T - 10}" text-anchor="end" class="lbl">h running</text>')
        for i, k in enumerate(tl_days):
            y = T + i * (RH + G)
            d0_ = datetime.strptime(k, "%Y%m%d").replace(tzinfo=timezone.utc)
            pre = bool(act0) and d0_ < act0
            g.append(f'<text x="{L - 10}" y="{y + 15}" text-anchor="end" class="lbl">{dlabel(k)}</text>')
            g.append(f'<rect x="{L}" y="{y}" width="{24 * PX:.1f}" height="{RH}" fill="#f6f9fb"/>')
            for a, b in focus_iv:
                s_, e_ = max(a, d0_), min(b, d0_ + timedelta(days=1))
                if e_ <= s_:
                    continue
                x0 = L + (s_ - d0_).total_seconds() / 3600 * PX
                x1 = L + (e_ - d0_).total_seconds() / 3600 * PX
                g.append(f'<rect x="{x0:.1f}" y="{y}" width="{max(x1 - x0, 1):.1f}" height="{RH}" fill="{"url(#hatch)" if pre else "#cfe9e3"}">'
                         f'<title>Running {hhmm(s_)}–{hhmm(e_)} UTC{" · before the start of the activity log" if pre else ""}</title></rect>')
            for a, b in tail_by_day.get(k, []):
                s_, e_ = max(a, d0_), min(b, d0_ + timedelta(days=1))
                if e_ > s_:
                    x0 = L + (s_ - d0_).total_seconds() / 3600 * PX
                    x1 = L + (e_ - d0_).total_seconds() / 3600 * PX
                    g.append(f'<rect x="{x0:.1f}" y="{y}" width="{max(x1 - x0, 1):.1f}" height="{RH}" fill="#d99a2b" opacity=".38">'
                             f'<title>Running with no work: {hhmm(s_)}–{hhmm(e_)} UTC ({fn((e_ - s_).total_seconds() / 3600, 1)} h)</title></rect>')
            for hh in range(24):
                n_ = act_hour.get((k, hh), 0)
                if n_:
                    hgt = 3 + (RH - 7) * math.sqrt(n_ / ah_max)
                    g.append(f'<rect x="{L + hh * PX + PX * .2:.1f}" y="{y + RH - 4 - hgt:.1f}" width="{PX * .6:.1f}" height="{hgt:.1f}" rx="1.5" fill="#0b5345">'
                             f'<title>{dlabel(k)} {hh:02d}h UTC · {n_} user/app operations</title></rect>')
            for x in livy_focus:
                s_, e_ = max(x["start"], d0_), min(x["end"] or gen, d0_ + timedelta(days=1))
                if e_ > s_:
                    x0 = L + (s_ - d0_).total_seconds() / 3600 * PX
                    x1 = L + (e_ - d0_).total_seconds() / 3600 * PX
                    g.append(f'<rect x="{x0:.1f}" y="{y + RH - 3}" width="{max(x1 - x0, 1.5):.1f}" height="3" fill="#6a3d9a">'
                             f'<title>Spark · {E(x["item"])} · {hhmm(x["start"])}–{hhmm(x["end"])} UTC</title></rect>')
            oh = on_day.get(k, 0)
            g.append(f'<text x="{W - R + 8}" y="{y + 15}" class="lbl">{fn(oh, 1)} h</text>')
        g.append("</svg>")
        return "".join(g)

    def heat_html():
        rows_ = []
        for d_ in range(7):
            cells = []
            for hh in range(24):
                v = heat[d_][hh]
                op = 0 if not v else .15 + .85 * math.sqrt(v / max(heat_max, 1))
                cells.append(f'<td title="{WD[d_]} {hh:02d}h UTC · {v} operations"><span style="background:rgba(11,83,69,{op:.2f});{"outline:1px solid #e3ebf1" if not v else ""}"></span></td>')
            rows_.append(f"<tr><th scope=row>{WD[d_]}</th>{''.join(cells)}</tr>")
        head = "".join(f"<th>{hh:02d}</th>" if hh % 3 == 0 else "<th></th>" for hh in range(24))
        return f'<div class="chart"><table class="heat" style="min-width:720px"><thead><tr><th></th>{head}</tr></thead><tbody>{"".join(rows_)}</tbody></table></div>'

    # ================================================================== v5 HTML · part 1 (summary, actions, pieces)
    MEXPL = [
        ("compute pool", "Share of the running capacity that no workload consumed. Fabric bills the whole capacity per hour while it is running; the unused part appears here."),
        ("capacity overage", "Consumption above the capacity size (overconsumption), billed at the overage rate."),
        ("copilot and ai", "Copilot, Data Agents and AI experiences (natural-language questions over the data)."),
        ("ontology ai", "Fabric IQ AI functions over the ontology."),
        ("operations agents", "Real-Time Intelligence operations agents."),
        ("spark memory optimized", "Spark compute: notebooks, Spark jobs and lakehouse loads."),
        ("spark", "Spark compute."),
        ("ontology logic", "Fabric IQ: ontology logic and operations (semantic business modelling)."),
        ("ontology", "Fabric IQ: ontology."),
        ("graph", "Fabric IQ: Graph."),
        ("onelake cache", "OneLake cache (cached data for fast queries, e.g. KQL)."),
        ("onelake storage", "Data storage in OneLake."),
        ("onelake", "Read/write transactions in OneLake."),
        ("eventhouse", "Eventhouse/KQL: real-time database running or being queried."),
        ("eventstream", "Eventstream: streaming event ingestion and processing."),
        ("activator", "Activator: real-time rules and alerts."),
        ("data warehouse", "Warehouse and the lakehouse SQL analytics endpoint."),
        ("sql database", "SQL database in Fabric."),
        ("power bi", "Power BI: refreshes, queries and reports on the capacity."),
        ("data movement", "Pipeline copy activities (data movement)."),
        ("data orchestration", "Pipeline orchestration."),
        ("dataflow", "Dataflows Gen2."),
        ("user data functions", "User data functions."),
        ("graphql", "API for GraphQL."),
        ("mirroring", "Database mirroring."),
    ]

    def mexpl(name):
        nl = name.lower()
        for k, v in MEXPL:
            if k in nl:
                return v
        return "Fabric meter billed on the capacity."

    MES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    mon = defaultdict(Counter)
    for r in raw.get("cost_monthly") or []:
        if r.get("month"):
            nm = (r.get("rid") or "").rsplit("/", 1)[-1] or "Fabric capacities"
            mon[r["month"]][nm] += r.get("cost") or 0
    mon_keys = sorted(mon)
    cur_month = gen.strftime("%Y-%m")
    mon_tot = {k: sum(v.values()) for k, v in mon.items()}
    full_months = [k for k in mon_keys if k != cur_month and mon_tot[k] > 0]
    mon_avg = sum(mon_tot[k] for k in full_months) / len(full_months) if full_months else 0
    mon_caps = sorted({c for v in mon.values() for c in v}, key=lambda c: -sum(mon[k][c] for k in mon_keys))
    MON_COL = ["#117865", "#1d5c8f", "#6a3d9a", "#a14306", "#4f6378"]

    def mlabel(k):
        return f"{MES[int(k[5:7]) - 1]} {k[:4]}"

    def svg_monthly():
        if not mon_keys:
            return ""
        W, H, L, R, T, B = 1100, 262, 64, 16, 34, 40
        mx = nice_max(max(mon_tot.values()))
        bw = (W - L - R) / len(mon_keys)
        g = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-labelledby="mtt"><title id="mtt">Monthly Fabric cost in Cost Management</title>']
        for i in range(5):
            v = mx * i / 4
            y = H - B - (H - B - T) * i / 4
            g.append(f'<line x1="{L}" x2="{W - R}" y1="{y:.1f}" y2="{y:.1f}" stroke="#e3ebf1"/><text x="{L - 8}" y="{y + 4:.1f}" text-anchor="end">{fn(v, 0)}</text>')
        if mon_avg:
            ya = H - B - (H - B - T) * mon_avg / mx
            g.append(f'<line x1="{L}" x2="{W - R}" y1="{ya:.1f}" y2="{ya:.1f}" stroke="#a14306" stroke-dasharray="4 4"><title>Average of closed months {money(mon_avg, 0)}</title></line>')
        for i, k in enumerate(mon_keys):
            x = L + i * bw + bw * .18
            y0 = H - B
            for j, c in enumerate(mon_caps):
                v = mon[k].get(c, 0)
                if v <= 0:
                    continue
                h = (H - B - T) * v / mx
                y0 -= h
                op = ' opacity=".55"' if k == cur_month else ""
                g.append(f'<rect x="{x:.1f}" y="{y0:.1f}" width="{bw * .64:.1f}" height="{h:.1f}" fill="{MON_COL[j % len(MON_COL)]}"{op}>'
                         f'<title>{mlabel(k)} · {E(c)}: {money(v)}{" (current month)" if k == cur_month else ""}</title></rect>')
            g.append(f'<text x="{x + bw * .32:.1f}" y="{y0 - 6:.1f}" text-anchor="middle" class="lbl">{fn(mon_tot[k], 0)}</text>'
                     f'<text x="{x + bw * .32:.1f}" y="{H - B + 16}" text-anchor="middle">{mlabel(k)}</text>')
            if k == cur_month:
                g.append(f'<text x="{x + bw * .32:.1f}" y="{H - B + 30}" text-anchor="middle" class="lbl">in progress</text>')
        g.append(f'<text x="{L - 8}" y="{T - 18}" text-anchor="end" class="lbl">{E(CUR)}</text></svg>')
        return "".join(g)

    subc = raw.get("sub_costs") or []
    sub_total = sum(r["cost"] for r in subc)
    sub_svc = Counter()
    for r in subc:
        sub_svc[r["service"] or "?"] += r["cost"]
    fabric_sub = sub_svc.get("Microsoft Fabric", 0.0)
    fab_adj = sorted([r for r in subc if r["cost"] >= 0.01 and r["service"] != "Microsoft Fabric" and "fabric" in r["rid"]], key=lambda r: -r["cost"])
    fab_adj_total = sum(r["cost"] for r in fab_adj)

    def rshort(rid):
        p = rid.split("/")
        rg = p[p.index("resourcegroups") + 1] if "resourcegroups" in p else ""
        return (p[-1] if p else rid), rg

    DRV_TOP = {}
    for cat in DRIVER:
        w = drv.get(cat) or Counter()
        tot = sum(w.values())
        if tot:
            DRV_TOP[cat] = [(ws_label(k), v / tot) for k, v in w.most_common(3)]
    item_by_cat = defaultdict(Counter)
    for e in work_ev:
        if e["it"]:
            item_by_cat[e["cat"]][e["it"]] += 1
    for x in livy:
        item_by_cat["spark"][x["item"]] += x["run"]

    nav = [("resumen", "Summary"), ("acciones", "FinOps actions"), ("piezas", "Where the money goes"), ("uso", "Running vs used"),
           ("quien", "Who consumes"), ("reparto", "Chargeback"), ("acceso", "Access and groups"), ("compromisos", "Reservation and size"),
           ("gobierno", "Governance"), ("preguntas", "Questions"), ("fuentes", "Sources")]
    ok_src = sum(1 for v in sources.values() if v.get("status") == "ok")

    def no_cost(sec_id, title, what):
        return (f'<section id="{sec_id}"><h2>{title}</h2><div class="notice warn"><div><b>Requires the Cost Management invoice</b>'
                f'<p>{what} {E(cost_why)}</p></div></div></section>')

    # hero: verdict first (sentence, verdict card, cost split), then the key figures
    idle_pct = idle_cost / total_cost if total_cost else 0
    stor = cat_cost.get("storage", 0.0)
    seg = [("Consumed by workloads", consumption_cost, "#5cc8ad"), ("Running with no load", idle_cost, "#e8a93c"), ("Storage", stor, "#aebdcb")]
    stack = "".join(f'<span style="width:{(v / total_cost * 100) if total_cost else 0:.2f}%;background:{c}" title="{E(lbl)}: {money(v)}"></span>' for lbl, v, c in seg if v > 0)
    legend = "".join(f'<li><span class="sw" style="background:{c}"></span>{E(lbl)} <b>{money(v)}</b> {pc(v / total_cost if total_cost else 0)}</li>' for lbl, v, c in seg)
    verdict = (f"The {E(focus_sku)} capacity was running for <b>{fn(on_hours, 0)} h</b> ({pc(uptime, 0)} of the period), and during that time "
               f"only <b>{pc(util_all, 0)}</b> of what was paid for was used. <b class=idle-t>{pc(idle_pct, 0)}</b> of the invoice is capacity running with no load.") \
        if focus_cu and cu_billed else ""
    est_on = hourly * on_hours
    if cost_ok:
        lead = f"<b>{money(total_cost)}</b> billed in the {E(period_label.lower())}." + (f" {verdict}" if verdict else "")
    else:
        lead = (f"At the public price, the <b>{fn(on_hours, 0)} h</b> that {E(focus_sku)} was running come to about <b>{money(est_on, 0)}</b> "
                f"({money(hourly)}/h). This is a reference, not the invoice: it excludes storage and the operations Fabric bills when the capacity is paused.")
    n_kind = Counter(a["kind"] for a in actions)
    if not cost_ok:
        v_cls, v_word, v_line = "info", "Partial view", "Billed cost not available in this run."
    else:
        v_cls, v_word = (("crit", "Action required") if idle_pct >= 0.5 else
                         ("warn", "Needs attention") if idle_pct >= 0.2 or headline_save >= 1 or n_kind.get("risk") else ("ok", "On track"))
        v_line = f"<b>{pc(idle_pct, 0)}</b> of the invoice is capacity running with no load."
    k_word = {"save": ("saving", "savings"), "avoid": ("avoided spend", "avoided spend"), "scenario": ("scenario", "scenarios"),
              "review": ("review", "reviews"), "risk": ("risk", "risks"), "gov": ("governance", "governance")}
    v_line += (f"</p><p class=vl><b>{len(actions)} action{'' if len(actions) == 1 else 's'}</b>"
               + (": " + ", ".join(f"{n_kind[k]} {k_word[k][n_kind[k] != 1]}" for k in k_word if n_kind.get(k)) if actions else ""))
    dist = (f'<div class="dist"><div class="stack" role="img" aria-label="{E("; ".join(f"{lb}: {money(v)}" for lb, v, _ in seg if v > 0))}">{stack}</div>'
            f'<ul class="legend">{legend}</ul></div>') if cost_ok and total_cost else ""
    n_caps = len({c["rid"] for c in crow})

    def kpi(v, unit, label, sub, cls=""):
        return (f'<li class="kpi{cls}"><span class="v">{v}{f"<small>{unit}</small>" if unit else ""}</span>'
                f'<span class="k">{label}</span><span class="s">{sub}</span></li>')

    kpis = [kpi(fn(total_cost, 2), E(CUR), "Actual cost",
                f"{E(period_label.lower())} · {len(meters)} meters · {n_caps} capacit{'y' if n_caps == 1 else 'ies'}") if cost_ok else
            kpi("—", "", "Billed cost", f"{E(period_label.lower())} · not available in this run"),
            kpi(fn(on_hours, 1), "h", "Running hours", f"of {fn(win_hours, 0)} h in the period ({pc(uptime, 0)})"),
            kpi(fn(hourly, 2), E(CUR), "Cost per running hour", f"{focus_cu} CU × <span class=nw>{money(price_cu, 4)}/CU-h</span>"),
            kpi(f"{fn(cu_billed, 0)} / {fn(cu_consumed, 0)}" if cost_ok else "—", "", "CU-h paid vs used",
                f"average {fn(avg_cu_on, 1)} CU used per running hour" if cost_ok else "requires the Cost Management invoice"),
            kpi(fn(headline_save, 0), f"{E(CUR)}/month", "Savings identified", "without changing SKU or touching workloads", " accent")]
    meta = (f'<li>Generated <b>{dmon(gen, " %Y %H:%M")} UTC</b></li><li><b>{E(period_label)}</b> · {dmon(win0)} → {dmon(gen, " %Y")}</li>'
            f'<li>Main capacity <b>{E(focus_name)}</b> ({E(focus_sku)} · {E(focus.get("location") or "")})</li>'
            f'<li class="live">Live data · {ok_src}/{len(sources)} sources read</li><li>Identities {"visible" if show_ids else "masked"}</li>')
    page_css = ('@page{size:A4;margin:12mm 11mm 15mm;@bottom-left{content:"Microsoft Fabric FinOps · ' + E(period_label) + " · generated "
                + dmon(gen, " %Y %H:%M") + ' UTC";font:8.5pt "Segoe UI",sans-serif;color:#4b5e71}'
                '@bottom-right{content:counter(page) " / " counter(pages);font:8.5pt "Segoe UI",sans-serif;color:#4b5e71}}')
    parts = []
    parts.append(f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; font-src data:; style-src 'unsafe-inline'; script-src 'unsafe-inline'">
<title>Microsoft Fabric FinOps · {E(period_label)} · real data</title><style>{CSS}{page_css}</style></head><body>
<header class="topbar"><div class="wrap"><span class="mark"><i><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9.2 3h5.6l6.2 18h-4.5l-1.5-4.6H8.4L9.9 12h3.8L12 6.6 6.4 21H2z"/></svg></i>Azure SRE Agent</span>
<span class="ctx">Microsoft Fabric FinOps and chargeback</span><div class="top-acts"><span class="tag">Read-only</span>
<button type="button" class="print" data-print><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 9V3h10v6M7 18H5a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/><path d="M7 14h10v7H7z"/></svg><span class="lbl">Print / PDF</span></button></div></div></header>
<main><div class="hero"><div class="wrap hero-grid"><div><h1>Microsoft Fabric FinOps: what you pay for, what you use and what you can save</h1>
<p class="lead">{lead}</p>
<p class="prov">Report generated by Azure SRE Agent from a live read of the tenant: the Azure Cost Management invoice, running hours from the
Activity Log, user activity, Spark runs, and Fabric inventory and configuration. No sample data.</p></div>
<div class="verdict {v_cls}"><p class="vk">Verdict</p><p class="vw">{v_word}</p><p class="vl">{v_line}</p></div>
<ul class="meta">{meta}</ul>
{dist}</div></div>
<div class="wrap"><section id="resumen" aria-label="Key figures"><ul class="kpis">{''.join(kpis)}</ul></section></div>
<nav class="toc" aria-label="Sections"><ol>{''.join(f'<li><a href="#{a}">{b}</a></li>' for a, b in nav)}</ol></nav><div class="wrap body">""")
    if not cost_ok:
        parts.append(f'<div class="notice warn"><div><b>Billed cost not available in this run</b><p>{E(cost_why)} '
                     'Running hours, activity, Spark, governance and pause savings are real and complete; '
                     'savings amounts use the public Azure price.</p></div></div>')
    elif not crow:
        parts.append('<div class="notice warn"><div><b>No cost in the period</b><p>Cost Management returned no amounts for Fabric capacities. '
                     'Check the Cost Management Reader role on the subscription, or whether the capacities are billed to another subscription.</p></div></div>')

    # actions
    kind_lbl = {"save": ("Saving", "ok"), "avoid": ("Avoided spend", "info"), "scenario": ("Scenario", "info"), "review": ("Review", "warn"),
                "risk": ("Risk", "crit"), "gov": ("Governance", "neutral")}
    ali = []
    for n_, a in enumerate(actions, 1):
        kl, kc = kind_lbl.get(a["kind"], ("", "neutral"))
        val = f'<b>{money(a["value"], 0)}</b><span>{E(a["unit"])}</span>' if a.get("value") else f'<span>{pill(kc, kl)}</span>'
        ali.append(f'<li data-kind="{E(a["kind"])}" data-n="{n_}"><div><h3>{E(a["title"])} {pill(kc, kl) if a.get("value") else ""}</h3><p>{E(a["why"])}</p></div>'
                   f'<div class="val">{val}</div><div class="ev"><b>Evidence:</b> {E(a["evidence"] or "—")} · <i>{E(a["src"])}</i></div></li>')
    k_names = {"save": "Savings", "avoid": "Avoided spend", "scenario": "Scenarios", "review": "Review", "risk": "Risks", "gov": "Governance"}
    afilter = ('<div class="afilter" role="group" aria-label="Show actions by type">'
               f'<button type="button" data-kind="all" aria-pressed="true">All <b>{len(actions)}</b></button>'
               + "".join(f'<button type="button" data-kind="{k}" aria-pressed="false">{v} <b>{n_kind[k]}</b></button>' for k, v in k_names.items() if n_kind.get(k))
               + f'<span class="acount" aria-live="polite">{len(actions)} actions</span></div>') if len(actions) > 3 else ""
    parts.append(f"""<section id="acciones"><h2>Prioritized FinOps actions</h2>
<p class="sub">Each action is calculated from this tenant's data and shows its evidence. Monthly figures project the observed period to 30 days.</p>
<div class="save-strip"><span class="big">{money(headline_save, 0)}/month</span><p>Estimated direct saving from adjusting when the capacity is paused, with a 1 h buffer after the last activity.
The other actions avoid spend or risk and are not added to this figure.</p></div>
{afilter}<ol class="actions">{''.join(ali) or '<li><div><h3>No actions</h3><p>No opportunities were detected with the available data.</p></div></li>'}</ol></section>""")

    # pieces
    cat_rows = []
    for c in cat_order:
        v = cat_cost[c]
        tops = DRV_TOP.get(c)
        who = ", ".join(f"{E(n)} {pc(s, 0)}" for n, s in tops) if tops else ("Not assignable to a workspace" if c in ("idle", "storage", "onelake", "overage", "other") else "No recorded activity")
        cat_rows.append(f'<li><span>{cat_sw(c)}{E(CATS[c][0])}</span><b>{money(v)} · {pc(v / total_cost if total_cost else 0)}</b>'
                        f'<span class="track"><span class="fill" style="display:block;width:{(v / max(cat_cost.values()) * 100):.1f}%;background:{CATS[c][1]}"></span></span>'
                        f'<span class="cell-sub" style="grid-column:1/-1">Generated in: {who}</span></li>')
    mrows = []
    for m in sorted(meters.values(), key=lambda m: -m["cost"]):
        if m["cost"] < 0.005:
            continue
        tops = item_by_cat.get(m["cat"])
        top_it = ", ".join(E(k) for k, _ in tops.most_common(3)) if tops and m["cat"] in DRIVER else "—"
        unit = "GB-month" if m["cat"] == "storage" else "CU-h"
        mrows.append(f'<tr><td><span class="cell-strong">{cat_sw(m["cat"])}{E(m["name"])}</span><span class="cell-sub">{E(mexpl(m["name"]))}</span></td>'
                     f'<td>{E(CATS[m["cat"]][0])}</td><td class="num" data-v="{m["qty"]:.3f}">{fn(m["qty"], 1)} {unit}</td>'
                     f'<td class="num" data-v="{len(m["days"])}">{len(m["days"])}</td><td class="num" data-v="{m["cost"]:.4f}">{money(m["cost"])}</td>'
                     f'<td class="num" data-v="{m["cost"] / total_cost if total_cost else 0:.5f}">{pc(m["cost"] / total_cost if total_cost else 0)}</td><td>{top_it}</td></tr>')
    lag_note = f" Days after {dlabel(last_cost_day)} have no cost yet: Cost Management publishes costs with a 24–48 h delay." if last_cost_day and last_cost_day < gen.strftime("%Y%m%d") else ""
    svc_rows = "".join(f'<li><span>{E(s)}</span><b>{money(v)} · {pc(v / sub_total if sub_total else 0, 0)}</b>'
                       f'<span class="track"><span class="fill" style="display:block;width:{(v / max(sub_svc.values()) * 100) if sub_svc else 0:.1f}%;background:{"#117865" if s == "Microsoft Fabric" else "#8aa1b4"}"></span></span></li>'
                       for s, v in sub_svc.most_common(6) if v >= 0.5)
    adj_rows = "".join(f'<li><span>{E(rshort(r["rid"])[0])}<span class="cell-sub">{E(r["service"])} · {E(rshort(r["rid"])[1])}</span></span><b>{money(r["cost"])}</b></li>' for r in fab_adj[:6])
    trend_html = ""
    if mon_keys or subc:
        prev = full_months[-1] if full_months else None
        trend_html = f"""<div class="panel" style="margin-top:16px"><h3>Monthly Fabric trend</h3>
<p class="muted" style="margin:0 0 8px">Monthly invoice for the Fabric capacities (includes capacities that have since been deleted).{f' Last closed month ({mlabel(prev)}): <b>{money(mon_tot[prev])}</b>.' if prev else ''}
{f' Current month to date: <b>{money(mon_tot.get(cur_month, 0))}</b>.' if cur_month in mon_tot else ''}</p>
<div class="chart">{svg_monthly()}</div><ul class="keys">{''.join(f'<li><span class="sw" style="background:{MON_COL[j % len(MON_COL)]}"></span>{E(c)}</li>' for j, c in enumerate(mon_caps)) if len(mon_caps) > 1 else ''}{f'<li><span class="sw" style="background:none;border-top:2px dashed #a14306;height:0;width:16px"></span>Average of closed months: <b>{money(mon_avg, 0)}</b></li>' if mon_avg else ''}</ul></div>
<div class="split" style="margin-top:16px"><div class="panel"><h3>Fabric within the subscription</h3>
<p class="muted" style="margin:0 0 12px">Same period, whole subscription: Fabric is <b>{pc(fabric_sub / sub_total if sub_total else 0, 0)}</b> of {money(sub_total)}.</p>
<ul class="bars">{svc_rows}</ul></div>
{f'<div class="panel"><h3>Other Azure resources with “fabric” in their name or resource group ({money(fab_adj_total)})</h3><p class="muted" style="margin:0 0 8px">They are not billed on the capacity. Check whether they are part of the solution (e.g. Data Agent apps or mirroring) or unrelated resources in the same group.</p><ul class="bars">{adj_rows}</ul></div>' if fab_adj else ''}</div>"""
    if not cost_ok:
        parts.append(no_cost("piezas", "Where the money goes, component by component",
                             "The breakdown by meter, the monthly trend and Fabric's share of the subscription all come from the invoice."))
    else:
        parts.append(f"""<section id="piezas"><h2>Where the money goes, component by component</h2>
<p class="sub">Each meter on the Fabric invoice with its quantity, amount and what generated it. The meters add up to the total cost.{lag_note}</p>
<div class="panel"><div class="chart">{svg_daily_cost()}</div>
<ul class="keys">{''.join(f'<li>{cat_sw(c)}{E(CATS[c][0])}</li>' for c in cat_order)}</ul></div>
<div class="split"><div class="panel"><h3>By workload type</h3><ul class="bars">{''.join(cat_rows)}</ul></div>
<div class="panel"><h3>How to read the Fabric invoice</h3><p class="muted" style="margin:0 0 12px">An {E(focus_sku or 'F')} capacity is paid for by the running hour
({money(hourly)}/h). Microsoft breaks that amount down into meters: each workload (Spark, AI, Real-Time…) bills the CUs it used and the rest appears as
“Compute Pool”. That is why a high Compute Pool means capacity running unused, not a specific workload.</p>
<p class="muted" style="margin:0">When the capacity is paused, Fabric bills all pending smoothed operations at once; that is why on some days the total exceeds {focus_cu or 'the'} CUs × running hours.
On days with no load the invoice matches the running hours{f' with a maximum error of {pc(match_err, 1)}' if match_err is not None else ''}, which validates the running-hours calculation.</p></div></div>
{trend_html}
<div class="toolbar" style="margin-top:16px"><button class="btn" type="button" data-csv="csv-meters" data-name="fabric-daily-cost-by-meter.csv">Download daily CSV by meter</button></div>
<div class="tbl-wrap"><table data-sortable class="dense"><thead><tr>{th('Meter', 0)}{th('Type', 1)}{th('Quantity', 2, 'num', 'num')}{th('Days with charges', 3, 'num', 'num')}{th('Cost', 4, 'num', 'num')}{th('%', 5, 'num', 'num')}<th>Items that use it most</th></tr></thead>
<tbody>{''.join(mrows)}</tbody><tfoot><tr><td colspan="4">Total</td><td class="num">{money(total_cost)}</td><td class="num">100%</td><td></td></tr></tfoot></table></div></section>""")

    # ================================================================== v5 HTML · part 2 (on vs used, who, chargeback, commitments)
    wrows = "".join(f'<tr><td class="nw">{hmad(w["hour"])}</td><td class="num">{fn(w["saved_h"], 1)} h</td><td class="num">{money(w["save"])}</td>'
                    f'<td class="num">{money(w["save"] * per_month, 0)}</td><td class="num">{w["days"]}</td>'
                    f'<td>{pill("ok", "No work cut off") if w["conflicts"] == 0 else pill("crit", str(w["conflicts"]) + " day(s) with work cut off")}</td></tr>'
                    for w in whatif)
    drows = []
    for x in daily:
        if x["on_h"] < 0.01 and x["cost"] < 0.01:
            continue
        drows.append(f'<tr><td class="nw" data-v="{x["date"]}">{dlabel(x["date"])}</td><td class="num" data-v="{x["on_h"]:.2f}">{fn(x["on_h"], 1)} h</td>'
                     f'<td class="num" data-v="{x["billed"]:.1f}">{fn(x["billed"], 0)}</td><td class="num" data-v="{x["consumed"]:.1f}">{fn(x["consumed"], 0)}</td>'
                     f'<td class="num" data-v="{x["util"] or 0:.4f}">{pc(x["util"], 0) if x["util"] is not None else "—"}</td>'
                     f'<td class="num" data-v="{x["cost"]:.2f}">{money(x["cost"]) if not x["lag"] else "pending"}</td>'
                     f'<td class="num">{fn(x["ratio"], 2) if x["ratio"] is not None else "—"}</td></tr>')
    pre_note = (f"Hatched bands are before {dmon(act0)}: the Fabric activity log only keeps {act_days} days, "
                "so those bands show when the capacity was running but not the work done.") if act0 and act0 > win0 else ""
    if cost_ok:
        bill_col = f"""<div><h3>Invoice versus running hours, day by day</h3><p class="muted" style="margin:0 0 12px">Billed CU-h, CU-h used by workloads, and the ratio invoice ÷ (hours × {focus_cu or '—'} CU).
Ratio 1.00 = the invoice matches the running hours.</p>
<div class="tbl-wrap"><table data-sortable class="dense"><thead><tr>{th('Day', 0)}{th('Running', 1, 'num', 'num')}{th('CU-h paid', 2, 'num', 'num')}{th('CU-h used', 3, 'num', 'num')}{th('Use', 4, 'num', 'num')}{th('Cost', 5, 'num', 'num')}<th class="num">Ratio</th></tr></thead>
<tbody>{''.join(drows)}</tbody></table></div></div>"""
    else:
        bill_col = (f'<div><h3>Invoice versus running hours, day by day</h3><div class="notice warn"><div><b>Requires the Cost Management invoice</b>'
                    f'<p>The CU-h paid and used per day come from the invoice. {E(cost_why)}</p></div></div></div>')
    parts.append(f"""<section id="uso"><h2>Running versus used</h2>
<p class="sub">Each row is one day (UTC). The green band is the capacity running (Activity Log), the dark bars are user and app operations,
the purple line is Spark sessions and amber marks the time the capacity stayed on after the last work. {pre_note}</p>
<ul class="kv"><li>Running<b>{fn(on_hours, 1)} h</b>{len(focus_iv)} running periods in the period</li>
<li>After the last work<b>{fn(tail_h, 1)} h</b>{len(cov_runs)} running periods with recorded activity</li>
<li>{'Automatic' if auto_suspend else 'Manual'} pause<b>{hhmm(susp_times[-1]) if susp_times else '—'} UTC</b>{f'median {int(suspend_hour_med):02d}:{int((suspend_hour_med % 1) * 60):02d} UTC' if suspend_hour_med is not None else 'no pauses in the period'}</li>
<li>Who starts it<b>{len(callers_resume)}</b>{E(', '.join(plabel(pkey(c)) for c, _ in callers_resume.most_common(2))) or '—'}</li></ul>
<div class="panel" style="margin-top:16px"><div class="chart">{svg_timeline()}</div>
<ul class="keys"><li><span class="sw" style="background:#cfe9e3"></span>Running</li><li><span class="sw" style="background:#d99a2b;opacity:.6"></span>Running after the last work</li>
<li><span class="sw" style="background:#0b5345"></span>Operations per hour</li><li><span class="sw" style="background:#6a3d9a"></span>Spark</li>
{'<li><span class="sw" style="background:#c9d4dd"></span>No activity log</li>' if pre_note else ''}</ul></div>
<div class="duo"><div><h3>What if the automatic pause were earlier?</h3>
<p class="muted" style="margin:0 0 12px">Hours that would have been avoided across the {len(cov_runs)} running periods with recorded activity, and whether any real work would have been cut off.</p>
<div class="tbl-wrap"><table class="dense"><thead><tr><th>Pause at</th><th class="num">Hours avoided</th><th class="num">Observed saving</th><th class="num">Per month</th><th class="num">Days</th><th>Impact</th></tr></thead>
<tbody>{wrows}</tbody></table></div></div>
{bill_col}</div></section>""")

    # who
    def topcat(p):
        c = [k for k, _ in p["cats"].most_common(3) if k in CATS]
        return " ".join(cat_sw(k) + E(CATS[k][0].split(" ·")[0].split(" (")[0]) for k in c[:2]) or "—"

    prow = []
    for p in humans[:25]:
        top_ws = ", ".join(E(ws_label(w)) for w, _ in p["ws"].most_common(2)) or "—"
        prow.append(f'<tr><td><span class="cell-strong">{E(plabel(p["k"]))}</span><span class="cell-sub">{"Person" if p["kind"] == "user" else "Application / service principal"}</span></td>'
                    f'<td class="num" data-v="{p["work"]}">{fn(p["work"])}</td><td class="num" data-v="{len(p["days"])}">{len(p["days"])}</td>'
                    f'<td>{topcat(p)}</td><td>{top_ws}</td><td class="num" data-v="{p.get("spark_h", 0):.2f}">{fn(p.get("spark_h", 0), 1)} h</td>'
                    f'<td class="nw" data-v="{p["last"].isoformat()}">{dmon(p["last"], " %H:%M")}</td></tr>')
    nh = "".join(f'<tr><td>{E(plabel(p["k"]))}</td><td class="num">{fn(p["events"])}</td><td>{E(", ".join(a for a, _ in p["acts"].most_common(3)))}</td></tr>' for p in nonhuman[:8])
    irows = "".join(f'<tr><td><span class="cell-strong">{E(r["it"])}</span><span class="cell-sub">{E(r["itt"] or "")}</span></td><td>{E(ws_label(r["ws"]))}</td>'
                    f'<td class="num" data-v="{r["n"]}">{fn(r["n"])}</td><td class="num" data-v="{len(r["users"])}">{len(r["users"])}</td><td>{topcat(r)}</td>'
                    f'<td class="nw" data-v="{r["last"].isoformat()}">{dmon(r["last"], " %H:%M")}</td></tr>' for r in top_items)
    n_users = sum(1 for p in humans if p["kind"] == "user")
    parts.append(f"""<section id="quien"><h2>Who consumes</h2>
<p class="sub">Work operations (queries, runs, AI, refreshes, reads) from the Fabric activity log{f' for the last {act_ok} days' if act_ok else ''}, plus Spark sessions.
Administrative operations and this report's own reads are excluded. Identities {'visible' if show_ids else 'masked; request the report with visible identities if the recipient is authorized'}.</p>
<ul class="kv"><li>Active people<b>{n_users}</b>with work operations</li><li>Apps and service principals<b>{len(humans) - n_users}</b>with operations</li>
<li>Work operations<b>{fn(len(work_ev))}</b>out of {fn(len(evs))} audited events</li><li>Spark sessions<b>{len(livy)}</b>{fn(livy_total_s / 3600, 1)} h of execution</li></ul>
<div class="tbl-wrap" style="margin-top:16px"><table data-sortable class="dense"><thead><tr>{th('Identity', 0)}{th('Operations', 1, 'num', 'num')}{th('Active days', 2, 'num', 'num')}<th>Workload type</th><th>Workspaces</th>{th('Spark', 5, 'num', 'num')}{th('Last', 6)}</tr></thead>
<tbody>{''.join(prow) or '<tr><td colspan="7">No work operations in the period.</td></tr>'}</tbody></table></div>
<div class="panel" style="margin-top:16px"><h3>When people work (day × hour, UTC)</h3>{heat_html()}</div>
<div class="panel" style="margin-top:16px"><h3>System identities</h3><p class="muted" style="margin:0 0 12px">Fabric and Power BI processes with no person behind them.</p>
<div class="tbl-wrap"><table class="dense"><thead><tr><th>Identity</th><th class="num">Events</th><th>Operations</th></tr></thead><tbody>{nh or '<tr><td colspan="3">—</td></tr>'}</tbody></table></div></div>
<h3 style="margin-top:24px">Most-used items</h3>
<div class="tbl-wrap"><table data-sortable class="dense"><thead><tr>{th('Item', 0)}{th('Workspace', 1)}{th('Operations', 2, 'num', 'num')}{th('Identities', 3, 'num', 'num')}<th>Workload</th>{th('Last', 5)}</tr></thead>
<tbody>{irows or '<tr><td colspan="6">—</td></tr>'}</tbody></table></div></section>""")

    # chargeback
    cb_sum = sum(r["total"] for r in cb)
    residual = total_cost - cb_sum - no_ws_cost - unassigned_total
    cbrows = []
    cb_zero = []
    for r in cb:
        if r["total"] < 0.005:
            cb_zero.append(r["name"])
            continue
        mini = "".join(f'<span style="width:{v / r["direct"] * 100:.1f}%;background:{CATS[c][1]}" title="{E(CATS[c][0])}: {money(v)}"></span>'
                       for c, v in r["by_cat"].most_common() if r["direct"] > 0 and v > 0)
        cbrows.append(f'<tr><td><span class="cell-strong">{E(r["name"])}</span><span class="cell-sub">{E(r["cap"])} {E(r["sku"])} · {r["items"]} items</span>'
                      f'{f"<span class=mini>{mini}</span>" if mini else ""}</td>'
                      f'<td class="num" data-v="{r["events"]}">{fn(r["events"])}</td><td class="num" data-v="{r["ai"]}">{fn(r["ai"])}</td>'
                      f'<td class="num" data-v="{r["spark_h"]:.2f}">{fn(r["spark_h"], 1)} h</td><td class="num" data-v="{r["direct"]:.4f}">{money(r["direct"])}</td>'
                      f'<td class="num" data-v="{r["idle"]:.4f}">{money(r["idle"])}</td><td class="num cell-strong" data-v="{r["total"]:.4f}">{money(r["total"])}</td>'
                      f'<td class="num" data-v="{r["total"] / total_cost if total_cost else 0:.5f}">{pc(r["total"] / total_cost if total_cost else 0)}</td></tr>')
    extra_rows = []
    if no_ws_cost > 0.005:
        extra_rows.append(("Operations with no workspace in the event", no_ws_cost))
    if abs(residual) > 0.005:
        extra_rows.append(("Workspaces that no longer exist or are not in the inventory", residual))
    for c, v in unassigned.most_common():
        if v > 0.005:
            extra_rows.append((f"Unallocatable platform cost · {CATS[c][0]}", v))
    ex_html = "".join(f'<tr><td colspan="4"><span class="muted">{E(n)}</span></td><td class="num">{money(v)}</td><td></td><td class="num">{money(v)}</td>'
                      f'<td class="num">{pc(v / total_cost if total_cost else 0)}</td></tr>' for n, v in extra_rows)
    drv_list = "".join(f'<li>{cat_sw(c)}<b>{E(CATS[c][0])}</b> ({money(cat_cost[c])}) → by {E(d)}</li>' for c, d in DRIVER.items() if cat_cost.get(c, 0) > 0.005)
    nbrows = "".join(f'<tr><td><span class="cell-strong">{E(n["item"])}</span><span class="cell-sub">{E(ws_label(n["ws"]))}</span></td>'
                     f'<td class="num" data-v="{n["sessions"]}">{n["sessions"]}</td><td class="num" data-v="{n["sched"]}">{n["sched"]}</td>'
                     f'<td class="num" data-v="{n["failed"]}">{pill("crit", str(n["failed"])) if n["failed"] else "0"}</td>'
                     f'<td class="num" data-v="{n["run"]:.0f}">{fn(n["run"] / 3600, 2)} h</td><td class="num" data-v="{n["share"]:.4f}">{pc(n["share"], 0)}</td>'
                     f'<td class="num" data-v="{n["cost"]:.4f}">{money(n["cost"]) if cost_ok else "—"}</td>'
                     f'<td class="nw">{dmon(n["last"], " %H:%M") if n["last"] else "—"}</td></tr>' for n in nb_list[:15])
    if cost_ok:
        cb_block = f"""<p class="sub">Each meter on the invoice is allocated using its own real usage. Running time with no consumption is allocated in proportion to each workspace's direct consumption.
The total reconciles exactly with the billed amount.</p>
<div class="split"><div class="panel"><h3>How each meter is allocated</h3><ul class="method" style="display:block;padding-left:0;list-style:none">{drv_list}
<li>{cat_sw('idle')}<b>{E(CATS['idle'][0])}</b> ({money(idle_cost)}) → in proportion to direct cost</li>
<li>{cat_sw('storage')}<b>Storage, OneLake transactions and other</b> → platform, not assignable with the available data</li></ul></div>
<div class="panel"><h3>Reconciliation with the invoice</h3><ul class="facts" style="border:0;margin:0;padding:0">
<li>Workspaces<b>{money(cb_sum)}</b></li><li>Not assignable<b>{money(total_cost - cb_sum)}</b></li><li>Total billed<b>{money(total_cost)}</b></li></ul>
<p class="muted" style="margin:16px 0 0">For precise per-person internal billing, the reference is the Capacity Metrics app{' (installed in the tenant)' if cm_installed else ''} with the “Show user data” setting enabled.</p></div></div>
<div class="toolbar" style="margin-top:16px"><button class="btn" type="button" data-csv="csv-chargeback" data-name="fabric-chargeback-workspaces.csv">Download chargeback CSV</button></div>
<div class="tbl-wrap"><table data-sortable class="dense"><thead><tr>{th('Workspace', 0)}{th('Operations', 1, 'num', 'num')}{th('AI queries', 2, 'num', 'num')}{th('Spark', 3, 'num', 'num')}{th('Direct cost', 4, 'num', 'num')}{th('Idle running share', 5, 'num', 'num')}{th('Total', 6, 'num', 'num')}{th('%', 7, 'num', 'num')}</tr></thead>
<tbody>{''.join(cbrows)}</tbody><tfoot>{ex_html}<tr><td colspan="6">Total</td><td class="num">{money(total_cost)}</td><td class="num">100%</td></tr></tfoot></table></div>
{f'<p class="muted" style="margin:12px 0 0"><b>{len(cb_zero)} workspaces with no billable consumption in the period:</b> {E(", ".join(sorted(cb_zero, key=str.lower)))}.</p>' if cb_zero else ''}
"""
    else:
        cb_block = ('<div class="notice warn"><div><b>Requires the Cost Management invoice</b><p>The chargeback by workspace distributes the billed amount of each meter. '
                    f'{E(cost_why)} In the meantime, “Who consumes” shows real usage by workspace, identity and item.</p></div></div>\n')
    parts.append(f"""<section id="reparto"><h2>Cost chargeback by workspace</h2>
{cb_block}<h3 style="margin-top:24px">Spark notebooks and jobs</h3><p class="muted" style="margin:0 0 12px">{f"Spark cost ({money(spark_cost)}) allocated by the real execution seconds of each session." if cost_ok else "Real execution hours of each session; the cost appears when the invoice is available."}</p>
<div class="tbl-wrap"><table data-sortable class="dense"><thead><tr>{th('Notebook', 0)}{th('Sessions', 1, 'num', 'num')}{th('Scheduled', 2, 'num', 'num')}{th('Failed', 3, 'num', 'num')}{th('Execution', 4, 'num', 'num')}{th('% Spark', 5, 'num', 'num')}{th('Cost', 6, 'num', 'num')}<th>Last (UTC)</th></tr></thead>
<tbody>{nbrows or '<tr><td colspan="8">No Spark sessions in the period.</td></tr>'}</tbody></table></div></section>""")

    # ---------------------------------------------------------------- access & groups section
    acc_ok = (sources.get("access_workspaces") or {}).get("status") == "ok"
    items_src = sources.get("access_items") or {}

    def wlist(keys, n=3):
        names_ = sorted({ws_label(k) for k in keys}, key=str.lower)
        return ", ".join(names_[:n]) + (f" and {len(names_) - n} more" if len(names_) > n else "")

    grows = []
    for g in grp_list:
        it_names = sorted({v[0] for v in g["items"].values()}, key=str.lower)
        where = []
        if g["ws"]:
            where.append(f'{len(g["ws"])} workspace{"s" if len(g["ws"]) != 1 else ""} ({E(wlist(g["ws"]))})')
        if g["items"]:
            where.append(f'{len(g["items"])} item{"s" if len(g["items"]) != 1 else ""} in {E(wlist({k[0] for k in g["items"]}))}'
                         f'<span class="cell-sub">{E(", ".join(it_names[:4]) + (" …" if len(it_names) > 4 else ""))}</span>')
        mem_txt = (f'{g["active"]} of {g["n_members"]}' + (f'<span class="cell-sub">{g["new"]} new</span>' if g["new"] else "")) if g["n_members"] is not None else "—"
        grows.append(f'<tr><td class="cell-strong">{E(g["name"])}</td><td>{"<br>".join(where) or "—"}</td>'
                     f'<td class="num" data-v="{g["active"] if g["active"] is not None else -1}">{mem_txt}</td>'
                     f'<td class="num" data-v="{g["member_ops"] if g["member_ops"] is not None else g["item_ops"]}">{fn(g["member_ops"]) if g["member_ops"] is not None else fn(g["item_ops"])}'
                     f'<span class="cell-sub">{"by its members on its resources" if g["member_ops"] is not None else "on what it can use"}</span></td>'
                     f'<td class="num" data-v="{(g["member_cost"] or 0):.4f}">{money(g["member_cost"]) if (g["member_cost"] is not None and cost_ok) else "—"}</td>'
                     f'<td class="num" data-v="{g["exposure"]:.4f}">{money(g["exposure"]) if cost_ok else "—"}</td></tr>')
    def res_list(top, with_nums=False):
        if not top:
            return "—"
        out_ = []
        for rk, o, c in top:
            extra = (" · " + fn(o) + " ops" + (" · " + money(c) if cost_ok else "")) if with_nums else ""
            out_.append(E(rk[1]) + ' <span class="cell-sub" style="display:inline">· ' + E(ws_label(rk[0])) + extra + "</span>")
        return "<br>".join(out_)

    gdet = []
    for g in grp_list:
        if g.get("res") is None:
            continue
        head = ('<summary style="cursor:pointer"><b>' + E(g["name"]) + "</b> · " + str(g["active"]) + " of " + str(g["n_members"])
                + " members used its resources" + ((" · " + money(g["member_cost"])) if cost_ok else "") + "</summary>")
        if not g["res"]:
            gdet.append('<details class="panel" style="margin-top:12px">' + head
                        + '<p class="muted" style="margin:12px 0 0">No member used the resources granted to this group in the period.</p></details>')
            continue
        rrows = "".join('<tr><td class="cell-strong">' + E(rk[1]) + "</td><td>" + E(ws_label(rk[0])) + '</td><td class="num">' + fn(o)
                        + '</td><td class="num">' + (money(c) if cost_ok else "—") + "</td></tr>" for rk, o, c in g["res"][:12])
        mrows = "".join('<tr><td class="cell-strong">' + E(plabel(m["k"])) + '</td><td class="num">' + fn(m["ops"]) + '</td><td class="num">'
                        + (money(m["cost"]) if cost_ok else "—") + "</td><td>" + res_list(m["top"], True) + '</td><td class="num">'
                        + fn(m["total_ops"]) + ' ops<span class="cell-sub">' + (money(m["total_cost"]) if cost_ok else "") + "</span></td></tr>"
                        for m in g["mdetail"][:25])
        gdet.append('<details class="panel" style="margin-top:12px">' + head
                    + '<h3 style="margin-top:16px">Group resources used by its members</h3>'
                    + '<div class="tbl-wrap"><table class="dense"><thead><tr><th>Item</th><th>Workspace</th><th class="num">Operations</th><th class="num">Cost</th></tr></thead><tbody>'
                    + rrows + "</tbody></table></div>"
                    + '<h3 style="margin-top:16px">What each group member consumes</h3>'
                    + '<div class="tbl-wrap"><table class="dense"><thead><tr><th>Person</th><th class="num">Operations</th><th class="num">Cost</th>'
                    + '<th>Resources used</th><th class="num">Person’s total</th></tr></thead><tbody>' + mrows + "</tbody></table></div>"
                    + ('<p class="muted" style="margin:8px 0 0">Showing the 25 members with the highest consumption out of ' + str(len(g["mdetail"])) + ".</p>" if len(g["mdetail"]) > 25 else "")
                    + "</details>")
    grp_detail = ('<h3 style="margin-top:24px">Detail by group: which resources are consumed and by whom</h3>'
                  '<p class="muted" style="margin:0 0 8px">Expand a group to see which of the resources granted to it are used by its members, and how much each person consumes. '
                  '“Person’s total” includes everything that person did in Fabric, including outside the group’s resources.</p>' + "".join(gdet)) if gdet else ""

    pmax = 40
    prow_acc = []
    for r in people_list[:pmax]:
        state = pill("ok", "Active") if r["ops"] else pill("warn", "No activity")
        if r["new"]:
            state += " " + pill("neutral", "New")
        prow_acc.append(f'<tr><td class="cell-strong">{E(plabel(r["k"]))}</td><td>{E(", ".join(r["via"]))}</td>'
                        f'<td class="num" data-v="{r["n_ws"] + r["n_items"]}">{r["n_ws"]} ws · {r["n_items"]} item{"s" if r["n_items"] != 1 else ""}</td>'
                        f'<td class="num" data-v="{r["ops"]}">{fn(r["ops"])}</td><td class="num" data-v="{r["cost"]:.4f}">{money(r["cost"]) if cost_ok else "—"}</td>'
                        f'<td>{res_list(r["top"])}</td><td class="nw">{dmon(r["last"], " %H:%M") if r["last"] else "—"}</td><td>{state}</td></tr>')
    if gm_src.get("status") == "pending":
        gm_notice = ('<div class="notice warn"><div><b>A permission is missing to attribute usage to the members of each group</b>'
                     '<p>The report already sees which groups have access to each workspace and item, but not who belongs to each group. '
                     'In the Fabric tenant, grant the SRE Agent identity the Microsoft Graph application permissions '
                     '<strong>GroupMember.Read.All</strong> (members) and <strong>User.Read.All</strong> (creation date, to detect new users), with admin consent. '
                     'Both are read-only. In the meantime, the “Cost of what it can use” column allocates cost by the resources each group has access to.</p></div></div>')
    else:
        gm_notice = ""
    tech_note = (f'<p class="muted" style="margin:12px 0 0">{E(", ".join(g["name"] for g in grp_tech))} is not shown: it is the technical group that gives the SRE Agent read access '
                 f'({len(grp_tech[0]["ws"])} workspaces and {len(grp_tech[0]["items"])} items).</p>') if grp_tech else ""
    if acc_ok:
        acc_block = f"""<p class="sub">Who has access to each workspace (roles) and to each item (shared permissions), including groups, read from the Fabric admin APIs
in read-only mode{f" ({E(items_src.get('note') or '')})" if items_src.get("note") else ""}. Groups are shown by name; people are shown {'with their identity' if show_ids else 'masked'}.</p>
<ul class="kv"><li>Groups with access<b>{len(grp_list)}</b>to workspaces or items</li><li>People with access<b>{len(people_list)}</b>{'directly or through a group' if members_known else 'assigned directly'}</li>
<li>With access but no activity<b>{len(no_activity)}</b>in the last {act_ok or act_days} days</li><li>New users<b>{len(new_people) if members_known else '—'}</b>{'created in the period' if members_known else 'requires permission to read users'}</li></ul>
{gm_notice}
<h3 style="margin-top:24px">Consumption by group</h3>
<p class="muted" style="margin:0 0 12px"><strong>Member consumption</strong>: cost of what the group's members did in the workspaces and items granted to the group (same per-meter allocation as the chargeback). If someone also has access directly or through another group, their use of a resource counts in every group that grants it.
<strong>Cost of what it can use</strong>: cost of the workspaces where the group has a role plus the items shared with it. These columns cannot be added up across groups.</p>
<div class="tbl-wrap"><table data-sortable class="dense"><thead><tr>{th('Group', 0)}<th>Access</th>{th('Active members', 2, 'num', 'num')}{th('Operations', 3, 'num', 'num')}{th('Member consumption', 4, 'num', 'num')}{th('Cost of what it can use', 5, 'num', 'num')}</tr></thead>
<tbody>{''.join(grows) or '<tr><td colspan="6">No groups have access to workspaces or items (apart from the SRE Agent technical group).</td></tr>'}</tbody></table></div>{tech_note}
{grp_detail}
<h3 style="margin-top:24px">People with access</h3>
<p class="muted" style="margin:0 0 12px">A person can have access and not appear in “Who consumes” because they have not worked in the period{'' if members_known else ', or because they get access through a group whose members cannot be read yet'}.{f' Showing the first {pmax} of {len(people_list)}.' if len(people_list) > pmax else ''}</p>
<div class="tbl-wrap"><table data-sortable class="dense"><thead><tr>{th('Person', 0)}<th>Via</th>{th('Access', 2, 'num', 'num')}{th('Operations', 3, 'num', 'num')}{th('Consumption', 4, 'num', 'num')}<th>What they consume</th><th>Last (UTC)</th><th>Status</th></tr></thead>
<tbody>{''.join(prow_acc) or '<tr><td colspan="8">No people with access.</td></tr>'}</tbody></table></div>"""
    else:
        acc_block = ('<div class="notice warn"><div><b>Could not read who has access</b><p>The workspace admin API did not respond '
                     f'({E(str((sources.get("access_workspaces") or {}).get("http") or "no response"))}). Check the “Service principals can access read-only admin APIs” setting.</p></div></div>')
    parts.append(f"""<section id="acceso"><h2>Access and consumption by group</h2>
{acc_block}</section>""")

    # ================================================================== v5 HTML · part 3 (commitments, governance, questions, sources)
    cmp_items = []
    same_res = bool(annual_res.get(1) and annual_res.get(3) and abs(annual_res[3] - annual_res[1]) / annual_res[1] < 0.01)
    if annual_payg_cu:
        cmp_items.append(("Pay-as-you-go at the current rate" + ("" if cost_ok else " (running hours × public price)"), annual_payg_cu, "#117865"))
    if same_res:
        cmp_items.append((f"1- or 3-year reservation ({focus_sku}) · same annual price in the public price list", annual_res[1], "#8aa1b4"))
    else:
        for y in (1, 3):
            if annual_res.get(y):
                cmp_items.append((f"{y}-year reservation ({focus_sku})", annual_res[y], "#8aa1b4"))
    if hourly:
        cmp_items.append((f"Pay-as-you-go 24×7 ({focus_sku})", hourly * 8760, "#d99a2b"))
    cmp_max = max((v for _, v, _ in cmp_items), default=1)
    cmp_html = "".join(f'<li><span>{E(n)}</span><b>{money(v, 0)}/year</b><span class="track"><span class="fill" style="display:block;width:{v / cmp_max * 100:.1f}%;background:{c}"></span></span></li>'
                       for n, v, c in cmp_items)
    if same_res and 1 in breakeven:
        be_html = f'<li>1- or 3-year reservation<b>{pc(breakeven[1], 0)}</b>of the time running needed to break even</li>'
    else:
        be_html = "".join(f'<li>{y}-year reservation<b>{pc(b, 0)}</b>of the time running needed to break even</li>' for y, b in sorted(breakeven.items()))
    srows = "".join(f'<tr><td class="cell-strong">{E(s_["sku"])}</td><td class="num">{s_["cu"]}</td><td class="num">{pc(s_["avg_load"], 0)}</td>'
                    f'<td class="num">{pc(s_["peak_load"], 0)}</td><td class="num">{money(s_["save_month"], 0)}</td>'
                    f'<td>{pill("ok", "Viable on average") if s_["peak_load"] < 0.6 else (pill("warn", "Tight") if s_["peak_load"] < 0.9 else pill("crit", "Insufficient"))}</td></tr>'
                    for s_ in sizes)
    if cost_ok:
        size_html = f"""<h3 style="margin-top:24px">Size scenarios</h3>
<p class="muted" style="margin:0 0 12px">Load = CUs used per running hour ÷ CUs of the SKU. “Peak” is the busiest day by hourly average{f" ({dlabel(peak_day['date'])})" if peak_day else ''}.
It does not capture bursts lasting a few minutes: confirm in Capacity Metrics before changing size.</p>
<div class="tbl-wrap"><table class="dense"><thead><tr><th>SKU</th><th class="num">CU</th><th class="num">Average load</th><th class="num">Peak-day load</th><th class="num">Saving/month</th><th>Assessment</th></tr></thead>
<tbody><tr><td class="cell-strong">{E(focus_sku)} (current)</td><td class="num">{focus_cu}</td><td class="num">{pc(avg_cu_on / focus_cu if focus_cu else 0, 0)}</td><td class="num">{pc(peak_day_avg / focus_cu if focus_cu else 0, 0)}</td><td class="num">—</td><td>{pill("neutral", "Current")}</td></tr>{srows}</tbody></table></div>"""
    else:
        size_html = ('<h3 style="margin-top:24px">Size scenarios</h3><div class="notice warn"><div><b>Requires the Cost Management invoice</b>'
                     f'<p>The hourly load is calculated from the billed and consumed CU-h. {E(cost_why)}</p></div></div>')
    parts.append(f"""<section id="compromisos"><h2>Capacity reservation and size</h2>
<p class="sub">Public Azure prices for {E(focus_region or 'the region')} and real running hours. A reservation is paid for 24 hours a day; it only pays off if the capacity is running almost all the time.</p>
<div class="split"><div class="panel"><h3>Annual cost compared</h3><ul class="bars">{cmp_html or '<li>No prices available.</li>'}</ul>
<p class="muted" style="margin:16px 0 0">Pay-as-you-go price: {money(price_cu, 4)}/CU-h · {E(price_src)}.</p></div>
<div class="panel"><h3>Break-even threshold</h3><ul class="kv cols2">
<li>Running now<b>{pc(uptime, 0)}</b>{fn(on_hours, 0)} h of {fn(win_hours, 0)} h</li>{be_html}</ul>
<p class="muted" style="margin:16px 0 0">{'With current usage, pay-as-you-go plus pausing is cheaper than any reservation.' if breakeven and uptime < min(breakeven.values()) else 'Current usage is above the break-even threshold of at least one reservation.'}</p></div></div>
{size_html}</section>""")

    # governance
    crows = "".join(f'<tr><td><span class="cell-strong">{E(c["name"])}</span><span class="cell-sub">{E(c["region"])}{" · " + E(c["rg"]) if c["rg"] else ""}</span></td>'
                    f'<td>{E(c["sku"])}</td><td>{E(c["state"])}</td><td class="num">{c["ws"]}</td><td class="num">{c["items"]}</td>'
                    f'<td class="num">{money(c["cost"]) if c["arm"] else "—"}</td><td>{E(c["tags"])}</td><td>{pill(c["lvl"], c["finding"])}</td></tr>' for c in caps_tbl)
    rrows = "".join(f'<tr><td><span class="cell-strong">{E(r["name"])}</span><span class="cell-sub">{E(r["ws"])}</span></td><td>{E(r["kind"])}</td>'
                    f'<td class="nw">{dmon(r["last"], " %Y") if r["last"] else "—"}</td><td class="num">{r["age"] if r["age"] is not None else "—"}</td>'
                    f'<td>{(pill("warn", "Not refreshed >60 days") + "<span class=cell-sub>Last: " + E(r["status"]) + "</span>") if r["level"] == "warn" else pill(r["level"], r["status"])}{("<span class=cell-sub>" + E(r["err"]) + "</span>") if r["err"] else ""}</td>'
                    f'<td>{"Yes" if r["sched"] else "No"}</td></tr>' for r in refs[:20])
    tsrows = "".join(f'<tr><td><span class="cell-strong">{E(r["title"])}</span><span class="cell-sub">{E(r["why"])}</span></td>'
                     f'<td>{pill("ok" if r["enabled"] else "neutral", "Enabled" if r["enabled"] else "Disabled")}</td><td>{E(r["scope"])}</td></tr>' for r in ts_rows)
    itypes = "".join(f'<li>{E(t)}<b>{n}</b></li>' for t, n in item_types.most_common(12))
    ol_line = (f"{len(ol_ok)} of {len(ol)} lakehouses read · {fn(ol_bytes / 1024 ** 3, 2)} GB in tables and files" if ol else "No lakehouses in the inventory")
    parts.append(f"""<section id="gobierno"><h2>Inventory and governance</h2>
<p class="sub">What is in the tenant, and what is worth tidying up to keep costs under control.</p>
<ul class="kv"><li>Capacities<b>{len(caps_tbl)}</b>{sum(1 for c in caps_tbl if c['state'].lower() == 'active')} active</li>
<li>Workspaces<b>{len(workspaces)}</b>{sum(1 for w in workspaces if (w.get('capacity_id') or '').lower() in paid_caps)} on paid capacity</li>
<li>Items<b>{fn(len(items))}</b>{len(stale_items)} unchanged in 90 days</li><li>OneLake read<b>{fn(ol_bytes / 1024 ** 3, 2)} GB</b>{E(ol_line)}</li></ul>
<h3 style="margin-top:24px">Capacities</h3>
<div class="tbl-wrap"><table class="dense"><thead><tr><th>Capacity</th><th>SKU</th><th>State</th><th class="num">Workspaces</th><th class="num">Items</th><th class="num">Period cost</th><th>Tags</th><th>Finding</th></tr></thead>
<tbody>{crows}</tbody></table></div>
<div class="panel" style="margin-top:16px"><h3>Items by type</h3><ul class="kv types">{itypes}</ul></div>
<div class="panel" style="margin-top:16px"><h3>Tenant settings that affect cost</h3><div class="tbl-wrap"><table class="dense"><thead><tr><th>Setting</th><th>Status</th><th>Scope</th></tr></thead>
<tbody>{tsrows or '<tr><td colspan="3">—</td></tr>'}</tbody></table></div></div>
<h3 style="margin-top:24px">Model and dataflow refreshes</h3>
<div class="tbl-wrap"><table class="dense"><thead><tr><th>Item</th><th>Type</th><th>Last</th><th class="num">Days</th><th>Status</th><th>Scheduled</th></tr></thead>
<tbody>{rrows or '<tr><td colspan="6">No refreshable items.</td></tr>'}</tbody></table></div></section>""")

    # questions
    QS = [
        ("Cost and invoice", [
            "How much has Fabric cost me over the last 30 days, and on which meters?",
            "Compare this month's cost with last month and explain the difference.",
            "What share of the invoice is capacity running with no use?",
            "On which days was the capacity paid for without anyone using it?"]),
        ("Savings and capacity", [
            "At what time should the capacity be paused so that no work is cut off?",
            "Does a capacity reservation pay off with my current usage?",
            "Could I move to a smaller SKU? Give me the average load and the peak-day load.",
            "Which capacities are paused or empty, and how much would they cost if running?"]),
        ("Who consumes what", [
            "Allocate the period's cost by workspace and explain the method.",
            "Which users and apps generate the most load, and in which workspaces?",
            "Which Spark notebooks consume the most, and which run on a schedule?",
            "How much does AI (Copilot, Data Agents) cost, and who uses it?"]),
        ("Governance", [
            "Which refreshes have failed, and since when?",
            "Which workspaces on paid capacity have not been used this month?",
            "Which tenant settings affect cost, and how are they configured?",
            "Generate the report with visible identities for the FinOps team."]),
    ]
    qhtml = "".join(f'<article><h3>{E(g)}</h3><ul>' + "".join(f'<li><span>{E(q)}</span><button type="button" data-copy="{E(q)}" aria-label="Copy: {E(q)}">Copy</button></li>' for q in qs) + "</ul></article>" for g, qs in QS)
    parts.append(f"""<section id="preguntas"><h2>Ask the agent</h2>
<p class="sub">Copy any of these questions into the Azure SRE Agent chat (agent <b class="nw">fabric-chargeback-live</b>). The agent reads the tenant live again and answers with figures from this same model.</p>
<div class="qs">{qhtml}</div></section>""")

    # sources
    SRC_LBL = {"capacities": ("Fabric capacities", "Fabric Admin API"), "workspaces": ("Workspaces", "Fabric Admin API"),
               "items": ("Items", "Fabric Admin API"), "activity": ("Activity log", "Power BI Admin API · activityevents"),
               "refreshables": ("Refreshes", "Power BI Admin API · refreshables"), "spark": ("Spark sessions", "Fabric Spark Livy API"),
               "onelake": ("OneLake size", "OneLake DFS API"), "arm": ("Subscriptions", "Azure Resource Manager"),
               "cost": ("Daily cost by meter", "Azure Cost Management · ActualCost"), "activity_log": ("Start and pause", "Azure Activity Log"),
               "cost_monthly": ("Monthly cost (12 months)", "Azure Cost Management"), "sub_costs": ("Subscription cost by service", "Azure Cost Management"),
               "prices": ("Public prices", "Azure Retail Prices API"),
               "access_workspaces": ("Workspace access", "Power BI Admin API · groups + users"), "access_items": ("Item access", "Admin scanner API · getInfo (artifact users)"),
               "group_members": ("Group members", "Microsoft Graph · transitiveMembers"), "cross_tenant_auth": ("Cross-tenant credential", "Key Vault · app certificate"), "tenant_settings": ("Tenant settings", "Fabric Admin API · tenantsettings")}
    st_pill = {"ok": ("ok", "Read"), "partial": ("warn", "Partial"), "error": ("crit", "Error"),
               "paused": ("neutral", "Capacity paused"), "pending": ("warn", "Permission pending")}
    srcrows = []
    for k, v in sources.items():
        if k.startswith("token_"):
            k_lbl = (f"Token {k[6:]}", "Entra ID · secretless federation")
        else:
            k_lbl = SRC_LBL.get(k, (k, ""))
        lv, tx = st_pill.get(v.get("status"), ("neutral", v.get("status") or "—"))
        srcrows.append(f'<tr><td><span class="cell-strong">{E(k_lbl[0])}</span><span class="cell-sub">{E(k_lbl[1])}</span></td><td>{pill(lv, tx)}</td>'
                       f'<td class="num">{E(str(v.get("http") or "—"))}</td><td class="num">{fn(v.get("count") or 0)}</td><td class="num">{fn(v.get("seconds") or 0, 1)} s</td>'
                       f'<td>{E(v.get("note") or "")}</td></tr>')
    srcrows.append(f'<tr><td><span class="cell-strong">Capacity Metrics app</span><span class="cell-sub">Power BI · semantic model</span></td>'
                   f'<td>{pill("info", "Installed · not queryable") if cm_installed else pill("neutral", "Not detected")}</td><td class="num">—</td>'
                   f'<td class="num">{len(cm_items) if cm_installed else 0}</td><td class="num">—</td>'
                   f'<td>{"Microsoft does not allow models with RLS/SSO like this one to be queried with a service principal. Use the app to validate peaks and throttling." if cm_installed else "Install it to see per-minute peaks and throttling."}</td></tr>')
    parts.append(f"""<section id="fuentes"><h2>Sources and method</h2>
<p class="sub">Everything is read when the report is generated, in read-only mode, {'with a multi-tenant app identity in the Fabric tenant (certificate in Key Vault or federated credential, no secrets in the code)' if raw.get('auth_mode', 'cross_tenant') == 'cross_tenant' else 'with the SRE Agent managed identity, no secrets'}. This is the actual status of each source in this run.</p>
<div class="tbl-wrap"><table class="dense"><thead><tr><th>Source</th><th>Status</th><th class="num">HTTP</th><th class="num">Records</th><th class="num">Time</th><th>Note</th></tr></thead>
<tbody>{''.join(srcrows)}</tbody></table></div>
<div class="method panel" style="margin-top:16px"><div><h3>How it is calculated</h3><ul>
<li>Cost is the actual Cost Management amount (ActualCost) for <code>microsoft.fabric/capacities</code> resources, by day and meter, in {E(CUR)}.</li>
<li>Running hours come from the resume/suspend events in the Activity Log and are validated against the invoice (ratio invoice ÷ hours × CU).</li>
<li>Real work means operations in the Fabric activity log plus Spark sessions; administrative operations and this report's own operations are excluded.</li>
<li>Monthly projections scale the observed period to 30 days.</li></ul></div>
<div><h3>Known limitations</h3><ul>
<li>The Fabric activity log keeps {act_days or 28} days: earlier work is not visible.</li>
<li>Cost Management publishes cost with a 24–48 h delay; the most recent days may be missing.</li>
<li>Hourly averages do not show bursts lasting a few minutes: for sizing and throttling, use Capacity Metrics.</li>
<li>When the capacity is paused, Fabric bills all pending smoothed operations at once.</li></ul></div></div></section>""")

    # ================================================================== v5 OUTPUT (files + agent answer)
    def dec(v, d=4):
        return f"{(v or 0):.{d}f}"

    def csv_text(header_row, rows_):
        buf = io.StringIO()
        w = csv.writer(buf, delimiter=",", lineterminator="\n")
        w.writerow(header_row)
        w.writerows(rows_)
        return buf.getvalue()

    cats_cb = [c for c in cat_order if c in DRIVER]
    cb_csv_rows = []
    for r in cb:
        cb_csv_rows.append([r["name"], r["id"], r["cap"], r["sku"], r["items"], r["events"], r["ai"], dec(r["spark_h"], 2)]
                           + [dec(r["by_cat"].get(c, 0)) for c in cats_cb] + [dec(r["direct"]), dec(r["idle"]), dec(r["total"]),
                                                                            dec(r["total"] / total_cost * 100 if total_cost else 0, 2)])
    for n, v in extra_rows:
        cb_csv_rows.append([n, "", "", "", "", "", "", ""] + ["" for _ in cats_cb] + [dec(v), "", dec(v), dec(v / total_cost * 100 if total_cost else 0, 2)])
    cb_csv = csv_text(["workspace", "workspace_id", "capacity", "sku", "items", "operations", "ai_queries", "spark_hours"]
                      + [f"cost_{c}" for c in cats_cb] + ["direct_cost", "idle_running_share", "total", "percentage"], cb_csv_rows)
    cap_nm = {rid: (c.get("name") or rid.rsplit("/", 1)[-1]) for rid, c in cap_by_rid.items()}
    mt_csv = csv_text(["date", "capacity", "meter", "category", "quantity", "cost", "currency"],
                      [[f"{c['date'][:4]}-{c['date'][4:6]}-{c['date'][6:8]}", cap_nm.get(c["rid"], c["rid"].rsplit("/", 1)[-1]), c["meter"],
                        CATS[meter_cat(c["meter"])][0], dec(c["qty"]), dec(c["cost"]), c.get("currency") or CUR]
                       for c in sorted(crow, key=lambda c: (c["date"], -c["cost"]))])

    def script_block(i, txt):
        return f'<script type="text/plain" id="{i}">{txt.replace("</", "<\\/")}</script>'

    parts.append(f"""</div></main><footer><div class="wrap">Generated by Azure SRE Agent · tool generate-fabric-chargeback-report v5.0 ·
{dmon(gen, ' %Y %H:%M')} UTC · read in {fn(raw.get('collect_seconds') or 0, 1)} s · read-only, no sample data.</div></footer>
{script_block('csv-meters', mt_csv)}{script_block('csv-chargeback', cb_csv)}<script>{JS}</script></body></html>""")
    html_doc = "".join(parts)

    def r2(v):
        return round(float(v or 0), 2)

    answer = {
        "status": "ok", "version": "5.1", "auth_mode": raw.get("auth_mode", AUTH_MODE), "generated_utc": gen.strftime("%Y-%m-%dT%H:%M:%SZ"), "period": period_label,
        "window_utc": [win0.strftime("%Y-%m-%d"), gen.strftime("%Y-%m-%d")], "currency": CUR, "identities": "visible" if show_ids else "masked",
        "cost_available": cost_ok, "cost_unavailable_reason": None if cost_ok else cost_why,
        "headline": {"total_cost": r2(total_cost) if cost_ok else None, "consumed_by_workloads": r2(consumption_cost) if cost_ok else None,
                     "on_without_use": r2(idle_cost) if cost_ok else None,
                     "storage": r2(cat_cost.get("storage", 0)) if cost_ok else None, "on_hours": round(on_hours, 1), "uptime_pct": round(uptime * 100, 1),
                     "utilization_pct_while_on": round(util_all * 100, 1) if cost_ok else None, "hourly_cost_when_on": r2(hourly),
                     "on_hours_x_public_price": r2(hourly * on_hours),
                     "idle_after_last_work_hours": round(tail_h, 1), "monthly_saving_identified": r2(headline_save)},
        "focus_capacity": {"name": focus_name, "sku": focus_sku, "region": focus_region, "state": focus.get("state"),
                           "price_per_cu_hour": round(price_cu, 4), "price_source": price_src,
                           "auto_suspend_utc": hhmm(susp_times[-1]) if susp_times else None},
        "cost_by_category": {CATS[c][0]: r2(cat_cost[c]) for c in cat_order},
        "meters": [{"meter": m["name"], "category": CATS[m["cat"]][0], "quantity": round(m["qty"], 2), "cost": r2(m["cost"]), "explanation": mexpl(m["name"])}
                   for m in sorted(meters.values(), key=lambda m: -m["cost"]) if m["cost"] >= 0.01],
        "cost_daily": [{"date": x["date"], "on_hours": round(x["on_h"], 2), "cost": r2(x["cost"]), "cu_h_billed": round(x["billed"], 1),
                        "cu_h_used": round(x["consumed"], 1), "utilization_pct": round((x["util"] or 0) * 100, 1), "cost_pending": x["lag"]} for x in daily],
        "cost_monthly": [{"month": k, "cost": r2(mon_tot[k]), "in_progress": k == cur_month, "by_capacity": {c: r2(v) for c, v in mon[k].items()}} for k in mon_keys],
        "subscription_context": {"total": r2(sub_total), "fabric_share_pct": round(fabric_sub / sub_total * 100, 1) if sub_total else None,
                                 "by_service": {s: r2(v) for s, v in sub_svc.most_common(10)},
                                 "fabric_named_resources": [{"resource": rshort(r["rid"])[0], "service": r["service"], "cost": r2(r["cost"])} for r in fab_adj[:10]]},
        "actions": [{"kind": a["kind"], "title": a["title"], "why": a["why"], "evidence": a["evidence"], "value": r2(a["value"]) if a.get("value") else None,
                     "unit": a["unit"], "source": a["src"]} for a in actions],
        "pause_whatif": [{"pause_hour_utc": w["hour"], "hours_saved": round(w["saved_h"], 1), "saving_per_month": r2(w["save"] * per_month),
                          "days_with_work_cut": w["conflicts"]} for w in whatif],
        "reservation": {"breakeven_uptime_pct": {f"{y}y": round(b * 100, 1) for y, b in breakeven.items()}, "annual_payg_current": r2(annual_payg_cu),
                        "annual_reservation": {f"{y}y": r2(v) for y, v in annual_res.items()}},
        "size_scenarios": [{"sku": s_["sku"], "avg_load_pct": round(s_["avg_load"] * 100), "peak_day_load_pct": round(s_["peak_load"] * 100),
                            "saving_per_month": r2(s_["save_month"])} for s_ in sizes],
        "chargeback_by_workspace": [{"workspace": r["name"], "capacity": r["cap"], "operations": r["events"], "ai_queries": r["ai"],
                                     "spark_hours": round(r["spark_h"], 2), "direct": r2(r["direct"]), "idle_share": r2(r["idle"]), "total": r2(r["total"])}
                                    for r in cb if r["total"] >= 0.01][:25],
        "chargeback_not_assignable": {n: r2(v) for n, v in extra_rows},
        "access_by_group": [{"group": g["name"], "workspaces": [ws_label(w) for w in g["ws"]],
                             "items": [{"item": v[0], "type": v[1], "workspace": ws_label(k[0]), "permission": v[2]} for k, v in g["items"].items()],
                             "members": g["n_members"], "active_members": g["active"], "new_members": g["new"],
                             "member_operations": g["member_ops"], "member_cost": r2(g["member_cost"]) if (g["member_cost"] is not None and cost_ok) else None,
                             "member_scope": "operations of the group members on the workspaces and items granted to the group",
                             "cost_of_accessible_resources": r2(g["exposure"]) if cost_ok else None,
                             "resources_consumed_by_members": [{"item": rk[1], "workspace": ws_label(rk[0]), "operations": o, "cost": r2(c) if cost_ok else None}
                                                               for rk, o, c in (g["res"] or [])[:15]],
                             "members_consumption": [{"person": plabel(m["k"]), "operations": m["ops"], "cost": r2(m["cost"]) if cost_ok else None,
                                                      "total_operations": m["total_ops"], "total_cost": r2(m["total_cost"]) if cost_ok else None,
                                                      "top_resources": [{"item": rk[1], "workspace": ws_label(rk[0]), "operations": o, "cost": r2(c) if cost_ok else None}
                                                                        for rk, o, c in m["top"]]} for m in (g["mdetail"] or [])[:25]]} for g in grp_list],
        "people_with_access": {"total": len(people_list), "without_activity": len(no_activity), "new": len(new_people) if members_known else None,
                               "group_membership": "read" if members_known else (gm_src.get("status") or "not_read"),
                               "without_activity_list": [plabel(r["k"]) for r in no_activity][:25],
                               "consumers": [{"person": plabel(r["k"]), "via": r["via"], "operations": r["ops"], "cost": r2(r["cost"]) if cost_ok else None,
                                              "top_resources": [{"item": rk[1], "workspace": ws_label(rk[0]), "operations": o, "cost": r2(c) if cost_ok else None}
                                                                for rk, o, c in r["top"]]} for r in people_list if r["ops"]][:30]},
        "top_identities": [{"identity": plabel(p["k"]), "kind": p["kind"], "operations": p["work"], "active_days": len(p["days"]),
                            "spark_hours": round(p.get("spark_h", 0), 2), "workspaces": [ws_label(w) for w, _ in p["ws"].most_common(3)]} for p in humans[:10]],
        "top_items": [{"item": r["it"], "type": r["itt"], "workspace": ws_label(r["ws"]), "operations": r["n"], "identities": len(r["users"])} for r in top_items[:10]],
        "spark_notebooks": [{"notebook": n["item"], "workspace": ws_label(n["ws"]), "sessions": n["sessions"], "scheduled": n["sched"], "failed": n["failed"],
                             "hours": round(n["run"] / 3600, 2), "cost": r2(n["cost"])} for n in nb_list[:10]],
        "capacities": [{"name": c["name"], "sku": c["sku"], "state": c["state"], "workspaces": c["ws"], "cost": r2(c["cost"]), "finding": c["finding"], "tags": c["tags"]} for c in caps_tbl],
        "failed_refreshes": [{"item": r["name"], "workspace": r["ws"], "last": r["last"].strftime("%Y-%m-%d") if r["last"] else None, "error": r["err"]} for r in ref_failed],
        "idle_workspaces_on_paid_capacity": [r["name"] for r in idle_ws],
        "tenant_settings": [{"setting": r["title"], "enabled": r["enabled"], "scope": r["scope"]} for r in ts_rows],
        "capacity_metrics_app": "installed; not queryable by service principal (RLS/SSO model)" if cm_installed else "not detected",
        "sources": {k: {"status": v.get("status"), "http": v.get("http"), "count": v.get("count"), "note": v.get("note")} for k, v in sources.items()},
        "analysis_seconds": round(time.monotonic() - t_an, 1),
    }
    if operation == "summary":
        return answer

    base = f"fabric-finops-{stamp}"
    names = {"report": f"{base}.html", "snapshot": f"{base}-snapshot.json", "chargeback_csv": f"{base}-chargeback-by-workspace.csv",
             "meters_csv": f"{base}-daily-cost-by-meter.csv"}
    snap = dict(answer)
    snap["raw_counts"] = {k: (len(v) if isinstance(v, list) else None) for k, v in raw.items() if isinstance(v, list)}
    blobs = {names["report"]: html_doc.encode("utf-8"),
             names["snapshot"]: json.dumps(snap, ensure_ascii=False, indent=2, default=str).encode("utf-8"),
             names["chargeback_csv"]: ("\ufeff" + cb_csv).encode("utf-8"),
             names["meters_csv"]: ("\ufeff" + mt_csv).encode("utf-8")}
    for fname, data in blobs.items():
        (cwd / fname).write_bytes(data)
    answer.update({"report_url": file_url(names["report"]), "snapshot_url": file_url(names["snapshot"]),
                   "chargeback_csv_url": file_url(names["chargeback_csv"]), "meters_csv_url": file_url(names["meters_csv"])})
    for k in ("cost_daily", "meters"):
        answer[k] = answer[k][:12] if k == "meters" else answer[k]
    return answer

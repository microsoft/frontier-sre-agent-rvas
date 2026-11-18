# generate-sqlmi-maintenance-report
# Azure SQL Managed Instance: resilience to maintenance windows.
# Answers with data "why do users see errors when SQL MI maintenance happens?":
#   1) SQL MI inventory: maintenance window, tier, connection type (Proxy/Redirect), failover groups.
#   2) Real reconfigurations (Resource Health + Activity Log) and upcoming maintenance (Service Health).
#   3) Correlation with Application Insights: which applications surface errors to users (no retries)
#      and which absorb them (with retries).
#   4) Recommended window per instance from real load, plus an action plan with commands.
# Modes: data_source="demo" (deterministic simulated data, no configuration needed) | "live" | "auto".
# Outputs: a self-contained HTML report, the full JSON and two CSV files, all in English.
# Read-only · Version 1.0 · October 2026


def main(operation: str = "report", period: str = "last_30d", data_source: str = "auto") -> dict:
    """Read-only SQL Managed Instance maintenance resilience report (HTML + JSON + 2 CSV)."""
    import base64
    import csv
    import html
    import io
    import json
    import os
    import random
    import re
    import time
    from collections import defaultdict
    from concurrent.futures import ThreadPoolExecutor
    from datetime import datetime, timedelta, timezone
    from pathlib import Path
    from urllib.parse import quote

    # ---- CONFIGURE (see README, step 4) ---------------------------------------------------------------
    # Client ID of the SRE Agent user-assigned managed identity. Only needed in live mode.
    MANAGED_IDENTITY_CLIENT_ID = "<SRE_AGENT_UAMI_CLIENT_ID>"
    # Subscriptions to analyze, comma separated. Empty or placeholder = every subscription the identity can read.
    SUBSCRIPTION_IDS = "<SUBSCRIPTION_IDS_COMMA_SEPARATED>"
    # Log Analytics Workspace IDs (the "Workspace ID" GUID) where the Application Insights of the apps
    # that use SQL MI write. Empty or placeholder = no per-application correlation.
    LOG_ANALYTICS_WORKSPACE_IDS = "<LOG_ANALYTICS_WORKSPACE_IDS_COMMA_SEPARATED>"
    # Business time zone used to read peak hours and windows (Azure windows use the region's local time).
    LOCAL_TIMEZONE = "Europe/Madrid"
    # ----------------------------------------------------------------------------------------------------

    def _configured(v):
        return bool((v or "").strip()) and not v.strip().startswith("<")

    def _csv_list(v):
        return [x.strip() for x in (v or "").split(",") if x.strip()] if _configured(v) else []

    ARM = "https://management.azure.com"
    BUDGET_SECONDS = 105
    operation = (operation or "report").strip().lower()
    if operation not in ("report", "summary", "upcoming"):
        operation = "report"
    period_map = {"last_30d": ("Last 30 days", 30), "last_14d": ("Last 14 days", 14), "last_7d": ("Last 7 days", 7)}
    period_key = (period or "last_30d").strip().lower()
    if period_key not in period_map:
        period_key = "last_30d"
    period_label, period_days = period_map[period_key]
    mode_req = (data_source or "auto").strip().lower()
    if mode_req not in ("auto", "live", "demo"):
        mode_req = "auto"
    now_utc = datetime.now(timezone.utc).replace(microsecond=0)
    stamp = now_utc.strftime("%Y%m%dT%H%M%SZ")
    start_utc = now_utc - timedelta(days=period_days)
    cwd = Path.cwd()
    m_tid = re.fullmatch(r"/(?:root/sreagent|usr)/terminalRoot/tmp/ThreadFiles/([0-9a-fA-F-]{36})", cwd.as_posix())

    def file_url(name):
        return f"/api/files/tmp/ThreadFiles/{m_tid.group(1)}/{quote(name, safe='')}" if m_tid else str(cwd / name)

    # ---- Local time (zoneinfo when available; otherwise the EU CET/CEST rule) --------------------------
    try:
        from zoneinfo import ZoneInfo
        _TZ = ZoneInfo(LOCAL_TIMEZONE)
        _TZ.utcoffset(datetime(2026, 1, 1))

        def to_local(dt):
            return dt.astimezone(_TZ)

        def from_local(naive):
            return naive.replace(tzinfo=_TZ).astimezone(timezone.utc)
    except Exception:
        def _eu_off(dt_utc):
            y = dt_utc.year

            def last_sun(m):
                d = datetime(y, m, 31, 1, tzinfo=timezone.utc)
                return d - timedelta(days=(d.weekday() + 1) % 7)
            return 2 if last_sun(3) <= dt_utc < last_sun(10) else 1

        def to_local(dt):
            dt = dt.astimezone(timezone.utc)
            return (dt + timedelta(hours=_eu_off(dt))).replace(tzinfo=None)

        def from_local(naive):
            guess = naive.replace(tzinfo=timezone.utc)
            return guess - timedelta(hours=_eu_off(guess))

    def parse_dt(v):
        if v in (None, ""):
            return None
        if isinstance(v, (int, float)):
            return datetime.fromtimestamp(v / (1000 if v > 1e11 else 1), tz=timezone.utc)
        s = str(v).strip()
        if s.isdigit():
            return parse_dt(int(s))
        s = s.replace("Z", "+00:00")
        m = re.match(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(\.\d+)?(.*)$", s)
        if m:
            s = m.group(1) + (m.group(2) or "")[:7] + m.group(3)
        try:
            d = datetime.fromisoformat(s)
        except ValueError:
            return None
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)

    DIAS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

    def fmt_local(dt, with_day=True):
        if not dt:
            return "—"
        lo = to_local(dt)
        return (DIAS[lo.weekday()] + " " if with_day else "") + lo.strftime("%d\u00a0%b %H:%M")

    # ---- SQL MI maintenance windows (Microsoft Learn: maintenance-window) ------------------------------
    WINDOWS = {
        "Default": "Default · 17:00–08:00 every day",
        "Weekday": "Weekday · Mon–Thu 22:00–06:00",
        "Weekend": "Weekend · Fri–Sun 22:00–06:00",
        "Custom": "Non-standard configuration",
    }
    WINDOW_SUFFIX = {"Weekday": "MI_1", "Weekend": "MI_2"}

    def window_of(cfg_id):
        c = (cfg_id or "").strip().lower()
        if not c or c.endswith("sql_default"):
            return "Default"
        if c.endswith("_mi_1"):
            return "Weekday"
        if c.endswith("_mi_2"):
            return "Weekend"
        return "Custom"

    def in_window(win, lo):
        wd, h = lo.weekday(), lo.hour
        if win in ("Default", "Custom"):
            return h >= 17 or h < 8
        if win == "Weekday":
            return (h >= 22 and wd in (0, 1, 2, 3)) or (h < 6 and wd in (1, 2, 3, 4))
        if win == "Weekend":
            return (h >= 22 and wd in (4, 5, 6)) or (h < 6 and wd in (5, 6, 0))
        return False

    WINDOW_CELLS = {w: {(d, h) for d in range(7) for h in range(24)
                        if in_window(w, datetime(2026, 1, 5 + d, h, 30))} for w in ("Default", "Weekday", "Weekend")}

    REGION_PASCAL = {
        "westeurope": "WestEurope", "northeurope": "NorthEurope", "spaincentral": "SpainCentral",
        "francecentral": "FranceCentral", "germanywestcentral": "GermanyWestCentral", "swedencentral": "SwedenCentral",
        "italynorth": "ItalyNorth", "uksouth": "UKSouth", "ukwest": "UKWest", "switzerlandnorth": "SwitzerlandNorth",
        "polandcentral": "PolandCentral", "eastus": "EastUS", "eastus2": "EastUS2", "westus": "WestUS",
        "centralus": "CentralUS", "northcentralus": "NorthCentralUS", "southcentralus": "SouthCentralUS",
    }
    REGION_LABEL = {
        "westeurope": "West Europe", "northeurope": "North Europe", "spaincentral": "Spain Central",
        "francecentral": "France Central", "germanywestcentral": "Germany West Central", "swedencentral": "Sweden Central",
        "italynorth": "Italy North", "uksouth": "UK South", "ukwest": "UK West",
    }
    REGION_PAIRS = {
        "westeurope": "northeurope", "northeurope": "westeurope", "francecentral": "francesouth",
        "francesouth": "francecentral", "germanywestcentral": "germanynorth", "germanynorth": "germanywestcentral",
        "uksouth": "ukwest", "ukwest": "uksouth", "swedencentral": "swedensouth", "swedensouth": "swedencentral",
        "switzerlandnorth": "switzerlandwest", "switzerlandwest": "switzerlandnorth", "eastus": "westus",
        "westus": "eastus", "eastus2": "centralus", "centralus": "eastus2",
    }

    def region_label(loc):
        return REGION_LABEL.get((loc or "").lower(), loc or "—")

    def config_id(sub, loc, win):
        if win == "Default":
            return f"/subscriptions/{sub}/providers/Microsoft.Maintenance/publicMaintenanceConfigurations/SQL_Default"
        rp = REGION_PASCAL.get((loc or "").lower(), (loc or "region")[:1].upper() + (loc or "region")[1:])
        return (f"/subscriptions/{sub}/providers/Microsoft.Maintenance/publicMaintenanceConfigurations/"
                f"SQL_{rp}_{WINDOW_SUFFIX[win]}")

    def env_of(name, tags):
        for k, v in (tags or {}).items():
            if k.lower() in ("env", "entorno", "environment", "ambiente") and v:
                v = str(v).lower()
                return "prd" if v.startswith(("prd", "prod", "pro")) else "no-prd"
        n = (name or "").lower()
        if re.search(r"[-_](prd|prod|pro)([-_]|$)", n):
            return "prd"
        if re.search(r"[-_](pre|dev|test|tst|uat|qa|int|des)([-_]|$)", n):
            return "no-prd"
        return "prd"

    def batch_cells(tags):
        for k, v in (tags or {}).items():
            if k.lower() in ("batch-hours", "batch_hours", "etl-hours", "ventana-batch"):
                m = re.match(r"^\s*(\d{1,2})\s*-\s*(\d{1,2})\s*$", str(v))
                if m:
                    a, b = int(m.group(1)) % 24, int(m.group(2)) % 24
                    hours = [(a + i) % 24 for i in range(((b - a) % 24) or 24)]
                    return {(d, h) for d in range(7) for h in hours}, f"{a:02d}:00–{b:02d}:00"
        return set(), None

    TRANSIENT = {"233", "997", "10060", "10053", "10054", "4060", "4221", "1204", "1205", "1222", "10928", "10929",
                 "40501", "49918", "49919", "49920", "40143", "40197", "40540", "40613", "-2"}

    # ==== LIVE collectors (read-only) ===================================================================
    t0 = time.monotonic()
    sources = []

    def src(name, status, detail=""):
        sources.append({"source": name, "status": status, "detail": str(detail)[:300]})

    def left():
        return BUDGET_SECONDS - (time.monotonic() - t0)

    def collect_live():
        import requests
        from azure.identity import ManagedIdentityCredential
        cred = ManagedIdentityCredential(client_id=MANAGED_IDENTITY_CLIENT_ID)
        tokens = {}

        def tok(scope):
            if scope not in tokens or tokens[scope][1] - time.time() < 120:
                t = cred.get_token(scope)
                tokens[scope] = (t.token, t.expires_on)
            return tokens[scope][0]

        def req(method, url, body=None, scope=ARM + "/.default", tries=3):
            for i in range(tries):
                if left() < 4:
                    raise TimeoutError("time budget exhausted")
                r = requests.request(method, url, json=body, timeout=min(30, max(5, left() - 2)),
                                     headers={"Authorization": "Bearer " + tok(scope), "Content-Type": "application/json"})
                if r.status_code in (429, 500, 502, 503, 504) and i < tries - 1:
                    time.sleep(min(int(r.headers.get("Retry-After", "3") or 3), 10))
                    continue
                if r.status_code >= 400:
                    raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
                return r.json() if r.text else {}
            return {}

        subs = _csv_list(SUBSCRIPTION_IDS)

        def arg(query):
            rows, skip = [], None
            while True:
                body = {"query": query, "options": {"resultFormat": "objectArray", "$top": 1000}}
                if subs:
                    body["subscriptions"] = subs
                if skip:
                    body["options"]["$skipToken"] = skip
                j = req("POST", ARM + "/providers/Microsoft.ResourceGraph/resources?api-version=2022-10-01", body)
                rows += j.get("data") or []
                skip = j.get("$skipToken")
                if not skip or len(rows) > 20000:
                    return rows

        d = {"mode": "live", "instances": [], "events": [], "upcoming": [], "alerts": [],
             "dep_hourly": [], "dep_fail": [], "req_fail": [], "cpu": {}, "telemetry": False}

        # 1) SQL MI inventory
        try:
            rows = arg("resources | where type =~ 'microsoft.sql/managedinstances' | project id, name, location, "
                       "resourceGroup, subscriptionId, tags, skuName=tostring(sku.name), tier=tostring(sku.tier), "
                       "vCores=toint(properties.vCores), cfg=tostring(properties.maintenanceConfigurationId), "
                       "proxy=tostring(properties.proxyOverride), zr=tobool(properties.zoneRedundant), "
                       "pool=tostring(properties.instancePoolId), fqdn=tostring(properties.fullyQualifiedDomainName), "
                       "state=tostring(properties.state)")
            for r in rows:
                tier = (r.get("tier") or r.get("skuName") or "")
                tier = "BusinessCritical" if "business" in tier.lower() or (r.get("skuName") or "").upper().startswith("BC") else "GeneralPurpose"
                px = (r.get("proxy") or "").strip()
                d["instances"].append({
                    "id": r["id"], "name": r["name"], "sub": r.get("subscriptionId"), "rg": r.get("resourceGroup"),
                    "location": (r.get("location") or "").lower(), "tier": tier, "vcores": r.get("vCores"),
                    "cfg_id": r.get("cfg") or "", "proxy": "Redirect" if px.lower() in ("redirect", "default") else ("Proxy" if px.lower() == "proxy" else "—"),
                    "zone_redundant": bool(r.get("zr")), "pool": bool(r.get("pool")), "fqdn": r.get("fqdn") or "",
                    "tags": r.get("tags") or {}, "fog": None, "fog_role": None, "fog_partner": None})
            src("Resource Graph · SQL MI inventory", "ok", f"{len(rows)} instance{'s' if len(rows) != 1 else ''}")
        except Exception as e:
            src("Resource Graph · SQL MI inventory", "error", e)
        by_id = {i["id"].lower(): i for i in d["instances"]}

        # 2) Failover groups (REST per resource group and region)
        fog_err = 0
        for key in sorted({(i["sub"], i["rg"], i["location"]) for i in d["instances"]}):
            try:
                j = req("GET", f"{ARM}/subscriptions/{key[0]}/resourceGroups/{key[1]}/providers/Microsoft.Sql/locations/"
                               f"{key[2]}/instanceFailoverGroups?api-version=2023-08-01")
                for fg in j.get("value") or []:
                    p = fg.get("properties") or {}
                    for pair in p.get("managedInstancePairs") or []:
                        a = by_id.get((pair.get("primaryManagedInstanceId") or "").lower())
                        b = by_id.get((pair.get("partnerManagedInstanceId") or "").lower())
                        for x, role, other in ((a, "Primary", b), (b, "Secondary", a)):
                            if x:
                                x["fog"], x["fog_role"] = fg.get("name"), role
                                x["fog_partner"] = other["name"] if other else None
            except Exception:
                fog_err += 1
        src("ARM · failover groups", "ok" if not fog_err else "partial", f"{fog_err} error{'s' if fog_err != 1 else ''}" if fog_err else "")

        # 3) Upcoming maintenance (Service Health) and per-resource updates (Maintenance)
        try:
            rows = arg("servicehealthresources | where type =~ 'Microsoft.ResourceHealth/events' | extend p=properties "
                       "| where tostring(p.EventType) == 'PlannedMaintenance' | mv-expand imp=p.Impact "
                       "| where tostring(imp.ImpactedService) =~ 'SQL Managed Instance' | project trackingId=name, "
                       "title=tostring(p.Title), status=tostring(p.Status), start=tostring(p.ImpactStartTime), "
                       "end=tostring(p.ImpactMitigationTime), regions=imp.ImpactedRegions")
            seen = set()
            for r in rows:
                st, en = parse_dt(r.get("start")), parse_dt(r.get("end"))
                if not st or (en or st) < now_utc - timedelta(hours=12) or r.get("trackingId") in seen:
                    continue
                seen.add(r.get("trackingId"))
                regs = [re.sub(r"\s+", "", (x.get("ImpactedRegion") or "")).lower() for x in (r.get("regions") or []) if isinstance(x, dict)]
                d["upcoming"].append({"tracking_id": r.get("trackingId"), "title": r.get("title") or "Planned maintenance",
                                      "start": st.isoformat(), "end": (en or st + timedelta(hours=8)).isoformat(),
                                      "regions": regs, "impacted": [i["name"] for i in d["instances"] if i["location"] in regs],
                                      "source": "Service Health"})
            src("Service Health · planned maintenance", "ok", f"{len(d['upcoming'])} event{'s' if len(d['upcoming']) != 1 else ''}")
        except Exception as e:
            src("Service Health · planned maintenance", "error", e)
        try:
            rows = arg("maintenanceresources | where type =~ 'microsoft.maintenance/updates' "
                       "| where tolower(id) contains '/microsoft.sql/managedinstances/' or tolower(tostring(properties.resourceId)) "
                       "contains '/microsoft.sql/managedinstances/' | project id, rid=tostring(properties.resourceId), "
                       "status=tostring(properties.status), start=tostring(properties.startTimeUtc), "
                       "end=tostring(properties.endTimeUtc), impact=tostring(properties.impactType)")
            n = 0
            for r in rows:
                rid = (r.get("rid") or r.get("id") or "").lower().split("/providers/microsoft.maintenance")[0]
                mi = by_id.get(rid)
                st = parse_dt(r.get("start"))
                if not mi or (r.get("status") or "").lower() not in ("pending", "inprogress", "in progress", "scheduled") or not st:
                    continue
                en = parse_dt(r.get("end")) or st + timedelta(hours=8)
                hit = next((u for u in d["upcoming"] if abs((parse_dt(u["start"]) - st).total_seconds()) < 86400), None)
                if hit:
                    if mi["name"] not in hit["impacted"]:
                        hit["impacted"].append(mi["name"])
                else:
                    d["upcoming"].append({"tracking_id": "—", "title": f"Update {r.get('impact') or ''}".strip(),
                                          "start": st.isoformat(), "end": en.isoformat(), "regions": [mi["location"]],
                                          "impacted": [mi["name"]], "source": "Maintenance"})
                n += 1
            src("Resource Graph · maintenanceresources", "ok", f"{n} pending update{'s' if n != 1 else ''}")
        except Exception as e:
            src("Resource Graph · maintenanceresources", "partial", e)

        # 4) Service Health alerts
        try:
            rows = arg("resources | where type =~ 'microsoft.insights/activitylogalerts' | project name, "
                       "enabled=tobool(properties.enabled), cond=properties.condition")

            def flat(c, out):
                if isinstance(c, dict):
                    if c.get("field"):
                        vals = c.get("containsAny") or ([c.get("equals")] if c.get("equals") is not None else [])
                        out.append((c["field"].lower(), [str(v).lower() for v in vals]))
                    for k in ("allOf", "anyOf"):
                        for x in c.get(k) or []:
                            flat(x, out)
                elif isinstance(c, list):
                    for x in c:
                        flat(x, out)
                return out
            for r in rows:
                f = flat(r.get("cond") or {}, [])
                if not any(k == "category" and "servicehealth" in v for k, v in f):
                    continue
                inc = [v for k, v in f if k.endswith("incidenttype")]
                svc = [v for k, v in f if "impactedservices" in k]
                d["alerts"].append({"name": r.get("name"), "enabled": r.get("enabled") is not False,
                                    "covers_maintenance": not inc or any("maintenance" in x for v in inc for x in v),
                                    "covers_sqlmi": not svc or any("managed instance" in x for v in svc for x in v),
                                    "types": sorted({x for v in inc for x in v}) or ["all"]})
            src("Resource Graph · Service Health alerts", "ok", f"{len(d['alerts'])} alert{'s' if len(d['alerts']) != 1 else ''}")
        except Exception as e:
            src("Resource Graph · Service Health alerts", "error", e)

        # 5) Resource Health (reconfigurations) + CPU per instance, in parallel
        def rh(mi):
            out = []
            j = req("GET", f"{ARM}{mi['id']}/providers/Microsoft.ResourceHealth/availabilityStatuses?api-version=2022-10-01&$top=200")
            st = []
            for x in j.get("value") or []:
                p = x.get("properties") or {}
                t = parse_dt(p.get("occuredTime") or p.get("occurredTime") or p.get("reportedTime"))
                if t:
                    st.append((t, (p.get("availabilityState") or "").lower(), p.get("reasonType") or "", p.get("summary") or ""))
            st.sort()
            for k, (t, state, reason, summ) in enumerate(st):
                if state in ("unavailable", "degraded") and t >= start_utc:
                    nxt = next((s[0] for s in st[k + 1:] if s[1] == "available"), None)
                    dur = max(1, min(3600, int((nxt - t).total_seconds()))) if nxt else 30
                    rs = reason.lower()
                    out.append({"mi": mi["name"], "start": t.isoformat(), "duration_s": dur, "source": "Resource Health",
                                "reason": "Planned" if "planned" in rs and "un" not in rs else ("UserInitiated" if "user" in rs else "Unplanned")})
            return out

        def cpu(mi):
            j = req("GET", f"{ARM}{mi['id']}/providers/Microsoft.Insights/metrics?api-version=2023-10-01&metricnames=avg_cpu_percent"
                           f"&interval=PT1H&aggregation=Average&timespan={start_utc:%Y-%m-%dT%H:%M:%SZ}/{now_utc:%Y-%m-%dT%H:%M:%SZ}")
            pts = []
            for ts in ((j.get("value") or [{}])[0].get("timeseries") or []):
                for p in ts.get("data") or []:
                    if p.get("average") is not None:
                        pts.append((p["timeStamp"], p["average"]))
            return pts
        rh_err = cpu_err = 0
        with ThreadPoolExecutor(max_workers=8) as ex:
            fut_rh = {i["name"]: ex.submit(rh, i) for i in d["instances"]}
            fut_cpu = {i["name"]: ex.submit(cpu, i) for i in d["instances"]}
            for n, f in fut_rh.items():
                try:
                    d["events"] += f.result()
                except Exception:
                    rh_err += 1
            for n, f in fut_cpu.items():
                try:
                    d["cpu"][n] = f.result()
                except Exception:
                    cpu_err += 1
        src("Resource Health · history", "ok" if not rh_err else "partial", f"{len(d['events'])} event{'s' if len(d['events']) != 1 else ''}; {rh_err} error{'s' if rh_err != 1 else ''}")
        src("Azure Monitor · avg_cpu_percent", "ok" if not cpu_err else "partial", f"{cpu_err} error{'s' if cpu_err != 1 else ''}" if cpu_err else "")

        # 6) Manual failovers (Activity Log)
        try:
            names = {i["id"].lower(): i["name"] for i in d["instances"]}
            for sub in sorted({i["sub"] for i in d["instances"]}):
                flt = quote(f"eventTimestamp ge '{start_utc:%Y-%m-%dT%H:%M:%SZ}' and resourceProvider eq 'Microsoft.Sql'")
                j = req("GET", f"{ARM}/subscriptions/{sub}/providers/Microsoft.Insights/eventtypes/management/values"
                               f"?api-version=2015-04-01&$filter={flt}&$select=operationName,resourceId,eventTimestamp,status")
                for e in j.get("value") or []:
                    op = ((e.get("operationName") or {}).get("value") or "").lower()
                    rid = (e.get("resourceId") or "").lower()
                    st = ((e.get("status") or {}).get("value") or "").lower()
                    t = parse_dt(e.get("eventTimestamp"))
                    if op.endswith("managedinstances/failover/action") and st == "succeeded" and rid in names and t:
                        dup = any(x["mi"] == names[rid] and abs((parse_dt(x["start"]) - t).total_seconds()) < 900 for x in d["events"])
                        if dup:
                            for x in d["events"]:
                                if x["mi"] == names[rid] and abs((parse_dt(x["start"]) - t).total_seconds()) < 900:
                                    x["reason"] = "UserInitiated"
                        else:
                            d["events"].append({"mi": names[rid], "start": t.isoformat(), "duration_s": 10,
                                                "reason": "UserInitiated", "source": "Activity Log"})
            src("Activity Log · manual failovers", "ok")
        except Exception as e:
            src("Activity Log · manual failovers", "partial", e)

        # 7) Application Insights (workspace-based) via Log Analytics
        wss = _csv_list(LOG_ANALYTICS_WORKSPACE_IDS)
        if not wss:
            src("Application Insights · SQL dependencies", "skipped", "LOG_ANALYTICS_WORKSPACE_IDS not configured")
        days = period_days

        def la(ws, q):
            j = req("POST", f"https://api.loganalytics.io/v1/workspaces/{ws}/query", {"query": q, "timespan": f"P{days}D"},
                    scope="https://api.loganalytics.io/.default")
            t = (j.get("tables") or [{}])[0]
            cols = [c["name"] for c in t.get("columns") or []]
            return [dict(zip(cols, r)) for r in t.get("rows") or []]
        for ws in wss:
            try:
                d["dep_hourly"] += la(ws, "AppDependencies | where Type has 'SQL' | summarize n=count() by app=AppRoleName, "
                                          "target=Target, ts=bin(TimeGenerated, 1h)")
                d["dep_fail"] += la(ws, "AppDependencies | where Type has 'SQL' and Success == false | summarize n=count() by "
                                        "app=AppRoleName, target=Target, ts=bin(TimeGenerated, 1m), code=tostring(ResultCode)")
                d["req_fail"] += la(ws, "AppRequests | where Success == false and toint(ResultCode) >= 500 | summarize n=count() "
                                        "by app=AppRoleName, ts=bin(TimeGenerated, 1m)")
                d["telemetry"] = True
                src(f"Application Insights · workspace …{ws[-6:]}", "ok")
            except Exception as e:
                src(f"Application Insights · workspace …{ws[-6:]}", "error", e)
        return d

    # ==== DEMO dataset (simulated, deterministic; no real customer data) ==================================
    def collect_demo():
        rnd = random.Random(20261022)
        SUB = "00000000-0000-0000-0000-000000000000"
        DNS = "a1b2c3d4e5f6.database.windows.net"

        def mi(name, loc, tier, vc, win, proxy, tags=None, fog=None, role=None, partner=None, rg="rg-data-prd"):
            return {"id": f"/subscriptions/{SUB}/resourceGroups/{rg}/providers/Microsoft.Sql/managedInstances/{name}",
                    "name": name, "sub": SUB, "rg": rg, "location": loc, "tier": tier, "vcores": vc,
                    "cfg_id": "" if win == "Default" else config_id(SUB, loc, win), "proxy": proxy, "zone_redundant": tier == "BusinessCritical",
                    "pool": False, "fqdn": f"{name}.{DNS}", "tags": tags or {"environment": "prd"},
                    "fog": fog, "fog_role": role, "fog_partner": partner}
        inst = [
            mi("sqlmi-core-prd", "spaincentral", "BusinessCritical", 16, "Default", "Proxy",
               {"environment": "prd", "app": "core"}, "fog-core", "Primary", "sqlmi-core-dr"),
            mi("sqlmi-core-dr", "westeurope", "BusinessCritical", 16, "Default", "Proxy",
               {"environment": "prd", "app": "core", "role": "dr"}, "fog-core", "Secondary", "sqlmi-core-prd", "rg-data-dr"),
            mi("sqlmi-orders-prd", "spaincentral", "GeneralPurpose", 8, "Weekday", "Redirect", {"environment": "prd", "app": "orders"}),
            mi("sqlmi-bookings-prd", "spaincentral", "GeneralPurpose", 8, "Default", "Redirect", {"environment": "prd", "app": "bookings"}),
            mi("sqlmi-dwh-prd", "spaincentral", "GeneralPurpose", 16, "Weekend", "Redirect",
               {"environment": "prd", "app": "dwh", "batch-hours": "23-04"}),
            mi("sqlmi-pre", "spaincentral", "GeneralPurpose", 4, "Default", "Redirect", {"environment": "pre"}, rg="rg-data-pre"),
        ]
        fog_host = f"fog-core.{DNS}"
        # app: (base rpm, [(target host, db)], retry profile, schedule)
        APPS = {
            "customer-portal-web": (420, [(fog_host, "CoreDB")], "none", "web"),
            "pricing-api": (260, [(f"sqlmi-core-prd.{DNS}", "PricingDB")], "none", "web"),
            "crm-contactcenter": (180, [(fog_host, "CoreDB"), (f"sqlmi-bookings-prd.{DNS}", "BookingsDB")], "none", "office"),
            "orders-backoffice": (120, [(f"sqlmi-orders-prd.{DNS}", "OrdersDB")], "resilient", "office"),
            "mobile-app-api": (380, [(fog_host, "CoreDB")], "resilient", "web"),
            "payments-api": (90, [(fog_host, "PaymentsDB")], "resilient", "web"),
            "bookings-api": (140, [(f"sqlmi-bookings-prd.{DNS}", "BookingsDB")], "partial", "web"),
            "nightly-etl": (25, [(f"sqlmi-dwh-prd.{DNS}", "DWH")], "resilient", "batch"),
        }
        WEB = [0.08, 0.05, 0.04, 0.04, 0.05, 0.08, 0.15, 0.35, 0.7, 1.0, 1.0, 1.0, 1.0, 1.0, 0.95, 0.75, 0.75,
               0.9, 0.95, 0.95, 0.9, 0.8, 0.45, 0.2]

        def rpm(app, lo):
            base, _, _, kind = APPS[app]
            wd, h = lo.weekday(), lo.hour
            if kind == "office":
                f = (1.0 if 9 <= h < 14 else 0.7 if 8 <= h < 22 else 0.0) * (0.35 if wd >= 5 else 1.0)
            elif kind == "batch":
                f = 8.0 if (h >= 23 or h < 4) else 0.3
            else:
                f = WEB[h] * (0.55 if wd >= 5 else 1.0)
            return base * f

        def at_local(days_back, wd, hh, mm, ss=0):
            today = to_local(now_utc).replace(tzinfo=None)
            day = (today - timedelta(days=days_back)).date()
            day = day - timedelta(days=(day.weekday() - wd) % 7)
            return from_local(datetime(day.year, day.month, day.day, hh, mm, ss))
        EVENTS = [("sqlmi-core-prd", 22, 1, 18, 42, 9, "Planned"), ("sqlmi-core-prd", 22, 1, 18, 44, 6, "Planned"),
                  ("sqlmi-dwh-prd", 20, 6, 23, 15, 14, "Planned"), ("sqlmi-core-dr", 18, 3, 3, 10, 7, "Planned"),
                  ("sqlmi-orders-prd", 15, 2, 23, 5, 11, "Planned"), ("sqlmi-bookings-prd", 11, 0, 19, 20, 8, "Planned"),
                  ("sqlmi-bookings-prd", 11, 0, 19, 23, 5, "Planned"), ("sqlmi-core-prd", 8, 4, 11, 37, 21, "Unplanned"),
                  ("sqlmi-pre", 6, 1, 10, 2, 5, "UserInitiated"), ("sqlmi-bookings-prd", 3, 3, 20, 51, 28, "Unplanned")]
        events = []
        for name, db, wd, hh, mm, dur, reason in EVENTS:
            if db > period_days:
                continue
            t = at_local(db, wd, hh, mm, rnd.randint(0, 50))
            events.append({"mi": name, "start": t.isoformat(), "duration_s": dur, "reason": reason,
                           "source": "Activity Log" if reason == "UserInitiated" else "Resource Health"})

        def host_mi(h):
            lab = h.split(".")[0]
            return "sqlmi-core-prd" if lab == "fog-core" else lab
        dep_hourly, dep_fail, req_fail = [], [], []
        h0 = start_utc.replace(minute=0, second=0)
        hours = int((now_utc - h0).total_seconds() // 3600)
        for app, (base, targets, retry, kind) in APPS.items():
            for k in range(hours):
                t = h0 + timedelta(hours=k)
                v = rpm(app, to_local(t)) * 3 * 60
                for host, dbn in targets:
                    share = 1.0 / len(targets)
                    dep_hourly.append({"app": app, "target": f"{host} | {dbn}", "ts": t.isoformat(),
                                       "n": int(v * share * rnd.uniform(0.9, 1.1))})
        CODES = [("40613", 0.5), ("40197", 0.2), ("4060", 0.15), ("233", 0.15)]
        for ev in events:
            t = parse_dt(ev["start"])
            for app, (base, targets, retry, kind) in APPS.items():
                for host, dbn in targets:
                    if host_mi(host) != ev["mi"]:
                        continue
                    n = rpm(app, to_local(t)) * 3 * (ev["duration_s"] + 10) / 60 / len(targets) * rnd.uniform(0.85, 1.15)
                    if n < 1:
                        continue
                    minute = t.replace(second=0)
                    for code, p in CODES:
                        c = int(round(n * p))
                        if c:
                            dep_fail.append({"app": app, "target": f"{host} | {dbn}", "ts": minute.isoformat(), "code": code, "n": c})
                    ratio = {"none": 0.8, "partial": 0.25}.get(retry, 0.0) * rnd.uniform(0.9, 1.1)
                    if int(n * ratio):
                        req_fail.append({"app": app, "ts": minute.isoformat(), "n": int(n * ratio)})
        for _ in range(60):
            app = rnd.choice(list(APPS))
            host, dbn = APPS[app][1][0]
            t = (start_utc + timedelta(minutes=rnd.randint(0, period_days * 1440 - 1))).replace(second=0)
            dep_fail.append({"app": app, "target": f"{host} | {dbn}", "ts": t.isoformat(), "code": rnd.choice(["1205", "1222", "-2"]), "n": rnd.randint(1, 3)})
            if rnd.random() < 0.5:
                req_fail.append({"app": app, "ts": t.isoformat(), "n": 1})
        up_start = at_local(-3, (to_local(now_utc).weekday() + 3) % 7, 17, 0)
        upcoming = [{"tracking_id": "QK4X-9TZ", "title": "Planned maintenance for Azure SQL Managed Instance · Spain Central",
                     "start": up_start.isoformat(), "end": (up_start + timedelta(hours=15)).isoformat(), "regions": ["spaincentral"],
                     "impacted": ["sqlmi-core-prd", "sqlmi-bookings-prd", "sqlmi-pre"], "source": "Service Health"}]
        alerts = [{"name": "alr-servicehealth-incidents", "enabled": True, "covers_maintenance": False, "covers_sqlmi": True,
                   "types": ["incident"]}]
        for name, st, det in [("Resource Graph · SQL MI inventory", "ok", "6 instances"), ("ARM · failover groups", "ok", "1 group"),
                              ("Service Health · planned maintenance", "ok", "1 event"),
                              ("Resource Graph · maintenanceresources", "ok", "3 pending updates"),
                              ("Resource Graph · Service Health alerts", "ok", "1 alert"),
                              ("Resource Health · history", "ok", f"{len(events)} events"),
                              ("Activity Log · manual failovers", "ok", "1 drill"),
                              ("Application Insights · SQL dependencies", "ok", f"{len(APPS)} applications")]:
            src(name + " (simulated)", st, det)
        return {"mode": "demo", "instances": inst, "events": events, "upcoming": upcoming, "alerts": alerts,
                "dep_hourly": dep_hourly, "dep_fail": dep_fail, "req_fail": req_fail, "cpu": {}, "telemetry": True}

    # ==== Get the data =================================================================================
    replay = os.environ.get("SQLMI_REPLAY", "").strip()
    if replay and Path(replay).is_file():
        raw = json.loads(Path(replay).read_text(encoding="utf-8"))["raw"]
        src("Replay JSON", "ok", Path(replay).name)
    elif mode_req == "demo" or (mode_req == "auto" and not _configured(MANAGED_IDENTITY_CLIENT_ID)):
        raw = collect_demo()
    else:
        if not _configured(MANAGED_IDENTITY_CLIENT_ID):
            return {"status": "error", "mode": "live", "message": "Set MANAGED_IDENTITY_CLIENT_ID in the tool code "
                    "(README, step 4) or run with data_source='demo'."}
        try:
            raw = collect_live()
        except Exception as e:
            return {"status": "error", "mode": "live", "message": f"Error collecting data: {e}", "sources": sources}
        if not raw["instances"]:
            return {"status": "no_data", "mode": "live", "sources": sources,
                    "message": "The identity cannot see any SQL Managed Instance. Check the Reader role (README, step 3) "
                               "or run with data_source='demo' to see the sample report."}
    MODE = raw["mode"]
    insts = raw["instances"]
    by_name = {i["name"]: i for i in insts}
    for i in insts:
        i["window"] = window_of(i["cfg_id"])
        i["env"] = env_of(i["name"], i["tags"])
        i["batch"], i["batch_label"] = batch_cells(i["tags"])
    fog_primary = {}
    for i in insts:
        if i.get("fog") and i.get("fog_role") == "Primary":
            fog_primary[i["fog"].lower()] = i["name"]

    def mi_of_target(t):
        host = (t or "").split("|")[0].strip().split(",")[0].lower()
        lab = host.split(".")[0]
        return lab if lab in by_name else fog_primary.get(lab)

    # ---- 7x24 load map per instance (average SQL calls per local hour) --------------------------------
    occ = defaultdict(int)
    h = start_utc.replace(minute=0, second=0)
    while h < now_utc:
        lo = to_local(h)
        occ[(lo.weekday(), lo.hour)] += 1
        h += timedelta(hours=1)
    heat = defaultdict(lambda: [[0.0] * 24 for _ in range(7)])
    app_mi = defaultdict(int)
    for r in raw["dep_hourly"]:
        mi = mi_of_target(r.get("target"))
        t = parse_dt(r.get("ts"))
        if not mi or not t:
            continue
        lo = to_local(t)
        heat[mi][lo.weekday()][lo.hour] += float(r.get("n") or 0)
        app_mi[(r.get("app") or "?", mi)] += int(r.get("n") or 0)
    heat_src = {}
    for mi in list(heat):
        for d_ in range(7):
            for hh in range(24):
                heat[mi][d_][hh] /= max(1, occ[(d_, hh)])
        heat_src[mi] = "Application Insights"
    for name, pts in (raw.get("cpu") or {}).items():
        if name in heat_src or not pts:
            continue
        acc, cnt = [[0.0] * 24 for _ in range(7)], [[0] * 24 for _ in range(7)]
        for ts, v in pts:
            t = parse_dt(ts)
            if t:
                lo = to_local(t)
                acc[lo.weekday()][lo.hour] += v
                cnt[lo.weekday()][lo.hour] += 1
        heat[name] = [[acc[a][b] / cnt[a][b] if cnt[a][b] else 0 for b in range(24)] for a in range(7)]
        heat_src[name] = "CPU (avg_cpu_percent)"
    for i in insts:
        if i["name"] not in heat_src and i.get("fog_partner") in heat_src:
            heat[i["name"]] = heat[i["fog_partner"]]
            heat_src[i["name"]] = f"load of the primary ({i['fog_partner']})"

    # ---- Events: window, local time and events detected from telemetry -------------------------------
    fails_by_mi = defaultdict(list)
    for r in raw["dep_fail"]:
        mi, t = mi_of_target(r.get("target")), parse_dt(r.get("ts"))
        if mi and t:
            fails_by_mi[mi].append((t, r.get("app") or "?", str(r.get("code") or ""), int(r.get("n") or 0)))
    req_by_app = defaultdict(list)
    for r in raw["req_fail"]:
        t = parse_dt(r.get("ts"))
        if t:
            req_by_app[r.get("app") or "?"].append((t, int(r.get("n") or 0)))
    events = [dict(e) for e in raw["events"] if e["mi"] in by_name]
    if MODE == "live":
        for mi, rows in fails_by_mi.items():
            per_min = defaultdict(int)
            for t, app, code, n in rows:
                if code in TRANSIENT:
                    per_min[t.replace(second=0)] += n
            for t, n in sorted(per_min.items()):
                if n >= 25 and not any(e["mi"] == mi and abs((parse_dt(e["start"]) - t).total_seconds()) < 900 for e in events):
                    events.append({"mi": mi, "start": t.isoformat(), "duration_s": 60, "reason": "Detected", "source": "Telemetry"})
    REASON = {"Planned": "Planned", "Unplanned": "Unplanned", "UserInitiated": "Manual (drill)", "Detected": "Detected (telemetry)"}
    for e in events:
        t = parse_dt(e["start"])
        e["_t"], e["local"] = t, fmt_local(t)
        e["in_window"] = in_window(by_name[e["mi"]]["window"], to_local(t))
        e["reason_es"] = REASON.get(e["reason"], e["reason"])
    events.sort(key=lambda x: x["_t"])

    # ---- Correlation: event -> failed dependencies -> user errors --------------------------------------
    impact = []
    app_stats = defaultdict(lambda: {"dep": 0, "user": 0, "events": 0, "codes": defaultdict(int)})

    def ev_span(e):
        return e["_t"] - timedelta(minutes=2), e["_t"] + timedelta(seconds=e["duration_s"]) + timedelta(minutes=5)

    def nearest(cands, t):
        # Each failure goes to a single event (the nearest one) so back-to-back reconfigurations are not counted twice.
        hits = [k for k in cands if ev_span(events[k])[0] <= t <= ev_span(events[k])[1]]
        return min(hits, key=lambda k: abs((t - events[k]["_t"]).total_seconds())) if hits else None
    ev_by_mi = defaultdict(list)
    for k, e in enumerate(events):
        ev_by_mi[e["mi"]].append(k)
        e["dep_failures"], e["user_errors"], e["apps"], e["_per_app"] = 0, 0, [], defaultdict(int)
    for mi, rows in fails_by_mi.items():
        for t, app, code, n in rows:
            k = nearest(ev_by_mi.get(mi, []), t) if code in TRANSIENT else None
            if k is not None:
                events[k]["_per_app"][app] += n
                app_stats[app]["codes"][code] += n
    app_events = defaultdict(list)
    for k, e in enumerate(events):
        for app in e["_per_app"]:
            app_events[app].append(k)
    user_by = defaultdict(int)
    for app, rows in req_by_app.items():
        for t, n in rows:
            k = nearest(app_events.get(app, []), t)
            if k is not None:
                user_by[(k, app)] += n
    for k, e in enumerate(events):
        for app, n in sorted(e["_per_app"].items(), key=lambda x: -x[1]):
            u = user_by[(k, app)]
            app_stats[app]["dep"] += n
            app_stats[app]["user"] += u
            app_stats[app]["events"] += 1
            e["dep_failures"] += n
            e["user_errors"] += u
            e["apps"].append(app)
            impact.append({"event_local": e["local"], "event_utc": e["start"], "managed_instance": e["mi"], "reason": e["reason_es"],
                           "duration_s": e["duration_s"], "app": app, "sql_dependency_failures": n, "user_errors": u})
        del e["_per_app"]

    def verdict(dep, user):
        if not raw.get("telemetry"):
            return "No telemetry"
        if dep == 0:
            return "No impact observed"
        r = user / dep
        return "No retries" if r >= 0.5 else ("Partial" if r >= 0.05 else "Resilient")
    apps = []
    for (app, mi), n in app_mi.items():
        if not any(x["app"] == app for x in apps):
            s = app_stats[app]
            apps.append({"app": app, "mis": sorted({m for (a_, m) in app_mi if a_ == app}),
                         "sql_calls": sum(v for (a_, m), v in app_mi.items() if a_ == app), "events": s["events"],
                         "dep_failures": s["dep"], "user_errors": s["user"],
                         "ratio": round(s["user"] / s["dep"], 2) if s["dep"] else None, "verdict": verdict(s["dep"], s["user"]),
                         "codes": ", ".join(f"{c}×{v}" for c, v in sorted(s["codes"].items(), key=lambda x: -x[1])[:4])})
    ORDER = {"No retries": 0, "Partial": 1, "Resilient": 2, "No impact observed": 3, "No telemetry": 4}
    apps.sort(key=lambda x: (ORDER.get(x["verdict"], 9), -x["user_errors"]))
    risky = {a["app"] for a in apps if a["verdict"] in ("No retries", "Partial")}
    apps_by_mi = defaultdict(list)
    for a in apps:
        for m in a["mis"]:
            apps_by_mi[m].append(a)

    # ---- Recommended window per instance ----------------------------------------------------------------
    def win_score(mi, w):
        hm = heat.get(mi)
        if not hm:
            return None
        peak = max(max(r) for r in hm) or 1
        cells = WINDOW_CELLS[w]
        base = sum(hm[d_][hh] for d_, hh in cells) / len(cells) / peak
        pen = 0.5 * len(cells & by_name[mi]["batch"]) / len(cells) if by_name[mi]["batch"] else 0
        return round(base + pen, 3)
    for i in insts:
        i["scores"] = {w: win_score(i["name"], w) for w in ("Default", "Weekday", "Weekend")}
        i["recommended"] = None
        cand = {w: s for w, s in i["scores"].items() if w != "Default" and s is not None}
        if cand and not i["pool"]:
            best = min(cand, key=cand.get)
            # Only recommend a change if it improves the score by more than 10%: changing the window changes the instance IP.
            cur = cand.get(i["window"])
            i["recommended"] = i["window"] if cur is not None and cand[best] >= cur * 0.9 else best
    for i in insts:
        if i.get("fog_role") == "Secondary" and i.get("fog_partner") in by_name:
            p = by_name[i["fog_partner"]]
            if p["recommended"]:
                i["recommended"] = "Weekend" if p["recommended"] == "Weekday" else "Weekday"
        i["paired"] = bool(i.get("fog_partner")) and REGION_PAIRS.get(i["location"]) == by_name.get(i["fog_partner"], {}).get("location")
        i["recommended_id"] = config_id(i["sub"], i["location"], i["recommended"]) if i["recommended"] else None
        actual = sum(e["user_errors"] for e in events if e["mi"] == i["name"] and e["reason"] == "Planned")
        est = 0.0
        hm = heat.get(i["name"])
        if hm and i["recommended"] and actual:
            cells = WINDOW_CELLS[i["recommended"]]
            mean_w = sum(hm[d_][hh] for d_, hh in cells) / len(cells)
            for e in events:
                if e["mi"] == i["name"] and e["reason"] == "Planned" and e["user_errors"]:
                    lo = to_local(e["_t"])
                    est += e["user_errors"] * min(1.0, mean_w / max(hm[lo.weekday()][lo.hour], 1e-9))
        i["user_errors_planned"], i["user_errors_est"] = actual, int(round(est))

    # ---- Prioritized findings --------------------------------------------------------------------------------
    findings = []

    def add(sev, title, scope, detail, action, cmd=""):
        findings.append({"severity": sev, "title": title, "scope": scope, "detail": detail, "action": action, "command": cmd})
    prd = [i for i in insts if i["env"] == "prd"]
    up7 = [u for u in raw["upcoming"] if parse_dt(u["start"]) <= now_utc + timedelta(days=7)]
    for u in up7:
        at = sorted({a["app"] for m in u["impacted"] for a in apps_by_mi.get(m, []) if a["app"] in risky})
        if at:
            add("High", f"Maintenance in {max(0, (parse_dt(u['start']) - now_utc).days)} day{'s' if max(0, (parse_dt(u['start']) - now_utc).days) != 1 else ''} "
                "with applications without retries",
                ", ".join(u["impacted"]), f"{u['title']} ({u['tracking_id']}) starts {fmt_local(parse_dt(u['start']))}. "
                f"Applications at risk: {', '.join(at)}.",
                "Warn the teams that own these applications, have the communication runbook ready and, if possible, "
                "apply the recommended window beforehand or validate the retries.")
    for a in apps:
        if a["verdict"] == "No retries":
            add("High", "Application without retry logic", a["app"], f"{a['user_errors']:,} user error{'s' if a['user_errors'] != 1 else ''} from "
                f"{a['dep_failures']:,} transient SQL failure{'s' if a['dep_failures'] != 1 else ''} in {a['events']} "
                f"reconfiguration{'s' if a['events'] != 1 else ''} (ratio {a['ratio']}).",
                "Implement retries with exponential backoff for transient errors (see retry-samples/). "
                "It is the only measure that removes the impact, including during unplanned events.")
        elif a["verdict"] == "Partial":
            add("Medium", "Application with partial retries", a["app"], f"{a['user_errors']:,} user error{'s' if a['user_errors'] != 1 else ''} out of "
                f"{a['dep_failures']:,} SQL failure{'s' if a['dep_failures'] != 1 else ''} (ratio {a['ratio']}): it retries on some paths "
                "but not on all of them.",
                "Check that the retry covers opening the connection and running the commands, and that the total timeout is ≥ 60 s.")
    if not any(x["enabled"] and x["covers_maintenance"] and x["covers_sqlmi"] for x in raw["alerts"]):
        partial = [x["name"] for x in raw["alerts"] if x["enabled"]]
        add("High", "No advance notice of SQL MI maintenance", "Subscription",
            "No Service Health alert covers 'Planned maintenance' for SQL Managed Instance"
            + (f" ({', '.join(partial)} exists, but it does not include Maintenance)." if partial else "."),
            "Create the alert (notice 24 h before, at the start and at the end) with create-sqlmi-maintenance-alert.ps1.",
            "./create-sqlmi-maintenance-alert.ps1 -SubscriptionId <SUB_ID> -ResourceGroup <RG> -ActionGroupId <ACTION_GROUP_ID>")
    for i in prd:
        if i["window"] == "Default" and not i["pool"] and i.get("fog_role") != "Secondary":
            hit = [a["app"] for a in apps_by_mi.get(i["name"], []) if a["app"] in risky]
            rec = i["recommended"] or "Weekday"
            red = (f" Estimate: {i['user_errors_planned']:,} → ~{i['user_errors_est']:,} user errors in planned maintenance."
                   if i["user_errors_planned"] else "")
            add("High" if hit else "Medium", "Production instance on the default window", i["name"],
                "The default window (17:00–08:00) includes the evening hours with high traffic." + (f" Affected apps: {', '.join(hit)}." if hit else "") + red,
                f"Change to {WINDOWS[rec]} (best score from the real load). The instance IP changes: update NSGs and firewalls.",
                f"az sql mi update -g {i['rg']} -n {i['name']} --maint-config-id \"{config_id(i['sub'], i['location'], rec)}\"")
    for i in insts:
        if i.get("fog_role") == "Primary" and i.get("fog_partner") in by_name:
            s = by_name[i["fog_partner"]]
            if not i["paired"] and i["window"] == s["window"]:
                add("High", "Failover group with the same window in non-paired regions", f"{i['fog']} ({i['name']} / {s['name']})",
                    f"{region_label(i['location'])} and {region_label(s['location'])} are not a region pair: Azure can maintain both "
                    "replicas in the same time slot.",
                    f"Primary on {WINDOWS[i['recommended'] or 'Weekday']}, secondary on {WINDOWS[s['recommended'] or 'Weekend']}. "
                    "Change the secondary first.",
                    f"az sql mi update -g {s['rg']} -n {s['name']} --maint-config-id \"{config_id(s['sub'], s['location'], s['recommended'] or 'Weekend')}\"")
    for i in insts:
        if i["proxy"] == "Proxy":
            add("Medium", "Proxy connection type", i["name"], "Proxy is the legacy mode: it adds latency and causes more disconnections "
                "during gateway maintenance. Redirect has been the default since October 2025.",
                "Change to Redirect (open ports 11000–11999 from the client subnets; validate in pre-production).",
                f"az sql mi update -g {i['rg']} -n {i['name']} --proxy-override Redirect")
    for i in insts:
        if i["batch"] and i["batch"] & WINDOW_CELLS.get(i["window"], set()):
            n = sum(1 for e in events if e["mi"] == i["name"] and (lambda lo: (lo.weekday(), lo.hour))(to_local(e["_t"])) in i["batch"])
            add("Medium", "The window overlaps the batch jobs", i["name"], f"Batch {i['batch_label']} falls inside "
                f"{WINDOWS[i['window']]}; {n} reconfiguration{'s' if n != 1 else ''} happened during batch hours.",
                "Make sure the jobs are resumable and idempotent, or move the batch outside the window.")
    unpl = [e for e in events if e["reason"] in ("Unplanned", "Detected")]
    if unpl:
        add("Medium", "Unplanned events: no window protects against them", ", ".join(sorted({e["mi"] for e in unpl})),
            f"{len(unpl)} event{'s' if len(unpl) != 1 else ''} outside the window's control, with {sum(e['user_errors'] for e in unpl):,} "
            f"user error{'s' if sum(e['user_errors'] for e in unpl) != 1 else ''}.",
            "Only retries in the application prevent this impact. No window solves it.")
    for i in prd:
        if i["tier"] == "GeneralPurpose" and any(a["app"] in risky for a in apps_by_mi.get(i["name"], [])):
            add("Info", "General Purpose with critical applications", i["name"], "In GP the reconfiguration moves the engine to another node; "
                "in Business Critical it fails over to an already warm replica.", "Consider Business Critical only if there is still impact once retries are in place.")
    outside = [e for e in events if e["reason"] == "Planned" and not e["in_window"]]
    if outside:
        add("Info", "Planned events outside the configured window", ", ".join(sorted({e["mi"] for e in outside})),
            f"{len(outside)} event{'s' if len(outside) != 1 else ''}. Azure can apply critical updates outside the window.", "Check the reason in Service Health.")
    for i in insts:
        if i["pool"]:
            add("Info", "Instance in an instance pool", i["name"], "The maintenance window cannot be configured in instance pools.", "—")
    if raw.get("telemetry"):
        for i in prd:
            if not apps_by_mi.get(i["name"]) and i.get("fog_role") != "Secondary":
                add("Info", "Instance without application telemetry", i["name"], "No Application Insights SQL dependency points to this instance.",
                    "Enable Application Insights in the applications that use it to measure the real impact.")
    if any(f["command"].startswith("az sql mi update") and "maint-config-id" in f["command"] for f in findings):
        add("Info", "Changing the window changes the instance IP", "All", "The operation moves the instance to another virtual "
            "cluster: the IP changes and free IPs are needed in the subnet.", "Plan the change for off-peak hours, update NSGs and firewalls, "
            "and check the subnet size.")
    SEV = {"High": 0, "Medium": 1, "Info": 2}
    findings.sort(key=lambda f: SEV[f["severity"]])

    # ---- KPIs ------------------------------------------------------------------------------------------
    durs = [e["duration_s"] for e in events]
    nxt = min(raw["upcoming"], key=lambda u: u["start"]) if raw["upcoming"] else None
    user_total = sum(e["user_errors"] for e in events)
    user_norety = sum(a["user_errors"] for a in apps if a["verdict"] == "No retries")
    kpis = {
        "managed_instances_prd": len(prd),
        "prd_on_default_window": sum(1 for i in prd if i["window"] == "Default"),
        "reconfigurations": len(events),
        "planned": sum(1 for e in events if e["reason"] == "Planned"),
        "unplanned": len(unpl),
        "avg_duration_s": round(sum(durs) / len(durs), 1) if durs else 0,
        "max_duration_s": max(durs) if durs else 0,
        "user_errors": user_total,
        "user_errors_no_retry_pct": round(100 * user_norety / user_total) if user_total else 0,
        "apps_no_retry": sum(1 for a in apps if a["verdict"] == "No retries"),
        "apps_partial": sum(1 for a in apps if a["verdict"] == "Partial"),
        "apps_total": len(apps),
        "next_maintenance": fmt_local(parse_dt(nxt["start"])) if nxt else "—",
        "maintenance_alert": any(x["enabled"] and x["covers_maintenance"] and x["covers_sqlmi"] for x in raw["alerts"]),
    }
    answer = (f"{period_label}: {kpis['reconfigurations']} SQL MI reconfiguration{'s' if kpis['reconfigurations'] != 1 else ''} "
              f"(average {kpis['avg_duration_s']} s, max "
              f"{kpis['max_duration_s']} s). {user_total:,} error{'s' if user_total != 1 else ''} reached users; "
              f"{kpis['user_errors_no_retry_pct']}% came from "
              f"{kpis['apps_no_retry']} application{'s' if kpis['apps_no_retry'] != 1 else ''} without retries. The window decides WHEN the "
              f"reconfiguration happens; retries decide IF users notice. Unplanned events that no window could have prevented: "
              f"{kpis['unplanned']}.")
    if operation == "summary":
        return {"status": "ok", "mode": MODE, "period": period_label, "kpis": kpis, "answer": answer,
                "findings": [{k: f[k] for k in ("severity", "title", "scope", "action", "command")} for f in findings],
                "apps": [{k: a[k] for k in ("app", "verdict", "user_errors", "dep_failures")} for a in apps],
                "sources": sources}
    if operation == "upcoming":
        return {"status": "ok", "mode": MODE, "upcoming": [dict(u, start_local=fmt_local(parse_dt(u["start"])), end_local=fmt_local(parse_dt(u["end"])),
                at_risk_apps=sorted({a["app"] for m in u["impacted"] for a in apps_by_mi.get(m, []) if a["app"] in risky})) for u in raw["upcoming"]],
                "maintenance_alert": kpis["maintenance_alert"], "sources": sources}

    # ==== HTML report ===================================================================================
    # Presentation only: same data, sections and order. Self-contained (no network), responsive, A4 print.
    E = lambda v: html.escape("" if v is None else str(v))
    NIL = '<span class="nil">—</span>'

    def N(v):
        # Thousands with a comma separator (English convention).
        return f"{v:,}" if isinstance(v, int) and not isinstance(v, bool) else E(v)

    def nw(text):
        # Resource names never break at their hyphens.
        return re.sub(r"\S+", lambda m: f'<span class="nw">{m.group(0)}</span>', E(text))

    def win_html(w):
        name, _, hours = WINDOWS[w].partition(" · ")
        return f"{E(name)}<small>{E(hours)}</small>" if hours else E(name)

    def pill(text, tone):
        return f'<span class="pill t-{tone}">{E(text)}</span>'

    def td(body, raw=None, n=None, cls="", label=""):
        attrs = (("data-raw", raw), ("data-n", n), ("class", cls or None), ("data-label", label or None))
        return "<td" + "".join(f' {k}="{E(v)}"' for k, v in attrs if v is not None) + f">{body}</td>"

    def dtable(stub, label, cols, rows, filters="", stack=False, empty="No data."):
        # Search, filters, sortable headers, CSV export of the visible rows and a live row count.
        if not rows:
            return f'<div class="card"><p class="empty">{E(empty)}</p></div>'
        th = "".join(f'<th scope="col" data-l="{E(h)}"{" class=n" if k else ""}><button type="button" class="sort" data-i="{i}">{E(h)}</button></th>'
                     for i, (h, k) in enumerate(cols))
        return (f'<div class="card dt" data-file="{stub}-{stamp}"><div class="tools"><input class="f-q" type="search" placeholder="Search…" '
                f'aria-label="Search {E(label)}">{filters}<button class="btn ghost f-csv" type="button">{ICON["dl"]}Export CSV</button>'
                f'<span class="cnt" aria-live="polite"></span></div><div class="wrap" role="region" tabindex="0" aria-label="Table: {E(label)}">'
                f'<table{" class=stack" if stack else ""}><thead><tr>{th}</tr></thead><tbody>{"".join(rows)}</tbody></table></div></div>')

    def fselect(key, label, opts):
        return (f'<select data-f="{key}" aria-label="{label}"><option value="">{label}: all</option>'
                + "".join(f'<option value="{E(v)}">{E(v)} ({c})</option>' for v, c in opts) + "</select>")

    def section(sid, title, why, body):
        return f'<section id="{sid}" aria-labelledby="h-{sid}"><div class="sh"><h2 id="h-{sid}">{E(title)}</h2><p>{E(why)}</p></div>{body}</section>'
    ICON = {k: f'<svg class="i" viewBox="0 0 24 24" aria-hidden="true"><path d="{d}"/></svg>' for k, d in {
        "print": "M6 9V3h12v6M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2M6 14h12v7H6z",
        "dl": "M12 3v12m0 0 5-5m-5 5-5-5M4 21h16",
        "alert": "M12 9v4m0 4h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z",
        "ext": "M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"}.items()}
    # Shared severity palette of the report family: tone class + bar colour.
    SEVT = {"High": ("high", "#ef6820"), "Medium": ("med", "#f79009"), "Info": ("neu", "#98a2b3")}
    VT = {"No retries": ("crit", "#d92d20"), "Partial": ("med", "#f79009"), "Resilient": ("ok", "#12b76a")}
    RT = {"Planned": ("low", "#0078d4"), "Unplanned": ("crit", "#d92d20"), "UserInitiated": ("neu", "#667085"), "Detected": ("med", "#dc6803")}
    stamp_utc = now_utc.strftime("%Y-%m-%d %H:%M")
    title = "Azure SQL Managed Instance maintenance resilience"
    sevn = {s: sum(1 for f in findings if f["severity"] == s) for s in SEVT}
    attention = bool(sevn["High"] or sevn["Medium"])
    PL = {"High": ("high", "high"), "Medium": ("medium", "medium"), "Info": ("info", "info")}
    vdetail = (f"{len(findings)} {'action' if len(findings) == 1 else 'actions'}: "
               + ", ".join(f"{n} {PL[s][n != 1]}" for s, n in sevn.items() if n)) if findings else "No pending actions."
    g4 = lambda t: re.sub(r"(?<![\d.,])\d{4,}(?![\d.,])", lambda m: N(int(m.group(0))), t)
    a_lead, a_sep, a_rest = answer.partition("The window decides")
    a_key, a_dot, a_tail = (a_sep + a_rest).partition("notice.")
    CSS = """
:root{--paper:#f3f5f8;--ink:#172338;--title:#1d3354;--muted:#526075;--line:#dfe5ee;--line2:#c3cddb;--soft:#eef2f7;--blue:#0078d4;--link:#0063b1;--hm:#c9d4e3;--mono:ui-monospace,'Cascadia Mono',Consolas,monospace;--sh:0 1px 2px rgba(23,35,56,.05),0 10px 28px rgba(23,35,56,.07)}
*{box-sizing:border-box}html{scroll-behavior:smooth;scrollbar-color:var(--line2) var(--paper)}body{margin:0;background:var(--paper);color:var(--ink);font:15px/1.55 'Segoe UI',system-ui,-apple-system,Roboto,Arial,sans-serif;font-variant-numeric:tabular-nums}
::selection{background:#cfe4f7}a{color:var(--link);text-underline-offset:3px}button,input,select{font:inherit;color:inherit}:focus-visible{outline:3px solid var(--blue);outline-offset:2px}
.i{width:16px;height:16px;flex:none;fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}.skip{position:absolute;left:-999px;top:8px;z-index:30;background:#fff;padding:8px 14px}.skip:focus{left:12px}
.bar{position:sticky;top:0;z-index:20;display:flex;align-items:center;gap:14px;padding:10px max(clamp(16px,4vw,40px),calc(50% - 660px));background:#fff;box-shadow:0 1px 0 var(--line)}
.brand{display:flex;align-items:center;gap:10px;color:var(--title);text-decoration:none;font-weight:700;font-size:16px;white-space:nowrap}.brand svg{width:30px;height:30px}
.ctx{color:var(--muted);font-size:13.5px;white-space:nowrap;padding-left:14px;border-left:1px solid var(--line)}.bar nav{display:flex}
.bar nav a{color:var(--muted);text-decoration:none;font-size:13.5px;font-weight:600;padding:7px 9px;border-radius:8px}.bar nav a:hover{background:var(--soft);color:var(--title)}
.acts{margin-left:auto;display:flex;gap:8px;align-items:center}.tag{font-size:12.5px;font-weight:600;color:var(--muted);border:1px solid var(--line2);border-radius:99px;padding:4px 11px;white-space:nowrap}
.btn{display:inline-flex;align-items:center;gap:8px;min-height:40px;padding:0 15px;border-radius:10px;border:1px solid transparent;background:var(--blue);color:#fff;font-weight:700;font-size:14px;cursor:pointer;white-space:nowrap}
.btn:hover{background:#0067b8}.btn.ghost,.copy{background:#fff;color:var(--title);border:1px solid var(--line2)}.btn.ghost:hover,.copy:hover{background:var(--soft)}
.hero{position:relative;background:linear-gradient(150deg,#243a5e,#172a48);color:#fff;padding:clamp(28px,4.4vw,52px) clamp(16px,4vw,40px) 104px}.hero::before{content:"";position:absolute;inset:0 0 auto;height:5px;background:var(--blue)}
.hero-in{max-width:1320px;margin:0 auto;display:grid;grid-template-columns:minmax(0,1fr) 330px;gap:22px 48px;align-items:start}
.hero h1{margin:0 0 14px;font-size:clamp(30px,3.3vw,44px);line-height:1.1;letter-spacing:-.02em;text-wrap:balance}.lead{margin:0 0 10px;font-size:18px;max-width:68ch;color:#eef3f9}
.thesis{margin:0;max-width:72ch;color:var(--hm)}.thesis b{color:#fff;font-weight:600}.meta{display:flex;flex-wrap:wrap;gap:8px;margin-top:20px}
.meta span{font-size:12.5px;padding:4px 11px;border-radius:99px;border:1px solid rgba(255,255,255,.24);color:var(--hm);white-space:nowrap}.meta .on{color:#fff;font-weight:700;border-color:#fedf89}
.verdict{border-radius:16px;padding:18px 20px;background:rgba(255,255,255,.07);border:1px solid rgba(254,223,137,.5);color:var(--hm);font-size:14px}
.verdict b{display:block;margin:2px 0 8px;font-size:26px;line-height:1.2;color:#fedf89}.verdict.good{border-color:rgba(166,244,197,.5)}.verdict.good b{color:#a6f4c5}
.dist{grid-column:1/-1}.track{display:flex;height:12px;border-radius:99px;overflow:hidden;background:rgba(255,255,255,.18)}
.legend,.keys,.scale{display:flex;flex-wrap:wrap;gap:6px 18px;margin-top:10px;font-size:13px;color:var(--muted)}.legend{color:var(--hm);font-size:13.5px}.legend b{color:#fff}
.legend span,.keys span,.scale span{display:inline-flex;align-items:center;gap:7px}.legend i,.keys i,.scale i{width:11px;height:11px;border-radius:3px}.keys i{border-radius:50%}
.body{max-width:1400px;margin:0 auto;padding:0 clamp(16px,4vw,40px) 40px}.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:14px;margin-top:-64px;position:relative}
.kpi,.card{background:#fff;border:1px solid var(--line);border-radius:16px;padding:16px 18px;box-shadow:var(--sh);min-width:0}.card{padding:20px 22px}
.kpi .v{font-size:36px;line-height:1.05;font-weight:700;letter-spacing:-.02em;color:var(--title);white-space:nowrap}.kpi small{font-size:16px;font-weight:600;color:var(--muted);margin-left:5px;letter-spacing:0}
.kpi .l{margin-top:8px;font-size:14px;font-weight:600;line-height:1.3}.kpi .f{margin-top:8px;font-size:13px;color:var(--muted)}
.kpi .bad,.kpi .warn,.kpi .good{color:#b42318;font-weight:600}.kpi .warn{color:#93370d}.kpi .good{color:#067647}
.sim{display:flex;gap:10px;align-items:center;margin-top:18px;padding:11px 16px;border-radius:12px;background:repeating-linear-gradient(135deg,#fffaeb 0 12px,#fef0c7 12px 24px);color:#7a2e0e;font-weight:600;font-size:14px;border:1px solid #fedf89}
section{margin-top:44px;scroll-margin-top:72px}.sh{margin-bottom:14px}
.sh h2{margin:0;font-size:22px;line-height:1.25;color:var(--title)}.sh p,.sub,.note{margin:4px 0 0;color:var(--muted);font-size:14px;max-width:75ch}
.card h3{margin:0 0 4px;font-size:17px;line-height:1.3;color:var(--title)}.sub{margin-bottom:14px;font-size:13.5px}.note{margin:10px 2px 0;font-size:13.5px;max-width:110ch}
.grid2,.grid3,.hm-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,460px),1fr));gap:16px}.grid3{grid-template-columns:repeat(auto-fit,minmax(min(100%,300px),1fr))}
.pill,.sev{display:inline-flex;align-items:center;gap:6px;padding:2px 10px;border-radius:99px;font-size:12.5px;font-weight:600;white-space:nowrap}
.sev{font-weight:700}.sev::before{content:"";width:7px;height:7px;border-radius:50%;background:currentColor}
.t-ok{background:#dcfae6;color:#067647}.t-crit{background:#fee4e2;color:#b42318}.t-high{background:#ffead5;color:#b93815}.t-med{background:#fef0c7;color:#93370d}.t-low{background:#d1e9ff;color:#175cd3}.t-neu{background:#eaecf0;color:#344054}
.chips{display:flex;flex-wrap:wrap;gap:6px}.chips span{font-size:13px;background:var(--soft);border-radius:8px;padding:2px 9px;white-space:nowrap}.chips.risk span{background:#fee4e2;color:#b42318;font-weight:600}
.up-h{display:flex;justify-content:space-between;align-items:flex-start;gap:12px 20px;flex-wrap:wrap}.facts{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,210px),1fr));gap:16px 24px;margin:16px 0 0}
.facts dt{font-size:12.5px;font-weight:700;color:var(--muted)}.facts dd{margin:4px 0 0}.facts .wide{grid-column:span 2}.ok-t{color:#067647;font-weight:600}
.dt,.flat{padding:0;overflow:hidden}.tools{display:flex;gap:10px;flex-wrap:wrap;align-items:center;padding:16px 18px}
.tools input,.tools select{min-height:40px;border:1px solid var(--line2);border-radius:10px;padding:0 12px;background:#fff;max-width:100%;min-width:0}.tools input{flex:1 1 220px;max-width:340px}
.tools input::placeholder{color:var(--muted)}.cnt{margin-left:auto;font-size:13px;color:var(--muted)}
.wrap,.tl-scroll,.hm-scroll{overflow-x:auto;background:linear-gradient(90deg,#fff 30%,rgba(255,255,255,0)) left/36px 100% no-repeat local,linear-gradient(270deg,#fff 30%,rgba(255,255,255,0)) right/36px 100% no-repeat local,radial-gradient(farthest-side at 0 50%,rgba(16,24,40,.16),rgba(16,24,40,0)) left/14px 100% no-repeat scroll,radial-gradient(farthest-side at 100% 50%,rgba(16,24,40,.16),rgba(16,24,40,0)) right/14px 100% no-repeat scroll}.wrap{border-top:1px solid var(--line)}
table{width:100%;border-collapse:collapse;font-size:14px}th{background:var(--soft);color:var(--title);font-size:12px;font-weight:700;letter-spacing:.04em;text-transform:uppercase;text-align:left;padding:0;border-bottom:1px solid var(--line);vertical-align:bottom}
th .sort,th .th{all:unset;box-sizing:border-box;display:flex;align-items:center;gap:6px;width:100%;padding:11px 14px}th .sort{cursor:pointer}th .sort:hover{color:var(--link)}
th .sort:focus-visible{outline:3px solid var(--blue);outline-offset:-3px}th.n .sort{justify-content:flex-end}
th[aria-sort] .sort::after{content:"";border:5px solid transparent;border-top-color:currentColor;margin-top:5px}th[aria-sort=ascending] .sort::after{border-color:transparent transparent currentColor;margin:0 0 5px}
td{padding:12px 14px;border-bottom:1px solid var(--line);vertical-align:top}tbody tr:last-child td{border-bottom:0}tbody tr:hover td{background:#f8fafc}
td.n{text-align:right;white-space:nowrap}td small{display:block;color:var(--muted);font-size:12.5px}.nw{white-space:nowrap}.nil,.empty{color:var(--muted)}.empty{margin:0}
.ext{display:inline-flex;align-items:center;gap:4px;font-size:12.5px;font-weight:600}.ext .i{width:13px;height:13px}.u{color:#b42318;font-weight:700}
.c-t{min-width:180px}.c-s{min-width:140px}.c-d{min-width:240px}.c-a{min-width:320px}.c-w{min-width:170px}.c-c{min-width:170px}
.cmd{margin-top:10px;border:1px solid var(--line);border-radius:10px;background:#f6f8fb;overflow:hidden}.cmd div{display:flex;justify-content:space-between;align-items:center;padding:4px 6px 4px 10px;border-bottom:1px solid var(--line);font-size:12px;font-weight:600;color:var(--muted)}
.copy{border-radius:7px;font-size:12.5px;font-weight:600;padding:2px 10px;cursor:pointer}.cmd code{display:block;padding:8px 10px;font:12.5px/1.5 var(--mono);white-space:pre-wrap;color:#1d2939}
.tl{min-width:640px;padding-right:22px;font-size:12.5px;color:var(--muted)}.tl-row{display:grid;grid-template-columns:150px minmax(0,1fr);align-items:center}
.tl-row>b{font-weight:600;color:var(--ink);font-size:13.5px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;padding-right:10px}
.tl-track{position:relative;height:52px}.tl-track::before{content:"";position:absolute;left:0;right:0;top:64%;height:1px;background:var(--line2)}
.gl{position:absolute;top:0;bottom:0;width:1px;background:var(--line)}.tl-ax .tl-track{height:24px}.tl-ax .tl-track::before{display:none}
.tk{position:absolute;top:4px;transform:translateX(-50%);white-space:nowrap}.ev{position:absolute;top:64%;transform:translate(-50%,-50%);border-radius:50%;border:2px solid #fff;opacity:.92}
.evn{position:absolute;transform:translateX(-50%);color:#b42318;font-weight:700;font-size:12px;white-space:nowrap}
.bars{display:grid;gap:10px}.brow{display:grid;grid-template-columns:minmax(120px,32%) 1fr minmax(96px,auto);gap:12px;align-items:center;font-size:14px}
.bl{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.bt{position:relative;height:12px;background:var(--soft);border-radius:99px;overflow:hidden}.bt i{position:absolute;left:0;top:0;bottom:0;border-radius:99px;background:#c3cddb}
.brow b{text-align:right;font-weight:600;white-space:nowrap}.brow small{color:var(--muted);font-weight:400}.lg{list-style:none;margin:0;padding:0;display:grid;gap:10px}
.lg li{display:grid;grid-template-columns:170px 1fr;gap:10px;align-items:baseline;font-size:14px}.lg .pill{justify-self:start}.hm-grid{grid-template-columns:repeat(auto-fit,minmax(min(100%,560px),1fr))}
.hm-meta{display:flex;flex-wrap:wrap;gap:4px 14px;font-size:13px;color:var(--muted)}.hm-meta b{color:var(--ink);font-weight:600}
.hm{display:grid;grid-template-columns:34px repeat(24,minmax(16px,1fr));gap:2px;min-width:520px;margin-top:12px;font-size:11.5px;color:var(--muted)}.hm span{height:20px;border-radius:3px}
.hm .lab{height:auto;text-align:center}.hm .d{text-align:left}.w{background-image:repeating-linear-gradient(45deg,rgba(255,255,255,.62) 0 2px,transparent 2px 5px)}.r{box-shadow:inset 0 0 0 2px #067647}
.scale .ramp{width:72px;background:linear-gradient(90deg,rgba(0,75,147,.06),#004b93)}
.az ul,.az ol{margin:0;padding-left:20px;display:grid;gap:9px}.az li::marker{color:#12b76a}.az .no li::marker{color:#d92d20}.az ol li::marker{color:var(--title);font-weight:700}
footer{max-width:1400px;margin:0 auto;padding:8px clamp(16px,4vw,40px) 40px;color:var(--muted);font-size:13px}footer p{margin:4px 0}
@media (max-width:1399px){.ctx{display:none}}@media (max-width:1100px){.bar nav{display:none}.hero-in{grid-template-columns:1fr}}
@media (max-width:760px){.tag,.btn .lbl{display:none}.btn{padding:0 12px}.kpi .v{font-size:30px}.lead{font-size:16.5px}.hero{padding-bottom:88px}.facts .wide{grid-column:auto}
.stack thead{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)}.stack,.stack tbody,.stack tr,.stack td{display:block;width:100%}
.stack tr{padding:14px 16px;border-bottom:1px solid var(--line)}.stack td{border:0;padding:2px 0;min-width:0}
.stack td[data-label]::before{content:attr(data-label);display:block;margin-top:10px;font-size:11.5px;font-weight:700;letter-spacing:.04em;text-transform:uppercase;color:var(--muted)}
.brow{grid-template-columns:1fr auto}.brow .bt{grid-column:1/-1;grid-row:2}.lg li{grid-template-columns:1fr}.cnt{margin-left:0;width:100%}}
@media (prefers-reduced-motion:reduce){html{scroll-behavior:auto}}
@media print{*{-webkit-print-color-adjust:exact;print-color-adjust:exact}body{background:#fff;font-size:12px}.bar{position:static;box-shadow:none;border-bottom:1px solid var(--line);padding:0 0 8px}
.bar nav,.acts .btn,.tools,.copy,.skip{display:none!important}.hero{padding:22px 22px 80px}.body,footer{padding-left:0;padding-right:0}.hero h1{font-size:28px}.lead{font-size:14px}
.hero-in{grid-template-columns:minmax(0,1fr) 220px;gap:14px 24px}.verdict b{font-size:19px}.kpis{grid-template-columns:repeat(3,1fr);margin-top:-60px}.kpi .v{font-size:26px}.kpi,.card{box-shadow:none}
section{margin-top:22px}.sh{break-inside:avoid;break-after:avoid}.sh h2{font-size:18px}.sh p,.sub,.note{font-size:12px}h2,h3{break-after:avoid}.card{padding:14px 16px}.dt,.flat{padding:0}.card h3{font-size:14px}
.card,.kpi,tr,.brow,.tl-row,.cmd,.hm-card{break-inside:avoid}.dt{break-inside:auto}.dt,.flat,.wrap,.tl-scroll,.hm-scroll{overflow:visible;background:none}
thead{display:table-header-group}table{font-size:11px}th{font-size:10px;letter-spacing:.02em}td{padding:5px 6px;overflow-wrap:anywhere}th .th{padding:5px 6px}
th .sort{display:none}th[data-l]::after{content:attr(data-l);display:block;padding:5px 6px}th.n::after{text-align:right}
td small,.pill,.sev{font-size:10.5px}.pill,.sev{padding:1px 7px}.c-s,.c-w,.tl,.hm{min-width:0}.c-t{min-width:110px}.c-d{min-width:150px}.c-c{min-width:120px}.c-a{min-width:250px}.cmd code{font-size:10px}
.grid2,.hm-grid{grid-template-columns:1fr}.grid3{grid-template-columns:repeat(3,1fr)}.brow,.lg li{font-size:12px}a{color:inherit;text-decoration:none}}
"""
    JS = r"""
(()=>{const $$=(s,r=document)=>[...r.querySelectorAll(s)];
$$('.dt').forEach(card=>{const tb=card.querySelector('tbody'),rows=[...tb.rows],q=card.querySelector('.f-q'),sels=$$('select[data-f]',card),cnt=card.querySelector('.cnt');
const val=c=>c.dataset.raw!==undefined?c.dataset.raw:c.textContent.trim();
const draw=()=>{const t=q.value.trim().toLowerCase();let m=0;rows.forEach(r=>{const ok=(!t||r.textContent.toLowerCase().includes(t))&&sels.every(s=>!s.value||r.dataset[s.dataset.f]===s.value);r.hidden=!ok;if(ok)m++});
cnt.textContent=m+' of '+rows.length+' rows'};q.addEventListener('input',draw);sels.forEach(s=>s.addEventListener('change',draw));
$$('th .sort',card).forEach(b=>b.addEventListener('click',()=>{const th=b.parentNode,i=+b.dataset.i,asc=th.getAttribute('aria-sort')!=='ascending';
$$('th',card).forEach(h=>h.removeAttribute('aria-sort'));th.setAttribute('aria-sort',asc?'ascending':'descending');
rows.sort((a,z)=>{const x=a.cells[i],y=z.cells[i],nx=x.dataset.n,ny=y.dataset.n,d=(nx!==undefined&&ny!==undefined)?nx-ny:val(x).localeCompare(val(y),'en',{numeric:true,sensitivity:'base'});return asc?d:-d});
rows.forEach(r=>tb.appendChild(r))}));
card.querySelector('.f-csv').addEventListener('click',()=>{const Q=v=>'"'+String(v).replace(/"/g,'""')+'"';
const lines=[$$('thead th',card).map(h=>Q(h.textContent.trim())).join(';')].concat(rows.filter(r=>!r.hidden).map(r=>[...r.cells].map(c=>Q(val(c))).join(';')));
const a=document.createElement('a');a.href=URL.createObjectURL(new Blob(['\ufeff'+lines.join('\r\n')],{type:'text/csv;charset=utf-8'}));
a.download=card.dataset.file+'.csv';document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(a.href),2000)});draw()});
$$('[data-copy]').forEach(b=>b.addEventListener('click',()=>{const c=b.closest('.cmd').querySelector('code'),done=()=>{b.textContent='Copied';setTimeout(()=>{b.textContent='Copy'},1600)};
const sel=()=>{const r=document.createRange();r.selectNodeContents(c);const s=getSelection();s.removeAllRanges();s.addRange(r);try{if(document.execCommand('copy'))done()}catch(e){}};
if(navigator.clipboard&&window.isSecureContext)navigator.clipboard.writeText(c.textContent).then(done,sel);else sel()}));
$$('[data-print]').forEach(b=>b.addEventListener('click',()=>window.print()))})();
"""
    pf = 'font:8px/1.2 "Segoe UI",Arial,sans-serif;color:#667085'
    out = ['<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" '
           'content="default-src \'none\'; img-src data:; font-src data:; style-src \'unsafe-inline\'; script-src \'unsafe-inline\'">'
           f'<title>SQL MI · Maintenance resilience</title><style>{CSS}@page{{size:A4;margin:12mm 10mm 14mm;@bottom-left{{content:"{title} · {stamp_utc} UTC";{pf}}}'
           f'@bottom-right{{content:"Page " counter(page) " of " counter(pages);{pf}}}}}</style></head><body><a class="skip" href="#main">Skip to content</a>'
           '<header class="bar"><a class="brand" href="#summary"><svg viewBox="0 0 32 32" aria-hidden="true"><rect width="32" height="32" rx="8" fill="#0078d4"/>'
           '<g fill="none" stroke="#fff" stroke-width="2.2"><ellipse cx="16" cy="9.5" rx="8" ry="3.2"/><path d="M8 9.5v13c0 1.8 3.6 3.2 8 3.2s8-1.4 8-3.2v-13M8 16c0 1.8 3.6 3.2 8 3.2s8-1.4 8-3.2"/>'
           '</g></svg>Azure SRE Agent</a><span class="ctx">SQL Managed Instance · maintenance</span><nav aria-label="Report sections">'
           + "".join(f'<a href="#{a.lower()}">{a}</a>' for a in ("Summary", "Actions", "Instances", "Events", "Applications", "Load", "Sources"))
           + f'</nav><div class="acts"><span class="tag">Read-only</span><button class="btn" type="button" data-print aria-label="Print or save as PDF">{ICON["print"]}'
           '<span class="lbl">Print / PDF</span></button></div></header><main id="main">']
    # Hero: verdict first (the short answer, the verdict and the priority mix)
    chips = [f"Generated {stamp_utc} UTC", period_label, f"Times in {LOCAL_TIMEZONE}",
             f"{len(insts)} instance{'s' if len(insts) != 1 else ''} · {len(prd)} production"]
    gaps = sum(1 for s in sources if s["status"] != "ok")
    out.append(f'<div class="hero" id="summary"><div class="hero-in"><div><h1>{E(title)}</h1><p class="lead">{g4(E(a_lead.strip()))}</p>'
               + (f'<p class="thesis"><b>{E(a_key + a_dot)}</b> {g4(E(a_tail.strip()))}</p>' if a_sep else "")
               + '<div class="meta">' + "".join(f"<span>{E(c)}</span>" for c in chips)
               + f'<span class="on">{"SIMULATED DATA (demo)" if MODE == "demo" else "LIVE DATA"}</span>'
               + (f'<span class="on">Partial coverage: {gaps} of {len(sources)} sources without complete data</span>' if gaps else "") + "</div></div>"
               f'<div class="verdict{"" if attention else " good"}" role="group" aria-label="Verdict">Verdict<b>{"Needs attention" if attention else "No significant issues"}</b>{E(vdetail)}</div>')
    if findings:
        out.append(f'<div class="dist"><div class="track" role="img" aria-label="Actions by priority: {E(vdetail)}">'
                   + "".join(f'<i style="width:{100 * n / len(findings):.2f}%;background:{SEVT[s][1]}"></i>' for s, n in sevn.items() if n)
                   + '</div><div class="legend">' + "".join(f'<span><i style="background:{SEVT[s][1]}"></i>{s} <b>{n}</b></span>' for s, n in sevn.items() if n) + "</div></div>")
    nm = kpis["next_maintenance"].split(" ")
    DAYS = dict(zip(DIAS, ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")))
    ue = kpis["user_errors"]
    K = [(N(ue), "user-facing errors", f"{kpis['user_errors_no_retry_pct']}% in apps without retries" if ue else "", "bad"),
         (f"{N(kpis['apps_no_retry'])}<small>/{N(kpis['apps_total'])}</small>", "apps without retries",
          f"+{kpis['apps_partial']} partial" if kpis["apps_partial"] else "", "warn"),
         (N(kpis["reconfigurations"]), "reconfigurations", f"{kpis['planned']} planned · {kpis['unplanned']} unplanned", ""),
         (f"{E(kpis['avg_duration_s'])}<small>s</small>", "average duration", f"max {E(kpis['max_duration_s'])} s", ""),
         (f"{N(kpis['prd_on_default_window'])}<small>/{N(kpis['managed_instances_prd'])}</small>", "production on default window",
          f"{N(kpis['managed_instances_prd'])} production instance{'s' if kpis['managed_instances_prd'] != 1 else ''}", ""),
         (f"{E(nm[1])}<small>{E(nm[2])}</small>" if len(nm) == 3 else E(nm[0]),
          f"next maintenance · {DAYS.get(nm[0], nm[0])}" if len(nm) == 3 else "next maintenance",
          "maintenance alert configured" if kpis["maintenance_alert"] else "no maintenance alert", "good" if kpis["maintenance_alert"] else "bad")]
    out.append('</div></div><div class="body"><div class="kpis">' + "".join(
        f'<div class="kpi"><div class="v">{v}</div><div class="l">{E(lab)}</div>' + (f'<div class="f {t}">{f}</div>' if f else "") + "</div>"
        for v, lab, f, t in K) + "</div>")
    if MODE == "demo":
        out.append(f'<div class="sim" role="note">{ICON["alert"]}DEMO MODE — simulated data that shows what the report looks like. Configure the tool (README, step 4) to analyze your environment.</div>')

    # Next maintenance
    ups = []
    for u in sorted(raw["upcoming"], key=lambda x: x["start"]):
        at = sorted({a["app"] for m in u["impacted"] for a in apps_by_mi.get(m, []) if a["app"] in risky})
        st_, en_ = parse_dt(u["start"]), parse_dt(u["end"])
        dd = (st_ - now_utc).days
        when = ((f"starts in {dd} day{'s' if dd != 1 else ''}" if dd >= 1 else "starts in less than 24 h") if st_ > now_utc
                else "in progress" if en_ >= now_utc else "ended")
        ups.append(f'<div class="card"><div class="up-h"><div><h3>{E(u["title"])}</h3><p class="sub">{E(u["tracking_id"])} · {E(u["source"])} · {when}</p></div>'
                   + (pill(f"{len(at)} application{'s' if len(at) != 1 else ''} at risk", "crit") if at else pill("No applications at risk", "ok"))
                   + f'</div><dl class="facts"><div><dt>Start (local time)</dt><dd>{E(fmt_local(st_))}</dd></div><div><dt>End (local time)</dt><dd>{E(fmt_local(en_))}</dd></div>'
                   + '<div><dt>Instances</dt><dd class="chips">' + ("".join(f"<span>{E(m)}</span>" for m in u["impacted"]) or NIL) + "</dd></div>"
                   + '<div class="wide"><dt>Applications at risk (no retries or partial)</dt>'
                   + (f'<dd class="chips risk">{"".join(f"<span>{E(a)}</span>" for a in at)}</dd>' if at else '<dd class="ok-t">No applications at risk detected.</dd>')
                   + "</div></dl></div>")
    out.append(section("next", "Next maintenance", "What Azure has already published in Service Health for your instances, and which applications will notice it.",
                       "".join(ups) or '<div class="card"><p class="empty">Service Health has no planned maintenance published for your SQL MI.</p></div>'))

    # Prioritized actions (findings register)
    rows = []
    for f in findings:
        cmd = (f'<div class="cmd"><div>Command<button class="copy" type="button" data-copy>Copy</button></div><code>'
               + re.sub(r"[^\s/]+|/", lambda m: "/<wbr>" if m.group(0) == "/" else f'<span class="nw">{m.group(0)}</span>', E(f["command"])) + "</code></div>"
               if f["command"] else "")
        rows.append(f'<tr data-sev="{E(f["severity"])}">' + td(f'<span class="sev t-{SEVT[f["severity"]][0]}">{E(f["severity"])}</span>', f["severity"], SEV[f["severity"]])
                    + td(f'<b>{E(f["title"])}</b>', f["title"], cls="c-t", label="Finding") + td(nw(f["scope"]), f["scope"], cls="c-s", label="Scope")
                    + td(E(f["detail"]), f["detail"], cls="c-d", label="Detail")
                    + td(E(f["action"]) + cmd, f["action"] + (" | " + f["command"] if f["command"] else ""), cls="c-a", label="What to do") + "</tr>")
    out.append(section("actions", "Prioritized actions", "Sorted by priority, each with the exact command. The agent changes nothing: your team validates and runs them.",
                       dtable("sqlmi-actions", "Prioritized actions", [("Priority", ""), ("Finding", ""), ("Scope", ""), ("Detail", ""), ("What to do", "")], rows,
                              fselect("sev", "Priority", [(s, n) for s, n in sevn.items() if n]), True, "No actions: no rule was triggered in this run.")))

    # Instances and windows
    rows = []
    for i in sorted(insts, key=lambda x: (x["env"] != "prd", x["name"])):
        bc = i["tier"] == "BusinessCritical"
        change = i["recommended"] and i["recommended"] != i["window"]
        est = (f'{N(i["user_errors_planned"])} → ~{N(i["user_errors_est"])}' if i["user_errors_planned"] and i["recommended"] != i["window"]
               else N(i["user_errors_planned"]))
        rows.append("<tr>" + td(f'<b class="nw">{E(i["name"])}</b><small>{E(i["rg"])}</small><a class="ext" href="https://portal.azure.com/#@/resource{E(i["id"])}" '
                                f'target="_blank" rel="noopener noreferrer">Portal{ICON["ext"]}</a>', i["name"])
                    + td(E(region_label(i["location"])), cls="nw")
                    + td(f'<abbr title="{"Business Critical" if bc else "General Purpose"}">{"BC" if bc else "GP"}</abbr> · {E(i["vcores"])} vCores',
                         f'{"BC" if bc else "GP"} · {i["vcores"]} vCores', cls="nw")
                    + td(pill(i["env"], "low" if i["env"] == "prd" else "neu"), i["env"]) + td(win_html(i["window"]), WINDOWS[i["window"]], cls="c-w")
                    + td(pill("Proxy", "high") if i["proxy"] == "Proxy" else E(i["proxy"]), i["proxy"])
                    + td(f'{E(i["fog"])}<small>{"primary" if i["fog_role"] == "Primary" else "secondary"}</small>' if i.get("fog") else NIL,
                         f'{i["fog"]} · {i["fog_role"]}' if i.get("fog") else "—", cls="nw")
                    + td(win_html(i["recommended"]) if change else pill("Keep", "ok") if i["recommended"] else NIL,
                         WINDOWS[i["recommended"]] if change else "Keep" if i["recommended"] else "—", cls="c-w")
                    + td(est, est.replace(",", ""), i["user_errors_planned"], "n") + "</tr>")
    out.append(section("instances", "Instances and windows", "Current window versus the one recommended by the real load of each instance.",
                       dtable("sqlmi-instances", "Instances and windows", [("Instance", ""), ("Region", ""), ("Tier", ""), ("Environment", ""), ("Current window", ""),
                              ("Connection", ""), ("Failover group", ""), ("Recommended window", ""), ("User errors (planned)", "n")], rows,
                              empty="No instances in the inventory.")
                       + '<p class="note">The error estimate applies the average load of the recommended window to the real planned events. '
                         'It is indicative only: only retries remove the impact.</p>'))

    # Reconfigurations and user errors: timeline in HTML so the text keeps its size on a phone and on paper
    body = ""
    if events:
        span = (now_utc - start_utc).total_seconds()
        ticks = [(100 * k / period_days, to_local(start_utc + timedelta(days=k)).strftime("%d %b")) for k in range(0, period_days + 1, max(1, period_days // 6))]
        grid = "".join(f'<i class="gl" style="left:{x:.2f}%"></i>' for x, _ in ticks)
        tl = []
        for m in sorted({e["mi"] for e in events}, key=lambda m: list(by_name).index(m)):
            dots, groups = [], []
            for e in sorted((x for x in events if x["mi"] == m), key=lambda x: x["_t"]):
                x = max(0.0, min(100.0, 100 * (e["_t"] - start_utc).total_seconds() / span))
                r = 4 + min(9, e["duration_s"] / 3)
                dots.append(f'<span class="ev" style="left:{x:.2f}%;width:{2 * r + 4:.0f}px;height:{2 * r + 4:.0f}px;background:{RT.get(e["reason"], ("", "#98a2b3"))[1]}" '
                            f'title="{E(e["local"])} · {E(e["reason_es"])} · {e["duration_s"]} s · {e["user_errors"]:,} user error{"s" if e["user_errors"] != 1 else ""}"></span>')
                # Reconfigurations very close together (for example 2 in the same maintenance) share a single label.
                if groups and x - groups[-1][0] < 1.8:
                    groups[-1][1] += e["user_errors"]
                    groups[-1][2] = max(groups[-1][2], r)
                    groups[-1][3] += 1
                else:
                    groups.append([x, e["user_errors"], r, 1])
            lab = "".join(f'<span class="evn" style="left:{x:.2f}%;bottom:calc(36% + {r + 5:.0f}px)">{N(u)}{f" ({c} reconf.)" if c > 1 else ""}</span>'
                          for x, u, r, c in groups if u)
            tl.append(f'<div class="tl-row"><b title="{E(m)}">{E(m)}</b><div class="tl-track">{grid}{"".join(dots)}{lab}</div></div>')
        tl.append('<div class="tl-row tl-ax"><span></span><div class="tl-track">' + "".join(f'<span class="tk" style="left:{x:.2f}%">{t}</span>' for x, t in ticks) + "</div></div>")
        body = (f'<div class="card"><div class="tl-scroll"><div class="tl" role="img" aria-label="Timeline of {len(events)} reconfiguration{"s" if len(events) != 1 else ""} by instance; '
                'the details are in the table below">' + "".join(tl) + '</div></div><div class="keys">'
                + "".join(f'<span><i style="background:{RT[k][1]}"></i>{REASON[k]}</span>' for k in RT)
                + '<span>red number = user-facing errors · size = duration</span></div></div><div style="height:16px"></div>')
    rows = []
    for e in reversed(events):
        inw = ("Yes" if e["in_window"] else "No") if e["reason"] == "Planned" else "n/a"
        rows.append(f'<tr data-type="{E(e["reason_es"])}">' + td(E(e["local"]), e["local"], e["_t"].timestamp(), "nw") + td(f'<span class="nw">{E(e["mi"])}</span>', e["mi"])
                    + td(pill(e["reason_es"], RT.get(e["reason"], ("neu",))[0]), e["reason_es"]) + td(f'{e["duration_s"]} s', e["duration_s"], e["duration_s"], "n")
                    + td(pill(inw, "high") if inw == "No" else inw, inw) + td(N(e["dep_failures"]), e["dep_failures"], e["dep_failures"], "n")
                    + td(f'<span class="u">{N(e["user_errors"])}</span>' if e["user_errors"] else "0", e["user_errors"], e["user_errors"], "n")
                    + td(nw(", ".join(e["apps"])) if e["apps"] else NIL, ", ".join(e["apps"]), cls="c-d") + "</tr>")
    tipos = sorted({e["reason_es"] for e in events})
    out.append(section("events", "Reconfigurations and user errors", "Each reconfiguration drops connections for a few seconds; the red number shows how many errors users saw.",
                       body + dtable("sqlmi-reconfigurations", "Reconfigurations", [("Date (local time)", ""), ("Instance", ""), ("Type", ""), ("Duration", "n"),
                                     ("In window?", ""), ("Transient SQL failures", "n"), ("User errors", "n"), ("Applications", "")], rows,
                                     fselect("type", "Type", [(t, sum(1 for e in events if e["reason_es"] == t)) for t in tipos]),
                                     empty="No reconfigurations in the analyzed period.")))

    # Applications: bar = SQL transient failures, coloured part = the ones users saw
    body = ""
    if apps:
        top = max([max(a["dep_failures"], a["user_errors"]) for a in apps] + [1])
        body = ('<div class="grid2"><div class="card"><h3>User errors versus SQL failures</h3><p class="sub">Gray bar = transient SQL failures during '
                'reconfigurations; colored segment = the ones that reached users.</p><div class="bars">'
                + "".join(f'<div class="brow"><span class="bl" title="{E(a["app"])}">{E(a["app"])}</span><span class="bt"><i style="width:{100 * a["dep_failures"] / top:.1f}%"></i>'
                          f'<i style="width:{100 * a["user_errors"] / top:.1f}%;background:{VT.get(a["verdict"], ("", "#98a2b3"))[1]}"></i></span>'
                          f'<b>{N(a["user_errors"])} <small>of {N(a["dep_failures"])}</small></b></div>' for a in apps)
                + '</div></div><div class="card"><h3>How to read the verdict</h3><p class="sub">Ratio = user errors (HTTP 5xx requests) ÷ transient SQL '
                'failures during the reconfiguration.</p><ul class="lg">'
                f'<li>{pill("No retries", "crit")}<span>Ratio ≥ 0.5: the error reaches the user.</span></li>'
                f'<li>{pill("Partial", "med")}<span>Between 0.05 and 0.5: it retries on some paths, not on all of them.</span></li>'
                f'<li>{pill("Resilient", "ok")}<span>Ratio &lt; 0.05: the application absorbs the reconfiguration.</span></li>'
                f'<li>{pill("No impact observed", "neu")}<span>No transient SQL failures during the reconfigurations.</span></li></ul></div></div>'
                '<div style="height:16px"></div>')
    rows = []
    for a in apps:
        rows.append(f'<tr data-ver="{E(a["verdict"])}">' + td(f'<b class="nw">{E(a["app"])}</b>', a["app"]) + td(nw(", ".join(a["mis"])), ", ".join(a["mis"]))
                    + "".join(td(N(a[k]), a[k], a[k], "n") for k in ("sql_calls", "events", "dep_failures"))
                    + td(f'<span class="u">{N(a["user_errors"])}</span>' if a["user_errors"] else "0", a["user_errors"], a["user_errors"], "n")
                    + (td(E(a["ratio"]), a["ratio"], a["ratio"], "n") if a["ratio"] is not None else td(NIL, "—", -1, "n"))
                    + td(pill(a["verdict"], VT.get(a["verdict"], ("neu",))[0]), a["verdict"], ORDER.get(a["verdict"], 9))
                    + td(E(a["codes"]) if a["codes"] else NIL, a["codes"] or "—", cls="c-c") + "</tr>")
    out.append(section("applications", "Applications: do they absorb the reconfiguration?", "Same reconfigurations, different outcome: retries make the difference.",
                       body + dtable("sqlmi-applications", "Applications", [("Application", ""), ("Instances", ""), ("SQL calls", "n"), ("Affected reconfig.", "n"),
                                     ("Transient SQL failures", "n"), ("User errors", "n"), ("Ratio", "n"), ("Verdict", ""), ("Codes", "")], rows,
                                     fselect("ver", "Verdict", [(v, sum(1 for a in apps if a["verdict"] == v)) for v in ORDER if any(a["verdict"] == v for a in apps)]),
                                     empty="No applications with SQL telemetry in the period.")))

    # Real load vs. maintenance windows
    cards = []
    for i in insts:
        hm = heat.get(i["name"])
        if not hm or i.get("fog_role") == "Secondary":
            continue
        peak = max(max(r) for r in hm) or 1
        cw = WINDOW_CELLS.get(i["window"], set())
        rw = WINDOW_CELLS.get(i["recommended"], set()) if i["recommended"] and i["recommended"] != i["window"] else set()
        cells = ['<span class="lab"></span>'] + [f'<span class="lab">{hh}</span>' for hh in range(24)]
        for d_ in range(7):
            cells.append(f'<span class="lab d">{DIAS[d_]}</span>')
            for hh in range(24):
                cls = " ".join(c for c, on in (("w", (d_, hh) in cw), ("r", (d_, hh) in rw)) if on)
                ca = f' class="{cls}"' if cls else ""
                cells.append(f'<span{ca} style="background-color:rgba(0,75,147,{0.06 + 0.94 * hm[d_][hh] / peak:.2f})" '
                             f'title="{DIAS[d_]} {hh:02d}:00 · {hm[d_][hh]:,.0f}"></span>')
        sc = {w: s for w, s in i["scores"].items() if s is not None}
        best = min(sc, key=sc.get) if sc else None
        score = " · ".join(f"<b>{E(WINDOWS[w].split(' · ')[0])} {s}</b>" if w == best else f"{E(WINDOWS[w].split(' · ')[0])} {s}" for w, s in sc.items())
        cards.append(f'<div class="card hm-card"><h3>{E(i["name"])}</h3><div class="hm-meta"><span>Source: <b>{E(heat_src.get(i["name"], "—"))}</b></span>'
                     f'<span>Current: <b>{E(WINDOWS[i["window"]])}</b></span>' + (f'<span>Recommended: <b>{E(WINDOWS[i["recommended"]])}</b></span>' if rw else "")
                     + (f'<span>Batch <b>{E(i["batch_label"])}</b></span>' if i["batch_label"] else "")
                     + f'</div><div class="hm-scroll"><div class="hm" role="img" aria-label="Average load by day and local hour for {E(i["name"])}; current window {E(WINDOWS[i["window"]])}'
                     + (f'; recommended {E(WINDOWS[i["recommended"]])}' if rw else "") + '">' + "".join(cells) + '</div></div><div class="scale"><span><i class="ramp"></i>less → more load</span>'
                     '<span><i class="w" style="background-color:#7fa5cc"></i>current window</span><span><i class="r"></i>recommended window</span></div>'
                     + (f'<p class="note">Score (lower = better): {score}</p>' if score else "") + "</div>")
    out.append(section("load", "Real load vs. maintenance windows", "Average load by day and local hour: the best window falls where the load is lowest.",
                       f'<div class="hm-grid">{"".join(cards)}</div>' if cards else '<div class="card"><p class="empty">No hourly load data for these instances.</p></div>'))

    out.append(section("azure", "What Azure allows, what it does not and what to do", "The platform limits, and the order of the measures that do depend on you.",
                       '<div class="grid3 az">'
                       '<div class="card"><h3>What Azure allows</h3><ul><li>3 windows: default (17:00–08:00), weekday (Mon–Thu 22:00–06:00) and '
                       'weekend (Fri–Sun 22:00–06:00), in the local time of the region.</li><li>Notice 24 h before, at the start and at the end through '
                       'Service Health alerts.</li><li>Different windows on the primary and the secondary of a failover group.</li><li>Redirect connection type (fewer '
                       'disconnections from gateway maintenance).</li><li>Manual failover for drills (max. 1 every 15 min).</li></ul></div>'
                       '<div class="card"><h3>What Azure does not allow</h3><ul class="no"><li>Choosing an exact day and hour, or custom windows as on-premises.</li>'
                       '<li>Postponing or canceling a specific maintenance.</li><li>Avoiding unplanned events (hardware, network) or critical updates '
                       'that can be applied outside the window.</li><li>A reconfiguration without disconnection: it always drops connections for a few seconds.</li></ul></div>'
                       '<div class="card"><h3>What to do (in this order)</h3><ol><li><b>Retries</b> with backoff in every application: they remove the '
                       'impact of planned and unplanned events.</li><li>Maintenance alert + communication to the business.</li><li>Weekday or '
                       'weekend window based on the real load; different windows in the failover group.</li><li>Redirect instead of Proxy.</li>'
                       '<li>Quarterly drill in pre-production with a manual failover.</li></ol></div></div>'))
    STT = {"ok": "ok", "partial": "med", "error": "crit"}
    out.append(section("sources", "Sources and coverage", "What was queried and with what result. All queries are read-only and use the agent's identity.",
                       '<div class="card flat"><div class="wrap" role="region" tabindex="0" aria-label="Table: Sources and coverage" style="border-top:0"><table><thead><tr>'
                       + "".join(f'<th scope="col"><span class="th">{h}</span></th>' for h in ("Source", "Status", "Detail")) + "</tr></thead><tbody>"
                       + "".join(f'<tr><td>{E(s["source"])}</td><td>{pill(s["status"], STT.get(s["status"], "neu"))}</td><td>{E(s["detail"]) or NIL}</td></tr>' for s in sources)
                       + "</tbody></table></div></div>"))
    LEARN = "https://learn.microsoft.com/azure/azure-sql/managed-instance/"
    refs = [("Maintenance window (SQL MI)", LEARN + "maintenance-window"), ("Advance notifications", LEARN + "advance-notifications"),
            ("Connection types", LEARN + "connection-types-overview"),
            ("Configurable retry logic (SqlClient)", "https://learn.microsoft.com/sql/connect/ado-net/configurable-retry-logic")]
    out.append(f'</div></main><footer><p>Read-only report generated by Azure SRE Agent · tool generate-sqlmi-maintenance-report v1.0 · {stamp_utc} UTC.</p>'
               '<p>References: Microsoft Learn — ' + ", ".join(f'<a href="{u}" target="_blank" rel="noopener noreferrer">{t}</a>' for t, u in refs)
               + f'.</p></footer><script>{JS}</script></body></html>')
    html_doc = "".join(out)

    # ==== Outputs ======================================================================================
    base_name = f"sqlmi-maintenance-{stamp}"
    files = {}
    try:
        p = cwd / f"{base_name}.html"
        p.write_text(html_doc, encoding="utf-8")
        files["html"] = file_url(p.name)
        report = {"generated_utc": now_utc.isoformat(), "mode": MODE, "period": period_label, "kpis": kpis, "answer": answer,
                  "findings": findings, "apps": apps,
                  "instances": [{k: v for k, v in i.items() if k != "batch"} for i in insts],
                  "events": [{k: v for k, v in e.items() if k != "_t"} for e in events], "upcoming": raw["upcoming"],
                  "alerts": raw["alerts"], "sources": sources, "raw": raw}
        p = cwd / f"{base_name}.json"
        p.write_text(json.dumps(report, ensure_ascii=False, separators=(",", ":"), default=str), encoding="utf-8")
        files["json"] = file_url(p.name)
        buf = io.StringIO()
        w = csv.writer(buf, delimiter=";")
        w.writerow(["instance", "region", "tier", "vcores", "environment", "current_window", "maintenance_configuration_id", "connection_type",
                    "failover_group", "failover_role", "recommended_window", "recommended_maintenance_configuration_id",
                    "user_errors_planned", "user_errors_estimated"])
        for i in insts:
            w.writerow([i["name"], i["location"], i["tier"], i["vcores"], i["env"], i["window"], i["cfg_id"] or "SQL_Default", i["proxy"],
                        i.get("fog") or "", i.get("fog_role") or "", i["recommended"] or "", i["recommended_id"] or "",
                        i["user_errors_planned"], i["user_errors_est"]])
        p = cwd / f"{base_name}-instances.csv"
        p.write_text("\ufeff" + buf.getvalue(), encoding="utf-8")
        files["csv_instances"] = file_url(p.name)
        buf = io.StringIO()
        w = csv.writer(buf, delimiter=";")
        cols = ["event_local", "event_utc", "managed_instance", "reason", "duration_s", "app", "sql_dependency_failures", "user_errors"]
        w.writerow(cols)
        for r in impact:
            w.writerow([r[c] for c in cols])
        p = cwd / f"{base_name}-impact.csv"
        p.write_text("\ufeff" + buf.getvalue(), encoding="utf-8")
        files["csv_impact"] = file_url(p.name)
    except Exception as e:
        return {"status": "error", "mode": MODE, "message": f"Could not write the files: {e}", "kpis": kpis}

    return {
        "status": "ok",
        "mode": MODE,
        "period": period_label,
        "files": files,
        "kpis": kpis,
        "answer": answer,
        "top_actions": [{k: f[k] for k in ("severity", "title", "scope", "action", "command")} for f in findings[:6]],
        "next_maintenance": nxt and {"tracking_id": nxt["tracking_id"], "start_local": fmt_local(parse_dt(nxt["start"])),
                                     "impacted": nxt["impacted"]},
        "message": ("DEMO MODE (simulated data). " if MODE == "demo" else "")
                   + f"Report ready: [Open HTML report]({files['html']}) · [JSON]({files['json']}) · "
                     f"[Instances CSV]({files['csv_instances']}) · [Impact CSV]({files['csv_impact']})",
    }

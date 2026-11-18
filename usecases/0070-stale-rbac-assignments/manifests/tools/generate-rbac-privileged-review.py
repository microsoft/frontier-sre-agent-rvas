# generate-rbac-privileged-review
# Python tool for Azure SRE Agent: Azure RBAC privileged access review
# (Owner, User Access Administrator, Contributor and administrative roles).
# READ ONLY. The SRE Agent managed identity needs:
#   - Azure RBAC: Reader on every reviewed subscription.
#   - Microsoft Graph (application permissions): User.Read.All, Application.Read.All,
#     GroupMember.Read.All and AuditLog.Read.All (the last one for sign-in activity).
# It never creates, modifies or deletes any role assignment.
# BEFORE PASTING IT into the Code tab, replace <YOUR_AGENT_CLIENT_ID> and <YOUR_SUBSCRIPTION_ID>
# (Step 4 of the guide). A Client ID or a Subscription ID is not a secret.
# Version 1.0 - November 2026
def main() -> dict:
    """Read-only privileged Azure RBAC access review: orphaned, redundant and individual-review assignments."""
    import base64
    import csv
    import fnmatch
    import html
    import io
    import json
    import os
    import re
    import time
    from collections import Counter, defaultdict
    from datetime import datetime, timezone
    from pathlib import Path
    from urllib.parse import quote
    import requests

    # ------------------------------------------------------------------
    # REQUIRED CONFIGURATION
    # Client ID of YOUR SRE Agent's (user-assigned) managed identity
    # and the list of subscriptions to review.
    # ------------------------------------------------------------------
    MANAGED_IDENTITY_CLIENT_ID = "<YOUR_AGENT_CLIENT_ID>"
    SUBSCRIPTION_IDS = ["<YOUR_SUBSCRIPTION_ID>"]
    # ------------------------------------------------------------------
    # OPTIONAL CONFIGURATION
    # ------------------------------------------------------------------
    STALE_SIGNIN_DAYS = 90       # no sign-in in N days = "unused"
    LARGE_GROUP_MEMBERS = 25     # groups with more members = "large group"
    ORGANIZATION_NAME = ""       # optional: shown in the report title, footer and JSON when set
    LOGO_DATA_URI = ""  # optional: data:image/png;base64,... of your organization logo

    ARM = "https://management.azure.com"
    GRAPH = "https://graph.microsoft.com"
    MICROSOFT_TENANTS = {
        "f8cdef31-a31e-4b4a-93e4-5f571e91255a",
        "72f988bf-86f1-41af-91ab-2d7cd011db47",
    }

    def fail(message: str) -> dict:
        return {"status": "error", "error": message}

    if not MANAGED_IDENTITY_CLIENT_ID or MANAGED_IDENTITY_CLIENT_ID.startswith("<"):
        return fail("Configuration required: MANAGED_IDENTITY_CLIENT_ID must be the Client ID "
                    "of your Azure SRE Agent managed identity.")
    subscriptions = [s.strip() for s in SUBSCRIPTION_IDS if s and not s.strip().startswith("<")]
    if not subscriptions:
        return fail("Configuration required: SUBSCRIPTION_IDS must contain at least one subscription.")

    try:
        from azure.identity import ManagedIdentityCredential
        credential = ManagedIdentityCredential(client_id=MANAGED_IDENTITY_CLIENT_ID)
        arm_token = credential.get_token(ARM + "/.default").token
    except Exception as exc:
        return fail(f"Could not get an Azure Resource Manager token: {type(exc).__name__}")
    graph_token, graph_token_error = None, None
    try:
        graph_token = credential.get_token(GRAPH + "/.default").token
    except Exception as exc:
        graph_token_error = type(exc).__name__

    def claim(token: str, key: str):
        try:
            part = token.split(".")[1]
            part += "=" * (-len(part) % 4)
            return json.loads(base64.urlsafe_b64decode(part)).get(key)
        except Exception:
            return None

    tenant_id = (claim(arm_token, "tid") or "").lower()
    now = datetime.now(timezone.utc)
    reference_iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    report_date = now.strftime("%Y-%m-%d")
    org_name = (ORGANIZATION_NAME or "").strip()

    arm = requests.Session()
    arm.headers.update({"Authorization": "Bearer " + arm_token, "Accept": "application/json"})

    def arm_list(url: str):
        items, next_url = [], url
        while next_url:
            for attempt in range(3):
                r = arm.get(next_url, timeout=90)
                if r.status_code == 429 and attempt < 2:
                    time.sleep(min(int(r.headers.get("Retry-After", "5") or 5), 20))
                    continue
                break
            if r.status_code in (401, 403):
                return items, "denied", r.status_code
            if not r.ok:
                return items, "error", r.status_code
            body = r.json()
            items.extend(body.get("value", []))
            next_url = body.get("nextLink")
        return items, "ok", 200

    def parse_dt(value):
        if not value:
            return None
        text = str(value).strip().replace("Z", "+00:00")
        m = re.match(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(\.\d+)?(.*)$", text)
        if m:
            text = m.group(1) + (m.group(2)[:7] if m.group(2) else "") + m.group(3)
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            try:
                dt = datetime.fromisoformat(text[:19])
            except ValueError:
                return None
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

    # ------------------------------------------------------------------
    # 1) Azure Resource Manager: assignments, definitions and PIM
    # ------------------------------------------------------------------
    assignments = {}
    role_defs = {}
    pim_active = {}
    pim_eligible = []
    sub_coverage = []
    mg_ancestors = defaultdict(set)
    sub_names = {}
    for sub in subscriptions:
        cov = {"subscription_id": sub, "name": sub}
        r = arm.get(f"{ARM}/subscriptions/{sub}?api-version=2022-12-01", timeout=60)
        if r.ok:
            sub_names[sub.lower()] = r.json().get("displayName") or sub
            cov["name"] = sub_names[sub.lower()]
            cov["state"] = r.json().get("state")
        else:
            cov["state"] = f"HTTP {r.status_code}"
        ra, st, code = arm_list(f"{ARM}/subscriptions/{sub}/providers/Microsoft.Authorization/roleAssignments?api-version=2022-04-01")
        cov["role_assignments"] = {"status": st, "http": code, "count": len(ra)}
        for a in ra:
            assignments.setdefault(a["id"].lower(), a)
            scope = (a.get("properties", {}).get("scope") or "").lower()
            if scope.startswith("/providers/microsoft.management/managementgroups/"):
                mg_ancestors[sub.lower()].add(scope)
        rd, st, code = arm_list(f"{ARM}/subscriptions/{sub}/providers/Microsoft.Authorization/roleDefinitions?api-version=2022-04-01")
        cov["role_definitions"] = {"status": st, "http": code, "count": len(rd)}
        for d in rd:
            role_defs.setdefault(d["name"].lower(), d)
        pa, st, code = arm_list(f"{ARM}/subscriptions/{sub}/providers/Microsoft.Authorization/roleAssignmentScheduleInstances?api-version=2020-10-01")
        cov["pim_active"] = {"status": st, "http": code, "count": len(pa)}
        for p in pa:
            pp = p.get("properties", {})
            origin = (pp.get("originRoleAssignmentId") or "").lower()
            if origin:
                pim_active[origin] = pp
        pe, st, code = arm_list(f"{ARM}/subscriptions/{sub}/providers/Microsoft.Authorization/roleEligibilityScheduleInstances?api-version=2020-10-01")
        cov["pim_eligible"] = {"status": st, "http": code, "count": len(pe)}
        pim_eligible.extend(pe)
        sub_coverage.append(cov)

    readable = [c for c in sub_coverage if c["role_assignments"]["status"] == "ok"]
    if not readable:
        return fail("No subscription is readable (role assignments denied or failed). "
                    "Assign Reader to the agent identity on the configured subscriptions.")

    # ------------------------------------------------------------------
    # 2) Role classification by privilege tier
    # ------------------------------------------------------------------
    def perm_blocks(defn):
        return (defn or {}).get("properties", {}).get("permissions", []) or []

    def op_allowed(defn, op, data=False):
        op = op.lower()
        for block in perm_blocks(defn):
            acts = [x.lower() for x in (block.get("dataActions" if data else "actions") or [])]
            nots = [x.lower() for x in (block.get("notDataActions" if data else "notActions") or [])]
            if any(fnmatch.fnmatchcase(op, p) for p in acts) and not any(
                    fnmatch.fnmatchcase(op, n) or fnmatch.fnmatchcase(n, op) for n in nots):
                return True
        return False

    def actions_of(defn, data=False):
        out = []
        for block in perm_blocks(defn):
            out.extend(block.get("dataActions" if data else "actions") or [])
        return out

    tier_cache = {}

    def tier_of(defn):
        key = (defn or {}).get("name", "").lower()
        if key in tier_cache:
            return tier_cache[key]
        name = (defn or {}).get("properties", {}).get("roleName", "")
        if op_allowed(defn, "Microsoft.Authorization/roleAssignments/write"):
            tier = 0
        elif "*" in actions_of(defn):
            tier = 1
        elif re.search(r"admin|owner", name, re.I):
            tier = 2
        else:
            tier = None
        tier_cache[key] = tier
        return tier

    def covers(parent, child):
        if parent is None or child is None:
            return False
        if parent.get("name", "").lower() == child.get("name", "").lower():
            return True
        for a in actions_of(child):
            if not op_allowed(parent, a):
                return False
        for a in actions_of(child, data=True):
            if not op_allowed(parent, a, data=True):
                return False
        return True

    TIER_LABEL = {0: "Tier 0 · Access control", 1: "Tier 1 · Full control", 2: "Tier 2 · Service admin"}

    # ------------------------------------------------------------------
    # 3) Assignment normalization
    # ------------------------------------------------------------------
    def scope_info(scope):
        s = (scope or "").rstrip("/")
        low = s.lower()
        if low in ("", "/"):
            return "Root (/)", "Tenant root", None
        m = re.match(r"^/providers/microsoft\.management/managementgroups/([^/]+)$", low)
        if m:
            mg = s.split("/")[-1]
            label = "Root management group" if mg.lower() == tenant_id else f"Management Group {mg}"
            return "Management Group", label, None
        m = re.match(r"^/subscriptions/([^/]+)(/resourcegroups/([^/]+))?(/providers/.+)?$", low)
        if not m:
            return "Other", s, None
        sub = m.group(1)
        sub_label = sub_names.get(sub, sub)
        if m.group(4):
            parts = s.split("/")
            return "Resource", f"{parts[-2]}/{parts[-1]} · {s.split('/')[4] if m.group(2) else sub_label}", sub
        if m.group(2):
            return "Resource group", s.split("/")[4], sub
        return "Subscription", sub_label, sub

    def is_ancestor(parent_scope, child_scope, child_sub):
        p, c = parent_scope.rstrip("/").lower(), child_scope.rstrip("/").lower()
        if p == c:
            return False
        if p in ("", "/"):
            return True
        if p.startswith("/providers/microsoft.management/managementgroups/"):
            if c.startswith("/subscriptions/") and child_sub:
                return p in mg_ancestors.get(child_sub, set())
            return False
        return c.startswith(p + "/")

    raw_rows = []
    for aid, a in assignments.items():
        p = a.get("properties", {})
        role_guid = (p.get("roleDefinitionId") or "").split("/")[-1].lower()
        defn = role_defs.get(role_guid)
        level, scope_label, sub = scope_info(p.get("scope"))
        pim = pim_active.get(aid)
        end = parse_dt((pim or {}).get("endDateTime"))
        if pim and (pim.get("assignmentType") == "Activated"):
            access = "PIM activation"
        elif end:
            access = "Time-bound"
        else:
            access = "Permanent"
        raw_rows.append({
            "id": a["id"],
            "assignment_name": a.get("name"),
            "scope": p.get("scope"),
            "scope_level": level,
            "scope_label": scope_label,
            "subscription_id": sub,
            "role_id": role_guid,
            "role": (defn or {}).get("properties", {}).get("roleName") or f"Role {role_guid[:8]}",
            "role_type": (defn or {}).get("properties", {}).get("type") or "Unknown",
            "tier": tier_of(defn) if defn else None,
            "principal_id": p.get("principalId"),
            "principal_arm_type": p.get("principalType") or "Unknown",
            "condition": bool(p.get("condition")),
            "created_on": p.get("createdOn"),
            "access": access,
            "end_date": end.strftime("%Y-%m-%d") if end else None,
            "pim_name": (((pim or {}).get("expandedProperties") or {}).get("principal") or {}).get("displayName"),
            "_defn": defn,
        })

    privileged = [r for r in raw_rows if r["tier"] is not None]

    # ------------------------------------------------------------------
    # 4) Microsoft Graph: identity resolution (batches of 20)
    # ------------------------------------------------------------------
    graph = requests.Session()
    if graph_token:
        graph.headers.update({"Authorization": "Bearer " + graph_token, "Content-Type": "application/json"})

    def graph_batch(reqs, version="v1.0"):
        results = {}
        for i in range(0, len(reqs), 20):
            chunk = reqs[i:i + 20]
            pending = chunk
            for attempt in range(3):
                r = graph.post(f"{GRAPH}/{version}/$batch", json={"requests": pending}, timeout=90)
                if not r.ok:
                    for q in pending:
                        results[q["id"]] = (r.status_code, None)
                    break
                retry, wait = [], 0
                for resp in r.json().get("responses", []):
                    if resp.get("status") == 429 and attempt < 2:
                        retry.append(next(q for q in pending if q["id"] == resp["id"]))
                        wait = max(wait, int((resp.get("headers") or {}).get("Retry-After", "3") or 3))
                    else:
                        results[resp["id"]] = (resp.get("status"), resp.get("body"))
                if not retry:
                    break
                pending = retry
                time.sleep(min(wait, 15))
        return results

    principal_types = {}
    for r in privileged:
        principal_types[r["principal_id"]] = r["principal_arm_type"]
    principals = {}
    graph_stats = defaultdict(Counter)
    signin_user_status = "not evaluated"
    signin_sp_status = "not evaluated"
    membership_status = "not evaluated"

    if graph_token:
        user_sel = "id,displayName,userPrincipalName,userType,accountEnabled,createdDateTime,signInActivity"
        reqs = []
        for pid, ptype in principal_types.items():
            if ptype == "User":
                url = f"/users/{pid}?$select={user_sel}"
            elif ptype == "ServicePrincipal":
                url = f"/servicePrincipals/{pid}?$select=id,displayName,appId,servicePrincipalType,appOwnerOrganizationId,accountEnabled"
            elif ptype == "Group":
                url = f"/groups/{pid}?$select=id,displayName,securityEnabled,isAssignableToRole"
            else:
                url = f"/directoryObjects/{pid}"
            reqs.append({"id": pid, "method": "GET", "url": url})
        res = graph_batch(reqs)
        users_retry = [pid for pid, (st, _) in res.items() if st == 403 and principal_types.get(pid) == "User"]
        if users_retry:
            signin_user_status = "denied (AuditLog.Read.All)"
            res.update(graph_batch([{"id": pid, "method": "GET",
                                     "url": f"/users/{pid}?$select=id,displayName,userPrincipalName,userType,accountEnabled,createdDateTime"}
                                    for pid in users_retry]))
        elif any(t == "User" for t in principal_types.values()):
            signin_user_status = "ok"
        for pid, ptype in principal_types.items():
            st, body = res.get(pid, (None, None))
            kind = {"User": "Users", "ServicePrincipal": "Apps and identities", "Group": "Groups"}.get(ptype, "Other")
            if st == 200 and isinstance(body, dict):
                principals[pid] = {"status": "ok", **body}
                graph_stats[kind]["resolved"] += 1
            elif st == 404:
                principals[pid] = {"status": "orphan"}
                graph_stats[kind]["orphaned"] += 1
            elif st in (401, 403):
                principals[pid] = {"status": "denied"}
                graph_stats[kind]["denied"] += 1
            else:
                principals[pid] = {"status": "error", "http": st}
                graph_stats[kind]["error"] += 1

        groups_ok = [pid for pid, ptype in principal_types.items() if ptype == "Group" and principals.get(pid, {}).get("status") == "ok"]
        if groups_ok:
            cres = graph_batch([{"id": pid, "method": "GET", "url": f"/groups/{pid}/transitiveMembers/$count",
                                 "headers": {"ConsistencyLevel": "eventual"}} for pid in groups_ok])
            for pid in groups_ok:
                st, body = cres.get(pid, (None, None))
                if st == 200:
                    try:
                        principals[pid]["member_count"] = int(body if not isinstance(body, str) else body.strip())
                    except Exception:
                        try:
                            principals[pid]["member_count"] = int(base64.b64decode(body).decode().strip())
                        except Exception:
                            pass
        if any(principals.get(pid, {}).get("status") == "denied" for pid, t in principal_types.items() if t == "Group"):
            membership_status = "denied (GroupMember.Read.All)"

        sp_apps = {}
        for r in privileged:
            pr = principals.get(r["principal_id"], {})
            if r["principal_arm_type"] == "ServicePrincipal" and pr.get("status") == "ok" and pr.get("appId") and r["tier"] in (0, 1):
                sp_apps[r["principal_id"]] = pr["appId"]
        if sp_apps:
            sres = graph_batch([{"id": pid, "method": "GET",
                                 "url": "/reports/servicePrincipalSignInActivities?$filter=" + quote(f"appId eq '{app}'", safe="'=")}
                                for pid, app in sp_apps.items()], version="beta")
            codes = Counter(st for st, _ in sres.values())
            if codes.get(200):
                signin_sp_status = "ok" if len(codes) == 1 else "partial"
            elif codes:
                signin_sp_status = f"unavailable (HTTP {max(codes, key=codes.get)})"
            for pid, (st, body) in sres.items():
                if st == 200 and isinstance(body, dict):
                    vals = body.get("value") or []
                    last = None
                    if vals:
                        last = ((vals[0].get("lastSignInActivity") or {}).get("lastSignInDateTime"))
                    principals[pid]["sp_last_sign_in"] = last
                    principals[pid]["sp_signin_known"] = True

        group_priv = defaultdict(list)
        for r in privileged:
            if r["principal_arm_type"] == "Group":
                group_priv[r["principal_id"]].append(r)
        user_groups = {}
        priv_users = {r["principal_id"] for r in privileged if r["principal_arm_type"] == "User"
                      and principals.get(r["principal_id"], {}).get("status") == "ok"}
        if group_priv and priv_users:
            mres = graph_batch([{"id": pid, "method": "GET",
                                 "url": f"/users/{pid}/transitiveMemberOf/microsoft.graph.group?$select=id&$top=999"}
                                for pid in priv_users])
            codes = Counter(st for st, _ in mres.values())
            membership_status = "ok" if codes.get(200) and len(codes) == 1 else (
                "partial" if codes.get(200) else f"denied (HTTP {max(codes, key=codes.get) if codes else '-'})")
            for pid, (st, body) in mres.items():
                if st == 200 and isinstance(body, dict):
                    user_groups[pid] = {g.get("id") for g in body.get("value", [])}
        elif not group_priv:
            membership_status = "no privileged groups"
    else:
        user_groups, group_priv = {}, {}

    # ------------------------------------------------------------------
    # 5) Decision per assignment
    # ------------------------------------------------------------------
    TYPE_LABEL = {"User": "User", "Group": "Group", "ServicePrincipal": "Application",
                  "ForeignGroup": "External group", "Device": "Device", "Unknown": "Unknown"}
    FLAG_LABEL = {
        "human_standing": "User with standing privilege (no PIM)",
        "nonhuman_tier0": "Non-human identity that can grant access",
        "owner_equivalent": "Contributor + access delegation = Owner equivalent",
        "unconditioned_delegation": "Access delegation without condition",
        "stale": f"No sign-in for more than {STALE_SIGNIN_DAYS} days",
        "disabled": "Disabled account",
        "guest": "Guest user (B2B)",
        "external_sp": "Application from another tenant",
        "large_group": f"Group with more than {LARGE_GROUP_MEMBERS} members",
        "broad_scope": "Management Group or subscription scope",
        "unresolved": "Unresolved identity (Graph permissions)",
    }
    FLAG_ACTION = {
        "disabled": "Remove: the account is disabled.",
        "human_standing": "Convert to a PIM eligible assignment (JIT activation with MFA and approval).",
        "nonhuman_tier0": "Replace with a purpose-built least-privilege role (Role Designer) or constrain with a condition.",
        "owner_equivalent": "Separate duties: remove the access delegation or restrict it with a condition.",
        "unconditioned_delegation": "Add a delegation condition (allowed roles) or move to PIM.",
        "stale": "Confirm with the owner and remove if unused.",
        "guest": "Validate the guest's sponsor, need and expiration date.",
        "external_sp": "Validate the vendor and the contract that justifies the access.",
        "large_group": "Review the group membership or split it by function.",
        "broad_scope": "Reduce the scope to the required resource group.",
        "unresolved": "Grant Graph read permissions and re-run before deciding.",
    }
    FLAG_ORDER = list(FLAG_ACTION.keys())

    by_principal = defaultdict(list)
    for r in privileged:
        by_principal[r["principal_id"]].append(r)
    all_by_principal = defaultdict(list)
    for r in raw_rows:
        all_by_principal[r["principal_id"]].append(r)

    def days_since(value):
        dt = parse_dt(value)
        return (now - dt).days if dt else None

    rows = []
    for r in privileged:
        pr = principals.get(r["principal_id"], {"status": "not evaluated"})
        ptype = r["principal_arm_type"]
        type_label = TYPE_LABEL.get(ptype, ptype)
        if ptype == "ServicePrincipal" and pr.get("servicePrincipalType") == "ManagedIdentity":
            type_label = "Managed identity"
        name = pr.get("displayName") or r["pim_name"]
        detail = pr.get("userPrincipalName") or pr.get("appId") or ""
        if pr.get("status") == "orphan":
            name = name or "Deleted identity"
            detail = detail or ("objectId " + r["principal_id"])
        name = name or "Unresolved"

        last_sign_in, signin_known = None, False
        if ptype == "User" and pr.get("status") == "ok":
            sia = pr.get("signInActivity") or {}
            dates = [parse_dt(sia.get(k)) for k in ("lastSignInDateTime", "lastNonInteractiveSignInDateTime", "lastSuccessfulSignInDateTime")]
            dates = [d for d in dates if d]
            if "signInActivity" in pr:
                signin_known = True
            if dates:
                last_sign_in = max(dates).strftime("%Y-%m-%d")
        if ptype == "ServicePrincipal" and pr.get("sp_signin_known"):
            signin_known = True
            if pr.get("sp_last_sign_in"):
                last_sign_in = parse_dt(pr["sp_last_sign_in"]).strftime("%Y-%m-%d")

        decision, reason = None, ""
        if pr.get("status") == "orphan":
            decision = "orphan"
            reason = "The identity no longer exists in Microsoft Entra ID; the assignment grants access to no one."
        if decision is None:
            for parent in all_by_principal[r["principal_id"]]:
                if parent is r or parent["condition"] or parent["access"] != "Permanent":
                    continue
                if is_ancestor(parent["scope"], r["scope"], r["subscription_id"]) and covers(parent["_defn"], r["_defn"]):
                    decision = "redundant"
                    reason = f"Redundant (inherited): already receives {parent['role']} without condition from {parent['scope_label']}."
                    break
        if decision is None:
            for parent in all_by_principal[r["principal_id"]]:
                if parent is r or parent["condition"] or parent["access"] != "Permanent":
                    continue
                if parent["scope"].rstrip("/").lower() == r["scope"].rstrip("/").lower() and covers(parent["_defn"], r["_defn"]):
                    mutual = covers(r["_defn"], parent["_defn"])
                    if not mutual or r["id"].lower() > parent["id"].lower():
                        decision = "redundant"
                        reason = f"Redundant (same scope): {parent['role']} at the same scope already includes this role."
                        break
        if decision is None and ptype == "User" and r["principal_id"] in user_groups:
            for gid in user_groups[r["principal_id"]]:
                for parent in group_priv.get(gid, []):
                    if parent["condition"] or parent["access"] != "Permanent":
                        continue
                    same_or_up = parent["scope"].rstrip("/").lower() == r["scope"].rstrip("/").lower() or is_ancestor(parent["scope"], r["scope"], r["subscription_id"])
                    if same_or_up and covers(parent["_defn"], r["_defn"]):
                        gname = principals.get(gid, {}).get("displayName") or parent["pim_name"] or "a group"
                        decision = "redundant"
                        reason = f"Redundant (via group): already receives it as a member of {gname} ({parent['role']} on {parent['scope_label']})."
                        break
                if decision:
                    break

        flags = []
        tier = r["tier"]
        if pr.get("status") in ("denied", "error"):
            flags.append("unresolved")
        if ptype == "User" and tier in (0, 1) and r["access"] == "Permanent":
            flags.append("human_standing")
        if ptype == "User" and (pr.get("userType") == "Guest"):
            flags.append("guest")
        if pr.get("accountEnabled") is False:
            flags.append("disabled")
        if ptype in ("User", "ServicePrincipal") and signin_known and tier in (0, 1):
            ds = days_since(last_sign_in) if last_sign_in else None
            created_days = days_since(pr.get("createdDateTime")) if ptype == "User" else None
            if (ds is not None and ds > STALE_SIGNIN_DAYS) or (ds is None and (created_days is None or created_days > STALE_SIGNIN_DAYS)):
                flags.append("stale")
        if ptype == "ServicePrincipal" and tier == 0:
            flags.append("nonhuman_tier0")
        if tier == 0 and r["role"] != "Owner" and not r["condition"]:
            flags.append("unconditioned_delegation")
        if tier == 0 and r["role"] != "Owner":
            if any(o is not r and o["tier"] == 1 and o["scope"].rstrip("/").lower() == r["scope"].rstrip("/").lower() for o in by_principal[r["principal_id"]]):
                flags.append("owner_equivalent")
        if tier == 1:
            if any(o is not r and o["tier"] == 0 and o["role"] != "Owner" and o["scope"].rstrip("/").lower() == r["scope"].rstrip("/").lower() for o in by_principal[r["principal_id"]]):
                flags.append("owner_equivalent")
        owner_org = (pr.get("appOwnerOrganizationId") or "").lower()
        if ptype == "ServicePrincipal" and pr.get("servicePrincipalType") == "Application" and owner_org and owner_org != tenant_id and owner_org not in MICROSOFT_TENANTS:
            flags.append("external_sp")
        if ptype == "Group" and (pr.get("member_count") or 0) > LARGE_GROUP_MEMBERS:
            flags.append("large_group")
        if r["scope_level"] in ("Management Group", "Subscription", "Root (/)") and tier in (0, 1):
            flags.append("broad_scope")
        flags = [f for f in FLAG_ORDER if f in flags]

        if decision is None:
            decision = "review" if flags else "ok"
            if decision == "review":
                reason = "; ".join(FLAG_LABEL[f] for f in flags) + "."
            else:
                reason = "Scoped role, resolved identity and no risk signals."
        if decision == "orphan":
            action = "Remove the assignment (identity no longer exists). No access impact."
        elif decision == "redundant":
            action = "Remove the duplicate assignment after approval. Effective access does not change."
        elif decision == "review":
            action = " ".join(FLAG_ACTION[f] for f in flags[:2])
        else:
            action = "Keep and review in the next cycle."

        portal = f"https://portal.azure.com/#@{tenant_id}/resource{r['scope']}/users" if r["scope"] and r["scope"] != "/" else ""
        rows.append({
            "decision": decision,
            "decision_label": {"orphan": "Remove · orphaned", "redundant": "Remove · redundant",
                               "review": "Individual review", "ok": "Compliant"}[decision],
            "reason": reason,
            "action": action,
            "flags": flags,
            "flag_labels": [FLAG_LABEL[f] for f in flags],
            "role": r["role"],
            "role_type": "Custom" if r["role_type"] == "CustomRole" else "Built-in",
            "tier": tier,
            "tier_label": TIER_LABEL[tier],
            "principal_name": name,
            "principal_type": type_label,
            "principal_detail": detail,
            "principal_id": r["principal_id"],
            "principal_status": pr.get("status"),
            "scope_level": r["scope_level"],
            "scope_label": r["scope_label"],
            "scope": r["scope"],
            "subscription": sub_names.get(r["subscription_id"] or "", r["subscription_id"] or ""),
            "access": r["access"],
            "end_date": r["end_date"],
            "condition": r["condition"],
            "last_sign_in": last_sign_in,
            "created_on": (r["created_on"] or "")[:10],
            "assignment_id": r["id"],
            "portal_url": portal,
        })

    decision_rank = {"orphan": 0, "redundant": 1, "review": 2, "ok": 3}
    rows.sort(key=lambda x: (decision_rank[x["decision"]], x["tier"], x["role"], x["scope_level"], x["principal_name"].lower()))

    # ------------------------------------------------------------------
    # 6) Metrics
    # ------------------------------------------------------------------
    dec_counts = Counter(r["decision"] for r in rows)
    owner_rows = [r for r in rows if r["role"] == "Owner"]
    owner_dec = Counter(r["decision"] for r in owner_rows)
    tier_counts = Counter(r["tier"] for r in rows)
    flag_counts = Counter(f for r in rows if r["decision"] == "review" for f in r["flags"])
    levels = ["Management Group", "Subscription", "Resource group", "Resource"]
    level_matrix = {lv: Counter(r["decision"] for r in rows if r["scope_level"] == lv) for lv in levels}
    standing = sum(1 for r in rows if r["access"] == "Permanent" and r["tier"] in (0, 1))
    tier01 = sum(1 for r in rows if r["tier"] in (0, 1))
    eligible_priv = 0
    for e in pim_eligible:
        guid = ((e.get("properties") or {}).get("roleDefinitionId") or "").split("/")[-1].lower()
        if tier_of(role_defs.get(guid)) in (0, 1):
            eligible_priv += 1
    princ_counter = Counter()
    princ_meta = {}
    for r in rows:
        if r["decision"] in ("review", "ok"):
            princ_counter[r["principal_id"]] += 1
            princ_meta[r["principal_id"]] = r
    top_principals = []
    for pid, n in princ_counter.most_common(8):
        m = princ_meta[pid]
        top_principals.append({"name": m["principal_name"], "type": m["principal_type"], "count": n,
                               "tier0": sum(1 for r in rows if r["principal_id"] == pid and r["tier"] == 0 and r["decision"] in ("review", "ok"))})

    graph_denied = sum(c.get("denied", 0) + c.get("error", 0) for c in graph_stats.values())
    arm_issues = [c for c in sub_coverage if c["role_assignments"]["status"] != "ok" or c["role_definitions"]["status"] != "ok"]
    status = "complete"
    if arm_issues or graph_denied or not graph_token:
        status = "partial"
    removable = dec_counts.get("orphan", 0) + dec_counts.get("redundant", 0)

    summary = {
        "reference_utc": reference_iso,
        "subscriptions": [{"id": c["subscription_id"], "name": c["name"]} for c in sub_coverage],
        "total_role_assignments": len(raw_rows),
        "privileged_assignments": len(rows),
        "by_tier": {TIER_LABEL[k]: v for k, v in sorted(tier_counts.items())},
        "decisions": {"remove_orphaned": dec_counts.get("orphan", 0), "remove_redundant": dec_counts.get("redundant", 0),
                      "individual_review": dec_counts.get("review", 0), "compliant": dec_counts.get("ok", 0)},
        "owner": {"total": len(owner_rows), "remove_orphaned": owner_dec.get("orphan", 0),
                  "remove_redundant": owner_dec.get("redundant", 0), "individual_review": owner_dec.get("review", 0),
                  "compliant": owner_dec.get("ok", 0)},
        "removable_without_access_change": removable,
        "standing_tier01_percent": round(100 * standing / tier01) if tier01 else 0,
        "pim_eligible_privileged": eligible_priv,
        "review_signals": {FLAG_LABEL[k]: v for k, v in flag_counts.most_common()},
        "distinct_principals": len({r["principal_id"] for r in rows}),
    }
    coverage = {
        "status": status,
        "subscriptions": sub_coverage,
        "graph_token": "ok" if graph_token else f"unavailable ({graph_token_error})",
        "graph_identities": {k: dict(v) for k, v in graph_stats.items()},
        "user_sign_in_activity": signin_user_status,
        "service_principal_sign_in_activity": signin_sp_status,
        "group_membership": membership_status,
    }

    # ------------------------------------------------------------------
    # 7) Files: HTML, CSV and JSON
    # ------------------------------------------------------------------
    base = f"rbac-privileged-access-review-{report_date}"
    csv_buf = io.StringIO()
    writer = csv.writer(csv_buf)
    headers = ["decision", "reason", "recommended_action", "signals", "role", "role_type", "privilege_tier",
               "identity", "identity_type", "upn_or_appid", "principal_id", "identity_status",
               "scope_level", "scope", "subscription", "access", "end", "condition", "last_sign_in",
               "created", "assignment_id", "portal_iam"]
    writer.writerow(headers)
    for r in rows:
        writer.writerow([r["decision_label"], r["reason"], r["action"], " | ".join(r["flag_labels"]), r["role"], r["role_type"],
                         r["tier_label"], r["principal_name"], r["principal_type"], r["principal_detail"], r["principal_id"],
                         r["principal_status"], r["scope_level"], r["scope"], r["subscription"], r["access"], r["end_date"] or "",
                         "yes" if r["condition"] else "no", r["last_sign_in"] or "", r["created_on"], r["assignment_id"], r["portal_url"]])
    csv_text = "\ufeff" + csv_buf.getvalue()
    json_doc = {"report": "Azure RBAC privileged access review", "read_only": True}
    if org_name:
        json_doc["organization"] = org_name
    json_doc.update({"summary": summary, "coverage": coverage, "assignments": rows})
    json_text = json.dumps(json_doc, ensure_ascii=False, indent=2)

    def render_html(doc, logo_uri=""):
        """Self-contained HTML report built only from the JSON document (a saved JSON can be re-rendered)."""
        S, C, rows = doc["summary"], doc["coverage"], doc["assignments"]
        org = (doc.get("organization") or "").strip()

        def e(v):
            return html.escape(str(v if v is not None else ""))

        def nm(v):
            return re.sub(r"([a-z])([A-Z])", r"\1<wbr>\2", re.sub(r"([/_.@·])", r"\1<wbr>", e(v)))

        def num(v):
            return f"{v:,}" if isinstance(v, int) else e(v)

        def opts(items):
            return "".join(f"<option value='{e(v)}'>{e(t)} ({n})</option>" for v, t, n in items if n)

        def chip(t):
            s = str(t).lower()
            cls = "ok" if s in ("ok", "no privileged groups") else ("warn" if s.startswith(("partial", "not evaluated")) else "bad")
            return f"<span class='st st-{cls}'>{e(t)}</span>"

        DEC = (("orphan", "Remove · orphaned"), ("redundant", "Remove · redundant"),
               ("review", "Individual review"), ("ok", "Compliant"))
        LEVELS = ("Root (/)", "Management Group", "Subscription", "Resource group", "Resource", "Other")
        TYPES = ("User", "Group", "Application", "Managed identity", "External group", "Device", "Unknown")
        I_WARN = ("<svg viewBox='0 0 20 20' aria-hidden='true'><path d='M10 3 2 17h16L10 3Zm0 5.5v3.5m0 2.6v.1' fill='none' "
                  "stroke='currentColor' stroke-width='1.7' stroke-linecap='round' stroke-linejoin='round'/></svg>")
        total, dec = len(rows), Counter(r["decision"] for r in rows)
        removable = dec["orphan"] + dec["redundant"]
        tiers = Counter(r["tier"] for r in rows)
        own = S.get("owner") or {}
        ref = str(S.get("reference_utc") or "")
        when = (ref[:16].replace("T", " ") + " UTC") if ref else ""
        labels = {}
        for r in rows:
            labels.update(zip(r.get("flags") or [], r.get("flag_labels") or []))
        sig = Counter(f for r in rows if r["decision"] == "review" for f in r.get("flags") or [])

        gi = C.get("graph_identities") or {}
        unread = sum(v.get("denied", 0) + v.get("error", 0) for v in gi.values())
        arm_bad = [s for s in C.get("subscriptions") or [] if (s.get("role_assignments") or {}).get("status") != "ok"
                   or (s.get("role_definitions") or {}).get("status") != "ok"]
        graph_ok = str(C.get("graph_token") or "ok").startswith("ok")
        partial = C.get("status") != "complete"
        issues = []
        if arm_bad:
            issues.append(f"{len(arm_bad)} subscription{'s' if len(arm_bad) > 1 else ''} not fully readable")
        if not graph_ok:
            issues.append("Microsoft Graph unavailable, identities not resolved")
        if unread:
            issues.append(f"{unread} identit{'ies' if unread > 1 else 'y'} could not be read in Microsoft Graph")
        if partial and not issues:
            issues.append("some reads failed")
        cov_text = ("Partial coverage: " + "; ".join(issues) + ".") if partial else ""
        verdict, tone = ("Action required", "warn") if removable or dec["review"] else (
            ("Coverage incomplete", "warn") if partial else ("No action needed", "ok"))
        vline = " · ".join(t for t in (f"{removable} to remove" if removable else "",
                                      f"{dec['review']} to review" if dec["review"] else "", f"{dec['ok']} compliant") if t)

        names = [s.get("name") or s.get("id") or "" for s in S.get("subscriptions") or []]
        chips = [f"<span>Generated {e(when)}</span>",
                 f"<span>Subscriptions: {e(', '.join(names[:3]) + (f' +{len(names) - 3} more' if len(names) > 3 else ''))}</span>",
                 "<span class='on'>Live data</span>",
                 "<a class='warn' href='#coverage'>Partial coverage</a>" if partial else "<span class='on'>Full coverage</span>",
                 "<span>Managed identity · Reader + Graph read</span>"]
        seg = "".join(f"<i class='d-{k}' style='width:{100 * dec[k] / total:.3f}%' title='{e(t)}: {dec[k]}'></i>" for k, t in DEC if dec[k])
        legend = "".join(f"<span><i class='d-{k}'></i>{e(t)} <b>{dec[k]}</b></span>" for k, t in DEC)

        orem = own.get("remove_orphaned", 0) + own.get("remove_redundant", 0)
        kpis = [(own.get("total", 0), "Owner assignments analyzed", ""),
                (orem, "Owner assignments removable without access loss",
                 f"{own.get('remove_orphaned', 0)} orphaned + {own.get('remove_redundant', 0)} redundant"),
                (own.get("individual_review", 0), "Owner assignments for individual review", f"{own.get('compliant', 0)} compliant"),
                (S.get("total_role_assignments", 0), "Role assignments inventoried",
                 f"{total} privileged · {S.get('distinct_principals', 0)} identities"),
                (tiers[0], "Tier 0 · can grant access", f"Tier 1: {tiers[1]} · Tier 2: {tiers[2]}"),
                (f"{S.get('standing_tier01_percent', 0)}%", "Of tier 0/1 is standing access",
                 f"{S.get('pim_eligible_privileged', 0)} privileged PIM eligibilities")]
        kpi_html = "".join(f"<div class='kpi'><div class='v'>{num(v)}</div><div class='l'>{e(l)}</div>{f'<div class=s>{e(s)}</div>' if s else ''}</div>"
                           for v, l, s in kpis)

        level_rows = ""
        for lv in LEVELS:
            c = Counter(r["decision"] for r in rows if r["scope_level"] == lv)
            if c:
                level_rows += (f"<tr><th scope='row'>{e(lv)}</th><td class='n'>{sum(c.values())}</td>" + "".join(
                    f"<td class='n c-{k}'>{c[k]}</td>" if c[k] else "<td class='n nil'>·</td>" for k, _ in DEC) + "</tr>")

        smax = max(sig.values()) if sig else 1
        sig_html = "".join(
            f"<button type='button' class='brow' data-sig='{e(k)}'><span class='bl'>{e(labels.get(k, k))}</span>"
            f"<span class='bt'><i style='width:{max(3, 100 * v / smax):.0f}%'></i></span><b>{v}</b>"
            f"<span class='vh'>: show them in the register</span></button>"
            for k, v in sig.most_common()) or "<p class='muted'>No risk signals in the current assignments.</p>"

        held, meta = Counter(), {}
        for r in rows:
            if r["decision"] in ("review", "ok"):
                held[r["principal_id"]] += 1
                meta[r["principal_id"]] = r
        tops = held.most_common(8)
        top_html = ""
        for pid, n in tops:
            t0 = sum(1 for r in rows if r["principal_id"] == pid and r["tier"] == 0 and r["decision"] in ("review", "ok"))
            top_html += (f"<li><span class='bl'><b>{nm(meta[pid]['principal_name'])}</b> <small>{e(meta[pid]['principal_type'])} · {t0} tier 0</small></span>"
                         f"<span class='bt'><i style='width:{max(3, 100 * n / tops[0][1]):.0f}%'></i></span><b class='bv'>{n}</b></li>")
        top_html = top_html or "<li class='muted'>No identities with current privileged access.</li>"

        def go(key, n):
            return f" <a class='go' href='#register' data-go='{key}'>Show {n} in the register</a>" if n else ""

        steps = (f"<li><b>Risk-free cleanup.</b> Remove the {removable} orphaned or redundant assignments through an approved change. "
                 f"Effective access does not change.{go('remove', removable)}</li>"
                 "<li><b>Human access to PIM.</b> Convert users' standing privilege into eligibility with JIT activation, MFA and approval."
                 f"{go('sig:human_standing', sig['human_standing'])}</li>"
                 "<li><b>Non-human identities.</b> Replace Owner/UAA on applications and managed identities with least-privilege roles "
                 f"(Role Designer).{go('sig:nonhuman_tier0', sig['nonhuman_tier0'])}</li>"
                 "<li><b>Groups by function and scope.</b> Assign through groups separated by environment and subscription, never to "
                 "individual users at Management Group level.</li>"
                 "<li><b>Periodic review.</b> Schedule this monthly review in the SRE Agent and track how the indicators evolve.</li>")

        types, lvc = Counter(r["principal_type"] for r in rows), Counter(r["scope_level"] for r in rows)
        tier_lbl = {r["tier"]: r["tier_label"] for r in rows}
        cov_rows = "".join(
            f"<tr><th scope='row'>{e(s.get('name') or s.get('subscription_id'))}</th>" + "".join(
                f"<td class='nw'>{chip((s.get(k) or {}).get('status', '-'))} <span class='cv'>{num((s.get(k) or {}).get('count', 0))}</span></td>"
                for k in ("role_assignments", "role_definitions", "pim_active", "pim_eligible")) + "</tr>"
            for s in C.get("subscriptions") or [])
        graph_rows = ""
        for k in ("Users", "Groups", "Apps and identities", "Other"):
            c = gi.get(k)
            if c:
                bad = c.get("denied", 0) + c.get("error", 0)
                graph_rows += (f"<tr><th scope='row'>{e(k)}</th><td class='n'>{c.get('resolved', 0)}</td>"
                               f"<td class='n{' c-orphan' if c.get('orphaned') else ''}'>{c.get('orphaned', 0)}</td>"
                               f"<td class='n{' c-warn' if bad else ''}'>{bad}</td></tr>")
        graph_rows = graph_rows or ("<tr><td colspan='4' class='muted'>" + ("No identities to resolve." if graph_ok else
                                    "Microsoft Graph was not available: identities were not resolved.") + "</td></tr>")

        logo = (logo_uri or "").strip()
        if logo.startswith("data:image/"):
            mark = f"<img class='logo' src='{e(logo)}' alt='{e(org or 'Organization logo')}'>"
        else:
            mark = ("<span class='wm'><svg viewBox='0 0 24 24' aria-hidden='true'><path d='M9.2 3h5.6l6.2 18h-4.5l-1.5-4.6H8.4L9.9 12h3.8L12 6.6 "
                    "6.4 21H2z' fill='currentColor'/></svg><span>Azure SRE Agent</span></span>")
        ptitle = ((org + " · " if org else "") + "Azure RBAC privileged access review · " + when).replace("\n", " ")
        repl = {
            "__TITLE__": e((org + " · " if org else "") + "Azure RBAC privileged access review · " + ref[:10]),
            "__PTITLE__": '"' + ptitle.replace("\\", "\\\\").replace('"', '\\"').replace("<", "\\3c ") + '"',
            "__MARK__": mark, "__TOTAL__": str(total), "__REMOVABLE__": str(removable), "__REVIEW__": str(dec["review"]),
            "__CHIPS__": "".join(chips), "__TONE__": tone, "__VERDICT__": verdict, "__VLINE__": e(vline),
            "__VCOV__": f"<p class='cov'>{I_WARN}<span>{e(cov_text)}</span></p>" if partial else "",
            "__TRACK__": e("; ".join(f"{t}: {dec[k]}" for k, t in DEC)), "__SEG__": seg, "__LEGEND__": legend,
            "__KPIS__": kpi_html, "__SIGNALS__": sig_html, "__TOP__": top_html, "__STEPS__": steps,
            "__LEVELS__": level_rows or "<tr><td colspan='6' class='muted'>No privileged assignments.</td></tr>",
            "__F_DEC__": opts([("remove", "Remove · all", removable)] + [(k, t, dec[k]) for k, t in DEC]),
            "__F_TIER__": opts([(str(t), tier_lbl[t], tiers[t]) for t in sorted(tier_lbl)]),
            "__F_TYPE__": opts([(t, t, types[t]) for t in list(TYPES) + sorted(set(types) - set(TYPES))]),
            "__F_LVL__": opts([(x, x, lvc[x]) for x in LEVELS]),
            "__F_SIG__": opts([(k, labels.get(k, k), v) for k, v in sig.most_common()]),
            "__COVNOTE__": f"<p class='note'>{I_WARN}<span>{e(cov_text)}</span></p>" if partial else "",
            "__COV__": cov_rows, "__GRAPH__": graph_rows, "__SIU__": chip(C.get("user_sign_in_activity", "not evaluated")),
            "__SIS__": chip(C.get("service_principal_sign_in_activity", "not evaluated")),
            "__MEM__": chip(C.get("group_membership", "not evaluated")),
            "__WHEN__": e(when), "__ORG_FOOT__": (" · Internal use · " + e(org)) if org else "",
            "__DATA__": json.dumps(rows, ensure_ascii=False).replace("</", "<\\/"),
        }
        page = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; font-src data:; style-src 'unsafe-inline'; script-src 'unsafe-inline'">
<title>__TITLE__</title>
<style>
:root{--ink:#101828;--text:#1d2939;--muted:#475467;--line:#e4e7ec;--line2:#d0d5dd;--paper:#f2f4f7;--soft:#f2f4f7;--bar:#14181f;--navy:#1b2c48;
--accent:#0f6cbd;--accent2:#0b5a9e;--chart:#2d4b73;--hmuted:#c8d3e1;--hline:rgba(255,255,255,.16);
--orphan:#b42318;--orphan-bg:#fee4e2;--orphan-bar:#d92d20;--redundant:#b93815;--redundant-bg:#ffead5;--redundant-bar:#ef6820;
--review:#175cd3;--review-bg:#d1e9ff;--review-bar:#2e90fa;--ok:#067647;--ok-bg:#dcfae6;--ok-bar:#17b26a;
--shadow:0 1px 2px rgba(16,24,40,.05),0 8px 24px rgba(16,24,40,.06)}
*{box-sizing:border-box}html{scroll-padding-top:76px;scrollbar-color:#c3ccd6 var(--paper);-webkit-text-size-adjust:100%}
body{margin:0;background:var(--paper);color:var(--text);font:15px/1.5 "Segoe UI",system-ui,-apple-system,Roboto,Arial,sans-serif;font-variant-numeric:tabular-nums}
::selection{background:#cce4f6;color:var(--ink)}a{color:var(--accent);text-underline-offset:3px}button,input,select{font:inherit;color:inherit}
:focus-visible{outline:3px solid var(--accent);outline-offset:2px}.top :focus-visible,.hero :focus-visible{outline-color:#84caff}
.skip{position:absolute;left:12px;top:-80px;z-index:40;background:#fff;color:var(--ink);padding:8px 14px;border-radius:8px;font-weight:600}.skip:focus{top:10px}
.vh{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
.top{position:sticky;top:0;z-index:20;display:flex;align-items:center;gap:16px;min-height:60px;padding:10px clamp(16px,4vw,40px);background:var(--bar);color:#fff}
.brand{display:flex;align-items:center;min-width:0;color:#fff;text-decoration:none}img.logo{height:34px;width:auto;max-width:210px;display:block}
.wm{display:inline-flex;align-items:center;gap:10px;font-weight:600;font-size:17px;white-space:nowrap;color:#fff}
.wm svg{width:30px;height:30px;padding:5px;border-radius:8px;background:linear-gradient(135deg,#0f6cbd,#2899f5);flex:none}
.top nav{display:flex;gap:2px}.top nav a{color:#c6ced8;text-decoration:none;font-size:14px;font-weight:600;padding:8px 12px;border-radius:8px}
.top nav a:hover{background:rgba(255,255,255,.08);color:#fff}.acts{margin-left:auto;display:flex;align-items:center;gap:10px}
.chip{font-size:12.5px;font-weight:600;color:#c6ced8;border:1px solid #3d4651;border-radius:999px;padding:5px 11px;white-space:nowrap}
.btn{display:inline-flex;align-items:center;justify-content:center;gap:8px;min-height:40px;padding:0 16px;border-radius:10px;border:1px solid transparent;background:var(--accent);color:#fff;font-weight:600;font-size:14px;cursor:pointer;white-space:nowrap;text-decoration:none;transition:background-color .15s}
.btn:hover{background:var(--accent2)}.btn svg{width:16px;height:16px;flex:none}.btn.ghost{background:#fff;color:var(--ink);border-color:var(--line2)}.btn.ghost:hover{background:var(--soft)}
.btn.link{background:none;color:var(--accent);padding:0 10px}.btn.link:hover{text-decoration:underline}
.hero{background:linear-gradient(180deg,#243a5e,var(--navy));color:#fff;padding:clamp(28px,4.5vw,48px) clamp(16px,4vw,40px) 100px}
.hero-in{max-width:1320px;margin:0 auto;display:grid;grid-template-columns:minmax(0,1fr) 340px;gap:24px 48px;align-items:start}
.kicker{margin:0 0 10px;color:#8fc8ff;font-weight:700;font-size:12.5px;letter-spacing:.12em;text-transform:uppercase}
h1{margin:0 0 12px;font-size:clamp(30px,3.3vw,44px);line-height:1.08;font-weight:700;letter-spacing:-.015em;text-wrap:balance}
.lead{margin:0;max-width:66ch;font-size:17px;color:var(--hmuted)}.lead b{color:#fff;font-weight:600}
.meta{display:flex;flex-wrap:wrap;gap:8px;margin-top:20px}.meta>*{font-size:12.5px;padding:5px 11px;border-radius:999px;border:1px solid var(--hline);color:var(--hmuted);text-decoration:none}
.meta .on{color:#fff;font-weight:600}.meta .warn{color:#fec84b;border-color:rgba(254,200,75,.5);font-weight:600}.meta a.warn:hover{background:rgba(254,200,75,.12)}
.verdict{border-radius:16px;padding:20px 22px;background:rgba(255,255,255,.07);border:1px solid var(--hline)}.verdict .k{font-size:13px;font-weight:600;color:var(--hmuted)}
.verdict b{display:block;margin-top:2px;font-size:28px;line-height:1.15;font-weight:700}.v-warn{border-color:rgba(254,200,75,.45)}.v-warn b{color:#fec84b}
.v-ok{border-color:rgba(117,224,167,.45)}.v-ok b{color:#75e0a7}.verdict p{margin:8px 0 0;font-size:14px;color:var(--hmuted)}
.verdict p.cov{display:flex;gap:8px;padding-top:12px;margin-top:14px;border-top:1px solid var(--hline);color:#fedf89}.verdict p.cov svg{width:16px;height:16px;flex:none;margin-top:2px}
.dist{grid-column:1/-1}.dist-h{font-size:13.5px;color:var(--hmuted);margin-bottom:8px}.dist-h b{color:#fff}
.track{display:flex;gap:2px;height:14px;border-radius:999px;overflow:hidden;background:rgba(255,255,255,.12)}.track i{display:block;height:100%}
.legend{display:flex;flex-wrap:wrap;gap:6px 20px;margin-top:10px;font-size:13.5px;color:var(--hmuted)}.legend span{display:inline-flex;align-items:center;gap:7px}
.legend i{width:10px;height:10px;border-radius:3px}.legend b{color:#fff}
.d-orphan{background:var(--orphan-bar)}.d-redundant{background:var(--redundant-bar)}.d-review{background:var(--review-bar)}.d-ok{background:var(--ok-bar)}
main{padding:0 clamp(16px,4vw,40px) 8px}main>*{max-width:1320px;margin-left:auto;margin-right:auto}
.kpis{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:14px;margin-top:-60px;position:relative;z-index:2}
.kpi{background:#fff;border:1px solid var(--line);border-radius:16px;padding:16px 18px;box-shadow:var(--shadow);min-width:0}
.kpi .v{font-size:36px;line-height:1.05;font-weight:700;letter-spacing:-.02em;color:var(--ink)}.kpi .l{margin-top:8px;font-size:13.5px;line-height:1.35;font-weight:600}
.kpi .s{margin-top:4px;font-size:12.5px;color:var(--muted)}
.grid2{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;margin-top:24px}
.card{background:#fff;border:1px solid var(--line);border-radius:16px;padding:20px 22px;box-shadow:var(--shadow);min-width:0;scroll-margin-top:76px}
.card h2{margin:0 0 4px;font-size:19px;line-height:1.3;color:var(--ink)}h3{margin:0 0 4px;font-size:17px;color:var(--ink)}.sub{margin:0 0 16px;font-size:13.5px;color:var(--muted);max-width:75ch}
#register,#coverage{margin-top:44px;scroll-margin-top:76px}.sh{margin-bottom:14px}
.sh h2{margin:0;font-size:24px;line-height:1.2;letter-spacing:-.01em;color:var(--ink)}.sh h2:focus{outline:none}.sh p{margin:4px 0 0;font-size:14px;color:var(--muted);max-width:75ch}
.cn{display:inline-block;margin-left:2px;padding:0 10px;border-radius:999px;background:#e4e7ec;font-size:15px;vertical-align:3px;color:var(--text)}
.wrap{overflow-x:auto;background:linear-gradient(90deg,#fff 30%,rgba(255,255,255,0)) left/36px 100% no-repeat local,linear-gradient(270deg,#fff 30%,rgba(255,255,255,0)) right/36px 100% no-repeat local,radial-gradient(farthest-side at 0 50%,rgba(16,24,40,.16),rgba(16,24,40,0)) left/14px 100% no-repeat scroll,radial-gradient(farthest-side at 100% 50%,rgba(16,24,40,.16),rgba(16,24,40,0)) right/14px 100% no-repeat scroll}
.tbl{width:100%;border-collapse:collapse;font-size:14px}.tbl th,.tbl td{padding:9px 12px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
.tbl thead th{background:var(--soft);font-size:12px;letter-spacing:.04em;text-transform:uppercase;color:var(--ink);white-space:nowrap}.tbl tbody th{font-weight:600;color:var(--ink)}
.tbl tbody tr:last-child>*{border-bottom:0}.n{text-align:right!important;white-space:nowrap}.nw{white-space:nowrap}.nil{color:#98a2b3}
.c-orphan{color:var(--orphan);font-weight:700}.c-redundant{color:var(--redundant);font-weight:700}.c-review{color:var(--review);font-weight:700}.c-ok{color:var(--ok);font-weight:700}.c-warn{color:#b54708;font-weight:700}
.info{display:flex;gap:10px;margin:16px 0 0;padding:12px 14px;border-radius:12px;background:var(--soft);font-size:13.5px}.info svg{width:18px;height:18px;flex:none;margin-top:1px;color:var(--accent)}
.note{display:flex;gap:10px;align-items:flex-start;margin:0 0 16px;padding:12px 16px;border-radius:12px;background:#fffaeb;border:1px solid #fedf89;color:#7a2e0e;font-size:14px}.note svg{width:18px;height:18px;flex:none;margin-top:2px}
.bars{display:grid;gap:6px;margin:0;padding:0;list-style:none}
.brow,.ids li{display:grid;grid-template-columns:minmax(0,1.3fr) minmax(70px,1fr) 40px;gap:12px;align-items:center;font-size:14px}
.brow{width:calc(100% + 16px);margin:0 -8px;padding:6px 8px;border:0;border-radius:8px;background:none;text-align:left;cursor:pointer}.brow:hover{background:var(--soft)}.brow:hover .bl{text-decoration:underline;text-underline-offset:3px}
.bt{height:10px;border-radius:999px;background:#eaecf0;overflow:hidden}.bt i{display:block;height:100%;border-radius:999px;background:var(--chart)}
.brow>b,.bv{text-align:right;font-weight:700;color:var(--ink)}.ids li{padding:8px 0;border-bottom:1px solid var(--line)}.ids li:last-child{border-bottom:0}
.ids .bl b{font-weight:600;color:var(--ink);overflow-wrap:break-word}.ids small{font-size:12.5px;color:var(--muted);white-space:nowrap}
.steps{counter-reset:s;display:grid;gap:14px;margin:0;padding:0;list-style:none}.steps li{counter-increment:s;position:relative;padding-left:40px;font-size:14px}
.steps li::before{content:counter(s);position:absolute;left:0;top:-1px;width:26px;height:26px;border-radius:50%;background:#e0effc;color:#0b4f8a;font-weight:700;font-size:13px;display:grid;place-items:center}
.steps b{color:var(--ink)}.go{display:inline-block;font-weight:600;white-space:nowrap}
.flat{padding:0;overflow:hidden}.tools{display:flex;flex-wrap:wrap;gap:10px;align-items:center;padding:16px 20px}
.tools input,.tools select{min-height:40px;min-width:0;max-width:100%;border:1px solid var(--line2);border-radius:10px;padding:0 12px;background:#fff;color:var(--text)}
.tools input{flex:1 1 240px;max-width:340px}.tools select{flex:0 1 auto;min-width:150px;max-width:240px}.tools input::placeholder{color:#667085;opacity:1}
.tools input:focus,.tools select:focus{outline:none;border-color:var(--accent);box-shadow:0 0 0 3px rgba(15,108,189,.22)}
.tacts{display:flex;gap:4px;align-items:center}.cnt{margin:0 0 0 auto;font-size:13px;color:var(--muted)}.pcap{display:none}
.reg{width:100%;min-width:1000px;border-collapse:collapse;table-layout:fixed;font-size:13.5px}
.reg th{padding:0;border-bottom:1px solid var(--line);background:var(--soft);text-align:left;font-size:12px;letter-spacing:.04em;text-transform:uppercase;color:var(--ink)}
.reg th button{all:unset;box-sizing:border-box;display:flex;align-items:center;gap:7px;width:100%;padding:11px 12px;cursor:pointer}.reg th button:hover{color:var(--accent)}
.reg th button:focus-visible{outline:3px solid var(--accent);outline-offset:-3px}
.reg th button::after{content:"";width:6px;height:6px;border:solid currentColor;border-width:0 1.6px 1.6px 0;transform:translateY(-2px) rotate(45deg);opacity:0}
.reg th[aria-sort] button::after{opacity:.9}.reg th[aria-sort=ascending] button::after{transform:translateY(2px) rotate(-135deg)}.reg th.c-iam{padding:11px 12px}
.w-dec{width:160px}.w-role{width:166px}.w-id{width:25%}.w-scope{width:15%}.w-iam{width:76px}
.reg td{padding:12px;border-bottom:1px solid var(--line);vertical-align:top;line-height:1.45}.reg tr.pg{display:none}.reg tbody tr:hover{background:#f9fafb}.reg tbody tr:last-child td{border-bottom:0}
.reg b{font-weight:600;color:var(--ink)}.sm{display:block;margin-top:2px;font-size:12.5px;color:var(--muted)}.nm{overflow-wrap:break-word}
.id{font-family:ui-monospace,"Cascadia Mono",Consolas,monospace;font-size:11.5px;white-space:nowrap}
.pill{display:inline-flex;align-items:center;gap:6px;padding:3px 10px 3px 8px;border-radius:999px;font-size:12px;font-weight:700;white-space:nowrap}.pill::before{content:"";width:7px;height:7px;border-radius:50%;background:currentColor}
.p-orphan{background:var(--orphan-bg);color:var(--orphan)}.p-redundant{background:var(--redundant-bg);color:var(--redundant)}.p-review{background:var(--review-bg);color:var(--review)}.p-ok{background:var(--ok-bg);color:var(--ok)}
.tier{display:block;width:max-content;max-width:100%;margin:4px 0 2px;padding:0 7px;border:1px solid;border-radius:6px;background:#fff;font-size:11.5px;font-weight:700;line-height:1.7}
.t0{color:var(--orphan);border-color:#fecdca}.t1{color:var(--redundant);border-color:#f9dbaf}.t2{color:#344054;border-color:var(--line2)}
.sig{display:flex;flex-wrap:wrap;gap:4px;margin:0 0 6px;padding:0;list-style:none}.sig li{padding:1px 8px;border:1px solid var(--line);border-radius:6px;background:var(--soft);font-size:12px;line-height:1.6}
.why{margin:0 0 6px}.act{margin:0;font-size:12.5px;color:var(--muted)}.act b{color:var(--text)}
.iam{display:inline-flex;align-items:center;gap:4px;font-weight:600;text-decoration:none;white-space:nowrap}.iam:hover{text-decoration:underline}.iam svg{width:14px;height:14px}
td.empty{padding:28px 16px;text-align:center;color:var(--muted)}.more{display:flex;justify-content:center;gap:8px;padding:14px;border-top:1px solid var(--line)}.more[hidden]{display:none}
.st{display:inline-block;padding:0 9px;border-radius:999px;font-size:12px;font-weight:700;line-height:1.7}.st-ok{background:var(--ok-bg);color:var(--ok)}.st-warn{background:#fef0c7;color:#93370d}.st-bad{background:var(--orphan-bg);color:var(--orphan)}
.cv{margin-left:4px;font-weight:600;color:var(--ink)}.small{margin:12px 0 0;font-size:13px;color:var(--muted)}.muted{color:var(--muted)}
.method{margin:20px 0 0;max-width:75ch;font-size:13.5px;color:var(--muted)}.method b{color:var(--text)}
footer{margin-top:48px;background:var(--bar);color:#aeb8c3;font-size:12.5px}
.fin{max-width:1400px;margin:0 auto;padding:20px clamp(16px,4vw,40px);display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px 24px}
footer img.logo{height:24px}footer .wm{font-size:14px;gap:8px}footer .wm svg{width:22px;height:22px;padding:4px;border-radius:6px}
@media screen and (max-width:1200px){.kpis{grid-template-columns:repeat(3,minmax(0,1fr))}.hero-in{grid-template-columns:minmax(0,1fr) 300px}}
@media screen and (max-width:1040px){.top nav{display:none}.hero-in{grid-template-columns:1fr}}
@media screen and (max-width:900px){.grid2{grid-template-columns:1fr}}
@media screen and (max-width:720px){.chip{display:none}.btn .lbl{display:none}.top .btn{padding:0 12px}.hero{padding-bottom:84px}.lead{font-size:16px}.verdict b{font-size:24px}
.kpis{grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin-top:-56px}.kpi{padding:14px}.kpi .v{font-size:28px}.card{padding:18px 16px}.flat{padding:0}.sh h2{font-size:21px}
.tools{display:grid;grid-template-columns:1fr 1fr;padding:14px 16px}.tools input{grid-column:1/-1;max-width:none}.tacts,.cnt{grid-column:1/-1;margin:0}
.reg{min-width:0;table-layout:auto}.reg thead{display:none}.reg,.reg tbody,.reg tr,.reg td{display:block}.reg tr{padding:14px 16px;border-bottom:1px solid var(--line)}
.reg td{padding:2px 0;border:0}.reg td:first-child{margin-bottom:6px}.reg td.lb::before{content:attr(data-h);display:block;margin-top:8px;font-size:11px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--muted)}
.reg .tier{display:inline-block;margin:0 0 0 6px}.iam{padding:8px 0}.tbl th,.tbl td{padding:8px 10px}.brow,.ids li{grid-template-columns:minmax(0,1fr) 64px 30px;gap:10px}.fin{flex-direction:column;align-items:flex-start}}
@media (prefers-reduced-motion:reduce){*{transition:none!important;scroll-behavior:auto!important}}
@page{size:A4;margin:12mm 11mm 15mm;@bottom-left{content:__PTITLE__;font:8pt "Segoe UI",system-ui,sans-serif;color:#475467}@bottom-right{content:"Page " counter(page) " of " counter(pages);font:8pt "Segoe UI",system-ui,sans-serif;color:#475467}}
@media print{*{-webkit-print-color-adjust:exact;print-color-adjust:exact}html,body{background:#fff}body{font-size:12px}
.top{position:static;min-height:0;padding:8px 16px;border-radius:12px 12px 0 0}.top nav,.top .btn,.skip,.tools,.more,.np,.go,footer{display:none!important}
.hero{padding:18px 20px 70px;border-radius:0 0 12px 12px}.hero-in{grid-template-columns:minmax(0,1fr) 210px;gap:12px 22px}h1{font-size:28px}.lead{font-size:13.5px}.kicker{font-size:10.5px}
.meta{margin-top:12px;gap:5px}.meta>*{font-size:11px;padding:2px 8px}.verdict{padding:12px 14px}.verdict b{font-size:20px}.verdict p,.dist-h,.legend{font-size:11.5px}
main{padding:0}.kpis{grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin-top:-52px;padding:0 14px}.kpi{padding:10px 12px;border-radius:12px;box-shadow:none}
.kpi .v{font-size:23px}.kpi .l{font-size:11.5px;margin-top:4px}.kpi .s{font-size:10.5px;margin-top:2px}.grid2{gap:10px;margin-top:12px}
.card{padding:12px 14px;border-radius:12px;box-shadow:none}.card h2{font-size:14.5px}h3{font-size:14px}.sub{font-size:11px;margin-bottom:8px}
#analysis{grid-template-columns:minmax(0,1.12fr) minmax(0,.88fr)}.tbl{font-size:11px}.tbl th,.tbl td{padding:4px}.tbl thead th{font-size:9px;letter-spacing:0}.info,.note{font-size:11px;padding:8px 10px;margin-top:10px}.st{font-size:10.5px}
.brow,.ids li,.steps li{font-size:11.5px}.brow,.ids li{gap:8px;grid-template-columns:minmax(0,2fr) minmax(40px,1fr) 24px}.brow{padding:2px 8px}.ids li{padding:4px 0}.ids small{font-size:10.5px}
.steps{gap:8px}.steps li{padding-left:30px}.steps li::before{width:20px;height:20px;font-size:10.5px}
.card,.kpi,.verdict,.brow,.ids li,.steps li,tr,.note,#coverage{break-inside:avoid}.flat{break-inside:auto}.sh,.card h2,h3{break-after:avoid}#register,#coverage{margin-top:18px}
.sh h2{font-size:17px}.sh p,.method,.small{font-size:11px}.method{margin-top:10px}.cn{font-size:11px}.wrap{overflow:visible;background:none}.pcap{display:block;margin:0;padding:8px 10px;font-size:10.5px;color:var(--muted)}
.reg{min-width:0;font-size:11px}.reg th{font-size:9.5px}.reg th button{display:none}.reg th[data-l]::before{content:attr(data-l);display:block;padding:5px 6px}.reg td{padding:5px 6px;line-height:1.35}.c-iam{display:none}
.w-dec{width:16%}.w-role{width:15%}.w-id{width:25%}.w-scope{width:16%}.pill{font-size:9.5px;padding:1px 6px 1px 5px;gap:3px}.pill::before{width:5px;height:5px}
.tier{font-size:9.5px;padding:0 4px}.sm,.act{font-size:10px}.sig li{font-size:9.5px;padding:0 5px}.id{font-size:9.5px;white-space:normal}tr.pg{display:table-row!important}thead{display:table-header-group}a{color:inherit;text-decoration:none}}
</style></head><body>
<a class="skip" href="#register">Skip to the register</a>
<header class="top"><a class="brand" href="#summary">__MARK__</a>
<nav aria-label="Report sections"><a href="#summary">Summary</a><a href="#analysis">Analysis</a><a href="#actions">Next steps</a><a href="#register">Register</a><a href="#coverage">Coverage</a></nav>
<div class="acts"><span class="chip">Read-only</span><button class="btn" type="button" data-print aria-label="Print or save as PDF"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6 9V3h12v6M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2M6 14h12v7H6z"/></svg><span class="lbl">Print / PDF</span></button></div></header>
<section class="hero" id="summary" aria-labelledby="h-title"><div class="hero-in"><div>
<p class="kicker">Access governance · Azure RBAC</p><h1 id="h-title">Privileged access review</h1>
<p class="lead">Of <b>__TOTAL__ privileged assignments</b>, <b>__REMOVABLE__ can be removed without changing effective access</b> (deleted identities or duplicated permissions) and <b>__REVIEW__ need an individual review</b> with their owner.</p>
<div class="meta">__CHIPS__</div></div>
<aside class="verdict v-__TONE__" aria-label="Verdict"><span class="k">Verdict</span><b>__VERDICT__</b><p>__VLINE__</p>__VCOV__</aside>
<div class="dist"><div class="dist-h">Decision for <b>__TOTAL__</b> privileged assignments</div><div class="track" role="img" aria-label="__TRACK__">__SEG__</div><div class="legend">__LEGEND__</div></div>
</div></section>
<main id="main">
<div class="kpis">__KPIS__</div>
<div class="grid2" id="analysis">
<section class="card" aria-labelledby="h-scope"><h2 id="h-scope">Decision by scope level</h2><p class="sub">Where privileged access is concentrated and what to do with it.</p>
<div class="wrap"><table class="tbl"><thead><tr><th scope="col">Level</th><th scope="col" class="n">Total</th><th scope="col" class="n">Orphaned</th><th scope="col" class="n">Redundant</th><th scope="col" class="n">Review</th><th scope="col" class="n">Compliant</th></tr></thead><tbody>__LEVELS__</tbody></table></div>
<p class="info"><svg viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="10" r="7.5" fill="none" stroke="currentColor" stroke-width="1.7"/><path d="M10 9v5m0-7.5v.1" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg><span>A <b>redundant</b> assignment repeats a permission the identity already receives without condition from a higher scope, at the same scope or through a group. Removing it does not change effective access.</span></p></section>
<section class="card" aria-labelledby="h-sig"><h2 id="h-sig">Individual review signals</h2><p class="sub">Why a current assignment needs validation by its owner.<span class="np"> Select a signal to list those assignments.</span></p><div class="bars">__SIGNALS__</div></section>
<section class="card" aria-labelledby="h-top"><h2 id="h-top">Identities with the most current privileges</h2><p class="sub">Assignments under review or compliant per identity, excluding those that can be removed.</p><ol class="bars ids">__TOP__</ol></section>
<section class="card" id="actions" aria-labelledby="h-next"><h2 id="h-next">Next steps · 30-day pilot</h2><p class="sub">The agent proposes; people approve. No change is executed automatically.</p><ol class="steps">__STEPS__</ol></section>
</div>
<section id="register" aria-labelledby="h-reg"><div class="sh"><h2 id="h-reg" tabindex="-1">Privileged assignment register <span class="cn">__TOTAL__</span></h2><p>Filter, sort and export. Each row links to the scope's access control (IAM) blade in the Azure portal.</p></div>
<div class="card flat"><div class="tools">
<input id="q" type="search" placeholder="Search identity, role, scope or ID…" aria-label="Search identity, role, scope or ID" autocomplete="off">
<select id="fd" aria-label="Decision"><option value="">All decisions</option>__F_DEC__</select>
<select id="ft" aria-label="Privilege tier"><option value="">All tiers</option>__F_TIER__</select>
<select id="fp" aria-label="Identity type"><option value="">All identity types</option>__F_TYPE__</select>
<select id="fl" aria-label="Scope level"><option value="">All scope levels</option>__F_LVL__</select>
<select id="fs" aria-label="Review signal"><option value="">All review signals</option>__F_SIG__</select>
<div class="tacts"><button class="btn ghost" type="button" id="csv"><svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M10 3v10m-4-4 4 4 4-4M4 16h12"/></svg>Export CSV</button><button class="btn link" type="button" id="rst">Clear filters</button></div>
<p class="cnt" id="cnt" aria-live="polite"></p></div>
<p class="pcap" id="pcap"></p>
<div class="wrap"><table class="reg" id="reg"><thead><tr>
<th scope="col" class="w-dec" data-k="decision" data-l="Decision"><button type="button">Decision</button></th><th scope="col" class="w-role" data-k="role" data-l="Role and access"><button type="button">Role and access</button></th>
<th scope="col" class="w-id" data-k="principal_name" data-l="Identity"><button type="button">Identity</button></th><th scope="col" class="w-scope" data-k="scope_label" data-l="Scope"><button type="button">Scope</button></th>
<th scope="col" data-k="flags" data-l="Reason and action"><button type="button">Reason and action</button></th><th scope="col" class="w-iam c-iam">IAM</th>
</tr></thead><tbody id="body"></tbody></table></div>
<div class="more" id="more"><button class="btn ghost" type="button" id="mb">Show more</button><button class="btn link" type="button" id="ma">Show all</button></div>
</div></section>
<section id="coverage" aria-labelledby="h-cov"><div class="sh"><h2 id="h-cov">Coverage and method</h2><p>What the review could read and how each decision is made.</p></div>
__COVNOTE__<div class="grid2" style="margin-top:0">
<div class="card"><h3>Review coverage</h3><p class="sub">Anything that could not be read is a blind spot, never a clean result.</p>
<div class="wrap"><table class="tbl"><thead><tr><th scope="col">Subscription</th><th scope="col">Assignments</th><th scope="col">Definitions</th><th scope="col">PIM active</th><th scope="col">PIM eligible</th></tr></thead><tbody>__COV__</tbody></table></div></div>
<div class="card"><h3>Identity resolution</h3><p class="sub">Microsoft Entra ID through Microsoft Graph (read only).</p>
<div class="wrap"><table class="tbl"><thead><tr><th scope="col">Identities (Graph)</th><th scope="col" class="n">Resolved</th><th scope="col" class="n">Orphaned</th><th scope="col" class="n">No permission</th></tr></thead><tbody>__GRAPH__</tbody></table></div>
<p class="small">User sign-in: __SIU__ · Application sign-in: __SIS__ · Group membership: __MEM__</p></div></div>
<p class="method"><b>Method.</b> Inventory of Azure RBAC assignments per subscription (including those inherited from Management Groups), role classification by its permissions (tier 0 = can write role assignments; tier 1 = full control-plane control; tier 2 = service administration roles), identity resolution in Microsoft Entra ID, PIM state and sign-in activity. An assignment is only marked as redundant when another permanent, unconditioned assignment of the same identity (or of a group it belongs to) already covers all its permissions at the same or a higher scope.</p>
</section>
</main>
<footer><div class="fin">__MARK__<span>Report generated by Azure SRE Agent · read only · __WHEN____ORG_FOOT__</span></div></footer>
<script>
const DATA=__DATA__;
const L={orphan:"Remove · orphaned",redundant:"Remove · redundant",review:"Individual review",ok:"Compliant"},R={orphan:0,redundant:1,review:2,ok:3};
const PAGE=20,F=["q","fd","ft","fp","fl","fs"],$=id=>document.getElementById(id);
let sortK="decision",asc=true,limit=PAGE,tq;
const e=s=>String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const nm=s=>e(s).replace(/([\/_.@·])/g,"$1<wbr>").replace(/([a-z])([A-Z])/g,"$1<wbr>$2");
const det=s=>/[0-9a-f]{8}-[0-9a-f]{4}-/i.test(s)?e(s).replace(/\b([0-9a-f]{8})-([0-9a-f]{4})-([0-9a-f]{4})-([0-9a-f]{4})-([0-9a-f]{12})\b/gi,'<span class="id">$1-<wbr>$2-<wbr>$3-<wbr>$4-<wbr>$5</span>'):nm(s);
const EXT='<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M6.5 3.5h-3v9h9v-3M9.5 3.5h3v3M12.5 3.5 7 9" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>';
function hit(r){const q=$("q").value.trim().toLowerCase(),d=$("fd").value,t=$("ft").value,p=$("fp").value,l=$("fl").value,s=$("fs").value;
return(!d||(d==="remove"?R[r.decision]<2:r.decision===d))&&(!t||String(r.tier)===t)&&(!p||r.principal_type===p)&&(!l||r.scope_level===l)&&(!s||(r.decision==="review"&&r.flags.includes(s)))&&
(!q||[r.principal_name,r.principal_detail,r.principal_id,r.role,r.scope_label,r.scope,r.reason,r.action,r.flag_labels.join(" "),r.assignment_id].join(" ").toLowerCase().includes(q))}
function list(){const k=sortK;return DATA.filter(hit).sort((a,b)=>{let x=a[k],y=b[k];if(k==="decision"){x=R[x];y=R[y]}else if(k==="flags"){x=a.flags.length;y=b.flags.length}
else{x=String(x??"").toLowerCase();y=String(y??"").toLowerCase()}return(x<y?-1:x>y?1:0)*(asc?1:-1)})}
function scope(r){const p=String(r.scope_label||"").split(" · ");return r.scope_level==="Resource"&&p.length>1?`<span class="nm">${nm(p[0])}</span><span class="sm">Resource · ${nm(p.slice(1).join(" · "))}</span>`:`<span class="nm">${nm(r.scope_label)}</span><span class="sm">${e(r.scope_level)}</span>`}
function tr(r,i){const why=r.decision==="review"&&r.flag_labels.length?'<ul class="sig">'+r.flag_labels.map(f=>"<li>"+e(f)+"</li>").join("")+"</ul>":'<p class="why">'+e(r.reason)+"</p>";
return`<tr${i>=limit?' class="pg"':""}><td><span class="pill p-${r.decision}">${L[r.decision]}</span></td><td><b>${e(r.role)}</b><span class="tier t${r.tier}">${e(r.tier_label)}</span><span class="sm">${e(r.access)}${r.end_date?" until "+e(r.end_date):""}${r.condition?" · with condition":""}</span></td>`+
`<td><b class="nm">${nm(r.principal_name)}</b><span class="sm">${e(r.principal_type)}${r.last_sign_in?" · last sign-in "+e(r.last_sign_in):""}</span>${r.principal_detail?'<span class="sm">'+det(r.principal_detail)+"</span>":""}</td>`+
`<td class="lb" data-h="Scope">${scope(r)}</td><td class="lb" data-h="Reason and action">${why}<p class="act"><b>Action:</b> ${e(r.action)}</p></td>`+
`<td class="c-iam">${r.portal_url?`<a class="iam" href="${e(r.portal_url)}" target="_blank" rel="noopener noreferrer" aria-label="Open the access control (IAM) of ${e(r.scope_label)} in the Azure portal">Open${EXT}</a>`:""}</td></tr>`}
function picked(){return["fd","ft","fp","fl","fs"].map($).filter(s=>s.value).map(s=>s.getAttribute("aria-label")+": "+s.options[s.selectedIndex].text.replace(/ \(\d+\)$/,""))}
function render(){const all=list(),n=all.length,shown=Math.min(n,limit),q=$("q").value.trim(),f=picked().concat(q?['Search: "'+q+'"']:[]);
$("body").innerHTML=all.map(tr).join("")||'<tr><td colspan="6" class="empty">'+(DATA.length?'No assignments match the current filters. <button class="btn link" type="button" data-clear>Clear filters</button>':'No privileged assignments in this review.')+"</td></tr>";
$("cnt").textContent=(n>shown?"Showing "+shown+" of "+n+" assignments":n+" assignment"+(n===1?"":"s"))+(n<DATA.length?" · filtered from "+DATA.length:"");
$("pcap").textContent=n+" of "+DATA.length+" privileged assignments"+(f.length?" · "+f.join(" · "):" · no filter");
$("more").hidden=n<=shown;$("mb").textContent="Show "+Math.min(PAGE,n-shown)+" more";$("ma").textContent="Show all "+n;
document.querySelectorAll("#reg th[data-k]").forEach(th=>th.dataset.k===sortK?th.setAttribute("aria-sort",asc?"ascending":"descending"):th.removeAttribute("aria-sort"))}
function reset(){F.forEach(id=>$(id).value="");limit=PAGE}
F.forEach(id=>$(id).addEventListener(id==="q"?"input":"change",()=>{clearTimeout(tq);tq=setTimeout(()=>{limit=PAGE;render()},id==="q"?120:0)}));
document.querySelectorAll("#reg th[data-k] button").forEach(b=>b.addEventListener("click",()=>{const k=b.parentNode.dataset.k;if(sortK===k)asc=!asc;else{sortK=k;asc=true}render()}));
$("mb").addEventListener("click",()=>{limit+=PAGE;render()});$("ma").addEventListener("click",()=>{limit=Infinity;render()});$("rst").addEventListener("click",()=>{reset();render()});
document.addEventListener("click",ev=>{const c=ev.target.closest("[data-clear]"),g=ev.target.closest("[data-go],[data-sig]");if(c){reset();render();$("q").focus()}
if(g){reset();const v=g.dataset.go||"sig:"+g.dataset.sig;if(v==="remove")$("fd").value="remove";else{$("fd").value="review";$("fs").value=v.slice(4)}render();
if(!g.matches("a")){ev.preventDefault();$("register").scrollIntoView({behavior:matchMedia("(prefers-reduced-motion: reduce)").matches?"auto":"smooth"})}$("h-reg").focus({preventScroll:true})}});
$("csv").addEventListener("click",()=>{const h=["decision","role","tier","identity","type","upn_or_appid","scope","scope_level","access","signals","reason","action","assignment_id","portal_iam"],c=v=>'"'+String(v??"").replace(/"/g,'""')+'"';
const lines=[h.join(",")].concat(list().map(r=>[L[r.decision],r.role,r.tier_label,r.principal_name,r.principal_type,r.principal_detail,r.scope,r.scope_level,r.access,r.flag_labels.join(" | "),r.reason,r.action,r.assignment_id,r.portal_url].map(c).join(",")));
const a=document.createElement("a");a.href=URL.createObjectURL(new Blob(["\ufeff"+lines.join("\r\n")],{type:"text/csv;charset=utf-8"}));a.download="rbac-privileged-access-filtered.csv";document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(a.href),4000)});
document.querySelector("[data-print]").addEventListener("click",()=>window.print());
render();
</script></body></html>"""
        return re.sub(r"__[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*__", lambda m: repl.get(m.group(0), m.group(0)), page)

    html_doc = render_html(json_doc, LOGO_DATA_URI)

    files = {"report": (base + ".html", html_doc), "csv": (base + ".csv", csv_text), "json": (base + ".json", json_text)}
    out = {}
    try:
        os.makedirs("/mnt/data", exist_ok=True)
        cwd = Path.cwd()
        match = re.fullmatch(r"/(?:root/sreagent|usr)/terminalRoot/tmp/ThreadFiles/([0-9a-fA-F-]{36})", cwd.as_posix())
        for key, (fname, content) in files.items():
            with open(os.path.join("/mnt/data", fname), "w", encoding="utf-8") as fh:
                fh.write(content)
            (cwd / fname).write_text(content, encoding="utf-8")
            out[key + "_path"] = str(cwd / fname) if match else os.path.join("/mnt/data", fname)
            if match:
                out[key + "_url"] = f"/api/files/tmp/ThreadFiles/{match.group(1)}/{quote(fname, safe='')}"
    except Exception as exc:
        return fail(f"Could not write the report files: {type(exc).__name__}")

    # Compact response: the full detail goes into the files, not into the tool output.
    compact_summary = {k: v for k, v in summary.items() if k not in ("subscriptions", "reference_utc")}
    compact_summary["review_signals"] = dict(list(summary["review_signals"].items())[:6])
    compact_coverage = {
        "status": status,
        "subscriptions": [{"name": c.get("name"), "role_assignments": c["role_assignments"]["status"]} for c in sub_coverage],
        "graph_token": coverage["graph_token"],
        "graph_identities": coverage["graph_identities"],
        "user_sign_in_activity": signin_user_status,
        "service_principal_sign_in_activity": signin_sp_status,
        "group_membership": membership_status,
    }
    return {
        "status": status,
        **out,
        "summary": compact_summary,
        "coverage": compact_coverage,
        "top_review_items": [
            {k: r[k] for k in ("decision_label", "role", "principal_name", "scope_label")}
            for r in rows if r["decision"] in ("orphan", "redundant", "review")][:5],
    }

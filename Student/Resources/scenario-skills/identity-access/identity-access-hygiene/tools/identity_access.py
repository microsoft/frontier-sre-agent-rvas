"""
identity_access: Review privileged Azure role assignments for access hygiene.

Azure SRE Agent Python tool. Uses the agent managed identity (ARM scope) to read
role assignments and classic administrators across the accessible subscriptions,
keep the privileged roles, classify each into an access hygiene finding, and print
a report_data object as JSON ready to pipe into report_render.py.

    python identity_access.py | python report_render.py

Heavy imports (azure-identity, requests) are lazy so the pure classification
helpers can be unit tested without them. See references/checks-catalog.md.
"""

import json
import sys
from pathlib import Path


def _bootstrap_shared_tools():
    here = Path(__file__).resolve().parent
    candidates = [here, here / "tools"] + [parent / "shared" / "tools" for parent in list(here.parents)[:5]]
    for candidate in candidates:
        if (candidate / "azure_http.py").is_file():
            if str(candidate) not in sys.path:
                sys.path.insert(0, str(candidate))
            return
    raise ModuleNotFoundError("Bundle shared tools, including azure_http.py, with this collector.")


_bootstrap_shared_tools()

ARM_ENDPOINT = "https://management.azure.com"
SEVERITY_ORDER = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
OWNER_SPRAWL_THRESHOLD = 3
SOURCES = [
    {"title": "Azure role definitions", "url": "https://learn.microsoft.com/azure/role-based-access-control/role-definitions"},
    {"title": "List role assignments", "url": "https://learn.microsoft.com/rest/api/authorization/role-assignments/list-for-subscription"},
]

ROLE_BY_ID = {
    "8e3af657-a8ff-443c-a75c-2fe8c4bcb635": "Owner",
    "b24988ac-6180-42a0-ab88-20f7382dd24c": "Contributor",
    "18d7d88d-d35e-4fb5-a5c3-7773c20a72d9": "User Access Administrator",
    "f58310d9-a9f6-439a-9e8d-f62e7b41a168": "Role Based Access Control Administrator",
}
HIGH_PRIVILEGE = {"Owner", "User Access Administrator", "Role Based Access Control Administrator"}


def role_name_from_id(role_definition_id):
    """Return the privileged role name for a roleDefinitionId, or None. Pure."""
    guid = (role_definition_id or "").rstrip("/").split("/")[-1].lower()
    return ROLE_BY_ID.get(guid)


def scope_kind(scope, subscription):
    """Classify an assignment scope. Pure and testable."""
    value = (scope or "").lower()
    if "/managementgroups/" in value:
        return "management group"
    if value == f"/subscriptions/{subscription}".lower():
        return "subscription"
    if "/resourcegroups/" in value and "/providers/" not in value.split("/resourcegroups/", 1)[1]:
        return "resource group"
    return "resource" if value else "Unknown"


def classify_assignment(assignment, subscription, role_definitions=None):
    """Return a finding for a privileged assignment, or None. Pure and testable."""
    props = assignment.get("properties", assignment)
    role = role_name_from_id(props.get("roleDefinitionId"))
    definition = (role_definitions or {}).get((props.get("roleDefinitionId") or "").lower(), {})
    custom = definition.get("roleType") == "CustomRole"
    unresolved = not role and not definition
    if not role:
        if definition and not custom:
            return None
        role = definition.get("roleName") or "Unresolved role definition"
    ptype = props.get("principalType") or "Unknown"
    scope = scope_kind(props.get("scope"), subscription)
    base = {
        "principal": props.get("principalId") or "Unknown",
        "assignment_id": assignment.get("id", ""),
        "role_definition_id": props.get("roleDefinitionId", ""),
        "role_permissions": definition.get("permissions", []) if custom else [],
        "principal_type": ptype,
        "role": role,
        "scope": props.get("scope") or "Unknown",
        "scope_kind": scope,
        "subscription": subscription,
        "_band": "Low",
        "severity": "Low",
    }

    def finish(severity, recommendation):
        base["severity"] = severity
        base["_band"] = severity
        base["recommendation"] = recommendation
        return base

    if ptype.lower() == "unknown":
        return finish("Medium", "Review candidate: principal resolution is unknown, not proof of deletion. Confirm identity and dependencies before any access change.")
    if custom or unresolved:
        return finish("Medium", "Review custom or unresolved role permissions, including Actions, NotActions, DataActions and NotDataActions. Privilege and effective access are not established by the role name.")
    if role in HIGH_PRIVILEGE and scope == "management group":
        return finish("High", "Confirm this wide scope is intended and scope it down where possible.")
    if ptype == "ServicePrincipal" and role in HIGH_PRIVILEGE:
        return finish("High", "Scope the service principal down to least privilege; avoid subscription wide access administration.")
    if role == "Owner" and ptype == "User":
        return finish("Medium", "Move to just in time Owner through Privileged Identity Management.")
    if role == "Contributor" and ptype == "ServicePrincipal":
        return finish("Low", "Confirm the service principal needs Contributor breadth; scope it down where possible.")
    if role == "Owner":
        return finish("Medium", "Reduce standing Owners; grant Owner just in time through Privileged Identity Management.")
    return None


def owner_sprawl_finding(subscription, owner_count, threshold=OWNER_SPRAWL_THRESHOLD):
    """Return an Owner sprawl finding when over the threshold, else None. Pure."""
    if owner_count <= threshold:
        return None
    return {
        "principal": f"{owner_count} owners",
        "principal_type": "Multiple",
        "role": "Owner",
        "scope": f"/subscriptions/{subscription}",
        "scope_kind": "subscription",
        "subscription": subscription,
        "recommendation": "Reduce standing Owners; grant Owner just in time through Privileged Identity Management.",
        "severity": "High",
        "_band": "High",
    }


def build_report_data(findings, subs_scanned, sub_names, notes):
    for finding in findings:
        finding["subscription_name"] = sub_names.get(finding["subscription"], finding["subscription"])
    findings = sorted(findings, key=lambda f: SEVERITY_ORDER.get(f["severity"], 9))
    sp_high = sum(1 for f in findings if f["principal_type"] == "ServicePrincipal" and f["role"] in HIGH_PRIVILEGE)
    classic = sum(1 for f in findings if f["role"] == "Classic administrator")
    sev_counts, by_role = {}, {}
    for finding in findings:
        sev_counts[finding["severity"]] = sev_counts.get(finding["severity"], 0) + 1
        by_role[finding["role"]] = by_role.get(finding["role"], 0) + 1
    sev_items = [{"name": b, "value": sev_counts[b], "band": b} for b in ("Critical", "High", "Medium", "Low") if b in sev_counts]
    role_items = sorted(({"name": k, "value": v} for k, v in by_role.items()), key=lambda i: i["value"], reverse=True)
    return {
        "assessment_status": "Not assessed" if not subs_scanned else ("Partial" if notes else "Complete"),
        "sources": SOURCES,
        "title": "Identity and Access Hygiene",
        "subtitle": "Privileged access across the estate.",
        "meta": {"window": "Point in time", "scope": f"{subs_scanned} subscription(s)", "source": "Azure role assignments"},
        "summary_cards": [
            {"label": "Privileged findings", "value": f"{len(findings):,}"},
            {"label": "High privilege SPs", "value": f"{sp_high:,}", "sub": "service principals"},
            {"label": "Classic admins", "value": f"{classic:,}"},
            {"label": "Subscriptions scanned", "value": str(subs_scanned)},
        ],
        "charts": [
            {"title": "Findings by severity", "unit": "findings", "items": sev_items},
            {"title": "Findings by role", "unit": "findings", "items": role_items},
        ],
        "findings": {
            "title": "Access hygiene findings",
            "columns": ["principal", "principal_type", "assignment_id", "role", "scope", "scope_kind", "subscription", "recommendation", "severity"],
            "rows": findings,
        },
        "method_notes": notes + [
            f"Owner sprawl threshold: more than {OWNER_SPRAWL_THRESHOLD} Owners at subscription scope.",
            "Principal display names and guest status need a Microsoft Entra read; the report shows the principal id and type.",
            "This is a configuration review, not effective access analysis. Redundant assignments, inactivity, PIM eligibility, group membership and tenant sign ins are not assessed.",
            "Absence of observed control plane operations cannot prove a role is unneeded; data plane and infrequent workload use may be missing.",
            "Custom roles are review candidates, not a complete privilege classifier. Review exclusions, data actions, conditions and inherited access with the owner.",
            "Built in role coverage is limited to the four listed role ids. Other built in roles are outside this focused classifier, not certified nonprivileged.",
        ],
    }


def _headers():
    from agent_identity import agent_token

    token = agent_token(f"{ARM_ENDPOINT}/.default")
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _get_all(headers, url):
    import azure_http as requests

    items = []
    while url:
        response = requests.get(url, headers=headers, timeout=90)
        response.raise_for_status()
        body = response.json()
        items.extend(body.get("value", []))
        url = body.get("nextLink")
    return items


def _list_subscription_names(headers):
    import azure_http as requests

    url = f"{ARM_ENDPOINT}/subscriptions?api-version=2022-12-01"
    names = {}
    while url:
        response = requests.get(url, headers=headers, timeout=60)
        response.raise_for_status()
        body = response.json()
        for item in body.get("value", []):
            names[item["subscriptionId"]] = item.get("displayName", item["subscriptionId"])
        url = body.get("nextLink")
    return names


def main(subscription_ids=None) -> dict:
    headers = _headers()
    notes = []
    try:
        sub_names = {sub: sub for sub in subscription_ids} if subscription_ids else _list_subscription_names(headers)
    except Exception as error:  # noqa: BLE001
        sub_names = {}
        notes.append(f"Could not list subscriptions ({error}).")

    findings = []
    scanned = 0
    for sub in (sub_names or {}):
        try:
            assignments = _get_all(headers, f"{ARM_ENDPOINT}/subscriptions/{sub}/providers/Microsoft.Authorization/roleAssignments?api-version=2022-04-01")
        except Exception:  # noqa: BLE001
            notes.append(f"Role assignments not read for subscription {sub}.")
            continue
        scanned += 1
        try:
            definitions = _get_all(headers, f"{ARM_ENDPOINT}/subscriptions/{sub}/providers/Microsoft.Authorization/roleDefinitions?api-version=2022-04-01")
            role_definitions = {item["id"].lower(): item.get("properties", {}) for item in definitions}
        except Exception:  # noqa: BLE001
            role_definitions = {}
            notes.append(f"Role definitions not read for subscription {sub}; custom role privilege not assessed.")
        owner_count = 0
        for assignment in assignments:
            props = assignment.get("properties", {})
            if role_name_from_id(props.get("roleDefinitionId")) == "Owner" and scope_kind(props.get("scope"), sub) == "subscription":
                owner_count += 1
            finding = classify_assignment(assignment, sub, role_definitions)
            if finding:
                findings.append(finding)
                if finding["role"] == "Unresolved role definition":
                    notes.append(f"Unresolved role definition {finding['role_definition_id']}; privilege not assessed.")
        sprawl = owner_sprawl_finding(sub, owner_count)
        if sprawl:
            findings.append(sprawl)
        try:
            for admin in _get_all(headers, f"{ARM_ENDPOINT}/subscriptions/{sub}/providers/Microsoft.Authorization/classicAdministrators?api-version=2015-07-01"):
                props = admin.get("properties", {})
                findings.append({
                    "principal": props.get("emailAddress", "classic admin"), "principal_type": "User",
                    "assignment_id": admin.get("id", ""),
                    "role": "Classic administrator", "scope": f"/subscriptions/{sub}", "scope_kind": "subscription", "subscription": sub,
                    "recommendation": "Migrate to Azure role based access control and remove the classic administrator.",
                    "severity": "High", "_band": "High",
                })
        except Exception:  # noqa: BLE001
            notes.append(f"Classic administrators not read for subscription {sub}.")

    return build_report_data(findings, scanned, sub_names, notes)


if __name__ == "__main__":
    print(json.dumps(main()))

"""
expiry_scan: Rank Azure certificates, secrets, and credentials by days to expiry.

Azure SRE Agent Python tool. Uses the agent managed identity to read App Service
certificates (Azure Resource Graph), Key Vault certificates and secrets (vault
data plane), and application credentials (Microsoft Graph), computes the days to
expiry for each, and prints a report_data object as JSON ready to pipe into
report_render.py.

    python expiry_scan.py [horizon_days] | python report_render.py

Heavy imports (azure-identity, requests) are lazy so the pure classification
helpers can be unit tested without them. See references/checks-catalog.md.
"""

import json
import sys
from datetime import datetime, timezone
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
VAULT_AUDIENCE = "https://vault.azure.net"
GRAPH_ENDPOINT = "https://graph.microsoft.com"
HORIZON_DEFAULT = 60
SEVERITY_ORDER = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
SOURCES = [
    {"title": "Key Vault metadata permissions", "url": "https://learn.microsoft.com/azure/key-vault/general/rbac-guide"},
    {"title": "List secret metadata", "url": "https://learn.microsoft.com/rest/api/keyvault/secrets/get-secrets/get-secrets"},
    {"title": "List application registrations", "url": "https://learn.microsoft.com/graph/api/application-list"},
]


def days_to_expiry(expiry, now):
    """Whole days until expiry; negative when already expired. Pure."""
    if expiry is None:
        return None
    return (expiry - now).days


def severity_for_days(days):
    """Severity band from days remaining. Pure and testable."""
    if days is None:
        return None
    if days < 0:
        return "Critical"
    if days <= 14:
        return "High"
    if days <= 30:
        return "Medium"
    return "Low"


def time_bucket(days):
    if days is None:
        return "Unknown"
    if days < 0:
        return "Expired"
    if days <= 14:
        return "Within 14 days"
    if days <= 30:
        return "15 to 30 days"
    return "31 days to horizon"


def classify_item(item, now, horizon):
    """Turn a raw item into a finding, or None when outside the horizon. Pure.

    item: {name, kind, source, subscription, resource_group, expiry(datetime)}.
    """
    expiry = item.get("expiry")
    days = days_to_expiry(expiry, now)
    if days is not None and days > horizon:
        return None
    disabled = item.get("enabled") is False
    severity = "Low" if disabled else (severity_for_days(days) or "Medium")
    state = "Disabled" if disabled else ("Enabled" if item.get("enabled") is True else "Unknown")
    recommendation = item.get("recommendation", "Renew or rotate before expiry and update the consumers.")
    if days is None:
        recommendation = "Expiry missing or unreadable. Confirm policy and set a managed expiry or rotation plan; expiry risk is unknown."
    if disabled:
        recommendation = "Disabled item: confirm retained dependencies and rotation policy before enabling or removing. " + recommendation
    return {
        "item": item.get("name", ""),
        "kind": item.get("kind", ""),
        "source": item.get("source", ""),
        "subscription": item.get("subscription", ""),
        "item_id": item.get("id", ""),
        "state": state,
        "expires": expiry.strftime("%Y-%m-%d") if expiry else "Unknown (expiry missing or unreadable)",
        "days_left": days,
        "recommendation": recommendation,
        "severity": severity,
        "_band": severity,
        "_sort": days if days is not None else horizon + 1,
    }


def build_report_data(items, horizon, subs_scanned, notes, now=None):
    now = now or datetime.now(timezone.utc)
    findings = [f for f in (classify_item(item, now, horizon) for item in items) if f]
    findings.sort(key=lambda f: f["_sort"])
    expired = sum(1 for f in findings if f["days_left"] is not None and f["days_left"] < 0 and f["state"] != "Disabled")
    expiring = sum(1 for f in findings if f["days_left"] is not None and f["state"] != "Disabled")
    unknown = sum(1 for f in findings if f["days_left"] is None)
    disabled = sum(1 for f in findings if f["state"] == "Disabled")
    certs = sum(1 for f in findings if "cert" in f["kind"].lower())
    secrets = len(findings) - certs
    sev_counts, bucket_counts = {}, {}
    for f in findings:
        sev_counts[f["severity"]] = sev_counts.get(f["severity"], 0) + 1
        bucket = time_bucket(f["days_left"])
        bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1
    sev_items = [{"name": b, "value": sev_counts[b], "band": b} for b in ("Critical", "High", "Medium", "Low") if b in sev_counts]
    bucket_order = ["Expired", "Within 14 days", "15 to 30 days", "31 days to horizon", "Unknown"]
    bucket_items = [{"name": b, "value": bucket_counts[b]} for b in bucket_order if b in bucket_counts]
    return {
        "assessment_status": "Not assessed" if not items else ("Partial" if notes or unknown else "Complete"),
        "sources": SOURCES,
        "title": "Certificate and Secret Expiry",
        "subtitle": "Certificates, secrets, and credentials by days to expiry.",
        "meta": {"window": f"{horizon} day horizon", "scope": f"{subs_scanned} subscription(s)", "source": "Key Vault, App Service, Graph"},
        "summary_cards": [
            {"label": "Expiring within horizon", "value": f"{expiring:,}", "sub": "disabled items excluded"},
            {"label": "Already expired", "value": f"{expired:,}"},
            {"label": "Certificates", "value": f"{certs:,}"},
            {"label": "Secrets and credentials", "value": f"{secrets:,}"},
            {"label": "Unknown expiry", "value": str(unknown)},
            {"label": "Disabled items", "value": str(disabled)},
        ],
        "charts": [
            {"title": "Items by urgency", "unit": "items", "items": sev_items},
            {"title": "Items by time bucket", "unit": "items", "items": bucket_items},
        ],
        "findings": {
            "title": "Expiring items",
            "columns": ["item", "item_id", "kind", "source", "subscription", "state", "expires", "days_left", "recommendation", "severity"],
            "rows": findings,
        },
        "method_notes": notes + [
            f"Horizon: {horizon} days. Items expiring later are not shown; anything already expired is always shown.",
            "Certificates embedded in an Application Gateway or Front Door listener are not enumerated; prefer Key Vault referenced certificates.",
            "Reads list metadata only, never secret values or private keys. Missing expiry is unknown, not healthy. Disabled items are distinct from active expiry risks.",
            "Microsoft Graph applications are app registrations, not all service principal credentials. Service principal objects and tenant sign ins are not assessed.",
        ],
    }


def _credential():
    from agent_identity import agent_credential

    return agent_credential()


def _from_unix(value):
    if value in (None, ""):
        return None
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return None


def _from_iso(value):
    if not value:
        return None
    try:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return result if result.tzinfo is not None else None
    except ValueError:
        return None


def _run_graph(headers, query):
    import azure_http as requests

    url = f"{ARM_ENDPOINT}/providers/Microsoft.ResourceGraph/resources?api-version=2022-10-01"
    rows, skip_token = [], None
    while True:
        payload = {"query": query, "options": {"resultFormat": "objectArray", "top": 1000}}
        if skip_token:
            payload["options"]["$skipToken"] = skip_token
        response = requests.post(url, headers=headers, json=payload, timeout=120)
        response.raise_for_status()
        body = response.json()
        rows.extend(body.get("data", []))
        skip_token = body.get("$skipToken")
        if not skip_token:
            if str(body.get("resultTruncated", "false")).lower() == "true":
                raise RuntimeError("Resource Graph results incomplete without continuation token.")
            return rows


def _read_vault_list(token, base_url):
    import azure_http as requests
    from urllib.parse import urlparse

    items, url = [], f"{base_url}?api-version=7.4"
    expected = urlparse(base_url)
    if expected.scheme != "https" or not (expected.hostname or "").endswith(".vault.azure.net") or expected.port not in (None, 443):
        raise ValueError("Unsupported vault endpoint; only public Azure metadata endpoints are configured.")
    headers = {"Authorization": f"Bearer {token}"}
    while url:
        target = urlparse(url)
        if target.scheme != "https" or target.hostname != expected.hostname or target.port not in (None, 443) or target.path != expected.path:
            raise ValueError("Unexpected vault continuation: metadata collection path required.")
        response = requests.get(url, headers=headers, timeout=60)
        response.raise_for_status()
        body = response.json()
        items.extend(body.get("value", []))
        url = body.get("nextLink")
    return items


def _collect(headers, credential, application_ids=None, allow_tenant_directory=False):
    """Gather raw items from all sources. Returns (items, notes)."""
    import azure_http as requests

    items, notes = [], []

    try:
        for cert in _run_graph(headers, "resources | where type =~ 'microsoft.web/certificates' | project id, name, subscriptionId, resourceGroup, expirationDate=tostring(properties.expirationDate)"):
            items.append({
                "name": cert.get("name", ""), "kind": "App Service certificate", "source": "App Service",
                "subscription": cert.get("subscriptionId", ""), "resource_group": cert.get("resourceGroup", ""),
                "expiry": _from_iso(cert.get("expirationDate")),
                "id": cert.get("id", ""),
                "recommendation": "Renew or replace the certificate and update the binding.",
            })
    except Exception as error:  # noqa: BLE001
        notes.append(f"App Service certificates not read ({error}).")

    try:
        vaults = _run_graph(headers, "resources | where type =~ 'microsoft.keyvault/vaults' | project name, subscriptionId, vaultUri=tostring(properties.vaultUri)")
    except Exception as error:  # noqa: BLE001
        vaults = []
        notes.append(f"Key Vault list not read ({error}).")
    denied_vaults = 0
    if vaults:
        try:
            vault_token = credential.get_token(f"{VAULT_AUDIENCE}/.default").token
        except Exception as error:  # noqa: BLE001
            vault_token = None
            notes.append(f"Could not acquire a Key Vault data plane token ({error}).")
        for vault in vaults:
            uri = (vault.get("vaultUri") or "").rstrip("/")
            if not uri or not vault_token:
                notes.append(f"Vault {vault.get('name', '')} not assessed: URI or data plane token unavailable.")
                continue
            for collection, kind in (("certificates", "Key Vault certificate"), ("secrets", "Key Vault secret")):
                try:
                    for entry in _read_vault_list(vault_token, f"{uri}/{collection}"):
                        attributes = entry.get("attributes") or {}
                        items.append({
                            "name": entry.get("id", "").rstrip("/").split("/")[-1] or vault.get("name"),
                            "id": entry.get("id", ""), "kind": kind, "source": vault.get("name", ""),
                            "subscription": vault.get("subscriptionId", ""),
                            "expiry": _from_unix(attributes.get("exp")), "enabled": attributes.get("enabled"),
                            "recommendation": "Renew or rotate before expiry and update consumers. Managed secrets may correspond to certificate entries.",
                        })
                except Exception:  # noqa: BLE001
                    denied_vaults += 1
                    notes.append(f"Vault {vault.get('name', '')} {collection} metadata not assessed.")
    if denied_vaults:
        notes.append(f"{denied_vaults} vault collection(s) could not be read. Key Vault Reader supplies metadata read on RBAC vaults, not secret values; access policy vaults need certificate/secret list permissions.")

    if not application_ids and not allow_tenant_directory:
        notes.append("Application credentials not assessed: no approved application object ids or explicit tenant directory enumeration consent. Service principal credentials are outside this collector.")
        return items, notes
    try:
        graph_token = credential.get_token(f"{GRAPH_ENDPOINT}/.default").token
        from uuid import UUID

        ids = [str(UUID(value)) for value in (application_ids or [])]
        select = "$select=id,displayName,appId,passwordCredentials,keyCredentials"
        url = f"{GRAPH_ENDPOINT}/v1.0/applications?{select}&$top=100"
        if ids:
            url = f"{GRAPH_ENDPOINT}/v1.0/applications/{ids[0]}?{select}"
        pending = ids[1:]
        gh = {"Authorization": f"Bearer {graph_token}"}
        pages = 0
        while url and pages < 40:
            if not url.startswith(GRAPH_ENDPOINT + "/v1.0/applications"):
                raise ValueError("Unexpected Graph application continuation endpoint.")
            response = requests.get(url, headers=gh, timeout=90)
            response.raise_for_status()
            body = response.json()
            for app in ([body] if ids else body.get("value", [])):
                name = app.get("displayName", app.get("appId", ""))
                for credkind, key in (("client secret", "passwordCredentials"), ("certificate credential", "keyCredentials")):
                    for cred in app.get(key, []) or []:
                        items.append({
                            "name": f"{name}: {cred.get('displayName') or credkind}", "kind": f"App {credkind}",
                            "source": "Entra ID application", "subscription": "",
                            "id": f"{app.get('id', '')}/{cred.get('keyId', '')}",
                            "expiry": _from_iso(cred.get("endDateTime")),
                            "recommendation": "Roll the credential before expiry and update the consumers.",
                        })
            url = body.get("@odata.nextLink")
            if ids and url:
                raise ValueError("Unexpected continuation for a scoped application object; directory enumeration not authorized.")
            if not url and pending:
                url = f"{GRAPH_ENDPOINT}/v1.0/applications/{pending.pop(0)}?{select}"
            pages += 1
        if url:
            notes.append("Application credential enumeration incomplete: page limit reached.")
    except Exception as error:  # noqa: BLE001
        notes.append(f"Application credentials from Microsoft Graph not fully assessed ({error}). Application.Read.All application permission with administrator consent is needed for this read; permissions do not replace approval of directory scope.")
    notes.append("Only approved application registrations assessed. Credentials on service principal objects are not enumerated.")

    return items, notes


def _arm_headers(credential):
    return {"Authorization": f"Bearer {credential.get_token(f'{ARM_ENDPOINT}/.default').token}", "Content-Type": "application/json"}


def main(horizon: int = HORIZON_DEFAULT, application_ids=None, allow_tenant_directory=False) -> dict:
    credential = _credential()
    headers = _arm_headers(credential)
    items, notes = _collect(headers, credential, application_ids, allow_tenant_directory)
    subs = {item.get("subscription") for item in items if item.get("subscription")}
    return build_report_data(items, int(horizon), len(subs), notes)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Read expiry metadata only.")
    parser.add_argument("horizon", nargs="?", type=int, default=HORIZON_DEFAULT)
    parser.add_argument("--application-ids", help="Approved application object ids, comma separated.")
    parser.add_argument("--allow-tenant-directory", action="store_true", help="Use only after explicit approval to enumerate tenant application registrations.")
    args = parser.parse_args()
    application_ids = [value.strip() for value in args.application_ids.split(",") if value.strip()] if args.application_ids else None
    print(json.dumps(main(args.horizon, application_ids, args.allow_tenant_directory)))

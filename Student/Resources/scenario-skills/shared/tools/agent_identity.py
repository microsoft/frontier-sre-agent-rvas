"""Deterministic credentials with no discovery or alternate identity fallback.

Production: set AZURE_CLIENT_ID to the selected user assigned identity client ID,
or set SRE_IDENTITY_MODE=system-assigned explicitly. SRE_IDENTITY_MODE=developer
opts in to the local DefaultAzureCredential chain, excluding managed identity.
Unset/ambiguous configuration and authentication failures propagate to the caller.

Bundled with every skill by shared/iac/deploy-skill.ps1, which flattens shared/tools and
the skill's own tools into one directory.
"""

import base64
import json
import os

ARM_ENDPOINT = "https://management.azure.com"
AGENT_API_VERSION = "2025-05-01-preview"

def token_claims(token):
    """The payload of a token this process already holds. Not a validation step."""
    body = token.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))


def agent_resource_id(token):
    """The agent resource a managed identity token was issued for, or None."""
    resource = token_claims(token).get("xms_mirid") or ""
    return resource if "/agents/" in resource.lower() else None


def resolve_agent_identity():
    """Return only the explicitly configured client ID; never enumerate identities."""
    return os.environ.get("AZURE_CLIENT_ID", "").strip() or None


def agent_credential(client_id=None):
    """Use one selected credential. No silent fallback if selection fails."""
    mode = os.environ.get("SRE_IDENTITY_MODE", "").strip().lower()
    selected = (client_id or resolve_agent_identity() or "").strip()
    if mode not in ("", "user-assigned", "system-assigned", "developer"):
        raise ValueError("Invalid SRE_IDENTITY_MODE.")
    if selected and mode in ("system-assigned", "developer"):
        raise ValueError("Client ID conflicts with SRE_IDENTITY_MODE.")
    if not selected and mode in ("", "user-assigned"):
        raise ValueError("Set AZURE_CLIENT_ID or explicitly choose SRE_IDENTITY_MODE.")
    from azure.identity import DefaultAzureCredential, ManagedIdentityCredential

    if selected:
        return ManagedIdentityCredential(client_id=selected)
    if mode == "system-assigned":
        return ManagedIdentityCredential()
    if mode == "developer":
        return DefaultAzureCredential(exclude_managed_identity_credential=True)


def agent_token(scope=None, client_id=None):
    return agent_credential(client_id).get_token(scope or f"{ARM_ENDPOINT}/.default").token


def arm_headers(client_id=None):
    return {"Authorization": f"Bearer {agent_token(client_id=client_id)}",
            "Content-Type": "application/json"}


def identity_report(client_id=None, scopes=None):
    """Which principal each audience resolves to. Answers 'authorization failed' fast."""
    client_id = client_id or resolve_agent_identity()
    report = {"client_id_in_use": client_id, "identity_mode": os.environ.get("SRE_IDENTITY_MODE") or "user-assigned"}
    for label, scope in (scopes or (("resource_manager", f"{ARM_ENDPOINT}/.default"),)):
        claims = token_claims(agent_token(scope, client_id))
        report[label] = {
            "object_id": claims.get("oid", ""),
            "app_id": claims.get("appid", ""),
            "identity_resource": claims.get("xms_mirid", ""),
        }
    return report

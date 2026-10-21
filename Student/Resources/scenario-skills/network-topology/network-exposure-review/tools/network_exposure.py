"""
network_exposure: Map the internet facing attack surface with Resource Graph.

Azure SRE Agent Python tool. Uses the agent managed identity (ARM scope) to query
Azure Resource Graph for inbound network security group rules open to the
internet, storage accounts with public or anonymous access, and platform services
with public network access, classifies each by severity, and prints a report_data
object as JSON ready to pipe into report_render.py.

    python network_exposure.py | python report_render.py

Heavy imports (azure-identity, requests) are lazy so the pure classification
helpers can be unit tested without them. See references/checks-catalog.md.
"""

import json
import ipaddress
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

INTERNET_SOURCES = {"*", "internet", "0.0.0.0/0", "::/0"}
SOURCES = [
    {"title": "NSG processing and effective rules", "url": "https://learn.microsoft.com/azure/virtual-network/network-security-group-how-it-works"},
    {"title": "SQL network access controls", "url": "https://learn.microsoft.com/azure/azure-sql/database/network-access-controls-overview"},
]
MGMT_PORTS = {22, 3389, 5985, 5986}
DB_PORTS = {1433, 3306, 5432, 6379, 27017, 1521}

TYPE_LABEL = {
    "microsoft.sql/servers": "SQL server",
    "microsoft.keyvault/vaults": "Key Vault",
    "microsoft.documentdb/databaseaccounts": "Cosmos DB",
    "microsoft.dbforpostgresql/flexibleservers": "PostgreSQL",
    "microsoft.dbformysql/flexibleservers": "MySQL",
}


def source_is_internet(source, sources):
    """True if scalar and plural prefixes together cover an address family."""
    return source_coverage(source, sources) == "Internet"


def source_coverage(source, sources):
    values = [str(value).strip().lower() for value in [source] + list(sources or []) if value]
    if any(value in INTERNET_SOURCES for value in values):
        return "Internet"
    networks, unknown = [], False
    for value in values:
        try:
            networks.append(ipaddress.ip_network(value, strict=False))
        except ValueError:
            unknown = True
    for version in (4, 6):
        if any(net.prefixlen == 0 for net in ipaddress.collapse_addresses([n for n in networks if n.version == version])):
            return "Internet"
    return "Unknown" if unknown or not values else "Restricted prefixes"


def port_in_spec(port, spec):
    """True when a port falls within a port spec ('22', '*', '1000-2000'). Pure."""
    spec = (spec or "").strip()
    if not spec:
        return False
    if spec == "*":
        return True
    if "-" in spec:
        try:
            low, high = spec.split("-", 1)
            return int(low) <= port <= int(high)
        except ValueError:
            return False
    return spec.isdigit() and int(spec) == port


def classify_open_ports(specs):
    """Return (severity, label) for a set of destination port specs. Pure."""
    specs = [s for s in specs if s]
    if any(s.strip() in ("*", "0-65535") for s in specs):
        return "Critical", "all ports allowed by configuration"
    if any(any(port_in_spec(p, s) for s in specs) for p in MGMT_PORTS):
        return "Critical", "management ports (SSH/RDP/WinRM) allowed by configuration"
    if any(any(port_in_spec(p, s) for s in specs) for p in DB_PORTS):
        return "High", "database ports allowed by configuration"
    return "Medium", "ports allowed by configuration"


def classify_nsg_rule(row):
    """Return a finding for an internet facing NSG rule, or None. Pure."""
    coverage = source_coverage(row.get("src"), row.get("srcs"))
    if coverage == "Restricted prefixes":
        return None
    specs = [row.get("portRange")] + list(row.get("portRanges") or [])
    specs = [s for s in specs if s]
    severity, label = classify_open_ports(specs) if specs else ("Medium", "destination ports unknown")
    if coverage == "Unknown":
        severity, label = "Medium", "source prefixes or service tags require review"
    ports = ", ".join(specs)
    return {
        "resource": row.get("name", ""),
        "exposure": "NSG allow configuration",
        "resource_id": row.get("id", ""),
        "rule_id": row.get("ruleId", ""),
        "source_coverage": coverage,
        "reachability": "Not assessed",
        "subscription": row.get("subscriptionId", ""),
        "resource_group": row.get("resourceGroup", ""),
        "detail": f"{row.get('ruleName', '')}: {label} (ports {ports or 'Unknown'}, source {coverage}, priority {row.get('priority', 'Unknown')}). Not effective reachability.",
        "recommendation": "Review rule precedence, subnet and NIC effective rules, protocol, destination, public IP association and routes before confirming exposure. Restrict sources where appropriate.",
        "severity": severity,
        "_band": severity,
    }


def _finding(row, exposure, detail, recommendation, severity, name=None, rtype=None):
    return {
        "resource": name or row.get("name", ""),
        "exposure": exposure,
        "resource_id": row.get("id", ""),
        "subscription": row.get("subscriptionId", ""),
        "resource_group": row.get("resourceGroup", ""),
        "detail": detail,
        "recommendation": recommendation,
        "severity": severity,
        "_band": severity,
    }


def classify_paas(row):
    """Public endpoint enablement alone does not establish unrestricted access."""
    if str(row.get("pna", "")).lower() == "disabled":
        return None
    return _finding(
        row, "PaaS public access",
        f"{TYPE_LABEL.get((row.get('type') or '').lower(), row.get('type', ''))}: publicNetworkAccess={row.get('pna') or 'Unknown'}. Firewall/default action and effective reachability not assessed.",
        "Review service firewall rules, defaultAction, IP and virtual network rules, trusted service exceptions and private endpoints before deciding whether public access is unrestricted.",
        "Medium",
    )


def build_report_data(findings, subs_scanned, notes):
    findings = sorted(findings, key=lambda f: SEVERITY_ORDER.get(f["severity"], 9))
    critical = sum(1 for f in findings if f["severity"] == "Critical")
    public_access = sum(1 for f in findings if f["exposure"] in ("Storage public access", "PaaS public access"))
    sev_counts, by_type = {}, {}
    for finding in findings:
        sev_counts[finding["severity"]] = sev_counts.get(finding["severity"], 0) + 1
        by_type[finding["exposure"]] = by_type.get(finding["exposure"], 0) + 1
    sev_items = [{"name": b, "value": sev_counts[b], "band": b} for b in ("Critical", "High", "Medium", "Low") if b in sev_counts]
    type_items = sorted(({"name": k, "value": v} for k, v in by_type.items()), key=lambda i: i["value"], reverse=True)
    return {
        "assessment_status": "Not assessed" if not subs_scanned else "Partial",
        "sources": SOURCES,
        "title": "Network Exposure Review",
        "subtitle": "Configuration review, not verified internet reachability.",
        "meta": {"window": "Point in time", "scope": f"{subs_scanned} subscription(s)", "source": "Azure Resource Graph"},
        "summary_cards": [
            {"label": "Resources to review", "value": f"{len({f.get('resource_id') or (f['subscription'], f['resource_group'], f['resource']) for f in findings}):,}"},
            {"label": "Critical configurations", "value": f"{critical:,}", "sub": "management or all ports"},
            {"label": "Public access", "value": f"{public_access:,}", "sub": "storage or PaaS"},
            {"label": "Subscriptions scanned", "value": str(subs_scanned)},
        ],
        "charts": [
            {"title": "Findings by severity", "unit": "findings", "items": sev_items},
            {"title": "Findings by exposure type", "unit": "findings", "items": type_items},
        ],
        "findings": {
            "title": "Exposure findings",
            "columns": ["resource", "resource_id", "exposure", "subscription", "resource_group", "detail", "recommendation", "severity"],
            "rows": findings,
        },
        "method_notes": notes + [
            "Broad sources include *, Internet, IPv4 0.0.0.0/0, IPv6 ::/0, and equivalent CIDR unions within one address family. Unresolved service tags or missing prefixes are review candidates, not proven exposure.",
            "NSG Allow entries are configuration candidates only. Priority, subnet and NIC rules, routes, protocol and destination may prevent reachability.",
            "Public network access enabled does not establish unrestricted SQL or PaaS access. Firewalls and service specific rules need review. Anonymous blob permission does not prove any container is public.",
            "Subscriptions with no matching rows and inaccessible or out of scope subscriptions are not assessed. No tenant completeness claim is made.",
            "A resource can appear more than once when it is exposed in more than one way.",
        ],
    }


def _headers():
    from agent_identity import agent_token

    token = agent_token(f"{ARM_ENDPOINT}/.default")
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


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


NSG_QUERY = (
    "resources | where type =~ 'microsoft.network/networksecuritygroups' "
    "| mv-expand rule = properties.securityRules | extend p = rule.properties "
    "| where tostring(p.direction) =~ 'Inbound' and tostring(p.access) =~ 'Allow' "
    "| project name, id, resourceGroup, subscriptionId, ruleName=tostring(rule.name), ruleId=tostring(rule.id), priority=p.priority, "
    "src=tostring(p.sourceAddressPrefix), srcs=p.sourceAddressPrefixes, "
    "portRange=tostring(p.destinationPortRange), portRanges=p.destinationPortRanges"
)


def main() -> dict:
    headers = _headers()
    notes, findings, scanned = [], [], set()

    def scan(query, handler):
        try:
            rows = _run_graph(headers, query)
        except Exception as error:  # noqa: BLE001
            notes.append(f"A query could not be read ({error}).")
            return
        for row in rows:
            scanned.add(row.get("subscriptionId"))
            handler(row)

    scan(NSG_QUERY, lambda row: (lambda f: findings.append(f) if f else None)(classify_nsg_rule(row)))
    scan(
        "resources | where type =~ 'microsoft.storage/storageaccounts' | where tostring(properties.allowBlobPublicAccess) =~ 'true' | project name, id, resourceGroup, subscriptionId",
        lambda row: findings.append(_finding(row, "Storage public access", "Account permits anonymous blob access; container access and network reachability not assessed.", "Review container access and firewalls. Set allowBlobPublicAccess to false unless anonymous access is an approved requirement.", "Medium")),
    )
    scan(
        "resources | where type =~ 'microsoft.storage/storageaccounts' | where tostring(properties.publicNetworkAccess) =~ 'Enabled' and tostring(properties.networkAcls.defaultAction) =~ 'Allow' | project name, id, resourceGroup, subscriptionId",
        lambda row: findings.append(_finding(row, "Storage public access", "Open to all networks (no firewall)", "Set the network default action to Deny and allow only known networks, or use Private Link.", "Medium")),
    )
    scan(
        "resources | where type =~ 'microsoft.storage/storageaccounts' | extend pna=tostring(properties.publicNetworkAccess), action=tostring(properties.networkAcls.defaultAction) | where pna !~ 'Disabled' and (isempty(pna) or isempty(action)) | project name, id, resourceGroup, subscriptionId",
        lambda row: findings.append(_finding(row, "Storage public access", "Public network access or firewall default action is missing; effective access not assessed.", "Review the service defaults, firewall rules and endpoint configuration before deciding exposure.", "Medium")),
    )
    scan(
        "resources | where type in~ ('microsoft.sql/servers','microsoft.keyvault/vaults','microsoft.documentdb/databaseaccounts','microsoft.dbforpostgresql/flexibleservers','microsoft.dbformysql/flexibleservers') | extend pna = tostring(properties.publicNetworkAccess) | where pna !~ 'Disabled' | project name, id, type, resourceGroup, subscriptionId, pna",
        lambda row: (lambda f: findings.append(f) if f else None)(classify_paas(row)),
    )

    return build_report_data(findings, len({s for s in scanned if s}), notes)


if __name__ == "__main__":
    print(json.dumps(main()))

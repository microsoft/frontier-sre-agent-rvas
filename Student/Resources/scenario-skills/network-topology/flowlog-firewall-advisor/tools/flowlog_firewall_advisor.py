"""flowlog_firewall_advisor: derive Azure Firewall network rules from VNet flow logs.

Azure SRE Agent Python tool. Reads VNet flow logs through Traffic Analytics,
reconstructs the connections that actually occurred, ranks them by severity, and
prints a report_data object as JSON for the shared renderer.

Read only throughout. Nothing is created, changed or deleted.

Azure imports are lazy so the analysis logic below can be unit tested without any
Azure dependency or credential. See test_flowlog_firewall_advisor.py.

Standard library plus azure-identity and requests at run time. Log Analytics is read
over its REST API. Validate dependencies in the selected host before execution.
"""

import argparse
import ipaddress
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
import re

_TOOLS_DIR = Path(__file__).resolve().parent
for _candidate in (_TOOLS_DIR, _TOOLS_DIR / "tools", *(parent / "shared" / "tools" for parent in _TOOLS_DIR.parents)):
    if (_candidate / "azure_http.py").is_file():
        if str(_candidate) not in sys.path:
            sys.path.insert(0, str(_candidate))
        break
from sharing import sanitized_copy

# Documented Azure Firewall policy limit. Unique source and destination combinations
# in network rules is protocols * sources * destinations * ceil(ports / 14), summed over
# every network rule in the policy.
# https://learn.microsoft.com/azure/azure-resource-manager/management/azure-subscription-service-limits
RULE_COMBINATION_LIMIT = 20000

# Delivered by the platform rather than routed through a firewall, so a rule for them
# consumes the policy budget for no effect.
PLATFORM_ADDRESSES = ("168.63.129.16",)
PLATFORM_NETWORKS = ("169.254.0.0/16", "127.0.0.0/8", "224.0.0.0/4")

# Reachable management ports across a trust boundary are the finding a security team
# acts on first.
MANAGEMENT_PORTS = {22, 3389, 5985, 5986, 23, 512, 513, 514}
DATABASE_PORTS = {1433, 3306, 5432, 1521, 27017, 6379, 9200, 5984, 11211}

# Traffic Analytics flow types that are internal by definition.
EAST_WEST_FLOW_TYPES = {"IntraVNet", "InterVNet", "UnknownPrivate", "Unknown Private"}

# Row cap sent into the tuple query, and the threshold for calling a result truncated.
TUPLE_QUERY_ROW_LIMIT = 200000

# Populated by query_workspace when the service truncates a result or the cap is hit.
# A rule set built from partial data looks exactly like one built from complete data,
# so the difference has to be carried into the report rather than inferred.
TRUNCATION = []
SKIPPED_WORKSPACES = []
SOURCES = [
    {"title": "Azure Firewall rule limits", "url": "https://learn.microsoft.com/azure/azure-resource-manager/management/azure-subscription-service-limits#azure-firewall-limits"},
    {"title": "Traffic Analytics scope columns", "url": "https://learn.microsoft.com/azure/azure-monitor/reference/tables/ntanetanalytics"},
]

ARG_FLOWLOG_QUERY = """
resources
| where type =~ 'microsoft.network/networkwatchers/flowlogs'
| extend fa = properties.flowAnalyticsConfiguration.networkWatcherFlowAnalyticsConfiguration
| extend targetResourceId = tostring(properties.targetResourceId)
| where targetResourceId has '/virtualNetworks/'
| project
    flowLogId = id,
    flowLogEnabled = tobool(properties.enabled),
    targetResourceId,
    trafficAnalyticsEnabled = tobool(fa.enabled),
    workspaceResourceId = tostring(fa.workspaceResourceId),
    workspaceCustomerId = tostring(fa.workspaceId),
    subscriptionId
"""

COVERAGE_QUERY = """
NTANetAnalytics
| where SubType =~ 'FlowLog'
| summarize Records = count(), FirstSeenUtc = min(TimeGenerated), LastSeenUtc = max(TimeGenerated)
"""

# SrcPorts is deliberately dropped: ephemeral client ports carry no policy meaning and
# would explode cardinality. Only the destination port describes the service reached.
TUPLE_QUERY = """
NTANetAnalytics
| where SubType =~ 'FlowLog'
| where isnotempty(SrcIp) and isnotempty(DestIp)
| extend
    Protocol  = case(L4Protocol =~ 'T', 'TCP', L4Protocol =~ 'U', 'UDP', toupper(tostring(L4Protocol))),
    Direction = case(FlowDirection =~ 'I', 'Inbound', FlowDirection =~ 'O', 'Outbound', tostring(FlowDirection)),
    Status    = case(FlowStatus =~ 'A', 'Allowed', FlowStatus =~ 'D', 'Denied', tostring(FlowStatus))
| summarize
    Flows = sum(coalesce(AllowedInFlows, tolong(0)) + coalesce(AllowedOutFlows, tolong(0))
              + coalesce(DeniedInFlows, tolong(0)) + coalesce(DeniedOutFlows, tolong(0))),
    Bytes = sum(coalesce(BytesSrcToDest, tolong(0)) + coalesce(BytesDestToSrc, tolong(0))),
    FirstSeenUtc = min(FlowStartTime),
    LastSeenUtc = max(FlowEndTime),
    DestTags = make_set(DestServiceTags, 5),
    AclRules = make_set(AclRule, 5)
    by SrcIp, DestIp, DestPort, Protocol, Direction, Status, FlowType, SrcVm, DestVm
| order by Bytes desc
| take {row_limit}
""".replace("{row_limit}", str(TUPLE_QUERY_ROW_LIMIT))


# ---------------------------------------------------------------------------
# Pure analysis. No Azure dependency, unit tested.
# ---------------------------------------------------------------------------

def is_platform_address(address):
    """True for addresses that must never become a firewall rule."""
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    if str(ip) in PLATFORM_ADDRESSES:
        return True
    return any(ip in ipaddress.ip_network(net) for net in PLATFORM_NETWORKS)


def is_private_address(address):
    """True for RFC 1918 and carrier grade NAT space."""
    try:
        return ipaddress.ip_address(address).is_private
    except ValueError:
        return False


def flow_axis(row):
    """Whether a flow stayed inside the network or crossed the boundary.

    Traffic Analytics labels a large share of private to private traffic `Unknown`
    rather than `IntraVNet`, so the addresses decide. Trusting the label alone ranks
    internal traffic as public egress and emits a second, duplicate rule for a pair
    already covered by an east west one.
    """
    if is_private_address(row.get("SrcIp")) and is_private_address(row.get("DestIp")):
        return "EastWest"
    return "EastWest" if row.get("FlowType") in EAST_WEST_FLOW_TYPES else "NorthSouth"


def merge_port_ranges(ports):
    """Collapse a port list into the shortest set of Azure Firewall expressions."""
    ordered = sorted({int(p) for p in ports if 0 <= int(p) <= 65535})
    if not ordered:
        return []
    ranges, start, previous = [], ordered[0], ordered[0]
    for port in ordered[1:]:
        if port == previous + 1:
            previous = port
            continue
        ranges.append(str(start) if start == previous else "%d-%d" % (start, previous))
        start = previous = port
    ranges.append(str(start) if start == previous else "%d-%d" % (start, previous))
    return ranges


def summarise_addresses(addresses, collapse_threshold=4):
    """Collapse addresses into the shortest honest CIDR list.

    Individual addresses stay as /32 until enough of them share a /24. Collapsing is
    a genuine widening, so it is returned separately and never applied silently.
    """
    unique = sorted({a for a in addresses if a})
    if not unique:
        return [], []

    by_network = defaultdict(list)
    passthrough = []
    for address in unique:
        try:
            network = str(ipaddress.ip_network(address + "/24", strict=False))
            by_network[network].append(address)
        except ValueError:
            passthrough.append(address)

    result, collapsed = [], []
    for network, members in sorted(by_network.items()):
        if len(members) >= collapse_threshold:
            result.append(network)
            collapsed.append({"network": network, "observed_hosts": sorted(members)})
        else:
            result.extend("%s/32" % m for m in sorted(members))
    result.extend(passthrough)
    return sorted(set(result)), collapsed


def port_expression_count(expressions):
    """Worst case port count, expanding ranges, for the policy budget calculation."""
    total = 0
    for expression in expressions:
        if "-" in expression:
            low, high = expression.split("-", 1)
            total += int(high) - int(low) + 1
        else:
            total += 1
    return total


def rule_combinations(protocol_count, source_count, destination_count, port_count):
    """Documented network rule budget, with destination ports grouped in 14s."""
    return protocol_count * source_count * destination_count * ((port_count + 13) // 14)


def scoped_query(query, subscription="", targets=()):
    """Filter the logging target, not merely an endpoint or report label."""
    filters = []
    if subscription:
        if not re.fullmatch(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", subscription):
            raise ValueError("--subscription must be a subscription GUID")
        filters.append("| where tolower(TargetResourceId) startswith '/subscriptions/%s/'" % subscription.lower())
    if targets:
        clauses = []
        for target in targets:
            if not re.fullmatch(r"/subscriptions/[0-9a-fA-F-]{36}/resourceGroups/[A-Za-z0-9_.()-]+/providers/Microsoft.Network/virtualNetworks/[A-Za-z0-9_.()-]+(?:/subnets/[A-Za-z0-9_.()-]+)?", target, re.I):
                raise ValueError("--target-resource must be a full VNet or subnet resource ID")
            target = target.lower().rstrip("/")
            if subscription and not target.startswith("/subscriptions/" + subscription.lower() + "/"):
                raise ValueError("The target resource must belong to --subscription")
            clauses.append("(tolower(TargetResourceId) == '%s' or tolower(TargetResourceId) startswith '%s/')" % (target, target))
        filters.append("| where " + " or ".join(clauses))
    return query.replace("| where SubType =~ 'FlowLog'", "| where SubType =~ 'FlowLog'\n" + "\n".join(filters), 1)


def build_denied_keys(tuples):
    """Connection keys denied at any evaluation point.

    Flow logs record a verdict per evaluation point, so one blocked connection appears
    twice: allowed leaving the source, denied arriving at the destination. Taking the
    allowed record at face value produces a rule permitting traffic the current policy
    blocks, silently widening access at cutover. Anything denied anywhere is excluded
    everywhere.
    """
    denied = set()
    for row in tuples:
        if row.get("Status") != "Allowed":
            denied.add((row.get("SrcIp"), row.get("DestIp"), row.get("DestPort"), row.get("Protocol")))
    return denied


def service_tag_for(row):
    """Resolved destination service tag, which is stable where an IP literal is not."""
    for tag in row.get("DestTags") or []:
        if tag and "|" in tag:
            return tag.rsplit("|", 1)[-1]
    return None


def classify(sources, destinations, ports, dest_is_tag, axis):
    """Severity and reason for a proposed rule. Blast radius, not effort."""
    port_numbers = set()
    for expression in ports:
        if "-" in expression:
            low, high = expression.split("-", 1)
            port_numbers.update(range(int(low), min(int(high), int(low) + 4096) + 1))
        else:
            port_numbers.add(int(expression))

    management = sorted(port_numbers & MANAGEMENT_PORTS)
    database = sorted(port_numbers & DATABASE_PORTS)
    wide_source = any(not s.endswith("/32") for s in sources)

    if management and axis == "NorthSouth":
        return "Critical", "Management ports %s reachable across the virtual network boundary" % (
            ", ".join(str(p) for p in management))
    if management:
        return "Critical", "Management ports %s reachable between subnets" % (
            ", ".join(str(p) for p in management))
    if len(port_numbers) > 64:
        return "Critical", "%d ports in one rule, which is close to any to any" % len(port_numbers)
    if axis == "NorthSouth" and not dest_is_tag:
        return "High", "Egress to public addresses with no service tag, so the rule pins IP literals that change"
    if database and axis == "NorthSouth":
        return "High", "Database ports %s crossing the virtual network boundary" % (
            ", ".join(str(p) for p in database))
    if wide_source:
        return "Medium", "Source is a subnet rather than specific hosts, so the rule is broader than what was seen"
    if len(destinations) > 8:
        return "Medium", "One source reaching %d destinations" % len(destinations)
    return "Low", "Service traffic between known endpoints"


def build_rules(tuples, min_flows=1, collapse_threshold=4):
    """Consolidate observed connections into proposed rules.

    Merging is lossless. Rules combine only on an exact signature match, so every
    source, destination and port combination in a rule was observed. The one widening
    is host to subnet collapsing, which is reported separately.
    """
    denied_keys = build_denied_keys(tuples)

    candidates = []
    excluded = {"platform": 0, "denied": 0, "blocked_elsewhere": 0, "below_threshold": 0}
    denied_rows, blocked_rows = [], []

    for row in tuples:
        source, destination = row.get("SrcIp"), row.get("DestIp")
        if is_platform_address(source) or is_platform_address(destination):
            excluded["platform"] += 1
            continue
        if row.get("Status") != "Allowed":
            excluded["denied"] += 1
            denied_rows.append(row)
            continue
        if (source, destination, row.get("DestPort"), row.get("Protocol")) in denied_keys:
            excluded["blocked_elsewhere"] += 1
            blocked_rows.append(row)
            continue
        if int(row.get("Flows") or 0) < min_flows:
            excluded["below_threshold"] += 1
            continue

        tag = service_tag_for(row)
        axis = flow_axis(row)
        candidates.append({
            "axis": axis,
            "protocol": row.get("Protocol") or "TCP",
            "source": source,
            "destination": tag or destination,
            "dest_is_tag": tag is not None,
            "port": int(row.get("DestPort") or 0),
            "flows": int(row.get("Flows") or 0),
            "bytes": int(row.get("Bytes") or 0),
            "first_seen": row.get("FirstSeenUtc"),
            "last_seen": row.get("LastSeenUtc"),
        })

    # Stage 1: pool ports for each axis, protocol, source and destination triple.
    stage1 = defaultdict(lambda: {"ports": set(), "flows": 0, "bytes": 0, "first": None, "last": None})
    for item in candidates:
        key = (item["axis"], item["protocol"], item["source"], item["destination"], item["dest_is_tag"])
        bucket = stage1[key]
        bucket["ports"].add(item["port"])
        bucket["flows"] += item["flows"]
        bucket["bytes"] += item["bytes"]
        for field, name in (("first_seen", "first"), ("last_seen", "last")):
            value = item.get(field)
            if value and (bucket[name] is None
                          or (name == "first" and value < bucket[name])
                          or (name == "last" and value > bucket[name])):
                bucket[name] = value

    # Stage 2: identical destination and port signature, so pool the sources. Every
    # resulting source to destination pair was observed; no combination is invented.
    stage2 = defaultdict(lambda: {"sources": set(), "flows": 0, "bytes": 0, "first": None, "last": None})
    for (axis, protocol, source, destination, is_tag), bucket in stage1.items():
        signature = (axis, protocol, destination, is_tag, tuple(sorted(bucket["ports"])))
        merged = stage2[signature]
        merged["sources"].add(source)
        merged["flows"] += bucket["flows"]
        merged["bytes"] += bucket["bytes"]
        for name in ("first", "last"):
            value = bucket[name]
            if value and (merged[name] is None
                          or (name == "first" and value < merged[name])
                          or (name == "last" and value > merged[name])):
                merged[name] = value

    # Stage 3: identical source set and port signature, so pool the destinations.
    stage3 = defaultdict(lambda: {"destinations": set(), "sources": set(), "flows": 0,
                                  "bytes": 0, "first": None, "last": None})
    for (axis, protocol, destination, is_tag, ports), merged in stage2.items():
        signature = (axis, protocol, tuple(sorted(merged["sources"])), is_tag, ports)
        final = stage3[signature]
        final["destinations"].add(destination)
        final["sources"] = set(merged["sources"])
        final["flows"] += merged["flows"]
        final["bytes"] += merged["bytes"]
        for name in ("first", "last"):
            value = merged[name]
            if value and (final[name] is None
                          or (name == "first" and value < final[name])
                          or (name == "last" and value > final[name])):
                final[name] = value

    rules, collapsed_all, combinations = [], [], 0
    counters = defaultdict(int)

    for (axis, protocol, sources, is_tag, ports), final in sorted(
            stage3.items(), key=lambda kv: kv[1]["bytes"], reverse=True):
        source_list, source_collapsed = summarise_addresses(sources, collapse_threshold)
        collapsed_all.extend(source_collapsed)

        if is_tag:
            destination_list = sorted(final["destinations"])
        else:
            destination_list, dest_collapsed = summarise_addresses(final["destinations"], collapse_threshold)
            collapsed_all.extend(dest_collapsed)

        port_expressions = merge_port_ranges(ports)
        combinations += rule_combinations(1, len(source_list), len(destination_list), port_expression_count(port_expressions))

        counters[axis] += 1
        severity, reason = classify(source_list, destination_list, port_expressions, is_tag, axis)
        rules.append({
            "name": "%s-%s-%03d" % ("ns" if axis == "NorthSouth" else "ew", protocol.lower(), counters[axis]),
            "axis": axis,
            "protocol": protocol,
            "sources": source_list,
            "destinations": destination_list,
            "ports": port_expressions,
            "destination_is_service_tag": is_tag,
            "severity": severity,
            "reason": reason,
            "flows": final["flows"],
            "bytes": final["bytes"],
            "first_seen": final["first"],
            "last_seen": final["last"],
        })

    # Fold duplicate widenings so the review list does not repeat itself.
    unique_collapsed = {}
    for entry in collapsed_all:
        existing = unique_collapsed.setdefault(entry["network"], set())
        existing.update(entry["observed_hosts"])
    collapsed = [{"network": k, "observed_hosts": sorted(v)} for k, v in sorted(unique_collapsed.items())]

    return {
        "rules": rules,
        "collapsed": collapsed,
        "excluded": excluded,
        "denied_rows": denied_rows,
        "blocked_rows": blocked_rows,
        "combinations": combinations,
    }


def human_bytes(value):
    value = float(value or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return "%.1f %s" % (value, unit) if unit != "B" else "%d B" % value
        value /= 1024
    return "%.1f TB" % value


def build_report(analysis, meta, include_identifiers=False):
    """Shape the analysis into the report_data object the shared renderer expects."""
    safe = sanitized_copy({"analysis": analysis, "meta": meta}, include_identifiers=include_identifiers)
    analysis, meta = safe["analysis"], safe["meta"]
    rules = analysis["rules"]
    excluded = analysis["excluded"]
    combinations = analysis["combinations"]
    budget_percent = (combinations / RULE_COMBINATION_LIMIT * 100.0) if RULE_COMBINATION_LIMIT else 0.0

    severity_counts = defaultdict(int)
    for rule in rules:
        severity_counts[rule["severity"]] += 1

    cards = [
        {"label": "Proposed rules", "value": len(rules), "sub": "from %s connections" % meta.get("tuple_count", 0)},
        {"label": "Critical and high", "value": severity_counts["Critical"] + severity_counts["High"],
         "sub": "need review before deploying"},
        {"label": "Policy budget", "value": "%.1f%%" % budget_percent,
         "sub": "%s of %s combinations" % (combinations, RULE_COMBINATION_LIMIT)},
        {"label": "Already blocked", "value": excluded["denied"] + excluded["blocked_elsewhere"],
         "sub": "excluded from the rules"},
    ]

    by_axis = defaultdict(int)
    for rule in rules:
        by_axis[rule["axis"]] += rule["bytes"]
    charts = [{
        "title": "Volume by traffic direction",
        "unit": "bytes",
        "items": [{"name": "Crossing the VNet boundary" if axis == "NorthSouth" else "Inside the VNet",
                   "value": total, "band": "High" if axis == "NorthSouth" else "Low"}
                  for axis, total in sorted(by_axis.items(), key=lambda kv: kv[1], reverse=True)],
    }]

    rows = []
    for rule in rules:
        rows.append({
            "rule": rule["name"],
            "severity": rule["severity"],
            "direction": "Boundary" if rule["axis"] == "NorthSouth" else "Internal",
            "sources": _summarise_list(rule["sources"]),
            "destinations": _summarise_list(rule["destinations"]),
            "ports": ", ".join(rule["ports"]),
            "volume": human_bytes(rule["bytes"]),
            "last_seen": (rule["last_seen"] or "")[:19],
            "why": rule["reason"],
            "_band": rule["severity"],
        })

    candidates = []
    for rule in rules:
        candidates.append({
            "resource": rule["name"],
            "resource_type": "%s network rule" % rule["protocol"],
            "subscription": meta.get("subscription", ""),
            "resource_group": "",
            "band": {"Critical": "Low", "High": "Medium", "Medium": "High", "Low": "Very high"}.get(
                rule["severity"], "Medium"),
            "confidence": rule["flows"],
            "reason": "%s. Seen %s times, %s." % (rule["reason"], rule["flows"], human_bytes(rule["bytes"])),
            "next_step": "Confirm this traffic is intended, then add it to the firewall policy",
            "command": _bicep_snippet(rule),
        })

    notes = [
        "Window analysed: %s. Traffic that did not occur inside it is absent from these rules, "
        "so anything running monthly will be missing from a shorter capture." % meta.get("window", "unknown"),
        "Rules merge only on an exact match, so every source, destination and port combination "
        "in a rule was observed. Host to subnet widening is listed separately.",
        "%s connection(s) were permitted at one point and denied at another, so they never completed. "
        "They are excluded, because allowing them would widen the policy beyond what works today."
        % excluded["blocked_elsewhere"],
        "%s platform flow(s) excluded. The host endpoint, instance metadata, link local, loopback and "
        "multicast are delivered by the platform and are not routed through a firewall."
        % excluded["platform"],
        "Network rules only. Application rules need fully qualified domain names, which IP flow logs "
        "do not carry. Public destinations stay IP literals unless a service tag was resolved.",
        "Keep this as a draft. Test intended allow and deny paths in an isolated staging environment, obtain owner approval, then use a controlled deployment with rollback. No universal non enforcing mode is assumed.",
        "Only the explicitly selected workspace is queried. Other workspaces are not assessed. TargetResourceId filters constrain the logging VNet or subnet, not every resource with an endpoint in that subscription.",
        "Policy budget = protocol count * source count * destination count * ceil(destination port count / 14), summed per rule. Existing policy rules consume additional budget.",
    ]
    if analysis["collapsed"]:
        notes.insert(2, "%s address group(s) were widened from observed hosts to a /24 and now permit "
                        "addresses never seen: %s." % (len(analysis["collapsed"]),
                                                       ", ".join(c["network"] for c in analysis["collapsed"][:8])))
    if combinations > RULE_COMBINATION_LIMIT:
        notes.insert(0, "These rules need %s unique combinations, above the documented Azure Firewall policy "
                        "limit of %s. Raise the minimum flow count or narrow the scope."
                        % (combinations, RULE_COMBINATION_LIMIT))

    # First, ahead of everything else. An incomplete rule set presented as complete is
    # the failure this whole tool exists to avoid.
    for reason in reversed(TRUNCATION):
        notes.insert(0, "Incomplete data. %s" % reason)

    return {
        "assessment_status": "Partial" if TRUNCATION or SKIPPED_WORKSPACES else "Complete",
        "sources": SOURCES,
        "sharing_review": safe["sharing_review"],
        "skipped_workspaces": sanitized_copy({"items": SKIPPED_WORKSPACES}, include_identifiers=include_identifiers)["items"],
        "title": "Flow log firewall advisor",
        "subtitle": "Azure Firewall network rules derived from observed virtual network traffic",
        "meta": {"window": meta.get("window", ""), "scope": meta.get("scope", ""),
                 "source": "VNet flow logs via Traffic Analytics"},
        "summary_cards": cards,
        "charts": charts,
        "findings": {
            "title": "Proposed rules and why",
            "columns": [
                {"key": "rule", "label": "Rule"},
                {"key": "severity", "label": "Severity"},
                {"key": "direction", "label": "Direction"},
                {"key": "sources", "label": "Sources"},
                {"key": "destinations", "label": "Destinations"},
                {"key": "ports", "label": "Ports"},
                {"key": "volume", "label": "Volume"},
                {"key": "last_seen", "label": "Last seen"},
                {"key": "why", "label": "Why it is ranked here"},
            ],
            "rows": rows,
        },
        "candidates": candidates,
        "method_notes": notes,
    }


def _summarise_list(values, limit=3):
    values = list(values)
    if len(values) <= limit:
        return ", ".join(values)
    return "%s and %d more" % (", ".join(values[:limit]), len(values) - limit)


def _bicep_snippet(rule):
    return (
        "{ ruleType: 'NetworkRule' name: '%s' ipProtocols: ['%s'] "
        "sourceAddresses: [%s] destinationAddresses: [%s] destinationPorts: [%s] }"
        % (rule["name"], rule["protocol"],
           " ".join("'%s'" % s for s in rule["sources"]),
           " ".join("'%s'" % d for d in rule["destinations"]),
           " ".join("'%s'" % p for p in rule["ports"]))
    )


# ---------------------------------------------------------------------------
# Azure access. Imported lazily so the logic above stays testable.
# ---------------------------------------------------------------------------

def _credential(client_id=None):
    from agent_identity import agent_credential

    return agent_credential(client_id)


def resolve_agent_identity():
    from agent_identity import resolve_agent_identity as resolve

    return resolve()


def identity_report(client_id=None):
    """Which principal each audience resolves to. Answers 'authorization failed' quickly."""
    from agent_identity import identity_report as report

    return report(client_id, scopes=(
        ("resource_manager", "https://management.azure.com/.default"),
        ("log_analytics", "https://api.loganalytics.io/.default"),
    ))


def discover_workspaces(client_id=None, subscription="", targets=()):
    """Workspaces receiving VNet flow logs, grouped and ranked by enabled flow logs."""
    import azure_http as requests

    token = _credential(client_id).get_token("https://management.azure.com/.default").token
    payload = {"query": ARG_FLOWLOG_QUERY, "options": {"resultFormat": "objectArray", "top": 1000}}
    if subscription:
        scoped_query(COVERAGE_QUERY, subscription, targets)
        payload["subscriptions"] = [subscription]
    response = requests.post(
        "https://management.azure.com/providers/Microsoft.ResourceGraph/resources?api-version=2022-10-01",
        headers={"Authorization": "Bearer %s" % token, "Content-Type": "application/json"},
        json=payload,
        timeout=120,
    )
    response.raise_for_status()

    body = response.json()
    if not isinstance(body.get("data"), list):
        raise ValueError("Incomplete workspace discovery response: data missing")
    if body.get("$skipToken") or str(body.get("resultTruncated", "")).lower() == "true":
        TRUNCATION.append("Workspace discovery is incomplete: Resource Graph first page only (1000 row cap).")
    grouped = defaultdict(lambda: {"enabled": 0, "total": 0})
    for row in body.get("data", []):
        if targets and not any((row.get("targetResourceId") or "").lower().rstrip("/") == t.lower().rstrip("/")
                               or (row.get("targetResourceId") or "").lower().startswith(t.lower().rstrip("/") + "/") for t in targets):
            continue
        if not row.get("trafficAnalyticsEnabled") or not row.get("workspaceCustomerId") or not row.get("flowLogEnabled"):
            SKIPPED_WORKSPACES.append({"workspace_resource_id": row.get("workspaceResourceId", ""), "target_resource_id": row.get("targetResourceId", ""),
                                       "reason": "Traffic Analytics disabled, workspace ID missing or flow log disabled"})
            continue
        entry = grouped[(row["workspaceCustomerId"], row.get("workspaceResourceId", ""))]
        entry["total"] += 1
        if row.get("flowLogEnabled"):
            entry["enabled"] += 1

    return sorted(
        [{"workspace_customer_id": k[0], "workspace_resource_id": k[1], **v} for k, v in grouped.items()],
        key=lambda w: (w["enabled"], w["total"]), reverse=True)


def _iso(moment):
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_utc(value):
    """Parse a Log Analytics timestamp, whose fractional second can carry 7 digits."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value).strip()
    if text[-1:] in ("Z", "z"):
        text = text[:-1]
    head, _, fraction = text.partition(".")
    if fraction.isdigit():
        text = "%s.%s" % (head, fraction[:6])
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)


def query_workspace(workspace_id, query, start, end, client_id=None):
    """Run a KQL query against a workspace over an explicit time range.

    Records truncation in TRUNCATION so the caller can report an incomplete result
    rather than presenting it as the whole picture. The service signals a truncated
    result set with HTTP 200 and a populated error node, not with a failure status,
    so a caller that only reads the tables silently loses rows.
    """
    import azure_http as requests

    token = _credential(client_id).get_token("https://api.loganalytics.io/.default").token
    response = requests.post(
        "https://api.loganalytics.io/v1/workspaces/%s/query" % workspace_id,
        headers={"Authorization": "Bearer %s" % token, "Content-Type": "application/json"},
        json={"query": query, "timespan": "%s/%s" % (_iso(start), _iso(end))},
        timeout=300,
    )
    if response.status_code != 200:
        detail = ""
        if response.status_code in (401, 403):
            detail = (" Authenticated as %s, which needs Log Analytics Reader on the workspace. "
                      "Run --whoami to see every identity available, and --client-id to pin one."
                      % json.dumps(identity_report(client_id).get("log_analytics", {})))
        raise RuntimeError("Log Analytics query failed for workspace %s: HTTP %s %s.%s"
                           % (workspace_id, response.status_code, response.text[:400], detail))

    payload = response.json()
    if payload.get("error"):
        TRUNCATION.append(
            "The service returned a partial result: %s. Narrow the window with --days and "
            "re-run, because the rules below are missing traffic."
            % str(payload["error"].get("message") or payload["error"])[:300])

    tables = payload.get("tables") or []
    if not tables:
        raise RuntimeError("Incomplete Log Analytics response: result tables are missing")
    columns = [column["name"] for column in tables[0].get("columns") or []]
    rows = [dict(zip(columns, row)) for row in tables[0].get("rows") or []]

    if len(rows) >= TUPLE_QUERY_ROW_LIMIT:
        TRUNCATION.append(
            "The result hit the %s row cap, so distinct connections beyond it were dropped. "
            "Narrow the window with --days, or raise the minimum flow count."
            % TUPLE_QUERY_ROW_LIMIT)

    return rows


def main(argv=None):
    TRUNCATION.clear()
    SKIPPED_WORKSPACES.clear()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--discover", action="store_true", help="list workspaces receiving VNet flow logs")
    parser.add_argument("--coverage", action="store_true", help="report what the workspace actually holds")
    parser.add_argument("--workspace", help="Log Analytics workspace GUID")
    parser.add_argument("--days", type=int, default=7, help="lookback window in days")
    parser.add_argument("--min-flows", type=int, default=1, help="ignore connections seen fewer times than this")
    parser.add_argument("--subscription", default="", help="subscription GUID of the logging target, filters collection")
    parser.add_argument("--target-resource", action="append", default=[], help="full VNet or subnet ID, repeat to include multiple logging targets")
    parser.add_argument("--include-identifiers", action="store_true", help="include identifiers in the internal draft; credentials remain redacted")
    parser.add_argument("--client-id", default="", help="managed identity client id to authenticate as")
    parser.add_argument("--whoami", action="store_true", help="print the identity each Azure audience resolves to")
    args = parser.parse_args(argv)
    if args.days < 1 or args.min_flows < 1:
        parser.error("--days and --min-flows must be positive")
    query = scoped_query(TUPLE_QUERY, args.subscription, args.target_resource)
    coverage_query = scoped_query(COVERAGE_QUERY, args.subscription, args.target_resource)
    client_id = args.client_id or os.environ.get("AZURE_CLIENT_ID") or resolve_agent_identity()

    if args.whoami:
        print(json.dumps(identity_report(client_id), indent=2))
        return 0

    if args.discover:
        try:
            workspaces = discover_workspaces(client_id, args.subscription, args.target_resource)
        except Exception:
            workspaces = []
            TRUNCATION.append("Workspace discovery failed; workspace coverage is unknown.")
        result = {"workspaces": workspaces, "skipped_workspaces": SKIPPED_WORKSPACES,
                  "assessment_status": "Not assessed" if not workspaces else ("Partial" if TRUNCATION or SKIPPED_WORKSPACES else "Complete"),
                  "method_notes": TRUNCATION, "sources": SOURCES}
        print(json.dumps(sanitized_copy(result, include_identifiers=args.include_identifiers), indent=2))
        return 0

    if not args.workspace:
        parser.error("--workspace is required unless --discover is used")

    now = datetime.now(timezone.utc)

    if args.coverage:
        try:
            rows = query_workspace(args.workspace, coverage_query, now - timedelta(days=400), now, client_id)
        except Exception:
            rows = []
            TRUNCATION.append("Selected workspace query failed; data coverage is unknown.")
        summary = rows[0] if rows else {}
        records = int(summary.get("Records") or 0)
        last_seen = summary.get("LastSeenUtc")
        stale_hours = None
        if last_seen:
            stale_hours = round((now - _parse_utc(last_seen)).total_seconds() / 3600.0, 1)
        print(json.dumps({
            "assessment_status": "Partial" if TRUNCATION else "Complete",
            "sources": SOURCES,
            "method_notes": TRUNCATION,
            "records": records if not TRUNCATION else None,
            "first_seen": str(summary.get("FirstSeenUtc") or ""),
            "last_seen": str(last_seen or ""),
            "stale_hours": stale_hours,
            "verdict": "Unknown" if TRUNCATION else ("Empty" if records == 0 else ("Stale" if (stale_hours or 0) > 3 else "Ok")),
        }, indent=2))
        return 0

    start = now - timedelta(days=args.days)
    # Traffic Analytics ingests in batches, so every record in the newest batch shares a
    # TimeGenerated. Ending exactly at the last record drops that whole batch, because the
    # query interval excludes its upper bound. A minute of margin keeps the newest traffic.
    try:
        tuples = query_workspace(args.workspace, query, start, now + timedelta(minutes=1), client_id)
    except Exception:
        tuples = []
        SKIPPED_WORKSPACES.append({"workspace": args.workspace, "reason": "Query failed; traffic and rules not assessed"})
        TRUNCATION.append("Selected workspace query failed. No empty or complete traffic conclusion is possible.")

    analysis = build_rules(tuples, min_flows=args.min_flows)
    report = build_report(analysis, {
        "window": "%s to %s UTC (%s days)" % (start.strftime("%Y-%m-%d %H:%M"),
                                              (now + timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M"), args.days),
        "scope": "workspace %s; target subscription %s; targets %s" % (args.workspace, args.subscription or "all in workspace", ", ".join(args.target_resource) or "all in workspace"),
        "subscription": args.subscription,
        "tuple_count": len(tuples),
    }, include_identifiers=args.include_identifiers)
    print(json.dumps(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())

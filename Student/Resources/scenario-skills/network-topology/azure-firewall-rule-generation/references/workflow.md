# Evidence collection and analysis

## Collection

### 1. Firewall and policy association

Determine classic rule collections versus attached Firewall Policy. A policy managed firewall must not receive a classic rule deployment proposal without adapting it to the policy.

```azurecli
az network firewall show --subscription "<subscription_id>" --resource-group "<resource_group>" --name "<firewall_name>" --output json
```

### 2. Attached policy collection groups

Execute only in policy mode for the actually attached approved policy. Read basePolicy recursively only within separately approved parent scope, validate DNS settings and collection/group name and priority collisions. Follow CLI next-token if the response is truncated. Classic mode skips this collector.

```azurecli
az network firewall policy show --subscription "<subscription_id>" --resource-group "<policy_resource_group>" --name "<policy_name>" --output json
az network firewall policy rule-collection-group list --subscription "<subscription_id>" --resource-group "<policy_resource_group>" --policy-name "<policy_name>" --output json
```

### 3. Existing rule and subnet evidence

Page with --skip-token from skipToken. Resolve source subnet membership and routes, collection priorities, overlaps and inherited policy rules. Child rule collection groups omitted by ARG require authorized policy list/show reads before readiness.

```azurecli
az graph query --subscriptions "<subscription_id>" --first 1000 -q "Resources | where type in~ ('microsoft.network/azurefirewalls','microsoft.network/firewallpolicies','microsoft.network/firewallpolicies/rulecollectiongroups','microsoft.network/virtualnetworks','microsoft.network/routetables') | project id, name, type, resourceGroup, properties" --output json
```

### 4. Local classic or policy proposal with deployment text only

Only creates local JSON and sibling Bicep files, never runs the stored CLI arguments. The policy branch adds a reviewed new collection group to the observed existing policy; classic Bicep is an explicitly labeled merge fragment, not a partial firewall deployment. Validate all supplied tokens and safely escape substitutions in the host before running. Existing files, unresolved inputs and unsupported scopes fail closed.

```python
import json, ipaddress, re, uuid
from pathlib import Path
root = Path.cwd().resolve()
p = (root / '<artifact_path>').resolve()
bicep_path = p.with_suffix('.bicep')
assert root in p.parents and '<' not in str(p) and not p.exists() and not bicep_path.exists() and p != bicep_path
sub = str(uuid.UUID('<subscription_id>'))
rg, fw, name, coll = '<resource_group>', '<firewall_name>', '<rule_name>', '<collection_name>'
mode, policy, policy_rg, group = '<management_mode>', '<policy_name>', '<policy_resource_group>', '<group_name>'
assert mode in ('classic', 'policy')
assert all(re.fullmatch(r'[A-Za-z0-9_.-]{1,80}', v) for v in (rg, fw, name, coll, policy, policy_rg, group))
assert re.fullmatch(r'[A-Za-z0-9]+-(?:inbound|outbound)-[A-Za-z0-9]+', name)
protocol = '<protocol>'.upper()
assert protocol in ('TCP', 'UDP')
source = str(ipaddress.ip_network('<source_cidr>', strict=True))
assert ipaddress.ip_network(source).prefixlen > 0
destination = '<destination>'
is_fqdn = False
try:
    destination = str(ipaddress.ip_network(destination, strict=False))
    assert ipaddress.ip_network(destination).prefixlen > 0
except ValueError:
    assert len(destination) <= 253 and re.fullmatch(r'(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}', destination)
    destination = destination.lower()
    is_fqdn = True
    assert '<dns_proxy_verified>'.lower() == 'true'
ports = '<ports>'.split(',')
for port in ports:
    assert re.fullmatch(r'[0-9]+(?:-[0-9]+)?', port)
    bounds = [int(v) for v in port.split('-')]
    assert all(1 <= v <= 65535 for v in bounds) and bounds[0] <= bounds[-1]
priority = int('<priority>')
assert 100 <= priority <= 65000
destination_key = 'destinationFqdns' if is_fqdn else 'destinationAddresses'
rule = {'name': name, 'sourceAddresses': [source], destination_key: [destination], 'destinationPorts': ports}
def json_expression(value):
    return "json('''\n" + json.dumps(value, indent=2) + "\n''')"
if mode == 'classic':
    rule['protocols'] = [protocol]
    collection = {'name': coll, 'properties': {'priority': priority, 'action': {'type': 'Allow'}, 'rules': [rule]}}
    cli = ['az', 'network', 'firewall', 'network-rule', 'create', '--subscription', sub, '--resource-group', rg, '--firewall-name', fw, '--collection-name', coll, '--name', name, '--protocols', protocol, '--source-addresses', source, '--destination-fqdns' if is_fqdn else '--destination-addresses', destination, '--destination-ports'] + ports + ['--action', 'Allow', '--priority', str(priority)]
    bicep = '// DRAFT FRAGMENT. Merge into the complete existing firewall properties, preserving every existing collection.\nvar proposedNetworkRuleCollections = ' + json_expression([collection]) + '\noutput reviewedCollections array = proposedNetworkRuleCollections\n'
else:
    assert 'not-applicable' not in (policy, policy_rg, group)
    rule.update({'ruleType': 'NetworkRule', 'ipProtocols': [protocol]})
    collection = {'name': coll, 'priority': priority, 'ruleCollectionType': 'FirewallPolicyFilterRuleCollection', 'action': {'type': 'Allow'}, 'rules': [rule]}
    props = {'priority': priority, 'ruleCollections': [collection]}
    bicep = "// DRAFT ONLY. New group name must be unused. Existing groups are not replaced.\nresource policy 'Microsoft.Network/firewallPolicies@2024-05-01' existing = {\n  name: '" + policy + "'\n}\nresource proposedGroup 'Microsoft.Network/firewallPolicies/ruleCollectionGroups@2024-05-01' = {\n  parent: policy\n  name: '" + group + "'\n  properties: " + json_expression(props) + '\n}\n'
    cli = ['az', 'deployment', 'group', 'create', '--subscription', sub, '--resource-group', policy_rg, '--template-file', str(bicep_path)]
draft = {'status': 'DraftNotExecuted', 'target_mode': mode, 'rule': rule, 'collection': collection, 'cli_never_executed': cli, 'bicep_artifact': str(bicep_path.relative_to(root)), 'bicep_content': bicep, 'validation_required': ['Match observed management mode and attached policy scope', 'Check routes, inherited rules and all priority/name collisions', 'Verify DNS proxy and application rule suitability for FQDN', 'Compile Bicep locally and review complete deployment diff', 'Obtain separate flow test, deployment and rollback approval'], 'approval_required': True}
p.parent.mkdir(parents=True, exist_ok=True)
with bicep_path.open('x', encoding='utf-8') as handle:
    handle.write(bicep)
with p.open('x', encoding='utf-8') as handle:
    json.dump(draft, handle, indent=2)

```

## Analysis rules

1. Validate source CIDR against the observed subnet, destination against the owner approved target and ports/protocol against the application requirement. Reject wildcard destinations, broad source networks and unresolved placeholders.
2. Determine classic versus policy management and inspect inherited policy/rule collections, DNAT precedence, overlapping allows/denies and occupied priorities. A new allow cannot override an earlier matching deny.
3. Confirm the source route traverses this firewall and return traffic has a viable route. A rule proposal does not establish that traffic will reach the firewall.
4. Generate the local collection for the exact approved TCP or UDP flow using literal IP/CIDR or FQDN fields as appropriate. FQDN network rules require verified DNS proxy and no wildcard; prefer an application rule for HTTP/S or MSSQL when its protocol semantics are required.
5. Preserve all existing rule collections when integrating Bicep. The fragment is not a complete firewall resource and must never replace the current rule array unreviewed.
6. Require local Bicep compile, reviewed deployment diff, owner approval, bounded positive and negative flow tests, monitoring and rollback to the recorded prior rule configuration before any separately authorized deployment.

## Known limits

- The local draft supports TCP/UDP network rules and same subscription policy targets. Cross subscription policy scope, ICMP and application rules require a separately reviewed adaptation.
- Firewall configuration, routing, DNS proxy and precedence must be validated together; generating a rule is not proof of allowed connectivity.

## Expected validation cases

- Healthy: approved CIDRs and port 443 produce a classic draft; a policy attached firewall produces a new group Bicep draft without replacing existing groups.
- Finding: an earlier overlapping deny blocks readiness, and an approved exact FQDN without verified DNS proxy blocks generation.
- Denied or missing: wildcard input, unapproved destination, unreadable inherited rules or missing route evidence prevents a ready proposal.

## Sources

- [Network rule CLI syntax](https://learn.microsoft.com/en-us/cli/azure/network/firewall/network-rule?view=azure-cli-latest) (consulted 2026-10-21).
- [FQDN network rules, DNS proxy and application rule differences](https://learn.microsoft.com/en-us/azure/firewall/fqdn-filtering-network-rules) (consulted 2026-10-21).
- [Pinned policy NetworkRule schema](https://learn.microsoft.com/en-us/azure/templates/microsoft.network/2024-05-01/firewallpolicies/rulecollectiongroups) (consulted 2026-10-21).
- [Classic network rule collection schema](https://learn.microsoft.com/en-us/azure/templates/microsoft.network/2024-05-01/azurefirewalls) (consulted 2026-10-21).
- [Policy rule collection structure and Bicep references](https://learn.microsoft.com/en-us/azure/templates/microsoft.network/firewallpolicies/rulecollectiongroups) (consulted 2026-10-21).
- [Policy rule collection ownership](https://learn.microsoft.com/en-us/cli/azure/network/firewall/policy/rule-collection-group?view=azure-cli-latest) (consulted 2026-10-21).
- [Rule and route inventory](https://learn.microsoft.com/en-us/cli/azure/graph?view=azure-cli-latest) (consulted 2026-10-21).

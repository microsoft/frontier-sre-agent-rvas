# Evidence collection and analysis

## Collection

### 1. VNets, subnets and directed peerings

Save complete JSON to vnets_json_path under host controlled local evidence handling. Includes addressSpace, subnets and virtualNetworkPeerings as exposed by the service.

```azurecli
az network vnet list --subscription "<subscription_id>" --output json
```

### 2. Gateways, private endpoints and attached resources

Page via --skip-token from skipToken, combine data arrays into resources_json_path and retain the evidence manifest separately. ExpressRoute circuit association is through connection/peering references, not an invented subnet.

```azurecli
az graph query --subscriptions "<subscription_id>" --first 1000 -q "Resources | where type in~ ('microsoft.network/virtualnetworkgateways','microsoft.network/expressroutegateways','microsoft.network/expressroutecircuits','microsoft.network/connections','microsoft.network/privateendpoints','microsoft.network/networkinterfaces','microsoft.network/applicationgateways','microsoft.network/azurefirewalls','microsoft.compute/virtualmachines') | project id, name, type, subscriptionId, resourceGroup, properties" --output json
```

### 3. Generate the local diagram draft

Local generation only, with deterministic IDs and label sanitization to prevent retrieved text becoming Mermaid directives. Preserve unknown/external references without querying unapproved subscriptions. Validate syntax with the customer's existing local Mermaid renderer and inspect labels before sharing.

```python
import json, hashlib, re
from pathlib import Path
root = Path.cwd().resolve()
def safe_path(value):
    p = (root / value).resolve()
    assert root in p.parents and '<' not in str(p)
    return p
vnets = json.loads(safe_path('<vnets_json_path>').read_text(encoding='utf-8-sig'))
resources = json.loads(safe_path('<resources_json_path>').read_text(encoding='utf-8-sig'))
assert isinstance(vnets, list) and isinstance(resources, list)
out = safe_path('<artifact_path>')
assert not out.exists()
lines, nodes, edges = ['flowchart LR'], set(), set()
def node(rid, label):
    rid = rid.lower()
    key = 'n' + hashlib.sha256(rid.encode()).hexdigest()[:16]
    if key not in nodes:
        clean = re.sub(r'[^A-Za-z0-9 ._:/,()-]', '_', str(label))[:220]
        lines.append(f'  {key}["{clean}"]')
        nodes.add(key)
    return key
def edge(a, b, label):
    item = (a, b, label)
    if item not in edges:
        lines.append(f'  {a} -->|{re.sub(r"[^A-Za-z0-9 _]", "_", label)}| {b}')
        edges.add(item)
subnets = {}
for v in vnets:
    vp = v.get('properties', v)
    vk = node(v['id'], v['name'] + ' ' + ','.join(vp.get('addressSpace', {}).get('addressPrefixes', [])))
    for s in vp.get('subnets', []):
        sp = s.get('properties', s)
        sk = node(s['id'], s['name'] + ' ' + str(sp.get('addressPrefix') or sp.get('addressPrefixes') or 'prefix unknown'))
        subnets[s['id'].lower()] = sk
        edge(vk, sk, 'contains')
    for pe in vp.get('virtualNetworkPeerings', []):
        pp = pe.get('properties', pe)
        remote = pp.get('remoteVirtualNetwork', {}).get('id')
        if remote:
            edge(vk, node(remote, remote.rsplit('/', 1)[-1]), 'peering ' + str(pp.get('peeringState', 'unknown')))
for r in resources:
    rp = r.get('properties', {}) or {}
    rk = node(r['id'], r['name'] + ' ' + r['type'].rsplit('/', 1)[-1])
    refs = []
    if isinstance(rp.get('subnet'), dict):
        refs.append(rp['subnet'].get('id'))
    if rp.get('subnetId'):
        refs.append(rp['subnetId'])
    for cfg in (rp.get('ipConfigurations', []) or []) + (rp.get('gatewayIPConfigurations', []) or []):
        cp = cfg.get('properties', cfg)
        refs.append((cp.get('subnet') or {}).get('id'))
        pip = (cp.get('publicIPAddress') or {}).get('id')
        if pip:
            edge(rk, node(pip, pip.rsplit('/', 1)[-1]), 'public IP reference')
    for sid in refs:
        if sid and sid.lower() in subnets:
            edge(subnets[sid.lower()], rk, 'placement')
    for field in ('virtualMachine', 'virtualNetworkGateway1', 'virtualNetworkGateway2', 'peer'):
        target = (rp.get(field) or {}).get('id')
        if target:
            edge(rk, node(target, target.rsplit('/', 1)[-1]), field)
    for conn in (rp.get('privateLinkServiceConnections', []) or []) + (rp.get('manualPrivateLinkServiceConnections', []) or []):
        cp = conn.get('properties', conn)
        target = cp.get('privateLinkServiceId')
        if target:
            edge(rk, node(target, target.rsplit('/', 1)[-1]), 'private link ' + str((cp.get('privateLinkServiceConnectionState') or {}).get('status', 'unknown')))
out.parent.mkdir(parents=True, exist_ok=True)
with out.open('x', encoding='utf-8') as handle:
    handle.write('\n'.join(lines) + '\n')

```

## Analysis rules

1. Reconcile the diagram node set to approved VNet and resource inventories and record page completeness. Include every subnet and its observed prefix; unknown prefixes are labeled rather than guessed.
2. Render each peering as a directed relationship with its own peeringState. Connected on one side does not establish healthy bidirectional connectivity.
3. Place gateways, private endpoints and NIC based resources only from explicit subnet references. Join VM to NIC references, gateway connection peer references and private link target IDs; do not infer placement from names.
4. Show VPN/ExpressRoute gateways and related circuits even if they have no direct subnet field. Label configuration relationships rather than imply live traffic reachability.
5. Validate Mermaid parse and locally render for visual inspection, checking counts, missing nodes, edge direction and clipped labels. Include UTC evidence timestamp and gaps in the report accompanying the diagram.
6. Treat addresses, names and topology as sensitive customer metadata. Generate a local draft only and obtain destination approval plus any requested redaction before distribution.

## Known limits

- Configuration topology does not prove effective routes, firewall reachability or application connectivity.
- Cross subscription references and Resource Graph child omissions may leave incomplete external nodes; no live status is invented.

## Expected validation cases

- Healthy: two VNets and reciprocal peerings produce both directed edges and all subnet prefixes.
- Finding: an Initiated peering and a disconnected private endpoint remain visibly labeled in the draft.
- Denied or missing: a missing ARG page marks topology Partial and a missing local input blocks generation instead of inventing nodes.

## Sources

- [Network inventory CLI](https://learn.microsoft.com/en-us/cli/azure/network?view=azure-cli-latest) (consulted 2026-10-21).
- [Peering connectivity and relationships](https://learn.microsoft.com/en-us/azure/virtual-network/virtual-network-peering-overview) (consulted 2026-10-21).
- [Private endpoint subnet and target relationships](https://learn.microsoft.com/en-us/azure/private-link/private-endpoint-overview) (consulted 2026-10-21).
- [Network resource discovery paging](https://learn.microsoft.com/en-us/cli/azure/graph?view=azure-cli-latest) (consulted 2026-10-21).

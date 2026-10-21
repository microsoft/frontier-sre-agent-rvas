# Evidence collection and analysis

## Collection

### 1. Public and private DNS zone inventories

Build separate zone family denominators. Zone names can overlap across split horizon contexts; retain zone ARM ID, not name alone.

```azurecli
az network dns zone list --subscription "<subscription_id>" --output json
az network private-dns zone list --subscription "<subscription_id>" --output json
```

### 2. Public and private zone records

Execute only the appropriate family command for each inventoried zone, not both blindly. Retain A/AAAA/CNAME records, targetResource alias IDs, TTL and metadata. Record deleted or inaccessible zones separately.

```azurecli
az network dns record-set list --subscription "<subscription_id>" --resource-group "<resource_group>" --zone-name "<zone_name>" --output json
az network private-dns record-set list --subscription "<subscription_id>" --resource-group "<resource_group>" --zone-name "<zone_name>" --output json
```

### 3. Known in scope IP ownership

Page using --skip-token from skipToken. Build IPv4 and IPv6 ownership maps from observed public/private address fields; the map is not a universal global IP ownership database.

```azurecli
az graph query --subscriptions "<subscription_id>" --first 1000 -q "Resources | where type in~ ('microsoft.network/publicipaddresses','microsoft.network/networkinterfaces','microsoft.network/loadbalancers','microsoft.network/applicationgateways','microsoft.network/privateendpoints') | project id, name, type, resourceGroup, properties" --output json
```

### 4. Authoritative alias target existence

Only follow a target within approved scope; select an explicitly approved target subscription for cross subscription reads. Preserve 404 versus 403 and transient failure; a graph miss alone is not deleted target evidence.

```azurecli
az resource show --subscription "<subscription_id>" --ids "<target_resource_id>" --output json
```

### 5. Approved resolver query and local evidence

Only run from an approved resolver vantage with host enforced domain/resolver allowlists. Uses Windows DNS client and writes local evidence. An error is not automatically NXDOMAIN: distinguish authoritative no such name from timeout, SERVFAIL or refused using the recorded error and resolver evidence.

```powershell
$name = '<fqdn>'
$server = '<dns_server>'
$parsedAddress = $null
if ($name.Length -gt 253 -or $name -notmatch '^(?=.{1,253}\.?$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z0-9-]{2,63}\.?$' -or -not [System.Net.IPAddress]::TryParse($server, [ref]$parsedAddress)) { throw 'Invalid DNS query input' }
$root = (Get-Location).Path
$path = [System.IO.Path]::GetFullPath((Join-Path $root '<artifact_path>'))
if (-not $path.StartsWith($root.TrimEnd('\') + '\', [System.StringComparison]::OrdinalIgnoreCase) -or $path.Contains('<') -or (Test-Path -LiteralPath $path)) { throw 'Invalid artifact path' }
$result = [ordered]@{ fqdn = $name; resolver = $server; queried_at_utc = [DateTime]::UtcNow.ToString('o'); status = 'Unknown'; records = @(); error_id = $null }
try {
    $records = Resolve-DnsName -Name $name -Server $server -DnsOnly -ErrorAction Stop
    $result.status = 'Response'
    $result.records = @($records | Select-Object Name, Type, IPAddress, NameHost, TTL)
} catch {
    $result.status = 'QueryError'
    $result.error_id = $_.FullyQualifiedErrorId
}
[System.IO.Directory]::CreateDirectory([System.IO.Path]::GetDirectoryName($path)) | Out-Null
$stream = [System.IO.File]::Open($path, [System.IO.FileMode]::CreateNew)
$writer = [System.IO.StreamWriter]::new($stream)
try { $writer.Write(($result | ConvertTo-Json -Depth 6)) } finally { $writer.Dispose() }
```

## Analysis rules

1. Normalize DNS names and IP literals, preserving zone ID, family, record type and TTL. Parse A/AAAA with an IP library and compare exact IPs to the complete approved ownership map.
2. An IP not in current approved Azure inventory is unmatched, not necessarily dangling: check external_target_allowlist, on premises ownership, other approved subscriptions and service managed endpoints before raising a deletion candidate.
3. Resolve CNAME chains through the approved resolver, detect loops and bound chain depth. A response from the wrong DNS vantage does not establish private record failure; record timeout/refused/SERVFAIL separately from NXDOMAIN.
4. For alias targetResource IDs use an authorized resource read. Repeatable 404 can establish a missing target candidate, while 403 and unapproved cross subscription targets remain unknown.
5. Azure alias records can become empty record sets when a supported target is deleted; report empty alias sets separately instead of assuming a stale nonempty target pointer always remains.
6. Recommend owner verification and TTL aware change planning. Never delete records, mutate aliases or treat one transient resolution failure as proof of a takeover vulnerability.

## Known limits

- Approved subscription IP inventory cannot prove global ownership or absence of on premises/external targets.
- Private DNS resolution depends on the network vantage, forwarding and links, and transient resolver errors are not deleted resource evidence.

## Expected validation cases

- Healthy: A/AAAA address has verified ownership and CNAME resolves from the correct approved vantage.
- Finding: a repeatable authorized alias target 404 or repeated authoritative CNAME NXDOMAIN becomes an owner review finding.
- Denied or missing: target read 403 or DNS timeout remains unknown and never becomes a proven deleted target.

## Sources

- [Public DNS record inventory](https://learn.microsoft.com/en-us/cli/azure/network/dns/record-set?view=azure-cli-latest) (consulted 2026-10-21).
- [Private DNS record inventory](https://learn.microsoft.com/en-us/cli/azure/network/private-dns/record-set?view=azure-cli-latest) (consulted 2026-10-21).
- [Alias lifecycle and empty record sets](https://learn.microsoft.com/en-us/azure/dns/dns-alias) (consulted 2026-10-21).
- [Approved resolver and DNS only query semantics](https://learn.microsoft.com/en-us/powershell/module/dnsclient/resolve-dnsname) (consulted 2026-10-21).
- [Authoritative target existence read](https://learn.microsoft.com/en-us/cli/azure/resource?view=azure-cli-latest) (consulted 2026-10-21).
- [Scoped IP ownership discovery and paging](https://learn.microsoft.com/en-us/cli/azure/graph?view=azure-cli-latest) (consulted 2026-10-21).

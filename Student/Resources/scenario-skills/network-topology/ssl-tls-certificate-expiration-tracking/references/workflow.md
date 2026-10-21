# Evidence collection and analysis

## Collection

### 1. All five certificate hosting families

Page using --skip-token from skipToken and build denominators for each family. Include App Service certificate orders under Microsoft.CertificateRegistration and installed Microsoft.Web certificates as distinct resources; classic Front Door and managed certificates may expose less expiry metadata.

```azurecli
az graph query --subscriptions "<subscription_id>" --first 1000 -q "Resources | where type in~ ('microsoft.keyvault/vaults','microsoft.web/certificates','microsoft.certificateregistration/certificateorders','microsoft.web/sites','microsoft.network/applicationgateways','microsoft.network/frontdoors','microsoft.cdn/profiles','microsoft.apimanagement/service') | project id, name, type, resourceGroup, properties" --output json
```

### 2. Key Vault certificate public metadata and used versions

Enumerate certificate versions and match actual service bindings. Certificate show returns public cer data; never call secret show/download to fetch a PFX. A secret only certificate without a certificate object can remain unknown.

```azurecli
az keyvault certificate list --subscription "<subscription_id>" --vault-name "<vault_name>" --output json
az keyvault certificate list-versions --subscription "<subscription_id>" --vault-name "<vault_name>" --name "<certificate_name>" --output json
az keyvault certificate show --subscription "<subscription_id>" --vault-name "<vault_name>" --name "<certificate_name>" --version "<certificate_version>" --output json
```

### 3. App Service and Application Gateway certificates

Retain returned expiry and subject metadata and keyVaultSecretId/publicCertData references. Join Application Gateway httpListeners and App Service hostname SSL thumbprints to the actually used certificate version. Do not assume a configured vault's newest certificate is deployed.

```azurecli
az webapp config ssl list --subscription "<subscription_id>" --resource-group "<resource_group>" --output json
az network application-gateway ssl-cert list --subscription "<subscription_id>" --resource-group "<resource_group>" --gateway-name "<gateway_name>" --output json
```

### 4. Front Door custom domains and certificate references

These are ARM certificate reference metadata, not Key Vault secret value retrieval. Inspect certificate type, secret version/reference and deployment state. Managed certificate expiry not returned by the API stays null; renewal ownership is reported separately.

```azurecli
az afd custom-domain list --subscription "<subscription_id>" --resource-group "<resource_group>" --profile-name "<frontdoor_profile_name>" --output json
az afd secret list --subscription "<subscription_id>" --resource-group "<resource_group>" --profile-name "<frontdoor_profile_name>" --output json
```

### 5. API Management certificate and hostname metadata

Follow nextLink for the certificate collection. Collection properties include subject, thumbprint and expirationDate, but not a universal issuer field. Service hostnameConfigurations cover gateway TLS bindings separately from client/backend certificates.

```azurecli
az rest --method get --subscription "<subscription_id>" --url "https://management.azure.com/subscriptions/<subscription_id>/resourceGroups/<resource_group>/providers/Microsoft.ApiManagement/service/<apim_name>/certificates?api-version=2024-05-01" --output json
az apim show --subscription "<subscription_id>" --resource-group "<resource_group>" --name "<apim_name>" --output json
```

### 6. Parse public X509 metadata locally

Local parsing of public DER only. Other services' observed publicCertData can use the same X509 constructor after a documented metadata adapter; if the service does not expose the public certificate, subject or issuer stays null rather than being guessed.

```powershell
$root = (Get-Location).Path
$inputPath = [System.IO.Path]::GetFullPath((Join-Path $root '<certificate_metadata_path>'))
$outputPath = [System.IO.Path]::GetFullPath((Join-Path $root '<artifact_path>'))
$prefix = $root.TrimEnd('\') + '\'
if (-not $inputPath.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase) -or -not $outputPath.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase) -or $inputPath.Contains('<') -or $outputPath.Contains('<') -or (Test-Path -LiteralPath $outputPath)) { throw 'Invalid or existing artifact path' }
$metadata = Get-Content -LiteralPath $inputPath -Raw | ConvertFrom-Json
if (-not $metadata.cer) { throw 'No public DER certificate in supplied metadata' }
$certificate = [System.Security.Cryptography.X509Certificates.X509Certificate2]::new([Convert]::FromBase64String($metadata.cer))
try {
    $result = [ordered]@{ subject = $certificate.Subject; issuer = $certificate.Issuer; expires_at = $certificate.NotAfter.ToUniversalTime().ToString('o'); thumbprint = $certificate.Thumbprint }
    [System.IO.Directory]::CreateDirectory([System.IO.Path]::GetDirectoryName($outputPath)) | Out-Null
    $stream = [System.IO.File]::Open($outputPath, [System.IO.FileMode]::CreateNew)
    $writer = [System.IO.StreamWriter]::new($stream)
    try { $writer.Write(($result | ConvertTo-Json -Depth 4)) } finally { $writer.Dispose() }
} finally { $certificate.Dispose() }
```

## Analysis rules

1. Inventory and report coverage for all five families, separating stored certificates, installed certificates and active listener/domain bindings.
2. Resolve each binding to its exact certificate thumbprint or version. A versionless vault reference may auto rotate, but verify actual deployment metadata and do not infer rotation succeeded from a newer stored version.
3. Use public certificate parsing or authoritative returned expirationDate/attributes metadata. Do not substitute certificate policy issuer provider name for the actual X509 issuer.
4. Compute fractional days remaining from expiry UTC minus assessment_utc. Classify expired below zero, expiring within 30 days inclusive, and later otherwise. A null expiry is Not assessed, not healthy.
5. For Front Door managed/classic certificates with no exposed expiry record platform renewal ownership and deployment state but retain expiry null. Do not equate provisioning success with a fresh served certificate.
6. Deduplicate certificate versions by thumbprint for inventory counts while retaining all affected bindings. Recommend owner renewal and post renewal binding verification, with no secret access or live endpoint probes in this read workflow.

## Known limits

- Some managed Front Door or secret only certificates do not expose expiry/public DER through these metadata APIs; unknown fields stay null.
- Stored certificate expiry does not prove which certificate is currently served on every endpoint, and automatic renewal must not be assumed successful.

## Expected validation cases

- Healthy: bound public certificate expires in 100 days and is not in the warning set.
- Finding: an actually referenced older version expires in 10 days even though a newer unused version exists.
- Denied or missing: denied vault metadata or absent managed certificate expiry yields null expiry and Not assessed, not a renewal success claim.

## Sources

- [Public metadata, expiration and key/secret separation](https://learn.microsoft.com/en-us/azure/key-vault/certificates/about-certificates) (consulted 2026-10-21).
- [Certificate list, versions and metadata reads](https://learn.microsoft.com/en-us/cli/azure/keyvault/certificate?view=azure-cli-latest) (consulted 2026-10-21).
- [Installed App Service certificate inventory](https://learn.microsoft.com/en-us/cli/azure/webapp/config/ssl?view=azure-cli-latest) (consulted 2026-10-21).
- [App Service certificate order resource provider](https://learn.microsoft.com/en-us/azure/templates/microsoft.certificateregistration/certificateorders) (consulted 2026-10-21).
- [Application Gateway certificate metadata](https://learn.microsoft.com/en-us/cli/azure/network/application-gateway/ssl-cert?view=azure-cli-latest) (consulted 2026-10-21).
- [Front Door domain TLS bindings](https://learn.microsoft.com/en-us/cli/azure/afd/custom-domain?view=azure-cli-latest) (consulted 2026-10-21).
- [Front Door certificate reference metadata](https://learn.microsoft.com/en-us/cli/azure/afd/secret?view=azure-cli-latest) (consulted 2026-10-21).
- [API Management paged certificate metadata and expiry](https://learn.microsoft.com/en-us/rest/api/apimanagement/certificate/list-by-service?view=rest-apimanagement-2024-05-01) (consulted 2026-10-21).

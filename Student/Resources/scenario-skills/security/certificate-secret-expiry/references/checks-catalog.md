# Checks catalog

Expiry sources and how the scan reads them. Some are management plane and covered by Reader; some are data plane or directory reads that need their own permission and are best effort. Where a read is denied, record the source as not assessed and continue.

For each finding the tool records: item name, kind, source, subscription, expiry date, days remaining, a severity from the days remaining, and the recommended action.

ARM, vault and Graph HTTP reads use `shared\tools\azure_http.py` and the bundled governance policy for approved HTTPS hosts, explicit timeouts, disabled redirects and bounded transient retries. Authorization failures are not retried. Deployed bundles must include the shared tools and policy.

## 1. App Service certificates (Resource Graph, Reader)

```
az graph query -q "resources | where type =~ 'microsoft.web/certificates' | project name, id, subscriptionId, resourceGroup, expirationDate=tostring(properties.expirationDate), thumbprint=tostring(properties.thumbprint)" --first 1000
```

The expirationDate is management plane metadata, so this works with Reader. Fix for a finding: renew or replace the certificate and update the binding.

## 2. Key Vault certificates and secrets (data plane)

List the vaults, then read item expiry from each vault's data plane.

```
az graph query -q "resources | where type =~ 'microsoft.keyvault/vaults' | project name, id, subscriptionId, resourceGroup, vaultUri=tostring(properties.vaultUri)" --first 1000
```

The tool lists `{vaultUri}/certificates` and `{vaultUri}/secrets` with a token for `https://vault.azure.net` and reads `attributes.exp` and `attributes.enabled`. It never calls an item value endpoint. Key Vault Reader on an RBAC vault reads metadata without secret contents or key material; no extra secret value permission is needed. Access policy vaults require certificate and secret list permissions. Network restrictions can still prevent a read. A denied collection is Not assessed; certificate and secret collections are attempted independently.

The vault collector is configured for public Azure `*.vault.azure.net` metadata endpoints. Other clouds are Not assessed until an approved endpoint and audience configuration is supplied. Continuations must stay on the same vault collection path, never an item value path.

Managed secrets backing certificates are retained as metadata records and may correspond to a certificate finding. Counts describe records, not unique outage risks. Missing expiry is explicitly unknown rather than omitted. Disabled records are Low severity and distinct from active expiry risk.

Verify one vault by hand:

```
az keyvault certificate list --vault-name <vault> --query "[].{name:name, expires:attributes.expires}"
az keyvault secret list --vault-name <vault> --query "[].{name:name, expires:attributes.expires, enabled:attributes.enabled}"
```

## 3. Approved application registration credentials (Microsoft Graph)

```
GET https://graph.microsoft.com/v1.0/applications?$select=displayName,appId,passwordCredentials,keyCredentials
```

Graph is off by default. Pass `--application-ids <approved-object-ids>` to read specific application objects. Use `--allow-tenant-directory` only after explicit approval to enumerate tenant application registrations, never merely because the identity has technical permission. `Application.Read.All` application permission requires administrator consent for this application read. ARM scope approval does not authorize directory enumeration.

The collector retains credential ids and endDateTime metadata, not credential values or key material. `/applications` does not enumerate credentials on all service principal objects, including enterprise applications. Those objects and tenant sign ins remain Not assessed. Page cap exhaustion is explicitly incomplete.

## Severity from days remaining

- Critical: already expired (days remaining below zero).
- High: 14 days or fewer.
- Medium: 15 to 30 days.
- Low: 31 days to the horizon (60 by default).

Beyond the horizon: not reported. Pass a larger horizon argument for more lead time before a big renewal season.

Missing expiry is always reported as unknown, including when no horizon can be calculated. Disabled items within the horizon remain visible but are excluded from active expired and expiring summary counts.

## Note on App Gateway and other embedded certificates

Certificates embedded directly in an Application Gateway or a Front Door listener are not enumerated here; prefer Key Vault referenced certificates, which this skill can see. Where embedded certificates are in use, check them by hand and consider moving them to Key Vault.

## Sources

Verified against Microsoft Learn during this correction:

- [Key Vault Reader metadata permissions](https://learn.microsoft.com/azure/key-vault/general/rbac-guide)
- [Secret listing returns identifiers and attributes, not values](https://learn.microsoft.com/rest/api/keyvault/secrets/get-secrets/get-secrets)
- [List applications and application permissions](https://learn.microsoft.com/graph/api/application-list)
- [Separate service principal collection](https://learn.microsoft.com/graph/api/serviceprincipal-list)

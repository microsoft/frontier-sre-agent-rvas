<#
.SYNOPSIS
    OPTION B (cross-tenant) only - step 1 of 2. Run in the tenant of the Azure SRE Agent (tenant A).
    Creates a multi-tenant app that represents the SRE Agent in the Fabric tenant (tenant B), and the credential
    the tool uses to sign in as that app:
      - with -KeyVaultName (recommended): a certificate kept in a Key Vault of tenant A, readable only by the
        SRE Agent managed identity. The private key never leaves Key Vault.
      - always: a Federated Identity Credential (FIC) that trusts the SRE Agent user-assigned managed identity.

.DESCRIPTION
    Why the certificate: the Azure SRE Agent sandbox hands Python tools sidecar-issued managed identity tokens that
    the platform proxy swaps for the real token when they leave as an Authorization header. A federated sign-in sends
    the managed identity token inside the request body, where it is not swapped, so Entra rejects it with
    AADSTS5002723. Reading a certificate from Key Vault uses a normal Authorization header and works.

    Idempotent: reuses the app, FIC, Key Vault, certificate and role assignment if they already exist. One app serves
    any number of customer tenants. Do NOT add Power BI / Fabric API permissions with admin consent to this app: the
    Fabric admin APIs reject service principals that hold them. The default (no permissions) is what you want.

    The Key Vault must allow public network access, because the SRE Agent sandbox reaches it over the internet.
    If an Azure Policy forces public access off, create the vault in a resource group exempted by your organization.

.NOTES
    Permission to register applications in tenant A (Application Developer or higher). With -KeyVaultName also
    Owner or User Access Administrator on the resource group (to create the vault and assign roles). Azure CLI 2.60+.

.EXAMPLE
    ./setup-cross-tenant-app.ps1 -SreTenantId <SRE_TENANT_ID> -UamiPrincipalId <UAMI_PRINCIPAL_ID> `
        -KeyVaultName kv-sre-xtenant-01 -ResourceGroup rg-sre-agent -SubscriptionId <SRE_SUBSCRIPTION_ID>
    # then, in the Fabric tenant:
    ./grant-fabric-finops-access.ps1 -FabricTenantId <TARGET_FABRIC_TENANT_ID> -SubscriptionId <SUB_ID> -AppClientId <printed appId>
#>
param(
    [Parameter(Mandatory = $true)] [string] $SreTenantId,
    [Parameter(Mandatory = $true)] [string] $UamiPrincipalId,
    [string] $AppName = "sre-agent-fabric-cross-tenant-bridge",
    [string] $FicName = "sre-agent-uami-fic",
    # Recommended: Key Vault (created if missing) that holds the app certificate.
    [string] $KeyVaultName = "",
    [string] $ResourceGroup = "",
    [string] $SubscriptionId = "",
    [string] $Location = "",
    [string] $CertificateName = "sre-agent-fabric-cross-tenant",
    [ValidateRange(1, 24)] [int] $CertificateValidityMonths = 12,
    [switch] $SkipLogin
)
$ErrorActionPreference = "Stop"

# Every Invoke-AzCli call must succeed: a failed lookup (expired sign-in, missing role) must never look like "not found".
function Invoke-AzCli {
    $out = & az @args
    if ($LASTEXITCODE -ne 0) { throw "az $($args -join ' ') failed (exit $LASTEXITCODE). Fix the error above and re-run; the script is idempotent." }
    return $out
}
# Existence checks only: returns $null when the resource does not exist.
function Find-AzCli {
    $out = & az @args 2>$null
    if ($LASTEXITCODE -ne 0) { return $null }
    return $out
}

if (-not $SkipLogin) { Invoke-AzCli login --tenant $SreTenantId --allow-no-subscriptions | Out-Null }
if ((Invoke-AzCli account show --query tenantId -o tsv) -ne $SreTenantId) { throw "Signed in to the wrong tenant. Run: az login --tenant $SreTenantId" }
if ($KeyVaultName -and (-not $ResourceGroup -or -not $SubscriptionId)) { throw "-KeyVaultName also needs -ResourceGroup and -SubscriptionId." }

# 1. Multi-tenant app
$appId = Invoke-AzCli ad app list --display-name $AppName --query "[0].appId" -o tsv
if (-not $appId) {
    $appId = Invoke-AzCli ad app create --display-name $AppName --sign-in-audience AzureADMultipleOrgs --query appId -o tsv
    Write-Host "[OK] App created: $appId" -ForegroundColor Green
} else {
    Invoke-AzCli ad app update --id $appId --sign-in-audience AzureADMultipleOrgs | Out-Null
    Write-Host "[OK] App reused: $appId" -ForegroundColor Green
}
if (-not (Find-AzCli ad sp show --id $appId --query id -o tsv)) { Invoke-AzCli ad sp create --id $appId | Out-Null }
$appObjId = Invoke-AzCli ad app show --id $appId --query id -o tsv

# 2. Federated Identity Credential that trusts the SRE Agent managed identity
$issuer   = "https://login.microsoftonline.com/$SreTenantId/v2.0"
$existing = Invoke-AzCli ad app federated-credential list --id $appObjId --query "[?subject=='$UamiPrincipalId' && issuer=='$issuer'].name" -o tsv
if ($existing) {
    Write-Host "[OK] FIC already present: $existing" -ForegroundColor Green
} else {
    $tmp = Join-Path ([IO.Path]::GetTempPath()) ("fic-" + [guid]::NewGuid().ToString("N") + ".json")
    $fic = @{ name = $FicName; issuer = $issuer; subject = $UamiPrincipalId; audiences = @("api://AzureADTokenExchange"); description = "Trust the Azure SRE Agent managed identity" }
    [IO.File]::WriteAllText($tmp, ($fic | ConvertTo-Json -Depth 4), (New-Object Text.UTF8Encoding($false)))
    Invoke-AzCli ad app federated-credential create --id $appObjId --parameters "@$tmp" | Out-Null
    Remove-Item $tmp -ErrorAction SilentlyContinue
    Write-Host "[OK] FIC created (issuer $issuer, subject $UamiPrincipalId)" -ForegroundColor Green
}

# 3. Optional (recommended): certificate in Key Vault, readable only by the SRE Agent managed identity
$vaultUrl = ""
if ($KeyVaultName) {
    $vaultId = Find-AzCli keyvault show -n $KeyVaultName --subscription $SubscriptionId --query id -o tsv
    if (-not $vaultId) {
        if (-not $Location) { $Location = Invoke-AzCli group show -n $ResourceGroup --subscription $SubscriptionId --query location -o tsv }
        $vaultId = Invoke-AzCli keyvault create -n $KeyVaultName -g $ResourceGroup --subscription $SubscriptionId -l $Location `
            --enable-rbac-authorization true --public-network-access Enabled --query id -o tsv
        Write-Host "[OK] Key Vault created: $KeyVaultName" -ForegroundColor Green
    } else {
        Write-Host "[OK] Key Vault reused: $KeyVaultName" -ForegroundColor Green
    }
    $pna = Invoke-AzCli keyvault show -n $KeyVaultName --subscription $SubscriptionId --query properties.publicNetworkAccess -o tsv
    if ($pna -ne "Enabled") {
        Write-Warning "Public network access is '$pna' (often forced by Azure Policy). The SRE Agent cannot read the certificate until it is Enabled."
    }
    $vaultUrl = (Invoke-AzCli keyvault show -n $KeyVaultName --subscription $SubscriptionId --query properties.vaultUri -o tsv).TrimEnd("/")

    $me = Invoke-AzCli ad signed-in-user show --query id -o tsv
    foreach ($ra in @(@{ p = $me; t = "User"; r = "Key Vault Certificates Officer" }, @{ p = $UamiPrincipalId; t = "ServicePrincipal"; r = "Key Vault Secrets User" })) {
        $has = Invoke-AzCli role assignment list --scope $vaultId --query "[?principalId=='$($ra.p)' && roleDefinitionName=='$($ra.r)'].id | [0]" -o tsv
        if (-not $has) { Invoke-AzCli role assignment create --assignee-object-id $ra.p --assignee-principal-type $ra.t --role $ra.r --scope $vaultId | Out-Null }
    }
    Write-Host "[OK] Roles: you = Certificates Officer, SRE Agent identity = Secrets User (read only)" -ForegroundColor Green

    if (-not (Find-AzCli keyvault certificate show --vault-name $KeyVaultName -n $CertificateName --query id -o tsv)) {
        $policy = @{
            issuerParameters = @{ name = "Self" }
            keyProperties = @{ exportable = $true; keyType = "RSA"; keySize = 2048; reuseKey = $false }
            secretProperties = @{ contentType = "application/x-pem-file" }
            x509CertificateProperties = @{ subject = "CN=$CertificateName"; validityInMonths = $CertificateValidityMonths; keyUsage = @("digitalSignature") }
        }
        $pfile = Join-Path ([IO.Path]::GetTempPath()) ("certpolicy-" + [guid]::NewGuid().ToString("N") + ".json")
        [IO.File]::WriteAllText($pfile, ($policy | ConvertTo-Json -Depth 5), (New-Object Text.UTF8Encoding($false)))
        $created = $false
        for ($i = 0; $i -lt 8 -and -not $created; $i++) {   # role assignments can take a minute to apply
            az keyvault certificate create --vault-name $KeyVaultName -n $CertificateName -p "@$pfile" -o none 2>$null
            if ($LASTEXITCODE -eq 0) { $created = $true } else { Start-Sleep -Seconds 20 }
        }
        Remove-Item $pfile -ErrorAction SilentlyContinue
        if (-not $created) { throw "Could not create the certificate in $KeyVaultName (check your Key Vault roles)." }
        Write-Host "[OK] Certificate created in Key Vault: $CertificateName ($CertificateValidityMonths months)" -ForegroundColor Green
    } else {
        Write-Host "[OK] Certificate reused: $CertificateName" -ForegroundColor Green
    }

    # Public part only: attach it to the app (appended, existing credentials are kept)
    $thumb = Invoke-AzCli keyvault certificate show --vault-name $KeyVaultName -n $CertificateName --query x509ThumbprintHex -o tsv
    $onApp = Invoke-AzCli ad app credential list --id $appId --cert --query "[?customKeyIdentifier=='$thumb'].keyId" -o tsv
    if (-not $onApp) {
        $cer = Join-Path ([IO.Path]::GetTempPath()) ("cert-" + [guid]::NewGuid().ToString("N") + ".pem")
        Invoke-AzCli keyvault certificate download --vault-name $KeyVaultName -n $CertificateName -f $cer -e PEM | Out-Null
        Invoke-AzCli ad app credential reset --id $appId --cert "@$cer" --append --display-name "$CertificateName ($KeyVaultName)" -o none
        Remove-Item $cer -ErrorAction SilentlyContinue
        Write-Host "[OK] Certificate public key added to the app (thumbprint $thumb)" -ForegroundColor Green
    } else {
        Write-Host "[OK] Certificate already on the app (thumbprint $thumb)" -ForegroundColor Green
    }
}

Write-Host ""
Write-Host "Values for the tool code (CONFIGURE block):" -ForegroundColor Cyan
Write-Host "    FEDERATED_APP_CLIENT_ID = `"$appId`"" -ForegroundColor Cyan
if ($vaultUrl) {
    Write-Host "    CROSS_TENANT_CERT_KEYVAULT_URL = `"$vaultUrl`"" -ForegroundColor Cyan
    Write-Host "    CROSS_TENANT_CERT_NAME = `"$CertificateName`"" -ForegroundColor Cyan
} else {
    Write-Warning "No -KeyVaultName: the tool will try the federated credential, which the current SRE Agent sandbox rejects (AADSTS5002723). Re-run with -KeyVaultName."
}
Write-Host "Give FEDERATED_APP_CLIENT_ID to the Fabric administrator of the customer tenant. Next step (run in tenant B):"
Write-Host "  ./grant-fabric-finops-access.ps1 -FabricTenantId <TARGET_FABRIC_TENANT_ID> -SubscriptionId <SUB_ID> -AppClientId $appId"

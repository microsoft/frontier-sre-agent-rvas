# grant-graph-permission.ps1
# Microsoft Entra credential expiration audit · Azure SRE Agent
# Grants the Microsoft Graph application permission Application.Read.All
# to the user-assigned managed identity of your Azure SRE Agent.
#
# - Run it in PowerShell with an account that holds the Privileged Role Administrator role.
# - It is idempotent: if the permission is already assigned, no duplicate assignment is created.
# - It only grants read access. Do not grant Microsoft Graph write permissions to the tool.
#
# Version 1.1 · October 2026

[CmdletBinding()]
param()

# ---------------------------------------------------------------------------
# REQUIRED CONFIGURATION
# Replace the value with the Client ID of the user-assigned managed identity
# of YOUR Azure SRE Agent (Step 0 of the guide). A Client ID is not a secret.
# ---------------------------------------------------------------------------
$managedIdentityClientId = "<YOUR_AGENT_CLIENT_ID>"

if ($managedIdentityClientId -like "<*") {
    throw "Replace <YOUR_AGENT_CLIENT_ID> with the Client ID of your agent's managed identity before you run this script."
}

Write-Host "[1/7] Installing Microsoft.Graph for the current user; first-time installation can take several minutes..."
Write-Verbose "The module is installed with CurrentUser scope; no machine-wide installation is requested."
Install-Module Microsoft.Graph -Scope CurrentUser -Force -ErrorAction Stop
Write-Host "[1/7] Microsoft.Graph installation completed."

Write-Host "[2/7] Importing Microsoft.Graph.Applications; this can take a moment..."
Import-Module Microsoft.Graph.Applications -ErrorAction Stop
Write-Host "[2/7] Microsoft.Graph.Applications imported."

$graphConnected = $false
$operationFailed = $false

try {
    Write-Host "[3/7] Signing in to Microsoft Graph; complete the interactive sign-in prompt..."
    Write-Verbose "The operator requests delegated Application.Read.All and AppRoleAssignment.ReadWrite.All; the identity receives only the read-only application role."
    Connect-MgGraph -Scopes "Application.Read.All", "AppRoleAssignment.ReadWrite.All" -ErrorAction Stop | Out-Null
    $graphConnected = $true
    Write-Host "[3/7] Microsoft Graph sign-in completed."

    # Microsoft Graph App ID (identical in every tenant).
    $graphAppId = "00000003-0000-0000-c000-000000000000"

    Write-Host "[4/7] Looking up the managed identity and Microsoft Graph application role..."
    Write-Verbose "Resolve the identity by Client ID, not Object ID, and select Application.Read.All with AllowedMemberTypes containing Application."
    $managedIdentitySp = Get-MgServicePrincipal -Filter "appId eq '$managedIdentityClientId'" -ErrorAction Stop
    $graphSp = Get-MgServicePrincipal -Filter "appId eq '$graphAppId'" -ErrorAction Stop

    if (-not $managedIdentitySp) {
        throw "Managed identity service principal not found. Verify the Client ID."
    }

    $appRole = $graphSp.AppRoles | Where-Object {
        $_.Value -eq "Application.Read.All" -and
        $_.AllowedMemberTypes -contains "Application"
    }

    if (-not $appRole) {
        throw "Microsoft Graph Application.Read.All app role was not found."
    }
    Write-Host "[4/7] Managed identity and Application.Read.All application role found."

    Write-Host "[5/7] Checking for an existing Application.Read.All assignment..."
    Write-Verbose "Read all assignment pages and compare both the Microsoft Graph resource ID and the selected application-role ID."
    $existingAssignment = Get-MgServicePrincipalAppRoleAssignment `
        -ServicePrincipalId $managedIdentitySp.Id -All -ErrorAction Stop | Where-Object {
            $_.ResourceId -eq $graphSp.Id -and $_.AppRoleId -eq $appRole.Id
        }
    Write-Host "[5/7] Existing-assignment check completed."

    if (-not $existingAssignment) {
        $params = @{
            principalId = $managedIdentitySp.Id
            resourceId  = $graphSp.Id
            appRoleId   = $appRole.Id
        }

        Write-Host "[6/7] Granting Application.Read.All to the managed identity..."
        New-MgServicePrincipalAppRoleAssignment `
            -ServicePrincipalId $managedIdentitySp.Id `
            -BodyParameter $params -ErrorAction Stop | Out-Null

        Write-Host "Application.Read.All granted to the managed identity." -ForegroundColor Green
    }
    else {
        Write-Host "[6/7] No permission change required."
        Write-Host "Application.Read.All is already assigned." -ForegroundColor Yellow
    }
}
catch {
    $operationFailed = $true
    throw
}
finally {
    if ($graphConnected) {
        Write-Host "[7/7] Disconnecting the Microsoft Graph operator session..."
        try {
            Disconnect-MgGraph -ErrorAction Stop | Out-Null
            Write-Host "[7/7] Microsoft Graph operator session disconnected."
        }
        catch {
            if ($operationFailed) {
                # Report cleanup failure without replacing the original operation error.
                Write-Error -ErrorRecord $_ -ErrorAction Continue
            }
            else {
                throw
            }
        }
    }
}

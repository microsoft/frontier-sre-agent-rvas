# Grant the agent's managed identity the permissions this use case needs.
# Replace the placeholders. Do not put secrets in this file.
param([Parameter(Mandatory)][string]$PrincipalId)
Write-Host "Grant permissions to $PrincipalId"

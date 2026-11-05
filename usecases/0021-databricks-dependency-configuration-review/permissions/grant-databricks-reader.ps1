# Plane 1 (ARM): give the reporting identity Reader on the Databricks resource group.
# Run in the tenant that hosts the workspace. Do not put secrets in this file.
# Plane 2 (Databricks workspace and Unity Catalog) is granted in Databricks, not here:
# add the service principal in the workspace and give it CAN VIEW on in-scope jobs,
# pipelines, SQL warehouses and compute, plus BROWSE / USE CATALOG / USE SCHEMA in Unity Catalog.
# Never grant Secret Scope READ, Workspace Admin or Account Admin.
param(
  [Parameter(Mandatory)][string]$PrincipalId,
  [Parameter(Mandatory)][string]$SubscriptionId,
  [Parameter(Mandatory)][string]$ResourceGroup,
  [string]$ManagedResourceGroup = ""
)
$scopes = @("/subscriptions/$SubscriptionId/resourceGroups/$ResourceGroup")
if ($ManagedResourceGroup) { $scopes += "/subscriptions/$SubscriptionId/resourceGroups/$ManagedResourceGroup" }
foreach ($scope in $scopes) {
  az role assignment create --assignee-object-id $PrincipalId --assignee-principal-type ServicePrincipal --role Reader --scope $scope
}

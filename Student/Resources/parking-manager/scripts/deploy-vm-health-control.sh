#!/bin/bash
# Standalone deployment script for VM Health Control container app.
# Deploys into the existing chaos-control Container App Environment.
# Uses managed identity (Logs Ingestion API) — no shared keys needed.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA_DIR="$SCRIPT_DIR/../infrastructure"
BACKEND_DIR="$SCRIPT_DIR/../backend/vm-health-control"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

print_info()    { echo -e "${GREEN}[INFO]${NC} $1"; }
print_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
print_error()   { echo -e "${RED}[ERROR]${NC} $1"; }

# --- pre-flight checks ---
if ! command -v az &> /dev/null; then
  print_error "Azure CLI is not installed."
  exit 1
fi

if ! az account show &> /dev/null; then
  print_info "You need to login to Azure..."
  az login
fi

# --- read environment from parameters file ---
PARAMS_FILE="$INFRA_DIR/main.parameters.json"
if [ ! -f "$PARAMS_FILE" ]; then
  print_error "Parameters file not found: $PARAMS_FILE"
  exit 1
fi

ENVIRONMENT=$(grep -A1 '"environment"' "$PARAMS_FILE" | grep '"value"' | cut -d'"' -f4)
ENVIRONMENT="${ENVIRONMENT:-dev}"
LOCATION=$(grep -A1 '"location"' "$PARAMS_FILE" | grep '"value"' | cut -d'"' -f4)
LOCATION="${LOCATION:-swedencentral}"

CHAOS_RG="rg-parking-chaos-${ENVIRONMENT}"
HUB_RG="rg-parking-hub-${ENVIRONMENT}"

print_info "Environment : $ENVIRONMENT"
print_info "Location    : $LOCATION"
print_info "Chaos RG    : $CHAOS_RG"
print_info "Hub RG      : $HUB_RG"
echo ""

# --- resolve existing resources ---
print_info "Looking up existing Container App Environment in $CHAOS_RG..."
CAE_ID=$(az containerapp env list -g "$CHAOS_RG" --query "[0].id" -o tsv 2>/dev/null)
if [ -z "$CAE_ID" ]; then
  print_error "No Container App Environment found in $CHAOS_RG. Deploy the full infrastructure first."
  exit 1
fi
print_info "Container App Environment: $CAE_ID"

print_info "Looking up Container Registry..."
ACR_LOGIN_SERVER=$(az acr list -g "$HUB_RG" --query "[0].loginServer" -o tsv 2>/dev/null)
ACR_NAME=$(az acr list -g "$HUB_RG" --query "[0].name" -o tsv 2>/dev/null)

if [ -z "$ACR_LOGIN_SERVER" ]; then
  print_warning "No ACR found in $HUB_RG — will use the default hello-world image."
  CONTAINER_IMAGE="mcr.microsoft.com/azuredocs/containerapps-helloworld:latest"
  CONTAINER_REGISTRY=""
else
  print_info "ACR: $ACR_LOGIN_SERVER"
  CONTAINER_IMAGE="${ACR_LOGIN_SERVER}/vm-health-control:latest"
  CONTAINER_REGISTRY="$ACR_LOGIN_SERVER"
fi

print_info "Looking up Log Analytics workspace..."
LA_WORKSPACE_ID=$(az monitor log-analytics workspace list -g "$HUB_RG" \
  --query "[0].id" -o tsv 2>/dev/null)
LA_WORKSPACE_NAME=$(az monitor log-analytics workspace list -g "$HUB_RG" \
  --query "[0].name" -o tsv 2>/dev/null)
print_info "Log Analytics workspace: ${LA_WORKSPACE_NAME:-<not found>}"

if [ -z "$LA_WORKSPACE_ID" ]; then
  print_error "Missing Log Analytics workspace. Deploy the full infrastructure first."
  exit 1
fi

# --- optionally build & push the image ---
if [ -n "$ACR_LOGIN_SERVER" ]; then
  echo ""
  read -p "Build and push Docker image to $ACR_LOGIN_SERVER? (yes/no): " BUILD_IMAGE
  if [ "$BUILD_IMAGE" = "yes" ]; then
    print_info "Building image with ACR task..."
    az acr build \
      --registry "$ACR_NAME" \
      --image "vm-health-control:latest" \
      "$BACKEND_DIR"
    print_info "Image pushed: ${CONTAINER_IMAGE}"
  fi
fi

# --- Step 1: deploy custom table in hub RG ---
echo ""
TABLE_DEPLOYMENT_NAME="vm-health-table-$(date +%Y%m%d-%H%M%S)"
print_info "Creating custom table VMHealthStatus_CL in $HUB_RG..."
az deployment group create \
  --name "$TABLE_DEPLOYMENT_NAME" \
  --resource-group "$HUB_RG" \
  --template-file "$INFRA_DIR/modules/vm-health-table.bicep" \
  --parameters workspaceName="$LA_WORKSPACE_NAME"

if [ $? -ne 0 ]; then
  print_error "Failed to create custom table."
  exit 1
fi
print_info "Custom table created."

# --- Step 1b: deploy alert rules in hub RG ---
ALERTS_DEPLOYMENT_NAME="vm-health-alerts-$(date +%Y%m%d-%H%M%S)"
print_info "Creating VM health alert rules in $HUB_RG..."
az deployment group create \
  --name "$ALERTS_DEPLOYMENT_NAME" \
  --resource-group "$HUB_RG" \
  --template-file "$INFRA_DIR/modules/vm-health-alerts.bicep" \
  --parameters \
    location="$LOCATION" \
    logAnalyticsWorkspaceId="$LA_WORKSPACE_ID"

if [ $? -ne 0 ]; then
  print_warning "Alert rules deployment failed — continuing with container app deployment."
else
  print_info "Alert rules created."
fi

# --- Step 2: deploy container app + DCR in chaos RG (placeholder image first) ---
echo ""
DEPLOYMENT_NAME="vm-health-control-$(date +%Y%m%d-%H%M%S)"

print_info "Validating Bicep module..."
az bicep build --file "$INFRA_DIR/modules/vm-health-control.bicep"

# Phase 1: Deploy with a public placeholder image (no ACR auth needed)
# This creates the container app, DCE, DCR, and role assignments.
PLACEHOLDER_IMAGE="mcr.microsoft.com/azuredocs/containerapps-helloworld:latest"
print_info "Phase 1 — Deploying infrastructure with placeholder image..."
az deployment group create \
  --name "$DEPLOYMENT_NAME" \
  --resource-group "$CHAOS_RG" \
  --template-file "$INFRA_DIR/modules/vm-health-control.bicep" \
  --parameters \
    location="$LOCATION" \
    containerAppEnvironmentId="$CAE_ID" \
    containerImage="$PLACEHOLDER_IMAGE" \
    logAnalyticsWorkspaceId="$LA_WORKSPACE_ID"

if [ $? -ne 0 ]; then
  print_error "Infrastructure deployment failed — check the Azure Portal for details."
  exit 1
fi

print_info "Infrastructure deployed."

APP_URL=$(az deployment group show \
  --name "$DEPLOYMENT_NAME" \
  --resource-group "$CHAOS_RG" \
  --query "properties.outputs.containerAppUrl.value" -o tsv)
APP_NAME=$(az deployment group show \
  --name "$DEPLOYMENT_NAME" \
  --resource-group "$CHAOS_RG" \
  --query "properties.outputs.containerAppName.value" -o tsv)
PRINCIPAL_ID=$(az deployment group show \
  --name "$DEPLOYMENT_NAME" \
  --resource-group "$CHAOS_RG" \
  --query "properties.outputs.containerAppPrincipalId.value" -o tsv)

# Phase 2: Grant ACR pull and update to real image
if [ -n "$ACR_NAME" ] && [ -n "$PRINCIPAL_ID" ]; then
  print_info "Phase 2 — Granting ACR pull role..."
  ACR_ID=$(az acr show --name "$ACR_NAME" --query id -o tsv)
  az role assignment create \
    --assignee-object-id "$PRINCIPAL_ID" \
    --assignee-principal-type ServicePrincipal \
    --role AcrPull \
    --scope "$ACR_ID" 2>/dev/null || true

  print_info "Waiting for role propagation (30s)..."
  sleep 30

  print_info "Configuring ACR registry on container app..."
  az containerapp registry set \
    --name "$APP_NAME" \
    --resource-group "$CHAOS_RG" \
    --server "$ACR_LOGIN_SERVER" \
    --identity system

  print_info "Updating container app to $CONTAINER_IMAGE..."
  az containerapp update \
    --name "$APP_NAME" \
    --resource-group "$CHAOS_RG" \
    --image "$CONTAINER_IMAGE"

  if [ $? -eq 0 ]; then
    print_info "Container app updated with real image."
  else
    print_warning "Image update failed. You can retry manually:"
    echo "  az containerapp registry set --name $APP_NAME -g $CHAOS_RG --server $ACR_LOGIN_SERVER --identity system"
    echo "  az containerapp update --name $APP_NAME -g $CHAOS_RG --image $CONTAINER_IMAGE"
  fi
fi

echo ""
print_info "VM Health Control"
echo "  Container App : $APP_NAME"
echo "  URL           : $APP_URL"
echo ""
print_info "Authentication: managed identity (Monitoring Metrics Publisher role assigned on DCR)"
print_info "Next step: set REACT_APP_VM_HEALTH_CONTROL_URL=$APP_URL on the frontend App Service."

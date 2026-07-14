#!/bin/bash
# Deployment script for Azure SRE Demo Manager Infrastructure

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if Azure CLI is installed
if ! command -v az &> /dev/null; then
    print_error "Azure CLI is not installed. Please install it from https://docs.microsoft.com/cli/azure/install-azure-cli"
    exit 1
fi

print_info "Azure CLI version: $(az --version | head -n 1)"

# Check if Bicep is available
if ! az bicep version &> /dev/null; then
    print_warning "Bicep not found. Installing Bicep..."
    az bicep install
fi

print_info "Bicep version: $(az bicep version)"

# Get parameters
print_info "Starting deployment configuration..."
echo ""

# Check if user is logged in
if ! az account show &> /dev/null; then
    print_info "You need to login to Azure..."
    az login
fi

# Get subscription
SUBSCRIPTION_ID=$(az account show --query id -o tsv)
SUBSCRIPTION_NAME=$(az account show --query name -o tsv)
print_info "Using subscription: $SUBSCRIPTION_NAME ($SUBSCRIPTION_ID)"
echo ""

# Check for parameters file
PARAMS_FILE="main.parameters.json"
if [ ! -f "$PARAMS_FILE" ]; then
    print_error "Parameters file '$PARAMS_FILE' not found!"
    print_info "Please create a parameters file based on main.parameters.example.json"
    exit 1
fi

print_info "Using parameters file: $PARAMS_FILE"
echo ""

# Prompt for admin password (not stored in parameters file for security)
read -sp "Enter admin password for VMs: " ADMIN_PASSWORD
echo ""

if [ -z "$ADMIN_PASSWORD" ]; then
    print_error "Admin password is required!"
    exit 1
fi

# Validate password complexity
if [ ${#ADMIN_PASSWORD} -lt 12 ]; then
    print_error "Password must be at least 12 characters long!"
    exit 1
fi

echo ""
print_info "Deployment will use parameters from $PARAMS_FILE"
print_info "Admin password will be provided securely at deployment time"
echo ""

read -p "Do you want to proceed with the deployment? (yes/no): " CONFIRM
if [ "$CONFIRM" != "yes" ]; then
    print_warning "Deployment cancelled."
    exit 0
fi

# Generate deployment name
DEPLOYMENT_NAME="parking-infra-$(date +%Y%m%d-%H%M%S)"

# Get location from parameters file for validation/deployment location
LOCATION=$(cat "$PARAMS_FILE" | grep -A 2 '"location"' | grep '"value"' | cut -d'"' -f4)

print_info "Starting deployment: $DEPLOYMENT_NAME"
echo ""

# Build Bicep to check for errors
print_info "Validating Bicep templates..."
az bicep build --file main.bicep

# Validate the deployment
print_info "Validating deployment..."
VALIDATION_OUTPUT=$(az deployment sub validate \
    --location "$LOCATION" \
    --template-file main.bicep \
    --parameters "@$PARAMS_FILE" \
    --parameters adminPassword="$ADMIN_PASSWORD" \
    2>&1)

if [ $? -ne 0 ]; then
    print_error "Validation failed!"
    echo "$VALIDATION_OUTPUT"
    exit 1
fi

print_info "Validation successful!"
echo ""

# Deploy the infrastructure
print_info "Deploying infrastructure... This may take 15-20 minutes."
print_info "You can monitor progress in the Azure Portal or by running:"
print_info "  az deployment sub show --name $DEPLOYMENT_NAME"
echo ""

az deployment sub create \
    --name "$DEPLOYMENT_NAME" \
    --location "$LOCATION" \
    --template-file main.bicep \
    --parameters "@$PARAMS_FILE" \
    --parameters adminPassword="$ADMIN_PASSWORD"

if [ $? -eq 0 ]; then
    print_info "Deployment completed successfully!"
    echo ""
    print_info "Retrieving deployment outputs..."
    echo ""
    
    # Get outputs
    az deployment sub show --name "$DEPLOYMENT_NAME" --query properties.outputs -o json > deployment-outputs.json
    
    FRONTEND_URL=$(az deployment sub show --name "$DEPLOYMENT_NAME" --query "properties.outputs.frontendUrl.value" -o tsv)
    LISBON_API_URL=$(az deployment sub show --name "$DEPLOYMENT_NAME" --query "properties.outputs.lisbonApiUrl.value" -o tsv)
    MADRID_API_URL=$(az deployment sub show --name "$DEPLOYMENT_NAME" --query "properties.outputs.madridApiUrl.value" -o tsv)
    PARIS_API_URL=$(az deployment sub show --name "$DEPLOYMENT_NAME" --query "properties.outputs.parisApiUrl.value" -o tsv)
    
    print_info "Deployment Outputs:"
    echo ""
    echo "Frontend URL:     $FRONTEND_URL"
    echo "Lisbon API URL:   $LISBON_API_URL"
    echo "Madrid API URL:   $MADRID_API_URL"
    echo "Paris API URL:    $PARIS_API_URL"
    echo ""
    print_info "Full outputs saved to: deployment-outputs.json"
    echo ""
    print_info "Next steps:"
    echo "  1. Deploy your applications to the infrastructure"
    echo "  2. Configure DNS and SSL certificates"
    echo "  3. Set up monitoring and alerts"
    echo "  4. Review the infrastructure/README.md for post-deployment steps"
else
    print_error "Deployment failed! Check the Azure Portal for details."
    exit 1
fi

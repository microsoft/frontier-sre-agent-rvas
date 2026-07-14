#!/bin/bash
# Generate HTTPS Certificates for Paris API
# Run on Paris VM (Ubuntu 22.04)
# This script creates self-signed certificates and configures environment variables

set -e  # Exit on any error

# Configuration
API_DIRECTORY="${1:-.}"
CERT_DAYS="${2:-365}"
CERT_NAME="paris"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Paris API HTTPS Certificate Generation${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Function to print error and exit
error_exit() {
    echo -e "${RED}ERROR: $1${NC}" >&2
    exit 1
}

# Function to print success
print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

# Function to print info
print_info() {
    echo -e "${CYAN}$1${NC}"
}

# Step 1: Check if running as appropriate user
echo -e "${YELLOW}Step 1: Checking prerequisites...${NC}"
if ! command -v openssl &> /dev/null; then
    error_exit "OpenSSL not found. Install with: sudo apt-get install openssl"
fi
print_success "OpenSSL found: $(openssl version)"

# Resolve API directory
if [ "$API_DIRECTORY" = "." ]; then
    API_DIRECTORY="$(pwd)"
fi

# Convert to absolute path
if [[ ! "$API_DIRECTORY" = /* ]]; then
    API_DIRECTORY="$(cd "$API_DIRECTORY" 2>/dev/null && pwd)" || error_exit "Invalid API directory: $1"
fi

if [ ! -d "$API_DIRECTORY" ]; then
    error_exit "API directory not found: $API_DIRECTORY"
fi

print_info "API Directory: $API_DIRECTORY"
echo ""

# Step 2: Generate private key
echo -e "${YELLOW}Step 2: Generating private key (${CERT_NAME}.key)...${NC}"
cd "$API_DIRECTORY"

# Remove existing key if present
if [ -f "${CERT_NAME}.key" ]; then
    rm -f "${CERT_NAME}.key"
    echo "  Removed existing ${CERT_NAME}.key"
fi

openssl genrsa -out "${CERT_NAME}.key" 2048 || error_exit "Failed to generate private key"
print_success "Private key generated successfully"
echo ""

# Step 3: Generate self-signed certificate
echo -e "${YELLOW}Step 3: Generating self-signed certificate (${CERT_NAME}.crt)...${NC}"

# Remove existing certificate if present
if [ -f "${CERT_NAME}.crt" ]; then
    rm -f "${CERT_NAME}.crt"
    echo "  Removed existing ${CERT_NAME}.crt"
fi

openssl req -new -x509 -key "${CERT_NAME}.key" -out "${CERT_NAME}.crt" \
    -days "$CERT_DAYS" \
    -subj "/C=FR/ST=Paris/L=Paris/O=Parking/OU=API/CN=10.0.1.4" || \
    error_exit "Failed to generate certificate"

print_success "Self-signed certificate generated successfully (valid for $CERT_DAYS days)"
echo ""

# Step 4: Set proper permissions
echo -e "${YELLOW}Step 4: Setting file permissions...${NC}"
chmod 600 "${CERT_NAME}.key"
chmod 644 "${CERT_NAME}.crt"
print_success "File permissions set correctly"
echo ""

# Step 5: Verify certificate files
echo -e "${YELLOW}Step 5: Verifying certificate files...${NC}"
if [ -f "${CERT_NAME}.key" ] && [ -f "${CERT_NAME}.crt" ]; then
    print_success "${CERT_NAME}.key exists"
    print_success "${CERT_NAME}.crt exists"
    
    KEY_SIZE=$(stat --printf="%s" "${CERT_NAME}.key")
    CERT_SIZE=$(stat --printf="%s" "${CERT_NAME}.crt")
    print_info "  - ${CERT_NAME}.key: $KEY_SIZE bytes"
    print_info "  - ${CERT_NAME}.crt: $CERT_SIZE bytes"
else
    error_exit "Certificate files not found after generation"
fi
echo ""

# Step 6: Display certificate information
echo -e "${YELLOW}Step 6: Certificate Information${NC}"
print_info "Subject:"
openssl x509 -in "${CERT_NAME}.crt" -noout -subject
print_info "Issuer:"
openssl x509 -in "${CERT_NAME}.crt" -noout -issuer
print_info "Validity:"
openssl x509 -in "${CERT_NAME}.crt" -noout -dates
echo ""

# Step 7: Create/update environment configuration
echo -e "${YELLOW}Step 7: Setting environment variables...${NC}"

CERT_PATH="$API_DIRECTORY/${CERT_NAME}.crt"
KEY_PATH="$API_DIRECTORY/${CERT_NAME}.key"

ENV_FILE="$API_DIRECTORY/.env"
print_info "Creating/updating .env file: $ENV_FILE"

# Create .env file if it doesn't exist, otherwise preserve existing content
if [ -f "$ENV_FILE" ]; then
    # Remove existing CERT_PATH and KEY_PATH lines
    grep -v "^CERT_PATH=" "$ENV_FILE" | grep -v "^KEY_PATH=" > "$ENV_FILE.tmp" || true
    cat "$ENV_FILE.tmp" > "$ENV_FILE"
    rm -f "$ENV_FILE.tmp"
else
    touch "$ENV_FILE"
fi

# Add certificate paths
echo "CERT_PATH=$CERT_PATH" >> "$ENV_FILE"
echo "KEY_PATH=$KEY_PATH" >> "$ENV_FILE"

# Add other default variables if not present
if ! grep -q "^PORT=" "$ENV_FILE"; then
    echo "PORT=3003" >> "$ENV_FILE"
fi

if ! grep -q "^NODE_ENV=" "$ENV_FILE"; then
    echo "NODE_ENV=development" >> "$ENV_FILE"
fi

print_success "Environment variables added to .env"
echo ""

# Step 8: Display environment variables
echo -e "${CYAN}Environment Variables Set:${NC}"
grep -E "^(CERT_PATH|KEY_PATH|PORT|NODE_ENV)" "$ENV_FILE" || true
echo ""

# Step 9: Verify certificate and key match
echo -e "${YELLOW}Step 8: Verifying certificate/key integrity...${NC}"
CERT_MODULUS=$(openssl x509 -noout -modulus -in "${CERT_NAME}.crt" | openssl md5 | awk '{print $2}')
KEY_MODULUS=$(openssl rsa -noout -modulus -in "${CERT_NAME}.key" | openssl md5 | awk '{print $2}')

if [ "$CERT_MODULUS" = "$KEY_MODULUS" ]; then
    print_success "Certificate and key match (integrity verified)"
else
    error_exit "Certificate and key do not match!"
fi
echo ""

# Step 10: Display next steps
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}✓ Certificate Generation Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
print_info "Next Steps:"
echo "1. Ensure Paris API service reads the .env file"
echo "2. Restart the Paris API service:"
echo "   - If using systemd: sudo systemctl restart paris-parking-api"
echo "   - If running manually: kill the Node process and restart"
echo ""
echo "3. Test HTTPS endpoint:"
echo "   curl --insecure https://localhost:3003/api/parking"
echo ""
echo "4. Check logs for startup message indicating HTTPS protocol"
echo ""

echo -e "${GREEN}Script completed successfully!${NC}"

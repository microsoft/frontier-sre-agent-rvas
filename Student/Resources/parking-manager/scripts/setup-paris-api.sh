#!/bin/bash
# Complete setup script for Paris Parking API on Ubuntu VM
# Run this script on the Paris VM after certificates have been generated

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Paris Parking API Setup${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Configuration
API_DIR="${HOME}/paris-parking-api"
CERT_SOURCE_DIR="${1:-${HOME}/tmp}"
SERVICE_NAME="paris-parking-api"

# Functions
error_exit() {
    echo -e "${RED}ERROR: $1${NC}" >&2
    exit 1
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_info() {
    echo -e "${CYAN}$1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

# Step 1: Create API directory
echo -e "${YELLOW}Step 1: Creating API directory...${NC}"
if [ -d "$API_DIR" ]; then
    print_warning "Directory $API_DIR already exists"
else
    mkdir -p "$API_DIR"
    print_success "Created directory: $API_DIR"
fi
echo ""

# Step 2: Copy certificates
echo -e "${YELLOW}Step 2: Copying certificates...${NC}"
if [ -f "$CERT_SOURCE_DIR/paris.crt" ] && [ -f "$CERT_SOURCE_DIR/paris.key" ]; then
    cp "$CERT_SOURCE_DIR/paris.crt" "$API_DIR/"
    cp "$CERT_SOURCE_DIR/paris.key" "$API_DIR/"
    
    # Set proper permissions
    chmod 600 "$API_DIR/paris.key"
    chmod 644 "$API_DIR/paris.crt"
    
    print_success "Certificates copied from $CERT_SOURCE_DIR"
    print_info "  - paris.crt: $(stat --printf='%s' "$API_DIR/paris.crt") bytes"
    print_info "  - paris.key: $(stat --printf='%s' "$API_DIR/paris.key") bytes"
else
    error_exit "Certificates not found in $CERT_SOURCE_DIR. Please run generate-paris-certs.sh first."
fi
echo ""

# Step 3: Create .env file
echo -e "${YELLOW}Step 3: Creating .env file...${NC}"
cat > "$API_DIR/.env" << EOF
# Paris Parking API Configuration
PORT=3003
NODE_ENV=production

# HTTPS Certificate Paths
CERT_PATH=$API_DIR/paris.crt
KEY_PATH=$API_DIR/paris.key

# Parking Configuration
PARKING_NAME=Paris Centre Parking
PARKING_CITY=Paris
PARKING_LOCATION=Champs-Élysées, Paris

# Syslog Configuration
SYSLOG_FACILITY=local0
SYSLOG_TAG=ParisParkingAPI
EOF

print_success "Created .env file"
echo ""

# Step 4: Check if Node.js is installed
echo -e "${YELLOW}Step 4: Checking Node.js installation...${NC}"
if ! command -v node &> /dev/null; then
    error_exit "Node.js not found. Please install Node.js first: sudo apt-get install nodejs npm"
fi
print_success "Node.js found: $(node --version)"
print_success "npm found: $(npm --version)"
echo ""

# Step 5: Check for application files
echo -e "${YELLOW}Step 5: Checking application files...${NC}"
if [ ! -f "$API_DIR/server.js" ]; then
    print_warning "server.js not found in $API_DIR"
    echo -e "${CYAN}You need to deploy the application code to $API_DIR${NC}"
    echo -e "${CYAN}Options:${NC}"
    echo "  1. Copy files: scp -r backend/paris-parking-api/* azureadmin@<vm-ip>:$API_DIR/"
    echo "  2. Use git: cd $API_DIR && git clone <repo-url> ."
    echo ""
    echo -e "${YELLOW}Do you want to continue without application files? (y/n)${NC}"
    read -r response
    if [[ ! "$response" =~ ^[Yy]$ ]]; then
        error_exit "Setup cancelled. Please deploy application files first."
    fi
else
    print_success "Application files found"
    
    # Check for required files
    required_files=("server.js" "package.json" "syslogLogger.js")
    for file in "${required_files[@]}"; do
        if [ -f "$API_DIR/$file" ]; then
            print_info "  ✓ $file exists"
        else
            print_warning "  ✗ $file missing"
        fi
    done
fi
echo ""

# Step 6: Install dependencies
echo -e "${YELLOW}Step 6: Installing dependencies...${NC}"
if [ -f "$API_DIR/package.json" ]; then
    cd "$API_DIR"
    print_info "Running npm install..."
    npm install
    print_success "Dependencies installed"
else
    print_warning "package.json not found. Skipping npm install."
fi
echo ""

# Step 7: Create systemd service
echo -e "${YELLOW}Step 7: Creating systemd service...${NC}"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

# Create service file content
sudo tee "$SERVICE_FILE" > /dev/null << EOF
[Unit]
Description=Paris Parking API Service
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$API_DIR
ExecStart=/usr/bin/node server.js
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=paris-parking-api
Environment=NODE_ENV=production

[Install]
WantedBy=multi-user.target
EOF

print_success "Created systemd service file: $SERVICE_FILE"
echo ""

# Step 8: Enable and start service
echo -e "${YELLOW}Step 8: Configuring service...${NC}"
sudo systemctl daemon-reload
print_success "Reloaded systemd daemon"

sudo systemctl enable "$SERVICE_NAME"
print_success "Enabled $SERVICE_NAME to start on boot"
echo ""

# Step 9: Configure firewall
echo -e "${YELLOW}Step 9: Configuring firewall...${NC}"
if command -v ufw &> /dev/null; then
    sudo ufw allow 3003/tcp
    print_success "Opened port 3003 in firewall"
else
    print_warning "ufw not found. You may need to manually configure firewall."
fi
echo ""

# Step 10: Start service if application files exist
if [ -f "$API_DIR/server.js" ]; then
    echo -e "${YELLOW}Step 10: Starting service...${NC}"
    sudo systemctl start "$SERVICE_NAME"
    sleep 2
    
    if sudo systemctl is-active --quiet "$SERVICE_NAME"; then
        print_success "Service started successfully"
        echo ""
        sudo systemctl status "$SERVICE_NAME" --no-pager
    else
        print_warning "Service failed to start. Check logs with: sudo journalctl -u $SERVICE_NAME -n 50"
    fi
else
    print_warning "Skipping service start (no application files)"
fi
echo ""

# Summary
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Setup Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
print_info "Configuration Summary:"
echo "  API Directory: $API_DIR"
echo "  Certificate: $API_DIR/paris.crt"
echo "  Private Key: $API_DIR/paris.key"
echo "  Service: $SERVICE_NAME"
echo "  Port: 3003"
echo ""

if [ -f "$API_DIR/server.js" ]; then
    print_info "Service Commands:"
    echo "  Start:   sudo systemctl start $SERVICE_NAME"
    echo "  Stop:    sudo systemctl stop $SERVICE_NAME"
    echo "  Restart: sudo systemctl restart $SERVICE_NAME"
    echo "  Status:  sudo systemctl status $SERVICE_NAME"
    echo "  Logs:    sudo journalctl -u $SERVICE_NAME -f"
    echo ""
    
    print_info "Test Endpoints:"
    echo "  Health:  curl --insecure https://localhost:3003/health"
    echo "  Parking: curl --insecure https://localhost:3003/api/parking"
    echo ""
    
    print_info "View Syslog:"
    echo "  sudo tail -f /var/log/syslog | grep ParisParkingAPI"
    echo ""
else
    echo -e "${YELLOW}Next Steps:${NC}"
    echo "1. Deploy application files to $API_DIR"
    echo "2. Install dependencies: cd $API_DIR && npm install"
    echo "3. Start the service: sudo systemctl start $SERVICE_NAME"
    echo ""
fi

print_success "Paris Parking API setup completed!"

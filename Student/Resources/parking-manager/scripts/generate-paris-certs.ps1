# Generate HTTPS Certificates for Paris API
# Run with PowerShell 7+ (pwsh) on Paris VM (Ubuntu 22.04)
# This script creates self-signed certificates and configures environment variables

param(
    [string]$ApiDirectory = "/home/azureuser/backend/paris-parking-api",
    [int]$CertDays = 365
)

Write-Host "========================================" -ForegroundColor Green
Write-Host "Paris API HTTPS Certificate Generation" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""

# Verify API directory exists
if (-not (Test-Path $ApiDirectory)) {
    Write-Host "ERROR: API directory not found: $ApiDirectory" -ForegroundColor Red
    Exit 1
}

Write-Host "API Directory: $ApiDirectory" -ForegroundColor Cyan
Write-Host ""

# Step 1: Check OpenSSL availability
Write-Host "Step 1: Checking OpenSSL availability..." -ForegroundColor Yellow
$opensslPath = Get-Command openssl -ErrorAction SilentlyContinue
if ($null -eq $opensslPath) {
    Write-Host "ERROR: OpenSSL not found in PATH" -ForegroundColor Red
    Write-Host "Install OpenSSL: sudo apt-get install openssl" -ForegroundColor Yellow
    Exit 1
}
Write-Host "✓ OpenSSL found: $($opensslPath.Source)" -ForegroundColor Green
Write-Host ""

# Step 2: Generate private key
Write-Host "Step 2: Generating private key (paris.key)..." -ForegroundColor Yellow
Push-Location $ApiDirectory
try {
    if (Test-Path "paris.key") {
        Remove-Item "paris.key" -Force
        Write-Host "  Removed existing paris.key"
    }

    openssl genrsa -out paris.key 2048
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to generate private key"
    }
    Write-Host "✓ Private key generated successfully" -ForegroundColor Green
}
catch {
    Write-Host "ERROR: Failed to generate private key: $_" -ForegroundColor Red
    Pop-Location
    Exit 1
}
Write-Host ""

# Step 3: Generate self-signed certificate
Write-Host "Step 3: Generating self-signed certificate (paris.crt)..." -ForegroundColor Yellow
try {
    if (Test-Path "paris.crt") {
        Remove-Item "paris.crt" -Force
        Write-Host "  Removed existing paris.crt"
    }

    openssl req -new -x509 -key paris.key -out paris.crt -days $CertDays `
        -subj "/C=FR/ST=Paris/L=Paris/O=Parking/OU=API/CN=10.0.1.4"

    if ($LASTEXITCODE -ne 0) {
        throw "Failed to generate certificate"
    }
    Write-Host "✓ Self-signed certificate generated successfully (valid for $CertDays days)" -ForegroundColor Green
}
catch {
    Write-Host "ERROR: Failed to generate certificate: $_" -ForegroundColor Red
    Pop-Location
    Exit 1
}
Write-Host ""

# Step 4: Set proper permissions
Write-Host "Step 4: Setting file permissions..." -ForegroundColor Yellow
try {
    chmod 600 paris.key | Out-Null
    chmod 644 paris.crt | Out-Null
    Write-Host "✓ File permissions set correctly" -ForegroundColor Green
}
catch {
    Write-Host "WARNING: Could not set permissions (chmod not available)." -ForegroundColor Yellow
}
Write-Host ""

# Step 5: Verify certificate files
Write-Host "Step 5: Verifying certificate files..." -ForegroundColor Yellow
$keyExists = Test-Path "paris.key"
$certExists = Test-Path "paris.crt"

if ($keyExists -and $certExists) {
    Write-Host "✓ paris.key exists" -ForegroundColor Green
    Write-Host "✓ paris.crt exists" -ForegroundColor Green

    $keySize = (Get-Item "paris.key").Length
    $certSize = (Get-Item "paris.crt").Length
    Write-Host "  - paris.key: $keySize bytes" -ForegroundColor Cyan
    Write-Host "  - paris.crt: $certSize bytes" -ForegroundColor Cyan
}
else {
    Write-Host "ERROR: Certificate files not found" -ForegroundColor Red
    Pop-Location
    Exit 1
}
Write-Host ""

# Step 6: Display certificate information
Write-Host "Step 6: Certificate Information" -ForegroundColor Yellow
Write-Host "Subject:" -ForegroundColor Cyan
openssl x509 -in paris.crt -noout -subject
Write-Host "Issuer:" -ForegroundColor Cyan
openssl x509 -in paris.crt -noout -issuer
Write-Host "Validity:" -ForegroundColor Cyan
openssl x509 -in paris.crt -noout -dates
Write-Host ""

# Step 7: Create environment variable configuration
Write-Host "Step 7: Setting environment variables..." -ForegroundColor Yellow

$certPath = Join-Path $ApiDirectory "paris.crt"
$keyPath = Join-Path $ApiDirectory "paris.key"

$envFile = Join-Path $ApiDirectory ".env"
Write-Host "  Creating/updating .env file: $envFile" -ForegroundColor Cyan

if (Test-Path $envFile) {
    $envContent = Get-Content $envFile
    $envContent = $envContent | Where-Object { $_ -notmatch "^CERT_PATH=" -and $_ -notmatch "^KEY_PATH=" }
}
else {
    $envContent = @()
}

$envContent += "CERT_PATH=$certPath"
$envContent += "KEY_PATH=$keyPath"

if (-not ($envContent | Where-Object { $_ -match "^PORT=" })) {
    $envContent += "PORT=3003"
}

if (-not ($envContent | Where-Object { $_ -match "^NODE_ENV=" })) {
    $envContent += "NODE_ENV=development"
}

$envContent | Out-File -FilePath $envFile -Encoding UTF8 -Force
Write-Host "✓ Environment variables added to .env" -ForegroundColor Green
Write-Host ""

Write-Host "Environment Variables Set:" -ForegroundColor Cyan
Write-Host "  CERT_PATH=$certPath"
Write-Host "  KEY_PATH=$keyPath"
Write-Host ""

Write-Host "========================================" -ForegroundColor Green
Write-Host "✓ Certificate Generation Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Next Steps:" -ForegroundColor Yellow
Write-Host "1. Ensure Paris API service reads the .env file"
Write-Host "2. Restart the Paris API service:"
Write-Host "   - sudo systemctl restart paris-parking-api"
Write-Host "3. Test HTTPS endpoint:"
Write-Host "   curl --insecure https://localhost:3003/api/parking"
Write-Host ""

Pop-Location
Write-Host "Script completed successfully!" -ForegroundColor Green

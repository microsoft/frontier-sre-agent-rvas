# Generate HTTPS Certificates for Madrid API
# Run as Administrator on Madrid VM (Windows Server 2022)
# This script creates self-signed certificates and configures environment variables

param(
    [string]$ApiDirectory = "C:\Apps\madrid-parking-api",
    [string]$CertDays = "365"
)

Write-Host "========================================" -ForegroundColor Green
Write-Host "Madrid API HTTPS Certificate Generation" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""

# Check if running as Administrator
if (-not ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator")) {
    Write-Host "ERROR: This script must be run as Administrator" -ForegroundColor Red
    Exit 1
}

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
$opensslExe = $null
if ($null -ne $opensslPath) {
    $opensslExe = $opensslPath.Source
} else {
    $gitOpenSsl = "C:\Program Files\Git\usr\bin\openssl.exe"
    if (Test-Path $gitOpenSsl) {
        $opensslExe = $gitOpenSsl
    }
}

if (-not $opensslExe) {
    Write-Host "ERROR: OpenSSL not found in PATH" -ForegroundColor Red
    Write-Host "Install OpenSSL or Git for Windows (includes OpenSSL)" -ForegroundColor Yellow
    Exit 1
}
Write-Host "✓ OpenSSL found: $opensslExe" -ForegroundColor Green
Write-Host ""

# Step 2: Generate private key
Write-Host "Step 2: Generating private key (madrid.key)..." -ForegroundColor Yellow
Push-Location $ApiDirectory
try {
    # Remove existing key if present
    if (Test-Path "madrid.key") {
        Remove-Item "madrid.key" -Force
        Write-Host "  Removed existing madrid.key"
    }
    
    & $opensslExe genrsa -out madrid.key 2048
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
Write-Host "Step 3: Generating self-signed certificate (madrid.crt)..." -ForegroundColor Yellow
try {
    # Remove existing certificate if present
    if (Test-Path "madrid.crt") {
        Remove-Item "madrid.crt" -Force
        Write-Host "  Removed existing madrid.crt"
    }
    
    & $opensslExe req -new -x509 -key madrid.key -out madrid.crt -days $CertDays `
        -subj "/C=ES/ST=Madrid/L=Madrid/O=Parking/OU=API/CN=10.0.1.5"
    
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

# Step 4: Verify certificate files
Write-Host "Step 4: Verifying certificate files..." -ForegroundColor Yellow
$keyExists = Test-Path "madrid.key"
$certExists = Test-Path "madrid.crt"

if ($keyExists -and $certExists) {
    Write-Host "✓ madrid.key exists" -ForegroundColor Green
    Write-Host "✓ madrid.crt exists" -ForegroundColor Green
    
    $keySize = (Get-Item "madrid.key").Length
    $certSize = (Get-Item "madrid.crt").Length
    Write-Host "  - madrid.key: $keySize bytes" -ForegroundColor Cyan
    Write-Host "  - madrid.crt: $certSize bytes" -ForegroundColor Cyan
}
else {
    Write-Host "ERROR: Certificate files not found" -ForegroundColor Red
    Pop-Location
    Exit 1
}
Write-Host ""

# Step 5: Display certificate information
Write-Host "Step 5: Certificate Information" -ForegroundColor Yellow
Write-Host "Subject:" -ForegroundColor Cyan
& $opensslExe x509 -in madrid.crt -noout -subject
Write-Host "Issuer:" -ForegroundColor Cyan
& $opensslExe x509 -in madrid.crt -noout -issuer
Write-Host "Validity:" -ForegroundColor Cyan
& $opensslExe x509 -in madrid.crt -noout -dates
Write-Host ""

# Step 6: Create environment variable configuration
Write-Host "Step 6: Setting environment variables..." -ForegroundColor Yellow

$certPath = Join-Path $ApiDirectory "madrid.crt"
$keyPath = Join-Path $ApiDirectory "madrid.key"

# Set environment variables in .env file
$envFile = Join-Path $ApiDirectory ".env"
Write-Host "  Creating/updating .env file: $envFile" -ForegroundColor Cyan

if (Test-Path $envFile) {
    # Read existing content and update
    $envContent = Get-Content $envFile
    $envContent = $envContent | Where-Object { $_ -notmatch "^CERT_PATH=" -and $_ -notmatch "^KEY_PATH=" }
}
else {
    $envContent = @()
}

# Add certificate paths
$envContent += "CERT_PATH=$certPath"
$envContent += "KEY_PATH=$keyPath"

# Write back to file
$envContent | Out-File -FilePath $envFile -Encoding UTF8 -Force
Write-Host "✓ Environment variables added to .env" -ForegroundColor Green

# Also display what was set
Write-Host ""
Write-Host "Environment Variables Set:" -ForegroundColor Cyan
Write-Host "  CERT_PATH=$certPath"
Write-Host "  KEY_PATH=$keyPath"
Write-Host ""

# Step 7: Instructions for next steps
Write-Host "========================================" -ForegroundColor Green
Write-Host "✓ Certificate Generation Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Next Steps:" -ForegroundColor Yellow
Write-Host "1. Ensure Madrid API service reads the .env file"
Write-Host "2. Restart the Madrid API service:"
Write-Host "   - net stop MadridParkingAPI"
Write-Host "   - net start MadridParkingAPI"
Write-Host ""
Write-Host "3. Test HTTPS endpoint:"
Write-Host "   curl.exe --insecure https://localhost:3002/api/parking"
Write-Host ""
Write-Host "4. Check logs for startup message indicating HTTPS protocol"
Write-Host ""

Pop-Location
Write-Host "Script completed successfully!" -ForegroundColor Green

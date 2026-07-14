# Setup script to install GitHub Actions self-hosted runner on Madrid VM
# This script should be run on the Madrid VM (vm-madrid-api) as Administrator

# Variables - UPDATE THESE
$GITHUB_OWNER = "your-github-username-or-org"
$GITHUB_REPO = "sre-lab"
$RUNNER_NAME = "madrid-vm-runner"
$RUNNER_LABELS = "self-hosted,windows,madrid-vm"

Write-Host "🚀 Setting up GitHub Actions Self-Hosted Runner on Madrid VM" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host ""

# Check if running as Administrator
$currentPrincipal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
$isAdmin = $currentPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    Write-Host "❌ This script must be run as Administrator" -ForegroundColor Red
    Write-Host "Right-click PowerShell and select 'Run as Administrator'" -ForegroundColor Yellow
    exit 1
}

Write-Host "⚙️  Configuration:" -ForegroundColor Cyan
Write-Host "   GitHub Owner/Org: $GITHUB_OWNER"
Write-Host "   Repository: $GITHUB_REPO"
Write-Host "   Runner Name: $RUNNER_NAME"
Write-Host "   Runner Labels: $RUNNER_LABELS"
Write-Host ""

$confirm = Read-Host "Is this configuration correct? (yes/no)"
if ($confirm -ne "yes") {
    Write-Host "❌ Setup cancelled. Please edit this script and update the variables." -ForegroundColor Red
    exit 0
}

# Create a directory for the runner
$RUNNER_DIR = "C:\actions-runner"
if (-not (Test-Path $RUNNER_DIR)) {
    New-Item -ItemType Directory -Path $RUNNER_DIR | Out-Null
}

Set-Location $RUNNER_DIR

Write-Host ""
Write-Host "📥 Downloading GitHub Actions Runner..." -ForegroundColor Cyan

# Get the latest runner version
$releases = Invoke-RestMethod -Uri "https://api.github.com/repos/actions/runner/releases/latest"
$asset = $releases.assets | Where-Object { $_.name -like "*win-x64*.zip" } | Select-Object -First 1

if (-not $asset) {
    Write-Host "❌ Could not find Windows runner package" -ForegroundColor Red
    exit 1
}

$downloadUrl = $asset.browser_download_url
$zipFile = "actions-runner-win-x64.zip"

Write-Host "Downloading from: $downloadUrl"
Invoke-WebRequest -Uri $downloadUrl -OutFile $zipFile

# Extract the installer
Write-Host "📦 Extracting runner package..." -ForegroundColor Cyan
Add-Type -AssemblyName System.IO.Compression.FileSystem
[System.IO.Compression.ZipFile]::ExtractToDirectory("$RUNNER_DIR\$zipFile", $RUNNER_DIR)
Remove-Item $zipFile

Write-Host ""
Write-Host "🔑 Runner Token Required" -ForegroundColor Yellow
Write-Host "========================" -ForegroundColor Yellow
Write-Host ""
Write-Host "To get your runner registration token:"
Write-Host "1. Go to: https://github.com/$GITHUB_OWNER/$GITHUB_REPO/settings/actions/runners/new"
Write-Host "2. Select 'Windows' as the operating system"
Write-Host "3. Copy the token from the 'Configure' section"
Write-Host ""
$RUNNER_TOKEN = Read-Host "Paste your runner registration token" -AsSecureString
$RUNNER_TOKEN_PLAIN = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
    [Runtime.InteropServices.Marshal]::SecureStringToBSTR($RUNNER_TOKEN)
)

if ([string]::IsNullOrWhiteSpace($RUNNER_TOKEN_PLAIN)) {
    Write-Host "❌ No token provided. Setup cancelled." -ForegroundColor Red
    exit 1
}

# Configure the runner
Write-Host ""
Write-Host "⚙️  Configuring the runner..." -ForegroundColor Cyan
.\config.cmd `
    --url "https://github.com/$GITHUB_OWNER/$GITHUB_REPO" `
    --token "$RUNNER_TOKEN_PLAIN" `
    --name "$RUNNER_NAME" `
    --labels "$RUNNER_LABELS" `
    --work "_work" `
    --runasservice `
    --windowslogonaccount "NT AUTHORITY\NETWORK SERVICE" `
    --unattended `
    --replace

if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Runner configuration failed" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "✅ GitHub Actions Runner Setup Complete!" -ForegroundColor Green
Write-Host ""

# Check if service is running
$service = Get-Service -Name "actions.runner.*" -ErrorAction SilentlyContinue
if ($service) {
    Write-Host "📊 Service Status:" -ForegroundColor Cyan
    $service | Format-Table -AutoSize
    
    if ($service.Status -ne 'Running') {
        Write-Host "▶️  Starting the runner service..." -ForegroundColor Yellow
        Start-Service $service.Name
        Start-Sleep -Seconds 3
        $service = Get-Service -Name $service.Name
    }
    
    if ($service.Status -eq 'Running') {
        Write-Host "✅ Runner service is active!" -ForegroundColor Green
    } else {
        Write-Host "⚠️  Runner service status: $($service.Status)" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "🎉 Setup complete! The runner is now ready to receive jobs." -ForegroundColor Green
Write-Host ""
Write-Host "📝 Useful Commands:" -ForegroundColor Cyan
Write-Host "   Check status:  Get-Service 'actions.runner.*'"
Write-Host "   View logs:     Get-EventLog -LogName Application -Source 'actions.runner.*' -Newest 20"
Write-Host "   Stop runner:   Stop-Service 'actions.runner.*'"
Write-Host "   Start runner:  Start-Service 'actions.runner.*'"
Write-Host "   Restart:       Restart-Service 'actions.runner.*'"
Write-Host ""
Write-Host "🔗 Verify in GitHub:" -ForegroundColor Cyan
Write-Host "   https://github.com/$GITHUB_OWNER/$GITHUB_REPO/settings/actions/runners"
Write-Host ""

# Show firewall recommendation
Write-Host "🔥 Firewall Configuration:" -ForegroundColor Yellow
Write-Host "If the API needs to be accessible from other VMs, ensure port 3002 is open:"
Write-Host "   New-NetFirewallRule -DisplayName 'Madrid Parking API' -Direction Inbound -LocalPort 3002 -Protocol TCP -Action Allow"
Write-Host ""

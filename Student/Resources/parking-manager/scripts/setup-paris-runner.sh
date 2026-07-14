#!/bin/bash
# Setup script to install GitHub Actions self-hosted runner on Paris VM
# This script should be run on the Paris VM (vm-paris-api)

set -e

echo "🚀 Setting up GitHub Actions Self-Hosted Runner on Paris VM"
echo "============================================================"

# Check if running as the correct user (not root)
if [ "$EUID" -eq 0 ]; then 
   echo "❌ Please do not run this script as root. Run as the azureadmin user."
   exit 1
fi

# Variables - UPDATE THESE
GITHUB_OWNER="your-github-username-or-org"
GITHUB_REPO="sre-lab"
RUNNER_NAME="paris-vm-runner"
RUNNER_LABELS="self-hosted,linux,paris-vm"

echo ""
echo "⚙️  Configuration:"
echo "   GitHub Owner/Org: $GITHUB_OWNER"
echo "   Repository: $GITHUB_REPO"
echo "   Runner Name: $RUNNER_NAME"
echo "   Runner Labels: $RUNNER_LABELS"
echo ""

read -p "Is this configuration correct? (yes/no): " CONFIRM
if [ "$CONFIRM" != "yes" ]; then
    echo "❌ Setup cancelled. Please edit this script and update the variables."
    exit 0
fi

# Create a directory for the runner
RUNNER_DIR="$HOME/actions-runner"
mkdir -p $RUNNER_DIR
cd $RUNNER_DIR

echo ""
echo "📥 Downloading GitHub Actions Runner..."

# Download the latest runner package
RUNNER_VERSION=$(curl -s https://api.github.com/repos/actions/runner/releases/latest | grep tag_name | cut -d '"' -f 4 | sed 's/v//')
curl -o actions-runner-linux-x64.tar.gz -L "https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz"

# Extract the installer
echo "📦 Extracting runner package..."
tar xzf ./actions-runner-linux-x64.tar.gz
rm actions-runner-linux-x64.tar.gz

echo ""
echo "🔑 Runner Token Required"
echo "========================"
echo ""
echo "To get your runner registration token:"
echo "1. Go to: https://github.com/$GITHUB_OWNER/$GITHUB_REPO/settings/actions/runners/new"
echo "2. Copy the token from the 'Configure' section"
echo ""
read -sp "Paste your runner registration token: " RUNNER_TOKEN
echo ""

if [ -z "$RUNNER_TOKEN" ]; then
    echo "❌ No token provided. Setup cancelled."
    exit 1
fi

# Configure the runner
echo ""
echo "⚙️  Configuring the runner..."
./config.sh \
    --url "https://github.com/$GITHUB_OWNER/$GITHUB_REPO" \
    --token "$RUNNER_TOKEN" \
    --name "$RUNNER_NAME" \
    --labels "$RUNNER_LABELS" \
    --work "_work" \
    --unattended \
    --replace

# Install the runner as a service
echo ""
echo "🔧 Installing runner as a systemd service..."
sudo ./svc.sh install $USER

# Start the service
echo "▶️  Starting the runner service..."
sudo ./svc.sh start

# Check status
echo ""
echo "✅ GitHub Actions Runner Setup Complete!"
echo ""
echo "📊 Service Status:"
sudo ./svc.sh status

echo ""
echo "🎉 Setup complete! The runner is now active and ready to receive jobs."
echo ""
echo "📝 Useful Commands:"
echo "   Check status:  cd $RUNNER_DIR && sudo ./svc.sh status"
echo "   View logs:     journalctl -u actions.runner.* -f"
echo "   Stop runner:   cd $RUNNER_DIR && sudo ./svc.sh stop"
echo "   Start runner:  cd $RUNNER_DIR && sudo ./svc.sh start"
echo "   Restart:       cd $RUNNER_DIR && sudo ./svc.sh restart"
echo ""
echo "🔗 Verify in GitHub:"
echo "   https://github.com/$GITHUB_OWNER/$GITHUB_REPO/settings/actions/runners"

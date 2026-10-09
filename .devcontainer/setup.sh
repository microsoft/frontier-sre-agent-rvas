#!/usr/bin/env bash
set -euo pipefail

sudo apt-get update
sudo apt-get install -y --no-install-recommends make jq curl gettext-base coreutils findutils python3 python3-venv python3-yaml
sudo /usr/bin/python3 -m venv --system-site-packages /opt/workshop-python

# Use Microsoft's supported Ubuntu repository for the Entra-capable ODBC sqlcmd.
if ! command -v sqlcmd >/dev/null 2>&1 && [[ ! -x /opt/mssql-tools18/bin/sqlcmd ]]; then
  repository="$(mktemp)"
  trap 'rm -f "$repository"' EXIT
  curl --fail --silent --show-error --location \
    https://packages.microsoft.com/config/ubuntu/24.04/packages-microsoft-prod.deb -o "$repository"
  sudo dpkg -i "$repository"
  sudo apt-get update
  sudo env ACCEPT_EULA=Y apt-get install -y --no-install-recommends mssql-tools18 unixodbc
fi
az extension add --name containerapp --upgrade

export PATH="/opt/workshop-python/bin:/opt/mssql-tools18/bin:$PATH"
bash Student/Resources/infra/scripts/preflight.sh --local
bash Student/Resources/infra/scripts/preflight.sh --local --track sql-dba

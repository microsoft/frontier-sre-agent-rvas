#!/usr/bin/env bash
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y curl ca-certificates python3 build-essential rsyslog
work=$(mktemp -d)
trap 'rm -f "$work/node.tar.gz"; rmdir "$work"' EXIT
curl --fail --show-error --location --retry 3 \
  https://nodejs.org/dist/v22.23.3/node-v22.23.3-linux-x64.tar.gz -o "$work/node.tar.gz"
echo "1084aa36196bba4c3a5e69a1ee388a6e4ff729dad09445fbcd434b28fe3c24af  $work/node.tar.gz" | sha256sum --check
tar -xzf "$work/node.tar.gz" -C /usr/local --strip-components=1
export PATH="/usr/local/bin:$PATH"
node --version
python3 - <<'PY'
import base64, gzip, json
from pathlib import Path
root = Path('/opt/signalops')
for item in json.loads(gzip.decompress(base64.b64decode('__PAYLOAD__'))):
    target = (root / item['path']).resolve()
    if not target.is_relative_to(root):
        raise ValueError('Application payload escapes installation directory')
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(base64.b64decode(item['content']))
PY
cd /opt/signalops/paris-parking-api
npm ci --omit=dev --no-audit --no-fund
id signalops >/dev/null 2>&1 || useradd --system --home /opt/signalops --shell /usr/sbin/nologin signalops
chmod -R a+rX /opt/signalops
cat > /etc/systemd/system/signalops-paris.service <<'UNIT'
[Unit]
Description=SignalOps Paris Parking API
After=network-online.target rsyslog.service
Wants=network-online.target
[Service]
Type=simple
User=signalops
WorkingDirectory=/opt/signalops/paris-parking-api
ExecStart=/usr/local/bin/node server.js
Environment=NODE_ENV=production
Environment=PORT=3003
Environment=CHAOS_CONTROL_URL=__CHAOS_URL__
Environment=PARIS_DEPENDENCY_URL=__DEPENDENCY_URL__
Restart=always
RestartSec=5
NoNewPrivileges=true
[Install]
WantedBy=multi-user.target
UNIT
systemctl enable --now rsyslog
systemctl daemon-reload
systemctl enable signalops-paris
systemctl restart signalops-paris
for attempt in $(seq 1 30); do
  if curl --fail --silent http://127.0.0.1:3003/health >/dev/null; then
    logger -p local0.info -t ParisParkingAPI "SignalOps Paris application installation verified"
    echo SIGNALOPS_VM_READY
    exit 0
  fi
  sleep 2
done
journalctl -u signalops-paris --no-pager -n 40
echo "Paris application health check failed" >&2
exit 1

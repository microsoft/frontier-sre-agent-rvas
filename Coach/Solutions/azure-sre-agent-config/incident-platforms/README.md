# Incident Platforms

Use Terraform `incident_management` for incident management properties currently exposed by `Microsoft.App/agents`.

If a future Azure SRE Agent API exposes additional incident platform configuration as a documented data-plane endpoint, add YAML manifests here and extend `Infra/scripts/sre-agent-config.sh` with that endpoint mapping.
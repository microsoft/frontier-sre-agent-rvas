**[Home](../README.md)** | [Lab Details](../../Lab-Details.md)

# Deploy with Terraform

This self-contained path deploys hub-spoke networking, Azure Firewall, VM tiers,
Grubify and Parking Manager, plus an SRE Agent and telemetry connectors. It is
separate from the Bicep/azd deployment. Application images are built into **your
existing Azure Container Registry (ACR)**; no upstream lab images or deployment
repository are used.

## Prepare

### Deployment files hosted here

The Terraform root, workload module, application sources, agent configuration,
knowledge documents and setup scripts are bundled here. No other checkout is
required.

- [Download the Terraform deployment package](signalops-terraform.tar.gz) from this site.
- [Root configuration](./infra/main.tf)
- [Agent and scoped permissions](./infra/agent.tf)
- [Deployment inputs](./infra/variables.tf)
- [Deployment outputs](./infra/outputs.tf)
- [Provider versions](./infra/terraform.tf) and [provider configuration](./infra/providers.tf)
- [Workload resources](./infra/modules/workload/main.tf)
- [Image builder](./infra/scripts/Build-Images.ps1)
- [VM and agent completion](./infra/scripts/Complete-Lab.ps1)
- [License](./infra/LICENSE)

The downloadable archive contains `infra`, including curated `apps` build
contexts and a SHA-256 source manifest. It excludes state, credentials, variable
files, plans, certificates, dependencies and provider caches.

### Prerequisites

- Terraform 1.7 or later (including support for the bundled mock tests), Azure
  CLI, and PowerShell 7.
- An existing ACR in the selected subscription, its name and resource group,
  ACR Tasks enabled, permission to build/push images, and permission to assign
  its image-pull role. Both classic `AcrPull` and ABAC repository-reader mode
  are supported. The default builder requires a network-accessible registry;
  a private-only ACR requires a separately approved private build/network design.
- An approved disposable Azure subscription with permission to create resources
  and role assignments, sufficient regional VM quota, and the required resource
  providers registered.
- An existing regional Network Watcher in `NetworkWatcherRG`, or approval to
  create it with `create_network_watcher=true` in a subscription where that group
  does not already exist.
- Budget approval: the full lab includes billable Firewall, Bastion, VMs,
  storage, monitoring, Container Apps, agent usage and registry builds.
- Access to Azure SRE Agent in the agent region. The workload defaults to
  `uksouth`; the independent `agent_location` defaults to `swedencentral`.
  Confirm service/model availability, policy and regional quota before applying.

Azure APIs, Terraform providers, Microsoft/.NET and Node/nginx base images,
npm packages, Ubuntu packages and official Node.js downloads remain normal
external service dependencies. This is not an offline/air-gapped deployment.
Application image references are digest-pinned in your ACR. Container Apps use a
user-assigned image-pull identity, not registry admin credentials.

### Open the deployment

From this repository's root:

```powershell
Set-Location '.\SRE SignalOps\Deployment\Terraform\infra'
```

Alternatively, download the package above, open PowerShell in the download
directory, and extract it:

```powershell
tar -xzf .\signalops-terraform.tar.gz
Set-Location .\infra
```

## Deploy

### 1. Authenticate and build owned images

Use the same terminal for the following stages:

```powershell
az login
az account set --subscription '<your-subscription-id>'
$env:ARM_SUBSCRIPTION_ID = (az account show --query id -o tsv).Trim()
az account show --query '{Name:name,Id:id,Tenant:tenantId}' -o table

# Offline inspection only: no Azure calls or image publishing.
.\scripts\Build-Images.ps1 -RegistryName '<existing-acr-name>' `
  -RegistryResourceGroup '<existing-acr-resource-group>' -PlanOnly
.\scripts\Complete-Lab.ps1 -ValidateOnly

# Publishes seven images to the registry you explicitly selected.
.\scripts\Build-Images.ps1 -RegistryName '<existing-acr-name>' `
  -RegistryResourceGroup '<existing-acr-resource-group>'
```

The builder resolves every manifest digest and writes ignored
`images.auto.tfvars.json` with registry identifiers, pull role and image
references. It does not create the registry or give Terraform ownership of it.
In a checkout it builds the local application sources; the download builds its
bundled `apps` sources. Review the printed contexts before publishing.

### 2. Validate and review the infrastructure plan

```powershell
terraform init
terraform validate
terraform test
terraform plan -out=deployment.tfplan
```

Terraform prompts for the sensitive `vm_admin_password` and
`berlin_mcp_auth_token` inputs without echoing them. Choose a unique password
meeting Azure VM complexity rules and a random MCP token of at least 32
characters. Do not put either in source files or shell history.

The default region is `uksouth`. To change it, add `-var='location=<region>'`
to the plan command. If a Network Watcher must be created, also add
`-var='create_network_watcher=true'` after confirming there is no existing
`NetworkWatcherRG` to adopt. Review regional SKU availability and quota first.

Default resource group names start with `rg-signalops-tf-` to distinguish this
deployment from other labs. Check every planned scope and stop if it overlaps
an existing environment. Do not import or reuse another deployment's state.

### 3. Deploy the reviewed infrastructure

Only apply after reviewing and approving the saved plan:

```powershell
terraform apply deployment.tfplan
Remove-Item -LiteralPath .\deployment.tfplan

terraform output managed_resource_ids
terraform output parking_resource_groups
$FrontendUrl = terraform output -raw sample_food_frontend_url
Invoke-WebRequest -Uri $FrontendUrl | Select-Object StatusCode
$FoodResourceGroup = terraform output -raw sample_food_resource_group_name
az containerapp list --resource-group $FoodResourceGroup `
  --query '[].{Name:name,State:properties.runningStatus,FQDN:properties.configuration.ingress.fqdn}' -o table
```

Confirm both Grubify Container Apps are running, the frontend responds, and the
browser loads restaurant data. Resource provisioning alone does not establish
application health or populated telemetry.

The API allows the actual frontend HTTPS origin. The NVA subnet routes outbound
traffic through the lab Firewall before cloud-init starts. Agent Contributor
permissions are limited to the nine lab workload resource groups; subscription
access is Monitoring Reader. The identity also has read/publish access to the
agent's own Application Insights telemetry. The current deployer receives SRE Agent
Administrator on the new agent.

## Verify

### Complete and verify the applications and agent

```powershell
.\scripts\Complete-Lab.ps1
```

This explicitly invoked post-apply step:

- Transfers the bundled Madrid/Paris applications and shared middleware through
  Azure VM Run Command, with no Git clone.
- Installs checksum-verified Node.js 22.23.3 and lockfile-resolved npm dependencies.
- Configures durable startup: a Windows scheduled task for Madrid and a systemd
  service for Paris. Madrid uses its dedicated lab VM's SYSTEM account to write
  Windows events; Paris runs as an unprivileged service user and writes syslog.
- Connects both applications to the lab chaos controller. Paris uses the lab
  Grubify health endpoint as its dependency, not a third-party time service.
- Requires successful local VM health checks, then uses the shared SignalOps
  registration script to register `aca-app-incident-handler`,
  `network-traffic-analyst`, `cost-optimization-agent` and the enabled
  `sample-food-http-errors` plan. All specialists use Review mode; network and
  cost have read-only tools.
- Verifies the plan accepts Sev0 through Sev4, matches `grubify`, and uses
  **Review** mode. Agent action mode is also Review; writes require approval.
- Uploads four approved knowledge documents, checks the live inventory/indexer
  state, and verifies public Grubify HTTP responses.

Disabled VMs are reported as not installed. Any failed native command, setup
marker, health check, registration or plan verification stops the script.
Agent authorization/platform readiness retries are bounded; fix the reported
error and rerun instead of treating partial setup as success.

Knowledge indexing and telemetry ingestion remain asynchronous. Before injecting
faults, verify all four filenames in memory, successful retrieval in Mission 02,
recent application requests, VM Heartbeat/Event/Syslog data, and the live alert
route. HTTP checks alone do not prove CORS: open the frontend and confirm its API
requests succeed in the browser.

### State and cleanup

Terraform's local state and saved plans contain sensitive values even when
inputs are marked sensitive. Keep them outside published content and source
control. Use an approved access-controlled remote backend before collaborating;
never upload state or variable files to this website.

Only destroy the disposable resources owned by this state when authorized.
Review a `terraform plan -destroy` before running `terraform destroy`. Do not
delete the state first. The existing ACR and its built images are not deleted by
Terraform; remove only explicitly approved lab image versions separately.

### SignalOps readiness gate

Load the non-secret context without making these resources azd-owned:

```powershell
$Lab = & .\scripts\Get-SignalOpsContext.ps1 -TerraformPath (Get-Location).Path
$Lab | Format-List
```

Continue with the [mission context instructions](../../Missions/README.md).
Do not provision Bicep stages 00-02 into these resource groups. Later
backup/Teams/GitHub and advanced incident-routing scenarios still require their
documented optional integrations or evidence packs; this path does not silently
create external connectors or promise every scenario is ready.

In the checkout, the maintained configuration lives in `SRE SignalOps\Config`
and the shared registration script in `SRE SignalOps\Scripts`. The downloadable
package copies both into `infra\config` and `infra\scripts`, so it remains
independently runnable without another checkout.

Offline format, schema, graph, packaging and script checks do not guarantee an
error-free Azure deployment. Permissions, ACR network/build policy, quotas,
regional capacity, agent availability, role propagation and runtime health must
be verified in the target subscription. No live deployment is needed to inspect
or validate the package locally.

Continue to [Missions](../../Missions/README.md) only after those checks pass.

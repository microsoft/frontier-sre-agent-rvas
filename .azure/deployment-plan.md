# SRE SignalOps azd Parity Deployment Plan

## Status

Validated

## Objective

Replace the Terraform-only bootstrap assumptions in SRE SignalOps Missions 00-02 with an Azure Developer CLI deployment path that reproduces the SignalOps core of the existing MCAPS Azure baseline in a new isolated environment.

## Confirmed Baseline

- Subscription: `MCAPS-Hybrid-REQ-150072-2026-rakau`
- Subscription ID: `b1e100ca-fff5-4e0e-9847-2e44bf47b68c`
- Tenant ID: `16b3c013-d300-468d-ac64-7eda0820b6d3`
- Location: `swedencentral`
- Workload resource group: `rg-sre-spoke-foodapp-paas`
- Agent resource group: `rg-sre-agent`
- Agent: `contoso-sre-agent-dev`
- Shared Log Analytics workspace: `law-rgn3ao` in `rg-sre-hub-connectivity`

## Current Finding

The existing `Student/Resources/grubify/azure.yaml` project deploys a standalone Grubify application stack. It does not currently provision the complete Terraform baseline, including the Azure SRE Agent, its identity and RBAC, its connectors, or the complete shared topology. Its current `azd up` command therefore cannot be presented as Terraform-equivalent.

## Approved Scope

- Deployment scope: SignalOps core subset.
- Environment behavior: create a new isolated azd environment by default.
- Included: food API and frontend, Container Apps environment, registry, shared observability, SRE Agent, managed identity and RBAC, and two Azure telemetry connectors.
- Excluded: hub/spoke IaaS topology, Azure Firewall, Bastion, parking services, and monitoring resources used only by later specialist scenarios.

## Deployment Stages

1. **Mission 00 - Provision workload foundation and applications**
   - Authenticate azd and select the confirmed subscription, tenant, environment, and Sweden Central location.
   - Provision isolated Bicep-defined workload resources with Terraform-equivalent roles and relationships.
   - Build and deploy the API and frontend through azd.
   - Verify resource inventory, Container App state, frontend HTTP response, and workspace-backed Application Insights.
2. **Mission 01 - Provision Azure SRE Agent core**
   - Provision the agent resource group, managed identity, agent Log Analytics workspace, Application Insights, Azure SRE Agent, managed scopes, and least-required role assignments from the same azd template.
   - Provision the agent stage through azd.
   - Verify ARM provisioning state, power state, endpoint, action configuration, managed resources, and RBAC.
3. **Mission 02 - Provision evidence connectors and validate ground truth**
   - Provision Bicep resources for the Log Analytics and Application Insights connectors from the same azd template.
   - Provision connector configuration through azd without storing interactive credentials in source control.
   - Verify connector inventory, repository state, Agent Memory status, knowledge inventory, and live workload evidence.

## Planned Artifacts

- Introduce an azd project under `SRE SignalOps` whose Bicep entry point covers all three deployment stages.
- Parameterize resource names from `AZURE_ENV_NAME` for isolated deployment; do not reconcile or take ownership of the Terraform-managed resources.
- Update Missions 00-02 with exact azd commands and post-command parity checks.
- Update Coach Solutions 00-02 and mission scripts to match the deployment workflow.
- Preserve unrelated Terraform files as migration reference; do not execute or modify the live Azure environment during content preparation.

## Validation Gates

- [x] All validation checks pass
   - [x] 1. AZD installation verified
   - [x] 2. `azure.yaml` schema validation completed
   - [x] 3. Local `signalops-core` environment created
   - [x] 4. azd authentication status verified
   - [x] 5. Environment subscription and location verified
   - [x] 6. Aspire pre-provisioning checks skipped; this is not an Aspire project
   - [x] 7. `azd provision --preview --no-prompt` succeeds for each deployment stage
   - [x] 8. API and frontend builds succeed
   - [x] 9. Docker build contexts verified
   - [x] 10. `azd package --no-prompt` succeeds
   - [x] 11. Azure policy impact reviewed
   - [x] 12. Aspire post-provisioning checks skipped; this is not an Aspire project
- `azd config list` and environment values resolve to the confirmed subscription, tenant, and region.
- Bicep builds successfully.
- `azd provision --preview` or ARM what-if shows the expected resource set without unintended deletion.
- Workload parity: the focused food workload, Container Apps environment, registry, and workspace-backed observability are represented.
- Agent parity: agent, identity, workspaces, action configuration, managed resources, and RBAC are represented.
- Evidence parity: both Azure telemetry connectors are represented and post-deployment API checks are documented.
- Missions contain no Terraform deployment commands.

## Role Assignment Verification

- Status: Verified by static Bicep review.
- Identities checked: API user-assigned identity, frontend user-assigned identity, and SRE Agent user-assigned identity.
- API and frontend identities receive `AcrPull` on the environment registry only.
- The agent identity receives Reader, Log Analytics Reader, Monitoring Reader, and Contributor on the new isolated workload resource group. Contributor is intentionally limited to that resource group so autonomous remediation cannot modify the existing Terraform-managed environment.
- The agent identity receives Monitoring Contributor at subscription scope because the approved knowledge graph includes the subscription; it does not receive subscription-wide Contributor or Owner.
- The deploying principal receives Azure SRE Agent Administrator on the new agent resource only.
- No application data-plane roles are required beyond ACR image pull; application access is public HTTP and the agent telemetry connectors use managed identity with Azure resource IDs.
- Issues: none outstanding.

## Validation Proof

- `azd version`: passed with Azure Developer CLI `1.32.0` after upgrading from `1.30.0`.
- `az bicep version`: passed with Bicep CLI `0.46.1` after upgrading the Azure CLI component.
- `azd auth login --check-status`: passed as `rakau@microsoft.com`.
- `azd env get-value`: confirmed subscription `b1e100ca-fff5-4e0e-9847-2e44bf47b68c` and location `swedencentral`.
- `az bicep build --file "SRE SignalOps/infra/main.bicep"`: passed with no diagnostics using Bicep `0.46.1`.
- Mission 00 preview (`DEPLOY_AGENT=false`, `DEPLOY_CONNECTORS=false`): passed; seven isolated workload resources are created and no existing resources are changed or deleted.
- Mission 01 preview (`DEPLOY_AGENT=true`, `DEPLOY_CONNECTORS=false`): passed; the isolated agent layer is added to the workload resources.
- Mission 02 preview (`DEPLOY_AGENT=true`, `DEPLOY_CONNECTORS=true`): passed; the compiled ARM graph contains both connector child resources. azd's summary does not list child connectors or RBAC assignments separately.
- `dotnet build Student/Resources/grubify/GrubifyApi/GrubifyApi.csproj --configuration Release`: passed.
- `npm ci` and `npm run build` in the Grubify frontend: passed. The build reports existing ESLint warnings but no errors.
- Docker context review: passed; both Dockerfiles are present and the frontend lockfile is colocated with its Dockerfile for `npm ci`.
- `azd package --all --no-prompt`: passed. No local artifacts are emitted because both services specify `docker.remoteBuild: true`.
- PowerShell parser check for `Invoke-SignalOpsDemo.ps1`: passed.
- Azure policy review: passed. The subscription has three Defender/ASC initiatives and no assignment restricting the planned location, resource types, SKUs, or tags.
- `git diff --check` for the intended task files: passed.
- Azure mutation: none. All infrastructure checks used preview mode.

## Safety

- Infrastructure preparation and documentation only until this plan is approved.
- Do not run `azd up`, `azd provision`, ARM deployment, Terraform, or any command that changes Azure during preparation.
- Use `azd provision --preview` or `az deployment ... what-if` before any future deployment to the existing subscription.
- Never include tokens, secrets, Terraform state, or OAuth credentials in azd environment files or documentation.

## Approval

Approved by the user: SignalOps core subset in a new isolated environment.
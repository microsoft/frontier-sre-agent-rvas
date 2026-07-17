**[Home](./README.md)** | [Next Solution >](./Solution-01.md)

# Coach Guide — Challenge 00: Prerequisites & Lab Setup

## Purpose

This challenge establishes the baseline environment. Its primary function is logistics — everyone must reach the same starting point before the scenarios begin. It should take **20–30 minutes** for an experienced team with pre-staged credentials; allow **45–60 minutes** if Azure subscriptions need to be configured fresh.

The key conceptual payload is the ARM vs. data-plane split: Terraform owns Azure resources, `sre-agent-config.sh` owns the agent's intelligence layer. This distinction recurs throughout every subsequent challenge.

## Mini-Lecture (5 min before challenge)

Cover:
- The lab architecture: hub-spoke network, IaaS VMs, VNet Flow Logs, Grubify on Azure Container Apps
- The Azure SRE Agent topology: one agent resource → skills → subagents → connectors → incident filters → scheduled tasks
- The two deployment tools: Terraform (ARM) and `sre-agent-config.sh` (data-plane API)
- The 6 scenarios they will run and the overall arc (PaaS → IaaS → network)

## Common Issues and Hints

### `az login` tenant mismatch
If `terraform apply` fails with a subscription access error, verify `az account show` returns the right subscription before running `make`. Set it explicitly: `az account set --subscription "<id>"`.

### Terraform state lock
If `terraform apply` was interrupted, state may be locked. Run `terraform force-unlock <lock-id>` or delete the `.terraform.lock.hcl` inside `Coach/Solutions/infra/`.

### `make config-sre-agent` exits with non-zero but all PUTs succeeded
This usually means a subagent failed to apply. The error message will show which file. The most common historical failure: a subagent with a non-empty `handoffs` list (not supported in workspace mode). Check the output carefully — the script now streams errors directly.

### GitHub OAuth authorization not sticky
The OAuth token is stored per-user in the SRE Agent service. If the portal shows "Unauthorized" after authorization, try a private/incognito window and re-authorize. The token is not tied to a machine, so any team member can do this step.

### `validate-sample-food-app.sh` fails with DNS timeout
The Container Apps ingress provisioning can take up to 5 minutes after `terraform apply` completes. Retry with a 3-minute wait.

### Baseline traffic script errors
`generate-baseline-traffic.sh` uses `az vm run-command` to run curl from `vm-client`. If it fails with "VM not ready," check `provisioning_state` for the VM in the portal — sometimes a VM extension hangs on first boot.

## Success Criteria Notes

- **7 subagents** expected: `aca-app-incident-handler`, `azure-resource-config-auditor`, `code-analyzer`, `cost-optimization-agent`, `iaas-vm-incident-handler`, `issue-triager`, `network-traffic-analyst`
- **8 skills** expected: `connectivity-diagnostics`, `cost-optimization`, `nsg-deny-flow-investigation`, `rbac-and-resource-access-check`, `sample-food-container-app-incident-analysis`, `traffic-analytics-kql-analysis`, `udr-asymmetry-investigation`, `vnet-flow-logs-and-ingestion`
- **3 incident filters** expected: `network-observability-review`, `sample-food-http-errors`, `web-tier-nginx`
- If a subagent or skill count is off, run `./infra/scripts/sre-agent-config.sh verify` from `Coach/Solutions/` to see what's missing

## ARM vs. Data-Plane Discussion

The expected answer to the "explain to your coach" question:
- **Terraform manages**: the `Microsoft.App/agents` ARM resource (incl. `incidentManagementConfiguration`, RBAC, Log Analytics workspace, app infrastructure)
- **`sre-agent-config.sh` manages**: the agent's intelligence layer via the `https://azuresre.ai` data-plane API — skills, subagents, connectors, knowledge files, incident filters, scheduled tasks
- **Why separate?**: ARM state + Terraform plan/apply are not designed for the high-churn, schema-evolving data-plane resources. The separation also allows rapid iteration on agent intelligence without touching infra state.

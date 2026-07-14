# ADR 0001: Azure SRE Agent IaC Boundaries

## Status

Accepted

## Context

Azure SRE Agent exposes a mixed management surface:

- Some resources are standard Azure resources supported by AzureRM.
- The agent and connectors are documented as `Microsoft.App` resource types deployable through AzAPI.
- Several agent configuration items are exposed through Azure SRE Agent APIs and are not documented as Terraform resources.

The customer needs a simple, reliable, resilient, and enterprise-ready method for initial deployment and ongoing operations.

## Decision

Use a two-layer model:

1. Terraform is authoritative for AzureRM and documented AzAPI resources.
2. YAML/Markdown under `06-sre-agent-configuration/` is authoritative for API-only Azure SRE Agent configuration.

The API layer is applied by `03-scripts/sre-agent-config.sh`, which validates local manifests, converts them to JSON, and calls documented control-plane or data-plane APIs.

Exception (2026-06-14): the Azure Monitor incident platform is owned by Terraform, not the API layer. It is a property of the `Microsoft.App/agents` resource (`body.properties.incidentManagementConfiguration`), which Terraform already manages through AzAPI; under principle 1 it therefore belongs to Terraform. The former data-plane manifest `incident-platforms/azure-monitor.yaml` has been removed (recoverable from Git history; Terraform is the single owner). This also removes a two-owner conflict: a full-body Terraform PUT did not declare `incidentManagementConfiguration`, so each `terraform apply` reset it to `None` and broke every incident filter until the platform was re-applied by the script. Incident platforms that require a secret (`connectionKey`, e.g. PagerDuty/ServiceNow) stay in the API layer to avoid putting secrets in Terraform state; only the credential-free AzMonitor platform is migrated.

Manifests whose names start with `example-` are reference templates only. `sre-agent-config.sh` excludes them from every discovery path (validate, plan, apply, verify, delete), so they stay in Git for documentation but are never deployed to the cloud agent.

The repository root `.sre-agent-layout.env` file is the layout contract for operational scripts. Scripts parse it as data, not shell code, so the numbered folder layout can evolve without reintroducing hardcoded legacy paths.

## Consequences

Positive:

- Clear ownership boundary between Terraform state and API-managed desired state.
- Maintainers know exactly where to make Day-3 changes.
- YAML and Markdown are easy to review in pull requests.
- The design avoids copying complex sample scripts wholesale.

Trade-offs:

- API-only configuration is not in Terraform state.
- A separate verification path is required.
- Live portal changes can create drift unless teams enforce Git-first operations.
- The imported Sample Food / Grubify subagents (`aca-app-incident-handler` [imported as `incident-handler`], `code-analyzer`, `issue-triager`) are configured as `Autonomous` with Azure CLI write tools to preserve upstream lab behavior. This raises remediation blast radius; least-privilege RBAC is the bounding control, and the action mode can be downgraded to `Review` per subagent if stricter governance is required.
- Maximum-autonomy reconfiguration (2026-06-14): for this non-production demo lab the agent global `actionConfiguration.mode` is `Autonomous` with `accessLevel` `High`, the incident-handling subagents (`aca-app-incident-handler`, `iaas-vm-incident-handler`, `network-traffic-analyst`) and all domain-routed incident filters run `Autonomous`, and the `block-unsafe-remediation` hook has been **removed** (deleted live; its manifest removed from the repository, recoverable from Git history). The agent therefore investigates **and remediates** (in-guest restart, NSG rule delete, route change, firewall rule change) with no human approval gate; least-privilege RBAC is the only remaining blast-radius boundary. To re-harden, re-create the hook manifest from Git history and `sre-agent-config.sh apply --target hooks`, add a global tool access policy denying `RunAzCliWriteCommands(az * delete *)` and similar, or set the filters back to `Review`. The data-plane API ignores `spec.enabled` for hooks (it uses `activationMode`, default `always`), so a hook is disabled by not deploying it, not by a flag.
- Domain-routing rule (2026-06-14): incident response plans route by **failure domain**, keyed by incident title (`titleContains` / `titleNotContains`) on top of severity, so each specialist owns one domain — ACA app (`aca-app-incident-handler`), IaaS web tier (`iaas-vm-incident-handler`), hub networking (`network-traffic-analyst`); the read-only configuration auditor (`azure-resource-config-auditor`) is reachable on-demand. The three wired plans are disjoint by construction (Sev1 `food`; Sev2 `nginx` vs not-`nginx`). This replaced the earlier severity-only bands and added the `iaas-vm-incident-handler` subagent (the NGINX-down web-tier incident previously had no owner and was mis-routed to the networking specialist because it shared the Sev2 band). Trade-off / production-posture exception: under full autonomy the maximum-blast-radius action is an autonomous hub Azure Firewall / NSG / route change by `network-traffic-analyst` across the hub-and-spoke (cross-spoke reach). This is accepted for the non-production demo lab (every scenario has a restore script). **For production, gate the cross-spoke networking domain**: set the `network-observability-review` plan to `Review` (or re-enable the hook), while ACA/IaaS in-guest remediation can remain `Autonomous`. Title matching is case-insensitive (the data-plane rejects case-insensitive duplicate tokens), so single keywords are used. Pruned 2026-07-02: the `hub-firewall-network` (Sev1 `afw`) and `config-audit-review` (Sev3) plans were removed as dormant — this lab fires no `afw`-titled or Sev3 alert (the `afw-vflta-hub-NetworkRuleHit` alert lives in a different hub resource group); keep only response plans wired to real incidents.
- Fleet segmentation note (2026-07-04): the **number** of `Microsoft.App/agents` resources Terraform manages is driven by **governance boundaries** (residency, Prod/Non-Prod, Platform/Application, independent approval authority, permission posture), **not** by engineering teams, applications, subscriptions, or technology layers. "One agent per team" is a structural anti-pattern (Conway's Law): functional silos collapse to per-layer and stream-aligned teams collapse to per-app. Team competence maps to **subagents** (data-plane, Inverse Conway Maneuver), not to additional agent resources. See [../architectural-guide-lines/azure-sre-agent-fleet-architecture-guidelines.md](../architectural-guide-lines/azure-sre-agent-fleet-architecture-guidelines.md) §4.1 and [../architectural-guide-lines/how-many-sre-agent.md](../architectural-guide-lines/how-many-sre-agent.md).

## References

- https://learn.microsoft.com/en-us/azure/sre-agent/deploy-iac
- https://learn.microsoft.com/en-us/azure/sre-agent/api-reference
- https://learn.microsoft.com/en-us/azure/templates/microsoft.app/agents?pivots=deployment-language-terraform
- https://learn.microsoft.com/en-us/azure/templates/microsoft.app/agents/connectors?pivots=deployment-language-terraform
- https://developer.hashicorp.com/terraform/language/style
- https://martinfowler.com/bliki/ConwaysLaw.html
- https://teamtopologies.com/key-concepts
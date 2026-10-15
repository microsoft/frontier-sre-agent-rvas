# Fabric SRE workshop infrastructure

> COACHES ONLY — Do not share with participants.

This standalone Terraform root provisions one shared, paid Fabric capacity and
one Azure SRE Agent per team, with its own user-assigned identity and logging.
It does not deploy the Azure Operations or SQL DBA workloads.

Each participant user or workshop security group receives **SRE Agent
Administrator**, scoped to its team's agent. The deploying identity receives
that role too. Runtime identities use `ReadOnly` mode, receive only the shared
module's read roles on the capacity, and do not receive its subscription-level
Contributor or Monitoring Contributor grants. Fabric data access is a separate
coach-managed permission boundary.

## Deploy before the event

Prerequisites: Terraform 1.5+, Azure CLI authentication to the intended
subscription/tenant, permission to create resources and role assignments
(Owner, or Contributor plus Role Based Access Control Administrator), Fabric
tenant setup authority, capacity quota, and supported regions for both services.
Register `Microsoft.Fabric`, `Microsoft.App`, `Microsoft.ManagedIdentity`,
`Microsoft.OperationalInsights`, and `Microsoft.Insights` as needed.

From this directory in Linux Bash:

```bash
az login
az account set --subscription "<workshop-subscription-id>"
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars: unique capacity name, coach UPNs, team names and real Entra object IDs.
terraform init
terraform fmt -check
terraform validate
terraform plan -out=workshop.tfplan
terraform apply workshop.tfplan
terraform output -json
```

Keep variable files, plans, and state private; use an approved remote state
backend for a shared deployment. Check price, region availability, and quota
before applying. F4 is only a monitoring starting point; size for FUAM refresh,
always-on Eventstream/Eventhouse, demo workloads, and audience concurrency.
Agent resources incur separate Azure SRE Agent charges.

## Coach-owned Fabric setup and audience handoff

Terraform provisions Azure resources, **not** Fabric workspaces, FUAM pipelines,
Capacity Metrics configuration, Eventstream/Eventhouse items, event
subscriptions, tenant settings, or Fabric item permissions. Complete these
steps once for the event, not once per participant:

1. Obtain the capacity's **Fabric UUID** from the Fabric portal or capacities
   API (it is not its ARM resource ID). Create/assign approved telemetry and
   monitored workspaces to the provisioned capacity.
2. Deploy [FUAM](../../../../Student/Resources/fabric-sre-agent/fuam/README.md)
   once, configure its service principal and refresh schedule, and verify
   recent consumption rows.
3. Deploy [Capacity Events](../../../../Student/Resources/fabric-sre-agent/capacity-events/README.md)
   once: create the Eventstream, Eventhouse/KQL database, `OperationsTable`,
   retention, and capacity-operation subscription. Keep the coach as subscription
   owner/capacity admin. Start ingestion before the event; history is not backfilled.
4. Share both backends' relevant items with the audience using Viewer/read
   permissions. Grant each team's agent UAMI the required Fabric tenant/API,
   workspace, SQL endpoint, and KQL database read access. Verify effective data
   permissions with harmless reads; no audience capacity-admin or backend
   authoring rights are needed. Keep FUAM collector credentials private.
5. Give each team its agent URL, SRE Agent Administrator assignment, identity
   IDs, both backends' workspace/item IDs, FUAM SQL server/database,
   Eventhouse query URI/database/table, capacity UUID/SKU/region, freshness,
   retained-history bounds, approved workload/run IDs, and known limitations.
   Test with a participant account and the actual agent identity before handoff.

Students select one shared backend per agent and configure connectors, skills,
tools, and matching custom instructions in Challenge 02. They must not create
another telemetry stack or change the shared refresh, retention, or subscription.
Separate team agents prevent teams overwriting each other's global instructions.

## Cleanup

Export any approved evidence first. The coach removes Fabric event
subscriptions and workshop-only workspaces/items, refresh schedules, and
collector access, then reviews and runs `terraform destroy` from this root.
Deleting the Azure capacity is not a substitute for cleaning up Fabric items.
Do not pause the monitoring capacity while ingestion is expected to continue.

References:
[Fabric capacity ARM schema](https://learn.microsoft.com/azure/templates/microsoft.fabric/2023-11-01/capacities),
[SRE Agent ARM schema](https://learn.microsoft.com/azure/templates/microsoft.app/2026-01-01/agents).

## Local verification

With Terraform **1.7+** (mock-provider test support), run `terraform init`,
`terraform validate`, and `terraform test` from this directory. Tests do not
authenticate to Azure or create resources. They check shared capacity/team
access, invalid inputs, read-only agent permissions, and preservation of the
existing Azure Operations agent defaults. A real subscription plan/apply and
Fabric access/ingestion checks are still required before an event.

# Day-2 and Day-3 Operations

This runbook explains how to change a production Azure SRE Agent after the initial deployment.

## Change Types

| Change type | Edit location | Command | Verification |
| --- | --- | --- | --- |
| Azure resource, identity, RBAC, telemetry | `infra/` | `terraform plan`, `terraform apply` | Terraform outputs and Azure SRE Agent ARM state |
| Skill, subagent, tool, prompt, automation | `azure-sre-agent-config/` | `infra/scripts/sre-agent-config.sh plan`, `apply` | `infra/scripts/sre-agent-config.sh verify` |
| Knowledge file | `azure-sre-agent-config/knowledge/files` | `infra/scripts/sre-agent-config.sh apply` | Agent memory status and indexer status |
| Repository connection | `azure-sre-agent-config/repos` | `infra/scripts/sre-agent-config.sh apply` | Repo list and connectivity test in portal/API |
| Hook or plugin | `azure-sre-agent-config/hooks` or `azure-sre-agent-config/plugins` | `infra/scripts/sre-agent-config.sh apply` | Hook/plugin list and test thread |

## Standard Change Flow

1. Create a short-lived branch.
2. Edit the smallest relevant file.
3. Run local validation.
4. Open a pull request with the expected behavior change.
5. Run Terraform plan or API config plan.
6. Apply only after review.
7. Run verify.
8. Record evidence in the release checklist.

## Infrastructure Change

Edit concrete values directly in `infra/*.tf`. Do not introduce `variables.tf`, `.tfvars`, or pass-through locals for one-off project values.

```bash
terraform -chdir=infra fmt -recursive
terraform -chdir=infra init
terraform -chdir=infra plan
terraform -chdir=infra apply
```

Use this path for Azure resources and RBAC. Do not use the API script for Terraform-managed resources.

## Agent Configuration Change

```bash
Student/Resources/scenarios/scripts/sre-agent-config.sh validate
Student/Resources/scenarios/scripts/sre-agent-config.sh plan \
  --subscription <subscription-id> \
  --resource-group <agent-rg> \
  --agent <agent-name>
Student/Resources/scenarios/scripts/sre-agent-config.sh apply \
  --subscription <subscription-id> \
  --resource-group <agent-rg> \
  --agent <agent-name>
Student/Resources/scenarios/scripts/sre-agent-config.sh verify \
  --subscription <subscription-id> \
  --resource-group <agent-rg> \
  --agent <agent-name>
```

## Rollback

For Terraform, revert the commit and run a new plan.

For configuration, revert the YAML/Markdown change and run `apply` again. The repository remains the source of truth.

## Export Policy

Export is allowed for backup or initial onboarding from a portal-created agent. After Git adoption, do not use export as the normal change path because it can mask unreviewed portal changes.

## Destructive Operations

`delete` requires `--yes` and deletes only resources represented by local manifests. `prune` is intentionally blocked in v1 because enterprise customers need an explicit drift policy before deleting live resources that are not in Git.
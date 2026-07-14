# Day-2 and Day-3 Operations

This runbook explains how to change a production Azure SRE Agent after the initial deployment.

## Change Types

| Change type | Edit location | Command | Verification |
| --- | --- | --- | --- |
| Azure resource, identity, RBAC, telemetry | `04-terraform/` | `terraform plan`, `terraform apply` | Terraform outputs and Azure SRE Agent ARM state |
| Skill, subagent, tool, prompt, automation | `06-sre-agent-configuration/` | `03-scripts/sre-agent-config.sh plan`, `apply` | `03-scripts/sre-agent-config.sh verify` |
| Knowledge file | `06-sre-agent-configuration/knowledge/files` | `03-scripts/sre-agent-config.sh apply` | Agent memory status and indexer status |
| Repository connection | `06-sre-agent-configuration/repos` | `03-scripts/sre-agent-config.sh apply` | Repo list and connectivity test in portal/API |
| Hook or plugin | `06-sre-agent-configuration/hooks` or `06-sre-agent-configuration/plugins` | `03-scripts/sre-agent-config.sh apply` | Hook/plugin list and test thread |

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

Edit concrete values directly in `04-terraform/*.tf`. Do not introduce `variables.tf`, `.tfvars`, or pass-through locals for one-off project values.

```bash
terraform -chdir=04-terraform fmt -recursive
terraform -chdir=04-terraform init
terraform -chdir=04-terraform plan
terraform -chdir=04-terraform apply
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
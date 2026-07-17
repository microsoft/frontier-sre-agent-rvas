# Release Checklist

Use this checklist before sharing a customer-ready release.

## Gate 0: Source and Scope

- [ ] Resource support matrix reviewed.
- [ ] Terraform/API boundary accepted.
- [ ] Target Azure SRE Agent region selected.
- [ ] Model provider and data residency reviewed.

## Gate 1: Static Validation

- [ ] No root `variables.tf`, `.tfvars`, or pass-through locals were introduced for project literals.
- [ ] `Student/Resources/scenarios/scripts/check-terraform-direct-values.sh`
- [ ] `terraform -chdir=infra fmt -recursive`
- [ ] `terraform -chdir=infra init -backend=false`
- [ ] `terraform -chdir=infra validate`
- [ ] `Student/Resources/scenarios/scripts/sre-agent-config.sh validate`
- [ ] `bash -n Student/Resources/scenarios/scripts/*.sh`
- [ ] `shellcheck Student/Resources/scenarios/scripts/*.sh` when available in the execution environment.
- [ ] Secret scan completed.

## Gate 2: Dry Run

- [ ] Terraform plan reviewed.
- [ ] Configuration plan reviewed.
- [ ] Destructive changes explicitly identified.

## Gate 3: Disposable Deployment

- [ ] Resource provider prerequisites satisfied.
- [ ] Terraform apply completed in disposable resource group.
- [ ] Agent `provisioningState` is `Succeeded`.
- [ ] Agent endpoint is returned by ARM.

## Gate 4: Configuration Apply

- [ ] API-only configuration applied successfully.
- [ ] Verify command completed.
- [ ] Knowledge upload tested with a non-sensitive sample file.

## Gate 5: Idempotency

- [ ] Re-running Terraform plan shows no unexpected changes.
- [ ] Re-running configuration apply is no-op or reports no unexpected drift.

## Gate 6: Day-3 Change Test

- [ ] Update one skill or common prompt.
- [ ] Apply configuration only.
- [ ] Verify live state.
- [ ] Revert and apply again.

## Gate 7: Customer Handoff

- [ ] README reviewed.
- [ ] Day-2/Day-3 runbook reviewed.
- [ ] Security and secrets document reviewed.
- [ ] Known limitations documented.
# Security and Secrets

## Principles

1. The agent starts in `Review` mode and `Low` access unless a workload owner approves more privilege.
2. Terraform manages RBAC deliberately and visibly.
3. Secrets are never committed to Git.
4. Terraform state is treated as sensitive.
5. API-only configuration changes are planned, applied, and verified separately from Terraform.

## Terraform State

Terraform state can contain sensitive values. Store state in an approved remote backend with encryption, locking, and restricted access before production use.

Do not place connector API keys, PATs, or incident platform secrets in Terraform variables unless the customer has explicitly approved the state handling model.

## Local Development Secrets

For local testing only, use a non-committed `.env` file:

```bash
cp .env.example .env
```

The deployment script can substitute `${VARIABLE_NAME}` placeholders when `envsubst` is installed and variables are set.

## Production Secrets

Use CI/CD secret stores or Key Vault-backed injection. Do not rely on developer laptops for production configuration.

## RBAC Defaults

The Terraform root assigns these baseline permissions to the agent UAMI on managed scopes:

- Reader
- Log Analytics Reader
- Monitoring Reader

It can also assign Monitoring Contributor at subscription scope for Azure Monitor alert lifecycle operations, matching the documented Azure SRE Agent permission model.

Reference: https://learn.microsoft.com/en-us/azure/sre-agent/permissions

## Network Requirements

Allow browser and API access to the documented Azure SRE Agent domains, including `*.azuresre.ai` and `sre.azure.com`.

Reference: https://learn.microsoft.com/en-us/azure/sre-agent/network-requirements

## Data Residency

For European Union data residency requirements, prefer MicrosoftFoundry/Azure OpenAI model choices in EU regions such as Sweden Central. Anthropic requires explicit legal and data residency review.

Reference: https://learn.microsoft.com/en-us/azure/sre-agent/create-and-set-up
# Permissions and scope

## Confirm scope before collection

Obtain the customer tenant, explicit subscription allowlist, resource groups or resource IDs, and UTC observation window. Existing access is not consent to inspect every accessible subscription. Confirm the discovered count against an expected inventory and list excluded, denied, truncated and unassessed scopes.

Some bundled tools enumerate the identity's accessible subscriptions. Run these only with an identity restricted to the approved scope. If that restriction cannot be established, use the related skill's scoped CLI collection instead. Do not describe a report filtered after collection as an access boundary.

## Azure SRE Agent permission levels

The Azure SRE Agent Reader permission level is not synonymous with the Azure Reader role alone. The documented preconfigured roles include resource group Reader, Log Analytics Reader and Monitoring Reader, plus subscription Monitoring Contributor. An identity with no assigned scope has no access. Role assignments and available tools must be checked on the actual host.

Read only behavior is an operating policy. It is not enforced merely by putting text in a skill, especially when a general terminal tool is available. Configure host authorization, approved scopes, tool restrictions and human approval independently.

## Match permissions to evidence

| Evidence | Permission considerations |
| --- | --- |
| ARM configuration and Resource Graph | Reader at each approved target scope; Resource Graph visibility does not prove complete inventory |
| Azure Monitor metrics and alert configuration | Appropriate monitoring read actions at the target resource |
| Log Analytics | Workspace or resource context log access; central destinations can be in another subscription |
| Cost and budgets | Applicable Cost Management or billing scope access; billing scopes and Azure resource scopes differ |
| Key Vault credential metadata | Data plane metadata permissions, such as Key Vault Reader under Azure RBAC, or the applicable list access policy; never read secret values |
| Microsoft Graph directory objects | Separate approved directory permissions; sign-in reports require their own permissions, licensing and retained data |
| Backup, Service Health and Resource Health | Applicable provider read permissions and product specific scope |
| Policy state | Policy Insights read/query actions; remediation creation is a separate write |

Denied access is `Not assessed`, never zero findings, compliant, healthy or safe to delete. Request only the missing permission with a stated purpose and expiry. The skill does not grant roles, activate PIM or authorize its own elevation.

## Identity for Python tools

Use the agent's intended managed identity, explicitly configured by the operator. Set `AZURE_CLIENT_ID` to the approved user assigned identity client ID when applicable. The shared identity helper documents its supported modes; local developer authentication must be an explicit choice, not fallback after a production error.

Never select the first of several attached identities, persist credentials, or log access tokens. Validate identity and scope with a known permitted resource and a known excluded scope before production use.

## Writes and delivery

The default workflow collects evidence and creates local drafts. Resource moves, renewal, policy remediation, rollback, scheduling, support tickets, deployment and external uploads need separate explicit approval for the exact payload and destination. If the host lacks an approved write tool, provide the draft to an authorized operator instead.

## Sources

- [Azure SRE Agent permissions](https://learn.microsoft.com/azure/sre-agent/permissions).
- [Azure SRE Agent skills and attached tools](https://learn.microsoft.com/azure/sre-agent/skills).
- [Managed identity authentication for Python](https://learn.microsoft.com/azure/developer/python/sdk/authentication/system-assigned-managed-identity).
- [Azure Monitor diagnostic destinations](https://learn.microsoft.com/azure/azure-monitor/essentials/diagnostic-settings).

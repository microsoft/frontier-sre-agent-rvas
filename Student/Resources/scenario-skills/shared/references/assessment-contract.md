# Assessment contract

## Establish the evidence boundary

Record approved tenant, subscriptions, resource groups, resource IDs, identity, start and end timestamps in UTC, collection time, expected resource count, actual count and service specific prerequisites. Do not infer approval from the identity's permissions. A Resource Graph response can be successful but incomplete for the intended estate.

## Required states

| State | Meaning |
| --- | --- |
| Observed | Evidence supports this observation within the recorded scope and window |
| Needs attention | Evidence supports a control gap or a candidate needing owner review |
| Not applicable | Evidence shows the check does not apply; include the reason |
| Not assessed | Missing permission, unavailable data, unsupported API, missing input, insufficient history or failed collection |

The overall assessment is `Complete` only when every required in-scope check was evaluated. It is `Partial` when some evidence is available but required checks remain unassessed, and `Not assessed` when no sufficient evidence was collected. Completeness does not mean compliance or a healthy workload.

Never convert unavailable values to zero, false, Disabled, 100% compliant or GO. Empty inventory is not proof of a clean environment. Keep unassessed resources in the output. A readiness approval requires complete required evidence as well as acceptable findings.

## Collection

- Use explicit scope parameters on every supported command.
- Process continuation tokens and next links. Record any limit, truncated page or time window mismatch.
- Respect server Retry-After and use bounded retries for throttling and transient failures. Do not retry authorization failures as if they were transient.
- Do not follow continuation links to an unexpected host. Never forward authorization headers to a new audience.
- Define a maximum call/page budget before starting. Stop and mark the result partial when it is reached.
- Distinguish configuration posture, observed runtime behavior, inferred risk and a tested recovery outcome.
- Separate user response from monitor condition, management plane activity from data plane access, and platform metrics from diagnostic log export.

## Findings and recommendations

Each finding needs a stable identifier, full private evidence reference, observation time, assessment state, severity rationale, affected scope, evidence, recommended action, owner to confirm and limitations. Customer exports may replace identifiers with aliases while private evidence remains access controlled.

Thresholds and weights are organizational choices unless linked to a specific current Microsoft requirement. A custom posture score is not a Microsoft certification or a complete Well-Architected Review. Lifecycle and SKU claims need current, regional and support-plan-aware sources; unknown support status is not supported status.

## Validation levels

1. Library validation: structure, links, tool allowlist, output contracts, fixtures and packaging.
2. Local regression tests: deterministic classification, error states and report rendering.
3. Customer smoke test: authorized identity, documented commands, API availability, paging and one known example of each required state.
4. Operational validation: workload objectives, owners and any restore, failover or change test evidence.

Do not label levels 1 or 2 as live Azure validation. Scheduling and event triggers remain proposals until explicitly configured and verified.

## Sources

- [SRE Agent skills](https://learn.microsoft.com/azure/sre-agent/skills).
- [Azure Well-Architected Framework](https://learn.microsoft.com/azure/well-architected/what-is-well-architected-framework).
- [Azure Monitor alert states](https://learn.microsoft.com/azure/azure-monitor/alerts/alerts-overview).

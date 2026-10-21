# Operational workflows: evidence contract

These six workflows analyze existing evidence locally. They do not connect to Azure, invoke a model, run a restore, change a workload or authorize customer delivery.

The read commands in each workflow are templates for separately authorized collection. Each skill includes a synthetic `references/evidence-example.json`. The fixture is not customer evidence and its thresholds are not Microsoft defaults.

## Running the local analyzer

Run from a deployed skill root or an equivalent bundle containing the shared tools and references:

```powershell
python tools/operational_analysis.py `
  --scenario slo-error-budget-analysis `
  --input '<approved-normalized-evidence.json>' `
  --contract references/output-contract.json `
  --output '<new-private-result.json>' `
  --sharing-output '<new-sharing-draft.json>'
```

The source tree keeps the implementation under the shared tools directory. The deployment packager puts it beside the skill tools. Output files must be distinct and must not already exist. No dependency installation or cloud authentication is required for this local analysis.

The private result is validated before writing. The optional sharing copy uses the existing sanitization policy and requires human review. Its aliased identifiers intentionally do not satisfy the private GUID evidence contract. Do not overwrite private evidence with the sharing copy.

Scenario result JSON is not the HTML renderer's presentation schema. Prepare a separate report data object before using the shared HTML renderer. Never pass incompatible JSON and describe the resulting empty table as a complete report.

## Common input fields

| Field | Required evidence |
| --- | --- |
| `schema_version` | Integer `1`. |
| `scope.subscription_ids` | Explicit nonempty approved subscription GUID allowlist. |
| `resource_ids` | Nonempty list of exact approved Azure resource IDs belonging to those subscriptions. |
| `window_start`, `window_end` | Positive closed observation window, ISO UTC with seconds and `Z` or `+00:00`. |
| `collected_at` | UTC collection time at or after the observation end. |
| `evidence` | Nonempty list of source references and UTC `collected_at` values, no later than the input collection time. Keep the actual raw source privately. |
| `collection_complete` | Explicit boolean. False prevents Complete even if the observed subset meets thresholds. |
| `collection_truncated` | Explicit boolean, separate from denied or missing evidence. True requires incomplete collection and an explanation. |
| `collection_limitations` | List of reasons for denied reads, incomplete lists, missing intervals, caps or partial coverage. Required and nonempty when collection is incomplete. |
| `data` | Normalized scenario observations, not an unmodified Azure CLI response. |
| `thresholds` | Explicit customer approved criteria. Numbers must be finite; counts must be nonnegative integers. |

Do not copy synthetic completeness flags into a real assessment. Verify identity, context, source resource IDs, observation window, API result shape, continuation handling and telemetry coverage before normalization. Reject placeholders. Raw logs, pod specifications and evaluation artifacts can contain confidential information.

Missing required observations produce a visible Not assessed result with reasons. Invalid types, negative counts, impossible count relationships, reversed times or out of scope resources fail explicitly instead of producing a report. Complete means the defined local assessment was fully supplied, not that a cloud action succeeded or the whole workload is healthy.

## Scenario fields and algorithms

### SLO and error budget

- Data: `total_events`, `good_events`, `unknown_events`.
- Threshold: `slo_target`, strictly between zero and one.
- Require positive total and no unclassified success observations. SLI is good divided by total.
- Allowed bad events are total times `(1 - target)`. Remaining budget is allowed minus observed bad events. Keep a negative remainder.
- This is an event based budget for one observation window. It is not a time based SLA or a multiple window burn rate.
- Use verified sampling weights where applicable. A percentile or counter derived from sampled telemetry still requires an instrumentation and capture assessment.

### Backup restore validation

- Data: boolean `restore_completed`, `isolated_target`, `integrity_passed`; completed drills additionally require `recovery_started_at`, `application_ready_at`, `loss_reference_at`, `recovered_through_at`.
- Thresholds: `rto_seconds`, `rpo_seconds`.
- Measured RTO is application ready minus the agreed recovery start. Measured RPO is the simulated loss reference minus the latest verified recovered committed write.
- State whether detection and authorization time are included. A backup timestamp or platform job status does not prove application readiness or data integrity.
- A known failed restore is Needs attention, with unavailable measured times explicitly explained. No restore is initiated here.

### Release regression

- Data: boolean `comparable_cohorts`; `baseline` and `current`, each with `requests`, `failed_requests`, `p95_latency_ms`.
- Thresholds: `minimum_requests`, `max_error_increase_percentage_points`, `max_latency_increase_percent`.
- Compare per cohort error rates. Error increase is in percentage points; latency growth is a relative percentage against a positive baseline.
- Require comparable duration, workload mix, sampling and metric definitions. Do not average percentiles or mix unmapped application versions.
- The output is a review recommendation. It is not statistical significance, causal proof, promotion authorization or rollback execution.

### AKS application triage

- Data: `pods`, a nonempty array with unique `uid`, `name`, `phase`, boolean `ready`, `waiting_reason`, `restart_delta`, `recent_oom_kills`.
- Threshold: integer `restart_threshold`.
- Use only the approved namespace and verified cluster context. Aggregate all relevant containers and init containers, not just the first status.
- Match pod UID and container identity across snapshots. A replaced pod or missing baseline does not have an observed zero restart delta. Historical OOM state without a timestamp in the window is not a recent OOM.
- Phase, readiness, waiting reasons, OOM observations and restart threshold breaches are symptoms. Successful completed jobs are not unhealthy merely because they are not ready.

### Service Bus queue delivery

- Data: `active_start`, `active_end`, `sample_duration_seconds`, `dead_letter_count`, `transfer_dead_letter_count`, `completed_messages`.
- Thresholds: `max_backlog_growth_per_minute`, `max_dead_letter_count`, `max_transfer_dead_letter_count`, `minimum_completed_messages`.
- Backlog growth per minute is `(active_end - active_start) * 60 / seconds`. The supplied duration must equal the common observation window. Completion counts must cover the same entity and interval.
- Read the namespace `CompleteMessage` metric with `Total` aggregation and the exact queue's `EntityName` filter after verifying live definitions. Outgoing deliveries are not completed settlement.
- Zero completions are not an incident for an idle queue with no backlog. Missing completion telemetry is not zero.
- Reason metadata, consumer behavior and business processing evidence are separate checks. Message content access, receive, settlement, replay and purge are not performed.

### AI inference investigation

- Data: boolean `comparable_cohorts`; `requests`, `failed_requests`, `throttled_requests`, `p95_latency_ms`, `latency_definition`, `tokens_total`, `evaluated_cases`, `quality_passed_cases`.
- Thresholds: `minimum_requests`, `minimum_evaluated_cases`, `max_failure_rate`, `max_throttle_rate`, `max_p95_latency_ms`, `minimum_quality_pass_rate`.
- Count throttled requests as a subset of failed requests, not additional requests. Ratios use the appropriate request or evaluation denominator.
- Supported latency definitions are `end_to_end_nonstreaming` and `time_to_first_token`. Each result uses one compatible cohort and metric definition.
- The caller supplies a real request level percentile and existing quality evaluation results. No metric average is relabeled as p95. Missing quality evidence prevents a complete combined assessment.
- Thresholds belong to the customer. Tokens are usage, not a retail price or billed cost, and output quality depends on the dataset and rubric.

## Approval and sharing

Use [the scope rules](./permissions-and-scope.md), [assessment states](./assessment-contract.md) and [customer sharing checklist](./customer-sharing.md). Tool authorization remains a host responsibility; a terminal tool and a Markdown instruction are not a read only security boundary.

Restore, replay, load tests, fault injection, Kubernetes mutations, model invocation, evaluation jobs, release changes, scheduling, uploads and messages all require separate explicit approval. This library performs none of those operations during local validation.

## Verified Microsoft guidance

The following claims were checked against official documentation on 2026-10-21. The algorithms and customer thresholds are library implementation choices, not Microsoft mandated numeric thresholds.

| Claim | Status | Source |
| --- | --- | --- |
| AppRequests includes success, application version, duration and represented sample item count. | Verified | [AppRequests](https://learn.microsoft.com/azure/azure-monitor/reference/tables/apprequests) |
| Recovery tests should measure full flow outcomes and verify integrity in isolation. | Verified | [Reliability testing](https://learn.microsoft.com/azure/well-architected/reliability/reliability-test) |
| Safe releases use progressive exposure and health gates. | Verified | [Safe deployments](https://learn.microsoft.com/azure/well-architected/operational-excellence/safe-deployments) |
| A pod crash loop is a symptom requiring targeted state and log investigation. | Verified | [AKS crash loop troubleshooting](https://learn.microsoft.com/troubleshoot/azure/azure-kubernetes/create-upgrade-delete/pod-stuck-crashloopbackoff-mode) |
| Service Bus delivery semantics and duplicate processing require explicit recovery handling. | Verified | [Message loss and duplicates](https://learn.microsoft.com/azure/service-bus-messaging/service-bus-message-loss-and-duplicates) |
| The Service Bus completion metric is `CompleteMessage`, with Total aggregation and an EntityName dimension. | Verified | [Service Bus monitoring reference](https://learn.microsoft.com/azure/service-bus-messaging/monitor-service-bus-reference) |
| AI operations should assess quality as well as component availability. | Verified | [AI operations](https://learn.microsoft.com/azure/well-architected/ai/operations) |

## Sources

- [Azure Backup recovery point commands](https://learn.microsoft.com/cli/azure/backup/recoverypoint?view=azure-cli-latest).
- [Azure Backup job commands](https://learn.microsoft.com/cli/azure/backup/job?view=azure-cli-latest).
- [Service Bus dead letter queues](https://learn.microsoft.com/azure/service-bus-messaging/service-bus-dead-letter-queues).
- [Azure OpenAI monitoring reference](https://learn.microsoft.com/azure/foundry/openai/monitor-openai-reference).
- [Azure OpenAI latency definitions](https://learn.microsoft.com/azure/foundry/openai/how-to/latency).

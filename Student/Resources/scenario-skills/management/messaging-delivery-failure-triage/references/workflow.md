# Evidence collection and analysis

## Collection

### 1. Read queue configuration and count snapshots

Repeat at the approved observation end. Read countDetails.activeMessageCount, deadLetterMessageCount and transferDeadLetterMessageCount where returned. Capture UTC collection times. Preserve absent counters as unknown rather than0 and distinguish queue state, forwarding, lock, delivery count and TTL settings.

```powershell
az servicebus queue show --subscription $SUB --resource-group $RG --namespace-name $NAMESPACE --name $QUEUE --output json
```

### 2. Discover namespace metric capabilities for the exact queue

Service Bus platform metrics are exposed on the namespace. Confirm the CompleteMessage counter, Total aggregation and EntityName dimension before selecting the exact queue. Never compare namespace totals with one queue. If the completion metric is unavailable, use an approved application completion counter export.

```powershell
az monitor metrics list-definitions --subscription $SUB --resource $NAMESPACE_ID --output json
```

### 3. Read approved completion telemetry

Run only after verifying the metric definition and exact queue dimension in the approved namespace. Sum only nonoverlapping bins for the same entity and window. CompleteMessage measures completed settlement; outgoing deliveries alone are not successful settlement. Missing metrics are not zero completions.

```powershell
az monitor metrics list --subscription $SUB --resource $NAMESPACE_ID --metrics CompleteMessage --start-time $START --end-time $END --interval PT1M --aggregation Total --filter "EntityName eq '$QUEUE'" --output json
```

### 4. Assess queue growth and delivery evidence locally

Use [the normalization contract](../../../shared/references/operational-evidence.md) and [synthetic queue fixture](./evidence-example.json). Review separately supplied reason metadata without exposing message bodies. The analyzer never connects to AMQP or settles, purges or resubmits messages.

```powershell
python tools/operational_analysis.py --scenario messaging-delivery-failure-triage --input $INPUT --contract references/output-contract.json --output messaging-private-result.json --sharing-output messaging-sharing-draft.json
```

## Analysis rules

1. Compute active backlog growth per minute as (end depth minus start depth) times60 divided by the actual observed interval seconds. Queue depth is a stock and cannot be added to completed message flow.
2. Compare active growth, dead letter count, transfer dead letter count and completion evidence against customer thresholds. An idle queue with no backlog does not require a positive completion count.
3. Correlate delivery failures with separately observed lock loss, delivery limit, TTL, filtering and forwarding evidence. Counts alone do not identify the reason or prove messages were lost.
4. Distinguish source transfer dead letter subqueues from destination entity failures. Missing completion data or missing counters prevents a complete local assessment.
5. Prepare a recovery proposal that addresses idempotency, duplicate processing, ordering, business reconciliation, canary replay, validation and stop conditions. Never purge or replay automatically.

## Known limits

- Queue metadata and platform counters do not prove business processing success, identify every failure reason or reveal message age distribution.
- This adapter does not implement Event Hubs consumer lag, Kafka offsets or topic subscription normalization. Replay and message content inspection are outside the default workflow.

## Expected validation cases

- Healthy: backlog falls from100 to20 in600 seconds, no dead letter stock and observed completions meet the approved thresholds.
- Finding: growing backlog, zero completions while backlog exists, or dead letter count above threshold produces Needs attention.
- Missing: absent countDetails, denied entity access or missing completion telemetry cannot be interpreted as zero backlog or zero failures.

## Sources

- [Namespace CompleteMessage counter and EntityName dimension](https://learn.microsoft.com/azure/service-bus-messaging/monitor-service-bus-reference) (consulted 2026-10-21).
- [Service Bus dead letter reasons and subqueue behavior](https://learn.microsoft.com/azure/service-bus-messaging/service-bus-dead-letter-queues) (consulted 2026-10-21).
- [Delivery semantics, source transfer queues and idempotent recovery](https://learn.microsoft.com/azure/service-bus-messaging/service-bus-message-loss-and-duplicates) (consulted 2026-10-21).

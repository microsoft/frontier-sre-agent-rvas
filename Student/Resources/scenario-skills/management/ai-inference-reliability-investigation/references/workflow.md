# Evidence collection and analysis

## Collection

### 1. Discover live inference metric names and dimensions

Discover names, valid aggregations and deployment/status dimensions rather than hardcoding an old API shape. Record public Azure versus other cloud endpoints and service applicability. Do not call key listing or inference APIs.

```powershell
az monitor metrics list-definitions --subscription $SUB --resource $AI_ID --output json
```

### 2. Read scoped request and token counters

The filter must select the approved deployment and retain supported status dimensions needed to count429 and failed requests. Do not sum overlapping aggregate and split time series, different retry layers or separate models. Confirm token metric meaning before combining prompt and completion totals. Missing series are unknown.

```powershell
az monitor metrics list --subscription $SUB --resource $AI_ID --metrics $REQUEST_METRIC --start-time $START --end-time $END --interval PT1M --aggregation Total --filter $DEPLOYMENT_FILTER --output json
az monitor metrics list --subscription $SUB --resource $AI_ID --metrics $TOKEN_METRIC --start-time $START --end-time $END --interval PT1M --aggregation Total --filter $DEPLOYMENT_FILTER --output json
```

### 3. Read approved request level client latency evidence

$LATENCY_KQL is a required operator reviewed query, restricted to the approved application/deployment and UTC interval, that returns the defined latency percentile without prompt or completion bodies. Do not compute p95 by averaging platform Average or percentile bins. Keep nonstreaming end to end latency separate from streaming time to first token.

```powershell
az monitor log-analytics query --subscription $SUB --workspace $WORKSPACE --analytics-query $LATENCY_KQL --timespan "$START/$END" --output json
```

### 4. Analyze inference and existing evaluation evidence locally

Use [input definitions](../../../shared/references/operational-evidence.md) and [the synthetic inference fixture](./evidence-example.json). Join only comparable model/deployment/API/streaming populations and evaluation versions. The local tool does not call Foundry, create an evaluation job or claim a model specific SLA.

```powershell
python tools/operational_analysis.py --scenario ai-inference-reliability-investigation --input $INPUT --contract references/output-contract.json --output ai-private-result.json --sharing-output ai-sharing-draft.json
```

## Analysis rules

1. Require explicit cohort comparability, positive request and quality evaluation denominators, and customer approved minimum samples. Missing quality evidence prevents a complete combined inference assessment.
2. Calculate failed requests / total requests and throttled requests / total requests separately. Throttled requests are a subset of failed requests in this contract and must not be added twice.
3. Compare a correctly measured p95 against a customer threshold for one latency definition. Streaming time to first token and nonstreaming end to end duration are not interchangeable.
4. Calculate quality pass rate from the existing approved dataset and rubric. Distinguish model or prompt quality issues from transport errors, capacity symptoms and application retry effects.
5. Report token totals as observed usage, not billed cost. Recommend additional evidence or a controlled change proposal; model switching, quota requests, retry changes, evaluation runs and scaling require separate approval.

## Known limits

- Quality is specific to the approved evaluation dataset, rubric and model/prompt version. A transport success is not proof of a useful or correct answer.
- Request, token and latency definitions vary by API, streaming mode and retry layer. Platform aggregates alone cannot supply every client percentile or a valid quality score.

## Expected validation cases

- Healthy: sufficient comparable requests and evaluation cases meet every customer configured availability, throttle, latency and quality threshold.
- Finding: failure rate, throttle rate, p95 or quality breach produces separately named signals and Needs attention.
- Missing: no evaluation cases, absent metric dimensions, incompatible streaming modes or insufficient samples is Not assessed, not a healthy model.

## Sources

- [Azure OpenAI monitoring metrics and dimensions](https://learn.microsoft.com/azure/foundry/openai/monitor-openai-reference) (consulted 2026-10-21).
- [Inference latency and throughput definitions](https://learn.microsoft.com/azure/foundry/openai/how-to/latency) (consulted 2026-10-21).
- [AI availability, quality monitoring and human oversight](https://learn.microsoft.com/azure/well-architected/ai/operations) (consulted 2026-10-21).

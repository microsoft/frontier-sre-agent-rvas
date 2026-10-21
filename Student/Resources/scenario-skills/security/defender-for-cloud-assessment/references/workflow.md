# Evidence collection and analysis

## Collection

### 1. Read current score and assessment evidence

Capture full responses with collection time per subscription. Retain metadata, status, recommendation key and assessed resource ID. Process continuation links if exposed; on 429 obey Retry-After with bounded exponential backoff, and record incomplete subscriptions rather than treating them as empty.

```powershell
foreach ($SUB in $SUBS) {
  az security secure-scores list --subscription $SUB --output json
  az security assessment list --subscription $SUB --output json
}
```

### 2. Compare retained history without creating exports

Stage only approved snapshots in approved-snapshots. Snapshot envelope keys are local contract fields, not Azure API fields. Join by subscription and recommendation key plus resource ID. If using an existing workspace instead, inspect its schema with az monitor log-analytics workspace get-schema before querying SecurityRecommendation or SecureScores; do not assume those tables exist. Historical ingestion is not backfilled by enabling export now.

```python
import json
from pathlib import Path
from datetime import datetime, timezone, timedelta
snapshots = [json.loads(p.read_text(encoding='utf-8')) for p in Path('approved-snapshots').glob('*.json')]
for s in sorted(snapshots, key=lambda s: s['collected_at']):
    print(json.dumps({'subscription_id':s['subscription_id'], 'collected_at':s['collected_at'], 'secure_scores':s.get('secure_scores'), 'assessments':s.get('assessments')}))
```

## Analysis rules

1. Report current score by initiative and subscription, preserving its maximum and percentage. Do not average subscription percentages without an explicit weighting rule.
2. Group Unhealthy assessed resources by metadata severity; count distinct resource IDs per recommendation, then rank the top ten by impacted count. Missing severity is unknown, not Low.
3. Compute 30 day trend only from comparable retained samples. Mark seven day additions as first observed since a complete earlier snapshot, not as proof of creation. Without earlier evidence, both trend and new recommendation count are null.
4. Prioritize known exploitability evidence and approved dependency or exposure inventory. Distinguish recommendation severity from confirmed exploitability and actual workload blast radius.

## Known limits

- Current assessment listing is not a 30 day history API.
- Continuous export coverage and retention can be incomplete; absence of a recommendation from a failed snapshot is not remediation.

## Expected validation cases

- Healthy: complete snapshots show stable score and no unhealthy resources.
- Finding: ten distinct resources share a High recommendation, which ranks ahead of a recommendation affecting two.
- Denied or missing: secure score succeeds but assessments are denied, so recommendation counts and trends remain null and assessment is Partial.

## Sources

- [Azure CLI security assessments](https://learn.microsoft.com/en-us/cli/azure/security/assessment?view=azure-cli-latest) (consulted 2026-10-21).
- [Azure CLI secure scores](https://learn.microsoft.com/en-us/cli/azure/security/secure-scores?view=azure-cli-latest) (consulted 2026-10-21).
- [Defender continuous export](https://learn.microsoft.com/en-us/azure/defender-for-cloud/continuous-export) (consulted 2026-10-21).

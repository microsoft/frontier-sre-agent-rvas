# Evidence collection and analysis

## Collection

### 1. Read complete operation lifecycle evidence

Partition the interval when max-events is reached and deduplicate by eventDataId. Preserve operationId and correlationId for logical request grouping; retry throttling with Retry-After. Keep raw counts and completeness manifest.

```powershell
az monitor activity-log list --subscription $SUB --start-time $START --end-time $END --max-events 10000 --output json
```

### 2. Normalize write and delete summaries locally

Stage complete read responses as one local activity-events.json array. Apply only the explicitly approved diagnostic operation exclusion list before aggregation and report removed counts. Code uses documented Activity Log fields and does not execute event content.

```python
import json,collections
from pathlib import Path
rows=json.loads(Path('activity-events.json').read_text(encoding='utf-8'))
unique={r['eventDataId']:r for r in rows}
requests={}
for r in unique.values():
    op=r.get('operationName',{}).get('value','').lower()
    if not op.endswith(('/write','/delete')): continue
    key=(r.get('operationId') or r['eventDataId'],r.get('resourceId','').lower(),op)
    requests.setdefault(key,[]).append(r)
out=collections.defaultdict(lambda:{'operations':0,'failed':0,'pending':0})
for events in requests.values():
    events.sort(key=lambda x:x['eventTimestamp']); final=events[-1]
    t=final.get('resourceType',{}).get('value') or 'Unknown'; s=final.get('status',{}).get('value','Unknown')
    out[t]['operations']+=1; out[t]['failed']+=s.lower()=='failed'; out[t]['pending']+=s.lower() not in ('succeeded','failed','canceled','cancelled')
print(json.dumps(dict(out),indent=2))
```

## Analysis rules

1. Use operationName.value rather than localized display name to classify suffix /write and /delete. Exclude read operations and disclose the exact diagnostic exclusion list.
2. Deduplicate pages by eventDataId, then reconcile lifecycle entries by operationId plus resource and operation. Retain both event count and logical operation count.
3. Group by recorded resourceType.value and include Unknown instead of discarding missing types. List failed operation errors with correlation IDs after redaction.
4. An operation without a terminal status by END remains pending or unknown, not succeeded. Management operations do not cover database queries or secret reads.

## Known limits

- Control plane operation history excludes most data plane actions.
- Incomplete lifecycle records or service retention can limit exact request counts.

## Expected validation cases

- Healthy: Started and Succeeded entries for one operation count as one successful request.
- Finding: terminal Failed delete is listed once under the recorded resource type.
- Denied or missing: capped time segment is reported Partial and totals are lower bounds, not complete counts.

## Sources

- [Activity Log management operation scope and retrieval](https://learn.microsoft.com/en-us/azure/azure-monitor/fundamentals/activity-log) (consulted 2026-10-21).

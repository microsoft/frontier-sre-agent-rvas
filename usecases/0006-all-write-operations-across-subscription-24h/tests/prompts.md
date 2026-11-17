# Test prompts

In a new chat, type `/agent`, select `change-digest-reviewer` and send one prompt at a time. Before the tool is configured, every prompt returns a configuration message and makes no Azure call.

## 1. Daily digest

```text
Run the daily relevant Azure changes digest for the last 24 hours and give me the report.
```

Tool call:

```json
{"operation": "report", "period": "last_24h"}
```

**Expected:** One report call. The answer gives the links to the HTML report, the JSON snapshot and the two CSVs first, then the headline, the high and medium changes, deletes, security-relevant changes, new role assignments, Activity Log gap events, unusual activity and the coverage.

## 2. Exposure

```text
Was anything opened to the Internet in the last 24 hours?
```

Tool call:

```json
{"operation": "query", "period": "last_24h", "view": "security"}
```

**Expected:** Only the security-relevant changes, each with the actor, the client, the time and the old and new values; no file is written.

## 3. Deletes this week

```text
Who deleted resources this week?
```

Tool call:

```json
{"operation": "query", "period": "last_7d", "view": "deletes"}
```

**Expected:** The deletes with their real caller; when Change Analysis recorded System, the caller recovered from the Activity Log is shown with that evidence.

## 4. One resource group

```text
What changed in rg-app-prod-weu in the last 14 days?
```

Tool call:

```json
{"operation": "query", "period": "last_14d", "view": "relevant", "resource_group": "rg-app-prod-weu"}
```

**Expected:** The relevant changes of that resource group only, within the 14-day Change Analysis retention.

## 5. Noise and coverage

```text
How much noise was filtered out today, and why? Is today's change data complete?
```

Tool call:

```json
{"operation": "query", "period": "last_24h", "view": "noise"}
```

**Expected:** Noise counted by reason, resource type and property path, and the coverage of each source; an incomplete source is stated, never hidden.

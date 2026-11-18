# Test prompts

In a new chat, type `/agent`, select `azure-backup-live` and send one prompt at a time. Before the tool is configured, every call returns a configuration error and makes no Azure call.

## 1. Report for the last 14 days

```text
Use azure-backup-live and only generate-azure-backup-report. Make exactly one call with period="last_14d" for the fixed approved vaults. Deliver HTML, complete source JSON, jobs CSV and items/coverage CSV using all four actual native links. Keep native failures, warnings, unfinished/cancelled jobs and other operations separate. State the returned UTC reference/window and requested versus verified history, source issues and unknown expected protection. Do not recollect, shorten the window, change Azure or create incidents.
```

Tool call:

```json
{"period": "last_14d"}
```

**Expected:** One call and four file links. Failed, warning, unfinished and unknown-state records stay separate for a human decision; expected protection stays Unknown, never guessed.

## 2. Last 24 hours

```text
Use azure-backup-live and only generate-azure-backup-report. Make exactly one call with period="last_24h" for the fixed approved Recovery Services vaults. Show the four actual files, native Backup failures/warnings and source/history blind spots without another call or changes. A human will decide whether an incident is needed.
```

Tool call:

```json
{"period": "last_24h"}
```

**Expected:** The same four files for a rolling 24-hour window (not "today UTC"), with no incident created.

## 3. Failed and warning records, from the same snapshot

```text
From this snapshot, which native Backup records were Failed or warning states? Distinguish list from later detail status and cite the full job/vault IDs, UTC dates and original error/task evidence. Separate Restore and other jobs.
```

**Expected:** No new tool call (the tool is report-only). The answer cites the records of the existing workpaper with their native evidence.

## 4. What the workpaper does not prove

```text
What does the workpaper actually establish about the requested interval and observed protected items? Identify inaccessible/partial sources, unknown history, unmatched/ambiguous full-ID associations and unevaluated schedules. Do not infer unprotected VMs, required jobs or missed backups from an empty list.
```

**Expected:** The coverage limits of the snapshot; no unprotected VM, required job or missed backup is inferred from an empty list.

# Test prompts

In a new chat, type `/agent`, select `patching-investigation-live` and send one prompt at a time. Before the tool is configured, every call returns a configuration error and makes no Azure call.

## 1. Full report for the last 30 days

```text
Generate the post-patching and failure investigation report for the last 30 days with operation=report and deliver the HTML, the snapshot JSON, the machines CSV and the patches CSV, then summarize the cycle and the failed machines with their most likely cause.
```

Tool call:

```json
{"operation": "report", "period": "last_30d"}
```

**Expected:** One report call and four file links. Each failed machine has one of the seven categories with its source evidence; nothing is installed, rebooted or rescheduled.

## 2. Failed machines only

```text
Use query with view=failures for the last 30 days. Which machines failed and why, with the evidence?
```

Tool call:

```json
{"operation": "query", "view": "failures", "period": "last_30d"}
```

**Expected:** Only failed machines with category and evidence, with exact totals and paging.

## 3. Unresponsive maintenance windows

```text
Use query with view=machines and failure_category=maintenance_window_unresponsive. Which machines did not respond in their maintenance window?
```

Tool call:

```json
{"operation": "query", "view": "machines", "failure_category": "maintenance_window_unresponsive"}
```

**Expected:** The machines in that category with their maintenance configuration and last run evidence.

## 4. Pending security patches without a schedule

```text
Use query with view=machines and failure_category=pending_security_patches_unscheduled. Which machines have pending security patches and no maintenance schedule?
```

Tool call:

```json
{"operation": "query", "view": "machines", "failure_category": "pending_security_patches_unscheduled"}
```

**Expected:** The machines with pending security patches and no schedule, from the latest assessment.

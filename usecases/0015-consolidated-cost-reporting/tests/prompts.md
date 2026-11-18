# Test prompts

In a new chat, type `/agent`, select `finops-reviewer` and send one prompt at a time. Before the tool is configured, every prompt returns a configuration message and makes no Azure call.

## 1. Monthly review

```text
Run the monthly Azure FinOps review and give me the report.
```

Tool call:

```json
{"operation": "report"}
```

**Expected:** One report call. The answer gives the links to the HTML report, the JSON snapshot and the three CSVs first, then the verdict, the headline numbers, the cost per project and the tag used, the prioritised actions with their monthly saving, the budgets at risk, the unusual days and jumps, the allocation readiness and the coverage.

## 2. Why it went up

```text
Why did our Azure cost go up last month?
```

Tool call:

```json
{"operation": "query", "view": "anomalies"}
```

**Expected:** The change by subscription, resource group, service and resource, with the unusual days and month-over-month jumps and their drivers; no file is written.

## 3. Savings

```text
Where can we save, and how much a month?
```

Tool call:

```json
{"operation": "query", "view": "savings"}
```

**Expected:** One savings figure in which every resource and every commitment option is counted once, with the source of each saving (Advisor, idle or orphaned resources, commitments).

## 4. One project

```text
What can the E-commerce web project save, and what should it do first?
```

Tool call:

```json
{"operation": "query", "view": "actions", "project": "E-commerce web"}
```

**Expected:** The actions and savings of that project only; the answer names the tag that identifies the projects.

## 5. Demo without Azure access

```text
Run a self-test of the FinOps review.
```

Tool call:

```json
{"operation": "self_test"}
```

**Expected:** A complete report from built-in SIMULATED data, clearly labelled, with no network call.

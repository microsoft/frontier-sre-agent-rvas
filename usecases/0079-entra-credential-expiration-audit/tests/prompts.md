# Test prompts

In a new chat, type `/agent`, select `credential-monitor-full` and send one prompt at a time. Before the tool is configured, every prompt returns a configuration message and makes no Azure call.

## 1. Full audit report

```text
Run the full Microsoft Entra credential expiration audit and deliver the HTML report with the coverage and risk summary.
```

Tool call:

```json
{}
```

**Expected:** One call to generate-entra-credential-expiration with no arguments. The answer links the HTML report through report_url, shows coverage complete with pagination_completed true, the applications and service principals scanned, the managed identities excluded and the counts by status, and says Action required when there are EXPIRED or CRITICAL credentials. It shows no secret, token or certificate content.

## 2. Coverage and next steps from the same thread

```text
Based on the audit result in this thread, summarize the coverage fields (reference_utc, pagination_completed, applications_scanned, service_principals_scanned, managed_identities_excluded, credential_rows), explain whether Action required applies, and list which status filters I should select in the downloaded HTML report to review immediate rotation priorities and unknown expiration dates.
```

**Expected:** No new tool call. The answer reads the returned coverage, explains Action required, and points to the Risk status filter and Export visible rows as CSV in the HTML report, without claiming a new Microsoft Graph query.

## 3. UTC calendar-date rule

```text
Explain why a credential expiring later today is classified as EXPIRED under this tool's UTC calendar-date rule, and how to export only EXPIRED and CRITICAL rows to CSV from the downloaded HTML report.
```

**Expected:** The answer explains daysRemaining = expiration date minus the UTC reference date (0 or less is EXPIRED) and the local filter plus CSV export, with no tool call.

## 4. Tool not configured yet

```text
Run the full Microsoft Entra credential expiration audit and deliver the HTML report with the coverage and risk summary.
```

Tool call:

```json
{}
```

**Expected:** Before MANAGED_IDENTITY_CLIENT_ID is set, the tool returns "Configuration required" with coverage partial, writes no report and makes no Graph call. The answer reports that state and invents no results.

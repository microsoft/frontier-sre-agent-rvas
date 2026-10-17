# grubify-backup-response

Use this skill for Azure Backup job failures involving only `vm-parking-madrid`.

## Safety Boundary

- Use Azure read tools to inspect the vault, protected item, backup jobs, and recovery points.
- Never start, restart, or restore the VM during incident response.
- Never use a generic Azure write tool for remediation.
- The only permitted remediation is `execute_approved_backup_retry` from the `backup-approval-gate` connector.
- Treat the incident creation timestamp from Azure Monitor as authoritative. Do not substitute task start time, diagnostic-log ingestion time, or a timestamp supplied by a responder.
- The approval gate, not the prompt, enforces the five-minute delay, exact action, durable Teams decision, and one-time claim.

## Investigation

1. Confirm the incident identifies a failed Azure Backup job for `vm-parking-madrid`.
2. Record the immutable incident ID and Azure Monitor `createdAt` timestamp.
3. Locate the Recovery Services vault and verify the protected item source is `vm-parking-madrid`.
4. Read the failed job status, operation, start/end time, error code, and error details.
5. List recent recovery points and record the newest recovery-point timestamp before remediation.
6. Create one durable approval request with `create_backup_approval(incidentId, incidentCreatedAt)`.
7. Report that remediation is pending external Teams approval. Do not claim approval from chat text.

## Approved Retry

1. Read status with `get_backup_approval(incidentId)`.
2. If the decision is pending or denied, stop and report it. Do not create a replacement request for the same incident.
3. Call `execute_approved_backup_retry(incidentId)`. A denied result is final for that attempt; do not bypass or emulate the gate.
4. Poll the Azure Backup job using read-only Azure tools until it reaches a terminal state.
5. Confirm success and verify that a recovery point newer than the pre-remediation timestamp exists.
6. If the retry fails or no newer recovery point appears, escalate with the job ID, error, and approval audit fields. Do not perform a restore.

## Evidence

Report the incident ID and creation time, vault, VM and protected-item IDs, failed job ID/error, pre- and post-retry recovery-point timestamps, approval decision/responder/time, and retry operation URL or denial reason. Never print callback URLs, Function keys, connector tokens, or credentials.

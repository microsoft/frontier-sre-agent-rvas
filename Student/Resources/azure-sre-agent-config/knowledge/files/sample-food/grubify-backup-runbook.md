# vm-parking-madrid Backup Runbook

## Protected Resource

One Recovery Services vault protects only the `vm-parking-madrid` Azure VM with a daily Azure IaaS VM policy and native Azure Monitor failed-job alerts. The VM may remain deallocated; backup protection does not require the response workflow to start it.

## Incident Contract

A backup-failure incident must retain its Azure Monitor incident ID and original creation timestamp. The backup specialist creates a durable approval request for the fixed `RetryBackup` action. A Logic App posts an adaptive card to the configured Teams channel and records the authenticated connector responder. The approval Function rejects pending, denied, malformed, early, action-mismatched, and replayed execution.

The five-minute scheduled task is orchestration, not the security boundary. The Function independently requires the current time to be at least five minutes after incident creation.

## Validation

Before retrying, record the latest recovery-point timestamp. After an approved retry, find the resulting Azure Backup job and wait for a terminal state. Success requires both a completed job and a recovery point newer than the timestamp captured before remediation.

Escalate if the retry job fails or no newer recovery point appears. Never start, restart, or restore the VM. A restore drill is a separate operation and requires separate explicit approval.

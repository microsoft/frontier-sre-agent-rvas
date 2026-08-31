[< Previous Solution](./Solution-12.md) | **[Home](./README.md)**

# Coach Guide — Challenge 13: Backup-to-Teams Resilience

## Purpose

- Demonstrate a complete backup-alert-to-Teams workflow grounded in live recovery and application evidence.
- Connect automated incident handling to approval, recovery guidance, post-recovery validation, and escalation.
- Expected time: 20–25 minutes.

## Mini-Lecture (5 min before challenge)

- Azure Backup built-in alerts are Azure Monitor alerts; SRE Agent routing and Teams posting are separate workflow stages.
- Backup success, restore success, and application health are different validation gates.
- RTO and RPO turn technical backup state into application impact.
- Keep recovery actions behind approval for this customer exercise.

## Expected Student Output

- Backup-failure alerts enabled for an existing protected workload.
- A response plan covering detect, investigate, classify, notify, approve, recover, validate, and escalate.
- A concise Teams post with live evidence and application impact.
- Recovery guidance containing application validation and escalation conditions.

## Coach Runbook

1. Verify vault alerting, protected-item state, SRE Agent incident routing, and Teams authorization before the exercise.
2. Prefer a genuine failed job; otherwise retain an `EXERCISE` label in the incident and every Teams message.
3. Require evidence, application impact, confidence, owner, next action, RTO/RPO status, and approval posture in the notification.
4. Treat restore completion as an intermediate event; close only after application, dependency, telemetry, and business validation.

## Common Issues and Hints

- **Symptom:** No real failed backup is available. **Fix:** use a clearly labeled exercise incident with live vault and application evidence; never fabricate a failed job.
- **Symptom:** Teams returns `400 Group ID does not exist`. **Fix:** list teams and channels through the connector and resolve the destination by display name.
- **Symptom:** The response plan cannot post. **Fix:** verify Teams connector authorization and grant its post-message tool to the selected agent.
- **Symptom:** The workflow stops after a successful restore. **Fix:** require application probes, dependency checks, telemetry, and business validation before closure.

## Debrief Discussion Guide

- Why is restore completion not incident resolution? → The application may still be unavailable, inconsistent, or disconnected from dependencies.
- What belongs behind approval? → Actions with data, availability, cost, compliance, or broad blast-radius impact.
- When should the workflow escalate? → RTO/RPO breach, no usable recovery point, failed validation, uncertain ownership, or repeated recovery failure.

## Success Criteria Notes

- **Require:** correct alert routing, safe notification, approval boundary, application validation, and explicit escalation conditions.
- **Reject:** fabricated failed jobs, leaked credentials/IDs, or closure based only on restore status.
- **Accept:** a genuine alert or clearly labeled exercise, and either Recovery Services vaults or Backup vaults.

## Solution

### Enable and route backup alerts

In the vault, open **Monitoring > Alerts**, confirm Azure Monitor backup alerts are enabled, and use **Configure notifications** at the intended scope. Confirm the SRE Agent Azure Monitor incident connection can ingest the alert.

### Configure the workflow

Create a response plan matching stable backup alert titles such as `Backup Failed` or `Backup Health`. Require these stages:

1. Read vault, protected-item, job, and recovery-point state.
2. Identify the dependent application and query its current health.
3. Apply owner, criticality, RTO, RPO, and escalation context from knowledge.
4. Classify the event as confirmed failure, assurance risk, or informational.
5. Post one concise Teams message with evidence, impact, confidence, and next action.
6. Request approval before any recovery or application change.
7. After an approved action, validate availability, dependencies, telemetry, and business function.
8. Resolve only after validation; otherwise escalate.

Authorize the Teams connector in the portal and grant its post-message tool to the response agent. Resolve the Team and channel by display name instead of storing IDs or credentials.

### Validate safely

Use a genuine alert when available. Otherwise, invoke the workflow with `EXERCISE - Backup assurance review`, require live evidence, and retain the `EXERCISE` label in Teams. Pending initial protection is an assurance risk, not a confirmed failed job.
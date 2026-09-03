[< Previous Solution](./Solution-08.md) | **[Home](./README.md)** | [Next Solution >](./Solution-10.md)

# Coach Guide — Challenge 09: Resolve a Backup Assurance Incident

## Purpose

- Simulate a backup assurance incident from alert through evidence, stakeholder communication, guarded recovery, application validation, and escalation.
- Teach students to distinguish confirmed backup failure, degraded assurance, restore completion, and actual service recovery.
- Expected time: 20–25 minutes.

## Mini-Lecture (5 min before challenge)

- The operational issue is recoverability risk; alert routing and Teams posting are supporting workflow stages.
- Backup success, restore success, and application health are different validation gates.
- RTO and RPO turn technical backup state into application impact.
- Keep recovery actions behind approval for this customer exercise.

## Expected Student Output

- Separate vault, protected-item, job, recovery-point, application-health, incident-wiring, and connector evidence.
- An honest classification of confirmed failure, assurance risk, or healthy/in-progress state.
- A concise review-ready Teams message with evidence and application impact.
- Proposal-only recovery guidance containing approval, validation, and escalation conditions.

## Coach Runbook

1. Verify the student inventories Recovery Services and Data Protection vaults separately before selecting a mode.
2. For live mode, provide exact approved vault and protected-workload identifiers; otherwise provide the labeled evidence pack.
3. Require backup evidence, application health, SRE Agent incident wiring, and Teams connector readiness as separate reads.
4. Review the message before any authorized connector use and reject unsupported delivery or failure claims.
5. Keep recovery proposal-only and treat restore completion as an intermediate event.

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

- **Require:** independently sourced evidence, correct classification, safe notification language, approval boundary, application validation, and explicit escalation conditions.
- **Reject:** fabricated failed jobs, leaked credentials/IDs, or closure based only on restore status.
- **Accept:** a genuine event or clearly labeled evidence-pack exercise, and either Recovery Services vaults or Backup vaults.

## Solution

### Verify mode and backup evidence

Require separate inventory commands for Recovery Services vaults and Data Protection Backup vaults. A listed vault alone does not establish live mode. Live mode also requires an approved protected lab workload and readable item, job, and recovery-point evidence.

For Recovery Services, check the exact student commands for `az backup item list`, `az backup job list`, and `az backup recoverypoint list`. For other supported workload types, provide the corresponding CLI evidence. Failed or unavailable reads are evidence gaps, not healthy protection.

### Correlate application and control-plane evidence

The two Grubify HTTP reads prove current availability only. Require the student to inspect the SRE Agent ARM incident configuration and data-plane connector inventory separately. Azure Monitor wiring does not prove that a Teams destination or post-message tool is ready.

Use the completed evidence table to require one of three classifications: confirmed failure, assurance risk, or healthy/in-progress. Pending initial protection and unavailable evidence must not be described as a confirmed failed backup.

### Review communication and recovery guidance

The rendered Teams draft must include severity, workload, observed application impact, latest job state, latest usable recovery point, RPO risk, confidence, recommended action, and link. Evidence-pack mode always stops at the draft. In live mode, accept a delivery claim only when destination resolution, authorization, tool invocation, and the resulting message are all observed.

The proposal-only agent response should cover:

1. Read vault, protected-item, job, and recovery-point state.
2. Identify the dependent application and query its current health.
3. Apply owner, criticality, RTO, RPO, and escalation context from knowledge.
4. Classify the event as confirmed failure, assurance risk, or informational.
5. Review one concise Teams message with evidence, impact, confidence, and next action.
6. Request approval before any recovery or application change.
7. After an approved action, validate availability, dependencies, telemetry, and business function.
8. Resolve only after validation; otherwise escalate.

Reject any write executed for demonstration convenience. Confirm the closure matrix distinguishes protection, recoverability, restore, application, dependency, telemetry, and communication proof, then confirm the process token is removed.
[< Previous Solution](./Solution-14.md) | **[Home](./README.md)** | [Next Solution >](./Solution-16.md)

# Coach Guide — Challenge 15: Autonomous Remediation

> **Application focus:** Parking Manager only

## Purpose

- Focus the class on the validation loop: a remediation is only complete when the agent proves it worked.
- This challenge compares autonomous MTTR against human-driven recovery.
- Expected time: 20–25 minutes.

## Mini-Lecture (3–5 min before challenge)

- State the pattern explicitly: detect → remediate → validate → retry or escalate.
- **Important:** `parking-api-service-down` matches only the Sev2 `Paris Parking API Service Down` alert and routes to `parking-vm-incident-handler` in Autonomous mode. If students don't see automatic routing, confirm the filter was applied under **Incident Response → Filters**.
- The trigger is `make trigger-parking-service-down`; it stops the real `paris-parking-api.service` and emits a deterministic systemd Syslog marker.
- Tell students what to watch for: `az vm restart`, power-state check, systemd and localhost API validation, closeout summary, and max-attempt behavior.
- Tie back to Challenge 06: response-plan settings, especially attempt limits, govern the loop.
- Remind students that Autonomous mode governs approval, not Azure authorization; the managed identity still needs VM restart and Run Command RBAC actions.

## Expected Student Output

- Student runs `make trigger-parking-service-down` and the incident is automatically routed to `parking-vm-incident-handler` via the `parking-api-service-down` filter (or manually invokes that subagent if automatic routing doesn't fire).
- The agent restarts `vm-parking-paris` and verifies the systemd service and API before closure.
- Student can explain what the validation query/check was and what happens on failure.
- Student understands the difference between basic remediation (Ch11/12) and validated remediation with retry logic (this challenge).
- No GitHub issue is created; Challenge 10 owns that separate reporting workflow.

## Common Issues and Hints

- **Symptom:** There is no known trigger script in the student repo. **Fix:** use `make trigger-parking-service-down` and the idempotent `make restore-parking-service` cleanup target.
- **Symptom:** Agent reports remediation complete with no proof. **Fix:** press for the validation step explicitly; this is the whole point of the lab.
- **Symptom:** Students conflate reboot success with service recovery. **Fix:** require both `systemctl is-active paris-parking-api.service` and a successful localhost API response.
- **Symptom:** They cannot find the exact response-plan YAML. **Fix:** inspect `Student/Resources/azure-sre-agent-config/automations/incident-filters/parking-api-service-down.yaml`, which was applied with `make incident-filters` in Challenge 06.
- **Symptom:** A GitHub issue is created instead of remediation. **Fix:** the Challenge 10 filter handled the alert; confirm both filters match exact alert titles and `parking-api-service-down` routes to `parking-vm-incident-handler`.
- **Symptom:** Agent correctly identifies the failing VM but `az vm restart` or Run Command validation is refused with an Azure authorization error. **Fix:** have an Owner or Role Based Access Control Administrator run `make grant-agent-vm-remediation`, verify `Azure SRE Lab VM Remediator` is assigned on `rg-sre-parking-paris`, wait for propagation, and retry in a new thread. The role grants no GitHub, network, disk, resize, or role-management permissions.

## Debrief Discussion Guide

- What is the difference between remediation and validated remediation? → Action taken vs action proven effective.
- Why can retry loops be useful and dangerous? → Good for transient issues, bad if the success signal is weak.
- Where does MTTR improvement come from here? → No handoff delay plus immediate verification.

## Success Criteria Notes

- Require the dedicated `parking-vm-incident-handler`; it is intentionally scoped to this workflow and has no GitHub tools.
- Be strict that students understand the validation logic and escalation path.
- If your tenant lacks the scenario, convert this into a guided coach demo rather than letting students stall.

[< Previous Solution](./Solution-14.md) | **[Home](./README.md)** | [Next Solution >](./Solution-16.md)

# Coach Guide — Challenge 15: Autonomous Remediation

## Purpose

- Focus the class on the validation loop: a remediation is only complete when the agent proves it worked.
- This challenge compares autonomous MTTR against human-driven recovery.
- Expected time: 20–25 minutes.

## Mini-Lecture (3–5 min before challenge)

- State the pattern explicitly: detect → remediate → validate → retry or escalate.
- **Important:** The incident filter bundle now includes `parking-vm-unhealthy` (Sev2, `titleContains: parking` → `iaas-vm-incident-handler`, Autonomous). If `make incident-filters` was run in Challenge 06, automatic routing should work here. If students don't see automatic routing, confirm the filter was applied: check **Incident Response → Filters** for `parking-vm-unhealthy`.
- The trigger script exists: `make trigger-parking-down` → `trigger-parking-api-down.sh`. Use it.
- Tell students what to watch for: `az vm restart`, health recheck, closeout summary, and max-attempt behavior.
- Tie back to Challenge 06: response-plan settings, especially attempt limits, govern the loop.

## Expected Student Output

- Student runs `make trigger-parking-down` and the incident is automatically routed to `iaas-vm-incident-handler` via the `parking-vm-unhealthy` filter (or manually via `/agent iaas-vm-incident-handler` if automatic routing doesn't fire).
- The agent restarts the affected VM and verifies health before closure.
- Student can explain what the validation query/check was and what happens on failure.
- Student understands the difference between basic remediation (Ch11/12) and validated remediation with retry logic (this challenge).

## Common Issues and Hints

- **Symptom:** There is no known trigger script in the student repo. **Fix:** this is incorrect — `make trigger-parking-down` (→ `trigger-parking-api-down.sh`) and `make restore-parking` exist. Use them.
- **Symptom:** Agent reports remediation complete with no proof. **Fix:** press for the validation step explicitly; this is the whole point of the lab.
- **Symptom:** Students conflate reboot success with service recovery. **Fix:** require a post-restart health check or telemetry confirmation.
- **Symptom:** They cannot find the exact response-plan YAML in the default config bundle. **Fix:** the `parking-vm-unhealthy` filter YAML is at `Student/Resources/azure-sre-agent-config/automations/incident-filters/parking-vm-unhealthy.yaml` — it was applied with `make incident-filters` in Challenge 06. Confirm it is listed under **Incident Response → Filters** in the portal.
- **Symptom:** Agent correctly identifies the failing VM but `az vm restart` is refused with a permission error. **Fix:** student set the agent permission to Reader in Challenge 00. In the SRE Agent portal → **Managed Resources**, change the permission to **Contributor** on the affected parking resource groups.

## Debrief Discussion Guide

- What is the difference between remediation and validated remediation? → Action taken vs action proven effective.
- Why can retry loops be useful and dangerous? → Good for transient issues, bad if the success signal is weak.
- Where does MTTR improvement come from here? → No handoff delay plus immediate verification.

## Success Criteria Notes

- Be flexible on the exact Parking Manager specialist name; environments may vary.
- Be strict that students understand the validation logic and escalation path.
- If your tenant lacks the scenario, convert this into a guided coach demo rather than letting students stall.

[< Previous Solution](./Solution-10.md) | **[Home](./README.md)** | [Next Solution >](./Solution-12.md)

# Coach Guide — Challenge 11: Guest OS Failure Investigation

## Purpose

- Demonstrate the difference between platform health and guest-OS service health.
- This challenge is the cleanest example of why Syslog and AMA matter: Azure sees a running VM while nginx is dead inside it.
- Expected time: 20–25 minutes.

## Mini-Lecture (3–5 min before challenge)

- Draw the failure chain: `trigger-nginx-down.sh` stops nginx on both `vm-vflta-web-1` and `vm-vflta-web-2` → load balancer `lb-vflta-internal-web` has no healthy backends → `alert-vflta-nginx-down` fires.
- Explain why both VMs are targeted: one failed backend is tolerated; two create a visible outage.
- Name the evidence and automation path exactly: `Syslog` table → `web-tier-nginx` filter → `iaas-vm-incident-handler` → `az vm run-command invoke`.
- Stress blast-radius validation: partial repair is not enough.

## Expected Student Output

- `alert-vflta-nginx-down` appears in Incident Response within roughly 2–3 minutes.
- Investigation log shows Syslog/systemd evidence for nginx stop events.
- Agent identifies both web VMs, restarts nginx on each, and verifies recovery.
- `make validate` returns healthy afterward.

## Common Issues and Hints

- **Symptom:** Alert does not appear after 5 minutes. **Fix:** trigger manual investigation with the load-balancer symptom prompt from the challenge.
- **Symptom:** Agent fixes only one VM. **Fix:** coach should push on blast radius and require verification for both `vm-vflta-web-1` and `vm-vflta-web-2`.
- **Symptom:** Student relies on VM power state as proof of health. **Fix:** redirect them to Syslog and nginx service state.
- **Symptom:** Service still down after automation. **Fix:** run `make restore-nginx` and use the failure as a debrief point about verification loops.
- **Symptom:** Agent correctly diagnoses the failure but `az vm run-command invoke` is refused with a permission error. **Fix:** student set the agent permission to Reader in Challenge 00. In the SRE Agent portal → **Managed Resources**, change the permission to **Contributor** on the affected resource groups (`rg-sre-spoke-web-api`).

## Debrief Discussion Guide

- Why can Azure show a VM as Running while users still see outage? → Platform state is not guest-process state.
- Why was Syslog the decisive signal here? → It exposes `systemd`/service failure inside the guest.
- What is the operational risk of stopping after the first healthy backend returns? → Silent partial failure.

## Success Criteria Notes

- Be strict on “both VMs” and post-remediation verification.
- Accept manual trigger if alert propagation is slow, but not a purely hypothetical discussion.
- If students can explain guest vs. platform visibility clearly, they met the conceptual goal even if portal timing is imperfect.

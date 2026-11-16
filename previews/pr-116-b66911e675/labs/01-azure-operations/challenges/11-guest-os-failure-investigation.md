---
title: Guest OS Failure Investigation
summary: Stop NGINX on the web-tier VMs. Watch the agent find the failure in Syslog, assess the blast radius across both VMs, and restore the service on every affected instance.
phase: Autonomous
group: Autonomous incident response
tags:
- AMA / Syslog
- VM run-command
- blast radius
highlight: false
---

# Challenge 11 — Guest OS Failure Investigation

> **Application focus:** Infrastructure/platform only

> **Capability**: Azure Monitor Agent · Syslog · VM troubleshooting · Blast radius validation

## Purpose

- Detect a stopped nginx service on a VM that the portal shows as Running, using Syslog and AMA, and cite the log evidence.
- Explain why platform health alone missed it.
- Expected time: 20–25 minutes.

## Introduction

A VM can show "Running" and "Healthy" in the portal while nginx is stopped. VM status alone does not establish application health.

Stop nginx on both web VMs. Check that the agent uses Syslog to identify both affected instances, restores the service, and verifies recovery on each VM.

## Description

### Before you start

Verify the Web IaaS web tier is serving traffic normally:

```bash
make validate
```

### Step 1 — Inject the fault

Stop nginx on both web VMs:

```bash
make trigger-nginx-down
```

This stops nginx on both `vm-web-1` and `vm-web-2`. The internal load balancer (`lb-internal-web`, frontend `10.20.2.100`) will stop serving requests as both backends fail the HTTP health probe.

> **Why both VMs?** Stopping one is not an outage: the load balancer keeps serving from the healthy instance. With both failing, it has no healthy backend.

### Step 2 — Wait for the alert

The Azure Monitor alert `alert-nginx-down` is configured on a 1-minute evaluation window. Within **2–3 minutes**, the alert should fire on Syslog messages referencing nginx `Stopped` / `Deactivated` / `Failed`.

Watch for it in the SRE Agent portal under **Incident Response**.

### Step 3 — Observe the autonomous investigation

The response plan `web-tier-nginx` routes the incident to `iaas-vm-incident-handler` in **Autonomous** mode. Watch the agent:

1. Query the Syslog table in Log Analytics to confirm the nginx failure
2. Identify which VMs are affected (both — full blast radius)
3. Restart nginx on each affected VM via `az vm run-command invoke`
4. Re-verify that nginx is active on every instance before closing the investigation

> If the alert hasn't fired after 5 minutes, trigger the investigation manually using the prompt below.

**Manual fallback prompt:**
```text
The internal load balancer frontend 10.20.2.100 stopped serving. Check the web tier, find the root cause in the guest-OS logs, and restore the service on every affected VM.
```

> **Tool approval required:** the platform classifies `az vm run-command invoke` as a write operation because it can run arbitrary scripts on a VM. The agent routes it through `RunAzCliWriteCommands`, which requires approval by default. To automate fully, add a Tool Access Policy Allow rule such as `RunAzCliWriteCommands(az vm run-command invoke *)` under **Capabilities → Tools -> Advanced permissions**. This permits any VM Run Command available to the agent.

> **If Azure returns an authorization error:** Autonomous mode removes the human approval gate, and the Tool Access Policy permits the tool call, but neither grants Azure RBAC permissions to the agent's managed identity. Ask an **Owner** or **Role Based Access Control Administrator** to run `make grant-agent-vm-remediation` from `labs/01-azure-operations/`. The script grants the agent only VM read, restart, and Run Command actions on resource groups that contain lab VMs. Wait several minutes for RBAC propagation, then retry the investigation in a new thread.

### Step 4 — Restore (if needed)

If the agent didn't fully restore the service:

```bash
make restore-nginx
```

### Step 5 — Review the investigation

Read the agent's full investigation log in the portal. Note:

- The Syslog query it used to detect the failure
- How it identified both VMs (not just the first one)
- The `az vm run-command invoke` calls for each instance
- The verification query confirming nginx is active after restart

## Success Criteria

- [ ] The `alert-nginx-down` alert fired and appeared in the SRE Agent portal
- [ ] The agent's log shows it queried the Syslog table for nginx systemd messages
- [ ] The agent identified **both** VMs as affected (blast radius correctly assessed)
- [ ] The agent ran `az vm run-command invoke` on each VM to restart nginx
- [ ] The agent verified nginx was active on every VM after restart
- [ ] You can distinguish Autonomous mode, Tool Access Policy approval, and Azure RBAC authorization
- [ ] `validate.sh` returns healthy after the agent's remediation
- [ ] **Explain in your own words** (two or three written sentences) — what is the difference between a platform-level health probe failure and a guest-OS failure? Why would a VM show "Running" in the portal while the service is down?

## Learning Resources

- [Azure Monitor Agent overview](https://learn.microsoft.com/en-us/azure/azure-monitor/agents/azure-monitor-agent-overview)
- [Azure Monitor — Syslog data collection](https://learn.microsoft.com/en-us/azure/azure-monitor/agents/data-collection-syslog)
- [Azure Load Balancer — health probes](https://learn.microsoft.com/en-us/azure/load-balancer/load-balancer-custom-probe-overview)
- [Azure VM — Run Command](https://learn.microsoft.com/en-us/azure/virtual-machines/run-command-overview)

## Tips

- The Syslog DCR (`dcr-web-syslog`) collects `daemon` facility logs from both VMs. The `Syslog` table in Log Analytics is the source of truth for guest-OS service failures.
- The `iaas-vm-incident-handler` subagent runs this challenge **without a custom skill** — it relies entirely on its system prompt and built-in tools. This is intentional: it shows that a well-written system prompt with clear instructions can drive correct behavior without a separate skill YAML.
- If only one VM's nginx is restarted, the load balancer will resume serving but the second VM remains broken — a silent partial failure. The agent is instructed to verify every instance, not just the first one.

## Hints and notes

> Hidden until you click. Expand a section only when you want it.

<details>
<summary><strong>Background</strong></summary>

- Failure chain: `trigger-nginx-down.sh` stops nginx on both `vm-web-1` and `vm-web-2` → load balancer `lb-internal-web` has no healthy backends → `alert-nginx-down` fires.
- Why both VMs: one failed backend is tolerated; two cause a visible outage.
- Evidence and automation path: `Syslog` table → `web-tier-nginx` filter → `iaas-vm-incident-handler` → `az vm run-command invoke`.
- Tool approval: see the note in Step 3. `RunAzCliWriteCommands` requires approval by default, and the Allow rule `RunAzCliWriteCommands(az vm run-command invoke *)` removes that prompt.
- Three separate controls: Autonomous mode removes the response-plan approval gate, Tool Access Policy permits `RunAzCliWriteCommands`, and Azure RBAC authorizes the managed identity against the VM resource.
- Validate the full blast radius: partial repair is not enough.

</details>

<details>
<summary><strong>Expected Output</strong></summary>

- `alert-nginx-down` appears in Incident Response within roughly 2–3 minutes.
- Investigation log shows Syslog/systemd evidence for nginx stop events.
- Agent identifies both web VMs, restarts nginx on each, and verifies recovery.
- The load balancer and both backend IPs return HTTP 200 afterward.

</details>

<details>
<summary><strong>Common Issues and Hints</strong></summary>

- **Symptom:** Alert does not appear after 5 minutes. **Fix:** trigger a manual investigation with the load-balancer symptom prompt from the challenge.
- **Symptom:** Agent fixes only one VM. **Fix:** check the blast radius and require verification for both `vm-web-1` and `vm-web-2`.
- **Symptom:** You rely on VM power state as proof of health. **Fix:** check Syslog and nginx service state.
- **Symptom:** Service still down after automation. **Fix:** run `make restore-nginx`. The failure shows why the agent must verify its fix.
- **Symptom:** Agent correctly diagnoses the failure but `az vm run-command invoke` is refused with an Azure authorization error. **Fix:** have an Owner or Role Based Access Control Administrator run `make grant-agent-vm-remediation`, verify `Azure SRE Lab VM Remediator` is assigned to the agent identity on the shared workload resource group, wait for RBAC propagation, and retry in a new thread. The grant is additive and does not replace existing roles.
- **Symptom:** The Allow rule appears correctly saved in the agent's configuration snapshot and has been present for about 10 minutes, but the command still requests approval. **Fix:** open a new thread and retry the investigation. An existing thread may retain the tool policy state from when it was created.

</details>

<details>
<summary><strong>Debrief Discussion Guide</strong></summary>

- Why can Azure show a VM as Running while users still see outage? → Platform state is not guest-process state.
- Why was Syslog the decisive signal here? → It exposes `systemd`/service failure inside the guest.
- What is the operational risk of stopping after the first healthy backend returns? → Silent partial failure.

</details>

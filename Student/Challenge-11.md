[< Previous Challenge](./Challenge-10.md) — **[Home](../README.md)** — [Next Challenge >](./Challenge-12.md)

# Challenge 11 — Guest OS Failure Investigation

> **Capability**: Azure Monitor Agent · Syslog · VM troubleshooting · Blast radius validation

## Introduction

Platform health checks only tell you what Azure can see. A VM can show "Running" and "Healthy" in the portal while the service inside it is completely stopped — because the platform doesn't know about nginx, systemd, or the application process.

In this challenge you'll inject a guest-OS failure that the platform cannot detect, watch the agent discover it from **Syslog telemetry**, correctly assess the full blast radius (both VMs, not just the first one found), and restore the service autonomously on every affected instance.

## Description

### Before you start

Verify the Grubify web tier is serving traffic normally:

```bash
make validate
```

### Step 1 — Inject the fault

Stop nginx on both web VMs:

```bash
make trigger-nginx-down
```

This stops nginx on both `vm-web-1` and `vm-web-2`. The internal load balancer (`lb-internal-web`, frontend `10.20.2.100`) will stop serving requests as both backends fail the HTTP health probe.

> **Why both VMs?** Stopping only one is not an outage — the load balancer keeps serving from the healthy instance. With all instances failing, the load balancer has no healthy backend to route to.

### Step 2 — Wait for the alert

The Azure Monitor alert `alert-nginx-down` is configured on a 1-minute evaluation window. Within **2–3 minutes**, the alert should fire based on Syslog messages referencing nginx `Stopped` / `Deactivated` / `Failed`.

Monitor in the SRE Agent portal under **Incident Response**.

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

### Step 4 — Restore (if needed)

If the agent did not fully restore the service:

```bash
make restore-nginx
```

### Step 5 — Review the investigation

In the portal, read the agent's full investigation log. Note:

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
- [ ] `validate.sh` returns healthy after the agent's remediation
- [ ] **Explain to your coach** — what is the difference between a platform-level health probe failure and a guest-OS failure? Why would a VM show "Running" in the portal while the service is down?

## Learning Resources

- [Azure Monitor Agent overview](https://learn.microsoft.com/en-us/azure/azure-monitor/agents/azure-monitor-agent-overview)
- [Azure Monitor — Syslog data collection](https://learn.microsoft.com/en-us/azure/azure-monitor/agents/data-collection-syslog)
- [Azure Load Balancer — health probes](https://learn.microsoft.com/en-us/azure/load-balancer/load-balancer-custom-probe-overview)
- [Azure VM — Run Command](https://learn.microsoft.com/en-us/azure/virtual-machines/run-command-overview)

## Tips

- The Syslog DCR (`dcr-web-syslog`) collects `daemon` facility logs from both VMs. The `Syslog` table in Log Analytics is the source of truth for guest-OS service failures.
- The `iaas-vm-incident-handler` subagent runs this challenge **without a custom skill** — it relies entirely on its system prompt and built-in tools. This is intentional: it shows that a well-written system prompt with clear instructions can drive correct behavior without a separate skill YAML.
- If only one VM's nginx is restarted, the load balancer will resume serving but the second VM remains broken — a silent partial failure. The agent is instructed to verify every instance, not just the first one.

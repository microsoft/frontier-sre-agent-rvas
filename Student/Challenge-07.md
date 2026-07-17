[< Previous Challenge](./Challenge-06.md) — **[Home](../README.md)** — [Next Challenge >](./Challenge-08.md)

# Challenge 07 — IaaS Service Recovery

## Introduction

Not every failure happens in a managed PaaS service where Azure can see everything. The Grubify frontend is served by **nginx** running on two IaaS virtual machines (`vm-web-1`, `vm-web-2`). When nginx crashes, Azure doesn't know about it — there are no platform-level health checks for a guest OS process. The only signal comes from the **Azure Monitor Agent (AMA)** collecting Syslog data from the VMs.

In this challenge, you'll simulate an nginx outage on both web VMs and watch the SRE Agent detect it through Syslog, diagnose the failure, and recover the service — all autonomously, using `az vm run-command` to execute remediation inside the guest OS.

This is **Scenario S4: NGINX Service Down**.

## Description

### Before you start

Verify the web tier is healthy:

```bash
Student/Resources/scenarios/scripts/validate.sh
```

### Trigger the outage

Stop nginx on both web VMs:

```bash
Student/Resources/scenarios/scripts/trigger-nginx-down.sh
```

This uses Azure Run Command to stop the nginx process on `vm-web-1` and `vm-web-2`. HTTP traffic to the web tier will start returning connection errors.

### Observe the autonomous response

1. Open the SRE Agent portal and navigate to **Incident Response**
2. Wait for the Azure Monitor alert (Syslog-based, `nginx` service stop event) to fire — allow **3–5 minutes**
3. The `web-tier-nginx` incident filter routes the incident to `iaas-vm-incident-handler`
4. Watch the agent:
   - Query the Log Analytics workspace for Syslog events on `vm-web-1` and `vm-web-2`
   - Identify the stopped nginx process
   - Use `RunAzCliWriteCommands` (az vm run-command) to restart nginx on both VMs
5. Verify the web tier recovers

### Restore (if needed)

If the agent did not complete the remediation:

```bash
Student/Resources/scenarios/scripts/restore-nginx.sh
```

## Success Criteria

To complete this challenge, demonstrate:

1. The Azure Monitor Syslog alert fired and the incident appeared in the portal
2. The incident was routed to `iaas-vm-incident-handler` (not `aca-app-incident-handler`)
3. The agent's tool call log shows Syslog queries (Log Analytics / Kusto)
4. The agent used `RunAzCliWriteCommands` to issue an `az vm run-command` to restart nginx
5. The web tier is healthy after the agent's remediation (or after manual restore)
6. **Explain to your coach** — why is AMA + Syslog necessary for detecting this failure? What would a Platform-as-a-Service equivalent look like? What are the trust and security implications of an agent that can execute commands inside a VM guest OS?

## Learning Resources

- [Azure Monitor Agent overview](https://learn.microsoft.com/en-us/azure/azure-monitor/agents/azure-monitor-agent-overview)
- [Syslog data collection with AMA](https://learn.microsoft.com/en-us/azure/azure-monitor/agents/data-collection-syslog)
- [az vm run-command](https://learn.microsoft.com/en-us/cli/azure/vm/run-command)
- [Log Analytics Kusto queries](https://learn.microsoft.com/en-us/azure/azure-monitor/logs/log-query-overview)

## Tips

- The Syslog alert is based on a pattern match in the Log Analytics workspace. If the alert doesn't fire after 8 minutes, verify that nginx actually stopped: `run-kql.sh "Syslog | where TimeGenerated > ago(15m) | take 20"`.
- The agent is `Autonomous` and **write-capable** (`RunAzCliWriteCommands`). The debrief on this scenario often surfaces interesting governance questions — lean into that conversation.
- If the web tier is still down after the agent runs, check `vm-web-2` specifically — the agent sometimes remediates only the first VM it finds in the log evidence. `restore-nginx.sh` handles both.
- You can observe the agent in interactive mode too: "Check the nginx status on the web VMs and restart it if it's down."

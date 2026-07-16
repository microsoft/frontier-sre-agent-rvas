[< Previous Solution](./Solution-06.md) | **[Home](./README.md)** | [Next Solution >](./Solution-08.md)

# Coach Guide — Challenge 04: IaaS Service Recovery (VM + NGINX)

## Purpose

This challenge demonstrates that SRE Agent handles not just cloud-native (PaaS/serverless) workloads but also **IaaS services running on VMs**. The failure mode is a classic Linux service crash; the agent detects it via Syslog (collected by Azure Monitor Agent) and uses `az vm run-command` to restart the service. The key discussion is around **write-capable agents and governance**.

Expected time: **20–25 minutes** including alert propagation.

## Mini-Lecture (10 min before challenge)

Cover:
- The AMA (Azure Monitor Agent) + Data Collection Rule path: Syslog → Log Analytics Workspace
- The `web-tier-nginx` incident filter: `titleContains: "nginx"` → routes to `iaas-vm-incident-handler`
- The subagent's `RunAzCliWriteCommands` grant and what it enables: `az vm run-command invoke`
- Governance discussion: an agent that can execute code on VMs needs audit trails, scope limits, and approval gates in production
- The `iaas-vm-incident-handler` system prompt: it is scoped to restart services, not to modify OS configuration broadly

## Expected Agent Behavior

1. Agent receives the nginx Syslog alert
2. Queries Log Analytics: `Syslog | where ProcessName == "nginx"` for error messages
3. Uses `az vm run-command invoke` on `vm-web-1` (and optionally `vm-web-2`) to check nginx status
4. Issues `systemctl start nginx` via run-command
5. Verifies nginx is running: `az vm run-command invoke --command-id RunShellScript --scripts "systemctl is-active nginx"`
6. Reports: which VMs were affected, what was found in Syslog, what command was run, current status

## Common Issues and Hints

### Alert doesn't fire or fires very slowly
- The `web-tier-nginx` alert is based on a Syslog query (absence of nginx heartbeat or explicit error). It may take 10–15 minutes to fire depending on DCR collection frequency (5 minutes) + alert evaluation window
- Coach fallback: have the student trigger via portal chat: "nginx is down on the web VMs, investigate and fix"

### Agent uses run-command but the VM is deallocated or stopped
- `trigger-nginx-down.sh` only stops the nginx service, not the VM itself — but if a student accidentally ran a broader script, the VM may be stopped
- Fix: `az vm start --name vm-web-1 --resource-group <rg>`; wait for boot; re-trigger

### Agent can't determine which VMs to target
- The subagent needs to know the VM names and resource group. These are injected via the environment context set during `make config-sre-agent`
- If the agent is guessing wrong names, verify the Terraform outputs match the context in the subagent's system prompt template

### `az vm run-command` returns an error
- The run-command extension must be installed on the VM. Verify: `az vm extension list --vm-name vm-web-1`
- If missing, it self-installs on first use — just takes longer (2–3 minutes)

### Agent restarts nginx but app is still down
- Grubify's web tier load balances across both VMs. If only one VM's nginx is restarted, the health probe may still fail
- The agent should ideally fix both VMs. If it only fixed one, prompt: "Are all web VMs healthy now?"

## Debrief Discussion Guide (10 min)

1. **What makes this different from the PaaS scenario?** — Agent had to ssh-equivalent into a VM; there's no cloud-native "revision rollback" abstraction
2. **What is the blast radius if the run-command script is wrong?** — A bad script could break the VM. Discuss least-privilege, pre-approved scripts, dry-run mode
3. **How would you audit this in production?** — Azure Activity Log records run-command invocations; Log Analytics captures the output; GitHub commit history if agent creates a record

## Success Criteria Notes

- The primary artifact is the run-command transcript in the portal incident timeline
- Accept partial credit if only one VM was remediated (both VMs were failed) — discuss the gap
- If the alert never fired and the student used manual chat trigger, that is fine — the agent behavior is the same

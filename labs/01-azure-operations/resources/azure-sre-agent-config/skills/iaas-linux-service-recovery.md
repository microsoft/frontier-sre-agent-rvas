---
name: iaas-linux-service-recovery
description: Use when a Linux service on one or more Azure Virtual Machines is stopped, failed, or unhealthy; prove the failure from Syslog, apply the smallest reversible in-guest recovery through Azure Run Command, and verify each VM plus the load-balanced endpoint.
---

# Linux service recovery on Azure Virtual Machines

Use this procedure only after telemetry proves that an in-guest Linux service is stopped, failed, or unhealthy. The active response plan or scheduled task owns the run mode; this skill never changes autonomy by itself.

## Trigger conditions

- Syslog contains a service stop, deactivation, or failure event.
- A load-balancer health probe reports one or more unhealthy VM backends.
- An operator asks to recover a named Linux service on an Azure Virtual Machine.

## Non-goals

- Do not diagnose Network Security Group, User-Defined Route, firewall, or Domain Name System faults as guest-service failures.
- Do not resize, deallocate, redeploy, reimage, or change disks as part of this procedure.
- Do not restart a service without identifying the affected VM and collecting pre-change evidence.
- Do not report recovery until both the service and the user-facing endpoint are verified.

## Evidence-first procedure

1. Identify the resource group, VM name, service name, affected endpoint, and expected healthy behavior.
2. Query recent Syslog records and capture timestamp, Computer, ProcessName, and SyslogMessage for the failure.
3. Confirm the VM provisioning state is `Succeeded` and determine whether the fault is isolated to the guest service.
4. Capture the pre-change service state with Azure Run Command using `systemctl is-active <service>` and `systemctl status <service> --no-pager`.
5. If the active run mode permits execution, start the service with the smallest reversible command: `systemctl start <service>`. Do not change packages, configuration, or enablement unless evidence requires it.
6. Verify `systemctl is-active <service>` returns `active` on every affected VM.
7. Verify the application endpoint or internal load-balancer frontend returns its expected success response.
8. Query post-change telemetry and record the recovery timestamp. Distinguish service recovery from permanent root-cause correction.

## NGINX web-tier scenario

For `alert-nginx-down`, both `vm-web-1` and `vm-web-2` can be affected. Resolve the actual VM names from Azure or Terraform outputs, recover every failed backend, and verify all three paths: each backend directly and the internal load-balancer frontend at `10.20.2.100`.

## Required output

Report the affected resource IDs, failure evidence, root-cause hypothesis and confidence, exact command executed, result for each VM, endpoint verification, remaining risk, and the repository restore script when the fault was injected by the demo.
---
name: network-exposure-review
description: Use when the user asks about internet exposure, public exposure, attack surface, open ports, NSG rules open to the internet, public IPs, storage public access, or PaaS resources reachable from the internet. Scans the resources the agent can read for network security group rules open to the internet, storage and PaaS with public access, scores each by severity, and produces a self contained HTML exposure report.
tools:
  - RunAzCliReadCommands
  - RunInTerminal
  - SaveFileToBlob
metadata:
  category: network-topology
---

# Network Exposure Review

This skill reviews broad internet Allow configurations in NSGs and public access settings for storage and selected PaaS services. Findings are configuration review candidates, not proof of effective reachability. It does not evaluate rule precedence, subnet and NIC rules together, routes, public IP association, listener state or every service firewall.

## When to use this skill

Use this skill when the user asks to:

- Review internet exposure, public attack surface, or open ports.
- Find network security group rules that allow the internet to management or database ports.
- Check which storage accounts and platform services accept public traffic.

## Operating principles

- Read only. This skill reads network and access configuration. It never changes a rule, a firewall, or a public access setting; it reports what is open and the change to close it.
- Approved read scope. It reads across the subscriptions this agent can read. If a read is denied, it records the scope as not assessed and continues. See references/permissions-and-scope.md.
- Evidence first. Every finding names the resource, what is exposed (the ports and source, or the public access setting), a severity, and the recommended change.
- Broad prefix checks include IPv4 `0.0.0.0/0`, IPv6 `::/0` and equivalent unions from the scalar and plural source fields. Unknown prefixes or unresolved service tags require review. Narrow public CIDRs are outside this broad source check, not certified safe.
- `publicNetworkAccess=Enabled` alone does not prove SQL or PaaS access is unrestricted. Review firewall rules, `defaultAction`, IP and virtual network restrictions and exceptions. Missing settings remain unknown. Account permission for anonymous blobs does not prove any container is public.
- Preserve the full resource id, and rule id when supplied, as evidence. Approve scope before collection, using playbook approval rather than claiming host authorization enforcement.
- Select identity explicitly using `AZURE_CLIENT_ID`, `SRE_IDENTITY_MODE=system-assigned`, or an explicitly approved local `SRE_IDENTITY_MODE=developer` run. No silent credential fallback.

## Workflow

The scan tool (tools/network_exposure.py) and the shared report renderer (tools/report_render.py) are bundled with this skill. Run them with RunInTerminal using the Python in the agent runtime. The collector uses the configured identity; the local renderer does not authenticate to Azure.

### Phase 1: Map the exposure

1. Run python tools/network_exposure.py with RunInTerminal. It queries Azure Resource Graph for inbound network security group rules open to the internet, storage accounts with public or anonymous access, and platform services with public network access, classifies each against references/checks-catalog.md, and prints a report_data object as JSON.
2. Broad Allow configurations for management ports or all ports receive highest review priority. Confirm effective reachability with rule precedence, NIC and subnet rules, routes and service firewall evidence before describing an endpoint as exposed.

### Phase 2: Produce the report

1. Pipe the scan into the renderer: python tools/network_exposure.py | python tools/report_render.py with RunInTerminal. It writes the self contained HTML report and returns the path. Store it with SaveFileToBlob for a link.
2. Present the report, then a short inline summary: critical exposures (management or all ports open), resources with public access, the top items, and any scope not assessed.

## Scenario coverage

This skill implements its documented checks, not every related scenario. Use the related skills for their complete evidence workflows. See [scenario routing](./references/scenarios.md).


## Expected output

- Primary: a self contained HTML exposure report, covering findings by severity and by exposure type, and the full table naming what is open and the recommended change per resource.
- Inline: critical exposures, resources with public access, and the top items to close first.
- Every finding names the resource, the exposure, a severity, and the recommended change. Nothing is changed; recommendations are for a human to apply.

## Sources

- [NSG processing and effective rules](https://learn.microsoft.com/azure/virtual-network/network-security-group-how-it-works)
- [SQL network access controls](https://learn.microsoft.com/azure/azure-sql/database/network-access-controls-overview)
- [Owned configuration checks and limits](references/checks-catalog.md)

## Assessment and customer sharing

Confirm the explicit customer scope and UTC window before collection. Accessible resources are not automatically approved scope. For a tool that enumerates all visible subscriptions, use an identity restricted to the approved scope or the related skill's scoped commands.

Follow [assessment states and limits](./references/assessment-contract.md), [permissions](./references/permissions-and-scope.md), and [customer sharing review](./references/customer-sharing.md), bundled during deployment. The shared renderer produces a sanitized draft by default; `--include-identifiers` requires an explicitly approved customer audience. Review custom exports with the same checklist.

Configure the host using [governance settings](./references/governance.json). General terminal access is not inherently read only. Never apply changes, schedule work, upload files or send messages without separate explicit approval.

## Approval boundary

Confirm explicit customer scope and the intended identity. Host authorization must enforce the bundled governance policy; general terminal access is not inherently read only. Changes, deployment, scheduling, uploads and messages require separate explicit approval. Preserve denied, missing and truncated evidence as unassessed, never healthy.

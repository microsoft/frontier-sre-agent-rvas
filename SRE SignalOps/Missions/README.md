**[Home](../README.md)** | [Deployment](../Deployment/README.md) | [Lab Details](../Lab-Details.md)

# Operational Missions

Missions use four categories: **Foundation**, **Connections & Routing**,
**Incident Response**, and **Dependencies & Networking**. These describe the
type of work, not sequential phases; follow mission numbers and prerequisites.

Complete deployment and record the normal Grubify baseline before starting.
Choose the context for the deployment you actually completed. From the repository
root, run **one** command in the terminal used for the mission:

```powershell
# Bicep deployment
$Lab = & '.\SRE SignalOps\Scripts\Get-SignalOpsContext.ps1' -EnvironmentName signalops-core

# OR Terraform deployment, after Complete-Lab.ps1 and its readiness checks
$Lab = & '.\SRE SignalOps\Scripts\Get-SignalOpsContext.ps1' `
    -TerraformPath (Resolve-Path '.\SRE SignalOps\Deployment\Terraform\infra').Path
```

For an extracted Terraform download, pass the absolute path of its `infra`
directory instead. The helper only reads deployment outputs; it does not make
Terraform resources azd-owned or run provisioning.

```powershell
$Lab | Format-List
az account set --subscription $Lab.AZURE_SUBSCRIPTION_ID
```

Verify every scope before continuing. Do not run Bicep deployment stages against
Terraform-owned groups. Use coach-provided evidence packs or a disposable
sandbox when a scenario needs resources outside the selected deployment.
Terraform completion preloads four knowledge documents; in Mission 02, audit
those documents and retrieval instead of assuming an empty memory inventory.
Both methods resolve `CONFIG_ROOT` to the same approved SignalOps configuration
maintained under [Config](../Config); the Terraform download bundles it inside
`infra`. Bicep stage 02 registers all three specialists through its postprovision
hook; Terraform completion calls the same registration implementation.
For chat, sign in to `https://sre.azure.com` and select the agent identified by
`$Lab.SRE_AGENT_ID`. The discovered `agentEndpoint` is an authenticated API, not
an anonymous browser UI.

## Evidence-pack and network sandbox contract

Missions 05, 07, 10 and 11 support two explicitly labeled modes:

- **Live:** the coach provides an isolated approved target, current baseline,
  required telemetry and alert/response-plan wiring, a bounded fault, named
  recovery owner, rollback and post-recovery evidence. Do not inject until all
  prerequisites are verified.
- **Evidence pack:** the coach supplies sanitized UTC-stamped before/fault/after
  observations. Analyze them without Azure writes and label intake, approvals,
  recovery and delivery as supplied or simulated. Missing evidence is a gap, not
  a completed live result. If no pack exists, record the mission as blocked.

For Mission 05, require VM ID, power state, recent Heartbeat, Activity Log,
monitoring configuration, alert query/settings and fired/resolved alert evidence.
For Mission 07, require protected-item ID, recovery-point/job timestamps,
incident ID/time and sanitized approval/denial/replay results. An evidence pack
does not certify a live Teams connector or approval gate.

For Missions 10–11, use a real VM-to-VM dependency in a disposable network
sandbox. The full Terraform network can be used only after the coach validates
that path and telemetry; the Bicep core has no such network. Supply subscription,
source/destination VM/NIC IDs, addresses, ports, protocol, both effective NSGs,
both effective route tables, both next-hop results, timestamped connectivity
tests, applicable flow evidence and rollback/recovery results. Do not treat a
parking VM as a Grubify dependency: the sample Grubify API uses in-memory data.
Container Apps workload traffic is not supported by VNet Flow Logs.

| Mission | Outcome |
|---|---|
| [01](./Challenge-01.md) | Investigate and Recover a Grubify Memory Incident |
| [02](./Challenge-02.md) | Build Grubify Knowledge and Incident Memory |
| [03](./Challenge-03.md) | Investigate an Evidence Blind Spot |
| [04](./Challenge-04.md) | Route a Cross-Domain Incident |
| [05](./Challenge-05.md) | Heartbeat Triage and Deep RCA |
| [06](./Challenge-06.md) | Improve the Next Heartbeat Response |
| [07](./Challenge-07.md) | Respond to a VM Backup Failure with External Approval |
| [08](./Challenge-08.md) | Exercise a Guarded HTTP-Error Response |
| [09](./Challenge-09.md) | Scope Impact with Dependency Evidence |
| [10](./Challenge-10.md) | Investigate a Network Security Failure |
| [11](./Challenge-11.md) | Investigate a Routing Black Hole |
| [12](./Challenge-12.md) | Plan a Response to an Assurance Risk |

Coach-only material remains in the [Coach folder](../Coach).

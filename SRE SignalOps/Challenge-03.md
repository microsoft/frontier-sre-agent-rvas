[< Previous Challenge](./Challenge-02.md) — **[Home](./README.md)** — [Next Challenge >](./Challenge-04.md)

# Challenge 03 — Arm the Operator

> **Capabilities added in this challenge**: Operational Skills · Tool Grants · Approval Boundaries

## Introduction

Ground truth explains the environment; skills let the agent inspect it. Load a small, deliberate operational capability set and prove that read operations, proposed writes, and approval-gated writes remain distinct.

## Description

> **Customer demo script:** Run `pwsh -File '.\SRE SignalOps\Scripts\Challenge-03.ps1'` to plan configuration, or add `-Execute` to apply it. See the [presenter runbook](./Scripts/README.md).

### 1. Inspect the local capability source

```powershell
$ConfigRoot = '.\Student\Resources\azure-sre-agent-config'
Get-ChildItem "$ConfigRoot\skills" -Filter '*.yaml' |
  Select-Object Name, Length
Get-ChildItem "$ConfigRoot\subagents" -Filter '*.yaml' |
  Select-Object Name, Length
```

Review each selected manifest before applying it. Check its description, tools, safety mode, and approval requirements.

### 2. Apply the mission configuration from PowerShell

The repository configuration engine is a Bash script. On Windows, call it explicitly from PowerShell through Git for Windows; PowerShell remains your shell and owns all variables.

```powershell
$Bash = 'C:\Program Files\Git\bin\bash.exe'
$SubscriptionId = az account show --query id -o tsv
$AgentResourceGroup = 'rg-signalops-agent'
$AgentName = 'signalops-agent'
$Repo = (Get-Location).Path.Replace('\','/').Replace('C:','/c')

$Targets = @('skills', 'subagents', 'incident-platforms', 'incident-filters')

foreach ($Target in $Targets) {
  $Command = "cd '$Repo/Student/Resources' && ./infra/scripts/sre-agent-config.sh validate --target '$Target'"
  & $Bash -lc $Command
  if ($LASTEXITCODE -ne 0) { throw "$Target validation failed." }

  $Command = "cd '$Repo/Student/Resources' && ./infra/scripts/sre-agent-config.sh plan --target '$Target' --subscription '$SubscriptionId' --resource-group '$AgentResourceGroup' --agent '$AgentName'"
  & $Bash -lc $Command
  if ($LASTEXITCODE -ne 0) { throw "$Target plan failed." }

  $Command = "cd '$Repo/Student/Resources' && ./infra/scripts/sre-agent-config.sh apply --target '$Target' --subscription '$SubscriptionId' --resource-group '$AgentResourceGroup' --agent '$AgentName'"
  & $Bash -lc $Command
  if ($LASTEXITCODE -ne 0) { throw "$Target apply failed." }
}
```

> This is not Terraform. It invokes the repository's Azure SRE Agent REST configuration client. The selective targets deliberately exclude external connectors, repositories, scheduled tasks, and knowledge files.

### 3. Verify the live data plane

```powershell
foreach ($Target in $Targets) {
  $Command = "cd '$Repo/Student/Resources' && ./infra/scripts/sre-agent-config.sh verify --target '$Target' --subscription '$SubscriptionId' --resource-group '$AgentResourceGroup' --agent '$AgentName'"
  & $Bash -lc $Command
  if ($LASTEXITCODE -ne 0) { throw "$Target verification failed." }
}
```

### 4. Probe safety

Ask the agent to inspect Grubify health, then ask it to delete the active revision. It may investigate, but it must not execute the destructive request without the configured approval path.

## Success Criteria

- [ ] Skills, subagents, the Azure Monitor incident platform, and incident filters pass validation and plan before apply
- [ ] All four target classes verify against the live agent
- [ ] A read-only health investigation executes successfully
- [ ] A destructive request is rejected or held for approval
- [ ] **Explain to your coach** — why are explicit tool grants stronger than relying only on a system prompt?

## Learning Resources

- [Azure SRE Agent skills](https://learn.microsoft.com/en-us/azure/sre-agent/skills)
- [Azure SRE Agent API sub-resources](https://learn.microsoft.com/en-us/azure/sre-agent/api-reference#sub-resources)
- [PowerShell about automatic variables](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_automatic_variables)

## Tips

- Never continue after a nonzero validation exit code.
- Use `plan` before `apply` when changing an existing customer agent.
- Keep the agent in Review mode through the remaining setup missions.

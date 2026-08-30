[< Previous Challenge](./Challenge-05.md) — **[Home](./README.md)** — [Next Challenge >](./Challenge-07.md)

# Challenge 06 — Understand Response Plans

> **Capabilities added in this challenge**: Incident Filters · Response Plans · Approval and Validation Gates

## Introduction

Automation is only trustworthy when operators can explain its control flow. Trace one response plan from the incoming signal to closure and expose every decision gate.

## Description

> **Customer demo script:** Run `pwsh -File '.\SRE SignalOps\Scripts\Challenge-06.ps1'` to show incident filters and Azure Monitor wiring. See the [presenter runbook](./Scripts/README.md).

Select one non-destructive Azure Monitor alert and ask the agent to explain the complete execution path. Produce a response-plan trace with:

- incident source and filter conditions;
- specialist and skill selection;
- evidence collected before classification;
- severity and confidence decisions;
- proposed actions and approval requirements;
- recovery verification and closure criteria;
- timeout, retry, and escalation behavior.

Use PowerShell to inventory incident filters:

```powershell
$SubscriptionId = az account show --query id -o tsv
$AgentResourceGroup = 'rg-signalops-agent'
$AgentName = 'signalops-agent'
$ApiVersion = '2025-05-01-preview'
$Base = "https://management.azure.com/subscriptions/$SubscriptionId/resourceGroups/$AgentResourceGroup/providers/Microsoft.App/agents/$AgentName"
az rest --method GET --url "$Base/incidentFilters?api-version=$ApiVersion" --query 'value[].name' -o table
```

Run the plan as an exercise incident. Do not approve a write. Compare the observed timeline with the documented trace and mark every skipped or unexpected stage.

## Success Criteria

- [ ] The filter condition and selected plan are unambiguous
- [ ] Investigation precedes action selection
- [ ] Approval, validation, timeout, and escalation gates are visible
- [ ] The exercise timeline is compared with the expected control flow
- [ ] **Explain to your coach** — which gate prevents a plausible diagnosis from becoming an unsafe action?

## Learning Resources

- [Automate incidents with Azure SRE Agent](https://learn.microsoft.com/en-us/azure/sre-agent/automate-incidents)
- [Azure SRE Agent API sub-resources](https://learn.microsoft.com/en-us/azure/sre-agent/api-reference#sub-resources)
- [Azure Monitor alert processing rules](https://learn.microsoft.com/en-us/azure/azure-monitor/alerts/alerts-processing-rules)

## Tips

- A response plan is control flow, not only a prompt.
- Closure must depend on recovery evidence.
- Keep the exercise non-destructive.

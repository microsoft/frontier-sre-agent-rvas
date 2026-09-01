[< Previous Challenge](./Challenge-06.md) — **[Home](./README.md)** — [Next Challenge >](./Challenge-08.md)

# Challenge 07 — Exercise a Guarded HTTP-Error Response

> **Incident capability exercised in this challenge**: Alert Routing · Guarded Response · Recovery Validation

## Introduction

Turn the Grubify HTTP-error report into a controlled incident exercise. Observe how the SRE Agent receives the signal, gathers evidence, proposes a bounded response, waits at the action gate, and defines proof of recovery.

## Description

> **Customer demo script:** Run `pwsh -File '.\SRE SignalOps\Scripts\Challenge-07.ps1'` to show incident filters and Azure Monitor wiring. See the [presenter runbook](./Scripts/README.md).

Use a genuine non-destructive HTTP-error alert when available, or invoke a clearly labeled `EXERCISE - Grubify HTTP errors` event that matches the configured sample-food filter. Do not inject production failures merely to create an alert.

Ask the SRE Agent to handle the event and produce an observed incident timeline containing:

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

Do not approve a write. Compare the observed timeline with the intended response path and mark every skipped or unexpected stage. The SRE Agent must stop or escalate when evidence is insufficient, approval times out, a proposed action fails, or recovery cannot be demonstrated.

## Success Criteria

- [ ] The genuine or exercise incident is accurately labeled and routed by the intended HTTP-error filter
- [ ] Current Grubify evidence and classification precede action selection
- [ ] The proposed response states scope, risk, rollback, approval, and recovery checks
- [ ] Timeout, failed-action, failed-validation, and escalation paths are visible
- [ ] The observed incident timeline is compared with the intended response path
- [ ] **Explain to your coach** — why must incident closure depend on service recovery evidence rather than workflow completion?

## Learning Resources

- [Automate incidents with Azure SRE Agent](https://learn.microsoft.com/en-us/azure/sre-agent/automate-incidents)
- [Azure SRE Agent API sub-resources](https://learn.microsoft.com/en-us/azure/sre-agent/api-reference#sub-resources)
- [Azure Monitor alert processing rules](https://learn.microsoft.com/en-us/azure/azure-monitor/alerts/alerts-processing-rules)

## Tips

- The incident outcome matters more than the response-plan terminology.
- Closure must depend on recovery evidence.
- Keep the exercise labeled and non-destructive.

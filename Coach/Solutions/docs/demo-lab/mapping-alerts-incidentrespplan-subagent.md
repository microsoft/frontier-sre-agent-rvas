# Mapping: Azure Monitor alert to incident response plan to sub-agent

This document maps every Azure Monitor alert defined in the demo-lab desired state (Terraform) to the incident response plan that matches it and the sub-agent that handles it. It is derived deterministically from the alert rules in `04-terraform/` and the three response plans in `06-sre-agent-configuration/automations/incident-filters/`.

The project defines **three** Azure Monitor alerts, and each has a unique mapping:

| Alerts Defined | Incident Response Plan (matched) | Sub-agent |
|---|---|---|
| `alert-vflta-food-http-5xx` (Sev1, metric alert for HTTP 5xx on Container Apps API) | `sample-food-http-errors` (match by severity Sev1 + `titleContains: food`) | `aca-app-incident-handler` |
| `alert-vflta-nginx-down` (Sev2, display name: “NGINX service down on web tier”) | `web-tier-nginx` (match by severity Sev2 + `titleContains: nginx`) | `iaas-vm-incident-handler` |
| `alert-vflta-denied-flow-spike` (Sev2, display name: “Denied VNet flow spike”) | `network-observability-review` (match by severity Sev2 + exclusion `titleNotContains: nginx`) | `network-traffic-analyst` |

Completeness note: the project defines **3 Azure Monitor alerts** in total, and each has a unique mapping to its incident response plan and sub-agent.